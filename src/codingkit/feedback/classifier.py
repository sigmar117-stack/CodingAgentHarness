"""Failure classifier (PLAN T3.2).

Rule-based classifier that maps a validator-produced ``FailureDetail`` to one
of 8 ``FailureCategory`` values (or ``UNCLASSIFIED``).  Categories, keywords,
and priority order follow SPEC §3.3.2 and the PLAN T3.2 verification steps.

Priority (highest → lowest):
    COMPILE > TYPE > IMPORT > BOUNDARY > ASSERTION > INFINITE_LOOP
    > TIMEOUT > ENVIRONMENT

When multiple categories match, the highest-priority one wins.  Confidence is
``matched_keyword_count / total_keyword_count`` for the winning category
(``0.0`` when unclassified).

Note on ImportError vs ModuleNotFoundError: ``ModuleNotFoundError`` is a
subclass of ``ImportError`` in Python, but the string ``"ModuleNotFoundError"``
does not contain the substring ``"ImportError"``.  Both the ENVIRONMENT and
IMPORT patterns therefore include ``"ImportError"``; a plain
``ImportError: cannot import name 'X'`` matches both, and IMPORT wins by
priority — matching the SPEC intent that ``ModuleNotFoundError`` (a missing
package) is an environment issue while a plain ``ImportError`` is a code-level
import problem.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List

from codingkit.feedback.validator import FailureDetail, TestResult


__all__ = [
    "FailureCategory",
    "ClassificationResult",
    "classify_failure",
    "classify",
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class FailureCategory(Enum):
    """The 8 failure categories plus an ``UNCLASSIFIED`` fallback."""

    COMPILE_ERROR = "compile_error"
    TYPE_ERROR = "type_error"
    IMPORT_ERROR = "import_error"
    BOUNDARY_ERROR = "boundary_error"
    ASSERTION_ERROR = "assertion_error"
    INFINITE_LOOP = "infinite_loop"
    TIMEOUT = "timeout"
    ENVIRONMENT_ERROR = "environment_error"
    UNCLASSIFIED = "unclassified"


@dataclass
class ClassificationResult:
    """Result of classifying a single failure."""

    __test__ = False  # prevent pytest from collecting this as a test class

    category: FailureCategory = FailureCategory.UNCLASSIFIED
    confidence: float = 0.0
    summary: str = ""
    key_info: str = ""


# ---------------------------------------------------------------------------
# Rule engine
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Rule:
    """A single classification rule: category + ordered keyword patterns."""

    category: FailureCategory
    patterns: tuple[str, ...]


# Categories ordered by priority (highest first).  Within a rule, ``patterns``
# is the full keyword set used for confidence calculation; a failure matches
# the rule when *any* pattern hits.  Patterns are matched case-sensitively as
# word boundaries to avoid spurious substrings (e.g. "TypeError" inside
# "SomeTypeError").
_RULES: tuple[_Rule, ...] = (
    _Rule(
        FailureCategory.COMPILE_ERROR,
        ("SyntaxError", "IndentationError", "NameError"),
    ),
    _Rule(
        FailureCategory.TYPE_ERROR,
        ("TypeError",),
    ),
    _Rule(
        # Plain "ImportError"; ModuleNotFoundError does NOT contain this
        # substring, so it falls through to ENVIRONMENT below.
        FailureCategory.IMPORT_ERROR,
        ("ImportError",),
    ),
    _Rule(
        FailureCategory.BOUNDARY_ERROR,
        ("IndexError", "KeyError", "ValueError"),
    ),
    _Rule(
        # Cover both the SPEC spelling ("AssertionError") and Python's real
        # built-in ("AssertionError"), plus bare assert statements.
        FailureCategory.ASSERTION_ERROR,
        ("AssertionError", "AssertionError", r"\bassert\b"),
    ),
    _Rule(
        FailureCategory.INFINITE_LOOP,
        ("MemoryError", "RecursionError", "OOM"),
    ),
    _Rule(
        FailureCategory.TIMEOUT,
        ("TimeoutError", "timed out", "timeout"),
    ),
    _Rule(
        # Environment issues: missing packages (ModuleNotFoundError) and the
        # generic ImportError (the latter also matches IMPORT above, but IMPORT
        # has higher priority so plain ImportError routes there; a bare
        # ModuleNotFoundError routes here).
        FailureCategory.ENVIRONMENT_ERROR,
        ("ModuleNotFoundError", "ImportError", "No module named"),
    ),
)


def _compile(pattern: str) -> re.Pattern[str]:
    """Compile a keyword/pattern into a case-sensitive regex.

    Literal exception names are anchored on word boundaries so that
    ``TypeError`` does not match ``MyTypeError``.
    """
    # Patterns that are already regex (start with a backslash) are compiled
    # verbatim; everything else is treated as a literal word-boundary match.
    if pattern.startswith("\\"):
        return re.compile(pattern)
    return re.compile(r"\b" + re.escape(pattern) + r"\b")


_COMPILED_RULES: tuple[tuple[_Rule, tuple[re.Pattern[str], ...]], ...] = tuple(
    (rule, tuple(_compile(p) for p in rule.patterns)) for rule in _RULES
)


def _search_text(failure: FailureDetail) -> str:
    """Combine all error fields into a single search string."""
    parts = [failure.error_type, failure.error_message, failure.traceback]
    return "\n".join(p for p in parts if p)


def _match_rule(
    text: str,
    compiled: tuple[re.Pattern[str], ...],
) -> tuple[bool, int]:
    """Return ``(any_match, matched_count)`` for a rule against ``text``."""
    matched = 0
    for pattern in compiled:
        if pattern.search(text):
            matched += 1
    return matched > 0, matched


def classify_failure(failure: FailureDetail) -> ClassificationResult:
    """Classify a single ``FailureDetail`` into a ``ClassificationResult``.

    Iterates rules in priority order; the first rule with ≥1 match wins.
    Confidence is ``matched / total`` for the winning rule.  If no rule
    matches, returns ``UNCLASSIFIED`` with confidence ``0.0``.
    """
    text = _search_text(failure)

    for rule, compiled in _COMPILED_RULES:
        any_match, matched = _match_rule(text, compiled)
        if not any_match:
            continue
        total = len(rule.patterns)
        confidence = matched / total if total else 1.0
        return ClassificationResult(
            category=rule.category,
            confidence=confidence,
            summary=_summary(rule.category, failure),
            key_info=_key_info(failure),
        )

    return ClassificationResult(
        category=FailureCategory.UNCLASSIFIED,
        confidence=0.0,
        summary=_summary(FailureCategory.UNCLASSIFIED, failure),
        key_info=_key_info(failure),
    )


def classify(test_result: TestResult) -> List[ClassificationResult]:
    """Classify every failure in a ``TestResult``.

    Returns one ``ClassificationResult`` per failure (empty list when there are
    no failures).  The order matches ``test_result.failures``.
    """
    return [classify_failure(f) for f in test_result.failures]


# ---------------------------------------------------------------------------
# Presentation helpers
# ---------------------------------------------------------------------------


_LABELS = {
    FailureCategory.COMPILE_ERROR: "Compile error",
    FailureCategory.TYPE_ERROR: "Type error",
    FailureCategory.IMPORT_ERROR: "Import error",
    FailureCategory.BOUNDARY_ERROR: "Boundary error",
    FailureCategory.ASSERTION_ERROR: "Assertion failure",
    FailureCategory.INFINITE_LOOP: "Infinite loop / resource exhaustion",
    FailureCategory.TIMEOUT: "Timeout",
    FailureCategory.ENVIRONMENT_ERROR: "Environment error",
    FailureCategory.UNCLASSIFIED: "Unclassified",
}


def _summary(category: FailureCategory, failure: FailureDetail) -> str:
    """One-line human-readable summary, e.g. ``Compile error: SyntaxError``."""
    label = _LABELS.get(category, "Unclassified")
    head = failure.error_type or "unknown"
    if failure.error_message:
        head = f"{head}: {failure.error_message.splitlines()[0]}"
    return f"{label} — {head}"


def _key_info(failure: FailureDetail) -> str:
    """The most informative single line: error_type + first message line."""
    if failure.error_type and failure.error_message:
        first = failure.error_message.splitlines()[0]
        return f"{failure.error_type}: {first}"
    if failure.error_type:
        return failure.error_type
    if failure.error_message:
        return failure.error_message.splitlines()[0]
    # Fall back to the first non-empty traceback line.
    for line in failure.traceback.splitlines():
        if line.strip():
            return line.strip()
    return "(no diagnostic information)"
