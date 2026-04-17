"""Governance event simulator.
__governance_simulator_v1__

Evaluates declared .nous policies against a synthetic event for
'what-if' analysis in the IDE Governance tab.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from governance import PolicyInspector


_SANDBOX_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "min": min,
    "max": max,
    "len": len,
    "round": round,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "True": True,
    "False": False,
    "None": None,
}


def _safe_eval(expr: str, namespace: dict[str, Any]) -> Any:
    """Evaluate expression in a restricted namespace. No builtins, no imports."""
    try:
        code = compile(expr, "<signal>", "eval")
    except SyntaxError as e:
        raise ValueError(f"signal syntax error: {e}") from e
    for n in code.co_names:
        if n.startswith("_"):
            raise ValueError(f"signal may not reference '{n}'")
    restricted_globals = {"__builtins__": _SANDBOX_BUILTINS}
    return eval(code, restricted_globals, namespace)  # noqa: S307


@dataclass(frozen=True)
class SimulationMatch:
    policy: str
    kind: str
    signal: str
    weight: float
    action: str
    fired: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "kind": self.kind,
            "signal": self.signal,
            "weight": self.weight,
            "action": self.action,
            "fired": self.fired,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class SimulationResult:
    event_kind: str
    event_data: dict[str, Any]
    policy_count: int
    matches: tuple[SimulationMatch, ...]

    @property
    def fired(self) -> tuple[SimulationMatch, ...]:
        return tuple(m for m in self.matches if m.fired)

    @property
    def skipped(self) -> tuple[SimulationMatch, ...]:
        return tuple(m for m in self.matches if not m.fired)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_kind": self.event_kind,
            "event_data": self.event_data,
            "policy_count": self.policy_count,
            "fired_count": len(self.fired),
            "skipped_count": len(self.skipped),
            "matches": [m.to_dict() for m in self.matches],
        }


def _build_namespace(event_kind: str, event_data: dict[str, Any]) -> dict[str, Any]:
    """Construct eval namespace: data fields as bare names + reserved."""
    data_fields: dict[str, Any] = {}
    if isinstance(event_data, dict):
        for k, v in event_data.items():
            if isinstance(k, str) and k.isidentifier() and not k.startswith("_"):
                data_fields[k] = v
    namespace: dict[str, Any] = {
        **data_fields,
        "kind": event_kind,
        "data": event_data,
    }
    return namespace


def simulate_event(
    source: str,
    event_kind: str,
    event_data: dict[str, Any] | None = None,
) -> SimulationResult:
    """Evaluate .nous policies against a synthetic event.

    Args:
        source: Raw .nous source code.
        event_kind: Simulated event kind (e.g. "llm.request", "memory.write").
        event_data: Event data dict whose fields become bare names in signal eval.

    Returns:
        SimulationResult with policy_count and per-policy match/reason.
    """
    if event_data is None:
        event_data = {}
    policies = PolicyInspector.from_source(source)
    namespace = _build_namespace(event_kind, event_data)
    matches: list[SimulationMatch] = []
    for p in policies:
        kind = p.kind or ""
        if kind and kind != event_kind:
            matches.append(SimulationMatch(
                policy=p.name,
                kind=kind,
                signal=p.signal or "",
                weight=float(p.weight),
                action=p.action or "log_only",
                fired=False,
                reason=f"kind mismatch (policy={kind!r}, event={event_kind!r})",
            ))
            continue
        signal = (p.signal or "").strip()
        if not signal:
            matches.append(SimulationMatch(
                policy=p.name,
                kind=kind,
                signal="",
                weight=float(p.weight),
                action=p.action or "log_only",
                fired=False,
                reason="empty signal",
            ))
            continue
        try:
            result = _safe_eval(signal, namespace)
            fired = bool(result)
            reason = f"signal evaluated to {result!r}"
        except NameError as exc:
            fired = False
            reason = f"undefined name: {exc}"
        except Exception as exc:
            fired = False
            reason = f"eval error: {type(exc).__name__}: {exc}"
        matches.append(SimulationMatch(
            policy=p.name,
            kind=kind,
            signal=signal,
            weight=float(p.weight),
            action=p.action or "log_only",
            fired=fired,
            reason=reason,
        ))
    return SimulationResult(
        event_kind=event_kind,
        event_data=dict(event_data),
        policy_count=len(policies),
        matches=tuple(matches),
    )
