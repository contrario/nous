"""S502: a release-VSA directory's index.json, checked by nous
build-attest-verify as the image of the inputs it has verified.

Design docs/RELEASE_INDEX_CLOSURE_DESIGN.md: decisions D502-1 to D502-9,
test plan section 14, build notes B502-1 to B502-6. The served directories
are read, never written; a test that changes a file works on a copy under
tmp_path.

# __s502_release_index_closure_tests_v1__
"""
from __future__ import annotations

import ast
import base64
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

import build_vsa
import cli_verify_release as CVR
import mint_release_vsa as M
import release_index as RI

REPO = Path(__file__).resolve().parent.parent
RELVSA = REPO / "website" / ".well-known" / "nous" / "release-vsa"
PINS = REPO / "tests" / "fixtures" / "rekor_v2"
DIRS = sorted((p for p in RELVSA.iterdir() if p.is_dir()),
              key=lambda p: RI.version_tuple(p.name))
VERSIONS = [p.name for p in DIRS]
V = "11.0.0"
PIN = CVR.NOUS_RELEASE_PINNED_PUBKEY_B64
REKOR = "rekor_v2_transparency_log"


def _copy(tmp_path: Path, v: str = V) -> Path:
    d = tmp_path / v
    shutil.copytree(RELVSA / v, d)
    return d


def _idx(d: Path) -> dict:
    return json.loads((d / "index.json").read_bytes())


def _put(d: Path, obj: dict) -> None:
    (d / "index.json").write_bytes(RI.index_bytes(obj))


def _art(o: dict, kind: str) -> dict:
    return [a for a in o["artifacts"] if a["kind"] == kind][0]


def _ix(d: Path, **kw) -> tuple[dict, dict]:
    r = CVR.verify_convergence(d, PINS, **kw)
    return r, r["index_closure"]


def _cli(d: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "cli", "build-attest-verify", "--bundle-dir", str(d),
         "--pins-dir", str(PINS), *extra],
        cwd=str(REPO), capture_output=True, text=True)


def _inputs(d: Path) -> dict:
    vsa = (d / "build-vsa.intoto.json").read_bytes()
    env = json.loads(vsa)
    payload = base64.b64decode(env["payload"])
    bn = "nous_lang-" + d.name + ".rekor-v2-bundle.json"
    bb = (d / bn).read_bytes()
    r = CVR.verify_convergence(d, PINS)
    return {"version": d.name, "statement": json.loads(payload), "bundle": json.loads(bb),
            "vsa_bytes": vsa, "bundle_bytes": bb,
            "verifier_bytes": (d / RI.VERIFIER_FILENAME).read_bytes(),
            "key_bytes": (d / RI.VERIFIER_KEY_FILENAME).read_bytes(),
            "pin_b64": PIN, "vsa_payload_sha256_hex": hashlib.sha256(payload).hexdigest(),
            "rfc3161_gen_time": r["evidence"]["rfc3161_gen_time"],
            "emitted_at": _idx(d)["emittedAt"]}


def _mint(d: Path, i: dict) -> bytes:
    v = i["version"]
    return RI.index_bytes(M.build_release_index(
        v, d, statement=i["statement"], bundle=i["bundle"],
        bundle_filename="nous_lang-" + v + ".rekor-v2-bundle.json",
        vsa_filename="nous_lang-" + v + ".build-vsa.intoto.json",
        verifier_filename=RI.VERIFIER_FILENAME, verifier_key_filename=RI.VERIFIER_KEY_FILENAME,
        operator_pin_b64=i["pin_b64"], vsa_payload_sha256_hex=i["vsa_payload_sha256_hex"],
        rfc3161_gen_time=i["rfc3161_gen_time"], emitted_at=i["emitted_at"]))


# ------------------------------------------------------- the served indexes


def test_t00_forty_one_served_directories():
    assert len(DIRS) == 41 and VERSIONS[0] == "5.60.1" and VERSIONS[-1] == V


@pytest.mark.parametrize("v", VERSIONS)
def test_t01_every_served_index_closes(v):
    r, ix = _ix(RELVSA / v)
    assert ix["status"] == "PASS", ix
    assert r["legs"]["index_closure"] is ix
    assert r["convergence"] == "PASS"
    assert "is not evidenced" in ix["detail"] and ix["boundary"] == RI.BOUNDARY


