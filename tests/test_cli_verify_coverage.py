"""
CLI tests for `nous verify-coverage`.

# __nous_test_cli_verify_coverage_v1__
"""
from __future__ import annotations

import types
from pathlib import Path

from cli_verify_coverage import cmd_verify_coverage


NOUS_COVER = """world Desk {
  heartbeat = 1s
  policy High { kind: "dispute" signal: amount > 50 weight: 5.0 action: block }
}
"""

NOUS_GAP = """world Desk {
  heartbeat = 1s
  policy High { kind: "dispute" signal: amount > 100 weight: 5.0 action: block }
}
"""

NOUS_NONBLOCK = """world Desk {
  heartbeat = 1s
  policy Low { kind: "dispute" signal: amount > 1 weight: 1.0 action: log_only }
}
"""


def _args(file: Path, threshold: str) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        file=str(file), threshold=threshold, timeout_ms=30000
    )


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "f.nous"
    p.write_text(text, encoding="utf-8")
    return p


def test_cli_proven(tmp_path, capsys) -> None:
    p = _write(tmp_path, NOUS_COVER)
    rc = cmd_verify_coverage(_args(p, "amount > 50"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "PROVEN" in out


def test_cli_refuted_with_counterexample(tmp_path, capsys) -> None:
    p = _write(tmp_path, NOUS_GAP)
    rc = cmd_verify_coverage(_args(p, "amount > 50"))
    out = capsys.readouterr().out
    assert rc == 1
    assert "REFUTED" in out
    assert "counterexample" in out


def test_cli_refused_string_threshold(tmp_path) -> None:
    p = _write(tmp_path, NOUS_COVER)
    rc = cmd_verify_coverage(_args(p, 'region == "EU"'))
    assert rc == 3


def test_cli_no_blocking_policy(tmp_path) -> None:
    p = _write(tmp_path, NOUS_NONBLOCK)
    rc = cmd_verify_coverage(_args(p, "amount > 50"))
    assert rc == 3
