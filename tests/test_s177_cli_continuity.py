from __future__ import annotations

# __s177_cli_continuity_tests_v1__
# Exercises the nous continuity CLI surfaces (link / receipt / verify /
# emit-verifier) through the real cli.main dispatch, asserts the key-separated
# independence invariant (link never accepts a private key), and cross-checks
# the emitted zero-NOUS verifier against the in-process walk (anti-drift).

import base64
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import continuity_ledger as cl
import continuity_verifier as cv

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

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


def _write_dossier(d: Path, op: Ed25519PrivateKey, seq: int, head: str) -> None:
    d.mkdir(parents=True, exist_ok=True)
    trace = {"memory_consultation": {
        "world_sha256": _WORLD, "producing_soul_sha256": _SOUL,
        "consulted_chain_head": head, "consulted_seq_count": seq,
    }}
    trace["signature"] = _op_sign(op, cl._doc_canonical_body_bytes(trace))
    manifest = {"source_sha256": _h("src"), "smt_spec_sha256": _h("smt"),
                "pricing_sha256": _h("price")}
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


def _build_two_link_ledger(tmp: Path, op, cp, witnessed: bool = True) -> Path:
    ledger = tmp / "ledger"
    _write_dossier(tmp / "run0", op, 0, _h("h0"))
    _write_dossier(tmp / "run1", op, 1, _h("h1"))
    assert _run(["continuity", "link", "--dir", str(tmp / "run0"),
                 "--genesis", "--counterparty-key-uri", _ISS,
                 "--out", str(ledger / "000")]) == 0
    prev = json.loads(
        (ledger / "000" / "link.json").read_text())["this_link_digest"]
    assert _run(["continuity", "link", "--dir", str(tmp / "run1"),
                 "--prev", prev, "--counterparty-key-uri", _ISS,
                 "--out", str(ledger / "001")]) == 0
    if witnessed:
        for leaf in ("000", "001"):
            assert _run(["continuity", "receipt", "--dir", str(ledger / leaf),
                         "--key", str(tmp / "cp_priv.pem"), "--kid", "k1",
                         "--iss", _ISS, "--aud", _AUD]) == 0
    return ledger


def _emitted_verdict(script: Path, ledger: Path, key: Path) -> dict:
    r = subprocess.run(
        [sys.executable, str(script), str(ledger), "--key", str(key),
         "--iss", _ISS, "--aud", _AUD, "--json"],
        capture_output=True, text=True)
    return {"rc": r.returncode, "out": r.stdout, "err": r.stderr}


def test_parser_exposes_continuity_with_five_actions() -> None:  # __s178_p1b_five_actions_v1__
    import argparse
    import cli
    ap = cli.build_parser()
    root = [a for a in ap._actions
            if isinstance(a, argparse._SubParsersAction)][0]
    assert "continuity" in root.choices
    cont = root.choices["continuity"]
    actions = [a for a in cont._actions
               if isinstance(a, argparse._SubParsersAction)][0]
    assert set(actions.choices) == {"link", "receipt", "verify",
                                    "emit-verifier", "checkpoint"}


def test_link_action_carries_no_private_key_option() -> None:
    import argparse
    import cli
    ap = cli.build_parser()
    root = [a for a in ap._actions
            if isinstance(a, argparse._SubParsersAction)][0]
    sub = [a for a in root.choices["continuity"]._actions
           if isinstance(a, argparse._SubParsersAction)][0]
    link_opts = []
    for a in sub.choices["link"]._actions:
        link_opts.extend(a.option_strings)
    assert "--key" not in link_opts
    receipt_opts = []
    for a in sub.choices["receipt"]._actions:
        receipt_opts.extend(a.option_strings)
    assert "--key" in receipt_opts


def test_link_genesis_writes_link_and_copies_artifacts(tmp_path) -> None:
    op, _cp = _keys(tmp_path)
    _write_dossier(tmp_path / "run0", op, 0, _h("h0"))
    out = tmp_path / "ledger" / "000"
    assert _run(["continuity", "link", "--dir", str(tmp_path / "run0"),
                 "--genesis", "--out", str(out)]) == 0
    link = json.loads((out / "link.json").read_text())
    assert link["prev_run_digest"] == cl.GENESIS_PREV_RUN_DIGEST
    assert link["link_kind"] == "run"
    for fname in ("conformance.json", "trace.json", "manifest.json"):
        assert (out / fname).is_file()


