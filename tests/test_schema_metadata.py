"""Guard the supported ORM/bootstrap contract from silent drift."""

from pathlib import Path

from market_intelligence.database.models import Base

EXPECTED_INDEXES = {
    "ix_source_documents_source_retrieved",
    "ix_ingestion_runs_source_started",
    "ix_company_profiles_company_valid",
}


def test_bootstrap_and_orm_share_named_access_paths() -> None:
    orm_indexes = {
        index.name
        for table in Base.metadata.tables.values()
        for index in table.indexes
        if index.name is not None
    }
    bootstrap = (Path(__file__).parents[1] / "sql" / "001_initial.sql").read_text()

    assert orm_indexes >= EXPECTED_INDEXES
    for index_name in EXPECTED_INDEXES:
        assert index_name in bootstrap


def test_owned_core_relations_declare_delete_cascades() -> None:
    expected = {
        ("core.external_identifiers", "company_id"),
        ("core.company_profiles", "company_id"),
        ("core.fact_records", "company_id"),
        ("core.document_chunks", "source_document_id"),
    }
    actual: set[tuple[str, str]] = set()
    for table_name, column_name in expected:
        column = Base.metadata.tables[table_name].c[column_name]
        foreign_key = next(iter(column.foreign_keys))
        if foreign_key.ondelete == "CASCADE":
            actual.add((table_name, column_name))

    assert actual == expected
