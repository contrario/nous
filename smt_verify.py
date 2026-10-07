"""
NOUS smt_verify — run an SMT solver against an SMTSpec and produce
a verdict + (on refutation) a human-readable counterexample with
constructive fix suggestions.

The solver is z3 (pinned in the [smt] extra). z3 is imported lazily
inside verify() so this module loads even when z3 is absent — but
verify() itself requires z3.

Public API:
  VerifyResult         frozen dataclass
  CounterExample       frozen dataclass
  verify(spec, ...)    -> VerifyResult
  format_verdict(...)  -> str (human-readable summary)
  verify_sequence(spec, ...)        -> SequenceVerifyResult
  format_sequence_verdict(...)      -> str (ASCII summary)

# __nous_smt_verify_module_v1__
"""
from __future__ import annotations
# __session64_smt_margin_v1__

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction  # __s402_cost_bound_display_v1__
from typing import Literal, Optional

from smt_emit import SMTSpec


# ─────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────

Verdict = Literal["proven", "refuted", "unknown", "error"]
SequenceVerdict = Literal[  # __phase2_stage4_seq_verify_v1__
    "consistent", "inconsistent", "vacuous", "unknown", "error"
]


@dataclass(frozen=True)
class SoulOverage:
    """Counterexample contribution from one soul."""
    soul_name: str
    canonical_model: str
    per_call_usd: Decimal
    total_usd: Decimal


@dataclass(frozen=True)
class CounterExample:
    """Z3 counterexample extracted from a refuted obligation.

    All values are exact Decimals from z3's RatNumRef.
    """
    total_cost_usd: Decimal
    cap_usd: Decimal
    overage_usd: Decimal
    overage_pct: Decimal
    max_ticks: int
    per_soul: tuple[SoulOverage, ...]
    largest_contributor: Optional[str] = None


@dataclass(frozen=True)
class VerifyResult:
    """Outcome of running the solver against a spec.

    On verdict='proven', counterexample is None.
    On verdict='refuted', counterexample is populated.
    On verdict='unknown' or 'error', error contains the reason.
    """
    verdict: Verdict
    spec: SMTSpec
    solver_name: str
    solver_version: str
    elapsed_ms: int
    timestamp_utc: str
    counterexample: Optional[CounterExample] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class CoverageCounterExample:  # __policy_coverage_verify_v1__
    """A concrete over-threshold input left uncovered (gap witness)."""
    assignment: tuple[tuple[str, str], ...]


CoverageVerdict = Literal[  # __policy_coverage_verify_v1__
    "proven", "refuted", "unknown", "error", "vacuous"
]


@dataclass(frozen=True)
class CoverageVerifyResult:  # __policy_coverage_verify_v1__
    """Outcome of running the solver against a spec's coverage script.

    proven  : z3 unsat -- no over-threshold input is uncovered.
    refuted : z3 sat   -- a gap exists; counterexample populated.
    vacuous : the spec declares no coverage obligation; z3 not run.
    unknown : z3 timeout / returned unknown.
    error   : z3 unavailable or a parse/check error.
    """
    verdict: CoverageVerdict
    spec: SMTSpec
    solver_name: str
    solver_version: str
    elapsed_ms: int
    timestamp_utc: str
    counterexample: Optional[CoverageCounterExample] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class SequenceVerifyResult:  # __phase2_stage4_seq_verify_v1__
    """Outcome of running the solver against a spec's sequence script.

    consistent  : z3 sat -- the 'before' laws admit a valid total order.
    inconsistent: z3 unsat -- the laws contradict (e.g. before(a,b)+before(b,a)).
    vacuous     : the spec declares no sequence laws; z3 is not invoked.
    unknown     : z3 timeout / returned unknown.
    error       : z3 unavailable or a parse/check error.
    """
    verdict: SequenceVerdict
    spec: SMTSpec
    solver_name: str
    solver_version: str
    elapsed_ms: int
    timestamp_utc: str
    error: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────
