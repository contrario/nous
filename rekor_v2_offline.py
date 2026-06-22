#!/usr/bin/env python3
"""Offline verifier for a Rekor v2 (rekor-tiles) hashedrekord/0.0.2 entry.

Dependencies: cryptography + Python stdlib ONLY. No sigstore, no rfc3161-client,
no network. This is the NOUS "evidence that travels" verifier: given a captured
Rekor v2 entry bundle and TUF-pinned roots, it re-derives, fully offline:

  leg 1  RFC 6962 Merkle inclusion of the entry under the checkpoint root
  leg 2  C2SP signed-note checkpoint signature against the pinned log Ed25519 key
  leg 3  RFC 3161 timestamp token against the pinned TSA chain, binding genTime
         to sha256(entry signature) (Sigstore countersigns the signature bytes)

Verdict is EVIDENCES-only: it attests public, append-only, timestamped inclusion
of the named digest. It PROVES nothing about the digest's meaning ('proves' is
reserved for Z3/Farkas). NOUS is a monitor, not a guard.

leg 1 and leg 2 are self-tested in __main__ (--selftest). leg 3 is validated
separately against a real production TSA response on a networked host (see the
companion harness) before being relied upon.
"""
from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_der_public_key
from cryptography.x509 import Certificate, load_der_x509_certificate, load_pem_x509_certificates
from cryptography.x509.oid import ExtendedKeyUsageOID, ExtensionOID


class VerificationError(Exception):
    """Raised on any failed offline verification step. Never a silent fallback."""


# ---------------------------------------------------------------------------
# leg 1: RFC 6962 Merkle inclusion (Trillian decomposition, matches reference)
# ---------------------------------------------------------------------------

_LEAF_HASH_PREFIX = b"\x00"
_NODE_HASH_PREFIX = b"\x01"


def _hash_leaf(leaf: bytes) -> bytes:
    return hashlib.sha256(_LEAF_HASH_PREFIX + leaf).digest()


def _hash_children(lhs: bytes, rhs: bytes) -> bytes:
    return hashlib.sha256(_NODE_HASH_PREFIX + lhs + rhs).digest()


def _decomp_inclusion_proof(index: int, size: int) -> tuple[int, int]:
    inner = (index ^ (size - 1)).bit_length()
    border = bin(index >> inner).count("1")
    return inner, border


def _chain_inner(seed: bytes, proof: list[bytes], index: int) -> bytes:
    acc = seed
    for i, h in enumerate(proof):
        if (index >> i) & 1 == 0:
            acc = _hash_children(acc, h)
        else:
            acc = _hash_children(h, acc)
    return acc


def _chain_border_right(seed: bytes, proof: list[bytes]) -> bytes:
    acc = seed
    for h in proof:
        acc = _hash_children(h, acc)
    return acc


def verify_inclusion(
    canonicalized_body: bytes,
    log_index: int,
    tree_size: int,
    proof_hashes: list[bytes],
    root_hash: bytes,
) -> bytes:
    """Return the leaf hash if the entry is included under root_hash, else raise."""
    if not (0 <= log_index < tree_size):
        raise VerificationError(f"log_index {log_index} out of range for tree_size {tree_size}")
    inner, border = _decomp_inclusion_proof(log_index, tree_size)
    if len(proof_hashes) != inner + border:
        raise VerificationError(
            f"inclusion proof wrong size: expected {inner + border}, got {len(proof_hashes)}"
        )
    leaf_hash = _hash_leaf(canonicalized_body)
    mid = _chain_inner(leaf_hash, proof_hashes[:inner], log_index)
    calc = _chain_border_right(mid, proof_hashes[inner:])
    if calc != root_hash:
        raise VerificationError(
            f"inclusion root mismatch: expected {root_hash.hex()}, calculated {calc.hex()}"
        )
    return leaf_hash


# ---------------------------------------------------------------------------
# leg 2: C2SP signed-note checkpoint
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Checkpoint:
    origin: str
    tree_size: int
    root_hash: bytes
    body: bytes
    signatures: list[tuple[str, bytes, bytes]]


