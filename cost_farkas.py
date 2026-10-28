"""Cost-cap Farkas certificate emitter and stdlib-only binding for NOUS
(S168 arc B, cost-cap upper-bound fragment).

The cost-cap obligation, as emitted by smt_emit.py, is the unsatisfiability of:

    AND over souls s:  cost_s_per_call = K_s         (K_s a constant rational)
    AND over souls s:  cost_s_total    = max_ticks * cost_s_per_call
                       total_cost      = SUM_s cost_s_total
    AND                total_cost      > effective_cap

over QF_LRA (set-logic (set-logic QF_LRA) in smt_emit.py). Every term is a
linear combination of variables (per-call / per-soul-total / total cost) with
constant rational coefficients; there is no variable*variable product, no
branch, no loop multiplier. The system is therefore a linear program and its
infeasibility admits a Farkas certificate: non-negative multipliers whose
weighted sum of the inequalities collapses to a numeric contradiction. Checking
that certificate is rational arithmetic alone -- no solver, no NOUS install --
which is exactly what coverage_farkas.check_serialized does. This module reuses
that shipped checker verbatim as the grader; it authors only the upper-bound
system and its closed-form witness.

Soundness, stated honestly. The system carried here is the UPPER-BOUND half:

    cost_s_per_call <= K_s
    cost_s_total    <= max_ticks * cost_s_per_call
    total_cost      <= SUM_s cost_s_total
    total_cost      >  effective_cap            (strict)

Its feasible region is a SUPERSET of the exact-equality SMT region, so proving
this superset infeasible implies the exact system is infeasible: the cap holds
even when every cost is allowed to be as large as its declared upper bound.
PROVES here is legitimate (it is a Farkas certificate) and is bounded to:
"under the declared per-call token estimates and the declared max_ticks, no
admissible execution exceeds effective_cap." It does NOT prove that the real
LLM honours those per-call token estimates -- that remains EVIDENCES via the
signed trace. NOUS is a monitor, not a guard.

Binding. check_serialized proves THIS linear system is unsat; it does not prove
the system is THIS program's cost model. check_serialized_cost re-derives the
system from the same structured inputs and rejects any substitution or
omission, and the manifest binds cost_farkas_sha256 (Ed25519-signed) to the
program -- the same two-tier model used for coverage_farkas_sha256.

# __s168_cost_farkas_emitter_v1__
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Optional, Union

from coverage_farkas import LinIneq, _contradiction_str, check_serialized

COST_CAP_FRAGMENT: str = "linear-real-cost-cap"
_MILLION: Fraction = Fraction(1_000_000)

Rational = Union[int, str, Decimal, Fraction]


class CostFarkasError(ValueError):
    """Raised on structurally invalid input to the cost-cap emitter
    (non-positive max_ticks, out-of-range margin, negative cost, empty
    soul set). Distinct from a non-provable cap, which is NOT an error:
    that returns None so the caller falls back to EVIDENCES."""


@dataclass(frozen=True)
class SoulCost:
    """One soul's resolved constant per-call cost (exact rational)."""
    name: str
    per_call: Fraction


def _as_fraction(value: Rational) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if isinstance(value, (int, str, Decimal)):
        return Fraction(value)
    raise CostFarkasError(
        "cost-cap input is not a rational scalar: " + repr(value)
    )


def per_call_rational(
    tokens_input: int,
    tokens_output: int,
    input_per_1m: Rational,
    output_per_1m: Rational,
    reasoning_mult: Rational,
) -> Fraction:
    """Exact-rational per-call cost, mirroring smt_emit._per_call_cost_smt:
        (input_per_1m * tokens_input
         + output_per_1m * tokens_output * reasoning_mult) / 1_000_000
    The reasoning_mult == 1 case is folded into the general formula
    (mult of 1 is the identity), so this stays byte-faithful to both SMT
    branches without duplicating the conditional."""
    if tokens_input < 0 or tokens_output < 0:
        raise CostFarkasError(
            "negative token estimate (input=" + str(tokens_input)
            + ", output=" + str(tokens_output) + ")"
        )
    inp = _as_fraction(input_per_1m)
    out = _as_fraction(output_per_1m)
    mult = _as_fraction(reasoning_mult)
    return (inp * tokens_input + out * tokens_output * mult) / _MILLION


