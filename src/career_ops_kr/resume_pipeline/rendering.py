from __future__ import annotations

import asyncio
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.async_api import async_playwright

from career_ops_kr.utils import ensure_dir


def render_resume_html(template_path: Path, context_path: Path, output_path: Path) -> Path:
    context = json.loads(context_path.read_text(encoding="utf-8"))
    environment = Environment(
        loader=FileSystemLoader(template_path.parent),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = environment.get_template(template_path.name)
    html = template.render(**context)

    ensure_dir(output_path.parent)
    output_path.write_text(html, encoding="utf-8")
    return output_path


async def _generate_pdf_async(input_path: Path, output_path: Path, page_format: str) -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()
        html = input_path.read_text(encoding="utf-8")
        await page.set_content(html, wait_until="networkidle")
        ensure_dir(output_path.parent)
        await page.pdf(
            path=output_path.as_posix(),
            format=page_format,
            print_background=True,
            margin={"top": "0.4in", "right": "0.4in", "bottom": "0.4in", "left": "0.4in"},
        )
        await browser.close()


def generate_pdf_file(input_path: Path, output_path: Path, page_format: str) -> Path:
    asyncio.run(_generate_pdf_async(input_path, output_path, page_format))
    return output_path


__all__ = [
    "generate_pdf_file",
    "render_resume_html",
]

