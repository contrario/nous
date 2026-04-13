"""NOUS Formatter v1.0 — Validation Test"""
import sys
sys.path.insert(0, "/opt/aetherlang_agents/nous")

from formatter import format_nous, fmt_file
from parser import parse_nous

TEST_MESSY = '''
world   GateAlpha {
law CostCeiling=$0.10 per cycle
  law MaxLatency=30s
    law NoLiveTrading = true
    heartbeat=5m
}

  soul Scout {
  mind: deepseek-r1 @ Tier1
      senses: [gate_alpha_scan,fetch_rsi,ddgs_search]
    memory { signals: [Signal] = [], scan_count: int = 0 }
  instinct {
  let tokens = sense gate_alpha_scan()
        let filtered = tokens.where(volume_24h > 50000)
    for token in filtered {
          let rsi = sense fetch_rsi(pair: token.pair)
      guard rsi < 70
            speak Signal(pair: token.pair, score: token.composite_score, rsi: rsi, source: self)
    }
      remember scan_count += 1
  }
      dna { volume_threshold: 50000 ~ [10000, 200000] }
heal { on timeout => retry(2, exponential) }
}

  message Signal {
pair: string
    score: float
  rsi: float
      source: string
}

  nervous_system {
          Scout -> Monitor
}

test "basic" {
    assert true
}
'''

def test_format_messy() -> bool:
    try:
        formatted = format_nous(TEST_MESSY)
        print("── Formatted output ──")
        print(formatted)
        print("── End ──")

        reparsed = parse_nous(formatted)
        assert reparsed.world is not None
        assert reparsed.world.name == "GateAlpha"
        assert len(reparsed.world.laws) == 3
        assert len(reparsed.souls) == 1
        assert reparsed.souls[0].name == "Scout"
        assert len(reparsed.messages) == 1
        assert reparsed.nervous_system is not None
        assert len(reparsed.tests) == 1
        print("✓ Messy → formatted → reparsed: PASS")
        return True
    except Exception as e:
        print(f"✗ Format test: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_idempotent() -> bool:
    try:
        formatted1 = format_nous(TEST_MESSY)
        formatted2 = format_nous(formatted1)
        if formatted1 == formatted2:
            print("✓ Idempotent: PASS")
            return True
        else:
            print("✗ Idempotent: FAIL — second format differs")
            for i, (a, b) in enumerate(zip(formatted1.splitlines(), formatted2.splitlines())):
                if a != b:
                    print(f"  Line {i+1}:")
                    print(f"    1st: {a!r}")
                    print(f"    2nd: {b!r}")
                    break
            return False
    except Exception as e:
        print(f"✗ Idempotent: {e}")
        return False


def test_gate_alpha_file() -> bool:
    try:
        formatted, changed = fmt_file("/opt/aetherlang_agents/nous/gate_alpha.nous")
        reparsed = parse_nous(formatted)
        souls = [s.name for s in reparsed.souls]
        print(f"✓ gate_alpha.nous: {len(reparsed.souls)} souls {souls}, changed={changed}")
        return True
    except Exception as e:
        print(f"✗ gate_alpha.nous: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("NOUS Formatter v1.0 — Validation")
    print("=" * 50)

    results = []
    results.append(test_format_messy())
    results.append(test_idempotent())
    results.append(test_gate_alpha_file())

    print()
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} passed")
    if passed == total:
        print("✓ Formatter READY")
    else:
        print("✗ FAILURES")
        sys.exit(1)
