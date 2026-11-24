"""Shared validation for generated data and administrative edits."""

from django.core.exceptions import ValidationError


def validate_options(value):
    """Require four distinct nonempty plain text answer options."""
    if not isinstance(value, list) or len(value) != 4:
        raise ValidationError("Exactly four answer options are required.")
    for option in value:
        if not isinstance(option, str) or not option.strip() or len(option) > 500:
            raise ValidationError(
                "Options must be nonempty strings up to 500 characters."
            )
    if len({option.strip().casefold() for option in value}) != 4:
        raise ValidationError("Answer options must be distinct.")
