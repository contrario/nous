"""AN-GATE-1 K-JS.7 for release_index.py (S502, build note B502-4): its two
strict sites refuse each planted mutation as an INDEX FAIL, and the tags
they name are recorded for tests/test_an_js_zz_sites.py, which runs after
this file (its name sorts last among the an_js files).

[js:rix.1] index.json, planted in a copy of the served 11.0.0 directory and
read by build-attest-verify. [js:rix.2] the Rekor bundle's
canonicalized_body: ROOT 2 has verified those bytes under the pinned log
key before the leg parses them, and no test holds that key, so the planted
body is handed to release_index.check_index directly.

# __an_js_strict_rix_v1__
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

import cli_verify_release as CVR
import release_index as RI
import test_an_js_strict as A
import test_an_js_strict_b as B

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "website" / ".well-known" / "nous" / "release-vsa" / "11.0.0"
PINS = REPO / "tests" / "fixtures" / "rekor_v2"


def _named(detail: str, label: str, mutation: str, key) -> None:
    assert label in detail, (A.RAN, label, mutation, detail)
    if mutation.startswith("dup_"):
        assert "refused: duplicate key " + repr(key) in detail, (A.RAN, mutation, detail)
    else:
        assert A.TOKENS[mutation] in detail, (A.RAN, mutation, detail)
        assert A.NONFINITE_PHRASE in detail, (A.RAN, mutation, detail)
    A.HITS.update(A.TAG.findall(detail))


def _copy(tmp_path: Path) -> Path:
    d = tmp_path / "11.0.0"
    shutil.copytree(SRC, d)
    return d


def test_rix_baseline_passes(tmp_path):
    r = CVR.verify_convergence(_copy(tmp_path), PINS)
    assert r["index_closure"]["status"] == "PASS", r["index_closure"]


@pytest.mark.parametrize("mutation", A.MUTATIONS)
def test_rix1_index_json(tmp_path, mutation):
    d = _copy(tmp_path)
    key = B._plant_path(d / "index.json", mutation)
    r = CVR.verify_convergence(d, PINS)
    ix = r["index_closure"]
    assert ix["status"] == "FAIL" and r["convergence"] == "FAIL", (A.RAN, ix)
    _named(ix["detail"], "index.json [js:rix.1]", mutation, key)


@pytest.mark.parametrize("mutation", A.MUTATIONS)
def test_rix2_canonicalized_body(tmp_path, mutation):
    vsa = (SRC / "build-vsa.intoto.json").read_bytes()
    payload = base64.b64decode(json.loads(vsa)["payload"])
    bb = (SRC / "nous_lang-11.0.0.rekor-v2-bundle.json").read_bytes()
    bundle = copy.deepcopy(json.loads(bb))
    tle = bundle["transparency_log_entry"]
    body, key = B._plant_bytes(base64.b64decode(tle["canonicalized_body"]), mutation)
    tle["canonicalized_body"] = base64.b64encode(body).decode("ascii")
    r = CVR.verify_convergence(SRC, PINS)
    ix = RI.check_index(
        SRC, version="11.0.0", statement=json.loads(payload), bundle=bundle,
        vsa_bytes=vsa, bundle_bytes=bb, pin_b64=CVR.NOUS_RELEASE_PINNED_PUBKEY_B64,
        vsa_payload_sha256_hex=hashlib.sha256(payload).hexdigest(),
        rfc3161_gen_time=r["evidence"]["rfc3161_gen_time"])
    assert ix["status"] == "FAIL", (A.RAN, ix)
    _named(ix["detail"], "canonicalized_body [js:rix.2]", mutation, key)
