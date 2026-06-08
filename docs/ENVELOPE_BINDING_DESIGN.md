# Envelope-Binding for Material Change: Design Freeze (S119)

Design freeze for the version-chaining of signed verification manifests across
material build changes, in support of an EU AI Act Article 25 (substantial
modification) argument. ASCII-only.

Status: DESIGN FROZEN, S119. Implementation is a separate later session,
gated on confirmation of this freeze. No implementation code is part of this
document.

Cross-references: `docs/SMT_VERIFICATION_DESIGN.md` (cost-proof soundness,
Z3 pin), `docs/VERIFY_DOSSIER.md` (dossier layout and offline verification),
`docs/RUNTIME_CONFORMANCE.md` (the per-run conformance certificate and its
honest boundary), `NOUS_COVERAGE_PROOF.md` (coverage obligation and the
Farkas certificate; the drop-when-None precedent this design follows),
`docs/ANNEX_IV_MAPPING.md` (evidence-to-Annex-IV crosswalk).

================================================================
0. Substrate this design is written against (S119 live bytes)
================================================================

Verified live before designing, not assumed. The design binds to these exact
facts; if a later session finds them changed, the live bytes win and this
freeze must be reconciled.

Manifest (`manifest.py:64`) is a FROZEN PLAIN CLASS, not Pydantic. Its signed
canonical bytes are:

    json.dumps(canonical_dict(), sort_keys=True, separators=(",", ":"))

This is plain sorted-keys compact JSON. It is NOT RFC 8785 / JCS. Every
prior-digest in this design is computed over THIS rule. No JCS dependency is
introduced.

The canonical body is the manifest minus BOTH the `signature` block and the
`transparency_log` block (confirmed identical across the plain, Rekor,
hybrid, coverage, and Farkas offline verifiers).

Manifest signed fields, as of S119:

  Always signed (14): schema_version, nous_version, smt_emit_version,
  source_sha256, pricing_sha256, smt_spec_sha256, world_name, cost_cap_usd,
  max_ticks, verdict, solver_name, solver_version, elapsed_ms, timestamp_utc.

  Drop-when-None (6): counterexample_total_usd, safety_margin_pct,
  proof_assumptions, policy_coverage_sha256, coverage_smt2_sha256,
  coverage_farkas_sha256. Each appears in `canonical_dict` only when not None
  (manifest.py lines 131-141), so a manifest that does not set it serializes
  byte-identically to one from before the field existed.

  Siblings, OUTSIDE the signed body (2): `signature`
  {algorithm: ed25519, public_key_b64, signature_b64} and `transparency_log`
  (absent / Rekor v1 / Rekor v2).

The signature block carries `public_key_b64`, so a manifest is self-verifying:
its Ed25519 signature checks against its own embedded public key with no
external key material.

The signed manifest is the SPINE of all NOUS evidence. The static dossier's
coverage fields bind to it; the per-run conformance certificate binds to it by
three shas (source, smt_spec, pricing) plus a trace sha. Chaining the manifest
therefore transitively locks everything that hangs off it.

================================================================
1. Scope and the honest boundary (stated first)
================================================================

This boundary is load-bearing and must survive verbatim into every public
surface (homepage, blog, docs, dossier README), the same way the boundaries in
`docs/RUNTIME_CONFORMANCE.md` and `coverage.html` do.

WHAT ENVELOPE-BINDING IS.

A material build change produces a fresh signed verification manifest that
proves the new build still satisfies its declared formation envelope (the SMT
cost cap, and the coverage / Farkas claim when present), and references its
predecessor by a tamper-evident digest. The chain of such manifests is
walkable backward to genesis by a third party, offline, with only the
`cryptography` library, fail-closed on any broken, missing, altered, or
no-op link. The result is an independently reconstructable version history of
the formation envelope: a sequence of signed envelope versions, each a real
build change, each linked by digest to the one before, terminating at genesis.

WHAT ENVELOPE-BINDING IS NOT.

