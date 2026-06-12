"""S133 gap-witness verifier-EMBED behavioral differential.

Phase 2b of the coverage-gap-witness arc. The production gap-witness API
(coverage_farkas.serialize_gap_witness / check_serialized_gap_witness, the
S132 phase-2a promotion) is now mirrored into the offline chain verifier
embed (dossier _GAPW_EMBED_BLOCK -> build_chain_net_verifier output) as
check_gap_witness, so a third party can check a CARRIED gap-witness offline
with rational arithmetic alone, no solver, zero issuer trust.

This unit proves the embed check_gap_witness AGREES with the production
check_serialized_gap_witness on accept/reject across a corpus and every
forgery class -- the same assurance class as U1 (bundle) and S131/S132
(hop/net). The embed returns (ok, reason); production returns bool; the
differential compares the boolean verdicts.

check_gap_witness exists ONLY inside build_chain_net_verifier() output
(spliced from _GAPW_EMBED_BLOCK after the net block, before the farkas END
marker), not in any static constant, so the embed namespace is obtained by
exec'ing the builder output.

BOUNDARY: this samples the input space. It does NOT prove universal
embed/production equivalence; it proves agreement on the sampled corpus and
mutants, the same assurance class as U1/S131/S132. The witness itself proves
a point lies in T and escapes every blocking signal -- a real coverage gap
-- NOT that the agent misbehaves there.
"""
from __future__ import annotations

import copy
from typing import Any

import pytest

import coverage_farkas
import coverage_minilang
import dossier

_GAPW_EMBED_CACHE: dict = {}


def _gapw_embed_ns() -> dict:
    if _GAPW_EMBED_CACHE:
        return _GAPW_EMBED_CACHE
    src = dossier.build_chain_net_verifier()
    code = compile(src, "<embed:build_chain_net_verifier>", "exec")
    ns: dict = {
        "__file__": "<embed:build_chain_net_verifier>",
        "__name__": "<embed_chain_net>",
    }
    exec(code, ns)  # noqa: S102
    _GAPW_EMBED_CACHE.update(ns)
    return _GAPW_EMBED_CACHE


def _ast(expr: str) -> Any:
    return coverage_minilang.ml_parse(expr)


def _sigs(exprs: "list[str]") -> "list[Any]":
    return [coverage_minilang.ml_parse(e) for e in exprs]


# (name, threshold_expr, blocking_exprs, point) with a REAL gap: the point
# lies in T and escapes every blocking signal, so serialize_gap_witness
# returns a witness and BOTH checkers must accept.
GAP = [
    ("one_signal", "amount > 0", ["amount > 1000"], {"amount": "500"}),
    (
        "two_signals",
        "amount > 0",
        ["amount > 1000", "amount > 5000"],
        {"amount": "500"},
    ),
    (
        "two_vars",
        "amount > 0",
        ["score > 90"],
        {"amount": "10", "score": "10"},
    ),
]

# (name, threshold_expr, blocking_exprs, point) where NO gap exists at the
# point: serialize_gap_witness must REFUSE (the point is blocked, or
# T-and-unblocked is empty), so the accept cases above are real gaps.
NO_GAP = [
    ("blocked_point", "amount > 0", ["amount > 1000"], {"amount": "2000"}),
    ("empty_gap", "amount > 1000", ["amount > 1000"], {"amount": "2000"}),
]

# (name, threshold_expr, blocking_exprs) outside the linear fragment
# (bilinear): both checkers must refuse during obligation derivation.
OUT_OF_FRAGMENT = [
    ("bilinear_threshold", "amount * score > 1000", ["amount > 500"]),
    ("bilinear_signal", "amount > 0", ["amount * score > 1000"]),
]


def _m_flip_fragment(doc: dict) -> dict:
    d = copy.deepcopy(doc)
    d["fragment"] = "not-a-gap-witness"
    return d


def _m_corrupt_disjunct(doc: dict) -> dict:
    d = copy.deepcopy(doc)
    d.setdefault("disjunct", []).append(
        {"coeffs": {"zzz_unmatched": "1", "": "-1"}, "strict": False}
    )
    return d


def _m_nonrational_point(doc: dict) -> dict:
    d = copy.deepcopy(doc)
    if d.get("point"):
        k = sorted(d["point"])[0]
        d["point"][k] = "not_a_number"
    return d


def _m_drop_point_var(doc: dict) -> dict:
    d = copy.deepcopy(doc)
    if d.get("point"):
        k = sorted(d["point"])[0]
        del d["point"][k]
    return d


def _m_zero_point(doc: dict) -> dict:
    d = copy.deepcopy(doc)
    for k in list(d.get("point", {})):
        d["point"][k] = "0"
    return d


MUTATORS = [
    ("flip_fragment", _m_flip_fragment),
    ("corrupt_disjunct", _m_corrupt_disjunct),
    ("nonrational_point", _m_nonrational_point),
    ("drop_point_var", _m_drop_point_var),
    ("zero_point", _m_zero_point),
]


