"""NT-GATE-1 V1: re-derive the cost system before grading it offline.

Red tests, written before any V1 code (V1_PREDICTIONS.md, sha256
7a8bd534...). Each offline verifier text that grades cost.farkas.json
must re-derive the system from the signed spec canon and compare it
before it may print PROVEN. Today no text does.

# __nt_v1_red_tests_v1__
"""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import date
from fractions import Fraction
from pathlib import Path

import pytest

import cost_farkas as cf
import dossier
import manifest as mf
import pricing
import smt_emit
import vsa_verifier
from cli_verify import cmd_verify
from dossier import build_dossier
from parser import parse_nous

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "templates" / "cost_cap_with_souls.nous"
SERVED_VSA = (
    "website/.well-known/nous/vsa-vectors/v1/verify_vsa_offline.py"
)
# __nt_w_v2_census_v1__ ruling (a), 2026-10-27: v2 carries the wired
# verifier; it grades cost and so must re-derive like the template.
SERVED_VSA_V2 = (
    "website/.well-known/nous/vsa-vectors/v2/verify_vsa_offline.py"
)
LEG = "_cost_rederive_leg"

EXPECTED_TEXTS = (
    "dossier.VERIFY_OFFLINE_PY",
    "dossier.VERIFY_OFFLINE_PY_WITH_REKOR",
    "dossier.VERIFY_OFFLINE_PY_CHAIN",
    "dossier.VERIFY_OFFLINE_PY_BUNDLE",
    "dossier.VERIFY_OFFLINE_PY_FARKAS",
    "dossier.VERIFY_OFFLINE_PY_COVERAGE",
    "dossier.VERIFY_OFFLINE_PY_CHAIN_BUNDLE",
    "dossier.build_chain_net_verifier()",
    "vsa_verifier.VSA_VERIFY_OFFLINE_PY",
    "served:" + SERVED_VSA_V2,
)
# Ruling (i), 2026-10-27: the published v1 vector is frozen as published.
# Its verifier predates re-derivation and stays so; index.json says so and
# names v2 for the check. It is pinned here, not required to re-derive.
FROZEN_TEXTS = {
    "served:" + SERVED_VSA:
        "aaa8ee347717def035d7c7fc4248fc09e0be1db8c5f627b8e7bd8e0a5795ecba",
}
EXPECTED_PROVEN_FILES = {"dossier.py", "vsa_verifier.py", SERVED_VSA,
                         SERVED_VSA_V2}


def _fold(node, env):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return env.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a, b = _fold(node.left, env), _fold(node.right, env)
        return None if a is None or b is None else a + b
    return None


def _dossier_constants() -> dict:
    tree = ast.parse((REPO / "dossier.py").read_text(encoding="utf-8"))
    env: dict = {}
    out: dict = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        tgt = node.targets[0] if isinstance(node, ast.Assign) \
            else node.target
        name = getattr(tgt, "id", "")
        if not name or node.value is None:
            continue
        val = _fold(node.value, env)
        if val is not None:
            env[name] = val
        if name.startswith("VERIFY_OFFLINE_PY"):
            assert val is not None, name + " did not fold to a string"
            out["dossier." + name] = val
    return out


def _texts() -> dict:
    texts = _dossier_constants()
    texts["dossier.build_chain_net_verifier()"] = (
        dossier.build_chain_net_verifier()
    )
    texts["vsa_verifier.VSA_VERIFY_OFFLINE_PY"] = (
        vsa_verifier.VSA_VERIFY_OFFLINE_PY
    )
    for served in (SERVED_VSA, SERVED_VSA_V2):
        p = REPO / served
        texts["served:" + served] = (
            p.read_text(encoding="utf-8") if p.is_file() else None
        )
    return texts


def _text(name: str) -> str:
    text = _texts()[name]
    assert text is not None, name + ": absent"
    return text


def _grades_cost(text) -> bool:
    return (text is not None and "cost.farkas" in text
            and "PROVEN offline" in text)


def _load_text(text: str, tmp: Path) -> dict:
    ns: dict = {"__name__": "nt_v1_text", "__file__": str(tmp / "v.py")}
    exec(compile(text, "nt_v1_text", "exec"), ns)
    return ns


# ---------------------------------------------------------------- P1


def test_p1_census_of_cost_grading_texts():
    texts = _texts()
    grading = sorted(k for k, v in texts.items() if _grades_cost(v))
    assert grading == sorted(EXPECTED_TEXTS + tuple(FROZEN_TEXTS))
    r = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z", "--cached", "--others",
         "--exclude-standard", "--", "*.py"],
        capture_output=True, check=True,
    )
    found = set()
    for rel in r.stdout.decode("utf-8").split("\0"):
        if not rel or rel.startswith("tests/"):
            continue
        if b"PROVEN offline" in (REPO / rel).read_bytes():
            found.add(rel)
    assert found == EXPECTED_PROVEN_FILES


