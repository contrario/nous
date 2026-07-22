"""The rule that normative changes require a revision bump, made enforceable.

SPEC.md's document revision exists so that two readers holding the same version
string hold the same normative text. Commit 06bb321 changed a MUST to a SHOULD
without moving the revision, and the gap was found by review, not by anything
in the repo. The rule written afterwards ("normative strength change -> bump
revision + changelog entry") had the same weakness it was written about: no
mechanism held it true.

This pins the normative surface. Every line of SPEC.md carrying an RFC 2119
keyword is collected and hashed; the hash and the revision it belongs to are
recorded in spec_normative_baseline.json. Then:

  hash unchanged                      -> pass
  hash changed, revision unchanged    -> FAIL: the rule was broken
  hash changed, revision also changed -> FAIL: bump was correct, now record it

The third case fails on purpose. Updating the baseline is the act that records
"these normative sentences belong to that revision", and it should be a
deliberate line in a diff rather than an automatic side effect.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SPEC = _REPO / "trace" / "SPEC.md"
_BASELINE = Path(__file__).resolve().parent / "spec_normative_baseline.json"

_RFC2119 = re.compile(r"\b(MUST NOT|SHOULD NOT|MUST|SHOULD|MAY)\b")


def _revision(text: str) -> str:
    m = re.search(r"^\*\*Version:\*\*\s*(\S+)", text, re.M)
    assert m, "SPEC.md has no **Version:** line"
    return m.group(1)


def _normative_lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if _RFC2119.search(ln)]


def _normative_hash(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def test_normative_text_matches_its_recorded_revision():
    if not _SPEC.is_file():
        pytest.skip("SPEC.md not present")
    text = _SPEC.read_text(encoding="utf-8")
    rev = _revision(text)
    lines = _normative_lines(text)
    h = _normative_hash(lines)

    if not _BASELINE.is_file():
        pytest.fail(
            "no normative baseline recorded. Create %s with:\n"
            '  {"revision": "%s", "normative_sha256": "%s", "line_count": %d}'
            % (_BASELINE.name, rev, h, len(lines)))

    base = json.loads(_BASELINE.read_text(encoding="utf-8"))

    if h == base["normative_sha256"]:
        # unchanged; the revision must not have been bumped behind its back
        assert rev == base["revision"], (
            "the document revision moved (%s -> %s) but no normative sentence "
            "changed. If the bump was for non-normative edits, record it by "
            "updating %s." % (base["revision"], rev, _BASELINE.name))
        return

    if rev == base["revision"]:
        pytest.fail(
            "NORMATIVE TEXT CHANGED WITHOUT A REVISION BUMP.\n"
            "  revision:        %s (unchanged)\n"
            "  normative lines: %d -> %d\n"
            "  hash:            %s -> %s\n"
            "Two readers holding %s would hold different normative texts. "
            "Bump **Version:** in SPEC.md, add a 'Changes from ...' entry, then "
            "update %s."
            % (rev, base["line_count"], len(lines),
               base["normative_sha256"][:16], h[:16], rev, _BASELINE.name))

    pytest.fail(
        "normative text and revision both changed (%s -> %s), which is the "
        "correct sequence -- now record it. Update %s to:\n"
        '  {"revision": "%s", "normative_sha256": "%s", "line_count": %d}'
        % (base["revision"], rev, _BASELINE.name, rev, h, len(lines)))


def test_rfc2119_keywords_are_only_uppercase():
    """RFC 2119 force comes from the uppercase form. A lowercase 'must' in a
    normative sentence reads as prose and is easy to miss in review; this keeps
    the normative surface the hash covers honest."""
    if not _SPEC.is_file():
        pytest.skip("SPEC.md not present")
    text = _SPEC.read_text(encoding="utf-8")
    # only flag lowercase keywords on lines that are otherwise normative
    offenders = []
    for i, ln in enumerate(text.splitlines(), 1):
        if not _RFC2119.search(ln):
            continue
        stripped = re.sub(r"`[^`]*`", "", ln)          # ignore code spans
        if re.search(r"\b(must not|should not)\b", stripped):
            offenders.append((i, ln.strip()[:90]))
    assert not offenders, (
        "lowercase RFC 2119 keywords on normative lines (ambiguous force):\n"
        + "\n".join("  line %d: %s" % o for o in offenders))
