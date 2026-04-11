from __future__ import annotations


def run_web_server(
    *,
    host: str = "127.0.0.1",
    port: int = 3001,
    reload: bool = False,
) -> None:
    import uvicorn

    uvicorn.run(
        "career_ops_kr.web.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
    )
