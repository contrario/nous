"""Counterparty-witnessed continuity: run-lineage ledger link + receipt.

S176 P1 mechanics for the arc frozen in
docs/COUNTERPARTY_WITNESSED_CONTINUITY_DESIGN.md. This module supplies two
producers and nothing else: a continuity-ledger LINK constructor whose unit is
a conformance-certified RUN, and a COUNTERPARTY RECEIPT generator that emits a
fully attached, self-contained JWS (RFC 7515 flattened JSON, EdDSA over
Ed25519 per RFC 8037).

Honest boundary (inviolable). This module PROVES nothing: "proves" stays
reserved for Z3 cost bounds and Farkas certificates. The link EVIDENCES a
tamper-evident position in a sequence of conformance-certified runs; a receipt
EVIDENCES that a party OTHER than the operator signed off on one exact
certified run. A valid receipt does not assert the agent could not misbehave,
and a ledger of N witnessed runs is not a claim that those were the only runs
(omission is not defeated). NOUS remains a monitor, not a guard.

Independence and zero-install verification. The receipt payload is ATTACHED so
any relying party verifies it with ubiquitous tooling and ZERO NOUS install:
either openssl on the reconstructed signing input, or jwt.decode over the
compact form protected.payload.signature. The trust root is the counterparty's
OWN published key; the `kid` header is an unauthenticated hint a verifier must
not resolve from. No method here imports an external agent framework, a solver,
or any network client.
"""
from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


LINK_KIND: str = "run"
WITNESS_KIND: str = "counterparty"
RECEIPT_FORMAT: str = "jws_eddsa_v1"
RECEIPT_ALG: str = "EdDSA"
RECEIPT_TYP: str = "application/nous-counterparty-receipt+jwt"

_GENESIS_PREIMAGE: bytes = b"nous:continuity-ledger:genesis:v1"
GENESIS_PREV_RUN_DIGEST: str = hashlib.sha256(_GENESIS_PREIMAGE).hexdigest()


class ContinuityLedgerError(RuntimeError):
    """Raised cause-first when a run cannot form a link or a counterparty
    receipt cannot be constructed under the design-freeze rules."""


