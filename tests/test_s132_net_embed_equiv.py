"""S132 NET entry-point behavioral differential.

This closes the last uncovered verifier-core entry point. The coverage map
before this unit:

  bundle  check_bundle_against_derived  -> covered by U1 (corpus + 5 mutants)
  hop     check_hop_bundle               -> covered by S131 (29 cases)
  net     check_net_bundle               -> NOT covered

U1 cross-checks the embed BUNDLE entry point against production; S131 does
the same for HOP; U4 pins production math symbols by source SHA but no entry
points. The NET entry point (embed check_net_bundle vs production
check_serialized_net_bundle) is exercised by none of them. This unit closes
it, completing the bundle+hop+net behavioral triangle.

NET differs from HOP in three load-bearing ways, all reflected here:

  - it operates on LISTS of blocking-signal ASTs, proving net containment
    net(prev) subset-of net(cur) by refuting every DNF disjunct of
    OR(prev_sigs) AND AND(NOT cur_sigs) (not a single threshold pair);
  - the issuer oracle serialize_net_bundle(prev_sigs, cur_sigs) takes no
    threshold-expression kwargs;
  - check_net_bundle exists ONLY inside build_chain_net_verifier() output
    (spliced from _NET_EMBED_BLOCK), not in any static verifier constant,
    so the embed namespace is obtained by exec'ing the builder output.

Against the oracle the differential asserts, for the chain-net verifier embed:

  - accept agreement: production and embed both ACCEPT an issuer-built net
    containment bundle (non-empty certs);
  - vacuous agreement: both ACCEPT an empty-cert bundle when the predecessor
    net is empty (vacuous containment) -- a net-only class;
  - reject agreement (forgery): both REJECT each of the five U1 mutants
    (drop / dup / neg_mult / corrupt_constraint / surplus);
  - reject agreement (wrong obligation): both REJECT a valid bundle checked
    against a DIFFERENT pair of signal lists (the bijection must fail);
  - refuse agreement (out of fragment): both REFUSE when the obligation is
    derived from bilinear signals (FarkasError caught -> falsey);
  - issuer sanity pin: serialize_net_bundle REFUSES a genuine
    non-containment (net widened, vanished, or disjoint), so the accept
    cases above are real containments, not vacuous.

BOUNDARY: this samples the input space. It does NOT prove universal
embed/production equivalence over all inputs; it proves agreement on the
sampled corpus and mutants, the same assurance class as U1 and S131.
"""
from __future__ import annotations

import copy
from fractions import Fraction
from typing import Any

import pytest

import coverage_farkas
import coverage_minilang
import dossier

_NET_EMBED_CACHE: dict = {}


def _net_embed_ns() -> dict:
    if _NET_EMBED_CACHE:
        return _NET_EMBED_CACHE
    src = dossier.build_chain_net_verifier()
    code = compile(src, "<embed:build_chain_net_verifier>", "exec")
    ns: dict = {
        "__file__": "<embed:build_chain_net_verifier>",
        "__name__": "<embed_chain_net>",
    }
    exec(code, ns)  # noqa: S102
    _NET_EMBED_CACHE.update(ns)
    return _NET_EMBED_CACHE


def _sigs(exprs: "list[str]") -> "list[Any]":
    return [coverage_minilang.ml_parse(e) for e in exprs]


# (name, prev_exprs, cur_exprs) with net(prev) subset-of net(cur) and a
# NON-EMPTY certificate list (used for accept agreement and mutants).
CONTAINMENT = [
    ("tighten", ["amount > 1000"], ["amount > 500"]),
    ("add_cur_signal", ["amount > 1000"], ["amount > 500", "score > 90"]),
    (
        "two_by_two",
        ["amount > 1000", "score > 90"],
        ["amount > 500", "score > 50"],
    ),
]

