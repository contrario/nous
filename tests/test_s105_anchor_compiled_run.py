"""S105 -- anchor_compiled_run reachable caller (offline via mock hook).

# __s105_anchor_compiled_run_tests_v1__
"""
from __future__ import annotations

from compiled_trace import anchor_compiled_run
from nous_trace import TraceEnvelope, verify_trace_signature
from rekor_verify_v2 import RekorAnchorV2

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


def test_anchor_compiled_run_returns_signed_trace_and_detached_anchor() -> None:
    env, anchor = anchor_compiled_run(_PROG, max_cycles=1, _test_anchor=_fake_anchor())
    assert isinstance(env, TraceEnvelope)
    assert isinstance(anchor, RekorAnchorV2)
    assert env.signature is not None
    assert verify_trace_signature(env) is True
    msgs = [(e.kind, e.action) for e in env.events if e.kind == "message"]
    assert ("message", "Ping") in msgs
    assert anchor.log_id == "test-log-id"
