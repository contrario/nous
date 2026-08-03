# EU AI Act Annex IV -- NOUS Mapping

> Per-clause crosswalk between the technical documentation requirements
> of EU AI Act Annex IV (Regulation (EU) 2024/1689, Article 11) and the
> evidence artifacts NOUS produces.

**Status:** Working reference, Session 106 (31 May 2026, HEAD `3298388`,
v5.24.0). This document is descriptive, not legal advice. Compliance is a
provider obligation; NOUS supplies machine-generated evidence to support
that obligation.

---

## 1. Purpose

This document is the per-section mapping between the nine items of EU
AI Act Annex IV and the artifacts NOUS produces during compilation,
verification, and dossier emission. It is intended for:

- Providers of high-risk AI systems preparing their conformity
  assessment under Article 43 (Annex VI internal control or Annex VII
  notified body).
- Auditors and compliance officers reviewing dossiers emitted by
  `nous dossier` or `nous dossier-spec`.
- Notified-body assessors looking for the structural correspondence
  between NOUS evidence and the legally required documentation.

It is **not** a substitute for legal counsel, a harmonised standard,
or the AI Act text itself. The mapping reflects how NOUS positions its
artifacts; the regulator decides whether a given dossier satisfies the
clause.

For the article-level matrix (Articles 9-15, 19, 50), see
[EU_AI_ACT_COMPLIANCE.md](EU_AI_ACT_COMPLIANCE.md). The current
document is the Annex-level peer to that file.

---

## 2. Regulatory status

The EU AI Act (Regulation (EU) 2024/1689) was adopted in June 2024 and
entered into force on 1 August 2024. Application of its provisions is
staged. The table below reflects the Digital Omnibus on AI AS ENACTED:
Regulation (EU) 2026/1744, OJ L, 2026/1744, 24.7.2026, CELEX 32026R1744.
Parliament adopted it on 16 June 2026 and Council on 29 June 2026; it was
signed on 8 July 2026 in Strasbourg and published on 24 July 2026.

| Provision | Original date | Revised date (post-Omnibus) |
|---|---|---|
| Prohibited practices (Article 5) | 2 Feb 2025 | unchanged |
| GPAI obligations (Articles 51-55) | 2 Aug 2025 | unchanged |
| **Annex III high-risk standalone** | **2 Aug 2026** | **2 Dec 2027** |
| Annex I high-risk (embedded in products) | 2 Aug 2027 | 2 Aug 2028 |
| Article 50(2) watermarking (new systems) | 2 Aug 2026 | unchanged |
| Article 50(2) watermarking (pre-existing) | 2 Aug 2026 | 2 Dec 2026 |
| National regulatory sandboxes | 2 Aug 2026 | 2 Aug 2027 |
| New Article 5 (NCII/CSAM/nudifier) | n/a | 2 Dec 2026 |

The revised Annex III date of 2 December 2027 is the operative planning
baseline for most providers. It is NO LONGER CONDITIONAL: the Omnibus is
enacted, and its Article 1(40) replaces the third paragraph of Article 113,
so the date sits in the enacted text rather than in a draft. The
substantive content of Annex IV itself has not changed; only the
application date has moved.

References:
- Council press release "Artificial Intelligence: Council and
  Parliament agree to simplify and streamline rules", 7 May 2026
  (updated 18 May 2026).
- Council presidency letter to European Parliament, 13 May 2026.

---

## 3. Mapping methodology

Sections 4 through 12 below cover the nine items of Annex IV in order.
For each item, the structure is:

- **Annex IV requirement** -- the verbatim text from the Regulation
  (paraphrased to ASCII where the original uses smart quotes or
  em-dashes).
- **Where in NOUS** -- pointer to the module, artifact, or CLI command
  that produces the relevant evidence.
- **Evidence artifact** -- the actual file an auditor opens.
- **Determinism boundary** -- which fields are byte-reproducible
  given the same inputs, and which are timestamp-dependent or
  probabilistic.

