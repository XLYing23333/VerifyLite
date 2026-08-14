"""Gunicorn WSGI entry point for VerifyLite."""

from app import create_app

app = create_app()
