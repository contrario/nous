# Rekor Anchoring (v5.3.0+)

> Status: **Public** -- shipped in `nous-lang 5.3.0` and later.
> Scope: optional `--anchor rekor` flag on `nous dossier-spec` and `nous skill-export`, and `anchor=rekor` field on the corresponding `POST /v1/dossier-spec` and `POST /v1/skill/export` HTTP endpoints.
> Reading order: this document, then `EU_AI_ACT_COMPLIANCE.md` for Article 14 context, then `SKILL_EXPORT.md` for the customer-facing flow.

NOUS v5.0.0 introduced Ed25519-signed dossiers: every verified program emits a manifest whose cryptographic signature is verifiable offline by anyone holding the signer's public key. That gives **inner-circle auditability** -- a signature chain that proves authorship and tamper-evidence between a counterparty and the signer.

It does NOT give **third-party-auditable durability**. If the signer's machine is later compromised and the private key is exfiltrated, a malicious party can mint backdated signed manifests indistinguishable from the originals. The signer can also unilaterally revoke or rotate keys without external notice. Article 14 of the EU AI Act calls for governance traces that survive operator-side compromise; an isolated Ed25519 signature does not meet that bar.

v5.3.0 closes the gap by anchoring every dossier manifest into the public Sigstore Rekor transparency log. Each anchored dossier carries an **inclusion proof** from Rekor: a cryptographic statement, signed by a public Rekor instance under a key trusted by the broader Sigstore ecosystem, that the manifest's canonical bytes were integrated into a public, immutable, append-only Merkle tree at a specific UTC moment. The Merkle tree's checkpoint is itself published; anyone, anywhere, at any future time, can verify offline that the manifest existed at that moment under that tree state.

This document describes how that works, why it required a per-submission dual-signing pivot, and how an external auditor can verify a Rekor-anchored dossier with only `cryptography` and `z3-solver` installed (no NOUS dependency, no network access).

---

## Quick start

```bash
# Emit a Rekor-anchored dossier from a NOUS .nous file
nous dossier-spec ./my_skill --anchor rekor --output ./dossier

# Anchor a skill-export bundle to Rekor
nous skill-export ./my_skill --anchor rekor --output ./bundle.zip

# Offline verification, no NOUS install needed
cd ./dossier
python3 verify_offline.py
# VERDICT: PASS (Ed25519 manifest + Sigstore Rekor anchor via Path-beta dual signing)
```

Without the `--anchor rekor` flag, dossiers remain byte-identical to v5.2.0 output. Existing customers who do not opt in to Rekor anchoring see no change in their generated artefacts.

---

## Architecture: Path-beta dual signing

The NOUS dossier signing pipeline uses two cryptographic primitives:

1. **Ed25519** -- the long-lived manifest signature. Proves authorship of the manifest's canonical body bytes. The same primitive used since v4.17.0; key material at `~/.local/share/nous/keys/signing.key` by default, overridable via `--key PATH`.

2. **ECDSA-P-256** -- a **per-submission ephemeral keypair** generated at the moment of Rekor submission. Used only to satisfy Rekor's wire-format constraints. Discarded immediately after the submission completes; never persisted to disk.

Both primitives sign the **same canonical manifest body bytes** -- the JSON serialisation of the manifest with the `signature` and `transparency_log` blocks stripped, using the same `sort_keys=True, separators=(",", ":")` canonicalisation that NOUS has used since v4.17.0. This is the bridge: verifying the Ed25519 signature (step 1 of the embedded verifier) proves authorship; verifying the ECDSA signature on the Rekor leaf (step 6) proves the integrity of the Rekor wire payload pointing to those same bytes; verifying the Rekor SignedEntryTimestamp (step 5) proves the leaf was integrated at the claimed time. Three independent crypto checks, all over the same canonical bytes, anchored to the public Sigstore Rekor instance.

### Why dual signing, not direct Ed25519 submission?

The natural design -- submit the manifest's Ed25519 signature directly as the Rekor leaf signature -- does not work. Rekor's primary leaf format (`hashedrekord/0.0.1`) passes only a pre-computed hash to the signature verifier. EdDSA (the Ed25519 signature scheme) requires the original message bytes because the hash is computed internally during EdDSA verify. The combination is fundamentally incompatible at the protocol level.

This is documented in Sigstore issue #851 (sigstore/rekor). Any project attempting Ed25519 + hashedrekord will hit HTTP 400 from production Rekor at submission time; the error message varies depending on which validation stage trips first (`tags don't match (16 vs 3)` for ASN.1 wire mismatch, `unsupported hash algorithm: 'SHA-256' not in [SHA-512]` for hash-length mismatch, `message cannot be nil` for missing payload). NOUS v5.3.0 encountered both during development before settling on Path-beta.

