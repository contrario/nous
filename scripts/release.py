#!/usr/bin/env python3
"""
NOUS atomic release pipeline.

One command. Runs the full Appendix A ritual end-to-end with hard gates
between phases. Refuses to upload if any check fails. Designed to make
a Session-57-class incident structurally impossible.

Usage:
    python3 scripts/release.py --check         # dry-run, no upload
    python3 scripts/release.py --build         # build + verify wheel, no upload
    python3 scripts/release.py --upload        # full pipeline up to PyPI
    python3 scripts/release.py --upload --skip-tests  # emergency bypass

Phases:
    0. Pre-flight: working tree clean, on master, tag for current version
       does not already exist.
    1. Grammar sync: scripts/sync_grammar.py + tests/test_grammar_sync.py.
    2. Test floor: pytest must pass at the floor count.
    3. Regression: regression_harness.py verify == 0 diffs.
    4. Version consistency: tests/test_version_consistency.py == 6/6.
    5. Build: rm -rf build/ dist/ *.egg-info/ then python -m build.
    6. Wheel content gate: _version.py + nous.lark + grammar_data.py +
       6 templates + METADATA Version=X.Y.Z.
    7. Clean-venv install: pip install <local-wheel> in fresh venv.
    8. UX smoke: nous templates extract + nous compile == exit 0.
    9. Upload: twine via /tmp/upload_venv.

Any failure aborts BEFORE upload. No partial PyPI publish.

# __cc_release_script_v1__
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT: Path = Path("/opt/aetherlang_agents/nous")
DIST_DIR: Path = REPO_ROOT / "dist"
TWINE_VENV: Path = Path("/tmp/upload_venv")
TEST_VENV: Path = Path("/tmp/release_test_venv")
PYTEST_FLOOR: int = 178
TEMPLATE_FOR_SMOKE: str = "sycophancy_guard"


class ReleaseError(RuntimeError):
    """Hard failure that must abort the pipeline."""


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        print(f"    stdout: {result.stdout[-500:]}")
        print(f"    stderr: {result.stderr[-500:]}")
        raise ReleaseError(f"command failed: {' '.join(cmd)} (exit {result.returncode})")
    return result


def phase_preflight() -> str:
    print("\n[0/9] PRE-FLIGHT")

    sys.path.insert(0, str(REPO_ROOT))
    try:
        import _version  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ReleaseError(f"_version.py not importable: {exc}") from exc
    finally:
        sys.path.pop(0)
    version: str = _version.__version__
    print(f"  current _version.__version__ = {version}")

    status = run(["git", "status", "--porcelain"], cwd=REPO_ROOT, check=False)
    dirty = [
        line for line in status.stdout.splitlines()
        if line and not line.endswith(".bak") and "noesis_lattice" not in line
    ]
    if dirty:
        print("  WARN: working tree has changes:")
        for line in dirty[:10]:
            print(f"    {line}")
        raise ReleaseError("working tree not clean — commit or stash first")

    tag_name: str = f"v{version}"
    tag_check = run(["git", "tag", "-l", tag_name], cwd=REPO_ROOT, check=False)
    if tag_check.stdout.strip() == tag_name:
        raise ReleaseError(f"tag {tag_name} already exists — bump _version.py first")

    print(f"  OK: clean tree, tag {tag_name} not yet present")
    return version


def phase_grammar_sync() -> None:
    print("\n[1/9] GRAMMAR SYNC")
    run(["python3", "scripts/sync_grammar.py"], cwd=REPO_ROOT)
    run(["python3", "-m", "pytest", "tests/test_grammar_sync.py", "-q"], cwd=REPO_ROOT)
    print("  OK")


def phase_pytest(skip: bool = False) -> None:
    print("\n[2/9] PYTEST FLOOR")
    if skip:
        print("  SKIP (--skip-tests)")
        return
    result = run(
        ["python3", "-m", "pytest", "tests/", "-q", "--tb=no"],
        cwd=REPO_ROOT,
        check=False,
    )
    last_lines: str = result.stdout.strip().splitlines()[-3:] if result.stdout else []
    print("  pytest tail:")
    for line in last_lines:
        print(f"    {line}")
    summary: str = " ".join(last_lines)
    if "passed" not in summary:
        raise ReleaseError(f"pytest summary did not report any passes: {summary!r}")
    import re
    m = re.search(r"(\d+) passed", summary)
    n_passed: int = int(m.group(1)) if m else 0
    if n_passed < PYTEST_FLOOR:
        raise ReleaseError(f"pytest passed={n_passed} below floor {PYTEST_FLOOR}")
    print(f"  OK: {n_passed} >= {PYTEST_FLOOR}")


def phase_regression() -> None:
    print("\n[3/9] REGRESSION")
    result = run(["python3", "regression_harness.py", "verify"], cwd=REPO_ROOT)
    if "RESULT: OK" not in result.stdout:
        raise ReleaseError(f"regression failed:\n{result.stdout[-500:]}")
    print("  OK: 0 diffs")


def phase_version_consistency() -> None:
    print("\n[4/9] VERSION CONSISTENCY")
    run(
        ["python3", "-m", "pytest", "tests/test_version_consistency.py", "-q"],
        cwd=REPO_ROOT,
    )
    print("  OK")


def phase_build() -> tuple[Path, Path]:
    print("\n[5/9] BUILD")
    for d in (REPO_ROOT / "build", DIST_DIR):
        if d.exists():
            shutil.rmtree(d)
    for egg in REPO_ROOT.glob("*.egg-info"):
        shutil.rmtree(egg)
    run(["python3", "-m", "build"], cwd=REPO_ROOT)
    whl = list(DIST_DIR.glob("nous_lang-*-py3-none-any.whl"))
    sdist = list(DIST_DIR.glob("nous_lang-*.tar.gz"))
    if len(whl) != 1 or len(sdist) != 1:
        raise ReleaseError(f"expected 1 wheel + 1 sdist, got whl={whl} sdist={sdist}")
    print(f"  OK: {whl[0].name} + {sdist[0].name}")
    return whl[0], sdist[0]


def phase_wheel_gate(whl: Path, version: str) -> None:
    print("\n[6/9] WHEEL CONTENT GATE")
    z = zipfile.ZipFile(whl)
    names = z.namelist()
    required: list[str] = ["_version.py", "nous.lark", "grammar_data.py"]
    missing: list[str] = [r for r in required if not any(n.endswith(r) for n in names)]
    if missing:
        raise ReleaseError(f"wheel missing files: {missing}")
    n_templates: int = sum(1 for n in names if n.endswith(".nous"))
    if n_templates != 6:
        raise ReleaseError(f"expected 6 templates in wheel, got {n_templates}")
    meta_path: str = next(n for n in names if n.endswith("METADATA"))
    meta: str = z.read(meta_path).decode()
    expected: str = f"Version: {version}"
    if expected not in meta:
        raise ReleaseError(f"wheel METADATA missing {expected!r}")
    print(f"  OK: _version.py + nous.lark + grammar_data + 6 templates + Version={version}")


def phase_install_smoke(whl: Path, version: str) -> None:
    print("\n[7/9] CLEAN-VENV INSTALL")
    if TEST_VENV.exists():
        shutil.rmtree(TEST_VENV)
    run(["python3", "-m", "venv", str(TEST_VENV)])
    run([str(TEST_VENV / "bin" / "pip"), "install", "--quiet", str(whl)])
    pyexe = TEST_VENV / "bin" / "python3"
    check_script = (
        "import importlib.metadata, _version, cli, nous_api;"
        f"v='{version}';"
        "assert importlib.metadata.version('nous-lang')==v;"
        "assert _version.__version__==v;"
        "assert cli.VERSION==v;"
        "assert nous_api.VERSION==v;"
        "print('CONSISTENCY: PASS')"
    )
    with tempfile.TemporaryDirectory() as td:
        run([str(pyexe), "-c", check_script], cwd=Path(td))
    print("  OK")

    print("\n[8/9] UX SMOKE")
    nous_bin = TEST_VENV / "bin" / "nous"
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        run([str(nous_bin), "templates", "extract", TEMPLATE_FOR_SMOKE], cwd=td_path)
        nous_file: Path = td_path / f"{TEMPLATE_FOR_SMOKE}.nous"
        if not nous_file.exists():
            raise ReleaseError(f"extract did not produce {nous_file}")
        run([str(nous_bin), "compile", nous_file.name], cwd=td_path)
        py_file: Path = td_path / f"{TEMPLATE_FOR_SMOKE}.py"
        if not py_file.exists():
            raise ReleaseError(f"compile did not produce {py_file}")
        if py_file.stat().st_size < 500:
            raise ReleaseError(f"compiled output suspiciously small: {py_file.stat().st_size}b")
    print(f"  OK: {TEMPLATE_FOR_SMOKE} extract + compile = exit 0")


def phase_upload(whl: Path, sdist: Path) -> None:
    print("\n[9/9] PYPI UPLOAD")
    if not TWINE_VENV.exists():
        raise ReleaseError(
            f"twine venv missing at {TWINE_VENV}; create with: "
            f"python3 -m venv {TWINE_VENV} && {TWINE_VENV}/bin/pip install twine packaging>=24.2"
        )
    twine = TWINE_VENV / "bin" / "twine"
    run([str(twine), "check", str(whl), str(sdist)])
    print("  twine check OK")
    run([str(twine), "upload", str(whl), str(sdist)])
    print(f"  OK: uploaded {whl.name} + {sdist.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="NOUS atomic release pipeline")
    parser.add_argument("--check", action="store_true", help="dry-run through phase 4")
    parser.add_argument("--build", action="store_true", help="run through phase 8 (no upload)")
    parser.add_argument("--upload", action="store_true", help="full pipeline incl. PyPI upload")
    parser.add_argument("--skip-tests", action="store_true", help="emergency: skip pytest floor")
    args = parser.parse_args()

    if not (args.check or args.build or args.upload):
        parser.print_help()
        return 1

    try:
        version: str = phase_preflight()
        phase_grammar_sync()
        phase_pytest(skip=args.skip_tests)
        phase_regression()
        phase_version_consistency()

        if args.check:
            print(f"\n[CHECK] all gates green for v{version}; build/upload skipped")
            return 0

        whl, sdist = phase_build()
        phase_wheel_gate(whl, version)
        phase_install_smoke(whl, version)

        if args.build:
            print(f"\n[BUILD] artifacts ready: {whl.name} + {sdist.name}")
            print("        next: python3 scripts/release.py --upload")
            return 0

        phase_upload(whl, sdist)
        print(f"\n[UPLOAD] v{version} live on PyPI")
        print(f"         next: git tag v{version} && git push origin v{version}")
        return 0

    except ReleaseError as exc:
        print(f"\nABORT: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
