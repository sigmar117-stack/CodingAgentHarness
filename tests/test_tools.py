"""Tests for tools and registry (PLAN T2.1).

No network. ``run_tests`` spawns a real pytest subprocess on a throwaway test
file inside ``tmp_path`` (pytest is a required dev dependency).
"""

from __future__ import annotations

import json
import os
import shutil
import textwrap
from pathlib import Path

import pytest

from codingkit.tools.base import RiskLevel
from codingkit.tools.delete_file import DeleteFileTool
from codingkit.tools.edit_file import EditFileTool
from codingkit.tools.execute_command import ExecuteCommandTool
from codingkit.tools.git_operation import GitOperationTool
from codingkit.tools.read_file import ReadFileTool
from codingkit.tools.registry import default_registry
from codingkit.tools.run_tests import RunTestsTool, _parse_junitxml
from codingkit.tools.search_content import SearchContentTool
from codingkit.tools.search_files import SearchFilesTool
from codingkit.tools.write_file import WriteFileTool

# --- Registry (PLAN T2.1 ① ⑥) --------------------------------------------


def test_registry_registers_all_ten_tools() -> None:
    reg = default_registry()
    assert len(reg.list_all()) == 10
    for name in [
        "read_file", "write_file", "edit_file", "execute_command", "run_tests",
        "search_files", "search_content", "install_dependencies", "delete_file",
        "git_operation",
    ]:
        tool = reg.get(name)
        assert tool is not None
        assert tool.name == name


def test_registry_unknown_name_returns_none() -> None:
    """PLAN T2.1 ⑥ — unknown tool name returns None."""
    assert default_registry().get("no_such_tool") is None


def test_registry_marks_four_tools_dangerous() -> None:
    reg = default_registry()
    dangerous = {t.name for t in reg.dangerous_tools()}
    assert dangerous == {"execute_command", "install_dependencies", "delete_file", "git_operation"}
    # the rest are normal
    normal = {t.name for t in reg.list_all() if t.risk_level == RiskLevel.NORMAL}
    assert normal == {"read_file", "write_file", "edit_file", "run_tests", "search_files", "search_content"}


# --- read_file (PLAN T2.1 ② ③) --------------------------------------------


