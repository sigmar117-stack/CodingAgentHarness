"""VectorStore: ChromaDB wrapper that degrades to InMemoryStore.

When ChromaDB is not installed (or fails to initialise), the store
silently falls back to an in-memory TF-IDF-based store so that the
rest of the application remains functional (SPEC §3.6, PLAN T2.3).
"""

from __future__ import annotations

import re
from collections import Counter
from math import log, sqrt
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ═══════════════════════════════════════════════════════════════════════════
# InMemoryStore  —  fallback for when ChromaDB is unavailable
# ═══════════════════════════════════════════════════════════════════════════

class InMemoryStore:
    """A simple in-memory vector store using TF-IDF scoring.

    Provides the same ``store`` / ``search`` / ``clear`` interface as the
    ChromaDB-backed VectorStore, but works without any external dependency.
    Used as the automatic fallback when ChromaDB cannot be imported.
    """

    def __init__(self) -> None:
        self._records: Dict[str, Dict[str, Any]] = {}  # id -> {content, metadata}

    # ── public API ────────────────────────────────────────────────────────

    def store(
        self,
        record_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store a record.

        Args:
            record_id: Unique identifier.
            content: Text content to store.
            metadata: Optional key-value metadata.
        """
        self._records[record_id] = {
            "id": record_id,
            "content": content,
            "metadata": metadata or {},
        }

    def search(
        self,
        query: str,
        n_results: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search for records matching the query.

        Results are ranked by TF-IDF cosine similarity, highest first.

        Args:
            query: Natural-language query string.
            n_results: Maximum number of results to return.
            filter_metadata: If provided, only return records whose metadata
                             contains all the key-value pairs given.

        Returns:
            A list of dicts with keys ``id``, ``content``, ``metadata``, and
            ``score``.  Empty list when no matches are found.
        """
        # Fast path: empty store
        if not self._records:
            return []

        # Apply metadata filter first
        candidates = self._filter_by_metadata(filter_metadata)
        if not candidates:
            return []

        # Build TF-IDF vectors
        query_tfidf = self._tfidf_vector(query, candidates)
        scored: List[Tuple[float, str]] = []
        for rec_id in candidates:
            doc_tfidf = self._tfidf_vector(
                self._records[rec_id]["content"], candidates
            )
            score = self._cosine_similarity(query_tfidf, doc_tfidf)
            scored.append((score, rec_id))

        # Sort by score descending, then by ID for determinism
        scored.sort(key=lambda x: (-x[0], x[1]))

        results = []
        for score, rec_id in scored[:n_results]:
            rec = self._records[rec_id]
            results.append({
                "id": rec_id,
                "content": rec["content"],
                "metadata": rec["metadata"],
                "score": score,
            })
        return results

    def clear(self) -> None:
        """Remove all stored records."""
        self._records.clear()

    # ── internals ─────────────────────────────────────────────────────────

    def _filter_by_metadata(
        self,
        filter_metadata: Optional[Dict[str, Any]],
    ) -> List[str]:
        """Return record IDs whose metadata matches *filter_metadata*."""
        if not filter_metadata:
            return list(self._records.keys())
        matching: List[str] = []
        for rec_id, rec in self._records.items():
            meta = rec["metadata"]
            if all(meta.get(k) == v for k, v in filter_metadata.items()):
                matching.append(rec_id)
        return matching

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Lower-case, split on non-alphanumeric, return non-empty tokens."""
        return [t.lower() for t in re.split(r"[^a-zA-Z0-9]+", text) if t]

    def _term_frequency(self, tokens: List[str]) -> Counter:
        """Raw term frequency for a single document."""
        return Counter(tokens)

    def _inverse_document_frequency(
        self,
        term: str,
        candidate_ids: List[str],
    ) -> float:
        """IDF for a term across the candidate set."""
        n_docs = len(candidate_ids)
        if n_docs == 0:
            return 0.0
        n_containing = sum(
            1 for rid in candidate_ids
            if term in self._records[rid]["content"].lower()
        )
        return log((1 + n_docs) / (1 + n_containing)) + 1.0

    def _tfidf_vector(
        self,
        text: str,
        candidate_ids: List[str],
    ) -> Dict[str, float]:
        """Build a TF-IDF vector for *text* over the candidate set."""
        tokens = self._tokenize(text)
        tf = self._term_frequency(tokens)
        vector: Dict[str, float] = {}
        for term, count in tf.items():
            vector[term] = count * self._inverse_document_frequency(term, candidate_ids)
        return vector

    @staticmethod
    def _cosine_similarity(
        vec_a: Dict[str, float],
        vec_b: Dict[str, float],
    ) -> float:
        """Cosine similarity between two sparse vectors."""
        all_terms = set(vec_a) | set(vec_b)
        dot = sum(vec_a.get(t, 0.0) * vec_b.get(t, 0.0) for t in all_terms)
        norm_a = sqrt(sum(v * v for v in vec_a.values()))
        norm_b = sqrt(sum(v * v for v in vec_b.values()))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)


# ═══════════════════════════════════════════════════════════════════════════
# VectorStore  —  ChromaDB wrapper with graceful degradation
# ═══════════════════════════════════════════════════════════════════════════

class VectorStore:
    """Vector store backed by ChromaDB, falling back to InMemoryStore.

    Usage::

        store = VectorStore()
        store.store("key-1", "some content", {"type": "decision"})
        results = store.search("content query", n_results=5)
        store.clear()

    If ChromaDB is not installed or fails to initialise, all operations
    are handled transparently by :class:`InMemoryStore`.
    """

    def __init__(self, persist_directory: Optional[str] = None) -> None:
        """Initialise the store.

        Args:
            persist_directory: Directory for ChromaDB persistence. When
                ``None``, defaults to ``~/.codingkit/chroma`` so cross-session
                memory actually survives a process restart (SPEC §3.6).
                Ignored when falling back to :class:`InMemoryStore`.
        """
        self._store: InMemoryStore
        self._using_chromadb = False

        if persist_directory is None:
            persist_directory = str(Path.home() / ".codingkit" / "chroma")

        # Try to use ChromaDB; fall back to InMemoryStore on failure
        try:
            import chromadb  # type: ignore[import-untyped]  # noqa: F401
            self._init_chromadb(persist_directory)
        except Exception:  # noqa: BLE001
            self._store = InMemoryStore()

    # ── public API ────────────────────────────────────────────────────────

    def store(
        self,
        record_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store a record.

        Args:
            record_id: Unique identifier.
            content: Text content to store.
            metadata: Optional key-value metadata.
        """
        metadata = metadata or {}
        if self._using_chromadb:
            try:
                self._collection.add(
                    ids=[record_id],
                    documents=[content],
                    metadatas=[metadata],
                )
                return
            except Exception:  # noqa: BLE001
                # Fall back to InMemoryStore on ChromaDB error
                self._using_chromadb = False
        self._store.store(record_id, content, metadata)

    def search(
        self,
        query: str,
        n_results: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search for records matching the query.

        Args:
            query: Natural-language query string.
            n_results: Maximum number of results to return.
            filter_metadata: If provided, only return records whose metadata
                             contains all the key-value pairs given.

        Returns:
            A list of dicts with keys ``id``, ``content``, ``metadata``, and
            ``score``.  Empty list when no matches are found.
        """
        if self._using_chromadb:
            try:
                where = None
                if filter_metadata:
                    where = {k: v for k, v in filter_metadata.items()}
                result = self._collection.query(
                    query_texts=[query],
                    n_results=n_results,
                    where=where,
                )
                return self._format_chromadb_results(result)
            except Exception:  # noqa: BLE001
                self._using_chromadb = False
        return self._store.search(query, n_results, filter_metadata)

    def clear(self) -> None:
        """Remove all stored records."""
        if self._using_chromadb:
            try:
                self._collection.delete(
                    where={},  # Delete all
                )
                return
            except Exception:  # noqa: BLE001
                self._using_chromadb = False
        self._store.clear()

    # ── internals ─────────────────────────────────────────────────────────

    def _init_chromadb(self, persist_directory: Optional[str] = None) -> None:
        """Attempt to create a ChromaDB collection."""
        import chromadb  # type: ignore[import-untyped]
        self._client = chromadb.Client(
            chromadb.config.Settings(
                anonymized_telemetry=False,
                allow_reset=True,
                is_persistent=persist_directory is not None,
                persist_directory=persist_directory,
            )
        )
        self._collection = self._client.get_or_create_collection(
            name="codingkit_memory",
        )
        self._using_chromadb = True

    @staticmethod
    def _format_chromadb_results(
        result: Any,
    ) -> List[Dict[str, Any]]:
        """Convert ChromaDB query results to our standard format."""
        formatted: List[Dict[str, Any]] = []
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        for i, doc_id in enumerate(ids):
            # ChromaDB's default distance is cosine distance in [0, 2]; the
            # InMemoryStore returns cosine similarity in [0, 1].  Convert to a
            # comparable [0, 1] relevance score (clamp negatives to 0) so the
            # two backends report the same scale.
            dist = distances[i] if i < len(distances) else 2.0
            score = max(0.0, 1.0 - (dist / 2.0))
            formatted.append({
                "id": doc_id,
                "content": documents[i] if i < len(documents) else "",
                "metadata": metadatas[i] if i < len(metadatas) else {},
                "score": score,
            })
        return formatted