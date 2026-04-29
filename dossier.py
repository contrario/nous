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
) -> DossierResult:
    """Build an Annex IV-aligned dossier directory."""
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

    (output / "manifest.json").write_text(
        manifest_text, encoding="utf-8"
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
