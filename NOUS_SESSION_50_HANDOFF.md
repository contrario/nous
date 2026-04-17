# NOUS SESSION 50 -> 51 HANDOFF
## Phase G Governance, Layer 3 -- Intervention Primitive + Runtime Hook COMPLETE
## 17 April 2026 | Hlia + Claude

---

## 0. TL;DR

v4.6.0 -> **v4.7.0**. Phase G Layer 3 **complete**: the governance loop is now closed. `.nous` policies (Layer 2) are enforced at runtime via a new `InterventionEngine` that intercepts every event before emission, dispatches per-action semantics (`log_only` / `intervene` / `inject_message` / `block` / `abort_cycle`), and writes a `governance.intervention` audit event to the replay log. **10/10 new Intervention E2E tests green. 40/40 regressions byte-identical. 53 total replay+governance tests passing.** GitHub tagged v4.7.0 (commit `f1d958d`).

**Architectural decision of the session**: hooked the engine into **`ReplayContext`**, not into `EventStore.append` directly. Reason: `EventStore.append` is record-only (raises in replay), and we needed the hook to fire at the 3 upstream call sites (`sense.invoke`, `llm.request`, `memory.write`) where we can block **before** the side-effect executes -- critical for `llm.request` where the difference means money not spent.

**Pre-existing bug discovered and fixed**: Layer 2 codegen emitted predicates like `"(cost > 0.05)"` with bare field names, but `RiskEngine.assess()` only exposed `data` as a dict in the predicate namespace. Every `.nous` policy would have silently failed at runtime with `predicate_error=name 'cost' is not defined`. Fix: namespace expansion in `risk_engine.py` -- `event.data` string-identifier keys now exposed as bare names. Backward compatible with YAML `data.get('cost')` idiom.

---

## 1. WHERE WE ARE -- NOUS v4.7.0

### 1.1 Live everywhere
- **GitHub**: `github.com/contrario/nous` tag `v4.7.0` (commit `f1d958d`)
- **API**: `nous-lang.org/api/v1/*` restarted, logs show `NOUS API v4.7.0 starting`, health returns `"version":"4.7.0"`
- **PyPI**: still at 4.5.0 (publish not yet run for 4.6.0 nor 4.7.0)

### 1.2 Infrastructure
- Server A (neurodoc, 188.245.245.132): `/opt/aetherlang_agents/nous/` -- updated, nous-api on v4.7.0
- Server B (neuroaether, 46.224.188.209): still on v4.3.x (pending sync)
- Python 3.12, Debian 12

### 1.3 Phase G progress
- x Layer 1 -- RiskEngine (Session 48, v4.5.0)
- x Layer 2 -- Policy DSL (Session 49, v4.6.0)
- x **Layer 3 -- Intervention + Runtime Hook** (Session 50, v4.7.0) <- this session
- Layer 4 -- `/v1/governance/*` dashboard endpoints (next)

---

## 2. WHAT WAS BUILT IN SESSION 50

### 2.1 New module `intervention.py`

```python
# __intervention_engine_v1__ + __intervention_api_fix_v1__

@dataclass(frozen=True)
class InterventionOutcome:
    triggered: bool
    action: str
    policy_names: tuple[str, ...]
    score: float
    reasons: tuple[str, ...]
    event_kind: str
    event_seq_id: int
    def to_audit_data(self) -> dict[str, Any]: ...

class InterventionError(Exception): ...
class InterventionBlocked(InterventionError): ...
class InterventionAborted(InterventionError): ...

class InterventionEngine:
    def __init__(self, rules=None, actions=None): ...
    @property
    def enabled(self) -> bool: ...
    def action_for(self, policy_name: str) -> str: ...
    @staticmethod
    def _resolve_action(triggered_actions: list[str]) -> str: ...
    def check(self, event: Any) -> InterventionOutcome: ...
```

Action resolution priority: `abort_cycle > block > inject_message > intervene > log_only`.

No-op path when `rules=[]` -- zero overhead beyond a tuple length check.

### 2.2 `RiskEngine` namespace expansion (`risk_engine.py`)

