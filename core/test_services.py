import io
from decimal import Decimal

from django.test import SimpleTestCase

from . import services


class FakeUpload(io.BytesIO):
    def __init__(self, data, name):
        super().__init__(data)
        self.name = name
        self.size = len(data)


class ParseAmountTests(SimpleTestCase):
    def test_formats(self):
        cases = {
            "1,234.56": "1234.56", "1.234,56": "1234.56", "1,234": "1234.00", "12,5": "12.50",
            "12.5": "12.50", "(100.00)": "-100.00", "-5.5": "-5.50", "5-": "-5.00", "0": "0.00",
            "$ 1,000.00": "1000.00", "1,234,567.89": "1234567.89", "1.234.567": "1234567.00",
            "0.123": "0.12", ".5": "0.50", "  42  ": "42.00",
            "": None, "   ": None, "abc": None, "nan": None, "-": None, "99999999999": None,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                got = services.parse_amount(raw)
                self.assertEqual(None if got is None else str(got), expected)

    def test_non_string_values(self):
        self.assertEqual(services.parse_amount(12.5), Decimal("12.50"))
        self.assertEqual(services.parse_amount(7), Decimal("7.00"))
        self.assertEqual(services.parse_amount(Decimal("1.005")), Decimal("1.01"))
        self.assertIsNone(services.parse_amount(None))
        self.assertIsNone(services.parse_amount(float("nan")))
        self.assertIsNone(services.parse_amount(True))


class CleanTextTests(SimpleTestCase):
    def test_empty_values_are_empty_strings_not_nan(self):
        self.assertEqual(services.clean_text(None), "")
        self.assertEqual(services.clean_text(float("nan")), "")
        self.assertEqual(services.clean_text("  hi "), "hi")
        self.assertEqual(services.clean_text(123.0), "123")
        self.assertEqual(services.clean_text("x" * 10, 4), "xxxx")


class DuplicateRuleTests(SimpleTestCase):
    @staticmethod
    def row(id, code, amount="10.00", merchant="M"):
        return {"id": id, "amount": None if amount is None else Decimal(amount),
                "trxn_code": code, "merchant": merchant}

    def test_ot_vs_os_flags_only_os(self):
        rows = [self.row(1, "OT"), self.row(2, "OS"), self.row(3, "OS")]
        self.assertEqual(services.find_duplicate_ids(rows), {2, 3})

    def test_or_or_om_flags_ot_and_os(self):
        for code in ("OR", "OM"):
            rows = [self.row(1, "OT"), self.row(2, "OS"), self.row(3, code)]
            self.assertEqual(services.find_duplicate_ids(rows), {1, 2})

    def test_ot_duplicates_alone_are_kept(self):
        self.assertEqual(services.find_duplicate_ids([self.row(1, "OT"), self.row(2, "OT")]), set())

    def test_different_merchant_or_amount_do_not_match(self):
        rows = [self.row(1, "OT"), self.row(2, "OS", merchant="OTHER"), self.row(3, "OR", amount="11.00")]
        self.assertEqual(services.find_duplicate_ids(rows), set())

    def test_rows_without_amount_are_ignored(self):
        rows = [self.row(1, "OT", amount=None), self.row(2, "OR", amount=None)]
        self.assertEqual(services.find_duplicate_ids(rows), set())

    def test_codes_are_case_and_space_insensitive(self):
        rows = [self.row(1, " ot "), self.row(2, "os")]
        self.assertEqual(services.find_duplicate_ids(rows), {2})


class ParseRowsTests(SimpleTestCase):
    HEADER = ["Ref", "Name", "Date", "Amount", "Trxn Code", "Merchants", "X", "Y", "Respond Code"]

    def test_maps_columns_by_header_name(self):
        rows = [self.HEADER, ["1", "a", "d", "1,234.50", "ot", "ACME", "", "", "50"]]
        records, stats = services.parse_rows(rows)
        self.assertEqual(records, [{
            "col1": "1", "col2": "a", "col3": "d", "amount": Decimal("1234.50"),
            "trxn_code": "OT", "merchant": "ACME", "respond_code": "50"}])
        self.assertEqual(stats["defaulted"], [])

    def test_falls_back_to_default_positions_and_reports_it(self):
        header = ["A", "B", "C", "D", "E", "F", "G", "H", "I"]
        records, stats = services.parse_rows([header, ["1", "2", "3", "", "5.00", "OS", "SHOP", "", "05"]])
        self.assertEqual(records[0]["amount"], Decimal("5.00"))
        self.assertEqual(records[0]["trxn_code"], "OS")
        self.assertEqual(records[0]["merchant"], "SHOP")
        self.assertEqual(records[0]["respond_code"], "05")
        self.assertEqual(len(stats["defaulted"]), 4)

    def test_bad_amounts_counted_blank_amounts_not(self):
        rows = [self.HEADER, ["1", "", "", "abc", "OT", "M", "", "", ""], ["2", "", "", "", "OT", "M", "", "", ""]]
        records, stats = services.parse_rows(rows)
        self.assertEqual(stats["bad_amounts"], 1)
        self.assertEqual([r["amount"] for r in records], [None, None])

    def test_blank_lines_skipped_and_empty_cells_stay_empty(self):
        rows = [self.HEADER, ["", "", "", "", "", "", "", "", ""], ["1", None, "", "5", None, None, None, None, None]]
        records, _ = services.parse_rows(rows)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["col2"], "")
        self.assertEqual(records[0]["merchant"], "")

    def test_truncation_flags(self):
        rows = [self.HEADER] + [["1", "", "", "1"]] * (services.MAX_ROWS + 1)
        records, stats = services.parse_rows(rows)
        self.assertEqual(len(records), services.MAX_ROWS)
        self.assertTrue(stats["truncated_rows"])
        wide = [["c%d" % i for i in range(30)], ["x"] * 30]
        self.assertTrue(services.parse_rows(wide)[1]["truncated_cols"])


class ReadTableTests(SimpleTestCase):
    def test_semicolon_latin1_csv(self):
        data = "Ref;Name;Amount\n1;José;1.234,50\n".encode("latin-1")
        rows = services.read_table(FakeUpload(data, "a.csv"))
        self.assertEqual(rows[1], ["1", "José", "1.234,50"])

    def test_utf8_bom_csv(self):
        data = "\ufeffRef,Name\n1,Ñandú\n".encode("utf-8")
        rows = services.read_table(FakeUpload(data, "a.csv"))
        self.assertEqual(rows[0][0], "Ref")
        self.assertEqual(rows[1][1], "Ñandú")

    def test_xlsx(self):
        from openpyxl import Workbook
        wb = Workbook()
        wb.active.append(["Ref", "Amount"])
        wb.active.append([1, 12.5])
        buffer = io.BytesIO()
        wb.save(buffer)
        rows = services.read_table(FakeUpload(buffer.getvalue(), "a.xlsx"))
        self.assertEqual(rows[1], [1, 12.5])

    def test_rejects_bad_input(self):
        with self.assertRaises(services.UploadError):
            services.read_table(FakeUpload(b"x", "a.txt"))
        with self.assertRaises(services.UploadError):
            services.read_table(FakeUpload(b"x", "a.xls"))
        with self.assertRaises(services.UploadError):
            services.read_table(FakeUpload(b"not a zip", "a.xlsx"))
        big = FakeUpload(b"x", "a.csv")
        big.size = services.MAX_UPLOAD_BYTES + 1
        with self.assertRaises(services.UploadError):
            services.read_table(big)
