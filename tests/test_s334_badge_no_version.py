"""No served version badge may claim a version it cannot confirm.

WHY. website/js/nous-version.js fetches /v1/health and rewrites the
text of every element carrying data-nous-version. When that fetch
fails the element keeps whatever the HTML holds. One element
therefore carried two meanings -- the running version on success, the
version at authoring time on failure -- and a reader cannot tell them
apart. Four pages held v5.66.0 while the running system was 5.78.0.

THE RULE. No data-nous-version element carries a version token. On
failure the element stays empty and claims nothing.

WHY THIS SHAPE AND NOT A RELEASE-COUPLED ONE. A rule that pins the
badge to the current version needs an oracle, costs six files per
release, and still prints a number the page cannot confirm at the
moment it prints it. This rule needs no oracle and cannot go stale.

THE SET IS THE TRACKED SET, NOT THE WORKING DIRECTORY. scripts/
deploy_website.sh names blog/drafts as served-only and untracked, and
an untracked file present on one machine and absent on another would
make this rule mean a different thing in each place. git ls-files is
the same set the patcher that established this rule used. If git is
not available the test FAILS rather than falling back to a wider set.

BLIND TO. A version written in any form other than digits dot digits
dot digits, and any element that carries the attribute with a value
rather than bare.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]

# __s334_badge_no_version_v1__
_SITE = re.compile(r"data-nous-version(?:\s[^>]*)?>([^<]*)<")
_VERSION = re.compile(r"v?[0-9]+\.[0-9]+\.[0-9]+")


def _tracked_html() -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files", "website/"],
        cwd=str(_REPO), capture_output=True, text=True)
    assert proc.returncode == 0, (
        "git ls-files failed in " + str(_REPO) + "; this rule is defined "
        "over the tracked set and has no meaning without it: "
        + proc.stderr.strip()[:200])
    return sorted(p for p in proc.stdout.split("\n") if p.endswith(".html"))


def _sites() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for rel in _tracked_html():
        text = (_REPO / rel).read_text(encoding="utf-8")
        for m in _SITE.finditer(text):
            found.append((rel, m.group(1)))
    return found


def test_the_site_shape_fires_on_a_constructed_positive() -> None:
    sample = '<span class="nav-ver" data-nous-version>v5.66.0</span>'
    m = _SITE.search(sample)
    assert m is not None, "the site shape does not match a real element"
    assert _VERSION.search(m.group(1)) is not None, (
        "the version shape does not fire on a version; this test would "
        "pass over a corpus full of them")


def test_the_site_shape_is_silent_on_the_empty_form() -> None:
    m = _SITE.search('<span class="nav-ver" data-nous-version></span>')
    assert m is not None, "the site shape misses the empty form"
    assert _VERSION.search(m.group(1)) is None


def test_the_attribute_selector_form_is_not_a_site() -> None:
    assert _SITE.search("querySelectorAll('[data-nous-version]')") is None, (
        "the shape reads the JS selector as an element; it would count "
        "the mechanism as one of the things it governs")


def test_the_tracked_set_is_not_empty() -> None:
    files = _tracked_html()
    assert files, (
        "git ls-files website/ returned no html; the set this rule is "
        "defined over is empty and every assertion below is vacuous")


def test_the_corpus_has_sites_at_all() -> None:
    found = _sites()
    assert found, (
        "no data-nous-version element found in the tracked website/; the "
        "shape reads nothing, so the rule below would hold vacuously")


def test_no_badge_element_carries_a_version() -> None:
    bad = [(p, t) for p, t in _sites() if _VERSION.search(t)]
    assert not bad, (
        "a version badge claims a version the page cannot confirm: "
        + "; ".join(p + " -> " + t for p, t in bad)
        + ". The element is filled at runtime from /v1/health. Leave it "
        "empty in the HTML.")
