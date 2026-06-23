<!-- __session71_phase5b_step11_docs_v1__ -->
# Cost Verification Guide

**Status:** Phase 5b shipped (v5.0.0, 3 May 2026). End-to-end
SMT cost verification is live for both USD and EUR pricing
tables. Token-interval syntax and per-hour billing arrive in
Phase 5c.

---

## What this is

NOUS is the first agentic programming language where you can
**mathematically prove** that your agent will not exceed a
declared cost ceiling, before deploying.

The proof is performed by an SMT solver (Z3) at compile time
under the `--smt` flag. The solver either succeeds (UNSAT of
the negated obligation = constraint always holds) or returns a
counterexample showing exactly which execution path violates
the cap.

This is distinct from runtime monitoring: the verification
happens **before** any LLM call is made.

---

## The four declarations

A cost-verifiable NOUS program declares four things. All four
are required under `--smt`. Without `--smt`, the declarations
are accepted but ignored.

### 1. `cost_cap` (per world)

The total spending ceiling.

```nous
world MyAgent {
    cost_cap: 0.10 USD
    ...
}
```

- Currency: `USD` or `EUR`. Both are end-to-end verified as of
  v5.0.0. The pricing table currency must match the cap
  currency; otherwise compilation fails with a clear error
  (Phase 5a guard `_validate_currency_consistency`).
- Amount: any decimal. Stored internally as `decimal.Decimal`
  (not `float`), so SMT proofs use exact rationals.

### 2. `max_ticks` (per world)

Upper bound on the number of heartbeat cycles the world will
execute. Without this, total cost is unbounded -- no proof of
any kind is possible.

```nous
world MyAgent {
    cost_cap: 0.10 USD
    max_ticks: 100
    ...
}
```

A typical agent with `heartbeat = 5m` and `max_ticks: 12` runs
for one hour, then halts.

Phase 5c will add token-interval declarations and per-hour
billing. For now, `max_ticks` is the single termination knob.

### 3. `mind` (per soul)

The LLM model and tier. The model name is looked up in the
pricing table (see "Configuring pricing" below) to determine
per-token cost.

```nous
soul Trader {
    mind: claude-opus-4-7 @ Tier1
    ...
}
```

If the model name is not in the pricing table, compilation
under `--smt` will fail with a clear error.

### 4. `tokens` (per soul)

Upper-bound token count per LLM call. Required because input
tokens and output tokens are priced differently (output is
typically 5x to 10x more expensive).

```nous
soul Trader {
    mind: claude-opus-4-7 @ Tier1
    tokens: input=500 output=200
    ...
}
```

How to choose values:

- `input` = system prompt + history + tool definitions +
  retrieved context. For a typical agent: 200 to 2000.
- `output` = longest plausible response. For most agents:
  100 to 500.

Phase 5c will replace these integers with intervals
(`[min, max]`) for tighter bounds.

---

## Putting it together (USD)

```nous
world TradingFloor {
    cost_cap: 0.50 USD
    max_ticks: 5

    soul Trader {
        mind: claude-opus-4-7 @ Tier1
        tokens: input=500 output=200
        instinct {
            speak buy_order(symbol="ACME", qty=10)
        }
    }

    soul Analyst {
        mind: claude-haiku-4-5 @ Tier3
        tokens: input=300 output=150
        instinct {
            speak market_brief(summary="ok")
        }
    }
}
```

This file ships at `templates/cost_cap_with_souls.nous` and is
exercised by the regression suite.

---

## Putting it together (EUR, v5.0.0)

The same program shape works against an EUR pricing table:

```nous
world TradingFloorEUR {
    cost_cap: 0.50 EUR
    max_ticks: 5

    soul Trader {
        mind: mistral-large-2 @ Tier1
        tokens: input=500 output=200
        instinct {
            speak buy_order(symbol="ACME", qty=10)
        }
    }
}
```

To compile this, point `--prices` at the EUR example table or
any custom EUR table:

