from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from career_ops_kr.commands.resume import (
    apply_resume_tailoring_packet,
    create_resume_tailoring_packet,
    render_resume_html,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = ROOT / "tests" / "fixtures"
EXAMPLES_DIR = ROOT / "examples"
TEMPLATES_DIR = ROOT / "templates"
SCORECARD = ROOT / "config" / "scorecard.kr.yml"


class ResumePipelineChainTest(unittest.TestCase):
    def test_prepare_apply_render_chain_from_saved_fixture(self) -> None:
        job_path = FIXTURES_DIR / "remember_platform_job.md"
        report_path = FIXTURES_DIR / "remember_platform_report.md"
        base_context_path = EXAMPLES_DIR / "resume-context.platform.ko.example.json"
        template_path = TEMPLATES_DIR / "resume-ko.html"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            tailoring_path = temp_path / "tailoring.json"
            tailored_context_path = temp_path / "context.json"
            output_html_path = temp_path / "resume.html"

            tailoring = create_resume_tailoring_packet(
                job_path,
                report_path,
                out=tailoring_path,
                base_context_path=base_context_path,
                scorecard_path=SCORECARD,
            )
            context = apply_resume_tailoring_packet(
                tailoring.output_path,
                base_context_path,
                out=tailored_context_path,
            )
            render_resume_html(template_path, context.output_path, output_html_path)

            packet = json.loads(tailoring_path.read_text(encoding="utf-8"))
            tailored_context = json.loads(tailored_context_path.read_text(encoding="utf-8"))
            rendered = output_html_path.read_text(encoding="utf-8")

            self.assertEqual("Platform", packet["selection"]["selected_role_profile"])
            self.assertEqual("Platform Engineer", packet["selection"]["selected_target_role"])
            self.assertIn("kubernetes", [item.lower() for item in packet["tailoring"]["skills_to_emphasize"]])
            self.assertEqual("Platform Engineer", tailored_context["headline"])
            self.assertEqual("Platform", tailored_context["tailoringGuidance"]["selection"]["selected_role_profile"])
            self.assertIn("요약", rendered)
            self.assertIn("기술 스택", rendered)
            self.assertIn("Platform Engineer", rendered)
            self.assertIn("홍길동", rendered)


if __name__ == "__main__":
    unittest.main()
