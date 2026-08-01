"""Correction state machine — data classes and state enum (PLAN T3.3).

This module defines the core types used by the strategy engine:

* ``CorrectionState`` — lifecycle states of the correction process.
* ``CorrectionAttempt`` — a single attempt with a strategy and its outcome.
* ``CorrectionContext`` — the full context passed through the state machine,
  including session identification, attempt history, and classification.

The state machine itself lives in ``strategy_engine.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from codingkit.feedback.classifier import (
    ClassificationResult,
    FailureCategory,
)


__all__ = [
    "CorrectionState",
    "CorrectionAttempt",
    "CorrectionContext",
]


# ---------------------------------------------------------------------------
# CorrectionState
# ---------------------------------------------------------------------------


class CorrectionState(Enum):
    """Lifecycle states of the correction process.

    Transitions::

        ATTEMPTING ──→ SUCCEEDED
            │
            ├──→ STRATEGY_EXHAUSTED  (all strategies tried)
            ├──→ MAX_RETRIES_REACHED (total attempts ≥ 6)
            │
            └──→ CANCELLED           (user cancelled)
                         │
                         └──→ USER_INTERVENTION  (paused for user input)
    """

    ATTEMPTING = "attempting"
    STRATEGY_EXHAUSTED = "strategy_exhausted"
    MAX_RETRIES_REACHED = "max_retries_reached"
    USER_INTERVENTION = "user_intervention"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# CorrectionAttempt
# ---------------------------------------------------------------------------


@dataclass
class CorrectionAttempt:
    """A single correction attempt with a strategy and its outcome."""

    __test__ = False  # prevent pytest from collecting this as a test class

    strategy: str
    result: str = ""
    success: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# CorrectionContext
# ---------------------------------------------------------------------------


@dataclass
class CorrectionContext:
    """Full context for the correction state machine.

    This object is passed through every state-machine transition and is
    mutated in place as the correction process progresses.
    """

    __test__ = False  # prevent pytest from collecting this as a test class

    session_id: str = ""
    turn_id: str = ""
    attempt_number: int = 0
    current_strategy_index: int = 0
    strategy_chain: List[str] = field(default_factory=list)
    history: List[CorrectionAttempt] = field(default_factory=list)
    classification: ClassificationResult = field(default_factory=ClassificationResult)
    state: CorrectionState = CorrectionState.ATTEMPTING
    consecutive_failures: int = 0  # failures *within* the current strategy