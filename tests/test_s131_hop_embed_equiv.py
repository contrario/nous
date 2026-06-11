"""S131 hop entry-point behavioral differential.

U1 (test_s130_verifier_embed_equiv.py) cross-checks the embed BUNDLE entry
point (check_bundle_against_derived) against production
(check_serialized_bundle) on a fixed corpus plus five forgery mutants.
U4 (test_s130_farkas_mirror_pin.py) pins 18 production mirror-core symbols
by source SHA -- but NOT the entry points. The HOP entry point
(embed check_hop_bundle vs production check_serialized_hop_bundle) is
exercised by neither: U1 never references it, U4 pins only math symbols.
This unit closes the hop half behaviorally.

The issuer oracle is coverage_farkas.serialize_hop_bundle, which emits a
hop-containment bundle iff region(T_prev) is contained in region(T_cur)
within the disjunctive linear fragment (it raises FarkasError otherwise).
Against that oracle the differential asserts, for the CHAIN_BUNDLE embed
(the only template that carries check_hop_bundle):

  - accept agreement: production and embed both ACCEPT an issuer-built
    containment bundle;
  - reject agreement (forgery): both REJECT each of the five U1 mutants
    (drop / dup / neg_mult / corrupt_constraint / surplus);
  - reject agreement (wrong obligation): both REJECT a valid bundle checked
    against a DIFFERENT pair of threshold ASTs (the bijection must fail);
  - refuse agreement (out of fragment): both REFUSE when the obligation is
    derived from bilinear ASTs (FarkasError caught -> False).

BOUNDARY: this samples the input space. It does NOT prove universal
embed/production equivalence over all inputs; it proves agreement on the
sampled corpus and mutants, which is the same assurance class as U1.
The NET entry point (check_net_bundle, only in build_chain_net_verifier
output) is NOT covered here and is the immediate follow-on unit.
"""
from __future__ import annotations

import copy
from fractions import Fraction
from typing import Any

import pytest

import coverage_farkas
import coverage_minilang
import dossier

HOP_EMBED_TEMPLATE = "VERIFY_OFFLINE_PY_CHAIN_BUNDLE"

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


# (name, prev_expr, cur_expr) with region(T_prev) subset-of region(T_cur).
CONTAINMENT = [
    ("tighten_gt", "amount > 1000", "amount > 500"),
    ("equal_ge", "amount >= 1000", "amount >= 1000"),
    ("and_prev_single_cur", "amount > 500 && score > 80", "amount > 400"),
    ("or_to_or", "amount > 1000 || score > 90", "amount > 500 || score > 50"),
]

# (name, prev_expr, cur_expr) where containment FAILS: the issuer must
# refuse at serialization (a disjunct of T_prev AND NOT(T_cur) is SAT).
NON_CONTAINMENT = [
    ("widen_gt", "amount > 500", "amount > 1000"),
    ("disjoint_vars", "amount > 500", "score > 500"),
]

# (name, prev_expr, cur_expr) outside the linear fragment (bilinear): both
# checkers must refuse during obligation derivation.
OUT_OF_FRAGMENT = [
    ("bilinear_cur", "amount > 500", "amount * score > 1000"),
    ("bilinear_prev", "amount * score > 1000", "amount > 500"),
]


def _asts(prev_expr: str, cur_expr: str) -> "tuple[Any, Any]":
    return (
        coverage_minilang.ml_parse(prev_expr),
        coverage_minilang.ml_parse(cur_expr),
    )


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


def test_hop_embed_exposes_entrypoints() -> None:
    ns = _embed_ns(HOP_EMBED_TEMPLATE)
    for name in ("check_hop_bundle", "_hop_disjuncts", "_canon_system"):
        assert name in ns, HOP_EMBED_TEMPLATE + " embed lacks " + name


@pytest.mark.parametrize(
    "name,prev_expr,cur_expr",
    CONTAINMENT,
    ids=[c[0] for c in CONTAINMENT],
)
def test_hop_containment_accepts_both(
    name: str,
    prev_expr: str,
    cur_expr: str,
) -> None:
    ns = _embed_ns(HOP_EMBED_TEMPLATE)
    prev_ast, cur_ast = _asts(prev_expr, cur_expr)
    doc = coverage_farkas.serialize_hop_bundle(
        prev_ast, cur_ast, prev_expr=prev_expr, cur_expr=cur_expr
    )
    assert isinstance(doc.get("certs"), list), (
        name + ": issuer bundle has no certs list (shape changed)"
    )

    prod_ok = coverage_farkas.check_serialized_hop_bundle(doc, prev_ast, cur_ast)
    embed_ok, reason = ns["check_hop_bundle"](doc, prev_ast, cur_ast)

    assert prod_ok is True, name + ": production rejected its own hop bundle"
    assert embed_ok is True, name + ": embed rejected a valid hop bundle: " + reason
    assert prod_ok == embed_ok, name + ": prod/embed disagree on a valid bundle"


