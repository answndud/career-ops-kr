from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from career_ops_kr.tracker import parse_tracker_rows
from career_ops_kr.web import app as web_app
from career_ops_kr.web import resume_tools
from career_ops_kr.web.db import connection_scope


class WebAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

        tmp_root = Path(self.tmpdir.name)
        self.db_path = tmp_root / "career-ops-web.db"
        self.upload_dir = tmp_root / "web-uploads"
        self.output_dir = tmp_root / "output"
        self.tracker_path = tmp_root / "applications.md"
        self.jd_dir = tmp_root / "jds"
        self.report_dir = tmp_root / "reports"

        self.env_patch = patch.dict(os.environ, {"CAREER_OPS_WEB_DB": self.db_path.as_posix()}, clear=False)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

        self.upload_patch = patch.object(resume_tools, "UPLOAD_DIR", self.upload_dir)
        self.upload_patch.start()
        self.addCleanup(self.upload_patch.stop)

        self.output_patch = patch.object(web_app, "OUTPUT_DIR", self.output_dir)
        self.output_patch.start()
        self.addCleanup(self.output_patch.stop)

        self.web_resume_output_patch = patch.object(web_app, "WEB_RESUME_OUTPUT_DIR", self.output_dir / "web-resumes")
        self.web_resume_output_patch.start()
        self.addCleanup(self.web_resume_output_patch.stop)

        self.tracker_patch = patch.object(web_app, "TRACKER_PATH", self.tracker_path)
        self.tracker_patch.start()
        self.addCleanup(self.tracker_patch.stop)

        self.jd_dir_patch = patch.object(web_app, "JD_DIR", self.jd_dir)
        self.jd_dir_patch.start()
        self.addCleanup(self.jd_dir_patch.stop)

        self.report_dir_patch = patch.object(web_app, "REPORT_DIR", self.report_dir)
        self.report_dir_patch.start()
        self.addCleanup(self.report_dir_patch.stop)

        self.client = TestClient(web_app.create_app())

    def test_pages_render(self) -> None:
        for route in ("/", "/search", "/settings", "/resume", "/assistant", "/tracker"):
            response = self.client.get(route)
            self.assertEqual(response.status_code, 200, route)
        home = self.client.get("/")
        search = self.client.get("/search")
        settings = self.client.get("/settings")
        self.assertNotIn("어시스턴트</a>", home.text)
        self.assertIn("AI 기능은 현재 기본 비활성화 상태입니다.", home.text)
        self.assertNotIn("Adzuna", home.text)
        self.assertNotIn("Adzuna", search.text)
        self.assertNotIn("ADZUNA_API_KEY", settings.text)
        self.assertIn("별도 API 키가 필요하지 않습니다.", settings.text)

    def test_settings_roundtrip(self) -> None:
        response = self.client.post("/api/settings", json={"key": "AI_PROVIDER", "value": "gemini"})
        self.assertEqual(response.status_code, 200)
        payload = self.client.get("/api/settings").json()
        self.assertEqual(payload["AI_PROVIDER"], "gemini")
        self.assertFalse(payload["ai_enabled"])
        self.assertEqual(payload["active_provider"], "disabled")

    def test_removed_search_setting_keys_are_rejected(self) -> None:
        response = self.client.post("/api/settings", json={"key": "ADZUNA_API_KEY", "value": "secret"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Invalid key")

    def test_ai_routes_are_disabled_by_default(self) -> None:
        for path, body in (
            ("/api/search/analyze", {"title": "Backend", "company": "Acme", "url": "https://example.com"}),
            ("/api/resume/match", {"resume_id": 1, "job_description": "Backend role"}),
            ("/api/resume/rewrite", {"job_description": "Backend role"}),
            ("/api/resume/recommend", {}),
            ("/api/ai/cover-letter", {"company": "Acme"}),
        ):
            response = self.client.post(path, json=body)
            self.assertEqual(response.status_code, 404, path)

    def test_jobs_crud_updates_tracker_file(self) -> None:
        create_response = self.client.post(
            "/api/jobs",
            json={
                "company": "Example Corp",
                "position": "Backend Engineer",
                "status": "검토중",
                "location": "Seoul",
                "source": "web",
            },
        )
        self.assertEqual(create_response.status_code, 201)
        created = create_response.json()
        self.assertEqual(created["company"], "Example Corp")

        rows = parse_tracker_rows(self.tracker_path.read_text(encoding="utf-8"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["company"], "Example Corp")

        update_response = self.client.put(
            f"/api/jobs/{created['id']}",
            json={"status": "지원예정", "notes": "Need portfolio refresh"},
        )
        self.assertEqual(update_response.status_code, 200)
        updated = self.client.get(f"/api/jobs/{created['id']}").json()
        self.assertEqual(updated["status"], "지원예정")
        self.assertEqual(updated["notes"], "Need portfolio refresh")

        rows = parse_tracker_rows(self.tracker_path.read_text(encoding="utf-8"))
        self.assertEqual(rows[0]["status"], "지원예정")
        self.assertEqual(rows[0]["notes"], "Need portfolio refresh")

        delete_response = self.client.delete(f"/api/jobs/{created['id']}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(self.client.get("/api/jobs").json(), [])
        rows = parse_tracker_rows(self.tracker_path.read_text(encoding="utf-8"))
        self.assertEqual(rows, [])

    def test_resume_upload_and_list(self) -> None:
        response = self.client.post(
            "/api/resume/upload",
            files={"file": ("resume.txt", b"Python\nFastAPI\nSQL", "text/plain")},
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["filename"], "resume.txt")
        resumes = self.client.get("/api/resume/upload").json()
        self.assertEqual(len(resumes), 1)
        self.assertEqual(resumes[0]["filename"], "resume.txt")

    def test_search_import_and_build_from_url_endpoint(self) -> None:
        import_response = self.client.post(
            "/api/import",
            json={
                "company": "Imported Inc",
                "title": "Platform Engineer",
                "url": "https://example.com/jobs/1",
                "location": "Seoul",
                "source": "원티드",
            },
        )
        self.assertEqual(import_response.status_code, 201)
        imported = import_response.json()
        self.assertEqual(imported["company"], "Imported Inc")

        fake_run_dir = self.output_dir / "web-resumes"
        fake_run_dir.mkdir(parents=True, exist_ok=True)
        self.jd_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        fake_artifacts = SimpleNamespace(
            job_path=self.jd_dir / "remember-job.md",
            report_path=self.report_dir / "remember-report.md",
            tracker_path=None,
            tailoring_path=self.output_dir / "tailoring.json",
            tailored_context_path=self.output_dir / "context.json",
            html_path=fake_run_dir / "resume.html",
            pdf_path=fake_run_dir / "resume.pdf",
        )

        with patch.object(web_app, "run_build_tailored_resume_from_url", return_value=fake_artifacts):
            response = self.client.post(
                "/api/resume/build-from-url",
                json={
                    "job_id": imported["id"],
                    "url": "https://career.rememberapp.co.kr/job/posting/293599",
                    "company": "Remember Co",
                    "position": "Platform Engineer",
                    "source": "원티드",
                    "role": "platform",
                    "language": "ko",
                    "pdf": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["job_id"], imported["id"])
        self.assertEqual(payload["html_url"], "/output/web-resumes/resume.html")
        self.assertEqual(payload["pdf_url"], "/output/web-resumes/resume.pdf")

        saved_job = self.client.get(f"/api/jobs/{imported['id']}").json()
        self.assertEqual(saved_job["job_path"], fake_artifacts.job_path.as_posix())
        self.assertEqual(saved_job["report_path"], fake_artifacts.report_path.as_posix())
        self.assertEqual(saved_job["html_path"], fake_artifacts.html_path.as_posix())
        self.assertEqual(saved_job["pdf_path"], fake_artifacts.pdf_path.as_posix())

    def test_search_endpoint_wiring(self) -> None:
        mocked = {
            "results": [
                {
                    "id": "wanted-1",
                    "title": "Backend Engineer",
                    "company": "Acme",
                    "location": "Seoul",
                    "source": "원티드",
                    "url": "https://example.com/jobs/1",
                    "type": "-",
                    "experience": "-",
                    "salary": "-",
                    "deadline": "-",
                    "description": "",
                }
            ],
            "count": 1,
            "translated_query": None,
            "sources": {"전체": 1, "원티드": 1},
        }
        with patch("career_ops_kr.web.app.search_jobs", return_value=mocked):
            response = self.client.get("/api/search", params={"q": "backend"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

    def test_home_dashboard_surfaces_recent_outputs(self) -> None:
        self.client.post(
            "/api/jobs",
            json={
                "company": "Acme",
                "position": "Platform Engineer",
                "status": "검토중",
                "source": "web",
            },
        )
        self.client.post(
            "/api/resume/upload",
            files={"file": ("resume.txt", b"Python\nFastAPI\nSQL", "text/plain")},
        )

        generated_dir = self.output_dir / "web-resumes"
        generated_dir.mkdir(parents=True, exist_ok=True)
        (generated_dir / "demo-resume.html").write_text("<html></html>", encoding="utf-8")
        (generated_dir / "demo-resume.pdf").write_bytes(b"%PDF-1.4")

        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        text = response.text
        self.assertIn("처음 쓰는 사람도 바로 시작할 수 있는 구직 대시보드", text)
        self.assertIn("demo-resume.html", text)
        self.assertIn("Acme", text)
        self.assertIn("resume.txt", text)
        self.assertIn("바로 시작할 수 있는 이력서 preset", text)
        self.assertIn("최근 생성한 웹 HTML/PDF", text)
        self.assertNotIn("최근 AI 출력", text)

    def test_dashboard_api_includes_recent_ai_outputs_and_artifact_paths(self) -> None:
        self.client.post(
            "/api/resume/upload",
            files={"file": ("resume.txt", b"Python\nFastAPI\nSQL", "text/plain")},
        )

        generated_dir = self.output_dir / "web-resumes"
        generated_dir.mkdir(parents=True, exist_ok=True)
        (generated_dir / "demo-resume.html").write_text("<html></html>", encoding="utf-8")
        (generated_dir / "demo-resume.pdf").write_bytes(b"%PDF-1.4")
        (self.output_dir / "resume-contexts").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "resume-contexts" / "demo-resume.json").write_text("{}", encoding="utf-8")
        (self.output_dir / "jds").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "reports").mkdir(parents=True, exist_ok=True)

        with connection_scope() as conn:
            conn.execute(
                "INSERT INTO ai_outputs(type, input_json, output) VALUES(?, ?, ?)",
                ("resume_rewrite", "{}", "Tailored summary output for dashboard preview"),
            )
            conn.commit()

        response = self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["totalResumes"], 1)
        self.assertEqual(payload["totalAiOutputs"], 1)
        self.assertEqual(payload["generatedResumeCount"], 1)
        self.assertEqual(payload["activeProvider"], "disabled")
        self.assertEqual(payload["recentGeneratedResumes"][0]["html_url"], "/output/web-resumes/demo-resume.html")
        self.assertEqual(payload["recentGeneratedResumes"][0]["pdf_url"], "/output/web-resumes/demo-resume.pdf")
        self.assertEqual(payload["recentGeneratedResumes"][0]["context_path"], (self.output_dir / "resume-contexts" / "demo-resume.json").as_posix())
        self.assertEqual(payload["recentAiOutputs"][0]["type"], "resume_rewrite")
        self.assertIn("Tailored summary output", payload["recentAiOutputs"][0]["preview"])

    def test_job_detail_page_and_artifact_views(self) -> None:
        create_response = self.client.post(
            "/api/jobs",
            json={
                "company": "Detail Co",
                "position": "Backend Engineer",
                "status": "검토중",
                "source": "web",
                "url": "https://example.com/jobs/detail-co",
                "notes": "Need a deeper review",
            },
        )
        self.assertEqual(create_response.status_code, 201)
        job_id = create_response.json()["id"]

        self.jd_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        context_dir = self.output_dir / "resume-contexts"
        context_dir.mkdir(parents=True, exist_ok=True)
        job_path = self.jd_dir / "detail-co.md"
        report_path = self.report_dir / "detail-co.md"
        context_path = context_dir / "detail-co.json"
        job_path.write_text("# JD\n\nBackend role", encoding="utf-8")
        report_path.write_text("# Report\n\nStrong fit", encoding="utf-8")
        context_path.write_text('{"headline":"Backend Engineer"}', encoding="utf-8")

        with connection_scope() as conn:
            conn.execute(
                "INSERT INTO resumes(filename, content, file_path) VALUES(?, ?, ?)",
                ("resume.txt", "Backend profile", None),
            )
            resume_id = conn.execute("SELECT id FROM resumes ORDER BY id DESC LIMIT 1").fetchone()["id"]
            conn.execute(
                """
                UPDATE jobs
                SET job_path = ?, report_path = ?, context_path = ?
                WHERE id = ?
                """,
                (job_path.as_posix(), report_path.as_posix(), context_path.as_posix(), job_id),
            )
            conn.execute(
                """
                INSERT INTO match_results(resume_id, job_id, job_description, match_score, analysis_json)
                VALUES(?, ?, ?, ?, ?)
                """,
                (resume_id, job_id, "Backend role", 91.0, "{}"),
            )
            conn.execute(
                "INSERT INTO ai_outputs(type, job_id, input_json, output) VALUES(?, ?, ?, ?)",
                ("job_analysis", job_id, "{}", "Detailed AI follow-up output"),
            )
            conn.commit()

        detail_response = self.client.get(f"/tracker/{job_id}")
        self.assertEqual(detail_response.status_code, 200)
        self.assertIn("Detail Co", detail_response.text)
        self.assertIn(f"/tracker/{job_id}/artifacts/report", detail_response.text)
        self.assertIn(f"/tracker/{job_id}/artifacts/context", detail_response.text)
        self.assertIn("이 공고에서 바로 맞춤 이력서 생성", detail_response.text)
        self.assertIn(f"Resume #{resume_id}", detail_response.text)
        self.assertNotIn("연결된 AI 출력", detail_response.text)

        job_artifact = self.client.get(f"/tracker/{job_id}/artifacts/job")
        report_artifact = self.client.get(f"/tracker/{job_id}/artifacts/report")
        context_artifact = self.client.get(f"/tracker/{job_id}/artifacts/context")
        self.assertEqual(job_artifact.status_code, 200)
        self.assertEqual(report_artifact.status_code, 200)
        self.assertEqual(context_artifact.status_code, 200)
        self.assertIn("Backend role", job_artifact.text)
        self.assertIn("Strong fit", report_artifact.text)
        self.assertIn("Backend Engineer", context_artifact.text)

    def test_database_backup_export_and_import_roundtrip(self) -> None:
        self.client.post(
            "/api/jobs",
            json={
                "company": "Backup Co",
                "position": "Platform Engineer",
                "status": "검토중",
                "source": "web",
            },
        )
        with connection_scope() as conn:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                ("ADZUNA_API_KEY", "legacy-secret"),
            )
            conn.commit()

        backup_response = self.client.post("/api/system/db/backup")
        self.assertEqual(backup_response.status_code, 200)
        backup_path = Path(backup_response.json()["backup_path"])
        self.assertTrue(backup_path.exists())

        export_response = self.client.post("/api/system/db/export")
        self.assertEqual(export_response.status_code, 200)
        export_path = Path(export_response.json()["export_path"])
        self.assertTrue(export_path.exists())
        exported_payload = json.loads(export_path.read_text(encoding="utf-8"))
        self.assertEqual(exported_payload["tables"]["jobs"][0]["company"], "Backup Co")
        self.assertNotIn("ADZUNA_API_KEY", {row["key"] for row in exported_payload["tables"]["settings"]})

        exported_payload["tables"]["settings"].append({"key": "ADZUNA_API_KEY", "value": "should-not-come-back"})
        export_path.write_text(json.dumps(exported_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        with connection_scope() as conn:
            conn.execute("DELETE FROM jobs")
            conn.execute("DELETE FROM settings")
            conn.commit()
        self.assertEqual(self.client.get("/api/jobs").json(), [])

        import_response = self.client.post(
            "/api/system/db/import",
            files={"file": (export_path.name, export_path.read_bytes(), "application/json")},
        )
        self.assertEqual(import_response.status_code, 200)
        restored_jobs = self.client.get("/api/jobs").json()
        self.assertEqual(len(restored_jobs), 1)
        self.assertEqual(restored_jobs[0]["company"], "Backup Co")
        settings_payload = self.client.get("/api/settings").json()
        self.assertNotIn("ADZUNA_API_KEY", settings_payload)
        with connection_scope() as conn:
            count = conn.execute("SELECT COUNT(*) AS count FROM settings WHERE key = ?", ("ADZUNA_API_KEY",)).fetchone()["count"]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
