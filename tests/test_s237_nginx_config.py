"""The served nginx config, tracked, and the predicates that actually bind.
__s237_p1_nginx_tracked_v1__

WHY THIS FILE EXISTS. /etc/nginx/sites-enabled/nous-lang.org carries a
correctness-bearing carve-out (S235): under /.well-known/, a missing artifact
must answer 404. Without it the SPA fallback answers 200 with the homepage, and
an auditor fetching a signed artifact receives a web page instead. That carve-out
was applied by hand, live, on the server. NO CODE PATH IN THIS REPOSITORY WRITES
IT. Its only records were one server's filesystem, one backup under /root, and a
downloaded patch file. A server rebuild reintroduces the defect silently.

WHAT TRACKING DOES AND DOES NOT DO -- read this before trusting the file.
Tracking the bytes is a RECOVERY RECORD. It is NOT enforcement. Git is a snapshot
too. Nothing here reaches out and rewrites /etc, and a deployed config can diverge
from these bytes at any moment. infra/systemd/ has tracked two live drop-ins for
months with no parity check at all; this file would be the same thing if the
docstring let you believe otherwise.

The BEHAVIOURAL check is strictly stronger and it lives elsewhere:
scripts/cold_audit.py asks the live site for a version that cannot exist and
refuses to audit any class unless the surface answers 404. This file records what
the config SHOULD be. That one checks what the surface ACTUALLY DOES.

THE PREDICATE THAT MATTERS IS NOT BLOCK ORDER. nginx selects the LONGEST MATCHING
PREFIX among prefix locations, whatever order they appear in the file, so
`location /.well-known/` (13 characters) outranks `location /` (1) wherever it
sits. A test asserting the order of those two blocks would assert something nginx
does not consult.

What nginx DOES consult first: a REGEX location is evaluated BEFORE the longest
prefix match is used. A future `location ~ ...` matching a .json path would
therefore outrank the carve-out and quietly restore the defect -- with the
carve-out still sitting in the config, looking correct. The tracked config carries
zero regex locations, and test_no_regex_location_can_outrank_the_wellknown_prefix
is what keeps it that way.

RESTORE (operator, on the server):
    cp infra/nginx/nous-lang.org.conf /etc/nginx/sites-enabled/nous-lang.org
    nginx -t && systemctl reload nginx
A backup NEVER lands inside /etc/nginx/sites-enabled/. nginx.conf includes that
directory with a BARE glob, so a .bak file there is parsed as a second server
block (FG-S235-C, and it happened).
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TRACKED = REPO_ROOT / "infra" / "nginx" / "nous-lang.org.conf"
LIVE = Path("/etc/nginx/sites-enabled/nous-lang.org")

_LOCATION_RE = re.compile(r"^[ \t]*location[ \t]+(\S+)(?:[ \t]+(\S+))?[ \t]*\{", re.MULTILINE)
_MODIFIERS = ("=", "~", "~*", "^~")

_SYNTHETIC_WITH_REGEX = """
server {
    location /.well-known/ {
        try_files $uri =404;
    }
    location ~ [.]json$ {
        try_files $uri /index.html;
    }
    location / {
        try_files $uri $uri/ /index.html;
    }
}
"""

_SYNTHETIC_WITHOUT_WELLKNOWN = """
server {
    location / {
        try_files $uri $uri/ /index.html;
    }
}
"""


def _locations(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for match in _LOCATION_RE.finditer(text):
        first: str = match.group(1)
        second: str | None = match.group(2)
        if first in _MODIFIERS and second is not None:
            out.append((first, second))
        else:
            out.append(("", first))
    return out


def _tracked_text() -> str:
    assert TRACKED.is_file(), "infra/nginx/nous-lang.org.conf is not in the checkout"
    return TRACKED.read_bytes().decode("ascii")


def test_the_config_is_tracked_and_ascii() -> None:
    assert TRACKED.is_file(), (
        "infra/nginx/nous-lang.org.conf is absent. The served config carries the "
        "/.well-known/ =404 carve-out and no code path in this repo writes it; "
        "untracked, its only record is one server's filesystem."
    )
    TRACKED.read_bytes().decode("ascii")


def test_the_wellknown_location_refuses_a_missing_artifact() -> None:
    match = re.search(
        r"location[ \t]+/\.well-known/[ \t]*\{(.*?)\}",
        _tracked_text(),
        re.DOTALL,
    )
    assert match is not None, (
        "no `location /.well-known/` block: a missing artifact falls through to "
        "the SPA fallback and is answered 200 with the homepage"
    )
    body: str = match.group(1)
    assert "try_files" in body and "=404" in body, (
        "the /.well-known/ block does not carry `try_files $uri =404;`: "
        + repr(body.strip())
    )


def test_only_one_wellknown_location_block() -> None:
    paths = [p for _, p in _locations(_tracked_text()) if p.startswith("/.well-known")]
    assert len(paths) == 1, (
        "expected exactly one /.well-known/ location, found "
        + str(len(paths)) + ": " + repr(paths)
    )


def test_no_regex_location_can_outrank_the_wellknown_prefix() -> None:
    regexes = [(m, p) for m, p in _locations(_tracked_text()) if m in ("~", "~*")]
    assert regexes == [], (
        "a REGEX location is evaluated BEFORE the longest-prefix match is used, "
        "so it outranks `location /.well-known/` no matter where either block "
        "sits in the file -- and the carve-out would still be there, looking "
        "correct, while a missing artifact was answered 200 again. Found: "
        + repr(regexes)
    )


def test_the_spa_fallback_still_serves_html_routes() -> None:
    match = re.search(
        r"location[ \t]+/[ \t]*\{(.*?)\}", _tracked_text(), re.DOTALL
    )
    assert match is not None, "the `location /` SPA fallback is gone"
    assert "/index.html" in match.group(1), (
        "the SPA fallback no longer falls back to /index.html; /governance, "
        "/replay, /policies and every other HTML route depend on it"
    )


def test_the_regex_predicate_actually_fires() -> None:
    regexes = [
        (m, p) for m, p in _locations(_SYNTHETIC_WITH_REGEX) if m in ("~", "~*")
    ]
    assert regexes, (
        "the regex predicate did not fire on a config that HAS a regex location. "
        "test_no_regex_location_can_outrank_the_wellknown_prefix would then be "
        "decoration: green with the predicate deleted (FG-S236-E)."
    )


def test_the_wellknown_predicate_actually_fires() -> None:
    match = re.search(
        r"location[ \t]+/\.well-known/[ \t]*\{",
        _SYNTHETIC_WITHOUT_WELLKNOWN,
    )
    assert match is None, (
        "the /.well-known/ predicate matched a config that does NOT carry the "
        "block. The guard above would then be decoration (FG-S236-E)."
    )


def test_the_live_config_matches_the_tracked_bytes() -> None:
    """VACUOUS OFF THE SERVER, DELIBERATELY, AND IT DOES NOT SKIP.

    A test that skips in CI and passes on Server A breaks the floor arithmetic:
    PYTEST_FLOOR is the live count minus one, and CI already runs one fewer test
    than Server A. A second CI-skipping test makes CI live-minus-two and aborts
    the next release at the pytest phase.

    So this asserts conditionally instead. On the server it has teeth: a config
    restored from an older backup, or edited by hand, fails here. Off the server
    it checks nothing, and this docstring is the honest statement of that."""
    if not LIVE.is_file():
        return
    live: bytes = LIVE.read_bytes()
    tracked: bytes = TRACKED.read_bytes()
    assert live == tracked, (
        "the DEPLOYED nginx config has diverged from infra/nginx/"
        "nous-lang.org.conf. Tracking bytes does not force a deploy to match "
        "them; this assertion is where that gap becomes visible. Reconcile "
        "before trusting either. live=" + hashlib.sha256(live).hexdigest()[:16]
        + "... tracked=" + hashlib.sha256(tracked).hexdigest()[:16] + "..."
    )
