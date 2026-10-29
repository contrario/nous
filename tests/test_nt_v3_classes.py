"""NT-GATE-1 V3: verdict classes and keys (K3.1 to K3.4).

Predictions: V3_PREDICTIONS.md ee46e301..., addendum 1 13de935d...
D4 as amended by the operator: 0 PASS, 1 INTEGRITY, 2 ENVIRONMENT,
3 OUTSIDE, and a "CLASS:" line last on stdout. No PASS without an
auditor-supplied --expect-signer.

# __nt_v3_classes_tests_v1__
"""
from __future__ import annotations

import argparse
import base64
import dataclasses
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

import cli_conformance
import conformance_verifier
import cost_farkas as cf
import dossier
import manifest as mf
import ndec
import offline_verifier_builder as ob
import test_nt_v1b_certify_canon as v1b
import test_nt_v2_recompute as v2t
import vsa_verifier
from nous_trace import TraceEnvelope, sign_trace
from parser import parse_nous
from rekor_verify_v2 import KNOWN_REKOR_V2_LOG_KEYS
from smt_emit import emit_smt
from smt_verify import VerifyResult

REPO = Path(__file__).resolve().parent.parent
pricing = v1b.pricing
s97 = v1b.s97

REGION_START = (
    "# --- v3 verdict classes embed (shared text; canonical copy: "
    "conformance_verifier.py) ---"
)
REGION_END = "# --- end v3 verdict classes embed ---"
MARK = "__nt_v3_classes_v1__"

DOSSIER_TEMPLATES = (
    "VERIFY_OFFLINE_PY", "VERIFY_OFFLINE_PY_WITH_REKOR",
    "VERIFY_OFFLINE_PY_CHAIN", "VERIFY_OFFLINE_PY_BUNDLE",
    "VERIFY_OFFLINE_PY_FARKAS", "VERIFY_OFFLINE_PY_COVERAGE",
    "VERIFY_OFFLINE_PY_CHAIN_BUNDLE",
)
TEXT_NAMES = (
    tuple("dossier." + n for n in DOSSIER_TEMPLATES)
    + ("dossier.chain_net", "dossier.gap_witness", "builder.dossier_v2",
       "conformance.standalone", "builder.conformance_v2", "vsa.template",
       "ndec.carried")
)

RUNTIME_NC = (
    "NOT CLAIMED", "completeness", "token counts", "the served model",
    "tool labels", "prices outside", "time:", "identity:",
    "the operator's honesty", "control: none", "regulatory status: none",
)
DOSSIER_NC = (
    "NOT CLAIMED", "declared", "identity:", "the operator's honesty",
    "control: none", "regulatory status: none",
)


def _texts() -> dict:
    allow = repr(KNOWN_REKOR_V2_LOG_KEYS)
    out = {"dossier." + n: getattr(dossier, n) for n in DOSSIER_TEMPLATES}
    out["dossier.chain_net"] = dossier.build_chain_net_verifier()
    out["dossier.gap_witness"] = dossier.build_gap_witness_verifier()
    out["builder.dossier_v2"] = ob.build_offline_verifier_v2(allow)
    out["conformance.standalone"] = (
        conformance_verifier.CONFORMANCE_VERIFY_OFFLINE_PY
    )
    out["builder.conformance_v2"] = ob.build_conformance_verifier_v2(allow)
    out["vsa.template"] = vsa_verifier.VSA_VERIFY_OFFLINE_PY
    out["ndec.carried"] = ndec.VERIFY_NDEC_PY
    assert tuple(sorted(out)) == tuple(sorted(TEXT_NAMES))
    return out


def _region(text: str):
    if text.count(REGION_START) != 1:
        return None
    i = text.index(REGION_START)
    j = text.find(REGION_END, i)
    if j < 0:
        return None
    return text[i:j + len(REGION_END)]


def _canonical_region():
    src = (REPO / "conformance_verifier.py").read_text(encoding="utf-8")
    m = re.search(
        r"(?ms)^" + re.escape(REGION_START) + r"$.*?^"
        + re.escape(REGION_END) + r"$", src)
    return m.group(0) if m else None


