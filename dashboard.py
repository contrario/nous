"""
NOUS Web Dashboard — Πίνακας (Pinakas)
========================================
HTTP API server for monitoring running worlds + HTML dashboard.
Start: python3 dashboard.py [--port 8080]
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread
from typing import Any

from ast_nodes import NousProgram
from parser import parse_nous_file
from validator import validate_program
from codegen import generate_python

log = logging.getLogger("nous.dashboard")

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ΝΟΥΣ Dashboard</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--border:#30363d;--text:#c9d1d9;
--h:#58a6ff;--ok:#7ee787;--warn:#d29922;--err:#f85149;--dim:#8b949e;
--soul:#bb86fc;--msg:#03dac6}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
background:var(--bg);color:var(--text);padding:1.5rem}
h1{color:var(--h);font-size:1.8rem;margin-bottom:.5rem}
.sub{color:var(--dim);font-size:.9rem;margin-bottom:1.5rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:1rem}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:1rem}
.card h2{color:var(--h);font-size:1.1rem;margin-bottom:.8rem;border-bottom:1px solid var(--border);padding-bottom:.4rem}
.stat{display:flex;justify-content:space-between;padding:.3rem 0}
.stat .label{color:var(--dim)}
.stat .value{color:var(--text);font-weight:600}
.soul-card{border-left:3px solid var(--soul)}
.soul-name{color:var(--soul);font-weight:700;font-size:1rem}
.tag{display:inline-block;padding:.1rem .4rem;border-radius:10px;font-size:.75rem;margin:.1rem}
.tag-tier{background:#1a3a2a;color:var(--ok)}
.tag-tool{background:#1a2a3a;color:var(--h)}
.tag-ok{background:#1a3a2a;color:var(--ok)}
.tag-err{background:#3a1a1a;color:var(--err)}
.route{padding:.2rem 0;font-family:monospace;font-size:.85rem}
.route .src{color:var(--soul)}
.route .arr{color:var(--dim);margin:0 .3rem}
.route .tgt{color:var(--ok)}
.law{padding:.2rem 0}
.law-name{color:var(--err);font-weight:600}
.law-val{color:var(--text)}
.msg-type{color:var(--msg);font-weight:600}
.msg-field{color:var(--dim);font-size:.85rem;padding-left:1rem}
.refresh{color:var(--dim);font-size:.8rem;text-align:right;margin-top:.5rem}
.status-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:.4rem}
.status-ok{background:var(--ok)}
.status-err{background:var(--err)}
.topo-server{border-left:2px solid var(--h);padding-left:.8rem;margin:.4rem 0}
table{width:100%;border-collapse:collapse;margin:.5rem 0}
th,td{padding:.3rem .5rem;text-align:left;border-bottom:1px solid var(--border);font-size:.85rem}
th{color:var(--h);font-weight:600}
#error{color:var(--err);padding:.5rem;display:none}
</style>
</head>
<body>
<h1>ΝΟΥΣ Dashboard</h1>
<p class="sub" id="worldInfo">Loading...</p>
<div id="error"></div>
<div class="grid" id="dashboard"></div>
<p class="refresh" id="lastUpdate"></p>

<script>
const API = window.location.origin + '/api';
let data = null;

async function fetchData() {
  try {
    const r = await fetch(API + '/status');
    data = await r.json();
    document.getElementById('error').style.display = 'none';
    render();
  } catch(e) {
    document.getElementById('error').textContent = 'Connection lost: ' + e.message;
    document.getElementById('error').style.display = 'block';
  }
}

function render() {
  if (!data) return;
  const d = data;
  document.getElementById('worldInfo').textContent =
    `World: ${d.world_name} | ${d.soul_count} souls | ${d.message_count} messages | ${d.law_count} laws`;

  let html = '';

  // Overview card
  html += `<div class="card"><h2>Overview</h2>
    <div class="stat"><span class="label">Status</span><span class="value">
      <span class="status-dot ${d.valid ? 'status-ok' : 'status-err'}"></span>${d.valid ? 'VALID' : 'INVALID'}</span></div>
    <div class="stat"><span class="label">Parse Time</span><span class="value">${d.parse_ms.toFixed(1)}ms</span></div>
    <div class="stat"><span class="label">Generated Lines</span><span class="value">${d.generated_lines}</span></div>
    <div class="stat"><span class="label">Heartbeat</span><span class="value">${d.heartbeat || 'default'}</span></div>
    ${d.topology_servers > 0 ? `<div class="stat"><span class="label">Topology</span><span class="value">${d.topology_servers} servers</span></div>` : ''}
    ${d.test_count > 0 ? `<div class="stat"><span class="label">Tests</span><span class="value">${d.test_count}</span></div>` : ''}
  </div>`;

  // Laws card
  if (d.laws && d.laws.length) {
    html += `<div class="card"><h2>Laws</h2>`;
    d.laws.forEach(l => {
      html += `<div class="law"><span class="law-name">${l.name}</span> = <span class="law-val">${l.value}</span></div>`;
    });
    html += '</div>';
  }

  // Souls
  d.souls.forEach(s => {
    const tierTag = s.tier ? `<span class="tag tag-tier">${s.tier}</span>` : '';
    const tools = (s.tools || []).map(t => `<span class="tag tag-tool">${t}</span>`).join(' ');
    html += `<div class="card soul-card"><h2><span class="soul-name">${s.name}</span> ${tierTag}</h2>
      <div class="stat"><span class="label">Model</span><span class="value">${s.model || '—'}</span></div>
      <div class="stat"><span class="label">Memory</span><span class="value">${s.memory_fields} fields</span></div>
      <div class="stat"><span class="label">Instinct</span><span class="value">${s.instinct_stmts} stmts</span></div>
      <div class="stat"><span class="label">Sense Calls</span><span class="value">${s.sense_calls}</span></div>
      <div class="stat"><span class="label">Complexity</span><span class="value">${s.complexity}</span></div>
      ${tools ? `<div style="margin-top:.4rem">${tools}</div>` : ''}
    </div>`;
  });

  // Messages
  if (d.messages && d.messages.length) {
    html += `<div class="card"><h2>Messages</h2>`;
    d.messages.forEach(m => {
      html += `<div class="msg-type">${m.name}</div>`;
      (m.fields || []).forEach(f => {
        html += `<div class="msg-field">${f.name}: ${f.type}${f.default_ ? ' = ' + f.default_ : ''}</div>`;
      });
    });
    html += '</div>';
  }

  // Routes
  if (d.routes && d.routes.length) {
    html += `<div class="card"><h2>Nervous System</h2>`;
    d.routes.forEach(r => {
      html += `<div class="route"><span class="src">${r.source}</span><span class="arr">→</span><span class="tgt">${r.target}</span></div>`;
    });
    html += '</div>';
  }

  // Topology
  if (d.topology && d.topology.length) {
    html += `<div class="card"><h2>Topology</h2>`;
    d.topology.forEach(t => {
      html += `<div class="topo-server"><strong>${t.name}</strong>: <code>${t.host}</code><br>
        Souls: ${t.souls} | Port: ${t.port}</div>`;
    });
    html += '</div>';
  }

  // Cost
  if (d.cost) {
    html += `<div class="card"><h2>Cost Estimation</h2>
      <div class="stat"><span class="label">Per Cycle</span><span class="value">$${d.cost.per_cycle.toFixed(6)}</span></div>
      <div class="stat"><span class="label">Daily</span><span class="value">$${d.cost.daily.toFixed(2)}</span></div>
      <div class="stat"><span class="label">Monthly</span><span class="value">$${d.cost.monthly.toFixed(2)}</span></div>
      ${d.cost.ceiling > 0 ? `<div class="stat"><span class="label">Ceiling</span><span class="value">$${d.cost.ceiling.toFixed(2)}/cycle (${d.cost.utilization.toFixed(0)}%)</span></div>` : ''}
    </div>`;
  }

  document.getElementById('dashboard').innerHTML = html;
  document.getElementById('lastUpdate').textContent = 'Updated: ' + new Date().toLocaleTimeString();
}

fetchData();
setInterval(fetchData, 5000);
</script>
</body>
</html>"""


