from __future__ import annotations
# __s106_cli_memory_tests_v1__
import hashlib
import json
from pathlib import Path

import cli


def _h(seed: bytes) -> str:
    return hashlib.sha256(seed).hexdigest()


def _run(argv: list[str]) -> int:
    args = cli.build_parser().parse_args(argv)
    return cli.cmd_memory(args)


def test_memory_init_and_idempotent(tmp_path: Path, capsys) -> None:
    w = _h(b"w")
    base = str(tmp_path)
    assert _run(["memory", "init", "--world", w, "--base-dir", base]) == 0
    out1 = capsys.readouterr().out
    assert "Initialized world" in out1
    assert "key_id:" in out1
    assert _run(["memory", "init", "--world", w, "--base-dir", base]) == 0
    out2 = capsys.readouterr().out
    assert "Already initialized" in out2


def test_memory_init_bad_hex_refuses(tmp_path: Path) -> None:
    assert _run(["memory", "init", "--world", "deadbeef", "--base-dir", str(tmp_path)]) == 1


def test_memory_append_uninitialized_refuses(tmp_path: Path) -> None:
    w = _h(b"noinit")
    s = _h(b"soul")
    x = _h(b"x")
    rc = _run([
        "memory", "append", "--world", w, "--soul", s,
        "--source-sha", x, "--manifest-sha", x, "--event-hash", x,
        "--outcome", "ok", "--trigger-kind", "manual", "--cost", "0",
        "--base-dir", str(tmp_path),
    ])
    assert rc == 1


def test_memory_append_verify_reindex(tmp_path: Path, capsys) -> None:
    w = _h(b"w")
    s = _h(b"soul")
    x = _h(b"x")
    base = str(tmp_path)
    assert _run(["memory", "init", "--world", w, "--base-dir", base]) == 0
    capsys.readouterr()
    append_argv = [
        "memory", "append", "--world", w, "--soul", s,
        "--source-sha", x, "--manifest-sha", x, "--event-hash", x,
        "--outcome", "ok", "--trigger-kind", "manual", "--cost", "0",
        "--base-dir", base,
    ]
    assert _run(append_argv) == 0
    assert "seq 0" in capsys.readouterr().out
    assert _run(append_argv) == 0
    assert "seq 1" in capsys.readouterr().out

    assert _run(["memory", "verify", "--world", w, "--base-dir", base]) == 0
    vout = capsys.readouterr().out
    assert "2 entries" in vout
    assert "snapshot" in vout

    assert _run(["memory", "verify", "--world", w, "--soul", s, "--base-dir", base]) == 0
    assert "2 entries" in capsys.readouterr().out

    db = str(tmp_path / "idx.db")  # __s106_testfix_reindex_v1__
    assert _run(["memory", "reindex", "--base-dir", base, "--db", db]) == 0


def test_memory_reindex_reports_ok(tmp_path: Path, capsys) -> None:
    w = _h(b"w")
    s = _h(b"soul")
    x = _h(b"x")
    base = str(tmp_path)
    _run(["memory", "init", "--world", w, "--base-dir", base])
    _run([
        "memory", "append", "--world", w, "--soul", s,
        "--source-sha", x, "--manifest-sha", x, "--event-hash", x,
        "--outcome", "ok", "--trigger-kind", "manual", "--cost", "0",
        "--base-dir", base,
    ])
    capsys.readouterr()
    db = str(tmp_path / "idx.db")
    assert _run(["memory", "reindex", "--base-dir", base, "--db", db]) == 0
    out = capsys.readouterr().out
    assert "Indexed 1 entries" in out
    assert "'ok': True" in out


def test_memory_verify_integrity_break_exit2(tmp_path: Path) -> None:
    w = _h(b"w")
    s = _h(b"soul")
    x = _h(b"x")
    base = str(tmp_path)
    _run(["memory", "init", "--world", w, "--base-dir", base])
    _run([
        "memory", "append", "--world", w, "--soul", s,
        "--source-sha", x, "--manifest-sha", x, "--event-hash", x,
        "--outcome", "ok", "--trigger-kind", "manual", "--cost", "0",
        "--base-dir", base,
    ])
    entry = tmp_path / "memory_log" / w / s / "entry_0.json"
    doc = json.loads(entry.read_text(encoding="utf-8"))
    doc["outcome"] = "tampered"
    entry.write_text(
        json.dumps(doc, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    assert _run(["memory", "verify", "--world", w, "--soul", s, "--base-dir", base]) == 2


def test_memory_no_action_usage(tmp_path: Path) -> None:
    assert _run(["memory"]) == 1
