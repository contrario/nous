"""
NOUS dossier --- EU AI Act Annex IV-aligned compliance bundle.

Consumes a NOUS source + signed manifest + pricing TOML and writes
a self-contained directory with all artefacts plus an Annex IV
mapping README and offline verifier script.

Pre-conditions verified before emit (raises DossierError otherwise):
  1. Manifest signature is valid (Ed25519 over canonical JSON).
  2. Source bytes hash matches manifest.source_sha256.
  3. Active pricing TOML hash matches manifest.pricing_sha256.
  4. Re-emitted SMT spec hash matches manifest.smt_spec_sha256.

Output structure:
    <output>/source.nous
    <output>/manifest.json
    <output>/pricing.toml
    <output>/public_key.b64
    <output>/README.md
    <output>/verify_offline.py

Public API:
    build_dossier(source, manifest=None, prices=None, output=None)
    DossierError
    DossierResult

# __session64_dossier_v1__
"""
from __future__ import annotations
# __session64_dossier_hotfix_v1__

import base64
import hashlib
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PublicKey,
)

from manifest import parse_manifest_json, verify_manifest_signature
from parser import parse_nous
from pricing import PricingTable, load_pricing
from smt_emit import emit_smt


class DossierError(RuntimeError):
    """Raised when dossier cannot be emitted (sha mismatch, etc.)."""


@dataclass(frozen=True)
class DossierResult:
    output_dir: Path
    files: tuple[str, ...]
    world_name: str
    verdict: str
    safety_margin_pct: Optional[int]


VERIFY_OFFLINE_PY: str = '#!/usr/bin/env python3\n"""Offline verification of NOUS dossier (Annex IV).\nUsage: python3 verify_offline.py\nExit:  0 = PASS, 1 = FAIL, 2 = environment error.\nRequires: cryptography library (no NOUS install needed).\n"""\nfrom __future__ import annotations\n\nimport base64\nimport hashlib\nimport json\nimport sys\nfrom pathlib import Path\n\nROOT = Path(__file__).parent\n\n\ndef _fail(msg: str) -> int:\n    print(f"FAIL: {msg}", file=sys.stderr)\n    return 1\n\n\ndef main() -> int:\n    try:\n        from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n            Ed25519PublicKey,\n        )\n        from cryptography.exceptions import InvalidSignature\n    except ImportError:\n        print(\n            "ERROR: cryptography library required.\\n"\n            "Install: pip install \'cryptography>=42\'",\n            file=sys.stderr,\n        )\n        return 2\n\n    manifest_path = ROOT / "manifest.json"\n    if not manifest_path.is_file():\n        return _fail(f"manifest.json not found in {ROOT}")\n    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))\n\n    sig_block = manifest.get("signature")\n    if not sig_block:\n        return _fail("manifest has no signature block")\n    pub_b64 = sig_block.get("public_key_b64", "")\n    sig_b64 = sig_block.get("signature_b64", "")\n    if not pub_b64 or not sig_b64:\n        return _fail("manifest signature block incomplete")\n\n    body = {k: v for k, v in manifest.items() if k != "signature"}\n    body_bytes = json.dumps(\n        body, sort_keys=True, separators=(",", ":")\n    ).encode("utf-8")\n\n    try:\n        pub_key = Ed25519PublicKey.from_public_bytes(\n            base64.b64decode(pub_b64)\n        )\n        pub_key.verify(base64.b64decode(sig_b64), body_bytes)\n    except InvalidSignature:\n        return _fail("Ed25519 signature does NOT verify")\n    except Exception as e:\n        return _fail(f"signature verification error: {e}")\n    print("OK   Ed25519 signature verified")\n\n    source_path = ROOT / "source.nous"\n    if not source_path.is_file():\n        return _fail(f"source.nous not found in {ROOT}")\n    src_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()\n    expected = manifest.get("source_sha256", "")\n    if src_sha != expected:\n        return _fail(\n            f"source.sha256 mismatch: file={src_sha[:16]}... "\n            f"manifest={expected[:16]}..."\n        )\n    print(f"OK   source.sha256 matches manifest ({src_sha[:16]}...)")\n\n    print()\n    print("VERDICT: PASS")\n    print(f"  world:      {manifest.get(\'world_name\', \'?\')}")\n    cap = manifest.get("cost_cap_usd", "?")\n    print(f"  cost_cap:   ${cap} USD")\n    margin = manifest.get("safety_margin_pct")\n    if margin:\n        try:\n            from decimal import Decimal\n            eff = Decimal(cap) * Decimal(100 - margin) / Decimal(100)\n            print(\n                f"  effective:  ${eff} USD ({margin}% safety margin)"\n            )\n        except Exception:\n            print(f"  margin:     {margin}%")\n    print(f"  verdict:    {manifest.get(\'verdict\', \'?\')}")\n    print(f"  solver:     {manifest.get(\'solver_version\', \'?\')}")\n    print(f"  timestamp:  {manifest.get(\'timestamp_utc\', \'?\')}")\n    return 0\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'


