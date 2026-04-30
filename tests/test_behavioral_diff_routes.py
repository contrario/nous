"""
tests/test_behavioral_diff_routes.py

Regression coverage for the FeedbackNode crash hit in Session 66.
/v1/diff blew up on trading_floor because three internal helpers did
blind route.source / route.target attribute access, assuming every
nerve statement has the shape of RouteNode. Every NerveStatement
variant must be handled by _get_routes (which yields edges) and
_get_entrypoints (which computes the "is a target" set).

Marker: __session66_behavioral_diff_routes_v1__
"""
from __future__ import annotations

from ast_nodes import (
    NousProgram, NervousSystemNode, SoulNode,
    RouteNode, MatchRouteNode, MatchArmNode,
    FanInNode, FanOutNode, FeedbackNode,
)
from behavioral_diff import _get_routes, _get_entrypoints


def _mk_program(routes: list, souls: list | None = None) -> NousProgram:
    """Build a minimal NousProgram via model_construct (skips validation)."""
    return NousProgram.model_construct(
        nervous_system=NervousSystemNode(routes=routes),
        souls=souls or [],
    )


# ---- _get_routes ----------------------------------------------------------

def test_get_routes_route_node() -> None:
    p = _mk_program([RouteNode(source="A", target="B")])
    assert _get_routes(p) == [("A", "B")]


def test_get_routes_match_route_node() -> None:
    p = _mk_program([
        MatchRouteNode(
            source="A",
            arms=[
                MatchArmNode(condition="x", target="B"),
                MatchArmNode(condition="y", target="C"),
                MatchArmNode(condition="silent", is_silence=True),
            ],
        )
    ])
    assert _get_routes(p) == [("A", "B"), ("A", "C")]


def test_get_routes_fan_in_node() -> None:
    p = _mk_program([FanInNode(sources=["A", "B", "C"], target="X")])
    assert _get_routes(p) == [("A", "X"), ("B", "X"), ("C", "X")]


def test_get_routes_fan_out_node() -> None:
    p = _mk_program([FanOutNode(source="A", targets=["X", "Y"])])
    assert _get_routes(p) == [("A", "X"), ("A", "Y")]


def test_get_routes_feedback_node() -> None:
    """Regression: Session 66 - FeedbackNode crashed _get_routes."""
    p = _mk_program([FeedbackNode(
        source_soul="Strategist",
        source_field="signal",
        target_soul="Watcher",
        target_field="last_signal",
    )])
    assert _get_routes(p) == [("Strategist", "Watcher")]


def test_get_routes_mixed() -> None:
    p = _mk_program([
        RouteNode(source="A", target="B"),
        FeedbackNode(
            source_soul="B", source_field="f",
            target_soul="A", target_field="g",
        ),
    ])
    assert _get_routes(p) == [("A", "B"), ("B", "A")]


def test_get_routes_empty() -> None:
    p = _mk_program([])
    assert _get_routes(p) == []


# ---- _get_entrypoints -----------------------------------------------------

def test_get_entrypoints_with_feedback_node() -> None:
    """Regression: Session 66 - FeedbackNode crashed _get_entrypoints."""
    s_a = SoulNode.model_construct(name="A")
    s_b = SoulNode.model_construct(name="B")
    p = NousProgram.model_construct(
        nervous_system=NervousSystemNode(routes=[
            FeedbackNode(
                source_soul="A", source_field="f",
                target_soul="B", target_field="g",
            ),
        ]),
        souls=[s_a, s_b],
    )
    # B is the target of the feedback edge; A has no incoming edge -> entrypoint.
    assert _get_entrypoints(p) == ["A"]
