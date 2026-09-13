# Architecture

## Scope

The first vertical slice proves one evidence path end to end:

```text
GitHub REST /orgs/{login}
  -> validated connector response
  -> immutable raw document + retrieval metadata
  -> directly retrieved facts + versioned company profile
  -> dbt staging/current-company mart
  -> FastAPI GET /v1/companies and /v1/companies/{slug}
```

RAG, embeddings, model classification, agents, and a frontend are explicitly deferred until this path is reproducible. The schema reserves a pgvector-backed `document_chunks` table and typed evidence records, but the milestone does not populate them.

## Project structure

```text
.
├── README.md                    # runbook and verification contract
├── pyproject.toml               # Python package and quality tooling
├── docker-compose.yml           # PostgreSQL + pgvector and optional app services
├── dbt/                         # staging and research mart models/tests
├── docs/                        # architecture, source review, data model, decisions
├── sample_data/                 # reviewed source registry seeds only; no fake outcomes
├── sql/                         # deterministic database bootstrap
├── src/market_intelligence/
│   ├── api/                     # HTTP schemas, dependencies, routes
│   ├── database/                # SQLAlchemy models, sessions, repository
│   ├── ingestion/               # source contracts, GitHub client, ingestion service
│   ├── orchestration/           # thin Prefect flow around domain service
│   └── config.py                # environment-backed settings
└── tests/                       # domain and API behavior tests
```

Dependencies point inward: API and orchestration call the ingestion/database application layer; the connector knows nothing about FastAPI, Prefect, or dbt. dbt reads database relations and never calls an external source.

## Runtime components

- **PostgreSQL 17 + pgvector:** system of record. The `raw` schema stores source registry and retrieval evidence; `core` stores normalized/versioned entities and typed facts; `analytics` is owned by dbt.
- **Python ingestion process:** validates the external payload with Pydantic before a transaction writes it. Invalid payloads fail visibly and are not partially normalized.
- **Prefect flow:** adds observable runs, bounded task retry, and explicit source/date parameters. Domain idempotency remains in the ingestion service, not in Prefect state.
- **dbt-postgres:** creates views/tables for research consumption and tests source/model assumptions.
- **FastAPI:** read-only first-slice API. It returns normalized data plus citations and evidence type; it does not expose raw payloads by default.

## Evidence taxonomy

Every research-facing assertion has one of three `evidence_type` values:

1. `direct_fact`: a field retrieved from a source (the only type emitted now).
2. `derived_classification`: deterministic or statistical transformation, with method/version and supporting facts.
3. `model_interpretation`: LLM-generated synthesis, with model/prompt/version and supporting facts.

`core.fact_records` stores the type, subject, predicate, JSON value, raw-document citation, extraction method, and method version. Database constraints require a citation for direct facts. Future derived/model records will use an assertion-evidence junction so every conclusion remains traceable.

## Ingestion and idempotency

1. Resolve an enabled source by `(source_type, external_key)` and require `review_status = 'approved'`.
2. Request the endpoint with an identifiable User-Agent, explicit GitHub media/API versions, optional token, and prior ETag.
3. Treat `304` as a successful unchanged check. Update `last_checked_at`; create no new document or profile version.
4. Re-lock and revalidate approval. If a newer request has already committed, mark this run unchanged and discard the stale body rather than regressing or archiving an unpromotable hash.
5. Validate a promotable `200` payload with Pydantic; canonicalize JSON and compute SHA-256.
6. Insert `raw.source_documents` under unique key `(source_id, external_id, content_hash)`. On conflict, update check metadata but create no duplicate facts/version.
7. Upsert the stable company identity through `core.external_identifiers`; append a `core.company_profiles` row only for a new source document.
8. Insert direct facts referencing that document, then update source success metadata in the same transaction.

HTTP retries are bounded to transient network errors, `429`, and `5xx`. Authentication/authorization/not-found/validation errors are not retried. `Retry-After` is honored within a configured ceiling. A failed database transaction rolls back all normalized changes.

## API contract

- `GET /health`: process and database status.
- `GET /v1/companies?query=&limit=&offset=`: normalized company summaries.
- `GET /v1/companies/{slug}`: current profile and field-level direct facts with source URL and retrieval time.

The profile response distinguishes missing from known values and reports the evidence type. An empty result is not model-filled. Raw response bodies remain internal; source/document retrieval endpoints belong to a later slice with retention authorization.

## dbt contract

- `<target>_staging.stg_company_profiles`: renamed, typed version records with citation metadata.
- `<target>_intermediate.int_company_profiles_ranked`: deterministic recency ordering.
- `<target>_analytics.company_research_profiles`: one current profile per company, retaining source URL, retrieval time, and raw-document ID.

Sources receive freshness warnings/errors. Tests cover keys, required values, relationships, evidence accepted values, and one-current-row invariants. dbt transformations do not overwrite evidence tables.

## Key tradeoffs

| Choice | Benefit | Cost / mitigation |
|---|---|---|
| Official GitHub REST API first | Predictable schema and documented controls | Narrow company signal; clearly label it self-reported and add primary websites/SEC later |
| PostgreSQL schemas in one database | Simple local operation and transactional lineage | Less isolation than separate stores; roles and retention policies should be split in production |
| Preserve reviewed JSON payloads | Reproducibility and reprocessing | Storage/licensing burden; source registry controls retention and future sources can use metadata-only mode |
| SQLAlchemy + psycopg, synchronous | Readable transactions; broad engineer familiarity | Lower single-process concurrency; ingestion is I/O-light and can move to async only with measured need |
| SQL bootstrap for milestone | Transparent, deterministic container start | Not a migration history; add Alembic before collaborative schema evolution |
| Prefect as a thin adapter | Observable retries/schedules without domain lock-in | Another runtime dependency; core service remains callable without Prefect |
| dbt view/table marts | Explicit lineage and tests | Requires a separate build step; API reads normalized `core` now and can switch to marts after deployment orchestration |
| Reserve vector table, defer embeddings | Demonstrates planned boundary without pretending RAG works | No semantic search yet; activation requires evaluation dataset and model decision |

## Security and operations

- Credentials are environment-only and never logged. The GitHub token is optional for low-volume public requests.
- Source identifiers are registry-controlled; retrieved URLs must match the reviewed URL, API origins require HTTPS, and tokens are bound to an approved host.
- Payload size, HTTP timeout, retry count, and backoff are bounded.
- Structured logs contain run/source/document identifiers, not credentials or full payloads.
- Database health is explicit. API errors do not silently return fabricated data.
- Production needs restricted database roles, encrypted backups, retention jobs, migrations, metrics/traces, and a terms-review alert process.

## Explicit limitations

This slice covers one GitHub organization endpoint and normalized profile facts. It does not establish legal identity, infer categories/products, ingest people/funding, measure market quality, compare companies, or answer research questions. It has no accuracy claim. Docker-backed dbt/database checks depend on a working Docker Compose environment; unit and API contract checks run without it.