# z3 helpers (lazy import)
# ─────────────────────────────────────────────────────────────────────

def _solver_version() -> str:
    """Return z3 version string, or 'unavailable'."""
    try:
        import z3
        return f"z3 {z3.get_version_string()}"
    except Exception:
        return "z3 unavailable"


def _ratnum_to_decimal(v) -> Decimal:
    """Convert z3 RatNumRef / IntNumRef to exact Decimal.

    z3 stores rationals as (num, den) integer pairs. We rebuild the
    exact Decimal via Fraction; no float passes through.
    """
    from fractions import Fraction
    try:
        n = v.numerator_as_long()
        d = v.denominator_as_long()
    except AttributeError:
        # IntNumRef
        return Decimal(v.as_long())
    return Decimal(n) / Decimal(d)


def _strip_check_sat(smt_text: str) -> str:
    """Remove (check-sat) so z3 from_string only parses the body."""
    return "\n".join(
        line for line in smt_text.splitlines()
        if not line.strip().startswith("(check-sat")
    )


# ─────────────────────────────────────────────────────────────────────
# Counterexample extraction
# ─────────────────────────────────────────────────────────────────────

def _extract_counterexample(
    spec: SMTSpec,
    z3_model,
) -> CounterExample:
    """Read soul-level cost variables out of the z3 model."""
    cap = spec.cost_cap_amount
    name_to_var = {decl.name(): decl for decl in z3_model.decls()}

    total_cost = Decimal("0")
    if "total_cost" in name_to_var:
        total_cost = _ratnum_to_decimal(z3_model[name_to_var["total_cost"]])

    per_soul: list[SoulOverage] = []
    largest: Optional[str] = None
    largest_total = Decimal("0")

    for canonical_model, soul_name, _per_call_expr in spec.soul_costs:
        per_call_var = f"cost_{soul_name}_per_call"
        total_var = f"cost_{soul_name}_total"
        per_call_val = Decimal("0")
        total_val = Decimal("0")
        if per_call_var in name_to_var:
            per_call_val = _ratnum_to_decimal(
                z3_model[name_to_var[per_call_var]]
            )
        if total_var in name_to_var:
            total_val = _ratnum_to_decimal(
                z3_model[name_to_var[total_var]]
            )
        per_soul.append(SoulOverage(
            soul_name=soul_name,
            canonical_model=canonical_model,
            per_call_usd=per_call_val,
            total_usd=total_val,
        ))
        if total_val > largest_total:
            largest_total = total_val
            largest = soul_name

    overage = total_cost - cap
    overage_pct = (
        (overage / cap * Decimal("100"))
        if cap > 0 else Decimal("0")
    )

    return CounterExample(
        total_cost_usd=total_cost,
        cap_usd=cap,
        overage_usd=overage,
        overage_pct=overage_pct,
        max_ticks=spec.max_ticks,
        per_soul=tuple(per_soul),
        largest_contributor=largest,
    )


# ─────────────────────────────────────────────────────────────────────
# Public verify()
# ─────────────────────────────────────────────────────────────────────