def parse_checkpoint(note: str) -> Checkpoint:
    head, sep, tail = note.partition("\n\n")
    if not sep:
        raise VerificationError("checkpoint missing text/signature separator")
    body = (head + "\n").encode("utf-8")
    lines = head.split("\n")
    if len(lines) < 3:
        raise VerificationError("checkpoint body has too few lines")
    try:
        tree_size = int(lines[1])
    except ValueError as exc:
        raise VerificationError("checkpoint tree size not an integer") from exc
    try:
        root_hash = base64.b64decode(lines[2])
    except Exception as exc:  # noqa: BLE001
        raise VerificationError("checkpoint root hash not base64") from exc
    sigs: list[tuple[str, bytes, bytes]] = []
    for line in tail.split("\n"):
        if not line.strip():
            continue
        parts = line.split(" ")
        if len(parts) < 3 or parts[0] != "\u2014":
            continue
        blob = base64.b64decode(parts[2])
        sigs.append((parts[1], blob[:4], blob[4:]))
    if not sigs:
        raise VerificationError("checkpoint carries no parseable signatures")
    return Checkpoint(lines[0], tree_size, root_hash, body, sigs)


def verify_checkpoint_signature(cp: Checkpoint, log_key: Ed25519PublicKey, key_id: bytes) -> None:
    for _name, hint, sig in cp.signatures:
        if hint != key_id[:4]:
            continue
        try:
            log_key.verify(sig, cp.body)
            return
        except InvalidSignature as exc:
            raise VerificationError("checkpoint key-hint matched but signature invalid") from exc
    for _name, _hint, sig in cp.signatures:
        try:
            log_key.verify(sig, cp.body)
            return
        except InvalidSignature:
            continue
    raise VerificationError("no checkpoint signature verified against the pinned log key")


# ---------------------------------------------------------------------------
# minimal DER reader (leg 3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TLV:
    tag: int
    value: bytes
    start: int
    end: int  # offset just past this TLV in the parent buffer


def _read_tlv(buf: bytes, off: int) -> TLV:
    start = off
    tag = buf[off]
    off += 1
    if tag & 0x1F == 0x1F:
        raise VerificationError("multi-byte DER tags unsupported")
    first = buf[off]
    off += 1
    if first < 0x80:
        length = first
    else:
        nbytes = first & 0x7F
        if nbytes == 0 or nbytes > 4:
            raise VerificationError("unsupported DER length encoding")
        length = int.from_bytes(buf[off : off + nbytes], "big")
        off += nbytes
    value = buf[off : off + length]
    if len(value) != length:
        raise VerificationError("DER length exceeds buffer")
    return TLV(tag, value, start, off + length)


def _children(value: bytes) -> list[TLV]:
    out: list[TLV] = []
    off = 0
    while off < len(value):
        node = _read_tlv(value, off)
        out.append(node)
        off = node.end
    return out


def _expect(node: TLV, tag: int, what: str) -> TLV:
    if node.tag != tag:
        raise VerificationError(f"{what}: expected tag 0x{tag:02x}, got 0x{node.tag:02x}")
    return node


