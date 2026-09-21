# One price source (arc B) -- design

Status: BUILD-ELIGIBLE-DEFERRED. Designed S361 (2026-09-18). No code.
Ships after 5.80.2. Every fact below was read on Server A at HEAD 23caa13
in S361 unless marked UNMEASURED. Re-measure before building; recon does
not stay fresh.

## 1. Problem statement

NOUS attaches dollar figures to models on several surfaces. Only one of
them reads the governed table (pricing/defaults.toml through pricing.py,
with verified_date, staleness refusal, lifecycle, aliases, and a
canonical digest written into manifests). The others read ungoverned
literals keyed by tier label or by a dispatch id. Two of those literals
decide something: a verifier error, and an enforced API budget.

Forcing facts:

- `nous verify` fails or passes a program on VR001, an error-level
  finding priced from verifier.py TIER_COSTS by tier label
  (_verify_resource_bounds, TIER_COSTS read at verifier.py:269; the
  result's pass test is `len(self.errors) == 0`, verifier.py:111).
  Nobody verified those prices; no date travels with them.
- In the same wheel, the name deepseek-v4-flash has two prices. The
  governed table resolves it to deepseek-flash, 0.30/1.20 per 1M (S361,
  commit 23caa13). nous_runtime.py RUNTIME_TIERS prices the same id at
  0.00014/0.00028 per 1k, which is 0.14/0.28 per 1M. RuntimeTier
  computes cost from those fields (nous_runtime.py:199, 311); that
  BudgetGuard (nous_runtime.py:49) enforces on that cost is the S360
  reading, not re-read in S361.
- CLI and API verify differ. The API passes pricing to verify_program
  (nous_api_server.py:286) and gets VR003, a Z3/Farkas bound over the
  declared pricing. The CLI calls verify_program(program) with no
  pricing at four sites (cli.py:873, 1032, 1077, 1382), so VR003 never
  runs from the CLI.
- verifier.py and runtime.py fall back to Tier1 on an unknown tier
  (`TIER_COSTS.get(tier, TIER_COSTS["Tier1"])`, verifier.py:269,
  runtime.py:86, 99). That is a silent guess, against axiom 5 (refuse
  over guess). The other three tier tables: UNMEASURED.

## 2. Measured inventory

Price literals in shipped modules (all in pyproject py-modules; 143
modules total):

| Table | Keyed by | Consumer | Effect |
|---|---|---|---|
| pricing/defaults.toml via pricing.py | model id | smt_emit.py:537 (--smt), verifier VR003 (API only), `nous prices` | proof input; governed |
| verifier.py:45 TIER_COSTS | tier label | _verify_resource_bounds (VR001 error), _estimate_cascade_cost, _verify_mitosis, _verify_dream | verdict |
| runtime.py:26 TIER_COSTS | tier label | CostTracker.charge, CostTracker.pre_check | see below |
| profiler.py:19 TIER_COSTS | tier label | profiler, dashboard (S360 reading) | display |
| cost_oracle.py:22 TIER_COSTS | tier label | cost command (S360 reading) | display |
| behavioral_diff.py:26 TIER_COSTS | tier label | diff cost deltas (S360 reading) | display |
| nous_runtime.py:332 RUNTIME_TIERS | dispatch id | RuntimeTier cost (199, 311); BudgetGuard, /v1 chat cost fields, router is_free (S360 reading) | enforced limit (S360 reading) |

Not in the wheel: noesis_oracle.py:212 TIERS (model id). Not a price
table: nous-vscode/server/nous_lsp.py:60 TIERS (tier names only).

The five tier-label tables carry identical numbers for Tier0A..Tier3
(per 1k: 0.00025/0.00125, 0.0005/0.0025, 0.003/0.015, 0.005/0.025,
0.015/0.075). runtime.py, cost_oracle.py and behavioral_diff.py add
Groq, Together, Fireworks and Cerebras with identical numbers. They
agree on numbers and disagree on meaning: profiler labels Tier3
"Opus-class"; cost_oracle labels Tier3 "Local (Ollama)" at the same
15/75 per 1M, and Tier2 "Free tier (Gemini)" at 5/25 per 1M.

RUNTIME_TIERS entries: five OpenRouter models at 0.0 (four with a
":free" suffix; openrouter/elephant-alpha without one), DeepSeek
`deepseek-v4-flash` at 0.14/0.28 per 1M, Claude
`claude-3-haiku-20240307` at 0.25/1.25 per 1M.

## 3. The runtime spend guard in generated programs

Measured:

- codegen emits `NousRuntime(world_name=..., heartbeat_seconds=...,
  cost_ceiling=COST_CEILING)` (codegen.py:739-745). NousRuntime takes no
  model, tier table or pricing (runtime.py:433-441).
- Each generated soul carries `self.model = "<declared model>"`
  (codegen.py:342) and SoulRunner receives `tier=` (codegen.py:795,
  1033).
- CostTracker.charge() has no caller outside a root-level script
  (test_runtime_v2.py:78, 85). No production module calls it.
- The only production call is `pre_check(self.name, 500, 200,
  self._tier)` (runtime.py:404): fixed token estimates at the tier
  price, compared with `_spent + est <= ceiling`.

Consequence: `_spent` stays 0 in production, CircuitBreakerTripped is
never raised by production code, and pre_check is a constant per-soul
comparison decided at build time. The generated program does not count
spend.

UNMEASURED: whether any shipped doc, blog post, CHANGELOG line or
website copy describes this as a breaker that stops spend. If one does,
that is an overclaim already shipped (Constitution Article IV) and is
corrected before any other phase.

## 4. The envelope gap (S353 OPEN)

- The --smt bound prices each soul's declared tokens.input and
  tokens.output (smt_emit.py:537-556, formula in _per_call_cost_smt).
- Dispatch caps output with hardcoded max_tokens: 300 at nous_runtime
  (157, 164, 232, 240), immune_engine (179, 182) and noesis_oracle (133,
  142); 200 at dream_engine (385, 398). LLM endpoints also appear in
  natural_lang.py, noesis_gemini_oracle.py and
  scripts/capture_phala_receipt.py (the last has no max_tokens line);
  whether any of these is a soul-runtime path is UNMEASURED.
- verifier VR001 uses its own constants: EST_TOKENS_PER_INSTINCT_BASE
  300, EST_TOKENS_PER_SENSE 500, EST_TOKENS_OUTPUT 200 (verifier.py:53-55).
- runtime pre_check uses 500/200.

Four token assumptions for one soul. The Z3 bound is a valid statement
over the declared envelope. Nothing at dispatch makes a call honour
that envelope: a soul declaring output below 300 can bill up to 300
output tokens, reasoning included (S353 measured that DeepSeek
reasoning tokens bill as output and count toward max_tokens; that
measurement is not pinned).

## 5. Reasons this should never exist (written first)

R1. Tier labels are a knob users write (`@ Tier1`). Pricing by model
    turns an unknown model from a Tier1 estimate into a refusal. More
    programs stop at verify.
R2. profiler, cost_oracle and behavioral_diff print estimates. Routing
    them through pricing.py changes display numbers and gains no
    evidence.
R3. The one proof NOUS makes about cost (--smt) already prices by
    model through the governed table. Everything else is estimation,
    and the honest boundary already permits a labelled estimate to be
    wrong.
R4. Passing the model into the generated runtime changes generated
    Python for every template. The regression harness is byte-identity,
    so this is a large release that re-baselines every template, for a
    guard that today never fires.
R5. Wiring observed spend into CostTracker.charge would make a
    generated program stop itself on spend. That moves NOUS from
    monitor toward guard, against the stated stance.
R6. RUNTIME_TIERS prices the operator's own /v1 chat cascade, not user
    programs. Its numbers are an operator concern.

## 6. Case for building (after section 5)

- VR001 is a verdict, not a display (answers R2 and R3 for the
  verifier): an ungoverned price decides pass or fail.
- The same model id carries two prices in one wheel (answers R6 in
  part): the S359 surface-disagreement class, reopened across surfaces.
- CLI and API verify return different finding sets for the same
  program.
- The Tier1 fallback is a silent guess in at least two modules.
- R4 is real but bounded: phases 1, 2 and 4 below change no generated
  bytes. Only phase 3 touches codegen.
- R5 is answered by choosing, not by default: phase 3 either wires
  observed usage as monitoring evidence (recorded, never raising) or
  removes the breaker wording. It does not add enforcement.

## 7. Claim class and honest boundary

No new claim class. This is an extension (Article VII): every surface
that prints or decides on a dollar figure derives it from the one table
whose digest travels in manifests.

After the arc:

- proves: unchanged. Z3/Farkas cost bounds over the declared envelope
  and the declared (pinned, dated) pricing.
- evidences: that every verdict and every budget figure used the same
  table the manifest names (by pricing_sha256).
- does NOT: guarantee a provider bills at the table's rate, honours
  max_tokens, or counts reasoning tokens as documented. Those remain
  evidenced by pinned first-party reads and by traces, not proven.
- does NOT: make a generated program a spend guard (see R5).

## 8. Design

D1. One source. Every consumer resolves `soul.mind.model` (or a
    dispatch id) through PricingTable.resolve, so aliases, lifecycle
    and staleness apply everywhere. Tier labels keep routing meaning
    only and stop carrying prices.
D2. Refuse on unpriceable. A model the table cannot resolve is a typed
    refusal before any network call and before any verdict. No Tier1
    fallback.
D3. Free is data. Free models become table entries with
    pricing_model = "free", each backed by a pinned first-party read,
    so "is free" has one source. An id that cannot be pinned is not
    free; it is unpriceable (D2).
D4. One verify. The CLI passes the shipped (or user-supplied) pricing
    to verify_program, so CLI and API run VR001 and VR003 alike.
D5. One envelope. Dispatch sends max_tokens equal to the soul's
    declared tokens.output, so the call honours the envelope the bound
    assumes. VR001 and pre_check read the declared tokens instead of
    their own constants.
D6. Structural gate. A test fails the build if any module other than
    pricing.py defines a per-token price literal (input_per_1k,
    output_per_1k, cost_per_1k_in, cost_per_1k_out).

## 9. Phases (narrow first)

P0 Recon, no code:
  - claims audit for "circuit breaker", "cost ceiling", "budget" across
    docs/, website/, README.md, CHANGELOG.md (section 3);
  - what `_noesis_engine` is (codegen.py:561-563), which module it
    lives in, whether that module ships, and what it prices with;
  - provider usage fields at each dispatch site (does the response
    carry token counts that could feed monitoring);
  - first-party pins for each RUNTIME_TIERS model: the four ":free"
    OpenRouter ids, openrouter/elephant-alpha, claude-3-haiku-20240307
    (retirement per repo CHANGELOG, unpinned);
  - whether every soul declares tokens (D5 needs a value).
P1 Dispatch prices (no generated bytes change): RUNTIME_TIERS cost
   fields come from pricing.py by model id; free entries per D3.
   Red-first test: every RUNTIME_TIERS id resolves in the shipped table
   and its cost fields equal the table's. Whether the DeepSeek dispatch
   id moves from deepseek-v4-flash to deepseek-flash is a separate,
   pinned decision (the provider still accepts both).
P2 Verdict (no generated bytes change): VR001 priced by model through
   pricing.py; CLI passes pricing (D4). Red-first test: the same
   program yields the same finding set from CLI and API.
P3 Generated runtime (generated bytes change): codegen passes the
   declared model to SoulRunner; pre_check prices by model; unknown ->
   refusal at build_runtime. Decide charge(): wire observed usage as
   recorded evidence, or delete the breaker wording. Template
   re-baseline is its own reviewed step with a release note.
P4 Delete the copies: profiler, cost_oracle and behavioral_diff read
   pricing.py; remove the five TIER_COSTS literals; add the D6 gate.
P5 Envelope: dispatch max_tokens = declared tokens.output (D5); close
   the S353 OPEN comment in defaults.toml.

Each phase is one release-sized unit. Nothing from P3 onward starts
before P1 and P2 have shipped.

## 10. Kill criteria (testable)

K1. If P0 finds no enforced or verdict-bearing use beyond VR001 and
    BudgetGuard, the arc shrinks to P1 + P2 + D6, and P3/P4 are
    dropped.
K2. If a dispatch id cannot be pinned first-party, it leaves the
    cascade rather than entering the table unpinned. If that empties
    the free cascade, P1 stops and the gap is disclosed.
K3. If provider responses at a dispatch site carry no token usage,
    charge() cannot be fed observed spend there; P3 then removes the
    breaker wording instead of wiring estimates.
K4. If the P0 claims audit finds shipped copy describing the breaker
    as stopping spend, that copy is corrected in the next release,
    ahead of every phase here.

## 11. Opportunity cost

Displaced by: the 5.80.2 release (deadline 2026-10-06, carries the
deepseek-v4-flash alias to PyPI). Displaces: other outstanding items
(tiered-pricing schema, snapshot/alias canonicalisation, the undated
entry rule under --smt). P0 and P1 are cheap and close the two-prices
defect; P3 is the expensive phase and is gated by K1.

## 12. Generalization path

Narrow: one surface at a time, P1 first because it closes the only
measured two-prices-for-one-id defect without touching generated code.
General last: D6, the structural gate that keeps a second price source
from reappearing, lands only after every consumer reads pricing.py.

## 13. Prior art and patent landscape

No new claim class; internal extension of a shipped primitive. No
external prior-art search was run for this arc. Closest internal
precedent: S359/S360 routing of --smt and `nous prices age` through
pricing.py. Patent landscape: UNKNOWN; not searched, no claim class at
stake.

<!-- __s362_p0_findings_v1__ -->
## 14. P0 findings (S362)

Recon only, no code. Basis: HEAD 785180f, read from a clone of origin at
785180f492e08ac05395fd56fc8468019d793f8a (three file sha256 values equal
Server A's and Server A's tree was clean, so tracked bytes are
identical); the published 5.80.2 wheel 08807185... (165 entries) and
sdist 1fc98f9f... (525 entries); Server A reads at 2026-09-18T23:07:34Z,
printed to stdout and not stored. A read marked "chat-side" was made
from the chat, not from Server A, and is not a pin.

### 14.1 Claims audit (the section 3 UNMEASURED item)

Surfaces: README.md, CHANGELOG.md, ROADMAP.md, docs/*.md,
website/**/*.html, ide.html, nous-vscode/snippets.json. Pattern:
breaker|budget|spend limit|cost ceiling|circuit, plus every cost_cap
line. website/docs/index.html excluded (corrected in S361, bound by
tests/test_s361_runtime_copy.py). All 98 pattern lines read. Not
audited: CLI help strings, .py docstrings.

No new copy describes a breaker that stops spend. Found instead:

| id | surface | claim | measured against |
|---|---|---|---|
| C1 | README.md:22 | Z3 proves no execution path can ever exceed the cost_cap | 14.3 dream reproducer; the bound holds over the declared envelope only |
| C2 | README.md:40 | proves before execution that total cost cannot exceed the cap | same |
| C3 | website/blog/index.html:2546 | spend above EUR 0.50 per cycle: "Z3 proved it cannot" | same; cost_cap bounds a total over max_ticks, not a cycle |
| C4 | website/blog/index.html:2331, 2390, 2605 | "we proved we will not exceed"; the bound "matches the alarm"; every path stays under the cap | same |
| C5 | docs/COST_VERIFICATION_GUIDE.md:13-15 | prove the agent will not exceed a declared cost ceiling | same; the proven object is cost_cap, not the cost law |
| C6 | website/index.html:875, website/coverage.html:107 | proves the cost ceiling | smt_emit reads no cost law (14.6) |
| C7 | website/blog/index.html:3221 | clones formally verified against the cost ceiling | VMI001 is a warning-level estimate; the runtime gate is VR001, an estimate |
| C8 | website/blog/index.html:3427-3433 | cost overrun statically verified not to occur (VR001-VR002) | VR001 estimates from undated tier constants; VR002 is a warning |
| C9 | docs/SKILL_EXPORT.md:222 | law form and cost_cap form semantically equivalent at runtime | false (14.6 reproducer) |
| C10 | website/examples/index.html:413 | heal rule `on budget_exceeded` | no module raises budget_exceeded (low) |

Not flagged: website/index.html:857 and website/coverage.html:79
(qualified "in the proven bound"), docs/SKILL_MD_SIDECAR.md:31,
README.md:287, the CHANGELOG [5.80.1] runtime-spend-limit line
(corrected by [5.80.2]), root ide.html (not served, not in wheel or
sdist).

### 14.2 `_noesis_engine`

- codegen emits `from noesis_engine import NoesisEngine` and a
  module-level `_noesis_engine = NoesisEngine()` when the program has a
  top-level `noesis { }` block (codegen.py:163-164, 249-263); `resonate`
  compiles to `_noesis_engine.think(...)` (codegen.py:561-563).
- noesis_engine.py is tracked and ships in neither the wheel nor the
  sdist. It imports nine `noesis_*_patch` modules at module level;
  .gitignore:18 excludes them. Server A holds ten such files, untracked,
  none with an HTTP API endpoint literal.
- Reproducer (5.80.2 wheel, clean venv): a program with `noesis {}` and
  `resonate` validates and compiles; importing the generated module
  raises ModuleNotFoundError: noesis_engine.
- Pricing: none in tracked code. OracleBridge(call_fn=None).consult
  returns None; noesis_engine.py has 0 price, cost, max_tokens or httpx
  tokens. No tracked .nous uses a noesis block or resonate.
- Arc B consequence: none. The import defect is 14.10 O1.

### 14.3 Dispatch sites and usage

| site | ships | reached from | max_tokens | model | reads usage |
|---|---|---|---|---|---|
| generated soul | yes | every generated program | none | none; self.model is set, never used | no call |
| nous_runtime call | yes | /v1 chat, webhook, classifier; `nous run --mode live` | 300 | RUNTIME_TIERS cascade | yes; cost = usage x RUNTIME_TIERS |
| nous_runtime stream_call | yes | /v1 chat_stream | 300 | cascade | parses usage; the request sets no stream_options.include_usage |
| dream_engine _call_dream_llm | yes | programs with dream_system | 200 | TIER_CONFIGS host and dream model; fallback deepseek-v4-flash, mistral-small-latest | no |
| immune_engine _default_llm_caller | yes | programs with immune_system | 300 | deepseek-v4-flash, mistral-small-latest, claude-3-haiku-20240307 | no |
| natural_lang _call_llm_local | yes | natural-language CLI | 4096 | claude-sonnet-4-20250514 | no |
| noesis_oracle, noesis_gemini_oracle | no | none | 300, 1024 | n/a | yes, no |

- `nous run` defaults to dry-run, which makes no call. With `--mode live`
  it calls NousRuntime.think, which walks RUNTIME_TIERS whatever the soul
  declares; the declared model is kept as model_hint only
  (nous_runtime.py:479-487).
- The live trace records soul, tick 0 and tokens, not the answering
  model (nous_runtime.py:492-498, trace_recorder.py:213-225).
  conformance prices each event at the declared model's governed rate
  (conformance.py:106-127, 571-575), so realized_total is the declared
  rate times tokens from whichever cascade model answered.
- /v1 chat (nous_api_server.py:1419), chat_stream (1647) and webhook
  (2086) call RUNTIME_TIERS directly; nous_api_server.py has 0
  references to BudgetGuard, can_spend or think. BudgetGuard gates
  NousRuntime.think only.
- Dream reproducer: cost_cap 0.50 USD, max_ticks 4, one soul with tokens
  and a dream_system. `nous verify --smt`: PROVEN, 1 soul x 4 ticks. The
  compiled program wires DreamEngine. smt_emit.py has 0 dream, immune or
  mitosis references, so engine calls are outside the bound.
- Provider responses (chat-side, not pins): DeepSeek's chat completion
  reference (api-docs.deepseek.com/api/create-chat-completion/)
  documents a non-stream usage object (prompt_tokens, completion_tokens,
  total_tokens, prompt_cache_hit_tokens, prompt_cache_miss_tokens, and a
  reasoning-token detail). OpenRouter's models guide states the response
  usage field carries input and output token counts. Mistral and the
  other dream tier hosts: UNMEASURED. The Server A pins 5cbf7f81,
  d928c166 and 31902010 contain 0 occurrences of these field names.
- BudgetGuard file on Server A (runtime_budget.json, root:root 0644,
  mtime 2026-05-30): last record dated 2026-04-14, spend 0.000051. Save
  errors are swallowed, so whether the writer can still write is
  UNMEASURED.

### 14.4 RUNTIME_TIERS first-party status (nous_runtime.py:332-398)

OpenRouter single-model endpoint GET /api/v1/model/{id}, read on
Server A at 2026-09-18T23:07:34Z:

| id | code price per 1M | http | body sha256 | status |
|---|---|---|---|---|
| nousresearch/hermes-3-llama-3.1-405b:free | 0/0 | 404 | 99186f73887203cac00f688dbe53d9c78210a52f2ffa3c3f2848b40f692b35a3 | not in catalog |
| nvidia/nemotron-3-super-120b-a12b:free | 0/0 | 200 | 539c4a1d3a575f2c10c271461a4626e6b22793e3601f25a773bc39f9cfb2c6ae | prompt 0, completion 0, expiration null |
| openrouter/elephant-alpha | 0/0 | 404 | d61383f4e8cba15a5499c0c61499f1c6a697ca21b24f8f0e421eff27c22eb58f | not in catalog |
| openai/gpt-oss-120b:free | 0/0 | 404 | d22ae74b9fa7f42d40b088edbfb78df43cd6c6ba3f2b3cce767a200b1c868a40 | not in catalog |
| google/gemma-4-31b-it:free | 0/0 | 200 | a357caa3d7b5233abc39de760c4b1b265aee0c2794211c634b962ed5d0b9b159 | prompt 0, completion 0, expiration null |

- deepseek-v4-flash (0.14/0.28 in code): pinned (5cbf7f81, 31902010);
  billed at the Flash price, which the governed table resolves to
  0.30/1.20.
- claude-3-haiku-20240307 (0.25/1.25 in code): Anthropic model
  deprecations page, Server A, same instant, http 200, 427584 bytes,
  sha256 72defeab1fdfb09f299084d3c09f58e18222e5432586ca195092e8842356ec97:
  Retired, deprecated 2026-02-19, retired 2026-04-20, replacement
  claude-haiku-4-5-20251001. immune_engine.py:169 dispatches the same id.

None of these reads was stored. P1 stores the pins.

### 14.5 Declared tokens

- 56 tracked .nous: 48 parse, 8 fail with UnexpectedToken
  (cross_world_command, customer_service, noesis_alpha,
  noosphere_migrated, research_pipeline, stdlib/logger/main,
  stdlib/watcher/main, topology_test). The 48 hold 88 souls; 15 declare
  tokens.
- Shipped templates (12): 24 souls, 9 with tokens, all 9 in cost_cap
  templates. smt_emit refuses a soul without tokens
  (smt_emit.py:308-313), so D5 has a value exactly where a --smt bound
  exists.
- The shipped templates split in two. content_pipeline,
  customer_service, market_monitor and trading_floor declare a cost law
  and no tokens; the last three carry dream_system or immune_system.
  cost_cap_basic, cost_cap_emit_demo, cost_cap_with_souls,
  quorum_gated_demo and sequence_law_demo declare cost_cap and no cost
  law.

### 14.6 world.cost_cap and the cost law

Two unrelated values.

- `cost_cap: <amount> USD|EUR` (world body) is read only by smt_emit
  (smt_emit.py:276-280, 339, 489-490, 524-525), which feeds --smt, VR003
  (API only), the dossier and manifest cost_cap_usd. It bounds a total
  over max_ticks. codegen never reads it: a world with only
  `cost_cap: 0.50 USD` compiles to COST_CEILING = 0.1 (the default) and
  the generated file carries neither cost_cap nor 0.5.
- `law <name> = $<amount> per cycle` is read by codegen for COST_CEILING
  (codegen.py:41, 143-144), by VR001, VR002, VMI001 and VDR002
  (verifier.py:178, 228-229), by the runtime mitosis gate
  (mitosis_engine.py:313-331), by the AST runner (logged only) and by
  skill_export. smt_emit.py has 0 LawCost references.
- skill_export writes the first cost law of any period into nous.yaml
  cost_cap (skill_export.py:162-170, 254-296); dossier-spec translates
  it into world.cost_cap with max_ticks = sum of tool max_calls
  (skill_md.py:312-333), and Z3 bounds the total. A per-cycle amount
  becomes a total cap: stricter, so the bound stays sound, but it is
  labelled per cycle.
- Four selection rules for the cost law: codegen and verifier take the
  last per-cycle law, nous_ast_runner.py:53-57 the first per-cycle law,
  skill_export the first law of any period.
- The rule that no copy ties cost_ceiling to the Z3 bound stands. C3, C5,
  C6 and C9 already do.

### 14.7 Corrections to sections 2-4

- Section 2, nous_runtime row: BudgetGuard does not gate /v1 chat,
  chat_stream or webhook (14.3).
- Section 3: pre_check is constant per soul, and it enforces. A listener
  soul skips its instinct when the tier estimate exceeds COST_CEILING
  (runtime.py:402-407). Measured: CostTracker(ceiling=0.01).pre_check
  with 500/200 tokens is False for Tier3; an unknown tier falls back to
  Tier1 and is True.
- Section 4: generated souls make no LLM call. max_tokens 300 at
  nous_runtime caps `nous run --mode live` and /v1, not generated
  programs. The endpoint list missed api.mistral.ai (dream_engine,
  immune_engine) and the dream TIER_CONFIGS hosts (OpenAI, Gemini, Groq,
  Together, Fireworks, Cerebras, local Ollama).

### 14.8 Kill criteria

- K1 not fired. Beyond VR001 at verify time and BudgetGuard, ungoverned
  tier prices decide three more things: runtime pre_check (listener
  souls skip), VR001 re-run at runtime to admit mitosis clones
  (mitosis_engine.py:256-257, 324-331), and is_free routing
  (nous_api_server.py:1341-1343, NousRuntime.think). P3 and P4 stay.
- K2 fired for four ids. hermes-3-llama-3.1-405b:free,
  openrouter/elephant-alpha and openai/gpt-oss-120b:free are absent from
  the OpenRouter catalog; claude-3-haiku-20240307 is retired. They leave
  the cascade. The free cascade does not empty (nemotron and gemma :free
  remain at 0/0), so P1 does not stop.
- K3 not fired for DeepSeek, the first provider at both engine sites
  (documented usage object). Open for Mistral and the dream tier hosts.
  Plain souls make no call, so charge() has nothing to meter outside
  DreamEngine and ImmuneEngine. Per provider: no usage, no metering, no
  estimate.
- K4 not fired as written: no breaker copy beyond S361. C1-C9 are the
  same class (Constitution Article IV) and are corrected in the next
  release ahead of P1, under section 3's rule.

### 14.9 Implications for the phases (decided at each phase)

- Next release, first unit: C1-C9 corrected, red first, as in S361.
- P1: RUNTIME_TIERS drops the four K2 ids; nemotron and gemma :free
  enter the table as pricing_model = "free" with stored pins. The
  engines' hardcoded dispatch ids (deepseek-v4-flash,
  mistral-small-latest, claude-3-haiku-20240307) carry no price and fall
  outside D6; mistral-small-latest has no table entry and no pin.
