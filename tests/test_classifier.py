"""Tests for the failure classifier (PLAN T3.2).

TDD: write a failing test first, then make it pass.

The classifier consumes ``FailureDetail`` objects produced by the validator
(T3.1) and maps each to one of 8 ``FailureCategory`` values (plus
``UNCLASSIFIED``) via a keyword/pattern rule engine with a fixed priority.
"""

from __future__ import annotations

import pytest

from codingkit.feedback.classifier import (
    ClassificationResult,
    FailureCategory,
    classify,
    classify_failure,
)
from codingkit.feedback.validator import FailureDetail, TestResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _failure(error_type: str = "", message: str = "", traceback: str = "") -> FailureDetail:
    """Build a ``FailureDetail`` with the given error fields."""
    return FailureDetail(
        test_name="test_dummy",
        error_type=error_type,
        error_message=message,
        traceback=traceback,
    )


# ---------------------------------------------------------------------------
# 8-category coverage (PLAN T3.2 verification ⑤)
# ---------------------------------------------------------------------------


class TestCompileError:
    """编译错误 — SyntaxError / IndentationError / NameError"""

    @pytest.mark.parametrize(
        "error_type,message",
        [
            ("SyntaxError", "invalid syntax"),
            ("IndentationError", "expected an indented block"),
            ("NameError", "name 'foo' is not defined"),
        ],
    )
    def test_compile_error(self, error_type: str, message: str) -> None:
        result = classify_failure(_failure(error_type, message))
        assert result.category == FailureCategory.COMPILE_ERROR
        assert 0.0 < result.confidence <= 1.0

    def test_compile_error_from_traceback(self) -> None:
        """关键词出现在 traceback 中也应被识别"""
        fd = _failure(traceback="file.py:3: SyntaxError: invalid syntax")
        assert classify_failure(fd).category == FailureCategory.COMPILE_ERROR


class TestAssertionError:
    """断言失败 — AssertionError / assert 语句"""

    def test_assertion_error(self) -> None:
        result = classify_failure(_failure("AssertionError", "expected 5, got 4"))
        assert result.category == FailureCategory.ASSERTION_ERROR

    def test_bare_assert_statement(self) -> None:
        """仅含 assert 关键词也应识别为断言失败"""
        fd = _failure(traceback="E       assert 1 == 2")
        assert classify_failure(fd).category == FailureCategory.ASSERTION_ERROR


class TestTimeout:
    """超时 — TimeoutError / timed out"""

    @pytest.mark.parametrize(
        "error_type,message",
        [
            ("TimeoutError", "test timed out after 30s"),
            ("", "DistributedScheduler: task timed out"),
        ],
    )
    def test_timeout(self, error_type: str, message: str) -> None:
        assert classify_failure(_failure(error_type, message)).category == FailureCategory.TIMEOUT


class TestEnvironmentError:
    """环境问题 — ModuleNotFoundError"""

    def test_module_not_found(self) -> None:
        result = classify_failure(
            _failure("ModuleNotFoundError", "No module named 'numpy'")
        )
        assert result.category == FailureCategory.ENVIRONMENT_ERROR


class TestTypeError:
    """类型错误 — TypeError"""

    def test_type_error(self) -> None:
        result = classify_failure(_failure("TypeError", "unsupported operand type(s)"))
        assert result.category == FailureCategory.TYPE_ERROR


class TestImportError:
    """Import 错误 — ImportError（非 ModuleNotFoundError 子类）"""

    def test_import_error(self) -> None:
        result = classify_failure(_failure("ImportError", "cannot import name 'X'"))
        assert result.category == FailureCategory.IMPORT_ERROR

    def test_import_error_not_environment(self) -> None:
        """普通 ImportError 应分类为 IMPORT_ERROR，而非 ENVIRONMENT_ERROR"""
        result = classify_failure(_failure("ImportError", "cannot import name 'foo'"))
        assert result.category == FailureCategory.IMPORT_ERROR
        assert result.category != FailureCategory.ENVIRONMENT_ERROR


class TestBoundaryError:
    """边界条件遗漏 — IndexError / KeyError / ValueError"""

    @pytest.mark.parametrize(
        "error_type",
        ["IndexError", "KeyError", "ValueError"],
    )
    def test_boundary_error(self, error_type: str) -> None:
        result = classify_failure(_failure(error_type, "list index out of range"))
        assert result.category == FailureCategory.BOUNDARY_ERROR


class TestInfiniteLoop:
    """死循环/资源耗尽 — MemoryError / RecursionError / OOM"""

    @pytest.mark.parametrize(
        "error_type,message",
        [
            ("RecursionError", "maximum recursion depth exceeded"),
            ("MemoryError", "out of memory"),
            ("", "OOMError: GPU out of memory (OOM)"),
        ],
    )
    def test_infinite_loop(self, error_type: str, message: str) -> None:
        assert (
            classify_failure(_failure(error_type, message)).category
            == FailureCategory.INFINITE_LOOP
        )


# ---------------------------------------------------------------------------
# PLAN T3.2 verification cases ①–④
# ---------------------------------------------------------------------------


