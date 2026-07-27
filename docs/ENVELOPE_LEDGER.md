# Envelope Ledger

The envelope ledger is the append-only, order-fixed commitment sequence over
governed-artifact checkpoints. It exists to make the HISTORY of what NOUS has
committed non-equivocable: a witness cosignature evidences that a pinned-key
holder attested a given append-only head, so a later divergent history is
detectable offline.

This document covers the shipped construction (commitment, leaf, log, store,
checkpoint, permanent origin) and the witnessing surface. It is the WHAT.
Companion design docs carry the derivations: `ENVELOPE_BINDING_DESIGN.md`
(commitment binding) and `COUNTERPARTY_WITNESSED_CONTINUITY_DESIGN.md`
(witnessed continuity).

## Honest boundary

- Witnesses attest append-only STRUCTURE (non-equivocation of the head), NOT
  content. A cosignature does not read, understand, or endorse any artifact.
- "proves" is reserved for Z3/Farkas. A cosignature EVIDENCES that the holder of
  a pinned key attested a head. Nothing here is "proven".
- The evidence layer is a MONITOR, not a guard. The ledger records; it enforces
  nothing at runtime. Runtime policy enforcement is separate (ADR-0010).
- The witness-key-to-operator binding is auditor-pinned and out-of-band. NOUS
  runs no CA and certifies no identity.
- Independence arrives ONLY when independent third-party witnesses cosign. An
  operator-run witness is a TEST HARNESS proving the mechanism and wire interop,
  not a trust root and not independence.

## Commitment

Each envelope entry is a 32-byte commitment binding the artifact AND its
temporal anchor:

    commitment = sha256(ENVELOPE_COMMIT_TAG || pce_sha256 || "|" || anchor)

where `ENVELOPE_COMMIT_TAG = b"nous.envelope.commit.v1|"`, `pce_sha256` is the
64-char PCE digest, and `anchor` is the anchor digest or the empty string when
absent. A distinct (envelope, anchor) pair yields a distinct commitment; the
identical pair yields the identical commitment (the dedupe target).

## Leaf

The raw Merkle leaf datum (pre-hash) is domain-separated:

    leaf_data = ENVELOPE_LEAF_PREFIX || commitment

with `ENVELOPE_LEAF_PREFIX = b"nous.envelope.leaf.v1\n"`. Leaves feed an
RFC 6962 tree; refuse-reorder is enforced downstream by the RFC 9162 consistency
proof (a later epoch whose prefix does not reproduce an earlier root fails
closed), not by the log object.

## Log

`EnvelopeLog` is append-only, deduped, and order-fixed. Dedupe is set semantics
on the commitment: a re-committed identical (envelope, anchor) is not a new fan
leaf. `order` is the append sequence; `order[0]` is the genesis commitment and
is permanent once the first commitment lands. `enumerate_fan()` is the auditor
enumeration -- every distinct commitment (hex) in append order -- where a
grinding fan becomes visible.

## Store

The operator-level append-only store is epoch-spanning (cross-build), NOT
per-dossier:

    $XDG_DATA_HOME/nous/envelope-log/log.jsonl
    (else ~/.local/share/nous/envelope-log/log.jsonl)

`load_log` rebuilds the `EnvelopeLog` from the JSONL, fail-closed on a malformed
record, skipping a commitment already present (a re-appended duplicate line
never inflates the fan).

## Checkpoint

`build_envelope_checkpoint` produces a C2SP signed-note checkpoint over the
current tree: origin line, tree size, base64 RFC 6962 root, signed by the
persistent log key. The log signature uses the standard C2SP/sumdb note
algorithm 0x01 (Ed25519). The note key id is:

    key_id = sha256(origin || "\n" || 0x01 || raw_pubkey)[:4]

The checkpoint log vkey (for witness registration) is:

    vkey = origin + "+" + hex(key_id) + "+" + base64(0x01 || raw_pubkey)

## Log origin (permanent)