```bash
$ nous verify --smt my_eur_agent.nous \
    --prices /opt/aetherlang_agents/nous/pricing/eur_example.toml
```

The shipped example `pricing/eur_example.toml` declares four
illustrative Mistral models (large-2, medium-3, small-3, plus
a local-ollama-eur entry) priced in EUR per 1 000 000 tokens.
**Values are explicitly marked illustrative**; verify against
the provider before any production use.

### Worked example: mistral-small-3 at 0.50 EUR cap

```
input_per_1m  = 0.20 EUR
output_per_1m = 0.60 EUR
tokens.input  = 100
tokens.output = 50

per_call_cost = (0.20 * 100 + 0.60 * 50) / 1 000 000
              = 50 / 1 000 000
              = 5e-5 EUR

max_ticks  = 1
total_cost = 5e-5 EUR

cap = 0.50 EUR  -> 5e-5 << 0.50  -> Z3 UNSAT (proven)
cap = 1e-7 EUR  -> 5e-5 >  1e-7  -> Z3 SAT   (counterexample)
```

The currency-mismatch matrix (enforced by Phase 5a):

| Pricing currency | Cap currency | Verdict     |
|------------------|--------------|-------------|
| USD              | USD          | OK          |
| EUR              | EUR          | OK (v5.0.0) |
| USD              | EUR          | REJECTED    |
| EUR              | USD          | REJECTED    |

---

## What runs today (v5.0.0)

- `nous run file.nous` -- runs the agent.
- `nous compile file.nous` -- emits Python.
- `nous parse file.nous` -- prints AST.
- `nous verify file.nous` -- structural plus governance lint.
- `nous verify --smt file.nous` -- end-to-end SMT proof under
  Z3, currency-aware, both USD and EUR. Emits an
  Ed25519-signed manifest by default; `--no-manifest` to skip.
- `nous verify --smt --smt-margin 10 file.nous` -- proves
  total_cost <= (cap * 90 / 100) for a 10 percent safety
  margin.
- `nous emit-smt file.nous` -- prints the SMT-LIB 2.6 source
  of the obligation without invoking Z3.
- `nous prices show / verify / age / init / upgrade` -- inspect
  and manage the pricing table.
- `nous dossier file.nous` -- emit an EU AI Act Annex IV
  compliance bundle (requires an adjacent `.manifest.json`
  produced by a successful `verify --smt` run).

## What does NOT run yet

- Token-interval syntax `tokens.input: [100, 500]` -- Phase 5c.
- Per-hour billing SMT (`expected_runtime_hours: 2.5`) --
  Phase 5c.
- `nous prices fetch <provider>` for live price retrieval --
  Phase 6.
- In-browser Z3 WASM demo at `nous-lang.org/cost` -- planned.

---

## Why declared bounds, not defaults?

A common temptation is to have the compiler insert default
values (e.g. 500 input tokens) when the user omits `tokens`.
This is unsound: the proof would say `cost <= X` based on a
number the compiler invented, while the actual prompt size is
controlled by the user at runtime. The user would see
"PROVEN SAFE" and then watch the agent overshoot the cap.

Industrial verifiers (Dafny, Frama-C, VeriGuard) all require
the user to declare bounds. NOUS follows the same discipline.

If you don't want the discipline, don't pass `--smt`. The
language stays usable; you just lose the proof.

---

## Versioning

| Construct          | Available in | Mandatory under `--smt` from |
|--------------------|--------------|------------------------------|
| `cost_cap` (USD)   | v4.13.0      | v4.13.0                      |
| `cost_cap` (EUR)   | v5.0.0       | v5.0.0                       |
| `max_ticks`        | v4.13.0      | v4.13.0                      |
| `tokens` (scalar)  | v4.13.0      | v4.13.0                      |
| `--smt-margin`     | v4.16.0      | optional                     |
| Pricing schema v2  | v5.0.0       | recommended                  |
| Token intervals    | Phase 5c     | optional                     |
| Per-hour billing   | Phase 5c     | optional                     |

---