def verify(
    spec: SMTSpec,
    timeout_ms: int = 30_000,
) -> VerifyResult:
    """Run z3 against the spec; return verdict + (if refuted) counterexample.

    timeout_ms: solver budget. 30s default is generous for QF_LRA
    over typical NOUS programs (sub-second in practice).
    """
    started: float = time.monotonic()
    ts: str = datetime.now(timezone.utc).isoformat(timespec="seconds")

    try:
        import z3
    except ImportError:
        return VerifyResult(
            verdict="error",
            spec=spec,
            solver_name="z3",
            solver_version="unavailable",
            elapsed_ms=0,
            timestamp_utc=ts,
            error="z3-solver not installed; install with "
                  "`pip install nous-lang[smt]`",
        )

    body: str = _strip_check_sat(spec.serialize())
    solver = z3.Solver()
    solver.set("timeout", int(timeout_ms))

    try:
        solver.from_string(body)
    except z3.Z3Exception as e:
        return VerifyResult(
            verdict="error",
            spec=spec,
            solver_name="z3",
            solver_version=_solver_version(),
            elapsed_ms=int((time.monotonic() - started) * 1000),
            timestamp_utc=ts,
            error=f"z3 parse error: {e}",
        )

    try:
        check = solver.check()
    except z3.Z3Exception as e:
        return VerifyResult(
            verdict="error",
            spec=spec,
            solver_name="z3",
            solver_version=_solver_version(),
            elapsed_ms=int((time.monotonic() - started) * 1000),
            timestamp_utc=ts,
            error=f"z3 check error: {e}",
        )

    elapsed_ms: int = int((time.monotonic() - started) * 1000)

    if check == z3.unsat:
        return VerifyResult(
            verdict="proven",
            spec=spec,
            solver_name="z3",
            solver_version=_solver_version(),
            elapsed_ms=elapsed_ms,
            timestamp_utc=ts,
        )

    if check == z3.sat:
        try:
            model = solver.model()
            ce = _extract_counterexample(spec, model)
        except Exception as e:
            return VerifyResult(
                verdict="error",
                spec=spec,
                solver_name="z3",
                solver_version=_solver_version(),
                elapsed_ms=elapsed_ms,
                timestamp_utc=ts,
                error=f"counterexample extraction failed: {e}",
            )
        return VerifyResult(
            verdict="refuted",
            spec=spec,
            solver_name="z3",
            solver_version=_solver_version(),
            elapsed_ms=elapsed_ms,
            timestamp_utc=ts,
            counterexample=ce,
        )

    # z3.unknown
    return VerifyResult(
        verdict="unknown",
        spec=spec,
        solver_name="z3",
        solver_version=_solver_version(),
        elapsed_ms=elapsed_ms,
        timestamp_utc=ts,
        error=f"z3 returned unknown (timeout {timeout_ms}ms or "
              f"complexity); solver reason: "
              f"{solver.reason_unknown()}",
    )


def verify_sequence(  # __phase2_stage4_seq_verify_v1__
    spec: SMTSpec,
    timeout_ms: int = 30_000,
) -> SequenceVerifyResult:
    """Run z3 against the spec's sequence-consistency script.

    Polarity is INVERTED relative to verify(): the sequence script
    asserts the ordering constraints directly, so SAT means the laws
    are jointly satisfiable (a valid total order exists) and UNSAT
    means they contradict. A spec with no sequence laws is 'vacuous'
    and z3 is not invoked.
    """
    started: float = time.monotonic()
    ts: str = datetime.now(timezone.utc).isoformat(timespec="seconds")

    script: Optional[str] = spec.serialize_sequence()
    if script is None:
        # __phase2_stage8b_at_most_verify_v1__: a law set with no SMT assertions
        # (at_most-only) is trivially consistent -- a cardinality
        # bound imposes no ordering, so z3 is not invoked. Only an
        # EMPTY law set is vacuous.
        verdict_no_script = (
            "vacuous" if not spec.sequence_laws else "consistent"
        )
        return SequenceVerifyResult(
            verdict=verdict_no_script,
            spec=spec,
            solver_name="z3",
            solver_version="n/a",
            elapsed_ms=0,
            timestamp_utc=ts,
        )

    try:
        import z3
    except ImportError:
        return SequenceVerifyResult(
            verdict="error",
            spec=spec,
            solver_name="z3",
            solver_version="unavailable",
            elapsed_ms=0,
            timestamp_utc=ts,
            error="z3-solver not installed; install with "
                  "`pip install nous-lang[smt]`",
        )

    body: str = _strip_check_sat(script)
    solver = z3.Solver()
    solver.set("timeout", int(timeout_ms))

    try:
        solver.from_string(body)
    except z3.Z3Exception as e:
        return SequenceVerifyResult(
            verdict="error",
            spec=spec,
            solver_name="z3",
            solver_version=_solver_version(),
            elapsed_ms=int((time.monotonic() - started) * 1000),
            timestamp_utc=ts,
            error=f"z3 parse error: {e}",
        )

    try:
        check = solver.check()
    except z3.Z3Exception as e:
        return SequenceVerifyResult(
            verdict="error",
            spec=spec,
            solver_name="z3",
            solver_version=_solver_version(),
            elapsed_ms=int((time.monotonic() - started) * 1000),
            timestamp_utc=ts,
            error=f"z3 check error: {e}",
        )

    elapsed_ms: int = int((time.monotonic() - started) * 1000)

    if check == z3.sat:
        return SequenceVerifyResult(
            verdict="consistent",
            spec=spec,
            solver_name="z3",
            solver_version=_solver_version(),
            elapsed_ms=elapsed_ms,
            timestamp_utc=ts,
        )

    if check == z3.unsat:
        return SequenceVerifyResult(
            verdict="inconsistent",
            spec=spec,
            solver_name="z3",
            solver_version=_solver_version(),
            elapsed_ms=elapsed_ms,
            timestamp_utc=ts,
            error="declared ordering laws contradict; no total order "
                  "satisfies all ordering constraints",
        )

    return SequenceVerifyResult(
        verdict="unknown",
        spec=spec,
        solver_name="z3",
        solver_version=_solver_version(),
        elapsed_ms=elapsed_ms,
        timestamp_utc=ts,
        error=f"z3 returned unknown (timeout {timeout_ms}ms); reason: "
              f"{solver.reason_unknown()}",
    )


