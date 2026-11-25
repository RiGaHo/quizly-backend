"""Public-safe errors for bounded media and AI processing."""


class GenerationError(Exception):
    """Report a failed processing step without exposing external diagnostics."""
