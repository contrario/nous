import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
CLAIM_LINT = REPO / "scripts" / "claim_lint.py"
CLAIMS = REPO / "claims.toml"

_BAD = (
    '"""Engine providing mathematical guarantees:\n'
    "1. Dependency Soundness - deadlock detection\n"
    "2. Liveness - every listener has a producer\n"
    "3. Reachability - every soul participates\n"
    "4. Memory Safety - remember targets exist\n"
    "5. Topology - distributed node coverage\n"
    '"""\n'
)
_GOOD = (
    '"""Engine that verifies:\n'
    "1. deadlock detection\n"
    "2. liveness of every listener\n"
    "3. reachability of every soul\n"
    "4. memory safety of targets\n"
    "5. topology coverage\n"
    '"""\n'
)


def _run(root: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLAIM_LINT), "--config", str(CLAIMS),
         "--root", str(root)],
        capture_output=True, text=True,
    )


def test_list_binding_catches_header_list_overclaim(tmp_path):
    (tmp_path / "m.py").write_text(_BAD, encoding="utf-8")
    r = _run(tmp_path)
    assert r.returncode != 0, r.stdout
    assert "list-object" in r.stdout, r.stdout


def test_list_binding_allows_honest_verb_header(tmp_path):
    (tmp_path / "m.py").write_text(_GOOD, encoding="utf-8")
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout
    assert "list-object" not in r.stdout, r.stdout
