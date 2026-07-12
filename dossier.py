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


VERIFY_OFFLINE_PY: str = '#!/usr/bin/env python3\n"""Offline verification of NOUS dossier (Annex IV).\nUsage: python3 verify_offline.py\nExit:  0 = PASS, 1 = FAIL, 2 = environment error.\nRequires: cryptography library (no NOUS install needed).\n"""\nfrom __future__ import annotations\n\nimport base64\nimport hashlib\nimport json\nimport sys\nfrom pathlib import Path\n\nROOT = Path(__file__).parent\n\n\ndef _fail(msg: str) -> int:\n    print(f"FAIL: {msg}", file=sys.stderr)\n    return 1\n\n\ndef _cost_check_serialized(doc):  # __s174_g1_cost_reproof__\n    from fractions import Fraction\n    constraints = doc.get("constraints")\n    multipliers = doc.get("multipliers")\n    if not isinstance(constraints, list) or not isinstance(\n        multipliers, list\n    ):\n        return False\n    if len(constraints) != len(multipliers):\n        return False\n    lam = []\n    for m in multipliers:\n        try:\n            lam.append(Fraction(m))\n        except (ValueError, TypeError, ZeroDivisionError):\n            return False\n    if any(x < 0 for x in lam):\n        return False\n    if not any(x > 0 for x in lam):\n        return False\n    combined = {}\n    strict = False\n    for x, c in zip(lam, constraints):\n        if x == 0:\n            continue\n        if not isinstance(c, dict):\n            return False\n        coeffs = c.get("coeffs")\n        if not isinstance(coeffs, dict):\n            return False\n        for k, v in coeffs.items():\n            try:\n                fv = Fraction(v)\n            except (ValueError, TypeError, ZeroDivisionError):\n                return False\n            combined[k] = combined.get(k, Fraction(0)) + x * fv\n        if c.get("strict"):\n            strict = True\n    for k, v in combined.items():\n        if k != "" and v != 0:\n            return False\n    const = combined.get("", Fraction(0))\n    if const > 0:\n        return True\n    if const == 0 and strict:\n        return True\n    return False\n\n\ndef main() -> int:\n    try:\n        from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n            Ed25519PublicKey,\n        )\n        from cryptography.exceptions import InvalidSignature\n    except ImportError:\n        print(\n            "ERROR: cryptography library required.\\n"\n            "Install: pip install \'cryptography>=42\'",\n            file=sys.stderr,\n        )\n        return 2\n\n    manifest_path = ROOT / "manifest.json"\n    if not manifest_path.is_file():\n        return _fail(f"manifest.json not found in {ROOT}")\n    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))\n\n    sig_block = manifest.get("signature")\n    if not sig_block:\n        return _fail("manifest has no signature block")\n    pub_b64 = sig_block.get("public_key_b64", "")\n    sig_b64 = sig_block.get("signature_b64", "")\n    if not pub_b64 or not sig_b64:\n        return _fail("manifest signature block incomplete")\n\n    body = {k: v for k, v in manifest.items() if k != "signature"}\n    body_bytes = json.dumps(\n        body, sort_keys=True, separators=(",", ":")\n    ).encode("utf-8")\n\n    try:\n        pub_key = Ed25519PublicKey.from_public_bytes(\n            base64.b64decode(pub_b64)\n        )\n        pub_key.verify(base64.b64decode(sig_b64), body_bytes)\n    except InvalidSignature:\n        return _fail("Ed25519 signature does NOT verify")\n    except Exception as e:\n        return _fail(f"signature verification error: {e}")\n    print("OK   Ed25519 signature verified")\n\n    source_path = ROOT / "source.nous"\n    if not source_path.is_file():\n        return _fail(f"source.nous not found in {ROOT}")\n    src_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()\n    expected = manifest.get("source_sha256", "")\n    if src_sha != expected:\n        return _fail(\n            f"source.sha256 mismatch: file={src_sha[:16]}... "\n            f"manifest={expected[:16]}..."\n        )\n    print(f"OK   source.sha256 matches manifest ({src_sha[:16]}...)")\n\n    cost_expected = manifest.get("cost_farkas_sha256")  # __s174_g1_cost_reproof__\n    if cost_expected:\n        cost_path = ROOT / "cost.farkas.json"\n        if not cost_path.is_file():\n            return _fail(\n                "manifest declares cost_farkas_sha256 but "\n                "cost.farkas.json is not present in the dossier "\n                "(missing cost-cap evidence)"\n            )\n        cost_bytes = cost_path.read_bytes()\n        cost_sha = hashlib.sha256(cost_bytes).hexdigest()\n        if cost_sha != cost_expected:\n            return _fail(\n                "cost.farkas.json sha256 mismatch: file=" + cost_sha[:16]\n                + "... manifest=" + cost_expected[:16]\n                + "... (cost-cap Farkas certificate tampered or "\n                "substituted)"\n            )\n        try:\n            cost_doc = json.loads(cost_bytes.decode("utf-8"))\n        except Exception as e:\n            return _fail("cost.farkas.json parse error: " + str(e))\n        if not _cost_check_serialized(cost_doc):\n            return _fail(\n                "cost-cap Farkas certificate does NOT prove the bound: "\n                "the declared multipliers do not collapse the linear "\n                "system to a numeric contradiction (cost overrun or "\n                "forged certificate)"\n            )\n        print(\n            "OK   cost-cap Farkas certificate PROVEN offline by "\n            "rational arithmetic, no solver (contradiction: "\n            + str(cost_doc.get("contradiction", "?")) + ")"\n        )\n\n    print()\n    print("VERDICT: PASS")\n    print(f"  world:      {manifest.get(\'world_name\', \'?\')}")\n    cap = manifest.get("cost_cap_usd", "?")\n    print(f"  cost_cap:   ${cap} USD")\n    margin = manifest.get("safety_margin_pct")\n    if margin:\n        try:\n            from decimal import Decimal\n            eff = Decimal(cap) * Decimal(100 - margin) / Decimal(100)\n            print(\n                f"  effective:  ${eff} USD ({margin}% safety margin)"\n            )\n        except Exception:\n            print(f"  margin:     {margin}%")\n    print(f"  verdict:    {manifest.get(\'verdict\', \'?\')}")\n    print(f"  solver:     {manifest.get(\'solver_version\', \'?\')}")\n    print(f"  timestamp:  {manifest.get(\'timestamp_utc\', \'?\')}")\n    return 0\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'


# __nous_aetherproof_verify_offline_rekor_v1__
# __nous_aetherproof_rekor_offline_verifier_pivot_v1__
VERIFY_OFFLINE_PY_WITH_REKOR: str = '#!/usr/bin/env python3\n"""Offline verification of NOUS dossier (Annex IV) with Sigstore Rekor anchor.\n\nUsage: python3 verify_offline.py\nExit:  0 = PASS, 1 = FAIL, 2 = environment error.\nRequires: cryptography library (no NOUS install needed).\n\nChecks performed:\n  1. Ed25519 signature over canonical manifest body bytes (signature and\n     transparency_log blocks stripped before recomputing canonical form).\n     Evidences that the holder of the embedded public key signed these\n     canonical manifest body bytes. NOUS runs no CA; the name-to-key\n     binding is operator-asserted.\n  2. source.nous sha256 matches manifest.source_sha256.\n  3. transparency_log.provider == "sigstore-rekor".\n  4. transparency_log.rekor_public_key_pem is in KNOWN_REKOR_PUBLIC_KEYS\n     (pinned Sigstore allowlist shipped with this verifier).\n  5. ECDSA P-256 verify of signed_entry_timestamp over canonical SET\n     payload {body, integratedTime, logID, logIndex}. Verifies Rekor\'s\n     attestation that the leaf was integrated at integratedTime.\n  6. Rekor leaf body is kind=="hashedrekord" and:\n     - spec.data.hash.algorithm == "sha256"\n     - spec.data.hash.value == sha256(canonical manifest body bytes)\n     - spec.signature.publicKey.content (b64) decodes to a PEM\n       SubjectPublicKeyInfo parseable as an ECDSA-P-256 public key\n       (the per-submission ephemeral submitter key)\n     - spec.signature.content (b64) decodes to a DER ECDSA signature\n       that verifies ECDSA-SHA256 over canonical manifest body bytes\n       under the leaf publicKey\n\nArchitecture (Path-beta dual signing). The Rekor leaf carries an\nECDSA-P-256 signature, not the manifest\'s Ed25519 signature. EdDSA is\nincompatible with hashedrekord (Sigstore issue #851) because hashedrekord\npasses only a pre-computed hash to the verifier while EdDSA must re-hash\nthe message internally. To anchor an Ed25519-signed NOUS manifest into\nRekor, the dossier signing pipeline generates a per-submission ephemeral\nECDSA-P-256 keypair, signs the same canonical bytes with it, and submits\nthe ECDSA artefact. Both signatures cover the same bytes: verification\nof the Ed25519 signature (step 1) evidences that the key holder\nsigned; verification of the ECDSA signature (step 6) evidences the\nintegrity of the Rekor leaf wired to those same bytes. The Rekor anchor\nitself (step 5) evidences an attestation by the log operator that the\nleaf was integrated at the claimed time. Each of these is EVIDENCE.\nNone is a Z3 or Farkas certificate, and the name-to-key binding is\noperator-asserted: NOUS runs no CA and certifies no identity.\n"""\nfrom __future__ import annotations\n\nimport base64\nimport hashlib\nimport json\nimport sys\nfrom pathlib import Path\n\nROOT = Path(__file__).parent\n\nKNOWN_REKOR_PUBLIC_KEYS = [\n    "-----BEGIN PUBLIC KEY-----\\n"\n    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE2G2Y+2tabdTV5BcGiBIx0a9fAFwr\\n"\n    "kBbmLSGtks4L3qX6yYY0zufBnhC8Ur/iy55GhWP/9A/bY2LhC30M9+RYtw==\\n"\n    "-----END PUBLIC KEY-----\\n",\n]\n\n\ndef _fail(msg: str) -> int:\n    print(f"FAIL: {msg}", file=sys.stderr)\n    return 1\n\n\ndef _cost_check_serialized(doc):  # __s174_g1_cost_reproof__\n    from fractions import Fraction\n    constraints = doc.get("constraints")\n    multipliers = doc.get("multipliers")\n    if not isinstance(constraints, list) or not isinstance(\n        multipliers, list\n    ):\n        return False\n    if len(constraints) != len(multipliers):\n        return False\n    lam = []\n    for m in multipliers:\n        try:\n            lam.append(Fraction(m))\n        except (ValueError, TypeError, ZeroDivisionError):\n            return False\n    if any(x < 0 for x in lam):\n        return False\n    if not any(x > 0 for x in lam):\n        return False\n    combined = {}\n    strict = False\n    for x, c in zip(lam, constraints):\n        if x == 0:\n            continue\n        if not isinstance(c, dict):\n            return False\n        coeffs = c.get("coeffs")\n        if not isinstance(coeffs, dict):\n            return False\n        for k, v in coeffs.items():\n            try:\n                fv = Fraction(v)\n            except (ValueError, TypeError, ZeroDivisionError):\n                return False\n            combined[k] = combined.get(k, Fraction(0)) + x * fv\n        if c.get("strict"):\n            strict = True\n    for k, v in combined.items():\n        if k != "" and v != 0:\n            return False\n    const = combined.get("", Fraction(0))\n    if const > 0:\n        return True\n    if const == 0 and strict:\n        return True\n    return False\n\n\ndef main() -> int:\n    try:\n        from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n            Ed25519PublicKey,\n        )\n        from cryptography.hazmat.primitives.asymmetric import ec\n        from cryptography.hazmat.primitives import hashes, serialization\n        from cryptography.hazmat.primitives.asymmetric.ec import ECDSA\n        from cryptography.exceptions import InvalidSignature\n    except ImportError:\n        print(\n            "ERROR: cryptography library required.\\n"\n            "Install: pip install \'cryptography>=42\'",\n            file=sys.stderr,\n        )\n        return 2\n\n    manifest_path = ROOT / "manifest.json"\n    if not manifest_path.is_file():\n        return _fail(f"manifest.json not found in {ROOT}")\n    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))\n\n    sig_block = manifest.get("signature")\n    if not sig_block:\n        return _fail("manifest has no signature block")\n    pub_b64 = sig_block.get("public_key_b64", "")\n    sig_b64 = sig_block.get("signature_b64", "")\n    if not pub_b64 or not sig_b64:\n        return _fail("manifest signature block incomplete")\n\n    body = {\n        k: v for k, v in manifest.items()\n        if k not in ("signature", "transparency_log")\n    }\n    body_bytes = json.dumps(\n        body, sort_keys=True, separators=(",", ":")\n    ).encode("utf-8")\n\n    try:\n        pub_key = Ed25519PublicKey.from_public_bytes(\n            base64.b64decode(pub_b64)\n        )\n        pub_key.verify(base64.b64decode(sig_b64), body_bytes)\n    except InvalidSignature:\n        return _fail("Ed25519 signature does NOT verify")\n    except Exception as e:\n        return _fail(f"signature verification error: {e}")\n    print("OK   Ed25519 manifest signature verified")\n\n    source_path = ROOT / "source.nous"\n    if not source_path.is_file():\n        return _fail(f"source.nous not found in {ROOT}")\n    src_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()\n    expected = manifest.get("source_sha256", "")\n    if src_sha != expected:\n        return _fail(\n            f"source.sha256 mismatch: file={src_sha[:16]}... "\n            f"manifest={expected[:16]}..."\n        )\n    print(f"OK   source.sha256 matches manifest ({src_sha[:16]}...)")\n\n    cost_expected = manifest.get("cost_farkas_sha256")  # __s174_g1_cost_reproof__\n    if cost_expected:\n        cost_path = ROOT / "cost.farkas.json"\n        if not cost_path.is_file():\n            return _fail(\n                "manifest declares cost_farkas_sha256 but "\n                "cost.farkas.json is not present in the dossier "\n                "(missing cost-cap evidence)"\n            )\n        cost_bytes = cost_path.read_bytes()\n        cost_sha = hashlib.sha256(cost_bytes).hexdigest()\n        if cost_sha != cost_expected:\n            return _fail(\n                "cost.farkas.json sha256 mismatch: file=" + cost_sha[:16]\n                + "... manifest=" + cost_expected[:16]\n                + "... (cost-cap Farkas certificate tampered or "\n                "substituted)"\n            )\n        try:\n            cost_doc = json.loads(cost_bytes.decode("utf-8"))\n        except Exception as e:\n            return _fail("cost.farkas.json parse error: " + str(e))\n        if not _cost_check_serialized(cost_doc):\n            return _fail(\n                "cost-cap Farkas certificate does NOT prove the bound: "\n                "the declared multipliers do not collapse the linear "\n                "system to a numeric contradiction (cost overrun or "\n                "forged certificate)"\n            )\n        print(\n            "OK   cost-cap Farkas certificate PROVEN offline by "\n            "rational arithmetic, no solver (contradiction: "\n            + str(cost_doc.get("contradiction", "?")) + ")"\n        )\n\n    tlog = manifest.get("transparency_log")\n    if tlog is None:\n        return _fail(\n            "transparency_log block missing; this verifier ships with "\n            "a Rekor-anchored dossier and expects the block to be present"\n        )\n    if not isinstance(tlog, dict):\n        return _fail("transparency_log is not an object")\n    if tlog.get("provider") != "sigstore-rekor":\n        return _fail(\n            f"transparency_log.provider != \'sigstore-rekor\' "\n            f"(got {tlog.get(\'provider\')!r})"\n        )\n\n    rekor_pem = tlog.get("rekor_public_key_pem", "")\n    if rekor_pem not in KNOWN_REKOR_PUBLIC_KEYS:\n        return _fail(\n            "transparency_log.rekor_public_key_pem is not in the pinned "\n            "KNOWN_REKOR_PUBLIC_KEYS allowlist; the dossier was either "\n            "anchored under a rotated Sigstore key not yet trusted by "\n            "this verifier, or the dossier is tampered"\n        )\n\n    try:\n        rekor_pub = serialization.load_pem_public_key(\n            rekor_pem.encode("utf-8")\n        )\n    except Exception as e:\n        return _fail(f"rekor pubkey parse error: {e}")\n    if not isinstance(rekor_pub, ec.EllipticCurvePublicKey):\n        return _fail("rekor pubkey is not an EC key")\n    if not isinstance(rekor_pub.curve, ec.SECP256R1):\n        return _fail(\n            f"rekor pubkey curve is not P-256: {rekor_pub.curve.name}"\n        )\n\n    try:\n        set_payload = json.dumps(\n            {\n                "body": tlog["body_b64"],\n                "integratedTime": int(tlog["integrated_time"]),\n                "logID": tlog["log_id"],\n                "logIndex": int(tlog["log_index"]),\n            },\n            sort_keys=True,\n            separators=(",", ":"),\n        ).encode("utf-8")\n    except (KeyError, TypeError, ValueError) as e:\n        return _fail(f"transparency_log fields invalid: {e}")\n\n    try:\n        set_sig_der = base64.b64decode(\n            tlog["signed_entry_timestamp_b64"], validate=True\n        )\n    except (KeyError, ValueError) as e:\n        return _fail(f"SET decode error: {e}")\n\n    try:\n        rekor_pub.verify(set_sig_der, set_payload, ECDSA(hashes.SHA256()))\n    except InvalidSignature:\n        return _fail("Rekor SET signature does NOT verify")\n    except Exception as e:\n        return _fail(f"Rekor SET verification error: {e}")\n    print("OK   Rekor SignedEntryTimestamp verified")\n\n    try:\n        leaf_raw = base64.b64decode(tlog["body_b64"], validate=True)\n        leaf = json.loads(leaf_raw)\n    except Exception as e:\n        return _fail(f"rekor leaf decode error: {e}")\n\n    if not isinstance(leaf, dict) or leaf.get("kind") != "hashedrekord":\n        return _fail(\n            f"rekor leaf kind != \'hashedrekord\' "\n            f"(got {leaf.get(\'kind\') if isinstance(leaf, dict) else type(leaf).__name__})"\n        )\n    spec = leaf.get("spec", {})\n    if not isinstance(spec, dict):\n        return _fail("rekor leaf spec is not an object")\n\n    data_block = spec.get("data", {})\n    if not isinstance(data_block, dict):\n        return _fail("rekor leaf spec.data is not an object")\n    hash_block = data_block.get("hash", {})\n    if not isinstance(hash_block, dict):\n        return _fail("rekor leaf spec.data.hash is not an object")\n\n    if hash_block.get("algorithm") != "sha256":\n        return _fail(\n            f"rekor leaf hash.algorithm != \'sha256\' "\n            f"(got {hash_block.get(\'algorithm\')!r})"\n        )\n\n    expected_payload_sha = hashlib.sha256(body_bytes).hexdigest()\n    leaf_hash = hash_block.get("value", "")\n    if leaf_hash != expected_payload_sha:\n        return _fail(\n            f"rekor leaf payload hash mismatch: "\n            f"manifest={expected_payload_sha[:16]}... "\n            f"leaf={leaf_hash[:16]}..."\n        )\n\n    sig_inner = spec.get("signature", {})\n    if not isinstance(sig_inner, dict):\n        return _fail("rekor leaf spec.signature is not an object")\n\n    pk_inner = sig_inner.get("publicKey", {})\n    if not isinstance(pk_inner, dict):\n        return _fail("rekor leaf spec.signature.publicKey is not an object")\n\n    try:\n        leaf_pubkey_pem = base64.b64decode(\n            pk_inner.get("content", ""), validate=True\n        )\n    except Exception as e:\n        return _fail(f"rekor leaf pubkey b64 decode error: {e}")\n\n    try:\n        leaf_pub = serialization.load_pem_public_key(leaf_pubkey_pem)\n    except Exception as e:\n        return _fail(f"rekor leaf pubkey PEM parse error: {e}")\n\n    if not isinstance(leaf_pub, ec.EllipticCurvePublicKey):\n        return _fail(\n            f"rekor leaf publicKey is not an EC key "\n            f"(got {type(leaf_pub).__name__}); Path-beta dual signing "\n            f"requires ECDSA-P-256 leaf publicKey"\n        )\n    if not isinstance(leaf_pub.curve, ec.SECP256R1):\n        return _fail(\n            f"rekor leaf publicKey curve is not P-256: "\n            f"{leaf_pub.curve.name}"\n        )\n\n    try:\n        leaf_sig_der = base64.b64decode(\n            sig_inner.get("content", ""), validate=True\n        )\n    except Exception as e:\n        return _fail(f"rekor leaf signature b64 decode error: {e}")\n\n    try:\n        leaf_pub.verify(leaf_sig_der, body_bytes, ECDSA(hashes.SHA256()))\n    except InvalidSignature:\n        return _fail(\n            "rekor leaf ECDSA signature does NOT verify over manifest "\n            "canonical body bytes (anchored signature is for different "\n            "bytes or has been tampered)"\n        )\n    except Exception as e:\n        return _fail(f"rekor leaf signature verification error: {e}")\n\n    print(\n        f"OK   Rekor leaf ECDSA-P-256 signature verified "\n        f"(log_index={tlog.get(\'log_index\')})"\n    )\n\n    print()\n    print(\n        "VERDICT: PASS (Ed25519 manifest + Sigstore Rekor anchor "\n        "via Path-beta dual signing)"\n    )\n    print(f"  world:        {manifest.get(\'world_name\', \'?\')}")\n    cap = manifest.get("cost_cap_usd", "?")\n    print(f"  cost_cap:     ${cap} USD")\n    margin = manifest.get("safety_margin_pct")\n    if margin:\n        try:\n            from decimal import Decimal\n            eff = Decimal(cap) * Decimal(100 - margin) / Decimal(100)\n            print(\n                f"  effective:    ${eff} USD ({margin}% safety margin)"\n            )\n        except Exception:\n            print(f"  margin:       {margin}%")\n    print(f"  verdict:      {manifest.get(\'verdict\', \'?\')}")\n    print(f"  solver:       {manifest.get(\'solver_version\', \'?\')}")\n    print(f"  timestamp:    {manifest.get(\'timestamp_utc\', \'?\')}")\n    print(f"  rekor_log_id: {tlog.get(\'log_id\')}")\n    print(f"  rekor_index:  {tlog.get(\'log_index\')}")\n    print(f"  rekor_time:   {tlog.get(\'integrated_time\')}")\n    return 0\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'

# __session82_dossier_hybrid_template_v1__


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


VERIFY_OFFLINE_PY_CHAIN: str = '#!/usr/bin/env python3\n"""Offline verification of NOUS dossier (Annex IV) with envelope-binding chain.\n\nUsage: python3 verify_offline.py\nExit:  0 = PASS, 1 = FAIL, 2 = environment error.\n\nRequires: cryptography (Ed25519 author signatures). The coverage claim, if\npresent, is checked by rational arithmetic alone (Farkas) or by z3 if a\ncoverage.smt2 is present without a Farkas certificate. The chain walk uses\ncryptography + stdlib only.\n\nThis verifier verifies an unbroken sequence of signature-valid formation\nenvelopes, each declaring its predecessor by digest, each a real build\nchange (a sha-bearing field moved), rooted at genesis -- offline,\ncryptography + stdlib, zero trust in the issuer. It does NOT prove execution\nconformance, does NOT prove the latest envelope is safer, and does NOT prove\ncoverage non-regression.\n\nChecks, in order, fail-closed:\n  1. Ed25519 signature over the current manifest\'s canonical body bytes\n     (signature and transparency_log stripped before recomputing).\n  2. source.nous sha256 == manifest.source_sha256.\n  3. If the manifest declares a coverage proof, it is checked: a Farkas\n     certificate (rational arithmetic, no solver) when present, else a z3\n     unsat re-check of coverage.smt2. Both gated by an O(1) file-sha match.\n  4. Chain walk over chain/ (prior manifests only), six fail-closed\n     conditions: per-link signature, missing chain, altered link (broken\n     hash chain), truncated/no-genesis, no-op re-binding (no sha-bearing\n     field moved), and cycle / more-than-one-genesis.\n  5. Coverage-region monotonicity (S121): per hop where both links\'\n     signed manifests declare coverage_farkas_sha256, the predecessor\'s\n     proven region must be contained in the current\'s (closed-form, no\n     solver). Coverage dropped across a re-binding is refused. This\n     proves only that the DECLARED blocking net did not shrink across\n     versions -- NOT that the system is safer, NOT real-world risk.\n  __s121_monotonicity_walk_v1__\n"""\nfrom __future__ import annotations\n\nimport base64\nimport hashlib\nimport json\nimport sys\nfrom pathlib import Path\n\nROOT = Path(__file__).parent\n\n_SHA_BEARING_FIELDS = (\n    "source_sha256",\n    "pricing_sha256",\n    "smt_spec_sha256",\n    "cost_cap_usd",\n    "max_ticks",\n)\n\n\ndef _fail(msg):\n    print("FAIL: " + msg, file=sys.stderr)\n    return 1\n\n\ndef _canonical_body_bytes(m):\n    body = {\n        k: v for k, v in m.items()\n        if k not in ("signature", "transparency_log")\n    }\n    return json.dumps(\n        body, sort_keys=True, separators=(",", ":")\n    ).encode("utf-8")\n\n\ndef _verify_link_signature(link, label):\n    from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n        Ed25519PublicKey,\n    )\n    from cryptography.exceptions import InvalidSignature\n\n    sig_block = link.get("signature")\n    if not isinstance(sig_block, dict):\n        return _fail(label + " has no signature block")\n    pub_b64 = sig_block.get("public_key_b64", "")\n    sig_b64 = sig_block.get("signature_b64", "")\n    if not pub_b64 or not sig_b64:\n        return _fail(label + " signature block incomplete")\n    body_bytes = _canonical_body_bytes(link)\n    try:\n        pub_key = Ed25519PublicKey.from_public_bytes(\n            base64.b64decode(pub_b64)\n        )\n        pub_key.verify(base64.b64decode(sig_b64), body_bytes)\n    except InvalidSignature:\n        return _fail(label + " Ed25519 signature does NOT verify")\n    except Exception as e:\n        return _fail(label + " signature verification error: " + str(e))\n    return 0\n\n\ndef _check_serialized(doc):\n    from fractions import Fraction\n\n    constraints = doc.get("constraints")\n    multipliers = doc.get("multipliers")\n    if not isinstance(constraints, list) or not isinstance(multipliers, list):\n        return False\n    if len(constraints) != len(multipliers):\n        return False\n    lam = []\n    for m in multipliers:\n        try:\n            lam.append(Fraction(m))\n        except (ValueError, TypeError, ZeroDivisionError):\n            return False\n    if any(x < 0 for x in lam):\n        return False\n    if not any(x > 0 for x in lam):\n        return False\n    combined = {}\n    strict = False\n    for x, c in zip(lam, constraints):\n        if x == 0:\n            continue\n        if not isinstance(c, dict):\n            return False\n        coeffs = c.get("coeffs")\n        if not isinstance(coeffs, dict):\n            return False\n        for k, v in coeffs.items():\n            try:\n                fv = Fraction(v)\n            except (ValueError, TypeError, ZeroDivisionError):\n                return False\n            combined[k] = combined.get(k, Fraction(0)) + x * fv\n        if c.get("strict"):\n            strict = True\n    for k, v in combined.items():\n        if k != "" and v != 0:\n            return False\n    const = combined.get("", Fraction(0))\n    if const > 0:\n        return True\n    if const == 0 and strict:\n        return True\n    return False\n\n\ndef _check_coverage(manifest):\n    farkas_expected = manifest.get("coverage_farkas_sha256")\n    smt2_expected = manifest.get("coverage_smt2_sha256")\n    cov_sha = manifest.get("policy_coverage_sha256")\n    if not cov_sha and not farkas_expected and not smt2_expected:\n        return 0\n\n    if smt2_expected:\n        smt2_path = ROOT / "coverage.smt2"\n        if not smt2_path.is_file():\n            return _fail("coverage.smt2 not found in " + str(ROOT))\n        smt2_sha = hashlib.sha256(smt2_path.read_bytes()).hexdigest()\n        if smt2_sha != smt2_expected:\n            return _fail(\n                "coverage.smt2 sha256 mismatch: file=" + smt2_sha[:16]\n                + "... manifest=" + smt2_expected[:16] + "..."\n            )\n        print(\n            "OK   coverage.smt2 sha256 matches manifest ("\n            + smt2_sha[:16] + "...)"\n        )\n\n    if farkas_expected:\n        farkas_path = ROOT / "coverage.farkas.json"\n        if not farkas_path.is_file():\n            return _fail("coverage.farkas.json not found in " + str(ROOT))\n        farkas_bytes = farkas_path.read_bytes()\n        farkas_sha = hashlib.sha256(farkas_bytes).hexdigest()\n        if farkas_sha != farkas_expected:\n            return _fail(\n                "coverage.farkas.json sha256 mismatch: file="\n                + farkas_sha[:16] + "... manifest=" + farkas_expected[:16]\n                + "... (Farkas certificate tampered or substituted)"\n            )\n        try:\n            farkas_doc = json.loads(farkas_bytes.decode("utf-8"))\n        except Exception as e:\n            return _fail("coverage.farkas.json parse error: " + str(e))\n        if not _check_serialized(farkas_doc):\n            return _fail(\n                "Farkas certificate does NOT prove unsat: the declared "\n                "multipliers do not collapse the linear system to a numeric "\n                "contradiction (coverage gap or forged certificate)"\n            )\n        print(\n            "OK   Farkas certificate verified by rational arithmetic, no "\n            "solver (contradiction: "\n            + str(farkas_doc.get("contradiction", "?")) + ")"\n        )\n        return 0\n\n    if smt2_expected:\n        try:\n            import z3\n        except ImportError:\n            print(\n                "ERROR: z3-solver required to check the coverage proof.\\n"\n                "Install: pip install z3-solver\\n"\n                "The crypto provenance gate above already PASSED; only the "\n                "semantic unsat re-check is skipped.",\n                file=sys.stderr,\n            )\n            return 2\n        solver = z3.Solver()\n        try:\n            solver.from_string(\n                (ROOT / "coverage.smt2").read_bytes().decode("utf-8")\n            )\n        except z3.Z3Exception as e:\n            return _fail("z3 parse error on coverage.smt2: " + str(e))\n        res = solver.check()\n        if str(res) != "unsat":\n            return _fail(\n                "coverage proof did NOT reproduce unsat (z3 returned "\n                + str(res) + "); treat as a coverage gap"\n            )\n        print("OK   z3 reproduced unsat: coverage proof holds (no gap)")\n    return 0\n\n\ndef _mono_vars(constraint):\n    coeffs = constraint.get("coeffs")\n    if not isinstance(coeffs, dict):\n        return None\n    return {k for k in coeffs if k != ""}\n\n\ndef _region_contains(ineq_a, ineq_b):\n    from fractions import Fraction\n\n    ca = ineq_a.get("coeffs")\n    cb = ineq_b.get("coeffs")\n    if not isinstance(ca, dict) or not isinstance(cb, dict):\n        return (False, "malformed: a constraint has no coeffs dict")\n    sa = ineq_a.get("strict")\n    sb = ineq_b.get("strict")\n    if not isinstance(sa, bool) or not isinstance(sb, bool):\n        return (False, "malformed: a constraint has no boolean strict flag")\n    var_union = sorted((set(ca) | set(cb)) - {""})\n\n    def _f(d, k):\n        try:\n            return Fraction(d.get(k, 0))\n        except (ValueError, TypeError, ZeroDivisionError):\n            return None\n\n    for v in var_union:\n        av = _f(ca, v)\n        bv = _f(cb, v)\n        if av is None or bv is None:\n            return (False, "malformed: non-rational coefficient")\n        if (av == 0) != (bv == 0):\n            return (\n                False,\n                "non-proportional: variable " + repr(v) + " is zero on one "\n                "threshold and nonzero on the other (different geometry)",\n            )\n    pivot = None\n    for v in var_union:\n        if _f(ca, v) != 0:\n            pivot = v\n            break\n    if pivot is None:\n        return (False, "malformed: threshold has no nonzero variable coeff")\n    t = _f(cb, pivot) / _f(ca, pivot)\n    if t <= 0:\n        return (\n            False,\n            "anti-parallel: proportionality factor t=" + str(t)\n            + " is not positive (half-spaces face opposite directions)",\n        )\n    for v in var_union:\n        if _f(cb, v) != t * _f(ca, v):\n            return (\n                False,\n                "non-proportional: coefficient of " + repr(v)\n                + " does not scale by t=" + str(t),\n            )\n    const_a = _f(ca, "")\n    const_b = _f(cb, "")\n    scaled_a = t * const_a\n    if const_b > scaled_a:\n        return (\n            False,\n            "insufficient-slack: const_b=" + str(const_b)\n            + " > t*const_a=" + str(scaled_a)\n            + " (region T_b does not cover region T_a)",\n        )\n    if const_b == scaled_a and (sa is False) and (sb is True):\n        return (\n            False,\n            "strictness-violation: at the shared boundary the predecessor "\n            "(<=) includes the boundary point but the current (<) excludes it",\n        )\n    return (True, "")\n\n\ndef _link_farkas_path(name):\n    # Prior links live in chain/NNN_*; the current link\'s farkas is at root.\n    if name == "manifest.json (current)":\n        return ROOT / "coverage.farkas.json"\n    return ROOT / "chain" / name.replace(\n        "_manifest.json", "_coverage.farkas.json"\n    )\n\n\ndef _authenticated_threshold(name, link):\n    # manifest-is-authority: coverage existence is decided by the signed\n    # manifest field, never by file presence.\n    field = link.get("coverage_farkas_sha256")\n    path = _link_farkas_path(name)\n    if field is None:\n        if path.is_file():\n            return ("refuse", _fail(\n                name + " declares no coverage_farkas_sha256 but a "\n                + path.name + " is present (unexpected evidence)"\n            ))\n        return ("none", None)\n    if not path.is_file():\n        return ("refuse", _fail(\n            name + " signed manifest declares coverage_farkas_sha256 but "\n            + path.name + " is missing (missing evidence / truncation)"\n        ))\n    data = path.read_bytes()\n    if hashlib.sha256(data).hexdigest() != field:\n        return ("refuse", _fail(\n            name + " " + path.name + " sha256 does not match the signed "\n            "manifest coverage_farkas_sha256 (tampered or substituted)"\n        ))\n    try:\n        doc = json.loads(data.decode("utf-8"))\n        ineq0 = doc["constraints"][0]\n    except Exception as e:\n        return ("refuse", _fail(\n            name + " " + path.name + " parse error: " + str(e)\n        ))\n    return ("has", ineq0)\n\n\ndef _walk_monotonicity(ordered):\n    # Composed after the S120 chain walk. ordered is\n    # [(name, link), ... , ("manifest.json (current)", current_manifest)].\n    checked = 0\n    for i in range(1, len(ordered)):\n        name_prev, link_prev = ordered[i - 1]\n        name_cur, link_cur = ordered[i]\n        st_prev, val_prev = _authenticated_threshold(name_prev, link_prev)\n        if st_prev == "refuse":\n            return val_prev\n        st_cur, val_cur = _authenticated_threshold(name_cur, link_cur)\n        if st_cur == "refuse":\n            return val_cur\n        if st_cur == "has" and st_prev == "has":\n            vars_prev = _mono_vars(val_prev)\n            vars_cur = _mono_vars(val_cur)\n            if vars_prev is None or vars_cur is None:\n                return _fail(\n                    "monotonicity at " + name_cur + ": malformed threshold "\n                    "constraint"\n                )\n            if vars_prev != vars_cur:\n                return _fail(\n                    "monotonicity INCOMPARABLE at " + name_cur + ": "\n                    "predecessor variables " + str(sorted(vars_prev))\n                    + " != current variables " + str(sorted(vars_cur))\n                    + " (region containment across a changed variable space "\n                    "is not assertable; refused, not passed)"\n                )\n            contained, reason = _region_contains(val_prev, val_cur)\n            if not contained:\n                return _fail(\n                    "coverage REGION REGRESSION at " + name_cur + ": "\n                    "region(predecessor) is NOT contained in region(current) "\n                    "-- " + reason + " (the declared blocking net shrank "\n                    "across this re-binding)"\n                )\n            checked += 1\n        elif st_cur == "none" and st_prev == "has":\n            return _fail(\n                "coverage VANISHED at " + name_cur + ": predecessor declares "\n                "a coverage proof but the current link drops it (dropping "\n                "coverage across a material change is refused)"\n            )\n        # (has, none) -> net grew from nothing; (none, none) -> skip.\n    if checked:\n        print(\n            "OK   coverage-region monotonicity verified across "\n            + str(checked) + " hop(s): each declared blocking net contains "\n            "its predecessor\'s (closed-form, offline, zero issuer trust)"\n        )\n    return 0\n\n\ndef _walk_chain(current_manifest):\n    prior_digest = current_manifest.get("prior_digest")\n    if prior_digest is None:\n        return _fail(\n            "this verifier expects an envelope-binding chain but the "\n            "current manifest declares no prior_digest"\n        )\n\n    chain_dir = ROOT / "chain"\n    if not chain_dir.is_dir():\n        return _fail(\n            "manifest declares prior_digest but no chain/ directory of "\n            "prior manifests is present (missing chain)"\n        )\n    link_paths = sorted(chain_dir.glob("*_manifest.json"))\n    if not link_paths:\n        return _fail(\n            "manifest declares prior_digest but chain/ contains no "\n            "*_manifest.json links (missing chain)"\n        )\n\n    links = []\n    for p in link_paths:\n        try:\n            links.append((p.name, json.loads(p.read_text(encoding="utf-8"))))\n        except Exception as e:\n            return _fail("chain link " + p.name + " parse error: " + str(e))\n\n    for name, link in links:\n        rc = _verify_link_signature(link, "chain/" + name)\n        if rc != 0:\n            return rc\n\n    genesis_count = sum(\n        1 for _, link in links if link.get("prior_digest") is None\n    )\n    if genesis_count != 1:\n        return _fail(\n            "chain has " + str(genesis_count) + " genesis links (links "\n            "without prior_digest); exactly one expected (cycle or "\n            "multiple roots)"\n        )\n    if links[0][1].get("prior_digest") is not None:\n        return _fail(\n            "chain/" + links[0][0] + " declares a prior_digest; the chain "\n            "is truncated (the oldest link shown is not genesis)"\n        )\n\n    seen_digests = set()\n    ordered = links + [("manifest.json (current)", current_manifest)]\n    for i in range(len(ordered)):\n        name_i, link_i = ordered[i]\n        digest_i = hashlib.sha256(\n            _canonical_body_bytes(link_i)\n        ).hexdigest()\n        if digest_i in seen_digests:\n            return _fail(\n                "cycle detected: " + name_i + " has a canonical digest "\n                "already seen earlier in the chain"\n            )\n        seen_digests.add(digest_i)\n\n    for i in range(1, len(ordered)):\n        name_prev, link_prev = ordered[i - 1]\n        name_cur, link_cur = ordered[i]\n        prev_digest = hashlib.sha256(\n            _canonical_body_bytes(link_prev)\n        ).hexdigest()\n        declared = link_cur.get("prior_digest")\n        if declared != prev_digest:\n            return _fail(\n                "chain broken at " + name_cur + ": declared prior_digest "\n                + str(declared)[:16] + "... does not match sha256 of "\n                + name_prev + " canonical body " + prev_digest[:16] + "..."\n            )\n        moved = [\n            f for f in _SHA_BEARING_FIELDS\n            if link_cur.get(f) != link_prev.get(f)\n        ]\n        if not moved:\n            return _fail(\n                "no-op re-binding at " + name_cur + ": no sha-bearing field "\n                "moved vs " + name_prev + " (a material change must alter at "\n                "least one of " + ", ".join(_SHA_BEARING_FIELDS) + ")"\n            )\n\n    print(\n        "OK   chain walk verified: " + str(len(links)) + " prior link(s), "\n        "rooted at genesis, each a real build change (no-trust, offline)"\n    )\n    rc_mono = _walk_monotonicity(ordered)\n    if rc_mono != 0:\n        return rc_mono\n    return 0\n\n\ndef _cost_check_serialized(doc):  # __s174_g1_cost_reproof__\n    from fractions import Fraction\n    constraints = doc.get("constraints")\n    multipliers = doc.get("multipliers")\n    if not isinstance(constraints, list) or not isinstance(\n        multipliers, list\n    ):\n        return False\n    if len(constraints) != len(multipliers):\n        return False\n    lam = []\n    for m in multipliers:\n        try:\n            lam.append(Fraction(m))\n        except (ValueError, TypeError, ZeroDivisionError):\n            return False\n    if any(x < 0 for x in lam):\n        return False\n    if not any(x > 0 for x in lam):\n        return False\n    combined = {}\n    strict = False\n    for x, c in zip(lam, constraints):\n        if x == 0:\n            continue\n        if not isinstance(c, dict):\n            return False\n        coeffs = c.get("coeffs")\n        if not isinstance(coeffs, dict):\n            return False\n        for k, v in coeffs.items():\n            try:\n                fv = Fraction(v)\n            except (ValueError, TypeError, ZeroDivisionError):\n                return False\n            combined[k] = combined.get(k, Fraction(0)) + x * fv\n        if c.get("strict"):\n            strict = True\n    for k, v in combined.items():\n        if k != "" and v != 0:\n            return False\n    const = combined.get("", Fraction(0))\n    if const > 0:\n        return True\n    if const == 0 and strict:\n        return True\n    return False\n\n\ndef main():\n    try:\n        from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n            Ed25519PublicKey,\n        )\n        from cryptography.exceptions import InvalidSignature\n    except ImportError:\n        print(\n            "ERROR: cryptography library required.\\n"\n            "Install: pip install \'cryptography>=42\'",\n            file=sys.stderr,\n        )\n        return 2\n\n    manifest_path = ROOT / "manifest.json"\n    if not manifest_path.is_file():\n        return _fail("manifest.json not found in " + str(ROOT))\n    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))\n\n    sig_block = manifest.get("signature")\n    if not sig_block:\n        return _fail("manifest has no signature block")\n    pub_b64 = sig_block.get("public_key_b64", "")\n    sig_b64 = sig_block.get("signature_b64", "")\n    if not pub_b64 or not sig_b64:\n        return _fail("manifest signature block incomplete")\n\n    body_bytes = _canonical_body_bytes(manifest)\n    try:\n        pub_key = Ed25519PublicKey.from_public_bytes(\n            base64.b64decode(pub_b64)\n        )\n        pub_key.verify(base64.b64decode(sig_b64), body_bytes)\n    except InvalidSignature:\n        return _fail("Ed25519 signature does NOT verify")\n    except Exception as e:\n        return _fail("signature verification error: " + str(e))\n    print("OK   Ed25519 signature verified")\n\n    source_path = ROOT / "source.nous"\n    if not source_path.is_file():\n        return _fail("source.nous not found in " + str(ROOT))\n    src_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()\n    expected = manifest.get("source_sha256", "")\n    if src_sha != expected:\n        return _fail(\n            "source.sha256 mismatch: file=" + src_sha[:16] + "... "\n            "manifest=" + expected[:16] + "..."\n        )\n    print("OK   source.sha256 matches manifest (" + src_sha[:16] + "...)")\n\n    cost_expected = manifest.get("cost_farkas_sha256")  # __s174_g1_cost_reproof__\n    if cost_expected:\n        cost_path = ROOT / "cost.farkas.json"\n        if not cost_path.is_file():\n            return _fail(\n                "manifest declares cost_farkas_sha256 but "\n                "cost.farkas.json is not present in the dossier "\n                "(missing cost-cap evidence)"\n            )\n        cost_bytes = cost_path.read_bytes()\n        cost_sha = hashlib.sha256(cost_bytes).hexdigest()\n        if cost_sha != cost_expected:\n            return _fail(\n                "cost.farkas.json sha256 mismatch: file=" + cost_sha[:16]\n                + "... manifest=" + cost_expected[:16]\n                + "... (cost-cap Farkas certificate tampered or "\n                "substituted)"\n            )\n        try:\n            cost_doc = json.loads(cost_bytes.decode("utf-8"))\n        except Exception as e:\n            return _fail("cost.farkas.json parse error: " + str(e))\n        if not _cost_check_serialized(cost_doc):\n            return _fail(\n                "cost-cap Farkas certificate does NOT prove the bound: "\n                "the declared multipliers do not collapse the linear "\n                "system to a numeric contradiction (cost overrun or "\n                "forged certificate)"\n            )\n        print(\n            "OK   cost-cap Farkas certificate PROVEN offline by "\n            "rational arithmetic, no solver (contradiction: "\n            + str(cost_doc.get("contradiction", "?")) + ")"\n        )\n\n    rc_cov = _check_coverage(manifest)\n    if rc_cov != 0:\n        return rc_cov\n\n    rc_chain = _walk_chain(manifest)\n    if rc_chain != 0:\n        return rc_chain\n\n    print()\n    print(\n        "VERDICT: PASS (Ed25519 manifest + envelope-binding chain, "\n        "rooted at genesis, offline, zero issuer trust)"\n    )\n    print("  world:        " + str(manifest.get("world_name", "?")))\n    print(\n        "  cost_cap:     $" + str(manifest.get("cost_cap_usd", "?")) + " USD"\n    )\n    print("  verdict:      " + str(manifest.get("verdict", "?")))\n    print(\n        "  prior_digest: "\n        + str(manifest.get("prior_digest", "?"))[:16] + "..."\n    )\n    print("  solver:       " + str(manifest.get("solver_version", "?")))\n    print("  timestamp:    " + str(manifest.get("timestamp_utc", "?")))\n    return 0\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'  # __s120_chain_verifier_v1__
def _is_bundle_farkas(farkas_bytes: bytes) -> bool:  # __s124_dossier_bundle_v1__
    """True iff the sha-gated Farkas artifact is a DNF bundle
    (fragment field); fail-closed False on any parse problem."""
    import json as _json_s124

    try:
        doc = _json_s124.loads(farkas_bytes.decode("utf-8"))
    except Exception:
        return False
    return (
        isinstance(doc, dict)
        and doc.get("fragment") == "disjunctive-linear-bundle"
    )


