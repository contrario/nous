# VERIFIER CORE INTEGRITY -- DESIGN

Status: DRAFT for sign-off (S130). ASCII-only. Target repo path:
docs/VERIFIER_CORE_INTEGRITY_DESIGN.md

This document specifies a foundations-first arc that hardens the emitted
offline verifier (verify_offline.py) -- the Trusted Computing Base of the
entire NOUS evidence proposition -- against silent drift, without changing
a single byte of any shipped dossier. Every unit is test-only or
byte-preserving. No release, no version bump, no manifest field, no PyPI.


## 1. Problem (from live source, S130)

The offline verifier is the only thing a third party runs to check a NOUS
dossier. All trust rests on it being correct. In proof-carrying-code /
de Bruijn terms it is a small certificate checker: the Farkas multipliers
are the certificate, the rational-arithmetic check is the kernel, and the
kernel must be small, single, and independently auditable.

The live source violates that shape. The admit/refuse logic is replicated
across multiple hand-maintained copies, synchronized only by a source
comment ("shared text; do not edit one copy without the other"). No test
enforces agreement.

### 1.1 Topology of the duplication (dumped S130)

| Logic | Production (issuer side) | Embedded (verifier side) |
|-------|--------------------------|--------------------------|
| minilang parser + policy scanner | coverage_minilang.py (lines 15-306, markers __s124_minilang_core_v1__ .. "end minilang core") | dossier.py VERIFY_OFFLINE_PY_BUNDLE (226); VERIFY_OFFLINE_PY_CHAIN_BUNDLE (878) |
| linear translation + NNF/DNF + canon + multiplier check | coverage_farkas.py (serialize_bundle, check_serialized_bundle, _check_multipliers, _gap_disjuncts, _canon_system, ...) | farkas embed inside BUNDLE (226) and CHAIN_BUNDLE (878) |
| v1 single-system multiplier check | coverage_farkas.check_serialized (462) | _check_serialized inside FARKAS (s116), CHAIN (s120), CHAIN_BUNDLE |
| hop-containment check | coverage_farkas.check_serialized_hop_bundle (1127) | check_hop_bundle inside CHAIN_BUNDLE |

Two distinct relationships, and they must be treated differently:

- minilang: the embed is intended to be a TEXTUAL COPY of
  coverage_minilang.py. Single source is achievable.
- farkas: the embed is a RE-IMPLEMENTATION, not a copy. Production carries
  type annotations and a frozen dataclass LinIneq; the embed is
  annotation-free with a hand-written __init__ and stdlib-only imports.
  Function names even differ (production check_serialized_bundle vs embed
  check_bundle_against_derived). This is N-version by construction.

### 1.2 Why this is the load-bearing risk

The worst failure is not "template bytes drifted". It is the embedded
checker silently diverging from the issuer such that the SHIPPED verifier
admits a forged bundle the issuer would reject. Nothing downstream
re-checks the verifier. A byte-hash regression guard alone does not catch
this: a legitimate edit re-blesses the baseline and a semantic divergence
sails through. The agreement must be PROVEN, not asserted by comment.


## 2. Axioms served

- Axiom 1 (single source of truth, derived everywhere else): minilang is
  collapsed to one source; the farkas N-version is made an explicit,
  pinned, differentially-proven decision rather than an unguarded copy.
- Axiom 2 (determinism produces evidence): the emitted verifier becomes
  byte-deterministic from a single source for the minilang section, with
  a snapshot guard over the whole emitted verifier.
- Axiom 8 (no silent merges / drift across discriminators): drift between
  issuer and verifier becomes a loud test failure (same pattern as the
  existing test_offline_verifier_v2_equiv.py GAP1 gate).
- North-star: after this arc a third party still verifies offline with
  cryptography + stdlib (z3 optional). Nothing in the trust path changes;
  the trust surface SHRINKS.


## 3. Existing primitives to reuse (no invention)

- offline_verifier_builder._extract_segments(module_path, symbol_names,
  pins): AST-extracts named top-level symbols from a module as source
  text, SHA-pins each segment against a pins dict, and refuses on drift
  (OfflineVerifierBuildError). Already used to assemble the Rekor v2
  verifier (build_offline_verifier_v2). This is the splice+pin mechanism
  for U3.
- The equivalence-test pattern from test_offline_verifier_v2_equiv.py:
  compile() + exec() the emitted verifier source into an isolated
  namespace (no pydantic permitted), then drive its functions and compare
  to the in-package implementation over a fixture. This is the harness
  pattern for U1.
