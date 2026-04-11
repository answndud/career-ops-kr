from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from career_ops_kr.web.routers.deps import ResumeRouterDeps


def build_resume_router(deps: ResumeRouterDeps) -> APIRouter:
    router = APIRouter()

    @router.get("/api/resume/presets")
    def api_resume_presets() -> dict[str, Any]:
        return {
            "presets": deps.resume_preset_options(),
            "default_profile_path": deps.default_web_profile_path().as_posix(),
        }

    @router.get("/api/resume/upload")
    def api_list_resumes() -> list[dict[str, Any]]:
        return deps.list_resumes()

    @router.post("/api/resume/upload", status_code=201)
    async def api_upload_resume(file: UploadFile = File(...)) -> dict[str, Any]:
        content = await file.read()
        try:
            return deps.save_uploaded_resume(file.filename or "resume.pdf", content)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/resume/build-from-url")
    async def api_resume_build_from_url(request: Request) -> dict[str, Any]:
        payload = await request.json()
        url = str(payload.get("url") or "").strip()
        company = str(payload.get("company") or "").strip() or "Unknown"
        position = str(payload.get("position") or "").strip() or "Resume"
        role_key = str(payload.get("role") or "platform").strip().lower()
        language = str(payload.get("language") or "ko").strip().lower()
        source = deps.normalize_web_source(payload.get("source"), url)
        want_pdf = bool(payload.get("pdf"))
        if not url:
            raise HTTPException(status_code=400, detail="url is required")

        try:
            base_context_path, template_path = deps.resolve_resume_preset(role_key, language)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        profile_path = deps.default_web_profile_path()
        slug = deps.artifact_slug(company, position, role_key, language)
        deps.ensure_dir(deps.web_resume_output_dir)
        job_out = deps.jd_dir / f"{slug}.md"
        report_out = deps.report_dir / f"{slug}.md"
        tailoring_out = deps.output_dir / "resume-tailoring" / f"{slug}.json"
        context_out = deps.output_dir / "resume-contexts" / f"{slug}.json"
        html_out = deps.web_resume_output_dir / f"{slug}.html"
        pdf_out = deps.web_resume_output_dir / f"{slug}.pdf" if want_pdf else None

        try:
            artifacts = deps.run_build_tailored_resume_from_url(
                url,
                base_context_path,
                template_path,
                source=source,
                job_out=job_out,
                report_out=report_out,
                tracker_out=None,
                html_out=html_out,
                tailoring_out=tailoring_out,
                tailored_context_out=context_out,
                pdf_out=pdf_out,
                profile_path=profile_path,
                scorecard_path=deps.default_web_scorecard_path,
                overwrite=False,
                insecure=False,
                pdf_format="A4",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        linked_job_id = deps.attach_resume_artifacts_to_job(
            artifacts=artifacts,
            job_id=deps.safe_int(payload.get("job_id")),
            url=url,
            company=company,
            position=position,
        )

        return {
            "job_id": linked_job_id,
            "job_path": artifacts.job_path.as_posix(),
            "report_path": artifacts.report_path.as_posix(),
            "tailoring_path": artifacts.tailoring_path.as_posix(),
            "context_path": artifacts.tailored_context_path.as_posix(),
            "html_path": artifacts.html_path.as_posix(),
            "html_url": deps.output_url(artifacts.html_path),
            "pdf_path": artifacts.pdf_path.as_posix() if artifacts.pdf_path else None,
            "pdf_url": deps.output_url(artifacts.pdf_path) if artifacts.pdf_path else None,
            "manifest_path": artifacts.manifest_path.as_posix() if artifacts.manifest_path else None,
            "manifest_url": deps.output_url(artifacts.manifest_path) if artifacts.manifest_path else None,
            "profile_path": profile_path.as_posix(),
            "base_context_path": base_context_path.as_posix(),
            "template_path": template_path.as_posix(),
            "tailoring_guidance": deps.load_tailoring_guidance(artifacts.tailored_context_path),
        }

    return router
