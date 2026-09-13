"""Tests for semantic content identity."""

from market_intelligence.ingestion.service import canonical_json_hash


def test_canonical_hash_ignores_json_key_order() -> None:
    first = {"name": "Example", "counts": {"repos": 3, "followers": 4}}
    reordered = {"counts": {"followers": 4, "repos": 3}, "name": "Example"}

    assert canonical_json_hash(first) == canonical_json_hash(reordered)


def test_canonical_hash_changes_with_source_value() -> None:
    before = {"description": "before"}
    after = {"description": "after"}

    assert canonical_json_hash(before) != canonical_json_hash(after)
