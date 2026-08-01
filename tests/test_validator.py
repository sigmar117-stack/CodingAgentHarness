"""Tests for the test-result validator (PLAN T3.1).

TDD: write a failing test first, then make it pass.
"""

from __future__ import annotations

import pytest

from codingkit.feedback.validator import (
    FailureDetail,
    TestResult,
    parse_junit_xml,
    parse_raw_output,
)


# ---------------------------------------------------------------------------
# Fixtures — hand-crafted JUnit XML strings
# ---------------------------------------------------------------------------

ALL_PASS_XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="3" failures="0" errors="0" skipped="0" time="0.123">
    <testcase classname="test_math" name="test_add" time="0.001" />
    <testcase classname="test_math" name="test_sub" time="0.002" />
    <testcase classname="test_math" name="test_mul" time="0.003" />
  </testsuite>
</testsuites>"""

PARTIAL_FAIL_XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="4" failures="2" errors="0" skipped="0" time="0.456">
    <testcase classname="test_math" name="test_add" time="0.001" />
    <testcase classname="test_math" name="test_sub" time="0.002">
      <failure message="AssertionError: assert 1 == 2" type="AssertionError">
test_math.py:10: AssertionError: assert 1 == 2
      </failure>
    </testcase>
    <testcase classname="test_math" name="test_mul" time="0.003" />
    <testcase classname="test_math" name="test_div" time="0.004">
      <failure message="ValueError: division by zero" type="ValueError">
test_math.py:20: ValueError: division by zero
      </failure>
    </testcase>
  </testsuite>
</testsuites>"""

ERRORS_XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="2" failures="0" errors="1" skipped="0" time="0.100">
    <testcase classname="test_foo" name="test_ok" time="0.001" />
    <testcase classname="test_foo" name="test_error" time="0.002">
      <error message="RuntimeError: something went wrong" type="RuntimeError">
test_foo.py:15: RuntimeError: something went wrong
      </error>
    </testcase>
  </testsuite>
</testsuites>"""

SINGLE_TESTSUITE_XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="1" failures="1" errors="0" skipped="0" time="0.010">
  <testcase classname="test_single" name="test_fail" time="0.001">
    <failure message="TypeError: unsupported type" type="TypeError">
test_single.py:5: TypeError: unsupported type
    </failure>
  </testcase>
</testsuite>"""

MULTIPLE_TESTSUITES_XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="suite_a" tests="2" failures="1" errors="0" skipped="0" time="0.200">
    <testcase classname="suite_a" name="test_a1" time="0.001" />
    <testcase classname="suite_a" name="test_a2" time="0.002">
      <failure message="AssertionError: fail" type="AssertionError">
suite_a.py:10: AssertionError: fail
      </failure>
    </testcase>
  </testsuite>
  <testsuite name="suite_b" tests="1" failures="1" errors="0" skipped="0" time="0.100">
    <testcase classname="suite_b" name="test_b1" time="0.001">
      <failure message="IndexError: out of range" type="IndexError">
suite_b.py:5: IndexError: out of range
      </failure>
    </testcase>
  </testsuite>
