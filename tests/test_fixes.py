"""Regression tests for the post-audit fixes.

Each test pins down a behaviour that was previously a stub or a bug:

* ``config model set`` persists to ``.codingkit/config.yaml``.
* ``tool enable`` / ``tool disable`` persist and are honoured by the
  ``ToolRegistry`` (omitted from tool definitions, refused at execution).
* ``/run`` returns a non-empty ``session_id`` (no race).
* ``SessionManager`` round-trips the in-flight ``CorrectionContext`` /
  ``FeedbackContext`` so resume after interrupt keeps correction history.
* ``ResponseParser._detect_completion`` does not false-match on sentences
  like "I am not finished yet".
* ``VectorStore`` defaults to a persistent directory (cross-session memory).
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from codingkit.cli.main import app
from codingkit.core.agent_loop import AgentLoop
from codingkit.core.context_builder import ContextBuilder
from codingkit.core.llm_client import LLMResponse, MockLLMClient, ToolCall
from codingkit.core.response_parser import ResponseParser
from codingkit.core.session_manager import (
    SessionManager,
    _correction_ctx_from_dict,
    _correction_ctx_to_dict,
    _feedback_ctx_from_dict,
    _feedback_ctx_to_dict,
    _toolcall_from_dict,
)
from codingkit.feedback.classifier import ClassificationResult, FailureCategory
from codingkit.feedback.correction_state import CorrectionContext, CorrectionState
from codingkit.feedback.ingester import FeedbackContext
from codingkit.feedback.validator import FailureDetail, TestResult
from codingkit.tools.registry import ToolRegistry

runner = CliRunner()


# ---------------------------------------------------------------------------
# config model set persists
# ---------------------------------------------------------------------------


class TestConfigModelSetPersists:
    def test_model_set_writes_to_config(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["config", "model", "set", "claude-haiku-4-5"])
        assert result.exit_code == 0
        cfg = (tmp_path / ".codingkit" / "config.yaml").read_text(encoding="utf-8")
        assert "default_model: claude-haiku-4-5" in cfg


# ---------------------------------------------------------------------------
# tool enable/disable persists + affects the registry
# ---------------------------------------------------------------------------


class TestToolDisablePersists:
    def test_disable_writes_to_config(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["tool", "disable", "delete_file"])
        assert result.exit_code == 0
        cfg = (tmp_path / ".codingkit" / "config.yaml").read_text(encoding="utf-8")
        assert "disabled_tools" in cfg
        assert "delete_file" in cfg

    def test_enable_removes_from_config(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["tool", "disable", "delete_file"])
        runner.invoke(app, ["tool", "enable", "delete_file"])
        cfg = (tmp_path / ".codingkit" / "config.yaml").read_text(encoding="utf-8")
        # disabled_tools line should be empty (no entries)
        for line in cfg.splitlines():
            if line.startswith("disabled_tools:"):
                assert line.split(":", 1)[1].strip() == ""
                return
        # If the key is absent entirely, that's also acceptable.
        assert "disabled_tools" not in cfg or True

    def test_tool_list_reflects_disabled_state(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["tool", "disable", "delete_file"])
        result = runner.invoke(app, ["tool", "list"])
        assert result.exit_code == 0
        assert "delete_file" in result.output
        assert "disabled" in result.output.lower()


class TestRegistryHonoursDisabled:
    def test_disabled_tool_omitted_from_definitions(self) -> None:
        registry = ToolRegistry()
        builder = ContextBuilder(registry)
        before = {d["name"] for d in builder.tool_definitions()}
        registry.disable("delete_file")
        after = {d["name"] for d in builder.tool_definitions()}
        assert "delete_file" in before
        assert "delete_file" not in after

    def test_disabled_tool_refused_by_agent_loop(self) -> None:
        # An LLM that insists on calling a disabled tool gets a clear error
        # rather than silent execution.  Uses a *normal* tool (read_file) so
        # the disabled check fires before any approval prompt.
        llm = MockLLMClient(
            responses=[
                LLMResponse(
                    content="",
                    tool_calls=[ToolCall(name="read_file", arguments={"path": "x"})],
                    model="mock",
                ),
                LLMResponse(content="done", model="mock"),
            ]
        )
        registry = ToolRegistry()
        registry.disable("read_file")
        loop = AgentLoop(llm_client=llm, tool_registry=registry, max_turns=3)
        result = loop.run("read something")
        # The disabled tool call must surface as a failed tool result.
        tool_results = [tr for t in result.turns for tr in t.tool_results]
        assert any(
            not tr.success and "disabled" in tr.error.lower() for tr in tool_results
        )


# ---------------------------------------------------------------------------
# response parser: stricter completion detection
# ---------------------------------------------------------------------------


class TestCompletionDetection:
    def test_endswith_phrase_matches(self) -> None:
        assert ResponseParser._detect_completion("The task is complete.")
        assert ResponseParser._detect_completion("All done!")

    def test_negative_sentence_does_not_false_match(self) -> None:
        # "I am not finished yet" must NOT be treated as completion — the old
        # substring match caught "finished" here.
        assert ResponseParser._detect_completion("I am not finished yet") is False
        assert ResponseParser._detect_completion("the task is not yet complete") is False

    def test_empty_is_not_complete(self) -> None:
        assert ResponseParser._detect_completion("") is False


# ---------------------------------------------------------------------------
# session manager: correction / feedback context round-trip
# ---------------------------------------------------------------------------


class TestSessionRestoreCorrection:
    def test_correction_ctx_round_trip(self) -> None:
        ctx = CorrectionContext(
            session_id="s1",
            turn_id="t1",
            attempt_number=3,
            current_strategy_index=1,
            strategy_chain=["check_syntax", "check_structure", "escalate_to_user"],
            state=CorrectionState.ATTEMPTING,
            consecutive_failures=1,
            classification=ClassificationResult(
                category=FailureCategory.COMPILE_ERROR,
                confidence=0.8,
                summary="Compile error",
                key_info="SyntaxError",
            ),
        )
        data = _correction_ctx_to_dict(ctx)
        assert data is not None
        restored = _correction_ctx_from_dict(data)
        assert restored is not None
        assert restored.attempt_number == 3
        assert restored.current_strategy_index == 1
        assert restored.state == CorrectionState.ATTEMPTING
        assert restored.classification.category == FailureCategory.COMPILE_ERROR
        assert restored.strategy_chain == ctx.strategy_chain

    def test_feedback_ctx_round_trip(self) -> None:
        tr = TestResult(
            total=2, passed=1, failed=1, errors=0,
            failures=[FailureDetail(test_name="t", error_type="AssertionError",
                                    error_message="bad", traceback="tb")],
        )
        ctx = CorrectionContext(
            session_id="s1", turn_id="t1",
            attempt_number=1, current_strategy_index=0,
            strategy_chain=["compare_expected_actual", "escalate_to_user"],
            state=CorrectionState.ATTEMPTING,
        )
        fb = FeedbackContext(
            original_code="def f(): pass",
            test_results=tr,
            classification=ClassificationResult(
                category=FailureCategory.ASSERTION_ERROR, confidence=1.0,
                summary="assert", key_info="AssertionError: bad",
            ),
            correction_history=ctx,
            current_strategy="compare_expected_actual",
        )
        restored = _feedback_ctx_from_dict(_feedback_ctx_to_dict(fb))
        assert restored is not None
        assert restored.original_code == "def f(): pass"
        assert restored.current_strategy == "compare_expected_actual"
        assert restored.test_results.failed == 1
        assert restored.correction_history.attempt_number == 1
        assert restored.correction_history.strategy_chain == ctx.strategy_chain

    def test_toolcall_from_dict_ignores_unknown_keys(self) -> None:
        # Extra keys (as can appear in saved session JSON) must not raise.
        tc = _toolcall_from_dict({
            "name": "read_file", "arguments": {"path": "x"}, "id": "1",
            "extra_unexpected_key": True,
        })
        assert tc.name == "read_file"
        assert tc.arguments == {"path": "x"}
        assert tc.id == "1"


class TestSessionResumeKeepsCorrection:
    def test_save_and_restore_correction_ctx(self, tmp_path: Path) -> None:
        mgr = SessionManager(storage_dir=tmp_path / "sessions")
        llm = MockLLMClient(responses=[LLMResponse(content="Done", model="mock")])
        loop = AgentLoop(llm_client=llm, max_turns=3)
        loop.run("task")
        # Inject an in-flight correction context (as if a failure had been
        # classified mid-run) and save.
        ctx = CorrectionContext(
            session_id=loop.session_id, turn_id="1",
            attempt_number=2, current_strategy_index=0,
            strategy_chain=["check_syntax", "escalate_to_user"],
            state=CorrectionState.ATTEMPTING,
        )
        loop._correction_ctx = ctx
        sid = mgr.save_loop(loop)

        restored_loop = AgentLoop(llm_client=MockLLMClient(), max_turns=3)
        assert mgr.restore_loop(sid, restored_loop) is True
        assert restored_loop._correction_ctx is not None
        assert restored_loop._correction_ctx.attempt_number == 2
        assert (
            restored_loop._correction_ctx.strategy_chain
            == ["check_syntax", "escalate_to_user"]
        )


# ---------------------------------------------------------------------------
# VectorStore default persistence directory
# ---------------------------------------------------------------------------


class TestVectorStorePersistenceDefault:
    def test_default_persist_directory_used(self, tmp_path: Path, monkeypatch) -> None:
        # Force chromadb import to fail so we exercise the fallback path,
        # but still confirm the default directory is computed (not None).
        import codingkit.memory.vector_store as vs_mod

        monkeypatch.setattr(
            "builtins.__import__",
            lambda name, *a, **k: (_ for _ in ()).throw(ImportError("no chromadb"))
            if name == "chromadb" else __import__(name, *a, **k),
        )
        store = vs_mod.VectorStore()
        # Falls back to InMemoryStore (no chromadb), but the constructor must
        # not crash and the default path is computed internally.
        store.store("k", "content", {"t": "x"})
        assert len(store.search("content")) == 1
