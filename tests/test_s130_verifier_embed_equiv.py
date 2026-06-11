"""
test_s130_verifier_embed_equiv.py -- U1 of the verifier-core integrity arc.

Differential equivalence gate between the SHIPPED offline-verifier embed
(the farkas + minilang checker carried verbatim inside the dossier.py
verifier templates) and the IN-PACKAGE production implementation
(coverage_farkas + coverage_minilang). The embed is the Trusted Computing
Base a third party actually runs; this test proves it decides admit/refuse
identically to the issuer, turning the "do not edit one copy without the
other" comment into an enforced invariant.

Three families:
  A. derivation-status equivalence over a corpus spanning in-fragment,
     out-of-fragment (bilinear / non-fragment comparison), and malformed
     source/threshold -- embed and production must agree on ok /
     refuse_minilang / refuse_farkas.
  B. checker-verdict equivalence over covered cases: an issuer-built bundle
     verifies PASS under both checkers (oracle: serialize_bundle emits iff
     coverage holds), and every forged mutant FAILS under both.
  C. _check_multipliers N-version: the two independently-written
     multiplier checkers agree on synthetic (constraints, multipliers).

Embed extracted by compile()+exec() of the template string into an
isolated namespace (no NOUS install used by the embed), mirroring
test_offline_verifier_v2_equiv.py. Test-only; ships nothing.
__s130_verifier_embed_equiv_v1__
"""
from __future__ import annotations

import copy
from fractions import Fraction
from typing import Any

import pytest

import coverage_farkas
import coverage_minilang
import dossier


EMBED_TEMPLATES = ("VERIFY_OFFLINE_PY_BUNDLE", "VERIFY_OFFLINE_PY_CHAIN_BUNDLE")

_EMBED_CACHE: dict = {}


def _embed_ns(template_attr: str) -> dict:
    if template_attr in _EMBED_CACHE:
        return _EMBED_CACHE[template_attr]
    src = getattr(dossier, template_attr)
    code = compile(src, "<embed:" + template_attr + ">", "exec")
    ns: dict = {"__file__": "<embed:" + template_attr + ">"}
    exec(code, ns)  # noqa: S102
    _EMBED_CACHE[template_attr] = ns
    return ns


def _src(signals: list) -> str:
    blocks = []
    for i, s in enumerate(signals):
        blocks.append(
            "policy p%d {\n  kind: monitor\n  signal: %s\n  action: block\n}\n"
            % (i, s)
        )
    return "\n".join(blocks)


COVERED = [
    ("single", _src(["amount > 500"]), "amount > 1000"),
    ("or2", _src(["amount > 500", "score > 80"]),
     "amount > 1000 || score > 90"),
    ("boundary", _src(["amount >= 1000"]), "amount >= 1000"),
    ("scaled", _src(["amount > 400"]), "2 * amount > 1000"),
]

OOF_FARKAS = [
    ("bilinear", _src(["amount > 500"]), "amount * score > 1000"),
    ("eqop", _src(["amount > 500"]), "amount == 1000"),
]

REFUSE_MINILANG = [
    ("trailing", _src(["amount > 500"]), "amount > 1000 extra"),
    ("malformed_src",
     "policy p0 {\n  kind: monitor\n  signal: amount > 500\n"
     "  action: block\n", "amount > 1000"),
]

ALL_CASES = (
    [(n, s, t, "ok") for (n, s, t) in COVERED]
    + [(n, s, t, "refuse_farkas") for (n, s, t) in OOF_FARKAS]
    + [(n, s, t, "refuse_minilang") for (n, s, t) in REFUSE_MINILANG]
)


def _prod_derive(source: str, threshold: str) -> "tuple[str, Any]":
    try:
        t_ast = coverage_minilang.ml_parse(threshold)
        blk = coverage_minilang.ml_scan_blocking_signals(source)
    except coverage_minilang.MinilangError:
        return ("refuse_minilang", None)
    try:
        disjuncts = coverage_farkas._gap_disjuncts(
            t_ast, blk, coverage_farkas.DISJUNCT_BOUND
        )
        derived: dict = {}
        for comps in disjuncts:
            constraints, _system = coverage_farkas._canon_system(comps)
            derived[coverage_farkas._canon_json(constraints)] = constraints
    except coverage_farkas.FarkasError:
        return ("refuse_farkas", None)
    return ("ok", (t_ast, blk, derived))


