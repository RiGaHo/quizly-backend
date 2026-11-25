"""Independent strict validation of all AI-generated quiz data."""

from typing import Annotated

from django.core.exceptions import ValidationError as DjangoValidationError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from quizzes.validators import validate_options, validate_plain_text

from .errors import GenerationError

Title = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=200),
]
Description = Annotated[
    str,
    StringConstraints(
        strict=True, strip_whitespace=True, min_length=1, max_length=3000
    ),
]
QuestionText = Annotated[
    str,
    StringConstraints(
        strict=True, strip_whitespace=True, min_length=1, max_length=1000
    ),
]
Option = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=500),
]


class GeneratedQuestion(BaseModel):
    """Require exactly four suitable choices and one exact matching answer."""

    model_config = ConfigDict(extra="forbid", strict=True)
    question_title: QuestionText
    question_options: list[Option] = Field(min_length=4, max_length=4)
    answer: Option

    @model_validator(mode="after")
    def validate_choices(self):
        """Apply application HTML/option rules independently of Gemini's schema."""
        validate_plain_text(self.question_title)
        validate_options(self.question_options)
        if self.answer not in self.question_options:
            raise ValueError("The answer must equal exactly one option.")
        return self


class GeneratedQuiz(BaseModel):
    """Require a complete ten-question quiz before persistence is possible."""

    model_config = ConfigDict(extra="forbid", strict=True)
    title: Title
    description: Description
    questions: list[GeneratedQuestion] = Field(min_length=10, max_length=10)

    @model_validator(mode="after")
    def validate_text(self):
        """Protect reference frontend HTML sinks without altering response formats."""
        validate_plain_text(self.title)
        validate_plain_text(self.description)
        return self


def parse_quiz(text, max_chars=100000):
    """Reject malformed, incomplete or excessive JSON without leaking model output."""
    if not isinstance(text, str) or len(text) > max_chars:
        raise GenerationError("Invalid generated quiz.")
    try:
        return GeneratedQuiz.model_validate_json(text).model_dump()
    except (ValidationError, DjangoValidationError, ValueError) as error:
        raise GenerationError("Invalid generated quiz.") from error
