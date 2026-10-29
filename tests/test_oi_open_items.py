"""OI: the open items after V3 (OI_PREDICTIONS.md): N10's wording of a
proven cost bound, the rejected-ideas entry for nous-trace, and the
three test names that counted files.

# __oi_open_items_tests_v1__
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

import smt_emit
import smt_verify
from parser import parse_nous
from pricing import load_pricing
from smt_emit import emit_smt

pytestmark = pytest.mark.usefixtures("dated_shipped_prices")

REPO = Path(__file__).resolve().parent.parent
PHRASE = "across all execution paths"
SCOPED = "for every admissible execution, at the declared token " \
         "estimates and prices."
# Records that quote what was printed or said at the time; left as
# written.
RECORDS = {
    "docs/COST_BOUND_DISPLAY_DESIGN.md": "quotes the output it measured",
    "docs/GLM_SUPERSESSION_DESIGN.md": "the ledger, append-only",
}


def _proven(margin: int) -> str:
    text = (REPO / "aml_transaction_governance.nous").read_text(
        encoding="utf-8")
    spec = emit_smt(parse_nous(text), load_pricing(), source_text=text,
                    margin_pct=margin)
    r = smt_verify.verify(spec, timeout_ms=30000)
    assert r.verdict == "proven"
    return smt_verify.format_verdict(r)


@pytest.mark.parametrize("margin", [0, 10])
def test_p1_proven_line_states_its_scope(margin):
    out = _proven(margin)
    line = next(ln for ln in out.splitlines() if ln.startswith("PROVEN:"))
    assert line.endswith(SCOPED), line
    assert PHRASE not in out, out


def _user_facing():
    yield REPO / "README.md"
    yield from sorted((REPO / "docs").glob("*.md"))
    yield from sorted((REPO / "website").glob("*.html"))


def test_p2_docs_do_not_drop_the_condition():
    found = []
    for f in _user_facing():
        rel = f.relative_to(REPO).as_posix()
        if rel in RECORDS:
            continue
        flat = " ".join(f.read_text(encoding="utf-8").split())
        if PHRASE in flat:
            found.append(rel)
    assert found == [], found
    for rel in RECORDS:
        assert (REPO / rel).is_file(), rel


def test_p3_smt_emit_docstring():
    flat = " ".join((smt_emit.__doc__ or "").split())
    assert PHRASE not in flat
    assert "declared token estimates and prices" in flat


def test_p4_rejected_ideas_r7():
    text = (REPO / "docs" / "REJECTED_IDEAS.md").read_text(encoding="utf-8")
    m = re.search(r"(?ms)^### R7 -- nous-trace.*?(?=^### |\Z)", text)
    assert m, "no R7 for nous-trace"
    block = " ".join(m.group(0).split())
    for field in ("- Idea:", "- Searches run:", "- Rejection reason:",
                  "- Revisit trigger:"):
        assert field in block, field
    assert "duplicates shipped work" in block
    assert "never" in block


def test_p5_no_test_name_counts_files():
    p = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "-p", "no:cacheprovider", "tests/test_dossier_coverage.py",
         "tests/test_dossier_spec_cli.py",
         "tests/test_s95_dossier_spec_rekor_v2_emit.py"],
        cwd=str(REPO), capture_output=True, text=True, timeout=300)
    ids = [ln for ln in p.stdout.splitlines() if "::" in ln]
    assert len(ids) > 3, p.stdout + p.stderr
    assert not [i for i in ids if "eight_files" in i], ids
