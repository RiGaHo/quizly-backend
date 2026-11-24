"""Controlled complete quiz fixtures shared across API and generation tests."""

from quizzes.models import Question, Quiz


def create_quiz(owner, title="Science"):
    """Persist a deterministic ten-question quiz without invoking external services."""
    quiz = Quiz.objects.create(
        owner=owner,
        title=title,
        description="A science quiz",
        video_url="https://www.youtube.com/watch?v=abcdefghijk",
    )
    Question.objects.bulk_create(
        [create_question(quiz, position) for position in range(1, 11)]
    )
    return quiz


def create_question(quiz, position):
    """Construct a valid ordered question without saving it separately."""
    return Question(
        quiz=quiz,
        position=position,
        question_title=f"Question {position}",
        question_options=["One", "Two", "Three", "Four"],
        answer="One",
    )
