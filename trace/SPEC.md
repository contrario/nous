# NOUS-TRACE Specification

**Version:** 0.2.6-draft
**Status:** Implementation-validated. Supersedes 0.2.5-draft.
**Wire version:** `spec_version` in signed objects remains `"0.2.0"`. The document revision and the wire format version are deliberately distinct: no revision since 0.2.0 has changed a field, tag, hash input or encoding, so packs are intended to remain byte-compatible across 0.2.x document revisions. Implementing the `both` backend in 0.2.5 does not change this: `both` has been a declared `anchoring` value since 0.2.0 (reserved until now), so no field, tag, hash input or encoding is added to the wire vocabulary; the composite anchor block is a new arrangement of existing anchor sub-blocks, exactly as the two-outcome `rekor` block was when that backend landed. A pre-0.2.5 Verifier meeting a `both` anchor fails closed on an anchor type it cannot verify — the conformant refusal every unverifiable type already requires, not a wire break — and a pack produced before 0.2.5 is unaffected and verifies unchanged. *Evidence: a committed golden pack (`tests/reference_evidence/trace_bundle`) must keep verifying unmodified under the current Verifier, which pins this from revision 0.2.1 onward. The 0.2.0 → 0.2.1 interval rests on review only — no 0.2.0-era pack was retained — and is therefore asserted, not demonstrated.*

**Changes from 0.2.5:** §17 -- RECOMMENDED is added to the declared RFC 2119 keyword list. It was already used normatively (§10.1, `both` for a high-stakes deployment record) while the declaration named only five keywords, so by this document's own terms its force was undeclared. §16 -- a note records that the shipped vector set exercises Verifier conformance only: all thirteen vectors feed a Verifier and check verdict and reason code, and none exercises a Producer or Signer obligation, although §16 declares all three roles conform independently. The note states scope; it defines no new regime and adds no requirement. No normative requirement changed and no wire change: no field, tag, hash input or encoding moved and `spec_version` remains `"0.2.0"`. No claim in §3 and no part of the threat model changed.

**Changes from 0.2.4:** §10.1 — the `both` composite backend is implemented and its reserved status is lifted. The reference Verifier and the Verifier embedded in emitted dossiers now verify a `both` anchor offline: the `rekor` leg establishes transparency-log membership and the `rfc3161` leg establishes trusted time bound directly to the signed Merkle root. `both` therefore regains an RFC 2119 RECOMMENDED for high-stakes deployment records — the recommendation now points at a backend every conforming Verifier can verify, so it is no longer an overclaim. Under `both` the `rekor` leg MUST NOT carry its own RFC 3161 token: the composite carries one trusted-time source, the `rfc3161` leg over the root, and a `rekor` leg bearing a second genTime leaves the §10.3 binding time undeterminable, so a Verifier MUST fail closed. A composite delivering both legs verifies as INCLUDED-TIMED and enters §10.3. A run that DECLARED `both` but delivered only one leg is a shortfall (§10.1.1): a surviving `rekor` leg is INCLUDED-UNTIMED and a surviving `rfc3161` leg is the new state TIMED-UNINCLUDED — trusted time present, transparency-log membership absent — each exit 10, each reported as absence with no cause attributed. The composite anchor block is signed inside the checkpoint body, so a leg cannot be removed or substituted without the runtime key; a Producer-asserted record of a failed leg is unsigned, is not carried in the Pack, and can be omitted by a hostile Producer. No wire change: `both` has been a declared `anchoring` value since 0.2.0 and no field, tag, hash input or encoding moved; `spec_version` remains `"0.2.0"`. No claim in §3 and no part of the threat model changed.

