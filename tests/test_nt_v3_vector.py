"""NT-GATE-1 V3: vector v3, minted with the V3 VSA template.

  X1  v3's index pins its bytes, the harness, the source and the VSA key.
  X2  v3's served verifier passes its bundle with the command its index
      states: exit 0, stdout equal to expected_stdout.txt, CLASS: PASS.
  X3  without --expect-signer it gives no PASS: exit 2, ENVIRONMENT.
  X4  the served verifier is the current template emitted with the
      vector's VSA key, byte for byte.
  X5  the expensive forgery re-signed with the published seeds is refused
      by the served verifier: exit 1, INTEGRITY, by recomputation.
  X6  the v3 harness does not depend on the wall clock (mints compared to
      each other, not to the published digests, which hold the minting
      version's NV).
  X7  the v3 harness does not depend on a price layer.
  X8  the docs name v3 and its pinned command.

# __nt_v3_classes_tests_v1__
"""
from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

import test_nt_v2_recompute as v2t
import test_nt_w_vsa_vector_v2 as w
import vsa_verifier

REPO = Path(__file__).resolve().parent.parent
V3 = REPO / "website" / ".well-known" / "nous" / "vsa-vectors" / "v3"
HARNESS = V3 / "mint_vsa_vector.py"
SOURCE = V3 / "vsa_conformance_vector_v3.nous"
SEED_VSA = bytes(range(96, 128))


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _index() -> dict:
    return json.loads((V3 / "index.json").read_text(encoding="utf-8"))


def _vsa_pub() -> str:
    return base64.b64encode(
        Ed25519PrivateKey.from_private_bytes(SEED_VSA).public_key()
        .public_bytes_raw()).decode("ascii")


def _bundle(tmp: Path) -> Path:
    d = tmp / "b"
    d.mkdir()
    for n in w.BUNDLE:
        shutil.copy2(V3 / n, d / n)
    return d


def _run(d: Path, args=()):
    p = subprocess.run([sys.executable, "-B", "verify_vsa_offline.py"]
                       + list(args), capture_output=True, text=True,
                       cwd=str(d))
    return p.returncode, p.stdout, p.stderr


def test_x1_index_pins_its_bytes():
    idx = _index()
    assert idx["version"] == "v3"
    assert sorted(a["name"] for a in idx["artifacts"]) == sorted(w.NAMES)
    for a in idx["artifacts"]:
        assert a["sha256"] == _sha((V3 / a["name"]).read_bytes()), a["name"]
        side = (V3 / (a["name"] + ".sha256")).read_text(encoding="utf-8")
        assert side.split() == [a["sha256"], a["name"]]
    raw = (V3 / "index.json").read_bytes()
    assert (V3 / "index.json.sha256").read_text(encoding="utf-8").split() \
        == [_sha(raw), "index.json"]
    assert idx["reproduce"]["harness"]["sha256"] == _sha(
        HARNESS.read_bytes())
    assert idx["vectorSource"]["sha256"] == _sha(SOURCE.read_bytes())
    assert idx["vectorKeys"]["vsaPubkeyB64"] == _vsa_pub()
    assert "--expect-signer <vectorKeys.vsaPubkeyB64>" in \
        idx["reproduce"]["verify"]


def test_x2_served_verifier_passes_its_bundle(tmp_path):
    d = _bundle(tmp_path)
    rc, out, err = _run(d, ["--expect-signer", _vsa_pub()])
    assert rc == int((V3 / "expected_exit.txt").read_text().strip()) == 0
    assert out == (V3 / "expected_stdout.txt").read_text(encoding="utf-8")
    assert out.splitlines()[-1] == "CLASS: PASS"
    assert "RECOMPUTED (" in out


def test_x3_no_pin_is_environment(tmp_path):
    d = _bundle(tmp_path)
    rc, out, err = _run(d)
    assert rc == 2, (rc, out, err)
    assert out.splitlines()[-1] == "CLASS: ENVIRONMENT"


def test_x4_served_verifier_is_the_current_template(tmp_path):
    vsa_verifier.emit_vsa_verifier(str(tmp_path), _vsa_pub())
    assert (tmp_path / "verify_vsa_offline.py").read_bytes() == \
        (V3 / "verify_vsa_offline.py").read_bytes()


def test_x5_expensive_forgery_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(v2t, "V2DIR", V3)
    d = tmp_path / "forged"
    v2t._forge_v2_expensive(d)
    rc, out, err = _run(d, ["--expect-signer", _vsa_pub()])
    assert rc == 1, (rc, out, err)
    assert out.splitlines()[-1] == "CLASS: INTEGRITY"
    assert "recomputed" in err, err


@pytest.fixture(scope="module")
def early(tmp_path_factory):
    return w.mint(HARNESS, SOURCE, "2026-01-01",
                  tmp_path_factory.mktemp("x6") / "early")


def test_x6_harness_does_not_depend_on_the_wall_clock(early, tmp_path):
    rc1, err1, d1 = early
    rc2, err2, d2 = w.mint(HARNESS, SOURCE, "2031-01-01", tmp_path / "late")
    assert rc1 == 0, err1
    assert rc2 == 0, err2
    assert sorted(d1) == sorted(w.NAMES)
    assert d1 == d2


def test_x7_harness_does_not_depend_on_a_price_layer(early, tmp_path):
    rc1, err1, d1 = early
    rc2, err2, d2 = w.mint(HARNESS, SOURCE, "2026-01-01",
                           tmp_path / "layers", layers=True)
    assert rc1 == 0, err1
    assert rc2 == 0, err2
    assert d1 == d2


def test_x8_docs_name_v3():
    text = (REPO / "docs" / "VSA_CONFORMANCE_VECTORS.md").read_text(
        encoding="utf-8")
    assert "vsa-vectors/v3" in text
    assert "--expect-signer" in text
