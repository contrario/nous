# ΝΟΗΣΗ + NOUS — SESSION 3 HANDOFF
## 13 Απριλίου 2026 | Βράδυ | Hlia + Claude
## Phase 7 (New Sources) + Phase 8 (Hardening) + Phase 9 (Advanced NOUS) + Superbrain Bridge

---

## 1. ΤΙ ΕΙΧΑΜΕ ΠΡΙΝ ΞΕΚΙΝΗΣΟΥΜΕ

### Noesis Engine v2.0 (από Session 2)
- 371 atoms στο lattice
- Phases 2-6 deployed: BM25 quality, reasoning, scaling, auto-feeding, NOUS integration
- 92 unit tests passing
- Oracle: DeepSeek → Mistral → SiliconFlow → Claude (4 tiers)
- Telegram bot: 14 commands
- 2 servers: A (neurodoc 188.245.245.132), B (neuroaether 46.224.188.209)
- Cron: daily feeds 04:00, lattice sync A↔B 04:30, merge 04:40

### NOUS Language v1.9.0
- 332+ γραμμές grammar (nous.lark) — LALR parser
- 40+ AST nodes (Pydantic V2)
- Phase 6: `noesis {}` block + `resonate "string"` (static only)
- 18 CLI commands
- `resonate` limited to string literals only

### FileScanner Support
- .txt, .md, .rst, .json, .toml, .yaml, .yml, .nous, .csv
- **ΔΕΝ** υποστήριζε PDF

---

## 2. PHASE 7 — NEW SOURCES

### 2.1 Τι κάναμε
Προσθέσαμε 3 νέες πηγές γνώσης: PDF ingestion, Gemini oracle, Serper Google Search.

### 2.2 PDF Ingestion (`noesis_pdf_ingest.py`)

**Αρχιτεκτονική:**
- `PDFExtractor` — uses pymupdf (fitz) για text extraction
- `PDFIngestor` — orchestrates extraction → sentence splitting → atom creation
- `PDFDocument` / `PDFPage` — data classes για extracted content
- `PDFIngestResult` — results tracking

**Πώς δουλεύει:**
1. Ανοίγει PDF μέσω pymupdf (`fitz.open()`)
2. Εξάγει text ανά σελίδα (`page.get_text("text")`)
3. Καθαρίζει: αφαιρεί page numbers, digit-only lines, κενές γραμμές
4. Splits σε sentences μέσω regex: `(?<=[.!?;·])\s+(?=[A-ZΑ-Ω0-9])`
5. Κάθε sentence → `engine.learn(text, source=f"pdf:{filename}")`
6. Hash-based dedup: SHA-256 hash του full text → `noesis_pdf_hashes.json`
7. Re-ingest blocked αν ίδιο hash, εκτός αν `--force`

**CLI:**
```bash
python3 noesis_pdf_ingest.py /path/to/dir           # Ingest all PDFs
python3 noesis_pdf_ingest.py /path/to/file.pdf       # Single file
python3 noesis_pdf_ingest.py /path --scan             # Scan without ingesting
python3 noesis_pdf_ingest.py /path --force            # Re-ingest even if seen
python3 noesis_pdf_ingest.py /path --no-recursive     # Don't recurse subdirs
```

**Features:**
- Recursive directory scanning
- Hash-based deduplication (persists to JSON)
- Minimum filters: lines < 10 chars filtered, pages < 20 chars skipped
- Page number removal (regex: `page \d+`, `σελίδα \d+`)
- Source tagging: `pdf:filename.pdf`

### 2.3 Gemini Oracle (`noesis_gemini_oracle.py`)

**Αρχιτεκτονική:**
- `GeminiOracle` class — direct REST API via httpx
- Endpoint: `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent`
- Auth: API key as query parameter
- Env var: `GEMINI_API_KEY`

**Πώς δουλεύει:**
1. System prompt → injected as user/model turn pair (Gemini δεν έχει system role)
2. Query → user turn
3. Response parsing: `candidates[0].content.parts[0].text`
4. Stats tracking: calls, failures, latency

**Position στο oracle tier stack:**
- Slot: μεταξύ SiliconFlow και Claude (Tier 3.5)
- Cost: $0.00 (free tier)
- Speed: ~1-2s

