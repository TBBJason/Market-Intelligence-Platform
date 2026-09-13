select
    id as fact_id,
    company_id,
    source_document_id,
    evidence_type,
    predicate,
    value,
    extraction_method,
    method_version,
    observed_at,
    created_at
from {{ source('core', 'fact_records') }}
