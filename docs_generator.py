"""
NOUS Documentation Generator v2.0 — Τεκμηρίωση (Tekmiriosi)
=============================================================
nous docs file.nous [-o output.html]
Generates HTML documentation with SVG nervous system diagram.
"""
from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from ast_nodes import (
    NousProgram, WorldNode, SoulNode, MessageNode, LawNode,
    RouteNode, MatchRouteNode, FanInNode, FanOutNode, FeedbackNode,
    LawCost, LawCurrency, LawDuration, LawBool, LawInt, LawConstitutional,
    NoesisConfigNode, ImportNode, TestNode,
    LetNode, RememberNode, SpeakNode, GuardNode, SenseCallNode,
    SleepNode, IfNode, ForNode,
)
from parser import parse_nous_file
from formatter import _fmt_expr, _fmt_args


CSS = """:root {
  --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #c9d1d9;
  --heading: #58a6ff; --accent: #7ee787; --warn: #d29922; --dim: #8b949e;
  --soul: #bb86fc; --msg: #03dac6; --law: #cf6679; --code-bg: #1c2128;
  --noesis: #f0883e; --import: #79c0ff; --test: #d2a8ff;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.6; padding: 2rem; max-width: 1060px; margin: 0 auto; }
h1 { color: var(--heading); font-size: 2rem; margin-bottom: 0.5rem; border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; }
h2 { color: var(--heading); font-size: 1.4rem; margin: 2rem 0 0.5rem; }
h3 { color: var(--dim); font-size: 1rem; margin: 1rem 0 0.3rem; text-transform: uppercase; letter-spacing: 0.05em; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 1.2rem; margin: 0.8rem 0; }
.soul-name { color: var(--soul); font-weight: bold; font-size: 1.2rem; }
.msg-name { color: var(--msg); font-weight: bold; font-size: 1.1rem; }
.law-name { color: var(--law); font-weight: bold; }
.field-name { color: var(--accent); font-family: monospace; }
.field-type { color: var(--dim); font-family: monospace; }
.route { padding: 0.3rem 0; font-family: monospace; color: var(--dim); }
.route .src { color: var(--soul); }
.route .tgt { color: var(--accent); }
.route .arrow { color: var(--dim); margin: 0 0.5rem; }
table { width: 100%; border-collapse: collapse; margin: 0.5rem 0; }
th, td { padding: 0.5rem 0.8rem; text-align: left; border-bottom: 1px solid var(--border); }
th { color: var(--heading); font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.04em; }
code { background: var(--code-bg); padding: 0.15rem 0.4rem; border-radius: 4px; font-size: 0.9rem; }
pre { background: var(--code-bg); padding: 1rem; border-radius: 6px; overflow-x: auto; font-size: 0.85rem; line-height: 1.5; margin: 0.5rem 0; }
pre code { background: none; padding: 0; }
.tag { display: inline-block; padding: 0.1rem 0.5rem; border-radius: 12px; font-size: 0.8rem; margin: 0.1rem; }
.tag-tier { background: #1a3a2a; color: var(--accent); }
.tag-tool { background: #1a2a3a; color: var(--heading); }
.tag-heal { background: #3a1a1a; color: var(--law); }
.toc { list-style: none; columns: 2; }
.toc li { padding: 0.2rem 0; }
.toc a { color: var(--heading); text-decoration: none; }
.toc a:hover { text-decoration: underline; }
.subtitle { color: var(--dim); font-size: 1rem; margin-bottom: 1.5rem; }
.stats { display: flex; gap: 1.5rem; flex-wrap: wrap; margin: 1rem 0; }
.stat { text-align: center; }
.stat-val { font-size: 1.8rem; font-weight: bold; color: var(--heading); }
.stat-label { font-size: 0.8rem; color: var(--dim); text-transform: uppercase; }
.kw { color: var(--soul); }
.fn { color: var(--accent); }
.str { color: var(--warn); }
.svg-container { text-align: center; margin: 1rem 0; overflow-x: auto; }
footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border); color: var(--dim); font-size: 0.85rem; text-align: center; }
"""


def _esc(text: Any) -> str:
    return html.escape(str(text))


