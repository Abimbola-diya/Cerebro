# Research API Planning Notes (No Integration Yet)

This document captures planning-time settings for research tooling.
It is intentionally implementation-agnostic and can be converted into code profiles later.

## Saved Secrets Location
- Local secret file: .env.research.local
- Not committed due .gitignore rules.

## Recommended Search Stack Roles
- Tavily: broad web discovery, LLM-oriented ranking, news-mode retrieval
- Serper: Google-style targeted discovery, strong recency/location control
- DuckDuckGo: lightweight fallback and diversity source
- Firecrawl: deep page extraction, site crawl, and PDF extraction

## Planner vs Retrieval Link Policy
- Planner should provide seed sources and source hints, not a closed link list.
- Retrieval stage should expand beyond seed links and discover additional related URLs for the same query intent.
- Expansion should remain constrained by dimension policy, source quality filters, and budget limits.
- Any expanded link used in synthesis should still carry full metadata and citation provenance.

## Query Modes and Settings Profiles

### 1) Latest Breaking News (0-48h)
Use when query asks: latest, today, breaking, now, this week.

Tavily profile:
- topic: news
- search_depth: basic (switch to advanced if sparse)
- max_results: 8-12
- include_raw_content: false (true only for synthesis handoff)
- include_domains: trusted news + regulators
- Recency: set tight news window in client-side post-filter if API-side date filter is limited

Serper profile:
- endpoint: news
- num: 10
- gl: ng
- hl: en
- tbs: qdr:d (day) or qdr:w (week)

DuckDuckGo profile:
- backend: news
- timelimit: d or w
- region: ng-en
- max_results: 10

Firecrawl profile:
- use only on top 3-5 URLs after ranking
- extract depth: basic first
- format: markdown
- enable PDF parsing when article links to report/doc

### 2) Recent News Window (7-30 days)
Use when query asks: recent developments, last month, recent updates.

Tavily profile:
- topic: news
- search_depth: advanced
- max_results: 12-20
- include_raw_content: true for top sources
- include_domains/exclude_domains: enforce source quality boundaries

Serper profile:
- endpoint: news
- num: 20
- tbs: qdr:w or qdr:m
- gl: ng, hl: en

DuckDuckGo profile:
- backend: text + news blend
- timelimit: w or m
- deduplicate against Tavily/Serper set

Firecrawl profile:
- scrape top URLs + linked source docs
- parse PDF attachments where present
- timeout tuned for report-heavy pages

### 3) Regulatory / Policy Deep Dive
Use for dimensions 1 and 6 mostly.

Tavily profile:
- topic: general
- search_depth: advanced
- include_domains: regulator and institution domains only
- max_results: 15

Serper profile:
- endpoint: search
- site operators: official regulator/institution domains
- tbs: qdr:m or qdr:y depending policy horizon

Firecrawl profile:
- crawl official domains with selected paths
- use advanced extraction for tables and policy docs
- parse PDFs and archive links

### 4) Expert Opinion and Contrasting Views
Use for dimension 4.

Tavily profile:
- topic: general
- search_depth: advanced
- include_domains: approved expert/publication list
- exclude low-credibility domains

Serper profile:
- endpoint: search
- site-operator constrained to approved expert sources
- gather contrasting outlets intentionally

Firecrawl profile:
- scrape only selected expert pages for quote-quality evidence

## Firecrawl PDF Strategy
- Prefer scrape/extract for direct PDF URLs where supported
- If article links to PDF, follow link and extract structured text
- Preserve metadata: source_url, discovered_from, retrieved_at, mime_type=application/pdf

## Reliability and Cost Controls
- Two-pass retrieval:
  1) discovery pass (cheap settings)
  2) enrichment pass (deep extraction on top-ranked URLs)
- Deduplicate by normalized URL + title + content hash
- Enforce per-dimension budget caps before deep crawl
- Preserve expansion audit trail: store whether a URL came from planner seed list or executor discovery expansion.

## Recency Policy Guidance
- Latest mode: prioritize <= 48h, allow <= 7d fallback if sparse
- Recent mode: <= 30d default
- Foundational mode: allow older authoritative reports but mark as context

## Notes for Future Integration
- Convert these profiles into a config module, not inline literals.
- Keep provider-specific knobs in separate adapters.
- Add runtime profile selection by query intent and dimension.
- Keep all secrets in .env.research.local or deployment secret manager only.
