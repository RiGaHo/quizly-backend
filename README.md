# Quizly Backend

Django/DRF API for personal YouTube quizzes: yt-dlp downloads audio, FFmpeg
converts it, local CPU Whisper transcribes it, and Gemini Flash generates ten
questions with four options each. Quiz creation is synchronous and atomic.

## Local setup

Use Python 3.12. Install **FFmpeg globally** (`sudo apt install ffmpeg` on
Debian/Ubuntu) and Node.js 24 for yt-dlp's JavaScript support.

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip==26.3
pip install -r requirements-dev.txt
cp .env.example .env
```

Set a random `DJANGO_SECRET_KEY` in `.env`, then start Django:

```sh
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000
```

Environment values override `.env`; `DJANGO_READ_DOTENV=false` disables loading it.
Use `DJANGO_DEBUG=true` only for local HTTP. Set `DJANGO_ALLOWED_HOSTS` and exact
`FRONTEND_ORIGINS` (e.g. `http://127.0.0.1:5500`). Serve the separately supplied
frontend on the same hostname with API base `http://127.0.0.1:8000/api/`.
The admin is available locally at `/admin/`.

## Configuration and API

Supply **either** `GEMINI_API_KEY` **or** `GEMINI_API_KEY_FILE`; configuring both
is an error. No Gemini key is required to start or use account/quiz-management
endpoints. Generation without a key returns 500 without saving a partial quiz.
Only the transcript is sent to Gemini; Whisper runs locally. Keep keys out of Git.

`.env.example` lists processing settings. Defaults: 900-second videos/jobs,
100 MB downloads, 120,000 transcript characters, Whisper `base` with two CPU
threads, and `gemini-3.8-flash`. One generation runs at a time. Model weights are
downloaded on first use and retained in `WHISPER_CACHE_DIR`. Temporary audio is
removed after processing. `DATABASE_PATH` selects the writable SQLite file.

- `POST /api/register/`, `/api/login/`, `/api/logout/`, `/api/token/refresh/`
- `GET` and `POST /api/quizzes/`
- `GET`, `PATCH` and `DELETE /api/quizzes/<id>/`

Creation accepts `url`; PATCH accepts only `title` and `description`. Lists contain
only the current user's quizzes. Existing foreign quizzes return 403; absent
quizzes return 404. Authentication uses HttpOnly `access_token`/`refresh_token`
cookies. Refresh needs no body. Logout revokes both token types for that login,
leaving other sessions valid. Unsafe requests require a trusted Origin (or
same-origin Referer); nonempty bodies must be JSON. Browser requests must include
credentials. Game answers remain client-side; there is no progress API.

## Structure and checks

`core/` contains project configuration. `accounts_app/` and `quizzes_app/` contain
models/admin, with API serializers, views, permissions/authentication and routing
under `api/`. Model hooks live in app `utils.py`; `generation/` contains the
unchanged processing pipeline. Each app's URLs are included by `core/urls.py`.

```sh
python manage.py check --settings=core.test_settings
```

Regular CI runs the existing tests, Ruff, migration consistency and convention
checks before publishing. Functions are limited to 14 physical lines including
signature/docstring; generated migrations are excluded. Tests require no real key.

## Container and deployment

Build with `docker build -t quizly-backend:local .`. The image includes FFmpeg,
Node and CPU dependencies, runs as `10001:10001` on port 8000, and migrates before
Gunicorn starts. Use one application instance during startup. Defaults are one
worker, two threads and a 960-second worker timeout; configure through
`GUNICORN_WORKERS`, `GUNICORN_THREADS`, `GUNICORN_TIMEOUT` as needed.

Use read-only root, dropped capabilities and no-new-privileges. Provide writable
`/data` (SQLite), `/models` (model cache) and `/tmp` (processing/server files).
Mounted persistent paths must be writable by UID/GID 10001. Mount Gemini secrets
read-only and set `GEMINI_API_KEY_FILE=/run/secrets/gemini_api_key`.

Production requires a strong Django key, explicit hosts and HTTPS origins.
Route `/api/` directly to the backend and other paths to the frontend; do not
expose `/admin/`. Enable `TRUST_PROXY=true` only behind a trusted proxy replacing
forwarded headers. Pi memory/performance, proxy timeouts and HSTS require separate
deployment verification; no real Gemini or full external integration is claimed.

Main pushes automatically publish AMD64/ARM64 images to
`ghcr.io/rigaho/quizly-backend:latest` and `:sha-<full-commit-sha>` after CI.
Pull requests never publish.

**Deployment after this structure change:** stop the backend, delete the old
SQLite database and its sidecar files, pull the new image, and start the backend.
Keep the Whisper model cache and environment configuration. Existing database
compatibility is intentionally not provided.
