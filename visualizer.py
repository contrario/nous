"""
NOUS Visualizer — Ὅρασις (Horasis)
====================================
Generates self-contained HTML with Mermaid.js graph
of the nervous system, souls, routes, and wake strategies.
"""
from __future__ import annotations

import html
import sys
from pathlib import Path
from typing import Any, Optional

from ast_nodes import (
    NousProgram, SoulNode, RouteNode, FanInNode, FanOutNode,
    MatchRouteNode, FeedbackNode, SpeakNode, LetNode,
    LawCost,
)


class SoulVizInfo:
    __slots__ = ("name", "mind", "tier", "senses", "memory_fields",
                 "wake_strategy", "speaks", "listens", "gene_count", "heal_count")

    def __init__(self, name: str) -> None:
        self.name = name
        self.mind: str = ""
        self.tier: str = ""
        self.senses: list[str] = []
        self.memory_fields: int = 0
        self.wake_strategy: str = "HEARTBEAT"
        self.speaks: list[str] = []
        self.listens: list[str] = []
        self.gene_count: int = 0
        self.heal_count: int = 0


class RouteVizInfo:
    __slots__ = ("source", "target", "kind", "label")

    def __init__(self, source: str, target: str, kind: str = "direct", label: str = "") -> None:
        self.source = source
        self.target = target
        self.kind = kind
        self.label = label


class VizResult:
    __slots__ = ("world_name", "heartbeat", "cost_ceiling", "souls", "routes",
                 "entrypoints", "listeners", "html")

    def __init__(self) -> None:
        self.world_name: str = "Unknown"
        self.heartbeat: str = ""
        self.cost_ceiling: str = ""
        self.souls: list[SoulVizInfo] = []
        self.routes: list[RouteVizInfo] = []
        self.entrypoints: set[str] = set()
        self.listeners: set[str] = set()
        self.html: str = ""


def analyze_program(program: NousProgram) -> VizResult:
    result = VizResult()

    if program.world:
        result.world_name = program.world.name
        result.heartbeat = program.world.heartbeat or ""
        for law in program.world.laws:
            if isinstance(law.expr, LawCost) and law.expr.per == "cycle":
                result.cost_ceiling = f"${law.expr.amount:.2f}"

    raw_routes: list[tuple[str, str]] = []
    incoming: dict[str, list[str]] = {}

    if program.nervous_system:
        for route in program.nervous_system.routes:
            if isinstance(route, RouteNode):
                raw_routes.append((route.source, route.target))
            elif isinstance(route, FanInNode):
                for src in route.sources:
                    raw_routes.append((src, route.target))
            elif isinstance(route, FanOutNode):
                for tgt in route.targets:
                    raw_routes.append((route.source, tgt))
            elif isinstance(route, MatchRouteNode):
                for arm in route.arms:
                    if arm.target:
                        raw_routes.append((route.source, arm.target))
            elif isinstance(route, FeedbackNode):
                raw_routes.append((route.source_soul, route.target_soul))

    for src, tgt in raw_routes:
        incoming.setdefault(tgt, []).append(src)

    soul_names = {s.name for s in program.souls}
    result.listeners = soul_names & set(incoming.keys())
    result.entrypoints = soul_names - result.listeners

    speak_map: dict[str, list[str]] = {}
    listen_map: dict[str, list[str]] = {}

    for soul in program.souls:
        if soul.instinct:
            for stmt in soul.instinct.statements:
                if isinstance(stmt, SpeakNode):
                    speak_map.setdefault(soul.name, []).append(stmt.message_type)
                elif isinstance(stmt, dict):
                    if stmt.get("kind") == "speak":
                        speak_map.setdefault(soul.name, []).append(stmt.get("message_type", ""))
                    elif stmt.get("kind") == "listen":
                        listen_map.setdefault(soul.name, []).append(stmt.get("message_type", ""))
                elif isinstance(stmt, LetNode):
                    if isinstance(stmt.value, dict) and stmt.value.get("kind") == "listen":
                        listen_map.setdefault(soul.name, []).append(stmt.value.get("message_type", ""))

    for src, tgt in raw_routes:
        msgs = speak_map.get(src, [])
        label = ", ".join(msgs) if msgs else ""
        kind = "direct"
        if program.nervous_system:
            for route in program.nervous_system.routes:
                if isinstance(route, FeedbackNode) and route.source_soul == src and route.target_soul == tgt:
                    kind = "feedback"
                    break
                elif isinstance(route, MatchRouteNode) and route.source == src:
                    kind = "match"
                    break
                elif isinstance(route, FanInNode) and tgt == route.target and src in route.sources:
                    kind = "fan_in"
                    break
                elif isinstance(route, FanOutNode) and src == route.source and tgt in route.targets:
                    kind = "fan_out"
                    break
        result.routes.append(RouteVizInfo(src, tgt, kind, label))

    for soul in program.souls:
        info = SoulVizInfo(soul.name)
        if soul.mind:
            info.mind = soul.mind.model
            info.tier = soul.mind.tier.value
        info.senses = list(soul.senses)
        info.memory_fields = len(soul.memory.fields) if soul.memory else 0
        info.wake_strategy = "LISTENER" if soul.name in result.listeners else "HEARTBEAT"
        info.speaks = speak_map.get(soul.name, [])
        info.listens = listen_map.get(soul.name, [])
        info.gene_count = len(soul.dna.genes) if soul.dna else 0
        info.heal_count = len(soul.heal.rules) if soul.heal else 0
        result.souls.append(info)

    return result


