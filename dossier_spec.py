"""
NOUS dossier_spec --- build Annex IV dossiers from SKILL.md skills.

Pipeline:
  parse_skill_dir(skill_dir) -> ParsedSkill
  translate_to_program(parsed) -> NousProgram
  emit_smt(prog, pricing, source_text=envelope) -> SMTSpec
  verify(spec) -> VerifyResult
  manifest_from_verify(result, nous_version) -> Manifest
  load_or_create_keypair(key_path) -> (priv, pub)
  sign_manifest(m, priv) -> bytes
  manifest_json(m, sig, pub) -> str

Output bundle:
  source.nous          : deterministic envelope bytes (SHA matches manifest)
  manifest.json        : signed manifest (existing schema)
  SKILL.md             : verbatim from input
  nous.yaml            : verbatim from input
  pricing.toml         : copy of resolved pricing layer
  public_key.b64       : Ed25519 public key (base64 raw)
  README.md            : human-readable Annex IV summary
  verify_offline.py    : copy from dossier.VERIFY_OFFLINE_PY (unchanged)

# __session77_dossier_spec_v3__
"""
from __future__ import annotations

import base64
import hashlib
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional


class DossierSpecError(RuntimeError):
    """Raised on any skill_md dossier build failure."""


@dataclass(frozen=True)
class DossierSpecResult:
    output_dir: Path
    files: tuple[str, ...]
    world_name: str
    verdict: str
    safety_margin_pct: Optional[int]


_ENVELOPE_VERSION: str = "1"
_SUPPORTED_CAP_CURRENCIES: frozenset[str] = frozenset({"USD", "EUR"})


def _hex_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_envelope(
    skill_name: str,
    skill_md_bytes: bytes,
    sidecar_bytes: bytes,
    nous_version: str,
) -> bytes:
    skill_sha = _hex_sha256(skill_md_bytes)
    sidecar_sha = _hex_sha256(sidecar_bytes)
    header = (
        f"# NOUS skill_md dossier source envelope v{_ENVELOPE_VERSION}\n"
        f"# name: {skill_name}\n"
        f"# skill_md_sha256: {skill_sha}\n"
        f"# sidecar_sha256: {sidecar_sha}\n"
        f"# generator: nous-lang {nous_version}\n"
        f"\n"
        f"===== BEGIN SKILL.md =====\n"
    ).encode("utf-8")
    mid = b"\n===== END SKILL.md =====\n\n===== BEGIN nous.yaml =====\n"
    tail = b"\n===== END nous.yaml =====\n"
    return header + skill_md_bytes + mid + sidecar_bytes + tail


def _public_key_raw_bytes(pub: Any) -> bytes:
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PublicFormat,
    )
    return pub.public_bytes(Encoding.Raw, PublicFormat.Raw)


def build_dossier_spec(
    skill_dir: Path,
    *,
    cap_override: Optional[str] = None,
    prices: Optional[Path] = None,
    output: Optional[Path] = None,
    smt_margin: int = 0,
    key_path: Optional[Path] = None,
    today: Optional[date] = None,
) -> DossierSpecResult:
    """Build an Annex IV-aligned dossier from a SKILL.md skill directory."""
    from skill_md import (
        SkillMDError,
        MoneyAmount,
        parse_skill_dir,
        translate_to_program,
    )
    from pricing import load_pricing
    from smt_emit import emit_smt
    from smt_verify import verify
    from manifest import (
        manifest_from_verify,
        load_or_create_keypair,
        sign_manifest,
        manifest_json,
        default_key_path,
    )
    from dossier import VERIFY_OFFLINE_PY
    from ast_nodes import CostCap
    from _version import __version__ as nous_version

    skill_dir = Path(skill_dir).resolve()
    if not skill_dir.is_dir():
        raise DossierSpecError(
            f"skill_dir is not a directory: {skill_dir}"
        )

    try:
        parsed = parse_skill_dir(skill_dir)
    except SkillMDError as e:
        raise DossierSpecError(f"skill parse failed: {e}") from e

    try:
        prog = translate_to_program(parsed)
    except SkillMDError as e:
        raise DossierSpecError(f"skill translation failed: {e}") from e
    except Exception as e:
        raise DossierSpecError(
            f"skill translation failed "
            f"({type(e).__name__}): {e}"
        ) from e

    if cap_override is not None:
        try:
            money = MoneyAmount.parse(cap_override)
        except Exception as e:
            raise DossierSpecError(
                f"--cap parse failed: {e}"
            ) from e
        if money.currency not in _SUPPORTED_CAP_CURRENCIES:
            raise DossierSpecError(
                f"--cap currency {money.currency} not supported "
                f"(only USD, EUR; ISO 4217 widening planned)"
            )
        prog.world.cost_cap = CostCap(
            amount=Decimal(str(money.amount)),
            currency=money.currency,
        )

    try:
        pricing = load_pricing(
            Path(prices).resolve() if prices is not None else None
        )
    except Exception as e:
        raise DossierSpecError(f"pricing load failed: {e}") from e

    skill_md_bytes = Path(parsed.skill_md_path).read_bytes()
    sidecar_bytes = Path(parsed.sidecar_path).read_bytes()
    envelope_bytes = _source_envelope(
        skill_name=parsed.frontmatter.name,
        skill_md_bytes=skill_md_bytes,
        sidecar_bytes=sidecar_bytes,
        nous_version=nous_version,
    )
    envelope_text = envelope_bytes.decode("utf-8")

    try:
        spec = emit_smt(
            prog,
            pricing,
            source_text=envelope_text,
            today=today,
            margin_pct=smt_margin,
        )
    except Exception as e:
        raise DossierSpecError(
            f"SMT emit failed ({type(e).__name__}): {e}"
        ) from e

    try:
        verify_result = verify(spec)
    except Exception as e:
        raise DossierSpecError(
            f"SMT verify failed ({type(e).__name__}): {e}"
        ) from e

    manifest = manifest_from_verify(verify_result, nous_version)

    key_path_resolved = (
        Path(key_path).resolve()
        if key_path is not None
        else default_key_path()
    )
    try:
        priv, pub, _resolved_key_path = load_or_create_keypair(
            key_path_resolved
        )
    except Exception as e:
        raise DossierSpecError(
            f"keypair load/create failed at "
            f"{key_path_resolved}: {e}"
        ) from e

    signature = sign_manifest(manifest, priv)
    signed_json = manifest_json(manifest, signature, pub)

    if output is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = (
            Path.cwd()
            / f"{parsed.frontmatter.name}_dossier_{ts}"
        )
    output = Path(output).resolve()
    if (
        output.exists()
        and output.is_dir()
        and any(output.iterdir())
    ):
        raise DossierSpecError(
            f"output directory not empty: {output}"
        )
    output.mkdir(parents=True, exist_ok=True)

    files: list[str] = []

    (output / "source.nous").write_bytes(envelope_bytes)
    files.append("source.nous")

    (output / "manifest.json").write_text(
        signed_json, encoding="utf-8"
    )
    files.append("manifest.json")

    (output / "SKILL.md").write_bytes(skill_md_bytes)
    files.append("SKILL.md")

    (output / "nous.yaml").write_bytes(sidecar_bytes)
    files.append("nous.yaml")

    if pricing.source_path is None:
        raise DossierSpecError(
            "pricing table has no source_path"
        )
    shutil.copy2(pricing.source_path, output / "pricing.toml")
    files.append("pricing.toml")

    raw_pub_bytes = _public_key_raw_bytes(pub)
    (output / "public_key.b64").write_text(
        base64.b64encode(raw_pub_bytes).decode("ascii") + "\n",
        encoding="utf-8",
    )
    files.append("public_key.b64")

    readme = _build_readme(
        parsed=parsed,
        manifest=manifest,
        envelope_sha=_hex_sha256(envelope_bytes),
        skill_md_sha=_hex_sha256(skill_md_bytes),
        sidecar_sha=_hex_sha256(sidecar_bytes),
        nous_version=nous_version,
    )
    (output / "README.md").write_text(readme, encoding="utf-8")
    files.append("README.md")

    verify_path = output / "verify_offline.py"
    verify_path.write_text(VERIFY_OFFLINE_PY, encoding="utf-8")
    verify_path.chmod(0o755)
    files.append("verify_offline.py")

    return DossierSpecResult(
        output_dir=output,
        files=tuple(files),
        world_name=manifest.world_name,
        verdict=manifest.verdict,
        safety_margin_pct=manifest.safety_margin_pct,
    )