_MINILANG_CORE_EMBED: str = '# --- minilang core (shared text; do not edit one copy without the other) ---\n# Tokenizer + recursive-descent parser for the NOUS signal-expression\n# fragment, plus a string-aware structural scanner for policy blocks.\n# Mirrors nous.lark precedence exactly on the supported subset:\n#   or_expr < and_expr < compare_expr < add_expr < mul_expr < unary(!)\n# with left-folding at every binary level. Anything outside the subset\n# raises MinilangError (typed refuse) -- never a silent fallback.\n# __s124_minilang_core_v1__\n\n\nclass MinilangError(ValueError):\n    """Signal text outside the minilang fragment, or malformed source\n    structure; the disjunct set cannot be independently re-derived."""\n\n\n_ML_TWO_CHAR = ("&&", "||", ">=", "<=", "==", "!=")\n_ML_ONE_CHAR = "()!<>+-*/%:"\n_ML_CLAUSE_KEYWORDS = (\n    "kind", "signal", "window", "weight", "action",\n    "description", "inject_as", "message",\n)\n_ML_BLOCKING_ACTIONS = ("block", "abort_cycle")\n\n\ndef ml_tokenize(text):\n    toks = []\n    i = 0\n    n = len(text)\n    while i < n:\n        c = text[i]\n        if c in " \\t\\r\\n":\n            i += 1\n            continue\n        two = text[i:i + 2]\n        if two in _ML_TWO_CHAR:\n            toks.append(two)\n            i += 2\n            continue\n        if c in _ML_ONE_CHAR:\n            toks.append(c)\n            i += 1\n            continue\n        if c.isdigit() or (c == "." and i + 1 < n and text[i + 1].isdigit()):\n            j = i\n            seen_dot = False\n            while j < n and (\n                text[j].isdigit() or (text[j] == "." and not seen_dot)\n            ):\n                if text[j] == ".":\n                    seen_dot = True\n                j += 1\n            lit = text[i:j]\n            toks.append(("num", float(lit) if "." in lit else int(lit)))\n            i = j\n            continue\n        if c.isalpha() or c == "_":\n            j = i\n            while j < n and (text[j].isalnum() or text[j] == "_"):\n                j += 1\n            toks.append(("name", text[i:j]))\n            i = j\n            continue\n        raise MinilangError(\n            "unsupported character " + repr(c) + " in signal text"\n        )\n    return toks\n\n\nclass _MlParser:\n    def __init__(self, toks):\n        self.toks = toks\n        self.i = 0\n\n    def peek(self):\n        return self.toks[self.i] if self.i < len(self.toks) else None\n\n    def take(self):\n        t = self.peek()\n        self.i += 1\n        return t\n\n\ndef _ml_or(p):\n    node = _ml_and(p)\n    while p.peek() == "||":\n        p.take()\n        node = {"kind": "binop", "op": "||",\n                "left": node, "right": _ml_and(p)}\n    return node\n\n\ndef _ml_and(p):\n    node = _ml_cmp(p)\n    while p.peek() == "&&":\n        p.take()\n        node = {"kind": "binop", "op": "&&",\n                "left": node, "right": _ml_cmp(p)}\n    return node\n\n\ndef _ml_cmp(p):\n    node = _ml_add(p)\n    while p.peek() in (">", ">=", "<", "<=", "==", "!="):\n        op = p.take()\n        node = {"kind": "binop", "op": op,\n                "left": node, "right": _ml_add(p)}\n    return node\n\n\ndef _ml_add(p):\n    node = _ml_mul(p)\n    while p.peek() in ("+", "-"):\n        op = p.take()\n        node = {"kind": "binop", "op": op,\n                "left": node, "right": _ml_mul(p)}\n    return node\n\n\ndef _ml_mul(p):\n    node = _ml_unary(p)\n    while p.peek() in ("*", "/", "%"):\n        op = p.take()\n        node = {"kind": "binop", "op": op,\n                "left": node, "right": _ml_unary(p)}\n    return node\n\n\ndef _ml_unary(p):\n    if p.peek() == "!":\n        p.take()\n        return {"kind": "not", "operand": _ml_unary(p)}\n    return _ml_atom(p)\n\n\ndef _ml_atom(p):\n    t = p.take()\n    if t == "(":\n        node = _ml_or(p)\n        if p.take() != ")":\n            raise MinilangError("unbalanced parenthesis in signal text")\n        return node\n    if isinstance(t, tuple) and t[0] == "num":\n        return t[1]\n    if isinstance(t, tuple) and t[0] == "name":\n        if t[1] == "true":\n            return True\n        if t[1] == "false":\n            return False\n        return t[1]\n    raise MinilangError("unexpected token " + repr(t) + " in signal text")\n\n\ndef ml_parse(text):\n    """Parse a complete expression; trailing tokens are refused."""\n    p = _MlParser(ml_tokenize(text))\n    node = _ml_or(p)\n    if p.peek() is not None:\n        raise MinilangError(\n            "trailing tokens after expression: " + repr(p.peek())\n        )\n    return node\n\n\ndef _ml_parse_prefix(toks):\n    """Maximal-munch parse of a token prefix. Returns (node, stop_index).\n    The token at stop_index must be a clause keyword or absent."""\n    p = _MlParser(toks)\n    node = _ml_or(p)\n    stop = p.peek()\n    if stop is not None and not (\n        isinstance(stop, tuple)\n        and stop[0] == "name"\n        and stop[1] in _ML_CLAUSE_KEYWORDS\n    ):\n        raise MinilangError(\n            "signal expression does not end at a clause boundary: "\n            + repr(stop)\n        )\n    return node, p.i\n\n\ndef _ml_shadow(text):\n    """Comments stripped, string interiors blanked (positions preserved).\n    All structural scanning happens on the shadow so \'policy\', braces,\n    and \'#\' inside string literals can never mislead the scanner."""\n    out = []\n    i = 0\n    n = len(text)\n    in_str = False\n    while i < n:\n        c = text[i]\n        if in_str:\n            if c == "\\\\" and i + 1 < n:\n                out.append("  ")\n                i += 2\n                continue\n            if c == \'"\':\n                in_str = False\n                out.append(c)\n                i += 1\n                continue\n            out.append("\\n" if c == "\\n" else " ")\n            i += 1\n            continue\n        if c == \'"\':\n            in_str = True\n            out.append(c)\n            i += 1\n            continue\n        if c == "#":\n            while i < n and text[i] != "\\n":\n                out.append(" ")\n                i += 1\n            continue\n        out.append(c)\n        i += 1\n    return "".join(out)\n\n\ndef _ml_is_ident_char(c):\n    return c.isalnum() or c == "_"\n\n\ndef _ml_find_keyword(shadow, word, start):\n    i = start\n    n = len(shadow)\n    w = len(word)\n    while True:\n        j = shadow.find(word, i)\n        if j < 0:\n            return -1\n        before_ok = j == 0 or not _ml_is_ident_char(shadow[j - 1])\n        after_ok = j + w >= n or not _ml_is_ident_char(shadow[j + w])\n        if before_ok and after_ok:\n            return j\n        i = j + 1\n\n\ndef _ml_match_brace(shadow, open_idx):\n    depth = 0\n    for i in range(open_idx, len(shadow)):\n        if shadow[i] == "{":\n            depth += 1\n        elif shadow[i] == "}":\n            depth -= 1\n            if depth == 0:\n                return i\n    raise MinilangError("unbalanced braces in source")\n\n\ndef _ml_clause_text(block, keyword):\n    j = _ml_find_keyword(block, keyword, 0)\n    if j < 0:\n        return None\n    k = block.find(":", j)\n    if k < 0:\n        raise MinilangError(\n            "clause " + repr(keyword) + " without \':\' in policy block"\n        )\n    return block[k + 1:]\n\n\ndef ml_scan_blocking_signals(source_text):\n    """Return the parsed signal ASTs of every policy whose action is a\n    blocking action, derived purely from the source TEXT (string-aware,\n    comment-aware). Refuses (typed) on structure it cannot certify."""\n    shadow = _ml_shadow(source_text)\n    sigs = []\n    i = 0\n    while True:\n        j = _ml_find_keyword(shadow, "policy", i)\n        if j < 0:\n            break\n        k = shadow.find("{", j)\n        if k < 0:\n            raise MinilangError("policy header without \'{\'")\n        end = _ml_match_brace(shadow, k)\n        block = shadow[k + 1:end]\n        action_text = _ml_clause_text(block, "action")\n        if action_text is not None:\n            action_toks = ml_tokenize(action_text)\n            action = (\n                action_toks[0][1]\n                if action_toks\n                and isinstance(action_toks[0], tuple)\n                and action_toks[0][0] == "name"\n                else None\n            )\n            if action in _ML_BLOCKING_ACTIONS:\n                signal_text = _ml_clause_text(block, "signal")\n                if signal_text is None:\n                    raise MinilangError(\n                        "blocking policy without a signal clause"\n                    )\n                node, _stop = _ml_parse_prefix(ml_tokenize(signal_text))\n                sigs.append(node)\n        i = end + 1\n    return sigs\n# --- end minilang core ---'  # __s130_minilang_single_source_v1__


_MATERIALITY_CHECK_EMBED: str = 'def _check_materiality(manifest, ROOT):\n    import hashlib as _hashlib\n    import json as _json\n    import sys as _sys\n    field = manifest.get("materiality_sha256")\n    path = ROOT / "materiality.json"\n    if field is None:\n        if path.is_file():\n            print(\n                "FAIL: manifest declares no materiality_sha256 but a "\n                "materiality.json is present (unexpected evidence)",\n                file=_sys.stderr,\n            )\n            return 1\n        return 0\n    if not path.is_file():\n        print(\n            "FAIL: signed manifest declares materiality_sha256 but "\n            "materiality.json is missing (missing evidence / truncation)",\n            file=_sys.stderr,\n        )\n        return 1\n    data = path.read_bytes()\n    if _hashlib.sha256(data).hexdigest() != field:\n        print(\n            "FAIL: materiality.json sha256 does not match the signed "\n            "manifest materiality_sha256 (tampered or substituted)",\n            file=_sys.stderr,\n        )\n        return 1\n    try:\n        doc = _json.loads(data.decode("utf-8"))\n    except Exception as e:\n        print("FAIL: materiality.json parse error: " + str(e),\n              file=_sys.stderr)\n        return 1\n    if not isinstance(doc, dict):\n        print("FAIL: materiality.json is not a JSON object",\n              file=_sys.stderr)\n        return 1\n    verdict = doc.get("verdict")\n    if verdict not in ("minor", "material"):\n        print(\n            "FAIL: materiality.json verdict is " + repr(verdict)\n            + ", not \'minor\' or \'material\' (malformed classification)",\n            file=_sys.stderr,\n        )\n        return 1\n    if not isinstance(doc.get("reasons"), list):\n        print("FAIL: materiality.json reasons is not a list "\n              "(malformed classification)", file=_sys.stderr)\n        return 1\n    basis = doc.get("basis")\n    if not isinstance(basis, str) or "not proof" not in basis:\n        print(\n            "FAIL: materiality.json basis missing or does not disclaim "\n            "proof; refusing to present a classification as if proven",\n            file=_sys.stderr,\n        )\n        return 1\n    proof_leg_present = manifest.get("prior_digest") is not None\n    print(\n        "OK   materiality classification authenticated (sha-gated, "\n        "schema-valid): verdict=" + verdict + " -- this is a "\n        "CLASSIFICATION, not a proof"\n    )\n    if verdict == "material":\n        if proof_leg_present:\n            print(\n                "     route: MATERIAL change -- the envelope-binding "\n                "proof leg IS carried in this dossier and was verified "\n                "above (chain walk passed); the new build is bound to "\n                "its predecessor"\n            )\n        else:\n            print(\n                "     route: MATERIAL change -- NO envelope-binding "\n                "proof leg is carried in this dossier; binding requires "\n                "\'nous verify --smt --supersedes <prior>\' (Article 25 "\n                "substantial-modification record), produced separately"\n            )\n    else:\n        print(\n            "     route: MINOR revision -- an Article 12 log entry "\n            "suffices; no envelope-binding re-proof required by this "\n            "classification"\n        )\n    return 0\n'  # __s171_materiality_embed_v1__


VERIFY_OFFLINE_PY_BUNDLE: str = '#!/usr/bin/env python3\n"""Offline verification of NOUS dossier (Annex IV) via Farkas DNF bundle.\n\nUsage: python3 verify_offline.py\nExit:  0 = PASS, 1 = FAIL, 2 = environment error.\n\nRequires: cryptography (for the Ed25519 author signature only). The\ncoverage claim itself is checked by RATIONAL ARITHMETIC ALONE (fractions,\nstdlib) -- no solver, no NOUS install. z3 is used only as an optional\nsecond opinion if it happens to be installed.\n\nThis dossier\'s blocking net contains boolean structure (&& / || / !\nover linear comparisons). Coverage is proven by case-split: the gap\nsearch T && NOT(B_1) && ... && NOT(B_n) is expanded to disjunctive\nnormal form, and EVERY disjunct must be refuted by its own Farkas\ncertificate. This verifier does NOT trust the bundle\'s enumeration:\nit RE-DERIVES the disjunct set from the SIGNED source (source.nous,\nsha-gated by the signed manifest) and the sha-gated threshold\nexpression, then requires a BIJECTION -- exactly one valid certificate\nper derived disjunct. A bundle that omits the gap disjunct, carries a\nsurplus or duplicate certificate, substitutes a constraint, or forges\na multiplier FAILS. Boolean ENUMERATION from signed source, never\nboolean solving; the verifier stays solver-free.\n\nChecks, in order, fail-closed:\n  1. Ed25519 signature over canonical manifest body bytes.\n  2. source.nous sha256 == manifest.source_sha256.\n  3. coverage.smt2 sha256 == manifest.coverage_smt2_sha256 (the human-\n     inspectable obligation; O(1) crypto provenance gate).\n  4. coverage.farkas.json sha256 == manifest.coverage_farkas_sha256\n     (O(1) crypto gate BEFORE any arithmetic; authenticates the\n     threshold expression the bundle was issued for).\n  5. Independent re-derivation of the gap disjunct set from the signed\n     source + bijection + per-disjunct Farkas multiplier check. Pure\n     fractions. PROVES the coverage claim with ZERO issuer trust and\n     ZERO solver trust.\n  6. z3 unsat re-check on coverage.smt2 -- OPTIONAL second opinion,\n     skipped gracefully if z3 is absent.\n__s124_bundle_verifier_v1__\n"""\nfrom __future__ import annotations\n\nimport base64\nimport hashlib\nimport json\nimport sys\nfrom pathlib import Path\n\nROOT = Path(__file__).parent\n\n\ndef _fail(msg):\n    print("FAIL: " + msg, file=sys.stderr)\n    return 1\n\n\n' + _MINILANG_CORE_EMBED + '\n\n\n# --- farkas embed (shared text; mirrors coverage_farkas.py exactly) ---\n# Standalone copies of the linear-translation, NNF/DNF, canonical-form,\n# and multiplier-check logic from coverage_farkas.py. fractions only.\n# __s124_farkas_embed_v1__\n\nfrom fractions import Fraction\n\n\nclass FarkasError(ValueError):\n    pass\n\n\nclass LinIneq:\n    def __init__(self, coeffs, strict):\n        self.coeffs = coeffs\n        self.strict = strict\n\n\nDISJUNCT_BOUND = 64\n\n_FLIP_OP = {">": "<=", ">=": "<", "<": ">=", "<=": ">"}\n\n_CMP_OPS = (">", ">=", "<", "<=")\n\n\ndef _num(node):\n    if isinstance(node, bool):\n        return None\n    if isinstance(node, int):\n        return Fraction(node)\n    if isinstance(node, float):\n        return Fraction(node).limit_denominator(10 ** 12)\n    if isinstance(node, dict) and "currency" in node and "amount" in node:\n        return _num(node["amount"])\n    return None\n\n\ndef _linear(node):\n    n = _num(node)\n    if n is not None:\n        return {"": n}\n    if isinstance(node, str):\n        if node[:1] in (\'"\', "\'"):\n            raise FarkasError("string literal outside fragment")\n        return {node: Fraction(1), "": Fraction(0)}\n    if isinstance(node, dict) and node.get("kind") == "binop":\n        op = node.get("op")\n        if op == "+":\n            return _add(_linear(node["left"]), _linear(node["right"]), 1)\n        if op == "-":\n            return _add(_linear(node["left"]), _linear(node["right"]), -1)\n        if op == "*":\n            return _linear_mul(\n                _linear(node["left"]), _linear(node["right"])\n            )\n        raise FarkasError("non-linear operator " + repr(op) + " in term")\n    raise FarkasError(\n        "unsupported term node " + repr(type(node).__name__)\n    )\n\n\ndef _add(a, b, sign):\n    out = dict(a)\n    for k, v in b.items():\n        out[k] = out.get(k, Fraction(0)) + sign * v\n    return out\n\n\ndef _scale(a, s):\n    return {k: v * s for k, v in a.items()}\n\n\ndef _is_const_only(d):\n    return all(k == "" for k in d)\n\n\ndef _linear_mul(a, b):\n    a_const = _is_const_only(a)\n    b_const = _is_const_only(b)\n    if a_const and b_const:\n        return {"": a.get("", Fraction(0)) * b.get("", Fraction(0))}\n    if a_const:\n        return _scale(b, a.get("", Fraction(0)))\n    if b_const:\n        return _scale(a, b.get("", Fraction(0)))\n    raise FarkasError(\n        "bilinear term (variable * variable) outside linear real "\n        "arithmetic (QF_LRA); only constant * variable is admitted"\n    )\n\n\ndef _comparison_to_ineq(node):\n    if not (isinstance(node, dict) and node.get("kind") == "binop"):\n        raise FarkasError("signal is not a single comparison")\n    op = node.get("op")\n    if op not in _CMP_OPS:\n        raise FarkasError(\n            "comparison op " + repr(op) + " outside fragment"\n        )\n    left = _linear(node["left"])\n    right = _linear(node["right"])\n    diff = _add(left, right, -1)\n    if op in ("<", "<="):\n        return LinIneq(coeffs=diff, strict=(op == "<"))\n    return LinIneq(coeffs=_scale(diff, Fraction(-1)), strict=(op == ">"))\n\n\ndef _is_comparison(node):\n    return (\n        isinstance(node, dict)\n        and node.get("kind") == "binop"\n        and node.get("op") in _CMP_OPS\n    )\n\n\ndef _nnf(node, negate):\n    if _is_comparison(node):\n        if not negate:\n            return node\n        flipped = dict(node)\n        flipped["op"] = _FLIP_OP[node["op"]]\n        return flipped\n    if isinstance(node, dict) and node.get("kind") == "not":\n        return _nnf(node["operand"], not negate)\n    if (\n        isinstance(node, dict)\n        and node.get("kind") == "binop"\n        and node.get("op") in ("&&", "and", "||", "or")\n    ):\n        is_and = node.get("op") in ("&&", "and")\n        if negate:\n            is_and = not is_and\n        return {\n            "kind": "binop",\n            "op": "&&" if is_and else "||",\n            "left": _nnf(node["left"], negate),\n            "right": _nnf(node["right"], negate),\n        }\n    raise FarkasError(\n        "signal node outside the disjunctive linear fragment: "\n        + repr(node)\n    )\n\n\ndef _dnf(node, bound):\n    if _is_comparison(node):\n        return [[node]]\n    if isinstance(node, dict) and node.get("kind") == "binop":\n        op = node.get("op")\n        if op == "||":\n            out = _dnf(node["left"], bound) + _dnf(node["right"], bound)\n            if len(out) > bound:\n                raise FarkasError(\n                    "DNF disjunct count exceeds bound " + str(bound)\n                )\n            return out\n        if op == "&&":\n            left = _dnf(node["left"], bound)\n            right = _dnf(node["right"], bound)\n            if len(left) * len(right) > bound:\n                raise FarkasError(\n                    "DNF disjunct count exceeds bound " + str(bound)\n                )\n            return [a + b for a in left for b in right]\n    raise FarkasError("non-NNF node in DNF expansion: " + repr(node))\n\n\ndef _gap_disjuncts(threshold_ast, blocking_signals, bound):\n    conj = _nnf(threshold_ast, False)\n    for sig in blocking_signals:\n        conj = {\n            "kind": "binop",\n            "op": "&&",\n            "left": conj,\n            "right": _nnf(sig, True),\n        }\n    return _dnf(conj, bound)\n\n\ndef _canon_constraint(ineq):\n    return {\n        "coeffs": {k: str(v) for k, v in sorted(ineq.coeffs.items())},\n        "strict": bool(ineq.strict),\n    }\n\n\ndef _canon_json(obj):\n    import json\n\n    return json.dumps(obj, sort_keys=True, separators=(",", ":"))\n\n\ndef _canon_system(comparisons):\n    pairs = []\n    for comp in comparisons:\n        ineq = _comparison_to_ineq(comp)\n        pairs.append((_canon_constraint(ineq), ineq))\n    pairs.sort(key=lambda p: _canon_json(p[0]))\n    return [p[0] for p in pairs], [p[1] for p in pairs]\n\n\ndef _check_multipliers(constraints, multipliers):\n    if not isinstance(constraints, list) or not isinstance(\n        multipliers, list\n    ):\n        return False\n    if len(constraints) != len(multipliers):\n        return False\n    lam = []\n    for m in multipliers:\n        try:\n            lam.append(Fraction(m))\n        except (ValueError, TypeError, ZeroDivisionError):\n            return False\n    if any(x < 0 for x in lam):\n        return False\n    if not any(x > 0 for x in lam):\n        return False\n    combined = {}\n    strict = False\n    for x, c in zip(lam, constraints):\n        if x == 0:\n            continue\n        if not isinstance(c, dict):\n            return False\n        coeffs = c.get("coeffs")\n        if not isinstance(coeffs, dict):\n            return False\n        for k, v in coeffs.items():\n            try:\n                fv = Fraction(v)\n            except (ValueError, TypeError, ZeroDivisionError):\n                return False\n            combined[k] = combined.get(k, Fraction(0)) + x * fv\n        if c.get("strict"):\n            strict = True\n    for k, v in combined.items():\n        if k != "" and v != 0:\n            return False\n    const = combined.get("", Fraction(0))\n    if const > 0:\n        return True\n    if const == 0 and strict:\n        return True\n    return False\n\n\ndef derive_disjunct_constraints(source_text, threshold_expr):\n    """source TEXT + sha-gated threshold expression -> dict of\n    canonical-key -> canonical constraints, one entry per derived gap\n    disjunct (deduplicated). The independent reconstruction of what the\n    bundle must prove."""\n    threshold_ast = ml_parse(threshold_expr)\n    blocking = ml_scan_blocking_signals(source_text)\n    disjuncts = _gap_disjuncts(threshold_ast, blocking, DISJUNCT_BOUND)\n    derived = {}\n    for comps in disjuncts:\n        constraints, _system = _canon_system(comps)\n        derived[_canon_json(constraints)] = constraints\n    return derived\n\n\ndef check_bundle_against_derived(doc, derived):\n    """Bijection + per-disjunct multiplier check of a bundle dict\n    against an independently derived disjunct map. Returns (ok, reason)."""\n    if not isinstance(doc, dict):\n        return (False, "bundle is not a JSON object")\n    if doc.get("fragment") != "disjunctive-linear-bundle":\n        return (False, "bundle fragment is not disjunctive-linear-bundle")\n    cert_list = doc.get("certs")\n    if not isinstance(cert_list, list):\n        return (False, "bundle has no certs array")\n    carried = {}\n    for cert in cert_list:\n        if not isinstance(cert, dict):\n            return (False, "a cert is not a JSON object")\n        cons = cert.get("constraints")\n        mults = cert.get("multipliers")\n        if not isinstance(cons, list) or not isinstance(mults, list):\n            return (False, "a cert lacks constraints or multipliers")\n        norm = []\n        for c in cons:\n            if not isinstance(c, dict):\n                return (False, "a carried constraint is not an object")\n            coeffs = c.get("coeffs")\n            if not isinstance(coeffs, dict):\n                return (False, "a carried constraint has no coeffs")\n            try:\n                norm_coeffs = {\n                    str(k): str(Fraction(v))\n                    for k, v in sorted(coeffs.items())\n                }\n            except (ValueError, TypeError, ZeroDivisionError):\n                return (False, "non-rational carried coefficient")\n            norm.append(\n                {"coeffs": norm_coeffs, "strict": bool(c.get("strict"))}\n            )\n        norm.sort(key=_canon_json)\n        key = _canon_json(norm)\n        if key in carried:\n            return (False, "duplicate certificate for one disjunct")\n        carried[key] = mults\n    missing = set(derived) - set(carried)\n    surplus = set(carried) - set(derived)\n    if missing:\n        return (\n            False,\n            "bundle OMITS " + str(len(missing)) + " derived gap "\n            "disjunct(s) (overclaim-by-omission)",\n        )\n    if surplus:\n        return (\n            False,\n            "bundle carries " + str(len(surplus)) + " certificate(s) for "\n            "disjuncts that do not derive from the signed source",\n        )\n    for key, constraints in derived.items():\n        if not _check_multipliers(constraints, carried[key]):\n            return (\n                False,\n                "a certificate\'s multipliers do not collapse its derived "\n                "disjunct to a contradiction (coverage gap or forged "\n                "certificate)",\n            )\n    return (True, "")\n# --- end farkas embed ---\n\n\n\ndef _cost_check_serialized(doc):  # __s174_g1_cost_reproof__\n    from fractions import Fraction\n    constraints = doc.get("constraints")\n    multipliers = doc.get("multipliers")\n    if not isinstance(constraints, list) or not isinstance(\n        multipliers, list\n    ):\n        return False\n    if len(constraints) != len(multipliers):\n        return False\n    lam = []\n    for m in multipliers:\n        try:\n            lam.append(Fraction(m))\n        except (ValueError, TypeError, ZeroDivisionError):\n            return False\n    if any(x < 0 for x in lam):\n        return False\n    if not any(x > 0 for x in lam):\n        return False\n    combined = {}\n    strict = False\n    for x, c in zip(lam, constraints):\n        if x == 0:\n            continue\n        if not isinstance(c, dict):\n            return False\n        coeffs = c.get("coeffs")\n        if not isinstance(coeffs, dict):\n            return False\n        for k, v in coeffs.items():\n            try:\n                fv = Fraction(v)\n            except (ValueError, TypeError, ZeroDivisionError):\n                return False\n            combined[k] = combined.get(k, Fraction(0)) + x * fv\n        if c.get("strict"):\n            strict = True\n    for k, v in combined.items():\n        if k != "" and v != 0:\n            return False\n    const = combined.get("", Fraction(0))\n    if const > 0:\n        return True\n    if const == 0 and strict:\n        return True\n    return False\n\n\ndef main():\n    try:\n        from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n            Ed25519PublicKey,\n        )\n        from cryptography.exceptions import InvalidSignature\n    except ImportError:\n        print(\n            "ERROR: cryptography library required.\\n"\n            "Install: pip install \'cryptography>=42\'",\n            file=sys.stderr,\n        )\n        return 2\n\n    manifest_path = ROOT / "manifest.json"\n    if not manifest_path.is_file():\n        return _fail("manifest.json not found in " + str(ROOT))\n    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))\n\n    sig_block = manifest.get("signature")\n    if not sig_block:\n        return _fail("manifest has no signature block")\n    pub_b64 = sig_block.get("public_key_b64", "")\n    sig_b64 = sig_block.get("signature_b64", "")\n    if not pub_b64 or not sig_b64:\n        return _fail("manifest signature block incomplete")\n\n    body = {k: v for k, v in manifest.items() if k != "signature"}\n    body_bytes = json.dumps(\n        body, sort_keys=True, separators=(",", ":")\n    ).encode("utf-8")\n\n    try:\n        pub_key = Ed25519PublicKey.from_public_bytes(\n            base64.b64decode(pub_b64)\n        )\n        pub_key.verify(base64.b64decode(sig_b64), body_bytes)\n    except InvalidSignature:\n        return _fail("Ed25519 signature does NOT verify")\n    except Exception as e:\n        return _fail("signature verification error: " + str(e))\n    print("OK   Ed25519 signature verified")\n\n    source_path = ROOT / "source.nous"\n    if not source_path.is_file():\n        return _fail("source.nous not found in " + str(ROOT))\n    source_bytes = source_path.read_bytes()\n    src_sha = hashlib.sha256(source_bytes).hexdigest()\n    expected = manifest.get("source_sha256", "")\n    if src_sha != expected:\n        return _fail(\n            "source.sha256 mismatch: file=" + src_sha[:16] + "... "\n            "manifest=" + expected[:16] + "..."\n        )\n    print("OK   source.sha256 matches manifest (" + src_sha[:16] + "...)")\n\n    cost_expected = manifest.get("cost_farkas_sha256")  # __s174_g1_cost_reproof__\n    if cost_expected:\n        cost_path = ROOT / "cost.farkas.json"\n        if not cost_path.is_file():\n            return _fail(\n                "manifest declares cost_farkas_sha256 but "\n                "cost.farkas.json is not present in the dossier "\n                "(missing cost-cap evidence)"\n            )\n        cost_bytes = cost_path.read_bytes()\n        cost_sha = hashlib.sha256(cost_bytes).hexdigest()\n        if cost_sha != cost_expected:\n            return _fail(\n                "cost.farkas.json sha256 mismatch: file=" + cost_sha[:16]\n                + "... manifest=" + cost_expected[:16]\n                + "... (cost-cap Farkas certificate tampered or "\n                "substituted)"\n            )\n        try:\n            cost_doc = json.loads(cost_bytes.decode("utf-8"))\n        except Exception as e:\n            return _fail("cost.farkas.json parse error: " + str(e))\n        if not _cost_check_serialized(cost_doc):\n            return _fail(\n                "cost-cap Farkas certificate does NOT prove the bound: "\n                "the declared multipliers do not collapse the linear "\n                "system to a numeric contradiction (cost overrun or "\n                "forged certificate)"\n            )\n        print(\n            "OK   cost-cap Farkas certificate PROVEN offline by "\n            "rational arithmetic, no solver (contradiction: "\n            + str(cost_doc.get("contradiction", "?")) + ")"\n        )\n\n    smt2_expected = manifest.get("coverage_smt2_sha256", "")\n    if smt2_expected:\n        smt2_path = ROOT / "coverage.smt2"\n        if not smt2_path.is_file():\n            return _fail("coverage.smt2 not found in " + str(ROOT))\n        smt2_sha = hashlib.sha256(smt2_path.read_bytes()).hexdigest()\n        if smt2_sha != smt2_expected:\n            return _fail(\n                "coverage.smt2 sha256 mismatch: file=" + smt2_sha[:16]\n                + "... manifest=" + smt2_expected[:16] + "..."\n            )\n        print(\n            "OK   coverage.smt2 sha256 matches manifest ("\n            + smt2_sha[:16] + "...)"\n        )\n\n    farkas_expected = manifest.get("coverage_farkas_sha256", "")\n    if not farkas_expected:\n        return _fail(\n            "manifest has no coverage_farkas_sha256; this verifier ships "\n            "with a bundle-bearing dossier and expects the field"\n        )\n    farkas_path = ROOT / "coverage.farkas.json"\n    if not farkas_path.is_file():\n        return _fail("coverage.farkas.json not found in " + str(ROOT))\n    farkas_bytes = farkas_path.read_bytes()\n    farkas_sha = hashlib.sha256(farkas_bytes).hexdigest()\n    if farkas_sha != farkas_expected:\n        return _fail(\n            "coverage.farkas.json sha256 mismatch: file=" + farkas_sha[:16]\n            + "... manifest=" + farkas_expected[:16]\n            + "... (Farkas bundle tampered or substituted)"\n        )\n    print(\n        "OK   coverage.farkas.json sha256 matches manifest ("\n        + farkas_sha[:16] + "...)"\n    )\n\n    try:\n        farkas_doc = json.loads(farkas_bytes.decode("utf-8"))\n    except Exception as e:\n        return _fail("coverage.farkas.json parse error: " + str(e))\n    threshold_expr = farkas_doc.get("threshold_expr")\n    if not isinstance(threshold_expr, str) or not threshold_expr:\n        return _fail(\n            "bundle carries no threshold_expr; the obligation cannot be "\n            "independently re-derived"\n        )\n\n    try:\n        derived = derive_disjunct_constraints(\n            source_bytes.decode("utf-8"), threshold_expr\n        )\n    except (MinilangError, FarkasError) as e:\n        return _fail(\n            "independent re-derivation from the signed source REFUSED: "\n            + str(e) + " (the obligation cannot be certified offline; "\n            "treat as unverified)"\n        )\n    ok, reason = check_bundle_against_derived(farkas_doc, derived)\n    if not ok:\n        return _fail("Farkas bundle does NOT prove coverage: " + reason)\n    print(\n        "OK   Farkas bundle verified by rational arithmetic, no solver: "\n        + str(len(derived)) + " gap disjunct(s) independently re-derived "\n        "from the signed source, bijection holds, every disjunct refuted"\n    )\n\n    try:\n        import z3\n        smt2_path = ROOT / "coverage.smt2"\n        if smt2_path.is_file():\n            solver = z3.Solver()\n            solver.from_string(smt2_path.read_bytes().decode("utf-8"))\n            res = solver.check()\n            if str(res) != "unsat":\n                return _fail(\n                    "z3 second opinion DISAGREES: coverage.smt2 returned "\n                    + str(res) + " (expected unsat); investigate"\n                )\n            print("OK   z3 second opinion agrees: coverage.smt2 unsat")\n    except ImportError:\n        print(\n            "NOTE z3 not installed; the bundle arithmetic proof above is "\n            "sufficient (no solver needed for the coverage claim)"\n        )\n    except Exception as e:\n        print("NOTE z3 second opinion skipped: " + str(e))\n\n    print()\n    print(\n        "VERDICT: PASS (Ed25519 manifest + Farkas DNF bundle, disjuncts "\n        "re-derived from signed source, stdlib-checked, zero issuer trust)"\n    )\n    print("  world:         " + str(manifest.get("world_name", "?")))\n    print(\n        "  cost_cap:      $" + str(manifest.get("cost_cap_usd", "?"))\n        + " USD"\n    )\n    print("  verdict:       " + str(manifest.get("verdict", "?")))\n    print("  threshold:     " + str(threshold_expr))\n    print("  disjuncts:     " + str(len(derived)) + " (all refuted)")\n    print(\n        "  coverage_sha:  "\n        + str(manifest.get("policy_coverage_sha256", "?"))[:16] + "..."\n    )\n    print("  solver:        " + str(manifest.get("solver_version", "?")))\n    print("  timestamp:     " + str(manifest.get("timestamp_utc", "?")))\n    return 0\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'  # __s124_dossier_bundle_v1__