@pytest.mark.parametrize("v", VERSIONS)
def test_t02_the_derivation_equals_the_mint_and_the_served_bytes(v, monkeypatch):
    # the mint writes today's Rekor boundary; for a release before 5.79.0 it
    # is given that release's text (design M1b), nothing else changed
    monkeypatch.setattr(M, "REKOR_LEG_BOUNDARY", RI.rekor_boundary(v))
    d = RELVSA / v
    i = _inputs(d)
    mine = RI.index_bytes(RI.derive_index(**i))
    assert mine == _mint(d, i) == (d / "index.json").read_bytes()


def _syn(kind: str, i: dict) -> dict:
    i = copy.deepcopy(i)
    st = i["statement"]
    ext = st["predicate"][RI.EXT_KEY]
    if kind == "backfill":
        ext["backfill"] = {"note": "synthetic", "n": 3}
    elif kind == "two_wheels":
        st["subject"].insert(0, {"name": "nous_lang-0.0.1-py3-none-any.whl",
                                 "digest": {"sha256": "a" * 64}})
    elif kind == "three_publish_legs":
        e = copy.deepcopy(ext["subjectFederation"][-1])
        e["name"] = "nous_lang-" + i["version"] + ".zip"
        e["publishLeg"]["payloadSha256"] = "b" * 64
        ext["subjectFederation"].append(e)
    elif kind == "no_sdist":
        st["subject"] = [s for s in st["subject"] if not s["name"].endswith(".tar.gz")]
    elif kind == "build_legs_differ":
        ext["subjectFederation"][0]["buildLeg"]["payloadSha256"] = "c" * 64
    elif kind == "anchor_mismatch":
        i["vsa_payload_sha256_hex"] = "d" * 64
    return i


@pytest.mark.parametrize("kind", ["as_served", "backfill", "two_wheels", "three_publish_legs"])
def test_t03_synthetic_statements_derive_as_the_mint(kind):
    d = RELVSA / V
    i = _syn(kind, _inputs(d))
    assert RI.index_bytes(RI.derive_index(**i)) == _mint(d, i)


@pytest.mark.parametrize("kind,why", [
    ("no_sdist", "missing wheel or sdist"),
    ("build_legs_differ", "do not share one provenance payloadSha256"),
    ("anchor_mismatch", "anchored digest is not the VSA payload digest")])
def test_t03b_synthetic_refusals_match_the_mint(kind, why):
    d = RELVSA / V
    i = _syn(kind, _inputs(d))
    with pytest.raises(M.MintError):
        _mint(d, i)
    with pytest.raises(RI.IndexClosureError, match=why):
        RI.derive_index(**i)


# ------------------------------------------------- M2's tampering, now FAIL


def _t(name: str, d: Path) -> bytes:
    raw = (d / "index.json").read_bytes()
    o = json.loads(raw)
    if name == "T1":
        o["vsaPayloadSha256"] = "0" * 64
    elif name == "T2":
        _art(o, "wheel")["sha256"] = "1" * 64
    elif name == "T3":
        _art(o, "offline_verifier")["sha256"] = "2" * 64
    elif name == "T4":
        _art(o, REKOR)["logIndex"] += 1
    elif name == "T5":
        o["buildIdentity"]["sourceCommit"] = "3" * 40
    elif name == "T6":
        anchor = b'  "artifacts": ['
        assert raw.count(anchor) == 1
        return raw.replace(anchor, b'  "vsaPayloadSha256": "' + b"0" * 64 + b'",\n' + anchor, 1)
    elif name == "T7":
        return (RELVSA / "10.0.0" / "index.json").read_bytes()
    return RI.index_bytes(o)


@pytest.mark.parametrize("name", ["T1", "T2", "T3", "T4", "T5", "T6", "T7"])
def test_t04_m2_tampering_fails(tmp_path, name):
    d = _copy(tmp_path)
    (d / "index.json").write_bytes(_t(name, d))
    r, ix = _ix(d)
    assert ix["status"] == "FAIL" and r["convergence"] == "FAIL", ix
    if name == "T6":
        assert "index.json [js:rix.1] refused: duplicate key 'vsaPayloadSha256'" in ix["detail"]
    else:
        assert "is not the image of the verified inputs" in ix["detail"], ix


