# Changelog
## [4.8.3] - 2026-04-17

### Fixed

- **Missing dependency**: `pyyaml` was not declared in `pyproject.toml`
  dependencies despite being required by `risk_engine.py` (since v4.5.0).
  Fresh installs from PyPI failed with `ModuleNotFoundError: No module named 'yaml'`
  when importing any governance module.
- `pyyaml>=6.0` is now an explicit core dependency.

### Notes

No functional code changes. v4.8.2 is broken on PyPI for clean installs;
users should install v4.8.3 or higher.

---

## [4.8.2] - 2026-04-17

### Added — Phase G Layer 4.5: prompt-hash recompute on inject_message

When an `inject_message` policy triggers and modifies the outgoing LLM
messages, the `llm.request` event now carries three additional fields:

- `prompt_hash_post_inject`: sha256 of the canonical payload after injection
- `injected_role`: the role (`system` or `user`) that was injected
- `injected_policies`: list of policy names that caused the injection

The original `prompt_hash` (used as the replay match key) is unchanged, so
all existing recorded logs remain playable. The new fields are emitted
**only** when injection actually occurs, preserving byte-identical
codegen output for every template without inject_message policies
(52/52 regression templates verified).

### Tests

- New `test_11_llm_request_event_has_post_inject_hash`
- New `test_12_no_inject_no_rehash_fields`
- New `test_13_post_inject_hash_matches_injected_messages`
- `tests/test_inject_message.py`: 27 -> 39 checks (all green)

### Compliance

This closes the audit gap where the recorded prompt hash did not reflect
the actual content sent to the LLM after governance-driven injection.
Auditors can now verify both what was requested and what was ultimately
transmitted.

---

## [4.8.0] - 2026-04-17

### Added - Phase G Layer 4: Governance Dashboard
- `governance.py`: PolicyInspector, GovernanceLog, GovernanceStats, InterventionRecord
- `GET /v1/governance/policies` - list active policies per world template
- `GET /v1/governance/interventions` - query intervention events from replay logs
- `GET /v1/governance/stats` - aggregated governance statistics
- `nous governance policies <file.nous>` - CLI policy inspector
- `nous governance inspect <log>` - CLI intervention event viewer
- `nous governance stats <log>` - CLI governance stats
- 30 governance dashboard tests (10 test functions, 30 assertions)
- `_signal_to_str()` - human-readable signal rendering from AST



## [4.7.0] - 2026-04-17
### Added - Phase G Governance, Layer 3: Intervention Primitive + Runtime Hook
- **`intervention.py`** - new module with `InterventionEngine`, `InterventionOutcome`, `InterventionError`, `InterventionBlocked`, `InterventionAborted`
  - Synchronous hot-path check with no-op mode when no rules loaded
  - Action priority resolution: `abort_cycle > block > inject_message > intervene > log_only`
  - `inject_message` stubbed to log_only for v4.7.0 (full semantics deferred to Layer 4)
- **`replay_runtime.py`** - `ReplayContext` gains `intervention_engine` param + `set_intervention_engine()` setter
  - Pre-emit hook at 3 sites: `sense.invoke`, `llm.request` (blocks cost before spend), `memory.write`
  - `governance.intervention` audit event emitted on every triggering (record mode only)
  - `block` raises `InterventionBlocked`, `abort_cycle` raises `InterventionAborted`
  - Replay + off modes: zero intervention logic (determinism preserved)
- **`risk_engine.py`** - predicate namespace expansion
  - `event.data` string-identifier keys now exposed as bare names in predicate scope
  - `cost > 0.10` works identically in `.nous` signals and YAML predicates
  - Reserved names (event fields, stats, `value`) take precedence on collision
  - Fully backward compatible - `data.get('cost', 0)` style YAML rules unchanged
- **`codegen.py`** - runtime engine wiring
  - Emits `from intervention import InterventionEngine` + `_INTERVENTION_ENGINE = InterventionEngine(_POLICIES, _POLICY_ACTIONS)` when policies exist
  - Emits `rt.replay_ctx.set_intervention_engine(_INTERVENTION_ENGINE)` in both simple and distributed `build_runtime()` paths
  - **Zero bytes emitted when no policies declared** - 40 regression templates byte-identical
- **`nous_api.py`** - `/v1/chat` maps `InterventionBlocked`/`InterventionAborted` to HTTP 422
  - Structured payload: `action`, `policies`, `score`, `reasons`, `triggering_event_kind`
  - Codes: `CHAT_INTERVENTION_BLOCKED`, `CHAT_INTERVENTION_ABORTED`
- **`tests/test_intervention.py`** - 10/10 E2E
  - All 5 actions exercised (log_only, intervene, inject_message, block, abort_cycle)
  - LLM block verified to prevent cost spend (execute() never runs)
  - Action priority resolution, codegen emission, generated module load
