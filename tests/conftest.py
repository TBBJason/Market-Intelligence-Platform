"""Shared synthetic fixtures; no fixture is represented as a real company claim."""

from collections.abc import Iterator
from typing import Any

import pytest


@pytest.fixture
def github_payload() -> dict[str, Any]:
    return {
        "id": 12345,
        "login": "example-infrastructure",
        "name": "Example Infrastructure",
        "description": "Synthetic organization used only for automated tests.",
        "blog": "https://example.com",
        "html_url": "https://github.com/example-infrastructure",
        "location": "Example City",
        "public_repos": 12,
        "followers": 34,
        "created_at": "2020-01-02T03:04:05Z",
        "updated_at": "2026-01-02T03:04:05Z",
        "type": "Organization",
        "ignored_external_field": "retained in raw payload, intentionally not normalized",
    }


@pytest.fixture
def no_database_session() -> Iterator[object]:
    """FastAPI override token for routes whose repository calls are monkeypatched."""

    yield object()
