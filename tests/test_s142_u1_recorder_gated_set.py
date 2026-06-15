"""S142 U1: TraceRecorder gated-set wiring.

The recorder ctor accepts the signed gated set (SMTSpec.gated_actions,
sha-bound) so a later stage can route a gated occurrence to kind=
"gated_action" instead of "message". U1 only wires the ctor: it validates
and stores the set; routing lands in U2. Default empty -> every existing
5-positional construction is byte-for-byte unaffected.
"""
from __future__ import annotations

import pytest

from trace_recorder import TraceRecorder, TraceRecorderError

_SHA_A = "a" * 64
_SHA_B = "b" * 64
_SHA_C = "c" * 64


def _mk(gated_actions: tuple[str, ...] = ()) -> TraceRecorder:
    return TraceRecorder(
        nous_version="5.41.0",
        world_name="W",
        source_sha256=_SHA_A,
        smt_spec_sha256=_SHA_B,
        pricing_sha256=_SHA_C,
        gated_actions=gated_actions,
    )


def test_default_gated_set_is_empty() -> None:
    r = TraceRecorder("5.41.0", "W", _SHA_A, _SHA_B, _SHA_C)
    assert r._gated_actions == frozenset()


def test_explicit_gated_set_stored() -> None:
    r = _mk(("escalate", "wire_transfer"))
    assert r._gated_actions == frozenset({"escalate", "wire_transfer"})


def test_gated_set_dedup_and_order_insensitive() -> None:
    r = _mk(("escalate", "escalate", "approve"))
    assert r._gated_actions == frozenset({"escalate", "approve"})


def test_rejects_non_str_entry() -> None:
    with pytest.raises(TraceRecorderError) as exc:
        _mk(("escalate", 123))  # type: ignore[arg-type]
    assert "non-empty strings" in str(exc.value)


def test_rejects_empty_str_entry() -> None:
    with pytest.raises(TraceRecorderError) as exc:
        _mk(("escalate", ""))
    assert "non-empty strings" in str(exc.value)


def test_positional_legacy_construction_unaffected() -> None:
    r = TraceRecorder("5.41.0", "W", _SHA_A, _SHA_B, _SHA_C)
    assert r.event_count == 0
    assert r._gated_actions == frozenset()
