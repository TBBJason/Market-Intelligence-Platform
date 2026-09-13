"""ORM mappings for evidence ingestion and normalized company profiles."""

import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative metadata root."""


json_type = JSON().with_variant(JSONB(), "postgresql")


class SourceRegistry(Base):
    """Reviewed allowlist entry for one external source."""

    __tablename__ = "source_registry"
    __table_args__ = (
        UniqueConstraint("source_type", "external_key", name="uq_source_registry_type_key"),
        CheckConstraint(
            "review_status IN ('pending', 'approved', 'rejected', 'review_required')",
            name="ck_source_review_status",
        ),
        CheckConstraint(
            "retention_mode IN ('full_response', 'metadata_only')",
            name="ck_source_retention_mode",
        ),
        CheckConstraint(
            "review_status <> 'approved' OR (reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL)",
            name="ck_approved_source_has_review",
        ),
        {"schema": "raw"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    external_key: Mapped[str] = mapped_column(String, nullable=False)
    company_slug: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    collection_method: Mapped[str] = mapped_column(String, nullable=False)
    terms_url: Mapped[str] = mapped_column(Text, nullable=False)
    robots_url: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String)
    attribution_text: Mapped[str] = mapped_column(Text, nullable=False)
    retention_mode: Mapped[str] = mapped_column(String, default="metadata_only", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_retrieval_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_http_status: Mapped[int | None] = mapped_column(Integer)
    etag: Mapped[str | None] = mapped_column(String)
    rate_limit_remaining: Mapped[int | None] = mapped_column(Integer)
    rate_limit_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SourceDocument(Base):
    """Content-addressed source response and retrieval metadata."""

    __tablename__ = "source_documents"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "external_id", "content_hash", name="uq_source_document_content"
        ),
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="ck_sha256_hex"),
        CheckConstraint("http_status BETWEEN 200 AND 299", name="ck_successful_document"),
        Index("ix_source_documents_source_retrieved", "source_id", "retrieved_at"),
        {"schema": "raw"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw.source_registry.id"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[dict[str, Any] | None] = mapped_column(json_type)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    etag: Mapped[str | None] = mapped_column(String)
    last_modified: Mapped[str | None] = mapped_column(String)
    attribution_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_headers: Mapped[dict[str, Any]] = mapped_column(
        json_type, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IngestionRun(Base):
    """Observable ingestion attempt, including explicit failures."""

    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('started', 'succeeded', 'unchanged', 'failed')",
            name="ck_ingestion_run_status",
        ),
        CheckConstraint(
            "status <> 'failed' OR (error_type IS NOT NULL AND error_message IS NOT NULL)",
            name="ck_failed_run_has_error",
        ),
        Index("ix_ingestion_runs_source_started", "source_id", "started_at"),
        {"schema": "raw"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw.source_registry.id"), nullable=False
    )
    orchestration_run_id: Mapped[str | None] = mapped_column(String)
    requested_as_of: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String, default="started", nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw.source_documents.id")
    )
    error_type: Mapped[str | None] = mapped_column(String)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Company(Base):
    """Stable normalized company identity."""

    __tablename__ = "companies"
    __table_args__ = (
        CheckConstraint("slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'", name="ck_company_slug"),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    canonical_name: Mapped[str] = mapped_column(String, nullable=False)
    website_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ExternalIdentifier(Base):
    """Source identifier attached to a stable company."""

    __tablename__ = "external_identifiers"
    __table_args__ = (
        UniqueConstraint("source_type", "external_id", name="uq_external_identifier"),
        UniqueConstraint("company_id", "source_type", name="uq_company_source_identifier"),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("core.companies.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CompanyProfile(Base):
    """Versioned normalized profile derived directly from one source document."""

    __tablename__ = "company_profiles"
    __table_args__ = (
        CheckConstraint("public_repos >= 0 AND followers >= 0", name="ck_profile_counts"),
        Index("ix_company_profiles_company_valid", "company_id", "valid_from"),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("core.companies.id", ondelete="CASCADE"), nullable=False
    )
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw.source_documents.id"), unique=True, nullable=False
    )
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    website_url: Mapped[str | None] = mapped_column(Text)
    github_url: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(String)
    public_repos: Mapped[int] = mapped_column(Integer, nullable=False)
    followers: Mapped[int] = mapped_column(Integer, nullable=False)
    source_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FactRecord(Base):
    """Typed assertion with mandatory citation for directly retrieved facts."""

    __tablename__ = "fact_records"
    __table_args__ = (
        UniqueConstraint("source_document_id", "predicate", name="uq_fact_per_document"),
        CheckConstraint(
            "evidence_type IN ('direct_fact', 'derived_classification', 'model_interpretation')",
            name="ck_fact_evidence_type",
        ),
        CheckConstraint(
            "evidence_type <> 'direct_fact' OR source_document_id IS NOT NULL",
            name="ck_direct_fact_citation",
        ),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("core.companies.id", ondelete="CASCADE"), nullable=False
    )
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw.source_documents.id")
    )
    evidence_type: Mapped[str] = mapped_column(String, nullable=False)
    predicate: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[Any] = mapped_column(json_type, nullable=False)
    extraction_method: Mapped[str] = mapped_column(String, nullable=False)
    method_version: Mapped[str] = mapped_column(String, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DocumentChunk(Base):
    """Reserved pgvector relation; embeddings are intentionally not produced yet."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "source_document_id", "chunk_index", "content_hash", name="uq_document_chunk"
        ),
        CheckConstraint("chunk_index >= 0", name="ck_chunk_index_nonnegative"),
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="ck_chunk_sha256_hex"),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw.source_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector())
    embedding_model: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
