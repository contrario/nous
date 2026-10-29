"""NT-GATE-1 W: the wired VSA verifier, the harness pins and vector v2.

Ruling (a), 2026-10-27: V1 lands together with the VSA wiring and v2.
Red before any W code (W_PREDICTIONS.md, sha256 86224f3c...).

  W1  v2's index pins its bytes and states its reproduction terms.
  W2  v2's served verifier passes its own bundle, as recorded.
  W3  v2's certificate carries the spec canon its manifest signs.
  W4  a one-row cost certificate re-signed with the published vector
      seeds: v1's frozen verifier prints PROVEN offline; v2's verifier
      and the current template refuse it.
  W5  the v2 harness does not depend on the wall clock.
  W6  the v2 harness does not depend on a price layer.
  W7  the docs name v2 and say v1 is frozen.

# __nt_w_vsa_v2_tests_v1__
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

import vsa_verifier

REPO = Path(__file__).resolve().parent.parent
VEC = REPO / "website" / ".well-known" / "nous" / "vsa-vectors"
V1 = VEC / "v1"
V2 = VEC / "v2"
HARNESS_V2 = V2 / "mint_vsa_vector.py"
SOURCE_V2 = V2 / "vsa_conformance_vector_v2.nous"
SHIPPED_PRICES = REPO / "pricing" / "defaults.toml"
NAMES = (
    "manifest.json", "trace.json", "conformance.json",
    "coverage.farkas.json", "cost.farkas.json", "vsa.intoto.json",
    "verify_vsa_offline.py", "expected_stdout.txt", "expected_exit.txt",
)
BUNDLE = NAMES[:7]
SEED_MANIFEST = bytes(range(0, 32))
SEED_VSA = bytes(range(96, 128))
EXT = "https://nous-lang.org/vsa/ext/v1"
DSSE_TYPE = "application/vnd.in-toto+json"
REDERIVE_OK = "cost system re-derived from the certificate's obligations_canon"
TRIVIAL = {"constraints": [{"coeffs": {"": "1"}, "strict": False}],
           "multipliers": ["1"], "contradiction": "forged"}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def _index() -> dict:
    p = V2 / "index.json"
    assert p.is_file(), "v2 index.json absent"
    return json.loads(p.read_text(encoding="utf-8"))


def _run_verifier(d: Path, verifier: Path | None = None, args=()):
    if verifier is not None:
        shutil.copy2(verifier, d / "verify_vsa_offline.py")
    p = subprocess.run(
        [sys.executable, "-B", "verify_vsa_offline.py"] + list(args),
        capture_output=True, text=True, cwd=str(d),
    )
    return p.returncode, p.stdout, p.stderr


def _copy_bundle(dest: Path) -> Path:
    assert V2.is_dir(), "v2 absent"
    dest.mkdir(parents=True)
    for n in BUNDLE:
        shutil.copy2(V2 / n, dest / n)
    return dest


# ------------------------------------------------------------------ W1


def test_w1_v2_index_pins_its_bytes():
    idx = _index()
    assert idx["version"] == "v2"
    arts = idx["artifacts"]
    assert sorted(a["name"] for a in arts) == sorted(NAMES)
    for a in arts:
        got = _sha((V2 / a["name"]).read_bytes())
        assert a["sha256"] == got, a["name"]
        side = (V2 / (a["name"] + ".sha256")).read_text(encoding="utf-8")
        assert side.split() == [got, a["name"]], a["name"]
    side = (V2 / "index.json.sha256").read_text(encoding="utf-8")
    assert side.split() == [_sha((V2 / "index.json").read_bytes()),
                            "index.json"]
    rep = idx["reproduce"]
    for entry in (idx["vectorSource"], rep["harness"]):
        assert entry["sha256"] == _sha((V2 / entry["name"]).read_bytes())
        assert entry["name"] not in NAMES
    assert "The bundle is the nine artifacts" in rep["scope"]
    note = rep["remint"]
    for term in ("2026-10-27", "pricing/defaults.toml", "7.0.0",
                 "wall clock", "price layer", "NV"):
        assert term in note, term
    assert "pin_clock" not in note
    assert "under the declared per-call token/tick estimates" in \
        idx["boundary"]


# ------------------------------------------------------------------ W2


def test_w2_served_v2_verifier_passes_its_bundle(tmp_path):
    d = _copy_bundle(tmp_path / "b")
    rc, out, err = _run_verifier(d)
    want_rc = int((V2 / "expected_exit.txt").read_text().strip())
    assert rc == want_rc == 0, err
    assert out == (V2 / "expected_stdout.txt").read_text(encoding="utf-8")
    assert REDERIVE_OK in out
    assert "VERDICT: PASS" in out


# ------------------------------------------------------------------ W3


def test_w3_certificate_carries_the_signed_canon():
    assert V2.is_dir(), "v2 absent"
    cert = json.loads((V2 / "conformance.json").read_text(encoding="utf-8"))
    man = json.loads((V2 / "manifest.json").read_text(encoding="utf-8"))
    canon = cert.get("obligations_canon")
    assert isinstance(canon, str)
    assert _sha(canon.encode("utf-8")) == man["smt_spec_sha256"]
    assert man.get("cost_farkas_sha256")


# ------------------------------------------------------------------ W4


def _pae(payload: bytes) -> bytes:
    pt = DSSE_TYPE.encode()
    return (b"DSSEv1 " + str(len(pt)).encode() + b" " + pt + b" "
            + str(len(payload)).encode() + b" " + payload)


def _forge_one_row(d: Path) -> None:
    cost = json.dumps(TRIVIAL, sort_keys=True).encode()
    cost_sha = _sha(cost)
    (d / "cost.farkas.json").write_bytes(cost)
    man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    man["cost_farkas_sha256"] = cost_sha
    body = _canon({k: v for k, v in man.items()
                   if k not in ("signature", "transparency_log")})
    mkey = Ed25519PrivateKey.from_private_bytes(SEED_MANIFEST)
    man["signature"]["signature_b64"] = base64.b64encode(
        mkey.sign(body)).decode()
    (d / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    env = json.loads((d / "vsa.intoto.json").read_text(encoding="utf-8"))
    stmt = json.loads(base64.b64decode(env["payload"]))
    pred = stmt["predicate"]
    pred[EXT]["costProof"]["sha256"] = cost_sha
    for ia in pred["inputAttestations"]:
        if ia["uri"] == "manifest.json":
            ia["digest"]["sha256"] = _sha(body)
        if ia["uri"] == "cost.farkas.json":
            ia["digest"]["sha256"] = cost_sha
    payload = _canon(stmt)
    vkey = Ed25519PrivateKey.from_private_bytes(SEED_VSA)
    env["payload"] = base64.b64encode(payload).decode()
    env["signatures"] = [{
        "keyid": env["signatures"][0].get("keyid", ""),
        "sig": base64.b64encode(vkey.sign(_pae(payload))).decode(),
    }]
    (d / "vsa.intoto.json").write_text(json.dumps(env), encoding="utf-8")


def test_w4_one_row_forgery_v1_proves_v2_and_template_refuse(tmp_path):
    runs = {}
    for label in ("v1", "v2", "template"):
        d = _copy_bundle(tmp_path / label)
        _forge_one_row(d)
        if label == "v1":
            runs[label] = _run_verifier(d, V1 / "verify_vsa_offline.py")
        elif label == "v2":
            runs[label] = _run_verifier(d)
        else:
            pub = base64.b64encode(
                Ed25519PrivateKey.from_private_bytes(SEED_VSA)
                .public_key().public_bytes_raw()).decode()
            vsa_verifier.emit_vsa_verifier(str(d), pub)
            runs[label] = _run_verifier(
                d, args=["--expect-signer", pub])  # __nt_v3_classes_tests_v1__
    rc, out, err = runs["v1"]
    assert rc == 0, err
    assert "PROVEN offline" in out and "VERDICT: PASS" in out
    for label in ("v2", "template"):
        rc, out, err = runs[label]
        assert rc == 1, (label, out, err)
        assert "re-derived from the spec canon" in err, (label, err)
        assert "PROVES-cost (rational" not in out, label


# ------------------------------------------------------------- W5, W6

WRAP = '''import datetime as _dt
import runpy
import sys
_DAY = _dt.date.fromisoformat(sys.argv[1])


class _Wall(_dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(_DAY.year, _DAY.month, _DAY.day, 12, 0, 0, tzinfo=tz)


import pricing  # noqa: E402
import smt_emit  # noqa: E402
pricing.datetime = _Wall
smt_emit.datetime = _Wall
sys.argv = sys.argv[2:]
runpy.run_path(sys.argv[0], run_name="__main__")
'''


def _layered_prices(text: str) -> str:
    head = '[models."claude-sonnet-4-6"]'
    i = text.index(head)
    j = text.index("\ninput_per_1m", i) + 1
    k = text.index("\n", j)
    assert text[j:k].replace(" ", "") == 'input_per_1m="3.00"'
    return text[:j] + 'input_per_1m  = "9.00"' + text[k:]


def mint(harness: Path, source: Path, wall_day: str, tmp: Path,
         layers: bool = False):
    """Run a harness as a user would, the wall clock set to wall_day;
    with layers, a user and a project price layer that change the
    vector model's input rate. Returns (rc, stderr, {name: sha256})."""
    tmp.mkdir(parents=True)
    home = tmp / "home"
    cwd = tmp / "cwd"
    home.mkdir()
    cwd.mkdir()
    if layers:
        changed = _layered_prices(
            SHIPPED_PRICES.read_text(encoding="utf-8"))
        (home / ".config" / "nous").mkdir(parents=True)
        (home / ".config" / "nous" / "prices.toml").write_text(
            changed, encoding="utf-8")
        (cwd / "nous_prices.toml").write_text(changed, encoding="utf-8")
    wrap = tmp / "wall.py"
    wrap.write_text(WRAP, encoding="utf-8")
    out = tmp / "out"
    env = dict(os.environ, HOME=str(home), PYTHONPATH=str(REPO))
    p = subprocess.run(
        [sys.executable, "-B", str(wrap), wall_day, str(harness),
         str(source), str(out)],
        capture_output=True, text=True, cwd=str(cwd), env=env,
    )
    digests = {}
    if out.is_dir():
        digests = {q.name: _sha(q.read_bytes())
                   for q in sorted(out.iterdir()) if q.is_file()}
    return p.returncode, p.stderr, digests


