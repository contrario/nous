"""S95: build_dossier_spec(anchor='rekor_v2') emission structural tests.

Mirrors tests/test_s93_dossier_rekor_v2_emit.py for the SKILL.md-directory
path. Exercises the v2 anchored emit offline via the _test_rekor_anchor_v2
hook (no live Rekor submit, no live TSA call). Asserts the rendered
manifest.json carries the v2 transparency_log block and that the emitted
verify_offline.py is the v2 variant with the pinned KNOWN_REKOR_V2_LOG_KEYS
allowlist. Live end-to-end (real submit + timestamp, verifier exit 0) is
proven on the server before release; static hooks cannot bind a leaf
signature to a per-run manifest's canonical bytes.

# __nous_s95_dossier_spec_rekor_v2_tests_v1__
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_DIR = _TESTS_DIR.parent
if str(_REPO_DIR) not in sys.path:
    sys.path.insert(0, str(_REPO_DIR))

from dossier_spec import (
    DossierSpecError,
    DossierSpecResult,
    build_dossier_spec,
)
from rekor_verify_v2 import RekorAnchorV2

FIXTURES = _TESTS_DIR / "skill_md_fixtures"


def _isolated_key(tmp_path: Path) -> Path:
    return tmp_path / "signing.key"


def _fake_v2_anchor() -> RekorAnchorV2:
    return RekorAnchorV2(
        rekor_api_version=2,
        log_id="test-log-id",
        log_index=0,
        body_b64="dGVzdC1ib2R5",
        checkpoint_envelope="test-checkpoint-envelope",
        inclusion_proof_hashes=["aGFzaC1vbmU="],
        rfc3161_token_b64="dGVzdC10b2tlbg==",
    )


def test_spec_rekor_v2_emit_writes_eight_files(tmp_path: Path) -> None:
    result = build_dossier_spec(
        FIXTURES / "basic",
        cap_override="0.50USD",
        output=tmp_path / "out",
        key_path=_isolated_key(tmp_path),
        anchor="rekor_v2",
        _test_rekor_anchor_v2=_fake_v2_anchor(),
    )
    expected = {
        "source.nous",
        "manifest.json",
        "SKILL.md",
        "nous.yaml",
        "pricing.toml",
        "public_key.b64",
        "README.md",
        "verify_offline.py",
    }
    assert isinstance(result, DossierSpecResult)
    assert set(result.files) == expected
    for f in expected:
        assert (tmp_path / "out" / f).is_file()


def test_spec_rekor_v2_manifest_has_v2_transparency_block(
    tmp_path: Path,
) -> None:
    build_dossier_spec(
        FIXTURES / "basic",
        cap_override="0.50USD",
        output=tmp_path / "out",
        key_path=_isolated_key(tmp_path),
        anchor="rekor_v2",
        _test_rekor_anchor_v2=_fake_v2_anchor(),
    )
    manifest = json.loads(
        (tmp_path / "out" / "manifest.json").read_text(encoding="utf-8")
    )
    tlog = manifest.get("transparency_log")
    assert isinstance(tlog, dict)
    assert tlog.get("rekor_api_version") == 2
    assert tlog.get("rfc3161_token_b64") == "dGVzdC10b2tlbg=="
    assert tlog.get("log_id") == "test-log-id"
    assert tlog.get("body_b64") == "dGVzdC1ib2R5"


def test_spec_rekor_v2_verifier_is_v2_variant(tmp_path: Path) -> None:
    build_dossier_spec(
        FIXTURES / "basic",
        cap_override="0.50USD",
        output=tmp_path / "out",
        key_path=_isolated_key(tmp_path),
        anchor="rekor_v2",
        _test_rekor_anchor_v2=_fake_v2_anchor(),
    )
    verify_text = (
        tmp_path / "out" / "verify_offline.py"
    ).read_text(encoding="utf-8")
    assert verify_text.startswith("#!/usr/bin/env python3")
    assert "KNOWN_REKOR_V2_LOG_KEYS" in verify_text
    assert "verify_rekor_v2_anchor" in verify_text
    assert "rekor_api_version" in verify_text


def test_spec_rekor_v2_verifier_pins_production_log_key(
    tmp_path: Path,
) -> None:
    build_dossier_spec(
        FIXTURES / "basic",
        cap_override="0.50USD",
        output=tmp_path / "out",
        key_path=_isolated_key(tmp_path),
        anchor="rekor_v2",
        _test_rekor_anchor_v2=_fake_v2_anchor(),
    )
    verify_text = (
        tmp_path / "out" / "verify_offline.py"
    ).read_text(encoding="utf-8")
    assert "log2025-1.rekor.sigstore.dev" in verify_text


def test_spec_rekor_v2_verifier_is_byte_compilable(
    tmp_path: Path,
) -> None:
    import py_compile

    build_dossier_spec(
        FIXTURES / "basic",
        cap_override="0.50USD",
        output=tmp_path / "out",
        key_path=_isolated_key(tmp_path),
        anchor="rekor_v2",
        _test_rekor_anchor_v2=_fake_v2_anchor(),
    )
    py_compile.compile(
        str(tmp_path / "out" / "verify_offline.py"), doraise=True
    )


def test_spec_anchor_none_has_no_transparency_block(
    tmp_path: Path,
) -> None:
    build_dossier_spec(
        FIXTURES / "basic",
        cap_override="0.50USD",
        output=tmp_path / "out",
        key_path=_isolated_key(tmp_path),
        anchor="none",
    )
    manifest = json.loads(
        (tmp_path / "out" / "manifest.json").read_text(encoding="utf-8")
    )
    assert "transparency_log" not in manifest


def test_spec_unknown_anchor_mode_refused(tmp_path: Path) -> None:
    with pytest.raises(DossierSpecError, match="unsupported anchor mode"):
        build_dossier_spec(
            FIXTURES / "basic",
            cap_override="0.50USD",
            output=tmp_path / "out",
            key_path=_isolated_key(tmp_path),
            anchor="bogus",
        )
