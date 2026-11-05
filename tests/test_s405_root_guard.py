"""The repository-root conftest.py refuses a pytest run as root.

R1  With euid 0 the run exits 4 before any test module is imported, and
    stderr names the refusal.
R2  With a non-zero euid the same tree imports its test module and passes.
__s405_root_guard_v1__
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "conftest.py"
RUNNER = (
    "import os\n"
    "import sys\n"
    "import pytest\n"
    "euid = int(sys.argv[1])\n"
    "os.geteuid = lambda: euid\n"
    "sys.exit(pytest.main(['-q', '-p', 'no:cacheprovider', sys.argv[2]]))\n"
)
PROBE = (
    "from pathlib import Path\n"
    "\n"
    "Path(__file__).with_name('IMPORTED').write_text('1')\n"
    "\n"
    "\n"
    "def test_probe() -> None:\n"
    "    assert True\n"
)


def _tree(tmp_path: Path) -> Path:
    tree = tmp_path / "tree"
    tree.mkdir()
    shutil.copyfile(GUARD, tree / "conftest.py")
    (tree / "test_probe.py").write_text(PROBE)
    return tree


def _run(tree: Path, euid: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", RUNNER, str(euid), str(tree)],
        cwd=tree,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_r1_root_is_refused_before_any_test_module(tmp_path: Path) -> None:
    tree = _tree(tmp_path)
    done = _run(tree, 0)
    assert done.returncode == 4, done.stdout + done.stderr
    assert "REFUSED: pytest as root (euid 0)" in done.stderr
    assert not (tree / "IMPORTED").exists()


def test_r2_non_root_runs(tmp_path: Path) -> None:
    tree = _tree(tmp_path)
    done = _run(tree, 1000)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "1 passed" in done.stdout
    assert (tree / "IMPORTED").exists()
