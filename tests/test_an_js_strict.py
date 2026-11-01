"""AN-GATE-1 D4/D5 (D432-12): strict JSON in every verifier input.

K-JS.1, K-JS.2 and K-JS.5, phase A. Predictions: JS_RED_PREDICTIONS.txt
f47e2662..., amended by JS_B_PREDICTIONS.txt 5f75237f... (A1, A2).
Every verifier refuses, as INTEGRITY, a JSON input with a
duplicate member name or a NaN, Infinity or -Infinity token, and says
which file and which key or token. A non-finite refusal also says that
a NOUS writer can write the token, so it is not by itself evidence of
tampering.

"Nested" means inside the first object below the top level, in
document order. In a flat file, one with no object below its top
level, it means inside an object held by one member added last:
"an_js_nested": {"n": 0} (amendment C-A2, JS_C_AMEND.txt d8f1625f).

# __an_js_strict_tests_v1__
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import tomllib
import zipfile
from pathlib import Path

import pytest

import manifest as mf
import ndec
import test_nt_v3_classes as v3c

REPO = Path(__file__).resolve().parent.parent
REGION_START = (
    "# --- strict json embed (shared text; canonical copy: "
    "conformance_verifier.py) ---"
)
REGION_END = "# --- end strict json embed ---"
MARK = "__an_js_strict_v1__"
NONFINITE_PHRASE = (
    "a NOUS writer can write this token, so this refusal is not by "
    "itself evidence of tampering"
)
MUTATIONS = ("dup_before", "dup_after", "dup_nested", "dup_after_nested",
             "nan_top", "inf_nested", "neginf_top")
TOKENS = {"nan_top": "NaN", "inf_nested": "Infinity",
          "neginf_top": "-Infinity"}


# ------------------------------------------------------------ planting


class _Raw:
    def __init__(self, text: str):
        self.text = text


def _ser(o) -> str:
    if isinstance(o, _Raw):
        return o.text
    if isinstance(o, _Obj):
        return "{" + ", ".join(
            json.dumps(k) + ": " + _ser(v) for k, v in o.items) + "}"
    if isinstance(o, dict):
        return "{" + ", ".join(
            json.dumps(k) + ": " + _ser(v) for k, v in o.items()) + "}"
    if isinstance(o, list):
        return "[" + ", ".join(_ser(v) for v in o) + "]"
    return json.dumps(o)


class _Obj:
    def __init__(self, items):
        self.items = items


def _other(v):
    if isinstance(v, bool):
        return not v
    if isinstance(v, int):
        return v + 1
    if isinstance(v, str):
        return "PLANTED" if v != "PLANTED" else "PLANTED2"
    return "PLANTED"


def _first_nested(doc):
    # (container, key) of the first object below the top level, in
    # document order, reached through objects and arrays.
    stack = [doc]
    first = True
    while stack:
        o = stack.pop(0)
        if isinstance(o, dict):
            if not first and o:
                return o
            first = False
            stack = list(o.values()) + stack
        elif isinstance(o, list):
            stack = list(o) + stack
    return None


def _plant(text: str, mutation: str):
    """Return (planted text, key) for one mutation of a JSON document."""
    doc = json.loads(text)
    assert isinstance(doc, dict) and doc, "top level must be an object"
    keys = list(doc)
    k0 = keys[0]
    if mutation == "dup_before":
        top = _Obj([(k0, _other(doc[k0]))] + list(doc.items()))
        return _ser(top), k0
    if mutation == "dup_after":
        top = _Obj(list(doc.items()) + [(k0, _other(doc[k0]))])
        return _ser(top), k0
    if mutation == "nan_top":
        return _ser(dict(doc, **{k0: _Raw("NaN")})), k0
    if mutation == "neginf_top":
        kl = keys[-1]
        return _ser(dict(doc, **{kl: _Raw("-Infinity")})), kl
    nested = _first_nested(doc)
    if nested is None:
        # C-A2: a flat document gets one last member holding an object.
        doc = dict(doc, an_js_nested={"n": 0})
        nested = doc["an_js_nested"]
    nk = next(iter(nested))
    if mutation == "dup_nested":
        repl = _Obj([(nk, _other(nested[nk]))] + list(nested.items()))
    elif mutation == "dup_after_nested":
        repl = _Obj(list(nested.items()) + [(nk, _other(nested[nk]))])
    else:
        repl = dict(nested, **{nk: _Raw("Infinity")})

    def walk(o):
        if o is nested:
            return repl
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        if isinstance(o, list):
            return [walk(v) for v in o]
        return o
    return _ser(walk(doc)), nk


# The red barrier (RULING 10:44Z, Q2.2): every refusal check asserts
# through these functions, and every one of their messages starts with
# RAN. They run only after the verifier has run, so a failure without
# RAN (the planter, a producer, a fixture) is never counted red.
RAN = "AN_JS_VERIFIER_RAN"
# K-JS.7 (RULING 11:58Z, round 3, 1): every region call site carries a
# tag [js:<object>.<n>] in its label; a refusal check records the tags it
# sees, and tests/test_an_js_zz_sites.py compares them with the scope.
TAG = re.compile(r"\[js:([a-z0-9_]+\.\d+)\]")
HITS: set = set()


def _assert_refused(rc, so, se, fname, mutation, key):
    lines = [ln for ln in se.splitlines() if ln.strip()]
    last = lines[-1] if lines else ""
    assert rc == 1, (RAN, fname, mutation, rc, so[-400:], se[-400:])
    assert v3c._last_line(so) == "CLASS: INTEGRITY", (RAN, fname, mutation,
                                                      so)
    assert fname in last, (RAN, fname, mutation, last)
    if mutation.startswith("dup_"):
        assert "refused: duplicate key " + repr(key) in last, (
            RAN, fname, mutation, last)
    else:
        assert TOKENS[mutation] in last, (RAN, fname, mutation, last)
        assert NONFINITE_PHRASE in last, (RAN, fname, mutation, last)
    HITS.update(TAG.findall(last))


# ------------------------------------------------------------- K-JS.2


def _texts21() -> dict:
    out = dict(v3c._texts())
    import annex_iv_map
    import build_vsa
    import continuity_verifier
    import provenance_verifier
    out["build_vsa.template"] = build_vsa.BUILD_VSA_VERIFY_OFFLINE_PY
    out["provenance.template"] = (
        provenance_verifier.PROVENANCE_VERIFY_OFFLINE_PY)
    out["continuity.template"] = (
        continuity_verifier.CONTINUITY_VERIFY_OFFLINE_PY)
    out["annex_iv.built"] = annex_iv_map.build_annex_iv_verifier()
    import guardrails_adapter
    import llm_guard_adapter
    import santander_adapter
    out["adapter.guardrails"] = guardrails_adapter._STANDALONE_VERIFIER
    out["adapter.llm_guard"] = llm_guard_adapter._STANDALONE_VERIFIER
    out["adapter.santander"] = santander_adapter._STANDALONE_VERIFIER
    assert len(out) == 21
    return out


TEXT21 = tuple(sorted(_texts21()))


def _region(text: str):
    if text.count(REGION_START) != 1:
        return None
    i = text.index(REGION_START)
    j = text.find(REGION_END, i)
    return None if j < 0 else text[i:j + len(REGION_END)]


def test_kjs2_canonical_region():
    src = (REPO / "conformance_verifier.py").read_text(encoding="utf-8")
    m = re.findall(
        r"(?ms)^" + re.escape(REGION_START) + r"$.*?^"
        + re.escape(REGION_END) + r"$", src)
    assert len(m) == 1, "canonical strict json region absent or repeated"
    assert MARK in m[0]


@pytest.mark.parametrize("name", TEXT21)
def test_kjs2_region_in_text(name):
    src = (REPO / "conformance_verifier.py").read_text(encoding="utf-8")
    m = re.search(
        r"(?ms)^" + re.escape(REGION_START) + r"$.*?^"
        + re.escape(REGION_END) + r"$", src)
    assert m is not None, "no canonical region"
    assert _region(_texts21()[name]) == m.group(0), name


def test_kjs2_region_in_reference_verifier():
    # __an_js_r2_v1__ trace/reference/verifier.py splices rekor_check.py,
    # whose leaf and pinned-keys parses call the region (round 2), so it
    # carries the region too; its other reads are outside D4 (3.5).
    src = (REPO / "conformance_verifier.py").read_text(encoding="utf-8")
    m = re.search(
        r"(?ms)^" + re.escape(REGION_START) + r"$.*?^"
        + re.escape(REGION_END) + r"$", src)
    ref = (REPO / "trace" / "reference" / "verifier.py").read_text(
        encoding="utf-8")
    assert _region(ref) == m.group(0)


# ------------------------------------------------------------ bundles


_CACHE: dict = {}


def _pricing_table():
    s97 = v3c.s97
    return s97._PricingTable.model_validate(tomllib.loads(s97.PRICING_TOML))


@pytest.fixture(scope="module")
def bundles(tmp_path_factory):
    import dated_prices
    root = tmp_path_factory.mktemp("an_js")
    conf_b, conf_pin = v3c._conf_bundle(_pricing_table(), root,
                                        v3c.GENUINE(), name="conf")
    vsa_b, vsa_pin = v3c._vsa_mint(root, 100, "vsa")
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("XDG_DATA_HOME", raising=False)  # __an_js_tmp_keys_v1__
        dated_prices.use_dated_shipped_prices(root / "prices", mp)
        dos_b, dos_pin = v3c._dossier(root, v3c.PROVEN_SRC, "dos")
        nd = ndec.build_ndec(dos_b, key_path=root / "ndec.key",
                             output=root / "d.ndec")
    _p, npub, _ = mf.load_or_create_keypair(root / "ndec.key")
    nd_dir = root / "nd"
    with zipfile.ZipFile(nd.path) as z:
        z.extractall(nd_dir)
    return {
        "conf": (conf_b, conf_pin),
        "vsa": (vsa_b, vsa_pin),
        "dos": (dos_b, dos_pin, root / "dos_work" / "signing.key"),
        "ndec": (nd_dir, mf.public_key_b64(npub)),
    }


def _copy(src: Path, tmp_path: Path, tag: str) -> Path:
    d = tmp_path / tag
    shutil.copytree(src, d)
    return d


def _plant_file(d: Path, fname: str, mutation: str) -> str:
    p = d / fname
    planted, key = _plant(p.read_text(encoding="utf-8"), mutation)
    p.write_text(planted, encoding="utf-8")
    return key


# -------------------------------------------------- K-JS.1/5, conformance


CONF_FILES = ("conformance.json", "manifest.json", "trace.json")


def test_conf_bundle_baseline(bundles, tmp_path):
    b, pin = bundles["conf"]
    for name in v3c.CONF_TEXTS:
        d = _copy(b, tmp_path, name)
        rc, so, se = v3c._run_conf(d, name, pin)
        assert rc == 0, (name, rc, so, se)


@pytest.mark.parametrize("mutation", MUTATIONS)
@pytest.mark.parametrize("fname", CONF_FILES)
@pytest.mark.parametrize("name", v3c.CONF_TEXTS)
def test_kjs_conformance(bundles, tmp_path, name, fname, mutation):
    b, pin = bundles["conf"]
    d = _copy(b, tmp_path, "c")
    key = _plant_file(d, fname, mutation)
    rc, so, se = v3c._run_conf(d, name, pin)
    _assert_refused(rc, so, se, fname, mutation, key)


# ----------------------------------------------------------- K-JS.1/5, VSA


VSA_FILES = ("vsa.intoto.json", "manifest.json", "conformance.json",
             "trace.json")


def test_vsa_bundle_baseline(bundles, tmp_path):
    b, pin = bundles["vsa"]
    d = _copy(b, tmp_path, "v")
    rc, so, se = v3c._run(d, "verify_vsa_offline.py",
                          ["--expect-signer", pin])
    assert rc == 0, (rc, so, se)


@pytest.mark.parametrize("mutation", MUTATIONS)
@pytest.mark.parametrize("fname", VSA_FILES)
def test_kjs_vsa(bundles, tmp_path, fname, mutation):
    b, pin = bundles["vsa"]
    d = _copy(b, tmp_path, "v")
    key = _plant_file(d, fname, mutation)
    rc, so, se = v3c._run(d, "verify_vsa_offline.py",
                          ["--expect-signer", pin])
    _assert_refused(rc, so, se, fname, mutation, key)


# ------------------------------------------------------- K-JS.1/5, dossier


def _resign_manifest(d: Path, key_path: Path, field: str, digest: str):
    priv, _pub, _ = mf.load_or_create_keypair(key_path)
    p = d / "manifest.json"
    man = json.loads(p.read_text(encoding="utf-8"))
    man[field] = digest
    body = {k: v for k, v in man.items()
            if k not in ("signature", "transparency_log")}
    sig = priv.sign(json.dumps(body, sort_keys=True,
                               separators=(",", ":")).encode("utf-8"))
    man["signature"]["signature_b64"] = base64.b64encode(sig).decode()
    p.write_text(json.dumps(man, indent=2, sort_keys=True) + "\n",
                 encoding="utf-8")


def test_dossier_bundle_baseline(bundles, tmp_path):
    b, pin, _k = bundles["dos"]
    d = _copy(b, tmp_path, "d")
    rc, so, se = v3c._run(d, "verify_offline.py", ["--expect-signer", pin])
    assert rc == 0, (rc, so, se)
    carried = hashlib.sha256((d / "verify_offline.py").read_bytes())
    names = [n for n, t in v3c._texts().items()
             if hashlib.sha256(t.encode()).digest() == carried.digest()]
    print("dossier template:", names, sorted(p.name for p in d.iterdir()))


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_kjs_dossier_manifest(bundles, tmp_path, mutation):
    b, pin, _k = bundles["dos"]
    d = _copy(b, tmp_path, "d")
    key = _plant_file(d, "manifest.json", mutation)
    rc, so, se = v3c._run(d, "verify_offline.py", ["--expect-signer", pin])
    _assert_refused(rc, so, se, "manifest.json", mutation, key)


REBOUND = (("cost.farkas.json", "cost_farkas_sha256"),)


@pytest.mark.parametrize("mutation", MUTATIONS)
@pytest.mark.parametrize("fname,field", REBOUND)
def test_kjs_dossier_rebound(bundles, tmp_path, fname, field, mutation):
    b, pin, keyp = bundles["dos"]
    d = _copy(b, tmp_path, "d")
    assert (d / fname).is_file(), fname
    key = _plant_file(d, fname, mutation)
    _resign_manifest(d, keyp, field,
                     hashlib.sha256((d / fname).read_bytes()).hexdigest())
    rc, so, se = v3c._run(d, "verify_offline.py", ["--expect-signer", pin])
    _assert_refused(rc, so, se, fname, mutation, key)


# ---------------------------------------------------------- K-JS.1/5, ndec


def test_ndec_bundle_baseline(bundles, tmp_path):
    b, pin = bundles["ndec"]
    d = _copy(b, tmp_path, "n")
    rc, so, se = v3c._run(d, "verify_ndec.py", ["--expect-signer", pin])
    assert rc == 0, (rc, so, se)


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_kjs_ndec_envelope(bundles, tmp_path, mutation):
    b, pin = bundles["ndec"]
    d = _copy(b, tmp_path, "n")
    key = _plant_file(d, "attestation.intoto.json", mutation)
    rc, so, se = v3c._run(d, "verify_ndec.py", ["--expect-signer", pin])
    _assert_refused(rc, so, se, "attestation.intoto.json", mutation, key)


# ------------------------------------------------------------- planter


PLANTER_DOCS = {"nested": {"a": 1, "b": {"c": "x", "d": [{"e": 2}]},
                           "z": "q"},
                "flat": {"a": 1, "l": ["x", 2], "z": "q"}}


@pytest.mark.parametrize("mutation", MUTATIONS)
@pytest.mark.parametrize("shape", sorted(PLANTER_DOCS))
def test_planter_self_check(shape, mutation):
    src = json.dumps(PLANTER_DOCS[shape])
    text, key = _plant(src, mutation)
    if shape == "flat" and mutation in ("dup_nested", "dup_after_nested",
                                        "inf_nested"):
        assert key == "n" and '"an_js_nested": {' in text, text
    pairs_seen = []

    def hook(pairs):
        pairs_seen.append([k for k, _ in pairs])
        return dict(pairs)
    consts = []
    json.loads(text, object_pairs_hook=hook,
               parse_constant=lambda c: consts.append(c) or 0.0)
    dups = [p for p in pairs_seen if len(p) != len(set(p))]
    if mutation.startswith("dup_"):
        assert len(dups) == 1 and key in dups[0], (mutation, text)
        assert consts == []
    else:
        assert dups == [] and consts == [TOKENS[mutation]], (mutation, text)
