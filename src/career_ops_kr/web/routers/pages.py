from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from career_ops_kr.web.routers.deps import PagesRouterDeps


def build_pages_router(deps: PagesRouterDeps) -> APIRouter:
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        dashboard = deps.get_dashboard_snapshot()
        return deps.templates.TemplateResponse(
            request,
            "home.html",
            deps.template_context(
                dashboard=dashboard,
                follow_up_agenda=dashboard.get("followUpAgenda") or deps.get_follow_up_agenda(),
                live_smoke=deps.get_live_smoke_status_snapshot(),
                resume_presets=deps.resume_preset_options(),
            ),
        )

    @router.get("/search", response_class=HTMLResponse)
    def search_page(
        request: Request,
        q: str | None = None,
        preset: str | None = None,
        source: str = "전체",
    ) -> HTMLResponse:
        results: dict[str, Any] | None = None
        visible_results: list[dict[str, Any]] = []
        selected_preset_source: str | None = None
        selected_preset = deps.use_search_preset(preset or "") if preset else None
        if selected_preset:
            selected_preset_source = "saved"
        elif not q:
            default_preset = next((item for item in deps.list_search_presets() if item.get("is_default")), None)
            if default_preset:
                selected_preset = deps.use_search_preset(default_preset["key"]) or default_preset
                selected_preset_source = "default"
        saved_presets = deps.list_search_presets()
        resolved_query = q or (selected_preset["query"] if selected_preset else "")
        active_source = source or "전체"
        if resolved_query:
            try:
                results = deps.search_jobs(resolved_query)
                results["results"] = deps.enrich_search_results(results.get("results", []))
                source_counts = results.get("sources", {})
                if active_source != "전체" and active_source not in source_counts:
                    active_source = "전체"
                result_rows = results.get("results", [])
                visible_results = (
                    result_rows
                    if active_source == "전체"
                    else [row for row in result_rows if row.get("source") == active_source]
                )
            except Exception as exc:
                results = {"error": str(exc), "results": [], "sources": {}}
        return deps.templates.TemplateResponse(
            request,
            "search.html",
            deps.template_context(
                query=resolved_query,
                selected_preset=selected_preset,
                selected_preset_source=selected_preset_source,
                search_presets=saved_presets,
                results=results,
                visible_results=visible_results,
                active_source=active_source,
                resume_presets=deps.resume_preset_options(),
            ),
        )

    @router.get("/artifacts", response_class=HTMLResponse)
    def artifacts_page(
        request: Request,
        source: str = "all",
        q: str = "",
    ) -> HTMLResponse:
        inventory = deps.generated_resume_snapshot(limit=None)
        filtered_items = deps.filter_generated_resume_items(inventory["items"], source=source, query=q)
        enriched_items = deps.enrich_generated_resume_items(filtered_items)
        return deps.templates.TemplateResponse(
            request,
            "artifacts.html",
            deps.template_context(
                source_filter=source if source in {"all", "web", "cli"} else "all",
                query=q,
                artifacts=enriched_items,
                inventory_total=inventory["total"],
                inventory_web_total=inventory["web_total"],
                inventory_cli_total=inventory["cli_total"],
                inventory_manifest_total=inventory["manifest_total"],
                inventory_legacy_total=inventory["legacy_total"],
                live_smoke=deps.get_live_smoke_status_snapshot(),
            ),
        )

    @router.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request) -> HTMLResponse:
        return deps.templates.TemplateResponse(
            request,
            "settings.html",
            deps.template_context(
                db_path=deps.resolve_db_path().as_posix(),
                live_smoke=deps.get_live_smoke_status_snapshot(),
            ),
        )

    @router.get("/tracker", response_class=HTMLResponse)
    def tracker_page(request: Request) -> HTMLResponse:
        with deps.connection_scope() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY updated_at DESC, created_at DESC"
            ).fetchall()
        jobs = [deps.job_row_with_ui_state(row) for row in rows]
        attention_counts = {
            "missing_report": sum(1 for row in jobs if not row["artifact_summary"]["report"]),
            "missing_resume": sum(1 for row in jobs if not row["artifact_summary"]["html"]),
            "overdue_follow_up": sum(
                1 for row in jobs if any(tag["label"] == "팔로업 overdue" for tag in row["attention"]["tags"])
            ),
        }
        return deps.templates.TemplateResponse(
            request,
            "tracker.html",
            deps.template_context(
                jobs=jobs,
                dashboard=deps.get_dashboard_snapshot(),
                statuses=deps.tracker_status_choices(),
                attention_counts=attention_counts,
                attention_filters=[
                    ("missing-report", "리포트 없음"),
                    ("missing-resume", "이력서 없음"),
                    ("follow-up-overdue", "팔로업 overdue"),
                    ("unlinked-tracker", "tracker 미연결"),
                ],
            ),
        )

    @router.get("/follow-ups", response_class=HTMLResponse)
    def follow_up_page(request: Request) -> HTMLResponse:
        agenda = deps.get_follow_up_agenda()
        return deps.templates.TemplateResponse(
            request,
            "follow-ups.html",
            deps.template_context(
                agenda=agenda,
                dashboard=deps.get_dashboard_snapshot(),
            ),
        )

    @router.get("/tracker/{job_id}", response_class=HTMLResponse)
    def tracker_job_detail_page(request: Request, job_id: int) -> HTMLResponse:
        with deps.connection_scope() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            match_results = conn.execute(
                """
                SELECT id, resume_id, match_score, created_at
                FROM match_results
                WHERE job_id = ?
                ORDER BY created_at DESC
                LIMIT 5
                """,
                (job_id,),
            ).fetchall()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        tracker_row = deps.load_tracker_row_for_job(row)
        tailoring_guidance = deps.load_tailoring_guidance(deps.coerce_path(row.get("context_path")))
        return deps.templates.TemplateResponse(
            request,
            "job-detail.html",
            deps.template_context(
                job=row,
                tracker_row=tracker_row,
                attention=deps.job_attention_snapshot(row, tracker_row),
                tracker_sync=deps.job_tracker_sync_snapshot(row, tracker_row),
                artifacts=deps.job_artifact_specs(row),
                tailoring_guidance=tailoring_guidance,
                focus_preview=deps.build_focus_preview(tailoring_guidance),
                match_results=match_results,
                resume_presets=deps.resume_preset_options(),
                statuses=deps.tracker_status_choices(),
            ),
        )

    @router.get("/tracker/{job_id}/artifacts/{artifact_key}")
    def tracker_job_artifact(job_id: int, artifact_key: str) -> Response:
        if artifact_key not in {"job", "report", "context"}:
            raise HTTPException(status_code=404, detail="Unsupported artifact")
        with deps.connection_scope() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        field_map = {
            "job": ("job_path", deps.jd_dir, "text/markdown; charset=utf-8"),
            "report": ("report_path", deps.report_dir, "text/markdown; charset=utf-8"),
            "context": ("context_path", deps.output_dir / "resume-contexts", "application/json"),
        }
        field_name, root, media_type = field_map[artifact_key]
        path = deps.coerce_path(row.get(field_name))
        if path is None or not path.exists() or not deps.safe_relative_to(path, root):
            raise HTTPException(status_code=404, detail="Artifact not found")
        content = path.read_text(encoding="utf-8")
        if media_type == "application/json":
            return Response(content=content, media_type=media_type)
        return PlainTextResponse(content, media_type=media_type)

    @router.get("/resume", response_class=HTMLResponse)
    def resume_page(request: Request) -> HTMLResponse:
        return deps.templates.TemplateResponse(
            request,
            "resume.html",
            deps.template_context(
                resumes=deps.list_resumes(),
                resume_presets=deps.resume_preset_options(),
            ),
        )

    return router
