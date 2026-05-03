"""
NOUS Phase 4 — manifest module tests.

Covers:
  - load_or_create_keypair generates a 0600 file
  - canonical_bytes deterministic across reorderings
  - sign + verify_manifest_signature round-trip
  - manifest_json + parse_manifest_json round-trip
  - Tampered manifest fails signature verification
  - Tampered signature fails verification
  - Public key encoding round-trips
  - manifest_from_verify populates required fields

# __nous_manifest_pytest_v1__
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from textwrap import dedent

import pytest
import tomllib

from ast_nodes import (
    CostCap, MindNode, NousProgram, SoulNode, TokensDecl, WorldNode,
)
from manifest import (
    Manifest,
    load_or_create_keypair,
    manifest_from_verify,
    manifest_json,
    parse_manifest_json,
    public_key_b64,
    sign_manifest,
    verify_manifest_signature,
)
from pricing import PricingTable
from smt_emit import emit_smt
from smt_verify import VerifyResult


PRICING_TOML = dedent("""\
    _schema_version = "2.0"
    _currency = "USD"

    [models."m1"]
    provider = "test"
    pricing_model = "per_token"
    input_per_1m = "1.00"
    output_per_1m = "5.00"
    reasoning_token_multiplier = "1.0"
    verified_date = "2026-04-28"