**Changes from 0.2.3:** §10.1.1 (new) -- the anchoring policy declared in `run_start` and in the Pack manifest is now normatively cross-checked. No revision had required this and no Verifier performed it, so a Pack whose signed `run_start` declared one backend and whose checkpoints delivered another verified VALID. `run_start` is authoritative (signed by the runtime key, bound into the hash chain at seq 0, and covered by the first checkpoint anchor); the Pack manifest is advisory (unsigned, and absent from `manifest.hashes`). When both carry a policy and they disagree, the declared intent is not determinable and a Verifier MUST fail closed with the new reason code `RUN_START_ANCHORING`. A checkpoint whose anchor type diverges from the declared policy is a SHORTFALL: the anchor verifies and its evidence is undiminished, but the Pack delivered less than the Producer committed to, so the verdict is INTEGRITY-OK/INCOMPLETE with exit 10 rather than an integrity failure. A Verifier MUST NOT attribute a cause to a shortfall. When either declaration is absent no comparison is performed, so no pre-existing Pack changes verdict. §10.1 -- the `both` bullet no longer carries an RFC 2119 RECOMMENDED: a recommendation pointing at a backend that no conforming Verifier can verify is an overclaim in normative language. `both` is marked reserved until the backend lands. §12.4 -- `RUN_START_ANCHORING` registered immediately after `RUN_START_TOLERANCE`, matching the §12.2 check order. No wire change: no field, tag, hash input or encoding moved and `spec_version` remains `"0.2.0"`. No claim in §3 and no part of the threat model changed.

**Changes from 0.2.2:** §10.1 — the SHOULD introduced in 0.2.2 is restored to MUST. The reference Verifier and the Verifier embedded in emitted dossiers now both implement `rekor` offline (C2SP checkpoint signature, RFC 6962 inclusion proof, hashedrekord 0.0.2 leaf tie), so the requirement is met rather than aspirational. The `rekor` description is corrected: Rekor v2 returns no signed entry timestamp and no integrated time, so the earlier wording (entry UUID, signed entry timestamp) described the retired v1 API. A `rekor` anchor now has two normatively distinct outcomes, INCLUDED-TIMED and INCLUDED-UNTIMED, which a Verifier MUST report as distinct states; an untimed range is excluded from the §10.3 time bound. A Verifier MUST NOT attribute a cause to absent trusted time. Untimed `rekor` is declared non-conformant for a high-stakes deployment record. §10.3 — `T_anchor` for `rekor` is the genTime of the RFC 3161 token over the leaf signature. The composite `both` declaration remains unimplemented and a Pack declaring it is refused as an unverifiable anchor type. No claim in §3 and no part of the threat model changed.

**Changes from 0.2.1:** §10.1 — "Verifiers MUST support both production proof types offline" is downgraded to SHOULD, because the reference Verifier implements `rfc3161` only; `rekor`, and therefore `both`, are unimplemented. A normative MUST the reference implementation does not satisfy is an overclaim in the strongest available language. The gap is converted into two requirements the implementation does meet: a Verifier MUST fail closed on an anchor type it cannot verify, and MUST report trust-root provenance, with Pack-carried roots treated as operator-supplied and downgrading the report. **This downgrade is temporary: the MUST is restored when `rekor` lands.** No claim in §3 and no part of the threat model changed.

**Changes from 0.2.0 (in 0.2.1):** folds the six errata surfaced by the reference implementation (13/13 conformance vectors passing): E1 checkpoint coverage rule, E2 normative NOUS-EXPR JSON encoding, E3 Payload Store entry format, E4 wrong-tag reporting, E5 anchor backend registry incl. test backend, E6 reason-code registry and fail-closed ordering. No architectural changes; 0.2.0 claims and threat model unchanged.

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, MAY, and RECOMMENDED are per RFC 2119.

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

## 3.1 Bundle-level Temporal Claims (normative)

The claims in §3 concern the internal integrity of a Trace and the
independent recomputation of its verdicts. This section adds a *taxonomy*
over the temporal guarantees that a completed trace bundle can carry. It
introduces one new normative claim (C2) and names two guarantees already
provided by §9–§10 (C1, C3); it renumbers and re-specifies nothing in §3.