# __nous_aetherproof_verify_offline_rekor_v1__
# __nous_aetherproof_rekor_offline_verifier_pivot_v1__
VERIFY_OFFLINE_PY_WITH_REKOR: str = '#!/usr/bin/env python3\n"""Offline verification of NOUS dossier (Annex IV) with Sigstore Rekor anchor.\n\nUsage: python3 verify_offline.py\nExit:  0 = PASS, 1 = FAIL, 2 = environment error.\nRequires: cryptography library (no NOUS install needed).\n\nChecks performed:\n  1. Ed25519 signature over canonical manifest body bytes (signature and\n     transparency_log blocks stripped before recomputing canonical form).\n     Proves manifest authorship.\n  2. source.nous sha256 matches manifest.source_sha256.\n  3. transparency_log.provider == "sigstore-rekor".\n  4. transparency_log.rekor_public_key_pem is in KNOWN_REKOR_PUBLIC_KEYS\n     (pinned Sigstore allowlist shipped with this verifier).\n  5. ECDSA P-256 verify of signed_entry_timestamp over canonical SET\n     payload {body, integratedTime, logID, logIndex}. Proves Rekor\'s\n     attestation that the leaf was integrated at integratedTime.\n  6. Rekor leaf body is kind=="hashedrekord" and:\n     - spec.data.hash.algorithm == "sha256"\n     - spec.data.hash.value == sha256(canonical manifest body bytes)\n     - spec.signature.publicKey.content (b64) decodes to a PEM\n       SubjectPublicKeyInfo parseable as an ECDSA-P-256 public key\n       (the per-submission ephemeral submitter key)\n     - spec.signature.content (b64) decodes to a DER ECDSA signature\n       that verifies ECDSA-SHA256 over canonical manifest body bytes\n       under the leaf publicKey\n\nArchitecture (Path-beta dual signing). The Rekor leaf carries an\nECDSA-P-256 signature, not the manifest\'s Ed25519 signature. EdDSA is\nincompatible with hashedrekord (Sigstore issue #851) because hashedrekord\npasses only a pre-computed hash to the verifier while EdDSA must re-hash\nthe message internally. To anchor an Ed25519-signed NOUS manifest into\nRekor, the dossier signing pipeline generates a per-submission ephemeral\nECDSA-P-256 keypair, signs the same canonical bytes with it, and submits\nthe ECDSA artefact. Both signatures cover the same bytes: verification\nof the Ed25519 signature (step 1) proves authorship; verification of\nthe ECDSA signature (step 6) proves the integrity of the Rekor leaf\nwired to those same bytes. The Rekor anchor itself (step 5) proves the\nleaf was integrated at the claimed time.\n"""\nfrom __future__ import annotations\n\nimport base64\nimport hashlib\nimport json\nimport sys\nfrom pathlib import Path\n\nROOT = Path(__file__).parent\n\nKNOWN_REKOR_PUBLIC_KEYS = [\n    "-----BEGIN PUBLIC KEY-----\\n"\n    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE2G2Y+2tabdTV5BcGiBIx0a9fAFwr\\n"\n    "kBbmLSGtks4L3qX6yYY0zufBnhC8Ur/iy55GhWP/9A/bY2LhC30M9+RYtw==\\n"\n    "-----END PUBLIC KEY-----\\n",\n]\n\n\ndef _fail(msg: str) -> int:\n    print(f"FAIL: {msg}", file=sys.stderr)\n    return 1\n\n\ndef main() -> int:\n    try:\n        from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n            Ed25519PublicKey,\n        )\n        from cryptography.hazmat.primitives.asymmetric import ec\n        from cryptography.hazmat.primitives import hashes, serialization\n        from cryptography.hazmat.primitives.asymmetric.ec import ECDSA\n        from cryptography.exceptions import InvalidSignature\n    except ImportError:\n        print(\n            "ERROR: cryptography library required.\\n"\n            "Install: pip install \'cryptography>=42\'",\n            file=sys.stderr,\n        )\n        return 2\n\n    manifest_path = ROOT / "manifest.json"\n    if not manifest_path.is_file():\n        return _fail(f"manifest.json not found in {ROOT}")\n    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))\n\n    sig_block = manifest.get("signature")\n    if not sig_block:\n        return _fail("manifest has no signature block")\n    pub_b64 = sig_block.get("public_key_b64", "")\n    sig_b64 = sig_block.get("signature_b64", "")\n    if not pub_b64 or not sig_b64:\n        return _fail("manifest signature block incomplete")\n\n    body = {\n        k: v for k, v in manifest.items()\n        if k not in ("signature", "transparency_log")\n    }\n    body_bytes = json.dumps(\n        body, sort_keys=True, separators=(",", ":")\n    ).encode("utf-8")\n\n    try:\n        pub_key = Ed25519PublicKey.from_public_bytes(\n            base64.b64decode(pub_b64)\n        )\n        pub_key.verify(base64.b64decode(sig_b64), body_bytes)\n    except InvalidSignature:\n        return _fail("Ed25519 signature does NOT verify")\n    except Exception as e:\n        return _fail(f"signature verification error: {e}")\n    print("OK   Ed25519 manifest signature verified")\n\n    source_path = ROOT / "source.nous"\n    if not source_path.is_file():\n        return _fail(f"source.nous not found in {ROOT}")\n    src_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()\n    expected = manifest.get("source_sha256", "")\n    if src_sha != expected:\n        return _fail(\n            f"source.sha256 mismatch: file={src_sha[:16]}... "\n            f"manifest={expected[:16]}..."\n        )\n    print(f"OK   source.sha256 matches manifest ({src_sha[:16]}...)")\n\n    tlog = manifest.get("transparency_log")\n    if tlog is None:\n        return _fail(\n            "transparency_log block missing; this verifier ships with "\n            "a Rekor-anchored dossier and expects the block to be present"\n        )\n    if not isinstance(tlog, dict):\n        return _fail("transparency_log is not an object")\n    if tlog.get("provider") != "sigstore-rekor":\n        return _fail(\n            f"transparency_log.provider != \'sigstore-rekor\' "\n            f"(got {tlog.get(\'provider\')!r})"\n        )\n\n    rekor_pem = tlog.get("rekor_public_key_pem", "")\n    if rekor_pem not in KNOWN_REKOR_PUBLIC_KEYS:\n        return _fail(\n            "transparency_log.rekor_public_key_pem is not in the pinned "\n            "KNOWN_REKOR_PUBLIC_KEYS allowlist; the dossier was either "\n            "anchored under a rotated Sigstore key not yet trusted by "\n            "this verifier, or the dossier is tampered"\n        )\n\n    try:\n        rekor_pub = serialization.load_pem_public_key(\n            rekor_pem.encode("utf-8")\n        )\n    except Exception as e:\n        return _fail(f"rekor pubkey parse error: {e}")\n    if not isinstance(rekor_pub, ec.EllipticCurvePublicKey):\n        return _fail("rekor pubkey is not an EC key")\n    if not isinstance(rekor_pub.curve, ec.SECP256R1):\n        return _fail(\n            f"rekor pubkey curve is not P-256: {rekor_pub.curve.name}"\n        )\n\n    try:\n        set_payload = json.dumps(\n            {\n                "body": tlog["body_b64"],\n                "integratedTime": int(tlog["integrated_time"]),\n                "logID": tlog["log_id"],\n                "logIndex": int(tlog["log_index"]),\n            },\n            sort_keys=True,\n            separators=(",", ":"),\n        ).encode("utf-8")\n    except (KeyError, TypeError, ValueError) as e:\n        return _fail(f"transparency_log fields invalid: {e}")\n\n    try:\n        set_sig_der = base64.b64decode(\n            tlog["signed_entry_timestamp_b64"], validate=True\n        )\n    except (KeyError, ValueError) as e:\n        return _fail(f"SET decode error: {e}")\n\n    try:\n        rekor_pub.verify(set_sig_der, set_payload, ECDSA(hashes.SHA256()))\n    except InvalidSignature:\n        return _fail("Rekor SET signature does NOT verify")\n    except Exception as e:\n        return _fail(f"Rekor SET verification error: {e}")\n    print("OK   Rekor SignedEntryTimestamp verified")\n\n    try:\n        leaf_raw = base64.b64decode(tlog["body_b64"], validate=True)\n        leaf = json.loads(leaf_raw)\n    except Exception as e:\n        return _fail(f"rekor leaf decode error: {e}")\n\n    if not isinstance(leaf, dict) or leaf.get("kind") != "hashedrekord":\n        return _fail(\n            f"rekor leaf kind != \'hashedrekord\' "\n            f"(got {leaf.get(\'kind\') if isinstance(leaf, dict) else type(leaf).__name__})"\n        )\n    spec = leaf.get("spec", {})\n    if not isinstance(spec, dict):\n        return _fail("rekor leaf spec is not an object")\n\n    data_block = spec.get("data", {})\n    if not isinstance(data_block, dict):\n        return _fail("rekor leaf spec.data is not an object")\n    hash_block = data_block.get("hash", {})\n    if not isinstance(hash_block, dict):\n        return _fail("rekor leaf spec.data.hash is not an object")\n\n    if hash_block.get("algorithm") != "sha256":\n        return _fail(\n            f"rekor leaf hash.algorithm != \'sha256\' "\n            f"(got {hash_block.get(\'algorithm\')!r})"\n        )\n\n    expected_payload_sha = hashlib.sha256(body_bytes).hexdigest()\n    leaf_hash = hash_block.get("value", "")\n    if leaf_hash != expected_payload_sha:\n        return _fail(\n            f"rekor leaf payload hash mismatch: "\n            f"manifest={expected_payload_sha[:16]}... "\n            f"leaf={leaf_hash[:16]}..."\n        )\n\n    sig_inner = spec.get("signature", {})\n    if not isinstance(sig_inner, dict):\n        return _fail("rekor leaf spec.signature is not an object")\n\n    pk_inner = sig_inner.get("publicKey", {})\n    if not isinstance(pk_inner, dict):\n        return _fail("rekor leaf spec.signature.publicKey is not an object")\n\n    try:\n        leaf_pubkey_pem = base64.b64decode(\n            pk_inner.get("content", ""), validate=True\n        )\n    except Exception as e:\n        return _fail(f"rekor leaf pubkey b64 decode error: {e}")\n\n    try:\n        leaf_pub = serialization.load_pem_public_key(leaf_pubkey_pem)\n    except Exception as e:\n        return _fail(f"rekor leaf pubkey PEM parse error: {e}")\n\n    if not isinstance(leaf_pub, ec.EllipticCurvePublicKey):\n        return _fail(\n            f"rekor leaf publicKey is not an EC key "\n            f"(got {type(leaf_pub).__name__}); Path-beta dual signing "\n            f"requires ECDSA-P-256 leaf publicKey"\n        )\n    if not isinstance(leaf_pub.curve, ec.SECP256R1):\n        return _fail(\n            f"rekor leaf publicKey curve is not P-256: "\n            f"{leaf_pub.curve.name}"\n        )\n\n    try:\n        leaf_sig_der = base64.b64decode(\n            sig_inner.get("content", ""), validate=True\n        )\n    except Exception as e:\n        return _fail(f"rekor leaf signature b64 decode error: {e}")\n\n    try:\n        leaf_pub.verify(leaf_sig_der, body_bytes, ECDSA(hashes.SHA256()))\n    except InvalidSignature:\n        return _fail(\n            "rekor leaf ECDSA signature does NOT verify over manifest "\n            "canonical body bytes (anchored signature is for different "\n            "bytes or has been tampered)"\n        )\n    except Exception as e:\n        return _fail(f"rekor leaf signature verification error: {e}")\n\n    print(\n        f"OK   Rekor leaf ECDSA-P-256 signature verified "\n        f"(log_index={tlog.get(\'log_index\')})"\n    )\n\n    print()\n    print(\n        "VERDICT: PASS (Ed25519 manifest + Sigstore Rekor anchor "\n        "via Path-beta dual signing)"\n    )\n    print(f"  world:        {manifest.get(\'world_name\', \'?\')}")\n    cap = manifest.get("cost_cap_usd", "?")\n    print(f"  cost_cap:     ${cap} USD")\n    margin = manifest.get("safety_margin_pct")\n    if margin:\n        try:\n            from decimal import Decimal\n            eff = Decimal(cap) * Decimal(100 - margin) / Decimal(100)\n            print(\n                f"  effective:    ${eff} USD ({margin}% safety margin)"\n            )\n        except Exception:\n            print(f"  margin:       {margin}%")\n    print(f"  verdict:      {manifest.get(\'verdict\', \'?\')}")\n    print(f"  solver:       {manifest.get(\'solver_version\', \'?\')}")\n    print(f"  timestamp:    {manifest.get(\'timestamp_utc\', \'?\')}")\n    print(f"  rekor_log_id: {tlog.get(\'log_id\')}")\n    print(f"  rekor_index:  {tlog.get(\'log_index\')}")\n    print(f"  rekor_time:   {tlog.get(\'integrated_time\')}")\n    return 0\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'

