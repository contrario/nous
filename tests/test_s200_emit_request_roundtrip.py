"""S200: --emit-request CLI surface + golden real-litewitness round trip.

Legs:
  1-2. The --emit-request CLI (cli.cmd_emit_request) emits bytes IDENTICAL to
       the folded emit_add_checkpoint_body for genesis (old=0) and incremental
       (old=2) paths, over a fixed log key and a fixed store. Deterministic, no
       witness.
  3.   A GOLDEN 0x04 Ed25519 cosignature captured from a REAL local litewitness
       (Filippo's torchwood, C2SP tlog-witness) over a fixed genesis checkpoint
       verifies through the shipped verify-before-include assembler AND the
       shipped assembled offline verifier (verify_offline.py), end to end.
       CI-portable: the cosignature is pinned bytes; no witness runs in CI.

HONEST LINE: the operator-run litewitness that produced the golden cosignature
is a TEST HARNESS proving the MECHANISM and the WIRE INTEROP -- it is NOT a trust
root and confers NO independence (operator-run == operator-internal, REJECTED by
the S199 decision). This test EVIDENCES that the emit/assemble/verify pipeline is
byte-correct and wire-compatible with real C2SP witness software; it does NOT
evidence witnessed non-equivocation. Independence arrives ONLY at the real
network join (a config-only swap of the pinned witness keys; the log key carries
across). "proves" stays reserved for Z3/Farkas.

# __s200_emit_request_roundtrip_v1__
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

import cli
EL = pytest.importorskip("envelope_ledger")
CC = pytest.importorskip("continuity_cosign")
RK = pytest.importorskip("rekor_v2_offline")
PROD = pytest.importorskip("envelope_witness_producer")
CV = pytest.importorskip("cli_verify")
DOSSIER = pytest.importorskip("dossier")

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from rekor_checkpoint import parse_checkpoint

TEMPLATE = (
    Path(__file__).resolve().parent.parent / "aml_transaction_governance.nous"
)

GOLDEN_FIXED_PCE = (
    "7ccccd454669fb78ff891d813c77573fdec9582acd08573d6f6a6275f78934e8"
)
GOLDEN_ORIGIN = (
    "nous-lang.org/envelope/"
    "a3559358b4d30c17110cdff012d8d25c41fbdb829821ab0cd077b72a8ec13f1c"
)
GOLDEN_CHECKPOINT_NOTE = (
    "nous-lang.org/envelope/"
    "a3559358b4d30c17110cdff012d8d25c41fbdb829821ab0cd077b72a8ec13f1c\n"
    "1\n"
    "AJbtVvmJqiJN0CKq9jQ/1Wpf4mc1OfLyF5RWxgP8Aqs=\n"
    "\n"
    "\u2014 nous-lang.org/envelope/"
    "a3559358b4d30c17110cdff012d8d25c41fbdb829821ab0cd077b72a8ec13f1c "
    "DvzWLwGVr7lN2p67eFcPEim8IisVIiuQ7p7AozRmeAMfg0eXPOicTbJWq+1mXHxPu0H8"
    "AtDowx9wskXQDg2HdRzMMAU=\n"
)
GOLDEN_PIN_NAME = "nous-lang.org/s200-test-witness"
GOLDEN_PIN_PUBKEY_B64 = "TP/cLe+TqK3nuocow6b0sc2bXHRUoieGaVfhiFfETgw="
GOLDEN_COSIG_LINE = (
    "\u2014 nous-lang.org/s200-test-witness "
    "yNWdXQAAAABqRl0oR8YfU3B1mod3HsL450RMf5r4GszqDQDVNBc2LxGj9LLj5GPIBtik"
    "vd12FdcGBZ7xLb5vDJUCIt90acJB0n2ECA=="
)
GOLDEN_PINS = [{"name": GOLDEN_PIN_NAME, "pubkey_b64": GOLDEN_PIN_PUBKEY_B64}]

_FIXED_SEED = bytes(range(32))


def _fixed_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_FIXED_SEED)


def _pce(i: int) -> str:
    return hashlib.sha256(("pce-%d" % i).encode()).hexdigest()


def _write_store(store_path: Path, pairs) -> None:
    lines = []
    for pce_sha256, anchor in pairs:
        rec = {
            "schema_version": EL.LEDGER_SCHEMA_VERSION,
            "commitment": EL.envelope_commitment(pce_sha256, anchor).hex(),
            "pce_sha256": pce_sha256,
            "pce_anchor_sha256": anchor,
        }
        lines.append(json.dumps(rec, sort_keys=True, separators=(",", ":")))
    store_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _make_log(pairs) -> "EL.EnvelopeLog":
    log = EL.EnvelopeLog()
    for pce_sha256, anchor in pairs:
        log.append(EL.envelope_commitment(pce_sha256, anchor))
    return log


def _write_key(path: Path) -> None:
    pem = _fixed_key().private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    path.write_bytes(pem)


def _run_cli_emit(tmp_path, n_store, prev, tag):
    pairs = [(_pce(i), None) for i in range(n_store)]
    store = tmp_path / (tag + "_store.jsonl")
    _write_store(store, pairs)
    key_path = tmp_path / (tag + "_log.key")
    _write_key(key_path)
    out = tmp_path / (tag + "_req.bin")
    ns = argparse.Namespace(
        prev_size=prev, store_path=str(store),
        log_key_path=str(key_path), out=str(out),
    )
    assert cli.cmd_emit_request(ns) == 0
    body = out.read_bytes()
    expected, _ = PROD.emit_add_checkpoint_body(
        _make_log(pairs), _fixed_key(), prev
    )
    assert body == expected
    return body


def test_cli_emit_genesis_matches_folded(tmp_path):
    body = _run_cli_emit(tmp_path, 1, 0, "gen")
    assert body.startswith(b"old 0\n\n")


def test_cli_emit_incremental_matches_folded(tmp_path):
    body = _run_cli_emit(tmp_path, 4, 2, "inc")
    assert body.startswith(b"old 2\n")


def test_cli_emit_refuses_empty_store(tmp_path):
    store = tmp_path / "empty.jsonl"
    store.write_text("", encoding="utf-8")
    key_path = tmp_path / "k.key"
    _write_key(key_path)
    ns = argparse.Namespace(
        prev_size=0, store_path=str(store),
        log_key_path=str(key_path), out=str(tmp_path / "o.bin"),
    )
    assert cli.cmd_emit_request(ns) == 1


def test_golden_cosig_verifies_and_assembles():
    cp = parse_checkpoint(GOLDEN_CHECKPOINT_NOTE)
    raw_pub = base64.b64decode(GOLDEN_PIN_PUBKEY_B64)
    pub = Ed25519PublicKey.from_public_bytes(raw_pub)
    parts = GOLDEN_COSIG_LINE.split(" ")
    blob = base64.b64decode(parts[2])
    assert CC.verify_cosignature_entry(
        cp.note_text_bytes, GOLDEN_PIN_NAME, pub,
        parts[1], blob[:4], blob[4:],
    )
    sidecar = PROD.assemble_witness_sidecar(
        GOLDEN_CHECKPOINT_NOTE, [GOLDEN_COSIG_LINE], GOLDEN_PINS, 1,
        fan_pairs=[(GOLDEN_FIXED_PCE, None)],
    )
    assert sidecar["threshold"] == 1
    assert len(sidecar["witnesses"]) == 1
    assert sidecar["fan"] == [[GOLDEN_FIXED_PCE, None]]


class _Args:
    smt = True
    prices = None
    timeout_ms = 30000
    no_manifest = False
    smt_margin = 0
    no_lint = True
    lint_strict = False
    lint_error_on = None
    supersedes = None
    chain_coverage = None
    gap_witness = False
    coverage_threshold = None
    materiality_against = None
    materiality_threshold_pct = 10.0
    pce = None
    pce_baseline = None
    pce_anchor = None
    witness = None

    def __init__(self, **over: object) -> None:
        for k, v in over.items():
            setattr(self, k, v)


def _run_verifier(out: Path):
    import os
    proc = subprocess.run(
        [sys.executable, "verify_offline.py"],
        cwd=str(out), capture_output=True, text=True, env=dict(os.environ),
    )
    verdict = None
    for line in proc.stdout.splitlines():
        if line.startswith("ENVELOPE_WITNESS_VERDICT_JSON:"):
            verdict = json.loads(line.split(":", 1)[1].strip())
    return proc.returncode, verdict


def _build_dossier(tmp_path, sidecar_bytes, tag):
    src = tmp_path / (tag + "_source.nous")
    src.write_bytes(TEMPLATE.read_bytes())
    wfile = tmp_path / (tag + "_witness.json")
    wfile.write_bytes(sidecar_bytes)
    mout = tmp_path / (tag + "_source.manifest.json")
    rc = CV.cmd_verify(_Args(
        file=str(src), manifest_out=str(mout),
        key_path=str(tmp_path / (tag + "_signing.key")), witness=str(wfile),
    ))
    assert rc == 0
    out = tmp_path / (tag + "_out")
    DOSSIER.build_dossier(src, manifest=mout, output=out)
    return out


@pytest.mark.skipif(not TEMPLATE.is_file(), reason="aml demo source not present")
def test_golden_assembled_verifier_end_to_end(tmp_path):
    sidecar = PROD.assemble_witness_sidecar(
        GOLDEN_CHECKPOINT_NOTE, [GOLDEN_COSIG_LINE], GOLDEN_PINS, 1,
        fan_pairs=[(GOLDEN_FIXED_PCE, None)],
    )
    sc_bytes = json.dumps(
        sidecar, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    out = _build_dossier(tmp_path, sc_bytes, "golden")
    assert (out / "verify_offline.py").is_file()
    (out / "witness_keys.json").write_text(
        json.dumps({"witnesses": GOLDEN_PINS}), encoding="utf-8"
    )
    rc, v = _run_verifier(out)
    assert rc == 0 and v is not None
    assert v["met"] is True
    assert v["key_provenance"] == "auditor-pinned"
    assert v["verified_names"] == [GOLDEN_PIN_NAME]
    assert v["origin"] == GOLDEN_ORIGIN
