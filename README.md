# Quizly Backend

Django REST API for generating personal quizzes from YouTube audio using local
Whisper transcription and Gemini Flash. Implementation is in progress; the
initial commit provides configuration and checks, not a finished quiz service.

## Development setup

Python 3.12 is the selected runtime. Create an isolated environment:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

Insert the generated value into `DJANGO_SECRET_KEY` in `.env`; do not commit it.
Environment variables take precedence over `.env`. Set explicit allowed hosts.
`DJANGO_DEBUG=true` enables local HTTP cookies; production defaults to HTTPS
redirects and secure cookies and requires a key of at least 50 characters.
Use `DATABASE_PATH` for a writable SQLite file on persistent storage. Its parent
directory must exist. Run migrations before serving:

```sh
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000
```

FFmpeg must be installed as a system executable in PATH for audio processing
and Whisper (on Debian/Ubuntu: `sudo apt install ffmpeg`). yt-dlp also requires
a supported JavaScript runtime and its EJS component. AI dependencies and
pipeline setup will be documented with their implementation.

Serve the provided, separately obtained frontend on `127.0.0.1`, for example
port 5500. Its API base is `http://127.0.0.1:8000/api/`. Add the exact frontend
origin to `FRONTEND_ORIGINS`; cookies require consistent host names. The original
frontend is not distributed in this repository.

`TRUST_PROXY=true` trusts `X-Forwarded-Proto` only when a trusted reverse proxy
removes incoming spoofed headers and direct backend access is prevented. Leave
it false for direct local serving. Admin is available locally at `/admin/` and
must not be exposed by portfolio routing. HSTS rollout belongs to the later
verified HTTPS deployment, not local development.

## Checks

```sh
python manage.py test --settings=config.test_settings
python manage.py check --settings=config.test_settings
python manage.py makemigrations --check --dry-run --settings=config.test_settings
ruff check .
ruff format --check .
python tools/check_conventions.py
```

The convention checker counts every physical line from `def` to the end of its
last statement, including the signature, docstring, blank lines and comments.
Decorators are outside that span. The limit is 14 lines for application, tools
and test functions. Generated migrations and virtual environments are excluded.
Ruff additionally checks formatting, imports, unused bindings and docstrings.
Responsibility boundaries, meaningful naming and obsolete code require review.

Test settings contain only nonsecret fixtures, use an in-memory database and a
fast password hasher. Never serve the application with test settings.