# __session82_dossier_hybrid_template_v1__
VERIFY_OFFLINE_PY_HYBRID: str = '#!/usr/bin/env python3\n"""Offline verification of NOUS dossier (Annex IV), hybrid mode.\n\nAccepts both Rekor-anchored dossiers (NOUS v5.3.0+) and unanchored\ndossiers (legacy / anchor=none).\n\n  - When the manifest carries a transparency_log block, the full\n    Sigstore Rekor anchor is verified (Path-beta dual signing:\n    Ed25519 author + ECDSA-P-256 submitter leaf, plus Rekor\n    signedEntryTimestamp).\n  - When the block is absent, the verifier performs Ed25519\n    signature and source SHA checks only, and requires the\n    --allow-unanchored flag to proceed. Default is refuse-on-missing,\n    aligned with the NOUS "refuse over guess" axiom.\n\nUsage:\n  python3 verify_offline.py                  # strict: refuses unanchored\n  python3 verify_offline.py --allow-unanchored\n\nExit:\n  0 = PASS, 1 = FAIL, 2 = environment error.\n\nRequires: cryptography library (no NOUS install needed).\n"""\nfrom __future__ import annotations\n\nimport argparse\nimport base64\nimport hashlib\nimport json\nimport sys\nfrom pathlib import Path\n\nROOT = Path(__file__).parent\n\nKNOWN_REKOR_PUBLIC_KEYS = [\n    "-----BEGIN PUBLIC KEY-----\\n"\n    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE2G2Y+2tabdTV5BcGiBIx0a9fAFwr\\n"\n    "kBbmLSGtks4L3qX6yYY0zufBnhC8Ur/iy55GhWP/9A/bY2LhC30M9+RYtw==\\n"\n    "-----END PUBLIC KEY-----\\n",\n]\n\n\ndef _fail(msg):\n    print("FAIL: " + msg, file=sys.stderr)\n    return 1\n\n\ndef _check_signature_and_source(manifest, root):\n    try:\n        from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n            Ed25519PublicKey,\n        )\n        from cryptography.exceptions import InvalidSignature\n    except ImportError:\n        print(\n            "ERROR: cryptography library required.\\n"\n            "Install: pip install \'cryptography>=42\'",\n            file=sys.stderr,\n        )\n        return (2, None)\n\n    sig_block = manifest.get("signature")\n    if not sig_block:\n        return (_fail("manifest has no signature block"), None)\n    pub_b64 = sig_block.get("public_key_b64", "")\n    sig_b64 = sig_block.get("signature_b64", "")\n    if not pub_b64 or not sig_b64:\n        return (_fail("manifest signature block incomplete"), None)\n\n    body = {\n        k: v for k, v in manifest.items()\n        if k not in ("signature", "transparency_log")\n    }\n    body_bytes = json.dumps(\n        body, sort_keys=True, separators=(",", ":")\n    ).encode("utf-8")\n\n    try:\n        pub_key = Ed25519PublicKey.from_public_bytes(\n            base64.b64decode(pub_b64)\n        )\n        pub_key.verify(base64.b64decode(sig_b64), body_bytes)\n    except InvalidSignature:\n        return (_fail("Ed25519 signature does NOT verify"), None)\n    except Exception as e:\n        return (_fail("signature verification error: " + str(e)), None)\n    print("OK   Ed25519 manifest signature verified")\n\n    source_path = root / "source.nous"\n    if not source_path.is_file():\n        return (_fail("source.nous not found in " + str(root)), None)\n    src_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()\n    expected = manifest.get("source_sha256", "")\n    if src_sha != expected:\n        return (\n            _fail(\n                "source.sha256 mismatch: file=" + src_sha[:16] + "... "\n                "manifest=" + expected[:16] + "..."\n            ),\n            None,\n        )\n    print("OK   source.sha256 matches manifest (" + src_sha[:16] + "...)")\n    return (None, body_bytes)\n\n\ndef _check_rekor_anchor(manifest, body_bytes):\n    try:\n        from cryptography.hazmat.primitives.asymmetric import ec\n        from cryptography.hazmat.primitives import hashes, serialization\n        from cryptography.hazmat.primitives.asymmetric.ec import ECDSA\n        from cryptography.exceptions import InvalidSignature\n    except ImportError:\n        print(\n            "ERROR: cryptography library required.\\n"\n            "Install: pip install \'cryptography>=42\'",\n            file=sys.stderr,\n        )\n        return 2\n\n    tlog = manifest.get("transparency_log")\n    if not isinstance(tlog, dict):\n        return _fail("transparency_log is not an object")\n    if tlog.get("provider") != "sigstore-rekor":\n        return _fail(\n            "transparency_log.provider != \'sigstore-rekor\' "\n            "(got " + repr(tlog.get("provider")) + ")"\n        )\n\n    rekor_pem = tlog.get("rekor_public_key_pem", "")\n    if rekor_pem not in KNOWN_REKOR_PUBLIC_KEYS:\n        return _fail(\n            "transparency_log.rekor_public_key_pem is not in the pinned "\n            "KNOWN_REKOR_PUBLIC_KEYS allowlist; the dossier was either "\n            "anchored under a rotated Sigstore key not yet trusted by "\n            "this verifier, or the dossier is tampered"\n        )\n\n    try:\n        rekor_pub = serialization.load_pem_public_key(\n            rekor_pem.encode("utf-8")\n        )\n    except Exception as e:\n        return _fail("rekor pubkey parse error: " + str(e))\n    if not isinstance(rekor_pub, ec.EllipticCurvePublicKey):\n        return _fail("rekor pubkey is not an EC key")\n    if not isinstance(rekor_pub.curve, ec.SECP256R1):\n        return _fail(\n            "rekor pubkey curve is not P-256: " + rekor_pub.curve.name\n        )\n\n    try:\n        set_payload = json.dumps(\n            {\n                "body": tlog["body_b64"],\n                "integratedTime": int(tlog["integrated_time"]),\n                "logID": tlog["log_id"],\n                "logIndex": int(tlog["log_index"]),\n            },\n            sort_keys=True,\n            separators=(",", ":"),\n        ).encode("utf-8")\n    except (KeyError, TypeError, ValueError) as e:\n        return _fail("transparency_log fields invalid: " + str(e))\n\n    try:\n        set_sig_der = base64.b64decode(\n            tlog["signed_entry_timestamp_b64"], validate=True\n        )\n    except (KeyError, ValueError) as e:\n        return _fail("SET decode error: " + str(e))\n\n    try:\n        rekor_pub.verify(set_sig_der, set_payload, ECDSA(hashes.SHA256()))\n    except InvalidSignature:\n        return _fail("Rekor SET signature does NOT verify")\n    except Exception as e:\n        return _fail("Rekor SET verification error: " + str(e))\n    print("OK   Rekor SignedEntryTimestamp verified")\n\n    try:\n        leaf_raw = base64.b64decode(tlog["body_b64"], validate=True)\n        leaf = json.loads(leaf_raw)\n    except Exception as e:\n        return _fail("rekor leaf decode error: " + str(e))\n\n    if not isinstance(leaf, dict) or leaf.get("kind") != "hashedrekord":\n        return _fail("rekor leaf kind != \'hashedrekord\'")\n    spec = leaf.get("spec", {})\n    if not isinstance(spec, dict):\n        return _fail("rekor leaf spec is not an object")\n\n    data_block = spec.get("data", {})\n    if not isinstance(data_block, dict):\n        return _fail("rekor leaf spec.data is not an object")\n    hash_block = data_block.get("hash", {})\n    if not isinstance(hash_block, dict):\n        return _fail("rekor leaf spec.data.hash is not an object")\n\n    if hash_block.get("algorithm") != "sha256":\n        return _fail(\n            "rekor leaf hash.algorithm != \'sha256\' "\n            "(got " + repr(hash_block.get("algorithm")) + ")"\n        )\n\n    expected_payload_sha = hashlib.sha256(body_bytes).hexdigest()\n    leaf_hash = hash_block.get("value", "")\n    if leaf_hash != expected_payload_sha:\n        return _fail(\n            "rekor leaf payload hash mismatch: "\n            "manifest=" + expected_payload_sha[:16] + "... "\n            "leaf=" + leaf_hash[:16] + "..."\n        )\n\n    sig_inner = spec.get("signature", {})\n    if not isinstance(sig_inner, dict):\n        return _fail("rekor leaf spec.signature is not an object")\n\n    pk_inner = sig_inner.get("publicKey", {})\n    if not isinstance(pk_inner, dict):\n        return _fail("rekor leaf spec.signature.publicKey is not an object")\n\n    try:\n        leaf_pubkey_pem = base64.b64decode(\n            pk_inner.get("content", ""), validate=True\n        )\n    except Exception as e:\n        return _fail("rekor leaf pubkey b64 decode error: " + str(e))\n\n    try:\n        leaf_pub = serialization.load_pem_public_key(leaf_pubkey_pem)\n    except Exception as e:\n        return _fail("rekor leaf pubkey PEM parse error: " + str(e))\n\n    if not isinstance(leaf_pub, ec.EllipticCurvePublicKey):\n        return _fail(\n            "rekor leaf publicKey is not an EC key; "\n            "Path-beta dual signing requires ECDSA-P-256 leaf publicKey"\n        )\n    if not isinstance(leaf_pub.curve, ec.SECP256R1):\n        return _fail(\n            "rekor leaf publicKey curve is not P-256: "\n            + leaf_pub.curve.name\n        )\n\n    try:\n        leaf_sig_der = base64.b64decode(\n            sig_inner.get("content", ""), validate=True\n        )\n    except Exception as e:\n        return _fail("rekor leaf signature b64 decode error: " + str(e))\n\n    try:\n        leaf_pub.verify(leaf_sig_der, body_bytes, ECDSA(hashes.SHA256()))\n    except InvalidSignature:\n        return _fail(\n            "rekor leaf ECDSA signature does NOT verify over manifest "\n            "canonical body bytes (anchored signature is for different "\n            "bytes or has been tampered)"\n        )\n    except Exception as e:\n        return _fail("rekor leaf signature verification error: " + str(e))\n\n    print(\n        "OK   Rekor leaf ECDSA-P-256 signature verified "\n        "(log_index=" + str(tlog.get("log_index")) + ")"\n    )\n    return 0\n\n\ndef _print_summary(manifest, anchored, tlog):\n    print()\n    if anchored:\n        print(\n            "VERDICT: PASS (Ed25519 manifest + Sigstore Rekor anchor "\n            "via Path-beta dual signing)"\n        )\n    else:\n        print(\n            "VERDICT: PASS (Ed25519 manifest only -- "\n            "unanchored dossier, no Sigstore Rekor anchor present)"\n        )\n    print("  world:        " + str(manifest.get("world_name", "?")))\n    cap = manifest.get("cost_cap_usd", "?")\n    print("  cost_cap:     $" + str(cap) + " USD")\n    margin = manifest.get("safety_margin_pct")\n    if margin:\n        try:\n            from decimal import Decimal\n            eff = Decimal(str(cap)) * Decimal(100 - margin) / Decimal(100)\n            print(\n                "  effective:    $" + str(eff)\n                + " USD (" + str(margin) + "% safety margin)"\n            )\n        except Exception:\n            print("  margin:       " + str(margin) + "%")\n    print("  verdict:      " + str(manifest.get("verdict", "?")))\n    print("  solver:       " + str(manifest.get("solver_version", "?")))\n    print("  timestamp:    " + str(manifest.get("timestamp_utc", "?")))\n    if anchored and isinstance(tlog, dict):\n        print("  rekor_log_id: " + str(tlog.get("log_id")))\n        print("  rekor_index:  " + str(tlog.get("log_index")))\n        print("  rekor_time:   " + str(tlog.get("integrated_time")))\n\n\ndef main(argv=None):\n    parser = argparse.ArgumentParser(\n        description="Offline verification of NOUS dossier (hybrid mode)"\n    )\n    parser.add_argument(\n        "--allow-unanchored",\n        action="store_true",\n        help=(\n            "accept dossiers without a Sigstore Rekor transparency_log "\n            "block; only Ed25519 author signature and source identity "\n            "are then verified. By default the verifier refuses "\n            "unanchored dossiers."\n        ),\n    )\n    args = parser.parse_args(argv)\n\n    manifest_path = ROOT / "manifest.json"\n    if not manifest_path.is_file():\n        return _fail("manifest.json not found in " + str(ROOT))\n    try:\n        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))\n    except json.JSONDecodeError as e:\n        return _fail("manifest.json parse error: " + str(e))\n\n    rc, body_bytes = _check_signature_and_source(manifest, ROOT)\n    if rc is not None:\n        return rc\n\n    tlog = manifest.get("transparency_log")\n    if tlog is None:\n        if not args.allow_unanchored:\n            return _fail(\n                "transparency_log block missing; the dossier is "\n                "unanchored. Re-run with --allow-unanchored to accept "\n                "Ed25519-only verification, or obtain an anchored "\n                "dossier (NOUS v5.3.0 or later)."\n            )\n        _print_summary(manifest, anchored=False, tlog=None)\n        return 0\n\n    rc2 = _check_rekor_anchor(manifest, body_bytes)\n    if rc2 != 0:\n        return rc2\n\n    _print_summary(manifest, anchored=True, tlog=tlog)\n    return 0\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'