class DashboardState:
    def __init__(self) -> None:
        self.program: NousProgram | None = None
        self.source_path: str = ""
        self.parse_ms: float = 0
        self.generated_lines: int = 0
        self.valid: bool = False
        self.errors: list[str] = []

    def load(self, source_path: str) -> None:
        self.source_path = source_path
        t0 = time.perf_counter()
        self.program = parse_nous_file(source_path)
        self.parse_ms = (time.perf_counter() - t0) * 1000

        result = validate_program(self.program)
        self.valid = result.ok
        self.errors = [str(e) for e in result.errors]

        code = generate_python(self.program)
        self.generated_lines = len(code.splitlines())

    def to_json(self) -> dict[str, Any]:
        p = self.program
        if not p:
            return {"error": "No program loaded"}

        w = p.world
        data: dict[str, Any] = {
            "world_name": w.name if w else "Unknown",
            "soul_count": len(p.souls),
            "message_count": len(p.messages),
            "law_count": len(w.laws) if w else 0,
            "parse_ms": self.parse_ms,
            "generated_lines": self.generated_lines,
            "valid": self.valid,
            "errors": self.errors,
            "heartbeat": w.heartbeat if w else None,
            "test_count": len(p.tests),
            "topology_servers": len(p.topology.servers) if p.topology else 0,
        }

        data["laws"] = []
        if w:
            for law in w.laws:
                data["laws"].append({"name": law.name, "value": _format_law(law)})

        data["souls"] = []
        for soul in p.souls:
            s: dict[str, Any] = {
                "name": soul.name,
                "model": soul.mind.model if soul.mind else "",
                "tier": soul.mind.tier.value if soul.mind else "",
                "tools": list(soul.senses),
                "memory_fields": len(soul.memory.fields) if soul.memory else 0,
                "instinct_stmts": len(soul.instinct.statements) if soul.instinct else 0,
                "sense_calls": 0,
                "complexity": 0,
            }
            if soul.instinct:
                from profiler import _count_stmts
                counts = _count_stmts(soul.instinct.statements)
                s["sense_calls"] = counts["sense"]
                s["complexity"] = (
                    counts["total"] + counts["sense"] * 3
                    + counts["if"] * 2 + counts["for"] * 4
                    + counts["speak"] + counts["listen"] * 2
                )
            data["souls"].append(s)

        data["messages"] = []
        for msg in p.messages:
            data["messages"].append({
                "name": msg.name,
                "fields": [{"name": f.name, "type": f.type_expr, "default_": str(f.default) if f.default else ""} for f in msg.fields],
            })

        data["routes"] = []
        if p.nervous_system:
            from ast_nodes import RouteNode, FanInNode, FanOutNode
            for r in p.nervous_system.routes:
                if isinstance(r, RouteNode):
                    data["routes"].append({"source": r.source, "target": r.target})
                elif isinstance(r, FanInNode):
                    for src in r.sources:
                        data["routes"].append({"source": src, "target": r.target})
                elif isinstance(r, FanOutNode):
                    for tgt in r.targets:
                        data["routes"].append({"source": r.source, "target": tgt})

        data["topology"] = []
        if p.topology:
            for srv in p.topology.servers:
                souls = srv.config.get("souls", [])
                data["topology"].append({
                    "name": srv.name,
                    "host": srv.host,
                    "souls": ", ".join(str(s) for s in souls) if isinstance(souls, list) else str(souls),
                    "port": srv.config.get("port", 9100),
                })

        from profiler import TIER_COSTS, AVG_TOKENS_PER_CYCLE
        total_cost = 0
        hb_sec = 300
        if w and w.heartbeat:
            from codegen import NousCodeGen
            cg = NousCodeGen(p)
            hb_sec = cg._duration_to_seconds(w.heartbeat)
        for soul in p.souls:
            tier = soul.mind.tier.value if soul.mind else "Tier1"
            tc = TIER_COSTS.get(tier, TIER_COSTS["Tier1"])
            cost = (AVG_TOKENS_PER_CYCLE["input"] / 1e6) * tc["input"] + (AVG_TOKENS_PER_CYCLE["output"] / 1e6) * tc["output"]
            total_cost += cost
        cpd = 86400 / hb_sec
        ceiling = 0
        if w:
            from ast_nodes import LawCost
            for law in w.laws:
                if isinstance(law.expr, LawCost):
                    ceiling = law.expr.amount
        data["cost"] = {
            "per_cycle": total_cost,
            "daily": total_cost * cpd,
            "monthly": total_cost * cpd * 30,
            "ceiling": ceiling,
            "utilization": (total_cost / ceiling * 100) if ceiling > 0 else 0,
        }

        return data


