"""S147 U3 -- ndec CLI module + installed verifier.
# __s147_u3_ndec_cli_tests_v1__
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

import ndec
import cli_ndec

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
    "        print('FAIL', file=sys.stderr); return 1\n"
    "    s = hashlib.sha256((ROOT/'source.nous').read_bytes()).hexdigest()\n"
    "    if s != m['source_sha256']:\n"
    "        print('FAIL', file=sys.stderr); return 1\n"
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
    body = json.dumps(man, sort_keys=True, separators=(",", ":")).encode()
    man["signature"] = {
        "algorithm": "ed25519",
        "public_key_b64": base64.b64encode(
            pub.public_bytes(Encoding.Raw, PublicFormat.Raw)
        ).decode("ascii"),
        "signature_b64": base64.b64encode(key.sign(body)).decode("ascii"),
    }
    (d / "manifest.json").write_text(
        json.dumps(man, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (d / "verify_offline.py").write_text(
        _MINI_VERIFY_OFFLINE, encoding="utf-8"
    )
    return d


def _build(tmp_path: Path) -> Path:
    d = _make_dossier(tmp_path)
    return ndec.build_ndec(
        d, key_path=tmp_path / "k.key", output=tmp_path / "decision.ndec"
    ).path


def test_parser_and_build(tmp_path, capsys) -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)
    cli_ndec.build_ndec_parser(sub)
    d = _make_dossier(tmp_path)
    args = ap.parse_args(
        [
            "ndec", "build", str(d),
            "--key-path", str(tmp_path / "k.key"),
            "-o", str(tmp_path / "out.ndec"),
        ]
    )
    rc = cli_ndec.cmd_ndec(args)
    assert rc == 0
    assert (tmp_path / "out.ndec").is_file()
    assert "WROTE" in capsys.readouterr().out


def test_verify_file_passes(tmp_path) -> None:
    ndec_path = _build(tmp_path)
    assert ndec.verify_ndec_file(ndec_path) == 0


def test_verify_file_detects_tampered_artifact(tmp_path) -> None:
    ndec_path = _build(tmp_path)
    out = tmp_path / "x"
    with zipfile.ZipFile(ndec_path) as zf:
        zf.extractall(out)
    (out / "dossier" / "source.nous").write_bytes(b"swapped\n")
    repacked = tmp_path / "tampered.ndec"
    with zipfile.ZipFile(repacked, "w") as zf:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                zf.write(f, str(f.relative_to(out)))
    assert ndec.verify_ndec_file(repacked) == 1


def test_verify_file_detects_doctored_verifier(tmp_path) -> None:
    ndec_path = _build(tmp_path)
    out = tmp_path / "x"
    with zipfile.ZipFile(ndec_path) as zf:
        zf.extractall(out)
    (out / "dossier" / "verify_offline.py").write_text(
        "import sys\nprint('VERDICT: PASS')\nsys.exit(0)\n",
        encoding="utf-8",
    )
    repacked = tmp_path / "doctored.ndec"
    with zipfile.ZipFile(repacked, "w") as zf:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                zf.write(f, str(f.relative_to(out)))
    assert ndec.verify_ndec_file(repacked) == 1


def test_verify_cmd_via_parser(tmp_path) -> None:
    ndec_path = _build(tmp_path)
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)
    cli_ndec.build_ndec_parser(sub)
    args = ap.parse_args(["ndec", "verify", str(ndec_path)])
    assert cli_ndec.cmd_ndec(args) == 0
