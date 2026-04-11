# NOUS SESSION 4 — COMPLETE HANDOFF

## Ημερομηνία: 12 Απριλίου 2026
## Engineer: Claude (Staff-Level Principal Language Designer)
## User: Hlias Staurou (Hlia)

---

## ΣΥΝΟΨΗ SESSION 4

Σε αυτό το session ολοκληρώθηκαν 4 από τα 7 priorities: LALR parser migration (90x speedup), ccxt real RSI integration, constitutional trading guards, και multi-world concurrent execution. Όλα verified live στον production server (Hetzner CCX23, 188.245.245.132).

---

## PRIORITY 1: LALR PARSER MIGRATION ✅

### Τι ήταν το πρόβλημα
Ο Earley parser δούλευε αλλά χρειαζόταν εκτεταμένα post-processing workarounds:
- `_merge_keyword_stmts()` — σάρωνε τα statements και έκανε merge keywords (guard, speak, sense) που ο Earley τα έβλεπε ως NAME tokens
- `_fix_duration_artifacts()` — αφαιρούσε artifacts όπου ο Earley ένωνε `70` + `s` (από το επόμενο `speak`)
- Sense call rewriting — ειδικό handling για `let X = sense tool(args)`
- 324ms per parse — αργός για production

### Τι κάναμε
Πλήρης rewrite grammar + parser για LALR compatibility.

**Grammar αλλαγές (nous.lark):**
1. **Keyword priority `.2`** — Όλα τα keyword terminals (LAW, SOUL, SENSE, SPEAK, GUARD, κτλ.) πήραν explicit priority `.2` γιατί ο LALR contextual lexer δεν έδινε αυτόματα προτεραιότητα σε named string terminals vs NAME regex
2. **`message_construct` αφαιρέθηκε από `atom`** — Προκαλούσε ambiguity με `func_call` (και τα δύο `NAME "(" ... ")"`). Τώρα μόνο μέσα σε `speak_stmt`
3. **`inline_if` μετακινήθηκε από `atom` σε `?expr` level** — Εξαλείφει conflict με `if_stmt` σε statement context
4. **`expr_stmt: or_expr`** αντί `statement: | expr` — Αποτρέπει inline_if/if_stmt ambiguity
5. **`route_chain: NAME ("->" NAME)+`** — Αντικαθιστά `route_linear` + `route_chain3`, εξαλείφει shift-reduce conflict
6. **`remember_set` / `remember_add`** — Split γιατί ο anonymous terminal `+=` φιλτράρεται από τον LALR Transformer
7. **`then_block` / `else_block` sub-rules** — Το anonymous `else` token φιλτράρεται, χρειάζονται sub-rules για separation
8. **`DURATION_UNIT.2: "ms" | "s" | "m" | "h" | "d"`** — Priority + "ms" πρώτο για longest match

**Parser αλλαγές (parser.py):**
1. **Keyword terminals → None** — Κάθε keyword terminal (WORLD, SOUL, LAW, κτλ.) επιστρέφει `None` μέσω handler method. Η `_strip()` helper τα αφαιρεί
2. **`string_lit` returns dict** — `{"kind": "string_lit", "value": "..."}` αντί bare string, ώστε ο codegen να ξεχωρίζει `"BUY"` (string) από `BUY` (variable)
3. **`let_sense_stmt` / `let_listen_stmt`** — Ξεχωριστοί grammar rules αντί post-processing merge
4. **Parser caching** — `_PARSER_CACHE` global, grammar compile μόνο μία φορά
5. **Μηδέν workarounds** — Καμία `_merge_keyword_stmts`, καμία `_fix_duration_artifacts`

### Λάθη που βρήκαμε και πώς τα διορθώσαμε

**Λάθος 1: Keyword priority**
- **Σύμπτωμα:** `law CostCeiling = ...` → `Token('NAME', 'law')` αντί `Token('LAW', 'law')`
- **Αιτία:** Lark LALR contextual lexer δεν δίνει αυτόματα priority σε named string terminals vs regex
- **Fix:** `LAW.2: "law" | "νόμος"` — explicit priority σε όλα τα keywords

