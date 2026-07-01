"""S196 Inc D: envelope-witness producer + assembled verify_offline.py regression.

The permanent assembled-run test (operating-method #12): the S194 splice is run
ASSEMBLED (the actual verify_offline.py an auditor runs), not the embed in
isolation. Ceremony at e+1 with 3 INDEPENDENT ephemeral witnesses (a test stand-
in for real independent parties), a real e->e+1 successor cosignature, then
envelope_witness_producer.assemble_witness_sidecar (--assemble-only path), then
the full assembled matrix + two negatives.

# __s196_incd_assembled_run_test_v1__
"""
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

EL = pytest.importorskip("envelope_ledger")
CC = pytest.importorskip("continuity_cosign")
RK = pytest.importorskip("rekor_v2_offline")
PROD = pytest.importorskip("envelope_witness_producer")
CV = pytest.importorskip("cli_verify")
DOSSIER = pytest.importorskip("dossier")

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

TEMPLATE = (
    Path(__file__).resolve().parent.parent / "aml_transaction_governance.nous"
)


def _raw_pub_b64(priv: Ed25519PrivateKey) -> str:
    raw = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


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


def _witness_cosign(name, priv, last_size, last_root, leaves_now, ckpt_now):
    n = len(leaves_now)
    proof = [] if last_size == 0 else RK.naive_consistency_proof(leaves_now, last_size)
    try:
        RK.verify_consistency(last_size, n, last_root, ckpt_now["env_root"], proof)
    except RK.VerificationError:
        return None
    return CC.build_cosignature_line(
        ckpt_now["note_text_bytes"], name, priv, int(time.time())
    )


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


def _run_verifier(out: Path, env=None):
    import os
    e = dict(os.environ)
    if env:
        e.update(env)
    proc = subprocess.run(
        [sys.executable, "verify_offline.py"],
        cwd=str(out), capture_output=True, text=True, env=e,
    )
    verdict = None
    for line in proc.stdout.splitlines():
        if line.startswith("ENVELOPE_WITNESS_VERDICT_JSON:"):
            verdict = json.loads(line.split(":", 1)[1].strip())
    return proc.returncode, verdict


def _ceremony(tmp_path):
    """Build a real e->e+1 ceremony; return (checkpoint_note, cosig_lines,
    pins, store_path, fan_pairs, witness_keys_obj)."""
    log_key = Ed25519PrivateKey.generate()
    wnames = ["witness-1.example", "witness-2.example", "witness-3.example"]
    wkeys = [Ed25519PrivateKey.generate() for _ in wnames]
    pins = [{"name": n, "pubkey_b64": _raw_pub_b64(k)} for n, k in zip(wnames, wkeys)]

    pairs_e = [(_pce(0), None), (_pce(1), None)]
    pairs_e1 = pairs_e + [(_pce(2), None), (_pce(3), None)]
    m = len(pairs_e)

    log_e = _make_log(pairs_e)
    ckpt_e = EL.build_envelope_checkpoint(log_e, log_key)
    log_e1 = _make_log(pairs_e1)
    ckpt_e1 = EL.build_envelope_checkpoint(log_e1, log_key)
    leaves_e1 = log_e1.leaves()

    # Establish each witness's last-seen head at epoch e, then cosign the e+1
    # successor after a real RFC 9162 consistency check e->e+1.
    lines = []
    for name, k in zip(wnames, wkeys):
        line = _witness_cosign(name, k, m, ckpt_e["env_root"], leaves_e1, ckpt_e1)
        assert line is not None
        lines.append(line)

    store_path = tmp_path / "log.jsonl"
    _write_store(store_path, pairs_e1)
    witness_keys_obj = {"witnesses": pins}
    return ckpt_e1["envelope_note"], lines, pins, store_path, pairs_e1, witness_keys_obj


def test_load_fan_pairs_order_equals_leaf_and_checkpoint_order(tmp_path):
    pairs = [(_pce(i), None) for i in range(5)]
    store_path = tmp_path / "log.jsonl"
    _write_store(store_path, pairs)
    fan = EL.load_fan_pairs(store_path)
    log = EL.load_log(store_path)
    fan_commitments = [EL.envelope_commitment(p, a) for (p, a) in fan]
    assert fan_commitments == log.order
    log_key = Ed25519PrivateKey.generate()
    ckpt = EL.build_envelope_checkpoint(log, log_key)
    assert len(fan) == ckpt["env_size"]
    leaves = [EL.ENVELOPE_LEAF_PREFIX + c for c in fan_commitments]
    assert RK._naive_root(leaves) == ckpt["env_root"]


