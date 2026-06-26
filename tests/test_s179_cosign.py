from __future__ import annotations

# __s179_cosign_tests_v1__
# Drives the real `nous continuity checkpoint` + `nous continuity cosign`
# producers and the emitted zero-NOUS verifier (subprocess) end to end: a
# witness Ed25519 type-0x04 cosignature is appended, the emitted verifier
# counts it under the pinned (name, key), refuses --witness-key without
# --witness-name, reports zero under a wrong pinned name, leaves an
# un-witnessed checkpoint byte-identical, and re-cosigning is idempotent.
# No producer mock; the ledger fixture mirrors test_s178_checkpoint_leg.

import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import continuity_cosign as ccs
import continuity_ledger as cl

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from manifest import load_or_create_keypair

_ISS = "https://counterparty.example/keys/ed25519-1"
_WORLD = hashlib.sha256(b"world").hexdigest()
_SOUL = hashlib.sha256(b"soul").hexdigest()
_AUD = "world:" + _WORLD
_WNAME = "witness.example/w1"


def _h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _op_sign(op: Ed25519PrivateKey, body: bytes) -> dict:
    pub = op.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return {
        "algorithm": "ed25519",
        "public_key_b64": base64.b64encode(pub).decode("ascii"),
        "signature_b64": base64.b64encode(op.sign(body)).decode("ascii"),
    }


def _write_priced_dossier(d: Path, op: Ed25519PrivateKey, seq: int,
                          head: str, cap: str) -> None:
    d.mkdir(parents=True, exist_ok=True)
    trace = {"memory_consultation": {
        "world_sha256": _WORLD, "producing_soul_sha256": _SOUL,
        "consulted_chain_head": head, "consulted_seq_count": seq,
    }}
    trace["signature"] = _op_sign(op, cl._doc_canonical_body_bytes(trace))
    manifest = {"source_sha256": _h("src"), "smt_spec_sha256": _h("smt"),
                "pricing_sha256": _h("price"), "cost_cap_usd": cap}
    cert = {
        "certificate_schema_version": 2, "conformant": True,
        "binding_ok": True, "surface_ok": True,
        "assumption_discharge_ok": True, "bound_transfer_ok": True,
        "authorization_ok": True, "trace_signature_ok": True,
        "sequence_ok": True,
        "trace_sha256": hashlib.sha256(
            cl._doc_canonical_body_bytes(trace)).hexdigest(),
        "source_sha256": _h("src"), "smt_spec_sha256": _h("smt"),
        "pricing_sha256": _h("price"),
    }
    cert["signature"] = _op_sign(op, cl._cert_canonical_body_bytes(cert))
    (d / "conformance.json").write_text(json.dumps(cert), encoding="utf-8")
    (d / "trace.json").write_text(json.dumps(trace), encoding="utf-8")
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _run(argv: list) -> int:
    import cli
    old = sys.argv
    sys.argv = ["nous"] + argv
    try:
        return cli.main()
    finally:
        sys.argv = old


def _keys(tmp: Path):
    op = Ed25519PrivateKey.generate()
    cp = Ed25519PrivateKey.generate()
    (tmp / "cp_priv.pem").write_bytes(cp.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    (tmp / "cp_pub.pem").write_bytes(cp.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo))
    return op, cp


def _build_ledger(tmp: Path, op, cp, caps) -> Path:
    ledger = tmp / "ledger"
    for i, cap in enumerate(caps):
        _write_priced_dossier(tmp / ("run" + str(i)), op, i,
                              _h("h" + str(i)), cap)
    prev_args = ["--genesis"]
    for i in range(len(caps)):
        leaf = str(i).zfill(3)
        assert _run(["continuity", "link",
                     "--dir", str(tmp / ("run" + str(i))), *prev_args,
                     "--counterparty-key-uri", _ISS,
                     "--out", str(ledger / leaf)]) == 0
        prev = json.loads(
            (ledger / leaf / "link.json").read_text())["this_link_digest"]
        prev_args = ["--prev", prev]
    for i in range(len(caps)):
        leaf = str(i).zfill(3)
        assert _run(["continuity", "receipt", "--dir", str(ledger / leaf),
                     "--key", str(tmp / "cp_priv.pem"), "--kid", "k1",
                     "--iss", _ISS, "--aud", _AUD]) == 0
    return ledger


def _log_pub_pem(tmp: Path, logkey: Path) -> Path:
    _priv, pub, _resolved = load_or_create_keypair(logkey)
    p = tmp / "logpub.pem"
    p.write_bytes(pub.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo))
    return p