VERIFY_OFFLINE_PY_FARKAS: str = '#!/usr/bin/env python3\n"""Offline verification of NOUS dossier (Annex IV) via Farkas certificate.\n\nUsage: python3 verify_offline.py\nExit:  0 = PASS, 1 = FAIL, 2 = environment error.\n\nRequires: cryptography (for the Ed25519 author signature only). The\ncoverage claim itself is checked by RATIONAL ARITHMETIC ALONE (fractions,\nstdlib) -- no solver, no NOUS install, no external dependency. z3 is used\nonly as an optional second opinion if it happens to be installed.\n\nChecks, in order, fail-closed:\n  1. Ed25519 signature over canonical manifest body bytes.\n  2. source.nous sha256 == manifest.source_sha256.\n  3. coverage.smt2 sha256 == manifest.coverage_smt2_sha256 (the human-\n     inspectable obligation; O(1) crypto provenance gate).\n  4. coverage.farkas.json sha256 == manifest.coverage_farkas_sha256\n     (O(1) crypto gate BEFORE any arithmetic).\n  5. Farkas certificate: non-negative multipliers collapse the declared\n     linear system to a numeric contradiction. Pure fractions. This PROVES\n     the coverage claim (no gap) with ZERO solver trust.\n  6. z3 unsat re-check on coverage.smt2 -- OPTIONAL second opinion, skipped\n     gracefully if z3 is absent.\n"""\nfrom __future__ import annotations\n\nimport base64\nimport hashlib\nimport json\nimport sys\nfrom fractions import Fraction\nfrom pathlib import Path\n\nROOT = Path(__file__).parent\n\n\ndef _fail(msg):\n    print("FAIL: " + msg, file=sys.stderr)\n    return 1\n\n\ndef _check_serialized(doc):\n    constraints = doc.get("constraints")\n    multipliers = doc.get("multipliers")\n    if not isinstance(constraints, list) or not isinstance(multipliers, list):\n        return False\n    if len(constraints) != len(multipliers):\n        return False\n    lam = []\n    for m in multipliers:\n        try:\n            lam.append(Fraction(m))\n        except (ValueError, TypeError, ZeroDivisionError):\n            return False\n    if any(x < 0 for x in lam):\n        return False\n    if not any(x > 0 for x in lam):\n        return False\n    combined = {}\n    strict = False\n    for x, c in zip(lam, constraints):\n        if x == 0:\n            continue\n        if not isinstance(c, dict):\n            return False\n        coeffs = c.get("coeffs")\n        if not isinstance(coeffs, dict):\n            return False\n        for k, v in coeffs.items():\n            try:\n                fv = Fraction(v)\n            except (ValueError, TypeError, ZeroDivisionError):\n                return False\n            combined[k] = combined.get(k, Fraction(0)) + x * fv\n        if c.get("strict"):\n            strict = True\n    for k, v in combined.items():\n        if k != "" and v != 0:\n            return False\n    const = combined.get("", Fraction(0))\n    if const > 0:\n        return True\n    if const == 0 and strict:\n        return True\n    return False\n\n\ndef _cost_check_serialized(doc):  # __s174_g1_cost_reproof__\n    from fractions import Fraction\n    constraints = doc.get("constraints")\n    multipliers = doc.get("multipliers")\n    if not isinstance(constraints, list) or not isinstance(\n        multipliers, list\n    ):\n        return False\n    if len(constraints) != len(multipliers):\n        return False\n    lam = []\n    for m in multipliers:\n        try:\n            lam.append(Fraction(m))\n        except (ValueError, TypeError, ZeroDivisionError):\n            return False\n    if any(x < 0 for x in lam):\n        return False\n    if not any(x > 0 for x in lam):\n        return False\n    combined = {}\n    strict = False\n    for x, c in zip(lam, constraints):\n        if x == 0:\n            continue\n        if not isinstance(c, dict):\n            return False\n        coeffs = c.get("coeffs")\n        if not isinstance(coeffs, dict):\n            return False\n        for k, v in coeffs.items():\n            try:\n                fv = Fraction(v)\n            except (ValueError, TypeError, ZeroDivisionError):\n                return False\n            combined[k] = combined.get(k, Fraction(0)) + x * fv\n        if c.get("strict"):\n            strict = True\n    for k, v in combined.items():\n        if k != "" and v != 0:\n            return False\n    const = combined.get("", Fraction(0))\n    if const > 0:\n        return True\n    if const == 0 and strict:\n        return True\n    return False\n\n\ndef main():\n    try:\n        from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n            Ed25519PublicKey,\n        )\n        from cryptography.exceptions import InvalidSignature\n    except ImportError:\n        print(\n            "ERROR: cryptography library required.\\n"\n            "Install: pip install \'cryptography>=42\'",\n            file=sys.stderr,\n        )\n        return 2\n\n    manifest_path = ROOT / "manifest.json"\n    if not manifest_path.is_file():\n        return _fail("manifest.json not found in " + str(ROOT))\n    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))\n\n    sig_block = manifest.get("signature")\n    if not sig_block:\n        return _fail("manifest has no signature block")\n    pub_b64 = sig_block.get("public_key_b64", "")\n    sig_b64 = sig_block.get("signature_b64", "")\n    if not pub_b64 or not sig_b64:\n        return _fail("manifest signature block incomplete")\n\n    body = {k: v for k, v in manifest.items() if k != "signature"}\n    body_bytes = json.dumps(\n        body, sort_keys=True, separators=(",", ":")\n    ).encode("utf-8")\n\n    try:\n        pub_key = Ed25519PublicKey.from_public_bytes(\n            base64.b64decode(pub_b64)\n        )\n        pub_key.verify(base64.b64decode(sig_b64), body_bytes)\n    except InvalidSignature:\n        return _fail("Ed25519 signature does NOT verify")\n    except Exception as e:\n        return _fail("signature verification error: " + str(e))\n    print("OK   Ed25519 signature verified")\n\n    source_path = ROOT / "source.nous"\n    if not source_path.is_file():\n        return _fail("source.nous not found in " + str(ROOT))\n    src_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()\n    expected = manifest.get("source_sha256", "")\n    if src_sha != expected:\n        return _fail(\n            "source.sha256 mismatch: file=" + src_sha[:16] + "... "\n            "manifest=" + expected[:16] + "..."\n        )\n    print("OK   source.sha256 matches manifest (" + src_sha[:16] + "...)")\n\n    cost_expected = manifest.get("cost_farkas_sha256")  # __s174_g1_cost_reproof__\n    if cost_expected:\n        cost_path = ROOT / "cost.farkas.json"\n        if not cost_path.is_file():\n            return _fail(\n                "manifest declares cost_farkas_sha256 but "\n                "cost.farkas.json is not present in the dossier "\n                "(missing cost-cap evidence)"\n            )\n        cost_bytes = cost_path.read_bytes()\n        cost_sha = hashlib.sha256(cost_bytes).hexdigest()\n        if cost_sha != cost_expected:\n            return _fail(\n                "cost.farkas.json sha256 mismatch: file=" + cost_sha[:16]\n                + "... manifest=" + cost_expected[:16]\n                + "... (cost-cap Farkas certificate tampered or "\n                "substituted)"\n            )\n        try:\n            cost_doc = json.loads(cost_bytes.decode("utf-8"))\n        except Exception as e:\n            return _fail("cost.farkas.json parse error: " + str(e))\n        if not _cost_check_serialized(cost_doc):\n            return _fail(\n                "cost-cap Farkas certificate does NOT prove the bound: "\n                "the declared multipliers do not collapse the linear "\n                "system to a numeric contradiction (cost overrun or "\n                "forged certificate)"\n            )\n        print(\n            "OK   cost-cap Farkas certificate PROVEN offline by "\n            "rational arithmetic, no solver (contradiction: "\n            + str(cost_doc.get("contradiction", "?")) + ")"\n        )\n\n    smt2_expected = manifest.get("coverage_smt2_sha256", "")\n    if smt2_expected:\n        smt2_path = ROOT / "coverage.smt2"\n        if not smt2_path.is_file():\n            return _fail("coverage.smt2 not found in " + str(ROOT))\n        smt2_sha = hashlib.sha256(smt2_path.read_bytes()).hexdigest()\n        if smt2_sha != smt2_expected:\n            return _fail(\n                "coverage.smt2 sha256 mismatch: file=" + smt2_sha[:16]\n                + "... manifest=" + smt2_expected[:16] + "..."\n            )\n        print(\n            "OK   coverage.smt2 sha256 matches manifest ("\n            + smt2_sha[:16] + "...)"\n        )\n\n    farkas_expected = manifest.get("coverage_farkas_sha256", "")\n    if not farkas_expected:\n        return _fail(\n            "manifest has no coverage_farkas_sha256; this verifier ships "\n            "with a Farkas-bearing dossier and expects the field"\n        )\n    farkas_path = ROOT / "coverage.farkas.json"\n    if not farkas_path.is_file():\n        return _fail("coverage.farkas.json not found in " + str(ROOT))\n    farkas_bytes = farkas_path.read_bytes()\n    farkas_sha = hashlib.sha256(farkas_bytes).hexdigest()\n    if farkas_sha != farkas_expected:\n        return _fail(\n            "coverage.farkas.json sha256 mismatch: file=" + farkas_sha[:16]\n            + "... manifest=" + farkas_expected[:16]\n            + "... (Farkas certificate tampered or substituted)"\n        )\n    print(\n        "OK   coverage.farkas.json sha256 matches manifest ("\n        + farkas_sha[:16] + "...)"\n    )\n\n    try:\n        farkas_doc = json.loads(farkas_bytes.decode("utf-8"))\n    except Exception as e:\n        return _fail("coverage.farkas.json parse error: " + str(e))\n    if not _check_serialized(farkas_doc):\n        return _fail(\n            "Farkas certificate does NOT prove unsat: the declared "\n            "multipliers do not collapse the linear system to a numeric "\n            "contradiction (treat as a coverage gap or a forged certificate)"\n        )\n    print(\n        "OK   Farkas certificate verified by rational arithmetic, no solver "\n        "(contradiction: " + str(farkas_doc.get("contradiction", "?")) + ")"\n    )\n\n    try:\n        import z3\n        smt2_path = ROOT / "coverage.smt2"\n        if smt2_path.is_file():\n            solver = z3.Solver()\n            solver.from_string(smt2_path.read_bytes().decode("utf-8"))\n            res = solver.check()\n            if str(res) != "unsat":\n                return _fail(\n                    "z3 second opinion DISAGREES: coverage.smt2 returned "\n                    + str(res) + " (expected unsat); investigate"\n                )\n            print("OK   z3 second opinion agrees: coverage.smt2 unsat")\n    except ImportError:\n        print(\n            "NOTE z3 not installed; the Farkas arithmetic proof above is "\n            "sufficient (no solver needed for the coverage claim)"\n        )\n    except Exception as e:\n        print("NOTE z3 second opinion skipped: " + str(e))\n\n    print()\n    print(\n        "VERDICT: PASS (Ed25519 manifest + Farkas coverage certificate, "\n        "stdlib-checked, no solver trust)"\n    )\n    print("  world:         " + str(manifest.get("world_name", "?")))\n    print(\n        "  cost_cap:      $" + str(manifest.get("cost_cap_usd", "?")) + " USD"\n    )\n    print("  verdict:       " + str(manifest.get("verdict", "?")))\n    print(\n        "  threshold:     " + str(farkas_doc.get("threshold_expr", "?"))\n    )\n    print(\n        "  contradiction: " + str(farkas_doc.get("contradiction", "?"))\n    )\n    print(\n        "  coverage_sha:  "\n        + str(manifest.get("policy_coverage_sha256", "?"))[:16] + "..."\n    )\n    print("  solver:        " + str(manifest.get("solver_version", "?")))\n    print("  timestamp:     " + str(manifest.get("timestamp_utc", "?")))\n    return 0\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'  # __s116_dossier_farkas_v1__


VERIFY_OFFLINE_PY_COVERAGE: str = '#!/usr/bin/env python3\n"""Offline verification of NOUS dossier (Annex IV) with coverage proof.\n\nUsage: python3 verify_offline.py\nExit:  0 = PASS, 1 = FAIL, 2 = environment error (e.g. z3 missing).\nRequires: cryptography (always); z3-solver (only for the coverage step).\n\nChecks, in order, fail-closed:\n  1. Ed25519 signature over canonical manifest body bytes.\n  2. source.nous sha256 == manifest.source_sha256.\n  3. coverage.smt2 sha256 == manifest.coverage_smt2_sha256  (O(1) crypto\n     provenance gate: evidences by sha256 identity that the .smt2 is\n     exactly what was signed, BEFORE any solver runs (this blocks the\n     tampered-but-still-unsat substitution). A hash match is IDENTITY,\n     not proof.\n  4. z3 over coverage.smt2 returns unsat (the coverage claim: no input\n     crossing the declared threshold escapes a blocking policy).\n"""\nfrom __future__ import annotations\n\nimport base64\nimport hashlib\nimport json\nimport sys\nfrom pathlib import Path\n\nROOT = Path(__file__).parent\n\n\ndef _fail(msg):\n    print("FAIL: " + msg, file=sys.stderr)\n    return 1\n\n\ndef _cost_check_serialized(doc):  # __s174_g1_cost_reproof__\n    from fractions import Fraction\n    constraints = doc.get("constraints")\n    multipliers = doc.get("multipliers")\n    if not isinstance(constraints, list) or not isinstance(\n        multipliers, list\n    ):\n        return False\n    if len(constraints) != len(multipliers):\n        return False\n    lam = []\n    for m in multipliers:\n        try:\n            lam.append(Fraction(m))\n        except (ValueError, TypeError, ZeroDivisionError):\n            return False\n    if any(x < 0 for x in lam):\n        return False\n    if not any(x > 0 for x in lam):\n        return False\n    combined = {}\n    strict = False\n    for x, c in zip(lam, constraints):\n        if x == 0:\n            continue\n        if not isinstance(c, dict):\n            return False\n        coeffs = c.get("coeffs")\n        if not isinstance(coeffs, dict):\n            return False\n        for k, v in coeffs.items():\n            try:\n                fv = Fraction(v)\n            except (ValueError, TypeError, ZeroDivisionError):\n                return False\n            combined[k] = combined.get(k, Fraction(0)) + x * fv\n        if c.get("strict"):\n            strict = True\n    for k, v in combined.items():\n        if k != "" and v != 0:\n            return False\n    const = combined.get("", Fraction(0))\n    if const > 0:\n        return True\n    if const == 0 and strict:\n        return True\n    return False\n\n\ndef main():\n    try:\n        from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n            Ed25519PublicKey,\n        )\n        from cryptography.exceptions import InvalidSignature\n    except ImportError:\n        print(\n            "ERROR: cryptography library required.\\n"\n            "Install: pip install \'cryptography>=42\'",\n            file=sys.stderr,\n        )\n        return 2\n\n    manifest_path = ROOT / "manifest.json"\n    if not manifest_path.is_file():\n        return _fail("manifest.json not found in " + str(ROOT))\n    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))\n\n    sig_block = manifest.get("signature")\n    if not sig_block:\n        return _fail("manifest has no signature block")\n    pub_b64 = sig_block.get("public_key_b64", "")\n    sig_b64 = sig_block.get("signature_b64", "")\n    if not pub_b64 or not sig_b64:\n        return _fail("manifest signature block incomplete")\n\n    body = {k: v for k, v in manifest.items() if k != "signature"}\n    body_bytes = json.dumps(\n        body, sort_keys=True, separators=(",", ":")\n    ).encode("utf-8")\n\n    try:\n        pub_key = Ed25519PublicKey.from_public_bytes(\n            base64.b64decode(pub_b64)\n        )\n        pub_key.verify(base64.b64decode(sig_b64), body_bytes)\n    except InvalidSignature:\n        return _fail("Ed25519 signature does NOT verify")\n    except Exception as e:\n        return _fail("signature verification error: " + str(e))\n    print("OK   Ed25519 signature verified")\n\n    source_path = ROOT / "source.nous"\n    if not source_path.is_file():\n        return _fail("source.nous not found in " + str(ROOT))\n    src_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()\n    expected = manifest.get("source_sha256", "")\n    if src_sha != expected:\n        return _fail(\n            "source.sha256 mismatch: file=" + src_sha[:16] + "... "\n            "manifest=" + expected[:16] + "..."\n        )\n    print("OK   source.sha256 matches manifest (" + src_sha[:16] + "...)")\n\n    cost_expected = manifest.get("cost_farkas_sha256")  # __s174_g1_cost_reproof__\n    if cost_expected:\n        cost_path = ROOT / "cost.farkas.json"\n        if not cost_path.is_file():\n            return _fail(\n                "manifest declares cost_farkas_sha256 but "\n                "cost.farkas.json is not present in the dossier "\n                "(missing cost-cap evidence)"\n            )\n        cost_bytes = cost_path.read_bytes()\n        cost_sha = hashlib.sha256(cost_bytes).hexdigest()\n        if cost_sha != cost_expected:\n            return _fail(\n                "cost.farkas.json sha256 mismatch: file=" + cost_sha[:16]\n                + "... manifest=" + cost_expected[:16]\n                + "... (cost-cap Farkas certificate tampered or "\n                "substituted)"\n            )\n        try:\n            cost_doc = json.loads(cost_bytes.decode("utf-8"))\n        except Exception as e:\n            return _fail("cost.farkas.json parse error: " + str(e))\n        if not _cost_check_serialized(cost_doc):\n            return _fail(\n                "cost-cap Farkas certificate does NOT prove the bound: "\n                "the declared multipliers do not collapse the linear "\n                "system to a numeric contradiction (cost overrun or "\n                "forged certificate)"\n            )\n        print(\n            "OK   cost-cap Farkas certificate PROVEN offline by "\n            "rational arithmetic, no solver (contradiction: "\n            + str(cost_doc.get("contradiction", "?")) + ")"\n        )\n\n    cov_expected = manifest.get("coverage_smt2_sha256", "")\n    if not cov_expected:\n        return _fail(\n            "manifest has no coverage_smt2_sha256; this verifier ships "\n            "with a coverage-bearing dossier and expects the field"\n        )\n    cov_path = ROOT / "coverage.smt2"\n    if not cov_path.is_file():\n        return _fail("coverage.smt2 not found in " + str(ROOT))\n    cov_bytes = cov_path.read_bytes()\n    cov_sha = hashlib.sha256(cov_bytes).hexdigest()\n    if cov_sha != cov_expected:\n        return _fail(\n            "coverage.smt2 sha256 mismatch: file=" + cov_sha[:16] + "... "\n            "manifest=" + cov_expected[:16] + "... "\n            "(the coverage proof was tampered or substituted)"\n        )\n    print("OK   coverage.smt2 sha256 matches manifest (" + cov_sha[:16]\n          + "...)")\n\n    try:\n        import z3\n    except ImportError:\n        print(\n            "ERROR: z3-solver required to check the coverage proof.\\n"\n            "Install: pip install z3-solver\\n"\n            "The crypto provenance gate above already PASSED; only the "\n            "semantic unsat re-check is skipped.",\n            file=sys.stderr,\n        )\n        return 2\n\n    solver = z3.Solver()\n    try:\n        solver.from_string(cov_bytes.decode("utf-8"))\n    except z3.Z3Exception as e:\n        return _fail("z3 parse error on coverage.smt2: " + str(e))\n    res = solver.check()\n    if str(res) != "unsat":\n        return _fail(\n            "coverage proof did NOT reproduce unsat (z3 returned "\n            + str(res) + "); the signed claim does not hold under this "\n            "solver -- treat as a coverage gap"\n        )\n    print("OK   z3 reproduced unsat: coverage proof holds (no gap)")\n\n    print()\n    print("VERDICT: PASS (Ed25519 manifest + coverage proof)")\n    print("  world:        " + str(manifest.get("world_name", "?")))\n    print("  cost_cap:     $" + str(manifest.get("cost_cap_usd", "?"))\n          + " USD")\n    print("  verdict:      " + str(manifest.get("verdict", "?")))\n    print("  coverage_sha: "\n          + str(manifest.get("policy_coverage_sha256", "?"))[:16] + "...")\n    print("  solver:       " + str(manifest.get("solver_version", "?")))\n    print("  timestamp:    " + str(manifest.get("timestamp_utc", "?")))\n    return 0\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'  # __s115_dossier_coverage_v1__


def _splice_materiality_check(verify_src: str) -> str:
    # __s171_splice_fn_v1__ build-time splice: insert the self-contained
    # _check_materiality function and a final call into the SELECTED
    # verifier. Applied only when the dossier carries a materiality
    # classification, so verifiers without one stay byte-identical.
    # The call is the LAST check in main(): in a chain verifier,
    # reaching it means the chain walk already passed, so the
    # verified-above route is sound by control flow, not declaration.
    n_def = verify_src.count("\n\n\ndef main(")
    if n_def != 1:
        raise DossierError(
            "materiality splice: expected exactly one 'def main(' "
            "anchor in the selected verifier, found " + str(n_def)
        )
    verify_src = verify_src.replace(
        "\n\n\ndef main(",
        "\n\n\n" + _MATERIALITY_CHECK_EMBED + "\n\ndef main(",
        1,
    )
    call_anchor = "    return 0\n\n\nif __name__ == \"__main__\":"
    if verify_src.count(call_anchor) != 1:
        raise DossierError(
            "materiality splice: expected exactly one main-return "
            "anchor in the selected verifier"
        )
    call_block = (
        "    _rc_mat = _check_materiality(manifest, ROOT)\n"
        "    if _rc_mat != 0:\n"
        "        return _rc_mat\n"
        "    return 0\n\n\nif __name__ == \"__main__\":"
    )
    return verify_src.replace(call_anchor, call_block, 1)


_ATTRIBUTION_CHECK_EMBED: str = '''def _check_attribution(manifest, ROOT):
    import base64 as _b64
    import hashlib as _hashlib
    import json as _json
    import sys as _sys
    attr = manifest.get("attribution")
    if attr is None:
        return 0
    if not isinstance(attr, dict):
        print("FAIL: attribution is not a JSON object", file=_sys.stderr)
        return 1
    kind = attr.get("attribution_kind")
    actor = attr.get("actor_identity", "?")
    declared_kid = attr.get("key_id", "")
    if kind == "asserted":
        print("UNVERIFIED attribution (asserted): actor=" + str(actor)
              + " key_id=" + str(declared_kid))
        print("The operator declared this actor; no independent "
              "co-signature is present.")
        return 0
    if kind != "attested":
        print("FAIL: attribution_kind is " + repr(kind)
              + ", not 'attested' or 'asserted'", file=_sys.stderr)
        return 1
    pub_b64 = attr.get("authorizer_pubkey_b64")
    compact = attr.get("authorization_receipt")
    if not isinstance(pub_b64, str) or not pub_b64:
        print("FAIL: attested attribution has no authorizer_pubkey_b64",
              file=_sys.stderr)
        return 1
    if not isinstance(compact, str) or not compact:
        print("FAIL: attested attribution has no authorization_receipt",
              file=_sys.stderr)
        return 1
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
        from cryptography.exceptions import InvalidSignature
    except ImportError:
        print("ERROR: cryptography library required for attribution check.",
              file=_sys.stderr)
        return 2
    try:
        pub_raw = _b64.b64decode(pub_b64, validate=True)
    except Exception as e:
        print("FAIL: authorizer_pubkey_b64 does not decode: " + str(e),
              file=_sys.stderr)
        return 1
    recomputed_kid = "sha256:" + _hashlib.sha256(pub_raw).hexdigest()
    if recomputed_kid != declared_kid:
        print("FAIL: authorizer key_id mismatch: recomputed "
              + recomputed_kid[:23] + "... != declared "
              + str(declared_kid)[:23] + "... (the declared key_id does "
              "not name the embedded key)", file=_sys.stderr)
        return 1
    parts = compact.split(".")
    if len(parts) != 3:
        print("FAIL: authorization_receipt is not a compact JWS "
              "(protected.payload.signature)", file=_sys.stderr)
        return 1
    protected_b64, payload_b64, signature_b64 = parts

    def _b64url_decode(segment):
        pad = "=" * (-len(segment) % 4)
        return _b64.urlsafe_b64decode(segment + pad)

    try:
        protected = _json.loads(_b64url_decode(protected_b64))
        payload = _json.loads(_b64url_decode(payload_b64))
        sig_raw = _b64url_decode(signature_b64)
    except Exception as e:
        print("FAIL: authorization_receipt JWS does not decode: " + str(e),
              file=_sys.stderr)
        return 1
    if protected.get("alg") != "EdDSA":
        print("FAIL: authorization receipt alg is not EdDSA",
              file=_sys.stderr)
        return 1
    if protected.get("typ") != "application/nous-authorization-receipt+jwt":
        print("FAIL: authorization receipt typ is not the authorization "
              "media type", file=_sys.stderr)
        return 1
    body = {k: v for k, v in manifest.items()
            if k not in ("signature", "transparency_log", "attribution")}
    expected_run_digest = _hashlib.sha256(
        _json.dumps(body, sort_keys=True, separators=(",", ":")).encode(
            "utf-8")).hexdigest()
    signing_input = (protected_b64 + "." + payload_b64).encode("ascii")
    try:
        pub = Ed25519PublicKey.from_public_bytes(pub_raw)
        pub.verify(sig_raw, signing_input)
    except InvalidSignature:
        print("FAIL: authorization receipt signature does NOT verify under "
              "the embedded authorizer key (co-signature forged or "
              "tampered)", file=_sys.stderr)
        return 1
    except Exception as e:
        print("FAIL: authorization receipt verification error: " + str(e),
              file=_sys.stderr)
        return 1
    if payload.get("run_digest") != expected_run_digest:
        print("FAIL: authorization receipt run_digest does not match this "
              "manifest's run identity (receipt replayed from another run)",
              file=_sys.stderr)
        return 1
    if payload.get("key_id") != declared_kid:
        print("FAIL: authorization receipt payload key_id does not match "
              "the declared attribution key_id", file=_sys.stderr)
        return 1
    print("OK   authorizer co-signature verified: actor=" + str(actor)
          + " key_id=" + recomputed_kid)
    print("Cryptographic Attribution Disclosure: an authorizer "
          "co-signature is present and was verified against an Ed25519 "
          "public key embedded in this manifest and covered by the "
          "operator signature, so the key cannot have been swapped after "
          "signing. To confirm that this key belongs to the named "
          "authorizer, compare the printed key_id against your own "
          "out-of-band record -- that identity check is YOUR step, not "
          "this verifier's. NOUS does not certify the key-to-identity "
          "binding; the name is operator-asserted. This evidences "
          "co-signing, not proof of identity, intent, or accountability.")
    return 0
'''


