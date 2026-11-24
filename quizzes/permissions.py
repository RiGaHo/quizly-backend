"""Object ownership checks preserving the documented 403/404 distinction."""

from rest_framework.permissions import BasePermission


class IsQuizOwner(BasePermission):
    """Deny access to existing foreign objects without exposing their contents."""

    def has_object_permission(self, request, view, obj):
        """Require the authenticated user to own the selected quiz."""
        return obj.owner_id == request.user.pk
