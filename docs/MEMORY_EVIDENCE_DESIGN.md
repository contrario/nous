# NOUS Memory Evidence -- Design (Phase 0 freeze)

Status: DESIGN FROZEN, pre-implementation. ASCII-only.
Audience: any future session implementing NOUS persistent memory.
Cross-reference from README.md alongside SMT_VERIFICATION_DESIGN.md and
HX-NOUS-API-HARDENING-DESIGN.md.

This document freezes the architecture so the decisions below are not
relitigated at implementation time. It defines what may be built in Phase 0
(pure signed evidence, zero execution influence) and reserves the schema and
invariants for the later phases that do influence execution.

---

## 0. Why this exists

Through S105 the system knows what was proven, what executed, what it cost, and
what it signed. It does not know what it learned. Persistent memory is the next
frontier. The hazard is that naive memory (RAG / vector blob, or a side-channel
store) breaks the property the whole project is built on: a run must be
reproducible from its signed, hashed inputs. If memory influences execution but
is not a hashed input, replay diverges and the Annex IV provenance chain is void.

The through line, restated for memory:
> deterministic evidence that travels with learned experience.
The goal is not memory that travels alongside the evidence; it is learned
experience that IS deterministic evidence. A run that consults memory stays
reproducible because the consulted snapshot is a hashed input, not a side
channel. Learning without loss of provability means memory inside the
determinism boundary, not beside it.

---

## 1. The central distinction (governs the whole schema)

Two different things, never conflated (axiom 8, no silent merges):

- evidence-of-learning: the system records what it learned. Append-only signed
  records. Additive, zero execution risk. This is all of Phase 0.
- learning-that-changes-behavior: memory consultation alters a run (e.g. heal /
  immune lookup applies a known remedy). This opens a hole in reproducibility
  UNLESS the consulted memory is a hashed run input. Phases 2+ only.

Corollary distinction inside an entry:

- observed_remedy: "in this run, after failure Y, heal-path X ran and the run
  then succeeded." A recorded observation. Signed. ADVISORY ONLY -- it is never
  auto-applied, because correlation in one run is not proof that X fixes Y.
- remedy_proof: "X provably keeps the run within the obligation that Y violated,
  discharged via SMT / conformance against this exact smt_spec_sha." A
  verification artifact. ONLY a remedy_proof may influence execution (Phase 2).

observed_remedy is the raw material; dreaming (Phase 3) takes observed remedies,
forms a hypothesis, runs it through the prover, and only on discharge promotes it
to a remedy_proof. The prover is the gate. "Refuse over guess" applied to
memory: an unproven hypothesis is never promoted, and remembering a failure (a
signed negative) is as valuable as remembering a success -- it is the immune
record.

---

## 2. Phasing (smallest reachable unit first)

| Phase | What | Execution influence | Reproducibility |
|-------|------|---------------------|-----------------|
| 0 | Signed hash-chained per-soul memory store; append-only; anchorable via the v5.23.0 trace-anchor path. Writes observed facts only. | none | unchanged |
| 1 | Deterministic memory consultation RECORDED in the trace (read-only; result captured; no behavior change). Proves the lookup is deterministic before it is allowed to matter. | none | unchanged |
| 2 | Memory as a hashed run input: add memory_snapshot_sha to the run SHAs. Consultation may influence heal / immune. Gated behind the Phase 1 determinism proof. | yes | new invariant |
| 3 | Dreaming: offline hypothesis -> SMT verification -> signed remedy_proof memory entry. | none directly | prover-gated |

Phase 0 is the only phase authorized by this document. Phases 1-3 require their
own design freeze before build.

---

## 3. Scope and provenance

Memory is per-world in SCOPE and per-soul-definition in CHAIN IDENTITY.

- Scope = per-world. Souls in a world share a single retrieval surface. Memory is
  environmental (the bloodstream / immune system), not genetic. This is why a
  clone benefits from an ancestor's experience without any inheritance-copy step
  at mitosis.
- Chain identity = per (world_sha, producing_soul_sha), where producing_soul_sha
  is the hash of the soul DEFINITION (mind / instinct / heal), NOT a runtime
  instance id.

Consequences of binding to the definition hash:

