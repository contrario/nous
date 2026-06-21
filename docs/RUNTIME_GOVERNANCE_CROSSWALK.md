# Runtime Governance Crosswalk

This document maps NOUS primitives to the framework-neutral concepts of
"runtime governance" -- an execution-time governance category articulated
independently of NOUS by Willis (2026), "Operationalizing Secure-by-Design AI
Through Deterministic Runtime Governance" (Sustainable Future Tech, Inc.;
Zenodo DOI 10.5281/zenodo.20749457). The purpose is to situate NOUS within a
recognized architectural category and to state precisely where NOUS implements,
exceeds, or deliberately does NOT occupy that category's roles.

This is an internal positioning and orientation document. It is not a
conformance claim against any specification, and it is not an EU AI Act
compliance statement. Any external-facing EU AI Act framing derived from this
crosswalk goes through the designated review gate before publication.

## What runtime governance is (framework-neutral)

Willis identifies a gap in current AI governance: most frameworks (NIST AI RMF,
NIST CSF 2.0, NIST SP 800-53, ISO/IEC 42001, CISA Secure-by-Design, MITRE
ATLAS, OWASP Agentic AI, the EU AI Act) define governance objectives and
control expectations but give limited guidance on how governance is evaluated
at the point where a proposed action transitions into execution. He names this
the absence of an execution-layer governance architecture, and proposes
"runtime governance" as a complementary layer that evaluates admissibility,
validates authority and evidence, preserves canonical state, enforces refusal,
and maintains continuity at the commit boundary -- the point where proposed
intent becomes operational reality.

Three of his distinctions matter for NOUS:

- Authorization is not admissibility. Authorization asks whether an actor has
  the authority to act; admissibility asks whether execution remains
  appropriate under current conditions. An action may stay authorized while
  ceasing to be admissible.
- Determinism is not correctness. Deterministic governance guarantees that a
  decision is reproducible and auditable given the same inputs, policies,
  state, and evidence. It does not guarantee the decision is correct.
- Runtime governance is an architectural category, not a product. Multiple
  implementations may inhabit it. NOUS is one such implementation of the
  category's evidence and admissibility concepts.

## Crosswalk: NOUS primitive to runtime-governance concept

The mapping below uses Willis's framework-neutral terminology (his Appendix A
core terminology), not any proprietary requirement catalog. NOUS is not
conformant to, nor derived from, any specific runtime-governance specification;
the correspondence is conceptual.

| NOUS primitive (shipped) | Runtime-governance concept | Secure-by-Design objective |
|---|---|---|
| Obligation shell; Requester / Authority vocabulary | Execution-bound authorization | Least privilege, complete mediation |
| Admission / Admissibility verdict in the conformance certificate | Admissibility evaluation | Complete mediation, secure defaults |
| `law gated(<action>)` grammar; signed `smt_spec_sha256`; `kind=gated_action` trace | Commit-bound governance (evidence of) | Complete mediation, accountability |
| Signed manifest, execution trace, conformance certificate, VSA | Governance evidence and receipts; evidence continuity | Accountability, auditability |
| SLSA build provenance leg (S159-S161), Ed25519 over DSSE/in-toto | Evidence provenance | Auditability, supply-chain integrity |
| Byte-deterministic canonical serialization; `run_shas`; offline re-derivation | Governance replayability; deterministic governance | Auditability, forensic reconstruction |
| Dual-control N-of-M quorum (`co_authorizations`, `gated_quorums`) | Delegated / multi-agent authority governance | Least privilege, accountability |
| GLM `formation` layer; cross-party VSA registry | Governance interoperability | Resilience, accountability |
| Constitutional constraints compiled from `law` into signed specs | Governance compilation / constitutional governance | Secure defaults |
| Z3 cost-cap verification; Farkas coverage certificates | Machine-verifiable governance (a bounded, proven subset) | Operational assurance, auditability |
| Portable offline verifiers (cryptography + stdlib, zero install) | Independent verification of governance outcomes | Auditability, independent assurance |

## Where NOUS exceeds the conceptual baseline

The paper's scope explicitly stops at "deterministic does not mean correct" and
places formal verification and machine-verifiable governance in future work
(its sections 18.6, 18.7). NOUS goes past that baseline in four concrete ways,
each already shipped:

1. A bounded PROVES leg, not only reproducibility. For the cost cap and for
   policy coverage, NOUS does not merely make the decision reproducible -- it
   carries a Z3 / Farkas certificate that an independent party re-checks
   offline by rational arithmetic, with no solver and no NOUS install. Within
   that bounded scope the claim is proven, not merely evidenced. The paper's
   determinism bar is reproducibility; NOUS clears it for general governance
   and exceeds it where a proof exists.

2. Concrete cryptographic anchoring, not abstract receipt integrity. Willis
   describes governance-receipt integrity as a requirement. NOUS realizes it
   with named, standards-based mechanisms: Ed25519 signatures, DSSE / in-toto
   statements, SLSA provenance, Sigstore Rekor v2 transparency logging, and
   RFC 3161 trusted timestamps.

3. Supply-chain provenance over the governance system itself. The paper governs
   a system's actions; it does not address how the governing system was built.
   NOUS carries SLSA build provenance over its own released artifacts, with an
   offline verifier published at a fetchable well-known path.

