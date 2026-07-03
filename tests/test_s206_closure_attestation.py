from __future__ import annotations

import base64
import hashlib
from dataclasses import replace
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import closure_ledger as cl
import closure_attestation as ca

_P = "policy.alpha.v1"
_P2 = "policy.beta.v2"
_START = "2026-07-03T00:00:00Z"
_END = "2026-07-03T23:59:59Z"


def _act(i: int) -> str:
    return hashlib.sha256(f"act-{i}".encode("utf-8")).hexdigest()


def _dict(policy: str = _P, n: int = 12) -> cl.ClosureDictionary:
    cd = cl.ClosureDictionary(policy, _START, _END)
    for i in range(n):
        cd.add(_act(i))
    return cd


def _signed(cd: cl.ClosureDictionary):
    sk = Ed25519PrivateKey.generate()
    pinned = base64.b64encode(sk.public_key().public_bytes_raw()).decode("ascii")
    att = ca.sign_attestation(ca.build_attestation(cd), sk)
    return att, att.to_record(), pinned, sk


def test_attestation_sig_roundtrip_pinned() -> None:
    _, rec, pinned, _ = _signed(_dict())
    assert ca.verify_signature(rec, pinned)


def test_forged_signature_rejected() -> None:
    _, rec, pinned, _ = _signed(_dict())
    raw = bytearray(base64.b64decode(str(rec["signature"])))
    raw[0] ^= 0x01
    rec["signature"] = base64.b64encode(bytes(raw)).decode("ascii")
    assert not ca.verify_signature(rec, pinned)


def test_wrong_pinned_vkey_rejected() -> None:
    _, rec, _, _ = _signed(_dict())
    other = base64.b64encode(
        Ed25519PrivateKey.generate().public_key().public_bytes_raw()
    ).decode("ascii")
    assert not ca.verify_signature(rec, other)


def test_tampered_root_breaks_sig() -> None:
    _, rec, pinned, _ = _signed(_dict())
    r = bytearray(bytes.fromhex(str(rec["root"])))
    r[0] ^= 0x01
    rec["root"] = bytes(r).hex()
    assert not ca.verify_signature(rec, pinned)


def test_tampered_count_breaks_sig() -> None:
    _, rec, pinned, _ = _signed(_dict())
    rec["action_count"] = int(rec["action_count"]) + 1
    assert not ca.verify_signature(rec, pinned)


def test_kind_discriminator_signed() -> None:
    _, rec, pinned, _ = _signed(_dict())
    rec["kind"] = "nous.closure.attestation.v2"
    assert not ca.verify_signature(rec, pinned)


def test_real_nonmembership_verifies_via_ledger() -> None:
    cd = _dict()
    _, rec, _, _ = _signed(cd)
    nm = cd.nonmembership_proof(_act(9999))
    assert cl.verify_nonmembership(nm, str(rec["root"]))


def test_omitted_action_self_incriminating() -> None:
    cd = _dict()
    _, rec, pinned, _ = _signed(cd)
    absent = _act(9999)
    nm = cd.nonmembership_proof(absent)
    verdict = ca.verify_omission(rec, nm, pinned, absent)
    assert verdict["absent"] is True
    assert verdict["scope_policy_id"] == _P


def test_honest_dict_cannot_emit_false_absence() -> None:
    cd = _dict()
    with pytest.raises(cl.ClosureLedgerError):
        cd.nonmembership_proof(_act(3))


def test_forged_absence_for_present_rejected() -> None:
    cd = _dict()
    _, rec, _, _ = _signed(cd)
    present = _act(5)
    mp = cd.membership_proof(present)
    forged = {
        "type": "nonmembership",
        "key": mp["key"],
        "leaf": cl.EMPTY_LEAF.hex(),
        "root": str(rec["root"]),
        "siblings": mp["siblings"],
        "policy_id": _P,
        "interval_start": _START,
        "interval_end": _END,
    }
    assert not cl.verify_nonmembership(forged, str(rec["root"]))


