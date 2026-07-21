# NOUS-TRACE Specification

**Version:** 0.1.0-draft
**Status:** Draft for adversarial review (Principal Critic pass pending)
**License intent:** Open specification. Reference verifier to be published under a permissive license.

---

## 1. Status of This Document

This is a draft. It has passed a research phase and an innovation gate but has NOT passed adversarial review. Nothing in this document is final. Implementations built against a draft MUST declare the draft version and MUST NOT claim conformance to "NOUS-TRACE" without a version qualifier.

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are to be interpreted as described in RFC 2119.

## 2. Problem Statement

Regulated operators of agentic AI systems must produce records that (a) are generated automatically, (b) are tamper-evident, (c) survive independent verification by a party that does not trust the operator, and (d) connect runtime behavior to the design-time policy commitments documented for the system.

Existing tooling addresses (a)–(c) as integrity of logs. No shipping tool binds runtime records to design-time obligations that were formally discharged (SMT-proved) before deployment. NOUS-TRACE specifies that binding.

## 3. Terminology

- **Trace**: the ordered sequence of Events describing one agent run.
- **Event**: one signed, hash-chained record.
- **Producer**: the runtime component emitting Events (agent-side).
- **Signer**: the isolated process holding the private key. Not the Producer.
- **Verifier**: independent software that validates a Trace offline.
- **Obligation**: a predicate from a compiled NOUS specification whose validity was discharged at design time by an SMT solver (Z3) or Farkas certificate.
- **Obligation Manifest**: the signed list of Obligations in force for a given deployment, extracted from the compiled NOUS spec.
- **Evidence Pack**: the exportable archive containing everything a Verifier needs.
- **Payload Store**: content-addressed storage for raw inputs/outputs, separate from the Trace.

## 4. Claims and Non-Claims

This section is normative. Marketing or documentation that exceeds these claims is non-conformant.

**Claimed:**

1. Any modification, reordering, deletion, or insertion of Events after signing is detectable by the Verifier (integrity).
2. Events anchored via a published checkpoint cannot be forged retroactively even by a party that later obtains the private key (bounded forgery window).
3. Each `policy_check` Event is bound to a specific Obligation whose predicate was discharged at design time; the Verifier can confirm the binding and the design-time evidence hash.
4. Erasure of a payload from the Payload Store does not invalidate the Trace (erasure compatibility).

**Not claimed:**

1. That the agent's computation is reproducible. LLM nodes are non-deterministic. Replay verifies the record, not the computation.
2. That the run is "proved correct." The word *proved* is reserved for design-time Z3/Farkas artifacts referenced by Obligations.
3. That a fully compromised host (including the Signer process) cannot produce false records going forward. See §14.
4. That a Trace by itself satisfies EU AI Act Article 12. It is designed to support an Article 12 record-keeping implementation; legal sufficiency is a deployment and legal question.

## 5. Threat Model

**Assets:** Trace integrity, Obligation binding, private signing key, anchored checkpoints.

**Adversaries:**

- **A1 — Compromised Producer.** The agent process is attacker-controlled at some point during the run. Goal: emit false Events, re-sign altered history, or silently drop Events.
- **A2 — Post-hoc editor.** An operator or intruder edits stored Traces after the run. Goal: undetectable modification or deletion.
- **A3 — Key thief.** Attacker obtains the private key at time t. Goal: forge Events dated before t.
- **A4 — Dishonest operator.** The operator runs a modified Producer that selectively logs. Goal: present a clean Trace while misbehaving off the record.

**Mitigations mapped:**

- A1: the Signer, not the Producer, enforces sequence monotonicity and chain consistency (§11). A compromised Producer cannot re-sign or reorder already-signed Events; it can only stop logging (detectable as an incomplete Trace, §13) or log false content going forward (residual, §14).
- A2: hash chain + signatures + Merkle checkpoints anchored in an external transparency log (Rekor).
- A3: anchored checkpoints bound the forgery window to post-theft Events only.
- A4: not fully solvable in software. Partially mitigated by Signer-side monotonic counters (gaps are evidence) and by the deployment requirement that tool adapters emit Events at the adapter layer, not inside model-generated code. Declared residual risk.

