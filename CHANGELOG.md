# Changelog

<!-- __session71_changelog_unreleased_v1__ -->

## [Unreleased]  <!-- __s105_changelog_ladder_v1__ -->

<!--
  Add bullets here under the headings below as work lands on `main`
  between releases, then promote into a versioned heading at release.
  Headings (Keep a Changelog 1.1.0): Added / Changed / Deprecated /
  Removed / Fixed / Security.
-->

## [5.42.0] - 2026-06-15  <!-- __s142_changelog_v5_42_0_v1__ -->
### Added
- Runtime gated-action emission: the conformance trace recorder now
  routes every occurrence whose action label is in the signed gated
  set (`SMTSpec.gated_actions`) to `kind=gated_action` instead of
  `kind=message`, so an honest runtime labels every gated occurrence
  with no manual step. New `run_shas.compute_run_gated_actions(source)`
  derives the set from the same `emit_smt` path that produces
  `smt_spec_sha256` and that the verifier re-derives, so producer
  emission and verifier check agree by construction; wired into both
  compiled-path recorder build sites (`compiled_trace.py`,
  `nous_ast_runner`). `TraceRecorder.__init__` gains an optional
  `gated_actions` parameter (default empty, byte-identical to prior
  traces). Closes the honest-but-careless issuer: a `gated_action`
  event without a valid approver attestation fails conformance
  obligation #5. PYTEST_FLOOR 1620 -> 1636.
### Changed
- Documented honest boundary in `docs/GATED_ACTIONS.md` and
  `docs/RUNTIME_CONFORMANCE.md`: runtime emission closes the careless
  case; the malicious case (a hand-built trace mislabelling a gated
  action as `message`) remains open until the trace is bound to signed
  instrumentation via a codegen digest -- a separate arc.

## [5.41.0] - 2026-06-14  <!-- __s141_changelog_v5_41_0_v1__ -->
### Added
- `law gated(<action>)` world construct: declare which actions require an
  approver attestation, in the signed source. New `GATED` grammar token and
  `law_decl_gated` rule; `LawGatedNode` AST node and `WorldNode.gated_actions`;
  validator checks GA001 (gated actions but no `events { ... }` block) and
  GA002 (gated label not in the event alphabet). See `docs/GATED_ACTIONS.md`.
### Changed
- Conformance obligation #5 (authorization) now reads the gated-action set
  from the signed, re-derived SMT spec (`SMTSpec.gated_actions`, folded into
  `smt_spec_sha256` as sorted, de-duplicated `GA:` lines) instead of the
  unsigned, tamperable `proof_assumptions` sibling. This closes the
  advisory-`gated_actions` completeness hole documented in
  `docs/RUNTIME_CONFORMANCE.md`: a tampered sibling can neither remove gating
  (a no-attestation gated event still fails) nor add it (an undeclared gated
  event still refuses). The completeness counterpart to the S139 presence
  proof. Empty gated set is byte-identical to prior specs (regression harness
  0 diffs); `serialize()` is unchanged (gated actions emit no solver
  assertions).
- PYTEST_FLOOR 1605 -> 1620 (+15 S141 gated-action teeth: validator 6, emit 6,
  conformance completeness 3).

## [5.40.0] - 2026-06-14  <!-- __s140_changelog_v5_40_0_v1__ -->
### Fixed
- Conformance obligation #5 (authorization) was unsatisfiable, not
  vacuously-true-by-design. Its attestation preimage was the canonical trace
  body (trace.canonical_body_bytes() + seq), which embeds each event's own
  attestation signature -- a self-referential preimage with no Ed25519 fixed
  point, so no verifying attestation could ever be constructed and the
  positive path had never run. Replaced with a domain-separated,
  envelope-bound, identity-bound preimage that EXCLUDES the attestation's own
  signature: `nous-gated-action-approval:v1|<smt_spec_sha256>|<seq>|<action>|<principal_id>`.
  Binds the exact decision (seq, action), the approver (principal_id), and
  the exact proof envelope (smt_spec_sha256); changing the envelope sha or
  the action breaks verification (anti-replay across worlds). Orthogonal to
  canonical_body_bytes, so every existing trace signature and conformance
  certificate stays byte-identical. Honest scope: proves presence + binding +
  identity for trace-LABELLED gated actions; does NOT prove labelling
  completeness (gated_actions is read from the advisory, unsigned
  proof_assumptions sibling) nor key-trust (proves SOME key bound to the
  principal_id label signed, not the RIGHT key). See
  docs/RUNTIME_CONFORMANCE.md.
### Added
- conformance.py public signer `sign_gated_action(...)` and preimage helper
  `_attestation_preimage(...)`; no issuer-side signer for gated-action
  approvals existed before, which is why obligation #5's positive path was
  never exercised.
- scripts/rule0.sh: tracked, auto-enumerating RULE 0 session-startup runner.
  Computes git rev-list --count <latest-tag>..HEAD and lists every commit
  since the tag, so seal-count drift can no longer be undercounted by hand.
### Changed
- PYTEST_FLOOR 1597 -> 1605 (+8: S139 authorization obligation #5 teeth
  in tests/test_s139_authorization_obligation.py).

## [5.39.0] - 2026-06-14  <!-- __s138_changelog_v5_39_0_v1__ -->
### Changed
- Blocking-net full-mode offline chain verifier now re-proves prior-link
  coverage. The emitted build_chain_net_verifier output previously proved
  current-link coverage, hop monotonicity (T_prev subset-of T_cur), and
  net containment (net_prev subset-of net_cur), but took every PRIOR
  link's blocking-net coverage on the issuer signature. It now re-runs the
  zero-trust coverage proof (net_prev superset-of T_prev) on every prior
  link using artifacts full mode already carries (per-link sha-gated
  source + sha-gated cert), catching an issuer-signed prior link that
  ships a sha-consistent gapped or forged Farkas certificate. No new
  carried artifact; full mode only; additive. Chains without per-link
  certs are vacuous (no false positive on legitimately-issued chains).
- PYTEST_FLOOR 1587 -> 1597 (+10 tests: S136 Annex IV gap-witness refuse,
  S137 prior-link coverage teeth).

## [5.38.0] - 2026-06-13  <!-- __s135_changelog_v5_38_0_v1__ -->

### Added
- Annex IV evidence-map sidecar for dossiers. `nous dossier --annex-iv-map`
  (default off) emits a signed `annex_iv_map.json` indexing the nine EU AI
  Act Annex IV technical-documentation items to the evidence artifacts the
  dossier already carries (manifest.json, source.nous, coverage sidecars),
  each reference bound by file-bytes sha256, the whole map bound to the
  dossier by the manifest canonical-body sha256 and signed Ed25519. A
  standalone `verify_annex_iv_map.py` is emitted alongside: it re-runs all
  four checks offline with `cryptography` + stdlib only (no NOUS install)
  -- map signature, dossier binding, per-reference presence and integrity,
  and indexing completeness with clause coherence. The sidecar is an
  orthogonal evidence index; it is never folded into `verify_offline.py`,
  and is refused on a coverage-gap-witness (refutation) dossier.
  Boundary, stated in the verifier verdict: it proves presence +
  authenticity + indexing of declared evidence, NOT legal sufficiency and
  NOT that any file satisfies its Annex IV item. Default off keeps every
  existing dossier byte-identical.
- New module `annex_iv_map.py` (build + verify + standalone-verifier
  builder), registered in the wheel content gate.

### Changed
- PYTEST_FLOOR 1557 -> 1587 (+30 tests across the Annex IV map arc).

## [5.37.0] - 2026-06-12  <!-- __s134_changelog_v5_37_0_v1__ -->

### Added
- End-to-end coverage-gap-witness dossiers: the witness primitive is now a
  full produce -> package -> verify pipeline with zero issuer trust.
  `nous verify --gap-witness` (with `--coverage-threshold`) issues a
  REFUTATION dossier when a coverage obligation is not proven: it finds a
  rational point in the threshold region that escapes every blocking signal
  (exact Fourier-Motzkin, no solver), serializes the witness, and binds it
  into the signed manifest as `source_kind="gap-witness"` +
  `gap_witness_sha256`. `build_dossier` packages such a manifest -- carrying
  `coverage.gapwitness.json` under its sha gate -- and emits a self-contained
  `verify_offline.py` that re-derives the gap from the signed `source.nous`
  by rational arithmetic alone (stdlib + `cryptography` for the Ed25519
  signature), printing `VERDICT: REFUTATION` on success. A verified
  gap-witness proves a coverage gap EXISTS at the carried point; it is not a
  compliance pass, not evidence the agent misbehaves, and not a claim the gap
  is unique or maximal.

### Changed
- The dossier verifier ladder leads with the signed `source_kind`
  discriminator (axiom 8): a `gap-witness` manifest selects the gap-witness
  verifier ahead of any `prior_digest`-keyed chain arm. `build_dossier`
  refuses a `gap-witness` manifest that also declares `prior_digest` (a
  refutation has no chain semantics) or requests a rekor anchor (the
  gap-witness verifier checks an Ed25519 signature only); both are refused
  rather than silently merged. All changes are additive: no existing manifest
  sets `source_kind`, so every prior dossier builds byte-identically.

## [5.36.0] - 2026-06-11  <!-- __s132_changelog_v5_36_0_v1__ -->

### Added
- Coverage-gap-witness: the dual of the policy-coverage Farkas bundle.
  `serialize_gap_witness(threshold_ast, blocking_signals, point)` emits
  a self-contained, JSON-serializable witness -- a concrete rational
  point lying in a DNF disjunct of `T && NOT(B)` (inside the threshold
  region while escaping every blocking signal) -- and
  `check_serialized_gap_witness(doc, threshold_ast, blocking_signals)`
  verifies it offline by rational arithmetic alone, re-deriving the gap
  disjunct set from the supplied ASTs with zero issuer trust. Where the
  Farkas bundle proves NO gap (every disjunct refuted), the witness
  proves a gap EXISTS at a named point; the two are mutually exclusive
  over the same `(T, B)`. The witness proves the point is admitted by
  the threshold and caught by no blocking signal; it does not prove the
  agent misbehaves there, nor that the gap is unique or maximal.

## [5.35.0] - 2026-06-11  <!-- __s127_changelog_v5_35_0_v1__ -->

### Added
- Blocking-net containment for envelope-binding chains
  (`--chain-coverage full`). A full-mode chain dossier carries
  per-link `source.nous` (sha-gated by each link's signed
  `source_sha256`) and one self-certifying blocking-net Farkas
  bundle per non-vacuous hop (`chain/NNN_net.farkas.json`). The
  emitted verifier re-derives the obligation
  `OR(prev_signals) AND AND(NOT cur_signals)` from the two
  authenticated sources -- never from a bundle -- and refutes every
  DNF disjunct with rational arithmetic alone (no solver, no issuer
  trust). This proves the actual blocking net never shrank across
  the chain, re-derived rather than signature-attested: a third
  party verifies offline that every prior link's blocking policies
  are still present (or strengthened) in the current one. Region
  containment over the reals is the unsatisfiability of
  `OR(prev) AND AND(NOT cur)`; within the disjunctive linear
  fragment, Farkas refutation of every disjunct is complete. Net
  shrink, net vanish, and bilinear signals refuse at issuance (the
  verifier would refuse the dossier it ships with). Full mode
  requires `--supersedes`; a full-mode chain must be full from its
  first full link (depth>=2 requires the predecessor to also carry
  per-link sources, else the build refuses). Honest boundary: this
  proves the declared blocking net did not shrink across versions --
  NOT that the system is safer, NOT real-world risk; policies are
  monitors, not guards.

