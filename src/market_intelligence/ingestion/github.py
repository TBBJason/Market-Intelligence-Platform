"""GitHub REST organization connector with bounded, policy-aware retries."""

import email.utils
import json
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
from pydantic import ValidationError

from market_intelligence.config import Settings
from market_intelligence.ingestion.schemas import (
    GitHubFetchResult,
    GitHubOrganization,
    ResponseMetadata,
)

_GITHUB_KEY = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")


class SourceFetchError(RuntimeError):
    """External request failed without exposing response bodies or credentials."""


class SourceRateLimitError(SourceFetchError):
    """GitHub explicitly denied a request because its request budget was exhausted."""

    def __init__(self, metadata: ResponseMetadata) -> None:
        super().__init__("GitHub rate limit exhausted")
        self.metadata = metadata


class SourceValidationError(ValueError):
    """External response did not satisfy the documented contract."""


class GitHubOrganizationConnector:
    """Fetch public organization metadata through GitHub's official REST API."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=settings.http_timeout_seconds)
        self._sleep = sleeper
        self._clock = clock

    def __enter__(self) -> "GitHubOrganizationConnector":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        """Close only clients created by this connector."""

        if self._owns_client:
            self._client.close()

    def fetch(self, organization: str, *, etag: str | None = None) -> GitHubFetchResult:
        """Fetch and validate one approved organization, conditionally when possible."""

        if not _GITHUB_KEY.fullmatch(organization):
            raise ValueError("Invalid GitHub organization key")

        request_started_at = self._clock()
        url = f"{self._settings.github_api_url}/orgs/{organization}"
        request_url = httpx.URL(url)
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": self._settings.http_user_agent,
        }
        if etag:
            headers["If-None-Match"] = etag
        if self._settings.github_token is not None:
            if (
                request_url.scheme != "https"
                or request_url.host != self._settings.github_token_host
                or (request_url.port or 443) != self._settings.github_token_port
            ):
                raise ValueError("Refusing to send GitHub token to an unapproved origin")
            headers["Authorization"] = f"Bearer {self._settings.github_token.get_secret_value()}"

        response: httpx.Response | None = None
        for attempt in range(1, self._settings.http_max_attempts + 1):
            try:
                request = self._client.build_request("GET", request_url, headers=headers)
                response = self._client.send(request, stream=True)
            except httpx.TransportError as exc:
                if attempt == self._settings.http_max_attempts:
                    raise SourceFetchError("GitHub request failed after bounded retries") from exc
                self._sleep(self._backoff_seconds(attempt, None))
                continue

            if not self._is_transient(response) or attempt == self._settings.http_max_attempts:
                break
            delay = self._backoff_seconds(attempt, response)
            response.close()
            self._sleep(delay)

        if response is None:
            raise SourceFetchError("GitHub request produced no response")

        metadata = self._metadata(response, request_started_at)
        if self._is_rate_limited(response):
            response.close()
            raise SourceRateLimitError(metadata)
        if response.status_code == httpx.codes.NOT_MODIFIED:
            response.close()
            return GitHubFetchResult(status="not_modified", metadata=metadata)
        if response.status_code != httpx.codes.OK:
            status_code = response.status_code
            response.close()
            raise SourceFetchError(f"GitHub request failed with HTTP {status_code}")

        body = self._read_limited(response)
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SourceValidationError("GitHub response was not valid JSON") from exc
        if not isinstance(payload, dict):
            raise SourceValidationError("GitHub response JSON was not an object")
        try:
            validated = GitHubOrganization.model_validate(payload)
        except ValidationError as exc:
            raise SourceValidationError("GitHub response failed schema validation") from exc

        return GitHubFetchResult(
            status="changed",
            organization=validated,
            raw_payload=payload,
            metadata=metadata,
        )

    def _read_limited(self, response: httpx.Response) -> bytes:
        content_length = response.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self._settings.http_max_response_bytes:
                    response.close()
                    raise SourceFetchError("GitHub response exceeded the configured size limit")
            except ValueError:
                pass

        chunks: list[bytes] = []
        received = 0
        try:
            for chunk in response.iter_bytes():
                received += len(chunk)
                if received > self._settings.http_max_response_bytes:
                    raise SourceFetchError("GitHub response exceeded the configured size limit")
                chunks.append(chunk)
        finally:
            response.close()
        return b"".join(chunks)

    def _metadata(self, response: httpx.Response, request_started_at: datetime) -> ResponseMetadata:
        reset_at: datetime | None = None
        reset_value = response.headers.get("x-ratelimit-reset")
        if reset_value:
            try:
                reset_at = datetime.fromtimestamp(int(reset_value), tz=UTC)
            except (ValueError, OverflowError):
                reset_at = None

        remaining: int | None = None
        remaining_value = response.headers.get("x-ratelimit-remaining")
        if remaining_value:
            try:
                remaining = int(remaining_value)
            except ValueError:
                remaining = None

        return ResponseMetadata(
            status_code=response.status_code,
            source_url=str(response.url),
            request_started_at=request_started_at,
            retrieved_at=self._clock(),
            content_type=response.headers.get("content-type"),
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
            rate_limit_remaining=remaining,
            rate_limit_reset_at=reset_at,
        )

    @staticmethod
    def _is_rate_limited(response: httpx.Response) -> bool:
        return response.status_code in {
            httpx.codes.TOO_MANY_REQUESTS,
            httpx.codes.FORBIDDEN,
        }

    def _is_transient(self, response: httpx.Response) -> bool:
        return self._is_rate_limited(response) or response.status_code >= 500

    def _backoff_seconds(self, attempt: int, response: httpx.Response | None) -> float:
        if response is not None:
            retry_after = response.headers.get("retry-after")
            if retry_after:
                parsed = self._parse_retry_after(retry_after)
                return min(parsed, float(self._settings.http_max_retry_after_seconds))
            if response.headers.get("x-ratelimit-remaining") == "0":
                reset = response.headers.get("x-ratelimit-reset")
                if reset:
                    try:
                        until_reset = datetime.fromtimestamp(int(reset), tz=UTC) - self._clock()
                        return min(
                            max(0.0, until_reset.total_seconds()),
                            float(self._settings.http_max_retry_after_seconds),
                        )
                    except (ValueError, OverflowError):
                        pass
        return min(float(2 ** (attempt - 1)), float(self._settings.http_max_retry_after_seconds))

    def _parse_retry_after(self, value: str) -> float:
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                parsed = email.utils.parsedate_to_datetime(value)
            except (TypeError, ValueError):
                return 1.0
            return max(0.0, (parsed - self._clock()).total_seconds())
