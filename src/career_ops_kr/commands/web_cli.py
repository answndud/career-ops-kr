from __future__ import annotations

import typer

from career_ops_kr.commands.web import run_web_server


def register_web_commands(app: typer.Typer) -> None:
    @app.command("serve-web")
    def serve_web(
        host: str = typer.Option("127.0.0.1", "--host", help="Bind host for the optional web app."),
        port: int = typer.Option(3001, "--port", min=1, max=65535, help="Bind port for the optional web app."),
        reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for local development."),
    ) -> None:
        run_web_server(host=host, port=port, reload=reload)

