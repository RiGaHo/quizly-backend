"""Application routes; expose administration only through authorized routing."""

from django.contrib import admin
from django.urls import path

from accounts.views import LoginView, LogoutView, RefreshView, RegisterView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/register/", RegisterView.as_view()),
    path("api/login/", LoginView.as_view()),
    path("api/logout/", LogoutView.as_view()),
    path("api/token/refresh/", RefreshView.as_view()),
]
