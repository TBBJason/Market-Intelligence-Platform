select
    profile.id as company_profile_id,
    profile.company_id,
    profile.source_document_id,
    profile.display_name,
    profile.description,
    profile.website_url,
    profile.github_url,
    profile.location,
    profile.public_repos,
    profile.followers,
    profile.source_created_at,
    profile.source_updated_at,
    profile.valid_from,
    document.source_url,
    document.retrieved_at,
    document.content_hash,
    document.attribution_text
from {{ source('core', 'company_profiles') }} as profile
inner join {{ source('raw', 'source_documents') }} as document
    on profile.source_document_id = document.id
