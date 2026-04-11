from __future__ import annotations

import os
import socket
import tempfile
import threading
import time
import unittest
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import uvicorn
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from career_ops_kr.web import app as web_app
from career_ops_kr.web import resume_tools


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class WebAppE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        if os.getenv("CAREER_OPS_RUN_BROWSER_E2E", "").strip().lower() not in {"1", "true", "yes", "on"}:
            self.skipTest("Browser E2E is optional. Set CAREER_OPS_RUN_BROWSER_E2E=1 to run it.")

        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

        tmp_root = Path(self.tmpdir.name)
        self.db_path = tmp_root / "career-ops-web.db"
        self.upload_dir = tmp_root / "web-uploads"
        self.output_dir = tmp_root / "output"
        self.tracker_path = tmp_root / "applications.md"
        self.jd_dir = tmp_root / "jds"
        self.report_dir = tmp_root / "reports"

        self.patches = [
            patch.dict(os.environ, {"CAREER_OPS_WEB_DB": self.db_path.as_posix()}, clear=False),
            patch.object(resume_tools, "UPLOAD_DIR", self.upload_dir),
            patch.object(web_app, "OUTPUT_DIR", self.output_dir),
            patch.object(web_app, "WEB_RESUME_OUTPUT_DIR", self.output_dir / "web-resumes"),
            patch.object(web_app, "LIVE_SMOKE_REPORT_DIR", self.output_dir / "live-smoke"),
            patch.object(web_app, "TRACKER_PATH", self.tracker_path),
            patch.object(web_app, "JD_DIR", self.jd_dir),
            patch.object(web_app, "REPORT_DIR", self.report_dir),
            patch.object(web_app, "search_jobs", side_effect=self._fake_search_jobs),
            patch.object(web_app, "run_build_tailored_resume_from_url", side_effect=self._fake_build_from_url),
        ]
        for active_patch in self.patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)

        self.port = _free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.server = uvicorn.Server(
            uvicorn.Config(web_app.create_app(), host="127.0.0.1", port=self.port, log_level="error")
        )
        self.server.install_signal_handlers = lambda: None
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop_server)
        self._wait_until_ready()

    def _wait_until_ready(self) -> None:
        deadline = time.time() + 10.0
        while time.time() < deadline:
            try:
                response = httpx.get(self.base_url, timeout=0.5)
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        self.fail("Timed out waiting for the web server to start.")

    def _stop_server(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)

    def _fake_build_from_url(
        self,
        url: str,
        base_context_path: Path,
        template_path: Path,
        *,
        source: str | None,
        job_out: Path,
        report_out: Path,
        tracker_out: Path | None,
        html_out: Path,
        tailoring_out: Path,
        tailored_context_out: Path,
        pdf_out: Path | None,
        profile_path: Path,
        scorecard_path: Path,
        overwrite: bool,
        insecure: bool,
        pdf_format: str,
    ) -> SimpleNamespace:
        for path in (job_out, report_out, tailoring_out, tailored_context_out, html_out):
            path.parent.mkdir(parents=True, exist_ok=True)
        job_out.write_text(f"# JD\n\n{url}", encoding="utf-8")
        report_out.write_text("# Report\n\nStrong fit", encoding="utf-8")
        tailoring_out.write_text('{"focus":"platform"}', encoding="utf-8")
        tailored_context_out.write_text('{"headline":"Platform Engineer"}', encoding="utf-8")
        html_out.write_text("<html><body>Resume</body></html>", encoding="utf-8")
        manifest_path = html_out.with_suffix(".manifest.json")
        manifest_path.write_text(
            '{"version":1,"generated_at":"2026-04-09T00:00:00+00:00","pipeline":"build_tailored_resume_from_url","job":{"company":"E2E Co","title":"Platform Engineer","url":"https://example.com/jobs/e2e","source":"web"},"selection":{"selected_role_profile":"Platform"},"focus":{},"paths":{"job_path":"'
            + job_out.as_posix()
            + '","report_path":"'
            + report_out.as_posix()
            + '","tailoring_path":"'
            + tailoring_out.as_posix()
            + '","context_path":"'
            + tailored_context_out.as_posix()
            + '","html_path":"'
            + html_out.as_posix()
            + '","pdf_path":'
            + ('"' + pdf_out.as_posix() + '"' if pdf_out is not None else "null")
            + ',"base_context_path":"'
            + base_context_path.as_posix()
            + '","template_path":"'
            + template_path.as_posix()
            + '","profile_path":"'
            + profile_path.as_posix()
            + '","scorecard_path":"'
            + scorecard_path.as_posix()
            + '"}}\n',
            encoding="utf-8",
        )
        if pdf_out is not None:
            pdf_out.parent.mkdir(parents=True, exist_ok=True)
            pdf_out.write_bytes(b"%PDF-1.4")
        return SimpleNamespace(
            job_path=job_out,
            report_path=report_out,
            tracker_path=tracker_out,
            tailoring_path=tailoring_out,
            tailored_context_path=tailored_context_out,
            html_path=html_out,
            pdf_path=pdf_out,
            manifest_path=manifest_path,
        )

    def _fake_search_jobs(self, query: str) -> dict[str, object]:
        normalized = query.strip().lower()
        title = "Platform Engineer" if "platform" in normalized else "Backend Engineer"
        company = "Search Co" if "platform" in normalized else "Preset Co"
        row_id = "wanted-platform-1" if "platform" in normalized else "wanted-backend-1"
        return {
            "results": [
                {
                    "id": row_id,
                    "title": title,
                    "company": company,
                    "location": "Seoul",
                    "source": "원티드",
                    "url": f"https://www.wanted.co.kr/wd/{54321 if 'platform' in normalized else 12345}",
                    "type": "-",
                    "experience": "-",
                    "salary": "-",
                    "deadline": "-",
                    "description": f"{title} role for {company}",
                }
            ],
            "count": 1,
            "translated_query": None,
            "provider_statuses": [],
            "provider_summary": None,
            "degraded": False,
            "sources": {"전체": 1, "원티드": 1},
        }

    def test_home_to_tracker_to_detail_flow(self) -> None:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=True)
            except PlaywrightError as exc:
                self.skipTest(f"Chromium is not available for Playwright: {exc}")
            try:
                page = browser.new_page()
                page.goto(self.base_url, wait_until="networkidle")
                self.assertIn("처음 쓰는 사람도 바로 시작할 수 있는 구직 대시보드", page.content())

                resume_file = Path(self.tmpdir.name) / "resume.txt"
                resume_file.write_text("Python\nFastAPI\nPostgreSQL", encoding="utf-8")
                page.locator("nav").get_by_role("link", name="이력서", exact=True).click()
                page.wait_for_url(f"{self.base_url}/resume")
                page.set_input_files("#resume-file", resume_file.as_posix())
                page.locator('#upload-form button[type="submit"]').click()
                page.locator("#upload-status").get_by_text("업로드 완료").wait_for()

                page.locator("nav").get_by_role("link", name="트래커", exact=True).click()
                page.wait_for_url(f"{self.base_url}/tracker")

                page.locator('#tracker-create-form input[name="company"]').fill("E2E Co")
                page.locator('#tracker-create-form input[name="position"]').fill("Platform Engineer")
                page.locator('#tracker-create-form input[name="source"]').fill("web")
                page.locator('#tracker-create-form input[name="location"]').fill("Seoul")
                page.locator('#tracker-create-form input[name="url"]').fill("https://example.com/jobs/e2e")

                page.locator('#tracker-create-form button[type="submit"]').click()
                page.locator("#tracker-action-output").get_by_text("추가 완료").wait_for()

                detail_link = page.get_by_role("link", name="상세")
                detail_link.wait_for()
                page.locator("tbody").get_by_text("E2E Co").wait_for()

                detail_link.click()
                page.wait_for_url(f"{self.base_url}/tracker/1")
                page.locator("h1").get_by_text("E2E Co").wait_for()
                self.assertIn("Platform Engineer", page.content())
                self.assertIn("저장된 산출물", page.content())
                self.assertIn("이 공고에서 바로 맞춤 이력서 생성", page.content())

                page.locator("#detail-build-preset").select_option("platform:ko")
                page.get_by_role("button", name="HTML/PDF 생성", exact=True).click()
                page.locator("#detail-build-output").get_by_text("생성 완료").wait_for()
                self.assertIn("HTML 열기", page.locator("#detail-build-output").inner_text())

                generated_files = list((self.output_dir / "web-resumes").glob("*.html"))
                self.assertEqual(len(generated_files), 1)

                page.locator("nav").get_by_role("link", name="홈", exact=True).click()
                page.wait_for_url(self.base_url + "/")
                self.assertIn(generated_files[0].name, page.content())
            finally:
                browser.close()

    def test_search_preset_artifact_filter_and_follow_up_flow(self) -> None:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=True)
            except PlaywrightError as exc:
                self.skipTest(f"Chromium is not available for Playwright: {exc}")
            try:
                page = browser.new_page()
                page.goto(f"{self.base_url}/search", wait_until="networkidle")

                page.locator('input[name="q"]').fill("platform engineer")
                page.get_by_role("button", name="검색", exact=True).click()
                page.wait_for_load_state("networkidle")
                page.locator("tbody").get_by_text("Search Co").wait_for()

                page.locator("#search-preset-name").fill("플랫폼 기본")
                page.get_by_role("button", name="현재 검색어를 기본으로 저장", exact=True).click()
                page.locator("#search-preset-output").get_by_text("기본 검색 preset을 저장했습니다").wait_for()
                self.assertIn("플랫폼 기본", page.locator("#search-preset-list").inner_text())
                self.assertIn("기본 preset", page.locator("#search-preset-list").inner_text())

                page.goto(f"{self.base_url}/search", wait_until="networkidle")
                page.get_by_text("기본 preset으로 검색 중").wait_for()
                page.locator("tbody").get_by_text("Search Co").wait_for()

                result_row = page.locator("tbody tr").filter(has=page.get_by_text("Search Co"))
                result_row.get_by_role("button", name="저장", exact=True).click()
                page.locator("#search-save-output").get_by_text("새 공고를 저장했습니다").wait_for()

                result_row.get_by_role("button", name="이력서 생성", exact=True).click()
                page.locator("#search-build-output").get_by_text("생성 완료").wait_for()

                generated_files = list((self.output_dir / "web-resumes").glob("*.html"))
                self.assertEqual(len(generated_files), 1)
                generated_name = generated_files[0].name

                page.goto(f"{self.base_url}/artifacts", wait_until="networkidle")
                page.locator('select[name="attention"]').select_option("follow-up-missing")
                page.get_by_role("button", name="보기", exact=True).click()
                page.wait_for_load_state("networkidle")
                self.assertIn(generated_name, page.content())
                self.assertIn("팔로업 미설정", page.content())

                page.goto(f"{self.base_url}/tracker", wait_until="networkidle")
                page.get_by_role("button", name="미설정 3일 준비", exact=True).click()
                page.locator("#tracker-action-output").get_by_text("미리 채웠습니다").wait_for()
                expected_follow_up = (date.today() + timedelta(days=3)).isoformat()
                self.assertEqual(page.locator("#bulk-follow-up").input_value(), expected_follow_up)
                self.assertEqual(page.locator(".job-select:checked").count(), 1)

                page.get_by_role("button", name="선택 항목 적용", exact=True).click()
                page.locator("#tracker-action-output").get_by_text("1개 항목에 follow_up 변경을 적용했습니다").wait_for()

                page.goto(f"{self.base_url}/follow-ups", wait_until="networkidle")
                page.get_by_text("Search Co · Platform Engineer").wait_for()
                page.get_by_role("button", name="오늘로", exact=True).click()
                page.wait_for_timeout(600)
                self.assertIn(date.today().isoformat(), page.content())
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