4. A working, verifiable implementation. NOUS is a released system (PyPI,
   two production servers, a public site, a published offline-verification
   surface), not a reference architecture. Its evidence is third-party
   fetchable and re-derivable today.

## Where NOUS deliberately does NOT operate (monitor, not guard)

This is the most important honest boundary in the crosswalk, and it is a real
divergence, not a gap to close.

Willis's "structural refusal" PREVENTS execution: a warning informs; a
structural refusal stops the action at the commit boundary. That is a guard
role -- the governance layer sits in the execution path and blocks the commit.

NOUS is a monitor, not a guard. NOUS does not interpose in the execution path
to prevent an action. Its refusal semantics are about EVIDENCE, not execution:
a NOUS validator, verifier, or certificate emitter refuses to produce a
governed attestation when conditions are ambiguous or unmet (refuse-over-guess,
fail-closed), and a conformance certificate can record a non-conformant
verdict. NOUS makes inadmissibility observable, attributable, and offline-
verifiable; it does not itself stop the commit. Enforcement -- if any -- belongs
to the operator's surrounding system acting on NOUS evidence.

Stated plainly: NOUS implements the evidence, admissibility-evaluation,
replayability, and machine-verifiability concepts of runtime governance. It
does not implement structural-refusal-as-execution-prevention. Anyone mapping
NOUS onto a runtime-governance architecture should place it in the evidence and
assurance layers, not in the commit-blocking enforcement path.

## Machine-readable projection

Prose crosswalks are declarations. The NOUS discipline is to evidence, not
declare: every governance claim NOUS makes travels as a signed, offline-
verifiable artifact. This crosswalk is therefore backed by a machine-readable
coverage profile, `docs/governance_coverage_profile.json`, that binds each
runtime-governance concept to the NOUS evidence type that discharges it, using
the OSCAL Control Mapping Model relationship vocabulary (`equivalent-to`,
`subset-of`, `intersects-with`, `no-relationship`). The monitor-not-guard
boundary is encoded as explicit `no-relationship` rows -- the boundary is a
machine-readable field, not a prose disclaimer a tool would skip.

The committed profile is reference content: deterministic, sorted-key, ASCII,
but UNSIGNED, and not published to any well-known path. It is the source body
for a planned evidence type:

- Governance Coverage Attestation (GCA), roadmap. A DSSE-wrapped in-toto
  Statement (`predicateType` `https://nous-lang.org/governance-coverage/v1`,
  a vendor-namespaced custom predicate) whose subject is a NOUS release
  (wheel/sdist sha, bound to the existing provenance) and whose predicate is
  the coverage profile canonicalized in the standard NOUS compact sorted-key
  form. Ed25519-signed by the operator key, offline-verifiable by the same
  cryptography-plus-stdlib path as the provenance and VSA verifiers, and
  published at the well-known evidence root. Honest boundary: the GCA
  EVIDENCES authorship and integrity of the coverage claim; it does not PROVE
  the concepts are correctly implemented, and it asserts no conformance to any
  framework.

- OSCAL Control Mapping projection, roadmap. The same canonical body emitted
  additionally as a NIST OSCAL Control Mapping Model instance, so the coverage
  is consumable by the assurance tooling that NIST, CISA, and FedRAMP auditors
  already use (OSCAL becomes a FedRAMP submission requirement in 2026). This
  bridges two ecosystems that do not currently meet: OSCAL control mappings are
  not cryptographically signed, and in-toto attestations do not speak OSCAL
  control identifiers. The GCA carries one canonical body in both
  serializations. Honest boundary: NOUS would emit OSCAL-aligned content;
  OSCAL-conformant requires validation against the NIST schema, a separate
  deferred step, and is not claimed until it passes.

Neither projection is built yet. Both are scoped as a future evidence-surface
arc, parallel to the build-provenance leg; this document and the reference
profile are their human-readable and data-model seeds.

## Standards neutrality

The runtime-governance category, as Willis frames it, is deliberately
framework-neutral and is positioned as complementary to (not a replacement for)
NIST, ISO, CISA, MITRE, OWASP, and EU AI Act guidance. This crosswalk inherits
that neutrality. It maps NOUS to the category's concepts, not to any single
specification's proprietary requirement catalog, and it does not assert
conformance to any of them. Where NOUS evidence is relevant to a specific
regime -- for example, EU AI Act Annex IV record-keeping -- that mapping is
maintained separately and is subject to the designated review gate.

## References

- Willis JM. Operationalizing Secure-by-Design AI Through Deterministic Runtime
  Governance. Sustainable Future Tech, Inc.; 2026. Zenodo. DOI:
  10.5281/zenodo.20749457.
- NIST OSCAL (Open Security Controls Assessment Language), Control Mapping
  Model. https://pages.nist.gov/OSCAL/
- in-toto Attestation Framework. https://github.com/in-toto/attestation
- Machine-readable coverage profile: docs/governance_coverage_profile.json
- NOUS evidence model and honest-boundary discipline: see
  docs/EU_AI_ACT_COMPLIANCE.md, docs/SLSA_PROVENANCE.md,
  docs/SMT_VERIFICATION_DESIGN.md, docs/COST_VERIFICATION_GUIDE.md.