A NOUS dossier emitted by `nous dossier <source>` or
`nous dossier-spec <skill_dir>` is a directory containing
`source.nous`, `manifest.json`, `pricing.toml`, `public_key.b64`,
`README.md`, and `verify_offline.py`. The `README.md` inside the dossier
contains a self-describing Annex IV item-by-item table for that
specific dossier; the current document is the broader project-level
mapping that explains how each NOUS evidence type maps to each clause.

---

## 4. Annex IV (1) -- General description of the AI system

**Annex IV requirement:** "A general description of the AI system
including its intended purpose, the name of the provider and the
version of the system reflecting its relation to previous versions."

**Where in NOUS:**

- `SKILL.md` sidecar (agentskills.io frontmatter) -- name, description,
  license, compatibility. See `docs/SKILL_MD_SIDECAR.md`.
- `nous.yaml` cost envelope -- declared `cost_cap`, `default_model`,
  per-tool token budgets.
- `manifest.json` fields: `world_name`, `nous_version`,
  `schema_version`, `smt_emit_version`.
- Source `.nous` file -- the language declaration is itself the system
  description (worlds, souls, policies, costs).

**Evidence artifact:**

```
<skill_dir>/SKILL.md                 # human-readable system description
<skill_dir>/nous.yaml                # machine-readable cost envelope
<dossier>/manifest.json              # signed identity and version
<dossier>/source.nous                # canonical source
```

**Determinism boundary:** All four artifacts are byte-deterministic for
a given source plus pricing input. `SKILL.md` frontmatter is generated
by `nous skill-export` with a documented one-way lossy projection (see
[SKILL_EXPORT.md](SKILL_EXPORT.md)).

**Code reference:** `skill_md.py`, `skill_export.py`,
`cli_skill_export.py`.

---

## 5. Annex IV (2) -- Detailed description of elements and development process

**Annex IV requirement:** "A detailed description of the elements of
the AI system and of the process for its development, including the
methods and steps performed for the development of the AI system, the
design specifications of the system, the design choices, the main
classification choices, what the system is designed to optimise for,
and the system architecture explaining how software components build
on or feed into each other and integrate into the overall processing."

**Where in NOUS:**

- `.nous` source files are the design specification. The grammar
  (`nous.lark`) is LALR(1)-deterministic and the AST
  (`ast_nodes.py`) is Pydantic V2 strict, so the design is fully
  machine-readable and unambiguous.
- Codegen target: deterministic Python 3.11+ asyncio
  (`codegen.py`). The same `.nous` source produces byte-identical
  Python output across runs.
- AEvolver lineage records (`aevolver.py`) document evolution of
  declarations across versions when the self-evolution path is used.
- Governance trace links source to validated AST to compiled artifact.

**Evidence artifact:**

```
<dossier>/source.nous                # the design specification
<dossier>/manifest.json              # source_sha256 binds the source
                                     # to all downstream evidence
```

**Determinism boundary:** Source-to-AST-to-Python codegen is fully
byte-deterministic. The 57-template regression harness
(`regression_harness.py verify`) enforces zero drift across releases.

**Code reference:** `parser.py`, `validator.py`, `codegen.py`,
`aevolver.py`, `regression_harness.py`.

---

## 6. Annex IV (3) -- Monitoring, functioning and control

<!-- __session99_docs_second_pass_v1__ -->
**Runtime evidence:** beyond the dossier (which records what the static SMT proof guarantees about every possible run), NOUS emits a runtime conformance certificate per execution. The certificate is a standalone Ed25519-signed artifact that records, for one specific run, six independent obligations (binding, surface, assumption_discharge, bound_transfer, authorization, trace_signature) against the re-derived static spec; with `--anchor rekor_v2` it is also stapled into the Sigstore Rekor v2 transparency log. The verdict is reproducible offline with `cryptography` plus stdlib only, no NOUS install required. See `RUNTIME_CONFORMANCE.md` for the six obligations, the SCITT-shaped rationale for keeping the certificate standalone (one static proof to many runtime certificates), and the honest scope limits (certificate proves the trace conforms, not that the trace faithfully records reality; full faithfulness against a malicious runtime needs a TEE or hardware attestation). Since S144, this trust boundary is made explicit and machine-checkable inside the signed artifact: a witnessed-run trace carries an evidence_kind/cost_binding/provider_token_integrity declaration (see WITNESSED_RUN_EVIDENCE.md and STRATIFIED_TRUST_DESIGN.md), so an auditor reads the provider-token-integrity tier (unattested today) rather than taking the scope limit on faith.  <!-- __s144_u6_docs_v1__ -->