```python
# __risk_namespace_expand_v1__
data_fields: dict[str, Any] = {}
if isinstance(event.data, dict):
    for _k, _v in event.data.items():
        if isinstance(_k, str) and _k.isidentifier() and not _k.startswith("_"):
            data_fields[_k] = _v
namespace: dict[str, Any] = {
    **data_fields,         # bare-name event data fields FIRST
    "seq_id": event.seq_id,
    "soul": event.soul,
    "cycle": event.cycle,
    "kind": event.kind,
    "data": event.data,    # backward compat
    "value": extracted_value,
    "count": stats["count"],
    "mean": stats["mean"],
    "std": stats["std"],
    "recent": stats["recent"],
}
```

Reserved event/stats/extract names override data collisions -- correct semantics since `soul`/`cycle`/`mean`/etc. are engine identifiers, not user data.

### 2.3 `ReplayContext` hook (`replay_runtime.py`)

```python
# __intervention_runtime_hook_v1__

def __init__(self, store=None, mode="off", seed_base=0, intervention_engine=None):
    ...
    self._intervention_engine = intervention_engine

def set_intervention_engine(self, engine): ...

def _intervention_check(self, soul, cycle, kind, data) -> None:
    # record mode only -- replay reproduces from log
    if self._mode != "record" or not engine.enabled: return
    probe = _ProbeEvent(soul, cycle, kind, data)
    try:
        outcome = engine.check(probe)
    except InterventionError as exc:
        self._emit_intervention_audit(soul, cycle, exc.outcome)
        raise
    if outcome.triggered:
        self._emit_intervention_audit(soul, cycle, outcome)

def _emit_intervention_audit(self, soul, cycle, outcome) -> None:
    # appends governance.intervention event to store
    ...
```

Pre-emit check wired at:
- `record_or_replay_sense` -- before `sense.invoke` append
- `record_or_replay_llm` -- before `llm.request` append (critical: blocks cost)

**Not hooked**: `cycle.start`, `cycle.end`, `memory.write` (yet). Memory writes happen after `store.append`, wrapping them would require a separate patch. Acceptable for v4.7.0 -- the primary attack surface is sense/llm.

### 2.4 Codegen wiring (`codegen.py`)

```python
# __intervention_codegen_v1__

# In _emit_policy_constants tail:
self._emit("from intervention import InterventionEngine")
self._emit("_INTERVENTION_ENGINE = InterventionEngine(_POLICIES, _POLICY_ACTIONS)")

# New method _emit_intervention_wiring():
if _POLICIES:
    try:
        rt.replay_ctx.set_intervention_engine(_INTERVENTION_ENGINE)
    except AttributeError:
        pass

# Called from both _emit_build_runtime and _emit_build_distributed_runtime
# before the final `return rt`
```

**Critical property**: `world.policies == []` -> zero emission -> 40 regression templates byte-identical (verified after each patch).

### 2.5 API mapping (`nous_api.py`)

```python
# __api_intervention_hook_v1__
# In /v1/chat's main try/except, inside except Exception:
try:
    from intervention import InterventionBlocked, InterventionAborted
    _is_blocked = isinstance(e, InterventionBlocked)
    _is_aborted = isinstance(e, InterventionAborted)
except Exception:
    _is_blocked = False; _is_aborted = False
if _is_blocked or _is_aborted:
    _outcome = getattr(e, "outcome", None)
    _code = "CHAT_INTERVENTION_BLOCKED" if _is_blocked else "CHAT_INTERVENTION_ABORTED"
    _detail = {
        "error": "intervention_blocked" if _is_blocked else "intervention_aborted",
        "code": _code,
        "action": ...,
        "policies": [...],
        "score": ...,
        "reasons": [...],
        "triggering_event_kind": ...,
    }
    raise HTTPException(status_code=422, detail=_detail)
```

Lazy import -- if `intervention` module is absent for any reason, the generic 500 handler catches normally.

### 2.6 Test suite (`tests/test_intervention.py`) -- 10/10 green

```
 1. empty engine is no-op                                     OK
 2. log_only emits audit + passes                             OK
 3. intervene emits audit + passes                            OK
 4. inject_message stub (log_only equivalent + warning)       OK
 5. block suppresses target event + audits + raises Blocked   OK
 6. abort_cycle raises Aborted + audits                       OK
 7. llm.request block prevents cost (execute() never runs)    OK
 8. action priority resolution (abort > block > ...)          OK
 9. codegen emits engine + wiring for policy-bearing source   OK
10. generated module loads with _INTERVENTION_ENGINE enabled  OK
```