- Mitosis: a clone has the same source_sha, therefore the same chain. It reads
  and writes the ancestor's chain. Correct: it is the same learned agent, forked.
  Inheritance is achieved through definition-identity, not through copying.
- Definition edit: changing mind / instinct / heal changes source_sha, therefore
  forks a new chain. A soul whose definition changed is a different learned agent;
  its old memory was learned under different behavior. The old chain survives
  (append-only, never deleted) and stays verifiable, but the new definition does
  NOT inherit it automatically. Inheritance across a definition change requires an
  explicit signed "memory migration" attestation, never implicit (axiom 4, no
  implied round-trippability; axiom 8).
- Retirement: retiring a soul tombstones its chain (a signed tombstone entry, not
  a silent delete), leaving siblings untouched. Apoptosis as a recorded event.

Blast radius equals the provenance unit: a poisoned or compromised chain can be
quarantined or refused at the granularity of one soul, without invalidating the
rest of the world's memory.

---

## 4. Store architecture (hybrid: signed files = truth, SQLite = derived lens)

Source of truth and derived index are separated. The signed files are the
evidence; the SQLite database is a rebuildable lens. The direction is strict:
files -> SQLite, never the reverse.

```
SOURCE OF TRUTH  (signed, WORM-style append-only, anchorable)
  memory_log/<world_sha>/<producing_soul_sha>/
    genesis_head = H(world_sha || producing_soul_sha || "nous_memory_genesis_v1")
    entry[seq].json   # hash-chained, Ed25519-signed, append-only, ASCII
  chain head per soul = hash(latest entry) or genesis_head if empty
  memory_snapshot(world) = H( sort_by_soul_sha[ (soul_sha, head) ] )

DERIVED INDEX  (SQLite -- lens; never trusted for a boundary decision; rebuildable)
  /var/lib/nous/memory_index.db
    entries(world_sha, soul_sha, seq, event_hash, outcome, trigger_kind,
            cost, run_manifest_sha, has_observed_remedy, has_remedy_proof,
            entry_file_path, entry_sha)
    chain_heads(world_sha, soul_sha, head_sha)
  rebuilt by `nous memory reindex` purely from the signed files
```

Why this direction, and why not the reverse:

- Single source of truth, derived everywhere else (axiom 1). The signed chains are
  the source; the SQLite index is generated, like grammar_data.py from nous.lark.
  On disagreement the files win and the index is rebuilt.
- A writable SQLite file cannot be a stable evidence anchor: any read may mutate
  bytes (WAL checkpoint, journal), breaking its hash. A signed append-only file
  has frozen bytes, a stable hash, and is anchorable. The evidence therefore lives
  in the files; SQLite is only a lens.
- Index loss is not data loss. Losing the SQLite index means rebuild; losing the
  files means data loss. (Prior art: memweave -- separate storage from search;
  files are truth, the index is always rebuildable.)

Rules that the hybrid imposes (NOUS-specific, on top of the generic pattern):

- Boundary-internal consultation (Phase 2) reads ONLY the signed files. The
  SQLite index may be used to LOCATE candidate entries fast, but the decision path
  is: (a) query SQLite for candidate entry_file_paths, (b) read the signed file
  and verify Ed25519 + trusted-key membership + recompute event_hash, (c) only
  then apply. Recompute-never-trust: a derived row never decides; the signed bytes
  decide.
- memory_snapshot_sha is computed from the files, never from the SQLite index, so
  an auditor who rebuilds the index derives the same snapshot.
- Index drift detection: each entry file carries its own entry_sha; the SQLite row
  stores it. `nous memory verify` re-walks the files and compares; on mismatch the
  index is stale and is REBUILT, never trusted. Same posture as the regression
  harness: the derived form must match the source byte-for-byte or refuse.
- Append is fail-closed and atomic: write the signed entry file first (mkstemp,
  chmod 0644, os.replace), then update SQLite. If the SQLite update fails after the
  file is written, the file is the truth and the next reindex picks it up. Never
  the reverse (a SQLite-first design would surface evidence that does not exist in
  the files). If the file write fails, the run does not pretend it learned (refuse
  over guess).
- No embedding / vector column on the execution-influencing path. Probabilistic
  retrieval is forbidden inside the boundary (probabilistic extraction accumulates
  error). Exact-match deterministic lookup only (by event_hash, or by world+soul).
  Semantic search, if ever added, is a SQLite-side advisory feature OUTSIDE the
  boundary, layered over the signed store.

