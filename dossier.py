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


VERIFY_OFFLINE_PY_CHAIN: str = '#!/usr/bin/env python3\n"""Offline verification of NOUS dossier (Annex IV) with envelope-binding chain.\n\nUsage: python3 verify_offline.py\nExit:  0 = PASS, 1 = FAIL, 2 = environment error.\n\nRequires: cryptography (Ed25519 author signatures). The coverage claim, if\npresent, is checked by rational arithmetic alone (Farkas) or by z3 if a\ncoverage.smt2 is present without a Farkas certificate. The chain walk uses\ncryptography + stdlib only.\n\nThis verifier verifies an unbroken sequence of signature-valid formation\nenvelopes, each declaring its predecessor by digest, each a real build\nchange (a sha-bearing field moved), rooted at genesis -- offline,\ncryptography + stdlib, zero trust in the issuer. It does NOT prove execution\nconformance, does NOT prove the latest envelope is safer, and does NOT prove\ncoverage non-regression.\n\nChecks, in order, fail-closed:\n  1. Ed25519 signature over the current manifest\'s canonical body bytes\n     (signature and transparency_log stripped before recomputing).\n  2. source.nous sha256 == manifest.source_sha256.\n  3. If the manifest declares a coverage proof, it is checked: a Farkas\n     certificate (rational arithmetic, no solver) when present, else a z3\n     unsat re-check of coverage.smt2. Both gated by an O(1) file-sha match.\n  4. Chain walk over chain/ (prior manifests only), six fail-closed\n     conditions: per-link signature, missing chain, altered link (broken\n     hash chain), truncated/no-genesis, no-op re-binding (no sha-bearing\n     field moved), and cycle / more-than-one-genesis.\n  5. Coverage-region monotonicity (S121): per hop where both links\'\n     signed manifests declare coverage_farkas_sha256, the predecessor\'s\n     proven region must be contained in the current\'s (closed-form, no\n     solver). Coverage dropped across a re-binding is refused. This\n     proves only that the DECLARED blocking net did not shrink across\n     versions -- NOT that the system is safer, NOT real-world risk.\n  __s121_monotonicity_walk_v1__\n"""\nfrom __future__ import annotations\n\nimport base64\nimport hashlib\nimport json\nimport sys\nfrom pathlib import Path\n\nROOT = Path(__file__).parent\n\n_SHA_BEARING_FIELDS = (\n    "source_sha256",\n    "pricing_sha256",\n    "smt_spec_sha256",\n    "cost_cap_usd",\n    "max_ticks",\n)\n\n\ndef _fail(msg):\n    print("FAIL: " + msg, file=sys.stderr)\n    return 1\n\n\ndef _canonical_body_bytes(m):\n    body = {\n        k: v for k, v in m.items()\n        if k not in ("signature", "transparency_log")\n    }\n    return json.dumps(\n        body, sort_keys=True, separators=(",", ":")\n    ).encode("utf-8")\n\n\ndef _verify_link_signature(link, label):\n    from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n        Ed25519PublicKey,\n    )\n    from cryptography.exceptions import InvalidSignature\n\n    sig_block = link.get("signature")\n    if not isinstance(sig_block, dict):\n        return _fail(label + " has no signature block")\n    pub_b64 = sig_block.get("public_key_b64", "")\n    sig_b64 = sig_block.get("signature_b64", "")\n    if not pub_b64 or not sig_b64:\n        return _fail(label + " signature block incomplete")\n    body_bytes = _canonical_body_bytes(link)\n    try:\n        pub_key = Ed25519PublicKey.from_public_bytes(\n            base64.b64decode(pub_b64)\n        )\n        pub_key.verify(base64.b64decode(sig_b64), body_bytes)\n    except InvalidSignature:\n        return _fail(label + " Ed25519 signature does NOT verify")\n    except Exception as e:\n        return _fail(label + " signature verification error: " + str(e))\n    return 0\n\n\ndef _check_serialized(doc):\n    from fractions import Fraction\n\n    constraints = doc.get("constraints")\n    multipliers = doc.get("multipliers")\n    if not isinstance(constraints, list) or not isinstance(multipliers, list):\n        return False\n    if len(constraints) != len(multipliers):\n        return False\n    lam = []\n    for m in multipliers:\n        try:\n            lam.append(Fraction(m))\n        except (ValueError, TypeError, ZeroDivisionError):\n            return False\n    if any(x < 0 for x in lam):\n        return False\n    if not any(x > 0 for x in lam):\n        return False\n    combined = {}\n    strict = False\n    for x, c in zip(lam, constraints):\n        if x == 0:\n            continue\n        if not isinstance(c, dict):\n            return False\n        coeffs = c.get("coeffs")\n        if not isinstance(coeffs, dict):\n            return False\n        for k, v in coeffs.items():\n            try:\n                fv = Fraction(v)\n            except (ValueError, TypeError, ZeroDivisionError):\n                return False\n            combined[k] = combined.get(k, Fraction(0)) + x * fv\n        if c.get("strict"):\n            strict = True\n    for k, v in combined.items():\n        if k != "" and v != 0:\n            return False\n    const = combined.get("", Fraction(0))\n    if const > 0:\n        return True\n    if const == 0 and strict:\n        return True\n    return False\n\n\ndef _check_coverage(manifest):\n    farkas_expected = manifest.get("coverage_farkas_sha256")\n    smt2_expected = manifest.get("coverage_smt2_sha256")\n    cov_sha = manifest.get("policy_coverage_sha256")\n    if not cov_sha and not farkas_expected and not smt2_expected:\n        return 0\n\n    if smt2_expected:\n        smt2_path = ROOT / "coverage.smt2"\n        if not smt2_path.is_file():\n            return _fail("coverage.smt2 not found in " + str(ROOT))\n        smt2_sha = hashlib.sha256(smt2_path.read_bytes()).hexdigest()\n        if smt2_sha != smt2_expected:\n            return _fail(\n                "coverage.smt2 sha256 mismatch: file=" + smt2_sha[:16]\n                + "... manifest=" + smt2_expected[:16] + "..."\n            )\n        print(\n            "OK   coverage.smt2 sha256 matches manifest ("\n            + smt2_sha[:16] + "...)"\n        )\n\n    if farkas_expected:\n        farkas_path = ROOT / "coverage.farkas.json"\n        if not farkas_path.is_file():\n            return _fail("coverage.farkas.json not found in " + str(ROOT))\n        farkas_bytes = farkas_path.read_bytes()\n        farkas_sha = hashlib.sha256(farkas_bytes).hexdigest()\n        if farkas_sha != farkas_expected:\n            return _fail(\n                "coverage.farkas.json sha256 mismatch: file="\n                + farkas_sha[:16] + "... manifest=" + farkas_expected[:16]\n                + "... (Farkas certificate tampered or substituted)"\n            )\n        try:\n            farkas_doc = json.loads(farkas_bytes.decode("utf-8"))\n        except Exception as e:\n            return _fail("coverage.farkas.json parse error: " + str(e))\n        if not _check_serialized(farkas_doc):\n            return _fail(\n                "Farkas certificate does NOT prove unsat: the declared "\n                "multipliers do not collapse the linear system to a numeric "\n                "contradiction (coverage gap or forged certificate)"\n            )\n        print(\n            "OK   Farkas certificate verified by rational arithmetic, no "\n            "solver (contradiction: "\n            + str(farkas_doc.get("contradiction", "?")) + ")"\n        )\n        return 0\n\n    if smt2_expected:\n        try:\n            import z3\n        except ImportError:\n            print(\n                "ERROR: z3-solver required to check the coverage proof.\\n"\n                "Install: pip install z3-solver\\n"\n                "The crypto provenance gate above already PASSED; only the "\n                "semantic unsat re-check is skipped.",\n                file=sys.stderr,\n            )\n            return 2\n        solver = z3.Solver()\n        try:\n            solver.from_string(\n                (ROOT / "coverage.smt2").read_bytes().decode("utf-8")\n            )\n        except z3.Z3Exception as e:\n            return _fail("z3 parse error on coverage.smt2: " + str(e))\n        res = solver.check()\n        if str(res) != "unsat":\n            return _fail(\n                "coverage proof did NOT reproduce unsat (z3 returned "\n                + str(res) + "); treat as a coverage gap"\n            )\n        print("OK   z3 reproduced unsat: coverage proof holds (no gap)")\n    return 0\n\n\ndef _mono_vars(constraint):\n    coeffs = constraint.get("coeffs")\n    if not isinstance(coeffs, dict):\n        return None\n    return {k for k in coeffs if k != ""}\n\n\ndef _region_contains(ineq_a, ineq_b):\n    from fractions import Fraction\n\n    ca = ineq_a.get("coeffs")\n    cb = ineq_b.get("coeffs")\n    if not isinstance(ca, dict) or not isinstance(cb, dict):\n        return (False, "malformed: a constraint has no coeffs dict")\n    sa = ineq_a.get("strict")\n    sb = ineq_b.get("strict")\n    if not isinstance(sa, bool) or not isinstance(sb, bool):\n        return (False, "malformed: a constraint has no boolean strict flag")\n    var_union = sorted((set(ca) | set(cb)) - {""})\n\n    def _f(d, k):\n        try:\n            return Fraction(d.get(k, 0))\n        except (ValueError, TypeError, ZeroDivisionError):\n            return None\n\n    for v in var_union:\n        av = _f(ca, v)\n        bv = _f(cb, v)\n        if av is None or bv is None:\n            return (False, "malformed: non-rational coefficient")\n        if (av == 0) != (bv == 0):\n            return (\n                False,\n                "non-proportional: variable " + repr(v) + " is zero on one "\n                "threshold and nonzero on the other (different geometry)",\n            )\n    pivot = None\n    for v in var_union:\n        if _f(ca, v) != 0:\n            pivot = v\n            break\n    if pivot is None:\n        return (False, "malformed: threshold has no nonzero variable coeff")\n    t = _f(cb, pivot) / _f(ca, pivot)\n    if t <= 0:\n        return (\n            False,\n            "anti-parallel: proportionality factor t=" + str(t)\n            + " is not positive (half-spaces face opposite directions)",\n        )\n    for v in var_union:\n        if _f(cb, v) != t * _f(ca, v):\n            return (\n                False,\n                "non-proportional: coefficient of " + repr(v)\n                + " does not scale by t=" + str(t),\n            )\n    const_a = _f(ca, "")\n    const_b = _f(cb, "")\n    scaled_a = t * const_a\n    if const_b > scaled_a:\n        return (\n            False,\n            "insufficient-slack: const_b=" + str(const_b)\n            + " > t*const_a=" + str(scaled_a)\n            + " (region T_b does not cover region T_a)",\n        )\n    if const_b == scaled_a and (sa is False) and (sb is True):\n        return (\n            False,\n            "strictness-violation: at the shared boundary the predecessor "\n            "(<=) includes the boundary point but the current (<) excludes it",\n        )\n    return (True, "")\n\n\ndef _link_farkas_path(name):\n    # Prior links live in chain/NNN_*; the current link\'s farkas is at root.\n    if name == "manifest.json (current)":\n        return ROOT / "coverage.farkas.json"\n    return ROOT / "chain" / name.replace(\n        "_manifest.json", "_coverage.farkas.json"\n    )\n\n\ndef _authenticated_threshold(name, link):\n    # manifest-is-authority: coverage existence is decided by the signed\n    # manifest field, never by file presence.\n    field = link.get("coverage_farkas_sha256")\n    path = _link_farkas_path(name)\n    if field is None:\n        if path.is_file():\n            return ("refuse", _fail(\n                name + " declares no coverage_farkas_sha256 but a "\n                + path.name + " is present (unexpected evidence)"\n            ))\n        return ("none", None)\n    if not path.is_file():\n        return ("refuse", _fail(\n            name + " signed manifest declares coverage_farkas_sha256 but "\n            + path.name + " is missing (missing evidence / truncation)"\n        ))\n    data = path.read_bytes()\n    if hashlib.sha256(data).hexdigest() != field:\n        return ("refuse", _fail(\n            name + " " + path.name + " sha256 does not match the signed "\n            "manifest coverage_farkas_sha256 (tampered or substituted)"\n        ))\n    try:\n        doc = json.loads(data.decode("utf-8"))\n        ineq0 = doc["constraints"][0]\n    except Exception as e:\n        return ("refuse", _fail(\n            name + " " + path.name + " parse error: " + str(e)\n        ))\n    return ("has", ineq0)\n\n\ndef _walk_monotonicity(ordered):\n    # Composed after the S120 chain walk. ordered is\n    # [(name, link), ... , ("manifest.json (current)", current_manifest)].\n    checked = 0\n    for i in range(1, len(ordered)):\n        name_prev, link_prev = ordered[i - 1]\n        name_cur, link_cur = ordered[i]\n        st_prev, val_prev = _authenticated_threshold(name_prev, link_prev)\n        if st_prev == "refuse":\n            return val_prev\n        st_cur, val_cur = _authenticated_threshold(name_cur, link_cur)\n        if st_cur == "refuse":\n            return val_cur\n        if st_cur == "has" and st_prev == "has":\n            vars_prev = _mono_vars(val_prev)\n            vars_cur = _mono_vars(val_cur)\n            if vars_prev is None or vars_cur is None:\n                return _fail(\n                    "monotonicity at " + name_cur + ": malformed threshold "\n                    "constraint"\n                )\n            if vars_prev != vars_cur:\n                return _fail(\n                    "monotonicity INCOMPARABLE at " + name_cur + ": "\n                    "predecessor variables " + str(sorted(vars_prev))\n                    + " != current variables " + str(sorted(vars_cur))\n                    + " (region containment across a changed variable space "\n                    "is not assertable; refused, not passed)"\n                )\n            contained, reason = _region_contains(val_prev, val_cur)\n            if not contained:\n                return _fail(\n                    "coverage REGION REGRESSION at " + name_cur + ": "\n                    "region(predecessor) is NOT contained in region(current) "\n                    "-- " + reason + " (the declared blocking net shrank "\n                    "across this re-binding)"\n                )\n            checked += 1\n        elif st_cur == "none" and st_prev == "has":\n            return _fail(\n                "coverage VANISHED at " + name_cur + ": predecessor declares "\n                "a coverage proof but the current link drops it (dropping "\n                "coverage across a material change is refused)"\n            )\n        # (has, none) -> net grew from nothing; (none, none) -> skip.\n    if checked:\n        print(\n            "OK   coverage-region monotonicity verified across "\n            + str(checked) + " hop(s): each declared blocking net contains "\n            "its predecessor\'s (closed-form, offline, zero issuer trust)"\n        )\n    return 0\n\n\ndef _walk_chain(current_manifest):\n    prior_digest = current_manifest.get("prior_digest")\n    if prior_digest is None:\n        return _fail(\n            "this verifier expects an envelope-binding chain but the "\n            "current manifest declares no prior_digest"\n        )\n\n    chain_dir = ROOT / "chain"\n    if not chain_dir.is_dir():\n        return _fail(\n            "manifest declares prior_digest but no chain/ directory of "\n            "prior manifests is present (missing chain)"\n        )\n    link_paths = sorted(chain_dir.glob("*_manifest.json"))\n    if not link_paths:\n        return _fail(\n            "manifest declares prior_digest but chain/ contains no "\n            "*_manifest.json links (missing chain)"\n        )\n\n    links = []\n    for p in link_paths:\n        try:\n            links.append((p.name, json.loads(p.read_text(encoding="utf-8"))))\n        except Exception as e:\n            return _fail("chain link " + p.name + " parse error: " + str(e))\n\n    for name, link in links:\n        rc = _verify_link_signature(link, "chain/" + name)\n        if rc != 0:\n            return rc\n\n    genesis_count = sum(\n        1 for _, link in links if link.get("prior_digest") is None\n    )\n    if genesis_count != 1:\n        return _fail(\n            "chain has " + str(genesis_count) + " genesis links (links "\n            "without prior_digest); exactly one expected (cycle or "\n            "multiple roots)"\n        )\n    if links[0][1].get("prior_digest") is not None:\n        return _fail(\n            "chain/" + links[0][0] + " declares a prior_digest; the chain "\n            "is truncated (the oldest link shown is not genesis)"\n        )\n\n    seen_digests = set()\n    ordered = links + [("manifest.json (current)", current_manifest)]\n    for i in range(len(ordered)):\n        name_i, link_i = ordered[i]\n        digest_i = hashlib.sha256(\n            _canonical_body_bytes(link_i)\n        ).hexdigest()\n        if digest_i in seen_digests:\n            return _fail(\n                "cycle detected: " + name_i + " has a canonical digest "\n                "already seen earlier in the chain"\n            )\n        seen_digests.add(digest_i)\n\n    for i in range(1, len(ordered)):\n        name_prev, link_prev = ordered[i - 1]\n        name_cur, link_cur = ordered[i]\n        prev_digest = hashlib.sha256(\n            _canonical_body_bytes(link_prev)\n        ).hexdigest()\n        declared = link_cur.get("prior_digest")\n        if declared != prev_digest:\n            return _fail(\n                "chain broken at " + name_cur + ": declared prior_digest "\n                + str(declared)[:16] + "... does not match sha256 of "\n                + name_prev + " canonical body " + prev_digest[:16] + "..."\n            )\n        moved = [\n            f for f in _SHA_BEARING_FIELDS\n            if link_cur.get(f) != link_prev.get(f)\n        ]\n        if not moved:\n            return _fail(\n                "no-op re-binding at " + name_cur + ": no sha-bearing field "\n                "moved vs " + name_prev + " (a material change must alter at "\n                "least one of " + ", ".join(_SHA_BEARING_FIELDS) + ")"\n            )\n\n    print(\n        "OK   chain walk verified: " + str(len(links)) + " prior link(s), "\n        "rooted at genesis, each a real build change (no-trust, offline)"\n    )\n    rc_mono = _walk_monotonicity(ordered)\n    if rc_mono != 0:\n        return rc_mono\n    return 0\n\n\ndef main():\n    try:\n        from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n            Ed25519PublicKey,\n        )\n        from cryptography.exceptions import InvalidSignature\n    except ImportError:\n        print(\n            "ERROR: cryptography library required.\\n"\n            "Install: pip install \'cryptography>=42\'",\n            file=sys.stderr,\n        )\n        return 2\n\n    manifest_path = ROOT / "manifest.json"\n    if not manifest_path.is_file():\n        return _fail("manifest.json not found in " + str(ROOT))\n    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))\n\n    sig_block = manifest.get("signature")\n    if not sig_block:\n        return _fail("manifest has no signature block")\n    pub_b64 = sig_block.get("public_key_b64", "")\n    sig_b64 = sig_block.get("signature_b64", "")\n    if not pub_b64 or not sig_b64:\n        return _fail("manifest signature block incomplete")\n\n    body_bytes = _canonical_body_bytes(manifest)\n    try:\n        pub_key = Ed25519PublicKey.from_public_bytes(\n            base64.b64decode(pub_b64)\n        )\n        pub_key.verify(base64.b64decode(sig_b64), body_bytes)\n    except InvalidSignature:\n        return _fail("Ed25519 signature does NOT verify")\n    except Exception as e:\n        return _fail("signature verification error: " + str(e))\n    print("OK   Ed25519 signature verified")\n\n    source_path = ROOT / "source.nous"\n    if not source_path.is_file():\n        return _fail("source.nous not found in " + str(ROOT))\n    src_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()\n    expected = manifest.get("source_sha256", "")\n    if src_sha != expected:\n        return _fail(\n            "source.sha256 mismatch: file=" + src_sha[:16] + "... "\n            "manifest=" + expected[:16] + "..."\n        )\n    print("OK   source.sha256 matches manifest (" + src_sha[:16] + "...)")\n\n    rc_cov = _check_coverage(manifest)\n    if rc_cov != 0:\n        return rc_cov\n\n    rc_chain = _walk_chain(manifest)\n    if rc_chain != 0:\n        return rc_chain\n\n    print()\n    print(\n        "VERDICT: PASS (Ed25519 manifest + envelope-binding chain, "\n        "rooted at genesis, offline, zero issuer trust)"\n    )\n    print("  world:        " + str(manifest.get("world_name", "?")))\n    print(\n        "  cost_cap:     $" + str(manifest.get("cost_cap_usd", "?")) + " USD"\n    )\n    print("  verdict:      " + str(manifest.get("verdict", "?")))\n    print(\n        "  prior_digest: "\n        + str(manifest.get("prior_digest", "?"))[:16] + "..."\n    )\n    print("  solver:       " + str(manifest.get("solver_version", "?")))\n    print("  timestamp:    " + str(manifest.get("timestamp_utc", "?")))\n    return 0\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'  # __s120_chain_verifier_v1__
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


