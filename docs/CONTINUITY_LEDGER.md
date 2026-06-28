# Continuity Ledger

The continuity ledger is the third NOUS evidence type. It binds a sequence of
already-certified runs into a single, tamper-evident chain, then seals the chain
head under a transparency-log checkpoint that a third party can re-verify
offline with nothing but the Python standard library and `cryptography`.

It EVIDENCES that a contiguous sequence of conformance-certified runs occurred in
a fixed order under a fixed head, and -- when a budget envelope is present --
PROVES that the declared per-run cost caps sum within an authorized budget. It is
a monitor, not a guard: it enforces nothing at runtime and does not assert that
the runs shown are the only runs that occurred. Omission is not defeated; the
ledger evidences what is present.

## The honest boundary

- `proves` is reserved strictly for the Z3/Farkas cost bound. The only
  proves-leg in this stack is the budget envelope (Lock 2): a Farkas certificate
  in rational arithmetic showing `sum(declared caps) <= B`, checked offline with
  no solver.
- everything else `evidences`: Ed25519 signatures, the RFC 6962 Merkle root, the
  operator log signature, the witness cosignature, continuity links, and
  counterparty receipts.
- the checkpoint head is a C2SP tlog-checkpoint signed note. Cap-to-actual-cost
  fidelity is out of scope here (it remains EVIDENCES via the per-run certified
  trace).

## The chain

Each link wraps one certified run: `conformance.json`, `trace.json`,
`manifest.json`, and `link.json`, with an optional counterparty `receipt.jws`.
A link commits the prior link's digest, forming a single hash-chain from a fixed
genesis. The walk is fail-closed and single-chain: a fork, a gap, a broken back
reference, or a failed conformance leg aborts with a typed error and zero
fallback. The append-only property of the ledger comes from this hash-chain, not
from a Merkle consistency proof.

## The checkpoint head

`nous continuity checkpoint` walks the ledger, builds an RFC 6962 Merkle root
over the ordered link digests, and serializes a three-line C2SP checkpoint body:

```
nous-lang.org/continuity/<first-link-digest>
<tree size>
<base64 root hash>
```

Merkle hashing is RFC 6962 Section 2.1: a leaf is `SHA-256(0x00 || data)`, an
interior node is `SHA-256(0x01 || left || right)`, and odd nodes are promoted
(the tree is imbalanced, never Bitcoin-style duplicated). The note is signed by a
dedicated operator log key (a plain Ed25519 note signature, signed-note type
0x01); the key id is `SHA-256(name || 0x0A || 0x01 || 32-byte pub)[:4]`. This is
the operator's own key and is distinct from any conformance, counterparty, or
witness key.

The offline verifier re-walks the ledger, recomputes the root over the link set,
and refuses if the recomputed root or tree size does not match the signed note
(`Lock 1` -- the ledger head is fixed at this Merkle root; a substituted head is
caught).

## Budget envelope (opt-in)

With `--budget B`, the checkpoint additionally commits an aggregate cost bound.
Each link must carry a usable `cost_cap_usd`; an unpriced link under `--budget`
is a fail-closed refusal, never a fabricated zero. The producer writes a
canonical sidecar (`aggregate.cost.farkas.json`) holding the fragment tag,
version, budget, the ordered leaf digests, and the per-link caps, and emits a
budget extension line:

```
nous.aggregate.cost.farkas v1 budget=<B> leaf_set=<sha256(canonical order)> cert=<sha256(canonical sidecar)>
```

The offline verifier re-derives the Farkas certificate from the sidecar and
PROVES `sum(caps) <= B` in pure rational arithmetic (`Lock 2`). This is the only
proves-leg in the ledger.

## In-tree budget commitment (S180)

Before S180 the budget commitment lived only on the extension line. Two problems
follow on the post-quantum horizon: the C2SP ML-DSA-44 cosignature (signed-note
type 0x06) signs only the checkpoint root (it commits a structured message whose
sole digest is the root hash, not the note body and not extension lines), and
extension lines are not auditable by log monitors. A naive PQ upgrade would
leave the strongest mathematical evidence in the system -- the Farkas cost-cap --
outside post-quantum protection.

S180 binds the budget cert into the Merkle tree itself. When priced, the producer
appends one committed budget leaf:

```
leaf data = b"nous.budget.leaf.v1\n" || sha256(canonical sidecar)
leaf hash = SHA-256(0x00 || leaf data)
```

