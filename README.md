<!-- __session64_docs_accuracy_v1__ -->
# NOUS (Νοῦς) — The Living Language

**The first agentic programming language with formal cost-bound verification.**

```
  _   _  ___  _   _ ____
 | \ | |/ _ \| | | / ___|
 |  \| | | | | | | \___ \
 | |\  | |_| | |_| |___) |
 |_| \_|\___/ \___/|____/   v4.13.0
```

**Author:** Hlias Staurou (Hlia) · **Project:** Noosphere · **GitHub:** [contrario/nous](https://github.com/contrario/nous) · **Website:** [nous-lang.org](https://nous-lang.org)

---

## What is NOUS?

NOUS is a programming language for agentic AI systems where every program is:

- **Verifiable** — declare a `cost_cap` and Z3 proves at compile time that no execution path can ever exceed it.
- **Auditable** — every verified program emits an ed25519-signed manifest with full provenance (source SHA-256, pricing SHA-256, SMT spec SHA-256, solver name+version, verdict, timestamp).
- **Governable** — first-class `policy { on … signal … action … }` declarations are statically lintable (28 rules) and live-simulatable.
- **Self-evolving** — programs can observe their own execution, evaluate fitness, mutate DNA parameters, and self-heal within constitutional safety bounds.

NOUS transpiles to Python 3.11+ asyncio. The toolchain is a single PyPI package — no Java, no Docker, no LangChain/LlamaIndex/CrewAI dependencies.

---

## Why v4.13.0 matters

Every other agentic framework lets you set a "max budget" *at runtime* and abort when it's exceeded — by which point the spend has already happened. NOUS lets you **prove before you ship** that every reachable execution stays under the cap. The proof is mechanical (Z3), the cost model is auditable (signed pricing TOML with SHA-256), and the artefact (signed manifest) is verifiable by anyone holding your public key — making it directly useful for **EU AI Act Annex IV / Article 11(1)** technical documentation.

---

## Install

```bash
# Core toolchain
pip install nous-lang

# With SMT cost-bound verification (Z3 + ed25519 signing)
pip install 'nous-lang[smt]'

# With LSP server (VS Code / editor diagnostics)
pip install 'nous-lang[lsp]'

# Everything
pip install 'nous-lang[all]'
```

Requirements: Python 3.11+. The `[smt]` extra pulls `z3-solver>=4.15.0,<4.17.0` and `cryptography>=42,<47`.

---

## 60-second quick start

```bash
# 1. Initialise a project
mkdir my_world && cd my_world
nous prices init        # writes nous.prices.toml from shipped defaults
nous templates copy gate_alpha   # copies a working .nous program

# 2. Add a cost cap
cat > trading.nous <<'EOF'
world TradingFloor {
    cost_cap: 0.50 USD
    max_ticks: 5
}

soul Trader {
    mind: claude-opus-4-7 @ Tier1
    tokens: input=500 output=200
}

soul Auditor {
    mind: claude-haiku-4-5-20251001 @ Tier2
    tokens: input=200 output=100
}
EOF

# 3. Verify formally
nous verify trading.nous --smt
# → Verdict: PROVEN. Manifest written to trading.manifest.json.
```

If the cap is too tight, the verifier returns a counterexample with **constructive fix suggestions** ("raise cap to $0.74" / "reduce max_ticks to 3" / "Trader contributes 68% of worst-case spend").

---

## Core CLI

```bash
nous run file.nous              # compile + execute
nous compile file.nous          # → Python file
nous verify file.nous           # governance lint as build gate
nous verify file.nous --smt     # SMT cost proof + signed manifest
nous emit-smt file.nous         # SMT-LIB 2.6 (re-usable across solvers)

nous prices show                # active layered pricing table + SHA-256
nous prices init                # write nous.prices.toml in cwd
nous prices verify              # cross-check vs shipped defaults
nous prices age                 # how stale is each price entry

nous governance lint file.nous  # 28-rule static analysis
nous governance simulate ...    # what-if policy evaluation

nous templates list             # bundled templates
nous templates copy <name>      # copy a template into cwd
nous lsp                        # start LSP server (stdio)
nous version
```

---

## Language at a glance

```nous
world ExampleWorld {
    cost_cap: 1.00 USD              # ← formal SMT bound, v4.13.0
    max_ticks: 10                   # ← bound on cycles
    law CostCeiling = $0.10 per cycle
    law MaxLatency = 30s
    law NoLiveTrading = true
}

soul Sentinel {
    mind: claude-opus-4-7 @ Tier1
    tokens: input=1000 output=400   # ← SMT input, v4.13.0
    senses: market_feed, risk_oracle
    speaks: AlertChannel
    remembers: last_signal
}

policy on llm.response signal contains_phrase("absolutely") action log_only weight 0.3
```

---

## Architecture

| Layer       | Implementation                                              |
|-------------|-------------------------------------------------------------|
| Grammar     | Lark LALR (`nous.lark`), bilingual EN+GR, ~200 rules        |
| AST         | Pydantic V2 strict models, 50+ node types                   |
| Validator   | Constitutional law checker on AST                           |
| Pricing     | Layered TOML (CLI → project → user → package), SHA-256 audit |
| SMT emit    | Deterministic SMT-LIB 2.6, exact rationals (no floats)      |
| SMT solve   | Z3 wrapper + counterexample extraction + fix suggestions   |
| Manifests   | ed25519-signed JSON, Sigstore/SLSA-style provenance         |
| CodeGen     | AST → Python 3.11+ asyncio                                   |
| Runtime     | asyncio event loop + Noosphere integration                  |
| LSP         | stdio JSON-RPC, lint diagnostics with `source="nous.lint"`  |

---

## The signed-manifest contract

When `nous verify --smt` returns `PROVEN`, it writes a JSON manifest:

```json
{
  "version": "1.0",
  "source_path": "trading.nous",
  "source_sha256": "...",
  "pricing_sha256": "...",
  "smt_sha256": "...",
  "solver": "z3",
  "solver_version": "4.15.2",
  "verdict": "proven",
  "cost_cap": "0.50",
  "currency": "USD",
  "timestamp": "2026-04-28T14:38:33Z",
  "signature": "<base64 ed25519>",
  "public_key": "<base64 ed25519 pubkey>"
}
```

Anyone with the manifest and the publisher's public key can re-verify offline. Tamper-detection is built in. The verifier signing key lives at `~/.local/share/nous/keys/signing.key` (XDG, mode 0600, auto-generated; override with `--key-path`).

---

## Documentation

- [Cost Verification Guide](docs/COST_VERIFICATION_GUIDE.md) — end-to-end walkthrough
- [SMT Verification Design](docs/SMT_VERIFICATION_DESIGN.md) — soundness contract, Z3 pin rationale
- [EU AI Act Compliance](docs/EU_AI_ACT_COMPLIANCE.md) — Annex IV / Article 11(1) mapping

---

## Stats (v4.13.0)

| Metric              | Value                                       |
|---------------------|---------------------------------------------|
| Tests               | 264 passing                                 |
| Regression          | 57 templates, 0 baseline drift              |
| Parser throughput   | LALR (Lark), 3.3 ms/parse                   |
| Grammar rules       | ~200 (bilingual EN+GR)                      |
| AST node types      | 50+ Pydantic V2 models                      |
| New in v4.13.0      | `cost_cap`, `tokens`, `max_ticks`, `--smt`, signed manifests |

---

## License

See [LICENSE](LICENSE).

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

<!-- __session63_readme_v4_13_0__ -->
