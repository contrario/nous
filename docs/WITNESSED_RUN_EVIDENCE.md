# Witnessed-Run Evidence and the Stratified Trust Layer

Since S144, NOUS produces two complementary evidence artifacts, and every signed
artifact declares which of its trust links are cryptographically bound and which
rest on an explicit, named assumption. This document explains both. The trust
vocabulary itself is frozen in `STRATIFIED_TRUST_DESIGN.md` (the cryptographic
interface); this document is the user- and auditor-facing reference for what the
evidence means.

## 1. Two evidence types

NOUS emits two artifacts that share the same `TraceEnvelope` structure and the
same offline verifier:

- ENVELOPE evidence (deterministic, design-time). The compiled path proves a
  cost ENVELOPE: "no execution path can exceed the declared cost cap." Given the
  same source it is byte-deterministic, which is what makes its signature and
  Rekor anchor meaningful. It carries placeholder token counts because it does
  not perform a real model call. This is the conformity proof you compute before
  deployment.

- WITNESSED-RUN evidence (empirical, operational). The live path records a real
  run: actual provider-reported token counts from real model calls, sealed into
  a signed `TraceEnvelope`. It is non-deterministic (it depends on the run) and
  is the tamper-evident operational record Article 12 expects. It carries an
  explicit trust declaration (Section 3).

Neither replaces the other. The envelope proof bounds every possible run; the
witnessed-run record attests one actual run. A complete Annex IV story uses
both: the envelope as the design-time bound, the witnessed-run records as the
lifecycle log.

How each is produced:

- Envelope: the compiled trace path (`compiled_trace.run_compiled_with_trace`)
  and the dossier/dossier-spec flows. No trust triple is emitted; absence is the
  canonical envelope form.
- Witnessed run: the live runtime path (`nous_ast_runner`, `mode == "live"`).
  The recorder stamps the trust triple and finalizes a signed envelope carrying
  the real provider-reported token counts. A `dry-run` does NOT produce
  witnessed-run evidence (it records placeholder zeros), so it stays envelope.

## 2. The three-link trust chain

Cost and model evidence binds across three links. NOUS makes each link's status
explicit rather than silently assuming it.

1. verifier <- trace. The conformance verifier binds what the trace asserts.
   PROVEN: obligation #4 recomputes the realized total from the trace's token
   counts under the proof's pinned rates. The `cost_binding` field records
   whether those counts are realized (a witnessed run) or envelope placeholders.

2. trace <- runtime. The trace faithfully records what the runtime observed.
   ASSUMED (trusted recorder), but the trace is signed: the signature proves the
   ISSUER did not tamper with the recorded values after the fact. It does not
   prove the runtime recorded faithfully in the first place.

3. runtime <- provider. The provider-reported token usage is true. NOT
   verifiable today with first-party model APIs: the provider returns an
   unsigned usage block, and token overbilling or model substitution cannot be
   detected from the response alone. The `provider_token_integrity` field
   records this link's status honestly.

What a witnessed-run record actually claims:

  This run, as recorded, stayed within its declared envelope; AND the issuer did
  not tamper with the relayed usage; AND the provider-token-integrity status of
  that usage is <the declared tier>.

It does NOT claim the provider reported truthfully. Link 3 is isolated and
named, never hidden. Closing link 3 (so that the provider cannot lie about
tokens or substitute a model) requires a trust root outside the issuer and the
provider's plaintext response -- a TEE/attested-inference receipt, which the
`tee_attested` tier is reserved for.

## 3. The trust declaration (frozen vocabulary)

Three fields, each `Optional` and folded into the signed canonical body. Absence
of all three is the canonical envelope form (byte-identical to every pre-S144
trace). A witnessed run carries all three. The exact value sets are frozen in
`STRATIFIED_TRUST_DESIGN.md`.

- `evidence_kind`: `envelope` | `witnessed_run`
- `cost_binding`: `envelope` | `realized`
- `provider_token_integrity`: `unattested` | `tee_attested` | `unverifiable`

Emitted today: `witnessed_run`, `realized`, `unattested`. The remaining values
are reserved (parseable, never emitted yet): `envelope`/`envelope` are denoted
by absence; `tee_attested` lands with the attestation-receipt verifier;
`unverifiable` lands when a producer path declares a provider that precludes
attestation.

The certificate mirrors `cost_binding` and `provider_token_integrity` (the two
that qualify the verdict's trust tier) under certificate schema version 3.
Certificates produced before S144 are schema 2; the new fields are excluded from
their canonical body, so every prior certificate signature still verifies.

## 4. Verifier enforcement (fail-closed, zero-trust)

`verify_conformance` enforces, as preconditions before any obligation boolean,
re-checking each invariant itself rather than trusting the producer:

- Vocabulary: any present trust value must be in its frozen set, else REFUSE.
- Cross-consistency: `cost_binding == "realized"` if and only if
  `evidence_kind == "witnessed_run"`, else REFUSE. A trace cannot claim realized
  cost without declaring a witnessed run, or vice versa.
- Attestation: `provider_token_integrity == "tee_attested"` requires an attached,
  verifier-checked inference receipt. No receipt mechanism exists in this build,
  so `tee_attested` is REFUSED fail-closed: a trace cannot claim hardware
  attestation without a verifiable receipt.

The trust tier is NOT an obligation: it does not enter the conformance verdict's
six/seven obligation booleans and does not change obligation #4 math. It
qualifies HOW MUCH the realized-cost result can be trusted, separately from
whether the obligations hold.

## 5. The `--require-attestation` verify mode

`nous conformance verify ... --require-attestation` fails the verdict unless
`provider_token_integrity == "tee_attested"`. Default behaviour reports the tier
and does not gate on it. Because `tee_attested` is not yet emittable, this flag
currently fails every run by design -- it is the forward-looking gate for
deployments that will require attested inference once the receipt verifier ships.

## 6. Honest boundary, restated

- Closed by a witnessed-run record: silent substitution of the operational log
  by the issuer (the trace is signed), and the gap between "no path can exceed"
  (envelope) and "this run did not exceed" (realized).
- NOT closed: a provider that misreports tokens or substitutes a model (link 3),
  and a runtime that records unfaithfully (link 2). These need a trust root
  outside the issuer; the `tee_attested` tier and a future attestation-receipt
  verifier are the path to closing link 3.

The value of the stratified declaration is that this boundary is machine-checkable
and travels inside the signed artifact, rather than living in prose an auditor
must take on faith.

## 7. Cross-references

- `STRATIFIED_TRUST_DESIGN.md` -- the frozen vocabulary and serialization
  contract (the cryptographic interface).
- `RUNTIME_CONFORMANCE.md` -- the conformance obligations and the standalone
  certificate.
- `COST_VERIFICATION_GUIDE.md` -- how the cost bound is computed; envelope vs
  realized.
- `ANNEX_IV_MAPPING.md` -- where this evidence maps in the Annex IV crosswalk
  (Article 12 record-keeping, Annex IV (3) monitoring).
