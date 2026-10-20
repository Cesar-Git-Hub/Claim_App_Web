from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path("login/", LoginView.as_view(template_name="core/login.html", redirect_authenticated_user=True), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),  # POST only
    path("registro/", views.signup, name="signup"),
    path("", views.dashboard, name="dashboard"),
    path("upload/", views.upload, name="upload"),
    path("action/", views.action, name="action"),
]
