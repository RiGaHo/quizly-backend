"""Owned quizzes and ordered, validated multiple-choice questions."""

from django.conf import settings
from django.db import models

from .utils import QuestionValidationMixin
from .validators import validate_options, validate_plain_text


class Quiz(models.Model):
    """Store one generated quiz and its source video."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quizzes"
    )
    title = models.CharField(max_length=200, validators=[validate_plain_text])
    description = models.TextField(max_length=3000, validators=[validate_plain_text])
    video_url = models.URLField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Show recent quizzes first, with deterministic timestamp ties."""

        ordering = ["-created_at", "-pk"]

    def __str__(self):
        """Identify quizzes by their readable title."""
        return self.title


class Question(QuestionValidationMixin, models.Model):
    """Store a single question with the exact answer string used by the frontend."""

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    position = models.PositiveSmallIntegerField()
    question_title = models.CharField(max_length=1000, validators=[validate_plain_text])
    question_options = models.JSONField(validators=[validate_options])
    answer = models.CharField(max_length=500, validators=[validate_plain_text])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Prevent duplicate slots and positions outside a ten-question quiz."""

        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["quiz", "position"], name="question_slot"),
            models.CheckConstraint(
                condition=models.Q(position__gte=1, position__lte=10),
                name="question_position_range",
            ),
        ]

    def __str__(self):
        """Identify questions by their title in administrative lists."""
        return self.question_title
