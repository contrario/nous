"""Anti-drift gate for the RFC 3161 timestamp path in the assembled
standalone v2 verifier (S92 b4).

Complements test_offline_verifier_v2_equiv: asserts that the assembled
verifier hoists the tsa_verify machinery (pydantic-free) and that, on a v2
anchor carrying an rfc3161_token_b64, the assembled verify_rekor_v2_anchor
produces the same timestamp_ok / trusted_time as the in-package one. The
token is the deterministic v2ts fixture (an RFC 3161 token over the fixture
leaf signature); its self-signed root is injected via trusted_tsa_roots.
No network I/O.

# __nous_s92_offline_verifier_tsa_test_v1__
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import offline_verifier_builder as ovb
import rekor_verify_v2 as pkg

_FIX = Path(__file__).parent / "tsa_fixtures"


def _assemble():
    src = ovb.build_offline_verifier_v2()
    ns = {"__file__": "<assembled_verify_offline>"}
    exec(compile(src, "<assembled_verify_offline>", "exec"), ns)  # noqa: S102
    return src, ns


def _token_block():
    manifest = (_FIX / "v2ts_manifest.bin").read_bytes()
    sig = (_FIX / "v2ts_sig.der").read_bytes()
    pub = (_FIX / "v2ts_pub.der").read_bytes()
    token = (_FIX / "v2ts_token.der").read_bytes()
    digest = hashlib.sha256(manifest).digest()
    leaf = {
        "kind": "hashedrekord",
        "apiVersion": "0.0.2",
        "spec": {
            "hashedRekordV002": {
                "data": {
                    "algorithm": "SHA2_256",
                    "digest": base64.b64encode(digest).decode(),
                },
                "signature": {
                    "content": base64.b64encode(sig).decode(),
                    "verifier": {
                        "keyDetails": "PKIX_ECDSA_P256_SHA_256",
                        "publicKey": {
                            "rawBytes": base64.b64encode(pub).decode()
                        },
                    },
                },
            }
        },
    }
    block = {
        "rekor_api_version": 2,
        "log_id": "x",
        "log_index": 0,
        "body_b64": base64.b64encode(json.dumps(leaf).encode()).decode(),
        "checkpoint_envelope": "o\n1\n"
        + base64.b64encode(b"\x00" * 32).decode() + "\n",
        "inclusion_proof_hashes": [],
        "rfc3161_token_b64": base64.b64encode(token).decode(),
    }
    return manifest, block


def test_assembled_has_tsa_symbols_and_no_pydantic() -> None:
    src, ns = _assemble()
    assert "import pydantic" not in src
    assert "from pydantic" not in src
    for name in (
        "verify_rfc3161_timestamp",
        "Rfc3161Malformed",
        "KNOWN_TSA_ROOT_CERTS",
        "Rfc3161VerifyDetail",
    ):
        assert name in ns, "assembled verifier missing " + name


def test_assembled_timestamp_matches_package() -> None:
    _, ns = _assemble()
    manifest, block = _token_block()
    root = (_FIX / "v2ts_root.pem").read_text()
    pkg_detail = pkg.verify_rekor_v2_anchor(
        manifest_body_bytes=manifest,
        block=block,
        trusted_log_keys={},
        trusted_tsa_roots=[root],
    )
    asm_detail = ns["verify_rekor_v2_anchor"](
        manifest_body_bytes=manifest,
        block=block,
        trusted_log_keys={},
        trusted_tsa_roots=[root],
    )
    assert pkg_detail.timestamp_ok is True
    assert asm_detail.timestamp_ok == pkg_detail.timestamp_ok
    assert asm_detail.trusted_time == pkg_detail.trusted_time


def test_assembled_default_roots_reject_fixture_token() -> None:
    _, ns = _assemble()
    manifest, block = _token_block()
    asm_detail = ns["verify_rekor_v2_anchor"](
        manifest_body_bytes=manifest,
        block=block,
        trusted_log_keys={},
    )
    assert asm_detail.timestamp_ok is False


def test_assembled_anchor_shim_carries_token_attr() -> None:
    _, ns = _assemble()
    _, block = _token_block()
    anchor = ns["RekorAnchorV2"].from_manifest_block(block)
    assert anchor.rfc3161_token_b64 == block["rfc3161_token_b64"]
