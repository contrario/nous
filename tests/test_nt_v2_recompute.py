"""NT-GATE-1 V2: the offline conformance verifiers recompute the cost
obligations (D6 (i)) from trace.json and the certificate's spec canon.

Red before any V2 code (V2_PREDICTIONS.md, sha256 d4a8ec92...).

# __nt_v2_recompute_tests_v1__
"""
from __future__ import annotations

import base64
import copy
import dataclasses
import hashlib
import json
import subprocess
from _v3pin import conformance_pin_args  # __nt_v3_classes_tests_v1__
import sys
from datetime import date
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

import conformance
import conformance_verifier
import cost_farkas as cf
import offline_verifier_builder
import test_nt_v1b_certify_canon as v1b
from conformance import ConformancePreconditionError, verify_conformance
from manifest import manifest_from_verify
from nous_trace import TraceEnvelope
from parser import parse_nous
from pricing import load_pricing
from smt_emit import emit_smt
from smt_verify import VerifyResult

pricing = v1b.pricing

REPO = Path(__file__).resolve().parent.parent
DEMO = "examples/demos/cert-4679350/verify_conformance_offline.py"
DEMO_SHA = "14239550160971edff712f9a2a818f4443f28e0303dbede4d65832068520d7b8"
SERVED_V1 = "website/.well-known/nous/vsa-vectors/v1/verify_vsa_offline.py"
SERVED_V2 = "website/.well-known/nous/vsa-vectors/v2/verify_vsa_offline.py"
SERVED_V3 = "website/.well-known/nous/vsa-vectors/v3/verify_vsa_offline.py"  # __nt_v3_classes_tests_v1__
FN = "_conf_recompute"
REGION_START = (
    "# --- conformance recompute embed (shared text; canonical copy: "
    "conformance.py) ---"
)
REGION_END = "# --- end conformance recompute embed ---"
BANNED = ("langchain", "langgraph", "pydantic", "lark", "z3")


def _texts() -> dict:
    return {
        "standalone": conformance_verifier.CONFORMANCE_VERIFY_OFFLINE_PY,
        "anchored": offline_verifier_builder.build_conformance_verifier_v2(
            "{}"),
    }


TEXTS = ("standalone", "anchored")
ARGS = {"standalone": [], "anchored": ["--allow-unanchored"]}


def _region(text: str):
    i = text.find(REGION_START)
    if i < 0:
        return None
    j = text.find(REGION_END, i)
    return None if j < 0 else text[i:j + len(REGION_END)]


# ------------------------------------------------------------- Q1, Q10


def test_q1_census_of_texts_judging_recorded_obligations():
    r = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z", "--cached", "--others",
         "--exclude-standard", "--", "*.py"],
        capture_output=True, check=True,
    )
    found = set()
    for rel in r.stdout.decode("utf-8").split("\0"):
        if rel and not rel.startswith("tests/") and \
                b"assumption_discharge_ok" in (REPO / rel).read_bytes():
            found.add(rel)
    assert found == {
        "cli_conformance.py", "conformance.py", "conformance_verifier.py",
        "continuity_ledger.py", DEMO, "offline_verifier_builder.py",
        "vsa.py", "vsa_verifier.py", SERVED_V1, SERVED_V2, SERVED_V3,
    }


def test_q10_demo_copy_is_frozen():
    got = hashlib.sha256((REPO / DEMO).read_bytes()).hexdigest()
    assert got == DEMO_SHA


# ---------------------------------------------------------- Q2, Q3


@pytest.mark.parametrize("name", TEXTS)
def test_q2_text_defines_the_recompute(name, tmp_path, monkeypatch):
    import types
    mod = types.ModuleType("nt_v2_text")
    mod.__file__ = str(tmp_path / "v.py")
    monkeypatch.setitem(sys.modules, "nt_v2_text", mod)
    exec(compile(_texts()[name], "nt_v2_text", "exec"), mod.__dict__)
    assert FN in mod.__dict__, name + ": no " + FN


