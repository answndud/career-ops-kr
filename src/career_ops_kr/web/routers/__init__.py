from career_ops_kr.web.routers.jobs import build_jobs_router
from career_ops_kr.web.routers.pages import build_pages_router
from career_ops_kr.web.routers.resume import build_resume_router
from career_ops_kr.web.routers.search import build_search_router
from career_ops_kr.web.routers.system import build_system_router

__all__ = [
    "build_jobs_router",
    "build_pages_router",
    "build_resume_router",
    "build_search_router",
    "build_system_router",
]