- P3: charge() wiring, if chosen, covers two sites (DreamEngine,
  ImmuneEngine).
- D1 and D5 gain a site. `nous run --mode live` dispatches the cascade,
  not the declared mind, and its trace carries no model id, so a
  conformance realized_total can price one model's tokens at another
  model's rate. Either live dispatch honours mind and tokens.output, or
  the trace records the answering model and conformance refuses a
  mismatch.
- D5: 73 of 88 tracked souls declare no tokens; D5 needs a rule for
  them (refuse at dispatch, or a labelled default).

### 14.10 Found outside arc B

- O1 A `noesis {}` program compiles from the wheel and fails at import
  (14.2).
- O2 `nous verify --smt` on an unpriced model prints a raw KeyError
  traceback (pricing.py:192) instead of a typed refusal.
- O3 `nous verify --smt` returned PROVEN and signed a manifest for a
  program that `nous compile` rejects (DR001, trigger_idle_sec 1): the
  --smt path does not run the validator.
- O4 Four cost-law selection rules (14.6).
- O5 BudgetGuard persists to a hardcoded operator path
  (/opt/aetherlang_agents/nous/runtime_budget.json) in a shipped module
  and swallows save errors.
- O6 Eight tracked .nous files do not parse (14.5).
- O7 Anthropic's deprecations page lists claude-haiku-4-5-20251001 as
  Active, retirement not sooner than 2026-10-15. Recorded only:
  FG-S360-I forbids writing alias lifecycle from a snapshot row.

