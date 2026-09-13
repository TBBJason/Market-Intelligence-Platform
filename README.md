# AI Infrastructure Market Intelligence Platform

An evidence-first research data platform for investors and market researchers studying AI and data-infrastructure companies.

The first vertical slice ingests one explicitly approved public GitHub organization profile through the official REST API, validates it, stores content-addressed evidence in PostgreSQL/pgvector, normalizes cited company facts, orchestrates runs with Prefect, builds a dbt research mart, and serves citation-bearing FastAPI responses. RAG and a frontend are deliberately deferred.

## What this milestone demonstrates

- source/terms/robots/attribution review before collection;
- bounded official-API ingestion with ETag and rate-limit handling;
- Pydantic validation, semantic SHA-256 idempotency, and durable failure records;
- direct facts separated from future classifications and model interpretations;
- PostgreSQL schemas, pgvector boundary, dbt lineage/freshness/tests, and Prefect state;
- normalized company search/profile responses with source citations;
- typed, structured, tested Python with no credentials or fabricated research outcomes.

It does **not** yet infer products/categories, compare companies, perform RAG, make investment recommendations, or claim research accuracy.

## Architecture and policy

- [Architecture and tradeoffs](docs/architecture.md)
- [Data-source legal/attribution matrix](docs/data-sources.md)
- [Data model and lineage](docs/data-model.md)
- [Evaluation plan and anti-overclaiming rules](docs/evaluation.md)
- [ADR 0001: first source and boundaries](docs/decisions/0001-first-source-and-boundaries.md)
- [ADR 0002: defer RAG](docs/decisions/0002-defer-rag-until-evidence-pipeline-is-verified.md)

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker with the Compose v2 plugin
- `curl` for the manual API checks

## Set up

```bash
cp .env.example .env
# Replace YOUR_EMAIL in MI_HTTP_USER_AGENT. MI_GITHUB_TOKEN is optional for this low-volume demo.
uv sync --extra dev --extra data
docker compose up -d postgres
docker compose exec -T postgres psql \
  -U market_intelligence -d market_intelligence \
  < sample_data/source_registry.sql
```

The seed is reviewed source configuration for the public Weaviate GitHub organization; it contains no copied or fabricated company response. If PostgreSQL was previously initialized with an older schema, use a new volume for this milestone. Do not delete a volume containing data you need.

## Run the vertical slice

### 1. Ingest through Prefect

```bash
uv run market-intelligence-flow weaviate
```

For explicit source/date replay partitions:

```bash
uv run market-intelligence-flow weaviate --date 2026-09-13
```

The date is an operational partition label. GitHub's organization endpoint returns current state; a past label is not a historical snapshot claim. The manual domain entry point is also available:

```bash
uv run market-intelligence-ingest-github weaviate
```

Run either command twice. The second unchanged payload should report `"status": "unchanged"` and reuse the document ID rather than creating another source document/profile.

### 2. Build and test dbt models

```bash
set -a; source .env; set +a
uv run dbt source freshness --project-dir dbt --profiles-dir dbt
uv run dbt build --project-dir dbt --profiles-dir dbt
uv run dbt docs generate --project-dir dbt --profiles-dir dbt
```

Freshness warns after two days and errors after seven. These are demonstration defaults, not universal source SLAs.

### 3. Serve and inspect the API

Run without a reload watcher:

```bash
uv run market-intelligence-api
```

In another terminal:

```bash
curl --fail http://localhost:8000/health
curl --fail 'http://localhost:8000/v1/companies?query=weaviate'
curl --fail http://localhost:8000/v1/companies/weaviate
```

The detail response must contain a `citation`, a normalized `profile`, and `facts`. Every fact must have `evidence_type: "direct_fact"` and its own citation matching the profile's source document. Null source values remain null; the API does not fill gaps.

Alternatively, build the API container with:

```bash
docker compose --profile app up -d --build
```

## Verify behavior

### Fast checks (no database required)

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -m 'not integration'
DBT_PASSWORD=placeholder uv run dbt parse --project-dir dbt --profiles-dir dbt
```

### Database and idempotency checks

After running the same live ingestion twice:

```bash
docker compose exec -T postgres psql -U market_intelligence -d market_intelligence -c \
"select (select count(*) from raw.source_documents) as documents,
        (select count(*) from core.company_profiles) as profiles,
        (select count(*) from core.fact_records) as facts;"
```

With only the provided source and no source change, expected counts are one document, one profile, and eleven directly mapped facts. These are row counts that verify idempotency—not quality or business-impact metrics.

The opt-in integration test truncates its configured database. Use a disposable database only:

```bash
docker compose exec -T postgres createdb -U market_intelligence market_intelligence_test
TEST_DATABASE_URL='postgresql+psycopg://market_intelligence:market_intelligence@localhost:5432/market_intelligence_test' \
  uv run pytest -m integration
```

### Inspect the mart

```bash
docker compose exec -T postgres psql -U market_intelligence -d market_intelligence -c \
"select slug, evidence_type, source_url, retrieved_at
 from dev_analytics.company_research_profiles;"
```

There should be one current row for the ingested company with `direct_fact` and non-null citation fields.

## Add another source safely

Do not change the CLI to accept arbitrary URLs. Add a `raw.source_registry` row only after documenting method, current terms, robots applicability, reviewer/date, attribution, retention, and rate controls. Keep `enabled = false` until `review_status = 'approved'`. A new provider should implement a connector contract and preserve the same evidence boundaries.

## Known limitations

- One current-state GitHub organization endpoint is supported; its text is self-reported and not proof of legal identity, product capabilities, funding, or market quality.
- The SQL file is bootstrap-only, not a migration history. Add Alembic before team schema evolution.
- Local credentials are intentionally simple; production needs secret management, TLS, restricted database roles, encrypted backups, and retention jobs.
- Prefect defaults to ephemeral/local orchestration unless a server/cloud deployment is configured. Scheduling is not deployed by this repository.
- API list rendering performs a latest-profile lookup per company; optimize after measuring real list sizes.
- Source review is a documented engineering control, not legal advice; terms can change and need periodic re-review.
- pgvector is installed but empty. No embedding model, retrieval quality, generated answer, latency, or cost has been evaluated.
- Docker-backed verification depends on a working Compose v2 environment.

## Repository layout

```text
.
├── dbt/                         # sources, staging, intermediate, mart, tests
├── docs/                        # architecture, compliance, model, evaluation, ADRs
├── sample_data/                 # reviewed source configuration only
├── sql/001_initial.sql          # PostgreSQL/pgvector bootstrap
├── src/market_intelligence/
│   ├── api/                     # citation-bearing FastAPI routes
│   ├── database/                # ORM, sessions, repository
│   ├── ingestion/               # GitHub connector and domain service
│   ├── orchestration/           # Prefect source/date flow
│   ├── extraction/              # reserved, deferred
│   ├── retrieval/               # reserved, deferred
│   └── evaluation/              # reserved, deferred
└── tests/                       # unit/API and opt-in PostgreSQL integration tests
```
