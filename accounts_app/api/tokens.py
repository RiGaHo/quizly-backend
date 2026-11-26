"""Issue and revoke JWTs using a shared persistent login-session identity."""

from datetime import UTC, datetime
from uuid import UUID

from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from ..models import LoginSession


def issue_tokens(user):
    """Create one session and bind both signed token types to it."""
    refresh = RefreshToken.for_user(user)
    session = LoginSession.objects.create(
        user=user,
        expires_at=datetime.fromtimestamp(refresh["exp"], tz=UTC),
    )
    refresh["sid"] = str(session.pk)
    return refresh.access_token, refresh


def active_session(token):
    """Reject unknown, expired, revoked or mismatched login identities."""
    try:
        session_id = UUID(str(token["sid"]))
        return LoginSession.objects.select_related("user").get(
            pk=session_id,
            user_id=token["user_id"],
            user__is_active=True,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
    except (KeyError, ValueError, TypeError, LoginSession.DoesNotExist) as error:
        raise AuthenticationFailed("Invalid authentication session.") from error


def validated_token(value, token_type=AccessToken):
    """Validate JWT signature, expiry, type and persistent session state."""
    if not value:
        raise AuthenticationFailed("Authentication cookie required.")
    try:
        token = token_type(value)
    except TokenError as error:
        raise AuthenticationFailed("Invalid authentication cookie.") from error
    return token, active_session(token)


def refreshed_access(request):
    """Refresh without requiring a valid access cookie or rotating the session."""
    token, _session = validated_token(
        request.COOKIES.get("refresh_token"), RefreshToken
    )
    return token.access_token


def revoke_session(session):
    """Monotonically revoke a session; refresh never updates or restores it."""
    LoginSession.objects.filter(pk=session.pk, revoked_at__isnull=True).update(
        revoked_at=timezone.now(),
    )