The taxonomy distinguishes three layers, and a claim's status depends on
which anchoring backend (§10.1) realizes it:

- **Protocol semantics** — the property as specified.
- **Profile realization** — a production anchoring profile (`rekor`,
  `rfc3161`, or `both`) that satisfies the property.
- **Conformance backend** — `rfc3161-sim` (§10.1, E5), which realizes only
  the structural aspects required for deterministic conformance testing.

**C1 — Intra-bundle checkpoint ordering.** The signed checkpoint chain
(§9) establishes a monotone order over the bundle's Events and checkpoints
that is internally verifiable without any external time source. C1 is
realized by every backend, including `rfc3161-sim`. C1 makes no claim about
wall-clock time; it orders Events *relative to one another within the
bundle*.

**C2 — Bundle temporal existence.** A VALID trace bundle evidences that the
bundle, identified by the canonical hash of its manifest, existed in its
exact form no later than an independently attested point in time
`T_attest`, without trusting the Producer. The temporal trust boundary is
the bundle identified by the canonical hash of its manifest; individual
checkpoints remain outside this claim.

*Not claimed by C2:* (a) trusted wall-clock time for individual checkpoints
— that is the concern of C3, not C2; (b) that the bundle existed *before*
any second, independent event — relative ordering between two attested
times requires a second anchor and is out of scope for C2; (c) that
`T_attest` is accurate beyond the trust placed in the attesting authority
named by the realizing profile. C2 is an *upper bound* on the bundle's
creation time (anti-backdating), not an assertion of equality with
`T_attest`.

**C3 — Per-checkpoint trusted time.** Each checkpoint anchor carries an
independent timestamp that bounds the claimed wall-clock times of the
Events in its range within a declared tolerance (§10.3). This is claim §3.4
("Time bounding") applied per checkpoint. C3 is a valid security property
of the specification whenever it is realized by a production anchoring
profile (`rekor` / `rfc3161`). The `rfc3161-sim` conformance backend
intentionally realizes only the structural aspects required for
deterministic testing, and therefore provides C1 but **not** the full C3
property. C3 is not absent from the specification; it is absent only from
the simulated backend. A bundle whose only anchor is `rfc3161-sim`
therefore does not carry C3, and the reference verifier already
communicates this limitation through its anchor basis (which names the
anchor as intra-bundle ordering, not trusted wall-clock time). A
first-class normative C3 result is deferred until the verifier exposes
one; introducing it earlier would place a MUST in the specification that
the reference implementation does not yet satisfy.

### 3.1.1 C2 reference profile (0.2.x)

In this version the attestation realizing C2 is an RFC 3161 timestamp token
from a pinned-root TSA over the exact bytes of the bundle's manifest;
`T_attest` is the token genTime; verification is performed offline against
the pinned TSA root, with no network access and no trust in the Producer.
The receipt binds the canonical manifest hash to `T_attest`, and the
Verifier reports the bundle as carrying C2 only when the token verifies
against a pinned root and its imprint binds the bundle manifest bytes.

In this profile, the bundle identity required by §3.1.2 is established
by verifying the bundle's canonical manifest hash (`trace_bundle_sha256`
in the signed dossier manifest); future profiles MAY establish the same
identity by another mechanism while preserving the requirement.

The C2 verification behavior specified here is normative; reference
implementation support is tracked separately until implemented. A reader
who runs the current reference verifier and observes no C2 result is
seeing the specification lead the implementation, not a defect in the
specification.

Future profiles MAY realize C2 through other mechanisms — for example a
transparency-log inclusion proof under a signed tree head — provided they
attest the bundle's canonical manifest hash and yield a verifiable
`T_attest` upper bound. **Future profiles MUST preserve the security
property of C2; only the realization mechanism may vary.**

## 3.1.2 C2 Verification Requirements (normative)