def test_link_chained_prev_matches(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_two_link_ledger(tmp_path, op, cp, witnessed=False)
    a = json.loads((ledger / "000" / "link.json").read_text())
    b = json.loads((ledger / "001" / "link.json").read_text())
    assert b["prev_run_digest"] == a["this_link_digest"]


def test_link_refuses_internally_inconsistent_dossier(tmp_path) -> None:
    op, _cp = _keys(tmp_path)
    d = tmp_path / "run0"
    _write_dossier(d, op, 0, _h("h0"))
    man = json.loads((d / "manifest.json").read_text())
    man["source_sha256"] = _h("EVIL")
    (d / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    assert _run(["continuity", "link", "--dir", str(d), "--genesis",
                 "--out", str(tmp_path / "ledger" / "000")]) == 1


def test_receipt_writes_jws_and_binds_run_identity(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_two_link_ledger(tmp_path, op, cp, witnessed=False)
    leaf = ledger / "000"
    assert _run(["continuity", "receipt", "--dir", str(leaf),
                 "--key", str(tmp_path / "cp_priv.pem"), "--kid", "k1",
                 "--iss", _ISS, "--aud", _AUD]) == 0
    receipt = json.loads((leaf / "receipt.jws").read_text())
    claims = json.loads(cl._b64url_decode(receipt["payload"]))
    link = json.loads((leaf / "link.json").read_text())
    assert claims["sub"] == link["run_identity_digest"]
    assert claims["iss"] == _ISS and claims["aud"] == _AUD


def test_verify_passes_witnessed_with_key(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_two_link_ledger(tmp_path, op, cp, witnessed=True)
    assert _run(["continuity", "verify", "--ledger", str(ledger),
                 "--key", str(tmp_path / "cp_pub.pem"), "--iss", _ISS,
                 "--aud", _AUD]) == 0


def test_verify_passes_no_key_chain_only(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_two_link_ledger(tmp_path, op, cp, witnessed=True)
    assert _run(["continuity", "verify", "--ledger", str(ledger)]) == 0


def test_verify_fails_tampered_cert(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_two_link_ledger(tmp_path, op, cp, witnessed=True)
    cert = json.loads((ledger / "001" / "conformance.json").read_text())
    cert["source_sha256"] = _h("EVIL")
    (ledger / "001" / "conformance.json").write_text(
        json.dumps(cert), encoding="utf-8")
    assert _run(["continuity", "verify", "--ledger", str(ledger),
                 "--key", str(tmp_path / "cp_pub.pem"), "--iss", _ISS,
                 "--aud", _AUD]) == 1


def test_verify_fails_wrong_key(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_two_link_ledger(tmp_path, op, cp, witnessed=True)
    other = Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo)
    (tmp_path / "other.pem").write_bytes(other)
    assert _run(["continuity", "verify", "--ledger", str(ledger),
                 "--key", str(tmp_path / "other.pem"), "--iss", _ISS,
                 "--aud", _AUD]) == 1


def test_emit_verifier_writes_script_round_trip(tmp_path) -> None:
    assert _run(["continuity", "emit-verifier", "--out", str(tmp_path)]) == 0
    script = tmp_path / "verify_continuity_offline.py"
    assert script.is_file()
    emitted = script.read_text(encoding="utf-8")
    assert hashlib.sha256(emitted.encode("utf-8")).hexdigest() == \
        hashlib.sha256(cv.CONTINUITY_VERIFY_OFFLINE_PY.encode("utf-8")
                       ).hexdigest()


def test_emitted_script_verifies_cli_built_ledger(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_two_link_ledger(tmp_path, op, cp, witnessed=True)
    assert _run(["continuity", "emit-verifier", "--out", str(tmp_path)]) == 0
    res = _emitted_verdict(tmp_path / "verify_continuity_offline.py",
                           ledger, tmp_path / "cp_pub.pem")
    assert res["rc"] == 0, res["err"]
    verdict = json.loads(res["out"])
    assert verdict["verdict"] == "PASS"
    assert verdict["n_witnessed_verified"] == 2


def test_emitted_script_matches_in_process_walk(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_two_link_ledger(tmp_path, op, cp, witnessed=True)
    bundles = []
    for leaf in ("000", "001"):
        d = ledger / leaf
        bundles.append({
            "cert": json.loads((d / "conformance.json").read_text()),
            "trace": json.loads((d / "trace.json").read_text()),
            "manifest": json.loads((d / "manifest.json").read_text()),
            "link": json.loads((d / "link.json").read_text()),
            "receipt": json.loads((d / "receipt.jws").read_text()),
        })
    rep = cl.walk_continuity_ledger(
        bundles, counterparty_keys={_ISS: (tmp_path / "cp_pub.pem").read_bytes()},
        expected_audience=_AUD)
    assert _run(["continuity", "emit-verifier", "--out", str(tmp_path)]) == 0
    res = _emitted_verdict(tmp_path / "verify_continuity_offline.py",
                           ledger, tmp_path / "cp_pub.pem")
    verdict = json.loads(res["out"])
    assert verdict["n_links"] == rep["n_links"]
    assert verdict["n_witnessed_verified"] == rep["n_witnessed"]


def test_emitted_script_fails_on_tamper(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_two_link_ledger(tmp_path, op, cp, witnessed=True)
    assert _run(["continuity", "emit-verifier", "--out", str(tmp_path)]) == 0
    link = json.loads((ledger / "000" / "link.json").read_text())
    link["this_link_digest"] = _h("forged")
    (ledger / "000" / "link.json").write_text(
        json.dumps(link), encoding="utf-8")
    res = _emitted_verdict(tmp_path / "verify_continuity_offline.py",
                           ledger, tmp_path / "cp_pub.pem")
    assert res["rc"] == 1


def test_receipt_issued_at_is_present(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_two_link_ledger(tmp_path, op, cp, witnessed=True)
    receipt = json.loads((ledger / "000" / "receipt.jws").read_text())
    claims = json.loads(cl._b64url_decode(receipt["payload"]))
    assert isinstance(claims.get("iat"), int)
    assert claims["iat"] <= int(time.time()) + 5
