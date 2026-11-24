"""Quiz management through DRF's standard list and object operations."""

from rest_framework import mixins
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from .models import Quiz
from .permissions import IsQuizOwner
from .serializers import QuizSerializer, QuizUpdateSerializer


class QuizViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    """Scope lists by owner, but resolve detail objects before ownership checks."""

    permission_classes = (IsAuthenticated, IsQuizOwner)
    http_method_names = ("get", "patch", "delete", "head", "options")
    pagination_class = None
    lookup_value_regex = "[0-9]+"

    def get_queryset(self):
        """Keep foreign detail objects discoverable for the required 403 response."""
        queryset = Quiz.objects.prefetch_related("questions")
        return (
            queryset.filter(owner=self.request.user)
            if self.action == "list"
            else queryset
        )

    def get_serializer_class(self):
        """Use restricted update input while retaining the documented response."""
        return (
            QuizUpdateSerializer if self.action == "partial_update" else QuizSerializer
        )
