import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
import traceback

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum, Q

import pandas as pd

from .models import Claim

logger = logging.getLogger(__name__)

SHOW_TRACE_IN_MESSAGES = False
DECIMAL_QUANT = Decimal("0.01")

# ------------------------
# Funciones auxiliares
# ------------------------

def normalize_number_str(s: str) -> str:
    if s is None:
        return "0"
    s = str(s).strip()
    if s == "":
        return "0"
    s = re.sub(r"\s+", "", s)
    if not re.search(r"\d", s):
        return "0"
    sign = ""
    if s.startswith("+") or s.startswith("-"):
        sign = s[0]
        s = s[1:]
    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "")
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    else:
        if "," in s and "." not in s:
            s = s.replace(",", ".")
    s = re.sub(r"[^0-9.\-+]", "", s)
    if s in ["", ".", "+", "-"]:
        return "0"
    return sign + s

def safe_parse_decimal(value):
    try:
        normalized = normalize_number_str(value)
        return Decimal(normalized).quantize(DECIMAL_QUANT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")

def safe_parse_int(value):
    try:
        return int(float(value))
    except Exception:
        return 0

# ------------------------
# Funciones de filtrado
# ------------------------

def marcar_valores_cero(df):
    df["ToDelete"] = df["Amount"].apply(lambda x: safe_parse_decimal(x) == Decimal("0.00"))
    return df

def marcar_codigos_50(df):
    df["ToDelete"] = df["Respond Code"].apply(lambda x: safe_parse_int(x) == 50)
    return df

def marcar_duplicados(df):
    df["ToDelete"] = False
    df["Trxn Code"] = df["Trxn Code"].str.strip().str.upper()
    df["Merchants"] = df["Merchants"].str.strip().str.upper()

    grouped = df.groupby(["Amount", "Merchants"])
    for (amount, merchant), group in grouped:
        tipos = set(group["Trxn Code"].tolist())

        # Caso 1: OR/OM junto con OT/OS → eliminar todos
        if ("OR" in tipos or "OM" in tipos) and ("OT" in tipos or "OS" in tipos):
            df.loc[group.index, "ToDelete"] = True

        # Caso 2: OT y OS → eliminar solo OS
        elif "OT" in tipos and "OS" in tipos:
            df.loc[group[group["Trxn Code"] == "OS"].index, "ToDelete"] = True

        # Caso 3: OS sin OT/OR/OM → se conserva
        # Caso 4: OT sin match → se conserva
    return df

def eliminar_marcadas():
    Claim.objects.filter(to_delete=True).delete()

# ------------------------
# Autenticación
# ------------------------

def user_login(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect("dashboard")
        else:
            return render(request, "core/login.html", {"error": "Credenciales inválidas"})
    return render(request, "core/login.html")

def user_logout(request):
    logout(request)
    return redirect("login")

# ------------------------
# Dashboard principal
# ------------------------

@login_required
def dashboard(request):
    claims_qs = Claim.objects.all()

    if request.method == "POST":
        if "btn_limpiar" in request.POST:
            Claim.objects.all().delete()
            messages.success(request, "Toda la data ha sido limpiada correctamente.")
            return redirect("dashboard")

        if "btn_eliminar_marcadas" in request.POST:
            eliminar_marcadas()
            messages.success(request, "Transacciones marcadas eliminadas correctamente.")
            return redirect("dashboard")

        uploaded = request.FILES.get("file")
        if not uploaded:
            messages.error(request, "No se seleccionó ningún archivo.")
            return redirect("dashboard")

        filename = uploaded.name.lower()

        try:
            # Leer archivo SIN encabezados
            if filename.endswith(".csv"):
                df = pd.read_csv(uploaded, header=None, dtype=str)
            elif filename.endswith((".xls", ".xlsx")):
                df = pd.read_excel(uploaded, header=None, engine="openpyxl", dtype=str)
            else:
                messages.error(request, "Formato no soportado. Usa .csv, .xls o .xlsx.")
                return redirect("dashboard")

            # Asignar encabezados predeterminados (12 columnas)
            df.columns = [
                "Date Marked", "Dated and Time", "Account", "Mark Type", "Amount",
                "Trxn Code", "Merchants", "Entry Mode", "Respond Code", "ECI",
                "Approval Code", "Customer ID"
            ]

            df = df.iloc[:6000, :].copy()

            for col in df.select_dtypes(include=["object"]).columns:
                df[col] = df[col].astype(str).str.strip()

            if "btn_valores_cero" in request.POST:
                df = marcar_valores_cero(df)
            elif "btn_codigos_50" in request.POST:
                df = marcar_codigos_50(df)
            elif "btn_duplicados" in request.POST:
                df = marcar_duplicados(df)

            claims_to_create = []
            for i, row in df.iterrows():
                try:
                    claim = Claim(
                        col1=row.get("Date Marked"),
                        col2=row.get("Dated and Time"),
                        col3=row.get("Account"),
                        col4=safe_parse_decimal(row.get("Amount")),
                        col5=row.get("Mark Type"),
                        col6=row.get("Trxn Code"),
                        col7=row.get("Merchants"),
                        col8=row.get("Entry Mode"),
                        col9=row.get("Respond Code"),
                        col10=row.get("ECI"),
                        col11=row.get("Approval Code"),
                        col12=row.get("Customer ID"),
                        to_delete=row.get("ToDelete", False),
                    )
                    claims_to_create.append(claim)
                except Exception as ex:
                    logger.warning("Fila %s inválida: %s", i, ex)

            chunk_size = 1000
            with transaction.atomic():
                for start in range(0, len(claims_to_create), chunk_size):
                    Claim.objects.bulk_create(claims_to_create[start:start + chunk_size])

            messages.success(request, f"Archivo procesado correctamente. {len(claims_to_create)} filas importadas.")
            return redirect("dashboard")

        except Exception as e:
            logger.exception("Error procesando archivo subido: %s", e)
            if SHOW_TRACE_IN_MESSAGES:
                messages.error(request, f"Error procesando archivo: {e}")
                messages.error(request, traceback.format_exc())
            else:
                messages.error(request, "Error procesando archivo. Revisa los logs para más detalles.")
            return redirect("dashboard")

    q = request.GET.get("q")
    if q:
        claims_qs = claims_qs.filter(Q(col1__icontains=q) | Q(col2__icontains=q))

    total = claims_qs.aggregate(total=Sum("col4"))["total"] or Decimal("0.00")
    return render(request, "core/dashboard.html", {"claims": claims_qs, "total": total})