---

## 5. Phase 0 entry schema (frozen day 1)

Each entry is a signed governed artifact, an extension of the trace-envelope
pattern. The signature covers the canonical body excluding the signature field
(model_dump(exclude={"signature"})), as with TraceEnvelope. source_kind is the
discriminator, frozen now (axiom 8).

```
schema_version
source_kind            # "nous_memory_entry_v1" -- frozen
prev_entry_hash        # hash chain; genesis_head for the first entry
seq                    # monotonic per chain from 0 (deterministic, no UUID)
world_sha              # scope: which world
producing_soul_sha     # provenance: soul DEFINITION identity (survives mitosis)
source_sha             # the program that ran
run_manifest_sha       # the run that produced this entry
event_hash             # deterministic f(world_sha, source_sha,
                       #   producing_soul_sha, trigger_kind)
outcome                # success | failure  (failure = signed negative = immune)
trigger                # structured: error class / obligation id -- hashes,
                       #   never free text
cost
timestamp
observed_remedy        # optional recorded fact, ADVISORY ONLY:
                       #   {heal_path_sha, post_outcome, post_run_manifest_sha}
remedy_proof           # RESERVED, null in Phase 0; populated only by Phase 3:
                       #   {proof_kind, smt_spec_sha, world_sha, verdict,
                       #    proof_signature, rekor_anchor?}
signature              # Ed25519 over canonical body (exclude signature)
```

Notes:
- empty chain is not absent: an unwritten chain has an explicit genesis_head, not
  null, so "no memory" and "empty memory" do not get conflated (refuse over
  guess).
- entries carry only hashes and structured enums, never raw payloads or message
  content (confidentiality: signing is not encryption; same posture as dossier
  manifests).

---

## 6. Threat model and mitigations

| Threat | Mitigation (principle) |
|--------|------------------------|
| Memory poisoning (attacker writes an entry to alter future runs) | Phase 2 consultation verifies Ed25519 sig AND trusted-key membership (per-world authorized key set); recomputes claimed SHAs; unsigned / untrusted -> REFUSED, never consulted. Recompute-never-trust. |
| Stale remedy (proven for spec A, applied to spec B) | remedy_proof binds to the exact smt_spec_sha + world_sha it discharged; Phase 2 requires exact match; bounds are re-derived from the signed proof, not trusted from the body. |
| Forge / replay of a proof | remedy_proof is itself a signed verification artifact (canonical bytes, signature excluded), verified offline before consultation, anchorable via the trace-anchor path. |
| Confidentiality | entries carry hashes + structured outcomes only, never raw payloads. |
| Unbounded growth / DoS | retention is deterministic and auditable; pruning is a signed tombstone entry, NEVER a silent delete -- chain of custody survives. |
| Cross-world leakage | world_sha scopes reads; consultation filters and refuses entries from other worlds; the scope key is enforced on read and re-derived, not trusted. |
| Index tampering | SQLite is never trusted for a decision; boundary reads the signed file; drift -> rebuild. |
| Concurrency nondeterminism | per-soul chains confine ordering to a single chain; within a run a soul writes only its own chain in tick order; the per-world snapshot is a canonical sort of heads. Probabilistic writes, deterministic per-chain bytes (axiom 3). |

---

## 5a. Signing key provisioning

Memory entries are long-lived evidence consulted across runs, so they are
signed with a PERSISTENT per-world Ed25519 key, not the ephemeral per-run key
the trace path uses (axiom 7: long-lived signing uses persistent keys under
XDG; web-tier uses ephemeral per request). A per-run ephemeral key would make
the Phase-2 trusted-key-set check (the primary memory-poisoning mitigation)
vacuous: a fresh key per run leaves nothing stable for the trusted set to
anchor to. The trace can use ephemeral keys because a trace is self-contained
and verified once; memory is consulted across runs and needs a stable signer
identity for the trusted set to mean anything.

Scope: one signing key per world, at `keys/memory/<world_sha>/signing.key`
(0600). Per-world rather than global so cross-world isolation is cryptographic,
not merely a world_sha filter: world B's entries are signed by B's key, which
is not in world A's trusted set. Blast radius of a key compromise is one world.

