"""AN-GATE-1 D4/D5 (D432-12): strict JSON, phase C (K-JS.1, K-JS.5).

Predictions: JS_C_PREDICTIONS.txt 795f6b96..., amended by
JS_C_AMEND.txt d8f1625f... The seven texts outside V3 (build VSA,
provenance, continuity, Annex IV, three adapters) refuse a duplicate
member name or a non-finite token as FAIL: rc 1, no CLASS line. The
installed CLI paths refuse it with a non-zero exit. Every key a test
uses is made under tmp_path.

# __an_js_strict_c_tests_v1__
"""
from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey)

import manifest as mf
import test_an_js_strict as A
import test_an_js_strict_b as B

REPO = Path(__file__).resolve().parent.parent
MUTATIONS = A.MUTATIONS
CLI_BOOT = ("import sys; from cli import main; "
            "sys.argv=['nous']+sys.argv[1:]; sys.exit(main())")
REL = REPO / "website" / ".well-known" / "nous" / "release-vsa" / "5.60.1"
FIX = REPO / "tests" / "fixtures" / "rekor_v2"


# ------------------------------------------------------------- running


def _proc(args, cwd=None):
    p = subprocess.run(args, cwd=None if cwd is None else str(cwd),
                       capture_output=True, text=True, timeout=300)
    return p.returncode, p.stdout, p.stderr


def _script(path: Path, args=(), cwd=None):
    return _proc([sys.executable, "-I", "-B", str(path)] + list(args), cwd)


def _cli(args, cwd=None):
    return _proc([sys.executable, "-I", "-c", CLI_BOOT]
                 + [str(a) for a in args], cwd)


