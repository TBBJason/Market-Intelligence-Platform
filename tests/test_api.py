"""User-facing API tests for citations, evidence types, and missing data."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from market_intelligence.api.main import create_app
from market_intelligence.database.repository import MarketIntelligenceRepository
from market_intelligence.database.session import get_session

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
COMPANY_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
DOCUMENT_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")


def _client() -> TestClient:
    app = create_app()

    def session_override() -> object:
        return object()

    app.dependency_overrides[get_session] = session_override
    return TestClient(app)


def _company() -> SimpleNamespace:
    return SimpleNamespace(
        id=COMPANY_ID,
        slug="example-infrastructure",
        canonical_name="Example Infrastructure",
        website_url="https://example.com",
    )


def _profile() -> SimpleNamespace:
    return SimpleNamespace(
        display_name="Example Infrastructure",
        description="Synthetic API test profile.",
        website_url="https://example.com",
        github_url="https://github.com/example-infrastructure",
        location=None,
        public_repos=12,
        followers=34,
        source_created_at=NOW,
        source_updated_at=NOW,
    )


def _document() -> SimpleNamespace:
    return SimpleNamespace(
        id=DOCUMENT_ID,
        source_url="https://api.github.com/orgs/example-infrastructure",
        retrieved_at=NOW,
        attribution_text="Source: GitHub organization API",
    )


def test_company_detail_cites_every_fact(monkeypatch: pytest.MonkeyPatch) -> None:
    fact = SimpleNamespace(
        evidence_type="direct_fact",
        predicate="github.organization.description",
        value="Synthetic API test profile.",
        extraction_method="pydantic_field_mapping",
        method_version="github_org_v1",
        observed_at=NOW,
    )
    monkeypatch.setattr(MarketIntelligenceRepository, "get_company_by_slug", lambda *_: _company())
    monkeypatch.setattr(
        MarketIntelligenceRepository,
        "latest_profile",
        lambda *_: (_profile(), _document()),
    )
    monkeypatch.setattr(MarketIntelligenceRepository, "facts_for_document", lambda *_: [fact])

    response = _client().get("/v1/companies/example-infrastructure")

    assert response.status_code == 200
    body = response.json()
    assert body["citation"]["source_document_id"] == str(DOCUMENT_ID)
    assert body["facts"][0]["evidence_type"] == "direct_fact"
    assert body["facts"][0]["citation"] == body["citation"]
    assert body["profile"]["description"] == "Synthetic API test profile."


def test_company_without_profile_is_explicitly_uncited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(MarketIntelligenceRepository, "get_company_by_slug", lambda *_: _company())
    monkeypatch.setattr(MarketIntelligenceRepository, "latest_profile", lambda *_: None)

    response = _client().get("/v1/companies/example-infrastructure")

    assert response.status_code == 200
    body = response.json()
    assert body["citation"] is None
    assert body["profile"] is None
    assert body["facts"] == []


def test_unknown_company_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MarketIntelligenceRepository, "get_company_by_slug", lambda *_: None)

    response = _client().get("/v1/companies/unknown")

    assert response.status_code == 404
    assert response.json() == {"detail": "Company not found"}
