# Santander mech-gov DecisionResult evidence adapter

A consume-only NOUS adapter that turns a Santander mech-gov `DecisionResult`
into a signed, offline-verifiable NOUS evidence dossier. It reads a
`DecisionResult.to_dict()` JSONL line by key, never imports the mech-gov
package, and emits a signed adapter manifest plus a decision-structural payload,
with an optional Rekor v2 anchor of the decision's entropy nonce.

Status: opt-in and DARK. The adapter writes nothing unless
`NOUS_SANTANDER_ADAPTER` is set. Enabling `emit_dossier_to_dir` writes only
`manifest.json`, `payload.json`, and a self-contained `verify_offline.py`.

Upstream pin (pinned, not coupled): `github.com/SantanderAI/mech-gov-framework`,
release v0.1.0 (2026-06-17), Apache-2.0, single-commit main
`bdf0fe6a6237c879fbd7a0f6bf7b54b54418965e`, Python 3.10+. The section-2.1
`DecisionResult` schema is 20 fields. The adapter parses by key and refuses on a
missing key, so it tolerates schema drift; it pins the read for the record and
does not couple to it.

## Honest boundary

This adapter adds no new cryptography and no new claim class. It composes over
shipped NOUS primitives: the Ed25519 manifest signer, the envelope ledger commit
surface, and the Rekor v2 anchor and verify path.

- Evidences, never proves. A verified dossier evidences that a `DecisionResult`
  with this structure and this entropy nonce was produced, and, when anchored,
  that the exact nonce is publicly logged and log-ordered. It does not prove the
  decision correct, fair, unbiased, single-shot, or non-gamed. "Proves" is
  reserved for Z3 cost bounds and Farkas certificates.
- Monitor, not guard, on this path. The adapter consumes the record after the
  fact. It enforces nothing on the mech-gov and blocks no decision.
- Hashes, not raw. Free-text and metadata fields are carried as sha256 only. No
  special-category data enters the signed payload. Raw values live in the
  out-of-band auditor pack, sha-gated by the carried commitments.
- Name-to-key is operator-asserted. NOUS runs no CA and certifies no identity.

Three flags travel with every surface:

1. No trusted time. The Rekor v2 anchor evidences public append-only logging and
   log-ordering of the nonce. It does not establish a trusted wall-clock time:
   this path captures no RFC 3161 timestamp token. The only time in the dossier
   is `timestamp_utc`, which is NOUS-self-asserted and untrusted. A trusted time
   would require a separate TSA-capture increment, which is out of scope here.
2. Interop, not production. The adapter evidences synthetic and benchmark
   records against the real external framework. There is no live mech-gov
   deployment behind it. The honest value is demonstrating that the evidence
   bridge works against a real external framework (interop capability). "Secures
   Santander decisions in production" would be an overclaim.
3. Evidences, not proves (restated, because it is the load-bearing claim).

## What it consumes

Input is one `DecisionResult.to_dict()` JSONL line. `parse_decision_jsonl`
refuses (typed, zero output) on malformed JSON, a non-object record, or any
missing section-2.1 key. The mech-gov package is never imported; parsing is
purely by key.

## The projection

`project_decision` maps the 20-field record to a canonical decision-structural
payload. Each field has exactly one treatment.

| field | treatment | note |
|-------|-----------|------|
| case_id | value (clear) | synthetic structured id (e.g. credit_approval-Baseline-0042); a deployment whose case_id encodes customer or case identity MUST reclassify it to hash |
| regime | value (clear) | |
| decision | value (clear) | |
| gates_triggered | value (clear) | |
| cefl_candidates | value, drop-when-None | regime-specific |
| cefl_candidate_scores | value, drop-when-None | regime-specific |
| i6q_passed | value, drop-when-None | regime-specific |
| modification_proposed | value, drop-when-None | regime-specific |
| modification_accepted | value, drop-when-None | regime-specific |
| drift_budget_remaining | value, drop-when-None | regime-specific |
| rationale | hash (sha256) | free text |
| pro_arguments | hash (sha256) | list |
| con_arguments | hash (sha256) | list |
| deferral_text | hash, drop-when-None | free text |
| conditions_text | hash, drop-when-None | free text |
| llm_raw_response | hash (sha256) | raw model output |
| metadata | remainder hash | E3 subfields lifted to the leg; the rest, including PII-derived counts, sha256'd |
| entropy_nonce | entropy leg | E3 commit-reveal; see below |
| processing_time_ms | drop | wall-clock telemetry; covered by upstream_digest |
| tokens_used | drop | usage telemetry; covered by upstream_digest |

