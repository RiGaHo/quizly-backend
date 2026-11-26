"""Use Django's established user administration with required email addresses."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class AccountAdmin(UserAdmin):
    """Include the required email field when creating users administratively."""

    add_fieldsets = UserAdmin.add_fieldsets + (("Contact", {"fields": ("email",)}),)
