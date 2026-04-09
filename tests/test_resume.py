from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from career_ops_kr.commands.resume import (
    BatchLiveResumeSmokeResult,
    compare_live_smoke_reports,
    DEFAULT_LIVE_SMOKE_TARGETS_PATH,
    BuildTailoredResumeFromUrlArtifacts,
    apply_resume_tailoring_packet,
    build_tailored_resume_from_url,
    build_tailored_resume,
    create_resume_tailoring_packet,
    evaluate_live_smoke_report_health,
    list_live_smoke_reports,
    list_latest_live_smoke_entries_by_target,
    list_live_smoke_targets,
    live_smoke_report_metadata,
    load_live_smoke_target,
    resolve_latest_live_smoke_report,
    resolve_latest_live_smoke_report_pair,
    run_batch_live_resume_smoke,
    run_live_resume_smoke,
    summarize_live_smoke_report,
    write_live_smoke_report,
    write_live_smoke_batch_report,
)


ROOT = Path(__file__).resolve().parents[1]
SCORECARD = ROOT / "config/scorecard.kr.yml"


def _write_test_live_smoke_targets_yaml(path: Path) -> Path:
    targets_path = path / "live-smoke-targets.yml"
    targets_path.write_text(
        "\n".join(
            [
                "targets:",
                "  remember_platform_ko:",
                "    candidates:",
                '      - url: "https://career.rememberapp.co.kr/job/posting/293599"',
                '        source: "remember"',
                '    base_context_path: "examples/resume-context.platform.ko.example.json"',
                '    template_path: "templates/resume-ko.html"',
                '    profile_path: "config/profile.example.yml"',
                "  wanted_backend_ko:",
                "    candidates:",
                '      - url: "https://www.wanted.co.kr/wd/157"',
                '        source: "wanted"',
                '    base_context_path: "examples/resume-context.backend.ko.example.json"',
                '    template_path: "templates/resume-ko.html"',
                '    profile_path: "config/profile.example.yml"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return targets_path


class ResumeTailoringTest(unittest.TestCase):
    def test_list_live_smoke_targets_reads_default_registry(self) -> None:
        targets = list_live_smoke_targets(DEFAULT_LIVE_SMOKE_TARGETS_PATH)
        self.assertGreaterEqual(len(targets), 6)
        keys = {target.key for target in targets}
        self.assertIn("remember_platform_ko", keys)
        self.assertIn("remember_platform_en", keys)
        self.assertIn("remember_backend_ko", keys)
        self.assertIn("remember_data_ai_ko", keys)
        self.assertIn("wanted_backend_ko", keys)
        self.assertIn("jumpit_data_ai_ko", keys)
        jumpit_target = next(target for target in targets if target.key == "jumpit_data_ai_ko")
        self.assertEqual(2, len(jumpit_target.candidates))

    def test_load_live_smoke_target_returns_expected_defaults(self) -> None:
        target = load_live_smoke_target("remember_platform_ko", DEFAULT_LIVE_SMOKE_TARGETS_PATH)
        self.assertEqual("remember", target.candidates[0].source)
        self.assertIn("job/posting/293599", target.candidates[0].url)
        self.assertEqual(2, len(target.candidates))
        self.assertTrue(target.base_context_path.as_posix().endswith("examples/resume-context.platform.ko.example.json"))
        self.assertTrue(target.template_path.as_posix().endswith("templates/resume-ko.html"))
        self.assertTrue(target.profile_path.as_posix().endswith("config/profile.example.yml"))

    def test_load_live_smoke_target_rejects_unknown_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown live smoke target"):
            load_live_smoke_target("missing-target", DEFAULT_LIVE_SMOKE_TARGETS_PATH)

    def test_create_resume_tailoring_packet_writes_structured_json(self) -> None:
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
                        "# Senior Platform Engineer",
                        "",
                        "Build kubernetes-based internal platform tooling with terraform, aws, observability, and sre practices.",
                        "The team supports developer platform reliability and production operations.",
                        "",
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
                        "- Total Score: 4.3/5",
                        "- Recommendation: 지원 적극 검토",
                        "- Seniority Signal: senior",
                        "- Work Mode Signal: remote",
                        "- Language Signal: ko, en",
                        "- Role Match Candidates: Senior Platform Engineer: 4",
                        "",
                        "## Why It Fits",
                        "",
                        "- Role keyword overlap: 4/6",
                        "- Stack keyword overlap: 3/6",
                        "- Preferred domains matched: 1",
                        "",
                        "## Risks",
                        "",
                        "- Avoid-domain matches: 0",
                        "- Compensation disclosed: no clear signal",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            base_context_path.write_text(
                json.dumps(
                    {
                        "name": "Hong Gil-dong",
                        "headline": "Platform Engineer",
                        "summary": "Platform and backend engineer.",
                        "skills": ["Python", "AWS", "Terraform"],
                        "experience": [
                            {
                                "role": "Platform Engineer",
                                "company": "Current Co",
                                "bullets": [
                                    "Built AWS infrastructure.",
                                    "Improved Terraform workflows.",
                                ],
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            artifacts = create_resume_tailoring_packet(
                job_path,
                report_path,
                out=output_path,
                base_context_path=base_context_path,
                scorecard_path=SCORECARD,
            )

            self.assertEqual(output_path, artifacts.output_path)
            packet = json.loads(output_path.read_text(encoding="utf-8"))

            self.assertEqual(job_path.as_posix(), packet["source"]["job_path"])
            self.assertEqual(report_path.as_posix(), packet["source"]["report_path"])
            self.assertEqual(base_context_path.as_posix(), packet["source"]["base_context_path"])
            self.assertEqual("Example Corp", packet["job"]["company"])
            self.assertEqual("Senior Platform Engineer", packet["selection"]["selected_target_role"])
            self.assertEqual("Platform", packet["selection"]["selected_role_profile"])
            self.assertEqual(4.3, packet["selection"]["total_score"])
            self.assertEqual("Senior Platform Engineer", packet["tailoring"]["headline"])
            self.assertIn("Terraform", packet["tailoring"]["matched_resume_skills"])
            self.assertIn("kubernetes", [item.lower() for item in packet["tailoring"]["skills_to_emphasize"]])
            self.assertIn("kubernetes", [item.lower() for item in packet["tailoring"]["missing_focus_keywords"]])
            self.assertTrue(packet["tailoring"]["notes"])

    def test_create_resume_tailoring_packet_requires_report_summary_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "job.md"
            report_path = temp_path / "report.md"

            job_path.write_text("# Job", encoding="utf-8")
            report_path.write_text(
                "\n".join(
                    [
                        "# Broken Report",
                        "",
                        "## Summary",
                        "",
                        "- Selected Domain: Platform",
                        "- Selected Target Role: Senior Platform Engineer",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                create_resume_tailoring_packet(job_path, report_path, scorecard_path=SCORECARD)

    def test_create_resume_tailoring_packet_requires_overwrite_for_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "job.md"
            report_path = temp_path / "report.md"
            output_path = temp_path / "tailoring.json"

            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Data AI Engineer"',
                        "---",
                        "",
                        "Serving llm inference and evaluation systems.",
                    ]
                ),
                encoding="utf-8",
            )
            report_path.write_text(
                "\n".join(
                    [
                        "# Example - Data AI Engineer",
                        "",
                        "## Summary",
                        "",
                        "- Date: 2026-04-06",
                        "- Selected Domain: Data",
                        "- Selected Target Role: Applied AI Engineer",
                        "- Selected Role Profile: Data-AI",
                        "- Total Score: 4.1/5",
                        "- Recommendation: 지원 적극 검토",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            output_path.write_text("old", encoding="utf-8")

            with self.assertRaises(ValueError):
                create_resume_tailoring_packet(
                    job_path,
                    report_path,
                    out=output_path,
                    scorecard_path=SCORECARD,
                )

            artifacts = create_resume_tailoring_packet(
                job_path,
                report_path,
                out=output_path,
                scorecard_path=SCORECARD,
                overwrite=True,
            )
            self.assertEqual(output_path, artifacts.output_path)
            self.assertNotEqual("old", output_path.read_text(encoding="utf-8"))

    def test_apply_resume_tailoring_packet_updates_visible_context_fields(self) -> None:
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
                            "url": "https://example.com/jobs/platform",
                            "source": "remember",
                        },
                        "selection": {
                            "selected_domain": "Platform",
                            "selected_target_role": "Senior Platform Engineer",
                            "selected_role_profile": "Platform",
                            "total_score": 4.4,
                            "recommendation": "지원 적극 검토",
                        },
                        "tailoring": {
                            "headline": "Senior Platform Engineer",
                            "summary": "Resume version for Senior Platform Engineer with emphasis on kubernetes, terraform, aws.",
                            "skills_to_emphasize": ["Kubernetes", "Terraform", "AWS"],
                            "matched_resume_skills": ["Terraform", "AWS"],
                            "missing_focus_keywords": ["Kubernetes"],
                            "experience_focus": [
                                "Move bullets proving kubernetes, terraform, aws closer to the top.",
                                "Make recent experience read like a direct match for Senior Platform Engineer.",
                            ],
                            "project_focus": [
                                "Highlight projects that show kubernetes, terraform in production.",
                                "Prefer Platform work that reduces perceived onboarding risk.",
                            ],
                            "keywords": ["Kubernetes", "Terraform", "AWS"],
                            "notes": [
                                "Recommendation from score report: 지원 적극 검토",
                            ],
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
                        "name": "Hong Gil-dong",
                        "headline": "Backend Engineer",
                        "summary": "Generalist backend engineer.",
                        "skills": ["Python", "AWS", "Terraform", "PostgreSQL"],
                        "experience": [
                            {
                                "role": "Backend Engineer",
                                "company": "Legacy Corp",
                                "bullets": ["Built CRUD APIs for internal systems."],
                            },
                            {
                                "role": "Platform Engineer",
                                "company": "Current Corp",
                                "bullets": ["Managed Kubernetes clusters and Terraform infrastructure."],
                            },
                        ],
                        "projects": [
                            {
                                "name": "Admin Tool",
                                "bullets": ["Internal admin dashboard for ops teams."],
                            },
                            {
                                "name": "Platform Migration",
                                "bullets": ["Migrated AWS infrastructure with Terraform and Kubernetes."],
                            },
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            artifacts = apply_resume_tailoring_packet(
                tailoring_path,
                base_context_path,
                out=output_path,
            )

            self.assertEqual(output_path, artifacts.output_path)
            tailored_context = json.loads(output_path.read_text(encoding="utf-8"))

            self.assertEqual("Senior Platform Engineer", tailored_context["headline"])
            self.assertIn("Resume version for Senior Platform Engineer", tailored_context["summary"])
            self.assertEqual(["AWS", "Terraform", "Python", "PostgreSQL"], tailored_context["skills"])
            self.assertEqual("Platform Engineer", tailored_context["experience"][0]["role"])
            self.assertEqual("Platform Migration", tailored_context["projects"][0]["name"])
            self.assertEqual("Platform", tailored_context["tailoringGuidance"]["selection"]["selected_role_profile"])
            self.assertIn(
                "Kubernetes",
                tailored_context["tailoringGuidance"]["focus"]["missing_focus_keywords"],
            )

    def test_apply_resume_tailoring_packet_requires_overwrite_for_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            tailoring_path = temp_path / "tailoring.json"
            base_context_path = temp_path / "resume-context.json"
            output_path = temp_path / "tailored-context.json"

            tailoring_path.write_text(
                json.dumps(
                    {
                        "job": {"company": "Example", "title": "Backend Engineer"},
                        "selection": {"selected_target_role": "Backend Engineer"},
                        "tailoring": {
                            "headline": "Backend Engineer",
                            "summary": "Tailored summary.",
                            "skills_to_emphasize": [],
                            "matched_resume_skills": [],
                            "missing_focus_keywords": [],
                            "experience_focus": [],
                            "project_focus": [],
                            "keywords": [],
                            "notes": [],
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            base_context_path.write_text(json.dumps({"headline": "Old"}, ensure_ascii=False), encoding="utf-8")
            output_path.write_text("old", encoding="utf-8")

            with self.assertRaises(ValueError):
                apply_resume_tailoring_packet(tailoring_path, base_context_path, out=output_path)

            artifacts = apply_resume_tailoring_packet(
                tailoring_path,
                base_context_path,
                out=output_path,
                overwrite=True,
            )
            self.assertEqual(output_path, artifacts.output_path)
            self.assertNotEqual("old", output_path.read_text(encoding="utf-8"))

    def test_build_tailored_resume_writes_full_chain_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = ROOT / "tests" / "fixtures" / "remember_platform_job.md"
            report_path = ROOT / "tests" / "fixtures" / "remember_platform_report.md"
            base_context_path = ROOT / "examples" / "resume-context.platform.ko.example.json"
            template_path = ROOT / "templates" / "resume-ko.html"
            html_path = temp_path / "resume.html"
            tailoring_path = temp_path / "tailoring.json"
            context_path = temp_path / "context.json"

            artifacts = build_tailored_resume(
                job_path,
                report_path,
                base_context_path,
                template_path,
                html_out=html_path,
                tailoring_out=tailoring_path,
                tailored_context_out=context_path,
                scorecard_path=SCORECARD,
            )

            self.assertEqual(tailoring_path, artifacts.tailoring_path)
            self.assertEqual(context_path, artifacts.tailored_context_path)
            self.assertEqual(html_path, artifacts.html_path)
            self.assertIsNone(artifacts.pdf_path)
            self.assertEqual(html_path.with_suffix(".manifest.json"), artifacts.manifest_path)
            self.assertTrue(html_path.exists())
            self.assertTrue(artifacts.manifest_path.exists())

            packet = json.loads(tailoring_path.read_text(encoding="utf-8"))
            manifest = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
            rendered = html_path.read_text(encoding="utf-8")
            self.assertEqual("Platform", packet["selection"]["selected_role_profile"])
            self.assertEqual("build_tailored_resume", manifest["pipeline"])
            self.assertEqual(html_path.as_posix(), manifest["paths"]["html_path"])
            self.assertEqual("(주)어피닛", manifest["job"]["company"])
            self.assertIn("홍길동", rendered)
            self.assertIn("Platform Engineer", rendered)

    def test_build_tailored_resume_requires_overwrite_for_existing_html_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = ROOT / "tests" / "fixtures" / "remember_platform_job.md"
            report_path = ROOT / "tests" / "fixtures" / "remember_platform_report.md"
            base_context_path = ROOT / "examples" / "resume-context.platform.ko.example.json"
            template_path = ROOT / "templates" / "resume-ko.html"
            html_path = temp_path / "resume.html"
            html_path.write_text("old", encoding="utf-8")

            with self.assertRaises(ValueError):
                build_tailored_resume(
                    job_path,
                    report_path,
                    base_context_path,
                    template_path,
                    html_out=html_path,
                    scorecard_path=SCORECARD,
                )

    def test_build_tailored_resume_requires_overwrite_for_existing_tailoring_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = ROOT / "tests" / "fixtures" / "remember_platform_job.md"
            report_path = ROOT / "tests" / "fixtures" / "remember_platform_report.md"
            base_context_path = ROOT / "examples" / "resume-context.platform.ko.example.json"
            template_path = ROOT / "templates" / "resume-ko.html"
            tailoring_path = temp_path / "tailoring.json"
            context_path = temp_path / "context.json"
            html_path = temp_path / "resume.html"
            tailoring_path.write_text("old", encoding="utf-8")

            with self.assertRaises(ValueError):
                build_tailored_resume(
                    job_path,
                    report_path,
                    base_context_path,
                    template_path,
                    html_out=html_path,
                    tailoring_out=tailoring_path,
                    tailored_context_out=context_path,
                    scorecard_path=SCORECARD,
                )

            self.assertEqual("old", tailoring_path.read_text(encoding="utf-8"))
            self.assertFalse(context_path.exists())
            self.assertFalse(html_path.exists())

    def test_build_tailored_resume_requires_overwrite_for_existing_context_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = ROOT / "tests" / "fixtures" / "remember_platform_job.md"
            report_path = ROOT / "tests" / "fixtures" / "remember_platform_report.md"
            base_context_path = ROOT / "examples" / "resume-context.platform.ko.example.json"
            template_path = ROOT / "templates" / "resume-ko.html"
            tailoring_path = temp_path / "tailoring.json"
            context_path = temp_path / "context.json"
            html_path = temp_path / "resume.html"
            context_path.write_text("old", encoding="utf-8")

            with self.assertRaises(ValueError):
                build_tailored_resume(
                    job_path,
                    report_path,
                    base_context_path,
                    template_path,
                    html_out=html_path,
                    tailoring_out=tailoring_path,
                    tailored_context_out=context_path,
                    scorecard_path=SCORECARD,
                )

            self.assertFalse(tailoring_path.exists())
            self.assertEqual("old", context_path.read_text(encoding="utf-8"))
            self.assertFalse(html_path.exists())

    def test_build_tailored_resume_from_url_runs_fetch_score_and_render_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_out = temp_path / "job.md"
            report_out = temp_path / "report.md"
            tracker_out = temp_path / "tracker.tsv"
            html_out = temp_path / "resume.html"
            tailoring_out = temp_path / "tailoring.json"
            context_out = temp_path / "context.json"
            base_context_path = ROOT / "examples" / "resume-context.platform.ko.example.json"
            template_path = ROOT / "templates" / "resume-ko.html"
            calls: list[tuple[str, Path]] = []

            def fake_fetch_job(
                url: str,
                *,
                out: Path | None = None,
                output_dir: Path | None = None,
                source: str = "manual",
                insecure: bool = False,
            ) -> Path:
                self.assertEqual("https://career.rememberapp.co.kr/job/posting/293599", url)
                self.assertEqual(job_out, out)
                self.assertIsNone(output_dir)
                self.assertEqual("remember", source)
                self.assertFalse(insecure)
                calls.append(("fetch", out))
                out.write_text(
                    (ROOT / "tests" / "fixtures" / "remember_platform_job.md").read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
                return out

            def fake_score_job(
                job_path: Path,
                *,
                report_path: Path | None = None,
                tracker_path: Path | None = None,
                profile_path: Path = ROOT / "config" / "profile.example.yml",
                scorecard_path: Path = SCORECARD,
                write_tracker: bool = True,
            ):
                from career_ops_kr.scoring import ScoreJobArtifacts

                self.assertEqual(job_out, job_path)
                self.assertEqual(report_out, report_path)
                self.assertEqual(tracker_out, tracker_path)
                self.assertTrue(write_tracker)
                calls.append(("score", report_path))
                report_path.write_text(
                    (ROOT / "tests" / "fixtures" / "remember_platform_report.md").read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
                tracker_path.write_text("tracker\n", encoding="utf-8")
                return ScoreJobArtifacts(
                    report_path=report_path,
                    tracker_path=tracker_path,
                    total_score=4.1,
                    recommendation="지원 적극 검토",
                )

            artifacts = build_tailored_resume_from_url(
                "https://career.rememberapp.co.kr/job/posting/293599",
                base_context_path,
                template_path,
                job_out=job_out,
                report_out=report_out,
                tracker_out=tracker_out,
                html_out=html_out,
                tailoring_out=tailoring_out,
                tailored_context_out=context_out,
                profile_path=ROOT / "config" / "profile.example.yml",
                scorecard_path=SCORECARD,
                fetch_job_func=fake_fetch_job,
                score_job_func=fake_score_job,
            )

            self.assertEqual([("fetch", job_out), ("score", report_out)], calls)
            self.assertEqual(job_out, artifacts.job_path)
            self.assertEqual(report_out, artifacts.report_path)
            self.assertEqual(tracker_out, artifacts.tracker_path)
            self.assertEqual(tailoring_out, artifacts.tailoring_path)
            self.assertEqual(context_out, artifacts.tailored_context_path)
            self.assertEqual(html_out, artifacts.html_path)
            self.assertEqual(html_out.with_suffix(".manifest.json"), artifacts.manifest_path)
            self.assertTrue(html_out.exists())
            self.assertTrue(artifacts.manifest_path.exists())
            manifest = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual("build_tailored_resume_from_url", manifest["pipeline"])
            self.assertEqual(
                (ROOT / "config" / "profile.example.yml").as_posix(),
                manifest["paths"]["profile_path"],
            )

    def test_build_tailored_resume_from_url_preserves_fetched_job_when_scoring_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_out = temp_path / "job.md"
            report_out = temp_path / "report.md"
            html_out = temp_path / "resume.html"
            base_context_path = ROOT / "examples" / "resume-context.platform.ko.example.json"
            template_path = ROOT / "templates" / "resume-ko.html"

            def fake_fetch_job(
                url: str,
                *,
                out: Path | None = None,
                output_dir: Path | None = None,
                source: str = "manual",
                insecure: bool = False,
            ) -> Path:
                out.write_text("fetched", encoding="utf-8")
                return out

            def fake_score_job(*args, **kwargs):
                raise ValueError("score failed")

            with self.assertRaisesRegex(ValueError, "score failed"):
                build_tailored_resume_from_url(
                    "https://example.com/jobs/platform",
                    base_context_path,
                    template_path,
                    source="manual",
                    job_out=job_out,
                    report_out=report_out,
                    html_out=html_out,
                    profile_path=ROOT / "config" / "profile.example.yml",
                    scorecard_path=SCORECARD,
                    fetch_job_func=fake_fetch_job,
                    score_job_func=fake_score_job,
                )

            self.assertEqual("fetched", job_out.read_text(encoding="utf-8"))
            self.assertFalse(report_out.exists())
            self.assertFalse(html_out.exists())

    def test_build_tailored_resume_from_url_stops_before_scoring_when_fetch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            report_out = temp_path / "report.md"
            html_out = temp_path / "resume.html"
            base_context_path = ROOT / "examples" / "resume-context.platform.ko.example.json"
            template_path = ROOT / "templates" / "resume-ko.html"
            score_called = False

            def fake_fetch_job(*args, **kwargs):
                raise ValueError("fetch failed")

            def fake_score_job(*args, **kwargs):
                nonlocal score_called
                score_called = True
                raise AssertionError("score should not be called")

            with self.assertRaisesRegex(ValueError, "fetch failed"):
                build_tailored_resume_from_url(
                    "https://example.com/jobs/platform",
                    base_context_path,
                    template_path,
                    source="manual",
                    report_out=report_out,
                    html_out=html_out,
                    profile_path=ROOT / "config" / "profile.example.yml",
                    scorecard_path=SCORECARD,
                    fetch_job_func=fake_fetch_job,
                    score_job_func=fake_score_job,
                )

            self.assertFalse(score_called)
            self.assertFalse(report_out.exists())
            self.assertFalse(html_out.exists())

    def test_run_live_resume_smoke_cleans_artifacts_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            out_dir = temp_path / "live-smoke"
            base_context_path = ROOT / "examples" / "resume-context.platform.ko.example.json"
            template_path = ROOT / "templates" / "resume-ko.html"

            def fake_build_from_url(*args, **kwargs):
                run_dir = kwargs["job_out"].parent
                run_dir.mkdir(parents=True, exist_ok=True)
                for key in ("job_out", "report_out", "tailoring_out", "tailored_context_out", "html_out"):
                    kwargs[key].write_text(key, encoding="utf-8")
                return BuildTailoredResumeFromUrlArtifacts(
                    job_path=kwargs["job_out"],
                    report_path=kwargs["report_out"],
                    tracker_path=None,
                    tailoring_path=kwargs["tailoring_out"],
                    tailored_context_path=kwargs["tailored_context_out"],
                    html_path=kwargs["html_out"],
                    pdf_path=None,
                )

            artifacts = run_live_resume_smoke(
                target_key="remember_platform_ko",
                targets_path=DEFAULT_LIVE_SMOKE_TARGETS_PATH,
                scorecard_path=SCORECARD,
                out_dir=out_dir,
                build_from_url_func=fake_build_from_url,
            )

            self.assertTrue(artifacts.cleaned)
            self.assertFalse(out_dir.exists())
            self.assertIn("job/posting/293599", artifacts.selected_url)
            self.assertFalse(artifacts.used_fallback)

    def test_run_live_resume_smoke_keeps_artifacts_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            out_dir = temp_path / "live-smoke"
            base_context_path = ROOT / "examples" / "resume-context.platform.ko.example.json"
            template_path = ROOT / "templates" / "resume-ko.html"

            def fake_build_from_url(*args, **kwargs):
                run_dir = kwargs["job_out"].parent
                run_dir.mkdir(parents=True, exist_ok=True)
                for key in ("job_out", "report_out", "tailoring_out", "tailored_context_out", "html_out"):
                    kwargs[key].write_text(key, encoding="utf-8")
                return BuildTailoredResumeFromUrlArtifacts(
                    job_path=kwargs["job_out"],
                    report_path=kwargs["report_out"],
                    tracker_path=None,
                    tailoring_path=kwargs["tailoring_out"],
                    tailored_context_path=kwargs["tailored_context_out"],
                    html_path=kwargs["html_out"],
                    pdf_path=None,
                )

            artifacts = run_live_resume_smoke(
                target_key="remember_platform_ko",
                targets_path=DEFAULT_LIVE_SMOKE_TARGETS_PATH,
                scorecard_path=SCORECARD,
                out_dir=out_dir,
                keep_artifacts=True,
                build_from_url_func=fake_build_from_url,
            )

            self.assertFalse(artifacts.cleaned)
            self.assertTrue(out_dir.exists())
            self.assertTrue(artifacts.html_path.exists())
            self.assertIn("job/posting/293599", artifacts.selected_url)

    def test_run_live_resume_smoke_allows_explicit_url_to_override_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            out_dir = temp_path / "live-smoke"
            observed_url: str | None = None

            def fake_build_from_url(url, *args, **kwargs):
                nonlocal observed_url
                observed_url = url
                run_dir = kwargs["job_out"].parent
                run_dir.mkdir(parents=True, exist_ok=True)
                for key in ("job_out", "report_out", "tailoring_out", "tailored_context_out", "html_out"):
                    kwargs[key].write_text(key, encoding="utf-8")
                return BuildTailoredResumeFromUrlArtifacts(
                    job_path=kwargs["job_out"],
                    report_path=kwargs["report_out"],
                    tracker_path=None,
                    tailoring_path=kwargs["tailoring_out"],
                    tailored_context_path=kwargs["tailored_context_out"],
                    html_path=kwargs["html_out"],
                    pdf_path=None,
                )

            run_live_resume_smoke(
                target_key="remember_platform_ko",
                targets_path=DEFAULT_LIVE_SMOKE_TARGETS_PATH,
                url="https://example.com/jobs/custom",
                scorecard_path=SCORECARD,
                out_dir=out_dir,
                keep_artifacts=True,
                build_from_url_func=fake_build_from_url,
            )

            self.assertEqual("https://example.com/jobs/custom", observed_url)

    def test_run_live_resume_smoke_uses_first_successful_fallback_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            out_dir = temp_path / "live-smoke"
            attempted: list[str] = []

            def fake_build_from_url(url, *args, **kwargs):
                attempted.append(url)
                if url.endswith("/293599"):
                    raise ValueError("primary failed")
                run_dir = kwargs["job_out"].parent
                run_dir.mkdir(parents=True, exist_ok=True)
                for key in ("job_out", "report_out", "tailoring_out", "tailored_context_out", "html_out"):
                    kwargs[key].write_text(key, encoding="utf-8")
                return BuildTailoredResumeFromUrlArtifacts(
                    job_path=kwargs["job_out"],
                    report_path=kwargs["report_out"],
                    tracker_path=None,
                    tailoring_path=kwargs["tailoring_out"],
                    tailored_context_path=kwargs["tailored_context_out"],
                    html_path=kwargs["html_out"],
                    pdf_path=None,
                )

            artifacts = run_live_resume_smoke(
                target_key="remember_platform_ko",
                targets_path=DEFAULT_LIVE_SMOKE_TARGETS_PATH,
                scorecard_path=SCORECARD,
                out_dir=out_dir,
                keep_artifacts=True,
                build_from_url_func=fake_build_from_url,
            )

            self.assertEqual(
                [
                    "https://career.rememberapp.co.kr/job/posting/293599",
                    "https://career.rememberapp.co.kr/job/posting/275546",
                ],
                attempted,
            )
            self.assertTrue(artifacts.used_fallback)
            self.assertEqual("https://career.rememberapp.co.kr/job/posting/275546", artifacts.selected_url)

    def test_run_live_resume_smoke_fails_when_all_candidates_fail(self) -> None:
        with self.assertRaisesRegex(ValueError, "293599") as context:
            run_live_resume_smoke(
                target_key="remember_platform_ko",
                targets_path=DEFAULT_LIVE_SMOKE_TARGETS_PATH,
                scorecard_path=SCORECARD,
                build_from_url_func=lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("failed")),
            )

        self.assertIn("275546", str(context.exception))

    def test_run_batch_live_resume_smoke_expands_all_targets_by_default(self) -> None:
        calls: list[str] = []

        def fake_run_live_smoke(**kwargs):
            target_key = kwargs["target_key"]
            calls.append(target_key)
            out_dir = kwargs["out_dir"] or Path("output") / target_key
            return type("Artifacts", (), {
                "run_dir": out_dir,
                "job_path": out_dir / "job.md",
                "report_path": out_dir / "report.md",
                "tailoring_path": out_dir / "tailoring.json",
                "tailored_context_path": out_dir / "context.json",
                "html_path": out_dir / "resume.html",
                "pdf_path": None,
                "cleaned": True,
            })()

        result = run_batch_live_resume_smoke(
            target_keys=None,
            targets_path=DEFAULT_LIVE_SMOKE_TARGETS_PATH,
            scorecard_path=SCORECARD,
            run_live_smoke_func=fake_run_live_smoke,
        )

        self.assertEqual(
            [
                "remember_platform_ko",
                "remember_platform_en",
                "remember_backend_ko",
                "remember_data_ai_ko",
                "wanted_backend_ko",
                "jumpit_data_ai_ko",
            ],
            calls,
        )
        self.assertEqual(6, len(result.successes))
        self.assertEqual([], result.failures)

    def test_run_batch_live_resume_smoke_continues_after_failure(self) -> None:
        calls: list[str] = []

        def fake_run_live_smoke(**kwargs):
            target_key = kwargs["target_key"]
            calls.append(target_key)
            if target_key == "remember_platform_en":
                raise ValueError("network failed")
            out_dir = kwargs["out_dir"] or Path("output") / target_key
            return type("Artifacts", (), {
                "run_dir": out_dir,
                "job_path": out_dir / "job.md",
                "report_path": out_dir / "report.md",
                "tailoring_path": out_dir / "tailoring.json",
                "tailored_context_path": out_dir / "context.json",
                "html_path": out_dir / "resume.html",
                "pdf_path": None,
                "cleaned": True,
            })()

        result = run_batch_live_resume_smoke(
            target_keys=["remember_platform_ko", "remember_platform_en", "remember_backend_ko"],
            targets_path=DEFAULT_LIVE_SMOKE_TARGETS_PATH,
            scorecard_path=SCORECARD,
            continue_on_error=True,
            run_live_smoke_func=fake_run_live_smoke,
        )

        self.assertEqual(
            ["remember_platform_ko", "remember_platform_en", "remember_backend_ko"],
            calls,
        )
        self.assertEqual(2, len(result.successes))
        self.assertEqual([("remember_platform_en", "network failed")], result.failures)

    def test_write_live_smoke_batch_report_writes_structured_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "reports" / "live-smoke.json"
            run_dir = temp_path / "run"
            run_dir.mkdir(parents=True, exist_ok=True)
            artifacts = type("Artifacts", (), {
                "run_dir": run_dir,
                "job_path": run_dir / "job.md",
                "report_path": run_dir / "report.md",
                "tailoring_path": run_dir / "tailoring.json",
                "tailored_context_path": run_dir / "context.json",
                "html_path": run_dir / "resume.html",
                "pdf_path": None,
                "selected_url": "https://career.rememberapp.co.kr/job/posting/293599",
                "candidate_label": "primary",
                "used_fallback": False,
                "cleaned": True,
            })()
            result = BatchLiveResumeSmokeResult(
                successes=[("remember_platform_ko", artifacts)],
                failures=[("wanted_backend_ko", "network failed")],
            )

            written = write_live_smoke_batch_report(
                result,
                targets_path=DEFAULT_LIVE_SMOKE_TARGETS_PATH,
                selected_targets=["remember_platform_ko", "wanted_backend_ko"],
                output_path=output_path,
            )

            self.assertEqual(output_path, written)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(1, payload["success_count"])
            self.assertEqual(1, payload["failure_count"])
            self.assertEqual(
                ["remember_platform_ko", "wanted_backend_ko"],
                payload["selected_targets"],
            )
            self.assertEqual(
                "https://career.rememberapp.co.kr/job/posting/293599",
                payload["successes"][0]["selected_url"],
            )
            self.assertEqual("wanted_backend_ko", payload["failures"][0]["target"])

    def test_write_live_smoke_batch_report_requires_overwrite_for_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "live-smoke.json"
            output_path.write_text("old", encoding="utf-8")
            result = BatchLiveResumeSmokeResult(successes=[], failures=[])

            with self.assertRaisesRegex(ValueError, "already exists"):
                write_live_smoke_batch_report(
                    result,
                    targets_path=DEFAULT_LIVE_SMOKE_TARGETS_PATH,
                    selected_targets=None,
                    output_path=output_path,
                )

            write_live_smoke_batch_report(
                result,
                targets_path=DEFAULT_LIVE_SMOKE_TARGETS_PATH,
                selected_targets=None,
                output_path=output_path,
                overwrite=True,
            )
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(0, payload["success_count"])

    def test_write_live_smoke_report_writes_structured_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "reports" / "single-live-smoke.json"
            run_dir = temp_path / "run"
            run_dir.mkdir(parents=True, exist_ok=True)
            artifacts = type("Artifacts", (), {
                "run_dir": run_dir,
                "job_path": run_dir / "job.md",
                "report_path": run_dir / "report.md",
                "tailoring_path": run_dir / "tailoring.json",
                "tailored_context_path": run_dir / "context.json",
                "html_path": run_dir / "resume.html",
                "pdf_path": None,
                "selected_url": "https://career.rememberapp.co.kr/job/posting/293599",
                "candidate_label": "primary",
                "used_fallback": False,
                "cleaned": True,
            })()

            written = write_live_smoke_report(
                artifacts,
                targets_path=DEFAULT_LIVE_SMOKE_TARGETS_PATH,
                target_key="remember_platform_ko",
                output_path=output_path,
            )

            self.assertEqual(output_path, written)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("remember_platform_ko", payload["target"])
            self.assertEqual(
                "https://career.rememberapp.co.kr/job/posting/293599",
                payload["selected_url"],
            )
            self.assertTrue(payload["cleaned"])

    def test_write_live_smoke_report_requires_overwrite_for_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "single-live-smoke.json"
            output_path.write_text("old", encoding="utf-8")
            artifacts = type("Artifacts", (), {
                "run_dir": temp_path / "run",
                "job_path": temp_path / "run/job.md",
                "report_path": temp_path / "run/report.md",
                "tailoring_path": temp_path / "run/tailoring.json",
                "tailored_context_path": temp_path / "run/context.json",
                "html_path": temp_path / "run/resume.html",
                "pdf_path": None,
                "selected_url": "https://career.rememberapp.co.kr/job/posting/293599",
                "candidate_label": "primary",
                "used_fallback": False,
                "cleaned": True,
            })()

            with self.assertRaisesRegex(ValueError, "already exists"):
                write_live_smoke_report(
                    artifacts,
                    targets_path=DEFAULT_LIVE_SMOKE_TARGETS_PATH,
                    target_key="remember_platform_ko",
                    output_path=output_path,
                )

            write_live_smoke_report(
                artifacts,
                targets_path=DEFAULT_LIVE_SMOKE_TARGETS_PATH,
                target_key="remember_platform_ko",
                output_path=output_path,
                overwrite=True,
            )
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("remember_platform_ko", payload["target"])

    def test_summarize_live_smoke_report_supports_single_and_batch_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            single_path = temp_path / "single.json"
            batch_path = temp_path / "batch.json"

            single_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-07T06:19:28Z",
                        "targets_path": DEFAULT_LIVE_SMOKE_TARGETS_PATH.as_posix(),
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
            batch_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-07T06:19:28Z",
                        "targets_path": DEFAULT_LIVE_SMOKE_TARGETS_PATH.as_posix(),
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

            single_lines = summarize_live_smoke_report(single_path)
            batch_lines = summarize_live_smoke_report(batch_path)

            self.assertIn("Type: single", single_lines)
            self.assertIn("Target: remember_platform_ko", single_lines)
            self.assertIn("Selected URL: https://career.rememberapp.co.kr/job/posting/293599", single_lines)
            self.assertIn("Type: batch", batch_lines)
            self.assertIn("Success count: 1", batch_lines)
            self.assertIn("FAILURE wanted_backend_ko: network failed", batch_lines)

    def test_compare_live_smoke_reports_detects_added_removed_and_changed_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            base_path = temp_path / "base.json"
            current_path = temp_path / "current.json"

            base_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-07T06:19:28Z",
                        "targets_path": DEFAULT_LIVE_SMOKE_TARGETS_PATH.as_posix(),
                        "selected_targets": ["remember_platform_ko", "wanted_backend_ko"],
                        "success_count": 2,
                        "failure_count": 0,
                        "successes": [
                            {
                                "target": "remember_platform_ko",
                                "selected_url": "https://career.rememberapp.co.kr/job/posting/293599",
                                "candidate_label": "primary",
                                "used_fallback": False,
                                "cleaned": True,
                            },
                            {
                                "target": "wanted_backend_ko",
                                "selected_url": "https://www.wanted.co.kr/wd/157",
                                "candidate_label": "primary",
                                "used_fallback": False,
                                "cleaned": True,
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
            current_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T06:19:28Z",
                        "targets_path": DEFAULT_LIVE_SMOKE_TARGETS_PATH.as_posix(),
                        "selected_targets": ["remember_platform_ko", "jumpit_data_ai_ko"],
                        "success_count": 2,
                        "failure_count": 0,
                        "successes": [
                            {
                                "target": "remember_platform_ko",
                                "selected_url": "https://career.rememberapp.co.kr/job/posting/275546",
                                "candidate_label": "fallback-devops",
                                "used_fallback": True,
                                "cleaned": True,
                            },
                            {
                                "target": "jumpit_data_ai_ko",
                                "selected_url": "https://jumpit.saramin.co.kr/position/53543924",
                                "candidate_label": "primary",
                                "used_fallback": False,
                                "cleaned": True,
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

            lines = compare_live_smoke_reports(base_path, current_path)

            self.assertIn("Added targets: 1", lines)
            self.assertIn("Removed targets: 1", lines)
            self.assertIn("Changed targets: 1", lines)
            self.assertIn("ADDED jumpit_data_ai_ko", lines)
            self.assertIn("REMOVED wanted_backend_ko", lines)
            self.assertIn(
                "CHANGED remember_platform_ko: https://career.rememberapp.co.kr/job/posting/293599 -> https://career.rememberapp.co.kr/job/posting/275546 | primary -> fallback",
                lines,
            )

    def test_list_live_smoke_reports_skips_non_report_json_and_sorts_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            old_report = temp_path / "old-batch.json"
            new_report = temp_path / "new-single.json"
            ignored_json = temp_path / "resume-context.json"

            old_report.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-07T06:19:28Z",
                        "targets_path": DEFAULT_LIVE_SMOKE_TARGETS_PATH.as_posix(),
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
            new_report.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T06:19:28Z",
                        "targets_path": DEFAULT_LIVE_SMOKE_TARGETS_PATH.as_posix(),
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
            ignored_json.write_text('{"name":"not-a-live-smoke-report"}\n', encoding="utf-8")

            reports = list_live_smoke_reports(temp_path)

            self.assertEqual(2, len(reports))
            self.assertEqual(new_report, reports[0]["path"])
            self.assertEqual("single", reports[0]["type"])
            self.assertEqual(old_report, reports[1]["path"])
            self.assertEqual("batch", reports[1]["type"])

    def test_list_live_smoke_reports_applies_filters_and_latest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "single-primary.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T07:00:00Z",
                        "targets_path": DEFAULT_LIVE_SMOKE_TARGETS_PATH.as_posix(),
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
            expected_batch = temp_path / "batch-fallback.json"
            expected_batch.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T08:00:00Z",
                        "targets_path": DEFAULT_LIVE_SMOKE_TARGETS_PATH.as_posix(),
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
            (temp_path / "single-fallback.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T06:00:00Z",
                        "targets_path": DEFAULT_LIVE_SMOKE_TARGETS_PATH.as_posix(),
                        "target": "jumpit_data_ai_ko",
                        "selected_url": "https://www.jumpit.co.kr/position/123",
                        "candidate_label": "fallback-ml",
                        "used_fallback": True,
                        "cleaned": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            reports = list_live_smoke_reports(
                temp_path,
                report_type="batch",
                target="remember_platform_ko",
                latest=1,
                used_fallback_only=True,
                failed_only=True,
            )

            self.assertEqual(1, len(reports))
            self.assertEqual(expected_batch, reports[0]["path"])
            self.assertEqual(1, reports[0]["fallback_success_count"])
            self.assertTrue(reports[0]["has_failures"])
            self.assertTrue(reports[0]["has_fallback"])

    def test_list_live_smoke_reports_rejects_invalid_type_filter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            with self.assertRaisesRegex(ValueError, "Unsupported live smoke report type filter"):
                list_live_smoke_reports(temp_path, report_type="weekly")

    def test_resolve_latest_live_smoke_report_returns_latest_matching_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            older_path = temp_path / "older.json"
            newer_path = temp_path / "newer.json"
            older_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T07:00:00Z",
                        "targets_path": DEFAULT_LIVE_SMOKE_TARGETS_PATH.as_posix(),
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
                        "failures": [{"target": "wanted_backend_ko", "message": "network failed"}],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            newer_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T08:00:00Z",
                        "targets_path": DEFAULT_LIVE_SMOKE_TARGETS_PATH.as_posix(),
                        "selected_targets": ["remember_platform_ko", "jumpit_data_ai_ko"],
                        "success_count": 2,
                        "failure_count": 0,
                        "successes": [
                            {
                                "target": "remember_platform_ko",
                                "selected_url": "https://career.rememberapp.co.kr/job/posting/275546",
                                "used_fallback": True,
                                "candidate_label": "fallback-devops",
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

            resolved = resolve_latest_live_smoke_report(
                temp_path,
                report_type="batch",
                target="remember_platform_ko",
                used_fallback_only=True,
            )

            self.assertEqual(newer_path, resolved)

    def test_resolve_latest_live_smoke_report_fails_when_no_report_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "broken.json").write_text("{not-json}\n", encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError,
                "No matching live smoke reports found.*filters: type=batch, failed_only=true.*Ignored invalid/unrecognized JSON files: 1",
            ):
                resolve_latest_live_smoke_report(temp_path, report_type="batch", failed_only=True)

    def test_resolve_latest_live_smoke_report_pair_returns_previous_and_current(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            oldest_path = temp_path / "oldest.json"
            previous_path = temp_path / "previous.json"
            current_path = temp_path / "current.json"

            oldest_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T06:00:00Z",
                        "targets_path": DEFAULT_LIVE_SMOKE_TARGETS_PATH.as_posix(),
                        "selected_targets": ["remember_platform_ko"],
                        "success_count": 1,
                        "failure_count": 0,
                        "successes": [
                            {"target": "remember_platform_ko", "selected_url": "https://career.rememberapp.co.kr/job/posting/111111", "used_fallback": False}
                        ],
                        "failures": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            previous_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T07:00:00Z",
                        "targets_path": DEFAULT_LIVE_SMOKE_TARGETS_PATH.as_posix(),
                        "selected_targets": ["remember_platform_ko"],
                        "success_count": 1,
                        "failure_count": 0,
                        "successes": [
                            {"target": "remember_platform_ko", "selected_url": "https://career.rememberapp.co.kr/job/posting/222222", "used_fallback": False}
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
                        "generated_at": "2026-04-08T08:00:00Z",
                        "targets_path": DEFAULT_LIVE_SMOKE_TARGETS_PATH.as_posix(),
                        "selected_targets": ["remember_platform_ko"],
                        "success_count": 1,
                        "failure_count": 0,
                        "successes": [
                            {"target": "remember_platform_ko", "selected_url": "https://career.rememberapp.co.kr/job/posting/333333", "used_fallback": True}
                        ],
                        "failures": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            resolved_previous, resolved_current = resolve_latest_live_smoke_report_pair(
                temp_path,
                report_type="batch",
                target="remember_platform_ko",
            )

            self.assertEqual(previous_path, resolved_previous)
            self.assertEqual(current_path, resolved_current)

    def test_resolve_latest_live_smoke_report_pair_fails_when_only_one_match_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "only.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T08:00:00Z",
                        "targets_path": DEFAULT_LIVE_SMOKE_TARGETS_PATH.as_posix(),
                        "selected_targets": ["remember_platform_ko"],
                        "success_count": 1,
                        "failure_count": 0,
                        "successes": [
                            {"target": "remember_platform_ko", "selected_url": "https://career.rememberapp.co.kr/job/posting/333333", "used_fallback": True}
                        ],
                        "failures": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "Need at least 2 matching live smoke reports.*recognized reports: 1",
            ):
                resolve_latest_live_smoke_report_pair(temp_path, report_type="batch", target="remember_platform_ko")

    def test_list_latest_live_smoke_entries_by_target_returns_latest_entry_per_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "older-batch.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T07:00:00Z",
                        "targets_path": DEFAULT_LIVE_SMOKE_TARGETS_PATH.as_posix(),
                        "selected_targets": ["remember_platform_ko", "wanted_backend_ko"],
                        "success_count": 1,
                        "failure_count": 1,
                        "successes": [
                            {
                                "target": "remember_platform_ko",
                                "selected_url": "https://career.rememberapp.co.kr/job/posting/222222",
                                "used_fallback": False,
                                "candidate_label": "primary",
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
                        "generated_at": "2026-04-08T08:00:00Z",
                        "targets_path": DEFAULT_LIVE_SMOKE_TARGETS_PATH.as_posix(),
                        "target": "remember_platform_ko",
                        "selected_url": "https://career.rememberapp.co.kr/job/posting/333333",
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

            entries = list_latest_live_smoke_entries_by_target(temp_path)

            self.assertEqual(2, len(entries))
            remember_entry = next(entry for entry in entries if entry["target"] == "remember_platform_ko")
            wanted_entry = next(entry for entry in entries if entry["target"] == "wanted_backend_ko")
            self.assertEqual("https://career.rememberapp.co.kr/job/posting/333333", remember_entry["selected_url"])
            self.assertTrue(remember_entry["used_fallback"])
            self.assertEqual("failure", wanted_entry["status"])
            self.assertEqual("network failed", wanted_entry["message"])

    def test_list_latest_live_smoke_entries_by_target_applies_entry_level_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "batch.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-08T08:00:00Z",
                        "targets_path": DEFAULT_LIVE_SMOKE_TARGETS_PATH.as_posix(),
                        "selected_targets": ["remember_platform_ko", "wanted_backend_ko"],
                        "success_count": 1,
                        "failure_count": 1,
                        "successes": [
                            {
                                "target": "remember_platform_ko",
                                "selected_url": "https://career.rememberapp.co.kr/job/posting/333333",
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

            fallback_entries = list_latest_live_smoke_entries_by_target(temp_path, used_fallback_only=True)
            failed_entries = list_latest_live_smoke_entries_by_target(temp_path, failed_only=True)

            self.assertEqual(["remember_platform_ko"], [entry["target"] for entry in fallback_entries])
            self.assertEqual(["wanted_backend_ko"], [entry["target"] for entry in failed_entries])

    def test_evaluate_live_smoke_report_health_marks_ok_stale_failed_and_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            targets_path = _write_test_live_smoke_targets_yaml(temp_path)
            now = datetime(2026, 4, 8, 9, 0, tzinfo=UTC)
            (temp_path / "batch.json").write_text(
                json.dumps(
                    {
                        "generated_at": (now - timedelta(hours=1)).isoformat(),
                        "targets_path": targets_path.as_posix(),
                        "selected_targets": ["remember_platform_ko", "wanted_backend_ko"],
                        "success_count": 1,
                        "failure_count": 1,
                        "successes": [
                            {
                                "target": "remember_platform_ko",
                                "selected_url": "https://career.rememberapp.co.kr/job/posting/293599",
                                "used_fallback": False,
                                "candidate_label": "primary",
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

            health_entries, scan_summary = evaluate_live_smoke_report_health(
                temp_path,
                targets_path=targets_path,
                max_age_hours=24,
                now=now,
            )

            self.assertEqual(2, len(health_entries))
            self.assertEqual(1, scan_summary["recognized_count"])
            remember_entry = next(entry for entry in health_entries if entry.target == "remember_platform_ko")
            wanted_entry = next(entry for entry in health_entries if entry.target == "wanted_backend_ko")
            self.assertEqual("ok", remember_entry.status)
            self.assertAlmostEqual(1.0, remember_entry.age_hours or 0.0, places=1)
            self.assertEqual("failed", wanted_entry.status)
            self.assertIn("network failed", wanted_entry.message or "")

    def test_evaluate_live_smoke_report_health_marks_stale_and_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            targets_path = _write_test_live_smoke_targets_yaml(temp_path)
            now = datetime(2026, 4, 8, 9, 0, tzinfo=UTC)
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

            health_entries, _scan_summary = evaluate_live_smoke_report_health(
                temp_path,
                targets_path=targets_path,
                max_age_hours=24,
                now=now,
            )

            remember_entry = next(entry for entry in health_entries if entry.target == "remember_platform_ko")
            wanted_entry = next(entry for entry in health_entries if entry.target == "wanted_backend_ko")
            self.assertEqual("stale", remember_entry.status)
            self.assertIn("older than 24h", remember_entry.message or "")
            self.assertEqual("missing", wanted_entry.status)

    def test_live_smoke_report_metadata_rejects_unrecognized_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            report_path = temp_path / "bad.json"
            report_path.write_text('{"foo":"bar"}\n', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Unrecognized live smoke report schema"):
                live_smoke_report_metadata(report_path)


if __name__ == "__main__":
    unittest.main()
