"""P5b-1: Producer support for the composite "both" anchoring backend.
__nous_p5b1_producer_both_tests_v1__

SPEC 10.1 declares the anchoring policy in the signed run_start and in the
unsigned pack manifest. "both" needs no new field on either surface: the
Producer already interpolates self._anchoring into each, so declaring the
composite policy is a ctor argument, not a schema change.

Delivery is a composite block rather than two legs. The checkpoint body
carries one "anchor" key and _make_anchor returns one block, so two
independent legs would mean "anchors": [...] and a wire change. The
composite sub-blocks are the single-backend blocks verbatim, type key
included, so the Producer emits the same object it would have emitted
standalone and a Verifier can dispatch each leg through unchanged
single-backend code. The redundant type is a checkable invariant: a
sub-block type that does not equal its key is malformed.

Produce-time DEGRADES, never refuses (SPEC 10.2):

    both legs succeed  -> composite block
    one leg succeeds   -> the surviving SINGLE-BACKEND block, unchanged
    both legs fail     -> None, the run continues unanchored

Refusing would discard a good transparency anchor to avoid an incomplete
claim, which is strictly worse evidence.

Under "both" the rekor leg does NOT run its own RFC 3161 timestamp. The
rekor token binds leaf.leaf_signature_der; the rfc3161 backend's token
binds the Merkle root. Both succeeding would place two genTimes in one
anchor with no disagreement rule in the SPEC -- a silent merge arriving
through the time axis. rfc3161-over-root is also one binding link where
rekor-token-over-leaf-signature is three. So: rekor leg evidences
membership, rfc3161 leg is the sole time, bound directly to the signed
root.

anchor_failures stays PRODUCER-ASSERTED. It is unsigned, never written
into the pack, and is not evidence of an outage to a Verifier. The leg
discriminators "both-rekor" and "both-rfc3161" are new; the existing
single-backend stage values are deliberately untouched.

These tests cover the Producer only. Verification of the composite block
is P5b-2 (reference verifier) and P5b-3 (tb_check plus embed re-sync); no
verifier in the tree reads type "both" yet.

rekor_entry.parse_rekor_leaf is stubbed in the leg fixture. The
shipped rekor arm swallows every exception in its timestamp leg
under one handler, so a synthetic leaf body the real parser rejects
yields the same stage value as a TSA outage, and the regression
assertions would pass for a cause that never occurred. Stubbing the
parser isolates the assertion to the thing under test: that the
rekor arm attaches a timestamp of its own where the composite arm
does not. The "both" arm never reaches this code by design, which
is why it needs no such stub.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

pytest.importorskip("trace_bridge")

import rekor_anchor_v2
import rekor_entry
import tsa_client
from trace_bridge import TraceBridge, TraceBridgeError

_ROOT = b"\x11" * 32


class _FakeV2:
    def __init__(self) -> None:
        body = {"spec": {"signature": {"content": "AAEC"}}}
        self.body_b64 = base64.b64encode(
            json.dumps(body).encode("utf-8")
        ).decode()

    def to_manifest_block(self) -> dict:
        return {"log_index": 7, "inclusion_proof": {"hashes": []}}


def _ok_rekor(root, base_url=None, timeout_seconds=None):
    return _FakeV2()


def _fail_rekor(root, base_url=None, timeout_seconds=None):
    raise RuntimeError("rekor submission refused")


class _FakeLeaf:
    leaf_signature_der = b"LEAFSIG"


def _ok_leaf(obj):
    return _FakeLeaf()


def _ok_tsa(timestamped_data=None, base_url=None, timeout_seconds=None):
    return b"TOKENBYTES"


def _fail_tsa(timestamped_data=None, base_url=None, timeout_seconds=None):
    raise RuntimeError("tsa unreachable")


def _legs(monkeypatch, rekor_ok: bool, tsa_ok: bool) -> None:
    monkeypatch.setattr(
        rekor_anchor_v2,
        "anchor_manifest_to_rekor_v2",
        _ok_rekor if rekor_ok else _fail_rekor,
    )
    monkeypatch.setattr(
        tsa_client, "anchor_timestamp", _ok_tsa if tsa_ok else _fail_tsa
    )
    monkeypatch.setattr(rekor_entry, "parse_rekor_leaf", _ok_leaf)


def _anchor(tmp_path, name, monkeypatch, backend, rekor_ok, tsa_ok):
    _legs(monkeypatch, rekor_ok, tsa_ok)
    monkeypatch.delenv("NOUS_TSA_ROOTS", raising=False)
    monkeypatch.delenv("NOUS_REKOR_LOG_KEYS", raising=False)
    pack = tmp_path / name
    with TraceBridge(
        str(pack),
        "actor",
        [],
        str(tmp_path / ("k_" + name)),
        anchoring=backend,
    ) as br:
        block = br._make_anchor(_ROOT)
        failures = [dict(f) for f in br.anchor_failures]
    return block, failures, pack


@pytest.mark.offline
@pytest.mark.parametrize(
    "backend", ["rfc3161-sim", "rfc3161", "rekor", "both"]
)
def test_ctor_accepts_every_declared_backend(
    tmp_path, monkeypatch, backend
) -> None:
    _, _, pack = _anchor(
        tmp_path, "ctor_" + backend.replace("-", "_"), monkeypatch,
        backend, True, True,
    )
    man = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    assert man["anchoring"] == backend


@pytest.mark.offline
def test_ctor_rejects_unknown_backend_and_names_both(tmp_path) -> None:
    with pytest.raises(TraceBridgeError) as exc:
        TraceBridge(
            str(tmp_path / "bad"),
            "actor",
            [],
            str(tmp_path / "k_bad"),
            anchoring="nonsense",
        )
    assert "both" in str(exc.value)


@pytest.mark.offline
def test_both_is_declared_in_signed_run_start(
    tmp_path, monkeypatch
) -> None:
    _, _, pack = _anchor(
        tmp_path, "declared", monkeypatch, "both", True, True
    )
    lines = (pack / "trace.ndjson").read_text(encoding="utf-8").splitlines()
    run_start = json.loads(lines[0])
    assert run_start["event_type"] == "run_start"
    assert run_start["body"]["anchoring"] == "both"
    assert run_start["sig"]


@pytest.mark.offline
def test_both_is_declared_in_pack_manifest(tmp_path, monkeypatch) -> None:
    _, _, pack = _anchor(
        tmp_path, "manifest", monkeypatch, "both", True, True
    )
    man = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    assert man["anchoring"] == "both"


@pytest.mark.offline
def test_both_legs_ok_emits_composite_block(tmp_path, monkeypatch) -> None:
    block, failures, _ = _anchor(
        tmp_path, "composite", monkeypatch, "both", True, True
    )
    assert block["type"] == "both"
    assert sorted(block) == ["rekor", "rfc3161", "type"]
    assert block["rekor"]["type"] == "rekor"
    assert block["rfc3161"]["type"] == "rfc3161"
    assert block["rekor"]["log_index"] == 7
    assert block["rfc3161"]["token_b64"] == base64.b64encode(
        b"TOKENBYTES"
    ).decode()
    assert failures == []


@pytest.mark.offline
def test_both_rekor_leg_carries_no_timestamp_of_its_own(
    tmp_path, monkeypatch
) -> None:
    block, _, _ = _anchor(
        tmp_path, "onetime", monkeypatch, "both", True, True
    )
    assert "rfc3161_token_b64" not in block["rekor"]
    assert "gen_time" not in block["rekor"]


@pytest.mark.offline
def test_both_degrades_to_rekor_when_tsa_fails(
    tmp_path, monkeypatch
) -> None:
    block, failures, _ = _anchor(
        tmp_path, "degrekor", monkeypatch, "both", True, False
    )
    assert block["type"] == "rekor"
    assert sorted(block) == ["inclusion_proof", "log_index", "type"]
    assert "rfc3161_token_b64" not in block
    assert [f["stage"] for f in failures] == ["both-rfc3161"]


@pytest.mark.offline
def test_both_degrades_to_rfc3161_when_rekor_fails(
    tmp_path, monkeypatch
) -> None:
    block, failures, _ = _anchor(
        tmp_path, "degrfc", monkeypatch, "both", False, True
    )
    assert block["type"] == "rfc3161"
    assert sorted(block) == ["token_b64", "type"]
    assert [f["stage"] for f in failures] == ["both-rekor"]


@pytest.mark.offline
def test_both_legs_fail_returns_none_and_run_continues(
    tmp_path, monkeypatch
) -> None:
    block, failures, pack = _anchor(
        tmp_path, "degnone", monkeypatch, "both", False, False
    )
    assert block is None
    assert sorted(f["stage"] for f in failures) == [
        "both-rekor",
        "both-rfc3161",
    ]
    assert all("from_seq" in f for f in failures)
    assert (pack / "trace.ndjson").exists()


@pytest.mark.offline
def test_anchor_failures_never_reach_the_pack(tmp_path, monkeypatch) -> None:
    _, failures, pack = _anchor(
        tmp_path, "asserted", monkeypatch, "both", False, False
    )
    assert failures
    man = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    assert "anchor_failures" not in man
    trace = (pack / "trace.ndjson").read_text(encoding="utf-8")
    assert "both-rekor" not in trace
    assert "both-rfc3161" not in trace


@pytest.mark.offline
def test_rekor_arm_still_runs_its_own_timestamp(
    tmp_path, monkeypatch
) -> None:
    block, failures, _ = _anchor(
        tmp_path, "regrekor", monkeypatch, "rekor", True, True
    )
    assert block["type"] == "rekor"
    assert "rfc3161_token_b64" in block
    assert failures == []


@pytest.mark.offline
def test_rekor_arm_tsa_failure_stage_unchanged(
    tmp_path, monkeypatch
) -> None:
    block, failures, _ = _anchor(
        tmp_path, "regrekortsa", monkeypatch, "rekor", True, False
    )
    assert block["type"] == "rekor"
    assert [f["stage"] for f in failures] == ["rekor-timestamp"]
    assert "tsa unreachable" in failures[0]["error"]


@pytest.mark.offline
def test_rekor_arm_submission_failure_stage_unchanged(
    tmp_path, monkeypatch
) -> None:
    block, failures, _ = _anchor(
        tmp_path, "regrekorsub", monkeypatch, "rekor", False, True
    )
    assert block is None
    assert [f["stage"] for f in failures] == ["rekor"]


@pytest.mark.offline
def test_rfc3161_arm_unchanged(tmp_path, monkeypatch) -> None:
    block, failures, _ = _anchor(
        tmp_path, "regrfc", monkeypatch, "rfc3161", True, True
    )
    assert block["type"] == "rfc3161"
    assert "token_b64" in block
    assert failures == []


@pytest.mark.offline
def test_rfc3161_arm_failure_record_has_no_stage_key(
    tmp_path, monkeypatch
) -> None:
    block, failures, _ = _anchor(
        tmp_path, "regrfcfail", monkeypatch, "rfc3161", True, False
    )
    assert block is None
    assert failures
    assert "stage" not in failures[0]


@pytest.mark.offline
def test_rfc3161_sim_arm_unchanged(tmp_path, monkeypatch) -> None:
    block, failures, _ = _anchor(
        tmp_path, "regsim", monkeypatch, "rfc3161-sim", True, True
    )
    assert block["type"] == "rfc3161-sim"
    assert "gen_time" in block
    assert "token" in block
    assert failures == []