**Λάθος 2: Keyword tokens στα items**
- **Σύμπτωμα:** `LawNode(name=items[0], expr=items[1])` crash — items[0] ήταν Token('LAW'), όχι name
- **Αιτία:** Named terminals (LAW, WORLD, κτλ.) μένουν στα items, δεν φιλτράρονται αυτόματα
- **Fix:** Handler methods που επιστρέφουν `None` + `_strip()` helper

**Λάθος 3: remember_stmt "+=" invisible**
- **Σύμπτωμα:** `remember scan_count += 1` → op="=" αντί op="+="
- **Αιτία:** Ο anonymous terminal "+=" φιλτράρεται, items ίδια για "=" και "+="
- **Fix:** Split σε `remember_set` / `remember_add` named alternatives

**Λάθος 4: if_stmt else body missing**
- **Σύμπτωμα:** else body χάνεται
- **Αιτία:** "else" anonymous terminal φιλτράρεται, αδύνατο να ξεχωρίσεις then/else
- **Fix:** `then_block` / `else_block` sub-rules

### Benchmark
```
Parse-only (100 iterations, gate_alpha.nous):
  Earley: 324.64ms/parse
  LALR:   3.33ms/parse
  Speedup: 90.6x
```

---

## PRIORITY 2: ccxt REAL OHLCV + RSI-14 ✅

### Τι ήταν το πρόβλημα
Ο παλιός `fetch_rsi.py` χρησιμοποιούσε synthetic data από DexScreener — RSI πάντα 63.64 για κάθε token.

### Τι κάναμε
Νέο `fetch_rsi.py` tool:
1. **ccxt async support** — `ccxt.async_support` για async exchange access
2. **RSI-14 Wilder smoothing** — Σωστός υπολογισμός RSI με Wilder's exponential moving average
3. **Exchange fallback chain** — Δοκιμάζει binance → bybit → gate → kucoin → okx
4. **Pair normalization** — "SOLUSDT" → "SOL/USDT", "SOL/USDC" preserved
5. **Contract address detection** — Hex addresses (0x...) ή Solana base58 (>30 chars) → instant skip
6. **Exotic quote skip** — CBBTC, WETH, WBTC κτλ. → instant skip (δεν υπάρχουν σε CEX)
7. **`execute()` function** — Interface που ψάχνει η runtime

### Λάθη που βρήκαμε και πώς τα διορθώσαμε

**Λάθος 1: Tool has no execute() function**
- **Σύμπτωμα:** `Tool fetch_rsi has no execute() function or class`
- **Αιτία:** Η runtime.ToolRegistry ψάχνει `execute()` — το νέο tool είχε `fetch_rsi()` και `run()`
- **Fix:** Προσθήκη `async def execute(*args, **kwargs)` wrapper

**Λάθος 2: Contract addresses ως trading pairs**
- **Σύμπτωμα:** `0XB30540172F1B37D1.../USDT` → 15s timeout ανά token (5 exchanges × 3s)
- **Αιτία:** DexScreener επιστρέφει contract addresses, normalize τα μετατρέπει σε nonsense pairs
- **Fix:** `_is_contract_address()` — detect hex/base58 → return 50.0 instant

**Λάθος 3: Exotic quote tokens**
- **Σύμπτωμα:** SOL/CBBTC, SOL/WETH → 15s timeout
- **Αιτία:** Wrapped tokens (CBBTC, WETH) δεν υπάρχουν ως quote σε CEX
- **Fix:** `_SKIP_QUOTES` set → instant skip

**Λάθος 4: gate_alpha_scan pair format**
- **Σύμπτωμα:** Pair field = contract address αντί symbol
- **Αιτία:** `"pair": pair.get("pairAddress", "")` στο scan tool
- **Fix:** `"pair": baseToken.symbol + "/" + quoteToken.symbol`

### Live Results
```
fetch_rsi: SOL/USDC RSI=59.86 (64 candles from binance)
fetch_rsi: SOL/USDC RSI=60.67 (64 candles from binance)
fetch_rsi: SOL/USDC RSI=62.21 (64 candles from binance)
```

---

## PRIORITY 4: CONSTITUTIONAL GUARDS ✅

### Τι κάναμε

