# NOUS SESSION — IDE + ARCHITECTURE DIFF + DOCUMENTATION HANDOFF
## 14 April 2026 | Hlia + Claude

---

## 1. WHAT WAS BUILT

### 1.1 NOUS IDE (`nous-lang.org/ide`)

A complete, self-contained browser IDE for the NOUS language. No build system, no React, no dependencies — a single HTML file served by nginx.

**Why:** NOUS had no interactive development environment accessible from the web. Developers and visitors needed a way to write, compile, and explore NOUS programs directly in the browser without installing anything.

**How:** Created a 31KB self-contained HTML file with embedded CSS and JavaScript. Deployed to `/var/www/nous-lang.org/ide.html` and configured nginx to serve it at `/ide` and `/playground`.

**4 Tabs:**

| Tab | Function |
|-----|----------|
| **Editor** | Code editor with syntax-aware textarea, Compile/Verify/Run buttons, output panel showing compilation results |
| **Verify** | Placeholder for formal verification output (connects to `nous verify`) |
| **Graph** | Placeholder for nervous system visualization (connects to `nous viz`) |
| **Architecture Diff** | Full behavioral diff visualizer with interactive demo data |

**Architecture Diff Tab Features:**
- Input bar showing original vs modified `.nous` files
- "Run Diff" button that loads demo data (or receives JSON from backend)
- Verdict banner: BREAKING CHANGES DETECTED / SAFE TO DEPLOY with severity pill counts
- Cost Impact card: monthly cost with strikethrough old value, green new value, percentage badge, per-cycle/daily mini-stats, per-soul bar chart breakdown
- Mind/Tier Changes card: visual tier pills with color coding per provider (Groq=orange, Cerebras=cyan, Tier1=green, etc.), REMOVED badge for deleted souls
- Topology card: diff lines showing added/removed/modified souls, route changes
- Capabilities & Memory card: senses and memory fields added/removed with color-coded diff lines
- All Findings log: filterable by ALL/CRITICAL/WARNING/INFO, each finding shows severity badge, error code, category, and message