_PCE_CHECK_EMBED: str = 'def _pce_parse_canon(canon):\n    _sa = set()\n    _ga = set()\n    _gq = {}\n    for ln in canon.split("\\n"):\n        if ln.startswith("SA:"):\n            _sa.add(ln[3:])\n        elif ln.startswith("GA:"):\n            _ga.add(ln[3:])\n        elif ln.startswith("GQ:"):\n            parts = ln[3:].rsplit(":", 1)\n            if len(parts) == 2:\n                _gq[parts[0]] = parts[1]\n    return _sa, _ga, _gq\n\n\ndef _pce_diff_obligations(prior_canon, current_canon):\n    psa, pga, pgq = _pce_parse_canon(prior_canon)\n    csa, cga, cgq = _pce_parse_canon(current_canon)\n    weak = []\n    strong = []\n    for x in sorted(psa - csa):\n        weak.append("SA removed: " + x)\n    for x in sorted(csa - psa):\n        strong.append("SA added: " + x)\n    for x in sorted(pga - cga):\n        weak.append("GA removed: " + x)\n    for x in sorted(cga - pga):\n        strong.append("GA added: " + x)\n    for a in sorted(set(pgq) - set(cgq)):\n        weak.append("GQ removed: " + a)\n    for a in sorted(set(cgq) - set(pgq)):\n        strong.append("GQ added: " + a + ":" + cgq[a])\n    for a in sorted(set(pgq) & set(cgq)):\n        if pgq[a] != cgq[a]:\n            try:\n                dlt = int(cgq[a]) - int(pgq[a])\n            except ValueError:\n                dlt = 0\n            msg = "GQ " + a + " quorum " + pgq[a] + "->" + cgq[a]\n            if dlt < 0:\n                weak.append(msg)\n            else:\n                strong.append(msg)\n    return {"weakened": weak, "strengthened": strong}\n\n\ndef _pce_gq_action_of(transition):\n    if transition.startswith("GQ removed: "):\n        return transition[len("GQ removed: "):]\n    if transition.startswith("GQ added: "):\n        return transition[len("GQ added: "):].rsplit(":", 1)[0]\n    if transition.startswith("GQ ") and " quorum " in transition:\n        return transition[len("GQ "):transition.index(" quorum ")]\n    return None\n\n\ndef _pce_gq_quorum_pair(transition):\n    if " quorum " not in transition or "->" not in transition:\n        return None\n    try:\n        tail = transition.split(" quorum ", 1)[1]\n        prev_s, cur_s = tail.split("->", 1)\n        return int(prev_s), int(cur_s)\n    except ValueError:\n        return None\n\n\nclass _PCEError(ValueError):\n    pass\n\n\ndef _pce_extract_cumulative(pce_doc):\n    # Validate the PCE document enough to fail closed, and extract the\n    # cumulative rules byte-faithfully to envelope.parse_envelope. Raises\n    # _PCEError on any malformation. Returns a dict of cumulative rules,\n    # or None if the PCE carries no cumulative dimension.\n    if not isinstance(pce_doc, dict):\n        raise _PCEError("pce.json is not a JSON object")\n    if pce_doc.get("pce_schema_version") != 1:\n        raise _PCEError(\n            "unsupported pce_schema_version "\n            + repr(pce_doc.get("pce_schema_version")) + "; expected 1"\n        )\n    basis = pce_doc.get("basis")\n    if not isinstance(basis, str) or (\n        "not a legal substantiality determination" not in basis\n    ):\n        raise _PCEError(\n            "pce.json basis missing or does not disclaim substantiality "\n            "(must contain \'not a legal substantiality determination\'); "\n            "refusing to present membership as a legal determination"\n        )\n    base_sha = pce_doc.get("baseline_canon_sha256")\n    if not isinstance(base_sha, str) or len(base_sha) != 64 or any(\n        c not in "0123456789abcdef" for c in base_sha\n    ):\n        raise _PCEError("pce.json baseline_canon_sha256 is not a 64-hex sha256")\n    ps = pce_doc.get("per_step")\n    if not isinstance(ps, dict):\n        raise _PCEError("pce.json per_step is missing or not an object")\n    ps_sa = ps.get("SA")\n    if not isinstance(ps_sa, dict) or not isinstance(ps_sa.get("mutable"), bool):\n        raise _PCEError("pce.json per_step.SA.mutable must be a bool")\n    per_step_sa_mutable = ps_sa.get("mutable")\n    cum = pce_doc.get("cumulative")\n    if cum is None:\n        return None\n    if not isinstance(cum, dict):\n        raise _PCEError("pce.json cumulative must be an object or absent")\n    c_sa = cum.get("SA", {})\n    c_ga = cum.get("GA", {})\n    c_gq = cum.get("GQ", {})\n    if not isinstance(c_sa, dict) or not isinstance(c_ga, dict) or not isinstance(c_gq, dict):\n        raise _PCEError("pce.json cumulative.SA/GA/GQ must each be objects")\n    sa_mutable = bool(c_sa.get("mutable", per_step_sa_mutable))\n    c_rm = c_ga.get("total_removable")\n    c_ad = c_ga.get("total_addable")\n    if c_rm is not None and (\n        not isinstance(c_rm, list) or any(not isinstance(x, str) for x in c_rm)\n    ):\n        raise _PCEError("cumulative.GA.total_removable must be list of strings or null")\n    if c_ad is not None and (\n        not isinstance(c_ad, list) or any(not isinstance(x, str) for x in c_ad)\n    ):\n        raise _PCEError("cumulative.GA.total_addable must be list of strings or null")\n    budget_raw = c_gq.get("quorum_drift_budget", {})\n    if not isinstance(budget_raw, dict):\n        raise _PCEError("cumulative.GQ.quorum_drift_budget must be an object")\n    budget = {}\n    for a, v in budget_raw.items():\n        if not isinstance(a, str) or not isinstance(v, int) or isinstance(v, bool) or v < 0:\n            raise _PCEError(\n                "cumulative.GQ.quorum_drift_budget values must be non-negative ints"\n            )\n        budget[a] = v\n    return {\n        "sa_mutable": sa_mutable,\n        "ga_total_removable": (frozenset(c_rm) if c_rm is not None else None),\n        "ga_total_addable": (frozenset(c_ad) if c_ad is not None else None),\n        "gq_quorum_drift_budget": budget,\n    }\n\n\ndef _pce_decide(pce_doc, baseline_canon, current_canon):\n    # Pure cumulative membership decision. Returns\n    # (verdict, breakouts, weakened, strengthened) where verdict is\n    # "WITHIN" | "OUTSIDE" | "NO_CUMULATIVE". Faithful port of\n    # envelope.decide_cumulative (parity asserted by the committed test\n    # against the installed envelope module).\n    cum = _pce_extract_cumulative(pce_doc)\n    delta = _pce_diff_obligations(baseline_canon, current_canon)\n    weak = list(delta["weakened"])\n    strong = list(delta["strengthened"])\n    if cum is None:\n        return ("NO_CUMULATIVE", [], weak, strong)\n    breakouts = []\n    for t in weak + strong:\n        if t.startswith("SA removed: ") or t.startswith("SA added: "):\n            if not cum["sa_mutable"]:\n                breakouts.append(t + " (SA cumulatively immutable)")\n    for t in weak:\n        if t.startswith("GA removed: "):\n            action = t[len("GA removed: "):]\n            if cum["ga_total_removable"] is None or action not in cum["ga_total_removable"]:\n                breakouts.append(t + " (GA removal not in cumulative removable set)")\n    for t in strong:\n        if t.startswith("GA added: "):\n            action = t[len("GA added: "):]\n            if cum["ga_total_addable"] is not None and action not in cum["ga_total_addable"]:\n                breakouts.append(t + " (GA addition not in cumulative addable set)")\n    for t in weak:\n        if t.startswith("GQ removed: "):\n            breakouts.append(t + " (cumulative GQ removal drops an oversight gate)")\n    for t in weak + strong:\n        if t.startswith("GQ ") and " quorum " in t:\n            action = _pce_gq_action_of(t)\n            pair = _pce_gq_quorum_pair(t)\n            if action is None or pair is None:\n                breakouts.append(t + " (uninterpretable cumulative quorum drift)")\n                continue\n            prev_q, cur_q = pair\n            drift = abs(cur_q - prev_q)\n            budget = cum["gq_quorum_drift_budget"].get(action)\n            if budget is None:\n                breakouts.append(\n                    t + " (cumulative drift " + str(drift)\n                    + "; no drift budget declared for " + action + ")"\n                )\n            elif drift > budget:\n                breakouts.append(\n                    t + " (cumulative drift " + str(drift) + " > budget "\n                    + str(budget) + ")"\n                )\n    verdict = "WITHIN" if len(breakouts) == 0 else "OUTSIDE"\n    return (verdict, breakouts, weak, strong)\n\n\ndef _check_pce(manifest, ROOT):\n    # __s190_pce_embed_v1__ Predetermined-Change Envelope (Art 43(4) /\n    # Annex IV 2(f)) cumulative-membership evidence. MONITOR, NOT GATE:\n    # returns 0 on WITHIN and on OUTSIDE; non-zero ONLY on integrity\n    # failure (sha mismatch, missing-but-declared sidecar, unparseable\n    # PCE). The verdict never fails the process; only tamper does.\n    import hashlib as _hashlib\n    import json as _json\n    import sys as _sys\n\n    field = manifest.get("pce_sha256")\n    pce_path = ROOT / "pce.json"\n    if field is None:\n        if pce_path.is_file():\n            print(\n                "FAIL: manifest declares no pce_sha256 but a pce.json is "\n                "present (unexpected evidence)",\n                file=_sys.stderr,\n            )\n            return 1\n        return 0\n    if not pce_path.is_file():\n        print(\n            "FAIL: signed manifest declares pce_sha256 but pce.json is "\n            "missing (missing evidence / truncation)",\n            file=_sys.stderr,\n        )\n        return 1\n    pce_bytes = pce_path.read_bytes()\n    if _hashlib.sha256(pce_bytes).hexdigest() != field:\n        print(\n            "FAIL: pce.json sha256 does not match the signed manifest "\n            "pce_sha256 (predetermined-change envelope tampered or "\n            "substituted)",\n            file=_sys.stderr,\n        )\n        return 1\n    try:\n        pce_doc = _json.loads(pce_bytes.decode("utf-8"))\n    except Exception as e:\n        print("FAIL: pce.json parse error: " + str(e), file=_sys.stderr)\n        return 1\n\n    # Current obligations canon: the full SMT-spec canonical preimage,\n    # authenticated by the EXISTING signed smt_spec_sha256 (no new field).\n    smt_field = manifest.get("smt_spec_sha256")\n    spec_canon_path = ROOT / "spec.canon"\n    if not isinstance(smt_field, str) or not smt_field:\n        print(\n            "FAIL: manifest has no smt_spec_sha256; the current obligations "\n            "canon cannot be authenticated",\n            file=_sys.stderr,\n        )\n        return 1\n    if not spec_canon_path.is_file():\n        print(\n            "FAIL: pce evidence present but spec.canon (the current "\n            "obligations canon) is missing (missing evidence / truncation)",\n            file=_sys.stderr,\n        )\n        return 1\n    spec_canon_bytes = spec_canon_path.read_bytes()\n    if _hashlib.sha256(spec_canon_bytes).hexdigest() != smt_field:\n        print(\n            "FAIL: spec.canon sha256 does not match the signed manifest "\n            "smt_spec_sha256 (current obligations canon tampered or "\n            "substituted)",\n            file=_sys.stderr,\n        )\n        return 1\n    current_canon = spec_canon_bytes.decode("utf-8")\n\n    # Baseline obligations canon: sha-gated transitively by the PCE\'s\n    # baseline_canon_sha256 (no manifest field; the PCE is itself sha-gated\n    # by the signed manifest above).\n    base_sha = pce_doc.get("baseline_canon_sha256")\n    if not isinstance(base_sha, str) or len(base_sha) != 64:\n        print(\n            "FAIL: pce.json baseline_canon_sha256 missing or not a 64-hex "\n            "sha256",\n            file=_sys.stderr,\n        )\n        return 1\n    baseline_path = ROOT / "baseline.canon"\n    if not baseline_path.is_file():\n        print(\n            "FAIL: pce.json commits to a baseline obligations canon but "\n            "baseline.canon is missing (missing evidence / truncation)",\n            file=_sys.stderr,\n        )\n        return 1\n    baseline_bytes = baseline_path.read_bytes()\n    if _hashlib.sha256(baseline_bytes).hexdigest() != base_sha:\n        print(\n            "FAIL: baseline.canon sha256 does not match the PCE\'s "\n            "baseline_canon_sha256 (committed baseline canon tampered or "\n            "substituted)",\n            file=_sys.stderr,\n        )\n        return 1\n    baseline_canon = baseline_bytes.decode("utf-8")\n\n    try:\n        verdict, breakouts, weak, strong = _pce_decide(\n            pce_doc, baseline_canon, current_canon\n        )\n    except _PCEError as e:\n        print(\n            "FAIL: predetermined-change envelope malformed: " + str(e),\n            file=_sys.stderr,\n        )\n        return 1\n\n    verdict_obj = {\n        "kind": "pce-cumulative-membership-v1",\n        "verdict": verdict,\n        "breakouts": list(breakouts),\n        "composed_weakened": list(weak),\n        "composed_strengthened": list(strong),\n        "scope": "sa-ga-gq-obligation-subset-of-signed-smt-spec-canon",\n        "temporal_precedence": "membership-only-no-temporal-claim",\n        "basis_disclaimed": True,\n    }\n    print(\n        "OK   predetermined-change envelope authenticated (pce.json + "\n        "baseline.canon + spec.canon sha-gated by the signed manifest)"\n    )\n    print(\n        "     SCOPE: membership decided over the SA/GA/GQ governance-"\n        "obligation subset of the signed SMT-spec canon. The sha-gate "\n        "authenticates the WHOLE spec preimage; the decision reads only "\n        "the obligation subset (it does NOT claim the spec equals the "\n        "obligation set)."\n    )\n    print(\n        "     TEMPORAL: membership-only. This leg makes NO ordering claim and does not read "\n        "the envelope\'s transparency-log / RFC 3161 pre-commitment anchor; "\n        "membership asserts the DECLARED envelope admits this composed "\n        "delta, NOT that the envelope was committed before the change."\n    )\n    if verdict == "NO_CUMULATIVE":\n        print(\n            "NOTE the carried PCE declares per_step only; the cumulative "\n            "(salami) membership determination is not available from this "\n            "dossier. No membership violation is asserted, and none is "\n            "claimed (monitor)."\n        )\n        print(\n            "PCE_VERDICT_JSON: "\n            + _json.dumps(verdict_obj, sort_keys=True, separators=(",", ":"))\n        )\n        return 0\n    if verdict == "WITHIN":\n        print(\n            "OK   PCE verdict: WITHIN. The composed baseline->current "\n            "obligation delta lies inside the cumulative envelope. Under "\n            "Article 43(4) the provider\'s own deduction is: a predetermined "\n            "change, NOT a substantial modification. NOUS surfaces this; "\n            "the notified body adjudicates."\n        )\n    else:\n        print(\n            "INFO PCE verdict: OUTSIDE. The composed delta exits the "\n            "cumulative envelope on the transition(s) below. This is a "\n            "TRUTHFUL detected event, not a process failure (monitor). It "\n            "is potentially a substantial modification; the notified body "\n            "adjudicates. NOUS decides nothing."\n        )\n        for b in breakouts:\n            print("       breakout: " + b)\n    print(\n        "PCE_VERDICT_JSON: "\n        + _json.dumps(verdict_obj, sort_keys=True, separators=(",", ":"))\n    )\n    return 0\n'  # __s190_pce_embed_assign_v1__


_PCE_ANCHOR_CHECK_EMBED: str = '_PA_OID_SIGNED_DATA = "1.2.840.113549.1.7.2"\n_PA_OID_CT_TSTINFO = "1.2.840.113549.1.9.16.1.4"\n_PA_OID_ATTR_CONTENT_TYPE = "1.2.840.113549.1.9.3"\n_PA_OID_ATTR_MESSAGE_DIGEST = "1.2.840.113549.1.9.4"\n\n_PA_KNOWN_TSA_ROOT_CERTS = [\n    "-----BEGIN CERTIFICATE-----\\n"\n    "MIIB9zCCAXygAwIBAgIUV7f0GLDOoEzIh8LXSW80OJiUp14wCgYIKoZIzj0EAwMw\\n"\n    "OTEVMBMGA1UEChMMc2lnc3RvcmUuZGV2MSAwHgYDVQQDExdzaWdzdG9yZS10c2Et\\n"\n    "c2VsZnNpZ25lZDAeFw0yNTA0MDgwNjU5NDNaFw0zNTA0MDYwNjU5NDNaMDkxFTAT\\n"\n    "BgNVBAoTDHNpZ3N0b3JlLmRldjEgMB4GA1UEAxMXc2lnc3RvcmUtdHNhLXNlbGZz\\n"\n    "aWduZWQwdjAQBgcqhkjOPQIBBgUrgQQAIgNiAAQUQNtfRT/ou3YATa6wB/kKTe70\\n"\n    "cfJwyRIBovMnt8RcJph/COE82uyS6FmppLLL1VBPGcPfpQPYJNXzWwi8icwhKQ6W\\n"\n    "/Qe2h3oebBb2FHpwNJDqo+TMaC/tdfkv/ElJB72jRTBDMA4GA1UdDwEB/wQEAwIB\\n"\n    "BjASBgNVHRMBAf8ECDAGAQH/AgEAMB0GA1UdDgQWBBSY7AHvf7tR/9SVHm+KiJhT\\n"\n    "B4nOvzAKBggqhkjOPQQDAwNpADBmAjEAwGEGrfGZR1cen1R8/DTVMI943LssZmJR\\n"\n    "tDp/i7SfGHmGRP6gRbuj9vOK3b67Z0QQAjEAuT2H673LQEaHTcyQSZrkp4mX7Wwk\\n"\n    "mF+sVbkYY5mXN+RMH13KUEHHOqASaemYWK/E\\n"\n    "-----END CERTIFICATE-----\\n",\n]\n\n\nclass _PaMalformed(ValueError):\n    pass\n\n\ndef _pa_der_len(buf, off):\n    b = buf[off]\n    if b < 0x80:\n        return b, off + 1\n    n = b & 0x7F\n    if n == 0 or n > 4:\n        raise _PaMalformed("unsupported DER length form")\n    return int.from_bytes(buf[off + 1:off + 1 + n], "big"), off + 1 + n\n\n\ndef _pa_tlv(buf, off):\n    length, hdr_end = _pa_der_len(buf, off + 1)\n    end = hdr_end + length\n    if end > len(buf):\n        raise _PaMalformed("DER length exceeds buffer")\n    return buf[off], off, hdr_end, end\n\n\ndef _pa_children(buf, start, end):\n    out = []\n    off = start\n    while off < end:\n        tag, tlv_start, c_off, c_end = _pa_tlv(buf, off)\n        out.append((tag, tlv_start, c_off, c_end))\n        off = c_end\n    return out\n\n\ndef _pa_oid_str(buf, c_off, c_end):\n    data = buf[c_off:c_end]\n    if not data:\n        raise _PaMalformed("empty OID")\n    first = data[0]\n    parts = [str(first // 40), str(first % 40)]\n    val = 0\n    for byte in data[1:]:\n        val = (val << 7) | (byte & 0x7F)\n        if not byte & 0x80:\n            parts.append(str(val))\n            val = 0\n    return ".".join(parts)\n\n\ndef _pa_parse_token(token_der):\n    try:\n        _, _, ci_c, ci_end = _pa_tlv(token_der, 0)\n        ci_kids = _pa_children(token_der, ci_c, ci_end)\n        if _pa_oid_str(token_der, ci_kids[0][2], ci_kids[0][3]) != \\\n                _PA_OID_SIGNED_DATA:\n            raise _PaMalformed("token is not a CMS SignedData")\n        sd = _pa_children(token_der, ci_kids[1][2], ci_kids[1][3])[0]\n        sd_kids = _pa_children(token_der, sd[2], sd[3])\n        enc = next(k for k in sd_kids if k[0] == 0x30)\n        enc_kids = _pa_children(token_der, enc[2], enc[3])\n        if _pa_oid_str(token_der, enc_kids[0][2], enc_kids[0][3]) != \\\n                _PA_OID_CT_TSTINFO:\n            raise _PaMalformed("eContentType is not id-ct-TSTInfo")\n        oct0 = _pa_children(token_der, enc_kids[1][2], enc_kids[1][3])[0]\n        tstinfo = token_der[oct0[2]:oct0[3]]\n        certs = []\n        for k in sd_kids:\n            if k[0] == 0xA0:\n                for c in _pa_children(token_der, k[2], k[3]):\n                    certs.append(token_der[c[1]:c[3]])\n                break\n        signer_set = [k for k in sd_kids if k[0] == 0x31 and k[1] > enc[3]][0]\n        si = _pa_children(token_der, signer_set[2], signer_set[3])[0]\n        si_kids = _pa_children(token_der, si[2], si[3])\n        i = 2\n        digest_alg = _pa_children(token_der, si_kids[i][2], si_kids[i][3])\n        digest_oid = _pa_oid_str(token_der, digest_alg[0][2], digest_alg[0][3])\n        i += 1\n        signed_attrs_der = None\n        signed_attrs_span = None\n        if si_kids[i][0] == 0xA0:\n            sa = si_kids[i]\n            signed_attrs_der = b"\\x31" + token_der[sa[1] + 1:sa[3]]\n            signed_attrs_span = (sa[2], sa[3])\n            i += 1\n        sig_alg = _pa_children(token_der, si_kids[i][2], si_kids[i][3])\n        sig_alg_oid = _pa_oid_str(token_der, sig_alg[0][2], sig_alg[0][3])\n        i += 1\n        signature = token_der[si_kids[i][2]:si_kids[i][3]]\n        attrs = {}\n        if signed_attrs_span is not None:\n            for a in _pa_children(token_der, *signed_attrs_span):\n                ak = _pa_children(token_der, a[2], a[3])\n                a_oid = _pa_oid_str(token_der, ak[0][2], ak[0][3])\n                vset = _pa_children(token_der, ak[1][2], ak[1][3])[0]\n                attrs[a_oid] = (vset[2], vset[3])\n    except _PaMalformed:\n        raise\n    except (IndexError, StopIteration, ValueError) as exc:\n        raise _PaMalformed("malformed TimeStampToken: " + repr(exc)) from exc\n    if signed_attrs_der is None:\n        raise _PaMalformed("TimeStampToken has no signed attributes")\n    return {\n        "tstinfo": tstinfo, "certs": certs, "digest_oid": digest_oid,\n        "signed_attrs_der": signed_attrs_der, "sig_alg_oid": sig_alg_oid,\n        "signature": signature, "attrs": attrs, "buf": token_der,\n    }\n\n\ndef _pa_parse_tstinfo(tstinfo):\n    import datetime as _dt\n    try:\n        _, _, c, e = _pa_tlv(tstinfo, 0)\n        kids = _pa_children(tstinfo, c, e)\n        mi = next(k for k in kids if k[0] == 0x30)\n        mi_kids = _pa_children(tstinfo, mi[2], mi[3])\n        alg_kids = _pa_children(tstinfo, mi_kids[0][2], mi_kids[0][3])\n        imprint_alg_oid = _pa_oid_str(tstinfo, alg_kids[0][2], alg_kids[0][3])\n        hashed = tstinfo[mi_kids[1][2]:mi_kids[1][3]]\n        gt = next(k for k in kids if k[0] == 0x18)\n        gen = tstinfo[gt[2]:gt[3]].decode("ascii")\n    except (IndexError, StopIteration, ValueError, UnicodeDecodeError) as exc:\n        raise _PaMalformed("malformed TSTInfo: " + repr(exc)) from exc\n    dt = _dt.datetime.strptime(gen.rstrip("Z"), "%Y%m%d%H%M%S").replace(\n        tzinfo=_dt.timezone.utc\n    )\n    return hashed, imprint_alg_oid, dt\n\n\ndef _pa_verify_rfc3161(token_der, timestamped_data):\n    # Faithful port of tsa_verify.verify_rfc3161_timestamp, returning\n    # (ok, gen_time, errors). Pinned-root chain, signer sig over the\n    # re-encoded SignedAttributes, content-type, message-digest, and the\n    # imprint binding to timestamped_data. cryptography + stdlib only.\n    import hashlib as _hl\n    from cryptography import x509\n    from cryptography.hazmat.primitives import hashes as _h\n    from cryptography.hazmat.primitives.asymmetric import ec as _ec\n    from cryptography.hazmat.primitives.asymmetric import padding as _pad\n    from cryptography.hazmat.primitives.asymmetric.ec import ECDSA as _ECDSA\n    from cryptography.x509.oid import ExtendedKeyUsageOID as _EKU\n\n    ecdsa_oids = {\n        "1.2.840.10045.4.3.2": _h.SHA256,\n        "1.2.840.10045.4.3.3": _h.SHA384,\n        "1.2.840.10045.4.3.4": _h.SHA512,\n    }\n    rsa_oids = {\n        "1.2.840.113549.1.1.11": _h.SHA256,\n        "1.2.840.113549.1.1.12": _h.SHA384,\n        "1.2.840.113549.1.1.13": _h.SHA512,\n    }\n    digest_oids = {\n        "2.16.840.1.101.3.4.2.1": "sha256",\n        "2.16.840.1.101.3.4.2.2": "sha384",\n        "2.16.840.1.101.3.4.2.3": "sha512",\n    }\n    parsed = _pa_parse_token(token_der)\n    errors = []\n\n    signer = None\n    for cert_der in parsed["certs"]:\n        cert = x509.load_der_x509_certificate(cert_der)\n        try:\n            eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage)\n        except x509.ExtensionNotFound:\n            continue\n        if _EKU.TIME_STAMPING in eku.value:\n            signer = cert\n            break\n\n    signer_chain_ok = False\n    if signer is None:\n        errors.append("no signer certificate with timeStamping EKU")\n    else:\n        for root_pem in _PA_KNOWN_TSA_ROOT_CERTS:\n            try:\n                root = x509.load_pem_x509_certificate(root_pem.encode("ascii"))\n                if root.subject != root.issuer:\n                    continue\n                signer.verify_directly_issued_by(root)\n                signer_chain_ok = True\n                break\n            except Exception:\n                continue\n        if not signer_chain_ok:\n            errors.append("signer does not chain to a pinned self-signed root")\n\n    signer_sig_ok = False\n    if signer is not None:\n        hash_cls = ecdsa_oids.get(parsed["sig_alg_oid"]) or rsa_oids.get(\n            parsed["sig_alg_oid"]\n        )\n        if hash_cls is None:\n            errors.append("unsupported signature algorithm "\n                          + parsed["sig_alg_oid"])\n        else:\n            try:\n                pub = signer.public_key()\n                if isinstance(pub, _ec.EllipticCurvePublicKey):\n                    pub.verify(parsed["signature"], parsed["signed_attrs_der"],\n                               _ECDSA(hash_cls()))\n                else:\n                    pub.verify(parsed["signature"], parsed["signed_attrs_der"],\n                               _pad.PKCS1v15(), hash_cls())\n                signer_sig_ok = True\n            except Exception as exc:\n                errors.append("signer signature verification failed: "\n                              + repr(exc))\n\n    content_type_ok = False\n    ct_span = parsed["attrs"].get(_PA_OID_ATTR_CONTENT_TYPE)\n    if ct_span is None:\n        errors.append("missing content-type signed attribute")\n    else:\n        content_type_ok = (\n            _pa_oid_str(parsed["buf"], ct_span[0], ct_span[1])\n            == _PA_OID_CT_TSTINFO\n        )\n        if not content_type_ok:\n            errors.append("content-type signed attribute is not id-ct-TSTInfo")\n\n    message_digest_ok = False\n    md_span = parsed["attrs"].get(_PA_OID_ATTR_MESSAGE_DIGEST)\n    digest_name = digest_oids.get(parsed["digest_oid"])\n    if md_span is None:\n        errors.append("missing message-digest signed attribute")\n    elif digest_name is None:\n        errors.append("unsupported digest algorithm " + parsed["digest_oid"])\n    else:\n        md = parsed["buf"][md_span[0]:md_span[1]]\n        message_digest_ok = (\n            _hl.new(digest_name, parsed["tstinfo"]).digest() == md\n        )\n        if not message_digest_ok:\n            errors.append("message-digest attribute does not match eContent")\n\n    hashed, imprint_alg_oid, gen_time = _pa_parse_tstinfo(parsed["tstinfo"])\n    imprint_binds_ok = False\n    imprint_name = digest_oids.get(imprint_alg_oid)\n    if imprint_name is None:\n        errors.append("unsupported imprint algorithm " + imprint_alg_oid)\n    else:\n        imprint_binds_ok = (\n            _hl.new(imprint_name, timestamped_data).digest() == hashed\n        )\n        if not imprint_binds_ok:\n            errors.append("messageImprint does not bind the supplied data")\n\n    ok = (signer_chain_ok and signer_sig_ok and content_type_ok\n          and message_digest_ok and imprint_binds_ok)\n    return ok, gen_time, errors\n\n\ndef _check_pce_anchor(manifest, ROOT):\n    # __s191_pce_anchor_embed_v1__ Pre-commitment temporal verifier (Art 43(4)\n    # anti-backdating). MONITOR, NOT GATE: returns 0 on every ordering verdict\n    # (anchored / post-hoc / anchored-absolute) and 0 when no receipt is\n    # carried; non-zero ONLY on integrity failure (sha mismatch, anchored\n    # bytes != pce.json, missing-but-declared sidecar, or an RFC 3161 token\n    # that does not verify against the pinned TSA root). Ordering never fails\n    # the process; only tamper does.\n    import base64 as _b64\n    import hashlib as _hl\n    import json as _js\n    import sys as _sys\n\n    field = manifest.get("pce_anchor_sha256")\n    ap = ROOT / "pce.anchor.json"\n    if field is None:\n        if ap.is_file():\n            print("FAIL: manifest declares no pce_anchor_sha256 but a "\n                  "pce.anchor.json is present (unexpected evidence)",\n                  file=_sys.stderr)\n            return 1\n        return 0\n    if not ap.is_file():\n        print("FAIL: signed manifest declares pce_anchor_sha256 but "\n              "pce.anchor.json is missing (missing evidence / truncation)",\n              file=_sys.stderr)\n        return 1\n    ab = ap.read_bytes()\n    if _hl.sha256(ab).hexdigest() != field:\n        print("FAIL: pce.anchor.json sha256 does not match the signed "\n              "manifest pce_anchor_sha256 (pre-commitment receipt tampered "\n              "or substituted)", file=_sys.stderr)\n        return 1\n    try:\n        receipt = _js.loads(ab.decode("utf-8"))\n    except Exception as e:\n        print("FAIL: pce.anchor.json parse error: " + str(e), file=_sys.stderr)\n        return 1\n\n    pj = ROOT / "pce.json"\n    if not pj.is_file():\n        print("FAIL: pce.anchor.json present but pce.json missing; the "\n              "anchored envelope is not in the dossier", file=_sys.stderr)\n        return 1\n    pce_bytes = pj.read_bytes()\n    pce_sha = _hl.sha256(pce_bytes).hexdigest()\n    if receipt.get("anchored_pce_sha256") != pce_sha:\n        print("FAIL: receipt anchored_pce_sha256 != sha256(pce.json) "\n              "(the receipt anchors different bytes than the carried "\n              "envelope)", file=_sys.stderr)\n        return 1\n    if manifest.get("pce_sha256") not in (None, pce_sha):\n        print("FAIL: sha256(pce.json) != signed manifest pce_sha256 "\n              "(envelope inconsistent with the signed manifest)",\n              file=_sys.stderr)\n        return 1\n\n    tok_b64 = receipt.get("pce_rfc3161_token_b64")\n    if not isinstance(tok_b64, str) or not tok_b64:\n        print("FAIL: receipt carries no pce_rfc3161_token_b64 (no trusted "\n              "time to recover; cannot establish pre-commitment)",\n              file=_sys.stderr)\n        return 1\n    try:\n        env_token = _b64.b64decode(tok_b64, validate=True)\n    except Exception as e:\n        print("FAIL: pce_rfc3161_token_b64 base64 decode error: " + str(e),\n              file=_sys.stderr)\n        return 1\n    try:\n        env_ok, t_env, env_errs = _pa_verify_rfc3161(env_token, pce_bytes)\n    except _PaMalformed as e:\n        print("FAIL: receipt RFC 3161 token malformed: " + str(e),\n              file=_sys.stderr)\n        return 1\n    if not env_ok:\n        print("FAIL: receipt RFC 3161 timestamp does NOT verify over the "\n              "envelope bytes against the pinned TSA root: "\n              + "; ".join(env_errs), file=_sys.stderr)\n        return 1\n\n    print("OK   pre-commitment receipt authenticated (pce.anchor.json "\n          "sha-gated; anchored_pce_sha256 == sha256(pce.json) == signed "\n          "manifest pce_sha256)")\n    print("     T_env (envelope pre-commitment; RFC 3161 genTime over the "\n          "envelope bytes, pinned TSA root): " + t_env.isoformat())\n\n    tlog = manifest.get("transparency_log")\n    t_change = None\n    if isinstance(tlog, dict) and tlog.get("rfc3161_token_b64") is not None:\n        ch_b64 = tlog.get("rfc3161_token_b64")\n        body_b64 = tlog.get("body_b64")\n        if not isinstance(ch_b64, str) or not isinstance(body_b64, str):\n            print("FAIL: transparency_log rfc3161_token_b64/body_b64 "\n                  "malformed (change-time present but unreadable)",\n                  file=_sys.stderr)\n            return 1\n        try:\n            leaf = _js.loads(_b64.b64decode(body_b64, validate=True))\n            inner = leaf["spec"]["hashedRekordV002"]\n            leaf_sig = _b64.b64decode(\n                inner["signature"]["content"], validate=True\n            )\n        except Exception as e:\n            print("FAIL: cannot recover the Rekor v2 leaf signature from "\n                  "transparency_log.body_b64: " + str(e), file=_sys.stderr)\n            return 1\n        try:\n            ch_token = _b64.b64decode(ch_b64, validate=True)\n            ch_ok, t_change, ch_errs = _pa_verify_rfc3161(ch_token, leaf_sig)\n        except _PaMalformed as e:\n            print("FAIL: change-time RFC 3161 token malformed: " + str(e),\n                  file=_sys.stderr)\n            return 1\n        except Exception as e:\n            print("FAIL: change-time token decode error: " + str(e),\n                  file=_sys.stderr)\n            return 1\n        if not ch_ok:\n            print("FAIL: change-time RFC 3161 timestamp does NOT verify over "\n                  "the Rekor v2 leaf signature against the pinned TSA root: "\n                  + "; ".join(ch_errs), file=_sys.stderr)\n            return 1\n        print("     T_change (this build\'s anchor; RFC 3161 genTime over the "\n              "Rekor v2 leaf signature): " + t_change.isoformat())\n\n    if t_change is None:\n        precedence = "anchored-absolute"\n        print("OK   PCE anchor: ANCHORED-ABSOLUTE. The envelope pre-commitment "\n              "time T_env is established by a pinned-TSA RFC 3161 timestamp "\n              "over the exact envelope bytes. This dossier carries NO in-band "\n              "change-time (no manifest transparency_log RFC 3161 token), so "\n              "NOUS asserts T_env absolutely, NOT relative to this build\'s "\n              "own change-time.")\n    elif t_env < t_change:\n        precedence = "anchored"\n        print("OK   PCE anchor: ANCHORED. T_env < T_change: the predetermined-"\n              "change envelope was timestamped by a pinned TSA BEFORE this "\n              "build\'s own trusted-timestamp. The envelope was pre-committed "\n              "in time; the membership claim is not post-hoc. NOUS evidences "\n              "the ordering; it does not adjudicate Article 43(4).")\n    else:\n        precedence = "post-hoc"\n        print("INFO PCE anchor: POST-HOC. T_env >= T_change: the envelope\'s "\n              "trusted-timestamp is NOT strictly before this build\'s change-"\n              "time. The membership claim may be retrofitted. This is a "\n              "TRUTHFUL detected ordering, not a process failure (monitor); "\n              "the notified body adjudicates. NOUS decides nothing.")\n\n    verdict_obj = {\n        "kind": "pce-anchor-temporal-v1",\n        "temporal_precedence": precedence,\n        "t_env_utc": t_env.isoformat(),\n        "t_change_utc": (t_change.isoformat() if t_change is not None\n                         else None),\n        "basis": ("RFC 3161 genTime ordering against a pinned TSA root; not a "\n                  "legal substantiality or precedence determination"),\n    }\n    print("PCE_ANCHOR_VERDICT_JSON: "\n          + _js.dumps(verdict_obj, sort_keys=True, separators=(",", ":")))\n    return 0\n'  # __s191_pce_anchor_embed_assign_v1__


