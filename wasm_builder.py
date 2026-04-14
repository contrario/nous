"""
NOUS WASM Builder — Πακέτο (Paketo)
======================================
Bundles generated JavaScript into a self-contained HTML file
with runtime dashboard, or outputs standalone .mjs module.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ast_nodes import NousProgram
from codegen_js import generate_javascript


def build_html(program: NousProgram, output: Optional[Path] = None) -> Path:
    js_code = generate_javascript(program)
    world_name = program.world.name if program.world else "Unknown"
    soul_names = [s.name for s in program.souls]
    soul_cards = ""
    for soul in program.souls:
        mind = f"{soul.mind.model} @ {soul.mind.tier.value}" if soul.mind else "none"
        senses = ", ".join(soul.senses) if soul.senses else "none"
        mem_count = len(soul.memory.fields) if soul.memory else 0
        soul_cards += f"""
        <div class="soul-card">
          <div class="soul-name">{soul.name}</div>
          <div class="soul-detail">Mind: {mind}</div>
          <div class="soul-detail">Senses: {senses}</div>
          <div class="soul-detail">Memory fields: {mem_count}</div>
          <div class="soul-detail">Cycles: <span id="cycles-{soul.name}">0</span></div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NOUS — {world_name}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #0f172a; color: #e2e8f0; font-family: 'JetBrains Mono', 'Fira Code', monospace; padding: 20px; }}
  .header {{ text-align: center; margin-bottom: 24px; }}
  .header h1 {{ font-size: 28px; color: #60a5fa; }}
  .header .subtitle {{ color: #94a3b8; font-size: 14px; margin-top: 4px; }}
  .stats {{ display: flex; gap: 16px; justify-content: center; margin-bottom: 20px; flex-wrap: wrap; }}
  .stat {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 12px 20px; text-align: center; }}
  .stat .label {{ color: #94a3b8; font-size: 11px; text-transform: uppercase; }}
  .stat .value {{ color: #f1f5f9; font-size: 22px; font-weight: bold; margin-top: 4px; }}
  .controls {{ text-align: center; margin-bottom: 20px; }}
  .btn {{ background: #2563eb; color: white; border: none; padding: 10px 24px; border-radius: 6px; cursor: pointer; font-family: inherit; font-size: 14px; margin: 0 6px; }}
  .btn:hover {{ background: #3b82f6; }}
  .btn.stop {{ background: #dc2626; }}
  .btn.stop:hover {{ background: #ef4444; }}
  .souls-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-bottom: 20px; }}
  .soul-card {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 16px; }}
  .soul-name {{ color: #60a5fa; font-size: 16px; font-weight: bold; margin-bottom: 8px; }}
  .soul-detail {{ color: #94a3b8; font-size: 12px; margin: 2px 0; }}
  .log-container {{ background: #0a0f1a; border: 1px solid #1e293b; border-radius: 8px; padding: 16px; max-height: 400px; overflow-y: auto; }}
  .log-container h3 {{ color: #60a5fa; margin-bottom: 8px; font-size: 14px; }}
  #nous-log {{ font-size: 12px; color: #94a3b8; white-space: pre-wrap; word-break: break-all; }}
</style>
</head>
<body>
<div class="header">
  <h1>NOUS — {world_name}</h1>
  <div class="subtitle">JavaScript Runtime | Browser Agent Execution</div>
</div>
<div class="stats">
  <div class="stat"><div class="label">Souls</div><div class="value">{len(soul_names)}</div></div>
  <div class="stat"><div class="label">Status</div><div class="value" id="status">Starting</div></div>
  <div class="stat"><div class="label">Total Cycles</div><div class="value" id="total-cycles">0</div></div>
</div>
<div class="controls">
  <button class="btn" onclick="window.location.reload()">Restart</button>
  <button class="btn stop" onclick="nousStop()">Stop</button>
</div>
<div class="souls-grid">
  {soul_cards}
</div>
<div class="log-container">
  <h3>Runtime Log</h3>
  <pre id="nous-log"></pre>
</div>
<script>
{js_code}

document.getElementById('status').textContent = 'Running';

setInterval(() => {{
  let total = 0;
  for (const [name, soul] of Object.entries(runtime.souls)) {{
    const el = document.getElementById('cycles-' + name);
    if (el) el.textContent = soul.cycleCount;
    total += soul.cycleCount;
  }}
  document.getElementById('total-cycles').textContent = total;
  if (!runtime.running) {{
    document.getElementById('status').textContent = 'Stopped';
  }}
}}, 1000);
</script>
</body>
</html>"""

    if output is None:
        safe_name = world_name.lower().replace(" ", "_")
        output = Path(f"{safe_name}_wasm.html")
    output.write_text(html, encoding="utf-8")
    return output


def build_module(program: NousProgram, output: Optional[Path] = None) -> Path:
    js_code = generate_javascript(program)
    world_name = program.world.name if program.world else "Unknown"
    if output is None:
        safe_name = world_name.lower().replace(" ", "_")
        output = Path(f"{safe_name}.mjs")
    output.write_text(js_code, encoding="utf-8")
    return output


def build_wasm_target(source: Path, output: Optional[Path] = None, target: str = "html") -> Path:
    from parser import parse_nous_file
    program = parse_nous_file(source)
    if target == "html" or target == "wasm":
        return build_html(program, output)
    elif target == "js" or target == "mjs":
        return build_module(program, output)
    else:
        raise ValueError(f"Unknown target: {target}. Use 'html', 'js', or 'wasm'.")
