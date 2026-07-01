"""Tests for envelope_witness (S194 Inc B1): the k-of-n witness quorum over the
standalone envelope checkpoint. Exercises the composition against the LIVE
continuity_cosign 0x04 machinery and the live envelope_ledger checkpoint, so a
pass here also proves the envelope_note round-trips through the shipped
rekor_checkpoint.parse_checkpoint that count_verified_cosignatures relies on."""
from __future__ import annotations

import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from continuity_cosign import build_cosignature_line
from envelope_ledger import EnvelopeLog, build_envelope_checkpoint
from envelope_witness import (
    EnvelopeWitnessError,
    QuorumResult,
    WitnessPin,
    count_quorum_witnesses,
    verify_envelope_quorum,
)

_TS = 1_900_000_000


def _log(n: int) -> EnvelopeLog:
    log = EnvelopeLog()
    for i in range(n):
        log.append(hashlib.sha256(b"commitment-" + str(i).encode()).digest())
    return log


def _checkpoint(n: int) -> dict:
    log_key = Ed25519PrivateKey.generate()
    return build_envelope_checkpoint(_log(n), log_key)


def _cosign(cp: dict, name: str, sk: Ed25519PrivateKey, ts: int = _TS) -> str:
    return build_cosignature_line(cp["note_text_bytes"], name, sk, ts)


def _envelope_with(
    cp: dict, cosigners: list[tuple[str, Ed25519PrivateKey]], ts: int = _TS
) -> str:
    env = cp["envelope_note"]
    for name, sk in cosigners:
        env = env + _cosign(cp, name, sk, ts) + "\n"
    return env


def test_quorum_met_when_k_cosign() -> None:
    cp = _checkpoint(4)
    ws = [("w" + str(i), Ed25519PrivateKey.generate()) for i in range(4)]
    env = _envelope_with(cp, ws[:3])
    pins = [WitnessPin(n, sk.public_key()) for n, sk in ws]
    res = verify_envelope_quorum(env, pins, 3)
    assert isinstance(res, QuorumResult)
    assert res.met is True
    assert res.verified_count == 3
    assert res.verified_names == ("w0", "w1", "w2")
    assert res.pin_count == 4


def test_under_quorum_is_verdict_not_exception() -> None:
    cp = _checkpoint(3)
    ws = [("w" + str(i), Ed25519PrivateKey.generate()) for i in range(4)]
    env = _envelope_with(cp, ws[:2])
    pins = [WitnessPin(n, sk.public_key()) for n, sk in ws]
    res = verify_envelope_quorum(env, pins, 3)
    assert res.met is False
    assert res.verified_count == 2


def test_wrong_key_under_pinned_name_not_counted() -> None:
    cp = _checkpoint(3)
    foreign = Ed25519PrivateKey.generate()
    env = _envelope_with(cp, [("w0", foreign)])
    honest_pk = Ed25519PrivateKey.generate().public_key()
    pins = [WitnessPin("w0", honest_pk)]
    res = verify_envelope_quorum(env, pins, 1)
    assert res.met is False
    assert res.verified_count == 0


def test_foreign_line_ignored_not_fatal() -> None:
    cp = _checkpoint(3)
    ws = [("w" + str(i), Ed25519PrivateKey.generate()) for i in range(2)]
    stranger = Ed25519PrivateKey.generate()
    env = _envelope_with(cp, ws + [("stranger", stranger)])
    pins = [WitnessPin(n, sk.public_key()) for n, sk in ws]
    count, names = count_quorum_witnesses(env, pins)
    assert count == 2
    assert names == ("w0", "w1")


def test_operator_log_line_ignored() -> None:
    cp = _checkpoint(3)
    ws = [("w" + str(i), Ed25519PrivateKey.generate()) for i in range(2)]
    env = _envelope_with(cp, ws)
    pins = [WitnessPin(n, sk.public_key()) for n, sk in ws]
    res = verify_envelope_quorum(env, pins, 2)
    assert res.met is True
    assert res.verified_count == 2


def test_duplicate_pin_name_raises() -> None:
    cp = _checkpoint(3)
    pk = Ed25519PrivateKey.generate().public_key()
    pins = [WitnessPin("w0", pk), WitnessPin("w0", pk)]
    with pytest.raises(EnvelopeWitnessError):
        verify_envelope_quorum(cp["envelope_note"], pins, 1)


def test_threshold_below_one_raises() -> None:
    cp = _checkpoint(3)
    pins = [WitnessPin("w0", Ed25519PrivateKey.generate().public_key())]
    with pytest.raises(EnvelopeWitnessError):
        verify_envelope_quorum(cp["envelope_note"], pins, 0)


def test_threshold_exceeds_pins_raises() -> None:
    cp = _checkpoint(3)
    pins = [WitnessPin("w0", Ed25519PrivateKey.generate().public_key())]
    with pytest.raises(EnvelopeWitnessError):
        verify_envelope_quorum(cp["envelope_note"], pins, 2)


def test_empty_pins_raises() -> None:
    cp = _checkpoint(3)
    with pytest.raises(EnvelopeWitnessError):
        verify_envelope_quorum(cp["envelope_note"], [], 1)


def test_malformed_envelope_fails_closed() -> None:
    pins = [WitnessPin("w0", Ed25519PrivateKey.generate().public_key())]
    with pytest.raises(Exception):
        verify_envelope_quorum("not a checkpoint envelope", pins, 1)
