# NOUS Verifier-Digest Registry -- cross-version canonical confirmation

Status: shipped v5.47.0 (S148). Mechanism present and offline-verifiable;
exercised against a synthetic Rekor v2 anchor and the live `build` ceremony.
No production registry signing key is pinned and no live anchor ships until an
operator publish ceremony issues them (see section 6). Until then the registry
path is dormant: with the default empty pin it always misses, and `.ndec`
verification is byte-identical to S147.

This document is the reference for the verifier-digest registry, which closes
the version-coupling of the S147 canonical-verifier allowlist. It builds on the
`.ndec` format (`docs/NDEC_FORMAT.md`) and the Rekor v2 read path
(`docs/REKOR_V2_MIGRATION.md`).

---

## 0. The problem it solves

S147 closed the trusting-trust gap on the installed `.ndec` verify path: before
running a carried `verify_offline.py`, the installed verifier confirms it is an
unmodified official NOUS template by exact-sha membership in
`ndec.canonical_verifier_digests()`. That set is computed from the templates of
the LOCAL install. A legitimate `.ndec` whose carried verifier was emitted by a
DIFFERENT NOUS release has a different template sha, misses the local set, and
degrades to signature-pinned -- trusting-trust is not closed, and
`--strict-canonical` refuses it.

The registry removes the version coupling. It is a signed, optionally
Rekor-v2-anchored static file that maps each official `VERIFY_OFFLINE_PY*`
template (by name and emitting NOUS version) to its sha256, across versions. On
a local miss, the installed verifier consults the registry; a confirmation
there closes trusting-trust across versions without the verifier matching the
locally installed template set.

## 1. What it evidences, and what it does not

The registry EVIDENCES that a verifier digest is an officially-published NOUS
verifier template. At the logged tier it additionally EVIDENCES that the
allowlist is publicly logged and append-only: a third party runs a standard
Rekor monitor and DETECTS if NOUS ever publishes a digest it should not. This
turns the "monitors, not guards" discipline on NOUS's own authority -- NOUS
stops asking a reviewer to trust its allowlist and instead publishes that
allowlist to a public transparency log.

It does NOT prove that the verifier is correct, that the decision is correct,
or that compliance is conferred. "Proves" is reserved for Z3 cost bounds and
Farkas certificates; the registry only ever upgrades a degrade into a
confirmation -- it never gates the base `.ndec` verdict, which stands on its own
with no registry at all.

## 2. Two tiers

  signed   The registry Ed25519 signature verifies against a pinned NOUS
           registry public key. Evidences a NOUS-authored cross-version
           allowlist. Strictly weaker than logged: it reduces to trusting the
           registry signing key, with no public, append-only record.

  logged   signed AND a Rekor v2 hashedrekord inclusion proof plus checkpoint,
           over the same canonical body, verifies against pinned Sigstore log
           keys. Evidences that the allowlist is publicly logged and
           append-only.

`--strict-canonical` is satisfied by a registry confirmation ONLY at the logged
tier (`require_anchor`). A signed-tier-only registry is informational; it does
not close trusting-trust across versions, because the public-log anchor is the
property that makes the claim monitorable rather than a bare assertion.

## 3. File shape

The registry is plain sorted-keys compact JSON (the canonical-serialization
contract; not Pydantic, for the same byte-preservation reason as `.ndec`). The
canonical body is the registry minus BOTH `signature` and `rekor_anchor`; the
Ed25519 signature and the Rekor leaf digest cover exactly those bytes.

    {
      "registry_schema": 1,
      "entries": [
        {
          "template_name": "VERIFY_OFFLINE_PY_FARKAS",
          "template_sha256": "f7447c65...",
          "nous_version": "5.46.0"
        }
      ],
      "signature": { "public_key_b64": "...", "signature_b64": "..." },
      "rekor_anchor": { ... v2 inclusion proof + checkpoint ... }
    }

`rekor_anchor` is drop-when-None: a signed-tier registry omits it entirely, so
the canonical body is byte-identical before and after anchoring.

## 4. Offline verification

The installed verifier checks, fail-closed, with `cryptography` and stdlib only:

  1. Ed25519 signature over the canonical body against the pinned registry-key
     allowlist (`verifier_registry.KNOWN_REGISTRY_PUBLIC_KEYS_B64`). The default
     allowlist is empty, so without a publish ceremony every registry fails
     closed.
  2. If `rekor_anchor` is present: the Rekor v2 anchor over the same canonical
     body against pinned Sigstore log keys (`KNOWN_REKOR_V2_LOG_KEYS`, a key
     SET keyed by log origin so 2025 and successor logs are trusted
     simultaneously). This reuses `verify_rekor_v2_anchor` verbatim; no new
     Rekor crypto is introduced.
  3. Membership: the queried template sha256 is present in `entries`.

`verifier_registry.confirm_digest(registry, sha, require_anchor=True)` returns a
`RegistryConfirmation` carrying the tier and, on success, the matched template
name and NOUS version.

## 5. Using it with .ndec

    nous ndec verify decision.ndec --strict-canonical --registry registry.json

On a local canonical miss, a logged-tier registry confirmation prints

    OK   verify_offline.py confirmed via verifier-digest registry
         (VERIFY_OFFLINE_PY_FARKAS@5.29.0, tier=logged); publicly logged,
         append-only -- trusting-trust closed across versions

and the verdict footer reads `verifier: registry:logged:<name>@<version>`. The
registry is supplied out-of-band (a separately published file), not carried
inside the `.ndec`; a registry frozen inside the archive could only list what
was known at build time, which is exactly the case the local allowlist already
covers.

## 6. Publishing (operator ceremony)

`scripts/publish_verifier_registry.py` is the single producer, never shipped in
the wheel and never invoked automatically.

    # offline: serialize this install's allowlist, sign with an operator key
    python3 scripts/publish_verifier_registry.py build \
        --key operator_registry.key --output registry.json

    # accrete across versions by unioning a prior signed registry
    python3 scripts/publish_verifier_registry.py build \
        --key operator_registry.key --merge prior_registry.json \
        --output registry.json

    # deferred live step: anchor the signed registry to Rekor v2
    python3 scripts/publish_verifier_registry.py anchor registry.json \
        --signing-config rekor_signing_config.json

`build` is offline and network-free. The registry signing key is supplied by the
operator and is NEVER auto-generated (the same discipline as the attestation
trust-root; see `scripts/gen_trust_root.py`). After `build`, the operator pins
the printed registry public key into
`verifier_registry.KNOWN_REGISTRY_PUBLIC_KEYS_B64` and ships that as part of the
installed verifier. `anchor` is the live step that raises a signed registry to
the logged tier; it resolves the Rekor endpoint from the signing config rather
than hardcoding a log URL, since Sigstore rotates log shards (log2025-1 today, a
successor later).

## 7. Boundary, restated

The registry widens the surface across which deterministic evidence travels:
from a confirmation bound to one install's templates to a cross-version,
publicly logged allowlist. It does not move the honest boundary. A third party
still verifies offline, with only `cryptography` and `z3`, that a NOUS decision
behaved within its declared envelope; the registry only lets them confirm,
across NOUS versions, that the verifier which re-checks that envelope is itself
an officially-published one -- and, at the logged tier, catch NOUS if it ever
blesses one it should not.
