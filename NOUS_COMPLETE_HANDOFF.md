# NOUS (Νοῦς) — COMPLETE PROJECT HANDOFF
## Sessions 1 & 2 | 11 Απριλίου 2026 | Hlia + Claude
## The Living Language — From Zero to Running System

---

## 1. ΤΙ ΕΙΝΑΙ ΤΟ NOUS

NOUS (Νοῦς) είναι μια πλήρης γλώσσα προγραμματισμού σχεδιασμένη αποκλειστικά για multi-agent AI systems. Δεν είναι framework, δεν είναι library — είναι γλώσσα με δική της γραμματική, parser, validator, compiler, runtime, και REPL.

**Σε μία πρόταση:** Γράφεις agents σε 140 γραμμές NOUS, ο compiler παράγει 333 γραμμές production Python, και τρέχει live σε asyncio runtime με real tools, real APIs, και real money tracking.

### 1.1 Γιατί χρειαζόταν

Το Noosphere ecosystem (100+ agents, 143+ tools, 4 servers) διαχειριζόταν μέσω 89+ YAML/TOML αρχείων:
- 80% του κώδικα ήταν plumbing, 20% agent logic
- Δεν υπήρχε type safety μεταξύ agents
- Η DAG orchestration ήταν hardcoded σε Python
- Η εξέλιξη (mutation) λειτουργούσε πάνω σε text files, όχι σε δομημένα δεδομένα
- Κάθε αλλαγή σε agent behavior απαιτούσε αλλαγές σε 3-5 αρχεία

### 1.2 Τι λύνει

| Πρόβλημα | NOUS Λύση |
|----------|-----------|
| Agents ως YAML configs | Agents (`soul`) είναι first-class citizens στη γραμματική |
| Hardcoded orchestration | DAG (`nervous_system`) είναι native σύνταξη: `Scout -> Quant -> Hunter` |
| Safety ως middleware | Safety (`law`) είναι φυσικός νόμος, compile-time enforced |
| Evolution σε text files | Evolution (`dna`) built into syntax, mutations σε typed AST |
| Error handling σε try/except | Self-repair (`heal`) είναι declarative ανά error type |
| 89 config files | 1 αρχείο `.nous` per cluster |

### 1.3 Τι δανειστήκαμε

| Γλώσσα | Feature | Πώς το χρησιμοποιεί η NOUS |
|--------|---------|---------------------------|
| Python | Σύνταξη, indentation | LLM-friendly, familiar syntax |
| Rust | Ownership model | Agent memory owned, others borrow via listen |
| Go | Goroutines, channels | spawn soul, typed channels |
| Erlang | Actor model, let-it-crash | Souls = actors, heal = supervision |
| Mojo | fn vs def, metaprogramming | instinct = compiled, dna = metaprogramming |
| TypeScript | Strict typing with inference | Parse-time validation |
| Dataflow DSLs | DAG-native -> operator | A -> B -> C is first-class syntax |

---

## 2. ΑΡΧΙΤΕΚΤΟΝΙΚΗ

### 2.1 Compilation Pipeline

```
.nous source file
       │
  ┌────▼─────┐
  │Lark Parser│  ← nous.lark (EBNF Grammar, ~200 rules)
  │(Earley)   │     Bilingual: English + Greek keywords
  └────┬─────┘
       │
  ┌────▼─────────┐
  │NousTransformer│  ← parser.py (CST → AST)
  │+ keyword merge│     Fixes Earley ambiguity post-hoc
  └────┬─────────┘
       │
  ┌────▼──────┐
  │Living AST  │  ← ast_nodes.py (40+ Pydantic V2 nodes)
  │(Ψυχόδενδρο)│    Mutable, persists in memory
  └──┬────┬───┘
     │    │
┌────▼──┐ ┌▼───────┐
│Validtr│ │Aevolver│  ← validator.py + aevolver.py
│(Laws) │ │(DNA)   │    Shadow copy → mutate → validate → commit/rollback
└───────┘ └────────┘
     │
┌────▼─────┐
│CodeGen   │  ← codegen.py
│(Python)  │    AST → asyncio + runtime.py integration
└────┬─────┘
     │
┌────▼──────────┐
│NOUS Runtime   │  ← runtime.py
│+ Noosphere    │    Tool dispatch, LLM calls, channels, perception
└────────────────┘
```

