"""
NOUS manifest — produce, sign, and (optionally) publish an
audit-ready proof manifest after a successful (or refuted) verify
run.

The manifest is a single self-contained JSON document with embedded
ed25519 signature. It encodes the full provenance chain:

    source_sha256       hash of the .nous program text
    pricing_sha256      hash of the active pricing TOML (canonical)
    smt_spec_sha256     hash of the emitted SMT-LIB spec
    solver, version     who solved it
    verdict             proven | refuted | unknown
    timestamp_utc       ISO 8601 UTC

Anyone with the manifest JSON + the publisher's public key can
verify the signature and recompute the provenance hashes from the
original artifacts. This is what makes NOUS proofs externally
auditable (EU AI Act Annex IV alignment).

Public API:
  Manifest                       frozen dataclass
  manifest_from_verify(...)      build from a VerifyResult
  load_or_create_keypair(path)   ed25519 keypair, 0600 perms
  sign_manifest(m, key)          -> bytes (raw signature)
  manifest_json(m, sig, pub)     -> str (canonical JSON)
  verify_manifest_signature(...) -> bool

# __nous_manifest_module_v1__
"""
from __future__ import annotations
# __session64_publish_removal_v1__
# __session64_smt_margin_v1__

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:  # __session96_manifest_smtspec_typecheck_import_v1__
    from smt_emit import SMTSpec

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)
from cryptography.exceptions import InvalidSignature

from smt_verify import VerifyResult


MANIFEST_SCHEMA_VERSION: str = "1.0"


# ─────────────────────────────────────────────────────────────────────
# Manifest dataclass
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Manifest:
    """Self-describing audit record of one verify run.

    Frozen so the canonical bytes (used for signing) are stable.
    """
    schema_version: str
    nous_version: str
    smt_emit_version: str

    # Provenance chain — all sha256 hex digests.
    source_sha256: str
    pricing_sha256: str
    smt_spec_sha256: str

    # World-level summary so the manifest is human-meaningful
    # without re-reading the source.
    world_name: str
    cost_cap_usd: str
    max_ticks: int

    # Solver outcome.
    verdict: str
    solver_name: str
    solver_version: str
    elapsed_ms: int
    timestamp_utc: str

    # When refuted, total observed cost (Decimal as string).
    counterexample_total_usd: Optional[str] = None

    # Optional safety margin applied during verify (--smt-margin PCT).
    safety_margin_pct: Optional[int] = None

    # Signed per-soul proof assumptions for runtime conformance (S96).
    proof_assumptions: Optional[dict] = None  # __session96_manifest_proof_assumptions_field_v1__

    def canonical_bytes(self) -> bytes:
        """Bytes that get signed — sorted, separator-stable JSON."""
        return json.dumps(
            self.canonical_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def canonical_dict(self) -> dict:
        d: dict = {
            "schema_version": self.schema_version,
            "nous_version": self.nous_version,
            "smt_emit_version": self.smt_emit_version,
            "source_sha256": self.source_sha256,
            "pricing_sha256": self.pricing_sha256,
            "smt_spec_sha256": self.smt_spec_sha256,
            "world_name": self.world_name,
            "cost_cap_usd": self.cost_cap_usd,
            "max_ticks": self.max_ticks,
            "verdict": self.verdict,
            "solver_name": self.solver_name,
            "solver_version": self.solver_version,
            "elapsed_ms": self.elapsed_ms,
            "timestamp_utc": self.timestamp_utc,
        }
        if self.counterexample_total_usd is not None:
            d["counterexample_total_usd"] = (
                self.counterexample_total_usd
            )
        if self.safety_margin_pct is not None:
            d["safety_margin_pct"] = self.safety_margin_pct
        return d  # __session96_revert_m3_canonical_dict_v1__


def _build_proof_assumptions(spec: "SMTSpec") -> Optional[dict]:  # __session96_build_proof_assumptions_v1__
    if not spec.soul_assumptions:
        return None
    souls: dict = {}
    for (name, model, max_in, max_out, in_rate, out_rate, mult) in (
        spec.soul_assumptions
    ):
        souls[name] = {
            "model": model,
            "max_input_tokens": max_in,
            "max_output_tokens": max_out,
            "input_per_1m": in_rate,
            "output_per_1m": out_rate,
            "reasoning_token_multiplier": mult,
        }
    return {
        "cost_cap": str(spec.cost_cap_amount),
        "currency": spec.cost_cap_currency,
        "max_ticks": spec.max_ticks,
        "pricing_sha256": spec.pricing_sha256,
        "souls": souls,
        "gated_actions": [],
    }


def manifest_from_verify(
    result: VerifyResult,
    nous_version: str,
) -> Manifest:
    """Build a Manifest from a VerifyResult (any verdict)."""
    spec = result.spec
    ce_total: Optional[str] = None
    if result.counterexample is not None:
        ce_total = str(result.counterexample.total_cost_usd)
    margin = spec.cost_cap_margin_pct
    return Manifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        nous_version=nous_version,
        smt_emit_version=spec.smt_emit_version,
        source_sha256=spec.source_sha256,
        pricing_sha256=spec.pricing_sha256,
        smt_spec_sha256=spec.sha256(),
        world_name=spec.world_name,
        cost_cap_usd=str(spec.cost_cap_amount),
        max_ticks=spec.max_ticks,
        verdict=result.verdict,
        solver_name=result.solver_name,
        solver_version=result.solver_version,
        elapsed_ms=result.elapsed_ms,
        timestamp_utc=result.timestamp_utc,
        counterexample_total_usd=ce_total,
        safety_margin_pct=(margin if margin > 0 else None),  # __session96_revert_m5_v1__
    )


