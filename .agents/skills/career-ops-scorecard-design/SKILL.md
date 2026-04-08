---
name: career-ops-scorecard-design
description: Update or redesign job scoring criteria without breaking the current scoring pipeline. Use when changing weights, dimensions, thresholds, or role-specific scoring rules.
---

# Career Ops Scorecard Design

Use this skill when changing how jobs are scored.

## Read first

- `config/scorecard.kr.yml`
- `docs/scoring-kr.md`
- `prompts/evaluate-job.md`
- `src/career_ops_kr/cli.py`

If the change is role-specific, also read:

- `config/profile.example.yml`
- relevant portal or workflow docs

## Workflow

1. Identify which scoring dimensions change.
2. Keep the weight total coherent.
3. Check whether `score-job` in `src/career_ops_kr/cli.py` needs logic changes.
4. Update documentation and prompt guidance together.
5. Re-state how recommendation thresholds should behave after the change.

## Hard rules

- Do not change weights in `config/scorecard.kr.yml` without checking `score-job`.
- If you add or remove a dimension, update both code and docs in the same change.
- Keep the explanation tied to Korean developer hiring signals, not generic job-search advice.

## Validation

After changes, run:

```bash
source .venv/bin/activate
career-ops-kr verify
python -m compileall src
```
