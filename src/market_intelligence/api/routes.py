"""Read-only health and normalized company endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from market_intelligence import __version__
from market_intelligence.api.schemas import (
    Citation,
    CompanyDetailResponse,
    CompanyListResponse,
    CompanyProfileData,
    CompanySummary,
    FactResponse,
    HealthResponse,
)
from market_intelligence.database.models import Company, CompanyProfile, SourceDocument
from market_intelligence.database.repository import MarketIntelligenceRepository
from market_intelligence.database.session import get_session

router = APIRouter()
SessionDependency = Annotated[Session, Depends(get_session)]


def _citation(document: SourceDocument) -> Citation:
    return Citation(
        source_document_id=document.id,
        source_url=document.source_url,
        retrieved_at=document.retrieved_at,
        attribution=document.attribution_text,
    )


def _summary(
    company: Company,
    latest: tuple[CompanyProfile, SourceDocument] | None,
) -> CompanySummary:
    return CompanySummary(
        id=company.id,
        slug=company.slug,
        canonical_name=company.canonical_name,
        website_url=company.website_url,
        citation=_citation(latest[1]) if latest else None,
    )


@router.get("/health", response_model=HealthResponse, tags=["operations"])
def health(session: SessionDependency) -> HealthResponse:
    """Report database reachability rather than returning a false healthy state."""

    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from exc
    return HealthResponse(status="ok", database="ok", version=__version__)


@router.get("/v1/companies", response_model=CompanyListResponse, tags=["companies"])
def list_companies(
    session: SessionDependency,
    query: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CompanyListResponse:
    """Search normalized company identities and include current source citations."""

    repository = MarketIntelligenceRepository(session)
    companies, total = repository.list_companies(query=query, limit=limit, offset=offset)
    items = [_summary(company, repository.latest_profile(company.id)) for company in companies]
    return CompanyListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/v1/companies/{slug}",
    response_model=CompanyDetailResponse,
    tags=["companies"],
)
def get_company(slug: str, session: SessionDependency) -> CompanyDetailResponse:
    """Return the latest normalized profile and field-level cited direct facts."""

    repository = MarketIntelligenceRepository(session)
    company = repository.get_company_by_slug(slug)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    latest = repository.latest_profile(company.id)
    summary = _summary(company, latest)
    if latest is None:
        return CompanyDetailResponse(**summary.model_dump(), profile=None, facts=[])

    profile, document = latest
    citation = _citation(document)
    facts = [
        FactResponse(
            evidence_type=fact.evidence_type,
            predicate=fact.predicate,
            value=fact.value,
            extraction_method=fact.extraction_method,
            method_version=fact.method_version,
            observed_at=fact.observed_at,
            citation=citation,
        )
        for fact in repository.facts_for_document(document.id)
    ]
    return CompanyDetailResponse(
        **summary.model_dump(),
        profile=CompanyProfileData(
            display_name=profile.display_name,
            description=profile.description,
            website_url=profile.website_url,
            github_url=profile.github_url,
            location=profile.location,
            public_repos=profile.public_repos,
            followers=profile.followers,
            source_created_at=profile.source_created_at,
            source_updated_at=profile.source_updated_at,
        ),
        facts=facts,
    )
