from __future__ import annotations

from typing import Callable

import typer

from career_ops_kr.commands.resume_build_cli import register_resume_build_commands
from career_ops_kr.commands.resume_smoke_cli import register_resume_smoke_commands


def register_resume_commands(
    app: typer.Typer,
    *,
    run_live_resume_smoke_func: Callable[..., object],
    run_batch_live_resume_smoke_func: Callable[..., object],
) -> None:
    register_resume_build_commands(app)
    register_resume_smoke_commands(
        app,
        run_live_resume_smoke_func=run_live_resume_smoke_func,
        run_batch_live_resume_smoke_func=run_batch_live_resume_smoke_func,
    )
