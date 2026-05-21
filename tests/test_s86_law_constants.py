"""test_s86_law_constants.py

S86 B2: HEARTBEAT_SECONDS / COST_CEILING are emitted unconditionally,
including for world-less sources, so generated modules never reference
them as undefined names.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parser import parse_nous_file  # noqa: E402
from codegen import generate_python, check_undefined_names  # noqa: E402


def _gen(src: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".nous")
    try:
        os.write(fd, src.encode("utf-8"))
        os.close(fd)
        return generate_python(parse_nous_file(path))
    finally:
        os.unlink(path)


_WORLDLESS = """\
soul Solo {
    mind: deepseek-chat @ Tier1
    senses: [http_get]
    memory { n: int = 0 }
    instinct {
        let x = sense http_get(url: "u")
        sleep 3s
        remember n = n + 1
    }
    heal { on error => retry(2, error) }
}
nervous_system { Solo -> Solo }
"""

_WORLDED = """\
world W {
    law cost_ceiling = $1.00 per cycle
    heartbeat = 15s
}
soul Solo {
    mind: deepseek-chat @ Tier1
    senses: [http_get]
    memory { n: int = 0 }
    instinct {
        let x = sense http_get(url: "u")
        sleep 3s
        remember n = n + 1
    }
    heal { on error => retry(2, error) }
}
nervous_system { Solo -> Solo }
"""


class TestLawConstantsUnconditional:
    def test_worldless_emits_both_constants(self) -> None:
        code = _gen(_WORLDLESS)
        assert "HEARTBEAT_SECONDS =" in code
        assert "COST_CEILING =" in code

    def test_worldless_is_gate_clean(self) -> None:
        code = _gen(_WORLDLESS)
        assert check_undefined_names(code) == []

    def test_worldless_omits_world_only_lines(self) -> None:
        code = _gen(_WORLDLESS)
        assert "WORLD_NAME =" not in code
        assert "World Laws" not in code

    def test_worlded_still_emits_world_name_and_header(self) -> None:
        code = _gen(_WORLDED)
        assert "WORLD_NAME =" in code
        assert "World Laws" in code
        assert "HEARTBEAT_SECONDS =" in code
        assert "COST_CEILING =" in code

    def test_worlded_uses_declared_heartbeat(self) -> None:
        code = _gen(_WORLDED)
        assert "HEARTBEAT_SECONDS = 15" in code
