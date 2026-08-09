"""Check one GLM supersedes link: does the predecessor it names hash to the
digest it declares.

    python3 scripts/check_glm_supersession.py --successor PATH

READ-ONLY. Reads one local file, performs at most one HTTP GET, writes
nothing. The successor is operator input and is read from disk; the
predecessor is fetched from the successor's supersedes URL. Exactly one
fetch is performed and it is always the predecessor, so UNREACHABLE is
never ambiguous about which end failed (D310-4).

The contract is the VERDICT token. The exit code is a projection of it and
is a summary, not the truth (D307-1). Non-zero codes are a stable API:

    0  CHECKED, NOTHING WRONG   VERIFIED, ROOT, DIGEST_ONLY
    2  CHECKED, WRONG           DIGEST_MISMATCH, MALFORMED_LINK,
                                SIGNATURE_BAD
    3  COULD NOT CHECK          UNREACHABLE, UNREADABLE, and the
                                UNCLASSIFIED case below
    1  unassigned

VERDICT always carries a name. Where no token in the set covers the
condition, the name is UNCLASSIFIED: an absence of verdict expressed as a
value rather than as a blank field (D310-5a). It is not a token.

COVERAGE DEBT, MEASURED AND NOT HIDDEN. Six rows of
tests/test_s309_supersession_cases.py lock six tokens against this
classifier. Eight further behaviours were exercised only in the seat's
container while this file was written, and nothing in the tree locks
them: (1) a link needing a fetch with no bytes; (2) and (3) a half-null
link in each of its two directions; (4) a predecessor whose own seal is
broken while the link still matches; (5) a successor carrying neither
link key; (6) an uppercase digest; (7) and (8) the two predecessor
branches that need an all-true verify detail. Two of the eight, (1) and
(7), can be locked in this tool's own tests from fixture bytes alone.
The remaining six need rows the fixture does not have, and one cannot be
built there at all: the fixture holds no predecessor signed by the
pinned key, so a signature failing under the pinned allowlist is not
reproducible from it. That is not a missing row; it is an input the
fixture cannot construct. The amendment is requested in
docs/GLM_SUPERSESSION_DESIGN.md and is unauthorised until granted.

__s310_check_glm_supersession_v1__
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

import glm_manifest

TOKENS = (
    "ROOT",
    "DIGEST_ONLY",
    "DIGEST_MISMATCH",
    "MALFORMED_LINK",
    "SIGNATURE_BAD",
    "UNREADABLE",
    "UNREACHABLE",
    "VERIFIED",
)

UNCLASSIFIED = "UNCLASSIFIED"

RC_BY_TOKEN = {
    "VERIFIED": 0,
    "ROOT": 0,
    "DIGEST_ONLY": 0,
    "DIGEST_MISMATCH": 2,
    "MALFORMED_LINK": 2,
    "SIGNATURE_BAD": 2,
    "UNREACHABLE": 3,
    "UNREADABLE": 3,
    UNCLASSIFIED: 3,
}

MAX_BODY_BYTES = 1048576
TIMEOUT_SECONDS = 60.0

_HEX64_CHARS = "0123456789abcdefABCDEF"


class FetchRefused(Exception):
    """The predecessor was not obtained. Always UNREACHABLE."""


class SuccessorError(Exception):
    """The operator's own input is unusable. Never a verdict."""


def link_shape(value: object) -> str:
    """NULL, HEX64 or MALFORMED. Case-insensitive by F308-10: the GLM
    specification compares digests case-insensitively."""
    if value is None:
        return "NULL"
    if (
        isinstance(value, str)
        and len(value) == 64
        and all(c in _HEX64_CHARS for c in value)
    ):
        return "HEX64"
    return "MALFORMED"


def classify_predecessor(detail, link_matches: bool) -> str:
    """The PREDECESSOR branch, given a verify result and the link comparison.

    digest_ok is a PRECONDITION of reading the signature legs, not an
    observation beside them: verify_glm_manifest checks the signature over
    the DECLARED digest, so when the predecessor's own seal is broken the
    signature was never checked against anything trustworthy (D310-3).
    """
    if not detail.digest_ok:
        return UNCLASSIFIED
    if not link_matches:
        return "DIGEST_MISMATCH"
    if not detail.signature_present:
        return "DIGEST_ONLY"
    if detail.signature_ok:
        return "VERIFIED"
    return "SIGNATURE_BAD"