**Annex IV requirement:** "Detailed information about the monitoring,
functioning and control of the AI system, in particular with regard
to: its capabilities and limitations in performance; the foreseeable
unintended outcomes and sources of risks to health and safety,
fundamental rights and discrimination; and the human oversight
measures needed."

**Where in NOUS:**

- Policy DSL declarations -- `policy { on ... signal ... action ... }`
  inside the source. Static analysis via `nous governance lint`
  (13 rule codes, L000-L100).
- V2 verify-dossier response surface (shipped v5.5.0):
  - `verdict: ACCEPT | REJECT` (deterministic from policy + checks).
  - `trust_level: rekor_anchored | ed25519_only | none`.
  - `checks` (eight discriminated check fields with
    `ok: true | false | "skipped_unanchored" | "skipped_no_policy"`).
  - `evidence` (raw facts: hashes, log indices, public keys, anchor
    age).
  - `human_readable` (verdict summary, trust explanation, next steps).
- HMI surfaces consuming the V2 response: `nous-lang.org/verify`,
  the in-browser IDE Dossier tab, and `verify_offline.py` CLI.

**Evidence artifact:**

```
<dossier>/manifest.json              # verdict, cost_cap_usd,
                                     # smt_spec_sha256, solver verdict
POST /api/v1/verify-dossier          # V2 response with verdict,
                                     # trust_level, checks, evidence,
                                     # human_readable
```

**Determinism boundary:** The verdict computation is deterministic from
`policy_applied` (the echoed policy with defaults filled) plus the
manifest bytes. Two auditors running the same policy on the same
dossier obtain the same verdict.

**Code reference:** `nous_api_server.py`, `dossier.py`,
`governance_lint.py`, `intervention.py`.

---

## 7. Annex IV (4) -- Performance metrics

**Annex IV requirement:** "A detailed description of the system in
terms of its performance, including its accuracy and the relevant
metrics for assessing its performance."

**Where in NOUS:**

- Declared cost cap (`cost_cap: <amount> <USD|EUR>`) inside the world
  block of the source.
- SMT proof under `nous verify --smt`: Z3 4.16.0 proves
  `total_cost <= cap` across all execution paths bounded by
  `max_ticks` and soul count.
- Manifest fields: `cost_cap_usd`, `verdict`, `solver_name`,
  `solver_version`, `elapsed_ms`, `smt_spec_sha256`,
  `smt_emit_version`.
- Conservative safety margin: `--smt-margin PCT` proves
  `total_cost <= cap * (100 - PCT) / 100`.

**Evidence artifact:**

```
<dossier>/manifest.json              # verdict: "proven", cost_cap_usd
<dossier>/source.nous                # cost_cap declaration
<dossier>/pricing.toml               # signed cost model
```

**Determinism boundary:** SMT emission is byte-deterministic; the spec
SHA-256 (`smt_spec_sha256`) is reproducible from the source plus the
pricing TOML. The solver verdict is deterministic for any sound SMT
solver; the elapsed time is environment-dependent and informational
only.

**Code reference:** `smt_emit.py`, `smt_runner.py`, `pricing.py`,
`cost_oracle.py`.

---

## 8. Annex IV (5) -- Risk management system

**Annex IV requirement:** "A detailed description of the risk
management system in accordance with Article 9."

**Where in NOUS:**

- `policy` DSL with explicit deny/require rules.
- Risk weights via `signal` declarations.
- REJECT verdict in V2 surface when any check fails the declared
  policy.
- Discriminated `ok` field distinguishes failed checks from skipped
  checks -- an auditor sees the exact reason for any non-PASS state.
- `nous governance policies <source>` lists every policy in a file.
- `nous governance lint <source>` runs static analysis (13 rule
  codes).
