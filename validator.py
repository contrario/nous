"""
NOUS Law Validator — Νόμος (Nomos)
===================================
Traverses the Living AST and enforces constitutional laws.
Violations at this stage are compile-time errors.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ast_nodes import (
    NousProgram, WorldNode, SoulNode, LawCost, LawDuration,
    LawBool, LawInt, LawConstitutional, RouteNode, MatchRouteNode,
    FanInNode, FanOutNode, FeedbackNode, LetNode, SpeakNode,
    RememberNode, GuardNode, SenseCallNode, SleepNode, IfNode, ForNode,
)


@dataclass
class ValidationError:
    severity: str
    code: str
    message: str
    location: str = ""

    def __str__(self) -> str:
        prefix = f"[{self.severity}] {self.code}"
        if self.location:
            prefix += f" @ {self.location}"
        return f"{prefix}: {self.message}"


@dataclass
class ValidationResult:
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def error(self, code: str, message: str, location: str = "") -> None:
        self.errors.append(ValidationError("ERROR", code, message, location))

    def warn(self, code: str, message: str, location: str = "") -> None:
        self.warnings.append(ValidationError("WARN", code, message, location))

    def summary(self) -> str:
        lines = []
        for e in self.errors:
            lines.append(str(e))
        for w in self.warnings:
            lines.append(str(w))
        status = "PASS" if self.ok else "FAIL"
        lines.append(f"\nValidation {status}: {len(self.errors)} errors, {len(self.warnings)} warnings")
        return "\n".join(lines)


class NousValidator:
    """Validates a NousProgram against its world laws and structural rules."""

    def __init__(self, program: NousProgram) -> None:
        self.program = program
        self.result = ValidationResult()
        self.soul_names: set[str] = set()
        self.message_names: set[str] = set()
        self.message_fields: dict[str, list[str]] = {}

    def validate(self) -> ValidationResult:
        self._check_world_exists()
        self._collect_names()
        self._check_constitutional_laws()
        self._check_souls()
        self._check_nervous_system()
        self._check_evolution()
        self._check_perception()
        self._check_speak_listen_types()
        self._check_nervous_system_cycles()
        return self.result

    def _check_world_exists(self) -> None:
        if self.program.world is None:
            self.result.error("W001", "No world declaration found. Every .nous file must define exactly one world.")

    def _collect_names(self) -> None:
        for soul in self.program.souls:
            if soul.name in self.soul_names:
                self.result.error("S001", f"Duplicate soul name: {soul.name}", f"soul {soul.name}")
            self.soul_names.add(soul.name)

        for msg in self.program.messages:
            if msg.name in self.message_names:
                self.result.error("M001", f"Duplicate message name: {msg.name}", f"message {msg.name}")
            self.message_names.add(msg.name)
            self.message_fields[msg.name] = [f.name for f in msg.fields]

    def _check_souls(self) -> None:

        live_trade_tools = {
            "execute_trade", "execute_live_trade", "place_order",
            "market_buy", "market_sell", "limit_buy", "limit_sell",
            "submit_order", "send_order",
        }
        paper_trade_tools = {
            "execute_paper_trade", "paper_trade", "simulate_trade",
        }

        no_live = self._get_bool_law("NoLiveTrading")

        for soul in self.program.souls:
            loc = f"soul {soul.name}"

            if soul.mind is None:
                self.result.error("S002", f"Soul {soul.name} has no mind declaration.", loc)

            if soul.heal is None:
                self.result.error("S003", f"Soul {soul.name} has no heal block. Every soul MUST define error recovery.", loc)

            if soul.instinct is None:
                self.result.warn("S004", f"Soul {soul.name} has no instinct block.", loc)

            if not soul.senses:
                self.result.warn("S005", f"Soul {soul.name} has no senses declared.", loc)

            if no_live:
                for sense in soul.senses:
                    if sense in live_trade_tools:
                        self.result.error(
                            "C001",
                            f"Soul {soul.name} uses live trade tool '{sense}' but law NoLiveTrading = true. "
                            f"Use 'execute_paper_trade' or set NoLiveTrading = false.",
                            loc,
                        )
                self._check_live_sense_calls(soul, live_trade_tools)

            if soul.dna:
                self._check_dna_ranges(soul)

    def _check_dna_ranges(self, soul: SoulNode) -> None:
        if self.program.world is None or soul.dna is None:
            return

        for gene in soul.dna.genes:
            loc = f"soul {soul.name} > dna > {gene.name}"

            if len(gene.range) < 2:
                self.result.error("D001", f"Gene {gene.name} must have at least 2 range values.", loc)
                continue

            all_numeric = all(isinstance(v, (int, float)) for v in gene.range)
            if all_numeric:
                min_val = min(gene.range)
                max_val = max(gene.range)
                if isinstance(gene.value, (int, float)):
                    if gene.value < min_val or gene.value > max_val:
                        self.result.error("D002", f"Gene {gene.name} value {gene.value} is outside range [{min_val}, {max_val}].", loc)

    def _get_bool_law(self, name: str) -> bool:
        if self.program.world is None:
            return False
        for law in self.program.world.laws:
            if law.name == name and isinstance(law.expr, LawBool):
                return law.expr.value
        return False

    def _get_currency_law(self, name: str) -> float | None:
        if self.program.world is None:
            return None
        for law in self.program.world.laws:
            if law.name == name and isinstance(law.expr, LawCost):
                return law.expr.amount
        return None

    def _check_constitutional_laws(self) -> None:
        if self.program.world is None:
            return

        for law in self.program.world.laws:
            if isinstance(law.expr, LawConstitutional):
                count = law.expr.count
                if count < 1:
                    self.result.error(
                        "C002",
                        f"Constitutional law '{law.name}' requires count >= 1, got {count}.",
                        "world",
                    )

        max_pos = self._get_currency_law("MaxPositionSize")
        max_loss = self._get_currency_law("MaxDailyLoss")
        cost_ceiling = self._get_currency_law("CostCeiling")

        has_trade_souls = any(
            s for s in self.program.souls
            if any(t in s.senses for t in (
                "execute_paper_trade", "execute_trade", "execute_live_trade",
                "place_order", "market_buy", "market_sell",
            ))
        )

        if has_trade_souls and max_pos is None:
            self.result.warn(
                "C003",
                "Trading souls detected but no MaxPositionSize law defined. "
                "Add: law MaxPositionSize = $1000",
                "world",
            )

        if has_trade_souls and max_loss is None:
            self.result.warn(
                "C004",
                "Trading souls detected but no MaxDailyLoss law defined. "
                "Add: law MaxDailyLoss = $100",
                "world",
            )

    def _check_live_sense_calls(self, soul: SoulNode, forbidden: set[str]) -> None:
        if soul.instinct is None:
            return
        self._scan_stmts_for_tools(soul.instinct.statements, soul.name, forbidden)

    def _scan_stmts_for_tools(self, stmts: list[Any], soul_name: str, forbidden: set[str]) -> None:
        for stmt in stmts:
            if isinstance(stmt, SenseCallNode):
                if stmt.tool_name in forbidden:
                    self.result.error(
                        "C001",
                        f"Soul {soul_name} calls forbidden live trade tool '{stmt.tool_name}' "
                        f"(NoLiveTrading = true).",
                        f"soul {soul_name} > instinct",
                    )
            elif isinstance(stmt, LetNode):
                if isinstance(stmt.value, dict) and stmt.value.get("kind") == "sense_call":
                    tool = stmt.value.get("tool", "")
                    if tool in forbidden:
                        self.result.error(
                            "C001",
                            f"Soul {soul_name} calls forbidden live trade tool '{tool}' "
                            f"(NoLiveTrading = true).",
                            f"soul {soul_name} > instinct",
                        )
            elif isinstance(stmt, IfNode):
                self._scan_stmts_for_tools(stmt.then_body, soul_name, forbidden)
                self._scan_stmts_for_tools(stmt.else_body, soul_name, forbidden)
            elif isinstance(stmt, ForNode):
                self._scan_stmts_for_tools(stmt.body, soul_name, forbidden)

    def _check_nervous_system(self) -> None:
        ns = self.program.nervous_system
        if ns is None:
            if len(self.program.souls) > 1:
                self.result.warn("N001", "Multiple souls defined but no nervous_system. Souls will run independently.")
            return

        for route in ns.routes:
            if isinstance(route, RouteNode):
                self._check_soul_ref(route.source, "nervous_system")
                self._check_soul_ref(route.target, "nervous_system")

            elif isinstance(route, MatchRouteNode):
                self._check_soul_ref(route.source, "nervous_system")
                for arm in route.arms:
                    if arm.target and not arm.is_silence:
                        self._check_soul_ref(arm.target, "nervous_system")

            elif isinstance(route, FanInNode):
                for src in route.sources:
                    self._check_soul_ref(src, "nervous_system")
                self._check_soul_ref(route.target, "nervous_system")

            elif isinstance(route, FanOutNode):
                self._check_soul_ref(route.source, "nervous_system")
                for tgt in route.targets:
                    self._check_soul_ref(tgt, "nervous_system")

            elif isinstance(route, FeedbackNode):
                self._check_soul_ref(route.source_soul, "nervous_system")
                self._check_soul_ref(route.target_soul, "nervous_system")

    def _check_soul_ref(self, name: str, context: str) -> None:
        if name not in self.soul_names:
            self.result.error("N002", f"Reference to undefined soul: {name}", context)

    def _check_evolution(self) -> None:
        evo = self.program.evolution
        if evo is None:
            return

        for mut in evo.mutations:
            parts = mut.target.split(".")
            if len(parts) >= 1:
                soul_name = parts[0]
                if soul_name not in self.soul_names:
                    self.result.error("E001", f"Evolution mutate target references undefined soul: {soul_name}", "evolution")

                soul = next((s for s in self.program.souls if s.name == soul_name), None)
                if soul and len(parts) >= 2 and parts[1] == "dna" and soul.dna is None:
                    self.result.error("E002", f"Evolution targets {soul_name}.dna but soul has no dna block.", "evolution")

    def _check_perception(self) -> None:
        perc = self.program.perception
        if perc is None:
            return

        for rule in perc.rules:
            action = rule.action
            if action.kind == "wake" and action.target:
                if action.target not in self.soul_names:
                    self.result.error("P001", f"Perception wake target references undefined soul: {action.target}", "perception")
            elif action.kind == "broadcast" and action.target:
                if action.target not in self.message_names and action.target not in self.soul_names:
                    self.result.warn("P002", f"Perception broadcast target {action.target} is not a known message or soul.", "perception")

    def _check_speak_listen_types(self) -> None:
        for soul in self.program.souls:
            if soul.instinct is None:
                continue
            self._walk_statements(soul.instinct.statements, soul.name)

    def _walk_statements(self, stmts: list[Any], soul_name: str) -> None:
        for stmt in stmts:
            if isinstance(stmt, SpeakNode):
                if stmt.message_type not in self.message_names:
                    self.result.error(
                        "T001",
                        f"speak uses undefined message type: {stmt.message_type}",
                        f"soul {soul_name} > instinct",
                    )

            elif isinstance(stmt, LetNode):
                if isinstance(stmt.value, dict):
                    if stmt.value.get("kind") == "listen":
                        msg_type = stmt.value.get("type", "")
                        if msg_type not in self.message_names:
                            self.result.error(
                                "T002",
                                f"listen expects undefined message type: {msg_type}",
                                f"soul {soul_name} > instinct",
                            )

            elif isinstance(stmt, IfNode):
                self._walk_statements(stmt.then_body, soul_name)
                self._walk_statements(stmt.else_body, soul_name)

            elif isinstance(stmt, ForNode):
                self._walk_statements(stmt.body, soul_name)

    def _check_nervous_system_cycles(self) -> None:
        ns = self.program.nervous_system
        if ns is None:
            return

        graph: dict[str, list[str]] = {name: [] for name in self.soul_names}
        feedback_edges: set[tuple[str, str]] = set()

        for route in ns.routes:
            if isinstance(route, RouteNode):
                if route.source in graph:
                    graph[route.source].append(route.target)
            elif isinstance(route, FeedbackNode):
                feedback_edges.add((route.source_soul, route.target_soul))
            elif isinstance(route, FanInNode):
                for src in route.sources:
                    if src in graph:
                        graph[src].append(route.target)
            elif isinstance(route, FanOutNode):
                if route.source in graph:
                    graph[route.source].extend(route.targets)
            elif isinstance(route, MatchRouteNode):
                for arm in route.arms:
                    if arm.target and not arm.is_silence and route.source in graph:
                        graph[route.source].append(arm.target)

        visited: set[str] = set()
        rec_stack: set[str] = set()

        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            for neighbor in graph.get(node, []):
                if (node, neighbor) in feedback_edges:
                    continue
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.discard(node)
            return False

        for node in list(graph.keys()):
            if node not in visited:
                if has_cycle(node):
                    self.result.error(
                        "N003",
                        "Cycle detected in nervous_system without explicit feedback annotation.",
                        "nervous_system",
                    )
                    break


def validate_program(program: NousProgram) -> ValidationResult:
    """Validate a NousProgram. Returns ValidationResult."""
    validator = NousValidator(program)
    return validator.validate()
