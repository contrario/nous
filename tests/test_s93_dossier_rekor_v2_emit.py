"""S93 P4(d): build_dossier(anchor='rekor_v2') emission structural tests.

Exercises the v2 anchored emit path offline via the _test_rekor_anchor_v2
hook (no live Rekor submit, no live TSA call). Asserts the rendered
manifest.json carries the v2 transparency_log block (rekor_api_version 2 +
rfc3161_token_b64) and that the emitted verify_offline.py is the v2 variant
with the pinned KNOWN_REKOR_V2_LOG_KEYS allowlist. Live cryptographic
end-to-end (real submit + timestamp, verifier exits 0) is proven at P4(f)
before the v5.11.0 release; static fixtures cannot bind a leaf signature to
a per-run manifest's canonical bytes.

# __nous_s93_dossier_rekor_v2_tests_v1__
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_DIR = _TESTS_DIR.parent
if str(_REPO_DIR) not in sys.path:
    sys.path.insert(0, str(_REPO_DIR))

from dossier import DossierError, build_dossier
from rekor_verify_v2 import RekorAnchorV2

TEMPLATE = _REPO_DIR / "templates" / "cost_cap_with_souls.nous"


@pytest.fixture
def proven_run(tmp_path: Path) -> tuple[Path, Path]:
    from cli_verify import cmd_verify

    src = tmp_path / "source.nous"
    shutil.copy2(TEMPLATE, src)

    class Args:
        file = str(src)
        smt = True
        prices = None
        timeout_ms = 30000
        no_manifest = False
        manifest_out = None
        key_path = None
        smt_margin = 0
        no_lint = True
        lint_strict = False
        lint_error_on = None

    rc = cmd_verify(Args())
    assert rc == 0
    manifest = src.with_suffix(".manifest.json")
    assert manifest.is_file()
    return src, manifest


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


def test_rekor_v2_emit_writes_standard_files(proven_run, tmp_path: Path) -> None:
    src, _ = proven_run
    output = tmp_path / "out"
    result = build_dossier(
        src,
        output=output,
        anchor="rekor_v2",
        _test_rekor_anchor_v2=_fake_v2_anchor(),
    )
    expected = {
        "source.nous",
        "manifest.json",
        "pricing.toml",
        "public_key.b64",
        "README.md",
        "verify_offline.py",
        "cost.farkas.json",  # __s170_leg2b_dossier_goldens_v1__
    }
    assert set(result.files) == expected
    for f in expected:
        assert (output / f).is_file()


def test_rekor_v2_manifest_has_v2_transparency_block(
    proven_run, tmp_path: Path
) -> None:
    src, _ = proven_run
    output = tmp_path / "out"
    build_dossier(
        src,
        output=output,
        anchor="rekor_v2",
        _test_rekor_anchor_v2=_fake_v2_anchor(),
    )
    manifest = json.loads(
        (output / "manifest.json").read_text(encoding="utf-8")
    )
    tlog = manifest.get("transparency_log")
    assert isinstance(tlog, dict)
    assert tlog.get("rekor_api_version") == 2
    assert tlog.get("rfc3161_token_b64") == "dGVzdC10b2tlbg=="
    assert tlog.get("log_id") == "test-log-id"
    assert tlog.get("body_b64") == "dGVzdC1ib2R5"


def test_rekor_v2_verifier_is_v2_variant(proven_run, tmp_path: Path) -> None:
    src, _ = proven_run
    output = tmp_path / "out"
    build_dossier(
        src,
        output=output,
        anchor="rekor_v2",
        _test_rekor_anchor_v2=_fake_v2_anchor(),
    )
    verify_text = (output / "verify_offline.py").read_text(encoding="utf-8")
    assert verify_text.startswith("#!/usr/bin/env python3")
    assert "KNOWN_REKOR_V2_LOG_KEYS" in verify_text
    assert "verify_rekor_v2_anchor" in verify_text
    assert "rekor_api_version" in verify_text


def test_rekor_v2_verifier_pins_production_log_key(
    proven_run, tmp_path: Path
) -> None:
    src, _ = proven_run
    output = tmp_path / "out"
    build_dossier(
        src,
        output=output,
        anchor="rekor_v2",
        _test_rekor_anchor_v2=_fake_v2_anchor(),
    )
    verify_text = (output / "verify_offline.py").read_text(encoding="utf-8")
    assert "log2025-1.rekor.sigstore.dev" in verify_text


def test_rekor_v2_verifier_is_byte_compilable(
    proven_run, tmp_path: Path
) -> None:
    import py_compile

    src, _ = proven_run
    output = tmp_path / "out"
    build_dossier(
        src,
        output=output,
        anchor="rekor_v2",
        _test_rekor_anchor_v2=_fake_v2_anchor(),
    )
    py_compile.compile(str(output / "verify_offline.py"), doraise=True)


def test_anchor_none_still_works(proven_run, tmp_path: Path) -> None:
    src, manifest = proven_run
    output = tmp_path / "out"
    build_dossier(src, output=output, anchor="none")
    emitted = json.loads(
        (output / "manifest.json").read_text(encoding="utf-8")
    )
    original = json.loads(manifest.read_text(encoding="utf-8"))
    assert emitted == original


def test_unknown_anchor_mode_refused(proven_run, tmp_path: Path) -> None:
    src, _ = proven_run
    with pytest.raises(DossierError, match="unsupported anchor mode"):
        build_dossier(src, output=tmp_path / "out", anchor="bogus")
