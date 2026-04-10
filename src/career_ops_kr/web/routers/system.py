from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from career_ops_kr.web.routers.deps import WebRouterDeps


def build_system_router(deps: WebRouterDeps) -> APIRouter:
    router = APIRouter()

    @router.post("/api/system/db/backup")
    def api_backup_database() -> dict[str, str]:
        backup_path = deps.create_database_backup(backup_dir=deps.web_db_snapshot_dir())
        return {"backup_path": backup_path.as_posix()}

    @router.post("/api/system/db/export")
    def api_export_database() -> dict[str, str]:
        export_path = deps.export_database_snapshot(out_path=deps.new_db_export_path())
        return {"export_path": export_path.as_posix()}

    @router.post("/api/system/db/import")
    async def api_import_database(file: UploadFile = File(...)) -> dict[str, Any]:
        if not (file.filename or "").lower().endswith(".json"):
            raise HTTPException(status_code=400, detail="Only JSON snapshot files are supported.")
        deps.ensure_dir(deps.web_db_snapshot_dir())
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snapshot_path = deps.web_db_snapshot_dir() / (
            f"import-{timestamp}-{deps.slugify(file.filename or 'snapshot', fallback='snapshot')}.json"
        )
        snapshot_path.write_bytes(await file.read())
        try:
            result = deps.import_database_snapshot(snapshot_path, backup_dir=deps.web_db_snapshot_dir())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "import_path": snapshot_path.as_posix(),
            "backup_path": str(result["backup_path"]),
            "counts": result["counts"],
        }

    @router.get("/api/dashboard")
    def api_dashboard() -> dict[str, Any]:
        dashboard = deps.get_dashboard_snapshot()
        dashboard["liveSmoke"] = deps.get_live_smoke_status_snapshot()
        return dashboard

    return router