**Validator (compile-time enforcement):**
1. **C001 — NoLiveTrading enforcement** — Αν `law NoLiveTrading = true`, block souls που χρησιμοποιούν live trade tools (execute_trade, place_order, κτλ.)
2. **C002 — Constitutional count validation** — Count πρέπει >= 1
3. **C003 — Missing MaxPositionSize warning** — Αν υπάρχουν trading souls χωρίς position limit
4. **C004 — Missing MaxDailyLoss warning** — Αν υπάρχουν trading souls χωρίς daily loss limit
5. **`_scan_stmts_for_tools()`** — Recursive scan σε if/for bodies για forbidden tools
6. **`_get_bool_law()` / `_get_currency_law()`** — Helpers για law lookup

**Codegen (runtime enforcement):**
1. **`ConstitutionalGuard` class** — Generated όταν υπάρχουν trade-related laws
2. **`check_trade()`** — Position size check, daily loss circuit breaker, audit logging
3. **`record_pnl()`** — Track daily P&L, trigger circuit breaker αν limit exceeded
4. **`reset_daily()`** — Reset counters (for cron-based daily reset)
5. **`GUARD = ConstitutionalGuard()`** — Module-level instance

### Live Validator Output
```
[WARN] C003 @ world: Trading souls detected but no MaxPositionSize law defined. Add: law MaxPositionSize = $1000
[WARN] C004 @ world: Trading souls detected but no MaxDailyLoss law defined. Add: law MaxDailyLoss = $100
Validation PASS
```

---

## PRIORITY 3: MULTI-WORLD ✅

### Τι κάναμε

**multiworld.py (νέο αρχείο):**
1. **`WorldInstance`** — Loads compiled .nous module via importlib
2. **`SharedChannelBus`** — Publish/subscribe για cross-world communication (prepared, not yet used)
3. **`MultiWorldRunner`** — TaskGroup-based concurrent execution
4. **`run_multi()`** — Entry point: compile → load → run all worlds

**cli.py v1.4.0:**
1. **`nous run file.nous`** — Single world (backwards compatible, subprocess)
2. **`nous run file1.nous file2.nous`** — Multi-world (concurrent, in-process via importlib)
3. **`files` argument** — `nargs="+"` accepts multiple files

### Λάθη που βρήκαμε και πώς τα διορθώσαμε

**Λάθος 1: infra_monitor.nous self-loop**
- **Σύμπτωμα:** `Cycle detected in nervous_system without explicit feedback annotation`
- **Αιτία:** `Watcher -> Watcher` = self-loop, validator blocks it
- **Fix:** Αφαίρεση nervous_system block (single soul δεν χρειάζεται)

**Λάθος 2: Pydantic forward refs σε dynamic import**
- **Σύμπτωμα:** `Signal is not fully defined; you should define Optional, then call Signal.model_rebuild()`
- **Αιτία:** `from __future__ import annotations` κάνει τα annotations strings — Pydantic χρειάζεται explicit rebuild σε dynamic import context
- **Fix:** `model_rebuild()` calls μετά κάθε message class στο codegen

### Live Multi-World Output
```
NOUS Multi-World: 2 worlds
  → gate_alpha.nous
  → infra_monitor.nous

Compiled: gate_alpha.nous → GateAlpha
Compiled: infra_monitor.nous → InfraMonitor
Starting 2 worlds concurrently...

[GateAlpha] Scout: cycle 1 complete (RSI=59.86, trade $131.51)
[GateAlpha] Quant: cycle 1 complete (Kelly edge=0.5536)
[GateAlpha] Hunter: cycle 1 complete
[GateAlpha] Monitor: cycle 1 complete (Telegram ✅)
[InfraMonitor] Watcher: cycle 1 complete
[InfraMonitor] Watcher: cycle 2 complete
```

---

## CODEGEN FIXES (NON-PRIORITY BUGS)

### Bug 1: _sense_* methods missing
- **Σύμπτωμα:** `'Soul_Scout' object has no attribute '_sense_gate_alpha_scan'`
- **Αιτία:** Codegen δεν generated `_sense_*` methods που delegate στο `self._runtime.sense()`
- **Fix:** Codegen generates per-soul `_sense_TOOL` methods + runtime initialization in `run_world()`

