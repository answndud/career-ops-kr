from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from career_ops_kr.web.routers.deps import WebRouterDeps


def build_search_router(deps: WebRouterDeps) -> APIRouter:
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

    return router
