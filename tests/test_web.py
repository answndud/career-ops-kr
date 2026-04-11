from __future__ import annotations

import os
import json
import tempfile
import unittest
from datetime import date, timedelta
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
        for route in ("/", "/search", "/follow-ups", "/settings", "/resume", "/tracker", "/artifacts"):
            response = self.client.get(route)
            self.assertEqual(response.status_code, 200, route)
        home = self.client.get("/")
        search = self.client.get("/search")
        settings = self.client.get("/settings")
        self.assertNotIn("어시스턴트</a>", home.text)
        self.assertNotIn("Adzuna", home.text)
        self.assertNotIn("Adzuna", search.text)
        self.assertIn("별도 API 키가 필요하지 않습니다.", settings.text)
        tracker = self.client.get("/tracker")
        self.assertIn("선택 항목 일괄 변경", tracker.text)
        self.assertIn("보이는 항목 전체 선택", tracker.text)

    def test_runtime_paths_follow_current_output_root_when_overrides_are_unset(self) -> None:
        with (
            patch.object(web_app, "WEB_RESUME_OUTPUT_DIR", None),
            patch.object(web_app, "LIVE_SMOKE_REPORT_DIR", None),
        ):
            paths = web_app._web_paths()
            deps = web_app._router_deps()

        self.assertEqual(paths.output_dir, self.output_dir)
        self.assertEqual(paths.web_resume_output_dir, self.output_dir / "web-resumes")
        self.assertEqual(paths.live_smoke_report_dir, self.output_dir / "live-smoke")
        self.assertEqual(paths.web_db_output_dir, self.output_dir / "web-db")
        self.assertEqual(deps.output_dir, self.output_dir)
        self.assertEqual(deps.web_resume_output_dir, self.output_dir / "web-resumes")

    def test_follow_up_agenda_page_and_api(self) -> None:
        today = date.today()
        overdue = (today - timedelta(days=2)).isoformat()
        due_today = today.isoformat()
        upcoming = (today + timedelta(days=3)).isoformat()
        later = (today + timedelta(days=10)).isoformat()
        self.client.post(
            "/api/jobs",
            json={
                "company": "Overdue Co",
                "position": "Backend Engineer",
                "status": "지원예정",
                "follow_up": overdue,
                "source": "web",
            },
        )
        self.client.post(
            "/api/jobs",
            json={
                "company": "Today Co",
                "position": "Platform Engineer",
                "status": "검토중",
                "follow_up": due_today,
                "source": "web",
            },
        )
        self.client.post(
            "/api/jobs",
            json={
                "company": "Upcoming Co",
                "position": "Data Engineer",
                "status": "지원완료",
                "follow_up": upcoming,
                "source": "web",
            },
        )
        self.client.post(
            "/api/jobs",
            json={
                "company": "Later Co",
                "position": "SRE",
                "status": "지원완료",
                "follow_up": later,
                "source": "web",
            },
        )
        self.client.post(
            "/api/jobs",
            json={
                "company": "No Date Co",
                "position": "Platform Engineer",
                "status": "검토중",
                "source": "web",
            },
        )

        page = self.client.get("/follow-ups")
        self.assertEqual(page.status_code, 200)
        self.assertIn("오늘 먼저 정리해야 할 팔로업만 모아보기", page.text)
        self.assertIn("Overdue Co", page.text)
        self.assertIn("Today Co", page.text)
        self.assertIn("Upcoming Co", page.text)
        self.assertIn("No Date Co", page.text)
        self.assertIn("오늘로", page.text)
        self.assertIn("3일 뒤", page.text)
        self.assertIn("7일 뒤", page.text)
        self.assertIn("미설정", page.text)

        payload = self.client.get("/api/follow-ups").json()
        self.assertEqual(payload["counts"]["overdue"], 1)
        self.assertEqual(payload["counts"]["today"], 1)
        self.assertEqual(payload["counts"]["upcoming"], 1)
        self.assertEqual(payload["counts"]["later"], 1)
        self.assertEqual(payload["counts"]["unscheduled_active"], 1)
        self.assertEqual(payload["preview_items"][0]["company"], "Overdue Co")

    def test_follow_up_quick_action_updates_schedule(self) -> None:
        today = date.today()
        overdue = (today - timedelta(days=1)).isoformat()
        created = self.client.post(
            "/api/jobs",
            json={
                "company": "Quick Action Co",
                "position": "Backend Engineer",
                "status": "검토중",
                "follow_up": overdue,
                "source": "web",
            },
        ).json()

        move_response = self.client.post(
            f"/api/jobs/{created['id']}/follow-up-quick",
            json={"action": "plus7"},
        )
        self.assertEqual(move_response.status_code, 200)
        moved_payload = move_response.json()
        self.assertEqual(moved_payload["follow_up"], (today + timedelta(days=7)).isoformat())

        agenda = self.client.get("/api/follow-ups").json()
        self.assertEqual(agenda["counts"]["overdue"], 0)
        self.assertEqual(agenda["counts"]["upcoming"], 1)

        clear_response = self.client.post(
            f"/api/jobs/{created['id']}/follow-up-quick",
            json={"action": "clear"},
        )
        self.assertEqual(clear_response.status_code, 200)
        self.assertIsNone(clear_response.json()["follow_up"])

        cleared_agenda = self.client.get("/api/follow-ups").json()
        self.assertEqual(cleared_agenda["counts"]["upcoming"], 0)
        self.assertEqual(cleared_agenda["counts"]["unscheduled_active"], 1)

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
        update_payload = update_response.json()
        self.assertEqual(update_payload["status"], "지원예정")
        self.assertIn("attention", update_payload)
        self.assertIn("artifact_summary", update_payload)
        self.assertIn("tracker_row", update_payload)
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

    def test_jobs_bulk_update_updates_tracker_rows(self) -> None:
        first = self.client.post(
            "/api/jobs",
            json={
                "company": "Bulk One",
                "position": "Backend Engineer",
                "status": "검토중",
                "location": "Seoul",
                "source": "web",
            },
        ).json()
        second = self.client.post(
            "/api/jobs",
            json={
                "company": "Bulk Two",
                "position": "Platform Engineer",
                "status": "검토중",
                "location": "Busan",
                "source": "web",
            },
        ).json()

        response = self.client.post(
            "/api/jobs/bulk-update",
            json={
                "ids": [first["id"], second["id"]],
                "status": "지원예정",
                "follow_up": "2026-04-15",
                "source": "wanted",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["updated_count"], 2)
        self.assertEqual(payload["updated_ids"], [first["id"], second["id"]])
        self.assertEqual(payload["fields"], ["follow_up", "source", "status"])
        self.assertEqual(
            payload["field_values"],
            {"status": "지원예정", "follow_up": "2026-04-15", "source": "wanted"},
        )
        self.assertEqual(payload["job_labels"], ["#1 Bulk One", "#2 Bulk Two"])
        self.assertEqual(payload["jobs"][0]["attention"]["summary"], "공고 평가 리포트를 먼저 생성하세요.")

        jobs = self.client.get("/api/jobs").json()
        for job in jobs:
            self.assertEqual(job["status"], "지원예정")
            self.assertEqual(job["follow_up"], "2026-04-15")
            self.assertEqual(job["source"], "wanted")

        rows = parse_tracker_rows(self.tracker_path.read_text(encoding="utf-8"))
        self.assertEqual(["지원예정", "지원예정"], [row["status"] for row in rows])
        self.assertEqual(["wanted", "wanted"], [row["source"] for row in rows])

    def test_jobs_bulk_update_rejects_missing_ids_and_fields(self) -> None:
        response = self.client.post("/api/jobs/bulk-update", json={"ids": [], "status": "지원예정"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "No job ids selected")

        created = self.client.post(
            "/api/jobs",
            json={
                "company": "Bulk Guard",
                "position": "Backend Engineer",
                "status": "검토중",
                "source": "web",
            },
        ).json()
        response = self.client.post("/api/jobs/bulk-update", json={"ids": [created["id"]]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "No bulk fields to update")

        response = self.client.post(
            "/api/jobs/bulk-update",
            json={"ids": [created["id"], created["id"] + 999], "status": "지원예정"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("Missing job ids", response.json()["detail"])

    def test_jobs_bulk_update_rejects_tracker_synced_fields_for_trackerless_rows(self) -> None:
        created = self.client.post(
            "/api/jobs",
            json={
                "company": "Trackerless Bulk",
                "position": "Backend Engineer",
                "status": "검토중",
                "source": "web",
            },
        ).json()

        with connection_scope() as conn:
            conn.execute("UPDATE jobs SET tracker_id = NULL WHERE id = ?", (created["id"],))
            conn.commit()

        response = self.client.post(
            "/api/jobs/bulk-update",
            json={"ids": [created["id"]], "status": "지원예정"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Tracker-linked fields require tracker_id", response.json()["detail"])

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
        self.assertEqual(efinancial_status["query_label"], "입력어")
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

    def test_search_presets_can_be_saved_reused_and_deleted(self) -> None:
        save_response = self.client.post(
            "/api/search-presets",
            json={"name": "플랫폼 기본", "query": "platform engineer"},
        )
        self.assertEqual(save_response.status_code, 200)
        payload = save_response.json()
        preset = payload["preset"]
        self.assertEqual(preset["name"], "플랫폼 기본")
        self.assertEqual(preset["query"], "platform engineer")
        self.assertTrue(preset["is_default"])
        self.assertIsNone(preset["last_used_at"])
        self.assertEqual(len(payload["presets"]), 1)

        list_response = self.client.get("/api/search-presets")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["presets"][0]["key"], preset["key"])

        mocked = {
            "results": [
                {
                    "id": "wanted-1",
                    "title": "Platform Engineer",
                    "company": "Preset Co",
                    "location": "Seoul",
                    "source": "원티드",
                    "url": "https://www.wanted.co.kr/wd/54321",
                    "type": "-",
                    "experience": "-",
                    "salary": "-",
                    "deadline": "-",
                    "description": "",
                }
            ],
            "count": 1,
            "translated_query": None,
            "provider_statuses": [],
            "provider_summary": None,
            "degraded": False,
            "sources": {"전체": 1, "원티드": 1},
        }
        with patch("career_ops_kr.web.app.search_jobs", return_value=mocked) as search_mock:
            page_response = self.client.get("/search", params={"preset": preset["key"]})
        self.assertEqual(page_response.status_code, 200)
        self.assertIn("저장된 preset으로 검색 중", page_response.text)
        self.assertIn("platform engineer", page_response.text)
        self.assertIn("플랫폼 기본", page_response.text)
        self.assertIn("기본 preset", page_response.text)
        search_mock.assert_called_once_with("platform engineer")

        used_list_response = self.client.get("/api/search-presets")
        self.assertEqual(used_list_response.status_code, 200)
        self.assertIsNotNone(used_list_response.json()["presets"][0]["last_used_at"])

        delete_response = self.client.delete(f"/api/search-presets/{preset['key']}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["presets"], [])

    def test_search_page_uses_default_preset_when_query_is_empty(self) -> None:
        first_response = self.client.post(
            "/api/search-presets",
            json={"name": "플랫폼 기본", "query": "platform engineer"},
        )
        self.assertEqual(first_response.status_code, 200)
        first_preset = first_response.json()["preset"]

        second_response = self.client.post(
            "/api/search-presets",
            json={"name": "데이터 기본", "query": "data platform", "make_default": True},
        )
        self.assertEqual(second_response.status_code, 200)
        second_preset = second_response.json()["preset"]
        self.assertTrue(second_preset["is_default"])

        default_response = self.client.post(f"/api/search-presets/{first_preset['key']}/default")
        self.assertEqual(default_response.status_code, 200)
        self.assertTrue(default_response.json()["preset"]["is_default"])

        mocked = {
            "results": [
                {
                    "id": "wanted-2",
                    "title": "Platform Engineer",
                    "company": "Default Co",
                    "location": "Seoul",
                    "source": "원티드",
                    "url": "https://www.wanted.co.kr/wd/99999",
                    "type": "-",
                    "experience": "-",
                    "salary": "-",
                    "deadline": "-",
                    "description": "",
                }
            ],
            "count": 1,
            "translated_query": None,
            "provider_statuses": [],
            "provider_summary": None,
            "degraded": False,
            "sources": {"전체": 1, "원티드": 1},
        }
        with patch("career_ops_kr.web.app.search_jobs", return_value=mocked) as search_mock:
            page_response = self.client.get("/search")
        self.assertEqual(page_response.status_code, 200)
        self.assertIn("기본 preset으로 검색 중", page_response.text)
        self.assertIn("플랫폼 기본", page_response.text)
        search_mock.assert_called_once_with("platform engineer")

        list_response = self.client.get("/api/search-presets")
        self.assertEqual(list_response.status_code, 200)
        presets = list_response.json()["presets"]
        presets_by_key = {item["key"]: item for item in presets}
        self.assertTrue(presets_by_key[first_preset["key"]]["is_default"])
        self.assertFalse(presets_by_key[second_preset["key"]]["is_default"])
        self.assertIsNotNone(presets_by_key[first_preset["key"]]["last_used_at"])

    def test_search_preset_save_rejects_empty_query(self) -> None:
        response = self.client.post("/api/search-presets", json={"name": "빈 검색", "query": "   "})
        self.assertEqual(response.status_code, 400)
        self.assertIn("검색어가 비어 있습니다.", response.json()["detail"])

    def test_home_dashboard_surfaces_recent_outputs(self) -> None:
        overdue = (date.today() - timedelta(days=1)).isoformat()
        created_job = self.client.post(
            "/api/jobs",
            json={
                "company": "Acme",
                "position": "Platform Engineer",
                "status": "검토중",
                "source": "web",
                "follow_up": overdue,
            },
        ).json()
        self.client.post(
            "/api/resume/upload",
            files={"file": ("resume.txt", b"Python\nFastAPI\nSQL", "text/plain")},
        )

        generated_dir = self.output_dir / "web-resumes"
        generated_dir.mkdir(parents=True, exist_ok=True)
        (generated_dir / "demo-resume.html").write_text("<html></html>", encoding="utf-8")
        (generated_dir / "demo-resume.pdf").write_bytes(b"%PDF-1.4")
        self.report_dir.mkdir(parents=True, exist_ok=True)
        (self.report_dir / "demo-resume.md").write_text("# Report\n\nPreview", encoding="utf-8")
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
        with connection_scope() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET html_path = ?, pdf_path = ?, report_path = ?, context_path = ?
                WHERE id = ?
                """,
                (
                    (generated_dir / "demo-resume.html").as_posix(),
                    (generated_dir / "demo-resume.pdf").as_posix(),
                    (self.report_dir / "demo-resume.md").as_posix(),
                    None,
                    created_job["id"],
                ),
            )
            conn.commit()

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
        self.assertIn("다음 액션:", text)
        self.assertIn("연결 공고 다음 액션:", text)
        self.assertIn("Report", text)
        self.assertIn("Resume", text)
        self.assertIn("팔로업 날짜가 지났습니다. 상태와 메모를 갱신하세요.", text)
        self.assertIn("홈에서 바로 일정 조정이 가능합니다.", text)
        self.assertIn("오늘로", text)
        self.assertIn("3일 뒤", text)
        self.assertIn("7일 뒤", text)
        self.assertIn("미설정", text)
        self.assertNotIn("최근 AI 출력", text)

    def test_dashboard_api_includes_recent_artifact_paths(self) -> None:
        created_job = self.client.post(
            "/api/jobs",
            json={
                "company": "Manifest Co",
                "position": "Platform Engineer",
                "status": "검토중",
                "source": "web",
            },
        ).json()
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
        self.report_dir.mkdir(parents=True, exist_ok=True)
        report_path = self.report_dir / "demo-resume.md"
        report_path.write_text("# Report\n\nManifest", encoding="utf-8")
        with connection_scope() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET html_path = ?, pdf_path = ?, context_path = ?, report_path = ?
                WHERE id = ?
                """,
                (
                    (generated_dir / "demo-resume.html").as_posix(),
                    (generated_dir / "demo-resume.pdf").as_posix(),
                    (self.output_dir / "resume-contexts" / "demo-resume.json").as_posix(),
                    report_path.as_posix(),
                    created_job["id"],
                ),
            )
            conn.commit()

        response = self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["totalResumes"], 1)
        self.assertEqual(payload["generatedResumeCount"], 2)
        self.assertEqual(payload["generatedWebResumeCount"], 1)
        self.assertEqual(payload["generatedCliResumeCount"], 1)
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
        self.assertEqual(
            generated_by_url["/output/web-resumes/demo-resume.html"]["job_id"],
            created_job["id"],
        )
        self.assertEqual(
            generated_by_url["/output/web-resumes/demo-resume.html"]["job_detail_url"],
            f"/tracker/{created_job['id']}",
        )
        self.assertEqual(
            generated_by_url["/output/web-resumes/demo-resume.html"]["job_attention_summary"],
            "다음 액션을 잊지 않도록 팔로업 날짜를 지정하세요.",
        )
        self.assertEqual(
            generated_by_url["/output/web-resumes/demo-resume.html"]["job_attention_tags"][0]["label"],
            "팔로업 미설정",
        )
        self.assertEqual(generated_by_url["/output/web-resumes/demo-resume.html"]["provenance"], "manifest")
        self.assertEqual(generated_by_url["/output/cli-resume.html"]["source_label"], "cli")
        self.assertEqual(generated_by_url["/output/cli-resume.html"]["provenance"], "legacy")

    def test_dashboard_api_sorts_manifest_artifacts_by_generated_at_not_manifest_mtime(self) -> None:
        generated_dir = self.output_dir / "web-resumes"
        generated_dir.mkdir(parents=True, exist_ok=True)

        recent_html = generated_dir / "recent-resume.html"
        recent_pdf = generated_dir / "recent-resume.pdf"
        recent_manifest = generated_dir / "recent-resume.manifest.json"
        recent_html.write_text("<html></html>", encoding="utf-8")
        recent_pdf.write_bytes(b"%PDF-1.4")
        recent_manifest.write_text(
            json.dumps(
                {
                    "version": 1,
                    "generated_at": "2026-04-09T03:00:00+00:00",
                    "pipeline": "build_tailored_resume_from_url",
                    "job": {"company": "Recent Co", "title": "Platform Engineer"},
                    "selection": {"selected_role_profile": "Platform"},
                    "focus": {},
                    "paths": {
                        "html_path": recent_html.as_posix(),
                        "pdf_path": recent_pdf.as_posix(),
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        legacy_html = generated_dir / "legacy-resume.html"
        legacy_pdf = generated_dir / "legacy-resume.pdf"
        legacy_manifest = generated_dir / "legacy-resume.manifest.json"
        legacy_html.write_text("<html></html>", encoding="utf-8")
        legacy_pdf.write_bytes(b"%PDF-1.4")
        legacy_manifest.write_text(
            json.dumps(
                {
                    "version": 1,
                    "generated_at": "2024-01-01T00:00:00+00:00",
                    "pipeline": "legacy_backfill",
                    "job": {"company": "Legacy Co", "title": "Platform Engineer"},
                    "selection": {"selected_role_profile": "Platform"},
                    "focus": {},
                    "paths": {
                        "html_path": legacy_html.as_posix(),
                        "pdf_path": legacy_pdf.as_posix(),
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        response = self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        labels = [item["label"] for item in payload["recentGeneratedResumes"]]
        self.assertEqual("recent-resume.html", labels[0])
        self.assertIn("legacy-resume.html", labels)

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

    def test_job_detail_page_shows_source_drift_warning(self) -> None:
        create_response = self.client.post(
            "/api/jobs",
            json={
                "company": "Drift Co",
                "position": "Platform Engineer",
                "status": "검토중",
                "source": "web",
                "url": "https://example.com/jobs/drift-co",
            },
        )
        self.assertEqual(create_response.status_code, 201)
        job_id = create_response.json()["id"]

        with connection_scope() as conn:
            conn.execute("UPDATE jobs SET source = ? WHERE id = ?", ("wanted", job_id))
            conn.commit()

        detail_response = self.client.get(f"/tracker/{job_id}")
        self.assertEqual(detail_response.status_code, 200)
        self.assertIn("web 출처와 markdown tracker 출처가 다릅니다.", detail_response.text)

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
                ("EXPORT_TEST_KEY", "test-secret"),
            )
            conn.commit()

        backup_response = self.client.post("/api/system/db/backup")
        self.assertEqual(backup_response.status_code, 200)
        backup_path = Path(backup_response.json()["backup_path"])
        self.assertTrue(backup_path.exists())
        self.assertEqual(backup_path.parent, self.output_dir / "web-db")

        export_response = self.client.post("/api/system/db/export")
        self.assertEqual(export_response.status_code, 200)
        export_path = Path(export_response.json()["export_path"])
        self.assertTrue(export_path.exists())
        self.assertEqual(export_path.parent, self.output_dir / "web-db")
        exported_payload = json.loads(export_path.read_text(encoding="utf-8"))
        self.assertEqual(exported_payload["tables"]["jobs"][0]["company"], "Backup Co")
        self.assertIn("EXPORT_TEST_KEY", {row["key"] for row in exported_payload["tables"]["settings"]})

        exported_payload["tables"]["settings"].append({"key": "IMPORTED_TEST_KEY", "value": "restored-value"})
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
        import_path = Path(import_response.json()["import_path"])
        self.assertEqual(import_path.parent, self.output_dir / "web-db")
        restored_jobs = self.client.get("/api/jobs").json()
        self.assertEqual(len(restored_jobs), 1)
        self.assertEqual(restored_jobs[0]["company"], "Backup Co")
        with connection_scope() as conn:
            restored = conn.execute("SELECT value FROM settings WHERE key = ?", ("IMPORTED_TEST_KEY",)).fetchone()
        self.assertEqual(restored["value"], "restored-value")

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
        created_job = self.client.post(
            "/api/jobs",
            json={
                "company": "Manifest Platform",
                "position": "Platform Engineer",
                "status": "검토중",
                "source": "web",
                "follow_up": (date.today() - timedelta(days=1)).isoformat(),
            },
        ).json()
        generated_dir = self.output_dir / "web-resumes"
        generated_dir.mkdir(parents=True, exist_ok=True)
        (generated_dir / "web-platform.html").write_text("<html></html>", encoding="utf-8")
        (generated_dir / "web-platform.pdf").write_bytes(b"%PDF-1.4")
        (generated_dir / "web-platform.manifest.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "build_run_id": "br_20260409T023000Z_demo1234",
                    "inventory_key": "web-resumes/web-platform.html",
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
        self.report_dir.mkdir(parents=True, exist_ok=True)
        report_path = self.report_dir / "web-platform.md"
        report_path.write_text("# Report\n\nArtifacts", encoding="utf-8")
        with connection_scope() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET html_path = ?, pdf_path = ?, report_path = ?, context_path = ?
                WHERE id = ?
                """,
                (
                    (generated_dir / "web-platform.html").as_posix(),
                    (generated_dir / "web-platform.pdf").as_posix(),
                    report_path.as_posix(),
                    (context_dir / "web-platform.json").as_posix(),
                    created_job["id"],
                ),
            )
            conn.commit()
        response = self.client.get("/artifacts")
        self.assertEqual(response.status_code, 200)
        self.assertIn("생성된 이력서 산출물", response.text)
        self.assertIn("web-platform.html", response.text)
        self.assertIn("cli-backend.html", response.text)
        self.assertIn("Platform", response.text)
        self.assertIn("br_20260409T023000Z_demo1234", response.text)
        self.assertIn("web-resumes/web-platform.html", response.text)
        self.assertIn("manifest", response.text)
        self.assertIn("연결 공고 다음 액션:", response.text)
        self.assertIn("팔로업 overdue", response.text)
        self.assertIn("팔로업 날짜가 지났습니다. 상태와 메모를 갱신하세요.", response.text)
        self.assertIn("생성된 이력서 산출물", response.text)

        filtered = self.client.get("/artifacts", params={"source": "cli"})
        self.assertEqual(filtered.status_code, 200)
        self.assertIn("cli-backend.html", filtered.text)


if __name__ == "__main__":
    unittest.main()