**Out of scope for v0.1:** hardware attestation (TEE), zkVM execution proofs, multi-node distributed traces, network-level adversaries between Producer and Signer on the same host.

## 6. Cryptographic Primitives

- Hash: SHA-256 everywhere.
- Signatures: Ed25519 (RFC 8032). The signature is computed over the 32-byte event hash (§8.2).
- Canonicalization: JSON Canonicalization Scheme, JCS (RFC 8785). All hashing of JSON structures MUST operate on JCS bytes.
- Merkle trees: RFC 6962 construction. Leaf hash = SHA-256(0x00 ‖ event_hash). Interior node = SHA-256(0x01 ‖ left ‖ right). This domain separation prevents second-preimage attacks between leaves and nodes.
- Salts: 16 bytes from a CSPRNG, one per payload.
- `key_id`: lowercase hex of the first 8 bytes of SHA-256(raw 32-byte Ed25519 public key).

Algorithm agility: every Trace carries `spec_version`. Future versions may rotate primitives; v0.1 implementations MUST reject unknown versions rather than guess.

## 7. Data Model

### 7.1 Trace file

A Trace is an NDJSON file: one Event object per line, in sequence order. Encoding UTF-8, no BOM.

### 7.2 Event object

```json
{
  "spec_version": "0.1.0",
  "trace_id": "uuidv7",
  "seq": 17,
  "ts_wall": "2026-07-21T14:03:22.117Z",
  "event_type": "tool_call",
  "actor": "aetherlang.greek_tax_advisor",
  "body": { },
  "payload_refs": [
    { "role": "input",  "hash": "hex sha256(salt||payload)" },
    { "role": "output", "hash": "hex sha256(salt||payload)" }
  ],
  "obligation_ref": null,
  "prev_hash": "hex 64 chars",
  "key_id": "hex 16 chars",
  "sig": "hex 128 chars"
}
```

Field rules:

- `seq`: unsigned integer, starts at 0, strictly increments by 1. No gaps, no reuse.
- `ts_wall`: informational only. Ordering guarantees derive from `seq`, never from clocks.
- `body`: event-type-specific structured metadata (tool name, model id, parameters hash, verdicts). MUST NOT contain raw payloads or personal data; raw content goes to the Payload Store and is referenced by `payload_refs`.
- `payload_refs`: zero or more salted-hash references. The salt is stored with the payload in the Payload Store, never in the Event.
- `obligation_ref`: null, or an object `{ "obligation_id": "hex64", "verdict": "pass|fail|error", "evidence_hash": "hex64" }`. Nullable by design: integrity-only mode is the degenerate case of the same schema.
- `prev_hash`: event_hash of the previous Event; for `seq` 0, 64 hex zeros.
- `sig`: Ed25519 signature over event_hash (§8.2).

### 7.3 Event types (v0.1 registry)

| type | purpose | obligation_ref |
|---|---|---|
| `run_start` | opens the Trace; carries deployment metadata: Obligation Manifest hash, NOUS dossier reference, Producer version | MUST be null |
| `llm_call` | one model invocation; body: model id, provider, params hash | MAY |
| `tool_call` | one tool/effect invocation; body: tool name, adapter version | MAY |
| `policy_check` | evaluation of an action against an Obligation | MUST be non-null |
| `human_override` | a human approved/denied/modified an action; body: operator id hash, decision | MAY |
| `error` | Producer-visible failure | MUST be null |
| `checkpoint` | Merkle anchor record (§9) | MUST be null |
| `run_end` | closes the Trace; body: outcome summary | MUST be null |

Unknown event types: Verifier MUST treat as opaque, verify integrity normally, and flag them in the report. This permits forward-compatible extension without breaking old verifiers.

## 8. Chain Construction

### 8.1 Signing input

For each Event, construct the object with all fields EXCEPT `sig`. Serialize with JCS.

### 8.2 Hash and signature

