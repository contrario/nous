"""
NOUS Behavioral Diff — Σημασιολογική Διαφορά
==============================================
Compares two .nous programs and reports the behavioral impact of changes.
Not a text diff — a semantic diff across cost, topology, verification, and risk.

Usage:
    python cli.py diff original.nous modified.nous
    python cli.py diff original.nous modified.nous --json
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from ast_nodes import NousProgram, SoulNode, MessageNode, Tier


TIER_COSTS: dict[str, dict[str, float]] = {
    "Tier0A": {"input_per_1k": 0.00025, "output_per_1k": 0.00125},
    "Tier0B": {"input_per_1k": 0.0005, "output_per_1k": 0.0025},
    "Tier1":  {"input_per_1k": 0.003, "output_per_1k": 0.015},
    "Tier2":  {"input_per_1k": 0.005, "output_per_1k": 0.025},
    "Tier3":  {"input_per_1k": 0.015, "output_per_1k": 0.075},
    "Groq":      {"input_per_1k": 0.0003, "output_per_1k": 0.001},
    "Together":  {"input_per_1k": 0.0005, "output_per_1k": 0.002},
    "Fireworks": {"input_per_1k": 0.0002, "output_per_1k": 0.0008},
    "Cerebras":  {"input_per_1k": 0.0001, "output_per_1k": 0.0004},
}

AVG_INPUT_TOKENS: float = 0.5
AVG_OUTPUT_TOKENS: float = 0.2


class Severity(str, Enum):
    INFO = "info"
    WARN = "warning"
    CRITICAL = "critical"


@dataclass
class DiffItem:
    category: str
    severity: Severity
    message: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        d: dict[str, str] = {
            "category": self.category,
            "severity": self.severity.value,
            "message": self.message,
        }
        if self.detail:
            d["detail"] = self.detail
        return d


@dataclass
class CostProjection:
    soul_name: str
    old_cost: float
    new_cost: float

    @property
    def delta(self) -> float:
        return self.new_cost - self.old_cost

    @property
    def delta_pct(self) -> float:
        if self.old_cost == 0:
            return 100.0 if self.new_cost > 0 else 0.0
        return (self.delta / self.old_cost) * 100


@dataclass
class BehavioralDiffResult:
    items: list[DiffItem] = field(default_factory=list)
    cost_projections: list[CostProjection] = field(default_factory=list)
    old_verif_count: int = 0
    new_verif_count: int = 0
    souls_added: list[str] = field(default_factory=list)
    souls_removed: list[str] = field(default_factory=list)
    souls_modified: list[str] = field(default_factory=list)
    messages_added: list[str] = field(default_factory=list)
    messages_removed: list[str] = field(default_factory=list)

    @property
    def total_old_cost(self) -> float:
        return sum(c.old_cost for c in self.cost_projections)

    @property
    def total_new_cost(self) -> float:
        return sum(c.new_cost for c in self.cost_projections)

    @property
    def has_critical(self) -> bool:
        return any(i.severity == Severity.CRITICAL for i in self.items)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == Severity.WARN for i in self.items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [i.to_dict() for i in self.items],
            "cost": {
                "old_total": self.total_old_cost,
                "new_total": self.total_new_cost,
                "delta": self.total_new_cost - self.total_old_cost,
                "per_soul": [
                    {"soul": c.soul_name, "old": c.old_cost, "new": c.new_cost,
                     "delta": c.delta, "delta_pct": round(c.delta_pct, 1)}
                    for c in self.cost_projections
                ],
            },
            "souls_added": self.souls_added,
            "souls_removed": self.souls_removed,
            "souls_modified": self.souls_modified,
            "messages_added": self.messages_added,
            "messages_removed": self.messages_removed,
        }


def _estimate_soul_cost(soul: SoulNode) -> float:
    if not soul.mind:
        return 0.0
    tier = soul.mind.tier.value if soul.mind.tier else "Tier1"
    costs = TIER_COSTS.get(tier, TIER_COSTS["Tier1"])
    return (AVG_INPUT_TOKENS * costs["input_per_1k"]) + (AVG_OUTPUT_TOKENS * costs["output_per_1k"])


def _get_routes(program: NousProgram) -> list[tuple[str, str]]:
    routes: list[tuple[str, str]] = []
    if program.nervous_system:
        for route in program.nervous_system.routes:
            src = route.source if isinstance(route.source, str) else str(route.source)
            dst = route.target if isinstance(route.target, str) else str(route.target)
            routes.append((src, dst))
    return routes


def _detect_cycles(routes: list[tuple[str, str]]) -> list[list[str]]:
    graph: dict[str, list[str]] = {}
    for src, dst in routes:
        graph.setdefault(src, []).append(dst)

    cycles: list[list[str]] = []
    visited: set[str] = set()
    path: list[str] = []
    on_path: set[str] = set()

    def dfs(node: str) -> None:
        if node in on_path:
            cycle_start = path.index(node)
            cycles.append(path[cycle_start:] + [node])
            return
        if node in visited:
            return
        visited.add(node)
        on_path.add(node)
        path.append(node)
        for neighbor in graph.get(node, []):
            dfs(neighbor)
        path.pop()
        on_path.discard(node)

    for node in graph:
        dfs(node)

    return cycles


def _find_unreachable(routes: list[tuple[str, str]], all_souls: list[str], entrypoints: list[str]) -> list[str]:
    graph: dict[str, list[str]] = {}
    for src, dst in routes:
        graph.setdefault(src, []).append(dst)

    reachable: set[str] = set()
    queue: list[str] = list(entrypoints)
    while queue:
        node = queue.pop(0)
        if node in reachable:
            continue
        reachable.add(node)
        for neighbor in graph.get(node, []):
            if neighbor not in reachable:
                queue.append(neighbor)

    return [s for s in all_souls if s not in reachable]


def _get_entrypoints(program: NousProgram) -> list[str]:
    if not program.nervous_system:
        return [s.name for s in program.souls]

    targets: set[str] = set()
    for route in program.nervous_system.routes:
        dst = route.target if isinstance(route.target, str) else str(route.target)
        targets.add(dst)

    return [s.name for s in program.souls if s.name not in targets]


def _get_soul_senses(soul: SoulNode) -> set[str]:
    return set(soul.senses) if soul.senses else set()


def _get_soul_memory_fields(soul: SoulNode) -> dict[str, str]:
    fields: dict[str, str] = {}
    if soul.memory:
        for f in soul.memory:
            name = f.name if hasattr(f, "name") else str(f)
            ftype = f.type if hasattr(f, "type") else "unknown"
            fields[name] = str(ftype)
    return fields


def _get_cost_ceiling(program: NousProgram) -> Optional[float]:
    if program.world:
        for law in program.world.laws:
            if hasattr(law, "expr") and hasattr(law.expr, "amount"):
                return float(law.expr.amount)
    return None


def behavioral_diff(old_program: NousProgram, new_program: NousProgram) -> BehavioralDiffResult:
    result = BehavioralDiffResult()

    old_souls = {s.name: s for s in old_program.souls}
    new_souls = {s.name: s for s in new_program.souls}
    old_msgs = {m.name: m for m in old_program.messages}
    new_msgs = {m.name: m for m in new_program.messages}

    result.souls_added = [n for n in new_souls if n not in old_souls]
    result.souls_removed = [n for n in old_souls if n not in new_souls]
    result.messages_added = [n for n in new_msgs if n not in old_msgs]
    result.messages_removed = [n for n in old_msgs if n not in new_msgs]

    for name in result.souls_added:
        result.items.append(DiffItem("topology", Severity.INFO, f"Soul added: {name}",
                                     f"New soul with mind: {new_souls[name].mind.model if new_souls[name].mind else 'none'}"))

    for name in result.souls_removed:
        result.items.append(DiffItem("topology", Severity.WARN, f"Soul removed: {name}",
                                     "Existing routes referencing this soul will break"))

    for name in result.messages_added:
        result.items.append(DiffItem("protocol", Severity.INFO, f"Message type added: {name}"))

    for name in result.messages_removed:
        result.items.append(DiffItem("protocol", Severity.WARN, f"Message type removed: {name}",
                                     "Souls speaking/listening to this type will fail"))

    common_souls = set(old_souls.keys()) & set(new_souls.keys())
    for name in common_souls:
        old_s = old_souls[name]
        new_s = new_souls[name]
        modified = False

        old_tier = old_s.mind.tier.value if old_s.mind and old_s.mind.tier else "none"
        new_tier = new_s.mind.tier.value if new_s.mind and new_s.mind.tier else "none"
        if old_tier != new_tier:
            modified = True
            result.items.append(DiffItem("cost", Severity.WARN,
                                         f"Soul {name}: tier changed {old_tier} → {new_tier}"))

        old_model = old_s.mind.model if old_s.mind else "none"
        new_model = new_s.mind.model if new_s.mind else "none"
        if old_model != new_model:
            modified = True
            result.items.append(DiffItem("cost", Severity.INFO,
                                         f"Soul {name}: model changed {old_model} → {new_model}"))

        old_senses = _get_soul_senses(old_s)
        new_senses = _get_soul_senses(new_s)
        added_senses = new_senses - old_senses
        removed_senses = old_senses - new_senses
        if added_senses:
            modified = True
            result.items.append(DiffItem("capability", Severity.INFO,
                                         f"Soul {name}: senses added: {', '.join(sorted(added_senses))}"))
        if removed_senses:
            modified = True
            result.items.append(DiffItem("capability", Severity.WARN,
                                         f"Soul {name}: senses removed: {', '.join(sorted(removed_senses))}",
                                         "Instinct code using these senses will fail"))

        old_mem = _get_soul_memory_fields(old_s)
        new_mem = _get_soul_memory_fields(new_s)
        for f in set(new_mem.keys()) - set(old_mem.keys()):
            modified = True
            result.items.append(DiffItem("memory", Severity.INFO,
                                         f"Soul {name}: memory field added: {f}: {new_mem[f]}"))
        for f in set(old_mem.keys()) - set(new_mem.keys()):
            modified = True
            result.items.append(DiffItem("memory", Severity.WARN,
                                         f"Soul {name}: memory field removed: {f}",
                                         "Remember statements targeting this field will fail"))

        if old_s.dna and new_s.dna:
            old_genes = {g.name: g for g in old_s.dna.genes} if old_s.dna and hasattr(old_s.dna, "genes") else {}
            new_genes = {g.name: g for g in new_s.dna.genes} if new_s.dna and hasattr(new_s.dna, "genes") else {}
            for gname in set(new_genes.keys()) - set(old_genes.keys()):
                modified = True
                result.items.append(DiffItem("evolution", Severity.INFO,
                                             f"Soul {name}: DNA gene added: {gname}"))
            for gname in set(old_genes.keys()) - set(new_genes.keys()):
                modified = True
                result.items.append(DiffItem("evolution", Severity.INFO,
                                             f"Soul {name}: DNA gene removed: {gname}"))

        if modified:
            result.souls_modified.append(name)

    all_soul_names_old = list(old_souls.keys())
    all_soul_names_new = list(new_souls.keys())

    for name in all_soul_names_new:
        s = new_souls[name]
        new_cost = _estimate_soul_cost(s)
        old_cost = _estimate_soul_cost(old_souls[name]) if name in old_souls else 0.0
        result.cost_projections.append(CostProjection(soul_name=name, old_cost=old_cost, new_cost=new_cost))

    for name in result.souls_removed:
        s = old_souls[name]
        old_cost = _estimate_soul_cost(s)
        result.cost_projections.append(CostProjection(soul_name=name, old_cost=old_cost, new_cost=0.0))

    cost_delta = result.total_new_cost - result.total_old_cost
    if result.total_old_cost > 0:
        cost_pct = (cost_delta / result.total_old_cost) * 100
    else:
        cost_pct = 0.0

    if abs(cost_pct) > 50:
        result.items.append(DiffItem("cost", Severity.CRITICAL,
                                     f"Total cost change: {cost_pct:+.1f}%",
                                     f"${result.total_old_cost:.6f} → ${result.total_new_cost:.6f} per cycle"))
    elif abs(cost_pct) > 10:
        result.items.append(DiffItem("cost", Severity.WARN,
                                     f"Total cost change: {cost_pct:+.1f}%",
                                     f"${result.total_old_cost:.6f} → ${result.total_new_cost:.6f} per cycle"))

    new_ceiling = _get_cost_ceiling(new_program)
    if new_ceiling and result.total_new_cost > new_ceiling:
        result.items.append(DiffItem("cost", Severity.CRITICAL,
                                     f"Cost exceeds ceiling: ${result.total_new_cost:.6f} > ${new_ceiling}",
                                     "Circuit breaker will trip every cycle"))

    old_routes = _get_routes(old_program)
    new_routes = _get_routes(new_program)
    added_routes = [r for r in new_routes if r not in old_routes]
    removed_routes = [r for r in old_routes if r not in new_routes]

    for src, dst in added_routes:
        result.items.append(DiffItem("topology", Severity.INFO, f"Route added: {src} → {dst}"))
    for src, dst in removed_routes:
        result.items.append(DiffItem("topology", Severity.WARN, f"Route removed: {src} → {dst}"))

    new_cycles = _detect_cycles(new_routes)
    old_cycles = _detect_cycles(old_routes)
    new_cycle_set = {tuple(c) for c in new_cycles}
    old_cycle_set = {tuple(c) for c in old_cycles}
    introduced_cycles = new_cycle_set - old_cycle_set
    for cycle in introduced_cycles:
        result.items.append(DiffItem("deadlock", Severity.CRITICAL,
                                     f"New circular dependency: {' → '.join(cycle)}",
                                     "This will cause deadlock unless annotated as feedback"))

    new_entrypoints = _get_entrypoints(new_program)
    old_entrypoints = _get_entrypoints(old_program)
    if len(new_entrypoints) == 0 and len(old_entrypoints) > 0:
        result.items.append(DiffItem("liveness", Severity.CRITICAL,
                                     "No entrypoints remain — pipeline will never start"))
    lost_entrypoints = set(old_entrypoints) - set(new_entrypoints)
    for ep in lost_entrypoints:
        if ep in new_souls:
            result.items.append(DiffItem("liveness", Severity.WARN,
                                         f"Soul {ep} is no longer an entrypoint (now has incoming routes)"))

    new_unreachable = _find_unreachable(new_routes, all_soul_names_new, new_entrypoints)
    old_unreachable = _find_unreachable(old_routes, all_soul_names_old, old_entrypoints)
    newly_unreachable = set(new_unreachable) - set(old_unreachable)
    for soul_name in newly_unreachable:
        result.items.append(DiffItem("reachability", Severity.WARN,
                                     f"Soul {soul_name} is now unreachable from entrypoints",
                                     "This soul will never execute"))

    old_wake: dict[str, str] = {}
    new_wake: dict[str, str] = {}
    old_targets = {r[1] for r in old_routes}
    new_targets = {r[1] for r in new_routes}
    for s in old_program.souls:
        old_wake[s.name] = "LISTENER" if s.name in old_targets else "HEARTBEAT"
    for s in new_program.souls:
        new_wake[s.name] = "LISTENER" if s.name in new_targets else "HEARTBEAT"

    for name in common_souls:
        if name in old_wake and name in new_wake and old_wake[name] != new_wake[name]:
            result.items.append(DiffItem("wake", Severity.WARN,
                                         f"Soul {name}: wake strategy changed {old_wake[name]} → {new_wake[name]}",
                                         "HEARTBEAT→LISTENER means soul now needs incoming messages to wake"))

    old_ceiling = _get_cost_ceiling(old_program)
    if old_ceiling != new_ceiling:
        if old_ceiling is not None and new_ceiling is not None:
            sev = Severity.WARN if new_ceiling > old_ceiling else Severity.INFO
            result.items.append(DiffItem("law", sev,
                                         f"Cost ceiling changed: ${old_ceiling} → ${new_ceiling}"))
        elif new_ceiling is None:
            result.items.append(DiffItem("law", Severity.CRITICAL,
                                         "Cost ceiling removed — no budget protection"))

    if old_program.world and new_program.world:
        old_hb = getattr(old_program.world, 'heartbeat', None)
        new_hb = getattr(new_program.world, 'heartbeat', None)
        if old_hb and new_hb and str(old_hb) != str(new_hb):
            result.items.append(DiffItem("performance", Severity.INFO,
                                         f"Heartbeat changed: {old_hb} → {new_hb}"))

    return result


def format_diff(result: BehavioralDiffResult, old_name: str, new_name: str) -> str:
    lines: list[str] = []
    lines.append("")
    lines.append("  ═══ NOUS Behavioral Diff ═══")
    lines.append(f"  {old_name} → {new_name}")
    lines.append("")

    if not result.items and not result.cost_projections:
        lines.append("  No behavioral changes detected.")
        return "\n".join(lines)

    if result.souls_added or result.souls_removed:
        lines.append("  ── Topology ──")
        for s in result.souls_added:
            lines.append(f"  + Soul added: {s}")
        for s in result.souls_removed:
            lines.append(f"  - Soul removed: {s}")
        if result.souls_modified:
            lines.append(f"  ~ Souls modified: {', '.join(result.souls_modified)}")
        lines.append("")

    if result.messages_added or result.messages_removed:
        lines.append("  ── Protocol ──")
        for m in result.messages_added:
            lines.append(f"  + Message added: {m}")
        for m in result.messages_removed:
            lines.append(f"  - Message removed: {m}")
        lines.append("")

    if result.cost_projections:
        lines.append("  ── Cost Impact ──")
        for cp in result.cost_projections:
            if cp.old_cost == 0 and cp.new_cost > 0:
                lines.append(f"  + {cp.soul_name}: ${cp.new_cost:.6f}/cycle (new)")
            elif cp.new_cost == 0 and cp.old_cost > 0:
                lines.append(f"  - {cp.soul_name}: -${cp.old_cost:.6f}/cycle (removed)")
            elif cp.delta != 0:
                arrow = "↑" if cp.delta > 0 else "↓"
                lines.append(f"  {arrow} {cp.soul_name}: ${cp.old_cost:.6f} → ${cp.new_cost:.6f} ({cp.delta_pct:+.1f}%)")
            else:
                lines.append(f"  = {cp.soul_name}: ${cp.new_cost:.6f}/cycle (unchanged)")

        delta = result.total_new_cost - result.total_old_cost
        pct = ((delta / result.total_old_cost) * 100) if result.total_old_cost > 0 else 0
        lines.append(f"")
        lines.append(f"  Total: ${result.total_old_cost:.6f} → ${result.total_new_cost:.6f} ({pct:+.1f}%)")

        if result.total_old_cost > 0:
            daily_old = result.total_old_cost * (86400 / 300)
            daily_new = result.total_new_cost * (86400 / 300)
            monthly_old = daily_old * 30
            monthly_new = daily_new * 30
            lines.append(f"  Daily:   ${daily_old:.2f} → ${daily_new:.2f}")
            lines.append(f"  Monthly: ${monthly_old:.2f} → ${monthly_new:.2f}")
        lines.append("")

    categories = {}
    for item in result.items:
        if item.category not in ("topology", "protocol"):
            categories.setdefault(item.category, []).append(item)

    for cat, items in categories.items():
        lines.append(f"  ── {cat.title()} ──")
        for item in items:
            icon = {"critical": "✗", "warning": "⚠", "info": "ℹ"}.get(item.severity.value, "·")
            color_prefix = {"critical": "CRITICAL", "warning": "WARNING", "info": ""}.get(item.severity.value, "")
            if color_prefix:
                lines.append(f"  {icon} [{color_prefix}] {item.message}")
            else:
                lines.append(f"  {icon} {item.message}")
            if item.detail:
                lines.append(f"    → {item.detail}")
        lines.append("")

    criticals = sum(1 for i in result.items if i.severity == Severity.CRITICAL)
    warnings = sum(1 for i in result.items if i.severity == Severity.WARN)
    infos = sum(1 for i in result.items if i.severity == Severity.INFO)

    lines.append("  ══════════════════════════════════════")
    if criticals > 0:
        lines.append(f"  BREAKING: {criticals} critical, {warnings} warnings, {infos} info")
    elif warnings > 0:
        lines.append(f"  CAUTION: {warnings} warnings, {infos} info")
    else:
        lines.append(f"  SAFE: {infos} changes, no warnings")
    lines.append("")

    return "\n".join(lines)


def diff_files(old_path: str, new_path: str, output_json: bool = False) -> str:
    from parser import parse_nous

    old_source = Path(old_path).read_text()
    new_source = Path(new_path).read_text()

    old_program = parse_nous(old_source)
    new_program = parse_nous(new_source)

    result = behavioral_diff(old_program, new_program)

    if output_json:
        return json.dumps(result.to_dict(), indent=2)

    return format_diff(result, Path(old_path).name, Path(new_path).name)
