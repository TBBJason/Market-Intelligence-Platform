"""Public API contracts with explicit evidence and missing-value semantics."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class EvidenceType(StrEnum):
    DIRECT_FACT = "direct_fact"
    DERIVED_CLASSIFICATION = "derived_classification"
    MODEL_INTERPRETATION = "model_interpretation"


class Citation(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_document_id: uuid.UUID
    source_url: HttpUrl
    retrieved_at: datetime
    attribution: str


class CompanySummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    slug: str
    canonical_name: str
    website_url: HttpUrl | None
    citation: Citation | None = Field(
        description="Null only when no source-backed profile exists; no value is fabricated."
    )


class CompanyListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[CompanySummary]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class CompanyProfileData(BaseModel):
    model_config = ConfigDict(frozen=True)

    display_name: str
    description: str | None
    website_url: HttpUrl | None
    github_url: HttpUrl
    location: str | None
    public_repos: int = Field(ge=0)
    followers: int = Field(ge=0)
    source_created_at: datetime
    source_updated_at: datetime


class FactResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_type: EvidenceType
    predicate: str
    value: Any
    extraction_method: str
    method_version: str
    observed_at: datetime
    citation: Citation


class CompanyDetailResponse(CompanySummary):
    profile: CompanyProfileData | None
    facts: list[FactResponse]


class HealthResponse(BaseModel):
    status: str
    database: str
    version: str
