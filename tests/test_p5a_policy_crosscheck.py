"""P5a: the anchoring-policy cross-check (SPEC 10.1, declared vs delivered).

__nous_p5a_policy_crosscheck_tests_v1__

SPEC 10.1 declares the anchoring policy in BOTH run_start and the pack
manifest. Until P5a neither verifier read it, so a Pack whose signed run_start
declared one backend and whose checkpoints delivered another verified VALID.

Two distinct conditions, two distinct verdicts:

  manifest vs run_start disagree -> RUN_START_ANCHORING, rc 20. run_start is
      signed by the runtime key, hash-chained, and covered by the first
      checkpoint Merkle root; manifest.json is unsigned and absent from
      manifest["hashes"], so it is advisory. When the two disagree the intent
      is undeterminable and the pack is malformed -- the same treatment
      tolerance_s already had.

  declared vs delivered disagree -> flag + rc 10. The anchor verifies and the
      evidence is genuine; it is simply less than what this Producer committed
      to under its own key. Adverse, truthful, and no cause is asserted: a
      Verifier cannot tell a degraded backend from a Producer that never
      attempted the declared one.

The divergence is produced by SIGNING it, never by editing a signed block.
The anchor lives inside the checkpoint body, so a post-hoc edit is forgery and
fails SIG_INVALID long before reaching the new check.

The wrong-reason guard is load-bearing. rc 10 previously had exactly one
cause, so the structural flag was appended unconditionally. With two causes,
appending it unconditionally states a cause that did not occur.
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

import trace_bridge
from trace_bridge import TraceBridge

import tb_check

_DIVERGENCE = "anchoring policy"
_STRUCTURAL = "no run_end"


def _verifier():
    vp = _REPO / "trace" / "reference" / "verifier.py"
    spec = importlib.util.spec_from_file_location("_rv_p5a", vp)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _sim_anchor(self, root):
    # A genuine rfc3161-sim block, signed by the Producer's own anchor key,
    # emitted by a bridge that DECLARED rekor. This is the P5b degrade shape
    # reached early: the delivered evidence is real and verifies.
    gt = trace_bridge._now_ts()
    return {"type": "rfc3161-sim", "gen_time": gt,
            "token": self.anch.sign(trace_bridge.TAG_ANCH,
                                    trace_bridge._sha(root + gt.encode()))}


def _pack(tmp_path, name, anchoring=None):
    pack = tmp_path / name
    kwargs = {} if anchoring is None else {"anchoring": anchoring}
    with TraceBridge(str(pack), "actor", [], str(tmp_path / ("k_" + name)),
                     **kwargs) as br:
        br.tool_call("t", "ad", input_bytes=b"{}")
    return pack


def _shortfall_pack(tmp_path, monkeypatch):
    monkeypatch.delenv("NOUS_TSA_ROOTS", raising=False)
    monkeypatch.delenv("NOUS_REKOR_LOG_KEYS", raising=False)
    monkeypatch.setattr(TraceBridge, "_make_anchor", _sim_anchor)
    return _pack(tmp_path, "short", anchoring="rekor")


@pytest.mark.offline
def test_declared_matches_delivered_is_clean(tmp_path, monkeypatch):
    monkeypatch.delenv("NOUS_TSA_ROOTS", raising=False)
    pack = _pack(tmp_path, "agree")
    code, report = _verifier().verify_pack(str(pack))
    assert code == 0
    assert report["verdict"] == "VALID"
    assert not [f for f in report["flags"] if _DIVERGENCE in f]


@pytest.mark.offline
def test_declared_rekor_delivered_sim_is_a_shortfall(tmp_path, monkeypatch):
    pack = _shortfall_pack(tmp_path, monkeypatch)
    man = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    assert man["anchoring"] == "rekor"
    code, report = _verifier().verify_pack(str(pack))
    assert code == 10
    assert report["verdict"] == "INTEGRITY-OK/INCOMPLETE"
    div = [f for f in report["flags"] if _DIVERGENCE in f]
    assert len(div) == 1, report["flags"]
    assert "delivered less than it committed" in div[0]


@pytest.mark.offline
def test_shortfall_does_not_claim_a_structural_gap(tmp_path, monkeypatch):
    # The run DID terminate in run_end + a final anchored checkpoint. If the
    # structural flag appears, the Verifier is asserting a cause that did not
    # occur -- the exact defect the flag guard was added to prevent.
    pack = _shortfall_pack(tmp_path, monkeypatch)
    code, report = _verifier().verify_pack(str(pack))
    assert code == 10
    assert not [f for f in report["flags"] if _STRUCTURAL in f], report["flags"]


@pytest.mark.offline
def test_manifest_contradicting_run_start_fails_closed(tmp_path, monkeypatch):
    monkeypatch.delenv("NOUS_TSA_ROOTS", raising=False)
    pack = _pack(tmp_path, "diverge")
    mp = pack / "manifest.json"
    man = json.loads(mp.read_text(encoding="utf-8"))
    assert man["anchoring"] == "rfc3161-sim"
    man["anchoring"] = "rekor"
    mp.write_text(json.dumps(man), encoding="utf-8")
    rv = _verifier()
    with pytest.raises(rv.VErr) as exc:
        rv.verify_pack(str(pack))
    assert exc.value.reason == "RUN_START_ANCHORING"
    assert exc.value.seq == 0


@pytest.mark.offline
def test_pack_without_a_declared_policy_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.delenv("NOUS_TSA_ROOTS", raising=False)
    orig = TraceBridge._emit

    def _strip(self, etype, body, *args, **kwargs):
        if etype == "run_start":
            body = {k: v for k, v in body.items() if k != "anchoring"}
        return orig(self, etype, body, *args, **kwargs)

    monkeypatch.setattr(TraceBridge, "_emit", _strip)
    pack = _pack(tmp_path, "legacy")
    first = (pack / "trace.ndjson").read_text(
        encoding="utf-8").splitlines()[0]
    assert "anchoring" not in json.loads(first)["body"]
    code, report = _verifier().verify_pack(str(pack))
    assert code == 0
    assert report["verdict"] == "VALID"
    assert not [f for f in report["flags"] if _DIVERGENCE in f]


@pytest.mark.offline
def test_tb_check_reports_the_same_shortfall(tmp_path, monkeypatch):
    # FG-S251-E parity: the verifier that ships inside every emitted
    # verify_offline.py must not disagree with the reference on the
    # Producer's own output. dossier's embed is covered byte-for-byte by
    # test_embed_matches_tracked_source, so pinning tb_check pins all three.
    pack = _shortfall_pack(tmp_path, monkeypatch)
    code, report = tb_check._tb_verify_pack(str(pack))
    assert code == 10
    assert report["verdict"] == "INTEGRITY-OK/INCOMPLETE"
    assert len([f for f in report["flags"] if _DIVERGENCE in f]) == 1


@pytest.mark.offline
def test_tb_check_fails_closed_on_manifest_divergence(tmp_path, monkeypatch):
    monkeypatch.delenv("NOUS_TSA_ROOTS", raising=False)
    pack = _pack(tmp_path, "diverge_tb")
    mp = pack / "manifest.json"
    man = json.loads(mp.read_text(encoding="utf-8"))
    man["anchoring"] = "rekor"
    mp.write_text(json.dumps(man), encoding="utf-8")
    with pytest.raises(tb_check._TbVErr) as exc:
        tb_check._tb_verify_pack(str(pack))
    assert exc.value.reason == "RUN_START_ANCHORING"
    assert exc.value.seq == 0
