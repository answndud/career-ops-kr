from __future__ import annotations

import typer

from career_ops_kr.commands.resume import run_batch_live_resume_smoke, run_live_resume_smoke
from career_ops_kr.commands.intake_cli import register_intake_commands
from career_ops_kr.commands.research_cli import register_research_commands
from career_ops_kr.commands.resume_cli import register_resume_commands
from career_ops_kr.commands.tracker_cli import register_tracker_commands
from career_ops_kr.commands.web_cli import register_web_commands


app = typer.Typer(help="Codex-first job search operations toolkit for Korean developers.")


register_web_commands(app)
register_intake_commands(app)
register_research_commands(app)
register_resume_commands(
    app,
    run_live_resume_smoke_func=lambda **kwargs: run_live_resume_smoke(**kwargs),
    run_batch_live_resume_smoke_func=lambda **kwargs: run_batch_live_resume_smoke(**kwargs),
)
register_tracker_commands(app)


def main() -> None:
    app()
