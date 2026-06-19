# Codegen Binding (codegen_sha256)

The fourth subject leg of a NOUS runtime trace.

## The gap it closes

A signed `TraceEnvelope` binds three subject digests: `source_sha256` (the
`.nous` source bytes), `smt_spec_sha256` (the canonical SMT spec), and
`pricing_sha256` (the active cost model). Conformance obligation #5 further
checks that each gated-action attestation is a valid Ed25519 signature over
its `(seq, action, proof envelope)`. None of these names the specific
compiled program that should have produced the trace's events. A trace can
set a genuine `source_sha256` and reference no compiled program at all: the
compiled artifact was the unbound leg.

`codegen_sha256` is that fourth leg. It binds a trace to the exact generated
Python the run harness compiles and executes.

## Definition (single source)

```
run_shas.compute_codegen_sha256(source_text) -> str
    = sha256( generate_python(parse_nous(source_text)).encode("utf-8") )
```

This is the ONE definition. The producer (the run harness) stamps it, and
the verifier (`nous conformance verify --source`) re-derives it, with the
SAME function. They cannot drift.

The digest is version-independent: the generated header carries no version
string, timestamp, or nonce, so the output is a pure, deterministic function
of the source and the codegen logic. The 57-template byte-identity
regression harness pins that logic; a codegen change that altered output
would change this digest exactly when it changes a harness baseline.

## Producer

When a run emits a trace (`nous run --emit-trace`, or `execute_program` with
`emit_trace=True`), the harness already holds `source_text` and derives the
three subject shas. It now also computes `compute_codegen_sha256(source_text)`
and passes it to the `TraceRecorder` as a keyword-only subject binding,
validated as 64-hex when present. `codegen_sha256` then rides the signed
`TraceEnvelope`.

The field is drop-when-None in both the canonical body and the persisted
dict, so every trace produced before this leg existed stays byte-identical
and continues to verify.

## Verifier (online)

`verify_conformance` takes an optional `codegen_sha256` (the re-derived
digest). `nous conformance verify --source <file.nous>` already re-derives
the SMT spec from the signed source; codegen is a pure function of that same
parsed program, so the CLI re-derives the codegen digest with the shared
helper and supplies it. The binding obligation folds in one check:

    if trace.codegen_sha256 is not None
       and codegen_sha256 is not None
       and trace.codegen_sha256 != codegen_sha256:
        binding_ok = False

A trace that declares a `codegen_sha256` the source does not re-derive fails
`binding_ok`. A trace that declares none, or a verification that supplies
none, adds no check: the leg is UNBOUND, not failed (backward-compatible).

## Honest boundary

- EVIDENCES: that a trace's gated-action events name the exact compiled
  program (a specific `generate_python` output), re-derivable from the signed
  source.
- Does NOT prove the run executed. A holder of the trace signing key can
  compute the genuine codegen digest from the public source and stamp a
  hand-authored trace that never ran the compiled recorder. Closing that
  residual requires execution attestation (a TEE or runtime witness), which
  is out of scope. NOUS is a monitor, not a guard.
- ONLINE only. Re-derivation needs the toolchain (`parse_nous` +
  `generate_python`), exactly like SMT-spec re-derivation, which the offline
  portable verifier excludes by design. The signed manifest and conformance
  certificate do not yet carry `codegen_sha256`, so an offline-checkable
  codegen leg (a signed manifest/certificate field plus a dedicated
  conformance obligation and an offline-template line) is a separate,
  later arc.

## Relationship to the sign_trace fix

This leg is only meaningful because a signed envelope now carries every
field it was constructed with. `sign_trace` previously reconstructed the
signed envelope from a hand-enumerated field list and silently dropped any
field not in that list (the S144 trust triple, S145 receipts); a new field
threaded through the recorder would have vanished on signing. `sign_trace`
now reconstructs from `TraceEnvelope.model_fields`, overriding only the
signature, so `codegen_sha256` (and every future field) survives signing.

## S156: the leg goes offline

S156 promotes `codegen_sha256` from a trace-only field to a signed
first-class leg of the Manifest and the conformance Certificate, adds a
dedicated conformance obligation `codegen_binding_ok` (decoupled from
`binding_ok`, axiom 8), and adds an independent sha-equality check to the
portable offline verifier.

- Manifest: `codegen_sha256` is stamped on the `nous verify` path and
  carried drop-when-None, so every prior signed Manifest stays
  byte-identical.
- Certificate: schema v3 -> v4 adds `codegen_sha256` and
  `codegen_binding_ok` (eight obligations at v4), schema-gated so prior
  signed Certificates stay byte-identical.
- Obligation: `codegen_binding_ok` is sha-equality across the present
  legs (trace, manifest, re-derived); vacuous when fewer than two are
  present.
- Offline verifier: when the certificate carries `codegen_sha256`, the
  portable verifier confirms it equals the trace's and the manifest's
  with `cryptography` + Python stdlib only. It does NOT trust the
  recorded `codegen_binding_ok` bool; it re-derives the equality and
  fails closed.

Residual honest boundary: the offline check confirms the certificate,
trace, and manifest name ONE compiled-program digest. It still does not
re-derive that program from source (that needs the toolchain; it is the
online path) and it still does not prove the run executed (a key-holder
can compute the genuine digest and stamp a fabricated trace; execution
attestation remains out of scope).

## Scope summary

| Concern | State |
|---------|-------|
| Trace carries codegen_sha256 | yes, optional, drop-when-None, signed |
| Producer stamps it | yes (run harness) |
| Online verifier re-derives + binds | yes (verify_conformance binding_ok) |
| Offline portable verifier checks it | yes (sha-equality; program re-derivation still online; S156) |
| Manifest / certificate carry it | yes (signed legs; S156) |
| Proves the run executed | no (execution attestation, out of scope) |
