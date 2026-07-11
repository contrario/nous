#!/usr/bin/env python3
"""
NOUS atomic release pipeline.

One command. Runs the full Appendix A ritual end-to-end with hard gates
between phases. Refuses to upload if any check fails. Designed to make
a Session-57-class incident structurally impossible.

Usage:
    python3 scripts/release.py --check         # dry-run, no upload
    python3 scripts/release.py --build         # build + verify wheel, no upload
    python3 scripts/release.py --build         # gates + build (CI uploads via Trusted Publisher)
    # publish: git tag vX.Y.Z && git push; CI release.yml does the upload

Phases:
    0. Pre-flight: working tree clean, on master, tag for current version
       does not already exist.
    1. Grammar sync: scripts/sync_grammar.py + tests/test_grammar_sync.py.
    2. Test floor: pytest must pass at the floor count.
    3. Regression: regression_harness.py verify == 0 diffs.
    4. Version consistency: tests/test_version_consistency.py == 6/6.
    5. Build: rm -rf build/ dist/ *.egg-info/ then python -m build.
    6. Wheel content gate: _version.py + nous.lark + grammar_data.py +
       all templates + METADATA Version=X.Y.Z.
    7. Clean-venv install: pip install <local-wheel> in fresh venv.
    8. UX smoke: nous templates extract + nous compile == exit 0.
    9. Upload: twine via /tmp/upload_venv.

Any failure aborts BEFORE upload. No partial PyPI publish.

# __cc_release_script_v1__
# __session70_phase5b_step10_release_prep_v1__
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import hashlib  # __s159_u2_provenance_imports_v1__
import json
import uuid
from datetime import datetime, timezone
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parent.parent  # __s162_p1_portable_repo_root_v1__
DIST_DIR: Path = REPO_ROOT / "dist"
TWINE_VENV: Path = Path("/tmp/upload_venv")
TEST_VENV: Path = Path("/tmp/release_test_venv")
PYTEST_FLOOR: int = 2507  # __s228_floor_2507_ci_portable__  # __s221_floor_2487_ci_portable__  # __s216_floor_2444_ci_portable__  # __s211_floor_2422_ci_portable__  # __s202_floor_2363_ci_portable__  # __s192_pce_floor_2327_ci_portable__  # __s183_continuity_floor_2211_ci_portable__  # __s181_attribution_reach_floor_2200_ci_portable__  # __s180_p5_checkpoint_verify_cli_floor_2190_ci_portable__  # __s179_p5_cosign_floor_2181_ci_portable__  # __s178_p3_checkpoint_leg_floor_2176_ci_portable__  # __s177_p2_continuity_cli_floor_2169__  # __s176_p2_continuity_floor_2154__  # __s175_p1b_floor_2126_ci_portable__  # __s175_g2_floor_2127__  # __s172_p2_floor_2125__  # __s172_p0b1_floor_2118__  # __s172_p0a_floor_2114__  # __s171_leg6c_floor_2109__  # __s171_leg4e_floor_2105__  # __s171_leg3_floor_2099__  # __s170_leg8_floor_2084__  # __s167_p3_floor_2052__  # __s166_floor_2045_ci_portable__  # __s166_floor_2046__  # __s163_floor_2019__  # __s163_floor_2020__  # __s159_u_floor_2003__  # __s158_u_floor_1981__  # __s157_u6_floor_1972__  # __s156_u6_floor_1930__  # __s155_u6_floor_1908__  # __s154_u4b_floor_1884__  # __s153_u2_6_floor_1862__  # __s152_u5_floor_1832__  # __s151_u5_floor_1817__  # __s151_u1_floor_1809__  # __s150_release_v5_49_0_floor__  # __s149_release_v5_48_0_floor__  # __s148_release_v5_47_0_floor__  # __s147_release_v5_46_0_floor__  # __s146_release_v5_45_0_floor__  # __s145_attestation_receipt_floor_v1__  # __s144_witnessed_run_trust_floor_v1__  # __s143_gated_kind_converse_floor_v1__  # __s142_release_v5_42_0_floor__  # __s141_release_v5_41_0_floor__  # __s140_release_v5_40_0_floor__  # __s138_release_v5_39_0_floor__  # __s135_release_v5_38_0_floor__  # __s134_release_v5_37_0_floor__  # __s132_release_v5_36_0_floor__  # __s127_release_v5_35_0_floor__  # __s126_release_v5_34_0_floor__  # __s125_release_v5_33_0_floor__  # __s124_release_v5_32_0_floor__  # __s123_boundary_pin_floor_v1__  # __s122_release_v5_31_0__  # __s121_release_v5_30_0__  # __s120_release_v5_29_0__  # __s118_release_v5_28_0_floor__  # __s116_release_v5_27_0_floor__  # __s114_coverage_floor_v1__  # __s112_release_v5_26_0_floor__  # __s107_phase1_consult_floor_v1__  # __s106_memory_cli_floor_v1__  # __nous_n2b_floor_v1__  # __nous_run_shas_floor_v1__  # __nous_trace_recorder_floor_v1__  # __phase2_stage8_at_most_floor_v1__  # __phase2_stage7b_leads_to_floor_v1__  # __phase2_stage7a_never_after_floor_v1__  # __phase2_decouple_floor_v1__  # __phase2_stage1_skeleton_floor_v1__  # __session98_release_floor_stage1_anchored_v1__  # __session98_release_floor_stage2_v1__  # __session98_release_floor_stage1_v1__  # __session98_release_floor_v1__  # __session97_release_floor_v1__  # __session96_release_floor_v1__  # __session95_release_v5_12_0_floor_v1__  # __session93_release_v5_11_0_floor_v1__  # __session86_release_v5_8_1_floor_v1__  # __session86_release_v5_8_0_floor_v1__  # __session86_release_v5_7_1_floor_v1__  # __session85_release_v5_7_0_floor_v1__  # __session77_release_v5_2_0_release_script__  # __diff_side_provenance_v1__  # __cost_cap_floor_bump_v1__ + __cost_cap_phase3a_floor_v1__ + __cost_cap_phase3b_floor_v1__ + __cost_cap_phase3c_floor_v1__ + __cost_cap_phase4_floor_v1__  # __session69_smt_currency_consistency_floor_v1__  # __phase5b_floor_v1__  # __session80_release_v5_3_0_release_script__  # __nous_aetherproof_release_530_packaging_v1__  # __session81_release_v5_4_0_release_script__  # __session82_release_v5_5_0_release_script__  # __session88_release_v5_9_0_floor_v1__  # __phase2_stage2_events_floor_v1__  # __phase2_stage3_seq_floor_v1__  # __phase2_stage4_seq_floor_v1__  # __phase2_stage5_seq_floor_v1__  # __phase2_stage5b_floor_v1__  # __phase2_stage6_floor_v1__
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
    # Force all child Python processes (incl. temp-venv wheels of any
    # version) to skip bytecode caching, preventing /tmp/__pycache__
    # .pyc orphans from conformance/verify subprocesses.
    _env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
        env=_env,
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
            ["python3", "-m", "pyflakes", str(path)],  # __s163_p5_pyflakes_m_v1__
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
                                "pce_anchor.py",  # __s191_pce_anchor_wheelgate_v1__
                                "tsa_verify.py",  # __session92_tsa_verify_wheelgate_v1__
                                "tsa_client.py",  # __session92_tsa_client_wheelgate_v1__
                                "nous_trace.py",  # __session96_trace_wheelgate_v1__
                                "conformance.py",  # __session96_conformance_wheelgate_v1__
                                "conformance_verifier.py",  # __nous_conformance_verifier_wheelgate_v1__
                                "cli_conformance.py",  # __session96_cli_conformance_wheelgate_v1__
                                "trace_recorder.py",  # __nous_trace_recorder_wheelgate_v1__
                                "run_shas.py",  # __nous_run_shas_wheelgate_v1__
                                "cost_farkas.py",  # __s168_cost_farkas_wheelgate_v1__
                                "run_identity.py",  # __s107_run_identity_wheelgate_v1__
                                "cli_verify_sequence.py",
                                "cli_verify_coverage.py",  # __s114_coverage_wheelgate_v1__
                                "cli_verify_cost.py",  # __s170_leg6a_verify_cost_wheelgate_v1__
                                "policy_coverage.py",  # __s114_policy_coverage_wheelgate_v1__
                                "coverage_farkas.py",  # __s115_farkas_v1__
                                "coverage_minilang.py",  # __s124_minilang_wheelgate_v1__
                                "attest_apr.py",  # __s145_u1_attest_apr_wheelgate_v1__
                                "keccak_lite.py",  # __s146_u1_keccak_lite_wheelgate_v1__
                                "ndec.py",  # __s147_u1_ndec_wheelgate_v1__
                                "cli_ndec.py",  # __s147_u3_cli_ndec_wheelgate_v1__
                                "verifier_registry.py",  # __s148_u1_verifier_registry_wheelgate_v1__
                                "glm_manifest.py",  # __s150_u1_glm_manifest_wheelgate_v1__
                                "decision_ledger.py",  # __s152_u1_decision_ledger_wheelgate_v1__
                                "vsa.py",  # __s157_u1_vsa_wheelgate_v1__
                                "vsa_verifier.py",  # __s157_u2_vsa_verifier_wheelgate_v1__
                                "cli_vsa.py",  # __s157_u3_cli_vsa_wheelgate_v1__
                                "cli_verify_release.py",  # __s167_p2_cli_verify_release_wheelgate_v1__
                                "compiled_trace.py",
                                "trace_anchor.py",
                                "memory_entry.py",
                                "memory_keyring.py",
                                "memory_store.py",
                                "memory_index.py",
                                "remedy_proof.py",  # __s112_release_v5_26_0_wheelgate__
                                "build_run_remedy.py",
                                "provenance.py",  # __s159_u1_provenance_wheelgate_v1__
                                "provenance_verifier.py",  # __s160_u2_provenance_verifier_wheelgate_v1__
                                "build_vsa.py",  # __s164_p3_u2_build_vsa_wheelgate_v1__
                                "rekor_v2_offline.py",  # __s166_p2_rekor_v2_offline_wheelgate_v1__
                                "mint_release_vsa.py",  # __s172_p0a_mint_release_vsa_wheelgate_v1__
                                "continuity_ledger.py",  # __s176_p1_continuity_ledger_wheelgate_v1__
                                "continuity_verifier.py",  # __s177_p1_continuity_verifier_wheelgate_v1__
                                "cli_continuity.py",  # __s177_p1_cli_continuity_wheelgate_v1__
                                "continuity_checkpoint.py",  # __s178_p1_continuity_checkpoint_wheelgate_v1__
                                "continuity_cosign.py",  # __s179_p1_continuity_cosign_wheelgate_v1__
                                "envelope.py",  # __s190_pce_envelope_wheelgate_v1__
                                "envelope_ledger.py",  # __s193_envelope_ledger_wheelgate_v1__
                                "envelope_witness.py",  # __s194_envelope_witness_wheelgate_v1__
                                "envelope_witness_producer.py",  # __s196_incd_envelope_witness_producer_wheelgate_v1__
                                "closure_ledger.py",  # __s205_closure_ledger_wheelgate_v1__
                                "closure_attestation.py",  # __s206_closure_attestation_wheelgate_v1__
                                "closure_witness.py",  # __s207_closure_witness_wheelgate_v1__
                                "santander_adapter.py",  # __s215_santander_adapter_wheelgate_v1__
                                "guardrails_adapter.py",  # __s219_guardrails_adapter_wheelgate_v1__
                                "llm_guard_adapter.py",  # __s219_llm_guard_adapter_wheelgate_v1__
                                "annex_iv_map.py"]  # __s135_annex_iv_map_wheelgate_v1__  # __s105_compiled_trace_wheelgate_v1__ __s105_trace_anchor_wheelgate_v1__ __s105_memory_entry_wheelgate_v1__ __s105_memory_keyring_wheelgate_v1__ __s105_memory_store_wheelgate_v1__ __s105_memory_index_wheelgate_v1__  # __phase2_stage6_wheelgate_v1__
    missing: list[str] = [r for r in required if not any(n.endswith(r) for n in names)]
    if missing:
        raise ReleaseError(f"wheel missing files: {missing}")
    n_templates: int = sum(1 for n in names if n.endswith(".nous"))
    EXPECTED_TEMPLATES: int = 12  # __session67_template_count_v1__
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


# __s175_p1_upload_refused_v1__ phase_upload (twine token path) retired;
# publishing is CI-only via .github/workflows/release.yml (Trusted Publisher).


# __s159_u2_provenance_phase_v1__
PROVENANCE_REPO_URI: str = "https://github.com/contrario/nous"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def phase_provenance(
    whl: Path,
    sdist: Path,
    version: str,
    *,
    started_on: str,
    anchor: bool = False,
    out_dir: Path = DIST_DIR,
    key_path: Path | None = None,
    git_commit: str | None = None,
    invocation_id: str | None = None,
    finished_on: str | None = None,
    anchor_fn: object | None = None,
) -> Path:
    print("\n[9b/10] SLSA PROVENANCE (build leg)")
    import provenance

    if git_commit is None:
        git_commit = run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).stdout.strip()
    if invocation_id is None:
        invocation_id = str(uuid.uuid4())
    if finished_on is None:
        finished_on = _now_utc()

    artifacts = [
        (whl.name, _file_sha256(whl)),
        (sdist.name, _file_sha256(sdist)),
    ]
    builder_versions = {"python": sys.version.split()[0]}
    for dep in ("build", "setuptools", "twine"):
        try:
            from importlib.metadata import version as _pkg_version

            builder_versions[dep] = _pkg_version(dep)
        except Exception:
            pass

    statement = provenance.build_provenance_statement(
        artifacts=artifacts,
        source_repo_uri=PROVENANCE_REPO_URI,
        git_commit=git_commit,
        version=version,
        ref="refs/tags/v" + version,
        started_on=started_on,
        finished_on=finished_on,
        invocation_id=invocation_id,
        build_script="scripts/release.py",
        builder_versions=builder_versions,
    )
    priv, pub, key_resolved = provenance.load_or_create_provenance_keypair(
        key_path
    )
    envelope = provenance.sign_provenance(statement, priv)

    out_dir.mkdir(parents=True, exist_ok=True)
    prov_path = out_dir / ("nous_lang-" + version + ".provenance.intoto.json")
    prov_path.write_text(
        json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    keyid = provenance.provenance_keyid(pub)
    print("  OK: " + prov_path.name)
    print("      builder keyid " + keyid[:16] + "... (" + str(key_resolved) + ")")
    print("      subjects: " + ", ".join(a[0] for a in artifacts))

    if anchor:
        canonical = provenance.statement_canonical_bytes(statement)
        if anchor_fn is None:
            from rekor_anchor_v2 import anchor_manifest_to_rekor_v2 as anchor_fn
        try:
            entry = anchor_fn(canonical)
        except Exception as exc:
            raise ReleaseError("rekor anchor failed: " + repr(exc))
        sidecar = {
            "provider": "sigstore-rekor-v2",
            "rekor_api_version": getattr(entry, "rekor_api_version", None),
            "log_id": getattr(entry, "log_id", None),
            "log_index": getattr(entry, "log_index", None),
            "body_b64": getattr(entry, "body_b64", None),
            "checkpoint_envelope": getattr(entry, "checkpoint_envelope", None),
            "inclusion_proof_hashes": list(
                getattr(entry, "inclusion_proof_hashes", []) or []
            ),
            "provenance_canonical_sha256": hashlib.sha256(canonical).hexdigest(),
        }
        rekor_path = out_dir / (
            "nous_lang-" + version + ".provenance.rekor.json"
        )
        rekor_path.write_text(
            json.dumps(sidecar, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print("      anchored: log_index " + str(sidecar["log_index"]))
    return prov_path


def main() -> int:
    parser = argparse.ArgumentParser(description="NOUS atomic release pipeline")
    parser.add_argument("--check", action="store_true", help="dry-run through phase 4")
    parser.add_argument("--build", action="store_true", help="run through phase 8 (no upload)")
    parser.add_argument("--upload", action="store_true", help="RETIRED: refuses; publish is CI-only (Trusted Publisher)")
    parser.add_argument("--skip-tests", action="store_true", help="emergency: skip pytest floor")
    parser.add_argument(
        "--allow-existing-tag", action="store_true",
        help="permit re-publish when tag already exists at HEAD",
    )
    parser.add_argument(
        "--anchor", action="store_true",
        help="emit and Rekor-anchor SLSA provenance (network; opt-in)",
    )  # __s159_u2_provenance_arg_v1__
    parser.add_argument(
        "--no-provenance", action="store_true",
        help="build + wheel-gate + install-smoke WITHOUT emitting the "
             "operator-key provenance leg (CI builds; key stays offline)",
    )  # __s161_u4_no_provenance_arg_v1__
    args = parser.parse_args()
    global _ALLOW_EXISTING_TAG
    _ALLOW_EXISTING_TAG = bool(args.allow_existing_tag)

    if not (args.check or args.build or args.upload):
        parser.print_help()
        return 1

    if args.upload:  # __s175_p1_upload_refused_v1__
        print(
            "REFUSED: --upload (twine token path) is retired. Publishing is "
            "CI-only via .github/workflows/release.yml (PyPI Trusted Publisher, "
            "OIDC; PEP 740 publish + SLSA build attestations)."
        )
        print("Canonical release:")
        print("  1) gates:  python3 scripts/release.py --check")
        print("  2) tag:    git tag vX.Y.Z && git push origin vX.Y.Z")
        print("  3) approve the 'pypi' environment in GitHub Actions")
        print("  4) anchor: python3 mint_release_vsa.py mint X.Y.Z")
        return 2

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

        prov_started = _now_utc()  # __s159_u2_provenance_started_v1__
        whl, sdist = phase_build()
        phase_wheel_gate(whl, version)
        phase_install_smoke(whl, version)
        if not args.no_provenance:  # __s161_u4_no_provenance_guard_v1__
            phase_provenance(
                whl, sdist, version, started_on=prov_started,
                anchor=bool(args.anchor),
            )  # __s159_u2_provenance_call_v1__
        else:
            print("\n[9b/10] SLSA PROVENANCE skipped (--no-provenance; "
                  "operator key not minted in this environment)")

        if args.build:
            print(f"\n[BUILD] artifacts ready: {whl.name} + {sdist.name}")
            print(f"        next: git tag v{version} && git push origin v{version}")
            print("        publish runs in CI via Trusted Publisher; approve "
                  "the 'pypi' environment to release")
            return 0

        raise ReleaseError(  # __s175_p1_upload_refused_v1__
            "unreachable: --upload is retired (refused before any phase runs)"
        )

    except ReleaseError as exc:
        print(f"\nABORT: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
# __session84_release_v5_6_0_version__