# ─────────────────────────────────────────────────────────────────────
# Human-readable formatting
# ─────────────────────────────────────────────────────────────────────

def _suggest_min_cap(ce: CounterExample) -> Decimal:
    """Smallest cap that would make the obligation provable.

    Round up to 4 decimal places ($0.0001 granularity) so the
    suggestion is a real, copy-pasteable amount.
    """
    if ce.total_cost_usd <= 0:
        return Decimal("0.0001")
    # Round up to 4 dp.
    cents = (ce.total_cost_usd * Decimal("10000")).to_integral_value(
        rounding="ROUND_CEILING"
    )
    return cents / Decimal("10000")


def _suggest_max_ticks_reduction(
    ce: CounterExample,
) -> Optional[int]:
    """How many ticks would fit under the existing cap.

    Returns None if even max_ticks=1 still overshoots.
    """
    if ce.max_ticks <= 0 or not ce.per_soul:
        return None
    per_tick_total = sum(
        (s.per_call_usd for s in ce.per_soul),
        start=Decimal("0"),
    )
    if per_tick_total <= 0:
        return None
    if per_tick_total > ce.cap_usd:
        return None
    # floor(cap / per_tick_total)
    fit = (ce.cap_usd / per_tick_total).to_integral_value(
        rounding="ROUND_FLOOR"
    )
    return int(fit) if fit >= 1 else None


class CostDisplayError(ValueError):  # __s402_cost_bound_display_v1__
    """The declared cost lines were refused. The message starts with the
    name of the first check that failed: check_serialized, variable
    cancellation, check_serialized_cost or byte equality
    (docs/COST_BOUND_DISPLAY_DESIGN.md D400-3, D401-1)."""


NO_CERTIFICATE_NONE: str = (  # __s402_cost_bound_display_v1__
    "no certificate: the certificate extractor returned none for this spec"
)
NO_CERTIFICATE_RAISED: str = (  # __s402_cost_bound_display_v1__
    "no certificate: certificate extraction raised CostFarkasError"
)


