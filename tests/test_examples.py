from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from career_ops_kr.commands.resume import render_resume_html


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = ROOT / "examples"
TEMPLATES_DIR = ROOT / "templates"


class ResumeExampleContextsTest(unittest.TestCase):
    def test_role_specific_example_contexts_have_required_fields(self) -> None:
        example_paths = sorted(EXAMPLES_DIR.glob("resume-context*.example.json"))
        self.assertGreaterEqual(len(example_paths), 9)

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

        for path in example_paths:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(required_keys.issubset(data.keys()), msg=path.as_posix())
            self.assertIsInstance(data["skills"], list, msg=path.as_posix())
            self.assertIsInstance(data["experience"], list, msg=path.as_posix())
            self.assertIsInstance(data["projects"], list, msg=path.as_posix())
            self.assertIsInstance(data["education"], list, msg=path.as_posix())

    def test_role_specific_example_contexts_render_with_resume_templates(self) -> None:
        example_paths = sorted(EXAMPLES_DIR.glob("resume-context*.example.json"))
        template_paths = [
            TEMPLATES_DIR / "resume-en.html",
            TEMPLATES_DIR / "resume-ko.html",
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            for example_path in example_paths:
                for template_path in template_paths:
                    output_path = temp_path / f"{example_path.stem}-{template_path.stem}.html"
                    render_resume_html(template_path, example_path, output_path)
                    rendered = output_path.read_text(encoding="utf-8")
                    data = json.loads(example_path.read_text(encoding="utf-8"))
                    self.assertIn(data["headline"], rendered)
                    self.assertIn(data["name"], rendered)

    def test_korean_resume_template_renders_korean_sections_and_contact(self) -> None:
        example_path = EXAMPLES_DIR / "resume-context.platform.ko.example.json"
        template_path = TEMPLATES_DIR / "resume-ko.html"

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "resume-ko.html"
            render_resume_html(template_path, example_path, output_path)
            rendered = output_path.read_text(encoding="utf-8")
            data = json.loads(example_path.read_text(encoding="utf-8"))

            self.assertIn('lang="ko"', rendered)
            self.assertIn(data["contactLine"], rendered)
            self.assertIn("요약", rendered)
            self.assertIn("기술 스택", rendered)
            self.assertIn("경력", rendered)
            self.assertIn("프로젝트", rendered)
            self.assertIn("학력", rendered)
            self.assertIn(data["experience"][0]["bullets"][0], rendered)

    def test_english_resume_template_renders_english_sections_and_contact(self) -> None:
        example_path = EXAMPLES_DIR / "resume-context.platform.example.json"
        template_path = TEMPLATES_DIR / "resume-en.html"

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "resume-en.html"
            render_resume_html(template_path, example_path, output_path)
            rendered = output_path.read_text(encoding="utf-8")
            data = json.loads(example_path.read_text(encoding="utf-8"))

            self.assertIn('lang="en"', rendered)
            self.assertIn(data["contactLine"], rendered)
            self.assertIn("Summary", rendered)
            self.assertIn("Skills", rendered)
            self.assertIn("Experience", rendered)
            self.assertIn("Projects", rendered)
            self.assertIn("Education", rendered)
            self.assertIn(data["experience"][0]["bullets"][0], rendered)


if __name__ == "__main__":
    unittest.main()
