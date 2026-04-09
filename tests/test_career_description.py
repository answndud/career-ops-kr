from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from career_ops_kr.commands.resume import render_resume_html


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT / "templates"
EXAMPLES_DIR = ROOT / "examples"


class CareerDescriptionTemplateTest(unittest.TestCase):
    def test_career_description_examples_have_resume_compatible_schema(self) -> None:
        example_paths = sorted(EXAMPLES_DIR.glob("career-description-context*.example.json"))
        expected_names = {
            "career-description-context.backend.example.json",
            "career-description-context.backend.ko.example.json",
            "career-description-context.data-ai.example.json",
            "career-description-context.data-ai.ko.example.json",
            "career-description-context.data-platform.example.json",
            "career-description-context.data-platform.ko.example.json",
            "career-description-context.platform.example.json",
            "career-description-context.platform.ko.example.json",
        }
        self.assertEqual({path.name for path in example_paths}, expected_names)
        required_keys = {
            "name",
            "headline",
            "contactLine",
            "summary",
            "skills",
            "experience",
            "projects",
            "education",
        }
        for example_path in example_paths:
            data = json.loads(example_path.read_text(encoding="utf-8"))
            self.assertTrue(required_keys.issubset(data.keys()), msg=example_path.as_posix())
            self.assertIsInstance(data["skills"], list, msg=example_path.as_posix())
            self.assertIsInstance(data["experience"], list, msg=example_path.as_posix())
            self.assertIsInstance(data["projects"], list, msg=example_path.as_posix())
            self.assertIsInstance(data["education"], list, msg=example_path.as_posix())

    def test_career_description_template_renders_expected_sections(self) -> None:
        example_paths = sorted(EXAMPLES_DIR.glob("career-description-context*.example.json"))

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            for example_path in example_paths:
                output_path = temp_path / f"{example_path.stem}.html"
                template_path = (
                    TEMPLATES_DIR / "career-description-ko.html"
                    if ".ko." in example_path.name
                    else TEMPLATES_DIR / "career-description-en.html"
                )
                render_resume_html(template_path, example_path, output_path)
                rendered = output_path.read_text(encoding="utf-8")
                data = json.loads(example_path.read_text(encoding="utf-8"))

                if ".ko." in example_path.name:
                    self.assertIn('lang="ko"', rendered)
                    self.assertIn("핵심 요약", rendered)
                    self.assertIn("기술 역량", rendered)
                    self.assertIn("주요 경력", rendered)
                    self.assertIn("프로젝트 및 부가 경험", rendered)
                    self.assertIn("학력", rendered)
                else:
                    self.assertIn('lang="en"', rendered)
                    self.assertIn("Summary", rendered)
                    self.assertIn("Core Skills", rendered)
                    self.assertIn("Experience", rendered)
                    self.assertIn("Selected Projects", rendered)
                    self.assertIn("Education", rendered)
                self.assertIn("Career Description", rendered)
                self.assertIn(data["name"], rendered)
                self.assertIn(data["contactLine"], rendered)
                self.assertIn(data["experience"][0]["bullets"][0], rendered)


if __name__ == "__main__":
    unittest.main()
