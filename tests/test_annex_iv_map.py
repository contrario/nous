"""Tests for the Annex IV evidence-map sidecar (S135).

Pure, test-only. Builds a synthetic dossier directory, signs the map with an
ephemeral Ed25519 key, and exercises the offline verifier's PASS path plus
every fail-closed branch. No NOUS install, no network, no real keypair file.

# __s135_annex_iv_map_tests_v1__
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

import annex_iv_map
from annex_iv_map import (
    ANNEX_IV_ITEMS,
    AnnexIvMapError,
    build_annex_iv_map,
    serialize_annex_iv_map,
    verify_annex_iv_map,
)


def _write_manifest(dossier_dir: Path) -> None:
    manifest = {
        "schema_version": 3,
        "nous_version": "5.37.0",
        "smt_emit_version": "1.0",
        "source_sha256": "a" * 64,
        "pricing_sha256": "b" * 64,
        "smt_spec_sha256": "c" * 64,
        "world_name": "TestWorld",
        "cost_cap_usd": "0.20",
        "max_ticks": 3,
        "verdict": "proven",
        "solver_name": "z3",
        "solver_version": "4.16.0",
        "elapsed_ms": 12,
        "timestamp_utc": "2026-06-12T00:00:00+00:00",
        "transparency_log": {"provider": "sigstore-rekor", "log_index": 42},
        "signature": {
            "public_key_b64": "ZmFrZQ==",
            "signature_b64": "ZmFrZXNpZw==",
        },
    }
    (dossier_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _make_dossier(dossier_dir: Path) -> None:
    _write_manifest(dossier_dir)
    (dossier_dir / "source.nous").write_bytes(b"world TestWorld {}\n")
    (dossier_dir / "README.md").write_text("# dossier\n", encoding="utf-8")
    (dossier_dir / "public_key.b64").write_text("ZmFrZQ==\n", encoding="utf-8")


def _resign(doc: dict, priv: Ed25519PrivateKey) -> dict:
    body = {k: v for k, v in doc.items() if k != "signature"}
    body_bytes = json.dumps(
        body, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    out = dict(doc)
    out["signature"] = {
        "public_key_b64": annex_iv_map._public_key_b64(priv.public_key()),
        "signature_b64": base64.b64encode(priv.sign(body_bytes)).decode(
            "ascii"
        ),
    }
    return out


def _build_and_write(dossier_dir: Path, priv: Ed25519PrivateKey) -> dict:
    doc = build_annex_iv_map(dossier_dir, priv)
    (dossier_dir / "annex_iv_map.json").write_text(
        serialize_annex_iv_map(doc), encoding="utf-8"
    )
    return doc


def test_build_then_verify_passes(tmp_path: Path) -> None:
    _make_dossier(tmp_path)
    priv = Ed25519PrivateKey.generate()
    _build_and_write(tmp_path, priv)
    ok, reason = verify_annex_iv_map(tmp_path)
    assert ok, reason


def test_all_nine_items_indexed(tmp_path: Path) -> None:
    _make_dossier(tmp_path)
    priv = Ed25519PrivateKey.generate()
    doc = build_annex_iv_map(tmp_path, priv)
    assert set(doc["items"].keys()) == {
        cid for cid, _t, _c, _k in ANNEX_IV_ITEMS
    }
    assert len(doc["items"]) == 9


def test_evidence_backed_items_carry_evidence(tmp_path: Path) -> None:
    _make_dossier(tmp_path)
    priv = Ed25519PrivateKey.generate()
    doc = build_annex_iv_map(tmp_path, priv)
    for item_id in ("1", "2", "3", "4", "5", "6"):
        assert doc["items"][item_id]["evidence"], item_id


def test_doc_and_operator_items_carry_no_evidence(tmp_path: Path) -> None:
    _make_dossier(tmp_path)
    priv = Ed25519PrivateKey.generate()
    doc = build_annex_iv_map(tmp_path, priv)
    for item_id in ("7", "8", "9"):
        assert doc["items"][item_id]["evidence"] == [], item_id


def test_build_is_deterministic(tmp_path: Path) -> None:
    _make_dossier(tmp_path)
    priv = Ed25519PrivateKey.generate()
    a = serialize_annex_iv_map(build_annex_iv_map(tmp_path, priv))
    b = serialize_annex_iv_map(build_annex_iv_map(tmp_path, priv))
    assert a == b


def test_missing_evidence_file_refuses_build(tmp_path: Path) -> None:
    _write_manifest(tmp_path)
    # No source.nous -> item 2 (evidence-backed) has no present candidate.
    priv = Ed25519PrivateKey.generate()
    with pytest.raises(AnnexIvMapError):
        build_annex_iv_map(tmp_path, priv)


def test_missing_manifest_refuses_build(tmp_path: Path) -> None:
    (tmp_path / "source.nous").write_bytes(b"world W {}\n")
    priv = Ed25519PrivateKey.generate()
    with pytest.raises(AnnexIvMapError):
        build_annex_iv_map(tmp_path, priv)


def test_tampered_evidence_file_fails_verify(tmp_path: Path) -> None:
    _make_dossier(tmp_path)
    priv = Ed25519PrivateKey.generate()
    _build_and_write(tmp_path, priv)
    # Mutate a referenced file AFTER signing; the map signature stays valid,
    # so check 3 (evidence integrity) is what must fire.
    (tmp_path / "source.nous").write_bytes(b"world TestWorld { tampered }\n")
    ok, reason = verify_annex_iv_map(tmp_path)
    assert not ok
    assert "source.nous" in reason


def test_broken_signature_fails_verify(tmp_path: Path) -> None:
    _make_dossier(tmp_path)
    priv = Ed25519PrivateKey.generate()
    doc = build_annex_iv_map(tmp_path, priv)
    doc["signature"]["signature_b64"] = base64.b64encode(b"\x00" * 64).decode(
        "ascii"
    )
    (tmp_path / "annex_iv_map.json").write_text(
        serialize_annex_iv_map(doc), encoding="utf-8"
    )
    ok, reason = verify_annex_iv_map(tmp_path)
    assert not ok
    assert "signature" in reason.lower()


def test_wrong_manifest_binding_fails_verify(tmp_path: Path) -> None:
    _make_dossier(tmp_path)
    priv = Ed25519PrivateKey.generate()
    _build_and_write(tmp_path, priv)
    # Change a non-signature manifest field -> canonical body changes ->
    # binding sha no longer matches. Binding (check 2) precedes evidence
    # integrity (check 3) so the binding failure is returned.
    manifest = json.loads(
        (tmp_path / "manifest.json").read_text(encoding="utf-8")
    )
    manifest["world_name"] = "DifferentWorld"
    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    ok, reason = verify_annex_iv_map(tmp_path)
    assert not ok
    assert "bound to this dossier" in reason


def test_omitted_item_fails_verify(tmp_path: Path) -> None:
    _make_dossier(tmp_path)
    priv = Ed25519PrivateKey.generate()
    doc = build_annex_iv_map(tmp_path, priv)
    del doc["items"]["9"]
    doc = _resign(doc, priv)
    (tmp_path / "annex_iv_map.json").write_text(
        serialize_annex_iv_map(doc), encoding="utf-8"
    )
    ok, reason = verify_annex_iv_map(tmp_path)
    assert not ok
    assert "9" in reason


def test_surplus_item_fails_verify(tmp_path: Path) -> None:
    _make_dossier(tmp_path)
    priv = Ed25519PrivateKey.generate()
    doc = build_annex_iv_map(tmp_path, priv)
    doc["items"]["10"] = {
        "title": "Invented",
        "clause_kind": "evidence-backed",
        "evidence": [],
    }
    doc = _resign(doc, priv)
    (tmp_path / "annex_iv_map.json").write_text(
        serialize_annex_iv_map(doc), encoding="utf-8"
    )
    ok, reason = verify_annex_iv_map(tmp_path)
    assert not ok
    assert "10" in reason


def test_overclaim_on_doc_clause_fails_verify(tmp_path: Path) -> None:
    _make_dossier(tmp_path)
    priv = Ed25519PrivateKey.generate()
    doc = build_annex_iv_map(tmp_path, priv)
    # Item 8 is operator-responsibility; injecting a *valid* evidence ref
    # (real file, correct sha) must still be rejected as an over-claim, after
    # the integrity check passes.
    import hashlib

    real_sha = hashlib.sha256(
        (tmp_path / "README.md").read_bytes()
    ).hexdigest()
    doc["items"]["8"]["evidence"] = [
        {"file": "README.md", "sha256": real_sha, "role": "primary"}
    ]
    doc = _resign(doc, priv)
    (tmp_path / "annex_iv_map.json").write_text(
        serialize_annex_iv_map(doc), encoding="utf-8"
    )
    ok, reason = verify_annex_iv_map(tmp_path)
    assert not ok
    assert "over-claim" in reason


def test_title_tamper_fails_verify(tmp_path: Path) -> None:
    _make_dossier(tmp_path)
    priv = Ed25519PrivateKey.generate()
    doc = build_annex_iv_map(tmp_path, priv)
    doc["items"]["1"]["title"] = "Wrong title"
    doc = _resign(doc, priv)
    (tmp_path / "annex_iv_map.json").write_text(
        serialize_annex_iv_map(doc), encoding="utf-8"
    )
    ok, reason = verify_annex_iv_map(tmp_path)
    assert not ok
    assert "title" in reason


def test_manifest_evidence_uses_file_bytes_not_canonical(
    tmp_path: Path,
) -> None:
    # The evidence sha for manifest.json must be the raw file bytes, distinct
    # from the canonical-body binding sha (which strips signature +
    # transparency_log). Confirm the two differ for the same manifest.
    _make_dossier(tmp_path)
    priv = Ed25519PrivateKey.generate()
    doc = build_annex_iv_map(tmp_path, priv)
    binding = doc["manifest_canonical_sha256"]
    manifest_ref = next(
        e for e in doc["items"]["1"]["evidence"]
        if e["file"] == "manifest.json"
    )
    assert manifest_ref["sha256"] != binding