def _embed_derive(ns: dict, source: str, threshold: str) -> "tuple[str, Any]":
    try:
        derived = ns["derive_disjunct_constraints"](source, threshold)
    except ns["MinilangError"]:
        return ("refuse_minilang", None)
    except ns["FarkasError"]:
        return ("refuse_farkas", None)
    return ("ok", derived)


@pytest.mark.parametrize("template_attr", EMBED_TEMPLATES)
def test_embed_compiles_and_exposes_entrypoints(template_attr: str) -> None:
    ns = _embed_ns(template_attr)
    for name in (
        "derive_disjunct_constraints",
        "check_bundle_against_derived",
        "ml_parse",
        "ml_scan_blocking_signals",
        "_check_multipliers",
        "MinilangError",
        "FarkasError",
    ):
        assert name in ns, template_attr + " embed missing " + name


@pytest.mark.parametrize("template_attr", EMBED_TEMPLATES)
@pytest.mark.parametrize(
    "name,source,threshold,expected",
    ALL_CASES,
    ids=[c[0] for c in ALL_CASES],
)
def test_derivation_status_equivalence(
    template_attr: str,
    name: str,
    source: str,
    threshold: str,
    expected: str,
) -> None:
    ns = _embed_ns(template_attr)
    prod_status, _prod = _prod_derive(source, threshold)
    embed_status, _embed = _embed_derive(ns, source, threshold)
    assert prod_status == expected, (
        name + ": production status " + prod_status + " != " + expected
    )
    assert embed_status == prod_status, (
        name + ": embed status " + embed_status
        + " != production status " + prod_status
    )


@pytest.mark.parametrize("template_attr", EMBED_TEMPLATES)
@pytest.mark.parametrize(
    "name,source,threshold",
    COVERED,
    ids=[c[0] for c in COVERED],
)
def test_covered_bundle_passes_both_checkers(
    template_attr: str,
    name: str,
    source: str,
    threshold: str,
) -> None:
    ns = _embed_ns(template_attr)
    t_ast = coverage_minilang.ml_parse(threshold)
    blk = coverage_minilang.ml_scan_blocking_signals(source)
    doc = coverage_farkas.serialize_bundle(t_ast, blk, threshold_expr=threshold)

    prod_ok = coverage_farkas.check_serialized_bundle(doc, t_ast, blk)
    assert prod_ok is True, name + ": production rejected its own bundle"

    embed_status, embed_derived = _embed_derive(ns, source, threshold)
    assert embed_status == "ok", name + ": embed derivation refused a covered case"
    embed_ok, reason = ns["check_bundle_against_derived"](doc, embed_derived)
    assert embed_ok is True, name + ": embed rejected a valid bundle: " + reason


def _m_drop(doc: dict) -> dict:
    d = copy.deepcopy(doc)
    if d["certs"]:
        d["certs"] = d["certs"][1:]
    return d


def _m_dup(doc: dict) -> dict:
    d = copy.deepcopy(doc)
    if d["certs"]:
        d["certs"].append(copy.deepcopy(d["certs"][0]))
    return d


def _m_neg_mult(doc: dict) -> dict:
    d = copy.deepcopy(doc)
    if d["certs"] and d["certs"][0]["multipliers"]:
        d["certs"][0]["multipliers"][0] = "-1"
    return d


def _m_corrupt_constraint(doc: dict) -> dict:
    d = copy.deepcopy(doc)
    if d["certs"] and d["certs"][0]["constraints"]:
        c = d["certs"][0]["constraints"][0]
        co = dict(c["coeffs"])
        co[""] = str(Fraction(co.get("", "0")) + 1)
        c["coeffs"] = co
    return d