def _exact_decimal(value: Fraction) -> Optional[str]:  # __s402_cost_bound_display_v1__
    den = value.denominator
    twos = 0
    fives = 0
    while den % 2 == 0:
        den //= 2
        twos += 1
    while den % 5 == 0:
        den //= 5
        fives += 1
    if den != 1:
        return None
    places = max(twos, fives)
    scaled = abs(value.numerator) * (10 ** places) // value.denominator
    digits = str(scaled).rjust(places + 1, "0")
    body = digits if places == 0 else digits[:-places] + "." + digits[-places:]
    return ("-" if value < 0 else "") + body


def _amount(value: Fraction, currency: str) -> str:  # __s402_cost_bound_display_v1__
    dec = _exact_decimal(value)
    if dec is None:
        return f"{value} {currency}"
    return f"{dec} {currency} ({value})"


@dataclass(frozen=True)
class DeclaredSoul:  # __s402_cost_bound_display_v1__
    """One soul's declared terms and its per-tick figure from the
    certificate's cost_<soul>_per_call row."""
    name: str
    tokens_input: int
    input_per_1m: str
    tokens_output: int
    output_per_1m: str
    reasoning_mult: str
    per_tick: Fraction


@dataclass(frozen=True)
class DeclaredCostDisplay:  # __s402_cost_bound_display_v1__
    """Figures read from a cost-cap certificate that passed the four checks
    of D400-3 and D401-1. residual is the headroom; declared_total is the
    certificate's cost_cap minus the residual."""
    currency: str
    cap: Fraction
    declared_cap: Fraction
    margin_pct: int
    residual: Fraction
    declared_total: Fraction
    max_ticks: int
    souls: tuple[DeclaredSoul, ...]

    def _cap_phrase(self) -> str:
        if self.margin_pct > 0:
            return (
                f"effective cap {self.cap} (cost_cap {self.declared_cap}, "
                f"margin {self.margin_pct}%)"
            )
        return f"cost_cap {self.cap}"

    def lines(self) -> tuple[str, ...]:
        out = [
            f"  declared total_cost = {_amount(self.declared_total, self.currency)}"
            f" = {self._cap_phrase()} - certificate residual {self.residual}",
            f"  headroom = {_amount(self.residual, self.currency)}, "
            f"the certificate residual",
        ]
        for s in self.souls:
            mult = "" if Fraction(s.reasoning_mult) == 1 else f" x {s.reasoning_mult}"
            out.append(
                f"    {s.name}: {s.tokens_input} in x {s.input_per_1m}/M + "
                f"{s.tokens_output} out x {s.output_per_1m}/M{mult} = "
                f"{s.per_tick} per tick x {self.max_ticks} ticks"
            )
        return tuple(out)

    def vr003_text(self) -> str:
        return (
            f" Declared total_cost {_amount(self.declared_total, self.currency)}"
            f" = {self._cap_phrase()} minus the Farkas certificate residual "
            f"{self.residual} (the headroom); basis: declared tokens x table "
            f"price x max_ticks."
        )


def _row_terms(row: object) -> Optional[dict[str, Fraction]]:  # __s402_cost_bound_display_v1__
    coeffs = row.get("coeffs") if isinstance(row, dict) else None
    if not isinstance(coeffs, dict):
        return None
    try:
        return {str(k): Fraction(v) for k, v in coeffs.items()}
    except (ValueError, TypeError, ZeroDivisionError):
        return None


