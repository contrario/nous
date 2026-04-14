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
        self._check_souls()
        self._check_nervous_system()
        self._check_evolution()
        self._check_perception()
        self._check_speak_listen_types()
        self._check_nervous_system_cycles()
        self._check_noesis()
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

            if soul.dna:
                self._check_dna_ranges(soul)

            if soul.mitosis:
                self._check_mitosis(soul)

            if soul.immune_system:
                self._check_immune(soul)

            if soul.dream_system:
                self._check_dream(soul)

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




    def _check_dream(self, soul: SoulNode) -> None:
        loc = f"soul {soul.name} > dream_system"
        ds = soul.dream_system
        if ds.trigger_idle_sec < 5:
            self.result.error("DR001", f"Dream trigger_idle_sec={ds.trigger_idle_sec} too short (min 5s).", loc)
        if ds.max_cache < 1:
            self.result.error("DR002", f"Dream max_cache must be >= 1.", loc)
        if ds.max_cache > 100:
            self.result.warn("DR003", f"Dream max_cache={ds.max_cache} is very large. Memory impact.", loc)
        if ds.speculation_depth < 1 or ds.speculation_depth > 10:
            self.result.warn("DR004", f"Dream speculation_depth={ds.speculation_depth} outside recommended range [1-10].", loc)
        if ds.dream_mind and soul.mind:
            if ds.dream_mind.tier == soul.mind.tier:
                self.result.warn("DR005", f"Dream mind uses same tier as primary mind. Use a cheaper tier for dreams.", loc)

    def _check_immune(self, soul: SoulNode) -> None:
        loc = f"soul {soul.name} > immune_system"
        im = soul.immune_system

        if im.adaptive_recovery and soul.heal is None:
            self.result.warn("IM001", f"Soul {soul.name} has immune_system but no heal block. Heal runs before immune recovery.", loc)

        if im.share_with_clones and (soul.mitosis is None):
            self.result.warn("IM002", f"Soul {soul.name} has share_with_clones=true but no mitosis block. No clones to share with.", loc)

        import re
        m = re.match(r"(\d+)(ms|s|m|h|d)", im.antibody_lifespan)
        if m:
            val = int(m.group(1))
            unit = m.group(2)
            seconds = {"ms": val / 1000, "s": val, "m": val * 60, "h": val * 3600, "d": val * 86400}.get(unit, val)
            if seconds < 10:
                self.result.error("IM003", f"Antibody lifespan {im.antibody_lifespan} is too short (min 10s).", loc)

    def _check_mitosis(self, soul: SoulNode) -> None:
        loc = f"soul {soul.name} > mitosis"
        m = soul.mitosis

        if m.max_clones < 1:
            self.result.error("MT001", f"Mitosis max_clones must be >= 1, got {m.max_clones}", loc)

        if m.max_clones > 10:
            self.result.warn("MT002", f"Mitosis max_clones={m.max_clones} is very high. Consider resource impact.", loc)

        if m.trigger is None:
            self.result.error("MT003", "Mitosis trigger condition is required.", loc)

        if soul.mind is None:
            self.result.error("MT004", f"Soul {soul.name} has mitosis but no mind. Clones need a mind.", loc)

        if soul.heal is None:
            self.result.warn("MT005", f"Soul {soul.name} has mitosis but no heal block. Clones inherit heal rules.", loc)

        if m.min_clones < 0:
            self.result.error("RT001", f"Mitosis min_clones must be >= 0, got {m.min_clones}", loc)

        if m.min_clones >= m.max_clones:
            self.result.error("RT002", f"Mitosis min_clones ({m.min_clones}) must be < max_clones ({m.max_clones})", loc)

        if m.retire_trigger is not None and m.trigger is None:
            self.result.warn("RT003", f"Soul {soul.name} has retire_trigger but no spawn trigger. Clones never spawn.", loc)

        if m.trigger is not None and m.retire_trigger is None:
            self.result.warn("RT004", f"Soul {soul.name} has mitosis but no retire_trigger. Clones never die — potential resource leak.", loc)

        if m.clone_tier:
            valid_tiers = {"Tier0A", "Tier0B", "Tier1", "Tier2", "Tier3", "Groq", "Together", "Fireworks", "Cerebras"}
            if m.clone_tier not in valid_tiers:
                self.result.error("MT006", f"Invalid clone_tier: {m.clone_tier}", loc)

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

    def _check_noesis(self) -> None:
        has_noesis = hasattr(self.program, 'noesis') and self.program.noesis is not None
        has_resonate = False
        for soul in self.program.souls:
            if not hasattr(soul, 'instinct') or not soul.instinct:
                continue
            stmts = getattr(soul.instinct, 'statements', [])
            for stmt in stmts:
                val = getattr(stmt, 'value', None)
                if isinstance(val, dict) and val.get('kind') == 'resonate':
                    has_resonate = True
                    break
        if has_resonate and not has_noesis:
            self.result.warn(
                "NS001",
                "resonate keyword used without noesis block — will use default config",
            )
        if has_noesis and self.program.noesis.lattice_path:
            from pathlib import Path
            lp = Path(self.program.noesis.lattice_path)
            if not lp.exists() and not lp.is_absolute():
                pass


def validate_program(program: NousProgram) -> ValidationResult:
    """Validate a NousProgram. Returns ValidationResult."""
    validator = NousValidator(program)
    return validator.validate()
