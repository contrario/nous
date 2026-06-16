# NOUS Attestation Receipt -- closing trust link 3 for the TEE case

Status: shipped v5.44.0 (S145). Mechanism present and offline-verifiable; seeded
with a TEST key only. No production / vendor pin ships until a real hardware
attestation ceremony issues one (see section 7).

This document is the reference for the attestation-receipt path that makes
`provider_token_integrity = "tee_attested"` emittable and verifiable. It builds
on the stratified-trust vocabulary frozen in `docs/STRATIFIED_TRUST_DESIGN.md`
and the witnessed-run record in `docs/WITNESSED_RUN_EVIDENCE.md`.

---

## 0. Claim boundary -- what tee_attested proves, and what it does not

PROVES: the per-event token counts in a signed trace equal the counts in a
signed inference receipt whose signing key is pinned -- via a NOUS-signed
Attestation Pinning Record (APR) -- to a specific enclave measurement (model
build) running in genuine TEE hardware.

DOES NOT PROVE: that the attested build counts tokens honestly inside the
enclave, or that the model did not misbehave. It is provenance plus count-
binding, not behavior. (Same discipline as coverage: coverage proves no gap in
the blocking net, not that the agent cannot misbehave.)

UNCHANGED BOUNDARY: first-party direct APIs (OpenAI, Anthropic) emit unsigned
usage. No scheme makes them `tee_attested`; they stay `unattested`, and that is
stated, not hidden. This is the differentiator for an Annex IV auditor: the cost
evidence declares exactly how much is cryptographically bound versus assumed.

---

## 1. Trust root (dedicated key, explicit ceremony)

A dedicated Ed25519 trust-root keypair, distinct from the long-lived dossier
signing key, anchors the chain. The key that asserts "this enclave is trusted"
is a higher-value target than a routine dossier signer, so it is isolated.

It is created by an explicit, one-time operator ceremony. It is NEVER generated
as a side effect of import, install, patch execution, or first run:

```
python3 scripts/gen_trust_root.py
```

The ceremony writes the private key (PKCS8 PEM, 0600) and public key (PEM, 0644)
under `~/.local/share/nous/keys/` and prints the public-key fingerprint
(sha256 of the raw 32-byte key) to record for pinning. It refuses to overwrite
an existing key unless `--overwrite` is passed. At-rest passphrase encryption of
the private key is a later hardening item.

The chain the offline verifier walks (two signature links, one published root):

```
trust-root pubkey  ->  APR (signed by trust-root)  ->  enclave_pubkey +
measurement + model_id  ->  receipt (signed by enclave key)  ->  model_id +
measurement + usage + source binding  ->  matched against the trace event
```

---

## 2. Attestation Pinning Record (APR)

A standalone signed governed artifact. The pin is EVIDENCE, not a hardcoded
config line: it records who verified the hardware attestation, when, and at what
TCB level, retaining the quote bytes for later re-audit. One APR per vendor
enclave key. For offline third-party verification the relevant APR(s) travel
with the dossier bundle.

Canonical body: plain sorted-keys compact JSON, drop-when-None, signature
excluded (`json.dumps(sort_keys=True, separators=(",",":"))`). Not JCS.

| Field | Meaning |
|-------|---------|
| apr_schema_version | integer, currently 1 |
| scheme | Literal["pinned_tee_key_v1"] (append-only discriminator) |
| enclave_key_id | stable id; the verifier index key |
| enclave_pubkey | base64; the key receipts are verified against |
| pubkey_alg | Literal["ed25519","ecdsa_p256"] (v1 verifies ed25519; ecdsa reserved) |
| measurement | hex; pinned build identity (compose-hash / PCR / image hash) |
| vendor | recognized S145 set: phala, marlin, near, test |
| model_id | the model build this pin authorizes |
| tcb_level | TCB / firmware level checked at pin time |
| quote_sha256 | optional; sha256 of the retained quote (audit-only) |
| verified_by | who ran the pin ceremony |
| verified_at | RFC3339 UTC |
| is_test | true for non-production pins |
| signature | Ed25519 over the canonical body by the trust-root key |

`measurement` is normalized to lowercase hex (a leading `0x` is stripped) so a
receipt and its APR compare equal regardless of input casing or prefix.

---

## 3. Inference receipt (per llm_call event)

Token counts in a NOUS trace are per-event (`TraceEvent.input_tokens` /
`output_tokens`). A receipt therefore binds at the llm_call event granularity,
correlated to the trace by `event_index`. Receipts live on the trace as a new
optional field `inference_receipts: Optional[list[InferenceReceipt]]`, dropped
when None, so a trace without receipts is byte-identical to a pre-S145 trace.

