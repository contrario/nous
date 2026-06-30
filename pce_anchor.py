"""NOUS predetermined-change envelope pre-commitment anchor (4a).

Assessment-time ceremony, UPSTREAM of and INDEPENDENT from any build. Given a
predetermined-change envelope (``pce.json``), this module anchors the envelope
bytes into the Sigstore Rekor v2 transparency log AND timestamps the same bytes
under RFC 3161, then writes a self-describing ABSOLUTE pre-commitment receipt
(``pce.anchor.json``).

Honest boundary. The receipt EVIDENCES pre-commitment-in-time: the envelope
provably existed at the RFC 3161 genTime (T_env) and is included in a public
append-only transparency log. The receipt makes NO ordering claim and does NOT
evidence the envelope's adequacy or coverage. Whether the envelope was
well-drawn remains the notified body's determination. "Proves" is reserved for
Z3 / Farkas. The precedes relation (T_env vs a later change's T_change) is the
verifier's relational computation at audit time, never asserted here.

This module never imports the verify or sign path. Its only network
dependencies (rekor_anchor_v2, tsa_client, httpx) are imported lazily inside
anchor_pce, so importing this module performs no network work and pulls no
third-party package.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import httpx

PCE_ANCHOR_SCHEMA_VERSION: int = 1

_BASIS_DISCLAIMER: str = (
    "This receipt evidences pre-commitment-in-time of the named "
    "predetermined-change envelope: the envelope provably existed at the "
    "RFC 3161 genTime and is included in a public append-only transparency "
    "log. It is not a legal substantiality determination and does not "
    "evidence the envelope's adequacy or coverage. This receipt asserts no "
    "ordering relative to any later change; any such relation is established "
    "only by the verifier at audit time, never by this receipt."
)

_REQUIRED_ENVELOPE_DISCLAIMER: str = "not a legal substantiality determination"


class PceAnchorError(ValueError):
    """A pce-anchor ceremony precondition or integrity failure."""


def _canonical_bytes(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _validate_envelope_shape(pce_doc: object) -> None:
    if not isinstance(pce_doc, dict):
        raise PceAnchorError("pce envelope is not a JSON object")
    basis = pce_doc.get("basis")
    if not isinstance(basis, str) or _REQUIRED_ENVELOPE_DISCLAIMER not in basis:
        raise PceAnchorError(
            "pce envelope basis missing or does not disclaim substantiality "
            "(must contain '" + _REQUIRED_ENVELOPE_DISCLAIMER + "'); refusing "
            "to anchor a document that does not declare itself a "
            "non-determination envelope"
        )
    base_sha = pce_doc.get("baseline_canon_sha256")
    if (
        not isinstance(base_sha, str)
        or len(base_sha) != 64
        or any(c not in "0123456789abcdef" for c in base_sha)
    ):
        raise PceAnchorError(
            "pce envelope baseline_canon_sha256 is not a 64-hex sha256; "
            "refusing to anchor an envelope with no committed baseline"
        )


def build_pce_anchor_receipt(
    *,
    pce_bytes: bytes,
    rekor_v2_block: dict,
    pce_rfc3161_token_der: bytes,
) -> dict:
    """Assemble the absolute pre-commitment receipt. Pure; no network.

    Binds the exact envelope bytes (anchored_pce_sha256), the Rekor v2
    transparency-log inclusion block, and an RFC 3161 token taken over the
    SAME envelope bytes (the T_env source). Carries no ordering claim by
    construction.
    """
    if not isinstance(rekor_v2_block, dict):
        raise PceAnchorError("rekor_v2_block must be a dict")
    if rekor_v2_block.get("rekor_api_version") != 2:
        raise PceAnchorError(
            "rekor_v2_block.rekor_api_version must be 2 (not a v2 anchor "
            "block)"
        )
    return {
        "pce_anchor_schema_version": PCE_ANCHOR_SCHEMA_VERSION,
        "anchored_pce_sha256": hashlib.sha256(pce_bytes).hexdigest(),
        "basis": _BASIS_DISCLAIMER,
        "rekor_v2": rekor_v2_block,
        "pce_rfc3161_token_b64": base64.b64encode(
            pce_rfc3161_token_der
        ).decode("ascii"),
    }


def anchor_pce(
    pce_path: Path,
    *,
    out_path: Optional[Path] = None,
    rekor_base_url: Optional[str] = None,
    tsa_url: Optional[str] = None,
    client: "Optional[httpx.Client]" = None,
) -> Path:
    """Run the live pce-anchor ceremony and write the receipt.

    IRREVERSIBLE: performs two live network POSTs (a Rekor v2 entry over the
    envelope bytes and an RFC 3161 timestamp over the same bytes). Returns the
    path of the written receipt.
    """
    from rekor_anchor_v2 import (
        REKOR_V2_DEFAULT_BASE_URL,
        anchor_manifest_to_rekor_v2,
    )
    from tsa_client import TSA_DEFAULT_URL, anchor_timestamp

    if not pce_path.is_file():
        raise PceAnchorError("pce envelope not found: " + str(pce_path))
    pce_bytes = pce_path.read_bytes()
    try:
        pce_doc = json.loads(pce_bytes.decode("utf-8"))
    except Exception as exc:
        raise PceAnchorError(
            "pce envelope is not valid JSON: " + repr(exc)
        ) from exc
    _validate_envelope_shape(pce_doc)

    v2_anchor = anchor_manifest_to_rekor_v2(
        manifest_canonical_bytes=pce_bytes,
        client=client,
        base_url=rekor_base_url or REKOR_V2_DEFAULT_BASE_URL,
    )
    token_der = anchor_timestamp(
        timestamped_data=pce_bytes,
        client=client,
        base_url=tsa_url or TSA_DEFAULT_URL,
    )
    receipt = build_pce_anchor_receipt(
        pce_bytes=pce_bytes,
        rekor_v2_block=v2_anchor.to_manifest_block(),
        pce_rfc3161_token_der=token_der,
    )
    target = out_path if out_path is not None else (
        pce_path.parent / "pce.anchor.json"
    )
    target.write_bytes(_canonical_bytes(receipt))
    return target
