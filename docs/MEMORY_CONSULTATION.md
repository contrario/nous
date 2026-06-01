# Memory Consultation (Phase 1)

A NOUS run may consult persistent per-world soul memory and record that
consultation INSIDE the signed conformance trace. The recorded consultation is
a cryptographic commitment to the exact memory state the run read, so a third
party can verify offline -- with only `cryptography` -- that the run consulted
the memory it claims, and nothing else.

This document is the user reference for the consultation field, the
offline-verifiable property it provides, the Phase 1 single-soul restriction,
and how the consultation surfaces to an auditor.

---

## What gets recorded

When a run is executed with consultation enabled, the signed `TraceEnvelope`
carries an optional `memory_consultation` object with these members:

| Member | Meaning |
|--------|---------|
| `world_sha256` | NAME-BOUND world identity: `sha256("nous_world_v1|" + world_name)` |
| `producing_soul_sha256` | NAME-BOUND soul identity: `sha256("nous_soul_v1|" + world_sha256_hex + "|" + soul_name)` |
| `consulted_chain_head` | Commitment to the entire consulted prefix: genesis if the chain is empty, else `chain_entry_hash(chain[-1])` |
| `consulted_seq_count` | Number of entries in the consulted chain |
| `consulted_at_utc` | Timestamp of the consultation |

The identities are NAME-BOUND: they are derived from the world and soul names,
not from any file path or run subject, so they are stable across edits to the
program source. The isolation boundary is the memory `base_dir`; two consultations
of the same world name within the same `base_dir` address the same world by
design.

---

## The offline-verifiable property

The consulted chain head is a hash commitment to the full prefix of memory the
run read. A verifier holding only the per-(world, soul) chain can reproduce the
claim end to end:

1. Read the chain for `(world_sha256, producing_soul_sha256)` from the memory store.
2. Recompute the head: genesis if empty, else `chain_entry_hash` of the last entry.
3. Compare to `consulted_chain_head` in the signed trace.
4. Confirm `consulted_seq_count` equals the chain length.

If all four agree, the run provably consulted exactly that memory state. No
private key is required for this check; it is a recomputation against the signed
commitment.

### Backward compatibility (drop-when-None)

The `memory_consultation` member is canonicalized DROP-WHEN-NONE: when a run does
not consult memory, the member is absent from the canonical signed body AND from
every persisted/wire form of the trace. A non-consulting trace is therefore
byte-identical to traces produced before this field existed. Every previously
shipped v1 signature continues to verify unchanged, and the key-agnostic offline
verifier accepts both consulting and non-consulting traces with no change.

This follows RFC 8785 (JCS) wire-vs-canonical discipline: canonicalization
defines how the members that are PRESENT are serialized, not which members are
present; equal member sets between the signed body and the persisted form are
the application invariant the writer must preserve.

---

## Phase 1 restriction: single soul

Phase 1 consultation requires exactly one soul. A run that would consult more
than one soul refuses fail-closed with `MemoryConsultationError`. This is the
smallest provable unit; multi-soul consultation as a canonicalized set is
deferred to Phase 1.x.

Consultation also requires trace emission: the interpreter path refuses to
consult memory without `--emit-trace`, because the consultation only has meaning
as a recorded, signed commitment.

---

## How to consult memory

Consultation is a flag on the existing `run` subcommand (not a new subcommand):

```
nous run program.nous --consult-memory --emit-trace
```

The flag defaults OFF. With it OFF, runs behave exactly as before and produce
byte-identical traces.

---

## Auditor visibility

The generated offline conformance verifier (`build_conformance_verifier_v2`)
prints the consulted soul, chain head, and entry count in its summary when the
trace carries a `memory_consultation`. This is a pure print over the
already-loaded trace dict; it does not alter canonicalization or the verify
result. A trace without a consultation prints nothing extra and verifies exactly
as it did before.

---

## See also

- `docs/MEMORY_PHASE1_DESIGN.md` -- the sealed design: NAME-BOUND identity, the
  drop-when-None write-path invariant, and the single-soul (Option c) freeze.
