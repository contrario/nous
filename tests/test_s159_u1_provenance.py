"""S159 U1 tests for the SLSA Provenance v1 emitter (provenance.py).

Covers Statement shape, SLSA Build L1 honesty (no overclaim), DSSE
sign/verify round-trip against the dedicated builder key, byte-identity under
fixed inputs, builder-key isolation and 0600 permissions, and fail-closed
input validation.
"""
from __future__ import annotations

import base64
import hashlib
import json
import stat
from pathlib import Path

import pytest

import provenance


_GOOD_KW = dict(
    artifacts=[
        ("nous_lang-9.9.9-py3-none-any.whl", "a" * 64),
        ("nous_lang-9.9.9.tar.gz", "b" * 64),
    ],
    source_repo_uri="https://github.com/contrario/nous",
    git_commit="c" * 40,
    version="9.9.9",
    ref="v9.9.9",
    started_on="2026-06-20T10:00:00Z",
    finished_on="2026-06-20T10:01:30.5Z",
    invocation_id="fixed-invocation-id",
    build_script="scripts/release.py",
    builder_versions={"python": "3.11.9", "build": "1.2.1"},
)


def _keypair(tmp_path: Path):
    return provenance.load_or_create_provenance_keypair(
        tmp_path / "provenance_signing.key"
    )


def test_statement_shape_matches_slsa_provenance_v1() -> None:
    stmt = provenance.build_provenance_statement(**_GOOD_KW)
    assert stmt["_type"] == "https://in-toto.io/Statement/v1"
    assert stmt["predicateType"] == "https://slsa.dev/provenance/v1"
    assert [s["digest"]["sha256"] for s in stmt["subject"]] == ["a" * 64, "b" * 64]
    assert [s["name"] for s in stmt["subject"]] == [
        "nous_lang-9.9.9-py3-none-any.whl",
        "nous_lang-9.9.9.tar.gz",
    ]
    bd = stmt["predicate"]["buildDefinition"]
    rd = stmt["predicate"]["runDetails"]
    assert bd["buildType"] == provenance.BUILD_TYPE
    assert bd["externalParameters"] == {
        "repository": "https://github.com/contrario/nous",
        "ref": "v9.9.9",
        "commit": "c" * 40,
        "version": "9.9.9",
    }
    assert bd["resolvedDependencies"][0]["uri"] == (
        "git+https://github.com/contrario/nous@v9.9.9"
    )
    assert bd["resolvedDependencies"][0]["digest"]["gitCommit"] == "c" * 40
    assert bd["internalParameters"] == {"buildScript": "scripts/release.py"}
    assert rd["builder"]["id"] == provenance.BUILDER_ID
    assert rd["builder"]["version"] == {"python": "3.11.9", "build": "1.2.1"}
    assert rd["metadata"]["startedOn"] == "2026-06-20T10:00:00Z"
    assert rd["metadata"]["finishedOn"] == "2026-06-20T10:01:30.5Z"
    assert rd["metadata"]["invocationId"] == "fixed-invocation-id"


def test_l1_honesty_no_overclaim() -> None:
    stmt = provenance.build_provenance_statement(**_GOOD_KW)
    pred = stmt["predicate"]
    assert provenance.SLSA_BUILD_LEVEL == 1
    assert pred["buildDefinition"]["buildType"] == (
        "https://nous-lang.org/buildtypes/release-script/v1"
    )
    assert pred["runDetails"]["builder"]["id"] == (
        "https://nous-lang.org/builders/release-script-adhoc/v1"
    )
    assert "adhoc" in pred["runDetails"]["builder"]["id"]
    ext = pred[provenance.NOUS_PROV_EXT_KEY]
    assert ext["slsaBuildLevel"] == 1
    assert ext["buildPlatformClass"] == "adhoc-operator-run-script"
    assert "Does NOT prove" in ext["scope"]
    assert "evidence layer is a monitor, not a guard" in ext["scope"]
    assert "SLSA Build Level 1" in ext["scope"]
    assert "verifiedLevels" not in pred
    for level in ("LEVEL_2", "LEVEL_3", "level 2", "level 3"):
        assert level not in json.dumps(stmt)


def test_optional_legs_dropped_when_absent() -> None:
    minimal = dict(
        artifacts=[("nous_lang-9.9.9.tar.gz", "d" * 64)],
        source_repo_uri="https://github.com/contrario/nous",
        git_commit="e" * 40,
        version="9.9.9",
        ref="v9.9.9",
        started_on="2026-06-20T10:00:00Z",
        finished_on="2026-06-20T10:01:00Z",
    )
    stmt = provenance.build_provenance_statement(**minimal)
    bd = stmt["predicate"]["buildDefinition"]
    rd = stmt["predicate"]["runDetails"]
    assert "internalParameters" not in bd
    assert "version" not in rd["builder"]
    assert "invocationId" not in rd["metadata"]


