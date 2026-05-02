"""
tests/test_codegen_topology.py

Stage 2 prerequisite tests — Session 69.

Locks in four bugs in NousCodeGen._analyze_topology (codegen.py) and
NousCodeGenJS._analyze_topology (codegen_js.py):

  1. MatchRouteNode arms are dropped from self._routes.
     -> Match-routed targets get no incoming edge recorded.
     -> They are misclassified as entrypoints (receive startup trigger
        they should not get).

  2. FeedbackNode edges are dropped from self._routes.
     -> Feedback targets get no incoming edge recorded.
     -> Same entrypoint misclassification.

The 57 regression templates today do not exercise match routing or
feedback wiring against the entrypoint set, so pytest is green despite
the bugs.

These tests are marked @pytest.mark.xfail(strict=True). They XFAIL
today. When Stage 2 migrates _analyze_topology to ast_nodes.iter_route_edges
they will XPASS; strict mode then converts XPASS into FAIL, forcing
the fixer to remove the xfail markers — at which point these become
permanent regression coverage.

Marker: __session69_codegen_topology_xfail_v1__
"""
from __future__ import annotations

import pytest

from ast_nodes import (
    NousProgram,
    NervousSystemNode,
    SoulNode,
    RouteNode,
    MatchRouteNode,
    MatchArmNode,
    FeedbackNode,
)
from codegen import NousCodeGen
from codegen_js import NousCodeGenJS


# ───────────────────────── helpers ─────────────────────────

def _souls(*names: str) -> list[SoulNode]:
    return [SoulNode.model_construct(name=n) for n in names]


def _program(routes: list, soul_names: list[str]) -> NousProgram:
    """Minimal NousProgram for topology analysis. World omitted on purpose:
    NousCodeGen._analyze_topology guards `if self.program.world` so a
    None world is fine for these contract tests."""
    return NousProgram.model_construct(
        nervous_system=NervousSystemNode(routes=routes),
        souls=_souls(*soul_names),
        world=None,
    )


def _match_program() -> NousProgram:
    """src is the producer; t1 and t2 receive only via match arms.
    Silence arm must not create an edge."""
    return _program(
        routes=[
            MatchRouteNode(
                source="src",
                arms=[
                    MatchArmNode(condition="ok", target="t1"),
                    MatchArmNode(condition="err", target="t2"),
                    MatchArmNode(condition="_", target=None, is_silence=True),
                ],
            )
        ],
        soul_names=["src", "t1", "t2"],
    )


def _feedback_program() -> NousProgram:
    """producer pushes a field into consumer via feedback wiring.
    consumer must not be classified as entrypoint."""
    return _program(
        routes=[
            FeedbackNode(
                source_soul="producer",
                source_field="loss",
                target_soul="consumer",
                target_field="signal",
            )
        ],
        soul_names=["producer", "consumer"],
    )


def _mixed_program() -> NousProgram:
    """Sanity baseline: RouteNode edges still work; the bug must not
    regress correct behavior on the supported variants."""
    return _program(
        routes=[
            RouteNode(source="alpha", target="beta"),
            MatchRouteNode(
                source="alpha",
                arms=[MatchArmNode(condition="x", target="gamma")],
            ),
            FeedbackNode(
                source_soul="beta",
                source_field="f",
                target_soul="alpha",
                target_field="g",
            ),
        ],
        soul_names=["alpha", "beta", "gamma"],
    )


# ───────────────────────── Python codegen ─────────────────────────

def test_py_match_route_arms_recorded_in_routes() -> None:
    cg = NousCodeGen(_match_program())
    assert ("src", "t1") in cg._routes
    assert ("src", "t2") in cg._routes
    assert all(tgt != "_" for _, tgt in cg._routes)


def test_py_match_route_targets_are_not_entrypoints() -> None:
    cg = NousCodeGen(_match_program())
    assert "t1" not in cg._entrypoints
    assert "t2" not in cg._entrypoints
    assert "t1" in cg._listeners
    assert "t2" in cg._listeners
    assert cg._entrypoints == {"src"}


def test_py_feedback_edge_recorded_in_routes() -> None:
    cg = NousCodeGen(_feedback_program())
    assert ("producer", "consumer") in cg._routes


def test_py_feedback_target_is_not_entrypoint() -> None:
    cg = NousCodeGen(_feedback_program())
    assert "consumer" not in cg._entrypoints
    assert "consumer" in cg._listeners
    assert cg._entrypoints == {"producer"}


# ───────────────────────── JS codegen ─────────────────────────

def test_js_match_route_arms_recorded_in_routes() -> None:
    cg = NousCodeGenJS(_match_program())
    assert ("src", "t1") in cg._routes
    assert ("src", "t2") in cg._routes


def test_js_match_route_targets_are_not_entrypoints() -> None:
    cg = NousCodeGenJS(_match_program())
    assert "t1" not in cg._entrypoints
    assert "t2" not in cg._entrypoints
    assert cg._entrypoints == {"src"}


def test_js_feedback_edge_recorded_in_routes() -> None:
    cg = NousCodeGenJS(_feedback_program())
    assert ("producer", "consumer") in cg._routes


def test_js_feedback_target_is_not_entrypoint() -> None:
    cg = NousCodeGenJS(_feedback_program())
    assert "consumer" not in cg._entrypoints
    assert cg._entrypoints == {"producer"}


# ───────────────────────── sanity (no xfail) ─────────────────────────

def test_py_route_node_baseline_unaffected() -> None:
    """Sanity: the supported RouteNode path still classifies correctly.
    This must NOT xfail — guards against regression of the working path."""
    p = _program(
        routes=[RouteNode(source="a", target="b")],
        soul_names=["a", "b"],
    )
    cg = NousCodeGen(p)
    assert ("a", "b") in cg._routes
    assert cg._entrypoints == {"a"}
    assert cg._listeners == {"b"}


def test_js_route_node_baseline_unaffected() -> None:
    p = _program(
        routes=[RouteNode(source="a", target="b")],
        soul_names=["a", "b"],
    )
    cg = NousCodeGenJS(p)
    assert ("a", "b") in cg._routes
    assert cg._entrypoints == {"a"}
    assert cg._listeners == {"b"}


def test_py_silence_arms_never_create_edges_post_fix() -> None:
    """After Stage 2: silence arms must NOT yield edges. iter_route_edges
    already enforces this. This test is xfail today because no MatchRoute
    edges are recorded at all; post-fix it must pass without needing to
    be un-xfailed."""
    p = _match_program()
    cg = NousCodeGen(p)
    silence_edges = [e for e in cg._routes if e[1] is None]
    assert silence_edges == []


def test_js_silence_arms_never_create_edges_post_fix() -> None:
    p = _match_program()
    cg = NousCodeGenJS(p)
    silence_edges = [e for e in cg._routes if e[1] is None]
    assert silence_edges == []


# ───────────────────────── mixed-graph contract (xfail) ─────────────────────────

def test_py_mixed_graph_all_edges_present() -> None:
    cg = NousCodeGen(_mixed_program())
    assert ("alpha", "beta") in cg._routes  # RouteNode
    assert ("alpha", "gamma") in cg._routes  # MatchArm
    assert ("beta", "alpha") in cg._routes  # Feedback


def test_js_mixed_graph_all_edges_present() -> None:
    cg = NousCodeGenJS(_mixed_program())
    assert ("alpha", "beta") in cg._routes
    assert ("alpha", "gamma") in cg._routes
    assert ("beta", "alpha") in cg._routes
