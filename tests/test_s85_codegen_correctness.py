"""test_s85_codegen_correctness.py

S85 v5.7.0 codegen-correctness coverage:
  - null/none literal -> None / is None / is not None
  - guard ... else <action> honored (sleep + speak before return)
  - undefined-name gate: refuses unbound names, silent on unused imports
  - release.py upload path retired (twine token path removed; publish CI-only)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parser import parse_nous_file  # noqa: E402
from codegen import (  # noqa: E402
    generate_python,
    check_undefined_names,
    assert_no_undefined_names,
    CodegenSemanticError,
)


def _compile_source(src: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".nous")
    try:
        os.write(fd, src.encode("utf-8"))
        os.close(fd)
        return generate_python(parse_nous_file(path))
    finally:
        os.unlink(path)


_BASE = """\
world W {{
    law cost_ceiling = $1.00 per cycle
    heartbeat = 15s
}}
message Alert {{ level: string }}
soul A {{
    mind: deepseek-v4-flash @ Tier1
    senses: [http_get]
    memory {{ n: int = 0 }}
    instinct {{
{body}
    }}
    heal {{ on error => retry(2, error) }}
}}
soul B {{
    mind: deepseek-v4-flash @ Tier1
    memory {{ m: int = 0 }}
    instinct {{
        let p = listen A::Alert
        remember m = m + 1
    }}
    heal {{ on error => retry(2, error) }}
}}
nervous_system {{ A -> B }}
"""


class TestNullLiteral:
    def test_not_equal_null_emits_is_not_none(self) -> None:
        body = (
            "        let x = sense http_get(url: \"u\")\n"
            "        guard x != null else sleep 5s\n"
            "        remember n = n + 1\n"
        )
        code = _compile_source(_BASE.format(body=body))
        assert "is not None" in code
        assert "!= null" not in code
        assert "!= None" not in code

    def test_equal_none_alias_emits_is_none(self) -> None:
        body = (
            "        let x = sense http_get(url: \"u\")\n"
            "        guard x == none else sleep 5s\n"
            "        remember n = n + 1\n"
        )
        code = _compile_source(_BASE.format(body=body))
        assert "is None" in code

    def test_null_never_leaks_as_name(self) -> None:
        body = (
            "        let x = sense http_get(url: \"u\")\n"
            "        guard x != null else sleep 5s\n"
            "        remember n = n + 1\n"
        )
        code = _compile_source(_BASE.format(body=body))
        assert check_undefined_names(code) == []


class TestGuardElse:
    def test_else_sleep_emitted_before_return(self) -> None:
        body = (
            "        let x = sense http_get(url: \"u\")\n"
            "        guard x != null else sleep 5s\n"
            "        remember n = n + 1\n"
        )
        code = _compile_source(_BASE.format(body=body))
        lines = code.splitlines()
        guard_idx = next(i for i, l in enumerate(lines) if "if not ((x is not None))" in l)
        window = "\n".join(lines[guard_idx:guard_idx + 4])
        assert "asyncio.sleep(HEARTBEAT_SECONDS * 5)" in window
        sleep_idx = next(i for i, l in enumerate(lines) if "asyncio.sleep(HEARTBEAT_SECONDS * 5)" in l)
        ret_idx = next(i for i, l in enumerate(lines[sleep_idx:], sleep_idx) if l.strip() == "return")
        assert sleep_idx < ret_idx

    def test_else_speak_emitted_before_return(self) -> None:
        body = (
            "        let x = sense http_get(url: \"u\")\n"
            "        guard x != null else speak Alert(level: \"HIGH\")\n"
            "        remember n = n + 1\n"
        )
        code = _compile_source(_BASE.format(body=body))
        assert "channels.send(\"A_Alert\", Alert(level=\"HIGH\"))" in code

    def test_guard_without_else_unchanged(self) -> None:
        body = (
            "        let x = sense http_get(url: \"u\")\n"
            "        guard x != null\n"
            "        remember n = n + 1\n"
        )
        code = _compile_source(_BASE.format(body=body))
        lines = code.splitlines()
        guard_idx = next(i for i, l in enumerate(lines) if "if not ((x is not None))" in l)
        assert lines[guard_idx + 1].strip() == "return"


class TestUndefinedNameGate:
    def test_gate_refuses_unbound_name(self) -> None:
        body = (
            "        let x = sense http_get(url: \"u\")\n"
            "        speak Alert(level: ghost_var)\n"
            "        remember n = n + 1\n"
        )
        code = _compile_source(_BASE.format(body=body))
        with pytest.raises(CodegenSemanticError) as exc:
            assert_no_undefined_names(code)
        assert "ghost_var" in str(exc.value)
        assert str(exc.value).startswith("undefined name")

    def test_gate_silent_on_unused_imports(self) -> None:
        code = (
            "import os\nimport sys\nimport json\nfrom typing import Any, Optional\n\n"
            "def f(x: int) -> int:\n    return x + 1\n"
        )
        assert check_undefined_names(code) == []
        assert_no_undefined_names(code)

    def test_gate_detects_undefined_local(self) -> None:
        code = "def f() -> int:\n    y = z\n    z = 1\n    return y\n"
        findings = check_undefined_names(code)
        assert any(name == "z" for (_ln, name, _cls) in findings)


class TestPhase10Idempotency:
    def test_release_upload_path_retired_no_twine(self) -> None:
        text = (ROOT / "scripts" / "release.py").read_text(encoding="utf-8")
        assert "__s175_p1_upload_refused_v1__" in text
        assert "def phase_upload" not in text
        assert "twine upload" not in text
        assert "--skip-existing" not in text
