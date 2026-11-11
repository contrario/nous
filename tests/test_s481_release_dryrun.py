"""S481 DR1: the release dry run is release.yml's build job, run by hand.

.github/workflows/release-dryrun.yml must run only on workflow_dispatch,
carry release.yml's build job byte for byte, hold no publish privilege,
and run, after the build job's own setup, release.py's phase 1 and phase
2 commands as release.py writes them. Read as text and by ast; stdlib
only. These tests evidence the file's shape; they do not run a workflow.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DRY = REPO / ".github" / "workflows" / "release-dryrun.yml"
REL = REPO / ".github" / "workflows" / "release.yml"
SCRIPT = REPO / "scripts" / "release.py"


def _lines(p: Path) -> list[str]:
    return p.read_text(encoding="ascii").split("\n")


def _job(lines: list[str], name: str) -> list[str]:
    i = lines.index("  %s:" % name)
    out = [lines[i]]
    for ln in lines[i + 1:]:
        if re.match(r"^  [A-Za-z_][A-Za-z0-9_-]*:$", ln) or re.match(r"^\S", ln):
            break
        out.append(ln)
    while out and out[-1] == "":
        out.pop()
    return out


def _jobs(lines: list[str]) -> list[str]:
    i = lines.index("jobs:")
    return [m.group(1) for ln in lines[i + 1:]
            for m in [re.match(r"^  ([A-Za-z_][A-Za-z0-9_-]*):$", ln)] if m]


def _steps(job: list[str]) -> list[list[str]]:
    k = job.index("    steps:")
    items: list[list[str]] = []
    for ln in job[k + 1:]:
        if ln.startswith("      - "):
            items.append([ln])
        elif items:
            items[-1].append(ln)
    return items


def _phase_cmds() -> list[str]:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    cmds: list[str] = []
    for fn in ("phase_grammar_sync", "phase_pytest"):
        f = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == fn][0]
        for c in ast.walk(f):
            if (isinstance(c, ast.Call) and getattr(c.func, "id", None) == "run"
                    and c.args and isinstance(c.args[0], ast.List)):
                cmds.append(" ".join(e.value for e in c.args[0].elts))
    return cmds


def test_dryrun_runs_only_by_hand() -> None:
    lines = _lines(DRY)
    i = lines.index("on:")
    block = []
    for ln in lines[i + 1:]:
        if ln and not ln.startswith(" "):
            break
        block.append(ln)
    assert [b for b in block if b.strip()] == ["  workflow_dispatch:"]


def test_dryrun_build_job_is_release_build_job() -> None:
    assert _job(_lines(DRY), "build") == _job(_lines(REL), "build")


def test_dryrun_holds_no_publish_privilege() -> None:
    text = "\n".join(ln for ln in _lines(DRY) if not ln.lstrip().startswith("#"))
    for tok in ("id-token", "attestations:", "environment:", "pypa/", "publish:"):
        assert tok not in text, tok
    lines = _lines(DRY)
    assert "permissions: {}" in lines
    assert _jobs(lines) == ["count", "build"]
    for name in _jobs(lines):
        job = _job(lines, name)
        k = job.index("    permissions:")
        perms = []
        for ln in job[k + 1:]:
            if not ln.startswith("      ") or ln.startswith("      - "):
                break
            perms.append(ln.strip())
        assert perms == ["contents: read"], (name, perms)


def test_dryrun_count_setup_is_build_setup() -> None:
    dry, rel = _lines(DRY), _lines(REL)
    count, build = _job(dry, "count"), _job(rel, "build")
    assert count[1:count.index("    steps:") + 1] == build[1:build.index("    steps:") + 1]
    assert _steps(count)[:3] == _steps(build)[:3]
    assert len(_steps(count)) == 4


def test_dryrun_count_step_runs_phase_1_and_2_as_written() -> None:
    cmds = _phase_cmds()
    assert len(cmds) == 3 and cmds[-1].startswith("python3 -m pytest tests/ ")
    last = _steps(_job(_lines(DRY), "count"))[3]
    body = [ln.strip() for ln in last[last.index("        run: |") + 1:] if ln.strip()]
    assert body == ["umask 022"] + cmds


def test_dryrun_actions_are_release_actions() -> None:
    rel = set(ln.strip() for ln in _lines(REL) if ln.strip().startswith("- uses: "))
    dry = [ln.strip() for ln in _lines(DRY) if ln.strip().startswith("- uses: ")]
    assert dry and all(u in rel for u in dry), dry
    assert all(re.search(r"@[0-9a-f]{40}\s", u + " ") for u in dry), dry
