"""FG-S427-I: pricing evidence for dossier fixtures assembled by hand.

Every dossier verifier binds pricing.canonical.json to the signed
manifest's pricing_sha256 and checks that each price in it is a finite
number >= 0 (FG-S427-I). A test that assembles a dossier by hand writes
these bytes into it and puts SHA into the manifest before it signs, so
the fixture has the shape build_dossier emits. The bytes are what
pricing.PricingTable.canonical_bytes() makes for TOML: the m1 entry of
test_s97_certificate.PRICING_TOML at a fixed date.

__fg_s427_i_pricing_evidence_v1__
"""
from __future__ import annotations

import tomllib
from pathlib import Path

import pricing

TOML = """\
_schema_version = "2.0"
_currency = "USD"
[models."m1"]
provider = "test"
pricing_model = "per_token"
input_per_1m = "1.00"
output_per_1m = "5.00"
reasoning_token_multiplier = "1.0"
verified_date = "2026-11-01"
"""
_TABLE = pricing.PricingTable.model_validate(tomllib.loads(TOML))
CANONICAL = _TABLE.canonical_bytes()
SHA = _TABLE.sha256()


def write(directory) -> str:
    """Write pricing.canonical.json into directory; return its sha256."""
    (Path(directory) / "pricing.canonical.json").write_bytes(CANONICAL)
    return SHA
