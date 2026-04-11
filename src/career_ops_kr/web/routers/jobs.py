from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from career_ops_kr.web.routers.deps import JobsRouterDeps


def build_jobs_router(deps: JobsRouterDeps) -> APIRouter:
    router = APIRouter()

    @router.get("/api/jobs")
    def api_list_jobs(
        status: str | None = None,
        q: str | None = None,
        attention: str | None = None,
        sort: str = "updated_at",
        order: str = "DESC",
    ) -> list[dict[str, Any]]:
        allowed_sorts = {
            "company",
            "position",
            "status",
            "date_applied",
            "source",
            "updated_at",
            "created_at",
        }
        sort_key = sort if sort in allowed_sorts else "updated_at"
        order_key = "ASC" if order.upper() == "ASC" else "DESC"
        query = "SELECT * FROM jobs WHERE 1=1"
        params: list[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if q:
            like = f"%{q}%"
            query += " AND (company LIKE ? OR position LIKE ? OR notes LIKE ?)"
            params.extend([like, like, like])
        query += f" ORDER BY {sort_key} {order_key}"
        with deps.connection_scope() as conn:
            rows = conn.execute(query, params).fetchall()
        ui_rows = [deps.job_row_with_ui_state(row) for row in rows]
        return [row for row in ui_rows if deps.matches_attention_filter(row, attention)]

    @router.get("/api/follow-ups")
    def api_follow_ups(horizon_days: int = 7) -> dict[str, Any]:
        return deps.get_follow_up_agenda(horizon_days=horizon_days)

    @router.post("/api/jobs", status_code=201)
    async def api_create_job(request: Request) -> dict[str, Any]:
        payload = await request.json()
        try:
            return deps.save_job_record(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/import", status_code=201)
    async def api_import_job(request: Request, response: Response) -> dict[str, Any]:
        payload = await request.json()
        import_payload = {
            "company": payload.get("company"),
            "position": payload.get("position") or payload.get("title"),
            "url": payload.get("url"),
            "location": payload.get("location"),
            "salary_min": payload.get("salary_min"),
            "salary_max": payload.get("salary_max"),
            "notes": payload.get("description") or payload.get("notes"),
            "source": payload.get("source"),
            "status": payload.get("status") or "검토중",
        }
        try:
            saved = deps.save_job_record(import_payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        save_result = deps.safe_text(saved.pop("_save_result")) or "created"
        save_result_label, save_detail, save_tone = deps.describe_save_result(save_result)
        saved_state = deps.saved_job_search_state(
            saved,
            match_note="canonical URL 기준으로 저장 상태를 다시 확인했습니다.",
        )
        response.status_code = 201 if save_result == "created" else 200
        saved["save_result"] = save_result
        saved["save_result_label"] = save_result_label
        saved["save_detail"] = save_detail
        saved["save_tone"] = save_tone
        saved["detail_url"] = saved_state["detail_url"]
        saved["has_report"] = saved_state["has_report"]
        saved["has_resume"] = saved_state["has_resume"]
        saved["attention_summary"] = saved_state["attention_summary"]
        saved["duplicate_guard_note"] = saved_state["duplicate_guard_note"]
        saved["duplicate_guard_triggered"] = save_result in {"updated", "existing"}
        return saved

    @router.get("/api/jobs/{job_id}")
    def api_get_job(job_id: int) -> dict[str, Any]:
        with deps.connection_scope() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        return row

    @router.put("/api/jobs/{job_id}")
    async def api_update_job(job_id: int, request: Request) -> dict[str, Any]:
        payload = await request.json()
        try:
            return deps.update_job_record(job_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/jobs/bulk-update")
    async def api_bulk_update_jobs(request: Request) -> dict[str, Any]:
        payload = await request.json()
        try:
            return deps.bulk_update_job_records(payload.get("ids") or [], payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.delete("/api/jobs/{job_id}")
    def api_delete_job(job_id: int) -> dict[str, bool]:
        if not deps.delete_job_record(job_id):
            raise HTTPException(status_code=404, detail="Not found")
        return {"success": True}

    @router.post("/api/tracker/sync")
    def api_sync_tracker() -> dict[str, int]:
        return deps.sync_tracker_rows_to_jobs()

    return router
