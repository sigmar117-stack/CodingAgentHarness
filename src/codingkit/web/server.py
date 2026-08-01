"""FastAPI application factory for the CodingKit WebUI (PLAN T5.1).

Usage::

    from codingkit.web.server import create_app
    app = create_app()
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routes import router

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE.parent.parent.parent / "webui" / "dist"


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        A fully configured FastAPI instance with:
        - CORS middleware (all origins for local dev)
        - REST API routes under ``/api``
        - WebSocket endpoint at ``/api/ws``
        - Static file serving for the React frontend (if ``webui/dist/`` exists)
    """
    app = FastAPI(
        title="CodingKit WebUI",
        description="Web interface for the CodingKit agent harness",
        version="0.1.0",
        docs_url="/docs",
    )

    # --- CORS (allow all origins for local dev) ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- API routes ---
    app.include_router(router)

    # --- Static file serving (React build output) ---
    static_path = STATIC_DIR.resolve()
    if static_path.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=str(static_path), html=True),
            name="static",
        )
        logger.info("Serving static files from %s", static_path)
    else:
        logger.warning(
            "Static directory not found at %s — frontend will not be served. "
            "Build the frontend with: cd webui && npm run build",
            static_path,
        )

    return app


# ---------------------------------------------------------------------------
# Standalone entry point (for development)
# ---------------------------------------------------------------------------


def serve(port: int = 8080, host: str = "127.0.0.1") -> None:
    """Start the WebUI server.

    Args:
        port: Port to listen on (default 8080).
        host: Host to bind to (default 127.0.0.1).
    """
    import uvicorn

    app = create_app()
    print(f"  CodingKit WebUI starting at http://{host}:{port}")
    print(f"  API docs at http://{host}:{port}/docs")
    print()
    uvicorn.run(app, host=host, port=port, log_level="info")