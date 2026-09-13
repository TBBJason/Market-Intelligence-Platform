# Evaluation plan

## Current milestone evidence

This milestone evaluates deterministic platform behavior, not research-answer accuracy. Automated checks cover external schema validation, conditional requests, retry bounds, semantic content hashing, API citations/evidence labels, and—when a disposable PostgreSQL URL is supplied—database-level idempotency. dbt tests cover lineage assumptions. Passing these checks does **not** show that the platform is accurate, complete, investment-grade, or production-ready.

No retrieval, generation, latency, token-cost, or answer-quality metric is reported because RAG has not been implemented. No career bullet should claim such a result yet.

## Gate before RAG

RAG work starts only after the vertical slice runs end to end against PostgreSQL, dbt succeeds, a repeated source ingestion is proven idempotent, and citation-bearing API output is manually inspected. Source retention must also permit the text selected for chunking.

## Reproducible RAG evaluation phase

1. Write at least 25 hand-labeled questions spanning company descriptions, products, technologies, target customers, longitudinal changes, comparisons, and deliberately unanswerable questions.
2. For each question, record expected document IDs and/or exact normalized facts before running retrieval.
3. Freeze an evaluation corpus snapshot by source-document content hashes.
4. Compare at least two configurations, such as lexical baseline vs. hybrid lexical/vector retrieval, with the same corpus and filters.
5. Report hit@1, hit@3, and hit@5 using expected supporting documents. Include macro results and per-question rows.
6. For generated structured answers, validate schema success and decompose each answer into claims. Mark each claim supported, contradicted, or not established by its citations.
7. Report citation precision (cited documents that support a claim), claim support rate, refusal behavior on unanswerable questions, and invalid-output rate.
8. Capture end-to-end latency, retrieval latency, model/embedding identifiers, token counts, and approximate provider cost using dated public pricing or provider usage records.
9. Categorize failures: source absence/staleness, extraction error, metadata filter error, retrieval miss, ranking miss, unsupported synthesis, citation mismatch, schema failure, or timeout.
10. Publish configuration, prompt versions, seeds where available, corpus hashes, raw per-question results, and aggregation code.

## Anti-overclaiming rules

- Do not call LLM-as-judge scores ground truth; calibrate them against human labels.
- Do not merge retrieval and generation failures into one accuracy number.
- Do not treat a citation's presence as evidence that it supports a claim.
- Do not infer unavailable market/funding/person data.
- Report sample size and confidence limitations alongside every aggregate.
- Keep failed and unanswerable examples in the published set.