def test_gapw_embed_exposes_entrypoints() -> None:
    ns = _gapw_embed_ns()
    for name in ("check_gap_witness", "_point_satisfies",
                 "GAP_WITNESS_FRAGMENT"):
        assert name in ns, (
            "build_chain_net_verifier output lacks " + name
        )
    assert ns["GAP_WITNESS_FRAGMENT"] == "coverage-gap-witness"


@pytest.mark.parametrize(
    "name,thr,blk,point", GAP, ids=[g[0] for g in GAP]
)
def test_gapw_accept_both(
    name: str, thr: str, blk: "list[str]", point: dict
) -> None:
    ns = _gapw_embed_ns()
    t_ast = _ast(thr)
    sigs = _sigs(blk)
    doc = coverage_farkas.serialize_gap_witness(t_ast, sigs, point)
    assert doc.get("fragment") == "coverage-gap-witness", (
        name + ": issuer produced a non-gap-witness doc (shape changed)"
    )
    prod_ok = coverage_farkas.check_serialized_gap_witness(doc, t_ast, sigs)
    embed_ok, reason = ns["check_gap_witness"](doc, t_ast, sigs)
    assert prod_ok is True, name + ": production rejected its own witness"
    assert embed_ok is True, (
        name + ": embed rejected a valid witness: " + reason
    )
    assert prod_ok == embed_ok, (
        name + ": prod/embed disagree on a valid witness"
    )


@pytest.mark.parametrize(
    "mut_name,mutator", MUTATORS, ids=[m[0] for m in MUTATORS]
)
@pytest.mark.parametrize(
    "name,thr,blk,point", GAP, ids=[g[0] for g in GAP]
)
def test_gapw_forged_fails_both(
    name: str, thr: str, blk: "list[str]", point: dict,
    mut_name: str, mutator: Any,
) -> None:
    ns = _gapw_embed_ns()
    t_ast = _ast(thr)
    sigs = _sigs(blk)
    doc = coverage_farkas.serialize_gap_witness(t_ast, sigs, point)
    mdoc = mutator(doc)
    prod_ok = coverage_farkas.check_serialized_gap_witness(mdoc, t_ast, sigs)
    embed_ok, _reason = ns["check_gap_witness"](mdoc, t_ast, sigs)
    label = name + "/" + mut_name
    assert prod_ok is False, label + ": production ACCEPTED a forged witness"
    assert embed_ok is False, label + ": embed ACCEPTED a forged witness"
    assert prod_ok == embed_ok, label + ": prod/embed disagree on a forgery"


def test_gapw_wrong_obligation_rejected_by_both() -> None:
    ns = _gapw_embed_ns()
    t1 = _ast("amount > 0")
    b1 = _sigs(["amount > 1000"])
    doc = coverage_farkas.serialize_gap_witness(t1, b1, {"amount": "500"})
    # Same valid witness, checked against a DIFFERENT obligation: the
    # re-derived disjunct set cannot contain the claimed disjunct.
    t2 = _ast("score > 0")
    b2 = _sigs(["score > 1000"])
    prod_ok = coverage_farkas.check_serialized_gap_witness(doc, t2, b2)
    embed_ok, _reason = ns["check_gap_witness"](doc, t2, b2)
    assert prod_ok is False, (
        "production accepted a witness for the wrong obligation"
    )
    assert embed_ok is False, (
        "embed accepted a witness for the wrong obligation"
    )
    assert prod_ok == embed_ok, (
        "prod/embed disagree on a wrong-obligation witness"
    )


@pytest.mark.parametrize(
    "name,thr,blk", OUT_OF_FRAGMENT, ids=[o[0] for o in OUT_OF_FRAGMENT]
)
def test_gapw_out_of_fragment_refused_by_both(
    name: str, thr: str, blk: "list[str]"
) -> None:
    ns = _gapw_embed_ns()
    t_ast = _ast(thr)
    sigs = _sigs(blk)
    # No issuer witness exists for an out-of-fragment obligation; feed a
    # shape-valid doc. Both checkers must refuse during derivation.
    doc = {
        "fragment": "coverage-gap-witness",
        "disjunct": [],
        "point": {"amount": "1"},
    }
    prod_ok = coverage_farkas.check_serialized_gap_witness(doc, t_ast, sigs)
    embed_ok, _reason = ns["check_gap_witness"](doc, t_ast, sigs)
    assert prod_ok is False, (
        name + ": production did not refuse an oof obligation"
    )
    assert embed_ok is False, name + ": embed did not refuse an oof obligation"
    assert prod_ok == embed_ok, (
        name + ": prod/embed disagree on an oof obligation"
    )


@pytest.mark.parametrize(
    "name,thr,blk,point", NO_GAP, ids=[n[0] for n in NO_GAP]
)
def test_gapw_no_gap_refused_at_issuance(
    name: str, thr: str, blk: "list[str]", point: dict
) -> None:
    # Sanity pin on the oracle itself: serialize_gap_witness must REFUSE a
    # point that witnesses no gap (blocked, or T-and-unblocked empty), so
    # the accept-agreement cases above are real gaps, not vacuous.
    t_ast = _ast(thr)
    sigs = _sigs(blk)
    with pytest.raises(coverage_farkas.FarkasError):
        coverage_farkas.serialize_gap_witness(t_ast, sigs, point)
