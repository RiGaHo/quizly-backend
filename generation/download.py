"""Single-video audio download using bounded yt-dlp options and guarded HTTPS."""

import time
from copy import deepcopy
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from .errors import GenerationError
from .network import GuardedUrllibRH
from .urls import normalized_video_url


class MediaDownloader(YoutubeDL):
    """Force every yt-dlp request through the application-controlled transport."""

    def build_request_director(self, handlers, preferences=None):
        """Prevent optional installed transports from bypassing network restrictions."""
        return super().build_request_director([GuardedUrllibRH])


class SilentLogger:
    """Discard library diagnostics that may contain signed media URLs."""

    def debug(self, message):
        """Discard verbose library diagnostics."""

    def warning(self, message):
        """Discard upstream warnings; callers receive controlled errors."""

    def error(self, message):
        """Discard upstream errors rather than logging sensitive request data."""


class DownloadBounds:
    """Enforce metadata, transfer-size and elapsed-time limits."""

    def __init__(self, seconds, max_bytes, timeout):
        """Capture fixed limits and the monotonic start time for this download."""
        self.seconds = seconds
        self.max_bytes = max_bytes
        self.deadline = time.monotonic() + timeout

    def match_filter(self, info, *, incomplete=False):
        """Reject active streams and unknown or excessive video duration."""
        duration = info.get("duration")
        if incomplete and duration is None:
            return None
        if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming"}:
            return "Live videos are not supported."
        if not isinstance(duration, (float, int)) or not 0 < duration <= self.seconds:
            return "Video duration is unavailable or exceeds limits."
        if info.get("filesize", 0) and info["filesize"] > self.max_bytes:
            return "Video exceeds download limits."
        return None

    def progress(self, status):
        """Abort unknown-length downloads as soon as byte or time limits are crossed."""
        if status.get("downloaded_bytes", 0) > self.max_bytes:
            raise GenerationError("Download size limit exceeded.")
        if time.monotonic() > self.deadline:
            raise GenerationError("Download time limit exceeded.")


BASE_OPTIONS = {
    "format": "bestaudio[protocol=https]/best[protocol=https]",
    "noplaylist": True,
    "allowed_extractors": ["youtube"],
    "socket_timeout": 15,
    "retries": 0,
    "fragment_retries": 0,
    "quiet": True,
    "cachedir": False,
    "proxy": "",
    "js_runtimes": {"node": {}},
    "remote_components": set(),
    "overwrites": False,
}


def download_options(workspace, bounds):
    """Combine isolated library defaults with this request's private bounds."""
    return deepcopy(BASE_OPTIONS) | {
        "outtmpl": str(Path(workspace) / "source.%(ext)s"),
        "max_filesize": bounds.max_bytes,
        "match_filter": bounds.match_filter,
        "progress_hooks": [bounds.progress],
        "logger": SilentLogger(),
    }


def download_audio(url, workspace, max_seconds=900, max_bytes=100_000_000, timeout=120):
    """Download one normalized video into the pipeline-owned temporary directory."""
    canonical = normalized_video_url(url)
    bounds = DownloadBounds(max_seconds, max_bytes, timeout)
    try:
        with MediaDownloader(download_options(workspace, bounds)) as downloader:
            info = downloader.extract_info(canonical, download=True)
            if not info:
                raise GenerationError("Video rejected by configured limits.")
            path = Path(downloader.prepare_filename(info))
        return checked_download(path, workspace, max_bytes)
    except (DownloadError, OSError, ValueError) as error:
        raise GenerationError("Video download failed.") from error


def checked_download(path, workspace, max_bytes):
    """Verify the completed file remains within the controlled size and directory."""
    if path.is_symlink() or not path.resolve().is_relative_to(
        Path(workspace).resolve()
    ):
        raise GenerationError("Invalid download output.")
    if not path.is_file() or not 0 < path.stat().st_size <= max_bytes:
        raise GenerationError("Download output is missing or exceeds limits.")
    return path
