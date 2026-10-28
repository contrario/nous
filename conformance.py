"""NOUS runtime conformance verification.

verify_conformance recomputes -- never trusts -- what a signed execution
trace realized, against the bounds the static SMT proof assumed. Those bounds
are taken from a RE-DERIVED SMTSpec (re-emitted from the source + pricing
by the caller) and bound by matching spec.sha256() to the manifest's
smt_spec_sha256 -- NOT read from the unsigned proof_assumptions sibling,
which is tamperable and therefore advisory only. This path does not verify
the manifest's signature (FG-S415-X); the binding is sha equality.

Six independent per-obligation booleans, no early exit; the overall verdict is
DERIVED (ConformanceDetail.ok), so an auditor sees exactly which obligation
broke. Structural impossibility -- a soul the proof never declared (no bound to
discharge against), a priced tool_call the cost MVP cannot model, an unknown
event kind -- raises a typed precondition error (refuse over guess). Every
evaluable outcome is a boolean.

Tool surface (__s414_tool_surface_v1__): when the re-derived spec declares
events, a tool_call whose action label is missing or not one of them is a
run outside the declared surface and raises the same precondition error.
When the spec declares no events this check is vacuous. It EVIDENCES that
every recorded tool_call named a declared event; it sees recorded events
only and proves nothing.

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
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from manifest import Manifest
from pricing import PricingTable
from nous_trace import (  # __s139_u1b_authattest_import__
    AuthorizationAttestation,
    TraceEnvelope,
    TraceEvent,
    verify_trace_signature,
)
from attest_apr import (  # __s145_u4a_attest_import_v1__
    AttestationPinningRecord,
    verify_trace_attestation,
)

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
    sequence_ok: bool = True  # __phase2_stage5_seq_conformance_v1__
    errors: tuple[str, ...] = field(default=())
    sequence_vacuous: tuple[str, ...] = field(default=())  # __s104_seq_vacuous_field_v1__
    cost_binding: Optional[str] = None  # __s144_u3_conformance_trust_precondition_v1__
    provider_token_integrity: Optional[str] = None
    codegen_binding_ok: bool = True  # __s156_u3_detail_codegen_binding_ok_v1__

    @property
    def ok(self) -> bool:
        return (
            self.binding_ok
            and self.surface_ok
            and self.assumption_discharge_ok
            and self.bound_transfer_ok
            and self.authorization_ok
            and self.trace_signature_ok
            and self.sequence_ok  # __phase2_stage5_seq_conformance_v1__
            and self.codegen_binding_ok  # __s156_u3_ok_folds_codegen_v1__
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


_GATED_ACTION_PREIMAGE_TAG = b"nous-gated-action-approval:v1|"  # __s139_u1_attestation_preimage__


def _attestation_preimage(
    smt_spec_sha256: str,
    seq: int,
    action: str,
    principal_id: str,
) -> bytes:
    """Domain-separated, envelope-bound, identity-bound approval
    preimage. EXCLUDES the attestation's own signature (so a verifying
    attestation is constructable) and binds the approval to this exact
    decision (seq, action), this exact approver (principal_id), and this
    exact proof envelope (smt_spec_sha256) so an attestation cannot be
    replayed onto a different decision or a different world."""
    return (
        _GATED_ACTION_PREIMAGE_TAG
        + smt_spec_sha256.encode("utf-8")
        + b"|"
        + str(seq).encode("utf-8")
        + b"|"
        + action.encode("utf-8")
        + b"|"
        + principal_id.encode("utf-8")
    )


def sign_gated_action(
    private_key: Ed25519PrivateKey,
    smt_spec_sha256: str,
    seq: int,
    action: str,
    principal_id: str,
    timestamp_utc: str,
) -> AuthorizationAttestation:
    """Issuer-side approver signer: produce an AuthorizationAttestation
    whose Ed25519 signature covers the envelope-bound approval preimage.
    The verifier (obligation #5) re-derives the same preimage and checks
    the signature under the embedded public key."""
    pre = _attestation_preimage(smt_spec_sha256, seq, action, principal_id)
    raw_sig = private_key.sign(pre)
    pub_raw = private_key.public_key().public_bytes_raw()
    return AuthorizationAttestation(
        principal_id=principal_id,
        approved_seq=seq,
        timestamp_utc=timestamp_utc,
        public_key_b64=base64.b64encode(pub_raw).decode("ascii"),
        signature_b64=base64.b64encode(raw_sig).decode("ascii"),
    )


_DECISION_VERBS = ("approved", "denied", "overridden")  # __s151_u1_decision_verbs_v1__


def _attestation_preimage_v2(  # __s151_u1_attestation_preimage_v2__
    smt_spec_sha256: str,
    seq: int,
    action: str,
    principal_id: str,
    decision: str,
) -> bytes:
    """S151 decision-surface preimage. For decision == 'approved' it returns
    the EXACT S139/S141 v1 bytes (no verb), so every existing approval
    attestation verifies unchanged and all prior traces stay byte-identical.
    For 'denied'/'overridden' it folds the decision verb into the signed
    preimage, so an approval cannot be replayed as a refusal nor a refusal
    stripped to an approval. EVIDENCES that a named principal recorded this
    exact decision bound to this exact (seq, action) and proof envelope; it
    does NOT prove the decision correct, the principal authorized, or the
    oversight meaningful, and it does not evidence whether a refusal was
    honored at runtime (codegen/runtime unit)."""
    if decision not in _DECISION_VERBS:
        raise ValueError(
            f"unknown authorization decision {decision!r}; "
            f"expected one of {_DECISION_VERBS}"
        )
    base = _attestation_preimage(smt_spec_sha256, seq, action, principal_id)
    if decision == "approved":
        return base
    return base + b"|" + decision.encode("utf-8")


def sign_gated_decision(  # __s151_u1_sign_gated_decision__
    private_key: Ed25519PrivateKey,
    smt_spec_sha256: str,
    seq: int,
    action: str,
    principal_id: str,
    timestamp_utc: str,
    decision: str = "approved",
) -> AuthorizationAttestation:
    """Issuer-side approver signer for the full Article 14(4)(d) decision
    surface (approve / disregard-override-reverse). Signs the v2 preimage and
    records the decision verb. 'approved' is byte-identical to
    sign_gated_action (the v1 approval path)."""
    pre = _attestation_preimage_v2(
        smt_spec_sha256, seq, action, principal_id, decision
    )
    raw_sig = private_key.sign(pre)
    pub_raw = private_key.public_key().public_bytes_raw()
    return AuthorizationAttestation(
        principal_id=principal_id,
        approved_seq=seq,
        timestamp_utc=timestamp_utc,
        public_key_b64=base64.b64encode(pub_raw).decode("ascii"),
        signature_b64=base64.b64encode(raw_sig).decode("ascii"),
        decision=decision,
    )


def _check_sequence_obligations(  # __phase2_stage5_seq_conformance_v1__
    trace: TraceEnvelope,
    spec: "SMTSpec",
) -> tuple[bool, list[str]]:
    """Check every 'before(A, B)' law against the trace's action-labelled events.

    Label = TraceEvent.action (the existing optional domain-action field); a
    sequence-relevant event is one with action set. before(A, B) holds iff
    every event with action == B has some earlier event (smaller seq) with
    action == A. Vacuous (True) when the re-derived spec declares no laws.
    The laws come from the re-derived spec (recompute-never-trust), not from
    any unsigned sibling.
    """
    laws = spec.sequence_laws
    if not laws:
        return True, []
    by_action: dict[str, list[int]] = {}
    for ev in trace.events:
        if ev.action is not None:
            by_action.setdefault(ev.action, []).append(ev.seq)
    ok = True
    errors: list[str] = []
    for law in laws:  # __phase2_stage8_at_most_conformance_v1__
        kind, a, b, count = law.kind, law.label_a, law.label_b, law.count
        a_positions = by_action.get(a, [])
        if kind == "before":
            for bpos in by_action.get(b, []):
                if not any(apos < bpos for apos in a_positions):
                    ok = False
                    errors.append(
                        f"sequence: action={b!r} at seq={bpos} has no preceding "
                        f"action={a!r} (law before({a},{b}))"
                    )
        elif kind == "never_after":  # __phase2_stage7a_never_after_conformance_v1__
            for bpos in by_action.get(b, []):
                if any(apos < bpos for apos in a_positions):
                    ok = False
                    errors.append(
                        f"sequence: action={b!r} at seq={bpos} occurs after "
                        f"action={a!r} (law never_after({a},{b}))"
                    )
        elif kind == "leads_to":  # __phase2_stage7b_leads_to_conformance_v1__
            b_positions = by_action.get(b, [])
            for apos in a_positions:
                if not any(bpos > apos for bpos in b_positions):
                    ok = False
                    errors.append(
                        f"sequence: action={a!r} at seq={apos} has no following "
                        f"action={b!r} (law leads_to({a},{b}))"
                    )
        elif kind == "at_most":  # __phase2_stage8_at_most_conformance_v1__
            n_occurrences = len(a_positions)
            if n_occurrences > count:
                ok = False
                errors.append(
                    f"sequence: action={a!r} occurs {n_occurrences} time(s), "
                    f"exceeds at_most({count},{a})"
                )
    return ok, errors


def _sequence_vacuous_laws(  # __s104_seq_vacuous_helper_v1__
    trace: TraceEnvelope,
    spec: "SMTSpec",
) -> list[str]:
    laws = spec.sequence_laws
    if not laws:
        return []
    by_action: dict[str, list[int]] = {}
    for ev in trace.events:
        if ev.action is not None:
            by_action.setdefault(ev.action, []).append(ev.seq)
    vacuous: list[str] = []
    for law in laws:
        kind, a, b, count = law.kind, law.label_a, law.label_b, law.count
        present_a = bool(by_action.get(a, []))
        present_b = bool(by_action.get(b, [])) if b is not None else False
        if kind == "at_most":
            if not present_a:
                vacuous.append(f"at_most({count},{a}): 0 occurrences of {a!r}")
        elif kind == "never_after":
            if not present_a and not present_b:
                vacuous.append(f"never_after({a},{b}): 0 occurrences of {a!r} and {b!r}")
        elif kind == "leads_to":
            if not present_a:
                vacuous.append(f"leads_to({a},{b}): 0 occurrences of {a!r}")
        else:
            if not present_b:
                vacuous.append(f"before({a},{b}): 0 occurrences of {b!r}")
    return vacuous


def count_distinct_approving_keys(  # __s154_u1_count_approvers_helper_v1__
    smt_spec_sha256: str,
    event: TraceEvent,
) -> set[str]:
    """Distinct valid APPROVING Ed25519 public keys bound to this gated event.

    Factored verbatim from verify_conformance obligation #5 (S153 U2.4) so the
    decision-ledger presentation (S154) and the conformance verdict count an
    approver by the EXACT same rule, never two definitions. A key counts iff its
    attestation has approved_seq == event.seq, decision == "approved", and its
    Ed25519 signature verifies over _attestation_preimage_v2(smt_spec_sha256,
    seq, action, principal_id, decision). Distinctness is on public_key_b64.
    EVIDENCES distinct signing keys recorded approvals bound to this exact
    (seq, action, proof envelope); does NOT prove K natural persons, authority,
    independence, or runtime enforcement.
    """
    approving_keys: set[str] = set()
    if event.action is None:
        return approving_keys
    for _att in [event.authorization, *(event.co_authorizations or [])]:
        if _att is None:
            continue
        if _att.approved_seq != event.seq:
            continue
        if _att.decision != "approved":
            continue
        _payload = _attestation_preimage_v2(
            smt_spec_sha256,
            event.seq,
            event.action,
            _att.principal_id,
            _att.decision,
        )
        try:
            _pub = Ed25519PublicKey.from_public_bytes(
                base64.b64decode(_att.public_key_b64, validate=True)
            )
            _pub.verify(
                base64.b64decode(_att.signature_b64, validate=True),
                _payload,
            )
        except (InvalidSignature, ValueError):
            continue
        approving_keys.add(_att.public_key_b64)
    return approving_keys


def verify_conformance(
    trace: TraceEnvelope,
    manifest: Manifest,
    spec: "SMTSpec",
    pricing_table: PricingTable,
    *,
    aprs: Optional[list[AttestationPinningRecord]] = None,  # __s145_u4a_signature_v1__
    attest_trust_root_public_key: Optional[Ed25519PublicKey] = None,
    codegen_sha256: Optional[str] = None,  # __s155_u5_codegen_binding_arg_v1__
) -> ConformanceDetail:
    bounds = _bounds_from_spec(spec)
    if not bounds:
        raise ConformancePreconditionError(
            "re-derived spec carries no soul_assumptions; cannot establish "
            "per-soul bounds (the proof declared no costed souls)"
        )

    cost_cap: Decimal = spec.cost_cap_amount
    max_ticks: int = spec.max_ticks
    gated_actions = frozenset(spec.gated_actions)  # __s141_u5_gated_signed_source_v1__
    quorum_by_action = dict(spec.gated_quorums)  # __s153_u2_4_quorum_obligation_v1__
    declared_events = frozenset(spec.declared_events)  # __s414_tool_surface_v1__

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
        if (
            ev.action is not None
            and ev.action in gated_actions
            and ev.kind != "gated_action"
        ):
            raise ConformancePreconditionError(  # __s143_u1_gated_kind_converse_v1__
                f"event seq={ev.seq} action {ev.action!r} is a declared "
                f"gated action but kind={ev.kind!r} (expected "
                f"'gated_action'); a gated action recorded under a "
                f"non-gated kind is trace tampering"
            )
        if ev.kind == "tool_call" and declared_events:  # __s414_tool_surface_v1__
            if ev.action is None:
                raise ConformancePreconditionError(
                    f"event seq={ev.seq} is a tool_call with no action "
                    f"label while the spec declares events "
                    f"{sorted(declared_events)}; a tool_call outside the "
                    f"declared tool surface cannot be checked"
                )
            if ev.action not in declared_events:
                raise ConformancePreconditionError(
                    f"event seq={ev.seq} tool_call action {ev.action!r} "
                    f"not in declared events {sorted(declared_events)} "
                    f"(run did something the spec never declared)"
                )

    _ek = trace.evidence_kind  # __s144_u3_conformance_trust_precondition_v1__
    _cb = trace.cost_binding
    _pti = trace.provider_token_integrity
    if _ek is not None and _ek not in ("envelope", "witnessed_run"):
        raise ConformancePreconditionError(
            f"trust: evidence_kind {_ek!r} is not in the frozen vocabulary"
        )
    if _cb is not None and _cb not in ("envelope", "realized"):
        raise ConformancePreconditionError(
            f"trust: cost_binding {_cb!r} is not in the frozen vocabulary"
        )
    if _pti is not None and _pti not in (
        "unattested", "tee_attested", "unverifiable"
    ):
        raise ConformancePreconditionError(
            f"trust: provider_token_integrity {_pti!r} is not in the "
            f"frozen vocabulary"
        )
    _realized = _cb == "realized"
    _witnessed = _ek == "witnessed_run"
    if _realized != _witnessed:
        raise ConformancePreconditionError(
            f"trust: cost_binding={_cb!r} and evidence_kind={_ek!r} are "
            f"inconsistent; realized cost requires a witnessed_run and "
            f"vice versa"
        )
    if _pti == "tee_attested":  # __s145_u4a_tee_verify_v1__
        if aprs is None or attest_trust_root_public_key is None:
            raise ConformancePreconditionError(
                "trust: provider_token_integrity='tee_attested' requires an "
                "attached, verifier-checked inference receipt and a pinned "
                "trust root; none supplied, so the claim is refused fail-closed"
            )
        _attest_verdict = verify_trace_attestation(
            trace, aprs, attest_trust_root_public_key
        )
        if not _attest_verdict.attested:
            raise ConformancePreconditionError(
                "trust: provider_token_integrity='tee_attested' claim is not "
                "backed by a verified inference receipt: "
                + _attest_verdict.reason
            )
    errors: list[str] = []

    # 1. binding: re-derived spec + supplied pricing match the manifest's
    #    shas (its signature is not verified here), and the trace claims
    #    those same shas.  # __x_g4_wording_v1__
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
    # __s156_u3_codegen_binding_obligation_v1__ decoupled from binding_ok
    # (axiom 8: codegen gets its own obligation). sha-equality across the
    # present legs (trace, manifest, re-derived); vacuous when fewer than
    # two are present. EVIDENCES that the trace names the exact compiled
    # program; does NOT prove the run executed.
    codegen_binding_ok = True
    _codegen_legs = [
        v for v in (
            trace.codegen_sha256,
            manifest.codegen_sha256,
            codegen_sha256,
        ) if v is not None
    ]
    if len(set(_codegen_legs)) > 1:
        codegen_binding_ok = False
        errors.append(
            "codegen_binding: trace/manifest/re-derived codegen_sha256 "
            "disagree (trace names a compiled program the source "
            "does not produce)"
        )

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
    #    attestation bound to that exact event. (gated_actions is sourced
    #    from the signed spec, not the advisory sibling -- S141.)
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
        if ev.action is None:
            authorization_ok = False
            errors.append(
                f"authorization: gated event seq={ev.seq} has no action label"
            )
            continue
        payload = _attestation_preimage_v2(  # __s151_u1_obligation5_decision_v1__
            trace.smt_spec_sha256,
            ev.seq,
            ev.action,
            auth.principal_id,
            auth.decision,
        )
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
        k_required = quorum_by_action.get(ev.action, 1)  # __s153_u2_4_quorum_obligation_v1__
        if k_required > 1:
            approving_keys = count_distinct_approving_keys(  # __s154_u1_count_approvers_helper_v1__
                trace.smt_spec_sha256, ev
            )
            if len(approving_keys) < k_required:
                authorization_ok = False
                errors.append(
                    f"authorization: gated event seq={ev.seq} quorum not "
                    f"met: {len(approving_keys)} distinct approving "
                    f"key(s), need {k_required}"
                )

    # 6. trace signature.
    trace_signature_ok = verify_trace_signature(trace)
    if not trace_signature_ok:
        errors.append("trace_signature: Ed25519 verify failed")

    # 7. sequence obligations (Phase 2 stage 5): every 'before(A,B)' law must
    #    hold over the trace's action-labelled events. Vacuous (True) when the
    #    re-derived spec declares no sequence laws.
    sequence_ok, sequence_errors = _check_sequence_obligations(trace, spec)  # __phase2_stage5_seq_conformance_v1__
    errors.extend(sequence_errors)
    return ConformanceDetail(
        binding_ok=binding_ok,
        surface_ok=surface_ok,
        assumption_discharge_ok=assumption_discharge_ok,
        bound_transfer_ok=bound_transfer_ok,
        authorization_ok=authorization_ok,
        trace_signature_ok=trace_signature_ok,
        realized_total=str(realized_total),
        cost_cap=str(cost_cap),
        sequence_vacuous=tuple(_sequence_vacuous_laws(trace, spec)),  # __s104_seq_vacuous_construct_v1__
        sequence_ok=sequence_ok,  # __phase2_stage5_seq_conformance_v1__
        cost_binding=trace.cost_binding,  # __s144_u3_conformance_trust_precondition_v1__
        provider_token_integrity=trace.provider_token_integrity,
        codegen_binding_ok=codegen_binding_ok,  # __s156_u3_detail_return_v1__
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

CERTIFICATE_SCHEMA_VERSION: int = 4  # __s156_u2_cert_schema_v4__ (was 3; +codegen leg)  # __s144_u4_cert_trust_fields_v1__ (was 2; +trust mirror)


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
    sequence_ok: bool = True  # __phase2_stage5b_cert_v1__
    conformant: bool

    realized_total: str = Field(min_length=1)
    cost_cap: str = Field(min_length=1)
    cost_currency: str = Field(min_length=1)
    errors: tuple[str, ...] = Field(default=())
    cost_binding: Optional[str] = Field(default=None)  # __s144_u4_cert_trust_fields_v1__
    provider_token_integrity: Optional[str] = Field(default=None)

    codegen_sha256: Optional[str] = Field(default=None)  # __s156_u2_cert_codegen_field_v1__
    codegen_binding_ok: bool = True  # __s156_u2_cert_codegen_binding_ok__
    obligations_canon: Optional[str] = Field(default=None)  # __s187b_1a_cert_obligations_canon_field_v1__
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
        if self.certificate_schema_version < 2:  # __phase2_stage5b_cert_v1__
            doc.pop("sequence_ok", None)
        if self.certificate_schema_version < 3:  # __s144_u4_cert_trust_fields_v1__
            doc.pop("cost_binding", None)
            doc.pop("provider_token_integrity", None)
        if self.certificate_schema_version < 4:  # __s156_u2_canon_method_gate_v1__
            doc.pop("codegen_sha256", None)
            doc.pop("codegen_binding_ok", None)
        if doc.get("obligations_canon") is None:  # __s187b_1a_canon_drop_none_method_v1__
            doc.pop("obligations_canon", None)
        return _json_cert.dumps(
            doc, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")


def _cert_public_key_raw_b64(public_key: Ed25519PublicKey) -> str:  # __nous_conformance_certificate_v1__
    raw: bytes = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def obligations_canon_for(  # __nt_v1b_certify_canon_rule_v1__
    manifest: Manifest,
    spec: "SMTSpec",
    emit: bool = False,
) -> Optional[str]:
    """The one rule for carrying the governing spec canon in a
    certificate: always when the manifest declares a cost proof
    (cost_farkas_sha256), so an offline verifier can re-derive the cost
    system it grades; otherwise only on request. The canon is what the
    signed manifest names by smt_spec_sha256."""
    if emit or manifest.cost_farkas_sha256 is not None:
        return spec.canonical_str()
    return None


def build_certificate(  # __nous_conformance_certificate_v1__
    detail: ConformanceDetail,
    trace: TraceEnvelope,
    manifest: Manifest,
    *,
    nous_version: str,
    issued_utc: str,
    obligations_canon: Optional[str] = None,  # __s187b_1a_build_cert_arg_v1__
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
        sequence_ok=detail.sequence_ok,  # __phase2_stage5b_cert_v1__
        conformant=detail.ok,
        realized_total=detail.realized_total,
        cost_cap=detail.cost_cap,
        cost_currency="USD",
        errors=tuple(detail.errors),
        cost_binding=detail.cost_binding,  # __s144_u4_cert_trust_fields_v1__
        provider_token_integrity=detail.provider_token_integrity,
        codegen_sha256=manifest.codegen_sha256,  # __s156_u3_build_cert_codegen_v1__
        codegen_binding_ok=detail.codegen_binding_ok,
        obligations_canon=obligations_canon,  # __s187b_1a_build_cert_set_v1__
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
        sequence_ok=cert.sequence_ok,  # __phase2_stage5b_sign_seqfix_v1__
        conformant=cert.conformant,
        realized_total=cert.realized_total,
        cost_cap=cert.cost_cap,
        cost_currency=cert.cost_currency,
        errors=tuple(cert.errors),
        cost_binding=cert.cost_binding,  # __s144_u4_cert_trust_fields_v1__
        provider_token_integrity=cert.provider_token_integrity,
        codegen_sha256=cert.codegen_sha256,  # __s156_u2_sign_reconstruct_v1__
        codegen_binding_ok=cert.codegen_binding_ok,
        obligations_canon=cert.obligations_canon,  # __s187b_1a_sign_reconstruct_v1__
        transparency_log=cert.transparency_log,  # __nous_conformance_cert_anchor_v1__
        signature=sig,
    )


_X_SIGNER_MISMATCH = "certificate signer is not the expected key"  # __x_g1_pinned_signer_v1__
_X_SIGNER_BADKEY = (  # __x_g1_pinned_signer_v1__
    "expected signer key is not a base64 raw 32-byte Ed25519 public key"
)


def _x_pinned_raw(expected_b64: str) -> Optional[bytes]:  # __x_g1_pinned_signer_v1__
    """Decode an auditor-pinned Ed25519 public key: strict base64, 32 raw bytes.

    Returns None when the value is not a usable key. The pinned key is the
    trust anchor; the key a certificate carries is a hint that must equal it
    (the closure_attestation.verify_signature shape). EVIDENCES that the
    certificate was signed by the holder of the pinned key; who holds that
    key is established out of band and is not claimed here.
    """
    try:
        raw = base64.b64decode(expected_b64, validate=True)
    except (ValueError, TypeError):
        return None
    return raw if len(raw) == 32 else None


def verify_certificate_signature(  # __nous_conformance_certificate_v1__
    cert: ConformanceCertificate,
    *,
    expected_public_key_b64: Optional[str] = None,  # __x_g1_pinned_signer_v1__
) -> bool:
    if cert.signature is None:
        return False
    if cert.signature.algorithm != "ed25519":
        return False
    try:
        pub_raw: bytes = base64.b64decode(
            cert.signature.public_key_b64, validate=True
        )
        if expected_public_key_b64 is not None:  # __x_g1_pinned_signer_v1__
            pinned_raw = _x_pinned_raw(expected_public_key_b64)
            if pinned_raw is None or pinned_raw != pub_raw:
                return False
            pub_raw = pinned_raw
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
    if doc.get("obligations_canon") is None:  # __s187b_1a_cert_json_drop_none_v1__
        doc.pop("obligations_canon", None)
    if cert.certificate_schema_version < 2:  # __phase2_stage5b_cert_v1__
        doc.pop("sequence_ok", None)
    if cert.certificate_schema_version < 4:  # __s156_u2_cert_json_gate_v1__
        doc.pop("codegen_sha256", None)
        doc.pop("codegen_binding_ok", None)
    doc["errors"] = list(cert.errors)
    return _json_cert.dumps(doc, indent=2, sort_keys=True) + "\n"


def load_certificate(path: str) -> ConformanceCertificate:  # __nous_conformance_certificate_v1__
    with open(path, "r", encoding="utf-8") as fh:
        data = _json_cert.load(fh)
    return ConformanceCertificate(**data)


# __nous_s98_stage1_lib_v1__
# Lib-level verification API used by the public /v1/verify-conformance
# endpoint and by any caller that has the JSON in hand (no paths required).

from typing import Literal as _Literal


class CertificateCheck(BaseModel):
    """One named verification step + human-readable detail.

    `ok` is True for pass, False for fail. `detail` is None on pass; on
    failure it carries a short reason string. `skipped` marks checks that
    were not run because optional input was missing (e.g. trace_json absent
    -> trace_binding skipped).
    """
    model_config = ConfigDict(strict=True, extra="forbid")
    ok: bool
    detail: Optional[str] = None
    skipped: bool = False


class AnchorCheck(BaseModel):
    """Rekor v2 transparency-log anchor sub-checks (when cert is anchored).

    Mirrors the rekor_verify_v2 read path: leaf digest, leaf signature,
    checkpoint signature, inclusion proof. overall_ok is the AND of all four.
    Present only when the certificate carries a `transparency_log` block.
    """
    model_config = ConfigDict(strict=True, extra="forbid")
    leaf_digest_ok: bool
    leaf_sig_ok: bool
    checkpoint_sig_ok: bool
    inclusion_proof_ok: bool
    overall_ok: bool
    log_index: Optional[int] = None
    checkpoint_origin: Optional[str] = None
    detail: Optional[str] = None


class CertificateVerificationResult(BaseModel):
    """Top-level verification result, parity with verify-dossier/v2 shape.

    `verdict` summarizes:
      PASS         all RUN checks ok and recorded conformant is True
      FAIL         at least one RUN check failed or recorded conformant False
      INCONCLUSIVE certificate parsed and signed but binding/anchor checks
                   could not be run because the optional inputs were absent
      MALFORMED    the certificate JSON itself failed to parse / validate
    """
    model_config = ConfigDict(strict=True, extra="forbid")
    spec_version: _Literal["verify-conformance/v1"] = "verify-conformance/v1"
    parsed: bool
    signature: CertificateCheck
    verdict_consistency: CertificateCheck
    trace_binding: CertificateCheck
    trace_signature: CertificateCheck
    manifest_binding: CertificateCheck
    anchor: Optional[AnchorCheck] = None
    conformant: Optional[bool] = None
    verdict: _Literal["PASS", "FAIL", "INCONCLUSIVE", "MALFORMED"]
    errors: list[str] = Field(default_factory=list)


_OBLIGATION_FIELDS = (
    "binding_ok",
    "surface_ok",
    "assumption_discharge_ok",
    "bound_transfer_ok",
    "authorization_ok",
    "trace_signature_ok",
)

_OBLIGATION_FIELDS_V2 = _OBLIGATION_FIELDS + ("sequence_ok",)  # __phase2_stage5b_cert_v1__
_OBLIGATION_FIELDS_V4 = _OBLIGATION_FIELDS_V2 + ("codegen_binding_ok",)  # __s156_u2_oblig_v4_tuple_v1__


def _obligation_fields_for(schema_version: int) -> tuple:  # __phase2_stage5b_cert_v1__
    if schema_version >= 4:  # __s156_u2_oblig_for_v4_v1__
        return _OBLIGATION_FIELDS_V4
    return _OBLIGATION_FIELDS_V2 if schema_version >= 2 else _OBLIGATION_FIELDS


def _malformed(reason: str) -> "CertificateVerificationResult":
    skipped = CertificateCheck(ok=False, skipped=True, detail="not run")
    return CertificateVerificationResult(
        parsed=False,
        signature=CertificateCheck(ok=False, skipped=True, detail="not run"),
        verdict_consistency=skipped,
        trace_binding=skipped,
        trace_signature=skipped,
        manifest_binding=skipped,
        anchor=None,
        conformant=None,
        verdict="MALFORMED",
        errors=[reason],
    )


def _canonical_body_bytes_dict(doc: dict) -> bytes:
    import json as _json  # __nous_s98_stage1_imports_hotfix_v1__
    body = {k: v for k, v in doc.items() if k != "signature"}
    return _json.dumps(
        body, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _cert_canonical_body_bytes_dict(doc: dict) -> bytes:
    # __nous_s98_stage1_cert_canon_hotfix_v1__ + __phase2_stage5b_cert_v1__
    # Parity with ConformanceCertificate.certificate_canonical_body_bytes:
    # signature is excluded (signature signs over body), AND
    # transparency_log is excluded (anchor is stapled after signing).
    # For schema_version < 2 (v1 certs), sequence_ok is popped to preserve
    # byte-identity with bodies signed before stage 5b shipped the field.
    import json as _json
    body = {
        k: v for k, v in doc.items()
        if k not in ("signature", "transparency_log")
    }
    if int(body.get("certificate_schema_version", 1)) < 2:
        body.pop("sequence_ok", None)
    if int(body.get("certificate_schema_version", 1)) < 3:  # __s144_u4_cert_trust_fields_v1__
        body.pop("cost_binding", None)
        body.pop("provider_token_integrity", None)
    if int(body.get("certificate_schema_version", 1)) < 4:  # __s156_u2_canon_dict_gate_v1__
        body.pop("codegen_sha256", None)
        body.pop("codegen_binding_ok", None)
    if body.get("obligations_canon") is None:  # __s187b_1a_canon_drop_none_dict_v1__
        body.pop("obligations_canon", None)
    return _json.dumps(
        body, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def verify_certificate_from_json(
    cert_json: str,
    trace_json: Optional[str] = None,
    manifest_json: Optional[str] = None,
    *,
    expected_signer_b64: Optional[str] = None,  # __x_g1_pinned_signer_v1__
) -> CertificateVerificationResult:
    """Verify a runtime conformance certificate from JSON strings.

    Pure function: no I/O, no network. Inputs are JSON text. Optional
    trace_json / manifest_json enable the binding checks; their absence
    causes those checks to be marked skipped (not failed).

    The set of checks mirrors the emitted offline verifier:
      1. certificate Ed25519 signature over its canonical body
      2. recorded six-obligation booleans consistent with cert.conformant
      3. cert.trace_sha256 == sha256(trace canonical body)   [needs trace]
      4. trace Ed25519 signature over trace canonical body   [needs trace]
      5. cert {source,smt_spec,pricing}_sha256 == manifest's [needs manifest]
      6. if cert carries transparency_log: Rekor v2 leaf+checkpoint+proof
    """
    import base64 as _b64
    import json  # __nous_s98_stage1_imports_hotfix_v1__
    import hashlib  # __nous_s98_stage1_imports_hotfix_v1__
    try:
        cert_doc = json.loads(cert_json)
    except json.JSONDecodeError as exc:
        return _malformed(f"cert_json parse error: {exc}")
    if not isinstance(cert_doc, dict):
        return _malformed("cert_json is not a JSON object")

    try:
        cert = ConformanceCertificate.model_validate(
            {k: v for k, v in cert_doc.items() if k != "signature"}
        )
    except Exception as exc:
        return _malformed(f"certificate validation failed: {type(exc).__name__}: {exc}")

    skipped = CertificateCheck(ok=False, skipped=True, detail="not run")
    errors: list[str] = []

    sig_block = cert_doc.get("signature")
    if not isinstance(sig_block, dict):
        return _malformed("certificate has no signature block")
    if sig_block.get("algorithm") != "ed25519":
        return _malformed("certificate signature algorithm is not ed25519")
    cpub_b64 = sig_block.get("public_key_b64", "")
    csig_b64 = sig_block.get("signature_b64", "")
    if not cpub_b64 or not csig_b64:
        return _malformed("certificate signature block incomplete")

    _x_pin_raw: Optional[bytes] = None  # __x_g1_pinned_signer_v1__
    if expected_signer_b64 is not None:
        _x_pin_raw = _x_pinned_raw(expected_signer_b64)
        if _x_pin_raw is None:
            return _malformed(_X_SIGNER_BADKEY)
    _x_mismatch = False
    if _x_pin_raw is not None:
        try:
            _x_mismatch = _b64.b64decode(cpub_b64, validate=True) != _x_pin_raw
        except (ValueError, TypeError):
            _x_mismatch = True

    body_bytes = _cert_canonical_body_bytes_dict(cert_doc)  # __nous_s98_stage1_cert_canon_hotfix_v1__
    if _x_mismatch:  # __x_g1_pinned_signer_v1__
        signature_check = CertificateCheck(ok=False, detail=_X_SIGNER_MISMATCH)
        errors.append(_X_SIGNER_MISMATCH)
    else:
        try:
            cpub = Ed25519PublicKey.from_public_bytes(
                _x_pin_raw
                if _x_pin_raw is not None
                else _b64.b64decode(cpub_b64, validate=True)
            )
            cpub.verify(_b64.b64decode(csig_b64, validate=True), body_bytes)
            signature_check = CertificateCheck(ok=True)
        except Exception as exc:
            signature_check = CertificateCheck(
                ok=False, detail=f"ed25519 verify failed: {type(exc).__name__}"
            )
            errors.append("certificate Ed25519 signature does not verify")

    schema_v = int(cert_doc.get("certificate_schema_version", 1))  # __phase2_stage5b_cert_v1__
    obligation_fields = _obligation_fields_for(schema_v)
    missing = [b for b in obligation_fields if b not in cert_doc]
    if missing:
        verdict_check = CertificateCheck(
            ok=False, detail=f"missing obligation fields: {missing}"
        )
        errors.append(f"certificate missing obligation fields: {missing}")
    else:
        derived = all(bool(cert_doc[b]) for b in obligation_fields)
        recorded = bool(cert_doc.get("conformant"))
        if derived == recorded:
            verdict_check = CertificateCheck(ok=True)
        else:
            verdict_check = CertificateCheck(
                ok=False,
                detail=(
                    f"recorded conformant={recorded} but "
                    f"{len(obligation_fields)} obligations imply {derived}"
                ),
            )
            errors.append("recorded verdict inconsistent with obligations")

    if trace_json is None:
        trace_binding = skipped
        trace_signature = skipped
    else:
        try:
            trace_doc = json.loads(trace_json)
            if not isinstance(trace_doc, dict):
                raise ValueError("trace_json is not a JSON object")
        except (json.JSONDecodeError, ValueError) as exc:
            trace_binding = CertificateCheck(
                ok=False, detail=f"trace_json parse error: {exc}"
            )
            trace_signature = CertificateCheck(
                ok=False, detail="not evaluated (trace_json malformed)"
            )
            errors.append("trace_json malformed")
        else:
            tbody = _canonical_body_bytes_dict(trace_doc)
            tsha = hashlib.sha256(tbody).hexdigest()
            if cert_doc.get("trace_sha256") == tsha:
                trace_binding = CertificateCheck(ok=True)
            else:
                trace_binding = CertificateCheck(
                    ok=False,
                    detail=(
                        f"cert.trace_sha256={str(cert_doc.get('trace_sha256'))[:16]}... "
                        f"trace_actual={tsha[:16]}..."
                    ),
                )
                errors.append("trace_binding mismatch")
            tsig_block = trace_doc.get("signature")
            if not isinstance(tsig_block, dict):
                trace_signature = CertificateCheck(
                    ok=False, detail="trace has no signature block"
                )
                errors.append("trace missing signature")
            elif tsig_block.get("algorithm") != "ed25519":
                trace_signature = CertificateCheck(
                    ok=False, detail="trace signature algorithm is not ed25519"
                )
                errors.append("trace signature non-ed25519")
            else:
                try:
                    tpub = Ed25519PublicKey.from_public_bytes(
                        _b64.b64decode(
                            tsig_block.get("public_key_b64", ""), validate=True
                        )
                    )
                    tpub.verify(
                        _b64.b64decode(
                            tsig_block.get("signature_b64", ""), validate=True
                        ),
                        tbody,
                    )
                    trace_signature = CertificateCheck(ok=True)
                except Exception as exc:
                    trace_signature = CertificateCheck(
                        ok=False,
                        detail=f"trace ed25519 verify failed: {type(exc).__name__}",
                    )
                    errors.append("trace signature does not verify")

    if manifest_json is None:
        manifest_binding = skipped
    else:
        try:
            man_doc = json.loads(manifest_json)
            if not isinstance(man_doc, dict):
                raise ValueError("manifest_json is not a JSON object")
        except (json.JSONDecodeError, ValueError) as exc:
            manifest_binding = CertificateCheck(
                ok=False, detail=f"manifest_json parse error: {exc}"
            )
            errors.append("manifest_json malformed")
        else:
            mismatches = []
            for fld in ("source_sha256", "smt_spec_sha256", "pricing_sha256"):
                if cert_doc.get(fld) != man_doc.get(fld):
                    mismatches.append(fld)
            if mismatches:
                manifest_binding = CertificateCheck(
                    ok=False,
                    detail=f"manifest binding mismatches in: {mismatches}",
                )
                errors.append(f"manifest binding mismatch: {mismatches}")
            else:
                manifest_binding = CertificateCheck(ok=True)

    anchor: Optional[AnchorCheck] = None
    tlog = cert_doc.get("transparency_log")
    if isinstance(tlog, dict):
        try:
            from rekor_verify_v2 import (
                verify_rekor_v2_anchor,
                load_trusted_log_keys,
                RekorV2AnchorMalformed,
            )
            keys = load_trusted_log_keys()
            detail = verify_rekor_v2_anchor(
                manifest_body_bytes=body_bytes,
                block=tlog,
                trusted_log_keys=keys,
            )
            anchor = AnchorCheck(
                leaf_digest_ok=detail.leaf_digest_ok,
                leaf_sig_ok=detail.leaf_sig_ok,
                checkpoint_sig_ok=detail.checkpoint_sig_ok,
                inclusion_proof_ok=detail.inclusion_proof_ok,
                overall_ok=detail.ok,
                log_index=detail.log_index,
                checkpoint_origin=detail.checkpoint_origin,
                detail="; ".join(detail.errors) if detail.errors else None,
            )
            if not detail.ok:
                errors.append("rekor_v2 anchor verification failed")
        except RekorV2AnchorMalformed as exc:
            anchor = AnchorCheck(
                leaf_digest_ok=False,
                leaf_sig_ok=False,
                checkpoint_sig_ok=False,
                inclusion_proof_ok=False,
                overall_ok=False,
                log_index=None,
                checkpoint_origin=None,
                detail=f"anchor block malformed: {exc}",
            )
            errors.append("rekor_v2 anchor block malformed")
        except Exception as exc:
            anchor = AnchorCheck(
                leaf_digest_ok=False,
                leaf_sig_ok=False,
                checkpoint_sig_ok=False,
                inclusion_proof_ok=False,
                overall_ok=False,
                log_index=None,
                checkpoint_origin=None,
                detail=f"anchor verify error: {type(exc).__name__}: {exc}",
            )
            errors.append("rekor_v2 anchor verify error")

    recorded_conformant = (
        bool(cert_doc.get("conformant"))
        if "conformant" in cert_doc
        else None
    )

    ran_checks: list[CertificateCheck] = [signature_check, verdict_check]
    if not trace_binding.skipped:
        ran_checks.extend([trace_binding, trace_signature])
    if not manifest_binding.skipped:
        ran_checks.append(manifest_binding)
    all_ran_ok = all(c.ok for c in ran_checks)
    anchor_ok = (anchor is None) or anchor.overall_ok

    inconclusive = (
        trace_binding.skipped or manifest_binding.skipped
    ) and all_ran_ok and anchor_ok and recorded_conformant is True

    if not all_ran_ok or not anchor_ok:
        verdict = "FAIL"
    elif inconclusive:
        verdict = "INCONCLUSIVE"
    elif recorded_conformant is True:
        verdict = "PASS"
    else:
        verdict = "FAIL"

    return CertificateVerificationResult(
        parsed=True,
        signature=signature_check,
        verdict_consistency=verdict_check,
        trace_binding=trace_binding,
        trace_signature=trace_signature,
        manifest_binding=manifest_binding,
        anchor=anchor,
        conformant=recorded_conformant,
        verdict=verdict,  # type: ignore[arg-type]
        errors=errors,
    )


# --- conformance recompute embed (shared text; canonical copy: conformance.py) ---
# Every offline conformance verifier carries this region byte-for-byte;
# tests/test_nt_v2_recompute.py names any copy that drifts. Standard
# library only. It recomputes the cost obligations (NT-GATE-1 D6 (i))
# from trace.json and the spec canon the certificate carries, bound by
# sha256 to the manifest's smt_spec_sha256. __nt_v2_recompute_v1__
_CONF_RC_MAX_BYTES = 16 * 1024 * 1024
_CONF_RC_MAX_DEPTH = 32
_CONF_RC_MAX_DIGITS = 64
_CONF_RC_KINDS = ("llm_call", "tool_call", "message", "gated_action")
_CONF_RC_SCOPE = (
    "binding_ok", "surface_ok", "assumption_discharge_ok",
    "bound_transfer_ok",
)


def _conf_rc_load(raw):
    # Strict JSON: UTF-8, non-ASCII only inside strings, bounded size
    # and nesting, no duplicate key, no NaN or Infinity, no float.
    # Returns (doc, "") or (None, why).
    import json
    if not isinstance(raw, (bytes, bytearray)):
        return None, "input is not bytes"
    if len(raw) > _CONF_RC_MAX_BYTES:
        return None, "larger than %d bytes" % _CONF_RC_MAX_BYTES
    try:
        text = bytes(raw).decode("utf-8")
    except UnicodeDecodeError:
        return None, "not UTF-8"
    depth = 0
    in_str = False
    esc = False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ord(ch) > 127:
            return None, "non-ASCII outside a string"
        elif ch in "[{":
            depth += 1
            if depth > _CONF_RC_MAX_DEPTH:
                return None, "nested deeper than %d" % _CONF_RC_MAX_DEPTH
        elif ch in "]}":
            depth -= 1

    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError("duplicate key " + repr(k))
            out[k] = v
        return out

    def no_constant(name):
        raise ValueError("non-finite number " + name)

    def no_float(s):
        raise ValueError("non-integer number " + s)

    try:
        doc = json.loads(text, object_pairs_hook=pairs,
                         parse_constant=no_constant, parse_float=no_float)
    except (ValueError, RecursionError) as exc:
        return None, str(exc)
    return doc, ""


def _conf_rc_rational(s):
    # "123" or "(/ 1 2)" -> Fraction; None outside the closed shape.
    import re
    from fractions import Fraction
    m = re.fullmatch(r"([0-9]+)|\(/ ([0-9]+) ([0-9]+)\)", s)
    if m is None:
        return None
    parts = [g for g in m.groups() if g is not None]
    if any(len(p) > _CONF_RC_MAX_DIGITS for p in parts):
        return None
    if m.group(1) is not None:
        return Fraction(int(m.group(1)))
    if int(m.group(3)) == 0:
        return None
    return Fraction(int(m.group(2)), int(m.group(3)))


def _conf_rc_decimal(s):
    # A decimal string, as Decimal prints one ("0.00105", "1E-7") ->
    # Fraction; None otherwise.
    import re
    from fractions import Fraction
    if not isinstance(s, str):
        return None
    m = re.fullmatch(r"(-?)([0-9]+)(?:\.([0-9]+))?(?:E([-+]?[0-9]{1,3}))?", s)
    if m is None or len(m.group(2)) + len(m.group(3) or "") > \
            _CONF_RC_MAX_DIGITS:
        return None
    frac = m.group(3) or ""
    v = Fraction(int(m.group(2) + frac), 10 ** len(frac))
    if m.group(4) is not None:
        v *= Fraction(10) ** int(m.group(4))
    return -v if m.group(1) else v


def _conf_rc_text(fr):
    # Exact decimal text of a Fraction whose denominator is 2^a 5^b.
    sign = "-" if fr < 0 else ""
    x = abs(fr)
    k = 0
    while x.denominator != 1 and k < 4 * _CONF_RC_MAX_DIGITS:
        x *= 10
        k += 1
    if x.denominator != 1:
        return sign + str(abs(fr))
    digits = str(x.numerator).rjust(k + 1, "0")
    if k == 0:
        return sign + digits
    head, tail = digits[:-k], digits[-k:].rstrip("0")
    return sign + head + ("." + tail if tail else "")


def _conf_rc_parse_canon(canon_text):
    # Closed shapes of smt_emit.canonical_str. Returns a dict, or a str
    # naming the first line outside the shapes.
    import re
    from fractions import Fraction
    if not isinstance(canon_text, str):
        return "spec canon is not text"
    # The grammar's NAME class (nous.lark): Latin and U+0370..U+03FF.
    gr = r"\u0370-\u03FF"
    nb = r"[A-Za-z_" + gr + r"][A-Za-z0-9_" + gr + r"]*"
    nm = "(" + nb + ")"
    rt = r"([0-9]+|\(/ [0-9]+ [0-9]+\))"
    re_pc = re.compile(
        r"A:\(assert \(= cost_" + nm + r"_per_call \(/ \(\+ \(\* " + rt
        + r" ([0-9]+)\) \(\* " + rt + r" ([0-9]+)(?: " + rt
        + r")?\)\) 1000000\)\)\)")
    re_tt = re.compile(
        r"A:\(assert \(= cost_" + nm + r"_total \(\* cost_" + nm
        + r"_per_call ([0-9]+)\)\)\)")
    re_t1 = re.compile(r"A:\(assert \(= total_cost cost_" + nm
                       + r"_total\)\)")
    re_tn = re.compile(r"A:\(assert \(= total_cost \(\+ ((?:cost_"
                       + nb + r"_total ?)+)\)\)\)")
    out = {"souls": {}, "ga": set(), "de": set()}
    seen = set()
    totals = {}
    sum_line = None
    for line in canon_text.split("\n"):
        tag, sep, rest = line.partition(":")
        if not sep:
            return "a line without a tag"
        if tag in ("CC", "MT", "MARGIN", "SS", "PS"):
            if tag in seen:
                return "duplicate " + tag + " line"
            seen.add(tag)
        if tag == "CC":
            m = re.fullmatch(r"([0-9]+)(?:\.([0-9]+))?\|([A-Z]{3})", rest)
            if m is None or len(m.group(1) + (m.group(2) or "")) > \
                    _CONF_RC_MAX_DIGITS:
                return "CC line outside the closed shape"
            out["cap"] = _conf_rc_decimal(
                m.group(1) + ("." + m.group(2) if m.group(2) else ""))
            out["currency"] = m.group(3)
        elif tag == "MT":
            if not re.fullmatch(r"[0-9]{1,9}", rest):
                return "MT line outside the closed shape"
            out["mt"] = int(rest)
        elif tag == "MARGIN":
            if not re.fullmatch(r"[0-9]{1,2}", rest):
                return "MARGIN line outside the closed shape"
        elif tag in ("SS", "PS"):
            if not re.fullmatch(r"[0-9a-f]{64}", rest):
                return tag + " line outside the closed shape"
            out[tag.lower()] = rest
        elif tag == "GA":
            out["ga"].add(rest)
        elif tag == "DE":
            out["de"].add(rest)
        elif tag == "A":
            m = re_pc.fullmatch(line)
            if m is not None:
                soul = m.group(1)
                if soul in out["souls"]:
                    return "duplicate per-call line for " + soul
                rin, rout = _conf_rc_rational(m.group(2)), \
                    _conf_rc_rational(m.group(4))
                mult = Fraction(1) if m.group(6) is None else \
                    _conf_rc_rational(m.group(6))
                if rin is None or rout is None or mult is None or \
                        len(m.group(3)) > 18 or len(m.group(5)) > 18:
                    return "per-call line outside the closed shape"
                out["souls"][soul] = (rin, int(m.group(3)), rout,
                                      int(m.group(5)), mult)
                continue
            m = re_tt.fullmatch(line)
            if m is not None:
                if m.group(1) != m.group(2) or m.group(1) in totals:
                    return "total line outside the closed shape"
                totals[m.group(1)] = int(m.group(3))
                continue
            m = re_t1.fullmatch(line) or re_tn.fullmatch(line)
            if m is not None:
                if sum_line is not None:
                    return "duplicate total_cost line"
                sum_line = sorted(re.findall(
                    r"cost_(" + nb + r")_total", m.group(1)
                    if m.re is re_tn else "cost_" + m.group(1) + "_total"))
                continue
            return "A: line outside the closed shapes"
        elif tag not in ("NV", "EV", "W", "D", "R", "O", "SD", "SA", "GQ"):
            return "unknown tag " + tag
    for need in ("cap", "mt", "ss", "ps"):
        if need not in out:
            return "spec canon lacks " + need.upper()
    if sorted(totals) != sorted(out["souls"]) or (
            out["souls"] and sum_line != sorted(out["souls"])):
        return "per-call, total and total_cost lines do not match"
    if any(t != out["mt"] for t in totals.values()):
        return "a total line multiplies by other than MT"
    return out


def _conf_rc_obligations(manifest, trace, canon_text):
    # The four obligations in scope, recomputed. ("refused", why) where
    # the online path raises a precondition, else
    # ("ok", {name: bool}, realized_total Fraction, [errors]).
    import hashlib
    from fractions import Fraction
    c = _conf_rc_parse_canon(canon_text)
    if isinstance(c, str):
        return ("refused", "spec canon refused: " + c)
    if not c["souls"]:
        return ("refused", "spec canon declares no costed soul")
    if not isinstance(manifest, dict) or not isinstance(trace, dict):
        return ("refused", "manifest or trace is not a JSON object")
    events = trace.get("events")
    if not isinstance(events, list):
        return ("refused", "trace has no event list")
    norm = []
    for i, ev in enumerate(events):
        if not isinstance(ev, dict):
            return ("refused", "event %d is not an object" % i)
        e = {}
        for key, dflt in (("seq", None), ("tick", None),
                          ("input_tokens", 0), ("output_tokens", 0)):
            v = ev.get(key, dflt)
            if type(v) is not int or v < 0:
                return ("refused", "event %d %s is not a non-negative "
                        "integer" % (i, key))
            e[key] = v
        for key in ("soul", "kind"):
            v = ev.get(key)
            if not isinstance(v, str) or not v:
                return ("refused", "event %d %s is not text" % (i, key))
            e[key] = v
        tc = _conf_rc_decimal(ev.get("tool_cost", "0"))
        if tc is None:
            return ("refused", "event %d tool_cost is not a decimal" % i)
        e["tool_cost"] = tc
        a = ev.get("action")
        if a is not None and not isinstance(a, str):
            return ("refused", "event %d action is not text" % i)
        e["action"] = a
        norm.append(e)
    souls, ga, de = c["souls"], c["ga"], c["de"]
    for e in norm:
        s = "event seq=%d " % e["seq"]
        if e["kind"] not in _CONF_RC_KINDS:
            return ("refused", s + "has an unknown kind")
        if e["soul"] not in souls:
            return ("refused", s + "names a soul the spec never declared")
        if e["kind"] == "tool_call" and e["tool_cost"] != 0:
            return ("refused", s + "is a priced tool_call")
        if e["kind"] == "gated_action" and e["action"] is not None and \
                e["action"] not in ga:
            return ("refused", s + "gated action is not declared")
        if e["action"] is not None and e["action"] in ga and \
                e["kind"] != "gated_action":
            return ("refused", s + "is a declared gated action recorded "
                    "under another kind")
        if e["kind"] == "tool_call" and de:
            if e["action"] is None or e["action"] not in de:
                return ("refused", s + "tool_call is outside the "
                        "declared events")
    ek = trace.get("evidence_kind")
    cb = trace.get("cost_binding")
    pti = trace.get("provider_token_integrity")
    if ek not in (None, "envelope", "witnessed_run") or cb not in (
            None, "envelope", "realized") or pti not in (
            None, "unattested", "tee_attested", "unverifiable"):
        return ("refused", "trust field outside its vocabulary")
    if sum(1 for v in (ek, cb, pti) if v is not None) not in (0, 3):
        return ("refused", "trust triple is partial (all three or none)")
    if (cb == "realized") != (ek == "witnessed_run"):
        return ("refused", "cost_binding and evidence_kind disagree")
    errors = []
    sha = hashlib.sha256(canon_text.encode("utf-8")).hexdigest()
    binding = (
        sha == manifest.get("smt_spec_sha256")
        and c["ss"] == manifest.get("source_sha256")
        and c["ps"] == manifest.get("pricing_sha256")
        and trace.get("source_sha256") == manifest.get("source_sha256")
        and trace.get("smt_spec_sha256") == manifest.get("smt_spec_sha256")
        and trace.get("pricing_sha256") == manifest.get("pricing_sha256")
    )
    if not binding:
        errors.append("binding: canon, manifest and trace shas disagree")
    discharge = True
    calls = {name: 0 for name in souls}
    max_tick = -1
    realized = Fraction(0)
    for e in norm:
        rin, max_in, rout, max_out, mult = souls[e["soul"]]
        max_tick = max(max_tick, e["tick"])
        if e["input_tokens"] > max_in or e["output_tokens"] > max_out:
            discharge = False
            errors.append("discharge: seq=%d tokens over the declared "
                          "bound" % e["seq"])
        if e["kind"] == "llm_call":
            calls[e["soul"]] += 1
            realized += (rin * e["input_tokens"]
                         + rout * e["output_tokens"] * mult) / 1000000
    for name, n in sorted(calls.items()):
        if n > c["mt"]:
            discharge = False
            errors.append("discharge: soul %s made %d llm_calls > %d"
                          % (name, n, c["mt"]))
    if max_tick >= c["mt"]:
        discharge = False
        errors.append("discharge: max tick %d >= %d" % (max_tick, c["mt"]))
    bound = realized <= c["cap"]
    if not bound:
        errors.append("bound_transfer: realized_total %s > cost_cap %s"
                      % (_conf_rc_text(realized), _conf_rc_text(c["cap"])))
    return ("ok", {"binding_ok": binding, "surface_ok": True,
                   "assumption_discharge_ok": discharge,
                   "bound_transfer_ok": bound}, realized, errors)


def _conf_recompute(manifest, cert, trace, canon_text):
    # ("absent", {}) without a canon; ("refused", {"reason"}); or
    # ("recomputed", {"line", "disagree", ...}). Reads no recorded
    # boolean to decide an obligation; compares them after.
    if canon_text is None:
        return ("absent", {})
    if not isinstance(cert, dict):
        return ("refused", {"reason": "certificate is not a JSON object"})
    r = _conf_rc_obligations(manifest, trace, canon_text)
    if r[0] == "refused":
        return ("refused", {"reason": r[1]})
    _ok, ob, realized, errors = r
    cap = _conf_rc_parse_canon(canon_text)["cap"]
    disagree = []
    for name in _CONF_RC_SCOPE:
        if name in cert and bool(cert[name]) != ob[name]:
            disagree.append(
                "certificate records %s=%s but recomputed from trace.json "
                "and the spec canon it is %s (recorded verdict disagrees "
                "with recomputation)" % (name, bool(cert[name]), ob[name]))
    rec = _conf_rc_decimal(cert.get("realized_total"))
    if rec != realized:
        disagree.append(
            "certificate records realized_total=%s but recomputed from "
            "trace.json and the spec canon it is %s (recorded verdict "
            "disagrees with recomputation)"
            % (cert.get("realized_total"), _conf_rc_text(realized)))
    line = (
        "RECOMPUTED (cost obligations, D6 (i)) from trace.json and the "
        "certificate's spec canon, equal to the recorded booleans: "
        + ", ".join("%s=%s" % (n, ob[n]) for n in _CONF_RC_SCOPE)
        + "; realized_total %s, cost_cap %s"
        % (_conf_rc_text(realized), _conf_rc_text(cap)))
    return ("recomputed", {"line": line, "disagree": disagree,
                           "obligations": ob, "realized_total": realized,
                           "errors": errors})
# --- end conformance recompute embed ---