### 2.2 Runtime Architecture

```
NousRuntime
├── ToolRegistry          — Loads tools from /opt/aetherlang_agents/tools/
│   ├── scan_noosphere()  — Auto-discovers .py tool files
│   ├── register_stub()   — Register test tools
│   └── call()            — Dispatches to tool's execute() function
├── LLMCaller             — Multi-tier LLM API calls
│   ├── Tier0A: Anthropic (claude-haiku, claude-sonnet)
│   ├── Tier0B: OpenAI (gpt-4o)
│   ├── Tier1: OpenRouter (deepseek-r1, mimo)
│   ├── Tier2: OpenRouter free (gemini-flash)
│   └── Tier3: Ollama local (gemma3, qwen3)
├── CostTracker           — Budget enforcement per cycle
│   └── Tracks cost per soul per operation
├── ChannelRegistry       — asyncio.Queue message passing
│   ├── send(key, message) — Typed messages between souls
│   └── receive(key, timeout) — With timeout + stats
├── PerceptionEngine      — External event triggers
│   ├── cron loops
│   ├── telegram triggers
│   └── wake/wake_all/alert actions
└── DataProxy + ToolResult — Ergonomic data access
    ├── .filter(field, op, value) — List filtering
    ├── __getattr__ → data fields — Dot notation for dicts
    ├── __lt__, __gt__, etc.     — Comparison operators
    └── __float__, __int__       — Numeric coercion
```

---

## 3. ΑΡΧΕΙΑ ΣΤΟΝ SERVER

```
/opt/aetherlang_agents/nous/
├── nous.lark                 # EBNF Grammar (~200 rules, bilingual EN+GR)
├── ast_nodes.py              # 40+ Pydantic V2 Living AST nodes
├── parser.py                 # Lark Transformer → Living AST (with keyword merge)
├── validator.py              # 8 error categories, cycle detection
├── codegen.py                # AST → Python 3.11+ asyncio + runtime integration
├── runtime.py                # Tool dispatch, LLM, costs, channels, perception
├── cli.py                    # 12 CLI commands (v1.3.0)
├── repl.py                   # Interactive NOUS shell
├── nsp.py                    # NSP protocol (70% token savings)
├── aevolver.py               # DNA mutation engine on Living AST
├── aevolver_live.py          # Live evolution: Langfuse + scheduler + git + Telegram
├── bridge.py                 # Noosphere integration analyzer
├── migrate.py                # YAML/TOML → .nous converter
├── install.sh                # /usr/local/bin/nous wrapper
├── gate_alpha.nous           # Example: 4-soul trading cluster (source)
├── gate_alpha.py             # Generated Python output (333 lines)
├── gate_alpha_generated.py   # Session 1 generated output (reference)
├── noosphere_migrated.nous   # 106 agents migrated (2716 lines)
├── paper_portfolio.json      # Paper trading state
├── evolution_history.json    # Evolution cycle log
├── nohup.out                 # Daemon scheduler output
└── README.md                 # Documentation
```

**Tools deployed (9 νέα στο /opt/aetherlang_agents/tools/):**
```
gate_alpha_scan.py    — DexScreener API market scanner
fetch_rsi.py          — RSI-14 calculator from price data
calculate_kelly.py    — Kelly criterion position sizing
backtest_pair.py      — Momentum backtest engine
execute_paper_trade.py — Paper trading with JSON portfolio
check_balance.py      — Portfolio balance reader
check_positions.py    — Open position monitor
send_telegram.py      — Telegram Bot API notifications
ddgs_search.py        — DuckDuckGo search wrapper
```

---

## 4. SESSION 1 — ΛΕΠΤΟΜΕΡΕΙΕΣ (Phases 1-10)