_ENVELOPE_WITNESS_CHECK_EMBED: str = 'def _ew_hash_leaf(leaf):\n    import hashlib as _hl\n    return _hl.sha256(b"\\x00" + leaf).digest()\n\n\ndef _ew_hash_children(lhs, rhs):\n    import hashlib as _hl\n    return _hl.sha256(b"\\x01" + lhs + rhs).digest()\n\n\ndef _ew_naive_root(leaves):\n    nodes = [_ew_hash_leaf(x) for x in leaves]\n    if len(nodes) == 1:\n        return nodes[0]\n\n    def build(items):\n        if len(items) == 1:\n            return items[0]\n        k = 1\n        while k * 2 < len(items):\n            k *= 2\n        return _ew_hash_children(build(items[:k]), build(items[k:]))\n\n    return build(nodes)\n\n\n_EW_LEAF_PREFIX = b"nous.envelope.leaf.v1\\n"\n_EW_COMMIT_TAG = b"nous.envelope.commit.v1|"\n\n\ndef _ew_commitment(pce_sha256, pce_anchor_sha256):\n    import hashlib as _hl\n    if not isinstance(pce_sha256, str) or len(pce_sha256) != 64:\n        raise ValueError("fan entry pce_sha256 is not a 64-hex sha256")\n    int(pce_sha256, 16)\n    anchor_b = b""\n    if pce_anchor_sha256 is not None:\n        if not isinstance(pce_anchor_sha256, str) or len(pce_anchor_sha256) != 64:\n            raise ValueError("fan entry pce_anchor_sha256 is not a 64-hex sha256")\n        int(pce_anchor_sha256, 16)\n        anchor_b = pce_anchor_sha256.encode("ascii")\n    preimage = _EW_COMMIT_TAG + pce_sha256.encode("ascii") + b"|" + anchor_b\n    return _hl.sha256(preimage).digest()\n\n\ndef _ew_cosig_key_id(name, raw_pub):\n    import hashlib as _hl\n    return _hl.sha256(\n        name.encode("utf-8") + b"\\x0a" + b"\\x04" + raw_pub\n    ).digest()[:4]\n\n\ndef _ew_cosig_signed_message(note_body, ts):\n    return b"cosignature/v1\\n" + b"time " + str(ts).encode("ascii") + b"\\n" + note_body\n\n\ndef _ew_verify_cosig(note_body, name, raw_pub, line_name, line_key_id, line_payload):\n    from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n        Ed25519PublicKey,\n    )\n    from cryptography.exceptions import InvalidSignature\n    if line_name != name:\n        return False\n    if line_key_id != _ew_cosig_key_id(name, raw_pub):\n        return False\n    if len(line_payload) != 72:\n        return False\n    ts = int.from_bytes(line_payload[:8], "big")\n    if ts <= 0 or ts > (1 << 63) - 1:\n        return False\n    try:\n        pub = Ed25519PublicKey.from_public_bytes(raw_pub)\n    except Exception:\n        return False\n    try:\n        pub.verify(line_payload[8:], _ew_cosig_signed_message(note_body, ts))\n    except InvalidSignature:\n        return False\n    except Exception:\n        return False\n    return True\n\n\ndef _ew_parse_checkpoint(note):\n    import base64 as _b64\n    head, sep, tail = note.partition("\\n\\n")\n    if not sep:\n        raise ValueError("checkpoint missing text/signature separator")\n    body = (head + "\\n").encode("utf-8")\n    lines = head.split("\\n")\n    if len(lines) < 3:\n        raise ValueError("checkpoint body has too few lines")\n    tree_size = int(lines[1])\n    root_hash = _b64.b64decode(lines[2])\n    sigs = []\n    for line in tail.split("\\n"):\n        if not line.strip():\n            continue\n        parts = line.split(" ")\n        if len(parts) < 3 or parts[0] != "\\u2014":\n            continue\n        blob = _b64.b64decode(parts[2])\n        sigs.append((parts[1], blob[:4], blob[4:]))\n    return lines[0], tree_size, root_hash, body, sigs\n\n\ndef _check_envelope_witness(manifest, ROOT):\n    # __s194_envelope_witness_embed_v1__ Witness-quorum non-equivocation over\n    # the standalone envelope checkpoint (C2SP 0x04 tlog-cosignatures). MONITOR,\n    # NOT GATE: returns 0 on quorum-met AND on under-quorum; non-zero ONLY on\n    # integrity failure (sha mismatch, missing-but-declared sidecar, malformed\n    # sidecar, re-derived env_root != checkpoint root). The quorum verdict never\n    # fails the process; only tamper does.\n    #\n    # Honest boundary (from line one):\n    #  - a verified cosignature EVIDENCES that a holder of a pinned key attested\n    #    exactly this envelope checkpoint head (origin, size, root); it PROVES\n    #    nothing. The only PROVES legs remain Z3 cost bounds and Farkas.\n    #  - witness INDEPENDENCE is a trust assumption, NOT a proof. Per the C2SP\n    #    tlog-witness model the witness key set is the VERIFIER\'s trusted\n    #    configuration, never supplied by the operator. This verifier reads an\n    #    auditor pin set (witness_keys.json beside the dossier, or the path in\n    #    NOUS_WITNESS_KEYS) when present -- key_provenance="auditor-pinned",\n    #    authoritative -- and otherwise FALLS BACK to the operator-supplied keys\n    #    carried in the sidecar, key_provenance="operator-supplied", and\n    #    DOWNGRADES the verdict: the k-of-n count is real but independence is\n    #    UNVERIFIED, because an operator can mint n keypairs it controls. The\n    #    downgrade is stated, not hidden.\n    #  - cross-epoch non-equivocation (a witness never cosigns two inconsistent\n    #    heads) is each witness\'s own cosign-time obligation; this counter does\n    #    not re-check it and trusts it, which is what a C2SP cosignature means.\n    #  - enumeration is bounded to envelopes committed THROUGH NOUS for this\n    #    epoch; off-log pre-commitment is out of scope and not defeated.\n    #  - name-to-key is operator-asserted; NOUS runs no CA. Rekor-anchoring of\n    #    the witnessed head remains available later as a public backstop.\n    import hashlib as _hl\n    import json as _js\n    import os as _os\n    import sys as _sys\n\n    field = manifest.get("envelope_witness_sha256")\n    wp = ROOT / "envelope.witness.json"\n    if field is None:\n        if wp.is_file():\n            print(\n                "FAIL: manifest declares no envelope_witness_sha256 but an "\n                "envelope.witness.json is present (unexpected evidence)",\n                file=_sys.stderr,\n            )\n            return 1\n        return 0\n    if not wp.is_file():\n        print(\n            "FAIL: signed manifest declares envelope_witness_sha256 but "\n            "envelope.witness.json is missing (missing evidence / truncation)",\n            file=_sys.stderr,\n        )\n        return 1\n    wb = wp.read_bytes()\n    if _hl.sha256(wb).hexdigest() != field:\n        print(\n            "FAIL: envelope.witness.json sha256 does not match the signed "\n            "manifest envelope_witness_sha256 (witness evidence tampered or "\n            "substituted)",\n            file=_sys.stderr,\n        )\n        return 1\n    try:\n        doc = _js.loads(wb.decode("utf-8"))\n    except Exception as e:\n        print("FAIL: envelope.witness.json parse error: " + str(e),\n              file=_sys.stderr)\n        return 1\n    if not isinstance(doc, dict):\n        print("FAIL: envelope.witness.json is not a JSON object",\n              file=_sys.stderr)\n        return 1\n    if doc.get("witness_schema_version") != 1:\n        print(\n            "FAIL: unsupported witness_schema_version "\n            + repr(doc.get("witness_schema_version")) + "; expected 1",\n            file=_sys.stderr,\n        )\n        return 1\n    note = doc.get("checkpoint_note")\n    if not isinstance(note, str) or not note:\n        print("FAIL: envelope.witness.json carries no checkpoint_note string",\n              file=_sys.stderr)\n        return 1\n    fan = doc.get("fan")\n    if not isinstance(fan, list) or not fan:\n        print("FAIL: envelope.witness.json carries no fan (enumerated envelope "\n              "commitments); the leaf domain cannot be re-derived",\n              file=_sys.stderr)\n        return 1\n    threshold = doc.get("threshold")\n    if not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 1:\n        print("FAIL: envelope.witness.json threshold must be a positive int",\n              file=_sys.stderr)\n        return 1\n\n    try:\n        origin, tree_size, root_hash, note_body, sigs = _ew_parse_checkpoint(note)\n    except Exception as e:\n        print("FAIL: checkpoint_note does not parse: " + str(e),\n              file=_sys.stderr)\n        return 1\n\n    # Re-derive env_root from the enumerated fan; must equal the checkpoint\n    # root and the fan length must equal the committed tree size.\n    try:\n        leaves = []\n        for entry in fan:\n            if not isinstance(entry, list) or len(entry) != 2:\n                raise ValueError("fan entry must be [pce_sha256, "\n                                 "pce_anchor_sha256|null]")\n            commitment = _ew_commitment(entry[0], entry[1])\n            leaves.append(_EW_LEAF_PREFIX + commitment)\n    except Exception as e:\n        print("FAIL: fan is malformed: " + str(e), file=_sys.stderr)\n        return 1\n    if len(leaves) != tree_size:\n        print(\n            "FAIL: fan length " + str(len(leaves)) + " != checkpoint tree_size "\n            + str(tree_size) + " (enumerated leaf domain disagrees with the "\n            "committed head)",\n            file=_sys.stderr,\n        )\n        return 1\n    derived_root = _ew_naive_root(leaves)\n    if derived_root != root_hash:\n        print(\n            "FAIL: re-derived env_root " + derived_root.hex()[:16] + "... != "\n            "checkpoint root " + root_hash.hex()[:16] + "... (the enumerated "\n            "fan does not reproduce the committed head)",\n            file=_sys.stderr,\n        )\n        return 1\n\n    # Resolve the witness pin set. Auditor pins are authoritative when present.\n    key_provenance = None\n    pins = []\n    ext_path = _os.environ.get("NOUS_WITNESS_KEYS")\n    ext_file = None\n    if ext_path:\n        from pathlib import Path as _Path\n        cand = _Path(ext_path)\n        if cand.is_file():\n            ext_file = cand\n    if ext_file is None and (ROOT / "witness_keys.json").is_file():\n        ext_file = ROOT / "witness_keys.json"\n    src_obj = None\n    if ext_file is not None:\n        try:\n            src_obj = _js.loads(ext_file.read_text(encoding="utf-8"))\n            key_provenance = "auditor-pinned"\n        except Exception as e:\n            print("FAIL: auditor witness_keys file parse error: " + str(e),\n                  file=_sys.stderr)\n            return 1\n    else:\n        src_obj = doc.get("witnesses")\n        key_provenance = "operator-supplied"\n    wlist = src_obj.get("witnesses") if isinstance(src_obj, dict) else src_obj\n    if not isinstance(wlist, list) or not wlist:\n        print(\n            "FAIL: witness key set (" + str(key_provenance) + ") carries no "\n            "witnesses list",\n            file=_sys.stderr,\n        )\n        return 1\n    import base64 as _b64\n    seen_names = set()\n    for w in wlist:\n        if not isinstance(w, dict):\n            print("FAIL: a witness pin is not an object", file=_sys.stderr)\n            return 1\n        name = w.get("name")\n        pub_b64 = w.get("pubkey_b64")\n        if not isinstance(name, str) or not name or " " in name or "\\n" in name:\n            print("FAIL: a witness pin has a missing or malformed name",\n                  file=_sys.stderr)\n            return 1\n        if name in seen_names:\n            print(\n                "FAIL: duplicate witness name " + repr(name) + " in the pin "\n                "set makes distinct-witness counting ambiguous",\n                file=_sys.stderr,\n            )\n            return 1\n        seen_names.add(name)\n        try:\n            raw_pub = _b64.b64decode(pub_b64, validate=True)\n        except Exception:\n            print("FAIL: witness " + repr(name) + " pubkey_b64 is not valid "\n                  "base64", file=_sys.stderr)\n            return 1\n        if len(raw_pub) != 32:\n            print("FAIL: witness " + repr(name) + " pubkey is not a 32-byte "\n                  "Ed25519 raw key", file=_sys.stderr)\n            return 1\n        pins.append((name, raw_pub))\n\n    # Distinct-witness k-of-n over the parsed cosignature lines.\n    verified_names = []\n    for name, raw_pub in pins:\n        for (ln_name, ln_kid, ln_payload) in sigs:\n            if _ew_verify_cosig(note_body, name, raw_pub, ln_name, ln_kid,\n                                ln_payload):\n                verified_names.append(name)\n                break\n    verified_count = len(verified_names)\n    met = verified_count >= threshold\n\n    print(\n        "OK   envelope witness evidence authenticated (envelope.witness.json "\n        "sha-gated by the signed manifest; " + str(len(leaves)) + " enumerated "\n        "envelope commitment(s) re-derive the checkpoint head " + origin + ")"\n    )\n    print(\n        "     KEY PROVENANCE: " + key_provenance + ". "\n        + ("The witness key set is the auditor\'s trusted configuration; the "\n           "independence assumption is auditor-backed."\n           if key_provenance == "auditor-pinned" else\n           "The witness key set is OPERATOR-SUPPLIED (carried in the sidecar). "\n           "The k-of-n count is real, but witness INDEPENDENCE is UNVERIFIED -- "\n           "an operator can mint keypairs it controls. Supply a witness_keys.json "\n           "beside the dossier (or NOUS_WITNESS_KEYS) to establish the trust "\n           "root.")\n    )\n    if met:\n        print(\n            "OK   witness quorum: MET. " + str(verified_count) + " of "\n            + str(len(pins)) + " pinned witnesses cosigned this head; threshold "\n            + str(threshold) + " reached. This EVIDENCES non-equivocation of the "\n            "envelope log under the named trust assumption (safe unless "\n            + str(threshold) + " pinned witnesses collude with the operator). "\n            "NOUS evidences; it proves nothing and adjudicates nothing."\n        )\n    else:\n        print(\n            "INFO witness quorum: UNDER-QUORUM. " + str(verified_count) + " of "\n            + str(len(pins)) + " pinned witnesses cosigned this head; threshold "\n            + str(threshold) + " NOT reached. This is a TRUTHFUL detected state, "\n            "not a process failure (monitor). An auditor requiring "\n            + str(threshold) + " independent attestations should treat "\n            "non-equivocation as NOT established from this dossier."\n        )\n    verdict_obj = {\n        "kind": "envelope-witness-quorum-v1",\n        "threshold": threshold,\n        "pin_count": len(pins),\n        "verified_count": verified_count,\n        "verified_names": sorted(verified_names),\n        "met": met,\n        "key_provenance": key_provenance,\n        "origin": origin,\n        "tree_size": tree_size,\n        "basis": ("k-of-n C2SP 0x04 cosignatures over the envelope checkpoint; "\n                  "independence is a named trust assumption, not a proof; "\n                  "monitor, not guard"),\n    }\n    print(\n        "ENVELOPE_WITNESS_VERDICT_JSON: "\n        + _js.dumps(verdict_obj, sort_keys=True, separators=(",", ":"))\n    )\n    return 0\n'  # __s194_envelope_witness_embed_assign_v1__


_CLOSURE_WITNESS_CHECK_EMBED: str = 'def _cw_hash_leaf(leaf):\n    import hashlib as _hl\n    return _hl.sha256(b"\\x00" + leaf).digest()\n\n\ndef _cw_hash_children(lhs, rhs):\n    import hashlib as _hl\n    return _hl.sha256(b"\\x01" + lhs + rhs).digest()\n\n\n_CW_LEAF_PREFIX = b"nous.envelope.leaf.v1\\n"\n_CW_COMMIT_TAG = b"nous/closure-root/v1|"\n\n\ndef _cw_public_body(root_hex, policy_id, interval_start, interval_end):\n    import json as _js\n    if not isinstance(root_hex, str) or len(root_hex) != 64:\n        raise ValueError("closure root is not a 64-hex sha256")\n    int(root_hex, 16)\n    doc = {\n        "interval_end": interval_end,\n        "interval_start": interval_start,\n        "policy_id": policy_id,\n        "root": root_hex,\n    }\n    return _js.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")\n\n\ndef _cw_commitment(root_hex, policy_id, interval_start, interval_end):\n    import hashlib as _hl\n    body = _cw_public_body(root_hex, policy_id, interval_start, interval_end)\n    return _hl.sha256(_CW_COMMIT_TAG + body).digest()\n\n\ndef _cw_decomp_inclusion_proof(index, size):\n    inner = (index ^ (size - 1)).bit_length()\n    border = bin(index >> inner).count("1")\n    return inner, border\n\n\ndef _cw_chain_inner(seed, proof, index):\n    acc = seed\n    for i, h in enumerate(proof):\n        if (index >> i) & 1 == 0:\n            acc = _cw_hash_children(acc, h)\n        else:\n            acc = _cw_hash_children(h, acc)\n    return acc\n\n\ndef _cw_chain_border_right(seed, proof):\n    acc = seed\n    for h in proof:\n        acc = _cw_hash_children(h, acc)\n    return acc\n\n\ndef _cw_verify_inclusion(leaf_data, log_index, tree_size, proof, root_hash):\n    if not (0 <= log_index < tree_size):\n        raise ValueError("log_index out of range for tree_size")\n    inner, border = _cw_decomp_inclusion_proof(log_index, tree_size)\n    if len(proof) != inner + border:\n        raise ValueError("inclusion proof wrong size")\n    lh = _cw_hash_leaf(leaf_data)\n    mid = _cw_chain_inner(lh, proof[:inner], log_index)\n    calc = _cw_chain_border_right(mid, proof[inner:])\n    if calc != root_hash:\n        raise ValueError("inclusion root mismatch")\n    return lh\n\n\ndef _cw_cosig_key_id(name, raw_pub):\n    import hashlib as _hl\n    return _hl.sha256(\n        name.encode("utf-8") + b"\\x0a" + b"\\x04" + raw_pub\n    ).digest()[:4]\n\n\ndef _cw_cosig_signed_message(note_body, ts):\n    return (b"cosignature/v1\\n" + b"time " + str(ts).encode("ascii")\n            + b"\\n" + note_body)\n\n\ndef _cw_verify_cosig(note_body, name, raw_pub, line_name, line_key_id,\n                     line_payload):\n    from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n        Ed25519PublicKey,\n    )\n    from cryptography.exceptions import InvalidSignature\n    if line_name != name:\n        return False\n    if line_key_id != _cw_cosig_key_id(name, raw_pub):\n        return False\n    if len(line_payload) != 72:\n        return False\n    ts = int.from_bytes(line_payload[:8], "big")\n    if ts <= 0 or ts > (1 << 63) - 1:\n        return False\n    try:\n        pub = Ed25519PublicKey.from_public_bytes(raw_pub)\n    except Exception:\n        return False\n    try:\n        pub.verify(line_payload[8:], _cw_cosig_signed_message(note_body, ts))\n    except InvalidSignature:\n        return False\n    except Exception:\n        return False\n    return True\n\n\ndef _cw_parse_checkpoint(note):\n    import base64 as _b64\n    head, sep, tail = note.partition("\\n\\n")\n    if not sep:\n        raise ValueError("checkpoint missing text/signature separator")\n    body = (head + "\\n").encode("utf-8")\n    lines = head.split("\\n")\n    if len(lines) < 3:\n        raise ValueError("checkpoint body has too few lines")\n    tree_size = int(lines[1])\n    root_hash = _b64.b64decode(lines[2])\n    sigs = []\n    for line in tail.split("\\n"):\n        if not line.strip():\n            continue\n        parts = line.split(" ")\n        if len(parts) < 3 or parts[0] != "\\u2014":\n            continue\n        blob = _b64.b64decode(parts[2])\n        sigs.append((parts[1], blob[:4], blob[4:]))\n    return lines[0], tree_size, root_hash, body, sigs\n\n\ndef _check_closure_witness(manifest, ROOT):\n    # __s208_closure_witness_embed_v1__ Closure-attestation inclusion +\n    # witness-quorum non-equivocation over the envelope checkpoint that\n    # carries the closure ROOT as a single leaf (tlog-proof@v1 shape:\n    # checkpoint-verbatim + single-entry inclusion + cosignatures). MONITOR,\n    # NOT GATE: returns 0 on quorum-met AND under-quorum; non-zero ONLY on\n    # integrity failure (sha mismatch, missing-but-declared sidecar, malformed\n    # sidecar, re-derived leaf not included under the cosigned root). The\n    # quorum verdict never fails the process; only tamper does.\n    #\n    # Honest boundary (from line one):\n    #  - a verified inclusion + cosignature quorum EVIDENCES that the operator\'s\n    #    signed closure ROOT for (policy, interval) is a leaf in an envelope log\n    #    whose head a quorum of pinned keys cosigned (non-equivocated under the\n    #    named trust assumption). It PROVES nothing: completeness itself is the\n    #    operator\'s Inc B signed assertion plus omission adverse-inference, never\n    #    a NOUS proof. The only PROVES legs remain Z3 cost bounds and Farkas.\n    #  - the sidecar carries the PUBLIC PROJECTION only: {policy_id, interval,\n    #    root}. It DOES NOT carry action_count; per-(policy, interval) governed-\n    #    action VOLUME stays in the auditor-only Inc B attestation, delivered\n    #    out-of-band. The dossier stays universally shareable.\n    #  - DISCLOSURE (stated, not hidden): an offline inclusion proof intrinsically\n    #    reveals the WHOLE-LOG envelope tree_size at the witnessed epoch. That is\n    #    a count of ALL envelopes in the epoch, NOT per-(policy, interval) action\n    #    volume, so the surface-split holds. A deployment finding even the whole-\n    #    log count too sensitive omits the field entirely (drop-when-None, opt-in)\n    #    or uses coarser epochs; it NEVER drops cosignatures, which would gut\n    #    offline non-equivocation.\n    #  - witness INDEPENDENCE is a trust assumption, NOT a proof. Per the C2SP\n    #    tlog-witness model the witness key set is the VERIFIER\'s trusted\n    #    configuration, never supplied by the operator. This verifier reads an\n    #    auditor pin set (witness_keys.json beside the dossier, or the path in\n    #    NOUS_WITNESS_KEYS) when present -- key_provenance="auditor-pinned",\n    #    authoritative -- and otherwise FALLS BACK to operator-supplied keys in\n    #    the sidecar, key_provenance="operator-supplied", and DOWNGRADES: the\n    #    k-of-n count is real but independence is UNVERIFIED.\n    #  - name-to-key is operator-asserted; NOUS runs no CA.\n    import base64 as _b64\n    import hashlib as _hl\n    import json as _js\n    import os as _os\n    import sys as _sys\n\n    field = manifest.get("closure_witness_sha256")\n    cp = ROOT / "closure.witness.json"\n    if field is None:\n        if cp.is_file():\n            print(\n                "FAIL: manifest declares no closure_witness_sha256 but a "\n                "closure.witness.json is present (unexpected evidence)",\n                file=_sys.stderr,\n            )\n            return 1\n        return 0\n    if not cp.is_file():\n        print(\n            "FAIL: signed manifest declares closure_witness_sha256 but "\n            "closure.witness.json is missing (missing evidence / truncation)",\n            file=_sys.stderr,\n        )\n        return 1\n    cb = cp.read_bytes()\n    if _hl.sha256(cb).hexdigest() != field:\n        print(\n            "FAIL: closure.witness.json sha256 does not match the signed "\n            "manifest closure_witness_sha256 (closure witness evidence "\n            "tampered or substituted)",\n            file=_sys.stderr,\n        )\n        return 1\n    try:\n        doc = _js.loads(cb.decode("utf-8"))\n    except Exception as e:\n        print("FAIL: closure.witness.json parse error: " + str(e),\n              file=_sys.stderr)\n        return 1\n    if not isinstance(doc, dict):\n        print("FAIL: closure.witness.json is not a JSON object",\n              file=_sys.stderr)\n        return 1\n    if doc.get("closure_witness_schema_version") != 1:\n        print(\n            "FAIL: unsupported closure_witness_schema_version "\n            + repr(doc.get("closure_witness_schema_version")) + "; expected 1",\n            file=_sys.stderr,\n        )\n        return 1\n\n    policy_id = doc.get("policy_id")\n    interval_start = doc.get("interval_start")\n    interval_end = doc.get("interval_end")\n    root_hex = doc.get("root")\n    for nm, vv in (("policy_id", policy_id), ("interval_start", interval_start),\n                   ("interval_end", interval_end), ("root", root_hex)):\n        if not isinstance(vv, str) or not vv:\n            print("FAIL: closure.witness.json " + nm + " missing or not a "\n                  "non-empty string", file=_sys.stderr)\n            return 1\n    if "action_count" in doc:\n        print(\n            "FAIL: closure.witness.json carries action_count; the dossier "\n            "projection must not disclose per-(policy, interval) volume "\n            "(surface-split violation)",\n            file=_sys.stderr,\n        )\n        return 1\n\n    note = doc.get("checkpoint_note")\n    if not isinstance(note, str) or not note:\n        print("FAIL: closure.witness.json carries no checkpoint_note string",\n              file=_sys.stderr)\n        return 1\n    log_index = doc.get("log_index")\n    tree_size = doc.get("tree_size")\n    if not isinstance(log_index, int) or isinstance(log_index, bool) \\\n            or log_index < 0:\n        print("FAIL: closure.witness.json log_index must be a non-negative int",\n              file=_sys.stderr)\n        return 1\n    if not isinstance(tree_size, int) or isinstance(tree_size, bool) \\\n            or tree_size < 1:\n        print("FAIL: closure.witness.json tree_size must be a positive int",\n              file=_sys.stderr)\n        return 1\n    proof_b64 = doc.get("inclusion_proof")\n    if not isinstance(proof_b64, list):\n        print("FAIL: closure.witness.json inclusion_proof must be a list of "\n              "base64 hashes", file=_sys.stderr)\n        return 1\n    try:\n        proof = [_b64.b64decode(h, validate=True) for h in proof_b64]\n    except Exception as e:\n        print("FAIL: closure.witness.json inclusion_proof b64 decode error: "\n              + str(e), file=_sys.stderr)\n        return 1\n    for h in proof:\n        if len(h) != 32:\n            print("FAIL: an inclusion_proof hash is not 32 bytes",\n                  file=_sys.stderr)\n            return 1\n    threshold = doc.get("threshold")\n    if not isinstance(threshold, int) or isinstance(threshold, bool) \\\n            or threshold < 1:\n        print("FAIL: closure.witness.json threshold must be a positive int",\n              file=_sys.stderr)\n        return 1\n\n    try:\n        origin, note_tree_size, root_hash, note_body, sigs = \\\n            _cw_parse_checkpoint(note)\n    except Exception as e:\n        print("FAIL: checkpoint_note does not parse: " + str(e),\n              file=_sys.stderr)\n        return 1\n    if note_tree_size != tree_size:\n        print(\n            "FAIL: sidecar tree_size " + str(tree_size) + " != checkpoint "\n            "note tree_size " + str(note_tree_size) + " (inclusion domain "\n            "disagrees with the cosigned head)",\n            file=_sys.stderr,\n        )\n        return 1\n\n    try:\n        commitment = _cw_commitment(root_hex, policy_id, interval_start,\n                                    interval_end)\n    except Exception as e:\n        print("FAIL: closure commitment cannot be re-derived from the "\n              "projection: " + str(e), file=_sys.stderr)\n        return 1\n    leaf_data = _CW_LEAF_PREFIX + commitment\n    try:\n        _cw_verify_inclusion(leaf_data, log_index, tree_size, proof, root_hash)\n    except Exception as e:\n        print(\n            "FAIL: the closure ROOT for (" + policy_id + ", " + interval_start\n            + "..." + interval_end + ") is NOT included under the cosigned "\n            "checkpoint root: " + str(e) + " (the signed closure attestation "\n            "is not the enveloped leaf, or the proof is forged)",\n            file=_sys.stderr,\n        )\n        return 1\n\n    key_provenance = None\n    ext_path = _os.environ.get("NOUS_WITNESS_KEYS")\n    ext_file = None\n    if ext_path:\n        from pathlib import Path as _Path\n        cand = _Path(ext_path)\n        if cand.is_file():\n            ext_file = cand\n    if ext_file is None and (ROOT / "witness_keys.json").is_file():\n        ext_file = ROOT / "witness_keys.json"\n    src_obj = None\n    if ext_file is not None:\n        try:\n            src_obj = _js.loads(ext_file.read_text(encoding="utf-8"))\n            key_provenance = "auditor-pinned"\n        except Exception as e:\n            print("FAIL: auditor witness_keys file parse error: " + str(e),\n                  file=_sys.stderr)\n            return 1\n    else:\n        src_obj = doc.get("witnesses")\n        key_provenance = "operator-supplied"\n    wlist = src_obj.get("witnesses") if isinstance(src_obj, dict) else src_obj\n    if not isinstance(wlist, list) or not wlist:\n        print(\n            "FAIL: witness key set (" + str(key_provenance) + ") carries no "\n            "witnesses list",\n            file=_sys.stderr,\n        )\n        return 1\n    pins = []\n    seen_names = set()\n    for w in wlist:\n        if not isinstance(w, dict):\n            print("FAIL: a witness pin is not an object", file=_sys.stderr)\n            return 1\n        name = w.get("name")\n        pub_b64 = w.get("pubkey_b64")\n        if not isinstance(name, str) or not name or " " in name or "\\n" in name:\n            print("FAIL: a witness pin has a missing or malformed name",\n                  file=_sys.stderr)\n            return 1\n        if name in seen_names:\n            print(\n                "FAIL: duplicate witness name " + repr(name) + " in the pin "\n                "set makes distinct-witness counting ambiguous",\n                file=_sys.stderr,\n            )\n            return 1\n        seen_names.add(name)\n        try:\n            raw_pub = _b64.b64decode(pub_b64, validate=True)\n        except Exception:\n            print("FAIL: witness " + repr(name) + " pubkey_b64 is not valid "\n                  "base64", file=_sys.stderr)\n            return 1\n        if len(raw_pub) != 32:\n            print("FAIL: witness " + repr(name) + " pubkey is not a 32-byte "\n                  "Ed25519 raw key", file=_sys.stderr)\n            return 1\n        pins.append((name, raw_pub))\n\n    verified_names = []\n    for name, raw_pub in pins:\n        for (ln_name, ln_kid, ln_payload) in sigs:\n            if _cw_verify_cosig(note_body, name, raw_pub, ln_name, ln_kid,\n                                ln_payload):\n                verified_names.append(name)\n                break\n    verified_count = len(verified_names)\n    met = verified_count >= threshold\n\n    print(\n        "OK   closure witness evidence authenticated (closure.witness.json "\n        "sha-gated by the signed manifest; the signed closure ROOT for policy "\n        + policy_id + " over [" + interval_start + ", " + interval_end + "] is "\n        "included as a single leaf in the cosigned envelope checkpoint "\n        + origin + ")"\n    )\n    print(\n        "     KEY PROVENANCE: " + key_provenance + ". "\n        + ("The witness key set is the auditor\'s trusted configuration; the "\n           "independence assumption is auditor-backed."\n           if key_provenance == "auditor-pinned" else\n           "The witness key set is OPERATOR-SUPPLIED (carried in the sidecar). "\n           "The k-of-n count is real, but witness INDEPENDENCE is UNVERIFIED -- "\n           "an operator can mint keypairs it controls. Supply a "\n           "witness_keys.json beside the dossier (or NOUS_WITNESS_KEYS) to "\n           "establish the trust root.")\n    )\n    print(\n        "     SCOPE: the projection carries {policy_id, interval, root} only. "\n        "No action_count is present; per-(policy, interval) governed-action "\n        "VOLUME stays in the auditor-only Inc B attestation (surface-split). "\n        "The whole-log envelope tree_size " + str(tree_size) + " is disclosed "\n        "by the inclusion proof and counts ALL envelopes in the epoch, NOT "\n        "this interval\'s actions."\n    )\n    if met:\n        print(\n            "OK   witness quorum: MET. " + str(verified_count) + " of "\n            + str(len(pins)) + " pinned witnesses cosigned this head; threshold "\n            + str(threshold) + " reached. This EVIDENCES non-equivocation of "\n            "the envelope log carrying the closure ROOT under the named trust "\n            "assumption (safe unless " + str(threshold) + " pinned witnesses "\n            "collude with the operator). Completeness itself remains the "\n            "operator\'s signed assertion; NOUS proves nothing and adjudicates "\n            "nothing."\n        )\n    else:\n        print(\n            "INFO witness quorum: UNDER-QUORUM. " + str(verified_count) + " of "\n            + str(len(pins)) + " pinned witnesses cosigned this head; threshold "\n            + str(threshold) + " NOT reached. This is a TRUTHFUL detected "\n            "state, not a process failure (monitor). An auditor requiring "\n            + str(threshold) + " independent attestations should treat "\n            "non-equivocation of the closure envelope as NOT established from "\n            "this dossier."\n        )\n    verdict_obj = {\n        "kind": "closure-witness-quorum-v1",\n        "policy_id": policy_id,\n        "interval": [interval_start, interval_end],\n        "root": root_hex,\n        "threshold": threshold,\n        "pin_count": len(pins),\n        "verified_count": verified_count,\n        "verified_names": sorted(verified_names),\n        "met": met,\n        "key_provenance": key_provenance,\n        "origin": origin,\n        "tree_size": tree_size,\n        "log_index": log_index,\n        "basis": ("single-leaf tlog-proof@v1 inclusion + k-of-n C2SP 0x04 "\n                  "cosignatures over the envelope checkpoint carrying the "\n                  "closure ROOT; independence is a named trust assumption, "\n                  "not a proof; completeness is the operator\'s signed "\n                  "assertion; monitor, not guard"),\n    }\n    print(\n        "CLOSURE_WITNESS_VERDICT_JSON: "\n        + _js.dumps(verdict_obj, sort_keys=True, separators=(",", ":"))\n    )\n    return 0\n'  # __s208_closure_witness_embed_assign_v1__


def _splice_closure_witness_check(verify_src: str) -> str:
    # __s208_closure_witness_splice_fn_v1__ build-time splice
    # mirroring the envelope-witness splice: insert the closure-
    # witness embed after ROOT and a call into the selected
    # verifier. Applied only when the dossier carries a
    # closure.witness.json, so verifiers without one stay byte-
    # identical.
    anchor = "ROOT = Path(__file__).parent\n"
    n_root = verify_src.count(anchor)
    if n_root != 1:
        raise DossierError(
            "closure-witness splice: expected exactly one ROOT "
            "anchor in the selected verifier, found " + str(n_root)
        )
    verify_src = verify_src.replace(
        anchor, anchor + "\n\n" + _CLOSURE_WITNESS_CHECK_EMBED + "\n", 1
    )
    call_anchor = "    return 0\n\n\nif __name__ == \"__main__\":"
    if verify_src.count(call_anchor) != 1:
        raise DossierError(
            "closure-witness splice: expected exactly one main-"
            "return anchor in the selected verifier"
        )
    call_block = (
        "    _rc_closure_witness = _check_closure_witness("
        "manifest, ROOT)\n"
        "    if _rc_closure_witness != 0:\n"
        "        return _rc_closure_witness\n"
        "    return 0\n\n\nif __name__ == \"__main__\":"
    )
    return verify_src.replace(call_anchor, call_block, 1)




