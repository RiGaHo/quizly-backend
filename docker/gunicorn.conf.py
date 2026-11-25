"""Serve synchronous AI requests with a bounded single-model worker."""

import os

bind = "0.0.0.0:8000"
workers = int(os.environ.get("GUNICORN_WORKERS", "1"))
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", "2"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "960"))
graceful_timeout = 30
keepalive = 5
worker_tmp_dir = "/tmp"
accesslog = None
errorlog = "-"
# The deployment proxy trust boundary is configured explicitly in Django.
forwarded_allow_ips = ""
