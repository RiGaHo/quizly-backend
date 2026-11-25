"""HTTPS-only media transport with host allowlisting and pinned public addresses."""

import http.client
import ipaddress
import socket
import urllib.request
from urllib.parse import urlsplit

from yt_dlp.networking import _urllib

from .errors import GenerationError


def allowed_host(host):
    """Permit only YouTube metadata and Google's video delivery hostnames."""
    return host == "youtubei.googleapis.com" or any(
        host == domain or host.endswith("." + domain)
        for domain in ("youtube.com", "googlevideo.com")
    )


def check_destination(url):
    """Validate every request, including redirected requests, before connection."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password:
        raise GenerationError("Unsupported media destination.")
    if not parsed.hostname or not allowed_host(parsed.hostname):
        raise GenerationError("Unsupported media destination.")
    if parsed.port not in (None, 443):
        raise GenerationError("Unsupported media port.")


def public_addresses(host, port):
    """Reject mixed public/private DNS answers before opening any socket."""
    if not allowed_host(host) or port != 443:
        raise GenerationError("Unsupported media destination.")
    records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(record[4][0] for record in records))
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise GenerationError("Nonpublic media destination.")
    return addresses


def public_connection(address, timeout=None, source_address=None):
    """Connect to a validated numeric address, preventing a second hostname lookup."""
    host, port = address
    for ip in public_addresses(host, port):
        try:
            return socket.create_connection((ip, port), timeout, source_address)
        except OSError as error:
            last_error = error
    raise last_error


class PublicHTTPSConnection(http.client.HTTPSConnection):
    """Keep standard TLS verification/SNI while pinning the underlying connection."""

    def __init__(self, *args, **kwargs):
        """Replace only the socket factory on this individual connection."""
        super().__init__(*args, **kwargs)
        self._create_connection = public_connection


class GuardedHTTPHandler(_urllib.HTTPHandler):
    """Reuse yt-dlp response handling with a strict connection boundary."""

    def https_open(self, request):
        """Check redirected destinations and use the pinned TLS connection."""
        check_destination(request.full_url)
        return self.do_open(PublicHTTPSConnection, request, context=self._context)

    def http_open(self, request):
        """Never permit downgrade redirects to unencrypted HTTP."""
        raise GenerationError("HTTPS is required for media requests.")


class GuardedUrllibRH(_urllib.UrllibRH):
    """Install no proxy, file, data, FTP or alternate network handlers."""

    def _create_instance(self, proxies, cookiejar, legacy_ssl_support=None):
        """Build a single guarded opener; redirects return through its TLS handler."""
        opener = urllib.request.OpenerDirector()
        for handler in guarded_handlers(self._make_sslcontext(), cookiejar):
            opener.add_handler(handler)
        opener.addheaders = []
        return opener


def guarded_handlers(context, cookiejar):
    """Enumerate the supported protocols explicitly, excluding proxy/file handlers."""
    return [
        GuardedHTTPHandler(context=context),
        _urllib.HTTPCookieProcessor(cookiejar),
        _urllib.UnknownHandler(),
        _urllib.HTTPDefaultErrorHandler(),
        _urllib.HTTPErrorProcessor(),
        _urllib.RedirectHandler(),
    ]
