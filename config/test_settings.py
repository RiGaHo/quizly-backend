"""Isolated, nonsecret test configuration; never use for serving the application."""

import os

os.environ["DJANGO_SECRET_KEY"] = "test-only-not-a-production-secret-" * 3
os.environ["DJANGO_DEBUG"] = "true"
os.environ["DJANGO_ALLOWED_HOSTS"] = "testserver,127.0.0.1,localhost"

from .settings import *  # noqa: E402,F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
