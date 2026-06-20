"""S159 U2 tests for phase_provenance in scripts/release.py.

The release pipeline is loaded by file path (scripts/ is not a package). All
non-deterministic inputs (git commit, timestamps, invocation id, output dir,
key path, anchor backend) are injected so the test is hermetic: no git, no
network, no writes outside tmp_path.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import types
from pathlib import Path

import pytest

import provenance

_RELEASE = Path(__file__).resolve().parent.parent / "scripts" / "release.py"


def _load_release():
    spec = importlib.util.spec_from_file_location(
        "nous_release_under_test", _RELEASE
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _artifacts(tmp_path: Path) -> tuple[Path, Path]:
    whl = tmp_path / "nous_lang-9.9.9-py3-none-any.whl"
    sdist = tmp_path / "nous_lang-9.9.9.tar.gz"
    whl.write_bytes(b"WHEEL-BYTES")
    sdist.write_bytes(b"SDIST-BYTES")
    return whl, sdist


def _emit(release, tmp_path: Path, **overrides):
    whl, sdist = _artifacts(tmp_path)
    kw = dict(
        started_on="2026-06-20T10:00:00Z",
        finished_on="2026-06-20T10:01:00Z",
        invocation_id="fixed-invocation",
        git_commit="c" * 40,
        out_dir=tmp_path / "dist",
        key_path=tmp_path / "provenance_signing.key",
    )
    kw.update(overrides)
    return whl, sdist, release.phase_provenance(whl, sdist, "9.9.9", **kw)


def test_release_module_loads_and_exposes_phase() -> None:
    release = _load_release()
    assert hasattr(release, "phase_provenance")
    assert hasattr(release, "_file_sha256")
    assert release.PROVENANCE_REPO_URI == "https://github.com/contrario/nous"


def test_emits_verifiable_dsse_with_file_subjects(tmp_path: Path) -> None:
    release = _load_release()
    whl, sdist, prov_path = _emit(release, tmp_path)
    assert prov_path.name == "nous_lang-9.9.9.provenance.intoto.json"
    envelope = json.loads(prov_path.read_text())
    _, pub, _ = provenance.load_or_create_provenance_keypair(
        tmp_path / "provenance_signing.key"
    )
    stmt = provenance.verify_provenance_envelope(envelope, pub)
    assert stmt["predicateType"] == "https://slsa.dev/provenance/v1"
    subjects = {s["name"]: s["digest"]["sha256"] for s in stmt["subject"]}
    assert subjects[whl.name] == hashlib.sha256(b"WHEEL-BYTES").hexdigest()
    assert subjects[sdist.name] == hashlib.sha256(b"SDIST-BYTES").hexdigest()


def test_honest_l1_fields_present(tmp_path: Path) -> None:
    release = _load_release()
    _, _, prov_path = _emit(release, tmp_path)
    envelope = json.loads(prov_path.read_text())
    _, pub, _ = provenance.load_or_create_provenance_keypair(
        tmp_path / "provenance_signing.key"
    )
    pred = provenance.verify_provenance_envelope(envelope, pub)["predicate"]
    assert pred["buildDefinition"]["buildType"] == provenance.BUILD_TYPE
    assert pred["runDetails"]["builder"]["id"] == provenance.BUILDER_ID
    assert pred["buildDefinition"]["externalParameters"]["ref"] == (
        "refs/tags/v9.9.9"
    )
    assert pred["buildDefinition"]["externalParameters"]["commit"] == "c" * 40
    assert pred["runDetails"]["builder"]["version"]["python"]
    assert pred[provenance.NOUS_PROV_EXT_KEY]["slsaBuildLevel"] == 1


def test_no_anchor_writes_single_file(tmp_path: Path) -> None:
    release = _load_release()
    _, _, prov_path = _emit(release, tmp_path)
    out = tmp_path / "dist"
    assert prov_path.exists()
    assert not (out / "nous_lang-9.9.9.provenance.rekor.json").exists()


def test_anchor_writes_sidecar_over_canonical_bytes(tmp_path: Path) -> None:
    release = _load_release()
    captured = {}

    def fake_anchor(canonical_bytes: bytes):
        captured["bytes"] = canonical_bytes
        return types.SimpleNamespace(
            rekor_api_version=2,
            log_id="LOGID",
            log_index=4242,
            body_b64="Qk9EWQ==",
            checkpoint_envelope="CKPT",
            inclusion_proof_hashes=["h1", "h2"],
        )

    whl, sdist, prov_path = _emit(
        release, tmp_path, anchor=True, anchor_fn=fake_anchor
    )
    sidecar_path = tmp_path / "dist" / "nous_lang-9.9.9.provenance.rekor.json"
    sidecar = json.loads(sidecar_path.read_text())
    assert sidecar["log_index"] == 4242
    assert sidecar["log_id"] == "LOGID"
    assert sidecar["provider"] == "sigstore-rekor-v2"
    envelope = json.loads(prov_path.read_text())
    payload = json.loads(
        __import__("base64").b64decode(envelope["payload"]).decode("utf-8")
    )
    canonical = provenance.statement_canonical_bytes(payload)
    assert captured["bytes"] == canonical
    assert sidecar["provenance_canonical_sha256"] == (
        hashlib.sha256(canonical).hexdigest()
    )


def test_anchor_failure_raises_release_error(tmp_path: Path) -> None:
    release = _load_release()

    def boom(_: bytes):
        raise RuntimeError("rekor down")

    with pytest.raises(release.ReleaseError):
        _emit(release, tmp_path, anchor=True, anchor_fn=boom)


def test_byte_identity_under_fixed_inputs(tmp_path: Path) -> None:
    release = _load_release()
    _, _, p1 = _emit(release, tmp_path, out_dir=tmp_path / "d1")
    _, _, p2 = _emit(release, tmp_path, out_dir=tmp_path / "d2")
    assert p1.read_bytes() == p2.read_bytes()