def _emit(tmp: Path) -> Path:
    assert _run(["continuity", "emit-verifier", "--out", str(tmp)]) == 0
    return tmp / "verify_continuity_offline.py"


def _make_witness(tmp: Path) -> Ed25519PrivateKey:
    w = Ed25519PrivateKey.generate()
    (tmp / "w_priv.pem").write_bytes(w.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    (tmp / "w_pub.pem").write_bytes(w.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo))
    return w


def _rail_checkpoint(tmp: Path):
    op, cp = _keys(tmp)
    ledger = _build_ledger(tmp, op, cp, ["0.10", "0.20"])
    logkey = tmp / "logkey"
    assert _run(["continuity", "checkpoint", "--ledger", str(ledger),
                 "--log-key", str(logkey)]) == 0
    return ledger, _log_pub_pem(tmp, logkey)


def _cosign(tmp: Path, note: Path, ts: str) -> int:
    return _run(["continuity", "cosign", "--note", str(note),
                 "--witness-key", str(tmp / "w_priv.pem"),
                 "--witness-name", _WNAME, "--time", ts])


def _verify(script: Path, ledger: Path, *, cp_pub: Path, log_pub,
            witness_key=None, witness_name=None) -> dict:
    argv = [sys.executable, str(script), str(ledger), "--key", str(cp_pub),
            "--iss", _ISS, "--aud", _AUD, "--json", "--log-key", str(log_pub)]
    if witness_key is not None:
        argv += ["--witness-key", str(witness_key)]
    if witness_name is not None:
        argv += ["--witness-name", witness_name]
    r = subprocess.run(argv, capture_output=True, text=True)
    return {"rc": r.returncode, "out": r.stdout, "err": r.stderr}


def test_cosign_appends_verifying_0x04(tmp_path) -> None:
    ledger, log_pub = _rail_checkpoint(tmp_path)
    w = _make_witness(tmp_path)
    note = ledger / "checkpoint.note"
    before = note.read_text(encoding="utf-8")
    assert _cosign(tmp_path, note, "1700000000") == 0
    after = note.read_text(encoding="utf-8")
    assert after.startswith(before)
    assert ccs.count_verified_cosignatures(after, _WNAME, w.public_key()) == 1
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  log_pub=log_pub, witness_key=tmp_path / "w_pub.pem",
                  witness_name=_WNAME)
    assert res["rc"] == 0, res["err"]
    cpk = json.loads(res["out"])["checkpoint"]
    assert cpk["verified"] and cpk["witness_verified"] == 1


def test_verifier_refuses_witness_key_without_name(tmp_path) -> None:
    ledger, log_pub = _rail_checkpoint(tmp_path)
    _make_witness(tmp_path)
    note = ledger / "checkpoint.note"
    assert _cosign(tmp_path, note, "1700000000") == 0
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  log_pub=log_pub, witness_key=tmp_path / "w_pub.pem",
                  witness_name=None)
    assert res["rc"] != 0  # __s179_p4_refusal_contract_v1__
    v = json.loads(res["out"])
    assert v["verdict"] == "FAIL"
    assert "--witness-name" in v["error"]


def test_verifier_wrong_pinned_name_counts_zero(tmp_path) -> None:
    ledger, log_pub = _rail_checkpoint(tmp_path)
    _make_witness(tmp_path)
    note = ledger / "checkpoint.note"
    assert _cosign(tmp_path, note, "1700000000") == 0
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  log_pub=log_pub, witness_key=tmp_path / "w_pub.pem",
                  witness_name="attacker.example/x")
    assert res["rc"] == 0, res["err"]
    assert json.loads(res["out"])["checkpoint"]["witness_verified"] == 0


def test_unwitnessed_checkpoint_byte_identical(tmp_path) -> None:
    ledger, log_pub = _rail_checkpoint(tmp_path)
    note = ledger / "checkpoint.note"
    original = note.read_bytes()
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  log_pub=log_pub)
    assert res["rc"] == 0, res["err"]
    cpk = json.loads(res["out"])["checkpoint"]
    assert cpk["verified"] and cpk["witness_verified"] == 0
    assert note.read_bytes() == original


def test_cosign_idempotent_on_identity(tmp_path) -> None:
    ledger, _log_pub = _rail_checkpoint(tmp_path)
    _make_witness(tmp_path)
    note = ledger / "checkpoint.note"
    assert _cosign(tmp_path, note, "1700000000") == 0
    once = note.read_bytes()
    assert _cosign(tmp_path, note, "1700000001") == 0
    assert note.read_bytes() == once
