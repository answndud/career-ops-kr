from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from career_ops_kr.scoring import score_job_file
from tests.fixtures.realistic_jds import REALISTIC_JD_SAMPLES


ROOT = Path(__file__).resolve().parents[1]
PROFILE_EXAMPLE = ROOT / "config/profile.example.yml"
SCORECARD = ROOT / "config/scorecard.kr.yml"


class ScoreJobFileTest(unittest.TestCase):
    def _score_realistic_sample(self, sample_key: str, slug: str):
        sample = REALISTIC_JD_SAMPLES[sample_key]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / f"{slug}.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        f'title: "{sample["title"]}"',
                        f'url: "https://example.com/jobs/{slug}"',
                        'source: "fixture"',
                        "---",
                        "",
                        f'# {sample["title"]}',
                        "",
                        sample["body"],
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )
            report = artifacts.report_path.read_text(encoding="utf-8")
        return artifacts, report

    def _assert_realistic_general_fixture(self, sample_key: str, slug: str, unsupported_family: str | None = None) -> None:
        artifacts, report = self._score_realistic_sample(sample_key, slug)
        self.assertIn("Selected Domain: General", report)
        self.assertIn("Selected Role Profile: General", report)
        if unsupported_family:
            self.assertIn(f"Unsupported Role Family: {unsupported_family}", report)
        self.assertLess(artifacts.total_score, 3.5)

    def test_score_job_file_writes_report_and_tracker_addition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "backend-job.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Senior Backend Engineer"',
                        'url: "https://example.com/jobs/backend"',
                        'source: "manual"',
                        "---",
                        "",
                        "# Senior Backend Engineer",
                        "",
                        "We are hiring a senior backend engineer with Python, AWS, Docker, and Kubernetes experience.",
                        "This is a remote role and English communication is required.",
                        "Our team builds AI tooling for B2B SaaS customers and shares salary ranges.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            tracker_line = artifacts.tracker_path.read_text(encoding="utf-8").strip()

            self.assertTrue(artifacts.report_path.exists())
            self.assertTrue(artifacts.tracker_path.exists())
            self.assertIn("Total Score:", report)
            self.assertIn("Recommendation:", report)
            self.assertIn("Selected Target Role: Senior Backend Engineer", report)
            self.assertIn("Selected Role Profile: Backend", report)
            self.assertIn(artifacts.report_path.as_posix(), tracker_line)
            self.assertIn("\t검토중\t", tracker_line)

    def test_score_job_file_respects_explicit_output_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "platform-job.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Platform Engineer"',
                        'url: "https://example.com/jobs/platform"',
                        'source: "wanted"',
                        "---",
                        "",
                        "# Platform Engineer",
                        "",
                        "Platform engineering role for Kubernetes, Terraform, and observability systems.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            report_path = temp_path / "custom" / "platform-report.md"
            tracker_path = temp_path / "custom" / "platform-addition.tsv"
            artifacts = score_job_file(
                job_path,
                report_path=report_path,
                tracker_path=tracker_path,
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            self.assertEqual(report_path, artifacts.report_path)
            self.assertEqual(tracker_path, artifacts.tracker_path)
            self.assertTrue(report_path.exists())
            self.assertTrue(tracker_path.exists())
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Target Role: Platform Engineer", report)
            self.assertIn("Selected Role Profile: Platform", report)

    def test_score_job_file_selects_data_ai_role_profile_from_target_role(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "ai-job.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Applied AI Engineer"',
                        'url: "https://example.com/jobs/ai"',
                        'source: "remember"',
                        "---",
                        "",
                        "# Applied AI Engineer",
                        "",
                        "We are hiring an applied ai engineer with LLM, RAG, eval, agent, and prompt experience.",
                        "The role focuses on model inference and experimentation for AI products.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Target Role: Applied AI Engineer", report)
            self.assertIn("Selected Role Profile: Data-AI", report)

    def test_score_job_file_respects_explicit_scorecard_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            profile_path = temp_path / "profile.yml"
            profile_path.write_text(
                "\n".join(
                    [
                        "candidate:",
                        "  name: Test User",
                        "preferences:",
                        "  preferred_languages:",
                        "    - ko",
                        "  work_modes:",
                        "    preferred:",
                        "      - remote",
                        "    acceptable:",
                        "      - hybrid",
                        "skills:",
                        "  primary:",
                        "    - Python",
                        "  secondary:",
                        "    - Docker",
                        "signals:",
                        "  preferred_domains:",
                        "    - ai tooling",
                        "  avoid_domains:",
                        "    - gambling",
                        "target_roles:",
                        "  - name: ML Platform Engineer",
                        "    scorecard_profile: data_ai",
                        "    keywords:",
                        "      - llmops",
                        "      - inference",
                        "      - platform",
                    ]
                ),
                encoding="utf-8",
            )
            job_path = temp_path / "ml-platform-job.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "ML Platform Engineer"',
                        'url: "https://example.com/jobs/ml-platform"',
                        'source: "manual"',
                        "---",
                        "",
                        "# ML Platform Engineer",
                        "",
                        "Build inference systems and llmops pipelines for AI product teams.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=profile_path,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Target Role: ML Platform Engineer", report)
            self.assertIn("Selected Role Profile: Data-AI", report)

    def test_score_job_file_falls_back_to_general_when_no_role_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "unmatched-job.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Sales Operations Manager"',
                        'url: "https://example.com/jobs/sales-ops"',
                        'source: "manual"',
                        "---",
                        "",
                        "# Sales Operations Manager",
                        "",
                        "We need a sales operations manager for CRM reporting and revenue planning.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Target Role: General", report)
            self.assertIn("Selected Role Profile: General", report)

    def test_score_job_file_selects_backend_role_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "backend-job.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Backend Engineer"',
                        'url: "https://example.com/jobs/backend"',
                        'source: "manual"',
                        "---",
                        "",
                        "# Backend Engineer",
                        "",
                        "Backend APIs, distributed systems, Python, and PostgreSQL are the core of this role.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Role Profile: Backend", report)
            self.assertIn("| role_alignment | 34 |", report)
            self.assertIn("| stack_overlap | 20 |", report)

    def test_score_job_file_selects_platform_role_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "platform-job.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Platform Engineer"',
                        'url: "https://example.com/jobs/platform"',
                        'source: "wanted"',
                        "---",
                        "",
                        "# Platform Engineer",
                        "",
                        "Kubernetes, Terraform, observability, and cloud reliability are the main platform responsibilities.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Role Profile: Platform", report)
            self.assertIn("| role_alignment | 30 |", report)
            self.assertIn("| stack_overlap | 22 |", report)

    def test_score_job_file_selects_data_ai_role_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "data-ai-job.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Applied AI Engineer"',
                        'url: "https://example.com/jobs/data-ai"',
                        'source: "manual"',
                        "---",
                        "",
                        "# Applied AI Engineer",
                        "",
                        "We build LLM, RAG, eval, prompt, and machine learning pipelines in Python.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Role Profile: Data-AI", report)
            self.assertIn("| role_alignment | 30 |", report)
            self.assertIn("| compensation_signal | 8 |", report)

    def test_score_job_file_selects_data_platform_role_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "data-platform-job.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Data Platform Engineer"',
                        'url: "https://example.com/jobs/data-platform"',
                        'source: "manual"',
                        "---",
                        "",
                        "# Data Platform Engineer",
                        "",
                        "We build data platform pipelines with Airflow, Spark, Kafka, and warehouse tooling for analytics products.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Target Role: Data Platform Engineer", report)
            self.assertIn("Selected Role Profile: Data-Platform", report)
            self.assertIn("| role_alignment | 31 |", report)
            self.assertIn("| company_signal | 7 |", report)

    def test_score_job_file_prefers_data_platform_over_data_ai_for_pipeline_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "pipeline-job.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Data Engineer"',
                        'url: "https://example.com/jobs/data-pipeline"',
                        'source: "manual"',
                        "---",
                        "",
                        "# Data Engineer",
                        "",
                        "Build data pipelines with Airflow, Spark, Kafka, ETL orchestration, and warehouse modeling.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Role Profile: Data-Platform", report)
            self.assertIn("Data Platform Engineer:", report)

    def test_score_job_file_does_not_pick_backend_from_generic_language_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "generic-python-job.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Automation Engineer"',
                        'url: "https://example.com/jobs/automation"',
                        'source: "manual"',
                        "---",
                        "",
                        "# Automation Engineer",
                        "",
                        "Python and Go are used for internal automation, scripting, and tooling support.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Target Role: General", report)
            self.assertIn("Selected Role Profile: General", report)

    def test_score_job_file_reports_role_specific_company_signals(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "ai-company-signal-job.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Applied AI Engineer"',
                        'url: "https://example.com/jobs/ai-company-signal"',
                        'source: "manual"',
                        "---",
                        "",
                        "# Applied AI Engineer",
                        "",
                        "We build ai tooling for research teams and ship llm inference systems for enterprise customers.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Role Profile: Data-AI", report)
            self.assertIn("- Role-specific positive company signals: 4", report)
            self.assertIn("- Avoid-domain matches: 0", report)

    def test_score_job_file_reports_role_specific_negative_company_signals(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "backend-negative-signal-job.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Backend Engineer"',
                        'url: "https://example.com/jobs/backend-negative"',
                        'source: "manual"',
                        "---",
                        "",
                        "# Backend Engineer",
                        "",
                        "Backend engineer role building backend APIs and distributed systems for outsourcing maintenance work in a gambling domain.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Role Profile: Backend", report)
            self.assertIn("- Avoid-domain matches: 1", report)
            self.assertIn("- Role-specific negative company signals: 2", report)

    def test_score_job_file_promotes_strong_backend_fit_to_aggressive_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "backend-strong-fit.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Senior Backend Engineer"',
                        'url: "https://example.com/jobs/backend-strong-fit"',
                        'source: "manual"',
                        "---",
                        "",
                        "# Senior Backend Engineer",
                        "",
                        "Senior backend engineer role building backend APIs, service backend systems, distributed systems, PostgreSQL, Redis, Kafka, AWS, Docker, and Kubernetes for a fintech B2B SaaS product.",
                        "Remote work, English communication, salary range, and stock options are provided.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Target Role: Senior Backend Engineer", report)
            self.assertIn("Selected Role Profile: Backend", report)
            self.assertIn("- Seniority Signal: senior", report)
            self.assertGreaterEqual(artifacts.total_score, 4.0)
            self.assertEqual("지원 적극 검토", artifacts.recommendation)

    def test_score_job_file_downgrades_general_mismatch_without_role_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "generic-mismatch-job.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Automation Engineer"',
                        'url: "https://example.com/jobs/automation-generic"',
                        'source: "manual"',
                        "---",
                        "",
                        "# Automation Engineer",
                        "",
                        "Software engineer role using Python and Docker in a cross-functional product team. Office based and Korean only.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Target Role: General", report)
            self.assertIn("Selected Role Profile: General", report)
            self.assertLess(artifacts.total_score, 3.0)
            self.assertEqual("스킵 권장", artifacts.recommendation)

    def test_score_job_file_scores_strong_data_platform_fit_in_high_band(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "data-platform-strong-fit.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Data Platform Engineer"',
                        'url: "https://example.com/jobs/data-platform-strong-fit"',
                        'source: "manual"',
                        "---",
                        "",
                        "# Data Platform Engineer",
                        "",
                        "Data platform engineer role owning ETL, Airflow, Spark, Kafka, dbt, BigQuery warehouse, batch and streaming pipelines for analytics experimentation products.",
                        "Hybrid work and compensation details are included for a B2B SaaS team.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Target Role: Data Platform Engineer", report)
            self.assertIn("Selected Role Profile: Data-Platform", report)
            self.assertGreaterEqual(artifacts.total_score, 4.0)
            self.assertEqual("지원 적극 검토", artifacts.recommendation)

    def test_score_job_file_scores_mixed_platform_fit_in_mid_band(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "platform-mixed-fit.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Platform Engineer"',
                        'url: "https://example.com/jobs/platform-mixed-fit"',
                        'source: "manual"',
                        "---",
                        "",
                        "# Platform Engineer",
                        "",
                        "Platform engineer role for Kubernetes, Terraform, observability, Prometheus, Grafana, and AWS infrastructure.",
                        "This is an onsite outsourcing engagement with no compensation details disclosed.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Target Role: Platform Engineer", report)
            self.assertIn("Selected Role Profile: Platform", report)
            self.assertGreaterEqual(artifacts.total_score, 3.0)
            self.assertLess(artifacts.total_score, 4.0)
            self.assertEqual("선별 검토", artifacts.recommendation)

    def test_score_job_file_prefers_data_ai_for_ai_heavy_ml_platform_jd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "ml-platform-ai-heavy.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "ML Platform Engineer"',
                        'url: "https://example.com/jobs/ml-platform-ai-heavy"',
                        'source: "manual"',
                        "---",
                        "",
                        "# ML Platform Engineer",
                        "",
                        "ML Platform Engineer building inference platforms, model serving, llmops, eval pipelines, embeddings infrastructure, observability, and kubernetes tooling for AI product teams.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Target Role: Applied AI Engineer", report)
            self.assertIn("Selected Role Profile: Data-AI", report)
            self.assertGreaterEqual(artifacts.total_score, 3.0)
            self.assertLess(artifacts.total_score, 4.0)

    def test_score_job_file_prefers_data_ai_for_ai_infrastructure_jd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "ai-infrastructure.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "AI Infrastructure Engineer"',
                        'url: "https://example.com/jobs/ai-infrastructure"',
                        'source: "manual"',
                        "---",
                        "",
                        "# AI Infrastructure Engineer",
                        "",
                        "AI Infrastructure Engineer building llmops, model serving, inference pipelines, embeddings retrieval, kubernetes, terraform, and observability for production AI products.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Data", report)
            self.assertIn("Selected Target Role: Applied AI Engineer", report)
            self.assertIn("Selected Role Profile: Data-AI", report)
            self.assertGreaterEqual(artifacts.total_score, 3.0)
            self.assertLess(artifacts.total_score, 4.5)

    def test_score_job_file_prefers_data_platform_for_data_platform_sre_jd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "data-platform-sre.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Data Platform SRE"',
                        'url: "https://example.com/jobs/data-platform-sre"',
                        'source: "manual"',
                        "---",
                        "",
                        "# Data Platform SRE",
                        "",
                        "Data Platform SRE operating airflow runtime, warehouse workflows, spark jobs, kafka streaming, data pipeline reliability, kubernetes, terraform, and observability for analytics systems.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Data", report)
            self.assertIn("Selected Target Role: Data Platform Engineer", report)
            self.assertIn("Selected Role Profile: Data-Platform", report)
            self.assertGreaterEqual(artifacts.total_score, 3.0)
            self.assertLess(artifacts.total_score, 4.5)

    def test_score_job_file_prefers_platform_for_platform_heavy_ml_platform_jd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "ml-platform-platform-heavy.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "ML Platform Engineer"',
                        'url: "https://example.com/jobs/ml-platform-platform-heavy"',
                        'source: "manual"',
                        "---",
                        "",
                        "# ML Platform Engineer",
                        "",
                        "ML Platform Engineer operating kubernetes clusters, terraform, observability, sre workflows, platform reliability, and deployment tooling for internal ML teams.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Target Role: Platform Engineer", report)
            self.assertIn("Selected Role Profile: Platform", report)
            self.assertGreaterEqual(artifacts.total_score, 4.0)
            self.assertEqual("지원 적극 검토", artifacts.recommendation)

    def test_score_job_file_prefers_data_platform_for_ai_team_data_infra_jd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "data-infra-ai-team.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Data Infrastructure Engineer"',
                        'url: "https://example.com/jobs/data-infra-ai-team"',
                        'source: "manual"',
                        "---",
                        "",
                        "# Data Infrastructure Engineer",
                        "",
                        "Data Infrastructure Engineer building Airflow, Spark, Kafka, warehouse and batch pipelines for internal ML and experimentation teams.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Data", report)
            self.assertIn("Selected Target Role: Data Platform Engineer", report)
            self.assertIn("Selected Role Profile: Data-Platform", report)
            self.assertGreaterEqual(artifacts.total_score, 3.5)
            self.assertLess(artifacts.total_score, 4.5)

    def test_score_job_file_keeps_platform_for_analytics_infrastructure_jd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "platform-analytics-infra.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Platform Engineer"',
                        'url: "https://example.com/jobs/platform-analytics-infra"',
                        'source: "manual"',
                        "---",
                        "",
                        "# Platform Engineer",
                        "",
                        "Platform Engineer responsible for kubernetes, terraform, observability, kafka operations, airflow platform reliability, and data workflow orchestration for product teams.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Platform", report)
            self.assertIn("Selected Target Role: Platform Engineer", report)
            self.assertIn("Selected Role Profile: Platform", report)
            self.assertGreaterEqual(artifacts.total_score, 3.4)
            self.assertLess(artifacts.total_score, 4.1)

    def test_score_job_file_prefers_data_platform_within_data_domain_over_data_ai(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "data-platform-vs-ai.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Data Engineer"',
                        'url: "https://example.com/jobs/data-platform-vs-ai"',
                        'source: "manual"',
                        "---",
                        "",
                        "# Data Engineer",
                        "",
                        "Engineer building feature pipelines, Airflow, Spark, warehouse models, training datasets, and experimentation pipelines for ML teams.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Data", report)
            self.assertIn("Selected Target Role: Data Platform Engineer", report)
            self.assertIn("Selected Role Profile: Data-Platform", report)
            self.assertGreaterEqual(artifacts.total_score, 3.0)
            self.assertLess(artifacts.total_score, 4.0)

    def test_score_job_file_prefers_data_platform_for_feature_pipeline_ml_jd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "feature-pipelines-ml.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Data Engineer"',
                        'url: "https://example.com/jobs/feature-pipelines-ml"',
                        'source: "manual"',
                        "---",
                        "",
                        "# Data Engineer",
                        "",
                        "Data engineer building feature pipelines, Airflow, Spark, warehouse models, and training datasets for ML experimentation teams.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Data", report)
            self.assertIn("Selected Role Profile: Data-Platform", report)
            self.assertGreaterEqual(artifacts.total_score, 3.0)
            self.assertLess(artifacts.total_score, 4.0)

    def test_score_job_file_prefers_data_ai_for_model_serving_pipeline_jd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "model-serving-data.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "AI Product Engineer"',
                        'url: "https://example.com/jobs/model-serving-data"',
                        'source: "manual"',
                        "---",
                        "",
                        "# AI Product Engineer",
                        "",
                        "Engineer building model serving pipelines, inference batch jobs, embeddings stores, feature retrieval, and Airflow orchestration for AI products.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Data", report)
            self.assertIn("Selected Role Profile: Data-AI", report)
            self.assertGreaterEqual(artifacts.total_score, 3.0)
            self.assertLess(artifacts.total_score, 4.0)

    def test_score_job_file_uses_data_platform_anchor_on_near_tie(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "data-platform-near-tie.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Data Platform Engineer"',
                        'url: "https://example.com/jobs/data-platform-near-tie"',
                        'source: "manual"',
                        "---",
                        "",
                        "# Data Platform Engineer",
                        "",
                        "Data platform engineer building feature store pipelines, training pipeline orchestration, Airflow jobs, warehouse models, and llm evaluation datasets for experimentation teams.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Data", report)
            self.assertIn("Selected Role Profile: Data-Platform", report)
            self.assertGreaterEqual(artifacts.total_score, 3.0)
            self.assertLess(artifacts.total_score, 4.0)

    def test_score_job_file_uses_data_ai_anchor_on_near_tie(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "data-ai-near-tie.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "AI Product Engineer"',
                        'url: "https://example.com/jobs/data-ai-near-tie"',
                        'source: "manual"',
                        "---",
                        "",
                        "# AI Product Engineer",
                        "",
                        "Engineer building model serving APIs, inference workflows, embeddings retrieval, and Airflow-based feature refresh pipelines for AI products.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Data", report)
            self.assertIn("Selected Role Profile: Data-AI", report)
            self.assertGreaterEqual(artifacts.total_score, 3.0)
            self.assertLess(artifacts.total_score, 4.0)

    def test_score_job_file_keeps_platform_domain_on_platform_data_near_tie(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "platform-domain-near-tie.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Platform Engineer"',
                        'url: "https://example.com/jobs/platform-domain-near-tie"',
                        'source: "manual"',
                        "---",
                        "",
                        "# Platform Engineer",
                        "",
                        "Engineer owning kubernetes, observability, reliability, airflow runtime, warehouse job operations, and terraform for analytics systems.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Platform", report)
            self.assertIn("Selected Role Profile: Platform", report)
            self.assertGreaterEqual(artifacts.total_score, 3.0)
            self.assertLess(artifacts.total_score, 4.0)

    def test_score_job_file_switches_to_data_domain_on_signal_heavier_near_tie(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "data-domain-near-tie.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        'title: "Data Platform Engineer"',
                        'url: "https://example.com/jobs/data-domain-near-tie"',
                        'source: "manual"',
                        "---",
                        "",
                        "# Data Platform Engineer",
                        "",
                        "Engineer owning airflow, warehouse, spark, feature store refresh, observability, and kubernetes operations for experimentation systems.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Data", report)
            self.assertIn("Selected Role Profile: Data-Platform", report)
            self.assertGreaterEqual(artifacts.total_score, 3.0)
            self.assertLess(artifacts.total_score, 4.0)

    def test_score_job_file_scores_realistic_backend_fintech_saas_fixture(self) -> None:
        sample = REALISTIC_JD_SAMPLES["backend_fintech_saas"]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "realistic-backend-fintech-saas.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        f'title: "{sample["title"]}"',
                        'url: "https://example.com/jobs/realistic-backend-fintech-saas"',
                        'source: "fixture"',
                        "---",
                        "",
                        f'# {sample["title"]}',
                        "",
                        sample["body"],
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Backend", report)
            self.assertIn("Selected Role Profile: Backend", report)
            self.assertGreaterEqual(artifacts.total_score, 3.2)
            self.assertLess(artifacts.total_score, 4.5)

    def test_score_job_file_scores_realistic_platform_security_fixture(self) -> None:
        sample = REALISTIC_JD_SAMPLES["devops_security_analytics"]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "realistic-platform-security.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        f'title: "{sample["title"]}"',
                        'url: "https://example.com/jobs/realistic-platform-security"',
                        'source: "fixture"',
                        "---",
                        "",
                        f'# {sample["title"]}',
                        "",
                        sample["body"],
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Platform", report)
            self.assertIn("Selected Role Profile: Platform", report)
            self.assertGreaterEqual(artifacts.total_score, 3.0)
            self.assertLess(artifacts.total_score, 4.5)

    def test_score_job_file_scores_realistic_data_ml_platform_fixture(self) -> None:
        sample = REALISTIC_JD_SAMPLES["data_ml_platform_ops"]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "realistic-data-ml-platform.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        f'title: "{sample["title"]}"',
                        'url: "https://example.com/jobs/realistic-data-ml-platform"',
                        'source: "fixture"',
                        "---",
                        "",
                        f'# {sample["title"]}',
                        "",
                        sample["body"],
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Platform", report)
            self.assertIn("Selected Role Profile: Platform", report)
            self.assertGreaterEqual(artifacts.total_score, 3.4)
            self.assertLess(artifacts.total_score, 4.5)

    def test_score_job_file_scores_realistic_llm_rag_service_fixture(self) -> None:
        sample = REALISTIC_JD_SAMPLES["llm_rag_service"]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "realistic-llm-rag-service.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        f'title: "{sample["title"]}"',
                        'url: "https://example.com/jobs/realistic-llm-rag-service"',
                        'source: "fixture"',
                        "---",
                        "",
                        f'# {sample["title"]}',
                        "",
                        sample["body"],
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Data", report)
            self.assertIn("Selected Role Profile: Data-AI", report)
            self.assertGreaterEqual(artifacts.total_score, 3.4)
            self.assertLess(artifacts.total_score, 4.5)

    def test_score_job_file_scores_realistic_feature_store_data_fixture(self) -> None:
        sample = REALISTIC_JD_SAMPLES["feature_store_data_platform"]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "realistic-feature-store-data.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        f'title: "{sample["title"]}"',
                        'url: "https://example.com/jobs/realistic-feature-store-data"',
                        'source: "fixture"',
                        "---",
                        "",
                        f'# {sample["title"]}',
                        "",
                        sample["body"],
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Data", report)
            self.assertIn("Selected Role Profile: Data-Platform", report)
            self.assertGreaterEqual(artifacts.total_score, 3.0)
            self.assertLess(artifacts.total_score, 4.5)

    def test_score_job_file_scores_realistic_streaming_data_infra_fixture(self) -> None:
        sample = REALISTIC_JD_SAMPLES["data_infra_streaming_engineer"]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "realistic-streaming-data-infra.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        f'title: "{sample["title"]}"',
                        'url: "https://example.com/jobs/realistic-streaming-data-infra"',
                        'source: "fixture"',
                        "---",
                        "",
                        f'# {sample["title"]}',
                        "",
                        sample["body"],
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Data", report)
            self.assertIn("Selected Role Profile: Data-Platform", report)
            self.assertGreaterEqual(artifacts.total_score, 3.2)
            self.assertLess(artifacts.total_score, 4.6)

    def test_score_job_file_scores_realistic_ai_platform_operations_fixture(self) -> None:
        sample = REALISTIC_JD_SAMPLES["ai_platform_operations"]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "realistic-ai-platform-operations.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        f'title: "{sample["title"]}"',
                        'url: "https://example.com/jobs/realistic-ai-platform-operations"',
                        'source: "fixture"',
                        "---",
                        "",
                        f'# {sample["title"]}',
                        "",
                        sample["body"],
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Platform", report)
            self.assertIn("Selected Role Profile: Platform", report)
            self.assertGreaterEqual(artifacts.total_score, 3.0)
            self.assertLess(artifacts.total_score, 4.5)

    def test_score_job_file_scores_realistic_ai_infrastructure_fixture_as_data_ai(self) -> None:
        sample = REALISTIC_JD_SAMPLES["ai_infrastructure_llmops"]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "realistic-ai-infrastructure.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        f'title: "{sample["title"]}"',
                        'url: "https://example.com/jobs/realistic-ai-infrastructure"',
                        'source: "fixture"',
                        "---",
                        "",
                        f'# {sample["title"]}',
                        "",
                        sample["body"],
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Data", report)
            self.assertIn("Selected Role Profile: Data-AI", report)
            self.assertGreaterEqual(artifacts.total_score, 3.0)
            self.assertLess(artifacts.total_score, 4.5)

    def test_score_job_file_scores_realistic_data_platform_sre_fixture_as_data_platform(self) -> None:
        sample = REALISTIC_JD_SAMPLES["data_platform_sre_observability"]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "realistic-data-platform-sre.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        f'title: "{sample["title"]}"',
                        'url: "https://example.com/jobs/realistic-data-platform-sre"',
                        'source: "fixture"',
                        "---",
                        "",
                        f'# {sample["title"]}',
                        "",
                        sample["body"],
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Data", report)
            self.assertIn("Selected Role Profile: Data-Platform", report)
            self.assertGreaterEqual(artifacts.total_score, 3.0)
            self.assertLess(artifacts.total_score, 4.5)

    def test_score_job_file_scores_realistic_analytics_infra_fixture_as_data_platform(self) -> None:
        sample = REALISTIC_JD_SAMPLES["analytics_infrastructure_experimentation"]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "realistic-analytics-infrastructure.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        f'title: "{sample["title"]}"',
                        'url: "https://example.com/jobs/realistic-analytics-infrastructure"',
                        'source: "fixture"',
                        "---",
                        "",
                        f'# {sample["title"]}',
                        "",
                        sample["body"],
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Data", report)
            self.assertIn("Selected Role Profile: Data-Platform", report)
            self.assertGreaterEqual(artifacts.total_score, 3.0)
            self.assertLess(artifacts.total_score, 4.5)

    def test_score_job_file_scores_realistic_devops_data_platform_fixture_as_platform(self) -> None:
        sample = REALISTIC_JD_SAMPLES["devops_data_platform_foundations"]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "realistic-devops-data-platform.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        f'title: "{sample["title"]}"',
                        'url: "https://example.com/jobs/realistic-devops-data-platform"',
                        'source: "fixture"',
                        "---",
                        "",
                        f'# {sample["title"]}',
                        "",
                        sample["body"],
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Platform", report)
            self.assertIn("Selected Role Profile: Platform", report)
            self.assertGreaterEqual(artifacts.total_score, 3.0)
            self.assertLess(artifacts.total_score, 4.5)

    def test_score_job_file_scores_realistic_mlops_fixture_as_data_ai(self) -> None:
        sample = REALISTIC_JD_SAMPLES["mlops_inference_runtime"]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "realistic-mlops.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        f'title: "{sample["title"]}"',
                        'url: "https://example.com/jobs/realistic-mlops"',
                        'source: "fixture"',
                        "---",
                        "",
                        f'# {sample["title"]}',
                        "",
                        sample["body"],
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Data", report)
            self.assertIn("Selected Role Profile: Data-AI", report)
            self.assertGreaterEqual(artifacts.total_score, 3.0)
            self.assertLess(artifacts.total_score, 4.5)

    def test_score_job_file_scores_realistic_frontend_fixture_as_general(self) -> None:
        sample = REALISTIC_JD_SAMPLES["frontend_next_typescript"]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "realistic-frontend.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        f'title: "{sample["title"]}"',
                        'url: "https://example.com/jobs/realistic-frontend"',
                        'source: "fixture"',
                        "---",
                        "",
                        f'# {sample["title"]}',
                        "",
                        sample["body"],
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: General", report)
            self.assertIn("Selected Role Profile: General", report)
            self.assertLess(artifacts.total_score, 3.5)

    def test_score_job_file_scores_realistic_ios_fixture_as_general(self) -> None:
        sample = REALISTIC_JD_SAMPLES["ios_native_mobile"]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "realistic-ios.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        f'title: "{sample["title"]}"',
                        'url: "https://example.com/jobs/realistic-ios"',
                        'source: "fixture"',
                        "---",
                        "",
                        f'# {sample["title"]}',
                        "",
                        sample["body"],
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: General", report)
            self.assertIn("Selected Role Profile: General", report)
            self.assertLess(artifacts.total_score, 3.5)

    def test_score_job_file_scores_realistic_product_design_fixture_as_general(self) -> None:
        self._assert_realistic_general_fixture(
            "product_designer_design_system",
            "realistic-product-design",
            unsupported_family="Product Design",
        )

    def test_score_job_file_scores_realistic_qa_fixture_as_general(self) -> None:
        self._assert_realistic_general_fixture(
            "qa_automation_platform_quality",
            "realistic-qa-automation",
            unsupported_family="QA",
        )

    def test_score_job_file_scores_realistic_embedded_fixture_as_general(self) -> None:
        self._assert_realistic_general_fixture(
            "embedded_firmware_iot",
            "realistic-embedded-firmware",
            unsupported_family="Embedded",
        )

    def test_score_job_file_scores_realistic_game_client_fixture_as_general(self) -> None:
        self._assert_realistic_general_fixture(
            "game_client_unity_liveops",
            "realistic-game-client",
            unsupported_family="Game Client",
        )

    def test_score_job_file_scores_realistic_ml_research_fixture_as_data_ai(self) -> None:
        sample = REALISTIC_JD_SAMPLES["generative_ai_research_engineer"]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "realistic-ml-research.md"
            job_path.write_text(
                "\n".join(
                    [
                        "---",
                        f'title: "{sample["title"]}"',
                        'url: "https://example.com/jobs/realistic-ml-research"',
                        'source: "fixture"',
                        "---",
                        "",
                        f'# {sample["title"]}',
                        "",
                        sample["body"],
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            artifacts = score_job_file(
                job_path,
                report_dir=temp_path / "reports",
                tracker_dir=temp_path / "tracker-additions",
                profile_path=PROFILE_EXAMPLE,
                scorecard_path=SCORECARD,
            )

            report = artifacts.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected Domain: Data", report)
            self.assertIn("Selected Role Profile: Data-AI", report)
            self.assertGreaterEqual(artifacts.total_score, 3.0)
            self.assertLess(artifacts.total_score, 4.5)


if __name__ == "__main__":
    unittest.main()
