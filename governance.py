"""
governance.py — Governance observability layer for NOUS.

Read-only inspection of policies and intervention audit events.
No codegen dependency — operates on parsed programs and JSONL event logs.
"""
# __governance_dashboard_v1__
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("nous.governance")

# __governance_signal_str_v1__
def _signal_to_str(expr: Any) -> str:
    """Convert a policy signal AST dict to human-readable string."""
    if expr is None:
        return ""
    if isinstance(expr, str):
        return expr
    if isinstance(expr, (int, float, bool)):
        return str(expr)
    if isinstance(expr, dict):
        kind = expr.get("kind", "")
        if kind == "binop":
            left = _signal_to_str(expr.get("left"))
            right = _signal_to_str(expr.get("right"))
            op = expr.get("op", "?")
            return f"{left} {op} {right}"
        elif kind == "not":
            return f"not ({_signal_to_str(expr.get('operand'))})"
        elif kind == "neg":
            return f"-{_signal_to_str(expr.get('operand'))}"
        elif kind == "attr":
            obj = _signal_to_str(expr.get("object"))
            attr = expr.get("attr", "?")
            return f"{obj}.{attr}"
        elif kind == "call":
            fn = _signal_to_str(expr.get("func"))
            args = ", ".join(_signal_to_str(a) for a in expr.get("args", []))
            return f"{fn}({args})"
        elif kind == "contains":
            left = _signal_to_str(expr.get("left"))
            right = _signal_to_str(expr.get("right"))
            return f"{left} contains {right}"
        return str(expr)
    return str(expr)



@dataclass(frozen=True)
class PolicyInfo:
    name: str
    kind: str
    signal: str
    weight: float
    action: str
    source_file: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "signal": self.signal,
            "weight": self.weight,
            "action": self.action,
            "source_file": self.source_file,
        }


@dataclass(frozen=True)
class InterventionRecord:
    seq_id: int
    soul: str
    cycle: int
    timestamp: float
    action: str
    policies: tuple[str, ...]
    score: float
    reasons: tuple[str, ...]
    event_kind: str
    raw_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq_id": self.seq_id,
            "soul": self.soul,
            "cycle": self.cycle,
            "timestamp": self.timestamp,
            "action": self.action,
            "policies": list(self.policies),
            "score": self.score,
            "reasons": list(self.reasons),
            "event_kind": self.event_kind,
        }


@dataclass
class GovernanceStats:
    total_events: int = 0
    total_interventions: int = 0
    by_action: dict[str, int] = field(default_factory=dict)
    by_policy: dict[str, int] = field(default_factory=dict)
    by_soul: dict[str, int] = field(default_factory=dict)
    blocked_count: int = 0
    aborted_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_events": self.total_events,
            "total_interventions": self.total_interventions,
            "by_action": dict(self.by_action),
            "by_policy": dict(self.by_policy),
            "by_soul": dict(self.by_soul),
            "blocked_count": self.blocked_count,
            "aborted_count": self.aborted_count,
        }


class PolicyInspector:
    """Extract policy definitions from a parsed NousProgram."""

    @staticmethod
    def extract(program: Any, source_file: str = "") -> list[PolicyInfo]:
        policies: list[PolicyInfo] = []
        world = getattr(program, "world", None)
        if world is None:
            return policies
        world_policies = getattr(world, "policies", None)
        if not world_policies:
            return policies
        for p in world_policies:
            name = getattr(p, "name", "unknown")
            kind = getattr(p, "kind", "")
            signal = _signal_to_str(getattr(p, "signal", ""))
            weight = float(getattr(p, "weight", 0.0))
            action = getattr(p, "action", "log_only")
            policies.append(PolicyInfo(
                name=name,
                kind=kind,
                signal=signal,
                weight=weight,
                action=action,
                source_file=source_file,
            ))
        return policies

    @staticmethod
    def from_source(source: str, source_file: str = "") -> list[PolicyInfo]:
        try:
            from parser import parse_nous
            program = parse_nous(source)
            return PolicyInspector.extract(program, source_file=source_file)
        except Exception as exc:
            logger.error("failed to parse source for policy inspection: %s", exc)
            return []

    @staticmethod
    def from_file(path: str | Path) -> list[PolicyInfo]:
        p = Path(path)
        if not p.exists():
            logger.error("file not found: %s", p)
            return []
        source = p.read_text(encoding="utf-8")
        return PolicyInspector.from_source(source, source_file=str(p))


