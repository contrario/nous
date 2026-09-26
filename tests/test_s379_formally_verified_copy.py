"""S379: the docs positioning line no longer calls NOUS formally verified.

__s379_positioning_copy_v1__

docs/RESERVED_VERB_AUDIT_DESIGN.md 9.4, D379-1 to D379-3. The line
website/docs/index.html:206 said NOUS "is a formally-verified language and
runtime for governed agentic AI". What NOUS proves is the declared envelope,
with Z3 and Farkas certificates, which the next sentence of the same paragraph
states. The edit deletes the two words and adds none. "Formal Verification" as
the name of the verify stage stays under D376-10 and is not checked here.

The first three tests are red on the tree before the edit. The fourth is the
control of the scan in the third: it plants the phrase in strings built at run
time and must find them, and it checks that the scan covers README.md and the
docs page, so an empty scan result is trusted only after the scanner has been
shown to see the phrase where it looks. Assertions are on precomputed values.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "website" / "docs" / "index.html"
OLD = "is a formally-verified language and runtime for governed agentic AI."
NEW = "\") is a language and runtime for governed agentic AI."
SELF_DESCRIPTION = re.compile(r"is a formally[- ]verified", re.IGNORECASE)


def _scanned_files() -> list[Path]:
    return [ROOT / "README.md"] + sorted((ROOT / "website").rglob("*.html"))


def _self_description_hits(files: list[Path]) -> list[str]:
    hits: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            if SELF_DESCRIPTION.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{number}")
    return hits


def test_docs_positioning_line_drops_formally_verified() -> None:
    old_present = OLD in DOCS.read_text(encoding="utf-8")
    assert old_present is False


def test_docs_positioning_line_keeps_its_sentence() -> None:
    new_present = NEW in DOCS.read_text(encoding="utf-8")
    assert new_present is True


def test_no_shipped_page_calls_nous_formally_verified() -> None:
    hits = _self_description_hits(_scanned_files())
    assert hits == []


def test_scan_control_finds_a_planted_self_description() -> None:
    planted = ["NOUS " + "is a formally" + sep + "verified language" for sep in ("-", " ")]
    found = [bool(SELF_DESCRIPTION.search(line)) for line in planted]
    files = _scanned_files()
    covers = [ROOT / "README.md" in files, DOCS in files]
    assert found == [True, True]
    assert covers == [True, True]