VERIFY_OFFLINE_PY_BUNDLE: str = '#!/usr/bin/env python3\n"""Offline verification of NOUS dossier (Annex IV) via Farkas DNF bundle.\n\nUsage: python3 verify_offline.py\nExit:  0 = PASS, 1 = FAIL, 2 = environment error.\n\nRequires: cryptography (for the Ed25519 author signature only). The\ncoverage claim itself is checked by RATIONAL ARITHMETIC ALONE (fractions,\nstdlib) -- no solver, no NOUS install. z3 is used only as an optional\nsecond opinion if it happens to be installed.\n\nThis dossier\'s blocking net contains boolean structure (&& / || / !\nover linear comparisons). Coverage is proven by case-split: the gap\nsearch T && NOT(B_1) && ... && NOT(B_n) is expanded to disjunctive\nnormal form, and EVERY disjunct must be refuted by its own Farkas\ncertificate. This verifier does NOT trust the bundle\'s enumeration:\nit RE-DERIVES the disjunct set from the SIGNED source (source.nous,\nsha-gated by the signed manifest) and the sha-gated threshold\nexpression, then requires a BIJECTION -- exactly one valid certificate\nper derived disjunct. A bundle that omits the gap disjunct, carries a\nsurplus or duplicate certificate, substitutes a constraint, or forges\na multiplier FAILS. Boolean ENUMERATION from signed source, never\nboolean solving; the verifier stays solver-free.\n\nChecks, in order, fail-closed:\n  1. Ed25519 signature over canonical manifest body bytes.\n  2. source.nous sha256 == manifest.source_sha256.\n  3. coverage.smt2 sha256 == manifest.coverage_smt2_sha256 (the human-\n     inspectable obligation; O(1) crypto provenance gate).\n  4. coverage.farkas.json sha256 == manifest.coverage_farkas_sha256\n     (O(1) crypto gate BEFORE any arithmetic; authenticates the\n     threshold expression the bundle was issued for).\n  5. Independent re-derivation of the gap disjunct set from the signed\n     source + bijection + per-disjunct Farkas multiplier check. Pure\n     fractions. PROVES the coverage claim with ZERO issuer trust and\n     ZERO solver trust.\n  6. z3 unsat re-check on coverage.smt2 -- OPTIONAL second opinion,\n     skipped gracefully if z3 is absent.\n__s124_bundle_verifier_v1__\n"""\nfrom __future__ import annotations\n\nimport base64\nimport hashlib\nimport json\nimport sys\nfrom pathlib import Path\n\nROOT = Path(__file__).parent\n\n\ndef _fail(msg):\n    print("FAIL: " + msg, file=sys.stderr)\n    return 1\n\n\n' + _MINILANG_CORE_EMBED + '\n\n\n# --- farkas embed (shared text; mirrors coverage_farkas.py exactly) ---\n# Standalone copies of the linear-translation, NNF/DNF, canonical-form,\n# and multiplier-check logic from coverage_farkas.py. fractions only.\n# __s124_farkas_embed_v1__\n\nfrom fractions import Fraction\n\n\nclass FarkasError(ValueError):\n    pass\n\n\nclass LinIneq:\n    def __init__(self, coeffs, strict):\n        self.coeffs = coeffs\n        self.strict = strict\n\n\nDISJUNCT_BOUND = 64\n\n_FLIP_OP = {">": "<=", ">=": "<", "<": ">=", "<=": ">"}\n\n_CMP_OPS = (">", ">=", "<", "<=")\n\n\ndef _num(node):\n    if isinstance(node, bool):\n        return None\n    if isinstance(node, int):\n        return Fraction(node)\n    if isinstance(node, float):\n        return Fraction(node).limit_denominator(10 ** 12)\n    if isinstance(node, dict) and "currency" in node and "amount" in node:\n        return _num(node["amount"])\n    return None\n\n\ndef _linear(node):\n    n = _num(node)\n    if n is not None:\n        return {"": n}\n    if isinstance(node, str):\n        if node[:1] in (\'"\', "\'"):\n            raise FarkasError("string literal outside fragment")\n        return {node: Fraction(1), "": Fraction(0)}\n    if isinstance(node, dict) and node.get("kind") == "binop":\n        op = node.get("op")\n        if op == "+":\n            return _add(_linear(node["left"]), _linear(node["right"]), 1)\n        if op == "-":\n            return _add(_linear(node["left"]), _linear(node["right"]), -1)\n        if op == "*":\n            return _linear_mul(\n                _linear(node["left"]), _linear(node["right"])\n            )\n        raise FarkasError("non-linear operator " + repr(op) + " in term")\n    raise FarkasError(\n        "unsupported term node " + repr(type(node).__name__)\n    )\n\n\ndef _add(a, b, sign):\n    out = dict(a)\n    for k, v in b.items():\n        out[k] = out.get(k, Fraction(0)) + sign * v\n    return out\n\n\ndef _scale(a, s):\n    return {k: v * s for k, v in a.items()}\n\n\ndef _is_const_only(d):\n    return all(k == "" for k in d)\n\n\ndef _linear_mul(a, b):\n    a_const = _is_const_only(a)\n    b_const = _is_const_only(b)\n    if a_const and b_const:\n        return {"": a.get("", Fraction(0)) * b.get("", Fraction(0))}\n    if a_const:\n        return _scale(b, a.get("", Fraction(0)))\n    if b_const:\n        return _scale(a, b.get("", Fraction(0)))\n    raise FarkasError(\n        "bilinear term (variable * variable) outside linear real "\n        "arithmetic (QF_LRA); only constant * variable is admitted"\n    )\n\n\ndef _comparison_to_ineq(node):\n    if not (isinstance(node, dict) and node.get("kind") == "binop"):\n        raise FarkasError("signal is not a single comparison")\n    op = node.get("op")\n    if op not in _CMP_OPS:\n        raise FarkasError(\n            "comparison op " + repr(op) + " outside fragment"\n        )\n    left = _linear(node["left"])\n    right = _linear(node["right"])\n    diff = _add(left, right, -1)\n    if op in ("<", "<="):\n        return LinIneq(coeffs=diff, strict=(op == "<"))\n    return LinIneq(coeffs=_scale(diff, Fraction(-1)), strict=(op == ">"))\n\n\ndef _is_comparison(node):\n    return (\n        isinstance(node, dict)\n        and node.get("kind") == "binop"\n        and node.get("op") in _CMP_OPS\n    )\n\n\ndef _nnf(node, negate):\n    if _is_comparison(node):\n        if not negate:\n            return node\n        flipped = dict(node)\n        flipped["op"] = _FLIP_OP[node["op"]]\n        return flipped\n    if isinstance(node, dict) and node.get("kind") == "not":\n        return _nnf(node["operand"], not negate)\n    if (\n        isinstance(node, dict)\n        and node.get("kind") == "binop"\n        and node.get("op") in ("&&", "and", "||", "or")\n    ):\n        is_and = node.get("op") in ("&&", "and")\n        if negate:\n            is_and = not is_and\n        return {\n            "kind": "binop",\n            "op": "&&" if is_and else "||",\n            "left": _nnf(node["left"], negate),\n            "right": _nnf(node["right"], negate),\n        }\n    raise FarkasError(\n        "signal node outside the disjunctive linear fragment: "\n        + repr(node)\n    )\n\n\ndef _dnf(node, bound):\n    if _is_comparison(node):\n        return [[node]]\n    if isinstance(node, dict) and node.get("kind") == "binop":\n        op = node.get("op")\n        if op == "||":\n            out = _dnf(node["left"], bound) + _dnf(node["right"], bound)\n            if len(out) > bound:\n                raise FarkasError(\n                    "DNF disjunct count exceeds bound " + str(bound)\n                )\n            return out\n        if op == "&&":\n            left = _dnf(node["left"], bound)\n            right = _dnf(node["right"], bound)\n            if len(left) * len(right) > bound:\n                raise FarkasError(\n                    "DNF disjunct count exceeds bound " + str(bound)\n                )\n            return [a + b for a in left for b in right]\n    raise FarkasError("non-NNF node in DNF expansion: " + repr(node))\n\n\ndef _gap_disjuncts(threshold_ast, blocking_signals, bound):\n    conj = _nnf(threshold_ast, False)\n    for sig in blocking_signals:\n        conj = {\n            "kind": "binop",\n            "op": "&&",\n            "left": conj,\n            "right": _nnf(sig, True),\n        }\n    return _dnf(conj, bound)\n\n\ndef _canon_constraint(ineq):\n    return {\n        "coeffs": {k: str(v) for k, v in sorted(ineq.coeffs.items())},\n        "strict": bool(ineq.strict),\n    }\n\n\ndef _canon_json(obj):\n    import json\n\n    return json.dumps(obj, sort_keys=True, separators=(",", ":"))\n\n\ndef _canon_system(comparisons):\n    pairs = []\n    for comp in comparisons:\n        ineq = _comparison_to_ineq(comp)\n        pairs.append((_canon_constraint(ineq), ineq))\n    pairs.sort(key=lambda p: _canon_json(p[0]))\n    return [p[0] for p in pairs], [p[1] for p in pairs]\n\n\ndef _check_multipliers(constraints, multipliers):\n    if not isinstance(constraints, list) or not isinstance(\n        multipliers, list\n    ):\n        return False\n    if len(constraints) != len(multipliers):\n        return False\n    lam = []\n    for m in multipliers:\n        try:\n            lam.append(Fraction(m))\n        except (ValueError, TypeError, ZeroDivisionError):\n            return False\n    if any(x < 0 for x in lam):\n        return False\n    if not any(x > 0 for x in lam):\n        return False\n    combined = {}\n    strict = False\n    for x, c in zip(lam, constraints):\n        if x == 0:\n            continue\n        if not isinstance(c, dict):\n            return False\n        coeffs = c.get("coeffs")\n        if not isinstance(coeffs, dict):\n            return False\n        for k, v in coeffs.items():\n            try:\n                fv = Fraction(v)\n            except (ValueError, TypeError, ZeroDivisionError):\n                return False\n            combined[k] = combined.get(k, Fraction(0)) + x * fv\n        if c.get("strict"):\n            strict = True\n    for k, v in combined.items():\n        if k != "" and v != 0:\n            return False\n    const = combined.get("", Fraction(0))\n    if const > 0:\n        return True\n    if const == 0 and strict:\n        return True\n    return False\n\n\ndef derive_disjunct_constraints(source_text, threshold_expr):\n    """source TEXT + sha-gated threshold expression -> dict of\n    canonical-key -> canonical constraints, one entry per derived gap\n    disjunct (deduplicated). The independent reconstruction of what the\n    bundle must prove."""\n    threshold_ast = ml_parse(threshold_expr)\n    blocking = ml_scan_blocking_signals(source_text)\n    disjuncts = _gap_disjuncts(threshold_ast, blocking, DISJUNCT_BOUND)\n    derived = {}\n    for comps in disjuncts:\n        constraints, _system = _canon_system(comps)\n        derived[_canon_json(constraints)] = constraints\n    return derived\n\n\ndef check_bundle_against_derived(doc, derived):\n    """Bijection + per-disjunct multiplier check of a bundle dict\n    against an independently derived disjunct map. Returns (ok, reason)."""\n    if not isinstance(doc, dict):\n        return (False, "bundle is not a JSON object")\n    if doc.get("fragment") != "disjunctive-linear-bundle":\n        return (False, "bundle fragment is not disjunctive-linear-bundle")\n    cert_list = doc.get("certs")\n    if not isinstance(cert_list, list):\n        return (False, "bundle has no certs array")\n    carried = {}\n    for cert in cert_list:\n        if not isinstance(cert, dict):\n            return (False, "a cert is not a JSON object")\n        cons = cert.get("constraints")\n        mults = cert.get("multipliers")\n        if not isinstance(cons, list) or not isinstance(mults, list):\n            return (False, "a cert lacks constraints or multipliers")\n        norm = []\n        for c in cons:\n            if not isinstance(c, dict):\n                return (False, "a carried constraint is not an object")\n            coeffs = c.get("coeffs")\n            if not isinstance(coeffs, dict):\n                return (False, "a carried constraint has no coeffs")\n            try:\n                norm_coeffs = {\n                    str(k): str(Fraction(v))\n                    for k, v in sorted(coeffs.items())\n                }\n            except (ValueError, TypeError, ZeroDivisionError):\n                return (False, "non-rational carried coefficient")\n            norm.append(\n                {"coeffs": norm_coeffs, "strict": bool(c.get("strict"))}\n            )\n        norm.sort(key=_canon_json)\n        key = _canon_json(norm)\n        if key in carried:\n            return (False, "duplicate certificate for one disjunct")\n        carried[key] = mults\n    missing = set(derived) - set(carried)\n    surplus = set(carried) - set(derived)\n    if missing:\n        return (\n            False,\n            "bundle OMITS " + str(len(missing)) + " derived gap "\n            "disjunct(s) (overclaim-by-omission)",\n        )\n    if surplus:\n        return (\n            False,\n            "bundle carries " + str(len(surplus)) + " certificate(s) for "\n            "disjuncts that do not derive from the signed source",\n        )\n    for key, constraints in derived.items():\n        if not _check_multipliers(constraints, carried[key]):\n            return (\n                False,\n                "a certificate\'s multipliers do not collapse its derived "\n                "disjunct to a contradiction (coverage gap or forged "\n                "certificate)",\n            )\n    return (True, "")\n# --- end farkas embed ---\n\n\n\ndef main():\n    try:\n        from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n            Ed25519PublicKey,\n        )\n        from cryptography.exceptions import InvalidSignature\n    except ImportError:\n        print(\n            "ERROR: cryptography library required.\\n"\n            "Install: pip install \'cryptography>=42\'",\n            file=sys.stderr,\n        )\n        return 2\n\n    manifest_path = ROOT / "manifest.json"\n    if not manifest_path.is_file():\n        return _fail("manifest.json not found in " + str(ROOT))\n    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))\n\n    sig_block = manifest.get("signature")\n    if not sig_block:\n        return _fail("manifest has no signature block")\n    pub_b64 = sig_block.get("public_key_b64", "")\n    sig_b64 = sig_block.get("signature_b64", "")\n    if not pub_b64 or not sig_b64:\n        return _fail("manifest signature block incomplete")\n\n    body = {k: v for k, v in manifest.items() if k != "signature"}\n    body_bytes = json.dumps(\n        body, sort_keys=True, separators=(",", ":")\n    ).encode("utf-8")\n\n    try:\n        pub_key = Ed25519PublicKey.from_public_bytes(\n            base64.b64decode(pub_b64)\n        )\n        pub_key.verify(base64.b64decode(sig_b64), body_bytes)\n    except InvalidSignature:\n        return _fail("Ed25519 signature does NOT verify")\n    except Exception as e:\n        return _fail("signature verification error: " + str(e))\n    print("OK   Ed25519 signature verified")\n\n    source_path = ROOT / "source.nous"\n    if not source_path.is_file():\n        return _fail("source.nous not found in " + str(ROOT))\n    source_bytes = source_path.read_bytes()\n    src_sha = hashlib.sha256(source_bytes).hexdigest()\n    expected = manifest.get("source_sha256", "")\n    if src_sha != expected:\n        return _fail(\n            "source.sha256 mismatch: file=" + src_sha[:16] + "... "\n            "manifest=" + expected[:16] + "..."\n        )\n    print("OK   source.sha256 matches manifest (" + src_sha[:16] + "...)")\n\n    smt2_expected = manifest.get("coverage_smt2_sha256", "")\n    if smt2_expected:\n        smt2_path = ROOT / "coverage.smt2"\n        if not smt2_path.is_file():\n            return _fail("coverage.smt2 not found in " + str(ROOT))\n        smt2_sha = hashlib.sha256(smt2_path.read_bytes()).hexdigest()\n        if smt2_sha != smt2_expected:\n            return _fail(\n                "coverage.smt2 sha256 mismatch: file=" + smt2_sha[:16]\n                + "... manifest=" + smt2_expected[:16] + "..."\n            )\n        print(\n            "OK   coverage.smt2 sha256 matches manifest ("\n            + smt2_sha[:16] + "...)"\n        )\n\n    farkas_expected = manifest.get("coverage_farkas_sha256", "")\n    if not farkas_expected:\n        return _fail(\n            "manifest has no coverage_farkas_sha256; this verifier ships "\n            "with a bundle-bearing dossier and expects the field"\n        )\n    farkas_path = ROOT / "coverage.farkas.json"\n    if not farkas_path.is_file():\n        return _fail("coverage.farkas.json not found in " + str(ROOT))\n    farkas_bytes = farkas_path.read_bytes()\n    farkas_sha = hashlib.sha256(farkas_bytes).hexdigest()\n    if farkas_sha != farkas_expected:\n        return _fail(\n            "coverage.farkas.json sha256 mismatch: file=" + farkas_sha[:16]\n            + "... manifest=" + farkas_expected[:16]\n            + "... (Farkas bundle tampered or substituted)"\n        )\n    print(\n        "OK   coverage.farkas.json sha256 matches manifest ("\n        + farkas_sha[:16] + "...)"\n    )\n\n    try:\n        farkas_doc = json.loads(farkas_bytes.decode("utf-8"))\n    except Exception as e:\n        return _fail("coverage.farkas.json parse error: " + str(e))\n    threshold_expr = farkas_doc.get("threshold_expr")\n    if not isinstance(threshold_expr, str) or not threshold_expr:\n        return _fail(\n            "bundle carries no threshold_expr; the obligation cannot be "\n            "independently re-derived"\n        )\n\n    try:\n        derived = derive_disjunct_constraints(\n            source_bytes.decode("utf-8"), threshold_expr\n        )\n    except (MinilangError, FarkasError) as e:\n        return _fail(\n            "independent re-derivation from the signed source REFUSED: "\n            + str(e) + " (the obligation cannot be certified offline; "\n            "treat as unverified)"\n        )\n    ok, reason = check_bundle_against_derived(farkas_doc, derived)\n    if not ok:\n        return _fail("Farkas bundle does NOT prove coverage: " + reason)\n    print(\n        "OK   Farkas bundle verified by rational arithmetic, no solver: "\n        + str(len(derived)) + " gap disjunct(s) independently re-derived "\n        "from the signed source, bijection holds, every disjunct refuted"\n    )\n\n    try:\n        import z3\n        smt2_path = ROOT / "coverage.smt2"\n        if smt2_path.is_file():\n            solver = z3.Solver()\n            solver.from_string(smt2_path.read_bytes().decode("utf-8"))\n            res = solver.check()\n            if str(res) != "unsat":\n                return _fail(\n                    "z3 second opinion DISAGREES: coverage.smt2 returned "\n                    + str(res) + " (expected unsat); investigate"\n                )\n            print("OK   z3 second opinion agrees: coverage.smt2 unsat")\n    except ImportError:\n        print(\n            "NOTE z3 not installed; the bundle arithmetic proof above is "\n            "sufficient (no solver needed for the coverage claim)"\n        )\n    except Exception as e:\n        print("NOTE z3 second opinion skipped: " + str(e))\n\n    print()\n    print(\n        "VERDICT: PASS (Ed25519 manifest + Farkas DNF bundle, disjuncts "\n        "re-derived from signed source, stdlib-checked, zero issuer trust)"\n    )\n    print("  world:         " + str(manifest.get("world_name", "?")))\n    print(\n        "  cost_cap:      $" + str(manifest.get("cost_cap_usd", "?"))\n        + " USD"\n    )\n    print("  verdict:       " + str(manifest.get("verdict", "?")))\n    print("  threshold:     " + str(threshold_expr))\n    print("  disjuncts:     " + str(len(derived)) + " (all refuted)")\n    print(\n        "  coverage_sha:  "\n        + str(manifest.get("policy_coverage_sha256", "?"))[:16] + "..."\n    )\n    print("  solver:        " + str(manifest.get("solver_version", "?")))\n    print("  timestamp:     " + str(manifest.get("timestamp_utc", "?")))\n    return 0\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'  # __s124_dossier_bundle_v1__