def test_t04b_the_cli_exits_1_on_a_tampered_index(tmp_path):
    d = _copy(tmp_path)
    (d / "index.json").write_bytes(_t("T2", d))
    p = _cli(d)
    assert p.returncode == 1, p.stdout + p.stderr
    assert "[FAIL]  INDEX" in p.stdout and "CONVERGENCE: FAIL" in p.stdout


# ------------------------------------------------------------- emittedAt


def test_t05_emitted_at_is_unbound(tmp_path):
    d = _copy(tmp_path)
    o = _idx(d)
    o["emittedAt"] = "1999-01-02T03:04:05Z"
    _put(d, o)
    r, ix = _ix(d)
    assert ix["status"] == "PASS" and r["convergence"] == "PASS", ix
    assert "emittedAt 1999-01-02T03:04:05Z is not evidenced" in ix["detail"]


@pytest.mark.parametrize("bad", ["2026-11-26 12:00:00Z", "2026-11-26T12:00:00+00:00",
                                 "2026-11-26T12:00:00.5Z", "x2026-11-26T12:00:00Z",
                                 "\uff12\uff10\uff12\uff16-11-26T12:00:00Z", 20261126, None])
def test_t05b_a_malformed_emitted_at_fails(tmp_path, bad):
    d = _copy(tmp_path)
    o = _idx(d)
    o["emittedAt"] = bad
    _put(d, o)
    r, ix = _ix(d)
    assert ix["status"] == "FAIL" and "emittedAt" in ix["detail"], ix


# ------------------------------------------------------- co-served files


def test_t06_the_verifier_missing_fails(tmp_path):
    d = _copy(tmp_path)
    (d / RI.VERIFIER_FILENAME).unlink()
    r, ix = _ix(d)
    assert ix["status"] == "FAIL" and RI.VERIFIER_FILENAME in ix["detail"], ix


def test_t06b_the_key_record_missing_fails(tmp_path):
    d = _copy(tmp_path)
    (d / RI.VERIFIER_KEY_FILENAME).unlink()
    r, ix = _ix(d)
    assert ix["status"] == "FAIL" and RI.VERIFIER_KEY_FILENAME in ix["detail"], ix


def test_t06c_a_changed_key_record_fails_even_with_the_index_matching(tmp_path):
    d = _copy(tmp_path)
    kp = d / RI.VERIFIER_KEY_FILENAME
    kp.write_bytes(kp.read_bytes() + b"\n")
    o = _idx(d)
    _art(o, "release_verifier_key")["sha256"] = hashlib.sha256(kp.read_bytes()).hexdigest()
    _put(d, o)
    r, ix = _ix(d)
    assert ix["status"] == "FAIL", ix
    assert "not the canonical record of the pinned key" in ix["detail"]


@pytest.mark.parametrize("src", ["5.60.1", "8.0.0", "synthetic"])
def test_t06d_a_coherent_verifier_swap_fails(tmp_path, src):
    d = _copy(tmp_path)
    vp = d / RI.VERIFIER_FILENAME
    if src == "synthetic":
        vp.write_bytes(vp.read_bytes() + b"# appended\n")
    else:
        shutil.copy(RELVSA / src / RI.VERIFIER_FILENAME, vp)
    o = _idx(d)
    _art(o, "offline_verifier")["sha256"] = hashlib.sha256(vp.read_bytes()).hexdigest()
    _put(d, o)
    r, ix = _ix(d)
    assert ix["status"] == "FAIL", ix
    assert "is not the verifier committed for " + V in ix["detail"]


# ------------------------------------------------------ boundary by version


@pytest.mark.parametrize("v,text", [("11.0.0", "old"), ("5.78.0", "new")])
def test_t07_the_other_era_boundary_fails(tmp_path, v, text):
    d = _copy(tmp_path, v)
    o = _idx(d)
    _art(o, REKOR)["boundary"] = (RI.REKOR_BOUNDARY_BEFORE_5_79_0 if text == "old"
                                  else RI.REKOR_BOUNDARY_FROM_5_79_0)
    _put(d, o)
    r, ix = _ix(d)
    assert ix["status"] == "FAIL" and "is not the image" in ix["detail"], ix


