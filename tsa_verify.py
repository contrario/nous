"""
NOUS RFC 3161 timestamp verifier (offline read path).

Verifies an RFC 3161 TimeStampToken (CMS SignedData carrying a TSTInfo)
using ONLY the cryptography library plus the Python standard library. No
third-party ASN.1 dependency: a minimal DER TLV walker extracts the TSTInfo,
the SignerInfo, and the embedded signer certificate; cryptography performs
all signature, certificate-chain, and digest checks.

This is the trusted-time companion to the Rekor v2 anchor: a v2 entry
carries integrated_time = 0, so a TimeStampToken from a pinned RFC 3161
Timestamp Authority supplies the trusted time. The token is timestamped over
the leaf signature bytes, so the verifier binds the timestamp to the same
ECDSA signature the Rekor v2 leaf carries.

Trust model: the TSA signer certificate is embedded in the token; only the
self-signed TSA root is pinned (KNOWN_TSA_ROOT_CERTS, mirroring the Rekor v2
log-key allowlist). The signer must chain directly to a pinned root and
carry the id-kp-timeStamping extended key usage. An empty trusted-root set
fails closed.

Checks performed (each an independent boolean in Rfc3161VerifyDetail):
  signer_chain_ok    signer cert has timeStamping EKU and is issued by a
                     pinned self-signed root
  signer_sig_ok      SignerInfo signature verifies over the reconstructed
                     SignedAttributes DER (tag re-encoded to SET OF)
  content_type_ok    content-type signed attribute is id-ct-TSTInfo
  message_digest_ok  message-digest signed attribute equals the digest of
                     the encapsulated TSTInfo
  imprint_binds_ok   TSTInfo messageImprint equals the digest of the
                     supplied timestamped_data
Structural malformation (not a verification outcome) raises
Rfc3161Malformed; cryptographic failures are reported as False, not raised.

# __nous_aetherproof_tsa_verify_module_v1__
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
from cryptography.x509.oid import ExtendedKeyUsageOID

OID_SIGNED_DATA = "1.2.840.113549.1.7.2"
OID_CT_TSTINFO = "1.2.840.113549.1.9.16.1.4"
OID_ATTR_CONTENT_TYPE = "1.2.840.113549.1.9.3"
OID_ATTR_MESSAGE_DIGEST = "1.2.840.113549.1.9.4"

KNOWN_TSA_ROOT_CERTS: list[str] = [
    "-----BEGIN CERTIFICATE-----\n"
    "MIIB9zCCAXygAwIBAgIUV7f0GLDOoEzIh8LXSW80OJiUp14wCgYIKoZIzj0EAwMw\n"
    "OTEVMBMGA1UEChMMc2lnc3RvcmUuZGV2MSAwHgYDVQQDExdzaWdzdG9yZS10c2Et\n"
    "c2VsZnNpZ25lZDAeFw0yNTA0MDgwNjU5NDNaFw0zNTA0MDYwNjU5NDNaMDkxFTAT\n"
    "BgNVBAoTDHNpZ3N0b3JlLmRldjEgMB4GA1UEAxMXc2lnc3RvcmUtdHNhLXNlbGZz\n"
    "aWduZWQwdjAQBgcqhkjOPQIBBgUrgQQAIgNiAAQUQNtfRT/ou3YATa6wB/kKTe70\n"
    "cfJwyRIBovMnt8RcJph/COE82uyS6FmppLLL1VBPGcPfpQPYJNXzWwi8icwhKQ6W\n"
    "/Qe2h3oebBb2FHpwNJDqo+TMaC/tdfkv/ElJB72jRTBDMA4GA1UdDwEB/wQEAwIB\n"
    "BjASBgNVHRMBAf8ECDAGAQH/AgEAMB0GA1UdDgQWBBSY7AHvf7tR/9SVHm+KiJhT\n"
    "B4nOvzAKBggqhkjOPQQDAwNpADBmAjEAwGEGrfGZR1cen1R8/DTVMI943LssZmJR\n"
    "tDp/i7SfGHmGRP6gRbuj9vOK3b67Z0QQAjEAuT2H673LQEaHTcyQSZrkp4mX7Wwk\n"
    "mF+sVbkYY5mXN+RMH13KUEHHOqASaemYWK/E\n"
    "-----END CERTIFICATE-----\n",
]

_ECDSA_SIG_OIDS = {
    "1.2.840.10045.4.3.2": hashes.SHA256,
    "1.2.840.10045.4.3.3": hashes.SHA384,
    "1.2.840.10045.4.3.4": hashes.SHA512,
}
_RSA_SIG_OIDS = {
    "1.2.840.113549.1.1.11": hashes.SHA256,
    "1.2.840.113549.1.1.12": hashes.SHA384,
    "1.2.840.113549.1.1.13": hashes.SHA512,
}
_DIGEST_OIDS = {
    "2.16.840.1.101.3.4.2.1": "sha256",
    "2.16.840.1.101.3.4.2.2": "sha384",
    "2.16.840.1.101.3.4.2.3": "sha512",
}


class Rfc3161Error(ValueError):
    """Base class for RFC 3161 timestamp verification failures."""


class Rfc3161Malformed(Rfc3161Error):
    """The token is not a structurally valid RFC 3161 TimeStampToken."""


@dataclass(frozen=True, slots=True)
class Rfc3161VerifyDetail:
    """Per-step result of verifying an RFC 3161 TimeStampToken."""

    signer_chain_ok: bool
    signer_sig_ok: bool
    content_type_ok: bool
    message_digest_ok: bool
    imprint_binds_ok: bool
    gen_time: datetime | None
    signer_subject: str | None
    errors: tuple[str, ...] = field(default=())

    @property
    def ok(self) -> bool:
        return (
            self.signer_chain_ok
            and self.signer_sig_ok
            and self.content_type_ok
            and self.message_digest_ok
            and self.imprint_binds_ok
        )


def _der_len(buf: bytes, off: int) -> tuple[int, int]:
    b = buf[off]
    if b < 0x80:
        return b, off + 1
    n = b & 0x7F
    if n == 0 or n > 4:
        raise Rfc3161Malformed("unsupported DER length form")
    return int.from_bytes(buf[off + 1 : off + 1 + n], "big"), off + 1 + n


def _tlv(buf: bytes, off: int) -> tuple[int, int, int, int]:
    tag = buf[off]
    length, hdr_end = _der_len(buf, off + 1)
    end = hdr_end + length
    if end > len(buf):
        raise Rfc3161Malformed("DER length exceeds buffer")
    return tag, off, hdr_end, end


def _children(buf: bytes, start: int, end: int) -> list[tuple[int, int, int, int]]:
    out: list[tuple[int, int, int, int]] = []
    off = start
    while off < end:
        tag, tlv_start, c_off, c_end = _tlv(buf, off)
        out.append((tag, tlv_start, c_off, c_end))
        off = c_end
    return out


def _oid_str(buf: bytes, c_off: int, c_end: int) -> str:
    data = buf[c_off:c_end]
    if not data:
        raise Rfc3161Malformed("empty OID")
    first = data[0]
    parts = [str(first // 40), str(first % 40)]
    val = 0
    for byte in data[1:]:
        val = (val << 7) | (byte & 0x7F)
        if not byte & 0x80:
            parts.append(str(val))
            val = 0
    return ".".join(parts)


def _parse_token(token_der: bytes) -> dict:
    try:
        _, _, ci_c, ci_end = _tlv(token_der, 0)
        ci_kids = _children(token_der, ci_c, ci_end)
        if _oid_str(token_der, ci_kids[0][2], ci_kids[0][3]) != OID_SIGNED_DATA:
            raise Rfc3161Malformed("token is not a CMS SignedData")
        sd = _children(token_der, ci_kids[1][2], ci_kids[1][3])[0]
        sd_kids = _children(token_der, sd[2], sd[3])

        enc = next(k for k in sd_kids if k[0] == 0x30)
        enc_kids = _children(token_der, enc[2], enc[3])
        if _oid_str(token_der, enc_kids[0][2], enc_kids[0][3]) != OID_CT_TSTINFO:
            raise Rfc3161Malformed("eContentType is not id-ct-TSTInfo")
        oct0 = _children(token_der, enc_kids[1][2], enc_kids[1][3])[0]
        tstinfo = token_der[oct0[2] : oct0[3]]

        certs = []
        for k in sd_kids:
            if k[0] == 0xA0:
                for c in _children(token_der, k[2], k[3]):
                    certs.append(token_der[c[1] : c[3]])
                break

        signer_set = [k for k in sd_kids if k[0] == 0x31 and k[1] > enc[3]][0]
        si = _children(token_der, signer_set[2], signer_set[3])[0]
        si_kids = _children(token_der, si[2], si[3])

        i = 2
        digest_alg = _children(token_der, si_kids[i][2], si_kids[i][3])
        digest_oid = _oid_str(token_der, digest_alg[0][2], digest_alg[0][3])
        i += 1
        signed_attrs_der = None
        signed_attrs_span = None
        if si_kids[i][0] == 0xA0:
            sa = si_kids[i]
            signed_attrs_der = b"\x31" + token_der[sa[1] + 1 : sa[3]]
            signed_attrs_span = (sa[2], sa[3])
            i += 1
        sig_alg = _children(token_der, si_kids[i][2], si_kids[i][3])
        sig_alg_oid = _oid_str(token_der, sig_alg[0][2], sig_alg[0][3])
        i += 1
        signature = token_der[si_kids[i][2] : si_kids[i][3]]

        attrs = {}
        if signed_attrs_span is not None:
            for a in _children(token_der, *signed_attrs_span):
                ak = _children(token_der, a[2], a[3])
                a_oid = _oid_str(token_der, ak[0][2], ak[0][3])
                vset = _children(token_der, ak[1][2], ak[1][3])[0]
                attrs[a_oid] = (vset[2], vset[3])
    except Rfc3161Malformed:
        raise
    except (IndexError, StopIteration, ValueError) as exc:
        raise Rfc3161Malformed(f"malformed TimeStampToken: {exc!r}") from exc

    if signed_attrs_der is None:
        raise Rfc3161Malformed("TimeStampToken has no signed attributes")

    return {
        "tstinfo": tstinfo,
        "certs": certs,
        "digest_oid": digest_oid,
        "signed_attrs_der": signed_attrs_der,
        "sig_alg_oid": sig_alg_oid,
        "signature": signature,
        "attrs": attrs,
        "buf": token_der,
    }


def _parse_tstinfo(tstinfo: bytes) -> tuple[bytes, str, datetime]:
    try:
        _, _, c, e = _tlv(tstinfo, 0)
        kids = _children(tstinfo, c, e)
        mi = next(k for k in kids if k[0] == 0x30)
        mi_kids = _children(tstinfo, mi[2], mi[3])
        alg_kids = _children(tstinfo, mi_kids[0][2], mi_kids[0][3])
        imprint_alg_oid = _oid_str(tstinfo, alg_kids[0][2], alg_kids[0][3])
        hashed = tstinfo[mi_kids[1][2] : mi_kids[1][3]]
        gt = next(k for k in kids if k[0] == 0x18)
        gen = tstinfo[gt[2] : gt[3]].decode("ascii")
    except (IndexError, StopIteration, ValueError, UnicodeDecodeError) as exc:
        raise Rfc3161Malformed(f"malformed TSTInfo: {exc!r}") from exc
    dt = datetime.strptime(gen.rstrip("Z"), "%Y%m%d%H%M%S").replace(
        tzinfo=timezone.utc
    )
    return hashed, imprint_alg_oid, dt


def verify_rfc3161_timestamp(
    *,
    token_der: bytes,
    timestamped_data: bytes,
    trusted_roots: list[str] | None = None,
) -> Rfc3161VerifyDetail:
    """Verify an RFC 3161 TimeStampToken offline.

    Raises Rfc3161Malformed only when the token is not a structurally valid
    TimeStampToken (a precondition failure). All cryptographic outcomes are
    reported as per-step booleans in the returned detail.
    """
    parsed = _parse_token(token_der)
    roots_pem = KNOWN_TSA_ROOT_CERTS if trusted_roots is None else trusted_roots
    errors: list[str] = []

    signer = None
    for cert_der in parsed["certs"]:
        cert = x509.load_der_x509_certificate(cert_der)
        try:
            eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
        except x509.ExtensionNotFound:
            continue
        if ExtendedKeyUsageOID.TIME_STAMPING in eku.value:
            signer = cert
            break

    signer_subject = signer.subject.rfc4514_string() if signer else None

    signer_chain_ok = False
    if signer is None:
        errors.append("no signer certificate with timeStamping EKU")
    else:
        for root_pem in roots_pem:
            try:
                root = x509.load_pem_x509_certificate(root_pem.encode("ascii"))
                if root.subject != root.issuer:
                    continue
                signer.verify_directly_issued_by(root)
                signer_chain_ok = True
                break
            except Exception:
                continue
        if not signer_chain_ok:
            errors.append("signer does not chain to a pinned self-signed root")

    signer_sig_ok = False
    if signer is not None:
        hash_cls = _ECDSA_SIG_OIDS.get(parsed["sig_alg_oid"]) or _RSA_SIG_OIDS.get(
            parsed["sig_alg_oid"]
        )
        if hash_cls is None:
            errors.append(f"unsupported signature algorithm {parsed['sig_alg_oid']}")
        else:
            try:
                pub = signer.public_key()
                if isinstance(pub, ec.EllipticCurvePublicKey):
                    pub.verify(
                        parsed["signature"],
                        parsed["signed_attrs_der"],
                        ECDSA(hash_cls()),
                    )
                else:
                    pub.verify(
                        parsed["signature"],
                        parsed["signed_attrs_der"],
                        padding.PKCS1v15(),
                        hash_cls(),
                    )
                signer_sig_ok = True
            except Exception as exc:
                errors.append(f"signer signature verification failed: {exc!r}")

    content_type_ok = False
    ct_span = parsed["attrs"].get(OID_ATTR_CONTENT_TYPE)
    if ct_span is None:
        errors.append("missing content-type signed attribute")
    else:
        content_type_ok = (
            _oid_str(parsed["buf"], ct_span[0], ct_span[1]) == OID_CT_TSTINFO
        )
        if not content_type_ok:
            errors.append("content-type signed attribute is not id-ct-TSTInfo")

    message_digest_ok = False
    md_span = parsed["attrs"].get(OID_ATTR_MESSAGE_DIGEST)
    digest_name = _DIGEST_OIDS.get(parsed["digest_oid"])
    if md_span is None:
        errors.append("missing message-digest signed attribute")
    elif digest_name is None:
        errors.append(f"unsupported digest algorithm {parsed['digest_oid']}")
    else:
        md = parsed["buf"][md_span[0] : md_span[1]]
        message_digest_ok = (
            hashlib.new(digest_name, parsed["tstinfo"]).digest() == md
        )
        if not message_digest_ok:
            errors.append("message-digest attribute does not match eContent")

    hashed, imprint_alg_oid, gen_time = _parse_tstinfo(parsed["tstinfo"])
    imprint_binds_ok = False
    imprint_name = _DIGEST_OIDS.get(imprint_alg_oid)
    if imprint_name is None:
        errors.append(f"unsupported imprint algorithm {imprint_alg_oid}")
    else:
        imprint_binds_ok = (
            hashlib.new(imprint_name, timestamped_data).digest() == hashed
        )
        if not imprint_binds_ok:
            errors.append("messageImprint does not bind the supplied data")

    return Rfc3161VerifyDetail(
        signer_chain_ok=signer_chain_ok,
        signer_sig_ok=signer_sig_ok,
        content_type_ok=content_type_ok,
        message_digest_ok=message_digest_ok,
        imprint_binds_ok=imprint_binds_ok,
        gen_time=gen_time,
        signer_subject=signer_subject,
        errors=tuple(errors),
    )
