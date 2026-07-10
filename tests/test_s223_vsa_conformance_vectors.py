"""S223: the published VSA conformance vector verifies offline and is pinned.

Verifies the COMMITTED bundle bytes (does not re-mint): the committed
verify_vsa_offline.py, run on the committed manifest/trace/cert/farkas/vsa
bytes, must exit 0 with VERDICT: PASS and both Farkas legs proven offline, and
its stdout must byte-match the committed expected_stdout.txt. Release- and
pricing-independent: a version or pricing change does not touch these frozen
bytes, so this test does not move with them.

The vector demonstrates FORMAT / implementation-independence (a foreign
verifier reproduces the canon, signatures, and the cost/coverage verdict
byte-for-byte). It says nothing about CONTENT (whether any obligation is
substantively correct). PROVES is the two Farkas legs (rational arithmetic,
stdlib + cryptography, no solver, no NOUS install); everything else EVIDENCES.
__s223_vsa_conformance_vectors_test_v1__
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_VEC = _REPO / "website" / ".well-known" / "nous" / "vsa-vectors" / "v1"

_EXPECTED = {
    "manifest.json":
        "af07541e745492fc38c0aa5d692e4a3ba4066fa88ced0abcfd8c967bee060ab7",
    "trace.json":
        "0d6648463650100f1604ca406b59e10193b54e5c2906f64cfee859ad6ca278d6",
    "conformance.json":
        "4208dffff1f2e5f96c80de3e006cafb76e6b167b5115a17042432d58f9ff4182",
    "coverage.farkas.json":
        "6f75675f870a1569cb5791d1d6434261aa08240d725dde5bd90820361c09f7f7",
    "cost.farkas.json":
        "ae5dc446cd5e24f766da60b69788e7c6c19b45a89d3701fc084bd0f61f59e583",
    "vsa.intoto.json":
        "b9865d5560d113227f85628a9a212cd6d156d19e263bcc00c36efb5b32ced3a9",
    "verify_vsa_offline.py":
        "aaa8ee347717def035d7c7fc4248fc09e0be1db8c5f627b8e7bd8e0a5795ecba",
    "expected_stdout.txt":
        "f88ed3122d5ba66d34984b2f5ce9b7e5ec5cb48549e8340b27917781940eaf9f",
    "expected_exit.txt":
        "9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa",
}

_BUNDLE_FOR_VERIFY = (
    "manifest.json", "trace.json", "conformance.json",
    "coverage.farkas.json", "cost.farkas.json", "vsa.intoto.json",
    "verify_vsa_offline.py",
)


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _run_verifier(tmp_path) -> subprocess.CompletedProcess:
    for name in _BUNDLE_FOR_VERIFY:
        (tmp_path / name).write_bytes((_VEC / name).read_bytes())
    return subprocess.run(
        [sys.executable, str(tmp_path / "verify_vsa_offline.py")],
        capture_output=True, text=True, cwd=str(tmp_path),
    )


def test_bundle_files_present_and_pinned() -> None:
    for name, want in _EXPECTED.items():
        p = _VEC / name
        assert p.is_file(), "missing served vector file: " + name
        assert _sha256(p.read_bytes()) == want, "digest drift: " + name


def test_verifier_passes_offline(tmp_path) -> None:
    r = _run_verifier(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "VERDICT: PASS" in r.stdout


def test_verifier_stdout_matches_frozen(tmp_path) -> None:
    r = _run_verifier(tmp_path)
    want = (_VEC / "expected_stdout.txt").read_text(encoding="utf-8")
    assert r.stdout == want


def test_both_farkas_legs_proven_offline(tmp_path) -> None:
    r = _run_verifier(tmp_path)
    assert "cost-cap Farkas certificate PROVEN offline by rational" in r.stdout
    assert "coverage Farkas certificate PROVEN offline by rational" in r.stdout


def test_expected_exit_is_zero() -> None:
    assert (_VEC / "expected_exit.txt").read_text(
        encoding="utf-8"
    ).strip() == "0"


def test_index_lists_artifacts_with_matching_sha() -> None:
    index = json.loads((_VEC / "index.json").read_text(encoding="utf-8"))
    assert index["schema"] == "nous.vsa.vectors.index.v1"
    by_name = {a["name"]: a["sha256"] for a in index["artifacts"]}
    for name, want in _EXPECTED.items():
        assert by_name.get(name) == want, "index sha mismatch: " + name


def test_sha256_sidecars_match() -> None:
    for name in _EXPECTED:
        side = _VEC / (name + ".sha256")
        assert side.is_file(), "missing sidecar: " + name + ".sha256"
        recorded = side.read_text(encoding="utf-8").split()[0]
        assert recorded == _sha256((_VEC / name).read_bytes())
