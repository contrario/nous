"""NOUS runtime trace recorder (producer).

Standalone producer that assembles a byte-deterministic, optionally
Ed25519-signed TraceEnvelope while a NOUS world runs. The recorder owns
NO schema of its own: it fills the existing nous_trace.TraceEnvelope /
TraceEvent models. The conformance verifier (conformance.py) remains the
sole consumer of the resulting envelope.

Design (Phase 0, S103):
  - Subject binding. source_sha256 / smt_spec_sha256 / pricing_sha256
    are fixed at construction and never mutate. They bind the trace to a
    specific source, cost model, and constraint system, exactly as the
    dossier manifest does (in-toto / SLSA subject-binding pattern: the
    signature covers every field except the signature itself, and the
    digests pin the artifact the evidence is about). Each must be a
    64-hex-char SHA-256; anything else is REFUSED at construction.
  - Producer only. The recorder appends TraceEvent rows under the four
    known kinds (llm_call, tool_call, message, gated_action) and seals
    them into a TraceEnvelope on finalize(). It introduces no new
    envelope format; nous_trace owns canonical bytes + sign/verify.
  - action is left None at this layer. Sequence labels ride the existing
    optional TraceEvent.action field and are bound by a later stage; the
    recorder accepts an explicit action only when a caller already holds
    a validated label, and never invents one.
  - Refuse over guess. Recording after finalize, or an unknown kind,
    raises a typed TraceRecorderError whose message starts with the
    cause. No silent fallbacks.
  - Deterministic clock. The timestamp source is injectable so tests
    produce byte-identical envelopes; production passes a UTC clock.

# __nous_trace_recorder_module_v1__
"""
from __future__ import annotations

from typing import Callable, Optional

from nous_trace import (
    AuthorizationAttestation,
    MemoryConsultation,
    TraceEnvelope,
    TraceEvent,
    sign_trace,
)

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
except Exception:  # pragma: no cover - cryptography is a hard dep at runtime
    Ed25519PrivateKey = None  # type: ignore[assignment, misc]

_KNOWN_KINDS: frozenset[str] = frozenset(
    {"llm_call", "tool_call", "message", "gated_action"}
)

_HEX_DIGITS: frozenset[str] = frozenset("0123456789abcdef")


class TraceRecorderError(Exception):
    """Raised when the recorder is used outside its contract."""