# ------------------------------------------------------------ material


@pytest.fixture(scope="module")
def material(tmp_path_factory):
    import dated_prices
    with pytest.MonkeyPatch.context() as mp:
        dated_prices.use_dated_shipped_prices(
            tmp_path_factory.mktemp("nt_v1_prices"), mp
        )
        work = tmp_path_factory.mktemp("nt_v1_run")
        src = work / "source.nous"
        shutil.copy2(TEMPLATE, src)
        key = work / "signing.key"

        class Args:
            file = str(src)
            smt = True
            prices = None
            timeout_ms = 30000
            no_manifest = False
            manifest_out = None
            key_path = str(key)
            smt_margin = 0
            no_lint = True
            lint_strict = False
            lint_error_on = None

        assert cmd_verify(Args()) == 0
        man_path = src.with_suffix(".manifest.json")
        man = json.loads(man_path.read_text(encoding="utf-8"))
        cost_doc = json.loads(
            (work / "cost.farkas.json").read_text(encoding="utf-8")
        )
        day = date.fromisoformat(man["timestamp_utc"][:10])
        text = src.read_text(encoding="utf-8")
        spec = smt_emit.emit_smt(
            parse_nous(text), pricing.load_pricing(None),
            source_text=text, today=day, margin_pct=0,
        )
        assert spec.sha256() == man["smt_spec_sha256"], (
            "fixture: re-emitted spec does not match the manifest"
        )
        double = cf.extract_cost_certificate(
            souls=cf.souls_from_smtspec(spec),
            max_ticks=int(spec.max_ticks),
            cost_cap=Fraction(str(spec.cost_cap_amount)) * 2,
            margin_pct=0,
        )
        assert double is not None
        out = work / "dossier"
        built = build_dossier(src, manifest=man_path, output=out)
        yield {
            "work": work, "src": src, "man_path": man_path, "man": man,
            "cost_doc": cost_doc, "canon": spec.canonical_str(),
            "double": double, "key": key, "dossier": out,
            "files": tuple(built.files),
        }


TRIVIAL = {"constraints": [{"coeffs": {"": "1"}, "strict": False}],
           "multipliers": ["1"]}


# ------------------------------------------------------------ P2, P3


@pytest.mark.parametrize("name", EXPECTED_TEXTS)
def test_p2_text_defines_rederive_leg(name, tmp_path):
    ns = _load_text(_text(name), tmp_path)
    assert LEG in ns, name + ": no " + LEG + " (grades the carried system)"


@pytest.mark.parametrize("name", EXPECTED_TEXTS)
def test_p3_rederive_leg_behaviour(name, tmp_path, material):
    ns = _load_text(_text(name), tmp_path)
    assert LEG in ns, name + ": no " + LEG + " (grades the carried system)"
    leg = ns[LEG]
    man = dict(material["man"])
    canon = material["canon"]
    genuine = material["cost_doc"]

    def sha(s):
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    ok, why = leg(man, TRIVIAL, canon)
    assert ok is False, "c1 trivial certificate accepted: " + why
    ok, why = leg(man, material["double"], canon)
    assert ok is False, "c2 certificate for cap x 2 accepted: " + why
    ok, why = leg(man, genuine, canon)
    assert ok is True, "c3 genuine certificate refused: " + why
    assert "MT:5" in canon
    ok, why = leg(man, genuine, canon.replace("MT:5", "MT:6"))
    assert ok is False, "c4 canon not bound to manifest sha: " + why
    odd = canon + "\nA:(assert (= cost_X_per_call (exp 2)))"
    ok, why = leg(dict(man, smt_spec_sha256=sha(odd)), genuine, odd)
    assert ok is False, "c5 unknown A: shape accepted: " + why
    ok, why = leg(dict(man, cost_cap_usd="1.00"), genuine, canon)
    assert ok is False, "c6 manifest cap not compared: " + why
    ok, why = leg(man, genuine, None)
    assert ok is False, "c7 absent canon accepted: " + why
    # c8 (addendum 2): a canon cheaper than the signed one, with a
    # certificate re-derived for it; only the sha bind can refuse it.
    lines = canon.split("\n")
    hit = [i for i, ln in enumerate(lines)
           if ln.startswith("A:(assert (= cost_Trader_per_call")]
    assert len(hit) == 1 and " 500)" in lines[hit[0]]
    lines[hit[0]] = lines[hit[0]].replace(" 500)", " 1)", 1)
    cheap = "\n".join(lines)
    per_call, mt, cap, _m = cf._cost_rederive_parse(cheap)
    forged = cf.extract_cost_certificate(
        souls=[cf.SoulCost(name=k, per_call=v) for k, v in per_call.items()],
        max_ticks=mt, cost_cap=cap, margin_pct=0,
    )
    assert forged is not None and forged != genuine
    ok, why = leg(man, forged, cheap)
    assert ok is False, "c8 canon not bound to the signed sha: " + why


