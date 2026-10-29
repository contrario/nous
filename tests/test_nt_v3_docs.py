"""NT-GATE-1 V3: the docs census. Every command line in the scanned docs
that runs an offline verifier in V3's scope carries --expect-signer and
runs Python isolated (python3 -I, addendum 8), except the named
exceptions, each with its reason; the exception set is exact, so a new
unpinned or unisolated command and a stale exception both fail.

# __nt_v3_classes_tests_v1__
"""
from __future__ import annotations

import re
from pathlib import Path

import ndec

REPO = Path(__file__).resolve().parent.parent
CMD = re.compile(
    r"python3?\s+(?:-\S+\s+)*\S*"
    r"verify_(?:offline|conformance_offline|vsa_offline|ndec)\.py")

# (file, stripped line) -> reason
EXCEPTIONS = {
    ("docs/VERIFYING_A_RELEASE.md", "python3 -I verify_vsa_offline.py"):
        "the served v1 vector, frozen; its verifier reads no arguments",
    ("docs/VSA_CONFORMANCE_VECTORS.md", "python3 -I verify_vsa_offline.py"):
        "the served v1 and v2 vectors, frozen; stated as taking no key",
    ("website/lending.html",
     '<div class="runline"><code>unzip loan_dossier_tampered.zip &amp;&amp;'
     ' cd loan_dossier &amp;&amp; python3 verify_offline.py</code></div>'):
        "the served demo zips carry their own pre-V3 verifiers",
}
LENDING_283 = "website/lending.html"


def _scanned():
    yield REPO / "README.md"
    yield from sorted((REPO / "docs").rglob("*.md"))
    yield from sorted((REPO / "website").glob("*.html"))
    yield from sorted((REPO / "website" / "docs").glob("*.html"))


def _unpinned():
    found = set()
    for f in _scanned():
        rel = f.relative_to(REPO).as_posix()
        for line in f.read_text(encoding="utf-8").splitlines():
            if CMD.search(line) and not (
                    "--expect-signer" in line and "python3 -I " in line):
                found.add((rel, line.strip()))
    return found


def test_d1_every_command_is_pinned_or_named():
    found = _unpinned()
    lending = {x for x in found if x[0] == LENDING_283
               and x not in EXCEPTIONS}
    assert len(lending) == 1, lending
    assert "loan_dossier.zip" in next(iter(lending))[1]
    assert found - lending == set(EXCEPTIONS), sorted(found - lending)


def test_d2_runtime_conformance_states_the_contract():
    flat = " ".join((REPO / "docs" / "RUNTIME_CONFORMANCE.md").read_text(
        encoding="utf-8").split())
    assert "--expect-manifest-signer" in flat
    assert "0 PASS, 1 INTEGRITY" in flat
    assert "the verifier gives no PASS without it" in flat


def test_d3_verify_dossier_names_the_texts_that_exist():
    text = (REPO / "docs" / "VERIFY_DOSSIER.md").read_text(encoding="utf-8")
    flat = " ".join(text.split())
    assert "VERIFY_OFFLINE_PY_HYBRID" not in text
    assert "--allow-unanchored" in text
    assert "3 OUTSIDE" in flat
    annex = (REPO / "docs" / "ANNEX_IV_MAPPING.md").read_text(
        encoding="utf-8")
    assert "HYBRID" not in annex


def test_d4_ndec_readme_and_carried_text():
    assert "--expect-signer" in ndec.README_NDEC_TXT
    assert "1 = FAIL" not in ndec.README_NDEC_TXT
    assert "Usage: python3 -I verify_ndec.py --expect-signer BASE64" in \
        ndec.VERIFY_NDEC_PY
    doc = (REPO / "docs" / "NDEC_FORMAT.md").read_text(encoding="utf-8")
    assert "nous ndec verify <file>.ndec --expect-signer BASE64" in doc


def test_d5_marked_surfaces():
    for rel in ("docs/VERIFY_DOSSIER.md", "docs/RUNTIME_CONFORMANCE.md",
                "docs/NOUS_VSA.md", "docs/REKOR_ANCHOR.md",
                "docs/SKILL_MD_SIDECAR.md", "docs/SKILL_EXPORT.md",
                "docs/COVERAGE_PROOF.md", "docs/ANNEX_IV_MAPPING.md",
                "website/verify.html", "website/coverage.html"):
        text = (REPO / rel).read_text(encoding="utf-8")
        assert "__nt_v3_classes_docs_v1__" in text, rel