def _splice_pce_anchor_check(verify_src: str) -> str:
    # __s191_pce_anchor_splice_fn_v1__ build-time splice mirroring the
    # PCE membership splice: insert _check_pce_anchor after ROOT and a
    # call into the selected verifier. Applied only when the dossier
    # carries a pre-commitment receipt, so verifiers without one stay
    # byte-identical. Composes with the pce/materiality/attribution
    # splices (distinct ROOT insert + shared return-0 call anchor).
    anchor = "ROOT = Path(__file__).parent\n"
    n_root = verify_src.count(anchor)
    if n_root != 1:
        raise DossierError(
            "pce-anchor splice: expected exactly one ROOT anchor in the "
            "selected verifier, found " + str(n_root)
        )
    verify_src = verify_src.replace(
        anchor, anchor + "\n\n" + _PCE_ANCHOR_CHECK_EMBED + "\n", 1
    )
    call_anchor = "    return 0\n\n\nif __name__ == \"__main__\":"
    if verify_src.count(call_anchor) != 1:
        raise DossierError(
            "pce-anchor splice: expected exactly one main-return anchor "
            "in the selected verifier"
        )
    call_block = (
        "    _rc_pce_anchor = _check_pce_anchor(manifest, ROOT)\n"
        "    if _rc_pce_anchor != 0:\n"
        "        return _rc_pce_anchor\n"
        "    return 0\n\n\nif __name__ == \"__main__\":"
    )
    return verify_src.replace(call_anchor, call_block, 1)


def _splice_envelope_witness_check(verify_src: str) -> str:
    # __s194_envelope_witness_splice_fn_v1__ build-time splice mirroring
    # the pce-anchor splice: insert the envelope-witness embed after ROOT
    # and a call into the selected verifier. Applied only when the dossier
    # carries an envelope.witness.json, so verifiers without one stay
    # byte-identical. Composes with the pce/pce-anchor/materiality/
    # attribution splices (distinct ROOT insert + shared return-0 call
    # anchor).
    anchor = "ROOT = Path(__file__).parent\n"
    n_root = verify_src.count(anchor)
    if n_root != 1:
        raise DossierError(
            "envelope-witness splice: expected exactly one ROOT anchor "
            "in the selected verifier, found " + str(n_root)
        )
    verify_src = verify_src.replace(
        anchor, anchor + "\n\n" + _ENVELOPE_WITNESS_CHECK_EMBED + "\n", 1
    )
    call_anchor = "    return 0\n\n\nif __name__ == \"__main__\":"
    if verify_src.count(call_anchor) != 1:
        raise DossierError(
            "envelope-witness splice: expected exactly one main-return "
            "anchor in the selected verifier"
        )
    call_block = (
        "    _rc_envelope_witness = _check_envelope_witness("
        "manifest, ROOT)\n"
        "    if _rc_envelope_witness != 0:\n"
        "        return _rc_envelope_witness\n"
        "    return 0\n\n\nif __name__ == \"__main__\":"
    )
    return verify_src.replace(call_anchor, call_block, 1)


def _splice_pce_check(verify_src: str) -> str:
    # __s190_pce_splice_fn_v1__ build-time splice: insert the self-contained
    # _check_pce function (after the ROOT definition) and a final call into
    # the SELECTED verifier. Applied only when the dossier carries a PCE, so
    # verifiers without one stay byte-identical. Composes with the materiality
    # and attribution splices in any order: distinct insert anchor (ROOT) and
    # the shared return-0 call anchor that all splices re-emit.
    anchor = "ROOT = Path(__file__).parent\n"
    n_root = verify_src.count(anchor)
    if n_root != 1:
        raise DossierError(
            "pce splice: expected exactly one ROOT anchor in the selected "
            "verifier, found " + str(n_root)
        )
    verify_src = verify_src.replace(
        anchor, anchor + "\n\n" + _PCE_CHECK_EMBED + "\n", 1
    )
    call_anchor = "    return 0\n\n\nif __name__ == \"__main__\":"
    if verify_src.count(call_anchor) != 1:
        raise DossierError(
            "pce splice: expected exactly one main-return anchor in the "
            "selected verifier"
        )
    call_block = (
        "    _rc_pce = _check_pce(manifest, ROOT)\n"
        "    if _rc_pce != 0:\n"
        "        return _rc_pce\n"
        "    return 0\n\n\nif __name__ == \"__main__\":"
    )
    return verify_src.replace(call_anchor, call_block, 1)


def _splice_attribution_check(verify_src: str) -> str:
    # __s180_splice_fn_v1__ build-time splice: insert the self-contained
    # _check_attribution function (after the ROOT definition) and a final
    # call into the SELECTED verifier. Applied only when the dossier
    # carries an attribution, so verifiers without one stay byte-identical.
    # Composes with the materiality splice in either order: distinct insert
    # anchor (ROOT, not the def-main anchor) and a shared return-0 call
    # anchor that both splices re-emit in their call block.
    anchor = "ROOT = Path(__file__).parent\n"
    n_root = verify_src.count(anchor)
    if n_root != 1:
        raise DossierError(
            "attribution splice: expected exactly one ROOT anchor in the "
            "selected verifier, found " + str(n_root)
        )
    verify_src = verify_src.replace(
        anchor, anchor + "\n\n" + _ATTRIBUTION_CHECK_EMBED + "\n", 1
    )
    call_anchor = "    return 0\n\n\nif __name__ == \"__main__\":"
    if verify_src.count(call_anchor) != 1:
        raise DossierError(
            "attribution splice: expected exactly one main-return anchor "
            "in the selected verifier"
        )
    call_block = (
        "    _rc_attr = _check_attribution(manifest, ROOT)\n"
        "    if _rc_attr != 0:\n"
        "        return _rc_attr\n"
        "    return 0\n\n\nif __name__ == \"__main__\":"
    )
    return verify_src.replace(call_anchor, call_block, 1)



