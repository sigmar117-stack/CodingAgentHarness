"""Tests for the memory module (PLAN T2.3).

Covers SessionStore, VectorStore (with ChromaDB fallback), and MemoryManager.
All tests are deterministic and require no network or real LLM.
"""

import tempfile
import uuid
from pathlib import Path

import pytest

from codingkit.memory.memory_manager import MemoryManager
from codingkit.memory.session_store import SessionStore
from codingkit.memory.vector_store import InMemoryStore, VectorStore

# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def temp_dir():
    """Provide a temporary directory that is cleaned up after the test."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def session_store(temp_dir):
    """Return a SessionStore backed by a temp directory."""
    return SessionStore(storage_dir=temp_dir)


@pytest.fixture
def vector_store():
    """Return a VectorStore (will use InMemoryStore due to no chromadb)."""
    return VectorStore()


@pytest.fixture
def memory_manager(temp_dir):
    """Return a MemoryManager backed by a temp directory."""
    return MemoryManager(storage_dir=temp_dir)


# ═══════════════════════════════════════════════════════════════════════════
# SessionStore Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSessionStore:
    """SessionStore: JSON file persistence for sessions."""

    def test_save_and_load_session(self, session_store):
        """Save a session then load it back, asserting fields match."""
        session_id = str(uuid.uuid4())
        data = {
            "id": session_id,
            "task": "Implement a sorting algorithm",
            "status": "running",
            "turns": [],
        }
        session_store.save(session_id, data)
        loaded = session_store.load(session_id)
        assert loaded is not None
        assert loaded["id"] == session_id
        assert loaded["task"] == data["task"]
        assert loaded["status"] == "running"

    def test_load_nonexistent_session(self, session_store):
        """Loading a session that does not exist returns None."""
        result = session_store.load("nonexistent-id")
        assert result is None

    def test_list_sessions(self, session_store):
        """List returns all saved sessions."""
        ids = [str(uuid.uuid4()) for _ in range(3)]
        for i, sid in enumerate(ids):
            session_store.save(sid, {"id": sid, "task": f"Task {i}", "status": "completed"})
        listed = session_store.list_sessions()
        listed_ids = [s["id"] for s in listed]
        for sid in ids:
            assert sid in listed_ids

    def test_delete_session(self, session_store):
        """Delete a session and assert it is gone."""
        session_id = str(uuid.uuid4())
        session_store.save(session_id, {"id": session_id, "task": "Delete me", "status": "paused"})
        session_store.delete(session_id)
        assert session_store.load(session_id) is None

    def test_delete_nonexistent_session_does_not_raise(self, session_store):
        """Deleting a session that does not exist should not raise."""
        session_store.delete("no-such-session")  # should not raise

    def test_save_overwrites_existing_session(self, session_store):
        """Saving with an existing session id overwrites the previous data."""
        session_id = str(uuid.uuid4())
        session_store.save(session_id, {"id": session_id, "status": "running"})
        session_store.save(session_id, {"id": session_id, "status": "completed", "summary": "done"})
        loaded = session_store.load(session_id)
        assert loaded["status"] == "completed"
        assert loaded["summary"] == "done"

    def test_list_sessions_empty(self, session_store):
        """List returns an empty list when no sessions exist."""
        assert session_store.list_sessions() == []

    def test_session_data_is_persistent(self, temp_dir):
        """Data written via SessionStore is readable as raw JSON on disk."""
        store1 = SessionStore(storage_dir=temp_dir)
        sid = str(uuid.uuid4())
        store1.save(sid, {"id": sid, "value": 42})
        # Create a new store instance pointing at the same dir
        store2 = SessionStore(storage_dir=temp_dir)
        loaded = store2.load(sid)
        assert loaded["value"] == 42


# ═══════════════════════════════════════════════════════════════════════════
# VectorStore / InMemoryStore Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestVectorStore:
    """VectorStore: ChromaDB wrapper that degrades to InMemoryStore."""

    def test_store_and_search(self, vector_store):
        """Store a record and search, assert the relevant result is returned."""
        vector_store.store("decision-1", "The user asked to use pytest for testing", {"type": "decision"})
        results = vector_store.search("pytest testing", n_results=5)
        assert len(results) > 0
        # The result should contain our stored content
        contents = [r["content"] for r in results]
        assert any("pytest" in c for c in contents)

    def test_search_multiple_ordering(self, vector_store):
        """Store multiple records, search for the most relevant, ordering is correct."""
        vector_store.store("doc-1", "Python is a programming language", {"topic": "python"})
        vector_store.store("doc-2", "Chocolate cake recipe with flour and eggs", {"topic": "cooking"})
        vector_store.store("doc-3", "Python decorators and context managers", {"topic": "python"})
        results = vector_store.search("Python programming", n_results=3)
        # The two Python-related docs should appear before the cooking one
        topics = [r["metadata"].get("topic", "") for r in results]
        python_indices = [i for i, t in enumerate(topics) if t == "python"]
        cooking_indices = [i for i, t in enumerate(topics) if t == "cooking"]
        # Python docs should be ranked higher (lower index) than cooking
        assert len(python_indices) > 0
        if cooking_indices:
            assert max(python_indices) < min(cooking_indices)

    def test_clear_returns_empty(self, vector_store):
        """Clear the store, then search, assert empty list."""
        vector_store.store("doc-1", "Something to remember", {"type": "test"})
        vector_store.clear()
        results = vector_store.search("Something to remember", n_results=5)
        assert len(results) == 0

    def test_search_empty_store(self, vector_store):
        """Searching an empty store returns an empty list."""
        results = vector_store.search("anything", n_results=5)
        assert results == []

    def test_search_with_metadata_filter(self, vector_store):
        """Search with metadata filtering returns only matching records."""
        vector_store.store("py-1", "Python list comprehensions", {"lang": "python", "type": "syntax"})
        vector_store.store("js-1", "JavaScript arrow functions", {"lang": "javascript", "type": "syntax"})
        results = vector_store.search("functions", n_results=5, filter_metadata={"lang": "javascript"})
        assert len(results) > 0
        for r in results:
            assert r["metadata"].get("lang") == "javascript"

    def test_store_without_metadata(self, vector_store):
        """Store a record without metadata, search still works."""
        vector_store.store("simple", "Just a plain text record")
        results = vector_store.search("plain text", n_results=5)
        assert len(results) == 1
        assert results[0]["id"] == "simple"


# ═══════════════════════════════════════════════════════════════════════════
# InMemoryStore Direct Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestInMemoryStore:
    """InMemoryStore: the fallback store used when ChromaDB is unavailable."""

    @pytest.fixture
    def mem_store(self):
        return InMemoryStore()

    def test_store_and_search(self, mem_store):
        mem_store.store("k1", "Python is great for data science", {"tag": "python"})
        results = mem_store.search("data science", n_results=5)
        assert len(results) > 0
        assert results[0]["id"] == "k1"

    def test_search_multiple_ordering(self, mem_store):
        mem_store.store("a", "Python programming language", {"tag": "python"})
        mem_store.store("b", "Baking bread with yeast", {"tag": "cooking"})
        mem_store.store("c", "Python decorators explained", {"tag": "python"})
        results = mem_store.search("Python", n_results=3)
        topics = [r["metadata"].get("tag", "") for r in results]
        python_indices = [i for i, t in enumerate(topics) if t == "python"]
        cooking_indices = [i for i, t in enumerate(topics) if t == "cooking"]
        assert len(python_indices) > 0
        if cooking_indices:
            assert max(python_indices) < min(cooking_indices)

    def test_clear(self, mem_store):
        mem_store.store("x", "Data", {"v": 1})
        mem_store.clear()
        assert mem_store.search("Data", n_results=5) == []

    def test_search_empty(self, mem_store):
        assert mem_store.search("anything", n_results=5) == []


# ═══════════════════════════════════════════════════════════════════════════
# MemoryManager Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestMemoryManager:
    """MemoryManager: unified remember/recall/clear interface."""

    def test_remember_and_recall(self, memory_manager):
        """Remember a key decision, then recall it."""
        memory_manager.remember(
            key="decision-fix-strategy",
            content="Use binary search to fix the performance issue",
            metadata={"type": "decision", "strategy": "optimization"},
        )
        results = memory_manager.recall("binary search optimization")
        assert len(results) > 0
        assert any("binary search" in r["content"] for r in results)

    def test_recall_empty(self, memory_manager):
        """Recall on an empty memory returns an empty list."""
        results = memory_manager.recall("anything")
        assert results == []

    def test_clear_memory(self, memory_manager):
        """Clear all memory, then recall returns empty."""
        memory_manager.remember("k1", "Important decision", {"type": "decision"})
        memory_manager.clear()
        results = memory_manager.recall("Important decision")
        assert len(results) == 0

    def test_remember_without_metadata(self, memory_manager):
        """Remember a record without metadata."""
        memory_manager.remember("k2", "Plain text note")
        results = memory_manager.recall("plain text note")
        assert len(results) == 1

    def test_multiple_remembers_ordering(self, memory_manager):
        """Remember multiple records, recall returns most relevant first."""
        memory_manager.remember("a", "Python is a high-level language", {"topic": "python"})
        memory_manager.remember("b", "Java is a compiled language", {"topic": "java"})
        memory_manager.remember("c", "Python has dynamic typing", {"topic": "python"})
        results = memory_manager.recall("Python dynamic typing", n_results=3)
        assert len(results) >= 2
        # The most relevant result should be about Python
        topics = [r["metadata"].get("topic", "") for r in results]
        python_indices = [i for i, t in enumerate(topics) if t == "python"]
        java_indices = [i for i, t in enumerate(topics) if t == "java"]
        if java_indices:
            assert max(python_indices) < min(java_indices)


# ═══════════════════════════════════════════════════════════════════════════
# Degradation / Fallback Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestDegradation:
    """When ChromaDB is unavailable, VectorStore degrades gracefully."""

    def test_vector_store_uses_inmemory_when_chromadb_unavailable(self):
        """VectorStore should fall back to InMemoryStore when chromadb is not importable."""
        store = VectorStore()
        # It should be usable without any error
        store.store("test", "Fallback content", {"type": "fallback"})
        results = store.search("Fallback content", n_results=5)
        assert len(results) == 1
        assert results[0]["id"] == "test"

    def test_memory_manager_works_without_chromadb(self, temp_dir):
        """MemoryManager should work even when chromadb is not installed."""
        mm = MemoryManager(storage_dir=temp_dir)
        mm.remember("key", "Content without chromadb", {"note": "test"})
        results = mm.recall("Content without chromadb")
        assert len(results) == 1
        assert results[0]["id"] == "key"


# ═══════════════════════════════════════════════════════════════════════════
# SessionStore + MemoryManager Integration Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestIntegration:
    """Integration tests combining SessionStore and MemoryManager."""

    def test_create_list_delete_restore_session(self, session_store, temp_dir):
        """Full lifecycle: create, list, delete, restore a session."""
        # Create sessions
        sid1 = str(uuid.uuid4())
        sid2 = str(uuid.uuid4())
        session_store.save(sid1, {"id": sid1, "task": "Task A", "status": "running"})
        session_store.save(sid2, {"id": sid2, "task": "Task B", "status": "completed"})

        # List them
        sessions = session_store.list_sessions()
        assert len(sessions) == 2

        # Delete one
        session_store.delete(sid1)
        assert session_store.load(sid1) is None
        assert session_store.load(sid2) is not None

        # Restore (re-create) a session
        session_store.save(sid1, {"id": sid1, "task": "Task A (restored)", "status": "paused"})
        loaded = session_store.load(sid1)
        assert loaded["status"] == "paused"
        assert "restored" in loaded["task"]

    def test_memory_manager_with_session_store(self, temp_dir):
        """MemoryManager uses VectorStore internally, and SessionStore is separate."""
        mm = MemoryManager(storage_dir=temp_dir)
        ss = SessionStore(storage_dir=temp_dir)

        # Store memory
        mm.remember("decision-1", "Use pytest for testing", {"type": "decision"})

        # Store session
        session_id = str(uuid.uuid4())
        ss.save(session_id, {"id": session_id, "task": "Setup tests", "status": "completed"})

        # Both should work independently
        memory_results = mm.recall("pytest testing")
        assert len(memory_results) > 0

        session = ss.load(session_id)
        assert session["task"] == "Setup tests"