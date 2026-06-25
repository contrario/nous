from __future__ import annotations

# __s178_checkpoint_leg_tests_v1__
# Drives the real `nous continuity checkpoint` producer and the emitted
# zero-NOUS verifier (subprocess) end to end: budget envelope accept, rail-only,
# Strict-Ignore fallback, and the checkpoint fail-closed branches (root
# substitution, sidecar tamper, wrong log key). No producer mock.

import base64
import hashlib
import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import continuity_ledger as cl

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from manifest import load_or_create_keypair

_ISS = "https://counterparty.example/keys/ed25519-1"
_WORLD = hashlib.sha256(b"world").hexdigest()
_SOUL = hashlib.sha256(b"soul").hexdigest()
_AUD = "world:" + _WORLD


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


def _build_priced_ledger(tmp: Path, op, cp, caps) -> Path:
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


def _verify(script: Path, ledger: Path, *, cp_pub: Path,
            log_pub=None) -> dict:
    argv = [sys.executable, str(script), str(ledger), "--key", str(cp_pub),
            "--iss", _ISS, "--aud", _AUD, "--json"]
    if log_pub is not None:
        argv += ["--log-key", str(log_pub)]
    r = subprocess.run(argv, capture_output=True, text=True)
    return {"rc": r.returncode, "out": r.stdout, "err": r.stderr}


def _emit(tmp: Path) -> Path:
    assert _run(["continuity", "emit-verifier", "--out", str(tmp)]) == 0
    return tmp / "verify_continuity_offline.py"


def test_checkpoint_cli_writes_note_and_sidecar(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_priced_ledger(tmp_path, op, cp, ["0.10", "0.20"])
    logkey = tmp_path / "logkey"
    assert _run(["continuity", "checkpoint", "--ledger", str(ledger),
                 "--log-key", str(logkey), "--budget", "1.00"]) == 0
    assert (ledger / "checkpoint.note").is_file()
    assert (ledger / "aggregate.cost.farkas.json").is_file()


def test_emitted_verifier_accepts_budget_checkpoint(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_priced_ledger(tmp_path, op, cp, ["0.10", "0.20"])
    logkey = tmp_path / "logkey"
    assert _run(["continuity", "checkpoint", "--ledger", str(ledger),
                 "--log-key", str(logkey), "--budget", "1.00"]) == 0
    log_pub = _log_pub_pem(tmp_path, logkey)
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  log_pub=log_pub)
    assert res["rc"] == 0, res["err"]
    v = json.loads(res["out"])
    assert v["verdict"] == "PASS"
    cpk = v["checkpoint"]
    assert cpk["present"] and cpk["verified"]
    assert cpk["mode"] == "budget"
    assert cpk["tree_size"] == 2
    assert cpk["budget"] == str(Fraction("1.00"))


def test_rail_only_checkpoint_verifies(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_priced_ledger(tmp_path, op, cp, ["0.10", "0.20"])
    logkey = tmp_path / "logkey"
    assert _run(["continuity", "checkpoint", "--ledger", str(ledger),
                 "--log-key", str(logkey)]) == 0
    assert not (ledger / "aggregate.cost.farkas.json").is_file()
    log_pub = _log_pub_pem(tmp_path, logkey)
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  log_pub=log_pub)
    assert res["rc"] == 0, res["err"]
    cpk = json.loads(res["out"])["checkpoint"]
    assert cpk["verified"] and cpk["mode"] == "rail" and cpk["budget"] is None


def test_strict_ignore_without_log_key(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_priced_ledger(tmp_path, op, cp, ["0.10", "0.20"])
    logkey = tmp_path / "logkey"
    assert _run(["continuity", "checkpoint", "--ledger", str(ledger),
                 "--log-key", str(logkey), "--budget", "1.00"]) == 0
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem", log_pub=None)
    assert res["rc"] == 0, res["err"]
    assert "checkpoint.note present but unverified" in res["err"]
    cpk = json.loads(res["out"])["checkpoint"]
    assert cpk["present"] and not cpk["verified"] and cpk["mode"] == "ignored"


def test_verifier_refuses_root_substitution(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_priced_ledger(tmp_path, op, cp, ["0.10", "0.20"])
    logkey = tmp_path / "logkey"
    assert _run(["continuity", "checkpoint", "--ledger", str(ledger),
                 "--log-key", str(logkey), "--budget", "1.00"]) == 0
    note = (ledger / "checkpoint.note").read_text(encoding="utf-8")
    lines = note.split("\n")
    lines[2] = base64.b64encode(b"\x00" * 32).decode("ascii")
    (ledger / "checkpoint.note").write_text("\n".join(lines), encoding="utf-8")
    log_pub = _log_pub_pem(tmp_path, logkey)
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  log_pub=log_pub)
    assert res["rc"] == 1


def test_verifier_refuses_sidecar_tamper(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_priced_ledger(tmp_path, op, cp, ["0.10", "0.20"])
    logkey = tmp_path / "logkey"
    assert _run(["continuity", "checkpoint", "--ledger", str(ledger),
                 "--log-key", str(logkey), "--budget", "1.00"]) == 0
    side = ledger / "aggregate.cost.farkas.json"
    side.write_bytes(side.read_bytes() + b" ")
    log_pub = _log_pub_pem(tmp_path, logkey)
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  log_pub=log_pub)
    assert res["rc"] == 1


def test_verifier_refuses_wrong_log_key(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_priced_ledger(tmp_path, op, cp, ["0.10", "0.20"])
    logkey = tmp_path / "logkey"
    assert _run(["continuity", "checkpoint", "--ledger", str(ledger),
                 "--log-key", str(logkey), "--budget", "1.00"]) == 0
    other = Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo)
    (tmp_path / "other_log.pem").write_bytes(other)
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  log_pub=tmp_path / "other_log.pem")
    assert res["rc"] == 1