def declared_cost_display(spec: SMTSpec, cost_doc: object) -> DeclaredCostDisplay:  # __s402_cost_bound_display_v1__
    """Read the declared total and the headroom off a cost-cap certificate,
    after four checks in a fixed order (D400-3, D401-1). Raises
    CostDisplayError naming the first check that fails. Every figure comes
    from the certificate; the re-derivation of check 4 only binds it."""
    import cost_farkas
    from coverage_farkas import check_serialized

    if not isinstance(cost_doc, dict) or not check_serialized(cost_doc):
        raise CostDisplayError(
            "check_serialized: the multipliers do not reduce the "
            "certificate's rows to a numeric contradiction"
        )
    combined: dict[str, Fraction] = {}
    for idx, (mult, row) in enumerate(zip(cost_doc["multipliers"], cost_doc["constraints"])):
        terms = _row_terms(row)
        if terms is None:
            raise CostDisplayError(
                f"variable cancellation: constraints[{idx}] is not a "
                f"constraint row with readable coefficients"
            )
        weight = Fraction(mult)
        for key, coeff in terms.items():
            combined[key] = combined.get(key, Fraction(0)) + weight * coeff
    residual = combined.get("", Fraction(0))
    souls = cost_farkas.souls_from_smtspec(spec)
    if not cost_farkas.check_serialized_cost(
        cost_doc, souls, spec.max_ticks, spec.cost_cap_amount,
        spec.cost_cap_margin_pct,
    ):
        raise CostDisplayError(
            "check_serialized_cost: the certificate's rows differ from the "
            "rows re-derived from the spec's declared tokens and table rates"
        )
    try:
        again = cost_farkas.extract_cost_certificate(
            souls, spec.max_ticks, spec.cost_cap_amount, spec.cost_cap_margin_pct,
        )
    except cost_farkas.CostFarkasError:
        raise CostDisplayError(
            "byte equality: re-derivation from the spec raised CostFarkasError"
        ) from None
    if again is None:
        raise CostDisplayError("byte equality: the spec re-derives no certificate")
    if cost_farkas.cost_farkas_json_bytes(cost_doc) != cost_farkas.cost_farkas_json_bytes(again):
        raise CostDisplayError(
            "byte equality: the certificate differs from the certificate "
            "re-derived from the spec"
        )
    assumed = {str(a[0]): a for a in spec.soul_assumptions}
    rows: list[DeclaredSoul] = []
    for row in cost_doc["constraints"]:
        coeffs = row["coeffs"]
        for key in coeffs:
            if key.startswith("cost_") and key.endswith("_per_call") and len(coeffs) == 2:
                name = key[len("cost_"):-len("_per_call")]
                a = assumed[name]
                rows.append(DeclaredSoul(
                    name=name,
                    tokens_input=int(a[2]),
                    input_per_1m=str(a[4]),
                    tokens_output=int(a[3]),
                    output_per_1m=str(a[5]),
                    reasoning_mult=str(a[6]),
                    per_tick=-Fraction(coeffs[""]),
                ))
    cap = Fraction(cost_doc["cost_cap"])
    return DeclaredCostDisplay(
        currency=spec.cost_cap_currency,
        cap=cap,
        declared_cap=Fraction(spec.cost_cap_amount),
        margin_pct=int(spec.cost_cap_margin_pct),
        residual=residual,
        declared_total=cap - residual,
        max_ticks=int(cost_doc["max_ticks"]),
        souls=tuple(rows),
    )


