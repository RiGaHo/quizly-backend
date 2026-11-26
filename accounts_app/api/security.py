"""Browser request provenance checks for the cookie API without CSRF headers."""

from urllib.parse import urlsplit

from django.conf import settings
from django.http import JsonResponse

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def referer_origin(value):
    """Extract a strict HTTP origin from a referer without trusting userinfo."""
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
        ):
            return None
        return f"{parsed.scheme}://{parsed.netloc}"
    except ValueError:
        return None


def trusted_request(request):
    """Require an exact trusted Origin, falling back to Referer only if absent."""
    origin = request.headers.get("Origin")
    if origin is None:
        origin = referer_origin(request.headers.get("Referer", ""))
    own_origin = f"{request.scheme}://{request.get_host()}"
    return origin in {own_origin, *settings.CORS_ALLOWED_ORIGINS}


class CookieOriginMiddleware:
    """Protect all unsafe API operations, including unauthenticated login."""

    def __init__(self, get_response):
        """Keep Django's middleware continuation."""
        self.get_response = get_response

    def __call__(self, request):
        """Reject untrusted browser provenance and form payloads before dispatch."""
        if request.path.startswith("/api/") and request.method not in SAFE_METHODS:
            if not trusted_request(request):
                return JsonResponse({"detail": "Untrusted request origin."}, status=403)
            if request.body and request.content_type != "application/json":
                return JsonResponse(
                    {"detail": "JSON requests are required."}, status=400
                )
        response = self.get_response(request)
        if request.path.startswith("/api/"):
            response["Cache-Control"] = "no-store"
        return response
