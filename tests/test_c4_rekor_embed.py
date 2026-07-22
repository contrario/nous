"""C4: the dossier's EMBEDDED bundle verifier accepts Rekor v2 anchors.

__nous_rekor_tb_tests_v1__

The asymmetry this closes: P1 taught the Producer to emit `rekor` anchors,
but tb_check.py -- the verifier that ships inside every emitted
verify_offline.py and travels to the auditor -- terminated its anchor
dispatch with ANCHOR_TYPE. A dossier carrying a rekor-anchored trace bundle
was therefore rejected by this project's own offline verifier. No existing
artifact was affected (the default backend is rfc3161-sim and no dossier path
selected rekor), but Producer and Consumer disagreed about the format, which
is the same defect family as a claim with no mechanism behind it.

The synthetic-log helpers are imported from test_c4_rekor_verify.py by path
rather than retyped, so the two suites cannot drift apart in what they
consider a well-formed leaf, checkpoint and inclusion proof.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

pytest.importorskip("trace_bridge")

import dossier
import tb_check

_SOURCE_PATH = _REPO / "rekor_check.py"
_TB_PATH = _REPO / "tb_check.py"
_BEGIN = "# __rk_tb_splice_begin_v1__\n"
_END = "# __rk_tb_splice_end_v1__\n"


def _helpers():
    path = Path(__file__).parent / "test_c4_rekor_verify.py"
    spec = importlib.util.spec_from_file_location("_c4_helpers", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _MP:
    """Minimal monkeypatch stand-in for the borrowed _pack helper."""

    def __init__(self):
        self._undo = []

    def delenv(self, name, raising=True):
        import os
        if name in os.environ:
            value = os.environ.pop(name)
            self._undo.append(lambda: os.environ.__setitem__(name, value))

    def setattr(self, target, name, value):
        old = getattr(target, name)
        setattr(target, name, value)
        self._undo.append(lambda: setattr(target, name, old))

    def undo(self):
        for fn in reversed(self._undo):
            fn()
        self._undo = []


def _bundle(tmp_path, timed):
    helpers = _helpers()
    mp = _MP()
    try:
        return helpers._pack(tmp_path, mp, timed=timed)
    finally:
        mp.undo()


@pytest.mark.offline
def test_tb_splice_matches_the_tracked_source():
    text = _TB_PATH.read_text(encoding="utf-8")
    assert text.count(_BEGIN) == 1
    assert text.count(_END) == 1
    spliced = text.split(_BEGIN, 1)[1].split(_END, 1)[0]
    assert spliced == _SOURCE_PATH.read_text(encoding="utf-8"), (
        "tb_check.py has DRIFTED from the tracked source rekor_check.py; "
        "edit rekor_check.py and re-splice, never edit the copy in place")


@pytest.mark.offline
def test_embed_carries_the_rekor_leg():
    embed = dossier._TRACE_BUNDLE_CHECK_EMBED
    assert _BEGIN in embed, (
        "dossier._TRACE_BUNDLE_CHECK_EMBED does not carry the rekor leg; "
        "re-sync it from tb_check.py")
    assert embed == _TB_PATH.read_text(encoding="utf-8")


@pytest.mark.offline
def test_rekor_no_longer_raises_anchor_type(tmp_path):
    pack = _bundle(tmp_path, timed=False)
    try:
        tb_check._tb_verify_pack(str(pack))
    except tb_check._TbVErr as exc:
        assert exc.reason != "ANCHOR_TYPE", (
            "the embedded verifier still refuses the rekor anchor type")
        raise


@pytest.mark.offline
def test_untimed_bundle_is_incomplete_and_names_the_gap(tmp_path):
    pack = _bundle(tmp_path, timed=False)
    code, report = tb_check._tb_verify_pack(str(pack))
    assert code == 10, (code, report["verdict"])
    assert report["verdict"] == "INTEGRITY-OK/INCOMPLETE"
    entries = [a for a in report["anchors"] if a["type"] == "rekor"]
    assert entries and all(a["state"] == "INCLUDED-UNTIMED" for a in entries)
    assert all("gen_time" not in a for a in entries)
    assert any("INCLUDED-UNTIMED" in f for f in report["flags"])


@pytest.mark.offline
def test_timed_bundle_is_valid(tmp_path, monkeypatch):
    import datetime

    def _ok(_token, _data):
        return True, datetime.datetime.now(datetime.timezone.utc), []

    pack = _bundle(tmp_path, timed=True)
    monkeypatch.setattr(tb_check, "_tbrv_verify_rfc3161", _ok)
    code, report = tb_check._tb_verify_pack(str(pack))
    assert code == 0, (code, report)
    assert report["verdict"] == "VALID"
    entries = [a for a in report["anchors"] if a["type"] == "rekor"]
    assert entries and all(a["state"] == "INCLUDED-TIMED" for a in entries)
    assert all(a["gen_time"] for a in entries)


@pytest.mark.offline
def test_embedded_verifier_asserts_no_cause(tmp_path):
    pack = _bundle(tmp_path, timed=False)
    _, report = tb_check._tb_verify_pack(str(pack))
    blob = json.dumps(report).lower()
    for forbidden in ("unavailable", "outage", "was down", "tsa failed"):
        assert forbidden not in blob, forbidden


@pytest.mark.offline
def test_rfc3161_parity_set_is_still_three_legs():
    # rekor_check.py deliberately carries NO RFC 3161 implementation: it takes
    # the host's verifier as a callable. If that ever changes, the parity test
    # silently stops covering a fourth copy.
    assert "return ok, gen_time, errors" not in _SOURCE_PATH.read_text(
        encoding="utf-8"), (
        "rekor_check.py now contains an RFC 3161 verifier of its own; the "
        "three-copy parity set no longer covers every copy")
