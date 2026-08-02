"""Feedback loop: validator, classifier, correction strategy engine, ingester (PLAN Layer 3)."""

from codingkit.feedback.classifier import (
    ClassificationResult,
    FailureCategory,
    classify,
    classify_failure,
)
from codingkit.feedback.correction_state import (
    CorrectionAttempt,
    CorrectionContext,
    CorrectionState,
)
from codingkit.feedback.ingester import FeedbackContext, build_feedback_prompt
from codingkit.feedback.strategy_engine import STRATEGY_CHAINS, StrategyEngine, get_strategy_chain
from codingkit.feedback.validator import (
    FailureDetail,
    TestResult,
    parse_junit_xml,
    parse_raw_output,
)

__all__ = [
    # T3.1 — Validator
    "FailureDetail",
    "TestResult",
    "parse_junit_xml",
    "parse_raw_output",
    # T3.2 — Classifier
    "ClassificationResult",
    "FailureCategory",
    "classify",
    "classify_failure",
    # T3.3 — Strategy Engine
    "CorrectionAttempt",
    "CorrectionContext",
    "CorrectionState",
    "STRATEGY_CHAINS",
    "StrategyEngine",
    "get_strategy_chain",
    # T3.4 — Ingester
    "FeedbackContext",
    "build_feedback_prompt",
]
