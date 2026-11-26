"""Documented nested quiz representation and restricted partial updates."""

from django.db import DatabaseError
from rest_framework import serializers
from rest_framework.exceptions import APIException

from generation.errors import GenerationError
from generation.urls import normalized_video_url

from ..models import Question, Quiz
from ..services import generate_and_save
from ..validators import validate_plain_text


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


class CreatedQuestionSerializer(QuestionSerializer):
    """Include the additional question timestamps documented for POST responses."""

    class Meta(QuestionSerializer.Meta):
        """Extend only the create representation with question lifecycle dates."""

        fields = QuestionSerializer.Meta.fields + ("created_at", "updated_at")
        read_only_fields = fields


class QuizCreateSerializer(QuizSerializer):
    """Accept only a source URL and return a completely persisted generated quiz."""

    url = serializers.CharField(write_only=True, max_length=2048)
    questions = CreatedQuestionSerializer(many=True, read_only=True)

    class Meta(QuizSerializer.Meta):
        """Keep generated quiz fields read-only and the source input write-only."""

        fields = QuizSerializer.Meta.fields + ("url",)

    def validate_url(self, value):
        """Normalize supported YouTube URLs before any expensive processing."""
        return normalized_video_url(value)

    def to_internal_value(self, data):
        """Prevent caller-supplied ownership, generated questions or metadata."""
        if isinstance(data, dict) and set(data) - {"url"}:
            raise serializers.ValidationError(
                {"non_field_errors": ["Only url is accepted."]}
            )
        return super().to_internal_value(data)

    def create(self, validated_data):
        """Convert controlled processing/storage failures to the documented 500."""
        try:
            return generate_and_save(validated_data["owner"], validated_data["url"])
        except (GenerationError, DatabaseError, OSError) as error:
            raise APIException("Quiz generation failed.") from error