def _oid_str(value: bytes) -> str:
    if not value:
        raise VerificationError("empty OID")
    first = value[0]
    parts = [str(first // 40), str(first % 40)]
    acc = 0
    for byte in value[1:]:
        acc = (acc << 7) | (byte & 0x7F)
        if not byte & 0x80:
            parts.append(str(acc))
            acc = 0
    return ".".join(parts)


_OID_SIGNED_DATA = "1.2.840.113549.1.7.2"
_OID_TST_INFO = "1.2.840.113549.1.9.16.1.4"
_OID_MESSAGE_DIGEST = "1.2.840.113549.1.9.4"
_OID_CONTENT_TYPE = "1.2.840.113549.1.9.3"
_OID_SHA256 = "2.16.840.1.101.3.4.2.1"
_OID_SHA384 = "2.16.840.1.101.3.4.2.2"
_OID_SHA512 = "2.16.840.1.101.3.4.2.3"
_HASH_BY_OID = {_OID_SHA256: hashes.SHA256, _OID_SHA384: hashes.SHA384, _OID_SHA512: hashes.SHA512}


def _parse_genalized_time(raw: bytes) -> _dt.datetime:
    text = raw.decode("ascii")
    if text.endswith("Z"):
        text = text[:-1]
    if "." in text:
        base, frac = text.split(".", 1)
        micro = int((frac + "000000")[:6])
    else:
        base, micro = text, 0
    dt = _dt.datetime.strptime(base, "%Y%m%d%H%M%S")
    return dt.replace(microsecond=micro, tzinfo=_dt.timezone.utc)


# ---------------------------------------------------------------------------
# leg 3: RFC 3161 timestamp token
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TimestampResult:
    gen_time: _dt.datetime
    message_imprint: bytes
    imprint_hash_oid: str


def _find_signed_data(node: TLV) -> TLV | None:
    if node.tag != 0x30:
        return None
    kids = _children(node.value)
    if kids and kids[0].tag == 0x06 and _oid_str(kids[0].value) == _OID_SIGNED_DATA:
        explicit0 = _expect(kids[1], 0xA0, "[0] EXPLICIT content")
        return _expect(_children(explicit0.value)[0], 0x30, "SignedData")
    for child in kids:
        found = _find_signed_data(child)
        if found is not None:
            return found
    return None


def _signed_data_from_token(token_der: bytes) -> TLV:
    outer = _read_tlv(token_der, 0)
    sd = _find_signed_data(outer)
    if sd is None:
        raise VerificationError("no id-signedData ContentInfo found (not a TSR or token)")
    return sd


def _verify_cert_signature(cert: Certificate, issuer: Certificate) -> None:
    pub = issuer.public_key()
    try:
        if isinstance(pub, ec.EllipticCurvePublicKey):
            pub.verify(cert.signature, cert.tbs_certificate_bytes, ec.ECDSA(cert.signature_hash_algorithm))
        elif isinstance(pub, rsa.RSAPublicKey):
            pub.verify(cert.signature, cert.tbs_certificate_bytes, padding.PKCS1v15(), cert.signature_hash_algorithm)
        elif isinstance(pub, ed25519.Ed25519PublicKey):
            pub.verify(cert.signature, cert.tbs_certificate_bytes)
        else:
            raise VerificationError(f"unsupported issuer key type {type(pub).__name__}")
    except InvalidSignature as exc:
        raise VerificationError("certificate signature does not verify against issuer") from exc


def _build_and_verify_chain(leaf: Certificate, roots: list[Certificate], at: _dt.datetime) -> None:
    pool = {c.subject.rfc4514_string(): c for c in roots}
    current = leaf
    seen = 0
    while True:
        if current.not_valid_before_utc > at or current.not_valid_after_utc < at:
            raise VerificationError("certificate not valid at timestamp genTime")
        issuer_name = current.issuer.rfc4514_string()
        if current.subject.rfc4514_string() == issuer_name:
            _verify_cert_signature(current, current)
            return
        issuer = pool.get(issuer_name)
        if issuer is None:
            raise VerificationError(f"no pinned issuer for {issuer_name}")
        _verify_cert_signature(current, issuer)
        current = issuer
        seen += 1
        if seen > 8:
            raise VerificationError("certificate chain too long")


def verify_timestamp(
    token_der: bytes,
    tsa_roots_pem: bytes,
    expected_imprint_message: bytes,
) -> TimestampResult:
    """Verify an RFC 3161 token; return genTime if it binds the expected message."""
    signed_data = _signed_data_from_token(token_der)
    nodes = _children(signed_data.value)

    enc_idx = next(i for i, n in enumerate(nodes) if n.tag == 0x30 and i >= 2)
    encap = nodes[enc_idx]
    enc_children = _children(encap.value)
    if _oid_str(_expect(enc_children[0], 0x06, "eContentType").value) != _OID_TST_INFO:
        raise VerificationError("encapsulated content is not id-ct-TSTInfo")
    econtent_explicit = _expect(enc_children[1], 0xA0, "[0] eContent")
    tst_octets = _expect(_children(econtent_explicit.value)[0], 0x04, "TSTInfo OCTET STRING")
    tst_info_der = tst_octets.value

    certs: list[Certificate] = []
    for node in nodes:
        if node.tag == 0xA0 and node.start >= encap.end:
            for cert_tlv in _children(node.value):
                certs.append(load_der_x509_certificate(_reencode(cert_tlv)))
    if not certs:
        raise VerificationError("token carries no embedded certificates")

    signer_infos = next(n for n in nodes if n.tag == 0x31 and n.start > encap.end)
    signer_info = _expect(_children(signer_infos.value)[0], 0x30, "SignerInfo")
    si = _children(signer_info.value)
    if len(si) < 5:
        raise VerificationError("SignerInfo has too few fields")

    digest_alg_tlv = _expect(si[2], 0x30, "digestAlgorithm")
    digest_alg_oid = _oid_str(_children(digest_alg_tlv.value)[0].value)
    hash_cls = _HASH_BY_OID.get(digest_alg_oid)
    if hash_cls is None:
        raise VerificationError(f"unsupported signedAttrs digest algorithm {digest_alg_oid}")

    pos = 3
    if si[pos].tag != 0xA0:
        raise VerificationError("SignerInfo without signedAttrs unsupported")
    signed_attrs_tlv = si[pos]
    pos += 1
    _expect(si[pos], 0x30, "signatureAlgorithm")
    pos += 1
    signature = _expect(si[pos], 0x04, "signature").value

    attrs = _children(signed_attrs_tlv.value)
    md = _attr_value(attrs, _OID_MESSAGE_DIGEST)
    ct = _attr_value(attrs, _OID_CONTENT_TYPE)
    if _oid_str(ct) != _OID_TST_INFO:
        raise VerificationError("signedAttrs contentType is not id-ct-TSTInfo")
    if md != hashlib.new(_digest_name(digest_alg_oid), tst_info_der).digest():
        raise VerificationError("signedAttrs messageDigest does not match TSTInfo")

    signed_bytes = b"\x31" + _der_len(len(signed_attrs_tlv.value)) + signed_attrs_tlv.value

    signer = _select_signer(certs, signer_info)
    _verify_signer_signature(signer, signature, signed_bytes, hash_cls())

    eku = signer.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE).value
    if ExtendedKeyUsageOID.TIME_STAMPING not in eku:
        raise VerificationError("signer certificate lacks id-kp-timeStamping EKU")

    gen_time, imprint, imprint_oid = _parse_tstinfo(tst_info_der)
    _build_and_verify_chain(signer, load_pem_x509_certificates(tsa_roots_pem), gen_time)

    expected = hashlib.new(_digest_name(imprint_oid), expected_imprint_message).digest()
    if imprint != expected:
        raise VerificationError("TSTInfo messageImprint does not bind the expected message")
    return TimestampResult(gen_time, imprint, imprint_oid)


def _reencode(tlv: TLV) -> bytes:
    return bytes([tlv.tag]) + _der_len(len(tlv.value)) + tlv.value


def _der_len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    body = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(body)]) + body


