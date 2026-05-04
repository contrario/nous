<!-- __session71_readme_v500_v1__ -->
# NOUS (Nous) -- The Living Language

**The first agentic programming language with end-to-end formal cost-bound verification, in any currency the pricing table declares.**

```
  _   _  ___  _   _ ____
 | \ | |/ _ \| | | / ___|
 |  \| | | | | | | \___ \
 | |\  | |_| | |_| |___) |
 |_| \_|\___/ \___/|____/   v5.0.0
```

**Author:** Hlias Staurou (Hlia) | **Project:** Noosphere | **GitHub:** [contrario/nous](https://github.com/contrario/nous) | **Website:** [nous-lang.org](https://nous-lang.org)

---

## What is NOUS?

NOUS is a programming language for agentic AI systems where every program is:

- **Verifiable** -- declare a `cost_cap` in USD or EUR and Z3 proves at compile time that no execution path can ever exceed it.
- **Auditable** -- every verified program emits an Ed25519-signed manifest with full provenance (source SHA-256, AST SHA-256, pricing SHA-256, SMT obligations SHA-256, solver name+version, verdict, timestamp).
- **Annex IV-ready** -- `nous dossier` emits an EU AI Act Annex IV-aligned compliance bundle directly from the AST plus the signed manifest plus the pricing table.
- **Governable** -- first-class `policy { on ... signal ... action ... }` declarations, statically lintable (13 rule codes) and live-simulatable.
- **Deterministically replayable** -- every agent run produces a SHA-256-chained JSONL event log. `nous replay verify` validates chain integrity offline.
- **Self-evolving** -- programs can observe their own execution, evaluate fitness, mutate DNA parameters, and self-heal within constitutional safety bounds.

NOUS transpiles to Python 3.11+ asyncio. The toolchain is a single PyPI package -- no Java, no Docker, no LangChain / LlamaIndex / CrewAI dependencies.

---

## Why v5.0.0 matters

Every other agentic framework lets you set a "max budget" *at runtime* and abort when it is exceeded -- by which point the spend has already happened. NOUS lets you **prove before you ship** that every reachable execution stays under the cap. The proof is mechanical (Z3), the cost model is auditable (signed pricing TOML with SHA-256), and the artefact (signed manifest) is verifiable by anyone holding your public key -- making it directly useful for **EU AI Act Annex IV / Article 11(1)** technical documentation.

v5.0.0 adds end-to-end EUR cost verification. Earlier versions hard-blocked any cap currency other than USD; v5.0.0 lifts that block while preserving the Phase 5a currency-mismatch guard, so a USD pricing table with an EUR cap (or vice versa) is still rejected at compile time. The pricing TOML schema drops its `_usd` field-name suffix in favour of a per-table `_currency` declaration; existing v1.0 files load with one `DeprecationWarning` and migrate cleanly via `nous prices upgrade`.

---

## Install

```bash
# Core toolchain (cryptography is base, not optional)
pip install nous-lang

# With SMT cost-bound verification (adds Z3)
pip install 'nous-lang[smt]'

# With LSP server (VS Code / editor diagnostics)
pip install 'nous-lang[lsp]'

# Everything
pip install 'nous-lang[all]'
```

Requirements: Python 3.11+. The `[smt]` extra pulls `z3-solver`. `cryptography` (used for Ed25519 signing) is a base dependency since v4.17.0.

---

## 60-second quick start

```bash
# 1. Initialise a project
mkdir my_world && cd my_world
nous prices init                       # writes ./nous_prices.toml from defaults
nous templates extract cost_cap_basic  # copies a working .nous program

# 2. Verify formally
nous verify cost_cap_basic.nous --smt
# -> Verdict: PROVEN. Manifest written to cost_cap_basic.manifest.json.

# 3. Emit an Annex IV compliance dossier
nous dossier cost_cap_basic.nous
# -> bundles source, AST, manifest, pricing table, and Annex IV mapping
```

For EUR end-to-end verification, point `--prices` at an EUR pricing table:

```bash
nous verify --smt my_eur_agent.nous \
    --prices /path/to/eur_prices.toml
```

The shipped `pricing/eur_example.toml` declares four illustrative Mistral models priced in EUR per 1 000 000 tokens. **Values are explicitly marked illustrative**; verify against the provider before any production use.

---

## Core CLI

```bash
nous run file.nous              # compile + execute
nous compile file.nous          # -> Python file
nous verify file.nous           # governance lint as build gate
nous verify file.nous --smt     # SMT cost proof + signed manifest
nous verify file.nous --smt --smt-margin 10
                                # prove total_cost <= cap * 90/100
nous emit-smt file.nous         # SMT-LIB 2.6 source (re-usable across solvers)
nous dossier file.nous          # EU AI Act Annex IV compliance bundle

nous prices show                # active layered pricing table + SHA-256
nous prices init                # write nous_prices.toml in cwd
nous prices verify <model>      # detailed cost breakdown for one model
nous prices age                 # staleness report across all entries
nous prices upgrade <file>      # migrate v1.0 -> v2.0 schema (preserves comments)

nous governance lint file.nous  # static analysis (13 rule codes)
nous governance simulate ...    # what-if policy evaluation

nous replay verify <log>        # validate JSONL chain integrity
nous replay diff a.jsonl b.jsonl
                                # lockstep event-level diff

nous templates list             # list bundled templates (9 shipped)
nous templates show <name>      # print template source to stdout
nous templates extract <name>   # copy template into a directory
nous lsp                        # start LSP server (stdio)
nous version
```

The full `nous --help` lists 48 top-level subcommands; the above covers the most-used surface.

---

## Language at a glance

```nous
world ExampleWorld {
    cost_cap: 1.00 USD              // formal SMT bound, USD or EUR
    max_ticks: 10                   // bound on heartbeat cycles
    law CostCeiling = $0.10 per cycle
    law MaxLatency = 30s
    law NoLiveTrading = true
}

soul Sentinel {
    mind: claude-opus-4-7 @ Tier1
    tokens: input=1000 output=400   // SMT input
    senses: market_feed, risk_oracle
    speaks: AlertChannel
    remembers: last_signal
}

policy on llm.response signal contains_phrase("absolutely") action log_only weight 0.3
```

---

## Architecture

| Layer       | Implementation                                                       |
|-------------|----------------------------------------------------------------------|
| Grammar     | Lark LALR (`nous.lark`), 115 rules, bilingual EN+GR                  |
| AST         | Pydantic V2 strict models, 61 node types                             |
| Validator   | Constitutional law checker on AST                                    |
| Pricing     | Layered TOML (CLI > project > user > package), SHA-256 audit, schema v2.0, currency-agnostic |
| SMT emit    | Deterministic SMT-LIB 2.6, exact rationals (no floats)               |
| SMT solve   | Z3 wrapper + counterexample extraction + fix suggestions             |
| Manifests   | Ed25519-signed JSON, manifest schema v1.0, offline-verifiable        |
| Dossier     | EU AI Act Annex IV-aligned compliance bundle from AST + manifest     |
| CodeGen     | AST -> Python 3.11+ asyncio                                          |
| Replay      | SHA-256-chained JSONL event log, integrity-verifiable offline        |
| Runtime     | asyncio event loop + Noosphere integration                           |
| LSP         | stdio JSON-RPC, lint diagnostics with `source="nous.lint"`           |

---

## The signed-manifest contract

When `nous verify --smt` returns `PROVEN`, it writes a JSON manifest:

```json
{
  "schema_version": "1.0",
  "nous_version": "5.0.0",
  "smt_emit_version": "...",
  "source_path": "trading.nous",
  "source_sha256": "...",
  "ast_sha256": "...",
  "pricing_sha256": "...",
  "smt_obligations_sha256": "...",
  "solver": "z3",
  "solver_version": "...",
  "verdict": "proven",
  "cost_cap": "0.50",
  "currency": "USD",
  "timestamp": "2026-05-03T19:12:54Z",
  "signature": "<base64 ed25519>",
  "public_key": "<base64 ed25519 pubkey>"
}
```

Anyone with the manifest and the publisher's public key can re-verify offline. Tamper-detection is built in. The verifier signing key lives at `$XDG_DATA_HOME/nous/keys/signing.key` (mode 0600, auto-generated; falls back to `~/.local/share/nous/keys/signing.key` if XDG is unset; override with `--key-path`).

---

## EU AI Act compliance

NOUS targets EU AI Act conformity for the high-risk AI system requirements of Regulation (EU) 2024/1689. The compliance matrix lives in [`docs/EU_AI_ACT_COMPLIANCE.md`](docs/EU_AI_ACT_COMPLIANCE.md). Current coverage: 8 of 10 mapped articles fully covered, 1 planned, 1 out of scope.

Key article alignments:

- **Article 11 (Technical Documentation)** -- `nous dossier` emits an Annex IV-aligned bundle directly from the AST.
- **Article 12 (Record-Keeping)** -- SHA-256-chained JSONL replay logs, integrity-verifiable via `nous replay verify`.
- **Article 14 (Human Oversight)** -- `intervene`, `inject_message`, `block` policy actions plus governance simulator.
- **Article 15 (Accuracy / Robustness / Cybersecurity)** -- Z3 SMT proofs on every `cost_cap` declaration, currency-aware (USD + EUR), with Ed25519-signed manifests.
- **Article 17 (Quality Management)** -- 10-phase release pipeline, 394-test pytest floor, 57-template byte-identical regression harness.

---

## Documentation

- [Cost Verification Guide](docs/COST_VERIFICATION_GUIDE.md) -- end-to-end walkthrough for USD and EUR
- [SMT Verification Design](docs/SMT_VERIFICATION_DESIGN.md) -- soundness contract, Z3 pin rationale
- [EU AI Act Compliance](docs/EU_AI_ACT_COMPLIANCE.md) -- Annex IV / Article 11 mapping

---

## Contributing

NOUS is developed under a non-standard model: single maintainer, chat-driven, idempotent patch scripts, 10-phase release pipeline. External contributions are welcome but follow an "issue first, PR after we agree on shape" intake. See [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

Security issues should be reported via [GitHub Security Advisories](https://github.com/contrario/nous/security/advisories/new), not public issues.

---

## Stats (v5.0.0)

| Metric              | Value                                                            |
|---------------------|------------------------------------------------------------------|
| Tests               | 394 passing (PYTEST_FLOOR enforced)                              |
| Regression          | 57 templates, 0 baseline drift                                   |
| Shipped templates   | 9 (`templates/*.nous`)                                           |
| Grammar rules       | 115 (Lark LALR, bilingual EN+GR)                                 |
| AST node types      | 61 (Pydantic V2 strict)                                          |
| Lint rule codes     | 13 (L000 - L012, L100)                                           |
| CLI subcommands     | 48 (`nous --help`)                                               |
| Pricing schema      | v2.0 (currency-agnostic, per-table `_currency`)                  |
| Manifest schema     | v1.0 (Ed25519-signed, offline-verifiable)                        |
| New in v5.0.0       | EUR end-to-end SMT, `nous prices upgrade`, sha-stable v1->v2 migration |

---

## License

MIT. See [LICENSE](LICENSE).

## Changelog

See [CHANGELOG.md](CHANGELOG.md). Latest release: [v5.0.0](https://github.com/contrario/nous/releases/tag/v5.0.0) (3 May 2026).