Value hash commitments are keyed `<field>_sha256`. drop-when-None fields are
absent from the payload when None, so unrelated dossiers stay byte-identical.
The metadata E3 subfields `e3_nonce_hash` and `e3_verified` are lifted into the
entropy leg in clear; every other metadata key (including `privacy_residual_pii`
and other PII-derived counts) is folded into a single `metadata_sha256`
remainder commitment. No metadata plaintext enters the payload.

## The two digests

The signed manifest binds two independent digests:

- `upstream_digest`: sha256 of the exact `to_dict()` JSONL line as consumed. It
  covers the whole record, including the dropped telemetry fields, so nothing is
  silently discarded from the provenance leg.
- `projection_digest`: sha256 of the canonical projected payload. It is the
  offline-verifiable identity of `payload.json`.

## The entropy leg and the Rekor anchor

When the record carries an `entropy_nonce`, the adapter builds an entropy leg
binding the revealed nonce N, the upstream commitment H(N) (`e3_nonce_hash`),
and the upstream reveal flag `e3_verified`. `build_entropy_leg` refuses if
sha256(N) does not equal the carried `e3_nonce_hash` (E3 commit-reveal). The leg
evidences that N existed and was committed. It proves nothing about the decision
being single-shot or unbiased.

The optional Rekor v2 anchor logs N to the Sigstore Rekor v2 transparency log
(`log2025-1.rekor.sigstore.dev`) via the shipped `anchor_manifest_to_rekor_v2`
primitive. The anchored bytes are N in ASCII, so the leaf digest equals
sha256(N) equals the upstream `e3_nonce_hash`: the anchor binds the same nonce
the E3 commit-reveal uses. This is the honest strength -- not time, but a
public, ordered, independently checkable commitment to the exact nonce.

Temporal claim, exactly: the anchor evidences that the nonce is publicly logged
and log-ordered. It does not establish a trusted time (flag 1). The observation
time is `timestamp_utc`, self-asserted and untrusted.

## Producer tag and signing key

The dossier root commitment rides the shipped envelope ledger under a
producer-side domain tag `nous/santander-decision/v1|`, following the closure
grammar `nous/<name>/v1|`. The tag is a placeholder until the first
persistent-key signature ships, at which point it is frozen (permanent once
signed).

The adapter is signed with a dedicated persistent Ed25519 key at
`~/.local/share/nous/keys/santander-adapter.key` (XDG-scoped, distinct producer
identity). The key does not exist until the genesis ceremony generates it. The
adapter verification key is published with the genesis dossier. No anchored
adapter dossier exists until the genesis ceremony produces the first one; this
document describes the capability, not an existing artifact.

## Dossier layout

An emitted dossier directory contains:

- `manifest.json`: the signed adapter manifest (canonical body signed with
  Ed25519; the signature block and, when present, the `transparency_log` anchor
  block are excluded from the signed body).
- `payload.json`: the canonical decision-structural payload.
- `verify_offline.py`: a self-contained verifier requiring only the
  `cryptography` library.

## Offline verification

`verify_offline.py` checks, fail-closed, in order:

1. Ed25519 signature over the canonical manifest body bytes.
2. `source_kind == "santander/mech-gov/decision"` (refuse any other kind).
3. `projection_digest == sha256(payload.json)`.
4. Entropy leg, when present: sha256(nonce) == nonce_hash (E3 commit-reveal).
5. Rekor v2 anchor, when a `transparency_log` block is present: leaf digest ==
   sha256(nonce) == e3_nonce_hash; leaf ECDSA over the nonce; C2SP checkpoint
   signed by the pinned Rekor v2 log key; RFC 6962 inclusion under the cosigned
   root.

Exit codes: 0 verified, 1 FAIL (tamper, wrong kind, broken E3, bad anchor), 2
environment. The in-package `verify_santander_dossier` returns a total verdict
with per-leg booleans and never raises; `rekor_ok` is vacuously true when no
anchor is carried (drop-when-None).

## Auditor pack contract

The dossier carries no raw free text and no metadata plaintext; the clear
fields are decision-structural (subject to the case_id deployment note in the
projection table above). Raw sensitive values are delivered out-of-band as the
auditor pack, sha-gated by the carried commitments. An auditor recomputes each
`<field>_sha256` and `metadata_sha256` over the raw pack and matches them
against the signed manifest. Name-to-key resolution for the signing key is the
auditor's out-of-band step; NOUS asserts only that the holder of the pinned key
signed.

## Scope and non-goals

The adapter does not import mech-gov, does not run the mech-gov, does not
adjudicate a decision, and does not establish trusted time on this path. It
evidences that a decision record was produced and, when anchored, that its
entropy nonce is publicly logged and ordered. It is a monitor, not a guard.