def _effective_cap(cost_cap: Rational, margin_pct: int) -> Fraction:
    if not (0 <= margin_pct <= 99):
        raise CostFarkasError(
            "margin_pct out of range: " + str(margin_pct) + " (must be 0..99)"
        )
    cap = _as_fraction(cost_cap)
    if margin_pct == 0:
        return cap
    return cap * Fraction(100 - margin_pct, 100)


def _validated_souls(souls: list[SoulCost], max_ticks: int) -> list[SoulCost]:
    if not isinstance(max_ticks, int) or max_ticks <= 0:
        raise CostFarkasError(
            "max_ticks must be a positive integer, got " + repr(max_ticks)
        )
    if not souls:
        raise CostFarkasError("cost-cap system requires at least one soul")
    ordered = sorted(souls, key=lambda s: s.name)
    seen: set[str] = set()
    for s in ordered:
        if s.name in seen:
            raise CostFarkasError("duplicate soul name: " + repr(s.name))
        seen.add(s.name)
        if s.per_call < 0:
            raise CostFarkasError(
                "soul " + repr(s.name) + " has negative per-call cost"
            )
    return ordered


def build_cost_system(
    souls: list[SoulCost],
    max_ticks: int,
    effective_cap: Fraction,
) -> tuple[list[LinIneq], list[Fraction]]:
    """Build the upper-bound LinIneq system and its closed-form Farkas
    witness, in lockstep order. Multipliers align positionally with the
    constraints (the contract check_serialized relies on)."""
    ordered = _validated_souls(souls, max_ticks)
    m = Fraction(max_ticks)
    system: list[LinIneq] = []
    witness: list[Fraction] = []

    for s in ordered:
        per_call = "cost_" + s.name + "_per_call"
        total = "cost_" + s.name + "_total"
        system.append(
            LinIneq({per_call: Fraction(1), "": -s.per_call}, False)
        )
        witness.append(m)
        system.append(
            LinIneq({total: Fraction(1), per_call: -m, "": Fraction(0)}, False)
        )
        witness.append(Fraction(1))

    sum_row: dict = {"total_cost": Fraction(1), "": Fraction(0)}
    for s in ordered:
        sum_row["cost_" + s.name + "_total"] = Fraction(-1)
    system.append(LinIneq(sum_row, False))
    witness.append(Fraction(1))

    system.append(
        LinIneq({"total_cost": Fraction(-1), "": effective_cap}, True)
    )
    witness.append(Fraction(1))

    return system, witness


def _constraint_dict(ineq: LinIneq) -> dict:
    coeffs = dict(ineq.coeffs)
    coeffs.setdefault("", Fraction(0))
    return {
        "coeffs": {k: str(v) for k, v in sorted(coeffs.items())},
        "strict": bool(ineq.strict),
    }


def serialize_cost_system(
    souls: list[SoulCost],
    max_ticks: int,
    effective_cap: Fraction,
) -> dict:
    """Build the self-contained JSON-serializable cost-cap Farkas
    certificate. Raises CostFarkasError on structurally invalid input.
    Does NOT self-grade; callers use extract_cost_certificate for the
    fail-closed path."""
    system, witness = build_cost_system(souls, max_ticks, effective_cap)
    return {
        "fragment": COST_CAP_FRAGMENT,
        "cost_cap": str(effective_cap),
        "max_ticks": int(max_ticks),
        "constraints": [_constraint_dict(i) for i in system],
        "multipliers": [str(w) for w in witness],
        "contradiction": _contradiction_str(system, witness),
    }


def extract_cost_certificate(
    souls: list[SoulCost],
    max_ticks: int,
    cost_cap: Rational,
    margin_pct: int = 0,
) -> Optional[dict]:
    """Emit a cost-cap Farkas certificate, fail-closed.

    Returns the certificate dict iff the declared cap (after margin) holds
    AND the shipped stdlib grader (coverage_farkas.check_serialized)
    independently confirms the witness collapses the system to a numeric
    contradiction. Returns None when the cap is not provable (cost may
    reach or exceed it) -- the caller then ships EVIDENCES only, never a
    false PROVES. Raises CostFarkasError only on structurally invalid
    input."""
    effective_cap = _effective_cap(cost_cap, margin_pct)
    doc = serialize_cost_system(souls, max_ticks, effective_cap)
    if not check_serialized(doc):
        return None
    return doc


