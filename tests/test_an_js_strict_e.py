"""AN-GATE-1 D4, round 3 (RULING 11:58Z; R3_PREDICTIONS 85e228d3).

Cases for the second review's holes: the conformance texts' trace.json
when the certificate carries no obligations_canon; nous ndec verify
--registry with the registry's Rekor leaf planted; attest_apr's vendor
body, strict everywhere with the vendor phrase; nous verify X.ndec;
the NOUS-TRACE reference verifier; nous continuity verify --json. Every
key is made under tmp_path.

# __an_js_strict_e_tests_v1__
"""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import manifest as mf
import test_an_js_strict as A
import test_an_js_strict_b as B
import test_an_js_strict_c as C
import test_nt_v3_classes as v3c

REPO = Path(__file__).resolve().parent.parent
MUTATIONS = A.MUTATIONS
VENDOR_PHRASE = ("the vendor signed these bytes and they have two readings; "
                 "not by itself evidence of tampering")


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    import dated_prices
    root = tmp_path_factory.mktemp("an_js_e")
    mp = pytest.MonkeyPatch()
    mp.delenv("XDG_DATA_HOME", raising=False)  # __an_js_tmp_keys_v1__
    dated_prices.use_dated_shipped_prices(root / "prices", mp)
    default_key = mf.default_key_path()
    yield root
    made = default_key.exists()
    mp.undo()
    assert not made, "a test created the default key " + str(default_key)


# ------------------------------------------------- conformance, no canon


def _nocanon_bundle(root: Path) -> tuple:
    b, pin = v3c._conf_bundle(A._pricing_table(), root, v3c.GENUINE(),
                              name="nc")
    work = root / "nc_mat"
    key = work / "op.key"
    priv = mf.load_or_create_keypair(key)[0]
    B._resign(work / "manifest.json", priv,
              lambda doc: doc.pop("cost_farkas_sha256", None))
    v3c._certify(work, key)
    cert = json.loads((work / "conformance.json").read_text(
        encoding="utf-8"))
    assert "obligations_canon" not in cert, "the certificate carries a canon"
    for n in ("conformance.json", "trace.json", "manifest.json"):
        (b / n).write_bytes((work / n).read_bytes())
    return b, pin


@pytest.fixture(scope="module")
def nocanon(env):
    r = env / "nocanon"
    r.mkdir()
    return _nocanon_bundle(r)


@pytest.mark.parametrize("name", v3c.CONF_TEXTS)
def test_e_nocanon_baseline(nocanon, tmp_path, name):
    b, pin = nocanon
    d = tmp_path / "c"
    shutil.copytree(b, d)
    rc, so, se = v3c._run_conf(d, name, pin)
    assert rc == 0, (name, rc, so[-600:], se[-600:])


@pytest.mark.parametrize("mutation", MUTATIONS)
@pytest.mark.parametrize("name", v3c.CONF_TEXTS)
def test_e_nocanon_trace(nocanon, tmp_path, name, mutation):
    b, pin = nocanon
    d = tmp_path / "c"
    shutil.copytree(b, d)
    key = B._plant_path(d / "trace.json", mutation)
    rc, so, se = v3c._run_conf(d, name, pin)
    A._assert_refused(rc, so, se, "trace.json", mutation, key)


# --------------------------------------------- ndec verify --registry leaf


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_e_registry_leaf(env, tmp_path, monkeypatch, capsys, mutation):
    import ndec
    import test_s148_u2_ndec_registry as t
    from cryptography.hazmat.primitives.asymmetric import ed25519
    out = t._build_mini_ndec(tmp_path)
    reg_key = ed25519.Ed25519PrivateKey.generate()
    reg, log_allow = t._logged_registry(
        "VERIFY_OFFLINE_PY_FARKAS", "5.99.0", t._mini_sha(), reg_key)
    body = base64.b64decode(reg["rekor_anchor"]["body_b64"])
    raw, key = B._plant_bytes(body, mutation)
    reg["rekor_anchor"]["body_b64"] = base64.b64encode(raw).decode("ascii")
    reg_path = tmp_path / "reg.json"
    reg_path.write_text(json.dumps(reg), encoding="utf-8")
    t._install_pins(monkeypatch, reg_key, log_allow)
    capsys.readouterr()
    rc = ndec.verify_ndec_file(
        out, strict_canonical=True, registry_path=str(reg_path),
        public_key=t.key_public(tmp_path / "k.key"))
    cap = capsys.readouterr()
    C._refused_ndec((rc, cap.out, cap.err), "leaf", mutation, key)


