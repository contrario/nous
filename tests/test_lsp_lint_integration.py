"""Integration tests for LSP diagnostics from governance lint.
__lsp_lint_integration_tests_v1__
"""
from __future__ import annotations
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lsp_server import check_file


PASSED: list[str] = []
FAILED: list[tuple[str, str]] = []


def _check(name: str, condition: bool, detail: str) -> None:
    if condition:
        PASSED.append(name)
    else:
        FAILED.append((name, detail))


CLEAN_SRC = '''world CleanWorld {
    heartbeat = 1s
    policy Cost {
        kind: "llm.request"
        signal: cost > 0.5
        weight: 5.0
        action: log_only
    }
}
soul S {
    mind: test @ Tier0A
    senses: [http_get]
    memory { x: int = 0 }
    instinct { let y = x + 1 }
    heal {
        on timeout => retry(3, exponential)
        on api_error => retry(2, exponential)
        on budget_exceeded => hibernate until next_cycle
    }
}
'''

RESERVED_PREFIX_SRC = '''world ReservedWorld {
    heartbeat = 1s
    policy __private {
        kind: "llm.request"
        signal: cost > 0.5
        weight: 5.0
        action: log_only
    }
}
soul S {
    mind: test @ Tier0A
    senses: [http_get]
    memory { x: int = 0 }
    instinct { let y = x + 1 }
    heal {
        on timeout => retry(3, exponential)
        on api_error => retry(2, exponential)
        on budget_exceeded => hibernate until next_cycle
    }
}
'''

INJECT_NO_MESSAGE_SRC = '''world BadInject {
    heartbeat = 1s
    policy NoMsg {
        kind: "llm.request"
        signal: cost > 0.0
        weight: 5.0
        action: inject_message
    }
}
soul S {
    mind: test @ Tier0A
    senses: [http_get]
    memory { x: int = 0 }
    instinct { let y = x + 1 }
    heal {
        on timeout => retry(3, exponential)
        on api_error => retry(2, exponential)
        on budget_exceeded => hibernate until next_cycle
    }
}
'''


def _tmp(src: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".nous", delete=False) as fd:
        fd.write(src)
        return fd.name


def test_lsp_clean_file_has_no_lint_diagnostics() -> None:
    path = _tmp(CLEAN_SRC)
    try:
        diags, _ = check_file(path)
        lint_diags = [d for d in diags if d["source"] == "nous.lint"]
        _check("clean_no_lint", lint_diags == [], f"got={lint_diags}")
    finally:
        Path(path).unlink()


def test_lsp_reserved_prefix_emits_l010() -> None:
    path = _tmp(RESERVED_PREFIX_SRC)
    try:
        diags, _ = check_file(path)
        lint_diags = [d for d in diags if d["source"] == "nous.lint"]
        l010 = [d for d in lint_diags if d["code"] == "L010"]
        _check("l010_present", len(l010) == 1, f"got_lint={lint_diags}")
        if l010:
            _check("l010_severity_warning", l010[0]["severity"] == 2, f"sev={l010[0]['severity']}")
            _check("l010_line_nonzero", l010[0]["range"]["start"]["line"] > 0, f"line={l010[0]['range']['start']['line']}")
    finally:
        Path(path).unlink()


def test_lsp_inject_without_message_emits_l008() -> None:
    path = _tmp(INJECT_NO_MESSAGE_SRC)
    try:
        diags, _ = check_file(path)
        lint_diags = [d for d in diags if d["source"] == "nous.lint"]
        l008 = [d for d in lint_diags if d["code"] == "L008"]
        _check("l008_present", len(l008) == 1, f"got_lint={lint_diags}")
        if l008:
            _check("l008_severity_error", l008[0]["severity"] == 1, f"sev={l008[0]['severity']}")
    finally:
        Path(path).unlink()


def test_lsp_lint_source_label() -> None:
    path = _tmp(RESERVED_PREFIX_SRC)
    try:
        diags, _ = check_file(path)
        sources = {d["source"] for d in diags}
        _check("nous_lint_source_present", "nous.lint" in sources, f"sources={sources}")
    finally:
        Path(path).unlink()


def run_all() -> int:
    tests = [
        test_lsp_clean_file_has_no_lint_diagnostics,
        test_lsp_reserved_prefix_emits_l010,
        test_lsp_inject_without_message_emits_l008,
        test_lsp_lint_source_label,
    ]
    for t in tests:
        try:
            t()
        except Exception as exc:
            FAILED.append((t.__name__, f"exception: {exc!r}"))
    total = len(PASSED) + len(FAILED)
    if FAILED:
        print("=" * 60)
        print(f"LSP LINT INTEGRATION TESTS -- FAILED ({len(FAILED)}/{total})")
        for name, detail in FAILED:
            print(f"  FAIL {name}: {detail}")
        print("=" * 60)
        return 1
    print("=" * 60)
    print(f"LSP LINT INTEGRATION TESTS -- ALL GREEN ({len(PASSED)}/{total})")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
