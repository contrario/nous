"""Inc C -- offline closure-witness surface.

Domain-separated closure-root -> envelope-commitment mapping (rides the shipped
envelope log), the R4 surface-split projection guard, and the total offline
verifier tying a closure root to a witnessed + optionally Rekor-anchored envelope
checkpoint. Composes over envelope_ledger, envelope_witness, rekor_v2_offline,
rekor_verify_v2 and the Inc B closure_attestation; reimplements none of them.

No signing, no network: the append, the witness cosignature, and the Rekor anchor
are deferred ceremonies. The public/witnessed surface commits only
{policy_id, interval, root}; action_count never enters the public commitment and
lives solely in the auditor-only Inc B attestation.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

import closure_attestation as ca
import envelope_ledger as el
import envelope_witness as ew
import rekor_v2_offline as rkt
import rekor_verify_v2 as rv2


CLOSURE_COMMIT_TAG = b"nous/closure-root/v1|"
CLOSURE_WITNESS_SCHEMA_VERSION = 1


class ClosureWitnessError(RuntimeError):
    pass


def _require_sha256_hex(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ClosureWitnessError(
            name + " must be a 64-char sha256 hex string, got: " + repr(value)
        )
    try:
        int(value, 16)
    except ValueError as exc:
        raise ClosureWitnessError(
            name + " is not hexadecimal: " + repr(value)
        ) from exc
    return value


def public_body(
    closure_root_hex: str,
    policy_id: str,
    interval_start: str,
    interval_end: str,
) -> bytes:
    doc = {
        "interval_end": interval_end,
        "interval_start": interval_start,
        "policy_id": policy_id,
        "root": _require_sha256_hex("closure_root", closure_root_hex),
    }
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")


def closure_commitment(
    closure_root_hex: str,
    policy_id: str,
    interval_start: str,
    interval_end: str,
) -> bytes:
    body = public_body(closure_root_hex, policy_id, interval_start, interval_end)
    return hashlib.sha256(CLOSURE_COMMIT_TAG + body).digest()


def assert_projection_consistent(
    attestation: "ca.ClosureAttestation",
    closure_root_hex: str,
    policy_id: str,
    interval_start: str,
    interval_end: str,
) -> None:
    if attestation.root != closure_root_hex:
        raise ClosureWitnessError(
            "projection root mismatch: public "
            + repr(closure_root_hex)
            + " != auditor "
            + repr(attestation.root)
        )
    if attestation.policy_id != policy_id:
        raise ClosureWitnessError(
            "projection policy_id mismatch: public "
            + repr(policy_id)
            + " != auditor "
            + repr(attestation.policy_id)
        )
    if (
        attestation.interval_start != interval_start
        or attestation.interval_end != interval_end
    ):
        raise ClosureWitnessError(
            "projection interval mismatch: public ("
            + repr(interval_start)
            + ", "
            + repr(interval_end)
            + ") != auditor ("
            + repr(attestation.interval_start)
            + ", "
            + repr(attestation.interval_end)
            + ")"
        )


@dataclass(frozen=True)
class ClosureWitnessVerdict:
    inclusion_ok: bool
    quorum_met: bool
    anchor_checked: bool
    anchor_ok: bool

    @property
    def ok(self) -> bool:
        return (
            self.inclusion_ok
            and self.quorum_met
            and (self.anchor_ok or not self.anchor_checked)
        )


def verify_closure_witnessed(
    *,
    closure_root_hex: str,
    policy_id: str,
    interval_start: str,
    interval_end: str,
    envelope_note: str,
    log_index: int,
    tree_size: int,
    inclusion_proof: Sequence[bytes],
    checkpoint_root: bytes,
    witness_pins: Sequence["ew.WitnessPin"],
    threshold: int,
    anchor_block: Optional[Mapping[str, object]] = None,
    anchored_body_bytes: Optional[bytes] = None,
    trusted_log_keys: Optional[Mapping[str, object]] = None,
) -> ClosureWitnessVerdict:
    inclusion_ok = False
    try:
        commitment = closure_commitment(
            closure_root_hex, policy_id, interval_start, interval_end
        )
        leaf_data = el.envelope_leaf_data(commitment)
        rkt.verify_inclusion(
            leaf_data,
            log_index,
            tree_size,
            list(inclusion_proof),
            checkpoint_root,
        )
        inclusion_ok = True
    except (
        ClosureWitnessError,
        rkt.VerificationError,
        el.EnvelopeLedgerError,
        ValueError,
        TypeError,
    ):
        inclusion_ok = False

    quorum_met = False
    try:
        result = ew.verify_envelope_quorum(envelope_note, witness_pins, threshold)
        quorum_met = bool(result.met)
    except Exception:
        quorum_met = False

    anchor_checked = anchor_block is not None and anchored_body_bytes is not None
    anchor_ok = False
    if anchor_checked:
        try:
            detail = rv2.verify_rekor_v2_anchor(
                manifest_body_bytes=anchored_body_bytes,
                block=anchor_block,
                trusted_log_keys=trusted_log_keys or {},
            )
            anchor_ok = bool(detail.ok)
        except rv2.RekorV2Error:
            anchor_ok = False

    return ClosureWitnessVerdict(
        inclusion_ok=inclusion_ok,
        quorum_met=quorum_met,
        anchor_checked=anchor_checked,
        anchor_ok=anchor_ok,
    )
