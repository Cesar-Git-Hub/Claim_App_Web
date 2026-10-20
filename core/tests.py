import io
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import Claim, Import

CSV = (
    "Ref,Name,Date,Amount,Trxn Code,Merchants,Extra,Other,Respond Code\n"
    '1,a,x,"1,234.50",ot,ACME,,,00\n'
    "2,b,y,0,OS,ACME,,,50\n"
    "3,c,z,abc,OR,BETA,,,05\n"
)


def csv_upload(text=CSV, name="claims.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


class BaseCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("tester", password="pw-12345-xyz")
        self.client.force_login(self.user)

    def make(self, code, amount="10.00", merchant="M", **extra):
        return Claim.objects.create(
            trxn_code=code, merchant=merchant, amount=None if amount is None else Decimal(amount), **extra
        )

    def act(self, name):
        return self.client.post(reverse("action"), {"action": name})


class AuthTests(TestCase):
    def test_anonymous_is_redirected_everywhere(self):
        for name in ("dashboard",):
            resp = self.client.get(reverse(name))
            self.assertRedirects(resp, f"{reverse('login')}?next={reverse(name)}")
        for name in ("upload", "action"):
            resp = self.client.post(reverse(name))
            self.assertEqual(resp.status_code, 302)
            self.assertIn(reverse("login"), resp["Location"])

    def test_login_and_logout(self):
        get_user_model().objects.create_user("u", password="pw-12345-xyz")
        resp = self.client.post(reverse("login"), {"username": "u", "password": "pw-12345-xyz"})
        self.assertRedirects(resp, reverse("dashboard"))
        self.assertRedirects(self.client.post(reverse("logout")), reverse("login"))

    def test_bad_login_shows_error(self):
        resp = self.client.post(reverse("login"), {"username": "u", "password": "nope"})
        self.assertContains(resp, "incorrectos")

    def test_logout_requires_post(self):
        self.client.force_login(get_user_model().objects.create_user("v", password="pw-12345-xyz"))
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)


class UploadTests(BaseCase):
    def test_csv_import_maps_headers_and_keeps_bad_amounts_null(self):
        resp = self.client.post(reverse("upload"), {"file": csv_upload()})
        self.assertRedirects(resp, reverse("dashboard"))
        rows = list(Claim.objects.order_by("id"))
        self.assertEqual([r.amount for r in rows], [Decimal("1234.50"), Decimal("0.00"), None])
        self.assertEqual([r.trxn_code for r in rows], ["OT", "OS", "OR"])
        self.assertEqual(rows[1].respond_code, "50")
        self.assertEqual(rows[0].merchant, "ACME")
        self.assertFalse(Claim.objects.filter(merchant="nan").exists())
        self.assertEqual(Import.objects.get().row_count, 3)
        self.assertEqual(Import.objects.get().uploaded_by, self.user)

    def test_warnings_are_shown(self):
        resp = self.client.post(reverse("upload"), {"file": csv_upload()}, follow=True)
        self.assertContains(resp, "importado: 3 filas")
        self.assertContains(resp, "no se pudo leer")

    def test_semicolon_latin1_csv(self):
        text = "Ref;Name;Date;Amount;Trxn Code;Merchants;;;Respond Code\n1;José;d;1.234,50;OT;ÑANDÚ;;;00\n"
        upload = SimpleUploadedFile("a.csv", text.encode("latin-1"))
        self.client.post(reverse("upload"), {"file": upload})
        claim = Claim.objects.get()
        self.assertEqual((claim.col2, claim.amount, claim.merchant), ("José", Decimal("1234.50"), "ÑANDÚ"))

    def test_xlsx_import(self):
        from openpyxl import Workbook
        wb = Workbook()
        wb.active.append(["Ref", "Name", "Date", "Amount", "Trxn Code", "Merchants", "", "", "Respond Code"])
        wb.active.append([7, "x", "d", 99.5, "os", "SHOP", None, None, 50])
        buf = io.BytesIO()
        wb.save(buf)
        self.client.post(reverse("upload"), {"file": SimpleUploadedFile("a.xlsx", buf.getvalue())})
        claim = Claim.objects.get()
        self.assertEqual((claim.col1, claim.amount, claim.trxn_code, claim.respond_code), ("7", Decimal("99.50"), "OS", "50"))

    def test_rejections_import_nothing(self):
        self.assertRedirects(self.client.post(reverse("upload")), reverse("dashboard"))
        for name in ("a.txt", "a.xls"):
            self.client.post(reverse("upload"), {"file": SimpleUploadedFile(name, b"x")})
        self.client.post(reverse("upload"), {"file": csv_upload("Amount\n", "empty.csv")})
        self.assertEqual(Claim.objects.count(), 0)
        self.assertEqual(Import.objects.count(), 0)

    def test_append_by_default_and_replace_on_request(self):
        self.client.post(reverse("upload"), {"file": csv_upload()})
        self.client.post(reverse("upload"), {"file": csv_upload()})
        self.assertEqual(Claim.objects.count(), 6)
        self.client.post(reverse("upload"), {"file": csv_upload(), "replace": "1"})
        self.assertEqual(Claim.objects.count(), 3)
        self.assertEqual(Import.objects.count(), 1)

    def test_undo_last_import(self):
        self.make("OT")  # legacy row without a batch must survive
        self.client.post(reverse("upload"), {"file": csv_upload()})
        self.assertEqual(Claim.objects.count(), 4)
        self.act("undo_import")
        self.assertEqual(Claim.objects.count(), 1)
        self.assertEqual(Import.objects.count(), 0)


