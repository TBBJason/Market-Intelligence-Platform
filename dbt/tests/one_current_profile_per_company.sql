with expected as (
    select company_id, source_document_id
    from {{ ref('int_company_profiles_ranked') }}
    where profile_recency_rank = 1
),
actual as (
    select company_id, source_document_id
    from {{ ref('company_research_profiles') }}
)
select
    coalesce(expected.company_id, actual.company_id) as company_id
from expected
full outer join actual using (company_id, source_document_id)
where expected.company_id is null
   or actual.company_id is null
