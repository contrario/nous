# Verifying NOUS Dossiers

Status: Public -- shipped in `nous-lang 5.4.0` and later.

A NOUS dossier is a byte-deterministic, Ed25519-signed bundle of
artefacts (source, manifest, generated Python, SMT spec) that records
the cost-cap proof of a verified soul. When a dossier is anchored
with `--anchor rekor`, the manifest canonical bytes are additionally
attested by a Sigstore Rekor transparency-log inclusion proof.

This document covers the three independent paths a third party can
use to verify a dossier they have been given.

## Three trust paths

| Path | What you need | What it proves |
|------|---------------|----------------|
| Browser | A modern browser | Same checks as offline, but trust the API operator. Convenience only. |
| Offline | Python 3.11+ and `cryptography` >= 42 | Full cryptographic verification with no external dependency. Canonical. |
| Toolchain | `pip install nous-lang` | Full verification plus SMT cost-cap re-check. |

### Path 1: Browser convenience

Open `https://nous-lang.org/verify`. Drop a `manifest.json` or a
`skill_export.zip` onto the page (the verifier extracts the manifest
from the ZIP client-side via JSZip). The page POSTs the manifest to
`/api/v1/verify-dossier` and renders the structured response: a
`SIGNATURE` pill (Ed25519 author check), a `REKOR SET` pill (Rekor
SignedEntryTimestamp + pinned-key allowlist), a `REKOR INCLUSION`
pill (leaf body hash + submitter signature), the `manifest_sha256`,
and -- for anchored entries -- a clickable `log_index` linking to the
live Sigstore Rekor entry page.

The IDE at `https://nous-lang.org/ide.html` exposes the same component
behind the `Dossier` tab; the surface is identical.

### Path 2: Offline reproducible

Download `https://nous-lang.org/verify_offline.py`. Place it anywhere;
the script reads `manifest.json` and `source.nous` from its current
working directory. Run:

```
cd path/to/dossier/
python3 /path/to/verify_offline.py
```

Exit codes:

- 0  PASS (all checks succeeded)
- 1  FAIL (one or more checks failed; specific failure on stderr)
- 2  Environment error (e.g. `cryptography` library missing)

The verifier is byte-identical to the `VERIFY_OFFLINE_PY_WITH_REKOR`
string embedded in `dossier.py` and emitted by `nous dossier-spec`
inside every anchored bundle. The `nous-lang.org/verify_offline.py`
asset is automatically re-synced from the live source-of-truth by the
release patcher; sha256 is verified on every apply.

Dependency: `cryptography>=42`. No NOUS install required.

### Path 3: Toolchain (full)

```
pip install nous-lang
nous dossier verify path/to/dossier/
```

Runs the offline verifier plus the SMT re-check against
`pricing/defaults.toml`. Required for organizations that need to
re-verify cost-cap admissibility, not just signature integrity.

## API reference: POST /v1/verify-dossier

Public endpoint. No authentication. Rate-limited 30 per minute per IP.
Inherits global CORS allow_origins="*".

### Request

```
POST /v1/verify-dossier
Content-Type: application/json

{
  "manifest_json": "<the full manifest.json text, including signature and optional transparency_log blocks>"
}
```

Request schema (Pydantic V2 strict; `extra` forbidden):

- `manifest_json: str` (min 1, max 262144 bytes)

### Response (always HTTP 200 for parseable requests)

```
{
  "signature_ok":        <bool>,
  "public_key_b64":      <str|null>,
  "rekor_inclusion_ok":  <bool|null>,
  "rekor_set_ok":        <bool|null>,
  "rekor_log_index":     <int|null>,
  "rekor_integrated_at": <str|null>,
  "manifest_sha256":     <str>,
  "errors":              <list[str]>
}
```

Field semantics:

- `signature_ok`: Ed25519 author signature verifies against the
  manifest claimed `signature.public_key_b64`. Proves authorship.
- `rekor_set_ok`: `pubkey_in_allowlist AND set_signature_ok`. True iff
  the Rekor SignedEntryTimestamp signature verifies AND the Rekor
  signing key is in the pinned allowlist. Proves the Rekor attestation
  was made under a trusted Sigstore instance.
- `rekor_inclusion_ok`: True iff the leaf body parses as
  `hashedrekord/0.0.1`, its sha256 matches the manifest canonical
  body bytes, AND the embedded submitter ECDSA-P-256 signature
  verifies. Proves the manifest in hand is exactly the manifest that
  was anchored.