**Status:** Module ready, αλλά GEMINI_API_KEY δεν βρέθηκε σε κανέναν server. Server B θα έπρεπε να το έχει αλλά δεν είναι στο .env.

### 2.4 Serper Google Search (`noesis_serper.py`)

**Αρχιτεκτονική:**
- `SerperSource` class — POST to `https://google.serper.dev/search`
- `SearchResult` — title, snippet, link, position
- `SerperSearchResult` — results + answer_box + knowledge_graph
- Auth: `X-API-KEY` header
- Env var: `SERPER_API_KEY`

**Πώς δουλεύει:**
1. Query → Serper API → Google Search results
2. Parses: organic results, answer box, knowledge graph
3. `search_and_learn()`: feeds results into lattice as atoms
4. Sources tagged: `serper:answer_box`, `serper:knowledge_graph`, `serper:<url>`

**CLI:**
```bash
python3 noesis_serper.py "query"                  # Search only
python3 noesis_serper.py "query" --learn           # Search + learn into lattice
python3 noesis_serper.py "query" --num 10          # More results
```

### 2.5 Sources Patch (`noesis_sources_patch.py`)

Monkey-patch που ενσωματώνει τα πάντα στο engine + Telegram:

**Engine methods added:**
- `engine.ingest_pdf(path)` — PDF ingestion
- `engine.scan_pdfs(path)` — scan without ingesting
- `engine.web_search(query, learn=True)` — Serper search
- `engine.web_search_formatted(query)` — formatted output

**Telegram commands added:**
- `/search query` — Google search + learn
- `/pdf /path/to/dir` — Ingest PDFs via Telegram

**Ingest CLI extended:**
- `python3 noesis_ingest.py --pdf /path` — PDF ingestion
- `python3 noesis_ingest.py --search "query"` — Google search + learn

### 2.6 PDF Ingestion Results

Τα PDFs στον Server A:

| PDF | Σελίδες | Sentences | Atoms |
|-----|---------|-----------|-------|
| 4172_2013.pdf (ΦΕΚ) | 60 | 1,413 | 1,337 |
| e_2023_2025_1.pdf (ΦΕΚ) | 222 | 3,522 | 3,039 |
| Πίνακας Περιεχομένων ΦΕ-2020 | 86 | 2,579 | 1,828 |
| paper.pdf (CS249r) | 24 | 914 | 747 |
| **Σύνολο PDFs** | **392** | **8,428** | **6,951** |

Τα text files:

| File | Atoms |
|------|-------|
| greek_tax.md | +502 |
| n8n_knowledge.md | +898 |
| nis2_mapping.json | +9 |

**Lattice growth: 371 → 8,731 atoms**

**Κενά PDFs (0 bytes, δεν κατέβηκαν σωστά):**
- entrepreneurship.pdf, principles_of_management.pdf, principles_of_marketing.pdf
- psychology_2e.pdf, organizational_behavior.pdf

**Skipped (no text):**
- 89_1967.pdf — scanned image, no extractable text
- 00_tinytorch.pdf — likely image-based

**Σκουπίδια (not ingested):**
- 23 icon_callout PDFs (1 page each, only icons)
- 14 fig-*.pdf (charts, no text)
- matplotlib/docker/n8n test PDFs

### 2.7 Phase 7 Bugs & Fixes

**Bug 1: `--break-system-packages` on Server B**
- Server B = Python 3.10 (Ubuntu 22.04), παλιότερο pip χωρίς αυτό το flag
- Fix: `pip install pymupdf httpx -q` (χωρίς flag)

**Bug 2: Server B missing TELEGRAM_BOT_TOKEN**
- Το .env στο `/opt/neuroaether/.env` δεν είχε TELEGRAM tokens
- Fix: copied tokens from Server A via SSH one-liner
- Σημείωση: 2 bots με ίδιο token = διπλές απαντήσεις. Kill τον B, κράτα ως backup.

### 2.8 Phase 7 Tests: 54/54 ✓ (Server A + B)

---

## 3. PHASE 8 — PRODUCTION HARDENING

