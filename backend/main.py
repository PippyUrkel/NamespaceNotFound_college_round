from __future__ import annotations

try:
    from backend.app.main import app
except ModuleNotFoundError:  # pragma: no cover
    from app.main import app
