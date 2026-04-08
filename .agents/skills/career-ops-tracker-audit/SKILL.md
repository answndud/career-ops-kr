---
name: career-ops-tracker-audit
description: Safely modify tracker behavior, statuses, or merge logic without corrupting application data. Use when touching tracker rows, states, merge flow, or verification rules.
---

# Career Ops Tracker Audit

Use this skill before changing tracker-related files or data rules.

## Read first

- `data/applications.md`
- `config/states.yml`
- `AGENTS.md`
- `src/career_ops_kr/cli.py`
- `src/career_ops_kr/tracker.py`

## Workflow

1. Identify whether the task changes:
   - tracker data
   - canonical statuses
   - merge logic
   - normalization logic
   - verification logic
2. Keep `data/applications.md` as the source of truth.
3. Prefer `data/tracker-additions/**/*.tsv` plus `finalize-tracker` for the default apply path.
4. If statuses change, update:
   - `config/states.yml`
   - normalization logic
   - merge behavior
   - relevant docs
5. If validation behavior changes, re-run verification commands.

## Hard rules

- Do not invent a second tracker format.
- Do not change the applications markdown table shape without updating every consumer.
- Do not leave smoke-test TSV additions behind.

## Validation

```bash
source .venv/bin/activate
career-ops-kr finalize-tracker --help
career-ops-kr verify
```
