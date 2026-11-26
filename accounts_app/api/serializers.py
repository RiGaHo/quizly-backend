"""Registration and login validation matching the supplied frontend."""

import re

from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.validators import UniqueValidator

from ..models import User


class RegisterSerializer(serializers.ModelSerializer):
    """Validate account data without exposing password fields in responses."""

    email = serializers.EmailField(
        validators=[
            UniqueValidator(queryset=User.objects.all(), lookup="iexact"),
        ]
    )
    password = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=128
    )
    confirmed_password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        """Limit account creation to the four documented request fields."""

        model = User
        fields = ("username", "email", "password", "confirmed_password")
        extra_kwargs = {"username": {"min_length": 3}}

    def validate(self, attrs):
        """Apply the frontend password rules and confirmation check."""
        password = attrs["password"]
        if not re.fullmatch(r"(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{6,128}", password):
            raise serializers.ValidationError(
                {"password": "Use 6+ characters, A-Z, a-z, 0-9."}
            )
        if password != attrs.pop("confirmed_password"):
            raise serializers.ValidationError(
                {"confirmed_password": "Passwords differ."}
            )
        attrs["email"] = attrs["email"].strip().lower()
        return attrs

    def create(self, validated_data):
        """Hash the password and handle concurrent uniqueness conflicts safely."""
        try:
            with transaction.atomic():
                return User.objects.create_user(**validated_data)
        except IntegrityError as error:
            raise serializers.ValidationError(
                "Username or email already exists."
            ) from error


class LoginSerializer(serializers.Serializer):
    """Authenticate without revealing whether a username exists."""

    username = serializers.CharField(max_length=150)
    password = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=128
    )

    def validate(self, attrs):
        """Use Django's authentication backend and password timing protections."""
        user = authenticate(request=self.context.get("request"), **attrs)
        if user is None:
            raise AuthenticationFailed("Invalid username or password.")
        return {"user": user}