- `governance_simulator` previews policy effect before deployment.

**Evidence artifact:**

```
<source>.nous                          # policy declarations
POST /api/v1/verify-dossier            # policy_applied + verdict
                                       # echo for audit record
<governance log>                       # intervention events
```

**Determinism boundary:** Policy evaluation is deterministic from the
declared policy plus the manifest. The `policy_applied` field in the
V2 response echoes the policy with defaults filled, providing a stable
audit record.

**Code reference:** `risk_engine.py`, `intervention.py`,
`governance_lint.py`, `governance_simulator.py`.

Article 9 cross-reference: see
[EU_AI_ACT_COMPLIANCE.md](EU_AI_ACT_COMPLIANCE.md) for the
article-level mapping.

---

## 9. Annex IV (6) -- Changes made to the system through its lifecycle

**Annex IV requirement:** "A description of any change made to the
system through its lifecycle."

**Where in NOUS:**

- Content addressing: every artifact carries its SHA-256 in the
  manifest (`source_sha256`, `pricing_sha256`, `smt_spec_sha256`).
- Ed25519 signature over canonical RFC 8785-style JSON binds the
  manifest to the signer.
- Optional Rekor anchoring (`--anchor rekor`, shipped v5.3.0)
  inserts the manifest signature into the public Sigstore
  transparency log. The inclusion proof embedded in the manifest
  proves the artifact existed at the log timestamp.
- Path-beta dual signing: per-submission ephemeral ECDSA-P-256 leaf
  for Rekor compatibility (Sigstore issue 851 EdDSA gap), long-lived
  Ed25519 manifest signature preserved.

**Evidence artifact:**

```
<dossier>/manifest.json                # source_sha256, pricing_sha256,
                                       # smt_spec_sha256, signature,
                                       # rekor inclusion proof (optional)
<dossier>/verify_offline.py            # offline HYBRID verifier:
                                       # validates Ed25519 + Rekor
                                       # inclusion (anchored) or
                                       # falls through with
                                       # --allow-unanchored
```

**Determinism boundary:** Content addressing is fully deterministic.
Rekor anchoring adds a non-deterministic timestamp (the `log_index`
and inclusion proof are assigned by the log), but the Ed25519
signature over the canonical manifest body is reproducible.

**Code reference:** `manifest.py`, `dossier.py`
(`VERIFY_OFFLINE_PY_HYBRID` constant), `rekor_anchor.py`.

See [REKOR_ANCHOR.md](REKOR_ANCHOR.md) for the full anchoring design.

---

## 10. Annex IV (7) -- Harmonised standards applied

**Annex IV requirement:** "A list of the harmonised standards applied
in full or in part the references of which have been published in the
Official Journal of the European Union; where no such harmonised
standards have been applied, a detailed description of the solutions
adopted to meet the requirements [...]"

**Where in NOUS:**

As of May 2026, **no harmonised standards have been cited in the
Official Journal of the European Union** under the EU AI Act. The
CEN-CENELEC JTC 21 work programme has the following primary standards
in development, full delivery target Q4 2026:

| Standard | Scope | AI Act anchor | Status |
|---|---|---|---|
| `prEN 18229-1` | AI Trustworthiness Pt 1: logging, transparency, human oversight | Art. 12, 13, 14 | Under development |
| `prEN 18229-2` | AI Trustworthiness Pt 2: accuracy, robustness | Art. 15 | Under development |
| `prEN 18282` | Cybersecurity specifications for AI | Art. 15 | Under development |
| `prEN 18283` | Bias management | Art. 10 | Under development |
| `prEN 18284` | Dataset quality and governance | Art. 10 | Under development |
| `prEN 18285` | AI Conformity assessment framework | Art. 43 | Under development |
| `prEN 18286` | Quality management system for EU AI Act | Art. 17 | Public enquiry (Oct 2025) |
| `prEN ISO/IEC 24970` | AI system logging | Art. 12 | Under development |