class TestPlanVerificationCases:
    """PLAN T3.2 验证步骤中的具体示例"""

    def test_case1_syntax_error(self) -> None:
        result = classify_failure(_failure("SyntaxError", "invalid syntax"))
        assert result.category == FailureCategory.COMPILE_ERROR

    def test_case2_assertion_error(self) -> None:
        result = classify_failure(_failure("AssertionError", "expected 5, got 4"))
        assert result.category == FailureCategory.ASSERTION_ERROR

    def test_case3_module_not_found(self) -> None:
        result = classify_failure(_failure("ModuleNotFoundError", "No module named 'numpy'"))
        assert result.category == FailureCategory.ENVIRONMENT_ERROR

    def test_case4_index_error(self) -> None:
        result = classify_failure(_failure("IndexError", "list index out of range"))
        assert result.category == FailureCategory.BOUNDARY_ERROR


# ---------------------------------------------------------------------------
# UNCLASSIFIED + edge cases (PLAN T3.2 verification ⑥)
# ---------------------------------------------------------------------------


class TestUnclassified:
    """无法匹配任何已知模式 → UNCLASSIFIED"""

    def test_unclassified_runtime_error(self) -> None:
        result = classify_failure(_failure("RuntimeError", "something went wrong"))
        assert result.category == FailureCategory.UNCLASSIFIED
        assert result.confidence == 0.0

    def test_unclassified_empty(self) -> None:
        result = classify_failure(_failure())
        assert result.category == FailureCategory.UNCLASSIFIED
        assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# Priority: multiple matches → highest priority wins (SPEC §3.3.2)
# Priority: COMPILE > TYPE > IMPORT > BOUNDARY > ASSERTION > INFINITE_LOOP
#           > TIMEOUT > ENVIRONMENT
# ---------------------------------------------------------------------------


class TestPriority:
    def test_compile_beats_assertion(self) -> None:
        """SyntaxError + AssertionError 同时出现 → COMPILE_ERROR（更高优先级）"""
        fd = _failure(
            error_type="SyntaxError",
            traceback="AssertionError: assert 1 == 2",
        )
        assert classify_failure(fd).category == FailureCategory.COMPILE_ERROR

    def test_type_beats_boundary(self) -> None:
        """TypeError + ValueError 同时出现 → TYPE_ERROR"""
        fd = _failure(
            error_type="TypeError",
            traceback="ValueError: division by zero",
        )
        assert classify_failure(fd).category == FailureCategory.TYPE_ERROR

    def test_import_beats_environment(self) -> None:
        """普通 ImportError 同时匹配 IMPORT 与 ENVIRONMENT → IMPORT_ERROR"""
        fd = _failure("ImportError", "cannot import name 'X'")
        assert classify_failure(fd).category == FailureCategory.IMPORT_ERROR


# ---------------------------------------------------------------------------
# Confidence calculation
# ---------------------------------------------------------------------------


class TestConfidence:
    def test_partial_match_confidence(self) -> None:
        """置信度 = 匹配关键词数 / 该分类总关键词数，应 < 1.0 当部分匹配"""
        fd = _failure("SyntaxError", "invalid syntax")
        result = classify_failure(fd)
        # COMPILE_ERROR has 3 keywords (SyntaxError, IndentationError, NameError);
        # only 1 matched → confidence ≈ 1/3
        assert 0.0 < result.confidence <= 1.0
        assert result.confidence == pytest.approx(1 / 3, abs=0.01)

    def test_full_match_confidence(self) -> None:
        """同一文本中匹配全部关键词 → confidence == 1.0"""
        fd = _failure(
            error_type="SyntaxError",
            message="IndentationError near NameError",
        )
        result = classify_failure(fd)
        assert result.category == FailureCategory.COMPILE_ERROR
        assert result.confidence == 1.0


# ---------------------------------------------------------------------------
# ClassificationResult fields (summary / key_info)
# ---------------------------------------------------------------------------


class TestResultFields:
    def test_summary_and_key_info_populated(self) -> None:
        fd = _failure("SyntaxError", "invalid syntax")
        result = classify_failure(fd)
        assert isinstance(result, ClassificationResult)
        assert result.summary  # non-empty
        assert result.key_info  # non-empty
        assert "SyntaxError" in result.key_info or "SyntaxError" in result.summary

    def test_unclassified_summary(self) -> None:
        result = classify_failure(_failure("RuntimeError", "boom"))
        assert result.category == FailureCategory.UNCLASSIFIED
        assert result.summary  # still provides a readable summary


# ---------------------------------------------------------------------------
# TestResult-level entry point
# ---------------------------------------------------------------------------


class TestClassifyTestResult:
    def test_classify_multiple_failures(self) -> None:
        tr = TestResult(
            total=3,
            passed=1,
            failed=2,
            errors=0,
            failures=[
                _failure("SyntaxError", "invalid syntax"),
                _failure("AssertionError", "assert 1 == 2"),
            ],
        )
        results = classify(tr)
        assert len(results) == 2
        assert results[0].category == FailureCategory.COMPILE_ERROR
        assert results[1].category == FailureCategory.ASSERTION_ERROR

    def test_classify_no_failures(self) -> None:
        tr = TestResult(total=3, passed=3, failed=0, errors=0, failures=[])
        assert classify(tr) == []

    def test_classify_unknown_error_unclassified(self) -> None:
        """validator 标记的 UnknownError 应被分类为 UNCLASSIFIED"""
        tr = TestResult(
            total=0,
            passed=0,
            failed=1,
            errors=0,
            failures=[FailureDetail(test_name="(unknown)", error_type="UnknownError",
                                   error_message="Unknown error — output was empty")],
        )
        results = classify(tr)
        assert len(results) == 1
        assert results[0].category == FailureCategory.UNCLASSIFIED
