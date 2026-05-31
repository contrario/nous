"""Per-world memory signing key and explicit init ceremony (S105 Phase 0).

Implements the Section 5a provisioning model of docs/MEMORY_EVIDENCE_DESIGN.md.
Memory entries are signed with a PERSISTENT per-world Ed25519 key, created by an
explicit ceremony that writes a signed genesis keyring entry (the trusted-set
root). Writes to an uninitialized world are refused, never auto-created.

Phase 0 scope: sign and record only. Trusted-set membership verification is
Phase 2 and is not implemented here.

# __s105_memory_keyring_module_v1__
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from pydantic import BaseModel, ConfigDict, Field

MEMORY_KEYRING_SOURCE_KIND: str = "nous_memory_keyring_v1"


class MemoryKeyringError(RuntimeError):
    """Raised on a memory keyring provisioning error."""


class MemoryKeyringSignature(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    algorithm: str = Field(default="ed25519")
    public_key_b64: str = Field(min_length=1)
    signature_b64: str = Field(min_length=1)


class MemoryKeyringEntry(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    source_kind: str = Field(default=MEMORY_KEYRING_SOURCE_KIND)
    world_sha256: str = Field(min_length=64, max_length=64)
    public_key_b64: str = Field(min_length=1)
    key_id: str = Field(min_length=64, max_length=64)
    created_at: str = Field(min_length=1)
    signature: Optional[MemoryKeyringSignature] = Field(default=None)

    def canonical_body_bytes(self) -> bytes:
        doc = self.model_dump(exclude={"signature"})
        return json.dumps(
            doc, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")


def _public_key_raw_b64(public_key: Ed25519PublicKey) -> str:
    raw: bytes = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def key_id_for(public_key_b64: str) -> str:
    raw: bytes = base64.b64decode(public_key_b64, validate=True)
    return hashlib.sha256(raw).hexdigest()


def _world_dir(world_sha256: str, base_dir: Path) -> Path:
    if len(world_sha256) != 64:
        raise MemoryKeyringError("world_sha256 must be 64 hex chars")
    return Path(base_dir) / "memory" / world_sha256


def _key_path(world_sha256: str, base_dir: Path) -> Path:
    return _world_dir(world_sha256, base_dir) / "signing.key"


def _genesis_path(world_sha256: str, base_dir: Path) -> Path:
    return _world_dir(world_sha256, base_dir) / "genesis_keyring.json"


def is_initialized(world_sha256: str, base_dir: Path) -> bool:
    return _genesis_path(world_sha256, base_dir).is_file()


def _atomic_write(path: Path, data: bytes, mode: int) -> None:
    fd, tmp = tempfile.mkstemp(suffix=".tmp", prefix=path.name + ".", dir=str(path.parent))
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    os.chmod(tmp, mode)
    os.replace(tmp, str(path))


def init_world_memory(
    world_sha256: str,
    base_dir: Path,
) -> tuple[str, str]:
    """Explicit ceremony. Returns (public_key_b64, key_id).

    REFUSES if the world is already initialized (idempotent caller should check
    is_initialized first; here a second init raises). Generates a persistent
    Ed25519 keypair (PEM, 0600; parent dir 0700) and writes a signed genesis
    keyring entry. Never auto-invoked by a write path.
    """
    wdir = _world_dir(world_sha256, base_dir)
    genesis = _genesis_path(world_sha256, base_dir)
    if genesis.is_file():
        raise MemoryKeyringError(
            f"world {world_sha256} already initialized; genesis keyring exists"
        )

    wdir.mkdir(parents=True, exist_ok=True)
    os.chmod(str(wdir), 0o700)

    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    pem: bytes = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    _atomic_write(_key_path(world_sha256, base_dir), pem, 0o600)

    pub_b64 = _public_key_raw_b64(public)
    kid = key_id_for(pub_b64)
    entry = MemoryKeyringEntry(
        world_sha256=world_sha256,
        public_key_b64=pub_b64,
        key_id=kid,
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    body = entry.canonical_body_bytes()
    raw_sig = private.sign(body)
    signed = MemoryKeyringEntry(
        source_kind=entry.source_kind,
        world_sha256=entry.world_sha256,
        public_key_b64=entry.public_key_b64,
        key_id=entry.key_id,
        created_at=entry.created_at,
        signature=MemoryKeyringSignature(
            algorithm="ed25519",
            public_key_b64=pub_b64,
            signature_b64=base64.b64encode(raw_sig).decode("ascii"),
        ),
    )
    out = json.dumps(signed.model_dump(), sort_keys=True, separators=(",", ":"))
    _atomic_write(genesis, out.encode("utf-8"), 0o644)
    return pub_b64, kid


def load_world_signing_key(
    world_sha256: str,
    base_dir: Path,
) -> Ed25519PrivateKey:
    """Load the persistent per-world signing key. REFUSE if not initialized."""
    if not is_initialized(world_sha256, base_dir):
        raise MemoryKeyringError(
            f"memory not initialized for world {world_sha256}; run nous memory init"
        )
    key_path = _key_path(world_sha256, base_dir)
    if not key_path.is_file():
        raise MemoryKeyringError(
            f"genesis present but signing key missing for world {world_sha256}"
        )
    private = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    if not isinstance(private, Ed25519PrivateKey):
        raise MemoryKeyringError(f"key for world {world_sha256} is not Ed25519")
    return private


def load_genesis_entry(
    world_sha256: str,
    base_dir: Path,
) -> MemoryKeyringEntry:
    """Load and parse the signed genesis keyring entry. REFUSE if absent."""
    genesis = _genesis_path(world_sha256, base_dir)
    if not genesis.is_file():
        raise MemoryKeyringError(
            f"memory not initialized for world {world_sha256}"
        )
    doc = json.loads(genesis.read_text(encoding="utf-8"))
    return MemoryKeyringEntry(**doc)


def verify_keyring_entry_signature(entry: MemoryKeyringEntry) -> bool:
    if entry.signature is None:
        return False
    if entry.signature.algorithm != "ed25519":
        return False
    try:
        pub_raw: bytes = base64.b64decode(
            entry.signature.public_key_b64, validate=True
        )
        raw_sig: bytes = base64.b64decode(
            entry.signature.signature_b64, validate=True
        )
        public_key = Ed25519PublicKey.from_public_bytes(pub_raw)
        public_key.verify(raw_sig, entry.canonical_body_bytes())
        return True
    except Exception:
        return False
