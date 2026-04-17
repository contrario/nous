# Changelog

## [4.4.3] - 2026-04-17
### Added
- **Phase D — LLM Replay in API** — chat endpoint now supports deterministic LLM replay
- **`ReplayContext.record_or_replay_llm`** — coroutine wrap for any async LLM call
  - Events: `llm.request`, `llm.response`, `llm.error`
  - Match key: `sha256(provider | model | canonical(messages) | temperature)[:16]`
  - Prompt hash mismatch raises `ReplayDivergence`
  - Preserves cost, tokens_in, tokens_out, tier, elapsed_ms in recorded response
- **`ChatRequest`** extended with three optional fields: `replay_mode` (off|record|replay), `replay_log`, `replay_seed_base`
- **`tests/test_replay_phase_d.py`** — 6-step E2E harness (OFF passthrough, record roundtrip, replay hit, prompt-hash divergence, error record+replay, seed determinism)

### Changed
- `/v1/chat` handler wraps the tier-call loop under `ReplayContext` when `replay_mode != "off"`; default behavior unchanged

### Stability
- 40 regression templates remain byte-identical
- Phase A foundation: 7/7, Phase C E2E: 10/10, Phase D E2E: 6/6 — all green


## [1.4.0] - 2026-04-12

### Added
- **LALR parser** — 90.6x faster than Earley (3.3ms vs 324ms per parse)
- **Multi-world execution** — `nous run a.nous b.nous` runs worlds concurrently via asyncio.TaskGroup
- **multiworld.py** — WorldInstance, SharedChannelBus, MultiWorldRunner
- **Constitutional guards** — C001 (NoLiveTrading enforcement), C003 (MaxPositionSize warning), C004 (MaxDailyLoss warning)
- **ConstitutionalGuard class** in codegen — position check, daily loss circuit breaker, audit log
- **ccxt RSI-14** — Real OHLCV from Binance/Bybit/Gate/KuCoin/OKX with Wilder smoothing
- **Exchange fallback chain** — 5 exchanges, contract address detection, exotic quote skip
- **`_sense_*` methods** — Per-soul tool delegation to `self._runtime.sense()`
- **`WORLD_CONFIG` dict** — World config + env vars accessible in generated code
- **`model_rebuild()`** — After every Pydantic message class in codegen
- **infra_monitor.nous** — Example infrastructure monitoring world

### Changed
- **nous.lark** — Keyword priority `.2`, `remember_set`/`remember_add` split, `then_block`/`else_block` sub-rules
- **parser.py** — Zero workarounds, `_strip()` helper, `string_lit` returns `{"kind": "string_lit", "value": "..."}`
- **codegen.py** — `self` → `self.name`, `.where()` → `.filter()`, runtime integration in `run_world()`
- **validator.py** — Recursive tool scanning in if/for bodies, `_get_bool_law()`/`_get_currency_law()` helpers
- **cli.py** — v1.4.0, `nargs="+"` for multi-file support
- **gate_alpha_scan.py** — Pair format: `symbol/quote` instead of contract address
- **fetch_rsi.py** — Full rewrite with ccxt async

### Fixed
- `self` in .nous generating Python object instead of soul name string
- `.where(field > val)` crash — ToolResult has `.filter()` not `.where()`
- `world.config.X` generating undefined `world_config` variable
- Channels not connected to runtime
- Pydantic forward refs crash in dynamic import (model_rebuild fix)

## [1.1.0] - 2026-04-11

### Added
- Initial grammar, parser, AST nodes, validator, codegen
- CLI with compile/run/validate/evolve/nsp/info/bridge commands
- NSP protocol (70% token savings)
- Aevolver DNA mutation engine
- Migration tool (106 agents from YAML/TOML)
- VS Code extension
- Gate Alpha example (4 souls: Scout, Quant, Hunter, Monitor)

## [1.0.0] - 2026-04-10

### Added
- Project inception
- Grammar design (Lark EBNF)
- Core AST node definitions
