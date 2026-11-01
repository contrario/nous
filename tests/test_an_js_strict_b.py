"""AN-GATE-1 D4/D5 (D432-12): strict JSON, phase B (K-JS.1, K-JS.5).

Predictions: JS_B_PREDICTIONS.txt 5f75237f... The families of section
B1 to B17: every JSON input of the V3 verifier texts and the dossier
splices that read JSON, reached through its bindings. A "rebind" input
is planted, then every digest and signature that binds it is
recomputed with the key the test holds, so the planted bytes reach the
parser; each rebind has an identity case that must keep the family's
baseline.

# __an_js_strict_b_tests_v1__
"""
from __future__ import annotations

import argparse
import base64
import dataclasses
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import pytest

import manifest as mf
import ndec
import test_an_js_strict as A
import test_nt_v3_classes as v3c

MUTATIONS = A.MUTATIONS
EXCL = ("signature", "transparency_log")
LEAF = {
    "apiVersion": "0.0.2", "kind": "hashedrekord",
    "spec": {"hashedRekordV002": {
        "data": {"algorithm": "SHA2_256", "digest": "AAAA"},
        "signature": {"content": "AAAA", "verifier": {
            "keyDetails": "PKIX_ECDSA_P256_SHA_256",
            "publicKey": {"rawBytes": "AAAA"}}}}},
}


# ------------------------------------------------------------- helpers


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _canon(doc: dict, exclude=EXCL) -> bytes:
    body = {k: v for k, v in doc.items() if k not in exclude}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def _priv(keyfile):
    return mf.load_or_create_keypair(Path(keyfile))[0]


def _pin_of(priv) -> str:
    return _b64(priv.public_key().public_bytes_raw())


def _resign(path: Path, priv, edit=None, exclude=EXCL) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if edit:
        edit(doc)
    doc["signature"]["signature_b64"] = _b64(priv.sign(_canon(doc,
                                                              exclude)))
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def _plant_path(p: Path, mutation):
    if mutation is None:
        return None
    text, key = A._plant(p.read_text(encoding="utf-8"), mutation)
    p.write_text(text, encoding="utf-8")
    return key


def _plant_bytes(raw: bytes, mutation):
    if mutation is None:
        return raw, None
    text, key = A._plant(raw.decode("utf-8"), mutation)
    return text.encode("utf-8"), key


def _pae(pt: str, payload: bytes) -> bytes:
    p = pt.encode("utf-8")
    return b"DSSEv1 %d %s %d %s" % (len(p), p, len(payload), payload)


def _dsse_payload(env_path: Path, priv, mutation, edit=None):
    env = json.loads(env_path.read_text(encoding="utf-8"))
    payload = base64.b64decode(env["payload"])
    if edit is not None:
        payload = edit(payload)
    payload, key = _plant_bytes(payload, mutation)
    env["payload"] = _b64(payload)
    env["signatures"][0]["sig"] = _b64(priv.sign(_pae(env["payloadType"],
                                                     payload)))
    env_path.write_text(json.dumps(env, sort_keys=True), encoding="utf-8")
    return key


def _cov_args(src: Path, mout: Path, key: Path, threshold,
              supersedes=None, full=False):
    class Args:
        file = str(src)
        smt = True
        prices = None
        timeout_ms = 30000
        no_manifest = False
        manifest_out = str(mout)
        key_path = str(key)
        smt_margin = 0
        coverage_threshold = threshold
        no_lint = True
        lint_strict = False
        lint_error_on = None
    Args.supersedes = str(supersedes) if supersedes else None
    Args.chain_coverage = "full" if full else None
    return Args()


def _verify(d: Path, text: str, threshold, key: Path, supersedes=None,
            full=False):
    from cli_verify import cmd_verify
    d.mkdir(parents=True, exist_ok=True)
    src = d / "source.nous"
    src.write_text(text, encoding="utf-8")
    mout = d / "source.manifest.json"
    assert cmd_verify(_cov_args(src, mout, key, threshold, supersedes,
                                full)) == 0
    return src, mout


def _run_dossier(d: Path, pin: str, extra=()):
    return v3c._run(d, "verify_offline.py",
                    list(extra) + ["--expect-signer", pin])


# ------------------------------------------------------------ families


class Fam:
    def __init__(self, d, run, baseline, **info):
        self.d, self.run, self.baseline, self.info = d, run, baseline, info


