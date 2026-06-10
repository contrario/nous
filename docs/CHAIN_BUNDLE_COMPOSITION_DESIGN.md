# Chain + Bundle Composition -- Design Freeze (S125)

Status: FROZEN -- accepted (S125, Option 3). No code precedes this freeze.
Committed to docs/CHAIN_BUNDLE_COMPOSITION_DESIGN.md at code time (U4).
Scope: lift the build-time refuse of "chain + Farkas DNF bundle" and define
the offline verifier that walks an envelope-binding chain whose CURRENT link
carries a disjunctive-linear-bundle coverage proof.

This document is the single source of truth for the S125+ composition unit.
When the feature ships it lands at docs/CHAIN_BUNDLE_COMPOSITION_DESIGN.md in
the same release window as the code.

--------------------------------------------------------------------------------
## 1. The question

Section 7 item 1 of the S124 handoff posed two sub-problems and one decision:

  (a) the chain verifier's monotonicity reader consumes doc["constraints"][0];
      bundle docs carry a top-level threshold_constraint instead (emitted by
      coverage_farkas.py, reader not yet taught).

  (b) THE blocker: chain/ carries no per-link source.nous, so per-link bundle
      RE-DERIVATION has no signed source for prior links.

Decision required: how to compose chain and bundle without enlarging the trust
surface for an offline third party holding only cryptography + stdlib
(+ optional z3). North-star test governs.

--------------------------------------------------------------------------------
## 2. Byte-confirmed current state (S125, HEAD 7783e13)

chain/ contents (writer dossier.py ~534-538; carry type dossier.py:360
`chain_links: list[tuple[bytes, "bytes | None"]]`):
  - chain/NNN_manifest.json        (prior link manifest bytes)
  - chain/NNN_coverage.farkas.json (prior link farkas sidecar, when present)
  - NO chain/NNN_source.nous. No prior-link signed source is carried.

VERIFY_OFFLINE_PY_CHAIN (dossier.py:210, __s120_chain_verifier_v1__):
  - chain walk (signature / hash-chain / single-genesis / no-op-rebinding /
    cycle) operates on manifest bytes ONLY -- fragment-agnostic, already
    correct for a bundle-bearing link.
  - _check_coverage -> _check_serialized reads TOP-LEVEL constraints/
    multipliers. This is the v1 single-comparison shape. A CURRENT-link
    bundle (certs array, no top-level constraints/multipliers) FAILS here
    today, before the chain walk is even reached.
  - _authenticated_threshold reads doc["constraints"][0] as the threshold
    inequality for monotonicity. v1-only; KeyErrors / mis-reads on a bundle.

VERIFY_OFFLINE_PY_BUNDLE (dossier.py:226, __s124_dossier_bundle_v1__):
  - re-derives the gap disjunct set from the SIGNED root source.nous
    (sha-gated) + the sha-gated threshold_expr carried in the farkas doc,
    requires a bijection against the carried certs, checks each cert's
    multipliers against the RE-DERIVED constraints. Carried constraints are
    display-only. Standalone single link; performs NO chain walk.

coverage_farkas.py:923: doc["threshold_constraint"] = _canon_constraint(...)
  - top-level in a bundle doc, emitted ONLY when the threshold T is a single
    comparison (boolean T -> no single threshold_constraint).

Build-time refuse (dossier.py:371, the honest boundary shipped in S124):
  "chain + Farkas bundle not yet supported: the chain verifier ..."

--------------------------------------------------------------------------------
## 3. The two sub-problems, restated from bytes

