"""Contract tests for bounded and validated GitHub REST behavior."""

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from market_intelligence.config import Settings
from market_intelligence.ingestion.github import (
    GitHubOrganizationConnector,
    SourceFetchError,
    SourceRateLimitError,
    SourceValidationError,
)

FIXED_NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "_env_file": None,
        "environment": "test",
        "github_api_url": "https://api.github.test",
        "http_user_agent": "market-intelligence-tests",
    }
    values.update(overrides)
    return Settings(**values)


def test_fetch_validates_payload_and_sends_conditional_headers(
    github_payload: dict[str, Any],
) -> None:
    captured_headers: httpx.Headers | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_headers
        captured_headers = request.headers
        return httpx.Response(
            200,
            json=github_payload,
            headers={
                "Content-Type": "application/json",
                "ETag": '"version-2"',
                "X-RateLimit-Remaining": "59",
                "X-RateLimit-Reset": "1789304400",
            },
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    connector = GitHubOrganizationConnector(
        _settings(), client=client, clock=lambda: FIXED_NOW, sleeper=lambda _: None
    )

    result = connector.fetch("example-infrastructure", etag='"version-1"')

    assert result.status == "changed"
    assert result.organization is not None
    assert result.organization.display_name == "Example Infrastructure"
    assert result.raw_payload == github_payload
    assert result.metadata.rate_limit_remaining == 59
    assert captured_headers is not None
    assert captured_headers["if-none-match"] == '"version-1"'
    assert captured_headers["x-github-api-version"] == "2022-11-28"
    assert captured_headers["user-agent"] == "market-intelligence-tests"
    assert "authorization" not in captured_headers


def test_fetch_304_returns_no_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(304, headers={"ETag": '"same"'}, request=request)

    connector = GitHubOrganizationConnector(
        _settings(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=lambda: FIXED_NOW,
    )

    result = connector.fetch("example-infrastructure", etag='"same"')

    assert result.status == "not_modified"
    assert result.organization is None
    assert result.raw_payload is None


def test_fetch_retries_rate_limit_with_bounded_retry_after(
    github_payload: dict[str, Any],
) -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "999"}, request=request)
        return httpx.Response(200, json=github_payload, request=request)

    connector = GitHubOrganizationConnector(
        _settings(http_max_retry_after_seconds=7),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=sleeps.append,
        clock=lambda: FIXED_NOW,
    )

    result = connector.fetch("example-infrastructure")

    assert result.status == "changed"
    assert attempts == 2
    assert sleeps == [7.0]


def test_fetch_rejects_invalid_external_payload(github_payload: dict[str, Any]) -> None:
    github_payload["public_repos"] = -1

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=github_payload, request=request)

    connector = GitHubOrganizationConnector(
        _settings(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(SourceValidationError, match="schema validation"):
        connector.fetch("example-infrastructure")


def test_fetch_rejects_untrusted_organization_key() -> None:
    def unexpected_request(_: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid organization key must fail before HTTP")

    connector = GitHubOrganizationConnector(
        _settings(), client=httpx.Client(transport=httpx.MockTransport(unexpected_request))
    )

    with pytest.raises(ValueError, match="Invalid GitHub organization key"):
        connector.fetch("../admin")


def test_fetch_rejects_oversized_stream_before_json_parsing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 1_025, request=request)

    connector = GitHubOrganizationConnector(
        _settings(http_max_response_bytes=1_024),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(SourceFetchError, match="size limit"):
        connector.fetch("example-infrastructure")


def test_token_is_bound_to_approved_https_host() -> None:
    settings = _settings(
        github_api_url="https://api.github.com:444/api/v3",
        github_token="secret-placeholder",
        github_token_host="api.github.com",
    )
    connector = GitHubOrganizationConnector(
        settings,
        client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(500, request=request))
        ),
    )

    with pytest.raises(ValueError, match="unapproved origin"):
        connector.fetch("example-infrastructure")


def test_primary_403_rate_limit_uses_reset_and_raises_specific_error() -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            403,
            headers={
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": "1789304400",
            },
            request=request,
        )

    connector = GitHubOrganizationConnector(
        _settings(http_max_attempts=2, http_max_retry_after_seconds=7),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=sleeps.append,
        clock=lambda: FIXED_NOW,
    )

    with pytest.raises(SourceRateLimitError) as caught:
        connector.fetch("example-infrastructure")

    assert attempts == 2
    assert sleeps == [7.0]
    assert caught.value.metadata.rate_limit_remaining == 0


def test_secondary_403_is_typed_rate_limit_without_prefect_eligible_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={"X-RateLimit-Remaining": "42"},
            request=request,
        )

    connector = GitHubOrganizationConnector(
        _settings(http_max_attempts=1),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=lambda: FIXED_NOW,
    )

    with pytest.raises(SourceRateLimitError) as caught:
        connector.fetch("example-infrastructure")

    assert caught.value.metadata.rate_limit_remaining == 42
