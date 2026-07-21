"""C2 manifest identity: trace_bundle_anchor_sha256 round-trips with its C1
sibling through sign -> render -> parse, and the re-signed manifest verifies
under the emitted verifier's exact body preimage.

This is the manifest-layer proof for Step 1 of the C2 (bundle temporal
existence) mapping. It exercises the PRODUCTION path parse_manifest_json,
which is where a missing parse-side hydration silently drops the field
(the bug the C1 e2e probe caught). Both fields must survive together so the
§3.1.2 invariant "C2 presupposes C1" can be enforced downstream by the
verifier over a manifest that actually carries both.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import base64
import dataclasses
import json
import shutil

import pytest

manifest_mod = pytest.importorskip("manifest")
cli_verify = pytest.importorskip("cli_verify")

_REPO = _Path(__file__).resolve().parent.parent
_TEMPLATE = _REPO / "templates" / "cost_cap_with_souls.nous"

_C1 = "ab" * 32
_C2 = "cd" * 32


def _signed_parsed(tmp_path):
    if not _TEMPLATE.is_file():
        pytest.skip("cost_cap_with_souls.nous template not present")
    src = tmp_path / "source.nous"
    shutil.copy2(_TEMPLATE, src)

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

    if cli_verify.cmd_verify(Args()) != 0:
        pytest.skip("cmd_verify could not prove the template (env issue)")
    text = src.with_suffix(".manifest.json").read_text(encoding="utf-8")
    parsed, _sig, _pub = manifest_mod.parse_manifest_json(text)
    return parsed


def test_both_fields_round_trip_through_parse(tmp_path):
    parsed = _signed_parsed(tmp_path)
    parsed = dataclasses.replace(
        parsed, trace_bundle_sha256=_C1, trace_bundle_anchor_sha256=_C2)
    priv, pub, _ = manifest_mod.load_or_create_keypair(None)
    doc = manifest_mod.manifest_json(
        parsed, manifest_mod.sign_manifest(parsed, priv), pub)

    rp, sig, pub2 = manifest_mod.parse_manifest_json(doc)
    assert rp.trace_bundle_sha256 == _C1
    assert rp.trace_bundle_anchor_sha256 == _C2
    assert manifest_mod.verify_manifest_signature(rp, sig, pub2)


def test_both_fields_present_in_rendered_body_and_verify(tmp_path):
    parsed = _signed_parsed(tmp_path)
    parsed = dataclasses.replace(
        parsed, trace_bundle_sha256=_C1, trace_bundle_anchor_sha256=_C2)
    priv, pub, _ = manifest_mod.load_or_create_keypair(None)
    doc = manifest_mod.manifest_json(
        parsed, manifest_mod.sign_manifest(parsed, priv), pub)

    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )
    dj = json.loads(doc)
    assert dj.get("trace_bundle_sha256") == _C1
    assert dj.get("trace_bundle_anchor_sha256") == _C2
    body = {k: v for k, v in dj.items() if k != "signature"}
    bb = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    pk = Ed25519PublicKey.from_public_bytes(
        base64.b64decode(dj["signature"]["public_key_b64"]))
    pk.verify(base64.b64decode(dj["signature"]["signature_b64"]), bb)


def test_parse_keeps_fields_independent(tmp_path):
    # The manifest layer must not couple the fields; the verifier (not the
    # parser) enforces C2 => C1. A manifest with C2 set and C1 None must
    # parse back with exactly that shape.
    parsed = _signed_parsed(tmp_path)
    only_c2 = dataclasses.replace(
        parsed, trace_bundle_sha256=None, trace_bundle_anchor_sha256=_C2)
    priv, pub, _ = manifest_mod.load_or_create_keypair(None)
    doc = manifest_mod.manifest_json(
        only_c2, manifest_mod.sign_manifest(only_c2, priv), pub)
    rp, _sig, _pub = manifest_mod.parse_manifest_json(doc)
    assert rp.trace_bundle_sha256 is None
    assert rp.trace_bundle_anchor_sha256 == _C2


def test_absent_field_omitted_from_canonical(tmp_path):
    # Default None => the field must not appear in the rendered manifest, so
    # existing manifests remain byte-identical (no forced field).
    parsed = _signed_parsed(tmp_path)
    priv, pub, _ = manifest_mod.load_or_create_keypair(None)
    doc = manifest_mod.manifest_json(
        parsed, manifest_mod.sign_manifest(parsed, priv), pub)
    dj = json.loads(doc)
    assert "trace_bundle_anchor_sha256" not in dj