(a) is a READER fix, not a trust question. Both v1 constraints[0] and bundle
    threshold_constraint are SIGNED (inside the farkas doc, sha-gated by the
    signed manifest's coverage_farkas_sha256). Teaching the reader to branch
    on fragment changes WHERE it reads the threshold inequality; it changes
    NOTHING about what is trusted.

(b) is the real design question, but it is conditional: per-link RE-DERIVATION
    is required only to prove per-link COMPLETENESS (the carried disjunct set
    is the COMPLETE gap set, no omission). Monotonicity does NOT require it.
    Current-link completeness does NOT require it (root source.nous exists).
    The blocker only bites if we choose to claim prior-link completeness.

--------------------------------------------------------------------------------
## 4. Options weighed against the north-star test

North-star: after this lands, can a third party verify offline, with only
cryptography + stdlib (+ optional z3), within the declared envelope, WITHOUT
trusting the issuer more than before?

Option 1 -- carry per-link source.nous (chain/NNN_source.nous):
  Claim: full per-link completeness, each prior link's bundle re-derived from
  its OWN signed source, sha-gated by that link's signed source_sha256
  (a sha-bearing field already present in every chain manifest).
  Trust surface: UNCHANGED. Identical re-derivation, applied per link.
  Cost: dossier size grows by every historical source; historical policy
  source is exposed in every shipped dossier (privacy).
  Verdict: sound, strictly more evidence, but pays a size+privacy cost that
  is NOT required for the v1 honest boundary. DEFER (see section 6).

Option 2 -- check prior carried multipliers only, still CLAIM completeness:
  For prior links, verify that carried multipliers collapse carried
  constraints to a contradiction, without re-deriving the disjunct SET.
  Trust surface: ENLARGES. With no source to re-derive the COMPLETE gap set,
  an issuer may OMIT a gap disjunct and the prior-link check still passes.
  This is precisely the overclaim-by-omission attack S124 manufactures
  protection against at issuance. "Stated honestly" does not rescue it: the
  evidence regresses -- a third party can no longer verify prior-link
  no-gap offline, only that an issuer-chosen subset is individually unsat.
  Verdict: REJECT. Regresses the property; violates north-star.

Option 3 -- monotonicity-only on the signed threshold_constraint; current
link fully re-derived:
  Split the two claims the chain verifier conflated.
  - Current link: prove COMPLETENESS by bundle re-derivation from the root
    signed source (exists). Carried constraints stay display-only.
  - Prior links: assert only region MONOTONICITY using each link's SIGNED
    threshold inequality (v1: constraints[0]; bundle: threshold_constraint).
    Do NOT re-prove prior completeness; do NOT claim it.
  Trust surface: UNCHANGED. threshold_constraint is signed; monotonicity is
  closed-form (_region_contains). No issuer enumeration is trusted.
  This is exactly the S121 monotonicity semantics ("the DECLARED blocking net
  did not shrink -- NOT that the system is safer"), now extended to admit
  bundle links, and STRICTLY STRONGER than S121 because the current link's
  boolean-net completeness is proven (S121 only handled v1 single-comparison
  current-link coverage).
  Cost: zero new bytes in chain/; zero new trust.
  Verdict: FREEZE as v1.

--------------------------------------------------------------------------------
## 5. FROZEN DECISION

v1 chain + bundle composition = Option 3.

  - The build-time refuse at dossier.py:371 is lifted for the chain+bundle
    case and replaced by emission of a MERGED verifier whose chain walk admits
    a bundle-bearing current link and whose monotonicity reader branches on
    fragment.
  - Prior-link claim is MONOTONICITY ONLY. The verdict text states explicitly
    that prior-link completeness is NOT re-proven offline (only the current
    link's is), and that monotonicity proves declared-net non-shrink, not
    safety.
  - A prior (or current) bundle link whose threshold T is boolean (no
    top-level threshold_constraint) yields a TYPED monotonicity REFUSE for
    that hop -- never a silent skip, never a pass. Region containment is
    single-half-space geometry; a boolean threshold has no single region.
    This reuses the existing INCOMPARABLE refuse pattern.

Option 2 is rejected permanently. Option 1 is deferred (section 6).

--------------------------------------------------------------------------------
## 6. Deferred: Option 1 enrichment (NOT this unit)

Carrying per-link source.nous to prove prior-link completeness is a future,
OPT-IN enrichment, gated before any code by:

  - a manifest/dossier discriminator (source_kind or a chain_carries_source
    flag) so a chain WITHOUT carried sources and a chain WITH them are never
    silently merged (axiom 8: no silent merges across discriminators);
  - the dossier-size / privacy research the S125 opener placed in scope:
    whether historical policy source must be carried in full, hashed-only
    with selective disclosure, or redacted; what a banking counterparty
    (FinQuest) tolerates in a shipped dossier. This research is a PRECONDITION
    for sealing the Option 1 design, not for this freeze.

Until that work, the honest boundary is Option 3: current link proven, prior
links monotonic.

--------------------------------------------------------------------------------
## 7. What v1 entails (unblocks the next unit; no code here)

Single new merged template, assembled from the SAME authored text blocks as
the repo modules (one authoring point, zero logic drift -- the S124 U3
discipline): chain-walk blocks (from VERIFY_OFFLINE_PY_CHAIN) + minilang core
+ farkas embed (from VERIFY_OFFLINE_PY_BUNDLE).

  1. Current-link coverage check: fragment branch.
       v1 farkas doc      -> existing _check_serialized path.
       disjunctive-linear-bundle -> read threshold_expr, re-derive disjuncts
         from ROOT source.nous, bijection + per-disjunct multiplier check
         (the VERIFY_OFFLINE_PY_BUNDLE logic).
       fragment sniff is fail-closed (reuse _is_bundle_farkas precedent).

  2. Monotonicity reader (_authenticated_threshold): fragment branch.
       v1    -> doc["constraints"][0].
       bundle, threshold_constraint present -> that inequality.
       bundle, threshold_constraint absent (boolean T) -> typed REFUSE hop.
     Output object shape is identical ({coeffs, strict}); _region_contains
     and _mono_vars are unchanged and operate on either.

  3. dossier.py selector: when prior_digest is set AND the current coverage is
     a bundle, emit the merged template instead of refusing. The chain+rekor
     refuse (dossier.py:362-365) is untouched and still applies.

  4. The chain walk proper, _SHA_BEARING_FIELDS, genesis/no-op/cycle logic are
     copied verbatim -- fragment-agnostic, no change.

  5. Tests: chain depth>=1 with a bundle current link PASS; bundle current link
     with a known gap FAIL; v1-prior -> bundle-current monotonic PASS;
     bundle-prior (single-comparison T) monotonic PASS; boolean-T prior hop
     REFUSE; omission/forgery/substitution/duplicate attacks on the current
     bundle still FAIL through the merged template; chain+rekor still REFUSED.
     Plus e2e subprocess (rc=0 "bijection holds" + chain verdict).

  6. Release discipline: if the merged template is a new authored constant in
     dossier.py it needs no new top-level module (no pyproject/wheel-gate
     change). Confirm at code time whether any new module is introduced; if
     so, dual-register in the SAME patch.

--------------------------------------------------------------------------------
## 8. Honest boundary after v1 lands

A third party, offline, with cryptography + stdlib (+ optional z3), can verify:
  - Ed25519 over the current manifest canonical body.
  - source.nous sha == manifest.source_sha256.
  - the CURRENT link's coverage claim: for a bundle, the complete gap disjunct
    set re-derived from the signed source, bijection holds, every disjunct
    refuted by rational arithmetic -- zero issuer trust, zero solver trust.
  - an unbroken envelope-binding chain rooted at genesis (signatures,
    hash-chain, real build changes, no cycle).
  - declared-threshold region MONOTONICITY across hops where both links carry
    a single-comparison threshold inequality.

A third party CANNOT, after v1:
  - re-prove PRIOR links' coverage completeness offline (no per-link source is
    carried; this is Option 1, deferred). Prior links are asserted monotonic
    on their signed thresholds, not re-proven complete.
  - assert monotonicity across a hop whose threshold is boolean (refused).
  - compose chain with rekor (separately refused, unchanged).

What can be verified offline GREW (boolean current-link coverage inside a
chain). What must be trusted did NOT.

--------------------------------------------------------------------------------
## 9. Invariants preserved

  - Refuse over guess: every fragment mismatch, missing threshold_constraint,
    and unsupported composition is a typed refuse with a cause-first message.
  - No solver in the verifier: enumeration from signed source only; z3 stays
    an optional second opinion.
  - Carried constraints display-only (current link): re-derivation, not the
    bundle's own enumeration, is what is believed.
  - Single authoring point: merged template assembled from the same text
    blocks as the repo modules; no logic fork.
  - No silent merges across discriminators (axiom 8): Option 1 gated behind an
    explicit carry discriminator before it can ship.
  - Single source of truth: threshold inequality is always read from signed,
    sha-gated data, never reconstructed by the verifier.

--------------------------------------------------------------------------------
## 10. Non-goals

  - Proving prior-link completeness (Option 1, deferred).
  - Boolean-threshold region monotonicity (no single-region geometry; refused).
  - chain + rekor composition (separately refused; out of scope here).
  - Execution conformance (the chain proves formation lineage, not behavior).

--------------------------------------------------------------------------------
## 11. Sign-off gate

Code begins only after this freeze is accepted. Open points needing an explicit
yes/no before the first patch:

  - Confirm v1 = Option 3 (monotonicity-only on prior links, current link fully
    re-derived). If prior-link completeness is wanted now, this reopens as
    Option 1 and the size/privacy research must precede code.