def _canonical_bytes(obj: Mapping[str, object]) -> bytes:
    return json.dumps(
        dict(obj), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _require_sha256_hex(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ContinuityLedgerError(
            name + " must be a 64-char sha256 hex string, got: " + repr(value)
        )
    try:
        int(value, 16)
    except ValueError:
        raise ContinuityLedgerError(
            name + " is not valid hexadecimal: " + repr(value)
        )
    return value


def certificate_body_digest(cert: Mapping[str, object]) -> str:
    """sha256 of the conformance certificate canonical body.

    Byte-identical to conformance_verifier `_cert_canonical_body_bytes`: drops
    `signature` and `transparency_log`; drops `sequence_ok` when the schema is
    below v2; canonical form json.dumps(sort_keys=True, separators=(",",":")).
    This is the link unit the continuity ledger chains; any party re-derives it
    from the certificate bytes alone.
    """
    body: dict[str, object] = {
        k: v
        for k, v in cert.items()
        if k not in ("signature", "transparency_log")
    }
    raw_schema = body.get("certificate_schema_version", 1)
    try:
        schema_v = int(raw_schema)
    except (TypeError, ValueError):
        raise ContinuityLedgerError(
            "certificate_schema_version is not an integer: " + repr(raw_schema)
        )
    if schema_v < 2:
        body.pop("sequence_ok", None)
    return hashlib.sha256(_canonical_bytes(body)).hexdigest()


def _extract_consultation(
    trace: Mapping[str, object],
) -> tuple[str, str, str, int]:
    mc = trace.get("memory_consultation")
    if mc is None:
        raise ContinuityLedgerError(
            "memory_consultation absent in trace: run is not "
            "counterparty-receipt-eligible (no run-lineage anchor)"
        )
    if not isinstance(mc, Mapping):
        raise ContinuityLedgerError(
            "memory_consultation is not an object: " + repr(type(mc))
        )
    world = _require_sha256_hex("world_sha256", mc.get("world_sha256"))
    soul = _require_sha256_hex(
        "producing_soul_sha256", mc.get("producing_soul_sha256")
    )
    head = _require_sha256_hex(
        "consulted_chain_head", mc.get("consulted_chain_head")
    )
    seq = mc.get("consulted_seq_count")
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
        raise ContinuityLedgerError(
            "consulted_seq_count must be a non-negative integer, got: "
            + repr(seq)
        )
    return world, soul, head, seq


def run_identity_digest(
    *,
    world_sha256: str,
    producing_soul_sha256: str,
    cert_body_sha256: str,
    consulted_chain_head: str,
    consulted_seq_count: int,
) -> str:
    """sha256 of the canonical run-identity tuple (design section 6).

    Because cert_body_sha256 is inside the digest, a receipt or link bound to
    this digest cannot be replayed onto a different certified run.
    """
    tuple_obj: dict[str, object] = {
        "world_sha256": world_sha256,
        "producing_soul_sha256": producing_soul_sha256,
        "cert_body_sha256": cert_body_sha256,
        "consulted_chain_head": consulted_chain_head,
        "consulted_seq_count": consulted_seq_count,
    }
    return hashlib.sha256(_canonical_bytes(tuple_obj)).hexdigest()


def build_link(
    *,
    cert: Mapping[str, object],
    trace: Mapping[str, object],
    prev_run_digest: str,
    counterparty_key_uri: Optional[str] = None,
) -> dict[str, object]:
    """Construct a continuity-ledger link (link.json) over one conformance-
    certified run.

    link_kind="run" makes the link un-confusable with a manifest chain link
    (no silent merge across discriminators). `counterparty_key_uri` is
    drop-when-absent: an un-witnessed link is byte-identical to one built with
    no counterparty mechanism at all. `prev_run_digest` is the predecessor link
    digest, or GENESIS_PREV_RUN_DIGEST for the first link. EVIDENCES a
    tamper-evident position in a run sequence; PROVES nothing.
    """
    _require_sha256_hex("prev_run_digest", prev_run_digest)
    world, soul, head, seq = _extract_consultation(trace)
    cert_body = certificate_body_digest(cert)
    rid = run_identity_digest(
        world_sha256=world,
        producing_soul_sha256=soul,
        cert_body_sha256=cert_body,
        consulted_chain_head=head,
        consulted_seq_count=seq,
    )
    link: dict[str, object] = {
        "link_kind": LINK_KIND,
        "prev_run_digest": prev_run_digest,
        "run_identity_digest": rid,
    }
    if counterparty_key_uri is not None:
        if not counterparty_key_uri:
            raise ContinuityLedgerError(
                "counterparty_key_uri, when present, must be a non-empty URI"
            )
        link["counterparty_key_uri"] = counterparty_key_uri
    link["this_link_digest"] = hashlib.sha256(
        _canonical_bytes(link)
    ).hexdigest()
    return link


def build_counterparty_receipt(
    *,
    cert: Mapping[str, object],
    trace: Mapping[str, object],
    counterparty_signing_key: Ed25519PrivateKey,
    counterparty_kid: str,
    issuer: str,
    audience: str,
    prev_run_digest: str,
    issued_at: int,
    not_before: Optional[int] = None,
) -> dict[str, str]:
    """Construct a counterparty receipt as a fully attached, self-contained
    JWS (RFC 7515 flattened JSON, EdDSA / Ed25519 per RFC 8037).

    The payload is attached so a relying party verifies with stock tooling and
    zero NOUS install. The trust root is the counterparty's OWN published key;
    `counterparty_kid` is an unauthenticated hint. EVIDENCES that a party other
    than the operator signed off on one exact certified run; PROVES nothing and
    does not assert the agent could not misbehave. NOUS is a monitor, not a
    guard.
    """
    _require_sha256_hex("prev_run_digest", prev_run_digest)
    if not issuer:
        raise ContinuityLedgerError("issuer (iss) must be a non-empty URI")
    if not audience:
        raise ContinuityLedgerError("audience (aud) must be a non-empty id")
    if not counterparty_kid:
        raise ContinuityLedgerError("counterparty_kid must be non-empty")
    if not isinstance(issued_at, int) or isinstance(issued_at, bool):
        raise ContinuityLedgerError(
            "issued_at (iat) must be an integer NumericDate"
        )
    if not isinstance(counterparty_signing_key, Ed25519PrivateKey):
        raise ContinuityLedgerError(
            "counterparty_signing_key must be an Ed25519PrivateKey"
        )

    world, soul, head, seq = _extract_consultation(trace)
    cert_body = certificate_body_digest(cert)
    if "conformant" not in cert:
        raise ContinuityLedgerError(
            "certificate has no `conformant` verdict to witness"
        )
    conformant = bool(cert.get("conformant"))
    rid = run_identity_digest(
        world_sha256=world,
        producing_soul_sha256=soul,
        cert_body_sha256=cert_body,
        consulted_chain_head=head,
        consulted_seq_count=seq,
    )

    protected: dict[str, object] = {
        "alg": RECEIPT_ALG,
        "typ": RECEIPT_TYP,
        "kid": counterparty_kid,
    }
    claims: dict[str, object] = {
        "iss": issuer,
        "sub": rid,
        "aud": audience,
        "iat": issued_at,
        "cert_body_sha256": cert_body,
        "world_sha256": world,
        "producing_soul_sha256": soul,
        "consulted_chain_head": head,
        "consulted_seq_count": seq,
        "prev_run_digest": prev_run_digest,
        "conformant": conformant,
    }
    if not_before is not None:
        if not isinstance(not_before, int) or isinstance(not_before, bool):
            raise ContinuityLedgerError(
                "not_before (nbf) must be an integer NumericDate"
            )
        claims["nbf"] = not_before

    protected_b64 = _b64url(_canonical_bytes(protected))
    payload_b64 = _b64url(_canonical_bytes(claims))
    signing_input = (protected_b64 + "." + payload_b64).encode("ascii")
    signature_b64 = _b64url(counterparty_signing_key.sign(signing_input))

    return {
        "protected": protected_b64,
        "payload": payload_b64,
        "signature": signature_b64,
    }


def receipt_compact(receipt: Mapping[str, str]) -> str:
    """The compact JWS (protected.payload.signature) a relying party feeds to
    jwt.decode directly, derived from the flattened receipt by one join.
    """
    return (
        receipt["protected"] + "." + receipt["payload"] + "."
        + receipt["signature"]
    )


def link_json_bytes(link: Mapping[str, object]) -> bytes:
    return _canonical_bytes(link)


def receipt_jws_bytes(receipt: Mapping[str, str]) -> bytes:
    return _canonical_bytes(receipt)


_BOOLS_V1: tuple[str, ...] = (
    "binding_ok",
    "surface_ok",
    "assumption_discharge_ok",
    "bound_transfer_ok",
    "authorization_ok",
    "trace_signature_ok",
)
_BOOLS_V2: tuple[str, ...] = _BOOLS_V1 + ("sequence_ok",)
_BOOLS_V4: tuple[str, ...] = _BOOLS_V2 + ("codegen_binding_ok",)


def _bools_for(schema_version: int) -> tuple[str, ...]:
    if schema_version >= 4:
        return _BOOLS_V4
    return _BOOLS_V2 if schema_version >= 2 else _BOOLS_V1


def _doc_canonical_body_bytes(doc: Mapping[str, object]) -> bytes:
    return _canonical_bytes(
        {k: v for k, v in doc.items() if k != "signature"}
    )


def _cert_canonical_body_bytes(cert: Mapping[str, object]) -> bytes:
    body: dict[str, object] = {
        k: v
        for k, v in cert.items()
        if k not in ("signature", "transparency_log")
    }
    raw_schema = body.get("certificate_schema_version", 1)
    try:
        schema_v = int(raw_schema)
    except (TypeError, ValueError):
        raise ContinuityLedgerError(
            "certificate_schema_version is not an integer: " + repr(raw_schema)
        )
    if schema_v < 2:
        body.pop("sequence_ok", None)
    return _canonical_bytes(body)


def _b64url_decode(segment: str) -> bytes:
    if not isinstance(segment, str):
        raise ContinuityLedgerError("JWS segment is not a string")
    pad = "=" * (-len(segment) % 4)
    try:
        return base64.urlsafe_b64decode(segment + pad)
    except (ValueError, base64.binascii.Error) as e:
        raise ContinuityLedgerError("JWS segment is not valid base64url: " + str(e))


def _verify_ed25519_b64(
    public_key_b64: str, signature_b64: str, body: bytes
) -> bool:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )
    from cryptography.exceptions import InvalidSignature
    try:
        pub = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(public_key_b64, validate=True)
        )
        pub.verify(base64.b64decode(signature_b64, validate=True), body)
        return True
    except (InvalidSignature, ValueError):
        return False