def _law_value(law: LawNode) -> str:
    e = law.expr
    if isinstance(e, LawCost):
        sym = "$" if e.currency == "USD" else "E"
        return f"{sym}{e.amount:.2f} per {e.per}"
    if isinstance(e, LawCurrency):
        sym = "$" if e.currency == "USD" else "E"
        amt = int(e.amount) if e.amount == int(e.amount) else e.amount
        return f"{sym}{amt}"
    if isinstance(e, LawDuration):
        return f"{e.value}{e.unit}"
    if isinstance(e, LawBool):
        return str(e.value).lower()
    if isinstance(e, LawInt):
        return str(e.value)
    if isinstance(e, LawConstitutional):
        return f"constitutional({e.count})"
    return str(e)


def _cost_estimate(program: NousProgram) -> dict[str, Any]:
    tier_costs = {"Tier0A": 0.0, "Tier0B": 0.0, "Tier1": 0.003, "Tier2": 0.001, "Tier3": 0.0004}
    total_per_cycle = 0.0
    soul_costs: dict[str, float] = {}
    for soul in program.souls:
        if soul.mind:
            cost = tier_costs.get(soul.mind.tier.value, 0.001)
            soul_costs[soul.name] = cost
            total_per_cycle += cost
    heartbeat_minutes = 5
    if program.world and program.world.heartbeat:
        import re
        m = re.match(r"(\d+)(ms|s|m|h|d)", program.world.heartbeat)
        if m:
            val, unit = int(m.group(1)), m.group(2)
            heartbeat_minutes = {"ms": 1, "s": max(1, val // 60), "m": val, "h": val * 60, "d": val * 1440}.get(unit, 5)
    cycles_per_day = (24 * 60) // max(1, heartbeat_minutes)
    daily = total_per_cycle * cycles_per_day
    return {"per_cycle": total_per_cycle, "daily": daily, "monthly": daily * 30, "cycles_per_day": cycles_per_day, "soul_costs": soul_costs}


def _fmt_stmt_html(stmt: Any, depth: int = 0) -> list[str]:
    ind = "  " * depth
    if isinstance(stmt, LetNode):
        val = stmt.value
        if isinstance(val, dict):
            kind = val.get("kind", "")
            if kind == "listen":
                return [f'{ind}<span class="kw">let</span> {_esc(stmt.name)} = <span class="kw">listen</span> {_esc(val["soul"])}::{_esc(val["type"])}']
            if kind == "sense_call":
                args = _esc(_fmt_args(val.get("args", {})))
                return [f'{ind}<span class="kw">let</span> {_esc(stmt.name)} = <span class="kw">sense</span> <span class="fn">{_esc(val["tool"])}</span>({args})']
            if kind == "resonate":
                return [f'{ind}<span class="kw">let</span> {_esc(stmt.name)} = <span class="kw">resonate</span> <span class="str">"{_esc(val["query"])}"</span>']
        return [f'{ind}<span class="kw">let</span> {_esc(stmt.name)} = {_esc(_fmt_expr(stmt.value))}']
    if isinstance(stmt, RememberNode):
        return [f'{ind}<span class="kw">remember</span> {_esc(stmt.name)} {_esc(stmt.op)} {_esc(_fmt_expr(stmt.value))}']
    if isinstance(stmt, SpeakNode):
        args = _esc(_fmt_args(stmt.args))
        return [f'{ind}<span class="kw">speak</span> <span class="fn">{_esc(stmt.message_type)}</span>({args})']
    if isinstance(stmt, GuardNode):
        return [f'{ind}<span class="kw">guard</span> {_esc(_fmt_expr(stmt.condition))}']
    if isinstance(stmt, SenseCallNode):
        args = _esc(_fmt_args(stmt.args))
        return [f'{ind}<span class="kw">sense</span> <span class="fn">{_esc(stmt.tool_name)}</span>({args})']
    if isinstance(stmt, SleepNode):
        return [f'{ind}<span class="kw">sleep</span> {stmt.cycles}s']
    if isinstance(stmt, IfNode):
        lines = [f'{ind}<span class="kw">if</span> {_esc(_fmt_expr(stmt.condition))} {{']
        for s in stmt.then_body:
            lines.extend(_fmt_stmt_html(s, depth + 1))
        if stmt.else_body:
            lines.append(f'{ind}}} <span class="kw">else</span> {{')
            for s in stmt.else_body:
                lines.extend(_fmt_stmt_html(s, depth + 1))
        lines.append(f"{ind}}}")
        return lines
    if isinstance(stmt, ForNode):
        lines = [f'{ind}<span class="kw">for</span> {_esc(stmt.var_name)} <span class="kw">in</span> {_esc(_fmt_expr(stmt.iterable))} {{']
        for s in stmt.body:
            lines.extend(_fmt_stmt_html(s, depth + 1))
        lines.append(f"{ind}}}")
        return lines
    return [f"{ind}{_esc(_fmt_expr(stmt))}"]


def _gen_svg_diagram(program: NousProgram) -> str:
    if not program.nervous_system:
        return ""
    soul_names = [s.name for s in program.souls]
    if not soul_names:
        return ""
    sources: set[str] = set()
    targets: set[str] = set()
    for route in program.nervous_system.routes:
        if isinstance(route, RouteNode):
            sources.add(route.source); targets.add(route.target)
        elif isinstance(route, FanOutNode):
            sources.add(route.source); targets.update(route.targets)
        elif isinstance(route, FanInNode):
            sources.update(route.sources); targets.add(route.target)
        elif isinstance(route, MatchRouteNode):
            sources.add(route.source)
            for arm in route.arms:
                if arm.target and not arm.is_silence:
                    targets.add(arm.target)
    roots = [s for s in soul_names if s in sources and s not in targets]
    middles = [s for s in soul_names if s in sources and s in targets]
    leaves = [s for s in soul_names if s not in sources and s in targets]
    others = [s for s in soul_names if s not in sources and s not in targets]
    ordered = roots + middles + leaves + others
    col_assign: dict[str, int] = {}
    for s in roots:
        col_assign[s] = 0
    changed = True
    while changed:
        changed = False
        for route in program.nervous_system.routes:
            if isinstance(route, RouteNode):
                if route.source in col_assign and route.target not in col_assign:
                    col_assign[route.target] = col_assign[route.source] + 1; changed = True
            elif isinstance(route, FanOutNode):
                if route.source in col_assign:
                    for t in route.targets:
                        if t not in col_assign:
                            col_assign[t] = col_assign[route.source] + 1; changed = True
            elif isinstance(route, MatchRouteNode):
                if route.source in col_assign:
                    for arm in route.arms:
                        if arm.target and not arm.is_silence and arm.target not in col_assign:
                            col_assign[arm.target] = col_assign[route.source] + 1; changed = True
    for s in ordered:
        if s not in col_assign:
            col_assign[s] = 0
    cols: dict[int, list[str]] = {}
    for s in ordered:
        c = col_assign[s]
        cols.setdefault(c, []).append(s)
    box_w, box_h, col_gap, row_gap, pad = 130, 50, 180, 80, 40
    max_col = max(cols.keys()) if cols else 0
    max_rows = max(len(v) for v in cols.values()) if cols else 1
    svg_w = (max_col + 1) * (box_w + col_gap) - col_gap + pad * 2
    svg_h = max_rows * (box_h + row_gap) - row_gap + pad * 2
    node_x: dict[str, int] = {}
    node_y: dict[str, int] = {}
    for c, names in cols.items():
        total_h = len(names) * box_h + (len(names) - 1) * row_gap
        start_y = pad + (svg_h - pad * 2 - total_h) // 2
        for i, name in enumerate(names):
            node_x[name] = pad + c * (box_w + col_gap)
            node_y[name] = start_y + i * (box_h + row_gap)
    lines: list[str] = []
    lines.append(f'<svg viewBox="0 0 {svg_w} {svg_h}" xmlns="http://www.w3.org/2000/svg" style="max-width:{svg_w}px">')
    lines.append('<defs><marker id="ah" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto"><polygon points="0 0,10 3.5,0 7" fill="#8b949e"/></marker></defs>')
    for route in program.nervous_system.routes:
        edges: list[tuple[str, str]] = []
        if isinstance(route, RouteNode):
            edges.append((route.source, route.target))
        elif isinstance(route, FanOutNode):
            edges.extend((route.source, t) for t in route.targets)
        elif isinstance(route, FanInNode):
            edges.extend((s, route.target) for s in route.sources)
        elif isinstance(route, MatchRouteNode):
            edges.extend((route.source, arm.target) for arm in route.arms if arm.target and not arm.is_silence)
        for src, tgt in edges:
            if src in node_x and tgt in node_x:
                x1, y1 = node_x[src] + box_w, node_y[src] + box_h // 2
                x2, y2 = node_x[tgt], node_y[tgt] + box_h // 2
                lines.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#8b949e" stroke-width="2" marker-end="url(#ah)"/>')
    for name in ordered:
        if name not in node_x:
            continue
        x, y = node_x[name], node_y[name]
        lines.append(f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="8" fill="#161b22" stroke="#bb86fc" stroke-width="2"/>')
        lines.append(f'<text x="{x + box_w // 2}" y="{y + box_h // 2 + 5}" text-anchor="middle" fill="#bb86fc" font-family="sans-serif" font-size="14" font-weight="bold">{_esc(name)}</text>')
    lines.append('</svg>')
    return "\n".join(lines)


def generate_docs(program: NousProgram, source_path: str = "") -> str:
    world = program.world
    world_name = world.name if world else "Unknown"
    parts: list[str] = []
    parts.append('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">')
    parts.append('<meta name="viewport" content="width=device-width,initial-scale=1">')
    parts.append(f'<title>NOUS Docs — {_esc(world_name)}</title>')
    parts.append(f'<style>{CSS}</style></head><body>')
    soul_count = len(program.souls)
    msg_count = len(program.messages)
    law_count = len(world.laws) if world else 0
    costs = _cost_estimate(program)
    parts.append(f'<h1>NOUS — {_esc(world_name)}</h1>')
    parts.append(f'<p class="subtitle">Generated from <code>{_esc(source_path or "source")}</code> — {soul_count} souls, {msg_count} messages, {law_count} laws</p>')
    parts.append('<div class="stats">')
    parts.append(f'<div class="stat"><div class="stat-val">{soul_count}</div><div class="stat-label">Souls</div></div>')
    parts.append(f'<div class="stat"><div class="stat-val">{msg_count}</div><div class="stat-label">Messages</div></div>')
    parts.append(f'<div class="stat"><div class="stat-val">{law_count}</div><div class="stat-label">Laws</div></div>')
    parts.append(f'<div class="stat"><div class="stat-val">${costs["daily"]:.2f}</div><div class="stat-label">Daily Cost</div></div>')
    parts.append(f'<div class="stat"><div class="stat-val">{costs["cycles_per_day"]}</div><div class="stat-label">Cycles/Day</div></div>')
    parts.append('</div>')
    parts.append('<h2>Contents</h2><ul class="toc">')
    if program.imports:
        parts.append('<li><a href="#imports">Imports</a></li>')
    if program.noesis:
        parts.append('<li><a href="#noesis">Noesis</a></li>')
    parts.append('<li><a href="#world">World</a></li>')
    if program.messages:
        parts.append('<li><a href="#messages">Messages</a></li>')
    for soul in program.souls:
        parts.append(f'<li><a href="#soul-{_esc(soul.name)}">Soul: {_esc(soul.name)}</a></li>')
    if program.nervous_system:
        parts.append('<li><a href="#nervous-system">Nervous System</a></li>')
    parts.append('<li><a href="#costs">Cost Analysis</a></li>')
    if program.tests:
        parts.append('<li><a href="#tests">Tests</a></li>')
    parts.append('</ul>')
    if program.imports:
        parts.append('<h2 id="imports">Imports</h2><div class="card">')
        for imp in program.imports:
            if imp.path:
                parts.append(f'<p><span style="color:var(--import)">import</span> <code>"{_esc(imp.path)}"</code></p>')
            elif imp.package:
                parts.append(f'<p><span style="color:var(--import)">import</span> <code>{_esc(imp.package)}</code></p>')
        parts.append('</div>')
    if program.noesis:
        n = program.noesis
        parts.append('<h2 id="noesis">Noesis — Symbolic Intelligence</h2><div class="card">')
        parts.append('<table><tr><th>Setting</th><th>Value</th></tr>')
        if n.lattice_path:
            parts.append(f'<tr><td>Lattice</td><td><code>{_esc(n.lattice_path)}</code></td></tr>')
        parts.append(f'<tr><td>Oracle Threshold</td><td><code>{n.oracle_threshold}</code></td></tr>')
        parts.append(f'<tr><td>Auto Learn</td><td><code>{"true" if n.auto_learn else "false"}</code></td></tr>')
        parts.append(f'<tr><td>Auto Evolve</td><td><code>{"true" if n.auto_evolve else "false"}</code></td></tr>')
        parts.append(f'<tr><td>Gap Tracking</td><td><code>{"true" if n.gap_tracking else "false"}</code></td></tr>')
        parts.append('</table></div>')
    parts.append('<h2 id="world">World</h2><div class="card">')
    if world:
        parts.append(f'<p><strong>{_esc(world.name)}</strong></p>')
        if world.heartbeat:
            parts.append(f'<p>Heartbeat: <code>{_esc(world.heartbeat)}</code></p>')
        if world.timezone:
            parts.append(f'<p>Timezone: <code>{_esc(world.timezone)}</code></p>')
        if world.laws:
            parts.append('<h3>Laws</h3><table><tr><th>Name</th><th>Value</th><th>Type</th></tr>')
            for law in world.laws:
                kind = law.expr.kind if hasattr(law.expr, "kind") else "unknown"
                parts.append(f'<tr><td><span class="law-name">{_esc(law.name)}</span></td><td><code>{_esc(_law_value(law))}</code></td><td>{_esc(kind)}</td></tr>')
            parts.append('</table>')
    parts.append('</div>')
    if program.messages:
        parts.append('<h2 id="messages">Messages</h2>')
        for msg in program.messages:
            parts.append(f'<div class="card"><span class="msg-name">{_esc(msg.name)}</span>')
            if msg.fields:
                parts.append('<table><tr><th>Field</th><th>Type</th><th>Default</th></tr>')
                for f in msg.fields:
                    default = f'<code>{_esc(_fmt_expr(f.default))}</code>' if f.default is not None else '<span style="color:var(--dim)">—</span>'
                    parts.append(f'<tr><td><span class="field-name">{_esc(f.name)}</span></td><td class="field-type">{_esc(f.type_expr)}</td><td>{default}</td></tr>')
                parts.append('</table>')
            parts.append('</div>')
    for soul in program.souls:
        parts.append(f'<h2 id="soul-{_esc(soul.name)}">Soul: {_esc(soul.name)}</h2><div class="card">')
        if soul.mind:
            parts.append(f'<p>Mind: <code>{_esc(soul.mind.model)}</code> <span class="tag tag-tier">{_esc(soul.mind.tier.value)}</span></p>')
        if soul.senses:
            tags = " ".join(f'<span class="tag tag-tool">{_esc(s)}</span>' for s in soul.senses)
            parts.append(f'<p>Senses: {tags}</p>')
        if soul.memory and soul.memory.fields:
            parts.append('<h3>Memory</h3><table><tr><th>Field</th><th>Type</th><th>Default</th></tr>')
            for f in soul.memory.fields:
                default = f'<code>{_esc(_fmt_expr(f.default))}</code>' if f.default is not None else "—"
                parts.append(f'<tr><td>{_esc(f.name)}</td><td>{_esc(f.type_expr)}</td><td>{default}</td></tr>')
            parts.append('</table>')
        if soul.instinct and soul.instinct.statements:
            parts.append('<h3>Instinct</h3><pre><code>')
            for stmt in soul.instinct.statements:
                for line in _fmt_stmt_html(stmt, 0):
                    parts.append(line)
            parts.append('</code></pre>')
        if soul.dna and soul.dna.genes:
            parts.append('<h3>DNA</h3><table><tr><th>Gene</th><th>Value</th><th>Range</th></tr>')
            for g in soul.dna.genes:
                rng = ", ".join(_esc(_fmt_expr(r)) for r in g.range)
                parts.append(f'<tr><td>{_esc(g.name)}</td><td><code>{_esc(_fmt_expr(g.value))}</code></td><td>[{rng}]</td></tr>')
            parts.append('</table>')
        if soul.heal and soul.heal.rules:
            parts.append('<h3>Heal</h3>')
            for rule in soul.heal.rules:
                tags = " ".join(f'<span class="tag tag-heal">{_esc(a.strategy.value)}</span>' for a in rule.actions)
                parts.append(f'<p>on <code>{_esc(rule.error_type)}</code> => {tags}</p>')
        parts.append('</div>')
    if program.nervous_system:
        parts.append('<h2 id="nervous-system">Nervous System</h2>')
        svg = _gen_svg_diagram(program)
        if svg:
            parts.append(f'<div class="svg-container">{svg}</div>')
        parts.append('<div class="card">')
        for route in program.nervous_system.routes:
            if isinstance(route, RouteNode):
                parts.append(f'<div class="route"><span class="src">{_esc(route.source)}</span><span class="arrow">-></span><span class="tgt">{_esc(route.target)}</span></div>')
            elif isinstance(route, MatchRouteNode):
                parts.append(f'<div class="route"><span class="src">{_esc(route.source)}</span><span class="arrow">-> match</span></div>')
                for arm in route.arms:
                    tgt = "silence" if arm.is_silence else arm.target
                    parts.append(f'<div class="route" style="padding-left:2rem">{_esc(arm.condition)} => <span class="tgt">{_esc(tgt)}</span></div>')
            elif isinstance(route, FanInNode):
                srcs = ", ".join(f'<span class="src">{_esc(s)}</span>' for s in route.sources)
                parts.append(f'<div class="route">[{srcs}]<span class="arrow">-></span><span class="tgt">{_esc(route.target)}</span></div>')
            elif isinstance(route, FanOutNode):
                tgts = ", ".join(f'<span class="tgt">{_esc(t)}</span>' for t in route.targets)
                parts.append(f'<div class="route"><span class="src">{_esc(route.source)}</span><span class="arrow">-></span>[{tgts}]</div>')
            elif isinstance(route, FeedbackNode):
                parts.append(f'<div class="route"><span class="src">{_esc(route.source_soul)}::{_esc(route.source_field)}</span><span class="arrow">-></span><span class="tgt">{_esc(route.target_soul)}::{_esc(route.target_field)}</span></div>')
        parts.append('</div>')
    parts.append('<h2 id="costs">Cost Analysis</h2><div class="card">')
    parts.append('<table><tr><th>Soul</th><th>Tier</th><th>Cost/Cycle</th></tr>')
    for soul in program.souls:
        tier = soul.mind.tier.value if soul.mind else "—"
        cost = costs["soul_costs"].get(soul.name, 0)
        parts.append(f'<tr><td>{_esc(soul.name)}</td><td>{_esc(tier)}</td><td>${cost:.4f}</td></tr>')
    parts.append(f'<tr style="border-top:2px solid var(--border)"><td><strong>Total</strong></td><td></td><td><strong>${costs["per_cycle"]:.4f}</strong></td></tr>')
    parts.append('</table>')
    parts.append(f'<p style="margin-top:0.5rem;color:var(--dim)">{costs["cycles_per_day"]} cycles/day = <strong style="color:var(--accent)">${costs["daily"]:.2f}/day</strong> (${costs["monthly"]:.2f}/month)</p>')
    parts.append('</div>')
    if program.tests:
        parts.append('<h2 id="tests">Tests</h2><div class="card">')
        for test in program.tests:
            parts.append(f'<p><span class="tag" style="background:#2a1a3a;color:var(--test)">{_esc(test.name)}</span> — {len(test.asserts)} assertions</p>')
        parts.append('</div>')
    parts.append('<footer>Generated by NOUS Documentation Generator v2.0</footer>')
    parts.append('</body></html>')
    return "\n".join(parts)


def generate_docs_file(source_path: str, output_path: str | None = None) -> str:
    path = Path(source_path)
    program = parse_nous_file(path)
    html_content = generate_docs(program, source_path=path.name)
    out = Path(output_path) if output_path else path.with_suffix(".html")
    out.write_text(html_content, encoding="utf-8")
    return str(out)
