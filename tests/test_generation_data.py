"""Strict generation validation and explicit credential-source tests."""

import json
import tempfile
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from google.genai import types

from generation.errors import GenerationError
from generation.gemini import (
    create_client,
    generate_quiz,
    generation_config,
    validated_response,
)
from generation.schema import parse_quiz
from generation.secrets import resolve_api_key


def generated_quiz():
    """Build controlled AI data without replacing production validation."""
    question = {
        "question_title": "Which option?",
        "question_options": ["a", "b", "c", "d"],
        "answer": "a",
    }
    return {
        "title": "Quiz",
        "description": "Description",
        "questions": [deepcopy(question) for _ in range(10)],
    }


INVALID_QUESTIONS = [
    {"question_options": ["a"] * 4},
    {"question_options": ["a", "b"]},
    {"question_options": [1, "b", "c", "d"]},
    {"answer": "none"},
    {"question_title": "<img src=x onerror=alert(1)>"},
    {"answer": ""},
]


class GeneratedDataTests(SimpleTestCase):
    """Check independent application validation beyond the requested JSON schema."""

    def test_valid_complete_quiz(self):
        """Return complete validated data with no invented defaults."""
        data = generated_quiz()
        self.assertEqual(parse_quiz(json.dumps(data)), data)

    def test_malformed_or_incomplete_json(self):
        """Reject missing fields, nonobjects, invalid JSON and excessive text."""
        for text in (None, "broken", "[]", "{}", "null", "x" * 100001):
            with self.subTest(text_type=type(text)), self.assertRaises(GenerationError):
                parse_quiz(text)

    def test_question_count(self):
        """Exactly ten questions are required for atomic persistence."""
        for count in (0, 1, 9, 11):
            data = generated_quiz()
            data["questions"] = [data["questions"][0]] * count
            with self.subTest(count=count), self.assertRaises(GenerationError):
                parse_quiz(json.dumps(data))

    def test_question_errors(self):
        """Reject bad option count/types, duplicates, missing answers and markup."""
        for mutation in INVALID_QUESTIONS:
            data = generated_quiz()
            data["questions"][0].update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(GenerationError):
                parse_quiz(json.dumps(data))

    def test_top_level_types_and_limits(self):
        """AI fields cannot exceed API limits or inject extra ownership fields."""
        for mutation in (
            {"title": 42},
            {"title": "a" * 201},
            {"description": " "},
            {"owner": 1},
        ):
            with self.subTest(mutation=mutation), self.assertRaises(GenerationError):
                parse_quiz(json.dumps(generated_quiz() | mutation))


class CredentialTests(SimpleTestCase):
    """Use only explicit nonsecret fixtures, never real environment credentials."""

    def test_environment_value(self):
        """Accept an explicitly supplied key without searching other variables."""
        self.assertEqual(
            resolve_api_key(" test-fixture-not-a-real-key "),
            "test-fixture-not-a-real-key",
        )

    def test_file_value(self):
        """Read a supplied runtime file and strip its trailing newline."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture"
            path.write_text("test-fixture-not-a-real-key\n")
            self.assertEqual(
                resolve_api_key(file_path=path), "test-fixture-not-a-real-key"
            )

    def test_conflicts_missing_and_oversized(self):
        """Reject ambiguity or missing credentials without reading unrelated files."""
        for value, path in (("", ""), ("fixture", "/unused"), ("x" * 4097, "")):
            with (
                self.subTest(value_length=len(value)),
                self.assertRaises(GenerationError),
            ):
                resolve_api_key(value, path)
        with self.assertRaisesMessage(GenerationError, "unavailable"):
            resolve_api_key(file_path="/nonexistent-quizly-test-fixture")


class GeminiTests(SimpleTestCase):
    """Mock only SDK requests while retaining configuration and JSON validation."""

    def test_explicit_client_boundary(self):
        """Disable credential autodiscovery, endpoint overrides and SDK retries."""
        with patch("generation.gemini.genai.Client") as factory:
            create_client("test-fixture-not-a-real-key", 60)
        options = factory.call_args.kwargs
        self.assertFalse(options["vertexai"])
        self.assertFalse(options["enterprise"])
        self.assertEqual(options["http_options"].retry_options.attempts, 1)
        self.assertEqual(options["http_options"].timeout, 60000)
        self.assertEqual(
            options["http_options"].base_url,
            "https://generativelanguage.googleapis.com",
        )

    def test_structured_output_config(self):
        """Create a real SDK config with schema, bounded output and no tools."""
        config = generation_config()
        self.assertEqual(config.response_mime_type, "application/json")
        self.assertEqual(
            config.response_json_schema["properties"]["questions"]["minItems"], 10
        )
        self.assertIsNone(config.tools)
        self.assertEqual(config.max_output_tokens, 8192)

    def test_success_uses_actual_validation(self):
        """A controlled SDK response traverses the entire generation validator."""
        response = sdk_response()
        client = Mock()
        client.models.generate_content.return_value = response
        with patch("generation.gemini.create_client") as factory:
            factory.return_value.__enter__.return_value = client
            result = generate_quiz(
                "Educational transcript with sufficient content.", "fixture"
            )
        self.assertEqual(result, generated_quiz())
        client.models.generate_content.assert_called_once()

    def test_truncated_and_blocked_responses(self):
        """A valid JSON body cannot override an incomplete finish status."""
        for reason in (types.FinishReason.MAX_TOKENS, types.FinishReason.SAFETY):
            response = SimpleNamespace(
                candidates=[SimpleNamespace(finish_reason=reason)],
                text=json.dumps(generated_quiz()),
            )
            with self.assertRaises(GenerationError):
                validated_response(response)

    def test_service_errors_are_sanitized(self):
        """Quota/timeout/SDK errors yield a controlled public error without retries."""
        with patch(
            "generation.gemini.request_quiz", side_effect=RuntimeError("private")
        ) as request:
            with self.assertRaisesMessage(GenerationError, "service failed"):
                generate_quiz(
                    "Educational transcript with sufficient content.", "fixture"
                )
        request.assert_called_once()


def sdk_response():
    """Represent one successful SDK response with controlled quiz JSON."""
    return SimpleNamespace(
        candidates=[SimpleNamespace(finish_reason=types.FinishReason.STOP)],
        text=json.dumps(generated_quiz()),
    )