def test_load_fan_pairs_dedup_identical_to_load_log(tmp_path):
    pairs = [(_pce(0), None), (_pce(1), None), (_pce(0), None), (_pce(2), None)]
    store_path = tmp_path / "log.jsonl"
    _write_store(store_path, pairs)
    fan = EL.load_fan_pairs(store_path)
    log = EL.load_log(store_path)
    assert [EL.envelope_commitment(p, a) for (p, a) in fan] == log.order
    assert [p for (p, a) in fan] == [_pce(0), _pce(1), _pce(2)]


def test_producer_assembles_valid_sidecar(tmp_path):
    note, lines, pins, store_path, fan_pairs, _ = _ceremony(tmp_path)
    sidecar = PROD.assemble_witness_sidecar(
        note, lines, pins, 2, store_path=store_path
    )
    assert sidecar["witness_schema_version"] == 1
    assert sidecar["threshold"] == 2
    assert len(sidecar["witnesses"]) == 3
    assert sidecar["fan"] == [[p, a] for (p, a) in fan_pairs]


def test_producer_refuses_unpinned_cosig_line(tmp_path):
    note, lines, pins, store_path, _, _ = _ceremony(tmp_path)
    rogue_key = Ed25519PrivateKey.generate()
    from rekor_checkpoint import parse_checkpoint
    cp = parse_checkpoint(note)
    rogue_line = CC.build_cosignature_line(
        cp.note_text_bytes, "rogue.example", rogue_key, int(time.time())
    )
    with pytest.raises(PROD.WitnessProducerError):
        PROD.assemble_witness_sidecar(
            note, lines + [rogue_line], pins, 2, store_path=store_path
        )


def test_producer_refuses_fan_not_reproducing_head(tmp_path):
    note, lines, pins, store_path, fan_pairs, _ = _ceremony(tmp_path)
    bad_store = tmp_path / "bad_log.jsonl"
    mutated = [(_pce(500), None)] + fan_pairs[1:]
    _write_store(bad_store, mutated)
    with pytest.raises(PROD.WitnessProducerError):
        PROD.assemble_witness_sidecar(
            note, lines, pins, 2, store_path=bad_store
        )


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
def test_assembled_verifier_full_matrix(tmp_path):
    note, lines, pins, store_path, fan_pairs, wkeys_obj = _ceremony(tmp_path)

    met = PROD.assemble_witness_sidecar(note, lines, pins, 2, store_path=store_path)
    met_bytes = json.dumps(met, sort_keys=True, separators=(",", ":")).encode("utf-8")
    out = _build_dossier(tmp_path, met_bytes, "met")
    assert (out / "verify_offline.py").is_file()
    assert (out / "envelope.witness.json").is_file()

    (out / "witness_keys.json").write_text(
        json.dumps(wkeys_obj), encoding="utf-8"
    )
    rc, v = _run_verifier(out)
    assert rc == 0 and v is not None
    assert v["met"] is True and v["key_provenance"] == "auditor-pinned"

    (out / "witness_keys.json").unlink()
    rc, v = _run_verifier(out)
    assert rc == 0 and v is not None
    assert v["met"] is True and v["key_provenance"] == "operator-supplied"

    (out / "envelope.witness.json").write_bytes(b'{"tampered":true}')
    rc, v = _run_verifier(out)
    assert rc == 1

    under = PROD.assemble_witness_sidecar(note, lines[:2], pins, 3, store_path=store_path)
    under_bytes = json.dumps(under, sort_keys=True, separators=(",", ":")).encode("utf-8")
    outu = _build_dossier(tmp_path, under_bytes, "under")
    rc, v = _run_verifier(outu)
    assert rc == 0 and v is not None and v["met"] is False


@pytest.mark.skipif(not TEMPLATE.is_file(), reason="aml demo source not present")
def test_assembled_verifier_tamper_b_fan_not_root(tmp_path):
    note, lines, pins, store_path, fan_pairs, _ = _ceremony(tmp_path)
    met = PROD.assemble_witness_sidecar(note, lines, pins, 2, store_path=store_path)
    met["fan"] = [[_pce(500), None]] + met["fan"][1:]
    bad_bytes = json.dumps(met, sort_keys=True, separators=(",", ":")).encode("utf-8")
    out = _build_dossier(tmp_path, bad_bytes, "tamperB")
    rc, v = _run_verifier(out)
    assert rc == 1