VERIFY_OFFLINE_PY_FARKAS: str = '#!/usr/bin/env python3\n"""Offline verification of NOUS dossier (Annex IV) via Farkas certificate.\n\nUsage: python3 verify_offline.py\nExit:  0 = PASS, 1 = FAIL, 2 = environment error.\n\nRequires: cryptography (for the Ed25519 author signature only). The\ncoverage claim itself is checked by RATIONAL ARITHMETIC ALONE (fractions,\nstdlib) -- no solver, no NOUS install, no external dependency. z3 is used\nonly as an optional second opinion if it happens to be installed.\n\nChecks, in order, fail-closed:\n  1. Ed25519 signature over canonical manifest body bytes.\n  2. source.nous sha256 == manifest.source_sha256.\n  3. coverage.smt2 sha256 == manifest.coverage_smt2_sha256 (the human-\n     inspectable obligation; O(1) crypto provenance gate).\n  4. coverage.farkas.json sha256 == manifest.coverage_farkas_sha256\n     (O(1) crypto gate BEFORE any arithmetic).\n  5. Farkas certificate: non-negative multipliers collapse the declared\n     linear system to a numeric contradiction. Pure fractions. This PROVES\n     the coverage claim (no gap) with ZERO solver trust.\n  6. z3 unsat re-check on coverage.smt2 -- OPTIONAL second opinion, skipped\n     gracefully if z3 is absent.\n"""\nfrom __future__ import annotations\n\nimport base64\nimport hashlib\nimport json\nimport sys\nfrom fractions import Fraction\nfrom pathlib import Path\n\nROOT = Path(__file__).parent\n\n\ndef _fail(msg):\n    print("FAIL: " + msg, file=sys.stderr)\n    return 1\n\n\ndef _check_serialized(doc):\n    constraints = doc.get("constraints")\n    multipliers = doc.get("multipliers")\n    if not isinstance(constraints, list) or not isinstance(multipliers, list):\n        return False\n    if len(constraints) != len(multipliers):\n        return False\n    lam = []\n    for m in multipliers:\n        try:\n            lam.append(Fraction(m))\n        except (ValueError, TypeError, ZeroDivisionError):\n            return False\n    if any(x < 0 for x in lam):\n        return False\n    if not any(x > 0 for x in lam):\n        return False\n    combined = {}\n    strict = False\n    for x, c in zip(lam, constraints):\n        if x == 0:\n            continue\n        if not isinstance(c, dict):\n            return False\n        coeffs = c.get("coeffs")\n        if not isinstance(coeffs, dict):\n            return False\n        for k, v in coeffs.items():\n            try:\n                fv = Fraction(v)\n            except (ValueError, TypeError, ZeroDivisionError):\n                return False\n            combined[k] = combined.get(k, Fraction(0)) + x * fv\n        if c.get("strict"):\n            strict = True\n    for k, v in combined.items():\n        if k != "" and v != 0:\n            return False\n    const = combined.get("", Fraction(0))\n    if const > 0:\n        return True\n    if const == 0 and strict:\n        return True\n    return False\n\n\ndef main():\n    try:\n        from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n            Ed25519PublicKey,\n        )\n        from cryptography.exceptions import InvalidSignature\n    except ImportError:\n        print(\n            "ERROR: cryptography library required.\\n"\n            "Install: pip install \'cryptography>=42\'",\n            file=sys.stderr,\n        )\n        return 2\n\n    manifest_path = ROOT / "manifest.json"\n    if not manifest_path.is_file():\n        return _fail("manifest.json not found in " + str(ROOT))\n    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))\n\n    sig_block = manifest.get("signature")\n    if not sig_block:\n        return _fail("manifest has no signature block")\n    pub_b64 = sig_block.get("public_key_b64", "")\n    sig_b64 = sig_block.get("signature_b64", "")\n    if not pub_b64 or not sig_b64:\n        return _fail("manifest signature block incomplete")\n\n    body = {k: v for k, v in manifest.items() if k != "signature"}\n    body_bytes = json.dumps(\n        body, sort_keys=True, separators=(",", ":")\n    ).encode("utf-8")\n\n    try:\n        pub_key = Ed25519PublicKey.from_public_bytes(\n            base64.b64decode(pub_b64)\n        )\n        pub_key.verify(base64.b64decode(sig_b64), body_bytes)\n    except InvalidSignature:\n        return _fail("Ed25519 signature does NOT verify")\n    except Exception as e:\n        return _fail("signature verification error: " + str(e))\n    print("OK   Ed25519 signature verified")\n\n    source_path = ROOT / "source.nous"\n    if not source_path.is_file():\n        return _fail("source.nous not found in " + str(ROOT))\n    src_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()\n    expected = manifest.get("source_sha256", "")\n    if src_sha != expected:\n        return _fail(\n            "source.sha256 mismatch: file=" + src_sha[:16] + "... "\n            "manifest=" + expected[:16] + "..."\n        )\n    print("OK   source.sha256 matches manifest (" + src_sha[:16] + "...)")\n\n    smt2_expected = manifest.get("coverage_smt2_sha256", "")\n    if smt2_expected:\n        smt2_path = ROOT / "coverage.smt2"\n        if not smt2_path.is_file():\n            return _fail("coverage.smt2 not found in " + str(ROOT))\n        smt2_sha = hashlib.sha256(smt2_path.read_bytes()).hexdigest()\n        if smt2_sha != smt2_expected:\n            return _fail(\n                "coverage.smt2 sha256 mismatch: file=" + smt2_sha[:16]\n                + "... manifest=" + smt2_expected[:16] + "..."\n            )\n        print(\n            "OK   coverage.smt2 sha256 matches manifest ("\n            + smt2_sha[:16] + "...)"\n        )\n\n    farkas_expected = manifest.get("coverage_farkas_sha256", "")\n    if not farkas_expected:\n        return _fail(\n            "manifest has no coverage_farkas_sha256; this verifier ships "\n            "with a Farkas-bearing dossier and expects the field"\n        )\n    farkas_path = ROOT / "coverage.farkas.json"\n    if not farkas_path.is_file():\n        return _fail("coverage.farkas.json not found in " + str(ROOT))\n    farkas_bytes = farkas_path.read_bytes()\n    farkas_sha = hashlib.sha256(farkas_bytes).hexdigest()\n    if farkas_sha != farkas_expected:\n        return _fail(\n            "coverage.farkas.json sha256 mismatch: file=" + farkas_sha[:16]\n            + "... manifest=" + farkas_expected[:16]\n            + "... (Farkas certificate tampered or substituted)"\n        )\n    print(\n        "OK   coverage.farkas.json sha256 matches manifest ("\n        + farkas_sha[:16] + "...)"\n    )\n\n    try:\n        farkas_doc = json.loads(farkas_bytes.decode("utf-8"))\n    except Exception as e:\n        return _fail("coverage.farkas.json parse error: " + str(e))\n    if not _check_serialized(farkas_doc):\n        return _fail(\n            "Farkas certificate does NOT prove unsat: the declared "\n            "multipliers do not collapse the linear system to a numeric "\n            "contradiction (treat as a coverage gap or a forged certificate)"\n        )\n    print(\n        "OK   Farkas certificate verified by rational arithmetic, no solver "\n        "(contradiction: " + str(farkas_doc.get("contradiction", "?")) + ")"\n    )\n\n    try:\n        import z3\n        smt2_path = ROOT / "coverage.smt2"\n        if smt2_path.is_file():\n            solver = z3.Solver()\n            solver.from_string(smt2_path.read_bytes().decode("utf-8"))\n            res = solver.check()\n            if str(res) != "unsat":\n                return _fail(\n                    "z3 second opinion DISAGREES: coverage.smt2 returned "\n                    + str(res) + " (expected unsat); investigate"\n                )\n            print("OK   z3 second opinion agrees: coverage.smt2 unsat")\n    except ImportError:\n        print(\n            "NOTE z3 not installed; the Farkas arithmetic proof above is "\n            "sufficient (no solver needed for the coverage claim)"\n        )\n    except Exception as e:\n        print("NOTE z3 second opinion skipped: " + str(e))\n\n    print()\n    print(\n        "VERDICT: PASS (Ed25519 manifest + Farkas coverage certificate, "\n        "stdlib-checked, no solver trust)"\n    )\n    print("  world:         " + str(manifest.get("world_name", "?")))\n    print(\n        "  cost_cap:      $" + str(manifest.get("cost_cap_usd", "?")) + " USD"\n    )\n    print("  verdict:       " + str(manifest.get("verdict", "?")))\n    print(\n        "  threshold:     " + str(farkas_doc.get("threshold_expr", "?"))\n    )\n    print(\n        "  contradiction: " + str(farkas_doc.get("contradiction", "?"))\n    )\n    print(\n        "  coverage_sha:  "\n        + str(manifest.get("policy_coverage_sha256", "?"))[:16] + "..."\n    )\n    print("  solver:        " + str(manifest.get("solver_version", "?")))\n    print("  timestamp:     " + str(manifest.get("timestamp_utc", "?")))\n    return 0\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'  # __s116_dossier_farkas_v1__


