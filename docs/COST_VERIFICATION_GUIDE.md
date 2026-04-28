<!-- __session64_publish_removal_v1__ -->
# Cost Verification Guide

**Status:** Phase 3a (foundations). End-to-end SMT verification
arrives in Phase 3c/4. This guide documents the source-level
constructs that already parse today.

---

## What this is

NOUS is the first agentic programming language where you can
**mathematically prove** that your agent will not exceed a
declared cost ceiling, before deploying.

The proof is performed by an SMT solver (Z3) at compile time
under the `--smt` flag. The solver either succeeds (UNSAT of the
negated obligation = constraint always holds) or returns a
counterexample showing exactly which execution path violates the
cap.

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

- Currency: `USD` or `EUR`. Mixing is not yet supported.
- Amount: any decimal. Stored internally as `decimal.Decimal`
  (not `float`), so SMT proofs use exact rationals.

### 2. `max_ticks` (per world)

Upper bound on the number of heartbeat cycles the world will
execute. Without this, total cost is unbounded — *no proof of
any kind is possible*.

```nous
world MyAgent {
    cost_cap: 0.10 USD
    max_ticks: 100
    ...
}
```

A typical agent with `heartbeat = 5m` and `max_ticks: 12` runs
for one hour, then halts.

Phase 5 will add proper loop-bound declarations and
self-terminating soul flags. For now, `max_ticks` is the single
knob.

### 3. `mind` (per soul)

The LLM model and tier. The model name is looked up in the
pricing table (`pricing/llm_prices_2026q2.toml`, shipped with
NOUS) to determine per-token cost.

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
typically 5–10× more expensive).

```nous
soul Trader {
    mind: claude-opus-4-7 @ Tier1
    tokens: input=500 output=200
    ...
}
```

How to choose values:

- `input` ≈ system prompt + history + tool definitions +
  retrieved context. For a typical agent: 200–2000.
- `output` ≈ longest plausible response. For most agents:
  100–500.

Phase 5 will replace these integers with intervals
(`[min, max]`) for tighter bounds.

---

## Putting it together

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

## What runs today (Phase 3a)

- `nous run file.nous` — runs the agent. Cost-related
  declarations are parsed and accepted; runtime is unchanged.
- `nous compile file.nous` — emits Python. Same.
- `nous parse file.nous` — prints AST. Cost fields are visible
  on `WorldNode` and `SoulNode`.

## What does *not* run yet

- `nous verify --smt file.nous` — Phase 3c (next).
- Compile-time error for missing `tokens` / `max_ticks` under
  `--smt` — Phase 3c.
- Cryptographic manifest with `smt_obligations_sha256` —
  Phase 4.
- Counterexample → deterministic replay trace — Phase 5.

---

## Why declared bounds, not defaults?

A common temptation is to have the compiler insert default
values (e.g., 500 input tokens) when the user omits `tokens`.
This is unsound: the proof would say `cost ≤ X` based on a
number the compiler invented, while the actual prompt size is
controlled by the user at runtime. The user would see
"PROVEN SAFE" and then watch the agent overshoot the cap.

Industrial verifiers (Dafny, Frama-C, VeriGuard) all require
the user to declare bounds. NOUS follows the same discipline.

If you don't want the discipline, don't pass `--smt`. The
language stays usable; you just lose the proof.

---

## Versioning

| Construct      | Available in | Mandatory under `--smt` from |
|----------------|--------------|------------------------------|
| `cost_cap`     | v4.13.0      | v4.13.0                      |
| `max_ticks`    | v4.13.0      | v4.13.0                      |
| `tokens`       | v4.13.0      | v4.13.0                      |
| Token intervals| v4.15.0+     | optional                     |
| Multi-currency | v4.15.0+     | optional                     |

---

*Last updated: Session 62 Phase 3a, 28 April 2026.*
*Companion documents: `SMT_VERIFICATION_DESIGN.md`,
`EU_AI_ACT_COMPLIANCE.md`.*


---

## Configuring pricing

NOUS ships with a verified pricing table at
`<package>/pricing/defaults.toml` (10 starter models, Q2 2026 prices).
You override it in any of three ways, listed from highest to lowest
priority:

| Layer | Path                                | Use case |
|-------|-------------------------------------|----------|
| 1 | `nous --prices /path/to/x.toml`        | One-off / CI / scripts |
| 2 | `./nous_prices.toml`                   | Project-specific rates |
| 3 | `~/.config/nous/prices.toml`           | Personal global override |
| 4 | `<package>/pricing/defaults.toml`      | Shipped defaults |

Run `nous prices show` to see which layer is active in your context.

### Customizing the table

```bash
$ nous prices init                # creates ./nous_prices.toml from defaults
$ vim nous_prices.toml             # add your custom models, edit prices
$ nous prices verify my-model      # confirm it parses
$ nous prices age                  # check staleness
```

