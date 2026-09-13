"""Prefect orchestration for source/date-partitioned GitHub ingestion."""

import argparse
from datetime import UTC, date, datetime
from typing import Any

from prefect import flow, runtime, task

from market_intelligence.config import get_settings
from market_intelligence.database.repository import SourceNotApprovedError
from market_intelligence.database.session import make_session_factory
from market_intelligence.ingestion.github import (
    GitHubOrganizationConnector,
    SourceRateLimitError,
    SourceValidationError,
)
from market_intelligence.ingestion.schemas import IngestionOutcome
from market_intelligence.ingestion.service import GitHubIngestionService
from market_intelligence.logging import configure_logging

MAX_PARTITIONS_PER_RUN = 31


def retry_transient_failure(_task: Any, _task_run: Any, state: Any) -> bool:
    """Do not restart requests that policy, validation, or rate limits rejected."""

    result = state.result(raise_on_failure=False)
    return not isinstance(
        result,
        (SourceNotApprovedError, SourceRateLimitError, SourceValidationError, ValueError),
    )


@task(
    name="ingest-github-organization",
    retries=1,
    retry_delay_seconds=15,
    retry_condition_fn=retry_transient_failure,
)
def ingest_github_organization(
    organization: str,
    partition_date: date,
) -> dict[str, Any]:
    """Run one idempotent source/date partition with durable domain-level status."""

    settings = get_settings()
    orchestration_run_id = str(runtime.flow_run.id) if runtime.flow_run.id else None
    with make_session_factory()() as session, GitHubOrganizationConnector(settings) as connector:
        outcome = GitHubIngestionService(session, connector).ingest(
            organization,
            requested_as_of=partition_date,
            orchestration_run_id=orchestration_run_id,
        )
    return outcome.model_dump(mode="json")


@flow(name="github-organization-ingestion", log_prints=False)
def github_organization_flow(
    organizations: list[str],
    partition_dates: list[date] | None = None,
) -> list[dict[str, Any]]:
    """Ingest reviewed organizations for explicit operational date partitions.

    GitHub exposes current state, so a past partition date supports replay/audit only; it is not
    represented as a historical snapshot date. Content hashes keep replayed responses idempotent.
    """

    normalized_organizations = sorted(set(organizations))
    normalized_dates = sorted(set(partition_dates or [datetime.now(UTC).date()]))
    if not normalized_organizations:
        raise ValueError("At least one organization is required")
    partition_count = len(normalized_organizations) * len(normalized_dates)
    if partition_count > MAX_PARTITIONS_PER_RUN:
        raise ValueError(
            f"Requested {partition_count} partitions; maximum is {MAX_PARTITIONS_PER_RUN}"
        )

    results: list[dict[str, Any]] = []
    for partition_date in normalized_dates:
        for organization in normalized_organizations:
            results.append(ingest_github_organization(organization, partition_date))
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the GitHub organization Prefect flow")
    parser.add_argument("organizations", nargs="+", help="Approved source external keys")
    parser.add_argument(
        "--date",
        action="append",
        dest="dates",
        type=date.fromisoformat,
        help="Repeat for explicit operational partitions (YYYY-MM-DD)",
    )
    return parser


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    args = build_parser().parse_args()
    results = github_organization_flow(args.organizations, args.dates)
    for raw_result in results:
        outcome = IngestionOutcome.model_validate(raw_result)
        print(outcome.model_dump_json())


if __name__ == "__main__":
    main()
