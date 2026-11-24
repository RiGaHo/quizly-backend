"""Application routes; expose administration only through authorized routing."""

from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from accounts.views import LoginView, LogoutView, RefreshView, RegisterView
from quizzes.views import QuizViewSet

router = SimpleRouter()
router.register("quizzes", QuizViewSet, basename="quiz")

urlpatterns = [
    path("api/", include(router.urls)),
    path("admin/", admin.site.urls),
    path("api/register/", RegisterView.as_view()),
    path("api/login/", LoginView.as_view()),
    path("api/logout/", LogoutView.as_view()),
    path("api/token/refresh/", RefreshView.as_view()),
]
