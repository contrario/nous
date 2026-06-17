# NOUS (Nous) -- The Living Language

[![PyPI version](https://img.shields.io/pypi/v/nous-lang.svg)](https://pypi.org/project/nous-lang/) [![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/contrario/nous/blob/main/LICENSE)

The first agentic programming language with end-to-end formal cost-bound verification, in any currency the pricing table declares, with cryptographically signed dossiers anchored to a public transparency log and verifiable by anyone offline.

```
  _   _  ___  _   _ ____
 | \ | |/ _ \| | | / ___|
 |  \| | | | | | | \___ \
 | |\  | |_| | |_| |___) |
 |_| \_|\___/ \___/|____/   v5.11.0
```

Author: Hlias Staurou (Hlia) | Project: Noosphere | GitHub: contrario/nous | Website: nous-lang.org

## What is NOUS?

NOUS is a programming language for agentic AI systems where every program is:

- **Verifiable** -- declare a `cost_cap` in USD or EUR and Z3 proves at compile time that no execution path can ever exceed it.
- **Auditable** -- every verified program emits an Ed25519-signed manifest with full provenance (source SHA-256, AST SHA-256, pricing SHA-256, SMT obligations SHA-256, solver name+version, verdict, timestamp).
- **Annex IV-ready** -- `nous dossier` emits an EU AI Act Annex IV-aligned compliance bundle directly from the AST plus the signed manifest plus the pricing table.
- **Rekor-anchored** -- since v5.3.0, optional `--anchor rekor` anchors emitted manifests into the public Sigstore Rekor transparency log via Path-beta dual signing (per-submission ECDSA-P-256 leaf, long-lived Ed25519 manifest signature preserved). Since v5.10.0 a Rekor v2 path (`--anchor rekor_v2`) targets the tile-backed Sigstore log with an RFC 3161 trusted timestamp over the leaf signature, all re-verifiable offline. External, third-party-auditable durability with zero NOUS-side trust assumption. See `docs/REKOR_ANCHOR.md` and `docs/REKOR_V2_MIGRATION.md`.
- **Publicly verifiable** -- since v5.4.0, any signed dossier can be verified by anyone via three independent paths: `POST /api/v1/verify-dossier` (browser convenience, no API key, rate-limited), `verify_offline.py` (canonical, single `cryptography` dependency), or `nous dossier verify` (full toolchain with SMT cost-cap re-check). See `docs/VERIFY_DOSSIER.md`.
- **Governable** -- first-class `policy { on ... signal ... action ... }` declarations, statically lintable (13 rule codes) and live-simulatable.
- **Deterministically replayable** -- every agent run produces a SHA-256-chained JSONL event log. `nous replay verify` validates chain integrity offline.
- **Self-evolving** -- programs can observe their own execution, evaluate fitness, mutate DNA parameters, and self-heal within constitutional safety bounds.

NOUS transpiles to Python 3.11+ asyncio. The toolchain is a single PyPI package -- no Java, no Docker, no LangChain / LlamaIndex / CrewAI dependencies.

## Why this matters

Every other agentic framework lets you set a "max budget" at runtime and abort when it is exceeded -- by which point the spend has already happened. NOUS lets you **prove before you ship** that every reachable execution stays under the cap. The proof is mechanical (Z3), the cost model is auditable (signed pricing TOML with SHA-256), and the artefact (signed manifest) is verifiable by anyone holding your public key -- making it directly useful for EU AI Act Annex IV / Article 11(1) technical documentation.

With v5.3.0 Rekor anchoring and v5.4.0 public verification surface, the trust model is closed end-to-end: third-party auditors no longer need the NOUS CLI to validate a dossier. A regulator, journalist, or compliance officer can drag a manifest into `nous-lang.org/verify` and see three independent PASS/FAIL pills in their browser, or run `verify_offline.py` on an air-gapped machine. The cryptographic chain extends from your build pipeline to a public transparency log to anyone holding a copy of the dossier, forever.

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

# 4. (Optional) Anchor the dossier into the public Sigstore Rekor log
nous dossier cost_cap_basic.nous --anchor rekor
# -> manifest gains a transparency_log block with log_index + integrated time

# 5. (Optional) Verify a dossier offline (no NOUS install required for the verifier)
python3 verify_offline.py cost_cap_basic.dossier.json
# -> PASS / FAIL on Ed25519 signature, source SHA, Rekor inclusion, ECDSA-P-256 SET
```

For EUR end-to-end verification, point `--prices` at an EUR pricing table:

```bash
nous verify --smt my_eur_agent.nous \
    --prices /path/to/eur_prices.toml
```

The shipped `pricing/eur_example.toml` declares four illustrative Mistral models priced in EUR per 1 000 000 tokens. Values are explicitly marked illustrative; verify against the provider before any production use.

## Core CLI

```
nous run file.nous              # compile + execute
nous compile file.nous          # -> Python file
nous verify file.nous           # governance lint as build gate
nous verify file.nous --smt     # SMT cost proof + signed manifest
nous verify file.nous --smt --smt-margin 10
                                # prove total_cost <= cap * 90/100
nous emit-smt file.nous         # SMT-LIB 2.6 source (re-usable across solvers)
nous dossier file.nous          # EU AI Act Annex IV compliance bundle
nous dossier file.nous --anchor rekor
                                # also anchor manifest into Sigstore Rekor
nous dossier verify <path>      # offline re-verification of a dossier

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

nous skill export file.nous     # emit agentskills.io-compatible skill folder
nous dossier-spec ./my-skill/   # emit signed Annex IV dossier from SKILL.md

nous lsp                        # start LSP server (stdio)
nous version
```

The full `nous --help` lists 44 top-level subcommands; the above covers the most-used surface.

## Language at a glance

```
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

## Architecture

| Layer | Implementation |
|---|---|
| Grammar | Lark LALR (`nous.lark`), 115 rules, bilingual EN+GR |
| AST | Pydantic V2 strict models, 61 node types |
| Validator | Constitutional law checker on AST |
| Pricing | Layered TOML (CLI > project > user > package), SHA-256 audit, schema v2.0, currency-agnostic |
| SMT emit | Deterministic SMT-LIB 2.6, exact rationals (no floats) |
| SMT solve | Z3 wrapper + counterexample extraction + fix suggestions |
| Manifests | Ed25519-signed JSON, manifest schema v1.0, offline-verifiable |
| Rekor anchor | Optional Path-beta dual signing (ECDSA-P-256 leaf + Ed25519 manifest) |
| Verify API | `POST /v1/verify-dossier` public endpoint, granular three-path response |
| Dossier | EU AI Act Annex IV-aligned compliance bundle from AST + manifest |
| CodeGen | AST -> Python 3.11+ asyncio |
| Replay | SHA-256-chained JSONL event log, integrity-verifiable offline |
| Runtime | asyncio event loop + Noosphere integration |
| LSP | stdio JSON-RPC, lint diagnostics with `source="nous.lint"` |

## The signed-manifest contract

When `nous verify --smt` returns PROVEN, it writes a JSON manifest:

```json
{
  "schema_version": "1.0",
  "nous_version": "5.11.0",
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
  "timestamp": "2026-05-17T12:34:56Z",
  "signature": "<base64 ed25519>",
  "public_key": "<base64 ed25519 pubkey>",
  "transparency_log": {
    "rekor_log_index": 1554376230,
    "rekor_integrated_at": "2026-05-16T20:08:25Z",
    "rekor_log_id": "...",
    "submitter_public_key_b64": "...",
    "submitter_signature_b64": "..."
  }
}
```

The `transparency_log` block is present only when the dossier was emitted with `--anchor rekor`. Anyone with the manifest and the publisher's public key can re-verify offline. Tamper-detection is built in. If the manifest is Rekor-anchored, the inclusion proof and SignedEntryTimestamp can be re-validated independently against the public Sigstore log.

The verifier signing key lives at `$XDG_DATA_HOME/nous/keys/signing.key` (mode `0600`, auto-generated; falls back to `~/.local/share/nous/keys/signing.key` if XDG is unset; override with `--key-path`).

## Public verification (v5.4.0+)

Three independent paths for third parties to verify a NOUS dossier without installing the NOUS toolchain:

1. **Browser convenience**: drag-drop the manifest into `https://nous-lang.org/verify`. Behind the scenes calls the public `POST /v1/verify-dossier` endpoint (no API key, rate-limited 30 req/min, 256 KiB body cap). Useful for compliance officers and journalists.
2. **Offline canonical**: download `https://nous-lang.org/verify_offline.py` (or extract from any anchored dossier). Runs locally; only dependency is `cryptography>=42`. No NOUS install, no internet required for non-Rekor checks, no network round-trip to NOUS infrastructure. This is the canonical trust path.
3. **Full CLI**: `pip install nous-lang && nous dossier verify <path>`. Re-runs SMT cost-cap verification in addition to signature and anchor checks.

Verification returns granular per-check results:

- `signature_ok` -- Ed25519 author signature over canonical manifest body
- `rekor_set_ok` -- Sigstore SignedEntryTimestamp + log-key allowlist
- `rekor_inclusion_ok` -- leaf body hash + ECDSA-P-256 submitter signature

See `docs/VERIFY_DOSSIER.md` for the full API reference, trust model, and failure-mode table.

## EU AI Act compliance

NOUS targets EU AI Act conformity for the high-risk AI system requirements of Regulation (EU) 2024/1689. The compliance matrix lives in `docs/EU_AI_ACT_COMPLIANCE.md`. Current coverage: 8 of 10 mapped articles fully covered, 1 planned, 1 out of scope.

Key article alignments:

- **Article 11 (Technical Documentation)** -- `nous dossier` emits an Annex IV-aligned bundle directly from the AST.
- **Article 12 (Record-Keeping)** -- SHA-256-chained JSONL replay logs, integrity-verifiable via `nous replay verify`.
- **Article 13 (Transparency)** -- public verification endpoint and standalone `nous-lang.org/verify` page give downstream users a no-install path to independently audit any dossier.
- **Article 14 (Human Oversight)** -- `intervene`, `inject_message`, `block` policy actions plus governance simulator.
- **Article 15 (Accuracy / Robustness / Cybersecurity)** -- Z3 SMT proofs on every `cost_cap` declaration, currency-aware (USD + EUR), with Ed25519-signed manifests and optional Sigstore Rekor anchoring for tamper-evident durability.
- **Article 17 (Quality Management)** -- 10-phase release pipeline, 738-test pytest floor, 51-source byte-identical regression harness.

## Annex IV dossiers from existing SKILL.md skills (v5.1.0+)

NOUS can produce signed Annex IV dossiers directly from skill folders that follow the agentskills.io SKILL.md spec, without modifying the skill itself. Add a `nous.yaml` sidecar declaring `cost_cap`, `default_model`, and per-tool `max_calls` / `input_tokens` / `output_tokens`, then:

```bash
nous dossier-spec ./my-skill/
```

The resulting bundle contains the verbatim `SKILL.md` and `nous.yaml`, a deterministic source envelope (`source.nous`), the signed `manifest.json`, the resolved pricing TOML, the public key, a human-readable README, and an offline `verify_offline.py`. SKILL.md is left byte-identical, so strict spec validators continue to pass. See `docs/SKILL_MD_SIDECAR.md` for the schema reference and CLI flag documentation. For the inverse direction -- emitting an agentskills.io skill from a `.nous` program via CLI, HTTP API, or IDE button -- see `docs/SKILL_EXPORT.md`.

## Documentation

- [Cost Verification Guide](docs/COST_VERIFICATION_GUIDE.md) -- end-to-end walkthrough for USD and EUR
- [SMT Verification Design](docs/SMT_VERIFICATION_DESIGN.md) -- soundness contract, Z3 pin rationale
- [Coverage Proof](docs/COVERAGE_PROOF.md) -- policy-coverage SMT obligation, Farkas certificate, stdlib-only offline verification  <!-- __s116_readme_coverage_proof_xref_v1__ -->
- [Memory Evidence Design](docs/MEMORY_EVIDENCE_DESIGN.md) -- signed per-soul memory, Phase 0 freeze
- [Memory CLI](docs/MEMORY_CLI.md) -- nous memory init/append/verify/reindex reference  <!-- __s106_readme_memory_cli_xref_v1__ -->
- [Memory Phase 1 Design](docs/MEMORY_PHASE1_DESIGN.md) -- NAME-BOUND identity, drop-when-None write-path invariant, single-soul (Option c) freeze  <!-- __s108_readme_memory_phase1_design_xref_v1__ -->
- [Memory Consultation](docs/MEMORY_CONSULTATION.md) -- consult per-(world,soul) memory inside the signed trace; offline-verifiable chain-head commitment  <!-- __s108_readme_memory_consultation_xref_v1__ -->
- [EU AI Act Compliance](docs/EU_AI_ACT_COMPLIANCE.md) -- Annex IV / Article 11 mapping
- [Annex IV Mapping](docs/ANNEX_IV_MAPPING.md) -- per-section Annex IV crosswalk to NOUS evidence artifacts
- [Rekor Anchoring](docs/REKOR_ANCHOR.md) -- Path-beta dual signing, Sigstore wire format, offline verification
- [Rekor v2 Migration](docs/REKOR_V2_MIGRATION.md) -- migration plan from Rekor v1 to v2 (Sigstore tile-based log)
- [Public Verification API](docs/VERIFY_DOSSIER.md) -- `POST /v1/verify-dossier`, trust model, three verification paths
- [SKILL.md Sidecar](docs/SKILL_MD_SIDECAR.md) -- emit dossiers from existing agentskills.io skill folders
- [Skill Export](docs/SKILL_EXPORT.md) -- emit agentskills.io skills from `.nous` programs
- [Runtime Conformance](docs/RUNTIME_CONFORMANCE.md) -- prove a signed execution trace stayed inside the static proof's envelope; standalone signed certificate, Rekor v2 anchor, offline verifier
- [Sequence Laws](docs/SEQUENCE_LAWS.md) -- declare ordering laws over an event alphabet; Z3 consistency proof (`nous verify-sequence`), the seventh runtime conformance obligation, schema-versioned certificate  <!-- __session100_sequence_laws_readme_v1__ -->
- [Gated Actions](docs/GATED_ACTIONS.md) -- declare which actions require an approver attestation via `law gated(<action>)`; the gated set is signed-source-derived and tamper-evident, the completeness counterpart to conformance obligation #5  <!-- __s141_gated_actions_readme_v1__ -->
- [Authorization Runtime](docs/AUTHORIZATION_RUNTIME.md) -- the gated-action decision surface (approve/deny/override) for Article 14(4)(d) human oversight; a signed, verb-bound `AuthorizationAttestation` evidences that a named principal recorded a decision, with refusals folded into the signed preimage and the exception/escalation record being the non-approved subset; evidences the decision was recorded, not that it was correct or meaningful  <!-- __s151_authorization_runtime_readme_v1__ -->
- [Witnessed-Run Evidence](docs/WITNESSED_RUN_EVIDENCE.md) -- the second evidence type: a signed realized-run trace with explicit stratified-trust declaration (evidence_kind/cost_binding/provider_token_integrity) and the three-link trust chain  <!-- __s144_u6_docs_v1__ -->
- [NDEC Format](docs/NDEC_FORMAT.md) -- portable proof-carrying decision attestation: a signed dossier wrapped in a DSSE / in-toto v1 envelope, offline-verifiable with `verify_ndec.py` or `nous verify <file>.ndec`; carried-verifier pin plus canonical-template allowlist  <!-- __s147_u5b_ndec_readme_xref_v1__ -->
- [Verifier-Digest Registry](docs/VERIFIER_DIGEST_REGISTRY.md) -- cross-version canonical confirmation: a signed, optionally Rekor-v2-anchored allowlist of official `verify_offline.py` template digests; on a local canonical miss a logged-tier registry confirmation closes trusting-trust across NOUS versions (evidences publicly-logged allowlist membership, not verifier correctness)  <!-- __s148_u4_registry_readme_xref_v1__ -->
- [Stratified Trust Design](docs/STRATIFIED_TRUST_DESIGN.md) -- frozen trust vocabulary and serialization contract (the cryptographic interface)
- [Attestation Receipt](docs/ATTESTATION_RECEIPT.md) -- close trust link 3 for the TEE case: an offline-verifiable provider-signed inference receipt pinned via a NOUS-signed Attestation Pinning Record (APR), making provider_token_integrity=tee_attested emittable and --require-attestation meaningful  <!-- __s145_u6_attest_readme_xref_v1__ -->

## Contributing

NOUS is developed under a non-standard model: single maintainer, chat-driven, idempotent patch scripts, 10-phase release pipeline. External contributions are welcome but follow an "issue first, PR after we agree on shape" intake. See `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md`.

Security issues should be reported via GitHub Security Advisories, not public issues.

## Stats (v5.11.0)

| Metric | Value |
|---|---|
| Tests | 738 passing (PYTEST_FLOOR enforced) |
| Regression | 51 corpus sources, 0 baseline drift |
| Shipped templates | 9 (`templates/*.nous`) |
| Grammar rules | 115 (Lark LALR, bilingual EN+GR) |
| AST node types | 61 (Pydantic V2 strict) |
| Lint rule codes | 13 (L000 - L012, L100) |
| CLI subcommands | 44 (`nous --help`) |
| Pricing schema | v2.0 (currency-agnostic, per-table `_currency`) |
| Manifest schema | v1.0 (Ed25519-signed, offline-verifiable, optional Rekor transparency_log) |
| Verification surfaces | 3 (browser endpoint, offline Python, full CLI) |
| Latest changes | See [CHANGELOG.md](CHANGELOG.md) for per-release detail |

## Commercial Services

NOUS itself is free and open source under the MIT License. Beyond the library, I offer commercial engagements for organizations that need more than self-service installation.

### EU AI Act Annex IV readiness audits

Pre-deployment review of your AI systems against Annex IV technical documentation requirements. Output: gap analysis, compliance roadmap, and (if engaged for implementation) NOUS-integrated dossier pipeline.

### Custom dossier templates

Annex IV technical documentation is domain-specific. If you operate in fintech, healthcare, insurance, recruitment, or another high-risk AI category, I build NOUS skill templates tailored to your specific sector's regulatory expectations.

### Compliance attestation

For organizations that need a named third party to sign off on their Annex IV dossier production process. I review your NOUS pipeline, verify cryptographic integrity, and provide a signed attestation suitable for regulatory submission.

### Integration consulting

End-to-end implementation: NOUS deployment, integration with your AI pipeline, observability setup, and team handover. Architecture through production reliability.

### Priority support and SLAs

Self-service NOUS is community-supported (GitHub issues). Priority support contracts offer guaranteed response times, direct contact, and security patch back-porting.

### How to engage

I work with 2-3 organizations at a time on contract basis. Discovery calls are 20-30 minutes and have no obligation.

- Email: hliasstaurou@gmail.com
- Project email: support@nous-lang.org
- LinkedIn: https://www.linkedin.com/in/hlias-staurou-a632a197

Trademark licensing inquiries are handled through the same channels; see `TRADEMARK.md` for details.

## License

MIT. See [LICENSE](LICENSE).

The MIT License covers the source code. Trademark rights over "NOUS", "Noosphere AI", "AetherProof", and "Asklepios" are reserved separately; see [TRADEMARK.md](TRADEMARK.md).

## Changelog

See [CHANGELOG.md](CHANGELOG.md). Latest release: [v5.11.0](https://github.com/contrario/nous/releases/tag/v5.11.0).
<!-- __session89_readme_freshen_v1__ -->
<!-- __s94_readme_v5_11_0_sync_v1__ -->