def _candidate_pricing_paths(
    custom_path: Optional[Path],
) -> list[Path]:
    """Return ordered list of pricing TOML paths to probe."""
    from pricing import _candidate_layers
    paths: list[Path] = []
    if custom_path is not None:
        paths.append(custom_path)
    for layer in _candidate_layers(None):
        if layer.path is None:
            continue
        if layer.path not in paths and layer.path.is_file():
            paths.append(layer.path)
    return paths


def _find_pricing_match(
    target_sha: str,
    custom_path: Optional[Path],
) -> tuple[Path, PricingTable]:
    """Locate pricing TOML whose load matches target sha256."""
    for path in _candidate_pricing_paths(custom_path):
        if not path.is_file():
            continue
        try:
            table = load_pricing(path)
        except Exception:
            continue
        if table.sha256() == target_sha:
            return path, table
    raise DossierError(
        f"no pricing TOML in candidate layers matches manifest "
        f"pricing_sha256 {target_sha[:16]}..."
    )


def _public_key_raw_bytes(pub: Ed25519PublicKey) -> bytes:
    """Extract 32-byte raw Ed25519 pubkey across cryptography versions."""
    if hasattr(pub, "public_bytes_raw"):
        return pub.public_bytes_raw()
    return pub.public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )


def _annex_iv_readme(
    world_name: str,
    nous_version: str,
    smt_emit_version: str,
    cost_cap_usd: str,
    max_ticks: int,
    verdict: str,
    solver_version: str,
    safety_margin_pct: Optional[int],
    timestamp_utc: str,
    source_sha: str,
    pricing_sha: str,
    smt_spec_sha: str,
) -> str:
    margin_lines = ""
    if safety_margin_pct is not None and safety_margin_pct > 0:
        eff = (Decimal(cost_cap_usd)
               * Decimal(100 - safety_margin_pct) / Decimal(100))
        margin_lines = (
            f"- **Safety margin applied:** {safety_margin_pct}% "
            f"(effective cap: ${eff} USD)\n"
        )

    return (
        f"# EU AI Act Annex IV Compliance Dossier\n\n"
        f"**World:** `{world_name}`  \n"
        f"**NOUS version:** {nous_version}  \n"
        f"**SMT emit version:** {smt_emit_version}  \n"
        f"**Verdict:** `{verdict}`  \n"
        f"**Solver:** {solver_version}  \n"
        f"**Timestamp:** {timestamp_utc}\n\n"
        f"## Cost-bound proof\n\n"
        f"- **Declared cost cap:** ${cost_cap_usd} USD\n"
        f"- **Max ticks:** {max_ticks}\n"
        f"{margin_lines}"
        f"\n"
        f"## Annex IV item-by-item mapping\n\n"
        f"| Annex IV requirement | Evidence in this dossier |\n"
        f"|---|---|\n"
        f"| 1. General description | `manifest.json` "
        f"(`world_name`, `nous_version`, `smt_emit_version`) |\n"
        f"| 2. Detailed description (development process) | "
        f"`source.nous` (audited source, content-addressed) |\n"
        f"| 3. Monitoring and control | `manifest.json` "
        f"(`verdict`, `cost_cap_usd`, optional `safety_margin_pct`) |\n"
        f"| 4. Performance metrics | "
        f"Cost upper bound is mechanically proven by Z3; "
        f"`manifest.json` carries the verdict and effective cap |\n"
        f"| 5. Risk management system (Article 9) | "
        f"`cost_cap` declaration in source + Z3 proof; "
        f"full Article 9 process is the operator\'s responsibility |\n"
        f"| 6. Lifecycle changes | "
        f"`source_sha256`, `pricing_sha256`, `smt_spec_sha256` "
        f"in `manifest.json` content-address each artefact version |\n"
        f"| 7. Standards applied | "
        f"SMT-LIB 2.6, Z3 ({solver_version}), Ed25519, "
        f"RFC 8785-style canonical JSON |\n"
        f"| 8. EU declaration of conformity | "
        f"Operator\'s responsibility (this dossier provides evidence) |\n"
        f"| 9. Post-market monitoring | "
        f"NOUS Phase D deterministic replay (optional `replay {{{{...}}}}` "
        f"block in source) |\n"
        f"\n"
        f"## Cryptographic chain of custody\n\n"
        f"- `manifest.json` is signed with Ed25519 over RFC 8785-style "
        f"canonical JSON (sorted keys, no whitespace).\n"
        f"- `public_key.b64` carries the raw 32-byte Ed25519 public "
        f"key (base64).\n"
        f"- `source_sha256` = `{source_sha}`\n"
        f"- `pricing_sha256` = `{pricing_sha}`\n"
        f"- `smt_spec_sha256` = `{smt_spec_sha}`\n\n"
        f"## Offline verification\n\n"
        f"```\n"
        f"python3 verify_offline.py\n"
        f"```\n\n"
        f"Exit `0` = PASS, `1` = FAIL (signature broken or source "
        f"hash mismatch). Requires only the `cryptography` library "
        f"(no NOUS install needed).\n\n"
        f"## Reproducing the proof from scratch\n\n"
        f"```\n"
        f"pip install \'nous-lang[smt]\'\n"
        f"nous verify source.nous --smt --prices pricing.toml\n"
        f"```\n\n"
        f"Expected output: `PROVEN: total_cost <= ${cost_cap_usd} "
        f"USD across all execution paths.`\n"
    )


