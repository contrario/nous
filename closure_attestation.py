"""nous closure attestation: the signed, per-(policy, interval) completeness
commitment over the closure_ledger root, plus the offline omission verifier.

S206 Inc B of the witnessed closure attestation arc.
__s206_closure_attestation_module_v1__

DARK LAYER. This module signs the key-indexed root that closure_ledger commits
and supplies the offline verifier for the non-membership challenge. It builds an
attestation on demand, contacts NO witness and NO transparency log (that is Inc C),
and NEVER signs at import. The persistent-key signature is an operator ceremony:
the signing key is loaded from disk or the call refuses cause-first; it is never
generated implicitly by a signing path.

Honest boundary (inviolable). The attestation EVIDENCES a completeness COMMITMENT
scoped to the operator's OWN declared policy P over interval T: "under policy P,
interval T, this signed root is the committed-complete set of governed actions."
It NEVER claims the operator did nothing off-book; an action never declared
in-scope-P was never claimed. Its bite is the operator's own signed declaration.
A surfaced in-scope-P action provably absent from the signed root (a non-membership
proof that verifies against that root) is inconsistent with the operator's own
completeness assertion -- the cryptographic form of adverse inference. Two
independent incrimination paths follow from one signed body: (1) per-action
non-membership; (2) an aggregate count mismatch, when a discovery surfaces more
in-scope actions than the signed action_count. It PROVES nothing: "proves" stays
reserved for Z3 cost bounds and Farkas certificates. NOUS is a monitor, not a
guard. The name-to-key binding is operator-asserted; the auditor pins the verifying
key out-of-band and that identity check is the auditor's step.

Disclosure (stated, not hidden). The signed body carries action_count, so the
attestation DISCLOSES the per-(policy, interval) governed-action VOLUME to any
verifier. This is deliberate: the count is a second, independent incrimination
path and, in the scoped adversarial-discovery setting the arc targets, the
per-(P, T) count is discoverable anyway. Hiding the count is NOT an Inc B concern
(the key-indexed trie already hides cardinality structurally; a single
non-membership proof leaks only path-local density). The volume-privacy question
bites only when the root goes PUBLIC and witnessed (Inc C); it is recorded as an
Inc C open question, not solved here with key-transparency machinery.

Serialization. The attestation is a frozen dataclass whose canonical body is plain
sorted-keys compact JSON -- json.dumps(sort_keys=True, separators=(",",":")) --
EXCLUDING the signature envelope (signature, vkey) exactly as the Manifest excludes
signature and transparency_log. Optional signed fields are drop-when-None so an
unwitnessed attestation stays byte-identical to one that later carries Inc C witness
and Rekor fields when those are absent.
"""
from __future__ import annotations

import base64
import json
import os
import stat
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

import closure_ledger

ATTEST_KIND: str = "nous.closure.attestation.v1"
ATTEST_SCHEMA_VERSION: int = 1
_ENVELOPE_FIELDS: tuple[str, ...] = ("signature", "vkey")
_ED25519_SEED_LEN: int = 32


class ClosureAttestationError(RuntimeError):
    """Raised cause-first on a schema, signing, key, or verification violation."""


@dataclass(frozen=True)
class ClosureAttestation:
    """A per-(policy, interval) signed completeness commitment over a closure root.

    canonical_body() excludes the signature envelope and drops None fields, so the
    unsigned body, the signed record, and a future Inc C witnessed record share
    byte-identical signed bytes when the optional fields are absent.
    """

    kind: str
    schema_version: int
    policy_id: str
    interval_start: str
    interval_end: str
    root: str
    action_count: int
    signature: Optional[str] = None
    vkey: Optional[str] = None

    def canonical_body(self) -> bytes:
        body = {
            k: v
            for k, v in self.__dict__.items()
            if k not in _ENVELOPE_FIELDS and v is not None
        }
        return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def to_record(self) -> Dict[str, object]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


