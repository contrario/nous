"""Test LALR parser migration against gate_alpha.nous."""
import sys
import time
from pathlib import Path

NOUS_DIR = Path(__file__).parent
sys.path.insert(0, str(NOUS_DIR))

from parser import parse_nous_file, _get_parser
from ast_nodes import LetNode, ForNode, RememberNode, SpeakNode, RouteNode


def test_lalr_parse() -> None:
    src = NOUS_DIR / "gate_alpha.nous"

    t0 = time.perf_counter()
    _get_parser()
    t_grammar = time.perf_counter() - t0

    t0 = time.perf_counter()
    program = parse_nous_file(src)
    t_parse = time.perf_counter() - t0

    print(f"Grammar compile: {t_grammar*1000:.1f}ms")
    print(f"Parse time:      {t_parse*1000:.1f}ms")
    print()

    assert program.world is not None, "Missing world"
    assert program.world.name == "GateAlpha"
    assert len(program.world.laws) == 3
    assert program.world.heartbeat == "5m"
    print(f"✓ World: {program.world.name}, {len(program.world.laws)} laws, heartbeat={program.world.heartbeat}")

    assert len(program.messages) == 2
    print(f"✓ Messages: {[m.name for m in program.messages]}")

    assert len(program.souls) == 4
    soul_names = [s.name for s in program.souls]
    assert soul_names == ["Scout", "Quant", "Hunter", "Monitor"]
    print(f"✓ Souls: {soul_names}")

    scout = program.souls[0]
    assert scout.mind is not None
    assert scout.mind.model == "deepseek-r1"
    assert scout.mind.tier.value == "Tier1"
    assert scout.senses == ["gate_alpha_scan", "fetch_rsi", "ddgs_search"]
    assert scout.memory is not None and len(scout.memory.fields) == 3
    assert scout.instinct is not None and len(scout.instinct.statements) > 0
    assert scout.dna is not None and len(scout.dna.genes) == 3
    assert scout.heal is not None and len(scout.heal.rules) == 3
    print(f"✓ Scout: mind={scout.mind.model}@{scout.mind.tier.value}, "
          f"{len(scout.senses)} senses, {len(scout.memory.fields)} memory fields, "
          f"{len(scout.instinct.statements)} statements, {len(scout.dna.genes)} genes, "
          f"{len(scout.heal.rules)} heal rules")

    stmts = scout.instinct.statements
    assert isinstance(stmts[0], LetNode) and stmts[0].name == "tokens"
    assert stmts[0].value.get("kind") == "sense_call"
    print("✓ let tokens = sense gate_alpha_scan()")

    assert isinstance(stmts[1], LetNode) and stmts[1].name == "filtered"
    assert stmts[1].value.get("kind") == "method_call"
    print("✓ let filtered = tokens.where(...)")

    assert isinstance(stmts[2], ForNode) and stmts[2].var_name == "token"
    print("✓ for token in filtered { ... }")

    assert isinstance(stmts[3], RememberNode) and stmts[3].name == "scan_count" and stmts[3].op == "+="
    print("✓ remember scan_count += 1")

    quant = program.souls[1]
    quant_stmts = quant.instinct.statements
    assert isinstance(quant_stmts[0], LetNode)
    assert quant_stmts[0].value.get("kind") == "listen"
    assert quant_stmts[0].value["soul"] == "Scout"
    assert quant_stmts[0].value["type"] == "Signal"
    print("✓ let signal = listen Scout::Signal")

    for s in quant_stmts:
        if isinstance(s, SpeakNode):
            assert s.message_type == "Decision"
            action_val = s.args.get("action")
            assert isinstance(action_val, dict) and action_val.get("kind") == "inline_if"
            then_val = action_val["then"]
            assert isinstance(then_val, dict) and then_val.get("kind") == "string_lit"
            assert then_val["value"] == "BUY"
            print('✓ speak Decision(action: if ... { "BUY" } else { "HOLD" })')
            break

    assert program.nervous_system is not None
    route_nodes = [r for r in program.nervous_system.routes if isinstance(r, RouteNode)]
    pairs = [(r.source, r.target) for r in route_nodes]
    assert ("Scout", "Quant") in pairs
    assert ("Quant", "Hunter") in pairs
    assert ("Scout", "Monitor") in pairs
    print(f"✓ Nervous system: {len(program.nervous_system.routes)} routes")

    assert program.evolution is not None
    assert program.evolution.schedule == "3:00 AM"
    assert len(program.evolution.mutations) == 1
    print(f"✓ Evolution: schedule={program.evolution.schedule}, {len(program.evolution.mutations)} mutations")

    assert program.perception is not None and len(program.perception.rules) == 3
    print(f"✓ Perception: {len(program.perception.rules)} rules")

    print()
    print("=" * 50)
    print("ALL TESTS PASSED — LALR MIGRATION VERIFIED ✅")
    print("=" * 50)


def test_benchmark() -> None:
    from lark import Lark
    src = (NOUS_DIR / "gate_alpha.nous").read_text()
    grammar_lalr = (NOUS_DIR / "nous.lark").read_text()

    lalr = Lark(grammar_lalr, parser="lalr", start="start")

    N = 100
    t0 = time.perf_counter()
    for _ in range(N):
        lalr.parse(src)
    t_lalr = (time.perf_counter() - t0) / N

    print(f"\nBenchmark ({N} iterations):")
    print(f"  LALR: {t_lalr*1000:.2f}ms/parse")


if __name__ == "__main__":
    test_lalr_parse()
    test_benchmark()