Provisioning is an EXPLICIT, recorded ceremony, never a lazy side effect:

```
nous memory init <world_sha>:
  1. REFUSE if already initialized (idempotent: existing genesis -> no-op + report)
  2. generate persistent Ed25519 keypair -> keys/memory/<world_sha>/signing.key (0600)
  3. write a signed genesis keyring entry (the trusted-set root):
       {world_sha, public_key, created_at, key_id,
        source_kind: "nous_memory_keyring_v1", signature}
  4. report public_key + key_id
```

A memory write to an uninitialized world is REFUSED ("memory not initialized
for world X; run `nous memory init`"), never auto-created. Rationale, on the
principles already in force:

- Refuse over guess: auto-creating trust material as a side effect of a write
  is a guess; the system refuses on an uninitialized world instead.
- Key creation is a governed, recorded event (a signed genesis keyring entry),
  not an emergent artifact -- explicit delegation, not server authority. This
  is the root the Phase-2 trusted set is verified against.
- No race: one ceremony yields one genesis key; concurrent first-writes cannot
  produce two competing keys (axiom 1, axiom 8).
- The key is born in a deliberate CLI ceremony, not inside a serving run, so a
  freshly generated private key is never resident in an API process's address
  space (consistent with HX-NOUS-API-PROC-ENVIRON-EXPOSURE).

Rotation: the trusted set is a SET of public keys, not one. On rotation the old
public key REMAINS in the set (old entries stay verifiable; append-only evidence
is never retroactively invalidated) and a new key signs new entries. The set
grows; it never shrinks. This matches invariant 7 (nothing is ever deleted).

Phase 0 scope: the per-world key is used to SIGN entries and the public key /
genesis keyring entry is recorded. The trusted-set VERIFICATION machinery
(checking an entry's signer is a member of the world keyring) is Phase 2
(consultation), not Phase 0 (write). The keyring artifact's own governance --
where the keyring lives and how its authenticity is rooted (world-definition
hash vs a separately anchored keyring) -- is a Phase-2 prerequisite, deferred
here but reserved by the source_kind discriminator.

---

## 7. Frozen invariants

1. Memory is per-world in scope and per-soul-definition in chain identity. Clones
   share a chain (same source_sha); definition edits fork a chain; retirement
   tombstones a chain.
2. The per-world snapshot is a canonical roll-up of all chain heads, computed from
   the signed files, frozen at run start, and is the single anchorable and
   (Phase 2) hashed-input unit. Mitosis mid-run does not retroactively change a
   run's input snapshot.
3. Signed hash-chained per-soul entry files are the source of truth and the only
   thing consulted on the execution-influencing path. The SQLite index is a
   derived, always-rebuildable lens for advisory / dreaming queries and for
   locating candidates, never trusted for a boundary decision.
4. observed_remedy is a recorded observation; remedy_proof is a verification
   artifact; only remedy_proof may influence execution; the two are never
   conflated. An entry may carry observed alone (most failures), proof alone,
   both, or neither.
5. No embedding / vector retrieval on the execution-influencing path. Exact-match
   deterministic lookup only inside the boundary.
6. Append is fail-closed: if the signed entry cannot be written, the run does not
   record that it learned. File write precedes index update; the file is the
   truth.
7. Nothing is ever deleted. Pruning and retirement are signed tombstone entries.
8. Memory entries are signed with a persistent per-world Ed25519 key created by
   an explicit `nous memory init` ceremony that writes a signed genesis keyring
   entry; writes to an uninitialized world are refused, never auto-created; the
   keyring (trusted set) is the Phase-2 verification root and grows by rotation,
   never shrinks.

---

## 8. Closing-principle check

After Phase 0 lands: can a third party verify offline, with only cryptography,
that the system's recorded learning is authentic, attributed, and untampered? Yes
-- each entry is Ed25519-signed over canonical bytes, hash-chained for
tamper-evidence, and the per-world snapshot is anchorable to a transparency log
via the v5.23.0 path. Phase 0 widens the evidence surface (a new class of signed,
verifiable artifact) without touching execution, so reproducibility is unchanged.
Phases 2+ keep the answer yes by making the consulted memory a hashed run input,
so replay stays deterministic.