def test_t07b_eras_start_at_the_first_release_vsa():
    assert RI.rekor_boundary("5.79.0") == M.REKOR_LEG_BOUNDARY
    assert RI.verifier_sha256("12.3.4") == RI.VERIFIER_SHA256_ERAS[-1][1]
    for bad in ("5.60.0", "1.0.0", "5.60", "v5.60.1", ""):
        with pytest.raises(RI.IndexClosureError):
            RI.verifier_sha256(bad)


# ---------------------------------------------------------- size and kind


def test_t08_an_index_over_1_mib_fails_before_parsing(tmp_path):
    d = _copy(tmp_path)
    raw = _t("T6", d)
    (d / "index.json").write_bytes(raw + b" " * (RI.MAX_READ_BYTES + 1 - len(raw)))
    r, ix = _ix(d)
    assert ix["status"] == "FAIL", ix
    assert "larger than 1048576 bytes; not parsed" in ix["detail"]
    assert "duplicate" not in ix["detail"]


def test_t08b_an_index_at_exactly_1_mib_is_read(tmp_path):
    d = _copy(tmp_path)
    raw = (d / "index.json").read_bytes()
    (d / "index.json").write_bytes(raw + b" " * (RI.MAX_READ_BYTES - len(raw)))
    r, ix = _ix(d)
    assert ix["status"] == "FAIL" and "is not the image" in ix["detail"], ix


@pytest.mark.parametrize("kind", ["directory", "fifo"])
def test_t09_index_json_not_a_regular_file_fails_at_once(tmp_path, kind):
    d = _copy(tmp_path)
    (d / "index.json").unlink()
    if kind == "directory":
        (d / "index.json").mkdir()
    else:
        os.mkfifo(d / "index.json")
    r, ix = _ix(d)
    assert ix["status"] == "FAIL" and "not a regular file" in ix["detail"], ix


# ----------------------------------------------- absent, and inputs failing


def _assembled(tmp_path: Path) -> Path:
    d = tmp_path / "asm"
    d.mkdir()
    src = RELVSA / "5.60.1"
    shutil.copy(src / "nous_lang-5.60.1.build-vsa.intoto.json", d / "build-vsa.intoto.json")
    shutil.copy(src / "nous_lang-5.60.1.rekor-v2-bundle.json", d / "rekor-v2-bundle.json")
    return d


def test_t10_no_index_is_absent_and_the_convergence_unchanged(tmp_path):
    d = _assembled(tmp_path)
    r, ix = _ix(d)
    assert ix["status"] == "ABSENT" and r["convergence"] == "PASS", ix
    assert "index_closure" not in r["legs"]
    assert sorted(r["legs"]) == ["binding_log_to_vsa", "root1_operator_ed25519",
                                 "root2_checkpoint_signature", "root2_rekor_inclusion",
                                 "root2_rfc3161_timestamp"]
    p = _cli(d)
    assert p.returncode == 0 and "[ABSENT]  INDEX" in p.stdout, p.stdout + p.stderr


def test_t10b_an_index_with_unverified_inputs_fails_without_derivation(tmp_path):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    other = base64.b64encode(Ed25519PrivateKey.generate().public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw)).decode()
    r, ix = _ix(RELVSA / V, pinned_pubkey_b64=other)
    assert r["legs"]["root1_operator_ed25519"]["status"] == "FAIL"
    assert ix["status"] == "FAIL" and "not derived" in ix["detail"], ix


def test_t10c_a_binding_failure_fails_without_derivation(tmp_path):
    d = _copy(tmp_path)
    shutil.copy(RELVSA / "10.0.0" / "nous_lang-10.0.0.rekor-v2-bundle.json",
                d / ("nous_lang-" + V + ".rekor-v2-bundle.json"))
    r, ix = _ix(d)
    assert r["legs"]["root2_rekor_inclusion"]["status"] == "PASS"
    assert r["legs"]["binding_log_to_vsa"]["status"] == "FAIL"
    assert ix["status"] == "FAIL" and "not derived" in ix["detail"], ix


# --------------------------------------------- the matrix, the JSON, the CLI


def test_t11_the_cli_matrix_and_json_on_a_served_directory():
    p = _cli(RELVSA / V)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "[PASS]  INDEX   index.json == image of the verified inputs" in p.stdout
    assert RI.BOUNDARY in p.stdout and "CONVERGENCE: PASS" in p.stdout
    j = _cli(RELVSA / V, "--json")
    assert j.returncode == 0
    obj = json.loads(j.stdout)
    assert obj["index_closure"]["status"] == "PASS"
    assert obj["legs"]["index_closure"]["status"] == "PASS"