def _digest_name(oid: str) -> str:
    return {_OID_SHA256: "sha256", _OID_SHA384: "sha384", _OID_SHA512: "sha512"}[oid]


def _attr_value(attrs: list[TLV], oid: str) -> bytes:
    for attr in attrs:
        ac = _children(attr.value)
        if _oid_str(_expect(ac[0], 0x06, "attr oid").value) == oid:
            return _children(_expect(ac[1], 0x31, "attr values").value)[0].value
    raise VerificationError(f"signedAttrs missing attribute {oid}")


def _select_signer(certs: list[Certificate], signer_info: TLV) -> Certificate:
    si = _children(signer_info.value)
    sid = si[1]
    if sid.tag == 0x30:
        ias = _children(sid.value)
        serial = int.from_bytes(_expect(ias[1], 0x02, "serial").value, "big")
        for cert in certs:
            if cert.serial_number == serial:
                return cert
    return certs[0]


def _verify_signer_signature(signer: Certificate, signature: bytes, signed_bytes: bytes, halg: Any) -> None:
    pub = signer.public_key()
    try:
        if isinstance(pub, ec.EllipticCurvePublicKey):
            pub.verify(signature, signed_bytes, ec.ECDSA(halg))
        elif isinstance(pub, rsa.RSAPublicKey):
            pub.verify(signature, signed_bytes, padding.PKCS1v15(), halg)
        elif isinstance(pub, ed25519.Ed25519PublicKey):
            pub.verify(signature, signed_bytes)
        else:
            raise VerificationError(f"unsupported signer key type {type(pub).__name__}")
    except InvalidSignature as exc:
        raise VerificationError("TSA signerInfo signature invalid over signedAttrs") from exc


