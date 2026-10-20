import os
import secrets

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import redirect, render
import logging
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Exists, OuterRef, Q, Sum
from django.views.decorators.http import require_POST

from . import services
from .models import Claim, Import

logger = logging.getLogger(__name__)

PAGE_SIZE = 100
CHUNK = 500


# ------------------------------------------------------------------ dashboard

@login_required
def dashboard(request):
    claims = Claim.objects.all()

    q = request.GET.get("q", "").strip()
    if q:
        claims = claims.filter(
            Q(col1__icontains=q) | Q(col2__icontains=q) | Q(col3__icontains=q)
            | Q(merchant__icontains=q) | Q(trxn_code__icontains=q)
        )

    flt = request.GET.get("filter", "")
    if flt == "zero":
        claims = claims.filter(amount=0)
    elif flt == "code50":
        claims = claims.filter(respond_code="50")
    elif flt == "duplicates":
        # another row with the same amount and merchant (the grouping the duplicate rules use)
        same = Claim.objects.filter(amount=OuterRef("amount"), merchant=OuterRef("merchant")).exclude(pk=OuterRef("pk"))
        claims = claims.filter(amount__isnull=False).filter(Exists(same))
    elif flt == "marked":
        claims = claims.filter(to_delete=True)
    else:
        flt = ""

    total = claims.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    page_obj = Paginator(claims.order_by("id"), PAGE_SIZE).get_page(request.GET.get("page"))

    params = request.GET.copy()
    params.pop("page", None)

    return render(request, "core/dashboard.html", {
        "page_obj": page_obj,
        "total": total,
        "q": q,
        "flt": flt,
        "querystring": params.urlencode(),
        "marked_count": Claim.objects.filter(to_delete=True).count(),
        "last_import": Import.objects.first(),
    })


# ------------------------------------------------------------------ upload

@login_required
@require_POST
def upload(request):
    uploaded = request.FILES.get("file")
    if not uploaded:
        messages.error(request, "Selecciona un archivo antes de cargar.")
        return redirect("dashboard")

    try:
        rows = services.read_table(uploaded)
        records, stats = services.parse_rows(rows)
    except services.UploadError as exc:
        messages.error(request, str(exc))
        return redirect("dashboard")
    except Exception:
        logger.exception("Error procesando %s", uploaded.name)
        messages.error(request, "No se pudo procesar el archivo. Revisa los logs.")
        return redirect("dashboard")

    if not records:
        messages.error(request, "El archivo no contiene filas de datos.")
        return redirect("dashboard")

    try:
        with transaction.atomic():
            if request.POST.get("replace") == "1":
                Claim.objects.all().delete()
                Import.objects.all().delete()
            batch = Import.objects.create(filename=uploaded.name[:255], uploaded_by=request.user, row_count=len(records))
            Claim.objects.bulk_create([Claim(batch=batch, **r) for r in records], batch_size=CHUNK)
    except Exception:
        logger.exception("Error guardando %s", uploaded.name)
        messages.error(request, "No se pudo guardar el archivo. No se importó nada.")
        return redirect("dashboard")

    messages.success(request, f"Archivo «{uploaded.name}» importado: {len(records)} filas.")
    if stats["bad_amounts"]:
        messages.warning(request, f"{stats['bad_amounts']} filas tienen un Amount que no se pudo leer; quedaron sin monto (vacío), no en 0.")
    if stats["truncated_rows"]:
        messages.warning(request, f"El archivo tiene más de {services.MAX_ROWS} filas; solo se importaron las primeras {services.MAX_ROWS}.")
    if stats["truncated_cols"]:
        messages.warning(request, f"El archivo tiene más de {services.MAX_COLS} columnas; se ignoraron las sobrantes.")
    if stats["defaulted"]:
        messages.warning(request, "No encontré estos encabezados y usé la columna por defecto: " + ", ".join(stats["defaulted"]) + ".")
    return redirect("dashboard")


# ------------------------------------------------------------------ actions

def _mark_ids(ids):
    ids = list(ids)
    return sum(Claim.objects.filter(id__in=ids[i:i + CHUNK], to_delete=False).update(to_delete=True)
               for i in range(0, len(ids), CHUNK))


def _mark_zeros(request):
    n = Claim.objects.filter(amount=0, to_delete=False).update(to_delete=True)
    messages.success(request, f"{n} registros con Amount = 0 marcados. Revisa el filtro «Marcados» y confirma.")


def _mark_code50(request):
    n = Claim.objects.filter(respond_code="50", to_delete=False).update(to_delete=True)
    messages.success(request, f"{n} registros con Respond Code = 50 marcados. Revisa el filtro «Marcados» y confirma.")


def _mark_duplicates(request):
    rows = Claim.objects.filter(to_delete=False, amount__isnull=False).values("id", "amount", "trxn_code", "merchant")
    n = _mark_ids(services.find_duplicate_ids(rows))
    if n:
        messages.success(request, f"{n} registros marcados por las reglas de duplicados. Revisa el filtro «Marcados» y confirma.")
    else:
        messages.info(request, "No se encontraron duplicados que cumplan las reglas.")


def _confirm_delete(request):
    deleted, _ = Claim.objects.filter(to_delete=True).delete()
    messages.success(request, f"{deleted} registros eliminados.")


def _clear_marks(request):
    n = Claim.objects.filter(to_delete=True).update(to_delete=False)
    messages.success(request, f"{n} marcas quitadas.")


def _undo_import(request):
    last = Import.objects.first()
    if last is None:
        messages.info(request, "No hay importaciones para deshacer.")
        return
    name, count = last.filename, last.claims.count()
    last.delete()  # cascades to its claims
    messages.success(request, f"Importación «{name}» deshecha ({count} registros eliminados).")


ACTIONS = {
    "mark_zeros": _mark_zeros,
    "mark_code50": _mark_code50,
    "mark_duplicates": _mark_duplicates,
    "confirm_delete": _confirm_delete,
    "clear_marks": _clear_marks,
    "undo_import": _undo_import,
}


@login_required
@require_POST
def action(request):
    name = request.POST.get("action", "")
    handler = ACTIONS.get(name)
    if handler is None:
        messages.error(request, "Acción no reconocida.")
        return redirect("dashboard")
    try:
        with transaction.atomic():
            handler(request)
    except Exception:
        logger.exception("Error ejecutando la acción %s", name)
        messages.error(request, "No se pudo completar la acción. Revisa los logs.")
    return redirect("dashboard")

# ------------------------------------------------------------------ signup

class SignUpForm(UserCreationForm):
    codigo = forms.CharField(label="Código de invitación", widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

    def clean_codigo(self):
        expected = os.environ.get("DJANGO_SIGNUP_CODE", "")
        given = self.cleaned_data["codigo"]
        if not expected or not secrets.compare_digest(given.encode(), expected.encode()):
            raise forms.ValidationError("Código de invitación inválido.")
        return given


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Cuenta creada. Ya puedes iniciar sesión.")
            return redirect("login")
    else:
        form = SignUpForm()
    return render(request, "core/signup.html", {"form": form})