- Production entry points (verified live, S130):
  - coverage_farkas.serialize_auto / serialize_bundle / serialize_system
    (issuer build)
  - coverage_farkas.check_serialized_bundle(doc, threshold_ast,
    blocking_signals); coverage_farkas.check_serialized(doc) (v1)
  - coverage_minilang.derive_disjunct_constraints(source_text,
    threshold_expr) -> dict; coverage_minilang.bundle_cert_keys(doc) -> set
  - coverage_minilang.ml_parse / ml_scan_blocking_signals
- Embed entry points (extracted by exec of the template):
  - derive_disjunct_constraints(source_text, threshold_expr)
  - check_bundle_against_derived(doc, derived)
  - _check_multipliers, ml_parse, ml_scan_blocking_signals


## 4. Unit sequence (foundations-first)

Each unit ships independently, leaves all dossiers byte-identical, and is
guarded by the prior unit. PYTEST_FLOOR rises per unit. Per-unit commit,
per-arc push.

### U1 -- Differential equivalence harness (test-only)

Exec the BUNDLE and CHAIN_BUNDLE templates into isolated namespaces. Build
an adversarial corpus of (source_text, threshold_expr, bundle_doc) cases:

- in-fragment QF_LRA: single comparison; conjunction; disjunction; nested
  boolean near DISJUNCT_BOUND.
- boundary: strict vs non-strict at a shared threshold boundary.
- out-of-fragment (must REFUSE identically): bilinear var*var; string
  literal; trailing tokens; unbalanced parens/braces.
- forged bundles (must FAIL identically): omitted disjunct; surplus cert;
  duplicate cert; negative multiplier; wrong multiplier; substituted
  constraint.

Assertions per case:

1. embed pipeline verdict (derive_disjunct_constraints ->
   check_bundle_against_derived) == production verdict
   (coverage_minilang.derive_disjunct_constraints +
   coverage_farkas.check_serialized_bundle), including the typed-refuse
   class on out-of-fragment input.
2. ORACLE: a known-no-gap bundle built by coverage_farkas.serialize_auto
   verifies PASS under the embed; a known-gap source is rejected; where a
   coverage.smt2 is available, z3 returns unsat in agreement.

Soundness note (section 5) dictates the oracle is mandatory, not optional.

Acceptance: widens determinism? no. Sharpens evidence? yes (proves the
N-version farkas embed decides identically to the issuer). Offline
crypto+z3 property? unchanged. Trust creep? reduces trust surface. PASS.
Risk: none (test-only).

### U2 -- Emitted-verifier snapshot + embed-region pin (test-only)

Two guards in one unit:

1. Whole-verifier snapshot: SHA each emitted verifier source against a
   stored baseline -- every VERIFY_OFFLINE_PY_* constant in dossier.py,
   plus build_offline_verifier_v2() and build_chain_net_verifier() output.
   Deterministic (no signatures involved). Any byte change turns it red;
   intended changes re-bless the baseline in the same patch.
2. Embed-region pin: assert the minilang section embedded in BUNDLE and
   CHAIN_BUNDLE equals coverage_minilang.py's marked region byte-for-byte
   (see OPEN ITEM 6.1), and the farkas embed matches a recorded SHA in
   both templates.

This is the real version of the dead S128/S129 "dossier regression"
item: it guards emitted-verifier CONTENT, which test_dossier_regression.py
(filename-only) and regression_harness.py (codegen-only) do not.

Acceptance: sharpens evidence (loud drift). PASS. Risk: none (test-only).

### U3 -- Single-source the minilang section (byte-preserving refactor)

LOCKED byte-preserving (OPEN 6.1 closed S130). The minilang section
embedded in BUNDLE and CHAIN_BUNDLE is byte-identical to a contiguous
verbatim region of coverage_minilang.py, header comment included:

  region  = HEADER ("# --- minilang core ...") .. END
            ("# --- end minilang core ---"), inclusive
  length  = 8473 bytes
  sha256  = 8c9e41b45c4efdd3bdd61e99fff5cb1f2800031bc362b6b7a70a498c38d1fc0e
  (marker-only START..END region: 7983 bytes, sha 9d9b630f...; both embeds
   agree with each other and with production.)

Therefore U3 turns BUNDLE and CHAIN_BUNDLE from hardcoded full strings into
ASSEMBLED strings (the build_offline_verifier_v2 pattern): a SHA-pinned
helper reads coverage_minilang.py, slices the HEADER..END region VERBATIM
(NOT _extract_segments AST-join, which re-joins symbols with "\n\n" and
would alter inter-symbol spacing), and splices it at the same anchors. The
emitted verifier bytes are unchanged; U2's snapshot stays green. After U3
there is ONE minilang source; both embeds are derived, not maintained. Pin
8c9e41b4... refuses on any future minilang edit until re-blessed.

