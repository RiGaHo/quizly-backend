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

## Data integrity and administration

Users have normalized, case-insensitively unique email addresses. Login sessions
provide a shared revocation identity for the forthcoming cookie token endpoints.
Quizzes belong to a user; questions cascade when their quiz is deleted. Question
positions are unique within a quiz and constrained to 1–10 by SQLite. Application
and admin validation require four distinct nonempty options and an exact answer.
The generation service must validate and save all ten questions atomically;
SQL row constraints alone cannot enforce a related-row count.

Admin quiz forms require exactly ten questions. Individual question pages permit
editing but not adding, moving or deleting questions independently. Quiz and
question timestamps are read-only. The naming check permits Django/unittest's
required lifecycle names (`setUp`, `tearDown`, `setUpClass`, `tearDownClass`,
`setUpTestData`); their physical length and docstrings are still checked.

## Cookie authentication and CSRF

`POST /api/register/` accepts `username`, `email`, `password`, and
`confirmed_password`; success returns 201. Password rules match the original
frontend: at least six characters, an uppercase letter, lowercase letter and a
digit (maximum 128). Django hashes passwords. Registration does not log users in.
`POST /api/login/` accepts `username` and `password`; success returns 200 with
`detail` and `user: {id, username, email}`. Invalid credentials return a generic
401. `POST /api/token/refresh/` needs only the refresh cookie; it works with an
expired access cookie, without a body or Content-Type header.

JWTs appear only in HttpOnly `access_token` and `refresh_token` cookies, scoped
to `/api/`, host-only, SameSite=Lax, Secure outside explicit local debug mode.
Access lasts 15 minutes; refresh and its server-side session last seven days.
There is no refresh rotation: renewal does not extend the session's deadline.
An Authorization header cannot replace the cookies. API responses use no-store.

`POST /api/logout/` requires a valid access cookie and revokes its login session
before expiring both cookies. Every access and refresh validates the same signed
session ID against persistent database state. Revocation rejects all tokens from
that login, including renewed access tokens. Other independently established
logins remain valid. Refresh never writes session state, so an overlapping
refresh cannot restore a revoked session: even a token issued after a concurrent
logout is rejected on use. A request already authorized before logout may finish.
With expired access, refresh first and then logout. No tokens or passwords are
stored in application logs; session rows contain identity and lifecycle dates.

Unsafe API requests must contain an exact allowed `Origin`, or, only when
Origin is absent, a Referer from the same origin or an explicitly allowed
frontend. Missing provenance, `Origin: null`, wildcard-like matches and foreign
origins return 403. Payloads must be JSON; empty logout and refresh bodies need
no content type. CORS permissions alone are not used as CSRF protection. The
Django admin keeps Django's normal CSRF-token protection.

The original frontend supplies Origin automatically through browser fetch and
needs no changes. For curl/Postman/automated clients, explicitly set
`Origin: http://127.0.0.1:8000` for local API writes (or the actual configured
origin). This header is a browser CSRF boundary, **not authentication**: nonbrowser
clients can set it but still require valid credentials or signed cookies. We do
not guess client type from User-Agent or Sec-Fetch headers and do not silently
allow absent Origin/Referer. Use the same hostname for local frontend/backend;
`localhost` and `127.0.0.1` are different cookie sites. Production uses the same
HTTPS origin for frontend and `/api/`.

## Quiz management

`GET /api/quizzes/` returns a direct JSON array of the authenticated user's
quizzes, newest first. `GET /api/quizzes/{id}/` returns one quiz with ordered
nested questions. `PATCH` at the same URL accepts only `title` and/or
`description`, returns the stored values and preserves omitted fields. Protected
or unknown fields are rejected with 400. `DELETE` removes the quiz and its
questions and returns 204 with no body. PUT and separate question CRUD routes
are not provided. Quiz generation by POST is the next implementation phase.

Detail lookup deliberately checks existence before ownership: existing foreign
IDs return 403, absent IDs 404, and missing authentication 401. This reveals ID
existence as required by the supplied contract, without returning foreign data.
The list query is always scoped to its owner. DRF generic mixins implement the
standard operations with object permissions and a restricted serializer.

Texts are plain text: executable HTML markup is rejected, including admin
edits, rather than silently rewritten or HTML-escaped in API output. Harmless
comparison text such as `2 < 3` remains unchanged. This reduces risk in the
unchanged reference frontend's HTML sinks; the separate portfolio frontend will
also use safe DOM insertion. Limits: titles 200, descriptions 3000, question
titles 1000 and individual options/answers 500 characters.

## Media input boundaries

YouTube links are normalized to `https://www.youtube.com/watch?v=<11-char-ID>`.
Supported inputs include watch, youtu.be, shorts, embed and live URL syntax;
a live-format URL does not authorize downloading an active livestream. The
subsequent metadata stage must reject active streams. Tracking/time/playlist
parameters are discarded, and playlist-only URLs are rejected. Credentials,
foreign hosts, custom ports and ambiguous IDs are rejected before networking.

The audio conversion module accepts only files inside its controlled workspace.
It invokes FFmpeg without a shell, disables network protocols and playlist
demuxers, limits decode time and uses one thread. The default conversion deadline
is 120 seconds and maximum audio duration 900 seconds; the pipeline can supply
explicit limits. Output is mono 16-bit PCM at 16 kHz and is checked for format,
duration, byte size and truncation. Failed output is removed. The owning pipeline
must manage the temporary directory for complete input/output cleanup.

