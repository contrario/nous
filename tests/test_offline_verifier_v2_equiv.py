"""
test_offline_verifier_v2_equiv.py -- anti-drift gate for P3d.

Asserts that the ASSEMBLED standalone v2 verifier (built by
offline_verifier_builder.build_offline_verifier_v2) and the IN-PACKAGE
verify_rekor_v2_anchor produce identical RekorV2VerifyDetail over the same
synthetic v2 anchor fixture. Any future divergence between the assembled
verifier and the package modules turns this red (axiom 8 / GAP1 pattern).

The assembled source is compiled and exec'd into an isolated namespace; no
pydantic is permitted in that namespace (the assembled verifier must run
cryptography + stdlib only). __session90_offline_verifier_v2_equiv_test_v1__
"""

from __future__ import annotations

import base64
import json

import pytest

import offline_verifier_builder as ovb


def _assemble_namespace():
    src = ovb.build_offline_verifier_v2()
    code = compile(src, "<assembled_verify_offline>", "exec")
    ns = {"__file__": "<assembled_verify_offline>"}
    exec(code, ns)  # noqa: S102
    return src, ns


def test_assembled_source_compiles_and_has_entrypoints():
    src, ns = _assemble_namespace()
    assert "import pydantic" not in src
    assert "from pydantic" not in src
    for name in (
        "verify_rekor_v2_anchor",
        "RekorAnchorV2",
        "RekorV2VerifyDetail",
        "load_trusted_log_keys",
        "parse_rekor_leaf",
        "parse_checkpoint",
        "verify_inclusion_proof",
        "main",
    ):
        assert name in ns, "assembled verifier missing " + name


def _malformed_v2_block():
    leaf = {
        "apiVersion": "0.0.2",
        "kind": "hashedrekord",
        "spec": {
            "hashedRekordV002": {
                "data": {
                    "algorithm": "SHA2_256",
                    "digest": base64.b64encode(b"\x00" * 32).decode(),
                },
                "signature": {
                    "content": base64.b64encode(b"\x00" * 8).decode(),
                    "verifier": {
                        "publicKey": {
                            "rawBytes": base64.b64encode(
                                b"\x00" * 8
                            ).decode()
                        }
                    },
                },
            }
        },
    }
    body_b64 = base64.b64encode(
        json.dumps(leaf).encode("utf-8")
    ).decode("ascii")
    return {
        "rekor_api_version": 2,
        "log_id": "test-log",
        "log_index": 0,
        "body_b64": body_b64,
        "checkpoint_envelope": "test-origin\n1\n"
        + base64.b64encode(b"\x00" * 32).decode() + "\n",
        "inclusion_proof_hashes": [],
    }


def test_assembled_matches_in_package_on_fixture():
    import rekor_verify_v2 as pkg

    _, ns = _assemble_namespace()
    body_bytes = b'{"world_name":"X"}'
    block = _malformed_v2_block()

    pkg_trusted = pkg.load_trusted_log_keys()
    asm_trusted = ns["load_trusted_log_keys"]()

    pkg_detail = pkg.verify_rekor_v2_anchor(
        manifest_body_bytes=body_bytes,
        block=block,
        trusted_log_keys=pkg_trusted,
    )
    asm_detail = ns["verify_rekor_v2_anchor"](
        manifest_body_bytes=body_bytes,
        block=block,
        trusted_log_keys=asm_trusted,
    )

    assert asm_detail.leaf_digest_ok == pkg_detail.leaf_digest_ok
    assert asm_detail.leaf_sig_ok == pkg_detail.leaf_sig_ok
    assert asm_detail.checkpoint_sig_ok == pkg_detail.checkpoint_sig_ok
    assert asm_detail.inclusion_proof_ok == pkg_detail.inclusion_proof_ok
    assert asm_detail.ok == pkg_detail.ok
    assert asm_detail.api_version == pkg_detail.api_version
    assert asm_detail.log_index == pkg_detail.log_index
    assert asm_detail.checkpoint_origin == pkg_detail.checkpoint_origin
    assert asm_detail.tree_size == pkg_detail.tree_size


def test_assembled_anchor_shim_rejects_non_v2_block():
    _, ns = _assemble_namespace()
    with pytest.raises(ns["RekorV2AnchorMalformed"]):
        ns["RekorAnchorV2"].from_manifest_block({"rekor_api_version": 1})


def test_assembled_anchor_shim_matches_package_malformed_paths():
    import rekor_verify_v2 as pkg

    _, ns = _assemble_namespace()
    bad_blocks = [
        {"rekor_api_version": 2},
        {"rekor_api_version": 2, "log_id": "", "log_index": 0,
         "body_b64": "x", "checkpoint_envelope": "y",
         "inclusion_proof_hashes": []},
        {"rekor_api_version": 2, "log_id": "a", "log_index": -1,
         "body_b64": "x", "checkpoint_envelope": "y",
         "inclusion_proof_hashes": []},
        {"rekor_api_version": 2, "log_id": "a", "log_index": 0,
         "body_b64": "x", "checkpoint_envelope": "y",
         "inclusion_proof_hashes": "notalist"},
    ]
    for blk in bad_blocks:
        pkg_raised = False
        asm_raised = False
        try:
            pkg.RekorAnchorV2.from_manifest_block(blk)
        except pkg.RekorV2AnchorMalformed:
            pkg_raised = True
        try:
            ns["RekorAnchorV2"].from_manifest_block(blk)
        except ns["RekorV2AnchorMalformed"]:
            asm_raised = True
        assert pkg_raised == asm_raised, (
            "shim/pkg disagree on malformed block: " + repr(blk)
        )
        assert pkg_raised is True
