"""Phase 2 Stage 1 (skeleton): grammar + AST sanity for 'law before(A, B)'.

Stage 1 ships ONLY the surface + AST shape. No validator rule, no emit, no Z3.
These tests verify that the new syntax parses, produces the expected AST node,
and does not interfere with the existing 'law NAME = expr' form.

__phase2_stage1_skeleton_tests_v1__
"""
from __future__ import annotations

from ast_nodes import LawNode, LawSequenceNode, WorldNode
from parser import parse_nous


def test_law_before_parses_into_sequence_law() -> None:
    src = (
        "world Bank {\n"
        "    cost_cap: 1.00 USD\n"
        "    law before(authenticate, access_pii)\n"
        "}\n"
    )
    prog = parse_nous(src)
    # __phase2_stage1_skeleton_tests_worlds_fix_v1__
    assert prog.world is not None
    world = prog.world
    assert isinstance(world, WorldNode)
    assert world.name == "Bank"
    assert world.sequence_laws and len(world.sequence_laws) == 1
    seq = world.sequence_laws[0]
    assert isinstance(seq, LawSequenceNode)
    assert seq.kind == "before"
    assert seq.before_label == "authenticate"
    assert seq.after_label == "access_pii"
    # named laws list must NOT contain the sequence law
    assert all(isinstance(x, LawNode) for x in world.laws)


def test_law_classic_still_works_alongside_before() -> None:
    src = (
        "world Bank {\n"
        "    cost_cap: 1.00 USD\n"
        "    law cost_ceiling = $0.50 per cycle\n"
        "    law before(authenticate, access_pii)\n"
        "}\n"
    )
    prog = parse_nous(src)
    world = prog.world  # __phase2_stage1_skeleton_tests_worlds_fix_v1__
    assert len(world.laws) == 1
    assert world.laws[0].name == "cost_ceiling"
    assert len(world.sequence_laws) == 1
    assert world.sequence_laws[0].kind == "before"
    assert world.sequence_laws[0].before_label == "authenticate"


def test_two_before_laws_collected_in_order() -> None:
    src = (
        "world Bank {\n"
        "    cost_cap: 1.00 USD\n"
        "    law before(authenticate, access_pii)\n"
        "    law before(verify_kyc, wire_transfer)\n"
        "}\n"
    )
    prog = parse_nous(src)
    world = prog.world  # __phase2_stage1_skeleton_tests_worlds_fix_v1__
    assert len(world.sequence_laws) == 2
    assert world.sequence_laws[0].before_label == "authenticate"
    assert world.sequence_laws[0].after_label == "access_pii"
    assert world.sequence_laws[1].before_label == "verify_kyc"
    assert world.sequence_laws[1].after_label == "wire_transfer"