## Configuring pricing

NOUS ships with a verified pricing table at
`<package>/pricing/defaults.toml` (11 starter models, Q2 2026
prices, schema v2.0). An EUR-native example is shipped
alongside at `<package>/pricing/eur_example.toml` (4 models).

You override the defaults in any of three ways, listed from
highest to lowest priority:

| Layer | Path                                | Use case |
|-------|-------------------------------------|----------|
| 1     | `nous --prices /path/to/x.toml`     | One-off / CI / scripts |
| 2     | `./nous_prices.toml`                | Project-specific rates |
| 3     | `~/.config/nous/prices.toml`        | Personal global override |
| 4     | `<package>/pricing/defaults.toml`   | Shipped defaults |

Run `nous prices show` to see which layer is active in your
context.

### Customizing the table

```bash
$ nous prices init                # creates ./nous_prices.toml from defaults
$ vim nous_prices.toml            # add models, edit prices, set _currency
$ nous prices verify my-model     # confirm a single model parses
$ nous prices age                 # check staleness across all entries
```

### Migrating from schema v1.0 to v2.0 (v5.0.0)

In v5.0.0, the per-token rate fields on `PricingEntry` dropped
their `_usd` suffix to become currency-agnostic. The shipped
default and the example tables are already v2.0. Any custom
table written against v4.18.0 or earlier loads under v5.0.0
with a single `DeprecationWarning` per file load (the loader
auto-translates v1.0 -> v2.0 in memory). To migrate the file
on disk:

```bash
$ nous prices upgrade my_prices.toml -o my_prices_v2.toml
$ diff my_prices.toml my_prices_v2.toml
$ mv my_prices_v2.toml my_prices.toml
```

Or in place:

```bash
$ nous prices upgrade my_prices.toml --in-place
```

The migration tool preserves all comments, blank lines, and
formatting; only the renamed field tokens and the
`_schema_version` value change. The output is validated
against the v2.0 Pydantic model BEFORE the file is written, so
a migration that would produce invalid TOML aborts with the
source untouched.

Field rename map:

| v1.0 name                       | v2.0 name                   |
|---------------------------------|-----------------------------|
| `input_per_1m_usd`              | `input_per_1m`              |
| `output_per_1m_usd`             | `output_per_1m`             |
| `input_cached_per_1m_usd`       | `input_cached_per_1m`       |
| `input_cache_write_per_1m_usd` | `input_cache_write_per_1m`  |
| `hourly_cost_usd`               | `hourly_cost`               |

The per-table `_currency` field (defaults to `"USD"`) becomes
the single source of truth for currency. Set it explicitly to
`"EUR"` for EUR-native tables.

---

## How the cost upper bound is computed

Total cost upper bound, per world:

    total_cost <= sum over each soul s of:
                    per_call_cost(s) * max_ticks(world)

For a single soul on a per-token model:

    per_call_cost(s) =
          (input_per_1m  * tokens.input  * cache_factor_in
         + output_per_1m * tokens.output * reasoning_mult)
        / 1 000 000

where:

  cache_factor_in
    = 1.0  if prompt caching not declared (sound default --
           full price)
    = (input_cached / input_per_1m + 1.25 / N) with N expected
           reuses, if user opts in to caching (Phase 5c)

  reasoning_mult
    = 1.0  for non-reasoning models (Claude, GPT-5.2, Sonnet)
    = X    where X is `reasoning_token_multiplier` in the
           TOML (typical: 5.0 for o3-class / R1-class)

These constants come from provider documentation:

- Anthropic: cache hit = 10 percent of input rate;
  cache write = 125 percent
- OpenAI:    cache hit = 50 percent of input rate
- Google:    cache hit = 10 percent of input rate

The reasoning multiplier is NOT documented uniformly. NOUS
uses conservative defaults (5.0 for reasoning models) and lets
the user override per-model.

### Soundness contract

NOUS guarantees that the reported upper bound is greater than
or equal to actual cost, under:

