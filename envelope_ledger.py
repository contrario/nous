"""nous envelope ledger: append-only, deduped commitment log of every
predetermined-change envelope bound through NOUS, for one operator.

S193 Inc A of the envelope non-equivocation arc. __s193_envelope_ledger_module_v1__

DARK SUBSTRATE. This module supplies the enumerable, root-committed,
consistency-clean leaf domain the witness quorum (a later increment) makes
non-equivocable. The CLI path calls append_commitment only: it records a
commitment into an append-only per-operator store. It builds NO checkpoint,
contacts NO witness, and imports NO Merkle/network code on that path.

Honest boundary (inviolable). This module EVIDENCES that a commitment was
appended to a single append-only history; it is NOT non-equivocation (a lone
operator-signed head is defeated by split-view; only a witness quorum closes
that, in a later increment). Enumeration is bounded to envelopes committed
THROUGH NOUS for the epoch; off-log / out-of-band pre-commitment is out of
scope. It PROVES nothing: "proves" stays reserved for Z3 cost bounds and Farkas
certificates. NOUS is a monitor, not a guard.

Determinism. A distinct (pce_sha256, pce_anchor_sha256) pair maps to a distinct
32-byte commitment; a re-committed identical pair is a no-op (set semantics, not
a bag) so it is never a spurious fan leaf. The absence of an anchor is a
distinct, honest value (empty), never fabricated.

Domain separation. The Merkle leaf datum ENVELOPE_LEAF_PREFIX || commitment is
prefixed so it can never collide with a continuity link leaf (a raw 32-byte
digest, no prefix) or the S180 budget leaf (b"nous.budget.leaf.v1\n" prefix).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Optional


ENVELOPE_ORIGIN_PREFIX: str = "nous-lang.org/envelope/"
ENVELOPE_LEAF_PREFIX: bytes = b"nous.envelope.leaf.v1\n"
ENVELOPE_COMMIT_TAG: bytes = b"nous.envelope.commit.v1|"
LEDGER_SCHEMA_VERSION: int = 1
_SIG_LINE_PREFIX: str = "\u2014 "


class EnvelopeLedgerError(RuntimeError):
    """Raised cause-first on a schema, dedupe, order, or store violation."""


def default_store_path() -> Path:
    """Operator-level append-only store, mirroring manifest.default_key_path:
    $XDG_DATA_HOME/nous/envelope-log/log.jsonl, else
    ~/.local/share/nous/envelope-log/log.jsonl. Epoch-spanning (cross-build),
    NOT per-dossier."""
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        root = Path(base) / "nous" / "envelope-log"
    else:
        root = (Path(os.path.expanduser("~"))
                / ".local" / "share" / "nous" / "envelope-log")
    return root / "log.jsonl"


def _require_sha256_hex(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise EnvelopeLedgerError(
            name + " must be a 64-char sha256 hex string, got: " + repr(value)
        )
    try:
        int(value, 16)
    except ValueError:
        raise EnvelopeLedgerError(name + " is not valid hexadecimal: " + repr(value))
    return value


def envelope_commitment(
    pce_sha256: str, pce_anchor_sha256: Optional[str]
) -> bytes:
    """32-byte commitment binding the envelope AND its temporal anchor.

    sha256(TAG || pce_sha256 || "|" || (pce_anchor_sha256 or "")). A distinct
    (envelope, anchor) pair yields a distinct commitment (a distinct fan leaf);
    the identical pair yields the identical commitment (the dedupe target).
    """
    _require_sha256_hex("pce_sha256", pce_sha256)
    anchor_b = b""
    if pce_anchor_sha256 is not None:
        _require_sha256_hex("pce_anchor_sha256", pce_anchor_sha256)
        anchor_b = pce_anchor_sha256.encode("ascii")
    preimage = ENVELOPE_COMMIT_TAG + pce_sha256.encode("ascii") + b"|" + anchor_b
    return hashlib.sha256(preimage).digest()


def envelope_leaf_data(commitment: bytes) -> bytes:
    """Raw Merkle leaf datum (pre-hash): ENVELOPE_LEAF_PREFIX || 32-byte
    commitment. Fed to the RFC 6962 tree by build_envelope_checkpoint."""
    if not isinstance(commitment, bytes) or len(commitment) != 32:
        raise EnvelopeLedgerError("commitment must be 32 bytes")
    return ENVELOPE_LEAF_PREFIX + commitment


class EnvelopeLog:
    """Append-only, deduped, order-fixed commitment sequence.

    Dedupe is set semantics on the commitment: a re-committed identical
    (envelope, anchor) is not a new fan leaf. Refuse-reorder is enforced
    downstream by the RFC 9162 consistency proof (a later epoch whose prefix
    does not reproduce an earlier root fails closed), not here.
    """

    def __init__(self) -> None:
        self._order: list[bytes] = []
        self._seen: set[bytes] = set()

    def append(self, commitment: bytes) -> bool:
        if not isinstance(commitment, bytes) or len(commitment) != 32:
            raise EnvelopeLedgerError("commitment must be 32 bytes")
        if commitment in self._seen:
            return False
        self._seen.add(commitment)
        self._order.append(commitment)
        return True

    @property
    def order(self) -> list[bytes]:
        return list(self._order)

    def leaves(self) -> list[bytes]:
        return [envelope_leaf_data(c) for c in self._order]

    def enumerate_fan(self) -> list[str]:
        """The auditor enumeration: every distinct commitment (hex) in append
        order. This is where a grinding fan becomes visible."""
        return [c.hex() for c in self._order]


def load_log(store_path: Optional[Path] = None) -> EnvelopeLog:
    """Rebuild an EnvelopeLog from the append-only JSONL store, fail-closed on
    a malformed record. A commitment already present is skipped (dedupe), so a
    re-appended duplicate line never inflates the fan."""
    if store_path is None:
        store_path = default_store_path()
    log = EnvelopeLog()
    if not store_path.is_file():
        return log
    for i, line in enumerate(
        store_path.read_text(encoding="utf-8").splitlines()
    ):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            commitment = bytes.fromhex(rec["commitment"])
        except (ValueError, KeyError, TypeError) as e:
            raise EnvelopeLedgerError(
                "malformed envelope-log record at line " + str(i + 1)
                + ": " + str(e)
            )
        if len(commitment) != 32:
            raise EnvelopeLedgerError(
                "envelope-log record at line " + str(i + 1)
                + " commitment is not 32 bytes"
            )
        log.append(commitment)
    return log




def load_fan_pairs(
    store_path: Optional[Path] = None,
):  # __s196_incd_load_fan_pairs_v1__
    """The enumerated fan as (pce_sha256, pce_anchor_sha256) pairs in append
    order, deduped IDENTICALLY to load_log (dedupe on the commitment), so the
    fan order equals the leaf order equals the checkpoint order by construction.
    This is the single authoritative source of the fan; there is no second."""
    if store_path is None:
        store_path = default_store_path()
    pairs: list[tuple[str, Optional[str]]] = []
    seen: set[bytes] = set()
    if not store_path.is_file():
        return pairs
    for i, line in enumerate(
        store_path.read_text(encoding="utf-8").splitlines()
    ):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            pce_sha256 = rec["pce_sha256"]
            pce_anchor_sha256 = rec.get("pce_anchor_sha256")
            commitment = envelope_commitment(pce_sha256, pce_anchor_sha256)
        except (ValueError, KeyError, TypeError, EnvelopeLedgerError) as e:
            raise EnvelopeLedgerError(
                "malformed envelope-log record at line " + str(i + 1)
                + ": " + str(e)
            )
        if commitment in seen:
            continue
        seen.add(commitment)
        pairs.append((pce_sha256, pce_anchor_sha256))
    return pairs

def append_commitment(
    pce_sha256: str,
    pce_anchor_sha256: Optional[str],
    *,
    store_path: Optional[Path] = None,
) -> dict:
    """Append one envelope commitment to the operator's append-only store.

    Idempotent on identity: an already-present commitment is not re-written
    (returns appended=False). Dependency-light: no Merkle, no checkpoint, no
    network. Returns a summary dict; raises EnvelopeLedgerError cause-first.
    """
    if store_path is None:
        store_path = default_store_path()
    commitment = envelope_commitment(pce_sha256, pce_anchor_sha256)
    existing = load_log(store_path)
    if not existing.append(commitment):
        return {
            "appended": False,
            "reason": "commitment already present (dedupe)",
            "commitment": commitment.hex(),
            "store_path": str(store_path),
            "count": len(existing.order),
        }
    store_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(store_path.parent, 0o700)
    except OSError:
        pass
    record = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "commitment": commitment.hex(),
        "pce_sha256": pce_sha256,
        "pce_anchor_sha256": pce_anchor_sha256,
    }
    line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
    with open(store_path, "a", encoding="utf-8") as fh:
        fh.write(line)
    reloaded = load_log(store_path)
    return {
        "appended": True,
        "commitment": commitment.hex(),
        "store_path": str(store_path),
        "count": len(reloaded.order),
    }


def build_envelope_checkpoint(
    log: EnvelopeLog, log_key: "object"
) -> dict:
    """Standalone three-line C2SP checkpoint over the envelope leaf set.

    NOT on the CLI path (Inc A is append-only DARK). Used by tests and the
    later witness increment. Lazy-imports the Merkle + key-id primitives so the
    append path stays dependency-light.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    import rekor_v2_offline as rkt
    from rekor_checkpoint import ed25519_key_id

    if not isinstance(log_key, Ed25519PrivateKey):
        raise EnvelopeLedgerError("log_key must be an Ed25519PrivateKey")
    order = log.order
    if not order:
        raise EnvelopeLedgerError("empty envelope log: no checkpoint")
    leaves = log.leaves()
    root = rkt._naive_root(leaves)
    origin = ENVELOPE_ORIGIN_PREFIX + order[0].hex()
    body_lines = [origin, str(len(leaves)),
                  base64.b64encode(root).decode("ascii")]
    note_text = "".join(ln + "\n" for ln in body_lines)
    pub = log_key.public_key()
    key_id = ed25519_key_id(origin, pub)
    sig = log_key.sign(note_text.encode("utf-8"))
    sig_line = (
        _SIG_LINE_PREFIX + origin + " "
        + base64.b64encode(key_id + sig).decode("ascii")
    )
    return {
        "origin": origin,
        "env_size": len(leaves),
        "env_root": root,
        "note_text_bytes": note_text.encode("utf-8"),
        "envelope_note": note_text + "\n" + sig_line + "\n",
        "key_id_hex": key_id.hex(),
    }
