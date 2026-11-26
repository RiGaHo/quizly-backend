"""Model validation hooks separate from quiz data declarations."""

from django.core.exceptions import ValidationError

from .validators import validate_options


class QuestionValidationMixin:
    """Retain cross-field validation for model and admin form callers."""

    def clean(self):
        """Validate options and require an exact, unambiguous answer match."""
        super().clean()
        validate_options(self.question_options)
        if self.answer not in self.question_options:
            raise ValidationError(
                {"answer": "The answer must match an option exactly."}
            )