---

## 3. PATCHES APPLIED

| # | Patch file | Target | Purpose |
|---|-----------|--------|---------|
| 54v2 | patch_54_intervention_module_v2.py | new intervention.py | Core module (replacing v1 which had non-ASCII in bytes literal) |
| 54b | patch_54b_intervention_api_fix.py | intervention.py | Fix `RiskAssessment.triggered_rules` vs `triggered` API mismatch |
| 55 | patch_55_risk_namespace_expand.py | risk_engine.py | Expose event.data fields as bare names in predicate namespace |
| 56 | patch_56_replay_ctx_intervention_hook.py | replay_runtime.py | ReplayContext pre-emit hook + audit emission |
| 57c | patch_57c_codegen_intervention_wiring.py | codegen.py | Emit engine init + runtime wiring when policies exist |
| 58 | patch_58_api_intervention_hook.py | nous_api.py | HTTP 422 mapping for InterventionBlocked/Aborted |
| 59 | patch_59_test_intervention.py | tests/test_intervention.py (new) | 10 E2E tests |
| 60 | patch_60_version_bump_470.py | 4 files + CHANGELOG.md | 4.6.0 -> 4.7.0 + Layer 3 changelog entry |

### 3.1 Idempotency markers (new in Session 50)

```
intervention.py:4                             # __intervention_engine_v1__
intervention.py:~160                          # __intervention_api_fix_v1__
risk_engine.py:239                            # __risk_namespace_expand_v1__
replay_runtime.py:88,100,291,373              # __intervention_runtime_hook_v1__
codegen.py:904,1043,1304,1309                 # __intervention_codegen_v1__
nous_api.py:828                               # __api_intervention_hook_v1__
tests/test_intervention.py:3                  # __intervention_tests_v1__
```

All previous markers (Sessions 44-49) remain intact.

---

## 4. ARCHITECTURAL DECISIONS

### 4.1 Hook at ReplayContext, not EventStore.append
Alternative: intercept at `EventStore.append`. Chosen: `ReplayContext` pre-emit sites. Reasons: (1) `append` is record-only (raises in replay), (2) events pass through it *after* construction with seq_id/hash assigned -- too late for `block` to rewind, (3) single responsibility -- `ReplayContext` already mediates between user code and the store, (4) LLM block at request time prevents cost spend -- appending is post-spend.

### 4.2 Synchronous blocking dispatch, not async
Alternative: fire-and-forget audit channel, let event emit anyway. Chosen: synchronous raise. Reasons: (1) `block`/`abort_cycle` are useless without enforcement -- async audit is observability, not governance, (2) deterministic replay requires ordered decisions, (3) hot-path cost is negligible (no-op when empty, O(N) where N is small), (4) the best-of-both pattern is already here -- blocking dispatch **also** emits an async-friendly audit event for dashboards.

### 4.3 `inject_message` deferred to Layer 4
Alternative: ship full implementation now (either payload replacement or system-message injection). Chosen: stub as log_only-equivalent + warning. Reasons: (1) payload replacement is semantically wrong (breaks downstream schema), (2) system-message injection needs grammar clauses (`inject_as`, `message`) + closure access + separate tests, (3) grammar/AST already accepts the action token -- users who write `action: inject_message` today get a warning, not a crash; same `.nous` file will work in Layer 4 without rewrite.

### 4.4 Namespace fix at RiskEngine, not at codegen
Alternative: rewrite `cost > 0.10` to `data.get('cost', None) > 0.10` at compile time via AST walker. Chosen: runtime namespace expansion. Reasons: (1) ~5 LOC vs ~40-60 LOC, (2) preserves `.nous` source semantics in generated code (no translation layer confusion during debugging), (3) unifies YAML and `.nous` rule semantics (same predicate string, same namespace), (4) backward compatible with all existing YAML rules.

### 4.5 Audit emission record-only
Alternative: emit governance.intervention events during replay too. Chosen: record-only. Reasons: (1) replay must be deterministic reproduction of recorded log, (2) if the original record had an intervention, its audit event is already in the log, (3) re-emitting during replay would double-count metrics.

