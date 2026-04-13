"""
NOUS Formatter v1.0 — nous fmt file.nous
=========================================
Parse → AST → Pretty Print with consistent style.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ast_nodes import (
    NousProgram, WorldNode, LawNode, LawCost, LawCurrency, LawDuration,
    LawConstitutional, LawBool, LawInt, SoulNode, MindNode,
    MemoryNode, FieldDeclNode, InstinctNode, DnaNode, GeneNode,
    HealNode, HealRuleNode, HealActionNode, HealStrategy,
    MessageNode, MessageFieldNode, NervousSystemNode, RouteNode,
    MatchRouteNode, MatchArmNode, FanInNode, FanOutNode, FeedbackNode,
    EvolutionNode, MutateBlockNode, MutateStrategyNode,
    PerceptionNode, PerceptionRuleNode,
    NoesisConfigNode, ImportNode, TestNode, TestAssertNode,
    LetNode, RememberNode, SpeakNode, GuardNode, SenseCallNode,
    SleepNode, IfNode, ForNode,
)
from parser import parse_nous, parse_nous_file


INDENT = "    "


def format_nous(source: str) -> str:
    program = parse_nous(source)
    return format_program(program)


def format_nous_file(path: str | Path) -> str:
    program = parse_nous_file(path)
    return format_program(program)


def format_program(p: NousProgram) -> str:
    sections: list[str] = []

    for imp in p.imports:
        sections.append(_fmt_import(imp))

    if p.noesis:
        sections.append(_fmt_noesis(p.noesis))

    if p.world:
        sections.append(_fmt_world(p.world))

    for msg in p.messages:
        sections.append(_fmt_message(msg))

    for soul in p.souls:
        sections.append(_fmt_soul(soul))

    if p.nervous_system:
        sections.append(_fmt_nervous_system(p.nervous_system))

    if p.evolution:
        sections.append(_fmt_evolution(p.evolution))

    if p.perception:
        sections.append(_fmt_perception(p.perception))

    for test in p.tests:
        sections.append(_fmt_test(test))

    return "\n\n".join(sections) + "\n"


# ── Import ──

def _fmt_import(node: ImportNode) -> str:
    if node.path:
        return f'import "{node.path}"'
    return f"import {node.package}"


# ── Noesis ──

def _fmt_noesis(node: NoesisConfigNode) -> str:
    lines = ["noesis {"]
    if node.lattice_path:
        lines.append(f'{INDENT}lattice: "{node.lattice_path}"')
    lines.append(f"{INDENT}oracle_threshold: {node.oracle_threshold}")
    lines.append(f"{INDENT}auto_learn: {'true' if node.auto_learn else 'false'}")
    lines.append(f"{INDENT}auto_evolve: {'true' if node.auto_evolve else 'false'}")
    lines.append(f"{INDENT}gap_tracking: {'true' if node.gap_tracking else 'false'}")
    lines.append("}")
    return "\n".join(lines)


# ── World ──

def _fmt_world(node: WorldNode) -> str:
    lines = [f"world {node.name} {{"]
    for law in node.laws:
        lines.append(f"{INDENT}{_fmt_law(law)}")
    if node.heartbeat:
        lines.append(f"{INDENT}heartbeat = {node.heartbeat}")
    if node.timezone:
        lines.append(f'{INDENT}timezone = "{node.timezone}"')
    for k, v in node.config.items():
        lines.append(f"{INDENT}{k} = {_fmt_expr(v)}")
    lines.append("}")
    return "\n".join(lines)


def _fmt_law(node: LawNode) -> str:
    return f"law {node.name} = {_fmt_law_expr(node.expr)}"


def _fmt_law_expr(expr: Any) -> str:
    if isinstance(expr, LawCost):
        sym = "$" if expr.currency == "USD" else "€"
        return f"{sym}{expr.amount:.2f} per cycle"
    if isinstance(expr, LawCurrency):
        sym = "$" if expr.currency == "USD" else "€"
        amt = int(expr.amount) if expr.amount == int(expr.amount) else expr.amount
        return f"{sym}{amt}"
    if isinstance(expr, LawDuration):
        return f"{expr.value}{expr.unit}"
    if isinstance(expr, LawConstitutional):
        return f"constitutional({expr.count})"
    if isinstance(expr, LawBool):
        return "true" if expr.value else "false"
    if isinstance(expr, LawInt):
        return str(expr.value)
    return str(expr)


# ── Message ──

def _fmt_message(node: MessageNode) -> str:
    lines = [f"message {node.name} {{"]
    for f in node.fields:
        default = f" = {_fmt_expr(f.default)}" if f.default is not None else ""
        lines.append(f"{INDENT}{f.name}: {f.type_expr}{default}")
    lines.append("}")
    return "\n".join(lines)


# ── Soul ──

def _fmt_soul(node: SoulNode) -> str:
    lines = [f"soul {node.name} {{"]
    if node.mind:
        lines.append(f"{INDENT}mind: {node.mind.model} @ {node.mind.tier.value}")
    if node.senses:
        slist = ", ".join(node.senses)
        lines.append(f"{INDENT}senses: [{slist}]")
    if node.memory:
        lines.append(_fmt_memory(node.memory))
    if node.instinct:
        lines.append(_fmt_instinct(node.instinct))
    if node.dna:
        lines.append(_fmt_dna(node.dna))
    if node.heal:
        lines.append(_fmt_heal(node.heal))
    lines.append("}")
    return "\n".join(lines)


def _fmt_memory(node: MemoryNode) -> str:
    if len(node.fields) <= 2:
        fields = ", ".join(
            f"{f.name}: {f.type_expr} = {_fmt_expr(f.default)}" for f in node.fields
        )
        return f"{INDENT}memory {{ {fields} }}"
    lines = [f"{INDENT}memory {{"]
    for f in node.fields:
        lines.append(f"{INDENT}{INDENT}{f.name}: {f.type_expr} = {_fmt_expr(f.default)}")
    lines.append(f"{INDENT}}}")
    return "\n".join(lines)


def _fmt_instinct(node: InstinctNode) -> str:
    lines = [f"{INDENT}instinct {{"]
    for stmt in node.statements:
        for line in _fmt_statement(stmt, 2):
            lines.append(line)
    lines.append(f"{INDENT}}}")
    return "\n".join(lines)


def _fmt_dna(node: DnaNode) -> str:
    if len(node.genes) <= 2:
        genes = ", ".join(
            f"{g.name}: {_fmt_expr(g.value)} ~ [{', '.join(_fmt_expr(r) for r in g.range)}]"
            for g in node.genes
        )
        return f"{INDENT}dna {{ {genes} }}"
    lines = [f"{INDENT}dna {{"]
    for g in node.genes:
        rng = ", ".join(_fmt_expr(r) for r in g.range)
        lines.append(f"{INDENT}{INDENT}{g.name}: {_fmt_expr(g.value)} ~ [{rng}]")
    lines.append(f"{INDENT}}}")
    return "\n".join(lines)


def _fmt_heal(node: HealNode) -> str:
    if len(node.rules) == 1 and len(node.rules[0].actions) <= 2:
        rule = node.rules[0]
        actions = " then ".join(_fmt_heal_action(a) for a in rule.actions)
        return f"{INDENT}heal {{ on {rule.error_type} => {actions} }}"
    lines = [f"{INDENT}heal {{"]
    for rule in node.rules:
        actions = " then ".join(_fmt_heal_action(a) for a in rule.actions)
        lines.append(f"{INDENT}{INDENT}on {rule.error_type} => {actions}")
    lines.append(f"{INDENT}}}")
    return "\n".join(lines)


def _fmt_heal_action(node: HealActionNode) -> str:
    p = node.params
    match node.strategy:
        case HealStrategy.RETRY:
            if "backoff" in p:
                return f"retry({p['max']}, {p['backoff']})"
            return "retry"
        case HealStrategy.LOWER:
            return f"lower({p['param']}, {_fmt_expr(p['delta'])})"
        case HealStrategy.RAISE:
            return f"raise({p['param']}, {_fmt_expr(p['delta'])})"
        case HealStrategy.HIBERNATE:
            return f"hibernate until {p['until']}"
        case HealStrategy.FALLBACK:
            return f"fallback({p['target']})"
        case HealStrategy.DELEGATE:
            return f"delegate({p['soul']})"
        case HealStrategy.ALERT:
            return f"alert({p['channel']})"
        case HealStrategy.SLEEP:
            return f"sleep {p['cycles']}s"
    return str(node.strategy.value)


# ── Statements ──

def _fmt_statement(stmt: Any, depth: int) -> list[str]:
    ind = INDENT * depth
    if isinstance(stmt, LetNode):
        val = stmt.value
        if isinstance(val, dict):
            kind = val.get("kind", "")
            if kind == "listen":
                if "world" in val:
                    return [f"{ind}let {stmt.name} = listen @{val['world']}::{val['soul']}::{val['type']}"]
                return [f"{ind}let {stmt.name} = listen {val['soul']}::{val['type']}"]
            if kind == "sense_call":
                args = _fmt_args(val.get("args", {}))
                return [f"{ind}let {stmt.name} = sense {val['tool']}({args})"]
            if kind == "resonate":
                guard = ""
                if val.get("guard_field"):
                    guard = f' with {val["guard_field"]} > {val["guard_threshold"]}'
                return [f'{ind}let {stmt.name} = resonate "{val["query"]}"{guard}']
        return [f"{ind}let {stmt.name} = {_fmt_expr(stmt.value)}"]
    if isinstance(stmt, RememberNode):
        return [f"{ind}remember {stmt.name} {stmt.op} {_fmt_expr(stmt.value)}"]
    if isinstance(stmt, SpeakNode):
        args = _fmt_args(stmt.args)
        if stmt.target_world:
            return [f"{ind}speak @{stmt.target_world}::{stmt.message_type}({args})"]
        return [f"{ind}speak {stmt.message_type}({args})"]
    if isinstance(stmt, GuardNode):
        return [f"{ind}guard {_fmt_expr(stmt.condition)}"]
    if isinstance(stmt, SenseCallNode):
        args = _fmt_args(stmt.args)
        return [f"{ind}sense {stmt.tool_name}({args})"]
    if isinstance(stmt, SleepNode):
        return [f"{ind}sleep {stmt.cycles}s"]
    if isinstance(stmt, IfNode):
        lines = [f"{ind}if {_fmt_expr(stmt.condition)} {{"]
        for s in stmt.then_body:
            lines.extend(_fmt_statement(s, depth + 1))
        if stmt.else_body:
            lines.append(f"{ind}}} else {{")
            for s in stmt.else_body:
                lines.extend(_fmt_statement(s, depth + 1))
        lines.append(f"{ind}}}")
        return lines
    if isinstance(stmt, ForNode):
        lines = [f"{ind}for {stmt.var_name} in {_fmt_expr(stmt.iterable)} {{"]
        for s in stmt.body:
            lines.extend(_fmt_statement(s, depth + 1))
        lines.append(f"{ind}}}")
        return lines
    if isinstance(stmt, dict):
        kind = stmt.get("kind", "")
        if kind == "resonate":
            return [f'{ind}resonate "{stmt["query"]}"']
    return [f"{ind}{_fmt_expr(stmt)}"]


# ── Nervous System ──

def _fmt_nervous_system(node: NervousSystemNode) -> str:
    lines = ["nervous_system {"]
    for route in node.routes:
        if isinstance(route, RouteNode):
            lines.append(f"{INDENT}{route.source} -> {route.target}")
        elif isinstance(route, MatchRouteNode):
            lines.append(f"{INDENT}{route.source} -> match {{")
            for arm in route.arms:
                if arm.is_silence:
                    lines.append(f"{INDENT}{INDENT}_ => silence,")
                else:
                    lines.append(f"{INDENT}{INDENT}{_fmt_expr(arm.condition)} => {arm.target},")
            lines.append(f"{INDENT}}}")
        elif isinstance(route, FanInNode):
            sources = ", ".join(route.sources)
            lines.append(f"{INDENT}[{sources}] -> {route.target}")
        elif isinstance(route, FanOutNode):
            targets = ", ".join(route.targets)
            lines.append(f"{INDENT}{route.source} -> [{targets}]")
        elif isinstance(route, FeedbackNode):
            lines.append(f"{INDENT}{route.source_soul}::{route.source_field} -> {route.target_soul}::{route.target_field}")
    lines.append("}")
    return "\n".join(lines)


# ── Evolution ──

def _fmt_evolution(node: EvolutionNode) -> str:
    lines = ["evolution {"]
    if node.schedule:
        lines.append(f"{INDENT}schedule: {node.schedule}")
    if node.fitness:
        lines.append(f"{INDENT}fitness: {_fmt_expr(node.fitness)}")
    for mut in node.mutations:
        lines.append(f"{INDENT}mutate {mut.target} {{")
        if mut.strategy:
            args = _fmt_args(mut.strategy.params)
            lines.append(f"{INDENT}{INDENT}strategy: {mut.strategy.name}({args})")
        if mut.survive_condition:
            lines.append(f"{INDENT}{INDENT}survive_if: {_fmt_expr(mut.survive_condition)}")
        if mut.rollback_condition:
            lines.append(f"{INDENT}{INDENT}rollback_if: {_fmt_expr(mut.rollback_condition)}")
        lines.append(f"{INDENT}}}")
    lines.append("}")
    return "\n".join(lines)


# ── Perception ──

def _fmt_perception(node: PerceptionNode) -> str:
    lines = ["perception {"]
    for rule in node.rules:
        trigger = rule.trigger
        if trigger.kind == "named" and len(trigger.args) == 2:
            trig_str = f'{trigger.name}("{trigger.args[0]}", {_fmt_expr(trigger.args[1])})'
        elif trigger.kind == "named":
            trig_str = f'{trigger.name}("{trigger.args[0]}")'
        else:
            trig_str = trigger.name
        action = rule.action
        if action.kind == "wake_all":
            act_str = "wake_all"
        elif action.kind == "wake":
            act_str = f"wake {action.target}"
        elif action.kind == "broadcast":
            act_str = f"broadcast {action.target}"
        else:
            act_str = f"alert {action.target}"
        lines.append(f"{INDENT}on {trig_str} => {act_str}")
    lines.append("}")
    return "\n".join(lines)


# ── Test ──

def _fmt_test(node: TestNode) -> str:
    lines = [f'test "{node.name}" {{']
    for a in node.asserts:
        lines.append(f"{INDENT}assert {_fmt_expr(a.condition)}")
    lines.append("}")
    return "\n".join(lines)


# ── Expressions ──

def _fmt_expr(expr: Any) -> str:
    if expr is None:
        return "null"
    if isinstance(expr, bool):
        return "true" if expr else "false"
    if isinstance(expr, int):
        return str(expr)
    if isinstance(expr, float):
        return f"{expr:g}"
    if isinstance(expr, str):
        if expr in ("self", "now()"):
            return expr
        if "." in expr and not expr.startswith('"'):
            return expr
        import re
        if expr and re.match(r'^[a-zA-Z_\u0370-\u03FF][a-zA-Z0-9_\u0370-\u03FF]*$', expr):
            return expr
        if expr and re.match(r'^\d+(ms|s|m|h|d)$', expr):
            return expr
        return f'"{expr}"'
    if isinstance(expr, list):
        if not expr:
            return "[]"
        items = ", ".join(_fmt_expr(e) for e in expr)
        return f"[{items}]"
    if isinstance(expr, dict):
        kind = expr.get("kind", "")
        if kind == "binop":
            left = _fmt_expr(expr["left"])
            right = _fmt_expr(expr["right"])
            op = expr["op"]
            return f"{left} {op} {right}"
        if kind == "not":
            return f"!{_fmt_expr(expr['operand'])}"
        if kind == "attr":
            return f"{_fmt_expr(expr['obj'])}.{expr['attr']}"
        if kind == "method_call":
            args = _fmt_args(expr.get("args", {}))
            return f"{_fmt_expr(expr['obj'])}.{expr['method']}({args})"
        if kind == "func_call":
            args = _fmt_args(expr.get("args", {}))
            return f"{expr['func']}({args})"
        if kind == "soul_field":
            return f"{expr['soul']}::{expr['field']}"
        if kind == "world_ref":
            return f"world.{expr['path']}"
        if kind == "inline_if":
            return f"if {_fmt_expr(expr['condition'])} {{ {_fmt_expr(expr['then'])} }} else {{ {_fmt_expr(expr['else'])} }}"
        if kind == "message_construct":
            args = _fmt_args(expr.get("args", {}))
            return f"{expr['type']}({args})"
        if kind == "listen":
            return f"listen {expr['soul']}::{expr['type']}"
        if kind == "sense_call":
            args = _fmt_args(expr.get("args", {}))
            return f"sense {expr['tool']}({args})"
        if kind == "resonate":
            return f'resonate "{expr["query"]}"'
        if "currency" in expr:
            sym = "$" if expr["currency"] == "USD" else "€"
            amt = expr["amount"]
            amt_s = f"{amt:.2f}" if amt != int(amt) else str(int(amt))
            return f"{sym}{amt_s}"
        if "_kv" in expr:
            return f"{expr['_kv'][0]}: {_fmt_expr(expr['_kv'][1])}"
        items = ", ".join(f"{k}: {_fmt_expr(v)}" for k, v in expr.items())
        return f"%{{{items}}}"
    return str(expr)


def _fmt_args(args: dict[str, Any]) -> str:
    if not args:
        return ""
    parts: list[str] = []
    for k, v in args.items():
        if k.startswith("_pos_"):
            parts.append(_fmt_expr(v))
        else:
            parts.append(f"{k}: {_fmt_expr(v)}")
    return ", ".join(parts)


# ── CLI Entry Point ──

def fmt_file(path: str | Path, *, write: bool = False, check: bool = False) -> tuple[str, bool]:
    p = Path(path)
    original = p.read_text(encoding="utf-8")
    formatted = format_nous(original)
    changed = original.rstrip() != formatted.rstrip()
    if write and changed:
        p.write_text(formatted, encoding="utf-8")
    return formatted, changed