<!-- __s362_claims_sweep_v1__ -->
### 14.11 Claim-class sweep (S362, before the correction)

14.1 matched a fixed word list. A sweep for the claim itself (the cost
bound stated as spend, or an estimate called verified), over the same
surfaces plus website/docs/index.html, found eight more sites:
website/blog/index.html:832, 1401 and 3258, website/coverage.html:74,
website/index.html:396 and 430, docs/ANNEX_IV_MAPPING.md:178 and
website/docs/index.html:895. They are corrected with C1-C9 and bound
by tests/test_s362_claims_copy.py. Left as written: design documents
(dated records), CLI transcripts of the PROVEN line (there
`total_cost` is the declared-envelope total), and sentences whose
subject is the declared total rather than a run
(website/index.html:857, website/coverage.html:79,
website/blog/index.html:1247 and 2631). C10 is deferred (low).

<!-- __s363_p1_decisions_v1__ -->
## 15. P1 decisions (S363, written before the code)

Basis: HEAD 1979eff, Server A tree clean. Files read from a clone of
origin whose sha256 values equal Server A's: pricing.py e9021eb9...,
nous_runtime.py 35580bdb..., nous_api_server.py 08d1adea...,
nous_ast_runner.py 5e3ae532..., nous_api.py 8a8187ab..., run_shas.py
89a22aca.... Reads and pins below were taken on Server A.

