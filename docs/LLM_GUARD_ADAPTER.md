# LLM Guard scan_output evidence adapter

A consume-only NOUS evidence adapter over an LLM Guard `scan_output` result.
It ingests the framework's own scan result, projects it to a canonical
decision-structural payload, and emits a signed, offline-verifiable dossier.
It imports nothing from `llm_guard`; it parses the record by key. The adapter
mirrors the shipped Santander adapter structure with no bespoke leg: the only
per-adapter differences are the projection map, the `source_kind`, and the
producer tag. There is no entropy leg -- a scan result carries no nonce.

## Honest boundary

- NOUS evidences; it does not prove. The only "proves" legs in NOUS are Z3 cost
  bounds and Farkas certificates; neither is carried here.
- NOUS is a monitor, not a guard. This adapter records a decision; it enforces
  nothing and adjudicates nothing.
- LLM Guard output is UNSIGNED. The value NOUS adds is exactly the tamper-evident
  provenance the framework does not itself produce: an Ed25519 signature over a
  canonical projection, plus optional public logging.
- No producer-independence claim. One NOUS verifier verifies NOUS-authored
  projections; that is true by construction and is not evidence that the
  upstream producer is independent of NOUS.
- Hashes, not raw. Free-text and any potentially sensitive field is carried as a
  sha256 commitment only; the raw values belong to the out-of-band auditor pack.
- Name-to-key is operator-asserted. NOUS runs no CA and certifies no identity.

## What it consumes

A normalized `scan_output` result mapping. The adapter reads the aggregate
decision, the per-scanner results, and the digests of the prompt, the original
model output, and the sanitized output. It refuses malformed input with a typed
error.

## The projection

`project_llmguard` maps the record to a canonical payload:

- `decision`: pass or block, computed as `all(results_valid)` over the scanners.
- per-scanner entries `{name, valid, score}`, sorted by name.
- `prompt_sha256`, `original_output_sha256`, `sanitized_output_sha256`.

Free-text fields (prompt, original output, sanitized output) are carried as
sha256 commitments only, never as raw text.

## The two digests

- `upstream_digest`: sha256 of the canonical upstream record.
- `projection_digest`: sha256 of the canonical projected payload.

Both travel in the signed manifest, so an auditor re-derives each offline from
the carried bytes.

## The Rekor anchor (optional)

When anchored, the adapter logs `_canonical_bytes(payload)` -- the exact
projected payload -- to Sigstore Rekor v2. Because there is no nonce, the Rekor
leaf digest equals `projection_digest` directly. The anchor evidences that the
projected payload was publicly logged and log-ordered; it does NOT evidence
trusted time, and the anchor is a separate, explicit, irreversible ceremony,
never performed by the emit path.

## Producer tag and signing key

The producer-side envelope-ledger domain tag is `nous/llm-guard-scan/v1|`. It
was FROZEN at S221 by a local genesis persistent-key signature over
`dossier_commitment(genesis_manifest) = sha256(tag || public_body)`; the
dedicated key binds these exact tag bytes, so a later tag edit invalidates the
frozen signature. The dedicated key is `llm-guard-adapter.key` (Ed25519, mode
0600, under the XDG keys directory), byte-identical in discipline to
`santander-adapter.key`. The tag is not part of the signed manifest; it
participates only in the envelope commitment.

## Dossier layout

- `manifest.json` -- the signed adapter manifest (Ed25519).
- `payload.json` -- the canonical projected payload.
- `verify_offline.py` -- a self-contained offline verifier.

## Offline verification

`verify_offline.py` needs only the `cryptography` library and the standard
library. It verifies the Ed25519 manifest signature over the canonical body
bytes, re-derives `upstream_digest` and `projection_digest`, and, when a
`transparency_log` block is present, verifies the Rekor v2 anchor over the
projected payload. It trusts the issuer for nothing.

## Auditor pack contract

Raw sensitive values are never written to the shareable dossier. An auditor
requiring the underlying text receives the out-of-band auditor pack, whose bytes
are sha-gated by the commitments carried in the signed manifest.

## Scope and non-goals

- Not a registry and not a canonical-layer claim.
- Not a production identity system: operator-asserted, staging not production.
- No entropy leg: a scan result has no nonce to anchor.
- Opt-in: the emit path writes nothing unless `NOUS_LLM_GUARD_ADAPTER` is set.
