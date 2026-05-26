<!-- __session98_runtime_conformance_doc_v1__ -->
# Runtime Conformance

**Status:** shipped v5.13.0 (26 May 2026); `nous conformance certify` CLI
verdict-print fixed in v5.13.1. First anchored certificate verified
end-to-end against the live Sigstore Rekor v2 log at log_index 4653352.

---

## What this is

The SMT cost proof (see `docs/SMT_VERIFICATION_DESIGN.md`) proves a property
of every possible run: the program **cannot** exceed its declared cost
envelope. It says nothing about any particular run that actually happened.

The runtime conformance certificate closes that gap. Given a signed execution
trace, `nous conformance certify` re-derives the proof bounds from the signed
source and pricing, recomputes the realized cost from the trace under those
exact rates, and emits a standalone Ed25519-signed `conformance.json` recording
whether that specific run stayed inside the envelope the static proof assumed.

The static proof is about all runs. The certificate is about one run. Together
they bridge probabilistic execution and deterministic evidence: the runtime is
probabilistic, the evidence is signed, byte-deterministic, and offline-checkable.

---

## The six obligations

`verify_conformance` computes six independent booleans; the overall verdict
(`conformant`) is their conjunction, so an auditor sees exactly which one broke.

1. **binding** -- the re-derived spec and supplied pricing match the manifest's
   signed source/spec/pricing hashes, and the trace claims those same hashes.
2. **surface** -- every soul and gated action in the trace was declared by the
   proof (an undeclared soul raises a precondition error, not a soft pass).
3. **assumption_discharge** -- per-event token counts are within each soul's
   declared bounds; per-soul call count is within max_ticks; the max observed
   tick is below max_ticks.
4. **bound_transfer** -- the realized total, recomputed in Decimal under the
   proof's own rates, is at or below the cost cap.
5. **authorization** -- every gated-action event carries a valid approver
   attestation bound to that exact event (vacuously true when no gated actions
   are declared; full wiring is future work).
6. **trace_signature** -- the trace's own Ed25519 signature verifies.

Structural impossibilities -- a soul the proof never declared, an unknown event
kind, a priced tool_call the cost MVP cannot model -- raise a typed precondition
error rather than returning a verdict. This is the refuse-over-guess axiom: the
verifier reports a boolean for every evaluable obligation and refuses only when
no verdict is possible.

The bounds are always re-derived from the signed `smt_spec_sha256`, never read
from any unsigned block. An advisory `proof_assumptions` sibling may accompany a
manifest, but it is tamperable and is never trusted for verification.

---

## Using it

```
nous conformance certify <trace.json> \
  --manifest <manifest.json> \
  --prices <pricing.toml> \
  --source <source.nous> \
  --out <conformance.json> \
  [--key-path <signing.key>] \
  [--issued-utc <ISO8601>] \
  [--anchor rekor_v2]
```

The command re-derives the spec from the signed source and pricing, runs the
six checks, builds the certificate, signs it with a persistent Ed25519 key
(default `~/.local/share/nous/keys/signing.key`), and writes
`conformance.json`. A non-conformant run is still a legitimate signed result:
the certificate records `conformant: false` with the failing obligations in its
`errors` field, and the command exits 0 (a produced, signed verdict). Exit 2 is
reserved for precondition errors (structurally unusable inputs).

`nous conformance verify` runs the same checks and prints the six booleans
without emitting a certificate, for a quick interactive check.

---

## Why a standalone certificate

The certificate is deliberately a separate artifact, not a block fused into the
dossier manifest. It references the manifest by the manifest's three signed
hashes (source, spec, pricing) and the trace by the SHA-256 of the trace's
canonical body. This mirrors the SCITT architecture's separation of a Signed
Statement from the artifacts it describes, and it preserves a one-to-many
relationship: one static proof can have many conformance certificates, one per
run. It also keeps the manifest byte-identical, so its already-shipped offline
verifier and any stored manifests are unaffected.

---

## Anchoring

With `--anchor rekor_v2` the certificate's own canonical body bytes are
submitted to the tile-backed Sigstore Rekor v2 log, and the returned inclusion
proof is stapled into the certificate as a `transparency_log` sibling. The
sibling lives outside the signed body (the SCITT protected/unprotected split),
so the author signature stays valid whether or not the certificate is later
anchored, and the anchor is never computed over bytes that contain itself. The
anchor reuses the same artifact-agnostic Rekor v2 write path and read-path
verifier the dossier uses; no new cryptography is introduced.

---

## Offline verification

A standalone `verify_conformance_offline.py` ships alongside the certificate. It
runs with `cryptography` plus the standard library only -- no NOUS install. It
checks the certificate's Ed25519 signature, the certificate-to-trace and
certificate-to-manifest bindings, the trace's own Ed25519 signature, the
internal consistency of the recorded verdict, and -- when the certificate is
anchored -- the full Rekor v2 inclusion proof over the certificate body.

**Scope, stated honestly.** The offline verifier proves the signed verdict is
authentic and bound to these exact artifacts. It does **not** re-derive the SMT
bounds offline; that requires the toolchain and is the online
`nous conformance verify` path. The offline guarantee is the SCITT
signed-statement guarantee: the issuer's signed claim, verifiably about these
artifacts and untampered, with a transparency-log inclusion proof when anchored.

---

## Honest limitations

- The certificate proves the **trace** conforms, not that the trace faithfully
  records reality. Emit-from-inside-the-runtime trace generation (future work)
  is the mitigation; full faithfulness against a malicious runtime needs a TEE
  or hardware attestation.
- The cost MVP models llm_call token cost only. Priced tool calls and
  sequence/ordering obligations (authenticate-before-access, no-send-after-read,
  per-tick call limits) are future work and are where Z3 becomes load-bearing
  for the runtime path; the cost MVP itself needs only interval checks and a
  Decimal sum.