### 15.1 D3 today

pricing.py holds a free entry without a schema change: PricingModel
includes "free", the validator requires `provider` and accepts zero or
omitted prices, and the shipped table already carries `local-ollama`.
`staleness_status` returns ok for every free entry before it reads
`verified_date` (pricing.py:391), and `nous prices age` does the same
(cli_prices.py:235). A free entry's `verified_date` therefore records
when the read was taken and starts no clock. Unchanged in P1 (15.6).

### 15.2 RUNTIME_TIERS consumers

| site | reads |
|---|---|
| nous_runtime RuntimeTier.call, stream_call | cost = reported tokens x tier price |
| nous_runtime RuntimeTier.is_free | free status |
| nous_runtime NousRuntime.think | the cascade; skips paid tiers when BudgetGuard is low |
| nous_api_server _classify_soul (1341) | free tiers only |
| nous_api_server chat (1501), chat_stream (1724), webhook (2146) | the cascade |
| nous_ast_runner (31, module level) | NousRuntime; reached from `nous run`, /v1/run with emit_trace, eight test modules |

No test referenced RUNTIME_TIERS or the per-1k fields before S363, and
no generated code reads them. `uvicorn nous_api:app` serves
nous_api_server.app through the re-export in nous_api.py.

### 15.3 Where a refusal fires

