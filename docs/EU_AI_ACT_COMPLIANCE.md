<!-- __session71_phase5b_step11_docs_v1__ -->
# EU AI Act Compliance Matrix

**Status:** Working document, Session 71 (3 May 2026, HEAD
`1a6dd1c`, v5.0.0). Tracks the alignment between NOUS language
features and the high-risk AI system requirements of
Regulation (EU) 2024/1689 (the "AI Act").

**Application date for high-risk Annex III systems:**
2 December 2027 (Regulation (EU) 2026/1744, Article 1(40)).

**Penalties:** up to EUR 35 000 000 or 7 percent of global
annual turnover for prohibited practices; up to EUR 15 000 000
or 3 percent for high-risk violations.

**This document is descriptive, not legal advice.** Compliance
is a provider/deployer obligation. NOUS provides primitives
that make compliance easier; the operator is responsible for
the resulting system.

---

## Strategic Position

NOUS is built around three pillars that map naturally to AI
Act requirements:

1. **Declarative Constitution.** Laws, policies, and risk
   constraints are first-class language constructs, not
   external documentation.
2. **Deterministic Replay.** Every agent run produces a
   reproducible, chained event log (Phase D, shipped Session
   54).
3. **SMT-Verified Compilation.** Constraints are
   mathematically proven before deployment (shipped end-to-end
   for both USD and EUR pricing in v5.0.0, 3 May 2026).

Combined with cryptographic provenance via Ed25519-signed
manifests (shipped Session 64) and the `nous dossier` Annex IV
emitter (shipped v4.14.0), NOUS holds the position of *the
first agentic programming language compliant with the AI Act
by construction* in its declared scope.

---

## Article-by-Article Matrix

What NOUS does, per row:
- **PROVES** Z3/Farkas result. **EVIDENCES** signed artifact.
- **GATES** runtime policy engine raises before the effect.
- **MAPS** language construct, no artifact of its own.
- **NOTHING** no mechanism. **OUT OF SCOPE** not NOUS's to do.
- **PLANNED** declared, not built.

### Article 9 -- Risk Management System

> *"A risk management system shall be established,
> implemented, documented and maintained ... a continuous
> iterative process planned and run throughout the entire
> lifecycle ..."*

**What NOUS does:** GATES. Policies raise in record mode.

**NOUS implementation:**
- Native `policy` DSL with risk weights (`risk_engine.py`)
- Governance simulator for what-if risk evaluation
  (`governance_simulator.py`)
- Lint rules (L000-L100) catch policy errors before deployment
- Risk re-evaluation on every event (continuous, not one-shot)

**Evidence:**
- `risk_engine.py` -- 10/10 tests
- `intervention.py` -- 14/14 tests
- `governance_lint.py` -- 49/49 tests
- `governance_simulator.py` -- 25/25 tests
- v4.8.2 release (Session 52) shipped Phase G governance
  complete

---

### Article 10 -- Data and Data Governance

> *"Training, validation and testing data sets shall be
> subject to data governance and management practices ..."*

**What NOUS does:** OUT OF SCOPE. Model-provider obligation.

**Rationale:** NOUS is the *runtime language* for agents, not
a model training framework. Data governance for the underlying
LLM is the responsibility of the model provider (e.g.
Anthropic, OpenAI). NOUS provides hooks (`memory.write`
policies, `data_scope` declarations) so deployers can enforce
data-handling constraints at the agent layer.

**Evidence:**
- Policy DSL supports `kind == "memory.write"` constraints
- 3-site symmetry (sense.invoke, llm.request, memory.write)
  enables per-site data governance

---

### Article 11 -- Technical Documentation

> *"Technical documentation ... shall be drawn up before that
> system is placed on the market or put into service ..."*

**What NOUS does:** EVIDENCES. Annex IV dossier from the AST.

**NOUS implementation:**
- AST is itself technical documentation: every law, policy,
  and risk declaration is structured, inspectable, and
  machine-readable.
- `nous dossier <source>` produces an Annex IV-aligned bundle
  directly from the AST plus the signed manifest plus the
  pricing table.
- Output format `annex_iv` ships in v4.14.0 and is the
  default.

**Evidence:**
- `cli_dossier.py` (registered as the `dossier` subcommand in
  `cli.py`)
- `ast_nodes.py` (Pydantic V2 strict validation)
- `parser.py` Lark grammar
- v4.0.0 timeline entry: "A compiler that compiles itself"