These requirements are stated as observable properties of a conforming
Verifier, not as an evaluation algorithm. Two Verifiers that produce the
same result for every input are equally conformant, regardless of internal
structure.

A Verifier MUST:

- establish and successfully verify the identity of the anchored bundle —
  a C2 claim is defined over an identified object, never over anonymous
  bytes;
- verify the integrity of the anchor receipt against the signed manifest;
- validate the RFC 3161 token against a pinned TSA root;
- verify that the token's message imprint binds the identified bundle
  manifest;
- emit a C2 claim only after all of the above have succeeded.

A Verifier MUST NOT emit a C2 claim unless the bundle identity has first
been established and successfully verified. C2 attestation presupposes
identity: temporal existence is claimed for a known object, not for the
bytes an unverified receipt happens to name.

A Verifier MUST distinguish the following failure classes so that a failure
is attributable to its cause: identity, receipt format, cryptographic
validation, and imprint binding. The concrete reason-code identifiers are
an implementation matter, provided each maps one-to-one onto a normative
failure class.

`T_attest` is trusted data extracted from a token that has already
satisfied every requirement above. It is a reported output, not a
verification step, and MUST NOT influence any requirement.

The anchor receipt carries only the evidence required to verify these
properties: a schema version, the identifying hash of the anchored bundle,
and the RFC 3161 token. Explanatory text (such as a human-readable basis)
and provenance (such as a TSA URL) are Verifier output or documentation,
not evidence; a Verifier MUST NOT rely on them from the receipt, and the
trust root for the token remains the pinned TSA certificate.

**Reference evaluation order (informative).** The reference implementation
evaluates these requirements in a fixed order — identity, then receipt
integrity, then cryptographic validation, then semantic extraction of
`T_attest`, then claim emission. This identity-before-cryptography order
keeps failure attribution clean and avoids ASN.1 work on a mis-identified
bundle. It is a reference strategy, not a conformance requirement: an
implementation MAY reorder, cache, or parallelize provided it satisfies the
normative requirements above and yields the same observable result for
every input.

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

**Concrete JSON encoding (normative, E2):**

| construct | encoding |
|---|---|
| int literal | `{"int": n}` |
| string literal | `{"str": "s"}` |
| bool literal | `{"bool": true}` |
| string set literal | `{"set": ["a","b"]}` |
| variable | `{"var": "name"}` |
| and / or | `{"op": "and", "args": [ ... ]}` |
| not | `{"op": "not", "arg": ... }` |
| comparisons `= != < <= > >=` | `{"op": "<=", "left": ..., "right": ...}` |
| arithmetic `+ - *` | `{"op": "+", "left": ..., "right": ...}` |
| prefix_of | `{"op": "prefix_of", "left": ..., "right": ...}` (left is prefix of right) |
| in | `{"op": "in", "left": sexpr, "right": {"set": [...]}}` |

`obligation_id` = SHA-256 of the JCS bytes of this AST object. Evaluation is total: unknown variables, type errors, or malformed nodes yield verdict `error`.

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

**Coverage rule (normative, E1):** `from_seq` of checkpoint N equals the `seq` of checkpoint N−1; the first checkpoint's `from_seq` is 0; `to_seq` equals the checkpoint's own `seq` minus 1. Consequently every checkpoint Event is Merkle-covered by the *next* checkpoint. The final checkpoint is covered by the hash chain, its Event signature, and its own anchor over the root it carries. Verifiers MUST enforce contiguity: a gap or overlap between ranges is INVALID (`CKPT_RANGE`).

## 10. Anchoring (resolves M1, B3)

### 10.1 Pluggable backends

Anchoring policy is declared in `run_start` and the Pack manifest: `rekor`, `rfc3161`, or `both`.

