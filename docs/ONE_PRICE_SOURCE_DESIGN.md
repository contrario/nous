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

<!-- __s366_sec18_v1__ -->
## 18. S366 decisions (FG-S364-A), written before the code

Basis: HEAD 4b89d1c = origin/main, tree clean, tag v5.83.0 one commit
behind HEAD, read by RULE 0 on Server A at 2026-09-21 23:16Z. The code
was read and executed in a container clone at 4b89d1c between 23:16Z
and 23:41Z. Server A's tree was clean at the same commit, so its files
are the committed blobs the clone holds; the 16 files RULE 0 hashes
(runtime.py, codegen.py, cli.py, pricing.py, this document, and 11
more) match byte for byte. The container runs used an isolated HOME
and working directory, so layers 2 and 3 were absent. Server A's own
layer 2 and 3 files were not read. Nothing ran against a provider.
File sha256 at read time: this document 62002608..., pricing.py
e9021eb9..., dossier.py 9cd972de..., cli.py b3d90e7a..., cli_prices.py
b4ed6546..., cli_verify.py bbc564f5..., cli_emit_smt.py 63b10a9c...,
cli_conformance.py 9accb6a4..., dossier_spec.py bccabbaa...,
run_shas.py 89a22aca..., canonical table 1f0a3ede....

### 18.1 Corrections to 16.7 and to the 5.83.0 CHANGELOG

- Y1 "ten other explicit-path call sites" (16.7, the S365 handoff and
  the S366 opener). There are eleven besides the P2 helper
  (cli.py:855-864): cli_verify.py:135 (`--smt`), cli_emit_smt.py:45,
  cli_prices.py:79, 132 and 218 (`show`, `verify`, `age`),
  cli_conformance.py:206, dossier.py:100, dossier_spec.py:177 (`nous
  dossier-spec`), run_shas.py:63 and 108, and cli.py:1475 (the
  governance ledger). The list folded dossier-spec into "dossier".
  Repro: `git grep -n "load_pricing(" -- '*.py' ':!tests/*'`.
- Y2 Conformance never fell back. `--prices` is required
  (cli_conformance.py:73 and 115) and `_derive_inputs` refuses a path
  that is not a file before it calls load_pricing
  (cli_conformance.py:193-200). Measured: `nous conformance verify` and
  `nous conformance certify` with a missing `--prices` print
  "PRECONDITION ERROR: prices file not found: <path>" and exit 2. The
  5.83.0 CHANGELOG known limit (CHANGELOG.md:124) and 16.7 name
  conformance wrongly and do not name dossier-spec.
- Y3 The fall-through is wider than a missing file. A layer counts as
  found only when `p.is_file()` (pricing.py:291), so a directory given
  as `--prices` falls through exactly as a missing path does. Measured
  with both.
- Y4 The dossier's fall-through is not in load_pricing.
  `_find_pricing_match` (dossier.py:91-108) skips a custom path that is
  not a file and searches layers 2-4 for a table whose sha256 equals the
  manifest's, calling load_pricing only on files that exist. A loader
  change alone leaves `nous dossier` unchanged.

### 18.2 Behaviour today, measured

Explicit path missing, layers 2 and 3 absent, so every fall-through
landed on the shipped table (layer 4, canonical 1f0a3ede...).

| site | exit | what happens |
|---|---|---|
| plain `nous verify` (P2 helper) | 1 | refuses: "--prices path is not a file" |
| `nous verify --smt` | 0 | "Loaded pricing: layer 4"; the proof runs and prints PROVEN against the shipped table |
| `nous emit-smt -o` | 0 | writes the spec; "layer used: 4" |
| `nous prices show` | 0 | layer 1 "not found", layer 4 marked ACTIVE, summary of the shipped table |
| `nous prices verify`, `age` | 0 | report the shipped table |
| `nous conformance verify`, `certify` | 2 | refuse (Y2) |
| `nous dossier`, manifest under the shipped table | 0 | builds; the sha search matches layer 4 |
| `nous dossier`, manifest under a custom table | 1 | refuses with the wrong cause: "no pricing TOML in candidate layers matches" |
| `nous dossier-spec` | 0 | signs a manifest whose pricing_sha256 is the shipped table's |
| run_shas, both functions | none | return values derived from the shipped table |
| ledger, trace under the shipped table | 0 | attaches K without a word |
| ledger, trace under a custom table | 1 | refuses with the wrong cause: "smt_spec_sha256 mismatch" |

The Z3 results in these rows hold for the table they name, and each
signed manifest binds that table's pricing sha256. The defect is that
it is not the table the operator named, and nothing says so.

### 18.3 Decisions

- A1 Loader. load_pricing refuses when `custom_path` is not None and
  is not a regular file, before any layer is consulted. It raises
  `PricingPathError`, new in pricing.py, a subclass of
  FileNotFoundError, with a message that starts with the cause and
  names the path: "explicit pricing path is not a file: <path>".
  Subclassing FileNotFoundError keeps every existing handler catching
  it. `custom_path=None` keeps the layered lookup byte for byte, so the
  API, dispatch, the generated runtime and the VSA vector minter, which
  all pass no path, do not change. `_candidate_layers` does not change.
