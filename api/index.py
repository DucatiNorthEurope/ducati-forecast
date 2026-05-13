"""Vercel function entry. Mounts the Flask app under /dashboard so Ross's
static index.html stays at the project root."""

import os
os.environ.setdefault("URL_PREFIX", "/dashboard")

from app.app import app  # noqa: F401  Vercel detects the `app` symbol as the WSGI callable
