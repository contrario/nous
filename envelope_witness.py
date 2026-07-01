"""nous envelope witness quorum: k-of-n non-equivocation over the envelope checkpoint.

S194 Inc B1 of the envelope arc. __s194_envelope_witness_module_v1__

Composes the shipped C2SP 0x04 tlog-cosignature verifier
(continuity_cosign.count_verified_cosignatures) over the standalone envelope
checkpoint note produced by envelope_ledger.build_envelope_checkpoint. It counts
how many of n pinned, independent witnesses cosigned exactly this checkpoint
head, and reports whether a threshold k of DISTINCT witnesses is met.

This is a COMPOSITION of existing primitives, not a new cryptographic build. The
0x04 cosignature machinery is shipped (S179) and the checkpoint substrate is
shipped (S193 Inc A). What is new is pointing a witness quorum at a per-operator
predetermined-change envelope log.

Honest boundary (inviolable, carried from the arc):
  - a verified quorum EVIDENCES that k distinct, named, pinned witnesses each
    observed and cosigned exactly this envelope checkpoint head (origin, size,
    root) at a stated time. It PROVES nothing; the only PROVES legs remain Z3
    cost bounds and Farkas. Monitor, not guard: under-quorum is a legitimate
    verdict, not an enforcement action; only a malformed envelope fails closed.
  - the cross-epoch non-equivocation property (a witness will not cosign two
    inconsistent heads) is delivered by each witness's OWN append-only
    consistency check at cosign time, which this auditor-side counter does not
    and need not perform. This module counts attestations; it TRUSTS that each
    witness verified consistency before cosigning, which is what a C2SP
    cosignature means. Non-equivocation therefore rests on a NAMED TRUST
    ASSUMPTION: the property holds unless k of the n pinned witnesses collude
    with the operator.
  - name-to-key binding is OPERATOR-ASSERTED. NOUS runs no CA and certifies no
    identity; a cosignature evidences only that the holder of a pinned key
    signed. Confirming each witness's identity is the auditor's out-of-band step.
  - enumeration is bounded to envelopes committed THROUGH NOUS for this epoch;
    off-log pre-commitment through another channel is out of scope and is not
    defeated.

Provisioning is deliberately out of this module. It verifies against whatever
(name, public key) pins the auditor supplies; whether those witnesses are a
public network or named ecosystem governance peers is a pinning decision, not a
code decision. The pins are the trust root; this module asserts no operating
quorum of its own.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from continuity_cosign import count_verified_cosignatures


class EnvelopeWitnessError(RuntimeError):
    """Raised cause-first for a malformed quorum CONFIGURATION: a non-integer or
    non-positive threshold, a threshold exceeding the number of pins, an empty
    pin set, or a duplicate cosigner name across pins (which would make
    distinct-witness counting ambiguous). A malformed checkpoint envelope is NOT
    reported here; it fails closed via the composed parser's own typed error."""


@dataclass(frozen=True)
class WitnessPin:
    """An operator-asserted (cosigner name, Ed25519 public key) binding for one
    independent witness. The name is pinned because the C2SP 0x04 signed message
    does not bind it; the auditor must supply the expected name and key."""

    name: str
    public_key: Ed25519PublicKey


@dataclass(frozen=True)
class QuorumResult:
    """The verdict of a k-of-n witness-quorum check over one envelope
    checkpoint. `met` is the monitor verdict: it is False (never an exception)
    when the envelope is well-formed but fewer than `threshold` distinct
    witnesses cosigned."""

    threshold: int
    pin_count: int
    verified_count: int
    verified_names: tuple[str, ...]
    met: bool


def _validate_pins(pins: Sequence[WitnessPin], threshold: int) -> None:
    if not isinstance(threshold, int) or isinstance(threshold, bool):
        raise EnvelopeWitnessError(
            "threshold must be an int (got " + repr(threshold) + ")"
        )
    if threshold < 1:
        raise EnvelopeWitnessError(
            "threshold must be >= 1 (got " + str(threshold) + ")"
        )
    if not pins:
        raise EnvelopeWitnessError("pin set is empty: no witnesses to count")
    seen: set[str] = set()
    for pin in pins:
        if pin.name in seen:
            raise EnvelopeWitnessError(
                "duplicate cosigner name across pins makes distinct-witness "
                "counting ambiguous: " + repr(pin.name)
            )
        seen.add(pin.name)
    if threshold > len(pins):
        raise EnvelopeWitnessError(
            "threshold " + str(threshold) + " exceeds the number of pinned "
            "witnesses " + str(len(pins)) + "; the quorum can never be met"
        )


def count_quorum_witnesses(
    envelope: str, pins: Sequence[WitnessPin]
) -> tuple[int, tuple[str, ...]]:
    """Count how many DISTINCT pinned witnesses have at least one verifying
    0x04 cosignature over `envelope`, returning (count, sorted verified names).

    Composes continuity_cosign.count_verified_cosignatures once per pin. A
    malformed envelope raises (fails closed) from the composed parser; this
    function adds no verdict of its own for that case."""
    verified: list[str] = []
    for pin in pins:
        if count_verified_cosignatures(
            envelope, pin.name, pin.public_key
        ) >= 1:
            verified.append(pin.name)
    return len(verified), tuple(sorted(verified))


def verify_envelope_quorum(
    envelope: str, pins: Sequence[WitnessPin], threshold: int
) -> QuorumResult:
    """Verify a k-of-n witness quorum over one envelope checkpoint.

    Monitor semantics: a well-formed envelope with fewer than `threshold`
    distinct verifying witnesses returns a QuorumResult with met=False and does
    NOT raise. A malformed CONFIGURATION raises EnvelopeWitnessError cause-first;
    a malformed ENVELOPE fails closed via the composed parser's typed error."""
    _validate_pins(pins, threshold)
    count, names = count_quorum_witnesses(envelope, pins)
    return QuorumResult(
        threshold=threshold,
        pin_count=len(pins),
        verified_count=count,
        verified_names=names,
        met=count >= threshold,
    )
