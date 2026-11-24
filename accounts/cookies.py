"""Consistent host-bound token cookie creation and removal."""

import time

from django.conf import settings


def set_token_cookie(response, name, token):
    """Bound the browser cookie lifetime to the signed token's expiry."""
    response.set_cookie(
        name,
        str(token),
        max_age=max(0, int(token["exp"] - time.time())),
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/api/",
    )


def clear_token_cookies(response):
    """Expire both cookies with matching scope and security attributes."""
    for name in ("access_token", "refresh_token"):
        response.set_cookie(
            name,
            "",
            max_age=0,
            expires="Thu, 01 Jan 1970 00:00:00 GMT",
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            path="/api/",
        )
