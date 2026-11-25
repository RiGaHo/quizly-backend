"""Check fail-closed settings in independent interpreter processes."""

import os
import subprocess
import sys

from django.test import SimpleTestCase

UNSAFE_ORIGINS = (
    "*",
    "null",
    "https://example.com/path",
    "https://user@example.com",
    "http://example.com",
)


class ConfigurationTests(SimpleTestCase):
    """Validate startup boundaries without importing production settings in tests."""

    def run_settings(self, **values):
        """Import settings in an isolated process with explicit environment values."""
        environment = {
            k: v for k, v in os.environ.items() if not k.startswith("DJANGO_")
        }
        environment["DJANGO_READ_DOTENV"] = "false"
        environment.update(values)
        return subprocess.run(
            [sys.executable, "-c", "import config.settings"],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_production_requires_key(self):
        """Missing production credentials prevent application startup."""
        result = self.run_settings()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY", result.stderr)

    def test_production_requires_hosts(self):
        """A long key alone does not implicitly trust every host."""
        result = self.run_settings(DJANGO_SECRET_KEY="a" * 64)
        self.assertNotEqual(result.returncode, 0)

    def test_wildcard_host_is_rejected(self):
        """Explicit wildcard configuration is rejected even in development."""
        result = self.run_settings(DJANGO_SECRET_KEY="a" * 64, DJANGO_ALLOWED_HOSTS="*")
        self.assertNotEqual(result.returncode, 0)

    def test_configured_production_starts_without_gemini(self):
        """Independent features need no AI credentials at startup."""
        result = self.run_settings(
            DJANGO_SECRET_KEY="a" * 64,
            DJANGO_ALLOWED_HOSTS="quizly.example.com",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unsafe_origins_rejected_at_startup(self):
        """Do not accidentally trust wildcard, path, userinfo or insecure origins."""
        for origin in UNSAFE_ORIGINS:
            result = self.run_settings(
                DJANGO_SECRET_KEY="a" * 64,
                DJANGO_ALLOWED_HOSTS="example.com",
                FRONTEND_ORIGINS=origin,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("FRONTEND_ORIGINS", result.stderr)

    def test_local_http_origin_is_explicitly_supported(self):
        """Debug mode supports the unmodified local frontend's HTTP origin."""
        result = self.run_settings(
            DJANGO_SECRET_KEY="local-test-only",
            DJANGO_DEBUG="true",
            DJANGO_ALLOWED_HOSTS="127.0.0.1",
            FRONTEND_ORIGINS="http://127.0.0.1:5500",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
