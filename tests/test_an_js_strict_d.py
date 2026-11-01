"""AN-GATE-1 D4, round 2 (RULING 10:44Z, Q2; R2_AMEND_A.txt f5d98868).

The JSON inputs the first review found outside the strict region: four
dossier splices (in a harness text that carries the region, the splice
and a main that calls it), the trace bundle's Rekor leg, nous ndec
verify without --expect-signer, build-attest-verify's
canonicalized_body through the CLI, the continuity text with --json,
and conformance verify with --apr. Every key is made under tmp_path.

# __an_js_strict_d_tests_v1__
"""
from __future__ import annotations

import base64
import json
import re
import shutil
import zipfile
from pathlib import Path

import pytest

import manifest as mf
import test_an_js_strict as A
import test_an_js_strict_b as B
import test_an_js_strict_c as C

REPO = Path(__file__).resolve().parent.parent
MUTATIONS = A.MUTATIONS
Fam = B.Fam

HARNESS_MAIN = '''

import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])


def main():
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    return CHECK(manifest, ROOT)


if __name__ == "__main__":
    try:
        _rc = main()
    except Exception as _exc:
        if not getattr(_exc, "an_js_refusal", False):
            raise
        print("FAIL: " + str(_exc), file=sys.stderr)
        _rc = 1
    sys.exit(_rc)
'''


def _canonical_region() -> str:
    src = (REPO / "conformance_verifier.py").read_text(encoding="utf-8")
    m = re.search(r"(?ms)^" + re.escape(A.REGION_START) + r"$.*?^"
                  + re.escape(A.REGION_END) + r"$", src)
    return m.group(0) if m else ""


# ------------------------------------------------------------ harness


def _doc_envelope():
    import test_s194_envelope_witness_dossier as t
    return t._witness_doc()


def _doc_closure():
    return {"closure_witness_schema_version": 1, "policy_id": "p",
            "interval": {"start": "2026-07-01T00:00:00Z"}}


def _doc_pce_anchor():
    import test_s191_pce_anchor_dossier as t
    return t._anchor_doc("0" * 64)


def _doc_tb_anchor():
    return {"anchor_schema_version": 1, "anchored_bundle_sha256": "0" * 64,
            "receipt": {"kind": "rfc3161"}}


SPLICES = {
    "envelope_witness": ("_ENVELOPE_WITNESS_CHECK_EMBED",
                         "_check_envelope_witness", "envelope.witness.json",
                         "envelope_witness_sha256", _doc_envelope),
    "closure_witness": ("_CLOSURE_WITNESS_CHECK_EMBED",
                        "_check_closure_witness", "closure.witness.json",
                        "closure_witness_sha256", _doc_closure),
    "pce_anchor": ("_PCE_ANCHOR_CHECK_EMBED", "_check_pce_anchor",
                   "pce.anchor.json", "pce_anchor_sha256", _doc_pce_anchor),
    "trace_bundle_anchor": ("_TRACE_BUNDLE_ANCHOR_CHECK_EMBED",
                            "_check_trace_bundle_anchor",
                            "trace_bundle.anchor.json",
                            "trace_bundle_anchor_sha256", _doc_tb_anchor),
}


def _bind(d: Path, fname: str, field: str) -> None:
    man = {field: B._sha((d / fname).read_bytes())}
    (d / "manifest.json").write_text(json.dumps(man), encoding="utf-8")


def _b_splice(name):
    def build(root):
        import dossier
        const, fn, fname, field, doc = SPLICES[name]
        d = root / name
        d.mkdir()
        text = ("#!/usr/bin/env python3\n" + _canonical_region() + "\n\n\n"
                + getattr(dossier, const) + HARNESS_MAIN.replace("CHECK",
                                                                 fn))
        (d / "harness.py").write_text(text, encoding="utf-8")
        (d / fname).write_text(json.dumps(doc(), sort_keys=True),
                               encoding="utf-8")
        (d / "trace_bundle").mkdir()
        (d / "trace_bundle" / "manifest.json").write_text("{}",
                                                         encoding="utf-8")
        _bind(d, fname, field)
        return Fam(d, lambda x: C._script(x / "harness.py", [x], cwd=x),
                   None, fname=fname, field=field)
    return build


def _splice_apply(f, d, mutation):
    key = B._plant_path(d / f.info["fname"], mutation)
    _bind(d, f.info["fname"], f.info["field"])
    return key


# ------------------------------------------------------------ CLI paths


def _b_ndec_nopin(root):
    f = C._b_ndec_cli(root)
    order = zipfile.ZipFile(next(root.glob("*.ndec"))).namelist()

    def run(x):
        out = x.parent / (x.name + ".ndec")
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for n in order:
                z.write(x / n, n)
        return C._cli(["ndec", "verify", out])
    # baseline 2: without --expect-signer no PASS (8.0.0, NT-GATE-1 V3)
    return Fam(f.d, run, 2, ndec_priv=f.info["ndec_priv"])


def _bav_body(f, d, mutation):
    p = d / "rekor-v2-bundle.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    tle = doc["transparency_log_entry"]
    raw, key = B._plant_bytes(base64.b64decode(tle["canonicalized_body"]),
                              mutation)
    tle["canonicalized_body"] = base64.b64encode(raw).decode("ascii")
    p.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return key


def _b_cont_json(root):
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
    args = C._cont_args(root) + ["--log-key", log_pub, "--json"]
    return Fam(ledger, lambda x: C._script(script, [x] + args), 0)