def check_serialized_cost(
    doc: object,
    souls: list[SoulCost],
    max_ticks: int,
    cost_cap: Rational,
    margin_pct: int = 0,
) -> bool:
    """Zero-trust check: re-derive the cost system from the same structured
    inputs (never taken from the document), require the document's
    constraint set to equal the re-derived set exactly (no substitution,
    omission, or surplus), then grade the multipliers with the shipped
    check_serialized. A document carrying a different -- even internally
    consistent -- linear system is rejected here, which is what binds the
    certificate to THIS program's cost model rather than to an arbitrary
    unsat system."""
    if not isinstance(doc, dict):
        return False
    try:
        effective_cap = _effective_cap(cost_cap, margin_pct)
        expected = serialize_cost_system(souls, max_ticks, effective_cap)
    except CostFarkasError:
        return False

    def _canon(constraints: object) -> Optional[list[str]]:
        if not isinstance(constraints, list):
            return None
        out: list[str] = []
        for c in constraints:
            if not isinstance(c, dict):
                return None
            coeffs = c.get("coeffs")
            if not isinstance(coeffs, dict):
                return None
            try:
                norm = {
                    str(k): str(Fraction(v)) for k, v in sorted(coeffs.items())
                }
            except (ValueError, TypeError, ZeroDivisionError):
                return None
            out.append(
                json.dumps(
                    {"coeffs": norm, "strict": bool(c.get("strict"))},
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        return sorted(out)

    want = _canon(expected.get("constraints"))
    got = _canon(doc.get("constraints"))
    if want is None or got is None or want != got:
        return False
    return check_serialized(doc)


def cost_farkas_json_bytes(doc: dict) -> bytes:
    """Canonical, byte-deterministic serialization of a cost-cap
    certificate (sorted keys, compact separators), matching the NOUS
    canonical-serialization invariant. These are the exact bytes hashed
    into manifest.cost_farkas_sha256 and written to cost.farkas.json."""
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def cost_farkas_sha256(doc: dict) -> str:
    return hashlib.sha256(cost_farkas_json_bytes(doc)).hexdigest()


def souls_from_smtspec(spec: object) -> list[SoulCost]:
    """Adapter: resolve each soul's exact constant per-call cost from an
    SMTSpec's structured soul_assumptions tuples
    (name, canonical, tokens_input, tokens_output, input_per_1m_str,
    output_per_1m_str, reasoning_mult_str). No pricing re-lookup and no
    SMT-string parsing: the certificate is derived from the same exact
    numbers smt_emit baked into the spec, which is itself
    smt_spec_sha256-bound to source and pricing."""
    assumptions = getattr(spec, "soul_assumptions", None)
    if not assumptions:
        raise CostFarkasError(
            "SMTSpec carries no soul_assumptions; cannot derive cost system"
        )
    souls: list[SoulCost] = []
    for row in assumptions:
        name, _canonical, tok_in, tok_out, in_rate, out_rate, mult = row
        souls.append(
            SoulCost(
                name=str(name),
                per_call=per_call_rational(
                    int(tok_in), int(tok_out), in_rate, out_rate, mult
                ),
            )
        )
    return souls


def cost_certificate_from_smtspec(spec: object) -> Optional[dict]:
    """Emit a cost-cap Farkas certificate directly from an SMTSpec,
    fail-closed. Returns None when the cap is not provable. The spec is
    not mutated and smt_emit.py is not touched (the byte-deterministic
    SMT spec and the 57-template regression are unaffected)."""
    souls = souls_from_smtspec(spec)
    return extract_cost_certificate(
        souls=souls,
        max_ticks=int(spec.max_ticks),
        cost_cap=spec.cost_cap_amount,
        margin_pct=int(getattr(spec, "cost_cap_margin_pct", 0) or 0),
    )


# --- cost rederive embed (shared text; canonical copy: cost_farkas.py) ---
# Every offline verifier that grades cost.farkas.json carries this region
# byte-for-byte; tests/test_nt_v1_cost_rederive.py names any copy that
# drifts. Standard library only. __nt_v1_cost_rederive_v1__
def _cost_rederive_grade(doc):
    from fractions import Fraction
    constraints = doc.get("constraints")
    multipliers = doc.get("multipliers")
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


def _cost_rederive_parse(canon_text):
    # The closed shapes smt_emit.canonical_str writes for the cost leg:
    # CC, MT, MARGIN, and four A: shapes. Any other A: line refuses.
    # Returns (per_call_by_soul, max_ticks, cap, margin) or a reason.
    import re
    from fractions import Fraction
    nm = r"[^\s()]+"
    rt = r"[0-9]+|\(/ [0-9]+ [0-9]+\)"
    re_cc = re.compile(r"CC:([0-9]+(?:\.[0-9]+)?)\|([A-Z]{3})")
    re_mt = re.compile(r"MT:([0-9]+)")
    re_mg = re.compile(r"MARGIN:([0-9]+)")
    re_pc = re.compile(
        r"A:\(assert \(= cost_(" + nm + r")_per_call \(/ \(\+ \(\* ("
        + rt + r") ([0-9]+)\) \(\* (" + rt + r") ([0-9]+)(?: ("
        + rt + r"))?\)\) 1000000\)\)\)"
    )
    re_tt = re.compile(
        r"A:\(assert \(= cost_(" + nm + r")_total \(\* cost_(" + nm
        + r")_per_call ([0-9]+)\)\)\)"
    )
    re_s1 = re.compile(
        r"A:\(assert \(= total_cost cost_(" + nm + r")_total\)\)"
    )
    re_sn = re.compile(
        r"A:\(assert \(= total_cost \(\+ ((?:cost_" + nm
        + r"_total)(?: cost_" + nm + r"_total)+)\)\)\)"
    )
    re_tok = re.compile(r"cost_(" + nm + r")_total")

    def rate(s):
        if s.startswith("(/ "):
            n, d = s[3:-1].split(" ")
            if int(d) == 0:
                return None
            return Fraction(int(n), int(d))
        return Fraction(int(s))

    head = {}
    per_call = {}
    totals = {}
    sums = []
    for line in canon_text.split("\n"):
        for tag, rx in (("CC", re_cc), ("MT", re_mt), ("MARGIN", re_mg)):
            if line.startswith(tag + ":"):
                if tag in head:
                    return "duplicate " + tag + " line"
                m = rx.fullmatch(line)
                if m is None:
                    return tag + " line outside the closed shape"
                head[tag] = m.group(1)
                break
        if not line.startswith("A:"):
            continue
        m = re_pc.fullmatch(line)
        if m is not None:
            soul = m.group(1)
            r_in, r_out = rate(m.group(2)), rate(m.group(4))
            mult = rate(m.group(6)) if m.group(6) else Fraction(1)
            if r_in is None or r_out is None or mult is None:
                return "zero denominator in a rate"
            if soul in per_call:
                return "duplicate per-call line for soul " + soul
            per_call[soul] = (
                r_in * int(m.group(3)) + r_out * int(m.group(5)) * mult
            ) / 1000000
            continue
        m = re_tt.fullmatch(line)
        if m is not None:
            if m.group(1) != m.group(2):
                return "total line names two souls"
            if m.group(1) in totals:
                return "duplicate total line for soul " + m.group(1)
            totals[m.group(1)] = int(m.group(3))
            continue
        m = re_s1.fullmatch(line)
        if m is not None:
            sums.append([m.group(1)])
            continue
        m = re_sn.fullmatch(line)
        if m is not None:
            sums.append([re_tok.fullmatch(t).group(1)
                         for t in m.group(1).split(" ")])
            continue
        return "A: line outside the closed shapes"
    if "CC" not in head or "MT" not in head:
        return "CC or MT line missing"
    max_ticks = int(head["MT"])
    margin = int(head.get("MARGIN", "0"))
    if max_ticks <= 0:
        return "max_ticks is not positive"
    if not 0 <= margin <= 99:
        return "margin out of range"
    if not per_call:
        return "no per-call cost line"
    if set(per_call) != set(totals):
        return "a soul lacks its per-call or its total line"
    if any(k != max_ticks for k in totals.values()):
        return "a total line multiplies by other than MT"
    if len(sums) != 1:
        return "expected exactly one total_cost line"
    if len(sums[0]) != len(set(sums[0])) or set(sums[0]) != set(per_call):
        return "total_cost does not sum each soul's total once"
    return per_call, max_ticks, Fraction(head["CC"]), margin


def _cost_rederive_leg(manifest, cost_doc, canon_text):
    # Re-derive the cost system from the spec canon the signed manifest
    # names (smt_spec_sha256), require the certificate's constraints to
    # equal it, then grade the multipliers. Pure; returns (bool, reason).
    import hashlib
    import json
    from fractions import Fraction
    if not isinstance(manifest, dict):
        return False, "manifest is not a JSON object"
    if not isinstance(canon_text, str):
        return False, (
            "no spec canon: the cost system cannot be re-derived, so the "
            "cost-cap Farkas certificate is not accepted"
        )
    want = manifest.get("smt_spec_sha256")
    got = hashlib.sha256(canon_text.encode("utf-8")).hexdigest()
    if not isinstance(want, str) or got != want:
        return False, (
            "spec canon sha256 != manifest smt_spec_sha256 (spec canon "
            "tampered or substituted)"
        )
    parsed = _cost_rederive_parse(canon_text)
    if isinstance(parsed, str):
        return False, "spec canon refused: " + parsed
    per_call, max_ticks, cap, margin = parsed
    try:
        man_cap = Fraction(str(manifest.get("cost_cap_usd")))
    except (ValueError, ZeroDivisionError):
        return False, "manifest cost_cap_usd is not a rational"
    if man_cap != cap:
        return False, "spec canon cap != manifest cost_cap_usd"
    man_mt = manifest.get("max_ticks")
    if type(man_mt) is not int or man_mt != max_ticks:
        return False, "spec canon max_ticks != manifest max_ticks"
    man_mg = manifest.get("safety_margin_pct")
    if man_mg is None:
        man_mg = 0
    if type(man_mg) is not int or man_mg != margin:
        return False, "spec canon margin != manifest safety_margin_pct"
    eff = cap if margin == 0 else cap * Fraction(100 - margin, 100)
    mt = Fraction(max_ticks)
    rows = []
    for soul in sorted(per_call):
        pc = "cost_" + soul + "_per_call"
        tt = "cost_" + soul + "_total"
        rows.append(({pc: Fraction(1), "": -per_call[soul]}, False))
        rows.append(({tt: Fraction(1), pc: -mt, "": Fraction(0)}, False))
    total = {"total_cost": Fraction(1), "": Fraction(0)}
    for soul in sorted(per_call):
        total["cost_" + soul + "_total"] = Fraction(-1)
    rows.append((total, False))
    rows.append(({"total_cost": Fraction(-1), "": eff}, True))

    def canon_rows(constraints):
        if not isinstance(constraints, list):
            return None
        out = []
        for c in constraints:
            if not isinstance(c, dict):
                return None
            coeffs = c.get("coeffs")
            if not isinstance(coeffs, dict):
                return None
            try:
                norm = {
                    str(k): str(Fraction(v))
                    for k, v in sorted(coeffs.items())
                }
            except (ValueError, TypeError, ZeroDivisionError):
                return None
            out.append(json.dumps(
                {"coeffs": norm, "strict": bool(c.get("strict"))},
                sort_keys=True, separators=(",", ":"),
            ))
        return sorted(out)

    if not isinstance(cost_doc, dict):
        return False, "cost certificate is not a JSON object"
    want_rows = canon_rows([{"coeffs": r, "strict": s} for r, s in rows])
    got_rows = canon_rows(cost_doc.get("constraints"))
    if got_rows is None or got_rows != want_rows:
        return False, (
            "cost certificate constraints != the cost system re-derived "
            "from the spec canon (substituted or forged certificate)"
        )
    if not _cost_rederive_grade(cost_doc):
        return False, (
            "cost-cap Farkas certificate does NOT prove the bound: the "
            "declared multipliers do not collapse the linear system to a "
            "numeric contradiction (cost overrun or forged certificate)"
        )
    return True, "re-derived from the spec canon, equal, and graded"
# --- end cost rederive embed ---