def generate_mermaid(result: VizResult) -> str:
    lines: list[str] = []
    lines.append("graph TD")

    for soul in result.souls:
        sid = _safe_id(soul.name)
        label_parts = [f"<b>{html.escape(soul.name)}</b>"]
        if soul.mind:
            label_parts.append(f"🧠 {html.escape(soul.mind)} @ {html.escape(soul.tier)}")
        label_parts.append(f"⚡ {soul.wake_strategy}")
        if soul.senses:
            label_parts.append(f"👁 {len(soul.senses)} senses")
        if soul.memory_fields:
            label_parts.append(f"💾 {soul.memory_fields} fields")
        if soul.gene_count:
            label_parts.append(f"🧬 {soul.gene_count} genes")

        label = "<br/>".join(label_parts)

        if soul.wake_strategy == "HEARTBEAT":
            lines.append(f'    {sid}["{label}"]')
        else:
            lines.append(f'    {sid}(["{label}"])')

    for route in result.routes:
        src_id = _safe_id(route.source)
        tgt_id = _safe_id(route.target)
        if route.label:
            escaped = html.escape(route.label)
            if route.kind == "feedback":
                lines.append(f"    {src_id} -.->|{escaped}| {tgt_id}")
            else:
                lines.append(f"    {src_id} -->|{escaped}| {tgt_id}")
        else:
            if route.kind == "feedback":
                lines.append(f"    {src_id} -.-> {tgt_id}")
            else:
                lines.append(f"    {src_id} --> {tgt_id}")

    for soul in result.souls:
        sid = _safe_id(soul.name)
        if soul.wake_strategy == "HEARTBEAT":
            lines.append(f"    style {sid} fill:#2563eb,stroke:#1d4ed8,color:#ffffff,stroke-width:3px")
        else:
            lines.append(f"    style {sid} fill:#059669,stroke:#047857,color:#ffffff,stroke-width:2px")

    return "\n".join(lines)


def _safe_id(name: str) -> str:
    return name.replace(" ", "_").replace("-", "_")


