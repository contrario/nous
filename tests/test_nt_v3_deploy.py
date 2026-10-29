"""NT-GATE-1 V3 addendum 7 (F10): the deploy does not publish Python
bytecode written into website/ by a test run, and the served-mirror
check does not count it as missing; a served one stays visible.

# __nt_v3_classes_tests_v1__
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DEPLOY = REPO / "scripts" / "deploy_website.sh"
CHECK = REPO / "scripts" / "served_mirror_check.py"


def _rsync_opts() -> list:
    text = DEPLOY.read_text(encoding="utf-8")
    m = re.search(r"(?m)^RSYNC_OPTS=\((.*)\)\s*$", text)
    assert m, "RSYNC_OPTS line not found"
    return shlex.split(m.group(1))


def _tree(root: Path, files) -> Path:
    for rel in files:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x " + rel.encode("ascii") + b"\n")
    return root


def test_p1_deploy_excludes_bytecode():
    opts = _rsync_opts()
    assert "--exclude=__pycache__/" in opts, opts
    assert "--exclude=*.pyc" in opts, opts


@pytest.mark.skipif(shutil.which("rsync") is None, reason="no rsync")
def test_p2_rsync_with_the_script_options_skips_bytecode(tmp_path):
    src = _tree(tmp_path / "src", ["a.html", "v/__pycache__/m.cpython-312.pyc",
                                   "v/m.py"])
    dst = tmp_path / "dst"
    dst.mkdir()
    subprocess.run(["rsync"] + _rsync_opts() + [str(src) + "/", str(dst) + "/"],
                   check=True, capture_output=True)
    got = sorted(str(p.relative_to(dst)) for p in dst.rglob("*")
                 if p.is_file())
    assert got == ["a.html", "v/m.py"], got


def _check(src: Path, dst: Path):
    env = dict(os.environ, SERVED_MIRROR_SRC=str(src),
               SERVED_MIRROR_DST=str(dst))
    p = subprocess.run([sys.executable, "-I", "-B", str(CHECK)], env=env,
                       capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def test_p3_local_bytecode_is_not_missing_served(tmp_path):
    src = _tree(tmp_path / "src", ["a.html", "__pycache__/m.pyc"])
    dst = _tree(tmp_path / "dst", ["a.html"])
    (dst / "a.html").write_bytes((src / "a.html").read_bytes())
    rc, out, err = _check(src, dst)
    assert rc == 0, (rc, out, err)
    assert "missing_served: 0" in out, out


def test_p4_served_bytecode_stays_visible(tmp_path):
    src = _tree(tmp_path / "src", ["a.html"])
    dst = _tree(tmp_path / "dst", ["a.html", "__pycache__/m.pyc"])
    rc, out, err = _check(src, dst)
    assert rc == 0, (rc, out, err)
    assert "orphan_served   __pycache__/m.pyc" in out, out
