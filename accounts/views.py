"""Documented authentication operations; JWTs are delivered only as cookies."""

from rest_framework.exceptions import AuthenticationFailed
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .cookies import clear_token_cookies, set_token_cookie
from .serializers import LoginSerializer, RegisterSerializer
from .tokens import issue_tokens, refreshed_access, revoke_session


class RegisterView(GenericAPIView):
    """Register an account without establishing a login session."""

    serializer_class = RegisterSerializer
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request):
        """Validate and save a user, returning the documented success message."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "User created successfully!"}, status=201)


class LoginView(GenericAPIView):
    """Establish an independent revocable login session."""

    serializer_class = LoginSerializer
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request):
        """Set both cookies and expose only public account identity in JSON."""
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            raise AuthenticationFailed("Invalid username or password.")
        user = serializer.validated_data["user"]
        access, refresh = issue_tokens(user)
        identity = {"id": user.pk, "username": user.username, "email": user.email}
        response = Response({"detail": "Login successfully!", "user": identity})
        set_token_cookie(response, "access_token", access)
        set_token_cookie(response, "refresh_token", refresh)
        return response

    def get_authenticate_header(self, request):
        """Preserve documented 401 on login failure despite anonymous access."""
        return "Cookie"


class RefreshView(GenericAPIView):
    """Accept a refresh cookie even when the access cookie has expired."""

    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request):
        """Renew the access cookie without a body or Authorization header."""
        access = refreshed_access(request)
        response = Response({"detail": "Token refreshed"})
        set_token_cookie(response, "access_token", access)
        return response

    def get_authenticate_header(self, request):
        """Return the documented 401 for missing or invalid refresh cookies."""
        return "Cookie"


class LogoutView(GenericAPIView):
    """Revoke all tokens belonging to this login, preserving other logins."""

    def post(self, request):
        """Persist revocation before removing the matching browser cookies."""
        revoke_session(request.auth)
        response = Response(
            {"detail": "Log-Out successfully! All session tokens invalidated."}
        )
        clear_token_cookies(response)
        return response
