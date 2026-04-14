# NOUS SESSION — WEBSITE + INTEGRATIONS HANDOFF
## 14 April 2026 | Hlia + Claude

---

## 1. WHAT WAS BUILT

### 1.1 Website: nous-lang.org

Complete professional website deployed on production server.

**Pages:**

| Page | URL | Size | Content |
|------|-----|------|---------|
| Homepage | `https://nous-lang.org` | 63KB | Hero, stats, language, compiler, verification, live proof terminal, ecosystem, story, install, footer |
| Documentation | `https://nous-lang.org/docs` | 47KB | 29 sections, sidebar navigation, scroll spy, search, full language reference |
| Examples | `https://nous-lang.org/examples` | 26KB | 5 programs: GateAlpha, Compiler, Research, Customer Service, Infra Monitor |
| Blog | `https://nous-lang.org/blog` | 25KB | 3 posts: v3.0.0 release, self-hosting deep dive, verification deep dive |
| IDE | `https://nous-lang.org/ide` | — | Alias to existing ide.html |
| Playground | `https://nous-lang.org/playground` | — | Redirects to IDE |
| Privacy Policy | `https://nous-lang.org` (footer) | — | SPA route, full GDPR-compliant policy |
| Terms of Service | `https://nous-lang.org` (footer) | — | SPA route, Greek law jurisdiction |
| Cookie Policy | `https://nous-lang.org` (footer) | — | SPA route, strictly necessary only |

**Infrastructure:**

| Component | Status | Details |
|-----------|--------|---------|
| SSL | Full (strict) | Cloudflare Origin Certificate, valid until 2041 |
| HSTS | Enabled | max-age=31536000, includeSubDomains |
| HTTP → HTTPS | Redirect 301 | nginx config |
| www → non-www | Redirect 301 | nginx config |
| Email | Active | support@nous-lang.org via Cloudflare Email Routing |
| SPF | Configured | Cloudflare MX records |
| DKIM | Configured | Cloudflare auto-generated |
| DMARC | Configured | v=DMARC1; p=quarantine |
| Analytics | Enabled | Cloudflare Web Analytics (RUM), zero cookies |
| Security headers | All set | X-Frame-Options, X-Content-Type, HSTS, Referrer-Policy |
| Gzip | Enabled | text/plain, text/css, text/javascript, application/json |
| Developer access | Password-protected | Footer link, base64 password check |

**Server Files:**

```
/var/www/nous-lang.org/
├── index.html           (63KB — homepage + live verification terminal)
├── favicon.svg          (362B — Ν logo)
├── og-image.png         (28KB — social sharing image)
├── docs/index.html      (47KB — documentation)
├── examples/index.html  (26KB — examples gallery)
└── blog/index.html      (25KB — blog with 3 posts)

/etc/nginx/sites-available/nous-lang.org  — nginx config with SSL
/etc/ssl/nous-lang.org/origin.pem         — Cloudflare origin cert
/etc/ssl/nous-lang.org/origin-key.pem     — Origin private key
```

**Design:**

