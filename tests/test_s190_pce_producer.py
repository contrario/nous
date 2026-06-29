"""S190 PCE Inc 3c: producer functional test -- `nous verify --pce`.

Exercises the wired sign-path producer end to end through the real cmd_verify:
  - --pce + --pce-baseline binds pce_sha256 into the SIGNED manifest (validated
    well-formed via envelope.parse_envelope; baseline.canon sha == the envelope
    baseline_canon_sha256) and writes pce.json + baseline.canon next to the
    manifest; build_dossier carries them (+ derives spec.canon) and the emitted
    offline verifier evidences cumulative membership.
  - WITHIN  (baseline == current canon) -> verifier rc 0, verdict WITHIN.
  - OUTSIDE (baseline = current + an immutable-SA line) -> rc 0, verdict OUTSIDE
    + breakout (monitor, never gate).
  - --pce-baseline sha mismatch / missing --pce-baseline / --gap-witness ->
    REFUSED, no manifest written.
  - omitted -> no pce.json, no manifest field (byte-identical path).

The current obligations canon is captured deterministically from a bootstrap
build (build_dossier writes spec.canon when a PCE is carried).

# __s190_pce_producer_v1__
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

cmd_verify = pytest.importorskip("cli_verify").cmd_verify
build_dossier = pytest.importorskip("dossier").build_dossier
pytest.importorskip("envelope")

TEMPLATE = Path(__file__).resolve().parent.parent / "aml_transaction_governance.nous"

_DISC = "not a legal substantiality determination"


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

    def __init__(self, **over: object) -> None:
        for k, v in over.items():
            setattr(self, k, v)


def _src(tmp_path: Path) -> Path:
    src = tmp_path / "source.nous"
    src.write_bytes(TEMPLATE.read_bytes())
    return src


def _env_doc(base_sha: str, *, sa_mutable: bool) -> dict:
    return {
        "pce_schema_version": 1,
        "baseline_canon_sha256": base_sha,
        "per_step": {
            "SA": {"mutable": sa_mutable},
            "GA": {"may_add": True, "may_remove": ["transfer"]},
            "GQ": {"may_add": True, "may_remove": False,
                   "quorum_bounds": {"approve": {"min": 2, "max": None}}},
        },
        "basis": "membership against a pre-committed envelope; " + _DISC,
        "declared_utc": "2026-06-29T00:00:00+00:00",
        "cumulative": {
            "SA": {"mutable": sa_mutable},
            "GA": {"total_removable": ["transfer"], "total_addable": None},
            "GQ": {"quorum_drift_budget": {"approve": 5}},
        },
    }


def _run_verifier(out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(out / "verify_offline.py")],
        capture_output=True, text=True,
    )


def _current_canon(tmp_path: Path, src: Path) -> str:
    bd = tmp_path / "boot"
    bd.mkdir()
    boot_base = bd / "baseline.canon"
    boot_base.write_text("NV:0", encoding="utf-8")
    boot_env = _env_doc(hashlib.sha256(b"NV:0").hexdigest(), sa_mutable=True)
    boot_pce = bd / "pce.json"
    boot_pce.write_text(json.dumps(boot_env), encoding="utf-8")
    mout = bd / "boot.manifest.json"
    rc = cmd_verify(_Args(
        file=str(src), manifest_out=str(mout),
        key_path=str(bd / "signing.key"),
        pce=str(boot_pce), pce_baseline=str(boot_base),
    ))
    assert rc == 0, "bootstrap cmd_verify failed"
    out = bd / "out"
    build_dossier(src, manifest=mout, output=out)
    return (out / "spec.canon").read_text(encoding="utf-8")


def _bind(tmp_path, src, baseline_text, *, sa_mutable):
    base_f = tmp_path / "baseline.canon"
    base_f.write_text(baseline_text, encoding="utf-8")
    env = _env_doc(hashlib.sha256(baseline_text.encode("utf-8")).hexdigest(),
                   sa_mutable=sa_mutable)
    pce_f = tmp_path / "envelope.json"
    pce_f.write_text(json.dumps(env), encoding="utf-8")
    mout = tmp_path / "source.manifest.json"
    rc = cmd_verify(_Args(
        file=str(src), manifest_out=str(mout),
        key_path=str(tmp_path / "signing.key"),
        pce=str(pce_f), pce_baseline=str(base_f),
    ))
    return rc, mout, pce_f


def test_producer_within_routes_within(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src = _src(tmp_path)
    canon = _current_canon(tmp_path, src)
    rc, mout, pce_f = _bind(tmp_path, src, canon, sa_mutable=True)
    assert rc == 0
    assert (tmp_path / "pce.json").is_file()
    assert (tmp_path / "baseline.canon").is_file()
    doc = json.loads(mout.read_text())
    assert (
        hashlib.sha256((tmp_path / "pce.json").read_bytes()).hexdigest()
        == doc["pce_sha256"]
    )
    out = tmp_path / "out"
    build_dossier(src, manifest=mout, output=out)
    proc = _run_verifier(out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert '"verdict":"WITHIN"' in proc.stdout


def test_producer_outside_routes_outside(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src = _src(tmp_path)
    canon = _current_canon(tmp_path, src)
    baseline = canon + "\nSA:zzz_pce_breakout(a,b)"
    rc, mout, pce_f = _bind(tmp_path, src, baseline, sa_mutable=False)
    assert rc == 0
    out = tmp_path / "out"
    build_dossier(src, manifest=mout, output=out)
    proc = _run_verifier(out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert '"verdict":"OUTSIDE"' in proc.stdout
    assert "breakout:" in proc.stdout


def test_producer_baseline_mismatch_refused(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src = _src(tmp_path)
    base_f = tmp_path / "baseline.canon"
    base_f.write_text("NV:1\nGA:approve", encoding="utf-8")
    env = _env_doc("a" * 64, sa_mutable=True)  # commits to a sha != file
    pce_f = tmp_path / "envelope.json"
    pce_f.write_text(json.dumps(env), encoding="utf-8")
    mout = tmp_path / "source.manifest.json"
    rc = cmd_verify(_Args(
        file=str(src), manifest_out=str(mout),
        key_path=str(tmp_path / "signing.key"),
        pce=str(pce_f), pce_baseline=str(base_f),
    ))
    assert rc == 1
    assert not mout.is_file()


def test_producer_requires_baseline(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src = _src(tmp_path)
    env = _env_doc("b" * 64, sa_mutable=True)
    pce_f = tmp_path / "envelope.json"
    pce_f.write_text(json.dumps(env), encoding="utf-8")
    mout = tmp_path / "source.manifest.json"
    rc = cmd_verify(_Args(
        file=str(src), manifest_out=str(mout),
        key_path=str(tmp_path / "signing.key"),
        pce=str(pce_f),
    ))
    assert rc == 1
    assert not mout.is_file()


def test_producer_refused_with_gap_witness(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src = _src(tmp_path)
    env = _env_doc("c" * 64, sa_mutable=True)
    pce_f = tmp_path / "envelope.json"
    pce_f.write_text(json.dumps(env), encoding="utf-8")
    mout = tmp_path / "source.manifest.json"
    rc = cmd_verify(_Args(
        file=str(src), manifest_out=str(mout),
        key_path=str(tmp_path / "signing.key"),
        coverage_threshold="amount > 5000",
        gap_witness=True,
        pce=str(pce_f), pce_baseline=str(tmp_path / "nope.canon"),
    ))
    assert rc == 1
    assert not (tmp_path / "pce.json").is_file()


def test_producer_omitted_is_byte_identical_path(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src = _src(tmp_path)
    mout = tmp_path / "source.manifest.json"
    rc = cmd_verify(_Args(
        file=str(src), manifest_out=str(mout),
        key_path=str(tmp_path / "signing.key"),
    ))
    assert rc == 0
    doc = json.loads(mout.read_text())
    assert "pce_sha256" not in doc
    assert not (tmp_path / "pce.json").is_file()
    assert not (tmp_path / "baseline.canon").is_file()
