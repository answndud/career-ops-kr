from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

from career_ops_kr.tracker import audit_tracker_jobs, merge_tracker_additions, normalize_tracker_statuses


class TrackerMergeTest(unittest.TestCase):
    def test_merge_tracker_additions_supports_recursive_subdirectories(self) -> None:
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

            merged = merge_tracker_additions(
                tracker_path,
                temp_path / "tracker-additions",
                recursive=True,
            )
            changed = normalize_tracker_statuses(tracker_path)
            content = tracker_path.read_text(encoding="utf-8")

            self.assertEqual(1, merged)
            self.assertEqual(0, changed)
            self.assertIn("Example Corp", content)
            self.assertIn("Platform Engineer", content)
            self.assertIn("검토중", content)

    def test_audit_tracker_jobs_reports_missing_artifacts_and_legacy_html(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            tracker_path = temp_path / "applications.md"
            report_path = temp_path / "reports" / "existing-report.md"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text("# Report", encoding="utf-8")
            output_dir = temp_path / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "legacy.html").write_text("<html></html>", encoding="utf-8")

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

            result = audit_tracker_jobs(
                tracker_path,
                repo_root=temp_path,
                output_dir=output_dir,
            )

            self.assertEqual(2, result.tracker_row_count)
            self.assertEqual(1, result.counts["missing_resume"])
            self.assertEqual(1, result.counts["missing_report_file"])
            self.assertEqual(1, result.counts["missing_resume_file"])
            self.assertEqual(1, result.counts["legacy_html"])
            self.assertFalse(result.ok)

    def test_audit_tracker_jobs_reports_manifest_and_artifact_index_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            tracker_path = temp_path / "applications.md"
            output_dir = temp_path / "output"
            html_path = output_dir / "web-resumes" / "alpha-platform.html"
            manifest_path = html_path.with_suffix(".manifest.json")
            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text("<html></html>", encoding="utf-8")
            tracker_path.write_text(
                "\n".join(
                    [
                        "# Applications Tracker",
                        "",
                        "| ID | Date | Company | Role | Score | Status | Source | Resume | Report | Notes |",
                        "|----|------|---------|------|-------|--------|--------|--------|--------|-------|",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            manifest_path.write_text(
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
                            },
                            "web-resumes/orphan.html": {
                                "inventory_key": "web-resumes/orphan.html",
                                "build_run_id": "br_orphan",
                                "generated_at": "2026-04-11T00:00:00+00:00",
                                "pipeline": "build_tailored_resume_from_url",
                                "manifest_path": "output/web-resumes/orphan.manifest.json",
                                "html_path": "output/web-resumes/orphan.html",
                                "pdf_path": None,
                            },
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            result = audit_tracker_jobs(
                tracker_path,
                repo_root=temp_path,
                output_dir=output_dir,
            )

            self.assertEqual(0, result.tracker_row_count)
            self.assertEqual(1, result.counts["manifest_missing_context_file"])
            self.assertEqual(1, result.counts["artifact_index_entry_mismatch"])
            self.assertEqual(1, result.counts["orphan_artifact_index_entry"])
            self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
