# core/views.py
import logging
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum

import pandas as pd

from .models import Claim

logger = logging.getLogger(__name__)

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

@login_required
def dashboard(request):
    # Datos por defecto para renderizar
    claims_qs = Claim.objects.all()

    if request.method == "POST":
        uploaded = request.FILES.get("file")
        if not uploaded:
            messages.error(request, "No se seleccionó ningún archivo.")
            return redirect("dashboard")

        filename = uploaded.name.lower()
        try:
            # Leer archivo
            if filename.endswith(".csv"):
                df = pd.read_csv(uploaded, dtype=str)  # leer como str para normalizar
            elif filename.endswith((".xls", ".xlsx")):
                # Asegúrate de tener openpyxl instalado: pip install openpyxl
                df = pd.read_excel(uploaded, engine="openpyxl", dtype=str)
            else:
                messages.error(request, "Formato no soportado. Usa .csv, .xls o .xlsx.")
                return redirect("dashboard")

            # Limitar tamaño para evitar OOM y seleccionar primeras 22 columnas
            df = df.iloc[:6000, :22]

            # Quitar espacios en columnas de texto
            for col in df.select_dtypes(include=["object"]).columns:
                df[col] = df[col].astype(str).str.strip()

            # --- Conversión segura de la columna que mapea a col4 ---
            # Ajusta col4_index si la columna numérica está en otra posición
            col4_index = 4
            if df.shape[1] <= col4_index:
                messages.error(request, "El archivo no contiene la columna esperada para col4.")
                return redirect("dashboard")

            # Intentar convertir a numérico; valores inválidos -> NaN
            df.iloc[:, col4_index] = pd.to_numeric(df.iloc[:, col4_index].str.replace(",", "."), errors="coerce")

            # Rellenar NaN con 0 (o cambiar a dropna() si prefieres eliminar filas)
            df.iloc[:, col4_index] = df.iloc[:, col4_index].fillna(0)

            # Construir lista de instancias Claim con conversión a Decimal segura
            claims_to_create = []
            for _, row in df.iterrows():
                raw_val = row.iloc[col4_index]
                try:
                    col4_val = Decimal(str(raw_val))
                except (InvalidOperation, TypeError, ValueError):
                    col4_val = Decimal("0.00")

                claims_to_create.append(Claim(
                    col1 = row.iloc[0] if df.shape[1] > 0 else None,
                    col2 = row.iloc[1] if df.shape[1] > 1 else None,
                    col3 = row.iloc[2] if df.shape[1] > 2 else None,
                    col4 = col4_val,
                    col5 = row.iloc[5] if df.shape[1] > 5 else None,
                    col6 = row.iloc[6] if df.shape[1] > 6 else None,
                    to_delete = False
                ))

            # Insertar en la BD por chunks dentro de una transacción
            chunk_size = 1000
            with transaction.atomic():
                for i in range(0, len(claims_to_create), chunk_size):
                    Claim.objects.bulk_create(claims_to_create[i:i+chunk_size])

            messages.success(request, f"Archivo procesado correctamente. {len(claims_to_create)} filas importadas.")
            return redirect("dashboard")

        except Exception as e:
            logger.exception("Error procesando archivo subido")
            messages.error(request, "Ocurrió un error al procesar el archivo. Revisa el formato y el contenido.")
            return redirect("dashboard")

    # GET: aplicar filtros y mostrar
    q = request.GET.get("q")
    if q:
        claims_qs = claims_qs.filter(col1__icontains=q) | claims_qs.filter(col2__icontains=q)

    total = claims_qs.aggregate(total=Sum("col4"))["total"] or 0
    return render(request, "core/dashboard.html", {"claims": claims_qs, "total": total})
