"""Cookie-only JWT authentication with per-request session revocation checks."""

from rest_framework.authentication import BaseAuthentication

from .tokens import validated_token


class CookieAuthentication(BaseAuthentication):
    """Authenticate signed access cookies and their still-active login session."""

    def authenticate(self, request):
        """Ignore Authorization headers and read only the HttpOnly access cookie."""
        value = request.COOKIES.get("access_token")
        if not value:
            return None
        _token, session = validated_token(value)
        return session.user, session

    def authenticate_header(self, request):
        """Return a challenge so unauthenticated protected requests yield 401."""
        return "Cookie"
