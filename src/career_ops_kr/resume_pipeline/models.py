from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ResumeTailoringArtifacts:
    output_path: Path
    packet: dict[str, Any]


@dataclass(slots=True)
class TailoredResumeContextArtifacts:
    output_path: Path
    context: dict[str, Any]


@dataclass(slots=True)
class BuildTailoredResumeArtifacts:
    tailoring_path: Path
    tailored_context_path: Path
    html_path: Path
    pdf_path: Path | None = None
    manifest_path: Path | None = None


@dataclass(slots=True)
class BuildTailoredResumeFromUrlArtifacts:
    job_path: Path
    report_path: Path
    tracker_path: Path | None
    tailoring_path: Path
    tailored_context_path: Path
    html_path: Path
    pdf_path: Path | None = None
    manifest_path: Path | None = None


@dataclass(slots=True)
class LiveResumeSmokeArtifacts:
    run_dir: Path
    job_path: Path
    report_path: Path
    tailoring_path: Path
    tailored_context_path: Path
    html_path: Path
    pdf_path: Path | None
    selected_url: str
    candidate_label: str | None
    used_fallback: bool
    cleaned: bool


@dataclass(slots=True)
class LiveResumeSmokeCandidate:
    url: str
    source: str | None = None
    label: str | None = None


@dataclass(slots=True)
class LiveResumeSmokeTarget:
    key: str
    candidates: list[LiveResumeSmokeCandidate]
    base_context_path: Path
    template_path: Path
    profile_path: Path
    description: str = ""


@dataclass(slots=True)
class BatchLiveResumeSmokeResult:
    successes: list[tuple[str, LiveResumeSmokeArtifacts]]
    failures: list[tuple[str, str]]


@dataclass(slots=True)
class BackfillArtifactManifestResult:
    scanned: int
    created: int
    overwritten: int
    skipped: int
    manifests: list[Path]


@dataclass(slots=True)
class LiveSmokeReportHealthEntry:
    target: str
    status: str
    generated_at: str | None
    age_hours: float | None
    report_path: Path | None
    report_type: str | None
    selected_url: str | None = None
    used_fallback: bool = False
    message: str | None = None


__all__ = [
    "BackfillArtifactManifestResult",
    "BatchLiveResumeSmokeResult",
    "BuildTailoredResumeArtifacts",
    "BuildTailoredResumeFromUrlArtifacts",
    "LiveResumeSmokeArtifacts",
    "LiveResumeSmokeCandidate",
    "LiveResumeSmokeTarget",
    "LiveSmokeReportHealthEntry",
    "ResumeTailoringArtifacts",
    "TailoredResumeContextArtifacts",
]