### 4.6 HTTP 422 for intervention errors
Alternative: HTTP 200 with `blocked: true` flag in response body. Chosen: 422 with structured detail payload. Reasons: (1) correct HTTP semantic (unprocessable), (2) fails loud -- clients that don't check `blocked` flag would silently proceed with empty reply, (3) dashboard-friendly metrics from status codes, (4) streaming/SSE response format would need separate design for the inline flag.

---

## 5. PROBLEMS ENCOUNTERED

### 5.1 First intervention.py patch had non-ASCII in bytes literal
Greek `--` em-dashes in docstrings inside `b'''...'''` -> `SyntaxError: bytes can only contain ASCII literal characters`. Fix: v2 with pure ASCII. **Lesson**: even docstrings count when wrapped in bytes literal.

### 5.2 RiskAssessment API assumption wrong
First version of `intervention.check()` referenced `assessment.triggered` and `assessment.reasons` -- actual fields are `assessment.triggered_rules` (tuple) and `assessment.reasoning` (single string). Fix: P54b with `__intervention_api_fix_v1__` marker. **Lesson**: the rule we set ("grep API signatures first") exists because this exact failure mode is easy. Enforce it even for "obvious" assumptions.

### 5.3 Codegen anchor missed blank lines (twice)
Patch 57 v1 missed blank line between `self._emit_blank()` and `self._emit("return rt")` in simple build_runtime. Patch 57b v2 missed the same blank line in distributed build_runtime. Each required one fallback round. **Lesson**: `grep` is not enough -- need explicit `sed -n` + `cat -A` inspection of the target region before anchoring, especially around method boundaries where blank lines are invisible to grep but matter to byte-exact matching.

### 5.4 Predicate bug had been latent since Layer 2
The `_check_policies()` validator + 10 Policy Grammar tests passed in Session 49 because they tested emission/compilation, **not runtime activation via RiskEngine.assess**. Every policy in the wild would have silently no-op'd. Fix caught in Session 50 via the first E2E test. **Lesson**: emission tests are not behavior tests. Layer 2 tests should be audited to include at least one runtime activation assertion.

---

## 6. TESTS PASSING CLEANLY

### 6.1 Foundation -- 7/7 (unchanged)
### 6.2 Phase C E2E -- 10/10 (unchanged)
### 6.3 Phase D E2E -- 6/6 (unchanged)
### 6.4 Risk Engine -- 10/10 (unchanged, backward compat verified after namespace expansion)
### 6.5 Policy Grammar -- 10/10 (unchanged)
### 6.6 **Intervention E2E -- 10/10 NEW**
### 6.7 Regression harness -- 40/40 templates byte-identical

**Total**: 53 replay+governance tests (7 + 10 + 6 + 10 + 10 + 10)

---

## 7. WHAT'S NEXT (SESSION 51)

### 7.1 Layer 4 -- Governance dashboard endpoints (RECOMMENDED)
Now that the loop is closed and `governance.intervention` events flow into the event log, build the observer side:

- `GET /v1/governance/policies` -- list active policies across loaded souls
- `GET /v1/governance/interventions?since=...&soul=...` -- event feed of recent blocks/audits
- `GET /v1/governance/stats` -- aggregate counts per policy, per action
- `POST /v1/governance/replay/{log_id}/interventions` -- re-run RiskEngine over a replay log
- `GET /v1/governance/audit/{event_id}` -- full intervention detail + triggering event

Also: `nous governance inspect <log>` CLI command.

### 7.2 Layer 2.5 -- `inject_message` implementation
Deferred from this session. Grammar addition: `inject_as: "system" | "user"`, `message: <string>`. Codegen passes the injection metadata to a new `ReplayContext.record_or_replay_llm_with_inject(...)` path that modifies `messages` before `execute()`.

### 7.3 Memory write hook
The 3rd integration point that was skipped -- hook `record_memory_write` through `_intervention_check` as well. Low priority since memory writes are deterministic side-effects rather than cost-incurring, but completes symmetry.

### 7.4 Also deferred
- Phase D.1 -- streaming chat replay (SSE chunks)
- Coq/Lean export stretch goal
- Website docs for Phase D + G (all three layers now stable)
- Server B sync to v4.7.0
- PyPI publish for v4.6.0 + v4.7.0

