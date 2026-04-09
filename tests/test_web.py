from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from career_ops_kr.tracker import parse_tracker_rows
from career_ops_kr.web import app as web_app
from career_ops_kr.web import resume_tools
from career_ops_kr.web import search as web_search
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

        self.live_smoke_dir_patch = patch.object(web_app, "LIVE_SMOKE_REPORT_DIR", self.output_dir / "live-smoke")
        self.live_smoke_dir_patch.start()
        self.addCleanup(self.live_smoke_dir_patch.stop)

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
        for route in ("/", "/search", "/settings", "/resume", "/assistant", "/tracker", "/artifacts"):
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

    def test_search_jobs_builds_high_signal_provider_statuses(self) -> None:
        wanted_result = web_search.JobSearchResult(
            id="wanted-1",
            title="Backend Engineer",
            company="Acme",
            location="Seoul",
            source="원티드",
            url="https://www.wanted.co.kr/wd/12345",
            type="-",
            experience="-",
            salary="-",
            deadline="-",
            description="",
        )
        with (
            patch(
                "career_ops_kr.web.search.translate_query",
                side_effect=lambda query, target_language: "backend" if target_language == "en" else "백엔드",
            ),
            patch("career_ops_kr.web.search._search_saramin", return_value=[]),
            patch("career_ops_kr.web.search._search_wanted", return_value=[wanted_result]),
            patch("career_ops_kr.web.search._search_efinancial", side_effect=httpx.ReadTimeout("timed out")),
        ):
            payload = web_search.search_jobs("백엔드")

        self.assertEqual(payload["provider_summary"]["ok"], 1)
        self.assertEqual(payload["provider_summary"]["empty"], 1)
        self.assertEqual(payload["provider_summary"]["error"], 1)
        self.assertIn("결과 없음 1개", payload["provider_summary"]["summary"])
        saramin_status = next(item for item in payload["provider_statuses"] if item["key"] == "saramin")
        self.assertEqual(saramin_status["status"], "empty")
        self.assertEqual(saramin_status["state_label"], "결과 없음")
        self.assertEqual(saramin_status["query_label"], "입력어")
        efinancial_status = next(item for item in payload["provider_statuses"] if item["key"] == "efinancial")
        self.assertEqual(efinancial_status["status"], "error")
        self.assertEqual(efinancial_status["query_label"], "영문 번역")
        self.assertEqual(efinancial_status["detail"], "요청 시간 초과")

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
        self.assertEqual(imported["save_result"], "created")
        self.assertEqual(imported["save_result_label"], "새 공고를 저장했습니다")
        self.assertFalse(imported["duplicate_guard_triggered"])

        fake_run_dir = self.output_dir / "web-resumes"
        fake_run_dir.mkdir(parents=True, exist_ok=True)
        self.jd_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        context_dir = self.output_dir / "resume-contexts"
        context_dir.mkdir(parents=True, exist_ok=True)
        fake_artifacts_context = context_dir / "context.json"
        fake_artifacts_context.write_text(
            json.dumps(
                {
                    "tailoringGuidance": {
                        "selection": {"selected_role_profile": "Platform"},
                        "focus": {"skills_to_emphasize": ["Terraform"]},
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        fake_artifacts = SimpleNamespace(
            job_path=self.jd_dir / "remember-job.md",
            report_path=self.report_dir / "remember-report.md",
            tracker_path=None,
            tailoring_path=self.output_dir / "tailoring.json",
            tailored_context_path=fake_artifacts_context,
            html_path=fake_run_dir / "resume.html",
            pdf_path=fake_run_dir / "resume.pdf",
            manifest_path=fake_run_dir / "resume.manifest.json",
        )
        fake_artifacts.manifest_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "pipeline": "build_tailored_resume_from_url",
                    "paths": {
                        "html_path": fake_artifacts.html_path.as_posix(),
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
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
        self.assertEqual(payload["manifest_url"], "/output/web-resumes/resume.manifest.json")
        self.assertEqual(payload["tailoring_guidance"]["selection"]["selected_role_profile"], "Platform")

        saved_job = self.client.get(f"/api/jobs/{imported['id']}").json()
        self.assertEqual(saved_job["job_path"], fake_artifacts.job_path.as_posix())
        self.assertEqual(saved_job["report_path"], fake_artifacts.report_path.as_posix())
        self.assertEqual(saved_job["html_path"], fake_artifacts.html_path.as_posix())
        self.assertEqual(saved_job["pdf_path"], fake_artifacts.pdf_path.as_posix())

    def test_import_uses_canonical_url_and_avoids_duplicates(self) -> None:
        first = self.client.post(
            "/api/import",
            json={
                "company": "Remember Co",
                "title": "Platform Engineer",
                "url": "https://career.rememberapp.co.kr/job/posting/293599",
                "location": "Seoul",
                "source": "리멤버",
            },
        )
        self.assertEqual(first.status_code, 201)
        first_payload = first.json()
        self.assertEqual(first_payload["save_result"], "created")

        second = self.client.post(
            "/api/import",
            json={
                "company": "Remember Co",
                "title": "Platform Engineer",
                "url": "https://career.rememberapp.co.kr/job/postings?postingId=293599",
                "location": "Seoul",
                "source": "remember",
                "description": "Duplicate import should reopen existing item.",
            },
        )
        self.assertEqual(second.status_code, 200)
        second_payload = second.json()
        self.assertEqual(second_payload["id"], first_payload["id"])
        self.assertIn(second_payload["save_result"], {"existing", "updated"})
        self.assertIn(second_payload["save_result_label"], {"기존 공고를 최신 정보로 보완했습니다", "이미 저장된 공고입니다"})
        self.assertIn("duplicate row는 만들지 않았습니다.", second_payload["save_detail"])
        self.assertTrue(second_payload["duplicate_guard_triggered"])
        self.assertEqual(second_payload["detail_url"], f"/tracker/{first_payload['id']}")
        self.assertIn("같은 canonical URL로 다시 저장해도 기존 항목을 재사용합니다.", second_payload["duplicate_guard_note"])

        jobs = self.client.get("/api/jobs").json()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(
            jobs[0]["canonical_url"],
            "https://career.rememberapp.co.kr/job/posting/293599",
        )

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
            "provider_statuses": [
                {
                    "key": "wanted",
                    "label": "원티드",
                    "status": "ok",
                    "tone": "ok",
                    "count": 1,
                    "state_label": "정상",
                    "detail": "1건 확인",
                    "query": "backend",
                    "query_label": "입력어",
                    "message": None,
                },
                {
                    "key": "saramin",
                    "label": "사람인",
                    "status": "error",
                    "tone": "error",
                    "count": 0,
                    "state_label": "오류",
                    "detail": "요청 시간 초과",
                    "query": "backend",
                    "query_label": "입력어",
                    "message": "요청 시간 초과",
                },
            ],
            "provider_summary": {
                "total": 2,
                "responded": 1,
                "ok": 1,
                "empty": 0,
                "error": 1,
                "failed_labels": ["사람인"],
                "empty_labels": [],
                "summary": "정상 1개 · 결과 없음 0개 · 실패 1개",
            },
            "degraded": True,
            "sources": {"전체": 1, "원티드": 1},
        }
        with patch("career_ops_kr.web.app.search_jobs", return_value=mocked):
            response = self.client.get("/api/search", params={"q": "backend"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertTrue(response.json()["degraded"])
        self.assertEqual(response.json()["provider_statuses"][1]["status"], "error")
        self.assertEqual(response.json()["provider_summary"]["error"], 1)

    def test_search_page_surfaces_provider_health_and_saved_job_state(self) -> None:
        created = self.client.post(
            "/api/jobs",
            json={
                "company": "Acme",
                "position": "Backend Engineer",
                "status": "지원예정",
                "source": "원티드",
                "url": "https://www.wanted.co.kr/wd/12345",
            },
        ).json()
        mocked = {
            "results": [
                {
                    "id": "wanted-1",
                    "title": "Backend Engineer",
                    "company": "Acme",
                    "location": "Seoul",
                    "source": "원티드",
                    "url": "https://www.wanted.co.kr/wd/12345",
                    "type": "-",
                    "experience": "-",
                    "salary": "-",
                    "deadline": "-",
                    "description": "",
                }
            ],
            "count": 1,
            "translated_query": None,
            "provider_statuses": [
                {
                    "key": "wanted",
                    "label": "원티드",
                    "status": "ok",
                    "tone": "ok",
                    "count": 1,
                    "state_label": "정상",
                    "detail": "1건 확인",
                    "query": "backend",
                    "query_label": "입력어",
                    "message": None,
                },
                {
                    "key": "saramin",
                    "label": "사람인",
                    "status": "error",
                    "tone": "error",
                    "count": 0,
                    "state_label": "오류",
                    "detail": "요청 시간 초과",
                    "query": "backend",
                    "query_label": "입력어",
                    "message": "요청 시간 초과",
                },
            ],
            "provider_summary": {
                "total": 2,
                "responded": 1,
                "ok": 1,
                "empty": 0,
                "error": 1,
                "failed_labels": ["사람인"],
                "empty_labels": [],
                "summary": "정상 1개 · 결과 없음 0개 · 실패 1개",
            },
            "degraded": True,
            "sources": {"전체": 1, "원티드": 1},
        }
        with patch("career_ops_kr.web.app.search_jobs", return_value=mocked):
            response = self.client.get("/search", params={"q": "backend"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("검색 source 상태", response.text)
        self.assertIn("정상 1개 · 결과 없음 0개 · 실패 1개", response.text)
        self.assertIn("일부 검색 소스가 일시적으로 실패했습니다.", response.text)
        self.assertIn("저장됨", response.text)
        self.assertIn("중복 저장 방지", response.text)
        self.assertIn("canonical URL 기준으로 이미 저장된 항목입니다.", response.text)
        self.assertIn(f"/tracker/{created['id']}", response.text)

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
        (self.output_dir / "cli-resume.html").write_text("<html></html>", encoding="utf-8")
        (self.output_dir / "live-smoke").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "live-smoke" / "batch-report.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-04-09T01:00:00+00:00",
                    "selected_targets": ["remember_platform_ko", "wanted_backend_ko"],
                    "success_count": 1,
                    "failure_count": 1,
                    "successes": [
                        {
                            "target": "remember_platform_ko",
                            "selected_url": "https://career.rememberapp.co.kr/job/posting/293599",
                            "used_fallback": False,
                        }
                    ],
                    "failures": [{"target": "wanted_backend_ko", "message": "404"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        text = response.text
        self.assertIn("처음 쓰는 사람도 바로 시작할 수 있는 구직 대시보드", text)
        self.assertIn("demo-resume.html", text)
        self.assertIn("cli-resume.html", text)
        self.assertIn("Acme", text)
        self.assertIn("resume.txt", text)
        self.assertIn("바로 시작할 수 있는 이력서 preset", text)
        self.assertIn("최근 생성한 HTML/PDF", text)
        self.assertIn("최근 live smoke 상태", text)
        self.assertIn("상세 상태 보기", text)
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
        (generated_dir / "demo-resume.manifest.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "pipeline": "build_tailored_resume_from_url",
                    "job": {"company": "Manifest Co", "title": "Platform Engineer"},
                    "selection": {"selected_role_profile": "Platform", "selected_domain": "platform"},
                    "focus": {"skills_to_emphasize": ["Terraform"]},
                    "paths": {
                        "html_path": (generated_dir / "demo-resume.html").as_posix(),
                        "pdf_path": (generated_dir / "demo-resume.pdf").as_posix(),
                        "context_path": (self.output_dir / "resume-contexts" / "demo-resume.json").as_posix(),
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.output_dir / "cli-resume.html").write_text("<html></html>", encoding="utf-8")
        (self.output_dir / "cli-resume.pdf").write_bytes(b"%PDF-1.4")
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
        self.assertEqual(payload["generatedResumeCount"], 2)
        self.assertEqual(payload["generatedWebResumeCount"], 1)
        self.assertEqual(payload["generatedCliResumeCount"], 1)
        self.assertEqual(payload["activeProvider"], "disabled")
        generated_by_url = {item["html_url"]: item for item in payload["recentGeneratedResumes"]}
        self.assertIn("/output/web-resumes/demo-resume.html", generated_by_url)
        self.assertIn("/output/cli-resume.html", generated_by_url)
        self.assertEqual(
            generated_by_url["/output/web-resumes/demo-resume.html"]["pdf_url"],
            "/output/web-resumes/demo-resume.pdf",
        )
        self.assertEqual(
            generated_by_url["/output/web-resumes/demo-resume.html"]["manifest_url"],
            "/output/web-resumes/demo-resume.manifest.json",
        )
        self.assertEqual(
            generated_by_url["/output/web-resumes/demo-resume.html"]["context_path"],
            (self.output_dir / "resume-contexts" / "demo-resume.json").as_posix(),
        )
        self.assertEqual(generated_by_url["/output/web-resumes/demo-resume.html"]["provenance"], "manifest")
        self.assertEqual(generated_by_url["/output/cli-resume.html"]["source_label"], "cli")
        self.assertEqual(generated_by_url["/output/cli-resume.html"]["provenance"], "legacy")
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
        context_path.write_text(
            json.dumps(
                {
                    "headline": "Backend Engineer",
                    "tailoringGuidance": {
                        "selection": {
                            "selected_domain": "Backend",
                            "selected_target_role": "Backend Engineer",
                            "selected_role_profile": "Backend",
                            "total_score": 4.2,
                            "recommendation": "지원 검토",
                        },
                        "focus": {
                            "skills_to_emphasize": ["Python", "FastAPI"],
                            "experience_focus": ["API reliability"],
                            "notes": ["서비스 트래픽 경험을 앞에 배치"],
                        },
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

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
        self.assertIn("최근 tailoring guidance", detail_response.text)
        self.assertIn("서비스 트래픽 경험을 앞에 배치", detail_response.text)

        job_artifact = self.client.get(f"/tracker/{job_id}/artifacts/job")
        report_artifact = self.client.get(f"/tracker/{job_id}/artifacts/report")
        context_artifact = self.client.get(f"/tracker/{job_id}/artifacts/context")
        self.assertEqual(job_artifact.status_code, 200)
        self.assertEqual(report_artifact.status_code, 200)
        self.assertEqual(context_artifact.status_code, 200)
        self.assertIn("Backend role", job_artifact.text)
        self.assertIn("Strong fit", report_artifact.text)
        self.assertIn("Backend Engineer", context_artifact.text)

    def test_job_detail_and_tracker_surface_next_actions(self) -> None:
        create_response = self.client.post(
            "/api/jobs",
            json={
                "company": "Next Step Co",
                "position": "Platform Engineer",
                "status": "지원예정",
                "source": "web",
                "url": "https://example.com/jobs/next-step",
                "follow_up": "2026-04-01",
            },
        )
        job_id = create_response.json()["id"]

        tracker_response = self.client.get("/tracker")
        self.assertEqual(tracker_response.status_code, 200)
        self.assertIn("리포트 없음", tracker_response.text)
        self.assertIn("팔로업 overdue", tracker_response.text)
        overdue_rows = self.client.get("/api/jobs", params={"attention": "follow-up-overdue"}).json()
        self.assertEqual(len(overdue_rows), 1)
        self.assertEqual(overdue_rows[0]["id"], job_id)

        detail_response = self.client.get(f"/tracker/{job_id}")
        self.assertEqual(detail_response.status_code, 200)
        self.assertIn("다음에 할 일", detail_response.text)
        self.assertIn("팔로업 날짜가 지났습니다. 상태와 메모를 갱신하세요.", detail_response.text)
        self.assertIn("공고 평가 리포트를 먼저 생성하세요.", detail_response.text)
        self.assertIn("상태와 메모 수정", detail_response.text)

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

    def test_settings_page_surfaces_live_smoke_summary(self) -> None:
        live_smoke_dir = self.output_dir / "live-smoke"
        live_smoke_dir.mkdir(parents=True, exist_ok=True)
        (live_smoke_dir / "single-report.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-04-09T03:00:00+00:00",
                    "target": "remember_platform_ko",
                    "selected_url": "https://career.rememberapp.co.kr/job/posting/293599",
                    "used_fallback": False,
                    "html_path": "/tmp/fake.html",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        response = self.client.get("/settings")
        self.assertEqual(response.status_code, 200)
        self.assertIn("포털 상태 점검", response.text)
        self.assertIn("문제 target", response.text)
        self.assertIn("saved report dir", response.text)

    def test_artifacts_page_surfaces_web_and_cli_outputs(self) -> None:
        generated_dir = self.output_dir / "web-resumes"
        generated_dir.mkdir(parents=True, exist_ok=True)
        (generated_dir / "web-platform.html").write_text("<html></html>", encoding="utf-8")
        (generated_dir / "web-platform.pdf").write_bytes(b"%PDF-1.4")
        (generated_dir / "web-platform.manifest.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "pipeline": "build_tailored_resume_from_url",
                    "job": {"company": "Manifest Platform", "title": "Platform Engineer"},
                    "selection": {"selected_role_profile": "Platform", "selected_domain": "platform"},
                    "focus": {"skills_to_emphasize": ["Kubernetes", "Terraform"]},
                    "paths": {
                        "html_path": (generated_dir / "web-platform.html").as_posix(),
                        "pdf_path": (generated_dir / "web-platform.pdf").as_posix(),
                        "context_path": (self.output_dir / "resume-contexts" / "web-platform.json").as_posix(),
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.output_dir / "cli-backend.html").write_text("<html></html>", encoding="utf-8")
        context_dir = self.output_dir / "resume-contexts"
        context_dir.mkdir(parents=True, exist_ok=True)
        (context_dir / "web-platform.json").write_text(
            json.dumps(
                {
                    "tailoringGuidance": {
                        "selection": {"selected_role_profile": "Platform", "selected_domain": "platform"},
                        "focus": {"skills_to_emphasize": ["Kubernetes", "Terraform"]},
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        response = self.client.get("/artifacts")
        self.assertEqual(response.status_code, 200)
        self.assertIn("생성된 이력서 산출물", response.text)
        self.assertIn("web-platform.html", response.text)
        self.assertIn("cli-backend.html", response.text)
        self.assertIn("Platform", response.text)
        self.assertIn("manifest", response.text)
        self.assertIn("생성된 이력서 산출물", response.text)

        filtered = self.client.get("/artifacts", params={"source": "cli"})
        self.assertEqual(filtered.status_code, 200)
        self.assertIn("cli-backend.html", filtered.text)


if __name__ == "__main__":
    unittest.main()