### Changed
- `chain_coverage_mode` discriminator added to the signed manifest
  (drop-when-None; byte-identity of existing manifests preserved).
  The emitted verifier decides full-mode vs threshold-only from this
  signed field, never from file presence (manifest-is-authority). A
  threshold-only chain emits no net files and selects the unchanged
  CHAIN_BUNDLE verifier (byte-identical to v5.34.0).

## [5.34.0] - 2026-06-10  <!-- __s126_changelog_v5_34_0_v1__ -->

### Added
- Hop-containment Farkas bundles for envelope-binding chains. Across a
  re-binding hop, coverage-region monotonicity (region(T_prev) is
  contained in region(T_cur)) is now proven by a hop-containment Farkas
  bundle (chain/NNN_hop.farkas.json) rather than the closed-form
  proportionality check of v5.30.0. Region containment over the reals is
  the unsatisfiability of T_prev AND NOT(T_cur); within the disjunctive
  linear fragment, Farkas refutation of every DNF disjunct is complete,
  so the hop proof is a theorem object. The emitted chain verifier
  (VERIFY_OFFLINE_PY_CHAIN_BUNDLE) re-derives each hop obligation from
  the two links' sha-gated threshold expressions -- never from the hop
  bundle -- and checks it with rational arithmetic alone (no solver, no
  issuer trust).

### Changed
- Boolean-threshold links are now admissible in a chained bundle dossier.
  The S125 issuance gates that refused a boolean threshold without a
  single-comparison threshold_constraint are removed: the hop proof no
  longer needs a single inequality. Region regression is caught at
  ISSUANCE (a satisfiable hop disjunct admits no Farkas witness, so the
  build refuses), matching the admission-control pattern.

### Security
- Hop bundles are unsigned and self-certifying: a forged multiplier
  fails rational arithmetic, an omitted or surplus disjunct fails the
  bijection, a deleted hop file fails closed, and an unexpected hop file
  on a coverage-less hop is refused. Tampering the hop bundle's own
  prev/cur threshold expression fields changes nothing, because the
  obligation is re-derived from the two sha-gated, signature-anchored
  sidecars.

## [5.33.0] - 2026-06-10  <!-- __s125_changelog_v5_33_0_v1__ -->

### Added
- Chain + Farkas DNF bundle composition. A re-binding (envelope-binding
  chain) dossier whose current link carries a boolean blocking net is now
  verifiable offline: the emitted verifier (VERIFY_OFFLINE_PY_CHAIN_BUNDLE)
  re-derives the current link's gap disjunct set from the SIGNED source
  (zero issuer trust, no solver) and walks the prior-link chain, asserting
  coverage-region MONOTONICITY from each link's SIGNED threshold inequality
  (v1 constraints[0] or bundle threshold_constraint). Prior-link coverage
  completeness is NOT re-proven (no per-link source is carried); the honest
  boundary is documented in docs/CHAIN_BUNDLE_COMPOSITION_DESIGN.md.

### Changed
- `nous dossier --supersedes` lifts the S124 unconditional chain+bundle
  refuse: it emits the chain+bundle verifier when the chain carries any
  disjunctive-linear bundle (current link or carried prior) bearing a
  single-comparison threshold_constraint. Plain v1 chains keep emitting the
  v1 chain verifier byte-identically.

### Security
- Boolean-THRESHOLD bundles (no single-comparison threshold_constraint) are
  refused at issuance -- as current link or carried prior -- because region
  monotonicity across a boolean threshold is not computed and the emitted
  verifier would otherwise refuse the dossier it ships with. The verifier's
  monotonicity reader also refuses such a hop defensively (fail-closed).

## [5.32.0] - 2026-06-10  <!-- __s124_changelog_v5_32_0_v1__ -->

### Added
- Farkas DNF bundle for boolean blocking nets (P3b-bool): boolean
  combinations of linear comparisons (&&, ||, !) are now certifiable by
  standard-library rational arithmetic. The gap search T && NOT(B) is
  expanded to disjunctive normal form over the NEGATION; one Farkas
  certificate per disjunct; coverage is PROVEN iff every disjunct is
  refuted. coverage.farkas.json becomes a bundle (fragment
  "disjunctive-linear-bundle") for boolean obligations; v1 single-system
  certificates remain byte-identical for linear obligations.
- Offline bundle verifier: re-derives the disjunct set from the SIGNED
  source (string-aware structural scanner plus a grammar-mirroring
  expression parser, pure stdlib) and requires a bijection -- exactly
  one valid certificate per derived disjunct. Omission, surplus,
  duplicate, substitution, and forged-multiplier bundles FAIL even under
  a valid manifest signature (zero issuer trust; boolean ENUMERATION
  from signed source, never boolean solving).
- coverage_minilang module and an issuance-time cross-derivation gate: a
  bundle is signed only when the text-level derivation reproduces the
  Lark-side disjunct set; divergence drops to z3-only evidence
  (drop-when-None).
- DNF disjunct count bounded (DISJUNCT_BOUND = 64) with a typed REFUSE
  (exponential case-split is never signed unbounded).

### Changed
- `nous verify --coverage-threshold` dispatches through serialize_auto:
  the v1 single-system path is byte-identical; boolean obligations emit
  the bundle.
- Honest boundary: chain + Farkas bundle composition is REFUSED at
  dossier build (the chain verifier checks single-system certificates
  only; carry-forward). var*var stays REFUSED (bilinear, outside
  QF_LRA).

## [5.31.0] - 2026-06-08  <!-- __s129_changelog_v5_31_0_backfill_v1__ -->

### Added
- P3b-multivar: the coverage fragment admits linear scalar
  multiplication (const*var) in threshold and signal expressions, while
  bilinear terms (var*var) stay REFUSED (outside QF_LRA). End-to-end
  through the dossier with a fragment-boundary re-scope.

## [5.30.0] - 2026-06-08  <!-- __s129_changelog_v5_30_0_backfill_v1__ -->

### Added
- Coverage-region monotonicity in the offline chain verifier: per
  re-binding hop where both links declare coverage, region(T_prev) is
  proven contained in region(T_cur) by a closed-form proportionality
  check (later upgraded to hop-containment Farkas bundles in 5.34.0).
- Chain-carry sidecar expansion so prior-link coverage thresholds travel
  with the dossier.
- Verified AI Lending demo page (nous-lang.org/lending.html) for
  FinQuest, with the log-vs-evidence differentiation and a no-trust
  verification panel.

## [5.29.0] - 2026-06-07  <!-- __s129_changelog_v5_29_0_backfill_v1__ -->

### Added
- Envelope-binding chain: a signed `prior_digest` manifest field, a
  `nous verify --supersedes` producer that re-binds a new formation
  envelope to its predecessor by digest, a chain-carrying `build_dossier`
  that ships prior manifests under `chain/`, and an offline chain-walk
  verifier that checks an unbroken signature-valid lineage rooted at
  genesis (six fail-closed conditions), cryptography + stdlib only.

## [5.28.0] - 2026-06-06  <!-- __s129_changelog_v5_28_0_backfill_v1__ -->

### Added
- S118 compiled-path runtime trace attribution: a real soul and a
  zero-token llm_call are attributed on the compiled execution path.

### Changed
- Governance-first public homepage and /runtime.html; softened absolute
  biology/resilience claims to match what the runtime establishes.

### Security
- Removed a Developer backdoor from the public homepage.

## [5.27.0] - 2026-06-06  <!-- __s116_changelog_v5_27_0_v1__ -->

### Added
- Policy-coverage proof now travels inside the signed dossier as
  coverage.smt2 (7th dossier file), bound by two drop-when-None manifest
  fields (policy_coverage_sha256, coverage_smt2_sha256). New flag
  `nous verify --smt --coverage-threshold "EXPR"`. REFUTED coverage fails
  closed: no manifest is written for an unproven coverage obligation.
- Farkas certificate for policy coverage as coverage.farkas.json (8th
  dossier file), bound by coverage_farkas_sha256. The offline verifier
  checks the coverage claim by standard-library rational arithmetic alone:
  no solver, no NOUS install required. z3 becomes an optional second
  opinion rather than the trust path. New module coverage_farkas.py exposes
  serialize_system and check_serialized.

### Changed
- Offline dossier verifier selection: a Farkas-bearing dossier ships the
  arithmetic-only verifier; coverage-only dossiers keep the z3 re-check
  verifier; cost-only dossiers remain byte-identical.

## [5.26.1] - 2026-06-02  <!-- __s129_changelog_v5_26_1_backfill_v1__ -->

### Fixed
- Dossier pricing-canonical hotfix: ship the exact pricing bytes the
  manifest hashes (the dossier now carries the pricing the signed
  manifest commits to).

## [5.26.0] - 2026-06-01  <!-- __s129_changelog_v5_26_0_backfill_v1__ -->

### Added
- Phase 2.0 remedy subsystem close-out: a heal-path digest producer, a
  typed RemedyProof parse-on-read view, a build_run_remedy admissibility
  gate, a TraceEnvelope.remedy_application sibling field, recorded-
  commitment promotion wiring (at most one promotion), and a
  `--apply-remedy` opt-in surface gated on `--consult-memory`. Adds the
  NOUS_MEMORY_BASE_DIR seam.

## [5.25.0] - 2026-06-01  <!-- __s107_changelog_v5_25_0_v1__ -->

### Added
- Deterministic memory consultation (Memory Phase 1). A run may consult
  persistent per-world soul memory and record that consultation INSIDE the
  signed conformance trace: `TraceEnvelope.memory_consultation` pins the
  consulted chain head (a hash-chain commitment to the consulted prefix),
  the producing soul, and the entry count. `nous run --consult-memory`
  (requires `--emit-trace`) opts in; default OFF. NAME-BOUND identity
  (`run_identity.world_sha256` / `producing_soul_sha256`) keeps memory
  identity orthogonal to the run subject binding. Phase 1 is single-soul
  and fail-closed: a multi-soul world refuses with MemoryConsultationError.
- Optional drop-when-None canonicalization for the signed trace: a
  non-consulting trace is byte-identical to prior releases and every shipped
  signature still verifies; the key-agnostic offline verifier accepts both
  consulting and non-consulting traces unchanged, and now surfaces the
  consultation in its summary for auditors.

## [5.24.0] - 2026-05-31  <!-- __s106_changelog_v5_24_0_v1__ -->

### Added
- Persistent per-world soul memory CLI surface: `nous memory init`,
  `nous memory append`, `nous memory verify`, `nous memory reindex`. This makes
  the Phase 0 memory stack reachable: signed hash-chained per-soul entry files
  are the truth, and a rebuildable SQLite index is a derived lens. `init` is an
  explicit per-world signing-key ceremony; writes refuse on an uninitialized
  world; `verify` recomputes the chain and exits 2 on any integrity break.
  Backing modules (`memory_entry`, `memory_keyring`, `memory_store`,
  `memory_index`) were already packaged; this release ships their caller.

## [5.23.0] - 2026-05-31  <!-- __s105_changelog_v5_23_0_v1__ -->

### Added
- Trace transparency anchoring (Rekor v2). A signed `TraceEnvelope` can be
  anchored to the Sigstore Rekor v2 log via
  `trace_anchor.anchor_trace_to_rekor_v2`, reusing the dossier anchoring
  path; the returned
  `RekorAnchorV2` is DETACHED (the frozen signed envelope is unchanged, the
  binding is cryptographic and checked at verify, matching the Sigstore
  detached-bundle convention). `compiled_trace.anchor_compiled_run` is the
  reachable caller: it runs the compiled path, signs the trace, anchors it,
  and returns `(TraceEnvelope, RekorAnchorV2)`. Anchoring an unsigned
  envelope is refused. A third party can now prove a run's trace existed at
  a point in time and was not altered after, in addition to offline
  signature verification.