### Phase 1: EBNF Grammar (`nous.lark`)
**Τι:** ~200 κανόνες σε Lark EBNF format.
**Γιατί:** Η γραμματική είναι ο θεμέλιος λίθος — parser/validator/codegen ακολουθούν μηχανικά.
**Πώς:** Rules για world, soul, mind, memory, instinct, dna, heal, nervous_system, evolution, perception, message, nsp, deploy, topology. Bilingual keywords (English + Greek).
**Fix:** Named tokens αντί anonymous (`ADD_OP` αντί `+`), dedicated `WAKE_ALL` keyword.

### Phase 2: Living AST (`ast_nodes.py`)
**Τι:** 40+ Pydantic V2 BaseModel nodes.
**Γιατί:** Typed, validated, serializable AST. Δεν πετιέται μετά compile — ο Aevolver μεταλλάσσει nodes απευθείας.
**Nodes:** WorldNode, SoulNode, MindNode, MemoryNode, InstinctNode, DnaNode, HealNode, MessageNode, NervousSystemNode, EvolutionNode, PerceptionNode, LetNode, RememberNode, SpeakNode, GuardNode, SenseCallNode, IfNode, ForNode, GeneNode, LawCost, LawDuration, κλπ.

### Phase 3: Parser (`parser.py`)
**Τι:** Lark Transformer (CST → Living AST).
**Γιατί:** Lark δίνει CST — χρειαζόμαστε typed AST.
**Κρίσιμο fix (Session 2):** Ο Earley parser δεν ξεχωρίζει `sense`/`speak`/`guard` ως keywords — τα βλέπει ως NAME. Η `_merge_keyword_stmts()` μέθοδος σκανάρει τα statements post-hoc και τα ενώνει:
- `["sense", func_call_dict]` → `SenseCallNode`
- `["speak", func_call_dict]` → `SpeakNode`
- `["guard", condition_dict]` → `GuardNode`
- `LetNode(value="sense")` + `func_call` → `LetNode(value=sense_call)`
- `"peak"` (artifact from `speak` tokenization) + `func_call` → `SpeakNode`
- Duration artifacts (`70s` from `70` + `speak`) → fixed via `_fix_duration_artifacts()`

**`sense_call()` fix (Session 2):** Ο transformer λαμβάνει `[var_name, SENSE_token, tool_name, args]` μετά την αφαίρεση literals. Αναγνωρίζει τη θέση του SENSE token και χειρίζεται σωστά let-sense patterns.

### Phase 4: Validator (`validator.py`)
**Τι:** 8 κατηγορίες ελέγχων στο Living AST.
**Checks:**
- W001: World exists
- S001-S005: Duplicate souls, missing mind/heal/instinct/senses
- D001-D002: DNA range validity
- N001-N003: Nervous system undefined refs, cycle detection (DFS)
- E001-E002: Evolution undefined targets
- P001-P002: Perception undefined wake/broadcast targets
- T001-T002: speak/listen type compatibility

### Phase 5: CodeGen (`codegen.py`)
**Τι:** AST → Python 3.11+ asyncio.
**Session 1 output:** Dummy `self._sense_toolname()` calls.
**Session 2 rewrite:** 
- `sense tool()` → `await self._runtime.sense(self.name, "tool", ...)`
- `speak Type()` → `await self._runtime.channels.send("Soul_Type", Type(...))`
- `listen Soul::Type` → `await self._runtime.channels.receive("Soul_Type")`
- `guard condition` → `if not (condition): return`
- `.where(field > value)` → `.filter("field", ">", value)` (list comprehension)
- `world.config.x` → `runtime.laws.get("config.x", "")`
- `BudgetExceededError` handling in run loop
- String literals preserve quotes (`"BUY"` not `BUY`)

### Phase 6: CLI (`cli.py`)
**v1.1.0 (Session 1):** 9 commands — compile/run/validate/ast/evolve/nsp/info/bridge/version.
**v1.3.0 (Session 2):** 12 commands — added shell/evolve-live. Install: `/usr/local/bin/nous` wrapper.

### Phase 7: NSP (`nsp.py`)
**Τι:** Parser/validator για `[NSP|CT.88|F.78|M.safe]` tokens.
**Αποτέλεσμα:** 40-70% token savings σε LLM prompts.

### Phase 8: Aevolver (`aevolver.py`)
**Τι:** DNA mutation engine στο Living AST.
**Process:** Shadow copy → mutate genes εντός declared ranges → validate κατά laws → measure fitness → accept αν βελτιώθηκε, rollback αν όχι.