def classify_pair(successor_text: str, predecessor_text: str | None) -> str:
    """token for one (successor, predecessor) pair. No I/O, no network.

    predecessor_text None means no predecessor was obtained. For a link that
    needs no fetch that is expected; for one that does, it is UNREACHABLE.
    """
    try:
        successor = json.loads(successor_text)
    except ValueError as exc:
        raise SuccessorError("successor is not valid JSON: " + str(exc))
    if not isinstance(successor, dict):
        raise SuccessorError("successor is not a JSON object")

    if "supersedes" not in successor or "supersedes_digest" not in successor:
        return UNCLASSIFIED

    url = successor.get("supersedes")
    declared = successor.get("supersedes_digest")
    shape = link_shape(declared)

    if shape == "NULL":
        return "ROOT" if url is None else "MALFORMED_LINK"
    if shape == "MALFORMED":
        return "MALFORMED_LINK"
    if url is None:
        return "MALFORMED_LINK"

    if predecessor_text is None:
        return "UNREACHABLE"

    try:
        detail = glm_manifest.verify_glm_manifest(predecessor_text)
        computed = glm_manifest.compute_glm_digest(predecessor_text)
    except glm_manifest.GlmManifestError:
        return "UNREADABLE"

    return classify_predecessor(detail, computed.lower() == declared.lower())


def fetch_predecessor(url: str) -> bytes:
    """At most MAX_BODY_BYTES, redirects not followed, refused never
    truncated: truncated bytes would reach compute_glm_digest and return
    DIGEST_MISMATCH, a verdict about content for a fault in transport."""
    chunks: list[bytes] = []
    total = 0
    try:
        with httpx.stream(
            "GET", url, follow_redirects=False, timeout=TIMEOUT_SECONDS
        ) as response:
            if response.status_code != 200:
                raise FetchRefused("HTTP " + str(response.status_code))
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > MAX_BODY_BYTES:
                    raise FetchRefused(
                        "body exceeds " + str(MAX_BODY_BYTES)
                        + " bytes; refused without truncating"
                    )
                chunks.append(chunk)
    except httpx.RequestError as exc:
        raise FetchRefused("transport: " + type(exc).__name__)
    return b"".join(chunks)


def _print(label: str, value: object) -> None:
    print(label.ljust(18) + str(value))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check one GLM supersedes link against the bytes it names."
        )
    )
    parser.add_argument(
        "--successor",
        required=True,
        help="path to a local GLM manifest; NOT a URL",
    )
    args = parser.parse_args(argv)

    from urllib.parse import urlsplit

    if urlsplit(args.successor).scheme:
        print(
            "REFUSED: --successor takes a local PATH, not a URL. The "
            "successor is read from disk; only the predecessor is fetched, "
            "and its address comes from the successor's supersedes field.",
            file=sys.stderr,
        )
        return 3

    try:
        successor_text = Path(args.successor).read_text(encoding="utf-8")
    except OSError as exc:
        print("cannot read successor: " + str(exc), file=sys.stderr)
        return 3

    try:
        successor = json.loads(successor_text)
    except ValueError as exc:
        print("successor is not valid JSON: " + str(exc), file=sys.stderr)
        return 3
    if not isinstance(successor, dict):
        print("successor is not a JSON object", file=sys.stderr)
        return 3

    url = successor.get("supersedes")
    declared = successor.get("supersedes_digest")
    shape = link_shape(declared)

    predecessor_text: str | None = None
    fetch_note = "no fetch performed"
    if shape == "HEX64" and isinstance(url, str) and url:
        try:
            body = fetch_predecessor(url)
            predecessor_text = body.decode("utf-8")
            fetch_note = "fetched " + str(len(body)) + " bytes"
        except FetchRefused as exc:
            fetch_note = "not obtained: " + str(exc)
        except UnicodeDecodeError:
            predecessor_text = ""
            fetch_note = "fetched, not UTF-8"

    try:
        token = classify_pair(successor_text, predecessor_text)
    except SuccessorError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    detail = None
    if predecessor_text is not None:
        try:
            detail = glm_manifest.verify_glm_manifest(predecessor_text)
        except glm_manifest.GlmManifestError:
            detail = None

    _print("successor", args.successor)
    _print("supersedes", repr(url))
    _print("supersedes_digest", repr(declared))
    _print("link_shape", shape)
    _print("fetch", fetch_note)
    _print("manifest_version", repr(successor.get("manifest_version")))
    owner = successor.get("owner")
    _print(
        "owner.version",
        repr(owner.get("version") if isinstance(owner, dict) else None),
    )
    if detail is not None:
        _print("pred.digest_ok", detail.digest_ok)
        _print("pred.sig_present", detail.signature_present)
        _print("pred.signer_pinned", detail.signer_pinned)
        _print("pred.signature_ok", detail.signature_ok)
        _print("pred.owner.version", repr(detail.owner_version))
    print("")
    print("The version fields above are REPORTED, NOT JUDGED (D308-1).")
    _print("VERDICT", token)
    if token == UNCLASSIFIED:
        print(
            "  no token in the set fixed by D307-1 as amended by D308-1 "
            "covers this condition; the observations above carry the fact "
            "and a fixture row is owed."
        )
    return RC_BY_TOKEN[token]


if __name__ == "__main__":
    raise SystemExit(main())