def _parse_tstinfo(tst_info_der: bytes) -> tuple[_dt.datetime, bytes, str]:
    seq = _expect(_read_tlv(tst_info_der, 0), 0x30, "TSTInfo")
    fields = _children(seq.value)
    imprint_seq = _expect(fields[2], 0x30, "messageImprint")
    ic = _children(imprint_seq.value)
    halg_oid = _oid_str(_children(_expect(ic[0], 0x30, "imprint halg").value)[0].value)
    hashed = _expect(ic[1], 0x04, "hashedMessage").value
    gen_time = None
    for node in fields[3:]:
        if node.tag == 0x18:
            gen_time = _parse_genalized_time(node.value)
            break
    if gen_time is None:
        raise VerificationError("TSTInfo missing genTime")
    return gen_time, hashed, halg_oid


# ---------------------------------------------------------------------------
# orchestrator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pins:
    log_key: Ed25519PublicKey
    log_key_id: bytes
    tsa_roots_pem: bytes


def load_pins(pins_dir: Path) -> Pins:
    tr = json.loads((pins_dir / "trusted_root.json").read_text())
    v2 = None
    for tlog in tr.get("tlogs", []):
        if tlog.get("publicKey", {}).get("keyDetails") == "PKIX_ED25519":
            v2 = tlog
    if v2 is None:
        raise VerificationError("no PKIX_ED25519 rekor v2 tlog in pinned trusted_root")
    der = base64.b64decode(v2["publicKey"]["rawBytes"])
    key = load_der_public_key(der)
    if not isinstance(key, Ed25519PublicKey):
        key = Ed25519PublicKey.from_public_bytes(der[-32:])
    return Pins(
        log_key=key,
        log_key_id=base64.b64decode(v2["logId"]["keyId"]),
        tsa_roots_pem=(pins_dir / "tsa_chain.pem").read_bytes(),
    )


@dataclass(frozen=True)
class Verdict:
    included: bool
    checkpoint_ok: bool
    timestamp: _dt.datetime | None
    tree_size: int
    log_index: int
    leaf_hash_hex: str


def verify_entry(bundle: dict[str, Any], pins: Pins, verify_time: bool = True) -> Verdict:
    tle = bundle["transparency_log_entry"]
    canonicalized_body = base64.b64decode(tle["canonicalized_body"])
    log_index = int(tle["log_index"])
    proof = tle["inclusion_proof"]
    tree_size = int(proof["tree_size"])
    proof_hashes = [base64.b64decode(h) for h in proof["hashes"]]

    cp = parse_checkpoint(proof["checkpoint"])
    verify_checkpoint_signature(cp, pins.log_key, pins.log_key_id)
    if cp.tree_size != tree_size:
        raise VerificationError("inclusion tree_size disagrees with verified checkpoint")

    leaf = verify_inclusion(canonicalized_body, log_index, tree_size, proof_hashes, cp.root_hash)

    ts: _dt.datetime | None = None
    if verify_time:
        token = base64.b64decode(bundle["rfc3161_timestamp"])
        sig_bytes = base64.b64decode(bundle["entry_signature"])
        ts = verify_timestamp(token, pins.tsa_roots_pem, sig_bytes).gen_time

    return Verdict(True, True, ts, tree_size, log_index, leaf.hex())