### Phase 9: Bridge (`bridge.py`)
**Τι:** Scans Noosphere tools/agents, maps souls → agents, senses → tools.
**Αποτέλεσμα:** 52 tools, 106 agents detected.

### Phase 10: Migration (`migrate.py`)
**Τι:** YAML/TOML → `.nous` converter.
**Αποτέλεσμα:** 106 agents → 2716 γραμμές NOUS, zero errors.

---

## 5. SESSION 2 — ΛΕΠΤΟΜΕΡΕΙΕΣ

### Priority 1: Runtime Integration (`runtime.py`)

**Πρόβλημα:** Ο generated Python είχε dummy sense calls (`self._sense_toolname()`) χωρίς υλοποίηση. Κανένα generated πρόγραμμα δεν μπορούσε να τρέξει πραγματικά.

**Λύση:** Δημιουργήσαμε πλήρες runtime layer:

**ToolRegistry:**
- Σαρώνει `/opt/aetherlang_agents/tools/*.py` αυτόματα
- Φορτώνει modules δυναμικά μέσω `importlib.util`
- Υποστηρίζει standalone functions (`execute(**kwargs)`) και classes (`.execute()`)
- Stub registration για testing
- Graceful error handling — tools με relative imports (παλιά Noosphere) αγνοούνται

**LLMCaller:**
- Anthropic API (native format)
- OpenAI-compatible (OpenRouter, Ollama)
- Cost tracking per call (input/output tokens × tier rate)
- Async httpx client

**CostTracker:**
- Budget per cycle (from `law CostCeiling = $0.10 per cycle`)
- Raises `BudgetExceededError` when exceeded
- Per-soul, per-operation cost logging

**ChannelRegistry:**
- asyncio.Queue per channel
- Named channels: `{SoulName}_{MessageType}`
- Timeout with clear error messages
- Stats tracking (sent/received counts)

**PerceptionEngine:**
- Cron expression parsing → interval loops
- wake/wake_all/alert action dispatch
- Telegram trigger registration

**DataProxy + ToolResult:**
- `DataProxy`: wraps dicts, provides dot-notation access (`token.pair`, `token.volume_24h`)
- `ToolResult.filter(field, op, value)`: filters list data by field comparison
- Comparison operators (`__lt__`, `__gt__`, `__eq__`): delegates to `_primary_value()`
- Numeric coercion (`__float__`, `__int__`): for use in arithmetic expressions
- Auto-unwrap: tools returning `{"data": [...]}` → ToolResult.data becomes the list

### Priority 2: Gate Alpha Live (9 Tools)

**Πρόβλημα:** Το Gate Alpha `.nous` πρόγραμμα αναφερόταν σε 9 tools που δεν υπήρχαν.

**Λύση:** 9 production-ready tool modules:

**gate_alpha_scan.py:**
- DexScreener Search API (`/latest/dex/search`)
- Filters: chain (Solana/Base), min volume, min liquidity
- Composite scoring: volume (30%) + liquidity (20%) + momentum (25%) + buy pressure (25%)
- Returns sorted candidates list