VERIFY_OFFLINE_PY_COVERAGE: str = '#!/usr/bin/env python3\n"""Offline verification of NOUS dossier (Annex IV) with coverage proof.\n\nUsage: python3 verify_offline.py\nExit:  0 = PASS, 1 = FAIL, 2 = environment error (e.g. z3 missing).\nRequires: cryptography (always); z3-solver (only for the coverage step).\n\nChecks, in order, fail-closed:\n  1. Ed25519 signature over canonical manifest body bytes.\n  2. source.nous sha256 == manifest.source_sha256.\n  3. coverage.smt2 sha256 == manifest.coverage_smt2_sha256  (O(1) crypto\n     provenance gate: proves the .smt2 is exactly what was signed, BEFORE\n     any solver runs -- blocks the tampered-but-still-unsat substitution).\n  4. z3 over coverage.smt2 returns unsat (the coverage claim: no input\n     crossing the declared threshold escapes a blocking policy).\n"""\nfrom __future__ import annotations\n\nimport base64\nimport hashlib\nimport json\nimport sys\nfrom pathlib import Path\n\nROOT = Path(__file__).parent\n\n\ndef _fail(msg):\n    print("FAIL: " + msg, file=sys.stderr)\n    return 1\n\n\ndef main():\n    try:\n        from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n            Ed25519PublicKey,\n        )\n        from cryptography.exceptions import InvalidSignature\n    except ImportError:\n        print(\n            "ERROR: cryptography library required.\\n"\n            "Install: pip install \'cryptography>=42\'",\n            file=sys.stderr,\n        )\n        return 2\n\n    manifest_path = ROOT / "manifest.json"\n    if not manifest_path.is_file():\n        return _fail("manifest.json not found in " + str(ROOT))\n    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))\n\n    sig_block = manifest.get("signature")\n    if not sig_block:\n        return _fail("manifest has no signature block")\n    pub_b64 = sig_block.get("public_key_b64", "")\n    sig_b64 = sig_block.get("signature_b64", "")\n    if not pub_b64 or not sig_b64:\n        return _fail("manifest signature block incomplete")\n\n    body = {k: v for k, v in manifest.items() if k != "signature"}\n    body_bytes = json.dumps(\n        body, sort_keys=True, separators=(",", ":")\n    ).encode("utf-8")\n\n    try:\n        pub_key = Ed25519PublicKey.from_public_bytes(\n            base64.b64decode(pub_b64)\n        )\n        pub_key.verify(base64.b64decode(sig_b64), body_bytes)\n    except InvalidSignature:\n        return _fail("Ed25519 signature does NOT verify")\n    except Exception as e:\n        return _fail("signature verification error: " + str(e))\n    print("OK   Ed25519 signature verified")\n\n    source_path = ROOT / "source.nous"\n    if not source_path.is_file():\n        return _fail("source.nous not found in " + str(ROOT))\n    src_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()\n    expected = manifest.get("source_sha256", "")\n    if src_sha != expected:\n        return _fail(\n            "source.sha256 mismatch: file=" + src_sha[:16] + "... "\n            "manifest=" + expected[:16] + "..."\n        )\n    print("OK   source.sha256 matches manifest (" + src_sha[:16] + "...)")\n\n    cov_expected = manifest.get("coverage_smt2_sha256", "")\n    if not cov_expected:\n        return _fail(\n            "manifest has no coverage_smt2_sha256; this verifier ships "\n            "with a coverage-bearing dossier and expects the field"\n        )\n    cov_path = ROOT / "coverage.smt2"\n    if not cov_path.is_file():\n        return _fail("coverage.smt2 not found in " + str(ROOT))\n    cov_bytes = cov_path.read_bytes()\n    cov_sha = hashlib.sha256(cov_bytes).hexdigest()\n    if cov_sha != cov_expected:\n        return _fail(\n            "coverage.smt2 sha256 mismatch: file=" + cov_sha[:16] + "... "\n            "manifest=" + cov_expected[:16] + "... "\n            "(the coverage proof was tampered or substituted)"\n        )\n    print("OK   coverage.smt2 sha256 matches manifest (" + cov_sha[:16]\n          + "...)")\n\n    try:\n        import z3\n    except ImportError:\n        print(\n            "ERROR: z3-solver required to check the coverage proof.\\n"\n            "Install: pip install z3-solver\\n"\n            "The crypto provenance gate above already PASSED; only the "\n            "semantic unsat re-check is skipped.",\n            file=sys.stderr,\n        )\n        return 2\n\n    solver = z3.Solver()\n    try:\n        solver.from_string(cov_bytes.decode("utf-8"))\n    except z3.Z3Exception as e:\n        return _fail("z3 parse error on coverage.smt2: " + str(e))\n    res = solver.check()\n    if str(res) != "unsat":\n        return _fail(\n            "coverage proof did NOT reproduce unsat (z3 returned "\n            + str(res) + "); the signed claim does not hold under this "\n            "solver -- treat as a coverage gap"\n        )\n    print("OK   z3 reproduced unsat: coverage proof holds (no gap)")\n\n    print()\n    print("VERDICT: PASS (Ed25519 manifest + coverage proof)")\n    print("  world:        " + str(manifest.get("world_name", "?")))\n    print("  cost_cap:     $" + str(manifest.get("cost_cap_usd", "?"))\n          + " USD")\n    print("  verdict:      " + str(manifest.get("verdict", "?")))\n    print("  coverage_sha: "\n          + str(manifest.get("policy_coverage_sha256", "?"))[:16] + "...")\n    print("  solver:       " + str(manifest.get("solver_version", "?")))\n    print("  timestamp:    " + str(manifest.get("timestamp_utc", "?")))\n    return 0\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'  # __s115_dossier_coverage_v1__


