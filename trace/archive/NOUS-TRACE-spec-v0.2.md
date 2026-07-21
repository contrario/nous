# NOUS-TRACE Specification

**Version:** 0.2.0-draft
**Status:** Post-critic redesign. Supersedes 0.1.0-draft.
**Changes from 0.1:** resolves critic findings B1 (domain separation), B2 (verifier recomputation), B3 (time bounding), B4 (payload classes / erasure), B5 (signer peer authentication), B6 (key lifecycle, two-tier keys), M1 (pluggable anchors), M2 (incomplete-trace semantics), S1 (policy packs / assurance levels), plus the JCS numeric restriction.

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are per RFC 2119.

---

## 1. Problem Statement

Regulated operators of agentic AI systems must produce records that are generated automatically, are tamper-evident, survive independent verification by a party that does not trust the operator, and connect runtime behavior to design-time policy commitments.

Existing tools stop at log integrity. NOUS-TRACE additionally specifies (a) a machine-checkable binding between runtime events and policy predicates, and (b) independent re-evaluation of those predicates by the Verifier — not trust in the operator's runtime checker.

## 2. Terminology

- **Trace / Event / Producer / Verifier**: as in v0.1 — ordered signed records of one run; the emitting runtime; the independent offline validator.
- **Signer**: isolated process holding the Runtime Key.
- **Deployment Key**: offline key that signs deployment artifacts (manifests). Never present on the runtime host.
- **Runtime Key**: online key held by the Signer; signs Events and checkpoint roots.
- **Obligation**: a predicate in NOUS-EXPR normal form (§8), listed in the Obligation Manifest.
- **Assurance level**: `proved` (predicate discharged at design time by Z3/Farkas, artifact included) or `declared` (predicate stated without design-time proof). See §8.4.
- **Assignment Record**: the concrete values of a predicate's variables at evaluation time. Evidence-class payload (§11).
- **Evidence Pack**: exportable archive containing everything the Verifier needs.

## 3. Claims and Non-Claims (normative)

**Claimed:**

1. **Integrity.** Any modification, reordering, deletion, or insertion of Events after signing is detectable.
2. **Bounded forgery.** Events covered by a published anchor cannot be forged retroactively, even by a party that later obtains the Runtime Key.
3. **Independent policy recomputation.** For each `policy_check`, the Verifier itself re-evaluates the Obligation's predicate over the recorded Assignment Record and compares the result to the recorded verdict. The trust base for the verdict is the Verifier, not the operator's runtime checker.
4. **Time bounding.** Claimed wall-clock times are bounded by independent anchor timestamps within a declared tolerance.
5. **Erasure compatibility.** Erasure of content-class payloads does not invalidate the Trace and does not remove audit evidence (§11).

**Not claimed:**

1. Reproducibility of the agent's computation. LLM nodes are non-deterministic; verification covers the record, not the computation.
2. Run-level correctness. *Proved* refers exclusively to design-time Z3/Farkas artifacts attached to `proved`-assurance Obligations.
3. Resistance to a fully compromised host including the Signer, for Events after the compromise (§15).
4. Legal sufficiency under any regulation. The format is designed to support Article 12-style record-keeping; sufficiency is a deployment and legal determination.
5. That the recorded Assignment Record faithfully reflects external reality. The Verifier proves *consistency of record and verdict*, not sensor truth. A Producer that records false values is adversary A4 (residual).

## 4. Cryptographic Primitives

- Hash: SHA-256.
- Signatures: Ed25519 (RFC 8032).
- Canonicalization: JCS (RFC 8785), restricted per §5.3.
- Merkle: RFC 6962 domain-separated construction (leaf `0x00‖h`, node `0x01‖l‖r`).
- Salts: 16 bytes CSPRNG, unique per payload.
- `key_id`: hex of first 8 bytes of SHA-256(raw public key).

### 4.1 Signature domain separation (resolves B1)

No raw digest is ever signed. The signing input is:

```
sign_input = UTF8(tag) || 0x00 || object_hash
sig        = Ed25519_sign(key, sign_input)
```

Registered tags (v0.2):

| tag | object | key |
|---|---|---|
| `NOUS-TRACE/v0.2/event` | event_hash | Runtime |
| `NOUS-TRACE/v0.2/checkpoint-root` | merkle_root (as submitted to anchor) | Runtime |
| `NOUS-TRACE/v0.2/obligation-manifest` | manifest hash | Deployment |
| `NOUS-TRACE/v0.2/keys-manifest` | keys manifest hash | Deployment |
| `NOUS-TRACE/v0.2/pack-manifest` | pack manifest hash | Deployment or Runtime (declared) |

A signature valid under one tag is invalid under every other by construction. Verifiers MUST reconstruct `sign_input` with the expected tag and MUST NOT accept a bare-digest signature.

### 4.2 Key hierarchy (resolves B6)

Two tiers:

- **Deployment Key**: offline. Signs the Obligation Manifest and the Keys Manifest at deploy time. Compromise of the runtime host does not permit forging manifests.
- **Runtime Key**: held only by the Signer. Signs Events and checkpoint roots.

**Keys Manifest** (`keys.json`): entries `{key_id, public_key, role: "runtime"|"deployment", not_before, not_after}` (RFC 3339 UTC), signed by the Deployment Key. Root of trust for a Pack = the Deployment public key, conveyed out of band (pinned by the auditor / published fingerprint). This is declared: NOUS-TRACE does not include a PKI.

**Validity enforcement:** the Verifier MUST reject any signature whose *anchor-bounded time* (§10.3) falls outside the signing key's validity window. Producer-claimed `ts_wall` alone MUST NOT be used for validity decisions.

## 5. Data Model

### 5.1 Trace file

NDJSON, one Event per line, sequence order, UTF-8, no BOM.

### 5.2 Event object

```json
{
  "spec_version": "0.2.0",
  "trace_id": "uuidv7",
  "seq": 17,
  "ts_wall": "2026-07-21T14:03:22Z",
  "event_type": "policy_check",
  "actor": "aetherlang.greek_tax_advisor",
  "body": { },
  "payload_refs": [
    { "role": "assignment", "class": "evidence", "hash": "hex64" }
  ],
  "obligation_ref": {
    "obligation_id": "hex64",
    "verdict": "pass",
    "assignment_hash": "hex64"
  },
  "prev_hash": "hex64",
  "key_id": "hex16",
  "sig": "hex128"
}
```

Rules unchanged from v0.1 except: `payload_refs[].class` is mandatory (§11); `obligation_ref.assignment_hash` MUST equal the hash of an evidence-class payload_ref in the same Event; `evidence_hash` from v0.1 is renamed and typed as the Assignment Record.

`seq` starts at 0, strict +1, no gaps. `ts_wall` is informational; ordering derives from `seq`. `body` MUST NOT contain raw payloads or personal data.

### 5.3 Numeric restriction (JCS interoperability)

In all signed structures (Events, manifests, checkpoint bodies): numbers MUST be integers within ±2^53−1. Floating point is FORBIDDEN. Non-integer quantities are strings with declared unit and scale (e.g., `"amount_eur_cents": 125000` or `"ratio_ppm": "153000"`). Rationale: IEEE-754 serialization divergence breaks cross-language hash agreement.

### 5.4 Event types

As v0.1 (`run_start`, `llm_call`, `tool_call`, `policy_check`, `human_override`, `error`, `checkpoint`, `run_end`), with:

- `run_start` body MUST include: Obligation Manifest hash, Keys Manifest hash, dossier reference, Producer version, anchoring policy (§10.1), time tolerance (§10.3).
- `policy_check`: `obligation_ref` MUST be non-null; assignment payload mandatory.
- Unknown types: integrity-verified, flagged, treated as opaque.

## 6. Chain Construction