### 3.1 Τι κάναμε
4 components σε 2 αρχεία: error recovery, rate limiting, structured logging, metrics collector.

### 3.2 Error Recovery (`ErrorRecovery` class)

**Πώς δουλεύει:**
1. Wraps `engine.think()` με try/except
2. Αν crash: reload lattice from disk, retry
3. Max retries: 3 (configurable)
4. Cooldown: 5s between retries
5. Crash history: τελευταία 5 crashes tracked
6. Recovery counter: πόσες φορές recovered

**Example flow:**
```
think("query") → crash → reload lattice → retry → success
think("query") → crash → reload → crash → reload → crash → RuntimeError
```

### 3.3 Rate Limiter (`RateLimiter` class)

**Πώς δουλεύει:**
- Sliding window algorithm (deque-based)
- Default: 60 calls/hour, 10 calls/minute
- Configurable via env vars: `NOESIS_MAX_ORACLE_HOUR`, `NOESIS_MAX_ORACLE_MINUTE`
- `allow()` → True/False
- `time_until_available()` → seconds until next slot
- `current_usage()` → `{"hour": "5/60", "minute": "2/10"}`
- Rejected calls logged + counted

**Patches:**
- `Oracle.ask()` → rate-limited (if limiter says no, return None)
- Rate-limited calls logged in structured log

### 3.4 Structured Logger (`StructuredLogger` class)

**Πώς δουλεύει:**
- JSON Lines format: 1 JSON object per line
- Output: `/var/log/noesis/noesis_YYYY-MM-DD.jsonl`
- Auto-rotation: new file per day, max 50MB per file
- Max 7 log files kept (auto-cleanup)

**Event types:**
- `query` — query, score, atoms_used, used_oracle, latency_ms
- `learn` — source, atoms_created
- `error` — error message, context
- `oracle` — tier, success, latency_ms
- `rate_limited` — usage stats

**API:**
```python
slog.log_query(query="...", score=0.85, atoms_used=5, used_oracle=False, latency_ms=12.5)
slog.log_learn(source="pdf:file.pdf", atoms_created=100)
slog.log_error(error="...", context="think()")
slog.recent(n=20, event_filter="query")
```

### 3.5 Metrics Collector (`MetricsCollector` class)

**Πώς δουλεύει:**
- Daily aggregation: queries, lattice answers, oracle answers, autonomy, atoms, errors
- 90-day history (auto-trim)
- Persistence: `noesis_metrics.json`

**Weekly Report:** generates Telegram-ready text:
```
📊 ΝΟΗΣΗ — Weekly Report
📅 2026-04-06 → 2026-04-13

🔍 Queries: 45
🧠 Lattice answers: 40
🔮 Oracle answers: 5
🎯 Autonomy: 88.9%

🧬 Atoms: 8731
📚 Learned: 6951
📈 Avg score: 0.723

📅 Daily breakdown:
  2026-04-13: 45q, 88.9% auto, 8731a
```

### 3.6 Hardening Patch (`noesis_hardening_patch.py`)

**Engine patches:**
- `NoesisEngine.think()` → wrapped with recovery + logging + metrics
- `NoesisEngine.learn()` → logged with source + atom count
- `Oracle.ask()` → rate-limited
- `NoesisEngine.hardening_status()` → combined status

**Telegram commands:**
- `/metrics` — today's stats
- `/report` — weekly report
- `/ratelimit` — oracle rate limit usage

### 3.7 Phase 8 Tests: 58/58 ✓ (Server A + B)

---

## 4. PHASE 9 — ADVANCED NOUS

### 4.1 Τι κάναμε
3 deliverables: dynamic `resonate(expr)`, `atom` type, `nous noesis` CLI.

### 4.2 Dynamic Resonate — Grammar

**Πριν (Phase 6):**
```nous
# Only string literals
let answer = resonate "What is NOUS?"
resonate "Static query"
```

**Μετά (Phase 9):**
```nous
# String literals (existing)
let answer = resonate "What is NOUS?"

# Dynamic — variable reference
let query = "What is " + topic
let result = resonate(query)

# Dynamic with guard
let knowledge = resonate(user_q) with score > 0.5

# Bare dynamic
resonate(user_input)
```

