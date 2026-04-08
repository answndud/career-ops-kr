from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from career_ops_kr.research import create_company_research_brief, create_company_research_followup


ROOT = Path(__file__).resolve().parents[1]


class CompanyResearchBriefTest(unittest.TestCase):
    def test_create_company_research_brief_uses_default_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            previous_cwd = Path.cwd()
            os.chdir(temp_dir)
            try:
                output_path = create_company_research_brief("Toss")
                self.assertEqual(Path("research") / f"{output_path.name}", output_path)
                self.assertTrue(output_path.name.endswith("-toss.md"))
                self.assertTrue(output_path.exists())
            finally:
                os.chdir(previous_cwd)

    def test_create_company_research_brief_writes_default_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = create_company_research_brief("Toss", out=temp_path / "research.md")

            content = output_path.read_text(encoding="utf-8")
            self.assertEqual(temp_path / "research.md", output_path)
            self.assertIn('company: "Toss"', content)
            self.assertIn("JobPlanet browse: https://www.jobplanet.co.kr/companies", content)
            self.assertIn("Blind browse: https://www.teamblind.com/company/", content)
            self.assertIn("## Search Hints", content)
            self.assertIn('JobPlanet search query: site:jobplanet.co.kr/companies "Toss"', content)
            self.assertIn("https://www.google.com/search?q=site%3Ajobplanet.co.kr%2Fcompanies", content)
            self.assertIn("## Research Checklist", content)
            self.assertIn("## Source Attribution Rules", content)
            self.assertIn("1. 제품과 비즈니스 모델", content)
            self.assertIn("### 1. 제품과 비즈니스 모델", content)

    def test_create_company_research_brief_respects_explicit_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "jd.md"
            report_path = temp_path / "report.md"
            job_path.write_text("# JD", encoding="utf-8")
            report_path.write_text("# Report", encoding="utf-8")

            output_path = create_company_research_brief(
                "Karrot",
                out=temp_path / "karrot.md",
                homepage="https://about.daangn.com/",
                careers_url="https://about.daangn.com/jobs/",
                job_url="https://about.daangn.com/jobs/backend",
                jobplanet_url="https://www.jobplanet.co.kr/companies/123/info",
                blind_url="https://www.teamblind.com/company/Karrot",
                job_path=job_path,
                report_path=report_path,
                extra_sources=["news=https://example.com/news"],
            )

            content = output_path.read_text(encoding="utf-8")
            self.assertIn("https://about.daangn.com/", content)
            self.assertIn("https://about.daangn.com/jobs/backend", content)
            self.assertIn("https://www.jobplanet.co.kr/companies/123/info", content)
            self.assertIn("https://www.teamblind.com/company/Karrot", content)
            self.assertIn(job_path.as_posix(), content)
            self.assertIn(report_path.as_posix(), content)
            self.assertIn("news: https://example.com/news", content)

    def test_create_company_research_brief_rejects_blank_company_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                create_company_research_brief("   ", out=Path(temp_dir) / "research.md")

    def test_create_company_research_brief_validates_extra_source_format(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                create_company_research_brief(
                    "Blind",
                    out=Path(temp_dir) / "blind.md",
                    extra_sources=["not-a-valid-source"],
                )

    def test_create_company_research_brief_requires_existing_job_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                create_company_research_brief(
                    "Blind",
                    out=Path(temp_dir) / "blind.md",
                    job_path=Path(temp_dir) / "missing-job.md",
                )

    def test_create_company_research_brief_requires_existing_report_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                create_company_research_brief(
                    "Blind",
                    out=Path(temp_dir) / "blind.md",
                    report_path=Path(temp_dir) / "missing-report.md",
                )

    def test_create_company_research_brief_uses_prompt_items_for_checklist_and_notes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            prompt_path = temp_path / "prompt.md"
            prompt_path.write_text(
                "# Prompt\n\n1. 팀 구조\n2. 최근 제품 변화\n3. 인터뷰 질문 5개\n",
                encoding="utf-8",
            )

            output_path = create_company_research_brief(
                "Karrot",
                out=temp_path / "karrot.md",
                prompt_path=prompt_path,
            )

            content = output_path.read_text(encoding="utf-8")
            self.assertIn("prompt_path: " + f"\"{prompt_path.as_posix()}\"", content)
            self.assertIn("1. 팀 구조", content)
            self.assertIn("2. 최근 제품 변화", content)
            self.assertIn("3. 인터뷰 질문 5개", content)
            self.assertIn("### 1. 팀 구조", content)
            self.assertIn("### 2. 최근 제품 변화", content)
            self.assertIn("### 3. 인터뷰 질문 5개", content)

    def test_create_company_research_brief_falls_back_when_prompt_has_no_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            prompt_path = temp_path / "prompt.md"
            prompt_path.write_text("# Prompt\n\nNo numbered items here.\n", encoding="utf-8")

            output_path = create_company_research_brief(
                "Karrot",
                out=temp_path / "karrot.md",
                prompt_path=prompt_path,
            )

            content = output_path.read_text(encoding="utf-8")
            self.assertIn("1. 제품과 비즈니스 모델", content)
            self.assertIn("### 5. 면접에서 물어볼 질문 5개", content)

    def test_create_company_research_brief_requires_overwrite_for_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "existing.md"
            output_path.write_text("old", encoding="utf-8")

            with self.assertRaises(ValueError):
                create_company_research_brief("Blind", out=output_path)

            replaced_path = create_company_research_brief("Blind", out=output_path, overwrite=True)
            self.assertEqual(output_path, replaced_path)
            self.assertNotEqual("old", output_path.read_text(encoding="utf-8"))

    def test_create_company_research_followup_summary_reuses_brief_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            prompt_path = temp_path / "prompt.md"
            prompt_path.write_text(
                "# Prompt\n\n1. 제품 요약\n2. 기술 조직 신호\n3. 면접 질문\n",
                encoding="utf-8",
            )
            brief_path = create_company_research_brief(
                "Toss",
                out=temp_path / "toss-brief.md",
                homepage="https://toss.im",
                careers_url="https://toss.im/career/jobs",
                jobplanet_url="https://www.jobplanet.co.kr/companies/123/info",
                blind_url="https://www.teamblind.com/company/Toss",
                prompt_path=prompt_path,
            )

            followup_path = create_company_research_followup(
                brief_path,
                mode="summary",
                out=temp_path / "toss-summary.md",
            )

            content = followup_path.read_text(encoding="utf-8")
            self.assertIn('mode: "summary"', content)
            self.assertIn(f'source_brief: "{brief_path.as_posix()}"', content)
            self.assertIn("# Toss Research Summary", content)
            self.assertIn("- Homepage: https://toss.im", content)
            self.assertIn("- JobPlanet page: https://www.jobplanet.co.kr/companies/123/info", content)
            self.assertIn("- 제품 요약", content)
            self.assertIn("### 회사 한 줄 요약", content)
            self.assertIn("### 다음 액션", content)

    def test_create_company_research_followup_outreach_writes_outreach_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            brief_path = create_company_research_brief("Karrot", out=temp_path / "karrot-brief.md")

            followup_path = create_company_research_followup(
                brief_path,
                mode="outreach",
                out=temp_path / "karrot-outreach.md",
            )

            content = followup_path.read_text(encoding="utf-8")
            self.assertIn('mode: "outreach"', content)
            self.assertIn("# Karrot Outreach Draft", content)
            self.assertIn("### Recruiter Outreach", content)
            self.assertIn("### Hiring Manager Note", content)
            self.assertIn("### Referral Request", content)
            self.assertIn("tracker나 pipeline 상태를 이 문서에서 변경하지 않는다.", content)

    def test_create_company_research_followup_validates_mode_and_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            brief_path = create_company_research_brief("Blind", out=temp_path / "blind-brief.md")
            followup_path = temp_path / "blind-summary.md"
            followup_path.write_text("old", encoding="utf-8")

            with self.assertRaises(ValueError):
                create_company_research_followup(brief_path, mode="invalid", out=temp_path / "bad.md")

            with self.assertRaises(ValueError):
                create_company_research_followup(brief_path, out=followup_path)

            replaced_path = create_company_research_followup(
                brief_path,
                out=followup_path,
                overwrite=True,
            )
            self.assertEqual(followup_path, replaced_path)
            self.assertNotEqual("old", followup_path.read_text(encoding="utf-8"))

    def test_create_company_research_followup_requires_existing_brief(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                create_company_research_followup(Path(temp_dir) / "missing-brief.md")


if __name__ == "__main__":
    unittest.main()
