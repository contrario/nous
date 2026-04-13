"""NOUS LALR Parser v2.0 — Validation Test"""
import sys
import time
sys.path.insert(0, "/opt/aetherlang_agents/nous")

from parser import parse_nous, _get_parser

GATE_ALPHA = '''
world GateAlpha {
    law CostCeiling = $0.10 per cycle
    law MaxLatency = 30s
    law NoLiveTrading = true
    law RequireApproval = true
    law MaxPositionSize = $500
    law MaxDailyLoss = $100
    heartbeat = 5m
}

soul Scout {
    mind: deepseek-r1 @ Tier1
    senses: [gate_alpha_scan, fetch_rsi, ddgs_search]
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

soul Monitor {
    mind: gpt-4o-mini @ Tier2
    senses: [ddgs_search]
    memory { alerts: [string] = [] }
    instinct {
        let signal = listen Scout::Signal
        let news = sense ddgs_search(query: signal.pair)
        if news.sentiment < 0 {
            speak Alert(pair: signal.pair, reason: news.summary, severity: "high")
        }
        remember alerts += signal.pair
    }
}

message Signal {
    pair: string
    score: float
    rsi: float
    source: string
}

message Alert {
    pair: string
    reason: string
    severity: string
}

nervous_system {
    Scout -> Monitor
}

test "scout parses" {
    assert true
}
'''

NOESIS_TEST = '''
noesis {
    lattice: "knowledge.lattice"
    oracle_threshold: 0.3
    auto_learn: true
    auto_evolve: false
    gap_tracking: true
}

world TestWorld {
    law Budget = $1.00 per cycle
    law MaxPos = $500
}

soul TestSoul {
    mind: gpt-4o @ Tier1
    senses: [test_tool]
    memory { count: int = 0 }
    instinct {
        let result = resonate "what is the best strategy"
        let data = sense test_tool(query: "test")
        remember count += 1
    }
}
'''

IMPORT_TEST = '''
import "utils.nous"
import stdlib_watcher

world ImportWorld {
    law Budget = $0.50 per cycle
}
'''

MAP_TEST = '''
world MapWorld {
    law Budget = $1.00 per cycle
}

soul MapSoul {
    mind: gpt-4o @ Tier1
    senses: [test_tool]
    memory { data: int = 0 }
    instinct {
        let config = %{name: "test", value: 42}
        let result = sense test_tool(key: "hello")
    }
}
'''

def run_test(name: str, source: str) -> bool:
    try:
        t0 = time.perf_counter()
        program = parse_nous(source)
        t1 = time.perf_counter()
        ms = (t1 - t0) * 1000
        print(f"  ✓ {name}: {ms:.1f}ms")

        if program.world:
            print(f"    world: {program.world.name}, {len(program.world.laws)} laws")
        if program.souls:
            print(f"    souls: {[s.name for s in program.souls]}")
        if program.messages:
            print(f"    messages: {[m.name for m in program.messages]}")
        if program.nervous_system:
            print(f"    routes: {len(program.nervous_system.routes)}")
        if program.noesis:
            print(f"    noesis: threshold={program.noesis.oracle_threshold}")
        if program.imports:
            print(f"    imports: {len(program.imports)}")
        if program.tests:
            print(f"    tests: {[t.name for t in program.tests]}")
        return True
    except Exception as e:
        print(f"  ✗ {name}: {e}")
        return False


def bench_cached(source: str, n: int = 100) -> None:
    _get_parser()
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        parse_nous(source)
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000)
    avg = sum(times) / len(times)
    mn = min(times)
    mx = max(times)
    print(f"  bench ({n} runs): avg={avg:.2f}ms min={mn:.2f}ms max={mx:.2f}ms")


if __name__ == "__main__":
    print("NOUS LALR Parser v2.0 — Validation")
    print("=" * 50)

    results = []
    results.append(run_test("gate_alpha", GATE_ALPHA))
    results.append(run_test("noesis", NOESIS_TEST))
    results.append(run_test("import", IMPORT_TEST))
    results.append(run_test("map_literals", MAP_TEST))

    print()
    print("Benchmark (cached parser):")
    bench_cached(GATE_ALPHA)

    print()
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} passed")

    if passed == total:
        print("✓ LALR v2.0 READY")
    else:
        print("✗ FAILURES — check errors above")
        sys.exit(1)