`ISO/IEC 42001` (AI management system) has approximately 40-50 percent
overlap with AI Act requirements but is **not being harmonised under
the Act**. It is suitable as an operational governance framework but
does not confer presumption of conformity.

Because no harmonised standard is yet citable, providers must currently
follow the alternative path: a detailed description of the solutions
adopted to meet the essential requirements. NOUS supplies that
description in the form of:

- This document (Annex-IV-to-NOUS crosswalk).
- [EU_AI_ACT_COMPLIANCE.md](EU_AI_ACT_COMPLIANCE.md)
  (article-by-article matrix).
- [SMT_VERIFICATION_DESIGN.md](SMT_VERIFICATION_DESIGN.md)
  (soundness contract for Article 15 cost-bound proofs).
- [REKOR_ANCHOR.md](REKOR_ANCHOR.md) (transparency log design for
  Article 12 record-keeping and Article 19 logs).
- [VERIFY_DOSSIER.md](VERIFY_DOSSIER.md) (V2 response surface design
  for Article 14 human oversight).

NOUS architecture is designed to align cleanly with the in-development
standards. When prEN 18229-1 is harmonised, the NOUS V2 verify-dossier
surface (verdict + trust_level + checks + evidence + human_readable)
maps directly onto the standard's logging, transparency, and human
oversight requirements.

**Code reference:** none (this is a documentation clause).

---

## 11. Annex IV (8) -- EU declaration of conformity

**Annex IV requirement:** "A copy of the EU declaration of conformity
referred to in Article 47."

**Where in NOUS:** Out of scope. The declaration is a legal document
the provider draws up and signs under their own legal identity. NOUS
does not issue or sign declarations.

**What NOUS supplies to back the declaration:** the evidence artifacts
listed in sections 4 through 10 and 12 of this document. The
declaration references those artifacts; the artifacts substantiate the
claims in the declaration.

**Code reference:** none.

---

## 12. Annex IV (9) -- Post-market monitoring plan

**Annex IV requirement:** "A description of the system in place to
evaluate the AI system performance in the post-market phase in
accordance with Article 72, including the post-market monitoring plan
referred to in Article 72(3)."

**Where in NOUS:**

- Phase D deterministic replay (shipped Session 54): every agent run
  produces a SHA-256-chained JSONL event log.
- `nous replay verify` validates chain integrity offline.
- Governance trace links execution events to triggering policies.
- Execution lineage and derived admission state surface intervention
  history.
- HTTP API: `GET /v1/replay/summary`, `/events`, `/verify`.
- Rekor-anchored dossiers are historically verifiable: an auditor in
  2030 holding a dossier from 2026 can validate the Ed25519 signature
  and the Rekor inclusion proof against the (immutable) public log.

**Evidence artifact:**

```
/var/lib/nous/replays/                 # append-only JSONL event logs
<replay>.jsonl                         # chained event log
<dossier>/verify_offline.py            # HYBRID verifier validates
                                       # historical dossiers offline
```

**Determinism boundary:** Replay events are content-addressed via
SHA-256 chain. The chain is independently re-verifiable; tampering
with any historical event invalidates all subsequent events.

**Code reference:** `replay_runtime.py`, `dossier.py` HYBRID body.

---

## 13. Article 14 cross-reference (Human Oversight)

Article 14 of the EU AI Act mandates that high-risk AI systems be
designed for effective oversight by natural persons. The NOUS surface
maps to each of Article 14's five paragraphs as follows:

