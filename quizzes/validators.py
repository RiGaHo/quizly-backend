"""Shared validation for generated data and administrative edits."""

import re

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
        validate_plain_text(option)
    if len({option.strip().casefold() for option in value}) != 4:
        raise ValidationError("Answer options must be distinct.")


def validate_plain_text(value):
    """Reject HTML markup that the unchanged reference frontend could execute."""
    if re.search(r"<\s*[a-z!/?]", value, flags=re.IGNORECASE):
        raise ValidationError("HTML markup is not allowed in quiz text.")
