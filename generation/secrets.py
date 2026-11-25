"""Read only explicitly configured Gemini credentials at request time."""

from pathlib import Path

from .errors import GenerationError


def resolve_api_key(value="", file_path=""):
    """Reject conflicting sources; never discover credentials or silently fall back."""
    if value and file_path:
        raise GenerationError("Configure only one Gemini credential source.")
    if file_path:
        value = read_key_file(file_path)
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise GenerationError("Gemini credentials are unavailable.")
    return value.strip()


def read_key_file(file_path):
    """Read a bounded runtime secret file without exposing its path or content."""
    try:
        with Path(file_path).open(encoding="utf-8") as secret:
            return secret.read(4097)
    except (OSError, UnicodeError) as error:
        raise GenerationError("Gemini credentials are unavailable.") from error