def _verify_conformance_leg(
    cert: Mapping[str, object],
    trace: Mapping[str, object],
    manifest: Mapping[str, object],
) -> None:
    """Offline conformance leg, byte-faithful to conformance_verifier
    CONFORMANCE_VERIFY_OFFLINE_PY: certificate Ed25519 signature; cert<->trace
    sha bind; cert<->manifest three-sha bind; optional codegen sha-equality;
    trace Ed25519 signature; recorded verdict consistent with the obligation
    booleans (six v1 / seven v2 / eight v4). cryptography + stdlib only. Raises
    ContinuityLedgerError, cause-first, on any failure."""
    csig = cert.get("signature")
    if not isinstance(csig, Mapping):
        raise ContinuityLedgerError("certificate has no signature block")
    if csig.get("algorithm") != "ed25519":
        raise ContinuityLedgerError(
            "certificate signature algorithm is not ed25519"
        )
    cpub = csig.get("public_key_b64", "")
    csigb = csig.get("signature_b64", "")
    if not cpub or not csigb:
        raise ContinuityLedgerError("certificate signature block incomplete")
    if not _verify_ed25519_b64(cpub, csigb, _cert_canonical_body_bytes(cert)):
        raise ContinuityLedgerError(
            "certificate Ed25519 signature does not verify"
        )

    trace_sha = hashlib.sha256(
        _doc_canonical_body_bytes(trace)
    ).hexdigest()
    if cert.get("trace_sha256") != trace_sha:
        raise ContinuityLedgerError(
            "cert.trace_sha256 != sha256(trace canonical body)"
        )

    for fld in ("source_sha256", "smt_spec_sha256", "pricing_sha256"):
        if cert.get(fld) != manifest.get(fld):
            raise ContinuityLedgerError(
                "cert." + fld + " != manifest." + fld
                + " (certificate not bound to this manifest)"
            )

    cert_cg = cert.get("codegen_sha256")
    if cert_cg is not None:
        man_cg = manifest.get("codegen_sha256")
        if man_cg is not None and man_cg != cert_cg:
            raise ContinuityLedgerError(
                "cert.codegen_sha256 != manifest.codegen_sha256"
            )
        tr_cg = trace.get("codegen_sha256")
        if tr_cg is not None and tr_cg != cert_cg:
            raise ContinuityLedgerError(
                "cert.codegen_sha256 != trace.codegen_sha256"
            )

    tsig = trace.get("signature")
    if not isinstance(tsig, Mapping):
        raise ContinuityLedgerError("trace has no signature block")
    if tsig.get("algorithm") != "ed25519":
        raise ContinuityLedgerError("trace signature algorithm is not ed25519")
    if not _verify_ed25519_b64(
        tsig.get("public_key_b64", ""),
        tsig.get("signature_b64", ""),
        _doc_canonical_body_bytes(trace),
    ):
        raise ContinuityLedgerError("trace Ed25519 signature does not verify")

    raw_schema = cert.get("certificate_schema_version", 1)
    try:
        schema_v = int(raw_schema)
    except (TypeError, ValueError):
        raise ContinuityLedgerError(
            "certificate_schema_version is not an integer: " + repr(raw_schema)
        )
    bools = _bools_for(schema_v)
    missing = [b for b in bools if b not in cert]
    if missing:
        raise ContinuityLedgerError(
            "certificate missing obligation fields: " + str(missing)
        )
    derived = all(bool(cert[b]) for b in bools)
    recorded = bool(cert.get("conformant"))
    if derived != recorded:
        raise ContinuityLedgerError(
            "certificate conformant=" + str(recorded)
            + " but the " + str(len(bools))
            + " obligations imply " + str(derived)
        )