</testsuites>"""


# ---------------------------------------------------------------------------
# Tests: parse_junit_xml
# ---------------------------------------------------------------------------


class TestParseJunitXmlAllPass:
    """传入全部通过的测试结果 → 断言 failed=0"""

    def test_all_pass_counts(self) -> None:
        result = parse_junit_xml(ALL_PASS_XML, raw_output="3 passed")
        assert result.total == 3
        assert result.passed == 3
        assert result.failed == 0
        assert result.errors == 0

    def test_all_pass_no_failures(self) -> None:
        result = parse_junit_xml(ALL_PASS_XML, raw_output="3 passed")
        assert result.failures == []


class TestParseJunitXmlPartialFail:
    """传入部分失败的测试结果 → 断言 failed>0 且 failures 列表正确"""

    def test_partial_fail_counts(self) -> None:
        result = parse_junit_xml(PARTIAL_FAIL_XML)
        assert result.total == 4
        assert result.passed == 2
        assert result.failed == 2
        assert result.errors == 0

    def test_partial_fail_failure_details(self) -> None:
        result = parse_junit_xml(PARTIAL_FAIL_XML)
        assert len(result.failures) == 2

        f1 = result.failures[0]
        assert f1.test_name == "test_math::test_sub"
        assert f1.error_type == "AssertionError"
        assert "assert 1 == 2" in f1.error_message

        f2 = result.failures[1]
        assert f2.test_name == "test_math::test_div"
        assert f2.error_type == "ValueError"
        assert "division by zero" in f2.error_message

    def test_partial_fail_traceback(self) -> None:
        result = parse_junit_xml(PARTIAL_FAIL_XML)
        f1 = result.failures[0]
        assert "test_math.py:10:" in f1.traceback


class TestParseJunitXmlErrors:
    """传入包含 errors 的测试结果"""

    def test_errors_counted(self) -> None:
        result = parse_junit_xml(ERRORS_XML)
        assert result.total == 2
        assert result.passed == 1
        assert result.failed == 0
        assert result.errors == 1

    def test_errors_in_failures_list(self) -> None:
        result = parse_junit_xml(ERRORS_XML)
        assert len(result.failures) == 1
        f1 = result.failures[0]
        assert f1.test_name == "test_foo::test_error"
        assert f1.error_type == "RuntimeError"
        assert "something went wrong" in f1.error_message

    def test_error_traceback(self) -> None:
        result = parse_junit_xml(ERRORS_XML)
        assert "test_foo.py:15:" in result.failures[0].traceback


class TestParseJunitXmlSingleTestsuite:
    """传入只有一个 <testsuite> 根元素（无 <testsuites> 包装）的 XML"""

    def test_single_testsuite_counts(self) -> None:
        result = parse_junit_xml(SINGLE_TESTSUITE_XML)
        assert result.total == 1
        assert result.failed == 1

    def test_single_testsuite_failure_detail(self) -> None:
        result = parse_junit_xml(SINGLE_TESTSUITE_XML)
        assert len(result.failures) == 1
        assert result.failures[0].error_type == "TypeError"
        assert "unsupported type" in result.failures[0].error_message


class TestParseJunitXmlMultipleTestsuites:
    """传入多个 <testsuite> 的 XML"""

    def test_multiple_suites_totals(self) -> None:
        result = parse_junit_xml(MULTIPLE_TESTSUITES_XML)
        assert result.total == 3
        assert result.failed == 2
        assert result.passed == 1

    def test_multiple_suites_failures(self) -> None:
        result = parse_junit_xml(MULTIPLE_TESTSUITES_XML)
        assert len(result.failures) == 2
        assert result.failures[0].error_type == "AssertionError"
        assert result.failures[1].error_type == "IndexError"


class TestParseJunitXmlEmpty:
    """传入空输出 → 标记为未知错误"""

    def test_empty_xml(self) -> None:
        result = parse_junit_xml("", raw_output="")
        assert result.total == 0
        assert result.passed == 0
        assert result.failed == 1
        assert result.errors == 0
        assert len(result.failures) == 1
        assert result.failures[0].error_type == "UnknownError"
        assert "empty" in result.failures[0].error_message.lower()

    def test_malformed_xml(self) -> None:
        result = parse_junit_xml("<not xml>>>", raw_output="garbage output")
        assert result.total == 0
        assert result.failed == 1
        assert len(result.failures) == 1
        assert result.failures[0].error_type == "UnknownError"

    def test_no_testsuite_element(self) -> None:
        result = parse_junit_xml("<root><foo /></root>", raw_output="")
        assert result.total == 0


class TestParseJunitXmlRawOutput:
    """raw_output 字段被正确传递"""

    def test_raw_output_preserved(self) -> None:
        raw = "some raw output text"
        result = parse_junit_xml(ALL_PASS_XML, raw_output=raw)
        assert result.raw_output == raw

    def test_raw_output_default_empty(self) -> None:
        result = parse_junit_xml(ALL_PASS_XML)
        assert result.raw_output == ""


# ---------------------------------------------------------------------------
# Tests: parse_raw_output
# ---------------------------------------------------------------------------


class TestParseRawOutputFailure:
    """从原始输出中提取失败信息"""

    def test_parse_raw_output_failure_details(self) -> None:
        result = parse_raw_output(RAW_OUTPUT_FAILURE)
        assert len(result.failures) >= 1

    def test_parse_raw_output_all_pass(self) -> None:
        result = parse_raw_output(RAW_OUTPUT_ALL_PASS)
        assert result.failed == 0
        assert result.errors == 0


class TestParseRawOutputEmpty:
    """传入空输出 → 标记为未知错误"""

    def test_empty_output(self) -> None:
        result = parse_raw_output(RAW_OUTPUT_EMPTY)
        assert result.total == 0
        assert result.failed == 1
        assert len(result.failures) == 1
        assert result.failures[0].error_type == "UnknownError"
        assert "unknown" in result.failures[0].error_message.lower()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_parse_junit_xml_none(self) -> None:
        """传入 None 作为 xml_content 应安全处理"""
        result = parse_junit_xml(None)  # type: ignore[arg-type]
        assert result.total == 0
        assert result.failed == 1
        assert result.failures[0].error_type == "UnknownError"

    def test_parse_raw_output_none(self) -> None:
        """传入 None 作为 raw_output 应安全处理"""
        result = parse_raw_output(None)  # type: ignore[arg-type]
        assert result.total == 0
        assert result.failed == 1

    def test_failure_detail_creation(self) -> None:
        """FailureDetail 数据类应能直接构造"""
        fd = FailureDetail(
            test_name="test_foo",
            error_type="ValueError",
            error_message="bad value",
            traceback="traceback here",
        )
        assert fd.test_name == "test_foo"
        assert fd.error_type == "ValueError"
        assert fd.error_message == "bad value"
        assert fd.traceback == "traceback here"

    def test_test_result_creation(self) -> None:
        """TestResult 数据类应能直接构造"""
        fd = FailureDetail(
            test_name="test_foo",
            error_type="ValueError",
            error_message="bad value",
            traceback="",
        )
        tr = TestResult(
            total=10,
            passed=8,
            failed=1,
            errors=1,
            failures=[fd],
            raw_output="output",
        )
        assert tr.total == 10
        assert tr.passed == 8
        assert tr.failed == 1
        assert tr.errors == 1
        assert len(tr.failures) == 1
        assert tr.raw_output == "output"


# Raw output fixture strings (defined at module level for test access)
RAW_OUTPUT_FAILURE = """_____________________________ test_fail _________________________________
def test_fail():
>       assert 1 == 2
E       assert 1 == 2

