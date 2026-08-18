from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import models
from django.urls import path
from . import views
from .models import Claim
import pandas as pd

def user_login(request):
    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]
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
    if request.method == "POST":
        file = request.FILES["file"]
        import pandas as pd
        if file.name.endswith(".csv"):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)

        df = df.iloc[:6000, :22]
        for col in df.select_dtypes(include=["object"]).columns:
            df[col] = df[col].str.strip()

        claims = []
        for _, row in df.iterrows():
            claims.append(Claim(
                col1=row[0], col2=row[1], col3=row[2],
                col4=row[4], col5=row[5], col6=row[6],
                to_delete=False
            ))
        Claim.objects.bulk_create(claims)

        return redirect("dashboard")

    # si es GET, mostrar datos
    claims = Claim.objects.all()
    q = request.GET.get("q")
    if q:
        claims = claims.filter(col1__icontains=q) | claims.filter(col2__icontains=q)
    total = claims.aggregate(total=models.Sum("col4"))["total"] or 0
    return render(request, "core/dashboard.html", {"claims": claims, "total": total})

