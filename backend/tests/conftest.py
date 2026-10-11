from __future__ import annotations

import pytest
from backend.config import settings


@pytest.fixture(autouse=True)
def default_disable_groq_api(monkeypatch):
    """Ensure tests run deterministically and don't make outbound API calls unless explicitly mocked."""
    monkeypatch.setattr(settings, "groq_api_key", "")