It does NOT assert "Article 25 compliance". That is a legal conclusion NOUS
does not make. The chain produces evidence that SUPPORTS an Article 25
argument; the argument is composed by the audit, not signed by NOUS.

The chain attests the FORMATION envelope across versions: that each version's
declared bounds were proven and link to the prior. It does NOT claim any
version was executed or conformed to a run. Execution conformance remains the
job of the per-run conformance certificate (`docs/RUNTIME_CONFORMANCE.md`),
which references its manifest version by sha and is therefore located through
the chain transitively, but is never itself a link in the chain. No surface may
imply the chain proves execution conformance.

The chain proves a real-world material change was DECLARED only insofar as that
change moved a signed sha. It CANNOT prove a real-world material change that
leaves the build bytes unchanged. An operator who changes the deployed
population, the operational scope, or the intended purpose, without changing
source, pricing, SMT spec, cost cap, or tick bound, leaves a chain that looks
complete because nothing the chain can observe moved. This is the same class of
boundary as "coverage proves no gap, not impossibility" and "the trace
conforms, not that it faithfully records reality against a malicious runtime."
Population, scope, and intended-purpose changes are real-world facts outside
the signed envelope; v1 does not cover them. They are handled by deferred
adjacent declaration artifacts (the same mechanism as Article 26(4) dataset
relevance and 26(11) intended purpose: referenced by `source_sha256`, composed
by the audit, never baked into the signed object).

Historical links in a carried chain verify at the level of signature plus
digest-link plus sha-movement. Full offline re-derivation (re-run the SMT
proof, re-check `coverage.smt2` under z3, re-check the Farkas certificate by
rational arithmetic) is available only for the CURRENT build, and for genesis
only if that dossier carries its own files. Intermediate links are not
re-derivable from the chain alone, because the chain carries prior MANIFESTS
only, not prior source / coverage / Farkas files. The chain proves "a sequence
of signed envelope versions, each a real build change, linked by digest to
genesis" -- NOT "every historical build is re-derivable from scratch." No
surface may imply the second.

================================================================
2. Trigger taxonomy: provable vs asserted
================================================================

A material change is classified by whether NOUS can PROVE the trigger fired
(machine-detectable from the signed manifest bytes) or can at most RECORD a
signed operator assertion that it fired (a real-world fact NOUS cannot observe).

  TRIGGER                         CLASS       BASIS (signed bytes)
  ------------------------------  ----------  -------------------------------
  declared-limit change           PROVABLE    cost_cap_usd, max_ticks are
  (cost_cap_usd / max_ticks)                  always-signed; a difference
                                              against the prior manifest is
                                              mechanically readable.
  source / topology change        PROVABLE    source_sha256 and smt_spec_sha256
                                              move; the change is self-evident
                                              from the sha diff. WHAT changed in
                                              the topology is reported by
                                              `nous diff`, which REPORTS only.
  model-version change            PROVABLE    the model string lives in
                                              soul_assumptions, inside signed
                                              proof_assumptions and covered by
                                              smt_spec_sha256; a model change
                                              moves signed shas.
  population / scope /             ASSERTED    real-world facts; NOUS does not
  intended-purpose change         only        observe who the users are or what
                                              the purpose is. It can only record
                                              a signed operator declaration that
                                              the event occurred.

V1 SCOPE DECISION: v1 is PROVABLE-ONLY.

v1 chains and attests build-level (sha-moving) material changes: limits,
source, topology, model. There is no signed operator-asserted
`change_declaration` field in v1, and no trigger-type enum in the signed body.

