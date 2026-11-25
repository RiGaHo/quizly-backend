"""Network-boundary and download-policy tests without external video access."""

import socket
import tempfile
import urllib.request
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from generation.download import (
    DownloadBounds,
    MediaDownloader,
    checked_download,
    download_options,
)
from generation.errors import GenerationError
from generation.network import (
    GuardedHTTPHandler,
    GuardedUrllibRH,
    check_destination,
    public_connection,
)


def dns_record(ip):
    """Build one deterministic IPv4 resolver result."""
    return (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443))


class NetworkTests(SimpleTestCase):
    """Exercise actual transport selection and the connect-time address boundary."""

    def test_forbidden_destinations(self):
        """Reject downgrades, userinfo, IP literals, ports and host suffix tricks."""
        urls = [
            "http://youtube.com/",
            "https://youtube.com.evil.test/",
            "https://127.0.0.1/",
            "https://user@youtube.com/",
            "https://youtube.com:444/",
            "file:///etc/passwd",
        ]
        for url in urls:
            with self.subTest(url=url), self.assertRaises(GenerationError):
                check_destination(url)

    def test_mixed_dns_answers_are_rejected(self):
        """A public record cannot conceal a second private target."""
        records = [dns_record("8.8.8.8"), dns_record("127.0.0.1")]
        with patch("generation.network.socket.getaddrinfo", return_value=records):
            with patch("generation.network.socket.create_connection") as connect:
                with self.assertRaises(GenerationError):
                    public_connection(("www.youtube.com", 443), 15)
                connect.assert_not_called()

    def test_connection_pins_checked_ip(self):
        """The connection factory never resolves the original hostname a second time."""
        with patch(
            "generation.network.socket.getaddrinfo",
            return_value=[dns_record("8.8.8.8")],
        ):
            with patch("generation.network.socket.create_connection") as connect:
                public_connection(("www.youtube.com", 443), 15)
        connect.assert_called_once_with(("8.8.8.8", 443), 15, None)

    def test_redirect_target_is_checked_before_socket(self):
        """A redirected HTTPS request cannot select an external host."""
        handler = GuardedHTTPHandler()
        with patch.object(handler, "do_open") as connect:
            with self.assertRaises(GenerationError):
                handler.https_open(urllib.request.Request("https://evil.example/"))
            connect.assert_not_called()

    def test_actual_downloader_uses_only_guarded_transport(self):
        """Construct real yt-dlp and inspect its selected request director."""
        options = download_options("/tmp", DownloadBounds(900, 1000, 120))
        with MediaDownloader(options) as downloader:
            handlers = list(downloader._request_director.handlers.values())
            self.assertEqual(len(handlers), 1)
            self.assertIsInstance(handlers[0], GuardedUrllibRH)


class DownloadPolicyTests(SimpleTestCase):
    """Check policy against metadata, progress reports and completed files."""

    def test_duration_and_live_rejection(self):
        """Reject unavailable duration, oversized videos and live/upcoming content."""
        bounds = DownloadBounds(900, 1000, 120)
        cases = [
            {},
            {"duration": 901},
            {"duration": 10, "is_live": True},
            {"duration": 10, "live_status": "is_upcoming"},
            {"duration": 10, "filesize": 1001},
        ]
        for info in cases:
            self.assertIsNotNone(bounds.match_filter(info))
        self.assertIsNone(bounds.match_filter({"duration": 300}))
        self.assertIsNone(bounds.match_filter({}, incomplete=True))

    def test_transfer_limits(self):
        """Progress callbacks enforce both unknown-length byte and time limits."""
        bounds = DownloadBounds(900, 1000, 120)
        with self.assertRaises(GenerationError):
            bounds.progress({"downloaded_bytes": 1001})
        with patch(
            "generation.download.time.monotonic", return_value=bounds.deadline + 1
        ):
            with self.assertRaises(GenerationError):
                bounds.progress({"downloaded_bytes": 1})

    def test_completed_file_boundary(self):
        """Reject missing or excessive completed downloads."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.webm"
            with self.assertRaises(GenerationError):
                checked_download(path, directory, 10)
            path.write_bytes(b"audio")
            self.assertEqual(checked_download(path, directory, 10), path)
            with self.assertRaises(GenerationError):
                checked_download(path, directory, 2)