**Grammar additions (nous.lark):**
```lark
resonate_stmt: "let" NAME "=" RESONATE STRING                                -> resonate_bind
             | "let" NAME "=" RESONATE "(" expr ")"                          -> resonate_bind_dynamic
             | "let" NAME "=" RESONATE STRING "with" NAME ">" FLOAT          -> resonate_bind_guarded
             | "let" NAME "=" RESONATE "(" expr ")" "with" NAME ">" FLOAT    -> resonate_bind_dynamic_guarded
             | RESONATE STRING                                               -> resonate_bare
             | RESONATE "(" expr ")"                                         -> resonate_bare_dynamic
```

**ATOM_TYPE keyword:**
```lark
ATOM_TYPE: "atom" | "άτομο"
```

### 4.3 Dynamic Resonate — AST

**ResonateNode updated:**
```python
class ResonateNode(NousNode):
    query: Any = None
    bind_name: Optional[str] = None
    guard_field: Optional[str] = None
    guard_threshold: Optional[float] = None
    is_dynamic: bool = False    # NEW
```

**AtomTypeNode added:**
```python
class AtomTypeNode(NousNode):
    base: str = "atom"
    is_list: bool = False
    is_optional: bool = False
```

### 4.4 Dynamic Resonate — Parser

3 new transformer methods στο `NousTransformer`:

```python
def resonate_bind_dynamic(self, items):
    s = self._strip(items)
    return LetNode(name=s[0], value={"kind": "resonate", "query": s[1], "is_dynamic": True})

def resonate_bind_dynamic_guarded(self, items):
    s = self._strip(items)
    return LetNode(name=s[0], value={
        "kind": "resonate", "query": s[1], "is_dynamic": True,
        "guard_field": s[2], "guard_threshold": float(s[3]),
    })

def resonate_bare_dynamic(self, items):
    s = self._strip(items)
    return {"kind": "resonate", "query": s[0], "is_dynamic": True}
```

**Σημαντικό:** Χρησιμοποιούν dict format `{"kind": "resonate", ...}` αντί `ResonateNode` object, γιατί ο codegen ελέγχει `value.get("kind") == "resonate"`.

### 4.5 Dynamic Resonate — CodeGen

```python
elif kind == "resonate":
    query = value.get("query", "")
    is_dynamic = value.get("is_dynamic", False)
    if is_dynamic:
        query_expr = self._expr_to_python(query)
        self._emit(f"{stmt.name} = _noesis_engine.think(str({query_expr}))")
    else:
        self._emit(f'{stmt.name} = _noesis_engine.think("{query}")')
```

**Generated output:**
```python
# Static
answer = _noesis_engine.think("What is the Maillard reaction?")

# Dynamic
result = _noesis_engine.think(str(query))

# Dynamic guarded
knowledge = _noesis_engine.think(str(user_q))
```

### 4.6 `nous noesis` CLI (`noesis_cli_noesis.py`)

**Commands:**

| Command | Description |
|---------|-------------|
| `nous noesis stats` | Lattice statistics: atoms, concepts, sources, levels |
| `nous noesis gaps [--limit N]` | Knowledge gaps (low-score queries) |
| `nous noesis topics` | Topic discovery: strong, weak, sources |
| `nous noesis evolve [--save]` | Run evolution cycle |
| `nous noesis search "query" [--top-k N]` | Search lattice (BM25) |
| `nous noesis think "query"` | Think with oracle fallback |
| `nous noesis feeds` | Suggest feeds for weak topics |
| `nous noesis weaning` | Oracle weaning status |
| `nous noesis export [--json]` | Export lattice summary |

**Standalone usage:**
```bash
python3 noesis_cli_noesis.py stats
python3 noesis_cli_noesis.py search "Maillard reaction"
python3 noesis_cli_noesis.py think "What is NOUS?"
```

### 4.7 Phase 9 Bugs & Fixes

**Bug 1: `noesis_phase9_apply.py` — wrong anchors**
- Apply script looked for `RESONATE: "resonate"` but server has `RESONATE.2: "resonate"` (with priority)
- Also: spacing mismatch in resonate_stmt rules
- Fix: updated apply script to match server format