### Bug 2: Runtime not initialized
- **Σύμπτωμα:** Tools loaded αλλά souls δεν τα βρίσκουν
- **Αιτία:** `run_world()` δεν initialize runtime, δεν register souls
- **Fix:** `init_runtime()` + `runtime.register_soul()` + `runtime.run()` in generated code

### Bug 3: `self` → Python object instead of name
- **Σύμπτωμα:** `Signal(source=self)` → Pydantic error "Input should be a valid string"
- **Αιτία:** `self` σε .nous = soul name (string), αλλά codegen generated `self` (Python object)
- **Fix:** `_expr_to_python("self")` → `"self.name"`

### Bug 4: `.where()` → ToolResult has no field 'where'
- **Σύμπτωμα:** `tokens.where(volume_24h > 50000)` crash
- **Αιτία:** `ToolResult` has `.filter()` not `.where()`. Codegen δεν μετατρέπει
- **Fix:** Codegen detects method "where" with binop arg → generates `.filter("field", ">", value)`

### Bug 5: `world_config` not defined
- **Σύμπτωμα:** Monitor crash: `name 'world_config' is not defined`
- **Αιτία:** `world.config.telegram_chat` generated `world_config.config.telegram_chat` — undefined
- **Fix:** Generate `WORLD_CONFIG` dict from world config + env vars, `world_ref` → `WORLD_CONFIG.get("key", "")`

### Bug 6: Channels not connected to runtime
- **Σύμπτωμα:** Channels created but not connected to runtime
- **Αιτία:** Generated ChannelRegistry was standalone, not linked to runtime
- **Fix:** `channels = None` at module level, `global channels; channels = runtime.channels` in `run_world()`

---

## ΑΡΧΕΙΑ ΠΟΥ ΑΛΛΑΞΑΝ

| Αρχείο | Τοποθεσία Server | Αλλαγή |
|--------|-------------------|--------|
| `nous.lark` | `/opt/aetherlang_agents/nous/` | LALR grammar, keyword priority .2 |
| `parser.py` | `/opt/aetherlang_agents/nous/` | Clean LALR, zero workarounds |
| `codegen.py` | `/opt/aetherlang_agents/nous/` | Runtime integration, guards, sense methods |
| `validator.py` | `/opt/aetherlang_agents/nous/` | Constitutional law enforcement |
| `cli.py` | `/opt/aetherlang_agents/nous/` | v1.4.0, multi-file support |
| `multiworld.py` | `/opt/aetherlang_agents/nous/` | **NEW** — concurrent world runner |
| `fetch_rsi.py` | `/opt/aetherlang_agents/tools/` | ccxt RSI-14 with exchange fallback |
| `gate_alpha_scan.py` | `/opt/aetherlang_agents/tools/` | Pair format: symbol/quote |
| `infra_monitor.nous` | `/opt/aetherlang_agents/nous/` | **NEW** — test world |

---

## LIVE PIPELINE — ΤΕΛΙΚΟ ΑΠΟΤΕΛΕΣΜΑ

```
nous compile gate_alpha.nous  → 421 lines Python, 0.14s, py_compile PASS

nous run gate_alpha.nous      → Full pipeline:
  Scout  → DexScreener scan (7 candidates, 85ms)
         → Real RSI from Binance (SOL/USDC RSI=60.67, 64 candles)
         → Signals sent
  Quant  → Kelly criterion (edge=0.5468) → Decision(BUY, size=0.125)
  Hunter → Paper trade ($150.30, balance $1052.12)
  Monitor → Telegram notification ✅
  All 4 souls: cycle complete in ~8s

nous run gate_alpha.nous infra_monitor.nous → 2 worlds, 5 souls concurrent ✅
```

---

## ΤΙ ΔΕΝ ΕΧΕΙ ΓΙΝΕΙ ΑΚΟΜΑ — SESSION 5+ PRIORITIES

### Priority 5: White Paper Update
Το `NOUS_WHITE_PAPER_v1.0.docx` υπάρχει αλλά χρειάζεται:
1. Update με Session 3+4 results (full pipeline, 4 souls, LALR, multi-world)
2. LALR benchmark data (90x speedup, 3.3ms/parse)
3. ccxt RSI integration results
4. Constitutional guards documentation
5. Architecture diagrams
6. Multi-world documentation