# (name, prev_exprs, cur_exprs) with an EMPTY predecessor net: the issuer
# emits an empty certificate list and both checkers must accept (vacuous
# containment). A net-only class with no hop analog.
VACUOUS = [
    ("empty_prev", [], ["amount > 500"]),
    ("empty_both", [], []),
]

# (name, prev_exprs, cur_exprs) where containment FAILS: the issuer must
# refuse at serialization (a disjunct of OR(prev) AND AND(NOT cur) is SAT).
NON_CONTAINMENT = [
    ("widen", ["amount > 500"], ["amount > 1000"]),
    ("vanish", ["amount > 500"], []),
    ("disjoint_vars", ["amount > 500"], ["score > 500"]),
]

# (name, prev_exprs, cur_exprs) outside the linear fragment (bilinear): both
# checkers must refuse during obligation derivation.
OUT_OF_FRAGMENT = [
    ("bilinear_prev", ["amount * score > 1000"], ["amount > 500"]),
    ("bilinear_cur", ["amount > 500"], ["amount * score > 1000"]),
]


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


def test_net_embed_exposes_entrypoints() -> None:
    ns = _net_embed_ns()
    for name in ("check_net_bundle", "_net_disjuncts", "_canon_system"):
        assert name in ns, (
            "build_chain_net_verifier output lacks " + name
        )


@pytest.mark.parametrize(
    "name,prev_exprs,cur_exprs",
    CONTAINMENT,
    ids=[c[0] for c in CONTAINMENT],
)
def test_net_containment_accepts_both(
    name: str,
    prev_exprs: "list[str]",
    cur_exprs: "list[str]",
) -> None:
    ns = _net_embed_ns()
    prev_sigs = _sigs(prev_exprs)
    cur_sigs = _sigs(cur_exprs)
    doc = coverage_farkas.serialize_net_bundle(prev_sigs, cur_sigs)
    assert isinstance(doc.get("certs"), list), (
        name + ": issuer bundle has no certs list (shape changed)"
    )
    assert doc["certs"], (
        name + ": expected a NON-EMPTY net bundle for a forgery base"
    )

    prod_ok = coverage_farkas.check_serialized_net_bundle(
        doc, prev_sigs, cur_sigs
    )
    embed_ok, reason = ns["check_net_bundle"](doc, prev_sigs, cur_sigs)

    assert prod_ok is True, name + ": production rejected its own net bundle"
    assert embed_ok is True, (
        name + ": embed rejected a valid net bundle: " + reason
    )
    assert prod_ok == embed_ok, name + ": prod/embed disagree on a valid bundle"


@pytest.mark.parametrize(
    "name,prev_exprs,cur_exprs",
    VACUOUS,
    ids=[c[0] for c in VACUOUS],
)
def test_net_vacuous_accepts_both(
    name: str,
    prev_exprs: "list[str]",
    cur_exprs: "list[str]",
) -> None:
    ns = _net_embed_ns()
    prev_sigs = _sigs(prev_exprs)
    cur_sigs = _sigs(cur_exprs)
    doc = coverage_farkas.serialize_net_bundle(prev_sigs, cur_sigs)
    assert doc.get("certs") == [], (
        name + ": empty predecessor net must yield an empty cert list"
    )

    prod_ok = coverage_farkas.check_serialized_net_bundle(
        doc, prev_sigs, cur_sigs
    )
    embed_ok, reason = ns["check_net_bundle"](doc, prev_sigs, cur_sigs)

    assert prod_ok is True, name + ": production rejected a vacuous net bundle"
    assert embed_ok is True, (
        name + ": embed rejected a vacuous net bundle: " + reason
    )
    assert prod_ok == embed_ok, name + ": prod/embed disagree on a vacuous bundle"


