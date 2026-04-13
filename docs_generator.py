"""
NOUS Documentation Generator — Τεκμηρίωση (Tekmiriosi)
========================================================
Generates HTML documentation from .nous source files.
"""
from __future__ import annotations

import html
import sys
from pathlib import Path
from typing import Any

from ast_nodes import (
    NousProgram, WorldNode, SoulNode, MessageNode, LawNode,
    RouteNode, MatchRouteNode, FanInNode, FanOutNode, FeedbackNode,
    LawCost, LawDuration, LawBool, LawInt, LawConstitutional, LawCurrency,
    TopologyNode,
)
from parser import parse_nous_file
from validator import validate_program

CSS = """
:root { --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #c9d1d9;
  --heading: #58a6ff; --accent: #7ee787; --warn: #d29922; --dim: #8b949e;
  --soul: #bb86fc; --msg: #03dac6; --law: #cf6679; --code-bg: #1c2128; }
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.6; padding: 2rem; max-width: 960px; margin: 0 auto; }
h1 { color: var(--heading); font-size: 2rem; margin-bottom: 0.5rem; border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; }
h2 { color: var(--heading); font-size: 1.4rem; margin: 1.5rem 0 0.5rem; }
h3 { color: var(--dim); font-size: 1.1rem; margin: 1rem 0 0.3rem; text-transform: uppercase; letter-spacing: 0.05em; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 1.2rem; margin: 0.8rem 0; }
.soul-name { color: var(--soul); font-weight: bold; font-size: 1.2rem; }
.msg-name { color: var(--msg); font-weight: bold; }
.law-name { color: var(--law); font-weight: bold; }
.field { display: flex; gap: 0.5rem; padding: 0.2rem 0; }
.field-name { color: var(--accent); min-width: 120px; }
.field-type { color: var(--dim); }
.field-default { color: var(--warn); }
.route { padding: 0.3rem 0; font-family: monospace; color: var(--dim); }
.route .src { color: var(--soul); }
.route .tgt { color: var(--accent); }
.route .arrow { color: var(--dim); margin: 0 0.5rem; }
table { width: 100%; border-collapse: collapse; margin: 0.5rem 0; }
th, td { padding: 0.5rem 0.8rem; text-align: left; border-bottom: 1px solid var(--border); }
th { color: var(--heading); font-size: 0.9rem; }
code { background: var(--code-bg); padding: 0.15rem 0.4rem; border-radius: 4px; font-size: 0.9rem; }
.tag { display: inline-block; padding: 0.1rem 0.5rem; border-radius: 12px; font-size: 0.8rem; margin: 0.1rem; }
.tag-tier { background: #1a3a2a; color: var(--accent); }
.tag-tool { background: #1a2a3a; color: var(--heading); }
.tag-heal { background: #3a1a1a; color: var(--law); }
.toc { list-style: none; }
.toc li { padding: 0.2rem 0; }
.toc a { color: var(--heading); text-decoration: none; }
.toc a:hover { text-decoration: underline; }
.badge { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.85rem; font-weight: bold; }
.badge-ok { background: #1a3a2a; color: var(--accent); }
.badge-err { background: #3a1a1a; color: var(--law); }
.subtitle { color: var(--dim); font-size: 1rem; margin-bottom: 1.5rem; }
.topology-server { border-left: 3px solid var(--heading); padding-left: 1rem; margin: 0.5rem 0; }
nav { position: sticky; top: 1rem; }
footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border); color: var(--dim); font-size: 0.85rem; text-align: center; }
"""


def _esc(text: Any) -> str:
    return html.escape(str(text))


def _law_value(law: LawNode) -> str:
    e = law.expr
    if isinstance(e, LawCost):
        return f"${e.amount} {e.currency} per {e.per}"
    if isinstance(e, LawCurrency):
        return f"${e.amount} {e.currency}"
    if isinstance(e, LawDuration):
        return f"{e.value}{e.unit}"
    if isinstance(e, LawBool):
        return str(e.value).lower()
    if isinstance(e, LawInt):
        return str(e.value)
    if isinstance(e, LawConstitutional):
        return f"constitutional({e.count})"
    return str(e)