Acceptance: single-source axiom; byte-identical dossiers; guarded by
U1+U2. PASS. Risk: low (U2 is the net).

### U4 -- Farkas N-version: keep, document, pin (no refactor)

Explicit decision: the farkas embed stays an independent re-implementation.
N-version independence is a TRUST PROPERTY (an issuer bug that emits a bad
bundle is caught by a separately-written checker), not a defect to collapse.
U1 proves behavioral agreement; U2 pins the embed bytes; a short docs note
records the decision so a future session does not "fix" it by collapsing.

Acceptance: refuse-to-over-engineer; preserves N-version trust. PASS.


## 5. Soundness of the differential method

Differential testing has a known blind spot: two implementations sharing
ancestry can be wrong in the same way, and the diff cannot see it (the
classic compiler/verifier-testing limitation). This arc addresses it
directly:

- The farkas layer is a genuine 2-version pair (independent
  re-implementation), so embed-vs-production farkas IS a real differential
  that catches divergent bugs.
- The minilang layer is a copy, so embed-vs-production minilang is a weak
  differential. Therefore U1's ORACLE (z3 + hand-labeled ground-truth
  gap/no-gap cases) is mandatory: it catches a bug present in BOTH minilang
  copies, which the pure differential cannot.

The combination -- genuine N-version on farkas, plus an external oracle on
the shared minilang -- is what makes U1 sound rather than self-referential.


## 6. Open verification items (close before locking the affected unit)

6.1 CLOSED (S130, probe sha a80201c2...). The minilang embed in BUNDLE and
    CHAIN_BUNDLE is byte-identical to coverage_minilang.py's HEADER..END
    region (8473 bytes,
    sha 8c9e41b45c4efdd3bdd61e99fff5cb1f2800031bc362b6b7a70a498c38d1fc0e),
    header comment included; both embeds also agree with each other. U3 is
    locked byte-preserving via verbatim header-inclusive splice.

6.2 (informs U2 baseline) full enumeration of which templates embed the
    farkas/minilang logic, and how build_chain_net_verifier (dossier.py
    903) splices via _NET_EMBED_ANCHOR (893), is partially dumped.
    build_chain_net_verifier internals not yet read; enumerate before
    freezing the U2 baseline so no embed copy is missed.


## 7. Non-goals and horizon

Non-goals this arc: no change to any shipped dossier; no new manifest
field; no new proof obligation; no collapse of the farkas N-version.

Horizon (named, deferred, do NOT open here): succinct recursive chain
coverage. The chain verifier is O(n) (full mode carries every prior source
and re-scans). The principled long-term form is incrementally verifiable
computation via accumulation/folding (ProtoStar 2023; Nova / HyperNova,
CRYPTO 2024) -- but those require finite-field R1CS/Plonk with
elliptic-curve commitments, which would break the current "cryptography +
z3 + stdlib only" offline property and fail the north-star acceptance test
as stated. The NOUS-native cheap analog worth a dedicated design session is
a Merkle accumulator over per-link obligation digests (stdlib hashing) for
O(1)-carry chain integrity, keeping the Farkas per-hop coverage check.
U3 (single-source) is a prerequisite for any such work: a recursive proof
system cannot be built on hand-copied checker logic.


## 8. OPEN ITEM 6.1 -- CLOSED (S130)

Closed by probe_s130_minilang_identity.py (sha a80201c2...). The minilang
section is a verbatim contiguous region of coverage_minilang.py
(HEADER..END inclusive, 8473 bytes, sha 8c9e41b4...), byte-identical across
both templates and production, header comment included. U3 splice =
verbatim header-inclusive region; pin = 8c9e41b4....

Still open: 6.2 (build_chain_net_verifier splice enumeration) before the
U2 baseline is frozen.


## 9. References (state of the art)

- Differential testing: McKeeman 1998; Yang et al., "Finding and
  Understanding Bugs in C Compilers" (CSmith), PLDI 2011. Known blind spot
  for shared-ancestry implementations: Dafny verifier-testing experience
  (ISSTA 2022).
- Small trusted checker: de Bruijn criterion; proof-carrying code (Necula);
  LFSC / DRAT-trim certificate checkers; minimal-TCB PCC checkers.
- Translation validation (the U3 framing -- a verified validator rather
  than a verified transformer): Pnueli et al.; CompCert backend.
- Horizon: Valiant (IVC); Bitansky-Chiesa-Tromer (PCD); Nova / HyperNova
  (folding); ProtoStar (accumulation).
