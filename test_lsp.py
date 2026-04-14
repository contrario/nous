"""
NOUS Test Suite — LSP Code Actions (P25)
==========================================
Tests: diagnostics, code actions, hover, edge cases.
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


def test_1_diagnostics_on_errors() -> None:
    print("\n═══ Test 1: Diagnostics Detection ═══")
    from lsp_server import NousDiagnostics
    from pathlib import Path
    source = Path("test_lsp_errors.nous").read_text()
    engine = NousDiagnostics()
    diags = engine.compute("file://test.nous", source)
    codes = [d.code for d in diags]
    check("has diagnostics", len(diags) > 0, f"got {len(diags)}")
    check("W001 no world", "W001" in codes)
    check("S002 no mind (Broken)", "S002" in codes)
    check("S003 no heal", "S003" in codes)
    check("T001 undefined message (FakeMessage)", "T001" in codes)
    check("N002 undefined soul ref (Reciver)", "N002" in codes)


def test_2_code_actions_generated() -> None:
    print("\n═══ Test 2: Code Actions Generated ═══")
    from lsp_server import NousDiagnostics, NousCodeActions
    from pathlib import Path
    source = Path("test_lsp_errors.nous").read_text()
    uri = "file://test.nous"
    d_engine = NousDiagnostics()
    a_engine = NousCodeActions()
    diags = d_engine.compute(uri, source)
    actions = a_engine.compute(uri, source, diags)
    titles = [a.title for a in actions]
    check("has actions", len(actions) > 0, f"got {len(actions)}")
    check("add world action", any("world" in t.lower() for t in titles))
    check("add mind action", any("mind" in t.lower() for t in titles))
    check("add heal action", any("heal" in t.lower() for t in titles))
    check("create message action", any("message" in t.lower() or "FakeMessage" in t for t in titles))
    check("did-you-mean or create soul", any("Reciver" in t or "Receiver" in t or "soul" in t.lower() for t in titles))


def test_3_code_action_edits_valid() -> None:
    print("\n═══ Test 3: Code Action Edits Valid ═══")
    from lsp_server import NousDiagnostics, NousCodeActions
    from pathlib import Path
    source = Path("test_lsp_errors.nous").read_text()
    uri = "file://test.nous"
    d_engine = NousDiagnostics()
    a_engine = NousCodeActions()
    diags = d_engine.compute(uri, source)
    actions = a_engine.compute(uri, source, diags)
    for action in actions:
        ad = action.to_dict()
        check(f"action '{action.title}' has edit", "edit" in ad)
        check(f"action '{action.title}' has changes", "changes" in ad.get("edit", {}))
        changes = ad.get("edit", {}).get("changes", {})
        for file_uri, edits in changes.items():
            for edit in edits:
                check("edit has range", "range" in edit)
                check("edit has newText", "newText" in edit)
                check("newText not empty", len(edit["newText"]) > 0)
        break


def test_4_clean_file_no_actions() -> None:
    print("\n═══ Test 4: Clean File — No Actions ═══")
    from lsp_server import NousDiagnostics, NousCodeActions
    source = '''
world Clean {
    law cost_ceiling = $0.10 per cycle
    heartbeat = 5m
}

message Ping {
    ts: float = 0.0
}

soul Worker {
    mind: claude-sonnet @ Tier0A
    senses: [http_get]
    memory {
        pings: int = 0
    }
    instinct {
        remember pings += 1
        speak Ping(ts: now())
    }
    heal {
        on timeout => retry(3, exponential)
    }
}
'''
    uri = "file://clean.nous"
    d_engine = NousDiagnostics()
    a_engine = NousCodeActions()
    diags = d_engine.compute(uri, source)
    errors = [d for d in diags if d.severity == 1]
    actions = a_engine.compute(uri, source, diags)
    check("no errors on clean file", len(errors) == 0, f"got {len(errors)} errors")
    check("no fix actions on clean file", len(actions) == 0, f"got {len(actions)} actions")


def test_5_hover_keywords() -> None:
    print("\n═══ Test 5: Hover Info ═══")
    from lsp_server import NousLSPServer
    server = NousLSPServer()
    source = '''
world Test {
    law x = $0.10 per cycle
    heartbeat = 5m
}
soul Worker {
    mind: claude-sonnet @ Tier0A
    heal {
        on timeout => retry(3, exponential)
    }
}
'''
    server._documents["file://t.nous"] = source
    keywords = ["soul", "world", "mind", "instinct", "heal", "speak", "listen", "topology"]
    for kw in keywords:
        info = server._get_hover_info(kw, source)
        check(f"hover '{kw}' returns info", info is not None and len(info) > 0)


def test_6_hover_soul_name() -> None:
    print("\n═══ Test 6: Hover Soul Name ═══")
    from lsp_server import NousLSPServer
    server = NousLSPServer()
    source = '''
world Test {
    law x = $0.10 per cycle
    heartbeat = 5m
}
message Ping {
    ts: float = 0.0
}
soul Scanner {
    mind: claude-sonnet @ Tier0A
    senses: [http_get]
    memory {
        count: int = 0
    }
    heal {
        on timeout => retry(3, exponential)
    }
}
'''
    server._documents["file://t.nous"] = source
    info = server._get_hover_info("Scanner", source)
    check("hover Scanner returns info", info is not None)
    if info:
        check("hover shows mind", "claude-sonnet" in info)
        check("hover shows senses", "http_get" in info)

    info2 = server._get_hover_info("Ping", source)
    check("hover Ping returns info", info2 is not None)
    if info2:
        check("hover shows fields", "ts" in info2)


def test_7_fix_map_coverage() -> None:
    print("\n═══ Test 7: Fix Map Coverage ═══")
    from lsp_server import NousCodeActions
    engine = NousCodeActions()
    expected_codes = ["W001", "S002", "S003", "S005", "N002", "T001", "T002", "TC001", "TC004", "TC005", "S004", "N001"]
    for code in expected_codes:
        check(f"FIX_MAP has {code}", code in engine.FIX_MAP)


def test_8_cli_check_mode() -> None:
    print("\n═══ Test 8: CLI Check Mode ═══")
    from lsp_server import check_file
    diags, actions = check_file("test_lsp_errors.nous")
    check("check_file returns diags", len(diags) > 0)
    check("check_file returns actions", len(actions) > 0)
    check("diags have code field", all("code" in d for d in diags))
    check("actions have title field", all("title" in a for a in actions))


if __name__ == "__main__":
    print("═══════════════════════════════════════════")
    print("  NOUS P25 — LSP Code Actions Tests")
    print("═══════════════════════════════════════════")
    test_1_diagnostics_on_errors()
    test_2_code_actions_generated()
    test_3_code_action_edits_valid()
    test_4_clean_file_no_actions()
    test_5_hover_keywords()
    test_6_hover_soul_name()
    test_7_fix_map_coverage()
    test_8_cli_check_mode()
    print(f"\n{'═' * 45}")
    total = PASS + FAIL
    print(f"  Results: {PASS}/{total} passed")
    if FAIL == 0:
        print("  Status: ALL PASS ✓")
    else:
        print(f"  Status: {FAIL} FAILED ✗")
    print(f"{'═' * 45}")
    sys.exit(0 if FAIL == 0 else 1)
