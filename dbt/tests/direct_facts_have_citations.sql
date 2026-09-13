select fact_id
from {{ ref('stg_fact_records') }}
where evidence_type = 'direct_fact'
  and source_document_id is null