def build_dossier(
    source: Path,
    *,
    manifest: Optional[Path] = None,
    prices: Optional[Path] = None,
    output: Optional[Path] = None,
    today: Optional[date] = None,
    anchor: str = "none",
    _test_rekor_anchor: "object | None" = None,
) -> DossierResult:
    """Build an Annex IV-aligned dossier directory.

    # __nous_aetherproof_dossier_rekor_emit_v1__

    When ``anchor == "none"`` (default), output is BYTE-IDENTICAL to
    v5.2.0: the input manifest.json is copied verbatim, and the
    Ed25519-only ``VERIFY_OFFLINE_PY`` template is emitted.

    When ``anchor == "rekor"``, the Ed25519 signature event is
    submitted to the public Sigstore Rekor transparency log. The
    emitted ``manifest.json`` gains a ``transparency_log`` block
    alongside the existing ``signature`` block. The emitted
    ``verify_offline.py`` is ``VERIFY_OFFLINE_PY_WITH_REKOR``, which
    performs the Ed25519 + source-hash checks plus ECDSA-P-256
    Rekor SignedEntryTimestamp verification and leaf-body cross-check.

    ``_test_rekor_anchor`` is a private hook accepting a pre-built
    ``rekor_anchor.RekorAnchor`` so unit tests can exercise the
    anchored path without making a live Rekor submission.
    """
    source = Path(source).resolve()
    if not source.is_file():
        raise DossierError(f"source not found: {source}")
    source_bytes = source.read_bytes()
    source_sha = hashlib.sha256(source_bytes).hexdigest()

    if manifest is None:
        manifest = source.with_suffix(".manifest.json")
    manifest = Path(manifest).resolve()
    if not manifest.is_file():
        raise DossierError(f"manifest not found: {manifest}")
    manifest_text = manifest.read_text(encoding="utf-8")

    parsed_manifest, sig, pub = parse_manifest_json(
        manifest_text
    )
    if not verify_manifest_signature(parsed_manifest, sig, pub):
        raise DossierError(
            "manifest Ed25519 signature does NOT verify"
        )

    if source_sha != parsed_manifest.source_sha256:
        raise DossierError(
            f"source.sha256 mismatch: file={source_sha[:16]}... "
            f"manifest={parsed_manifest.source_sha256[:16]}..."
        )

    pricing_path, pricing_table = _find_pricing_match(
        parsed_manifest.pricing_sha256,
        Path(prices).resolve() if prices is not None else None,
    )

    program = parse_nous(source_bytes.decode("utf-8"))
    spec = emit_smt(
        program,
        pricing_table,
        source_text=source_bytes.decode("utf-8"),
        today=today,
        margin_pct=(parsed_manifest.safety_margin_pct or 0),
    )
    if spec.sha256() != parsed_manifest.smt_spec_sha256:
        raise DossierError(
            f"smt_spec.sha256 mismatch: regenerated="
            f"{spec.sha256()[:16]}... "
            f"manifest={parsed_manifest.smt_spec_sha256[:16]}..."
        )

    if output is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = source.parent / f"{source.stem}_dossier_{ts}"
    output = Path(output).resolve()
    if output.exists() and output.is_dir() and any(output.iterdir()):
        raise DossierError(
            f"output directory not empty: {output}"
        )
    output.mkdir(parents=True, exist_ok=True)

    files: list[str] = []

    (output / "source.nous").write_bytes(source_bytes)
    files.append("source.nous")

    rekor_anchor_obj = None
    if anchor == "rekor":
        if _test_rekor_anchor is not None:
            rekor_anchor_obj = _test_rekor_anchor
        else:
            from rekor_anchor import anchor_manifest_to_rekor
            rekor_anchor_obj = anchor_manifest_to_rekor(
                manifest_canonical_bytes=parsed_manifest.canonical_bytes(),
                manifest_signature_b64=base64.b64encode(
                    sig
                ).decode("ascii"),
                manifest_public_key_b64=base64.b64encode(
                    _public_key_raw_bytes(pub)
                ).decode("ascii"),
            )
        from manifest import manifest_json as _render_manifest_json
        rendered_manifest_text = _render_manifest_json(
            parsed_manifest, sig, pub, rekor_anchor=rekor_anchor_obj
        )
        (output / "manifest.json").write_text(
            rendered_manifest_text, encoding="utf-8"
        )
    elif anchor == "none":
        (output / "manifest.json").write_text(
            manifest_text, encoding="utf-8"
        )
    else:
        raise DossierError(
            f"unsupported anchor mode: {anchor!r} "
            f"(expected 'none' or 'rekor')"
        )
    files.append("manifest.json")

    shutil.copy2(pricing_path, output / "pricing.toml")
    files.append("pricing.toml")

    raw_pub = _public_key_raw_bytes(pub)
    (output / "public_key.b64").write_text(
        base64.b64encode(raw_pub).decode("ascii") + "\n",
        encoding="utf-8",
    )
    files.append("public_key.b64")

    readme = _annex_iv_readme(
        world_name=parsed_manifest.world_name,
        nous_version=parsed_manifest.nous_version,
        smt_emit_version=parsed_manifest.smt_emit_version,
        cost_cap_usd=parsed_manifest.cost_cap_usd,
        max_ticks=parsed_manifest.max_ticks,
        verdict=parsed_manifest.verdict,
        solver_version=parsed_manifest.solver_version,
        safety_margin_pct=parsed_manifest.safety_margin_pct,
        timestamp_utc=parsed_manifest.timestamp_utc,
        source_sha=parsed_manifest.source_sha256,
        pricing_sha=parsed_manifest.pricing_sha256,
        smt_spec_sha=parsed_manifest.smt_spec_sha256,
    )
    (output / "README.md").write_text(readme, encoding="utf-8")
    files.append("README.md")

    verify_path = output / "verify_offline.py"
    if anchor == "rekor":
        verify_path.write_text(
            VERIFY_OFFLINE_PY_WITH_REKOR, encoding="utf-8"
        )
    else:
        verify_path.write_text(VERIFY_OFFLINE_PY, encoding="utf-8")
    verify_path.chmod(0o755)
    files.append("verify_offline.py")

    return DossierResult(
        output_dir=output,
        files=tuple(files),
        world_name=parsed_manifest.world_name,
        verdict=parsed_manifest.verdict,
        safety_margin_pct=parsed_manifest.safety_margin_pct,
    )