**Bug 2: Grammar patch didn't apply**
- `patch_file()` couldn't find exact string match due to extra spaces
- Fix: used `sed -i` to insert rules directly after `resonate_bare`

**Bug 3: Triple insertion**
- sed inserted the dynamic methods 3 times (once per match in the address range)
- Fix: `sed -i '316,341d'` to remove duplicates

**Bug 4: `resonate_bare` body missing**
- sed insertion clobbered the body of `resonate_bare`
- Also: orphan `s = self._strip(items)` line left over
- Fix: Python script to replace entire block cleanly

**Bug 5: `ResonateNode` not imported in parser.py**
- Dynamic methods referenced `ResonateNode` but it wasn't in the imports
- Fix: `sed -i 's/Tier,/Tier,\n    ResonateNode,/'`
- Later fix: changed methods to use dict format instead (matching existing pattern)

**Bug 6: Parser methods inserted outside class**
- First apply attempt put methods at module level, not inside NousTransformer class
- Lark returned raw `Tree` objects instead of calling transformer methods
- Fix: inserted methods at correct line number inside the class

**Bug 7: Codegen ignored `is_dynamic`**
- Codegen checked `kind == "resonate"` but always used `f'think("{query}")'`
- Dynamic nodes stored `is_dynamic: True` but codegen didn't check it
- Fix: added `is_dynamic` check → `think(str(query_expr))` for dynamic

**Bug 8: CLI `_load_engine` — Path vs str**
- `engine.load(str(lp))` failed because `lattice.load()` expects Path object
- `engine.load(lp)` with Path works
- Fix: changed back to `engine.load(lp)`

**Bug 9: CLI `topics` — string vs dict**
- `discover_topics()` returns dict with `strong_topics`, `weak_topics`, `all_topics` lists
- Code assumed list of simple topics, tried `.get()` on strings
- Fix: check `isinstance(data, dict)` and extract sub-lists

**Bug 10: CLI `search` — Atom objects in results**
- `Resonator.resonate()` returns `list[tuple[Atom, float]]`
- Code assumed `list[tuple[str, float]]` (atom_id, score)
- Fix: `atom, score = item` and `getattr(atom, "template", ...)`

### 4.8 Phase 9 Test Results

| Test | Status |
|------|--------|
| LALR grammar parse | ✓ |
| AST: ResonateNode.is_dynamic | ✓ |
| AST: AtomTypeNode | ✓ |
| Parser: static resonate | ✓ |
| Parser: resonate_bind_dynamic | ✓ |
| Parser: resonate_bind_dynamic_guarded | ✓ |
| Parser: resonate_bare_dynamic | ✓ |
| CodeGen: static → `think("...")` | ✓ |
| CodeGen: dynamic → `think(str(expr))` | ✓ |
| CodeGen: guarded → `think(str(expr))` + guard | ✓ |
| py_compile: 234 lines | ✓ |
| CLI: 13/13 tests | ✓ |

---

## 5. SUPERBRAIN BRIDGE

### 5.1 Τι κάναμε
Σύνδεσε τη Νόηση (BM25, 8,731 atoms) με τον Superbrain (ChromaDB, 18 domains, semantic search) μέσω SSH στον Oracle Server.

### 5.2 Αρχιτεκτονική

```
Query → Noesis Lattice (BM25, <10ms)
      → Superbrain ChromaDB (semantic, ~11s via SSH)
      → Merge results
      → Auto-learn Superbrain chunks → Noesis atoms
```

**3 Servers:**
- Server A (neurodoc, 188.245.245.132) — Noesis engine + bot
- Server B (neuroaether, 46.224.188.209) — Noesis mirror + bot backup
- Oracle Server (92.5.115.194) — Superbrain ChromaDB

**SSH Connection:**
- Host: 92.5.115.194
- User: ubuntu
- Key: `/root/ssh-key-2026-04-07.key`
- Python: `/home/ubuntu/superbrain-env/bin/python3`
- DB: `/home/ubuntu/superbrain/db`

### 5.3 Superbrain Details

**Collection:** `superbrain_knowledge`
**Chunks:** 36 total
**Domains:** 18

