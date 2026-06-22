from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

import rekor_v2_offline as rv

_FIXTURES = Path(__file__).parent / "fixtures" / "rekor_v2"


def _load_bundle() -> dict:
    return json.loads((_FIXTURES / "bundle.json").read_text())


def test_module_selftest_legs_1_and_2() -> None:
    assert rv._selftest() == 0


def test_verify_entry_real_bundle_three_legs() -> None:
    bundle = _load_bundle()
    pins = rv.load_pins(_FIXTURES)
    verdict = rv.verify_entry(bundle, pins, verify_time=True)
    assert verdict.included is True
    assert verdict.checkpoint_ok is True
    assert verdict.log_index == 5272998
    assert verdict.tree_size == 5272999
    assert (
        verdict.leaf_hash_hex
        == "17e07e828041c0240b0c0d4e754f531db64795973d1d314eeee8cfd0aab0638e"
    )
    assert verdict.timestamp is not None
    assert verdict.timestamp.isoformat() == "2026-06-22T10:02:24+00:00"


def test_tampered_tree_size_refused() -> None:
    bundle = _load_bundle()
    pins = rv.load_pins(_FIXTURES)
    bundle["transparency_log_entry"]["inclusion_proof"]["tree_size"] = 9999999
    with pytest.raises(rv.VerificationError):
        rv.verify_entry(bundle, pins, verify_time=True)


def test_tampered_canonicalized_body_refused() -> None:
    bundle = _load_bundle()
    pins = rv.load_pins(_FIXTURES)
    bundle["transparency_log_entry"]["canonicalized_body"] = base64.b64encode(
        b"tampered"
    ).decode("ascii")
    with pytest.raises(rv.VerificationError):
        rv.verify_entry(bundle, pins, verify_time=True)
