"""
NOUS Test Suite — Natural Language Interface (P30)
====================================================
Tests: template generation, extraction, validation, edge cases.
"""
from __future__ import annotations

import sys

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


def test_1_simple_agent() -> None:
    print("\n═══ Test 1: Simple Agent ═══")
    from natural_lang import generate_from_description
    result = generate_from_description(
        "A web scraping agent that monitors prices",
        use_llm=False,
    )
    check("generation ok", result.ok, result.error or str(result.validation_errors))
    check("has source", len(result.source) > 0)
    check("has world", "world" in result.source)
    check("has soul", "soul" in result.source)
    check("has mind", "mind:" in result.source)
    check("has heal", "heal" in result.source)
    check("soul count >= 1", result.soul_count >= 1)
    check("parses cleanly", result.ok)


def test_2_pipeline_agent() -> None:
    print("\n═══ Test 2: Pipeline Agent ═══")
    from natural_lang import generate_from_description
    result = generate_from_description(
        "A pipeline that scans news, analyzes sentiment, and then sends alerts",
        use_llm=False,
    )
    check("generation ok", result.ok, result.error or str(result.validation_errors))
    check("multiple souls", result.soul_count >= 2, f"got {result.soul_count}")
    check("has messages", result.message_count >= 1, f"got {result.message_count}")
    check("has nervous_system", "nervous_system" in result.source)
    check("has routes", result.route_count >= 1, f"got {result.route_count}")


def test_3_multi_role_detection() -> None:
    print("\n═══ Test 3: Multi-Role Detection ═══")
    from natural_lang import generate_from_description
    result = generate_from_description(
        "Build a system with a Scanner agent that fetches data from APIs, "
        "an Analyzer agent that processes the results, "
        "and an Executor agent that takes action",
        use_llm=False,
    )
    check("generation ok", result.ok, result.error or str(result.validation_errors))
    check("has Scanner", "Scanner" in result.source)
    check("has Analyzer", "Analyzer" in result.source)
    check("has Executor", "Executor" in result.source)
    check("3 souls", result.soul_count == 3, f"got {result.soul_count}")


def test_4_extract_world_name() -> None:
    print("\n═══ Test 4: World Name Extraction ═══")
    from natural_lang import _extract_world_name
    check("MarketScanner", _extract_world_name("Market Scanner Bot") == "MarketScanner")
    check("fallback works", len(_extract_world_name("a simple bot")) > 0)
    check("capitalized", _extract_world_name("weather monitor")[0].isupper())


def test_5_extract_souls() -> None:
    print("\n═══ Test 5: Soul Extraction ═══")
    from natural_lang import _extract_souls
    souls = _extract_souls("A scanner that monitors prices and an analyzer that evaluates trends")
    names = [s[0] for s in souls]
    check("found souls", len(souls) >= 2, f"got {len(souls)}: {names}")

    souls2 = _extract_souls("simple chatbot")
    check("single soul fallback", len(souls2) >= 1)

    souls3 = _extract_souls("a pipeline that processes data and then filters and transforms")
    check("pipeline detection", len(souls3) >= 2, f"got {len(souls3)}")


def test_6_extract_messages() -> None:
    print("\n═══ Test 6: Message Extraction ═══")
    from natural_lang import _extract_messages
    souls = [("Scanner", "scan"), ("Analyzer", "analyze"), ("Executor", "execute")]
    messages = _extract_messages(souls)
    check("2 messages for 3 souls", len(messages) == 2)
    check("first is ScannerOutput", messages[0][0] == "ScannerOutput")
    check("second is AnalyzerOutput", messages[1][0] == "AnalyzerOutput")
    check("has fields", len(messages[0][1]) >= 2)


def test_7_code_extraction() -> None:
    print("\n═══ Test 7: Code Extraction ═══")
    from natural_lang import _extract_nous_code
    raw1 = '```nous\nworld Test {\n}\n```'
    check("strips backticks", _extract_nous_code(raw1) == "world Test {\n}")

    raw2 = "world Clean {\n    heartbeat = 5m\n}"
    check("passes clean code", _extract_nous_code(raw2) == raw2)

    raw3 = '```\nworld X {\n}\n```'
    check("generic backticks", "world X" in _extract_nous_code(raw3))