**Design:**
- Matches nous-lang.org aesthetic: dark background (#05070e), gold accents (#c9a554)
- Playfair Display headings, JetBrains Mono for code, DM Sans for body
- Zero cookies, zero frameworks, zero external dependencies
- Mobile responsive

**Files:**

| File | Location | Size |
|------|----------|------|
| `ide.html` | `/var/www/nous-lang.org/ide.html` | 31KB |

**nginx Configuration:**

```nginx
location = /ide {
    rewrite ^ /ide.html last;
}
location = /ide.html {
    alias /var/www/nous-lang.org/ide.html;
}
location = /playground {
    rewrite ^ /ide.html last;
}
```

The original config had `alias /var/www/html/ide.html` (wrong path). Fixed to `/var/www/nous-lang.org/ide.html`.

---

### 1.2 Homepage Architecture Diff Section (`nous-lang.org/#ArchDiff`)

A showcase section on the homepage demonstrating the behavioral diff engine.

**Why:** The Architecture Diff is a world-first feature — no other language or framework has semantic impact analysis for agent systems. It deserves prominent placement on the homepage to show visitors what makes NOUS unique.

**How:** Created an HTML section injected into `index.html` after the "What's New" section (line 576) using `sed -i '576r /tmp/diff_section.html'`. Added a "Diff" nav link to the top navigation bar.

**Contains:**
- "WORLD FIRST" red tag badge
- "Architecture Diff" title with description
- Command bar showing `nous diff gate_alpha.nous vs gate_alpha_v2.nous`
- Full verdict banner with 1 Critical, 4 Warning, 4 Info pills
- Cost Impact card: $145.80 → $45.14/month, ↓69.0%, per-soul bars
- Mind/Tier Changes card: Scout Tier1→Groq, Monitor Tier2→REMOVED
- Topology section: Monitor removed, Scout modified
- All Findings log: 5 findings shown (CRITICAL, WARNING, INFO)
- "Open in NOUS IDE →" button linking to `/ide`

**Navigation:** Added `<a href="#ArchDiff" class="nav-link">Diff</a>` to the top nav bar in `index.html`.

---

### 1.3 Documentation: Architecture Diff (`nous-lang.org/docs#arch-diff`)

Full documentation for the `nous diff` command.

**Why:** Every feature needs documentation. Users need to understand what the diff engine analyzes, what severity levels mean, how to read the output, and how to use the `--json` flag for CI/CD integration.

**How:** Created HTML content in `/tmp/diff_docs.html` using a Python script (heredoc was unreliable for large pastes). Injected after the Debugger & REPL section (line 709) using `sed -i '709r /tmp/diff_docs.html'`. Added sidebar link after "Debugger & REPL".

**Sections:**
- Usage: `nous diff original.nous modified.nous [--json]`
- What It Analyzes: 12 categories table (Topology, Routes, Protocol, Cost, Deadlock, Liveness, Reachability, Wake Strategy, Capability, Memory, Evolution)
- Severity Levels: CRITICAL, WARNING, INFO with descriptions
- Example Output: full terminal output example
- JSON Output: description of `--json` flag and payload structure
- IDE Integration: link to the IDE's Architecture Diff tab
- File: `behavioral_diff.py` location

---

### 1.4 Documentation: Cost Oracle (`nous-lang.org/docs#cost-oracle`)

Full documentation for the `nous cost` command.

**Why:** The Cost Oracle is a companion to the diff engine. Users need to understand cost projections, per-soul breakdowns, and how optimization suggestions work.

**How:** Included in the same injection as Architecture Diff docs.

**Sections:**
- Usage: `nous cost file.nous`
- What It Projects: per-cycle, daily, monthly cost, ceiling headroom, per-soul breakdown
- Optimization Suggestions: how the oracle identifies savings opportunities
- Example Output: full terminal output with bar chart and suggestions
- File: `cost_oracle.py` location

---

### 1.5 React Component (Downloadable)

A standalone React component `<BehavioralDiffVisualizer />` for future use.

**Why:** The IDE currently uses vanilla HTML/JS. If the IDE is ever rebuilt with React, this component is ready to drop in. It was also used as the design reference for the vanilla implementation.

**How:** Created as a `.jsx` file with all subcomponents: `VerdictBanner`, `CostImpactCard`, `TierChangeCard`, `TopologyCard`, `CapabilitiesCard`, `FindingsLog`, `AnimatedNumber`, `SeverityBadge`.

**File:** `/var/www/nous-lang.org/BehavioralDiffVisualizer.jsx` (23KB) — available on server but not served by nginx.

---

## 2. ARCHITECTURE DECISIONS

### Why vanilla HTML instead of React?

The NOUS website is static HTML served by nginx behind Cloudflare. There is no build system (no webpack, no vite, no node.js) on the production server. Adding React would require:
1. A build pipeline
2. Node.js on the server
3. A deployment process

None of this exists. The entire site is hand-crafted HTML files. The IDE follows the same pattern: one self-contained HTML file, zero dependencies. This keeps the site at ~161KB total, loads instantly, requires no JavaScript framework overhead, and can be edited with `nano` on the server.

### Why inject into index.html with sed?

Hlia works entirely from a terminal (nano + bash). There is no local development environment, no git workflow, no CI/CD pipeline. The fastest path from "idea" to "deployed" is:
1. Create content in a temp file
2. Inject at the right line number with `sed`
3. Verify with `grep`

This is how every section of nous-lang.org was built.

### Why mock data instead of live backend?

The diff engine (`behavioral_diff.py`) runs on the server as a CLI tool. The IDE runs in the browser as static HTML. There is no API server connecting them. The mock data demonstrates the full visualization capability. When a backend API is added later, the IDE's `renderDiff()` function accepts any JSON payload matching the schema — just replace the mock with a `fetch()` call.

---

## 3. FILES MODIFIED

| File | Change |
|------|--------|
| `/var/www/nous-lang.org/ide.html` | **Created** — Full IDE with 4 tabs |
| `/var/www/nous-lang.org/index.html` | **Modified** — Added nav link "Diff", added #ArchDiff section after "What's New" |
| `/var/www/nous-lang.org/docs/index.html` | **Modified** — Added sidebar links (Architecture Diff, Cost Oracle), added 2 doc sections after Debugger |
| `/etc/nginx/sites-available/nous-lang.org` | **Modified** — Fixed ide.html alias path from `/var/www/html/` to `/var/www/nous-lang.org/` |

---

## 4. CURRENT STATE

### 4.1 Website Pages: 7

| Page | URL | Status |
|------|-----|--------|
| Homepage | `nous-lang.org` | Live — now includes Architecture Diff section |
| Documentation | `nous-lang.org/docs` | Live — now includes Arch Diff + Cost Oracle docs |
| Examples | `nous-lang.org/examples` | Live |
| Blog | `nous-lang.org/blog` | Live |
| IDE | `nous-lang.org/ide` | **NEW** — 4-tab IDE |
| Playground | `nous-lang.org/playground` | Redirects to IDE |
| Privacy/Terms/Cookies | Footer links | Live |

### 4.2 Server File Tree

```
/var/www/nous-lang.org/
├── index.html                    (updated — +ArchDiff section, +nav link)
├── ide.html                      (NEW — 31KB, full IDE)
├── BehavioralDiffVisualizer.jsx  (23KB — React component, not served)
├── favicon.svg
├── og-image.png
├── docs/index.html               (updated — +2 doc sections, +2 sidebar links)
├── examples/index.html
└── blog/index.html
```

### 4.3 nginx Routes

```
/ide          → /var/www/nous-lang.org/ide.html
/ide.html     → /var/www/nous-lang.org/ide.html
/playground   → redirect to /ide.html
```

---

## 5. WHAT'S NEXT

### 5.1 IDE Enhancements

| Feature | Description |
|---------|-------------|
| **Backend API** | REST endpoint that runs `nous diff --json` and returns results to the IDE |
| **Live Compilation** | Editor sends code to server, receives compiled output |
| **Verify Tab** | Connect to `nous verify` and render proof results |
| **Graph Tab** | Render nervous system topology using the visualizer |
| **Syntax Highlighting** | Proper tokenizer for NOUS keywords in the editor |
| **Home Button** | Link back to nous-lang.org from IDE header |

### 5.2 Language Features

| Feature | Description |
|---------|-------------|
| Soul Mitosis | Self-replicating verified agents |
| Agent Dreaming | Speculative pre-computation during idle |
| Agent Immune System | Adaptive error recovery |

### 5.3 Infrastructure

| Task | Description |
|------|-------------|
| Blog RSS feed | Auto-generated from blog posts |
| GitHub Actions CI | Run 259 tests on push |
| PyPI package | `pip install nous-lang` |

---

## 6. COMMANDS USED

For reference, the exact sequence of commands executed on the server:

```bash
# Check what exists
ls -la /var/www/nous-lang.org/

# Fix nginx alias path
nano /etc/nginx/sites-available/nous-lang.org
# Changed: alias /var/www/html/ide.html → alias /var/www/nous-lang.org/ide.html
nginx -t && systemctl reload nginx

# Deploy IDE (pasted via heredoc or SCP)
# Result: /var/www/nous-lang.org/ide.html (31KB)

# Add nav link to homepage
sed -i 's|<a href="#Ecosystem" class="nav-link">Ecosystem</a>|<a href="#Ecosystem" class="nav-link">Ecosystem</a>\n      <a href="#ArchDiff" class="nav-link">Diff</a>|' /var/www/nous-lang.org/index.html

# Create and inject homepage diff section
cat > /tmp/diff_section.html << 'DIFFSEC'
# ... section content ...
DIFFSEC
sed -i '576r /tmp/diff_section.html' /var/www/nous-lang.org/index.html

# Create documentation content via Python (heredoc was unreliable)
python3 -c "content = '''...'''; open('/tmp/diff_docs.html','w').write(content)"

# Inject docs after Debugger section
sed -i '709r /tmp/diff_docs.html' /var/www/nous-lang.org/docs/index.html

# Add sidebar links
sed -i '162a\    <a href="#arch-diff" class="sb-link">Architecture Diff</a>\n    <a href="#cost-oracle" class="sb-link">Cost Oracle</a>' /var/www/nous-lang.org/docs/index.html
```

---

## 7. NEXT SESSION PROMPT

```
You are a Staff-Level Principal Language Designer. Continue building NOUS.

CONTEXT:
- NOUS v3.1.0 — 35 CLI commands, 259 tests, 9 LLM tiers
- Website live at nous-lang.org (7 pages, SSL, DMARC)
- IDE live at nous-lang.org/ide (4 tabs: Editor, Verify, Graph, Architecture Diff)
- Architecture Diff showcased on homepage (#ArchDiff)
- Documentation updated with Arch Diff + Cost Oracle sections
- MCP Bridge, Behavioral Diff, Cost Oracle all deployed

READ: /opt/aetherlang_agents/nous/NOUS_IDE_SESSION_HANDOFF.md

PRIORITY OPTIONS:
1. Backend API — connect IDE to actual nous diff/verify/compile commands
2. Soul Mitosis — self-replicating verified agents
3. Agent Dreaming — speculative pre-computation during idle
4. Syntax highlighting — proper NOUS tokenizer for the IDE editor

Pick one and build it.
```

---

*NOUS v3.1.0 — 14 April 2026*
*Created by Hlias Staurou (Hlia) + Claude*