def test_cross_policy_proof_rejected_by_scope() -> None:
    _, rec, pinned, _ = _signed(_dict(_P))
    cd2 = _dict(_P2)
    absent = _act(9999)
    nm2 = cd2.nonmembership_proof(absent)
    verdict = ca.verify_omission(rec, nm2, pinned, absent)
    assert verdict["absent"] is False


def test_aggregate_count_mismatch_second_path() -> None:
    _, rec, _, _ = _signed(_dict(n=12))
    assert ca.count_mismatch(rec, 13) is True
    assert ca.count_mismatch(rec, 12) is False


def test_canonical_excludes_signature_envelope() -> None:
    cd = _dict()
    att, _, _, _ = _signed(cd)
    assert att.canonical_body() == ca.build_attestation(cd).canonical_body()


def test_drop_when_none_byte_identical() -> None:
    cd = _dict()
    unsigned = ca.build_attestation(cd)
    explicit_none = replace(unsigned, signature=None, vkey=None)
    assert explicit_none.canonical_body() == unsigned.canonical_body()


def test_action_id_hex_enforced() -> None:
    cd = _dict()
    _, rec, pinned, _ = _signed(cd)
    nm = cd.nonmembership_proof(_act(9999))
    verdict = ca.verify_omission(rec, nm, pinned, "not-a-hex-action-id")
    assert verdict["absent"] is False


def test_membership_still_composes() -> None:
    cd = _dict()
    _, rec, _, _ = _signed(cd)
    mp = cd.membership_proof(_act(0))
    assert cl.verify_membership(mp, str(rec["root"]))


def test_verify_omission_scope_interval_mismatch() -> None:
    cd = _dict()
    _, rec, pinned, _ = _signed(cd)
    absent = _act(9999)
    nm = cd.nonmembership_proof(absent)
    nm["interval_end"] = "1999-01-01T00:00:00Z"
    verdict = ca.verify_omission(rec, nm, pinned, absent)
    assert verdict["absent"] is False


def test_verify_omission_bad_proof_type() -> None:
    _, rec, pinned, _ = _signed(_dict())
    verdict = ca.verify_omission(rec, "not-a-dict", pinned, _act(9999))
    assert verdict["absent"] is False


def test_count_mismatch_typed_refusal() -> None:
    _, rec, _, _ = _signed(_dict())
    with pytest.raises(ca.ClosureAttestationError):
        ca.count_mismatch(rec, -1)


def test_malformed_record_yields_no_absence() -> None:
    verdict = ca.verify_omission({"kind": "x"}, {}, "AAAA", _act(1))
    assert verdict["absent"] is False


def test_generate_key_writes_0600_and_returns_vkey(tmp_path: Path) -> None:
    p = tmp_path / "closure-attestation.key"
    vkey = ca.generate_operator_key(p)
    assert p.is_file()
    assert (p.stat().st_mode & 0o777) == 0o600
    assert len(base64.b64decode(vkey)) == 32


def test_load_key_roundtrip_signs(tmp_path: Path) -> None:
    p = tmp_path / "closure-attestation.key"
    vkey = ca.generate_operator_key(p)
    sk = ca.load_operator_key(p)
    cd = _dict()
    att = ca.sign_attestation(ca.build_attestation(cd), sk)
    assert ca.verify_signature(att.to_record(), vkey)


def test_load_key_refuses_absent(tmp_path: Path) -> None:
    with pytest.raises(ca.ClosureAttestationError):
        ca.load_operator_key(tmp_path / "missing.key")


def test_generate_key_refuses_overwrite(tmp_path: Path) -> None:
    p = tmp_path / "closure-attestation.key"
    ca.generate_operator_key(p)
    with pytest.raises(ca.ClosureAttestationError):
        ca.generate_operator_key(p)


def test_load_key_refuses_malformed_length(tmp_path: Path) -> None:
    p = tmp_path / "bad.key"
    p.write_bytes(b"tooshort")
    with pytest.raises(ca.ClosureAttestationError):
        ca.load_operator_key(p)


def test_default_key_path_is_xdg_scoped() -> None:
    path = ca.default_key_path()
    assert path.name == "closure-attestation.key"
    assert path.parent.name == "keys"