## [5.22.0] - 2026-05-31  <!-- __s105_changelog_v5_22_0_v1__ -->

### Added
- Compiled-path signed conformance trace. The codegen/compiled runtime
  now emits a signed `TraceEnvelope` (offline-verifiable with
  `cryptography` alone) via the new `compiled_trace.run_compiled_with_trace`,
  using the same nous_trace recorder as the interpreter. Message events
  are recorded at the runtime `ChannelRegistry.send` choke-point
  (`NousRuntime`/`ChannelRegistry` gain an opt-in trace context, no-op by
  default). Message-event parity with the interpreter path is proven by a
  direct-equality test. `llm_call` events and per-soul attribution are
  authoritatively deferred (soul is the reserved `unknown_soul` sentinel).
  Additive: codegen is untouched and the 57-template byte-identity gate
  holds at 0 diffs; signed certificate bytes unchanged.

## [5.21.0] - 2026-05-31  <!-- __s105_changelog_v5_21_0_v1__ -->

### Added
- `POST /v1/run` opt-in dry-run signed trace emission. With
  `emit_trace: true`, a dry-run returns the signed `TraceEnvelope`
  (ephemeral Ed25519, offline-verifiable with `cryptography` alone)
  plus `execution_kind: "dry-run"`; the `execute` branch is tagged
  `execution_kind: "refused"` (live execution not yet wired). A third
  party can now obtain and verify a real run's labelled trace over the
  API without a local install. Additive: `execute_program` gains a
  keyword `trace_capture` (default None -> all callers byte-identical),
  `RunRequest.emit_trace` defaults False; no codegen, signature, or
  signed-certificate change; regression byte-identity held.

## [5.20.1] - 2026-05-30

### Fixed
- `cli_commands` in the `/v1/health` response was a hand-bumped literal
  (46) that had silently drifted from the real root subcommand count
  (52). It is now derived: `cli.build_parser()` is extracted from
  `main()` and `cli.cli_command_count()` returns the live count; a test
  locks the health literal to that count so the two can never diverge
  again. Behavior of `main()` is byte-identical (it now calls
  `build_parser()`); regression byte-identity unaffected.

## [5.20.0] - 2026-05-30

### Added
- Producer-existence for sequence laws. A conformance verdict now lists
  `sequence_vacuous`: laws that passed only because their event never
  occurred in the trace, distinguished from genuinely proven laws. The
  static verifier additionally warns (SEQ-PROD) when a sequence law
  references an event no soul emits via speak. Additive: the
  `_check_sequence_obligations` signature and the signed conformance
  certificate are unchanged; no existing test or fixture affected.

## [5.19.0] - 2026-05-30

### Added
- Action-label binding on the interpreter trace path: a `speak` whose
  message type is declared in `world.events` now stamps that label onto
  the signed trace `action` field (implicit-by-name). Sequence laws
  (before/never_after/leads_to/at_most) now enforce against real runs,
  not fixtures only. Think/llm_call events and undeclared messages stay
  null. No grammar, AST, or codegen change; regression byte-identity held.

## [5.18.0] - 2026-05-30

### Added
- Runtime trace emission on the interpreter path (S103): `nous run
  --emit-trace` produces a signed `TraceEnvelope` (ephemeral Ed25519,
  offline-verifiable). Initial events carried `action=null` (bound in
  v5.19.0).

## [5.17.0] - 2026-05-29

### Added
- `at_most(N, label)` cardinality sequence law.

## [5.16.0] - 2026-05-29

### Added
- `never_after` and `leads_to` ordering sequence laws.

## [5.15.1] - 2026-05-29

### Added
- `docs/SEQUENCE_LAWS.md` and decoupling of `verify-sequence` from
  pricing validity (two post-5.15.0 addenda).

## [5.15.0] - 2026-05-28

### Added
- Phase 2 sequence arc (Stages 2-6), end-to-end: events declaration +
  validator, sequence-consistency SMT emission, Z3 consistency proof,
  runtime sequence conformance (`ConformanceDetail.sequence_ok`), the
  seventh obligation itemized in the signed certificate body (schema
  v1->v2), and the `nous verify-sequence` CLI. cli_commands 45 -> 46.

## [5.14.0] - 2026-05-27

### Added
- `POST /v1/verify-conformance` endpoint and the
  `verify_certificate_from_json` library API.

## [5.13.1] - 2026-05-26

### Fixed
- CLI verdict-print used `detail.conformant`; `ConformanceDetail`
  exposes `.ok`. Corrected, with a CLI regression test.

## [5.13.0] - 2026-05-26

### Added
- S97 standalone signed conformance certificate with Rekor v2 anchoring
  and an offline verifier.

<!-- __session95_release_v5_12_0_changelog__ -->
## [5.12.0] - 2026-05-25
### Added
- `nous dossier --anchor rekor_v2` and `nous dossier-spec --anchor rekor_v2` now expose the tile-backed
  Rekor v2 + RFC 3161 trusted-timestamp anchor on both CLI dossier
  paths. The `dossier-spec` (SKILL.md-directory) path gained the v2
  emit branch and verifier selection mirroring `dossier`, with a
  `_test_rekor_anchor_v2` hook for offline tests. Proven end-to-end:
  both paths emit a bundle whose `verify_offline.py` passes with
  VERDICT PASS against the live log (dossier log_index 4626112,
  dossier-spec log_index 4626706).
  <!-- __session95_dossier_spec_rekor_v2_changelog_v1__ -->

<!-- __session93_release_v5_11_0_changelog__ -->
## [5.11.0] - 2026-05-24

### Added

- Rekor v2 + RFC 3161 dossier emission (the v2 write path).
  `nous dossier --anchor rekor_v2` submits a manifest's canonical
  bytes to the tile-backed Sigstore Rekor v2 log (`log2025-1`),
  recovers the per-submission ephemeral ECDSA-P-256 leaf signature
  from the server-returned leaf body, requests an RFC 3161 trusted
  timestamp over that signature from the Sigstore TSA, and embeds
  both in the dossier's `transparency_log` block. The emitted
  `verify_offline.py` is the v2 variant assembled by
  `offline_verifier_builder` with the pinned production log-key
  allowlist; it checks the leaf-to-manifest ECDSA tie, the checkpoint
  Ed25519 signature, the RFC 6962 inclusion proof, and the RFC 3161
  trusted time, fully offline with only `cryptography` plus stdlib.
  Proven end-to-end against the live log (log_index 4598985).
  <!-- __session93_dossier_rekor_v2_emit_changelog_v1__ -->

### Fixed

- v2 emission attached the RFC 3161 token via `model_copy(update=...)`
  on the frozen `RekorAnchorV2`; on this model the updated value did
  not reach `model_dump()` / `to_manifest_block()`, so the emitted
  manifest carried no token and offline timestamp verification
  failed. Emission now re-constructs the anchor with every field plus
  the token, which serializes correctly.
  <!-- __session93_dossier_rekor_v2_token_changelog_v1__ -->

## [5.10.0] - 2026-05-23

### Added

- Rekor transparency-log API v2 verification support.
  `MAX_SUPPORTED_REKOR_API_VERSION` is now 2;
  `parse_manifest_json_with_anchor_v2` dispatches a manifest's
  `transparency_log` block by its `rekor_api_version` discriminator
  (absent or 1 -> the existing v1 SET-based path, byte-identical;
  2 -> the v2 checkpoint path; higher -> refused). The v1 read path is
  unchanged. v2 anchor emission is not part of this release.
  <!-- __session91_rekor_v2_dispatch_changelog_v1__ -->
- Portable offline verifier for v2-anchored dossiers:
  `offline_verifier_builder` assembles a standalone `verify_offline.py`
  (cryptography + stdlib only) from the shipped Rekor v2 read-path
  modules, guarded by an anti-drift equivalence test.
  <!-- __session90_offline_verifier_changelog_v1__ -->
- Pinned the production Sigstore Rekor v2 log key
  (`log2025-1.rekor.sigstore.dev`) into the verifier allowlist, proven
  against a real checkpoint and a synthetic full verify flow.
  <!-- __session90_rekor_v2_pin_changelog_v1__ -->
- Release pipeline phase-9 UX smoke now also runs `nous verify` from
  the clean install venv.
  <!-- __session90_phase9_verify_changelog_v1__ -->
- Differential test (`tests/test_runner_codegen_equiv.py`): asserts the
  AST runner and codegen derive an identical semantic surface (souls,
  messages, per-soul model/tier/senses/memory-field names, law
  constants) from each gate-clean source. The codegen side recovers the
  surface from the emitted module via stdlib `ast`, so a pass proves
  codegen emits what the runner consumes. Routes are deferred to a
  separate forward test. <!-- __session89_g1_changelog_v1__ -->

### Changed

### Fixed

- AST runner ignored declared per-cycle cost ceilings. `_extract_cost_ceiling`
  tested `isinstance(law, LawCost)` where `law` is a `LawNode` wrapper (payload
  in `.expr`), so the check was always false and the runner silently used the
  0.10 default. Now reads `law.expr` (matching codegen). Surfaced by the new
  differential test.

<!-- __session82_release_v5_5_0_changelog__ -->
<!-- __session86_release_v5_8_1_changelog__ -->
<!-- __session88_release_v5_9_0_changelog__ -->
## [5.9.0] - 2026-05-21

### Added
- Rekor v2 read-path verifier (modules only; not yet wired into the
  live verify flow -- dispatch lands in a later release). `rekor_entry`
  normalizes hashedrekord v0.0.1 and v0.0.2 leaf bodies into one value
  object (DER SubjectPublicKeyInfo public key, hex digest), recognizing
  and refusing dsse. `rekor_checkpoint` verifies a C2SP signed-note
  checkpoint (Ed25519 log signature, key ID per the signed-note spec)
  and an RFC 6962 inclusion proof, taking root hash and tree size from
  the verified checkpoint. `rekor_verify_v2` composes both with the
  Path-beta leaf-to-manifest ECDSA tie and reports four independent
  per-step results (leaf digest, leaf signature, checkpoint signature,
  inclusion proof) so an auditor sees exactly which link broke.
- `RekorAnchorV2` v2 anchor manifest schema with a `rekor_api_version`
  discriminator present only in v2 blocks. v1 anchor blocks omit it and
  the reader treats absence as v1, so every historical v1 dossier and
  its signature remain byte-identical.

### Changed
- PYTEST_FLOOR raised 596 -> 641.

## [5.8.1] - 2026-05-21

### Fixed
- The undefined-name gate is now enforced by `nous run` and hot-reload,
  not only `nous compile`. nous_ast_runner executes the AST live (no
  codegen), so `nous run` performs a throwaway codegen pass and refuses
  (CodegenSemanticError, exit 1) before any execution if a generated
  module would reference an undefined name. `run` and `compile` now
  reject the same sources by the same check.

<!-- __session86_release_v5_8_0_changelog__ -->
## [5.8.0] - 2026-05-21