def _m_surplus(doc: dict) -> dict:
    d = copy.deepcopy(doc)
    if d["certs"]:
        extra = copy.deepcopy(d["certs"][0])
        co = dict(extra["constraints"][0]["coeffs"])
        co[""] = str(Fraction(co.get("", "0")) + 99)
        extra["constraints"][0]["coeffs"] = co
        d["certs"].append(extra)
    return d


MUTATORS = [
    ("drop", _m_drop),
    ("dup", _m_dup),
    ("neg_mult", _m_neg_mult),
    ("corrupt_constraint", _m_corrupt_constraint),
    ("surplus", _m_surplus),
]


@pytest.mark.parametrize("template_attr", EMBED_TEMPLATES)
@pytest.mark.parametrize("mut_name,mutator", MUTATORS, ids=[m[0] for m in MUTATORS])
@pytest.mark.parametrize(
    "name,source,threshold",
    COVERED,
    ids=[c[0] for c in COVERED],
)
def test_forged_mutations_fail_both_checkers(
    template_attr: str,
    mut_name: str,
    mutator: Any,
    name: str,
    source: str,
    threshold: str,
) -> None:
    ns = _embed_ns(template_attr)
    t_ast = coverage_minilang.ml_parse(threshold)
    blk = coverage_minilang.ml_scan_blocking_signals(source)
    doc = coverage_farkas.serialize_bundle(t_ast, blk, threshold_expr=threshold)
    mdoc = mutator(doc)

    prod_ok = coverage_farkas.check_serialized_bundle(mdoc, t_ast, blk)
    _status, embed_derived = _embed_derive(ns, source, threshold)
    embed_ok, _reason = ns["check_bundle_against_derived"](mdoc, embed_derived)

    label = name + "/" + mut_name
    assert prod_ok is False, label + ": production ACCEPTED a forged bundle"
    assert embed_ok is False, label + ": embed ACCEPTED a forged bundle"


SYNTH_MULT = [
    (
        "valid_contradiction",
        [{"coeffs": {"x": "1", "": "0"}, "strict": False},
         {"coeffs": {"x": "-1", "": "1"}, "strict": False}],
        ["1", "1"],
        True,
    ),
    (
        "valid_strict_zero_residual",
        [{"coeffs": {"x": "1", "": "0"}, "strict": True},
         {"coeffs": {"x": "-1", "": "0"}, "strict": False}],
        ["1", "1"],
        True,
    ),
    (
        "negative_multiplier",
        [{"coeffs": {"x": "1", "": "0"}, "strict": False},
         {"coeffs": {"x": "-1", "": "1"}, "strict": False}],
        ["-1", "1"],
        False,
    ),
    (
        "all_zero_multipliers",
        [{"coeffs": {"x": "1", "": "0"}, "strict": False},
         {"coeffs": {"x": "-1", "": "1"}, "strict": False}],
        ["0", "0"],
        False,
    ),
    (
        "non_cancelling",
        [{"coeffs": {"x": "1", "": "1"}, "strict": False}],
        ["1"],
        False,
    ),
    (
        "length_mismatch",
        [{"coeffs": {"x": "1", "": "0"}, "strict": False}],
        ["1", "1"],
        False,
    ),
]


@pytest.mark.parametrize("template_attr", EMBED_TEMPLATES)
@pytest.mark.parametrize(
    "name,constraints,multipliers,expected",
    SYNTH_MULT,
    ids=[c[0] for c in SYNTH_MULT],
)
def test_check_multipliers_nversion(
    template_attr: str,
    name: str,
    constraints: list,
    multipliers: list,
    expected: bool,
) -> None:
    ns = _embed_ns(template_attr)
    prod = coverage_farkas._check_multipliers(constraints, multipliers)
    embed = ns["_check_multipliers"](constraints, multipliers)
    assert prod == expected, name + ": production _check_multipliers wrong"
    assert embed == prod, (
        name + ": embed _check_multipliers " + str(embed)
        + " != production " + str(prod)
    )