| Article 14 paragraph | NOUS feature |
|---|---|
| (1) Effective oversight via HMI tools | IDE Dossier tab (in-browser), `nous-lang.org/verify` (drag-and-drop), `verify_offline.py` (CLI) |
| (2) Aim: prevent or minimise risks | Policy DSL deny rules; REJECT verdict in V2 surface |
| (3) Built-in or deployer-implemented | Policies ship with provider artifact (built-in) or are customised by deployer (Annex VI / VII self-assessment path) |
| (4)(a) Understand capabilities and limits | Discriminated `checks` block surfaces what the system actually validated; `trust_explanation` describes what verdict means |
| (4)(b) Awareness of automation bias | REJECT path triggers explicit `next_steps[]` rather than auto-accept |
| (4)(c) Correctly interpret output | `human_readable.verdict_summary` and `trust_level` discriminator give plain-language framing |
| (4)(d) Decide not to use or disregard | Policy `require_anchor=true` rejects unanchored dossiers; auditor sets policy at request time |
| (4)(e) Intervene or interrupt | `intervene`, `block`, `inject_message` actions in policy DSL halt execution |
| (4)(f) Halt operation | `block` action aborts cycle; REJECT verdict signals halt at dossier validation time |
| (5) Two-person verification for biometric ID | Out of scope; NOUS does not ship biometric identification systems. The dual-signature architecture (Path-beta) demonstrates the project supports dual-key ceremonies if needed |

See the Session 78 blog post "Your Stop Button Is Not Article 14
Compliance" (2026-05-16) at `nous-lang.org/blog` for the design
rationale.

---

## 14. Out of scope

The following obligations are listed in Annex IV or related provisions
but are out of scope for NOUS as a meta-language. They are either
deployer responsibilities, model-provider responsibilities, or apply
only to system categories NOUS does not target.

- **Article 50(2) watermarking.** NOUS does not generate audio,
  image, video, or text content. It is the orchestration language for
  systems that may include generative components; watermarking is the
  responsibility of the underlying model provider.
- **Annex I high-risk (medical devices, machinery, toys, lifts).**
  Different annex, different conformity assessment path (sectoral
  regulation governs). Application date 2 August 2028 post-Omnibus.
- **Article 5 new prohibitions.** NCII, CSAM, and nudifier apps are
  not an applicable surface for NOUS.
- **Article 27 Fundamental Rights Impact Assessment.** Deployer
  obligation. NOUS supplies input artifacts but does not produce the
  FRIA itself.
- **Article 10 training data governance.** NOUS is the runtime
  language for agents, not a model training framework. The underlying
  LLM's data governance is the model provider's responsibility.

---

## 15. Conformity assessment path

The EU AI Act Article 43 specifies two paths for high-risk system
conformity assessment:

**Annex VI (internal control / self-assessment)** is the default and
applies to Annex III points 2 through 8:

- Critical infrastructure (point 2)
- Education and vocational training (point 3)
- Employment, workers management, access to self-employment (point 4)
- Access to essential private and public services (point 5)
- Law enforcement (point 6)
- Migration, asylum, border control (point 7)
- Administration of justice and democratic processes (point 8)

The provider self-assesses against Section 2 requirements (Articles
8-15), documents findings in the technical file (Annex IV), declares
conformity, affixes CE marking, and registers the system in the EU
database.

**Annex VII (third-party assessment by a notified body)** is
mandatory for:

- Annex III point 1 (remote biometric identification, biometric
  categorisation, emotion recognition).
- AI systems where the provider has not applied harmonised standards
  (currently: any provider, since no standards are yet cited).
- AI systems embedded in Annex I regulated products (medical devices,
  machinery) -- here the sectoral conformity procedure governs.

Most NOUS-served use cases fall under **Annex VI**. NOUS dossiers
feed the provider's own internal review. For Annex VII paths,
the same dossier serves as the technical documentation the notified
body audits.

**Code reference:** `nous dossier`, `nous dossier-spec`,
`nous skill-export`.

---

## 16. How to generate the dossier from NOUS

This section captures a real end-to-end run on Server A, NOUS v5.5.0,
19 May 2026. Commands are verbatim; outputs are abbreviated where
indicated by `[...]`.

### Step 1: extract a template

```
$ nous templates extract cost_cap_emit_demo
Extracted: /tmp/s83_annex_iv_demo/cost_cap_emit_demo.nous
```

The extracted source declares a world with a 0.20 USD cost cap,
`max_ticks: 3`, and two souls running `claude-haiku-4-5 @ Tier3`.

### Step 2: verify with SMT proof and emit signed manifest

