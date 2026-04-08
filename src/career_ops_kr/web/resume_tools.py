from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from career_ops_kr.utils import ensure_dir
from career_ops_kr.web.ai import AiServiceError, generate_json, generate_text
from career_ops_kr.web.db import connection_scope
from career_ops_kr.web.search import search_jobs


REPO_ROOT = Path(__file__).resolve().parents[3]
UPLOAD_DIR = Path(
    os.getenv(
        "CAREER_OPS_WEB_UPLOAD_DIR",
        os.getenv("CAREER_OPS_WEB_OUTPUT_DIR", (REPO_ROOT / "output").as_posix()) + "/web-uploads",
    )
)


def extract_resume_text(filename: str, content: bytes) -> str:
    lowered = filename.lower()
    if lowered.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages).strip()
    if lowered.endswith(".txt") or lowered.endswith(".md"):
        return content.decode("utf-8", errors="ignore").strip()
    raise ValueError("Unsupported file type. Use PDF, TXT, or MD.")


def save_uploaded_resume(filename: str, content: bytes, *, db_path: Path | None = None) -> dict[str, Any]:
    text = extract_resume_text(filename, content)
    if not text:
        raise ValueError("Could not extract text from file.")

    ensure_dir(UPLOAD_DIR)
    safe_name = Path(filename).name
    stored_path = UPLOAD_DIR / safe_name
    suffix_index = 1
    while stored_path.exists():
        stored_path = UPLOAD_DIR / f"{stored_path.stem}-{suffix_index}{stored_path.suffix}"
        suffix_index += 1
    stored_path.write_bytes(content)

    with connection_scope(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO resumes(filename, content, file_path) VALUES(?, ?, ?)",
            (filename, text, stored_path.as_posix()),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, filename, file_path, created_at FROM resumes WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return row or {}


def list_resumes(*, db_path: Path | None = None) -> list[dict[str, Any]]:
    with connection_scope(db_path) as conn:
        rows = conn.execute(
            "SELECT id, filename, file_path, created_at FROM resumes ORDER BY created_at DESC"
        ).fetchall()
    return rows


def get_resume_content(resume_id: int | None = None, *, db_path: Path | None = None) -> dict[str, Any] | None:
    with connection_scope(db_path) as conn:
        if resume_id is None:
            return conn.execute(
                "SELECT * FROM resumes ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return conn.execute("SELECT * FROM resumes WHERE id = ?", (resume_id,)).fetchone()


def analyze_resume_match(
    *,
    resume_id: int,
    job_description: str,
    job_id: int | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    resume = get_resume_content(resume_id, db_path=db_path)
    if not resume:
        raise ValueError("Resume not found.")

    prompt = f"""You are an expert recruiter and resume analyst.

RESUME:
{resume['content']}

JOB DESCRIPTION:
{job_description}

Return valid JSON with this exact structure:
{{
  "score": 0,
  "matched_skills": [],
  "missing_skills": [],
  "suggestions": [],
  "summary": ""
}}
"""
    analysis = generate_json(prompt, db_path=db_path)
    with connection_scope(db_path) as conn:
        conn.execute(
            """
            INSERT INTO match_results(resume_id, job_id, job_description, match_score, analysis_json)
            VALUES(?, ?, ?, ?, ?)
            """,
            (
                resume_id,
                job_id,
                job_description,
                float(analysis.get("score") or 0),
                json.dumps(analysis, ensure_ascii=False),
            ),
        )
        conn.commit()
    return analysis


def rewrite_resume_for_job(
    *,
    job_description: str,
    company: str | None = None,
    position: str | None = None,
    language: str = "en",
    resume_id: int | None = None,
    db_path: Path | None = None,
) -> str:
    resume = get_resume_content(resume_id, db_path=db_path)
    if not resume:
        raise ValueError("이력서를 먼저 업로드해주세요.")

    lang_instruction = (
        "한국어로 작성하세요. 기술 용어는 영어를 병기해도 됩니다."
        if language == "ko"
        else "Write the resume in English."
    )
    prompt = f"""You are an expert resume writer.

ORIGINAL RESUME:
{resume['content']}

TARGET COMPANY: {company or 'Not specified'}
TARGET POSITION: {position or 'Not specified'}

JOB DESCRIPTION:
{job_description}

Instructions:
1. Reorganize and rewrite the resume to fit the target role.
2. Use keywords from the job description naturally.
3. Quantify achievements where possible.
4. Keep the format ATS-friendly and concise.
5. {lang_instruction}
"""
    rewritten = generate_text(prompt, db_path=db_path)
    with connection_scope(db_path) as conn:
        conn.execute(
            "INSERT INTO ai_outputs(type, input_json, output) VALUES(?, ?, ?)",
            (
                "resume_rewrite",
                json.dumps(
                    {
                        "resume_id": resume["id"],
                        "company": company,
                        "position": position,
                        "language": language,
                    },
                    ensure_ascii=False,
                ),
                rewritten,
            ),
        )
        conn.commit()
    return rewritten


def recommend_jobs_for_resume(
    *,
    resume_id: int | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    resume = get_resume_content(resume_id, db_path=db_path)
    if not resume:
        raise ValueError("이력서를 먼저 업로드해주세요.")

    keyword_prompt = f"""Extract 3 job-search keywords from this resume.
Return JSON like {{"keywords": ["korean keyword", "english keyword 1", "english keyword 2"]}}.

RESUME:
{resume['content'][:3000]}
"""
    keyword_payload = generate_json(keyword_prompt, db_path=db_path)
    keywords = [str(item).strip() for item in keyword_payload.get("keywords", []) if str(item).strip()]
    all_results: list[dict[str, Any]] = []
    for keyword in keywords:
        payload = search_jobs(keyword)
        all_results.extend(payload["results"])

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for result in all_results:
        dedupe_key = f"{result['title']}|{result['company']}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(result)

    candidates = deduped[:15]
    ranking_prompt = (
        "이력서와 다음 공고의 적합도를 0-100 점수로 평가하고 한 줄 이유를 반환하세요.\n"
        f"이력서:\n{resume['content'][:2000]}\n\n"
        "채용 공고 목록:\n"
        + "\n".join(
            f"{index + 1}. {item['title']} @ {item['company']} ({item['location']})"
            for index, item in enumerate(candidates)
        )
        + '\n\nReturn JSON like {"rankings":[{"index":1,"score":85,"reason":"..."}, ...]}'
    )
    ranking_payload = generate_json(ranking_prompt, db_path=db_path)
    rankings = ranking_payload.get("rankings", [])
    recommendations: list[dict[str, Any]] = []
    for ranking in rankings:
        index = int(ranking.get("index", 0)) - 1
        if index < 0 or index >= len(candidates):
            continue
        enriched = dict(candidates[index])
        enriched["match_score"] = int(ranking.get("score", 0))
        enriched["reason"] = str(ranking.get("reason", ""))
        recommendations.append(enriched)
    recommendations.sort(key=lambda item: item["match_score"], reverse=True)
    return {"keywords": keywords, "recommendations": recommendations}


def generate_assistant_output(
    *,
    mode: str,
    payload: dict[str, Any],
    db_path: Path | None = None,
) -> str:
    prompts = {
        "cover_letter": (
            "Write a practical cover letter.\n"
            f"Resume:\n{(get_resume_content(payload.get('resume_id'), db_path=db_path) or {}).get('content', '')}\n\n"
            f"Company: {payload.get('company')}\n"
            f"Position: {payload.get('position')}\n"
            f"Job description:\n{payload.get('job_description')}"
        ),
        "interview_prep": (
            "Create interview preparation notes.\n"
            f"Company: {payload.get('company')}\n"
            f"Position: {payload.get('position')}\n"
            f"Job description:\n{payload.get('job_description')}"
        ),
        "job_analysis": (
            "Analyze this job description in detail.\n"
            f"Job description:\n{payload.get('job_description')}"
        ),
        "skill_gap": (
            "Analyze the skill gap between this resume and job description.\n"
            f"Resume:\n{(get_resume_content(payload.get('resume_id'), db_path=db_path) or {}).get('content', '')}\n\n"
            f"Job description:\n{payload.get('job_description')}"
        ),
    }
    if mode not in prompts:
        raise ValueError(f"Unsupported assistant mode: {mode}")
    output = generate_text(prompts[mode], db_path=db_path)
    with connection_scope(db_path) as conn:
        conn.execute(
            "INSERT INTO ai_outputs(type, input_json, output) VALUES(?, ?, ?)",
            (mode, json.dumps(payload, ensure_ascii=False), output),
        )
        conn.commit()
    return output