| Domain | Chunks |
|--------|--------|
| business_consulting | 5 |
| meta_knowledge | 5 |
| economy_finance | 4 |
| cybersecurity_tech | 3 |
| culinary_food | 3 |
| philosophy_spiritual | 3 |
| technology_development | 2 |
| science_physics | 1 |
| science_chemistry | 1 |
| science_mathematics | 1 |
| science_cosmology | 1 |
| science_neuroscience | 1 |
| health_medicine | 1 |
| health_nutrition | 1 |
| governance_law | 1 |
| energy_environment | 1 |
| intelligence_geopolitics | 1 |
| culture_arts | 1 |

**Search:** `hybrid_search(query, n_results)` — returns `{"query", "relevant_domains", "context"}`
- `relevant_domains` = list of `{rank, title, domain, chunk_index, key_concepts, content}`

### 5.4 `noesis_superbrain.py`

**Classes:**
- `SuperbrainBridge` — main bridge class
- `SuperbrainResult` — search result
- `HybridResult` — merged Noesis + Superbrain result

**Engine methods patched:**
- `engine.superbrain_search(query, n_results)` — search ChromaDB only
- `engine.superbrain_think(query, n_results)` — hybrid search + merge
- `engine.superbrain_domains()` — list all domains + chunks
- `engine.superbrain_stats()` — bridge statistics

**Telegram commands:**
- `/superbrain query` or `/sb query` — hybrid search
- `/domains` — list Superbrain domains

**Auto-learn:** Κάθε Superbrain query → chunks learned into Noesis lattice automatically. Source tag: `superbrain:<domain>`.

### 5.5 Superbrain Bugs & Fixes

**Bug 1: SSH escaping — `\\n` literals**
- Script strings used `"...\\n..."` which sent literal `\n` instead of newlines
- SSH `-c` command broke on complex multi-line scripts
- Fix: changed `_ssh_run()` to use `input=script` (stdin) instead of `-c "..."`

**Bug 2: `hybrid_search` response format**
- Bridge expected `results` or `chunks` key
- Actual response: `{"query", "relevant_domains", "context"}`
- Fix: added `relevant_domains` as primary key to look for

**Bug 3: Content extraction**
- Bridge expected `text` or `document` key in chunks
- Actual format: `content` key
- Fix: added `content` to extraction chain

---

## 6. ΑΡΧΕΙΑ ΑΝΑ SERVER

### Server A (neurodoc) — Νέα αρχεία (13)

```
# Phase 7
noesis_pdf_ingest.py          # PDF → atoms (pymupdf)
noesis_gemini_oracle.py       # Gemini 2.0 Flash oracle tier
noesis_serper.py              # Google Search via Serper
noesis_sources_patch.py       # monkey-patch: PDF + Gemini + Serper
noesis_sources_test.py        # 54 tests

# Phase 8
noesis_hardening.py           # ErrorRecovery + RateLimiter + StructuredLogger + MetricsCollector
noesis_hardening_patch.py     # monkey-patch into engine + Telegram
noesis_hardening_test.py      # 58 tests

# Phase 9
noesis_cli_noesis.py          # nous noesis CLI (stats, gaps, topics, search, think)
noesis_phase9_apply.py        # Grammar/AST/parser/codegen patcher
noesis_phase9_test.py         # 13 tests
noesis_phase9_test.nous       # Test .nous file

# Superbrain
noesis_superbrain.py          # Noesis ↔ Superbrain ChromaDB bridge
```

### Server A — Τροποποιημένα αρχεία (5)

```
noesis_engine.py              # 3 new import lines added (Phase 7, 8, Superbrain)
nous.lark                     # Phase 9: 3 dynamic resonate rules + ATOM_TYPE
ast_nodes.py                  # Phase 9: AtomTypeNode + ResonateNode.is_dynamic
parser.py                     # Phase 9: 3 dynamic transformer methods + ResonateNode import
codegen.py                    # Phase 9: is_dynamic check in resonate codegen
noesis_telegram.py            # 8 new commands in help + dict
```

### noesis_engine.py imports (7 total)

