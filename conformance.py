"""NOUS runtime conformance verification.

verify_conformance recomputes -- never trusts -- what a signed execution
trace realized, against the bounds the static SMT proof assumed. Those bounds
are taken from a RE-DERIVED SMTSpec (re-emitted from the signed source +
pricing by the caller) and authenticated by matching spec.sha256() to the
manifest's signed smt_spec_sha256 -- NOT read from the unsigned
proof_assumptions sibling, which is tamperable and therefore advisory only.

Six independent per-obligation booleans, no early exit; the overall verdict is
DERIVED (ConformanceDetail.ok), so an auditor sees exactly which obligation
broke. Structural impossibility -- a soul the proof never declared (no bound to
discharge against), a priced tool_call the cost MVP cannot model, an unknown
event kind -- raises a typed precondition error (refuse over guess). Every
evaluable outcome is a boolean.

Z3 is not required here: re-deriving the SMTSpec is pure parse + emit (pre
solver); discharge and bound transfer are interval checks and a Decimal sum;
signatures are cryptography. Re-running the ORIGINAL cost proof (Z3) remains
the dossier's job.

# __nous_conformance_module_v1__
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from manifest import Manifest
from pricing import PricingTable
from nous_trace import TraceEnvelope, TraceEvent, verify_trace_signature

if TYPE_CHECKING:
    from smt_emit import SMTSpec

_MILLION = Decimal("1000000")
_KNOWN_KINDS = frozenset({"llm_call", "tool_call", "message", "gated_action"})


class ConformanceError(ValueError):
    """Base class for conformance verification failures."""


class ConformancePreconditionError(ConformanceError):
    """Inputs are structurally unusable (a dispatch failure, not a verdict)."""


@dataclass(frozen=True, slots=True)
class _SoulBound:
    model: str
    max_input_tokens: int
    max_output_tokens: int
    input_per_1m: Decimal
    output_per_1m: Decimal
    reasoning_token_multiplier: Decimal


@dataclass(frozen=True, slots=True)
class ConformanceDetail:
    binding_ok: bool
    surface_ok: bool
    assumption_discharge_ok: bool
    bound_transfer_ok: bool
    authorization_ok: bool
    trace_signature_ok: bool
    realized_total: str
    cost_cap: str
    errors: tuple[str, ...] = field(default=())

    @property
    def ok(self) -> bool:
        return (
            self.binding_ok
            and self.surface_ok
            and self.assumption_discharge_ok
            and self.bound_transfer_ok
            and self.authorization_ok
            and self.trace_signature_ok
        )


def _bounds_from_spec(spec: "SMTSpec") -> dict[str, _SoulBound]:
    bounds: dict[str, _SoulBound] = {}
    for row in spec.soul_assumptions:
        (name, model, max_in, max_out, in_rate, out_rate, mult) = row
        bounds[name] = _SoulBound(
            model=model,
            max_input_tokens=int(max_in),
            max_output_tokens=int(max_out),
            input_per_1m=Decimal(in_rate),
            output_per_1m=Decimal(out_rate),
            reasoning_token_multiplier=Decimal(mult),
        )
    return bounds


def _event_cost(event: TraceEvent, bound: _SoulBound) -> Decimal:
    return (
        bound.input_per_1m * Decimal(event.input_tokens)
        + bound.output_per_1m
        * Decimal(event.output_tokens)
        * bound.reasoning_token_multiplier
    ) / _MILLION


def verify_conformance(
    trace: TraceEnvelope,
    manifest: Manifest,
    spec: "SMTSpec",
    pricing_table: PricingTable,
) -> ConformanceDetail:
    bounds = _bounds_from_spec(spec)
    if not bounds:
        raise ConformancePreconditionError(
            "re-derived spec carries no soul_assumptions; cannot establish "
            "per-soul bounds (the proof declared no costed souls)"
        )

    cost_cap: Decimal = spec.cost_cap_amount
    max_ticks: int = spec.max_ticks
    gated_actions = frozenset(
        (manifest.proof_assumptions or {}).get("gated_actions", [])
    )

    # Structural preconditions (refuse over guess): a soul or gated action the
    # proof never declared, an unknown kind, or a priced tool_call -- none can
    # be mapped to a bound, so no verdict is possible.
    for ev in trace.events:
        if ev.kind not in _KNOWN_KINDS:
            raise ConformancePreconditionError(
                f"event seq={ev.seq} has unknown kind {ev.kind!r}; "
                f"expected one of {sorted(_KNOWN_KINDS)}"
            )
        if ev.soul not in bounds:
            raise ConformancePreconditionError(
                f"event seq={ev.seq} references soul {ev.soul!r} not in the "
                f"proof surface {sorted(bounds)} (run did something the spec "
                f"never declared)"
            )
        if ev.kind == "tool_call" and Decimal(ev.tool_cost) != Decimal("0"):
            raise ConformancePreconditionError(
                f"event seq={ev.seq} is a priced tool_call "
                f"(tool_cost={ev.tool_cost}); the cost MVP models llm_call "
                f"token cost only (priced tool calls are Phase 2)"
            )
        if ev.kind == "gated_action" and ev.action is not None:
            if ev.action not in gated_actions:
                raise ConformancePreconditionError(
                    f"event seq={ev.seq} gated action {ev.action!r} not in "
                    f"declared gated_actions {sorted(gated_actions)}"
                )

    errors: list[str] = []

    # 1. binding: re-derived spec + supplied pricing match the signed shas,
    #    and the trace claims those same shas.
    binding_ok = True
    if spec.source_sha256 != manifest.source_sha256:
        binding_ok = False
        errors.append("binding: spec.source_sha256 != manifest.source_sha256")
    if spec.pricing_sha256 != manifest.pricing_sha256:
        binding_ok = False
        errors.append("binding: spec.pricing_sha256 != manifest.pricing_sha256")
    if spec.sha256() != manifest.smt_spec_sha256:
        binding_ok = False
        errors.append("binding: spec.sha256() != manifest.smt_spec_sha256")
    if pricing_table.sha256() != manifest.pricing_sha256:
        binding_ok = False
        errors.append(
            "binding: supplied pricing_table.sha256() != manifest.pricing_sha256"
        )
    if trace.source_sha256 != manifest.source_sha256:
        binding_ok = False
        errors.append("binding: trace.source_sha256 != manifest.source_sha256")
    if trace.smt_spec_sha256 != manifest.smt_spec_sha256:
        binding_ok = False
        errors.append("binding: trace.smt_spec_sha256 != manifest.smt_spec_sha256")
    if trace.pricing_sha256 != manifest.pricing_sha256:
        binding_ok = False
        errors.append("binding: trace.pricing_sha256 != manifest.pricing_sha256")

    # 2. surface: all souls/gated actions validated in the precondition loop
    #    (violations raised); reaching here means the surface holds.
    surface_ok = True

    # 3. assumption discharge: per-event token caps + per-soul call count <=
    #    max_ticks + global max(tick) < max_ticks.
    assumption_discharge_ok = True
    call_count: dict[str, int] = {name: 0 for name in bounds}
    max_seen_tick = -1
    for ev in trace.events:
        max_seen_tick = max(max_seen_tick, ev.tick)
        b = bounds[ev.soul]
        if ev.input_tokens > b.max_input_tokens:
            assumption_discharge_ok = False
            errors.append(
                f"discharge: seq={ev.seq} soul {ev.soul} input_tokens "
                f"{ev.input_tokens} > max {b.max_input_tokens}"
            )
        if ev.output_tokens > b.max_output_tokens:
            assumption_discharge_ok = False
            errors.append(
                f"discharge: seq={ev.seq} soul {ev.soul} output_tokens "
                f"{ev.output_tokens} > max {b.max_output_tokens}"
            )
        if ev.kind == "llm_call":
            call_count[ev.soul] += 1
    for name, n in call_count.items():
        if n > max_ticks:
            assumption_discharge_ok = False
            errors.append(
                f"discharge: soul {name} made {n} llm_call(s) > max_ticks "
                f"{max_ticks}"
            )
    if max_seen_tick >= max_ticks:
        assumption_discharge_ok = False
        errors.append(
            f"discharge: max tick {max_seen_tick} >= max_ticks {max_ticks}"
        )

    # 4. bound transfer: recompute realized total under the proof's rates.
    realized_total = Decimal("0")
    for ev in trace.events:
        if ev.kind == "llm_call":
            realized_total += _event_cost(ev, bounds[ev.soul])
    bound_transfer_ok = realized_total <= cost_cap
    if not bound_transfer_ok:
        errors.append(
            f"bound_transfer: realized_total {realized_total} > cost_cap "
            f"{cost_cap}"
        )

    # 5. authorization: every gated_action event carries a valid approver
    #    attestation bound to that exact event. (MVP gated_actions == [] makes
    #    this vacuously True.)
    authorization_ok = True
    for ev in trace.events:
        if ev.kind != "gated_action":
            continue
        auth = ev.authorization
        if auth is None:
            authorization_ok = False
            errors.append(
                f"authorization: gated event seq={ev.seq} has no attestation"
            )
            continue
        if auth.approved_seq != ev.seq:
            authorization_ok = False
            errors.append(
                f"authorization: seq={ev.seq} approved_seq {auth.approved_seq} "
                f"!= event seq {ev.seq}"
            )
            continue
        payload = trace.canonical_body_bytes() + str(ev.seq).encode("utf-8")
        try:
            pub = Ed25519PublicKey.from_public_bytes(
                base64.b64decode(auth.public_key_b64, validate=True)
            )
            pub.verify(
                base64.b64decode(auth.signature_b64, validate=True), payload
            )
        except (InvalidSignature, ValueError):
            authorization_ok = False
            errors.append(
                f"authorization: seq={ev.seq} attestation signature invalid"
            )

    # 6. trace signature.
    trace_signature_ok = verify_trace_signature(trace)
    if not trace_signature_ok:
        errors.append("trace_signature: Ed25519 verify failed")

    return ConformanceDetail(
        binding_ok=binding_ok,
        surface_ok=surface_ok,
        assumption_discharge_ok=assumption_discharge_ok,
        bound_transfer_ok=bound_transfer_ok,
        authorization_ok=authorization_ok,
        trace_signature_ok=trace_signature_ok,
        realized_total=str(realized_total),
        cost_cap=str(cost_cap),
        errors=tuple(errors),
    )
