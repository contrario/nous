"""
S172 P0(b)-2 -- live ANCHOR orchestrator (offline via 5.60.1 replay).

Exercises anchor() with the network ops injected (Rekor POST + TSA) by
replaying 5.60.1's real anchor data, proving the orchestrator assembles the
exact published bundle + index and runs the dual-root self-verify, with NO
network and NO Rekor write. A second test runs the REAL offline verifier
against the orchestrator output using durable operator pins (skipped if pins
absent). Refusal paths (re-anchor, missing inputs) are covered too.

# __s172_p0b2_test_anchor_orchestrator_v1__
"""
from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path

import pytest

import mint_release_vsa as M

_REPO = Path(__file__).resolve().parent.parent
_REF = _REPO / "website" / ".well-known" / "nous" / "release-vsa" / "5.60.1"
_VER = "5.60.1"
_TRUSTED_ROOT = Path(
    "/var/lib/nous-refresh/.cache/sigstore-python/tuf/"
    "https%3A%2F%2Ftuf-repo-cdn.sigstore.dev/trusted_root.json"
)

pytestmark = pytest.mark.skipif(
    not _REF.is_dir(),
    reason="5.60.1 release-VSA reference dir not present (clean-venv/sdist)",
)


def _published(name: str) -> dict:
    return json.loads((_REF / name).read_text(encoding="utf-8"))


class _ReplayAnchor:
    def __init__(self, bundle: dict) -> None:
        tle = bundle["transparency_log_entry"]
        ip = tle["inclusion_proof"]
        self.body_b64 = tle["canonicalized_body"]
        self.checkpoint_envelope = ip["checkpoint"]
        self.inclusion_proof_hashes = ip["hashes"]
        self.log_index = tle["log_index"]


def _mint_dir(tmp_path: Path) -> Path:
    d = tmp_path / "mintdir"
    d.mkdir()
    for name in (  # __s236_p2_fixture_alias_v1__
        "nous_lang-5.60.1.build-vsa.intoto.json",
        "build-vsa.intoto.json",
        "verify_build_vsa_offline.py",
        "release-verifier-key.json",
    ):
        shutil.copy2(_REF / name, d / name)
    return d


def _replay_seams():
    bundle = _published("nous_lang-5.60.1.rekor-v2-bundle.json")
    token_der = base64.b64decode(bundle["rfc3161_timestamp"])

    def anchor_fn(canonical: bytes) -> _ReplayAnchor:
        return _ReplayAnchor(bundle)

    def timestamp_fn(*, timestamped_data: bytes) -> bytes:
        return token_der

    return anchor_fn, timestamp_fn


def _pins_dir(tmp_path: Path) -> Path:
    p = tmp_path / "pins"
    p.mkdir()
    shutil.copy2(_TRUSTED_ROOT, p / "trusted_root.json")
    import tsa_verify

    (p / "tsa_chain.pem").write_text(
        "\n".join(tsa_verify.KNOWN_TSA_ROOT_CERTS), encoding="utf-8"
    )
    return p


def test_anchor_replays_5_60_1_bundle_and_index(tmp_path: Path) -> None:
    d = _mint_dir(tmp_path)
    pins = tmp_path / "fakepins"
    pins.mkdir()
    (pins / "trusted_root.json").write_text("{}", encoding="utf-8")
    (pins / "tsa_chain.pem").write_text("x", encoding="utf-8")
    anchor_fn, timestamp_fn = _replay_seams()
    idx_published = _published("index.json")

    def verify_fn(bundle_dir, pins_dir):
        return {
            "convergence": "PASS",
            "evidence": {"rfc3161_gen_time": "2026-06-22T10:02:24Z"},
        }

    rc = M.anchor(
        _VER,
        d,
        pins_dir=pins,
        anchor_fn=anchor_fn,
        timestamp_fn=timestamp_fn,
        verify_fn=verify_fn,
    )
    assert rc == 0
    produced_bundle = (d / "nous_lang-5.60.1.rekor-v2-bundle.json").read_bytes()
    assert produced_bundle == (
        _REF / "nous_lang-5.60.1.rekor-v2-bundle.json"
    ).read_bytes()
    produced_index = json.loads((d / "index.json").read_text(encoding="utf-8"))
    produced_index.pop("emittedAt")
    expected = dict(idx_published)
    expected.pop("emittedAt")
    assert produced_index == expected


def test_anchor_refuses_reanchor(tmp_path: Path) -> None:
    d = _mint_dir(tmp_path)
    (d / "nous_lang-5.60.1.rekor-v2-bundle.json").write_text("{}", encoding="utf-8")
    pins = tmp_path / "pins"
    pins.mkdir()
    (pins / "trusted_root.json").write_text("{}", encoding="utf-8")
    (pins / "tsa_chain.pem").write_text("x", encoding="utf-8")
    anchor_fn, timestamp_fn = _replay_seams()
    with pytest.raises(M.MintError):
        M.anchor(_VER, d, pins_dir=pins, anchor_fn=anchor_fn, timestamp_fn=timestamp_fn, verify_fn=lambda a, b: {})


def test_anchor_refuses_missing_vsa(tmp_path: Path) -> None:
    d = tmp_path / "empty"
    d.mkdir()
    pins = tmp_path / "pins"
    pins.mkdir()
    (pins / "trusted_root.json").write_text("{}", encoding="utf-8")
    (pins / "tsa_chain.pem").write_text("x", encoding="utf-8")
    with pytest.raises(M.MintError):
        M.anchor(_VER, d, pins_dir=pins, anchor_fn=lambda *a, **k: None, timestamp_fn=lambda **k: b"", verify_fn=lambda a, b: {})


def test_anchor_refuses_on_nonconvergent_selfverify(tmp_path: Path) -> None:
    d = _mint_dir(tmp_path)
    pins = tmp_path / "pins"
    pins.mkdir()
    (pins / "trusted_root.json").write_text("{}", encoding="utf-8")
    (pins / "tsa_chain.pem").write_text("x", encoding="utf-8")
    anchor_fn, timestamp_fn = _replay_seams()

    def verify_fn(a, b):
        return {"convergence": "FAIL", "legs": {"root2_inclusion": {"status": "FAIL"}}}

    with pytest.raises(M.MintError):
        M.anchor(_VER, d, pins_dir=pins, anchor_fn=anchor_fn, timestamp_fn=timestamp_fn, verify_fn=verify_fn)
    assert not (d / "index.json").exists()


@pytest.mark.skipif(
    not _TRUSTED_ROOT.is_file(),
    reason="durable operator trusted_root.json not present",
)
def test_anchor_selfverify_converges_with_real_verifier(tmp_path: Path) -> None:
    d = _mint_dir(tmp_path)
    pins = _pins_dir(tmp_path)
    anchor_fn, timestamp_fn = _replay_seams()
    rc = M.anchor(
        _VER, d, pins_dir=pins, anchor_fn=anchor_fn, timestamp_fn=timestamp_fn
    )
    assert rc == 0
    assert (d / "index.json").is_file()
