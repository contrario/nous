# Memory Phase 2 Design Freeze: remedy_proof Influences Execution

Status: SEALED design freeze. No code. This document settles the frontier
questions for Phase 2.0 before any unit is authored (prove-before-build).

Phase 0 recorded memory. Phase 1 let a run consult memory and recorded the
consultation inside the signed trace, without letting memory change what the run
does. Phase 2.0 crosses that line for the first time, under the narrowest lever
that keeps the static envelope proof valid without re-proving: a verified
remedy_proof may PROMOTE an already-declared heal rule to first attempt. Nothing
else.

---

## 1. The lever: promotion-only

On a recoverable error, if verified memory carries a remedy_proof bound to (this
trigger class, this heal_path digest) and the CURRENT program declares a heal
rule with that digest, the runtime promotes that already-declared rule to be
tried first. The lever does ONLY this:

- It reorders the attempt sequence among rules the program author already
  declared and the validator already accepted (S003: every soul must define a
  heal block).
- It adds nothing, removes nothing, mutates nothing: no new rule, no changed
  guard, no changed retry count, no change to any law on the heal block.

Promotion changes the ORDER of attempt. It does not change what is attemptable.

---

## 2. The closure argument (load-bearing)

Promotion is admissible because it is closed under the static envelope proof.

The SMT cost bound is universally quantified: it proves total_cost <= cap for
ALL execution paths, where the path set is bounded by max_ticks and the soul
count. Promotion only selects among paths that are already reachable and already
bounded by that proof; it introduces no new path. The set of reachable behaviors
is therefore invariant under promotion, and the bound continues to hold WITHOUT
re-running the solver.

This is the precise property that makes Phase 2.0 admissible under the closing
axiom: after promotion lands, a third party can still verify offline, with only
cryptography and z3-solver, that the run stayed inside its declared envelope,
because the envelope obligations are re-proven independently of the remedy. A
forged, stale, or malicious remedy_proof cannot move the run outside its
envelope; the worst it can do is reorder legal recoveries. This mirrors the
proof-carrying code property: a tampered proof yields an outcome that is either
invalid (rejected by the gate) or harmless (still inside the safety policy). The
trusted base is the checker, not the producer of the proof.

---

## 3. Why retry-count tuning is rejected

Retry-count tuning is excluded not out of conservatism but because it is a
different category of change.

The retry count is a quantity the cost proof is parametrized over. Changing it at
runtime either takes the run outside the proven envelope, or forces runtime
re-proving. Runtime re-proving breaks "formation before execution" -- the exact
property that makes the dossier admissible: the proof is formed once, before the
run, and travels with it. Promotion changes the order of attempt; tuning changes
a proven quantity. Only the first is free. The trade is bad: small user value
(latency or cost the envelope already caps) against a large architectural cost.
Tuning may be revisited only if gated behind an explicit cost re-proof; that is
out of scope for 2.0.

---

## 4. User value

Promotion is not a weak lever; it captures exactly the reason memory exists:
"last time, for this trigger, the fallback worked better than the retry -- try it
first." If the promoted path succeeds, the known-bad path never runs. The only
lost value is the case where the promoted path's guard fails and the run falls
back to retry -- which is correct, conservative behavior, not a regression.

---

## 5. Frontier questions

### FQ1 (SEALED): the canonical heal-path digest does not exist today; Phase 2 defines it

Verification against live v1 bytes established that heal_path_sha256 is a
declared field on ObservedRemedy with NO producer anywhere in the codebase: no
function computes it. Phase 2 must define the digest. This is therefore a sealed
design decision, not an assumption.

DECISION: heal_path_sha256 is the sha256 of a NORMALIZED AST PROJECTION of a
single HealRuleNode:
- Project the HealRuleNode (with its HealActionNode and HealStrategy) to a
  deterministic JSON document.
- EXCLUDE all positional and source-location metadata and any non-semantic
  fields; include only the fields that define the recovery's meaning.
- Canonicalize JCS-style: sort_keys=True, separators=(",", ":"), UTF-8.
- sha256 over those bytes.

RATIONALE: the digest must be stable across source reformatting and across
codegen and release changes, and recomputable by the current program at match
time so matching is deterministic. This is the same discipline as the S107
NAME-BOUND identity: the digest's meaning is orthogonal to incidental
representation.

REJECTED ALTERNATIVES:
- Source span: whitespace- and comment-fragile; a reformat would change the
  digest of an unchanged recovery.
- Generated Python: codegen-version-fragile; a codegen change would change the
  digest across releases.

OPEN SPIKE (U1 prerequisite, prove-before-build): enumerate the semantic field
set of HealRuleNode / HealActionNode / HealStrategy from a live parsed repr()
before authoring the digest function. The projection's field selection is
derived from live bytes, never assumed.

### FQ2 (SEALED): conflict resolution is refuse-on-conflict