@pytest.mark.parametrize(
    "mut_name,mutator", MUTATORS, ids=[m[0] for m in MUTATORS]
)
@pytest.mark.parametrize(
    "name,prev_expr,cur_expr",
    CONTAINMENT,
    ids=[c[0] for c in CONTAINMENT],
)
def test_hop_forged_fails_both(
    name: str,
    prev_expr: str,
    cur_expr: str,
    mut_name: str,
    mutator: Any,
) -> None:
    ns = _embed_ns(HOP_EMBED_TEMPLATE)
    prev_ast, cur_ast = _asts(prev_expr, cur_expr)
    doc = coverage_farkas.serialize_hop_bundle(
        prev_ast, cur_ast, prev_expr=prev_expr, cur_expr=cur_expr
    )
    mdoc = mutator(doc)

    prod_ok = coverage_farkas.check_serialized_hop_bundle(mdoc, prev_ast, cur_ast)
    embed_ok, _reason = ns["check_hop_bundle"](mdoc, prev_ast, cur_ast)

    label = name + "/" + mut_name
    assert prod_ok is False, label + ": production ACCEPTED a forged hop bundle"
    assert embed_ok is False, label + ": embed ACCEPTED a forged hop bundle"
    assert prod_ok == embed_ok, label + ": prod/embed disagree on a forgery"


def test_hop_wrong_obligation_rejected_by_both() -> None:
    ns = _embed_ns(HOP_EMBED_TEMPLATE)
    prev1, cur1 = _asts("amount > 1000", "amount > 500")
    doc = coverage_farkas.serialize_hop_bundle(
        prev1, cur1, prev_expr="amount > 1000", cur_expr="amount > 500"
    )
    # Same valid bundle, checked against a DIFFERENT obligation (score space):
    # the re-derived disjunct set cannot match the carried certs.
    prev2, cur2 = _asts("score > 90", "score > 50")

    prod_ok = coverage_farkas.check_serialized_hop_bundle(doc, prev2, cur2)
    embed_ok, _reason = ns["check_hop_bundle"](doc, prev2, cur2)

    assert prod_ok is False, "production accepted a bundle for the wrong obligation"
    assert embed_ok is False, "embed accepted a bundle for the wrong obligation"
    assert prod_ok == embed_ok, "prod/embed disagree on a wrong-obligation bundle"


@pytest.mark.parametrize(
    "name,prev_expr,cur_expr",
    OUT_OF_FRAGMENT,
    ids=[c[0] for c in OUT_OF_FRAGMENT],
)
def test_hop_out_of_fragment_refused_by_both(
    name: str,
    prev_expr: str,
    cur_expr: str,
) -> None:
    ns = _embed_ns(HOP_EMBED_TEMPLATE)
    prev_ast, cur_ast = _asts(prev_expr, cur_expr)
    # No issuer bundle exists for an out-of-fragment obligation; feed a
    # shape-valid empty bundle. Both checkers must refuse during derivation.
    doc = {"fragment": "hop-containment-bundle", "certs": []}

    prod_ok = coverage_farkas.check_serialized_hop_bundle(doc, prev_ast, cur_ast)
    embed_ok, _reason = ns["check_hop_bundle"](doc, prev_ast, cur_ast)

    assert prod_ok is False, name + ": production did not refuse an oof obligation"
    assert embed_ok is False, name + ": embed did not refuse an oof obligation"
    assert prod_ok == embed_ok, name + ": prod/embed disagree on an oof obligation"


def test_non_containment_refused_at_issuance() -> None:
    # Sanity pin on the oracle itself: serialize_hop_bundle must refuse a
    # genuine non-containment (a disjunct of T_prev AND NOT(T_cur) is SAT),
    # so the accept-agreement cases above are real containments, not vacuous.
    for name, prev_expr, cur_expr in NON_CONTAINMENT:
        prev_ast, cur_ast = _asts(prev_expr, cur_expr)
        with pytest.raises(coverage_farkas.FarkasError):
            coverage_farkas.serialize_hop_bundle(
                prev_ast, cur_ast, prev_expr=prev_expr, cur_expr=cur_expr
            )