@pytest.mark.parametrize("name", TEXTS)
def test_q3_region_matches_canonical(name):
    canon = (REPO / "conformance.py").read_text(encoding="utf-8")
    assert canon.count(REGION_START) == 1
    text = _texts()[name]
    assert text.count(REGION_START) == 1, name
    assert _region(text) == _region(canon), name + ": region drifted"


# ------------------------------------------------------ bundle helpers


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _body(doc: dict, drop) -> bytes:
    return json.dumps({k: v for k, v in doc.items() if k not in drop},
                      sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign(doc: dict, drop, key: Ed25519PrivateKey) -> None:
    sig = dict(doc.get("signature") or {})
    sig["algorithm"] = "ed25519"
    sig["public_key_b64"] = _b64(key.public_key().public_bytes_raw())
    sig["signature_b64"] = _b64(key.sign(_body(doc, drop)))
    doc["signature"] = sig


TRACE_DROP = ("signature",)
CERT_DROP = ("signature", "transparency_log")


def _bundle(pricing, tmp_path: Path, with_cost: bool = True) -> Path:
    d = tmp_path / "material"
    d.mkdir()
    _spec, _man, src_p, prices_p, trace_p, man_p = v1b._material(
        pricing, d, with_cost=with_cost)
    v1b._certify(d, src_p, prices_p, trace_p, man_p, flag=False)
    b = tmp_path / "bundle"
    b.mkdir()
    for n in ("conformance.json", "trace.json", "manifest.json"):
        (b / n).write_bytes((d / n).read_bytes())
    return b


def _load(b: Path, n: str) -> dict:
    return json.loads((b / n).read_text(encoding="utf-8"))


def _rewrite(b: Path, trace: dict | None = None, cert_edit=None,
             trace_text=None) -> None:
    tkey = Ed25519PrivateKey.generate()
    ckey = Ed25519PrivateKey.generate()
    if trace is not None:
        _sign(trace, TRACE_DROP, tkey)
        text = trace_text(trace) if trace_text else json.dumps(trace)
        (b / "trace.json").write_text(text, encoding="utf-8")
    tr = json.loads((b / "trace.json").read_text(encoding="utf-8")) \
        if trace is None else trace
    cert = _load(b, "conformance.json")
    cert["trace_sha256"] = hashlib.sha256(
        _body(tr, TRACE_DROP)).hexdigest()
    if cert_edit:
        cert_edit(cert)
    _sign(cert, CERT_DROP, ckey)
    (b / "conformance.json").write_text(json.dumps(cert), encoding="utf-8")


def _run(b: Path, name: str):
    v = b / "verify_conformance_offline.py"
    v.write_text(_texts()[name], encoding="utf-8")
    p = subprocess.run([sys.executable, "-B", str(v)] + ARGS[name]
                       + conformance_pin_args(b),
                       capture_output=True, text=True, cwd=str(b))
    return p.returncode, p.stdout, p.stderr


# ------------------------------------------------------------------ Q4


def _over_trace(trace: dict) -> dict:
    t = copy.deepcopy(trace)
    ev0 = t["events"][0]
    t["events"] = []
    for i in range(6):
        e = dict(ev0, seq=i, tick=i, soul="Analyst",
                 input_tokens=10 ** 7, output_tokens=10 ** 6)
        t["events"].append(e)
    return t


@pytest.mark.parametrize("name", TEXTS)
def test_q4a_forged_certificate_over_an_expensive_trace(pricing, tmp_path,
                                                        name):
    b = _bundle(pricing, tmp_path)
    _rewrite(b, trace=_over_trace(_load(b, "trace.json")))
    cert = _load(b, "conformance.json")
    assert cert["conformant"] is True and cert["bound_transfer_ok"] is True
    rc, out, err = _run(b, name)
    assert rc == 1, (out, err)
    assert "recomputed" in err, err


@pytest.mark.parametrize("name", TEXTS)
def test_q4b_recorded_value_disagreeing_with_recomputation(pricing,
                                                          tmp_path, name):
    b = _bundle(pricing, tmp_path)

    def lie(cert):
        cert["bound_transfer_ok"] = False
        cert["conformant"] = False

    _rewrite(b, cert_edit=lie)
    rc, out, err = _run(b, name)
    assert rc == 1, (out, err)
    assert "disagrees with recomputation" in err, err


# ------------------------------------------------------------------ Q5

GATED_SRC = (
    "world G {\n"
    "  cost_cap: 0.10 USD\n"
    "  max_ticks: 4\n"
    "  events { Escalate }\n"
    "  law gated(Escalate)\n"
    "}\n"
    "message Escalate { v: string }\n"
    "soul A {\n"
    "  mind: claude-sonnet-4-6 @ Tier1\n"
    "  tokens: input = 100 output = 50\n"
    "  instinct {\n"
    "    speak Escalate(v: \"x\")\n"
    "  }\n"
    "  heal { on error => retry(2, error) }\n"
    "}\n"
)
PIN_DAY = date(2026, 10, 27)


def _world(src: str, table, today):
    spec = emit_smt(parse_nous(src), table, source_text=src, today=today)
    man = manifest_from_verify(
        VerifyResult(verdict="proven", spec=spec, solver_name="z3",
                     solver_version="z3 4.16.0", elapsed_ms=1,
                     timestamp_utc="2026-05-26T00:00:00+00:00"),
        nous_version="test",
    )
    doc = cf.cost_certificate_from_smtspec(spec)
    man = dataclasses.replace(man, cost_farkas_sha256=cf.cost_farkas_sha256(doc))
    return spec, man


def _ev(seq, tick, soul, kind="llm_call", it=0, ot=0, tc="0", action=None):
    return {"seq": seq, "tick": tick, "soul": soul, "kind": kind,
            "input_tokens": it, "output_tokens": ot, "tool_cost": tc,
            "action": action, "authorization": None,
            "timestamp_utc": "2026-05-25T00:00:00Z"}


def _trace_doc(spec, events, **extra) -> dict:
    doc = {"nous_version": "test", "world_name": spec.world_name,
           "source_sha256": spec.source_sha256,
           "smt_spec_sha256": spec.sha256(),
           "pricing_sha256": spec.pricing_sha256,
           "trace_schema_version": 1, "events": events}
    doc.update(extra)
    return doc


def _variants_floor(spec):
    g = [_ev(0, 0, "Analyst", it=900, ot=400),
         _ev(1, 1, "Trader", it=300, ot=150)]
    return {
        "a0_genuine": _trace_doc(spec, g),
        "a1_input_over": _trace_doc(spec, [_ev(0, 0, "Analyst", it=1001)]),
        "a2_output_over": _trace_doc(spec, [_ev(0, 0, "Trader", ot=201)]),
        "a3_calls_over": _trace_doc(spec, [
            _ev(i, t, "Analyst", it=10, ot=10)
            for i, t in enumerate((0, 0, 1, 2, 3, 4))]),
        "a4_tick_over": _trace_doc(spec, [_ev(0, 5, "Analyst", it=1)]),
        "a5_price_over_cap": _trace_doc(spec, [
            _ev(0, 0, "Analyst", it=10 ** 6, ot=10 ** 6)]),
        "a6_unknown_soul": _trace_doc(spec, [_ev(0, 0, "Ghost", it=1)]),
        "a7_priced_tool": _trace_doc(spec, [
            _ev(0, 0, "Analyst", kind="tool_call", tc="0.01")]),
        "a8_unlabelled_tool_no_events": _trace_doc(spec, [
            _ev(0, 0, "Analyst", kind="tool_call")]),
        "a9_message": _trace_doc(spec, g + [
            _ev(2, 2, "Trader", kind="message")]),
        "a10_smt_sha_mismatch": dict(_trace_doc(spec, g),
                                     smt_spec_sha256="0" * 64),
        "a11_trust_inconsistent": _trace_doc(
            spec, g, evidence_kind="witnessed_run"),
        "a12_trust_consistent": _trace_doc(
            spec, g, evidence_kind="witnessed_run", cost_binding="realized"),
        "a13_unknown_kind": _trace_doc(spec, [
            _ev(0, 0, "Analyst", kind="teleport")]),
        "a14_empty": _trace_doc(spec, []),
        "a15_trust_full": _trace_doc(
            spec, g, evidence_kind="witnessed_run", cost_binding="realized",
            provider_token_integrity="unattested"),
        "a16_at_cap": _trace_doc(spec, [
            _ev(0, 0, "Analyst", it=500000)]),
    }


def _variants_gated(spec):
    return {
        "b0_llm_and_gated": _trace_doc(spec, [
            _ev(0, 0, "A", it=100, ot=50),
            _ev(1, 1, "A", kind="gated_action", action="Escalate")]),
        "b1_tool_declared": _trace_doc(spec, [
            _ev(0, 0, "A", kind="tool_call", action="Escalate")]),
        "b2_tool_undeclared": _trace_doc(spec, [
            _ev(0, 0, "A", kind="tool_call", action="Nope")]),
        "b3_tool_unlabelled": _trace_doc(spec, [
            _ev(0, 0, "A", kind="tool_call")]),
        "b4_gated_undeclared": _trace_doc(spec, [
            _ev(0, 0, "A", kind="gated_action", action="Other")]),
        "b5_gated_converse": _trace_doc(spec, [
            _ev(0, 0, "A", kind="message", action="Escalate")]),
    }


SCOPE = ("binding_ok", "surface_ok", "assumption_discharge_ok",
         "bound_transfer_ok")


def _online(trace_doc, man, spec, table):
    try:
        env = TraceEnvelope.model_validate(trace_doc)
        d = verify_conformance(env, man, spec, table)
    except (ConformancePreconditionError, ValueError) as exc:
        return ("refused", str(exc))
    return ("ok", {k: getattr(d, k) for k in SCOPE},
            Fraction(Decimal(d.realized_total)))


def test_q5_offline_equals_online_over_variants(pricing):
    assert hasattr(conformance, "_conf_rc_obligations"), \
        "no _conf_rc_obligations in conformance.py"
    off = conformance._conf_rc_obligations
    shipped = load_pricing(REPO / "pricing" / "defaults.toml")
    cases = []
    spec_a, man_a = _world(v1b.s97._SOULED_SOURCE, pricing, v1b.s97.TODAY)
    cases += [(k, v, man_a, spec_a, pricing)
              for k, v in _variants_floor(spec_a).items()]
    spec_b, man_b = _world(GATED_SRC, shipped, PIN_DAY)
    cases += [(k, v, man_b, spec_b, shipped)
              for k, v in _variants_gated(spec_b).items()]
    seen = 0
    for label, tdoc, man, spec, table in cases:
        on = _online(tdoc, man, spec, table)
        mdoc = dataclasses.asdict(man)
        got = off(mdoc, tdoc, spec.canonical_str())
        assert got[0] == on[0], (label, on, got)
        if on[0] == "ok":
            assert got[1] == on[1], (label, on, got)
            assert got[2] == on[2], (label, on[2], got[2])
        seen += 1
        if label == "a16_at_cap":
            assert on[1]["bound_transfer_ok"] is True, on
            assert on[2] == Fraction(1, 2), on
    assert seen == 23


# ------------------------------------------------------------------ Q6

STRICT = {
    "float": lambda t: t.replace('"input_tokens": 900,',
                                 '"input_tokens": 900.0,', 1),
    "nan": lambda t: t.replace('"input_tokens": 900,',
                               '"input_tokens": NaN,', 1),
    "non_ascii_digit": lambda t: t.replace(
        '"input_tokens": 900,', '"input_tokens": \u0669\u0660\u0660,', 1),
    "duplicate_key": lambda t: t.replace(
        '"input_tokens": 900,', '"input_tokens": 900, "input_tokens": 900,',
        1),
}


@pytest.mark.parametrize("name", TEXTS)
@pytest.mark.parametrize("kind", sorted(STRICT))
def test_q6_strict_trace_refusals(pricing, tmp_path, name, kind):
    b = _bundle(pricing, tmp_path)
    tr = _load(b, "trace.json")
    if kind == "float":
        tr["events"][0]["input_tokens"] = 900.0
    if kind == "nan":
        tr["events"][0]["input_tokens"] = float("nan")

    def text(doc):
        t = json.dumps(doc)
        if kind in ("non_ascii_digit", "duplicate_key"):
            t2 = STRICT[kind](t)
            assert t2 != t
            return t2
        return t

    _rewrite(b, trace=tr, trace_text=text)
    rc, out, err = _run(b, name)
    assert rc == 1, (out, err)
    assert "trace.json refused" in err, err


# ------------------------------------------------------------------ Q7


@pytest.mark.parametrize("name", TEXTS)
def test_q7_no_canon_is_named_not_recomputed(pricing, tmp_path, name):
    b = _bundle(pricing, tmp_path, with_cost=False)
    assert "obligations_canon" not in _load(b, "conformance.json")
    rc, out, err = _run(b, name)
    assert "NOT RECOMPUTED: no spec canon in the certificate" in out, out
    assert "RECOMPUTED (" not in out


# ------------------------------------------------------------------ Q8

PROBE = (
    "import runpy, sys\n"
    "sys.argv = sys.argv[1:]\n"
    "try:\n"
    "    runpy.run_path(sys.argv[0], run_name='__main__')\n"
    "except SystemExit:\n"
    "    pass\n"
    "bad = sorted(m for m in sys.modules\n"
    "             if m.split('.')[0] in %r)\n"
    "print('BANNED_MODULES', bad)\n" % (BANNED,)
)


@pytest.mark.parametrize("name", TEXTS)
def test_q8_no_banned_module_after_a_recomputing_run(pricing, tmp_path,
                                                      name):
    b = _bundle(pricing, tmp_path)
    v = b / "verify_conformance_offline.py"
    v.write_text(_texts()[name], encoding="utf-8")
    probe = tmp_path / "probe.py"
    probe.write_text(PROBE, encoding="utf-8")
    p = subprocess.run([sys.executable, "-B", str(probe), str(v)]
                       + ARGS[name] + conformance_pin_args(b),
                       capture_output=True, text=True,
                       cwd=str(b))
    assert "RECOMPUTED (" in p.stdout, (p.stdout, p.stderr)
    assert "BANNED_MODULES []" in p.stdout, p.stdout


# ------------------------------------------------------------------ Q9


def test_q9_caps():
    for name in ("_conf_rc_load", "_conf_rc_parse_canon"):
        assert hasattr(conformance, name), "no " + name
    load = conformance._conf_rc_load
    big = b'{"a": "' + b"x" * (conformance._CONF_RC_MAX_BYTES + 1) + b'"}'
    assert load(big)[0] is None
    deep = b"[" * (conformance._CONF_RC_MAX_DEPTH + 1) + \
        b"]" * (conformance._CONF_RC_MAX_DEPTH + 1)
    assert load(deep)[0] is None
    canon = "\n".join((
        "CC:0.5|USD", "MT:5",
        "A:(assert (= cost_S_per_call (/ (+ (* " + "9" * 200
        + " 100) (* 2 50)) 1000000)))",
        "A:(assert (= cost_S_total (* cost_S_per_call 5)))",
        "A:(assert (= total_cost cost_S_total))",
    ))
    assert isinstance(conformance._conf_rc_parse_canon(canon), str)


# ----------------------------------------------- Q11, Q12 (addendum 1)

V2DIR = REPO / "website" / ".well-known" / "nous" / "vsa-vectors" / "v2"
SEED_T, SEED_C, SEED_V = (bytes(range(32, 64)), bytes(range(64, 96)),
                          bytes(range(96, 128)))
DISCLOSE = (
    "The VSA verifier checks that the certificate's recorded obligations "
    "are consistent with its verdict; it does not recompute them from "
    "trace.json. verify_conformance_offline.py, run on manifest.json, "
    "trace.json and conformance.json of this directory, recomputes the "
    "cost obligations."
)


def _forge_v2_expensive(d: Path) -> None:
    d.mkdir()
    for n in ("manifest.json", "trace.json", "conformance.json",
              "vsa.intoto.json", "cost.farkas.json", "coverage.farkas.json",
              "verify_vsa_offline.py"):
        (d / n).write_bytes((V2DIR / n).read_bytes())
    tr = _load(d, "trace.json")
    e0 = tr["events"][0]
    tr["events"] = [dict(e0, seq=i, tick=i % 4, input_tokens=10 ** 7,
                         output_tokens=10 ** 6) for i in range(4)]
    _sign(tr, TRACE_DROP, Ed25519PrivateKey.from_private_bytes(SEED_T))
    (d / "trace.json").write_text(json.dumps(tr), encoding="utf-8")
    cert = _load(d, "conformance.json")
    cert["trace_sha256"] = hashlib.sha256(_body(tr, TRACE_DROP)).hexdigest()
    _sign(cert, CERT_DROP, Ed25519PrivateKey.from_private_bytes(SEED_C))
    (d / "conformance.json").write_text(json.dumps(cert), encoding="utf-8")
    env = _load(d, "vsa.intoto.json")
    st = json.loads(base64.b64decode(env["payload"]))
    for ia in st["predicate"]["inputAttestations"]:
        if ia["uri"] == "trace.json":
            ia["digest"]["sha256"] = cert["trace_sha256"]
        if ia["uri"] == "conformance.json":
            ia["digest"]["sha256"] = hashlib.sha256(
                _body(cert, CERT_DROP)).hexdigest()
    p = json.dumps(st, sort_keys=True, separators=(",", ":")).encode()
    t = b"application/vnd.in-toto+json"
    pae = b"DSSEv1 %d %s %d %s" % (len(t), t, len(p), p)
    env["payload"] = _b64(p)
    env["signatures"][0]["sig"] = _b64(
        Ed25519PrivateKey.from_private_bytes(SEED_V).sign(pae))
    (d / "vsa.intoto.json").write_text(json.dumps(env), encoding="utf-8")


@pytest.mark.parametrize("name", TEXTS)
def test_q11_v2_vsa_passes_conformance_recompute_refuses(tmp_path, name):
    d = tmp_path / "forged"
    _forge_v2_expensive(d)
    p = subprocess.run([sys.executable, "-B", "verify_vsa_offline.py"],
                       capture_output=True, text=True, cwd=str(d))
    assert p.returncode == 0 and "VERDICT: PASS" in p.stdout, p.stderr
    rc, out, err = _run(d, name)
    assert rc == 1, (out, err)
    assert "recomputed" in err, err


def test_q12_v2_index_and_docs_disclose_the_composition():
    idx_raw = (V2DIR / "index.json").read_bytes()
    idx = json.loads(idx_raw)
    assert DISCLOSE in idx["boundary"]
    side = (V2DIR / "index.json.sha256").read_text(encoding="utf-8")
    assert side.split() == [hashlib.sha256(idx_raw).hexdigest(),
                            "index.json"]
    docs = (REPO / "docs" / "VSA_CONFORMANCE_VECTORS.md").read_text(
        encoding="utf-8")
    assert "does not recompute them from" in docs
    assert "verify_conformance_offline.py" in docs


# ------------------------------------------------------------------ Q13
# Addendum 2 (f5ec3b8c...): grammar NAME admits U+0370..U+03FF, and the
# runner writes trace.json with ensure_ascii=False.

GA = "\u0391\u03bd\u03b1\u03bb\u03c5\u03c4\u03b7\u03c2"
GT = "\u0388\u03bc\u03c0\u03bf\u03c1\u03bf\u03c2"
GREEK_SRC = (
    "world Floor {\n"
    "    cost_cap: 0.50 USD\n"
    "    max_ticks: 5\n"
    "}\n"
    "soul " + GA + " {\n"
    "    mind: m1 @ Tier1\n"
    "    tokens: input=1000 output=500\n"
    "}\n"
    "soul " + GT + " {\n"
    "    mind: m2 @ Tier1\n"
    "    tokens: input=400 output=200\n"
    "}\n"
)


def _greek_bundle(pricing, tmp_path: Path) -> Path:
    s97 = v1b.s97
    d = tmp_path / "gmat"
    d.mkdir()
    spec, man = _world(GREEK_SRC, pricing, s97.TODAY)
    env = TraceEnvelope(
        nous_version="test", world_name=spec.world_name,
        source_sha256=spec.source_sha256, smt_spec_sha256=spec.sha256(),
        pricing_sha256=spec.pricing_sha256,
        events=[s97._event(0, 0, GA, it=900, ot=400),
                s97._event(1, 1, GT, it=300, ot=150)])
    tr = v1b.sign_trace(env, Ed25519PrivateKey.generate())
    raw = json.dumps(tr.persisted_dict(), indent=2,
                     ensure_ascii=False).encode("utf-8")
    assert not raw.isascii()
    (d / "trace.json").write_bytes(raw)
    (d / "source.nous").write_text(GREEK_SRC, encoding="utf-8")
    (d / "pricing.toml").write_text(s97.PRICING_TOML, encoding="utf-8")
    priv, pub, _ = v1b.load_or_create_keypair(d / "m.key")
    (d / "manifest.json").write_text(
        v1b.manifest_json(man, v1b.sign_manifest(man, priv), pub),
        encoding="utf-8")
    v1b._certify(d, d / "source.nous", d / "pricing.toml",
                 d / "trace.json", d / "manifest.json", flag=False)
    b = tmp_path / "bundle"
    b.mkdir()
    for n in ("conformance.json", "trace.json", "manifest.json"):
        (b / n).write_bytes((d / n).read_bytes())
    return b


def test_q13a_greek_canon_parses(pricing):
    spec, _man = _world(GREEK_SRC, pricing, v1b.s97.TODAY)
    got = conformance._conf_rc_parse_canon(spec.canonical_str())
    assert isinstance(got, dict), got
    assert sorted(got["souls"]) == sorted([GA, GT])


def test_q13b_greek_offline_equals_online(pricing):
    spec, man = _world(GREEK_SRC, pricing, v1b.s97.TODAY)
    variants = {
        "g0_genuine": _trace_doc(spec, [_ev(0, 0, GA, it=900, ot=400),
                                        _ev(1, 1, GT, it=300, ot=150)]),
        "g1_input_over": _trace_doc(spec, [_ev(0, 0, GA, it=1001)]),
        "g2_at_cap": _trace_doc(spec, [_ev(0, 0, GA, it=500000)]),
    }
    mdoc = dataclasses.asdict(man)
    for label, tdoc in variants.items():
        on = _online(tdoc, man, spec, pricing)
        got = conformance._conf_rc_obligations(mdoc, tdoc,
                                               spec.canonical_str())
        assert on[0] == "ok", (label, on)
        assert got[0] == "ok" and got[1] == on[1] and got[2] == on[2], \
            (label, on, got)


def test_q13c_utf8_inside_a_string_loads():
    raw = json.dumps({"soul": GA, "n": 1}, ensure_ascii=False).encode()
    doc, why = conformance._conf_rc_load(raw)
    assert doc == {"soul": GA, "n": 1}, why


def test_q13e_non_ascii_digit_outside_a_string_refuses():
    raw = '{"n": \u0663}'.encode("utf-8")
    doc, why = conformance._conf_rc_load(raw)
    assert doc is None and why


@pytest.mark.parametrize("name", TEXTS)
def test_q13d_greek_bundle_end_to_end(pricing, tmp_path, name):
    b = _greek_bundle(pricing, tmp_path)
    rc, out, err = _run(b, name)
    assert rc == 0, (out, err)
    assert "RECOMPUTED (" in out, out