- **`rekor`**: public transparency log (Rekor v2, tile-backed). Proof = log index, the canonicalized leaf, an RFC 6962 inclusion proof, and the log-signed C2SP checkpoint that proof resolves against. Rekor v2 returns no signed entry timestamp and no integrated time, so the log evidences MEMBERSHIP only; trusted time, when present, is a separate RFC 3161 token over the leaf signature. Property: public auditability. Cost: publicly observable activity metadata (rate, volume).
- **`rfc3161`**: timestamp token from one or more declared TSAs over the signed root. Property: private, cheap, standard. Cost: trust in the TSA(s); no public transparency.
- **`both`**: the composite backend. A single checkpoint anchor of `type: "both"` carries a `rekor` sub-block and an `rfc3161` sub-block, each the single-backend anchor block verbatim (its own `type` key included). The `rekor` leg evidences transparency-log membership; the `rfc3161` leg establishes trusted time bound directly to the signed Merkle root, and is the sole time source — the `rekor` leg MUST NOT carry its own RFC 3161 token, since two genTimes in one anchor leave the §10.3 binding time undeterminable and a Verifier MUST fail closed. A Verifier MUST verify both legs; a composite with both legs verifying is INCLUDED-TIMED and participates in §10.3. For a high-stakes deployment record `both` is RECOMMENDED, delivering public auditability and trusted time together in one anchor. A Producer that obtains only one leg MUST emit the surviving single-backend block unchanged rather than a partial composite (§10.2); a Producer that obtains neither emits an unanchored checkpoint.
- **`rfc3161-sim`** (E5): test backend for conformance vectors ONLY. A pinned anchor key signs `SHA-256(root ‖ gen_time)` under the tag `NOUS-TRACE/v0.2/anchor-sim`. Structurally equivalent to a TSA token with the ASN.1 layer removed. Production Packs MUST NOT declare `rfc3161-sim`; Verifiers MUST flag it whenever the Pack is not marked as a test vector.

A `rekor` anchor therefore has two outcomes carrying different assurance, and a Verifier MUST report them as distinct states rather than as one state with a note:

- **INCLUDED-TIMED**: inclusion verified AND an RFC 3161 token over the leaf signature verified. The checkpoint establishes a `T_anchor` and participates in §10.3.
- **INCLUDED-UNTIMED**: inclusion verified, no trusted time present. The range establishes no `T_anchor`, MUST be excluded from the §10.3 time bound, and MUST be reported as a gap.
- **TIMED-UNINCLUDED**: reached only under a declared `both` policy that delivered a surviving `rfc3161` leg alone. Trusted time is present and establishes a `T_anchor`, but transparency-log membership is absent. The range participates in §10.3, and the missing membership MUST be reported as a shortfall (§10.1.1) with no cause attributed.

An RFC 3161 token that is present but does not verify is NEITHER state: the anchor is invalid and the Verifier MUST fail closed. A Verifier MUST NOT attribute a cause to absent trusted time. It cannot distinguish a TSA outage from a Producer that omitted the TSA, and any Producer-side record of such a failure is unsigned, is not carried in the Pack, and can be omitted by a hostile Producer; the untimed path is therefore an inducible downgrade. The Verifier reports absence, never explanation.

`rekor` without a trusted-time token is NOT conformant for a high-stakes deployment record. Such deployments MUST carry a trusted-time token, directly or via `both` once that backend is available.

Verifiers MUST support both production proof types offline (pinned Rekor log key / pinned TSA certificate chains in the Pack). *As of v0.2.5 the reference Verifier and the Verifier embedded in emitted dossiers implement `rekor`, `rfc3161`, and the composite `both`.* A Verifier MUST reject an anchor type it cannot verify (fail closed) rather than skip it, and MUST report the TSA/log trust-root provenance it used: auditor-pinned roots are authoritative, and roots carried inside the Pack are operator-supplied and MUST downgrade the report.

### 10.1.1 Declared policy versus delivered anchors

The anchoring policy is declared twice, and the two declarations are not equally trustworthy. The `run_start` Event body is signed by the runtime key, is bound into the hash chain at seq 0, and is covered by the Merkle root of the first checkpoint and therefore by that checkpoint's anchor. The Pack manifest carries no signature and is not listed in `manifest.hashes`; it can be rewritten without invalidating anything.

