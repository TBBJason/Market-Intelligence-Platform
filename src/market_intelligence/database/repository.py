"""Transactional repository for reviewed-source ingestion and company reads."""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from market_intelligence.database.models import (
    Company,
    CompanyProfile,
    ExternalIdentifier,
    FactRecord,
    IngestionRun,
    SourceDocument,
    SourceRegistry,
)
from market_intelligence.ingestion.schemas import GitHubFetchResult, GitHubOrganization


class SourceNotApprovedError(PermissionError):
    """A source is missing, disabled, or lacks a current approval."""


class MarketIntelligenceRepository:
    """Keep SQL and transaction-aware persistence outside source connectors."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_approved_source(self, source_type: str, external_key: str) -> SourceRegistry:
        """Resolve only enabled, explicitly approved source-registry entries."""

        source = self.session.scalar(
            select(SourceRegistry).where(
                SourceRegistry.source_type == source_type,
                SourceRegistry.external_key == external_key,
                SourceRegistry.enabled.is_(True),
                SourceRegistry.review_status == "approved",
            )
        )
        if source is None:
            raise SourceNotApprovedError(
                f"Source {source_type}/{external_key} is not enabled and approved"
            )
        return source

    def lock_approved_source(self, source_id: uuid.UUID) -> SourceRegistry:
        """Serialize writes and fail closed if approval changed during external I/O."""

        source = self.session.scalar(
            select(SourceRegistry)
            .where(
                SourceRegistry.id == source_id,
                SourceRegistry.enabled.is_(True),
                SourceRegistry.review_status == "approved",
            )
            .with_for_update()
        )
        if source is None:
            raise SourceNotApprovedError(f"Source {source_id} is no longer enabled and approved")
        return source

    @staticmethod
    def should_promote(source: SourceRegistry, request_started_at: datetime) -> bool:
        """Prevent an older in-flight request from replacing newer current state."""

        return (
            source.last_successful_retrieval_at is None
            or request_started_at >= source.last_successful_retrieval_at
        )

    def start_run(
        self,
        source_id: uuid.UUID,
        *,
        requested_as_of: date | None,
        orchestration_run_id: str | None,
    ) -> IngestionRun:
        run = IngestionRun(
            source_id=source_id,
            requested_as_of=requested_as_of,
            orchestration_run_id=orchestration_run_id,
            status="started",
        )
        self.session.add(run)
        self.session.flush()
        return run

    def mark_run_failed(
        self, run_id: uuid.UUID, error: Exception, *, finished_at: datetime
    ) -> None:
        """Persist bounded failure details; external response bodies are never included."""

        run = self.session.get(IngestionRun, run_id)
        if run is None:
            return
        run.status = "failed"
        run.finished_at = finished_at
        run.error_type = type(error).__name__
        run.error_message = self._safe_error_message(error)

    def record_rate_limit(
        self,
        source_id: uuid.UUID,
        *,
        checked_at: datetime,
        status_code: int,
        remaining: int | None,
        reset_at: datetime | None,
    ) -> None:
        source = self.session.get(SourceRegistry, source_id)
        if source is None:
            return
        source.last_checked_at = checked_at
        source.last_http_status = status_code
        source.rate_limit_remaining = remaining
        source.rate_limit_reset_at = reset_at

    @staticmethod
    def _safe_error_message(error: Exception) -> str:
        if isinstance(error, SQLAlchemyError):
            return "Database operation failed; parameters hidden"
        if error.__class__.__module__.startswith("market_intelligence") or isinstance(
            error, PermissionError
        ):
            return str(error)[:500]
        return "Ingestion failed; inspect the structured error type"

    def persist_not_modified(
        self,
        source: SourceRegistry,
        run_id: uuid.UUID,
        result: GitHubFetchResult,
        *,
        promote: bool,
    ) -> tuple[SourceDocument | None, Company | None]:
        checked_at = result.metadata.retrieved_at
        if source.last_checked_at is None or checked_at > source.last_checked_at:
            source.last_checked_at = checked_at
        if promote:
            source.last_http_status = result.metadata.status_code
            source.etag = result.metadata.etag or source.etag
            source.rate_limit_remaining = result.metadata.rate_limit_remaining
            source.rate_limit_reset_at = result.metadata.rate_limit_reset_at
            source.updated_at = checked_at

        document = self.session.scalar(
            select(SourceDocument)
            .where(SourceDocument.source_id == source.id)
            .order_by(SourceDocument.retrieved_at.desc(), SourceDocument.id.desc())
            .limit(1)
        )
        company = (
            self._company_for_external_id(source.source_type, document.external_id)
            if document is not None
            else None
        )
        run = self._require_run(run_id)
        run.status = "unchanged"
        run.finished_at = checked_at
        run.document_id = document.id if document is not None else None
        return document, company

    def persist_changed(
        self,
        source: SourceRegistry,
        run_id: uuid.UUID,
        result: GitHubFetchResult,
        content_hash: str,
        *,
        promote: bool,
    ) -> tuple[str, SourceDocument, Company | None]:
        """Persist a validated response and normalized profile exactly once by hash."""

        organization, raw_payload = self._require_changed_payload(result)
        checked_at = result.metadata.retrieved_at
        existing = self.session.scalar(
            select(SourceDocument).where(
                SourceDocument.source_id == source.id,
                SourceDocument.external_id == str(organization.id),
                SourceDocument.content_hash == content_hash,
            )
        )

        if source.last_checked_at is None or checked_at > source.last_checked_at:
            source.last_checked_at = checked_at
        if promote:
            source.last_successful_retrieval_at = checked_at
            source.last_http_status = result.metadata.status_code
            source.etag = result.metadata.etag or source.etag
            source.rate_limit_remaining = result.metadata.rate_limit_remaining
            source.rate_limit_reset_at = result.metadata.rate_limit_reset_at
            source.updated_at = checked_at
        run = self._require_run(run_id)

        if existing is not None:
            if checked_at > existing.last_checked_at:
                existing.last_checked_at = checked_at
            run.status = "unchanged"
            run.finished_at = checked_at
            run.document_id = existing.id
            company = self._company_for_external_id("github_org", str(organization.id))
            return "unchanged", existing, company

        document = SourceDocument(
            source_id=source.id,
            external_id=str(organization.id),
            source_url=str(result.metadata.source_url),
            content_type=result.metadata.content_type or "application/json",
            content_hash=content_hash,
            content=raw_payload if source.retention_mode == "full_response" else None,
            retrieved_at=checked_at,
            last_checked_at=checked_at,
            http_status=result.metadata.status_code,
            etag=result.metadata.etag,
            last_modified=result.metadata.last_modified,
            attribution_text=source.attribution_text,
            response_headers={
                "etag": result.metadata.etag,
                "last_modified": result.metadata.last_modified,
                "rate_limit_remaining": result.metadata.rate_limit_remaining,
                "rate_limit_reset_at": (
                    result.metadata.rate_limit_reset_at.isoformat()
                    if result.metadata.rate_limit_reset_at
                    else None
                ),
            },
        )
        self.session.add(document)
        self.session.flush()

        if not promote:
            raise ValueError("Stale responses must not be persisted as new documents")

        company = self._resolve_company(source, organization)
        profile = CompanyProfile(
            company_id=company.id,
            source_document_id=document.id,
            display_name=organization.display_name,
            description=organization.description,
            website_url=str(organization.blog) if organization.blog else None,
            github_url=str(organization.html_url),
            location=organization.location,
            public_repos=organization.public_repos,
            followers=organization.followers,
            source_created_at=organization.created_at,
            source_updated_at=organization.updated_at,
            valid_from=checked_at,
        )
        self.session.add(profile)
        self._add_direct_facts(company.id, document.id, organization, checked_at)

        run.status = "succeeded"
        run.finished_at = checked_at
        run.document_id = document.id
        return "inserted", document, company

    def company_query(self, query: str | None = None) -> Select[tuple[Company]]:
        statement = select(Company)
        if query:
            escaped = query.replace("%", r"\%").replace("_", r"\_")
            pattern = f"%{escaped}%"
            statement = statement.where(
                or_(Company.canonical_name.ilike(pattern), Company.slug.ilike(pattern))
            )
        return statement.order_by(Company.canonical_name.asc(), Company.id.asc())

    def list_companies(
        self,
        *,
        query: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Company], int]:
        """Return a stable page and total count for the same filtered statement."""

        statement = self.company_query(query)
        total = self.session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        companies = list(self.session.scalars(statement.limit(limit).offset(offset)))
        return companies, int(total or 0)

    def get_company_by_slug(self, slug: str) -> Company | None:
        return self.session.scalar(select(Company).where(Company.slug == slug))

    def latest_profile(self, company_id: uuid.UUID) -> tuple[CompanyProfile, SourceDocument] | None:
        row = self.session.execute(
            select(CompanyProfile, SourceDocument)
            .join(SourceDocument, SourceDocument.id == CompanyProfile.source_document_id)
            .where(CompanyProfile.company_id == company_id)
            .order_by(CompanyProfile.valid_from.desc(), CompanyProfile.id.desc())
            .limit(1)
        ).one_or_none()
        return row.tuple() if row is not None else None

    def facts_for_document(self, document_id: uuid.UUID) -> list[FactRecord]:
        return list(
            self.session.scalars(
                select(FactRecord)
                .where(FactRecord.source_document_id == document_id)
                .order_by(FactRecord.predicate.asc())
            )
        )

    def _require_run(self, run_id: uuid.UUID) -> IngestionRun:
        run = self.session.get(IngestionRun, run_id)
        if run is None:
            raise LookupError(f"Ingestion run {run_id} not found")
        return run

    @staticmethod
    def _require_changed_payload(
        result: GitHubFetchResult,
    ) -> tuple[GitHubOrganization, dict[str, Any]]:
        if result.status != "changed" or result.organization is None or result.raw_payload is None:
            raise ValueError("Changed GitHub result is missing its validated payload")
        return result.organization, result.raw_payload

    def _company_for_external_id(self, source_type: str, external_id: str) -> Company | None:
        return self.session.scalar(
            select(Company)
            .join(ExternalIdentifier, ExternalIdentifier.company_id == Company.id)
            .where(
                ExternalIdentifier.source_type == source_type,
                ExternalIdentifier.external_id == external_id,
            )
        )

    def _resolve_company(self, source: SourceRegistry, organization: GitHubOrganization) -> Company:
        external_id = str(organization.id)
        company = self._company_for_external_id(source.source_type, external_id)
        if company is None:
            company = self.session.scalar(
                select(Company).where(Company.slug == source.company_slug)
            )
        if company is None:
            company = Company(
                slug=source.company_slug,
                canonical_name=organization.display_name,
                website_url=str(organization.blog) if organization.blog else None,
            )
            self.session.add(company)
            self.session.flush()
        else:
            company.canonical_name = organization.display_name
            company.website_url = str(organization.blog) if organization.blog else None
            company.updated_at = datetime.now(UTC)

        identifier_count = self.session.scalar(
            select(func.count())
            .select_from(ExternalIdentifier)
            .where(
                ExternalIdentifier.source_type == source.source_type,
                ExternalIdentifier.external_id == external_id,
            )
        )
        if not identifier_count:
            self.session.add(
                ExternalIdentifier(
                    company_id=company.id,
                    source_type=source.source_type,
                    external_id=external_id,
                )
            )
        return company

    def _add_direct_facts(
        self,
        company_id: uuid.UUID,
        document_id: uuid.UUID,
        organization: GitHubOrganization,
        observed_at: datetime,
    ) -> None:
        values = organization.model_dump(mode="json")
        for predicate in (
            "id",
            "login",
            "name",
            "description",
            "blog",
            "html_url",
            "location",
            "public_repos",
            "followers",
            "created_at",
            "updated_at",
        ):
            self.session.add(
                FactRecord(
                    company_id=company_id,
                    source_document_id=document_id,
                    evidence_type="direct_fact",
                    predicate=f"github.organization.{predicate}",
                    value=values[predicate],
                    extraction_method="pydantic_field_mapping",
                    method_version="github_org_v1",
                    observed_at=observed_at,
                )
            )
