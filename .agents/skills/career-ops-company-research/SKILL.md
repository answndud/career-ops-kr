---
name: career-ops-company-research
description: Work on prepare-company-research, research briefs, and company-signal follow-up without mixing company research with intake or tracker mutation.
---

# Career Ops Company Research

Use this skill when touching the company research workflow.

## Read first

- `src/career_ops_kr/research.py`
- `prompts/company-research.md`
- `docs/workflows.md`
- `docs/portal-integration-strategy.md`
- `PLAN.md`
- `PROGRESS.md`

## Workflow

1. Identify whether the task changes:
   - `prepare-company-research` CLI behavior
   - `research/*.md` brief structure
   - JobPlanet / Blind / official source metadata
   - post-brief follow-up outputs such as summaries or outreach drafts
2. Keep company research separate from intake:
   - do not add crawler behavior here
   - do not mutate `data/pipeline.md`
   - do not mutate `data/applications.md`
3. If brief structure changes, update:
   - prompt seed
   - helper logic
   - docs and examples
4. If follow-up outputs are added, keep them downstream of an existing research brief instead of coupling them into portal intake commands.

## Hard rules

- Do not turn JobPlanet or Blind into discovery sources from this workflow.
- Do not mix company research outputs with tracker-addition TSV generation.
- Do not leave smoke research briefs behind after validation.

## Validation

```bash
source .venv/bin/activate
career-ops-kr prepare-company-research Toss --out research/_smoke_toss.md --homepage https://toss.im --careers-url https://toss.im/career/jobs
career-ops-kr prepare-company-followup research/_smoke_toss.md --mode summary --out research/_smoke_toss-summary.md
python -m unittest discover -s tests
rm -f research/_smoke_toss.md research/_smoke_toss-summary.md
```
