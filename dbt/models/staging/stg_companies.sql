select
    id as company_id,
    slug,
    canonical_name,
    website_url,
    created_at,
    updated_at
from {{ source('core', 'companies') }}