Two alternatives were considered and rejected:

| Alternative | Why rejected |
|-------------|--------------|
| Switch to `rekord/0.0.1` (legacy leaf format that supports Ed25519) | Rekor v2 (current in-progress upgrade) drops `rekord`. Long-term dead end. |
| Jump to DSSE / Rekor v2 now | Early adoption risk; Python tooling for DSSE-over-Rekor-v2 is thin as of May 2026. |

Path-beta dual signing keeps NOUS on the stable `hashedrekord/0.0.1` path that is widely-used in production, while preserving Ed25519 for the manifest itself. The ephemeral ECDSA keypair is a wire-format adapter, not a key the customer ever sees or has to manage.

---

## Wire format

A Rekor-anchored manifest gains a `transparency_log` block:

```json
{
  "world_name": "...",
  "cost_cap_usd": "...",
  "...": "...",
  "signature": {
    "public_key_b64": "<Ed25519 manifest pubkey>",
    "signature_b64": "<Ed25519 signature over canonical body bytes>"
  },
  "transparency_log": {
    "provider": "sigstore-rekor",
    "rekor_public_key_pem": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----\n",
    "log_id": "<hex>",
    "log_index": <int>,
    "integrated_time": <unix-seconds>,
    "body_b64": "<base64 of the hashedrekord leaf JSON>",
    "signed_entry_timestamp_b64": "<base64 of the SET DER signature>"
  }
}
```

The `body_b64` decodes to the actual Rekor leaf, which has the post-Path-beta shape:

```json
{
  "apiVersion": "0.0.1",
  "kind": "hashedrekord",
  "spec": {
    "data": {
      "hash": {
        "algorithm": "sha256",
        "value": "<hex sha256 of canonical manifest body bytes>"
      }
    },
    "signature": {
      "content": "<base64 of ECDSA-P-256 DER signature over canonical body bytes>",
      "publicKey": {
        "content": "<base64 of PEM SubjectPublicKeyInfo of the ephemeral ECDSA-P-256 pubkey>"
      }
    }
  }
}
```

Three signatures, two trust anchors, one set of canonical bytes:

| Signature | Algorithm | Trust anchor | Proves |
|-----------|-----------|--------------|--------|
| `manifest.signature.signature_b64` | Ed25519 | Customer's published Ed25519 pubkey | Manifest authorship |
| `transparency_log.body_b64 -> spec.signature.content` | ECDSA-P-256 | The publicKey carried alongside in the leaf | The wire payload anchors the same canonical bytes the manifest signs |
| `transparency_log.signed_entry_timestamp_b64` | ECDSA-P-256 | Sigstore Rekor's published pubkey (`KNOWN_REKOR_PUBLIC_KEYS` allowlist) | Rekor's attestation that the leaf was integrated at `integrated_time` under `log_index` |

---

## Offline verification

The dossier ships `verify_offline.py` next to the manifest. It is a single-file, dependency-light Python script: `cryptography>=42` is the only requirement. The shipped verifier is structurally derived from the same logic as `rekor_anchor.verify_rekor_anchor_offline` in the NOUS source tree, but is self-contained: a third party can run it without installing NOUS.

The verifier performs six checks in order:

1. **Ed25519 signature over canonical manifest body bytes.** The `signature` and `transparency_log` blocks are stripped before recomputing the canonical form. Proves manifest authorship.
2. **`source.nous` SHA-256 matches `manifest.source_sha256`.** Proves the source archived alongside the manifest is the one that was verified.
3. **`transparency_log.provider == "sigstore-rekor"`.** Pins the trust ecosystem.
4. **`rekor_public_key_pem` is in the pinned `KNOWN_REKOR_PUBLIC_KEYS` allowlist.** This allowlist ships with the verifier and grows as Sigstore rotates keys; older keys remain so historical dossiers continue to verify.
5. **ECDSA-P-256 verify of `signed_entry_timestamp_b64`** over the canonical SET payload `{body, integratedTime, logID, logIndex}` using the Rekor public key. Proves Rekor's attestation.
6. **Rekor leaf body is `hashedrekord` and:**
   - `spec.data.hash.algorithm == "sha256"`,
   - `spec.data.hash.value == sha256(canonical manifest body bytes)`,
   - `spec.signature.publicKey.content` decodes to a PEM SubjectPublicKeyInfo parseable as an ECDSA-P-256 public key (the per-submission ephemeral submitter key),
   - `spec.signature.content` decodes to a DER ECDSA signature that verifies ECDSA-SHA256 over canonical body bytes under that leaf publicKey.

Any failure prints `FAIL: <reason>` to stderr and exits 1. Success prints `VERDICT: PASS (Ed25519 manifest + Sigstore Rekor anchor via Path-beta dual signing)` plus a summary block (world name, cost cap, verdict, solver, timestamp, log_id, log_index, integrated_time) and exits 0.

