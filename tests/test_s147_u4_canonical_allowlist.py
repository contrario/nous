"""S147 U4 -- canonical-verifier allowlist + honest degradation.
# __s147_u4_canonical_tests_v1__
"""
from __future__ import annotations

import base64
import hashlib
import json
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

import dossier
import ndec

_MINI = (
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


def _make_dossier(tmp_path: Path, verifier_text: str) -> Path:
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
    (d / "verify_offline.py").write_text(verifier_text, encoding="utf-8")
    return d


def test_canonical_digests_nonempty_and_hex() -> None:
    digs = ndec.canonical_verifier_digests()
    assert digs_ok(digs)


def digs_ok(digs) -> bool:
    if not digs:
        return False
    for name, dig in digs.items():
        if not name.startswith("VERIFY_OFFLINE_PY"):
            return False
        if len(dig) != 64:
            return False
    return True


def test_plain_template_is_canonical(tmp_path, capsys) -> None:
    # dossier.VERIFY_OFFLINE_PY (plain) only checks sig + source sha,
    # which our synthetic signed dossier satisfies; and its bytes ARE a
    # canonical template, so the installed path must report it canonical.
    d = _make_dossier(tmp_path, dossier.VERIFY_OFFLINE_PY)
    out = ndec.build_ndec(
        d, key_path=tmp_path / "k.key", output=tmp_path / "c.ndec"
    ).path
    rc = ndec.verify_ndec_file(out)
    captured = capsys.readouterr().out
    assert rc == 0
    assert "trusting-trust closed" in captured
    assert "canonical:VERIFY_OFFLINE_PY" in captured


def test_noncanonical_degrades(tmp_path, capsys) -> None:
    d = _make_dossier(tmp_path, _MINI)
    out = ndec.build_ndec(
        d, key_path=tmp_path / "k.key", output=tmp_path / "n.ndec"
    ).path
    rc = ndec.verify_ndec_file(out)
    captured = capsys.readouterr().out
    assert rc == 0
    assert "not confirmed canonical" in captured
    assert "trusting-trust closed" not in captured


def test_strict_canonical_refuses_noncanonical(tmp_path) -> None:
    d = _make_dossier(tmp_path, _MINI)
    out = ndec.build_ndec(
        d, key_path=tmp_path / "k.key", output=tmp_path / "s.ndec"
    ).path
    assert ndec.verify_ndec_file(out, strict_canonical=True) == 1


def test_strict_canonical_allows_canonical(tmp_path) -> None:
    d = _make_dossier(tmp_path, dossier.VERIFY_OFFLINE_PY)
    out = ndec.build_ndec(
        d, key_path=tmp_path / "k.key", output=tmp_path / "sc.ndec"
    ).path
    assert ndec.verify_ndec_file(out, strict_canonical=True) == 0


def test_malicious_signer_doctored_verifier_degrades_not_closed(
    tmp_path, capsys
) -> None:
    # A signer who ships (and signs over) a non-canonical doctored verifier:
    # the pin covers it, but the installed path must NOT claim trusting-trust
    # closed -- it degrades and labels the verdict honestly. This documents
    # the boundary, it does not claim closure that is not earned.
    doctored = "import sys\nprint('VERDICT: PASS')\nsys.exit(0)\n"
    d = _make_dossier(tmp_path, doctored)
    out = ndec.build_ndec(
        d, key_path=tmp_path / "k.key", output=tmp_path / "m.ndec"
    ).path
    rc = ndec.verify_ndec_file(out)
    captured = capsys.readouterr().out
    assert rc == 0
    assert "trusting-trust closed" not in captured
    assert "not confirmed canonical" in captured
    # strict mode refuses the doctored-but-signed verifier
    assert ndec.verify_ndec_file(out, strict_canonical=True) == 1