A Verifier MUST treat the `run_start` declaration as authoritative and the manifest declaration as advisory, and MUST NOT resolve a disagreement between them in favour of the manifest.

When both carry a policy and the two disagree, the declared intent is not determinable and the Pack is malformed: a Verifier MUST fail closed with `RUN_START_ANCHORING` (§12.4). When either declaration is absent, no comparison is performed, so Packs produced before this revision verify unchanged.

A checkpoint whose anchor `type` differs from the declared policy is a SHORTFALL. The anchor itself verifies under its own backend rules and its evidence is not diminished by the divergence; what the Pack delivered is simply less than what the Producer committed to under its own key. A Verifier MUST report the shortfall, MUST NOT report it as an integrity failure, and MUST NOT return a clean verdict for a Pack containing one: the verdict is INTEGRITY-OK/INCOMPLETE with exit 10. An unanchored checkpoint (§10.2) delivers no anchor type, is not a shortfall, and is reported under §10.2.

A Verifier MUST NOT attribute a cause to a shortfall. It cannot distinguish a Producer that degraded to a surviving backend from one that never attempted the declared backend, and any Producer-side record of the difference is unsigned, is not carried in the Pack, and can be omitted by a hostile Producer. As with absent trusted time (§10.1), the shortfall is an inducible downgrade and is reported as absence, never as explanation.

A Verifier reporting a shortfall MUST NOT also report a structural gap that did not occur. Exit 10 carries more than one cause, and naming the wrong one is an assertion the evidence does not support.

### 10.2 Anchoring failure

Network failure → checkpoint emitted with `anchor: null`, retro-anchored by a later checkpoint over the same root. Unanchored ranges are reported as gaps, and weigh into the verdict per §13.

### 10.3 Time bounding (resolves B3)

Each anchor proof that establishes time carries an independent timestamp `T_anchor` (TSA genTime; for `rekor`, the genTime of the RFC 3161 token over the leaf signature, since Rekor v2 provides no integrated time). An INCLUDED-UNTIMED `rekor` anchor establishes no `T_anchor`: its range is not time-bounded and is reported as a gap under §10.2 rather than checked here. Let `tol` be the tolerance declared in `run_start` (default 600 s, MUST be ≤ 3600 s). The Verifier MUST check, for every Event in an anchored range:

```
T_prev_anchor − tol ≤ ts_wall ≤ T_anchor + tol
```

(with `T_prev_anchor` = anchor time of the preceding anchored checkpoint; for the first range, the lower bound is unchecked and reported). Violations are INVALID. Consequence: a Trace fabricated today cannot claim last January; its claimed times are contradicted by its own anchors.

## 11. Payload Store, classes, erasure (resolves B4)

Content-addressed store; key = `SHA-256(salt‖payload)`.

**Entry format (normative, E3):** one file per entry, filename = the salted hash in lowercase hex, path `payloads/<class>/<hash>`, content a JSON object `{"salt": "<hex 32 chars>", "media_type": "<IANA type>", "data": "<base64 payload bytes>"}`. Verifiers MUST recompute `SHA-256(salt‖payload)` and reject mismatches (`PAYLOAD_HASH_MISMATCH`).

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

### 12.4 Reason-code registry and ordering (E6)

