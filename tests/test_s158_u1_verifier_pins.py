# S158 U1: verifier_pins parallel array on the verifier-digest registry.
# Drop-when-empty byte-identity + fail-closed pin normalization. Portable:
# no dependency on the published website registry.
from __future__ import annotations

import base64

import pytest

import verifier_registry as vr

_ENTRY = {
    "template_name": "VERIFY_OFFLINE_PY",
    "template_sha256": "a" * 64,
    "nous_version": "5.56.0",
}
_PUB_B64 = base64.b64encode(bytes([1] * 32)).decode("ascii")
_PIN = {
    "verifier_id": "https://nous-lang.org/vsa/verifier/v1",
    "public_key_b64": _PUB_B64,
}


def _body_keys(reg):
    return sorted(
        k for k in reg.keys() if k not in ("signature", "rekor_anchor")
    )


def test_no_pins_body_is_unchanged():
    reg = vr.build_registry([_ENTRY])
    assert _body_keys(reg) == ["entries", "registry_schema"]
    assert "verifier_pins" not in reg


def test_empty_pins_dropped_byte_identical():
    a = vr.build_registry([_ENTRY])
    b = vr.build_registry([_ENTRY], verifier_pins=[])
    assert "verifier_pins" not in b
    assert vr.canonical_registry_body_bytes(
        a
    ) == vr.canonical_registry_body_bytes(b)


def test_none_pins_dropped_byte_identical():
    a = vr.build_registry([_ENTRY])
    b = vr.build_registry([_ENTRY], verifier_pins=None)
    assert vr.canonical_registry_body_bytes(
        a
    ) == vr.canonical_registry_body_bytes(b)


def test_pin_present_entries_and_schema_unchanged():
    base = vr.build_registry([_ENTRY])
    reg = vr.build_registry([_ENTRY], verifier_pins=[_PIN])
    assert reg["entries"] == base["entries"]
    assert reg["registry_schema"] == base["registry_schema"]
    assert reg["verifier_pins"] == [
        {"public_key_b64": _PUB_B64, "verifier_id": _PIN["verifier_id"]}
    ]


def test_pins_sorted_deterministically():
    p1 = {"verifier_id": "https://b", "public_key_b64": _PUB_B64}
    p2 = {"verifier_id": "https://a", "public_key_b64": _PUB_B64}
    reg = vr.build_registry([_ENTRY], verifier_pins=[p1, p2])
    assert [p["verifier_id"] for p in reg["verifier_pins"]] == [
        "https://a",
        "https://b",
    ]


def test_refuse_missing_verifier_id():
    with pytest.raises(vr.RegistryError):
        vr.build_registry(
            [_ENTRY], verifier_pins=[{"public_key_b64": _PUB_B64}]
        )


def test_refuse_bad_pubkey_length():
    bad = base64.b64encode(bytes([1] * 31)).decode("ascii")
    with pytest.raises(vr.RegistryError):
        vr.build_registry(
            [_ENTRY],
            verifier_pins=[
                {"verifier_id": "https://x", "public_key_b64": bad}
            ],
        )


def test_refuse_non_base64_pubkey():
    with pytest.raises(vr.RegistryError):
        vr.build_registry(
            [_ENTRY],
            verifier_pins=[
                {"verifier_id": "https://x", "public_key_b64": "not_b64!!"}
            ],
        )


def test_refuse_duplicate_verifier_id():
    with pytest.raises(vr.RegistryError):
        vr.build_registry([_ENTRY], verifier_pins=[_PIN, dict(_PIN)])