# -------------------------------------------------------- P4 to P8


def _copy_dossier(material, tmp_path, carry_canon: bool) -> Path:
    out = tmp_path / "d"
    shutil.copytree(material["dossier"], out)
    if carry_canon:
        # D3 enters the tests here only (V1_PREDICTIONS section 2).
        (out / "spec.canon").write_bytes(
            material["canon"].encode("utf-8")
        )
    elif (out / "spec.canon").exists():
        # Green: the producer now carries spec.canon; P7 tests absence.
        (out / "spec.canon").unlink()
    return out


def _forge_cost(material, out: Path, doc: dict) -> None:
    body = cf.cost_farkas_json_bytes(doc)
    (out / "cost.farkas.json").write_bytes(body)
    m, _sig, pub = mf.parse_manifest_json(
        (out / "manifest.json").read_text(encoding="utf-8")
    )
    m2 = dataclasses.replace(
        m, cost_farkas_sha256=hashlib.sha256(body).hexdigest()
    )
    priv, pub2, _ = mf.load_or_create_keypair(material["key"])
    assert mf.public_key_b64(pub2) == mf.public_key_b64(pub)
    sig2 = mf.sign_manifest(m2, priv)
    (out / "manifest.json").write_text(
        mf.manifest_json(m2, sig2, pub), encoding="utf-8"
    )


def _run(out: Path, hide_z3: bool = False):
    v = str(out / "verify_offline.py")
    if hide_z3:
        cmd = [sys.executable, "-I", "-B", "-c",
               "import sys, runpy; sys.modules['z3'] = None; "
               "sys.argv = [sys.argv[1]]; "
               "runpy.run_path(sys.argv[0], run_name='__main__')", v]
    else:
        cmd = [sys.executable, "-I", "-B", v]
    return subprocess.run(cmd, cwd=str(out), capture_output=True,
                          text=True, timeout=120)


def test_p4_e2e_trivial_forgery_fails(material, tmp_path):
    out = _copy_dossier(material, tmp_path, carry_canon=True)
    _forge_cost(material, out, TRIVIAL)
    r = _run(out)
    assert "PROVEN offline" not in r.stdout, r.stdout
    assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)


def test_p5_e2e_double_cap_certificate_fails(material, tmp_path):
    out = _copy_dossier(material, tmp_path, carry_canon=True)
    _forge_cost(material, out, material["double"])
    r = _run(out)
    assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)


def test_p6_e2e_genuine_passes(material, tmp_path):
    out = _copy_dossier(material, tmp_path, carry_canon=True)
    r = _run(out)
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)


def test_p7_e2e_trivial_forgery_without_canon_never_proven(
        material, tmp_path):
    out = _copy_dossier(material, tmp_path, carry_canon=False)
    _forge_cost(material, out, TRIVIAL)
    r = _run(out)
    assert "PROVEN offline" not in r.stdout, r.stdout


def test_p8_e2e_genuine_passes_without_z3(material, tmp_path):
    out = _copy_dossier(material, tmp_path, carry_canon=True)
    r = _run(out, hide_z3=True)
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)


# ------------------------------------------- P9 to P12 (V1 green)

REGION_START = (
    "# --- cost rederive embed (shared text; canonical copy: "
    "cost_farkas.py) ---"
)
REGION_END = "# --- end cost rederive embed ---"


def _region(text: str):
    i = text.find(REGION_START)
    if i < 0:
        return None
    j = text.find(REGION_END, i)
    return None if j < 0 else text[i:j + len(REGION_END)]


def _canonical_region() -> str:
    text = (REPO / "cost_farkas.py").read_text(encoding="utf-8")
    assert text.count(REGION_START) == 1
    return _region(text)


@pytest.mark.parametrize("name", EXPECTED_TEXTS)
def test_p9_region_matches_canonical(name):
    text = _text(name)
    assert text.count(REGION_START) == 1, name + ": region count"
    assert _region(text) == _canonical_region(), name + ": region drifted"


@pytest.mark.parametrize("name", EXPECTED_TEXTS)
def test_p10_cost_branch_calls_the_leg(name):
    import re
    text = _text(name)
    assert "_cost_check_serialized(" not in text, name
    assert "_check_serialized(cost_doc)" not in text, name
    assert re.search(
        r"_cost_rederive_leg\(\s*manifest,\s*cost_doc,", text
    ), name + ": cost branch does not call " + LEG