class GovernanceLog:
    """Read and filter governance.intervention events from a JSONL event log."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._events: list[dict[str, Any]] = []
        self._interventions: list[InterventionRecord] = []
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        if not self._path.exists():
            raise FileNotFoundError(f"event log not found: {self._path}")
        events: list[dict[str, Any]] = []
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        self._events = events
        self._interventions = []
        for ev in events:
            if ev.get("kind") == "governance.intervention":
                data = ev.get("data", {})
                self._interventions.append(InterventionRecord(
                    seq_id=int(ev.get("seq_id", -1)),
                    soul=str(ev.get("soul", "")),
                    cycle=int(ev.get("cycle", 0)),
                    timestamp=float(ev.get("timestamp", 0.0)),
                    action=str(data.get("action", "unknown")),
                    policies=tuple(data.get("policies", [])),
                    score=float(data.get("score", 0.0)),
                    reasons=tuple(data.get("reasons", [])),
                    event_kind=str(data.get("event_kind", "")),
                    raw_data=dict(data),
                ))
        self._loaded = True

    @property
    def total_events(self) -> int:
        self.load()
        return len(self._events)

    @property
    def interventions(self) -> list[InterventionRecord]:
        self.load()
        return list(self._interventions)

    def query(
        self,
        soul: Optional[str] = None,
        action: Optional[str] = None,
        since: Optional[float] = None,
        limit: int = 100,
    ) -> list[InterventionRecord]:
        self.load()
        results: list[InterventionRecord] = []
        for rec in self._interventions:
            if soul is not None and rec.soul != soul:
                continue
            if action is not None and rec.action != action:
                continue
            if since is not None and rec.timestamp < since:
                continue
            results.append(rec)
            if len(results) >= limit:
                break
        return results

    def stats(self) -> GovernanceStats:
        self.load()
        s = GovernanceStats(
            total_events=len(self._events),
            total_interventions=len(self._interventions),
        )
        for rec in self._interventions:
            s.by_action[rec.action] = s.by_action.get(rec.action, 0) + 1
            s.by_soul[rec.soul] = s.by_soul.get(rec.soul, 0) + 1
            for pname in rec.policies:
                s.by_policy[pname] = s.by_policy.get(pname, 0) + 1
            if rec.action == "block":
                s.blocked_count += 1
            elif rec.action == "abort_cycle":
                s.aborted_count += 1
        return s


def inspect_policies_cli(path: str) -> int:
    """CLI entry: print policies from a .nous file."""
    policies = PolicyInspector.from_file(path)
    if not policies:
        print(f"No policies found in {path}")
        return 0
    print(f"Policies in {path}:")
    print(f"{'Name':<25} {'Kind':<20} {'Action':<15} {'Weight':<8} Signal")
    print("-" * 90)
    for p in policies:
        print(f"{p.name:<25} {p.kind:<20} {p.action:<15} {p.weight:<8.1f} {p.signal}")
    return 0


def inspect_log_cli(path: str, soul: Optional[str] = None, limit: int = 50) -> int:
    """CLI entry: print intervention events from a JSONL log."""
    try:
        glog = GovernanceLog(path)
        records = glog.query(soul=soul, limit=limit)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        return 1
    if not records:
        print(f"No governance.intervention events found in {path}")
        return 0
    print(f"Intervention events in {path} ({len(records)} shown):")
    print(f"{'Seq':<6} {'Soul':<15} {'Cycle':<6} {'Action':<15} {'Score':<8} Policies")
    print("-" * 80)
    for r in records:
        pnames = ", ".join(r.policies)
        print(f"{r.seq_id:<6} {r.soul:<15} {r.cycle:<6} {r.action:<15} {r.score:<8.2f} {pnames}")
    return 0


def stats_log_cli(path: str) -> int:
    """CLI entry: print aggregated governance stats from a JSONL log."""
    try:
        glog = GovernanceLog(path)
        s = glog.stats()
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        return 1
    print(f"Governance stats for {path}:")
    print(f"  Total events:        {s.total_events}")
    print(f"  Total interventions: {s.total_interventions}")
    print(f"  Blocked:             {s.blocked_count}")
    print(f"  Aborted:             {s.aborted_count}")
    if s.by_action:
        print(f"\n  By action:")
        for act, cnt in sorted(s.by_action.items()):
            print(f"    {act:<20} {cnt}")
    if s.by_policy:
        print(f"\n  By policy:")
        for pol, cnt in sorted(s.by_policy.items()):
            print(f"    {pol:<25} {cnt}")
    if s.by_soul:
        print(f"\n  By soul:")
        for sl, cnt in sorted(s.by_soul.items()):
            print(f"    {sl:<20} {cnt}")
    return 0
