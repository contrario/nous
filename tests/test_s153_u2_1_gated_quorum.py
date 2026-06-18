from __future__ import annotations
# __s153_u2_1_gated_quorum_tests_v1__
# S153 U2.1: 'law gated(<action>, K)' quorum threshold -- language surface
# only (grammar/AST/parser/validator GA003). quorum unused downstream this
# unit; default K=1 is byte-identical to plain 'law gated(<action>)'.
from decimal import Decimal
from textwrap import dedent

from ast_nodes import (
    CostCap, LawGatedNode, MindNode, NousProgram, SoulNode,
    TokensDecl, WorldNode,
)
from parser import parse_nous
from validator import validate_program


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


_SRC_QUORUM = dedent("""\
    world W {
      cost_cap: 0.10 USD
      max_ticks: 4
      events { escalate, resolve }
      law gated(escalate, 2)
    }
    soul S {
      mind: gpt-5-2 @ Tier1
      tokens: input = 100 output = 50
    }
""")

_SRC_PLAIN = dedent("""\
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


def test_ast_default_quorum_is_one() -> None:
    node = LawGatedNode(action="escalate")
    assert node.quorum == 1


def test_ast_explicit_quorum() -> None:
    node = LawGatedNode(action="escalate", quorum=3)
    assert node.quorum == 3


def test_parse_gated_quorum_builds_node() -> None:
    prog = parse_nous(_SRC_QUORUM)
    gated = prog.world.gated_actions
    assert len(gated) == 1
    assert gated[0].action == "escalate"
    assert gated[0].quorum == 2


def test_parse_plain_gated_defaults_quorum_one() -> None:
    prog = parse_nous(_SRC_PLAIN)
    gated = prog.world.gated_actions
    assert len(gated) == 1
    assert gated[0].action == "escalate"
    assert gated[0].quorum == 1


def test_validate_quorum_two_ok() -> None:
    prog = _prog([LawGatedNode(action="escalate", quorum=2)],
                 ["escalate", "resolve"])
    result = validate_program(prog)
    assert not any(e.code == "GA003" for e in result.errors)


def test_validate_quorum_zero_rejected() -> None:
    prog = _prog([LawGatedNode(action="escalate", quorum=0)],
                 ["escalate"])
    result = validate_program(prog)
    assert not result.ok
    assert any(e.code == "GA003" for e in result.errors)


def test_validate_quorum_one_ok() -> None:
    prog = _prog([LawGatedNode(action="escalate", quorum=1)],
                 ["escalate"])
    result = validate_program(prog)
    assert not any(e.code == "GA003" for e in result.errors)