test_math.py:10: AssertionError
_____________________________ test_error ________________________________
def test_error():
>       raise RuntimeError("boom")
E       RuntimeError: boom

test_foo.py:15: RuntimeError
=========================== short test summary info ============================
FAILED test_math.py::test_fail - AssertionError: assert 1 == 2
FAILED test_foo.py::test_error - RuntimeError: boom
1 passed, 2 failed in 0.12s"""

RAW_OUTPUT_ALL_PASS = """============================= test session starts =============================
collected 3 items
test_math.py ...                                                       [100%]
============================== 3 passed in 0.01s =============================="""

RAW_OUTPUT_EMPTY = ""


# ---------------------------------------------------------------------------
# Supplementary edge-case tests (T7.1)
# ---------------------------------------------------------------------------


class TestParseRawOutputEmptyString:
    """Empty string input to parse_raw_output."""

    def test_empty_string_returns_zero_total(self) -> None:
        """Empty string → TestResult with total=0."""
        result = parse_raw_output("")
        assert result.total == 0
        assert result.passed == 0
        assert result.failed == 1  # One unknown error
        assert len(result.failures) == 1

    def test_empty_string_unknown_error_type(self) -> None:
        """Empty string → UnknownError failure detail."""
        result = parse_raw_output("")
        assert result.failures[0].error_type == "UnknownError"


class TestParseJunitXmlNoTestCases:
    """JUnit XML with no test cases."""

    NO_CASES_XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="0" failures="0" errors="0" skipped="0" time="0.000">
  </testsuite>
</testsuites>"""

    def test_no_test_cases_parses_to_zero(self) -> None:
        """JUnit XML with no test cases → total=0."""
        result = parse_junit_xml(self.NO_CASES_XML, raw_output="")
        assert result.total == 0
        assert result.passed == 0
        assert result.failed == 0
        assert result.errors == 0
        assert result.failures == []

    def test_no_test_cases_empty_suite_element(self) -> None:
        """<testsuite> with no <testcase> children → 0 tests."""
        xml = '<?xml version="1.0" ?><testsuite name="pytest" tests="0" failures="0" errors="0"></testsuite>'
        result = parse_junit_xml(xml)
        assert result.total == 0
        assert result.failures == []