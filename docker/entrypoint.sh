#!/bin/sh
set -eu
umask 077
# One application instance owns migrations; diagnostic commands skip them.
if [ "${1:-}" = "gunicorn" ]; then
    python manage.py check
    python manage.py migrate --noinput
fi
exec "$@"
