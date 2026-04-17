"""
intervention.py - NOUS Phase G Layer 3: Intervention primitive

# __intervention_engine_v1__

Runtime governance enforcement. Given a RiskEngine populated with
_POLICIES (Layer 2) or YAML rules (Layer 1), intercept every event
before it is appended to the EventStore and dispatch the policy
action (log_only / intervene / block / abort_cycle / inject_message).

Design:
  - Synchronous. Hot path must be cheap.
  - No-op when no rules loaded.
  - Raises explicit exceptions that the ReplayContext handles.
  - Emits a governance.intervention audit event on every triggering.

Actions (v4.7.0):
  log_only        -> audit event, pass
  intervene       -> audit event, pass (generic hook for dashboard/Layer 4)
  block           -> audit event, raise InterventionBlocked
  abort_cycle     -> audit event, raise InterventionAborted
  inject_message  -> audit event + warning, pass (stub for Layer 4)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from risk_engine import RiskEngine, RiskAssessment

logger = logging.getLogger(__name__)

_VALID_ACTIONS: frozenset[str] = frozenset({
    "log_only",
    "intervene",
    "block",
    "abort_cycle",
    "inject_message",
})


@dataclass(frozen=True)
class InterventionOutcome:
    """Result of running an event through InterventionEngine.check()."""
    triggered: bool
    action: str
    policy_names: tuple[str, ...]
    score: float
    reasons: tuple[str, ...]
    event_kind: str
    event_seq_id: int

    def to_audit_data(self) -> dict[str, Any]:
        """Serialise for governance.intervention event payload."""
        return {
            "action": self.action,
            "policies": list(self.policy_names),
            "score": self.score,
            "reasons": list(self.reasons),
            "triggering_event_kind": self.event_kind,
            "triggering_event_seq_id": self.event_seq_id,
        }


class InterventionError(Exception):
    """Base class for intervention-driven control flow."""

    def __init__(self, outcome: InterventionOutcome) -> None:
        super().__init__(
            f"intervention: action={outcome.action} "
            f"policies={outcome.policy_names} score={outcome.score:.3f}"
        )
        self.outcome: InterventionOutcome = outcome


class InterventionBlocked(InterventionError):
    """Raised when action=block. Event emission is halted."""
    pass


class InterventionAborted(InterventionError):
    """Raised when action=abort_cycle. Current soul cycle terminates."""
    pass


class InterventionEngine:
    """
    Wraps a RiskEngine + policy action map. Called for every event.

    Usage:
        engine = InterventionEngine(rules=_POLICIES, actions=_POLICY_ACTIONS)
        outcome = engine.check(event)   # may raise InterventionBlocked/Aborted
        # on log_only / intervene / inject_message: outcome.triggered can be True
        # but execution continues. Caller emits audit event via outcome.

    No-op mode: if rules is empty, check() returns a non-triggered outcome
    immediately. Zero overhead beyond one tuple length check.
    """

    def __init__(
        self,
        rules: Optional[list[Any]] = None,
        actions: Optional[dict[str, str]] = None,
    ) -> None:
        self._rules: list[Any] = list(rules) if rules else []
        self._actions: dict[str, str] = dict(actions) if actions else {}
        self._engine: Optional[RiskEngine] = None
        if self._rules:
            self._engine = RiskEngine(self._rules)

    @property
    def enabled(self) -> bool:
        return self._engine is not None

    def action_for(self, policy_name: str) -> str:
        """Return the action for a triggered policy. Defaults to log_only."""
        a = self._actions.get(policy_name, "log_only")
        if a not in _VALID_ACTIONS:
            logger.warning(
                "intervention: unknown action %r for policy %s, treating as log_only",
                a, policy_name,
            )
            return "log_only"
        return a

    @staticmethod
    def _resolve_action(triggered_actions: list[str]) -> str:
        """
        When multiple policies fire with different actions, pick the most
        severe. Order: abort_cycle > block > inject_message > intervene > log_only.
        """
        priority: dict[str, int] = {
            "abort_cycle": 4,
            "block": 3,
            "inject_message": 2,
            "intervene": 1,
            "log_only": 0,
        }
        if not triggered_actions:
            return "log_only"
        return max(triggered_actions, key=lambda a: priority.get(a, -1))

    def check(self, event: Any) -> InterventionOutcome:
        """
        Evaluate event against all policies. Returns outcome.
        Raises InterventionBlocked / InterventionAborted on severe actions.
        """
        if self._engine is None:
            return InterventionOutcome(
                triggered=False,
                action="log_only",
                policy_names=(),
                score=0.0,
                reasons=(),
                event_kind=getattr(event, "kind", ""),
                event_seq_id=int(getattr(event, "seq_id", 0)),
            )

        # __intervention_api_fix_v1__
        assessment: RiskAssessment = self._engine.assess(event)

        triggered_names: list[str] = list(assessment.triggered_rules)

        if not triggered_names:
            return InterventionOutcome(
                triggered=False,
                action="log_only",
                policy_names=(),
                score=float(assessment.score),
                reasons=(),
                event_kind=getattr(event, "kind", ""),
                event_seq_id=int(getattr(event, "seq_id", 0)),
            )

        per_policy_actions: list[str] = [
            self.action_for(name) for name in triggered_names
        ]
        resolved: str = self._resolve_action(per_policy_actions)

        reasoning_str: str = str(getattr(assessment, "reasoning", "") or "")
        reasons_tuple: tuple[str, ...] = (
            tuple(s.strip() for s in reasoning_str.split(";") if s.strip())
            if reasoning_str else ()
        )

        outcome = InterventionOutcome(
            triggered=True,
            action=resolved,
            policy_names=tuple(triggered_names),
            score=float(assessment.score),
            reasons=reasons_tuple,
            event_kind=getattr(event, "kind", ""),
            event_seq_id=int(getattr(event, "seq_id", 0)),
        )

        if resolved == "inject_message":
            logger.warning(
                "intervention: inject_message not yet implemented in v4.7.0; "
                "treating as log_only for policies=%s",
                triggered_names,
            )

        if resolved == "block":
            raise InterventionBlocked(outcome)
        if resolved == "abort_cycle":
            raise InterventionAborted(outcome)

        return outcome


__all__ = [
    "InterventionEngine",
    "InterventionOutcome",
    "InterventionError",
    "InterventionBlocked",
    "InterventionAborted",
]