1. The pricing TOML reflects current provider rates.
2. Token counts declared on souls are upper bounds (not
   averages).
3. `max_ticks` is the actual termination count.
4. The reasoning multiplier covers worst-case thinking tokens.
5. The pricing table currency matches the cap currency
   (Phase 5a guard, hard-blocked at compile time).

NOUS does NOT guarantee tightness -- the proven bound may be
2x to 5x higher than typical actual cost. To tighten:

- Declare `prompt_caching: enabled` on the world (Phase 5c)
- Declare `batch: true` on the soul (Phase 5c)
- Reduce `tokens.input` / `tokens.output` to your actual
  maximum

### Why list price, not negotiated rate

NOUS uses publicly-listed provider prices because:

1. Audit trails need reproducibility -- your private rate is
   not verifiable by an EU AI Act regulator.
2. Worst-case analysis is the goal -- list price is the
   ceiling.
3. If you have a negotiated rate, you can override per-model
   in your private pricing TOML.

---

## Manifest storage (v5.0.0)

When `nous verify --smt` succeeds, NOUS emits a self-contained
Ed25519-signed manifest. The manifest is offline-verifiable:
anyone with the file plus the publisher's public key can
verify authenticity without contacting any service. Storage is
the publisher's choice (filesystem, S3, IPFS, git release,
etc.).

The manifest contains:

- source code SHA-256
- AST SHA-256
- pricing table SHA-256 (this is why pricing is
  content-addressed)
- SMT obligations SHA-256
- Z3 version that produced the proof
- Ed25519 signature against the publisher's public key

Anyone can run `nous dossier <source>` and produce an EU AI
Act Annex IV-aligned bundle from the manifest plus the source
plus the pricing table -- without trusting the user.

This is how NOUS satisfies EU AI Act Article 11 (technical
documentation), Annex IV (technical documentation contents),
and Article 12 (record-keeping with chained event logs) while
preserving privacy: the manifest contains hashes, not source.

---

## Sha-stability across schema versions (CLOSED window)

In v5.0.0 the `PricingTable.sha256()` canonical form changed
because of the v1.0 -> v2.0 schema rename. There were no
production dossiers in the wild at the moment v5.0.0 shipped,
so the sha-break has zero deployed impact. **The window for
free schema renames has now closed**: any future schema change
(v2.0 -> v2.1, v3.0, etc.) must be sha-stable, either purely
additive (new optional fields without renaming existing ones)
or via a versioned canonicalization function that preserves
hashes across versions.

A v1.0 file and its v2.0-equivalent migrated form **must**
produce identical sha256s. This is empirically locked by
`tests/test_pricing_v1_compat.py::test_sha256_v1_equals_v2_equivalent`.

---

## Video walkthrough script

When recording a 5 to 7 minute walkthrough, this script gives
you a linear narrative. Read while running the commands.

### 0:00 to 0:30 -- The problem

> "Most agentic AI frameworks promise reliability through
> testing. NOUS proves it through math. Here is a five-minute
> demo showing how to declare a cost ceiling on an AI agent
> and have a solver prove the ceiling can never be exceeded
> -- before any LLM call is made."

### 0:30 to 2:00 -- Live proof

```bash
$ cat my_agent.nous
world Trader {
    cost_cap: 0.50 USD
    max_ticks: 5
}
soul Alice {
    mind: claude-opus-4-7 @ Tier1
    tokens: input=500 output=200
}

$ nous verify --smt my_agent.nous
Loading pricing: /opt/.../pricing/defaults.toml (sha256 d23f54...)
Emitting SMT-LIB constraints... 8 assertions, 1 obligation
Running Z3 (timeout=30s)... unsat in 0.02s

PROVEN: total_cost <= 0.50 USD across all execution paths.
Manifest: my_agent.manifest.json (Ed25519, signed).
```

### 2:00 to 3:30 -- Live counterexample

