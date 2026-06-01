"""Tests for run_identity -- Memory Phase 1 U1 (S107).

Pins the NAME-BOUND derivation from docs/MEMORY_PHASE1_DESIGN.md Section 3 with
known-answer digests and the structural properties the design relies on:
determinism, 64-hex lowercase form, world/soul domain separation, soul scoping
within a world, and fail-closed refusal on empty/non-string names.

# __s107_run_identity_tests_v1__
"""
from __future__ import annotations

import re

import pytest

from run_identity import (
    RunIdentityError,
    producing_soul_sha256,
    world_sha256,
)

_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")

_WORLD_TRADER = "e69838816917946bdb4b7db4f6e9d117a933a94eae11ebf43361ad2903bd4561"
_SOUL_TRADER_ALPHA = "ab1f419f1046258f32a295ef103672ea022998342c283ec38e5572b4b6f4491c"
_SOUL_TRADER_TRADER = "dc75f1d8a70b5f1faf7b8d64c2ee1bf499fd8db34cf8fee8621daa783980fca8"


def test_world_known_answer() -> None:
    assert world_sha256("Trader") == _WORLD_TRADER


def test_soul_known_answer() -> None:
    assert producing_soul_sha256("Trader", "alpha") == _SOUL_TRADER_ALPHA


def test_world_form_is_64_hex_lowercase() -> None:
    h = world_sha256("Trader")
    assert _HEX64.match(h) is not None


def test_soul_form_is_64_hex_lowercase() -> None:
    h = producing_soul_sha256("Trader", "alpha")
    assert _HEX64.match(h) is not None


def test_world_is_deterministic() -> None:
    assert world_sha256("Trader") == world_sha256("Trader")


def test_soul_is_deterministic() -> None:
    assert producing_soul_sha256("Trader", "alpha") == producing_soul_sha256(
        "Trader", "alpha"
    )


def test_world_stable_across_source_edits() -> None:
    assert world_sha256("Trader") == _WORLD_TRADER


def test_world_and_soul_labels_do_not_collide() -> None:
    assert world_sha256("Trader") != producing_soul_sha256("Trader", "Trader")
    assert producing_soul_sha256("Trader", "Trader") == _SOUL_TRADER_TRADER


def test_soul_scoped_within_world() -> None:
    a = producing_soul_sha256("Trader", "alpha")
    b = producing_soul_sha256("Risk", "alpha")
    assert a != b


def test_distinct_souls_differ() -> None:
    a = producing_soul_sha256("Trader", "alpha")
    b = producing_soul_sha256("Trader", "beta")
    assert a != b


def test_world_refuses_empty() -> None:
    with pytest.raises(RunIdentityError):
        world_sha256("")


def test_soul_refuses_empty_world() -> None:
    with pytest.raises(RunIdentityError):
        producing_soul_sha256("", "alpha")


def test_soul_refuses_empty_soul() -> None:
    with pytest.raises(RunIdentityError):
        producing_soul_sha256("Trader", "")


def test_world_refuses_non_string() -> None:
    with pytest.raises(RunIdentityError):
        world_sha256(None)  # type: ignore[arg-type]
