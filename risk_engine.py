"""
risk_engine.py — NOUS runtime risk assessment over replay event logs.

Reads any replay log (JSONL from EventStore) and emits per-event risk
assessments using a configurable rule set. Integrates with the existing
deterministic replay infrastructure: every RiskAssessment is itself
reproducible because the inputs (the event log) are hash-chained.

Architecture:
    RiskRule       — dataclass: name, kind_filter, predicate, weight, window
    RiskAssessment — per-event result: seq_id, score in [0,1], triggered_rules
    RiskReport     — aggregate over a full log: events, assessments, summary
    RiskEngine     — stateless core with assess() and assess_log()

Predicate sandbox:
    Predicates are Python expressions evaluated against a restricted
    namespace containing:
      - event fields: seq_id, soul, cycle, kind, data
      - rolling stats (per soul): count, mean, std, recent (last N values)
      - helpers: abs, max, min, len, sum

# __risk_engine_v1__
"""
from __future__ import annotations

import json
import logging
import math
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

import yaml

from replay_store import Event

logger = logging.getLogger("nous.risk_engine")


# ───────────────────────────────────────────────────────────
# Data shapes
# ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RiskRule:
    """A single risk rule loaded from YAML config."""
    name: str
    description: str
    kind_filter: tuple[str, ...]
    predicate: str
    weight: float
    window: int = 0
    extract: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RiskRule":
        kf_raw = d.get("kind_filter", [])
        if isinstance(kf_raw, str):
            kf: tuple[str, ...] = (kf_raw,)
        else:
            kf = tuple(str(x) for x in kf_raw)
        return cls(
            name=str(d["name"]),
            description=str(d.get("description", "")),
            kind_filter=kf,
            predicate=str(d["predicate"]),
            weight=float(d.get("weight", 1.0)),
            window=int(d.get("window", 0)),
            extract=str(d.get("extract", "")),
        )


@dataclass(frozen=True)
class RiskAssessment:
    """Per-event risk result."""
    seq_id: int
    soul: str
    cycle: int
    kind: str
    score: float
    triggered_rules: tuple[str, ...]
    reasoning: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq_id": self.seq_id,
            "soul": self.soul,
            "cycle": self.cycle,
            "kind": self.kind,
            "score": round(self.score, 4),
            "triggered_rules": list(self.triggered_rules),
            "reasoning": self.reasoning,
        }


@dataclass
class RiskReport:
    """Aggregate risk report over a full event log."""
    log_path: str
    total_events: int = 0
    total_assessments: int = 0
    triggered_events: int = 0
    max_score: float = 0.0
    mean_score: float = 0.0
    rule_hits: dict[str, int] = field(default_factory=dict)
    assessments: list[RiskAssessment] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "log_path": self.log_path,
            "total_events": self.total_events,
            "total_assessments": self.total_assessments,
            "triggered_events": self.triggered_events,
            "max_score": round(self.max_score, 4),
            "mean_score": round(self.mean_score, 4),
            "rule_hits": dict(self.rule_hits),
            "assessments": [a.to_dict() for a in self.assessments],
            "errors": list(self.errors),
        }


# ───────────────────────────────────────────────────────────
# Sandbox
# ───────────────────────────────────────────────────────────

_SANDBOX_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "max": max,
    "min": min,
    "len": len,
    "sum": sum,
    "round": round,
    "float": float,
    "int": int,
    "str": str,
    "bool": bool,
    "True": True,
    "False": False,
    "None": None,
}


def _safe_eval(expr: str, namespace: dict[str, Any]) -> Any:
    """Evaluate expression in a restricted namespace. No builtins, no imports."""
    try:
        code = compile(expr, "<risk_rule>", "eval")
    except SyntaxError as e:
        raise ValueError(f"rule predicate syntax error: {e}") from e
    for name in code.co_names:
        if name.startswith("_"):
            raise ValueError(f"rule predicate may not reference '{name}'")
    restricted_globals = {"__builtins__": _SANDBOX_BUILTINS}
    return eval(code, restricted_globals, namespace)  # noqa: S307


# ───────────────────────────────────────────────────────────
# Engine
# ───────────────────────────────────────────────────────────

