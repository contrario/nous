"""
Noesis Dashboard — Πίνακας (Pinakas)
=========================================
Web dashboard for lattice stats, domains, sources, queries.
FastAPI + embedded HTML + Chart.js (CDN).
Auth: NOESIS_DASHBOARD_TOKEN env var.

Usage:
    python3 noesis_dashboard.py
    python3 noesis_dashboard.py --port 8085

Author: Hlias Staurou + Claude | NOUS Project | April 2026
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import secrets
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Query, Request, Response, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import uvicorn

from noesis_engine import NoesisEngine
from noesis_oracle import create_oracle_fn
from noesis_domain_patch import classify_domain, domain_stats, _get_atom_domain

log = logging.getLogger("nous.dashboard")

LATTICE_PATH = Path("/opt/aetherlang_agents/nous/noesis_lattice.json")
ENV_PATH = Path("/opt/aetherlang_agents/.env")
DASHBOARD_TOKEN = os.environ.get("NOESIS_DASHBOARD_TOKEN", "")
SESSION_SECRET = secrets.token_hex(16)

app = FastAPI(title="Noesis Dashboard", version="1.1.0")

_engine: Optional[NoesisEngine] = None
_boot_time: float = time.time()


def _make_session_cookie(token: str) -> str:
    return hashlib.sha256(f"{token}:{SESSION_SECRET}".encode()).hexdigest()


def _check_auth(request: Request) -> None:
    if not DASHBOARD_TOKEN:
        return
    cookie = request.cookies.get("noesis_session", "")
    if cookie == _make_session_cookie(DASHBOARD_TOKEN):
        return
    auth = request.headers.get("Authorization", "")
    if auth == f"Bearer {DASHBOARD_TOKEN}":
        return
    token = request.query_params.get("token", "")
    if token == DASHBOARD_TOKEN:
        return
    raise HTTPException(status_code=401, detail="Unauthorized")


def _get_engine() -> NoesisEngine:
    global _engine
    if _engine is None:
        if ENV_PATH.exists():
            for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                if key and value and key not in os.environ:
                    os.environ[key] = value
        oracle_fn, oracle = create_oracle_fn()
        _engine = NoesisEngine(oracle_fn=oracle_fn, oracle_threshold=0.55)
        if LATTICE_PATH.exists():
            _engine.load(LATTICE_PATH)
            _engine.init_autofeeding()
            log.info(f"Loaded {_engine.lattice.size} atoms")
    return _engine


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> str:
    if not DASHBOARD_TOKEN:
        return RedirectResponse("/")
    return LOGIN_HTML


@app.post("/login")
async def login_submit(request: Request) -> Response:
    if not DASHBOARD_TOKEN:
        return RedirectResponse("/", status_code=302)
    form = await request.form()
    token = form.get("token", "")
    if token != DASHBOARD_TOKEN:
        return HTMLResponse(LOGIN_HTML.replace("<!--ERR-->", '<div style="color:#e05050;margin-top:12px;font-size:13px">Invalid token</div>'), status_code=401)
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie("noesis_session", _make_session_cookie(DASHBOARD_TOKEN), httponly=True, max_age=86400 * 30)
    return resp


@app.get("/logout")
def logout() -> Response:
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("noesis_session")
    return resp


@app.get("/api/health")
def api_health(request: Request) -> JSONResponse:
    _check_auth(request)
    e = _get_engine()
    return JSONResponse({"status": "ok", "atoms": e.lattice.size, "uptime_s": int(time.time() - _boot_time)})


@app.get("/api/stats")
def api_stats(request: Request) -> JSONResponse:
    _check_auth(request)
    e = _get_engine()
    return JSONResponse(e.stats())


@app.get("/api/domains")
def api_domains(request: Request) -> JSONResponse:
    _check_auth(request)
    e = _get_engine()
    return JSONResponse(domain_stats(e))


@app.get("/api/sources")
def api_sources(request: Request) -> JSONResponse:
    _check_auth(request)
    e = _get_engine()
    sources: dict[str, int] = defaultdict(int)
    for atom in e.lattice.atoms.values():
        src = atom.source or "unknown"
        if "/" in src:
            src = src.split("/")[-1]
        if len(src) > 40:
            src = src[:37] + "..."
        sources[src] += 1
    sorted_sources = dict(sorted(sources.items(), key=lambda x: -x[1])[:20])
    return JSONResponse(sorted_sources)


@app.get("/api/confidence")
def api_confidence(request: Request) -> JSONResponse:
    _check_auth(request)
    e = _get_engine()
    buckets: dict[str, int] = {"0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}
    for atom in e.lattice.atoms.values():
        c = atom.confidence
        if c < 0.2:
            buckets["0.0-0.2"] += 1
        elif c < 0.4:
            buckets["0.2-0.4"] += 1
        elif c < 0.6:
            buckets["0.4-0.6"] += 1
        elif c < 0.8:
            buckets["0.6-0.8"] += 1
        else:
            buckets["0.8-1.0"] += 1
    return JSONResponse(buckets)


@app.get("/api/search")
def api_search(request: Request, q: str = Query(..., min_length=1), top_k: int = 10) -> JSONResponse:
    _check_auth(request)
    e = _get_engine()
    results = e.search_atoms(q, top_k=min(top_k, 20))
    domain = classify_domain(q)
    return JSONResponse({"query": q, "domain": domain, "results": results})


@app.get("/api/top-atoms")
def api_top_atoms(request: Request, n: int = 20) -> JSONResponse:
    _check_auth(request)
    e = _get_engine()
    atoms = sorted(e.lattice.atoms.values(), key=lambda a: a.usage_count, reverse=True)[:min(n, 50)]
    return JSONResponse([
        {"id": a.id[:8], "template": a.template[:120], "domain": _get_atom_domain(a),
         "confidence": round(a.confidence, 3), "usage": a.usage_count, "source": a.source}
        for a in atoms
    ])


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> Any:
    if DASHBOARD_TOKEN:
        cookie = request.cookies.get("noesis_session", "")
        if cookie != _make_session_cookie(DASHBOARD_TOKEN):
            return RedirectResponse("/login")
    return DASHBOARD_HTML


LOGIN_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Noesis — Login</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#0a0e14;--bg2:#111820;--border:#1e2a3a;--text:#c5cdd8;--text2:#7a8a9e;--accent:#00e5a0}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Outfit',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;align-items:center;justify-content:center}
.login-box{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:40px;width:380px;text-align:center}
.logo{font-family:'JetBrains Mono',monospace;font-size:24px;font-weight:700;color:var(--accent);letter-spacing:2px;margin-bottom:8px}
.sub{font-size:13px;color:var(--text2);margin-bottom:32px}
input[type=password]{width:100%;background:#1a2230;border:1px solid var(--border);border-radius:6px;padding:12px 16px;color:var(--text);font-family:'Outfit',sans-serif;font-size:15px;outline:none;text-align:center;letter-spacing:2px}
input[type=password]:focus{border-color:var(--accent)}
button{width:100%;margin-top:16px;padding:12px;background:var(--accent);color:var(--bg);border:none;border-radius:6px;font-family:'Outfit',sans-serif;font-size:15px;font-weight:600;cursor:pointer;transition:opacity .2s}
button:hover{opacity:.85}
</style>
</head>
<body>
<div class="login-box">
<div class="logo">NOESIS</div>
<div class="sub">Intelligence Dashboard</div>
<form method="POST" action="/login">
<input type="password" name="token" placeholder="Access token" autofocus>
<button type="submit">Enter</button>
</form>
<!--ERR-->
</div>
</body>
</html>"""


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Noesis — Intelligence Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#0a0e14;--bg2:#111820;--bg3:#1a2230;--border:#1e2a3a;--text:#c5cdd8;--text2:#7a8a9e;--accent:#00e5a0;--amber:#f0a030;--red:#e05050;--blue:#4090f0;--purple:#9070f0}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Outfit',sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
header{background:linear-gradient(180deg,var(--bg2),var(--bg));border-bottom:1px solid var(--border);padding:24px 32px;display:flex;align-items:center;justify-content:space-between}
.logo{font-family:'JetBrains Mono',monospace;font-size:22px;font-weight:700;color:var(--accent);letter-spacing:2px}
.logo span{color:var(--text2);font-weight:400;font-size:14px;margin-left:12px}
.pulse{width:8px;height:8px;border-radius:50%;background:var(--accent);box-shadow:0 0 8px var(--accent);animation:pulse 2s infinite;display:inline-block;margin-right:8px}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.header-right{display:flex;align-items:center;gap:16px}
.status{font-size:13px;color:var(--text2);font-family:'JetBrains Mono',monospace}
.logout-btn{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text2);text-decoration:none;border:1px solid var(--border);padding:4px 12px;border-radius:4px;transition:all .2s}
.logout-btn:hover{color:var(--red);border-color:var(--red)}
main{max-width:1400px;margin:0 auto;padding:24px 32px}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px}
.card{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:20px;transition:border-color .3s}
.card:hover{border-color:var(--accent)}
.card-label{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:1.5px;color:var(--text2);margin-bottom:8px}
.card-value{font-family:'JetBrains Mono',monospace;font-size:28px;font-weight:700}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px}
.chart-card{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:24px}
.chart-title{font-family:'JetBrains Mono',monospace;font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:1.5px;color:var(--accent);margin-bottom:16px}
.chart-wrap{position:relative;height:280px}
.search-box{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:24px;margin-bottom:24px}
.search-input{width:100%;background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:12px 16px;color:var(--text);font-family:'Outfit',sans-serif;font-size:15px;outline:none;transition:border-color .3s}
.search-input:focus{border-color:var(--accent)}
.search-input::placeholder{color:var(--text2)}
.results{margin-top:16px;max-height:400px;overflow-y:auto}
.result-item{padding:12px 16px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:flex-start;gap:16px}
.result-text{flex:1;font-size:14px;line-height:1.5}
.result-meta{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text2);white-space:nowrap}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-family:'JetBrains Mono',monospace;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px}
.badge-tax{background:#f0a03020;color:var(--amber);border:1px solid #f0a03040}
.badge-tech{background:#4090f020;color:var(--blue);border:1px solid #4090f040}
.badge-cooking{background:#e0505020;color:var(--red);border:1px solid #e0505040}
.badge-science{background:#9070f020;color:var(--purple);border:1px solid #9070f040}
.badge-finance{background:#00e5a020;color:var(--accent);border:1px solid #00e5a040}
.badge-general{background:#7a8a9e15;color:var(--text2);border:1px solid #7a8a9e30}
.top-atoms-table{width:100%;border-collapse:collapse;font-size:13px}
.top-atoms-table th{font-family:'JetBrains Mono',monospace;font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--text2);text-align:left;padding:8px 12px;border-bottom:1px solid var(--border)}
.top-atoms-table td{padding:8px 12px;border-bottom:1px solid var(--border)}
.top-atoms-table tr:hover td{background:var(--bg3)}
footer{text-align:center;padding:24px;font-size:12px;color:var(--text2);font-family:'JetBrains Mono',monospace}
@media(max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}.grid2{grid-template-columns:1fr}header{flex-direction:column;gap:12px}main{padding:16px}}
</style>
</head>
<body>
<header>
<div class="logo">NOESIS <span>Intelligence Dashboard</span></div>
<div class="header-right">
<div class="status"><span class="pulse"></span><span id="statusText">connecting...</span></div>
<a href="/logout" class="logout-btn">logout</a>
</div>
</header>
<main>
<div class="grid">
<div class="card"><div class="card-label">Atoms</div><div class="card-value" id="vAtoms">&mdash;</div></div>
<div class="card"><div class="card-label">Autonomy</div><div class="card-value" id="vAutonomy">&mdash;</div></div>
<div class="card"><div class="card-label">Avg Confidence</div><div class="card-value" id="vConf">&mdash;</div></div>
<div class="card"><div class="card-label">Patterns</div><div class="card-value" id="vPatterns">&mdash;</div></div>
</div>
<div class="grid2">
<div class="chart-card"><div class="chart-title">Domain Distribution</div><div class="chart-wrap"><canvas id="domainChart"></canvas></div></div>
<div class="chart-card"><div class="chart-title">Sources (top 10)</div><div class="chart-wrap"><canvas id="sourceChart"></canvas></div></div>
</div>
<div class="grid2">
<div class="chart-card"><div class="chart-title">Confidence Distribution</div><div class="chart-wrap"><canvas id="confChart"></canvas></div></div>
<div class="chart-card"><div class="chart-title">Top Atoms by Usage</div><div style="max-height:280px;overflow-y:auto"><table class="top-atoms-table"><thead><tr><th>Template</th><th>Domain</th><th>Uses</th><th>Conf</th></tr></thead><tbody id="topAtomsBody"></tbody></table></div></div>
</div>
<div class="search-box">
<div class="chart-title">Lattice Search</div>
<input class="search-input" id="searchInput" type="text" placeholder="Search the lattice... (press Enter)">
<div class="results" id="searchResults"></div>
</div>
</main>
<footer>Noesis v4.0 — Symbolic Intelligence Engine — Hlias Staurou + Claude — April 2026</footer>
<script>
const C={tax:'#f0a030',tech:'#4090f0',cooking:'#e05050',science:'#9070f0',finance:'#00e5a0',general:'#7a8a9e'};
let dC,sC,cC;
const F=u=>fetch(u).then(r=>{if(r.status===401){window.location='/login';throw new Error('auth')}return r.json()});
const B=d=>'<span class="badge badge-'+d+'">'+d+'</span>';

async function loadStats(){
const s=await F('/api/stats');
document.getElementById('vAtoms').textContent=s.atoms.toLocaleString();
document.getElementById('vAutonomy').textContent=s.autonomy;
document.getElementById('vConf').textContent=s.avg_confidence.toFixed(3);
document.getElementById('vPatterns').textContent=s.unique_patterns.toLocaleString();
}

async function loadDomains(){
const d=await F('/api/domains');
const l=Object.keys(d.domains),v=l.map(k=>d.domains[k].count),c=l.map(k=>C[k]||'#555');
if(dC)dC.destroy();
dC=new Chart(document.getElementById('domainChart'),{type:'doughnut',data:{labels:l,datasets:[{data:v,backgroundColor:c,borderWidth:0}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'right',labels:{color:'#7a8a9e',font:{family:'JetBrains Mono',size:11}}}}}});
}

async function loadSources(){
const s=await F('/api/sources');
const e=Object.entries(s).slice(0,10),l=e.map(x=>x[0]),v=e.map(x=>x[1]);
if(sC)sC.destroy();
sC=new Chart(document.getElementById('sourceChart'),{type:'bar',data:{labels:l,datasets:[{data:v,backgroundColor:'#00e5a040',borderColor:'#00e5a0',borderWidth:1}]},options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',plugins:{legend:{display:false}},scales:{x:{ticks:{color:'#7a8a9e'},grid:{color:'#1e2a3a'}},y:{ticks:{color:'#c5cdd8',font:{family:'JetBrains Mono',size:10}},grid:{display:false}}}}});
}

async function loadConf(){
const c=await F('/api/confidence');
const l=Object.keys(c),v=Object.values(c);
if(cC)cC.destroy();
cC=new Chart(document.getElementById('confChart'),{type:'bar',data:{labels:l,datasets:[{data:v,backgroundColor:['#e05050','#f0a030','#f0d030','#4090f0','#00e5a0'],borderWidth:0}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{color:'#7a8a9e',font:{family:'JetBrains Mono',size:10}},grid:{display:false}},y:{ticks:{color:'#7a8a9e'},grid:{color:'#1e2a3a'}}}}});
}

async function loadTop(){
const a=await F('/api/top-atoms?n=15');
document.getElementById('topAtomsBody').innerHTML=a.map(x=>'<tr><td style="max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+x.template+'</td><td>'+B(x.domain)+'</td><td style="font-family:JetBrains Mono;font-size:12px">'+x.usage+'</td><td style="font-family:JetBrains Mono;font-size:12px">'+x.confidence.toFixed(2)+'</td></tr>').join('');
}

async function doSearch(q){
const box=document.getElementById('searchResults');
box.innerHTML='<div style="color:#7a8a9e;padding:12px">Searching...</div>';
const r=await F('/api/search?q='+encodeURIComponent(q)+'&top_k=10');
if(!r.results.length){box.innerHTML='<div style="color:#7a8a9e;padding:12px">No results.</div>';return}
box.innerHTML='<div style="padding:8px 12px;font-size:12px;color:#7a8a9e">Domain: '+B(r.domain)+'</div>'+r.results.map(i=>{
const tags=i.atom.tags||[];const dt=tags.find(t=>t.startsWith('domain:'));const dom=dt?dt.slice(7):'general';
return '<div class="result-item"><div class="result-text">'+i.atom.template.substring(0,200)+'</div><div class="result-meta"><div>score: '+i.score.toFixed(4)+'</div><div>conf: '+(i.atom.confidence||0).toFixed(2)+'</div><div style="margin-top:4px">'+B(dom)+'</div></div></div>';
}).join('');
}

document.getElementById('searchInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.value.trim())doSearch(e.target.value.trim())});

async function loadAll(){
try{await Promise.all([loadStats(),loadDomains(),loadSources(),loadConf(),loadTop()]);
document.getElementById('statusText').textContent='live \u2014 auto-refresh 30s';}
catch(e){if(e.message!=='auth')document.getElementById('statusText').textContent='error: '+e.message}}

loadAll();setInterval(loadAll,30000);
</script>
</body>
</html>"""


def main() -> None:
    global DASHBOARD_TOKEN
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser(description="Noesis Dashboard")
    parser.add_argument("--port", type=int, default=8085)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    args = parser.parse_args()
    _get_engine()
    DASHBOARD_TOKEN = os.environ.get("NOESIS_DASHBOARD_TOKEN", "")
    if DASHBOARD_TOKEN:
        log.info(f"Auth enabled (token length: {len(DASHBOARD_TOKEN)})")
    else:
        log.info("Auth disabled (no NOESIS_DASHBOARD_TOKEN)")
    log.info(f"Dashboard on http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