```
event_hash = SHA-256(JCS(event_without_sig))
sig        = Ed25519_sign(runtime_key, "NOUS-TRACE/v0.2/event" || 0x00 || event_hash)
prev_hash(n+1) = event_hash(n);  genesis prev_hash = 64 hex zeros
```

## 7. Signer

1. Separate OS process and OS user; sole holder of the Runtime private key (file mode 0600).
2. Local-only Unix domain socket. No network listener.
3. **Peer authentication (resolves B5):** the Signer MUST obtain peer credentials (`SO_PEERCRED` on Linux) on every connection and MUST reject clients whose UID is not in a configured allowlist. Rejected attempts MUST be written to the Signer's local audit log. Deployments on platforms without ancestry-verifiable peer credentials are non-conformant for the Signer role.
4. **Stateful integrity gate:** per `trace_id`, the Signer persists `(last_seq, last_event_hash)`; it MUST refuse `seq ≠ last_seq+1`, mismatched `prev_hash`, or a second signature for any `(trace_id, seq)`. State MUST survive restarts; state loss terminates the Trace and MUST NOT reset counters.
5. The Signer signs only registered tags (§4.1) and MUST refuse a request that supplies its own signing input.

## 8. Obligations and NOUS-EXPR

### 8.1 NOUS-EXPR normal form

Predicates are quantifier-free expressions over typed variables, in the following grammar (v0.2, closed):

```
type     := int | bool | string
expr     := bexpr
bexpr    := bexpr "and" bexpr | bexpr "or" bexpr | "not" bexpr
          | iexpr cmp iexpr | sexpr scmp sexpr | var(bool) | "true" | "false"
cmp      := "=" | "!=" | "<" | "<=" | ">" | ">="
scmp     := "=" | "!=" | "prefix_of" | "in"        // "in": membership in a literal string set
iexpr    := var(int) | int_literal | iexpr "+" iexpr | iexpr "-" iexpr | iexpr "*" iexpr
sexpr    := var(string) | string_literal | literal string set
```

Division, modulo, floats, regular expressions, quantifiers, and function calls are excluded from v0.2. Evaluation is total: any type error is verdict `error`. Integers are arbitrary precision at evaluation; serialized literals obey §5.3.

Rationale: this subset is decidable, trivially evaluable, side-effect-free, sufficient for tool-use policies (limits, allowlists, orderings), and small enough that two independent evaluator implementations can realistically agree.

### 8.2 Obligation Manifest

Signed by the Deployment Key. Entries:

```json
{
  "obligation_id": "hex64 = SHA-256(JCS(predicate_object))",
  "label": "max_refund_without_human",
  "predicate": { },
  "variables": [ {"name": "amount_eur_cents", "type": "int"}, ... ],
  "assurance": "proved" | "declared",
  "proof_artifact_hash": "hex64 | null",
  "dossier_ref": "… | null"
}
```

### 8.3 Assignment Record and recomputation (resolves B2)

The Assignment Record is a JCS JSON object mapping every variable of the predicate to a concrete value, stored as an **evidence-class** payload; its salted hash appears as `assignment_hash`.

The Verifier MUST: load the Assignment Record; check the variable set matches the Manifest declaration exactly (no missing, no extra); evaluate the predicate with its own evaluator; compare its result to the recorded `verdict`. Any mismatch, or any absent Assignment Record, is INVALID.

The resulting claim: the verdict is recomputed by the auditor's own tooling from recorded inputs. The operator's runtime checker is out of the trust base. What remains untrusted is whether recorded values reflect reality (Non-claim 5).

### 8.4 Assurance levels (resolves S1)

- `proved`: `proof_artifact_hash` MUST be non-null and the artifact (Z3 proof object / unsat core / Farkas certificate as emitted by the NOUS toolchain) MUST be present in the Pack with matching hash. Only these Obligations may be described with the word "proved".
- `declared`: predicate stated without design-time proof. Permitted, first-class, honestly labeled. This enables standalone **policy packs** — adoption without the full NOUS toolchain, with an upgrade path to `proved`.

