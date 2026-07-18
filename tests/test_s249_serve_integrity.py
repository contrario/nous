"""Tracked-artifact + behavioural lock for the served-vs-mirror drift check.
__s249_serve_integrity_tracked_v1__

WHY THIS FILE EXISTS. scripts/served_mirror_check.py compares the served tree
(/var/www) against the tracked website/ mirror; infra/systemd/nous-serve-integrity.
{service,timer} run it every 30 min as a read-only, hardened oneshot. Neither the
timer being enabled nor the live /var/www matching the mirror is asserted here --
those are LIVE state a repository test cannot honestly claim. What this file locks:
(1) the checker still BEHAVES per its contract (rc 0 clean / 1 drift / 2 failed
measurement, the *.bak exclude, the empty-tree positive control), exercised on
fixtures through the same entrypoint the timer runs; and (2) the tracked units keep
their read-only, write-confined shape and still point at the real checker. The live
behavioural guarantee is the timer plus `systemctl --failed`, not this test.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_CHECKER = _REPO / "scripts" / "served_mirror_check.py"
_SERVICE = _REPO / "infra" / "systemd" / "nous-serve-integrity.service"
_TIMER = _REPO / "infra" / "systemd" / "nous-serve-integrity.timer"


def _run(src: Path, dst: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["SERVED_MIRROR_SRC"] = str(src)
    env["SERVED_MIRROR_DST"] = str(dst)
    return subprocess.run(
        [sys.executable, str(_CHECKER)],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def test_checker_clean_when_served_matches_mirror(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    (src / "index.html").write_text("X")
    (dst / "index.html").write_text("X")
    (dst / "extra.pdf").write_text("orphan")
    result = _run(src, dst)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RESULT: CLEAN" in result.stdout
    assert "orphan_served   extra.pdf" in result.stdout


def test_checker_flags_differ_missing_orphan_and_excludes_bak(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    (src / "sub").mkdir(parents=True)
    (dst / "sub").mkdir(parents=True)
    (src / "a.html").write_text("AAA")
    (dst / "a.html").write_text("AAA")
    (src / "sub" / "b.css").write_text("v1")
    (dst / "sub" / "b.css").write_text("v2")
    (src / "d.js").write_text("JS")
    (src / "old.bak").write_text("bak")
    (dst / "orphan.zip").write_text("Z")
    result = _run(src, dst)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "DIFFER          sub/b.css" in result.stdout
    assert "MISSING_SERVED  d.js" in result.stdout
    assert "orphan_served   orphan.zip" in result.stdout
    assert "tracked: 3" in result.stdout
    assert "compared: 2" in result.stdout


def test_checker_empty_mirror_is_failed_measurement(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    (dst / "only.html").write_text("Z")
    result = _run(src, dst)
    assert result.returncode == 2, result.stdout + result.stderr


def test_checker_missing_served_tree_is_failed_measurement(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "x.html").write_text("X")
    result = _run(src, tmp_path / "nonexistent")
    assert result.returncode == 2, result.stdout + result.stderr


def test_service_is_oneshot_and_runs_the_tracked_checker() -> None:
    text = _SERVICE.read_text(encoding="utf-8")
    assert "Type=oneshot" in text
    assert "scripts/served_mirror_check.py" in text
    assert _CHECKER.is_file(), "checker referenced by the unit is absent from the repo"


def test_service_is_read_only_write_confined() -> None:
    text = _SERVICE.read_text(encoding="utf-8")
    assert "ProtectSystem=strict" in text
    assert "NoNewPrivileges=yes" in text
    assert "ReadWritePaths=" not in text, "read-only probe must not declare ReadWritePaths"


def test_timer_is_scheduled_and_persistent() -> None:
    text = _TIMER.read_text(encoding="utf-8")
    assert "OnCalendar=" in text
    assert "Persistent=yes" in text
    assert "WantedBy=timers.target" in text