def format_verdict(
    result: VerifyResult,
    *,
    cost_certificate: Optional[dict] = None,  # __s402_cost_bound_display_v1__
) -> str:
    """Render a VerifyResult into a CLI-ready text block."""
    spec = result.spec
    lines: list[str] = []
    lines.append("─" * 60)
    lines.append(f"World:        {spec.world_name}")
    lines.append(f"Solver:       {result.solver_version}")
    lines.append(f"Elapsed:      {result.elapsed_ms}ms")
    lines.append(f"Spec sha256:  {spec.sha256()[:16]}…")
    lines.append("─" * 60)

    if result.verdict == "proven":
        if spec.cost_cap_margin_pct > 0:
            eff = (spec.cost_cap_amount
                   * Decimal(100 - spec.cost_cap_margin_pct)
                   / Decimal(100))
            lines.append(
                f"PROVEN: total_cost ≤ ${eff} "
                f"{spec.cost_cap_currency} across all execution paths."
            )
            lines.append(
                f"  Declared cap: ${spec.cost_cap_amount} "
                f"{spec.cost_cap_currency}, "
                f"safety margin: {spec.cost_cap_margin_pct}%."
            )
        else:
            lines.append(
                f"PROVEN: total_cost ≤ ${spec.cost_cap_amount} "
                f"{spec.cost_cap_currency} across all execution paths."
            )
        lines.append(
            f"  bounded by: {len(spec.soul_costs)} soul(s) × "
            f"{spec.max_ticks} ticks"
        )
        if cost_certificate is not None:  # __s402_cost_bound_display_v1__
            lines.extend(declared_cost_display(spec, cost_certificate).lines())
        return "\n".join(lines)

    if result.verdict == "refuted":
        ce = result.counterexample
        assert ce is not None
        lines.append(
            f"REFUTED: SMT solver found a counterexample."
        )
        lines.append("")
        lines.append("Per-soul cost breakdown:")
        for s in ce.per_soul:
            lines.append(
                f"  {s.soul_name:<20s} "
                f"({s.canonical_model:<24s})  "
                f"per-call ${s.per_call_usd:.6f}  × "
                f"{ce.max_ticks} ticks  =  ${s.total_usd:.6f}"
            )
        lines.append("")
        lines.append(
            f"  total_cost  =  ${ce.total_cost_usd:.6f}"
        )
        lines.append(
            f"  cap         =  ${ce.cap_usd}"
        )
        lines.append(
            f"  overage     =  ${ce.overage_usd:.6f}  "
            f"({ce.overage_pct:.1f}% over)"
        )
        if ce.largest_contributor:
            lines.append(
                f"  largest contributor: {ce.largest_contributor!r}"
            )

        lines.append("")
        lines.append("Suggested fixes (any one):")
        suggested_cap = _suggest_min_cap(ce)
        lines.append(
            f"  1. Raise cost_cap to >= ${suggested_cap} USD"
        )
        max_ticks_fit = _suggest_max_ticks_reduction(ce)
        if max_ticks_fit is not None:
            lines.append(
                f"  2. Reduce max_ticks to <= {max_ticks_fit} "
                f"(currently {ce.max_ticks})"
            )
        else:
            lines.append(
                f"  2. max_ticks reduction insufficient; even 1 tick "
                f"exceeds cap"
            )
        if ce.largest_contributor:
            lines.append(
                f"  3. Reduce tokens on soul "
                f"{ce.largest_contributor!r} (largest cost driver)"
            )
        return "\n".join(lines)

    if result.verdict == "unknown":
        lines.append(f"UNKNOWN: {result.error}")
        lines.append(
            "  Try: --timeout-ms 60000 (longer budget) or simplify "
            "the program."
        )
        return "\n".join(lines)

    # error
    lines.append(f"ERROR: {result.error}")
    return "\n".join(lines)


def format_sequence_verdict(result: SequenceVerifyResult) -> str:  # __phase2_stage4_seq_verify_v1__
    """Render a SequenceVerifyResult into a CLI-ready text block (ASCII)."""
    spec = result.spec
    lines: list[str] = []
    lines.append("-" * 60)
    lines.append(f"World:        {spec.world_name}")
    lines.append(f"Solver:       {result.solver_version}")
    lines.append(f"Elapsed:      {result.elapsed_ms}ms")
    lines.append(f"Spec sha256:  {spec.sha256()[:16]}...")
    lines.append(f"Seq laws:     {len(spec.sequence_laws)}")  # __phase2_stage8b_at_most_verify_v1__
    lines.append("-" * 60)

    if result.verdict == "vacuous":
        lines.append("VACUOUS: no sequence laws declared; nothing to check.")
        return "\n".join(lines)
    if result.verdict == "consistent":
        lines.append(
            "CONSISTENT: the declared ordering laws admit a valid total "
            "order."
        )
        lines.append(  # __phase2_stage8b_at_most_verify_v1__
            f"  {len(spec.sequence_laws)} ordering law(s) "
            f"over {len(spec.sequence_declarations)} event label(s)."
        )
        return "\n".join(lines)
    if result.verdict == "inconsistent":
        lines.append("INCONSISTENT: the declared ordering laws contradict.")
        lines.append(f"  {result.error}")
        return "\n".join(lines)
    if result.verdict == "unknown":
        lines.append(f"UNKNOWN: {result.error}")
        return "\n".join(lines)
    lines.append(f"ERROR: {result.error}")
    return "\n".join(lines)


