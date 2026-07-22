"""Compatibility entrypoint for local uvicorn commands.

The backend application lives at ``backend.app.main``. This shim keeps
``uvicorn app.main:app`` working when the command is launched from the
repository root.
"""

from backend.app.main import app

__all__ = ["app"]
