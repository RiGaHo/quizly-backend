# syntax=docker/dockerfile:1
FROM node:24.22.3-trixie-slim AS javascript
FROM python:3.12.16-slim-trixie AS dependencies
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY requirements.txt requirements-ai.txt ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip==26.3 \
    && /opt/venv/bin/pip install -r requirements.txt

FROM python:3.12.16-slim-trixie AS runtime
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DJANGO_READ_DOTENV=false DATABASE_PATH=/data/db.sqlite3 \
    WHISPER_CACHE_DIR=/models HOME=/tmp \
    OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 quizly \
    && useradd --uid 10001 --gid 10001 --no-create-home quizly \
    && install -d -o 10001 -g 10001 /data /models
COPY --from=javascript /usr/local/bin/node /usr/local/bin/node
COPY --from=dependencies /opt/venv /opt/venv
WORKDIR /app
COPY manage.py ./
COPY config/ ./config/
COPY accounts/ ./accounts/
COPY quizzes/ ./quizzes/
COPY generation/ ./generation/
COPY docker/entrypoint.sh docker/gunicorn.conf.py ./docker/
RUN chmod 0555 /app/docker/entrypoint.sh
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--config", "/app/docker/gunicorn.conf.py"]
