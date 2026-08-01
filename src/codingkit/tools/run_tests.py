"""run_tests tool (PLAN T2.1).

Runs pytest with the built-in ``--junitxml`` option (no extra dependency) and
returns a lightweight structured summary as JSON inside ``ToolResult.output``:
``{"total","passed","failed","errors","skipped","raw_stdout","raw_stderr"}``.

This is deliberately lighter than the full ``TestResult`` model — the feedback
loop's validator (PLAN T3.1) does the detailed ``FailureDetail`` extraction
(both JSON-report and junitxml). The two layers meet at this boundary.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from typing import Any

from codingkit.tools.base import RiskLevel, Tool, ToolResult

_DEFAULT_TIMEOUT = 300


def _parse_junitxml(path: str) -> dict[str, int]:
    """Extract test counts from a JUnit XML report (testsuite or testsuites)."""
    tree = ET.parse(path)
    root = tree.getroot()

    suites: list[ET.Element] = []
    if root.tag == "testsuites":
        suites = list(root.findall("testsuite"))
    elif root.tag == "testsuite":
        suites = [root]
    else:
        suites = list(root.iter("testsuite"))

    total = failed = errors = skipped = 0
    for suite in suites:
        total += int(suite.get("tests", 0))
        failed += int(suite.get("failures", 0))
        errors += int(suite.get("errors", 0))
        skipped += int(suite.get("skipped", 0))
    passed = max(total - failed - errors - skipped, 0)
    return {"total": total, "passed": passed, "failed": failed, "errors": errors, "skipped": skipped}


class RunTestsTool(Tool):
    name = "run_tests"
    description = "Run the pytest test suite and return a structured summary."
    risk_level = RiskLevel.NORMAL

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Test path (file or dir). Defaults to current dir."},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 300)."},
            },
            "required": [],
        }

    def execute(self, params: dict[str, Any]) -> ToolResult:
        path = params.get("path") or "."
        timeout = params.get("timeout", _DEFAULT_TIMEOUT)

        tmp_fd, tmp_name = tempfile.mkstemp(suffix=".xml")
        os.close(tmp_fd)

        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", path, f"--junitxml={tmp_name}", "-q"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            summary = _parse_junitxml(tmp_name)
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, output="", error=f"Tests timed out after {timeout}s")
        except (ET.ParseError, OSError, FileNotFoundError) as exc:
            return ToolResult(success=False, output="", error=f"Could not run/parse tests: {exc}")
        finally:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass

        summary["raw_stdout"] = (proc.stdout or "")[-2000:]
        summary["raw_stderr"] = (proc.stderr or "")[-2000:]
        summary["exit_code"] = proc.returncode

        # Success requires: tests actually ran, none failed/errored, and pytest
        # exited 0. (Exit code 5 == no tests collected; we treat that as a
        # failure — the agent asked for tests and got none.)
        no_tests = summary["total"] == 0
        success = (
            summary["failed"] == 0
            and summary["errors"] == 0
            and not no_tests
            and proc.returncode == 0
        )
        if no_tests:
            err = "no tests collected"
        else:
            err = None if success else f"{summary['failed']} failed, {summary['errors']} errors"
        return ToolResult(success=success, output=json.dumps(summary, ensure_ascii=False), error=err)