URL/audio unit tests use controlled files and mock only the FFmpeg subprocess
boundary. They do not demonstrate a real YouTube download or installed FFmpeg.
The download and complete generation pipeline are still in implementation.

## Download transport

The download module uses pinned yt-dlp and yt-dlp-ejs releases plus Node 22 or
newer in PATH. It enables only the YouTube extractor, selects direct HTTPS media
instead of manifests and downloads one normalized video. No personal cookies,
proxy environment, remote EJS components, external downloaders or persistent
metadata cache are used. Current defaults are 15-minute videos, 100 MB download
size, a 15-second socket timeout and a 120-second progress deadline; no retries.
Live/upcoming videos and final metadata without duration are rejected.

All yt-dlp requests use a dedicated urllib transport. Only youtube.com subdomains,
googlevideo.com subdomains and youtubei.googleapis.com are allowed over HTTPS on
443. DNS answers must all be globally routable. Connections use the checked
numeric address while standard TLS still verifies the original hostname. Redirects
pass through the same checks; HTTP downgrade, file, FTP and data transports are
unavailable. This adapter deliberately uses pinned yt-dlp transport APIs and needs
regression testing when yt-dlp is upgraded.

Progress deadlines do not interrupt a stalled DNS lookup or JavaScript challenge.
A hard whole-job deadline and temporary-directory cleanup still need integration
in the synchronous generation orchestration. No real YouTube download has yet
been performed; tests cover controlled DNS/socket boundaries and actual yt-dlp
transport construction. Runtime transport compatibility remains to be verified.

## Local Whisper and synchronous process limits

Runtime requirements include OpenAI Whisper 20250625 and PyTorch 2.15.0+cpu.
The latter is installed from the official PyTorch CPU wheel index; Linux Python
3.12 wheels exist for AMD64 and ARM64. This establishes package availability,
not a successful ARM64 container build. Whisper's upstream Linux dependencies
include Triton on x86_64, but CUDA and an NVIDIA GPU are not required.

The transcription module explicitly loads models on CPU and disables FP16 and
verbose transcript output. Model name, writable persistent cache directory, CPU
thread count and transcript limit are supplied by the pipeline. The default
thread count is two; transcripts shorter than 20 characters or longer than
120,000 characters are rejected. Whisper downloads missing official model weights
into the supplied cache on first use; subsequent loads reuse those files. Keep
this directory outside a read-only container root. `tiny` is useful for initial
resource checks; `base` is the intended starting configuration. Larger models
require separately measured RAM and processing time; Pi performance is unverified.

The local processing session uses one reusable spawned Python child and returns
its result synchronously. It is internal to the application, with no additional
service, queue or async HTTP API. Successful tasks retain the loaded model;
failed/timed-out tasks discard the process. A parent deadline terminates the
process group, including FFmpeg/Node descendants. A subsequent request starts a
fresh child. This boundary also covers stalled native inference and DNS work,
which cannot be reliably interrupted by progress callbacks alone. Use one
Gunicorn worker to avoid duplicate model allocations; complete pipeline and
cross-process concurrency integration are still pending.

Tests exercise real process reuse, timeout termination, failure sanitization and
recovery; transcription tests replace the heavy model boundary. Real speech
transcription and full pipeline integration remain separate checks.

## Gemini boundary and credentials

The Gemini module uses the official `google-genai` SDK with the stable
`gemini-3.8-flash` model as its explicit default. The model can be passed by the
pipeline; there is no automatic fallback or model upgrade. Official model and
pricing references checked on 2026-11-25:
[model](https://aistudio.google.com/docs/models/gemini-3.8-flash),
[pricing](https://aistudio.google.com/docs/pricing),
[structured output](https://aistudio.google.com/docs/structured-output).
A Free Tier is documented, but account eligibility, quotas and future pricing
must be checked by the operator. No billing or API service is activated here.

The credential resolver accepts an explicit environment value or an explicitly
configured secret-file path. Both supplied together are an error; neither source
silently overrides the other. Missing, unreadable, empty or oversized credentials
fail without revealing paths or contents. The file is read at request time and
bounded to 4096 characters. The pipeline will wire these inputs to
`GEMINI_API_KEY` and `GEMINI_API_KEY_FILE`; the preferred production file is
`/run/secrets/gemini_api_key`, provisioned separately by the operator. No real key
belongs in this repository, development VM, CI or review archive.

Only transcript text is sent to `generativelanguage.googleapis.com`; no audio,
user identity, database records or authentication cookies are included. The
client explicitly disables Vertex/Enterprise autodiscovery, environment proxy
inheritance and automatic retries. A call has a 60-second SDK timeout by default,
8192 output-token limit and no tools, search or URL context. Transcript instructions
are treated as untrusted source material, separated from the system instruction.
The full pipeline's parent deadline will additionally bound the call.

Gemini receives a JSON schema, but returned JSON is independently checked with
strict Pydantic types, bounded plain text, exactly ten questions, four distinct
options and an exact answer match. Blocked/truncated finish states, malformed or
oversized responses are rejected. No quiz is fabricated on failure. Tests use
controlled SDK responses and fixture credentials; no real Gemini request has
been made. Environment wiring, atomic persistence and POST integration follow
in the next implementation phase.
