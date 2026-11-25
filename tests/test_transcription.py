"""Check CPU inference parameters, reuse and transcription failure boundaries."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from generation.errors import GenerationError
from generation.transcription import cached_model, transcribe_audio, transcript_text


class TranscriptionTests(SimpleTestCase):
    """Replace heavy dependency boundaries without skipping local application logic."""

    def test_transcript_validation(self):
        """Reject wrong types, insufficient speech and oversized model output."""
        cases = [
            None,
            {},
            {"text": 7},
            {"text": " "},
            {"text": "short"},
            {"text": "a" * 101},
        ]
        for result in cases:
            with self.subTest(result=result), self.assertRaises(GenerationError):
                transcript_text(result, 100)
        self.assertEqual(transcript_text({"text": "  " + "a" * 20}, 100), "a" * 20)

    def test_inference_is_local_cpu_and_quiet(self):
        """Call Whisper locally with half-precision and transcript printing disabled."""
        model = Mock()
        model.transcribe.return_value = {"text": "A useful educational transcript."}
        with patch("generation.transcription.cached_model", return_value=model) as load:
            text = transcribe_audio("/tmp/audio.wav", "base", "/tmp/models")
        self.assertEqual(text, "A useful educational transcript.")
        load.assert_called_once_with("base", "/tmp/models", 2)
        model.transcribe.assert_called_once_with(
            "/tmp/audio.wav", fp16=False, verbose=None
        )

    @patch("generation.transcription.Path.mkdir")
    def test_model_reused_and_loaded_on_cpu(self, _mkdir):
        """Identical configurations load once with explicit CPU execution."""
        cached_model.cache_clear()
        whisper = SimpleNamespace(available_models=lambda: ["base"], load_model=Mock())
        torch = SimpleNamespace(set_num_threads=Mock())
        with patch.dict("sys.modules", {"whisper": whisper, "torch": torch}):
            first = cached_model("base", "/cache", 2)
            self.assertIs(first, cached_model("base", "/cache", 2))
        whisper.load_model.assert_called_once_with(
            "base", device="cpu", download_root="/cache"
        )
        torch.set_num_threads.assert_called_once_with(2)
        cached_model.cache_clear()

    def test_transcription_failure_is_controlled(self):
        """Upstream exceptions never expose internal model/file diagnostics."""
        with patch(
            "generation.transcription.cached_model", side_effect=RuntimeError("private")
        ):
            with self.assertRaisesMessage(
                GenerationError, "Local transcription failed."
            ):
                transcribe_audio("/tmp/audio.wav", "base", "/cache")