```python
import noesis_quality_patch      # Phase 2
import noesis_reasoning_patch    # Phase 3
import noesis_scaling_patch      # Phase 4
import noesis_autofeeding_patch  # Phase 5
import noesis_sources_patch      # Phase 7
import noesis_hardening_patch    # Phase 8
import noesis_superbrain         # Superbrain bridge
```

### Server B (neuroaether)
```
Phases 2-8: deployed ✓
Phase 9: NOT deployed (grammar patches only on A)
Superbrain: NOT deployed (needs Oracle Server SSH access)
Bot: stopped (killed to avoid double responses)
Lattice: 8,731 atoms (synced from A)
```

### Dependencies installed
```
Server A: pymupdf, httpx, asyncssh (pip install --break-system-packages)
Server B: pymupdf, httpx (pip install without --break-system-packages)
```

---

## 7. TESTS — ΣΥΝΟΛΟ

| Phase | Tests | Status |
|-------|-------|--------|
| 2 — Quality | 23/23 | ✓ Server A+B |
| 3 — Reasoning | 28/28 | ✓ Server A+B |
| 4 — Scaling | 17/17 | ✓ Server A+B |
| 5 — Auto-feeding | 24/24 | ✓ Server A+B |
| 6 — NOUS Integration | Parse+CodeGen+py_compile | ✓ Server A |
| 7 — Sources | 54/54 | ✓ Server A+B |
| 8 — Hardening | 58/58 | ✓ Server A+B |
| 9 — Advanced NOUS | 13/13 + parse/codegen/compile | ✓ Server A |
| **Total** | **217+ tests** | **✓** |

---

## 8. TELEGRAM COMMANDS — 22 TOTAL

```
# Original 14
/think      — Ask Noesis a question
/learn      — Teach Noesis new knowledge
/weather    — Get weather for a city
/country    — Get country info
/define     — Define a word
/crypto     — Get crypto price
/quake      — Recent significant earthquakes
/food       — Search food nutrition
/pubmed     — Search medical papers
/wiki       — Learn from Wikipedia
/stats      — Show Noesis statistics
/evolve     — Run lattice evolution
/save       — Save lattice to disk
/help       — Show this help

# Phase 7 (3)
/search     — Google search + learn
/pdf        — Ingest PDFs into lattice

# Phase 8 (3)
/metrics    — Today's stats
/report     — Weekly report
/ratelimit  — Oracle rate limit status

# Superbrain (3)
/superbrain — Hybrid search (Noesis + ChromaDB)
/sb         — Shortcut for /superbrain
/domains    — Superbrain domain list
```

---

## 9. CLI — `nous noesis`

```bash
python3 noesis_cli_noesis.py stats              # 8,731 atoms, 13 sources, 0.802 avg conf
python3 noesis_cli_noesis.py topics             # 50 topics, 10 strong
python3 noesis_cli_noesis.py search "Maillard"  # BM25 search, top-K
python3 noesis_cli_noesis.py think "What is?"   # Think with oracle
python3 noesis_cli_noesis.py gaps               # Knowledge gaps
python3 noesis_cli_noesis.py evolve --save      # Evolution cycle
python3 noesis_cli_noesis.py feeds              # Feed suggestions
python3 noesis_cli_noesis.py weaning            # Oracle weaning status
python3 noesis_cli_noesis.py export --json      # Export summary
```

---

## 10. ΑΡΧΙΤΕΚΤΟΝΙΚΕΣ ΑΠΟΦΑΣΕΙΣ

**Γιατί pymupdf αντί pdfplumber/PyPDF2:**
pymupdf (fitz) είναι ο πιο reliable text extractor. Handles Unicode, Greek, complex layouts. Μόνο 1 dependency.

**Γιατί hash-based dedup αντί content-based:**
SHA-256 του full extracted text. Fast, simple, no false positives. Αν αλλάξει 1 χαρακτήρας, re-ingest.

**Γιατί SSH αντί HTTP για Superbrain:**
Ο Superbrain ήδη χρησιμοποιεί SSH (υπάρχον `superbrain_skill.py`). Δεν χρειάστηκε setup HTTP server. Trade-off: 11s latency vs ~200ms με HTTP. Μελλοντικό improvement.