The priced tree is `[link_0 .. link_{n-1}, budget_leaf]`, so the tree size is
`n + 1` and the root now transitively commits the budget cert. A future 0x06
signature over the root therefore protects the cost-cap proof. The construction
is drop-when-absent: an unpriced checkpoint appends nothing, computes the
byte-identical root and note body it computed before S180, and verifies
unchanged.

Cross-bind: the same `sha256(sidecar)` feeds the extension `cert=`, the sidecar
file, and the in-tree leaf, so `extension cert == in-tree leaf digest ==
sha256(sidecar file)`. A budget-cert substitution now flips the root and fails
`Lock 1`, before the `Lock 2` cert check -- escalating a budget tamper from
Lock-2-only to Lock-1+Lock-2.

The budget extension line is preserved (the Lock-2 extension lane is unchanged);
its deprecation, and repointing Lock 2 to read the in-tree leaf, are deferred to
the gamma (PQ dual-sign) window.

Forward-compatibility: the trailing budget leaf means a priced checkpoint tree is
not an RFC 6962 prefix of a later priced tree. This regresses nothing shipped
(append-only evidence is the link hash-chain; no consistency-proof leg exists).
A future witnessed-liveness ribbon must run its consistency proof over the link
sub-tree, not the full tree.

## Append-only continuity (S183)

Single-checkpoint verification fixes one head; it cannot detect that an
earlier, already-witnessed head was later rolled back, rewritten, reordered, or
truncated. The append-only leg closes that gap with an RFC 9162 Merkle
consistency proof between two rail checkpoints.

`build_continuity_proof(ledger_dir, prior_checkpoint_path, out_path)` walks the
current ledger, parses the prior checkpoint, and refuses cause-first on any of:
a priced (extension-bearing) prior (rail scope only), an origin mismatch
(different log), `prior.tree_size > current size` (rollback/truncation), or a
prefix root that does not reproduce the prior root (rewrite/reorder). When all
gates pass it writes an unsigned `continuity.proof` carrying the two tree sizes,
both roots, and the consistency hash path -- and nothing about the leaves, which
is the offline-auditor position.

The standalone offline verifier consumes it with `--prior-checkpoint` (also
surfaced as `nous continuity verify --prior-checkpoint`): it parses the prior
checkpoint, reads `continuity.proof` from the ledger dir, recomputes the current
rail root from the walked link set, cross-checks both sizes and both roots
against the proof, and runs `verify_consistency`. On success it prints
`EVIDENCES: Cryptographic consistency proof verified. ...`.

Honest boundary. The proof EVIDENCES append-only structure between two roots. It
does not, alone, defeat split-view equivocation (that requires the witness
quorum), and it does not detect never-logged omission. No new proves-leg: the
consistency math is Merkle structure, not a cost bound.