def test_sign_verify_roundtrip(tmp_path: Path) -> None:
    priv, pub, _ = _keypair(tmp_path)
    stmt = provenance.build_provenance_statement(**_GOOD_KW)
    env = provenance.sign_provenance(stmt, priv)
    assert env["payloadType"] == "application/vnd.in-toto+json"
    assert env["signatures"][0]["keyid"] == provenance.provenance_keyid(pub)
    recovered = provenance.verify_provenance_envelope(env, pub)
    assert recovered == stmt


def test_verify_rejects_tampered_payload(tmp_path: Path) -> None:
    priv, pub, _ = _keypair(tmp_path)
    stmt = provenance.build_provenance_statement(**_GOOD_KW)
    env = provenance.sign_provenance(stmt, priv)
    env["payload"] = base64.b64encode(b'{"_type":"forged"}').decode("ascii")
    with pytest.raises(provenance.ProvenanceError):
        provenance.verify_provenance_envelope(env, pub)


def test_verify_rejects_wrong_key(tmp_path: Path) -> None:
    priv, _, _ = _keypair(tmp_path)
    other_priv, other_pub, _ = provenance.load_or_create_provenance_keypair(
        tmp_path / "other.key"
    )
    stmt = provenance.build_provenance_statement(**_GOOD_KW)
    env = provenance.sign_provenance(stmt, priv)
    with pytest.raises(provenance.ProvenanceError):
        provenance.verify_provenance_envelope(env, other_pub)


def test_byte_identity_under_fixed_inputs(tmp_path: Path) -> None:
    priv, _, _ = _keypair(tmp_path)
    s1 = provenance.build_provenance_statement(**_GOOD_KW)
    s2 = provenance.build_provenance_statement(**_GOOD_KW)
    assert provenance.statement_canonical_bytes(s1) == (
        provenance.statement_canonical_bytes(s2)
    )
    assert provenance.sign_provenance(s1, priv) == (
        provenance.sign_provenance(s2, priv)
    )


def test_canonical_bytes_are_sorted_compact_json() -> None:
    stmt = provenance.build_provenance_statement(**_GOOD_KW)
    raw = provenance.statement_canonical_bytes(stmt)
    assert raw == json.dumps(
        stmt, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def test_builder_key_isolated_and_0600(tmp_path: Path) -> None:
    key_path = tmp_path / "provenance_signing.key"
    priv1, pub1, resolved = provenance.load_or_create_provenance_keypair(key_path)
    assert resolved == key_path
    assert key_path.is_file()
    assert len(key_path.read_bytes()) == 32
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
    priv2, pub2, _ = provenance.load_or_create_provenance_keypair(key_path)
    assert provenance.public_key_raw_b64(pub1) == provenance.public_key_raw_b64(
        pub2
    )


def test_default_key_path_is_distinct_from_vsa() -> None:
    assert provenance.DEFAULT_PROVENANCE_KEY_PATH.name == (
        "provenance_signing.key"
    )
    assert "vsa_signing.key" not in str(
        provenance.DEFAULT_PROVENANCE_KEY_PATH
    )


def test_rejects_empty_artifacts() -> None:
    with pytest.raises(provenance.ProvenanceError):
        provenance.build_provenance_statement(
            **dict(_GOOD_KW, artifacts=[])
        )


def test_rejects_bad_sha256() -> None:
    with pytest.raises(provenance.ProvenanceError):
        provenance.build_provenance_statement(
            **dict(_GOOD_KW, artifacts=[("x.whl", "z" * 64)])
        )
    with pytest.raises(provenance.ProvenanceError):
        provenance.build_provenance_statement(
            **dict(_GOOD_KW, artifacts=[("x.whl", "a" * 63)])
        )


def test_rejects_bad_timestamp() -> None:
    with pytest.raises(provenance.ProvenanceError):
        provenance.build_provenance_statement(
            **dict(_GOOD_KW, started_on="2026-06-20 10:00:00")
        )
    with pytest.raises(provenance.ProvenanceError):
        provenance.build_provenance_statement(
            **dict(_GOOD_KW, finished_on="not-a-time")
        )


def test_rejects_missing_required_scalars() -> None:
    for field in ("source_repo_uri", "git_commit", "version", "ref"):
        with pytest.raises(provenance.ProvenanceError):
            provenance.build_provenance_statement(**dict(_GOOD_KW, **{field: ""}))


def test_subject_digest_round_trips_sha256_of_bytes(tmp_path: Path) -> None:
    blob = b"pretend-wheel-bytes"
    digest = hashlib.sha256(blob).hexdigest()
    stmt = provenance.build_provenance_statement(
        **dict(_GOOD_KW, artifacts=[("nous_lang-9.9.9.tar.gz", digest)])
    )
    assert stmt["subject"][0]["digest"]["sha256"] == digest
