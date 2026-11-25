"""Deterministic URL and bounded audio tests without external downloads."""

import subprocess
import tempfile
import wave
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from generation.audio import convert_audio, ffmpeg_command, validate_wave
from generation.errors import GenerationError
from generation.urls import normalized_video_url

VIDEO_ID = "aBcdEF12_-3"
VALID_LINKS = [
    f"https://www.youtube.com/watch?v={VIDEO_ID}",
    f"http://m.youtube.com/watch?v={VIDEO_ID}&list=ignored&t=20",
    f"https://youtu.be/{VIDEO_ID}?si=tracking",
    f"https://www.youtube.com/shorts/{VIDEO_ID}",
    f"https://youtube.com/embed/{VIDEO_ID}",
    f"https://youtube.com/live/{VIDEO_ID}",
]
INVALID_LINKS = [
    None,
    42,
    "",
    "file:///etc/passwd",
    "http://127.0.0.1/watch?v=" + VIDEO_ID,
    "https://youtube.com.evil.test/watch?v=" + VIDEO_ID,
    "https://youtube.com@evil.test/watch?v=" + VIDEO_ID,
    "https://user:pass@youtube.com/watch?v=" + VIDEO_ID,
    "https://youtube.com:444/watch?v=" + VIDEO_ID,
    "https://youtube.com/playlist?list=anything",
    "https://youtube.com/watch?v=short",
    "https://youtube.com/watch?v=" + VIDEO_ID + "&v=" + VIDEO_ID,
    "https://youtu.be/" + VIDEO_ID + "/extra",
    "https://youtube.com/watch?v=abcdefghij%0A",
    "https://youtube.com/watch?v=abcdefghijé",
    "https://youtube.com/watch?v=$(id)",
]


def write_wave(path, frames=160, rate=16000):
    """Write controlled silence, sufficient to test conversion output checks."""
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\x00\x00" * frames)


class VideoUrlTests(SimpleTestCase):
    """Accept supported formats while removing all non-ID URL authority."""

    def test_normalization(self):
        """Canonical watch URLs remain compatible with the original iframe code."""
        for value in VALID_LINKS:
            with self.subTest(value=value):
                self.assertEqual(
                    normalized_video_url(value),
                    f"https://www.youtube.com/watch?v={VIDEO_ID}",
                )

    def test_invalid_links(self):
        """Reject ambiguous IDs, foreign hosts, credentials and playlist-only URLs."""
        for value in INVALID_LINKS:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                normalized_video_url(value)


class AudioTests(SimpleTestCase):
    """Test cleanup, process limits and PCM validation at the real file boundary."""

    def setUp(self):
        """Provide a private temporary workspace with a nonsecret input file."""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "source.webm"
        self.source.write_bytes(b"fixture")

    def produce_wave(self, command, **kwargs):
        """Replace only FFmpeg's OS boundary, keeping actual file validation."""
        write_wave(command[-1])

    def test_successful_conversion(self):
        """Run production conversion orchestration against controlled PCM output."""
        with patch(
            "generation.audio.subprocess.run", side_effect=self.produce_wave
        ) as run:
            output = convert_audio(self.source, self.root)
        self.assertEqual(output, self.root / "audio.wav")
        self.assertEqual(run.call_args.kwargs["timeout"], 120)
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_conversion_failure_and_timeout_cleanup(self):
        """Failed processes cannot leave a partial WAV for the next stage."""
        errors = [
            OSError(),
            subprocess.CalledProcessError(1, "ffmpeg"),
            subprocess.TimeoutExpired("ffmpeg", 1),
        ]
        for error in errors:
            (self.root / "audio.wav").write_bytes(b"partial")
            with patch("generation.audio.subprocess.run", side_effect=error):
                with self.assertRaises(GenerationError):
                    convert_audio(self.source, self.root)
            self.assertFalse((self.root / "audio.wav").exists())

    def test_output_validation_failure_cleanup(self):
        """Invalid decoded content is also removed before reporting failure."""
        (self.root / "audio.wav").write_bytes(b"not audio")
        with patch("generation.audio.subprocess.run"):
            with self.assertRaises(GenerationError):
                convert_audio(self.source, self.root)
        self.assertFalse((self.root / "audio.wav").exists())

    def test_rejects_nonlocal_and_symlink_sources(self):
        """No user path or symlink can select a file outside the workspace."""
        link = self.root / "link.webm"
        link.symlink_to(self.source)
        for source in (link, self.root.parent / "outside", self.root / "missing"):
            with self.subTest(source=source), self.assertRaises(GenerationError):
                convert_audio(source, self.root)

    def test_duration_and_format_limits(self):
        """Reject empty, overlong and incorrectly sampled decoded audio."""
        path = self.root / "audio.wav"
        for frames, rate in ((0, 16000), (16001, 16000), (160, 8000)):
            write_wave(path, frames=frames, rate=rate)
            with (
                self.subTest(frames=frames, rate=rate),
                self.assertRaises(GenerationError),
            ):
                validate_wave(path, 1)

    def test_network_protocols_disabled(self):
        """FFmpeg receives only a local-file whitelist and bounded decode duration."""
        command = ffmpeg_command(self.source, self.root / "audio.wav", 900)
        self.assertEqual(command[command.index("-protocol_whitelist") + 1], "file")
        self.assertEqual(command[command.index("-t") + 1], "901")
        self.assertEqual(command[command.index("-threads") + 1], "1")
