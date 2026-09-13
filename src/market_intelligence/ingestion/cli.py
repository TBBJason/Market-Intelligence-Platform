"""Command-line entry point for manual, registry-controlled ingestion."""

import argparse
from datetime import date

from market_intelligence.config import get_settings
from market_intelligence.database.session import make_session_factory
from market_intelligence.ingestion.github import GitHubOrganizationConnector
from market_intelligence.ingestion.service import GitHubIngestionService
from market_intelligence.logging import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest an approved GitHub organization source")
    parser.add_argument("organization", help="Exact external_key in raw.source_registry")
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        help="Operational partition date (YYYY-MM-DD), not a historical-source guarantee",
    )
    return parser


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    args = build_parser().parse_args()
    with make_session_factory()() as session, GitHubOrganizationConnector(settings) as connector:
        result = GitHubIngestionService(session, connector).ingest(
            args.organization,
            requested_as_of=args.as_of,
        )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
