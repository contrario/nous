"""Regression tests for ast_nodes.iter_route_edges and dispatch sweep.

Covers the latent bugs identified in Session 67:
- cli.py `nous show` previously skipped FanIn/FanOut/Feedback edges
- cost_oracle.py crashed on FanOutNode (no .target attr)

If iter_route_edges() ever changes behavior, these tests catch it.
"""
from __future__ import annotations

import pytest

from ast_nodes import (
    FanInNode,
    FanOutNode,
    FeedbackNode,
    MatchArmNode,
    MatchRouteNode,
    NervousSystemNode,
    RouteNode,
    iter_route_edges,
)


def _ns_all_kinds() -> NervousSystemNode:
    return NervousSystemNode(
        routes=[
            RouteNode(source="alpha", target="beta"),
            MatchRouteNode(
                source="gamma",
                arms=[
                    MatchArmNode(condition="x", target="delta"),
                    MatchArmNode(condition="y", target="epsilon"),
                    MatchArmNode(condition="_", target=None, is_silence=True),
                ],
            ),
            FanInNode(sources=["s1", "s2", "s3"], target="sink"),
            FanOutNode(source="hub", targets=["o1", "o2"]),
            FeedbackNode(
                source_soul="learner",
                source_field="loss",
                target_soul="teacher",
                target_field="signal",
            ),
        ]
    )


def test_iter_route_edges_none_input() -> None:
    assert list(iter_route_edges(None)) == []


def test_iter_route_edges_empty_routes() -> None:
    ns = NervousSystemNode(routes=[])
    assert list(iter_route_edges(ns)) == []


def test_iter_route_edges_route_node() -> None:
    ns = NervousSystemNode(routes=[RouteNode(source="a", target="b")])
    assert list(iter_route_edges(ns)) == [("a", "b", "route")]


def test_iter_route_edges_match_route_skips_silence() -> None:
    ns = NervousSystemNode(
        routes=[
            MatchRouteNode(
                source="src",
                arms=[
                    MatchArmNode(condition="ok", target="t1"),
                    MatchArmNode(condition="_", target=None, is_silence=True),
                    MatchArmNode(condition="err", target="t2"),
                ],
            )
        ]
    )
    edges = list(iter_route_edges(ns))
    assert edges == [("src", "t1", "match"), ("src", "t2", "match")]


def test_iter_route_edges_fanin_expands() -> None:
    ns = NervousSystemNode(
        routes=[FanInNode(sources=["a", "b", "c"], target="z")]
    )
    edges = list(iter_route_edges(ns))
    assert edges == [
        ("a", "z", "fanin"),
        ("b", "z", "fanin"),
        ("c", "z", "fanin"),
    ]


def test_iter_route_edges_fanout_expands() -> None:
    ns = NervousSystemNode(
        routes=[FanOutNode(source="hub", targets=["x", "y"])]
    )
    edges = list(iter_route_edges(ns))
    assert edges == [("hub", "x", "fanout"), ("hub", "y", "fanout")]


def test_iter_route_edges_feedback_uses_soul_fields() -> None:
    ns = NervousSystemNode(
        routes=[
            FeedbackNode(
                source_soul="a",
                source_field="f1",
                target_soul="b",
                target_field="f2",
            )
        ]
    )
    edges = list(iter_route_edges(ns))
    assert edges == [("a", "b", "feedback")]


def test_iter_route_edges_all_kinds_count() -> None:
    ns = _ns_all_kinds()
    edges = list(iter_route_edges(ns))
    assert len(edges) == 1 + 2 + 3 + 2 + 1  # 9 edges total
    kinds = {kind for _, _, kind in edges}
    assert kinds == {"route", "match", "fanin", "fanout", "feedback"}


def test_iter_route_edges_targets_set_no_crash_on_fanout() -> None:
    """Regression: cost_oracle.py used to crash on FanOutNode.

    The naive `route.target` access fails because FanOutNode has `targets: list[str]`
    not `target: str`. The helper-based collection must produce 'o1' and 'o2'
    in the targets set without raising.
    """
    ns = _ns_all_kinds()
    targets = {tgt for _, tgt, _ in iter_route_edges(ns)}
    assert {"o1", "o2"} <= targets
    assert "sink" in targets
    assert "teacher" in targets


def test_iter_route_edges_unknown_subtype_raises() -> None:
    """Helper must fail loudly if a new NerveStatement variant is added
    without extending the dispatcher."""

    class FakeNerve:
        pass

    ns = NervousSystemNode.model_construct(routes=[FakeNerve()])
    with pytest.raises(TypeError, match="unknown NerveStatement"):
        list(iter_route_edges(ns))
