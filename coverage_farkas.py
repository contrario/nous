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
        if op == "*":  # __s122_farkas_linear_mul_v1__
            return _linear_mul(
                _linear(node["left"]), _linear(node["right"])
            )
        raise FarkasError(f"non-linear operator {op!r} in term")
    raise FarkasError(f"unsupported term node {type(node).__name__!r}")


def _add(a: dict, b: dict, sign: int) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, Fraction(0)) + sign * v
    return out


def _scale(a: dict, s: Fraction) -> dict:
    return {k: v * s for k, v in a.items()}


def _is_const_only(d: dict) -> bool:  # __s122_farkas_linear_mul_v1__
    """True iff a linear term has no variable component (constant-only)."""
    return all(k == "" for k in d)


def _linear_mul(a: dict, b: dict) -> dict:  # __s122_farkas_linear_mul_v1__
    """Linear multiply: exactly one operand must be constant-only.
    c*x and x*c fold to a scaled term; x*y (both carry a variable) is
    bilinear and REFUSED as outside linear real arithmetic (QF_LRA)."""
    a_const = _is_const_only(a)
    b_const = _is_const_only(b)
    if a_const and b_const:
        return {"": a.get("", Fraction(0)) * b.get("", Fraction(0))}
    if a_const:
        return _scale(b, a.get("", Fraction(0)))
    if b_const:
        return _scale(a, b.get("", Fraction(0)))
    raise FarkasError(
        "bilinear term (variable * variable) outside linear real "
        "arithmetic (QF_LRA); only constant * variable is admitted"
    )


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


# ===========================================================================
# S124 -- Farkas DNF bundle (P3b-bool).  __s124_farkas_dnf_bundle_v1__
#
# Lifts the stdlib-checkable certificate from the single-linear-system
# fragment to Disjunctive Linear Arithmetic. The gap search
# T && NOT(B_1) && ... && NOT(B_n) is expanded to DNF over the NEGATION,
# and coverage is PROVEN iff EVERY disjunct of the negation carries a
# Farkas witness (the disjunct is unsat). The bundle is checkable with
# fractions alone. The checker does NOT trust the handed enumeration:
# it re-derives the disjunct set from the caller-supplied ASTs and
# requires a bijection (exactly one valid certificate per derived
# disjunct), so a bundle that omits the gap disjunct FAILS
# (no overclaim-by-omission). The bijection key is the full canonical
# serialization of the disjunct's constraints, so substitution and
# omission break the same check. var*var stays REFUSED (bilinear,
# outside QF_LRA). The DNF disjunct count is bounded with a typed
# REFUSE (DNF blowup is exponential; an unbounded expansion is never
# signed).
# ===========================================================================

DISJUNCT_BOUND: int = 64  # __s124_farkas_dnf_bundle_v1__

BUNDLE_FRAGMENT: str = "disjunctive-linear-bundle"

_FLIP_OP: dict = {">": "<=", ">=": "<", "<": ">=", "<=": ">"}

_CMP_OPS: tuple = (">", ">=", "<", "<=")


def _is_comparison(node: Any) -> bool:
    """True iff the node is a binop over a P3b-comparable operator."""
    return (
        isinstance(node, dict)
        and node.get("kind") == "binop"
        and node.get("op") in _CMP_OPS
    )


def _nnf(node: Any, negate: bool) -> Any:
    """Negation normal form over the boolean fragment (&& / || / ! over
    comparisons). Comparisons are the literals; negation is absorbed by
    flipping the comparison operator. Refuses (typed) outside the
    fragment, including ==/!=, bool literals, and bare names."""
    if _is_comparison(node):
        if not negate:
            return node
        flipped = dict(node)
        flipped["op"] = _FLIP_OP[node["op"]]
        return flipped
    if isinstance(node, dict) and node.get("kind") == "not":
        return _nnf(node["operand"], not negate)
    if (
        isinstance(node, dict)
        and node.get("kind") == "binop"
        and node.get("op") in ("&&", "and", "||", "or")
    ):
        is_and = node.get("op") in ("&&", "and")
        if negate:
            is_and = not is_and
        return {
            "kind": "binop",
            "op": "&&" if is_and else "||",
            "left": _nnf(node["left"], negate),
            "right": _nnf(node["right"], negate),
        }
    raise FarkasError(
        f"signal node outside the disjunctive linear fragment "
        f"(P3b-bool): {node!r}"
    )


