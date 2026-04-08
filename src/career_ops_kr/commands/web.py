from __future__ import annotations

import os


def run_web_server(
    *,
    host: str = "127.0.0.1",
    port: int = 3001,
    reload: bool = False,
    enable_ai: bool = False,
) -> None:
    os.environ["CAREER_OPS_WEB_ENABLE_AI"] = "1" if enable_ai else "0"

    import uvicorn

    uvicorn.run(
        "career_ops_kr.web.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
    )