def build_dossier(
    source: Path,
    *,
    manifest: Optional[Path] = None,
    prices: Optional[Path] = None,
    output: Optional[Path] = None,
    today: Optional[date] = None,
    anchor: str = "none",
    supersedes: Optional[Path] = None,  # __s120_chain_carry_v1__
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
    verify_path.chmod(0o755)
    files.append("verify_offline.py")

    return DossierResult(
        output_dir=output,
        files=tuple(files),
        world_name=parsed_manifest.world_name,
        verdict=parsed_manifest.verdict,
        safety_margin_pct=parsed_manifest.safety_margin_pct,
    )


VERIFY_OFFLINE_PY_CHAIN_BUNDLE: str = '#!/usr/bin/env python3\n"""Offline verification of NOUS dossier (Annex IV): an envelope-binding\nchain whose CURRENT link carries a coverage proof that may be a Farkas DNF\nbundle (boolean blocking net) or a v1 single-comparison Farkas certificate.\n\nUsage: python3 verify_offline.py\nExit:  0 = PASS, 1 = FAIL, 2 = environment error.\n\nRequires: cryptography (Ed25519 author signatures). The coverage claim is\nchecked by RATIONAL ARITHMETIC ALONE (fractions, stdlib): a Farkas DNF\nbundle is verified by RE-DERIVING the gap disjunct set from the SIGNED\nsource.nous and the sha-gated threshold expression, requiring a bijection\nagainst the carried certificates and checking every multiplier; a v1\ncertificate is verified directly. No solver is required; z3 is an optional\nsecond opinion only. The chain walk uses cryptography + stdlib only.\n\nThis verifier proves the CURRENT link\'s coverage claim with zero issuer\ntrust and zero solver trust, and verifies an unbroken sequence of\nsignature-valid formation envelopes, each declaring its predecessor by\ndigest, each a real build change, rooted at genesis. Across hops it asserts\ncoverage-region MONOTONICITY by hop-containment Farkas bundles: per hop,\nregion(T_prev) subset-of region(T_cur) is proven by refuting every DNF\ndisjunct of T_prev AND NOT(T_cur), where both threshold expressions are\nread from the two links\' sha-gated Farkas sidecars (never from the hop\nbundle) and the disjunct set is RE-DERIVED independently. Boolean\nthresholds are admitted. It does NOT re-prove PRIOR links\' coverage\ncompleteness (no per-link source is carried), does NOT prove execution\nconformance, and does NOT prove the latest envelope is safer.\n\nChecks, in order, fail-closed:\n  1. Ed25519 signature over the current manifest\'s canonical body bytes.\n  2. source.nous sha256 == manifest.source_sha256.\n  3. Current-link coverage: a bundle (re-derive disjuncts from the signed\n     source, bijection, per-disjunct multiplier check) or a v1 certificate,\n     each gated by an O(1) coverage.farkas.json sha match; optional z3\n     second opinion on coverage.smt2.\n  4. Chain walk over chain/ (prior manifests only), six fail-closed\n     conditions: per-link signature, missing chain, altered link, truncated\n     / no-genesis, no-op re-binding, and cycle / more-than-one-genesis.\n  5. Coverage-region monotonicity: per hop where both links declare\n     coverage, region containment is proven by a hop-containment Farkas\n     bundle (chain/NNN_hop.farkas.json): the obligation is re-derived\n     from the two sha-gated threshold expressions, a bijection is\n     required, and every disjunct is refuted by rational arithmetic.\n     Boolean thresholds are admitted.\n  __s125_chain_bundle_walk_v1__ __s126_hop_walk_v1__\n"""\nfrom __future__ import annotations\n\nimport base64\nimport hashlib\nimport json\nimport sys\nfrom pathlib import Path\n\nROOT = Path(__file__).parent\n\n_SHA_BEARING_FIELDS = (\n    "source_sha256",\n    "pricing_sha256",\n    "smt_spec_sha256",\n    "cost_cap_usd",\n    "max_ticks",\n)\n\n\ndef _fail(msg):\n    print("FAIL: " + msg, file=sys.stderr)\n    return 1\n\n\ndef _canonical_body_bytes(m):\n    body = {\n        k: v for k, v in m.items()\n        if k not in ("signature", "transparency_log")\n    }\n    return json.dumps(\n        body, sort_keys=True, separators=(",", ":")\n    ).encode("utf-8")\n\n\ndef _verify_link_signature(link, label):\n    from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n        Ed25519PublicKey,\n    )\n    from cryptography.exceptions import InvalidSignature\n\n    sig_block = link.get("signature")\n    if not isinstance(sig_block, dict):\n        return _fail(label + " has no signature block")\n    pub_b64 = sig_block.get("public_key_b64", "")\n    sig_b64 = sig_block.get("signature_b64", "")\n    if not pub_b64 or not sig_b64:\n        return _fail(label + " signature block incomplete")\n    body_bytes = _canonical_body_bytes(link)\n    try:\n        pub_key = Ed25519PublicKey.from_public_bytes(\n            base64.b64decode(pub_b64)\n        )\n        pub_key.verify(base64.b64decode(sig_b64), body_bytes)\n    except InvalidSignature:\n        return _fail(label + " Ed25519 signature does NOT verify")\n    except Exception as e:\n        return _fail(label + " signature verification error: " + str(e))\n    return 0\n\n\n' + _MINILANG_CORE_EMBED + '\n\n\n# --- farkas embed (shared text; mirrors coverage_farkas.py exactly) ---\n# Standalone copies of the linear-translation, NNF/DNF, canonical-form,\n# and multiplier-check logic from coverage_farkas.py. fractions only.\n# __s124_farkas_embed_v1__\n\nfrom fractions import Fraction\n\n\nclass FarkasError(ValueError):\n    pass\n\n\nclass LinIneq:\n    def __init__(self, coeffs, strict):\n        self.coeffs = coeffs\n        self.strict = strict\n\n\nDISJUNCT_BOUND = 64\n\n_FLIP_OP = {">": "<=", ">=": "<", "<": ">=", "<=": ">"}\n\n_CMP_OPS = (">", ">=", "<", "<=")\n\n\ndef _num(node):\n    if isinstance(node, bool):\n        return None\n    if isinstance(node, int):\n        return Fraction(node)\n    if isinstance(node, float):\n        return Fraction(node).limit_denominator(10 ** 12)\n    if isinstance(node, dict) and "currency" in node and "amount" in node:\n        return _num(node["amount"])\n    return None\n\n\ndef _linear(node):\n    n = _num(node)\n    if n is not None:\n        return {"": n}\n    if isinstance(node, str):\n        if node[:1] in (\'"\', "\'"):\n            raise FarkasError("string literal outside fragment")\n        return {node: Fraction(1), "": Fraction(0)}\n    if isinstance(node, dict) and node.get("kind") == "binop":\n        op = node.get("op")\n        if op == "+":\n            return _add(_linear(node["left"]), _linear(node["right"]), 1)\n        if op == "-":\n            return _add(_linear(node["left"]), _linear(node["right"]), -1)\n        if op == "*":\n            return _linear_mul(\n                _linear(node["left"]), _linear(node["right"])\n            )\n        raise FarkasError("non-linear operator " + repr(op) + " in term")\n    raise FarkasError(\n        "unsupported term node " + repr(type(node).__name__)\n    )\n\n\ndef _add(a, b, sign):\n    out = dict(a)\n    for k, v in b.items():\n        out[k] = out.get(k, Fraction(0)) + sign * v\n    return out\n\n\ndef _scale(a, s):\n    return {k: v * s for k, v in a.items()}\n\n\ndef _is_const_only(d):\n    return all(k == "" for k in d)\n\n\ndef _linear_mul(a, b):\n    a_const = _is_const_only(a)\n    b_const = _is_const_only(b)\n    if a_const and b_const:\n        return {"": a.get("", Fraction(0)) * b.get("", Fraction(0))}\n    if a_const:\n        return _scale(b, a.get("", Fraction(0)))\n    if b_const:\n        return _scale(a, b.get("", Fraction(0)))\n    raise FarkasError(\n        "bilinear term (variable * variable) outside linear real "\n        "arithmetic (QF_LRA); only constant * variable is admitted"\n    )\n\n\ndef _comparison_to_ineq(node):\n    if not (isinstance(node, dict) and node.get("kind") == "binop"):\n        raise FarkasError("signal is not a single comparison")\n    op = node.get("op")\n    if op not in _CMP_OPS:\n        raise FarkasError(\n            "comparison op " + repr(op) + " outside fragment"\n        )\n    left = _linear(node["left"])\n    right = _linear(node["right"])\n    diff = _add(left, right, -1)\n    if op in ("<", "<="):\n        return LinIneq(coeffs=diff, strict=(op == "<"))\n    return LinIneq(coeffs=_scale(diff, Fraction(-1)), strict=(op == ">"))\n\n\ndef _is_comparison(node):\n    return (\n        isinstance(node, dict)\n        and node.get("kind") == "binop"\n        and node.get("op") in _CMP_OPS\n    )\n\n\ndef _nnf(node, negate):\n    if _is_comparison(node):\n        if not negate:\n            return node\n        flipped = dict(node)\n        flipped["op"] = _FLIP_OP[node["op"]]\n        return flipped\n    if isinstance(node, dict) and node.get("kind") == "not":\n        return _nnf(node["operand"], not negate)\n    if (\n        isinstance(node, dict)\n        and node.get("kind") == "binop"\n        and node.get("op") in ("&&", "and", "||", "or")\n    ):\n        is_and = node.get("op") in ("&&", "and")\n        if negate:\n            is_and = not is_and\n        return {\n            "kind": "binop",\n            "op": "&&" if is_and else "||",\n            "left": _nnf(node["left"], negate),\n            "right": _nnf(node["right"], negate),\n        }\n    raise FarkasError(\n        "signal node outside the disjunctive linear fragment: "\n        + repr(node)\n    )\n\n\ndef _dnf(node, bound):\n    if _is_comparison(node):\n        return [[node]]\n    if isinstance(node, dict) and node.get("kind") == "binop":\n        op = node.get("op")\n        if op == "||":\n            out = _dnf(node["left"], bound) + _dnf(node["right"], bound)\n            if len(out) > bound:\n                raise FarkasError(\n                    "DNF disjunct count exceeds bound " + str(bound)\n                )\n            return out\n        if op == "&&":\n            left = _dnf(node["left"], bound)\n            right = _dnf(node["right"], bound)\n            if len(left) * len(right) > bound:\n                raise FarkasError(\n                    "DNF disjunct count exceeds bound " + str(bound)\n                )\n            return [a + b for a in left for b in right]\n    raise FarkasError("non-NNF node in DNF expansion: " + repr(node))\n\n\ndef _gap_disjuncts(threshold_ast, blocking_signals, bound):\n    conj = _nnf(threshold_ast, False)\n    for sig in blocking_signals:\n        conj = {\n            "kind": "binop",\n            "op": "&&",\n            "left": conj,\n            "right": _nnf(sig, True),\n        }\n    return _dnf(conj, bound)\n\n\ndef _canon_constraint(ineq):\n    return {\n        "coeffs": {k: str(v) for k, v in sorted(ineq.coeffs.items())},\n        "strict": bool(ineq.strict),\n    }\n\n\ndef _canon_json(obj):\n    import json\n\n    return json.dumps(obj, sort_keys=True, separators=(",", ":"))\n\n\ndef _canon_system(comparisons):\n    pairs = []\n    for comp in comparisons:\n        ineq = _comparison_to_ineq(comp)\n        pairs.append((_canon_constraint(ineq), ineq))\n    pairs.sort(key=lambda p: _canon_json(p[0]))\n    return [p[0] for p in pairs], [p[1] for p in pairs]\n\n\ndef _check_multipliers(constraints, multipliers):\n    if not isinstance(constraints, list) or not isinstance(\n        multipliers, list\n    ):\n        return False\n    if len(constraints) != len(multipliers):\n        return False\n    lam = []\n    for m in multipliers:\n        try:\n            lam.append(Fraction(m))\n        except (ValueError, TypeError, ZeroDivisionError):\n            return False\n    if any(x < 0 for x in lam):\n        return False\n    if not any(x > 0 for x in lam):\n        return False\n    combined = {}\n    strict = False\n    for x, c in zip(lam, constraints):\n        if x == 0:\n            continue\n        if not isinstance(c, dict):\n            return False\n        coeffs = c.get("coeffs")\n        if not isinstance(coeffs, dict):\n            return False\n        for k, v in coeffs.items():\n            try:\n                fv = Fraction(v)\n            except (ValueError, TypeError, ZeroDivisionError):\n                return False\n            combined[k] = combined.get(k, Fraction(0)) + x * fv\n        if c.get("strict"):\n            strict = True\n    for k, v in combined.items():\n        if k != "" and v != 0:\n            return False\n    const = combined.get("", Fraction(0))\n    if const > 0:\n        return True\n    if const == 0 and strict:\n        return True\n    return False\n\n\ndef derive_disjunct_constraints(source_text, threshold_expr):\n    """source TEXT + sha-gated threshold expression -> dict of\n    canonical-key -> canonical constraints, one entry per derived gap\n    disjunct (deduplicated). The independent reconstruction of what the\n    bundle must prove."""\n    threshold_ast = ml_parse(threshold_expr)\n    blocking = ml_scan_blocking_signals(source_text)\n    disjuncts = _gap_disjuncts(threshold_ast, blocking, DISJUNCT_BOUND)\n    derived = {}\n    for comps in disjuncts:\n        constraints, _system = _canon_system(comps)\n        derived[_canon_json(constraints)] = constraints\n    return derived\n\n\ndef check_bundle_against_derived(doc, derived):\n    """Bijection + per-disjunct multiplier check of a bundle dict\n    against an independently derived disjunct map. Returns (ok, reason)."""\n    if not isinstance(doc, dict):\n        return (False, "bundle is not a JSON object")\n    if doc.get("fragment") != "disjunctive-linear-bundle":\n        return (False, "bundle fragment is not disjunctive-linear-bundle")\n    cert_list = doc.get("certs")\n    if not isinstance(cert_list, list):\n        return (False, "bundle has no certs array")\n    carried = {}\n    for cert in cert_list:\n        if not isinstance(cert, dict):\n            return (False, "a cert is not a JSON object")\n        cons = cert.get("constraints")\n        mults = cert.get("multipliers")\n        if not isinstance(cons, list) or not isinstance(mults, list):\n            return (False, "a cert lacks constraints or multipliers")\n        norm = []\n        for c in cons:\n            if not isinstance(c, dict):\n                return (False, "a carried constraint is not an object")\n            coeffs = c.get("coeffs")\n            if not isinstance(coeffs, dict):\n                return (False, "a carried constraint has no coeffs")\n            try:\n                norm_coeffs = {\n                    str(k): str(Fraction(v))\n                    for k, v in sorted(coeffs.items())\n                }\n            except (ValueError, TypeError, ZeroDivisionError):\n                return (False, "non-rational carried coefficient")\n            norm.append(\n                {"coeffs": norm_coeffs, "strict": bool(c.get("strict"))}\n            )\n        norm.sort(key=_canon_json)\n        key = _canon_json(norm)\n        if key in carried:\n            return (False, "duplicate certificate for one disjunct")\n        carried[key] = mults\n    missing = set(derived) - set(carried)\n    surplus = set(carried) - set(derived)\n    if missing:\n        return (\n            False,\n            "bundle OMITS " + str(len(missing)) + " derived gap "\n            "disjunct(s) (overclaim-by-omission)",\n        )\n    if surplus:\n        return (\n            False,\n            "bundle carries " + str(len(surplus)) + " certificate(s) for "\n            "disjuncts that do not derive from the signed source",\n        )\n    for key, constraints in derived.items():\n        if not _check_multipliers(constraints, carried[key]):\n            return (\n                False,\n                "a certificate\'s multipliers do not collapse its derived "\n                "disjunct to a contradiction (coverage gap or forged "\n                "certificate)",\n            )\n    return (True, "")\n\n\ndef _hop_disjuncts(prev_ast, cur_ast, bound):\n    # __s126_hop_embed_v1__\n    conj = {\n        "kind": "binop",\n        "op": "&&",\n        "left": _nnf(prev_ast, False),\n        "right": _nnf(cur_ast, True),\n    }\n    return _dnf(conj, bound)\n\n\ndef check_hop_bundle(doc, prev_ast, cur_ast):\n    """Zero-trust check of a hop-containment bundle: the obligation\n    T_prev AND NOT(T_cur) is re-derived from the two authenticated\n    threshold ASTs, a bijection is required against the carried\n    certificates, and every multiplier is checked by rational\n    arithmetic. Returns (ok, reason)."""\n    if not isinstance(doc, dict):\n        return (False, "hop bundle is not a JSON object")\n    if doc.get("fragment") != "hop-containment-bundle":\n        return (False, "hop bundle fragment is not hop-containment-bundle")\n    cert_list = doc.get("certs")\n    if not isinstance(cert_list, list):\n        return (False, "hop bundle has no certs array")\n    try:\n        disjuncts = _hop_disjuncts(prev_ast, cur_ast, DISJUNCT_BOUND)\n    except FarkasError as e:\n        return (False, "hop obligation derivation refused: " + str(e))\n    derived = {}\n    for comps in disjuncts:\n        try:\n            constraints, _system = _canon_system(comps)\n        except FarkasError as e:\n            return (False, "hop obligation derivation refused: " + str(e))\n        derived[_canon_json(constraints)] = constraints\n    carried = {}\n    for cert in cert_list:\n        if not isinstance(cert, dict):\n            return (False, "a hop cert is not a JSON object")\n        cons = cert.get("constraints")\n        mults = cert.get("multipliers")\n        if not isinstance(cons, list) or not isinstance(mults, list):\n            return (False, "a hop cert lacks constraints or multipliers")\n        norm = []\n        for c in cons:\n            if not isinstance(c, dict):\n                return (False, "a carried hop constraint is not an object")\n            coeffs = c.get("coeffs")\n            if not isinstance(coeffs, dict):\n                return (False, "a carried hop constraint has no coeffs")\n            try:\n                norm_coeffs = {\n                    str(k): str(Fraction(v))\n                    for k, v in sorted(coeffs.items())\n                }\n            except (ValueError, TypeError, ZeroDivisionError):\n                return (False, "non-rational carried hop coefficient")\n            norm.append(\n                {"coeffs": norm_coeffs, "strict": bool(c.get("strict"))}\n            )\n        norm.sort(key=_canon_json)\n        key = _canon_json(norm)\n        if key in carried:\n            return (False, "duplicate hop certificate for one disjunct")\n        carried[key] = mults\n    missing = set(derived) - set(carried)\n    surplus = set(carried) - set(derived)\n    if missing:\n        return (\n            False,\n            "hop bundle OMITS " + str(len(missing)) + " derived "\n            "disjunct(s) of T_prev AND NOT(T_cur) "\n            "(overclaim-by-omission)",\n        )\n    if surplus:\n        return (\n            False,\n            "hop bundle carries " + str(len(surplus)) + " certificate(s) "\n            "for disjuncts that do not derive from the authenticated "\n            "threshold expressions",\n        )\n    for key, constraints in derived.items():\n        if not _check_multipliers(constraints, carried[key]):\n            return (\n                False,\n                "a hop certificate\'s multipliers do not collapse its "\n                "derived disjunct to a contradiction (region regression "\n                "or forged certificate)",\n            )\n    return (True, "")\n\n\n# --- end farkas embed ---\n\n\ndef _check_serialized(doc):\n    from fractions import Fraction\n\n    constraints = doc.get("constraints")\n    multipliers = doc.get("multipliers")\n    if not isinstance(constraints, list) or not isinstance(multipliers, list):\n        return False\n    if len(constraints) != len(multipliers):\n        return False\n    lam = []\n    for m in multipliers:\n        try:\n            lam.append(Fraction(m))\n        except (ValueError, TypeError, ZeroDivisionError):\n            return False\n    if any(x < 0 for x in lam):\n        return False\n    if not any(x > 0 for x in lam):\n        return False\n    combined = {}\n    strict = False\n    for x, c in zip(lam, constraints):\n        if x == 0:\n            continue\n        if not isinstance(c, dict):\n            return False\n        coeffs = c.get("coeffs")\n        if not isinstance(coeffs, dict):\n            return False\n        for k, v in coeffs.items():\n            try:\n                fv = Fraction(v)\n            except (ValueError, TypeError, ZeroDivisionError):\n                return False\n            combined[k] = combined.get(k, Fraction(0)) + x * fv\n        if c.get("strict"):\n            strict = True\n    for k, v in combined.items():\n        if k != "" and v != 0:\n            return False\n    const = combined.get("", Fraction(0))\n    if const > 0:\n        return True\n    if const == 0 and strict:\n        return True\n    return False\n\n\ndef _check_coverage(manifest, source_text):\n    farkas_expected = manifest.get("coverage_farkas_sha256")\n    smt2_expected = manifest.get("coverage_smt2_sha256")\n    cov_sha = manifest.get("policy_coverage_sha256")\n    if not cov_sha and not farkas_expected and not smt2_expected:\n        return 0\n\n    if smt2_expected:\n        smt2_path = ROOT / "coverage.smt2"\n        if not smt2_path.is_file():\n            return _fail("coverage.smt2 not found in " + str(ROOT))\n        smt2_sha = hashlib.sha256(smt2_path.read_bytes()).hexdigest()\n        if smt2_sha != smt2_expected:\n            return _fail(\n                "coverage.smt2 sha256 mismatch: file=" + smt2_sha[:16]\n                + "... manifest=" + smt2_expected[:16] + "..."\n            )\n        print(\n            "OK   coverage.smt2 sha256 matches manifest ("\n            + smt2_sha[:16] + "...)"\n        )\n\n    if farkas_expected:\n        farkas_path = ROOT / "coverage.farkas.json"\n        if not farkas_path.is_file():\n            return _fail("coverage.farkas.json not found in " + str(ROOT))\n        farkas_bytes = farkas_path.read_bytes()\n        farkas_sha = hashlib.sha256(farkas_bytes).hexdigest()\n        if farkas_sha != farkas_expected:\n            return _fail(\n                "coverage.farkas.json sha256 mismatch: file="\n                + farkas_sha[:16] + "... manifest=" + farkas_expected[:16]\n                + "... (Farkas certificate tampered or substituted)"\n            )\n        try:\n            farkas_doc = json.loads(farkas_bytes.decode("utf-8"))\n        except Exception as e:\n            return _fail("coverage.farkas.json parse error: " + str(e))\n        if isinstance(farkas_doc, dict) and farkas_doc.get(\n            "fragment"\n        ) == "disjunctive-linear-bundle":\n            threshold_expr = farkas_doc.get("threshold_expr")\n            if not isinstance(threshold_expr, str) or not threshold_expr:\n                return _fail(\n                    "bundle carries no threshold_expr; the obligation "\n                    "cannot be independently re-derived"\n                )\n            try:\n                derived = derive_disjunct_constraints(\n                    source_text, threshold_expr\n                )\n            except (MinilangError, FarkasError) as e:\n                return _fail(\n                    "independent re-derivation from the signed source "\n                    "REFUSED: " + str(e) + " (the obligation cannot be "\n                    "certified offline; treat as unverified)"\n                )\n            ok, reason = check_bundle_against_derived(farkas_doc, derived)\n            if not ok:\n                return _fail(\n                    "Farkas bundle does NOT prove coverage: " + reason\n                )\n            print(\n                "OK   Farkas bundle verified by rational arithmetic, no "\n                "solver: " + str(len(derived)) + " gap disjunct(s) "\n                "independently re-derived from the signed source, "\n                "bijection holds, every disjunct refuted"\n            )\n            return 0\n        if not _check_serialized(farkas_doc):\n            return _fail(\n                "Farkas certificate does NOT prove unsat: the declared "\n                "multipliers do not collapse the linear system to a numeric "\n                "contradiction (coverage gap or forged certificate)"\n            )\n        print(\n            "OK   Farkas certificate verified by rational arithmetic, no "\n            "solver (contradiction: "\n            + str(farkas_doc.get("contradiction", "?")) + ")"\n        )\n        return 0\n\n    if smt2_expected:\n        try:\n            import z3\n        except ImportError:\n            print(\n                "ERROR: z3-solver required to check the coverage proof.\\n"\n                "Install: pip install z3-solver\\n"\n                "The crypto provenance gate above already PASSED; only the "\n                "semantic unsat re-check is skipped.",\n                file=sys.stderr,\n            )\n            return 2\n        solver = z3.Solver()\n        try:\n            solver.from_string(\n                (ROOT / "coverage.smt2").read_bytes().decode("utf-8")\n            )\n        except z3.Z3Exception as e:\n            return _fail("z3 parse error on coverage.smt2: " + str(e))\n        res = solver.check()\n        if str(res) != "unsat":\n            return _fail(\n                "coverage proof did NOT reproduce unsat (z3 returned "\n                + str(res) + "); treat as a coverage gap"\n            )\n        print("OK   z3 reproduced unsat: coverage proof holds (no gap)")\n    return 0\n\n\ndef _link_farkas_path(name):\n    # Prior links live in chain/NNN_*; the current link\'s farkas is at root.\n    if name == "manifest.json (current)":\n        return ROOT / "coverage.farkas.json"\n    return ROOT / "chain" / name.replace(\n        "_manifest.json", "_coverage.farkas.json"\n    )\n\n\ndef _authenticated_threshold(name, link):\n    # manifest-is-authority: coverage existence is decided by the signed\n    # manifest field, never by file presence. Returns the link\'s\n    # sha-gated threshold EXPRESSION; the hop containment obligation is\n    # re-derived from it, never read from a hop bundle.\n    field = link.get("coverage_farkas_sha256")\n    path = _link_farkas_path(name)\n    if field is None:\n        if path.is_file():\n            return ("refuse", _fail(\n                name + " declares no coverage_farkas_sha256 but a "\n                + path.name + " is present (unexpected evidence)"\n            ))\n        return ("none", None)\n    if not path.is_file():\n        return ("refuse", _fail(\n            name + " signed manifest declares coverage_farkas_sha256 but "\n            + path.name + " is missing (missing evidence / truncation)"\n        ))\n    data = path.read_bytes()\n    if hashlib.sha256(data).hexdigest() != field:\n        return ("refuse", _fail(\n            name + " " + path.name + " sha256 does not match the signed "\n            "manifest coverage_farkas_sha256 (tampered or substituted)"\n        ))\n    try:\n        doc = json.loads(data.decode("utf-8"))\n    except Exception as e:\n        return ("refuse", _fail(\n            name + " " + path.name + " parse error: " + str(e)\n        ))\n    expr = doc.get("threshold_expr") if isinstance(doc, dict) else None\n    if not isinstance(expr, str) or not expr:\n        return ("refuse", _fail(\n            name + " " + path.name + " carries no threshold_expr; the "\n            "hop containment obligation cannot be re-derived"\n        ))\n    return ("has", expr)\n\n\ndef _hop_path(idx):\n    return ROOT / "chain" / (str(idx).zfill(3) + "_hop.farkas.json")\n\n\ndef _walk_monotonicity(ordered):\n    # Composed after the S120 chain walk. ordered is\n    # [(name, link), ... , ("manifest.json (current)", current_manifest)].\n    # Per hop where both links declare coverage, a hop-containment\n    # Farkas bundle chain/NNN_hop.farkas.json (NNN = predecessor index)\n    # must prove region(T_prev) subset-of region(T_cur): the obligation\n    # is RE-DERIVED from the two sha-gated threshold expressions and\n    # every DNF disjunct of T_prev AND NOT(T_cur) must be refuted.\n    # __s126_hop_walk_v1__\n    checked = 0\n    for i in range(1, len(ordered)):\n        name_prev, link_prev = ordered[i - 1]\n        name_cur, link_cur = ordered[i]\n        st_prev, expr_prev = _authenticated_threshold(name_prev, link_prev)\n        if st_prev == "refuse":\n            return expr_prev\n        st_cur, expr_cur = _authenticated_threshold(name_cur, link_cur)\n        if st_cur == "refuse":\n            return expr_cur\n        hop_file = _hop_path(i - 1)\n        if st_cur == "has" and st_prev == "has":\n            if not hop_file.is_file():\n                return _fail(\n                    "hop containment bundle missing: chain/"\n                    + hop_file.name + " (both links declare coverage; "\n                    "the region-containment proof is required, "\n                    "fail-closed)"\n                )\n            try:\n                hop_doc = json.loads(\n                    hop_file.read_bytes().decode("utf-8")\n                )\n            except Exception as e:\n                return _fail(\n                    "chain/" + hop_file.name + " parse error: " + str(e)\n                )\n            try:\n                prev_ast = ml_parse(expr_prev)\n                cur_ast = ml_parse(expr_cur)\n            except MinilangError as e:\n                return _fail(\n                    "hop threshold parse REFUSED at " + name_cur + ": "\n                    + str(e)\n                )\n            ok, reason = check_hop_bundle(hop_doc, prev_ast, cur_ast)\n            if not ok:\n                return _fail(\n                    "coverage REGION REGRESSION or invalid hop proof "\n                    "at " + name_cur + ": " + reason\n                )\n            checked += 1\n        else:\n            if hop_file.is_file():\n                return _fail(\n                    "unexpected hop bundle chain/" + hop_file.name\n                    + ": a hop where a link declares no coverage must "\n                    "carry no hop proof"\n                )\n            if st_cur == "none" and st_prev == "has":\n                return _fail(\n                    "coverage VANISHED at " + name_cur + ": predecessor "\n                    "declares a coverage proof but the current link "\n                    "drops it (dropping coverage across a material "\n                    "change is refused)"\n                )\n        # (has, none) -> net grew from nothing; (none, none) -> skip.\n    if checked:\n        print(\n            "OK   hop containment verified across " + str(checked)\n            + " hop(s): each declared threshold region contains its "\n            "predecessor\'s, obligations re-derived from sha-gated "\n            "threshold expressions, every disjunct refuted (Farkas, "\n            "offline, zero issuer trust)"\n        )\n    return 0\n\n\ndef _walk_chain(current_manifest):\n    prior_digest = current_manifest.get("prior_digest")\n    if prior_digest is None:\n        return _fail(\n            "this verifier expects an envelope-binding chain but the "\n            "current manifest declares no prior_digest"\n        )\n\n    chain_dir = ROOT / "chain"\n    if not chain_dir.is_dir():\n        return _fail(\n            "manifest declares prior_digest but no chain/ directory of "\n            "prior manifests is present (missing chain)"\n        )\n    link_paths = sorted(chain_dir.glob("*_manifest.json"))\n    if not link_paths:\n        return _fail(\n            "manifest declares prior_digest but chain/ contains no "\n            "*_manifest.json links (missing chain)"\n        )\n\n    links = []\n    for p in link_paths:\n        try:\n            links.append((p.name, json.loads(p.read_text(encoding="utf-8"))))\n        except Exception as e:\n            return _fail("chain link " + p.name + " parse error: " + str(e))\n\n    for name, link in links:\n        rc = _verify_link_signature(link, "chain/" + name)\n        if rc != 0:\n            return rc\n\n    genesis_count = sum(\n        1 for _, link in links if link.get("prior_digest") is None\n    )\n    if genesis_count != 1:\n        return _fail(\n            "chain has " + str(genesis_count) + " genesis links (links "\n            "without prior_digest); exactly one expected (cycle or "\n            "multiple roots)"\n        )\n    if links[0][1].get("prior_digest") is not None:\n        return _fail(\n            "chain/" + links[0][0] + " declares a prior_digest; the chain "\n            "is truncated (the oldest link shown is not genesis)"\n        )\n\n    seen_digests = set()\n    ordered = links + [("manifest.json (current)", current_manifest)]\n    for i in range(len(ordered)):\n        name_i, link_i = ordered[i]\n        digest_i = hashlib.sha256(\n            _canonical_body_bytes(link_i)\n        ).hexdigest()\n        if digest_i in seen_digests:\n            return _fail(\n                "cycle detected: " + name_i + " has a canonical digest "\n                "already seen earlier in the chain"\n            )\n        seen_digests.add(digest_i)\n\n    for i in range(1, len(ordered)):\n        name_prev, link_prev = ordered[i - 1]\n        name_cur, link_cur = ordered[i]\n        prev_digest = hashlib.sha256(\n            _canonical_body_bytes(link_prev)\n        ).hexdigest()\n        declared = link_cur.get("prior_digest")\n        if declared != prev_digest:\n            return _fail(\n                "chain broken at " + name_cur + ": declared prior_digest "\n                + str(declared)[:16] + "... does not match sha256 of "\n                + name_prev + " canonical body " + prev_digest[:16] + "..."\n            )\n        moved = [\n            f for f in _SHA_BEARING_FIELDS\n            if link_cur.get(f) != link_prev.get(f)\n        ]\n        if not moved:\n            return _fail(\n                "no-op re-binding at " + name_cur + ": no sha-bearing field "\n                "moved vs " + name_prev + " (a material change must alter at "\n                "least one of " + ", ".join(_SHA_BEARING_FIELDS) + ")"\n            )\n\n    print(\n        "OK   chain walk verified: " + str(len(links)) + " prior link(s), "\n        "rooted at genesis, each a real build change (no-trust, offline)"\n    )\n    rc_mono = _walk_monotonicity(ordered)\n    if rc_mono != 0:\n        return rc_mono\n    return 0\n\n\ndef main():\n    try:\n        from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n            Ed25519PublicKey,\n        )\n        from cryptography.exceptions import InvalidSignature\n    except ImportError:\n        print(\n            "ERROR: cryptography library required.\\n"\n            "Install: pip install \'cryptography>=42\'",\n            file=sys.stderr,\n        )\n        return 2\n\n    manifest_path = ROOT / "manifest.json"\n    if not manifest_path.is_file():\n        return _fail("manifest.json not found in " + str(ROOT))\n    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))\n\n    sig_block = manifest.get("signature")\n    if not sig_block:\n        return _fail("manifest has no signature block")\n    pub_b64 = sig_block.get("public_key_b64", "")\n    sig_b64 = sig_block.get("signature_b64", "")\n    if not pub_b64 or not sig_b64:\n        return _fail("manifest signature block incomplete")\n\n    body_bytes = _canonical_body_bytes(manifest)\n    try:\n        pub_key = Ed25519PublicKey.from_public_bytes(\n            base64.b64decode(pub_b64)\n        )\n        pub_key.verify(base64.b64decode(sig_b64), body_bytes)\n    except InvalidSignature:\n        return _fail("Ed25519 signature does NOT verify")\n    except Exception as e:\n        return _fail("signature verification error: " + str(e))\n    print("OK   Ed25519 signature verified")\n\n    source_path = ROOT / "source.nous"\n    if not source_path.is_file():\n        return _fail("source.nous not found in " + str(ROOT))\n    source_bytes = source_path.read_bytes()\n    src_sha = hashlib.sha256(source_bytes).hexdigest()\n    expected = manifest.get("source_sha256", "")\n    if src_sha != expected:\n        return _fail(\n            "source.sha256 mismatch: file=" + src_sha[:16] + "... "\n            "manifest=" + expected[:16] + "..."\n        )\n    print("OK   source.sha256 matches manifest (" + src_sha[:16] + "...)")\n\n    rc_cov = _check_coverage(manifest, source_bytes.decode("utf-8"))\n    if rc_cov != 0:\n        return rc_cov\n\n    rc_chain = _walk_chain(manifest)\n    if rc_chain != 0:\n        return rc_chain\n\n    print()\n    print(\n        "VERDICT: PASS (Ed25519 manifest + envelope-binding chain + "\n        "current-link coverage re-derived, hop containment proven, "\n        "offline, zero issuer trust)"\n    )\n    print("  world:        " + str(manifest.get("world_name", "?")))\n    print(\n        "  cost_cap:     $" + str(manifest.get("cost_cap_usd", "?")) + " USD"\n    )\n    print("  verdict:      " + str(manifest.get("verdict", "?")))\n    print(\n        "  prior_digest: "\n        + str(manifest.get("prior_digest", "?"))[:16] + "..."\n    )\n    print("  solver:       " + str(manifest.get("solver_version", "?")))\n    print("  timestamp:    " + str(manifest.get("timestamp_utc", "?")))\n    return 0\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'  # __s125_chain_bundle_template_v1__ __s126_hop_walk_v1__


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


def build_chain_net_verifier():
    base = VERIFY_OFFLINE_PY_CHAIN_BUNDLE
    for label, anchor in (
        ("net-embed", _NET_EMBED_ANCHOR),
        ("net-walk", _NET_WALK_ANCHOR),
        ("net-call", _NET_CALL_ANCHOR),
    ):
        if base.count(anchor) != 1:
            raise DossierError(
                "S127 net verifier splice REFUSED: anchor " + label
                + " occurs " + str(base.count(anchor)) + " times in "
                "CHAIN_BUNDLE (expected 1); template drift"
            )
    out = base.replace(
        _NET_EMBED_ANCHOR,
        _NET_EMBED_BLOCK + _GAPW_EMBED_BLOCK + _NET_EMBED_ANCHOR, 1
    )
    out = out.replace(
        _NET_WALK_ANCHOR, _NET_WALK_BLOCK + _NET_WALK_ANCHOR, 1
    )
    _call_repl = (
        "    rc_mono = _walk_monotonicity(ordered)" + _NL_S127
        + "    if rc_mono != 0:" + _NL_S127
        + "        return rc_mono" + _NL_S127
        + _NET_WALK_CALL
        + "    return 0"
    )
    out = out.replace(_NET_CALL_ANCHOR, _call_repl, 1)
    return out
