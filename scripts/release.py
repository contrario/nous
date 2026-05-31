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
# __session70_phase5b_step10_release_prep_v1__
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
PYTEST_FLOOR: int = 893  # __nous_n2b_floor_v1__  # __nous_run_shas_floor_v1__  # __nous_trace_recorder_floor_v1__  # __phase2_stage8_at_most_floor_v1__  # __phase2_stage7b_leads_to_floor_v1__  # __phase2_stage7a_never_after_floor_v1__  # __phase2_decouple_floor_v1__  # __phase2_stage1_skeleton_floor_v1__  # __session98_release_floor_stage1_anchored_v1__  # __session98_release_floor_stage2_v1__  # __session98_release_floor_stage1_v1__  # __session98_release_floor_v1__  # __session97_release_floor_v1__  # __session96_release_floor_v1__  # __session95_release_v5_12_0_floor_v1__  # __session93_release_v5_11_0_floor_v1__  # __session86_release_v5_8_1_floor_v1__  # __session86_release_v5_8_0_floor_v1__  # __session86_release_v5_7_1_floor_v1__  # __session85_release_v5_7_0_floor_v1__  # __session77_release_v5_2_0_release_script__  # __diff_side_provenance_v1__  # __cost_cap_floor_bump_v1__ + __cost_cap_phase3a_floor_v1__ + __cost_cap_phase3b_floor_v1__ + __cost_cap_phase3c_floor_v1__ + __cost_cap_phase4_floor_v1__  # __session69_smt_currency_consistency_floor_v1__  # __phase5b_floor_v1__  # __session80_release_v5_3_0_release_script__  # __nous_aetherproof_release_530_packaging_v1__  # __session81_release_v5_4_0_release_script__  # __session82_release_v5_5_0_release_script__  # __session88_release_v5_9_0_floor_v1__  # __phase2_stage2_events_floor_v1__  # __phase2_stage3_seq_floor_v1__  # __phase2_stage4_seq_floor_v1__  # __phase2_stage5_seq_floor_v1__  # __phase2_stage5b_floor_v1__  # __phase2_stage6_floor_v1__
TEMPLATE_FOR_SMOKE: str = "sycophancy_guard"
_ALLOW_EXISTING_TAG: bool = False  # __NERVE_DISPATCH_RELEASE_ALLOW_EXISTING_TAG_v1__
PYFLAKES_TARGETS: tuple[str, ...] = (
    "nous_api_server.py",
    "nous_api.py",
    "cli.py",
    "nous_runtime.py",
    "parser.py",
    "validator.py",
    "codegen.py",
)


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
        # __NERVE_DISPATCH_RELEASE_ALLOW_EXISTING_TAG_v1__
        if not _ALLOW_EXISTING_TAG:
            raise ReleaseError(
                f"tag {tag_name} already exists — bump _version.py first "
                "(or pass --allow-existing-tag for re-publish)"
            )
        head = run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).stdout.strip()
        tag_sha = run(
            ["git", "rev-list", "-n", "1", tag_name], cwd=REPO_ROOT,
        ).stdout.strip()
        if head != tag_sha:
            raise ReleaseError(
                f"--allow-existing-tag set but HEAD ({head[:8]}) does not "
                f"match tag {tag_name} ({tag_sha[:8]}) — refusing to publish "
                "a different commit under the same tag"
            )
        print(f"  OK: tag {tag_name} matches HEAD; re-publish allowed")
    else:
        print(f"  OK: clean tree, tag {tag_name} not yet present")
    return version


def phase_grammar_sync() -> None:
    print("\n[1/10] GRAMMAR SYNC")
    run(["python3", "scripts/sync_grammar.py"], cwd=REPO_ROOT)
    run(["python3", "-m", "pytest", "tests/test_grammar_sync.py", "-q"], cwd=REPO_ROOT)
    print("  OK")


def phase_pytest(skip: bool = False) -> None:
    print("\n[2/10] PYTEST FLOOR")
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
    print("\n[3/10] REGRESSION")
    result = run(["python3", "regression_harness.py", "verify"], cwd=REPO_ROOT)
    if "RESULT: OK" not in result.stdout:
        raise ReleaseError(f"regression failed:\n{result.stdout[-500:]}")
    print("  OK: 0 diffs")


def phase_version_consistency() -> None:
    print("\n[4/10] VERSION CONSISTENCY")
    run(
        ["python3", "-m", "pytest", "tests/test_version_consistency.py", "-q"],
        cwd=REPO_ROOT,
    )
    print("  OK")