def _b_farkas(root):
    import test_dossier_coverage as tc
    from dossier import build_dossier
    w = root / "farkas_w"
    w.mkdir()
    src, mout = tc._proven_coverage_run(w)
    out = root / "farkas"
    build_dossier(src, manifest=mout, output=out)
    key = w / "signing.key"
    pin = _pin_of(_priv(key))
    return Fam(out, lambda d: _run_dossier(d, pin), 0, key=key)


def _b_bundle(root):
    import test_s124_farkas_dnf_bundle as t
    from dossier import build_dossier
    key = root / "bundle.key"
    src, mout = _verify(root / "bundle_w",
                        t._BOOL_NOUS.replace("COST_CAP", "0.50"),
                        t._BOOL_THRESHOLD, key)
    out = root / "bundle"
    build_dossier(src, manifest=mout, output=out)
    pin = _pin_of(_priv(key))
    return Fam(out, lambda d: _run_dossier(d, pin), 0, key=key)


def _b_coverage(root):
    import test_dossier_coverage as tc
    from dossier import build_dossier
    w = root / "coverage_w"
    w.mkdir()
    src, mout = tc._proven_coverage_run(w)
    key = w / "signing.key"
    m, _s, _p = mf.parse_manifest_json(mout.read_text(encoding="utf-8"))
    m2 = dataclasses.replace(m, coverage_farkas_sha256=None)
    priv, pub, _ = mf.load_or_create_keypair(key)
    mout.write_text(mf.manifest_json(m2, mf.sign_manifest(m2, priv), pub),
                    encoding="utf-8")
    out = root / "coverage"
    build_dossier(src, manifest=mout, output=out)
    assert not (out / "coverage.farkas.json").exists()
    pin = _pin_of(priv)
    return Fam(out, lambda d: _run_dossier(d, pin), 0, key=key)


def _b_rekor_v1(root):
    from test_rekor_anchor import _valid_anchor
    out, pin = v3c._dossier(root, v3c.PROVEN_SRC, "rekor1", anchor="rekor",
                            _test_rekor_anchor=_valid_anchor())
    key = root / "rekor1_work" / "signing.key"
    return Fam(out, lambda d: _run_dossier(d, pin), 1, key=key)


def _b_rekor_v2_unanchored(root):
    out, pin = v3c._rekor_v2_dossier(root, v3c.PROVEN_SRC, "v2u", False)
    return Fam(out, lambda d: _run_dossier(d, pin, ["--allow-unanchored"]),
               0)


def _set_leaf(path: Path, leaf_bytes: bytes) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["transparency_log"]["body_b64"] = _b64(leaf_bytes)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def _b_rekor_v2_leaf(root):
    out, pin = v3c._rekor_v2_dossier(root, v3c.PROVEN_SRC, "v2l", True)
    _set_leaf(out / "manifest.json", json.dumps(LEAF).encode())
    return Fam(out, lambda d: _run_dossier(d, pin), 1)


def _b_chain(root):
    from test_s120_chain_carry import _genesis, _child
    from dossier import build_dossier
    g = root / "chain_g"
    g.mkdir()
    gsrc, gm = _genesis(g)
    d0 = root / "chain_d0"
    build_dossier(gsrc, manifest=gm, output=d0)
    c = root / "chain_c"
    c.mkdir()
    csrc, cm = _child(c, gm)
    out = root / "chain"
    build_dossier(csrc, manifest=cm, output=out, supersedes=d0)
    ckey, gkey = c / "signing.key", g / "signing.key"
    pin = _pin_of(_priv(ckey))
    return Fam(out, lambda d: _run_dossier(d, pin), 0, key=ckey,
               link_key=gkey)


def _b_chain_bundle(root):
    import test_s125_chain_bundle as t
    from dossier import build_dossier
    key = root / "cb.key"
    s1, m1 = _verify(root / "cb_l1", t._SRC.replace("COST_CAP", "0.50"),
                     t._SCALAR_THRESHOLD, key)
    d1 = root / "cb_d1"
    build_dossier(s1, manifest=m1, output=d1)
    s2, m2 = _verify(root / "cb_l2", t._SRC.replace("COST_CAP", "0.40"),
                     t._SCALAR_THRESHOLD, key, supersedes=m1)
    out = root / "chain_bundle"
    build_dossier(s2, manifest=m2, output=out, supersedes=d1)
    pin = _pin_of(_priv(key))
    return Fam(out, lambda d: _run_dossier(d, pin), 0, key=key,
               link_key=key)


