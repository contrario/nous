# Verifying NOUS Dossiers

Status: Public -- shipped in `nous-lang 5.5.0` and later.

A NOUS dossier is a byte-deterministic, Ed25519-signed bundle of
artefacts (source, manifest, generated Python, SMT spec) that records
the cost-cap proof of a verified soul. When a dossier is anchored
with `--anchor rekor`, the manifest canonical bytes are additionally
attested by a Sigstore Rekor transparency-log inclusion proof.

This document covers the three independent paths a third party can
use to verify a dossier they have been given.

## Three trust paths

| Path | What you need | What it verifies |
|------|---------------|------------------|
| Browser | A modern browser | Same checks as offline, but trust the API operator. Convenience only. |
| Offline | Python 3.11+ and `cryptography` >= 42 | Full cryptographic verification with no external dependency. Canonical. |
| Toolchain | `pip install nous-lang` | Full verification plus SMT cost-cap re-check. |

### Path 1: Browser convenience

Open `https://nous-lang.org/verify.html`. Drop a `manifest.json` or a
`skill_export.zip` onto the page (the verifier extracts the manifest
from the ZIP client-side via JSZip). The page POSTs the manifest to
`/api/v1/verify-dossier` and renders the structured V2 response: a
verdict banner (ACCEPT / REJECT), four status pills (SIGNATURE,
SOURCE ID, ANCHORED, REKOR ANCHOR), an evidence block, a collapsible
trust explanation, a next-steps list, and per-check diagnostics for
any failing checks.

The IDE at `https://nous-lang.org/ide.html` exposes the same component
behind the `Dossier` tab; the surface is identical in semantics, with
a more compact layout for the tab context.

### Path 2: Offline reproducible

Run the `verify_offline.py` inside the dossier directory, with the
publisher's raw Ed25519 public key in base64:
`cd <dossier> && python3 -I verify_offline.py --expect-signer BASE64`.
The standalone download is withdrawn
(`docs/adr/ADR-0009-standalone-verifier-withdrawal.md`). The script
reads `manifest.json` and `source.nous` from its current working
directory and prints a structured verdict.

<!-- __nt_v3_classes_docs_v1__ -->
The key comes from the publisher, out of band, not from the dossier:
`public_key.b64` inside it is the key the manifest carries, and any
key can sign. Without `--expect-signer` the verifier gives no PASS
(exit 2); a manifest signed by any other key exits 1 (NT-GATE-1 V3).
`-I` keeps Python from importing modules from the bundle's
directory, which its sender controls: without it, a module planted
there runs in place of the standard library's.

The dossier ships the verifier that matches how it was emitted:

- Rekor-anchored (`--anchor rekor`, NOUS v5.3.0 and later): strict,
  requires a valid `transparency_log` block and refuses a dossier
  without one.
- Rekor v2-anchored (`--anchor rekor_v2`): strict by default; add
  `--allow-unanchored` to accept a dossier with no `transparency_log`
  block, on the Ed25519 author signature and the source sha alone.
  It carries no cost-cap check.
- Unanchored (`--anchor none`): checks the Ed25519 author signature
  and the source sha, plus the legs the dossier carries. It takes no
  option other than `--expect-signer`.

The verifier is the text `build_dossier` writes: one of the templates
in `dossier.py`, or, for `rekor_v2`, the text
`offline_verifier_builder.build_offline_verifier_v2` assembles. This
is the canonical trust path. Exit codes: 0 PASS, 1 INTEGRITY (a
signature, a digest or a proof check fails), 2 ENVIRONMENT (no key, a
malformed or unexpected argument, a missing dependency), 3 OUTSIDE
(the manifest is authentic under the expected key and its solver
verdict is not `proven`). The last line of stdout names the class,
and the output ends with a NOT CLAIMED list. Lines printed before the
last checks are progress, not the verdict: the CLASS line is. An
ENVIRONMENT exit means the run stopped before its remaining checks: a
dossier whose coverage proof needs z3 exits 2 on a host without z3
before the checks that follow it run; rerun where z3 is present.

Coverage-bearing dossiers (emitted with `nous verify --smt --coverage-threshold ...` then `nous dossier ... --anchor none`) ship a different embedded verifier. When a Farkas certificate is present the dossier carries `VERIFY_OFFLINE_PY_FARKAS`, whose coverage trust path is standard-library rational arithmetic with no solver; when only `coverage.smt2` is present it carries `VERIFY_OFFLINE_PY_COVERAGE`, which re-checks unsat with z3 if available. Both add an O(1) sha256 file-provenance gate before any proof check, and both require only the `cryptography` library for the signature. See `docs/COVERAGE_PROOF.md`. <!-- __s116_verify_dossier_coverage_v1__ -->

### Path 3: Toolchain (full)

For organizations that already have NOUS installed. Install the
version the manifest records, then run in the dossier directory:

```
pip install nous-lang==<nous_version>
nous dossier source.nous --manifest manifest.json --prices pricing.toml --output <dir>
nous verify-cost cost.farkas.json --manifest manifest.json
```