**fetch_rsi.py:**
- DexScreener Pairs API for price data
- Synthetic price series from 5m/1h/6h/24h price changes
- RSI-14 calculation (Wilder's smoothing)
- Returns rsi value + price info

**calculate_kelly.py:**
- Kelly criterion: f* = (bp - q) / b
- Fallback: momentum × 0.6 + rsi_factor × 0.4
- Capped at 25% max position
- Accepts signal object or explicit parameters

**backtest_pair.py:**
- Simulated returns from DexScreener price changes
- Tracks capital, wins, max drawdown
- Returns total return %, win rate, Sharpe ratio

**execute_paper_trade.py:**
- JSON file portfolio state (`paper_portfolio.json`)
- BUY: deducts from balance, creates position record
- CLOSE: calculates PnL, updates balance
- Handles Decision objects from Quant soul

**check_balance.py / check_positions.py:**
- Read paper_portfolio.json
- Return balance, total trades, PnL, open positions

**send_telegram.py:**
- Telegram Bot API (`/bot{token}/sendMessage`)
- Graceful fallback to local logging when token not set
- HTML parse mode

**ddgs_search.py:**
- `duckduckgo_search` package (primary)
- Fallback to lite HTML scraping

### Priority 3: Aevolver Live (`aevolver_live.py`)

**Πρόβλημα:** Η evolution τρέχει μόνο χειροκίνητα, δεν συνδέεται με πραγματικό fitness data, δεν κάνει git commit, δεν ενημερώνει τα source files.

**Λύση:** Full live evolution pipeline:

**LangfuseFitness:**
- Connects to self-hosted Langfuse (`langfuse.neurodoc.app`)
- Queries scores per soul per metric
- Auto-detect: αν δεν υπάρχουν env vars, uses fallback

**PaperTradingFitness:**
- Reads `paper_portfolio.json`
- Score = 0.3 + (win_rate × 0.4) + (ROI_normalized × 0.3)
- Returns 0-1 fitness score

**SourceRewriter:**
- Regex-based DNA value rewriting in `.nous` source
- Matches `soul Name { ... dna { ... gene_name: VALUE ~ [...] } }`
- Preserves formatting, updates only the value

**GitCommitter:**
- Auto-detects git repo
- Commits with descriptive message after accepted mutations
- Handles `git init` if needed

**TelegramNotifier:**
- Sends 🧬 Evolution Report via Telegram Bot API
- Includes per-soul fitness change, mutation details, accept/reject status

**EvolutionScheduler:**
- Calculates seconds until next 3:00 AM
- Runs as asyncio daemon
- Full cycle: parse → validate → evolve → rewrite → commit → notify

### Priority 4: REPL (`repl.py`) + CLI v1.3.0

**REPL Features:**
- Tab completion for NOUS keywords and commands
- Command history (saved to `~/.nous_history`)
- Multi-line input (brace counting)
- 15 commands: help, load, ast, compile, validate, info, dna, souls, tools, evolve, run, clear, reset, quit
- Context-aware prompt: `nous:GateAlpha>`
- Color-coded output (ANSI)
- Inline NOUS code parsing and validation

**CLI v1.3.0 — 12 Commands:**
```
nous compile <file>              — Compile to Python
nous run <file>                  — Compile and execute
nous validate <file>             — Validate laws
nous ast <file> [--json]         — Print Living AST
nous evolve <file> [--cycles N]  — Run evolution cycles
nous evolve-live <file>          — Live evolution (Langfuse/Telegram)
nous evolve-live <file> --daemon — Evolution daemon (3:00 AM)
nous shell [file]                — Interactive REPL
nous nsp <text>                  — Parse NSP tokens
nous info <file>                 — Program summary
nous bridge <file>               — Noosphere analysis
nous version                     — Show version
```

---

## 6. EARLEY PARSER FIXES — TECHNICAL DEEP DIVE

Ο Earley parser με dynamic lexing δεν ξεχωρίζει πάντα keywords από identifiers. Αυτό είναι fundamental στο πώς δουλεύει ο Earley — δοκιμάζει όλες τις πιθανές tokenizations.

### Πρόβλημα 1: `let tokens = sense gate_alpha_scan()`
**Earley βλέπει:** `sense` ως SENSE token, `tokens` ως NAME → `sense_call` rule matches, αλλά items = [tokens, sense, gate_alpha_scan]
**Fix:** `sense_call()` transformer ανιχνεύει τη θέση του SENSE token. Αν SENSE δεν είναι στη θέση 0, τότε items[0] = bind_name, items[2+] = tool_name + args.

### Πρόβλημα 2: `let kelly = sense calculate_kelly(signal)`
**Earley βλέπει:** `let_stmt` matches first (higher priority), captures `kelly` = NAME, `sense` = expr (NAME). Η `calculate_kelly(signal)` γίνεται orphan `func_call`.
**Fix:** `_merge_keyword_stmts()` σαρώνει: αν `LetNode(value="sense")` ακολουθείται από `func_call`, τα ενώνει σε `LetNode(value=sense_call)`.

### Πρόβλημα 3: `guard rsi < 70` πριν από `speak Signal(...)`
**Earley βλέπει:** `guard` ως NAME, `rsi` ως NAME. Χειρότερα: `70` + `s` (πρώτο γράμμα του `speak`) → tokenized ως `70s` (duration). `peak` = υπόλοιπο `speak`.
**Fix:** `_merge_keyword_stmts()` αναγνωρίζει `"guard" + condition` → `GuardNode`. `_fix_duration_artifacts()` μετατρέπει `"70s"` → `70`. `"peak" + func_call` → `SpeakNode`.

### Πρόβλημα 4: `.where(volume_24h > 50000)`
**Python problem:** `volume_24h` is undefined variable στο generated code.
**Fix:** Codegen αναγνωρίζει `method_call` με method `"where"` + binop arg → εκπέμπει `.filter("volume_24h", ">", 50000)` αντί `.where((volume_24h > 50000))`.

---

## 7. LIVE TESTS ΣΤΟΝ SERVER

### Compilation
```bash
nous compile gate_alpha.nous    # 333 lines Python, 0.32s
nous validate gate_alpha.nous   # PASS, 0 errors, 0 warnings
```

### Full Pipeline Run
```
Scout  → DexScreener scan (7 candidates, 105ms)
       → Volume filter (>50K)
       → RSI check per candidate
       → Speak Signal to channel
Quant  → Listen Scout::Signal
       → Kelly criterion (edge=0.61)
       → Speak Decision(BUY, size=0.125)
Hunter → Listen Quant::Decision
       → Guard action == "BUY"
       → Paper trade executed ($1250, balance $8750)
Monitor → Listen Scout::Signal
        → Telegram notification delivered
```

### Evolution
```
Langfuse connected: langfuse.neurodoc.app
Fitness: 0.3797 (paper trading, reflects -$1.51 PnL)
3 mutations proposed → rolled back (fitness not improved)
Telegram: 🧬 Evolution Report delivered
Daemon: scheduled daily at 03:00
```

### REPL
```
nous shell gate_alpha.nous
nous:GateAlpha> :info
nous:GateAlpha> :dna
nous:GateAlpha> :souls
nous:GateAlpha> :validate
```

---

## 8. NOUS SYNTAX REFERENCE

```nous
# World — execution environment
world GateAlpha {
    law CostCeiling = $0.10 per cycle
    law MaxLatency = 30s
    law NoLiveTrading = true
    heartbeat = 5m
}

# Message — typed inter-soul communication
message Signal {
    pair: string
    score: float
    rsi: float?
    source: SoulRef
}

# Soul — agent = state + behavior + evolution + healing
soul Scout {
    mind: deepseek-r1 @ Tier1
    senses: [gate_alpha_scan, fetch_rsi, ddgs_search]

    memory {
        signals: [Signal] = []
        scan_count: int = 0
    }

    instinct {
        let tokens = sense gate_alpha_scan()
        let filtered = tokens.where(volume_24h > 50000)
        for token in filtered {
            let rsi = sense fetch_rsi(token.pair)
            guard rsi < 70
            speak Signal(pair: token.pair, score: token.composite_score, rsi: rsi, source: self)
        }
        remember scan_count += 1
    }

    dna {
        volume_threshold: 50000 ~ [10000, 200000]
        rsi_ceiling: 70 ~ [60, 80]
        temperature: 0.3 ~ [0.1, 0.9]
    }

    heal {
        on timeout => retry(2, exponential)
        on api_error => sleep 1 cycle
        on hallucination => lower(temperature, 0.1) then retry
    }
}

# Nervous System — DAG
nervous_system {
    Scout -> Quant -> Hunter
    Scout -> Monitor
}

# Evolution — self-mutation
evolution {
    schedule: 3:00 AM
    fitness: langfuse(quality_score)
    mutate Scout.dna {
        strategy: genetic(population: 3, generations: 2)
        survive_if: fitness > parent.fitness
        rollback_if: any_law_violated
    }
}

# Perception — external triggers
perception {
    on telegram("/scan") => wake Scout
    on cron("*/5 * * * *") => wake_all
    on system_error => alert Telegram
}
```

### Bilingual Keywords

| English | Greek | Purpose |
|---------|-------|---------|
| world | κόσμος | Top-level container |
| soul | ψυχή | Agent definition |
| mind | νους | LLM backend |
| sense | αίσθηση | Tool invocation |
| memory | μνήμη | Owned state |
| remember | θυμάμαι | Mutate memory |
| instinct | ένστικτο | Behavior |
| speak | λέω | Emit message |
| listen | ακούω | Receive message |
| heal | θεραπεία | Error recovery |
| law | νόμος | Constitutional constraint |
| guard | φύλακας | Assert condition |
| evolution | εξέλιξη | Self-mutation |
| perception | αντίληψη | External events |

---

## 9. INFRASTRUCTURE

**Server:** Hetzner CCX23, 188.245.245.132
**OS:** Debian 12, Python 3.12
**Dependencies:** lark, pydantic, httpx, duckduckgo_search
**Install:** `/usr/local/bin/nous` shell wrapper
**Dir:** `/opt/aetherlang_agents/nous/`
**Tools:** `/opt/aetherlang_agents/tools/`
**Agents:** `/opt/aetherlang_agents/agents/`

**Env vars (in /opt/aetherlang_agents/.env):**
- `TELEGRAM_BOT_TOKEN` — Noosphere_bot
- `TELEGRAM_CHAT_ID` — 6046304883
- `LANGFUSE_PUBLIC_KEY` — pk-lf-...
- `LANGFUSE_SECRET_KEY` — sk-lf-...
- `LANGFUSE_BASE_URL` — https://langfuse.neurodoc.app
- `OPENROUTER_API_KEY` — for Tier1/Tier2
- `ANTHROPIC_API_KEY` — for Tier0A
- `OPENAI_API_KEY` — for Tier0B

---

## 10. ΓΝΩΣΤΑ ISSUES

1. **Earley parser ambiguity:** Η `_merge_keyword_stmts()` λύνει τα γνωστά cases, αλλά νέα syntax patterns μπορεί να χρειαστούν νέα merge rules. Εναλλακτική: switch σε LALR parser (απαιτεί grammar refactor).

2. **Tool warnings:** 42 παλιά Noosphere tools φαίνονται ως "Failed to load" λόγω relative imports. Δεν επηρεάζουν τη λειτουργία — αφορούν tools που τρέχουν μέσω του παλιού agent_runtime.py.

3. **RSI calculation:** Η fetch_rsi χρησιμοποιεί synthetic price series (DexScreener δεν δίνει OHLCV). Για ακριβέστερο RSI, χρειάζεται ccxt integration.

4. **Paper trading:** Δεν υπολογίζει unrealized PnL. Positions κλείνουν μόνο manually (CLOSE action).

5. **Fitness baseline:** Με 0 trades, fitness = 0.5. Με λίγα losing trades, fitness < 0.5, και mutations δεν γίνονται accepted. Χρειάζεται αρκετό trading history.

---

## 11. ΤΙ ΑΚΟΛΟΥΘΕΙ

### Priority 4 (Remaining): Language Evolution
- [ ] Deploy/topology blocks — grammar rules exist, need codegen
- [ ] LSP (Language Server Protocol) — VS Code syntax highlighting
- [ ] Better error messages — line numbers, suggestions, "did you mean?"

### Priority 5: Documentation & Community
- [ ] GitHub repo: contrario/nous — public release
- [ ] Landing page: nous-lang.dev
- [ ] White paper publication
- [ ] Example programs beyond Gate Alpha
- [ ] Tutorial: "Build your first NOUS agent"

### Priority 6: Production Hardening
- [ ] Suppress tool loading warnings for non-NOUS tools
- [ ] LALR parser migration (eliminate Earley ambiguity)
- [ ] ccxt integration for real OHLCV data
- [ ] Live trading mode (with constitutional guards)
- [ ] Multi-world support (run multiple .nous files)
- [ ] Distributed topology (multi-server execution)

---

*NOUS v1.3.0 — The Living Language*
*15 αρχεία, 12 CLI commands, 9 tools, 4 souls live*
*Hlias Staurou | 11 Απριλίου 2026 | Athens, Greece*
