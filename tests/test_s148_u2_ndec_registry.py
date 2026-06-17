"""S148 U2 -- ndec installed-path registry confirmation.

A carried verifier that is NOT in this install's canonical template set
(local miss) is confirmed via a logged-tier verifier-digest registry, turning
a degrade into a confirmation and letting --strict-canonical pass across NOUS
versions. Signed-tier-only registries do NOT satisfy --strict-canonical
(require_anchor): the public-log anchor is what closes trusting-trust.

The .ndec is built with the same real fixture S147 U4 uses (_make_dossier +
_MINI). The registry anchor is the proven synthetic construction from
test_rekor_v2_verify_flow.py, generalized over the registry canonical body.
The registry-key pin and the log-key loader are monkeypatched to the synthetic
keys; nothing is hardcoded.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

import dossier
import ndec
import verifier_registry
from rekor_checkpoint import ed25519_key_id
from rekor_verify_v2 import load_trusted_log_keys


_LEAF_PREFIX = b"\x00"

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


_DOSSIER_SEQ = [0]  # __s148_u2_hotfix_seq_v1__


def _make_dossier(tmp_path: Path, verifier_text: str) -> Path:
    _DOSSIER_SEQ[0] += 1
    d = tmp_path / ("loan_dossier_" + str(_DOSSIER_SEQ[0]))
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
    key = ed25519.Ed25519PrivateKey.generate()
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


def _synthetic_anchor_over(body_bytes: bytes):
    digest = hashlib.sha256(body_bytes).digest()
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    leaf_sig_der = leaf_key.sign(body_bytes, ec.ECDSA(hashes.SHA256()))
    leaf_pub_der = leaf_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    leaf = {
        "kind": "hashedrekord",
        "apiVersion": "0.0.2",
        "spec": {
            "hashedRekordV002": {
                "data": {
                    "algorithm": "SHA2_256",
                    "digest": base64.b64encode(digest).decode(),
                },
                "signature": {
                    "content": base64.b64encode(leaf_sig_der).decode(),
                    "verifier": {
                        "keyDetails": "PKIX_ECDSA_P256_SHA_256",
                        "publicKey": {
                            "rawBytes": base64.b64encode(
                                leaf_pub_der
                            ).decode()
                        },
                    },
                },
            }
        },
    }
    leaf_bytes = json.dumps(leaf).encode("utf-8")
    body_b64 = base64.b64encode(leaf_bytes).decode("ascii")
    root_hash = hashlib.sha256(_LEAF_PREFIX + leaf_bytes).digest()
    log_key = ed25519.Ed25519PrivateKey.generate()
    log_pub = log_key.public_key()
    origin = "nous-synthetic-registry-v2"
    note_text = (
        origin + "\n" + "1" + "\n"
        + base64.b64encode(root_hash).decode() + "\n"
    )
    sig = log_key.sign(note_text.encode("utf-8"))
    sig_blob = ed25519_key_id(origin, log_pub) + sig
    checkpoint_envelope = (
        note_text + "\n"
        + "\u2014 " + origin + " "
        + base64.b64encode(sig_blob).decode() + "\n"
    )
    block = {
        "rekor_api_version": 2,
        "log_id": "synthetic-registry-log-id",
        "log_index": 0,
        "body_b64": body_b64,
        "checkpoint_envelope": checkpoint_envelope,
        "inclusion_proof_hashes": [],
    }
    allowlist = {
        origin: base64.b64encode(
            log_pub.public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        ).decode()
    }
    return block, allowlist


def _reg_key_b64(private_key: ed25519.Ed25519PrivateKey) -> str:
    raw = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return base64.b64encode(raw).decode("ascii")


def _logged_registry(template_name, version, target_sha, reg_key):
    unsigned = verifier_registry.build_registry(
        [
            {
                "template_name": template_name,
                "template_sha256": target_sha,
                "nous_version": version,
            }
        ]
    )
    signed = verifier_registry.sign_registry(unsigned, reg_key)
    body = verifier_registry.canonical_registry_body_bytes(signed)
    block, log_allow = _synthetic_anchor_over(body)
    signed["rekor_anchor"] = block
    return signed, log_allow


def _signed_only_registry(template_name, version, target_sha, reg_key):
    unsigned = verifier_registry.build_registry(
        [
            {
                "template_name": template_name,
                "template_sha256": target_sha,
                "nous_version": version,
            }
        ]
    )
    return verifier_registry.sign_registry(unsigned, reg_key)


def _install_pins(monkeypatch, reg_key, log_allow):
    monkeypatch.setattr(
        verifier_registry,
        "KNOWN_REGISTRY_PUBLIC_KEYS_B64",
        (_reg_key_b64(reg_key),),
    )
    monkeypatch.setattr(
        verifier_registry,
        "load_trusted_log_keys",
        lambda allowlist=None: load_trusted_log_keys(log_allow),
    )


def _mini_sha() -> str:
    return hashlib.sha256(_MINI.encode("utf-8")).hexdigest()


def _build_mini_ndec(tmp_path: Path) -> str:
    d = _make_dossier(tmp_path, _MINI)
    return ndec.build_ndec(
        d, key_path=tmp_path / "k.key", output=tmp_path / "m.ndec"
    ).path


def test_mini_is_not_locally_canonical() -> None:
    assert _mini_sha() not in set(
        ndec.canonical_verifier_digests().values()
    )


def test_logged_registry_confirms_strict_passes(
    tmp_path, capsys, monkeypatch
) -> None:
    out = _build_mini_ndec(tmp_path)
    reg_key = ed25519.Ed25519PrivateKey.generate()
    reg, log_allow = _logged_registry(
        "VERIFY_OFFLINE_PY_FARKAS", "5.99.0", _mini_sha(), reg_key
    )
    reg_path = tmp_path / "reg.json"
    reg_path.write_text(json.dumps(reg), encoding="utf-8")
    _install_pins(monkeypatch, reg_key, log_allow)
    rc = ndec.verify_ndec_file(
        out, strict_canonical=True, registry_path=str(reg_path)
    )
    captured = capsys.readouterr().out
    assert rc == 0, captured
    assert "trusting-trust closed across versions" in captured
    assert "registry:logged:VERIFY_OFFLINE_PY_FARKAS@5.99.0" in captured


def test_logged_registry_non_strict_reports_footer(
    tmp_path, capsys, monkeypatch
) -> None:
    out = _build_mini_ndec(tmp_path)
    reg_key = ed25519.Ed25519PrivateKey.generate()
    reg, log_allow = _logged_registry(
        "VERIFY_OFFLINE_PY_FARKAS", "5.99.0", _mini_sha(), reg_key
    )
    reg_path = tmp_path / "reg.json"
    reg_path.write_text(json.dumps(reg), encoding="utf-8")
    _install_pins(monkeypatch, reg_key, log_allow)
    rc = ndec.verify_ndec_file(out, registry_path=str(reg_path))
    captured = capsys.readouterr().out
    assert rc == 0
    assert "registry:logged:" in captured


def test_signed_only_registry_strict_refused(
    tmp_path, monkeypatch
) -> None:
    out = _build_mini_ndec(tmp_path)
    reg_key = ed25519.Ed25519PrivateKey.generate()
    reg = _signed_only_registry(
        "VERIFY_OFFLINE_PY_FARKAS", "5.99.0", _mini_sha(), reg_key
    )
    reg_path = tmp_path / "reg.json"
    reg_path.write_text(json.dumps(reg), encoding="utf-8")
    monkeypatch.setattr(
        verifier_registry,
        "KNOWN_REGISTRY_PUBLIC_KEYS_B64",
        (_reg_key_b64(reg_key),),
    )
    assert (
        ndec.verify_ndec_file(
            out, strict_canonical=True, registry_path=str(reg_path)
        )
        == 1
    )


def test_wrong_sha_registry_strict_refused(tmp_path, monkeypatch) -> None:
    out = _build_mini_ndec(tmp_path)
    reg_key = ed25519.Ed25519PrivateKey.generate()
    reg, log_allow = _logged_registry(
        "VERIFY_OFFLINE_PY_FARKAS", "5.99.0", "a" * 64, reg_key
    )
    reg_path = tmp_path / "reg.json"
    reg_path.write_text(json.dumps(reg), encoding="utf-8")
    _install_pins(monkeypatch, reg_key, log_allow)
    assert (
        ndec.verify_ndec_file(
            out, strict_canonical=True, registry_path=str(reg_path)
        )
        == 1
    )


def test_no_registry_is_s147_identical(tmp_path) -> None:
    out = _build_mini_ndec(tmp_path)
    assert ndec.verify_ndec_file(out, strict_canonical=True) == 1
    d = _make_dossier(tmp_path, dossier.VERIFY_OFFLINE_PY)
    can = ndec.build_ndec(
        d, key_path=tmp_path / "k2.key", output=tmp_path / "c.ndec"
    ).path
    assert ndec.verify_ndec_file(can, strict_canonical=True) == 0


def test_broken_registry_file_degrades(tmp_path, capsys) -> None:
    out = _build_mini_ndec(tmp_path)
    reg_path = tmp_path / "reg.json"
    reg_path.write_text("{not json", encoding="utf-8")
    assert (
        ndec.verify_ndec_file(
            out, strict_canonical=True, registry_path=str(reg_path)
        )
        == 1
    )
    rc = ndec.verify_ndec_file(out, registry_path=str(reg_path))
    captured = capsys.readouterr()
    assert rc == 0
    assert "could not be read" in captured.err


def test_unpinned_registry_does_not_confirm(tmp_path, monkeypatch) -> None:
    out = _build_mini_ndec(tmp_path)
    reg_key = ed25519.Ed25519PrivateKey.generate()
    reg, log_allow = _logged_registry(
        "VERIFY_OFFLINE_PY_FARKAS", "5.99.0", _mini_sha(), reg_key
    )
    reg_path = tmp_path / "reg.json"
    reg_path.write_text(json.dumps(reg), encoding="utf-8")
    monkeypatch.setattr(
        verifier_registry,
        "load_trusted_log_keys",
        lambda allowlist=None: load_trusted_log_keys(log_allow),
    )
    assert (
        ndec.verify_ndec_file(
            out, strict_canonical=True, registry_path=str(reg_path)
        )
        == 1
    )