def test_read_file_returns_content(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("hello world", encoding="utf-8")
    res = ReadFileTool().execute({"path": str(f)})
    assert res.success is True
    assert res.output == "hello world"


def test_read_file_missing_returns_error(tmp_path: Path) -> None:
    res = ReadFileTool().execute({"path": str(tmp_path / "missing.txt")})
    assert res.success is False
    assert "not found" in (res.error or "").lower()


def test_read_file_requires_path() -> None:
    res = ReadFileTool().execute({})
    assert res.success is False
    assert "path" in (res.error or "")


# --- write_file (PLAN T2.1 ④) ---------------------------------------------


def test_write_then_read_roundtrip(tmp_path: Path) -> None:
    f = tmp_path / "out.txt"
    res = WriteFileTool().execute({"path": str(f), "content": "line1\nline2"})
    assert res.success is True
    assert ReadFileTool().execute({"path": str(f)}).output == "line1\nline2"


# --- edit_file -------------------------------------------------------------


def test_edit_file_replaces_text(tmp_path: Path) -> None:
    f = tmp_path / "e.txt"
    f.write_text("foo bar foo", encoding="utf-8")
    res = EditFileTool().execute({"path": str(f), "old": "foo", "new": "baz"})
    assert res.success is True
    assert f.read_text(encoding="utf-8") == "baz bar baz"


def test_edit_file_old_not_found(tmp_path: Path) -> None:
    f = tmp_path / "e.txt"
    f.write_text("nothing here", encoding="utf-8")
    res = EditFileTool().execute({"path": str(f), "old": "absent", "new": "x"})
    assert res.success is False
    assert "not found" in (res.error or "")


# --- run_tests (PLAN T2.1 ⑤) ----------------------------------------------


def _write_sample_tests(dirpath: Path) -> Path:
    f = dirpath / "test_sample.py"
    f.write_text(
        textwrap.dedent(
            """
            def test_passes():
                assert 1 + 1 == 2

            def test_fails():
                assert 1 + 1 == 3
            """
        ),
        encoding="utf-8",
    )
    return f


def test_run_tests_returns_structured_result(tmp_path: Path) -> None:
    """PLAN T2.1 ⑤ — structured result with correct counts."""
    f = _write_sample_tests(tmp_path)
    res = RunTestsTool().execute({"path": str(f)})
    assert res.success is False  # one test fails
    summary = json.loads(res.output)
    assert summary["total"] == 2
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["errors"] == 0
    assert "raw_stdout" in summary


def test_parse_junitxml_handles_suites_root() -> None:
    xml = (
        '<?xml version="1.0"?>'
        '<testsuites><testsuite name="s" tests="3" failures="1" errors="0" skipped="1"/>'
        '</testsuites>'
    )
    path = os.path.join(os.path.dirname(__file__), "_tmp_junit.xml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(xml)
    try:
        counts = _parse_junitxml(path)
    finally:
        os.unlink(path)
    assert counts == {"total": 3, "passed": 1, "failed": 1, "errors": 0, "skipped": 1}


def test_run_tests_missing_path_returns_error(tmp_path: Path) -> None:
    res = RunTestsTool().execute({"path": str(tmp_path / "does_not_exist.py")})
    # pytest exits non-zero / no junit produced — surface as a failure
    assert res.success is False


# --- search_files / search_content ----------------------------------------


def test_search_files_glob(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    (tmp_path / "b.txt").write_text("x", encoding="utf-8")
    res = SearchFilesTool().execute({"pattern": "*.py", "path": str(tmp_path)})
    assert res.success is True
    found = json.loads(res.output)
    assert any(p.endswith("a.py") for p in found)
    assert not any(p.endswith("b.txt") for p in found)


def test_search_content_finds_match(tmp_path: Path) -> None:
    f = tmp_path / "c.py"
    f.write_text("def foo():\n    return 42\n", encoding="utf-8")
    res = SearchContentTool().execute({"pattern": r"def \w+", "path": str(f)})
    assert res.success is True
    matches = json.loads(res.output)
    assert len(matches) == 1
    assert matches[0]["line"] == 1
    assert "def foo" in matches[0]["text"]


# --- delete_file -----------------------------------------------------------


def test_delete_file_removes_file_and_dir(tmp_path: Path) -> None:
    f = tmp_path / "to_delete.txt"
    f.write_text("x", encoding="utf-8")
    assert DeleteFileTool().execute({"path": str(f)}).success is True
    assert not f.exists()

    d = tmp_path / "subdir"
    d.mkdir()
    (d / "inner.txt").write_text("y", encoding="utf-8")
    assert DeleteFileTool().execute({"path": str(d)}).success is True
    assert not d.exists()


def test_delete_file_missing_returns_error(tmp_path: Path) -> None:
    res = DeleteFileTool().execute({"path": str(tmp_path / "nope")})
    assert res.success is False


# --- execute_command (DANGEROUS) -------------------------------------------


def test_execute_command_runs_echo() -> None:
    res = ExecuteCommandTool().execute({"command": "echo codingkit"})
    assert res.success is True
    assert "codingkit" in res.output


def test_execute_command_requires_command() -> None:
    assert ExecuteCommandTool().execute({}).success is False


# --- git_operation (DANGEROUS) --------------------------------------------


def test_git_operation_rejects_unsupported_op() -> None:
    res = GitOperationTool().execute({"operation": "push"})
    assert res.success is False
    assert "Unsupported" in (res.error or "")


def test_git_operation_status_in_tmp_repo(tmp_path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    import subprocess

    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
    res = GitOperationTool().execute({"operation": "status", "path": str(tmp_path)})
    assert res.success is True
