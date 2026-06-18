"""S155 U2: compute_codegen_sha256 binds a trace to the compiled artifact.

The helper is the SINGLE definition of the codegen digest. The producer
(run harness, U3) and the verifier (nous verify --source, U4) both import
it, so the stamped digest and the re-derived digest agree by construction
(the S154 single-source lesson applied to the fourth subject leg). The
digest is computed over the exact bytes of generate_python(parse_nous(src))
-- the same artifact the run harness compiles and executes -- and the
generated header carries no version string, timestamp, or nonce, so it is a
pure, deterministic function of the source and codegen logic.

# __s155_u2_codegen_digest_test_module_v1__
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import run_shas
from run_shas import compute_codegen_sha256, RunShasError
from parser import parse_nous
from codegen import generate_python

_REPO = Path(run_shas.__file__).resolve().parent
_SRC = (_REPO / "gate_alpha.nous").read_text(encoding="utf-8")


def test_codegen_sha256_refuses_empty() -> None:
    with pytest.raises(RunShasError):
        compute_codegen_sha256("")


def test_codegen_sha256_refuses_non_str() -> None:
    with pytest.raises(RunShasError):
        compute_codegen_sha256(None)  # type: ignore[arg-type]


def test_codegen_sha256_is_64_hex() -> None:
    digest = compute_codegen_sha256(_SRC)
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_codegen_sha256_deterministic() -> None:
    assert compute_codegen_sha256(_SRC) == compute_codegen_sha256(_SRC)


def test_codegen_sha256_matches_manual_generate_python() -> None:
    manual = hashlib.sha256(
        generate_python(parse_nous(_SRC)).encode("utf-8")
    ).hexdigest()
    assert compute_codegen_sha256(_SRC) == manual


def test_codegen_sha256_is_over_generated_not_source() -> None:
    source_digest = hashlib.sha256(_SRC.encode("utf-8")).hexdigest()
    assert compute_codegen_sha256(_SRC) != source_digest