def _b_conf_apr(root):
    import test_s145_attestation_receipt as t
    f = C._b_conf_cli(root)
    rk, ek = t._make_keys()
    (f.d / "apr.json").write_text(t._make_apr(rk, ek).model_dump_json(),
                                  encoding="utf-8")
    return Fam(f.d, lambda x: C._cli(
        ["conformance", "verify", "trace.json", "--manifest",
         "manifest.json", "--prices", "pricing.toml", "--source",
         "source.nous", "--apr", "apr.json"], cwd=x), 0)


BUILDERS = {name: _b_splice(name) for name in SPLICES}
BUILDERS.update({"ndec_nopin": _b_ndec_nopin, "bav_body": C._b_bav_cli,
                 "continuity_json": _b_cont_json, "conf_apr": _b_conf_apr})


@pytest.fixture(scope="module")
def fams(tmp_path_factory):
    import dated_prices
    cache: dict = {}
    root = tmp_path_factory.mktemp("an_js_d")
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


# ------------------------------------------------------------- checks


def _refused_json(res, label, mutation, key):
    rc, so, se = res
    assert rc == 1, (A.RAN, label, mutation, rc, so[-400:], se[-400:])
    lines = [ln for ln in so.splitlines() if ln.strip()]
    assert lines, (A.RAN, label, mutation, "no stdout", se[-400:])
    doc = json.loads(lines[-1])
    assert doc.get("verdict") == "FAIL", (A.RAN, label, mutation, doc)
    C._named(str(doc.get("error")), label, mutation, key)


CHECKS = {"seven": C._refused_seven, "cli": C._refused_cli,
          "ndec": C._refused_ndec, "json": _refused_json}

# (family, label, apply, kind, check)
INPUTS = [(name, SPLICES[name][2], _splice_apply, "rebind", "seven")
          for name in SPLICES] + [
    ("ndec_nopin", "payload", C._ndec_dsse, "rebind", "ndec"),
    ("bav_body", "canonicalized_body", _bav_body, "rebind", "cli"),
    ("continuity_json", "link.json", C._plain("000/link.json"), "plain",
     "json"),
    ("conf_apr", "apr.json", C._plain("apr.json"), "plain", "cli"),
]
IDS = ["%s:%s" % (fam, label) for fam, label, _a, _k, _c in INPUTS]


def _case_dir(fams, tmp_path, fam):
    f = fams(fam)
    d = tmp_path / "case"
    shutil.copytree(f.d, d)
    return f, d


@pytest.mark.parametrize("fam", sorted(BUILDERS))
def test_d_family_baseline(fams, tmp_path, fam):
    f, d = _case_dir(fams, tmp_path, fam)
    rc, so, se = f.run(d)
    if f.baseline is None:
        assert "parse error" not in se and "refused" not in se, (fam, se)
    else:
        assert rc == f.baseline, (fam, rc, so[-900:], se[-900:])


REBINDS = [(fam, label, apply) for fam, label, apply, kind, _c in INPUTS
           if kind == "rebind"]


@pytest.mark.parametrize("fam,label,apply", REBINDS,
                         ids=["%s:%s" % (a, b) for a, b, _c in REBINDS])
def test_d_rebind_identity(fams, tmp_path, fam, label, apply):
    f, d = _case_dir(fams, tmp_path, fam)
    assert apply(f, d, None) is None
    rc, so, se = f.run(d)
    if f.baseline is None:
        assert "parse error" not in se and "refused" not in se, (fam, se)
    else:
        assert rc == f.baseline, (fam, label, rc, so[-900:], se[-900:])


@pytest.mark.parametrize("mutation", MUTATIONS)
@pytest.mark.parametrize("fam,label,apply,kind,check", INPUTS, ids=IDS)
def test_d_strict(fams, tmp_path, fam, label, apply, kind, check,
                  mutation):
    f, d = _case_dir(fams, tmp_path, fam)
    key = apply(f, d, mutation)
    CHECKS[check](f.run(d), label, mutation, key)


# ------------------------------------------------- trace bundle Rekor leg


def _tb_check():
    import conformance_verifier as cv
    import tb_check
    tb_check.loads = getattr(cv, "loads", None)  # the stand-in base gets the region's loads
    return tb_check


def _refused_call(exc, label, mutation, key):
    assert exc is not None, (A.RAN, label, mutation, "accepted")
    assert getattr(exc, "an_js_refusal", False), (A.RAN, label, mutation,
                                                  repr(exc))
    C._named(str(exc), label, mutation, key)


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_d_tb_rekor_leaf(mutation):
    tb = _tb_check()
    raw, key = B._plant_bytes(json.dumps(B.LEAF).encode("utf-8"), mutation)
    exc = None
    try:
        tb._rk_parse_leaf(raw)
    except Exception as e:  # noqa: BLE001
        exc = e
    _refused_call(exc, "canonicalized_body", mutation, key)


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_d_tb_rekor_pinned_keys(tmp_path, mutation):
    tb = _tb_check()
    p = tmp_path / "rekor_log_keys.json"
    b64 = base64.b64encode(bytes(32)).decode("ascii")
    p.write_text(json.dumps({"log.example": b64, "log2.example": b64}),
                 encoding="utf-8")
    key = B._plant_path(p, mutation)
    exc = None
    try:
        tb._rk_resolve_log_keys(str(p), None, {})
    except Exception as e:  # noqa: BLE001
        exc = e
    _refused_call(exc, "auditor-pinned log keys", mutation, key)
