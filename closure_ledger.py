"""nous closure ledger: per-(policy, interval) key-indexed completeness
commitment over the operator's declared governed-action set.

S205 Inc A of the witnessed closure attestation arc. __s205_closure_ledger_module_v1__

DARK SUBSTRATE. This module supplies the key-indexed, root-committed, enumerable
leaf domain a completeness attestation (a later increment) signs and a witness
quorum (a later increment) makes non-equivocable. The recording path
(append_action) is opt-in via NOUS_CLOSURE_LOG and writes NOTHING when that
variable is unset (FG-118). It builds NO attestation, contacts NO witness, and
imports NO signing/network code.

Honest boundary (inviolable). This module EVIDENCES a completeness COMMITMENT
scoped to the operator's OWN declared policy P over interval T: "under policy P,
interval T, this is the committed-complete set of governed actions." It NEVER
claims the operator did nothing off-book; an action never declared in-scope-P was
never claimed. Its bite is the operator's own declaration: a surfaced in-scope-P
action provably absent from the committed root is inconsistent with that signed
completeness assertion -- the cryptographic form of adverse inference. It PROVES
nothing: "proves" stays reserved for Z3 cost bounds and Farkas certificates. NOUS
is a monitor, not a guard.

Structure. A key-indexed binary sparse Merkle trie (CONIKS/akd shape): the leaf
for a governed action lives at, and only at, the 256-bit position
sha256(CLOSURE_KEY_TAG || sha256(policy_id) || action_id). Non-membership is a
proof that that position resolves to the EMPTY leaf, verified against the
committed root from (key, empty_leaf, co-path) alone. Because the position is
key-determined, absence is sound against a MALICIOUS operator with NO full-set
rebuild and NO sortedness assumption -- the threat model closure attestation
exists to bind. (A sorted-leaf compact non-membership is sound only against an
honestly-built tree; it was spiked, proven unsound for this threat model, and
discarded as the primitive.)

Determinism. The root is a pure function of the (policy_id, action_id) set:
position is key-determined, so append order is irrelevant and a re-added identical
action is a no-op (set semantics). Two governed-action ids that collide to one
256-bit position refuse cause-first rather than silently merge.

Domain separation. The leaf/node/empty digests carry distinct v1 prefixes so a
closure leaf can never collide with an envelope leaf (b"nous.envelope.leaf.v1\n"),
a continuity link leaf (a raw 32-byte digest), or the budget leaf
(b"nous.budget.leaf.v1\n").
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple


CLOSURE_KEY_TAG: bytes = b"nous.closure.key.v1|"
CLOSURE_VALUE_TAG: bytes = b"nous.closure.value.v1|"
CLOSURE_LEAF_PREFIX: bytes = b"nous.closure.leaf.v1\n"
CLOSURE_NODE_PREFIX: bytes = b"nous.closure.node.v1\n"
CLOSURE_EMPTY_PREFIX: bytes = b"nous.closure.empty.v1\n"
CLOSURE_LOG_ENV: str = "NOUS_CLOSURE_LOG"
CLOSURE_SCHEMA_VERSION: int = 1
_KEY_BITS: int = 256


class ClosureLedgerError(RuntimeError):
    """Raised cause-first on a schema, dedupe, position, or store violation."""


def _sha256(*parts: bytes) -> bytes:
    m = hashlib.sha256()
    for p in parts:
        m.update(p)
    return m.digest()


def _leaf_digest(key: bytes, value: bytes) -> bytes:
    return _sha256(CLOSURE_LEAF_PREFIX, key, value)


def _node(left: bytes, right: bytes) -> bytes:
    return _sha256(CLOSURE_NODE_PREFIX, left, right)


EMPTY_LEAF: bytes = _sha256(CLOSURE_EMPTY_PREFIX)

_DEFAULT: List[bytes] = [b""] * (_KEY_BITS + 1)
_DEFAULT[_KEY_BITS] = EMPTY_LEAF
for _d in range(_KEY_BITS - 1, -1, -1):
    _DEFAULT[_d] = _node(_DEFAULT[_d + 1], _DEFAULT[_d + 1])


def _require_sha256_hex(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ClosureLedgerError(
            name + " must be a 64-char sha256 hex string, got: " + repr(value)
        )
    try:
        int(value, 16)
    except ValueError:
        raise ClosureLedgerError(name + " is not valid hexadecimal: " + repr(value))
    return value


def position_key(policy_id: str, action_id: str) -> bytes:
    """256-bit trie position for a governed action under a declared policy:
    sha256(CLOSURE_KEY_TAG || sha256(policy_id) || action_id). Fixed-length
    concatenation binds the position unambiguously to the declared scope; a
    distinct (policy, action) pair yields a distinct position."""
    if not isinstance(policy_id, str) or not policy_id:
        raise ClosureLedgerError("policy_id must be a non-empty string")
    _require_sha256_hex("action_id", action_id)
    return _sha256(
        CLOSURE_KEY_TAG,
        _sha256(policy_id.encode("utf-8")),
        bytes.fromhex(action_id),
    )


def record_value(action_id: str) -> bytes:
    """Leaf value committing the governed-action record:
    sha256(CLOSURE_VALUE_TAG || action_id)."""
    _require_sha256_hex("action_id", action_id)
    return _sha256(CLOSURE_VALUE_TAG, bytes.fromhex(action_id))


def _bit(key: bytes, i: int) -> int:
    return (key[i // 8] >> (7 - (i % 8))) & 1


def _subtree_root(entries: List[Tuple[bytes, bytes]], depth: int) -> bytes:
    if not entries:
        return _DEFAULT[depth]
    if depth == _KEY_BITS:
        if len(entries) == 1:
            return entries[0][1]
        raise ClosureLedgerError("position collision at 256-bit key")
    if len(entries) == 1:
        key, node = entries[0][0], entries[0][1]
        for d in range(_KEY_BITS - 1, depth - 1, -1):
            node = (
                _node(node, _DEFAULT[d + 1])
                if _bit(key, d) == 0
                else _node(_DEFAULT[d + 1], node)
            )
        return node
    left = [e for e in entries if _bit(e[0], depth) == 0]
    right = [e for e in entries if _bit(e[0], depth) == 1]
    return _node(_subtree_root(left, depth + 1), _subtree_root(right, depth + 1))


def _proof_siblings(entries: List[Tuple[bytes, bytes]], key: bytes) -> Dict[int, bytes]:
    siblings: Dict[int, bytes] = {}
    cur = entries
    for d in range(_KEY_BITS):
        if not cur:
            break
        left = [e for e in cur if _bit(e[0], d) == 0]
        right = [e for e in cur if _bit(e[0], d) == 1]
        if _bit(key, d) == 0:
            sib = _subtree_root(right, d + 1)
            cur = left
        else:
            sib = _subtree_root(left, d + 1)
            cur = right
        if sib != _DEFAULT[d + 1]:
            siblings[d] = sib
    return siblings


def _root_from_copath(key: bytes, leaf: bytes, siblings: Dict[int, bytes]) -> bytes:
    node = leaf
    for d in range(_KEY_BITS - 1, -1, -1):
        sib = siblings.get(d, _DEFAULT[d + 1])
        node = _node(node, sib) if _bit(key, d) == 0 else _node(sib, node)
    return node


def _siblings_wire(siblings: Dict[int, bytes]) -> List[List[object]]:
    return [[d, siblings[d].hex()] for d in sorted(siblings)]


def _siblings_from_wire(wire: object) -> Dict[int, bytes]:
    if not isinstance(wire, list):
        raise ClosureLedgerError("siblings must be a list of [depth, hex] pairs")
    out: Dict[int, bytes] = {}
    for item in wire:
        if (not isinstance(item, list)) or len(item) != 2:
            raise ClosureLedgerError("each sibling must be a [depth, hex] pair")
        depth, hex_digest = item
        if not isinstance(depth, int) or not (0 <= depth < _KEY_BITS):
            raise ClosureLedgerError("sibling depth out of range: " + repr(depth))
        if not isinstance(hex_digest, str):
            raise ClosureLedgerError("sibling digest must be a hex string")
        sib = bytes.fromhex(hex_digest)
        if len(sib) != 32:
            raise ClosureLedgerError("sibling digest is not 32 bytes")
        if depth in out:
            raise ClosureLedgerError("duplicate sibling depth: " + repr(depth))
        out[depth] = sib
    return out


class ClosureDictionary:
    """Key-indexed sparse Merkle trie over one (policy_id, interval) scope.

    Enumerable, root-committed, order-independent. add() is set semantics on the
    policy-scoped position: a re-added identical action is a no-op; two actions
    colliding to one 256-bit position refuse cause-first.
    """

    def __init__(self, policy_id: str, interval_start: str, interval_end: str) -> None:
        if not isinstance(policy_id, str) or not policy_id:
            raise ClosureLedgerError("policy_id must be a non-empty string")
        if not isinstance(interval_start, str) or not interval_start:
            raise ClosureLedgerError("interval_start must be a non-empty string")
        if not isinstance(interval_end, str) or not interval_end:
            raise ClosureLedgerError("interval_end must be a non-empty string")
        self.policy_id: str = policy_id
        self.interval_start: str = interval_start
        self.interval_end: str = interval_end
        self._by_key: Dict[bytes, Tuple[str, bytes]] = {}

    def add(self, action_id: str) -> bool:
        key = position_key(self.policy_id, action_id)
        leaf = _leaf_digest(key, record_value(action_id))
        if key in self._by_key:
            existing_action, existing_leaf = self._by_key[key]
            if existing_action == action_id and existing_leaf == leaf:
                return False
            raise ClosureLedgerError(
                "position collision: two governed actions map to one 256-bit key"
            )
        self._by_key[key] = (action_id, leaf)
        return True

    def has_action(self, action_id: str) -> bool:
        return position_key(self.policy_id, action_id) in self._by_key

    def _entries(self) -> List[Tuple[bytes, bytes]]:
        return sorted(
            ((k, v[1]) for k, v in self._by_key.items()), key=lambda e: e[0]
        )

    @property
    def action_count(self) -> int:
        return len(self._by_key)

    def enumerate_actions(self) -> List[str]:
        """Every distinct in-scope action id in ascending position order. This is
        the auditor enumeration; the full set re-derives the committed root."""
        return [self._by_key[k][0] for k in sorted(self._by_key)]

    def root(self) -> bytes:
        return _subtree_root(self._entries(), 0)

    def membership_proof(self, action_id: str) -> dict:
        key = position_key(self.policy_id, action_id)
        if key not in self._by_key:
            raise ClosureLedgerError(
                "membership proof requested for an action absent from the scope"
            )
        leaf = self._by_key[key][1]
        return {
            "interval_end": self.interval_end,
            "interval_start": self.interval_start,
            "key": key.hex(),
            "leaf": leaf.hex(),
            "policy_id": self.policy_id,
            "root": self.root().hex(),
            "siblings": _siblings_wire(_proof_siblings(self._entries(), key)),
            "type": "membership",
            "value": record_value(action_id).hex(),
        }

    def nonmembership_proof(self, action_id: str) -> dict:
        key = position_key(self.policy_id, action_id)
        if key in self._by_key:
            raise ClosureLedgerError(
                "non-membership proof requested for a present action"
            )
        return {
            "interval_end": self.interval_end,
            "interval_start": self.interval_start,
            "key": key.hex(),
            "leaf": EMPTY_LEAF.hex(),
            "policy_id": self.policy_id,
            "root": self.root().hex(),
            "siblings": _siblings_wire(_proof_siblings(self._entries(), key)),
            "type": "nonmembership",
        }


def verify_membership(proof: object, expected_root_hex: str) -> bool:
    """Offline: recompute the root from (key, leaf, co-path) and bind the leaf to
    (key, value). Input is the proof and the committed root only -- no entry set,
    no rebuild."""
    if not isinstance(proof, dict) or proof.get("type") != "membership":
        return False
    if proof.get("root") != expected_root_hex:
        return False
    try:
        key = bytes.fromhex(proof["key"])
        value = bytes.fromhex(proof["value"])
        leaf = bytes.fromhex(proof["leaf"])
        siblings = _siblings_from_wire(proof["siblings"])
    except (KeyError, TypeError, ValueError, ClosureLedgerError):
        return False
    if leaf != _leaf_digest(key, value):
        return False
    return _root_from_copath(key, leaf, siblings).hex() == expected_root_hex


def verify_nonmembership(proof: object, expected_root_hex: str) -> bool:
    """Offline: recompute the root from (key, EMPTY_LEAF, co-path). Sound against
    a malicious operator with no rebuild, because position is key-determined."""
    if not isinstance(proof, dict) or proof.get("type") != "nonmembership":
        return False
    if proof.get("root") != expected_root_hex:
        return False
    try:
        key = bytes.fromhex(proof["key"])
        leaf = bytes.fromhex(proof["leaf"])
        siblings = _siblings_from_wire(proof["siblings"])
    except (KeyError, TypeError, ValueError, ClosureLedgerError):
        return False
    if leaf != EMPTY_LEAF:
        return False
    return _root_from_copath(key, leaf, siblings).hex() == expected_root_hex


def default_store_path() -> Path:
    """Operator-level append-only closure store, mirroring
    envelope_ledger.default_store_path:
    $XDG_DATA_HOME/nous/closure-log/log.jsonl, else
    ~/.local/share/nous/closure-log/log.jsonl."""
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        root = Path(base) / "nous" / "closure-log"
    else:
        root = (
            Path(os.path.expanduser("~"))
            / ".local" / "share" / "nous" / "closure-log"
        )
    return root / "log.jsonl"


def load_closure(
    policy_id: str,
    interval_start: str,
    interval_end: str,
    *,
    store_path: Optional[Path] = None,
) -> ClosureDictionary:
    """Rebuild the ClosureDictionary for one (policy_id, interval) scope from the
    append-only JSONL store, fail-closed on a malformed record. Records outside
    the requested scope are skipped; a duplicate action is deduped by add()."""
    if store_path is None:
        store_path = default_store_path()
    cd = ClosureDictionary(policy_id, interval_start, interval_end)
    if not store_path.is_file():
        return cd
    for i, line in enumerate(store_path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            rec_policy = rec["policy_id"]
            rec_start = rec["interval_start"]
            rec_end = rec["interval_end"]
            rec_action = rec["action_id"]
        except (ValueError, KeyError, TypeError) as e:
            raise ClosureLedgerError(
                "malformed closure-log record at line " + str(i + 1) + ": " + str(e)
            )
        if (rec_policy, rec_start, rec_end) != (
            policy_id,
            interval_start,
            interval_end,
        ):
            continue
        cd.add(rec_action)
    return cd


def append_action(
    policy_id: str,
    interval_start: str,
    interval_end: str,
    action_id: str,
    *,
    store_path: Optional[Path] = None,
) -> dict:
    """Append one governed-action id to the operator's append-only closure store,
    scoped to (policy_id, interval).

    DARK. Writes NOTHING unless NOUS_CLOSURE_LOG is set (FG-118); when unset the
    call is a no-op returning appended=False with the disabled-gate reason.
    Idempotent on identity within the scope: an already-present action is not
    re-written. Dependency-light: no attestation, no witness, no network. Raises
    ClosureLedgerError cause-first.
    """
    if os.environ.get(CLOSURE_LOG_ENV) is None:
        return {
            "appended": False,
            "reason": "closure log disabled (NOUS_CLOSURE_LOG unset)",
            "policy_id": policy_id,
        }
    _require_sha256_hex("action_id", action_id)
    if store_path is None:
        store_path = default_store_path()
    existing = load_closure(
        policy_id, interval_start, interval_end, store_path=store_path
    )
    if existing.has_action(action_id):
        return {
            "appended": False,
            "reason": "action already present in scope (dedupe)",
            "policy_id": policy_id,
            "action_id": action_id,
            "count": existing.action_count,
        }
    store_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(store_path.parent, 0o700)
    except OSError:
        pass
    record = {
        "schema_version": CLOSURE_SCHEMA_VERSION,
        "policy_id": policy_id,
        "interval_start": interval_start,
        "interval_end": interval_end,
        "action_id": action_id,
    }
    line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
    with open(store_path, "a", encoding="utf-8") as fh:
        fh.write(line)
    reloaded = load_closure(
        policy_id, interval_start, interval_end, store_path=store_path
    )
    return {
        "appended": True,
        "policy_id": policy_id,
        "action_id": action_id,
        "root": reloaded.root().hex(),
        "count": reloaded.action_count,
        "store_path": str(store_path),
    }
