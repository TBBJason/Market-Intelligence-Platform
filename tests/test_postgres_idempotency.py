"""Optional end-to-end persistence test against a disposable PostgreSQL database."""

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from market_intelligence.database.models import (
    CompanyProfile,
    FactRecord,
    SourceDocument,
    SourceRegistry,
)
from market_intelligence.ingestion.schemas import (
    GitHubFetchResult,
    GitHubOrganization,
    ResponseMetadata,
)
from market_intelligence.ingestion.service import GitHubIngestionService

pytestmark = pytest.mark.integration
DATABASE_URL = os.getenv("TEST_DATABASE_URL")


class StaticConnector:
    def __init__(self, result: GitHubFetchResult) -> None:
        self.result = result

    def fetch(self, organization: str, *, etag: str | None = None) -> GitHubFetchResult:
        return self.result


def _result(payload: dict[str, Any]) -> GitHubFetchResult:
    return GitHubFetchResult(
        status="changed",
        organization=GitHubOrganization.model_validate(payload),
        raw_payload=payload,
        metadata=ResponseMetadata(
            status_code=200,
            source_url="https://api.github.com/orgs/example-infrastructure",
            request_started_at=datetime(2026, 9, 13, 11, 59, tzinfo=UTC),
            retrieved_at=datetime(2026, 9, 13, 12, 0, tzinfo=UTC),
            content_type="application/json",
            etag='"same-content"',
        ),
    )


@pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not configured")
def test_repeated_payload_creates_one_document_profile_and_fact_set(
    github_payload: dict[str, Any],
) -> None:
    assert DATABASE_URL is not None
    engine = create_engine(DATABASE_URL)
    bootstrap = (Path(__file__).parents[1] / "sql" / "001_initial.sql").read_text()
    database_url = make_url(DATABASE_URL)
    with psycopg.connect(
        host=database_url.host,
        port=database_url.port,
        dbname=database_url.database,
        user=database_url.username,
        password=database_url.password,
        autocommit=True,
    ) as connection:
        connection.execute(bootstrap)

    with Session(engine) as session:
        session.execute(text("TRUNCATE raw.source_registry CASCADE"))
        source = SourceRegistry(
            source_type="github_org",
            external_key="example-infrastructure",
            company_slug="example-infrastructure",
            source_url="https://api.github.com/orgs/example-infrastructure",
            collection_method="official_api",
            terms_url="https://docs.github.com/en/site-policy/github-terms/github-terms-of-service",
            review_status="approved",
            reviewed_at=datetime(2026, 9, 13, tzinfo=UTC),
            reviewed_by="automated-test",
            attribution_text="Source: GitHub organization API",
            retention_mode="full_response",
            enabled=True,
        )
        session.add(source)
        session.commit()

        connector = StaticConnector(_result(github_payload))
        service = GitHubIngestionService(session, connector)  # type: ignore[arg-type]
        first = service.ingest("example-infrastructure")
        second = service.ingest("example-infrastructure")

        assert first.status == "inserted"
        assert second.status == "unchanged"
        assert session.scalar(select(func.count()).select_from(SourceDocument)) == 1
        assert session.scalar(select(func.count()).select_from(CompanyProfile)) == 1
        assert session.scalar(select(func.count()).select_from(FactRecord)) == 11
