select
    company.company_id,
    company.slug,
    company.canonical_name,
    profile.display_name,
    profile.description,
    profile.website_url as website_url,
    profile.github_url,
    profile.location,
    profile.public_repos,
    profile.followers,
    profile.source_created_at,
    profile.source_updated_at,
    profile.source_document_id,
    profile.source_url,
    profile.retrieved_at,
    profile.content_hash,
    profile.attribution_text,
    'direct_fact'::text as evidence_type
from {{ ref('stg_companies') }} as company
inner join {{ ref('int_company_profiles_ranked') }} as profile
    on company.company_id = profile.company_id
    and profile.profile_recency_rank = 1
