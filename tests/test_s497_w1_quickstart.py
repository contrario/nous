"""S497 W1: the README quick start runs on an installed wheel.

prices init finds the shipped defaults where a wheel puts them; compile
says SKIPPED when the undefined-name gate did not run; the quick start
check reads the README and runs its steps with an env of its own;
release.py installs [smt] and runs that check on the built wheel."""
import argparse
import ast
import importlib.util
import os
import stat
import sys
import tempfile
from pathlib import Path

import pytest

import cli
import cli_prices
import pricing

ROOT = Path(__file__).resolve().parent.parent
CQ_PATH = ROOT / "scripts" / "check_quickstart.py"
CMDS = [
    "nous prices init",
    "nous templates extract cost_cap_emit_demo",
    "nous verify cost_cap_emit_demo.nous --smt",
    "nous dossier cost_cap_emit_demo.nous",
]


def _cq():
    spec = importlib.util.spec_from_file_location("check_quickstart", CQ_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _layout(tmp_path, monkeypatch, beside, prefix):
    mod = tmp_path / "mod"
    pre = tmp_path / "prefix"
    work = tmp_path / "work"
    for d in (mod, pre, work):
        d.mkdir()
    body = b"# s497 shipped defaults\n"
    if beside:
        (mod / "pricing").mkdir()
        (mod / "pricing" / "defaults.toml").write_bytes(body)
    if prefix:
        (pre / "pricing").mkdir()
        (pre / "pricing" / "defaults.toml").write_bytes(body)
    monkeypatch.setattr(cli_prices, "__file__", str(mod / "cli_prices.py"))
    monkeypatch.setattr(pricing, "__file__", str(mod / "pricing.py"))
    monkeypatch.setattr(sys, "prefix", str(pre))
    monkeypatch.chdir(work)
    return work, body


def test_t1_prices_init_wheel_layout(tmp_path, monkeypatch):
    work, body = _layout(tmp_path, monkeypatch, beside=False, prefix=True)
    rc = cli_prices.cmd_prices_init(argparse.Namespace(force=False))
    assert rc == 0
    assert (work / "nous_prices.toml").read_bytes() == body


def test_t2_prices_init_nothing_shipped(tmp_path, monkeypatch):
    work, _ = _layout(tmp_path, monkeypatch, beside=False, prefix=False)
    rc = cli_prices.cmd_prices_init(argparse.Namespace(force=False))
    assert rc == 2
    assert not (work / "nous_prices.toml").exists()


def test_t3_prices_init_source_layout(tmp_path, monkeypatch):
    work, body = _layout(tmp_path, monkeypatch, beside=True, prefix=False)
    rc = cli_prices.cmd_prices_init(argparse.Namespace(force=False))
    assert rc == 0
    assert (work / "nous_prices.toml").read_bytes() == body


def _compile(tmp_path, monkeypatch, capsys):
    src = tmp_path / "g.nous"
    src.write_bytes((ROOT / "templates" / "sycophancy_guard.nous").read_bytes())
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    ns = argparse.Namespace(file=str(src), output=str(tmp_path / "g.py"),
                            node=None, target="python")
    rc = cli.cmd_compile(ns)
    return rc, capsys.readouterr().out


def test_t4_compile_gate_skipped_without_pyflakes(tmp_path, monkeypatch, capsys):
    for m in ("pyflakes", "pyflakes.api", "pyflakes.messages"):
        monkeypatch.setitem(sys.modules, m, None)
    rc, out = _compile(tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "undefined-name gate SKIPPED (pyflakes not installed)" in out
    assert "undefined-name gate PASS" not in out


def test_t5_compile_gate_pass_with_pyflakes(tmp_path, monkeypatch, capsys):
    pytest.importorskip("pyflakes.api")
    rc, out = _compile(tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "undefined-name gate PASS" in out
    assert "SKIPPED" not in out


def test_t6_readme_quick_start_parse():
    installs, cmds = _cq().parse_readme((ROOT / "README.md").read_text(encoding="utf-8"))
    assert installs == ["pip install 'nous-lang[smt]'"]
    assert cmds == CMDS


def test_t7_release_installs_smt_and_runs_the_check():
    src = (ROOT / "scripts" / "release.py").read_text(encoding="utf-8")
    fn = [n for n in ast.walk(ast.parse(src))
          if isinstance(n, ast.FunctionDef) and n.name == "phase_install_smoke"]
    assert len(fn) == 1
    body = ast.get_source_segment(src, fn[0])
    assert '"install", "--quiet", f"{whl}[smt]"' in body
    assert '"install", "--quiet", str(whl)' not in body
    assert '"check_quickstart.py"' in body
    assert '"--nous", str(nous_bin)' in body


FAKE = """#!/bin/sh
D=$(dirname "$0")
M=$(cat "$D/mode")
echo "HOME=$HOME" >> "$D/seen"
[ -n "$NOUS_S497_SENTINEL" ] && echo "SENTINEL" >> "$D/seen"
case "$1 $2" in
  "prices init") [ "$M" = failinit ] && exit 2; : > nous_prices.toml; exit 0;;
  "templates extract") [ "$M" = failextract ] && exit 3; : > "$3.nous"; exit 0;;
  "verify "*)
    [ "$M" = noproven ] && exit 0
    [ "$M" = unproven ] && { echo "UNPROVEN: total_cost unknown"; exit 0; }
    echo "PROVEN: total_cost <= cap"; exit 0;;
  "dossier "*) mkdir -p x_dossier_1 && : > x_dossier_1/manifest.json; exit 0;;
esac
exit 9
"""


def _fake(tmp_path, mode):
    d = tmp_path / "fakebin"
    d.mkdir(exist_ok=True)
    f = d / "nous"
    f.write_text(FAKE)
    f.chmod(f.stat().st_mode | stat.S_IXUSR)
    (d / "mode").write_text(mode)
    if (d / "seen").exists():
        (d / "seen").unlink()
    return f, d


def _run(tmp_path, mode, capsys):
    f, d = _fake(tmp_path, mode)
    rc = _cq().main(["--nous", str(f), "--readme", str(ROOT / "README.md")])
    seen = (d / "seen").read_text().splitlines() if (d / "seen").exists() else []
    return rc, capsys.readouterr().out, seen


def test_t8_runner_good(tmp_path, capsys):
    rc, out, seen = _run(tmp_path, "good", capsys)
    assert rc == 0
    assert out.rstrip().splitlines()[-1] == "QUICKSTART PASS"
    assert len(seen) == 4


def test_t9_runner_stops_at_failed_step(tmp_path, capsys):
    rc, out, seen = _run(tmp_path, "failinit", capsys)
    assert rc == 1
    assert "QS STEP 1 rc 2 nous prices init" in out
    assert "QUICKSTART FAIL" in out
    assert len(seen) == 1
    rc, out, seen = _run(tmp_path, "failextract", capsys)
    assert rc == 1
    assert "QS STEP 2 rc 3 nous templates extract cost_cap_emit_demo" in out
    assert "QUICKSTART FAIL" in out
    assert len(seen) == 2


def test_t10_runner_needs_a_proven_line(tmp_path, capsys):
    for mode in ("noproven", "unproven"):
        rc, out, _ = _run(tmp_path, mode, capsys)
        assert rc == 1, mode
        assert "QUICKSTART FAIL" in out, mode


def test_t11_runner_env_is_its_own(tmp_path, capsys, monkeypatch):
    caller_home = tmp_path / "callerhome"
    caller_home.mkdir()
    monkeypatch.setenv("HOME", str(caller_home))
    monkeypatch.setenv("NOUS_S497_SENTINEL", "1")
    rc, out, seen = _run(tmp_path, "good", capsys)
    assert rc == 0
    homes = {s for s in seen if s.startswith("HOME=")}
    assert len(homes) == 1
    h = homes.pop()[len("HOME="):]
    assert h != str(caller_home)
    assert Path(h).name == "home" and not Path(h).exists()
    assert "SENTINEL" not in seen
