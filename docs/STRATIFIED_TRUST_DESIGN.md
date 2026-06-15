# NOUS Stratified Trust Layer -- Vocabulary Lock and Serialization Contract

Status: FROZEN as of S144 U0. This document is the single source of truth for
the trust-declaration vocabulary. The enum strings below are folded into
`TraceEnvelope.canonical_body_bytes()` and signed. Altering any string later
breaks signature backward-compatibility for every prior trace and conformance
certificate. New values may only be APPENDED to a Literal set (append is
parse-compatible); existing strings are never renamed or removed.

## 1. Why freeze before writing code

The trust declaration travels inside the signed body of the trace. A signature
is computed over `canonical_body_bytes()`. If an enum string changes after the
first witnessed-run trace is signed, every consumer that re-derives the body to
check the signature computes different bytes and the signature fails. The
vocabulary is therefore a cryptographic interface, not an implementation detail.
It is locked here before any field is added to the model.

## 2. Two evidence types

NOUS now produces two complementary evidence artifacts that share the same
TraceEnvelope spine:

- ENVELOPE evidence (the existing, deterministic artifact): the compiled path
  proves a cost ENVELOPE -- "no path can exceed the declared cap" -- with
  byte-deterministic output given the same source. It carries placeholder zero
  token counts because it does not execute a real model call. This is the
  design-time conformity proof.

- WITNESSED-RUN evidence (the new artifact): the live path records the REALIZED
  run -- actual provider-reported token counts from real model calls -- into a
  signed TraceEnvelope. This is a tamper-evident empirical record of one run. It
  is inherently non-deterministic (depends on the run) and rests on explicit
  trust assumptions declared in the artifact itself.

Both are Annex IV relevant. The envelope proof is the design-time bound; the
witnessed-run record is the operational log Article 12 requires. Neither
replaces the other.

## 3. The three-link trust chain (what is proven, what is assumed)

Cost/model evidence binds across three links. The witnessed-run record makes
each link's status EXPLICIT rather than silently assumed:

1. verifier <- trace: the conformance verifier binds what the trace asserts.
   PROVEN (obligation #4 recomputes realized total from the trace's token
   counts; the `cost_binding` value records whether those counts are realized or
   envelope placeholders).
2. trace <- runtime: the trace faithfully records what the runtime observed.
   ASSUMED (trusted-recorder). The trace is signed by the issuer, so this link
   proves the ISSUER did not tamper with the recorded values after the fact, but
   not that the runtime recorded faithfully in the first place.
3. runtime <- provider: the provider-reported token `usage` is true. NOT
   verifiable today with first-party APIs (industry-wide gap: providers relay an
   unsigned plaintext usage block; token overbilling and model substitution are
   undetectable from the response alone). The `provider_token_integrity` value
   records this link's status honestly.

The honest claim of a witnessed-run record: "this run, as recorded, stayed
within its declared envelope, AND the issuer did not tamper with the relayed
usage, AND the provider-token-integrity status of that usage is <declared
tier>." It is NOT "the provider reported truthfully." Link 3 is isolated and
named, not hidden.

## 4. Frozen vocabulary (verbatim)

```
evidence_kind            : Literal["envelope", "witnessed_run"]
cost_binding             : Literal["envelope", "realized"]
provider_token_integrity : Literal["unattested", "tee_attested", "unverifiable"]
```

### 4.1 Value semantics

- evidence_kind
  - "envelope"      : design-time cost-envelope proof; token counts are
                      placeholders. RESERVED string -- see 6: NOUS never emits
                      it explicitly; absence of the trust triple denotes it.
  - "witnessed_run" : empirical record of a realized run with real token counts.

- cost_binding
  - "envelope"      : obligation #4 operated on envelope placeholders; it proves
                      the bound, not the realized run. RESERVED string (see 6).
  - "realized"      : obligation #4 operated on real provider-reported token
                      counts; it binds the realized run under the link-2 and
                      link-3 assumptions declared alongside.