# ─────────────────────────────────────────────────────────────────────
# Keypair management
# ─────────────────────────────────────────────────────────────────────

def default_key_path() -> Path:
    """Default key location: $XDG_DATA_HOME/nous/keys/signing.key.

    Falls back to ~/.local/share/nous/keys/signing.key if unset.
    """
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / "nous" / "keys" / "signing.key"
    return (Path(os.path.expanduser("~"))
            / ".local" / "share" / "nous" / "keys" / "signing.key")


def load_or_create_keypair(
    key_path: Optional[Path] = None,
) -> tuple[Ed25519PrivateKey, Ed25519PublicKey, Path]:
    """Load an existing ed25519 keypair, or create one.

    Private key file is mode 0600; parent directory 0700.
    Returns (private_key, public_key, resolved_path).
    """
    if key_path is None:
        key_path = default_key_path()
    key_path = Path(key_path).expanduser()

    if key_path.is_file():
        pem_bytes: bytes = key_path.read_bytes()
        private = serialization.load_pem_private_key(
            pem_bytes, password=None,
        )
        if not isinstance(private, Ed25519PrivateKey):
            raise ValueError(
                f"key at {key_path} is not Ed25519"
            )
        return private, private.public_key(), key_path

    # Create new keypair.
    key_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(key_path.parent, 0o700)
    except OSError:
        pass
    private = Ed25519PrivateKey.generate()
    pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path.write_bytes(pem)
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    return private, private.public_key(), key_path


def public_key_b64(public_key: Ed25519PublicKey) -> str:
    raw: bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


# ─────────────────────────────────────────────────────────────────────
# Sign + verify
# ─────────────────────────────────────────────────────────────────────

def sign_manifest(
    manifest: Manifest,
    private_key: Ed25519PrivateKey,
) -> bytes:
    return private_key.sign(manifest.canonical_bytes())


def verify_manifest_signature(
    manifest: Manifest,
    signature: bytes,
    public_key: Ed25519PublicKey,
) -> bool:
    try:
        public_key.verify(signature, manifest.canonical_bytes())
        return True
    except InvalidSignature:
        return False


