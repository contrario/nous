"""test_s86_run_gate.py

S86 #3 -- the undefined-name gate is enforced by `nous run` (cmd_run),
not only `nous compile`. cmd_run executes the AST live (no codegen), so
the gate runs a throwaway codegen pass and refuses before execution.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cli  # noqa: E402

_UNBOUND = """\
world W {
    law cost_ceiling = $1.00 per cycle
    heartbeat = 15s
}
message Ping { v: string }
soul A {
    mind: deepseek-v4-flash @ Tier1
    senses: [http_get]
    memory { n: int = 0 }
    instinct {
        let x = sense http_get(url: "u")
        speak Ping(v: ghost_var)
        remember n = n + 1
    }
    heal { on error => retry(2, error) }
}
soul B {
    mind: deepseek-v4-flash @ Tier1
    memory { m: int = 0 }
    instinct {
        let p = listen A::Ping
        remember m = m + 1
    }
    heal { on error => retry(2, error) }
}
nervous_system { A -> B }
"""


def _write(src: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".nous")
    os.write(fd, src.encode("utf-8"))
    os.close(fd)
    return path


def _args(path: str) -> argparse.Namespace:
    return argparse.Namespace(
        file=path, hot=False, mode="dry-run", cycles=1, budget=0.33
    )


class TestRunGate:
    def test_run_refuses_unbound_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called = {"ran": False}

        def _boom(*a: object, **k: object) -> None:
            called["ran"] = True
            raise AssertionError("run_program must not execute on gate failure")

        import nous_ast_runner
        monkeypatch.setattr(nous_ast_runner, "run_program", _boom)

        path = _write(_UNBOUND)
        try:
            rc = cli.cmd_run(_args(path))
        finally:
            os.unlink(path)

        assert rc == 1
        assert called["ran"] is False
