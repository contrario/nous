"""Farkas certificate extraction and stdlib-only checking for NOUS
policy-coverage proofs (S115 P3b, single-comparison fragment).

A coverage obligation is UNSAT of:
    threshold  AND  NOT(s1 OR ... OR sk)
  = threshold  AND  (NOT s1) AND ... AND (NOT sk)
where threshold and each si are single linear comparisons over Reals.

For a conjunction of linear inequalities over the reals that is
unsatisfiable, Farkas' lemma gives non-negative multipliers whose
combination is a numeric contradiction. The certificate is that list of
rational multipliers; checking it is rational arithmetic alone -- no
solver, no NOUS install.

This module is import-light (stdlib only) so it can be embedded in the
offline dossier verifier.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Optional


class FarkasError(ValueError):
    """Raised when an obligation is outside the single-comparison
    fragment, or when no Farkas witness can be extracted."""


# A linear inequality is stored normalized to the form:  L  REL  0
# where L is a dict {var_name: Fraction, "": Fraction(const)} and REL is
# one of ">=", ">", "<=", "<".  We canonicalize every inequality to a
# "<= 0" / "< 0" orientation for Farkas combination.

_COMPARE = {">", ">=", "<", "<=", "=="}


@dataclass(frozen=True)
class LinIneq:
    coeffs: dict           # {var: Fraction, "": Fraction}  (L)
    strict: bool           # True => L < 0 ; False => L <= 0


@dataclass(frozen=True)
class FarkasCertificate:
    inequalities: tuple                 # tuple of canonical strings "L < 0"
    multipliers: tuple                  # tuple of Fraction (as str p/q)
    contradiction: str                  # the collapsed form, e.g. "1 < 0"


def _num(node: Any) -> Optional[Fraction]:
    if isinstance(node, bool):
        return None
    if isinstance(node, int):
        return Fraction(node)
    if isinstance(node, float):
        return Fraction(node).limit_denominator(10 ** 12)
    if isinstance(node, dict) and "currency" in node and "amount" in node:
        return _num(node["amount"])
    return None


def _linear(node: Any) -> dict:
    """Translate an arithmetic AST term to {var: Fraction, "": const}.
    Refuses anything beyond names, numeric literals, and +/- of them."""
    n = _num(node)
    if n is not None:
        return {"": n}
    if isinstance(node, str):
        if node[:1] in ('"', "'"):
            raise FarkasError("string literal outside fragment")
        return {node: Fraction(1), "": Fraction(0)}
    if isinstance(node, dict) and node.get("kind") == "binop":
        op = node.get("op")
        if op == "+":
            return _add(_linear(node["left"]), _linear(node["right"]), 1)
        if op == "-":
            return _add(_linear(node["left"]), _linear(node["right"]), -1)
        raise FarkasError(f"non-linear operator {op!r} in term")
    raise FarkasError(f"unsupported term node {type(node).__name__!r}")


def _add(a: dict, b: dict, sign: int) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, Fraction(0)) + sign * v
    return out


def _scale(a: dict, s: Fraction) -> dict:
    return {k: v * s for k, v in a.items()}


def _comparison_to_ineq(node: Any) -> LinIneq:
    """A single comparison AST -> LinIneq in 'L (< or <=) 0' form."""
    if not (isinstance(node, dict) and node.get("kind") == "binop"):
        raise FarkasError("signal is not a single comparison")
    op = node.get("op")
    if op not in (">", ">=", "<", "<="):
        raise FarkasError(
            f"comparison op {op!r} outside fragment "
            f"(==/!= and boolean structure not supported in P3b)"
        )
    left = _linear(node["left"])
    right = _linear(node["right"])
    # left OP right  ->  move to  (left - right) OP 0
    diff = _add(left, right, -1)
    # normalize to <= / < 0
    if op in ("<", "<="):
        return LinIneq(coeffs=diff, strict=(op == "<"))
    # > / >=  :  diff > 0  <=>  -diff < 0
    return LinIneq(coeffs=_scale(diff, Fraction(-1)), strict=(op == ">"))


def _negate(ineq_node: Any) -> LinIneq:
    """NOT of a single comparison, as a LinIneq in '< / <= 0' form.
    NOT(a < b)  = a >= b ; NOT(a <= b) = a > b ; and mirror for > >=."""
    if not (isinstance(ineq_node, dict)
            and ineq_node.get("kind") == "binop"):
        raise FarkasError("negated signal is not a single comparison")
    op = ineq_node.get("op")
    flip = {">": "<=", ">=": "<", "<": ">=", "<=": ">"}
    if op not in flip:
        raise FarkasError(
            f"cannot negate op {op!r} in P3b fragment"
        )
    neg = dict(ineq_node)
    neg["op"] = flip[op]
    return _comparison_to_ineq(neg)


def _signal_disjuncts(node: Any) -> list:
    """Return the list of single-comparison disjuncts of a blocking
    signal. P3b accepts only a single comparison (one disjunct) or a
    flat OR of single comparisons. Refuses AND / NOT / nesting."""
    if isinstance(node, dict) and node.get("kind") == "binop" \
            and node.get("op") in ("or", "||"):
        return (_signal_disjuncts(node["left"])
                + _signal_disjuncts(node["right"]))
    if isinstance(node, dict) and node.get("kind") == "binop" \
            and node.get("op") in (">", ">=", "<", "<="):
        return [node]
    raise FarkasError(
        "blocking signal outside P3b fragment (only a single comparison "
        "or a flat OR of comparisons is supported)"
    )


def extract_certificate(
    threshold_ast: Any,
    blocking_signals: list,
) -> FarkasCertificate:
    """Build a Farkas certificate for the single-comparison fragment.

    System to refute:  threshold AND AND_i(NOT s_i_disjunct).
    Because NOT(OR_j d_j) = AND_j(NOT d_j), every disjunct across every
    blocking signal contributes one negated inequality. P3b requires the
    resulting conjunction to be refutable as a SINGLE linear system
    (one Farkas witness). If a blocking signal is itself an OR, each
    disjunct's negation is conjoined -- still one linear system.
    """
    system: list = [_comparison_to_ineq(threshold_ast)]
    for sig in blocking_signals:
        for disj in _signal_disjuncts(sig):
            system.append(_negate(disj))

    witness = _find_farkas(system)
    if witness is None:
        raise FarkasError(
            "no Farkas witness: the conjunction is satisfiable or outside "
            "the single linear system P3b can certify (a gap may exist, "
            "or the obligation needs case-splitting -> P3b-bool)"
        )

    ineq_strs = tuple(_ineq_str(i) for i in system)
    mult_strs = tuple(_frac_str(m) for m in witness)
    contradiction = _contradiction_str(system, witness)
    return FarkasCertificate(
        inequalities=ineq_strs,
        multipliers=mult_strs,
        contradiction=contradiction,
    )


def _all_vars(system: list) -> list:
    seen: list = []
    for ineq in system:
        for k in ineq.coeffs:
            if k != "" and k not in seen:
                seen.append(k)
    return sorted(seen)


def _find_farkas(system: list) -> Optional[list]:
    """Find non-negative multipliers lambda_i such that
    sum_i lambda_i * (L_i) has all variable coeffs 0 and constant >= 0,
    with at least one strict inequality having lambda > 0 (=> 0 < 0),
    OR constant > 0 (=> c < 0 with c > 0). Solves the small system over
    Fractions via exhaustive structure for the single-variable case and
    a general nullspace search for multi-variable.

    For the single-comparison fragment the system is small; we use an
    exact rational Gaussian elimination on the 'cancel all variables'
    constraints, then verify the constant/strictness contradiction.
    """
    variables = _all_vars(system)
    n = len(system)

    # Build matrix A (vars x n) for variable-cancellation: A * lambda = 0.
    # We seek lambda >= 0, not all zero, in the nullspace, such that the
    # combined constant term c = sum lambda_i * const_i satisfies the
    # contradiction condition.
    # Strategy: enumerate minimal support solutions for small n.
    from itertools import combinations

    def combo_ok(idxs: tuple) -> Optional[list]:
        # Solve for positive lambda on this support that cancels all vars.
        m = len(idxs)
        if m == 0:
            return None
        # variable-cancellation equations
        rows: list = []
        for v in variables:
            rows.append([system[i].coeffs.get(v, Fraction(0)) for i in idxs])
        # We want a nonzero non-negative solution lambda (length m).
        # Set lambda[last] = 1 and solve the linear system if square-ish.
        # General approach: find nullspace of rows (over Fractions).
        null = _nullspace(rows, m)
        for vec in null:
            # try to scale to all-positive
            scaled = _make_nonneg(vec)
            if scaled is None:
                continue
            # compute constant and strictness
            const = Fraction(0)
            any_strict = False
            for j, i in enumerate(idxs):
                if scaled[j] > 0:
                    const += scaled[j] * system[i].coeffs.get("", Fraction(0))
                    if system[i].strict:
                        any_strict = True
            # contradiction: combined says  const (< or <=) 0
            #   - if const > 0  -> "const < 0" false => UNSAT proof
            #   - if const == 0 and any_strict -> "0 < 0" => UNSAT proof
            if const > 0 or (const == 0 and any_strict):
                full = [Fraction(0)] * n
                for j, i in enumerate(idxs):
                    full[i] = scaled[j]
                return full
        return None

    for size in range(1, n + 1):
        for idxs in combinations(range(n), size):
            res = combo_ok(idxs)
            if res is not None:
                return res
    return None


def _nullspace(rows: list, ncols: int) -> list:
    """Exact rational nullspace basis of the matrix `rows` (list of rows,
    each length ncols). Returns a list of basis vectors (list[Fraction]).
    If there are no rows, the whole space is the nullspace."""
    # Gaussian elimination over Fractions.
    M = [row[:] for row in rows if any(x != 0 for x in row)]
    if not M:
        basis = []
        for i in range(ncols):
            e = [Fraction(0)] * ncols
            e[i] = Fraction(1)
            basis.append(e)
        return basis
    nrows = len(M)
    pivot_cols: list = []
    r = 0
    for c in range(ncols):
        piv = None
        for rr in range(r, nrows):
            if M[rr][c] != 0:
                piv = rr
                break
        if piv is None:
            continue
        M[r], M[piv] = M[piv], M[r]
        inv = Fraction(1) / M[r][c]
        M[r] = [x * inv for x in M[r]]
        for rr in range(nrows):
            if rr != r and M[rr][c] != 0:
                f = M[rr][c]
                M[rr] = [a - f * b for a, b in zip(M[rr], M[r])]
        pivot_cols.append(c)
        r += 1
        if r == nrows:
            break
    free_cols = [c for c in range(ncols) if c not in pivot_cols]
    basis: list = []
    for fc in free_cols:
        vec = [Fraction(0)] * ncols
        vec[fc] = Fraction(1)
        for ri, pc in enumerate(pivot_cols):
            vec[pc] = -M[ri][fc]
        basis.append(vec)
    return basis


def _make_nonneg(vec: list) -> Optional[list]:
    """Scale a vector by +-1 (and require it to be all >= 0). Returns the
    non-negative version or None if it has mixed signs."""
    if all(x >= 0 for x in vec) and any(x > 0 for x in vec):
        return vec
    neg = [-x for x in vec]
    if all(x >= 0 for x in neg) and any(x > 0 for x in neg):
        return neg
    return None


def _ineq_str(ineq: LinIneq) -> str:
    rel = "<" if ineq.strict else "<="
    terms: list = []
    for k in sorted(ineq.coeffs):
        if k == "":
            continue
        terms.append(f"{ineq.coeffs[k]}*{k}")
    const = ineq.coeffs.get("", Fraction(0))
    lhs = " + ".join(terms) if terms else "0"
    return f"{lhs} + {const} {rel} 0"


def _frac_str(f: Fraction) -> str:
    return str(f)


def _contradiction_str(system: list, witness: list) -> str:
    const = Fraction(0)
    strict = False
    for lam, ineq in zip(witness, system):
        if lam > 0:
            const += lam * ineq.coeffs.get("", Fraction(0))
            if ineq.strict:
                strict = True
    rel = "<" if strict else "<="
    return f"{const} {rel} 0"


def check_certificate(
    threshold_ast: Any,
    blocking_signals: list,
    multipliers: list,
) -> bool:
    """Stdlib-only verification: rebuild the linear system from the AST,
    apply the given multipliers, confirm they are non-negative, cancel
    all variables, and yield a numeric contradiction. Returns True iff
    the certificate proves UNSAT. No solver involved."""
    system: list = [_comparison_to_ineq(threshold_ast)]
    for sig in blocking_signals:
        for disj in _signal_disjuncts(sig):
            system.append(_negate(disj))

    lam = [Fraction(m) if not isinstance(m, Fraction) else m
           for m in multipliers]
    if len(lam) != len(system):
        return False
    if any(x < 0 for x in lam):
        return False
    if not any(x > 0 for x in lam):
        return False

    combined: dict = {}
    strict = False
    for x, ineq in zip(lam, system):
        if x == 0:
            continue
        for k, v in ineq.coeffs.items():
            combined[k] = combined.get(k, Fraction(0)) + x * v
        if ineq.strict:
            strict = True

    # all variable coefficients must cancel
    for k, v in combined.items():
        if k != "" and v != 0:
            return False
    const = combined.get("", Fraction(0))
    # contradiction: const < 0 is asserted by combination but const >= 0,
    # i.e. combined says "const <(=) 0" while const is actually > 0
    # (non-strict) OR const == 0 with a strict inequality used.
    if const > 0:
        return True
    if const == 0 and strict:
        return True
    return False


def serialize_system(  # __s116_farkas_serialize_v1__
    threshold_ast,
    blocking_signals,
    threshold_expr=None,
):
    """Build a self-contained, JSON-serializable Farkas certificate for the
    single-comparison fragment. The returned dict carries the canonical
    linear system (each inequality as exact-rational coeffs in 'L (< or
    <=) 0' form) plus the non-negative multipliers that collapse it to a
    numeric contradiction. It is checkable by check_serialized() with
    fractions alone -- no AST, no solver. Raises FarkasError outside the
    fragment or when no single-system Farkas witness exists."""
    system = [_comparison_to_ineq(threshold_ast)]
    for sig in blocking_signals:
        for disj in _signal_disjuncts(sig):
            system.append(_negate(disj))

    witness = _find_farkas(system)
    if witness is None:
        raise FarkasError(
            "no Farkas witness: the conjunction is satisfiable or outside "
            "the single linear system P3b can certify (a gap may exist, or "
            "the obligation needs case-splitting -> P3b-bool)"
        )

    constraints = []
    for ineq in system:
        constraints.append(
            {
                "coeffs": {k: str(v) for k, v in sorted(ineq.coeffs.items())},
                "strict": bool(ineq.strict),
            }
        )
    return {
        "fragment": "linear-real-single-comparison",
        "threshold_expr": threshold_expr,
        "constraints": constraints,
        "multipliers": [str(m) for m in witness],
        "contradiction": _contradiction_str(system, witness),
    }


def check_serialized(doc):  # __s116_farkas_serialize_v1__
    """Stdlib-only verification of a serialized Farkas certificate (the
    dict produced by serialize_system). Confirms: equal-length non-negative
    multipliers (at least one positive), that the multiplier-weighted sum of
    the carried inequalities cancels every variable, and that the residual
    constant yields a numeric contradiction. Returns True iff the certificate
    proves UNSAT. No AST, no solver, no NOUS install. fractions only."""
    constraints = doc.get("constraints")
    multipliers = doc.get("multipliers")
    if not isinstance(constraints, list) or not isinstance(multipliers, list):
        return False
    if len(constraints) != len(multipliers):
        return False

    lam = []
    for m in multipliers:
        try:
            lam.append(Fraction(m))
        except (ValueError, TypeError, ZeroDivisionError):
            return False
    if any(x < 0 for x in lam):
        return False
    if not any(x > 0 for x in lam):
        return False

    combined = {}
    strict = False
    for x, c in zip(lam, constraints):
        if x == 0:
            continue
        if not isinstance(c, dict):
            return False
        coeffs = c.get("coeffs")
        if not isinstance(coeffs, dict):
            return False
        for k, v in coeffs.items():
            try:
                fv = Fraction(v)
            except (ValueError, TypeError, ZeroDivisionError):
                return False
            combined[k] = combined.get(k, Fraction(0)) + x * fv
        if c.get("strict"):
            strict = True

    for k, v in combined.items():
        if k != "" and v != 0:
            return False
    const = combined.get("", Fraction(0))
    if const > 0:
        return True
    if const == 0 and strict:
        return True
    return False


class MonotonicityOutOfFragment(FarkasError):  # __s121_monotonicity_helpers_v1__
    """A serialized constraint is malformed or outside the single linear
    comparison fragment; the containment system cannot be built."""


class MonotonicityIncomparable(FarkasError):  # __s121_monotonicity_helpers_v1__
    """Two thresholds live in different variable spaces; region containment
    is not a meaningful comparison (refused, never silently passed)."""


def negate_serialized(constraint: Any) -> dict:  # __s121_monotonicity_helpers_v1__
    """NOT of a normalized serialized constraint, as a serialized constraint.

    A normalized LinIneq is 'L (< if strict else <=) 0'.
      NOT(L < 0)  = (L >= 0) = (-L <= 0)   -> scale -1, strict False
      NOT(L <= 0) = (L > 0)  = (-L < 0)    -> scale -1, strict True
    Negation = scale every coeff (including the '' constant) by -1, flip
    strict. Defensive: refuses non-normalized / malformed input locally,
    because S121 negation does NOT pass through _comparison_to_ineq (which is
    what guarantees the normal form elsewhere). Raises MonotonicityOutOfFragment.
    """
    if not isinstance(constraint, dict):
        raise MonotonicityOutOfFragment(
            "negate_serialized: constraint is not a dict"
        )
    coeffs = constraint.get("coeffs")
    strict = constraint.get("strict")
    if not isinstance(coeffs, dict) or not isinstance(strict, bool):
        raise MonotonicityOutOfFragment(
            "negate_serialized: constraint missing coeffs/strict or wrong type"
        )
    neg_coeffs: dict = {}
    for k, v in coeffs.items():
        try:
            neg_coeffs[k] = str(-Fraction(v))
        except (ValueError, TypeError, ZeroDivisionError) as e:
            raise MonotonicityOutOfFragment(
                "negate_serialized: non-rational coefficient "
                + repr(v) + ": " + str(e)
            )
    return {"coeffs": neg_coeffs, "strict": (not strict)}


def _serialized_vars(constraint: Any) -> set:  # __s121_monotonicity_helpers_v1__
    """Variable set of a serialized constraint: coeffs keys minus the ''
    constant. Used for the comparability gate (cheap, pre-Farkas, no solver)."""
    if not isinstance(constraint, dict):
        raise MonotonicityOutOfFragment(
            "_serialized_vars: constraint is not a dict"
        )
    coeffs = constraint.get("coeffs")
    if not isinstance(coeffs, dict):
        raise MonotonicityOutOfFragment(
            "_serialized_vars: constraint has no coeffs dict"
        )
    return {k for k in coeffs if k != ""}


def _lin_from_serialized(constraint: dict) -> "LinIneq":  # __s121_monotonicity_helpers_v1__
    """Reconstruct a LinIneq from a serialized constraint (coeffs as rational
    strings, strict bool). No AST, no re-parse."""
    coeffs = {
        k: Fraction(v) for k, v in constraint["coeffs"].items()
    }
    return LinIneq(coeffs=coeffs, strict=bool(constraint["strict"]))


def serialize_containment(ineq_a: dict, ineq_b: dict) -> Optional[dict]:  # __s121_monotonicity_helpers_v1__
    """Prove region(T_a) subset-of region(T_b), i.e. T_a => T_b, i.e.
    T_a AND NOT(T_b) is UNSAT, as a serialized Farkas certificate.

    ineq_a, ineq_b are serialized constraints[0] (the threshold inequality)
    of the predecessor (a) and current (b) coverage.farkas.json certs, each
    normalized to 'L (< or <=) 0'. Builds the two-row system
    [ineq_a, negate(ineq_b)] directly from the serialized coeffs (no AST),
    then reuses the existing _find_farkas engine (single-source). Returns a
    check_serialized-compatible cert dict on a witness, or None when no
    witness exists (the system is satisfiable -> region NOT contained ->
    a real counterexample input lies in region(T_a) but outside region(T_b)).

    Raises MonotonicityIncomparable if the two thresholds use different
    variable sets (comparison is meaningless). Raises
    MonotonicityOutOfFragment on malformed input. NEVER returns a cert for an
    incomparable or malformed pair -- fail-closed.
    """
    vars_a = _serialized_vars(ineq_a)
    vars_b = _serialized_vars(ineq_b)
    if vars_a != vars_b:
        raise MonotonicityIncomparable(
            "incomparable thresholds: predecessor variables "
            + str(sorted(vars_a)) + " != current variables "
            + str(sorted(vars_b))
            + "; region containment across a changed variable space is not "
            "assertable (refused, not passed)"
        )
    neg_b = negate_serialized(ineq_b)
    system = [_lin_from_serialized(ineq_a), _lin_from_serialized(neg_b)]
    witness = _find_farkas(system)
    if witness is None:
        return None
    constraints = []
    for ineq in system:
        constraints.append(
            {
                "coeffs": {k: str(v) for k, v in sorted(ineq.coeffs.items())},
                "strict": bool(ineq.strict),
            }
        )
    return {
        "fragment": "linear-real-single-comparison-containment",
        "constraints": constraints,
        "multipliers": [str(m) for m in witness],
        "contradiction": _contradiction_str(system, witness),
    }


def region_contains(ineq_a: dict, ineq_b: dict) -> "tuple[bool, str]":  # __s121_region_contains_v1__
    """Closed-form: does region(T_a) lie inside region(T_b)?  i.e. T_a => T_b.

    ineq_a, ineq_b are serialized single-comparison constraints normalized
    to 'L (< if strict else <=) 0', over the SAME variable set (the caller's
    comparability gate guarantees this; this function does not assume it and
    refuses non-proportional geometry). Exact rational arithmetic only;
    never float. Returns (contained, reason): reason is "" when contained,
    else names the failed condition. Complete for the 2-row single-comparison
    fragment, so (False, reason) is a DEFINITIVE regression.
    """
    ca = ineq_a.get("coeffs")
    cb = ineq_b.get("coeffs")
    if not isinstance(ca, dict) or not isinstance(cb, dict):
        raise MonotonicityOutOfFragment(
            "region_contains: a constraint has no coeffs dict"
        )
    sa = ineq_a.get("strict")
    sb = ineq_b.get("strict")
    if not isinstance(sa, bool) or not isinstance(sb, bool):
        raise MonotonicityOutOfFragment(
            "region_contains: a constraint has no boolean strict flag"
        )

    # Variable union (excluding the '' constant), pivot from a STABLE sorted
    # order so t is not derived from dict insertion order.
    var_union = sorted(
        (set(ca) | set(cb)) - {""}
    )

    def _f(d: dict, k: str) -> Fraction:
        try:
            return Fraction(d.get(k, 0))
        except (ValueError, TypeError, ZeroDivisionError) as e:
            raise MonotonicityOutOfFragment(
                "region_contains: non-rational coefficient for "
                + repr(k) + ": " + str(e)
            )

    # Zero-coefficient cross-case, both directions, per variable.
    for v in var_union:
        av = _f(ca, v)
        bv = _f(cb, v)
        if (av == 0) != (bv == 0):
            return (
                False,
                "non-proportional: variable " + repr(v) + " is zero on one "
                "threshold and nonzero on the other (different geometry)",
            )

    # Pivot: first variable nonzero on BOTH sides (equal-zero vars skipped).
    pivot = None
    for v in var_union:
        if _f(ca, v) != 0:
            pivot = v
            break
    if pivot is None:
        # No nonzero variable coefficient on either side: degenerate
        # (constant-only) thresholds are outside the comparison fragment.
        raise MonotonicityOutOfFragment(
            "region_contains: threshold has no nonzero variable coefficient "
            "(degenerate, outside the single-comparison fragment)"
        )

    t = _f(cb, pivot) / _f(ca, pivot)
    if t <= 0:
        return (
            False,
            "anti-parallel: proportionality factor t=" + str(t)
            + " is not positive (the half-spaces face opposite directions)",
        )

    # Every variable coefficient must satisfy coeff_b == t * coeff_a exactly.
    for v in var_union:
        if _f(cb, v) != t * _f(ca, v):
            return (
                False,
                "non-proportional: coefficient of " + repr(v)
                + " does not scale by t=" + str(t),
            )

    # Offset slack: const_b <= t * const_a, with strict slack required when
    # T_a is non-strict and T_b is strict (shared-boundary exclusion).
    const_a = _f(ca, "")
    const_b = _f(cb, "")
    scaled_a = t * const_a
    if const_b > scaled_a:
        return (
            False,
            "insufficient-slack: const_b=" + str(const_b)
            + " > t*const_a=" + str(scaled_a)
            + " (region T_b does not cover region T_a)",
        )
    if const_b == scaled_a and (sa is False) and (sb is True):
        return (
            False,
            "strictness-violation: at the shared boundary the predecessor "
            "(<=) includes the boundary point but the current (<) excludes "
            "it (region shrank at the boundary)",
        )
    return (True, "")
