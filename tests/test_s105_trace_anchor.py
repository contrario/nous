"""S105 -- detached Rekor v2 trace anchoring (offline via mock hook).

# __s105_trace_anchor_tests_v1__
"""
from __future__ import annotations

import pytest

from compiled_trace import run_compiled_with_trace
from rekor_verify_v2 import RekorAnchorV2
from trace_anchor import TraceAnchorError, anchor_trace_to_rekor_v2

_PROG = (
    "world W {\n"
    "  cost_cap: 0.10 USD\n"
    "  max_ticks: 4\n"
    "  events { Ping }\n"
    "}\n"
    "message Ping { v: string }\n"
    "soul A {\n"
    "  mind: claude-sonnet-4-6 @ Tier1\n"
    "  tokens: input = 100 output = 50\n"
    "  instinct {\n"
    "    speak Ping(v: \"x\")\n"
    "  }\n"
    "  heal { on error => retry(2, error) }\n"
    "}\n"
)


def _fake_anchor() -> RekorAnchorV2:
    return RekorAnchorV2(
        rekor_api_version=2,
        log_id="test-log-id",
        log_index=0,
        body_b64="dGVzdC1ib2R5",
        checkpoint_envelope="test-checkpoint-envelope",
        inclusion_proof_hashes=["aGFzaC1vbmU="],
        rfc3161_token_b64="dGVzdC10b2tlbg==",
    )


def test_anchor_signed_trace_returns_detached_anchor() -> None:
    env = run_compiled_with_trace(_PROG, max_cycles=1)
    assert env.signature is not None
    anchor = anchor_trace_to_rekor_v2(env, _test_anchor=_fake_anchor())
    assert isinstance(anchor, RekorAnchorV2)
    assert anchor.log_index == 0
    block = anchor.to_manifest_block()
    assert block["log_id"] == "test-log-id"


def test_anchor_unsigned_envelope_refused() -> None:
    from trace_recorder import TraceRecorder
    from run_shas import compute_run_shas
    import _version

    src_sha, smt_sha, pricing_sha = compute_run_shas(_PROG)
    rec = TraceRecorder(_version.__version__, "W", src_sha, smt_sha, pricing_sha)
    rec.record_message("unknown_soul", 0, action="Ping")
    unsigned = rec.finalize(private_key=None)
    assert unsigned.signature is None
    with pytest.raises(TraceAnchorError):
        anchor_trace_to_rekor_v2(unsigned, _test_anchor=_fake_anchor())
