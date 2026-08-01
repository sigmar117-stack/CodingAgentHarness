"""MemoryManager: unified interface for remembering and recalling information.

Combines a VectorStore (for cross-session memory) with a SessionStore
(for session persistence).  Only stores key decisions — correction strategy
selections, user instructions, and important conventions (SPEC §3.6, PLAN T2.3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from codingkit.memory.session_store import SessionStore
from codingkit.memory.vector_store import VectorStore


class MemoryManager:
    """Unified interface for cross-session memory.

    Typical usage::

        mm = MemoryManager()
        mm.remember("decision-1", "Use pytest for testing", {"type": "decision"})
        results = mm.recall("pytest testing")
        mm.clear()

    The manager wraps a :class:`VectorStore` for semantic search and a
    :class:`SessionStore` for session persistence.
    """

    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        persist_directory: Optional[str] = None,
    ) -> None:
        """Initialise the memory manager.

        Args:
            storage_dir: Directory for session JSON files.
                         Passed through to :class:`SessionStore`.
            persist_directory: Directory for ChromaDB persistence.
                               Passed through to :class:`VectorStore`.
        """
        self._vector_store = VectorStore(persist_directory=persist_directory)
        self._session_store = SessionStore(storage_dir=storage_dir)

    # ── public API ────────────────────────────────────────────────────────

    def remember(
        self,
        key: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store a piece of information for future recall.

        Only key decisions and important context should be stored — not
        every turn of conversation.

        Args:
            key: Unique identifier for this memory.
            content: The text content to remember.
            metadata: Optional key-value metadata (e.g. ``{"type": "decision"}``).
        """
        self._vector_store.store(key, content, metadata)

    def recall(
        self,
        query: str,
        n_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """Search stored memories for information relevant to *query*.

        Args:
            query: Natural-language query string.
            n_results: Maximum number of results to return.

        Returns:
            A list of matching memory records, each with keys ``id``,
            ``content``, ``metadata``, and ``score``.  Empty list when
            no matches are found.
        """
        return self._vector_store.search(query, n_results=n_results)

    def clear(self) -> None:
        """Clear all stored memories."""
        self._vector_store.clear()

    # ── property access to sub-stores ─────────────────────────────────────

    @property
    def session_store(self) -> SessionStore:
        """Access the underlying :class:`SessionStore`."""
        return self._session_store

    @property
    def vector_store(self) -> VectorStore:
        """Access the underlying :class:`VectorStore`."""
        return self._vector_store