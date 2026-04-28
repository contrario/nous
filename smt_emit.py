"""
NOUS smt_emit — translate parsed NousProgram + PricingTable into
SMT-LIB 2.6 constraints for cost_cap verification.

Pure-Python: no z3 import. The output is a string suitable for any
SMT-LIB 2.6 solver (z3, cvc5, MathSAT). The actual solver run lives
in Phase 4 (smt_verify.py); this module's responsibility ends with
the byte-deterministic spec.

Soundness model (see docs/COST_VERIFICATION_GUIDE.md "How the cost
upper bound is computed"):

    total_cost  =  Sum over each soul s:  per_call_cost(s) * max_ticks

    per_call_cost(s)
        = (input_per_1m * tokens.input
        +  output_per_1m * tokens.output * reasoning_mult)
        / 1_000_000

The negated obligation `(not (<= total_cost cap))` is asserted; an
SMT solver that returns `unsat` proves the cap holds across all
execution paths. `sat` produces a counterexample (Phase 4 work).

Public API:
  SMTSpec          dataclass (declarations, assertions, obligation, meta)
  EmitError        raised on under-declaration / unsupported pricing
  emit_smt(prog, pricing, today=None) -> SMTSpec
  SMTSpec.serialize() -> str           byte-deterministic
  SMTSpec.sha256() -> str              canonical hash for manifests

# __nous_smt_emit_module_v1__
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from ast_nodes import NousProgram, SoulNode, WorldNode
from pricing import (
    PricingEntry,
    PricingTable,
    get_price_for_smt,
)


class EmitError(ValueError):
    """Raised when the source program cannot be SMT-emitted soundly.

    Distinct from generic ValueError so the CLI can format these as
    user-facing diagnostics.
    """


@dataclass(frozen=True)
class SMTSpec:
    """Self-contained SMT-LIB spec produced from one NousProgram."""
    nous_version: str
    smt_emit_version: str
    source_sha256: str
    pricing_sha256: str
    world_name: str
    cost_cap_amount: Decimal
    cost_cap_currency: str
    max_ticks: int

    declarations: tuple[tuple[str, str], ...] = ()
    range_assertions: tuple[str, ...] = ()
    cost_assertions: tuple[str, ...] = ()
    obligation: str = ""
    soul_costs: tuple[tuple[str, str, str], ...] = ()

    def serialize(self) -> str:
        lines: list[str] = []
        lines.append("; ---------------------------------------------------------")
        lines.append(f"; NOUS smt_emit {self.smt_emit_version} - "
                     f"NOUS {self.nous_version}")
        lines.append(f"; source.sha256:  {self.source_sha256}")
        lines.append(f"; pricing.sha256: {self.pricing_sha256}")
        lines.append(f"; world: {self.world_name}")
        lines.append(f"; cost_cap: {self.cost_cap_amount} "
                     f"{self.cost_cap_currency}")
        lines.append(f"; max_ticks: {self.max_ticks}")
        for canonical, soul, per_call in self.soul_costs:
            lines.append(f"; soul {soul}: model={canonical}, "
                         f"per-call cost = {per_call}")
        lines.append("; ---------------------------------------------------------")
        lines.append("")
        lines.append("(set-logic QF_LRA)")
        lines.append("")

        for var, sort in self.declarations:
            lines.append(f"(declare-const {var} {sort})")
        lines.append("")

        if self.range_assertions:
            lines.append("; range constraints (no negative costs)")
            for r in self.range_assertions:
                lines.append(r)
            lines.append("")

        if self.cost_assertions:
            lines.append("; per-soul cost equations + total")
            for a in self.cost_assertions:
                lines.append(a)
            lines.append("")

        lines.append("; negated obligation - unsat proves the cap")
        lines.append(self.obligation)
        lines.append("")
        lines.append("(check-sat)")
        return "\n".join(lines) + "\n"

    def sha256(self) -> str:
        canonical: list[str] = []
        canonical.append(f"NV:{self.nous_version}")
        canonical.append(f"EV:{self.smt_emit_version}")
        canonical.append(f"SS:{self.source_sha256}")
        canonical.append(f"PS:{self.pricing_sha256}")
        canonical.append(f"W:{self.world_name}")
        canonical.append(
            f"CC:{self.cost_cap_amount}|{self.cost_cap_currency}"
        )
        canonical.append(f"MT:{self.max_ticks}")
        for var, sort in self.declarations:
            canonical.append(f"D:{var}:{sort}")
        for r in self.range_assertions:
            canonical.append(f"R:{r}")
        for a in self.cost_assertions:
            canonical.append(f"A:{a}")
        canonical.append(f"O:{self.obligation}")
        encoded: bytes = "\n".join(canonical).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def _decimal_to_rational(d: Decimal) -> str:
    """Convert a Decimal to an SMT-LIB Real literal (exact rational)."""
    num, den = d.as_integer_ratio()
    if den == 1:
        return str(num)
    return f"(/ {num} {den})"


def _source_sha256(source_text: Optional[str]) -> str:
    if source_text is None:
        return "unknown"
    return hashlib.sha256(source_text.encode("utf-8")).hexdigest()


NOUS_VERSION_FALLBACK: str = "4.13.0-dev"
SMT_EMIT_VERSION: str = "1.0"


def _import_nous_version() -> str:
    try:
        from _version import __version__
        return str(__version__)
    except Exception:
        return NOUS_VERSION_FALLBACK


def _validate_world(prog: NousProgram) -> WorldNode:
    if prog.world is None:
        raise EmitError(
            "program has no world; --smt requires exactly one world "
            "with cost_cap and max_ticks declarations"
        )
    w = prog.world
    if w.cost_cap is None:
        raise EmitError(
            f"world {w.name!r} has no `cost_cap:` declaration; "
            f"--smt cannot prove anything without a declared ceiling. "
            f"Add inside the world block: cost_cap: <amount> <USD|EUR>"
        )
    if w.cost_cap.currency != "USD":
        raise EmitError(
            f"world {w.name!r} declares cost_cap in "
            f"{w.cost_cap.currency!r}; --smt v4.13.0 supports USD only "
            f"(multi-currency conversion is a Phase 5 feature). "
            f"Convert your cap to USD or remove --smt."
        )
    if w.max_ticks is None:
        raise EmitError(
            f"world {w.name!r} has no `max_ticks:` declaration; "
            f"--smt cannot bound total cost without a tick limit. "
            f"Add inside the world block: max_ticks: <integer>"
        )
    if w.max_ticks <= 0:
        raise EmitError(
            f"world {w.name!r} has max_ticks={w.max_ticks}; "
            f"must be a positive integer"
        )
    return w


def _validate_souls(prog: NousProgram) -> list[SoulNode]:
    if not prog.souls:
        raise EmitError(
            "program has no souls; cost_cap requires at least one "
            "soul with a `mind:` declaration to have any meaning"
        )
    for s in prog.souls:
        if s.mind is None:
            raise EmitError(
                f"soul {s.name!r} has no `mind:` declaration; "
                f"--smt cannot resolve a price without a model"
            )
        if s.tokens is None:
            raise EmitError(
                f"soul {s.name!r} has no `tokens:` declaration; "
                f"--smt cannot bound LLM cost without declared "
                f"token estimates. Add inside the soul block: "
                f"tokens: input=<N> output=<M>"
            )
        if s.tokens.input < 0 or s.tokens.output < 0:
            raise EmitError(
                f"soul {s.name!r} has negative tokens "
                f"(input={s.tokens.input}, output={s.tokens.output}); "
                f"both must be >= 0"
            )
    return sorted(prog.souls, key=lambda s: s.name)


def _per_call_cost_smt(
    canonical_model: str,
    entry: PricingEntry,
    tokens_input: int,
    tokens_output: int,
) -> str:
    if entry.input_per_1m_usd is None or entry.output_per_1m_usd is None:
        raise EmitError(
            f"model {canonical_model!r} has no input/output prices; "
            f"only per_token models are supported under --smt"
        )

    input_rate = _decimal_to_rational(entry.input_per_1m_usd)
    output_rate = _decimal_to_rational(entry.output_per_1m_usd)
    reasoning_mult = _decimal_to_rational(entry.reasoning_token_multiplier)
    million = "1000000"

    if entry.reasoning_token_multiplier == Decimal("1.0"):
        return (
            f"(/ (+ (* {input_rate} {tokens_input}) "
            f"(* {output_rate} {tokens_output})) {million})"
        )
    return (
        f"(/ (+ (* {input_rate} {tokens_input}) "
        f"(* {output_rate} {tokens_output} {reasoning_mult})) {million})"
    )


def emit_smt(
    prog: NousProgram,
    pricing: PricingTable,
    source_text: Optional[str] = None,
    today: Optional[date] = None,
) -> SMTSpec:
    if today is None:
        today = datetime.now(timezone.utc).date()

    world = _validate_world(prog)
    souls = _validate_souls(prog)

    cap_amount = world.cost_cap.amount
    cap_currency = world.cost_cap.currency
    max_ticks = world.max_ticks

    decls: list[tuple[str, str]] = []
    ranges: list[str] = []
    asserts: list[str] = []
    soul_costs: list[tuple[str, str, str]] = []

    for s in souls:
        canonical, entry = get_price_for_smt(
            pricing, s.mind.model, today=today,
        )
        per_call_expr = _per_call_cost_smt(
            canonical, entry,
            s.tokens.input, s.tokens.output,
        )
        per_call_var = f"cost_{s.name}_per_call"
        total_var = f"cost_{s.name}_total"

        decls.append((per_call_var, "Real"))
        decls.append((total_var, "Real"))
        ranges.append(f"(assert (>= {per_call_var} 0))")
        ranges.append(f"(assert (>= {total_var} 0))")

        asserts.append(f"(assert (= {per_call_var} {per_call_expr}))")
        asserts.append(
            f"(assert (= {total_var} (* {per_call_var} {max_ticks})))"
        )
        soul_costs.append((canonical, s.name, per_call_expr))

    decls.append(("total_cost", "Real"))
    ranges.append("(assert (>= total_cost 0))")
    if souls:
        sum_terms = " ".join(f"cost_{s.name}_total" for s in souls)
        if len(souls) == 1:
            asserts.append(
                f"(assert (= total_cost cost_{souls[0].name}_total))"
            )
        else:
            asserts.append(
                f"(assert (= total_cost (+ {sum_terms})))"
            )

    cap_smt = _decimal_to_rational(cap_amount)
    obligation = f"(assert (not (<= total_cost {cap_smt})))"

    return SMTSpec(
        nous_version=_import_nous_version(),
        smt_emit_version=SMT_EMIT_VERSION,
        source_sha256=_source_sha256(source_text),
        pricing_sha256=pricing.sha256(),
        world_name=world.name,
        cost_cap_amount=cap_amount,
        cost_cap_currency=cap_currency,
        max_ticks=max_ticks,
        declarations=tuple(decls),
        range_assertions=tuple(ranges),
        cost_assertions=tuple(asserts),
        obligation=obligation,
        soul_costs=tuple(soul_costs),
    )