@pytest.mark.parametrize(
    "mut_name,mutator", MUTATORS, ids=[m[0] for m in MUTATORS]
)
@pytest.mark.parametrize(
    "name,prev_exprs,cur_exprs",
    CONTAINMENT,
    ids=[c[0] for c in CONTAINMENT],
)
def test_net_forged_fails_both(
    name: str,
    prev_exprs: "list[str]",
    cur_exprs: "list[str]",
    mut_name: str,
    mutator: Any,
) -> None:
    ns = _net_embed_ns()
    prev_sigs = _sigs(prev_exprs)
    cur_sigs = _sigs(cur_exprs)
    doc = coverage_farkas.serialize_net_bundle(prev_sigs, cur_sigs)
    mdoc = mutator(doc)

    prod_ok = coverage_farkas.check_serialized_net_bundle(
        mdoc, prev_sigs, cur_sigs
    )
    embed_ok, _reason = ns["check_net_bundle"](mdoc, prev_sigs, cur_sigs)

    label = name + "/" + mut_name
    assert prod_ok is False, label + ": production ACCEPTED a forged net bundle"
    assert embed_ok is False, label + ": embed ACCEPTED a forged net bundle"
    assert prod_ok == embed_ok, label + ": prod/embed disagree on a forgery"


def test_net_wrong_obligation_rejected_by_both() -> None:
    ns = _net_embed_ns()
    prev1 = _sigs(["amount > 1000"])
    cur1 = _sigs(["amount > 500"])
    doc = coverage_farkas.serialize_net_bundle(prev1, cur1)
    # Same valid bundle, checked against a DIFFERENT obligation (score space):
    # the re-derived disjunct set cannot match the carried certs.
    prev2 = _sigs(["score > 90"])
    cur2 = _sigs(["score > 50"])

    prod_ok = coverage_farkas.check_serialized_net_bundle(doc, prev2, cur2)
    embed_ok, _reason = ns["check_net_bundle"](doc, prev2, cur2)

    assert prod_ok is False, "production accepted a bundle for the wrong obligation"
    assert embed_ok is False, "embed accepted a bundle for the wrong obligation"
    assert prod_ok == embed_ok, "prod/embed disagree on a wrong-obligation bundle"


@pytest.mark.parametrize(
    "name,prev_exprs,cur_exprs",
    OUT_OF_FRAGMENT,
    ids=[c[0] for c in OUT_OF_FRAGMENT],
)
def test_net_out_of_fragment_refused_by_both(
    name: str,
    prev_exprs: "list[str]",
    cur_exprs: "list[str]",
) -> None:
    ns = _net_embed_ns()
    prev_sigs = _sigs(prev_exprs)
    cur_sigs = _sigs(cur_exprs)
    # No issuer bundle exists for an out-of-fragment obligation; feed a
    # shape-valid empty bundle. Both checkers must refuse during derivation.
    doc = {"fragment": "blocking-net-containment-bundle", "certs": []}

    prod_ok = coverage_farkas.check_serialized_net_bundle(
        doc, prev_sigs, cur_sigs
    )
    embed_ok, _reason = ns["check_net_bundle"](doc, prev_sigs, cur_sigs)

    assert prod_ok is False, name + ": production did not refuse an oof obligation"
    assert embed_ok is False, name + ": embed did not refuse an oof obligation"
    assert prod_ok == embed_ok, name + ": prod/embed disagree on an oof obligation"


def test_net_non_containment_refused_at_issuance() -> None:
    # Sanity pin on the oracle itself: serialize_net_bundle must refuse a
    # genuine non-containment (a disjunct of OR(prev) AND AND(NOT cur) is
    # SAT), so the accept-agreement cases above are real containments, not
    # vacuous. Covers net widened, net vanished (empty cur), and disjoint.
    for name, prev_exprs, cur_exprs in NON_CONTAINMENT:
        prev_sigs = _sigs(prev_exprs)
        cur_sigs = _sigs(cur_exprs)
        with pytest.raises(coverage_farkas.FarkasError):
            coverage_farkas.serialize_net_bundle(prev_sigs, cur_sigs)
