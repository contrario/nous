"""
NOUS Test Suite — WASM/JS Target (P27)
========================================
Tests: JS codegen, HTML builder, module output, CLI integration.
"""
from __future__ import annotations

import sys
from pathlib import Path

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        msg = f"  ✗ {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)


def test_1_js_codegen_basic() -> None:
    print("\n═══ Test 1: JS CodeGen Basic ═══")
    from parser import parse_nous_file
    from codegen_js import generate_javascript
    p = parse_nous_file("test_distributed.nous")
    js = generate_javascript(p)
    check("generates JS", len(js) > 0)
    check("has NousChannel class", "class NousChannel" in js)
    check("has NousRuntime class", "class NousRuntime" in js)
    check("has message classes", "class Signal" in js)
    check("has soul classes", "class Soul_Scanner" in js)
    check("has Soul_Analyzer", "class Soul_Analyzer" in js)
    check("has Soul_Executor", "class Soul_Executor" in js)
    check("has buildRuntime", "function buildRuntime" in js)
    check("has HEARTBEAT_MS", "HEARTBEAT_MS" in js)
    check("has COST_CEILING", "COST_CEILING" in js)
    check("has setInterval for heartbeat", "setInterval" in js)
    check("has fetch for sense", "fetch" in js)
    check("exports for Node.js", "module.exports" in js)
    check("window binding for browser", "window.nousRuntime" in js)


def test_2_js_soul_wake_strategies() -> None:
    print("\n═══ Test 2: JS Wake Strategies ═══")
    from parser import parse_nous_file
    from codegen_js import generate_javascript
    p = parse_nous_file("test_distributed.nous")
    js = generate_javascript(p)
    check("Scanner is HEARTBEAT", "// Scanner: HEARTBEAT" in js)
    check("Analyzer is LISTENER", "// Analyzer: LISTENER" in js)
    check("Executor is LISTENER", "// Executor: LISTENER" in js)


def test_3_js_channel_wiring() -> None:
    print("\n═══ Test 3: JS Channel Wiring ═══")
    from parser import parse_nous_file
    from codegen_js import generate_javascript
    p = parse_nous_file("test_distributed.nous")
    js = generate_javascript(p)
    check("Scanner_Signal channel", "Scanner_Signal" in js)
    check("Analyzer_Analysis channel", "Analyzer_Analysis" in js)
    check("rt.send for speak", "rt.send" in js or "this._rt.send" in js)
    check("rt.receive for listen", "rt.receive" in js or "this._rt.receive" in js)


def test_4_html_builder() -> None:
    print("\n═══ Test 4: HTML Builder ═══")
    from parser import parse_nous_file
    from wasm_builder import build_html
    p = parse_nous_file("test_distributed.nous")
    out = Path("/tmp/test_nous_wasm.html")
    result = build_html(p, out)
    check("HTML file created", result.exists())
    content = result.read_text()
    check("has DOCTYPE", "<!DOCTYPE html>" in content)
    check("has world name", "DistributedPipeline" in content)
    check("has soul cards", "Soul_Scanner" in content)
    check("has runtime log div", "nous-log" in content)
    check("has stop button", "nousStop" in content)
    check("has dark theme", "#0f172a" in content)
    check("has cycle counter", "total-cycles" in content)
    check("has script tag", "<script>" in content)
    check("file size > 5KB", result.stat().st_size > 5000)
    out.unlink()


def test_5_module_builder() -> None:
    print("\n═══ Test 5: Module Builder ═══")
    from parser import parse_nous_file
    from wasm_builder import build_module
    p = parse_nous_file("test_distributed.nous")
    out = Path("/tmp/test_nous.mjs")
    result = build_module(p, out)
    check("MJS file created", result.exists())
    content = result.read_text()
    check("has module.exports", "module.exports" in content)
    check("no HTML tags", "<html>" not in content)
    out.unlink()


def test_6_local_only_program() -> None:
    print("\n═══ Test 6: Local-Only Program ═══")
    from parser import parse_nous
    from codegen_js import generate_javascript
    source = '''
world Simple {
    law cost_ceiling = $0.05 per cycle
    heartbeat = 10s
}

message Ping {
    ts: float = 0.0
}

soul Pinger {
    mind: claude-sonnet @ Tier0A
    senses: [http_get]
    memory {
        count: int = 0
    }
    instinct {
        remember count += 1
        speak Ping(ts: now())
    }
    heal {
        on timeout => retry(2, exponential)
    }
}
'''
    js = generate_javascript(parse_nous(source))
    check("generates valid JS", len(js) > 100)
    check("Pinger is HEARTBEAT", "HEARTBEAT" in js)
    check("HEARTBEAT_MS = 10000", "10000" in js)
    check("has Ping class", "class Ping" in js)
    check("has Soul_Pinger", "class Soul_Pinger" in js)
    check("has count memory", "this.count = 0" in js)
    check("has remember count +=", "this.count +=" in js)
    check("has Date.now for now()", "Date.now()" in js)
    check("has retry heal", "retry" in js.lower() or "_r < 2" in js)


def test_7_no_regressions_python() -> None:
    print("\n═══ Test 7: Python CodeGen Unchanged ═══")
    from parser import parse_nous_file
    from codegen import generate_python
    import py_compile, tempfile, os
    p = parse_nous_file("test_distributed.nous")
    code = generate_python(p)
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        tmp = f.name
    try:
        py_compile.compile(tmp, doraise=True)
        check("Python codegen still passes py_compile", True)
    except py_compile.PyCompileError as e:
        check("Python codegen still passes py_compile", False, str(e))
    finally:
        os.unlink(tmp)
    check("Python code has DistributedRuntime", "DistributedRuntime" in code)


if __name__ == "__main__":
    print("═══════════════════════════════════════════")
    print("  NOUS P27 — WASM/JS Target Tests")
    print("═══════════════════════════════════════════")
    test_1_js_codegen_basic()
    test_2_js_soul_wake_strategies()
    test_3_js_channel_wiring()
    test_4_html_builder()
    test_5_module_builder()
    test_6_local_only_program()
    test_7_no_regressions_python()
    print(f"\n{'═' * 45}")
    total = PASS + FAIL
    print(f"  Results: {PASS}/{total} passed")
    if FAIL == 0:
        print("  Status: ALL PASS ✓")
    else:
        print(f"  Status: {FAIL} FAILED ✗")
    print(f"{'═' * 45}")
    sys.exit(0 if FAIL == 0 else 1)