def phase_pyflakes() -> None:
    print("\n[5/10] PYFLAKES (undefined names)")
    bad: list[str] = []
    for target in PYFLAKES_TARGETS:
        path: Path = REPO_ROOT / target
        if not path.is_file():
            raise ReleaseError(f"pyflakes target missing: {target}")
        result = subprocess.run(
            ["pyflakes", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in (result.stdout + result.stderr).splitlines():
            if "undefined name" in line:
                bad.append(line)
    if bad:
        for line in bad:
            print(f"  {line}")
        raise ReleaseError(f"{len(bad)} undefined name(s) in production sources")
    print(f"  OK: {len(PYFLAKES_TARGETS)} files clean")


def phase_build() -> tuple[Path, Path]:
    print("\n[6/10] BUILD")
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
    print("\n[7/10] WHEEL CONTENT GATE")
    z = zipfile.ZipFile(whl)
    names = z.namelist()
    required: list[str] = ["_version.py", "nous.lark", "grammar_data.py",
                            "skill_md.py", "dossier_spec.py",
                            "cli_dossier_spec.py",
                            "skill_export.py", "cli_skill_export.py",
                                "rekor_anchor.py",
                                "rekor_signing_config.py",  # __session86_rekor_signing_config_wheelgate_v1__
                                "rekor_entry.py",  # __session87_rekor_entry_wheelgate_v1__
                                "rekor_checkpoint.py",  # __session87_rekor_checkpoint_wheelgate_v1__
                                "rekor_verify_v2.py",  # __session87_rekor_verify_v2_wheelgate_v1__
                                "offline_verifier_builder.py",  # __session90_offline_verifier_builder_wheelgate_v1__
                                "rekor_anchor_v2.py",  # __session92_rekor_anchor_v2_wheelgate_v1__
                                "tsa_verify.py",  # __session92_tsa_verify_wheelgate_v1__
                                "tsa_client.py",  # __session92_tsa_client_wheelgate_v1__
                                "nous_trace.py",  # __session96_trace_wheelgate_v1__
                                "conformance.py",  # __session96_conformance_wheelgate_v1__
                                "conformance_verifier.py",  # __nous_conformance_verifier_wheelgate_v1__
                                "cli_conformance.py",  # __session96_cli_conformance_wheelgate_v1__
                                "trace_recorder.py",  # __nous_trace_recorder_wheelgate_v1__
                                "run_shas.py",  # __nous_run_shas_wheelgate_v1__
                                "cli_verify_sequence.py",
                                "compiled_trace.py",
                                "trace_anchor.py"]  # __s105_compiled_trace_wheelgate_v1__ __s105_trace_anchor_wheelgate_v1__  # __phase2_stage6_wheelgate_v1__
    missing: list[str] = [r for r in required if not any(n.endswith(r) for n in names)]
    if missing:
        raise ReleaseError(f"wheel missing files: {missing}")
    n_templates: int = sum(1 for n in names if n.endswith(".nous"))
    EXPECTED_TEMPLATES: int = 9  # __session67_template_count_v1__
    if n_templates != EXPECTED_TEMPLATES:
        raise ReleaseError(f"expected {EXPECTED_TEMPLATES} templates in wheel, got {n_templates}")
    meta_path: str = next(n for n in names if n.endswith("METADATA"))
    meta: str = z.read(meta_path).decode()
    expected: str = f"Version: {version}"
    if expected not in meta:
        raise ReleaseError(f"wheel METADATA missing {expected!r}")
    print(f"  OK: _version.py + nous.lark + grammar_data + {EXPECTED_TEMPLATES} templates + Version={version}")


def phase_install_smoke(whl: Path, version: str) -> None:
    print("\n[8/10] CLEAN-VENV INSTALL")
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

    print("\n[9/10] UX SMOKE")
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
        run([str(nous_bin), "verify", nous_file.name], cwd=td_path)  # __session90_phase9_verify_smoke_v1__
    print(f"  OK: {TEMPLATE_FOR_SMOKE} extract + compile + verify = exit 0")


def phase_upload(whl: Path, sdist: Path) -> None:
    print("\n[10/10] PYPI UPLOAD")
    if not TWINE_VENV.exists():
        raise ReleaseError(
            f"twine venv missing at {TWINE_VENV}; create with: "
            f"python3 -m venv {TWINE_VENV} && {TWINE_VENV}/bin/pip install twine packaging>=24.2"
        )
    twine = TWINE_VENV / "bin" / "twine"
    run([str(twine), "check", str(whl), str(sdist)])
    print("  twine check OK")
    # __session85_phase10_idempotent_v1__
    result = run(
        [str(twine), "upload", "--skip-existing", str(whl), str(sdist)],
        check=False,
    )
    combined = (result.stdout + result.stderr).lower()
    duplicate = (
        "already exists" in combined
        or "skipping" in combined
        or "this filename has already been used" in combined
    )
    if result.returncode != 0 and not duplicate:
        print(f"    stdout: {result.stdout[-500:]}")
        print(f"    stderr: {result.stderr[-500:]}")
        raise ReleaseError(
            f"twine upload failed (exit {result.returncode}); not a duplicate"
        )
    if duplicate:
        print(f"  OK: {whl.name} + {sdist.name} already on PyPI (idempotent)")
    else:
        print(f"  OK: uploaded {whl.name} + {sdist.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="NOUS atomic release pipeline")
    parser.add_argument("--check", action="store_true", help="dry-run through phase 4")
    parser.add_argument("--build", action="store_true", help="run through phase 8 (no upload)")
    parser.add_argument("--upload", action="store_true", help="full pipeline incl. PyPI upload")
    parser.add_argument("--skip-tests", action="store_true", help="emergency: skip pytest floor")
    parser.add_argument(
        "--allow-existing-tag", action="store_true",
        help="permit re-publish when tag already exists at HEAD",
    )
    args = parser.parse_args()
    global _ALLOW_EXISTING_TAG
    _ALLOW_EXISTING_TAG = bool(args.allow_existing_tag)

    if not (args.check or args.build or args.upload):
        parser.print_help()
        return 1

    try:
        version: str = phase_preflight()
        phase_grammar_sync()
        phase_pytest(skip=args.skip_tests)
        phase_regression()
        phase_version_consistency()
        phase_pyflakes()

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
# __session84_release_v5_6_0_version__