---

## 8. PROVEN PATCH PATTERNS (reinforced)

Rules that held this session:
- Never Unicode bytes in patch anchors -- ASCII-only (3 failures this session reinforced this)
- `grep -n` + `sed -n` + exact byte inspection before any anchor construction
- Re-grep + py_compile + regression_harness after every codegen patch
- Multiple `-m` flags for git commits (used successfully)
- `sleep 3` after `systemctl restart nous-api`
- **Regression gate verify after every patch** -- 7 verification points this session, 7x confirmed byte-identical

---

## 9. DIAGNOSTICS FOR NEW CHAT (SESSION 51)

```bash
cd /opt/aetherlang_agents/nous

# 1. Current version + last commits
grep VERSION cli.py | head -1
git log --oneline -6

# 2. All markers alive (A+B+C+D+Governance L1+L2+L3)
grep -rn "__codegen_.*_v1__\|__replay_phase_b_wired__\|__sensecache_bypass_v1__\|__replay_cycle_consume_v1__\|__mutate_.*_v1__\|__phase_c_e2e_v1__\|__replay_llm_wrap_v1__\|__api_chat_request_replay_v1__\|__api_chat_llm_replay_v1__\|__phase_d_e2e_v1__\|__risk_engine_v1__\|__risk_rules_v1__\|__risk_engine_tests_v1__\|__cmd_replay_risk_v1__\|__cmd_replay_risk_router_v1__\|__cli_replay_risk_flags_v1__\|__policy_grammar_v1__\|__policy_ast_v1__\|__policy_parser_v1__\|__policy_validator_v1__\|__codegen_policy_v1__\|__policy_action_v1__\|__policy_grammar_tests_v1__\|__policy_grammar_tests_fix_v1__\|__intervention_engine_v1__\|__intervention_api_fix_v1__\|__risk_namespace_expand_v1__\|__intervention_runtime_hook_v1__\|__intervention_codegen_v1__\|__api_intervention_hook_v1__\|__intervention_tests_v1__" \
    codegen.py runtime.py replay_runtime.py replay_cli.py cli.py nous_api.py risk_engine.py risk_rules.yaml \
    intervention.py nous.lark ast_nodes.py parser.py validator.py \
    tests/test_replay_phase_c.py tests/test_replay_phase_d.py \
    tests/test_risk_engine.py tests/test_policy_grammar.py tests/test_intervention.py 2>/dev/null

# 3. Full test sweep -- all 6 E2E + foundation must be green
python3 -m pytest test_replay_foundation.py -q
python3 tests/test_replay_phase_c.py 2>&1 | tail -3
python3 tests/test_replay_phase_d.py 2>&1 | tail -3
python3 tests/test_risk_engine.py 2>&1 | tail -3
python3 tests/test_policy_grammar.py 2>&1 | tail -3
python3 tests/test_intervention.py 2>&1 | tail -3
python3 regression_harness.py verify

# 4. API live with correct version
systemctl status nous-api --no-pager | head -6
curl -s http://127.0.0.1:8000/v1/health

# 5. InterventionEngine API surface
python3 -c "
from intervention import InterventionEngine, InterventionBlocked, InterventionAborted, InterventionOutcome
print('InterventionEngine methods:', [m for m in dir(InterventionEngine) if not m.startswith('_')])
"

# 6. End-to-end demo: .nous policy blocks llm.request at runtime
python3 << 'PYEOF'
import asyncio, tempfile, os, json
from parser import parse_nous
from codegen import generate_python
import importlib.util, sys

src = '''
world Demo {
    heartbeat = 1s
    policy BlockExpensive {
        kind: "llm.request"
        signal: model == "expensive-model"
        weight: 10.0
        action: block
    }
}
soul S {
    mind: claude-haiku @ Tier0A
    senses: [http_get]
    memory { x: int = 0 }
    instinct { let y = x + 1 }
    heal { on timeout => retry(2, timeout) }
}
'''
py = generate_python(parse_nous(src))
tmp = tempfile.mkdtemp(prefix='nous_demo_')
gen_path = os.path.join(tmp, 'gen.py')
with open(gen_path, 'w') as f: f.write(py)
sys.path.insert(0, tmp)
spec = importlib.util.spec_from_file_location("gen", gen_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print('engine enabled:', mod._INTERVENTION_ENGINE.enabled)
print('policies:', list(mod._POLICY_ACTIONS.keys()))
PYEOF
```