The origin is the never-changing identity string a witness tracks forever. It is
constructed, and REGISTERED, as:

    origin = ENVELOPE_ORIGIN_PREFIX + order[0].hex()

with `ENVELOPE_ORIGIN_PREFIX = "nous-lang.org/envelope/"` -- always suffixed with
the genesis-leaf commitment hex.

The fixed production origin (as registered with the network and as emitted by the
code) is:

    nous-lang.org/envelope/5fe20ff38bf251d0d1d21865cced8d9e60cb808546dc27d608bee9c88701d4ff

The genesis commitment is a deliberate, documented genesis marker. Its leaf-0
preimage is the label `nous-lang.org/envelope genesis v1`; genesis PCE is
`sha256(label)` = `18d2755ac552ab87ffa8765ed78906b4b6b09a76228fa596aa3393699674a946`;
genesis commitment (with no anchor) =
`5fe20ff38bf251d0d1d21865cced8d9e60cb808546dc27d608bee9c88701d4ff`. Seeding a
deliberate genesis makes the origin a permanent constant rather than an accident
of whichever artifact happened to be first.

Why never-changing: witnesses track the exact origin string forever. Rotating
it, or registering a different string than the code emits, creates a new unknown
log and orphans (or breaks) the witnessed history. The registered origin MUST
equal the emitted origin or the witness rejects on origin mismatch -- this is why
the suffixed form is the one sent.

Rejected alternative -- the bare label `nous-lang.org/envelope`: rejected because
it is unreachable without patching the checkpoint construction, which would break
the S200 golden fixture and touch the fixed proven contract. The genesis-leaf
suffix was adopted; the bare label was rejected (not the reverse). The earlier
hash-suffixed TEST origin used during mechanism development was a test origin,
NOT this permanent production origin.

Honest framing for every surface: the envelope log is WITNESSED at the STAGING
tier by one independent, best-effort witness (k=1); auditor-pins the witness
keys; the production tier is not offered by the network. A cosignature EVIDENCES
non-equivocation of the head STRUCTURE, not content, and it never proves. Never
"member of"; never "production".
<!-- __s212_envelope_witnessed_staging_v1__ -->

ADR candidate -- promote to the ADR ledger at the post-release docs-hardening
milestone.

## Witnessing

The witness protocol is the C2SP tlog-witness protocol. The operator emits a
tlog-witness add-checkpoint request body and POSTs it out-of-band to the
witness's add-checkpoint endpoint; the witness returns a cosignature line. The
witness cosignature is key type 0x04 (cosignature/v1, Ed25519), which the shipped
verifier consumes without change. Cosignatures are assembled into an offline
sidecar and verified by the shipped offline verifier. A k-of-n witness quorum is
supported by the shipped witness verifier.

Registration targets the public Witness Network: an application fixes the origin
and the log vkey; a maintainer approves; participating witnesses periodically
pull the machine-readable list and auto-configure the log; a witness must not
remove or update an already-configured log, so the witness-from-genesis
constraint holds. Independence is a property of the real network join, not of any
operator-run witness.

## Emit surface

The `emit-request` CLI reads the operator append-only store, load-or-creates the
persistent XDG envelope-log key, builds the log-signed checkpoint, and writes
ONLY the add-checkpoint request body to `--out`. It is PURE: no network call (the
operator POSTs the body out-of-band). It writes only `--out`, never the store.
The returned 0x04 cosignature line(s) feed `build-witness --assemble-only`.

## Cross-references

- `ENVELOPE_BINDING_DESIGN.md` -- commitment binding derivation.
- `COUNTERPARTY_WITNESSED_CONTINUITY_DESIGN.md` -- witnessed continuity design.
- `CONTINUITY_LEDGER.md` -- continuity links, receipts, checkpoints.
- `PCE.md` -- the PCE digest the envelope commits.
- `REKOR_ANCHOR.md` -- Rekor v2 temporal backstop (complementary, not the
  non-equivocation root).