def verify_link(
    *,
    cert: Mapping[str, object],
    trace: Mapping[str, object],
    manifest: Mapping[str, object],
    link: Mapping[str, object],
    receipt: Optional[Mapping[str, str]] = None,
    counterparty_public_key_pem: Optional[bytes] = None,
    expected_issuer: Optional[str] = None,
    expected_audience: Optional[str] = None,
) -> dict[str, object]:
    """Verify one continuity-ledger link in isolation, fail-closed.

    Checks link integrity (link_kind, this_link_digest recomputation,
    run-identity binding to cert+trace), the conformance leg over
    cert/trace/manifest, and -- when a receipt is present -- the receipt JWS
    signature against the resolved counterparty key plus every claim
    cross-check (sub, cert_body_sha256, conformant, prev_run_digest, iss, aud).
    Returns {certified: True, witnessed: bool, run_identity_digest, world,
    soul, consulted_seq_count}. Raises ContinuityLedgerError on any failure."""
    if link.get("link_kind") != LINK_KIND:
        raise ContinuityLedgerError(
            "link_kind is not " + repr(LINK_KIND) + ": " + repr(link.get("link_kind"))
        )
    _require_sha256_hex("link.prev_run_digest", link.get("prev_run_digest"))
    recorded_link_digest = _require_sha256_hex(
        "link.this_link_digest", link.get("this_link_digest")
    )
    _require_sha256_hex(
        "link.run_identity_digest", link.get("run_identity_digest")
    )

    recompute_src = {k: v for k, v in link.items() if k != "this_link_digest"}
    if hashlib.sha256(_canonical_bytes(recompute_src)).hexdigest() != recorded_link_digest:
        raise ContinuityLedgerError(
            "this_link_digest does not recompute (tampered link)"
        )

    _verify_conformance_leg(cert, trace, manifest)

    world, soul, head, seq = _extract_consultation(trace)
    cert_body = certificate_body_digest(cert)
    rid = run_identity_digest(
        world_sha256=world,
        producing_soul_sha256=soul,
        cert_body_sha256=cert_body,
        consulted_chain_head=head,
        consulted_seq_count=seq,
    )
    if rid != link.get("run_identity_digest"):
        raise ContinuityLedgerError(
            "link run_identity_digest not bound to this cert+trace"
        )

    witnessed = False
    if receipt is not None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
        from cryptography.exceptions import InvalidSignature
        if counterparty_public_key_pem is None:
            raise ContinuityLedgerError(
                "receipt present but no counterparty public key resolved"
            )
        if expected_audience is None:
            raise ContinuityLedgerError(
                "receipt present but no expected_audience to validate aud"
            )
        try:
            pub = serialization.load_pem_public_key(counterparty_public_key_pem)
        except ValueError as e:
            raise ContinuityLedgerError(
                "counterparty public key PEM does not load: " + str(e)
            )
        if not isinstance(pub, Ed25519PublicKey):
            raise ContinuityLedgerError(
                "counterparty public key is not Ed25519"
            )
        for fld in ("protected", "payload", "signature"):
            if not isinstance(receipt.get(fld), str) or not receipt.get(fld):
                raise ContinuityLedgerError(
                    "receipt missing JWS field: " + fld
                )
        protected = json.loads(_b64url_decode(receipt["protected"]))
        if protected.get("alg") != RECEIPT_ALG:
            raise ContinuityLedgerError("receipt alg is not EdDSA")
        if protected.get("typ") != RECEIPT_TYP:
            raise ContinuityLedgerError("receipt typ is not the receipt media type")
        signing_input = (
            receipt["protected"] + "." + receipt["payload"]
        ).encode("ascii")
        try:
            pub.verify(_b64url_decode(receipt["signature"]), signing_input)
        except InvalidSignature:
            raise ContinuityLedgerError(
                "receipt JWS signature does not verify against counterparty key"
            )
        claims = json.loads(_b64url_decode(receipt["payload"]))
        if expected_issuer is not None and claims.get("iss") != expected_issuer:
            raise ContinuityLedgerError(
                "receipt iss does not match the resolved key owner"
            )
        if claims.get("aud") != expected_audience:
            raise ContinuityLedgerError(
                "receipt aud does not match the expected world id"
            )
        if claims.get("sub") != link.get("run_identity_digest"):
            raise ContinuityLedgerError(
                "receipt sub does not match this link run_identity_digest"
            )
        if claims.get("cert_body_sha256") != cert_body:
            raise ContinuityLedgerError(
                "receipt cert_body_sha256 does not match this certificate"
            )
        if bool(claims.get("conformant")) != bool(cert.get("conformant")):
            raise ContinuityLedgerError(
                "receipt conformant does not match the certificate verdict"
            )
        if claims.get("prev_run_digest") != link.get("prev_run_digest"):
            raise ContinuityLedgerError(
                "receipt prev_run_digest does not match this link"
            )
        witnessed = True

    return {
        "certified": True,
        "witnessed": witnessed,
        "run_identity_digest": rid,
        "world_sha256": world,
        "producing_soul_sha256": soul,
        "consulted_seq_count": seq,
        "this_link_digest": recorded_link_digest,
    }