```
$ nous verify cost_cap_emit_demo.nous --smt \
    --manifest-out cost_cap_emit_demo.manifest.json

Parsed cost_cap_emit_demo.nous: world=EmitDemo, souls=2
Loaded pricing: layer 4, 10 models, sha256 aa5c9f64e6b23c54...
Emitted SMT-LIB: spec sha256 29f24beda5419c38...
Running solver (timeout 30000ms)...

------------------------------------------------------------
World:        EmitDemo
Solver:       z3 4.16.0
Elapsed:      30ms
Spec sha256:  29f24beda5419c38...
------------------------------------------------------------
PROVEN: total_cost <= $0.2 USD across all execution paths.
  bounded by: 2 soul(s) x 3 ticks

Manifest signed: cost_cap_emit_demo.manifest.json
  key:    /root/.local/share/nous/keys/signing.key
  sha256 spec: 29f24beda5419c3881a2e0642297ed15834a4d60701a7a65073e465878748044
```

### Step 3: emit the Annex IV dossier

```
$ nous dossier cost_cap_emit_demo.nous --anchor none --format annex_iv

Dossier emitted: /tmp/s83_annex_iv_demo/cost_cap_emit_demo_dossier_20260519T170113Z
  world:    EmitDemo
  verdict:  proven
  files:    6
    - source.nous
    - manifest.json
    - pricing.toml
    - public_key.b64
    - README.md
    - verify_offline.py
```

The emitted manifest contains 15 fields:

```
$ cat <dossier>/manifest.json | python3 -c "import sys, json; \
    print(json.dumps(sorted(json.load(sys.stdin).keys()), indent=2))"

[
  "cost_cap_usd",
  "elapsed_ms",
  "max_ticks",
  "nous_version",
  "pricing_sha256",
  "schema_version",
  "signature",
  "smt_emit_version",
  "smt_spec_sha256",
  "solver_name",
  "solver_version",
  "source_sha256",
  "timestamp_utc",
  "verdict",
  "world_name"
]
```

### Step 4: offline verification

```
$ cd <dossier> && python3 verify_offline.py manifest.json --allow-unanchored

OK   Ed25519 signature verified
OK   source.sha256 matches manifest (23ec3894eb31d396...)

VERDICT: PASS
  world:      EmitDemo
  cost_cap:   $0.2 USD
  verdict:    proven
  solver:     z3 4.16.0
  timestamp:  2026-05-19T17:01:12+00:00
```

The verifier requires only the `cryptography` library (no NOUS
install needed). Two checks are run: Ed25519 signature validation and
source SHA-256 match.

### Step 5: (optional) Rekor anchoring

Replace `--anchor none` with `--anchor rekor` in step 3 to also embed
a Sigstore Rekor inclusion proof in the manifest. The offline verifier
then additionally validates the inclusion proof against the pinned
Sigstore key allowlist. See [REKOR_ANCHOR.md](REKOR_ANCHOR.md).

### Step 6: (alternative) emit from SKILL.md sidecar

For agentskills.io-compatible projects, `nous dossier-spec <skill_dir>`
produces the same dossier shape from a SKILL.md + nous.yaml pair. See
[SKILL_MD_SIDECAR.md](SKILL_MD_SIDECAR.md).

---

## 17. Glossary

The vocabulary below is used consistently across NOUS documentation
and dossiers. Definitions are operational, not legal.

- **Obligation shell** -- the policy block declared in a NOUS source
  that binds the system to specified deny/require rules.
- **Requester / Authority** -- the two principals in any policy
  evaluation: the Requester asks for an action, the Authority decides.
- **Admission / Admissibility** -- whether a policy admits a given
  request given the current state.
- **Attestation primitive** -- the Ed25519 signature over canonical
  manifest bytes; the cryptographic root of trust for a NOUS dossier.
- **Governed artifact** -- any NOUS-produced file whose manifest is
  signed and (optionally) Rekor-anchored.
- **Governance trace** -- the chained event log produced by an agent
  run; serves as the post-market monitoring evidence.
- **Execution lineage** -- the chain of declarations, validations,
  and code generations from source to running program.
- **Derived admission state** -- the cumulative result of policy
  evaluations across a run.
- **Verdict** -- `ACCEPT` or `REJECT` in the V2 verify-dossier
  response, deterministically computed from policy plus checks.