```
event_hash = SHA-256(JCS(event_without_sig))
sig        = Ed25519_sign(private_key, event_hash)
```

### 8.3 Linking

`prev_hash` of Event n+1 MUST equal `event_hash` of Event n. Genesis (`seq` 0) uses 64 hex zeros.

## 9. Checkpointing and Anchoring

A `checkpoint` Event MUST be emitted when ANY of the following occurs:

- 64 Events have been signed since the last checkpoint (configurable, MUST be ≤ 256), or
- 300 seconds have elapsed since the last checkpoint with at least one new Event, or
- the run ends (`run_end` is always followed by a final checkpoint), or
- the Producer shuts down gracefully.

The checkpoint body contains:

```json
{
  "range": { "from_seq": 12, "to_seq": 42 },
  "merkle_root": "hex64",
  "anchor": {
    "type": "rekor",
    "log_index": 123456789,
    "entry_uuid": "…",
    "inclusion_proof": { }
  }
}
```

The Merkle tree is built over the `event_hash` values of the covered range (RFC 6962 construction, §6). The signed `merkle_root` is submitted to the Rekor transparency log. The returned inclusion proof MUST be embedded in the checkpoint body so that offline verification is possible without contacting Rekor.

Anchoring failure (network down): the Producer MUST still emit the checkpoint with `anchor: null`, and MUST retro-anchor at the next opportunity via a subsequent checkpoint covering the same root. Unanchored checkpoints are flagged, not fatal.

## 10. Payload Store and Erasure

- Content-addressed: key = the salted hash appearing in `payload_refs`.
- Each entry stores: salt (16 bytes), raw payload bytes, media type.
- **Erasure semantics:** deleting an entry (payload AND salt) satisfies erasure requests. The hash remaining in the chain is, without the salt, computationally unlinkable to the erased content. The Trace remains fully verifiable; the Verifier reports the reference as `erased/unavailable`, which is a legitimate state, not an integrity failure.
- Salts MUST be unique per payload. Reuse across payloads is non-conformant (enables cross-referencing).

## 11. Signer

The Signer is a separate OS process. Requirements:

1. Holds the only copy of the private key. Key file permissions 0600, owner = signer user, distinct from the Producer user.
2. Exposes a local-only interface (Unix domain socket). No network listener.
3. Is **stateful per trace_id**: it stores `(last_seq, last_event_hash)` and MUST refuse to sign an Event whose `seq` is not exactly `last_seq + 1` or whose `prev_hash` does not equal `last_event_hash`. This makes the Signer, not the Producer, the integrity gate: a compromised Producer cannot rewrite or fork history, only append or stop.
4. MUST refuse to sign two different Events for the same `(trace_id, seq)`.
5. Appends every signing operation to its own local audit log (append-only file). This log is operational, not part of the Trace.
6. Signer state persistence: `(trace_id, last_seq, last_event_hash)` MUST survive Signer restarts. Loss of Signer state terminates the Trace (a new run must start); it MUST NOT silently reset counters.

## 12. Obligation Binding

- `obligation_id` = SHA-256 of the JCS form of the predicate object as emitted by the NOUS compiler.
- The **Obligation Manifest** is produced at deploy time: the list of `{obligation_id, human_label, dossier_ref, proof_artifact_hash}` entries, signed with the same key hierarchy, its hash recorded in `run_start`.
- A `policy_check` Event's `obligation_id` MUST appear in the Manifest referenced by its own Trace's `run_start`. The Verifier enforces this.
- `evidence_hash` = SHA-256 of the runtime checker's output artifact (e.g., the guard's evaluation record), stored in the Payload Store.
- **Semantics of the binding, stated exactly:** "At design time, predicate P was discharged by Z3/Farkas (proof artifact hash H, in dossier D). At runtime, at Trace position s, action A was evaluated against P with verdict V." Nothing more.

## 13. Verifier

### 13.1 Independence requirements

The Verifier MUST be a separate codebase from the Producer/Signer, minimal dependencies (JCS, SHA-256, Ed25519, JSON parsing), MUST run fully offline given an Evidence Pack, and MUST NOT execute any code contained in the Trace or payloads.

