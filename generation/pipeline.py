"""Synchronous orchestration with parent-owned cleanup and shared concurrency limit."""

import fcntl
import json
import os
from contextlib import contextmanager
from tempfile import TemporaryDirectory

from django.conf import settings

from .audio import convert_audio
from .download import download_audio
from .errors import GenerationError
from .gemini import generate_quiz
from .process import ProcessingSession
from .schema import parse_quiz
from .secrets import resolve_api_key
from .transcription import transcribe_audio

SESSION = ProcessingSession()


@contextmanager
def generation_slot():
    """Use a shared advisory lock across all application processes on this host."""
    descriptor = os.open(
        settings.GENERATION_LOCK_PATH, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise GenerationError("A generation is already running.") from error
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def generate_data(url):
    """Resolve credentials before expensive work and clean files even on timeout."""
    key = resolve_api_key(settings.GEMINI_API_KEY, settings.GEMINI_API_KEY_FILE)
    with (
        generation_slot(),
        TemporaryDirectory(
            prefix="quizly-", dir=settings.GENERATION_TEMP_DIR
        ) as directory,
    ):
        arguments = (url, directory, key, settings.GENERATION_OPTIONS)
        result = SESSION.execute(process_video, arguments, settings.GENERATION_TIMEOUT)
    return parse_quiz(json.dumps(result))


def process_video(url, directory, key, options):
    """Perform real media extraction, local transcription and text-only generation."""
    source = download_audio(url, directory, **options["download"])
    audio = convert_audio(source, directory, **options["audio"])
    transcript = transcribe_audio(audio, **options["whisper"])
    return generate_quiz(transcript, key, **options["gemini"])