| Field | Meaning |
|-------|---------|
| receipt_schema_version | integer, currently 1 |
| scheme | Literal["pinned_tee_key_v1"] (append-only) |
| enclave_key_id | resolves against the supplied APR set |
| event_index | correlates to TraceEnvelope.events[event_index] |
| model_id | must equal the APR model_id |
| measurement | hex; must equal the APR measurement |
| usage_input_tokens | the value inside the signed payload |
| usage_output_tokens | the value inside the signed payload |
| source_sha256 | binds the receipt to THIS trace (replay resistance) |
| signature | base64; enclave-key signature over signed_payload_bytes() |
| quote | optional base64 vendor quote (audit-only, drop-when-None) |

The exact bytes the enclave key signs (`signed_payload_bytes`) for
`pinned_tee_key_v1` are the canonical compact JSON of:

```
{scheme, enclave_key_id, event_index, model_id, measurement,
 source_sha256, usage_input_tokens, usage_output_tokens}
```

A vendor whose TEE signs different bytes (for example Phala signs the HTTP
response) requires a future `scheme` (for example `phala_response_sig_v1`) that
defines its own signed-payload reconstruction. v1 defines the mechanism and is
seeded with a NOUS-controlled test signer; it does not claim vendor wire-
compatibility. `receipt.scheme == APR.scheme` is enforced (no cross-scheme).

---

## 4. Verify rule (zero-trust, fail-closed, cryptography-only)

Inputs: the trace, the set of APRs, the pinned trust-root public key. For
`tee_attested` to hold, ALL must pass; ANY failure refuses the claim (never a
silent downgrade):

1. every APR signature verifies against the trust-root public key.
2. inference_receipts present and non-empty.
3. for each token-bearing llm_call event (input or output tokens > 0): exactly
   one receipt with matching event_index (uncovered, duplicate, or stray
   receipt -> refuse). This bijection defeats both omission and injection.
4. each receipt.enclave_key_id resolves to exactly one APR.
5. receipt.scheme == APR.scheme == "pinned_tee_key_v1".
6. receipt.measurement == APR.measurement and receipt.model_id == APR.model_id.
7. receipt.source_sha256 == trace.source_sha256 (foreign / replayed receipt ->
   refuse).
8. re-derive signed_payload from the receipt fields; verify receipt.signature
   against APR.enclave_pubkey (ed25519; ecdsa_p256 refused as not-yet-supported).
9. receipt.usage_*_tokens == events[event_index].*_tokens (a validly-signed
   receipt that under-reports tokens is caught here).
10. strict mode (`--require-attestation`): refuse if any resolved APR.is_test.

The verifier re-derives every bound quantity itself; it never trusts a producer
"verified" flag.

---

## 5. CLI

```
nous conformance verify <trace.json> \
  --manifest <m.json> --prices <p.toml> --source <s.nous> \
  --apr <apr1.json> [--apr <apr2.json> ...] \
  --attest-root <trust_root.pub> \
  --require-attestation
```

- `--apr` (repeatable): a signed APR JSON. Required to verify a tee_attested
  claim; without it a tee_attested trace is refused as a precondition error.
- `--attest-root`: the pinned trust-root public key (PEM).
- `--require-attestation`: FAIL the verdict unless the trace is tee_attested AND
  the receipt verifies AND no resolved pin is a test pin.

A trace that does not claim tee_attested is unaffected by these flags (it stays
on the existing envelope / witnessed-run path).

---

## 6. Honest boundary

- First-party unsigned-usage APIs cannot produce a receipt; they remain
  `unattested`. The docs and the artifact both say so.
- A TEE receipt proves provenance and count-binding, not internal honesty of the
  attested build; the residual trust is named, not hidden.
- Closing link 3 for the TEE case does not close it for non-attested providers.

---

## 7. S145 status (safety gate)

- The mechanism, the offline verifier, the fail-closed wiring, 19 tests, and
  this documentation ship in v5.44.0.
- Only a TEST enclave key is exercised (APR.is_test=true, vendor="test").
- No production pin, no Phala / Marlin / NEAR APR, and no claim of vendor
  support ships until a real hardware attestation ceremony against a live
  endpoint issues a real APR under a vendor-specific scheme.
- `--require-attestation` strict mode refuses test pins, so production gating
  cannot pass on the test seed.

Result: `tee_attested` is mechanically emittable and offline-verifiable now;
production-meaningful only after a genuine ceremony. The honest boundary moved
from prose an auditor takes on faith into a machine-checkable, signature-bound
field.
