"""Adversarial session and refresh/logout interleavings."""

from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from accounts_app.api.tokens import active_session, revoke_session
from accounts_app.models import LoginSession, User


class SessionTests(APITestCase):
    """Keep actual token signatures and DB checks active in race scenarios."""

    def setUp(self):
        """Create a logged-in browser client for each isolated test."""
        self.client.defaults["HTTP_ORIGIN"] = "http://testserver"
        User.objects.create_user("alice", "alice@example.com", "Secret1")
        self.client.post(
            "/api/login/",
            {"username": "alice", "password": "Secret1"},
            format="json",
        )

    def revoke_after_validation(self, token):
        """Simulate logout committing after refresh reads the active session."""
        session = active_session(token)
        revoke_session(session)
        return session

    def test_refresh_cannot_resurrect_concurrently_revoked_session(self):
        """A token issued after an overlapping logout remains unusable."""
        with patch(
            "accounts_app.api.tokens.active_session",
            side_effect=self.revoke_after_validation,
        ):
            response = self.client.post("/api/token/refresh/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(LoginSession.objects.get().revoked_at)
        self.assertEqual(self.client.post("/api/logout/").status_code, 401)
        self.assertEqual(self.client.post("/api/token/refresh/").status_code, 401)

    def test_refresh_never_extends_session_expiry(self):
        """Repeated renewal leaves the original login deadline unchanged."""
        deadline = LoginSession.objects.get().expires_at
        for _ in range(3):
            self.assertEqual(self.client.post("/api/token/refresh/").status_code, 200)
        self.assertEqual(LoginSession.objects.get().expires_at, deadline)

    def test_expired_session_rejects_signed_tokens(self):
        """The server-side deadline applies even to otherwise unexpired JWTs."""
        LoginSession.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.post("/api/logout/").status_code, 401)
        self.assertEqual(self.client.post("/api/token/refresh/").status_code, 401)

    def test_unknown_or_malformed_session(self):
        """Signed tokens without a valid session identifier are rejected."""
        token = AccessToken(self.client.cookies["access_token"].value)
        for session_id in ("bad", "00000000-0000-0000-0000-000000000000", None):
            token["sid"] = session_id
            self.client.cookies["access_token"] = str(token)
            self.assertEqual(self.client.post("/api/logout/").status_code, 401)

    def test_access_rejects_wrong_token_type(self):
        """A refresh JWT cannot authenticate a protected operation."""
        self.client.cookies["access_token"] = self.client.cookies["refresh_token"].value
        self.assertEqual(self.client.post("/api/logout/").status_code, 401)

    def test_refresh_rejects_wrong_token_type(self):
        """An access JWT cannot mint another access JWT."""
        self.client.cookies["refresh_token"] = self.client.cookies["access_token"].value
        self.assertEqual(self.client.post("/api/token/refresh/").status_code, 401)

    def test_expired_access_cannot_logout(self):
        """Expired access receives 401 so clients can refresh first."""
        token = AccessToken(self.client.cookies["access_token"].value)
        token.set_exp(from_time=timezone.now() - timedelta(hours=1))
        self.client.cookies["access_token"] = str(token)
        self.assertEqual(self.client.post("/api/logout/").status_code, 401)

    def test_mismatched_user_is_rejected(self):
        """Session identity must belong to the token's authenticated user."""
        token = RefreshToken(self.client.cookies["refresh_token"].value)
        token["user_id"] = 999
        self.client.cookies["refresh_token"] = str(token)
        self.assertEqual(self.client.post("/api/token/refresh/").status_code, 401)
