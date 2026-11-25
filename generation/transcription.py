"""Local CPU transcription with reusable model weights and bounded text output."""

from functools import lru_cache
from pathlib import Path
from threading import Lock

from .errors import GenerationError

MODEL_LOCK = Lock()


@lru_cache(maxsize=1)
def cached_model(name, cache_directory, cpu_threads):
    """Load one configured model per process from a persistent writable cache."""
    import torch
    import whisper

    if name not in whisper.available_models():
        raise GenerationError("Unsupported Whisper model.")
    Path(cache_directory).mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(cpu_threads)
    return whisper.load_model(name, device="cpu", download_root=str(cache_directory))


def transcribe_audio(
    path, model_name, cache_directory, cpu_threads=2, max_chars=120000
):
    """Serialize local inference and report only controlled processing errors."""
    try:
        with MODEL_LOCK:
            model = cached_model(model_name, str(cache_directory), cpu_threads)
            result = model.transcribe(str(path), fp16=False, verbose=None)
        return transcript_text(result, max_chars)
    except GenerationError:
        raise
    except (OSError, RuntimeError, ValueError, ImportError) as error:
        raise GenerationError("Local transcription failed.") from error


def transcript_text(result, max_chars):
    """Require a useful nonempty text transcript without retaining audio metadata."""
    text = result.get("text") if isinstance(result, dict) else None
    if not isinstance(text, str):
        raise GenerationError("Invalid transcription result.")
    text = text.strip()
    if len(text) < 20:
        raise GenerationError("Video contains insufficient speech.")
    if len(text) > max_chars:
        raise GenerationError("Transcript exceeds configured limits.")
    return text