- `rekor_log_index` and `rekor_integrated_at`: present iff a
  `transparency_log` block is in the manifest; identify the live
  Sigstore Rekor entry.
- `manifest_sha256`: sha256 of the canonical manifest body bytes (or
  sha256 of the request bytes on parse failure).
- `errors[]`: diagnostic strings prefixed by their origin
  (`parse_error: ...`, `ed25519_signature_invalid`,
  `rekor: set_signature_invalid`, etc.).

### Parse-failure behavior

The endpoint never returns HTTP 5xx on bad input. Invalid JSON,
missing signature block, malformed schema -- all return HTTP 200 with
`signature_ok=false`, the relevant `rekor_*` fields null, the
`manifest_sha256` of the input bytes, and a `parse_error: <reason>`
entry in `errors[]`. This keeps the contract simple for browser
clients.

HTTP 4xx is returned only for shape violations of the request itself:
missing `manifest_json` field, extra fields, or oversize body.

## Internal API: RekorVerifyDetail

Code that needs to distinguish between failure modes (rather than just
PASS / FAIL) can call `rekor_anchor.verify_rekor_anchor_offline_detail()`
directly. It returns a `RekorVerifyDetail` Pydantic V2 frozen model:

```
class RekorVerifyDetail(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    pubkey_in_allowlist: bool
    set_signature_ok:    bool
    inclusion_body_ok:   bool
    errors:              list[str]
```

Each boolean is evaluated independently with no early exit, so the
caller can observe which specific check failed. The legacy boolean
function `verify_rekor_anchor_offline()` is retained and refactored
to delegate; its return is the AND of the three detail booleans.
Equivalence is asserted by
`tests/test_rekor_anchor.py::TestVerifyRekorAnchorOfflineDetail::test_legacy_bool_matches_and_of_detail_fields`
across all three captured S80 fixtures.

## Trust model

The browser endpoint runs the same cryptographic computation as the
offline verifier, but the computation happens on the NOUS API server.
If you do not trust the operator, the response is meaningless. Use
`verify_offline.py` for any audit where verifier independence matters.

The offline verifier correctness depends on:

1. The `cryptography` library being installed and uncompromised.
2. The `KNOWN_REKOR_PUBLIC_KEYS` allowlist hardcoded inside
   `verify_offline.py` being the genuine Sigstore Rekor signing key.
   Sigstore publishes this key at
   `https://rekor.sigstore.dev/api/v1/log/publicKey`; compare.
3. The verifier code itself being unmodified. Compare its sha256
   against the value published with the release.

The toolchain path additionally verifies that the SMT cost-cap proof
re-checks against the current `pricing/defaults.toml`, which can
shift between releases if pricing tables update. Pin the NOUS version
to the one stamped in `manifest.nous_version` for byte-for-byte
reproducibility of the SMT result.

## Failure modes

| Symptom | Likely cause |
|---------|--------------|
| `signature_ok=false`, `ed25519_signature_invalid` in errors | Manifest fields were edited after signing, or signature bytes corrupted. |
| `rekor_set_ok=false`, no other rekor failures | Rekor key rotated since the dossier was anchored; pinned allowlist is stale. Update verifier to latest. |
| `rekor_inclusion_ok=false`, `rekor_set_ok=true` | The Rekor entry is valid but does not match the manifest in hand. The manifest has been substituted for a different one anchored under the same submitter ephemeral key. |
| `parse_error: KeyError: 'signature'` | The submitted JSON is missing the `signature` block. Not a valid NOUS manifest. |
| All three `rekor_*` are null | No `transparency_log` block in the manifest. Dossier was emitted without `--anchor rekor`. Verify via the toolchain path if anchor required. |

## See also

- `docs/REKOR_ANCHOR.md` -- the anchoring side: how a dossier acquires
  its `transparency_log` block, Path-beta dual signing rationale,
  Sigstore issue #851.
- `docs/EU_AI_ACT_COMPLIANCE.md` -- where in Annex IV this surface
  lands.
- Source: `nous_api_server.py::verify_dossier_endpoint`,
  `rekor_anchor.py::verify_rekor_anchor_offline_detail`,
  `dossier.py::VERIFY_OFFLINE_PY_WITH_REKOR`.

<!-- __session81_docs_verify_dossier_v1__ -->
