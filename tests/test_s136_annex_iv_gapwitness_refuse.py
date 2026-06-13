"""S136 7.1: `nous dossier --annex-iv-map` is REFUSED on a gap-witness dossier.

Closes the only untested branch of the S135 Annex IV arc (axiom 8: no silent
merge across discriminators). An Annex IV evidence index over a coverage-gap-
witness -- a REFUTATION artifact -- is incoherent, so the emit path refuses
with a typed DossierError rather than indexing a refutation.

The fixture reuses the test_s134_gapw_e2e.py issue pattern: cmd_verify
--gap-witness on the AML governance source against a coverage threshold the
blocking net does NOT cover mints a signed gap-witness manifest plus a
sha-bound coverage.gapwitness.json. build_dossier(..., annex_iv_map=True) over
that manifest must raise (matched on the refuse message to pin THIS branch,
not any DossierError); without the flag it must build the gap-witness dossier
normally -- the positive control proving the refusal is flag-specific, not an
artifact of the gap-witness itself.

# __s136_annex_iv_gapw_refuse_test_v1__
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cli_verify import cmd_verify
from dossier import build_dossier, DossierError

TEMPLATE = Path(__file__).resolve().parent.parent / (
    "aml_transaction_governance.nous"
)

UNCOVERED_THRESHOLD = "amount > 5000"


class _Args:
    smt = True
    prices = None
    timeout_ms = 30000
    no_manifest = False
    smt_margin = 0
    no_lint = True
    lint_strict = False
    lint_error_on = None
    supersedes = None
    chain_coverage = None
    gap_witness = False
    coverage_threshold = None

    def __init__(self, **over: object) -> None:
        for k, v in over.items():
            setattr(self, k, v)


def _issue(tmp_path: Path) -> Path:
    src = tmp_path / "source.nous"
    src.write_bytes(TEMPLATE.read_bytes())
    mout = tmp_path / "source.manifest.json"
    args = _Args(
        file=str(src),
        manifest_out=str(mout),
        key_path=str(tmp_path / "signing.key"),
        coverage_threshold=UNCOVERED_THRESHOLD,
        gap_witness=True,
    )
    assert cmd_verify(args) == 0
    assert mout.is_file()
    assert (tmp_path / "coverage.gapwitness.json").is_file()
    return src


def test_annex_iv_map_refused_on_gap_witness_dossier(tmp_path: Path) -> None:
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src = _issue(tmp_path)
    with pytest.raises(
        DossierError, match="refused on a coverage-gap-witness"
    ):
        build_dossier(
            src,
            manifest=tmp_path / "source.manifest.json",
            output=tmp_path / "out",
            annex_iv_map=True,
        )


def test_gap_witness_dossier_builds_without_annex_iv_flag(
    tmp_path: Path,
) -> None:
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src = _issue(tmp_path)
    result = build_dossier(
        src,
        manifest=tmp_path / "source.manifest.json",
        output=tmp_path / "out",
    )
    assert "coverage.gapwitness.json" in result.files
    assert "annex_iv_map.json" not in result.files
    assert "verify_annex_iv_map.py" not in result.files
