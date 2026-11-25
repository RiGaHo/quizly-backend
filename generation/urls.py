"""Normalize supported YouTube links without ever fetching user-provided hosts."""

import re
from urllib.parse import parse_qs, urlsplit

from django.core.exceptions import ValidationError

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}", flags=re.ASCII)


def normalized_video_url(value):
    """Accept an individual public YouTube link and return canonical watch syntax."""
    if not isinstance(value, str) or len(value) > 2048:
        raise ValidationError("Provide a YouTube video URL.")
    try:
        parsed = urlsplit(value.strip())
        check_url_parts(parsed)
        video_id = extract_video_id(parsed)
    except (ValueError, KeyError, IndexError) as error:
        raise ValidationError("Provide a valid YouTube video URL.") from error
    if not VIDEO_ID.fullmatch(video_id):
        raise ValidationError("Invalid YouTube video ID.")
    return f"https://www.youtube.com/watch?v={video_id}"


def check_url_parts(parsed):
    """Reject credentials, foreign hosts, custom ports and unsupported schemes."""
    if parsed.scheme not in {"https", "http"} or parsed.username or parsed.password:
        raise ValidationError("Only public YouTube HTTP(S) links are supported.")
    if parsed.hostname not in YOUTUBE_HOSTS | {"youtu.be", "www.youtu.be"}:
        raise ValidationError("Only YouTube video URLs are supported.")
    if parsed.port not in {None, 443 if parsed.scheme == "https" else 80}:
        raise ValidationError("Custom ports are not supported.")
    if "\\" in parsed.netloc or any(ord(char) < 33 for char in parsed.netloc):
        raise ValidationError("Invalid URL authority.")


def extract_video_id(parsed):
    """Extract only video IDs; discard tracking, playlist and time parameters."""
    path = parsed.path.rstrip("/")
    if parsed.hostname in {"youtu.be", "www.youtu.be"}:
        return path.removeprefix("/")
    if path == "/watch":
        values = parse_qs(parsed.query, max_num_fields=30).get("v", [])
        if len(values) == 1:
            return values[0]
    for prefix in ("/shorts/", "/embed/", "/live/"):
        if path.startswith(prefix):
            return path.removeprefix(prefix)
    raise ValidationError("A single YouTube video is required.")