def _last_err(se: str) -> str:
    lines = [ln for ln in se.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def _named(last, label, mutation, key):
    assert label in last, (A.RAN, label, mutation, last)
    if mutation.startswith("dup_"):
        assert "refused: duplicate key " + repr(key) in last, (
            A.RAN, label, mutation, last)
    else:
        assert A.TOKENS[mutation] in last, (A.RAN, label, mutation, last)
        assert A.NONFINITE_PHRASE in last, (A.RAN, label, mutation, last)
    A.HITS.update(A.TAG.findall(last))


def _refused_seven(res, label, mutation, key):
    rc, so, se = res
    assert rc == 1, (A.RAN, label, mutation, rc, so[-400:], se[-400:])
    assert not [ln for ln in so.splitlines() if ln.startswith("CLASS:")], (
        A.RAN, label, mutation, so[-400:])
    _named(_last_err(se), label, mutation, key)


def _refused_cli(res, label, mutation, key):
    rc, so, se = res
    assert rc != 0, (A.RAN, label, mutation, rc, so[-400:], se[-400:])
    _named(_last_err(se), label, mutation, key)


def _refused_ndec(res, label, mutation, key):
    rc, so, se = res
    assert rc == 1, (A.RAN, label, mutation, rc, so[-400:], se[-400:])
    _named(_last_err(se), label, mutation, key)


def _refused_conv(res, label, mutation, key):
    # (kind, text): ("raise", message) or ("result", root 1 status+detail)
    kind, status, text = res
    if kind == "result":
        assert status == "FAIL", (A.RAN, label, mutation, status, text)
    _named(text, label, mutation, key)


CHECKS = {"seven": _refused_seven, "cli": _refused_cli,
          "ndec": _refused_ndec, "conv": _refused_conv}


# ------------------------------------------------------------ families


Fam = B.Fam


def _b_build_vsa(root):
    import build_vsa as bv
    import test_build_vsa as t
    seed = Ed25519PrivateKey.generate().private_bytes_raw()
    priv = Ed25519PrivateKey.from_private_bytes(seed)
    d = root / "bvsa"
    d.mkdir()
    env = bv.sign_build_vsa(t._valid_statement(), seed)
    (d / "build-vsa.intoto.json").write_text(json.dumps(env),
                                             encoding="utf-8")
    (d / t.WHL_NAME).write_bytes(t.WHL)
    (d / t.SD_NAME).write_bytes(t.SD)
    bv.emit_build_vsa_verifier(str(d), B._pin_of(priv))
    return Fam(d, lambda x: _script(x / "verify_build_vsa_offline.py",
                                    [x]), 0, priv=priv)


def _b_provenance(root):
    import provenance_verifier as pv
    import test_s160_u2_provenance_verifier as t
    priv = Ed25519PrivateKey.generate()
    d = root / "prov"
    d.mkdir()
    wheel = b"WHEELBYTES\n" * 64
    sdist = b"SDISTBYTES\n" * 96
    (d / t.WHEEL).write_bytes(wheel)
    (d / t.SDIST).write_bytes(sdist)
    (d / t.ENV_NAME).write_bytes(t._make_env(priv, B._sha(wheel),
                                             B._sha(sdist)))
    (d / "verify_provenance_offline.py").write_text(
        pv.emit_provenance_verifier(t._pub_b64(priv)), encoding="utf-8")
    return Fam(d, lambda x: _script(x / "verify_provenance_offline.py"),
               0, priv=priv)


def _cont_args(root):
    import test_s178_checkpoint_leg as t
    return ["--key", root / "cp_pub.pem", "--iss", t._ISS, "--aud", t._AUD]


def _b_continuity(root):
    import test_s178_checkpoint_leg as t
    op, cp = t._keys(root)
    ledger = t._build_priced_ledger(root, op, cp, ["0.10", "0.20"])
    logkey = root / "logkey"
    assert t._run(["continuity", "checkpoint", "--ledger", str(ledger),
                   "--log-key", str(logkey), "--budget", "1.00"]) == 0
    log_pub = t._log_pub_pem(root, logkey)
    vdir = root / "verifier"
    vdir.mkdir()
    script = t._emit(vdir)
    args = _cont_args(root) + ["--log-key", log_pub]
    return Fam(ledger, lambda x: _script(script, [x] + args), 0,
               logkey=logkey)


def _b_continuity_prior(root):
    import test_s183_patch2_verifier as t
    from continuity_checkpoint import build_continuity_proof
    ledger = t._ledger9(root)
    prior_dir = t._prefix_dir(root, ledger, 5, "prior5")
    prior = t._rail_checkpoint(root, prior_dir, "p5")
    build_continuity_proof(ledger, prior, ledger / "continuity.proof")
    script = t._emit(root)
    return Fam(ledger, lambda x: _script(
        script, [x, "--prior-checkpoint", prior]), 0)


def _b_annex(root):
    import test_annex_iv_verifier as t
    d = root / "annex"
    d.mkdir()
    t._make_dossier_with_map(d)
    return Fam(d, lambda x: _script(x / "verify_annex_iv_map.py", cwd=x), 0)


def _adapter(name):
    if name == "ga":
        import guardrails_adapter as mod
        import test_guardrails_adapter as t
        rec = t._FIXTURE_FAIL
        pre = (lambda: mod._canonical_bytes(mod.project_guardrails(rec)))
        emit = (lambda key, out, anchor: mod.emit_dossier_to_dir(
            rec, key, t._TS, t._VER, out, rekor_anchor=anchor))
        anchor = t._synthetic_anchor
    elif name == "lg":
        import llm_guard_adapter as mod
        import test_llm_guard_adapter as t
        rec = t._FIXTURE_BLOCK
        pre = (lambda: mod._canonical_bytes(mod.project_llmguard(rec)))
        emit = (lambda key, out, anchor: mod.emit_dossier_to_dir(
            rec, key, t._TS, t._VER, out, rekor_anchor=anchor))
        anchor = t._synthetic_anchor
    else:
        import santander_adapter as mod
        import test_santander_adapter as t
        rec = t._FIXTURE_R2
        pre = (lambda: rec["entropy_nonce"])
        emit = (lambda key, out, anchor: mod.emit_dossier_to_dir(
            rec, t._line(rec), key, t._TS, t._VER, out,
            rekor_anchor=anchor))
        anchor = t._s216_synthetic_anchor
    return mod, emit, pre, anchor


def _b_adapter(name, leaf):
    def build(root):
        mod, emit, pre, anchor = _adapter(name)
        key = Ed25519PrivateKey.generate()
        d = root / (name + ("_leaf" if leaf else ""))
        d.mkdir()
        info = {}
        block = None
        if leaf:
            log_priv = Ed25519PrivateKey.generate()
            block, _trusted = anchor(pre(), log_priv)
            info["log_priv"] = log_priv
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv(mod._OPT_IN_ENV, "1")
            emit(key, d, block)
        return Fam(d, lambda x: _script(x / "verify_offline.py", cwd=x),
                   1 if leaf else 0, **info)
    return build


def _b_ndec_cli(root):
    f = B._b_ndec(root)
    pin = B._pin_of(f.info["ndec_priv"])
    order = zipfile.ZipFile(next(root.glob("*.ndec"))).namelist()

    def run(x):
        out = x.parent / (x.name + ".ndec")
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for n in order:
                z.write(x / n, n)
        return _cli(["ndec", "verify", out, "--expect-signer", pin])
    return Fam(f.d, run, 0, ndec_priv=f.info["ndec_priv"])


def _b_conf_cli(root):
    import test_nt_v3_classes as v3c
    v3c._conf_bundle(A._pricing_table(), root, v3c.GENUINE(), name="conf")
    d = root / "conf_mat"
    return Fam(d, lambda x: _cli(
        ["conformance", "verify", "trace.json", "--manifest",
         "manifest.json", "--prices", "pricing.toml", "--source",
         "source.nous"], cwd=x), 0)


def _b_cont_cli(root):
    import test_s178_checkpoint_leg as t
    op, cp = t._keys(root)
    ledger = t._build_priced_ledger(root, op, cp, ["0.10", "0.20"])
    args = _cont_args(root)
    return Fam(ledger, lambda x: _cli(
        ["continuity", "verify", "--ledger", x] + args), 0)


def _assemble(d: Path) -> Path:
    d.mkdir()
    shutil.copy(REL / "nous_lang-5.60.1.build-vsa.intoto.json",
                d / "build-vsa.intoto.json")
    shutil.copy(REL / "nous_lang-5.60.1.rekor-v2-bundle.json",
                d / "rekor-v2-bundle.json")
    shutil.copy(FIX / "trusted_root.json", d / "trusted_root.json")
    shutil.copy(FIX / "tsa_chain.pem", d / "tsa_chain.pem")
    return d


def _b_bav_cli(root):
    d = _assemble(root / "bav")
    return Fam(d, lambda x: _cli(["build-attest-verify", "--bundle-dir", x]),
               0)


def _b_conv(root):
    from cli_verify_release import ConvergenceInputError, verify_convergence
    from conformance_verifier import StrictJsonError
    d = _assemble(root / "conv")
    priv = Ed25519PrivateKey.generate()
    pin = B._pin_of(priv)
    B._dsse_payload(d / "build-vsa.intoto.json", priv, None)

    def run(x):
        try:
            r = verify_convergence(x, pinned_pubkey_b64=pin)
        except (ConvergenceInputError, StrictJsonError) as exc:
            return ("raise", None, str(exc))
        leg = r["legs"]["root1_operator_ed25519"]
        return ("result", leg["status"], str(leg["detail"]))
    return Fam(d, run, "PASS", priv=priv)


def _b_cost_cli(root):
    import test_trace_bundle_dossier_e2e as t
    w = root / "cost"
    w.mkdir()
    src, man = t._signed_source(w)
    assert (w / "cost.farkas.json").is_file()
    return Fam(w, lambda x: _cli(
        ["verify-cost", x / "cost.farkas.json", "--manifest",
         x / man.name]), 0, manifest=man.name)


BUILDERS = {
    "build_vsa": _b_build_vsa, "provenance": _b_provenance,
    "continuity": _b_continuity, "continuity_prior": _b_continuity_prior,
    "annex_iv": _b_annex,
    "guardrails": _b_adapter("ga", False),
    "guardrails_leaf": _b_adapter("ga", True),
    "llm_guard": _b_adapter("lg", False),
    "llm_guard_leaf": _b_adapter("lg", True),
    "santander": _b_adapter("sa", False),
    "santander_leaf": _b_adapter("sa", True),
    "ndec_cli": _b_ndec_cli, "conformance_cli": _b_conf_cli,
    "continuity_cli": _b_cont_cli, "bav_cli": _b_bav_cli,
    "convergence": _b_conv, "verify_cost_cli": _b_cost_cli,
}


@pytest.fixture(scope="module")
def fams(tmp_path_factory):
    import dated_prices
    cache: dict = {}
    root = tmp_path_factory.mktemp("an_js_c")
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
        return B._plant_path(d / fname, mutation)
    return apply


def _dsse(fname):
    def apply(f, d, mutation):
        return B._dsse_payload(d / fname, f.info["priv"], mutation)
    return apply


def _ndec_dsse(f, d, mutation):
    return B._dsse_payload(d / "attestation.intoto.json",
                           f.info["ndec_priv"], mutation)


def _receipt_part(part):
    def apply(f, d, mutation):
        p = d / "000" / "receipt.jws"
        doc = json.loads(p.read_text(encoding="utf-8"))
        raw, key = B._plant_bytes(B._unb64url(doc[part]), mutation)
        doc[part] = B._b64url(raw)
        p.write_text(json.dumps(doc), encoding="utf-8")
        return key
    return apply


def _tree_digest(d):  # __s7b_b3_sidecar_writer_v1__
    return sorted(
        (str(p.relative_to(d)), oct(p.lstat().st_mode),
         hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "")
        for p in d.rglob("*"))


def _writer_refused(msg, mutation, key):  # __s7b_b3_sidecar_writer_v1__
    # The reason _named asks of the reader, asked of the writer's guard.
    assert "[js:w.ckp.2]" in msg, (mutation, msg)
    if mutation.startswith("dup_"):
        assert "refused: duplicate key " + repr(key) in msg, (mutation, msg)
    else:
        assert A.TOKENS[mutation] in msg, (mutation, msg)
        assert A.NONFINITE_PHRASE in msg, (mutation, msg)


def _sidecar(f, d, mutation):
    # __s7b_b3_sidecar_writer_v1__ (S7B_B3_AMENDMENT_2). For a mutation:
    # W1 the real writer refuses the planted sidecar by its S7b guard
    # [js:w.ckp.2], with the reason the reader gives, and leaves the case
    # dir as it was; W2 a writer without that one guard (any NOUS before
    # S7b) writes the same bytes, and the reader (cnt.5) is checked as
    # before. The bypass lives only in this MonkeyPatch context.
    import continuity_checkpoint as cc
    from conformance_verifier import StrictJsonError
    real = cc._canonical_bytes
    seen = {}

    def planted(obj):
        b = real(obj)
        if isinstance(obj, dict) and (
                obj.get("fragment") == cc.BUDGET_EXTENSION_TAG):
            if "raw" not in seen:
                seen["raw"], seen["key"] = B._plant_bytes(b, mutation)
            return seen["raw"]
        return b
    for n in ("checkpoint.note", "aggregate.cost.farkas.json"):
        (d / n).unlink()
    hits = []
    if mutation is not None:
        before = _tree_digest(d)
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(cc, "_canonical_bytes", planted)
            with pytest.raises(StrictJsonError) as ei:
                cc.build_continuity_checkpoint(
                    d, log_key_path=f.info["logkey"], budget="1.00")
        _writer_refused(str(ei.value), mutation, seen["key"])
        assert _tree_digest(d) == before, "the refused writer wrote"
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(cc, "_canonical_bytes", planted)
        if mutation is not None:
            guard = cc._s7b_loads

            def unguarded(raw, label):
                if "[js:w.ckp.2]" in label:
                    hits.append(label)
                    return None
                return guard(raw, label)
            mp.setattr(cc, "_s7b_loads", unguarded)
        cc.build_continuity_checkpoint(d, log_key_path=f.info["logkey"],
                                       budget="1.00")
    assert len(hits) == (0 if mutation is None else 1), hits
    assert (d / "aggregate.cost.farkas.json").read_bytes() == seen["raw"]
    return seen["key"]


def _reanchor(f, d, mutation):
    from rekor_checkpoint import ed25519_key_id
    p = d / "manifest.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    block = doc["transparency_log"]
    body, key = B._plant_bytes(base64.b64decode(block["body_b64"]),
                               mutation)
    origin = block["checkpoint_envelope"].split("\n", 1)[0]
    root_hash = hashlib.sha256(b"\x00" + body).digest()
    note = (origin + "\n1\n" + base64.b64encode(root_hash).decode()
            + "\n")
    lp = f.info["log_priv"]
    blob = ed25519_key_id(origin, lp.public_key()) + lp.sign(note.encode())
    block["body_b64"] = base64.b64encode(body).decode()
    block["checkpoint_envelope"] = (note + "\n\u2014 " + origin + " "
                                    + base64.b64encode(blob).decode()
                                    + "\n")
    p.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n",
                 encoding="utf-8")
    return key


