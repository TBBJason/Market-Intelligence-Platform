select
    *,
    row_number() over (
        partition by company_id
        order by valid_from desc, company_profile_id desc
    ) as profile_recency_rank
from {{ ref('stg_company_profiles') }}