def _variants(genuine: dict, double: dict) -> dict:
    import copy
    v = {"genuine": genuine, "trivial": TRIVIAL, "cap_x2": double}
    d = copy.deepcopy(genuine)
    d["multipliers"][0] = str(Fraction(d["multipliers"][0]) + 1)
    v["multiplier_changed"] = d
    d = copy.deepcopy(genuine)
    k = sorted(k for k in d["constraints"][0]["coeffs"] if k)[0]
    d["constraints"][0]["coeffs"][k] = "2"
    v["coefficient_changed"] = d
    d = copy.deepcopy(genuine)
    d["constraints"].pop(0)
    d["multipliers"].pop(0)
    v["row_dropped"] = d
    d = copy.deepcopy(genuine)
    d["constraints"].append(d["constraints"][0])
    d["multipliers"].append("0")
    v["row_duplicated"] = d
    d = copy.deepcopy(genuine)
    d["constraints"].reverse()
    d["multipliers"].reverse()
    v["rows_reversed"] = d
    d = copy.deepcopy(genuine)
    c = d["constraints"][-1]["coeffs"]
    c["total_cost"] = float(Fraction(c["total_cost"]))
    v["float_coefficient"] = d
    d = copy.deepcopy(genuine)
    d["constraints"][0]["coeffs"]["extra_var"] = "0"
    v["extra_variable"] = d
    v["not_a_dict"] = ["constraints"]
    return v


def test_p11_leg_equals_online_oracle(material):
    import coverage_farkas as cov
    text = material["src"].read_text(encoding="utf-8")
    day = date.fromisoformat(material["man"]["timestamp_utc"][:10])
    checked = 0
    for margin in (0, 10):
        spec = smt_emit.emit_smt(
            parse_nous(text), pricing.load_pricing(None),
            source_text=text, today=day, margin_pct=margin,
        )
        souls = cf.souls_from_smtspec(spec)
        genuine = cf.cost_certificate_from_smtspec(spec)
        double = cf.extract_cost_certificate(
            souls=souls, max_ticks=int(spec.max_ticks),
            cost_cap=Fraction(str(spec.cost_cap_amount)) * 2,
            margin_pct=margin,
        )
        assert genuine is not None and double is not None
        man = {
            "smt_spec_sha256": spec.sha256(),
            "cost_cap_usd": str(spec.cost_cap_amount),
            "max_ticks": int(spec.max_ticks),
            "safety_margin_pct": margin or None,
        }
        canon = spec.canonical_str()
        for label, doc in _variants(genuine, double).items():
            got = cf._cost_rederive_leg(man, doc, canon)[0]
            want = cf.check_serialized_cost(
                doc, souls, int(spec.max_ticks), spec.cost_cap_amount,
                margin,
            )
            assert got == want, (margin, label, got, want)
            if isinstance(doc, dict):
                assert cf._cost_rederive_grade(doc) == \
                    cov.check_serialized(doc), (margin, label)
            checked += 1
    assert checked == 22


def test_p12_producer_carries_spec_canon(material):
    out = material["dossier"]
    assert "spec.canon" in material["files"]
    body = (out / "spec.canon").read_bytes()
    assert hashlib.sha256(body).hexdigest() == \
        material["man"]["smt_spec_sha256"]
    assert body == material["canon"].encode("utf-8")


def test_p13_frozen_v1_verifier_is_pinned_and_declared():
    # Ruling (i): the frozen verifier keeps its bytes, and the published
    # index says what it does not do and how v1 reproduces.
    for name, want in FROZEN_TEXTS.items():
        got = hashlib.sha256(_texts()[name].encode("utf-8")).hexdigest()
        assert got == want, name
    index = json.loads(
        (REPO / SERVED_VSA).with_name("index.json").read_text(
            encoding="utf-8")
    )
    boundary = index["boundary"]
    assert "FROZEN:" in boundary
    assert "without re-deriving" in boundary
    assert "use v2" in boundary
    assert "LIMITATION" not in boundary
    note = index["reproduce"]["remint"]
    for term in ("c2d9680", "5.73.0", "2026-09-27", "2026-09-28",
                 "pin_clock.py", "was false because the digests depend on",
                 "price table", "code generator", "clock"):
        assert term in note, term
    assert "The bundle is the nine artifacts" in index["reproduce"]["scope"]
    assert len(index["artifacts"]) == 9
    vec = (REPO / SERVED_VSA).parent
    for key, entry in (("pinClock", index["reproduce"]["pinClock"]),
                       ("harness", index["reproduce"]["harness"]),
                       ("vectorSource", index["vectorSource"])):
        got = hashlib.sha256((vec / entry["name"]).read_bytes()).hexdigest()
        assert entry["sha256"] == got, key
        assert entry["name"] not in {a["name"] for a in index["artifacts"]}