def generate_html(result: VizResult, mermaid_code: str) -> str:
    world_esc = html.escape(result.world_name)
    hb_esc = html.escape(result.heartbeat) if result.heartbeat else "N/A"
    cost_esc = html.escape(result.cost_ceiling) if result.cost_ceiling else "N/A"
    soul_count = len(result.souls)
    route_count = len(result.routes)
    ep_count = len(result.entrypoints)
    ls_count = len(result.listeners)
    mermaid_esc = html.escape(mermaid_code)

    soul_cards = []
    for soul in result.souls:
        senses_html = ", ".join(f"<code>{html.escape(s)}</code>" for s in soul.senses) if soul.senses else "none"
        speaks_html = ", ".join(f"<code>{html.escape(s)}</code>" for s in soul.speaks) if soul.speaks else "none"
        listens_html = ", ".join(f"<code>{html.escape(s)}</code>" for s in soul.listens) if soul.listens else "none"
        badge_class = "badge-heartbeat" if soul.wake_strategy == "HEARTBEAT" else "badge-listener"
        card = f"""
        <div class="soul-card">
            <div class="soul-header">
                <span class="soul-name">{html.escape(soul.name)}</span>
                <span class="badge {badge_class}">{soul.wake_strategy}</span>
            </div>
            <div class="soul-detail"><strong>Mind:</strong> {html.escape(soul.mind or 'none')} @ {html.escape(soul.tier or 'N/A')}</div>
            <div class="soul-detail"><strong>Senses:</strong> {senses_html}</div>
            <div class="soul-detail"><strong>Speaks:</strong> {speaks_html}</div>
            <div class="soul-detail"><strong>Listens:</strong> {listens_html}</div>
            <div class="soul-detail"><strong>Memory:</strong> {soul.memory_fields} fields | <strong>Genes:</strong> {soul.gene_count} | <strong>Heal:</strong> {soul.heal_count} rules</div>
        </div>"""
        soul_cards.append(card)

    cards_html = "\n".join(soul_cards)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NOUS — {world_esc}</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
:root {{
    --bg: #0f172a;
    --surface: #1e293b;
    --border: #334155;
    --text: #e2e8f0;
    --text-dim: #94a3b8;
    --accent: #3b82f6;
    --heartbeat: #2563eb;
    --listener: #059669;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
}}
.container {{ max-width: 1400px; margin: 0 auto; padding: 2rem; }}
header {{
    text-align: center;
    padding: 2rem 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 2rem;
}}
header h1 {{ font-size: 2.5rem; font-weight: 700; letter-spacing: -0.02em; }}
header h1 span {{ color: var(--accent); }}
.stats {{
    display: flex;
    justify-content: center;
    gap: 2rem;
    margin-top: 1rem;
    flex-wrap: wrap;
}}
.stat {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.75rem 1.5rem;
    text-align: center;
}}
.stat-value {{ font-size: 1.5rem; font-weight: 700; color: var(--accent); }}
.stat-label {{ font-size: 0.75rem; text-transform: uppercase; color: var(--text-dim); letter-spacing: 0.05em; }}
.legend {{
    display: flex;
    justify-content: center;
    gap: 2rem;
    margin: 1.5rem 0;
}}
.legend-item {{
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.85rem;
    color: var(--text-dim);
}}
.legend-dot {{
    width: 14px;
    height: 14px;
    border-radius: 4px;
}}
.legend-dot.hb {{ background: var(--heartbeat); }}
.legend-dot.ls {{ background: var(--listener); border-radius: 50%; }}
.graph-container {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 2rem;
    margin-bottom: 2rem;
    overflow-x: auto;
}}
.graph-container .mermaid {{ display: flex; justify-content: center; }}
h2 {{
    font-size: 1.25rem;
    font-weight: 600;
    margin-bottom: 1rem;
    color: var(--text);
}}
.soul-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
    gap: 1rem;
    margin-bottom: 2rem;
}}
.soul-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.25rem;
}}
.soul-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
}}
.soul-name {{ font-size: 1.1rem; font-weight: 600; }}
.badge {{
    font-size: 0.7rem;
    font-weight: 600;
    padding: 0.2rem 0.6rem;
    border-radius: 999px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}}