def _dnf(node: Any, bound: int) -> list:
    """NNF tree -> disjunct list (each disjunct is a list of comparison
    dicts). Refuses (typed) when the disjunct count exceeds `bound`."""
    if _is_comparison(node):
        return [[node]]
    if isinstance(node, dict) and node.get("kind") == "binop":
        op = node.get("op")
        if op == "||":
            out = _dnf(node["left"], bound) + _dnf(node["right"], bound)
            if len(out) > bound:
                raise FarkasError(
                    f"DNF disjunct count exceeds bound {bound}; "
                    f"case-split refused (coverage stays "
                    f"z3-checkable-only)"
                )
            return out
        if op == "&&":
            left = _dnf(node["left"], bound)
            right = _dnf(node["right"], bound)
            if len(left) * len(right) > bound:
                raise FarkasError(
                    f"DNF disjunct count exceeds bound {bound}; "
                    f"case-split refused (coverage stays "
                    f"z3-checkable-only)"
                )
            return [a + b for a in left for b in right]
    raise FarkasError(f"non-NNF node in DNF expansion: {node!r}")


def _gap_disjuncts(
    threshold_ast: Any,
    blocking_signals: list,
    bound: int,
) -> list:
    """DNF of the gap search T && NOT(B_1) && ... && NOT(B_n)."""
    conj = _nnf(threshold_ast, False)
    for sig in blocking_signals:
        conj = {
            "kind": "binop",
            "op": "&&",
            "left": conj,
            "right": _nnf(sig, True),
        }
    return _dnf(conj, bound)


def _canon_constraint(ineq: "LinIneq") -> dict:
    """Canonical JSON-serializable form of one LinIneq (matches the v1
    serialize_system constraint shape byte-for-byte)."""
    return {
        "coeffs": {k: str(v) for k, v in sorted(ineq.coeffs.items())},
        "strict": bool(ineq.strict),
    }


def _canon_json(obj: Any) -> str:
    import json

    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _canon_system(comparisons: list) -> "tuple[list, list]":
    """Comparison dicts -> (canonical-sorted constraint dicts, the
    LinIneq system in the SAME order). Multipliers found against this
    order align with the canonical constraint order, so an independent
    checker that re-derives the same canonical system can verify them
    with zero positional trust."""
    pairs = []
    for comp in comparisons:
        ineq = _comparison_to_ineq(comp)
        pairs.append((_canon_constraint(ineq), ineq))
    pairs.sort(key=lambda p: _canon_json(p[0]))
    return [p[0] for p in pairs], [p[1] for p in pairs]


def serialize_bundle(
    threshold_ast: Any,
    blocking_signals: list,
    threshold_expr: "Optional[str]" = None,
) -> dict:
    """Build a self-contained, JSON-serializable Farkas certificate
    BUNDLE for the disjunctive linear fragment (boolean combinations of
    linear comparisons via && / || / !). One Farkas certificate per
    DNF disjunct of the negation T && !B; coverage is proven iff every
    disjunct is refuted. Raises FarkasError outside the fragment, when
    any disjunct lacks a witness (a gap may exist), or when the
    disjunct count exceeds DISJUNCT_BOUND."""
    disjuncts = _gap_disjuncts(
        threshold_ast, blocking_signals, DISJUNCT_BOUND
    )
    certs: dict = {}
    for comps in disjuncts:
        constraints, system = _canon_system(comps)
        key = _canon_json(constraints)
        if key in certs:
            continue
        witness = _find_farkas(system)
        if witness is None:
            raise FarkasError(
                "no Farkas witness for a gap disjunct: the disjunct is "
                "satisfiable (a coverage gap may exist) or outside the "
                "linear system the certificate can refute"
            )
        certs[key] = {
            "constraints": constraints,
            "multipliers": [str(m) for m in witness],
            "contradiction": _contradiction_str(system, witness),
        }
    cert_list = [certs[k] for k in sorted(certs)]
    doc: dict = {
        "fragment": BUNDLE_FRAGMENT,
        "threshold_expr": threshold_expr,
        "disjunct_count": len(cert_list),
        "certs": cert_list,
    }
    if _is_comparison(threshold_ast):
        doc["threshold_constraint"] = _canon_constraint(
            _comparison_to_ineq(threshold_ast)
        )
    return doc


def _check_multipliers(constraints: list, multipliers: list) -> bool:
    """Stdlib-only Farkas check of one (constraints, multipliers) pair:
    non-negative multipliers (at least one positive), the weighted sum
    cancels every variable, and the residual constant is a numeric
    contradiction. fractions only."""
    if not isinstance(constraints, list) or not isinstance(
        multipliers, list
    ):
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
    combined: dict = {}
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


