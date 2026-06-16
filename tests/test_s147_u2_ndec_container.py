"""S147 U2 -- NDEC container builder + carried verifier integration.
# __s147_u2_ndec_tests_v1__
"""
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

import ndec

_MINI_VERIFY_OFFLINE = (
    "#!/usr/bin/env python3\n"
    "import base64, hashlib, json, sys\n"
    "from pathlib import Path\n"
    "from cryptography.hazmat.primitives.asymmetric.ed25519 import "
    "Ed25519PublicKey\n"
    "from cryptography.exceptions import InvalidSignature\n"
    "ROOT = Path(__file__).parent\n"
    "def main():\n"
    "    m = json.loads((ROOT/'manifest.json').read_text())\n"
    "    sig = m['signature']\n"
    "    body = {k:v for k,v in m.items() if k not in ('signature',"
    "'transparency_log')}\n"
    "    bb = json.dumps(body, sort_keys=True, separators=(',',':'))"
    ".encode()\n"
    "    try:\n"
    "        Ed25519PublicKey.from_public_bytes(base64.b64decode("
    "sig['public_key_b64'])).verify(base64.b64decode("
    "sig['signature_b64']), bb)\n"
    "    except InvalidSignature:\n"
    "        print('FAIL: sig', file=sys.stderr); return 1\n"
    "    s = hashlib.sha256((ROOT/'source.nous').read_bytes()).hexdigest()\n"
    "    if s != m['source_sha256']:\n"
    "        print('FAIL: source', file=sys.stderr); return 1\n"
    "    print('VERDICT: PASS'); return 0\n"
    "sys.exit(main())\n"
)


def _make_dossier(tmp_path: Path) -> Path:
    d = tmp_path / "loan_dossier"
    d.mkdir()
    source = b"world Demo {\n  law cost_c = $0.5 per cycle\n}\n"
    (d / "source.nous").write_bytes(source)
    man = {
        "schema_version": "1.0",
        "nous_version": "5.45.0",
        "world_name": "Demo",
        "verdict": "proven",
        "cost_cap_usd": "0.5",
        "source_sha256": hashlib.sha256(source).hexdigest(),
    }
    key = Ed25519PrivateKey.generate()
    pub = key.public_key()
    body_bytes = json.dumps(
        man, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    sig = key.sign(body_bytes)
    man["signature"] = {
        "algorithm": "ed25519",
        "public_key_b64": base64.b64encode(
            pub.public_bytes(Encoding.Raw, PublicFormat.Raw)
        ).decode("ascii"),
        "signature_b64": base64.b64encode(sig).decode("ascii"),
    }
    (d / "manifest.json").write_text(
        json.dumps(man, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (d / "pricing.toml").write_bytes(b"[pricing]\n")
    (d / "verify_offline.py").write_text(
        _MINI_VERIFY_OFFLINE, encoding="utf-8"
    )
    (d / "README.md").write_bytes(b"# dossier\n")
    return d


def _extract(ndec_path: Path, dest: Path) -> Path:
    with zipfile.ZipFile(ndec_path) as zf:
        zf.extractall(dest)
    return dest


def test_build_ndec_layout_and_envelope(tmp_path) -> None:
    d = _make_dossier(tmp_path)
    key_path = tmp_path / "signing.key"
    result = ndec.build_ndec(d, key_path=key_path)
    assert result.path.is_file()
    assert result.path.suffix == ".ndec"
    with zipfile.ZipFile(result.path) as zf:
        names = set(zf.namelist())
    assert "attestation.intoto.json" in names
    assert "verify_ndec.py" in names
    assert "README.ndec.txt" in names
    assert "dossier/manifest.json" in names
    assert "dossier/verify_offline.py" in names


def test_predicate_pins_verify_offline(tmp_path) -> None:
    d = _make_dossier(tmp_path)
    result = ndec.build_ndec(d, key_path=tmp_path / "k.key")
    assert "verify_offline_sha256" in result.artifacts
    vo_sha = hashlib.sha256(
        (d / "verify_offline.py").read_bytes()
    ).hexdigest()
    assert result.artifacts["verify_offline_sha256"] == vo_sha


def test_envelope_roundtrip_verifies(tmp_path) -> None:
    d = _make_dossier(tmp_path)
    key_path = tmp_path / "k.key"
    result = ndec.build_ndec(d, key_path=key_path)
    out = _extract(result.path, tmp_path / "out")
    env = json.loads((out / "attestation.intoto.json").read_text())
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    import manifest as _m
    priv, pub, _ = _m.load_or_create_keypair(key_path)
    stmt = ndec.verify_envelope(envelope=env, public_key=pub)
    man = json.loads((out / "dossier" / "manifest.json").read_text())
    assert stmt["subject"][0]["digest"]["sha256"] == (
        ndec.manifest_canonical_sha256(man)
    )


def test_build_is_deterministic(tmp_path) -> None:
    d = _make_dossier(tmp_path)
    key_path = tmp_path / "k.key"
    r1 = ndec.build_ndec(d, key_path=key_path, output=tmp_path / "a.ndec")
    r2 = ndec.build_ndec(d, key_path=key_path, output=tmp_path / "b.ndec")
    assert (tmp_path / "a.ndec").read_bytes() == (
        tmp_path / "b.ndec"
    ).read_bytes()


def test_refuses_inconsistent_dossier(tmp_path) -> None:
    d = _make_dossier(tmp_path)
    (d / "source.nous").write_bytes(b"tampered after signing\n")
    with pytest.raises(ndec.NdecError):
        ndec.build_ndec(d, key_path=tmp_path / "k.key")


def test_carried_verifier_passes(tmp_path) -> None:
    d = _make_dossier(tmp_path)
    result = ndec.build_ndec(d, key_path=tmp_path / "k.key")
    out = _extract(result.path, tmp_path / "out")
    proc = subprocess.run(
        [sys.executable, str(out / "verify_ndec.py")],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "VERDICT: PASS" in proc.stdout


def test_carried_verifier_detects_tampered_artifact(tmp_path) -> None:
    d = _make_dossier(tmp_path)
    result = ndec.build_ndec(d, key_path=tmp_path / "k.key")
    out = _extract(result.path, tmp_path / "out")
    (out / "dossier" / "source.nous").write_bytes(b"swapped\n")
    proc = subprocess.run(
        [sys.executable, str(out / "verify_ndec.py")],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode != 0


def test_carried_verifier_detects_doctored_verifier(tmp_path) -> None:
    d = _make_dossier(tmp_path)
    result = ndec.build_ndec(d, key_path=tmp_path / "k.key")
    out = _extract(result.path, tmp_path / "out")
    (out / "dossier" / "verify_offline.py").write_text(
        "import sys\nprint('VERDICT: PASS')\nsys.exit(0)\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(out / "verify_ndec.py")],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode != 0