def walk_continuity_ledger(
    links: "list[Mapping[str, object]]",
    *,
    counterparty_keys: Optional[Mapping[str, bytes]] = None,
    expected_audience: Optional[str] = None,
    expected_issuer: Optional[str] = None,
) -> dict[str, object]:
    """Walk a continuity ledger fail-closed (design 7.3 + 10).

    `links` is a list of bundles, each a mapping with keys cert, trace,
    manifest, link, and optional receipt. Establishes exactly one genesis
    (prev_run_digest == GENESIS_PREV_RUN_DIGEST), orders the links by the
    prev_run_digest hash chain (each non-genesis prev must equal a present
    link this_link_digest), refuses on a dangling prev, a fork, more than one
    genesis, or a cycle / disconnected link, verifies each link, and enforces
    non-decreasing consulted_seq_count within a matching (world, soul). Returns
    {n_links, n_witnessed, witnessed_ratio, order, per_link}. Reports a link
    with no receipt as certified-but-un-witnessed (operator-only), never a
    failure -- witness is additive. Raises ContinuityLedgerError on any
    fail-closed condition."""
    if not links:
        raise ContinuityLedgerError("empty ledger: nothing to walk")

    by_digest: dict[str, Mapping[str, object]] = {}
    for bundle in links:
        lk = bundle.get("link")
        if not isinstance(lk, Mapping):
            raise ContinuityLedgerError("ledger bundle missing link.json")
        tld = _require_sha256_hex("this_link_digest", lk.get("this_link_digest"))
        if tld in by_digest:
            raise ContinuityLedgerError(
                "duplicate this_link_digest in ledger: " + tld[:16]
            )
        by_digest[tld] = bundle

    genesis = [
        b for b in links
        if b["link"].get("prev_run_digest") == GENESIS_PREV_RUN_DIGEST
    ]
    if len(genesis) != 1:
        raise ContinuityLedgerError(
            "ledger must have exactly one genesis link, found " + str(len(genesis))
        )

    successor: dict[str, str] = {}
    for b in links:
        prev = b["link"].get("prev_run_digest")
        if prev == GENESIS_PREV_RUN_DIGEST:
            continue
        if prev not in by_digest:
            raise ContinuityLedgerError(
                "dangling prev_run_digest names no present link: " + str(prev)[:16]
            )
        if prev in successor:
            raise ContinuityLedgerError(
                "fork: two links share predecessor " + str(prev)[:16]
                + " (ledger is not a single chain)"
            )
        successor[prev] = b["link"]["this_link_digest"]

    order: list[Mapping[str, object]] = [genesis[0]]
    cursor = genesis[0]["link"]["this_link_digest"]
    seen: set[str] = {cursor}
    while cursor in successor:
        nxt = successor[cursor]
        if nxt in seen:
            raise ContinuityLedgerError("cycle detected in ledger chain")
        order.append(by_digest[nxt])
        seen.add(nxt)
        cursor = nxt
    if len(order) != len(links):
        raise ContinuityLedgerError(
            "ledger is not a single contiguous chain "
            "(" + str(len(order)) + " reachable of " + str(len(links)) + ")"
        )

    per_link: list[dict[str, object]] = []
    prev_world = ""
    prev_soul = ""
    prev_seq = -1
    for b in order:
        receipt = b.get("receipt")
        pem: Optional[bytes] = None
        issuer_for_link: Optional[str] = expected_issuer
        if receipt is not None:
            iss = _peek_receipt_issuer(receipt)
            issuer_for_link = iss
            if counterparty_keys is None or iss not in counterparty_keys:
                raise ContinuityLedgerError(
                    "no published counterparty key for receipt issuer: " + iss
                )
            pem = counterparty_keys[iss]
        report = verify_link(
            cert=b["cert"],
            trace=b["trace"],
            manifest=b["manifest"],
            link=b["link"],
            receipt=receipt,
            counterparty_public_key_pem=pem,
            expected_issuer=issuer_for_link,
            expected_audience=expected_audience,
        )
        world = report["world_sha256"]
        soul = report["producing_soul_sha256"]
        seq = report["consulted_seq_count"]
        if world == prev_world and soul == prev_soul:
            if not isinstance(seq, int) or seq < prev_seq:
                raise ContinuityLedgerError(
                    "consulted_seq_count decreased within one (world, soul): "
                    + str(prev_seq) + " -> " + str(seq) + " (reordering)"
                )
        prev_world, prev_soul, prev_seq = world, soul, seq if isinstance(seq, int) else prev_seq
        per_link.append(report)

    n = len(per_link)
    n_witnessed = sum(1 for r in per_link if r["witnessed"])
    return {
        "n_links": n,
        "n_witnessed": n_witnessed,
        "witnessed_ratio": (n_witnessed / n) if n else 0.0,
        "order": [r["this_link_digest"] for r in per_link],
        "per_link": per_link,
    }


def _peek_receipt_issuer(receipt: Mapping[str, str]) -> str:
    payload = receipt.get("payload")
    if not isinstance(payload, str) or not payload:
        raise ContinuityLedgerError("receipt has no payload to read iss from")
    claims = json.loads(_b64url_decode(payload))
    iss = claims.get("iss")
    if not isinstance(iss, str) or not iss:
        raise ContinuityLedgerError("receipt payload has no string iss claim")
    return iss
