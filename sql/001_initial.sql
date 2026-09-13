BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS raw.source_registry (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type text NOT NULL,
    external_key text NOT NULL,
    company_slug text NOT NULL,
    source_url text NOT NULL,
    collection_method text NOT NULL,
    terms_url text NOT NULL,
    robots_url text,
    review_status text NOT NULL DEFAULT 'pending'
        CHECK (review_status IN ('pending', 'approved', 'rejected', 'review_required')),
    reviewed_at timestamptz,
    reviewed_by text,
    attribution_text text NOT NULL,
    retention_mode text NOT NULL DEFAULT 'metadata_only'
        CHECK (retention_mode IN ('full_response', 'metadata_only')),
    enabled boolean NOT NULL DEFAULT false,
    last_checked_at timestamptz,
    last_successful_retrieval_at timestamptz,
    last_http_status integer,
    etag text,
    rate_limit_remaining integer,
    rate_limit_reset_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_source_registry_type_key UNIQUE (source_type, external_key),
    CONSTRAINT ck_approved_source_has_review CHECK (
        review_status <> 'approved' OR (reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS raw.ingestion_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id uuid NOT NULL REFERENCES raw.source_registry(id),
    orchestration_run_id text,
    requested_as_of date,
    status text NOT NULL DEFAULT 'started'
        CHECK (status IN ('started', 'succeeded', 'unchanged', 'failed')),
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    document_id uuid,
    error_type text,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_failed_run_has_error CHECK (
        status <> 'failed' OR (error_type IS NOT NULL AND error_message IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS raw.source_documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id uuid NOT NULL REFERENCES raw.source_registry(id),
    external_id text NOT NULL,
    source_url text NOT NULL,
    content_type text NOT NULL,
    content_hash char(64) NOT NULL,
    content jsonb,
    retrieved_at timestamptz NOT NULL,
    last_checked_at timestamptz NOT NULL,
    http_status integer NOT NULL,
    etag text,
    last_modified text,
    attribution_text text NOT NULL,
    response_headers jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_source_document_content UNIQUE (source_id, external_id, content_hash),
    CONSTRAINT ck_sha256_hex CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_successful_document CHECK (http_status BETWEEN 200 AND 299)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_ingestion_run_document'
    ) THEN
        ALTER TABLE raw.ingestion_runs
            ADD CONSTRAINT fk_ingestion_run_document
            FOREIGN KEY (document_id) REFERENCES raw.source_documents(id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_source_documents_source_retrieved
    ON raw.source_documents (source_id, retrieved_at DESC);
CREATE INDEX IF NOT EXISTS ix_ingestion_runs_source_started
    ON raw.ingestion_runs (source_id, started_at DESC);

CREATE TABLE IF NOT EXISTS core.companies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug text NOT NULL UNIQUE,
    canonical_name text NOT NULL,
    website_url text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_company_slug CHECK (slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$')
);

CREATE TABLE IF NOT EXISTS core.external_identifiers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id) ON DELETE CASCADE,
    source_type text NOT NULL,
    external_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_external_identifier UNIQUE (source_type, external_id),
    CONSTRAINT uq_company_source_identifier UNIQUE (company_id, source_type)
);

CREATE TABLE IF NOT EXISTS core.company_profiles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id) ON DELETE CASCADE,
    source_document_id uuid NOT NULL UNIQUE REFERENCES raw.source_documents(id),
    display_name text NOT NULL,
    description text,
    website_url text,
    github_url text NOT NULL,
    location text,
    public_repos integer NOT NULL,
    followers integer NOT NULL,
    source_created_at timestamptz NOT NULL,
    source_updated_at timestamptz NOT NULL,
    valid_from timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_profile_counts CHECK (public_repos >= 0 AND followers >= 0)
);

CREATE INDEX IF NOT EXISTS ix_company_profiles_company_valid
    ON core.company_profiles (company_id, valid_from DESC);

CREATE TABLE IF NOT EXISTS core.fact_records (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id) ON DELETE CASCADE,
    source_document_id uuid REFERENCES raw.source_documents(id),
    evidence_type text NOT NULL
        CHECK (evidence_type IN ('direct_fact', 'derived_classification', 'model_interpretation')),
    predicate text NOT NULL,
    value jsonb NOT NULL,
    extraction_method text NOT NULL,
    method_version text NOT NULL,
    observed_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_fact_per_document UNIQUE (source_document_id, predicate),
    CONSTRAINT ck_direct_fact_citation CHECK (
        evidence_type <> 'direct_fact' OR source_document_id IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS ix_fact_records_company_predicate
    ON core.fact_records (company_id, predicate);

CREATE TABLE IF NOT EXISTS core.products (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id) ON DELETE CASCADE,
    name text NOT NULL,
    description text,
    source_document_id uuid NOT NULL REFERENCES raw.source_documents(id),
    evidence_type text NOT NULL DEFAULT 'direct_fact'
        CHECK (evidence_type IN ('direct_fact', 'derived_classification', 'model_interpretation')),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_product_evidence UNIQUE (company_id, name, source_document_id)
);

CREATE TABLE IF NOT EXISTS core.categories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug text NOT NULL UNIQUE,
    name text NOT NULL UNIQUE,
    description text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.company_categories (
    company_id uuid NOT NULL REFERENCES core.companies(id) ON DELETE CASCADE,
    category_id uuid NOT NULL REFERENCES core.categories(id),
    source_document_id uuid NOT NULL REFERENCES raw.source_documents(id),
    evidence_type text NOT NULL
        CHECK (evidence_type IN ('direct_fact', 'derived_classification', 'model_interpretation')),
    method_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, category_id, source_document_id, method_version)
);

CREATE TABLE IF NOT EXISTS core.technologies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug text NOT NULL UNIQUE,
    name text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.company_technologies (
    company_id uuid NOT NULL REFERENCES core.companies(id) ON DELETE CASCADE,
    technology_id uuid NOT NULL REFERENCES core.technologies(id),
    source_document_id uuid NOT NULL REFERENCES raw.source_documents(id),
    evidence_type text NOT NULL
        CHECK (evidence_type IN ('direct_fact', 'derived_classification', 'model_interpretation')),
    method_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, technology_id, source_document_id, method_version)
);

CREATE TABLE IF NOT EXISTS core.people (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name text NOT NULL,
    source_document_id uuid NOT NULL REFERENCES raw.source_documents(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_person_evidence UNIQUE (full_name, source_document_id)
);

CREATE TABLE IF NOT EXISTS core.company_people (
    company_id uuid NOT NULL REFERENCES core.companies(id) ON DELETE CASCADE,
    person_id uuid NOT NULL REFERENCES core.people(id) ON DELETE CASCADE,
    role text NOT NULL,
    source_document_id uuid NOT NULL REFERENCES raw.source_documents(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, person_id, role, source_document_id)
);

CREATE TABLE IF NOT EXISTS core.funding_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id) ON DELETE CASCADE,
    announced_on date,
    round_name text,
    amount numeric(20, 2),
    currency char(3),
    source_document_id uuid NOT NULL REFERENCES raw.source_documents(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_nonnegative_funding CHECK (amount IS NULL OR amount >= 0),
    CONSTRAINT uq_funding_evidence UNIQUE (company_id, source_document_id)
);

CREATE TABLE IF NOT EXISTS core.document_chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_document_id uuid NOT NULL REFERENCES raw.source_documents(id) ON DELETE CASCADE,
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    content text NOT NULL,
    content_hash char(64) NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    embedding vector,
    embedding_model text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_document_chunk UNIQUE (source_document_id, chunk_index, content_hash)
);

COMMIT;