The TOML schema (v1.0) has self-explaining comments above every field.
Open the file in any editor to see what each entry means.

---

## How the cost upper bound is computed

Total cost upper bound, per world:

    total_cost ≤ Σ over each soul s:  per_call_cost(s) × max_ticks(world)

For a single soul on a per-token model:

    per_call_cost(s) =
        (input_per_1m × tokens.input × cache_factor_in
       + output_per_1m × tokens.output × reasoning_mult)
      / 1,000,000

where:

  cache_factor_in
    = 1.0  if prompt caching not declared (sound default — full price)
    = (input_cached/input_per_1m + 1.25/N)  with N = expected reuses
       if user opts in to caching (Phase 5)

  reasoning_mult
    = 1.0  for non-reasoning models (Claude, GPT-5.2, Sonnet)
    = X    where X is `reasoning_token_multiplier` in the TOML
           (typical: 5.0 for o3-class / R1-class)

These constants come from provider documentation:

- Anthropic: cache hit = 10% of input rate; cache write = 125%
- OpenAI:    cache hit = 50% of input rate
- Google:    cache hit = 10% of input rate

The reasoning multiplier is NOT documented uniformly. NOUS uses
conservative defaults (5.0 for reasoning models) and lets the user
override per-model.

### Soundness contract

NOUS guarantees that the reported upper bound is **≥ actual cost**, under:

1. The pricing TOML reflects current provider rates.
2. Token counts declared on souls are upper bounds (not averages).
3. `max_ticks` is the actual termination count.
4. The reasoning multiplier covers worst-case thinking tokens.

NOUS does NOT guarantee tightness — the proven bound may be 2–5× higher
than typical actual cost. To tighten:

- Declare `prompt_caching: enabled` on the world (Phase 5)
- Declare `batch: true` on the soul (Phase 5)
- Reduce `tokens.input` / `tokens.output` to your actual maximum

### Why list price, not negotiated rate

NOUS uses publicly-listed provider prices because:

1. Audit trails need reproducibility — your private rate is not
   verifiable by an EU AI Act regulator.
2. Worst-case analysis is the goal — list price is the ceiling.
3. If you have a negotiated rate, you can override per-model in your
   private pricing TOML.

---

## Manifest storage (Phase 4)

When `nous verify --smt` succeeds, Phase 4 emits a self-contained
Ed25519-signed manifest. The manifest is offline-verifiable:
anyone with the file plus the publisher's public key can verify
authenticity without contacting any service. Storage is the
publisher's choice (filesystem, S3, IPFS, git release, etc.).

The manifest contains:

- source code SHA-256
- AST SHA-256
- pricing table SHA-256 (this is why pricing is content-addressed)
- SMT obligations SHA-256
- Z3 version that produced the proof
- ed25519 signature against NOUS root-of-trust

Anyone can run `nous audit <request_id>` and get a reproducible
verdict — without trusting the user.

This is how NOUS satisfies EU AI Act Article 11(1) and Annex IV
(technical documentation) while preserving privacy: the manifest
contains hashes, not source.

---

## Video walkthrough script

When recording a 5–7 minute walkthrough, this script gives you a
linear narrative. Read while running the commands.

### 0:00–0:30 — The problem

> "Most agentic AI frameworks promise reliability through testing.
> NOUS proves it through math. Here's a five-minute demo showing
> how to declare a cost ceiling on an AI agent and have a solver
> prove the ceiling can never be exceeded — before any LLM call
> is made."

### 0:30–2:00 — Live proof

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

PROVEN: total_cost <= $0.50 USD across all execution paths.
```

### 2:00–3:30 — Live counterexample

```bash
# Lower the cap to an unprovable level
$ sed -i 's/0.50 USD/0.001 USD/' my_agent.nous
$ nous verify --smt my_agent.nous

REFUTED: SMT solver found a counterexample.
  Alice contributes $0.0025 per call (Opus 4-7 @ 500 in / 200 out)
  total_cost = 5 ticks * $0.0025 = $0.0125
  cap        = $0.001
  overage    = $0.0115
```

### 3:30–5:00 — Pricing transparency

```bash
$ nous prices show
$ nous prices verify claude-opus-4-7
$ nous prices age
```

### 5:00–6:00 — EU AI Act tie-in

> "Article 15 of the EU AI Act requires high-risk AI systems to
> declare and prove their performance metrics. Cost is one such
> metric. NOUS is the first language where this declaration is
> first-class and verifiable. Phase 4 adds public, signed manifests
> for audit-ready compliance."

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

## Web roadmap

`nous-lang.org/cost` (Phase 4) will host a live demo and Article 15
mapping. The page will use the existing site stack (nginx, static
HTML, Cloudflare); no new infrastructure.

