# __s161_u1_builder_profile_test_v1__
from __future__ import annotations

import hashlib

import provenance
from provenance import (
    BUILDER_PROFILE_L1_ADHOC,
    BUILDER_PROFILE_L2_GITHUB,
    BUILD_PLATFORM_CLASS,
    BUILD_TYPE,
    BUILDER_ID,
    HONEST_SCOPE,
    SLSA_BUILD_LEVEL,
)

_FIXED = dict(
    artifacts=[
        ("nous_lang-9.9.9-py3-none-any.whl", "a" * 64),
        ("nous_lang-9.9.9.tar.gz", "b" * 64),
    ],
    source_repo_uri="https://github.com/contrario/nous",
    git_commit="0" * 40,
    version="9.9.9",
    ref="refs/tags/v9.9.9",
    started_on="2026-01-01T00:00:00Z",
    finished_on="2026-01-01T00:00:01Z",
    invocation_id="fixed-invocation",
    build_script="scripts/release.py",
    builder_versions={"python": "3.11.0"},
)

_EXT = "https://nous-lang.org/provenance/ext/v1"


def _canonical_sha(**extra) -> str:
    stmt = provenance.build_provenance_statement(**_FIXED, **extra)
    return hashlib.sha256(provenance.statement_canonical_bytes(stmt)).hexdigest()


def test_l1_profile_fields_match_legacy_constants() -> None:
    p = BUILDER_PROFILE_L1_ADHOC
    assert p.build_type == BUILD_TYPE
    assert p.builder_id == BUILDER_ID
    assert p.slsa_build_level == SLSA_BUILD_LEVEL
    assert p.build_platform_class == BUILD_PLATFORM_CLASS
    assert p.honest_scope == HONEST_SCOPE


def test_default_profile_is_l1_adhoc() -> None:
    stmt = provenance.build_provenance_statement(**_FIXED)
    ext = stmt["predicate"][_EXT]
    assert ext["slsaBuildLevel"] == 1
    assert ext["buildPlatformClass"] == "adhoc-operator-run-script"
    assert ext["scope"] == HONEST_SCOPE
    assert stmt["predicate"]["buildDefinition"]["buildType"] == BUILD_TYPE
    assert stmt["predicate"]["runDetails"]["builder"]["id"] == BUILDER_ID


def test_default_equals_explicit_l1_canonical_bytes() -> None:
    assert _canonical_sha() == _canonical_sha(profile=BUILDER_PROFILE_L1_ADHOC)


def test_l2_github_profile_is_distinct_and_truthful() -> None:
    stmt = provenance.build_provenance_statement(
        **_FIXED, profile=BUILDER_PROFILE_L2_GITHUB
    )
    ext = stmt["predicate"][_EXT]
    assert ext["slsaBuildLevel"] == 2
    assert ext["buildPlatformClass"] == "github-hosted-isolated-runner"
    bid = stmt["predicate"]["runDetails"]["builder"]["id"]
    assert bid.startswith("https://github.com/contrario/nous/")
    assert _canonical_sha(profile=BUILDER_PROFILE_L2_GITHUB) != _canonical_sha()