def _ndec_manifest(f, d, mutation):
    return B._ndec_manifest(f, d, mutation)


def _cost_manifest(f, d, mutation):
    return B._plant_path(d / f.info["manifest"], mutation)


# (family, label, apply, kind, check)
INPUTS = [
    ("build_vsa", "build-vsa.intoto.json",
     _plain("build-vsa.intoto.json"), "plain", "seven"),
    ("build_vsa", "payload", _dsse("build-vsa.intoto.json"), "rebind",
     "seven"),
    ("provenance", "nous_lang-5.58.0.provenance.intoto.json",
     _plain("nous_lang-5.58.0.provenance.intoto.json"), "plain", "seven"),
    ("provenance", "payload",
     _dsse("nous_lang-5.58.0.provenance.intoto.json"), "rebind", "seven"),
    ("continuity", "link.json", _plain("000/link.json"), "plain", "seven"),
    ("continuity", "manifest.json", _plain("000/manifest.json"), "plain",
     "seven"),
    ("continuity", "conformance.json", _plain("000/conformance.json"),
     "plain", "seven"),
    ("continuity", "trace.json", _plain("000/trace.json"), "plain",
     "seven"),
    ("continuity", "receipt.jws", _plain("000/receipt.jws"), "plain",
     "seven"),
    ("continuity", "protected", _receipt_part("protected"), "rebind",
     "seven"),
    ("continuity", "payload", _receipt_part("payload"), "rebind", "seven"),
    ("continuity", "aggregate.cost.farkas.json", _sidecar, "rebind",
     "seven"),
    ("continuity_prior", "continuity.proof", _plain("continuity.proof"),
     "plain", "seven"),
    ("annex_iv", "annex_iv_map.json", _plain("annex_iv_map.json"), "plain",
     "seven"),
    ("annex_iv", "manifest.json", _plain("manifest.json"), "plain",
     "seven"),
    ("guardrails", "manifest.json", _plain("manifest.json"), "plain",
     "seven"),
    ("guardrails", "payload.json", _plain("payload.json"), "plain",
     "seven"),
    ("guardrails_leaf", "leaf", _reanchor, "rebind", "seven"),
    ("llm_guard", "manifest.json", _plain("manifest.json"), "plain",
     "seven"),
    ("llm_guard", "payload.json", _plain("payload.json"), "plain",
     "seven"),
    ("llm_guard_leaf", "leaf", _reanchor, "rebind", "seven"),
    ("santander", "manifest.json", _plain("manifest.json"), "plain",
     "seven"),
    ("santander", "payload.json", _plain("payload.json"), "plain",
     "seven"),
    ("santander_leaf", "leaf", _reanchor, "rebind", "seven"),
    ("ndec_cli", "attestation.intoto.json",
     _plain("attestation.intoto.json"), "plain", "ndec"),
    ("ndec_cli", "payload", _ndec_dsse, "rebind", "ndec"),
    ("ndec_cli", "manifest.json", _ndec_manifest, "rebind", "ndec"),
    ("conformance_cli", "manifest.json", _plain("manifest.json"), "plain",
     "cli"),
    ("conformance_cli", "trace.json", _plain("trace.json"), "plain",
     "cli"),
    ("continuity_cli", "link.json", _plain("000/link.json"), "plain",
     "cli"),
    ("continuity_cli", "receipt.jws", _plain("000/receipt.jws"), "plain",
     "cli"),
    ("bav_cli", "build-vsa.intoto.json", _plain("build-vsa.intoto.json"),
     "plain", "cli"),
    ("bav_cli", "rekor-v2-bundle.json", _plain("rekor-v2-bundle.json"),
     "plain", "cli"),
    ("bav_cli", "trusted_root.json", _plain("trusted_root.json"), "plain",
     "cli"),
    ("convergence", "payload", _dsse("build-vsa.intoto.json"), "rebind",
     "conv"),
    ("verify_cost_cli", "cost.farkas.json", _plain("cost.farkas.json"),
     "plain", "cli"),
    ("verify_cost_cli", "manifest.json", _cost_manifest, "plain", "cli"),
]
IDS = ["%s:%s" % (fam, label) for fam, label, _a, _k, _c in INPUTS]