class ActionTests(BaseCase):
    def test_mark_then_confirm_flow(self):
        ot, os_, orr = self.make("OT"), self.make("OS"), self.make("OR")
        zero = self.make("OT", amount="0.00", merchant="Z")
        self.act("mark_duplicates")
        self.act("mark_zeros")
        marked = set(Claim.objects.filter(to_delete=True).values_list("id", flat=True))
        self.assertEqual(marked, {ot.id, os_.id, zero.id})
        self.assertEqual(Claim.objects.count(), 4)  # nothing deleted yet
        self.act("confirm_delete")
        self.assertEqual(list(Claim.objects.values_list("id", flat=True)), [orr.id])

    def test_clear_marks(self):
        self.make("OT", amount="0.00")
        self.act("mark_zeros")
        self.assertEqual(Claim.objects.filter(to_delete=True).count(), 1)
        self.act("clear_marks")
        self.assertEqual(Claim.objects.filter(to_delete=True).count(), 0)

    def test_mark_code50_only_matches_exactly_50(self):
        a = self.make("OT", respond_code="50")
        self.make("OT", respond_code="05", merchant="B")
        self.make("OT", respond_code="", merchant="C")
        self.act("mark_code50")
        self.assertEqual(list(Claim.objects.filter(to_delete=True)), [a])

    def test_null_amount_is_not_zero(self):
        self.make("OT", amount=None)
        self.act("mark_zeros")
        self.assertEqual(Claim.objects.filter(to_delete=True).count(), 0)

    def test_unknown_action_and_get_not_allowed(self):
        self.assertRedirects(self.act("nope"), reverse("dashboard"))
        self.assertEqual(self.client.get(reverse("action")).status_code, 405)
        self.assertEqual(self.client.get(reverse("upload")).status_code, 405)


class DashboardTests(BaseCase):
    def ids(self, **params):
        resp = self.client.get(reverse("dashboard"), params)
        self.assertEqual(resp.status_code, 200)
        return [c.id for c in resp.context["page_obj"]]

    def test_filters(self):
        a, b = self.make("OT"), self.make("OS")
        solo = self.make("OT", amount="5.00", merchant="SOLO")
        zero = self.make("OT", amount="0.00", merchant="Z", respond_code="50")
        zero.to_delete = True
        zero.save()
        self.assertEqual(len(self.ids()), 4)
        self.assertCountEqual(self.ids(filter="duplicates"), [a.id, b.id])
        self.assertEqual(self.ids(filter="zero"), [zero.id])
        self.assertEqual(self.ids(filter="code50"), [zero.id])
        self.assertEqual(self.ids(filter="marked"), [zero.id])
        self.assertEqual(self.ids(filter="bogus").count(solo.id), 1)

    def test_search_and_total(self):
        self.make("OT", amount="10.00", merchant="ACME STORE")
        self.make("OT", amount="5.50", merchant="OTHER")
        resp = self.client.get(reverse("dashboard"), {"q": "acme"})
        self.assertEqual(resp.context["total"], Decimal("10.00"))
        self.assertEqual(len(resp.context["page_obj"]), 1)

    def test_pagination_keeps_query(self):
        for i in range(150):
            Claim.objects.create(col1=f"row{i}", merchant="M", amount=Decimal("1"))
        resp = self.client.get(reverse("dashboard"), {"q": "row"})
        self.assertEqual(len(resp.context["page_obj"]), 100)
        self.assertContains(resp, "q=row&page=2")
        self.assertEqual(len(self.client.get(reverse("dashboard"), {"q": "row", "page": 2}).context["page_obj"]), 50)

    def test_messages_are_rendered(self):
        self.make("OT", amount="0.00")
        resp = self.client.post(reverse("action"), {"action": "mark_zeros"}, follow=True)
        self.assertContains(resp, "marcados")
