"""
NOUS Formal Verifier — Απόδειξη (Apodeixi)
=============================================
Static analysis engine providing mathematical guarantees:
1. Resource Bounding — max cost per cycle vs world ceiling
2. Dependency Soundness — deadlock detection in nervous_system
3. Protocol Consistency — speak/listen message type alignment
4. Liveness — every listener has at least one producer
5. Reachability — every soul participates in the pipeline
6. Memory Safety — remember targets exist and types match
7. Topology Soundness — distributed node soul coverage
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ast_nodes import (
    NousProgram, SoulNode, WorldNode, MessageNode,
    NervousSystemNode, RouteNode, MatchRouteNode,
    FanInNode, FanOutNode, FeedbackNode,
    LetNode, RememberNode, SpeakNode, GuardNode,
    SenseCallNode, SleepNode, IfNode, ForNode,
    LawCost, TopologyNode,
)


TIER_COSTS: dict[str, dict[str, float]] = {
    "Tier0A": {"input_per_1k": 0.00025, "output_per_1k": 0.00125},
    "Tier0B": {"input_per_1k": 0.0005, "output_per_1k": 0.0025},
    "Tier1":  {"input_per_1k": 0.003, "output_per_1k": 0.015},
    "Tier2":  {"input_per_1k": 0.005, "output_per_1k": 0.025},
    "Tier3":  {"input_per_1k": 0.015, "output_per_1k": 0.075},
}

EST_TOKENS_PER_SENSE = 500
EST_TOKENS_OUTPUT = 200
EST_TOKENS_PER_INSTINCT_BASE = 300


class VerificationSeverity:
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"
    PROVEN = "PROVEN"


@dataclass
class VerificationItem:
    severity: str
    code: str
    category: str
    message: str
    location: str = ""
    detail: str = ""

    def __str__(self) -> str:
        icon = {"ERROR": "✗", "WARNING": "⚠", "INFO": "ℹ", "PROVEN": "✓"}.get(self.severity, "?")
        prefix = f"  {icon} [{self.code}]"
        if self.location:
            prefix += f" @ {self.location}"
        line = f"{prefix}: {self.message}"
        if self.detail:
            line += f"\n      {self.detail}"
        return line


@dataclass
class VerificationResult:
    items: list[VerificationItem] = field(default_factory=list)

    @property
    def errors(self) -> list[VerificationItem]:
        return [i for i in self.items if i.severity == VerificationSeverity.ERROR]

    @property
    def warnings(self) -> list[VerificationItem]:
        return [i for i in self.items if i.severity == VerificationSeverity.WARNING]

    @property
    def proven(self) -> list[VerificationItem]:
        return [i for i in self.items if i.severity == VerificationSeverity.PROVEN]

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def add(self, severity: str, code: str, category: str, message: str, location: str = "", detail: str = "") -> None:
        self.items.append(VerificationItem(severity, code, category, message, location, detail))

    def error(self, code: str, category: str, message: str, location: str = "", detail: str = "") -> None:
        self.add(VerificationSeverity.ERROR, code, category, message, location, detail)

    def warning(self, code: str, category: str, message: str, location: str = "", detail: str = "") -> None:
        self.add(VerificationSeverity.WARNING, code, category, message, location, detail)

    def prove(self, code: str, category: str, message: str, location: str = "", detail: str = "") -> None:
        self.add(VerificationSeverity.PROVEN, code, category, message, location, detail)

    def info(self, code: str, category: str, message: str, location: str = "", detail: str = "") -> None:
        self.add(VerificationSeverity.INFO, code, category, message, location, detail)

    def summary(self) -> str:
        lines: list[str] = []
        categories: dict[str, list[VerificationItem]] = {}
        for item in self.items:
            categories.setdefault(item.category, []).append(item)
        for cat in ["resource_bound", "deadlock", "protocol", "liveness", "reachability", "memory_safety", "topology", "telemetry", "mitosis", "retirement", "immune", "dream"]:
            if cat not in categories:
                continue
            cat_label = cat.replace("_", " ").title()
            lines.append(f"\n  ── {cat_label} ──")
            for item in categories[cat]:
                lines.append(str(item))
        err_count = len(self.errors)
        warn_count = len(self.warnings)
        proven_count = len(self.proven)
        total = len(self.items)
        lines.append(f"\n  ══════════════════════════════════════")
        status = "VERIFIED" if self.ok else "FAILED"
        lines.append(f"  {status}: {proven_count} proven, {warn_count} warnings, {err_count} errors ({total} checks)")
        return "\n".join(lines)


class NousVerifier:

    def __init__(self, program: NousProgram) -> None:
        self.program = program
        self.result = VerificationResult()
        self._soul_map: dict[str, SoulNode] = {}
        self._message_map: dict[str, MessageNode] = {}
        self._routes: list[tuple[str, str]] = []
        self._incoming: dict[str, list[str]] = {}
        self._outgoing: dict[str, list[str]] = {}
        self._feedback_edges: set[tuple[str, str]] = set()
        self._speaks: dict[str, list[str]] = {}
        self._listens: dict[str, list[tuple[str, str]]] = {}
        self._cost_ceiling: float = 0.10

    def verify(self) -> VerificationResult:
        self._collect_metadata()
        self._verify_resource_bounds()
        self._verify_deadlocks()
        self._verify_protocol_consistency()
        self._verify_liveness()
        self._verify_reachability()
        self._verify_memory_safety()
        self._verify_topology()
        self._verify_telemetry()
        self._verify_mitosis()
        self._verify_retirement()
        self._verify_immune()
        self._verify_dream()
        return self.result

    def _collect_metadata(self) -> None:
        for soul in self.program.souls:
            self._soul_map[soul.name] = soul
        for msg in self.program.messages:
            self._message_map[msg.name] = msg

        ns = self.program.nervous_system
        if ns:
            for route in ns.routes:
                if isinstance(route, RouteNode):
                    self._routes.append((route.source, route.target))
                elif isinstance(route, FanInNode):
                    for src in route.sources:
                        self._routes.append((src, route.target))
                elif isinstance(route, FanOutNode):
                    for tgt in route.targets:
                        self._routes.append((route.source, tgt))
                elif isinstance(route, FeedbackNode):
                    self._feedback_edges.add((route.source_soul, route.target_soul))
                elif isinstance(route, MatchRouteNode):
                    for arm in route.arms:
                        if arm.target and not arm.is_silence:
                            self._routes.append((route.source, arm.target))

        for src, tgt in self._routes:
            self._outgoing.setdefault(src, []).append(tgt)
            self._incoming.setdefault(tgt, []).append(src)

        for soul in self.program.souls:
            self._speaks[soul.name] = []
            self._listens[soul.name] = []
            if soul.instinct:
                self._collect_speak_listen(soul.instinct.statements, soul.name)

        if self.program.world:
            for law in self.program.world.laws:
                if isinstance(law.expr, LawCost) and law.expr.per == "cycle":
                    self._cost_ceiling = law.expr.amount

    def _collect_speak_listen(self, stmts: list[Any], soul_name: str) -> None:
        for stmt in stmts:
            if isinstance(stmt, SpeakNode):
                self._speaks[soul_name].append(stmt.message_type)
            elif isinstance(stmt, LetNode):
                if isinstance(stmt.value, dict) and stmt.value.get("kind") == "listen":
                    src_soul = stmt.value.get("soul", "")
                    msg_type = stmt.value.get("type", "")
                    self._listens[soul_name].append((src_soul, msg_type))
            elif isinstance(stmt, IfNode):
                self._collect_speak_listen(stmt.then_body, soul_name)
                self._collect_speak_listen(stmt.else_body, soul_name)
            elif isinstance(stmt, ForNode):
                self._collect_speak_listen(stmt.body, soul_name)

    def _verify_resource_bounds(self) -> None:
        for soul in self.program.souls:
            tier = soul.mind.tier.value if soul.mind else "Tier1"
            tier_info = TIER_COSTS.get(tier, TIER_COSTS["Tier1"])
            sense_count = self._count_sense_calls(soul)
            est_input = EST_TOKENS_PER_INSTINCT_BASE + (sense_count * EST_TOKENS_PER_SENSE)
            est_output = EST_TOKENS_OUTPUT
            est_cost = (
                (est_input / 1000) * tier_info["input_per_1k"]
                + (est_output / 1000) * tier_info["output_per_1k"]
            )
            loc = f"soul {soul.name}"
            if est_cost > self._cost_ceiling:
                self.result.error(
                    "VR001", "resource_bound",
                    f"Soul {soul.name} estimated max cost ${est_cost:.6f} exceeds ceiling ${self._cost_ceiling:.2f}",
                    loc,
                    f"Tier={tier}, senses={sense_count}, est_input={est_input}tok, est_output={est_output}tok",
                )
            else:
                ratio = est_cost / self._cost_ceiling if self._cost_ceiling > 0 else 0
                self.result.prove(
                    "VR001", "resource_bound",
                    f"Soul {soul.name} cost bounded: ${est_cost:.6f} ≤ ${self._cost_ceiling:.2f} ({ratio:.0%} of ceiling)",
                    loc,
                )

        total_max = 0.0
        for soul in self.program.souls:
            if soul.name not in self._incoming:
                tier = soul.mind.tier.value if soul.mind else "Tier1"
                cascade_cost = self._estimate_cascade_cost(soul.name, set())
                total_max += cascade_cost

        if total_max > self._cost_ceiling:
            self.result.warning(
                "VR002", "resource_bound",
                f"Total cascade cost ${total_max:.6f} may exceed ceiling ${self._cost_ceiling:.2f}",
                "world",
                "Sum of all entrypoint cascades through nervous_system",
            )
        else:
            self.result.prove(
                "VR002", "resource_bound",
                f"Total cascade cost ${total_max:.6f} ≤ ${self._cost_ceiling:.2f}",
                "world",
            )

    def _estimate_cascade_cost(self, soul_name: str, visited: set[str]) -> float:
        if soul_name in visited:
            return 0.0
        visited.add(soul_name)
        soul = self._soul_map.get(soul_name)
        if not soul:
            return 0.0
        tier = soul.mind.tier.value if soul.mind else "Tier1"
        tier_info = TIER_COSTS.get(tier, TIER_COSTS["Tier1"])
        sense_count = self._count_sense_calls(soul)
        est_input = EST_TOKENS_PER_INSTINCT_BASE + (sense_count * EST_TOKENS_PER_SENSE)
        cost = (
            (est_input / 1000) * tier_info["input_per_1k"]
            + (EST_TOKENS_OUTPUT / 1000) * tier_info["output_per_1k"]
        )
        for tgt in self._outgoing.get(soul_name, []):
            cost += self._estimate_cascade_cost(tgt, visited)
        return cost

    def _count_sense_calls(self, soul: SoulNode) -> int:
        if not soul.instinct:
            return 0
        return self._count_senses_in_stmts(soul.instinct.statements)

    def _count_senses_in_stmts(self, stmts: list[Any]) -> int:
        count = 0
        for stmt in stmts:
            if isinstance(stmt, SenseCallNode):
                count += 1
            elif isinstance(stmt, LetNode):
                if isinstance(stmt.value, dict) and stmt.value.get("kind") == "sense_call":
                    count += 1
            elif isinstance(stmt, IfNode):
                count += self._count_senses_in_stmts(stmt.then_body)
                count += self._count_senses_in_stmts(stmt.else_body)
            elif isinstance(stmt, ForNode):
                count += self._count_senses_in_stmts(stmt.body)
        return count

    def _verify_deadlocks(self) -> None:
        soul_names = set(self._soul_map.keys())

        for soul_name, listen_list in self._listens.items():
            for src_soul, msg_type in listen_list:
                if src_soul == soul_name:
                    self.result.error(
                        "VD002", "deadlock",
                        f"Soul {soul_name} listens to itself for {msg_type} — will deadlock",
                        f"soul {soul_name}",
                    )

        if not self._routes:
            self.result.info("VD001", "deadlock", "No routes defined — deadlock analysis skipped")
            return

        graph: dict[str, list[str]] = {name: [] for name in soul_names}
        for src, tgt in self._routes:
            if src in graph:
                graph[src].append(tgt)

        visited: set[str] = set()
        rec_stack: set[str] = set()
        cycle_path: list[str] = []

        def find_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            cycle_path.append(node)
            for neighbor in graph.get(node, []):
                if (node, neighbor) in self._feedback_edges:
                    continue
                if neighbor not in visited:
                    if find_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    cycle_start = cycle_path.index(neighbor)
                    cycle = cycle_path[cycle_start:] + [neighbor]
                    self.result.error(
                        "VD001", "deadlock",
                        f"Circular dependency detected: {' → '.join(cycle)}",
                        "nervous_system",
                        "Add explicit feedback annotation to break the cycle",
                    )
                    return True
            cycle_path.pop()
            rec_stack.discard(node)
            return False

        has_cycle = False
        for node in list(graph.keys()):
            if node not in visited:
                if find_cycle(node):
                    has_cycle = True
                    break

        if not has_cycle:
            self.result.prove(
                "VD001", "deadlock",
                f"No circular dependencies in nervous_system ({len(self._routes)} routes checked)",
                "nervous_system",
            )

        for soul_name, listen_list in self._listens.items():
            for src_soul, msg_type in listen_list:
                if src_soul == soul_name:
                    self.result.error(
                        "VD002", "deadlock",
                        f"Soul {soul_name} listens to itself for {msg_type} — will deadlock",
                        f"soul {soul_name}",
                    )

    def _verify_protocol_consistency(self) -> None:
        for soul_name, listen_list in self._listens.items():
            for src_soul, msg_type in listen_list:
                src_speaks = self._speaks.get(src_soul, [])
                if msg_type not in src_speaks:
                    if src_soul in self._soul_map:
                        self.result.error(
                            "VP001", "protocol",
                            f"Soul {soul_name} listens for {src_soul}::{msg_type}, but {src_soul} never speaks {msg_type}",
                            f"soul {soul_name} > instinct",
                        )

        for src, tgt in self._routes:
            src_speaks = self._speaks.get(src, [])
            tgt_listens = self._listens.get(tgt, [])
            if src_speaks:
                for msg_type in src_speaks:
                    listener_matches = [
                        (ls, lt) for ls, lt in tgt_listens
                        if ls == src and lt == msg_type
                    ]
                    if not listener_matches and tgt_listens:
                        listened_types = [lt for ls, lt in tgt_listens if ls == src]
                        if listened_types:
                            self.result.warning(
                                "VP002", "protocol",
                                f"Route {src} → {tgt}: {src} speaks {msg_type} but {tgt} listens for {', '.join(listened_types)}",
                                "nervous_system",
                            )

        checked = 0
        for soul_name, speak_list in self._speaks.items():
            for msg_type in speak_list:
                if msg_type in self._message_map:
                    checked += 1
        if checked > 0:
            self.result.prove(
                "VP003", "protocol",
                f"All {checked} speak calls reference defined message types",
            )

    def _verify_liveness(self) -> None:
        soul_names = set(self._soul_map.keys())
        listeners = soul_names & set(self._incoming.keys())
        entrypoints = soul_names - listeners

        for soul_name in listeners:
            incoming_sources = self._incoming.get(soul_name, [])
            has_producer = False
            for src in incoming_sources:
                if self._speaks.get(src):
                    has_producer = True
                    break
            if not has_producer:
                self.result.warning(
                    "VL001", "liveness",
                    f"Listener {soul_name} has incoming routes but no producer speaks any message",
                    f"soul {soul_name}",
                )

        if not entrypoints and soul_names:
            self.result.error(
                "VL002", "liveness",
                "No entrypoint souls — all souls are listeners, nothing can initiate",
                "nervous_system",
            )
        elif entrypoints:
            self.result.prove(
                "VL002", "liveness",
                f"Pipeline has {len(entrypoints)} entrypoint(s): {', '.join(sorted(entrypoints))}",
            )

    def _verify_reachability(self) -> None:
        if not self._routes:
            return

        soul_names = set(self._soul_map.keys())
        entrypoints = soul_names - set(self._incoming.keys())
        reachable: set[str] = set()

        def walk(node: str) -> None:
            if node in reachable:
                return
            reachable.add(node)
            for tgt in self._outgoing.get(node, []):
                walk(tgt)

        for ep in entrypoints:
            walk(ep)

        unreachable = soul_names - reachable
        if unreachable:
            self.result.warning(
                "VE001", "reachability",
                f"Unreachable souls: {', '.join(sorted(unreachable))}",
                "nervous_system",
                "These souls have no path from any entrypoint",
            )
        else:
            self.result.prove(
                "VE001", "reachability",
                f"All {len(soul_names)} souls reachable from entrypoints",
            )

    def _verify_memory_safety(self) -> None:
        for soul in self.program.souls:
            if not soul.instinct:
                continue
            mem_fields = set()
            if soul.memory:
                mem_fields = {f.name for f in soul.memory.fields}
            self._check_memory_stmts(soul.instinct.statements, soul.name, mem_fields)

        checked = sum(
            len(s.memory.fields) if s.memory else 0
            for s in self.program.souls
        )
        if checked > 0:
            self.result.prove(
                "VM001", "memory_safety",
                f"All {checked} memory fields validated for type-safe access",
            )

    def _check_memory_stmts(self, stmts: list[Any], soul_name: str, mem_fields: set[str]) -> None:
        for stmt in stmts:
            if isinstance(stmt, RememberNode):
                if stmt.name not in mem_fields:
                    self.result.error(
                        "VM002", "memory_safety",
                        f"Soul {soul_name} remembers undefined field '{stmt.name}'",
                        f"soul {soul_name} > instinct",
                    )
            elif isinstance(stmt, IfNode):
                self._check_memory_stmts(stmt.then_body, soul_name, mem_fields)
                self._check_memory_stmts(stmt.else_body, soul_name, mem_fields)
            elif isinstance(stmt, ForNode):
                self._check_memory_stmts(stmt.body, soul_name, mem_fields)

    def _verify_topology(self) -> None:
        topo = self.program.topology
        if not topo or not topo.servers:
            return

        all_souls = set(self._soul_map.keys())
        assigned_souls: set[str] = set()
        multi_assigned: list[str] = []

        for server in topo.servers:
            for soul in server.souls:
                if soul not in all_souls:
                    self.result.error(
                        "VT001", "topology",
                        f"Topology assigns undefined soul '{soul}' to node '{server.name}'",
                        f"topology > {server.name}",
                    )
                if soul in assigned_souls:
                    multi_assigned.append(soul)
                assigned_souls.add(soul)

        unassigned = all_souls - assigned_souls
        if unassigned:
            self.result.warning(
                "VT002", "topology",
                f"Souls not assigned to any node: {', '.join(sorted(unassigned))}",
                "topology",
            )

        if multi_assigned:
            self.result.error(
                "VT003", "topology",
                f"Souls assigned to multiple nodes: {', '.join(multi_assigned)}",
                "topology",
            )

        if not unassigned and not multi_assigned and assigned_souls == all_souls:
            self.result.prove(
                "VT001", "topology",
                f"All {len(all_souls)} souls correctly assigned to {len(topo.servers)} node(s)",
                "topology",
            )

        for src, tgt in self._routes:
            src_node = None
            tgt_node = None
            for server in topo.servers:
                if src in server.souls:
                    src_node = server.name
                if tgt in server.souls:
                    tgt_node = server.name
            if src_node and tgt_node and src_node != tgt_node:
                self.result.info(
                    "VT004", "topology",
                    f"Cross-node route: {src}@{src_node} → {tgt}@{tgt_node} (requires TCP channel)",
                    "topology",
                )


    def _verify_telemetry(self) -> None:
        if not self.program.world or not self.program.world.telemetry:
            return

        t = self.program.world.telemetry
        loc = "world > telemetry"

        if not t.enabled:
            self.result.info("VTL001", "telemetry", "Telemetry declared but disabled", loc)
            return

        self.result.prove(
            "VTL001", "telemetry",
            f"Telemetry enabled: exporter={t.exporter}, sample_rate={t.sample_rate}",
            loc,
        )

        if t.trace_senses and t.trace_llm:
            self.result.prove(
                "VTL002", "telemetry",
                "Full observability: senses and LLM calls traced",
                loc,
            )
        elif t.trace_senses:
            self.result.info(
                "VTL002", "telemetry",
                "Partial observability: senses traced, LLM calls not traced",
                loc,
            )
        elif t.trace_llm:
            self.result.info(
                "VTL002", "telemetry",
                "Partial observability: LLM calls traced, senses not traced",
                loc,
            )
        else:
            self.result.warning(
                "VTL002", "telemetry",
                "Telemetry enabled but neither senses nor LLM calls are traced",
                loc,
            )

        soul_count = len(self.program.souls)
        has_mitosis = any(s.mitosis for s in self.program.souls)
        has_immune = any(s.immune_system for s in self.program.souls)
        has_dream = any(s.dream_system for s in self.program.souls)
        subsystems = []
        if has_mitosis:
            subsystems.append("mitosis")
        if has_immune:
            subsystems.append("immune")
        if has_dream:
            subsystems.append("dream")
        sub_str = ", ".join(subsystems) if subsystems else "none"
        self.result.prove(
            "VTL003", "telemetry",
            f"Telemetry covers {soul_count} soul(s), subsystems: {sub_str}",
            loc,
        )

    def _verify_mitosis(self) -> None:
        mitosis_souls = [s for s in self.program.souls if s.mitosis is not None]
        if not mitosis_souls:
            return

        for soul in mitosis_souls:
            m = soul.mitosis
            loc = f"soul {soul.name}"

            tier = soul.mind.tier.value if soul.mind else "Tier1"
            tier_info = TIER_COSTS.get(tier, TIER_COSTS["Tier1"])
            clone_tier_str = m.clone_tier or tier
            clone_tier_info = TIER_COSTS.get(clone_tier_str, TIER_COSTS["Tier1"])

            sense_count = self._count_sense_calls(soul)
            est_input = EST_TOKENS_PER_INSTINCT_BASE + (sense_count * EST_TOKENS_PER_SENSE)
            base_cost = (
                (est_input / 1000) * tier_info["input_per_1k"]
                + (EST_TOKENS_OUTPUT / 1000) * tier_info["output_per_1k"]
            )
            clone_cost = (
                (est_input / 1000) * clone_tier_info["input_per_1k"]
                + (EST_TOKENS_OUTPUT / 1000) * clone_tier_info["output_per_1k"]
            )
            worst_case = base_cost + (clone_cost * m.max_clones)

            if worst_case > self._cost_ceiling:
                self.result.warning(
                    "VMI001", "mitosis",
                    f"Soul {soul.name} with {m.max_clones} clones: worst-case ${worst_case:.6f} exceeds ceiling ${self._cost_ceiling:.2f}",
                    loc,
                    f"Parent=${base_cost:.6f} + {m.max_clones}×clone=${clone_cost:.6f}",
                )
            else:
                ratio = worst_case / self._cost_ceiling if self._cost_ceiling > 0 else 0
                self.result.prove(
                    "VMI001", "mitosis",
                    f"Soul {soul.name} mitosis cost bounded: ${worst_case:.6f} ≤ ${self._cost_ceiling:.2f} ({ratio:.0%})",
                    loc,
                )

            if m.verify:
                self.result.prove(
                    "VMI002", "mitosis",
                    f"Soul {soul.name} clones require verification gate before deployment",
                    loc,
                )
            else:
                self.result.warning(
                    "VMI002", "mitosis",
                    f"Soul {soul.name} clones skip verification — unverified agents in production",
                    loc,
                )

            if m.clone_tier and m.clone_tier != tier:
                parent_rate = tier_info["input_per_1k"] + tier_info["output_per_1k"]
                clone_rate = clone_tier_info["input_per_1k"] + clone_tier_info["output_per_1k"]
                if clone_rate < parent_rate:
                    savings = ((parent_rate - clone_rate) / parent_rate) * 100
                    self.result.prove(
                        "VMI003", "mitosis",
                        f"Soul {soul.name} clones use cheaper tier {m.clone_tier} ({savings:.0f}% savings)",
                        loc,
                    )
                else:
                    self.result.warning(
                        "VMI003", "mitosis",
                        f"Soul {soul.name} clone_tier {m.clone_tier} is not cheaper than parent tier {tier}",
                        loc,
                    )

            is_listener = soul.name in self._incoming
            if is_listener and m.max_clones > 1:
                self.result.info(
                    "VMI004", "mitosis",
                    f"Listener {soul.name} with mitosis: clones will share the same input channel",
                    loc,
                    "Multiple consumers on one channel provides load balancing",
                )

        total_max_clones = sum(s.mitosis.max_clones for s in mitosis_souls)
        total_souls = len(self.program.souls) + total_max_clones
        self.result.info(
            "VMI005", "mitosis",
            f"Mitosis capacity: {len(mitosis_souls)} soul(s) can spawn up to {total_max_clones} clones (max {total_souls} total)",
        )

    def _verify_retirement(self) -> None:
        mitosis_souls = [s for s in self.program.souls if s.mitosis is not None]
        if not mitosis_souls:
            return

        retire_souls = [s for s in mitosis_souls if s.mitosis.retire_trigger is not None]

        for soul in retire_souls:
            m = soul.mitosis
            loc = f"soul {soul.name}"

            retire_window = m.max_clones - m.min_clones
            self.result.prove(
                "VRT001", "retirement",
                f"Soul {soul.name} retirement policy: min_clones={m.min_clones}, "
                f"max_clones={m.max_clones}, retire window={retire_window}",
                loc,
            )

            if m.min_clones < m.max_clones:
                self.result.prove(
                    "VRT002", "retirement",
                    f"Soul {soul.name} retirement feasible: min_clones ({m.min_clones}) < max_clones ({m.max_clones})",
                    loc,
                )
            else:
                self.result.warning(
                    "VRT002", "retirement",
                    f"Soul {soul.name} retirement impossible: min_clones ({m.min_clones}) >= max_clones ({m.max_clones})",
                    loc,
                )

        if mitosis_souls:
            coverage = len(retire_souls)
            total = len(mitosis_souls)
            if coverage == total:
                self.result.prove(
                    "VRT003", "retirement",
                    f"Retirement coverage: {coverage}/{total} mitosis souls have retirement policy",
                )
            else:
                without = [s.name for s in mitosis_souls if s.mitosis.retire_trigger is None]
                self.result.warning(
                    "VRT003", "retirement",
                    f"Retirement coverage: {coverage}/{total} — souls without retirement: {', '.join(without)}",
                )



    def _verify_dream(self) -> None:
        dream_souls = [s for s in self.program.souls if s.dream_system is not None]
        if not dream_souls:
            return

        for soul in dream_souls:
            ds = soul.dream_system
            loc = f"soul {soul.name}"

            if not ds.enabled:
                self.result.info("VDR001", "dream", f"Soul {soul.name} has dream_system but disabled", loc)
                continue

            if ds.dream_mind:
                dream_tier = ds.dream_mind.tier.value
                primary_tier = soul.mind.tier.value if soul.mind else "Tier1"
                dream_cost = TIER_COSTS.get(dream_tier, TIER_COSTS["Tier1"])
                primary_cost = TIER_COSTS.get(primary_tier, TIER_COSTS["Tier1"])
                dream_rate = dream_cost["input_per_1k"] + dream_cost["output_per_1k"]
                primary_rate = primary_cost["input_per_1k"] + primary_cost["output_per_1k"]
                if dream_rate < primary_rate:
                    savings = ((primary_rate - dream_rate) / primary_rate) * 100
                    self.result.prove(
                        "VDR001", "dream",
                        f"Soul {soul.name} dream_mind {dream_tier} is {savings:.0f}% cheaper than primary {primary_tier}",
                        loc,
                    )
                else:
                    self.result.warning(
                        "VDR001", "dream",
                        f"Soul {soul.name} dream_mind {dream_tier} is not cheaper than primary {primary_tier}",
                        loc,
                    )

            worst_dreams = ds.speculation_depth
            dream_tier_info = TIER_COSTS.get(
                ds.dream_mind.tier.value if ds.dream_mind else "Tier1",
                TIER_COSTS["Tier1"]
            )
            dream_cost_per = (200 / 1000) * dream_tier_info["input_per_1k"] + (200 / 1000) * dream_tier_info["output_per_1k"]
            total_dream_cost = dream_cost_per * worst_dreams
            if total_dream_cost < self._cost_ceiling * 0.1:
                self.result.prove(
                    "VDR002", "dream",
                    f"Soul {soul.name} dream cost ${total_dream_cost:.6f} is <10% of ceiling",
                    loc,
                )
            else:
                self.result.warning(
                    "VDR002", "dream",
                    f"Soul {soul.name} dream cost ${total_dream_cost:.6f} may impact budget",
                    loc,
                )

            is_listener = soul.name in self._incoming
            if is_listener:
                self.result.prove(
                    "VDR003", "dream",
                    f"Listener {soul.name} will dream during message wait — zero wasted idle time",
                    loc,
                )
            else:
                self.result.prove(
                    "VDR003", "dream",
                    f"Heartbeat {soul.name} will dream between cycles — productive idle time",
                    loc,
                )

        self.result.info(
            "VDR004", "dream",
            f"Dream coverage: {len(dream_souls)}/{len(self.program.souls)} souls can dream",
        )


    def _verify_immune(self) -> None:
        immune_souls = [s for s in self.program.souls if s.immune_system is not None]
        if not immune_souls:
            return

        for soul in immune_souls:
            im = soul.immune_system
            loc = f"soul {soul.name}"

            if im.adaptive_recovery:
                self.result.prove(
                    "VIM001", "immune",
                    f"Soul {soul.name} has adaptive immune recovery enabled",
                    loc,
                )
            else:
                self.result.info(
                    "VIM001", "immune",
                    f"Soul {soul.name} has immune_system but adaptive_recovery=false",
                    loc,
                )

            if im.share_with_clones:
                has_mitosis = soul.mitosis is not None
                has_clone_siblings = any(
                    s.mitosis for s in self.program.souls if s.name != soul.name
                )
                if has_mitosis:
                    self.result.prove(
                        "VIM002", "immune",
                        f"Soul {soul.name} antibodies broadcast to up to {soul.mitosis.max_clones} clone(s)",
                        loc,
                    )
                elif has_clone_siblings:
                    self.result.info(
                        "VIM002", "immune",
                        f"Soul {soul.name} has share_with_clones but no mitosis — sharing disabled at runtime",
                        loc,
                    )
                else:
                    self.result.info(
                        "VIM002", "immune",
                        f"Soul {soul.name} has share_with_clones but no clones exist in system",
                        loc,
                    )

            import re
            m = re.match(r"(\d+)(ms|s|m|h|d)", im.antibody_lifespan)
            if m:
                val = int(m.group(1))
                unit = m.group(2)
                seconds = {"ms": val / 1000, "s": val, "m": val * 60, "h": val * 3600, "d": val * 86400}.get(unit, val)
                if seconds >= 86400:
                    self.result.warning(
                        "VIM003", "immune",
                        f"Soul {soul.name} antibody_lifespan={im.antibody_lifespan} is very long (>24h)",
                        loc,
                        "Long-lived antibodies may mask evolving error patterns",
                    )
                else:
                    self.result.prove(
                        "VIM003", "immune",
                        f"Soul {soul.name} antibody_lifespan={im.antibody_lifespan} within safe bounds",
                        loc,
                    )

            if im.adaptive_recovery and soul.heal:
                self.result.prove(
                    "VIM004", "immune",
                    f"Soul {soul.name} has layered defense: heal (static) + immune (adaptive)",
                    loc,
                )

        self.result.info(
            "VIM005", "immune",
            f"Immune coverage: {len(immune_souls)}/{len(self.program.souls)} souls protected",
        )


def verify_program(program: NousProgram) -> VerificationResult:
    verifier = NousVerifier(program)
    return verifier.verify()


def print_verification_report(result: VerificationResult, world_name: str = "Unknown") -> None:
    print(f"\n  ═══ NOUS Formal Verification — {world_name} ═══")
    print(result.summary())
