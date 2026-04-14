"""
NOUS Test Suite — Formal Verification (P29)
=============================================
Tests: resource bounds, deadlocks, protocol, liveness, reachability, memory, topology.
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


def test_1_clean_program_passes() -> None:
    print("\n═══ Test 1: Clean Program Passes ═══")
    from parser import parse_nous
    from verifier import verify_program
    source = '''
world Clean {
    law cost_ceiling = $0.10 per cycle
    heartbeat = 5m
}
message Ping { ts: float = 0.0 }
soul A {
    mind: claude-sonnet @ Tier0A
    memory { count: int = 0 }
    instinct {
        remember count += 1
        speak Ping(ts: now())
    }
    heal { on timeout => retry(3, exponential) }
}
soul B {
    mind: claude-sonnet @ Tier0A
    memory { received: int = 0 }
    instinct {
        let msg = listen A::Ping
        remember received += 1
    }
    heal { on timeout => retry(3, exponential) }
}
nervous_system { A -> B }
'''
    p = parse_nous(source)
    result = verify_program(p)
    check("clean program ok", result.ok)
    check("has proven items", len(result.proven) > 0)
    check("no errors", len(result.errors) == 0)


def test_2_resource_bound_violation() -> None:
    print("\n═══ Test 2: Resource Bound Violation ═══")
    from parser import parse_nous
    from verifier import verify_program
    source = '''
world Cheap {
    law cost_ceiling = $0.0001 per cycle
    heartbeat = 5m
}
message X { v: int = 0 }
soul Expensive {
    mind: claude-sonnet @ Tier3
    senses: [http_get, http_post]
    instinct {
        let a = sense http_get(url: "http://a")
        let b = sense http_post(url: "http://b")
        let c = sense http_get(url: "http://c")
        let d = sense http_post(url: "http://d")
        let e = sense http_get(url: "http://e")
        speak X(v: 1)
    }
    heal { on timeout => retry(1, fixed) }
}
'''
    p = parse_nous(source)
    result = verify_program(p)
    codes = [i.code for i in result.errors]
    check("VR001 resource bound error", "VR001" in codes)


def test_3_deadlock_detection() -> None:
    print("\n═══ Test 3: Deadlock Detection ═══")
    from parser import parse_nous
    from verifier import verify_program
    source = '''
world CycleWorld {
    law cost_ceiling = $1.00 per cycle
    heartbeat = 5m
}
message M1 { v: int = 0 }
message M2 { v: int = 0 }
soul A {
    mind: claude-sonnet @ Tier0A
    instinct { speak M1(v: 1) }
    heal { on timeout => retry(1, fixed) }
}
soul B {
    mind: claude-sonnet @ Tier0A
    instinct { speak M2(v: 2) }
    heal { on timeout => retry(1, fixed) }
}
soul C {
    mind: claude-sonnet @ Tier0A
    instinct { speak M1(v: 3) }
    heal { on timeout => retry(1, fixed) }
}
nervous_system {
    A -> B
    B -> C
    C -> A
}
'''
    p = parse_nous(source)
    result = verify_program(p)
    codes = [i.code for i in result.errors]
    check("VD001 deadlock detected", "VD001" in codes)


def test_4_self_listen_deadlock() -> None:
    print("\n═══ Test 4: Self-Listen Deadlock ═══")
    from parser import parse_nous
    from verifier import verify_program
    source = '''
world SelfWorld {
    law cost_ceiling = $1.00 per cycle
    heartbeat = 5m
}
message Echo { v: string = "" }
soul Narcissus {
    mind: claude-sonnet @ Tier0A
    instinct {
        let msg = listen Narcissus::Echo
        speak Echo(v: "echo")
    }
    heal { on timeout => retry(1, fixed) }
}
'''
    p = parse_nous(source)
    result = verify_program(p)
    codes = [i.code for i in result.errors]
    check("VD002 self-listen detected", "VD002" in codes)


def test_5_protocol_mismatch() -> None:
    print("\n═══ Test 5: Protocol Mismatch ═══")
    from parser import parse_nous
    from verifier import verify_program
    source = '''
world Proto {
    law cost_ceiling = $1.00 per cycle
    heartbeat = 5m
}
message Foo { x: int = 0 }
message Bar { y: string = "" }
soul Sender {
    mind: claude-sonnet @ Tier0A
    instinct { speak Foo(x: 42) }
    heal { on timeout => retry(1, fixed) }
}
soul Receiver {
    mind: claude-sonnet @ Tier0A
    instinct {
        let msg = listen Sender::Bar
    }
    heal { on timeout => retry(1, fixed) }
}
nervous_system { Sender -> Receiver }
'''
    p = parse_nous(source)
    result = verify_program(p)
    codes = [i.code for i in result.errors]
    check("VP001 protocol mismatch", "VP001" in codes)


def test_6_no_entrypoint() -> None:
    print("\n═══ Test 6: No Entrypoint ═══")
    from parser import parse_nous
    from verifier import verify_program
    source = '''
world NoEntry {
    law cost_ceiling = $1.00 per cycle
    heartbeat = 5m
}
message M { v: int = 0 }
soul X {
    mind: claude-sonnet @ Tier0A
    instinct { speak M(v: 1) }
    heal { on timeout => retry(1, fixed) }
}
soul Y {
    mind: claude-sonnet @ Tier0A
    instinct { speak M(v: 2) }
    heal { on timeout => retry(1, fixed) }
}
nervous_system {
    X -> Y
    Y -> X
}
'''
    p = parse_nous(source)
    result = verify_program(p)
    deadlock_codes = [i.code for i in result.errors if i.category == "deadlock"]
    liveness_codes = [i.code for i in result.errors if i.category == "liveness"]
    check("VD001 or VL002 detected", "VD001" in deadlock_codes or "VL002" in liveness_codes)


def test_7_memory_safety() -> None:
    print("\n═══ Test 7: Memory Safety ═══")
    from parser import parse_nous
    from verifier import verify_program
    source = '''
world MemWorld {
    law cost_ceiling = $1.00 per cycle
    heartbeat = 5m
}
message P { v: int = 0 }
soul Safe {
    mind: claude-sonnet @ Tier0A
    memory { count: int = 0 }
    instinct {
        remember count += 1
        remember ghost_field = 42
        speak P(v: count)
    }
    heal { on timeout => retry(1, fixed) }
}
'''
    p = parse_nous(source)
    result = verify_program(p)
    codes = [i.code for i in result.errors]
    check("VM002 undefined memory field", "VM002" in codes)


def test_8_topology_verification() -> None:
    print("\n═══ Test 8: Topology Verification ═══")
    from parser import parse_nous_file
    from verifier import verify_program
    p = parse_nous_file("test_distributed.nous")
    result = verify_program(p)
    topo_items = [i for i in result.items if i.category == "topology"]
    check("topology checked", len(topo_items) > 0)
    proven_topo = [i for i in topo_items if i.severity == "PROVEN"]
    check("topology proven", len(proven_topo) > 0)
    cross_node = [i for i in topo_items if "Cross-node" in i.message]
    check("cross-node route detected", len(cross_node) > 0)


def test_9_gate_alpha_verification() -> None:
    print("\n═══ Test 9: gate_alpha Full Verification ═══")
    from parser import parse_nous_file
    from verifier import verify_program
    p = parse_nous_file("gate_alpha.nous")
    result = verify_program(p)
    check("gate_alpha verifies", result.ok, f"{len(result.errors)} errors")
    check("has proven items", len(result.proven) > 0)
    for item in result.proven:
        print(f"    {item}")


def test_10_compiler_nous_verification() -> None:
    print("\n═══ Test 10: compiler.nous Verification ═══")
    from parser import parse_nous_file
    from verifier import verify_program
    p = parse_nous_file("compiler.nous")
    result = verify_program(p)
    check("compiler.nous verifies", result.ok, f"{len(result.errors)} errors")
    check("has resource bounds proven", any(i.code == "VR001" and i.severity == "PROVEN" for i in result.items))
    check("has deadlock proven", any(i.code == "VD001" and i.severity == "PROVEN" for i in result.items))
    check("has liveness proven", any(i.code == "VL002" and i.severity == "PROVEN" for i in result.items))


if __name__ == "__main__":
    print("═══════════════════════════════════════════")
    print("  NOUS P29 — Formal Verification Tests")
    print("═══════════════════════════════════════════")
    test_1_clean_program_passes()
    test_2_resource_bound_violation()
    test_3_deadlock_detection()
    test_4_self_listen_deadlock()
    test_5_protocol_mismatch()
    test_6_no_entrypoint()
    test_7_memory_safety()
    test_8_topology_verification()
    test_9_gate_alpha_verification()
    test_10_compiler_nous_verification()
    print(f"\n{'═' * 45}")
    total = PASS + FAIL
    print(f"  Results: {PASS}/{total} passed")
    if FAIL == 0:
        print("  Status: ALL PASS ✓")
    else:
        print(f"  Status: {FAIL} FAILED ✗")
    print(f"{'═' * 45}")
    sys.exit(0 if FAIL == 0 else 1)
