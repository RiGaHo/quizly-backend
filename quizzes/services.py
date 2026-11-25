"""Validate generated data before atomic persistence of complete quiz aggregates."""

import json

from django.db import transaction

from generation.pipeline import generate_data
from generation.schema import parse_quiz

from .models import Question, Quiz


def generate_and_save(owner, url):
    """Keep external processing outside every database transaction."""
    data = generate_data(url)
    return save_generated_quiz(owner, url, data)


def save_generated_quiz(owner, url, data):
    """Validate all data first, then store quiz and ten questions as one unit."""
    validated = parse_quiz(json.dumps(data))
    questions = validated.pop("questions")
    with transaction.atomic():
        quiz = Quiz.objects.create(owner=owner, video_url=url, **validated)
        Question.objects.bulk_create(
            [
                Question(quiz=quiz, position=position, **question)
                for position, question in enumerate(questions, start=1)
            ]
        )
    return quiz
