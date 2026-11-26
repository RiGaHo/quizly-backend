"""Exercise cookie contracts, revocation and browser request boundaries."""

from datetime import timedelta

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from accounts_app.models import LoginSession, User

ORIGIN = "http://testserver"
REGISTRATION = {
    "username": "alice",
    "email": "ALICE@Example.com",
    "password": "Secret1",
    "confirmed_password": "Secret1",
}


INVALID_REGISTRATIONS = [
    {"username": "alice"},
    {"email": "ALICE@example.com"},
    {"email": "invalid"},
    {"confirmed_password": "different"},
    {"password": "weak"},
    {"username": "a"},
]


class AuthenticationTests(APITestCase):
    """Use real signed JWTs and database state, never force-authenticated requests."""

    def setUp(self):
        """Supply the browser's origin and a real password-hashed account."""
        self.client.defaults["HTTP_ORIGIN"] = ORIGIN
        self.user = User.objects.create_user("alice", "alice@example.com", "Secret1")

    def login(self):
        """Perform the actual login endpoint and retain cookies in the client."""
        return self.client.post(
            "/api/login/",
            {"username": "alice", "password": "Secret1"},
            format="json",
        )

    def test_registration_contract(self):
        """Create a user and return only the documented confirmation."""
        data = REGISTRATION | {"username": "bob", "email": "BOB@Example.com"}
        response = self.client.post("/api/register/", data, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"detail": "User created successfully!"})
        self.assertTrue(User.objects.get(username="bob").check_password("Secret1"))
        self.assertEqual(User.objects.get(username="bob").email, "bob@example.com")

    def test_invalid_registration_fields(self):
        """Reject missing, duplicate, mismatched and invalid registration data."""
        for change in INVALID_REGISTRATIONS:
            data = (
                REGISTRATION | {"username": "bob", "email": "bob@example.com"} | change
            )
            with self.subTest(change=change):
                self.assertEqual(
                    self.client.post("/api/register/", data, format="json").status_code,
                    400,
                )
        self.assertEqual(User.objects.count(), 1)

    def test_missing_registration_fields(self):
        """Each documented registration field is required."""
        for field in REGISTRATION:
            data = {key: value for key, value in REGISTRATION.items() if key != field}
            with self.subTest(field=field):
                self.assertEqual(
                    self.client.post("/api/register/", data, format="json").status_code,
                    400,
                )

    def test_login_contract(self):
        """Expose the documented user object and no token strings in JSON."""
        response = self.login()
        self.assertEqual(response.status_code, 200)
        identity = {
            "id": self.user.pk,
            "username": "alice",
            "email": "alice@example.com",
        }
        expected = {"detail": "Login successfully!", "user": identity}
        self.assertEqual(response.json(), expected)
        self.assertEqual(set(response.cookies), {"access_token", "refresh_token"})

    def test_cookie_scope(self):
        """Use HttpOnly, host-only, scoped, expiring cookies for local HTTP."""
        response = self.login()
        for cookie in response.cookies.values():
            self.assertTrue(cookie["httponly"])
            self.assertFalse(cookie["secure"])
            self.assertEqual(cookie["samesite"], "Lax")
            self.assertEqual(cookie["path"], "/api/")
            self.assertEqual(cookie["domain"], "")
            self.assertGreater(cookie["max-age"], 0)

    @override_settings(COOKIE_SECURE=True)
    def test_production_cookie_security(self):
        """Secure flags apply to both creation and deletion in production."""
        response = self.login()
        self.assertTrue(all(cookie["secure"] for cookie in response.cookies.values()))
        response = self.client.post("/api/logout/")
        self.assertTrue(all(cookie["secure"] for cookie in response.cookies.values()))

    def test_login_failure_is_generic(self):
        """Existing and nonexistent usernames receive the same 401 message."""
        responses = []
        for username in ("alice", "nobody"):
            data = {"username": username, "password": "wrong"}
            responses.append(self.client.post("/api/login/", data, format="json"))
        self.assertEqual([response.status_code for response in responses], [401, 401])
        self.assertEqual(responses[0].json(), responses[1].json())

    def test_missing_login_fields_are_generic(self):
        """Missing or empty credentials receive the same general login failure."""
        for data in ({}, {"username": "alice"}, {"username": "", "password": ""}):
            response = self.client.post("/api/login/", data, format="json")
            self.assertEqual(response.status_code, 401)
            self.assertEqual(
                response.json(), {"detail": "Invalid username or password."}
            )

    def test_refresh_without_body_or_content_type(self):
        """Match the original frontend's minimal refresh request."""
        self.login()
        response = self.client.generic("POST", "/api/token/refresh/", content_type="")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"detail": "Token refreshed"})
        self.assertEqual(set(response.cookies), {"access_token"})

    def test_refresh_ignores_expired_access(self):
        """A valid refresh cookie succeeds after access expiry."""
        self.login()
        access = AccessToken(self.client.cookies["access_token"].value)
        access.set_exp(from_time=timezone.now() - timedelta(hours=1))
        self.client.cookies["access_token"] = str(access)
        self.assertEqual(self.client.post("/api/token/refresh/").status_code, 200)

    def test_refresh_rejects_missing_and_malformed(self):
        """Missing or untrusted refresh cookies never produce access cookies."""
        for value in ("", "invalid", "a.b.c"):
            self.client.cookies["refresh_token"] = value
            response = self.client.post("/api/token/refresh/")
            self.assertEqual(response.status_code, 401)
            self.assertNotIn("access_token", response.cookies)

    def test_expired_refresh(self):
        """Cryptographically valid but expired refresh cookies fail."""
        self.login()
        token = RefreshToken(self.client.cookies["refresh_token"].value)
        token.set_exp(from_time=timezone.now() - timedelta(days=8))
        self.client.cookies["refresh_token"] = str(token)
        self.assertEqual(self.client.post("/api/token/refresh/").status_code, 401)

    def test_logout_revokes_original_and_refreshed_tokens(self):
        """Replay of every token from the logged-out session fails."""
        self.login()
        original = self.client.cookies["access_token"].value
        refresh = self.client.cookies["refresh_token"].value
        self.client.post("/api/token/refresh/")
        renewed = self.client.cookies["access_token"].value
        self.assertEqual(self.client.post("/api/logout/").status_code, 200)
        for value in (original, renewed):
            self.client.cookies["access_token"] = value
            self.assertEqual(self.client.post("/api/logout/").status_code, 401)
        self.client.cookies["refresh_token"] = refresh
        self.assertEqual(self.client.post("/api/token/refresh/").status_code, 401)

    def test_logout_cookie_deletion(self):
        """Remove both cookies with the same path and SameSite scope."""
        self.login()
        response = self.client.post("/api/logout/")
        for name in ("access_token", "refresh_token"):
            self.assertEqual(response.cookies[name]["max-age"], 0)
            self.assertEqual(response.cookies[name]["path"], "/api/")
            self.assertEqual(response.cookies[name].value, "")
        self.assertIsNotNone(LoginSession.objects.get().revoked_at)

    def test_other_login_remains_valid(self):
        """Logout affects the authenticated login, not another device's session."""
        self.login()
        earlier = self.client.cookies["access_token"].value
        self.login()
        self.client.post("/api/logout/")
        self.client.cookies["access_token"] = earlier
        self.assertEqual(self.client.post("/api/logout/").status_code, 200)

    def test_inactive_user_cannot_refresh(self):
        """Deactivation also invalidates existing session use."""
        self.login()
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.client.post("/api/token/refresh/").status_code, 401)

    def test_missing_access_is_401(self):
        """A protected operation requires a valid access cookie."""
        self.assertEqual(self.client.post("/api/logout/").status_code, 401)

    def test_authorization_header_does_not_authenticate(self):
        """JWT authentication uses only the documented cookies."""
        self.login()
        token = self.client.cookies["access_token"].value
        self.client.cookies.clear()
        response = self.client.post(
            "/api/logout/", HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        self.assertEqual(response.status_code, 401)


class OriginTests(APITestCase):
    """Test middleware without any force-authentication or CSRF bypass."""

    def test_untrusted_origins(self):
        """Reject null, attacker origins and deceptive suffixes before dispatch."""
        for origin in (
            "null",
            "https://attacker.example",
            ORIGIN + ".evil",
            ORIGIN + "/",
        ):
            for path in ("login", "logout", "register", "token/refresh"):
                response = self.client.post(f"/api/{path}/", HTTP_ORIGIN=origin)
                self.assertEqual(response.status_code, 403)

    def test_missing_origin_and_referer(self):
        """API clients must deliberately supply provenance, just like browsers."""
        self.assertEqual(self.client.post("/api/token/refresh/").status_code, 403)

    def test_same_origin_referer_fallback(self):
        """A same-origin Referer can replace an absent Origin, never a bad one."""
        response = self.client.post(
            "/api/token/refresh/", HTTP_REFERER=ORIGIN + "/page"
        )
        self.assertEqual(response.status_code, 401)
        response = self.client.post(
            "/api/token/refresh/",
            HTTP_REFERER=ORIGIN + "/page",
            HTTP_ORIGIN="null",
        )
        self.assertEqual(response.status_code, 403)

    def test_form_payload_rejected(self):
        """Even trusted origins cannot submit state-changing form payloads."""
        response = self.client.post(
            "/api/login/", {"username": "a"}, HTTP_ORIGIN=ORIGIN
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(CORS_ALLOWED_ORIGINS=["http://127.0.0.1:5500"])
    def test_original_frontend_origin_and_cors(self):
        """An explicitly permitted frontend can send the headerless refresh."""
        origin = "http://127.0.0.1:5500"
        response = self.client.post("/api/token/refresh/", HTTP_ORIGIN=origin)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["Access-Control-Allow-Origin"], origin)
        self.assertEqual(response["Access-Control-Allow-Credentials"], "true")

    def test_untrusted_origin_has_no_cors_permission(self):
        """Credentialed CORS never reflects arbitrary origins."""
        response = self.client.get("/api/login/", HTTP_ORIGIN="https://evil.example")
        self.assertNotIn("Access-Control-Allow-Origin", response)