### Added
- `rekor_signing_config` module: a Sigstore SigningConfig v0.2 loader
  and Rekor transparency-log endpoint selector. Makes the
  SigningConfig the single source of truth for which Rekor tlog
  endpoint to submit to, removing hardcoded URL/path assumptions
  (per the rekor-tiles client spec: the v2 URL MUST NOT be
  hardcoded). Selects the highest API version the client supports
  (currently v1), grouped by operator, honoring validFor windows.
  Fails closed with RekorApiVersionUnsupported if only a
  higher-than-supported API version is available, rather than
  silently downgrading. Submission and offline verification are
  unchanged; Rekor v2 submission/verification (tiles, inclusion
  proof, checkpoint) remain future work.

<!-- __session86_release_v5_7_1_changelog__ -->
## [5.7.1] - 2026-05-21

### Fixed
- Codegen now emits `HEARTBEAT_SECONDS` and `COST_CEILING`
  unconditionally (using defaults when no `world` block is present),
  so generated modules for world-less sources no longer reference
  these as undefined names. World-bearing output is byte-identical.
  Caught by the S85 undefined-name gate.

<!-- __session85_release_v5_7_0_changelog__ -->
## [5.7.0] - 2026-05-21

### Added
- `null` / `none` as a first-class literal mapping to Python `None`;
  `== null` / `!= null` emit `is None` / `is not None`.
- `guard <expr> else <action>` now honored: the else action (any
  statement) is emitted before the guard return instead of being
  silently dropped.
- Codegen-time undefined-name gate: `nous compile` runs pyflakes as a
  library over generated Python and REFUSES with `CodegenSemanticError`
  if any name is undefined, before writing output. Ignores unused
  imports and all non-undefined-name categories.

### Changed
- `customer_service` template binds `message` in soul Triage from a
  `superbrain_search` sense call (was unbound).
- Regression baseline re-anchored to gate-verified codegen output for
  the 7 templates whose output changed under the null / guard-else fixes.

### Fixed
- Release pipeline phase 10 is idempotent on duplicate upload
  (`twine upload --skip-existing`; duplicate-400 no longer aborts
  before tag).

<!-- __session84_release_v5_6_0_changelog__ -->
## [5.6.0] - 2026-05-20

### Added

