"""S134: production gap-witness point finder (commit 1, test-only pins).

S133 added a TEST-ONLY Fourier-Motzkin finder (tests/test_s133_gap_finder.py)
as the missing half of the certifying algorithm. S134 commit 1 GRADUATES that
finder into production (coverage_farkas.find_gap_witness_point and the _fm_*
helpers), still UNCALLED by any issuer -- the dossier call path lands in the
release commit. This module pins the production finder three ways:

  1. lockstep to the S133 reference finder: the production _fm_find_point
     returns a BYTE-IDENTICAL point (or both None) for every disjunct of every
     fixture (the reference is loaded from the S133 file by path, not sys.path);
  2. lockstep to the shipped SAT oracle: (_find_farkas is None) iff
     find_gap_witness_point produces a point, per disjunct;
  3. shipped validation: every produced point is accepted by the shipped
     _point_satisfies and, end-to-end, by check_serialized_gap_witness, while
     serialize_bundle REFUSES exactly when a witness exists.

BOUNDARY: a produced point proves THIS point lies in T and is caught by no
blocking signal -- a real gap in the net. It does NOT prove the agent
misbehaves there, nor that the gap is unique or maximal.

All fixture expressions use positive literals only: the minilang grammar has no
negative-number literal (amount < -1000 raises MinilangError at parse time).
"""
from __future__ import annotations

import importlib.util
from fractions import Fraction
from pathlib import Path
from typing import Any, Optional

import pytest

import coverage_farkas as cf
import coverage_minilang


def _load_reference() -> Any:
    path = Path(__file__).parent / "test_s133_gap_finder.py"
    spec = importlib.util.spec_from_file_location("_s133_finder_ref", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load S133 reference finder from " + str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_REF = _load_reference()


def _asts(t_expr: str, b_exprs: "list[str]") -> "tuple[Any, list]":
    return (
        coverage_minilang.ml_parse(t_expr),
        [coverage_minilang.ml_parse(e) for e in b_exprs],
    )


def _disjunct_systems(t_ast: Any, b_asts: list) -> "list[list]":
    out: list = []
    for comps in cf._gap_disjuncts(t_ast, b_asts, cf.DISJUNCT_BOUND):
        _constraints, system = cf._canon_system(comps)
        out.append(system)
    return out


COVER = [
    ("cover_single", "amount > 1000", ["amount > 500"]),
    ("cover_or", "amount > 1000 || score > 90", ["amount > 500", "score > 50"]),
    ("cover_two_block", "amount > 1000", ["amount > 500", "amount > 800"]),
]

GAP = [
    ("gap_single", "amount > 1000", ["amount > 2000"]),
    ("gap_no_block", "amount > 1000", []),
    ("gap_partial", "amount > 1000", ["amount > 1500"]),
    ("gap_two_var", "amount > 1000 && score > 50", ["amount > 2000"]),
    ("gap_or_one_open", "amount > 1000 || score > 90", ["amount > 5000"]),
    ("gap_band", "amount > 1000 && amount < 5000", ["amount > 9000"]),
]

ALL = [(c[0], c[1], c[2]) for c in COVER] + [(g[0], g[1], g[2]) for g in GAP]


@pytest.mark.parametrize("name,t_expr,b_exprs", ALL, ids=[a[0] for a in ALL])
def test_production_matches_reference_per_disjunct(
    name: str, t_expr: str, b_exprs: "list[str]"
) -> None:
    t_ast, b_asts = _asts(t_expr, b_exprs)
    systems = _disjunct_systems(t_ast, b_asts)
    assert systems, name + ": no disjuncts derived"
    for idx, system in enumerate(systems):
        prod = cf._fm_find_point(system)
        ref = _REF._fm_find_point(system)
        assert prod == ref, (
            name + " disjunct " + str(idx)
            + ": production finder disagrees with S133 reference"
        )


@pytest.mark.parametrize("name,t_expr,b_exprs", ALL, ids=[a[0] for a in ALL])
def test_production_oracle_lockstep(
    name: str, t_expr: str, b_exprs: "list[str]"
) -> None:
    t_ast, b_asts = _asts(t_expr, b_exprs)
    for idx, system in enumerate(_disjunct_systems(t_ast, b_asts)):
        farkas = cf._find_farkas(system)
        point = cf._fm_find_point(system)
        assert (farkas is None) == (point is not None), (
            name + " disjunct " + str(idx)
            + ": production finder and _find_farkas disagree on satisfiability"
        )
        if point is not None:
            assert cf._point_satisfies(point, system), (
                name + " disjunct " + str(idx)
                + ": shipped _point_satisfies rejected the production point"
            )


@pytest.mark.parametrize("name,t_expr,b_exprs", GAP, ids=[g[0] for g in GAP])
def test_entry_produces_checkable_witness_on_gap(
    name: str, t_expr: str, b_exprs: "list[str]"
) -> None:
    t_ast, b_asts = _asts(t_expr, b_exprs)
    point = cf.find_gap_witness_point(t_ast, b_asts)
    assert point is not None, name + ": entry produced no point for a gap"
    doc = cf.serialize_gap_witness(t_ast, b_asts, point, threshold_expr=t_expr)
    assert doc["fragment"] == cf.GAP_WITNESS_FRAGMENT, name
    assert cf.check_serialized_gap_witness(doc, t_ast, b_asts) is True, (
        name + ": shipped checker rejected an entry-produced witness"
    )
    with pytest.raises(cf.FarkasError):
        cf.serialize_bundle(t_ast, b_asts, threshold_expr=t_expr)


@pytest.mark.parametrize("name,t_expr,b_exprs", COVER, ids=[c[0] for c in COVER])
def test_entry_returns_none_on_cover(
    name: str, t_expr: str, b_exprs: "list[str]"
) -> None:
    t_ast, b_asts = _asts(t_expr, b_exprs)
    assert cf.find_gap_witness_point(t_ast, b_asts) is None, (
        name + ": entry produced a point where coverage holds"
    )
    cf.serialize_bundle(t_ast, b_asts, threshold_expr=t_expr)


@pytest.mark.parametrize("name,t_expr,b_exprs", GAP, ids=[g[0] for g in GAP])
def test_entry_determinism(
    name: str, t_expr: str, b_exprs: "list[str]"
) -> None:
    t_ast, b_asts = _asts(t_expr, b_exprs)
    first = cf.find_gap_witness_point(t_ast, b_asts)
    second = cf.find_gap_witness_point(t_ast, b_asts)
    assert first == second, name + ": entry is non-deterministic"


def test_strict_boundary_interior() -> None:
    t_ast, b_asts = _asts("amount > 1000", [])
    point = cf.find_gap_witness_point(t_ast, b_asts)
    assert point is not None
    assert point["amount"] > Fraction(1000)
    assert point["amount"] != Fraction(1000)


def test_multivar_joint_point() -> None:
    t_ast, b_asts = _asts("amount > 1000 && score > 50", ["amount > 2000"])
    point = cf.find_gap_witness_point(t_ast, b_asts)
    assert point is not None
    assert set(point) == {"amount", "score"}


def test_fmblowup_is_farkas_error() -> None:
    assert issubclass(cf.FMBlowupError, cf.FarkasError)
