---
name: career-ops-session-bootstrap
description: Load the current project state before starting work in this repository. Use at the start of a session, after context loss, or before proposing a multi-file change.
---

# Career Ops Session Bootstrap

Use this skill to rebuild working context before making decisions.

## Read first

- `PLAN.md`
- `PROGRESS.md`
- `AGENTS.md`
- `README.md`
- `docs/architecture.md`
- `docs/workflows.md`

If the task touches Codex-local automation, also read:

- `.codex/config.toml`
- relevant files in `.codex/agents/`
- relevant files in `.agents/skills/`

## Output

Summarize only the information needed to start work:

1. Current project goal
2. Already implemented CLI capabilities
3. Default workflow invariants that must not drift
4. Highest-priority open work
5. Likely files to change for this task
6. Validation commands to run after the change

## Rules

- Do not skip `PLAN.md` or `PROGRESS.md`.
- If the requested work conflicts with current project rules, say so before editing files.
- If the task only needs a small change, keep the bootstrap summary short.
- Call out the current default helper flow when relevant:
  - intake: `discover-jobs -> process-pipeline --score -> finalize-tracker`
  - company research: `prepare-company-research` stays separate from intake and tracker mutation