class RiskEngine:
    """Evaluate risk over replay events using configurable rules."""

    DEFAULT_RULES_PATH = Path(__file__).parent / "risk_rules.yaml"

    def __init__(self, rules: list[RiskRule]) -> None:
        self._rules: list[RiskRule] = list(rules)
        self._rolling: dict[tuple[str, str], deque[float]] = defaultdict(lambda: deque(maxlen=128))

    @classmethod
    def from_yaml(cls, path: Optional[Path] = None) -> "RiskEngine":
        p = path if path is not None else cls.DEFAULT_RULES_PATH
        if not p.exists():
            raise FileNotFoundError(f"risk rules config not found: {p}")
        with open(p, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        rules_raw = raw.get("rules", [])
        rules = [RiskRule.from_dict(r) for r in rules_raw]
        return cls(rules=rules)

    @property
    def rules(self) -> tuple[RiskRule, ...]:
        return tuple(self._rules)

    def _rolling_stats(self, soul: str, rule: RiskRule) -> dict[str, Any]:
        buf = self._rolling[(soul, rule.name)]
        values = list(buf)
        count = len(values)
        mean = sum(values) / count if count > 0 else 0.0
        if count >= 2:
            std = statistics.pstdev(values)
        else:
            std = 0.0
        return {"count": count, "mean": mean, "std": std, "recent": values}

    def _update_rolling(self, soul: str, rule: RiskRule, value: float) -> None:
        buf = self._rolling[(soul, rule.name)]
        if rule.window > 0 and buf.maxlen != rule.window:
            new_buf: deque[float] = deque(buf, maxlen=rule.window)
            self._rolling[(soul, rule.name)] = new_buf
            buf = new_buf
        buf.append(value)

    def assess(self, event: Event) -> RiskAssessment:
        """Evaluate all rules against a single event. Updates rolling state."""
        triggered: list[str] = []
        reasons: list[str] = []
        total_weight = 0.0
        hit_weight = 0.0

        for rule in self._rules:
            if rule.kind_filter and event.kind not in rule.kind_filter:
                continue

            total_weight += rule.weight
            extracted_value: Optional[float] = None
            if rule.extract:
                try:
                    ns_extract: dict[str, Any] = {
                        "data": event.data,
                        "seq_id": event.seq_id,
                        "soul": event.soul,
                        "cycle": event.cycle,
                        "kind": event.kind,
                    }
                    v = _safe_eval(rule.extract, ns_extract)
                    if v is not None:
                        extracted_value = float(v)
                except Exception as e:
                    reasons.append(f"{rule.name}: extract_error={e}")
                    continue

            stats = self._rolling_stats(event.soul, rule)
            namespace: dict[str, Any] = {
                "seq_id": event.seq_id,
                "soul": event.soul,
                "cycle": event.cycle,
                "kind": event.kind,
                "data": event.data,
                "value": extracted_value,
                "count": stats["count"],
                "mean": stats["mean"],
                "std": stats["std"],
                "recent": stats["recent"],
            }

            try:
                result = _safe_eval(rule.predicate, namespace)
            except Exception as e:
                reasons.append(f"{rule.name}: predicate_error={e}")
                if extracted_value is not None:
                    self._update_rolling(event.soul, rule, extracted_value)
                continue

            if bool(result):
                triggered.append(rule.name)
                hit_weight += rule.weight
                if extracted_value is not None:
                    reasons.append(f"{rule.name}(value={extracted_value:.4g})")
                else:
                    reasons.append(rule.name)

            if extracted_value is not None:
                self._update_rolling(event.soul, rule, extracted_value)

        if total_weight > 0.0:
            score = hit_weight / total_weight
        else:
            score = 0.0
        score = max(0.0, min(1.0, score))

        return RiskAssessment(
            seq_id=event.seq_id,
            soul=event.soul,
            cycle=event.cycle,
            kind=event.kind,
            score=score,
            triggered_rules=tuple(triggered),
            reasoning="; ".join(reasons) if reasons else "no_triggers",
        )

    def assess_events(self, events: Iterable[Event]) -> Iterator[RiskAssessment]:
        """Stream assessments over an iterable of events."""
        for ev in events:
            yield self.assess(ev)

    def assess_log(self, log_path: str | Path) -> RiskReport:
        """Batch-assess a JSONL replay log. Returns aggregate RiskReport."""
        p = Path(log_path)
        report = RiskReport(log_path=str(p))
        if not p.exists():
            report.errors.append(f"log not found: {p}")
            return report

        scores: list[float] = []
        with open(p, "r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    ev = Event.from_dict(d)
                except Exception as e:
                    report.errors.append(f"line {lineno}: parse_error={e}")
                    continue
                report.total_events += 1
                a = self.assess(ev)
                report.assessments.append(a)
                report.total_assessments += 1
                scores.append(a.score)
                if a.triggered_rules:
                    report.triggered_events += 1
                for r in a.triggered_rules:
                    report.rule_hits[r] = report.rule_hits.get(r, 0) + 1
                if a.score > report.max_score:
                    report.max_score = a.score

        if scores:
            report.mean_score = sum(scores) / len(scores)

        return report


# ───────────────────────────────────────────────────────────
# Convenience for CLI
# ───────────────────────────────────────────────────────────

def render_report_text(report: RiskReport, verbose: bool = False) -> str:
    """Human-readable risk report."""
    lines: list[str] = []
    lines.append(f"RISK REPORT: {report.log_path}")
    lines.append("=" * 56)
    lines.append(f"events analyzed:    {report.total_events}")
    lines.append(f"assessments:        {report.total_assessments}")
    lines.append(f"triggered events:   {report.triggered_events}")
    lines.append(f"max score:          {report.max_score:.4f}")
    lines.append(f"mean score:         {report.mean_score:.4f}")
    if report.rule_hits:
        lines.append("")
        lines.append("rule hits:")
        for r in sorted(report.rule_hits.keys()):
            lines.append(f"  {r:30s} {report.rule_hits[r]}")
    else:
        lines.append("rule hits:          (none)")
    if report.errors:
        lines.append("")
        lines.append(f"errors: {len(report.errors)}")
        for e in report.errors[:10]:
            lines.append(f"  - {e}")
    if verbose and report.assessments:
        lines.append("")
        lines.append("per-event (triggered only):")
        for a in report.assessments:
            if a.triggered_rules:
                lines.append(
                    f"  seq={a.seq_id:4d} soul={a.soul:12s} cycle={a.cycle:3d} "
                    f"kind={a.kind:16s} score={a.score:.4f} rules={list(a.triggered_rules)}"
                )
    return "\n".join(lines)