def check_serialized_bundle(
    doc: Any,
    threshold_ast: Any,
    blocking_signals: list,
) -> bool:
    """Zero-trust check of a Farkas bundle. The disjunct set is
    RE-DERIVED from the supplied ASTs (never taken from the bundle),
    then a bijection is required: exactly one certificate per derived
    disjunct, keyed by the full canonical serialization of the
    disjunct's constraints. Each certificate's multipliers are checked
    against the RE-DERIVED constraints. A bundle that omits a disjunct,
    carries a surplus or duplicate certificate, substitutes a
    constraint, or forges a multiplier returns False."""
    if not isinstance(doc, dict) or doc.get("fragment") != BUNDLE_FRAGMENT:
        return False
    cert_list = doc.get("certs")
    if not isinstance(cert_list, list):
        return False
    try:
        disjuncts = _gap_disjuncts(
            threshold_ast, blocking_signals, DISJUNCT_BOUND
        )
    except FarkasError:
        return False
    derived: dict = {}
    for comps in disjuncts:
        try:
            constraints, _system = _canon_system(comps)
        except FarkasError:
            return False
        derived[_canon_json(constraints)] = constraints
    carried: dict = {}
    for cert in cert_list:
        if not isinstance(cert, dict):
            return False
        cons = cert.get("constraints")
        mults = cert.get("multipliers")
        if not isinstance(cons, list) or not isinstance(mults, list):
            return False
        norm = []
        for c in cons:
            if not isinstance(c, dict):
                return False
            coeffs = c.get("coeffs")
            if not isinstance(coeffs, dict):
                return False
            try:
                norm_coeffs = {
                    str(k): str(Fraction(v))
                    for k, v in sorted(coeffs.items())
                }
            except (ValueError, TypeError, ZeroDivisionError):
                return False
            norm.append(
                {"coeffs": norm_coeffs, "strict": bool(c.get("strict"))}
            )
        norm.sort(key=_canon_json)
        key = _canon_json(norm)
        if key in carried:
            return False
        carried[key] = mults
    if set(carried) != set(derived):
        return False
    for key, constraints in derived.items():
        if not _check_multipliers(constraints, carried[key]):
            return False
    return True


def serialize_auto(
    threshold_ast: Any,
    blocking_signals: list,
    threshold_expr: "Optional[str]" = None,
) -> dict:
    """Dispatch: the v1 single-system certificate when the obligation
    fits the v1 fragment (byte-identical emission, zero churn for all
    prior manifests), the DNF bundle when boolean structure is present.
    Raises FarkasError when neither path certifies."""
    try:
        return serialize_system(
            threshold_ast, blocking_signals, threshold_expr=threshold_expr
        )
    except FarkasError:
        return serialize_bundle(
            threshold_ast, blocking_signals, threshold_expr=threshold_expr
        )
HOP_FRAGMENT: str = "hop-containment-bundle"  # __s126_hop_bundle_v1__


def _hop_disjuncts(prev_ast: Any, cur_ast: Any, bound: int) -> list:
    """DNF of the hop containment obligation T_prev AND NOT(T_cur).
    Region containment T_prev subset-of T_cur over the reals holds iff
    this conjunction is unsatisfiable; within the disjunctive linear
    fragment Farkas refutation of every disjunct is complete."""
    conj = {
        "kind": "binop",
        "op": "&&",
        "left": _nnf(prev_ast, False),
        "right": _nnf(cur_ast, True),
    }
    return _dnf(conj, bound)


def serialize_hop_bundle(
    prev_ast: Any,
    cur_ast: Any,
    prev_expr: "Optional[str]" = None,
    cur_expr: "Optional[str]" = None,
) -> dict:
    """Build a self-contained, JSON-serializable hop-containment bundle
    proving region(T_prev) subset-of region(T_cur): one Farkas
    certificate per DNF disjunct of T_prev AND NOT(T_cur). Raises
    FarkasError outside the fragment, when the disjunct count exceeds
    DISJUNCT_BOUND, or when any disjunct is satisfiable -- i.e. the
    declared threshold region shrank or is not contained over the
    joint variable space (a DEFINITIVE non-containment within the
    fragment, caught at issuance)."""
    disjuncts = _hop_disjuncts(prev_ast, cur_ast, DISJUNCT_BOUND)
    certs: dict = {}
    for comps in disjuncts:
        constraints, system = _canon_system(comps)
        key = _canon_json(constraints)
        if key in certs:
            continue
        witness = _find_farkas(system)
        if witness is None:
            raise FarkasError(
                "no Farkas witness for a hop disjunct: T_prev AND "
                "NOT(T_cur) is satisfiable -- the declared threshold "
                "region shrank across this re-binding, or the "
                "predecessor region is not contained in the current "
                "one over the joint variable space"
            )
        certs[key] = {
            "constraints": constraints,
            "multipliers": [str(m) for m in witness],
            "contradiction": _contradiction_str(system, witness),
        }
    cert_list = [certs[k] for k in sorted(certs)]
    return {
        "fragment": HOP_FRAGMENT,
        "prev_threshold_expr": prev_expr,
        "cur_threshold_expr": cur_expr,
        "disjunct_count": len(cert_list),
        "certs": cert_list,
    }