- Dark theme (#05070e base)
- Playfair Display headings (classical Greek aesthetic)
- JetBrains Mono code, DM Sans body
- Gold (#c9a554) accent, blue/green/purple for categories
- Canvas particle network animation (hero)
- Auto-typing verification terminal with scroll trigger
- Animated stat counters with IntersectionObserver
- Fade-in scroll animations throughout
- Mobile responsive
- Zero dependencies, zero cookies, zero JavaScript frameworks
- Total site weight: ~161KB

---

### 1.2 MCP Bridge

Connects NOUS souls to any MCP (Model Context Protocol) server.

**Files:**

| File | Location | Purpose |
|------|----------|---------|
| `mcp_bridge.py` | `/opt/aetherlang_agents/nous/` | Core MCP client — JSON-RPC 2.0 over SSE, connection pooling |
| `mcp_discover.py` | `/opt/aetherlang_agents/tools/` | Sense tool — list available tools from MCP server |
| `mcp_call.py` | `/opt/aetherlang_agents/tools/` | Sense tool — call any tool on any MCP server |
| `mcp_example.nous` | `/opt/aetherlang_agents/nous/` | 3-soul demo: Finder → Summarizer → Publisher |

**Architecture:**

```
MCP Server (SSE)
    ↑ JSON-RPC 2.0
MCPClient (mcp_bridge.py)
    ↑ MCPRegistry (connection pool)
mcp_call / mcp_discover (sense tools)
    ↑ ToolRegistry auto-discovery
NOUS Soul instinct block
```

**Usage in .nous:**

```nous
soul Agent {
    senses: [mcp_discover, mcp_call]
    instinct {
        let tools = sense mcp_discover(server: "https://mcp.slack.com/sse")
        let result = sense mcp_call(
            server: "https://mcp.slack.com/sse",
            tool: "send_message",
            channel: "#general",
            text: "Hello from NOUS"
        )
    }
}
```

**Verification:** mcp_example.nous — VERIFIED: 9 proven, 0 errors

---

### 1.3 Extended LLM Tiers

Added 4 new LLM providers to the tier system.

**Before (5 tiers):**

```
Tier0A: Anthropic (Claude)
Tier0B: OpenAI (GPT-4o)
Tier1:  OpenRouter (DeepSeek)
Tier2:  Free (Gemini Flash)
Tier3:  Local (Ollama)
```

**After (9 tiers):**

```
Tier0A:    Anthropic (Claude)         $0.00025-0.00125/1k
Tier0B:    OpenAI (GPT-4o)            $0.0005-0.0025/1k
Tier1:     OpenRouter (DeepSeek)      $0.003-0.015/1k
Tier2:     Free (Gemini Flash)        $0.005-0.025/1k
Tier3:     Local (Ollama)             $0.015-0.075/1k
Groq:      Ultra-fast inference       $0.0003-0.001/1k      ← NEW
Together:  Together AI                $0.0005-0.002/1k      ← NEW
Fireworks: Fireworks AI               $0.0002-0.0008/1k     ← NEW
Cerebras:  Fastest inference          $0.0001-0.0004/1k     ← NEW
```

**Files modified:**

| File | Change |
|------|--------|
| `nous.lark` line 333 | TIER regex: added Groq, Together, Fireworks, Cerebras |
| `ast_nodes.py` line 14 | Tier enum: added 4 new values |
| `runtime.py` line 20 | TIER_COSTS: added 4 new pricing entries |
| `bridge.py` line 24 | TIER_MAP: added 4 new provider configs with models and base URLs |

**Usage:**

```nous
soul Fast { mind: llama-70b @ Groq }
soul Cheap { mind: llama-8b @ Cerebras }
```

**Verification:** tier_test.nous — VERIFIED: 8 proven, 0 errors

---

### 1.4 Behavioral Diff

Semantic impact analysis when you change a .nous file. World-first — no other framework has this.

**File:** `/opt/aetherlang_agents/nous/behavioral_diff.py`

**Command:** `nous diff original.nous modified.nous`

**What it analyzes:**

| Category | What It Detects |
|----------|-----------------|
| Topology | Souls added/removed/modified, route changes |
| Protocol | Message types added/removed |
| Cost | Per-soul cost delta, total cost change (%), daily/monthly projection |
| Deadlock | New circular dependencies introduced |
| Liveness | Lost entrypoints, unreachable souls |
| Reachability | Souls that become unreachable from entrypoints |
| Wake Strategy | HEARTBEAT ↔ LISTENER changes |
| Capability | Senses added/removed per soul |
| Memory | Memory fields added/removed |
| Evolution | DNA genes added/removed |
| Law | Cost ceiling changes |
| Performance | Heartbeat interval changes |

**Severity levels:** CRITICAL (breaking), WARNING (risky), INFO (safe)

**Example output:**

```
═══ NOUS Behavioral Diff ═══
gate_alpha.nous → gate_alpha_v2.nous

── Topology ──
- Soul removed: Monitor
~ Souls modified: Scout

── Cost Impact ──
↓ Scout: $0.004500 → $0.000350 (-92.2%)
Total: $0.016875 → $0.005225 (-69.0%)
Daily:   $4.86 → $1.50
Monthly: $145.80 → $45.14

── Cost ──
⚠ [WARNING] Soul Scout: tier changed Tier1 → Groq
✗ [CRITICAL] Total cost change: -69.0%

══════════════════════════════════════
BREAKING: 1 critical, 4 warnings, 4 info
```

---

### 1.5 Cost Oracle

Predictive cost analysis with automatic optimization suggestions.

**File:** `/opt/aetherlang_agents/nous/cost_oracle.py`

**Command:** `nous cost file.nous`

**What it projects:**

- Per-cycle, daily, and monthly cost
- Per-soul breakdown with visual bar chart
- Cost ceiling headroom percentage
- Cycles until ceiling breach
- Automatic optimization suggestions with savings per day/month
- Risk rating per suggestion (low/medium/high)

**Example output:**

```
═══ NOUS Cost Oracle — GateAlpha ═══

── Projection ──
Per cycle:  $0.016875
Daily:      $4.86
Monthly:    $145.80
Ceiling:    $0.1/cycle (83% headroom)

── Per-Soul Breakdown ──
Monitor          $   2.16/day  ████████░░░░░░░░░░░░   44%
Scout            $   1.30/day  █████░░░░░░░░░░░░░░░   27%
Hunter           $   1.30/day  █████░░░░░░░░░░░░░░░   27%
Quant            $   0.11/day  ░░░░░░░░░░░░░░░░░░░░    2%

── Optimization Suggestions ──
1. Monitor: Switch tier Tier2 → Cerebras
   Save: $2.12/day ($63.68/month) · Risk: low

Total saveable: $4.71/day ($141.31/month)
Optimized cost: $4.86 → $0.15/day

══════════════════════════════════════
OPTIMIZE: $141.31/month saveable across 4 suggestions
```

---

## 2. CURRENT STATE

### 2.1 CLI Commands: 35

```
compile  run  validate  typecheck  verify  test  watch  debug
shell  profile  docker  plugins  pkg  ast  evolve  nsp
info  bridge  version  crossworld  bench  docs  fmt  noesis
build  init  migrate  viz  lsp  wasm  self-compile  create
diff  cost  verify
```

New commands this session: `diff`, `cost`

### 2.2 File Inventory Update

**New files created this session:**

| File | Size | Purpose |
|------|------|---------|
| `mcp_bridge.py` | ~8KB | MCP client (JSON-RPC/SSE) |
| `behavioral_diff.py` | ~16KB | Semantic diff engine |
| `cost_oracle.py` | ~10KB | Predictive cost analysis |
| `mcp_example.nous` | ~2KB | MCP demo program |

**New tool files:**

| File | Location | Purpose |
|------|----------|---------|
| `mcp_discover.py` | `/opt/aetherlang_agents/tools/` | MCP tool discovery sense |
| `mcp_call.py` | `/opt/aetherlang_agents/tools/` | MCP tool invocation sense |

### 2.3 Test Status

All existing 259 tests remain passing. New features verified:

| Program | Verification Result |
|---------|-------------------|
| mcp_example.nous | 9 proven, 0 errors |
| tier_test.nous (Groq+Cerebras) | 8 proven, 0 errors |
| gate_alpha.nous (diff test) | Behavioral diff executed successfully |
| gate_alpha.nous (cost test) | Cost oracle executed successfully |

---

## 3. WHAT'S NEXT

### 3.1 Ready to Build (High Impact)

| Feature | Description | Effort |
|---------|------------|--------|
| **Soul Mitosis** | Self-replicating agents with verification gate | Hard |
| **Agent Dreaming** | Speculative pre-computation during idle time | Medium |
| **Agent Immune System** | Adaptive error recovery, propagating antibodies | Hard |

### 3.2 Infrastructure

| Task | Description |
|------|------------|
| Telegram Bot popup | Integrate on website |
| Blog RSS feed | Auto-generated from blog posts |
| GitHub Actions CI | Run 259 tests on push |
| PyPI package | `pip install nous-lang` |

### 3.3 Language Evolution

| Feature | Description |
|---------|------------|
| Import system v2 | Cross-file soul references |
| Hot reload | Change .nous → auto-recompile → swap souls without restart |
| Telemetry sense | Built-in Langfuse/OpenTelemetry integration |
| Streaming output | Soul output streams to channels in real-time |

---

## 4. ARCHITECTURE OVERVIEW

```
nous-lang.org (Cloudflare → nginx → static HTML)
    │
    ├── / (homepage)
    ├── /docs (documentation)
    ├── /examples (gallery)
    ├── /blog (3 posts)
    ├── /ide (NOUS IDE)
    └── /playground (→ IDE)

NOUS Compiler Pipeline:
    .nous → Parser → AST → Validator → TypeChecker → Verifier → CodeGen → Output
                                                        │
                                                   Behavioral Diff (nous diff)
                                                   Cost Oracle (nous cost)

NOUS Runtime:
    Souls → Channels → SenseExecutor → ToolRegistry
                                           │
                                      MCP Bridge → Any MCP Server
                                      Local Tools → /opt/aetherlang_agents/tools/

LLM Tiers (9):
    Tier0A (Anthropic) → Tier0B (OpenAI) → Tier1 (OpenRouter)
    → Tier2 (Free) → Tier3 (Ollama) → Groq → Together
    → Fireworks → Cerebras
```

---

## 5. SERVER DETAILS

| Server | IP | Path |
|--------|-----|------|
| neurodoc (Server A) | 188.245.245.132 | `/opt/aetherlang_agents/nous/` |
| neuroaether (Server B) | — | `/opt/neuroaether/nous/` (nightly rsync) |

**Domain:** nous-lang.org (Cloudflare, proxied)
**Email:** support@nous-lang.org (Cloudflare Email Routing)
**GitHub:** github.com/contrario/nous

---

## 6. NEXT SESSION PROMPT

```
You are a Staff-Level Principal Language Designer. Continue building NOUS.

CONTEXT:
- NOUS v3.1.0 — 35 CLI commands, 259 tests, 9 LLM tiers
- MCP Bridge deployed (mcp_call, mcp_discover senses)
- Behavioral Diff (nous diff) — semantic impact analysis
- Cost Oracle (nous cost) — predictive cost with optimization suggestions
- Website live at nous-lang.org (6 pages, SSL, DMARC)

READ: /opt/aetherlang_agents/nous/NOUS_WEBSITE_SESSION_HANDOFF.md

PRIORITY OPTIONS:
1. Soul Mitosis — self-replicating verified agents
2. Agent Dreaming — speculative pre-computation during idle
3. Agent Immune System — adaptive error recovery

Pick one and build it.
```

---

*NOUS v3.1.0 — 14 April 2026*
*Created by Hlias Staurou (Hlia) + Claude*
