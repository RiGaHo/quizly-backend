"""Exercise database invariants and administrative question validation."""

from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.forms import inlineformset_factory, modelform_factory
from django.test import TestCase

from accounts.models import User
from quizzes.admin import QuestionAdmin, QuestionFormSet
from quizzes.models import Question, Quiz

INVALID_OPTIONS = [
    None,
    {},
    "text",
    [],
    ["a"] * 4,
    ["a", " A ", "b", "c"],
    ["", "a", "b", "c"],
    [1, "a", "b", "c"],
    ["x" * 501, "a", "b", "c"],
]


class ModelTests(TestCase):
    """Check integrity on model, database and administrative write boundaries."""

    def setUp(self):
        """Create an owner and an empty quiz fixture for individual invariants."""
        self.owner = User.objects.create_user("owner", "OWNER@Example.com", "Secret1")
        self.quiz = Quiz.objects.create(
            owner=self.owner,
            title="Science",
            description="A science quiz",
            video_url="https://www.youtube.com/watch?v=abcdefghijk",
        )

    def question(self, **changes):
        """Construct an unsaved valid question with optional invalid mutations."""
        values = {
            "quiz": self.quiz,
            "position": 1,
            "question_title": "Which one?",
            "question_options": ["One", "Two", "Three", "Four"],
            "answer": "One",
        }
        return Question(**(values | changes))

    def test_email_normalization(self):
        """Normalize case across the entire stored email address."""
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.email, "owner@example.com")

    def test_database_rejects_case_variant_email(self):
        """Bulk inserts cannot bypass case-insensitive email uniqueness."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.bulk_create(
                [User(username="other", email="OWNER@EXAMPLE.COM")]
            )

    def test_password_is_hashed(self):
        """Django user creation never stores the original password."""
        self.assertNotEqual(self.owner.password, "Secret1")
        self.assertTrue(self.owner.check_password("Secret1"))

    def test_invalid_options(self):
        """Reject wrong types, counts, blanks, duplicates and oversized options."""
        for options in INVALID_OPTIONS:
            with self.subTest(options=options), self.assertRaises(ValidationError):
                self.question(question_options=options).full_clean()

    def test_answer_must_match_exactly(self):
        """An answer differing by whitespace or case is not an exact option."""
        for answer in ("one", " One", "Other"):
            with self.subTest(answer=answer), self.assertRaises(ValidationError):
                self.question(answer=answer).full_clean()

    def test_database_rejects_duplicate_slot(self):
        """A quiz cannot have two questions at the same position."""
        self.question().save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.question().save()

    def test_database_rejects_out_of_range_slot(self):
        """Database checks protect the ten-slot range without model validation."""
        for position in (0, 11):
            with self.subTest(position=position):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.question(position=position).save()

    def test_quiz_deletion_removes_questions(self):
        """Cascade deletion prevents orphaned questions."""
        self.question().save()
        self.quiz.delete()
        self.assertFalse(Question.objects.exists())

    def test_admin_form_rejects_invalid_answer(self):
        """Django ModelForms apply question validation to individual admin edits."""
        form_type = modelform_factory(Question, fields=["question_options", "answer"])
        form = form_type(
            data={"question_options": '["a", "b", "c", "d"]', "answer": "other"},
            instance=self.question(),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("answer", form.errors)

    def test_admin_prevents_incomplete_quiz(self):
        """Inline submission cannot create a quiz without its ten questions."""
        formset_type = inlineformset_factory(
            Quiz,
            Question,
            formset=QuestionFormSet,
            fields="__all__",
        )
        data = {"questions-TOTAL_FORMS": "0", "questions-INITIAL_FORMS": "0"}
        formset = formset_type(data=data, instance=self.quiz)
        self.assertFalse(formset.is_valid())
        self.assertTrue(formset.non_form_errors())

    def test_individual_admin_cannot_add_or_delete(self):
        """Individual question pages cannot change the complete question count."""
        model_admin = QuestionAdmin(Question, AdminSite())
        self.assertFalse(model_admin.has_add_permission(None))
        self.assertFalse(model_admin.has_delete_permission(None, self.question()))

    def test_admin_rejects_executable_quiz_title(self):
        """ModelForms protect the unchanged frontend from admin-entered markup."""
        form_type = modelform_factory(Quiz, fields=["title"])
        form = form_type(data={"title": "<svg onload=alert(1)>"}, instance=self.quiz)
        self.assertFalse(form.is_valid())
        self.assertIn("title", form.errors)

    def test_question_options_reject_html(self):
        """Generated or admin-edited answer options must not contain HTML markup."""
        options = ["<img src=x onerror=alert(1)>", "b", "c", "d"]
        with self.assertRaises(ValidationError):
            self.question(question_options=options).full_clean()
