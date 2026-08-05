"""S298 tests for the four ceremony preconditions added to
scripts/sign_glm_manifest.py.

G1  the predecessor digest is recomputed from the source bytes.
G2  a placeholder cannot become a supersedes_digest.
G3  valid_from must be YYYY-MM-DD (it is concatenated into generated_at).
G4  a successor must not carry the source owner.version.

Each guard has a fixture that reaches the branch it names. The two cmd_build
guards are asserted to fire BEFORE the operator key is loaded, so these tests
stay hermetic and CI-portable: no private key, no network, no served read.

The last test covers a shape no other fixture has: the archived root of the
supersedes chain, which declares no predecessor at all.

__s298_glm_ceremony_guard_tests_v1__
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path

import pytest

import glm_manifest as gm

_REPO = Path(__file__).resolve().parents[1]
_SIGNER = _REPO / "scripts" / "sign_glm_manifest.py"
_ROOT_MANIFEST = (
    _REPO / "website" / "governance" / "glm-archive"
    / "governance-layer-manifest-5.37.0.json"
)

_MISSING_KEY = "/nonexistent/s298/no-such-operator.key"


def _load_signer():
    spec = importlib.util.spec_from_file_location("_s298_signer", _SIGNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source_manifest(digest_value: str = "ab" * 32) -> dict:
    return {
        "schema_version": "1.1",
        "manifest_version": "1.0",
        "owner": {"name": "NOUS", "version": "1.0.0"},
        "valid_from": "2026-01-01",
        "generated_at": "2026-01-01T00:00:00Z",
        "supersedes": "https://example.invalid/old.json",
        "supersedes_digest": "cd" * 32,
        "operational_scope": {"does_not": ["Attest a specific execution"]},
        "manifest_digest": {
            "type": "sha256",
            "value": digest_value,
            "canonicalization_method": "superseded by the transform",
        },
        "manifest_signature": {
            "type": "ed25519",
            "value": None,
            "public_key": None,
        },
    }


def _sealed_source_text(doc: dict) -> str:
    """Serialize doc and set manifest_digest.value to its own recomputed
    digest. The digest is taken over the placeholder form, so substituting the
    real value back does not change the canonical bytes."""
    dummy = doc["manifest_digest"]["value"]
    text = json.dumps(doc, indent=2, ensure_ascii=True) + "\n"
    assert text.count(dummy) == 1
    return text.replace(dummy, gm.compute_glm_digest(text), 1)


def _build_args(tmp_path: Path, source_text: str, new_version: str):
    source = tmp_path / "source.json"
    source.write_text(source_text, encoding="utf-8")
    return argparse.Namespace(
        source=str(source),
        key=_MISSING_KEY,
        new_version=new_version,
        valid_from="2026-08-05",
        supersedes_url="https://example.invalid/new.json",
        out=str(tmp_path / "out.json"),
        overwrite=False,
    )


# --- G2: a placeholder is not a predecessor -----------------------------


def test_transform_refuses_the_publish_time_placeholder() -> None:
    signer = _load_signer()
    source = _source_manifest("<computed-at-publish-time>")
    with pytest.raises(signer.CeremonyError) as exc:
        signer._transform_source(
            source,
            new_version="2.0.0",
            valid_from="2026-08-05",
            supersedes_url="https://example.invalid/new.json",
        )
    assert "64 lowercase hex" in str(exc.value)


def test_transform_refuses_an_uppercase_digest() -> None:
    signer = _load_signer()
    source = _source_manifest("AB" * 32)
    with pytest.raises(signer.CeremonyError):
        signer._transform_source(
            source,
            new_version="2.0.0",
            valid_from="2026-08-05",
            supersedes_url="https://example.invalid/new.json",
        )


# --- G3: valid_from is concatenated, so it must be a bare date ----------


def test_transform_refuses_a_timestamp_as_valid_from() -> None:
    """An ISO timestamp would yield generated_at '...ZT00:00:00Z'."""
    signer = _load_signer()
    with pytest.raises(signer.CeremonyError) as exc:
        signer._transform_source(
            _source_manifest(),
            new_version="2.0.0",
            valid_from="2026-08-05T12:00:00Z",
            supersedes_url="https://example.invalid/new.json",
        )
    assert "YYYY-MM-DD" in str(exc.value)


def test_transform_still_accepts_a_bare_date() -> None:
    """POSITIVE CONTROL: the guard must not reject the normal input."""
    signer = _load_signer()
    out = signer._transform_source(
        _source_manifest(),
        new_version="2.0.0",
        valid_from="2026-08-05",
        supersedes_url="https://example.invalid/new.json",
    )
    assert out["generated_at"] == "2026-08-05T00:00:00Z"
    assert out["supersedes_digest"] == "ab" * 32


# --- G1: the predecessor digest is recomputed, not trusted --------------


def test_build_refuses_a_source_whose_digest_does_not_match_its_bytes(
    tmp_path, capsys
) -> None:
    signer = _load_signer()
    doc = _source_manifest()
    text = json.dumps(doc, indent=2, ensure_ascii=True) + "\n"
    args = _build_args(tmp_path, text, "2.0.0")
    rc = signer.cmd_build(args)
    err = capsys.readouterr().err
    assert rc == 1
    assert "does not match the source bytes" in err
    assert "operator key not found" not in err
    assert not Path(args.out).exists()


# --- G4: two bodies do not carry one version ----------------------------


def test_build_refuses_a_new_version_equal_to_the_source_version(
    tmp_path, capsys
) -> None:
    signer = _load_signer()
    text = _sealed_source_text(_source_manifest())
    args = _build_args(tmp_path, text, "1.0.0")
    rc = signer.cmd_build(args)
    err = capsys.readouterr().err
    assert rc == 1
    assert "equals the source" in err
    assert "operator key not found" not in err
    assert not Path(args.out).exists()


def test_build_reaches_the_key_once_the_source_checks_pass(
    tmp_path, capsys
) -> None:
    """POSITIVE CONTROL for the ordering: with a digest-consistent source and
    an advancing version, both guards pass and the ceremony proceeds to the
    key, which is absent here. Without this, the two REFUSE tests above could
    pass for the wrong reason."""
    signer = _load_signer()
    text = _sealed_source_text(_source_manifest())
    args = _build_args(tmp_path, text, "2.0.0")
    rc = signer.cmd_build(args)
    err = capsys.readouterr().err
    assert rc == 1
    assert "operator key not found" in err
    assert not Path(args.out).exists()


# --- the root of the chain ----------------------------------------------


def test_the_archived_root_declares_no_predecessor_and_still_chains() -> None:
    """The archived root carries supersedes and supersedes_digest as null: it
    is the start of the chain, not a link in it. The transform must still be
    able to chain from it, using its own recomputed digest."""
    text = _ROOT_MANIFEST.read_text(encoding="utf-8")
    doc = json.loads(text)
    assert doc.get("supersedes") is None
    assert doc.get("supersedes_digest") is None

    declared = doc["manifest_digest"]["value"]
    assert gm.compute_glm_digest(text) == declared

    signer = _load_signer()
    out = signer._transform_source(
        copy.deepcopy(doc),
        new_version="0.0.0-test",
        valid_from="2026-08-05",
        supersedes_url="https://example.invalid/root.json",
    )
    assert out["supersedes_digest"] == declared
