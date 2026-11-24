#!/usr/bin/env python
"""Run Django administrative commands."""

import os
import sys

from django.core.management import execute_from_command_line


def main():
    """Dispatch commands using the configured application settings."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
