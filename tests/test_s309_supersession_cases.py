"""S309 case table for the D305-1(a) supersession checker.

One row per token in the set fixed by D307-1 and amended by D308-1. Every row
carries its subject, its provenance label and its token as GIVEN data. Nothing
in this file classifies: there is no branch that decides which token a case
deserves, because the tool that will do that does not exist yet. When it does,
its own tests import this table and assert that it agrees.

A token names a LINK, and a link has two ends. Rows of subject LINK are decided
without any fetch. Rows of subject PREDECESSOR describe a document that was
fetched. Six rows are constructed in memory, one is read from the published
manifest, and one is present as an absence.

Hermetic and CI-portable: no network, no private key, no served-path read. The
two files read here are the tracked published manifest and the tracked archive
root, which tests/test_s297 and tests/test_s298 already read.

__s309_supersession_cases_v1__
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import glm_manifest as gm

_REPO = Path(__file__).resolve().parents[1]
_MANIFEST = _REPO / "website" / ".well-known" / "governance-layer-manifest.json"
_ROOT_MANIFEST = (
    _REPO / "website" / "governance" / "glm-archive"
    / "governance-layer-manifest-5.37.0.json"
)

_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
_URL = "https://example.invalid/predecessor.json"
_RAISED = "RAISED"

LINK = "LINK"
PREDECESSOR = "PREDECESSOR"

CONSTRUCTED = "CONSTRUCTED"
READ = "READ"
ABSENT_BY_DECISION = "ABSENT_BY_DECISION"

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

# token -> (subject, provenance). One row per token; see D309-3.
TABLE = {
    "ROOT": (LINK, CONSTRUCTED),
    "MALFORMED_LINK": (LINK, CONSTRUCTED),
    "DIGEST_ONLY": (PREDECESSOR, CONSTRUCTED),
    "DIGEST_MISMATCH": (PREDECESSOR, CONSTRUCTED),
    "SIGNATURE_BAD": (PREDECESSOR, CONSTRUCTED),
    "UNREADABLE": (PREDECESSOR, CONSTRUCTED),
    "VERIFIED": (PREDECESSOR, READ),
    "UNREACHABLE": (PREDECESSOR, ABSENT_BY_DECISION),
}

# token -> the observation the token names, GIVEN, never derived.
# (digest_ok, signature_present, signer_pinned, signature_ok,
#  supersedes present, supersedes_digest present, link shape, link matches)
EXPECTED = {
    "ROOT": (None, None, None, None, True, True, "NULL", None),
    "MALFORMED_LINK": (
        None, None, None, None, True, True, "MALFORMED", None,
    ),
    "DIGEST_ONLY": (True, False, False, False, True, True, "HEX64", True),
    "DIGEST_MISMATCH": (
        True, False, False, False, True, True, "HEX64", False,
    ),
    "SIGNATURE_BAD": (True, True, False, False, True, True, "HEX64", True),
    "UNREADABLE": (
        _RAISED, _RAISED, _RAISED, _RAISED, True, True, "HEX64", _RAISED,
    ),
    "VERIFIED": (True, True, True, True, None, None, None, None),
}


def _doc(supersedes, supersedes_digest, owner_version):
    """A structurally complete GLM source document.

    manifest_signature carries all four keys the published archive root
    carries. seal_glm_manifest forces only type and value, so the shape of
    the block is a property of this dict and not of the library.
    """
    return {
        "schema_version": "1.1",
        "manifest_version": "1.0",
        "owner": {"name": "NOUS", "version": owner_version},
        "valid_from": "2026-01-01",
        "generated_at": "2026-01-01T00:00:00Z",
        "supersedes": supersedes,
        "supersedes_digest": supersedes_digest,
        "operational_scope": {"does_not": ["Attest a specific execution"]},
        "manifest_digest": {
            "type": "sha256",
            "value": gm.GLM_DIGEST_PLACEHOLDER,
            "canonicalization_method": "placeholder-form sha256",
        },
        "manifest_signature": {
            "note": "unsigned; the ceremony seals at publish time",
            "planned_extensions": ["rekor"],
            "type": None,
            "value": None,
        },
    }


def _shape(value):
    if value is None:
        return "NULL"
    if isinstance(value, str) and _HEX64.match(value):
        return "HEX64"
    return "MALFORMED"


def _build_constructed():
    """token -> (successor_text, predecessor_text_or_None), in memory only.

    UNREACHABLE is absent by decision: it is a property of transport and no
    bytes exhibit it. VERIFIED is absent here because it is READ; see pair().
    """
    ephemeral = Ed25519PrivateKey.generate()
    unsigned = gm.seal_glm_manifest(_doc(None, None, "1.0.0"), private_key=None)
    signed = gm.seal_glm_manifest(
        _doc(None, None, "1.0.0"), private_key=ephemeral
    )
    other = gm.seal_glm_manifest(_doc(None, None, "9.9.9"), private_key=None)

    def successor(digest):
        return gm.seal_glm_manifest(
            _doc(_URL, digest, "2.0.0"), private_key=None
        )

    unsigned_digest = gm.compute_glm_digest(unsigned)
    return {
        "ROOT": (
            gm.seal_glm_manifest(_doc(None, None, "2.0.0"), private_key=None),
            None,
        ),
        "MALFORMED_LINK": (successor("not-a-digest"), None),
        "DIGEST_ONLY": (successor(unsigned_digest), unsigned),
        "DIGEST_MISMATCH": (
            successor(gm.compute_glm_digest(other)), unsigned,
        ),
        "SIGNATURE_BAD": (
            successor(gm.compute_glm_digest(signed)), signed,
        ),
        "UNREADABLE": (
            successor(unsigned_digest), "<html><body>404</body></html>",
        ),
    }


def _observe(successor_text, predecessor_text):
    """The observation tuple. Link fields come from the successor; the four
    booleans come from verifying the predecessor. Absent ends read None."""
    if successor_text is None:
        sup_present = None
        supd_present = None
        shape = None
        declared = None
    else:
        successor = json.loads(successor_text)
        sup_present = "supersedes" in successor
        supd_present = "supersedes_digest" in successor
        declared = successor.get("supersedes_digest")
        shape = _shape(declared)

    if predecessor_text is None:
        return (None, None, None, None, sup_present, supd_present, shape, None)

    try:
        detail = gm.verify_glm_manifest(predecessor_text)
    except gm.GlmManifestError:
        return (
            _RAISED, _RAISED, _RAISED, _RAISED,
            sup_present, supd_present, shape, _RAISED,
        )

    if isinstance(declared, str) and _HEX64.match(declared):
        computed = gm.compute_glm_digest(predecessor_text)
        link = computed.lower() == declared.lower()
    else:
        link = None
    return (
        detail.digest_ok, detail.signature_present, detail.signer_pinned,
        detail.signature_ok, sup_present, supd_present, shape, link,
    )


CONSTRUCTED_PAIRS = _build_constructed()

_WITH_BYTES = tuple(
    t for t in TOKENS if TABLE[t][1] in (CONSTRUCTED, READ)
)


def pair(token):
    """The bytes for a row. The READ row is read here rather than at import,
    so a missing tracked file fails a test instead of collection, and the
    file read happens inside a call as it does in tests/test_s297."""
    if token in CONSTRUCTED_PAIRS:
        return CONSTRUCTED_PAIRS[token]
    if token == "VERIFIED":
        return (None, _MANIFEST.read_text(encoding="utf-8"))
    raise KeyError(token)


# --- the table is complete and each row has one subject ------------------


def test_the_table_carries_one_row_per_token() -> None:
    """Set equality, never a length. A count breaks at the next amendment of
    the token set and reports arithmetic; this reports the thing that
    matters, which is a token with no row or a row with no token."""
    assert set(TABLE) == set(TOKENS)
    assert set(EXPECTED) | {"UNREACHABLE"} == set(TOKENS)


def test_every_row_carries_one_subject_and_one_provenance() -> None:
    for token, (subject, provenance) in TABLE.items():
        assert subject in (LINK, PREDECESSOR), token
        assert provenance in (CONSTRUCTED, READ, ABSENT_BY_DECISION), token


def test_the_absent_row_is_present_and_carries_no_bytes() -> None:
    """An absence shown is measurable; an absence left outside the table is
    an omission that resembles a decision."""
    assert TABLE["UNREACHABLE"] == (PREDECESSOR, ABSENT_BY_DECISION)
    assert "UNREACHABLE" not in CONSTRUCTED_PAIRS
    with pytest.raises(KeyError):
        pair("UNREACHABLE")


# --- property: each row exhibits what its token names --------------------


@pytest.mark.parametrize("token", _WITH_BYTES)
def test_each_row_exhibits_the_observation_its_token_names(token) -> None:
    successor_text, predecessor_text = pair(token)
    assert _observe(successor_text, predecessor_text) == EXPECTED[token]


# --- self-consistency: the link is what the checker checks ---------------


def test_the_link_digest_matches_the_predecessor_where_it_must() -> None:
    for token in ("DIGEST_ONLY", "SIGNATURE_BAD"):
        successor_text, predecessor_text = pair(token)
        declared = json.loads(successor_text)["supersedes_digest"]
        assert gm.compute_glm_digest(predecessor_text) == declared, token

    successor_text, predecessor_text = pair("DIGEST_MISMATCH")
    declared = json.loads(successor_text)["supersedes_digest"]
    assert _HEX64.match(declared)
    assert gm.compute_glm_digest(predecessor_text) != declared


# --- distinguishability, measured WITHIN a subject -----------------------


def test_no_two_rows_of_one_subject_share_an_observation() -> None:
    """Comparing across subjects is what made two cases look like one. The
    LINK rows have no verifier fields at all; that is the signature of no
    predecessor having been examined, not a collision."""
    for subject in (LINK, PREDECESSOR):
        rows = [
            t for t in _WITH_BYTES if TABLE[t][0] == subject
        ]
        seen = [_observe(*pair(t)) for t in rows]
        assert len(set(seen)) == len(rows), subject


def test_the_link_shape_alone_separates_the_link_rows() -> None:
    shapes = {
        t: _observe(*pair(t))[6] for t in _WITH_BYTES if TABLE[t][0] == LINK
    }
    assert set(shapes.values()) == {"NULL", "MALFORMED"}


def test_no_link_row_carries_a_well_formed_digest() -> None:
    """HEX64 is the transition, not a token: it is the condition under which
    the tool fetches and the subject becomes PREDECESSOR."""
    for token in _WITH_BYTES:
        if TABLE[token][0] != LINK:
            continue
        assert _observe(*pair(token))[6] != "HEX64", token


# --- the constructed bytes are the shape they claim to be ----------------


def test_the_constructed_root_matches_the_published_archive_root() -> None:
    """A fixture that builds the wrong bytes and asserts self-consistently
    around them passes green and is false. This is the only assertion that
    compares a construction against the artifact it stands for."""
    built = json.loads(pair("ROOT")[0])
    served = json.loads(_ROOT_MANIFEST.read_text(encoding="utf-8"))

    assert set(built["manifest_signature"]) == set(
        served["manifest_signature"]
    )
    assert built["manifest_signature"]["type"] is None
    assert served["manifest_signature"]["type"] is None
    assert built["manifest_signature"]["value"] is None
    assert served["manifest_signature"]["value"] is None

    for key in ("supersedes", "supersedes_digest"):
        assert key in built, key
        assert key in served, key
        assert built[key] is None
        assert served[key] is None


def test_the_read_row_is_the_published_manifest() -> None:
    """VERIFIED is not constructible under the default allowlist, so it is
    read. The four booleans are the observation; the row carries no
    successor, because a read document is not one end of a built link."""
    detail = gm.verify_glm_manifest(pair("VERIFIED")[1])
    observed = (
        detail.digest_ok, detail.signature_present,
        detail.signer_pinned, detail.signature_ok,
    )
    assert observed == EXPECTED["VERIFIED"][:4], detail.errors
    assert pair("VERIFIED")[0] is None