@pytest.fixture(scope="module")
def early(tmp_path_factory):
    if not HARNESS_V2.is_file():
        return None
    return mint(HARNESS_V2, SOURCE_V2, "2026-01-01",
                tmp_path_factory.mktemp("w5") / "early")


def test_w5_v2_harness_stops_on_the_current_tree(early, tmp_path):
    # NT-GATE-1 V3: the template v2's harness emits now needs
    # --expect-signer, which that harness does not pass, so its PASS
    # gate stops the mint on this tree. v2 reproduces from the tree it
    # was committed from, as its index says. Clock and price-layer
    # independence is checked on v3's harness (test_nt_v3_vector.py).
    assert early is not None, "v2 harness absent"  # __nt_v3_classes_tests_v1__
    rc1, err1, _d1 = early
    assert rc1 == 1, err1
    assert "PASS GATE FAILED" in err1, err1
    assert "the tree it was committed from" in _index()["reproduce"]["remint"]


def test_w6_v2_index_pins_the_harness_it_was_measured_with():
    # NT-GATE-1 V3: see W5. The record of v2's reproduction stays its
    # index: the harness bytes it was measured with, pinned by sha256.  # __nt_v3_classes_tests_v1__
    h = _index()["reproduce"]["harness"]
    assert h["name"] == HARNESS_V2.name
    assert h["sha256"] == _sha(HARNESS_V2.read_bytes())


# ------------------------------------------------------------------ W7


def test_w7_docs_name_v2_and_v1_frozen():
    text = (REPO / "docs" / "VSA_CONFORMANCE_VECTORS.md").read_text(
        encoding="utf-8")
    assert "vsa-vectors/v2/" in text
    assert "v1 is frozen" in text
