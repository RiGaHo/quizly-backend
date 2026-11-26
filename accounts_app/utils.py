"""Persistence hooks kept separate from account data declarations."""


class UserNormalizationMixin:
    """Preserve email normalization for every ordinary model save."""

    def save(self, *args, **kwargs):
        """Normalize email addresses before persistence."""
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)
