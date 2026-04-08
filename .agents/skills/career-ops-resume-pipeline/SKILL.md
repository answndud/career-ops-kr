---
name: career-ops-resume-pipeline
description: Work on resume templates, rendering, and PDF generation without breaking the current output flow. Use when touching templates, example context, render-resume, or generate-pdf.
---

# Career Ops Resume Pipeline

Use this skill for resume output work.

## Read first

- `templates/resume-ko.html`
- `templates/resume-en.html`
- `examples/resume-context.example.json`
- `src/career_ops_kr/cli.py`
- `README.md`

## Workflow

1. Decide whether the change affects:
   - template structure
   - context schema
   - HTML rendering
   - PDF generation
2. Keep templates as Jinja HTML.
3. If context fields change, update:
   - example JSON
   - template references
   - any relevant docs
4. Validate by rendering HTML first, then generating PDF.

## Hard rules

- Do not replace Jinja templates with Python string concatenation.
- Do not leave validation PDFs or HTML files in `output/`.
- Do not change example context field names without updating both templates and docs.

## Validation

```bash
source .venv/bin/activate
career-ops-kr render-resume templates/resume-en.html examples/resume-context.example.json output/test-resume.html
career-ops-kr generate-pdf output/test-resume.html output/test-resume.pdf
rm -f output/test-resume.html output/test-resume.pdf
```
