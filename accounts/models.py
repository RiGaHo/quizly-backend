"""Users and revocable login sessions shared by access and refresh tokens."""

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower


class User(AbstractUser):
    """Require a unique email address, including case-insensitive uniqueness."""

    email = models.EmailField(unique=True)

    class Meta:
        """Enforce normalized uniqueness even for writes outside serializers."""

        constraints = [models.UniqueConstraint(Lower("email"), name="user_email_ci")]

    def save(self, *args, **kwargs):
        """Normalize email addresses before persistence."""
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)


class LoginSession(models.Model):
    """Keep one immutable session identity across a login's token renewals."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="logins")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