def build_dossier(
    source: Path,
    *,
    manifest: Optional[Path] = None,
    prices: Optional[Path] = None,
    output: Optional[Path] = None,
    today: Optional[date] = None,
    anchor: str = "none",
    supersedes: Optional[Path] = None,  # __s120_chain_carry_v1__
    annex_iv_map: bool = False,  # __s135_annex_iv_emit_v1__
    annex_iv_key_path: Optional[Path] = None,  # __s135_annex_iv_emit_v1__
    _test_rekor_anchor: "object | None" = None,
    _test_rekor_anchor_v2: "object | None" = None,
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

    coverage_smt2_bytes = None  # __s115_dossier_coverage_v1__
    if parsed_manifest.policy_coverage_sha256 is not None:
        cov_src = manifest.parent / "coverage.smt2"
        if not cov_src.is_file():
            raise DossierError(
                f"manifest declares a coverage proof but "
                f"coverage.smt2 not found next to manifest: "
                f"{cov_src}"
            )
        coverage_smt2_bytes = cov_src.read_bytes()
        cov_file_sha = hashlib.sha256(coverage_smt2_bytes).hexdigest()
        if cov_file_sha != parsed_manifest.coverage_smt2_sha256:
            raise DossierError(
                f"coverage.smt2 sha256 mismatch: file="
                f"{cov_file_sha[:16]}... manifest="
                f"{(parsed_manifest.coverage_smt2_sha256 or '')[:16]}"
                f"... (coverage proof tampered or substituted)"
            )

    coverage_farkas_bytes = None  # __s116_dossier_farkas_v1__
    if parsed_manifest.coverage_farkas_sha256 is not None:
        farkas_src = manifest.parent / "coverage.farkas.json"
        if not farkas_src.is_file():
            raise DossierError(
                f"manifest declares a Farkas certificate but "
                f"coverage.farkas.json not found next to manifest: "
                f"{farkas_src}"
            )
        coverage_farkas_bytes = farkas_src.read_bytes()
        farkas_file_sha = hashlib.sha256(coverage_farkas_bytes).hexdigest()
        if farkas_file_sha != parsed_manifest.coverage_farkas_sha256:
            raise DossierError(
                f"coverage.farkas.json sha256 mismatch: file="
                f"{farkas_file_sha[:16]}... manifest="
                f"{(parsed_manifest.coverage_farkas_sha256 or '')[:16]}"
                f"... (Farkas certificate tampered or substituted)"
            )
    cost_farkas_bytes = None  # __s170_leg2_cost_carry_v1__
    if parsed_manifest.cost_farkas_sha256 is not None:  # __s170_leg2_cost_carry_v1__
        cost_src = manifest.parent / "cost.farkas.json"
        if not cost_src.is_file():
            raise DossierError(
                f"manifest declares a cost-cap Farkas certificate but "
                f"cost.farkas.json not found next to manifest: "
                f"{cost_src}"
            )
        cost_farkas_bytes = cost_src.read_bytes()
        cost_file_sha = hashlib.sha256(cost_farkas_bytes).hexdigest()
        if cost_file_sha != parsed_manifest.cost_farkas_sha256:
            raise DossierError(
                f"cost.farkas.json sha256 mismatch: file="
                f"{cost_file_sha[:16]}... manifest="
                f"{(parsed_manifest.cost_farkas_sha256 or '')[:16]}"
                f"... (cost-cap Farkas certificate tampered or substituted)"
            )
    materiality_bytes = None  # __s171_materiality_carry_read_v1__
    if parsed_manifest.materiality_sha256 is not None:  # __s171_materiality_carry_read_v1__
        if parsed_manifest.source_kind == "gap-witness":  # __s171_gapw_materiality_refuse_v1__
            raise DossierError(
                "materiality classification refused on a coverage-gap-"
                "witness (refutation) dossier: a minor/material change "
                "verdict over a refutation artifact is incoherent"
            )
        mat_src = manifest.parent / "materiality.json"
        if not mat_src.is_file():
            raise DossierError(
                f"manifest declares a materiality classification but "
                f"materiality.json not found next to manifest: "
                f"{mat_src}"
            )
        materiality_bytes = mat_src.read_bytes()
        mat_file_sha = hashlib.sha256(materiality_bytes).hexdigest()
        if mat_file_sha != parsed_manifest.materiality_sha256:
            raise DossierError(
                f"materiality.json sha256 mismatch: file="
                f"{mat_file_sha[:16]}... manifest="
                f"{(parsed_manifest.materiality_sha256 or '')[:16]}"
                f"... (materiality classification tampered or substituted)"
            )
    pce_bytes = None  # __s190_pce_carry_read_v1__
    baseline_canon_bytes = None  # __s190_pce_carry_read_v1__
    spec_canon_bytes = None  # __s190_pce_carry_read_v1__
    _pce_anchor_bytes = None  # __s191_pce_anchor_carry_init_v1__
    _envelope_witness_bytes = None  # __s194_envelope_witness_carry_init_v1__
    if parsed_manifest.pce_sha256 is not None:  # __s190_pce_carry_read_v1__
        import hashlib as _pce_hashlib
        import json as _pce_json
        if parsed_manifest.source_kind == "gap-witness":  # __s190_gapw_pce_refuse_v1__
            raise DossierError(
                "predetermined-change envelope refused on a coverage-gap-"
                "witness (refutation) dossier: an Article 43(4) change-"
                "envelope membership over a refutation artifact is incoherent"
            )
        pce_src = manifest.parent / "pce.json"
        if not pce_src.is_file():
            raise DossierError(
                "manifest declares a predetermined-change envelope but "
                "pce.json not found next to manifest: " + str(pce_src)
            )
        pce_bytes = pce_src.read_bytes()
        _pce_file_sha = _pce_hashlib.sha256(pce_bytes).hexdigest()
        if _pce_file_sha != parsed_manifest.pce_sha256:
            raise DossierError(
                "pce.json sha256 mismatch: file=" + _pce_file_sha[:16]
                + "... manifest=" + (parsed_manifest.pce_sha256 or "")[:16]
                + "... (predetermined-change envelope tampered or substituted)"
            )
        try:
            _pce_doc = _pce_json.loads(pce_bytes.decode("utf-8"))
        except Exception as _pce_e:
            raise DossierError("pce.json parse error: " + str(_pce_e))
        _pce_base_sha = _pce_doc.get("baseline_canon_sha256")
        if not isinstance(_pce_base_sha, str) or len(_pce_base_sha) != 64:
            raise DossierError(
                "pce.json baseline_canon_sha256 missing or not a 64-hex sha256"
            )
        baseline_src = manifest.parent / "baseline.canon"
        if not baseline_src.is_file():
            raise DossierError(
                "pce.json commits to a baseline obligations canon but "
                "baseline.canon not found next to manifest: " + str(baseline_src)
            )
        baseline_canon_bytes = baseline_src.read_bytes()
        _pce_base_file_sha = _pce_hashlib.sha256(baseline_canon_bytes).hexdigest()
        if _pce_base_file_sha != _pce_base_sha:
            raise DossierError(
                "baseline.canon sha256 mismatch: file=" + _pce_base_file_sha[:16]
                + "... pce.baseline_canon_sha256=" + _pce_base_sha[:16]
                + "... (committed baseline canon tampered or substituted)"
            )
        spec_canon_bytes = spec.canonical_str().encode("utf-8")
    if parsed_manifest.pce_anchor_sha256 is not None:  # __s191_pce_anchor_carry_read_v1__
        import hashlib as _pa_hashlib_s191
        if parsed_manifest.pce_sha256 is None:
            raise DossierError(
                "manifest declares pce_anchor_sha256 but no pce_sha256; a "
                "pre-commitment receipt cannot be carried without the "
                "predetermined-change envelope it anchors"
            )
        pce_anchor_src = manifest.parent / "pce.anchor.json"
        if not pce_anchor_src.is_file():
            raise DossierError(
                "manifest declares a pre-commitment receipt but "
                "pce.anchor.json not found next to manifest: "
                + str(pce_anchor_src)
            )
        _pce_anchor_bytes = pce_anchor_src.read_bytes()
        _pce_anchor_file_sha = _pa_hashlib_s191.sha256(
            _pce_anchor_bytes
        ).hexdigest()
        if _pce_anchor_file_sha != parsed_manifest.pce_anchor_sha256:
            raise DossierError(
                "pce.anchor.json sha256 mismatch: file="
                + _pce_anchor_file_sha[:16] + "... manifest="
                + (parsed_manifest.pce_anchor_sha256 or "")[:16]
                + "... (pre-commitment receipt tampered or substituted)"
            )
    _closure_witness_bytes = None  # __s208_closure_witness_carry_read_v1__
    if parsed_manifest.closure_witness_sha256 is not None:
        import hashlib as _cw_hashlib_s208
        _cw_src = manifest.parent / "closure.witness.json"
        if not _cw_src.is_file():
            raise DossierError(
                "manifest declares a closure witness but "
                "closure.witness.json not found next to manifest: "
                + str(_cw_src)
            )
        _closure_witness_bytes = _cw_src.read_bytes()
        _cw_file_sha = _cw_hashlib_s208.sha256(
            _closure_witness_bytes
        ).hexdigest()
        if _cw_file_sha != parsed_manifest.closure_witness_sha256:
            raise DossierError(
                "closure.witness.json sha256 mismatch: file="
                + _cw_file_sha[:16] + "... manifest="
                + (parsed_manifest.closure_witness_sha256 or "")[:16]
                + "... (closure witness evidence tampered or "
                "substituted)"
            )
    if parsed_manifest.envelope_witness_sha256 is not None:  # __s194_envelope_witness_carry_read_v1__
        import hashlib as _ew_hashlib_s194
        witness_src = manifest.parent / "envelope.witness.json"
        if not witness_src.is_file():
            raise DossierError(
                "manifest declares an envelope witness quorum but "
                "envelope.witness.json not found next to manifest: "
                + str(witness_src)
            )
        _envelope_witness_bytes = witness_src.read_bytes()
        _ew_file_sha = _ew_hashlib_s194.sha256(
            _envelope_witness_bytes
        ).hexdigest()
        if _ew_file_sha != parsed_manifest.envelope_witness_sha256:
            raise DossierError(
                "envelope.witness.json sha256 mismatch: file="
                + _ew_file_sha[:16] + "... manifest="
                + (parsed_manifest.envelope_witness_sha256 or "")[:16]
                + "... (envelope witness evidence tampered or "
                "substituted)"
            )
    gap_witness_bytes = None  # __s134_gapw_consume_v1__
    if parsed_manifest.source_kind == "gap-witness":
        _gw_expected = parsed_manifest.gap_witness_sha256
        gw_src = manifest.parent / "coverage.gapwitness.json"
        if not gw_src.is_file():
            raise DossierError(
                "manifest declares source_kind gap-witness but "
                "coverage.gapwitness.json not found next to "
                "manifest: " + str(gw_src)
            )
        gap_witness_bytes = gw_src.read_bytes()
        _gw_file_sha = hashlib.sha256(gap_witness_bytes).hexdigest()
        if _gw_file_sha != _gw_expected:
            raise DossierError(
                "coverage.gapwitness.json sha256 mismatch: file="
                + _gw_file_sha[:16] + "... manifest="
                + str(_gw_expected or "")[:16]
                + "... (gap-witness tampered or substituted)"
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

    chain_links: list[tuple[bytes, "bytes | None"]] = []  # __s120_chain_carry_v1__ __s121_chain_carry_sidecars_v1__ __s121_revert_monotonic_carry_v1__
    _hop_docs: list[tuple[int, bytes]] = []  # __s126_hop_issuance_v1__
    _net_docs: list[tuple[int, bytes]] = []  # __s127_net_issuance_v1__
    _net_source_docs: list[tuple[int, bytes]] = []  # __s127_net_issuance_v1__
    _prior_digest = parsed_manifest.prior_digest
    if _prior_digest is not None and anchor != "none":  # __s120_chain_refuse_hoist_v1__
        raise DossierError(
            "chain + rekor anchor not yet supported: a re-binding "
            "dossier (prior_digest set) cannot currently be anchored; "
            "rebuild the current envelope with --anchor none"
        )
    # __s126_hop_gate_lift_v1__ boolean-threshold chain gate removed:
    # hop containment is proven by a Farkas bundle per hop (S126).
    if (parsed_manifest.source_kind == "gap-witness"  # __s134_gapw_consume_v1__
            and _prior_digest is not None):
        raise DossierError(
            "source_kind is gap-witness but the manifest also "
            "declares prior_digest; a coverage-gap-witness is a "
            "standalone refutation artifact with no chain semantics "
            "(refuse over silently dropping the chain)"
        )
    if (parsed_manifest.source_kind == "gap-witness"
            and anchor != "none"):  # __s134_gapw_consume_v1__
        raise DossierError(
            "source_kind is gap-witness but a rekor anchor was "
            "requested; the gap-witness verifier checks an Ed25519 "
            "manifest signature only and would never inspect a "
            "transparency-log anchor (refuse over a silent merge); "
            "rebuild with --anchor none"
        )
    if _prior_digest is None and supersedes is not None:
        raise DossierError(
            "--supersedes given but the current manifest declares no "
            "prior_digest; the producer did not record a re-binding "
            "(run `nous verify --smt --supersedes <prior manifest>` first)"
        )
    if _prior_digest is not None and supersedes is None:
        raise DossierError(
            "manifest declares prior_digest "
            + str(_prior_digest)[:16]
            + "... but no --supersedes predecessor dossier was given; "
            "the chain of prior manifests cannot be built"
        )
    _full_mode_s127 = (  # __s127_net_issuance_v1__
        parsed_manifest.chain_coverage_mode == "blocking-net-full"
    )
    if _full_mode_s127 and _prior_digest is None:
        raise DossierError(
            "chain_coverage_mode is blocking-net-full but the "
            "manifest declares no prior_digest; full-mode "
            "coverage requires a re-binding chain (there is no "
            "blocking net to contain at genesis)"
        )
    if _prior_digest is not None and supersedes is not None:
        pred_dir = Path(supersedes).resolve()
        if not pred_dir.is_dir():
            raise DossierError(
                "--supersedes is not a directory: " + str(pred_dir)
            )
        pred_manifest_path = pred_dir / "manifest.json"
        if not pred_manifest_path.is_file():
            raise DossierError(
                "predecessor dossier has no manifest.json: "
                + str(pred_manifest_path)
            )
        pred_text = pred_manifest_path.read_text(encoding="utf-8")
        try:
            pred_parsed, pred_sig, pred_pub = parse_manifest_json(pred_text)
        except Exception as e:
            raise DossierError(
                "cannot parse predecessor manifest "
                + str(pred_manifest_path) + ": " + str(e)
            )
        if not verify_manifest_signature(pred_parsed, pred_sig, pred_pub):
            raise DossierError(
                "predecessor manifest " + str(pred_manifest_path)
                + " Ed25519 signature does NOT verify; refusing to chain "
                "onto a non-authentic predecessor"
            )
        pred_digest = hashlib.sha256(
            pred_parsed.canonical_bytes()
        ).hexdigest()
        if pred_digest != _prior_digest:
            raise DossierError(
                "self-consistency: --supersedes points at a dossier whose "
                "manifest canonical digest=" + pred_digest[:16]
                + "... does not equal the prior_digest="
                + str(_prior_digest)[:16]
                + "... declared by the producer in the current manifest"
            )
        pred_chain_dir = pred_dir / "chain"
        if pred_chain_dir.is_dir():  # __s121_chain_carry_sidecars_v1__
            prior_links = sorted(
                pred_chain_dir.glob("*_manifest.json")
            )
            for link_path in prior_links:
                _far = link_path.parent / link_path.name.replace(
                    "_manifest.json", "_coverage.farkas.json"
                )
                chain_links.append((
                    link_path.read_bytes(),
                    _far.read_bytes() if _far.is_file() else None,
                ))
        _pred_far = pred_dir / "coverage.farkas.json"
        chain_links.append((
            pred_manifest_path.read_bytes(),
            _pred_far.read_bytes() if _pred_far.is_file() else None,
        ))
        _any_bundle_s126 = (  # __s126_hop_issuance_v1__
            (coverage_farkas_bytes is not None
             and _is_bundle_farkas(coverage_farkas_bytes))
            or any(
                _fb_b is not None and _is_bundle_farkas(_fb_b)
                for _mb_b, _fb_b in chain_links
            )
        )
        if _any_bundle_s126:
            import json as _json_s126
            from coverage_farkas import FarkasError as _FarkasError_s126
            from coverage_farkas import (
                serialize_hop_bundle as _ser_hop_s126,
            )
            from coverage_minilang import (
                MinilangError as _MinilangError_s126,
            )
            from coverage_minilang import ml_parse as _ml_parse_s126

            def _link_threshold_expr_s126(
                mb: bytes, fb: "bytes | None", label: str
            ) -> "str | None":
                try:
                    _mdoc = _json_s126.loads(mb.decode("utf-8"))
                except Exception as e:
                    raise DossierError(
                        "chain link " + label + " manifest parse error: "
                        + str(e)
                    )
                _field = _mdoc.get("coverage_farkas_sha256")
                if _field is None:
                    if fb is not None:
                        raise DossierError(
                            "chain link " + label + " declares no "
                            "coverage_farkas_sha256 but carries a Farkas "
                            "sidecar (unexpected evidence)"
                        )
                    return None
                if fb is None:
                    raise DossierError(
                        "chain link " + label + " declares "
                        "coverage_farkas_sha256 but its Farkas sidecar "
                        "is missing (truncated predecessor dossier)"
                    )
                if hashlib.sha256(fb).hexdigest() != _field:
                    raise DossierError(
                        "chain link " + label + " Farkas sidecar sha256 "
                        "does not match its manifest (tampered or "
                        "substituted)"
                    )
                try:
                    _fdoc = _json_s126.loads(fb.decode("utf-8"))
                except Exception as e:
                    raise DossierError(
                        "chain link " + label + " Farkas sidecar parse "
                        "error: " + str(e)
                    )
                _expr = (
                    _fdoc.get("threshold_expr")
                    if isinstance(_fdoc, dict) else None
                )
                if not isinstance(_expr, str) or not _expr:
                    raise DossierError(
                        "chain link " + label + " Farkas artifact "
                        "carries no threshold_expr; the hop containment "
                        "obligation cannot be derived"
                    )
                return _expr

            _exprs_s126: "list[str | None]" = [
                _link_threshold_expr_s126(
                    _mb_h, _fb_h, str(_ih).zfill(3)
                )
                for _ih, (_mb_h, _fb_h) in enumerate(chain_links)
            ]
            if parsed_manifest.coverage_farkas_sha256 is not None:
                try:
                    _cur_fdoc_s126 = _json_s126.loads(
                        coverage_farkas_bytes.decode("utf-8")
                    )
                except Exception as e:
                    raise DossierError(
                        "current coverage.farkas.json parse error: "
                        + str(e)
                    )
                _cur_expr_s126 = (
                    _cur_fdoc_s126.get("threshold_expr")
                    if isinstance(_cur_fdoc_s126, dict) else None
                )
                if (not isinstance(_cur_expr_s126, str)
                        or not _cur_expr_s126):
                    raise DossierError(
                        "current Farkas artifact carries no "
                        "threshold_expr; hop containment obligations "
                        "cannot be derived"
                    )
                _exprs_s126.append(_cur_expr_s126)
            else:
                _exprs_s126.append(None)
            for _hi in range(1, len(_exprs_s126)):
                _e_prev_s126 = _exprs_s126[_hi - 1]
                _e_cur_s126 = _exprs_s126[_hi]
                if _e_prev_s126 is not None and _e_cur_s126 is None:
                    raise DossierError(
                        "coverage VANISHED at hop "
                        + str(_hi - 1).zfill(3)
                        + ": the predecessor declares a coverage proof "
                        "but the successor drops it; the emitted chain "
                        "verifier would refuse the dossier it ships with"
                    )
                if _e_prev_s126 is None or _e_cur_s126 is None:
                    continue
                try:
                    _hop_doc_s126 = _ser_hop_s126(
                        _ml_parse_s126(_e_prev_s126),
                        _ml_parse_s126(_e_cur_s126),
                        prev_expr=_e_prev_s126,
                        cur_expr=_e_cur_s126,
                    )
                except (_FarkasError_s126, _MinilangError_s126) as e:
                    raise DossierError(
                        "hop containment REFUSED at hop "
                        + str(_hi - 1).zfill(3) + ": " + str(e)
                    )
                _hop_docs.append((
                    _hi - 1,
                    _json_s126.dumps(
                        _hop_doc_s126,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8"),
                ))

        if _full_mode_s127:  # __s127_net_issuance_v1__
            import json as _json_s127
            from coverage_farkas import (
                FarkasError as _FE_s127,
            )
            from coverage_farkas import (
                serialize_net_bundle as _ser_net_s127,
            )
            from coverage_minilang import (
                MinilangError as _ME_s127,
            )
            from coverage_minilang import (
                ml_scan_blocking_signals as _scan_s127,
            )
            _chain_sources_s127: list[bytes] = []
            if pred_chain_dir.is_dir():
                for _lp_s127 in sorted(
                    pred_chain_dir.glob("*_manifest.json")
                ):
                    _ps_s127 = _lp_s127.parent / _lp_s127.name.replace(
                        "_manifest.json", "_source.nous"
                    )
                    if not _ps_s127.is_file():
                        raise DossierError(
                            "--chain-coverage full requires per-link "
                            "source carry, but predecessor link "
                            + _ps_s127.name
                            + " has no source.nous; the predecessor "
                            "was not built with --chain-coverage "
                            "full (a full-mode chain must be full "
                            "from its first full link)"
                        )
                    _chain_sources_s127.append(
                        _ps_s127.read_bytes()
                    )
            _pred_src_s127 = pred_dir / "source.nous"
            if not _pred_src_s127.is_file():
                raise DossierError(
                    "predecessor dossier has no source.nous; "
                    "cannot carry per-link source for a full-mode "
                    "chain"
                )
            _chain_sources_s127.append(
                _pred_src_s127.read_bytes()
            )
            if len(_chain_sources_s127) != len(chain_links):
                raise DossierError(
                    "internal: full-mode source carry count "
                    + str(len(_chain_sources_s127))
                    + " != chain link count "
                    + str(len(chain_links))
                )
            for _idx_s127, _sb_s127 in enumerate(
                _chain_sources_s127
            ):
                _net_source_docs.append((_idx_s127, _sb_s127))
            _src_seq_s127 = _chain_sources_s127 + [source_bytes]
            for _ni_s127 in range(1, len(_src_seq_s127)):
                try:
                    _pv_s127 = _scan_s127(
                        _src_seq_s127[_ni_s127 - 1].decode("utf-8")
                    )
                    _cv_s127 = _scan_s127(
                        _src_seq_s127[_ni_s127].decode("utf-8")
                    )
                    _net_doc_s127 = _ser_net_s127(
                        _pv_s127, _cv_s127
                    )
                except (_FE_s127, _ME_s127) as e:
                    raise DossierError(
                        "blocking-net containment REFUSED at hop "
                        + str(_ni_s127 - 1).zfill(3)
                        + ": " + str(e)
                        + " (the emitted full-mode verifier would "
                        "refuse the dossier it ships with)"
                    )
                _net_docs.append((
                    _ni_s127 - 1,
                    _json_s127.dumps(
                        _net_doc_s127,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8"),
                ))

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
    elif anchor == "rekor_v2":
        # __nous_s93_dossier_rekor_v2_emit_v1__
        if _test_rekor_anchor_v2 is not None:
            rekor_anchor_obj = _test_rekor_anchor_v2
        else:
            import json as _json
            from rekor_anchor_v2 import anchor_manifest_to_rekor_v2
            from rekor_entry import parse_rekor_leaf
            from tsa_client import anchor_timestamp
            v2_anchor = anchor_manifest_to_rekor_v2(
                manifest_canonical_bytes=parsed_manifest.canonical_bytes(),
            )
            leaf = parse_rekor_leaf(
                _json.loads(
                    base64.b64decode(v2_anchor.body_b64, validate=True)
                )
            )
            token_der = anchor_timestamp(
                timestamped_data=leaf.leaf_signature_der,
            )
            # __nous_s93_dossier_rekor_v2_token_reconstruct_v1__
            rekor_anchor_obj = type(v2_anchor)(
                rekor_api_version=v2_anchor.rekor_api_version,
                log_id=v2_anchor.log_id,
                log_index=v2_anchor.log_index,
                body_b64=v2_anchor.body_b64,
                checkpoint_envelope=v2_anchor.checkpoint_envelope,
                inclusion_proof_hashes=list(
                    v2_anchor.inclusion_proof_hashes
                ),
                rfc3161_token_b64=base64.b64encode(
                    token_der
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
            f"(expected 'none', 'rekor', or 'rekor_v2')"
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

    if chain_links:  # __s120_chain_carry_v1__ __s121_chain_carry_sidecars_v1__
        chain_dir = output / "chain"
        chain_dir.mkdir(parents=True, exist_ok=True)
        for idx, (_mb, _fb) in enumerate(chain_links):
            _base = "chain/" + str(idx).zfill(3)
            _mn = _base + "_manifest.json"
            (output / _mn).write_bytes(_mb)
            files.append(_mn)
            if _fb is not None:
                _fn = _base + "_coverage.farkas.json"
                (output / _fn).write_bytes(_fb)
                files.append(_fn)
        for _hop_idx_w, _hop_bytes_w in _hop_docs:  # __s126_hop_emit_v1__
            _hop_name_w = (
                "chain/" + str(_hop_idx_w).zfill(3) + "_hop.farkas.json"
            )
            (output / _hop_name_w).write_bytes(_hop_bytes_w)
            files.append(_hop_name_w)
        for _nsi_w, _nsb_w in _net_source_docs:  # __s127_net_emit_v1__
            _nsn_w = (
                "chain/" + str(_nsi_w).zfill(3) + "_source.nous"
            )
            (output / _nsn_w).write_bytes(_nsb_w)
            files.append(_nsn_w)
        for _ndi_w, _ndb_w in _net_docs:  # __s127_net_emit_v1__
            _ndn_w = (
                "chain/" + str(_ndi_w).zfill(3) + "_net.farkas.json"
            )
            (output / _ndn_w).write_bytes(_ndb_w)
            files.append(_ndn_w)

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

    if coverage_smt2_bytes is not None:  # __s115_dossier_coverage_v1__
        (output / "coverage.smt2").write_bytes(coverage_smt2_bytes)
        files.append("coverage.smt2")
    if coverage_farkas_bytes is not None:  # __s116_dossier_farkas_v1__
        (output / "coverage.farkas.json").write_bytes(coverage_farkas_bytes)
        files.append("coverage.farkas.json")
    if cost_farkas_bytes is not None:  # __s170_leg2_cost_carry_v1__
        (output / "cost.farkas.json").write_bytes(cost_farkas_bytes)
        files.append("cost.farkas.json")
    if materiality_bytes is not None:  # __s171_materiality_carry_write_v1__
        (output / "materiality.json").write_bytes(materiality_bytes)
        files.append("materiality.json")
    if pce_bytes is not None:  # __s190_pce_carry_write_v1__
        (output / "pce.json").write_bytes(pce_bytes)
        files.append("pce.json")
        (output / "baseline.canon").write_bytes(baseline_canon_bytes)
        files.append("baseline.canon")
        (output / "spec.canon").write_bytes(spec_canon_bytes)
        files.append("spec.canon")
    if _pce_anchor_bytes is not None:  # __s191_pce_anchor_carry_write_v1__
        (output / "pce.anchor.json").write_bytes(_pce_anchor_bytes)
        files.append("pce.anchor.json")
    if _envelope_witness_bytes is not None:  # __s194_envelope_witness_carry_write_v1__
        (output / "envelope.witness.json").write_bytes(
            _envelope_witness_bytes
        )
        files.append("envelope.witness.json")
    if _closure_witness_bytes is not None:  # __s208_closure_witness_carry_write_v1__
        (output / "closure.witness.json").write_bytes(
            _closure_witness_bytes
        )
        files.append("closure.witness.json")
    if gap_witness_bytes is not None:  # __s134_gapw_consume_v1__
        (output / "coverage.gapwitness.json").write_bytes(
            gap_witness_bytes
        )
        files.append("coverage.gapwitness.json")

    verify_path = output / "verify_offline.py"
    if parsed_manifest.source_kind == "gap-witness":  # __s134_gapw_consume_v1__
        if annex_iv_map:  # __s135_annex_iv_emit_v1__
            raise DossierError(
                "--annex-iv-map refused on a coverage-gap-witness "
                "(refutation) dossier: an Annex IV evidence index "
                "over a refutation artifact is incoherent"
            )
        verify_path.write_text(
            build_gap_witness_verifier(), encoding="utf-8"
        )
        verify_path.chmod(0o755)
        files.append("verify_offline.py")
        return DossierResult(
            output_dir=output,
            files=tuple(files),
            world_name=parsed_manifest.world_name,
            verdict=parsed_manifest.verdict,
            safety_margin_pct=parsed_manifest.safety_margin_pct,
        )
    verify_path = output / "verify_offline.py"
    _any_bundle_link = (
        (
            coverage_farkas_bytes is not None
            and _is_bundle_farkas(coverage_farkas_bytes)
        )
        or any(
            _fb_s is not None and _is_bundle_farkas(_fb_s)
            for _mb_s, _fb_s in chain_links
        )
    )  # __s125_chain_bundle_select_v1__
    if (parsed_manifest.prior_digest is not None
            and parsed_manifest.chain_coverage_mode
            == "blocking-net-full"):  # __s127_net_select_v1__
        verify_path.write_text(
            build_chain_net_verifier(), encoding="utf-8"
        )
    elif (parsed_manifest.prior_digest is not None
            and _any_bundle_link):  # __s125_chain_bundle_select_v1__
        verify_path.write_text(
            VERIFY_OFFLINE_PY_CHAIN_BUNDLE, encoding="utf-8"
        )
    elif parsed_manifest.prior_digest is not None:  # __s120_chain_verifier_v1__ __s120_chain_refuse_hoist_v1__
        verify_path.write_text(
            VERIFY_OFFLINE_PY_CHAIN, encoding="utf-8"
        )
    elif (coverage_farkas_bytes is not None and anchor == "none"
            and _is_bundle_farkas(coverage_farkas_bytes)):  # __s124_dossier_bundle_v1__
        verify_path.write_text(
            VERIFY_OFFLINE_PY_BUNDLE, encoding="utf-8"
        )
    elif coverage_farkas_bytes is not None and anchor == "none":  # __s116_dossier_farkas_v1__
        verify_path.write_text(
            VERIFY_OFFLINE_PY_FARKAS, encoding="utf-8"
        )
    elif coverage_smt2_bytes is not None and anchor == "none":  # __s115_dossier_coverage_v1__
        verify_path.write_text(
            VERIFY_OFFLINE_PY_COVERAGE, encoding="utf-8"
        )
    elif anchor == "rekor":
        verify_path.write_text(
            VERIFY_OFFLINE_PY_WITH_REKOR, encoding="utf-8"
        )
    elif anchor == "rekor_v2":
        # __nous_s93_dossier_rekor_v2_verifier_v1__
        from offline_verifier_builder import build_offline_verifier_v2
        from rekor_verify_v2 import KNOWN_REKOR_V2_LOG_KEYS
        verify_path.write_text(
            build_offline_verifier_v2(repr(KNOWN_REKOR_V2_LOG_KEYS)),
            encoding="utf-8",
        )
    else:
        verify_path.write_text(VERIFY_OFFLINE_PY, encoding="utf-8")
    if parsed_manifest.materiality_sha256 is not None:  # __s171_materiality_splice_v1__
        verify_path.write_text(
            _splice_materiality_check(
                verify_path.read_text(encoding="utf-8")
            ),
            encoding="utf-8",
        )
    if parsed_manifest.pce_sha256 is not None:  # __s190_pce_splice_v1__
        verify_path.write_text(
            _splice_pce_check(
                verify_path.read_text(encoding="utf-8")
            ),
            encoding="utf-8",
        )
    if parsed_manifest.pce_anchor_sha256 is not None:  # __s191_pce_anchor_splice_v1__
        verify_path.write_text(
            _splice_pce_anchor_check(
                verify_path.read_text(encoding="utf-8")
            ),
            encoding="utf-8",
        )
    if parsed_manifest.envelope_witness_sha256 is not None:  # __s194_envelope_witness_splice_v1__
        verify_path.write_text(
            _splice_envelope_witness_check(
                verify_path.read_text(encoding="utf-8")
            ),
            encoding="utf-8",
        )
    if parsed_manifest.closure_witness_sha256 is not None:  # __s208_closure_witness_splice_v1__
        verify_path.write_text(
            _splice_closure_witness_check(
                verify_path.read_text(encoding="utf-8")
            ),
            encoding="utf-8",
        )
    if parsed_manifest.attribution is not None:  # __s180_attribution_splice_v1__
        verify_path.write_text(
            _splice_attribution_check(
                verify_path.read_text(encoding="utf-8")
            ),
            encoding="utf-8",
        )
    verify_path.chmod(0o755)
    files.append("verify_offline.py")

    if annex_iv_map:  # __s135_annex_iv_emit_v1__
        from manifest import load_or_create_keypair
        from annex_iv_map import (
            build_annex_iv_map,
            build_annex_iv_verifier,
            serialize_annex_iv_map,
        )
        _aiv_priv, _aiv_pub, _aiv_kp = load_or_create_keypair(
            annex_iv_key_path
        )
        _aiv_doc = build_annex_iv_map(output, _aiv_priv)
        (output / "annex_iv_map.json").write_text(
            serialize_annex_iv_map(_aiv_doc), encoding="utf-8"
        )
        files.append("annex_iv_map.json")
        _aiv_verify = output / "verify_annex_iv_map.py"
        _aiv_verify.write_text(
            build_annex_iv_verifier(), encoding="utf-8"
        )
        _aiv_verify.chmod(0o755)
        files.append("verify_annex_iv_map.py")

    return DossierResult(
        output_dir=output,
        files=tuple(files),
        world_name=parsed_manifest.world_name,
        verdict=parsed_manifest.verdict,
        safety_margin_pct=parsed_manifest.safety_margin_pct,
    )


VERIFY_OFFLINE_PY_CHAIN_BUNDLE: str = '#!/usr/bin/env python3\n"""Offline verification of NOUS dossier (Annex IV): an envelope-binding\nchain whose CURRENT link carries a coverage proof that may be a Farkas DNF\nbundle (boolean blocking net) or a v1 single-comparison Farkas certificate.\n\nUsage: python3 verify_offline.py\nExit:  0 = PASS, 1 = FAIL, 2 = environment error.\n\nRequires: cryptography (Ed25519 author signatures). The coverage claim is\nchecked by RATIONAL ARITHMETIC ALONE (fractions, stdlib): a Farkas DNF\nbundle is verified by RE-DERIVING the gap disjunct set from the SIGNED\nsource.nous and the sha-gated threshold expression, requiring a bijection\nagainst the carried certificates and checking every multiplier; a v1\ncertificate is verified directly. No solver is required; z3 is an optional\nsecond opinion only. The chain walk uses cryptography + stdlib only.\n\nThis verifier proves the CURRENT link\'s coverage claim with zero issuer\ntrust and zero solver trust, and verifies an unbroken sequence of\nsignature-valid formation envelopes, each declaring its predecessor by\ndigest, each a real build change, rooted at genesis. Across hops it asserts\ncoverage-region MONOTONICITY by hop-containment Farkas bundles: per hop,\nregion(T_prev) subset-of region(T_cur) is proven by refuting every DNF\ndisjunct of T_prev AND NOT(T_cur), where both threshold expressions are\nread from the two links\' sha-gated Farkas sidecars (never from the hop\nbundle) and the disjunct set is RE-DERIVED independently. Boolean\nthresholds are admitted. It does NOT re-prove PRIOR links\' coverage\ncompleteness (no per-link source is carried), does NOT prove execution\nconformance, and does NOT prove the latest envelope is safer.\n\nChecks, in order, fail-closed:\n  1. Ed25519 signature over the current manifest\'s canonical body bytes.\n  2. source.nous sha256 == manifest.source_sha256.\n  3. Current-link coverage: a bundle (re-derive disjuncts from the signed\n     source, bijection, per-disjunct multiplier check) or a v1 certificate,\n     each gated by an O(1) coverage.farkas.json sha match; optional z3\n     second opinion on coverage.smt2.\n  4. Chain walk over chain/ (prior manifests only), six fail-closed\n     conditions: per-link signature, missing chain, altered link, truncated\n     / no-genesis, no-op re-binding, and cycle / more-than-one-genesis.\n  5. Coverage-region monotonicity: per hop where both links declare\n     coverage, region containment is proven by a hop-containment Farkas\n     bundle (chain/NNN_hop.farkas.json): the obligation is re-derived\n     from the two sha-gated threshold expressions, a bijection is\n     required, and every disjunct is refuted by rational arithmetic.\n     Boolean thresholds are admitted.\n  __s125_chain_bundle_walk_v1__ __s126_hop_walk_v1__\n"""\nfrom __future__ import annotations\n\nimport base64\nimport hashlib\nimport json\nimport sys\nfrom pathlib import Path\n\nROOT = Path(__file__).parent\n\n_SHA_BEARING_FIELDS = (\n    "source_sha256",\n    "pricing_sha256",\n    "smt_spec_sha256",\n    "cost_cap_usd",\n    "max_ticks",\n)\n\n\ndef _fail(msg):\n    print("FAIL: " + msg, file=sys.stderr)\n    return 1\n\n\ndef _canonical_body_bytes(m):\n    body = {\n        k: v for k, v in m.items()\n        if k not in ("signature", "transparency_log")\n    }\n    return json.dumps(\n        body, sort_keys=True, separators=(",", ":")\n    ).encode("utf-8")\n\n\ndef _verify_link_signature(link, label):\n    from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n        Ed25519PublicKey,\n    )\n    from cryptography.exceptions import InvalidSignature\n\n    sig_block = link.get("signature")\n    if not isinstance(sig_block, dict):\n        return _fail(label + " has no signature block")\n    pub_b64 = sig_block.get("public_key_b64", "")\n    sig_b64 = sig_block.get("signature_b64", "")\n    if not pub_b64 or not sig_b64:\n        return _fail(label + " signature block incomplete")\n    body_bytes = _canonical_body_bytes(link)\n    try:\n        pub_key = Ed25519PublicKey.from_public_bytes(\n            base64.b64decode(pub_b64)\n        )\n        pub_key.verify(base64.b64decode(sig_b64), body_bytes)\n    except InvalidSignature:\n        return _fail(label + " Ed25519 signature does NOT verify")\n    except Exception as e:\n        return _fail(label + " signature verification error: " + str(e))\n    return 0\n\n\n' + _MINILANG_CORE_EMBED + '\n\n\n# --- farkas embed (shared text; mirrors coverage_farkas.py exactly) ---\n# Standalone copies of the linear-translation, NNF/DNF, canonical-form,\n# and multiplier-check logic from coverage_farkas.py. fractions only.\n# __s124_farkas_embed_v1__\n\nfrom fractions import Fraction\n\n\nclass FarkasError(ValueError):\n    pass\n\n\nclass LinIneq:\n    def __init__(self, coeffs, strict):\n        self.coeffs = coeffs\n        self.strict = strict\n\n\nDISJUNCT_BOUND = 64\n\n_FLIP_OP = {">": "<=", ">=": "<", "<": ">=", "<=": ">"}\n\n_CMP_OPS = (">", ">=", "<", "<=")\n\n\ndef _num(node):\n    if isinstance(node, bool):\n        return None\n    if isinstance(node, int):\n        return Fraction(node)\n    if isinstance(node, float):\n        return Fraction(node).limit_denominator(10 ** 12)\n    if isinstance(node, dict) and "currency" in node and "amount" in node:\n        return _num(node["amount"])\n    return None\n\n\ndef _linear(node):\n    n = _num(node)\n    if n is not None:\n        return {"": n}\n    if isinstance(node, str):\n        if node[:1] in (\'"\', "\'"):\n            raise FarkasError("string literal outside fragment")\n        return {node: Fraction(1), "": Fraction(0)}\n    if isinstance(node, dict) and node.get("kind") == "binop":\n        op = node.get("op")\n        if op == "+":\n            return _add(_linear(node["left"]), _linear(node["right"]), 1)\n        if op == "-":\n            return _add(_linear(node["left"]), _linear(node["right"]), -1)\n        if op == "*":\n            return _linear_mul(\n                _linear(node["left"]), _linear(node["right"])\n            )\n        raise FarkasError("non-linear operator " + repr(op) + " in term")\n    raise FarkasError(\n        "unsupported term node " + repr(type(node).__name__)\n    )\n\n\ndef _add(a, b, sign):\n    out = dict(a)\n    for k, v in b.items():\n        out[k] = out.get(k, Fraction(0)) + sign * v\n    return out\n\n\ndef _scale(a, s):\n    return {k: v * s for k, v in a.items()}\n\n\ndef _is_const_only(d):\n    return all(k == "" for k in d)\n\n\ndef _linear_mul(a, b):\n    a_const = _is_const_only(a)\n    b_const = _is_const_only(b)\n    if a_const and b_const:\n        return {"": a.get("", Fraction(0)) * b.get("", Fraction(0))}\n    if a_const:\n        return _scale(b, a.get("", Fraction(0)))\n    if b_const:\n        return _scale(a, b.get("", Fraction(0)))\n    raise FarkasError(\n        "bilinear term (variable * variable) outside linear real "\n        "arithmetic (QF_LRA); only constant * variable is admitted"\n    )\n\n\ndef _comparison_to_ineq(node):\n    if not (isinstance(node, dict) and node.get("kind") == "binop"):\n        raise FarkasError("signal is not a single comparison")\n    op = node.get("op")\n    if op not in _CMP_OPS:\n        raise FarkasError(\n            "comparison op " + repr(op) + " outside fragment"\n        )\n    left = _linear(node["left"])\n    right = _linear(node["right"])\n    diff = _add(left, right, -1)\n    if op in ("<", "<="):\n        return LinIneq(coeffs=diff, strict=(op == "<"))\n    return LinIneq(coeffs=_scale(diff, Fraction(-1)), strict=(op == ">"))\n\n\ndef _is_comparison(node):\n    return (\n        isinstance(node, dict)\n        and node.get("kind") == "binop"\n        and node.get("op") in _CMP_OPS\n    )\n\n\ndef _nnf(node, negate):\n    if _is_comparison(node):\n        if not negate:\n            return node\n        flipped = dict(node)\n        flipped["op"] = _FLIP_OP[node["op"]]\n        return flipped\n    if isinstance(node, dict) and node.get("kind") == "not":\n        return _nnf(node["operand"], not negate)\n    if (\n        isinstance(node, dict)\n        and node.get("kind") == "binop"\n        and node.get("op") in ("&&", "and", "||", "or")\n    ):\n        is_and = node.get("op") in ("&&", "and")\n        if negate:\n            is_and = not is_and\n        return {\n            "kind": "binop",\n            "op": "&&" if is_and else "||",\n            "left": _nnf(node["left"], negate),\n            "right": _nnf(node["right"], negate),\n        }\n    raise FarkasError(\n        "signal node outside the disjunctive linear fragment: "\n        + repr(node)\n    )\n\n\ndef _dnf(node, bound):\n    if _is_comparison(node):\n        return [[node]]\n    if isinstance(node, dict) and node.get("kind") == "binop":\n        op = node.get("op")\n        if op == "||":\n            out = _dnf(node["left"], bound) + _dnf(node["right"], bound)\n            if len(out) > bound:\n                raise FarkasError(\n                    "DNF disjunct count exceeds bound " + str(bound)\n                )\n            return out\n        if op == "&&":\n            left = _dnf(node["left"], bound)\n            right = _dnf(node["right"], bound)\n            if len(left) * len(right) > bound:\n                raise FarkasError(\n                    "DNF disjunct count exceeds bound " + str(bound)\n                )\n            return [a + b for a in left for b in right]\n    raise FarkasError("non-NNF node in DNF expansion: " + repr(node))\n\n\ndef _gap_disjuncts(threshold_ast, blocking_signals, bound):\n    conj = _nnf(threshold_ast, False)\n    for sig in blocking_signals:\n        conj = {\n            "kind": "binop",\n            "op": "&&",\n            "left": conj,\n            "right": _nnf(sig, True),\n        }\n    return _dnf(conj, bound)\n\n\ndef _canon_constraint(ineq):\n    return {\n        "coeffs": {k: str(v) for k, v in sorted(ineq.coeffs.items())},\n        "strict": bool(ineq.strict),\n    }\n\n\ndef _canon_json(obj):\n    import json\n\n    return json.dumps(obj, sort_keys=True, separators=(",", ":"))\n\n\ndef _canon_system(comparisons):\n    pairs = []\n    for comp in comparisons:\n        ineq = _comparison_to_ineq(comp)\n        pairs.append((_canon_constraint(ineq), ineq))\n    pairs.sort(key=lambda p: _canon_json(p[0]))\n    return [p[0] for p in pairs], [p[1] for p in pairs]\n\n\ndef _check_multipliers(constraints, multipliers):\n    if not isinstance(constraints, list) or not isinstance(\n        multipliers, list\n    ):\n        return False\n    if len(constraints) != len(multipliers):\n        return False\n    lam = []\n    for m in multipliers:\n        try:\n            lam.append(Fraction(m))\n        except (ValueError, TypeError, ZeroDivisionError):\n            return False\n    if any(x < 0 for x in lam):\n        return False\n    if not any(x > 0 for x in lam):\n        return False\n    combined = {}\n    strict = False\n    for x, c in zip(lam, constraints):\n        if x == 0:\n            continue\n        if not isinstance(c, dict):\n            return False\n        coeffs = c.get("coeffs")\n        if not isinstance(coeffs, dict):\n            return False\n        for k, v in coeffs.items():\n            try:\n                fv = Fraction(v)\n            except (ValueError, TypeError, ZeroDivisionError):\n                return False\n            combined[k] = combined.get(k, Fraction(0)) + x * fv\n        if c.get("strict"):\n            strict = True\n    for k, v in combined.items():\n        if k != "" and v != 0:\n            return False\n    const = combined.get("", Fraction(0))\n    if const > 0:\n        return True\n    if const == 0 and strict:\n        return True\n    return False\n\n\ndef derive_disjunct_constraints(source_text, threshold_expr):\n    """source TEXT + sha-gated threshold expression -> dict of\n    canonical-key -> canonical constraints, one entry per derived gap\n    disjunct (deduplicated). The independent reconstruction of what the\n    bundle must prove."""\n    threshold_ast = ml_parse(threshold_expr)\n    blocking = ml_scan_blocking_signals(source_text)\n    disjuncts = _gap_disjuncts(threshold_ast, blocking, DISJUNCT_BOUND)\n    derived = {}\n    for comps in disjuncts:\n        constraints, _system = _canon_system(comps)\n        derived[_canon_json(constraints)] = constraints\n    return derived\n\n\ndef check_bundle_against_derived(doc, derived):\n    """Bijection + per-disjunct multiplier check of a bundle dict\n    against an independently derived disjunct map. Returns (ok, reason)."""\n    if not isinstance(doc, dict):\n        return (False, "bundle is not a JSON object")\n    if doc.get("fragment") != "disjunctive-linear-bundle":\n        return (False, "bundle fragment is not disjunctive-linear-bundle")\n    cert_list = doc.get("certs")\n    if not isinstance(cert_list, list):\n        return (False, "bundle has no certs array")\n    carried = {}\n    for cert in cert_list:\n        if not isinstance(cert, dict):\n            return (False, "a cert is not a JSON object")\n        cons = cert.get("constraints")\n        mults = cert.get("multipliers")\n        if not isinstance(cons, list) or not isinstance(mults, list):\n            return (False, "a cert lacks constraints or multipliers")\n        norm = []\n        for c in cons:\n            if not isinstance(c, dict):\n                return (False, "a carried constraint is not an object")\n            coeffs = c.get("coeffs")\n            if not isinstance(coeffs, dict):\n                return (False, "a carried constraint has no coeffs")\n            try:\n                norm_coeffs = {\n                    str(k): str(Fraction(v))\n                    for k, v in sorted(coeffs.items())\n                }\n            except (ValueError, TypeError, ZeroDivisionError):\n                return (False, "non-rational carried coefficient")\n            norm.append(\n                {"coeffs": norm_coeffs, "strict": bool(c.get("strict"))}\n            )\n        norm.sort(key=_canon_json)\n        key = _canon_json(norm)\n        if key in carried:\n            return (False, "duplicate certificate for one disjunct")\n        carried[key] = mults\n    missing = set(derived) - set(carried)\n    surplus = set(carried) - set(derived)\n    if missing:\n        return (\n            False,\n            "bundle OMITS " + str(len(missing)) + " derived gap "\n            "disjunct(s) (overclaim-by-omission)",\n        )\n    if surplus:\n        return (\n            False,\n            "bundle carries " + str(len(surplus)) + " certificate(s) for "\n            "disjuncts that do not derive from the signed source",\n        )\n    for key, constraints in derived.items():\n        if not _check_multipliers(constraints, carried[key]):\n            return (\n                False,\n                "a certificate\'s multipliers do not collapse its derived "\n                "disjunct to a contradiction (coverage gap or forged "\n                "certificate)",\n            )\n    return (True, "")\n\n\ndef _hop_disjuncts(prev_ast, cur_ast, bound):\n    # __s126_hop_embed_v1__\n    conj = {\n        "kind": "binop",\n        "op": "&&",\n        "left": _nnf(prev_ast, False),\n        "right": _nnf(cur_ast, True),\n    }\n    return _dnf(conj, bound)\n\n\ndef check_hop_bundle(doc, prev_ast, cur_ast):\n    """Zero-trust check of a hop-containment bundle: the obligation\n    T_prev AND NOT(T_cur) is re-derived from the two authenticated\n    threshold ASTs, a bijection is required against the carried\n    certificates, and every multiplier is checked by rational\n    arithmetic. Returns (ok, reason)."""\n    if not isinstance(doc, dict):\n        return (False, "hop bundle is not a JSON object")\n    if doc.get("fragment") != "hop-containment-bundle":\n        return (False, "hop bundle fragment is not hop-containment-bundle")\n    cert_list = doc.get("certs")\n    if not isinstance(cert_list, list):\n        return (False, "hop bundle has no certs array")\n    try:\n        disjuncts = _hop_disjuncts(prev_ast, cur_ast, DISJUNCT_BOUND)\n    except FarkasError as e:\n        return (False, "hop obligation derivation refused: " + str(e))\n    derived = {}\n    for comps in disjuncts:\n        try:\n            constraints, _system = _canon_system(comps)\n        except FarkasError as e:\n            return (False, "hop obligation derivation refused: " + str(e))\n        derived[_canon_json(constraints)] = constraints\n    carried = {}\n    for cert in cert_list:\n        if not isinstance(cert, dict):\n            return (False, "a hop cert is not a JSON object")\n        cons = cert.get("constraints")\n        mults = cert.get("multipliers")\n        if not isinstance(cons, list) or not isinstance(mults, list):\n            return (False, "a hop cert lacks constraints or multipliers")\n        norm = []\n        for c in cons:\n            if not isinstance(c, dict):\n                return (False, "a carried hop constraint is not an object")\n            coeffs = c.get("coeffs")\n            if not isinstance(coeffs, dict):\n                return (False, "a carried hop constraint has no coeffs")\n            try:\n                norm_coeffs = {\n                    str(k): str(Fraction(v))\n                    for k, v in sorted(coeffs.items())\n                }\n            except (ValueError, TypeError, ZeroDivisionError):\n                return (False, "non-rational carried hop coefficient")\n            norm.append(\n                {"coeffs": norm_coeffs, "strict": bool(c.get("strict"))}\n            )\n        norm.sort(key=_canon_json)\n        key = _canon_json(norm)\n        if key in carried:\n            return (False, "duplicate hop certificate for one disjunct")\n        carried[key] = mults\n    missing = set(derived) - set(carried)\n    surplus = set(carried) - set(derived)\n    if missing:\n        return (\n            False,\n            "hop bundle OMITS " + str(len(missing)) + " derived "\n            "disjunct(s) of T_prev AND NOT(T_cur) "\n            "(overclaim-by-omission)",\n        )\n    if surplus:\n        return (\n            False,\n            "hop bundle carries " + str(len(surplus)) + " certificate(s) "\n            "for disjuncts that do not derive from the authenticated "\n            "threshold expressions",\n        )\n    for key, constraints in derived.items():\n        if not _check_multipliers(constraints, carried[key]):\n            return (\n                False,\n                "a hop certificate\'s multipliers do not collapse its "\n                "derived disjunct to a contradiction (region regression "\n                "or forged certificate)",\n            )\n    return (True, "")\n\n\n# --- end farkas embed ---\n\n\ndef _check_serialized(doc):\n    from fractions import Fraction\n\n    constraints = doc.get("constraints")\n    multipliers = doc.get("multipliers")\n    if not isinstance(constraints, list) or not isinstance(multipliers, list):\n        return False\n    if len(constraints) != len(multipliers):\n        return False\n    lam = []\n    for m in multipliers:\n        try:\n            lam.append(Fraction(m))\n        except (ValueError, TypeError, ZeroDivisionError):\n            return False\n    if any(x < 0 for x in lam):\n        return False\n    if not any(x > 0 for x in lam):\n        return False\n    combined = {}\n    strict = False\n    for x, c in zip(lam, constraints):\n        if x == 0:\n            continue\n        if not isinstance(c, dict):\n            return False\n        coeffs = c.get("coeffs")\n        if not isinstance(coeffs, dict):\n            return False\n        for k, v in coeffs.items():\n            try:\n                fv = Fraction(v)\n            except (ValueError, TypeError, ZeroDivisionError):\n                return False\n            combined[k] = combined.get(k, Fraction(0)) + x * fv\n        if c.get("strict"):\n            strict = True\n    for k, v in combined.items():\n        if k != "" and v != 0:\n            return False\n    const = combined.get("", Fraction(0))\n    if const > 0:\n        return True\n    if const == 0 and strict:\n        return True\n    return False\n\n\ndef _check_coverage(manifest, source_text):\n    farkas_expected = manifest.get("coverage_farkas_sha256")\n    smt2_expected = manifest.get("coverage_smt2_sha256")\n    cov_sha = manifest.get("policy_coverage_sha256")\n    if not cov_sha and not farkas_expected and not smt2_expected:\n        return 0\n\n    if smt2_expected:\n        smt2_path = ROOT / "coverage.smt2"\n        if not smt2_path.is_file():\n            return _fail("coverage.smt2 not found in " + str(ROOT))\n        smt2_sha = hashlib.sha256(smt2_path.read_bytes()).hexdigest()\n        if smt2_sha != smt2_expected:\n            return _fail(\n                "coverage.smt2 sha256 mismatch: file=" + smt2_sha[:16]\n                + "... manifest=" + smt2_expected[:16] + "..."\n            )\n        print(\n            "OK   coverage.smt2 sha256 matches manifest ("\n            + smt2_sha[:16] + "...)"\n        )\n\n    if farkas_expected:\n        farkas_path = ROOT / "coverage.farkas.json"\n        if not farkas_path.is_file():\n            return _fail("coverage.farkas.json not found in " + str(ROOT))\n        farkas_bytes = farkas_path.read_bytes()\n        farkas_sha = hashlib.sha256(farkas_bytes).hexdigest()\n        if farkas_sha != farkas_expected:\n            return _fail(\n                "coverage.farkas.json sha256 mismatch: file="\n                + farkas_sha[:16] + "... manifest=" + farkas_expected[:16]\n                + "... (Farkas certificate tampered or substituted)"\n            )\n        try:\n            farkas_doc = json.loads(farkas_bytes.decode("utf-8"))\n        except Exception as e:\n            return _fail("coverage.farkas.json parse error: " + str(e))\n        if isinstance(farkas_doc, dict) and farkas_doc.get(\n            "fragment"\n        ) == "disjunctive-linear-bundle":\n            threshold_expr = farkas_doc.get("threshold_expr")\n            if not isinstance(threshold_expr, str) or not threshold_expr:\n                return _fail(\n                    "bundle carries no threshold_expr; the obligation "\n                    "cannot be independently re-derived"\n                )\n            try:\n                derived = derive_disjunct_constraints(\n                    source_text, threshold_expr\n                )\n            except (MinilangError, FarkasError) as e:\n                return _fail(\n                    "independent re-derivation from the signed source "\n                    "REFUSED: " + str(e) + " (the obligation cannot be "\n                    "certified offline; treat as unverified)"\n                )\n            ok, reason = check_bundle_against_derived(farkas_doc, derived)\n            if not ok:\n                return _fail(\n                    "Farkas bundle does NOT prove coverage: " + reason\n                )\n            print(\n                "OK   Farkas bundle verified by rational arithmetic, no "\n                "solver: " + str(len(derived)) + " gap disjunct(s) "\n                "independently re-derived from the signed source, "\n                "bijection holds, every disjunct refuted"\n            )\n            return 0\n        if not _check_serialized(farkas_doc):\n            return _fail(\n                "Farkas certificate does NOT prove unsat: the declared "\n                "multipliers do not collapse the linear system to a numeric "\n                "contradiction (coverage gap or forged certificate)"\n            )\n        print(\n            "OK   Farkas certificate verified by rational arithmetic, no "\n            "solver (contradiction: "\n            + str(farkas_doc.get("contradiction", "?")) + ")"\n        )\n        return 0\n\n    if smt2_expected:\n        try:\n            import z3\n        except ImportError:\n            print(\n                "ERROR: z3-solver required to check the coverage proof.\\n"\n                "Install: pip install z3-solver\\n"\n                "The crypto provenance gate above already PASSED; only the "\n                "semantic unsat re-check is skipped.",\n                file=sys.stderr,\n            )\n            return 2\n        solver = z3.Solver()\n        try:\n            solver.from_string(\n                (ROOT / "coverage.smt2").read_bytes().decode("utf-8")\n            )\n        except z3.Z3Exception as e:\n            return _fail("z3 parse error on coverage.smt2: " + str(e))\n        res = solver.check()\n        if str(res) != "unsat":\n            return _fail(\n                "coverage proof did NOT reproduce unsat (z3 returned "\n                + str(res) + "); treat as a coverage gap"\n            )\n        print("OK   z3 reproduced unsat: coverage proof holds (no gap)")\n    return 0\n\n\ndef _link_farkas_path(name):\n    # Prior links live in chain/NNN_*; the current link\'s farkas is at root.\n    if name == "manifest.json (current)":\n        return ROOT / "coverage.farkas.json"\n    return ROOT / "chain" / name.replace(\n        "_manifest.json", "_coverage.farkas.json"\n    )\n\n\ndef _authenticated_threshold(name, link):\n    # manifest-is-authority: coverage existence is decided by the signed\n    # manifest field, never by file presence. Returns the link\'s\n    # sha-gated threshold EXPRESSION; the hop containment obligation is\n    # re-derived from it, never read from a hop bundle.\n    field = link.get("coverage_farkas_sha256")\n    path = _link_farkas_path(name)\n    if field is None:\n        if path.is_file():\n            return ("refuse", _fail(\n                name + " declares no coverage_farkas_sha256 but a "\n                + path.name + " is present (unexpected evidence)"\n            ))\n        return ("none", None)\n    if not path.is_file():\n        return ("refuse", _fail(\n            name + " signed manifest declares coverage_farkas_sha256 but "\n            + path.name + " is missing (missing evidence / truncation)"\n        ))\n    data = path.read_bytes()\n    if hashlib.sha256(data).hexdigest() != field:\n        return ("refuse", _fail(\n            name + " " + path.name + " sha256 does not match the signed "\n            "manifest coverage_farkas_sha256 (tampered or substituted)"\n        ))\n    try:\n        doc = json.loads(data.decode("utf-8"))\n    except Exception as e:\n        return ("refuse", _fail(\n            name + " " + path.name + " parse error: " + str(e)\n        ))\n    expr = doc.get("threshold_expr") if isinstance(doc, dict) else None\n    if not isinstance(expr, str) or not expr:\n        return ("refuse", _fail(\n            name + " " + path.name + " carries no threshold_expr; the "\n            "hop containment obligation cannot be re-derived"\n        ))\n    return ("has", expr)\n\n\ndef _hop_path(idx):\n    return ROOT / "chain" / (str(idx).zfill(3) + "_hop.farkas.json")\n\n\ndef _walk_monotonicity(ordered):\n    # Composed after the S120 chain walk. ordered is\n    # [(name, link), ... , ("manifest.json (current)", current_manifest)].\n    # Per hop where both links declare coverage, a hop-containment\n    # Farkas bundle chain/NNN_hop.farkas.json (NNN = predecessor index)\n    # must prove region(T_prev) subset-of region(T_cur): the obligation\n    # is RE-DERIVED from the two sha-gated threshold expressions and\n    # every DNF disjunct of T_prev AND NOT(T_cur) must be refuted.\n    # __s126_hop_walk_v1__\n    checked = 0\n    for i in range(1, len(ordered)):\n        name_prev, link_prev = ordered[i - 1]\n        name_cur, link_cur = ordered[i]\n        st_prev, expr_prev = _authenticated_threshold(name_prev, link_prev)\n        if st_prev == "refuse":\n            return expr_prev\n        st_cur, expr_cur = _authenticated_threshold(name_cur, link_cur)\n        if st_cur == "refuse":\n            return expr_cur\n        hop_file = _hop_path(i - 1)\n        if st_cur == "has" and st_prev == "has":\n            if not hop_file.is_file():\n                return _fail(\n                    "hop containment bundle missing: chain/"\n                    + hop_file.name + " (both links declare coverage; "\n                    "the region-containment proof is required, "\n                    "fail-closed)"\n                )\n            try:\n                hop_doc = json.loads(\n                    hop_file.read_bytes().decode("utf-8")\n                )\n            except Exception as e:\n                return _fail(\n                    "chain/" + hop_file.name + " parse error: " + str(e)\n                )\n            try:\n                prev_ast = ml_parse(expr_prev)\n                cur_ast = ml_parse(expr_cur)\n            except MinilangError as e:\n                return _fail(\n                    "hop threshold parse REFUSED at " + name_cur + ": "\n                    + str(e)\n                )\n            ok, reason = check_hop_bundle(hop_doc, prev_ast, cur_ast)\n            if not ok:\n                return _fail(\n                    "coverage REGION REGRESSION or invalid hop proof "\n                    "at " + name_cur + ": " + reason\n                )\n            checked += 1\n        else:\n            if hop_file.is_file():\n                return _fail(\n                    "unexpected hop bundle chain/" + hop_file.name\n                    + ": a hop where a link declares no coverage must "\n                    "carry no hop proof"\n                )\n            if st_cur == "none" and st_prev == "has":\n                return _fail(\n                    "coverage VANISHED at " + name_cur + ": predecessor "\n                    "declares a coverage proof but the current link "\n                    "drops it (dropping coverage across a material "\n                    "change is refused)"\n                )\n        # (has, none) -> net grew from nothing; (none, none) -> skip.\n    if checked:\n        print(\n            "OK   hop containment verified across " + str(checked)\n            + " hop(s): each declared threshold region contains its "\n            "predecessor\'s, obligations re-derived from sha-gated "\n            "threshold expressions, every disjunct refuted (Farkas, "\n            "offline, zero issuer trust)"\n        )\n    return 0\n\n\ndef _walk_chain(current_manifest):\n    prior_digest = current_manifest.get("prior_digest")\n    if prior_digest is None:\n        return _fail(\n            "this verifier expects an envelope-binding chain but the "\n            "current manifest declares no prior_digest"\n        )\n\n    chain_dir = ROOT / "chain"\n    if not chain_dir.is_dir():\n        return _fail(\n            "manifest declares prior_digest but no chain/ directory of "\n            "prior manifests is present (missing chain)"\n        )\n    link_paths = sorted(chain_dir.glob("*_manifest.json"))\n    if not link_paths:\n        return _fail(\n            "manifest declares prior_digest but chain/ contains no "\n            "*_manifest.json links (missing chain)"\n        )\n\n    links = []\n    for p in link_paths:\n        try:\n            links.append((p.name, json.loads(p.read_text(encoding="utf-8"))))\n        except Exception as e:\n            return _fail("chain link " + p.name + " parse error: " + str(e))\n\n    for name, link in links:\n        rc = _verify_link_signature(link, "chain/" + name)\n        if rc != 0:\n            return rc\n\n    genesis_count = sum(\n        1 for _, link in links if link.get("prior_digest") is None\n    )\n    if genesis_count != 1:\n        return _fail(\n            "chain has " + str(genesis_count) + " genesis links (links "\n            "without prior_digest); exactly one expected (cycle or "\n            "multiple roots)"\n        )\n    if links[0][1].get("prior_digest") is not None:\n        return _fail(\n            "chain/" + links[0][0] + " declares a prior_digest; the chain "\n            "is truncated (the oldest link shown is not genesis)"\n        )\n\n    seen_digests = set()\n    ordered = links + [("manifest.json (current)", current_manifest)]\n    for i in range(len(ordered)):\n        name_i, link_i = ordered[i]\n        digest_i = hashlib.sha256(\n            _canonical_body_bytes(link_i)\n        ).hexdigest()\n        if digest_i in seen_digests:\n            return _fail(\n                "cycle detected: " + name_i + " has a canonical digest "\n                "already seen earlier in the chain"\n            )\n        seen_digests.add(digest_i)\n\n    for i in range(1, len(ordered)):\n        name_prev, link_prev = ordered[i - 1]\n        name_cur, link_cur = ordered[i]\n        prev_digest = hashlib.sha256(\n            _canonical_body_bytes(link_prev)\n        ).hexdigest()\n        declared = link_cur.get("prior_digest")\n        if declared != prev_digest:\n            return _fail(\n                "chain broken at " + name_cur + ": declared prior_digest "\n                + str(declared)[:16] + "... does not match sha256 of "\n                + name_prev + " canonical body " + prev_digest[:16] + "..."\n            )\n        moved = [\n            f for f in _SHA_BEARING_FIELDS\n            if link_cur.get(f) != link_prev.get(f)\n        ]\n        if not moved:\n            return _fail(\n                "no-op re-binding at " + name_cur + ": no sha-bearing field "\n                "moved vs " + name_prev + " (a material change must alter at "\n                "least one of " + ", ".join(_SHA_BEARING_FIELDS) + ")"\n            )\n\n    print(\n        "OK   chain walk verified: " + str(len(links)) + " prior link(s), "\n        "rooted at genesis, each a real build change (no-trust, offline)"\n    )\n    rc_mono = _walk_monotonicity(ordered)\n    if rc_mono != 0:\n        return rc_mono\n    return 0\n\n\ndef _cost_check_serialized(doc):  # __s174_g1_cost_reproof__\n    from fractions import Fraction\n    constraints = doc.get("constraints")\n    multipliers = doc.get("multipliers")\n    if not isinstance(constraints, list) or not isinstance(\n        multipliers, list\n    ):\n        return False\n    if len(constraints) != len(multipliers):\n        return False\n    lam = []\n    for m in multipliers:\n        try:\n            lam.append(Fraction(m))\n        except (ValueError, TypeError, ZeroDivisionError):\n            return False\n    if any(x < 0 for x in lam):\n        return False\n    if not any(x > 0 for x in lam):\n        return False\n    combined = {}\n    strict = False\n    for x, c in zip(lam, constraints):\n        if x == 0:\n            continue\n        if not isinstance(c, dict):\n            return False\n        coeffs = c.get("coeffs")\n        if not isinstance(coeffs, dict):\n            return False\n        for k, v in coeffs.items():\n            try:\n                fv = Fraction(v)\n            except (ValueError, TypeError, ZeroDivisionError):\n                return False\n            combined[k] = combined.get(k, Fraction(0)) + x * fv\n        if c.get("strict"):\n            strict = True\n    for k, v in combined.items():\n        if k != "" and v != 0:\n            return False\n    const = combined.get("", Fraction(0))\n    if const > 0:\n        return True\n    if const == 0 and strict:\n        return True\n    return False\n\n\ndef main():\n    try:\n        from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n            Ed25519PublicKey,\n        )\n        from cryptography.exceptions import InvalidSignature\n    except ImportError:\n        print(\n            "ERROR: cryptography library required.\\n"\n            "Install: pip install \'cryptography>=42\'",\n            file=sys.stderr,\n        )\n        return 2\n\n    manifest_path = ROOT / "manifest.json"\n    if not manifest_path.is_file():\n        return _fail("manifest.json not found in " + str(ROOT))\n    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))\n\n    sig_block = manifest.get("signature")\n    if not sig_block:\n        return _fail("manifest has no signature block")\n    pub_b64 = sig_block.get("public_key_b64", "")\n    sig_b64 = sig_block.get("signature_b64", "")\n    if not pub_b64 or not sig_b64:\n        return _fail("manifest signature block incomplete")\n\n    body_bytes = _canonical_body_bytes(manifest)\n    try:\n        pub_key = Ed25519PublicKey.from_public_bytes(\n            base64.b64decode(pub_b64)\n        )\n        pub_key.verify(base64.b64decode(sig_b64), body_bytes)\n    except InvalidSignature:\n        return _fail("Ed25519 signature does NOT verify")\n    except Exception as e:\n        return _fail("signature verification error: " + str(e))\n    print("OK   Ed25519 signature verified")\n\n    source_path = ROOT / "source.nous"\n    if not source_path.is_file():\n        return _fail("source.nous not found in " + str(ROOT))\n    source_bytes = source_path.read_bytes()\n    src_sha = hashlib.sha256(source_bytes).hexdigest()\n    expected = manifest.get("source_sha256", "")\n    if src_sha != expected:\n        return _fail(\n            "source.sha256 mismatch: file=" + src_sha[:16] + "... "\n            "manifest=" + expected[:16] + "..."\n        )\n    print("OK   source.sha256 matches manifest (" + src_sha[:16] + "...)")\n\n    cost_expected = manifest.get("cost_farkas_sha256")  # __s174_g1_cost_reproof__\n    if cost_expected:\n        cost_path = ROOT / "cost.farkas.json"\n        if not cost_path.is_file():\n            return _fail(\n                "manifest declares cost_farkas_sha256 but "\n                "cost.farkas.json is not present in the dossier "\n                "(missing cost-cap evidence)"\n            )\n        cost_bytes = cost_path.read_bytes()\n        cost_sha = hashlib.sha256(cost_bytes).hexdigest()\n        if cost_sha != cost_expected:\n            return _fail(\n                "cost.farkas.json sha256 mismatch: file=" + cost_sha[:16]\n                + "... manifest=" + cost_expected[:16]\n                + "... (cost-cap Farkas certificate tampered or "\n                "substituted)"\n            )\n        try:\n            cost_doc = json.loads(cost_bytes.decode("utf-8"))\n        except Exception as e:\n            return _fail("cost.farkas.json parse error: " + str(e))\n        if not _cost_check_serialized(cost_doc):\n            return _fail(\n                "cost-cap Farkas certificate does NOT prove the bound: "\n                "the declared multipliers do not collapse the linear "\n                "system to a numeric contradiction (cost overrun or "\n                "forged certificate)"\n            )\n        print(\n            "OK   cost-cap Farkas certificate PROVEN offline by "\n            "rational arithmetic, no solver (contradiction: "\n            + str(cost_doc.get("contradiction", "?")) + ")"\n        )\n\n    rc_cov = _check_coverage(manifest, source_bytes.decode("utf-8"))\n    if rc_cov != 0:\n        return rc_cov\n\n    rc_chain = _walk_chain(manifest)\n    if rc_chain != 0:\n        return rc_chain\n\n    print()\n    print(\n        "VERDICT: PASS (Ed25519 manifest + envelope-binding chain + "\n        "current-link coverage re-derived, hop containment proven, "\n        "offline, zero issuer trust)"\n    )\n    print("  world:        " + str(manifest.get("world_name", "?")))\n    print(\n        "  cost_cap:     $" + str(manifest.get("cost_cap_usd", "?")) + " USD"\n    )\n    print("  verdict:      " + str(manifest.get("verdict", "?")))\n    print(\n        "  prior_digest: "\n        + str(manifest.get("prior_digest", "?"))[:16] + "..."\n    )\n    print("  solver:       " + str(manifest.get("solver_version", "?")))\n    print("  timestamp:    " + str(manifest.get("timestamp_utc", "?")))\n    return 0\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'  # __s125_chain_bundle_template_v1__ __s126_hop_walk_v1__


# --- S127 blocking-net-full verifier machinery (__s127_net_verifier_build_v1__) ---
# build_chain_net_verifier() splices the net-containment walk into
# the CHAIN_BUNDLE template at three unique anchors. Fail-closed on
# any anchor whose count != 1. Unused until U6 wires the select.

_NET_EMBED_BLOCK = '\n\ndef _net_disjuncts(prev_sigs, cur_sigs, bound):\n    # __s127_net_walk_v1__ DNF of OR(prev_sigs) AND AND(NOT cur_sigs).\n    # A real point witnesses non-containment iff it is blocked by some\n    # predecessor signal yet by no current signal; net(prev) subset-of\n    # net(cur) over the reals iff this conjunction is unsatisfiable.\n    # Empty predecessor net -> no disjuncts (vacuous containment).\n    if not prev_sigs:\n        return []\n    prev_or = _nnf(prev_sigs[0], False)\n    for sig in prev_sigs[1:]:\n        prev_or = {\n            "kind": "binop", "op": "||",\n            "left": prev_or, "right": _nnf(sig, False),\n        }\n    conj = prev_or\n    for sig in cur_sigs:\n        conj = {\n            "kind": "binop", "op": "&&",\n            "left": conj, "right": _nnf(sig, True),\n        }\n    return _dnf(conj, bound)\n\n\ndef check_net_bundle(doc, prev_sigs, cur_sigs):\n    # __s127_net_walk_v1__ Zero-trust check of a blocking-net containment\n    # bundle: the obligation OR(prev_sigs) AND AND(NOT cur_sigs) is\n    # RE-DERIVED from the two authenticated blocking-signal lists, a\n    # bijection is required against the carried certificates, and every\n    # multiplier is checked by rational arithmetic. Returns (ok, reason).\n    if not isinstance(doc, dict):\n        return (False, "net bundle is not a JSON object")\n    if doc.get("fragment") != "blocking-net-containment-bundle":\n        return (False, "net bundle fragment is not "\n                "blocking-net-containment-bundle")\n    cert_list = doc.get("certs")\n    if not isinstance(cert_list, list):\n        return (False, "net bundle has no certs array")\n    try:\n        disjuncts = _net_disjuncts(prev_sigs, cur_sigs, DISJUNCT_BOUND)\n    except FarkasError as e:\n        return (False, "net obligation derivation refused: " + str(e))\n    derived = {}\n    for comps in disjuncts:\n        try:\n            constraints, _system = _canon_system(comps)\n        except FarkasError as e:\n            return (False, "net obligation derivation refused: " + str(e))\n        derived[_canon_json(constraints)] = constraints\n    carried = {}\n    for cert in cert_list:\n        if not isinstance(cert, dict):\n            return (False, "a net cert is not a JSON object")\n        cons = cert.get("constraints")\n        mults = cert.get("multipliers")\n        if not isinstance(cons, list) or not isinstance(mults, list):\n            return (False, "a net cert lacks constraints or multipliers")\n        norm = []\n        for c in cons:\n            if not isinstance(c, dict):\n                return (False, "a carried net constraint is not an object")\n            coeffs = c.get("coeffs")\n            if not isinstance(coeffs, dict):\n                return (False, "a carried net constraint has no coeffs")\n            try:\n                norm_coeffs = {\n                    str(k): str(Fraction(v))\n                    for k, v in sorted(coeffs.items())\n                }\n            except (ValueError, TypeError, ZeroDivisionError):\n                return (False, "non-rational carried net coefficient")\n            norm.append(\n                {"coeffs": norm_coeffs, "strict": bool(c.get("strict"))}\n            )\n        norm.sort(key=_canon_json)\n        key = _canon_json(norm)\n        if key in carried:\n            return (False, "duplicate net certificate for one disjunct")\n        carried[key] = mults\n    missing = set(derived) - set(carried)\n    surplus = set(carried) - set(derived)\n    if missing:\n        return (\n            False,\n            "net bundle OMITS " + str(len(missing)) + " derived disjunct(s) "\n            "of OR(prev_sigs) AND AND(NOT cur_sigs) (overclaim-by-omission)",\n        )\n    if surplus:\n        return (\n            False,\n            "net bundle carries " + str(len(surplus)) + " certificate(s) for "\n            "disjuncts that do not derive from the authenticated sources",\n        )\n    for key, constraints in derived.items():\n        if not _check_multipliers(constraints, carried[key]):\n            return (\n                False,\n                "a net certificate\'s multipliers do not collapse its "\n                "derived disjunct to a contradiction (net regression or "\n                "forged certificate)",\n            )\n    return (True, "")\n\n'

_NET_WALK_BLOCK = 'def _link_source_path(name):\n    # __s127_net_walk_v1__ current link\'s source is at root; prior links\n    # carry chain/NNN_source.nous (full mode only).\n    if name == "manifest.json (current)":\n        return ROOT / "source.nous"\n    return ROOT / "chain" / name.replace(\n        "_manifest.json", "_source.nous"\n    )\n\n\ndef _net_path(idx):\n    return ROOT / "chain" / (str(idx).zfill(3) + "_net.farkas.json")\n\n\ndef _authenticated_blocking_signals(name, link):\n    # __s127_net_walk_v1__ manifest-is-authority: the per-link source is\n    # sha-gated by the link\'s SIGNED source_sha256, then blocking signals\n    # are scanned from the authenticated bytes. Full mode requires the\n    # carried source for every link; its absence is a fail-closed refusal.\n    expected = link.get("source_sha256")\n    if not isinstance(expected, str) or len(expected) != 64:\n        return ("refuse", _fail(\n            name + " signed manifest has no usable source_sha256; the "\n            "blocking-net obligation cannot be re-derived"\n        ))\n    path = _link_source_path(name)\n    if not path.is_file():\n        return ("refuse", _fail(\n            name + " chain_coverage_mode is blocking-net-full but "\n            + path.name + " is missing (full mode requires per-link "\n            "source carry; missing evidence / truncation)"\n        ))\n    data = path.read_bytes()\n    if hashlib.sha256(data).hexdigest() != expected:\n        return ("refuse", _fail(\n            name + " " + path.name + " sha256 does not match the signed "\n            "source_sha256 (tampered or substituted)"\n        ))\n    try:\n        sigs = ml_scan_blocking_signals(data.decode("utf-8"))\n    except MinilangError as e:\n        return ("refuse", _fail(\n            name + " blocking-signal scan REFUSED: " + str(e)\n        ))\n    return ("has", sigs)\n\n\ndef _walk_net_containment(ordered):\n    # __s127_net_walk_v1__ Composed after the hop-containment walk, only\n    # when the CURRENT signed manifest declares chain_coverage_mode ==\n    # "blocking-net-full". Per hop, region(net_prev) subset-of\n    # region(net_cur) is proven by refuting every DNF disjunct of\n    # OR(prev_sigs) AND AND(NOT cur_sigs); both signal lists are scanned\n    # from the two links\' sha-gated carried sources, never trusted from a\n    # bundle. An empty predecessor net is vacuously contained and carries\n    # no proof; a present net bundle there is refused as unexpected.\n    checked = 0\n    for i in range(1, len(ordered)):\n        name_prev, link_prev = ordered[i - 1]\n        name_cur, link_cur = ordered[i]\n        st_p, prev_sigs = _authenticated_blocking_signals(\n            name_prev, link_prev\n        )\n        if st_p == "refuse":\n            return prev_sigs\n        st_c, cur_sigs = _authenticated_blocking_signals(\n            name_cur, link_cur\n        )\n        if st_c == "refuse":\n            return cur_sigs\n        net_file = _net_path(i - 1)\n        if not prev_sigs:\n            if net_file.is_file():\n                return _fail(\n                    "unexpected net bundle chain/" + net_file.name\n                    + ": the predecessor blocking net is empty (vacuous "\n                    "containment carries no proof)"\n                )\n            continue\n        if not net_file.is_file():\n            return _fail(\n                "blocking-net containment bundle missing: chain/"\n                + net_file.name + " (predecessor net is non-empty; the "\n                "net-containment proof is required, fail-closed)"\n            )\n        try:\n            net_doc = json.loads(net_file.read_bytes().decode("utf-8"))\n        except Exception as e:\n            return _fail(\n                "chain/" + net_file.name + " parse error: " + str(e)\n            )\n        ok, reason = check_net_bundle(net_doc, prev_sigs, cur_sigs)\n        if not ok:\n            return _fail(\n                "BLOCKING-NET REGRESSION or invalid net proof at "\n                + name_cur + ": " + reason\n            )\n        checked += 1\n    if checked:\n        print(\n            "OK   blocking-net containment verified across " + str(checked)\n            + " hop(s): each blocking net contains its predecessor\'s, "\n            "re-derived from sha-gated per-link sources, every disjunct "\n            "refuted (Farkas, offline, zero issuer trust)"\n        )\n    return 0\n\n\n'

_NET_WALK_CALL = '    if current_manifest.get(\n        "chain_coverage_mode"\n    ) == "blocking-net-full":  # __s127_net_walk_v1__\n        rc_net = _walk_net_containment(ordered)\n        if rc_net != 0:\n            return rc_net\n'

_NL_S127 = chr(10)
_NET_EMBED_ANCHOR = "# --- end farkas embed ---"
_NET_WALK_ANCHOR = "def _walk_chain(current_manifest):"
_NET_CALL_ANCHOR = (
    "    rc_mono = _walk_monotonicity(ordered)" + _NL_S127
    + "    if rc_mono != 0:" + _NL_S127
    + "        return rc_mono" + _NL_S127
    + "    return 0"
)


_GAPW_EMBED_BLOCK = '\n\nGAP_WITNESS_FRAGMENT = "coverage-gap-witness"\n\n\ndef _point_satisfies(point, system):\n    # __s133_gapw_embed_v1__ True iff the rational assignment point\n    # satisfies every LinIneq in system (each L (< | <=) 0). The caller\n    # guarantees point assigns every non-constant variable of system.\n    for ineq in system:\n        lhs = Fraction(0)\n        for k, v in ineq.coeffs.items():\n            lhs += v if k == "" else v * point[k]\n        if ineq.strict:\n            if not (lhs < 0):\n                return False\n        elif not (lhs <= 0):\n            return False\n    return True\n\n\ndef check_gap_witness(doc, threshold_ast, blocking_signals):\n    # __s133_gapw_embed_v1__ Zero-trust check of a coverage-gap-witness:\n    # the gap disjunct set is RE-DERIVED from the threshold AST and the\n    # blocking signals (never taken from the document); the document\n    # disjunct field only SELECTS which derived disjunct is claimed, by\n    # canonical key, and the witness point is evaluated against the\n    # RE-DERIVED constraints by rational arithmetic alone. Mirrors\n    # coverage_farkas.check_serialized_gap_witness; returns (ok, reason).\n    if not isinstance(doc, dict) or doc.get("fragment") != GAP_WITNESS_FRAGMENT:\n        return (False, "not a coverage-gap-witness document")\n    point = doc.get("point")\n    cons = doc.get("disjunct")\n    if not isinstance(point, dict) or not isinstance(cons, list):\n        return (False, "gap witness lacks point or disjunct")\n    norm = []\n    for c in cons:\n        if not isinstance(c, dict):\n            return (False, "a gap constraint is not an object")\n        coeffs = c.get("coeffs")\n        if not isinstance(coeffs, dict):\n            return (False, "a gap constraint has no coeffs")\n        try:\n            norm_coeffs = {\n                str(k): str(Fraction(v)) for k, v in sorted(coeffs.items())\n            }\n        except (ValueError, TypeError, ZeroDivisionError):\n            return (False, "non-rational gap coefficient")\n        norm.append({"coeffs": norm_coeffs, "strict": bool(c.get("strict"))})\n    norm.sort(key=_canon_json)\n    key = _canon_json(norm)\n    try:\n        disjuncts = _gap_disjuncts(threshold_ast, blocking_signals, DISJUNCT_BOUND)\n    except FarkasError as e:\n        return (False, "gap obligation derivation refused: " + str(e))\n    systems = {}\n    for comps in disjuncts:\n        try:\n            constraints, system = _canon_system(comps)\n        except FarkasError as e:\n            return (False, "gap obligation derivation refused: " + str(e))\n        systems[_canon_json(constraints)] = system\n    if key not in systems:\n        return (False, "claimed disjunct does not derive from the "\n                "authenticated threshold and blocking signals")\n    pt = {}\n    for k, v in point.items():\n        try:\n            pt[str(k)] = Fraction(v)\n        except (ValueError, TypeError, ZeroDivisionError):\n            return (False, "non-rational witness coordinate")\n    system = systems[key]\n    needed = set()\n    for ineq in system:\n        for vk in ineq.coeffs:\n            if vk != "":\n                needed.add(vk)\n    if not needed.issubset(set(pt)):\n        return (False, "witness point omits a variable of its disjunct")\n    if _point_satisfies(pt, system):\n        return (True, "")\n    return (False, "witness point does not satisfy its claimed gap "\n            "disjunct (not in T-and-unblocked at this point)")\n\n'  # __s133_gapw_embed_v1__


_PRIORCOV_BLOCK = 'def _walk_prior_coverage(ordered):\n    # __s137_priorcov_v1__ Full mode only. Re-proves each PRIOR link\'s\n    # OWN coverage completeness with zero issuer trust. net-containment\n    # + hop-monotonicity + current-link coverage do NOT imply that a\n    # prior link\'s blocking net actually covers its threshold: a signed\n    # prior link could carry a gapped or omitting Farkas cert that is\n    # sha-consistent with its own manifest, and the chain would still\n    # pass. Full mode already carries, per prior link, the sha-gated\n    # chain/NNN_source.nous and the sha-gated chain/NNN_coverage.farkas\n    # .json; this walk runs the SAME zero-trust re-derivation the\n    # current link gets (derive gap disjuncts from the sha-gated source\n    # and sha-gated threshold_expr, bijection against the sha-gated\n    # cert, refute every disjunct), or a v1 single-comparison cert\n    # check for the legacy fragment. No new carried artifact. The\n    # current link is proven by _check_coverage; this covers\n    # ordered[:-1]. A prior link declaring no coverage is skipped (a\n    # chain may add coverage from nothing).\n    checked = 0\n    for name, link in ordered[:-1]:\n        field = link.get("coverage_farkas_sha256")\n        if field is None:\n            continue\n        if not isinstance(field, str) or len(field) != 64:\n            return _fail(\n                name + " has a malformed coverage_farkas_sha256; the "\n                "prior-link coverage obligation cannot be re-derived"\n            )\n        far_path = _link_farkas_path(name)\n        if not far_path.is_file():\n            return _fail(\n                name + " declares coverage_farkas_sha256 but "\n                + far_path.name + " is missing (full-mode prior-link "\n                "coverage requires the carried cert; missing evidence)"\n            )\n        far_bytes = far_path.read_bytes()\n        if hashlib.sha256(far_bytes).hexdigest() != field:\n            return _fail(\n                name + " " + far_path.name + " sha256 does not match "\n                "the signed coverage_farkas_sha256 (tampered or "\n                "substituted)"\n            )\n        try:\n            far_doc = json.loads(far_bytes.decode("utf-8"))\n        except Exception as e:\n            return _fail(\n                name + " " + far_path.name + " parse error: " + str(e)\n            )\n        if isinstance(far_doc, dict) and far_doc.get(\n            "fragment"\n        ) == "disjunctive-linear-bundle":\n            threshold_expr = far_doc.get("threshold_expr")\n            if not isinstance(threshold_expr, str) or not threshold_expr:\n                return _fail(\n                    name + " coverage bundle carries no threshold_expr; "\n                    "the obligation cannot be independently re-derived"\n                )\n            src_expected = link.get("source_sha256")\n            if not isinstance(src_expected, str) or len(\n                src_expected\n            ) != 64:\n                return _fail(\n                    name + " has no usable source_sha256; the prior-"\n                    "link coverage obligation cannot be re-derived"\n                )\n            src_path = _link_source_path(name)\n            if not src_path.is_file():\n                return _fail(\n                    name + " declares coverage but " + src_path.name\n                    + " is missing (full-mode prior-link coverage "\n                    "requires the carried source; missing evidence / "\n                    "truncation)"\n                )\n            src_bytes = src_path.read_bytes()\n            if hashlib.sha256(src_bytes).hexdigest() != src_expected:\n                return _fail(\n                    name + " " + src_path.name + " sha256 does not "\n                    "match the signed source_sha256 (tampered or "\n                    "substituted)"\n                )\n            try:\n                derived = derive_disjunct_constraints(\n                    src_bytes.decode("utf-8"), threshold_expr\n                )\n            except (MinilangError, FarkasError) as e:\n                return _fail(\n                    name + " prior-link coverage re-derivation from "\n                    "the sha-gated source REFUSED: " + str(e)\n                    + " (the obligation cannot be certified offline)"\n                )\n            ok, reason = check_bundle_against_derived(far_doc, derived)\n            if not ok:\n                return _fail(\n                    "PRIOR-LINK COVERAGE GAP or forged cert at " + name\n                    + ": " + reason\n                )\n        else:\n            if not _check_serialized(far_doc):\n                return _fail(\n                    "PRIOR-LINK COVERAGE GAP or forged cert at " + name\n                    + ": the v1 Farkas certificate does not collapse "\n                    "its linear system to a contradiction"\n                )\n        checked += 1\n    if checked:\n        print(\n            "OK   prior-link coverage re-proven across " + str(checked)\n            + " prior link(s): each declared blocking net actually "\n            "covers its threshold, re-derived from sha-gated per-link "\n            "sources and certs, every gap disjunct refuted (Farkas, "\n            "offline, zero issuer trust)"\n        )\n    return 0\n\n\n'  # __s137_priorcov_v1__

_PRIORCOV_CALL = '    if current_manifest.get(\n        "chain_coverage_mode"\n    ) == "blocking-net-full":  # __s137_priorcov_v1__\n        rc_priorcov = _walk_prior_coverage(ordered)\n        if rc_priorcov != 0:\n            return rc_priorcov\n'  # __s137_priorcov_v1__

_PRIORCOV_DOC_OLD = "It does NOT re-prove PRIOR links' coverage\ncompleteness (no per-link source is carried), does NOT prove execution\nconformance, and does NOT prove the latest envelope is safer."  # __s137_priorcov_v1__

_PRIORCOV_DOC_NEW = "In full mode (blocking-net-full) it ALSO re-proves every PRIOR link's\ncoverage completeness with zero issuer trust: each per-link source and\ncert is carried and sha-gated, and each prior link's gap disjunct set\nis RE-DERIVED and refuted exactly as the current link is. It does NOT\nprove execution conformance, and does NOT prove the latest envelope is\nsafer."  # __s137_priorcov_v1__


def build_chain_net_verifier():
    base = VERIFY_OFFLINE_PY_CHAIN_BUNDLE
    for label, anchor in (
        ("net-embed", _NET_EMBED_ANCHOR),
        ("net-walk", _NET_WALK_ANCHOR),
        ("net-call", _NET_CALL_ANCHOR),
        ("priorcov-doc", _PRIORCOV_DOC_OLD),  # __s137_priorcov_v1__
    ):
        if base.count(anchor) != 1:
            raise DossierError(
                "S127 net verifier splice REFUSED: anchor " + label
                + " occurs " + str(base.count(anchor)) + " times in "
                "CHAIN_BUNDLE (expected 1); template drift"
            )
    out = base.replace(
        _NET_EMBED_ANCHOR,
        _NET_EMBED_BLOCK + _NET_EMBED_ANCHOR, 1
    )
    out = out.replace(
        _NET_WALK_ANCHOR,
        _NET_WALK_BLOCK + _PRIORCOV_BLOCK + _NET_WALK_ANCHOR, 1  # __s137_priorcov_v1__
    )
    _call_repl = (
        "    rc_mono = _walk_monotonicity(ordered)" + _NL_S127
        + "    if rc_mono != 0:" + _NL_S127
        + "        return rc_mono" + _NL_S127
        + _NET_WALK_CALL
        + _PRIORCOV_CALL  # __s137_priorcov_v1__
        + "    return 0"
    )
    out = out.replace(_NET_CALL_ANCHOR, _call_repl, 1)
    out = out.replace(_PRIORCOV_DOC_OLD, _PRIORCOV_DOC_NEW, 1)  # __s137_priorcov_v1__
    return out


_GAPW_VERIFIER_HEADER = '#!/usr/bin/env python3\n"""Offline verification of NOUS dossier (Annex IV): a CARRIED coverage-gap-\nwitness -- a REFUTATION artifact, the dual of a coverage proof.\n\nUsage: python3 verify_offline.py\nExit:  0 = artifact verified, 1 = FAIL (tamper / wrong claim kind / missing\n       evidence / witness does not hold), 2 = environment error.\n\nThe exit code answers ONE question: is the artifact valid? It does NOT\nencode whether the demonstrated fact is good or bad news. A verified\ngap-witness exits 0 and prints VERDICT: REFUTATION with a machine-readable\n"result: gap-demonstrated" line; a consumer that wants to gate on the\nexistence of a gap keys on that line, never on the exit status (which stays\nconsistent across all NOUS verifier templates).\n\nRequires: cryptography (Ed25519 author signature only). The gap-witness is\nchecked by RATIONAL ARITHMETIC ALONE (stdlib): the gap disjunct set is\nRE-DERIVED from the SIGNED source.nous and the sha-gated threshold\nexpression, and the carried point is evaluated against it. No solver, no\nNOUS install, zero issuer trust.\n\nChecks, fail-closed, in order:\n  1. Ed25519 signature over the canonical manifest body bytes.\n  2. source.nous sha256 == manifest.source_sha256.\n  3. manifest.source_kind == "gap-witness" (refuse any other kind;\n     no silent discriminator merge).\n  4. coverage.gapwitness.json sha256 == manifest.gap_witness_sha256.\n  5. Re-derive (threshold, blocking) from the signed source + sha-gated\n     threshold_expr; check the carried point lies in the threshold region\n     and escapes every blocking signal. PROVES a real gap EXISTS.\n\nBOUNDARY: a verified gap-witness proves a coverage gap EXISTS at the carried\npoint -- NOT a compliance pass, NOT that the agent misbehaves, NOT that the\ngap is unique or maximal.\n__s134_gapw_verifier_v1__\n"""'


_GAPW_VERIFIER_MAIN = '\ndef main():\n    try:\n        from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n            Ed25519PublicKey,\n        )\n        from cryptography.exceptions import InvalidSignature\n    except ImportError:\n        print(\n            "ERROR: cryptography library required. "\n            "Install: pip install \'cryptography>=42\'",\n            file=sys.stderr,\n        )\n        return 2\n\n    manifest_path = ROOT / "manifest.json"\n    if not manifest_path.is_file():\n        return _fail("manifest.json not found in " + str(ROOT))\n    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))\n\n    sig_block = manifest.get("signature")\n    if not sig_block:\n        return _fail("manifest has no signature block")\n    pub_b64 = sig_block.get("public_key_b64", "")\n    sig_b64 = sig_block.get("signature_b64", "")\n    if not pub_b64 or not sig_b64:\n        return _fail("manifest signature block incomplete")\n\n    body = {\n        k: v for k, v in manifest.items()\n        if k not in ("signature", "transparency_log")\n    }\n    body_bytes = json.dumps(\n        body, sort_keys=True, separators=(",", ":")\n    ).encode("utf-8")\n    try:\n        pub_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64))\n        pub_key.verify(base64.b64decode(sig_b64), body_bytes)\n    except InvalidSignature:\n        return _fail("Ed25519 signature does NOT verify")\n    except Exception as e:\n        return _fail("signature verification error: " + str(e))\n    print("OK   Ed25519 signature verified")\n\n    source_path = ROOT / "source.nous"\n    if not source_path.is_file():\n        return _fail("source.nous not found in " + str(ROOT))\n    source_bytes = source_path.read_bytes()\n    src_sha = hashlib.sha256(source_bytes).hexdigest()\n    expected = manifest.get("source_sha256", "")\n    if src_sha != expected:\n        return _fail(\n            "source.sha256 mismatch: file=" + src_sha[:16] + "... "\n            "manifest=" + expected[:16] + "...")\n    print("OK   source.sha256 matches manifest (" + src_sha[:16] + "...)")\n\n    if manifest.get("source_kind") != "gap-witness":\n        return _fail(\n            "manifest source_kind is " + repr(manifest.get("source_kind"))\n            + ", not \'gap-witness\'; this verifier ships with a coverage-gap-"\n            "witness (refutation) dossier and refuses any other claim kind")\n\n    gw_expected = manifest.get("gap_witness_sha256", "")\n    if not gw_expected:\n        return _fail(\n            "manifest declares source_kind \'gap-witness\' but carries no "\n            "gap_witness_sha256 binding")\n    gw_path = ROOT / "coverage.gapwitness.json"\n    if not gw_path.is_file():\n        return _fail("coverage.gapwitness.json not found in " + str(ROOT))\n    gw_bytes = gw_path.read_bytes()\n    gw_sha = hashlib.sha256(gw_bytes).hexdigest()\n    if gw_sha != gw_expected:\n        return _fail(\n            "coverage.gapwitness.json sha256 mismatch: file=" + gw_sha[:16]\n            + "... manifest=" + gw_expected[:16]\n            + "... (gap-witness tampered or substituted)")\n    print("OK   coverage.gapwitness.json sha256 matches manifest ("\n          + gw_sha[:16] + "...)")\n\n    try:\n        gw_doc = json.loads(gw_bytes.decode("utf-8"))\n    except Exception as e:\n        return _fail("coverage.gapwitness.json parse error: " + str(e))\n    if not isinstance(gw_doc, dict):\n        return _fail("coverage.gapwitness.json is not a JSON object")\n    threshold_expr = gw_doc.get("threshold_expr")\n    if not isinstance(threshold_expr, str) or not threshold_expr:\n        return _fail(\n            "gap-witness carries no threshold_expr; the obligation cannot "\n            "be independently re-derived")\n\n    try:\n        threshold_ast = ml_parse(threshold_expr)\n        blocking_signals = ml_scan_blocking_signals(\n            source_bytes.decode("utf-8"))\n    except (MinilangError, FarkasError) as e:\n        return _fail(\n            "independent re-derivation from the signed source REFUSED: "\n            + str(e) + " (obligation cannot be certified offline)")\n\n    ok, reason = check_gap_witness(gw_doc, threshold_ast, blocking_signals)\n    if not ok:\n        return _fail(\n            "gap-witness does NOT verify: " + reason\n            + " (the carried point is not a real coverage gap, or the "\n            "witness was tampered or substituted)")\n    print("OK   gap-witness verified by rational arithmetic, no solver: "\n          "the carried point lies in the threshold region and escapes "\n          "every blocking signal (re-derived from the signed source)")\n\n    print()\n    print("VERDICT: REFUTATION (Ed25519 manifest + coverage-gap-witness; a "\n          "coverage gap is DEMONSTRATED at the carried point, re-derived "\n          "from the signed source, stdlib-checked, zero issuer trust)")\n    print("result: gap-demonstrated")\n    print("boundary: proves a gap EXISTS at this point; NOT a compliance "\n          "pass, NOT that the agent misbehaves, NOT unique or maximal")\n    print("  world:       " + str(manifest.get("world_name", "?")))\n    print("  threshold:   " + str(threshold_expr))\n    print("  point:       "\n          + json.dumps(gw_doc.get("point", {}), sort_keys=True))\n    print("  gw_sha:      "\n          + str(manifest.get("gap_witness_sha256", "?"))[:16] + "...")\n    print("  solver:      " + str(manifest.get("solver_version", "?")))\n    print("  timestamp:   " + str(manifest.get("timestamp_utc", "?")))\n    return 0\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'


def build_gap_witness_verifier():
    base = VERIFY_OFFLINE_PY_BUNDLE
    end_embed = "# --- end farkas embed ---"
    main_anchor = chr(10) + "def main():"
    doc_anchor = chr(10) + "from __future__ import annotations" + chr(10)
    for label, a in (("end-embed", end_embed), ("main", main_anchor),
                     ("docstring", doc_anchor)):
        if base.count(a) != 1:
            raise DossierError(
                "S134 gap-witness verifier splice REFUSED: anchor " + label
                + " occurs " + str(base.count(a)) + " times in BUNDLE "
                "(expected 1); template drift")
    after_doc = base.split(doc_anchor, 1)[1]
    rebodied = _GAPW_VERIFIER_HEADER + doc_anchor + after_doc
    rebodied = rebodied.replace(end_embed, _GAPW_EMBED_BLOCK + end_embed, 1)
    idx = rebodied.find(main_anchor)
    return rebodied[:idx] + _GAPW_VERIFIER_MAIN
