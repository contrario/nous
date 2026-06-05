"""
NOUS policy_coverage - translate a numeric policy-signal AST subset into
SMT-LIB 2.6 terms, and build the coverage obligation that proves the
blocking-policy net leaves no gap over a declared threshold region.

Pure-Python: no z3 import. Output is solver-agnostic SMT-LIB text. The
solver run lives in smt_verify.verify_coverage (a later patch). This
module's responsibility ends at byte-deterministic spec fragments.

Soundness model (see docs and the build doc Part 2-3):

  Policies are MONITORS, not guards. The provable claim is COVERAGE:

    For every input where <threshold> holds, at least one policy whose
    action is in {block, abort_cycle} has a signal that also holds.

  Negated obligation handed to the solver:

    (assert <threshold>)                         ; protected region
    (assert (not (or <blocking_signal_i> ...)))  ; net is open
    (check-sat)

    unsat -> PROVEN: no gap.
    sat   -> REFUTED: a concrete over-threshold input slips through.

Single sort: Real. NOUS has no expression type system; the runtime
semantic of a signal is Python eval. Building an independent sort-
inference engine would be a second source of truth. Every free variable
and numeric literal is Real (QF_LRA). Sound relative to Python numeric
comparison on the supported operator subset; everything else is REFUSED,
never approximated (refuse over guess).

Supported AST (verified live shapes):
  binop:    {'kind':'binop','op':OP,'left':X,'right':Y}
  not:      {'kind':'not','operand':X}
  currency: {'currency':'EUR'|'USD','amount':float}   (numeric magnitude)
  name:     bare str without quotes
  number:   bare int | float
Supported OP: > < >= <= == != && || + -
REFUSED OP:   * / %   (Python-vs-SMT numeric-tower divergence)
REFUSED:      string literal (bare str starting with a double quote),
              bool literal as a free operand, and any dict whose shape is
              not binop/not/currency.

# __nous_policy_coverage_module_v1__
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


POLICY_COVERAGE_VERSION: str = "1.0"

_BLOCKING_ACTIONS: frozenset[str] = frozenset({"block", "abort_cycle"})

_COMPARE_OPS: frozenset[str] = frozenset({">", "<", ">=", "<=", "==", "!="})
_BOOL_OPS: dict[str, str] = {"&&": "and", "||": "or"}
_ARITH_OPS: dict[str, str] = {"+": "+", "-": "-"}
_REFUSED_ARITH: frozenset[str] = frozenset({"*", "/", "%"})


class CoverageEmitError(ValueError):
    """Raised when a signal/threshold cannot be soundly translated.

    The message starts with the cause. Callers surface this as a CLI
    diagnostic and DO NOT emit a coverage obligation; the cost
    obligation is unaffected.
    """


@dataclass(frozen=True)
class ThresholdClaim:
    """A parsed threshold expression plus the names and currency units
    it touches. `expr_ast` is a signal-shaped AST (same shape produced
    by the NOUS parser for a policy signal)."""
    expr_ast: Any
    smt_term: str
    names: tuple[str, ...]
    currency_units: frozenset[str]


@dataclass(frozen=True)
class CoverageBlock:
    """The SMT-LIB fragments for one coverage obligation."""
    declarations: tuple[tuple[str, str], ...]
    threshold_assertion: str
    open_net_assertion: str
    threshold_expr_human: str
    currency_unit: Optional[str]


def _is_quoted_string(s: str) -> bool:
    return len(s) >= 1 and (s[0] == '"' or s[0] == "'")


def _is_currency_dict(node: Any) -> bool:
    return (
        isinstance(node, dict)
        and "currency" in node
        and "amount" in node
        and "kind" not in node
    )


def _num_to_smt(value: Any) -> str:
    """Render a Python int/float as an SMT-LIB Real literal.

    Floats are rendered via their exact integer ratio so no binary-float
    rounding enters the proof. Integers render directly.
    """
    if isinstance(value, bool):
        raise CoverageEmitError(
            "bool literal is not a numeric operand; refused in coverage "
            "(2a supports numeric comparison only)"
        )
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        from fractions import Fraction
        frac = Fraction(value).limit_denominator(10**12)
        if frac.denominator == 1:
            return str(frac.numerator)
        return f"(/ {frac.numerator} {frac.denominator})"
    raise CoverageEmitError(
        f"unsupported numeric literal type {type(value).__name__!r}"
    )


def _translate(
    node: Any,
    names: set[str],
    units: set[str],
) -> str:
    """Translate a signal-AST node to an SMT-LIB term. Side effects:
    populate `names` with free variables and `units` with currency
    units encountered. Refuses (typed) on anything outside the subset.
    """
    # currency literal: {'currency':..,'amount':..}
    if _is_currency_dict(node):
        units.add(str(node["currency"]))
        return _num_to_smt(node["amount"])

    # bare numeric literal
    if isinstance(node, bool):
        raise CoverageEmitError(
            "bool literal as a free operand is refused in coverage (2a); "
            "boolean structure must come from &&/||/! over comparisons"
        )
    if isinstance(node, (int, float)):
        return _num_to_smt(node)

    # bare string: variable (no quotes) or string literal (quoted)
    if isinstance(node, str):
        if _is_quoted_string(node):
            raise CoverageEmitError(
                f"string literal {node!r} is refused in coverage (2a); "
                f"string/enum coverage is deferred to a later phase"
            )
        names.add(node)
        return node

    # dict nodes: binop / not
    if isinstance(node, dict):
        kind = node.get("kind")
        if kind == "not":
            inner = _translate(node["operand"], names, units)
            return f"(not {inner})"
        if kind == "binop":
            op = node.get("op")
            if op in _REFUSED_ARITH:
                raise CoverageEmitError(
                    f"arithmetic operator {op!r} is refused in coverage "
                    f"(2a): Python-vs-SMT numeric-tower divergence. Only "
                    f"+ and - are supported."
                )
            left = _translate(node["left"], names, units)
            right = _translate(node["right"], names, units)
            if op in _COMPARE_OPS:
                if op == "==":
                    return f"(= {left} {right})"
                if op == "!=":
                    return f"(not (= {left} {right}))"
                return f"({op} {left} {right})"
            if op in _BOOL_OPS:
                return f"({_BOOL_OPS[op]} {left} {right})"
            if op in _ARITH_OPS:
                return f"({_ARITH_OPS[op]} {left} {right})"
            raise CoverageEmitError(
                f"unsupported operator {op!r} in coverage (2a)"
            )
        raise CoverageEmitError(
            f"unsupported signal node kind {kind!r} in coverage (2a)"
        )

    if node is None:
        raise CoverageEmitError(
            "null/None signal node is refused in coverage (2a)"
        )

    raise CoverageEmitError(
        f"unsupported signal node type {type(node).__name__!r} "
        f"in coverage (2a)"
    )


def translate_signal(signal_ast: Any) -> tuple[str, tuple[str, ...], frozenset[str]]:
    """Public: translate one signal AST to (smt_term, names, units).

    Raises CoverageEmitError on any unsupported construct.
    """
    names: set[str] = set()
    units: set[str] = set()
    term = _translate(signal_ast, names, units)
    return term, tuple(sorted(names)), frozenset(units)


def build_threshold_claim(threshold_ast: Any, human: str) -> ThresholdClaim:
    """Build a ThresholdClaim from a parsed threshold signal AST."""
    term, names, units = translate_signal(threshold_ast)
    if len(units) > 1:
        raise CoverageEmitError(
            f"threshold mixes currency units {sorted(units)}; cross-unit "
            f"comparison is not auditable and is refused"
        )
    return ThresholdClaim(
        expr_ast=threshold_ast,
        smt_term=term,
        names=names,
        currency_units=units,
    )


def build_coverage_block(
    policies: list[Any],
    threshold: ThresholdClaim,
) -> CoverageBlock:
    """Build the coverage SMT fragments from blocking policies and a
    threshold claim.

    Only policies whose action is in {block, abort_cycle} participate.
    Every free variable across the threshold and the participating
    signals is declared Real. Refuses (typed) if no blocking policy
    exists (there is nothing to prove coverage against) or if any
    participating signal or the threshold mixes currency units.
    """
    blocking = [p for p in policies if getattr(p, "action", None) in _BLOCKING_ACTIONS]
    if not blocking:
        raise CoverageEmitError(
            "no blocking policy (action block/abort_cycle) is declared; "
            "coverage has nothing to prove. Add a blocking policy or omit "
            "the coverage obligation."
        )

    all_names: set[str] = set(threshold.names)
    all_units: set[str] = set(threshold.currency_units)
    signal_terms: list[str] = []
    for p in blocking:
        term, names, units = translate_signal(p.signal)
        signal_terms.append(term)
        all_names.update(names)
        all_units.update(units)

    if len(all_units) > 1:
        raise CoverageEmitError(
            f"coverage mixes currency units {sorted(all_units)} across "
            f"threshold and policies; cross-unit comparison is refused"
        )

    decls: tuple[tuple[str, str], ...] = tuple(
        (name, "Real") for name in sorted(all_names)
    )
    threshold_assertion = f"(assert {threshold.smt_term})"
    if len(signal_terms) == 1:
        union = signal_terms[0]
    else:
        union = f"(or {' '.join(signal_terms)})"
    open_net_assertion = f"(assert (not {union}))"
    unit = next(iter(all_units)) if all_units else None

    return CoverageBlock(
        declarations=decls,
        threshold_assertion=threshold_assertion,
        open_net_assertion=open_net_assertion,
        threshold_expr_human=threshold.smt_term,
        currency_unit=unit,
    )


def serialize_coverage(block: CoverageBlock) -> str:
    """Serialize a CoverageBlock to byte-deterministic SMT-LIB text."""
    lines: list[str] = []
    lines.append("; ---------------------------------------------------------")
    lines.append(f"; NOUS policy_coverage {POLICY_COVERAGE_VERSION}")
    lines.append("; coverage obligation: blocking-policy net over threshold")
    lines.append(f"; threshold: {block.threshold_expr_human}")
    if block.currency_unit is not None:
        lines.append(f"; currency_unit: {block.currency_unit}")
    lines.append("; unsat proves no over-threshold input is uncovered")
    lines.append("; ---------------------------------------------------------")
    lines.append("")
    lines.append("(set-logic QF_LRA)")
    lines.append("")
    for var, sort in block.declarations:
        lines.append(f"(declare-const {var} {sort})")
    lines.append("")
    lines.append("; protected region")
    lines.append(block.threshold_assertion)
    lines.append("; net is open (negated) - unsat proves coverage")
    lines.append(block.open_net_assertion)
    lines.append("")
    lines.append("(check-sat)")
    return "\n".join(lines) + "\n"


def coverage_sha256(block: CoverageBlock) -> str:
    """Canonical hash of a CoverageBlock. Independent of the cost spec's
    SMTSpec.sha256(); changing coverage never perturbs the cost sha."""
    import hashlib as _hashlib

    canonical: list[str] = []
    canonical.append(f"PCV:{POLICY_COVERAGE_VERSION}")
    for var, sort in block.declarations:
        canonical.append(f"CD:{var}:{sort}")
    canonical.append(f"CT:{block.threshold_assertion}")
    canonical.append(f"CO:{block.open_net_assertion}")
    if block.currency_unit is not None:
        canonical.append(f"CU:{block.currency_unit}")
    encoded = "\n".join(canonical).encode("utf-8")
    return _hashlib.sha256(encoded).hexdigest()