def _last_line(out: str) -> str:
    lines = [ln for ln in out.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def _run(d: Path, script: str, args=()):
    p = subprocess.run([sys.executable, "-I", "-B", script] + list(args),
                       cwd=str(d), capture_output=True, text=True,
                       timeout=180)
    return p.returncode, p.stdout, p.stderr


def _b64_pub(key: Ed25519PrivateKey) -> str:
    return base64.b64encode(key.public_key().public_bytes_raw()).decode(
        "ascii")


OTHER = Ed25519PrivateKey.from_private_bytes(bytes(range(200, 232)))
OTHER_PIN = _b64_pub(OTHER)


# ------------------------------------------------------------------ R1


def test_r1_canonical_region_exists():
    reg = _canonical_region()
    assert reg is not None, "no canonical v3 region in conformance_verifier"
    assert MARK in reg
    assert reg.isascii()


@pytest.mark.parametrize("name", TEXT_NAMES)
def test_r1_region_in_text(name):
    text = _texts()[name]
    reg = _region(text)
    assert reg is not None, name + ": no v3 region"
    assert reg == _canonical_region(), name + ": region drifted"


# ------------------------------------------------------------------ R2


@pytest.mark.parametrize("name", TEXT_NAMES)
def test_r2_no_pin_is_environment(name, tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    (d / "v.py").write_text(_texts()[name], encoding="utf-8")
    rc, out, err = _run(d, "v.py")
    assert rc == 2, (name, rc, out, err)
    assert _last_line(out) == "CLASS: ENVIRONMENT", (name, out, err)
    assert "PASS" not in out.replace("CLASS: ENVIRONMENT", ""), out


# ------------------------------------------------- conformance material


def _certify(d: Path, key: Path):
    ns = argparse.Namespace(
        command="conformance", conformance_cmd="certify",
        trace=str(d / "trace.json"), manifest=str(d / "manifest.json"),
        prices=str(d / "pricing.toml"), source=str(d / "source.nous"),
        out=str(d / "conformance.json"), key_path=str(key),
        issued_utc="2026-05-26T00:00:00Z", anchor=None,
        emit_obligations_canon=False,
    )
    assert cli_conformance.cmd_conformance(ns) == 0


def _conf_bundle(pricing, tmp_path: Path, events, name="cb") -> tuple:
    d = tmp_path / (name + "_mat")
    d.mkdir()
    program = parse_nous(s97._SOULED_SOURCE)
    spec = emit_smt(program, pricing, source_text=s97._SOULED_SOURCE,
                    today=s97.TODAY)
    man = mf.manifest_from_verify(
        VerifyResult(verdict="proven", spec=spec, solver_name="z3",
                     solver_version="z3 4.16.0", elapsed_ms=11,
                     timestamp_utc="2026-05-26T00:00:00+00:00"),
        nous_version="5.13.1",
    )
    doc = cf.cost_certificate_from_smtspec(spec)
    man = dataclasses.replace(man,
                              cost_farkas_sha256=cf.cost_farkas_sha256(doc))
    env = TraceEnvelope(
        nous_version="5.13.1", world_name=spec.world_name,
        source_sha256=spec.source_sha256, smt_spec_sha256=spec.sha256(),
        pricing_sha256=spec.pricing_sha256, events=events)
    tr = sign_trace(env, Ed25519PrivateKey.generate())
    (d / "source.nous").write_text(s97._SOULED_SOURCE, encoding="utf-8")
    (d / "pricing.toml").write_text(s97.PRICING_TOML, encoding="utf-8")
    (d / "trace.json").write_text(s97._trace_json(tr), encoding="utf-8")
    key = d / "op.key"
    priv, pub, _ = mf.load_or_create_keypair(key)
    (d / "manifest.json").write_text(
        mf.manifest_json(man, mf.sign_manifest(man, priv), pub),
        encoding="utf-8")
    _certify(d, key)
    b = tmp_path / name
    b.mkdir()
    for n in ("conformance.json", "trace.json", "manifest.json"):
        (b / n).write_bytes((d / n).read_bytes())
    return b, mf.public_key_b64(pub)


GENUINE = lambda: [s97._event(0, 0, "Analyst", it=900, ot=400),  # noqa
                   s97._event(1, 1, "Trader", it=300, ot=150)]
OVER = lambda: [s97._event(0, 0, "Analyst", it=10 ** 6, ot=0)]  # noqa
CONF_TEXTS = ("conformance.standalone", "builder.conformance_v2")


def _run_conf(b: Path, name: str, pin):
    (b / "verify_conformance_offline.py").write_text(
        _texts()[name], encoding="utf-8")
    args = ["--expect-signer", pin] if pin else []
    if name == "builder.conformance_v2":
        args = ["--allow-unanchored"] + args
    return _run(b, "verify_conformance_offline.py", args)


# ------------------------------------------------------------- R3, R4


@pytest.mark.parametrize("name", CONF_TEXTS)
def test_r3_manifest_resigned_by_another_key(pricing, tmp_path, name):
    b, pin = _conf_bundle(pricing, tmp_path, GENUINE())
    m, _sig, _pub = mf.parse_manifest_json(
        (b / "manifest.json").read_text(encoding="utf-8"))
    (b / "manifest.json").write_text(
        mf.manifest_json(m, mf.sign_manifest(m, OTHER), OTHER.public_key()),
        encoding="utf-8")
    rc, out, err = _run_conf(b, name, pin)
    assert rc == 1, (rc, out, err)
    assert _last_line(out) == "CLASS: INTEGRITY", out
    assert "manifest signer" in err, err


@pytest.mark.parametrize("name", CONF_TEXTS)
def test_r4_conformance_pass(pricing, tmp_path, name):
    b, pin = _conf_bundle(pricing, tmp_path, GENUINE())
    rc, out, err = _run_conf(b, name, pin)
    assert rc == 0, (rc, out, err)
    assert _last_line(out) == "CLASS: PASS", out
    for s in RUNTIME_NC:
        assert s in out, (s, out)


@pytest.mark.parametrize("name", CONF_TEXTS)
def test_r4_conformance_outside(pricing, tmp_path, name):
    b, pin = _conf_bundle(pricing, tmp_path, OVER())
    cert = json.loads((b / "conformance.json").read_text(encoding="utf-8"))
    assert cert["conformant"] is False
    rc, out, err = _run_conf(b, name, pin)
    assert rc == 3, (rc, out, err)
    assert _last_line(out) == "CLASS: OUTSIDE", out
    assert "VERDICT: OUTSIDE" in out, out


@pytest.mark.parametrize("name", CONF_TEXTS)
def test_r4_conformance_integrity(pricing, tmp_path, name):
    b, pin = _conf_bundle(pricing, tmp_path, GENUINE())
    raw = (b / "trace.json").read_text(encoding="utf-8")
    assert raw.count('"input_tokens": 900') == 1
    (b / "trace.json").write_text(
        raw.replace('"input_tokens": 900', '"input_tokens": 901'),
        encoding="utf-8")
    rc, out, err = _run_conf(b, name, pin)
    assert rc == 1, (rc, out, err)
    assert _last_line(out) == "CLASS: INTEGRITY", out


@pytest.mark.parametrize("name", CONF_TEXTS)
def test_r4_conformance_another_key_pinned(pricing, tmp_path, name):
    b, _pin = _conf_bundle(pricing, tmp_path, GENUINE())
    rc, out, err = _run_conf(b, name, OTHER_PIN)
    assert rc == 1, (rc, out, err)
    assert _last_line(out) == "CLASS: INTEGRITY", out



# ----------------------------------------------- R3b (addendum 2, D2')

DEMO = REPO / "examples" / "demos" / "cert-4679350"


def _demo(tmp_path: Path, name: str) -> Path:
    d = tmp_path / name
    d.mkdir()
    for n in ("conformance.json", "trace.json", "manifest.json"):
        shutil.copy(DEMO / n, d / n)
    return d


def _key(d: Path, n: str) -> str:
    return json.loads((d / n).read_text(encoding="utf-8"))[
        "signature"]["public_key_b64"]


@pytest.mark.parametrize("name", CONF_TEXTS)
def test_r3b_demo_two_keys(tmp_path, name):
    d = _demo(tmp_path, "both")
    ck, mk = _key(d, "conformance.json"), _key(d, "manifest.json")
    assert ck != mk
    (d / "v.py").write_text(_texts()[name], encoding="utf-8")
    rc, out, err = _run(d, "v.py", ["--expect-signer", ck,
                                     "--expect-manifest-signer", mk])
    assert rc == 0, (rc, out, err)
    assert _last_line(out) == "CLASS: PASS", out
    d2 = _demo(tmp_path, "one")
    (d2 / "v.py").write_text(_texts()[name], encoding="utf-8")
    rc, out, err = _run(d2, "v.py", ["--expect-signer", ck])
    assert rc == 1, (rc, out, err)
    assert _last_line(out) == "CLASS: INTEGRITY", out
    assert "manifest signer" in err, err


# ------------------------------------------------------------ dossiers


PROVEN_SRC = (
    "world Floor {\n    cost_cap: 1.00 USD\n    max_ticks: 5\n}\n"
    "soul Analyst {\n    mind: claude-sonnet-4-6 @ Tier1\n"
    "    tokens: input=1000 output=500\n}\n"
)
REFUTED_SRC = PROVEN_SRC.replace("cost_cap: 1.00 USD",
                                 "cost_cap: 0.000001 USD")


@pytest.fixture
def dated(tmp_path):
    import dated_prices
    with pytest.MonkeyPatch.context() as mp:
        dated_prices.use_dated_shipped_prices(tmp_path / "prices", mp)
        yield


def _dossier(tmp_path: Path, src_text: str, name: str, **kw) -> tuple:
    from cli_verify import cmd_verify
    work = tmp_path / (name + "_work")
    work.mkdir()
    src = work / "source.nous"
    src.write_text(src_text, encoding="utf-8")
    key = work / "signing.key"

    class A:
        file = str(src)
        smt = True
        prices = None
        timeout_ms = 30000
        no_manifest = False
        manifest_out = str(work / "source.manifest.json")
        key_path = str(key)
        smt_margin = 0
        no_lint = True
        lint_strict = False
        lint_error_on = None

    cmd_verify(A())
    out = tmp_path / name
    dossier.build_dossier(src, manifest=work / "source.manifest.json",
                          output=out, **kw)
    _priv, pub, _ = mf.load_or_create_keypair(key)
    return out, mf.public_key_b64(pub)


def test_r5_dossier_pass(dated, tmp_path):
    out, pin = _dossier(tmp_path, PROVEN_SRC, "proven")
    rc, so, se = _run(out, "verify_offline.py", ["--expect-signer", pin])
    assert rc == 0, (rc, so, se)
    assert _last_line(so) == "CLASS: PASS", so
    for s in DOSSIER_NC:
        assert s in so, (s, so)


def test_r5_dossier_refuted_is_outside(dated, tmp_path):
    out, pin = _dossier(tmp_path, REFUTED_SRC, "refuted")
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert man["verdict"] == "refuted"
    rc, so, se = _run(out, "verify_offline.py", ["--expect-signer", pin])
    assert rc == 3, (rc, so, se)
    assert _last_line(so) == "CLASS: OUTSIDE", so
    assert "VERDICT: PASS" not in so, so


def test_r5_dossier_source_altered(dated, tmp_path):
    out, pin = _dossier(tmp_path, PROVEN_SRC, "altered")
    (out / "source.nous").write_text(PROVEN_SRC + "\n", encoding="utf-8")
    rc, so, se = _run(out, "verify_offline.py", ["--expect-signer", pin])
    assert rc == 1, (rc, so, se)
    assert _last_line(so) == "CLASS: INTEGRITY", so


def test_r5_dossier_another_key_pinned(dated, tmp_path):
    out, _pin = _dossier(tmp_path, PROVEN_SRC, "otherkey")
    rc, so, se = _run(out, "verify_offline.py",
                      ["--expect-signer", OTHER_PIN])
    assert rc == 1, (rc, so, se)
    assert _last_line(so) == "CLASS: INTEGRITY", so
    assert "manifest signer" in se, se


# ------------------------------------------------------------------ R6


def test_r6_gap_witness_is_outside(tmp_path):
    import test_s134_gapw_e2e as gw
    if not gw.TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src = gw._issue(tmp_path)
    out = tmp_path / "gw_out"
    dossier.build_dossier(src, manifest=tmp_path / "source.manifest.json",
                          output=out)
    _priv, pub, _ = mf.load_or_create_keypair(tmp_path / "signing.key")
    rc, so, se = _run(out, "verify_offline.py",
                      ["--expect-signer", mf.public_key_b64(pub)])
    assert rc == 3, (rc, so, se)
    assert _last_line(so) == "CLASS: OUTSIDE", so
    assert "result: gap-demonstrated" in so, so


# ------------------------------------------------------------------ R7


V2DIR = REPO / "website" / ".well-known" / "nous" / "vsa-vectors" / "v2"


def _harness():
    spec = importlib.util.spec_from_file_location(
        "nt_v3_vsa_harness", V2DIR / "mint_vsa_vector.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["nt_v3_vsa_harness"] = mod
    spec.loader.exec_module(mod)
    return mod


def _vsa_mint(tmp_path: Path, in_tok: int, name: str) -> tuple:
    hv = _harness()
    import pricing as pm
    import smt_emit as sm
    saved = (pm.datetime, sm.datetime)
    pm.datetime = hv._PinnedPriceClock
    sm.datetime = hv._PinnedPriceClock
    try:
        run_root = tmp_path / name
        work = run_root / "work"
        work.mkdir(parents=True)
        source_path = V2DIR / "vsa_conformance_vector_v2.nous"
        source_text = source_path.read_text(encoding="utf-8")
        mkey = work / "_manifest.key"
        hv._write_pkcs8_pem(hv._SEED_MANIFEST, mkey)
        assert hv.cli_verify.cmd_verify(
            hv._verify_args(source_path, work, mkey)) == 0
        manifest_path = work / "manifest.json"
        hv._repin_manifest(manifest_path)
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
        rec.record_llm_call(hv._SOUL, 0, in_tok, hv._OUT_TOK)
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
    return bundle, _b64_pub(hv._fixed_key(hv._SEED_VSA))


def test_r7_vsa_pass(tmp_path):
    b, pin = _vsa_mint(tmp_path, 100, "pass")
    rc, so, se = _run(b, "verify_vsa_offline.py", ["--expect-signer", pin])
    assert rc == 0, (rc, so, se)
    assert _last_line(so) == "CLASS: PASS", so
    for s in RUNTIME_NC:
        assert s in so, (s, so)


def test_r7_vsa_outside(tmp_path):
    b, pin = _vsa_mint(tmp_path, 10 ** 7, "outside")
    cert = json.loads((b / "conformance.json").read_text(encoding="utf-8"))
    assert cert["conformant"] is False
    rc, so, se = _run(b, "verify_vsa_offline.py", ["--expect-signer", pin])
    assert rc == 3, (rc, so, se)
    assert _last_line(so) == "CLASS: OUTSIDE", so


def test_r7_vsa_no_pin(tmp_path):
    b, _pin = _vsa_mint(tmp_path, 100, "nopin")
    rc, so, se = _run(b, "verify_vsa_offline.py")
    assert rc == 2, (rc, so, se)
    assert _last_line(so) == "CLASS: ENVIRONMENT", so


def test_r7_vsa_another_key_pinned(tmp_path):
    b, _pin = _vsa_mint(tmp_path, 100, "other")
    rc, so, se = _run(b, "verify_vsa_offline.py",
                      ["--expect-signer", OTHER_PIN])
    assert rc == 1, (rc, so, se)
    assert _last_line(so) == "CLASS: INTEGRITY", so


def test_r7_vsa_inline_pin_differs_from_auditor(tmp_path):
    b, pin = _vsa_mint(tmp_path, 100, "inline")
    vsa_verifier.emit_vsa_verifier(str(b), OTHER_PIN)
    rc, so, se = _run(b, "verify_vsa_offline.py", ["--expect-signer", pin])
    assert rc == 1, (rc, so, se)
    assert _last_line(so) == "CLASS: INTEGRITY", so


def test_r7_vsa_forged_expensive_is_refused(tmp_path):
    d = tmp_path / "forged"
    v2t._forge_v2_expensive(d)
    vsa_pin = _b64_pub(Ed25519PrivateKey.from_private_bytes(v2t.SEED_V))
    vsa_verifier.emit_vsa_verifier(str(d), vsa_pin)
    rc, so, se = _run(d, "verify_vsa_offline.py",
                      ["--expect-signer", vsa_pin])
    assert rc == 1, (rc, so, se)
    assert _last_line(so) == "CLASS: INTEGRITY", so
    assert "recomput" in se, se


# ------------------------------------------------------------------ R9


def test_r9_ndec_pins_the_inner_run(dated, tmp_path):
    out, _pin = _dossier(tmp_path, PROVEN_SRC, "nd")
    res = ndec.build_ndec(out, key_path=tmp_path / "ndec.key",
                          output=tmp_path / "d.ndec")
    _priv, npub, _ = mf.load_or_create_keypair(tmp_path / "ndec.key")
    assert ndec.verify_ndec_file(res.path, public_key=npub) == 0
    assert ndec.verify_ndec_file(res.path) == 2


# ----------------------------------------------------------------- R10


def test_r10_readme_gives_the_pinned_command(dated, tmp_path):
    out, _pin = _dossier(tmp_path, PROVEN_SRC, "readme")
    text = (out / "README.md").read_text(encoding="utf-8")
    assert "--expect-signer" in text, text
    assert "declared" in text, text
    assert "across all execution paths" not in text, text


# ------------------------------------------------- R11, R12 (addendum 3)


_ARG_REFUSALS = ("unrecognized arguments", "unexpected argument", "usage:")


def _own_option_sets(text: str) -> list:
    sets = [["--expect-signer", OTHER_PIN]]
    if "--allow-unanchored" in text:
        sets.append(["--allow-unanchored", "--expect-signer", OTHER_PIN])
    if "--expect-manifest-signer" in text:
        sets.append(["--expect-signer", OTHER_PIN,
                     "--expect-manifest-signer", OTHER_PIN])
    return sets


@pytest.mark.parametrize("name", TEXT_NAMES)
def test_r11_text_accepts_its_own_options(name, tmp_path):
    text = _texts()[name]
    for i, args in enumerate(_own_option_sets(text)):
        d = tmp_path / ("e" + str(i))
        d.mkdir()
        (d / "v.py").write_text(text, encoding="utf-8")
        rc, out, err = _run(d, "v.py", args)
        for s in _ARG_REFUSALS:
            assert s not in err, (name, args, rc, err)
        assert _last_line(out).startswith("CLASS: "), (name, args, out)


def _rekor_v2_dossier(tmp_path: Path, src_text: str, name: str,
                      keep_anchor: bool) -> tuple:
    from test_s93_dossier_rekor_v2_emit import _fake_v2_anchor
    out, pin = _dossier(tmp_path, src_text, name, anchor="rekor_v2",
                        _test_rekor_anchor_v2=_fake_v2_anchor())
    text = (out / "verify_offline.py").read_text(encoding="utf-8")
    assert "Rekor v2 (tile-backed)" in text
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert "transparency_log" in man
    if not keep_anchor:
        del man["transparency_log"]
        (out / "manifest.json").write_text(
            json.dumps(man, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
    return out, pin


def test_r12a_rekor_v2_dossier_unanchored_pass(dated, tmp_path):
    out, pin = _rekor_v2_dossier(tmp_path, PROVEN_SRC, "v2a", False)
    rc, so, se = _run(out, "verify_offline.py",
                      ["--allow-unanchored", "--expect-signer", pin])
    assert rc == 0, (rc, so, se)
    assert _last_line(so) == "CLASS: PASS", so
    for s in DOSSIER_NC:
        assert s in so, (s, so)


def test_r12b_rekor_v2_dossier_another_key(dated, tmp_path):
    out, _pin = _rekor_v2_dossier(tmp_path, PROVEN_SRC, "v2b", False)
    rc, so, se = _run(out, "verify_offline.py",
                      ["--allow-unanchored", "--expect-signer", OTHER_PIN])
    assert rc == 1, (rc, so, se)
    assert _last_line(so) == "CLASS: INTEGRITY", so
    assert "manifest signer" in se, se


def test_r12c_rekor_v2_dossier_fake_anchor(dated, tmp_path):
    out, pin = _rekor_v2_dossier(tmp_path, PROVEN_SRC, "v2c", True)
    rc, so, se = _run(out, "verify_offline.py", ["--expect-signer", pin])
    assert rc == 1, (rc, so, se)
    assert _last_line(so) == "CLASS: INTEGRITY", so
    assert "Rekor v2 anchor" in se, se


def test_r12d_rekor_v2_dossier_refuted_is_outside(dated, tmp_path):
    out, pin = _rekor_v2_dossier(tmp_path, REFUTED_SRC, "v2d", False)
    rc, so, se = _run(out, "verify_offline.py",
                      ["--allow-unanchored", "--expect-signer", pin])
    assert rc == 3, (rc, so, se)
    assert _last_line(so) == "CLASS: OUTSIDE", so
    assert "VERDICT: PASS" not in so, so


# ------------------------------------------------- R13, R14 (addendum 4)


_INPUTS = ("manifest.json", "conformance.json", "trace.json",
           "vsa.intoto.json")


@pytest.mark.parametrize("name", TEXT_NAMES)
def test_r13_missing_dependency_is_environment(name, tmp_path):
    text = _texts()[name]
    args = _own_option_sets(text)[-1]
    d = tmp_path / "nodep"
    d.mkdir()
    (d / "v.py").write_text(text, encoding="utf-8")
    for n in _INPUTS:
        (d / n).write_text("{}", encoding="utf-8")
    p = subprocess.run([sys.executable, "-I", "-S", "-B", "v.py"] + args,
                       cwd=str(d), capture_output=True, text=True,
                       timeout=180)
    assert p.returncode == 2, (name, p.returncode, p.stdout, p.stderr)
    assert _last_line(p.stdout) == "CLASS: ENVIRONMENT", (name, p.stdout)
    assert "cryptography" in p.stderr, (name, p.stderr)


DOSSIER_FAMILY = tuple(n for n in TEXT_NAMES
                       if n.startswith(("dossier.", "builder.dossier")))


@pytest.fixture(scope="module")
def one_dossier(tmp_path_factory):
    import dated_prices
    tmp = tmp_path_factory.mktemp("r14")
    with pytest.MonkeyPatch.context() as mp:
        dated_prices.use_dated_shipped_prices(tmp / "prices", mp)
        return _dossier(tmp, PROVEN_SRC, "r14")


@pytest.mark.parametrize("name", DOSSIER_FAMILY)
def test_r14_every_dossier_text_checks_the_signer(name, one_dossier,
                                                   tmp_path):
    out, pin = one_dossier
    seen = {}
    for label, key in (("own", pin), ("other", OTHER_PIN)):
        d = tmp_path / label
        shutil.copytree(out, d)
        (d / "verify_offline.py").write_text(_texts()[name],
                                             encoding="utf-8")
        args = ["--expect-signer", key]
        if name == "builder.dossier_v2":
            args = ["--allow-unanchored"] + args
        seen[label] = _run(d, "verify_offline.py", args)
    rc, so, se = seen["other"]
    assert rc == 1, (name, rc, so, se)
    assert _last_line(so) == "CLASS: INTEGRITY", (name, so)
    assert "manifest signer" in se, (name, se)
    rc, so, se = seen["own"]
    assert "manifest signer" not in se, (name, se)


# --------------------------------------------- R16, R17, R18 (addendum 5)


def _ndec_of(tmp_path: Path, src_text: str, name: str) -> tuple:
    out, _pin = _dossier(tmp_path, src_text, name)
    res = ndec.build_ndec(out, key_path=tmp_path / (name + ".ndec.key"),
                          output=tmp_path / (name + ".ndec"))
    priv, npub, _ = mf.load_or_create_keypair(
        tmp_path / (name + ".ndec.key"))
    return res.path, priv, npub, mf.public_key_b64(npub)


def _extract(ndec_path: Path, dest: Path) -> Path:
    import zipfile
    with zipfile.ZipFile(ndec_path) as z:
        z.extractall(dest)
    return dest


def test_r16_carried_ndec_pass(dated, tmp_path):
    path, _priv, _npub, nkey = _ndec_of(tmp_path, PROVEN_SRC, "n16a")
    x = _extract(path, tmp_path / "x")
    rc, so, se = _run(x, "verify_ndec.py", ["--expect-signer", nkey])
    assert rc == 0, (rc, so, se)
    assert _last_line(so) == "CLASS: PASS", so
    for s in DOSSIER_NC:
        assert s in so, (s, so)


def test_r16_carried_ndec_another_key(dated, tmp_path):
    path, _priv, _npub, _nkey = _ndec_of(tmp_path, PROVEN_SRC, "n16b")
    x = _extract(path, tmp_path / "x")
    rc, so, se = _run(x, "verify_ndec.py", ["--expect-signer", OTHER_PIN])
    assert rc == 1, (rc, so, se)
    assert _last_line(so) == "CLASS: INTEGRITY", so
    assert "ndec signer" in se, se


def test_r16_carried_ndec_no_key(dated, tmp_path):
    path, _priv, _npub, _nkey = _ndec_of(tmp_path, PROVEN_SRC, "n16c")
    x = _extract(path, tmp_path / "x")
    rc, so, se = _run(x, "verify_ndec.py")
    assert rc == 2, (rc, so, se)
    assert _last_line(so) == "CLASS: ENVIRONMENT", so


def test_r16_carried_ndec_refuted_is_outside(dated, tmp_path):
    path, _priv, _npub, nkey = _ndec_of(tmp_path, REFUTED_SRC, "n16d")
    x = _extract(path, tmp_path / "x")
    rc, so, se = _run(x, "verify_ndec.py", ["--expect-signer", nkey])
    assert rc == 3, (rc, so, se)
    assert _last_line(so) == "CLASS: OUTSIDE", so
    assert "VERDICT: PASS" not in so, so


def _drop_manifest_digest(path: Path, priv, tmp_path: Path) -> Path:
    import zipfile
    with zipfile.ZipFile(path) as z:
        entries = {n: z.read(n) for n in z.namelist()}
    env = json.loads(entries["attestation.intoto.json"])
    stmt = json.loads(base64.b64decode(env["payload"]))
    del stmt["predicate"]["artifacts"]["manifest_sha256"]
    entries["attestation.intoto.json"] = json.dumps(
        ndec.sign_envelope(statement=stmt, private_key=priv),
        sort_keys=True, separators=(",", ":")).encode("utf-8")
    new = tmp_path / "dropped.ndec"
    new.write_bytes(ndec._build_zip_bytes(entries))
    return new


def test_r17_installed_refuses_unbound_manifest(dated, tmp_path):
    path, priv, npub, _nkey = _ndec_of(tmp_path, PROVEN_SRC, "n17a")
    new = _drop_manifest_digest(path, priv, tmp_path)
    assert ndec.verify_ndec_file(new, public_key=npub) == 1


def test_r17_carried_refuses_unbound_manifest(dated, tmp_path):
    path, priv, _npub, nkey = _ndec_of(tmp_path, PROVEN_SRC, "n17b")
    new = _drop_manifest_digest(path, priv, tmp_path)
    x = _extract(new, tmp_path / "x")
    rc, so, se = _run(x, "verify_ndec.py", ["--expect-signer", nkey])
    assert rc == 1, (rc, so, se)
    assert "manifest_sha256" in se, se


def _cli(argv):
    p = subprocess.run([sys.executable, "-B", str(REPO / "cli.py")]
                       + list(argv), capture_output=True, text=True,
                       cwd=str(REPO), timeout=300)
    return p.returncode, p.stdout, p.stderr


def test_r18_cli_ndec_verify_with_key(dated, tmp_path):
    path, _priv, _npub, nkey = _ndec_of(tmp_path, PROVEN_SRC, "n18a")
    rc, so, se = _cli(["ndec", "verify", str(path), "--expect-signer",
                       nkey])
    assert rc == 0, (rc, so, se)


def test_r18_cli_ndec_verify_without_key(dated, tmp_path):
    path, _priv, _npub, _nkey = _ndec_of(tmp_path, PROVEN_SRC, "n18b")
    for argv in (["ndec", "verify", str(path)], ["verify", str(path)]):
        rc, so, se = _cli(argv)
        assert rc == 2, (argv, rc, so, se)
        assert "--expect-signer" in so, (argv, so)


def test_r18_cli_ndec_verify_malformed_key(dated, tmp_path):
    path, _priv, _npub, _nkey = _ndec_of(tmp_path, PROVEN_SRC, "n18c")
    rc, so, se = _cli(["ndec", "verify", str(path), "--expect-signer",
                       "AAAA"])
    assert rc == 2, (rc, so, se)
    assert "--expect-signer" in se, se


# ---------------------------------------------------- R19 (addendum 6)


def _refuted_bundle_dossier(tmp_path: Path) -> tuple:
    import hashlib
    import test_trace_bundle_dossier as tb
    pack = tb._build_valid_pack(tmp_path)
    d = tmp_path / "refuted_tb"
    d.mkdir()
    src = b"world W {}\n"
    (d / "source.nous").write_bytes(src)
    shutil.copytree(pack, d / "trace_bundle")
    man = {"source_sha256": hashlib.sha256(src).hexdigest(),
           "verdict": "refuted",
           "trace_bundle_sha256": hashlib.sha256(
               (d / "trace_bundle" / "manifest.json").read_bytes()
           ).hexdigest()}
    man = tb._sign_manifest(man)
    (d / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    (d / "verify_offline.py").write_text(
        dossier._splice_trace_bundle_check(dossier.VERIFY_OFFLINE_PY),
        encoding="utf-8")
    return d, man["signature"]["public_key_b64"]


def test_r19_refuted_untouched_is_outside(tmp_path):
    d, pin = _refuted_bundle_dossier(tmp_path)
    rc, so, se = _run(d, "verify_offline.py", ["--expect-signer", pin])
    assert rc == 3, (rc, so, se)
    assert _last_line(so) == "CLASS: OUTSIDE", so


def test_r19_refuted_altered_bundle_is_integrity(tmp_path):
    d, pin = _refuted_bundle_dossier(tmp_path)
    tf = d / "trace_bundle" / "trace.ndjson"
    ev = [json.loads(x) for x in tf.read_text().splitlines() if x.strip()]
    ev[1]["body"]["model"] = "x"
    tf.write_text("".join(json.dumps(e, separators=(",", ":")) + "\n"
                          for e in ev), encoding="utf-8")
    rc, so, se = _run(d, "verify_offline.py", ["--expect-signer", pin])
    assert rc == 1, (rc, so, se)
    assert _last_line(so) == "CLASS: INTEGRITY", so
    assert "SIG_INVALID" in se, se
