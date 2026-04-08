from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from career_ops_kr.portals import canonicalize_job_url, discover_job_urls, infer_source_from_url, merge_pending_urls


class PortalCanonicalizationTest(unittest.TestCase):
    def test_canonicalize_job_url_normalizes_supported_portals_and_indeed(self) -> None:
        self.assertEqual(
            "https://www.wanted.co.kr/wd/12345",
            canonicalize_job_url("https://recruit.wanted.co.kr/wd/12345?source=web"),
        )
        self.assertEqual(
            "https://career.rememberapp.co.kr/job/posting/24786",
            canonicalize_job_url(
                "https://career.rememberapp.co.kr/job/postings?postingId=24786&isInvitation=false"
            ),
        )
        self.assertEqual(
            "https://kr.indeed.com/viewjob?jk=abc123",
            canonicalize_job_url(
                "https://kr.indeed.com/m/viewjob?jk=abc123&from=shareddesktop_copy&tk=1"
            ),
        )
        self.assertEqual(
            "https://www.indeed.com/viewjob?jk=def456",
            canonicalize_job_url("https://m.indeed.com/viewjob?vjk=def456&from=app-tracker"),
        )
        self.assertEqual(
            "https://www.rocketpunch.com/jobs/154190",
            canonicalize_job_url("https://www.rocketpunch.com/en-US/jobs/154190?ref=share"),
        )
        self.assertEqual(
            "https://www.rocketpunch.com/jobs/154190",
            canonicalize_job_url("https://www.rocketpunch.com/jobs/154190/platform-engineer?ref=share"),
        )
        self.assertEqual(
            "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=123456",
            canonicalize_job_url(
                "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=123456&view_type=list&utm_source=share"
            ),
        )

    def test_infer_source_from_url_detects_indeed_detail_urls(self) -> None:
        self.assertEqual("indeed", infer_source_from_url("https://www.indeed.com/viewjob?jk=abc123"))
        self.assertEqual("indeed", infer_source_from_url("https://kr.indeed.com/m/viewjob?jk=abc123"))
        self.assertEqual("rocketpunch", infer_source_from_url("https://rocketpunch.com/en-US/jobs/154190"))
        self.assertEqual(
            "saramin",
            infer_source_from_url("https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=123456&view_type=list"),
        )
        self.assertEqual(
            "rocketpunch",
            infer_source_from_url("https://www.rocketpunch.com/jobs/154190/platform-engineer"),
        )

    def test_merge_pending_urls_deduplicates_by_canonical_url(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pipeline_path = Path(temp_dir) / "pipeline.md"
            added = merge_pending_urls(
                pipeline_path,
                [
                    "https://www.indeed.com/viewjob?jk=abc123",
                    "https://www.indeed.com/viewjob?jk=abc123&from=shareddesktop_copy",
                    "https://recruit.wanted.co.kr/wd/12345?campaign=foo",
                    "https://www.wanted.co.kr/wd/12345",
                ],
            )

            content = pipeline_path.read_text(encoding="utf-8")

            self.assertEqual(2, added)
            self.assertIn("- [ ] https://www.indeed.com/viewjob?jk=abc123", content)
            self.assertIn("- [ ] https://www.wanted.co.kr/wd/12345", content)
            self.assertNotIn("shareddesktop_copy", content)
            self.assertNotIn("recruit.wanted.co.kr", content)

    @patch.dict(os.environ, {}, clear=False)
    def test_discover_job_urls_requires_saramin_access_key(self) -> None:
        with patch.dict(os.environ, {"SARAMIN_ACCESS_KEY": ""}, clear=False):
            with self.assertRaisesRegex(ValueError, "SARAMIN_ACCESS_KEY"):
                discover_job_urls("saramin", limit=5)

    @patch("career_ops_kr.portals.httpx.Client")
    def test_discover_job_urls_supports_saramin_api(self, mock_client_cls) -> None:
        client = mock_client_cls.return_value.__enter__.return_value
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "jobs": {
                "job": [
                    {
                        "url": "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=123456&view_type=list"
                    },
                    {
                        "url": "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=654321&utm_source=share"
                    },
                ]
            }
        }
        client.get.return_value = response

        with patch.dict(os.environ, {"SARAMIN_ACCESS_KEY": "test-key"}, clear=False):
            urls = discover_job_urls("saramin", limit=2)

        self.assertEqual(
            [
                "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=123456",
                "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=654321",
            ],
            urls,
        )
        params = client.get.call_args.kwargs["params"]
        self.assertEqual("test-key", params["access-key"])
        self.assertEqual("2", params["job_mid_cd"])
        self.assertEqual("directhire", params["sr"])


if __name__ == "__main__":
    unittest.main()
