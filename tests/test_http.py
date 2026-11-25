"""Exercise browser-compatible cookies through a real local HTTP socket."""

import json
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from django.test import LiveServerTestCase

from tests.test_auth import REGISTRATION


class HttpSmokeTests(LiveServerTestCase):
    """Verify registration and session lifecycle beyond the in-process client."""

    def setUp(self):
        """Use an ordinary HTTP cookie jar to retain server-issued cookies."""
        self.cookies = CookieJar()
        self.browser = build_opener(HTTPCookieProcessor(self.cookies))

    def request(self, path, method="GET", data=None):
        """Send the same Origin and optional JSON body as the original frontend."""
        headers = {"Origin": self.live_server_url}
        if data is not None:
            headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode() if data is not None else None
        request = Request(self.live_server_url + path, body, headers, method=method)
        try:
            response = self.browser.open(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_cookie_session_lifecycle(self):
        """Register, login, list, refresh without body, logout and reject reuse."""
        self.assertEqual(self.request("/api/register/", "POST", REGISTRATION)[0], 201)
        credentials = {"username": "alice", "password": "Secret1"}
        self.assertEqual(self.request("/api/login/", "POST", credentials)[0], 200)
        self.assertEqual(
            {cookie.name for cookie in self.cookies}, {"access_token", "refresh_token"}
        )
        self.assertEqual(self.request("/api/quizzes/"), (200, []))
        self.assertEqual(self.request("/api/token/refresh/", "POST")[0], 200)
        self.assertEqual(self.request("/api/logout/", "POST")[0], 200)
        self.assertEqual(list(self.cookies), [])
        self.assertEqual(self.request("/api/quizzes/")[0], 401)
        self.assertEqual(self.request("/api/token/refresh/", "POST")[0], 401)