### Stability
- **40 regression templates byte-identical** throughout all 8 patches (54, 54b, 55, 56, 57c, 58, 59, 60)
- All 43 previous tests remain green
- **53 total replay+governance tests** (43 previous + 10 Intervention)
### Governance loop closed
- Layer 1 (RiskEngine, v4.5.0) + Layer 2 (Policy DSL, v4.6.0) + Layer 3 (Runtime enforcement, v4.7.0)

## [4.6.0] - 2026-04-17
### Added — Phase G Governance, Layer 2: Policy DSL
- **Grammar extension** — `policy NAME { ... }` blocks inside `world`
  - Keywords: `policy` | `πολιτική` (POLICY.2 terminal)
  - Clauses: `kind`, `signal`, `window`, `weight`, `action`, `description`
  - Actions: `log_only`, `intervene`, `block`, `inject_message`, `abort_cycle`
  - **Native NOUS expressions** as signals — type-checked at parse time, not runtime strings
- **AST nodes** — `PolicyNode` (Pydantic V2) with `PolicyAction` Literal enum
  - Rejects invalid actions at construction time (compile-time type safety)
  - `WorldNode.policies: list[PolicyNode]` default empty
- **Validator** — `_check_policies()` with 5 error codes
  - PL001 duplicate name, PL002 missing signal, PL003 weight range, PL004 negative window, PL005 empty kind
- **Codegen emission** — `_emit_policy_constants()`
  - Emits `_POLICIES: list[RiskRule] = [...]` + `_POLICY_ACTIONS: dict[str, str]`
  - Imports `risk_engine.RiskRule` only when policies present
  - Reuses `_expr_to_python` for signal → predicate translation (binop, not, compare)
  - **Zero bytes emitted when no policies declared** → 40 regression templates byte-identical
- **RiskRule** — extended with `action: str = "log_only"` field (backward compatible)
  - `from_dict` reads optional `action` from YAML
  - Existing YAML rules continue to work unchanged
- **`tests/test_policy_grammar.py`** — 10/10 E2E
  - Parse, AST typing, defaults, validator positive+negative, codegen emission, zero-output-without-policies, runtime RiskRule instantiation, py_compile

### Stability
- **40 regression templates remain byte-identical** — the critical gate
- All previous tests green: Foundation 7/7, Phase C 10/10, Phase D 6/6, Risk 10/10
- **43 total replay+governance tests** (7 + 10 + 6 + 10 + 10)

### Why 4.6.0 (minor bump)
Layer 2 closes the loop: policies now live in source code as first-class constructs,
compiled into the same `RiskRule` runtime used by Layer 1. Rules written in `.nous`
and rules loaded from YAML merge into a unified governance surface.
Layer 3 (Intervention primitive + runtime hook) follows in 4.7.0.


## [4.5.0] - 2026-04-17
### Added — Phase G Governance, Layer 1: RiskEngine
- **`risk_engine.py`** — runtime risk assessment over replay event logs
  - `RiskRule` (dataclass) — YAML-configurable rule: `kind_filter`, `predicate`, `weight`, `window`, `extract`
  - `RiskAssessment` — per-event score in [0,1] with `triggered_rules` + `reasoning`
  - `RiskReport` — aggregate over a full log (max/mean score, rule hits, per-event detail)
  - `RiskEngine.assess(event)` and `assess_log(path)` public API
  - Sandboxed predicate eval (no `__` names, no builtins) — safe to load untrusted rule YAML
  - Rolling per-(soul, rule) statistics for drift detection
- **`risk_rules.yaml`** — 7 default rules: `high_llm_cost`, `llm_token_burst`, `sense_error`, `memory_write_burst`, `cycle_duration_spike`, `llm_error`, `response_length_anomaly`
- **`nous replay <log> --risk-report`** — new CLI mode
  - `--rules YAML` — load custom ruleset
  - `--json` — machine-parseable output for CI/CD
  - `--verbose` — per-event triggered rows
  - Exit 0 = clean, 5 = triggered, 1 = I/O error
- **`tests/test_risk_engine.py`** — 10/10 E2E: default rules, clean log, each rule fires, custom YAML, sandbox escape blocked, JSON roundtrip

### Stability
- Zero changes to existing code — pure additive layer
- 40 regression templates remain byte-identical
- Phase A 7/7, Phase C 10/10, Phase D 6/6, Risk 10/10 — all green
- 33 total replay+governance tests

### Why 4.5.0 (minor bump)
Phase G (Governance) is a new capability layer, not a patch to Replay. Layer 1 ships the foundation (scoring); Layers 2-4 (grammar `law` blocks, `Intervention` primitive, dashboard) will follow in 4.6.0 / 4.7.0 / 4.8.0.


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
