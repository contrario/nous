"""
test_rekor_v2_live_log.py -- parse + key-ID match against a real checkpoint
captured from the production Rekor v2 log (log2025-1.rekor.sigstore.dev),
P3e.

Two assertions, both against real bytes (not synthetic):

  1. parse_checkpoint accepts the real C2SP checkpoint envelope and yields
     the expected origin, tree_size, root_hash, and a signature line whose
     key_name matches the origin. Parse-only: no full inclusion-proof chain
     is verified here (the captured checkpoint is not paired with a leaf and
     proof), but it proves the parser handles production bytes, not only
     synthetic ones.

  2. The C2SP Ed25519 key ID computed from the PINNED production log key
     (KNOWN_REKOR_V2_LOG_KEYS['log2025-1.rekor.sigstore.dev']) via the
     in-package ed25519_key_id equals the 4-byte key ID parsed from the real
     checkpoint signature line. This proves the pinned key + key-ID matching
     are correct against the live log, not asserted by hand.

__session90_rekor_v2_live_log_v1__
"""

from __future__ import annotations

import base64
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

import rekor_verify_v2 as pkg
from rekor_checkpoint import ed25519_key_id, parse_checkpoint

_FIXTURE = (
    Path(__file__).parent / "rekor_fixtures" / "real_checkpoint_log2025-1.txt"
)
_ORIGIN = "log2025-1.rekor.sigstore.dev"
_EXPECTED_TREE_SIZE = 4558960
_EXPECTED_ROOT_B64 = "4aTJ6f2zLnL+mPfarg+rm9NFEUCBZGsKGYvG3sYNlBc="


def test_real_checkpoint_parses():
    envelope = _FIXTURE.read_text(encoding="utf-8")
    cp = parse_checkpoint(envelope)
    assert cp.origin == _ORIGIN
    assert cp.tree_size == _EXPECTED_TREE_SIZE
    assert cp.root_hash == base64.b64decode(_EXPECTED_ROOT_B64)
    assert len(cp.signatures) == 1
    assert cp.signatures[0].key_name == _ORIGIN


def test_pinned_key_id_matches_real_checkpoint():
    envelope = _FIXTURE.read_text(encoding="utf-8")
    cp = parse_checkpoint(envelope)
    pinned_b64 = pkg.KNOWN_REKOR_V2_LOG_KEYS.get(_ORIGIN)
    assert pinned_b64 is not None, (
        "production log key for " + _ORIGIN
        + " is not pinned in KNOWN_REKOR_V2_LOG_KEYS"
    )
    pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(pinned_b64))
    computed = ed25519_key_id(_ORIGIN, pub)
    assert computed == cp.signatures[0].key_id, (
        "C2SP key ID from pinned key " + computed.hex()
        + " does not match real checkpoint key ID "
        + cp.signatures[0].key_id.hex()
    )