- A2 Existing handlers carry the refusal. `--smt` exits 3 ("ERROR:
  pricing load failed"), emit-smt 2, `prices verify` and `age` 2,
  dossier-spec 1 (through DossierSpecError), the ledger 1 ("REFUSED:
  --source pricing load failed"). None of these handlers is edited.
- A3 `nous prices show`. When `--prices` is given and is not a file, no
  layer is marked ACTIVE; the four layer lines still print, and the
  command exits 2 through its existing load handler with the loader's
  message. That handler loses its `# pragma: no cover`, since it becomes
  reachable and tested. The "no pricing TOML available" message stays
  for the case with no flag.
- A4 `nous dossier`. `_find_pricing_match` raises DossierError before
  probing any layer when an explicit path is given and is not a file,
  message starting with the cause and naming the path. cli_dossier.py
  already turns DossierError into exit 1.
- A5 Not changed in this unit: a `nous dossier --prices` path that is a
  file but does not load, or loads with a sha256 that does not match the
  manifest, is still skipped in favour of a matching layer
  (dossier.py:96-104, by code reading; the mismatch case measured in
  18.2). The resulting dossier is consistent with its manifest, and the
  operator's path is ignored without a word. Whether that refuses too is
  an operator decision, carried in the S366 handoff.
- A6 run_shas is not edited. Both functions let PricingPathError
  propagate. Both production callers pass no path
  (compiled_trace.py:73 and 75, nous_ast_runner.py:246 and 248), so no
  command reaches the explicit branch. Wrapping it in RunShasError
  would also change the type of the existing no-layer and invalid-TOML
  errors, which is outside this unit.
- A7 The P2 helper is not edited. Its own check now duplicates A1 and
  refuses first, so plain `nous verify` keeps its message and exit 1.
- A8 Release-unit work: the CHANGELOG states the change and corrects
  Y2 (conformance always refused; dossier-spec fell back and was not
  named); docs/COST_VERIFICATION_GUIDE.md gains one sentence under the
  layer table: an explicit `--prices` that is not a file is an error,
  and layers 2-4 are consulted only when no path is given. The `--prices`
  help text "(default: layered lookup)" describes the case with no flag
  and stays true. The site is grepped for layer and fallback statements
  before release (FG-S365-G). The blog post and docs/DECISION_LEDGER.md
  line saying the ledger refuses on a pricing failure become true for a
  missing prices file; neither is edited.
- A9 No new module, so pyproject py-modules and the wheel-content gate
  do not change. No codegen change, so templates/trading_floor.py and
  the regression baseline do not move. The verifier registry entries
  are digests of the VERIFY_OFFLINE templates, which A4 does not touch.

### 18.4 Blast radius, measured

- A log-only probe in load_pricing and in `_find_pricing_match` recorded
  every call with an explicit path that is not a file, and every explicit
  dossier path that is a file with a mismatching sha256: 0 events across
  the suite (3071 passed, 13 skipped in the container). A direct call
  wrote one event, so the probe reaches its target.
- The suite with A1 and A4 applied as raising probes: 3071 passed, 13
  skipped, failed set empty.
- The container runs one test fewer and skips one more than Server A
  (3072 passed, 12 skipped there). The green gate runs on Server A.
- One handler in the call-site files and the run_shas callers continues
  after a failed load: `except Exception: continue` at dossier.py:101,
  inside the sha search. A4 refuses before that loop, so a path that is
  not a file never reaches it. Every other broad handler in those files
  wraps something other than a pricing load: a version import, a health
  probe, a subprocess launch, a witness file read, a Farkas JSON parse,
  a trace-bridge shutdown and a discount percentage.

### 18.5 Red first

tests/test_s366_prices_path_refused.py, written and failing before any
code. Each CLI case runs in process with HOME and the working directory
set to a temporary directory, so layers 2 and 3 are absent. Tables the
tests need are built in the test and dated the day it runs. The new
exception is checked by type name and by `isinstance(...,
FileNotFoundError)`, never imported at module level, so the file
collects before the code exists.

- Red, and failing for the stated reason: the loader refuses a missing
  path and a directory with the typed error; each of `verify --smt`,
  emit-smt, `prices show` (no ACTIVE marker), `prices verify`, `prices
  age`, dossier-spec and the ledger exits with its A2 code and the
  loader's message; `nous dossier` refuses with the A4 cause; both
  run_shas functions raise the typed error.
- Controls, green before and after: `custom_path=None` resolves the
  shipped table at layer 4; an explicit path that exists loads at layer
  1; conformance verify and certify already refuse; plain `nous verify`
  already refuses.

The red gate compares the set of failed test ids with the expected red
set and the set of passed ids with the controls, and prints each failed
id with its first assertion line, so a case red for the wrong reason is
visible before the code (FG-S365-B).

### 18.6 Kill criteria

- If the green run on Server A fails any test outside the new file, the
  change had an effect 18.4 did not measure: restore, then measure
  before any retry.
- If anything that passes no explicit path changes, A1 is wrong: the
  regression harness must show 0 diffs, and `nous prices show` with no
  flag must print the same bytes before and after the code.
- If the refusal reaches a handler that continues instead of failing,
  the site is recorded here before the code changes again.

The UnpriceableSoulModel CLI message is a separate unit, with its own
recon and decisions written as section 19 before its code.

<!-- __s366_sec19_v1__ -->
## 19. S366 decisions (UnpriceableSoulModel at the command line), written before the code

Basis: HEAD d406670 = origin/main, pushed 2026-09-22 00:11:14Z, tree
clean. Code read and executed in a container clone, first at 4b89d1c
and then fast-forwarded to d406670, with an isolated HOME and working
directory, ending 00:14Z by the container clock. Every file cited below
is byte-identical at both commits: the FG-S364-A commit changed only
pricing.py, cli_prices.py, dossier.py and its test. Nothing ran against
a provider. File sha256 at read time:
this document 86887fe4..., runtime.py 50e6c315..., cli.py b3d90e7a...,
replay_cli.py e6ea837d..., hot_reload_engine.py 68e9d27d...,
compiled_trace.py a54b3252....

### 19.1 Corrections to 17.6 and to the 5.83.0 CHANGELOG

- Z1 17.6 and the 5.83.0 known limit say `nous run`, replay, hot reload
  and compiled trace meet the refusal as an uncaught UnpriceableSoulModel.
  Measured with a soul model the table does not carry:
  - `nous run` without `--hot` runs the AST runner
    (nous_ast_runner.run_program, cli.py:192), which never constructs a
    SoulRunner. The program runs, exit 0, and nothing is refused.
  - `nous run --hot` exits 1 with a raw traceback: build_runtime at
    cli.py:259 is outside any try.
  - `nous replay --mutate` catches every exception from the build and
    the drive (replay_cli.py:340-362) and prints "DIVERGENT --
    UnpriceableSoulModel: ...", exit 4, the code for a behavioural
    divergence. Against an empty recorded baseline the same source with
    a priced model prints EQUIVALENT, exit 0.
  - compiled trace (compiled_trace.run_compiled_with_trace) has no CLI or
    API caller, and never reaches the refusal: compute_run_shas
    (compiled_trace.py:73) fails first, with a raw KeyError for a model
    the table does not carry and a raw ValueError for a removed or
    per-hour one. That is O2 (14.10), not this refusal.
  - Not named in 17.6: a compiled program run directly (`python
    prog.py`) meets the refusal in its generated main() and prints a raw
    traceback.
- Z2 Hot reload, measured by driving HotReloadEngine._reload against a
  live runtime:
  - H1 An edit that removes soul B and adds soul C with an unpriceable
    model leaves only A. B is removed (hot_reload_engine.py:204-207)
    before build_runtime (line 209) raises, and C is never added. In a
    running world the engine loop catches the exception (lines 59-60)
    and logs "Hot reload engine error: <cause>".
  - H2 An edit that changes soul A from claude-haiku-4-5 @ Tier3 to
    claude-opus-4-7 @ Tier1 leaves A's runner at model claude-haiku-4-5
    and tier Tier1. The swap for a soul present before and after the
    edit (lines 214-226) copies `_instinct`, `_heal`, `_tier` and
    `_heartbeat`, not `_model`, and pre_check prices by `_model`
    (runtime.py:488), so after such an edit the pre-check prices the
    model the world started with.
- Z3 The default `nous run` checks no soul model against the table: the
  P3 refusal covers the generated runtime only. Recorded here, not
  changed in this unit.

### 19.2 Decisions

- C1 `nous run --hot`: the initial build_runtime (cli.py:259) catches
  UnpriceableSoulModel and prints "Error: cannot build the runtime:
  <cause>" to stderr, exit 1, before the world starts. Any other
  exception keeps today's behaviour.
- C2 Hot reload: `_swap_souls` builds the new runtime before it removes,
  swaps or adds any soul. On UnpriceableSoulModel it records "Swap
  refused: <cause>" in the engine's errors, logs it at error level and
  returns with the live world unchanged. Any other exception now also
  leaves the world unchanged, because nothing has been removed when the
  build fails, and the engine loop still logs it.
- C3 Hot reload copies `_model` with `_tier` for a soul present before
  and after the edit. The new runner was built, so its model has
  already passed the refusal.
- C4 `nous replay --mutate`: UnpriceableSoulModel from build_runtime is
  a build error, not a divergence. The command prints "error: cannot
  build the runtime for <source>: <cause>" to stderr and exits 1, the
  code its docstring gives for I/O and compile errors, with no text or
  JSON report; the generated temporary file is still removed. Any
  other exception keeps the divergence path.
- C5 Compiled trace is not changed: it fails before build_runtime, with
  O2's raw errors, and no command reaches it. Its docstring says a build
  failure raises CompiledTraceError; O2's unit owns that.
- C6 The generated main() is not changed: catching the refusal there
  changes the generated bytes of every soul-bearing program and of
  templates/trading_floor.py (FG-S365-F), which is a codegen unit of
  its own.
- C7 Release-unit work: the CHANGELOG corrects Z1 and states C1-C4 and
  Z3; the site is grepped for statements about `nous run`, replay and
  hot reload behaviour before release (FG-S365-G).
- C8 No new module and no codegen change, so pyproject py-modules, the
  wheel-content gate, the regression baseline and
  templates/trading_floor.py do not move.

### 19.3 Blast radius, measured

A grep of tests/ for HotReloadEngine, `_swap_souls`, `_run_hot_reload`,
`--hot` and `--mutate` finds only tests/test_replay_phase_c.py, a
standalone harness with no collected test function. A grep that finds
nothing is not proof that nothing depends on these paths; the full suite
on the green run is the check.

### 19.4 Red first

tests/test_s366_unpriceable_cli.py, written and failing before any code,
with HOME and the working directory isolated:

- Red: `nous run --hot` on a program with an unpriceable soul model
  exits 1 with the C1 message and no traceback; `nous replay --mutate`
  on the same program against an empty recorded baseline exits 1 with
  the C4 message and no DIVERGENT line; H1: after the refused edit the
  live runners are unchanged and the engine's errors carry "Swap
  refused: unpriceable:"; H2: after a priced model edit the runner's
  `_model` is the new model.
- Controls, green before and after: `nous replay --mutate` with a priced
  model against the same baseline prints EQUIVALENT, exit 0; a priced
  hot reload edit that adds a soul adds it.

The red gate compares the set of failed test ids with the expected red
set and the passed ids with the controls, and prints each failure's
first line (FG-S365-B).

### 19.5 Kill criteria

- If the green run on Server A fails any test outside the new file,
  restore and measure before any retry.
- The regression harness must show 0 diffs: nothing here changes
  generated code.
- If building the new runtime before any removal changes what a swap
  does for a priced edit, the priced control fails; C2 is then recorded
  here as wrong before the code changes again.

<!-- __s366_sec19_notes_v1__ -->
### 19.6 Build notes, written with the code

- C1 cli.py: `_run_hot_reload` catches UnpriceableSoulModel around the
  initial build_runtime only. The import is local to the function, like
  the other imports there.
- C2 hot_reload_engine.py: `_swap_souls` builds the new runtime before
  any removal and now returns a bool; `_reload` returns without counting
  the reload or logging "HOT RELOAD COMPLETE" when it is False, so a
  refused swap does not reach `_reload_count`. The existing path for a
  generated module with no build_runtime() returns True and keeps its
  old accounting; this unit does not change it.
- C3 One line copies `_model` after `_tier`.
- C4 replay_cli.py: the new except sits before the existing `except
  Exception` and covers the whole build-and-drive block. Inside that
  block only build_runtime raises UnpriceableSoulModel: the drive calls
  `instinct()` directly and never the runner's pre-check.
- Measured in the container at d406670: red 4 of 4 for the reasons in
  19.4 and controls 2 of 2; green 6 of 6; suite 3095 passed, 13 skipped,
  0 failed; regression harness 0 diffs; inserted lines ASCII. On Server
  A at 3a52768 the red gate matched by set, 4 red and 2 green, for the
  same reasons.

<!-- __s366_sec19_correction_v1__ -->
### 19.7 Correction to 18.1

18.1, in its heading and in Y2, places the `--prices` known limit in the
5.83.0 CHANGELOG. It is in the 5.82.0 section (CHANGELOG.md:124 at
d406670). The 5.84.0 CHANGELOG corrects that entry. Found while drafting
the 5.84.0 entry.

<!-- __s367_sec20_v1__ -->
## 20. S367 decisions (O2: emit_smt's raw pricing errors), written before the code

Basis: HEAD 1bcbe53 = origin/main, pushed 2026-09-22 08:37:22Z, tree
clean; the Server A RULE 0 at 08:48Z matched every leg of the S367
opener. Code read and executed in a container clone of 1bcbe53,
byte-identical to Server A on 17 file sha256 values, with an isolated
HOME and working directory. One fixture table (sha256 ba9c2b0e...)
served as `--prices` and as ./nous_prices.toml (layer 2); it carries a
priced model and one model of each refused kind. Nothing ran against a
provider. File sha256 at read time: this document 1c30a4b9...,
smt_emit.py 0bd4036e..., pricing.py 0c12c924..., cli_verify.py
bbc564f5..., cli_emit_smt.py 63b10a9c..., cli.py 998b052d...,
compiled_trace.py a54b3252..., run_shas.py 89a22aca...,
cli_conformance.py 9accb6a4..., dossier_spec.py bccabbaa...,
cli_dossier.py 5aff4f93..., nous_ast_runner.py 5e3ae532...,
verifier.py 9c5e1e89..., nous_api_server.py 19d726d5....

### 20.1 Corrections to 14.10 and 19.1

- W1 14.10 names one raw error, a KeyError at pricing.py:192. emit_smt
  calls get_price_for_smt once per soul (smt_emit.py:537), and that call
  raises four raw errors, measured: a KeyError for a model the table
  does not carry (pricing.py:192), and a ValueError for a removed model
  (439), a per-hour model (443) and a model verified more than 90 days
  ago under --smt (450). The fourth is the path deepseek-r1 takes from
  2026-09-28. A fifth, "alias chain too deep" (pricing.py:203), comes
  from the same call; alias validation at load makes it unlikely, not
  impossible.
- W2 19.1 Z1 and the S366 handoff give compiled trace's raw errors as a
  KeyError, or a ValueError for a removed or per-hour model. The stale
  ValueError reaches it too, and a source that does not parse raises a
  raw lark UnexpectedToken at compiled_trace.py:64, before any pricing.
  The docstring (compiled_trace.py:50) promises CompiledTraceError for a
  parse failure as well.

### 20.2 Behaviour today, measured

Each caller ran with a soul model of each kind and with the priced
control, which reached and passed the emit stage. Every refused row
names its model in its output.

| caller | what catches the error | missing, removed, per-hour, stale |
|---|---|---|
| `nous verify --smt` | EmitError only (cli_verify.py:151) | traceback, exit 1 |
| `nous emit-smt` | EmitError only (cli_emit_smt.py:52) | traceback, exit 1 |
| `nous governance ledger --source` | EmitError only (cli.py:1490) | traceback, exit 1 |
| compiled trace (library; no CLI or API caller) | nothing; run_shas.py:64 and :109 do not catch | raw KeyError or ValueError |
| `nous run --emit-trace` (AST runner, via run_shas) | catch-all (cli.py:198) | "Runtime error: <message>", exit 1; the KeyError text arrives inside double quotes |
| `nous conformance certify` and `verify` | (ValueError, KeyError) (cli_conformance.py:252, :322) | "PRECONDITION ERROR: KeyError: ..." or "ValueError: ...", exit 2; certify measured, verify shares _derive_inputs and the same except |
| `nous dossier-spec` | catch-all into DossierSpecError (dossier_spec.py:203) | "SMT emit failed (KeyError): ...", exit 1 |
| `nous dossier` | catch-all (cli_dossier.py:89) | reachable only as time passes after the manifest: with a manifest signed today for a model removed tomorrow, build_dossier at today+10 raised a raw ValueError; the CLI then prints "ERROR: unexpected failure: ValueError: ...", exit 3 (by reading) |
| `nous verify` without --smt | (EmitError, KeyError, ValueError) (verifier.py:369) | VR003 dark by design; VR001 names the cause |
| POST /v1/run with emit_trace | catch-all (nous_api_server.py:1152) | 422 RUN001, the message as for `nous run`, KeyError quoted |
| POST /v1/skill/export with with_dossier | catch-all (nous_api_server.py:478) | 422 SKILLEXPORT001, "SMT emit failed (KeyError): ..." |
| POST /v1/verify | the verifier, as above | 200, VR003 dark, VR001 names the cause |

No /v1 route returns 500 for any of the four kinds.
website/.well-known/nous/vsa-vectors/v1/mint_vsa_vector.py calls
emit_smt on its fixed vector source only.

### 20.3 Decisions

- D1 emit_smt types the refusal at its source. The one get_price_for_smt
  call (smt_emit.py:537) is wrapped: a KeyError or ValueError from it is
  raised again, `from` the original, as UnpriceableSmtModel, a new
  subclass of EmitError defined in smt_emit.py. The message is
  "soul '<name>': <cause>", where <cause> is get_price_for_smt's own
  text; for a KeyError that is its argument, not the quoted repr. It
  opens the way the existing EmitError messages open ("soul 'A' has no
  `mind:` declaration").
- D2 pricing.py does not change. get_price_for_smt keeps its types and
  messages; six tests call it directly and pin them (test_pricing.py x3,
  test_s359_staleness_category.py, test_s360_shipped_table.py,
  test_s361_v4flash_alias.py). pricing.py cannot raise EmitError in any
  case: smt_emit imports pricing.
- D3 The three callers that catch EmitError change no code and now
  refuse with the cause, with the exit code each already gives every
  other EmitError: `nous verify --smt` prints "ERROR: cannot emit SMT
  for <file>:" and the message, exit 3; `nous emit-smt` the same, exit
  3; `nous governance ledger --source` prints "REFUSED: --source emit
  failed: <message>", exit 1, and no ledger.
- D4 Compiled trace: run_compiled_with_trace raises CompiledTraceError
  "parse failed: <cause>" when parse_nous raises, and "cannot derive the
  trace subject binding: <cause>" when compute_run_shas or
  compute_run_gated_actions raises EmitError (UnpriceableSmtModel
  included) or RunShasError, each `from` the original. The docstring
  lists what raises CompiledTraceError: a source that does not parse,
  declares no world, fails validation or cannot be priced for its
  subject binding, and an emitted module that cannot be loaded or has no
  build_runtime(). Every other error, such as a pricing table that does
  not load or a memory consultation refusal, propagates unchanged, and
  the docstring says so.
- D5 The callers that already catch broadly keep their code; their
  output now carries the typed name and the unquoted message:
  conformance "PRECONDITION ERROR: UnpriceableSmtModel: soul ...", exit
  2; dossier-spec and /v1/skill/export "SMT emit failed
  (UnpriceableSmtModel): soul ...", exit 1 and 422 SKILLEXPORT001; `nous
  run --emit-trace` "Runtime error: soul ...", exit 1; /v1/run 422
  RUN001; `nous dossier` "ERROR: unexpected failure:
  UnpriceableSmtModel: ...", exit 3. VR003 stays dark: verifier.py:369
  catches EmitError.
- D6 deepseek-r1 is not touched. From 2026-09-28 `nous verify --smt`
  still refuses it, through the stale path; after this unit that
  refusal is D3's message with exit 3 instead of a traceback. Its entry,
  its verified_date and the refusal itself do not change.
- D7 Recorded, not changed here: `nous dossier` calls an expected
  refusal "unexpected failure"; compiled trace and run_shas let a
  pricing load failure through raw;
  tests/test_trace_emission.py::test_unpriced_program_refused_fail_fast
  accepts any Exception; mint_vsa_vector.py is a published /.well-known
  artifact and is not edited; neither /v1 route gets its own error code.
- D8 Release-unit work: the CHANGELOG states W1, W2 and D1-D6, and the
  site is grepped for statements about how these commands fail before
  release (FG-S365-G). UnpriceableSmtModel lives in smt_emit.py, so
  there is no new module and no codegen change: pyproject py-modules,
  the wheel-content gate, the regression baseline and
  templates/trading_floor.py do not move.

### 20.4 Blast radius, measured

A log-only hook at smt_emit.py:537, in a copy of the tree, recorded
every KeyError or ValueError from get_price_for_smt with the current
test id and raised the same object again. The full suite ran on the
copy with PYTHONPATH set to it, so subprocess tests loaded it too: 3095
passed, 13 skipped, the container's figure. Seven events, from seven
tests:

- tests/test_s189_vr003_unpriceable.py: test_unknown_model_dark_no_raise,
  test_per_hour_model_dark_no_raise, test_stale_model_dark_no_raise and
  test_api_verify_dark_for_unpriceable_no_422 stay green after D1: the
  verifier catches EmitError.
- tests/test_smt_emit.py::TestEmitErrors::test_per_hour_model_rejected
  and ::test_removed_model_rejected stay green: UnpriceableSmtModel is a
  ValueError and keeps "per_hour" and "cannot be used" in its message.
- tests/test_trace_emission.py::test_unpriced_program_refused_fail_fast
  stays green: it accepts any Exception.

The hook sees only tests that reach that call. The full suite on the
green run is the check.

### 20.5 Red first

tests/test_s367_emit_smt_typed.py, written and failing before any code,
with HOME and the working directory isolated and a fixture table of
the kind described in the basis:

- Red, for each of missing, removed, per-hour and stale: emit_smt
  raises UnpriceableSmtModel, an EmitError, whose message starts
  "soul 'A': " and names the model; `nous verify --smt` exits 3 with
  D3's message and no traceback; `nous emit-smt` the same; `nous
  governance ledger --source` exits 1 with "REFUSED: --source emit
  failed: soul 'A': " and no traceback; run_compiled_with_trace raises
  CompiledTraceError whose message starts "cannot derive the trace
  subject binding: soul 'A': " and whose __cause__ is
  UnpriceableSmtModel. Also red: a source that does not parse makes
  run_compiled_with_trace raise CompiledTraceError starting "parse
  failed: "; `nous run --emit-trace` with the missing model prints
  "Runtime error: soul 'A': model " with no double quote before
  "model". 22 red: 4 x 5 + 2.
- Controls, green before and after (7): the priced model emits;
  `nous verify --smt` and `nous emit-smt` on it exit 0; `nous governance
  ledger --source` on it reaches the sha comparison and refuses on the
  mismatch; run_compiled_with_trace on it returns a trace; a soul with
  no `mind:` still raises plain EmitError with today's message;
  get_price_for_smt still raises KeyError for the missing model.

The red gate compares the set of failed test ids with the expected red
set and the passed ids with the controls, prints each failure's first
line, and a red counts only when that line shows the reason above
(FG-S365-B, FG-S366-B).

### 20.6 Kill criteria

- If the green run on Server A fails any test outside the new file,
  restore and measure before any retry.
- If any of the seven tests in 20.4 changes outcome, D1's subclassing
  is wrong; record it here before the code changes again.
- The regression harness must show 0 diffs. A priced program's SMT spec
  must not change: before the code, the emit-smt sha256 of every
  shipped template that emits under the shipped table is recorded at a
  fixed date, and compared after.
- A caller of emit_smt not listed in 20.2 that the green run exposes is
  recorded here before release.

<!-- __s367_sec20_notes_v1__ -->
### 20.7 Build notes, written with the code

- D1 smt_emit.py: UnpriceableSmtModel follows EmitError, and the module
  docstring lists it. The wrap covers only the get_price_for_smt call,
  so an EmitError raised later in the loop (a per_token entry with no
  prices) keeps its own type and text.
- D4 compiled_trace.py: the parse call and the two run_shas calls are
  wrapped; the import of compute_run_gated_actions moved above
  compute_run_shas so both calls share one try. Correction to D4's
  wording: the code turns a missing import spec for the emitted module
  into CompiledTraceError, not every load failure; an error while the
  module executes or builds its runtime propagates. The docstring says
  exactly that, and also names the two argument checks (an empty
  source, a max_cycles below 1) that D4 left out.
- pyflakes reports smt_emit.py's unused `field` import. It predates
  this unit (line 39 at 1bcbe53) and is not an undefined name.
- Kill criterion 20.6, measured in the container with the shipped table
  (sha256 1f0a3ede...) at 2026-09-22: 4 of the 12 shipped templates
  emit, with spec sha256 equal before and after; the other 8 stop
  earlier with a plain EmitError, identical before and after. None
  reaches the pricing refusal, so the templates exercise only the
  unchanged path. The code patch repeats this comparison on Server A.
- Measured in the container at 1bcbe53 plus section 20: red 22 of 22
  for the reasons in 20.5 and controls 7 of 7; green 29 of 29; the
  seven tests of 20.4 green; suite 3124 passed, 13 skipped, 0 failed;
  regression harness 0 diffs; inserted lines ASCII. On Server A at
  14bcf22 the red gate matched by set and by reason, 22 red and 7 green.

<!-- __s369_sec21_v1__ -->
## 21. S369 measurements (broad-catch callers on 5.85.0, the deepseek-r1 cliff), no code

Basis: the Server A RULE 0 at 2026-09-22 11:06:06Z read HEAD 1ec01c0 =
origin/main, tree clean, 5.85.0 on A and B, suite 3125 passed and 12
skipped. The probe ran in a container clone of GitHub main 84b3ef8,
which is 1ec01c0 plus three commits of the S368 lane that touch only
docs/GLM_SUPERSESSION_DESIGN.md. The 24 file sha256 values the Server A
RULE 0 printed matched the clone. The caller files match section 20's
basis: cli_verify.py bbc564f5..., cli_emit_smt.py 63b10a9c...,
run_shas.py 89a22aca..., cli_conformance.py 9accb6a4...,
dossier_spec.py bccabbaa..., cli_dossier.py 5aff4f93...,
nous_ast_runner.py 5e3ae532..., verifier.py 9c5e1e89...,
nous_api_server.py 19d726d5..., cli.py 998b052d...; smt_emit.py
a0d64bcd..., pricing.py 0c12c924..., pricing/defaults.toml 58ffc6fa....
Environment: Python 3.12.3, lark 1.3.1, pydantic 2.13.5, httpx 0.28.1,
cryptography 46.0.7, fastapi 0.141.1, z3 4.16.0; Server A's own
environment was not used. Every case ran in its own process with its
own HOME and working directory under libfaketime 0.9.10 (FAKETIME
"@<date>", monotonic clock not faked). A guard in the same environment
printed the clock, the working directory, HOME and the pricing table
the case resolved. CLI cases called cli.main() as the console script
does; /v1 cases went through FastAPI's TestClient. Nothing ran against
a provider. Probe files, sha256: probe_s369.py 05c98226...,
api_case.py 872d1a5a..., guard_case.py d3c41aef..., fixture.toml
1fa5ba87..., rows.jsonl 75e45a89....

### 21.1 What was open

- 20.3 D5 gave the output of the callers that catch broadly by
  construction; the S367 handoff (section 5) says they were not
  re-probed after the change, and only `nous run --emit-trace` is
  pinned by a test.
- The 5.85.0 CHANGELOG gives `nous conformance verify` exit 2 from
  code reading.
- 20.2 gave the `nous dossier` command line by reading; only the
  library call was run.

### 21.2 Broad-catch callers, measured

Fixture table (file 1fa5ba87..., canonical d99997ee...) with a priced
model and one model of each refused kind, clock 2026-09-22 12:00Z. For
every caller the priced control reached and passed the emit stage, and
every refused row names its model and its cause.

| caller | missing, removed, per-hour, stale |
|---|---|
| `nous conformance verify` and `certify` | exit 2, "PRECONDITION ERROR: UnpriceableSmtModel: soul 'A': <cause>" |
| `nous dossier-spec` | exit 1, "ERROR: dossier-spec build failed: SMT emit failed (UnpriceableSmtModel): soul 'summarizer': <cause>" |
| POST /v1/skill/export with with_dossier | 422 SKILLEXPORT001, "SMT emit failed (UnpriceableSmtModel): soul 'http_get': <cause>" |
| POST /v1/run with emit_trace | 422 RUN001, "soul 'A': <cause>", no double quote |
| `nous run --emit-trace` | exit 1, "Runtime error: soul 'A': <cause>" |

`nous dossier`: manifests signed at 2026-09-22 for a model removed
after 2026-09-23 and for a model verified 2026-06-29, built at
2026-10-02 12:00Z: exit 3, "ERROR: unexpected failure:
UnpriceableSmtModel: soul 'A': <cause>" for both. The control, signed
at 2026-09-22 and built at 2026-10-02 like them, exited 0 with its
dossier.

No command printed a traceback and no route returned 500. D5 holds for
every row. D5 wrote "soul ..." for the two skill paths without naming
the soul; the name printed is the soul of the translated program (21.5
F2).

### 21.3 deepseek-r1 at its cliff, measured

Shipped table (canonical 1f0a3ede...), a program whose one soul has
mind deepseek-r1, and the same program with deepseek-flash as the
control. Ten callers: `nous verify --smt`, `nous emit-smt`, `nous
governance ledger --source`, `nous conformance verify` and `certify`,
`nous dossier-spec`, POST /v1/skill/export, POST /v1/run with
emit_trace, `nous run --emit-trace`, and `nous dossier` on manifests
signed at 2026-09-27.

- 2026-09-27 12:00Z: every caller passes the emit stage for both
  models. deepseek-r1 is 90 days old, a warning and not a refusal.
- 2026-09-28 00:00:30Z: every caller refuses deepseek-r1 with "model
  'deepseek-r1' pricing too old for --smt: verified 91 days ago;
  exceeds 90-day threshold for --smt mode", in the form 21.2 gives for
  that caller, or D3's for the other three: `nous verify --smt` and
  `nous emit-smt` exit 3 with "ERROR: cannot emit SMT for prog.nous:"
  then "soul 'A': <cause>", and `nous governance ledger --source` exit
  1 with "REFUSED: --source emit failed: soul 'A': <cause>".
  deepseek-flash passes in all ten.
- The rule is pricing.py:402: refused when age > 90, where age is the
  UTC date minus verified_date. The first refused date is 2026-09-28
  by the clock of the host that runs the command.

### 21.4 Checks on the probe

- A refused row counts only when its caller's control passed at the
  same clock: 37 controls and 36 refusals, none void and none
  mismatched.
- The checks were shown to fail on a wrong cause, a wrong exit code,
  a guard clock on the wrong day and two simulated 5.84.0 forms: the
  KeyError text inside double quotes from `nous run`, and the untyped
  "PRECONDITION ERROR: ValueError: ..." from conformance.
- One control failed on the first run and its rows were replaced: the
  dossier case lacked cost.farkas.json, which `nous verify --smt`
  writes beside the manifest. With every signing output copied, the
  control built its dossier.

### 21.5 Findings and decisions

- F1 `nous dossier` reports an expected refusal as "unexpected
  failure" with exit 3; the cli_dossier.py docstring defines exit 3 as
  an argument error or missing input. From 2026-09-28 this is
  reachable for any manifest that names deepseek-r1 and was signed on
  or before 2026-09-27. Recorded under D7; not changed here.
- F2 `nous dossier-spec` and POST /v1/skill/export name the soul of
  the program translated from the skill, which is a tool name: for a
  source whose soul is Scanner the route printed 'http_get'. Recorded;
  not changed here.
- F3 Read in pricing.py: staleness_status returns "ok" for
  pricing_model "free", so a free entry never reaches the --smt age
  refusal. The two OpenRouter ":free" entries dated 2026-09-19 and
  local-ollama start no clock, as the table's S363 comment says.
- F4 Read in pricing/defaults.toml, not run: of the four entries with
  verified_date 2026-06-29 only deepseek-r1 is newly refused on
  2026-09-28. deepseek-chat carries removed_after 2026-07-24,
  llama-3-3-70b-local is per_hour and local-ollama is free.
- D1 No code changes for the callers that catch broadly: D5 holds as
  measured.
- D2 No test is added here. A test that pins 21.2 changes the suite
  count and the floor and is a unit of its own.
- D3 deepseek-r1 is not touched.

This section records how refusals are reported. No claim class
changes.

<!-- __s369_sec22_v1__ -->
## 22. S369 decisions (D7: `nous dossier` calls an expected refusal "unexpected failure"), written before the code

Basis: HEAD 9fbab5e = origin/main, which is section 21 on top of the
S368 lane's 84b3ef8. Code read and run in a container clone of 9fbab5e
in the environment of section 21. File sha256 at read time: this
document 06e0a6c4..., cli_dossier.py 5aff4f93..., dossier.py
a5175c98..., dossier_spec.py bccabbaa..., smt_emit.py a0d64bcd....

### 22.1 Behaviour today

- build_dossier (dossier.py:651) verifies the manifest's signature,
  compares the source sha256 with the manifest and finds the pricing
  table by the manifest's pricing_sha256, then calls emit_smt once
  (dossier.py:718) with today=None, so emit_smt takes the UTC date of
  the build. Read, not run: source and table are the ones that were
  signed, so a model missing from the table or billed per hour would
  have refused when `nous verify --smt` produced the manifest. Only the
  two kinds that depend on the date reach this call: a model removed
  since the signing, and a model whose verified_date has passed 90
  days.
- build_dossier does not catch the resulting UnpriceableSmtModel. The
  catch-all at cli_dossier.py:87 prints "ERROR: unexpected failure:
  UnpriceableSmtModel: soul 'A': <cause>" and exits 3 (21.2, measured
  for both kinds; 21.3, measured for deepseek-r1 at 2026-09-28).
- The cli_dossier.py docstring gives exit 1 for a failed validation and
  exit 3 for an argument error or missing input. dossier-spec, the
  other dossier builder, refuses the same cause with exit 1 and "SMT
  emit failed (UnpriceableSmtModel): soul ..." (dossier_spec.py:203).
- build_dossier has one caller outside the tests, cli_dossier's
  cmd_dossier. llm_guard_adapter.py, guardrails_adapter.py and
  santander_adapter.py each define a build_dossier of their own and do
  not call this one.

### 22.2 Decisions

- D1 build_dossier types the refusal at its source. An EmitError from
  its one emit_smt call is raised again, `from` the original, as
  DossierError "SMT emit failed (<type>): <message>", the text
  dossier_spec.py:203 uses. UnpriceableSmtModel is an EmitError, so the
  message reads "SMT emit failed (UnpriceableSmtModel): soul 'A':
  <cause>". Only EmitError is caught; any other exception from that
  call propagates as before.
- D2 cli_dossier.py does not change. Its DossierError branch
  (cli_dossier.py:69) prints "ERROR: dossier build failed: <message>"
  and exits 1. The catch-all keeps exit 3 and "unexpected failure" for
  every error that is still unexpected.
- D3 What is refused does not change. A manifest whose model has since
  been removed or aged past 90 days still gets no dossier; the refusal
  now reads "ERROR: dossier build failed: SMT emit failed
  (UnpriceableSmtModel): soul 'A': <cause>", exit 1. A build that
  succeeds is byte-identical: only the path where emit_smt raises
  changes.
- D4 Not decided here; for the operator. build_dossier judges --smt
  freshness at the build date, not at the date the manifest was
  signed, so a manifest verified inside the 90 days cannot be packaged
  once they have passed, although its source, table and spec are
  unchanged (21.3). Passing the manifest's signing date as today would
  make the outcome of a build depend on its inputs only, not on the
  clock. Against it: timestamp_utc is asserted by the signer,
  and a model removed after the signing would no longer stop a build.
  D1 holds either way.
- D5 deepseek-r1 is not touched.
- D6 Release 5.85.1 before 2026-09-28. Its CHANGELOG states that
  5.85.0's first known limit no longer holds. No new module; codegen,
  templates/trading_floor.py and the regression baseline do not move.

### 22.3 Blast radius, measured

A log-only hook at build_dossier's emit_smt call, in a copy of the tree
installed editable so that the `nous` command and subprocess tests
loaded it, recorded every exception from that call with the current
test id. Its control, a test that must reach the refusal, recorded one
UnpriceableSmtModel event. The full suite on the copy recorded none:
3120 passed, 14 skipped, and 3 failed: three tests in
test_s334_badge_no_version.py that need a .git directory the copy did
not have. No existing test reaches the changed path. The skipped
tests are 4 live tests, 6 ML-DSA tests, a git-checkout guard, a
trusted_root.json test, a v2ts pair test and a world-less source test.

### 22.4 Red first

tests/test_s369_dossier_refusal_typed.py, written and failing before
any code, with HOME and the working directory isolated and a fixture
table holding a priced model verified 5 days before the run, a model
removed the day after the run and a model verified 85 days before the
run. Manifests are signed by `nous verify --smt` on the real clock; the
build moves smt_emit's clock 10 days forward.

- Red (4), for each of removed and stale: build_dossier with today 10
  days on raises DossierError whose message starts "SMT emit failed
  (UnpriceableSmtModel): soul 'A': ", names the model and has
  UnpriceableSmtModel as __cause__; `nous dossier` with the clock 10
  days on exits 1 with "ERROR: dossier build failed: SMT emit failed
  (UnpriceableSmtModel): soul 'A': " and prints neither "unexpected
  failure" nor a traceback.
- Controls (5), green before and after: the priced model builds on the
  day it is signed, through build_dossier and through `nous dossier`;
  it builds with the clock 10 days on; a source changed after signing
  still exits 1 with "source.sha256 mismatch"; a failure inside
  build_dossier that is not an EmitError still exits 3 with "ERROR:
  unexpected failure".

The red gate compares the failed test ids with the red set and the
passed ids with the controls, and reads each failure's reason from
--junitxml (FG-S365-B, FG-S366-B, FG-S367-D).

### 22.5 Kill criteria

- If the green run on Server A fails any test outside the new file,
  restore and measure before any retry.
- If any existing dossier test's output files change, D3 is wrong;
  record it here before the code changes again.
- The regression harness must show 0 diffs.
- If 5.85.1 cannot reach PyPI, Server A and Server B before
  2026-09-28, record that here; nothing else changes.
