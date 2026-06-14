from __future__ import annotations
# __s141_u3_gated_validator_tests_v1__
# S141 U3: validator for 'law gated(<action>)' -- action labels must be
# declared in the world 'events { ... }' block (GA001/GA002).
from decimal import Decimal
from textwrap import dedent

from ast_nodes import (
    CostCap, LawGatedNode, MindNode, NousProgram, SoulNode,
    TokensDecl, WorldNode,
)
from parser import parse_nous
from validator import validate_program


def _gated(action: str) -> LawGatedNode:
    return LawGatedNode(action=action)


def _prog(gated_actions, events) -> NousProgram:
    return NousProgram(
        world=WorldNode(
            name="W",
            cost_cap=CostCap(amount=Decimal("0.10"), currency="USD"),
            max_ticks=4,
            gated_actions=list(gated_actions),
            events=list(events),
        ),
        souls=[SoulNode(
            name="S",
            mind=MindNode(model="m1", tier="Tier1"),
            tokens=TokensDecl(input=100, output=50),
        )],
    )


_SRC = dedent("""\
    world W {
      cost_cap: 0.10 USD
      max_ticks: 4
      events { escalate, resolve }
      law gated(escalate)
    }
    soul S {
      mind: gpt-5-2 @ Tier1
      tokens: input = 100 output = 50
    }
""")


def test_parse_gated_builds_node() -> None:
    prog = parse_nous(_SRC)
    gated = prog.world.gated_actions
    assert len(gated) == 1
    assert gated[0].action == "escalate"
    assert prog.world.sequence_laws == []


def test_validate_gated_declared_ok() -> None:
    prog = _prog([_gated("escalate")], ["escalate", "resolve"])
    result = validate_program(prog)
    assert not any(e.code in ("GA001", "GA002") for e in result.errors)


def test_validate_gated_undeclared_label() -> None:
    prog = _prog([_gated("ghost")], ["escalate"])
    result = validate_program(prog)
    assert not result.ok
    assert any(e.code == "GA002" for e in result.errors)


def test_validate_gated_no_events_block() -> None:
    prog = _prog([_gated("escalate")], [])
    result = validate_program(prog)
    assert not result.ok
    assert any(e.code == "GA001" for e in result.errors)


def test_validate_no_gated_no_error() -> None:
    prog = _prog([], [])
    result = validate_program(prog)
    assert not any(e.code in ("GA001", "GA002") for e in result.errors)


def test_validate_src_gated_declared_ok() -> None:
    prog = parse_nous(_SRC)
    result = validate_program(prog)
    assert not any(e.code in ("GA001", "GA002") for e in result.errors)