def manifest_json(
    manifest: Manifest,
    signature: bytes,
    public_key: Ed25519PublicKey,
    rekor_anchor: "RekorAnchor | None" = None,
    include_proof_assumptions: bool = False,  # __session96_manifest_json_optin_sig_v1__
) -> str:
    """Render the full audit-ready JSON document.

    If ``rekor_anchor`` is provided, the manifest envelope gains a
    sibling ``transparency_log`` block alongside the ``signature``
    block. When ``rekor_anchor=None`` (the default), the output is
    BYTE-IDENTICAL to the v5.2.0 behavior.
    """
    # __nous_aetherproof_manifest_json_extension_v1__
    doc: dict = manifest.canonical_dict()
    doc["signature"] = {
        "algorithm": "ed25519",
        "public_key_b64": public_key_b64(public_key),
        "signature_b64": base64.b64encode(signature).decode("ascii"),
    }
    if rekor_anchor is not None:
        doc["transparency_log"] = rekor_anchor.to_manifest_block()
    if (  # __session96_manifest_json_optin_body_v1__
        include_proof_assumptions
        and manifest.proof_assumptions is not None
    ):
        doc["proof_assumptions"] = manifest.proof_assumptions
    return json.dumps(doc, indent=2, sort_keys=True) + "\n"


def parse_manifest_json(text: str) -> tuple[Manifest, bytes,
                                            Ed25519PublicKey]:
    """Inverse of manifest_json — for `nous audit` flows."""
    doc = json.loads(text)
    sig_block = doc.pop("signature")
    if sig_block.get("algorithm") != "ed25519":
        raise ValueError("only ed25519 signatures are supported")
    sig = base64.b64decode(sig_block["signature_b64"])
    pub_raw = base64.b64decode(sig_block["public_key_b64"])
    pub = Ed25519PublicKey.from_public_bytes(pub_raw)
    m = Manifest(
        schema_version=doc["schema_version"],
        nous_version=doc["nous_version"],
        smt_emit_version=doc["smt_emit_version"],
        source_sha256=doc["source_sha256"],
        pricing_sha256=doc["pricing_sha256"],
        smt_spec_sha256=doc["smt_spec_sha256"],
        world_name=doc["world_name"],
        cost_cap_usd=doc["cost_cap_usd"],
        max_ticks=doc["max_ticks"],
        verdict=doc["verdict"],
        solver_name=doc["solver_name"],
        solver_version=doc["solver_version"],
        elapsed_ms=doc["elapsed_ms"],
        timestamp_utc=doc["timestamp_utc"],
        counterexample_total_usd=doc.get(
            "counterexample_total_usd"
        ),
        proof_assumptions=doc.get("proof_assumptions"),  # __session96_parse_manifest_json_sibling_v1__
    )
    return m, sig, pub


def parse_manifest_json_with_anchor(
    text: str,
) -> tuple[Manifest, bytes, Ed25519PublicKey, "RekorAnchor | None"]:
    """Inverse of manifest_json that also recovers a Rekor anchor.

    Returns a 4-tuple ``(manifest, signature_bytes, public_key,
    anchor_or_None)``. When the ``transparency_log`` block is absent
    (any v5.2.0 dossier, or any v5.3.0 dossier produced without
    ``--anchor rekor``), the fourth element is ``None`` and the first
    three elements match :func:`parse_manifest_json` exactly.
    """
    # __nous_aetherproof_parse_with_anchor_v1__
    from rekor_anchor import RekorAnchor as _RekorAnchor
    doc = json.loads(text)
    anchor_block = doc.pop("transparency_log", None)
    sig_block = doc.pop("signature")
    if sig_block.get("algorithm") != "ed25519":
        raise ValueError("only ed25519 signatures are supported")
    sig = base64.b64decode(sig_block["signature_b64"])
    pub_raw = base64.b64decode(sig_block["public_key_b64"])
    pub = Ed25519PublicKey.from_public_bytes(pub_raw)
    m = Manifest(
        schema_version=doc["schema_version"],
        nous_version=doc["nous_version"],
        smt_emit_version=doc["smt_emit_version"],
        source_sha256=doc["source_sha256"],
        pricing_sha256=doc["pricing_sha256"],
        smt_spec_sha256=doc["smt_spec_sha256"],
        world_name=doc["world_name"],
        cost_cap_usd=doc["cost_cap_usd"],
        max_ticks=doc["max_ticks"],
        verdict=doc["verdict"],
        solver_name=doc["solver_name"],
        solver_version=doc["solver_version"],
        elapsed_ms=doc["elapsed_ms"],
        timestamp_utc=doc["timestamp_utc"],
        counterexample_total_usd=doc.get(
            "counterexample_total_usd"
        ),
        proof_assumptions=doc.get("proof_assumptions"),  # __session96_parse_with_anchor_sibling_v1__
    )
    anchor: "_RekorAnchor | None" = None
    if anchor_block is not None:
        anchor = _RekorAnchor.from_manifest_block(anchor_block)
    return m, sig, pub, anchor



