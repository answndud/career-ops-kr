from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import yaml
from typer.testing import CliRunner

from career_ops_kr.cli import app
from career_ops_kr.pipeline import pipeline_lock_path
from career_ops_kr.research import create_company_research_brief

ROOT = Path(__file__).resolve().parents[1]
SCORECARD = ROOT / "config/scorecard.kr.yml"


def _write_test_live_smoke_targets_yaml(path: Path) -> Path:
    targets_path = path / "live-smoke-targets.yml"
    targets_path.write_text(
        yaml.safe_dump(
            {
                "targets": {
                    "remember_platform_ko": {
                        "candidates": [{"url": "https://career.rememberapp.co.kr/job/posting/293599", "source": "remember"}],
                        "base_context_path": "examples/resume-context.platform.ko.example.json",
                        "template_path": "templates/resume-ko.html",
                        "profile_path": "config/profile.example.yml",
                    },
                    "wanted_backend_ko": {
                        "candidates": [{"url": "https://www.wanted.co.kr/wd/157", "source": "wanted"}],
                        "base_context_path": "examples/resume-context.backend.ko.example.json",
                        "template_path": "templates/resume-ko.html",
                        "profile_path": "config/profile.example.yml",
                    },
                }
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return targets_path


class ScoreJobCliTest(unittest.TestCase):
    def test_score_job_accepts_profile_path_override(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "reliability-job.md"
            profile_path = temp_path / "profile.yml"
            report_path = temp_path / "reports" / "report.md"
            tracker_path = temp_path / "tracker" / "addition.tsv"

            profile_path.write_text(
                "\n".join(
                    [
                        "candidate:",
                        "  name: Override Test User",
                        "preferences:",
                        "  preferred_languages:",
                        "    - ko",
                        "    - en",
                        "  work_modes:",
                        "    preferred:",
                        "      - remote",
                        "    acceptable:",
                        "      - hybrid",
                        "skills:",
                        "  primary:",
                        "    - Terraform",
                        "    - Kubernetes",
                        "  secondary:",
                        "    - Observability",
                        "signals:",
                        "  preferred_domains:",
                        "    - reliability",
                        "  avoid_domains:",
                        "    - gambling",
                        "target_roles:",
                        "  - name: Experimental Reliability Engineer",
                        "    scorecard_profile: platform",
                        "    keywords:",
                        "      - reliability",
                        "      - sre",
                        "      - observability",
                        "      - terraform",
                    ]
                ),
                encoding="utf-8",
            )
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Experimental Reliability Engineer"',
                        'url: "https://example.com/jobs/reliability"',
                        'source: "manual"',
                        "---",
                        "",
                        "# Experimental Reliability Engineer",
                        "",
                        "Remote reliability engineering role focused on sre, terraform, kubernetes, and observability.",
                        "The team builds reliability tooling for internal platform customers.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                [
                    "score-job",
                    job_path.as_posix(),
                    "--out",
                    report_path.as_posix(),
                    "--tracker-out",
                    tracker_path.as_posix(),
                    "--profile-path",
                    profile_path.as_posix(),
                ],
            )

            self.assertEqual(0, result.exit_code, msg=result.output)
            self.assertTrue(report_path.exists())
            self.assertTrue(tracker_path.exists())

            report = report_path.read_text(encoding="utf-8")
            tracker = tracker_path.read_text(encoding="utf-8")

            self.assertIn("Selected Target Role: Experimental Reliability Engineer", report)
            self.assertIn("Selected Role Profile: Platform", report)
            self.assertIn(report_path.as_posix(), result.output)
            self.assertIn(tracker_path.as_posix(), result.output)
            self.assertIn("\tExperimental Reliability Engineer\t", tracker)

    def test_score_job_accepts_scorecard_path_override(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "reliability-job.md"
            profile_path = temp_path / "profile.yml"
            scorecard_path = temp_path / "scorecard.yml"
            report_path = temp_path / "reports" / "report.md"
            tracker_path = temp_path / "tracker" / "addition.tsv"

            profile_path.write_text(
                "\n".join(
                    [
                        "candidate:",
                        "  name: Override Test User",
                        "preferences:",
                        "  preferred_languages:",
                        "    - ko",
                        "    - en",
                        "  work_modes:",
                        "    preferred:",
                        "      - remote",
                        "    acceptable:",
                        "      - hybrid",
                        "skills:",
                        "  primary:",
                        "    - Terraform",
                        "    - Kubernetes",
                        "  secondary:",
                        "    - Observability",
                        "signals:",
                        "  preferred_domains:",
                        "    - reliability",
                        "  avoid_domains:",
                        "    - gambling",
                        "target_roles:",
                        "  - name: Experimental Reliability Engineer",
                        "    scorecard_profile: platform",
                        "    keywords:",
                        "      - reliability",
                        "      - sre",
                        "      - observability",
                        "      - terraform",
                    ]
                ),
                encoding="utf-8",
            )
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Experimental Reliability Engineer"',
                        'url: "https://example.com/jobs/reliability"',
                        'source: "manual"',
                        "---",
                        "",
                        "# Experimental Reliability Engineer",
                        "",
                        "Remote reliability engineering role focused on sre, terraform, kubernetes, and observability.",
                        "The team builds reliability tooling for internal platform customers.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            scorecard = yaml.safe_load(SCORECARD.read_text(encoding="utf-8"))
            scorecard["role_profiles"]["platform"]["weights"]["company_signal"] = 99
            scorecard_path.write_text(
                yaml.safe_dump(scorecard, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                [
                    "score-job",
                    job_path.as_posix(),
                    "--out",
                    report_path.as_posix(),
                    "--tracker-out",
                    tracker_path.as_posix(),
                    "--profile-path",
                    profile_path.as_posix(),
                    "--scorecard-path",
                    scorecard_path.as_posix(),
                ],
            )

            self.assertEqual(0, result.exit_code, msg=result.output)
            report = report_path.read_text(encoding="utf-8")

            self.assertIn("Selected Role Profile: Platform", report)
            self.assertIn("| company_signal | 99 |", report)

    def test_process_pipeline_score_accepts_profile_path_override(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            pipeline_path = temp_path / "pipeline.md"
            pipeline_path.write_text(
                "\n".join(
                    [
                        "# Pipeline Inbox",
                        "",
                        "## Pending",
                        "- [ ] https://example.com/jobs/reliability",
                        "",
                        "## Processed",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            profile_path = temp_path / "profile.yml"
            profile_path.write_text(
                "\n".join(
                    [
                        "candidate:",
                        "  name: Override Test User",
                        "preferences:",
                        "  preferred_languages:",
                        "    - ko",
                        "    - en",
                        "  work_modes:",
                        "    preferred:",
                        "      - remote",
                        "    acceptable:",
                        "      - hybrid",
                        "skills:",
                        "  primary:",
                        "    - Terraform",
                        "    - Kubernetes",
                        "  secondary:",
                        "    - Observability",
                        "signals:",
                        "  preferred_domains:",
                        "    - reliability",
                        "  avoid_domains:",
                        "    - gambling",
                        "target_roles:",
                        "  - name: Experimental Reliability Engineer",
                        "    scorecard_profile: platform",
                        "    keywords:",
                        "      - reliability",
                        "      - sre",
                        "      - observability",
                        "      - terraform",
                    ]
                ),
                encoding="utf-8",
            )
            scorecard_path = temp_path / "scorecard.yml"
            scorecard = yaml.safe_load(SCORECARD.read_text(encoding="utf-8"))
            scorecard["role_profiles"]["platform"]["weights"]["company_signal"] = 99
            scorecard_path.write_text(
                yaml.safe_dump(scorecard, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )

            out_dir = temp_path / "jds"
            report_dir = temp_path / "reports"
            tracker_dir = temp_path / "tracker-additions"

            def fake_fetch_job_to_markdown(
                url: str,
                *,
                out: Path | None = None,
                output_dir: Path | None = None,
                source: str = "manual",
                insecure: bool = False,
            ) -> Path:
                self.assertEqual("https://example.com/jobs/reliability", url)
                self.assertEqual("manual", source)
                self.assertFalse(insecure)
                self.assertIsNone(out)
                self.assertIsNotNone(output_dir)

                job_path = Path(output_dir or temp_path) / "fetched-reliability.md"
                job_path.parent.mkdir(parents=True, exist_ok=True)
                job_path.write_text(
                    "\n".join(
                        [
                            "---",
                            'title: "Experimental Reliability Engineer"',
                            'url: "https://example.com/jobs/reliability"',
                            'source: "manual"',
                            "---",
                            "",
                            "# Experimental Reliability Engineer",
                            "",
                            "Remote reliability engineering role focused on sre, terraform, kubernetes, and observability.",
                            "The team builds reliability tooling for internal platform customers.",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                return job_path

            with patch("career_ops_kr.commands.intake.fetch_job_to_markdown", side_effect=fake_fetch_job_to_markdown):
                result = runner.invoke(
                    app,
                    [
                        "process-pipeline",
                        "--pipeline",
                        pipeline_path.as_posix(),
                        "--limit",
                        "1",
                        "--out-dir",
                        out_dir.as_posix(),
                        "--score",
                        "--report-dir",
                        report_dir.as_posix(),
                        "--tracker-dir",
                        tracker_dir.as_posix(),
                        "--profile-path",
                        profile_path.as_posix(),
                        "--scorecard-path",
                        scorecard_path.as_posix(),
                    ],
                )

            self.assertEqual(0, result.exit_code, msg=result.output)
            self.assertIn("Saved: https://example.com/jobs/reliability", result.output)
            self.assertIn("Scored:", result.output)
            self.assertIn("Marked 1 pipeline item(s) as processed", result.output)

            report_paths = list(report_dir.glob("*.md"))
            tracker_paths = list(tracker_dir.glob("*.tsv"))
            self.assertEqual(1, len(report_paths))
            self.assertEqual(1, len(tracker_paths))

            report = report_paths[0].read_text(encoding="utf-8")
            pipeline_text = pipeline_path.read_text(encoding="utf-8")

            self.assertIn("Selected Target Role: Experimental Reliability Engineer", report)
            self.assertIn("Selected Role Profile: Platform", report)
            self.assertIn("| company_signal | 99 |", report)
            self.assertIn("- [x] https://example.com/jobs/reliability", pipeline_text)
            self.assertFalse(pipeline_lock_path(pipeline_path).exists())

    def test_finalize_tracker_merges_recursive_additions_directory(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            tracker_path = temp_path / "applications.md"
            additions_dir = temp_path / "tracker-additions" / "batch-1"
            additions_dir.mkdir(parents=True, exist_ok=True)
            (additions_dir / "entry.tsv").write_text(
                "\t".join(
                    [
                        "2026-04-06",
                        "Example Corp",
                        "Platform Engineer",
                        "4.2/5",
                        "review",
                        "remember",
                        "",
                        "reports/example.md",
                        "선별 검토",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                [
                    "finalize-tracker",
                    "--tracker-path",
                    tracker_path.as_posix(),
                    "--additions-dir",
                    (temp_path / "tracker-additions").as_posix(),
                    "--no-verify",
                ],
            )

            self.assertEqual(0, result.exit_code, msg=result.output)
            content = tracker_path.read_text(encoding="utf-8")

            self.assertIn("Merged 1 addition file(s)", result.output)
            self.assertIn("Tracker finalize complete.", result.output)
            self.assertIn("Example Corp", content)
            self.assertIn("Platform Engineer", content)
            self.assertIn("검토중", content)

    def test_audit_jobs_reports_tracker_and_legacy_output_findings(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            tracker_path = temp_path / "applications.md"
            output_dir = temp_path / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "legacy.html").write_text("<html></html>", encoding="utf-8")
            html_path = output_dir / "web-resumes" / "alpha-platform.html"
            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text("<html></html>", encoding="utf-8")
            html_path.with_suffix(".manifest.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "generated_at": "2026-04-11T00:00:00+00:00",
                        "build_run_id": "br_test",
                        "inventory_key": "web-resumes/alpha-platform.html",
                        "pipeline": "build_tailored_resume_from_url",
                        "job": {},
                        "selection": {},
                        "focus": {},
                        "paths": {
                            "job_path": None,
                            "report_path": None,
                            "tailoring_path": None,
                            "context_path": "output/resume-contexts/missing-context.json",
                            "html_path": "output/web-resumes/alpha-platform.html",
                            "pdf_path": None,
                            "base_context_path": None,
                            "template_path": None,
                            "profile_path": None,
                            "scorecard_path": None,
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (output_dir / "artifact-index.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "updated_at": "2026-04-11T00:00:00+00:00",
                        "entries": {
                            "web-resumes/alpha-platform.html": {
                                "inventory_key": "web-resumes/alpha-platform.html",
                                "build_run_id": "br_test",
                                "generated_at": "2026-04-11T00:00:00+00:00",
                                "pipeline": "build_tailored_resume_from_url",
                                "manifest_path": "output/web-resumes/wrong.manifest.json",
                                "html_path": "output/web-resumes/wrong.html",
                                "pdf_path": None,
                            }
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            report_path = temp_path / "reports" / "existing-report.md"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text("# Report", encoding="utf-8")
            tracker_path.write_text(
                "\n".join(
                    [
                        "# Applications Tracker",
                        "",
                        "| ID | Date | Company | Role | Score | Status | Source | Resume | Report | Notes |",
                        "|----|------|---------|------|-------|--------|--------|--------|--------|-------|",
                        f"| 1 | 2026-04-11 | Alpha | Platform Engineer | 4.5/5 | 지원예정 | remember |  | {report_path.relative_to(temp_path).as_posix()} | note |",
                        "| 2 | 2026-04-11 | Beta | Backend Engineer | 3.9/5 | 검토중 | wanted | output/missing-resume.html | reports/missing-report.md | note |",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                [
                    "audit-jobs",
                    "--tracker-path",
                    tracker_path.as_posix(),
                    "--repo-root",
                    temp_path.as_posix(),
                    "--output-dir",
                    output_dir.as_posix(),
                    "--json",
                ],
            )

            self.assertEqual(0, result.exit_code, msg=result.output)
            payload = json.loads(result.output)
            self.assertEqual(2, payload["tracker_row_count"])
            self.assertEqual(1, payload["counts"]["missing_resume"])
            self.assertEqual(1, payload["counts"]["missing_report_file"])
            self.assertEqual(1, payload["counts"]["missing_resume_file"])
            self.assertEqual(1, payload["counts"]["legacy_html"])
            self.assertEqual(1, payload["counts"]["manifest_missing_context_file"])
            self.assertEqual(1, payload["counts"]["artifact_index_entry_mismatch"])

            strict_result = runner.invoke(
                app,
                [
                    "audit-jobs",
                    "--tracker-path",
                    tracker_path.as_posix(),
                    "--repo-root",
                    temp_path.as_posix(),
                    "--output-dir",
                    output_dir.as_posix(),
                    "--strict",
                ],
            )
            self.assertEqual(1, strict_result.exit_code)
            self.assertIn("legacy_html", strict_result.output)


class CompanyResearchCliTest(unittest.TestCase):
    def test_prepare_company_followup_generates_summary_from_existing_brief(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            brief_path = create_company_research_brief(
                "Toss",
                out=temp_path / "toss-brief.md",
                homepage="https://toss.im",
                careers_url="https://toss.im/career/jobs",
            )
            followup_path = temp_path / "toss-summary.md"

            result = runner.invoke(
                app,
                [
                    "prepare-company-followup",
                    brief_path.as_posix(),
                    "--mode",
                    "summary",
                    "--out",
                    followup_path.as_posix(),
                ],
            )

            self.assertEqual(0, result.exit_code, msg=result.output)
            self.assertTrue(followup_path.exists())
            self.assertIn(followup_path.as_posix(), result.output)

            content = followup_path.read_text(encoding="utf-8")
            self.assertIn('mode: "summary"', content)
            self.assertIn("# Toss Research Summary", content)
            self.assertIn("- Homepage: https://toss.im", content)

    def test_prepare_company_followup_creates_summary_output(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            brief_path = create_company_research_brief(
                "Toss",
                out=temp_path / "toss-brief.md",
                homepage="https://toss.im",
                careers_url="https://toss.im/career/jobs",
            )
            followup_path = temp_path / "toss-summary.md"

            result = runner.invoke(
                app,
                [
                    "prepare-company-followup",
                    brief_path.as_posix(),
                    "--mode",
                    "summary",
                    "--out",
                    followup_path.as_posix(),
                ],
            )

            self.assertEqual(0, result.exit_code, msg=result.output)
            self.assertTrue(followup_path.exists())
            content = followup_path.read_text(encoding="utf-8")

            self.assertIn("# Toss Research Summary", content)
            self.assertIn("- Homepage: https://toss.im", content)
            self.assertIn(followup_path.as_posix(), result.output)


class ResumeCliTest(unittest.TestCase):
    def test_prepare_resume_tailoring_generates_json_packet(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "job.md"
            report_path = temp_path / "report.md"
            base_context_path = temp_path / "resume-context.json"
            output_path = temp_path / "tailoring.json"

            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Senior Platform Engineer"',
                        'company: "Example Corp"',
                        'url: "https://example.com/jobs/platform"',
                        'source: "remember"',
                        "---",
                        "",
                        "Kubernetes, terraform, aws, and observability for platform engineering.",
                    ]
                ),
                encoding="utf-8",
            )
            report_path.write_text(
                "\n".join(
                    [
                        "# Example Corp - Senior Platform Engineer",
                        "",
                        "## Summary",
                        "",
                        "- Date: 2026-04-06",
                        "- Source: remember",
                        "- URL: https://example.com/jobs/platform",
                        "- Selected Domain: Platform",
                        "- Selected Target Role: Senior Platform Engineer",
                        "- Selected Role Profile: Platform",
                        "- Total Score: 4.2/5",
                        "- Recommendation: 지원 적극 검토",
                        "- Seniority Signal: senior",
                        "- Work Mode Signal: remote",
                        "- Language Signal: ko, en",
                        "",
                        "## Why It Fits",
                        "",
                        "- Role keyword overlap: 3/6",
                        "",
                        "## Risks",
                        "",
                        "- Compensation disclosed: no clear signal",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            base_context_path.write_text(
                json.dumps(
                    {
                        "headline": "Platform Engineer",
                        "skills": ["AWS", "Terraform"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                [
                    "prepare-resume-tailoring",
                    job_path.as_posix(),
                    report_path.as_posix(),
                    "--base-context",
                    base_context_path.as_posix(),
                    "--scorecard-path",
                    SCORECARD.as_posix(),
                    "--out",
                    output_path.as_posix(),
                ],
            )

            self.assertEqual(0, result.exit_code, msg=result.output)
            self.assertTrue(output_path.exists())
            self.assertIn(output_path.as_posix(), result.output)

            packet = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("Platform", packet["selection"]["selected_role_profile"])
            self.assertIn("AWS", packet["tailoring"]["matched_resume_skills"])
            self.assertIn("kubernetes", [item.lower() for item in packet["tailoring"]["skills_to_emphasize"]])

    def test_apply_resume_tailoring_generates_tailored_context(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            tailoring_path = temp_path / "tailoring.json"
            base_context_path = temp_path / "resume-context.json"
            output_path = temp_path / "tailored-context.json"

            tailoring_path.write_text(
                json.dumps(
                    {
                        "job": {
                            "company": "Example Corp",
                            "title": "Senior Platform Engineer",
                        },
                        "selection": {
                            "selected_domain": "Platform",
                            "selected_target_role": "Senior Platform Engineer",
                            "selected_role_profile": "Platform",
                            "total_score": 4.2,
                            "recommendation": "지원 적극 검토",
                        },
                        "tailoring": {
                            "headline": "Senior Platform Engineer",
                            "summary": "Resume version for Senior Platform Engineer with emphasis on terraform and aws.",
                            "skills_to_emphasize": ["Terraform", "AWS"],
                            "matched_resume_skills": ["Terraform", "AWS"],
                            "missing_focus_keywords": ["Kubernetes"],
                            "experience_focus": ["Move platform bullets higher."],
                            "project_focus": ["Highlight infra migration work."],
                            "keywords": ["Terraform", "AWS"],
                            "notes": ["Recommendation from score report: 지원 적극 검토"],
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            base_context_path.write_text(
                json.dumps(
                    {
                        "headline": "Backend Engineer",
                        "summary": "Base summary.",
                        "skills": ["Python", "AWS", "Terraform"],
                        "experience": [
                            {"role": "Platform Engineer", "bullets": ["Terraform and AWS platform work."]},
                            {"role": "Backend Engineer", "bullets": ["CRUD APIs for business services."]},
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                [
                    "apply-resume-tailoring",
                    tailoring_path.as_posix(),
                    base_context_path.as_posix(),
                    "--out",
                    output_path.as_posix(),
                ],
            )

            self.assertEqual(0, result.exit_code, msg=result.output)
            self.assertTrue(output_path.exists())
            self.assertIn(output_path.as_posix(), result.output)

            tailored_context = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("Senior Platform Engineer", tailored_context["headline"])
            self.assertEqual(["AWS", "Terraform", "Python"], tailored_context["skills"])
            self.assertEqual("Platform Engineer", tailored_context["experience"][0]["role"])
            self.assertEqual("Platform", tailored_context["tailoringGuidance"]["selection"]["selected_role_profile"])

    def test_build_tailored_resume_runs_prepare_apply_render_chain(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = ROOT / "tests" / "fixtures" / "remember_platform_job.md"
            report_path = ROOT / "tests" / "fixtures" / "remember_platform_report.md"
            base_context_path = ROOT / "examples" / "resume-context.platform.ko.example.json"
            template_path = ROOT / "templates" / "resume-ko.html"
            html_path = temp_path / "resume.html"
            tailoring_path = temp_path / "tailoring.json"
            context_path = temp_path / "context.json"

            result = runner.invoke(
                app,
                [
                    "build-tailored-resume",
                    job_path.as_posix(),
                    report_path.as_posix(),
                    base_context_path.as_posix(),
                    template_path.as_posix(),
                    "--html-out",
                    html_path.as_posix(),
                    "--tailoring-out",
                    tailoring_path.as_posix(),
                    "--context-out",
                    context_path.as_posix(),
                    "--scorecard-path",
                    SCORECARD.as_posix(),
                ],
            )

            self.assertEqual(0, result.exit_code, msg=result.output)
            self.assertTrue(html_path.exists())
            self.assertTrue(tailoring_path.exists())
            self.assertTrue(context_path.exists())
            self.assertIn(f"Tailoring: {tailoring_path.as_posix()}", result.output)
            self.assertIn(f"Tailored context: {context_path.as_posix()}", result.output)
            self.assertIn(f"HTML: {html_path.as_posix()}", result.output)

            rendered = html_path.read_text(encoding="utf-8")
            self.assertIn("홍길동", rendered)
            self.assertIn("Platform Engineer", rendered)

    def test_build_tailored_resume_from_url_runs_full_chain_without_tracker_side_effect(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "job.md"
            report_path = temp_path / "report.md"
            tailoring_path = temp_path / "tailoring.json"
            context_path = temp_path / "context.json"
            html_path = temp_path / "resume.html"
            profile_path = ROOT / "config" / "profile.example.yml"
            base_context_path = ROOT / "examples" / "resume-context.platform.ko.example.json"
            template_path = ROOT / "templates" / "resume-ko.html"
            fixture_job = (ROOT / "tests" / "fixtures" / "remember_platform_job.md").read_text(encoding="utf-8")

            def fake_fetch_job_to_markdown(
                url: str,
                *,
                out: Path | None = None,
                output_dir: Path | None = None,
                source: str = "manual",
                insecure: bool = False,
            ) -> Path:
                self.assertEqual("https://career.rememberapp.co.kr/job/posting/293599", url)
                self.assertEqual(job_path, out)
                self.assertEqual("remember", source)
                self.assertFalse(insecure)
                out.write_text(fixture_job, encoding="utf-8")
                return out

            with patch("career_ops_kr.commands.resume.fetch_job_to_markdown", side_effect=fake_fetch_job_to_markdown):
                result = runner.invoke(
                    app,
                    [
                        "build-tailored-resume-from-url",
                        "https://career.rememberapp.co.kr/job/posting/293599",
                        base_context_path.as_posix(),
                        template_path.as_posix(),
                        "--job-out",
                        job_path.as_posix(),
                        "--report-out",
                        report_path.as_posix(),
                        "--tailoring-out",
                        tailoring_path.as_posix(),
                        "--context-out",
                        context_path.as_posix(),
                        "--html-out",
                        html_path.as_posix(),
                        "--profile-path",
                        profile_path.as_posix(),
                        "--scorecard-path",
                        SCORECARD.as_posix(),
                    ],
                )

            self.assertEqual(0, result.exit_code, msg=result.output)
            self.assertTrue(job_path.exists())
            self.assertTrue(report_path.exists())
            self.assertTrue(tailoring_path.exists())
            self.assertTrue(context_path.exists())
            self.assertTrue(html_path.exists())
            rendered = html_path.read_text(encoding="utf-8")
            self.assertIn("홍길동", rendered)
            self.assertIn("요약", rendered)
            self.assertIn(f"Job: {job_path.as_posix()}", result.output)
            self.assertIn(f"Report: {report_path.as_posix()}", result.output)
            self.assertIn(f"HTML: {html_path.as_posix()}", result.output)
            self.assertNotIn("Tracker addition:", result.output)

    def test_smoke_live_resume_reports_cleanup_when_artifacts_are_not_kept(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            out_dir = temp_path / "live-smoke"

            def fake_run_live_resume_smoke(**kwargs):
                return type("Artifacts", (), {
                    "run_dir": out_dir,
                    "job_path": out_dir / "job.md",
                    "report_path": out_dir / "report.md",
                    "tailoring_path": out_dir / "tailoring.json",
                    "tailored_context_path": out_dir / "context.json",
                    "html_path": out_dir / "resume.html",
                    "pdf_path": None,
                    "selected_url": "https://career.rememberapp.co.kr/job/posting/293599",
                    "candidate_label": "primary",
                    "used_fallback": False,
                    "cleaned": True,
                })()

            with patch("career_ops_kr.cli.run_live_resume_smoke", side_effect=fake_run_live_resume_smoke):
                result = runner.invoke(
                    app,
                    [
                        "smoke-live-resume",
                        "--url",
                        "https://career.rememberapp.co.kr/job/posting/293599",
                    ],
                )

            self.assertEqual(0, result.exit_code, msg=result.output)
            self.assertIn("Live smoke OK for https://career.rememberapp.co.kr/job/posting/293599", result.output)
            self.assertIn("Selected URL: https://career.rememberapp.co.kr/job/posting/293599", result.output)
            self.assertIn("Artifacts cleaned after successful smoke run.", result.output)

    def test_smoke_live_resume_writes_json_report_when_requested(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            report_path = temp_path / "single-live-smoke.json"
            out_dir = temp_path / "live-smoke"

            def fake_run_live_resume_smoke(**kwargs):
                return type("Artifacts", (), {
                    "run_dir": out_dir,
                    "job_path": out_dir / "job.md",
                    "report_path": out_dir / "report.md",
                    "tailoring_path": out_dir / "tailoring.json",
                    "tailored_context_path": out_dir / "context.json",
                    "html_path": out_dir / "resume.html",
                    "pdf_path": None,
                    "selected_url": "https://career.rememberapp.co.kr/job/posting/293599",
                    "candidate_label": "primary",
                    "used_fallback": False,
                    "cleaned": True,
                })()

            with patch("career_ops_kr.cli.run_live_resume_smoke", side_effect=fake_run_live_resume_smoke):
                result = runner.invoke(
                    app,
                    [
                        "smoke-live-resume",
                        "--target",
                        "remember_platform_ko",
                        "--report-out",
                        report_path.as_posix(),
                    ],
                )

            self.assertEqual(0, result.exit_code, msg=result.output)
            self.assertIn(f"Smoke report: {report_path.as_posix()}", result.output)
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual("remember_platform_ko", payload["target"])
            self.assertEqual(
                "https://career.rememberapp.co.kr/job/posting/293599",
                payload["selected_url"],
            )

    def test_list_live_smoke_targets_prints_registered_targets(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["list-live-smoke-targets"])
        self.assertEqual(0, result.exit_code, msg=result.output)
        self.assertIn("remember_platform_ko:", result.output)
        self.assertIn("candidates=2", result.output)
        self.assertIn("remember_platform_en:", result.output)
        self.assertIn("remember_backend_ko:", result.output)
        self.assertIn("remember_data_ai_ko:", result.output)
        self.assertIn("wanted_backend_ko:", result.output)
        self.assertIn("jumpit_data_ai_ko:", result.output)

    def test_show_live_smoke_report_prints_human_readable_summary(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            report_path = temp_path / "live-smoke.json"
            report_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-07T06:19:28Z",
                        "targets_path": "config/live-smoke-targets.yml",
                        "target": "remember_platform_ko",
                        "selected_url": "https://career.rememberapp.co.kr/job/posting/293599",
                        "candidate_label": "primary",
                        "used_fallback": False,
                        "cleaned": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            result = runner.invoke(app, ["show-live-smoke-report", report_path.as_posix()])

        self.assertEqual(0, result.exit_code, msg=result.output)
        self.assertIn(f"Report: {report_path.as_posix()}", result.output)
        self.assertIn("Type: single", result.output)
        self.assertIn("Target: remember_platform_ko", result.output)
        self.assertIn("Selected URL: https://career.rememberapp.co.kr/job/posting/293599", result.output)

    def test_show_live_smoke_report_can_resolve_latest_matching_report(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "older.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-07T06:19:28Z",
                        "targets_path": "config/live-smoke-targets.yml",
                        "selected_targets": ["remember_platform_ko", "wanted_backend_ko"],
                        "success_count": 1,
                        "failure_count": 1,
                        "successes": [
                            {
                                "target": "remember_platform_ko",
                                "selected_url": "https://career.rememberapp.co.kr/job/posting/293599",
                                "candidate_label": "primary",
                                "used_fallback": False,
                            }
                        ],
                        "failures": [{"target": "wanted_backend_ko", "message": "network failed"}],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            latest_path = temp_path / "latest.json"
            latest_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T06:19:28Z",
                        "targets_path": "config/live-smoke-targets.yml",
                        "selected_targets": ["remember_platform_ko"],
                        "success_count": 1,
                        "failure_count": 0,
                        "successes": [
                            {
                                "target": "remember_platform_ko",
                                "selected_url": "https://career.rememberapp.co.kr/job/posting/275546",
                                "candidate_label": "fallback-devops",
                                "used_fallback": True,
                            }
                        ],
                        "failures": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                [
                    "show-live-smoke-report",
                    "--latest-from",
                    temp_path.as_posix(),
                    "--type",
                    "batch",
                    "--target",
                    "remember_platform_ko",
                    "--used-fallback-only",
                ],
            )

        self.assertEqual(0, result.exit_code, msg=result.output)
        self.assertIn(f"Report: {latest_path.as_posix()}", result.output)
        self.assertIn("Type: batch", result.output)
        self.assertIn("SUCCESS remember_platform_ko: https://career.rememberapp.co.kr/job/posting/275546 | fallback | label=fallback-devops", result.output)

    def test_show_live_smoke_report_rejects_mixed_path_and_latest_from(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            report_path = temp_path / "live-smoke.json"
            report_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-07T06:19:28Z",
                        "targets_path": "config/live-smoke-targets.yml",
                        "target": "remember_platform_ko",
                        "selected_url": "https://career.rememberapp.co.kr/job/posting/293599",
                        "candidate_label": "primary",
                        "used_fallback": False,
                        "cleaned": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                [
                    "show-live-smoke-report",
                    report_path.as_posix(),
                    "--latest-from",
                    temp_path.as_posix(),
                ],
            )

        self.assertEqual(2, result.exit_code, msg=result.output)
        self.assertIn("Pass a report path or use --latest-from, not both.", result.output)

    def test_show_live_smoke_report_requires_path_or_latest_from(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["show-live-smoke-report"])
        self.assertEqual(2, result.exit_code, msg=result.output)
        self.assertIn("Pass a report path or use --latest-from.", result.output)

    def test_show_live_smoke_report_latest_from_reports_filter_and_ignored_json_on_no_match(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "broken.json").write_text("{not-json}\n", encoding="utf-8")
            (temp_path / "single.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T06:19:28Z",
                        "targets_path": "config/live-smoke-targets.yml",
                        "target": "remember_platform_ko",
                        "selected_url": "https://career.rememberapp.co.kr/job/posting/293599",
                        "candidate_label": "primary",
                        "used_fallback": False,
                        "cleaned": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                [
                    "show-live-smoke-report",
                    "--latest-from",
                    temp_path.as_posix(),
                    "--type",
                    "batch",
                    "--failed-only",
                ],
            )

        self.assertEqual(2, result.exit_code, msg=result.output)
        self.assertIn("No matching live smoke reports found in", result.output)
        self.assertIn(temp_path.as_posix(), result.output)
        self.assertIn("filters:", result.output)
        self.assertIn("type=batch", result.output)
        self.assertIn("failed_only=true", result.output)
        self.assertIn("recognized reports: 1", result.output)
        self.assertIn("Ignored", result.output)
        self.assertIn("invalid/unrecognized JSON files: 1", result.output)

    def test_list_live_smoke_reports_no_match_prints_filter_and_ignored_summary(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "broken.json").write_text("{not-json}\n", encoding="utf-8")
            (temp_path / "single.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T06:19:28Z",
                        "targets_path": "config/live-smoke-targets.yml",
                        "target": "remember_platform_ko",
                        "selected_url": "https://career.rememberapp.co.kr/job/posting/293599",
                        "candidate_label": "primary",
                        "used_fallback": False,
                        "cleaned": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                [
                    "list-live-smoke-reports",
                    temp_path.as_posix(),
                    "--type",
                    "batch",
                    "--failed-only",
                ],
            )

        self.assertEqual(0, result.exit_code, msg=result.output)
        self.assertIn(f"No matching live smoke reports found in {temp_path.as_posix()}", result.output)
        self.assertIn("filters: type=batch, failed_only=true", result.output)
        self.assertIn("recognized reports: 1", result.output)
        self.assertIn("Ignored invalid/unrecognized JSON files: 1", result.output)

    def test_compare_live_smoke_reports_prints_changed_targets(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            base_path = temp_path / "base.json"
            current_path = temp_path / "current.json"
            base_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-07T06:19:28Z",
                        "targets_path": "config/live-smoke-targets.yml",
                        "selected_targets": ["remember_platform_ko"],
                        "success_count": 1,
                        "failure_count": 0,
                        "successes": [
                            {
                                "target": "remember_platform_ko",
                                "selected_url": "https://career.rememberapp.co.kr/job/posting/293599",
                                "candidate_label": "primary",
                                "used_fallback": False,
                            }
                        ],
                        "failures": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            current_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T06:19:28Z",
                        "targets_path": "config/live-smoke-targets.yml",
                        "selected_targets": ["remember_platform_ko"],
                        "success_count": 1,
                        "failure_count": 0,
                        "successes": [
                            {
                                "target": "remember_platform_ko",
                                "selected_url": "https://career.rememberapp.co.kr/job/posting/275546",
                                "candidate_label": "fallback-devops",
                                "used_fallback": True,
                            }
                        ],
                        "failures": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                ["compare-live-smoke-reports", base_path.as_posix(), current_path.as_posix()],
            )

        self.assertEqual(0, result.exit_code, msg=result.output)
        self.assertIn(f"Base report: {base_path.as_posix()}", result.output)
        self.assertIn(f"Current report: {current_path.as_posix()}", result.output)
        self.assertIn("Changed targets: 1", result.output)
        self.assertIn(
            "CHANGED remember_platform_ko: https://career.rememberapp.co.kr/job/posting/293599 -> https://career.rememberapp.co.kr/job/posting/275546 | primary -> fallback",
            result.output,
        )

    def test_compare_live_smoke_reports_can_resolve_latest_pair(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "previous.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T07:19:28Z",
                        "targets_path": "config/live-smoke-targets.yml",
                        "selected_targets": ["remember_platform_ko"],
                        "success_count": 1,
                        "failure_count": 0,
                        "successes": [
                            {
                                "target": "remember_platform_ko",
                                "selected_url": "https://career.rememberapp.co.kr/job/posting/293599",
                                "candidate_label": "primary",
                                "used_fallback": False,
                            }
                        ],
                        "failures": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            latest_path = temp_path / "latest.json"
            latest_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T08:19:28Z",
                        "targets_path": "config/live-smoke-targets.yml",
                        "selected_targets": ["remember_platform_ko"],
                        "success_count": 1,
                        "failure_count": 0,
                        "successes": [
                            {
                                "target": "remember_platform_ko",
                                "selected_url": "https://career.rememberapp.co.kr/job/posting/275546",
                                "candidate_label": "fallback-devops",
                                "used_fallback": True,
                            }
                        ],
                        "failures": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                [
                    "compare-live-smoke-reports",
                    "--latest-from",
                    temp_path.as_posix(),
                    "--type",
                    "batch",
                    "--target",
                    "remember_platform_ko",
                ],
            )

        self.assertEqual(0, result.exit_code, msg=result.output)
        self.assertIn("Base report:", result.output)
        self.assertIn("Current report:", result.output)
        self.assertIn(f"Current report: {latest_path.as_posix()}", result.output)
        self.assertIn("Changed targets: 1", result.output)

    def test_compare_live_smoke_reports_latest_from_fails_when_only_one_match_exists(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "only.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T08:19:28Z",
                        "targets_path": "config/live-smoke-targets.yml",
                        "selected_targets": ["remember_platform_ko"],
                        "success_count": 1,
                        "failure_count": 0,
                        "successes": [
                            {
                                "target": "remember_platform_ko",
                                "selected_url": "https://career.rememberapp.co.kr/job/posting/275546",
                                "candidate_label": "fallback-devops",
                                "used_fallback": True,
                            }
                        ],
                        "failures": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                [
                    "compare-live-smoke-reports",
                    "--latest-from",
                    temp_path.as_posix(),
                    "--type",
                    "batch",
                    "--target",
                    "remember_platform_ko",
                ],
            )

        self.assertEqual(2, result.exit_code, msg=result.output)
        self.assertIn("Need at least 2 matching live smoke reports", result.output)
        self.assertIn("recognized reports: 1", result.output)

    def test_compare_live_smoke_reports_rejects_mixed_paths_and_latest_from(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            base_path = temp_path / "base.json"
            current_path = temp_path / "current.json"
            base_path.write_text('{"selected_url":"https://example.com","target":"t"}\n', encoding="utf-8")
            current_path.write_text('{"selected_url":"https://example.com/2","target":"t"}\n', encoding="utf-8")

            result = runner.invoke(
                app,
                [
                    "compare-live-smoke-reports",
                    base_path.as_posix(),
                    current_path.as_posix(),
                    "--latest-from",
                    temp_path.as_posix(),
                ],
            )

        self.assertEqual(2, result.exit_code, msg=result.output)
        self.assertIn("Pass two report paths or use --latest-from, not both.", result.output)

    def test_list_live_smoke_reports_prints_saved_reports_only(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "single.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T06:19:28Z",
                        "targets_path": "config/live-smoke-targets.yml",
                        "target": "remember_platform_ko",
                        "selected_url": "https://career.rememberapp.co.kr/job/posting/293599",
                        "candidate_label": "primary",
                        "used_fallback": False,
                        "cleaned": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (temp_path / "batch.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-07T06:19:28Z",
                        "targets_path": "config/live-smoke-targets.yml",
                        "selected_targets": ["remember_platform_ko"],
                        "success_count": 1,
                        "failure_count": 0,
                        "successes": [],
                        "failures": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (temp_path / "other.json").write_text('{"name":"ignore"}\n', encoding="utf-8")

            result = runner.invoke(app, ["list-live-smoke-reports", temp_path.as_posix()])

        self.assertEqual(0, result.exit_code, msg=result.output)
        self.assertIn("single.json | single | 2026-04-08T06:19:28Z | target=remember_platform_ko", result.output)
        self.assertIn(
            "batch.json | batch | 2026-04-07T06:19:28Z | targets=remember_platform_ko | success=1 | failure=0 | fallback-hits=0",
            result.output,
        )
        self.assertNotIn("other.json", result.output)

    def test_list_live_smoke_reports_applies_cli_filters(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "single.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T06:19:28Z",
                        "targets_path": "config/live-smoke-targets.yml",
                        "target": "remember_platform_ko",
                        "selected_url": "https://career.rememberapp.co.kr/job/posting/293599",
                        "candidate_label": "primary",
                        "used_fallback": False,
                        "cleaned": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (temp_path / "batch.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T08:19:28Z",
                        "targets_path": "config/live-smoke-targets.yml",
                        "selected_targets": ["remember_platform_ko", "wanted_backend_ko"],
                        "success_count": 1,
                        "failure_count": 1,
                        "successes": [
                            {
                                "target": "remember_platform_ko",
                                "selected_url": "https://career.rememberapp.co.kr/job/posting/275546",
                                "used_fallback": True,
                                "candidate_label": "fallback-devops",
                            }
                        ],
                        "failures": [
                            {
                                "target": "wanted_backend_ko",
                                "message": "network failed",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                [
                    "list-live-smoke-reports",
                    temp_path.as_posix(),
                    "--type",
                    "batch",
                    "--target",
                    "remember_platform_ko",
                    "--latest",
                    "1",
                    "--used-fallback-only",
                    "--failed-only",
                ],
            )

        self.assertEqual(0, result.exit_code, msg=result.output)
        self.assertIn(
            "batch.json | batch | 2026-04-08T08:19:28Z | targets=remember_platform_ko,wanted_backend_ko | success=1 | failure=1 | fallback-hits=1",
            result.output,
        )
        self.assertNotIn("single.json", result.output)

    def test_list_live_smoke_reports_can_show_latest_per_target(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "older-batch.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T07:19:28Z",
                        "targets_path": "config/live-smoke-targets.yml",
                        "selected_targets": ["remember_platform_ko", "wanted_backend_ko"],
                        "success_count": 1,
                        "failure_count": 1,
                        "successes": [
                            {
                                "target": "remember_platform_ko",
                                "selected_url": "https://career.rememberapp.co.kr/job/posting/293599",
                                "candidate_label": "primary",
                                "used_fallback": False,
                            }
                        ],
                        "failures": [
                            {
                                "target": "wanted_backend_ko",
                                "message": "network failed",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (temp_path / "latest-single.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T08:19:28Z",
                        "targets_path": "config/live-smoke-targets.yml",
                        "target": "remember_platform_ko",
                        "selected_url": "https://career.rememberapp.co.kr/job/posting/275546",
                        "candidate_label": "fallback-devops",
                        "used_fallback": True,
                        "cleaned": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                [
                    "list-live-smoke-reports",
                    temp_path.as_posix(),
                    "--latest-per-target",
                ],
            )

        self.assertEqual(0, result.exit_code, msg=result.output)
        self.assertIn(
            "remember_platform_ko | 2026-04-08T08:19:28Z | success | single | url=https://career.rememberapp.co.kr/job/posting/275546 | fallback",
            result.output,
        )
        self.assertIn(
            "wanted_backend_ko | 2026-04-08T07:19:28Z | failure | batch | message=network failed",
            result.output,
        )

    def test_list_live_smoke_reports_rejects_latest_and_latest_per_target_together(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            result = runner.invoke(
                app,
                [
                    "list-live-smoke-reports",
                    temp_path.as_posix(),
                    "--latest",
                    "1",
                    "--latest-per-target",
                ],
            )

        self.assertEqual(2, result.exit_code, msg=result.output)
        self.assertIn("Use --latest or --latest-per-target, not both.", result.output)

    def test_list_live_smoke_reports_rejects_invalid_type_filter(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            result = runner.invoke(
                app,
                ["list-live-smoke-reports", temp_path.as_posix(), "--type", "weekly"],
            )

        self.assertEqual(2, result.exit_code, msg=result.output)
        self.assertIn("Unsupported live smoke report type filter: weekly", result.output)

    def test_validate_live_smoke_targets_reports_target_count(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["validate-live-smoke-targets"])
        self.assertEqual(0, result.exit_code, msg=result.output)
        self.assertIn("Validated 6 live smoke target(s)", result.output)
        self.assertIn("Targets with fallback candidates: 6", result.output)
        self.assertIn("Fallback coverage: 6/6", result.output)
        self.assertIn("Targets with more than 2 candidates: 0", result.output)
        self.assertIn("Single-candidate targets: none", result.output)
        self.assertNotIn("Warning: some live smoke targets still depend on a single public URL.", result.output)
        self.assertNotIn(
            "Warning: some live smoke targets have more than 2 candidates. Consider pruning or splitting them.",
            result.output,
        )

    def test_validate_live_smoke_targets_strict_passes_when_all_targets_have_fallback_candidates(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["validate-live-smoke-targets", "--strict"])
        self.assertEqual(0, result.exit_code, msg=result.output)
        self.assertIn("Fallback coverage: 6/6", result.output)
        self.assertIn("Targets with more than 2 candidates: 0", result.output)

    def test_validate_live_smoke_targets_max_candidates_fails_when_threshold_exceeded(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["validate-live-smoke-targets", "--max-candidates", "1"])
        self.assertEqual(1, result.exit_code, msg=result.output)
        self.assertIn(
            "Targets exceeding max candidates (1): remember_platform_ko, remember_platform_en, remember_backend_ko, remember_data_ai_ko, wanted_backend_ko, jumpit_data_ai_ko",
            result.output,
        )

    def test_validate_live_smoke_targets_max_candidates_passes_when_threshold_allows_current_registry(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["validate-live-smoke-targets", "--max-candidates", "2"])
        self.assertEqual(0, result.exit_code, msg=result.output)
        self.assertIn("Targets with more than 2 candidates: 0", result.output)

    def test_validate_live_smoke_reports_passes_for_fresh_successful_targets(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            targets_path = _write_test_live_smoke_targets_yaml(temp_path)
            now = datetime.now(UTC)
            (temp_path / "batch.json").write_text(
                json.dumps(
                    {
                        "generated_at": (now - timedelta(minutes=30)).isoformat(),
                        "targets_path": targets_path.as_posix(),
                        "selected_targets": ["remember_platform_ko", "wanted_backend_ko"],
                        "success_count": 2,
                        "failure_count": 0,
                        "successes": [
                            {
                                "target": "remember_platform_ko",
                                "selected_url": "https://career.rememberapp.co.kr/job/posting/293599",
                                "candidate_label": "primary",
                                "used_fallback": False,
                            },
                            {
                                "target": "wanted_backend_ko",
                                "selected_url": "https://www.wanted.co.kr/wd/157",
                                "candidate_label": "primary",
                                "used_fallback": False,
                            },
                        ],
                        "failures": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                [
                    "validate-live-smoke-reports",
                    temp_path.as_posix(),
                    "--targets-path",
                    targets_path.as_posix(),
                    "--max-age-hours",
                    "24",
                ],
            )

        self.assertEqual(0, result.exit_code, msg=result.output)
        self.assertIn("Validated latest live smoke report status for 2 target(s)", result.output)
        self.assertIn("OK remember_platform_ko", result.output)
        self.assertIn("OK wanted_backend_ko", result.output)
        self.assertIn("Live smoke report health summary: 2 ok, 0 failing.", result.output)

    def test_validate_live_smoke_reports_fails_for_missing_or_stale_targets(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            targets_path = _write_test_live_smoke_targets_yaml(temp_path)
            now = datetime.now(UTC)
            (temp_path / "single.json").write_text(
                json.dumps(
                    {
                        "generated_at": (now - timedelta(hours=48)).isoformat(),
                        "targets_path": targets_path.as_posix(),
                        "target": "remember_platform_ko",
                        "selected_url": "https://career.rememberapp.co.kr/job/posting/293599",
                        "candidate_label": "primary",
                        "used_fallback": False,
                        "cleaned": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                [
                    "validate-live-smoke-reports",
                    temp_path.as_posix(),
                    "--targets-path",
                    targets_path.as_posix(),
                    "--max-age-hours",
                    "24",
                ],
            )

        self.assertEqual(1, result.exit_code, msg=result.output)
        self.assertIn("STALE remember_platform_ko", result.output)
        self.assertIn("MISSING wanted_backend_ko", result.output)
        self.assertIn("Live smoke report health summary: 0 ok, 2 failing.", result.output)

    def test_smoke_live_resume_batch_reports_mixed_results(self) -> None:
        runner = CliRunner()

        def fake_run_batch_live_resume_smoke(**kwargs):
            self.assertEqual(["remember_platform_ko", "remember_platform_en"], kwargs["target_keys"])
            return type("BatchResult", (), {
                "successes": [
                    ("remember_platform_ko", type("Artifacts", (), {
                        "run_dir": Path("output/live-smoke/platform-ko"),
                        "selected_url": "https://career.rememberapp.co.kr/job/posting/293599",
                        "used_fallback": False,
                        "cleaned": True,
                    })()),
                ],
                "failures": [("remember_platform_en", "network failed")],
            })()

        with patch("career_ops_kr.cli.run_batch_live_resume_smoke", side_effect=fake_run_batch_live_resume_smoke):
            result = runner.invoke(
                app,
                [
                    "smoke-live-resume-batch",
                    "--target",
                    "remember_platform_ko",
                    "--target",
                    "remember_platform_en",
                ],
            )

        self.assertEqual(1, result.exit_code, msg=result.output)
        self.assertIn("OK remember_platform_ko | https://career.rememberapp.co.kr/job/posting/293599 | primary | output/live-smoke/platform-ko | cleaned", result.output)
        self.assertIn("FAILED remember_platform_en | network failed", result.output)
        self.assertIn("Batch live smoke summary: 1 passed, 1 failed.", result.output)

    def test_smoke_live_resume_batch_writes_json_report_when_requested(self) -> None:
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            report_path = temp_path / "live-smoke.json"

            def fake_run_batch_live_resume_smoke(**kwargs):
                return type("BatchResult", (), {
                    "successes": [
                        ("remember_platform_ko", type("Artifacts", (), {
                            "run_dir": Path("output/live-smoke/platform-ko"),
                            "job_path": Path("output/live-smoke/platform-ko/job.md"),
                            "report_path": Path("output/live-smoke/platform-ko/report.md"),
                            "tailoring_path": Path("output/live-smoke/platform-ko/tailoring.json"),
                            "tailored_context_path": Path("output/live-smoke/platform-ko/context.json"),
                            "html_path": Path("output/live-smoke/platform-ko/resume.html"),
                            "pdf_path": None,
                            "selected_url": "https://career.rememberapp.co.kr/job/posting/293599",
                            "candidate_label": "primary",
                            "used_fallback": False,
                            "cleaned": True,
                        })()),
                    ],
                    "failures": [],
                })()

            with patch("career_ops_kr.cli.run_batch_live_resume_smoke", side_effect=fake_run_batch_live_resume_smoke):
                result = runner.invoke(
                    app,
                    [
                        "smoke-live-resume-batch",
                        "--target",
                        "remember_platform_ko",
                        "--report-out",
                        report_path.as_posix(),
                    ],
                )

            self.assertEqual(0, result.exit_code, msg=result.output)
            self.assertIn(f"Batch report: {report_path.as_posix()}", result.output)
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(1, payload["success_count"])
            self.assertEqual(["remember_platform_ko"], payload["selected_targets"])
            self.assertEqual(
                "https://career.rememberapp.co.kr/job/posting/293599",
                payload["successes"][0]["selected_url"],
            )

    def test_smoke_live_resume_batch_prints_fallback_when_target_uses_fallback(self) -> None:
        runner = CliRunner()

        def fake_run_batch_live_resume_smoke(**kwargs):
            return type("BatchResult", (), {
                "successes": [
                    ("remember_platform_ko", type("Artifacts", (), {
                        "run_dir": Path("output/live-smoke/platform-ko"),
                        "job_path": Path("output/live-smoke/platform-ko/job.md"),
                        "report_path": Path("output/live-smoke/platform-ko/report.md"),
                        "tailoring_path": Path("output/live-smoke/platform-ko/tailoring.json"),
                        "tailored_context_path": Path("output/live-smoke/platform-ko/context.json"),
                        "html_path": Path("output/live-smoke/platform-ko/resume.html"),
                        "pdf_path": None,
                        "selected_url": "https://career.rememberapp.co.kr/job/posting/275546",
                        "candidate_label": "fallback-devops",
                        "used_fallback": True,
                        "cleaned": True,
                    })()),
                ],
                "failures": [],
            })()

        with patch("career_ops_kr.cli.run_batch_live_resume_smoke", side_effect=fake_run_batch_live_resume_smoke):
            result = runner.invoke(
                app,
                [
                    "smoke-live-resume-batch",
                    "--target",
                    "remember_platform_ko",
                ],
            )

        self.assertEqual(0, result.exit_code, msg=result.output)
        self.assertIn(
            "OK remember_platform_ko | https://career.rememberapp.co.kr/job/posting/275546 | fallback | label=fallback-devops | output/live-smoke/platform-ko | cleaned",
            result.output,
        )

    def test_smoke_live_resume_batch_runs_all_targets_by_default(self) -> None:
        runner = CliRunner()

        def fake_run_batch_live_resume_smoke(**kwargs):
            self.assertIsNone(kwargs["target_keys"])
            return type("BatchResult", (), {
                "successes": [],
                "failures": [],
            })()

        with patch("career_ops_kr.cli.run_batch_live_resume_smoke", side_effect=fake_run_batch_live_resume_smoke):
            result = runner.invoke(app, ["smoke-live-resume-batch"])

        self.assertEqual(0, result.exit_code, msg=result.output)
        self.assertIn("Batch live smoke summary: 0 passed, 0 failed.", result.output)


class ArtifactManifestCliTest(unittest.TestCase):
    def test_backfill_artifact_manifests_dry_run_reports_create_and_overwrite(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_dir = temp_path / "output"
            jd_dir = temp_path / "jds"
            report_dir = temp_path / "reports"
            html_dir = output_dir / "rendered"
            html_dir.mkdir(parents=True, exist_ok=True)
            jd_dir.mkdir(parents=True, exist_ok=True)
            report_dir.mkdir(parents=True, exist_ok=True)

            new_html = html_dir / "new-role.html"
            existing_html = html_dir / "existing-role.html"
            new_html.write_text("<html></html>", encoding="utf-8")
            existing_html.write_text("<html></html>", encoding="utf-8")
            existing_manifest = existing_html.with_suffix(".manifest.json")
            existing_manifest.write_text('{"version":1,"paths":{}}\n', encoding="utf-8")

            result = runner.invoke(
                app,
                [
                    "backfill-artifact-manifests",
                    "--output-dir",
                    output_dir.as_posix(),
                    "--jd-dir",
                    jd_dir.as_posix(),
                    "--report-dir",
                    report_dir.as_posix(),
                    "--overwrite",
                    "--dry-run",
                ],
            )

            self.assertEqual(0, result.exit_code, msg=result.output)
            self.assertIn("Scanned HTML artifacts: 2", result.output)
            self.assertIn("Created: 1", result.output)
            self.assertIn("Overwritten: 1", result.output)
            self.assertIn("Skipped: 0", result.output)
            self.assertIn(new_html.with_suffix(".manifest.json").as_posix(), result.output)
            self.assertIn(existing_manifest.as_posix(), result.output)
            self.assertEqual('{"version":1,"paths":{}}\n', existing_manifest.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