def test_8_validation_integration() -> None:
    print("\n═══ Test 8: Validation Integration ═══")
    from natural_lang import _validate_generated
    good = '''
world Valid {
    law cost = $0.10 per cycle
    heartbeat = 5m
}
message Ping { ts: float = 0.0 }
soul Worker {
    mind: claude-sonnet @ Tier0A
    instinct { speak Ping(ts: now()) }
    heal { on timeout => retry(1, fixed) }
}
'''
    ok, errors, warnings, info = _validate_generated(good)
    check("valid code passes", ok)
    check("no errors", len(errors) == 0)
    check("world name extracted", info["world"] == "Valid")

    bad = "this is not nous code at all {{{ }}}"
    ok2, errors2, _, _ = _validate_generated(bad)
    check("bad code fails", not ok2)
    check("has parse error", len(errors2) > 0)


def test_9_generated_code_compiles() -> None:
    print("\n═══ Test 9: Generated Code Compiles ═══")
    from natural_lang import generate_from_description
    from parser import parse_nous
    from codegen import generate_python
    import py_compile, tempfile, os

    result = generate_from_description(
        "A monitoring agent that checks server health and sends alerts",
        use_llm=False,
    )
    check("template generates", result.ok, str(result.validation_errors))
    if result.ok:
        program = parse_nous(result.source)
        code = generate_python(program)
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            tmp = f.name
        try:
            py_compile.compile(tmp, doraise=True)
            check("py_compile PASS", True)
        except py_compile.PyCompileError as e:
            check("py_compile PASS", False, str(e))
        finally:
            os.unlink(tmp)


def test_10_generated_code_verifies() -> None:
    print("\n═══ Test 10: Generated Code Verifies ═══")
    from natural_lang import generate_from_description
    from parser import parse_nous
    from verifier import verify_program

    result = generate_from_description(
        "A data pipeline with a collector that fetches market data and an analyzer that processes it",
        use_llm=False,
    )
    check("template generates", result.ok, str(result.validation_errors))
    if result.ok:
        program = parse_nous(result.source)
        vresult = verify_program(program)
        check("formal verification passes", vresult.ok, f"{len(vresult.errors)} errors")
        proven = len(vresult.proven)
        check("has proven properties", proven > 0, f"got {proven}")


def test_11_edge_cases() -> None:
    print("\n═══ Test 11: Edge Cases ═══")
    from natural_lang import generate_from_description

    result1 = generate_from_description("bot", use_llm=False)
    check("minimal desc works", result1.ok, str(result1.validation_errors))

    result2 = generate_from_description(
        "A very complex system with weather monitoring, price tracking, "
        "news scanning, email notifications, and database storage",
        use_llm=False,
    )
    check("complex desc works", result2.ok, str(result2.validation_errors))
    check("complex has multiple souls", result2.soul_count >= 2, f"got {result2.soul_count}")

    result3 = generate_from_description("Ένα σύστημα παρακολούθησης τιμών", use_llm=False)
    check("greek desc works", result3.ok, str(result3.validation_errors))


if __name__ == "__main__":
    print("═══════════════════════════════════════════")
    print("  NOUS P30 — Natural Language Interface Tests")
    print("═══════════════════════════════════════════")
    test_1_simple_agent()
    test_2_pipeline_agent()
    test_3_multi_role_detection()
    test_4_extract_world_name()
    test_5_extract_souls()
    test_6_extract_messages()
    test_7_code_extraction()
    test_8_validation_integration()
    test_9_generated_code_compiles()
    test_10_generated_code_verifies()
    test_11_edge_cases()
    print(f"\n{'═' * 45}")
    total = PASS + FAIL
    print(f"  Results: {PASS}/{total} passed")
    if FAIL == 0:
        print("  Status: ALL PASS ✓")
    else:
        print(f"  Status: {FAIL} FAILED ✗")
    print(f"{'═' * 45}")
    sys.exit(0 if FAIL == 0 else 1)