---

### Article 12 -- Record-Keeping

> *"High-risk AI systems shall technically allow for the
> automatic recording of events (logs) over the lifetime of
> the system."*

**What NOUS does:** EVIDENCES. Hash-chained replay log.

**NOUS implementation:**
- Phase D Deterministic Replay (shipped Session 54)
- Every event chained via SHA-256 hash (prev_hash +
  content_hash)
- `EventStore` integrity check via `nous replay verify`
- HTTP API: `GET /v1/replay/summary`, `/events`, `/verify`

**Evidence:**
- `replay_runtime.py`
- `tests/test_replay_phase_d.py` 6/6 (standalone harness)
- v4.8.2 timeline: "Deterministic replay Phase A-D locked"
- Production replay directory `/var/lib/nous/replays/` with
  immutable evidence files

**Cryptographic chain:** every replay log can be signed by an
Ed25519 key (publisher-controlled); the manifest is stored at
the publisher's chosen location; the auditor verifies the
cryptographic chain offline.

---

### Article 13 -- Transparency and Provision of Information to Deployers

> *"High-risk AI systems shall be designed and developed in
> such a way as to ensure that their operation is sufficiently
> transparent ..."*

**What NOUS does:** MAPS. Policies as source; dashboards.

**NOUS implementation:**
- Laws and policies are written in declarative source code,
  not buried in prompts or runtime configuration.
- `policies.html` dashboard renders all active policies with
  their signals, weights, and actions.
- `governance.html` dashboard shows live intervention history.

**Evidence:**
- `website/policies.html` (split-pane editor with live
  preview)
- `website/governance.html` (3-tab dashboard)
- v4.8.3 release shipped 3 production dashboards

---

### Article 14 -- Human Oversight

> *"High-risk AI systems shall be designed and developed in
> such a way ... that they can be effectively overseen by
> natural persons ..."*

**What NOUS does:** MAPS. Operator hooks; no human gate.

**NOUS implementation:**
- `intervene` action emits an audit event and surfaces the
  decision to a human operator; execution continues.
- `inject_message` action injects clarifying text into agent
  context (Layer 2.5, v4.8.1).
- `block` action halts emission of the event; `abort_cycle`
  terminates the current soul cycle.
- `governance_simulator` lets operators preview policy effect
  before deployment.

**Evidence:**
- `intervention.py` 14/14 tests
- v4.8.1 timeline: "inject_message"
- Live demo at `https://nous-lang.org/governance`

---

### Article 15 -- Accuracy, Robustness and Cybersecurity

> *"High-risk AI systems shall be designed and developed in
> such a way that they achieve an appropriate level of
> accuracy, robustness, and cybersecurity, and that they
> perform consistently in those respects throughout their
> lifecycle."*

**What NOUS does:** PROVES the declared cost cap (Z3/Farkas,
v5.0.0). EVIDENCES everything else in this section.

**Shipped:**
- Validator (`validator.py`) catches structural and semantic
  errors at compile time.
- 57 templates baseline-stable, 0 drift (deterministic
  codegen).
- Pyflakes Phase 4.5 gate against undefined-name violations
  (Session 60).
- Z3 SMT solver integration: every `cost_cap` declaration is
  proven (or refuted) before deployment under `--smt`.
- AST -> SMT-LIB 2.6 emission (`smt_emit.py`) for cost caps
  with currency-aware semantics; both USD and EUR pricing
  tables are supported end-to-end.
- Phase 5a hard-blocks currency mismatch between pricing table
  and cap (`_validate_currency_consistency`, S69 commit
  `1eb3e6b`).
- Phase 5b shipped end-to-end EUR verification, removed the
  v4.13.0 USD-only escape hatch in `_validate_world`, and
  added `nous prices upgrade` for v1.0 -> v2.0 schema
  migration (S70 commits `5e4ae11`, `237738f`, `b2869c6`,
  release `1a6dd1c`).
- Counterexample reporting includes the offending soul,
  per-call cost, total cost, declared cap, and overage.
- `--smt-margin PCT` adds a conservative safety margin (proves
  total_cost <= cap * (100 - PCT) / 100).
- Ed25519-signed manifest emitted by default on every
  successful proof; `--no-manifest` to skip.

