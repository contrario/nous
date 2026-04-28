# EU AI Act Compliance Matrix

**Status:** Working document, Session 61. Tracks the alignment between NOUS
language features and the high-risk AI system requirements of Regulation
(EU) 2024/1689 (the "AI Act").

**Enforcement deadline for high-risk Annex III systems:** 2 August 2026.

**Penalties:** up to EUR 35 000 000 or 7 % of global annual turnover for
prohibited practices; up to EUR 15 000 000 or 3 % for high-risk violations.

**This document is descriptive, not legal advice.** Compliance is a
provider/deployer obligation. NOUS provides primitives that make
compliance easier; the operator is responsible for the resulting system.

---

## Strategic Position

NOUS is built around three pillars that map naturally to AI Act
requirements:

1. **Declarative Constitution.** Laws, policies, and risk constraints
   are first-class language constructs, not external documentation.
2. **Deterministic Replay.** Every agent run produces a reproducible,
   chained event log (Phase D, shipped Session 54).
3. **SMT-Verified Compilation.** Constraints are mathematically proven
   before deployment (Sessions 62-65, in progress).

Combined with cryptographic provenance via AetherProof signed manifests
(planned Session 64), NOUS targets the position of *the first
agentic programming language compliant with the AI Act by construction*.

---

## Article-by-Article Matrix

Status legend:
- **COVERED**: feature exists and is tested in production.
- **PARTIAL**: foundation exists, additional work required.
- **PLANNED**: not yet built; on the killer-feature arc.
- **OUT OF SCOPE**: provider/deployer obligation, not a language concern.

### Article 9 -- Risk Management System

> *"A risk management system shall be established, implemented,
> documented and maintained ... a continuous iterative process planned
> and run throughout the entire lifecycle ..."*

**Status:** COVERED

**NOUS implementation:**
- Native `policy` DSL with risk weights (`risk_engine.py`)
- Governance simulator for what-if risk evaluation (`governance_simulator.py`)
- Lint rules (L000-L100) catch policy errors before deployment
- Risk re-evaluation on every event (continuous, not one-shot)

**Evidence:**
- `risk_engine.py` -- 10/10 tests
- `intervention.py` -- 14/14 tests
- `governance_lint.py` -- 49/49 tests
- `governance_simulator.py` -- 25/25 tests
- v4.8.2 release (Session 52) shipped Phase G governance complete

---

### Article 10 -- Data and Data Governance

> *"Training, validation and testing data sets shall be subject to data
> governance and management practices ..."*

**Status:** OUT OF SCOPE

**Rationale:** NOUS is the *runtime language* for agents, not a model
training framework. Data governance for the underlying LLM is the
responsibility of the model provider (e.g., Anthropic, OpenAI). NOUS
provides hooks (`memory.write` policies, `data_scope` declarations) so
deployers can enforce data-handling constraints at the agent layer.

**Evidence:**
- Policy DSL supports `kind == "memory.write"` constraints
- 3-site symmetry (sense.invoke, llm.request, memory.write) enables
  per-site data governance

---

### Article 11 -- Technical Documentation

> *"Technical documentation ... shall be drawn up before that system is
> placed on the market or put into service ..."*

**Status:** COVERED (machine-generated)

**NOUS implementation:**
- AST is itself technical documentation: every law, policy, and risk
  declaration is structured, inspectable, and machine-readable.
- `nous compile --emit-docs` (planned, Session 65) will produce an
  Annex IV-aligned dossier directly from the AST.

**Gap:** the dossier-generation CLI is not yet shipped. Manual export
via `nous ast | nous emit md` is possible today but not standardized.

**Evidence:**
- `ast_nodes.py` (Pydantic V2 strict validation)
- `parser.py` Lark grammar
- v4.0.0 timeline entry: "A compiler that compiles itself"

---

### Article 12 -- Record-Keeping

> *"High-risk AI systems shall technically allow for the automatic
> recording of events (logs) over the lifetime of the system."*

**Status:** COVERED

**NOUS implementation:**
- Phase D Deterministic Replay (shipped Session 54)
- Every event chained via SHA-256 hash (prev_hash + content_hash)
- `EventStore` integrity check via `nous replay verify`
- HTTP API: `GET /v1/replay/summary`, `/events`, `/verify`

**Evidence:**
- `replay_runtime.py`
- `tests/test_replay_phase_d.py` 6/6 (standalone harness)
- v4.8.2 timeline: "Deterministic replay Phase A-D locked"

**Forthcoming enhancement (Session 64):** every replay log signed by
AetherProof Ed25519 key; manifest published immutable on
`api.aetherlang.online`; auditor verifies cryptographic chain.

---

### Article 13 -- Transparency and Provision of Information to Deployers

> *"High-risk AI systems shall be designed and developed in such a way as
> to ensure that their operation is sufficiently transparent ..."*

**Status:** COVERED

**NOUS implementation:**
- Laws and policies are written in declarative source code, not buried
  in prompts or runtime configuration.
- `policies.html` dashboard renders all active policies with their
  signals, weights, and actions.
- `governance.html` dashboard shows live intervention history.

**Evidence:**
- `website/policies.html` (split-pane editor with live preview)
- `website/governance.html` (3-tab dashboard)
- v4.8.3 release shipped 3 production dashboards

---

### Article 14 -- Human Oversight

