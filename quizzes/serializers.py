"""Documented nested quiz representation and restricted partial updates."""

from rest_framework import serializers

from .models import Question, Quiz
from .validators import validate_plain_text


class QuestionSerializer(serializers.ModelSerializer):
    """Expose the question fields documented for list, detail and PATCH."""

    class Meta:
        """Keep internal positions and quiz foreign keys out of responses."""

        model = Question
        fields = ("id", "question_title", "question_options", "answer")
        read_only_fields = fields


class QuizSerializer(serializers.ModelSerializer):
    """Return owned quiz data with read-only nested questions."""

    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        """Expose only documented quiz fields."""

        model = Quiz
        fields = (
            "id",
            "title",
            "description",
            "created_at",
            "updated_at",
            "video_url",
            "questions",
        )
        read_only_fields = fields


class QuizUpdateSerializer(QuizSerializer):
    """Allow only title and description, preserving the full response schema."""

    title = serializers.CharField(max_length=200, validators=[validate_plain_text])
    description = serializers.CharField(
        max_length=3000, validators=[validate_plain_text]
    )

    def to_internal_value(self, data):
        """Reject protected and unknown fields instead of silently ignoring edits."""
        if isinstance(data, dict) and set(data) - {"title", "description"}:
            raise serializers.ValidationError(
                {"non_field_errors": ["Only title and description may be updated."]}
            )
        return super().to_internal_value(data)