`nous dossier` checks the manifest's Ed25519 signature under the key
the manifest carries and the source sha, re-derives the SMT spec from
source, and refuses on any mismatch; it writes a new dossier
directory; `--anchor` defaults to none. `nous verify-cost` re-checks
the cost-cap Farkas certificate by exact arithmetic and, with
`--manifest`, that it is the certificate the manifest names (a sha
match only; the manifest signature is checked by `verify_offline.py`
and by `nous dossier`). Who holds the signing key is established out
of band.

## V2 API surface (since v5.5.0)

The `POST /api/v1/verify-dossier` endpoint accepts an optional
`policy` request field. When `policy` is present, the endpoint
returns a structured V2 response designed for auditors and automated
verification pipelines. When `policy` is omitted, the endpoint
returns the legacy V1 response shape byte-identically for backward
compatibility with existing clients.

### Request

```json
{
  "manifest_json": "<the manifest.json contents as a string>",
  "policy": {
    "require_anchor": true,
    "max_anchor_age_seconds": null,
    "require_pubkey_in_allowlist": true
  }
}
```

The `policy` field is optional. When absent, the V1 response is
returned. When present, all fields default if omitted:

| Field | Default | Meaning |
|-------|---------|---------|
| `require_anchor` | `true` | Reject the dossier if it lacks a `transparency_log` block. Set to `false` for diagnostic UX (verify.html uses this). |
| `max_anchor_age_seconds` | `null` | If set, reject the dossier when the Rekor anchor is older than this many seconds. Useful for time-bounded compliance contexts. |
| `require_pubkey_in_allowlist` | `true` | Reject the dossier if the Rekor signing key is not in the pinned Sigstore allowlist. |

### Response

```json
{
  "spec_version": "verify-dossier/v2",
  "verdict": "ACCEPT",
  "trust_level": "rekor_anchored",
  "policy_applied": {
    "require_anchor": true,
    "max_anchor_age_seconds": null,
    "require_pubkey_in_allowlist": true
  },
  "checks": {
    "manifest_well_formed": {"ok": true, "errors": []},
    "manifest_signature_ed25519": {"ok": true, "errors": []},
    "source_sha256_field_well_formed": {"ok": true, "errors": []},
    "transparency_log_present": {"ok": true, "errors": []},
    "rekor_public_key_in_allowlist": {"ok": true, "errors": []},
    "rekor_signed_entry_timestamp": {"ok": true, "errors": []},
    "rekor_leaf_inclusion": {"ok": true, "errors": []},
    "rekor_anchor_age": {"ok": true, "errors": []}
  },
  "evidence": {
    "manifest_sha256": "<hex>",
    "manifest_canonical_bytes_sha256": "<hex>",
    "public_key_b64": "<base64>",
    "rekor_log_index": 1554376230,
    "rekor_integrated_at": "2026-05-16T20:08:25Z",
    "rekor_log_id": "<hex>",
    "rekor_anchor_age_seconds": 63134
  },
  "human_readable": {
    "verdict_summary": "Dossier accepted: Ed25519 signature verified, Rekor anchor valid.",
    "trust_explanation": "...",
    "next_steps": []
  }
}
```

### Field semantics

`verdict` is a binary ACCEPT or REJECT, computed deterministically
from the applied policy and the check results. ACCEPT means every
check that policy required to pass did pass. REJECT means at least
one required check failed.

`trust_level` upgrades or downgrades based on which checks passed:

| `trust_level` | Meaning |
|---------------|---------|
| `rekor_anchored` | All four Rekor checks passed: dossier has an anchor, the SET signature verifies under a pinned key, the leaf body matches, and the anchor age is within policy. Highest trust. |
| `ed25519_only` | Author signature verified but no public anchor is present (or anchor was downgraded). Useful for legacy or development dossiers. |
| `none` | Author signature is invalid or manifest could not be parsed. Do not trust. |

`policy_applied` echoes back the policy with all defaults filled in.
A verifier can persist this alongside the verdict to record what
policy produced the decision.

`checks` is the per-check evidence. Each check has an `ok` field
with one of four states:

| `ok` | Meaning |
|------|---------|
| `true` | Check ran and passed. |
| `false` | Check ran and failed. The `errors` array contains the failure cause. |
| `"skipped_unanchored"` | Check was skipped because the dossier has no `transparency_log` block. Only applies to the four Rekor checks. |
| `"skipped_no_policy"` | Check was skipped because the policy does not require it. Currently only applies to `rekor_anchor_age` when `max_anchor_age_seconds` is `null`. |

The discriminated `ok` field is what makes the V2 surface auditor-
grade: a check that did not run is distinguishable from a check that
ran and failed, and both are distinguishable from a check that ran
and passed. Boolean response shapes (V1) collapse the first two
cases, which a strict auditor cannot accept.

`evidence` is the raw facts: hashes, log indices, signing keys.
Useful for cross-referencing against an external source (e.g.
clicking through to the Sigstore Rekor entry page).

`human_readable` is a short prose summary intended for UI display.
The `verdict_summary` is one sentence. The `trust_explanation` is
one or two sentences explaining why the trust_level is what it is.
The `next_steps` array is empty on ACCEPT; on REJECT it contains
suggested remediation actions.