- **Trust level** -- `rekor_anchored | ed25519_only | none`,
  describing the strength of the dossier's transparency chain.

---

## 18. References

**Regulation:**

- Regulation (EU) 2024/1689 (the AI Act), Annex IV, Article 11,
  Article 14, Article 9, Article 43.
- AI Act Service Desk: https://ai-act-service-desk.ec.europa.eu/

**Digital Omnibus on AI:**

- Council provisional agreement, 7 May 2026, consilium.europa.eu.
- Council presidency letter to European Parliament, 13 May 2026.

**Standards:**

- CEN-CENELEC JTC 21 work programme.
- prEN 18229-1 (logging, transparency, human oversight).
- prEN 18286 (quality management system for AI Act).
- prEN 18285 (conformity assessment framework).

**NOUS documentation:**

- [EU_AI_ACT_COMPLIANCE.md](EU_AI_ACT_COMPLIANCE.md) -- article-by-article matrix.
- [VERIFY_DOSSIER.md](VERIFY_DOSSIER.md) -- V2 verify-dossier surface.
- [REKOR_ANCHOR.md](REKOR_ANCHOR.md) -- transparency log anchoring.
- [SKILL_MD_SIDECAR.md](SKILL_MD_SIDECAR.md) -- skill folder dossiers.
- [SKILL_EXPORT.md](SKILL_EXPORT.md) -- agentskills.io export.
- [SMT_VERIFICATION_DESIGN.md](SMT_VERIFICATION_DESIGN.md) -- soundness contract.
- [COST_VERIFICATION_GUIDE.md](COST_VERIFICATION_GUIDE.md) -- end-to-end walkthrough.

**NOUS blog:**

- "Your Stop Button Is Not Article 14 Compliance" (Session 78,
  2026-05-16), nous-lang.org/blog.
- "NOUS v5.5.0 -- A Verdict, with Evidence" (Session 82,
  2026-05-17), nous-lang.org/blog.

---

*Last updated: Session 106, 31 May 2026 (HEAD: `3298388`, v5.24.0).*

<!-- __session83_annex_iv_mapping_v1__ __session106_annex_iv_mapping_v5_24_0_v1__ -->

---

## Appendix: the signed Annex IV evidence-map sidecar (v5.38.0)
<!-- __s135_annex_iv_sidecar_appendix_v1__ -->

`nous dossier --annex-iv-map` (default off) emits, alongside the dossier,
two files that make the crosswalk above machine-checkable offline:

- `annex_iv_map.json` -- a signed index. For each of the nine Annex IV
  items it records the canonical title, a clause kind (`evidence-backed`,
  `documentation-clause`, or `operator-responsibility`), and zero or more
  evidence references. Each reference names a file already present in the
  dossier and pins its sha256 over the raw file bytes. The whole map is
  bound to the dossier by `manifest_canonical_sha256` (the sha256 of the
  manifest canonical body, signature and transparency_log stripped) and
  signed Ed25519.
- `verify_annex_iv_map.py` -- a self-contained verifier. It requires only
  `cryptography` and the standard library; no NOUS install, no network, no
  solver. It re-runs four checks, fail-closed: (1) the map signature over
  its canonical body; (2) the dossier binding; (3) for every reference,
  the file is present and its sha256 matches; (4) indexing completeness --
  exactly the nine canonical items, each with the canonical title and a
  clause kind consistent with its evidence (evidence-backed items index at
  least one reference; documentation-clause and operator-responsibility
  items index none, so the sidecar cannot over-claim).

Boundary. A passing `verify_annex_iv_map.py` proves presence, authenticity,
and indexing of the declared evidence. It does NOT prove legal sufficiency,
does NOT prove that a referenced artifact actually satisfies its Annex IV
item, and does NOT prove anything about execution conformance. The sidecar
is orthogonal to `verify_offline.py` (which proves the cost-cap / coverage
claim) and is never folded into it. It is refused on a coverage-gap-witness
(refutation) dossier, since an evidence index over a refutation artifact is
incoherent.
