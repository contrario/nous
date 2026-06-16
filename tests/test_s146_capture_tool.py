from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "capture_phala_receipt.py"

pytestmark = pytest.mark.skipif(
    not _SCRIPT.exists(),
    reason="capture_phala_receipt.py not present in this build",
)


def _load():
    spec = importlib.util.spec_from_file_location("capture_phala_receipt", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_compute_sha256_hex_matches_hashlib() -> None:
    cap = _load()
    data = b'{"model":"phala/x","messages":[]}'
    assert cap.compute_sha256_hex(data) == hashlib.sha256(data).hexdigest()


def test_build_text_is_colon_joined() -> None:
    cap = _load()
    assert cap.build_text("a" * 64, "b" * 64) == ("a" * 64) + ":" + ("b" * 64)


def test_build_bundle_shapes_and_self_consistency() -> None:
    cap = _load()
    request_body = b'{"model":"phala/x","messages":[{"role":"user","content":"hi"}],"stream":false}'
    response_body = b'{"id":"chatcmpl-1","usage":{"prompt_tokens":3,"completion_tokens":2}}'
    bundle = cap.build_bundle(
        model="phala/x",
        base_url="https://api.redpill.ai/v1",
        request_body=request_body,
        response_body=response_body,
        signature_hex="ab12",
        signing_address="0xdead",
        intel_quote="qqq",
        nvidia_payload="nnn",
        captured_at="2026-06-16T00:00:00+00:00",
    )
    assert bundle["scheme"] == "phala_response_sig_v1"
    assert bundle["request_sha256"] == hashlib.sha256(request_body).hexdigest()
    assert bundle["response_sha256"] == hashlib.sha256(response_body).hexdigest()
    assert bundle["text"] == f"{bundle['request_sha256']}:{bundle['response_sha256']}"
    assert bundle["request_body"] == request_body.decode("utf-8")
    assert bundle["response_body"] == response_body.decode("utf-8")


def test_assert_bundle_consistent_raises_on_mismatch() -> None:
    cap = _load()
    bundle = {"text": "aa:bb"}
    cap.assert_bundle_consistent(bundle, "aa:bb")
    with pytest.raises(RuntimeError):
        cap.assert_bundle_consistent(bundle, "aa:cc")


def test_main_with_empty_key_returns_2_without_network() -> None:
    cap = _load()
    assert cap.main(["--out", "/tmp/_unused_s146.json", "--api-key", ""]) == 2
