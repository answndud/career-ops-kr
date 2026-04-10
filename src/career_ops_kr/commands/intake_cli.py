from __future__ import annotations

import typer

from career_ops_kr.commands.intake_fetch_cli import register_intake_fetch_commands
from career_ops_kr.commands.intake_pipeline_cli import register_intake_pipeline_commands


def register_intake_commands(app: typer.Typer) -> None:
    register_intake_fetch_commands(app)
    register_intake_pipeline_commands(app)
