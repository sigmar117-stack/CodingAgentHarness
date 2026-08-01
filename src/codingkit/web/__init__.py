"""WebUI: FastAPI backend + React frontend static serving (PLAN Layer 5)."""

from .routes import router as api_router
from .server import create_app, serve
from .websocket import ConnectionManager

__all__ = [
    "api_router",
    "create_app",
    "serve",
    "ConnectionManager",
]