**Evidence:**
- `smt_emit.py`, `smt_runner.py`, `manifest.py`
- `tests/test_smt_emit.py`, `tests/test_smt_emit_eur.py`,
  `tests/test_smt_verify.py`,
  `tests/test_pricing_v1_compat.py`
- 394 pytest passing on Server A, 0 xfailed (PYTEST_FLOOR =
  394)
- 57-template regression harness, 0 drift
- v5.0.0 CHANGELOG entry covering the full Phase 5b arc

This is the **killer feature** of NOUS as positioned for the
AI Act: no other agentic language ships verified-by-
construction safety today.

---

### Article 19 -- Automatically Generated Logs

> *"Providers of high-risk AI systems shall keep the logs ...
> for a period appropriate to the intended purpose ..."*

**What NOUS does:** EVIDENCES. Same chain as Article 12.

**NOUS implementation:**
- All replay event logs are JSONL append-only with SHA-256
  chain.
- Retention is operator-controlled (NOUS does not delete
  logs).
- `nous replay verify <log>` validates chain integrity.

**Evidence:** see Article 12.

---

### Article 50 -- Transparency Obligations (Synthetic Content)

> *"Providers of AI systems ... that generate synthetic audio,
> image, video or text content, shall ensure that the outputs
> of the AI system are marked in a machine-readable format and
> detectable as artificially generated or manipulated."*

**What NOUS does:** PLANNED. `mark_synthetic` policy action;
marking is a property of model output, not the language.

**Rationale:** Synthetic-content marking is a property of the
model output, not the orchestration language. NOUS provides a
`mark_synthetic` action in the policy DSL (planned, future
session) so deployers can declare watermarking obligations as
policies.

---

## Summary

| Article | Title                                | Status                |
|---------|--------------------------------------|-----------------------|
| 9       | Risk Management System               | COVERED               |
| 10      | Data and Data Governance             | OUT OF SCOPE          |
| 11      | Technical Documentation              | COVERED (machine-gen) |
| 12      | Record-Keeping                       | COVERED               |
| 13      | Transparency to Deployers            | COVERED               |
| 14      | Human Oversight                      | COVERED               |
| 15      | Accuracy / Robustness / Cybersec     | COVERED (v5.0.0)      |
| 19      | Automatically Generated Logs         | COVERED               |
| 50      | Synthetic Content Marking            | PLANNED               |

---

## Compliance Dossier (shipped)

The four pieces called out in earlier revisions of this
document are all live as of v5.0.0:

1. **SMT-verified compilation:** every declared `cost_cap` is
   proven by Z3 before deployment under `--smt`.
   Currency-aware for both USD and EUR.
2. **Signed manifests:** every compiled program emits a
   content-addressed Ed25519-signed manifest. Storage is the
   publisher's choice; verification is offline.
3. **Auditor verification:** any holder of the manifest plus
   the publisher's public key verifies the cryptographic
   chain offline, replays deterministically, and produces a
   compliance report.
4. **Public dossier:** `nous dossier <source>` emits an Annex
   IV-aligned technical documentation bundle auto-generated
   from the AST plus the signed manifest plus the pricing
   table.

---

## What is NOT in this matrix

An article is in the matrix when NOUS gives the deployer a
language or runtime mechanism for it. Otherwise it is here.

- Article 16 (provider obligations on placing on the market):
  provider/deployer obligation, not a language concern.
- Article 17 (quality management system): provider obligation.
  The NOUS release pipeline is the quality system of the NOUS
  package, not of a deployer's high-risk AI system. NOUS
  supplies toolchain provenance (SLSA build attestation, PEP
  740 publish attestation, Rekor v2 anchor, signed manifests)
  that a provider may cite inside their own quality system.
- Article 18 (record-keeping retention period): operator
  policy.
- Article 20 (corrective actions): operator policy.
- Articles 26 to 49 (provider/deployer obligations, conformity
  assessment, registration): operator and notified-body
  responsibilities. NOUS supplies the technical documentation
  (Article 11) and proof artifacts (Article 15) on which those
  obligations are built.

---

## References

- Regulation (EU) 2024/1689 (the AI Act):
  https://artificialintelligenceact.eu/
- Implementation timeline:
  https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai
- AI Act Service Desk:
  https://ai-act-service-desk.ec.europa.eu/
- Code of Practice on Marking and Labelling AI-Generated
  Content (draft, Dec 2025)

---

*Last updated: Session 71, 3 May 2026 (HEAD: post-`1a6dd1c`,
v5.0.0).*