The verifier makes **zero network calls**. The Rekor SignedEntryTimestamp is a self-contained inclusion proof; verification needs only the pinned Sigstore pubkey allowlist (shipped) plus the manifest itself.

---

## Byte-identity guarantee for `anchor=none`

A common compliance concern: does adopting Rekor anchoring change the manifest format for customers who do NOT opt in? Answer: no.

When `nous dossier-spec` is invoked WITHOUT `--anchor rekor`, or when the API receives `anchor=none` (the default), the emitted manifest is **byte-identical** to v5.2.0 output for the same inputs. The `transparency_log` block is absent entirely; the manifest schema is unchanged; the embedded verifier in the dossier is the v5.2.0 non-Rekor verifier (single-purpose, Ed25519-only). This is structurally enforced by `tests/test_dossier_regression.py`, which compares manifest SHA-256 against the v5.2.0 baseline.

Only the explicit opt-in flag adds the `transparency_log` block. The default path is unchanged.

---

## First public NOUS Rekor anchor

The first NOUS payload integrated into the public Sigstore Rekor instance was submitted during NOUS Session 79 development, on 2026-05-16T20:08:25Z UTC. It is permanently retrievable:

- **log_index:** 1554376230
- **log_id:** `c0d23d6ad406973f9559f3ba2d1ca01f84147d8ffc5b8445c224f98b9591801d`
- **Manifest SHA-256:** `3e0e088e8346d939c248b777189b7f3bb95d2dc54308564cdb852fa26d876811`
- **Tree state:** size 1432473436, checkpoint `rekor.sigstore.dev - 1193050959916656506`
- **Retrieve:** `curl https://rekor.sigstore.dev/api/v1/log/entries?logIndex=1554376230`

Anyone can verify offline today, using only `cryptography` and `z3-solver`, that this hash was integrated at that moment under that tree state -- with no dependency on Hlias, no dependency on Anthropic, no dependency on any operator-controlled infrastructure beyond the laws of cryptography and the persistence of Sigstore's public log.

---

## Air-gapped operation

For environments where outbound HTTPS to `https://rekor.sigstore.dev` is unavailable (academic clusters, regulated networks, air-gapped CI runners), the `--anchor rekor` flag MUST fail rather than silently fall back. NOUS treats Rekor submission failures as a hard error:

```
$ nous dossier-spec ./my_skill --anchor rekor
RekorUnavailable: failed to reach https://rekor.sigstore.dev/api/v1/log/entries: ConnectError(timed out)
```

The dossier is NOT emitted partially. If outbound connectivity is uncertain at submission time, omit the flag; the resulting v5.2.0-equivalent dossier remains structurally complete and Article 14-compliant for inner-circle audit.

For batch operations where Rekor reachability matters, check connectivity ahead of time:

```bash
curl -fsS -o /dev/null https://rekor.sigstore.dev/api/v1/log/entries && \
  nous dossier-spec ./my_skill --anchor rekor
```

---

## Sigstore key rotation

Sigstore Rekor occasionally rotates its signing key (last rotation: 2024). The `KNOWN_REKOR_PUBLIC_KEYS` allowlist shipped with `verify_offline.py` is **additive**: each rotation adds a new PEM entry, and old entries remain so historical dossiers continue to verify. The verifier accepts a manifest as long as the `rekor_public_key_pem` field matches ANY entry in the allowlist.

NOUS releases will update the allowlist within 30 days of any announced Sigstore rotation. Customers running pinned-version NOUS installations should monitor `https://docs.sigstore.dev` for rotation announcements and upgrade their NOUS install accordingly. For maximum durability, archive the dossier alongside the specific `verify_offline.py` that shipped with it; the verifier and the allowlist are co-versioned.

---

## See also

- `EU_AI_ACT_COMPLIANCE.md` -- Article 14 governance trace context that motivates Rekor anchoring.
- `RUNTIME_CONFORMANCE.md` -- runtime conformance certificate (separate signed artifact, reuses the v2 anchor write path; one static manifest can have many anchored conformance certificates, one per run). <!-- __session99_docs_second_pass_v1__ -->
- `SKILL_EXPORT.md` -- the `nous skill-export --anchor rekor` customer flow.
- `SKILL_MD_SIDECAR.md` -- the source schema (`SKILL.md` + `nous.yaml`) that the dossier pipeline anchors.
- `COST_VERIFICATION_GUIDE.md` -- how `cost_cap` proofs interact with the dossier signing chain.
- `SMT_VERIFICATION_DESIGN.md` -- the Z3 SMT layer that the manifest claims are derived from.

<!-- __nous_aetherproof_release_530_docs_v1__ -->