- provider_token_integrity
  - "unattested"    : provider returned an unsigned usage block; link 3 is
                      assumed, not verified. (Emitted in S144 for every
                      witnessed run.)
  - "tee_attested"  : the run targeted an attested endpoint and a provider/TEE
                      inference receipt is attached AND verified by the verifier
                      against pinned vendor roots. RESERVED in S144 -- not
                      emitted until the attestation-receipt verifier arc lands.
                      A trace asserting this value WITHOUT a verifier-checked
                      receipt is REFUSED (fail-closed).
  - "unverifiable"  : the provider/path is known to preclude attestation (link 3
                      cannot be closed even in principle for this run). RESERVED
                      in S144 -- not emitted until a producer path sets it.

### 4.2 Emitted vs reserved in S144

| value                              | S144 status |
|------------------------------------|-------------|
| evidence_kind = witnessed_run      | EMITTED     |
| evidence_kind = envelope           | RESERVED (denoted by absence) |
| cost_binding = realized            | EMITTED     |
| cost_binding = envelope            | RESERVED (denoted by absence) |
| provider_token_integrity = unattested   | EMITTED |
| provider_token_integrity = tee_attested  | RESERVED (requires receipt verifier) |
| provider_token_integrity = unverifiable  | RESERVED (no producer path yet) |

Reserved values are part of the frozen vocabulary so future arcs add NO new
strings. They are parseable today; they are simply never produced by S144.

## 5. Where the fields live

- The three fields are members of `TraceEnvelope`. They are inside
  `canonical_body_bytes()` -- i.e. SIGNED. This is what binds the trust
  declaration to the same signature as the realized token counts (link-2
  tamper-evidence for the declaration itself).
- The conformance certificate mirrors `cost_binding` and
  `provider_token_integrity` (the two that qualify the verdict's trust tier).
  `evidence_kind` stays a trace property. The certificate schema version is
  bumped and the new cert fields are gated below the new version in the cert
  canonical body (existing-cert byte-safety, mirroring the sequence_ok
  precedent).

## 6. Serialization contract (byte-identity invariant)

- Carrier: each field is `Optional[Literal[...]] = None`.
- Drop-when-None in BOTH `canonical_body_bytes()` AND `persisted_dict()` (both
  sites; a miss in either desynchronizes signed bytes from stored bytes).
- Absence of the trust triple IS the canonical ENVELOPE form. NOUS NEVER emits
  the explicit strings "envelope" / "envelope"; an envelope/legacy trace carries
  no trust fields at all. This guarantees every pre-S144 trace is BYTE-IDENTICAL
  and every existing signature still verifies.
- All-or-nothing: the three fields are either all None (envelope/legacy) or all
  set (witnessed_run). A partial triple is REFUSED at construction. This
  prevents an ambiguous half-declared trust state from ever being signed.
- A witnessed_run trace therefore serializes exactly:
  `"evidence_kind":"witnessed_run","cost_binding":"realized","provider_token_integrity":"unattested"`
  (S144), with the keys sorted into the compact JSON body alongside the existing
  fields.

## 7. Cross-consistency invariant (verifier-enforced)

The verifier (not only the producer) enforces, fail-closed, as a precondition
before any obligation boolean:

- `cost_binding == "realized"` IFF `evidence_kind == "witnessed_run"`.
- `cost_binding == "envelope"` (or absent) IFF `evidence_kind == "envelope"`
  (or absent).
- `provider_token_integrity == "tee_attested"` REQUIRES a verifier-checked
  inference receipt; absent/invalid receipt -> REFUSE.

The producer-side model also rejects a partial or inconsistent triple at
construction (defense in depth), but the verifier never trusts the producer:
it re-checks the invariant itself.

## 8. Backward-compatibility guarantee

- Every trace and certificate produced before S144 is byte-identical and its
  signature still verifies (the trust triple is absent -> dropped).
- The regression harness (57 compiled templates) is unaffected -- it exercises
  codegen byte-identity, not the trace/runtime path.
- Adding a future provider_token_integrity tier is an APPEND to the Literal and
  is parse-compatible; renaming or removing a value is forbidden.