def _require_sha256(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TraceRecorderError(
            f"{field_name} must be a 64-hex-char SHA-256 string, "
            f"got {type(value).__name__}"
        )
    if len(value) != 64 or any(c not in _HEX_DIGITS for c in value):
        raise TraceRecorderError(
            f"{field_name} is not a 64-hex-char SHA-256 string "
            f"(len={len(value)}); the recorder refuses an ill-formed "
            f"subject binding"
        )
    return value


class TraceRecorder:
    """Assemble a TraceEnvelope for a single NOUS world run.

    Construction fixes the immutable subject binding (the three SHA-256
    digests) and run identity (nous_version, world_name). Each record_*
    call appends one TraceEvent under a known kind, auto-incrementing the
    global seq counter. finalize() seals the events into a TraceEnvelope,
    optionally Ed25519-signed, after which the recorder is closed.
    """

    def __init__(
        self,
        nous_version: str,
        world_name: str,
        source_sha256: str,
        smt_spec_sha256: str,
        pricing_sha256: str,
        clock: Optional[Callable[[], str]] = None,
    ) -> None:
        if not isinstance(nous_version, str) or not nous_version:
            raise TraceRecorderError(
                "nous_version must be a non-empty string"
            )
        if not isinstance(world_name, str) or not world_name:
            raise TraceRecorderError(
                "world_name must be a non-empty string"
            )
        self._nous_version: str = nous_version
        self._world_name: str = world_name
        self._source_sha256: str = _require_sha256(
            source_sha256, "source_sha256"
        )
        self._smt_spec_sha256: str = _require_sha256(
            smt_spec_sha256, "smt_spec_sha256"
        )
        self._pricing_sha256: str = _require_sha256(
            pricing_sha256, "pricing_sha256"
        )
        self._clock: Callable[[], str] = (
            clock if clock is not None else _default_clock
        )
        self._events: list[TraceEvent] = []
        self._seq: int = 0
        self._finalized: bool = False
        self._memory_consultation: Optional[MemoryConsultation] = None  # __s107_u3_consult_state_v1__

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def finalized(self) -> bool:
        return self._finalized

    def _append(
        self,
        kind: str,
        tick: int,
        soul: str,
        input_tokens: int,
        output_tokens: int,
        tool_cost: str,
        action: Optional[str],
        authorization: Optional[AuthorizationAttestation],
    ) -> TraceEvent:
        if self._finalized:
            raise TraceRecorderError(
                "recorder is finalized; cannot record further events"
            )
        if kind not in _KNOWN_KINDS:
            raise TraceRecorderError(
                f"kind {kind!r} is not a known trace kind "
                f"{sorted(_KNOWN_KINDS)}; the recorder refuses to emit "
                f"an unrecognised event kind"
            )
        if not isinstance(soul, str) or not soul:
            raise TraceRecorderError(
                "soul must be a non-empty string"
            )
        event = TraceEvent(
            seq=self._seq,
            tick=tick,
            soul=soul,
            kind=kind,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tool_cost=tool_cost,
            action=action,
            authorization=authorization,
            timestamp_utc=self._clock(),
        )
        self._events.append(event)
        self._seq += 1
        return event

    def record_llm_call(
        self,
        soul: str,
        tick: int,
        input_tokens: int,
        output_tokens: int,
        action: Optional[str] = None,
    ) -> TraceEvent:
        return self._append(
            kind="llm_call",
            tick=tick,
            soul=soul,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tool_cost="0",
            action=action,
            authorization=None,
        )

    def record_tool_call(
        self,
        soul: str,
        tick: int,
        tool_cost: str = "0",
        action: Optional[str] = None,
    ) -> TraceEvent:
        return self._append(
            kind="tool_call",
            tick=tick,
            soul=soul,
            input_tokens=0,
            output_tokens=0,
            tool_cost=tool_cost,
            action=action,
            authorization=None,
        )

    def record_message(
        self,
        soul: str,
        tick: int,
        action: Optional[str] = None,
    ) -> TraceEvent:
        return self._append(
            kind="message",
            tick=tick,
            soul=soul,
            input_tokens=0,
            output_tokens=0,
            tool_cost="0",
            action=action,
            authorization=None,
        )

    def record_gated_action(
        self,
        soul: str,
        tick: int,
        action: str,
        authorization: Optional[AuthorizationAttestation] = None,
    ) -> TraceEvent:
        if not isinstance(action, str) or not action:
            raise TraceRecorderError(
                "gated_action requires a non-empty action label"
            )
        return self._append(
            kind="gated_action",
            tick=tick,
            soul=soul,
            input_tokens=0,
            output_tokens=0,
            tool_cost="0",
            action=action,
            authorization=authorization,
        )

    def set_memory_consultation(
        self,
        *,
        consultation: MemoryConsultation,
    ) -> None:  # __s107_u3_set_consult_v1__
        if self._finalized:
            raise TraceRecorderError(
                "cannot set memory consultation after finalize()"
            )
        if not isinstance(consultation, MemoryConsultation):
            raise TraceRecorderError(
                "consultation must be a MemoryConsultation instance"
            )
        if self._memory_consultation is not None:
            raise TraceRecorderError(
                "memory consultation already set; refusing to overwrite "
                "a recorded run input"
            )
        self._memory_consultation = consultation

    def _build_envelope(self) -> TraceEnvelope:
        return TraceEnvelope(
            nous_version=self._nous_version,
            world_name=self._world_name,
            source_sha256=self._source_sha256,
            smt_spec_sha256=self._smt_spec_sha256,
            pricing_sha256=self._pricing_sha256,
            events=list(self._events),
            memory_consultation=self._memory_consultation,  # __s107_u3_consult_build_v1__
            signature=None,
        )

    def finalize(
        self,
        private_key: Optional["Ed25519PrivateKey"] = None,
    ) -> TraceEnvelope:
        if self._finalized:
            raise TraceRecorderError(
                "recorder already finalized; finalize() is single-shot"
            )
        envelope = self._build_envelope()
        self._finalized = True
        if private_key is None:
            return envelope
        return sign_trace(envelope, private_key)


def _default_clock() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