The Verifier's report MUST state the assurance level per Obligation and MUST summarize: "N checks recomputed; K against proved obligations, M against declared obligations."

## 9. Checkpointing

A `checkpoint` Event MUST be emitted when any of: 64 Events since last checkpoint (configurable ≤ 256); 300 s elapsed with ≥1 new Event; `run_end`; graceful shutdown. The Merkle tree covers `event_hash` values of the range; the root is signed under the `checkpoint-root` tag and submitted to the anchor backend(s).

## 10. Anchoring (resolves M1, B3)

### 10.1 Pluggable backends

Anchoring policy is declared in `run_start` and the Pack manifest: `rekor`, `rfc3161`, or `both`.

- **`rekor`**: public transparency log. Proof = log index, entry UUID, inclusion proof, signed entry timestamp. Property: public auditability. Cost: publicly observable activity metadata (rate, volume). 
- **`rfc3161`**: timestamp token from one or more declared TSAs over the signed root. Property: private, cheap, standard. Cost: trust in the TSA(s); no public transparency.
- **`both`**: RECOMMENDED for high-stakes deployments.

Verifiers MUST support both proof types offline (pinned Rekor log key / pinned TSA certificate chains in the Pack).

### 10.2 Anchoring failure

Network failure → checkpoint emitted with `anchor: null`, retro-anchored by a later checkpoint over the same root. Unanchored ranges are reported as gaps, and weigh into the verdict per §13.

### 10.3 Time bounding (resolves B3)

Each anchor proof carries an independent timestamp `T_anchor` (Rekor integrated time / TSA genTime). Let `tol` be the tolerance declared in `run_start` (default 600 s, MUST be ≤ 3600 s). The Verifier MUST check, for every Event in an anchored range:

```
T_prev_anchor − tol ≤ ts_wall ≤ T_anchor + tol
```

(with `T_prev_anchor` = anchor time of the preceding anchored checkpoint; for the first range, the lower bound is unchecked and reported). Violations are INVALID. Consequence: a Trace fabricated today cannot claim last January; its claimed times are contradicted by its own anchors.

## 11. Payload Store, classes, erasure (resolves B4)

Content-addressed store; entry = salt (16 B) + payload bytes + media type; key = `SHA-256(salt‖payload)`.

Two classes, declared per reference:

- **`content`**: raw inputs/outputs. MAY contain personal data. Erasable: deleting payload+salt satisfies erasure; the chain hash becomes computationally unlinkable; the Verifier reports `erased/unavailable` as a legitimate state.
- **`evidence`**: Assignment Records, override decisions, verdict artifacts. MUST NOT contain personal data **by construction**: permitted value types are the NOUS-EXPR types, and deployments MUST map personal identifiers into pseudonymous or hashed variables before they enter an Assignment Record. Erasure of evidence-class payloads is FORBIDDEN; an absent evidence payload is INVALID, not `erased`.

This separates the two legal regimes structurally: erasure rights operate on content; record-keeping operates on evidence. Salt reuse across payloads is non-conformant.

## 12. Verifier

### 12.1 Independence

Separate codebase; minimal dependencies (SHA-256, Ed25519, JCS, JSON, and the NOUS-EXPR evaluator); fully offline given a Pack; MUST NOT execute code from the Trace or payloads; MUST fail closed.

### 12.2 Algorithm (normative order)

1. Parse Pack manifest; check `spec_version`.
2. Verify Keys Manifest signature under the pinned Deployment public key; index keys, roles, validity windows.
3. Verify Obligation Manifest signature (Deployment Key); index Obligations; for `proved` entries, check proof artifacts present with matching hashes.
4. Parse Trace; check `seq` continuity; recompute `event_hash`; check `prev_hash` links; verify each `sig` under the correct tag and a `runtime`-role key.
5. Recompute Merkle roots per checkpoint range; verify root signatures (`checkpoint-root` tag); verify anchor proofs offline (Rekor inclusion / RFC 3161 token) per declared policy.
6. Apply time bounding (§10.3); apply key-validity windows using anchor-bounded times (§4.2).
7. Structural checks: single `run_start` at seq 0; manifest hashes in `run_start` match the Pack's manifests; `run_end` and final anchored checkpoint present, else incomplete.
8. For every `policy_check`: resolve the Assignment Record (evidence-class, present, hash-valid); check variable set; **re-evaluate the predicate**; compare to recorded verdict.
9. Resolve content-class payload_refs: hash-verify present ones; mark absent as `erased/unavailable`.
10. Emit report: verdict, anchor coverage, time-bounding results, per-obligation recomputation summary with assurance levels, flags.

