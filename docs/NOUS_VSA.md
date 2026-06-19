# NOUS Verification Summary Attestation (VSA)

This document describes the `nous vsa` workflow that wraps an already
-signed NOUS evidence set (manifest, runtime trace, conformance
certificate) in a portable, offline-verifiable
[SLSA Verification Summary Attestation](https://slsa.dev/spec/v1.1/verification_summary).

The VSA is a purely additive *consumer* of artifacts NOUS already
produces. It introduces no new field into the Manifest or the
Certificate and adds no new trust root: the manifest, trace, and
certificate Ed25519 signatures and the coverage Farkas arithmetic
remain the only things a verifier must trust.

<!-- __s157_docs_nous_vsa_v1__ -->

## 1. What a VSA is here

A VSA is a single signed statement that says: "this verifier checked
these named artifacts and re-derived this verdict." It is an in-toto
Statement v1 (`_type https://in-toto.io/Statement/v1`) carrying a SLSA
verification-summary predicate (`predicateType
https://slsa.dev/verification_summary/v1`, `slsaVersion 1.1`), wrapped
in a DSSE envelope (`payloadType application/vnd.in-toto+json`) and
signed with a persistent NOUS VSA key.

The point of the VSA is delegation of confirmation, not a new proof:
a consumer who trusts the NOUS VSA key can read one small signed object
instead of re-running the full verifier, while a consumer who trusts
nothing can still re-derive everything from the carried artifacts with
`cryptography` and the Python standard library alone.

## 2. EVIDENCES vs PROVES (the honest scope)

NOUS reserves "proves" for results that are re-checkable by
mathematics with no trusted oracle. Everything else evidences.

- The coverage Farkas certificate (when carried) PROVES policy
  coverage offline: the infeasibility certificate is re-checked by
  pure rational arithmetic (lambda >= 0, lambda^T A = 0,
  lambda^T b < 0) using `Fraction`, with no solver and no NOUS code.
- The eight conformance obligations, the codegen leg, and the cost
  cap EVIDENCES: they are sha-equality and signature checks over
  signed artifacts. The cost cap was proven by Z3 at emission time,
  but no Farkas certificate is carried for it, so offline it is an
  EVIDENCES leg, not a PROVES leg.

A VSA evidences that a verification occurred over the named artifacts
and that its verdict is re-derivable. It does NOT attest that the
agent run actually executed (execution attestation is out of scope)
and it does NOT make any claim of EU AI Act conformity by itself.

## 3. Emit

```
nous vsa emit <trace.json> \
  --manifest <manifest.json> \
  --cert <conformance.json> \
  [--coverage <coverage.farkas.json>] \
  --out <bundle_dir> \
  [--key-path <vsa_signing.key>]
```

`emit` computes the manifest, trace, and certificate input-attestation
digests by the same canonical method the offline verifier uses (strip
`signature` and `transparency_log`, serialize with sorted keys and
compact separators, sha256), so the emitted digests are byte-identical
to what the verifier recomputes. It re-derives the `verificationResult`
from the eight certificate obligations rather than trusting the
recorded boolean, signs the DSSE envelope with the persistent VSA key
(default `~/.local/share/nous/keys/vsa_signing.key`, 0600), and writes
a complete self-verifying bundle into `--out`:

- the input artifacts, copied byte-for-byte (the coverage Farkas file
  is hashed as raw bytes, so an exact copy is mandatory)
- `vsa.intoto.json`, the signed DSSE envelope
- `verify_vsa_offline.py`, the portable offline verifier, pinned to
  the public half of the signing key

If `--coverage` is given, `emit` refuses unless the file sha256 matches
the manifest's `coverage_farkas_sha256`, so a mismatched or tampered
Farkas certificate cannot enter the bundle.

## 4. Verify

```
nous vsa verify <vsa.intoto.json> [--dir <bundle_dir>] [--key-path <p>]
```

`verify` is the internal validation path. It copies the bundle into a
temporary directory, emits a fresh `verify_vsa_offline.py` pinned to
the local VSA key, and runs it. This executes the exact artifact a
consumer runs (single source, zero drift) without mutating the bundle.

Third parties verify with the shipped `verify_vsa_offline.py` directly:

```
python3 verify_vsa_offline.py
```

It requires only `cryptography` and the standard library.

## 5. What the offline verifier checks

The verifier is zero-trust by construction:

1. It verifies the DSSE envelope signature against the pinned public
   key using the exact PAE preimage, and parses only the verified
   payload bytes (never the unverified envelope).
2. It recomputes each input digest canonically and checks it against
   the VSA subject and `inputAttestations`.
3. It verifies the manifest, trace, and certificate Ed25519 signatures
   against their own embedded public keys.
4. It re-derives the conformance verdict from the eight obligations and
   rejects a `verificationResult` that disagrees (a lying verdict is
   reported, not honored).
5. It checks the codegen leg by sha-equality across certificate,
   trace, and manifest.
6. If a coverage Farkas certificate is carried, it re-checks the
   infeasibility certificate with `Fraction`; a forged sha-match that
   does not actually prove unsat is rejected.

The output banner names each leg as PROVES or EVIDENCES so a reader can
never mistake an EVIDENCES leg for a mathematical proof.

## 6. Predicate field reference

| Field | Meaning |
|-------|---------|
| `subject[].digest.sha256` | the verified program identity (codegen sha when present, else source sha) |
| `verifier.id` | the NOUS VSA verifier identity URI |
| `verifier.version` | the NOUS version that emitted the VSA |
| `timeVerified` | the certificate `issued_utc` |
| `resourceUri` | the world name as `nous:world:<name>` |
| `policy.digest.sha256` | the obligation-set fingerprint (which obligations were checked) |
| `inputAttestations[]` | manifest, trace, and certificate canonical digests |
| `verificationResult` | PASSED or FAILED, re-derived offline |
| `verifiedLevels[]` | `ORG_NOUS_CONFORMANT_V1` when conformant |
| `slsaVersion` | `1.1` |

`dependencyLevels` is intentionally omitted (an absent field is a
no-claim; an empty object would falsely assert "no dependencies").
A NOUS extension block under `https://nous-lang.org/vsa/ext/v1` records
the per-leg PROVES/EVIDENCES labels, the subject digest kind, and any
policy violations derived from the certificate `errors`.

## 7. Out of scope (deferred)

Cross-party trusted-key resolution -- a registry that maps
`verifier.id` to an anchored public key and pins the offline-template
digest, so a third party can confirm the signer without first
receiving the bundle -- is deferred. It requires a Rekor-anchored key
and is built with the Rekor-anchoring arc rather than faked as a
signed-tier-only shortcut. Until then, `emit` pins the bundle to the
live VSA key it signs with, and the offline verifier fails closed on
any other key.
