"""LC-G3 (D2, mechanism O2): a tool_call outside the declared events is refused.

K3.1, K3.3 and K3.5 of LC_INNOVATION_GATE.md (6191a812), with the
mechanism ruled in S414: refusal over guess, on the precedent of the
undeclared soul and the undeclared gated action. When the re-derived spec
declares events, every tool_call must carry an action label that is one of
them; a missing or undeclared label raises ConformancePreconditionError.
When the spec declares no events the check is vacuous. Scope is the
tool_call kind only.

HONEST BOUNDARY: EVIDENCES that every recorded tool_call named a declared
event. It sees recorded events only; a tool executed outside the recorder
is invisible to it. It proves nothing.

# __s414_tool_surface_tests_v1__
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from textwrap import dedent

import pytest
import tomllib
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from ast_nodes import (
    CostCap, LawSequenceNode, MindNode, NousProgram, SoulNode,
    TokensDecl, WorldNode,
)
from conformance import ConformancePreconditionError, verify_conformance
from manifest import manifest_from_verify
from nous_trace import TraceEnvelope, TraceEvent, sign_trace
from pricing import PricingTable
from smt_emit import emit_sequence_spec, emit_smt
from smt_verify import VerifyResult

_TODAY = date(2026, 4, 28)
_TS = "2026-04-28T00:00:00Z"
_PRICING_TOML = dedent("""\
    _schema_version = "2.0"
    _currency = "USD"
    [models."m1"]
    provider = "test"
    pricing_model = "per_token"
    input_per_1m = "1.00"
    output_per_1m = "5.00"
    reasoning_token_multiplier = "1.0"
    verified_date = "2026-04-28"
""")
_EVENTS = ["SearchDocs", "GetWeather"]


@pytest.fixture
def pricing() -> PricingTable:
    return PricingTable.model_validate(tomllib.loads(_PRICING_TOML))


def _at_most(n: int, label: str) -> LawSequenceNode:
    return LawSequenceNode(
        kind="at_most", before_label=label, after_label=None, count=n,
    )


def _prog(events, laws=()):
    return NousProgram(
        world=WorldNode(
            name="W",
            cost_cap=CostCap(amount=Decimal("0.50"), currency="USD"),
            max_ticks=8,
            sequence_laws=list(laws),
            events=list(events),
        ),
        souls=[SoulNode(
            name="Agent",
            mind=MindNode(model="m1", tier="Tier1"),
            tokens=TokensDecl(input=4000, output=800),
        )],
    )


def _spec(pricing, events, laws=()):
    return emit_smt(_prog(events, laws), pricing, source_text="x",
                    today=_TODAY)


def _manifest(spec):
    return manifest_from_verify(
        VerifyResult(
            verdict="proven",
            spec=spec,
            solver_name="z3",
            solver_version="z3 4.16.0",
            elapsed_ms=1,
            timestamp_utc=datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
        ),
        nous_version="lc-g3",
    )


_CLEAN = [
    (0, "llm_call", 3000, 500, None),
    (0, "tool_call", 0, 0, "SearchDocs"),
    (1, "llm_call", 3500, 400, None),
    (1, "tool_call", 0, 0, "GetWeather"),
    (2, "llm_call", 3900, 700, None),
]


def _detail(pricing, events, rows, laws=()):
    spec = _spec(pricing, events, laws)
    evs = [
        TraceEvent(
            seq=i, tick=r[0], soul="Agent", kind=r[1],
            input_tokens=r[2], output_tokens=r[3], tool_cost="0",
            action=r[4], timestamp_utc=_TS,
        )
        for i, r in enumerate(rows)
    ]
    env = TraceEnvelope(
        nous_version="lc-g3", world_name="W",
        source_sha256=spec.source_sha256,
        smt_spec_sha256=spec.sha256(),
        pricing_sha256=spec.pricing_sha256,
        events=evs,
    )
    signed = sign_trace(env, Ed25519PrivateKey.generate())
    return verify_conformance(signed, _manifest(spec), spec, pricing)


def test_clean_declared_labels_pass(pricing) -> None:
    d = _detail(pricing, _EVENTS, _CLEAN)
    assert d.ok is True


def test_undeclared_label_is_refused(pricing) -> None:
    with pytest.raises(ConformancePreconditionError,
                       match="'DeleteAll' not in declared events"):
        _detail(pricing, _EVENTS,
                _CLEAN + [(3, "tool_call", 0, 0, "DeleteAll")])


def test_relabel_bypass_of_at_most_is_refused(pricing) -> None:
    laws = [_at_most(3, "SearchDocs"), _at_most(2, "GetWeather")]
    rows = _CLEAN + [(3, "tool_call", 0, 0, "SearchDocs2")] * 5
    with pytest.raises(ConformancePreconditionError,
                       match="'SearchDocs2' not in declared events"):
        _detail(pricing, _EVENTS, rows, laws)


def test_at_most_still_counts_declared_labels(pricing) -> None:
    laws = [_at_most(3, "SearchDocs"), _at_most(2, "GetWeather")]
    rows = _CLEAN + [(3, "tool_call", 0, 0, "SearchDocs")] * 3
    d = _detail(pricing, _EVENTS, rows, laws)
    assert d.sequence_ok is False
    assert d.ok is False


def test_unlabelled_tool_call_is_refused_when_events_declared(
    pricing,
) -> None:
    with pytest.raises(ConformancePreconditionError,
                       match="tool_call with no action label"):
        _detail(pricing, _EVENTS, _CLEAN + [(3, "tool_call", 0, 0, None)])


def test_vacuous_without_declared_events(pricing) -> None:
    rows = [
        (0, "llm_call", 3000, 500, None),
        (0, "tool_call", 0, 0, "anything"),
        (1, "tool_call", 0, 0, None),
    ]
    d = _detail(pricing, [], rows)
    assert d.ok is True


def test_scope_is_tool_call_kind_only(pricing) -> None:
    rows = _CLEAN + [(3, "llm_call", 100, 50, "NotAnEvent")]
    d = _detail(pricing, _EVENTS, rows)
    assert d.ok is True


def test_spec_declared_events_drop_when_empty(pricing) -> None:
    assert "\nDE:" not in _spec(pricing, []).canonical_str()
    lines = _spec(pricing, ["b", "a"]).canonical_str().split("\n")
    assert [x for x in lines if x.startswith("DE:")] == ["DE:a", "DE:b"]


def test_declared_events_bind_the_spec_hash(pricing) -> None:
    assert _spec(pricing, ["a"]).sha256() != _spec(pricing, ["b"]).sha256()


def test_both_constructors_carry_declared_events(pricing) -> None:
    seq = emit_sequence_spec(_prog(["b", "a"]), source_text="x")
    assert seq.declared_events == ("a", "b")
    assert _spec(pricing, ["b", "a"]).declared_events == ("a", "b")
