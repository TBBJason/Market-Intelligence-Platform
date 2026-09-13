"""Validated external payloads and source-neutral ingestion outcomes."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)


class GitHubOrganization(BaseModel):
    """The documented GitHub organization fields selected for this product."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    id: int = Field(gt=0)
    login: str = Field(
        min_length=1, max_length=39, pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$"
    )
    name: str | None = None
    description: str | None = None
    blog: HttpUrl | None = None
    html_url: HttpUrl
    location: str | None = None
    public_repos: int = Field(ge=0)
    followers: int = Field(ge=0)
    created_at: AwareDatetime
    updated_at: AwareDatetime
    type: Literal["Organization"]

    @field_validator("blog", mode="before")
    @classmethod
    def empty_blog_is_missing(cls, value: object) -> object:
        """GitHub represents an absent profile website as an empty string."""

        return None if value == "" else value

    @property
    def display_name(self) -> str:
        """Use GitHub's explicit name when present, otherwise its stable login."""

        return self.name or self.login


class ResponseMetadata(BaseModel):
    """Safe response metadata retained for provenance and rate-limit operations."""

    model_config = ConfigDict(frozen=True)

    status_code: int
    source_url: HttpUrl
    request_started_at: AwareDatetime
    retrieved_at: AwareDatetime
    content_type: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    rate_limit_remaining: int | None = None
    rate_limit_reset_at: AwareDatetime | None = None


class GitHubFetchResult(BaseModel):
    """Validated result of one conditional organization request."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    status: Literal["changed", "not_modified"]
    organization: GitHubOrganization | None = None
    raw_payload: dict[str, Any] | None = None
    metadata: ResponseMetadata

    @model_validator(mode="after")
    def payload_matches_status(self) -> "GitHubFetchResult":
        """A changed response carries evidence; a 304 carries no response body."""

        has_payload = self.organization is not None and self.raw_payload is not None
        if self.status == "changed" and not has_payload:
            raise ValueError("changed result requires validated and raw payloads")
        if self.status == "not_modified" and (
            self.organization is not None or self.raw_payload is not None
        ):
            raise ValueError("not_modified result must not carry a payload")
        return self


class IngestionOutcome(BaseModel):
    """Stable, serializable summary returned by CLI and Prefect."""

    model_config = ConfigDict(frozen=True)

    status: Literal["inserted", "unchanged"]
    source_id: UUID
    run_id: UUID
    document_id: UUID | None
    company_id: UUID | None
    content_hash: str | None
    observed_at: datetime