# ------------------------------------------------ constants and placement


def test_t12_constants_equal_the_mint_and_build_vsa():
    assert RI.EXT_KEY == M.NOUS_BUILD_VSA_EXT_KEY == build_vsa.NOUS_BUILD_VSA_EXT_KEY
    assert RI.INDEX_SCHEMA == M.RELEASE_VSA_INDEX_SCHEMA
    assert RI.BASE_URL == M.RELEASE_VSA_BASE_URL
    assert RI.PYPI_PROJECT_URL == M.PYPI_PROJECT_URL
    assert RI.REKOR_BOUNDARY_FROM_5_79_0 == M.REKOR_LEG_BOUNDARY
    assert RI.KEY_RECORD_LEVELS == (M.SLSA_BUILD_LEVEL,)
    assert RI.RELEASE_VERIFIER_ID == build_vsa.NOUS_RELEASE_VERIFIER_ID
    assert PIN == M.COMMITTED_RELEASE_PIN_B64
    kb = RI.key_record_bytes(PIN)
    assert hashlib.sha256(kb).hexdigest() == (
        "e9cd1a34cc8c64329d99c96155b4b81afeca307c1dc024b84a078aa35b21a604")
    assert all((p / RI.VERIFIER_KEY_FILENAME).read_bytes() == kb for p in DIRS)


def test_t13_the_last_verifier_row_is_what_build_vsa_emits_today(tmp_path):
    out = build_vsa.emit_build_vsa_verifier(str(tmp_path), PIN)
    assert hashlib.sha256(Path(out).read_bytes()).hexdigest() == RI.VERIFIER_SHA256_ERAS[-1][1]


def test_t14_release_index_is_pure():
    tree = ast.parse((REPO / "release_index.py").read_text(encoding="utf-8"))
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods.add((n.module or "").split(".")[0])
    assert mods == {"__future__", "base64", "hashlib", "json", "os", "re", "stat",
                    "pathlib", "typing", "conformance_verifier"}, mods


def test_t15_rule_9_registration():
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert "release_index" in data["tool"]["setuptools"]["py-modules"]
    assert '"release_index.py",  # __s502_release_index_wheelgate_v1__' in (
        REPO / "scripts" / "release.py").read_text(encoding="utf-8")


def _cold_audit(monkeypatch):
    spec = importlib.util.spec_from_file_location("cold_audit_s502",
                                                  REPO / "scripts" / "cold_audit.py")
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "cold_audit_s502", mod)
    spec.loader.exec_module(mod)
    return mod


class _Stop(Exception):
    pass


def test_t16_the_cold_audit_fetches_the_leg_inputs(tmp_path, monkeypatch):
    mod = _cold_audit(monkeypatch)
    seen = []

    def fetch(base, names, into):
        seen.append(tuple(names))
        raise _Stop()
    monkeypatch.setattr(mod, "_fetch_all", fetch)
    with pytest.raises(_Stop):
        mod.audit_release_vsa_rekor(V, tmp_path)
    for name in ("index.json", "build-vsa.intoto.json", RI.VERIFIER_FILENAME,
                 RI.VERIFIER_KEY_FILENAME, "nous_lang-" + V + ".rekor-v2-bundle.json"):
        assert name in seen[0], (name, seen)


def test_t17_the_guide_takes_no_decision_from_index_json():
    doc = (REPO / "docs" / "VERIFYING_A_RELEASE.md").read_text(encoding="utf-8")
    s12 = doc[doc.index("### 1.2 "):doc.index("### 1.3 ")]
    assert "json.load(open('index.json'))" not in s12
    assert "INDEX leg" in s12 and "not signed" in s12
    s15 = doc[doc.index("### 1.5 "):doc.index("\n## ", doc.index("### 1.5 "))]
    assert 'curl -fsSLO "$B/release-verifier-key.json"' in s15
    assert "no\nverifier reads it" not in s15


def test_t18_the_an_js_scans_cover_release_index():
    import test_an_js_inventory as I
    assert "release_index.py" in I.SCOPE_P