def check_serialized_hop_bundle(
    doc: Any,
    prev_ast: Any,
    cur_ast: Any,
) -> bool:
    """Zero-trust check of a hop-containment bundle. The disjunct set
    is RE-DERIVED from the supplied ASTs (never taken from the bundle),
    then a bijection is required: exactly one certificate per derived
    disjunct, keyed by the canonical serialization of the disjunct's
    constraints, each checked by rational arithmetic alone. A bundle
    that omits a disjunct, carries a surplus or duplicate certificate,
    substitutes a constraint, or forges a multiplier returns False."""
    if not isinstance(doc, dict) or doc.get("fragment") != HOP_FRAGMENT:
        return False
    cert_list = doc.get("certs")
    if not isinstance(cert_list, list):
        return False
    try:
        disjuncts = _hop_disjuncts(prev_ast, cur_ast, DISJUNCT_BOUND)
    except FarkasError:
        return False
    derived: dict = {}
    for comps in disjuncts:
        try:
            constraints, _system = _canon_system(comps)
        except FarkasError:
            return False
        derived[_canon_json(constraints)] = constraints
    carried: dict = {}
    for cert in cert_list:
        if not isinstance(cert, dict):
            return False
        cons = cert.get("constraints")
        mults = cert.get("multipliers")
        if not isinstance(cons, list) or not isinstance(mults, list):
            return False
        norm = []
        for c in cons:
            if not isinstance(c, dict):
                return False
            coeffs = c.get("coeffs")
            if not isinstance(coeffs, dict):
                return False
            try:
                norm_coeffs = {
                    str(k): str(Fraction(v))
                    for k, v in sorted(coeffs.items())
                }
            except (ValueError, TypeError, ZeroDivisionError):
                return False
            norm.append(
                {"coeffs": norm_coeffs, "strict": bool(c.get("strict"))}
            )
        norm.sort(key=_canon_json)
        key = _canon_json(norm)
        if key in carried:
            return False
        carried[key] = mults
    if set(carried) != set(derived):
        return False
    for key, constraints in derived.items():
        if not _check_multipliers(constraints, carried[key]):
            return False
    return True


NET_FRAGMENT: str = "blocking-net-containment-bundle"  # __s127_net_bundle_v1__


def _net_disjuncts(
    prev_sigs: list, cur_sigs: list, bound: int
) -> list:
    """DNF of the blocking-net containment obligation
    OR(prev_sigs) AND AND(NOT cur_sigs). A real point witnesses
    non-containment iff it is blocked by some predecessor signal yet
    by no current signal; region containment net(prev) subset-of
    net(cur) holds over the reals iff this conjunction is
    unsatisfiable. Within the disjunctive linear fragment Farkas
    refutation of every disjunct is complete. An empty predecessor net
    yields no disjuncts (vacuous containment)."""
    if not prev_sigs:
        return []
    prev_or: Any = _nnf(prev_sigs[0], False)
    for sig in prev_sigs[1:]:
        prev_or = {
            "kind": "binop",
            "op": "||",
            "left": prev_or,
            "right": _nnf(sig, False),
        }
    conj: Any = prev_or
    for sig in cur_sigs:
        conj = {
            "kind": "binop",
            "op": "&&",
            "left": conj,
            "right": _nnf(sig, True),
        }
    return _dnf(conj, bound)