def _case_dir(fams, tmp_path, fam):
    f = fams(fam)
    d = tmp_path / "case"
    shutil.copytree(f.d, d)
    return f, d


def _baseline_of(res):
    return res[1] if isinstance(res[0], str) else res[0]


@pytest.mark.parametrize("fam", sorted(BUILDERS))
def test_c_family_baseline(fams, tmp_path, fam):
    f, d = _case_dir(fams, tmp_path, fam)
    res = f.run(d)
    assert _baseline_of(res) == f.baseline, (fam, str(res)[-900:])


REBINDS = [(fam, label, apply) for fam, label, apply, kind, _c in INPUTS
           if kind == "rebind"]


@pytest.mark.parametrize("fam,label,apply", REBINDS,
                         ids=["%s:%s" % (a, b) for a, b, _c in REBINDS])
def test_c_rebind_identity(fams, tmp_path, fam, label, apply):
    f, d = _case_dir(fams, tmp_path, fam)
    assert apply(f, d, None) is None
    res = f.run(d)
    assert _baseline_of(res) == f.baseline, (fam, label, str(res)[-900:])


@pytest.mark.parametrize("mutation", MUTATIONS)
@pytest.mark.parametrize("fam,label,apply,kind,check", INPUTS, ids=IDS)
def test_c_strict(fams, tmp_path, fam, label, apply, kind, check,
                  mutation):
    f, d = _case_dir(fams, tmp_path, fam)
    key = apply(f, d, mutation)
    CHECKS[check](f.run(d), label, mutation, key)
