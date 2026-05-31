"""S105 -- per-world memory key + init ceremony (Phase 0 unit 2).

# __s105_memory_keyring_tests_v1__
"""
from __future__ import annotations

from pathlib import Path

import pytest

from memory_keyring import (
    MemoryKeyringError,
    init_world_memory,
    is_initialized,
    key_id_for,
    load_genesis_entry,
    load_world_signing_key,
    verify_keyring_entry_signature,
)

_W = "b" * 64


def test_init_creates_key_and_signed_genesis(tmp_path: Path) -> None:
    assert is_initialized(_W, tmp_path) is False
    pub_b64, kid = init_world_memory(_W, tmp_path)
    assert is_initialized(_W, tmp_path) is True
    assert kid == key_id_for(pub_b64)
    keyfile = tmp_path / "memory" / _W / "signing.key"
    assert keyfile.is_file()
    assert (keyfile.stat().st_mode & 0o777) == 0o600


def test_genesis_entry_signature_verifies(tmp_path: Path) -> None:
    init_world_memory(_W, tmp_path)
    entry = load_genesis_entry(_W, tmp_path)
    assert entry.signature is not None
    assert entry.world_sha256 == _W
    assert verify_keyring_entry_signature(entry) is True


def test_double_init_refused(tmp_path: Path) -> None:
    init_world_memory(_W, tmp_path)
    with pytest.raises(MemoryKeyringError):
        init_world_memory(_W, tmp_path)


def test_load_signing_key_refuses_uninitialized(tmp_path: Path) -> None:
    with pytest.raises(MemoryKeyringError):
        load_world_signing_key(_W, tmp_path)


def test_load_signing_key_after_init(tmp_path: Path) -> None:
    init_world_memory(_W, tmp_path)
    key = load_world_signing_key(_W, tmp_path)
    sig = key.sign(b"x")
    assert isinstance(sig, bytes) and len(sig) == 64


def test_distinct_worlds_distinct_keys(tmp_path: Path) -> None:
    w2 = "c" * 64
    p1, _ = init_world_memory(_W, tmp_path)
    p2, _ = init_world_memory(w2, tmp_path)
    assert p1 != p2