# ------------------------------------------------- attest_apr vendor body


USAGE = '"usage": {"prompt_tokens": 3, "completion_tokens": 4}'
VENDOR = {
    "body_dup": ('{"id": "x", "id": "y", ' + USAGE + '}', "id", "dup"),
    "chunk_dup": ('data: {"x": 1, "x": 2}\ndata: {' + USAGE + '}\n'
                  'data: [DONE]\n', "x", "dup"),
    "usage_then_null": ('data: {' + USAGE + ', "usage": null}\n'
                        'data: [DONE]\n', "usage", "dup"),
    "nan": ('{"usage": {"prompt_tokens": NaN, "completion_tokens": 4}}',
            "NaN", "token"),
}


@pytest.mark.parametrize("case", sorted(VENDOR))
def test_e_vendor_body(case):
    import attest_apr
    body, key, kind = VENDOR[case]
    exc = None
    try:
        attest_apr._parse_vendor_usage(body)
    except Exception as e:  # noqa: BLE001
        exc = e
    assert exc is not None, (A.RAN, case, "accepted")
    assert getattr(exc, "an_js_refusal", False), (A.RAN, case, repr(exc))
    msg = str(exc)
    assert "vendor_response_body" in msg, (A.RAN, case, msg)
    if kind == "dup":
        assert "refused: duplicate key " + repr(key) in msg, (A.RAN, case,
                                                               msg)
    else:
        assert key in msg, (A.RAN, case, msg)
    assert VENDOR_PHRASE in msg, (A.RAN, case, msg)
    assert "a NOUS writer" not in msg, (A.RAN, case, msg)
    A.HITS.update(A.TAG.findall(msg))


# ------------------------------------------------------ nous verify X.ndec


@pytest.fixture(scope="module")
def ndec_fam(env):
    sub = env / "ndec"
    sub.mkdir()
    return C._b_ndec_cli(sub)


def _rezip(x: Path, order) -> Path:
    out = x.parent / (x.name + ".ndec")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n in order:
            z.write(x / n, n)
    return out


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_e_nous_verify_ndec(env, ndec_fam, tmp_path, mutation):
    d = tmp_path / "case"
    shutil.copytree(ndec_fam.d, d)
    order = zipfile.ZipFile(next((env / "ndec").glob("*.ndec"))).namelist()
    key = C._ndec_manifest(ndec_fam, d, mutation)
    rc, so, se = C._cli(["verify", _rezip(d, order)])
    assert "Traceback" not in se, (A.RAN, mutation, se[-600:])
    C._refused_ndec((rc, so, se), "dossier/manifest.json", mutation, key)


# ---------------------------------------- the NOUS-TRACE reference verifier


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_e_reference_verifier_keys(tmp_path, monkeypatch, mutation):
    import test_c4_rekor_verify as t
    pack = t._pack(tmp_path, monkeypatch, timed=False)
    p = pack / "rekor_log_keys.json"
    assert p.is_file(), "the pack carries no pinned log keys file"
    key = B._plant_path(p, mutation)
    r = subprocess.run([sys.executable, "-I", "-B",
                        str(REPO / "trace" / "reference" / "verifier.py"),
                        str(pack)], capture_output=True, text=True,
                       timeout=300)
    assert "Traceback" not in r.stderr, (A.RAN, mutation, r.stderr[-600:])
    assert r.returncode == 20, (A.RAN, mutation, r.returncode,
                                r.stdout[-600:])
    rep = json.loads(r.stdout)
    assert rep["verdict"].startswith("INVALID"), (A.RAN, mutation, rep)
    C._named(str(rep.get("detail")), "auditor-pinned log keys", mutation,
             key)


# ------------------------------------------ nous continuity verify --json


@pytest.fixture(scope="module")
def cont(env):
    import test_s178_checkpoint_leg as t
    sub = env / "cont"
    sub.mkdir()
    op, cp = t._keys(sub)
    return t._build_priced_ledger(sub, op, cp, ["0.10", "0.20"]), sub


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_e_continuity_cli_json(cont, tmp_path, mutation):
    from test_an_js_strict_d import _refused_json
    ledger, sub = cont
    d = tmp_path / "ledger"
    shutil.copytree(ledger, d)
    key = B._plant_path(d / "000" / "link.json", mutation)
    res = C._cli(["continuity", "verify", "--ledger", d, "--json"]
                 + C._cont_args(sub))
    _refused_json(res, "link.json", mutation, key)
