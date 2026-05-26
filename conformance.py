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


import hashlib  # __nous_conformance_certificate_v1__
import json as _json_cert  # __nous_conformance_certificate_v1__

from pydantic import BaseModel, ConfigDict, Field, field_validator  # __nous_conformance_certificate_v1__
from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # __nous_conformance_certificate_v1__
    Ed25519PrivateKey,
)
from cryptography.hazmat.primitives.serialization import (  # __nous_conformance_certificate_v1__
    Encoding,
    PublicFormat,
)

CERTIFICATE_SCHEMA_VERSION: int = 1  # __nous_conformance_certificate_v1__


class CertificateSignature(BaseModel):  # __nous_conformance_certificate_v1__
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    algorithm: str = Field(default="ed25519")
    public_key_b64: str = Field(min_length=1)
    signature_b64: str = Field(min_length=1)


class ConformanceCertificate(BaseModel):  # __nous_conformance_certificate_v1__
    """Standalone signed conformance verdict for one execution trace.

    The signed body binds the verdict to the proof artifacts by hash, so a
    verifier confirms cert -> trace -> manifest identity offline with no
    re-emit and no Z3. Signature covers certificate_canonical_body_bytes().
    """

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    certificate_schema_version: int = Field(default=CERTIFICATE_SCHEMA_VERSION)
    nous_version: str = Field(min_length=1)
    world_name: str = Field(min_length=1)
    issued_utc: str = Field(min_length=1)

    source_sha256: str = Field(min_length=64, max_length=64)
    smt_spec_sha256: str = Field(min_length=64, max_length=64)
    pricing_sha256: str = Field(min_length=64, max_length=64)
    trace_sha256: str = Field(min_length=64, max_length=64)

    binding_ok: bool
    surface_ok: bool
    assumption_discharge_ok: bool
    bound_transfer_ok: bool
    authorization_ok: bool
    trace_signature_ok: bool
    conformant: bool

    realized_total: str = Field(min_length=1)
    cost_cap: str = Field(min_length=1)
    cost_currency: str = Field(min_length=1)
    errors: tuple[str, ...] = Field(default=())

    signature: Optional[CertificateSignature] = Field(default=None)
    transparency_log: Optional[dict] = Field(  # __nous_conformance_cert_anchor_v1__
        default=None
    )

    @field_validator("errors", mode="before")
    @classmethod
    def _coerce_errors(cls, v: object) -> object:
        if isinstance(v, list):
            return tuple(v)
        return v

    def certificate_canonical_body_bytes(self) -> bytes:
        doc = self.model_dump(  # __nous_conformance_cert_anchor_v1__
            exclude={"signature", "transparency_log"}
        )
        return _json_cert.dumps(
            doc, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")


def _cert_public_key_raw_b64(public_key: Ed25519PublicKey) -> str:  # __nous_conformance_certificate_v1__
    raw: bytes = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def build_certificate(  # __nous_conformance_certificate_v1__
    detail: ConformanceDetail,
    trace: TraceEnvelope,
    manifest: Manifest,
    *,
    nous_version: str,
    issued_utc: str,
) -> ConformanceCertificate:
    """Record a computed ConformanceDetail as an unsigned certificate.

    No recompute: detail is the authority (it was produced by
    verify_conformance against the re-derived spec). The certificate binds the
    verdict to source/spec/pricing (from the manifest's signed shas) and to the
    trace (by sha256 of its canonical body bytes).
    """
    trace_sha = hashlib.sha256(trace.canonical_body_bytes()).hexdigest()
    return ConformanceCertificate(
        certificate_schema_version=CERTIFICATE_SCHEMA_VERSION,
        nous_version=nous_version,
        world_name=manifest.world_name,
        issued_utc=issued_utc,
        source_sha256=manifest.source_sha256,
        smt_spec_sha256=manifest.smt_spec_sha256,
        pricing_sha256=manifest.pricing_sha256,
        trace_sha256=trace_sha,
        binding_ok=detail.binding_ok,
        surface_ok=detail.surface_ok,
        assumption_discharge_ok=detail.assumption_discharge_ok,
        bound_transfer_ok=detail.bound_transfer_ok,
        authorization_ok=detail.authorization_ok,
        trace_signature_ok=detail.trace_signature_ok,
        conformant=detail.ok,
        realized_total=detail.realized_total,
        cost_cap=detail.cost_cap,
        cost_currency="USD",
        errors=tuple(detail.errors),
    )


def sign_certificate(  # __nous_conformance_certificate_v1__
    cert: ConformanceCertificate,
    private_key: Ed25519PrivateKey,
) -> ConformanceCertificate:
    body: bytes = cert.certificate_canonical_body_bytes()
    raw_sig: bytes = private_key.sign(body)
    sig = CertificateSignature(
        algorithm="ed25519",
        public_key_b64=_cert_public_key_raw_b64(private_key.public_key()),
        signature_b64=base64.b64encode(raw_sig).decode("ascii"),
    )
    return ConformanceCertificate(
        certificate_schema_version=cert.certificate_schema_version,
        nous_version=cert.nous_version,
        world_name=cert.world_name,
        issued_utc=cert.issued_utc,
        source_sha256=cert.source_sha256,
        smt_spec_sha256=cert.smt_spec_sha256,
        pricing_sha256=cert.pricing_sha256,
        trace_sha256=cert.trace_sha256,
        binding_ok=cert.binding_ok,
        surface_ok=cert.surface_ok,
        assumption_discharge_ok=cert.assumption_discharge_ok,
        bound_transfer_ok=cert.bound_transfer_ok,
        authorization_ok=cert.authorization_ok,
        trace_signature_ok=cert.trace_signature_ok,
        conformant=cert.conformant,
        realized_total=cert.realized_total,
        cost_cap=cert.cost_cap,
        cost_currency=cert.cost_currency,
        errors=tuple(cert.errors),
        transparency_log=cert.transparency_log,  # __nous_conformance_cert_anchor_v1__
        signature=sig,
    )


def verify_certificate_signature(  # __nous_conformance_certificate_v1__
    cert: ConformanceCertificate,
) -> bool:
    if cert.signature is None:
        return False
    if cert.signature.algorithm != "ed25519":
        return False
    try:
        pub_raw: bytes = base64.b64decode(
            cert.signature.public_key_b64, validate=True
        )
        raw_sig: bytes = base64.b64decode(
            cert.signature.signature_b64, validate=True
        )
        public_key = Ed25519PublicKey.from_public_bytes(pub_raw)
        public_key.verify(raw_sig, cert.certificate_canonical_body_bytes())
        return True
    except (InvalidSignature, ValueError):
        return False


def certificate_json(cert: ConformanceCertificate) -> str:  # __nous_conformance_certificate_v1__
    doc = cert.model_dump()
    if doc.get("signature") is None:
        doc.pop("signature", None)
    if doc.get("transparency_log") is None:  # __nous_conformance_cert_anchor_v1__
        doc.pop("transparency_log", None)
    doc["errors"] = list(cert.errors)
    return _json_cert.dumps(doc, indent=2, sort_keys=True) + "\n"


def load_certificate(path: str) -> ConformanceCertificate:  # __nous_conformance_certificate_v1__
    with open(path, "r", encoding="utf-8") as fh:
        data = _json_cert.load(fh)
    return ConformanceCertificate(**data)
