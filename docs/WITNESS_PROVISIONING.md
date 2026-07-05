# Witness Provisioning

How the envelope ledger is witnessed: the persistent log identity, the permanent
origin, the genesis-at-zero constraint, and the public Witness Network join. This
is the operational companion to `ENVELOPE_LEDGER.md` (which carries the
construction) -- the WHO and HOW-TO-JOIN, not the WHAT.

## Honest boundary

- A witness cosignature EVIDENCES that the holder of a pinned key attested an
  append-only head. It is not a proof; "proves" is reserved for Z3/Farkas.
- Witnesses attest append-only STRUCTURE (non-equivocation), NOT content.
- Independence is a property of the real network join, not of any operator-run
  witness. An operator-run witness (operator-internal) is a TEST HARNESS proving
  the mechanism and wire interop; it is explicitly NOT a trust root and NOT
  independence, and it does not evidence witnessed non-equivocation.
- The witness-key-to-operator binding is auditor-pinned and out-of-band. NOUS
  runs no CA.
- The highest honest public claim is STAGING-tier witnessing (see Tiers). Never
  "member of"; never "production".

## Persistent log identity

The envelope log is signed by a PERSISTENT Ed25519 key under XDG, not an
ephemeral ceremony key:

    ~/.local/share/nous/keys/envelope-log.key   (PKCS8 PEM, mode 0600)

loaded via `manifest.load_or_create_keypair`. This is the production log identity
that registers with the witness network. A key rotation invalidates the log vkey
and therefore the registration; treat the key as long-lived.

## Permanent origin

The origin is the never-changing string a witness tracks forever. Construction,
the fixed production value, and the rejected bare-label alternative are in
`ENVELOPE_LEDGER.md` (Log origin (permanent)). Summary of the commitment:

- fixed production origin (registered + emitted):
  `nous-lang.org/envelope/5fe20ff38bf251d0d1d21865cced8d9e60cb808546dc27d608bee9c88701d4ff`
- it is genesis-leaf-derived; the registered origin MUST equal the emitted origin
  or the witness rejects on origin mismatch.
- rotating it orphans the witnessed history. One-way commitment; ADR candidate.

## Genesis at zero

A witness attests the append-only history only from the point it STARTED
cosigning; it does not attest retroactively. Therefore the production log must be
established AT GENESIS (size 0 -> the genesis checkpoint is the first the witness
sees), so the publishable witnesses attest the full history from the start.

Genesis-witnessing is free ONLY while the store is ABSENT. The store is:

    $XDG_DATA_HOME/nous/envelope-log/log.jsonl
    (else ~/.local/share/nous/envelope-log/log.jsonl)

Establish the production genesis under the fixed origin BEFORE the store
accumulates any bytes. Dogfooding real bytes first would grow the log to size N,
and network witnesses joining at N would never attest the genesis prefix.

## Log vkey

The log registers with a C2SP signed-note verifier key (key type 0x01 Ed25519,
name == origin). Derivation (key id, vkey format) is in `ENVELOPE_LEDGER.md`
(Checkpoint). The vkey is signature-free and store-free: it is a pure function of
the fixed origin and the persistent public key, so deriving and printing it is a
read-only operation.

## The public Witness Network join

Registration is a maintainer-approval gate, not a per-witness contact:

1. Send a log participation request to `participate@lists.witness-network.org`
   with the origin line, the log vkey, the add-checkpoint rate, the target tier,
   and a contact. First posts are held for the list moderator (non-member hold);
   do not re-send.
2. A community maintainer reviews and approves.
3. The log is added to a machine-readable list.
4. Participating witnesses periodically pull the list and auto-configure the new
   log. No per-witness contact.

Append-only guarantee: a witness MUST NOT remove or update an already-configured
log when the list changes. Maintainers cannot disrupt past configs, so the
witness-from-genesis constraint holds by construction.

Cosignatures: witness cosignatures are key type 0x04 (cosignature/v1, Ed25519),
which the shipped verifier consumes without change. There is NO code change to
consume real-network cosignatures; the join is config-level provisioning of
pinned witness keys.

## Tiers

The production list is NOT available. Available tiers are `testing` (dev /
short-lived) and `staging` (real usage, dogfooding). The highest honest public
claim is therefore STAGING-tier witnessing. Every public surface must say
"staging" precisely and must not claim "production Witness Network".

## Fallback

If the network declines: recruit independent litewitness peers (the same C2SP
tlog-witness protocol, different keys and different operators). The honest
boundary is unchanged; independence comes from operator-distinctness. Operator-
internal witnesses are REJECTED -- an operator witnessing its own log voids the
non-equivocation property.

## Operational sequence

1. Fix the permanent origin (done; see `ENVELOPE_LEDGER.md`).
2. Establish the production envelope log at genesis with the persistent key under
   that origin (store ABSENT -> free).
3. Derive the log vkey (read-only) and send the staging application.
4. On acceptance: run the emit-request -> POST -> real network cosignature ->
   assemble -> shipped offline verifier round trip. A green assembled verifier
   over a REAL network cosignature is what promotes the claim from "targets
   staging" to witnessed non-equivocation at staging tier. DONE for the envelope
   genesis leaf: the round trip was run against one independent best-effort
   witness (k=1) and verified GREEN, so the envelope log is witnessed at staging
   tier. A closure root is NOT yet witnessed -- no shipped command appends a
   closure leaf to a checkpoint; that is a future produce-path increment.
<!-- __s212_wp_roundtrip_done_v1__ -->

## Cross-references

- `ENVELOPE_LEDGER.md` -- commitment, leaf, log, checkpoint, permanent origin,
  vkey derivation, emit surface.
- `COUNTERPARTY_WITNESSED_CONTINUITY_DESIGN.md` -- witnessed continuity design.
- `REKOR_ANCHOR.md` -- Rekor v2 temporal backstop (complementary, not the
  non-equivocation root).