Rationale, in order of weight:

  1. Architectural consistency, already decided. Descriptive / real-world
     claims (26(4), 26(11)) were already ruled to stay outside the signed
     dossier as adjacent artifacts referenced by source_sha256. Population /
     scope / purpose declarations are the same class -- descriptive,
     real-world, not verification -- so they belong to the same adjacent
     mechanism, not a new signed field. Signing one breaks the line just held.

  2. Attack surface without proof. A signed `change_declaration` says "the
     operator declared the population changed" -- NOUS signs "X was declared",
     never "X happened". In a signed, auditor-facing object, a field that looks
     like proof while being an attestation is exactly the over-trust risk this
     project guards against. It does not go in without the adjacent-artifact
     framing that disambiguates it.

  3. Honest scope is complete without the asserted set. Provable-only is fully
     honest and self-sufficient: a re-binding manifest whose signed shas differ
     from its predecessor IS the proof that the build changed. It claims no
     coverage it lacks.

  4. Refuse over-engineering. The pressing Article 25 case an auditor presses
     is build-level material change -> prove it still holds. That is exactly
     the provable set. The asserted set is real but lower-pressure and better
     adjacent.

CONSEQUENCE: the mechanism is TRIGGER-AGNOSTIC. The chain attests "this build's
envelope holds AND supersedes the prior X (by digest)." That the shas differ is
self-evident from comparing the two signed bodies; which one changed is the job
of `nous diff` (which REPORTS). No trigger enum is added to the signed body.

================================================================
3. The behavioral diff: what it reports, what it does not prove
================================================================

`nous diff <a.nous> <b.nous> [--json]` (cli.py `cmd_diff` -> `behavioral_diff
.diff_files`) emits a `BehavioralDiffResult` carrying per-soul cost projections
(old / new / delta / delta_pct) and a list of `DiffItem`s
(category x severity in {info, warning, critical}) across cost, topology,
verification, and risk.

The diff's costs are ESTIMATES (`_estimate_soul_cost`: a TIER_COSTS table times
fixed average-token heuristics, AVG_INPUT_TOKENS / AVG_OUTPUT_TOKENS), NOT the
SMT-proven cost envelope. The diff therefore REPORTS what changed; it PROVES
nothing.

ROLE IN ENVELOPE-BINDING: the diff is documentation, never the proving
mechanism. The proof that the new build's envelope holds is the fresh signed
manifest itself (verdict PROVEN, bound to source / pricing / smt_spec by sha,
Ed25519-signed), plus its coverage / Farkas fields when present. A re-binding
dossier MAY include a diff against its predecessor as a human-readable summary
of what moved; the offline verifier neither requires nor trusts it.

================================================================
4. The proven property set the chain locks
================================================================

The chain binds to the COMPLETE formation envelope via the manifest spine, not
a shorthand. Locking the manifest by digest transitively locks:

  - The SMT cost envelope: verdict (PROVEN), cost_cap_usd, max_ticks, bound to
    source_sha256 / pricing_sha256 / smt_spec_sha256, and the per-soul
    proof_assumptions when present.
  - The coverage claim when present: policy_coverage_sha256 (semantic binding),
    coverage_smt2_sha256 (z3-checkable file provenance), coverage_farkas_sha256
    (stdlib-checkable file provenance).

