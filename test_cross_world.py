"""NOUS Cross-World v2.0 — Validation Test"""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, "/opt/aetherlang_agents/nous")

from parser import parse_nous
from cross_world import CrossWorldChecker, print_cross_world_report
from formatter import format_nous

WORLD_A = '''
world AlphaWorld {
    law Budget = $1.00 per cycle
    heartbeat = 5m
}

message Signal {
    pair: string
    score: float
}

soul Scout {
    mind: deepseek-r1 @ Tier1
    senses: [scanner]
    memory { count: int = 0 }
    instinct {
        let data = sense scanner()
        speak Signal(pair: data.pair, score: data.score)
        speak @BetaWorld::Alert(level: "high", source: "AlphaWorld")
        remember count += 1
    }
}

nervous_system {
    Scout -> Scout
}
'''

WORLD_B = '''
world BetaWorld {
    law Budget = $0.50 per cycle
    heartbeat = 10m
}

message Alert {
    level: string
    source: string
}

message Report {
    summary: string
}

soul Monitor {
    mind: gpt-4o-mini @ Tier2
    senses: [logger]
    memory { alerts: int = 0 }
    instinct {
        let alert = listen @AlphaWorld::Scout::Signal
        speak Report(summary: alert.pair)
        remember alerts += 1
    }
}

nervous_system {
    Monitor -> Monitor
}
'''

WORLD_BAD = '''
world BadWorld {
    law Budget = $0.50 per cycle
}

soul Breaker {
    mind: gpt-4o @ Tier1
    senses: [test]
    memory { x: int = 0 }
    instinct {
        speak @NonExistent::Fake(data: "test")
        speak @AlphaWorld::Signal(pair: "BTC")
        speak @BetaWorld::Alert(wrong_field: "oops")
    }
}
'''


def test_parse_cross_world() -> bool:
    try:
        p = parse_nous(WORLD_A)
        cross_speaks = []
        for soul in p.souls:
            if soul.instinct:
                for stmt in soul.instinct.statements:
                    from ast_nodes import SpeakNode
                    if isinstance(stmt, SpeakNode) and stmt.target_world:
                        cross_speaks.append(f"@{stmt.target_world}::{stmt.message_type}")
        assert len(cross_speaks) == 1
        assert cross_speaks[0] == "@BetaWorld::Alert"
        print("  ✓ Parse cross-world speak: @BetaWorld::Alert")
        return True
    except Exception as e:
        print(f"  ✗ Parse cross-world: {e}")
        import traceback; traceback.print_exc()
        return False


def test_parse_cross_listen() -> bool:
    try:
        p = parse_nous(WORLD_B)
        from ast_nodes import LetNode
        cross_listens = []
        for soul in p.souls:
            if soul.instinct:
                for stmt in soul.instinct.statements:
                    if isinstance(stmt, LetNode) and isinstance(stmt.value, dict):
                        if stmt.value.get("kind") == "listen" and "world" in stmt.value:
                            cross_listens.append(f"@{stmt.value['world']}::{stmt.value['soul']}::{stmt.value['type']}")
        assert len(cross_listens) == 1
        assert cross_listens[0] == "@AlphaWorld::Scout::Signal"
        print("  ✓ Parse cross-world listen: @AlphaWorld::Scout::Signal")
        return True
    except Exception as e:
        print(f"  ✗ Parse cross-world listen: {e}")
        import traceback; traceback.print_exc()
        return False


def test_format_roundtrip() -> bool:
    try:
        formatted = format_nous(WORLD_A)
        assert "@BetaWorld::Alert" in formatted
        reparsed = parse_nous(formatted)
        from ast_nodes import SpeakNode
        found = False
        for soul in reparsed.souls:
            if soul.instinct:
                for stmt in soul.instinct.statements:
                    if isinstance(stmt, SpeakNode) and stmt.target_world == "BetaWorld":
                        found = True
        assert found
        print("  ✓ Format roundtrip: cross-world speak preserved")
        return True
    except Exception as e:
        print(f"  ✗ Format roundtrip: {e}")
        import traceback; traceback.print_exc()
        return False


def test_checker_valid() -> bool:
    try:
        checker = CrossWorldChecker()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".nous", delete=False) as f:
            f.write(WORLD_A); fa = f.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".nous", delete=False) as f:
            f.write(WORLD_B); fb = f.name
        checker.add_file(fa)
        checker.add_file(fb)
        result = checker.check()
        Path(fa).unlink(); Path(fb).unlink()
        assert result.ok, f"Expected pass, got errors: {[e.message for e in result.errors]}"
        assert result.cross_speaks >= 1
        assert result.cross_listens >= 1
        print(f"  ✓ Cross-world valid: {result.cross_speaks} speaks, {result.cross_listens} listens, 0 errors")
        return True
    except Exception as e:
        print(f"  ✗ Cross-world valid: {e}")
        import traceback; traceback.print_exc()
        return False


def test_checker_errors() -> bool:
    try:
        checker = CrossWorldChecker()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".nous", delete=False) as f:
            f.write(WORLD_A); fa = f.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".nous", delete=False) as f:
            f.write(WORLD_B); fb = f.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".nous", delete=False) as f:
            f.write(WORLD_BAD); fc = f.name
        checker.add_file(fa)
        checker.add_file(fb)
        checker.add_file(fc)
        result = checker.check()
        Path(fa).unlink(); Path(fb).unlink(); Path(fc).unlink()

        print()
        print_cross_world_report(result)
        print()

        error_codes = [e.code for e in result.errors]
        assert "CW002" in error_codes, "Expected CW002 (world not found)"
        assert "CW004" in error_codes, "Expected CW004 (missing fields)"
        print(f"  ✓ Cross-world errors detected: {error_codes}")
        return True
    except Exception as e:
        print(f"  ✗ Cross-world errors: {e}")
        import traceback; traceback.print_exc()
        return False


if __name__ == "__main__":
    print("NOUS Cross-World v2.0 — Validation")
    print("=" * 50)
    results = []
    results.append(test_parse_cross_world())
    results.append(test_parse_cross_listen())
    results.append(test_format_roundtrip())
    results.append(test_checker_valid())
    results.append(test_checker_errors())

    print()
    passed = sum(results)
    print(f"Results: {passed}/{len(results)}")
    if passed == len(results):
        print("✓ CROSS-WORLD v2 READY")
    else:
        print("✗ FAILURES")
        sys.exit(1)
