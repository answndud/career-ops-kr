from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from career_ops_kr.commands.intake import DEFAULT_SCORECARD_PATH
from career_ops_kr.commands.resume import (
    build_tailored_resume_from_url as run_build_tailored_resume_from_url,
)
from career_ops_kr.utils import ensure_dir
from career_ops_kr.web.paths import WebPaths
from career_ops_kr.web.router_deps_factory import WebRouterFactoryHooks, build_router_deps
from career_ops_kr.web.routers import (
    build_jobs_router,
    build_pages_router,
    build_resume_router,
    build_search_router,
    build_system_router,
)
from career_ops_kr.web.routers.deps import WebRouterDeps
from career_ops_kr.web.runtime import build_web_paths
from career_ops_kr.web.search import search_jobs


REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=TEMPLATE_DIR.as_posix())


def _optional_env_path(name: str) -> Path | None:
    value = os.getenv(name)
    if not value:
        return None
    return Path(value)


OUTPUT_DIR = Path(os.getenv("CAREER_OPS_WEB_OUTPUT_DIR", (REPO_ROOT / "output").as_posix()))
TRACKER_PATH = Path(os.getenv("CAREER_OPS_WEB_TRACKER_PATH", (REPO_ROOT / "data" / "applications.md").as_posix()))
JD_DIR = Path(os.getenv("CAREER_OPS_WEB_JD_DIR", (REPO_ROOT / "jds").as_posix()))
REPORT_DIR = Path(os.getenv("CAREER_OPS_WEB_REPORT_DIR", (REPO_ROOT / "reports").as_posix()))
WEB_RESUME_OUTPUT_DIR = _optional_env_path("CAREER_OPS_WEB_RESUME_OUTPUT_DIR")
LIVE_SMOKE_REPORT_DIR = _optional_env_path("CAREER_OPS_WEB_LIVE_SMOKE_DIR")
DEFAULT_WEB_SCORECARD_PATH = (
    DEFAULT_SCORECARD_PATH if DEFAULT_SCORECARD_PATH.exists() else REPO_ROOT / "config" / "scorecard.kr.yml"
)
RESUME_PRESETS: dict[tuple[str, str], Path] = {
    ("backend", "ko"): REPO_ROOT / "examples" / "resume-context.backend.ko.example.json",
    ("backend", "en"): REPO_ROOT / "examples" / "resume-context.backend.example.json",
    ("platform", "ko"): REPO_ROOT / "examples" / "resume-context.platform.ko.example.json",
    ("platform", "en"): REPO_ROOT / "examples" / "resume-context.platform.example.json",
    ("data-platform", "ko"): REPO_ROOT / "examples" / "resume-context.data-platform.ko.example.json",
    ("data-platform", "en"): REPO_ROOT / "examples" / "resume-context.data-platform.example.json",
    ("data-ai", "ko"): REPO_ROOT / "examples" / "resume-context.data-ai.ko.example.json",
    ("data-ai", "en"): REPO_ROOT / "examples" / "resume-context.data-ai.example.json",
}
TEMPLATE_PRESETS: dict[str, Path] = {
    "ko": REPO_ROOT / "templates" / "resume-ko.html",
    "en": REPO_ROOT / "templates" / "resume-en.html",
}


def _web_paths() -> WebPaths:
    return build_web_paths(
        repo_root=REPO_ROOT,
        output_dir=OUTPUT_DIR,
        tracker_path=TRACKER_PATH,
        jd_dir=JD_DIR,
        report_dir=REPORT_DIR,
        web_resume_output_dir=WEB_RESUME_OUTPUT_DIR,
        live_smoke_report_dir=LIVE_SMOKE_REPORT_DIR,
    )


def _router_hooks() -> WebRouterFactoryHooks:
    return WebRouterFactoryHooks(
        templates=templates,
        paths_factory=_web_paths,
        default_web_scorecard_path=DEFAULT_WEB_SCORECARD_PATH,
        resume_presets=RESUME_PRESETS,
        template_presets=TEMPLATE_PRESETS,
        search_jobs=lambda query: search_jobs(query),
        run_build_tailored_resume_from_url=lambda *args, **kwargs: run_build_tailored_resume_from_url(*args, **kwargs),
    )


def _router_deps() -> WebRouterDeps:
    return build_router_deps(hooks=_router_hooks())


def create_app() -> FastAPI:
    paths = _web_paths()
    app = FastAPI(title="Career Ops KR Web")
    ensure_dir(paths.output_dir)
    app.mount("/output", StaticFiles(directory=paths.output_dir.as_posix()), name="output")
    deps = _router_deps()
    app.include_router(build_pages_router(deps.pages))
    app.include_router(build_system_router(deps.system))
    app.include_router(build_jobs_router(deps.jobs))
    app.include_router(build_search_router(deps.search))
    app.include_router(build_resume_router(deps.resume))
    return app