Fail-closed ordering is normative: the reported reason is the FIRST failing check in §12.2 order. Registry (v0.2.4; `RUN_START_ANCHORING` added in 0.2.4, otherwise unchanged since v0.2.1): `SPEC_VERSION, TOLERANCE_INVALID, MANIFEST_FILE_HASH, KEYS_MANIFEST_SIG, KEY_ID_MISMATCH, OBLIGATION_MANIFEST_SIG, OBLIGATION_ID_MISMATCH, PROOF_ARTIFACT_MISSING, PROOF_ARTIFACT_HASH, ASSURANCE_INVALID, FLOAT_IN_SIGNED, INT_RANGE, EMPTY_TRACE, TRACE_ID_MIXED, SEQ_ORDER, HASH_CHAIN_BREAK, KEY_UNKNOWN, SIG_INVALID, STRUCT_NO_RUN_START, RUN_START_KEYS_HASH, RUN_START_OBL_HASH, RUN_START_TOLERANCE, RUN_START_ANCHORING, CKPT_RANGE, MERKLE_MISMATCH, CKPT_ROOT_SIG, ANCHOR_TYPE, ANCHOR_INVALID, TIME_BOUND_VIOLATION, KEY_EXPIRED, PAYLOAD_CLASS, PAYLOAD_HASH_MISMATCH, ASSIGNMENT_MISSING, ASSIGNMENT_REF_MISSING, ASSIGNMENT_PARSE, ASSIGNMENT_VARS_MISMATCH, OBLIGATION_UNKNOWN, OBLIGATION_REF_REQUIRED, OBLIGATION_REF_FORBIDDEN, VERDICT_MISMATCH, SALT_REUSE`. Wrong-tag signatures (E4) are indistinguishable from bad signatures by construction and are reported as `SIG_INVALID`.

## 13. Failure, Recovery, Residual Risk

- Producer crash: loss bounded by checkpoint policy; verdict INTEGRITY-OK/INCOMPLETE.
- Signer crash: run terminates; persisted state prevents counter reset.
- Anchor backends down: unanchored checkpoints, retro-anchoring, reported gaps.
- **Residual, declared:** (i) full-host compromise including the Signer → false Events forward of compromise, never behind an anchor; (ii) dishonest operator running an untraced parallel system — NOUS-TRACE evidences what the traced system did, not that nothing else ran; (iii) recorded-value fidelity (Non-claim 5); (iv) TSA collusion under `rfc3161`-only policy — mitigated by `both` or multiple TSAs.

## 14. Evidence Pack

`manifest.json` fields (normative): `spec_version`, `anchoring` (declared backend), `tolerance_s` (int, ≤ 3600), `trust_anchors` (hex raw public keys: `deployment_pub`, plus backend-specific: `anchor_pub` / `rekor_log_pub` / TSA chain refs), `hashes` (SHA-256 hex of `keys.json` and `obligations.json`; Verifiers MUST check).

```
manifest.json          as above
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
- tampering set: edited body (SIG_INVALID); dropped Event (SEQ_ORDER); reordered Events (SEQ_ORDER); post-anchor forged Event (ANCHOR_INVALID); reused salt (SALT_REUSE); verdict/assignment mismatch (VERDICT_MISMATCH); missing evidence payload (ASSIGNMENT_MISSING); wrong-tag signature (SIG_INVALID, per E4); expired-key signature (KEY_EXPIRED); back-dated `ts_wall` beyond tolerance (TIME_BOUND_VIOLATION); float in signed structure (FLOAT_IN_SIGNED);
- plus one truncated-tail vector yielding INTEGRITY-OK/INCOMPLETE, exit 10.

Each tampered vector MUST yield INVALID with the expected reason code under §12.4 ordering. The reference implementation passes 13/13.

*Scope of the shipped vectors (informative):* every vector above is fed to a Verifier and checked for verdict and reason code, so the set exercises Verifier conformance only. No vector exercises a Producer or a Signer obligation directly, and no Producer or Signer conformance regime is defined here. A Producer obligation therefore has no vector that can fail; §9's cadence went unimplemented from 0.2.0 to 0.2.5 for exactly this reason.

---

*Reference implementation status: complete for this version — self-contained Verifier, vector generator acting as reference Producer/Signer, 13/13 conformance vectors. Production anchor backends (RFC 3161, Rekor, and the composite both) and the standalone Signer process are implemented. Next: the AetherLang Producer adapter.*