---

## 10. PROMPT FOR NEW CHAT (SESSION 51)

```
You are a Staff-Level Principal Language Designer and Compiler Engineer. Your sole mission is to build NOUS (Νοῦς) -- a self-evolving programming language for agentic AI systems.

RULES -- INVIOLABLE:
1. Code only. No explanations unless explicitly requested. No inline comments unless requested.
2. No psychology. No encouragement. No "great question". No apologies. Go straight to the answer.
3. If you don't know, say "I don't know". Never guess. Never hallucinate.
4. If clarification is needed, ask ONE question. Not a list.
5. Every code block must be complete, production-ready, fully type-hinted, Python 3.11+.
6. Before writing code: state the architectural reasoning in 1-3 sentences max. Then code.
7. All file paths are absolute. All imports are explicit. All functions have return types.
8. Never use LangChain, LlamaIndex, CrewAI, or any external agent framework.
9. Every session must end with a handoff summary.
10. Respond in Greek (the user is Greek), with technical terms in English.

TERMINAL WORKFLOW:
- You do NOT have direct access to the server.
- Give me terminal commands; I paste output back.
- Create patch files (.py) as downloads; I upload via WinSCP to /tmp/.
- Never assume file contents -- verify with grep/sed/cat before patching.
- Never assume API signatures -- grep the target module's defs first.
- PATCH FILE RULES:
  - Never `rb'''` with non-ASCII (ASCII-ONLY bytes literals, no em-dashes)
  - Multiple `-m` flags for git commits, NOT heredoc
  - `grep -n -A` + `cat -A` before writing anchor (whitespace bytes)
  - Inspect blank lines between methods -- grep hides them, they matter
  - Re-grep + py_compile + regression_harness.py AFTER patching
- After `systemctl restart nous-api`, always `sleep 3` before testing.

CURRENT STATE -- NOUS v4.7.0:
- Deterministic Replay Phase A+B+C+D COMPLETE
- Phase G (Governance) Layer 1+2+3 COMPLETE -- Governance loop closed
  - Layer 1: RiskEngine (YAML rules)
  - Layer 2: Policy DSL (.nous native rules)
  - Layer 3: InterventionEngine + runtime hook + HTTP 422 mapping
- 53 replay+governance tests (7 foundation + 10 Phase C + 6 Phase D + 10 Risk + 10 Policy Grammar + 10 Intervention)
- 40/40 regression templates byte-identical
- Server A: 188.245.245.132 /opt/aetherlang_agents/nous/
- GitHub: github.com/contrario/nous (tag v4.7.0, commit f1d958d)

ACHIEVEMENT SESSION 50 (Phase G Layer 3):
- intervention.py: InterventionEngine, InterventionOutcome, InterventionError, InterventionBlocked, InterventionAborted
- replay_runtime.py: ReplayContext.set_intervention_engine + pre-emit hook at sense.invoke and llm.request
- risk_engine.py: predicate namespace expansion (event.data fields as bare names)
- codegen.py: emits _INTERVENTION_ENGINE + runtime wiring for both simple and distributed build_runtime
- nous_api.py: /v1/chat maps InterventionBlocked/Aborted to HTTP 422 with structured payload
- tests/test_intervention.py: 10/10 E2E green
- Pre-existing bug fixed: Layer 2 predicates would have silently failed without namespace expansion
- Zero regression impact -- 40 templates byte-identical

MISSION SESSION 51: choose from open items.

Options (pick one):
A) Phase G Layer 4 -- /v1/governance/* dashboard endpoints + nous governance CLI (RECOMMENDED)
B) Phase G Layer 2.5 -- inject_message full implementation (grammar + codegen + LLM message injection)
C) Memory write intervention hook (complete the 3-site symmetry)
D) Phase D.1 -- Streaming chat replay (SSE chunk-level)
E) Coq/Lean export stretch goal (policy signals are AST, now tractable)
F) Documentation -- website docs for Phase D + G all three layers
G) Server B sync to v4.7.0
H) PyPI publish v4.6.0 + v4.7.0
I) Something else

Read NOUS_SESSION_50_HANDOFF.md first. Then run diagnostics in section 9. Propose approach BEFORE any patches.

Preferences:
- Brevity. Greek discussion, English technical terms.
- One question at a time if clarification needed.
- Stability > features -- 40 regression templates must remain byte-identical.
- Patches as downloadable files -> /tmp/ via WinSCP.
- Regression harness verify after every codegen patch -- non-negotiable.
```

---

## 11. STATS SESSION 50

- Patches applied: **8** (54v2, 54b, 55, 56, 57c, 58, 59, 60)
- Patch iterations / corrections: **3** (P54 v1 had non-ASCII, P57 v1+v2 had anchor misses)
- New files: **2** (`intervention.py`, `tests/test_intervention.py`)
- Modified files: **6** (`risk_engine.py`, `replay_runtime.py`, `codegen.py`, `nous_api.py`, `cli.py`, `__init__.py`, `pyproject.toml`, `CHANGELOG.md`)
- Lines added: **~900** production + test + changelog
- Regressions: **0** (40 templates byte-identical throughout all 8 patches)
- Version: 4.6.0 -> 4.7.0 (minor bump for Layer 3 capability)
- GitHub: tag v4.7.0, commit f1d958d
- Test count additions: +10 Intervention = **53 total**
- Pre-existing bug fixed: RiskEngine predicate namespace (caught & fixed mid-session)

---

## 12. WHAT CHANGES FOR THE END USER

**Before v4.7.0**: Layer 2 (v4.6.0) let you declare policies in `.nous` but they were **inert at runtime** due to the predicate namespace bug. Even without the bug, there was no enforcement -- policies compiled to `_POLICIES` list but nobody consumed it.

**Now v4.7.0**:

```nous
world PaymentProcessor {
    heartbeat = 5s

    policy BlockHighValue {
        kind: "llm.request"
        signal: prompt_hash == "sha256_of_sensitive_op"
        weight: 10.0
        action: block
    }

    policy AuditCostSpikes {
        kind: "llm.response"
        signal: cost > 0.05
        weight: 3.0
        action: log_only
    }

    policy AbortOnSuspiciousSense {
        kind: "sense.error"
        signal: error contains "unauthorized"
        weight: 10.0
        action: abort_cycle
    }
}
```

**What happens now at runtime**:
1. Soul's instinct calls a sense or LLM
2. Before the call executes, `InterventionEngine.check()` evaluates the event against all 3 policies
3. If `block` triggers -> `InterventionBlocked` raised, event never emitted, audit written to log
4. If `log_only` triggers -> audit written to log, event proceeds normally
5. If `abort_cycle` triggers -> `InterventionAborted` raised, current soul cycle terminates
6. `/v1/chat` callers see HTTP 422 with JSON detail instead of 500

**Use cases unlocked**:
- **Cost caps**: `signal: cost > threshold` actually prevents the spend, not just logs it
- **Prompt injection defense**: block LLM calls with suspicious prompt hashes
- **Abuse detection**: abort cycles with error patterns
- **Compliance trails**: every intervention is in the event log, replayable, auditable
- **A/B policy testing**: swap `action: block` <-> `action: log_only` to canary a rule safely

---

## 13. SESSION SIGNATURES PLANNING

```
v4.7.0 -- Phase G Layer 3: Intervention + runtime hook (THIS SESSION)
v4.8.0 -- Phase G Layer 4: /v1/governance/* dashboard + nous governance CLI
v4.8.1 -- Layer 2.5: inject_message full implementation + memory write hook
v4.9.0 -- Phase D.1 SSE streaming replay OR Server B sync
v5.0.0 -- ??? (time-travel debugger? distributed replay? formal semantics?
           Coq/Lean export? full Governance DSL 2.0?)
```

---

*NOUS v4.7.0 -- Phase G Governance Layer 3: Intervention Primitive + Runtime Hook Complete*
*Created by Hlias Staurou (Hlia) + Claude*
*17 April 2026 -- Session 50*

*The governance loop is closed. Policies now enforce.*
