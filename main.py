"""Точка входа для ASGI-серверов: uvicorn main:app."""
from app.web import app

__all__ = ["app"]