- **Rekor v2 migration P1: trust root mirror (S84 #3a/#3b).** New
  `infra/sigstore/signing_config.json`, a pinned snapshot of the
  Sigstore SigningConfig resolved via TUF on 2026-05-20 (v1-only:
  the production config lists only `rekor.sigstore.dev` at
  `majorApiVersion: 1`, by Sigstore's stated decision to withhold the
  Rekor v2 URL from TUF until clients upgrade). New
  `scripts/refresh_signing_config.py`: a stdlib-only refresh that drives
  a version-pinned `sigstore` CLI (`sigstore plumbing update-trust-root`)
  via subprocess and never imports `sigstore` into the NOUS runtime,
  writing the resolved config to a staging path. A monthly systemd timer
  (`infra/systemd/sigstore-signing-config-refresh.{service,timer}`) runs
  the refresh as an unprivileged `nous-refresh` user under a hardened
  sandbox; promotion of a changed config into the repo is a deliberate
  commit.
- **6 new tests** in `tests/test_signing_config_mirror.py` validating the
  pinned mirror offline (mediaType, rekorTlogUrls shape, v1 presence).
  PYTEST_FLOOR raised 560 -> 566.

### Notes

- No runtime code path consumes the mirror yet; `rekor_anchor.py` is
  unchanged. P1 is the trust-root plumbing for the v2 read path (P2,
  planned v5.7.0). The dependency surface of `nous-lang` is unchanged:
  the `sigstore` tool lives in an isolated venv, not in the wheel.
- The homepage story timeline was rebuilt into ascending order with
  v4.14.0 through v5.5.0 cards (web-only, not in this package).
- `CHANGELOG.md` was folded to ASCII for typographic characters; the
  `POLICY.2` Greek grammar-keyword reference is retained intentionally.

## [5.5.0] - 2026-05-17

### Added

- V2 response shape for `POST /v1/verify-dossier` (S82 #1b): backward-compatible opt-in via new `policy` request field. When `policy` is present, returns `spec_version: "verify-dossier/v2"`, `verdict` (ACCEPT/REJECT), `trust_level` (rekor_anchored / ed25519_only / none), `policy_applied`, `checks{8}` (each with discriminated `ok: true | false | "skipped_unanchored" | "skipped_no_policy"` plus `errors[]`), `evidence`, and `human_readable{verdict_summary, trust_explanation, next_steps[]}`. When `policy` is omitted the legacy V1 response shape is preserved byte-identically for existing clients.
- `dossier.VERIFY_OFFLINE_PY_HYBRID` (S82 #1a): hybrid offline verifier that accepts both Rekor-anchored and unanchored dossiers. Strict by default; new `--allow-unanchored` flag explicitly opts into unanchored verification. Replaces `VERIFY_OFFLINE_PY_WITH_REKOR` as the verifier source shipped from `nous-lang.org/verify_offline.py`.
- Six new `tests/test_dossier_hybrid_template.py` cases covering the unanchored verification path of the HYBRID template.
- Twelve new `tests/test_verify_dossier_endpoint_v2.py` cases covering V2 endpoint dispatch, verdict computation, policy defaults, check skipping, evidence assembly, and error propagation.

### Changed

- `nous-lang.org/verify.html` JS refactored for V2 response shape (S82 #1c): verdict banner, four status pills (SIGNATURE, SOURCE ID, ANCHORED, REKOR ANCHOR with composite state), evidence block with clickable Rekor log link, collapsible trust explanation, next-steps list, and per-check diagnostics. POST body opts into V2 with a permissive policy (`require_anchor: false`) so unanchored dossiers render with honest evidence rather than a hard REJECT. Wording in path-card #2 and the Run-offline note updated to reflect HYBRID-mode verifier.
- `nous-lang.org/ide.html` Dossier tab (S82 #1c2): same V2 surface as verify.html, adapted to IDE element IDs (`dossier-*`) and the compact tab layout.
- `nous-lang.org/verify_offline.py` (S82 #1c): re-extracted from `dossier.VERIFY_OFFLINE_PY_HYBRID`. SHA-pinned at deploy time.
- `PYTEST_FLOOR` raised 542 -> 560 to reflect the new tests (S82 #1d).

<!-- __session81_release_v5_4_0_changelog__ -->
## [5.4.0] - 2026-05-17

### Added

- Public `POST /v1/verify-dossier` endpoint (S81 #1): unauthenticated, rate-limited 30/minute, accepts a `manifest_json` string, returns structured `signature_ok`, `rekor_set_ok`, `rekor_inclusion_ok`, `manifest_sha256`, `rekor_log_index`, `rekor_integrated_at`, and `errors[]`. Convenience surface for browser verification; offline `verify_offline.py` remains the canonical trust path.
- `rekor_anchor.RekorVerifyDetail` Pydantic V2 strict frozen model with granular `pubkey_in_allowlist`, `set_signature_ok`, `inclusion_body_ok` booleans plus `errors[]` (S81 #1).
- `rekor_anchor.verify_rekor_anchor_offline_detail()` (S81 #1): no-early-exit variant that evaluates each check independently for diagnostic visibility.
- IDE: new `Dossier` tab (S81 #2) calling `/api/v1/verify-dossier` with drag-drop `manifest.json` / `skill_export.zip` support via JSZip 3.10.1 (SRI-pinned). Tab sits between `Verify` (source) and `Graph` for semantic grouping of verification flows.
- `nous-lang.org/verify.html` (S81 #3): standalone verification surface with the same drag-drop component, three trust paths documented (browser, offline, CLI), and links to Sigstore Rekor for anchored entries.
- `nous-lang.org/verify_offline.py` (S81 #3): byte-identical static extraction of `dossier.VERIFY_OFFLINE_PY_WITH_REKOR`. Auto-synced by the S81 #3 patcher; sha256 verified against the live source of truth on every apply.

### Changed

- `rekor_anchor.verify_rekor_anchor_offline()` refactored to delegate to `verify_rekor_anchor_offline_detail()`; outcome byte-equivalent to S80, asserted across all three captured fixtures by `tests/test_rekor_anchor.py::TestVerifyRekorAnchorOfflineDetail::test_legacy_bool_matches_and_of_detail_fields`.
- `PYTEST_FLOOR` raised 530 -> 542 (9 new endpoint tests + 3 new rekor detail tests, all shipped in S81 #1).

<!-- __session80_release_v5_3_0_changelog__ -->  <!-- __nous_aetherproof_release_530_docs_v1__ -->
## [5.3.0] - 2026-05-16

### Added

- **Rekor anchoring (Path-beta dual signing).** Optional `--anchor rekor` flag on `nous dossier-spec` and `nous skill-export` (and the corresponding HTTP endpoints) anchors emitted manifests into the public Sigstore Rekor transparency log. New module `rekor_anchor.py`. The Rekor leaf carries a per-submission ephemeral ECDSA-P-256 signature over the manifest's canonical body bytes; the existing Ed25519 manifest signature is preserved unchanged. Both signatures cover the same bytes; the dual-signing design works around the incompatibility between Ed25519 and Rekor's `hashedrekord/0.0.1` leaf format (Sigstore issue #851).
- **Self-contained offline verifier.** Dossiers emitted with `--anchor rekor` ship a `verify_offline.py` that validates the Ed25519 manifest signature, the source SHA-256, the Rekor SignedEntryTimestamp, AND the ECDSA-P-256 leaf signature against canonical body bytes -- all offline, no network calls, no NOUS install needed (only `cryptography>=42`). Pinned Sigstore Rekor public key allowlist shipped in the verifier.
- **27 new tests** in `tests/test_rekor_anchor.py` covering the Pydantic V2 model, failure modes (RekorUnavailable, RekorRejected), offline verify (positive + 6 rejection axes), raw-b64 Ed25519 PEM helper, post-Path-beta wire shape, and the `/v1/skill/export` `anchor` field. PYTEST_FLOOR raised 503 -> 530.
- **Live Rekor anchor fixture.** `tests/rekor_fixtures/valid_anchor.json` is the wire response from the first NOUS payload submitted to public Rekor (log_index 1554376230, integrated 2026-05-16T20:08:25Z UTC). Used as the offline-verify positive-case fixture. Anyone can retrieve the live entry: `curl https://rekor.sigstore.dev/api/v1/log/entries?logIndex=1554376230`.
- **`docs/REKOR_ANCHOR.md`**: full reference covering the Path-beta architecture, Sigstore issue #851 explanation, wire format, offline-verify procedure, byte-identity guarantee for `anchor=none`, Sigstore key rotation policy.

### Changed

- `pyproject.toml` py-modules list extended with `rekor_anchor`.
- Wheel content gate (`scripts/release.py`) now requires `rekor_anchor.py` in addition to the v5.2.0 set; PYTEST_FLOOR raised 503 -> 530.
- `dossier.py::VERIFY_OFFLINE_PY_WITH_REKOR` embedded verifier rewritten to match Path-beta semantics: ECDSA-P-256 verify of leaf signature over canonical body bytes, replacing the prior byte-identity check that assumed Ed25519 direct submission.

### Notes

- **Byte-identity guarantee preserved**: without the explicit `--anchor rekor` opt-in, manifests are byte-identical to v5.2.0 output. Existing customers see no change.
- **Air-gapped operation**: `--anchor rekor` fails hard on Rekor unreachability rather than falling back silently. Customers in air-gapped environments should omit the flag; the v5.2.0-equivalent dossier remains Article 14-compliant for inner-circle audit.
- The per-submission ECDSA-P-256 keypair is ephemeral: generated at submission time, used once, discarded. Customers do not manage Rekor-side key material.

<!-- __session77_release_v5_2_0_changelog__ -->
## [5.2.0] - 2026-05-16

### Added

- **`nous skill-export` subcommand.** Inverse of `nous dossier-spec`: emit an agentskills.io-compliant skill (SKILL.md + nous.yaml) from a NOUS `.nous` program. New helper module `skill_export.py`, new CLI wrapper `cli_skill_export.py`.
- **`POST /v1/skill/export` HTTP endpoint.** Streams an `application/zip` containing the emitted skill plus, by default, a fully-signed Annex IV dossier under an ephemeral Ed25519 key. Rate-limited 10/minute per API key. Timeout 60s. Header `X-Skill-Name` carries the resolved skill name.
- **IDE Export Skill button.** New toolbar button in the NOUS IDE (`/ide.html`) next to Download .py. Prompts for description and (optional) skill name, POSTs to `/v1/skill/export`, downloads the resulting ZIP. API key stored in `localStorage` after first use, matching the existing saveTemplate convention.
- **62 new tests** covering schema (40), CLI surface (11), and HTTP endpoint (11) including end-to-end ZIP -> `verify_offline.py` -> VERDICT: PASS. PYTEST_FLOOR raised 441 -> 503.
- **`docs/SKILL_EXPORT.md`**: full reference covering translation surface, all three call sites (CLI, API, IDE), output bundle layout, determinism boundary, refusal conditions, and the chain of custody.

### Changed

- `pyproject.toml` py-modules list extended with `skill_export`, `cli_skill_export`.
- Wheel content gate (`scripts/release.py`) now requires the 2 new modules in addition to the v5.1.0 set.
- `/v1/health` reports `cli_commands: 44` (was 43).

### Notes

- Skill export translation is **lossy and one-way**: NOUS constructs the agentskills.io schema cannot hold (instincts, mitosis, immune, nervous-system topology, message contracts) are dropped. The original `.nous` program retains them at runtime.
- The API and IDE surfaces use **ephemeral Ed25519 keys per request**. For stable signing keys across many exports, use the CLI surface plus `nous dossier-spec --key PATH` on the emitted skill directory.
- The `.nous` world-level `cost_cap: X CCY` shorthand (distinct from `law cost_<name> = $... per cycle`) is not recognized by the exporter; planned for a future minor.

<!-- __session77_release_v5_1_0_changelog__ -->
## [5.1.0] - 2026-05-16

### Added

- **`nous dossier-spec` subcommand.** Emit EU AI Act Annex IV-aligned, Ed25519-signed compliance dossiers directly from agentskills.io-compliant skill folders. New helper module `dossier_spec.py`, new CLI wrapper `cli_dossier_spec.py`.
- **`skill_md.py` sidecar format.** Pydantic V2 schema (`NousSidecar`, `NousToolSpec`, `MoneyAmount`, `SkillMDFrontmatter`), parser (`parse_skill_dir`, `parse_skill_md_file`, `parse_sidecar_file`), and translator (`translate_to_program`) for `SKILL.md` + adjacent `nous.yaml`.
- **Deterministic source envelope** (`source.nous` in skill_md dossiers): canonical byte sequence wrapping `SKILL.md` and `nous.yaml` whose SHA-256 anchors the manifest.
- **`--key PATH` CLI flag** on `nous dossier-spec` for CI/CD-friendly Ed25519 signing key override (fallback to `manifest.default_key_path()` with auto-create).
- **44 new tests** covering schema, parser, translator, CLI end-to-end, and `nous dossier` regression. PYTEST_FLOOR raised 397 -> 441.
- **6 new test fixtures** under `tests/skill_md_fixtures/`: minimal, basic, extended, invalid-currency, over-budget, missing-nous-block.
- **`docs/SKILL_MD_SIDECAR.md`**: schema reference, CLI flag documentation, envelope format spec.

### Changed

- `skill_md.translate_to_program` now sets `world.max_ticks = sum(tool.max_calls)` so emitted programs are immediately SMT-verifiable without further user input.
- `pyproject.toml` py-modules list extended with `skill_md`, `dossier_spec`, `cli_dossier_spec`.
- Wheel content gate (`scripts/release.py`) now requires the 3 new modules in addition to the existing `_version.py`, `nous.lark`, `grammar_data.py`.

### Notes

- `dossier-spec` translator currently narrows currency to USD and EUR; sidecar parses any ISO 4217 shape, broader currency support tracked for a future minor.
- Manifest schema unchanged; `source_kind: Literal["nous","skill_md"]` discriminator deferred to v5.2.0.
- Envelope format is v1; future widenings will increment while keeping `verify_offline.py` format-agnostic.

## [5.0.0] - 2026-05-03

### Breaking

- **Pricing schema v1.0 -> v2.0 field rename.** The `*_usd` suffix
  has been dropped from `PricingEntry` to make per-token rates
  currency-agnostic; per-table `_currency` is now authoritative.
    - `input_per_1m_usd`            -> `input_per_1m`
    - `output_per_1m_usd`           -> `output_per_1m`
    - `input_cached_per_1m_usd`     -> `input_cached_per_1m`
    - `input_cache_write_per_1m_usd`-> `input_cache_write_per_1m`
    - `hourly_cost_usd`             -> `hourly_cost`
  Existing v1.0 pricing TOMLs continue to load via a loader-side
  backward-compat translator that emits exactly one
  `DeprecationWarning` per file. Run `nous prices upgrade <file>`
  to migrate.

- **`PricingTable.sha256()` canonical form changed for v1.0 inputs
  after migration.** The pre-translation v1.0 hash and the
  post-Phase-5b hash for the same logical data will differ
  because canonical field names changed. No production dossiers
  existed prior to this release, so the break has zero deployed
  impact. Going forward, sha256 is stable across v1->v2 loads
  because the translator runs before canonicalisation.

### Added

- **`nous prices upgrade <input.toml> -o <output.toml>`** -- new
  CLI subcommand. Line-based migration that preserves comments,
  blank lines, and formatting verbatim. Validates the migrated
  TOML through the v2 loader and full Pydantic validation BEFORE
  writing the output file. Idempotent on v2.0 input. Refuses to
  overwrite output without `--force`. Supports `--in-place`.

- **EUR end-to-end SMT cost verification.** Programs declaring
  `cost_cap: <amount> EUR` and using a pricing table with
  `_currency = "EUR"` now compile cleanly under `--smt`. Z3
  round-trip confirmed: provable obligations return UNSAT,
  refuted obligations return SAT with counterexamples. The
  Phase 5a `_validate_currency_consistency` guard remains:
  mixing pricing-currency and cap-currency inside a single
  proof is still refused (FX rates are not auditable).

- **`pricing/eur_example.toml`** -- shipped EUR-native pricing
  demonstration with three Mistral models and a local-ollama-eur
  entry. Values are illustrative; production use requires
  provider verification.

- **`tests/test_pricing_v1_compat.py`** (12 tests) locking in
  the v1->v2 loader translator: DeprecationWarning emission,
  sha-stable v1==v2 invariant, dual-name rejection, decimal
  precision preservation.

- **`tests/test_cli_prices_upgrade.py`** (18 tests) covering
  every upgrade CLI behaviour including comment / blank-line
  preservation and post-migration Pydantic validation.

- **`tests/test_smt_emit_eur.py`** (11 tests) end-to-end EUR
  cost verification including Z3 round-trip with provable and
  refuted obligations at multiple `max_ticks` scales.

### Removed

- The v4.13.0 USD-only escape hatch in
  `smt_emit.py::_validate_world` (the `if w.cost_cap.currency
  != "USD"` block raising "USD only"). Phase 5a's
  `_validate_currency_consistency` remains in place as the
  asfaleia floor for mismatched-currency cases.

- `tests/test_smt_emit.py::test_eur_currency_rejected_v4_13`.
  The test asserted error message "USD only" which no longer
  exists. The mismatch case it exercised (USD pricing + EUR
  cap) is covered by `test_currency_consistency_eur_pricing_rejects`
  and the new `test_smt_emit_eur.py::TestCurrencyMismatchStillRejected`
  class.

### Migration guide

```bash
# Migrate a v1.0 pricing TOML in place:
nous prices upgrade ./nous_prices.toml --in-place

# Migrate to a separate output file (safe for review):
nous prices upgrade ./nous_prices.toml -o ./nous_prices_v2.toml
diff ./nous_prices.toml ./nous_prices_v2.toml

# After migration, cost_cap.currency MUST equal pricing _currency.
# If your project uses a non-USD provider (e.g. Mistral via Le
# Plateforme), update BOTH sides:
#   1. _currency = "EUR"        in your pricing TOML
#   2. cost_cap: 0.50 EUR       in your world block
```

PYTEST_FLOOR: 354 -> 394

## [4.18.0] - 2026-05-01

### Added
- `DiffSide` provenance model in `nous_api.py`: classifies one side of a diff
  comparison by `kind` (template / editor / paste / replay / file / unknown),
  optional `identifier`, and optional `label` override.
- `DiffRequest.original_side` and `DiffRequest.modified_side` (both optional;
  default `None` = backward compatible with 4.16.x clients).
- `render_diff_side()` canonical renderer producing deterministic display
  strings: `Template: sycophancy_guard`, `Editor (current)`, `Paste A`,
  `Replay 550e8400...`, `File: sample.jsonl`, `(unknown source)`.
- `/v1/diff` response now includes `original_label` and `modified_label`
  fields, server-rendered via the canonical function. Clients that send
  no provenance get `(unknown source)` for both -- explicit, not fabricated.
- 17 regression tests in `tests/test_diff_side.py` covering every kind,
  edge cases (anonymous paste, missing identifier, label override),
  request roundtrip, and Literal enum rejection of unknown kinds.

### Fixed
- The IDE diff card no longer needs to hardcode the literal
  `original.nous -> modified.nous` string. All four flows (Save bar,
  template-vs-editor, paste-vs-paste, replay-vs-replay) now have a
  contract-defined provenance shape they can fill in. Frontend wiring
  follows in a separate commit (lives outside this repo at /var/www/).

### Architectural notes
- Mirrors W3C PROV: every comparison artifact has TWO sides, each with
  identity + origin metadata. Removes the audit-trail liability where
  `nous dossier` evidence pointed at fictional file names.
- `kind` is a closed Literal enum. New kinds are explicit additions, not
  silent string drift. `unknown` is the safe default; clients are not
  forced to lie.
- Server computes labels once. Audit logs and dossiers see stable strings
  regardless of client UI version.

### Breaking
- None. Existing 4.16.x clients sending only `original` and `modified`
  continue to work; the response gains two new fields they can ignore.

PYTEST_FLOOR: 320 -> 337

## [4.17.0] - 2026-05-01

### Added
- `ast_nodes.iter_route_edges(nervous_system)`: canonical iterator yielding
  `(source, target, kind)` tuples over every NerveStatement edge
  (RouteNode, MatchRouteNode, FanInNode, FanOutNode, FeedbackNode).
  Single source of truth for route enumeration; reimplementing this
  dispatch elsewhere is now a regression.
- 10 regression tests in `tests/test_iter_route_edges.py` covering
  every variant, silence-arm filtering, empty/None inputs, and
  unknown-subtype panic. PYTEST_FLOOR raised 310 -> 320.

### Fixed
- `nous show` no longer silently drops FanIn/FanOut/Feedback edges.
  Previously the `hasattr(r, "source") and hasattr(r, "target")` guard
  matched only RouteNode; programs with multi-source/multi-target
  topology displayed wrong edge counts.
- `nous cost-cap` no longer crashes on programs containing FanOutNode
  or FeedbackNode. Previously `route.target` access raised AttributeError
  on these variants.
- `behavioral_diff._get_routes` now delegates to `iter_route_edges`,
  collapsing 27 lines of duplicated dispatch into 4. Behavior preserved
  by existing test suite.

### Dependencies
- `cryptography>=42,<47` promoted from `[smt]` extra to a base dependency.
  `cli.py` loads `cli_dossier` -> `dossier` at module import (Session 64),
  so cryptography was already a hard requirement for any working install.
  The `[smt]` extra now contains only `z3-solver`.

### Internal
- NerveStatement dispatch sweep, phase 1-4. Remaining inline dispatch
  in `verifier.py`, `validator.py`, `codegen.py` deliberately retained:
  those sites do per-kind work beyond edge enumeration and need separate
  refactors.

<!-- __session63_changelog_v4_13_0__ -->

<!-- __session63_changelog_v4_13_1__ -->
<!-- __session64_changelog_v4_13_2__ -->
<!-- __session64_changelog_v4_13_3__ -->
<!-- __session65_changelog_v4_16_0__ -->
<!-- __session66_changelog_v4_16_1__ -->
## [4.16.1] - 2026-04-30
### Fixed
- **`/v1/diff`** crashed with `'FeedbackNode' object has no attribute
  'source'` (and `.target`) when either input contained a
  `FeedbackNode`, `FanInNode`, `FanOutNode`, or `MatchRouteNode` in
  its `nervous_system`. Three call sites had blind
  `route.source` / `route.target` access:
    1. `behavioral_diff._get_routes`
    2. `behavioral_diff._get_entrypoints`
    3. nested `_get_routes` inside
       `nous_api_server._transform_diff_for_ide`.
  All three now isinstance-dispatch over every `NerveStatement`
  variant and emit the correct edges (or "is a target" set).
### Tests
- New `tests/test_behavioral_diff_routes.py` (+8 tests) locks in the
  dispatch behavior for each NerveStatement variant plus mixed and
  empty cases. Pytest floor: 302 -> 310.
## [4.16.0] - 2026-04-30
### Added
- **`PUT /v1/templates/{name}`** --- save a `.nous` world template
  to `TEMPLATES_DIR`. Pairs with the existing
  `GET /v1/templates/{name}` (read) for full RESTful CRUD on
  templates. Pipeline:
  1. Hard auth (`require_write_api_key`): empty `API_KEYS` -> 403,
     missing or invalid key -> 401. Reads remain soft-auth.
  2. Name sanitisation: `^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$`,
     resolved path must stay inside `TEMPLATES_DIR`.
  3. Lint gate: `governance_lint` errors block the save unless
     `force=true`. Linter crash treated as has_errors.
  4. Backup: existing file copied to
     `<name>.nous.bak.<YYYYmmddTHHMMSS_uuuuuu>`, oldest pruned
     beyond 5 backups.
  5. Atomic write: `tempfile -> fsync -> os.replace`. No reader
     ever sees a partial file.
  6. Response includes `sha256` of bytes written.

### Architectural notes
- **No alias endpoints added.** The Session 64 sec.6.3 plan listed
  `/v1/policies/list` and `/v1/policies/validate`, but the
  existing `GET /v1/governance/policies` and
  `POST /v1/governance/lint` already cover those. Aliasing
  doubles the API surface for zero new capability and was
  rejected.
- **Endpoint named for what it actually does.** A `.nous` template
  contains the entire world (souls, mind, governance), not just
  policies. `templates/save` is honest naming.

### Tests
- `tests/test_templates_save.py` --- 13 new tests covering hard
  auth (3 paths), happy path, backup creation + pruning to 5,
  lint-errors-blocks-save, force-override, lint-unavailable,
  lint-crash, and three name-safety rejections.
- PYTEST_FLOOR: 289 -> 302.

### Compatibility
- No changes to existing endpoints. No grammar / AST / codegen
  changes. 57/57 regression templates baseline-stable.

<!-- __session65_changelog_v4_15_0__ -->
## [4.15.0] - 2026-04-30
### Added
- **`GET /v1/replay/list`** --- enumerate replay logs in
  `NOUS_REPLAY_DIR` (default `/var/lib/nous/replays`,
  env-overridable). Returns per-log metadata (name, size,
  mtime, last_seq_id, last_hash, last_kind) via O(8KB) tail
  read. Does not validate hash chains; pair with
  `/v1/replay/verify` for integrity.
- **`POST /v1/replay/diff`** --- lockstep compare two replay
  logs by `(seq_id, hash)`. Body: `{a, b, max_events?}`
  (filenames inside `NOUS_REPLAY_DIR`). Returns status =
  `identical | divergent | truncated_a | truncated_b | error`,
  with first divergence event side-by-side.

### Security
- New endpoints sandbox filenames to `NOUS_REPLAY_DIR`. Reject
  path separators, leading dot, parent-dir traversal, and
  symlinks pointing outside the directory. Existing replay
  endpoints (`summary`, `events`, `verify`) preserve their
  current absolute-path behaviour for backward compatibility.

### Tests
- `tests/test_replay_list_diff.py` --- 11 new tests covering
  list metadata, list filtering, diff identical / truncated_a /
  truncated_b / divergent, and four path-safety rejections.
- PYTEST_FLOOR: 278 -> 289.

### Compatibility
- No changes to existing endpoints. No grammar / AST / codegen
  changes. 57/57 regression templates baseline-stable.

<!-- __session64_changelog_v4_14_0__ -->
## [4.14.0] - 2026-04-29

### Added

- **`nous dossier <source.nous>`** --- new top-level subcommand
  for EU AI Act Annex IV compliance bundles. Takes a NOUS source
  plus its signed manifest, validates the full crypto chain, and
  emits a self-contained directory:

  ```
  source_dossier_<timestamp>/
      source.nous           audited program
      manifest.json         signed manifest (copy)
      pricing.toml          active pricing layer snapshot
      public_key.b64        raw 32-byte Ed25519 pubkey
      README.md             Annex IV item-by-item mapping
      verify_offline.py     portable verifier (cryptography only)
  ```

  Pre-conditions verified before any file is written
  (raises `DossierError` otherwise):
  1. Manifest Ed25519 signature is valid.
  2. Source bytes hash matches `manifest.source_sha256`.
  3. Active pricing TOML hash matches `manifest.pricing_sha256`.
  4. Re-emitted SMT spec hash matches `manifest.smt_spec_sha256`.

- **`verify_offline.py`** ships in every dossier. Pure stdlib +
  `cryptography` library. No NOUS install required. Re-checks
  Ed25519 signature and source SHA-256, prints PASS/FAIL with
  exit `0` / `1`. Designed for regulators and auditors who hold
  the dossier directory and the publisher's public key.

- New module `dossier.py` (`build_dossier()`, `DossierError`,
  `DossierResult`).
- New CLI module `cli_dossier.py` (`cmd_dossier`,
  `build_dossier_parser`).

### Architectural decision

- The original Session 63 candidate name was
  `nous prices export --format=annex_iv`. Renamed to top-level
  `nous dossier` because a dossier composes manifest + source +
  pricing + crypto, not pricing alone. The `nous prices` tree
  stays focused on pricing operations (`show`, `init`, `verify`,
  `age`).

### Tests

- `tests/test_dossier.py` --- 6 tests (272 -> 278 total).
  - happy path emits 6 expected files
  - README contains Annex IV mapping items 1-9
  - verify_offline.py is executable
  - tampered source -> source.sha256 mismatch
  - tampered manifest -> Ed25519 signature does NOT verify
  - non-empty output dir -> refuse to overwrite

### Packaging

- Added `dossier` and `cli_dossier` to `pyproject.toml` py-modules
  so wheel installs include both.

## [4.13.3] - 2026-04-29

### Added

- **`--smt-margin PCT` flag** for `nous verify --smt`. Proves
  `total_cost <= declared_cap * (100 - PCT) / 100` instead of
  `total_cost <= declared_cap`. Conservative buffer for compliance
  use cases (e.g. EU AI Act dossiers where regulators expect a
  proven safety margin against billing surprises). Range `0..99`.
  Default `0`. Example:
  ```
  nous verify file.nous --smt --smt-margin 20
  PROVEN: total_cost <= $0.4 USD across all execution paths.
    Declared cap: $0.5 USD, safety margin: 20%.
  ```

- New `SMTSpec.cost_cap_margin_pct: int` field (default `0`).
- New `Manifest.safety_margin_pct: Optional[int]` field. Populated
  only when `--smt-margin > 0`; absent from canonical JSON when
  margin is zero (preserves manifest schema for non-margin runs).

### Backward compatibility

- `--smt-margin 0` (default) preserves the v4.13.2 obligation
  literal and SMT-LIB serialize structure exactly. The spec sha256
  cycles on the version-string bump (the `NV:` canonical key
  includes `nous_version`), as it does on every release.
- 57 / 57 regression templates baseline-stable.
- All cost_cap demo templates compile, verify, and emit manifests
  byte-identically when `--smt-margin` is omitted.

### Tests

- `tests/test_smt_margin.py` -- 8 new tests (264 -> 272 total).

## [4.13.2] - 2026-04-29

### Removed

- **Broken AetherProof publish path.** `manifest.publish_to_aetherproof()`,
  the `AETHERPROOF_DEFAULT_URL` constant, and the `--publish` /
  `--publish-endpoint` CLI flags on `nous verify --smt` are gone.
  The shipped client posted to `https://api.aetherlang.online/v1/manifests`,
  but that POST endpoint was never built (only `GET /v1/manifests/{id}`
  exists publicly), and the payload schema NOUS sent did not match what
  the AetherProof service expects (gate evidence, not pre-signed
  manifests). Calling `--publish` on v4.13.1 always failed with
  `HTTP 404`.

### Architectural decision

- **NOUS manifests are self-verifying offline artifacts.** A holder of
  the manifest file plus the publisher's Ed25519 public key can verify
  authenticity without contacting any service. Storage is the
  publisher's choice (filesystem, S3, IPFS, git release, etc.) -- no
  central-ledger dependency. `manifest.verify_manifest_signature()`
  remains the offline-verification primitive. `sign_manifest`,
  `manifest_json`, `parse_manifest_json`, and the keypair management
  helpers are unchanged.

### Documentation

- `docs/COST_VERIFICATION_GUIDE.md`, `docs/SMT_VERIFICATION_DESIGN.md`,
  and `docs/EU_AI_ACT_COMPLIANCE.md` updated to describe
  storage-agnostic, offline-verifiable manifests instead of
  POST-to-central-service.


## [4.13.1] - 2026-04-28

### Fixed

- **Shipped `pricing/defaults.toml` not found by wheel installs.**
  `pricing.py` hardcoded `<package>/pricing/defaults.toml`, but
  setuptools `data-files` installs the file at
  `<sys.prefix>/pricing/defaults.toml`. Fresh installs of v4.13.0
  could not run `nous verify --smt` (loader raised
  `FileNotFoundError: no pricing TOML found in any layer`).

  The package-defaults layer (layer 4) now resolves through a
  small helper that tries, in order:
  1. `<__file__>/pricing/defaults.toml` (dev tree, editable install).
  2. `<sys.prefix>/pricing/defaults.toml` (data-files install).
  3. `<sys.prefix>/share/pricing/defaults.toml` (some venv layouts).

  Layer index unchanged: still `4` (so existing tests and
  manifest provenance audits remain stable).

### Notes

- v4.13.0 was tagged and a GitHub release was published, but the
  wheel was **never uploaded to PyPI** because clean-install
  verification caught this issue first. v4.13.1 is the first
  v4.13.x to reach PyPI.



## [4.13.0] - 2026-04-28

### Added -- Formal SMT cost-bound verification

- **`cost_cap` world-body declaration** -- `cost_cap: 0.50 USD` declares a
  hard upper bound on total program spend. Currency parser supports USD
  (extensible to EUR etc. in Phase 5).
- **`max_ticks` world-body declaration** -- `max_ticks: 5` bounds the number
  of execution cycles. Required input for SMT proof.
- **Per-soul `tokens` declaration** -- `tokens: input=500 output=200`
  declares per-tick token estimates. Multiplied by per-token rates from
  the active pricing table to compute worst-case spend.
- **Layered pricing infrastructure** (`pricing/defaults.toml`):
  - Strict Pydantic loader with schema v1.0.
  - Priority order: `--prices` flag > `./nous.prices.toml` >
    `~/.config/nous/prices.toml` > package defaults.
  - Deterministic ordering, SHA-256 audit hash.
  - New CLI: `nous prices show / init / verify / age`.
- **`smt_emit.py`** -- deterministic SMT-LIB 2.6 emitter. Decimal -> exact
  rationals; no float artefacts. Output is byte-deterministic across
  runs and machines. New CLI: `nous emit-smt FILE.nous`.
- **`smt_verify.py`** -- Z3 wrapper with counterexample extraction and
  **constructive fix suggestions** (raise cap to X / reduce ticks to Y /
  identify largest contributor).
- **`manifest.py`** -- ed25519-signed JSON manifests (Sigstore/SLSA
  convention). Single self-contained file with embedded base64 signature.
  Tamper detection. AetherProof publish opt-in via `--publish`.
- **`nous verify FILE.nous --smt`** -- flagship CLI: parse -> emit -> solve
  -> manifest. Backward compat preserved: `nous verify FILE.nous` (no
  `--smt`) still runs governance lint as a build gate.
- **ed25519 key management** -- auto-generated at
  `~/.local/share/nous/keys/signing.key` (XDG, mode 0600).
  `--key-path` override supported.
- **`[smt]` optional extra** in `pyproject.toml`:
  `z3-solver>=4.15.0,<4.17.0` and `cryptography>=42,<47`.
- **Documentation**: `docs/COST_VERIFICATION_GUIDE.md`,
  `docs/SMT_VERIFICATION_DESIGN.md`, `docs/EU_AI_ACT_COMPLIANCE.md`.

### Changed

- Existing `nous verify` subparser extended with `--smt` flag. No new
  subparser registered. Default behaviour (no `--smt`) unchanged.

### Stats

- Tests: 184 -> 264 (+80).
- Regression templates: 54/54 byte-identical (additive arc only).
- Codegen touch: zero.
- New modules: `smt_emit`, `cli_emit_smt`, `smt_verify`, `manifest`,
  `cli_verify`, `pricing/*`.

---

## [4.12.0] - 2026-04-27

### Added

- **Single-source `VERSION` constant** -- `_version.py` is now the sole
  source of truth (`__version__: str` + `__version_tuple__: tuple`).
  `nous_api.py` reads it dynamically; no hardcoded version strings
  anywhere else.
- **R18 version-consistency test** -- verifies pip metadata matches
  `_version.__version__` after install. Run with
  `pip install -e .` to refresh metadata before invoking.
- **Atomic release pipeline** -- Phase 4.5 pyflakes gate added; release
  pipeline now has 10 phases, each commit-atomic.

### Fixed

- `cli.py`: missing `Any` in typing import.
- `nous_api_server.py`: `NousProgram` forward ref + `body`/`message`
  `NameError` in compile/verify/chat pipelines.
- `tests/conftest.py`: exclude `test_replay_phase_d.py` from collection
  (path-collection edge case).

### Changed

- Build artifacts (`build/`, `dist/`, `*.egg-info/`) added to
  `.gitignore`.

---

## [4.11.3] - 2026-04-25

### Fixed

- **Broken-template hotfix** -- `nous templates copy` was emitting a
  template that failed parser load on fresh installs.
- **Grammar single-source** -- `nous.lark` is now resolved through one
  canonical loader path. Previous duplicate-resolution paths (package
  vs sys.path) caused divergent parser state on certain installs.

---

## [4.11.2] - 2026-04-21

### Added

- **Templates as proper package** -- bundled `.nous` templates moved into
  the top-level `templates/` package and shipped via `package-data`.
  Reachable via `importlib.resources`.
- **`nous templates list / copy <name>`** CLI commands.

---

## [4.11.1] - 2026-04-21

### Changed

- **`nous_api.py` split** into thin importable library + dedicated
  `nous_api_server.py` runner. Programs that only need to call the
  library no longer pull in FastAPI/uvicorn at import time.

---

## [4.11.0] - 2026-04-21

### Added

- **Sycophancy phrase detector** (`phrase_detector.py`) -- heuristic
  pass over LLM outputs to flag flattery / capitulation / over-eager
  agreement language.
- **`llm.response` event kind** -- first-class event in the governance
  layer. Policies can match on `llm.response` and inspect the response
  string via signal helpers (e.g. `contains_phrase("absolutely")`).
- Governance lint extended to validate `llm.response` policies.

---

## [4.10.0] - 2026-04-17

### Added
- `--error-on CODES` CLI flag for `nous governance lint` -- elevate non-error rules to failure (e.g. `--error-on L010,L007`). Exit 2 on invalid rule codes.
- `nous verify` now runs governance lint after formal verification. Errors fail the build by default. New flags: `--no-lint`, `--lint-strict`, `--lint-error-on`.
- LSP server emits lint diagnostics with source `nous.lint`. Visible as red/amber/blue squiggles in VS Code (L008 error, L010 warning, L007 info).
- New module `governance_simulator.py` -- safe-eval engine for what-if policy evaluation. Data fields become bare names in signal namespace.
- New HTTP endpoint `POST /v1/governance/simulate` -- simulate an event against declared policies. Error codes SIM001/SIM002/SIM003.
- New IDE element: EVENT SIMULATION strip in Governance tab with kind/data inputs and color-coded fired/skipped matches.
- New constant `VALID_RULE_CODES` and helper `_parse_rule_codes()` in `governance_lint`.
- New template `governance_demo.nous` with 5 policies across 3 event kinds.

### Changed
- `lint_cli()` signature extended with optional `error_on: str | frozenset[str] | None = None`.
- `cmd_verify()` behavior change: files with governance lint errors now fail the build. Use `--no-lint` to restore pre-4.10.0 behavior.

### Stats
- Tests: 163 -> 212 (+49)
- Regression templates: 52/52 byte-identical
- Codegen touch: zero
- New modules: 1 (`governance_simulator`)
- New tests files: 3 (`test_governance_simulator`, `test_verify_lint_integration`, `test_lsp_lint_integration`)

## [4.9.1] - 2026-04-17

### Fixed

- **Missing module in wheel**: `governance_lint.py` was not listed in
  `[tool.setuptools].py-modules` despite being introduced in v4.9.0.
  Fresh PyPI installs of 4.9.0 raised `ImportError` when running
  `nous governance lint` or calling `POST /v1/governance/lint`.
- v4.9.0 is broken on PyPI; users should install v4.9.1 or higher.

---


## [4.9.0] - 2026-04-17

### Added -- `nous governance lint` CLI

Static analysis for NOUS policy declarations. New subcommand:

    nous governance lint <file.nous> [--format text|json] [--strict]

Rule catalog (L000-L100):

- **L000** file not found
- **L001** duplicate policy name
- **L002** empty policy name
- **L003** invalid action (must be log_only/intervene/block/abort_cycle/inject_message)
- **L004** weight out of range (0.0, 10.0]
- **L006** empty signal expression
- **L007** unknown event kind (info)
- **L008** `inject_message` policy missing `message` field
- **L009** no policies in file (warn)
- **L010** reserved name prefix `__` (warn)
- **L011** negative window
- **L012** literal `True`/`False` signal (always/never fires)
- **L100** parse error

Output: text (default) or machine-readable JSON. `--strict` promotes warnings to non-zero exit for CI pipelines.

### Added -- Interactive Governance tab in IDE (`/ide`)

Sixth tab alongside Editor/Verify/Graph/Architecture Diff/Chat. Two-column layout:

- **Policies** (left): declared policies with color-coded action badges (red for block/abort_cycle, amber for intervene, purple for inject_message, blue for log_only), weight, kind, signal expression.
- **Lint** (right): live static analysis with severity-coded issues (ERR / WARN / INFO), rule code, policy name, message.

Auto-refreshes when the tab is clicked (debounced 150ms). Manual REFRESH button. Reads source via `monaco.editor.getEditors()[0].getValue()`.

### Added -- New backend endpoint

- **POST `/v1/governance/lint`**: exposes `GovernanceLinter.lint_source()`. Request `{source: str, strict: bool}`. Response: full `LintReport` as JSON plus `would_fail_strict` flag. API-key protected, rate-limited 60/min. Error codes LNT001 (module missing) / LNT002 (internal error).

### Tests

- 37 new tests in `tests/test_governance_lint.py`.
- Total test count: **126 -> 163** (+37).
- 52/52 regression templates remain byte-identical (zero codegen impact).

### Architecture notes

- Linter uses `parse_nous()` directly instead of `PolicyInspector` so it can inspect `inject_as`, `message`, `window`, `description` fields that `PolicyInfo` strips.
- Empty/whitespace source short-circuits to L009 instead of L100 parse error for cleaner UX.
- New files: `governance_lint.py`, `tests/test_governance_lint.py`.

---

## [4.8.3] - 2026-04-17

### Fixed

- **Missing dependency**: `pyyaml` was not declared in `pyproject.toml`
  dependencies despite being required by `risk_engine.py` (since v4.5.0).
  Fresh installs from PyPI failed with `ModuleNotFoundError: No module named 'yaml'`
  when importing any governance module.
- `pyyaml>=6.0` is now an explicit core dependency.

### Notes

No functional code changes. v4.8.2 is broken on PyPI for clean installs;
users should install v4.8.3 or higher.

---

## [4.8.2] - 2026-04-17

### Added -- Phase G Layer 4.5: prompt-hash recompute on inject_message

When an `inject_message` policy triggers and modifies the outgoing LLM
messages, the `llm.request` event now carries three additional fields:

- `prompt_hash_post_inject`: sha256 of the canonical payload after injection
- `injected_role`: the role (`system` or `user`) that was injected
- `injected_policies`: list of policy names that caused the injection

The original `prompt_hash` (used as the replay match key) is unchanged, so
all existing recorded logs remain playable. The new fields are emitted
**only** when injection actually occurs, preserving byte-identical
codegen output for every template without inject_message policies
(52/52 regression templates verified).

### Tests

- New `test_11_llm_request_event_has_post_inject_hash`
- New `test_12_no_inject_no_rehash_fields`
- New `test_13_post_inject_hash_matches_injected_messages`
- `tests/test_inject_message.py`: 27 -> 39 checks (all green)

### Compliance

This closes the audit gap where the recorded prompt hash did not reflect
the actual content sent to the LLM after governance-driven injection.
Auditors can now verify both what was requested and what was ultimately
transmitted.

---

## [4.8.0] - 2026-04-17

### Added - Phase G Layer 4: Governance Dashboard
- `governance.py`: PolicyInspector, GovernanceLog, GovernanceStats, InterventionRecord
- `GET /v1/governance/policies` - list active policies per world template
- `GET /v1/governance/interventions` - query intervention events from replay logs
- `GET /v1/governance/stats` - aggregated governance statistics
- `nous governance policies <file.nous>` - CLI policy inspector
- `nous governance inspect <log>` - CLI intervention event viewer
- `nous governance stats <log>` - CLI governance stats
- 30 governance dashboard tests (10 test functions, 30 assertions)
- `_signal_to_str()` - human-readable signal rendering from AST



## [4.7.0] - 2026-04-17
### Added - Phase G Governance, Layer 3: Intervention Primitive + Runtime Hook
- **`intervention.py`** - new module with `InterventionEngine`, `InterventionOutcome`, `InterventionError`, `InterventionBlocked`, `InterventionAborted`
  - Synchronous hot-path check with no-op mode when no rules loaded
  - Action priority resolution: `abort_cycle > block > inject_message > intervene > log_only`
  - `inject_message` stubbed to log_only for v4.7.0 (full semantics deferred to Layer 4)
- **`replay_runtime.py`** - `ReplayContext` gains `intervention_engine` param + `set_intervention_engine()` setter
  - Pre-emit hook at 3 sites: `sense.invoke`, `llm.request` (blocks cost before spend), `memory.write`
  - `governance.intervention` audit event emitted on every triggering (record mode only)
  - `block` raises `InterventionBlocked`, `abort_cycle` raises `InterventionAborted`
  - Replay + off modes: zero intervention logic (determinism preserved)
- **`risk_engine.py`** - predicate namespace expansion
  - `event.data` string-identifier keys now exposed as bare names in predicate scope
  - `cost > 0.10` works identically in `.nous` signals and YAML predicates
  - Reserved names (event fields, stats, `value`) take precedence on collision
  - Fully backward compatible - `data.get('cost', 0)` style YAML rules unchanged
- **`codegen.py`** - runtime engine wiring
  - Emits `from intervention import InterventionEngine` + `_INTERVENTION_ENGINE = InterventionEngine(_POLICIES, _POLICY_ACTIONS)` when policies exist
  - Emits `rt.replay_ctx.set_intervention_engine(_INTERVENTION_ENGINE)` in both simple and distributed `build_runtime()` paths
  - **Zero bytes emitted when no policies declared** - 40 regression templates byte-identical
- **`nous_api.py`** - `/v1/chat` maps `InterventionBlocked`/`InterventionAborted` to HTTP 422
  - Structured payload: `action`, `policies`, `score`, `reasons`, `triggering_event_kind`
  - Codes: `CHAT_INTERVENTION_BLOCKED`, `CHAT_INTERVENTION_ABORTED`
- **`tests/test_intervention.py`** - 10/10 E2E
  - All 5 actions exercised (log_only, intervene, inject_message, block, abort_cycle)
  - LLM block verified to prevent cost spend (execute() never runs)
  - Action priority resolution, codegen emission, generated module load
### Stability
- **40 regression templates byte-identical** throughout all 8 patches (54, 54b, 55, 56, 57c, 58, 59, 60)
- All 43 previous tests remain green
- **53 total replay+governance tests** (43 previous + 10 Intervention)
### Governance loop closed
- Layer 1 (RiskEngine, v4.5.0) + Layer 2 (Policy DSL, v4.6.0) + Layer 3 (Runtime enforcement, v4.7.0)

## [4.6.0] - 2026-04-17
### Added -- Phase G Governance, Layer 2: Policy DSL
- **Grammar extension** -- `policy NAME { ... }` blocks inside `world`
  - Keywords: `policy` | `πολιτική` (POLICY.2 terminal)
  - Clauses: `kind`, `signal`, `window`, `weight`, `action`, `description`
  - Actions: `log_only`, `intervene`, `block`, `inject_message`, `abort_cycle`
  - **Native NOUS expressions** as signals -- type-checked at parse time, not runtime strings
- **AST nodes** -- `PolicyNode` (Pydantic V2) with `PolicyAction` Literal enum
  - Rejects invalid actions at construction time (compile-time type safety)
  - `WorldNode.policies: list[PolicyNode]` default empty
- **Validator** -- `_check_policies()` with 5 error codes
  - PL001 duplicate name, PL002 missing signal, PL003 weight range, PL004 negative window, PL005 empty kind
- **Codegen emission** -- `_emit_policy_constants()`
  - Emits `_POLICIES: list[RiskRule] = [...]` + `_POLICY_ACTIONS: dict[str, str]`
  - Imports `risk_engine.RiskRule` only when policies present
  - Reuses `_expr_to_python` for signal -> predicate translation (binop, not, compare)
  - **Zero bytes emitted when no policies declared** -> 40 regression templates byte-identical
- **RiskRule** -- extended with `action: str = "log_only"` field (backward compatible)
  - `from_dict` reads optional `action` from YAML
  - Existing YAML rules continue to work unchanged
- **`tests/test_policy_grammar.py`** -- 10/10 E2E
  - Parse, AST typing, defaults, validator positive+negative, codegen emission, zero-output-without-policies, runtime RiskRule instantiation, py_compile

### Stability
- **40 regression templates remain byte-identical** -- the critical gate
- All previous tests green: Foundation 7/7, Phase C 10/10, Phase D 6/6, Risk 10/10
- **43 total replay+governance tests** (7 + 10 + 6 + 10 + 10)

### Why 4.6.0 (minor bump)
Layer 2 closes the loop: policies now live in source code as first-class constructs,
compiled into the same `RiskRule` runtime used by Layer 1. Rules written in `.nous`
and rules loaded from YAML merge into a unified governance surface.
Layer 3 (Intervention primitive + runtime hook) follows in 4.7.0.


## [4.5.0] - 2026-04-17
### Added -- Phase G Governance, Layer 1: RiskEngine
- **`risk_engine.py`** -- runtime risk assessment over replay event logs
  - `RiskRule` (dataclass) -- YAML-configurable rule: `kind_filter`, `predicate`, `weight`, `window`, `extract`
  - `RiskAssessment` -- per-event score in [0,1] with `triggered_rules` + `reasoning`
  - `RiskReport` -- aggregate over a full log (max/mean score, rule hits, per-event detail)
  - `RiskEngine.assess(event)` and `assess_log(path)` public API
  - Sandboxed predicate eval (no `__` names, no builtins) -- safe to load untrusted rule YAML
  - Rolling per-(soul, rule) statistics for drift detection
- **`risk_rules.yaml`** -- 7 default rules: `high_llm_cost`, `llm_token_burst`, `sense_error`, `memory_write_burst`, `cycle_duration_spike`, `llm_error`, `response_length_anomaly`
- **`nous replay <log> --risk-report`** -- new CLI mode
  - `--rules YAML` -- load custom ruleset
  - `--json` -- machine-parseable output for CI/CD
  - `--verbose` -- per-event triggered rows
  - Exit 0 = clean, 5 = triggered, 1 = I/O error
- **`tests/test_risk_engine.py`** -- 10/10 E2E: default rules, clean log, each rule fires, custom YAML, sandbox escape blocked, JSON roundtrip

### Stability
- Zero changes to existing code -- pure additive layer
- 40 regression templates remain byte-identical
- Phase A 7/7, Phase C 10/10, Phase D 6/6, Risk 10/10 -- all green
- 33 total replay+governance tests

### Why 4.5.0 (minor bump)
Phase G (Governance) is a new capability layer, not a patch to Replay. Layer 1 ships the foundation (scoring); Layers 2-4 (grammar `law` blocks, `Intervention` primitive, dashboard) will follow in 4.6.0 / 4.7.0 / 4.8.0.


## [4.4.3] - 2026-04-17
### Added
- **Phase D -- LLM Replay in API** -- chat endpoint now supports deterministic LLM replay
- **`ReplayContext.record_or_replay_llm`** -- coroutine wrap for any async LLM call
  - Events: `llm.request`, `llm.response`, `llm.error`
  - Match key: `sha256(provider | model | canonical(messages) | temperature)[:16]`
  - Prompt hash mismatch raises `ReplayDivergence`
  - Preserves cost, tokens_in, tokens_out, tier, elapsed_ms in recorded response
- **`ChatRequest`** extended with three optional fields: `replay_mode` (off|record|replay), `replay_log`, `replay_seed_base`
- **`tests/test_replay_phase_d.py`** -- 6-step E2E harness (OFF passthrough, record roundtrip, replay hit, prompt-hash divergence, error record+replay, seed determinism)

### Changed
- `/v1/chat` handler wraps the tier-call loop under `ReplayContext` when `replay_mode != "off"`; default behavior unchanged

### Stability
- 40 regression templates remain byte-identical
- Phase A foundation: 7/7, Phase C E2E: 10/10, Phase D E2E: 6/6 -- all green


## [1.4.0] - 2026-04-12

### Added
- **LALR parser** -- 90.6x faster than Earley (3.3ms vs 324ms per parse)
- **Multi-world execution** -- `nous run a.nous b.nous` runs worlds concurrently via asyncio.TaskGroup
- **multiworld.py** -- WorldInstance, SharedChannelBus, MultiWorldRunner
- **Constitutional guards** -- C001 (NoLiveTrading enforcement), C003 (MaxPositionSize warning), C004 (MaxDailyLoss warning)
- **ConstitutionalGuard class** in codegen -- position check, daily loss circuit breaker, audit log
- **ccxt RSI-14** -- Real OHLCV from Binance/Bybit/Gate/KuCoin/OKX with Wilder smoothing
- **Exchange fallback chain** -- 5 exchanges, contract address detection, exotic quote skip
- **`_sense_*` methods** -- Per-soul tool delegation to `self._runtime.sense()`
- **`WORLD_CONFIG` dict** -- World config + env vars accessible in generated code
- **`model_rebuild()`** -- After every Pydantic message class in codegen
- **infra_monitor.nous** -- Example infrastructure monitoring world

### Changed
- **nous.lark** -- Keyword priority `.2`, `remember_set`/`remember_add` split, `then_block`/`else_block` sub-rules
- **parser.py** -- Zero workarounds, `_strip()` helper, `string_lit` returns `{"kind": "string_lit", "value": "..."}`
- **codegen.py** -- `self` -> `self.name`, `.where()` -> `.filter()`, runtime integration in `run_world()`
- **validator.py** -- Recursive tool scanning in if/for bodies, `_get_bool_law()`/`_get_currency_law()` helpers
- **cli.py** -- v1.4.0, `nargs="+"` for multi-file support
- **gate_alpha_scan.py** -- Pair format: `symbol/quote` instead of contract address
- **fetch_rsi.py** -- Full rewrite with ccxt async

### Fixed
- `self` in .nous generating Python object instead of soul name string
- `.where(field > val)` crash -- ToolResult has `.filter()` not `.where()`
- `world.config.X` generating undefined `world_config` variable
- Channels not connected to runtime
- Pydantic forward refs crash in dynamic import (model_rebuild fix)

## [1.1.0] - 2026-04-11

### Added
- Initial grammar, parser, AST nodes, validator, codegen
- CLI with compile/run/validate/evolve/nsp/info/bridge commands
- NSP protocol (70% token savings)
- Aevolver DNA mutation engine
- Migration tool (106 agents from YAML/TOML)
- VS Code extension
- Gate Alpha example (4 souls: Scout, Quant, Hunter, Monitor)

## [1.0.0] - 2026-04-10

### Added
- Project inception
- Grammar design (Lark EBNF)
- Core AST node definitions
<!-- __changelog_ascii_fold_s84_v1__ -->
