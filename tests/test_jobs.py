from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from career_ops_kr.jobs import fetch_job_to_markdown


class FetchJobValidationTest(unittest.TestCase):
    @patch("career_ops_kr.jobs.httpx.get")
    def test_fetch_job_uses_jobposting_structured_data_when_body_is_empty(self, mock_get) -> None:
        response = httpx.Response(
            200,
            request=httpx.Request("GET", "https://career.rememberapp.co.kr/job/posting/293599"),
            text=(
                "<html><head>"
                "<title>Fallback Title</title>"
                '<script type="application/ld+json">'
                "{"
                '"@context":"http://schema.org",'
                '"@type":"JobPosting",'
                '"title":"[어피닛] Dev-ops Engineer (Data/ML Platform)",'
                '"description":"• AWS 인프라 설계 및 운영\\n• Kubernetes(EKS) 기반 Data & ML 플랫폼 구축",'
                '"qualifications":"• Terraform 경험\\n• GitHub Actions 또는 ArgoCD 경험",'
                '"experienceRequirements":"경력 6년~12년 차",'
                '"hiringOrganization":{"@type":"Organization","name":"(주)어피닛"}'
                "}"
                "</script>"
                "</head><body><main></main></body></html>"
            ),
        )
        mock_get.return_value = response

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "job.md"
            saved_path = fetch_job_to_markdown(
                "https://career.rememberapp.co.kr/job/posting/293599",
                out=output_path,
                source="remember",
            )

            self.assertEqual(output_path, saved_path)
            content = output_path.read_text(encoding="utf-8")
            self.assertIn('title: "[어피닛] Dev-ops Engineer (Data/ML Platform)"', content)
            self.assertIn('company: "(주)어피닛"', content)
            self.assertIn("Description", content)
            self.assertIn("Qualifications", content)
            self.assertIn("Terraform", content)
            self.assertIn("Kubernetes(EKS)", content)

    @patch("career_ops_kr.jobs.httpx.get")
    def test_fetch_job_rejects_non_detail_indeed_url(self, mock_get) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "job.md"
            with self.assertRaisesRegex(
                ValueError,
                "Indeed intake supports manual detail URLs only",
            ):
                fetch_job_to_markdown(
                    "https://www.indeed.com/jobs?q=platform+engineer&l=Remote",
                    out=output_path,
                )

        mock_get.assert_not_called()

    @patch("career_ops_kr.jobs.httpx.get")
    def test_fetch_job_rejects_rocketpunch_gate_content(self, mock_get) -> None:
        response = httpx.Response(
            200,
            request=httpx.Request("GET", "https://www.rocketpunch.com/jobs/154190"),
            text=(
                "<html><head><title>RocketPunch Job</title></head><body>"
                "로그인 후 검색 가능 "
                "공개된 데이터도 크롤링 등 기술적 장치를 이용해 허가 없이 수집 "
                "개인정보 데이터를 포함하여 각 정보주체의 동의 없이 데이터를 무단으로 수집하는 행위를 금지"
                "</body></html>"
            ),
        )
        mock_get.return_value = response

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "job.md"
            with self.assertRaisesRegex(
                ValueError,
                "RocketPunch returned login or anti-crawl gate content",
            ):
                fetch_job_to_markdown(
                    "https://www.rocketpunch.com/jobs/154190",
                    out=output_path,
                    source="rocketpunch",
                )

    @patch("career_ops_kr.jobs.httpx.get")
    def test_fetch_job_rejects_rocketpunch_waf_marker_html(self, mock_get) -> None:
        response = httpx.Response(
            200,
            request=httpx.Request("GET", "https://www.rocketpunch.com/jobs/154190"),
            text=(
                "<html><head><title>RocketPunch Job</title>"
                "<script>window.awsWafCookieDomainList=[];window.gokuProps={}</script></head><body>"
                "This response looks long enough to avoid the short-text fallback, "
                "but it should still be rejected because the HTML contains AWS WAF challenge markers "
                "instead of a usable job description for manual intake."
                "</body></html>"
            ),
        )
        mock_get.return_value = response

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "job.md"
            with self.assertRaisesRegex(
                ValueError,
                "RocketPunch returned login or anti-crawl gate content",
            ):
                fetch_job_to_markdown(
                    "https://www.rocketpunch.com/jobs/154190",
                    out=output_path,
                    source="rocketpunch",
                )

    @patch("career_ops_kr.jobs.httpx.get")
    def test_fetch_job_rejects_rocketpunch_listing_url(self, mock_get) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "job.md"
            with self.assertRaisesRegex(
                ValueError,
                "RocketPunch intake supports manual detail URLs only",
            ):
                fetch_job_to_markdown(
                    "https://www.rocketpunch.com/jobs",
                    out=output_path,
                    source="rocketpunch",
                )

        mock_get.assert_not_called()

    @patch("career_ops_kr.jobs.httpx.get")
    def test_fetch_job_rejects_rocketpunch_company_recruit_url(self, mock_get) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "job.md"
            with self.assertRaisesRegex(
                ValueError,
                "RocketPunch intake supports manual detail URLs only",
            ):
                fetch_job_to_markdown(
                    "https://www.rocketpunch.com/companies/example/recruit",
                    out=output_path,
                    source="rocketpunch",
                )

        mock_get.assert_not_called()

    @patch("career_ops_kr.jobs.httpx.get")
    def test_fetch_job_rejects_blank_rocketpunch_detail_response(self, mock_get) -> None:
        response = httpx.Response(
            200,
            request=httpx.Request("GET", "https://www.rocketpunch.com/jobs/154190"),
            text="<html><head><title>154190</title></head><body></body></html>",
        )
        mock_get.return_value = response

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "job.md"
            with self.assertRaisesRegex(
                ValueError,
                "RocketPunch returned login or anti-crawl gate content",
            ):
                fetch_job_to_markdown(
                    "https://www.rocketpunch.com/jobs/154190",
                    out=output_path,
                    source="rocketpunch",
                )

    @patch("career_ops_kr.jobs.httpx.get")
    def test_fetch_job_accepts_rocketpunch_slug_detail_url_and_writes_canonical_url(self, mock_get) -> None:
        response = httpx.Response(
            200,
            request=httpx.Request("GET", "https://www.rocketpunch.com/jobs/154190"),
            text=(
                "<html><head><title>Platform Engineer</title></head><body>"
                "Platform engineering role focused on backend systems, reliability, observability, "
                "developer tooling, infrastructure automation, and incident response for internal teams."
                "</body></html>"
            ),
        )
        mock_get.return_value = response

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "job.md"
            saved_path = fetch_job_to_markdown(
                "https://www.rocketpunch.com/en-US/jobs/154190/platform-engineer?ref=share",
                out=output_path,
                source="rocketpunch",
            )

            mock_get.assert_called_once()
            requested_url = mock_get.call_args.kwargs["url"] if "url" in mock_get.call_args.kwargs else mock_get.call_args.args[0]
            self.assertEqual("https://www.rocketpunch.com/jobs/154190", requested_url)
            self.assertEqual(output_path, saved_path)
            content = output_path.read_text(encoding="utf-8")
            self.assertIn('url: "https://www.rocketpunch.com/jobs/154190"', content)



if __name__ == "__main__":
    unittest.main()
