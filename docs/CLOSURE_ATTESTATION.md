# Closure Attestation

A per-(policy, interval) witnessed completeness commitment over the operator's
own declared governed-action set. The operator signs a root that commits "under
policy P, interval T, this is the committed-complete set of governed actions,"
and -- when the Witness Network join is live -- has that commitment cosigned by
an independent witness so it cannot later equivocate on what it committed.

If a governed action that was in scope of policy P is later surfaced through any
other channel (discovery, a subject complaint, a second log) and is provably
ABSENT from the signed root, that action is inconsistent with the operator's own
signed completeness assertion. This is the cryptographic form of adverse
inference: the incrimination is pre-committed.

## Honest boundary (inviolable)

EVIDENCES: that the operator signed a completeness commitment over a specific
governed-action set for a specific (policy, interval); and, on challenge, that a
queried action is or is not in that committed set. A surfaced in-scope action
provably absent from the signed root is inconsistent with what the operator
asserted was complete.

Does NOT:

- prove the operator logged everything. You cannot prove a negative about the
  physical world. It evidences a COMMITMENT to completeness, not completeness.
- detect omissions on its own. It bites only when an omission surfaces through
  some other channel; it is a deterrent and accountability primitive, not a
  detection mechanism (the latent-evidence bound, stated).
- reach actions the operator never declared in scope of policy P. It binds the
  operator's own declaration; an action never claimed as governed was never
  claimed.
- prevent anything. NOUS is a monitor, not a guard.

"proves" is reserved strictly for Z3 cost bounds and Farkas certificates. Closure
attestation EVIDENCES the commitment and the inconsistency-if-surfaced. The
name-to-key binding is operator-asserted; the auditor pins the verifying key
out-of-band, and that identity check is the auditor's step.

## Structure (Increment A -- closure_ledger)

A key-indexed binary sparse Merkle trie (CONIKS/akd shape). The leaf for a
governed action lives at, and only at, the 256-bit position

    sha256(CLOSURE_KEY_TAG || sha256(policy_id) || action_id)

Non-membership is a proof that the position resolves to the EMPTY leaf, verified
against the committed root from (key, empty_leaf, co-path) alone. Because the
position is key-determined, absence is sound against a MALICIOUS operator with no
full-set rebuild and no sortedness assumption -- the threat model this arc exists
to bind. (A sorted-leaf compact non-membership is sound only against an honestly
built tree; it was spiked, proven unsound for this threat model, and discarded as
the primitive.)

The recording path is opt-in via NOUS_CLOSURE_LOG and writes nothing when that
variable is unset. The root is a pure function of the (policy_id, action_id) set:
append order is irrelevant, a re-added identical action is a no-op, and two ids
that collide to one 256-bit position refuse cause-first rather than silently
merge. Leaf, node, and empty digests carry distinct v1 domain-separation
prefixes so a closure leaf can never collide with an envelope, continuity, or
budget leaf.

## The attestation (Increment B -- closure_attestation)

A frozen-dataclass, per-(policy, interval) signed commitment over the ledger
root, plus the offline omission verifier. The persistent-key signature is an
operator ceremony: the signing key is loaded from disk under XDG or the call
refuses cause-first; it is never generated implicitly by a signing path, and the
module never signs at import.

Two independent incrimination paths follow from one signed body:

1. per-action non-membership: a surfaced in-scope action absent from the signed
   root.
2. aggregate count mismatch: a discovery surfaces more in-scope actions than the
   signed action_count.

Canonical body: plain sorted-keys compact JSON, excluding the signature envelope
(signature, vkey), exactly as the Manifest excludes its own signature. Optional
signed fields are drop-when-None, so an unwitnessed attestation stays
byte-identical to one that later carries witness and Rekor fields when those are
absent.

## Surface split (auditor-only vs public)

The signed Increment B body carries action_count, so the attestation DISCLOSES
the per-(policy, interval) governed-action VOLUME to any verifier. This is
deliberate: the count is the second incrimination path, and in the adversarial-
discovery setting the arc targets, the per-(P, T) count is discoverable anyway.

The public, witnessed surface (Increment C) commits ONLY
{policy_id, interval, root}. action_count NEVER enters the public commitment; it
lives solely in the auditor-only Increment B attestation. A surface-split
projection guard enforces this separation. The volume-privacy question therefore
bites only in the auditor-only body, never on the public witnessed surface.

## Witnessing status -- PENDING

Independent witnessing is NOT yet effective. It targets the staging tier of the
public Witness Network and is pending the network join -- the same join the
envelope ledger and the Predetermined-Change Envelope (PCE) wait on. Closure
rides the SAME envelope-log origin as PCE (one origin, one join): the closure
root is committed as a domain-separated tagged leaf (CLOSURE_COMMIT_TAG,
"nous/closure-root/v1|") on that single log, so its witness cosignature activates
on the SAME round trip -- no separate origin, no second join.

Current state of a first attestation: signed by the persistent operator key; the
independent witness cosignature is pending the round trip. Rekor anchoring of the
closure root is join-independent and available as a capability, but it is not the
witnessing this document defers, and it is not claimed here as performed. This
document does not claim independent witnessing exists. When the round trip lands,
the shipped verifier consumes the cosignature with no new release -- the
witnessed claim becomes a documentation update, not a version bump.

## Verification

Offline, with cryptography + stdlib only. The verifier is total: it ties a
closure root to the Increment B attestation and, when present, to a witnessed and
optionally Rekor-anchored envelope checkpoint, composing over envelope_ledger,
envelope_witness, rekor_v2_offline, and rekor_verify_v2 and reimplementing none
of them. No signing and no network occur on the verification path.

## See also

- [Envelope Ledger](ENVELOPE_LEDGER.md) -- the append-only commitment sequence
  the closure root rides.
- [Predetermined-Change Envelope](PCE.md) -- the other evidence leaf on the same
  origin.
- [Witness Provisioning](WITNESS_PROVISIONING.md) -- the persistent log key, the
  permanent origin, and the Witness Network join (staging tier; production not
  offered).
