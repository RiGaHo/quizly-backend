"""Verify ownership, nested response contracts and quiz mutation boundaries."""

from django.utils.dateparse import parse_datetime
from rest_framework.test import APITestCase

from accounts.models import User
from quizzes.models import Question, Quiz
from tests.quiz_fixtures import create_quiz

QUIZ_FIELDS = {
    "id",
    "title",
    "description",
    "created_at",
    "updated_at",
    "video_url",
    "questions",
}
QUESTION_FIELDS = {"id", "question_title", "question_options", "answer"}


class QuizApiTests(APITestCase):
    """Exercise actual cookie authentication for two users with complete quizzes."""

    def setUp(self):
        """Prepare owned and foreign quizzes and authenticate through login."""
        self.client.defaults["HTTP_ORIGIN"] = "http://testserver"
        self.owner = User.objects.create_user("alice", "alice@example.com", "Secret1")
        self.other = User.objects.create_user("other", "other@example.com", "Secret1")
        self.quiz = create_quiz(self.owner)
        self.foreign = create_quiz(self.other, "Private")
        self.url = f"/api/quizzes/{self.quiz.pk}/"
        self.client.post(
            "/api/login/", {"username": "alice", "password": "Secret1"}, format="json"
        )

    def assert_quiz_contract(self, data, quiz):
        """Check the exact documented shape and real persisted quiz values."""
        self.assertEqual(set(data), QUIZ_FIELDS)
        for field in ("id", "title", "description", "video_url"):
            self.assertEqual(data[field], getattr(quiz, field))
        for field in ("created_at", "updated_at"):
            self.assertEqual(parse_datetime(data[field]), getattr(quiz, field))
        self.assertEqual(len(data["questions"]), 10)
        for actual, expected in zip(
            data["questions"], quiz.questions.all(), strict=True
        ):
            self.assert_question_contract(actual, expected)

    def assert_question_contract(self, actual, expected):
        """Check IDs, ordered nested values, string answers and options."""
        self.assertEqual(set(actual), QUESTION_FIELDS)
        for field in QUESTION_FIELDS:
            self.assertEqual(actual[field], getattr(expected, field))
        self.assertIsInstance(actual["id"], int)
        self.assertIsInstance(actual["question_title"], str)
        self.assertEqual(len(actual["question_options"]), 4)
        self.assertTrue(
            all(isinstance(option, str) for option in actual["question_options"])
        )
        self.assertIsInstance(actual["answer"], str)

    def test_list_contract_and_ownership(self):
        """Return an unpaginated array containing only this user's quizzes."""
        response = self.client.get("/api/quizzes/")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)
        self.assertEqual(len(response.json()), 1)
        self.assert_quiz_contract(response.json()[0], self.quiz)

    def test_list_is_newest_first(self):
        """The supplied sidebar receives recent quizzes first."""
        newer = create_quiz(self.owner, "Newer")
        ids = [quiz["id"] for quiz in self.client.get("/api/quizzes/").json()]
        self.assertEqual(ids, [newer.pk, self.quiz.pk])

    def test_detail_contract(self):
        """Retrieve an owned quiz with its exact nested contract."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assert_quiz_contract(response.json(), self.quiz)

    def test_patch_title_preserves_other_fields(self):
        """A partial update preserves description, source and question values."""
        description = self.quiz.description
        response = self.client.patch(self.url, {"title": "New title"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.title, "New title")
        self.assertEqual(self.quiz.description, description)
        self.assert_quiz_contract(response.json(), self.quiz)

    def test_patch_description_and_both_fields(self):
        """Return the actual stored description despite the PDF example typo."""
        for data in (
            {"description": "New description"},
            {"title": "Both", "description": "Both changed"},
        ):
            response = self.client.patch(self.url, data, format="json")
            self.assertEqual(response.status_code, 200)
            self.quiz.refresh_from_db()
            for field, value in data.items():
                self.assertEqual(getattr(self.quiz, field), value)
            self.assert_quiz_contract(response.json(), self.quiz)

    def test_readonly_fields_rejected(self):
        """Protected ownership, source, questions and timestamps cannot be edited."""
        for field in QUIZ_FIELDS - {"title", "description"} | {
            "owner",
            "owner_id",
            "unknown",
        }:
            with self.subTest(field=field):
                response = self.client.patch(self.url, {field: 7}, format="json")
                self.assertEqual(response.status_code, 400)
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.owner, self.owner)
        self.assertEqual(self.quiz.questions.count(), 10)

    def test_foreign_detail_patch_delete_are_403(self):
        """Existing foreign objects return 403 without disclosing quiz contents."""
        url = f"/api/quizzes/{self.foreign.pk}/"
        for method in ("get", "patch", "delete"):
            response = getattr(self.client, method)(url)
            self.assertEqual(response.status_code, 403)
            self.assertNotIn("title", response.json())
        self.assertTrue(Quiz.objects.filter(pk=self.foreign.pk).exists())

    def test_unknown_objects_are_404(self):
        """Unknown IDs remain distinct from forbidden existing objects."""
        for method in ("get", "patch", "delete"):
            response = getattr(self.client, method)("/api/quizzes/99999/")
            self.assertEqual(response.status_code, 404)

    def test_delete_cascades_and_has_empty_body(self):
        """Successful delete returns 204 and removes every dependent question."""
        question_ids = list(self.quiz.questions.values_list("pk", flat=True))
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertFalse(Quiz.objects.filter(pk=self.quiz.pk).exists())
        self.assertFalse(Question.objects.filter(pk__in=question_ids).exists())
        self.assertEqual(self.foreign.questions.count(), 10)

    def test_anonymous_operations_are_401(self):
        """Protected operations never accept absent authentication cookies."""
        self.client.cookies.clear()
        for method, url in (
            ("get", "/api/quizzes/"),
            ("get", self.url),
            ("patch", self.url),
            ("delete", self.url),
        ):
            self.assertEqual(getattr(self.client, method)(url).status_code, 401)

    def test_revoked_access_cannot_read_quiz(self):
        """Logout revocation also protects real read-only quiz operations."""
        token = self.client.cookies["access_token"].value
        self.client.post("/api/logout/")
        self.client.cookies["access_token"] = token
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_no_put_or_question_api(self):
        """Do not expose undocumented write operations."""
        self.assertEqual(self.client.put(self.url, {}, format="json").status_code, 405)
        self.assertEqual(self.client.get("/api/questions/").status_code, 404)

    def test_html_patch_rejected_without_rewriting_plain_text(self):
        """Prevent executable markup while preserving harmless comparison text."""
        response = self.client.patch(
            self.url, {"title": "<img src=x onerror=alert(1)>"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(
            self.url, {"title": "2 < 3 & 4 > 1"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "2 < 3 & 4 > 1")
