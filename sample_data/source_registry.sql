-- Reviewed source configuration only; this file contains no fabricated company response data.
INSERT INTO raw.source_registry (
    source_type,
    external_key,
    company_slug,
    source_url,
    collection_method,
    terms_url,
    review_status,
    reviewed_at,
    reviewed_by,
    attribution_text,
    retention_mode,
    enabled
)
VALUES (
    'github_org',
    'weaviate',
    'weaviate',
    'https://api.github.com/orgs/weaviate',
    'official_api',
    'https://docs.github.com/en/site-policy/github-terms/github-terms-of-service',
    'approved',
    '2026-09-13T00:00:00Z',
    'project-maintainer',
    'Source: GitHub organization API (https://api.github.com/orgs/weaviate)',
    'full_response',
    true
)
ON CONFLICT (source_type, external_key) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    terms_url = EXCLUDED.terms_url,
    review_status = EXCLUDED.review_status,
    reviewed_at = EXCLUDED.reviewed_at,
    reviewed_by = EXCLUDED.reviewed_by,
    attribution_text = EXCLUDED.attribution_text,
    retention_mode = EXCLUDED.retention_mode,
    enabled = EXCLUDED.enabled,
    updated_at = now();
