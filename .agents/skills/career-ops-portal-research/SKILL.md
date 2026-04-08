---
name: career-ops-portal-research
description: Research Korean job portals or company careers pages before implementing or updating an intake or discovery integration. Use when adding Wanted, Jumpit, RocketPunch, or other portal-specific intake behavior.
---

# Career Ops Portal Research

Use this skill before adding or changing a portal integration.

## Read first

- `config/portals.kr.example.yml`
- `docs/portal-integration-strategy.md`
- `PLAN.md`
- `PROGRESS.md`
- any existing portal-related code or docs for the target source

## Workflow

1. Identify the target portal or careers page.
2. Check the public page behavior.
3. Determine whether the page is:
   - static enough for `httpx` + HTML parsing
   - dynamic enough to require browser automation
   - blocked enough to require manual URL capture or a staged workflow
4. Capture the reliable entry points:
   - listing URL patterns
   - job detail URL patterns
   - obvious query parameters
   - visible identifiers or slugs
5. Note constraints:
   - authentication
   - rate limits or anti-bot behavior
   - locale or region dependencies
6. Propose the minimum implementation path.

## Output

Return:

- target portal
- recommended fetch strategy
- evidence URLs
- implementation risks
- exact config or code files likely to change

## Rules

- Do not hardcode brittle selectors without evidence from a current page.
- Separate observed facts from inferred behavior.
- If public access is insufficient, say so instead of guessing.
- Do not use this skill for `prepare-company-research` brief generation or company-review synthesis. That belongs to the company research workflow.
