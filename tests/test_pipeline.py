"""Verify orchestration, parent cleanup, shared locking and generated POST data."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from django.db import IntegrityError, connection
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.utils.dateparse import parse_datetime
from rest_framework.test import APITestCase

from accounts.models import User
from generation.errors import GenerationError
from generation.pipeline import generate_data, generation_slot
from quizzes.models import Question, Quiz
from quizzes.services import generate_and_save
from tests.test_generation_data import generated_quiz, sdk_response
from tests.test_quiz_api import QUESTION_FIELDS, QUIZ_FIELDS


class PipelineTests(SimpleTestCase):
    """Run application stages in-process with controlled external boundaries."""

    def setUp(self):
        """Own an isolated parent workspace and shared lock for every test."""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.settings_override = override_settings(
            GEMINI_API_KEY="test-fixture-not-a-real-key",
            GEMINI_API_KEY_FILE="",
            GENERATION_TEMP_DIR=self.root,
            GENERATION_LOCK_PATH=str(self.root / "lock"),
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def execute_inline(self, function, arguments, timeout):
        """Keep the actual pipeline stages while separate tests cover real processes."""
        self.workspace = Path(arguments[1])
        return function(*arguments)

    def controlled_stages(self):
        """Replace external boundaries while preserving actual local orchestration."""
        self.controlled_models()
        self.enterContext(
            patch("generation.pipeline.SESSION.execute", self.execute_inline)
        )
        self.enterContext(patch("generation.pipeline.download_audio"))
        self.enterContext(patch("generation.pipeline.convert_audio"))

    def controlled_models(self):
        """Replace expensive model calls with bounded educational fixtures."""
        model = Mock()
        model.transcribe.return_value = {"text": "A useful educational transcript."}
        self.enterContext(
            patch("generation.transcription.cached_model", return_value=model)
        )
        self.enterContext(
            patch("generation.gemini.request_quiz", return_value=sdk_response())
        )

    def test_full_stage_composition_and_cleanup(self):
        """Actual transcript/schema logic validates the controlled external output."""
        self.controlled_stages()
        self.assertEqual(generate_data("url"), generated_quiz())
        self.assertFalse(self.workspace.exists())

    def test_failure_removes_workspace(self):
        """Parent-owned temporary files disappear even when its child times out."""

        def fail(function, arguments, timeout):
            """Create a partial file before reporting a controlled process failure."""
            self.workspace = Path(arguments[1])
            (self.workspace / "partial.webm").write_bytes(b"partial")
            raise GenerationError("Deadline exceeded.")

        with patch("generation.pipeline.SESSION.execute", side_effect=fail):
            with self.assertRaises(GenerationError):
                generate_data("url")
        self.assertFalse(self.workspace.exists())

    @override_settings(GEMINI_API_KEY="", GEMINI_API_KEY_FILE="")
    def test_missing_key_fails_before_download(self):
        """Do no costly or external work when credentials are unavailable."""
        with patch("generation.pipeline.SESSION.execute") as execute:
            with self.assertRaises(GenerationError):
                generate_data("url")
        execute.assert_not_called()

    def test_shared_lock_rejects_second_holder(self):
        """Separate file descriptors cannot both hold the generation slot."""
        with generation_slot():
            with self.assertRaises(GenerationError):
                with generation_slot():
                    self.fail("Second generation must not acquire the lock")
        with generation_slot():
            pass


class QuizCreationTests(APITestCase):
    """Verify the remaining documented operation with real DB/serializer logic."""

    def setUp(self):
        """Log in with real cookie tokens before each POST test."""
        self.user = User.objects.create_user("alice", "alice@example.com", "Secret1")
        self.client.defaults["HTTP_ORIGIN"] = "http://testserver"
        self.client.post(
            "/api/login/", {"username": "alice", "password": "Secret1"}, format="json"
        )
        self.payload = {"url": "https://youtu.be/aBcdEF12_-3?si=ignored"}

    def test_post_contract_and_persistence(self):
        """POST returns the complete quiz and question timestamps after saving."""
        with patch("quizzes.services.generate_data", return_value=generated_quiz()):
            response = self.client.post("/api/quizzes/", self.payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Quiz.objects.get().owner, self.user)
        self.assertEqual(
            response.json()["video_url"], "https://www.youtube.com/watch?v=aBcdEF12_-3"
        )
        self.assertEqual(Question.objects.count(), 10)
        self.assert_create_fields(response.json())

    def assert_create_fields(self, data):
        """Validate create-specific field sets and persisted timestamp values."""
        self.assertEqual(set(data), QUIZ_FIELDS)
        for question in data["questions"]:
            self.assertEqual(
                set(question), QUESTION_FIELDS | {"created_at", "updated_at"}
            )
            self.assertEqual(question["answer"], "a")
            self.assertEqual(question["question_options"], ["a", "b", "c", "d"])
            stored = Question.objects.get(pk=question["id"])
            self.assertEqual(parse_datetime(question["created_at"]), stored.created_at)
            self.assertEqual(parse_datetime(question["updated_at"]), stored.updated_at)

    def test_invalid_input_never_starts_generation(self):
        """Reject foreign URLs, missing input and attempts to supply an owner."""
        cases = [{}, {"url": "https://evil.example/"}, self.payload | {"owner": 7}]
        with patch("quizzes.services.generate_data") as generate:
            for data in cases:
                self.assertEqual(
                    self.client.post("/api/quizzes/", data, format="json").status_code,
                    400,
                )
        generate.assert_not_called()

    def test_generation_failure_has_no_partial_quiz(self):
        """Expose a controlled 500 without model diagnostics or partial rows."""
        with patch(
            "quizzes.services.generate_data", side_effect=GenerationError("private")
        ):
            response = self.client.post("/api/quizzes/", self.payload, format="json")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "Quiz generation failed."})
        self.assertFalse(Quiz.objects.exists())

    def test_storage_failure_rolls_back_quiz(self):
        """A question insertion failure rolls back the preceding quiz insertion."""
        with patch("quizzes.services.generate_data", return_value=generated_quiz()):
            with patch(
                "quizzes.services.Question.objects.bulk_create",
                side_effect=IntegrityError,
            ):
                response = self.client.post(
                    "/api/quizzes/", self.payload, format="json"
                )
        self.assertEqual(response.status_code, 500)
        self.assertFalse(Quiz.objects.exists())
        self.assertFalse(Question.objects.exists())

    def test_invalid_generated_data_cannot_persist(self):
        """Revalidate at persistence even when an upstream stage supplies bad data."""
        with patch(
            "quizzes.services.generate_data", return_value={"title": "Incomplete"}
        ):
            response = self.client.post("/api/quizzes/", self.payload, format="json")
        self.assertEqual(response.status_code, 500)
        self.assertFalse(Quiz.objects.exists())

    def test_unauthenticated_post_is_401(self):
        """Generation always requires a valid session."""
        self.client.cookies.clear()
        response = self.client.post("/api/quizzes/", self.payload, format="json")
        self.assertEqual(response.status_code, 401)


class TransactionBoundaryTests(TransactionTestCase):
    """Inspect transaction state without TestCase's outer wrapping transaction."""

    def test_external_work_precedes_transaction(self):
        """Never hold a database transaction while downloading or calling models."""
        user = User.objects.create_user("alice", "alice@example.com", "Secret1")

        def external_work(url):
            """Check the actual database state at the external-work boundary."""
            self.assertFalse(connection.in_atomic_block)
            return generated_quiz()

        with patch("quizzes.services.generate_data", side_effect=external_work):
            quiz = generate_and_save(
                user, "https://www.youtube.com/watch?v=aBcdEF12_-3"
            )
        self.assertEqual(quiz.questions.count(), 10)