def _b_chain_net(root):
    import test_s127_net_e2e as t
    from dossier import build_dossier
    key = root / "net.key"
    s1, m1 = _verify(root / "net_l1", t._src("4000", "0.50"), None, key)
    d1 = root / "net_d1"
    build_dossier(s1, manifest=m1, output=d1)
    s2, m2 = _verify(root / "net_l2", t._src("2000", "0.40"), None, key,
                     supersedes=m1, full=True)
    out = root / "chain_net"
    build_dossier(s2, manifest=m2, output=out, supersedes=d1)
    pin = _pin_of(_priv(key))
    return Fam(out, lambda d: _run_dossier(d, pin), 0, key=key,
               link_key=key)


def _b_gapw(root):
    import test_s134_gapw_e2e as gw
    from dossier import build_dossier
    w = root / "gapw_w"
    w.mkdir()
    src = gw._issue(w)
    out = root / "gapw"
    build_dossier(src, manifest=w / "source.manifest.json", output=out)
    key = w / "signing.key"
    pin = _pin_of(_priv(key))
    return Fam(out, lambda d: _run_dossier(d, pin), 3, key=key)


def _b_conf_leaf(root):
    import offline_verifier_builder as ob
    from rekor_verify_v2 import KNOWN_REKOR_V2_LOG_KEYS
    from test_s93_dossier_rekor_v2_emit import _fake_v2_anchor
    b, pin = v3c._conf_bundle(A._pricing_table(), root, v3c.GENUINE(),
                              name="confleaf")
    (b / "verify_conformance_offline.py").write_text(
        ob.build_conformance_verifier_v2(repr(KNOWN_REKOR_V2_LOG_KEYS)),
        encoding="utf-8")
    cert = json.loads((b / "conformance.json").read_text(encoding="utf-8"))
    cert["transparency_log"] = _fake_v2_anchor().to_manifest_block()
    (b / "conformance.json").write_text(
        json.dumps(cert, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _set_leaf(b / "conformance.json", json.dumps(LEAF).encode())
    return Fam(b, lambda d: v3c._run(d, "verify_conformance_offline.py",
                                     ["--expect-signer", pin]), 1)


def _b_vsa(root):
    b, pin = v3c._vsa_mint(root, 100, "vsa_b")
    hv = v3c._harness()
    return Fam(b, lambda d: v3c._run(d, "verify_vsa_offline.py",
                                     ["--expect-signer", pin]), 0,
               vsa_priv=hv._fixed_key(hv._SEED_VSA))


def _b_vsa_registry(root):
    import test_nt_v3_review as t
    d, reg = t._registry_only(root, "valid")
    (d / "verifier-registry.json").write_text(
        json.dumps(t._signed_registry(reg, t.VSA_KEY)), encoding="utf-8")
    return Fam(d, lambda x: v3c._run(x, "verify_vsa_offline.py",
                                     ["--expect-signer", t.VSA_KEY]), 0)


def _b_ndec(root):
    out, _pin = v3c._dossier(root, v3c.PROVEN_SRC, "ndb")
    nd = ndec.build_ndec(out, key_path=root / "ndb.key",
                         output=root / "ndb.ndec")
    priv, pub, _ = mf.load_or_create_keypair(root / "ndb.key")
    d = root / "ndec_b"
    with zipfile.ZipFile(nd.path) as z:
        z.extractall(d)
    pin = mf.public_key_b64(pub)
    return Fam(d, lambda x: v3c._run(x, "verify_ndec.py",
                                     ["--expect-signer", pin]), 0,
               ndec_priv=priv)


def _b_materiality(root):
    import test_s171_materiality_e2e as t
    from dossier import build_dossier
    w = root / "mat_w"
    w.mkdir()
    src, mout, key = t._proven_manifest(w)
    t._attach_materiality(mout, key, "material")
    out = root / "mat"
    build_dossier(src, manifest=mout, output=out)
    pin = _pin_of(_priv(key))
    return Fam(out, lambda d: _run_dossier(d, pin), 0, key=key)


def _b_pce(root):
    import test_s171_materiality_e2e as t
    import test_s190_pce_dossier as p
    from dossier import build_dossier
    w = root / "pce_w"
    w.mkdir()
    src, mout, key = t._proven_manifest(w)
    pre = root / "pce_pre"
    build_dossier(src, manifest=mout, output=pre)
    base = (pre / "spec.canon").read_bytes()
    (mout.parent / "baseline.canon").write_bytes(base)
    pj = json.dumps(p._pce(p._CUM_OPEN, base_sha=_sha(base)),
                    sort_keys=True, separators=(",", ":")).encode()
    (mout.parent / "pce.json").write_bytes(pj)
    m, _s, _p = mf.parse_manifest_json(mout.read_text(encoding="utf-8"))
    m = dataclasses.replace(m, pce_sha256=_sha(pj))
    priv, pub, _ = mf.load_or_create_keypair(key)
    mout.write_text(mf.manifest_json(m, mf.sign_manifest(m, priv), pub),
                    encoding="utf-8")
    out = root / "pce"
    build_dossier(src, manifest=mout, output=out)
    return Fam(out, lambda d: _run_dossier(d, _pin_of(priv)), 0, key=key)


def _b_trace_bundle(root):
    import test_trace_bundle_dossier_e2e as t
    import dossier
    w = root / "tb_w"
    w.mkdir()
    src, mp = t._signed_source(w)
    t._attach_bundle_and_resign(w, mp)
    out = root / "tb"
    dossier.build_dossier(src, output=out)
    priv = _priv(w / "op.key")  # __an_js_tmp_keys_v1__
    return Fam(out, lambda d: _run_dossier(d, _pin_of(priv)), 0,
               op_priv=priv)


def _b_attribution(root):
    import test_s180_attribution as t
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey)
    authz = Ed25519PrivateKey.generate()
    op = Ed25519PrivateKey.generate()
    d = root / "attr"
    d.mkdir()
    base = mf.Manifest(**t.FIELDS)
    base = dataclasses.replace(base,
                               source_sha256=_sha(b"world demo {}\n"))
    attr, _kid = t._attestation_for(base.run_digest(), authz)
    m = dataclasses.replace(base, attribution=attr)
    proc, _text, _m = t._emit_and_run(str(d), m, op)
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    return Fam(d, lambda x: _run_dossier(x, _pin_of(op)), 0, op_priv=op)


BUILDERS = {
    "farkas": _b_farkas, "bundle": _b_bundle, "coverage": _b_coverage,
    "rekor_v1": _b_rekor_v1, "rekor_v2_unanchored": _b_rekor_v2_unanchored,
    "rekor_v2_leaf": _b_rekor_v2_leaf, "chain": _b_chain,
    "chain_bundle": _b_chain_bundle, "chain_net": _b_chain_net,
    "gapw": _b_gapw, "conf_leaf": _b_conf_leaf, "vsa": _b_vsa,
    "vsa_registry": _b_vsa_registry, "ndec": _b_ndec,
    "materiality": _b_materiality, "pce": _b_pce,
    "trace_bundle": _b_trace_bundle, "attribution": _b_attribution,
}
NEEDS_PRICES = {"farkas", "bundle", "coverage", "rekor_v1",
                "rekor_v2_unanchored", "rekor_v2_leaf", "chain",
                "chain_bundle", "chain_net", "gapw", "ndec", "materiality",
                "pce", "trace_bundle"}


@pytest.fixture(scope="module")
def fams(tmp_path_factory):
    import dated_prices
    cache: dict = {}
    root = tmp_path_factory.mktemp("an_js_b")
    mp = pytest.MonkeyPatch()
    mp.delenv("XDG_DATA_HOME", raising=False)  # __an_js_tmp_keys_v1__
    dated_prices.use_dated_shipped_prices(root / "prices", mp)
    default_key = mf.default_key_path()

    def get(name):
        if name not in cache:
            sub = root / name
            sub.mkdir()
            cache[name] = BUILDERS[name](sub)
        return cache[name]
    yield get
    made = default_key.exists()
    mp.undo()
    assert not made, "a test created the default key " + str(default_key)


# --------------------------------------------------------------- inputs


def _plain(fname):
    def apply(f, d, mutation):
        return _plant_path(d / fname, mutation)
    return apply


def _rebind_manifest_field(fname, field, exclude=EXCL):
    def apply(f, d, mutation):
        key = _plant_path(d / fname, mutation)
        digest = _sha((d / fname).read_bytes())
        _resign(d / "manifest.json", _priv(f.info["key"]),
                lambda doc: doc.__setitem__(field, digest), exclude)
        return key
    return apply


def _rebind_link_cov(link_manifest, link_file):
    def apply(f, d, mutation):
        key = _plant_path(d / "chain" / link_file, mutation)
        digest = _sha((d / "chain" / link_file).read_bytes())
        lp = d / "chain" / link_manifest
        _resign(lp, _priv(f.info["link_key"]),
                lambda doc: doc.__setitem__("coverage_farkas_sha256",
                                            digest))
        prior = _sha(_canon(json.loads(lp.read_text(encoding="utf-8"))))
        _resign(d / "manifest.json", _priv(f.info["key"]),
                lambda doc: doc.__setitem__("prior_digest", prior))
        return key
    return apply


def _leaf(fname):
    def apply(f, d, mutation):
        raw, key = _plant_bytes(json.dumps(LEAF).encode(), mutation)
        _set_leaf(d / fname, raw)
        return key
    return apply


def _dsse(fname, priv_key):
    def apply(f, d, mutation):
        return _dsse_payload(d / fname, f.info[priv_key], mutation)
    return apply


def _ndec_manifest(f, d, mutation):
    p = d / "dossier" / "manifest.json"
    key = _plant_path(p, mutation)
    raw = p.read_bytes()
    man = json.loads(raw)
    canon = ndec.manifest_canonical_sha256(man)

    def edit(payload):
        st = json.loads(payload)
        arts = st["predicate"]["artifacts"]
        arts["manifest_sha256"] = _sha(raw)
        arts["manifest_canonical_sha256"] = canon
        for s in st["subject"]:
            s["digest"]["sha256"] = canon
        return json.dumps(st, sort_keys=True,
                          separators=(",", ":")).encode()
    _dsse_payload(d / "attestation.intoto.json", f.info["ndec_priv"], None,
                  edit=edit)
    return key


def _tb_manifest(f, d, mutation):
    p = d / "trace_bundle" / "manifest.json"
    key = _plant_path(p, mutation)
    digest = _sha(p.read_bytes())
    _resign(d / "manifest.json", f.info["op_priv"],
            lambda doc: doc.__setitem__("trace_bundle_sha256", digest))
    return key


def _tb_hashed(name):
    def apply(f, d, mutation):
        key = _plant_path(d / "trace_bundle" / name, mutation)
        tbm = d / "trace_bundle" / "manifest.json"
        doc = json.loads(tbm.read_text(encoding="utf-8"))
        doc["hashes"][name] = _sha((d / "trace_bundle" / name).read_bytes())
        tbm.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
        digest = _sha(tbm.read_bytes())
        _resign(d / "manifest.json", f.info["op_priv"],
                lambda m: m.__setitem__("trace_bundle_sha256", digest))
        return key
    return apply


def _tb_ndjson(f, d, mutation):
    p = d / "trace_bundle" / "trace.ndjson"
    lines = p.read_text(encoding="utf-8").split("\n")
    key = None
    if mutation is not None:
        lines[0], key = A._plant(lines[0], mutation)
    p.write_text("\n".join(lines), encoding="utf-8")
    return key


def _tb_payload(f, d, mutation):
    files = sorted((d / "trace_bundle" / "payloads").rglob("*"))
    target = [q for q in files if q.is_file()][0]
    return _plant_path(target, mutation)


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _unb64url(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _jws_part(index):
    def apply(f, d, mutation):
        mp = d / "manifest.json"
        doc = json.loads(mp.read_text(encoding="utf-8"))
        parts = doc["attribution"]["authorization_receipt"].split(".")
        raw, key = _plant_bytes(_unb64url(parts[index]), mutation)
        parts[index] = _b64url(raw)
        _resign(mp, f.info["op_priv"],
                lambda m: m["attribution"].__setitem__(
                    "authorization_receipt", ".".join(parts)))
        return key
    return apply


def _mat_file(f, d, mutation):
    names = [q.name for q in d.iterdir() if "materiality" in q.name
             and q.suffix == ".json"]
    assert len(names) == 1, names
    return _rebind_manifest_field(names[0], "materiality_sha256")(
        f, d, mutation)


# (family, label, apply, kind)
INPUTS = [
    ("farkas", "manifest.json", _plain("manifest.json"), "plain"),
    ("farkas", "cost.farkas.json",
     _rebind_manifest_field("cost.farkas.json", "cost_farkas_sha256"),
     "rebind"),
    ("farkas", "coverage.farkas.json",
     _rebind_manifest_field("coverage.farkas.json", "coverage_farkas_sha256"),
     "rebind"),
    ("bundle", "manifest.json", _plain("manifest.json"), "plain"),
    ("bundle", "cost.farkas.json",
     _rebind_manifest_field("cost.farkas.json", "cost_farkas_sha256"),
     "rebind"),
    ("bundle", "coverage.farkas.json",
     _rebind_manifest_field("coverage.farkas.json", "coverage_farkas_sha256"),
     "rebind"),
    ("coverage", "manifest.json", _plain("manifest.json"), "plain"),
    ("coverage", "cost.farkas.json",
     _rebind_manifest_field("cost.farkas.json", "cost_farkas_sha256"),
     "rebind"),
    ("rekor_v1", "manifest.json", _plain("manifest.json"), "plain"),
    ("rekor_v1", "cost.farkas.json",
     _rebind_manifest_field("cost.farkas.json", "cost_farkas_sha256"),
     "rebind"),
    ("rekor_v2_unanchored", "manifest.json", _plain("manifest.json"),
     "plain"),
    ("rekor_v2_leaf", "leaf", _leaf("manifest.json"), "plain"),
    ("chain", "manifest.json", _plain("manifest.json"), "plain"),
    ("chain", "cost.farkas.json",
     _rebind_manifest_field("cost.farkas.json", "cost_farkas_sha256"),
     "rebind"),
    ("chain", "000_manifest.json", _plain("chain/000_manifest.json"),
     "plain"),
    ("chain", "000_coverage.farkas.json",
     _rebind_link_cov("000_manifest.json", "000_coverage.farkas.json"),
     "rebind"),
    ("chain_bundle", "000_hop.farkas.json",
     _plain("chain/000_hop.farkas.json"), "plain"),
    ("chain_net", "000_net.farkas.json",
     _plain("chain/000_net.farkas.json"), "plain"),
    # G-B (JS_G_AMEND_B.txt): the chain texts' other inputs
    ("chain", "coverage.farkas.json",
     _rebind_manifest_field("coverage.farkas.json", "coverage_farkas_sha256"),
     "rebind"),
    ("chain_bundle", "manifest.json", _plain("manifest.json"), "plain"),
    ("chain_bundle", "cost.farkas.json",
     _rebind_manifest_field("cost.farkas.json", "cost_farkas_sha256"),
     "rebind"),
    ("chain_bundle", "coverage.farkas.json",
     _rebind_manifest_field("coverage.farkas.json", "coverage_farkas_sha256"),
     "rebind"),
    ("chain_bundle", "000_manifest.json", _plain("chain/000_manifest.json"),
     "plain"),
    ("chain_bundle", "000_coverage.farkas.json",
     _rebind_link_cov("000_manifest.json", "000_coverage.farkas.json"),
     "rebind"),
    ("chain_net", "manifest.json", _plain("manifest.json"), "plain"),
    ("chain_net", "cost.farkas.json",
     _rebind_manifest_field("cost.farkas.json", "cost_farkas_sha256"),
     "rebind"),
    ("chain_net", "000_manifest.json", _plain("chain/000_manifest.json"),
     "plain"),
    ("gapw", "manifest.json", _plain("manifest.json"), "plain"),
    ("gapw", "coverage.gapwitness.json",
     _rebind_manifest_field("coverage.gapwitness.json",
                            "gap_witness_sha256"), "rebind"),
    ("conf_leaf", "leaf", _leaf("conformance.json"), "plain"),
    ("vsa", "payload", _dsse("vsa.intoto.json", "vsa_priv"), "rebind"),
    ("vsa_registry", "verifier-registry.json",
     _plain("verifier-registry.json"), "plain"),
    ("ndec", "payload", _dsse("attestation.intoto.json", "ndec_priv"),
     "rebind"),
    ("ndec", "manifest.json", _ndec_manifest, "rebind"),
    ("materiality", "materiality", _mat_file, "rebind"),
    ("pce", "pce.json",
     _rebind_manifest_field("pce.json", "pce_sha256"), "rebind"),
    ("trace_bundle", "trace_bundle/manifest.json", _tb_manifest, "rebind"),
    ("trace_bundle", "keys.json", _tb_hashed("keys.json"), "rebind"),
    ("trace_bundle", "obligations.json", _tb_hashed("obligations.json"),
     "rebind"),
    ("trace_bundle", "trace.ndjson", _tb_ndjson, "plain"),
    ("trace_bundle", "payloads", _tb_payload, "plain"),
    ("attribution", "header", _jws_part(0), "rebind"),
    ("attribution", "payload", _jws_part(1), "rebind"),
]
IDS = ["%s:%s" % (fam, label) for fam, label, _a, _k in INPUTS]


def _case_dir(fams, tmp_path, fam):
    f = fams(fam)
    d = tmp_path / "case"
    shutil.copytree(f.d, d)
    return f, d


@pytest.mark.parametrize("fam", sorted(BUILDERS))
def test_b_family_baseline(fams, tmp_path, fam):
    f, d = _case_dir(fams, tmp_path, fam)
    rc, so, se = f.run(d)
    assert rc == f.baseline, (fam, rc, so[-600:], se[-600:])


REBINDS = [(fam, label, apply) for fam, label, apply, kind in INPUTS
           if kind == "rebind"]


@pytest.mark.parametrize("fam,label,apply", REBINDS,
                         ids=["%s:%s" % (a, b) for a, b, _c in REBINDS])
def test_b_rebind_identity(fams, tmp_path, fam, label, apply):
    f, d = _case_dir(fams, tmp_path, fam)
    assert apply(f, d, None) is None
    rc, so, se = f.run(d)
    assert rc == f.baseline, (fam, label, rc, so[-600:], se[-600:])


@pytest.mark.parametrize("mutation", MUTATIONS)
@pytest.mark.parametrize("fam,label,apply,kind", INPUTS, ids=IDS)
def test_b_strict(fams, tmp_path, fam, label, apply, kind, mutation):
    f, d = _case_dir(fams, tmp_path, fam)
    key = apply(f, d, mutation)
    rc, so, se = f.run(d)
    A._assert_refused(rc, so, se, label, mutation, key)


# --------------------------------------------- VSA farkas, planted early


def _vsa_mint_hooked(tmp_path: Path, name: str, hook):
    hv = v3c._harness()
    import pricing as pm
    import smt_emit as sm
    saved = (pm.datetime, sm.datetime)
    pm.datetime = hv._PinnedPriceClock
    sm.datetime = hv._PinnedPriceClock
    try:
        run_root = tmp_path / name
        work = run_root / "work"
        work.mkdir(parents=True)
        source_path = v3c.V2DIR / "vsa_conformance_vector_v2.nous"
        source_text = source_path.read_text(encoding="utf-8")
        mkey = work / "_manifest.key"
        hv._write_pkcs8_pem(hv._SEED_MANIFEST, mkey)
        assert hv.cli_verify.cmd_verify(
            hv._verify_args(source_path, work, mkey)) == 0
        manifest_path = work / "manifest.json"
        hv._repin_manifest(manifest_path)
        key = hook(hv, work, manifest_path)
        program = hv.parse_nous(source_text)
        table = hv.load_pricing(hv._SHIPPED_PRICES)
        spec = hv.emit_smt(program, table, source_text=source_text,
                           today=hv._PINNED_PRICE_DAY)
        codegen = hv.compute_codegen_sha256(source_text)
        rec = hv.TraceRecorder(
            nous_version="vector", world_name=spec.world_name,
            source_sha256=spec.source_sha256,
            smt_spec_sha256=spec.sha256(),
            pricing_sha256=spec.pricing_sha256, codegen_sha256=codegen,
            clock=hv._fixed_clock)
        rec.record_llm_call(hv._SOUL, 0, 100, hv._OUT_TOK)
        trace = rec.finalize(hv._fixed_key(hv._SEED_TRACE))
        manifest, _b, _p = hv.parse_manifest_json(
            manifest_path.read_text(encoding="utf-8"))
        detail = hv.verify_conformance(trace, manifest, spec, table,
                                       codegen_sha256=codegen)
        cert = hv.sign_certificate(
            hv.build_certificate(
                detail, trace, manifest, nous_version="vector",
                issued_utc=hv._PINNED_ISSUED,
                obligations_canon=hv.obligations_canon_for(manifest, spec)),
            hv._fixed_key(hv._SEED_CERT))
        (work / "trace.json").write_text(
            json.dumps(trace.persisted_dict(), sort_keys=True),
            encoding="utf-8")
        (work / "conformance.json").write_text(
            hv.certificate_json(cert), encoding="utf-8")
        vkey = work / "_vsa.key"
        vkey.write_bytes(hv._SEED_VSA)
        bundle = run_root / "bundle"
        assert hv.cli_vsa.cmd_vsa(argparse.Namespace(
            command="vsa", vsa_command="emit",
            trace=str(work / "trace.json"), manifest=str(manifest_path),
            cert=str(work / "conformance.json"),
            coverage=str(work / "coverage.farkas.json"),
            cost=str(work / "cost.farkas.json"), out=str(bundle),
            key_path=str(vkey), no_inline_pin=False)) == 0
    finally:
        pm.datetime, sm.datetime = saved
    return bundle, v3c._b64_pub(hv._fixed_key(hv._SEED_VSA)), key


def _farkas_hook(fname, field, mutation):
    def hook(hv, work, mpath):
        key = _plant_path(work / fname, mutation)
        body = (work / fname).read_bytes()
        m, _b, _p = hv.parse_manifest_json(mpath.read_text(encoding="utf-8"))
        m2 = dataclasses.replace(m, **{field: _sha(body)})
        priv = hv._fixed_key(hv._SEED_MANIFEST)
        mpath.write_text(hv.manifest_json(m2, hv.sign_manifest(m2, priv),
                                          priv.public_key()),
                         encoding="utf-8")
        return key
    return hook


# cost.farkas.json is planted after the mint (G-A, JS_G_AMEND.txt
# 0c4f8cbf): cli_vsa emit re-derives the cost system from the planted
# certificate and refuses a changed value, so no bundle would exist.
VSA_FARKAS = (("coverage.farkas.json", "coverage_farkas_sha256"),)


@pytest.mark.parametrize("fname,field", VSA_FARKAS)
def test_b_vsa_farkas_identity(tmp_path, fname, field):
    b, pin, key = _vsa_mint_hooked(tmp_path, "id",
                                   _farkas_hook(fname, field, None))
    assert key is None
    rc, so, se = v3c._run(b, "verify_vsa_offline.py",
                          ["--expect-signer", pin])
    assert rc == 0, (rc, so[-600:], se[-600:])


@pytest.mark.parametrize("mutation", MUTATIONS)
@pytest.mark.parametrize("fname,field", VSA_FARKAS)
def test_b_vsa_farkas(tmp_path, fname, field, mutation):
    b, pin, key = _vsa_mint_hooked(tmp_path, "m",
                                   _farkas_hook(fname, field, mutation))
    rc, so, se = v3c._run(b, "verify_vsa_offline.py",
                          ["--expect-signer", pin])
    A._assert_refused(rc, so, se, fname, mutation, key)


# ------------------------------------- VSA cost.farkas.json, planted late


def _vsa_cost_post(b: Path, mutation):
    hv = v3c._harness()
    cost = b / "cost.farkas.json"
    old_cost = _sha(cost.read_bytes())
    key = _plant_path(cost, mutation)
    new_cost = _sha(cost.read_bytes())
    mp = b / "manifest.json"
    old_man = _sha(_canon(json.loads(mp.read_text(encoding="utf-8"))))
    _resign(mp, hv._fixed_key(hv._SEED_MANIFEST),
            lambda doc: doc.__setitem__("cost_farkas_sha256", new_cost))
    new_man = _sha(_canon(json.loads(mp.read_text(encoding="utf-8"))))

    def edit(payload):
        st = json.loads(payload)
        for ia in st["predicate"]["inputAttestations"]:
            if ia["uri"] == "cost.farkas.json":
                ia["digest"]["sha256"] = new_cost
            if ia["uri"] == "manifest.json":
                ia["digest"]["sha256"] = new_man
        text = json.dumps(st, sort_keys=True, separators=(",", ":"))
        text = text.replace(old_cost, new_cost).replace(old_man, new_man)
        return text.encode("utf-8")
    _dsse_payload(b / "vsa.intoto.json", hv._fixed_key(hv._SEED_VSA), None,
                  edit=edit)
    return key


def _vsa_identity_mint(tmp_path):
    return _vsa_mint_hooked(
        tmp_path, "c", _farkas_hook("cost.farkas.json", "cost_farkas_sha256",
                                    None))


def test_b_vsa_cost_post_identity(tmp_path):
    b, pin, _k = _vsa_identity_mint(tmp_path)
    assert _vsa_cost_post(b, None) is None
    rc, so, se = v3c._run(b, "verify_vsa_offline.py",
                          ["--expect-signer", pin])
    assert rc == 0, (rc, so[-600:], se[-600:])


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_b_vsa_cost_post(tmp_path, mutation):
    b, pin, _k = _vsa_identity_mint(tmp_path)
    key = _vsa_cost_post(b, mutation)
    rc, so, se = v3c._run(b, "verify_vsa_offline.py",
                          ["--expect-signer", pin])
    A._assert_refused(rc, so, se, "cost.farkas.json", mutation, key)