### Priority 6: Landing Page (nous-lang.dev)
1. Single-page site με syntax examples
2. Live playground (compile .nous στον browser via API)
3. Installation instructions
4. Links: GitHub, white paper, documentation

### Priority 7: GitHub Push
Τα νέα αρχεία δεν είναι ακόμα στο repo (github.com/contrario/nous):
- `nous.lark` (updated)
- `parser.py` (rewritten)
- `codegen.py` (major changes)
- `validator.py` (constitutional guards)
- `cli.py` (v1.4.0)
- `multiworld.py` (new)
- `fetch_rsi.py` (new ccxt version)
- `infra_monitor.nous` (new example)
- Update README, CHANGELOG

### Priority 8: Cross-World Communication
`SharedChannelBus` υπάρχει στο multiworld.py αλλά δεν χρησιμοποιείται ακόμα:
1. Grammar support: `speak @OtherWorld::MessageType` cross-world routing
2. Bus integration σε generated code
3. Shared state management

### Priority 9: Hot Reload
1. `nous watch file.nous` — file watcher, recompile + restart on change
2. `inotifywait` ή `watchdog` integration
3. Graceful restart χωρίς channel loss

### Priority 10: Distributed Topology
1. `topology` block → actually deploy souls to multiple servers via SSH
2. SSH key management
3. Cross-server channels via WebSocket/Redis

### Priority 11: Better REPL
1. `nous shell` → load runtime, allow `run Scout` to execute single soul
2. Tab completion for soul names, tool names
3. Live AST inspection

### Priority 12: VS Code Extension Update
1. Update TextMate grammar for new LALR syntax
2. Update LSP server for new parser
3. Add multi-world support

### Priority 13: Live Trading Completion
1. `law RequireApproval = true` → Telegram confirmation before trade execution
2. Audit log: JSON file with every trade decision + reasoning
3. Kill switch: Telegram command to halt all trading
4. Real exchange integration (Binance Futures, Gate.io)

### Priority 14: Suppress urllib3/chardet Warning
```python
import warnings
warnings.filterwarnings("ignore", message="urllib3.*chardet.*")
```

### Priority 15: Tool Argument Validation
Codegen should validate named args match tool signatures. Currently passes kwargs blindly.

---

## ENVIRONMENT

- **Server:** Hetzner CCX23, 188.245.245.132, Debian 12, Python 3.12
- **Langfuse:** langfuse.neurodoc.app (self-hosted)
- **Telegram:** Noosphere_bot (token: 864...Kv8, chat: 604...883)
- **Git:** github.com/contrario/nous (main branch, needs push)
- **Env vars:** /opt/aetherlang_agents/.env (auto-loaded by CLI wrapper)
- **Tools dir:** /opt/aetherlang_agents/tools/ (19 tools loaded)
- **ccxt:** v4.5.43 installed system-wide

---

## ΤΕΧΝΙΚΕΣ ΣΗΜΕΙΩΣΕΙΣ ΓΙΑ ΝΕΕΣ SESSIONS

### LALR Parser Patterns
- Keyword terminals **ΠΡΕΠΕΙ** να έχουν `.2` priority
- Anonymous terminals (inline strings) φιλτράρονται από Transformer — use named alternatives αν χρειάζεσαι τη value
- `_strip()` helper αφαιρεί None values και Token objects
- Parser cached globally — clear cache αν αλλάξεις grammar

### Codegen Patterns
- `_sense_*` methods delegate σε `self._runtime.sense()`
- `self` → `self.name` always
- `.where(field > val)` → `.filter("field", ">", val)`
- `world.config.X` → `WORLD_CONFIG.get("X", "")`
- `string_lit` dict form: `{"kind": "string_lit", "value": "..."}`
- `model_rebuild()` μετά κάθε Pydantic message class

### Runtime Integration
- `init_runtime()` → creates NousRuntime
- `runtime.register_soul()` → connects soul to runtime
- `runtime.channels` → shared channel registry
- `runtime.sense()` → tool dispatch via ToolRegistry
- Tools need `execute()` function or class with `.execute()` method
