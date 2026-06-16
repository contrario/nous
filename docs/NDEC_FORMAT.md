# NOUS .ndec -- Portable Proof-Carrying Decision Attestation

A `.ndec` file is a portable, offline-verifiable object that carries a single
NOUS governed decision together with the evidence needed to check it. It wraps
an existing NOUS dossier in a standard DSSE envelope over an in-toto v1
Statement, with a NOUS decision predicate. Media type
`application/vnd.nous.decision+zip`.

## What it proves, and what it does not

A `.ndec` PROVES the declared cost/coverage envelope of the decision: the SMT
cost bound and, when present, the policy-coverage claim, re-checked by Z3 or
by a stdlib Farkas certificate with zero solver trust. It EVIDENCES
provenance and issuer non-tampering through Ed25519 signatures.

It does NOT prove that the decision was correct, that the dossier is legally
sufficient, or that regulatory compliance is conferred. NOUS policies are
monitors, not guards: coverage proves there is no gap in the declared blocking
net, not that the agent cannot misbehave. Conformity is determined by a
notified body, not by an artifact.

## Container layout

A `.ndec` is a deterministic ZIP (stored, fixed timestamps, sorted entries):

    dossier/                  the wrapped dossier, byte-identical
      manifest.json
      source.nous
      pricing.toml
      coverage.smt2           (when present)
      coverage.farkas.json    (when present)
      annex_iv_map.json       (when present)
      public_key.b64
      README.md
      verify_offline.py       the dossier's own offline verifier
    attestation.intoto.json   DSSE envelope over the in-toto Statement
    verify_ndec.py            standalone .ndec verifier (cryptography only)
    README.ndec.txt           how to verify

## Envelope

`attestation.intoto.json` is a DSSE envelope:

    { "payloadType": "application/vnd.in-toto+json",
      "payload": "<base64 in-toto Statement>",
      "signatures": [ { "keyid": "<sha256(pubkey)>", "sig": "<base64>" } ] }

The signature covers the DSSE Pre-Authentication Encoding (PAE) of
`(payloadType, payload-bytes)`, not the raw payload. The payload is an
in-toto v1 Statement:

    { "_type": "https://in-toto.io/Statement/v1",
      "subject": [ { "name": "<world_name>",
                     "digest": { "sha256": "<manifest_canonical_sha256>" } } ],
      "predicateType": "https://nous-lang.org/attestation/decision/v1",
      "predicate": { ... } }

The subject digest is the sha256 of the dossier manifest's canonical body
(the manifest with `signature` and `transparency_log` stripped, serialized as
sorted-keys compact JSON). The predicate commits to the world, verdict, NOUS
version, the declared cost/coverage scope, the signer public key, and the
sha256 of every carried artifact -- INCLUDING the dossier verifier itself
(`verify_offline_sha256`).

The `.ndec` DSSE signature is a SECOND, distinct signature from the dossier's
own Ed25519 manifest signature; both reuse the same Ed25519 key family.

## Verification (eight steps, fail-closed)

A conforming verifier performs, in order, refusing on the first failure:

1. DSSE envelope: Ed25519 verify over `PAE(payloadType, payload)`; payloadType
   and predicateType are the NOUS decision types; `keyid == sha256(pubkey)`.
2. Parse the verified payload exactly once; never re-parse after verification.
3. Subject binding: recompute the canonical manifest sha256 from
   `dossier/manifest.json` and require it to equal the subject digest.
4. Artifact binding: recompute the sha256 of every carried artifact named in
   the predicate -- including `verify_offline.py` -- and require each to match.
5. Inner proof: run the dossier's `verify_offline.py` (or re-derive with the
   installed verifier), which checks the Ed25519 manifest signature, the
   source sha, and the cost/coverage proof (Z3 or stdlib Farkas).
6. Honest degradation: a coverage step that needs Z3 in an environment without
   it reports environment-limited (exit 2) rather than passing or failing.
7. Verdict and scope are printed, including the machine-readable honest
   boundary (proves / evidences / not-claimed).
8. Exit 0 PASS, 1 FAIL, 2 environment-limited.

## Trust model

Two verification paths exist, by design at different trust levels:

- The carried `verify_ndec.py` is a no-install convenience: it checks the
  envelope and bindings in `cryptography` + stdlib, then runs the
  signature-pinned carried dossier verifier as a subprocess. Its guarantee
  reduces to the signer key plus the predicate pin.
- The installed `nous verify <file>.ndec` is the trusted path: the envelope
  and binding logic are the installed NOUS code, not carried bytes. It
  additionally confirms the carried `verify_offline.py` is an unmodified
  official NOUS verifier by exact-sha membership in the installed canonical
  template set (`canonical_verifier_digests`). A match closes the
  trusting-trust gap even against a malicious signer, because a doctored
  verifier cannot match an exact sha. A non-match degrades honestly to a
  signature-pinned-only statement; `nous ndec verify --strict-canonical`
  refuses anything not confirmed canonical.

The carried-verifier pin defends against tampering with a legitimately signed
`.ndec` in transit or at rest. The canonical allowlist defends against a
malicious signer shipping a doctored verifier. A cross-version
Rekor-anchored verifier-digest registry, which would let the canonical match
succeed across NOUS versions independently of any single installed build, is
proposed but not yet shipped.

## CLI

    nous ndec build <dossier-dir> [--key-path PATH] [-o OUT.ndec]
    nous ndec verify <file>.ndec [--strict-canonical]
    nous verify <file>.ndec

`build` wraps an existing dossier directory; it does not rebuild the dossier,
and it refuses to wrap a dossier whose manifest signature or declared shas do
not verify. `verify` and `nous verify <file>.ndec` use the installed trusted
path.

## Determinism

Given the same dossier directory and signing key, `build` produces a
byte-identical `.ndec` (stored ZIP, fixed entry timestamps, sorted names; the
Ed25519 signature is deterministic and the payload is sorted-keys compact
JSON). Determinism is what makes the attestation reproducible and the
signatures meaningful.