> *"High-risk AI systems shall be designed and developed in such a way ...
> that they can be effectively overseen by natural persons ..."*

**Status:** COVERED

**NOUS implementation:**
- `intervene` action in policy DSL halts execution and surfaces decision
  to a human operator.
- `inject_message` action injects clarifying text into agent context
  (Layer 2.5, v4.8.1).
- `block` action aborts the cycle entirely.
- `governance_simulator` lets operators preview policy effect before
  deployment.

**Evidence:**
- `intervention.py` 14/14 tests
- v4.8.1 timeline: "inject_message"
- Live demo at `https://nous-lang.org/governance`

---

### Article 15 -- Accuracy, Robustness and Cybersecurity

> *"High-risk AI systems shall be designed and developed in such a way
> that they achieve an appropriate level of accuracy, robustness, and
> cybersecurity, and that they perform consistently in those respects
> throughout their lifecycle."*

**Status:** PARTIAL -> moving to COVERED in Sessions 62-65

**Currently shipped:**
- Validator (`validator.py`) catches structural and semantic errors at
  compile time.
- 54/54 regression templates byte-identical (deterministic codegen).
- Pyflakes Phase 4.5 gate against undefined-name violations (Session 60).

**Gap (closing in Sessions 62-65):**
- No mathematical proof that constraints hold across all execution
  paths. Today's validator is structural, not semantic.

**Planned implementation:**
- Z3 SMT solver integration (Session 62)
- AST -> SMT-LIB emission for cost caps, rate limits, forbidden actions
  (Sessions 62-63)
- Counterexample -> deterministic replay trace (Session 63)
- Build fails if Z3 cannot prove safety (Session 63)

This is the **killer feature** of NOUS as positioned for the AI Act:
no other agentic language ships verified-by-construction safety today.

---

### Article 17 -- Quality Management System

> *"Providers of high-risk AI systems shall put a quality management
> system in place that ensures compliance ..."*

**Status:** COVERED

**NOUS implementation:**
- `scripts/release.py` 10-phase pipeline (test, regression, version
  consistency, grammar sync, pyflakes gate, ...)
- `regression_harness.py` for 54-template byte-identical verification
- PYTEST_FLOOR enforced (currently 184)
- Version-consistency tests across `cli.py`, `nous_api.py`, `_version.py`

**Evidence:**
- `scripts/release.py`
- `regression_harness.py verify` (must return RESULT: OK)
- `tests/test_version_consistency.py` 7/7

---

### Article 19 -- Automatically Generated Logs

> *"Providers of high-risk AI systems shall keep the logs ... for a
> period appropriate to the intended purpose ..."*

**Status:** COVERED

**NOUS implementation:**
- All replay event logs are JSONL append-only with SHA-256 chain.
- Retention is operator-controlled (NOUS does not delete logs).
- `nous replay verify <log>` validates chain integrity.

**Evidence:** see Article 12.

---

### Article 50 -- Transparency Obligations (Synthetic Content)

> *"Providers of AI systems ... that generate synthetic audio, image,
> video or text content, shall ensure that the outputs of the AI system
> are marked in a machine-readable format and detectable as artificially
> generated or manipulated."*

**Status:** OUT OF SCOPE for the language; PLANNED hook

**Rationale:** Synthetic-content marking is a property of the model
output, not the orchestration language. NOUS provides a
`mark_synthetic` action in the policy DSL (planned, Session 66+) so
deployers can declare watermarking obligations as policies.

---

## Summary

| Article                | Title                                | Status                  |
|------------------------|--------------------------------------|-------------------------|
| 9                      | Risk Management System               | COVERED                 |
| 10                     | Data and Data Governance             | OUT OF SCOPE            |
| 11                     | Technical Documentation              | COVERED (machine-gen)   |
| 12                     | Record-Keeping                       | COVERED                 |
| 13                     | Transparency to Deployers            | COVERED                 |
| 14                     | Human Oversight                      | COVERED                 |
| 15                     | Accuracy / Robustness / Cybersec     | PARTIAL -> 62-65        |
| 17                     | Quality Management System            | COVERED                 |
| 19                     | Automatically Generated Logs         | COVERED                 |
| 50                     | Synthetic Content Marking            | PLANNED (Session 66+)   |

**7 articles covered, 1 partial (closing), 1 planned, 1 out of scope.**

---

## Path to Full Compliance Dossier

Sessions 62-65 close the only material gap (Article 15). At end of
Session 65, NOUS will ship:

1. **SMT-verified compilation:** every law/policy/cost-cap proven by Z3
   before deployment.
2. **AetherProof signed manifests:** every compiled program emits a
   content-addressed Ed25519-signed manifest published on
   `api.aetherlang.online`.
3. **Auditor CLI:** `nous audit <manifest_id>` downloads the manifest,
   verifies the cryptographic chain, replays deterministically, and
   produces a human-readable compliance report.
4. **Public dossier:** v5.0.0 release will include an Annex IV-aligned
   technical documentation dossier auto-generated from the AST.

---

## References

- Regulation (EU) 2024/1689 (the AI Act): https://artificialintelligenceact.eu/
- Implementation timeline: https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai
- AI Act Service Desk: https://ai-act-service-desk.ec.europa.eu/
- Code of Practice on Marking and Labelling AI-Generated Content (draft, Dec 2025)

---

*Last updated: Session 61, 28 April 2026 (HEAD: ad278dd)*
