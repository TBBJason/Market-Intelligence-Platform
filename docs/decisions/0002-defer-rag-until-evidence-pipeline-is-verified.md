# ADR 0002: Defer RAG and agents until the evidence pipeline is verified

- Status: accepted
- Date: 2026-09-13

## Context

A broad demonstration could add embeddings and generated answers quickly, but unverified ingestion, weak citation lineage, or source-retention mistakes would make RAG metrics misleading.

## Decision

The first milestone may create the pgvector extension and an empty chunk boundary but must not chunk, embed, retrieve, prompt, or generate research answers. RAG begins only after PostgreSQL ingestion, idempotency, dbt tests, and citation-bearing API output are verified. The next phase requires a frozen corpus and at least 25 hand-labeled questions before selecting an embedding/retrieval configuration.

## Consequences

The current product answers normalized company-profile requests, not free-form research questions. There are no accuracy, cost, or latency claims. This reduces portfolio breadth in the first milestone but makes later evaluation attributable and reproducible.
