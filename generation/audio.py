"""Convert controlled local media into bounded mono PCM for local Whisper."""

import subprocess
import wave
from pathlib import Path

from .errors import GenerationError

FFMPEG_INPUT_OPTIONS = ("-nostdin", "-hide_banner", "-loglevel", "error", "-y")
MEDIA_FORMATS = "mov,matroska,webm,mp3,ogg,wav,flac,aac"
PCM_OPTIONS = ("-vn", "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le")


def convert_audio(source, workspace, max_seconds=900, timeout=120):
    """Decode a controlled local file and remove rejected output on every error."""
    source = local_source(source, workspace)
    output = Path(workspace).resolve() / "audio.wav"
    try:
        run_ffmpeg(ffmpeg_command(source, output, max_seconds), timeout)
        validate_wave(output, max_seconds)
    except (OSError, GenerationError, wave.Error, EOFError) as error:
        output.unlink(missing_ok=True)
        raise GenerationError("Audio conversion failed.") from error
    return output


def run_ffmpeg(command, timeout):
    """Enforce wall time and suppress diagnostics that could contain private data."""
    try:
        subprocess.run(
            command,
            timeout=timeout,
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.SubprocessError as error:
        raise GenerationError("Audio conversion failed.") from error


def local_source(source, workspace):
    """Require a regular input file strictly inside the controlled workspace."""
    source = Path(source)
    root = Path(workspace).resolve()
    if source.is_symlink() or not source.resolve().is_relative_to(root):
        raise GenerationError("Invalid audio source.")
    if not source.is_file() or source.resolve() == root / "audio.wav":
        raise GenerationError("Invalid audio source.")
    return source.resolve()


def ffmpeg_command(source, output, max_seconds):
    """Use an argument vector and local-only demuxing; never invoke a shell."""
    command = ["ffmpeg", *FFMPEG_INPUT_OPTIONS]
    command += ["-protocol_whitelist", "file", "-format_whitelist", MEDIA_FORMATS]
    command += ["-i", str(source)]
    command += PCM_OPTIONS
    command += ["-t", str(max_seconds + 1), "-threads", "1", str(output)]
    return command


def validate_wave(path, max_seconds):
    """Reject empty, oversized or truncated outputs before transcription."""
    with wave.open(str(path), "rb") as audio:
        validate_pcm(audio)
        frames = audio.getnframes()
        if not 0 < frames <= max_seconds * 16000:
            raise GenerationError("Audio duration exceeds configured limits.")
        if path.stat().st_size > max_seconds * 32000 + 4096:
            raise GenerationError("Audio size exceeds configured limits.")
        if len(audio.readframes(frames)) != frames * 2:
            raise GenerationError("Incomplete audio output.")


def validate_pcm(audio):
    """Accept only the mono signed-16-bit 16kHz format produced for Whisper."""
    actual = (audio.getnchannels(), audio.getsampwidth(), audio.getframerate())
    if actual != (1, 2, 16000):
        raise GenerationError("Unsupported audio format.")