def parse_manifest_json_with_anchor_v2(
    text: str,
) -> tuple[Manifest, bytes, Ed25519PublicKey, "RekorAnchor | None", "dict | None"]:
    """Version-dispatching inverse of manifest_json.

    Like :func:`parse_manifest_json_with_anchor` but routes the
    ``transparency_log`` block by its ``rekor_api_version`` discriminator.
    Returns a 5-tuple ``(manifest, signature_bytes, public_key,
    v1_anchor_or_None, v2_block_or_None)``.

    Routing:
      - block absent, or ``rekor_api_version`` absent, or ``== 1``:
        delegates to :func:`parse_manifest_json_with_anchor`; the v1 anchor
        is recovered byte-identically and the fifth element is ``None``.
      - ``rekor_api_version == 2`` (within
        ``MAX_SUPPORTED_REKOR_API_VERSION``): the raw v2 block is returned
        as the fifth element; the v1 anchor element is ``None``.
      - any version above ``MAX_SUPPORTED_REKOR_API_VERSION`` (or any other
        non-1/2 value): raises ``ValueError`` (refuse over guess; preserves
        the historical throw-on-unsupported-anchor behaviour).

    The v1 path is delegated, not reimplemented, so this function cannot
    drift from the proven 4-tuple parser.
    """
    # __nous_s91_anchor_v2_dispatch_v1__
    from rekor_signing_config import MAX_SUPPORTED_REKOR_API_VERSION

    doc = json.loads(text)
    anchor_block = doc.get("transparency_log")
    if anchor_block is None:
        m, sig, pub, anchor = parse_manifest_json_with_anchor(text)
        return m, sig, pub, anchor, None
    if not isinstance(anchor_block, dict):
        raise ValueError("transparency_log is not an object")

    api_version = anchor_block.get("rekor_api_version")
    if api_version is None:
        m, sig, pub, anchor = parse_manifest_json_with_anchor(text)
        return m, sig, pub, anchor, None
    if isinstance(api_version, bool) or not isinstance(api_version, int):
        raise ValueError(
            "transparency_log.rekor_api_version is not an integer "
            "(got " + repr(api_version) + ")"
        )
    if api_version == 1:
        m, sig, pub, anchor = parse_manifest_json_with_anchor(text)
        return m, sig, pub, anchor, None
    if api_version > MAX_SUPPORTED_REKOR_API_VERSION:
        raise ValueError(
            "transparency_log.rekor_api_version " + str(api_version)
            + " exceeds MAX_SUPPORTED_REKOR_API_VERSION "
            + str(MAX_SUPPORTED_REKOR_API_VERSION)
        )
    if api_version == 2:
        doc_no_anchor = {
            k: v for k, v in doc.items() if k != "transparency_log"
        }
        m, sig, pub, _ = parse_manifest_json_with_anchor(
            json.dumps(doc_no_anchor)
        )
        return m, sig, pub, None, anchor_block
    raise ValueError(
        "transparency_log.rekor_api_version " + str(api_version)
        + " is not a supported version"
    )
