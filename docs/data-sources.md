# Data-source review

Last reviewed: 2026-09-13

This document is an engineering review, not legal advice. Approval is source- and purpose-specific: a green collection method does not grant rights to republish all returned content. Before enabling a new source, record the applicable terms URL, robots result (for crawled pages), reviewer, review date, attribution text, and retention decision in the source registry.

## Source/legal/attribution matrix

| Candidate source | Useful data | Preferred collection method | Terms and robots considerations | Rate limits and freshness | Attribution and retention | Reliability limitations | Milestone decision |
|---|---|---|---|---|---|---|---|
| GitHub organization metadata | Organization name, description, public profile URL, website, public repository counts, creation/update timestamps | Official REST API, `GET /orgs/{org}`; conditional requests with ETag when available | API use is governed by GitHub's Terms of Service and Acceptable Use Policies. Use the API rather than scraping HTML. Do not collect private data, infer sensitive traits, or redistribute repository content without checking its license. `robots.txt` is not the control plane for an official API. | 60 requests/hour unauthenticated; typically 5,000/hour with a user token. Persist rate-limit headers, serialize polling, honor `Retry-After`, and use conditional requests. Poll daily at most for this slice; `updated_at` does not guarantee every profile field changed. | Cite the organization API URL and public GitHub profile URL. Store the API response because the milestone uses factual profile metadata only; reassess before retaining repository files or user data. | Self-reported organization text; organizations can rename or delete fields; counts change; an organization is not proof of corporate identity or product claims. | **Implement first.** Stable, documented API; no browser automation; small payload; useful company evidence. |
| SEC EDGAR submissions and company facts | Public-company filings, legal names, CIKs, filing dates, XBRL facts, primary-source risk and business descriptions | Official `data.sec.gov` JSON APIs and filing archives | SEC provides developer access and a fair-access policy. Send a descriptive User-Agent including contact information. Avoid parallel bulk traffic; use nightly bulk ZIP files for broad backfills. EDGAR APIs are preferable to HTML scraping. | Current published ceiling is 10 requests/second across machines; this project should remain well below it (for example, 2/second). Submissions update throughout filing days; bulk archives are republished nightly. | US federal filings are generally public records, but third-party exhibits may carry rights. Cite accession URL, filing form/date, and SEC. Retain exact filing sections only after a field-level retention review. | Applies mainly to public issuers; private infrastructure companies are absent. Filings are delayed, legalistic, amended, and may contain inline-XBRL parsing edge cases. | **Next source for public-company evidence**, not used in this milestone. |
| Official documentation via `llms.txt` | Curated product/docs summaries and links to machine-readable Markdown | Discover `/llms.txt`; follow only allowed links after source-level review | `llms.txt` is a voluntary proposal and discovery aid, not permission or a licensing instrument. Check site terms, robots rules, page-level directives, and licenses independently. Restrict requests to the reviewed host/path. | No universal rate limit or freshness guarantee. Respect HTTP cache headers, use conditional GET, and default to no more than one request/second per host. Record file and linked-page retrieval times independently. | Cite every final page, not only `llms.txt`. Preserve full content only when the site's license/terms permit it; otherwise retain hashes, metadata, and minimal excerpts. | Informal standard with uneven adoption; files may be stale, incomplete, marketing-curated, or link externally. | **High-priority discovery method after a per-site review.** |
| Official company blog RSS/Atom feeds | Product launches, positioning language, release chronology, canonical post links, publication/update timestamps | RSS or Atom feed exposed by the company | A feed is intentionally machine-readable but does not automatically authorize unrestricted republication. Review site terms and feed license; do not follow paywalled/authenticated links. Robots normally governs fetching linked HTML, not consuming an explicitly published feed, but record both decisions. | No universal limit. Honor feed TTL/cache headers where supplied; otherwise poll every 6–24 hours with ETag/Last-Modified and bounded backoff. | Display company/feed attribution and canonical post URL. Prefer metadata plus a limited excerpt unless republication rights are clear. | Entries can be edited or removed; dates and GUIDs are inconsistent; feeds may contain truncated HTML or only recent history. | **Preferred for longitudinal positioning** where a reviewed official feed exists. |
| Official website sitemap + permitted HTML | Product pages, customer segments, category language, changelog and documentation URLs | Use sitemap for discovery, then simple HTTP + HTML parsing; Playwright only for a reviewed, genuinely client-rendered page | Follow RFC 9309 robots rules using an identifiable User-Agent. Robots is a crawler-control protocol, not authorization; terms, copyright, privacy, and page directives still apply. Treat 5xx/network failure while retrieving robots as disallow. Never bypass access controls or anti-bot measures. | Site-specific. Honor `Retry-After`, cache validators, sitemap `lastmod` as a hint only, and a conservative default of one request/second with low concurrency. | Cite canonical URL and retrieval timestamp. Store full HTML only when permitted; otherwise store content hash, response metadata, extracted facts, and short evidence spans. | Marketing copy changes without notice; JavaScript/consent shells reduce extraction quality; sitemap `lastmod` can be inaccurate; layout changes break selectors. | **Fallback only after machine-readable/API options and a documented site review.** |

## Why GitHub is the first connector

The first slice ingests one configured GitHub organization profile. It demonstrates official API use, external validation, immutable raw evidence, content-addressed idempotency, source citations, and normalized company data without introducing brittle selectors. It does **not** classify the company, treat repository counts as investment quality, or infer products from repositories.

The connector sends GitHub's recommended API media type and API-version header, supports an optional token, records ETag and rate-limit headers, and backs off only for bounded transient failures. A source is enabled only after its registry row has review status `approved`.

## Operational policy

1. Default deny: connectors run only for registry entries with an approved review and an allowed collection method.
2. Prefer API/feed/machine-readable data over scraping. Do not use Playwright unless static retrieval cannot obtain reviewed public content.
3. Identify the client, keep concurrency low, honor cache validators and rate-limit headers, and stop on access denials.
4. Store URL, retrieval time, HTTP status, content hash, response validators, attribution, and review provenance.
5. Separate source evidence from derived classifications and model interpretations. Every derived record must point to one or more evidence records.
6. Do not collect authenticated, paywalled, access-controlled, personal-profile, or prohibited social-network content.
7. Re-review terms at least every 90 days and before changing collection scope or retention behavior.

## Primary references

- [GitHub REST API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
- [GitHub REST API best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)
- [GitHub organization endpoints](https://docs.github.com/en/rest/orgs/orgs)
- [GitHub Terms of Service](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service)
- [GitHub Acceptable Use Policies](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies)
- [SEC EDGAR developer resources](https://www.sec.gov/about/developer-resources)
- [SEC access and fair-access guidance](https://www.sec.gov/edgar/searchedgar/accessing-edgar-data.htm)
- [IETF RFC 9309: Robots Exclusion Protocol](https://datatracker.ietf.org/doc/html/rfc9309)
- [Sitemaps protocol](https://www.sitemaps.org/protocol.html)
- [RSS 2.0 specification](https://www.rssboard.org/rss-2-0-2)
- [`llms.txt` proposal](https://llmstxt.org/)

Content from linked sources was rephrased for compliance with licensing restrictions. This review intentionally records operational constraints rather than reproducing source terms; consult the linked current terms before deployment.
