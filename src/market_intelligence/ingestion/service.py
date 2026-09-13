"""Source-neutral ingestion transaction boundary for the GitHub vertical slice."""

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime

import structlog
from sqlalchemy.orm import Session

from market_intelligence.database.repository import MarketIntelligenceRepository
from market_intelligence.ingestion.github import (
    GitHubOrganizationConnector,
    SourceRateLimitError,
)
from market_intelligence.ingestion.schemas import IngestionOutcome

logger = structlog.get_logger(__name__)


def canonical_json_hash(payload: Mapping[str, object]) -> str:
    """Return a stable SHA-256 over semantic JSON rather than response formatting."""

    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class GitHubIngestionService:
    """Coordinate review enforcement, HTTP retrieval, and atomic normalization."""

    def __init__(
        self,
        session: Session,
        connector: GitHubOrganizationConnector,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._session = session
        self._repository = MarketIntelligenceRepository(session)
        self._connector = connector
        self._clock = clock

    def ingest(
        self,
        external_key: str,
        *,
        requested_as_of: date | None = None,
        orchestration_run_id: str | None = None,
    ) -> IngestionOutcome:
        """Ingest one registry-approved organization; unchanged content creates no version."""

        source = self._repository.get_approved_source("github_org", external_key)
        run = self._repository.start_run(
            source.id,
            requested_as_of=requested_as_of,
            orchestration_run_id=orchestration_run_id,
        )
        run_id = run.id
        source_id = source.id
        previous_etag = source.etag
        self._session.commit()

        log = logger.bind(source_id=str(source_id), run_id=str(run_id), external_key=external_key)
        log.info("ingestion_started", requested_as_of=requested_as_of)

        try:
            result = self._connector.fetch(external_key, etag=previous_etag)
            if str(result.metadata.source_url).rstrip("/") != source.source_url.rstrip("/"):
                raise PermissionError("Retrieved URL does not match the reviewed source URL")
            locked_source = self._repository.lock_approved_source(source_id)
            promote = self._repository.should_promote(
                locked_source, result.metadata.request_started_at
            )
            if result.status == "not_modified" or not promote:
                document, company = self._repository.persist_not_modified(
                    locked_source, run_id, result, promote=promote
                )
                self._session.commit()
                outcome = IngestionOutcome(
                    status="unchanged",
                    source_id=source_id,
                    run_id=run_id,
                    document_id=document.id if document else None,
                    company_id=company.id if company else None,
                    content_hash=document.content_hash if document else None,
                    observed_at=result.metadata.retrieved_at,
                )
                log.info(
                    "ingestion_unchanged",
                    reason=("http_304" if result.status == "not_modified" else "stale_response"),
                    document_id=str(document.id) if document else None,
                )
                return outcome

            if result.raw_payload is None:
                raise ValueError("Changed source result had no raw payload")
            content_hash = canonical_json_hash(result.raw_payload)
            status, document, company = self._repository.persist_changed(
                locked_source, run_id, result, content_hash, promote=promote
            )
            self._session.commit()
            outcome = IngestionOutcome(
                status=status,
                source_id=source_id,
                run_id=run_id,
                document_id=document.id,
                company_id=company.id if company else None,
                content_hash=content_hash,
                observed_at=result.metadata.retrieved_at,
            )
            log.info(
                "ingestion_completed",
                status=status,
                document_id=str(document.id),
                company_id=str(company.id) if company else None,
                content_hash=content_hash,
            )
            return outcome
        except Exception as exc:
            self._session.rollback()
            try:
                if isinstance(exc, SourceRateLimitError):
                    metadata = exc.metadata
                    self._repository.record_rate_limit(
                        source_id,
                        checked_at=metadata.retrieved_at,
                        status_code=metadata.status_code,
                        remaining=metadata.rate_limit_remaining,
                        reset_at=metadata.rate_limit_reset_at,
                    )
                self._repository.mark_run_failed(run_id, exc, finished_at=self._clock())
                self._session.commit()
            except Exception as persistence_error:
                self._session.rollback()
                log.error(
                    "failure_record_persistence_failed",
                    error_type=type(persistence_error).__name__,
                )
            log.error("ingestion_failed", error_type=type(exc).__name__)
            raise