The per-run conformance certificate's seven obligations (v2: binding_ok,
surface_ok, assumption_discharge_ok, bound_transfer_ok, authorization_ok,
trace_signature_ok, sequence_ok; conformant = their AND) are NOT chained. The
certificate is execution-time evidence; the chain is formation-time evidence.
A certificate binds to its manifest version by sha already, so once that
manifest is in the chain, the certificate is reachable by reference -- composed
adjacent, not nested. (Coverage and Farkas are manifest-level fields, not
certificate obligations; this is recorded to prevent the recurring "6 vs 7 vs
coverage" miscount.)

WHY FORMATION-ONLY, NOT FRESH-CERT-PER-REBINDING. Material change is a
formation-time event: the build changed; does the declared envelope still hold?
The manifest / dossier is the formation proof (universally quantified over all
paths bounded by max_ticks and soul count, pre-execution). The conformance
certificate is execution-time: one specific run conformed to one trace.
Requiring a fresh certificate per re-binding would inject an execution-time
artifact into a formation-time event -- a semantic collapse, and impossible in
the general case: a new build may not have run yet, so there is no trace, and
NOUS does not fabricate a run to populate a certificate.

================================================================
5. The chain format
================================================================

5.1 The link field.

A single new signed field on the manifest:

  prior_digest: Optional[str] = None

It holds the hex sha256 of the live canonical body bytes of the immediately
preceding manifest -- that is, sha256 of the predecessor's
`canonical_dict()` serialized by the live rule (sorted-keys compact JSON),
which is the predecessor body minus signature and transparency_log.

It is drop-when-None: it appears in `canonical_dict` only when set, inserted at
its alphabetical position under sort_keys. This exactly follows the Farkas /
coverage precedent (manifest.py lines 137-141).

  - Genesis manifest: prior_digest is None -> key absent -> byte-identical to
    any pre-existing manifest. Every dossier already in the field stays
    byte-identical; no prior signature is disturbed.
  - Re-binding manifest: prior_digest is set -> key present, signed -> the link
    is tamper-evident (stripping it from a re-binding, or adding it to a
    genesis, breaks the Ed25519 signature).

5.2 The discriminator (no silent merge, axiom 8).

The PRESENCE of prior_digest is the genesis / re-binding discriminator. No
separate event_kind field is needed, because:

  1. The field has a single semantics; no second pipeline emits it (axiom 8
     guards against collision between pipelines; there is none here).
  2. It is inside the signed body -> tamper-evident in both directions.
  3. It is binary and mutually exclusive: present = re-binding, absent =
     genesis.

5.3 Self-contained, chain-carrying dossier (manifests-only).

A re-binding dossier carries, in addition to its own full artifact set
(source.nous, manifest.json, pricing.toml, public_key.b64, README.md, and
coverage.smt2 / coverage.farkas.json when present):

  chain/
    manifest_1.json        (genesis)
    manifest_2.json
    ...
    manifest_{N-1}.json    (the immediate predecessor)

Each carried prior manifest is a complete signed manifest, hence self-verifying
(its signature block embeds its own public_key_b64). The chain carries prior
MANIFESTS ONLY -- not prior source / coverage / smt2 / Farkas files. Those are
unnecessary for chain-integrity and sha-movement, and excluding them caps
growth at O(n * ~1-2 KB per manifest) rather than O(n * full dossier). Material
changes are rare events, so this is practically negligible.

The decision to carry prior bytes (option (a)), rather than a digest-only link
(option (b)), is forced by the trust model, not merely by the through-line
test. Without the prior bytes, the only way a verifier could know a sha moved
is to trust that the issuer enforced it at issuance -- a direct violation of
"the verifier does not trust the producer." A signed no-op re-binding from a
compromised, buggy, or careless issuer would pass digest-link integrity yet is
exactly what the sha-movement rule exists to catch, and it must be caught
offline with zero issuer trust. Digest-only (b) degrades the hard rule to
"best-effort if the predecessor happens to be available" and is rejected.

5.4 Offline chain-walk: fail-closed conditions.

The offline verifier (extending the existing `verify_offline.py` family;
`cryptography` + stdlib only, no NOUS install, no network) walks from the
current manifest backward to genesis. It REFUSES (exit non-zero, fail-closed)
on any of:

  1. Current or any carried manifest's Ed25519 signature does not verify.
  2. prior_digest is set but the referenced prior manifest is absent from
     chain/ (missing link).
  3. prior_digest does not equal the live canonical digest of the carried
     predecessor (altered link).
  4. The walk does not terminate at a genesis manifest (one with no
     prior_digest): a truncated or dangling chain.
  5. No sha-bearing field (source_sha256 / pricing_sha256 / smt_spec_sha256 /
     cost_cap_usd / max_ticks) differs between a link and its predecessor:
     a no-op re-binding (declared re-binding with no build change = suspect).
  6. A cycle, or more than one genesis, in the chain: malformed.

Only when the full walk reaches genesis with every link satisfying signature,
digest-link, and sha-movement does the chain verify. This is the literal
satisfaction of the through-line test: walk backward to genesis, fail-closed on
a broken link, no NOUS, no network, zero issuer trust.

================================================================
6. Manifest impact and determinism guarantees
================================================================

  - One new signed field: prior_digest (Optional[str], drop-when-None). It
    joins the existing drop-when-None group in `Manifest`, `canonical_dict`,
    and every `parse_manifest_json*` reader, in the same patch.
  - Byte-identity for unaffected dossiers: any manifest that does not set
    prior_digest (every existing dossier, and every future genesis) serializes
    byte-identically to today. Prior signatures are preserved. Proven by the
    drop-when-None precedent already shipped for the coverage and Farkas fields.
  - Determinism for re-binding manifests: given the same predecessor and the
    same build inputs, prior_digest is a pure function of the predecessor's
    canonical bytes, so a re-binding manifest is byte-deterministic.
  - The signature and transparency_log blocks stay outside the canonical body;
    prior_digest is inside it. A re-binding manifest can still be Rekor-anchored
    by the existing anchor path with no change to the anchoring logic, because
    the anchor signs the same canonical body bytes that now include
    prior_digest.

================================================================
7. Out of scope (deferred), explicitly
================================================================

  - Operator-asserted change declarations (population / scope / intended
    purpose). Deferred to the adjacent-artifact layer (the same mechanism as
    26(4) / 26(11)); design-only, separate session. NOT a signed field in v1.
  - GLM (Governance Layer Manifest) `supersedes_digest` interoperability. The
    internal chain here stands alone and is offline-verifiable on its own; it
    is NOT coupled to that external, still-evolving schema. Whether NOUS
    additionally emits a GLM-aligned declaration that references this chain is a
    separate interoperability arc, out of scope.
  - Full offline re-derivation of every historical link (carry full prior
    dossiers, with the storage cost). v1 carries manifests only. Deferred
    option if a use case ever demands per-link re-derivation from scratch.

================================================================
8. Through-line test
================================================================

After this lands, can a third party verify offline (cryptography + z3) BOTH
that a real new build still satisfies the same envelope AND that the chain to
its predecessor is intact, back to genesis?

  - New build satisfies the envelope: yes. The current dossier verifies exactly
    as today (Ed25519 manifest signature, source sha, and -- with the files it
    carries -- z3 / Farkas coverage), now additionally carrying prior_digest in
    its signed body.
  - Chain to genesis intact: yes. The carried chain/ manifests let the verifier
    check signature + digest-link + sha-movement at every step, terminating at
    genesis, fail-closed on any break, with zero issuer trust.

No claim exceeds what is signed: the chain attests a sequence of proven
formation envelopes linked to genesis, and explicitly disclaims execution
conformance and unobservable real-world changes. A forged chain, a missing
event passing as complete (within the provable set), and a no-op re-binding are
all rejected. The design is additive.

================================================================
9. Dual-registration reminder (for the implementation session)
================================================================

If the offline chain-walk logic is factored into a new top-level Python module
(rather than emitted inline into the `verify_offline.py` string family in
`dossier.py`), that module MUST be added to BOTH `pyproject.toml` py-modules
AND the `scripts/release.py` wheel-gate `required` list in the same patch, per
the dual-registration invariant. The emitted offline verifier script itself
ships inside the dossier, not as an installed module, so it is not subject to
the wheel gate; only NOUS-side code that the toolchain imports is.

================================================================
10. Acceptance checklist (this freeze satisfies all)
================================================================

  [x] Scope + honest boundary stated first, verbatim-survivable (section 1).
  [x] Trigger taxonomy with provable-vs-asserted split and v1/deferred lines
      (section 2).
  [x] Behavioral-diff binding: what it proves vs what it reports (section 3).
  [x] Version-chain format: offline-verifiable with cryptography alone,
      fail-closed on a broken link, walkable to genesis (section 5).
  [x] The discriminator field (section 5.2).
  [x] Manifest-impact decision + byte-identity for unaffected dossiers +
      determinism for re-binding dossiers (section 6).
  [x] Threat model / explicit out-of-scope + deferred section (sections 1, 7).
  [x] Through-line test (section 8).
  [x] Dual-registration reminder (section 9).