# __policy_coverage_verify_v1__
def verify_coverage(
    spec: SMTSpec,
    timeout_ms: int = 30_000,
) -> CoverageVerifyResult:
    """Run z3 against the spec's coverage script.

    Polarity matches verify() (cost): the script asserts the protected
    region and the negated open-net, so UNSAT proves coverage (no gap)
    and SAT refutes it (a concrete uncovered over-threshold input).
    A spec with no coverage obligation is 'vacuous'.
    """
    started: float = time.monotonic()
    ts: str = datetime.now(timezone.utc).isoformat(timespec="seconds")

    script: Optional[str] = spec.serialize_coverage()
    if script is None:
        return CoverageVerifyResult(
            verdict="vacuous", spec=spec, solver_name="z3",
            solver_version="n/a", elapsed_ms=0, timestamp_utc=ts,
        )

    try:
        import z3
    except ImportError:
        return CoverageVerifyResult(
            verdict="error", spec=spec, solver_name="z3",
            solver_version="unavailable", elapsed_ms=0, timestamp_utc=ts,
            error="z3-solver not installed; install with "
                  "`pip install nous-lang[smt]`",
        )

    body: str = _strip_check_sat(script)
    solver = z3.Solver()
    solver.set("timeout", int(timeout_ms))

    try:
        solver.from_string(body)
    except z3.Z3Exception as e:
        return CoverageVerifyResult(
            verdict="error", spec=spec, solver_name="z3",
            solver_version=_solver_version(),
            elapsed_ms=int((time.monotonic() - started) * 1000),
            timestamp_utc=ts, error=f"z3 parse error: {e}",
        )

    try:
        check = solver.check()
    except z3.Z3Exception as e:
        return CoverageVerifyResult(
            verdict="error", spec=spec, solver_name="z3",
            solver_version=_solver_version(),
            elapsed_ms=int((time.monotonic() - started) * 1000),
            timestamp_utc=ts, error=f"z3 check error: {e}",
        )

    elapsed_ms: int = int((time.monotonic() - started) * 1000)

    if check == z3.unsat:
        return CoverageVerifyResult(
            verdict="proven", spec=spec, solver_name="z3",
            solver_version=_solver_version(),
            elapsed_ms=elapsed_ms, timestamp_utc=ts,
        )

    if check == z3.sat:
        try:
            model = solver.model()
            assignment = tuple(
                sorted(
                    (str(d.name()), str(model[d])) for d in model.decls()
                )
            )
            ce = CoverageCounterExample(assignment=assignment)
        except Exception as e:
            return CoverageVerifyResult(
                verdict="error", spec=spec, solver_name="z3",
                solver_version=_solver_version(),
                elapsed_ms=elapsed_ms, timestamp_utc=ts,
                error=f"counterexample extraction failed: {e}",
            )
        return CoverageVerifyResult(
            verdict="refuted", spec=spec, solver_name="z3",
            solver_version=_solver_version(),
            elapsed_ms=elapsed_ms, timestamp_utc=ts,
            counterexample=ce,
        )

    return CoverageVerifyResult(
        verdict="unknown", spec=spec, solver_name="z3",
        solver_version=_solver_version(),
        elapsed_ms=elapsed_ms, timestamp_utc=ts,
        error=f"z3 returned unknown (timeout {timeout_ms}ms); reason: "
              f"{solver.reason_unknown()}",
    )