# ---------------------------------------------------------------------------
# self-test (legs 1 + 2, offline, no fixtures)
# ---------------------------------------------------------------------------


def _naive_root(leaves: list[bytes]) -> bytes:
    nodes = [_hash_leaf(x) for x in leaves]
    if len(nodes) == 1:
        return nodes[0]

    def build(items: list[bytes]) -> bytes:
        if len(items) == 1:
            return items[0]
        k = 1
        while k * 2 < len(items):
            k *= 2
        return _hash_children(build(items[:k]), build(items[k:]))

    return build(nodes)


def _naive_proof(leaves: list[bytes], index: int) -> list[bytes]:
    proof: list[bytes] = []

    def _subtree(items: list[bytes]) -> bytes:
        if len(items) == 1:
            return items[0]
        k = 1
        while k * 2 < len(items):
            k *= 2
        return _hash_children(_subtree(items[:k]), _subtree(items[k:]))

    def recurse(items: list[bytes], idx: int) -> bytes:
        if len(items) == 1:
            return items[0]
        k = 1
        while k * 2 < len(items):
            k *= 2
        if idx < k:
            left = recurse(items[:k], idx)
            right = _subtree(items[k:])
            proof.append(right)
            return _hash_children(left, right)
        right = recurse(items[k:], idx - k)
        left = _subtree(items[:k])
        proof.append(left)
        return _hash_children(left, right)

    recurse([_hash_leaf(x) for x in leaves], index)
    return proof


def _selftest() -> int:
    import os

    ok = True
    for size in range(1, 33):
        leaves = [os.urandom(24) for _ in range(size)]
        root = _naive_root(leaves)
        for index in range(size):
            proof = _naive_proof(leaves, index)
            try:
                verify_inclusion(leaves[index], index, size, proof, root)
            except VerificationError as exc:
                print(f"FAIL inclusion size={size} index={index}: {exc}")
                ok = False
                break
            if proof:
                bad = list(proof)
                bad[0] = bytes(b ^ 0xFF for b in bad[0])
                try:
                    verify_inclusion(leaves[index], index, size, bad, root)
                    print(f"FAIL tamper not detected size={size} index={index}")
                    ok = False
                except VerificationError:
                    pass
    print("leg1 inclusion KAT (sizes 1..32, all indices, tamper-negatives):", "PASS" if ok else "FAIL")

    priv = ed25519.Ed25519PrivateKey.generate()
    pub = priv.public_key()
    body_text = "log2025-1.rekor.sigstore.dev\n777\n" + base64.b64encode(b"r" * 32).decode() + "\n"
    sig = priv.sign(body_text.encode())
    key_id = hashlib.sha256(b"k").digest()
    note = body_text + "\n\u2014 origin " + base64.b64encode(key_id[:4] + sig).decode() + "\n"
    cp = parse_checkpoint(note)
    try:
        verify_checkpoint_signature(cp, pub, key_id)
        cp_ok = True
    except VerificationError:
        cp_ok = False
    bad_note = note.replace("777", "778", 1)
    try:
        verify_checkpoint_signature(parse_checkpoint(bad_note), pub, key_id)
        tamper_ok = False
    except VerificationError:
        tamper_ok = True
    print("leg2 checkpoint KAT (sign + tamper-negative):", "PASS" if cp_ok and tamper_ok else "FAIL")
    return 0 if (ok and cp_ok and tamper_ok) else 1


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("usage: rekor_v2_offline.py --selftest", file=sys.stderr)
    raise SystemExit(2)
