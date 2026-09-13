# ADR 0001: Start with GitHub organization metadata and evidence-first boundaries

- Status: accepted
- Date: 2026-09-13

## Context

The product eventually needs heterogeneous source ingestion and citation-grounded research. Implementing scraping, classification, embeddings, and generation together would make failures difficult to attribute and could obscure source-permission mistakes.

## Decision

Implement one official GitHub REST organization-profile connector. Validate responses before persistence, content-address raw source documents, version normalized profiles, and store direct facts with citations. Keep connectors, persistence, orchestration, transformation, and presentation as separate modules. Defer all model-generated data and RAG.

## Consequences

The first demonstration is intentionally narrow but auditable. Re-running unchanged content creates no evidence/profile duplicates. GitHub data remains self-reported and cannot support broad market conclusions. New sources must implement the same connector contract and pass an explicit source-registry review. The initial SQL bootstrap must be replaced or complemented by migrations before concurrent schema development.