### 12.3 Verdicts and their meaning (resolves M2)

- `VALID` (exit 0): all checks pass; `run_end` present; final checkpoint anchored.
- `INTEGRITY-OK/INCOMPLETE` (exit 10): the verified prefix up to the last anchored checkpoint passes all checks; the Trace lacks a proper ending or has an unanchored tail. **Normative interpretation: in any high-stakes or audit context this verdict MUST be treated as an adverse finding requiring explanation, not as a weaker VALID.** Rationale: post-run key compromise permits truncating the tail to the last anchor; completeness of the tail is exactly what this verdict cannot attest.
- `INVALID(reason, seq)` (exit 20): first failing check with position.

## 13. Failure, Recovery, Residual Risk

- Producer crash: loss bounded by checkpoint policy; verdict INTEGRITY-OK/INCOMPLETE.
- Signer crash: run terminates; persisted state prevents counter reset.
- Anchor backends down: unanchored checkpoints, retro-anchoring, reported gaps.
- **Residual, declared:** (i) full-host compromise including the Signer → false Events forward of compromise, never behind an anchor; (ii) dishonest operator running an untraced parallel system — NOUS-TRACE evidences what the traced system did, not that nothing else ran; (iii) recorded-value fidelity (Non-claim 5); (iv) TSA collusion under `rfc3161`-only policy — mitigated by `both` or multiple TSAs.

## 14. Evidence Pack

```
manifest.json          spec_version, file hashes, anchoring policy, tolerance, pinned trust anchors
trace.ndjson
keys.json              Keys Manifest (Deployment-signed)
keys/deployment.pub    pinned out of band; included for convenience
obligations.json       Obligation Manifest (Deployment-signed)
proofs/                Z3/Farkas artifacts for proved obligations
anchors/               Rekor proofs / RFC 3161 tokens, if not inlined
payloads/evidence/     all evidence-class entries (mandatory, complete)
payloads/content/      content-class entries not erased (optional)
dossier_ref.json       pointer + hash of the NOUS Annex IV dossier (null for policy-pack mode)
```

Record-keeping mapping (informative), as v0.1 §15: policy_check failures and overrides → Art. 12(2)(a); complete traces → Art. 12(2)(b)/72; operator-attributed structure → Art. 12(2)(c)/26(5); retention per Art. 19 is storage policy; Packs are self-contained and cold-storable.

## 15. Non-Goals (v0.2)

TEE/hardware attestation; zkVM/computation proofs; LLM determinism or replay-of-computation; policy enforcement (recording only — the guard gates, the trace records); PKI (Deployment key is pinned out of band); multi-node traces; streaming verification; key revocation beyond validity windows (revocation list format deferred to v0.3).

## 16. Conformance

Roles conform independently: Producer, Signer, Verifier. Fail-closed is mandatory for Verifiers. Normative test vectors ship with the reference implementation:

- 1 golden VALID Trace (mixed proved/declared obligations, both anchor types, one erased content payload);
- tampering set: edited body; dropped Event; reordered Events; post-anchor forged Event; reused salt; verdict/assignment mismatch; missing evidence payload; wrong-tag signature; expired-key signature; back-dated `ts_wall` beyond tolerance; float in signed structure.

Each tampered vector MUST yield INVALID with the expected reason code.

---

*Next stage per the approved sequence: reference implementation, verifier-first — the Verifier plus the normative test vectors define conformance before any Producer code exists.*
