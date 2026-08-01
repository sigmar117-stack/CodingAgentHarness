"""Test-result validator (PLAN T3.1).

Parses pytest JUnit XML output and extracts structured ``TestResult`` /
``FailureDetail`` objects.  Two entry points:

* ``parse_junit_xml(xml_content, raw_output="")`` — parse a JUnit XML string.
* ``parse_raw_output(output)`` — parse raw pytest stdout/stderr when no XML is
  available (fallback).

The T2.1 ``run_tests`` tool returns a lightweight summary dict; this module is
where the **full** ``FailureDetail`` extraction happens.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional


__all__ = [
    "FailureDetail",
    "TestResult",
    "parse_junit_xml",
    "parse_raw_output",
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FailureDetail:
    """Detailed information about a single test failure or error."""

    __test__ = False  # prevent pytest from collecting this as a test class

    test_name: str = ""
    error_type: str = ""
    error_message: str = ""
    traceback: str = ""


@dataclass
class TestResult:
    """Structured result of a test run."""

    __test__ = False  # prevent pytest from collecting this as a test class

    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    failures: List[FailureDetail] = field(default_factory=list)
    raw_output: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UNKNOWN_ERROR = "UnknownError"
_UNKNOWN_MSG = "Unknown error — output was empty or unparseable"


def _make_unknown_error(raw_output: str = "") -> TestResult:
    """Return a ``TestResult`` representing an unparseable / empty result."""
    return TestResult(
        total=0,
        passed=0,
        failed=1,
        errors=0,
        failures=[
            FailureDetail(
                test_name="(unknown)",
                error_type=_UNKNOWN_ERROR,
                error_message=_UNKNOWN_MSG if not raw_output else raw_output[:500],
                traceback=raw_output,
            )
        ],
        raw_output=raw_output,
    )


def _build_test_name(classname: str | None, name: str | None) -> str:
    """Build a human-readable test name from JUnit ``classname`` + ``name``."""
    cn = (classname or "").strip()
    nm = (name or "").strip()
    if cn and nm:
        return f"{cn}::{nm}"
    return nm or cn or "(unnamed)"


def _extract_failure_details(
    root: ET.Element,
) -> tuple[List[FailureDetail], int, int]:
    """Extract ``FailureDetail`` items from every ``<testcase>`` that has
    a ``<failure>`` or ``<error>`` child.

    Returns ``(failures, fail_count, error_count)``.
    """
    failures: list[FailureDetail] = []
    fail_count = 0
    error_count = 0

    for suite in root.iter("testsuite"):
        for case in suite.iter("testcase"):
            classname = case.get("classname")
            name = case.get("name")
            test_name = _build_test_name(classname, name)

            # <failure> elements
            for failure in case.findall("failure"):
                fail_count += 1
                error_type = failure.get("type", _UNKNOWN_ERROR)
                message = failure.get("message", "") or ""
                traceback = (failure.text or "").strip()
                failures.append(
                    FailureDetail(
                        test_name=test_name,
                        error_type=error_type,
                        error_message=message,
                        traceback=traceback,
                    )
                )

            # <error> elements (setup/teardown errors, etc.)
            for error in case.findall("error"):
                error_count += 1
                error_type = error.get("type", _UNKNOWN_ERROR)
                message = error.get("message", "") or ""
                traceback = (error.text or "").strip()
                failures.append(
                    FailureDetail(
                        test_name=test_name,
                        error_type=error_type,
                        error_message=message,
                        traceback=traceback,
                    )
                )

    return failures, fail_count, error_count


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_junit_xml(
    xml_content: str | None,
    raw_output: str = "",
) -> TestResult:
    """Parse a pytest JUnit XML string into a ``TestResult``.

    Args:
        xml_content: The XML content as a string, or ``None``/empty.
        raw_output: Optional raw stdout/stderr to preserve in the result.

    Returns:
        A ``TestResult`` populated from the XML data.
    """
    if not xml_content:
        return _make_unknown_error(raw_output)

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        return _make_unknown_error(raw_output)

    # Collect all <testsuite> elements (handle both <testsuites> and
    # bare <testsuite> root).
    suites: list[ET.Element] = []
    if root.tag == "testsuites":
        suites = list(root.findall("testsuite"))
    elif root.tag == "testsuite":
        suites = [root]
    else:
        # Unknown root element — try iterating for testsuites anyway
        suites = list(root.iter("testsuite"))

    if not suites:
        return _make_unknown_error(raw_output)

    total = 0
    failed_attr = 0
    errors_attr = 0

    for suite in suites:
        total += int(suite.get("tests", 0))
        failed_attr += int(suite.get("failures", 0))
        errors_attr += int(suite.get("errors", 0))

    failures, extracted_fails, extracted_errors = _extract_failure_details(root)

    # Use XML attribute counts for the summary numbers (they are the
    # authoritative source), but fall back to extraction counts if the
    # attributes are missing.
    fail_count = max(failed_attr, extracted_fails)
    error_count = max(errors_attr, extracted_errors)
    passed = max(total - fail_count - error_count, 0)

    return TestResult(
        total=total,
        passed=passed,
        failed=fail_count,
        errors=error_count,
        failures=failures,
        raw_output=raw_output,
    )


def parse_raw_output(output: str | None) -> TestResult:
    """Parse raw pytest stdout/stderr when no JUnit XML is available.

    This is a best-effort fallback that looks for:

    * The ``FAILED test_file.py::test_name - ErrorType: message`` summary line.
    * A final summary line like ``N passed, M failed in Xs``.

    Args:
        output: The raw text output, or ``None``/empty.

    Returns:
        A ``TestResult`` with as much detail as could be extracted.
    """
    if not output:
        return _make_unknown_error(output or "")

    # Count failures from the "FAILED ..." summary lines
    fail_pattern = re.compile(
        r"^FAILED\s+(\S+(?:::?\S+)?)\s+-\s+(.+)$", re.MULTILINE
    )
    failures: list[FailureDetail] = []
    for match in fail_pattern.finditer(output):
        test_name = match.group(1)
        error_info = match.group(2).strip()
        # error_info is typically "ErrorType: message"
        if ":" in error_info:
            error_type, _, error_message = error_info.partition(":")
            error_type = error_type.strip()
            error_message = error_message.strip()
        else:
            error_type = error_info
            error_message = ""
        failures.append(
            FailureDetail(
                test_name=test_name,
                error_type=error_type,
                error_message=error_message,
                traceback=output,
            )
        )

    # Try to parse the final summary line: "N passed, M failed in Xs"
    summary_pattern = re.compile(
        r"(\d+)\s+passed\s*(?:,\s*(\d+)\s+failed)?\s*(?:,\s*(\d+)\s+errors)?\s+in\s+",
        re.IGNORECASE,
    )
    summary_match = summary_pattern.search(output)

    if summary_match:
        passed = int(summary_match.group(1))
        failed = int(summary_match.group(2)) if summary_match.group(2) else 0
        errors = int(summary_match.group(3)) if summary_match.group(3) else 0
        total = passed + failed + errors
    else:
        # No structured summary found — use count of FAILED lines
        failed = len(failures)
        total = failed
        passed = 0
        errors = 0

    return TestResult(
        total=total,
        passed=passed,
        failed=failed,
        errors=errors,
        failures=failures,
        raw_output=output,
    )