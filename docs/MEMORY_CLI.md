# Memory CLI

`nous memory` is the command surface over the Phase 0 persistent-memory stack.
It makes the four memory modules (`memory_entry`, `memory_keyring`,
`memory_store`, `memory_index`) reachable from the command line.

The model in one line: signed, hash-chained, per-soul entry files are the
truth; the SQLite index is a derived, rebuildable lens that is never an
evidence anchor.

All four subcommands take `--base-dir` (default `/var/lib/nous`). Under that
directory the layout is:

```
<base-dir>/
  memory/<world_sha256>/signing.key          # per-world Ed25519 private key (0600)
  memory/<world_sha256>/genesis_keyring.json  # signed keyring genesis entry
  memory_log/<world_sha256>/<soul_sha256>/entry_<seq>.json  # signed chain entries
```

`<world_sha256>` and `<soul_sha256>` are 64-hex SHA-256 digests. The CLI
refuses any value that is not exactly 64 hex characters.

## init

```
nous memory init --world <world_sha256> [--base-dir DIR]
```

Explicit per-world signing-key ceremony. Generates a persistent Ed25519
keypair (PEM, mode 0600) and writes a signed genesis keyring entry. Prints the
public key and key id. Re-running on an already-initialized world is a no-op
(prints `Already initialized` and exits 0); it never overwrites an existing
key. This ceremony is the only path that creates trust material -- write paths
never auto-create it.

Exit codes: 0 on success or already-initialized; 1 on bad input.

## append

```
nous memory append \
  --world <world_sha256> --soul <soul_sha256> \
  --source-sha <sha256> --manifest-sha <sha256> --event-hash <sha256> \
  --outcome <label> --trigger-kind <label> --cost <string> \
  [--timestamp <iso8601>] [--base-dir DIR]
```

Appends a signed entry to the soul's chain. The previous-entry hash and the
next sequence number are recomputed from the verified chain, never trusted from
a stored value. The entry is signed with the persistent per-world key and
written atomically; an existing sequence file is never overwritten.

If `--timestamp` is omitted, the current UTC time is used.

Append refuses (exit 1) when the world is not initialized. In Phase 0 the
subject-binding hashes are passed explicitly; deriving them from a run is
Phase 1.

Exit codes: 0 on success; 1 on bad input or refusal.

## verify

```
nous memory verify --world <world_sha256> [--soul <soul_sha256>] [--base-dir DIR]
```

Recomputes and verifies chains from the signed bytes. With `--soul`, verifies
that one chain; without it, verifies every chain in the world. For each chain
it prints the entry count and the verified chain head, then prints the
canonical world memory snapshot hash.

A chain is rejected on any integrity break: a bad signature, a broken hash
link, a non-contiguous sequence, or a scope mismatch.

Exit codes: 0 when all checked chains verify; 2 on any integrity break; 1 on
bad input.

## reindex

```
nous memory reindex [--base-dir DIR] [--db PATH]
```

Rebuilds the derived SQLite index from the signed chains under `--base-dir`.
The index is a query lens only; it is rebuilt from the files and is never
consulted for a trust decision. `--db` defaults to
`/var/lib/nous/memory_index.db`. Prints the number of entries indexed and a
verify result (`ok`, `reason`, `checked`).

Exit codes: 0 on success; 1 on error.

## Offline verifiability

Every entry and every keyring genesis record is Ed25519-signed over canonical
bytes, so a third party can verify a chain offline with the `cryptography`
library alone, without a NOUS install and without the SQLite index.