def _format_law(law: Any) -> str:
    e = law.expr
    if e.kind == "cost":
        return f"${e.amount} {e.currency} per {e.per}"
    if e.kind == "currency":
        return f"${e.amount} {e.currency}"
    if e.kind == "duration":
        return f"{e.value}{e.unit}"
    if e.kind == "bool":
        return str(e.value).lower()
    if e.kind == "int":
        return str(e.value)
    if e.kind == "constitutional":
        return f"constitutional({e.count})"
    return str(e)


state = DashboardState()


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode())
        elif self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                if state.source_path:
                    state.load(state.source_path)
                data = state.to_json()
            except Exception as e:
                data = {"error": str(e)}
            self.wfile.write(json.dumps(data).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        pass


def start_dashboard(source_path: str, port: int = 8080) -> None:
    state.load(source_path)
    world_name = state.program.world.name if state.program and state.program.world else "?"

    server = HTTPServer(("0.0.0.0", port), DashboardHandler)
    print(f"ΝΟΥΣ Dashboard — {world_name}")
    print(f"  http://localhost:{port}")
    print(f"  http://0.0.0.0:{port}")
    print(f"  Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
        server.shutdown()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="NOUS Dashboard")
    ap.add_argument("file", help=".nous file to monitor")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    start_dashboard(args.file, args.port)
