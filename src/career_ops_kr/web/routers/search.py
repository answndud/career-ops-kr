from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from career_ops_kr.web.routers.deps import SearchRouterDeps


def build_search_router(deps: SearchRouterDeps) -> APIRouter:
    router = APIRouter()

    @router.get("/api/search")
    def api_search(q: str) -> dict[str, Any]:
        if not q.strip():
            raise HTTPException(status_code=400, detail="Query required")
        try:
            payload = deps.search_jobs(q.strip())
            payload["results"] = deps.enrich_search_results(payload.get("results", []))
            return payload
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.get("/api/search-presets")
    def api_search_presets() -> dict[str, Any]:
        return {"presets": deps.list_search_presets()}

    @router.post("/api/search-presets")
    async def api_save_search_preset(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            preset = deps.save_search_preset(payload.get("name"), payload.get("query"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"preset": preset, "presets": deps.list_search_presets()}

    @router.delete("/api/search-presets/{preset_key}")
    def api_delete_search_preset(preset_key: str) -> dict[str, Any]:
        if not deps.delete_search_preset(preset_key):
            raise HTTPException(status_code=404, detail="Preset not found")
        return {"success": True, "presets": deps.list_search_presets()}

    return router