```bash
# Lower the cap to an unprovable level
$ sed -i 's/0.50 USD/0.001 USD/' my_agent.nous
$ nous verify --smt my_agent.nous

REFUTED: SMT solver found a counterexample.
  Alice contributes 0.0025 USD per call (Opus 4-7 @ 500 in / 200 out)
  total_cost = 5 ticks * 0.0025 = 0.0125 USD
  cap        = 0.001 USD
  overage    = 0.0115 USD
```

### 3:30 to 5:00 -- Pricing transparency

```bash
$ nous prices show
$ nous prices verify claude-opus-4-7
$ nous prices age
```

### 5:00 to 6:00 -- EU AI Act tie-in

> "Article 15 of the EU AI Act requires high-risk AI systems
> to declare and prove their performance metrics. Cost is one
> such metric. NOUS is the first language where this
> declaration is first-class and verifiable. v5.0.0 ships
> end-to-end SMT proofs in both USD and EUR, plus
> Ed25519-signed manifests for audit-ready Annex IV
> compliance."

### Copy-paste recording commands

```bash
# Tab 1: terminal
cd ~/recordings && cat my_agent.nous
nous verify --smt my_agent.nous
sed -i 's/0.50 USD/0.001 USD/' my_agent.nous
nous verify --smt my_agent.nous
git checkout my_agent.nous
nous prices show
nous prices verify claude-opus-4-7
nous prices age

# Tab 2: editor showing my_agent.nous side-by-side
```

---

## Offline re-check: the cost-cap Farkas certificate

<!-- __s170_docs_verify_cost_v1__ -->

The `--smt` proof above runs once, at verify time, inside Z3. Since
v5.63.0 NOUS can also **emit** that proof as a standalone artifact and
**re-check** it later with no solver at all.

When the cap is provable, `nous verify --smt` writes `cost.farkas.json`:
a Farkas certificate -- a vector of non-negative multipliers that combine
the cost system's constraints into a numeric contradiction. If the
multipliers check out, no admissible execution under the declared per-call
token and tick estimates can reach the cap. The manifest records the
certificate's SHA-256 in `cost_farkas_sha256`.

The certificate then travels with every evidence surface: it is carried in
the Annex IV dossier, attested in the Verification Summary Attestation
(VSA), and packaged into the portable `.ndec` bundle.

To re-check it offline:

```
nous verify-cost cost.farkas.json
nous verify-cost cost.farkas.json --manifest manifest.json
```

`nous verify-cost` re-derives the refutation in exact rational arithmetic
-- no Z3, no model, no trust in the solver that produced it. This is the
certificate-checking discipline that SAT solvers (DRAT) and mixed-integer
solvers (VIPR) have used for over a decade: the prover emits a witness, and
a small independent checker re-verifies it.

**What it proves.** The certificate is a valid refutation, so under the
declared per-call estimates the cost cap holds. With `--manifest` it also
**evidences** that this is the certificate a signed manifest committed to.

**What it does not do.** It does not re-derive the cost model from your
source -- that is the online `nous verify --smt` path. It does not prove
your agent stayed within the declared estimates at runtime -- the signed
execution trace evidences that. "Proves" stays reserved for Z3 and Farkas;
NOUS is a monitor, not a guard.

**Exit codes.** `0` proven, `1` refuted, `2` precondition/error (file
missing, not a cost-cap certificate, or `--manifest` binding failure).

## Web roadmap

- `nous-lang.org/blog/` hosts the v5.0.0 release narrative
  alongside earlier release notes.
- `nous-lang.org/cost` (planned) will host an in-browser Z3
  WASM demo letting users edit a NOUS world block and see the
  proof verdict live.
- `nous-lang.org/prices/` (Phase 6) will host a community
  pricing registry with multi-provider live updates.

---

*Last updated: Session 71, 3 May 2026 (HEAD: post-`1a6dd1c`); offline cost-cert re-check (`nous verify-cost`) documented Session 170, 23 June 2026.*
*Companion documents: `SMT_VERIFICATION_DESIGN.md`,
`EU_AI_ACT_COMPLIANCE.md`.*