- Build: tests/test_s363_runtime_tiers_pricing.py fails if a
  RUNTIME_TIERS id does not resolve in the shipped table, resolves
  through an alias, carries removed_after, deprecated_after or per_hour
  billing, or if a tier's cost fields or free status differ from the
  table's.
- Dispatch: RuntimeTier.call and stream_call resolve the tier's model
  before any network client is built. Not in the table gives
  "unpriceable: ...", a removed entry "removed: ...", per_hour billing
  "per_hour: ...". The refusal is a failed tier result, so the cascade
  moves on. Staleness is `staleness_status(under_smt=False)`: one
  warning per entry per process, no refusal. The 90-day refusal stays
  with --smt, which bounds declared tokens; dispatch prices the tokens
  a provider reported.
- Import: nothing. nous_api_server imports nous_runtime inside four
  request handlers, so an import-time refusal would not stop nous-api
  from starting (the S363 opener's prior is false). It would fail every
  /v1 chat, chat_stream, webhook and classifier request, `nous run`
  including dry-run, and collection of eight test modules, and a
  date-driven cause would fail the suite on a calendar date with no
  code change.
- Table: `load_pricing()` with no path, the loader run_shas and the API
  use, so dispatch prices and a trace's pricing_sha256 name the same
  table. Cached per process: a table change needs a nous-api restart
  (FG-S361-H). On Server A (2026-09-19) nous-api runs as root with cwd
  /opt/aetherlang_agents/nous and neither nous_prices.toml nor
  ~/.config/nous/prices.toml exists, so it resolves the shipped table.
  Server B was not measured when this was written. Measured later in
  S363, after the 5.81.0 sync (2026-09-19T11:13Z): nous-api runs as
  root with cwd /opt/neuroaether/nous, neither file exists, and the
  table resolves to canonical 1f0a3ede. Server B runs two uvicorn
  workers; each caches its own table, and one restart covers both
  (FG-S363-H). <!-- __s364_doc_b_measured_v1__ -->
- `is_free` is the resolved entry's pricing_model == "free". A tier the
  table refuses is neither free nor dispatched.

### 15.4 Cascade after P1

| tier | dispatch id | table entry | read |
|---|---|---|---|
| Nemotron-120B | nvidia/nemotron-3-super-120b-a12b:free | free | /root/openrouter_nemotron_free_s363.json 539c4a1d3a575f2c10c271461a4626e6b22793e3601f25a773bc39f9cfb2c6ae |
| Gemma4-31B | google/gemma-4-31b-it:free | free | /root/openrouter_gemma_free_s363.json a357caa3d7b5233abc39de760c4b1b265aee0c2794211c634b962ed5d0b9b159 |
| DeepSeek | deepseek-flash | per_token 0.30/1.20 per 1M | /root/deepseek_docs_s360.html 5cbf7f81..., /root/deepseek_pricing_s361.html 31902010... |

Left the cascade (K2), each read stored on Server A at
2026-09-19T00:08:07Z:

| id | read | sha256 |
|---|---|---|
| nousresearch/hermes-3-llama-3.1-405b:free | 404 | 99186f73887203cac00f688dbe53d9c78210a52f2ffa3c3f2848b40f692b35a3 |
| openrouter/elephant-alpha | 404 | d61383f4e8cba15a5499c0c61499f1c6a697ca21b24f8f0e421eff27c22eb58f |
| openai/gpt-oss-120b:free | 404 | d22ae74b9fa7f42d40b088edbfb78df43cd6c6ba3f2b3cce767a200b1c868a40 |
| claude-3-haiku-20240307 | Anthropic deprecations page: retired 2026-04-20 | 010edb1466a16b3f652c3fc6fe53af6562a6cb2a8c57988ba0bbbbaa4da6fe69 |

The five stored OpenRouter bodies are byte-identical to the S362 reads
(2026-09-18T23:07:34Z) and the S363 R2 reads (2026-09-19T00:01:07Z).
Each removed id already failed at dispatch, so no working tier was
lost.

### 15.5 DeepSeek dispatch id

RUNTIME_TIERS dispatches `deepseek-flash`. Both stored DeepSeek pages
(5cbf7f81, 31902010) say to use deepseek-flash as the model name; the
legacy names are still accepted, their models are retired, and their
requests are served and billed as V4.1 Flash. The updates page
(8ab3cf3f) says the legacy names are temporarily routed to V4.1 Flash
and states no end date. The price does not change with the move:
deepseek-v4-flash is an alias of deepseek-flash. dream_engine,
immune_engine and codegen.py:844 still dispatch deepseek-v4-flash;
codegen emits it into generated Python, so moving it is a P3 change.

<!-- __s364_doc_e5_v1__ -->
immune_engine.py:169 also names `claude-3-haiku-20240307`, the third
provider in `_default_llm_caller`. It is tried when DEEPSEEK_API_KEY
and MISTRAL_API_KEY are unset or their calls fail. Anthropic retired
that id on 2026-04-20 (/root/anthropic_deprecations_s363.html
010edb14..., 15.4), and it has no table entry. The caller does not
check the HTTP status: a response without `content` text raises
inside its try, which it logs as a warning and skips. It then
returns an empty string, so `_generate_antibody` returns None.
RUNTIME_TIERS dropped the same id under K2; the engine kept it. The
5.81.0 known limits omit it (S363 E5, found after the release).
Anthropic's response to the retired id was not measured.

### 15.6 Open after P1

- A free entry never ages (15.1). Whether an OpenRouter ":free" id can
  bill instead of failing is not pinned.
- /v1 chat replay keys each recorded call by provider (the tier name)
  and model. A log recorded on the old cascade may not replay on the
  new one. Not measured.
- FG-S363-A: the Anthropic deprecations page gave three sha256 values
  at one byte length (427584) in three fetches (S362 72defeab, S363 R2
  92f810a4, S363 pin 010edb14). The pin identifies the stored copy; the
  check is the two rows it must contain.
- website/ide.html:693 describes Tier0A as Hermes-405B via OpenRouter;
  the generated runtime prices Tier0A at 0.25/1.25 per 1M and
  dream_engine sends Tier0A to Anthropic.
- Engine dispatch ids (15.5); mistral-small-latest has no table entry
  and no pin.
- immune_engine's retired Claude fallback (15.5) is missing from the
  5.81.0 known limits. The next release's CHANGELOG carries it.
  <!-- __s364_doc_e5_open_v1__ -->

<!-- __s364_decisions_v1__ -->
## 16. S364 decisions (F1, E5, P2), written before the code

Basis: HEAD e8ae637, Server A tree clean. Files read from a clone of
origin at e8ae637; e8ae637 changed only this document, and Server A's
tree was clean at 6e1b2ab with six file sha256 values equal to the
clone's, so tracked bytes are identical (no .gitattributes).
verifier.py 4599391b..., cli.py 70561f49..., nous_api_server.py
08d1adea..., pricing.py e9021eb9..., immune_engine.py 1f3d70db....
Measurements in the chat container used z3 5.1.0; Server A's z3
version was not read. One live read on Server A: /v1/verify on 5.81.0,
2026-09-19 between 12:34Z and 12:42Z.

### 16.1 Corrections to sections 1 and 14

- Section 1 names four CLI verify sites. There are nine. cli.py:873,
  1032, 1077 and 1382 call `verify_program(program)`; cmd_consciousness,
  cmd_metabolism, cmd_symbiosis, cmd_telemetry and cmd_retire build
  `NousVerifier(program)` directly (cli.py:1130, 1170, 1216, 1263, 1327).
  None passes a table.
- `nous verify --smt` delegates to cli_verify, which loads the table
  (`load_pricing(--prices)`) and never calls verify_program, so it runs
  neither VR001 nor the structural checks.
- The API loads the table once per process (`_get_default_pricing`,
  nous_api_server.py:254-263) and turns any load exception into None,
  which skips VR003 without a finding.
- mitosis_engine.py:324 re-runs NousVerifier with no table at runtime,
  over souls it builds with `MindNode(model="runtime")`.

### 16.2 F1: non-affirmative items carried tier PROVEN

Measured: `VerificationResult.add` defaults `tier` to "PROVEN"
(verifier.py:113), and `error`, `warning` and `info` pass no tier, so
every ERROR, WARNING and INFO item carries tier PROVEN. The only reader
is /v1/verify (nous_api_server.py:298, whose own fallback is also
"PROVEN"). Live on Server A: /v1/verify on templates/market_monitor.nous
returned VMB002 and VMI003 (WARNING) and VMI005 and VIM005 (INFO), each
with tier PROVEN. In the container all 12 templates emit at least one
such item. tests/test_verify_honest_tiers.py and
tests/test_verify_tier_routing.py filter on affirmative items (severity
PROVEN) and did not see it. This is an overclaim on a shipped surface
(Constitution Article IV) and is corrected first in the next release.

An affirmative item is one emitted by `prove`, `verify`, `estimate` or
`report`. verifier.py has 45 non-affirmative call sites.

- F1.1 No ERROR, WARNING or INFO item carries tier PROVEN.
- F1.2 A non-affirmative item carries the tier its code carries when
  affirmative, where that is a single tier other than PROVEN: 29 sites.
- F1.3 Otherwise it carries no tier (JSON null): 14 sites whose code is
  never affirmative, and both VR003 errors (refuted; solver unknown or
  error). A refutation carries its counterexample in the message and
  detail; the tier axis stays reserved for the bound itself.
- The map lives in verifier.py. A test derives it from the affirmative
  calls by AST and fails on drift. The CLI does not read the tier and
  its output does not change. No generated bytes change.
- Red first: across the 12 templates no non-affirmative item carries
  tier PROVEN, and no /v1/verify entry outside `proven` does.
  tests/test_s189_smt_cost_proof.py asserts only that a refuted VR003 is
  not ESTIMATED, so it stays green.

### 16.3 E5: immune_engine's retired Claude leg

Decision: removed in the next release, red first, in its own commit.
K2 already removed the same id from RUNTIME_TIERS for the same reason,
and the leg cannot return text (15.5). immune_engine is imported by
generated code, not generated, and codegen.py names no Claude id, so no
generated bytes change. The Anthropic branches of `_default_llm_caller`
serve only that leg and go with it. The provider list moves to module
level so a test can read it. `deepseek-v4-flash` and
`mistral-small-latest` stay; the CHANGELOG keeps them as known limits.

Red test: every model in immune_engine's default provider list resolves
in the shipped table (an alias is allowed) with lifecycle ok, or is on
a disclosed unpriced list that holds only `mistral-small-latest` (K3
open).

### 16.4 P2 decisions

- P2.1 Scope. With a table supplied, VR001 and VR002 price each soul by
  `soul.mind.model` through `PricingTable.resolve`, in one helper. The
  mitosis estimates (VMI) keep TIER_COSTS because `clone_tier` names no
  model; the dream estimates (VDR) keep it because `dream_mind` is
  optional. How a clone or a default dream mind names its model is a P4
  question. With no table (the mitosis runtime re-verify, direct test
  calls) the verifier keeps the tier path; P3 owns the runtime.
- P2.2 Callers. All nine CLI sites and /v1/verify pass one table.
  `--prices` applies to plain `nous verify`; without it the CLI uses
  `load_pricing()`. A load failure is a typed error on both surfaces;
  the API no longer turns it into None.
- P2.3 Unpriceable. With a table, a soul whose model is not in it, whose
  entry is removed (`lifecycle_status`), whose entry bills per hour, or
  which declares no mind, gets a VR001 ERROR naming the model and the
  reason. No Tier1 fallback. The shipped table holds one removed entry
  (deepseek-chat, removed_after 2026-07-24) and one per_hour entry
  (llama-3-3-70b-local). Measured blast radius: 0 of 26 template souls;
  27 of the 88 souls in the 48 parseable tracked .nous files
  (claude-sonnet 13, claude-haiku 5, gemini-flash 3, deepseek-v3 2,
  llama-8b 2, claude-sonnet-4-5 1, no mind 1).
  tests/test_s189_vr003_unpriceable.py::test_api_verify_dark_for_unpriceable_no_422
  asserts ok True for an unpriceable program; for VR001 that is reversed
  on purpose. VR003's dark path does not change, and its three tests
  stay.
- P2.4 Staleness. VR001 is an estimate, so it uses
  `staleness_status(under_smt=False)`: an entry older than 30 days adds
  a VR001 WARNING naming the model and its verified_date. No refusal;
  the 90-day refusal stays with --smt and VR003. The finding depends on
  the date by design, so every test that reads it pins the date. Today
  only deepseek-r1 (82 days) is past 30; the claude entries pass 30 days
  after 2026-10-08.
- P2.5 Tokens do not change: 300 plus 500 per sense in, 200 out
  (verifier.py:53-55). D5 is P5.
- P2.6 Red test, tests/test_s364_one_verify.py: for the 12 templates and
  three fixtures, the (code, severity) multiset from `nous verify` equals
  the one from /v1/verify. The fixtures are a soul whose tier price and
  model price differ, pinning VR001's figure to the model price; a soul
  with an unpriceable model (VR001 ERROR on both); a soul with no mind.
  Red today: 4 of 12 templates differ because VR003 runs only in the API
  (container, z3 5.1.0).
- P2.7 Copy. website/blog/index.html:3431 ("based on its mind tier")
  becomes false for the CLI and the API and is rewritten. The VR001 guard
  in tests/test_s362_claims_copy.py is rebound to blog:3221 (clone
  admission, still tier-priced) and blog:3431 (model-priced). The
  transcripts at website/docs/index.html:606 and website/index.html:403
  are recomputed during the build. Deployed through
  scripts/deploy_website.sh after the commit.
- P2.8 No generated bytes change: verifier.py, cli.py and the API only.

### 16.5 Release

Units in order, each red first in its own commit: F1, E5, P2. Then one
version bump; floor and hero move once, from the live count.

<!-- __s364_f1_amend_v1__ -->
### 16.6 Amendment to 16.2 (found writing the F1 red test)

F1.2 derived the tier by code for every non-affirmative item. VD001 is
affirmative as VERIFIED, so its INFO note that no routes are defined
and deadlock analysis was skipped would have carried VERIFIED for a
check that did not run. All 14 INFO sites in verifier.py are notes of
this kind (skipped, disabled, partial, capacity, coverage), not results
of a check. F1.2 and F1.3 now read:

- F1.2 An ERROR or WARNING item carries the tier its code carries when
  affirmative, where that is a single tier other than PROVEN: 20 sites,
  20 codes.
- F1.3 Every other non-affirmative item carries no tier (JSON null):
  the 14 INFO sites, the 9 ERROR or WARNING sites whose code is never
  affirmative, and both VR003 errors, 25 sites in all.

The red test prices its fixture from a table built in the test and
dated the day it runs, so its refuted VR003 does not go dark when a
shipped entry passes 90 days. By code reading,
tests/test_s189_vr003_unpriceable.py::test_api_verify_lights_vr003_for_default_priced
prices claude-opus-4-7 (verified 2026-09-08) from the shipped table and
fails from 2026-12-08 unless that entry is re-verified first. Recorded,
not changed here.

<!-- __s364_p2_build_v1__ -->
### 16.7 P2 build notes (written with the code)

- The blog sentence is website/blog/index.html:3432; 16.4 said 3431,
  its section heading.
- A soul with no mind fails validation (S002) before either surface runs
  the verifier, so the no-mind fixture of P2.6 cannot reach VR001 from
  the CLI or the API and is dropped. The verifier still refuses such a
  soul for a direct caller.
- website/docs/index.html:606 and website/index.html:403 show no source
  program for their Scout transcript, so there is nothing to recompute;
  they stay as illustrations of the output format.
- VR001 compares the table's currency with the cost law's (`$` is USD,
  a euro-sign literal is EUR), the rule --smt applies to the cost cap
  (smt_emit._validate_currency_consistency). A mismatch is a VR001 error.
- VR001's figure uses the --smt per-call formula, reasoning multiplier
  included, over the verifier's token estimates. A free entry prices at
  0.
- A deprecated entry is a VR001 warning, as is a price older than 30
  days; one warning per model.
- VR002 with an unpriceable soul in a cascade is a warning that the
  total was not estimated.
- NousVerifier and verify_program take `today` so tests pin the date;
  VR003 passes it to emit_smt. With no date both use the UTC date, as
  before.
- The CLI now runs VR003. Without z3 installed, a program with a
  cost_cap fails `nous verify` with a VR003 error that names the smt
  extra (measured with the z3 import blocked); the API behaves the same
  on a host without z3. The release smoke verifies sycophancy_guard,
  which declares no cost_cap.
- The five direct CLI sites share identical surrounding lines, so their
  edit must match exactly five times; a partial state refuses.
- load_pricing(custom_path) falls through to the other layers when the
  explicit path does not exist, so `--prices missing.toml` used the
  shipped table without a word. The P2 CLI helper refuses a missing
  explicit path itself. The loader and its ten other explicit-path
  call sites (--smt, emit-smt, `nous prices`, conformance, dossier,
  run_shas, the governance ledger) are unchanged here and carried as a
  known limit.
- nous_api_server raises PricingUnavailable from _get_default_pricing,
  and /v1/verify reports it as VERIFY001 (422). Only a successful load
  is cached.

<!-- __s365_p3_decisions_v1__ -->
## 17. S365 decisions (P3), written before the code

Basis: HEAD 9b916f3 = origin/main, tree clean, tag v5.82.0 one commit
behind HEAD. Every read below was taken on Server A between 2026-09-21
00:14Z and 00:58Z against that tree. Nothing ran against a provider.
File sha256 at read time: this document e8a67be5..., verifier.py
9c5e1e89..., cli.py b3d90e7a..., nous_api_server.py 19d726d5...,
immune_engine.py 2a7803df..., pricing.py e9021eb9...,
pricing/defaults.toml 58ffc6fa..., canonical table 1f0a3ede....

### 17.1 Corrections to sections 9 and 15.5

Four priors carried into this phase are false. Each is recorded with
the read that falsified it.

- X1 "codegen.py:844 emits deepseek-v4-flash into generated Python, so
  moving it changes generated bytes" (15.5). Line 844 is the else
  branch of `ds.dream_mind.model if ds.dream_mind else`, reached only
  by a dream_system that declares no dream_mind. All three tracked
  .nous files with a dream_system declare one: dream_lucid_test.nous:21
  and dream_test.nous:22 (deepseek-v4-flash), and
  templates/trading_floor.nous:75 (deepseek-flash). Repro:
  `git grep -ln dream_system -- '*.nous'` then
  `git grep -n dream_mind -- '*.nous'`. Editing 844 alone produces zero
  regression-baseline diffs. The `deepseek-v4-flash` in
  dream_test.gen.py:112 is the declared mind of dream_test.nous:22, not
  the default.
- X2 The regression gate is not template-scoped. regression_harness.py
  discovers every .nous file in the repo (rglob, discover_nous_files)
  and compares the sha256 of the generated Python against
  tests/regression_baseline.json: 59 entries, 49 hashed, 2 skipped
  (replay blocks), 8 recorded as compile errors. 46 of the 49 hashed
  entries carry at least one soul. A change to the per-soul emission
  rebaselines 46 entries, not one template.
- X3 "Decide charge(): wire observed usage as recorded evidence"
  (section 9, P3) has no source inside a generated program. A generated
  program dispatches no LLM: the only network call in
  templates/trading_floor.py is `_sense("http_get", ...)` at line 97,
  and the file carries no httpx import, no API key read and no token
  counts. Repro: `grep -nE 'httpx|API_KEY|usage|tokens'
  templates/trading_floor.py`. There is no observed usage there to
  charge.
- X4 charge() is not a free choice.
  tests/test_s361_runtime_copy.py::test_no_shipped_module_calls_cost_tracker_charge
  asserts that no module in pyproject py-modules calls `.charge(`, and
  it is bound to the docs-page disclosure "does not meter observed
  spend". Wiring charge() would falsify shipped copy in the same
  commit.

### 17.2 P3 decisions

- P3.1 Emission. codegen passes the declared model to SoulRunner at
  both add_soul sites (codegen.py:787-797 and codegen.py:1025-1035),
  from `soul.mind.model`, and `"unknown"` when the soul declares no
  mind, mirroring the existing `self.model` emission at
  codegen.py:342-346. `SoulRunner.__init__` gains
  `model: Optional[str] = None`. This is the generated-bytes change:
  one added line per soul.
- P3.2 Pricing. The per-soul runtime estimate prices by model instead
  of by tier label, through `PricingTable.resolve`, with the verifier's
  formula: `(est_input * input_per_1m + est_output * output_per_1m *
  reasoning_token_multiplier) / 1000000`; a free entry prices at 0.0.
  Tokens do not change: pre_check keeps 500 in and 200 out (D5 is P5).
  runtime.py imports pricing lazily inside the function that needs it,
  never at module level: codegen emits a try/except ImportError
  fallback for pydantic (codegen.py:205-212), so a module-level pricing
  import would make pydantic a hard requirement of every generated
  program. One table load per process, memoised.
- P3.3 Refusal. An explicitly passed model that the table cannot price
  refuses in `SoulRunner.__init__`, which is reached from
  `build_runtime`, as section 9 requires. A typed exception whose
  message starts with the cause names the model and the reason: not in
  the table, removed by lifecycle_status, or billed per hour.
  `model=None`, which is what the two direct constructors pass
  (mitosis_engine.py:387 and test_runtime_v2.py:138), neither prices
  nor refuses, so no non-generated caller changes. Currency is out of
  scope: a generated program carries no law currency to compare against
  the table's.
- P3.4 charge() is not wired (X3, X4). The S361 disclosure and its test
  stay as written. The CHANGELOG restates the limit: the generated
  runtime pre-checks a constant estimate and does not meter observed
  spend.
- P3.5 Clone admission. mitosis_engine stops naming `"runtime"`
  (mitosis_engine.py:306) and `"cloned"` (mitosis_engine.py:353): both
  read the model off the runner, available after P3.1, with
  `"unknown"` as the fallback, and the clone node carries the parent
  runner's model. No table is passed to the runtime re-verify, so the
  verifier stays on the tier path (verifier.py:418-425) and no
  admission verdict changes; what changes is that the re-verified
  program names the real models. Whether the admission gate consults
  the table is a P4 question: it would turn a pricing-table fact into a
  runtime admission refusal, and needs its own kill criteria.
- P3.6 Out of scope, recorded. The engine dispatch ids (dream_engine
  51, 358, 367; immune_engine 144) stay operator-gated and emit no
  generated bytes. mistral-small-latest still has no table entry and no
  pin (K3).
- P3.7 Baseline. The rebaseline lands in the same commit as the
  emission change, with the diff count stated in the commit message. No
  new module, so pyproject py-modules and the release wheel-content
  gate do not change.

### 17.3 Blast radius, measured

Against the shipped table, the models in the 49 hashed baseline entries
that P3.3 would refuse are exactly the ones VR001 already errors on
since 5.82.0: no mind (5 files), claude-sonnet (13), claude-haiku (7),
gemini-flash (3), deepseek-v3 (2), deepseek-chat (2, removed
2026-07-24), llama-8b (2), claude-sonnet-4-5 (1). Zero of the 12
templates. The refusal fires at build_runtime, which the harness never
reaches: the harness compiles, it does not execute.

### 17.4 Red first

tests/test_s365_runtime_model_priced.py, written and failing before any
code:

- every gate-clean corpus program emits `model=` in each add_soul call,
  read by AST from the generated source, with the value equal to the
  declared mind model;
- a SoulRunner built with a model whose table price differs from its
  tier price pre-checks at the table price, pinned to a table built in
  the test and dated the day it runs;
- a free entry pre-checks at 0.0;
- an unpriceable model refuses at build_runtime with the typed
  exception, once per reason: absent, removed, per_hour;
- `model=None` neither prices nor refuses;
- the mitosis re-verify verdict for a fixture is unchanged by P3.5, and
  the re-verified program names the parent's model rather than
  "runtime".

### 17.5 Kill criteria

- If any of the 12 templates, or any test that executes build_runtime,
  refuses under P3.3, the refusal moves from `SoulRunner.__init__` to
  pre_check (a failed pre-check skips the cycle instead of failing the
  build), and this document records the move before the code changes.
- If the lazy pricing import adds a hard dependency to the generated
  program's import surface, P3.2 reverts to the tier path and P3 ships
  as emission only.
- If the rebaseline diff count is not exactly the number of hashed
  baseline entries carrying souls (46 at the time of writing), the
  emission has a second effect that was not decided here: stop and
  measure it before committing.

<!-- __s365_p3_build_v1__ -->
### 17.6 P3 build notes (written with the code)

- Refusal placement. A scan of tests/*.py and tests/**/*.nous found 20
  files declaring a model the shipped table cannot price; two of them
  load a generated module: tests/test_inject_message.py (model `test`)
  and tests/test_intervention.py (model `claude-haiku`). Neither file
  calls build_runtime, and a generated module constructs SoulRunner only
  inside build_runtime, which it calls from main(). The 17.5 kill
  criterion is checked by the full suite before the commit, not assumed
  here.
- `model` is the last parameter of SoulRunner.__init__, after
  `sense_cache`, so a positional caller keeps its meaning. codegen emits
  it after `tier=`.
- The refusal lives in `resolve_soul_price`, which SoulRunner.__init__
  calls when a model is passed and pre_check calls when it prices by
  model. The table is memoised per process in `_RUNTIME_PRICING` through
  `runtime_pricing()`, loaded by `load_pricing()` with no path, the
  loader the API and dispatch use.
- runtime.py imports pricing only inside `runtime_pricing` and
  `resolve_soul_price`, so importing runtime does not import pricing.
  tests/test_s365_p3_runtime_surface.py asserts it in a fresh
  interpreter.
- A deprecated or stale entry prices normally. The staleness result is
  carried on SoulPrice and not logged; P3 adds no runtime log line.
- A command that builds a runtime (`nous run`, replay, hot reload,
  compiled trace) now meets the refusal as an uncaught
  UnpriceableSoulModel whose message names the model and the reason. A
  clean CLI message instead of a traceback is release-unit work.
- The clone runner built at mitosis_engine.py:387 passes no model, as
  17.2 P3.3 decided, so a clone pre-checks at its tier price, and a
  re-verify that includes an existing clone names it `"unknown"`.
  Carried to P4 with the admission-table question.
- The P3.5 test lives in tests/test_s365_p3_runtime_surface.py, not in
  the 17.4 file, so the committed red test stays byte-identical to the
  file the red gate ran.
- The CHANGELOG entry, and a check of shipped copy that describes the
  runtime pre-check price basis, are release-unit work, not this commit.
- Amendment to 17.4, found on the first apply. The codegen test as first
  written asserted a SoulRunner call for every template.
  templates/cost_cap_basic.nous and templates/sycophancy_guard.nous
  declare no soul, so those two parameters were red for a false premise
  and stayed red after the code. The first apply failed its green gate on
  exactly those two and restored every original byte. The assertion now
  requires a call only when the template declares a soul; the
  emitted == declared comparison is unchanged, so a soul-bearing template
  that emits nothing still fails. The red gate compares the set of
  failed test ids with an expected set, not a count.
- 17.4 names the gate-clean corpus; the test covers the 12 templates. The
  corpus-wide check is the rebaseline: every hashed baseline entry that
  carries a soul must change and no other may (17.5).
- Correction to 17.2 P3.2. pyproject declares pydantic>=2.0.0 as a
  dependency, so a module-level pricing import would add no requirement
  and the second 17.5 kill criterion cannot fire. The lazy import stays:
  importing runtime does not load the pricing code.
