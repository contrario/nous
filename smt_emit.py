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
# __session70_phase5b_v2_schema_rename_v1__
# __session70_phase5b_step8_eur_e2e_v1__
"""
from __future__ import annotations
# __session64_smt_margin_v1__

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
    cost_cap_margin_pct: int = 0

    declarations: tuple[tuple[str, str], ...] = ()
    range_assertions: tuple[str, ...] = ()
    cost_assertions: tuple[str, ...] = ()
    obligation: str = ""
    soul_costs: tuple[tuple[str, str, str], ...] = ()
    soul_assumptions: tuple[
        tuple[str, str, int, int, str, str, str], ...
    ] = ()  # __session96_smtspec_soul_assumptions_v1__
    sequence_declarations: tuple[tuple[str, str], ...] = ()  # __phase2_stage3_seq_emit_v1__
    sequence_assertions: tuple[str, ...] = ()  # __phase2_stage3_seq_emit_v1__
    sequence_laws: tuple[tuple[str, str, str], ...] = ()  # __phase2_stage5_seq_laws_v1__

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
        if self.cost_cap_margin_pct > 0:
            eff = (self.cost_cap_amount
                   * Decimal(100 - self.cost_cap_margin_pct)
                   / Decimal(100))
            lines.append(
                f"; cost_cap_margin_pct: {self.cost_cap_margin_pct}"
            )
            lines.append(
                f"; effective_cap: {eff} {self.cost_cap_currency}"
            )
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

    def serialize_sequence(self) -> Optional[str]:  # __phase2_stage3_seq_emit_v1__
        if not self.sequence_assertions:
            return None
        lines: list[str] = []
        lines.append("; ---------------------------------------------------------")
        lines.append(
            f"; NOUS smt_emit {self.smt_emit_version} - sequence consistency"
        )
        lines.append(f"; source.sha256:  {self.source_sha256}")
        lines.append(f"; world: {self.world_name}")
        lines.append(
            "; SAT proves the declared ordering laws admit a valid total order"
        )
        lines.append(
            "; UNSAT proves the laws contradict (e.g. before(a,b)+before(b,a))"
        )
        lines.append("; ---------------------------------------------------------")
        lines.append("")
        lines.append("(set-logic QF_LRA)")
        lines.append("")
        for var, sort in self.sequence_declarations:
            lines.append(f"(declare-const {var} {sort})")
        lines.append("")
        lines.append("; ordering constraints (one per 'before' law)")
        for a in self.sequence_assertions:
            lines.append(a)
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
        if self.cost_cap_margin_pct > 0:
            canonical.append(
                f"MARGIN:{self.cost_cap_margin_pct}"
            )
        for var, sort in self.declarations:
            canonical.append(f"D:{var}:{sort}")
        for r in self.range_assertions:
            canonical.append(f"R:{r}")
        for a in self.cost_assertions:
            canonical.append(f"A:{a}")
        canonical.append(f"O:{self.obligation}")
        for var, sort in self.sequence_declarations:  # __phase2_stage3_seq_emit_v1__
            canonical.append(f"SD:{var}:{sort}")
        for a in self.sequence_assertions:  # __phase2_stage3_seq_emit_v1__
            canonical.append(f"SA:{a}")
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


# __session69_smt_currency_consistency_v1__
def _validate_currency_consistency(
    world: WorldNode,
    pricing: PricingTable,
) -> None:
    """Refuse to emit an SMT spec whose pricing currency disagrees
    with the world's declared cost_cap currency.

    Mixing currencies inside a formal proof would require embedding
    an FX rate as an SMT assertion. FX rates are not bounded and
    fluctuate continuously, so they cannot be part of an auditable
    EU AI Act Annex IV evidence chain. The only safe action is to
    refuse the combination at emit time.
    """
    pricing_ccy = pricing.currency
    cap_ccy = world.cost_cap.currency
    if pricing_ccy == cap_ccy:
        return

    source_hint = ""
    if getattr(pricing, "source_path", None) is not None:
        source_hint = f" (pricing source: {pricing.source_path})"

    raise EmitError(
        f"currency mismatch: world {world.name!r} declares cost_cap in "
        f"{cap_ccy!r} but pricing table declares "
        f"_currency = {pricing_ccy!r}{source_hint}. "
        f"--smt refuses to mix currencies inside a formal proof "
        f"(FX rates are not auditable). "
        f"Use a pricing TOML whose _currency matches your cost_cap, "
        f"or change cost_cap to {pricing_ccy!r}."
    )


def _per_call_cost_smt(
    canonical_model: str,
    entry: PricingEntry,
    tokens_input: int,
    tokens_output: int,
) -> str:
    if entry.input_per_1m is None or entry.output_per_1m is None:
        raise EmitError(
            f"model {canonical_model!r} has no input/output prices; "
            f"only per_token models are supported under --smt"
        )

    input_rate = _decimal_to_rational(entry.input_per_1m)
    output_rate = _decimal_to_rational(entry.output_per_1m)
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
    margin_pct: int = 0,
) -> SMTSpec:
    if today is None:
        today = datetime.now(timezone.utc).date()

    if not (0 <= margin_pct <= 99):
        raise EmitError(
            f"--smt-margin out of range: {margin_pct} (must be 0..99)"
        )

    world = _validate_world(prog)
    souls = _validate_souls(prog)
    _validate_currency_consistency(world, pricing)  # __session69_smt_currency_consistency_v1__

    cap_amount = world.cost_cap.amount
    cap_currency = world.cost_cap.currency
    max_ticks = world.max_ticks

    decls: list[tuple[str, str]] = []
    ranges: list[str] = []
    asserts: list[str] = []
    soul_costs: list[tuple[str, str, str]] = []
    soul_assumptions: list[  # __session96_emit_soul_assumptions_decl_v1__
        tuple[str, str, int, int, str, str, str]
    ] = []

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
        soul_assumptions.append((  # __session96_emit_soul_assumptions_v1__
            s.name,
            canonical,
            s.tokens.input,
            s.tokens.output,
            str(entry.input_per_1m),
            str(entry.output_per_1m),
            str(entry.reasoning_token_multiplier),
        ))

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

    if margin_pct > 0:
        effective_cap = (cap_amount
                         * Decimal(100 - margin_pct)
                         / Decimal(100))
    else:
        effective_cap = cap_amount
    cap_smt = _decimal_to_rational(effective_cap)
    obligation = f"(assert (not (<= total_cost {cap_smt})))"

    seq_decls: list[tuple[str, str]] = []  # __phase2_stage3_seq_emit_v1__
    seq_asserts: list[str] = []
    seq_laws_struct: tuple[tuple[str, str, str], ...] = ()  # __phase2_stage5_seq_laws_v1__
    if world.sequence_laws:
        declared = set(world.events)
        for law in world.sequence_laws:
            if law.kind != "before":
                raise EmitError(
                    f"unsupported sequence law kind: {law.kind!r} "
                    f"(stage 3 supports only 'before')"
                )
            for lbl in (law.before_label, law.after_label):
                if lbl not in declared:
                    raise EmitError(
                        f"sequence law references undeclared event "
                        f"label {lbl!r}; declare it in world.events"
                    )
        for lbl in sorted(declared):
            seq_decls.append((f"seqrank_{lbl}", "Real"))
        for law in world.sequence_laws:
            seq_asserts.append(
                f"(assert (< seqrank_{law.before_label} "
                f"seqrank_{law.after_label}))"
            )
        seq_laws_struct = tuple(  # __phase2_stage5_seq_laws_v1__
            (law.kind, law.before_label, law.after_label)
            for law in world.sequence_laws
        )

    return SMTSpec(
        nous_version=_import_nous_version(),
        smt_emit_version=SMT_EMIT_VERSION,
        source_sha256=_source_sha256(source_text),
        pricing_sha256=pricing.sha256(),
        world_name=world.name,
        cost_cap_amount=cap_amount,
        cost_cap_currency=cap_currency,
        max_ticks=max_ticks,
        cost_cap_margin_pct=margin_pct,
        declarations=tuple(decls),
        range_assertions=tuple(ranges),
        cost_assertions=tuple(asserts),
        obligation=obligation,
        soul_costs=tuple(soul_costs),
        soul_assumptions=tuple(soul_assumptions),  # __session96_emit_soul_assumptions_ctor_v1__
        sequence_declarations=tuple(seq_decls),  # __phase2_stage3_seq_emit_v1__
        sequence_assertions=tuple(seq_asserts),  # __phase2_stage3_seq_emit_v1__
        sequence_laws=seq_laws_struct,  # __phase2_stage5_seq_laws_v1__
    )
