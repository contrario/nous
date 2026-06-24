"""
S172 P0(b)-1 -- pure release-VSA bundle assembler + index generator.

Reproduces the published 5.60.1 release-VSA bundle and index from their parts,
fully offline (no network, no Rekor write), proving the Phase-2 pure functions
emit the exact published artifacts before any live anchor. Skips when the
5.60.1 reference dir is not present (clean-venv / sdist).

# __s172_p0b1_test_release_bundle_index_v1__
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

import mint_release_vsa as M

_REPO = Path(__file__).resolve().parent.parent
_REF = _REPO / "website" / ".well-known" / "nous" / "release-vsa" / "5.60.1"
_VER = "5.60.1"
_PIN = "E3FNG9zFMRjhg/iVkOu9K3gH5mmG6Uwvdy8EvwHsYVo="

pytestmark = pytest.mark.skipif(
    not _REF.is_dir(),
    reason="5.60.1 release-VSA reference dir not present (clean-venv/sdist)",
)


def _load(name: str) -> dict:
    return json.loads((_REF / name).read_text(encoding="utf-8"))


def _published_bundle() -> dict:
    return _load("nous_lang-5.60.1.rekor-v2-bundle.json")


def _published_index() -> dict:
    return _load("index.json")


def _published_vsa() -> dict:
    return _load("nous_lang-5.60.1.build-vsa.intoto.json")


class _Anchor:
    def __init__(self, tle: dict) -> None:
        ip = tle["inclusion_proof"]
        self.body_b64 = tle["canonicalized_body"]
        self.checkpoint_envelope = ip["checkpoint"]
        self.inclusion_proof_hashes = ip["hashes"]
        self.log_index = tle["log_index"]


def test_assemble_rekor_bundle_reproduces_5_60_1() -> None:
    published = _published_bundle()
    anchor = _Anchor(published["transparency_log_entry"])
    token_der = base64.b64decode(published["rfc3161_timestamp"])
    rebuilt = M.assemble_rekor_bundle(anchor, token_der)
    assert rebuilt == published
    canon = json.dumps(rebuilt, sort_keys=True, indent=2).encode("utf-8")
    on_disk = (_REF / "nous_lang-5.60.1.rekor-v2-bundle.json").read_bytes()
    assert canon == on_disk


def test_helpers_match_5_60_1() -> None:
    body = _published_bundle()["transparency_log_entry"]["canonicalized_body"]
    idx = _published_index()
    rekor = [a for a in idx["artifacts"] if a["kind"] == "rekor_v2_transparency_log"][0]
    assert M._leaf_hash_hex(body) == rekor["leafHash"]
    assert M._anchored_digest_hex(body) == rekor["anchoredDigestSha256"]
    assert M._entry_kind(body) == rekor["entryKind"]
    assert M.vsa_payload_sha256(_published_vsa()) == idx["vsaPayloadSha256"]


def test_build_release_index_reproduces_5_60_1() -> None:
    published_idx = _published_index()
    bundle = _published_bundle()
    statement = M.decode_build_vsa_statement(_published_vsa())
    rekor = [a for a in published_idx["artifacts"] if a["kind"] == "rekor_v2_transparency_log"][0]
    rebuilt = M.build_release_index(
        _VER,
        _REF,
        statement=statement,
        bundle=bundle,
        bundle_filename="nous_lang-5.60.1.rekor-v2-bundle.json",
        vsa_filename="nous_lang-5.60.1.build-vsa.intoto.json",
        verifier_filename="verify_build_vsa_offline.py",
        verifier_key_filename="release-verifier-key.json",
        operator_pin_b64=_PIN,
        vsa_payload_sha256_hex=published_idx["vsaPayloadSha256"],
        rfc3161_gen_time=rekor["rfc3161GenTime"],
        emitted_at=published_idx["emittedAt"],
    )
    assert rebuilt == published_idx
    canon = json.dumps(rebuilt, sort_keys=True, indent=2).encode("utf-8")
    on_disk = (_REF / "index.json").read_bytes()
    assert canon == on_disk


def test_build_index_binding_self_check_refuses_on_mismatch() -> None:
    bundle = _published_bundle()
    statement = M.decode_build_vsa_statement(_published_vsa())
    with pytest.raises(M.MintError):
        M.build_release_index(
            _VER,
            _REF,
            statement=statement,
            bundle=bundle,
            bundle_filename="nous_lang-5.60.1.rekor-v2-bundle.json",
            vsa_filename="nous_lang-5.60.1.build-vsa.intoto.json",
            verifier_filename="verify_build_vsa_offline.py",
            verifier_key_filename="release-verifier-key.json",
            operator_pin_b64=_PIN,
            vsa_payload_sha256_hex="00" * 32,
            rfc3161_gen_time="2026-06-22T10:02:24Z",
            emitted_at="2026-06-22T02:16:35Z",
        )
