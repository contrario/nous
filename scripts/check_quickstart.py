#!/usr/bin/env python3
"""Run the README quick start against an installed nous console script.

Seat S497 (W1). Reads the "## 60-second quick start" block of a README,
takes its "nous " lines up to the first "(Optional)" step, and runs each
one with the given --nous in a fresh temporary directory. The commands
get an environment of their own: PATH (the directory of --nous, then
/usr/bin and /bin), HOME (a temporary directory) and LANG. Nothing of
the caller's environment is passed: "nous verify --smt" writes a
signing key under $HOME/.local/share/nous/keys, and a release run must
not use or create one in the release operator's home.

Stops at the first step whose exit code is not 0. Checks, besides the
exit codes: the block has a "pip install" line naming nous-lang[smt]
(or [all]) when a step uses --smt; nous_prices.toml exists after
"prices init"; the output of "verify ... --smt" has a line starting
"PROVEN:" (a substring would also match "UNPROVEN"); a *_dossier_*
directory holding manifest.json exists after "dossier".

Exit 0 PASS, 1 FAIL, 2 usage or an unreadable README. It checks exit
codes, one verdict line and files, not the correctness of the program.

    python3 scripts/check_quickstart.py --nous VENV/bin/nous --readme README.md
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

HEADING = "## 60-second quick start"
_COMMENT = re.compile(r"\s+#.*$")
_PROVEN = re.compile(r"^\s*PROVEN:", re.MULTILINE)


def parse_readme(text: str) -> tuple[list[str], list[str]]:
    """Return (pip install lines, nous command lines) of the quick start."""
    lines = text.splitlines()
    if HEADING not in lines:
        raise ValueError("quick start heading not found: " + HEADING)
    i = lines.index(HEADING) + 1
    while i < len(lines) and not lines[i].startswith("```"):
        i += 1
    if i >= len(lines):
        raise ValueError("quick start code block not found")
    installs: list[str] = []
    commands: list[str] = []
    for raw in lines[i + 1:]:
        if raw.startswith("```"):
            break
        s = raw.strip()
        if s.startswith("#"):
            if "(Optional)" in s:
                break
            continue
        s = _COMMENT.sub("", s)
        if s.startswith("pip install"):
            installs.append(s)
        elif s.startswith("nous "):
            commands.append(s)
    else:
        raise ValueError("quick start code block not closed")
    if not commands:
        raise ValueError("quick start has no nous command")
    return installs, commands


def _installs_smt(installs: list[str]) -> bool:
    return any("nous-lang[smt]" in s or "nous-lang[all]" in s for s in installs)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--nous", required=True, help="path to the nous console script")
    ap.add_argument("--readme", required=True, help="README holding the quick start")
    ap.add_argument("--timeout", type=int, default=300, help="seconds per step")
    a = ap.parse_args(argv)
    nous = Path(a.nous).absolute()
    if not nous.is_file() or not os.access(nous, os.X_OK):
        print(f"QS ERROR not an executable file: {nous}")
        return 2
    try:
        raw = Path(a.readme).read_bytes()
        installs, commands = parse_readme(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as e:
        print(f"QS ERROR {e}")
        return 2
    print(f"QS README {a.readme} sha256 {hashlib.sha256(raw).hexdigest()[:16]} "
          f"COMMANDS {len(commands)}")
    for s in installs:
        print(f"QS INSTALL {s}")
    fails: list[str] = []
    if any("--smt" in shlex.split(c) for c in commands) and not _installs_smt(installs):
        print("QS CHECK install_smt no")
        fails.append("no pip install line naming nous-lang[smt] for a --smt step")
    with tempfile.TemporaryDirectory(prefix="nous-quickstart-") as td:
        home = Path(td) / "home"
        work = Path(td) / "work"
        home.mkdir()
        work.mkdir()
        env = {"PATH": f"{nous.parent}:/usr/bin:/bin", "HOME": str(home),
               "LANG": "C.UTF-8"}
        for n, c in enumerate(commands, 1):
            args = shlex.split(c)
            args[0] = str(nous)
            try:
                r = subprocess.run(args, cwd=work, env=env, capture_output=True,
                                   text=True, timeout=a.timeout,
                                   stdin=subprocess.DEVNULL)
                rc: object = r.returncode
                out = r.stdout + r.stderr
            except subprocess.TimeoutExpired:
                rc, out = "timeout", ""
            print(f"QS STEP {n} rc {rc} {c}")
            if rc != 0:
                for line in out.splitlines()[-3:]:
                    print(f"QS   | {line[:150]}")
                fails.append(f"step {n} rc {rc}")
                break
            words = args[1:]
            check = None
            if words[:2] == ["prices", "init"]:
                check = ("prices_file", (work / "nous_prices.toml").is_file())
            elif words[:1] == ["verify"] and "--smt" in words:
                check = ("proven_line", bool(_PROVEN.search(out)))
            elif words[:1] == ["dossier"]:
                check = ("dossier_dir", any(
                    p.is_dir() and (p / "manifest.json").is_file()
                    for p in work.glob("*_dossier_*")))
            if check is not None:
                print(f"QS CHECK {check[0]} {'yes' if check[1] else 'no'}")
                if not check[1]:
                    fails.append(f"step {n} {check[0]}")
                    break
    if fails:
        print("QUICKSTART FAIL: " + "; ".join(fails))
        return 1
    print("QUICKSTART PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
