#!/usr/bin/env python3
"""SPEC 9 checkpoint cadence: the Producer obligation, locked.

trace/SPEC.md 9 requires a checkpoint Event when any of: N Events since the
last checkpoint (N configurable <= 256); 300 s elapsed with >=1 new Event;
run_end; graceful shutdown. Two of the four were never implemented, so a run
produced exactly ONE checkpoint unless the caller asked for more. That left
the 10.3 lower bound unchecked for the whole run and made 10.2 retro-anchoring
structurally unreachable.

Nothing in the suite exercised the cadence, because no fixture builds more
than nine Events -- which is precisely why the gap survived. These tests are
the mechanism that keeps the obligation implemented.

Anchoring is the default rfc3161-sim throughout: local Ed25519, no network.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

trace_bridge = pytest.importorskip("trace_bridge")
TraceBridge = trace_bridge.TraceBridge
TraceBridgeError = trace_bridge.TraceBridgeError

_VERIFIER = _REPO / "trace" / "reference" / "verifier.py"

_OBLS = [{"label": "x",
          "predicate": {"op": "<=", "left": {"var": "a"}, "right": {"int": 1}},
          "variables": [{"name": "a", "type": "int"}],
          "assurance": "declared",
          "proof_artifact": None,
          "dossier_ref": None}]


def _build(root: Path, n_events: int, every: int):
    pack = root / "pack"
    keys = root / "keys"
    with TraceBridge(str(pack), "s257-cadence", _OBLS, str(keys),
                     checkpoint_every_events=every) as tb:
        for i in range(n_events):
            tb.tool_call("t%d" % i, "test/1")
    lines = (pack / "trace.ndjson").read_text(encoding="utf-8").splitlines()
    return pack, [json.loads(ln) for ln in lines if ln.strip()]


def _checkpoints(events):
    return [e for e in events if e["event_type"] == "checkpoint"]


def test_event_count_leg_fires(tmp_path):
    _pack, events = _build(tmp_path, 20, 4)
    cks = _checkpoints(events)
    assert len(cks) > 1, (
        "SPEC 9 event-count leg did not fire: %d checkpoint(s) across %d "
        "Events at every=4" % (len(cks), len(events)))


def test_cadence_is_configurable(tmp_path):
    _p1, tight = _build(tmp_path / "a", 20, 4)
    _p2, loose = _build(tmp_path / "b", 20, 256)
    assert len(_checkpoints(tight)) > len(_checkpoints(loose))
    assert len(_checkpoints(loose)) == 1, (
        "at every=256 only finalize() should checkpoint")


def test_e1_contiguity_holds_across_auto_checkpoints(tmp_path):
    _pack, events = _build(tmp_path, 20, 4)
    cks = _checkpoints(events)
    assert len(cks) > 1
    assert cks[0]["body"]["range"]["from_seq"] == 0
    for prev, cur in zip(cks, cks[1:]):
        assert cur["body"]["range"]["from_seq"] == prev["seq"], (
            "E1 violated: from_seq %d != preceding checkpoint seq %d"
            % (cur["body"]["range"]["from_seq"], prev["seq"]))


def test_auto_checkpointed_pack_verifies(tmp_path):
    pack, events = _build(tmp_path, 20, 4)
    assert len(_checkpoints(events)) > 1
    p = subprocess.run([sys.executable, str(_VERIFIER), str(pack)],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert json.loads(p.stdout)["verdict"] == "VALID"


def test_checkpoint_event_does_not_recurse(tmp_path):
    _pack, events = _build(tmp_path, 12, 1)
    seqs = [e["seq"] for e in events]
    assert seqs == sorted(seqs)
    assert len(seqs) == len(set(seqs))
    for prev, cur in zip(events, events[1:]):
        assert not (prev["event_type"] == "checkpoint"
                    and cur["event_type"] == "checkpoint"), (
            "consecutive checkpoints at seq %d/%d: the reentrancy guard or "
            "the checkpoint-type exclusion regressed"
            % (prev["seq"], cur["seq"]))


def test_out_of_range_cadence_refused(tmp_path):
    for bad in (0, 257, -1, "64", 3.0):
        with pytest.raises(TraceBridgeError):
            TraceBridge(str(tmp_path / "p"), "s257", _OBLS,
                        str(tmp_path / "k"), checkpoint_every_events=bad)
