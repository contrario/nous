"""Detached Rekor v2 transparency anchoring for trace envelopes (S105 #5).

A signed TraceEnvelope can be anchored to the Sigstore Rekor v2 transparency
log so a third party can prove the trace existed at a point in time and was
not altered after. The anchor is DETACHED: the TraceEnvelope is frozen and its
canonical bytes are already signed, so the anchor cannot live inside it. The
binding is cryptographic -- the Rekor leaf signs the same
envelope.canonical_body_bytes() -- and is checked at verify time, exactly as
the dossier manifest path does.

# __s105_trace_anchor_module_v1__
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import httpx
    from nous_trace import TraceEnvelope
    from rekor_verify_v2 import RekorAnchorV2


class TraceAnchorError(RuntimeError):
    """Raised when a trace envelope cannot be anchored."""


def anchor_trace_to_rekor_v2(
    envelope: "TraceEnvelope",
    *,
    client: "Optional[httpx.Client]" = None,
    _test_anchor: "Optional[Any]" = None,
) -> "RekorAnchorV2":
    """Anchor a signed trace envelope to Rekor v2; return a detached anchor.

    The envelope MUST already be signed (it carries a signature); anchoring an
    unsigned envelope is refused, since the transparency record would attest to
    a body whose authorship is unestablished.

    _test_anchor is a private hook: when provided it is returned unchanged,
    letting tests exercise the path offline with no live Rekor/TSA submit.
    """
    sig = getattr(envelope, "signature", None)
    if sig is None:
        raise TraceAnchorError(
            "envelope is unsigned; sign before anchoring (anchor attests a signed body)"
        )
    if _test_anchor is not None:
        return _test_anchor

    from rekor_anchor_v2 import anchor_manifest_to_rekor_v2

    body = envelope.canonical_body_bytes()
    if not isinstance(body, bytes) or len(body) < 1:
        raise TraceAnchorError("envelope canonical body is empty")
    return anchor_manifest_to_rekor_v2(manifest_canonical_bytes=body, client=client)