### Verdict logic

```
if not checks.manifest_well_formed.ok:
    verdict = REJECT
elif not checks.manifest_signature_ed25519.ok:
    verdict = REJECT
elif not checks.source_sha256_field_well_formed.ok:
    verdict = REJECT
elif policy.require_anchor and not checks.transparency_log_present.ok:
    verdict = REJECT
elif checks.transparency_log_present.ok:
    if (not checks.rekor_public_key_in_allowlist.ok
            or not checks.rekor_signed_entry_timestamp.ok
            or not checks.rekor_leaf_inclusion.ok):
        verdict = REJECT
    elif (policy.max_anchor_age_seconds is not None
            and not checks.rekor_anchor_age.ok):
        verdict = REJECT
    else:
        verdict = ACCEPT
else:
    verdict = ACCEPT
```

### V1 backward compatibility

When the request body omits `policy`, the endpoint returns the V1
response shape exactly as in v5.4.0:

```json
{
  "signature_ok": false,
  "public_key_b64": null,
  "rekor_inclusion_ok": null,
  "rekor_set_ok": null,
  "rekor_log_index": null,
  "rekor_integrated_at": null,
  "manifest_sha256": "<hex>",
  "errors": ["..."]
}
```

This is byte-identical to v5.4.0 behavior. Existing clients do not
need to change.

## Trust model

`POST /v1/verify-dossier` is not in the trust path. It runs the same
checks as `verify_offline.py` but inside the NOUS API: if you do not
trust the API operator, the response means nothing. The offline
verifier is the only path where the verification computation happens
entirely on the verifier's machine, with no network round-trip and
no dependency on the issuer's infrastructure. The browser page is,
accordingly, framed as a quick check, not as audit evidence.

The V2 surface improves auditor UX over V1 in three concrete ways:

1. The `verdict` field is a deterministic function of the policy and
   the checks. An auditor records both `policy_applied` and
   `verdict`; the decision is reproducible from those two values
   plus the original manifest.
2. The `evidence` block is raw enough to be re-verified offline by
   replaying the checks against the dossier without re-calling the
   endpoint. The endpoint is a convenience, not a fact source.
3. The discriminated `ok` field on each check lets an auditor write
   policies that distinguish "this dossier failed verification" from
   "this dossier was not subjected to this check," which V1 conflates
   into `null`.

The endpoint is rate-limited (30 requests per minute per IP) and the
request body is capped at 256 KiB. Real-world dossiers are 2-10 KiB;
the cap exists to prevent abuse, not to constrain legitimate use.

## Failure modes

| Symptom | Likely cause |
|---------|--------------|
| `verdict=REJECT`, `human_readable.verdict_summary` mentions "manifest could not be parsed" | The submitted text is not valid JSON, or is missing required manifest fields. |
| `verdict=REJECT`, `checks.manifest_signature_ed25519.ok=false`, `errors` contains `ed25519_signature_invalid` | Manifest fields were edited after signing, or signature bytes corrupted. Trust level downgrades to `none`. |
| `verdict=REJECT`, `checks.rekor_signed_entry_timestamp.ok=false` | Rekor key rotated since the dossier was anchored; pinned allowlist is stale. Update verifier to latest. |
| `verdict=REJECT`, `checks.rekor_leaf_inclusion.ok=false`, `checks.rekor_signed_entry_timestamp.ok=true` | The Rekor entry is valid but does not match the manifest in hand. The manifest has been substituted for a different one anchored under the same submitter ephemeral key. |
| `verdict=REJECT`, all four `rekor_*` checks are `"skipped_unanchored"`, `policy.require_anchor=true` | No `transparency_log` block in the manifest. Either accept with `policy.require_anchor=false` (downgrades trust to `ed25519_only`) or re-issue with `nous dossier --anchor rekor`. |
| `verdict=ACCEPT`, `trust_level=ed25519_only` | Dossier has a valid author signature but no public anchor. Audit-acceptable only if your policy allows unanchored dossiers. |
| `verdict=REJECT`, `checks.rekor_anchor_age.ok=false`, `evidence.rekor_anchor_age_seconds` exceeds `policy.max_anchor_age_seconds` | The Rekor anchor is older than your policy allows. Either widen the policy or re-issue. |

## See also

- `docs/REKOR_ANCHOR.md` -- the anchoring side: how a dossier acquires
  its `transparency_log` block, Path-beta dual signing rationale,
  Sigstore issue #851.
- `docs/EU_AI_ACT_COMPLIANCE.md` -- where in Annex IV this surface
  lands.
- `docs/COVERAGE_PROOF.md` -- the policy-coverage obligation and the
  stdlib-checkable Farkas certificate; the coverage/Farkas offline
  verifiers shipped in coverage-bearing dossiers.
- Source: `nous_api_server.py::verify_dossier_endpoint`,
  `rekor_anchor.py::verify_rekor_anchor_offline_detail`,
  `dossier.py` (the `VERIFY_OFFLINE_PY*` templates),
  `offline_verifier_builder.py::build_offline_verifier_v2`.

<!-- __session82_docs_verify_dossier_v2_v1__ -->