Two verified remedy_proofs for the same trigger class that would promote
DIFFERENT heal paths is a conflict. Resolution: refuse, fail-closed. The run
proceeds as if no remedy applied (default attempt order), and the refusal is
surfaced. Most-recent-by-chain-order is explicitly NOT chosen: automatic
selection among conflicting remedies requires auditor validation first, and is
deferred. This preserves the refuse-over-guess axiom and keeps determinism: the
outcome of a conflict is defined, not guessed.

### FQ3 (SEALED): promotion respects guards

Promotion changes the order in which declared heal rules are tried; it does not
gate. A promoted rule does not fire if its own guard fails. If the promoted
rule's guard fails, the runtime falls through to the next rule in the (now
reordered) sequence, exactly as it would without promotion. Promotion is
preference, never bypass.

### FQ4 (SEALED): default OFF, opt-in, drop-when-None recording

The lever is opt-in, default OFF, surfaced as a flag on the run path in the
shape of --consult-memory (the precise surface name is a unit decision, not a
freeze decision). With it off, runs behave exactly as before and produce
byte-identical traces. The application is recorded in a new optional signed
trace field, TraceEnvelope.remedy_application, a sibling of memory_consultation,
carrying the SAME drop-when-None write-path invariant: the member is dropped
from BOTH canonical_body_bytes (signer) AND every persisted/wire serializer
(persisted_dict) when None. A non-applying run is byte-identical to prior
releases; every shipped signature stays valid; the key-agnostic offline verifier
accepts applying and non-applying traces unchanged. Regression 0.

---

## 6. Storage backward compatibility (verified, not assumed)

Confirmed from live v1 bytes (memory_entry.py):
- canonical_body_bytes() = model_dump(exclude={"signature"}) then
  json.dumps(sort_keys=True, separators=(",", ":")). It excludes ONLY the
  signature field.
- observed_remedy and remedy_proof are therefore inside the signed body in v1.
- The module documents remedy_proof as reserved, null in Phase 0, the only field
  intended to carry future content.

CONSEQUENCE: "zero schema change" is scoped to STORAGE and holds. The
heal_path_sha256 digest is a DERIVATION Phase 2 introduces, not a new stored
field; its field slot already exists on ObservedRemedy. Phase 2 begins WRITING
the already-signed optional fields (observed_remedy.heal_path_sha256 and
remedy_proof) where Phase 0 left them null. Writing a previously-null optional
field that is already part of the signed body does not change the schema version:
new entries that populate them are valid v1 entries, and old entries with them
null remain valid. No MemoryEntry schema bump.

The stored remedy_proof stays Optional[dict] (untyped) so existing v1 entry
signatures are preserved bit-for-bit. A typed consumption view, RemedyProof
(strict, frozen, extra=forbid), is parsed on read, refuse-over-guess; it never
re-types the stored field.

---

## 7. Recording and verification design (TCB held constant)

remedy_application records, at minimum: world_sha256, producing_soul_sha256, the
source entry's seq, the remedy_proof sha256, the selected heal_path digest, and
an applied-at timestamp. The exact field set is a unit decision; the invariant is
that the record is a commitment sufficient for an offline third party to:

1. Read the source chain entry for (world, soul).
2. Recompute the remedy_proof sha256 and compare.
3. Re-verify the remedy_proof using the EXISTING offline conformance verifier
   (the S97 / v5.13 machinery): no new cryptography, no new trusted code.
4. Confirm the selected heal_path digest is one the current program declares
   (recompute the digest of each declared HealRuleNode and match).

If all hold, the run provably was influenced by exactly that proof, and the
influence was a legal reordering of declared recoveries. The trusted base is the
existing checker; Phase 2 must not grow it. This is the proof-carrying-code
discipline: trust the checker, not the producer.

---

## 8. Out of scope for Phase 2.0 (named, not silently deferred)

- The runtime conformance certificate gains no remedy obligation in 2.0; the
  signed certificate is untouched. A certificate-level remedy obligation is
  deferred to Phase 2.1.
- Retry-count tuning, gated behind an explicit cost re-proof, is deferred.
- Automatic selection among conflicting remedies (lifting FQ2's refuse) is
  deferred behind auditor validation.
- Multi-soul remedy application follows the same single-soul Option (c)
  restriction as Phase 1 until Phase 1.x lifts it.

---

## 9. Closing principle

Phase 2.0 moves the determinism boundary again: for the first time, memory
influences a run. It is admissible because the influence is closed under the
static envelope proof -- promotion selects among already-reachable, already-
bounded paths and adds none, so the universally quantified cost bound holds
without re-solving, and the run re-proves its own envelope independently of the
remedy. A third party can verify offline, with only cryptography and z3-solver,
both that the run stayed inside its declared envelope and that the only memory
influence was a verified, legal reordering of declared recoveries. The feature
widens the determinism boundary; it does not regress it. Phase 2.1 (certificate
remedy obligation) gets its own design freeze first.