### 13.2 Verification algorithm (normative order)

1. Parse the Evidence Pack manifest; check `spec_version` is supported.
2. Load declared public keys; check `key_id` derivations.
3. Parse Trace NDJSON. Check `seq` = 0,1,2,… with no gaps or duplicates.
4. For each Event: recompute `event_hash` from JCS bytes; check `prev_hash` linkage; verify `sig` under the declared key.
5. Recompute Merkle roots for every checkpoint range; compare to checkpoint bodies.
6. For each anchored checkpoint: verify the embedded Rekor inclusion proof against the pinned Rekor public key (offline). Online tail consistency check is OPTIONAL.
7. Check structural rules: exactly one `run_start` at `seq` 0; `run_end` present, else result is INCOMPLETE; final checkpoint covers the tail.
8. Load the Obligation Manifest; check its hash against `run_start`; check every `policy_check` references a manifested `obligation_id`; verify presence and hashes of proof artifacts included in the Pack.
9. Resolve `payload_refs` against included payloads: verify salted hashes for present payloads; mark absent ones `erased/unavailable`.
10. Emit report.

### 13.3 Verdicts

- `VALID` — all checks pass, Trace complete.
- `VALID-INCOMPLETE` — integrity checks pass, but no `run_end` (crash) or unanchored tail. The verified prefix is trustworthy up to the last anchored checkpoint.
- `INVALID(reason, seq)` — first failing check, with position.

Exit codes: 0 / 10 / 20 respectively, for CI use.

## 14. Failure, Recovery, Residual Risk

- **Producer crash:** Trace ends without `run_end`. Loss is bounded by the checkpoint policy (§9): at most 64 Events or 300 seconds of unanchored tail.
- **Signer crash:** run terminates; state persistence (§11.6) prevents counter reset attacks.
- **Rekor unavailable:** degraded to unanchored checkpoints, retro-anchored later; the Verifier reports the anchoring gap.
- **Residual risks, declared:** full-host compromise including the Signer allows false Events going forward (never retroactively past an anchor); a dishonest operator can run an unlogged parallel system (A4) — NOUS-TRACE evidences what the traced system did, not that no other system existed.

## 15. Evidence Pack

A tar.gz archive:

```
manifest.json          pack metadata, spec_version, file hashes
trace.ndjson           the Trace
keys/producer.pub      Ed25519 public key(s)
keys/rekor.pub         pinned Rekor log public key
obligations.json       Obligation Manifest
proofs/                design-time Z3/Farkas artifacts referenced by the Manifest
payloads/              optional; content-addressed entries not erased
dossier_ref.json       pointer + hash of the NOUS Annex IV dossier
```

**Record-keeping mapping (informative):** `policy_check` failures and `human_override` Events support identification of risk situations (Art. 12(2)(a)); complete Traces with outcome summaries support post-market monitoring (Art. 12(2)(b), Art. 72); per-run structure with operator-attributed overrides supports operation monitoring by deployers (Art. 12(2)(c), Art. 26(5)). Retention (Art. 19) is a storage-policy concern outside the Pack format; Packs are self-contained and cold-storable.

## 16. Non-Goals (v0.1)

TEE/hardware attestation; zkVM or any proof of model computation; LLM determinism or output replay; policy *enforcement* (remains in the existing guard — NOUS-TRACE records, it does not gate); key rotation ceremonies beyond `key_id` presence; multi-node/distributed traces; streaming verification.

## 17. Conformance

An implementation conforms as **Producer**, **Signer**, or **Verifier** independently. A conforming Verifier MUST fail closed: any ambiguity is INVALID, not VALID. Test vectors (golden Traces: one valid, one per tampering class — edited body, dropped Event, reordered Events, forged post-anchor Event, reused salt) ship with the reference implementation and are normative.

---

*Draft prepared for adversarial review. Next stage per the engineering sequence: Principal Critic pass, then redesign, then reference implementation (Signer + Producer adapter for AetherLang, standalone Verifier CLI).*
