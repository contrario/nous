"""S228 guard: the reserved word "proven" is never RENDERED over static-check
output.

NOUS carries a dual axis on every VerificationItem:

  severity -- the legacy affirmative flag. "PROVEN" is set by prove(),
              verify(), estimate() AND report() alike, so a severity-PROVEN
              count is a count of STATIC CHECKS.
  tier     -- the honest axis: PROVEN / VERIFIED / ESTIMATED / REPORTED.
              Only the Z3/Farkas SMT leg is tier PROVEN
              (see test_verify_tier_routing).

Rendering the word "proven" off a SEVERITY count therefore prints "N proven"
over static checks. That is the overclaim the honest boundary forbids:
"proves" is reserved for the Z3 cost bound and Farkas certificates; every
other check evidences. S226 removed the same defect from index.html; S227
removed it from runtime.html; S228 removes it from the source.

These tests fail if a render site regrows the word, and they pin the one
legitimate rendered "proven" -- VerificationResult.summary() -- to the TIER
axis. They are guards, not behaviour tests: S228 relabels the render only and
must not alter the counted set.
"""
from __future__ import annotations

import inspect

import cli
import mitosis_engine
from verifier import VerificationResult


def test_cli_never_renders_proven_over_a_severity_count() -> None:
    src = inspect.getsource(cli)
    assert "} proven," not in src, (
        "cli.py renders the reserved word off a severity-PROVEN count; that "
        "count is a count of STATIC CHECKS, not of Z3/Farkas proofs"
    )
    assert "proven, {errors} errors" not in src


def test_cli_renders_the_static_checker_count_as_verified() -> None:
    src = inspect.getsource(cli)
    assert "{verified} verified, {errors} errors" in src
    assert "Verification: {verified} verified," in src


def test_cli_still_counts_the_same_severity_set() -> None:
    src = inspect.getsource(cli)
    assert src.count('i.severity == "PROVEN"') == 3, (
        "S228 relabels the RENDER only; the dream / immune / mitosis counts "
        "must still filter on the severity axis exactly as before"
    )


def test_mitosis_clone_admission_string_claims_no_proof() -> None:
    src = inspect.getsource(mitosis_engine)
    assert "proven, 0 errors" not in src, (
        "the clone-admission success string renders the reserved word over "
        "NousVerifier.verify(), which is the STATIC 4-tier checker; the clone "
        "gate is real and it RECORDS its verdict, it does not prove it"
    )
    assert "static checks passed, 0 errors" in src


def test_verifier_summary_renders_proven_off_the_tier_axis() -> None:
    result = VerificationResult()
    result.verify("VX001", "topology", "a static check")
    result.report("VX002", "topology", "a declared config value")
    line = result.summary()
    assert "0 proven" in line, (
        "summary() must count TIER PROVEN; a static check is never a proof"
    )
    assert "1 verified" in line
    assert "1 reported" in line
    assert len(result.proven) == 2, (
        "the severity axis is unchanged: both affirmative items still carry "
        "severity PROVEN (the legacy flag), which is why rendering the word "
        "off it is the defect"
    )
