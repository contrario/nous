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