def serialize_net_bundle(
    prev_sigs: list,
    cur_sigs: list,
) -> dict:
    """Build a self-contained, JSON-serializable blocking-net
    containment bundle proving net(prev) subset-of net(cur): one
    Farkas certificate per DNF disjunct of
    OR(prev_sigs) AND AND(NOT cur_sigs). Raises FarkasError outside
    the fragment, when the disjunct count exceeds DISJUNCT_BOUND, or
    when any disjunct is satisfiable -- i.e. the predecessor blocking
    net is not contained in the current one over the joint variable
    space (a DEFINITIVE non-containment within the fragment, including
    the case where the current net is empty while the predecessor net
    is not: the net vanished). An empty predecessor net produces an
    empty certificate list (vacuous containment)."""
    disjuncts = _net_disjuncts(prev_sigs, cur_sigs, DISJUNCT_BOUND)
    certs: dict = {}
    for comps in disjuncts:
        constraints, system = _canon_system(comps)
        key = _canon_json(constraints)
        if key in certs:
            continue
        witness = _find_farkas(system)
        if witness is None:
            raise FarkasError(
                "no Farkas witness for a blocking-net disjunct: "
                "OR(prev_sigs) AND AND(NOT cur_sigs) is satisfiable -- "
                "the predecessor blocking net is not contained in the "
                "current one over the joint variable space (the net "
                "shrank or vanished across this re-binding)"
            )
        certs[key] = {
            "constraints": constraints,
            "multipliers": [str(m) for m in witness],
            "contradiction": _contradiction_str(system, witness),
        }
    cert_list = [certs[k] for k in sorted(certs)]
    return {
        "fragment": NET_FRAGMENT,
        "disjunct_count": len(cert_list),
        "certs": cert_list,
    }


def check_serialized_net_bundle(
    doc: Any,
    prev_sigs: list,
    cur_sigs: list,
) -> bool:
    """Zero-trust check of a blocking-net containment bundle. The
    disjunct set is RE-DERIVED from the supplied signal ASTs (never
    taken from the bundle), then a bijection is required: exactly one
    certificate per derived disjunct, keyed by the canonical
    serialization of the disjunct's constraints, each checked by
    rational arithmetic alone. An empty predecessor net derives no
    disjuncts and requires an empty certificate list. A bundle that
    omits a disjunct, carries a surplus or duplicate certificate,
    substitutes a constraint, or forges a multiplier returns False."""
    if not isinstance(doc, dict) or doc.get("fragment") != NET_FRAGMENT:
        return False
    cert_list = doc.get("certs")
    if not isinstance(cert_list, list):
        return False
    try:
        disjuncts = _net_disjuncts(prev_sigs, cur_sigs, DISJUNCT_BOUND)
    except FarkasError:
        return False
    derived: dict = {}
    for comps in disjuncts:
        try:
            constraints, _system = _canon_system(comps)
        except FarkasError:
            return False
        derived[_canon_json(constraints)] = constraints
    carried: dict = {}
    for cert in cert_list:
        if not isinstance(cert, dict):
            return False
        cons = cert.get("constraints")
        mults = cert.get("multipliers")
        if not isinstance(cons, list) or not isinstance(mults, list):
            return False
        norm = []
        for c in cons:
            if not isinstance(c, dict):
                return False
            coeffs = c.get("coeffs")
            if not isinstance(coeffs, dict):
                return False
            try:
                norm_coeffs = {
                    str(k): str(Fraction(v))
                    for k, v in sorted(coeffs.items())
                }
            except (ValueError, TypeError, ZeroDivisionError):
                return False
            norm.append(
                {"coeffs": norm_coeffs, "strict": bool(c.get("strict"))}
            )
        norm.sort(key=_canon_json)
        key = _canon_json(norm)
        if key in carried:
            return False
        carried[key] = mults
    if set(carried) != set(derived):
        return False
    for key, constraints in derived.items():
        if not _check_multipliers(constraints, carried[key]):
            return False
    return True


GAP_WITNESS_FRAGMENT: str = "coverage-gap-witness"  # __s132_gap_witness_v1__


def _point_satisfies(point: dict, system: list) -> bool:
    """True iff the rational assignment `point` satisfies every LinIneq in
    `system` (each in 'L (< | <=) 0' form). The caller guarantees `point`
    assigns every non-constant variable referenced by `system`."""
    for ineq in system:
        lhs = Fraction(0)
        for k, v in ineq.coeffs.items():
            lhs += v if k == "" else v * point[k]
        if ineq.strict:
            if not (lhs < 0):
                return False
        elif not (lhs <= 0):
            return False
    return True


