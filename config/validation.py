"""Fail closed on unsafe deployment configuration before serving requests."""

from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


def validate_origins(origins, debug):
    """Accept exact HTTP(S) origins, requiring HTTPS outside local debug mode."""
    for origin in origins:
        try:
            parsed = urlsplit(origin)
            valid = valid_origin(parsed) and (debug or parsed.scheme == "https")
        except ValueError:
            valid = False
        if not valid:
            raise ImproperlyConfigured(
                "FRONTEND_ORIGINS must contain exact trusted origins."
            )


def valid_origin(parsed):
    """Reject wildcards, userinfo, paths and invalid ports from origin settings."""
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and "*" not in parsed.netloc
        and not parsed.username
        and not parsed.password
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
        and (parsed.port is None or 0 < parsed.port < 65536)
    )