.badge-heartbeat {{ background: var(--heartbeat); color: #fff; }}
.badge-listener {{ background: var(--listener); color: #fff; }}
.soul-detail {{
    font-size: 0.85rem;
    color: var(--text-dim);
    margin-bottom: 0.3rem;
}}
.soul-detail strong {{ color: var(--text); }}
.soul-detail code {{
    background: rgba(59, 130, 246, 0.15);
    padding: 0.1rem 0.4rem;
    border-radius: 4px;
    font-size: 0.8rem;
    color: var(--accent);
}}
footer {{
    text-align: center;
    padding: 1.5rem 0;
    border-top: 1px solid var(--border);
    color: var(--text-dim);
    font-size: 0.8rem;
}}
</style>
</head>
<body>
<div class="container">
    <header>
        <h1>Νοῦς — <span>{world_esc}</span></h1>
        <div class="stats">
            <div class="stat"><div class="stat-value">{soul_count}</div><div class="stat-label">Souls</div></div>
            <div class="stat"><div class="stat-value">{route_count}</div><div class="stat-label">Routes</div></div>
            <div class="stat"><div class="stat-value">{ep_count}</div><div class="stat-label">Entrypoints</div></div>
            <div class="stat"><div class="stat-value">{ls_count}</div><div class="stat-label">Listeners</div></div>
            <div class="stat"><div class="stat-value">{hb_esc}</div><div class="stat-label">Heartbeat</div></div>
            <div class="stat"><div class="stat-value">{cost_esc}</div><div class="stat-label">Cost Ceiling</div></div>
        </div>
    </header>

    <div class="legend">
        <div class="legend-item"><div class="legend-dot hb"></div> Heartbeat (Entrypoint — wakes on timer)</div>
        <div class="legend-item"><div class="legend-dot ls"></div> Listener (Sleeps until message arrives)</div>
    </div>

    <div class="graph-container">
        <pre class="mermaid">
{mermaid_esc}
        </pre>
    </div>

    <h2>Soul Details</h2>
    <div class="soul-grid">
{cards_html}
    </div>

    <footer>
        NOUS Visualizer — Ὅρασις (Horasis) | Generated from Living AST
    </footer>
</div>
<script>
mermaid.initialize({{
    startOnLoad: true,
    theme: 'dark',
    themeVariables: {{
        primaryColor: '#2563eb',
        primaryTextColor: '#ffffff',
        primaryBorderColor: '#1d4ed8',
        lineColor: '#64748b',
        secondaryColor: '#059669',
        tertiaryColor: '#1e293b',
        edgeLabelBackground: '#1e293b',
        fontSize: '14px',
    }},
    flowchart: {{
        curve: 'basis',
        padding: 20,
        htmlLabels: true,
    }},
}});
</script>
</body>
</html>"""


def visualize_program(program: NousProgram, output: Optional[Path] = None) -> Path:
    result = analyze_program(program)
    mermaid_code = generate_mermaid(result)
    html_content = generate_html(result, mermaid_code)
    result.html = html_content

    if output is None:
        world_name = result.world_name.lower().replace(" ", "_")
        output = Path(f"{world_name}_viz.html")

    output.write_text(html_content, encoding="utf-8")
    return output


def visualize_file(source: Path, output: Optional[Path] = None) -> Path:
    from parser import parse_nous_file
    program = parse_nous_file(source)
    return visualize_program(program, output)


def visualize_workspace(output: Optional[Path] = None) -> Path:
    from workspace import open_workspace
    ws = open_workspace()
    if ws is None:
        raise RuntimeError("No nous.toml found. Run 'nous init' first.")
    result = ws.build()
    if not result.ok:
        errors = [str(e) for e in result.errors[:5]]
        raise RuntimeError(f"Workspace build failed: {'; '.join(errors)}")
    if result.merged is None:
        raise RuntimeError("Workspace produced no merged program.")
    return visualize_program(result.merged, output)