def serialize_gap_witness(
    threshold_ast: Any,
    blocking_signals: list,
    point: dict,
    threshold_expr: "Optional[str]" = None,
) -> dict:
    """Build a self-contained, JSON-serializable coverage-gap-witness: a
    concrete rational point lying in a DNF disjunct of
    T && NOT(B_1) && ... && NOT(B_n) -- inside the threshold region T while
    escaping every blocking signal. This is the DUAL of serialize_bundle:
    where the bundle proves NO gap (every disjunct refuted by a Farkas
    certificate), the witness proves a gap EXISTS at this point. The two are
    mutually exclusive over the same (T, B): a satisfying point exists iff
    some disjunct is satisfiable iff serialize_bundle refuses.

    Raises FarkasError if `point` carries a non-rational coordinate, or if
    it witnesses no gap disjunct (it lies in no disjunct of T && NOT(B): the
    threshold region is covered at this point, or the point is not in
    T-and-unblocked). No solver is used; the point's satisfaction of a
    disjunct IS the satisfiability proof.

    The witness is checked offline by check_serialized_gap_witness with
    Fraction arithmetic alone: it proves THIS point is admitted by the
    threshold and caught by no blocking signal. It does NOT prove the agent
    misbehaves there, nor that the gap is unique or maximal."""
    pt: dict = {}
    for k, v in point.items():
        try:
            pt[str(k)] = Fraction(v)
        except (ValueError, TypeError, ZeroDivisionError):
            raise FarkasError(
                "gap-witness point has a non-rational coordinate: " + repr(k)
            )
    disjuncts = _gap_disjuncts(threshold_ast, blocking_signals, DISJUNCT_BOUND)
    for comps in disjuncts:
        constraints, system = _canon_system(comps)
        needed = set()
        for ineq in system:
            for vk in ineq.coeffs:
                if vk != "":
                    needed.add(vk)
        if not needed.issubset(set(pt)):
            continue
        if _point_satisfies(pt, system):
            return {
                "fragment": GAP_WITNESS_FRAGMENT,
                "threshold_expr": threshold_expr,
                "disjunct": constraints,
                "point": {k: str(pt[k]) for k in sorted(pt)},
            }
    raise FarkasError(
        "supplied point witnesses no coverage gap: it lies in no DNF "
        "disjunct of T && NOT(B) (the threshold region is covered here, or "
        "the point is not in T-and-unblocked)"
    )


def check_serialized_gap_witness(
    doc: Any,
    threshold_ast: Any,
    blocking_signals: list,
) -> bool:
    """Zero-trust check of a coverage-gap-witness. The gap disjunct set is
    RE-DERIVED from the supplied threshold AST and blocking signals (never
    taken from the document); the document's `disjunct` field only SELECTS
    which derived disjunct is claimed, by canonical key. The witness point
    is then evaluated against the RE-DERIVED constraints of that disjunct by
    rational arithmetic alone. Returns True iff the claimed disjunct
    actually derives and the point lies in it (in T, blocked by no signal).
    A document that claims a non-derived disjunct, omits a variable of the
    disjunct, carries a non-rational coordinate, or supplies a point outside
    the disjunct returns False."""
    if not isinstance(doc, dict) or doc.get("fragment") != GAP_WITNESS_FRAGMENT:
        return False
    point = doc.get("point")
    cons = doc.get("disjunct")
    if not isinstance(point, dict) or not isinstance(cons, list):
        return False
    norm = []
    for c in cons:
        if not isinstance(c, dict):
            return False
        coeffs = c.get("coeffs")
        if not isinstance(coeffs, dict):
            return False
        try:
            norm_coeffs = {
                str(k): str(Fraction(v)) for k, v in sorted(coeffs.items())
            }
        except (ValueError, TypeError, ZeroDivisionError):
            return False
        norm.append({"coeffs": norm_coeffs, "strict": bool(c.get("strict"))})
    norm.sort(key=_canon_json)
    key = _canon_json(norm)
    try:
        disjuncts = _gap_disjuncts(
            threshold_ast, blocking_signals, DISJUNCT_BOUND
        )
    except FarkasError:
        return False
    systems: dict = {}
    for comps in disjuncts:
        try:
            constraints, system = _canon_system(comps)
        except FarkasError:
            return False
        systems[_canon_json(constraints)] = system
    if key not in systems:
        return False
    pt: dict = {}
    for k, v in point.items():
        try:
            pt[str(k)] = Fraction(v)
        except (ValueError, TypeError, ZeroDivisionError):
            return False
    system = systems[key]
    needed = set()
    for ineq in system:
        for vk in ineq.coeffs:
            if vk != "":
                needed.add(vk)
    if not needed.issubset(set(pt)):
        return False
    return _point_satisfies(pt, system)
