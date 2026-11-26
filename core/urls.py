"""Include app-owned API routes and the local administration interface."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("accounts_app.api.urls")),
    path("api/", include("quizzes_app.api.urls")),
]
