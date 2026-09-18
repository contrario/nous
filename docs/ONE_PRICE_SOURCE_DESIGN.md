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