def _rehydrate(record: object) -> ClosureAttestation:
    if not isinstance(record, dict):
        raise ClosureAttestationError("attestation record must be a dict")
    try:
        return ClosureAttestation(
            kind=str(record["kind"]),
            schema_version=int(record["schema_version"]),
            policy_id=str(record["policy_id"]),
            interval_start=str(record["interval_start"]),
            interval_end=str(record["interval_end"]),
            root=str(record["root"]),
            action_count=int(record["action_count"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ClosureAttestationError("malformed attestation record: " + str(exc))


def build_attestation(cd: closure_ledger.ClosureDictionary) -> ClosureAttestation:
    """Unsigned completeness commitment over the ledger's current root and count."""
    return ClosureAttestation(
        kind=ATTEST_KIND,
        schema_version=ATTEST_SCHEMA_VERSION,
        policy_id=cd.policy_id,
        interval_start=cd.interval_start,
        interval_end=cd.interval_end,
        root=cd.root().hex(),
        action_count=cd.action_count,
    )


def sign_attestation(
    att: ClosureAttestation, signing_key: Ed25519PrivateKey
) -> ClosureAttestation:
    """Sign the canonical body (signature envelope excluded) and return a signed
    copy carrying the base64 signature and the raw verifying key."""
    unsigned = replace(att, signature=None, vkey=None)
    sig = signing_key.sign(unsigned.canonical_body())
    vkey = signing_key.public_key().public_bytes_raw()
    return replace(
        att,
        signature=base64.b64encode(sig).decode("ascii"),
        vkey=base64.b64encode(vkey).decode("ascii"),
    )


def verify_signature(record: object, pinned_vkey_b64: str) -> bool:
    """Offline: verify the attestation signature under the AUDITOR-PINNED key. The
    embedded vkey is a hint only; if present it must equal the pinned key."""
    if not isinstance(record, dict):
        return False
    try:
        att = _rehydrate(record)
        if "vkey" in record and str(record["vkey"]) != pinned_vkey_b64:
            return False
        vkey = Ed25519PublicKey.from_public_bytes(base64.b64decode(pinned_vkey_b64))
        vkey.verify(base64.b64decode(str(record["signature"])), att.canonical_body())
        return True
    except (InvalidSignature, ValueError, KeyError, TypeError, ClosureAttestationError):
        return False


def verify_omission(
    record: object,
    nonmembership_proof: object,
    pinned_vkey_b64: str,
    action_id: str,
) -> Dict[str, object]:
    """Offline verdict that a queried in-scope action is provably absent from the
    operator's signed completeness commitment. Composes closure_ledger's
    non-membership verifier; consumes only (record, proof, pinned key, action) --
    no dictionary object and no full-set rebuild."""
    if not verify_signature(record, pinned_vkey_b64):
        return {"absent": False, "reason": "attestation signature invalid under pinned key"}
    assert isinstance(record, dict)
    try:
        expected_key = closure_ledger.position_key(
            str(record["policy_id"]), action_id
        ).hex()
    except closure_ledger.ClosureLedgerError as exc:
        return {"absent": False, "reason": str(exc)}
    if not isinstance(nonmembership_proof, dict):
        return {"absent": False, "reason": "non-membership proof must be a dict"}
    scope_ok = (
        nonmembership_proof.get("policy_id") == record["policy_id"]
        and nonmembership_proof.get("interval_start") == record["interval_start"]
        and nonmembership_proof.get("interval_end") == record["interval_end"]
    )
    if not scope_ok:
        return {"absent": False, "reason": "proof scope does not match attestation scope"}
    if nonmembership_proof.get("key") != expected_key:
        return {
            "absent": False,
            "reason": "proof key is not the position of the queried action under this policy",
        }
    if not closure_ledger.verify_nonmembership(nonmembership_proof, str(record["root"])):
        return {
            "absent": False,
            "reason": "non-membership proof does not verify against the signed root",
        }
    return {
        "absent": True,
        "scope_policy_id": str(record["policy_id"]),
        "interval": [str(record["interval_start"]), str(record["interval_end"])],
        "action_id": action_id,
        "statement": (
            "action provably absent from the operator-signed completeness commitment "
            "for policy " + str(record["policy_id"]) + " over the attested interval; "
            "evidences inconsistency with that signed assertion, does not prove intent"
        ),
    }


def count_mismatch(record: object, surfaced_in_scope: int) -> bool:
    """True when a discovery surfaces more in-scope actions than the signed
    action_count -- the aggregate incrimination path, independent of which specific
    actions are absent."""
    if not isinstance(record, dict):
        raise ClosureAttestationError("attestation record must be a dict")
    if not isinstance(surfaced_in_scope, int) or surfaced_in_scope < 0:
        raise ClosureAttestationError("surfaced_in_scope must be a non-negative int")
    return surfaced_in_scope > int(record["action_count"])


def default_key_path() -> Path:
    """Persistent closure-attestation signing key, XDG-scoped (axiom 7):
    $XDG_DATA_HOME/nous/keys/closure-attestation.key, else
    ~/.local/share/nous/keys/closure-attestation.key. Distinct from the
    envelope-log key; raw 32-byte Ed25519 seed on disk, 0600."""
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        root = Path(base) / "nous" / "keys"
    else:
        root = Path(os.path.expanduser("~")) / ".local" / "share" / "nous" / "keys"
    return root / "closure-attestation.key"


def load_operator_key(key_path: Optional[Path] = None) -> Ed25519PrivateKey:
    """Load the persistent signing key. Refuse cause-first if absent or malformed;
    NEVER generate implicitly (generation is a separate operator ceremony)."""
    if key_path is None:
        key_path = default_key_path()
    if not key_path.is_file():
        raise ClosureAttestationError(
            "closure-attestation key absent at " + str(key_path)
            + "; run the key-generation ceremony first (no implicit generation)"
        )
    seed = key_path.read_bytes()
    if len(seed) != _ED25519_SEED_LEN:
        raise ClosureAttestationError(
            "closure-attestation key is not a 32-byte Ed25519 seed: " + str(key_path)
        )
    return Ed25519PrivateKey.from_private_bytes(seed)


def generate_operator_key(key_path: Optional[Path] = None) -> str:
    """Operator ceremony: generate the persistent signing key and write it 0600.
    Refuse cause-first if a key already exists (never overwrite key material).
    Returns the base64 verifying key for the auditor to pin."""
    if key_path is None:
        key_path = default_key_path()
    if key_path.exists():
        raise ClosureAttestationError(
            "refusing to overwrite existing key material at " + str(key_path)
        )
    key_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(key_path.parent, 0o700)
    except OSError:
        pass
    sk = Ed25519PrivateKey.generate()
    seed = sk.private_bytes_raw()
    fd, tmp = tempfile.mkstemp(dir=str(key_path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(seed)
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(tmp, key_path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return base64.b64encode(sk.public_key().public_bytes_raw()).decode("ascii")


def enumerate_scope(cd: closure_ledger.ClosureDictionary) -> List[str]:
    """Auditor enumeration passthrough: the in-scope action ids whose set
    re-derives the signed root."""
    return cd.enumerate_actions()