def generate_docs(program: NousProgram, source_path: str = "") -> str:
    world = program.world
    world_name = world.name if world else "Unknown"
    result = validate_program(program)

    parts: list[str] = []
    parts.append(f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>")
    parts.append(f"<meta name='viewport' content='width=device-width,initial-scale=1'>")
    parts.append(f"<title>NOUS Docs — {_esc(world_name)}</title>")
    parts.append(f"<style>{CSS}</style></head><body>")

    # Header
    parts.append(f"<h1>ΝΟΥΣ — {_esc(world_name)}</h1>")
    status = '<span class="badge badge-ok">VALID</span>' if result.ok else f'<span class="badge badge-err">{len(result.errors)} ERRORS</span>'
    parts.append(f'<p class="subtitle">Generated from <code>{_esc(source_path or "source")}</code> | {status}</p>')

    # TOC
    parts.append('<h2>Contents</h2><ul class="toc">')
    parts.append('<li><a href="#world">World</a></li>')
    if program.messages:
        parts.append('<li><a href="#messages">Messages</a></li>')
    for soul in program.souls:
        parts.append(f'<li><a href="#soul-{_esc(soul.name)}">{_esc(soul.name)}</a></li>')
    if program.nervous_system:
        parts.append('<li><a href="#nervous-system">Nervous System</a></li>')
    if program.topology:
        parts.append('<li><a href="#topology">Topology</a></li>')
    parts.append('</ul>')

    # World
    parts.append('<h2 id="world">World</h2><div class="card">')
    if world:
        parts.append(f'<p><strong>{_esc(world.name)}</strong></p>')
        if world.heartbeat:
            parts.append(f'<p>Heartbeat: <code>{_esc(world.heartbeat)}</code></p>')
        if world.timezone:
            parts.append(f'<p>Timezone: <code>{_esc(world.timezone)}</code></p>')
        if world.laws:
            parts.append('<h3>Laws</h3><table><tr><th>Name</th><th>Value</th></tr>')
            for law in world.laws:
                parts.append(f'<tr><td><span class="law-name">{_esc(law.name)}</span></td><td><code>{_esc(_law_value(law))}</code></td></tr>')
            parts.append('</table>')
    parts.append('</div>')

    # Messages
    if program.messages:
        parts.append('<h2 id="messages">Messages</h2>')
        for msg in program.messages:
            parts.append(f'<div class="card"><span class="msg-name">{_esc(msg.name)}</span>')
            if msg.fields:
                for f in msg.fields:
                    default = f' = <span class="field-default">{_esc(f.default)}</span>' if f.default is not None else ""
                    parts.append(f'<div class="field"><span class="field-name">{_esc(f.name)}</span><span class="field-type">{_esc(f.type_expr)}</span>{default}</div>')
            parts.append('</div>')

    # Souls
    for soul in program.souls:
        parts.append(f'<h2 id="soul-{_esc(soul.name)}">Soul: {_esc(soul.name)}</h2><div class="card">')
        parts.append(f'<p class="soul-name">{_esc(soul.name)}</p>')
        if soul.mind:
            parts.append(f'<p>Mind: <code>{_esc(soul.mind.model)}</code> <span class="tag tag-tier">{_esc(soul.mind.tier.value)}</span></p>')
        if soul.senses:
            tags = " ".join(f'<span class="tag tag-tool">{_esc(s)}</span>' for s in soul.senses)
            parts.append(f'<p>Senses: {tags}</p>')
        if soul.memory and soul.memory.fields:
            parts.append('<h3>Memory</h3>')
            for f in soul.memory.fields:
                default = f' = <span class="field-default">{_esc(f.default)}</span>' if f.default is not None else ""
                parts.append(f'<div class="field"><span class="field-name">{_esc(f.name)}</span><span class="field-type">{_esc(f.type_expr)}</span>{default}</div>')
        if soul.dna and soul.dna.genes:
            parts.append('<h3>DNA</h3>')
            for g in soul.dna.genes:
                rng = ", ".join(str(v) for v in g.range)
                parts.append(f'<div class="field"><span class="field-name">{_esc(g.name)}</span><span class="field-default">{_esc(g.value)}</span><span class="field-type">~ [{rng}]</span></div>')
        if soul.heal and soul.heal.rules:
            tags = " ".join(f'<span class="tag tag-heal">{_esc(r.error_type)}</span>' for r in soul.heal.rules)
            parts.append(f'<p>Heal: {tags}</p>')
        parts.append('</div>')

    # Nervous System
    if program.nervous_system:
        ns = program.nervous_system
        parts.append('<h2 id="nervous-system">Nervous System</h2><div class="card">')
        for route in ns.routes:
            if isinstance(route, RouteNode):
                parts.append(f'<div class="route"><span class="src">{_esc(route.source)}</span><span class="arrow">→</span><span class="tgt">{_esc(route.target)}</span></div>')
            elif isinstance(route, MatchRouteNode):
                parts.append(f'<div class="route"><span class="src">{_esc(route.source)}</span><span class="arrow">→ match</span></div>')
                for arm in route.arms:
                    tgt = "silence" if arm.is_silence else arm.target
                    parts.append(f'<div class="route" style="padding-left:2rem">{_esc(arm.condition)} ⇒ <span class="tgt">{_esc(tgt)}</span></div>')
            elif isinstance(route, FanInNode):
                srcs = ", ".join(f'<span class="src">{_esc(s)}</span>' for s in route.sources)
                parts.append(f'<div class="route">[{srcs}]<span class="arrow">→</span><span class="tgt">{_esc(route.target)}</span></div>')
            elif isinstance(route, FanOutNode):
                tgts = ", ".join(f'<span class="tgt">{_esc(t)}</span>' for t in route.targets)
                parts.append(f'<div class="route"><span class="src">{_esc(route.source)}</span><span class="arrow">→</span>[{tgts}]</div>')
        parts.append('</div>')

    # Topology
    if program.topology:
        parts.append('<h2 id="topology">Topology</h2><div class="card">')
        for srv in program.topology.servers:
            souls = srv.config.get("souls", [])
            soul_list = ", ".join(str(s) for s in souls) if isinstance(souls, list) else str(souls)
            port = srv.config.get("port", 9100)
            parts.append(f'<div class="topology-server">')
            parts.append(f'<p><strong>{_esc(srv.name)}</strong>: <code>{_esc(srv.host)}</code></p>')
            parts.append(f'<p>Souls: {_esc(soul_list)} | Port: {_esc(port)}</p>')
            parts.append('</div>')
        parts.append('</div>')

    # Footer
    parts.append(f'<footer>Generated by NOUS Documentation Generator v1.8.0</footer>')
    parts.append('</body></html>')
    return "\n".join(parts)


def generate_docs_file(source_path: str, output_path: str | None = None) -> str:
    path = Path(source_path)
    program = parse_nous_file(path)
    html_content = generate_docs(program, source_path=path.name)
    out = Path(output_path) if output_path else path.with_suffix(".html")
    out.write_text(html_content, encoding="utf-8")
    return str(out)