""")


@pytest.fixture
def pricing() -> PricingTable:
    data = tomllib.loads(PRICING_TOML)
    return PricingTable.model_validate(data)


@pytest.fixture
def synthetic_result(pricing: PricingTable):
    """Build a VerifyResult without invoking z3."""
    prog = NousProgram(
        world=WorldNode(
            name="MfTest",
            cost_cap=CostCap(amount=Decimal("0.10"), currency="USD"),
            max_ticks=2,
        ),
        souls=[SoulNode(
            name="S",
            mind=MindNode(model="m1", tier="Tier1"),
            tokens=TokensDecl(input=100, output=50),
        )],
    )
    spec = emit_smt(prog, pricing, today=date(2026, 4, 28))
    return VerifyResult(
        verdict="proven",
        spec=spec,
        solver_name="z3",
        solver_version="z3 4.16.0",
        elapsed_ms=23,
        timestamp_utc=datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ),
    )


# ─────────────────────────────────────────────────────────────────────
# Keypair management
# ─────────────────────────────────────────────────────────────────────

class TestKeypair:

    def test_create_writes_0600_key(self, tmp_path: Path) -> None:
        key_path = tmp_path / "k.pem"
        priv, pub, resolved = load_or_create_keypair(key_path)
        assert resolved == key_path
        assert key_path.is_file()
        assert (key_path.stat().st_mode & 0o777) == 0o600

    def test_load_existing_key_returns_same(
            self, tmp_path: Path) -> None:
        key_path = tmp_path / "k.pem"
        priv1, pub1, _ = load_or_create_keypair(key_path)
        priv2, pub2, _ = load_or_create_keypair(key_path)
        # Same public key bytes from both loads.
        assert public_key_b64(pub1) == public_key_b64(pub2)


# ─────────────────────────────────────────────────────────────────────
# manifest_from_verify
# ─────────────────────────────────────────────────────────────────────

class TestManifestBuilder:

    def test_populates_required_fields(self, synthetic_result) -> None:
        m = manifest_from_verify(synthetic_result, nous_version="4.13.0")
        assert m.schema_version == "1.0"
        assert m.nous_version == "4.13.0"
        assert m.verdict == "proven"
        assert m.world_name == "MfTest"
        assert m.cost_cap_usd == "0.10"
        assert m.max_ticks == 2
        assert len(m.smt_spec_sha256) == 64

    def test_canonical_bytes_deterministic(
            self, synthetic_result) -> None:
        m1 = manifest_from_verify(synthetic_result,
                                  nous_version="4.13.0")
        m2 = manifest_from_verify(synthetic_result,
                                  nous_version="4.13.0")
        assert m1.canonical_bytes() == m2.canonical_bytes()


# ─────────────────────────────────────────────────────────────────────
# Sign / verify round-trip
# ─────────────────────────────────────────────────────────────────────

class TestSignVerify:

    def test_signature_round_trip(self, tmp_path: Path,
                                  synthetic_result) -> None:
        priv, pub, _ = load_or_create_keypair(tmp_path / "k.pem")
        m = manifest_from_verify(synthetic_result,
                                 nous_version="4.13.0")
        sig = sign_manifest(m, priv)
        assert verify_manifest_signature(m, sig, pub)

    def test_signature_size(self, tmp_path: Path,
                            synthetic_result) -> None:
        """ed25519 signatures are exactly 64 bytes."""
        priv, _, _ = load_or_create_keypair(tmp_path / "k.pem")
        m = manifest_from_verify(synthetic_result,
                                 nous_version="4.13.0")
        sig = sign_manifest(m, priv)
        assert len(sig) == 64


# ─────────────────────────────────────────────────────────────────────
# JSON round-trip
# ─────────────────────────────────────────────────────────────────────

class TestJSONRoundTrip:

    def test_round_trip(self, tmp_path: Path,
                        synthetic_result) -> None:
        priv, pub, _ = load_or_create_keypair(tmp_path / "k.pem")
        m = manifest_from_verify(synthetic_result,
                                 nous_version="4.13.0")
        sig = sign_manifest(m, priv)
        doc = manifest_json(m, sig, pub)

        m2, sig2, pub2 = parse_manifest_json(doc)
        assert m2 == m
        assert sig2 == sig
        assert public_key_b64(pub2) == public_key_b64(pub)
        assert verify_manifest_signature(m2, sig2, pub2)

    def test_json_is_valid_json(self, tmp_path: Path,
                                synthetic_result) -> None:
        priv, pub, _ = load_or_create_keypair(tmp_path / "k.pem")
        m = manifest_from_verify(synthetic_result,
                                 nous_version="4.13.0")
        sig = sign_manifest(m, priv)
        doc = manifest_json(m, sig, pub)
        parsed = json.loads(doc)
        assert parsed["verdict"] == "proven"
        assert parsed["signature"]["algorithm"] == "ed25519"


# ─────────────────────────────────────────────────────────────────────
# Tamper detection
# ─────────────────────────────────────────────────────────────────────

class TestTamperDetection:

    def test_modified_field_breaks_signature(
            self, tmp_path: Path, synthetic_result) -> None:
        priv, pub, _ = load_or_create_keypair(tmp_path / "k.pem")
        m = manifest_from_verify(synthetic_result,
                                 nous_version="4.13.0")
        sig = sign_manifest(m, priv)
        doc = manifest_json(m, sig, pub)

        tampered = doc.replace('"MfTest"', '"Spoofed"')
        assert tampered != doc, "tamper must produce different text"
        m2, sig2, pub2 = parse_manifest_json(tampered)
        assert m2.world_name == "Spoofed"
        assert not verify_manifest_signature(m2, sig2, pub2)

    def test_swapped_signature_fails(
            self, tmp_path: Path, synthetic_result) -> None:
        """Replacing the signature with one for a different manifest
        must fail to verify."""
        priv, pub, _ = load_or_create_keypair(tmp_path / "k.pem")
        m1 = manifest_from_verify(synthetic_result,
                                  nous_version="4.13.0")

        # Build a different manifest by changing nous_version.
        # Decimal/cap fields aren't easy to vary without re-emitting,
        # so just rebuild with a different version string.
        m2 = manifest_from_verify(synthetic_result,
                                  nous_version="4.13.1")
        sig_for_m2 = sign_manifest(m2, priv)

        # Try to use m2's signature for m1.
        assert not verify_manifest_signature(m1, sig_for_m2, pub)

# __session70_phase5b_v2_schema_rename_v1__
