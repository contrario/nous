"""NOUS trace-bundle temporal-existence anchor (C2).

Build-time ceremony, INDEPENDENT of the verify/sign path. Given the exact
bytes of a completed trace bundle's manifest (``trace_bundle/manifest.json``),
this module timestamps those bytes under RFC 3161 and writes a self-describing
ABSOLUTE temporal-existence receipt (``trace_bundle.anchor.json``).

Honest boundary. The receipt EVIDENCES bundle temporal existence (SPEC
§3.1 C2): the bundle, identified by the canonical hash of its manifest,
provably existed in its exact form no later than the RFC 3161 genTime
(T_attest). It is an UPPER BOUND on bundle creation (anti-backdating), not
an assertion of equality with T_attest, and carries NO ordering claim
relative to any second event (relative ordering is out of scope for C2 and
would require a second anchor). "Proves" is reserved for Z3 / Farkas.

Deliberate divergence from pce_anchor (evidence vs metadata). Unlike
pce.anchor.json, this receipt carries ONLY evidence-bearing fields: the
schema version, the identifying hash of the anchored bundle, and the RFC
3161 token. It deliberately OMITS a human-readable ``basis`` string and any
provenance such as a TSA URL. A basis is verifier OUTPUT (produced after
successful verification, SPEC §3.1.2), not evidence; a TSA URL is
provenance, not trust (the trust root is the pinned TSA certificate). The
pce.anchor.json receipt embeds a basis string inside the evidence object;
that mixing is intentionally not reproduced here, keeping the receipt a
pure carrier of what is cryptographically verified.

This module never imports the verify or sign path. Its only network
dependency (tsa_client, httpx) is imported lazily inside the live ceremony,
so importing this module performs no network work and pulls no third-party
package. build_trace_bundle_anchor_receipt itself is pure.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import httpx

TRACE_BUNDLE_ANCHOR_SCHEMA_VERSION: int = 1


class TraceBundleAnchorError(ValueError):
    """A trace-bundle-anchor ceremony precondition or integrity failure."""


def build_trace_bundle_anchor_receipt(
    *,
    bundle_manifest_bytes: bytes,
    tsa_rfc3161_token_der: bytes,
) -> dict:
    """Assemble the absolute temporal-existence receipt. Pure; no network.

    Binds the exact bundle manifest bytes (anchored_bundle_sha256) to an RFC
    3161 token taken over those SAME bytes (the T_attest source). Evidence
    only: no basis, no provenance. The receipt is verifiable against the
    pinned TSA root offline, and its anchored_bundle_sha256 must equal both
    sha256(trace_bundle/manifest.json) and the signed dossier manifest's
    trace_bundle_sha256 (the §3.1.2 identity requirement, checked by the
    verifier, not here).
    """
    if not isinstance(bundle_manifest_bytes, (bytes, bytearray)):
        raise TraceBundleAnchorError(
            "bundle_manifest_bytes must be bytes"
        )
    if not isinstance(tsa_rfc3161_token_der, (bytes, bytearray)):
        raise TraceBundleAnchorError(
            "tsa_rfc3161_token_der must be bytes"
        )
    if not tsa_rfc3161_token_der:
        raise TraceBundleAnchorError(
            "tsa_rfc3161_token_der is empty (no token to carry)"
        )
    return {
        "trace_bundle_anchor_schema_version":
            TRACE_BUNDLE_ANCHOR_SCHEMA_VERSION,
        "anchored_bundle_sha256":
            hashlib.sha256(bytes(bundle_manifest_bytes)).hexdigest(),
        "tsa_rfc3161_token_b64":
            base64.b64encode(bytes(tsa_rfc3161_token_der)).decode("ascii"),
    }


def anchor_trace_bundle(
    bundle_manifest_path: Path,
    *,
    out_path: Optional[Path] = None,
    tsa_url: Optional[str] = None,
    client: "Optional[httpx.Client]" = None,
) -> Path:
    """Run the live trace-bundle-anchor ceremony and write the receipt.

    IRREVERSIBLE: performs one live network POST (an RFC 3161 timestamp over
    the exact bundle manifest bytes). Returns the path of the written
    receipt. Network deps imported lazily so module import stays pure.
    """
    from tsa_client import TSA_DEFAULT_URL, anchor_timestamp

    if not bundle_manifest_path.is_file():
        raise TraceBundleAnchorError(
            "bundle manifest not found: " + str(bundle_manifest_path)
        )
    bundle_manifest_bytes = bundle_manifest_path.read_bytes()
    token_der = anchor_timestamp(
        timestamped_data=bundle_manifest_bytes,
        client=client,
        base_url=tsa_url or TSA_DEFAULT_URL,
    )
    receipt = build_trace_bundle_anchor_receipt(
        bundle_manifest_bytes=bundle_manifest_bytes,
        tsa_rfc3161_token_der=token_der,
    )
    target = out_path if out_path is not None else (
        bundle_manifest_path.parent.parent / "trace_bundle.anchor.json"
    )
    target.write_bytes(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    return target
