"""SessionStore: JSON file persistence for sessions.

Stores session data as individual JSON files in a configurable directory.
Part of the CodingKit memory module (PLAN T2.3).
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


class SessionStore:
    """Persists sessions as JSON files on disk.

    Each session is stored as ``<session_id>.json`` in *storage_dir*.
    Provides save/load/delete/list operations.
    """

    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        """Initialize the store.

        Args:
            storage_dir: Directory for session JSON files.
                         Defaults to ``~/.codingkit/sessions/``.
        """
        if storage_dir is None:
            storage_dir = Path.home() / ".codingkit" / "sessions"
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    # ── public API ────────────────────────────────────────────────────────

    def save(self, session_id: str, data: Dict[str, Any]) -> None:
        """Save (create or overwrite) a session.

        Args:
            session_id: Unique identifier for the session.
            data: Dictionary of session data to persist.
        """
        file_path = self._path_for(session_id)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load a session by its ID.

        Args:
            session_id: Unique identifier for the session.

        Returns:
            The session dict, or *None* if it does not exist.
        """
        file_path = self._path_for(session_id)
        if not file_path.exists():
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def delete(self, session_id: str) -> None:
        """Delete a session file.

        Does *not* raise if the file does not exist.

        Args:
            session_id: Unique identifier for the session.
        """
        file_path = self._path_for(session_id)
        if file_path.exists():
            file_path.unlink()

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all persisted sessions.

        Returns:
            A list of session dicts.  Each dict is the full content of the
            session JSON file.  Returns an empty list when no sessions exist.
        """
        sessions: List[Dict[str, Any]] = []
        if not self._storage_dir.exists():
            return sessions
        for file_path in sorted(self._storage_dir.iterdir()):
            if file_path.suffix == ".json":
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        sessions.append(json.load(f))
                except (json.JSONDecodeError, OSError):
                    continue
        return sessions

    # ── internals ─────────────────────────────────────────────────────────

    def _path_for(self, session_id: str) -> Path:
        """Return the filesystem path for a session ID."""
        return self._storage_dir / f"{session_id}.json"