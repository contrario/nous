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


def format_verdict(result: VerifyResult) -> str:
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