Rail scope. A priced checkpoint's leaf stream is `[link_0 .. link_{n-1},
budget_leaf]`, so the trailing budget leaf interleaves and naive prefix
consistency over two priced signed roots does not hold. Rail checkpoints (signed
root == link-only root) are consistency-clean; priced-checkpoint continuity is a
banked tree-reshape sub-arc.

Root-anchoring invariant. PQ-witnessable evidence lives under the Merkle root,
never on an extension line. A 0x04 Ed25519 cosignature signs the whole
checkpoint note body, including extension lines; a 0x06 ML-DSA-44 cosignature
signs only the root and excludes extension lines. So any evidence that must
survive post-quantum witnessing -- the budget cost-cap proof above all -- is a
committed in-tree leaf under the signed root (S180), not an extension line. The
consistency proof runs over rail roots, which are exactly the link-only roots a
future 0x06 signature will protect.

<!-- __s183_continuity_appendonly_doc_v1__ -->

## Segment in-envelope conformance (S185)

Layered on the S183 consistency proof, the segment in-envelope leg PROVES that
every run appended across the witnessed segment stayed inside its own declared
envelope. When a prior checkpoint and a verified consistency proof establish the
ledger as an append-only extension from tree size `m` to `n`, the verifier
checks, for every appended link in `[m, n)`, that the link's conformance
certificate is `conformant == True` (and `bound_transfer_ok == True`). Any
appended link that is not fails the verification closed; on success the verifier
prints a `PROVES:` line.

This earns `proves` because the verdict is read from root-committed bytes, not
from a sidecar. Each certificate's body digest is bound into the leaf through
`cert_body_sha256 -> run_identity_digest -> this_link_digest`, and the link
digests are the leaves of the signed Merkle root. The check is therefore boolean
arithmetic over data the signed root already commits -- no solver, no new
dependency in the offline verifier.

Enforcement, not restatement. The ledger walk records, but does not gate, a
self-consistent non-conformant run (NOUS is a monitor: it records what happened,
including a run that honestly reports `conformant == False`). This leg adds
segment-scoped enforcement: it refuses the `PROVES:` line and fails the
verification when the consistency-proven append contains an honestly-recorded
non-conformant run.

The honest boundary. It PROVES the witnessed segment is conformance-certified
`bound_transfer_ok` under the signed root, and EVIDENCES (unchanged) that the
segment is the actual append via the S183 consistency proof. It does NOT prove
that the declared cost ceiling did not rise across the segment; cap-value
monotonicity would require the cost cap value itself to be committed under the
root (it is currently sidecar-only) and remains future work.

Under `--json` the verifier emits a drop-when-absent `segment_inenvelope` object
(`prior_tree_size`, `current_tree_size`, `proven`) alongside the `consistency`
object; both are `null` when no prior checkpoint is supplied.
<!-- __s185_segment_inenvelope_doc_v1__ -->

## Witness cosignature (S179)

The checkpoint head can carry an independent, timestamped Ed25519 cosignature
(C2SP tlog-cosignature, signed-note type 0x04) from a key-isolated witness or
counterparty. It EVIDENCES that a named party observed this head at a stated
time. Key separation is structural: cosigning is a distinct action signed with
the witness's own private key; the checkpoint producer never holds a witness key.

The verifier must be pinned to the expected `(name, key)`: the 0x04 cosignature
signed message does not commit the cosigner name (only the 4-byte key id binds
it), so reading the name off the line is unsound. `--witness-key` therefore
fail-closes without `--witness-name`. The cosignature key id is
`SHA-256(name || 0x0A || 0x04 || 32-byte pub)[:4]` -- the same formula as the
operator log key but with type byte 0x04, a sibling that never collides with the
0x01 operator key.

## CLI surface

The `nous continuity` subparser exposes six actions: `link`, `receipt`,
`verify`, `emit-verifier`, `checkpoint`, and `cosign`. Key handling is
structural, not procedural -- an action that must not hold a private key does not
expose the option to:

- `link` -- chain a certified run onto the ledger; holds no signing key
  (the only action with no `--key` option).
- `receipt` -- a counterparty signs a per-link receipt with its own private key.
- `cosign` -- a witness/counterparty signs the checkpoint head with its own
  private key, producing a 0x04 cosignature line.
- `verify` -- takes only public keys.
- `checkpoint --ledger <dir> --log-key <pem> [--budget <B>]` -- build and sign
  the head (and the optional budget envelope).
- `emit-verifier --out <dir>` -- write the standalone zero-NOUS offline verifier.

For exact flags of each action, run `nous continuity <action> --help`.

The emitted offline verifier (`verify_continuity_offline.py`) takes the ledger
directory plus `--key` (counterparty public key), `--iss`, `--aud`, `--log-key`
(operator log public key), optional `--witness-key` and `--witness-name`, and
`--json`. It depends only on the standard library and `cryptography`, and returns
0 on PASS, 1 on FAIL (with a JSON `verdict`/`error` on stdout under `--json`),
and 2 on an environment or usage error.

## Forthcoming: gamma (post-quantum dual-sign)

The next step is a dual Ed25519 + ML-DSA-44 (FIPS 204; signed-note type 0x06)
signature over the checkpoint, backward-compatible because clients ignore unknown
signatures. Because 0x06 signs the root, S180's in-tree budget leaf places the
cost-cap proof under that future signature. The library-surface question is now resolved: `cryptography` exposes ML-DSA
(FIPS 204) through `hazmat.primitives.asymmetric.mldsa` when built against
OpenSSL 3.5+ (shipped March 2026), AWS-LC, or BoringSSL, so ML-DSA-44
verification is available under the stdlib + `cryptography` invariant with no new
dependency. Because a third-party auditor's `cryptography` build is not under
NOUS control, the offline verifier capability-gates the 0x06 leg: it verifies the
ML-DSA-44 cosignature when the local `cryptography` exposes `mldsa`, and otherwise
reports that leg un-checked rather than failing -- the Ed25519 legs (0x01
operator, 0x04 witness) always verify. ML-DSA-44 is NIST Level 2 (1312-byte
public key, 2420-byte signature); its cosignature key id is
`SHA-256(name || 0x0A || 0x06 || 1312-byte pub)[:4]`, and the note line is
drop-when-absent on size.