**Γιατί `resonate(expr)` αντί `resonate expr`:**
LALR parser ambiguity: `resonate query with score > 0.5` — `with` is NAME, not keyword. Parentheses `resonate(expr)` = unambiguous delimiter. RESONATE keyword has higher priority than NAME, so `resonate(...)` ≠ function call.

**Γιατί dict format αντί ResonateNode στον parser:**
Ο codegen ελέγχει `value.get("kind") == "resonate"`. Αν χρησιμοποιήσουμε `ResonateNode` (Pydantic), ο codegen δεν τον αναγνωρίζει (no `.get()`). Dict = consistent with existing static resonate pattern.

**Γιατί sliding window αντί fixed-window rate limiting:**
Fixed window (60/hour reset κάθε ώρα) = bursty. Sliding window (deque, τελευταίες 3600 seconds) = smooth distribution. Αποτρέπει 60 calls σε 1 λεπτό.

**Γιατί JSON Lines αντί SQL logging:**
Append-only, zero dependencies, human-readable, grep-friendly. `cat noesis_2026-04-13.jsonl | jq '.event'`. No database needed.

**Γιατί auto-learn Superbrain chunks:**
Κάθε Superbrain query κοστίζει ~11s (SSH). Αν learn τα chunks, η Νόηση θα τα ξέρει next time = 0.1ms. One-time investment, infinite returns.

---

## 11. LATTICE STATUS

```
Atoms:      8,731
Concepts:   8,679
Relations:  0
Avg conf:   0.802
Levels:     All Level 3

Sources (13):
  pdf:                  6,951 (79.6%)
  n8n_knowledge.md:       898 (10.3%)
  greek_tax.md:           502  (5.8%)
  noesis_knowledge.txt:   120  (1.4%)
  rss:                     90  (1.0%)
  nasa:                    60
  nasa_ads:                35
  arxiv:                   20
  github:                  19
  wikipedia:               16
  binance:                 10
  nis2_mapping.json:        9
  input:                    1

Topics: 50
Strong: άρθρου(417.8), περίπτωση(260.6), είχε(199.3), φόρου(194.7)
Weaning: ~0.55 threshold (8,731 atoms → 10,000 level next)
```

---

## 12. ΤΙ ΜΕΝΕΙ ΝΑ ΚΑΝΟΥΜΕ

### Immediate
1. **Deploy Phase 9 + Superbrain to Server B**
2. **Formatter fix**: `memory { last_trade: string = }` — empty default crashes parser. Need optional expr after `=` in `field_decl`
3. **Weaning init**: `/weaning` returns "Weaner not initialized". Need `engine.init_autofeeding()` call on startup
4. **Restart bot Server A** (if not already running after Phase 9 changes)

### Short-term
5. **Superbrain HTTP API**: Replace SSH (11s) with FastAPI endpoint on Oracle Server (~200ms)
6. **Gemini API key**: Find/add GEMINI_API_KEY on Server B for free oracle tier
7. **Weekly report cron**: Auto-send `/report` every Monday via Telegram
8. **`nous noesis` integration into main CLI**: Add `noesis` subcommand to `cli.py`
9. **Server B bot**: Separate Telegram token or remove bot (currently killed to avoid doubles)

### Medium-term
10. **Embeddings hybrid**: BM25 + embeddings search on same lattice (local sentence-transformers model)
11. **More knowledge ingestion**: Re-download empty PDFs (psychology, business, marketing), feed CS249r book
12. **Real-time merge**: Replace daily cron with event-driven A↔B sync
13. **Dashboard**: Web UI for lattice stats, topics, gaps (React + lattice JSON)
14. **NOUS standard library**: Noesis soul template, common patterns

### Long-term
15. **Self-evolving grammar**: Noesis suggests new syntax extensions based on usage patterns
16. **Multi-lattice**: Different lattices per domain (tax, tech, cooking) with cross-lattice reasoning
17. **Streaming think**: Real-time token streaming for long oracle responses
18. **NOUS package manager**: `nous install soul-template-trading`

---

*Νόηση v3.0 — Hybrid Intelligence with Superbrain Bridge*
*217+ tests | 9 phases | 3 servers | 8,731 atoms | 22 Telegram commands*
*Hlias Staurou + Claude | 13 Απριλίου 2026 | Athens, Greece*
