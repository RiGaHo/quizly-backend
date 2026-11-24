"""Check fail-closed settings in independent interpreter processes."""

import os
import subprocess
import sys

from django.test import SimpleTestCase


class ConfigurationTests(SimpleTestCase):
    """Validate startup boundaries without importing production settings in tests."""

    def run_settings(self, **values):
        """Import settings in an isolated process with explicit environment values."""
        environment = {
            k: v for k, v in os.environ.items() if not k.startswith("DJANGO_")
        }
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