def _build_readme(
    *,
    parsed: Any,
    manifest: Any,
    envelope_sha: str,
    skill_md_sha: str,
    sidecar_sha: str,
    nous_version: str,
) -> str:
    margin_line = ""
    if manifest.safety_margin_pct:
        margin_line = (
            f"  Safety margin: {manifest.safety_margin_pct}%\n"
        )
    lines = [
        "# Annex IV Compliance Dossier (skill_md flavor)\n",
        "\n",
        "This dossier was generated by `nous dossier-spec` from a "
        "SKILL.md\n",
        "skill directory. It attests, under Ed25519 signature, that "
        "the\n",
        "skill's declared cost budget is satisfied across all "
        "execution\n",
        "paths up to `max_ticks`.\n",
        "\n",
        "## Skill identity\n",
        "\n",
        f"- Name:        `{parsed.frontmatter.name}`\n",
        f"- Description: {parsed.frontmatter.description}\n",
        f"- World name:  `{manifest.world_name}`\n",
        "\n",
        "## Provenance hashes (SHA-256)\n",
        "\n",
        f"- source.nous (envelope): `{envelope_sha}`\n",
        f"- SKILL.md (verbatim):    `{skill_md_sha}`\n",
        f"- nous.yaml (verbatim):   `{sidecar_sha}`\n",
        f"- pricing.toml:           `{manifest.pricing_sha256}`\n",
        f"- smt_spec:               `{manifest.smt_spec_sha256}`\n",
        "\n",
        "## Verdict\n",
        "\n",
        f"  Verdict:   {manifest.verdict}\n",
        f"  Cost cap:  {manifest.cost_cap_usd}\n",
        f"  Max ticks: {manifest.max_ticks}\n",
        margin_line,
        f"  Solver:    {manifest.solver_version}\n",
        f"  Timestamp: {manifest.timestamp_utc}\n",
        "\n",
        "## Versioning\n",
        "\n",
        f"- nous-lang: {nous_version}\n",
        f"- smt_emit:  {manifest.smt_emit_version}\n",
        f"- envelope:  v{_ENVELOPE_VERSION} (skill_md flavor)\n",
        "\n",
        "## Verification\n",
        "\n",
        "```\n",
        "python3 verify_offline.py\n",
        "```\n",
        "\n",
        "The verifier confirms:\n",
        "  1. The Ed25519 signature on manifest.json verifies under "
        "the\n",
        "     public key in public_key.b64.\n",
        "  2. The SHA-256 of source.nous matches "
        "manifest.source_sha256.\n",
        "\n",
        "The source.nous file is a deterministic envelope encoding\n",
        "SKILL.md and nous.yaml. Auditors may also independently "
        "verify\n",
        "the per-file SHAs above against SKILL.md and nous.yaml in "
        "this\n",
        "dossier.\n",
    ]
    return "".join(lines)
