_TBRV_OID_SIGNED_DATA = "1.2.840.113549.1.7.2"
_TBRV_OID_CT_TSTINFO = "1.2.840.113549.1.9.16.1.4"
_TBRV_OID_ATTR_CONTENT_TYPE = "1.2.840.113549.1.9.3"
_TBRV_OID_ATTR_MESSAGE_DIGEST = "1.2.840.113549.1.9.4"

_TBRV_KNOWN_TSA_ROOT_CERTS = [
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


class _TbrvMalformed(ValueError):
    pass


def _tbrv_der_len(buf, off):
    b = buf[off]
    if b < 0x80:
        return b, off + 1
    n = b & 0x7F
    if n == 0 or n > 4:
        raise _TbrvMalformed("unsupported DER length form")
    return int.from_bytes(buf[off + 1:off + 1 + n], "big"), off + 1 + n


def _tbrv_tlv(buf, off):
    length, hdr_end = _tbrv_der_len(buf, off + 1)
    end = hdr_end + length
    if end > len(buf):
        raise _TbrvMalformed("DER length exceeds buffer")
    return buf[off], off, hdr_end, end


def _tbrv_children(buf, start, end):
    out = []
    off = start
    while off < end:
        tag, tlv_start, c_off, c_end = _tbrv_tlv(buf, off)
        out.append((tag, tlv_start, c_off, c_end))
        off = c_end
    return out


def _tbrv_oid_str(buf, c_off, c_end):
    data = buf[c_off:c_end]
    if not data:
        raise _TbrvMalformed("empty OID")
    first = data[0]
    parts = [str(first // 40), str(first % 40)]
    val = 0
    for byte in data[1:]:
        val = (val << 7) | (byte & 0x7F)
        if not byte & 0x80:
            parts.append(str(val))
            val = 0
    return ".".join(parts)


def _tbrv_parse_token(token_der):
    try:
        _, _, ci_c, ci_end = _tbrv_tlv(token_der, 0)
        ci_kids = _tbrv_children(token_der, ci_c, ci_end)
        if _tbrv_oid_str(token_der, ci_kids[0][2], ci_kids[0][3]) != \
                _TBRV_OID_SIGNED_DATA:
            raise _TbrvMalformed("token is not a CMS SignedData")
        sd = _tbrv_children(token_der, ci_kids[1][2], ci_kids[1][3])[0]
        sd_kids = _tbrv_children(token_der, sd[2], sd[3])
        enc = next(k for k in sd_kids if k[0] == 0x30)
        enc_kids = _tbrv_children(token_der, enc[2], enc[3])
        if _tbrv_oid_str(token_der, enc_kids[0][2], enc_kids[0][3]) != \
                _TBRV_OID_CT_TSTINFO:
            raise _TbrvMalformed("eContentType is not id-ct-TSTInfo")
        oct0 = _tbrv_children(token_der, enc_kids[1][2], enc_kids[1][3])[0]
        tstinfo = token_der[oct0[2]:oct0[3]]
        certs = []
        for k in sd_kids:
            if k[0] == 0xA0:
                for c in _tbrv_children(token_der, k[2], k[3]):
                    certs.append(token_der[c[1]:c[3]])
                break
        signer_set = [k for k in sd_kids if k[0] == 0x31 and k[1] > enc[3]][0]
        si = _tbrv_children(token_der, signer_set[2], signer_set[3])[0]
        si_kids = _tbrv_children(token_der, si[2], si[3])
        i = 2
        digest_alg = _tbrv_children(token_der, si_kids[i][2], si_kids[i][3])
        digest_oid = _tbrv_oid_str(token_der, digest_alg[0][2], digest_alg[0][3])
        i += 1
        signed_attrs_der = None
        signed_attrs_span = None
        if si_kids[i][0] == 0xA0:
            sa = si_kids[i]
            signed_attrs_der = b"\x31" + token_der[sa[1] + 1:sa[3]]
            signed_attrs_span = (sa[2], sa[3])
            i += 1
        sig_alg = _tbrv_children(token_der, si_kids[i][2], si_kids[i][3])
        sig_alg_oid = _tbrv_oid_str(token_der, sig_alg[0][2], sig_alg[0][3])
        i += 1
        signature = token_der[si_kids[i][2]:si_kids[i][3]]
        attrs = {}
        if signed_attrs_span is not None:
            for a in _tbrv_children(token_der, *signed_attrs_span):
                ak = _tbrv_children(token_der, a[2], a[3])
                a_oid = _tbrv_oid_str(token_der, ak[0][2], ak[0][3])
                vset = _tbrv_children(token_der, ak[1][2], ak[1][3])[0]
                attrs[a_oid] = (vset[2], vset[3])
    except _TbrvMalformed:
        raise
    except (IndexError, StopIteration, ValueError) as exc:
        raise _TbrvMalformed("malformed TimeStampToken: " + repr(exc)) from exc
    if signed_attrs_der is None:
        raise _TbrvMalformed("TimeStampToken has no signed attributes")
    return {
        "tstinfo": tstinfo, "certs": certs, "digest_oid": digest_oid,
        "signed_attrs_der": signed_attrs_der, "sig_alg_oid": sig_alg_oid,
        "signature": signature, "attrs": attrs, "buf": token_der,
    }


def _tbrv_parse_tstinfo(tstinfo):
    import datetime as _dt
    try:
        _, _, c, e = _tbrv_tlv(tstinfo, 0)
        kids = _tbrv_children(tstinfo, c, e)
        mi = next(k for k in kids if k[0] == 0x30)
        mi_kids = _tbrv_children(tstinfo, mi[2], mi[3])
        alg_kids = _tbrv_children(tstinfo, mi_kids[0][2], mi_kids[0][3])
        imprint_alg_oid = _tbrv_oid_str(tstinfo, alg_kids[0][2], alg_kids[0][3])
        hashed = tstinfo[mi_kids[1][2]:mi_kids[1][3]]
        gt = next(k for k in kids if k[0] == 0x18)
        gen = tstinfo[gt[2]:gt[3]].decode("ascii")
    except (IndexError, StopIteration, ValueError, UnicodeDecodeError) as exc:
        raise _TbrvMalformed("malformed TSTInfo: " + repr(exc)) from exc
    dt = _dt.datetime.strptime(gen.rstrip("Z"), "%Y%m%d%H%M%S").replace(
        tzinfo=_dt.timezone.utc
    )
    return hashed, imprint_alg_oid, dt


def _tbrv_verify_rfc3161(token_der, timestamped_data):
    # Faithful port of tsa_verify.verify_rfc3161_timestamp, returning
    # (ok, gen_time, errors). Pinned-root chain, signer sig over the
    # re-encoded SignedAttributes, content-type, message-digest, and the
    # imprint binding to timestamped_data. cryptography + stdlib only.
    import hashlib as _hl
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes as _h
    from cryptography.hazmat.primitives.asymmetric import ec as _ec
    from cryptography.hazmat.primitives.asymmetric import padding as _pad
    from cryptography.hazmat.primitives.asymmetric.ec import ECDSA as _ECDSA
    from cryptography.x509.oid import ExtendedKeyUsageOID as _EKU

    ecdsa_oids = {
        "1.2.840.10045.4.3.2": _h.SHA256,
        "1.2.840.10045.4.3.3": _h.SHA384,
        "1.2.840.10045.4.3.4": _h.SHA512,
    }
    rsa_oids = {
        "1.2.840.113549.1.1.11": _h.SHA256,
        "1.2.840.113549.1.1.12": _h.SHA384,
        "1.2.840.113549.1.1.13": _h.SHA512,
    }
    digest_oids = {
        "2.16.840.1.101.3.4.2.1": "sha256",
        "2.16.840.1.101.3.4.2.2": "sha384",
        "2.16.840.1.101.3.4.2.3": "sha512",
    }
    parsed = _tbrv_parse_token(token_der)
    errors = []

    signer = None
    for cert_der in parsed["certs"]:
        cert = x509.load_der_x509_certificate(cert_der)
        try:
            eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
        except x509.ExtensionNotFound:
            continue
        if _EKU.TIME_STAMPING in eku.value:
            signer = cert
            break

    signer_chain_ok = False
    if signer is None:
        errors.append("no signer certificate with timeStamping EKU")
    else:
        for root_pem in _TBRV_KNOWN_TSA_ROOT_CERTS:
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
        hash_cls = ecdsa_oids.get(parsed["sig_alg_oid"]) or rsa_oids.get(
            parsed["sig_alg_oid"]
        )
        if hash_cls is None:
            errors.append("unsupported signature algorithm "
                          + parsed["sig_alg_oid"])
        else:
            try:
                pub = signer.public_key()
                if isinstance(pub, _ec.EllipticCurvePublicKey):
                    pub.verify(parsed["signature"], parsed["signed_attrs_der"],
                               _ECDSA(hash_cls()))
                else:
                    pub.verify(parsed["signature"], parsed["signed_attrs_der"],
                               _pad.PKCS1v15(), hash_cls())
                signer_sig_ok = True
            except Exception as exc:
                errors.append("signer signature verification failed: "
                              + repr(exc))

    content_type_ok = False
    ct_span = parsed["attrs"].get(_TBRV_OID_ATTR_CONTENT_TYPE)
    if ct_span is None:
        errors.append("missing content-type signed attribute")
    else:
        content_type_ok = (
            _tbrv_oid_str(parsed["buf"], ct_span[0], ct_span[1])
            == _TBRV_OID_CT_TSTINFO
        )
        if not content_type_ok:
            errors.append("content-type signed attribute is not id-ct-TSTInfo")

    message_digest_ok = False
    md_span = parsed["attrs"].get(_TBRV_OID_ATTR_MESSAGE_DIGEST)
    digest_name = digest_oids.get(parsed["digest_oid"])
    if md_span is None:
        errors.append("missing message-digest signed attribute")
    elif digest_name is None:
        errors.append("unsupported digest algorithm " + parsed["digest_oid"])
    else:
        md = parsed["buf"][md_span[0]:md_span[1]]
        message_digest_ok = (
            _hl.new(digest_name, parsed["tstinfo"]).digest() == md
        )
        if not message_digest_ok:
            errors.append("message-digest attribute does not match eContent")

    hashed, imprint_alg_oid, gen_time = _tbrv_parse_tstinfo(parsed["tstinfo"])
    imprint_binds_ok = False
    imprint_name = digest_oids.get(imprint_alg_oid)
    if imprint_name is None:
        errors.append("unsupported imprint algorithm " + imprint_alg_oid)
    else:
        imprint_binds_ok = (
            _hl.new(imprint_name, timestamped_data).digest() == hashed
        )
        if not imprint_binds_ok:
            errors.append("messageImprint does not bind the supplied data")

    ok = (signer_chain_ok and signer_sig_ok and content_type_ok
          and message_digest_ok and imprint_binds_ok)
    return ok, gen_time, errors


def _tbrv_resolve_tsa_roots(pack, man):
    # Auditor pins win; pack-carried roots verify but downgrade the report.
    import os as _os
    import re as _re
    path = _os.environ.get("NOUS_TSA_ROOTS")
    if not path:
        cand = _os.path.join(pack, "tsa_roots.pem")
        path = cand if _os.path.isfile(cand) else None
    if path and _os.path.isfile(path):
        with open(path, "r", encoding="ascii") as f:
            blob = f.read()
        roots = [m.group(0) for m in _re.finditer(
            r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----\n?",
            blob, _re.S)]
        if roots:
            return roots, "auditor-pinned"
    carried = (man.get("trust_anchors") or {}).get("tsa_roots")
    if isinstance(carried, list) and carried:
        return list(carried), "operator-supplied"
    return [], "none"


# --- SPEC 10.1 production anchor backend: Rekor v2 -------------------------
# Spliced VERBATIM from the tracked source rekor_check.py. Do NOT edit the
# copy below: edit rekor_check.py and re-splice. This fragment ships inside
# every emitted verify_offline.py, so it cannot import the source and must
# travel as bytes.
# __rk_tb_splice_begin_v1__
_RK_SIG_PREFIX = "\u2014 "
_RK_LEAF_PREFIX = b"\x00"
_RK_NODE_PREFIX = b"\x01"
_RK_ED25519_SIG_TYPE = b"\x01"
_RK_SHA256_LEN = 32

_RK_KNOWN_LOG_KEYS = {
    "log2025-1.rekor.sigstore.dev":
        "t8rlp1knGwjfbcXAYPYAkn0XiLz1x8O4t0YkEhie244=",
}


class _RkMalformed(ValueError):
    pass


class _RkInclusionError(ValueError):
    pass


def _rk_b64(value, what):
    import base64 as _b64
    import binascii as _bx
    if not isinstance(value, str):
        raise _RkMalformed(what + " is not a string")
    try:
        return _b64.b64decode(value, validate=True)
    except (_bx.Error, ValueError) as exc:
        raise _RkMalformed(what + " is not valid base64: " + str(exc))


def _rk_parse_checkpoint(envelope):
    if not isinstance(envelope, str):
        raise _RkMalformed("checkpoint envelope is not a string")
    if "\r" in envelope:
        raise _RkMalformed(
            "checkpoint envelope contains CR; LF line endings only")
    lines = envelope.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    cut = len(lines)
    while cut > 0 and lines[cut - 1].startswith(_RK_SIG_PREFIX):
        cut -= 1
    sig_lines = lines[cut:]
    if not sig_lines:
        raise _RkMalformed("checkpoint has no signature lines")
    if cut == 0 or lines[cut - 1] != "":
        raise _RkMalformed(
            "checkpoint signature block is not preceded by the blank "
            "separator line")
    body_lines = lines[:cut - 1]
    if len(body_lines) < 3:
        raise _RkMalformed(
            "checkpoint body has fewer than 3 mandatory lines "
            "(origin, tree size, root hash)")
    note_text_bytes = "".join(ln + "\n" for ln in body_lines).encode("utf-8")
    origin = body_lines[0]
    if not origin:
        raise _RkMalformed("checkpoint origin line is empty")
    size_str = body_lines[1]
    if not size_str.isascii() or not size_str.isdigit():
        raise _RkMalformed("checkpoint tree size is not ASCII decimal")
    tree_size = int(size_str)
    if str(tree_size) != size_str:
        raise _RkMalformed(
            "checkpoint tree size is not canonical (leading zeros)")
    root_hash = _rk_b64(body_lines[2], "checkpoint root hash")
    if len(root_hash) != _RK_SHA256_LEN:
        raise _RkMalformed("checkpoint root hash is not 32 bytes")
    signatures = []
    for raw_line in sig_lines:
        rest = raw_line[len(_RK_SIG_PREFIX):]
        parts = rest.split(" ", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise _RkMalformed("checkpoint signature line is malformed")
        decoded = _rk_b64(parts[1], "checkpoint signature")
        if len(decoded) < 4:
            raise _RkMalformed(
                "checkpoint signature decodes to fewer than 4 bytes "
                "(no key ID)")
        signatures.append((parts[0], decoded[:4], decoded[4:]))
    return {"origin": origin, "tree_size": tree_size,
            "root_hash": root_hash, "note_text_bytes": note_text_bytes,
            "signatures": signatures}


def _rk_ed25519_key_id(key_name, raw_pub):
    import hashlib as _hl
    return _hl.sha256(key_name.encode("utf-8") + b"\x0a"
                      + _RK_ED25519_SIG_TYPE + raw_pub).digest()[:4]


def _rk_verify_checkpoint_sig(cp, key_name, raw_pub):
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey)
    try:
        pub = Ed25519PublicKey.from_public_bytes(raw_pub)
    except Exception as exc:
        return False, "trusted log key is not a valid Ed25519 key: " + str(exc)
    expected = _rk_ed25519_key_id(key_name, raw_pub)
    matched = [s for s in cp["signatures"]
               if s[0] == key_name and s[1] == expected]
    if not matched:
        return False, ("no checkpoint signature line matches the trusted log "
                       "key name and key ID")
    for s in matched:
        try:
            pub.verify(s[2], cp["note_text_bytes"])
            return True, None
        except InvalidSignature:
            continue
    return False, ("checkpoint Ed25519 signature failed to verify over the "
                   "checkpoint note text")


def _rk_leaf_hash(canonicalized_body):
    import hashlib as _hl
    return _hl.sha256(_RK_LEAF_PREFIX + canonicalized_body).digest()


def _rk_verify_inclusion(leaf_hash, log_index, tree_size, proof, root_hash):
    import hashlib as _hl
    if tree_size <= 0:
        raise _RkInclusionError("tree size must be positive")
    if log_index < 0 or log_index >= tree_size:
        raise _RkInclusionError("leaf index out of range for the tree size")
    if len(root_hash) != _RK_SHA256_LEN:
        raise _RkInclusionError("root hash is not 32 bytes")
    fn = log_index
    sn = tree_size - 1
    r = leaf_hash
    for p in proof:
        if len(p) != _RK_SHA256_LEN:
            raise _RkInclusionError("proof node is not 32 bytes")
        if sn == 0:
            raise _RkInclusionError("proof is too long for the tree size")
        if (fn & 1) or (fn == sn):
            r = _hl.sha256(_RK_NODE_PREFIX + p + r).digest()
            if not (fn & 1):
                while fn != 0 and not (fn & 1):
                    fn >>= 1
                    sn >>= 1
        else:
            r = _hl.sha256(_RK_NODE_PREFIX + r + p).digest()
        fn >>= 1
        sn >>= 1
    if sn != 0:
        raise _RkInclusionError("proof is too short for the tree size")
    if r != root_hash:
        raise _RkInclusionError(
            "recomputed Merkle root does not match the checkpoint root hash")


def _rk_parse_leaf(canonicalized_body):
    import binascii as _bx
    import json as _js
    try:
        leaf = _js.loads(canonicalized_body)
    except Exception as exc:
        raise _RkMalformed("leaf body is not JSON: " + str(exc))
    if not isinstance(leaf, dict):
        raise _RkMalformed("leaf body is not an object")
    kind = leaf.get("kind")
    version = leaf.get("apiVersion")
    if kind != "hashedrekord" or version != "0.0.2":
        raise _RkMalformed(
            "unsupported Rekor leaf (kind=" + repr(kind) + ", apiVersion="
            + repr(version) + "); this verifier accepts hashedrekord 0.0.2 "
            "only and fails closed on every other kind or version")
    spec = leaf.get("spec")
    if not isinstance(spec, dict):
        raise _RkMalformed("leaf spec is not an object")
    inner = spec.get("hashedRekordV002")
    if not isinstance(inner, dict):
        raise _RkMalformed("leaf spec.hashedRekordV002 is not an object")
    data = inner.get("data")
    if not isinstance(data, dict):
        raise _RkMalformed("leaf data is not an object")
    if data.get("algorithm") != "SHA2_256":
        raise _RkMalformed(
            "leaf hash algorithm is " + repr(data.get("algorithm"))
            + "; hashedrekord 0.0.2 supports SHA2_256 only")
    digest = _rk_b64(data.get("digest"), "leaf data.digest")
    if len(digest) != _RK_SHA256_LEN:
        raise _RkMalformed("leaf digest is not 32 bytes")
    signature = inner.get("signature")
    if not isinstance(signature, dict):
        raise _RkMalformed("leaf signature is not an object")
    sig_der = _rk_b64(signature.get("content"), "leaf signature.content")
    verifier = signature.get("verifier")
    if not isinstance(verifier, dict):
        raise _RkMalformed("leaf signature.verifier is not an object")
    public_key = verifier.get("publicKey")
    if not isinstance(public_key, dict):
        raise _RkMalformed("leaf verifier.publicKey is not an object")
    pub_der = _rk_b64(public_key.get("rawBytes"),
                      "leaf publicKey.rawBytes")
    return {"digest_hex": _bx.hexlify(digest).decode("ascii"),
            "sig_der": sig_der, "pub_der": pub_der,
            "key_details": verifier.get("keyDetails")}


def _rk_resolve_log_keys(env_path, pack_keys_path, carried):
    """Return (origin -> raw Ed25519 pubkey bytes, provenance).

    Auditor pins (NOUS_REKOR_LOG_KEYS or <pack>/rekor_log_keys.json) win and
    are used ALONE. Otherwise the verifier's own built-in pin is the base;
    keys carried inside the pack are operator-supplied and downgrade the
    report. A carried key that contradicts a built-in pin for the same origin
    fails closed -- it is a substitution attempt, not a supplement.
    """
    import json as _js
    import os as _os

    def _decode(mapping, what):
        out = {}
        if not isinstance(mapping, dict):
            raise _RkMalformed(what + " is not an object")
        for origin, b64 in mapping.items():
            if not isinstance(origin, str) or not origin:
                raise _RkMalformed(what + " has a non-string origin")
            out[origin] = _rk_b64(b64, what + "[" + origin + "]")
        return out

    path = env_path
    if not path and pack_keys_path and _os.path.isfile(pack_keys_path):
        path = pack_keys_path
    if path and _os.path.isfile(path):
        with open(path, "r", encoding="ascii") as handle:
            return _decode(_js.load(handle), "auditor-pinned log keys"), \
                "auditor-pinned"

    builtin = _decode(_RK_KNOWN_LOG_KEYS, "built-in log keys")
    if not isinstance(carried, dict) or not carried:
        return builtin, "verifier-pinned"
    supplied = _decode(carried, "pack-carried log keys")
    for origin, raw in supplied.items():
        if origin in builtin and builtin[origin] != raw:
            raise _RkMalformed(
                "pack-carried log key for origin " + repr(origin)
                + " contradicts the verifier's built-in pin; refusing to "
                "let a pack redefine a pinned log identity")
    merged = dict(builtin)
    merged.update(supplied)
    return merged, "operator-supplied"


def _rk_verify_anchor(block, signed_bytes, log_keys, rfc3161_verify=None):
    """Verify a NOUS-TRACE `rekor` anchor block offline.

    signed_bytes is the checkpoint Merkle root the leaf must commit to.
    rfc3161_verify, when supplied, is the host file's already-shipped RFC
    3161 verifier -- (token_der, timestamped_data) -> (ok, gen_time, errors).
    This leg does NOT carry its own copy of that code.

    Returns a detail dict. The four inclusion booleans are evaluated
    independently with no early exit. `state` is the DISCRIMINATOR:

      INCLUDED-TIMED   inclusion verified AND an RFC 3161 token over the leaf
                       signature verified -- transparency plus trusted time.
      INCLUDED-UNTIMED inclusion verified, NO trusted time present. Rekor v2
                       has no per-entry integrated time, so a block without
                       the token evidences membership only.
      None             inclusion did not verify.

    A Verifier can only report that no trusted time is PRESENT. It cannot
    distinguish a TSA outage from a Producer that skipped the TSA, so it
    never asserts a cause.
    """
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes as _h
    from cryptography.hazmat.primitives.asymmetric import ec as _ec
    from cryptography.hazmat.primitives.asymmetric.ec import ECDSA as _ECDSA
    from cryptography.hazmat.primitives.serialization import (
        load_der_public_key)
    import hashlib as _hl

    if not isinstance(block, dict):
        raise _RkMalformed("anchor block is not an object")
    if block.get("rekor_api_version") != 2:
        raise _RkMalformed(
            "anchor rekor_api_version is " + repr(block.get(
                "rekor_api_version")) + "; expected 2")

    errors = []
    detail = {"state": None, "leaf_digest_ok": False, "leaf_sig_ok": False,
              "checkpoint_sig_ok": False, "inclusion_ok": False,
              "timestamp_ok": False, "gen_time": None, "log_index": None,
              "origin": None, "tree_size": None, "errors": errors}

    log_index = block.get("log_index")
    if not isinstance(log_index, int) or isinstance(log_index, bool):
        raise _RkMalformed("anchor log_index is not an integer")
    detail["log_index"] = log_index

    body = _rk_b64(block.get("body_b64"), "anchor body_b64")
    leaf = _rk_parse_leaf(body)

    expected = _hl.sha256(signed_bytes).hexdigest()
    if leaf["digest_hex"] == expected:
        detail["leaf_digest_ok"] = True
    else:
        errors.append(
            "leaf digest does not match sha256(checkpoint merkle root)")

    try:
        pub = load_der_public_key(leaf["pub_der"])
        if not isinstance(pub, _ec.EllipticCurvePublicKey):
            errors.append("leaf public key is not an EC key")
        elif not isinstance(pub.curve, _ec.SECP256R1):
            errors.append("leaf public key curve is not P-256")
        else:
            pub.verify(leaf["sig_der"], signed_bytes, _ECDSA(_h.SHA256()))
            detail["leaf_sig_ok"] = True
    except InvalidSignature:
        errors.append(
            "leaf ECDSA signature does not verify over the merkle root")
    except Exception as exc:
        errors.append("leaf signature verification error: " + str(exc))

    cp = _rk_parse_checkpoint(block.get("checkpoint_envelope"))
    detail["origin"] = cp["origin"]
    detail["tree_size"] = cp["tree_size"]

    raw_pub = log_keys.get(cp["origin"]) if isinstance(log_keys, dict) else None
    if raw_pub is None:
        errors.append(
            "checkpoint origin " + repr(cp["origin"]) + " is not in the "
            "trusted log key allowlist")
    else:
        ok, why = _rk_verify_checkpoint_sig(cp, cp["origin"], raw_pub)
        detail["checkpoint_sig_ok"] = ok
        if not ok:
            errors.append(why)

    hashes_field = block.get("inclusion_proof_hashes")
    if not isinstance(hashes_field, list):
        raise _RkMalformed("anchor inclusion_proof_hashes is not a list")
    try:
        proof = [_rk_b64(h, "inclusion proof node") for h in hashes_field]
        _rk_verify_inclusion(_rk_leaf_hash(body), log_index,
                             cp["tree_size"], proof, cp["root_hash"])
        detail["inclusion_ok"] = True
    except _RkInclusionError as exc:
        errors.append("inclusion proof: " + str(exc))

    token_b64 = block.get("rfc3161_token_b64")
    if token_b64 is not None:
        if rfc3161_verify is None:
            errors.append(
                "anchor carries an RFC 3161 token but no verifier was "
                "supplied to this leg")
        else:
            token_der = _rk_b64(token_b64, "anchor rfc3161_token_b64")
            ok, gen_time, errs = rfc3161_verify(token_der, leaf["sig_der"])
            detail["timestamp_ok"] = bool(ok)
            if ok:
                detail["gen_time"] = gen_time
            else:
                errors.extend("timestamp: " + e for e in errs)

    included = (detail["leaf_digest_ok"] and detail["leaf_sig_ok"]
                and detail["checkpoint_sig_ok"] and detail["inclusion_ok"])
    if included and detail["timestamp_ok"]:
        detail["state"] = "INCLUDED-TIMED"
    elif included and token_b64 is None:
        detail["state"] = "INCLUDED-UNTIMED"
    return detail
# __rk_tb_splice_end_v1__


_TB_SPEC = "0.2.0"
_TB_TAG_EVENT = b"NOUS-TRACE/v0.2/event"
_TB_TAG_CKPT = b"NOUS-TRACE/v0.2/checkpoint-root"
_TB_TAG_OBL = b"NOUS-TRACE/v0.2/obligation-manifest"
_TB_TAG_KEYS = b"NOUS-TRACE/v0.2/keys-manifest"
_TB_TAG_ANCH = b"NOUS-TRACE/v0.2/anchor-sim"
_TB_MAX_INT = 2 ** 53 - 1


class _TbVErr(Exception):
    def __init__(self, reason, seq=None, detail=""):
        self.reason = reason
        self.seq = seq
        self.detail = detail
        super().__init__(reason)


class _TbFloatFound(Exception):
    pass


def _tb_reject_float(_s):
    raise _TbFloatFound()


def _tb_jloads(s):
    import json as _json
    return _json.loads(s, parse_float=_tb_reject_float)


def _tb_jcs_str(s):
    out = ['"']
    for ch in s:
        c = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == '\\':
            out.append('\\\\')
        elif ch == '\b':
            out.append('\\b')
        elif ch == '\t':
            out.append('\\t')
        elif ch == '\n':
            out.append('\\n')
        elif ch == '\f':
            out.append('\\f')
        elif ch == '\r':
            out.append('\\r')
        elif c < 0x20:
            out.append('\\u%04x' % c)
        else:
            out.append(ch)
    out.append('"')
    return ''.join(out)


def _tb_jcs(obj):
    if obj is None:
        return 'null'
    if obj is True:
        return 'true'
    if obj is False:
        return 'false'
    if isinstance(obj, int):
        if abs(obj) > _TB_MAX_INT:
            raise _TbVErr("INT_RANGE", detail=str(obj))
        return str(obj)
    if isinstance(obj, float):
        raise _TbVErr("FLOAT_IN_SIGNED")
    if isinstance(obj, str):
        return _tb_jcs_str(obj)
    if isinstance(obj, list):
        return '[' + ','.join(_tb_jcs(x) for x in obj) + ']'
    if isinstance(obj, dict):
        keys = sorted(obj.keys(), key=lambda k: k.encode('utf-16-be'))
        return '{' + ','.join(
            _tb_jcs_str(k) + ':' + _tb_jcs(obj[k]) for k in keys) + '}'
    raise _TbVErr("JCS_TYPE", detail=type(obj).__name__)


def _tb_sha256(b):
    import hashlib as _hl
    return _hl.sha256(b).digest()


def _tb_jcs_hash(obj):
    return _tb_sha256(_tb_jcs(obj).encode('utf-8'))


def _tb_key_id_of(pub_raw):
    return _tb_sha256(pub_raw)[:8].hex()


def _tb_verify_sig(pub_raw, tag, obj_hash, sig_hex):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )
    from cryptography.exceptions import InvalidSignature
    try:
        Ed25519PublicKey.from_public_bytes(pub_raw).verify(
            bytes.fromhex(sig_hex), tag + b"\x00" + obj_hash)
        return True
    except (InvalidSignature, ValueError):
        return False


def _tb_merkle_root(leaves):
    if not leaves:
        return _tb_sha256(b'')
    if len(leaves) == 1:
        return _tb_sha256(b'\x00' + leaves[0])
    k = 1
    while k * 2 < len(leaves):
        k *= 2
    return _tb_sha256(
        b'\x01' + _tb_merkle_root(leaves[:k]) + _tb_merkle_root(leaves[k:]))


def _tb_parse_ts(s):
    import datetime as _dt
    return _dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=_dt.timezone.utc)


class _TbEvalError(Exception):
    pass


def _tb_ev(node, env):
    if not isinstance(node, dict):
        raise _TbEvalError()
    if "var" in node:
        if node["var"] not in env:
            raise _TbEvalError()
        return env[node["var"]]
    if "int" in node:
        if type(node["int"]) is not int:
            raise _TbEvalError()
        return node["int"]
    if "str" in node:
        if type(node["str"]) is not str:
            raise _TbEvalError()
        return node["str"]
    if "bool" in node:
        if type(node["bool"]) is not bool:
            raise _TbEvalError()
        return node["bool"]
    if "set" in node:
        if not isinstance(node["set"], list) or not all(
                type(x) is str for x in node["set"]):
            raise _TbEvalError()
        return frozenset(node["set"])
    op = node.get("op")
    if op == "and":
        return all(_tb_eb(_tb_ev(a, env)) for a in node["args"])
    if op == "or":
        return any(_tb_eb(_tb_ev(a, env)) for a in node["args"])
    if op == "not":
        return not _tb_eb(_tb_ev(node["arg"], env))
    if op in ("+", "-", "*"):
        l, r = _tb_ei(_tb_ev(node["left"], env)), _tb_ei(_tb_ev(node["right"], env))
        return l + r if op == "+" else l - r if op == "-" else l * r
    if op in ("=", "!="):
        l, r = _tb_ev(node["left"], env), _tb_ev(node["right"], env)
        if type(l) is not type(r) or isinstance(l, frozenset):
            raise _TbEvalError()
        return (l == r) if op == "=" else (l != r)
    if op in ("<", "<=", ">", ">="):
        l, r = _tb_ei(_tb_ev(node["left"], env)), _tb_ei(_tb_ev(node["right"], env))
        return {"<": l < r, "<=": l <= r, ">": l > r, ">=": l >= r}[op]
    if op == "prefix_of":
        l, r = _tb_es(_tb_ev(node["left"], env)), _tb_es(_tb_ev(node["right"], env))
        return r.startswith(l)
    if op == "in":
        l = _tb_es(_tb_ev(node["left"], env))
        r = _tb_ev(node["right"], env)
        if not isinstance(r, frozenset):
            raise _TbEvalError()
        return l in r
    raise _TbEvalError()


def _tb_eb(v):
    if type(v) is not bool:
        raise _TbEvalError()
    return v


def _tb_ei(v):
    if type(v) is not int or type(v) is bool:
        raise _TbEvalError()
    return v


def _tb_es(v):
    if type(v) is not str:
        raise _TbEvalError()
    return v


def _tb_evaluate(pred, env):
    try:
        return "pass" if _tb_eb(_tb_ev(pred, env)) else "fail"
    except _TbEvalError:
        return "error"


def _tb_load_payload(pack, cls, h):
    import os as _os
    import base64 as _b64
    p = _os.path.join(pack, "payloads", cls, h)
    if not _os.path.exists(p):
        return None
    with open(p) as f:
        entry = _tb_jloads(f.read())
    salt = bytes.fromhex(entry["salt"])
    data = _b64.b64decode(entry["data"])
    if _tb_sha256(salt + data).hex() != h:
        raise _TbVErr("PAYLOAD_HASH_MISMATCH", detail=h)
    return salt, data


def _tb_verify_pack(pack):
    import os as _os
    report = {"flags": [], "erased": [], "policy_checks": [], "anchors": []}

    with open(_os.path.join(pack, "manifest.json")) as f:
        man = _tb_jloads(f.read())
    if man["spec_version"] != _TB_SPEC:
        raise _TbVErr("SPEC_VERSION", detail=man["spec_version"])
    dep_pub = bytes.fromhex(man["trust_anchors"]["deployment_pub"])
    anch_pub = bytes.fromhex(man["trust_anchors"]["anchor_pub"])
    tol = man["tolerance_s"]
    if not isinstance(tol, int) or tol > 3600:
        raise _TbVErr("TOLERANCE_INVALID")

    for fn in ("keys.json", "obligations.json"):
        with open(_os.path.join(pack, fn), 'rb') as f:
            if _tb_sha256(f.read()).hex() != man["hashes"][fn]:
                raise _TbVErr("MANIFEST_FILE_HASH", detail=fn)

    with open(_os.path.join(pack, "keys.json")) as f:
        keysdoc = _tb_jloads(f.read())
    keys_core = {"keys": keysdoc["keys"]}
    keys_hash = _tb_jcs_hash(keys_core)
    if not _tb_verify_sig(dep_pub, _TB_TAG_KEYS, keys_hash, keysdoc["sig"]):
        raise _TbVErr("KEYS_MANIFEST_SIG")
    keys = {}
    for k in keysdoc["keys"]:
        raw = bytes.fromhex(k["public_key"])
        if _tb_key_id_of(raw) != k["key_id"]:
            raise _TbVErr("KEY_ID_MISMATCH", detail=k["key_id"])
        keys[k["key_id"]] = {"raw": raw, "role": k["role"],
                             "nb": _tb_parse_ts(k["not_before"]),
                             "na": _tb_parse_ts(k["not_after"])}

    with open(_os.path.join(pack, "obligations.json")) as f:
        obldoc = _tb_jloads(f.read())
    obl_core = {"obligations": obldoc["obligations"]}
    obl_hash = _tb_jcs_hash(obl_core)
    if not _tb_verify_sig(dep_pub, _TB_TAG_OBL, obl_hash, obldoc["sig"]):
        raise _TbVErr("OBLIGATION_MANIFEST_SIG")
    obligations = {}
    for o in obldoc["obligations"]:
        if _tb_jcs_hash(o["predicate"]).hex() != o["obligation_id"]:
            raise _TbVErr("OBLIGATION_ID_MISMATCH", detail=o["label"])
        if o["assurance"] == "proved":
            pf = _os.path.join(pack, "proofs", o["proof_artifact_hash"])
            if not _os.path.exists(pf):
                raise _TbVErr("PROOF_ARTIFACT_MISSING", detail=o["label"])
            with open(pf, 'rb') as f:
                if _tb_sha256(f.read()).hex() != o["proof_artifact_hash"]:
                    raise _TbVErr("PROOF_ARTIFACT_HASH", detail=o["label"])
        elif o["assurance"] != "declared":
            raise _TbVErr("ASSURANCE_INVALID", detail=o["label"])
        obligations[o["obligation_id"]] = o

    events = []
    with open(_os.path.join(pack, "trace.ndjson")) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                e = _tb_jloads(line)
            except _TbFloatFound:
                raise _TbVErr("FLOAT_IN_SIGNED", seq=i)
            events.append(e)
    if not events:
        raise _TbVErr("EMPTY_TRACE")

    trace_id = events[0]["trace_id"]
    prev = "0" * 64
    ehashes = []
    for i, e in enumerate(events):
        if e.get("spec_version") != _TB_SPEC:
            raise _TbVErr("SPEC_VERSION", seq=i)
        if e.get("trace_id") != trace_id:
            raise _TbVErr("TRACE_ID_MIXED", seq=i)
        if e.get("seq") != i:
            raise _TbVErr("SEQ_ORDER", seq=i)
        if e.get("prev_hash") != prev:
            raise _TbVErr("HASH_CHAIN_BREAK", seq=i)
        core = {k: v for k, v in e.items() if k != "sig"}
        try:
            eh = _tb_jcs_hash(core)
        except _TbVErr as ve:
            ve.seq = i
            raise
        kid = e.get("key_id")
        if kid not in keys or keys[kid]["role"] != "runtime":
            raise _TbVErr("KEY_UNKNOWN", seq=i, detail=str(kid))
        if not _tb_verify_sig(keys[kid]["raw"], _TB_TAG_EVENT, eh, e["sig"]):
            raise _TbVErr("SIG_INVALID", seq=i)
        ehashes.append(eh)
        prev = eh.hex()

    if events[0]["event_type"] != "run_start":
        raise _TbVErr("STRUCT_NO_RUN_START", seq=0)
    rs = events[0]["body"]
    if rs["keys_manifest_hash"] != keys_hash.hex():
        raise _TbVErr("RUN_START_KEYS_HASH", seq=0)
    if rs["obligation_manifest_hash"] != obl_hash.hex():
        raise _TbVErr("RUN_START_OBL_HASH", seq=0)
    if rs["tolerance_s"] != tol:
        raise _TbVErr("RUN_START_TOLERANCE", seq=0)

    # __p5a_declared_v1__ SPEC 10.1 declares the anchoring policy in BOTH
    # run_start and the pack manifest. run_start is signed by the runtime
    # key, hash-chained, and covered by the first checkpoint Merkle root;
    # manifest.json carries no signature and is not listed in
    # manifest["hashes"], so it is ADVISORY ONLY and never authoritative.
    # Two declarations of the same intent that disagree leave the intent
    # undeterminable: the pack is malformed and the Verifier fails closed,
    # exactly as tolerance_s does above. An absent field on either side is
    # not a disagreement (packs predating the check keep verifying).
    declared_anchoring = rs.get("anchoring")
    if (declared_anchoring is not None
            and man.get("anchoring") is not None
            and man.get("anchoring") != declared_anchoring):
        raise _TbVErr("RUN_START_ANCHORING", seq=0)
    anchoring_shortfall = False

    ckpts = [e for e in events if e["event_type"] == "checkpoint"]
    expected_from = 0
    anchored = []
    for c in ckpts:
        b = c["body"]
        fr, to = b["range"]["from_seq"], b["range"]["to_seq"]
        if fr != expected_from or to != c["seq"] - 1:
            raise _TbVErr("CKPT_RANGE", seq=c["seq"])
        expected_from = c["seq"]
        root = _tb_merkle_root(ehashes[fr:to + 1])
        if root.hex() != b["merkle_root"]:
            raise _TbVErr("MERKLE_MISMATCH", seq=c["seq"])
        kid = c["key_id"]
        if not _tb_verify_sig(keys[kid]["raw"], _TB_TAG_CKPT, root, b["root_sig"]):
            raise _TbVErr("CKPT_ROOT_SIG", seq=c["seq"])
        a = b.get("anchor")
        if a is None:
            report["flags"].append("unanchored checkpoint seq=%d" % c["seq"])
            continue
        atype = a.get("type")
        # __p5a_delivered_v1__ Declared-vs-delivered. The signed run_start
        # value is authoritative. A checkpoint whose anchor type differs
        # from the declared policy carries GENUINE, VERIFYING evidence that
        # is nonetheless less than what this Producer committed to under its
        # own key. That is neither an integrity failure (rc 20) nor a clean
        # record (rc 0): it is an adverse-but-truthful shortfall. The
        # Verifier reports the divergence and asserts no cause for it --
        # it cannot distinguish a degraded backend from a Producer that
        # never attempted the declared one.
        if declared_anchoring is not None and atype != declared_anchoring:
            anchoring_shortfall = True
            report["flags"].append(
                "checkpoint seq=%d carries a %s anchor but the signed "
                "run_start declares the anchoring policy %s; the anchor "
                "verifies, but this run delivered less than it committed "
                "to. The Verifier reports the divergence and asserts no "
                "cause for it." % (c["seq"], repr(atype),
                                   repr(declared_anchoring)))
        if atype == "rfc3161-sim":
            tok_hash = _tb_sha256(root + a["gen_time"].encode())
            if not _tb_verify_sig(anch_pub, _TB_TAG_ANCH, tok_hash, a["token"]):
                raise _TbVErr("ANCHOR_INVALID", seq=c["seq"])
            T = _tb_parse_ts(a["gen_time"])
            if not man.get("test_vector", False):
                report["flags"].append(
                    "checkpoint seq=%d uses the rfc3161-sim TEST backend but "
                    "the pack is not marked test_vector; it evidences no "
                    "trusted time to an external auditor (SPEC 10.1)"
                    % c["seq"])
            report["anchors"].append({"seq": c["seq"], "type": atype,
                                      "gen_time": a["gen_time"]})
        elif atype == "rfc3161":
            import base64 as _b64
            roots, provenance = _tbrv_resolve_tsa_roots(pack, man)
            report.setdefault("tsa_root_provenance", provenance)
            if not roots:
                raise _TbVErr("ANCHOR_INVALID", seq=c["seq"],
                              detail="no pinned TSA roots available")
            tok_b64 = a.get("token_b64")
            if not isinstance(tok_b64, str) or not tok_b64:
                raise _TbVErr("ANCHOR_INVALID", seq=c["seq"],
                              detail="rfc3161 anchor carries no token_b64")
            try:
                token_der = _b64.b64decode(tok_b64, validate=True)
            except Exception as e:
                raise _TbVErr("ANCHOR_INVALID", seq=c["seq"],
                              detail="token_b64 decode: " + str(e))
            saved = globals()["_TBRV_KNOWN_TSA_ROOT_CERTS"]
            try:
                globals()["_TBRV_KNOWN_TSA_ROOT_CERTS"] = roots
                ok_a, T, errs_a = _tbrv_verify_rfc3161(token_der, root)
            except _TbrvMalformed as e:
                raise _TbVErr("ANCHOR_INVALID", seq=c["seq"],
                              detail="malformed token: " + str(e))
            finally:
                globals()["_TBRV_KNOWN_TSA_ROOT_CERTS"] = saved
            if not ok_a:
                raise _TbVErr("ANCHOR_INVALID", seq=c["seq"],
                              detail="; ".join(errs_a))
            if provenance == "operator-supplied":
                report["flags"].append(
                    "checkpoint seq=%d: the RFC 3161 token verifies, but the "
                    "TSA trust root is OPERATOR-SUPPLIED (carried in the "
                    "pack); supply auditor pins via NOUS_TSA_ROOTS or "
                    "tsa_roots.pem" % c["seq"])
            report["anchors"].append(
                {"seq": c["seq"], "type": atype,
                 "gen_time": T.strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "tsa_root_provenance": provenance})
        elif atype == "rekor":
            # __rk_tb_dispatch_v1__ SPEC 10.1 transparency-log backend. Rekor
            # v2 carries no per-entry integrated time and no SET, so trusted
            # time can only come from an RFC 3161 token over the leaf
            # signature. Inclusion WITH time and inclusion WITHOUT it are
            # different claim classes and are reported as different states.
            # NEVER bind `keys` here: it is the keys manifest and the time
            # bound below depends on it.
            log_keys, log_prov = _rk_resolve_log_keys(
                _os.environ.get("NOUS_REKOR_LOG_KEYS"),
                _os.path.join(pack, "rekor_log_keys.json"),
                (man.get("trust_anchors") or {}).get("rekor_log_keys"))
            report.setdefault("rekor_log_key_provenance", log_prov)
            roots, tsa_prov = _tbrv_resolve_tsa_roots(pack, man)
            if a.get("rfc3161_token_b64") is not None:
                report.setdefault("tsa_root_provenance", tsa_prov)
            saved = globals()["_TBRV_KNOWN_TSA_ROOT_CERTS"]
            try:
                if roots:
                    globals()["_TBRV_KNOWN_TSA_ROOT_CERTS"] = roots
                detail = _rk_verify_anchor(a, root, log_keys,
                                           _tbrv_verify_rfc3161)
            except (_RkMalformed, _RkInclusionError) as e:
                raise _TbVErr("ANCHOR_INVALID", seq=c["seq"], detail=str(e))
            finally:
                globals()["_TBRV_KNOWN_TSA_ROOT_CERTS"] = saved
            if detail["state"] is None:
                raise _TbVErr("ANCHOR_INVALID", seq=c["seq"],
                              detail="; ".join(detail["errors"]))
            T = detail["gen_time"]
            entry = {"seq": c["seq"], "type": atype,
                     "state": detail["state"],
                     "log_index": detail["log_index"],
                     "log_origin": detail["origin"],
                     "tree_size": detail["tree_size"],
                     "rekor_log_key_provenance": log_prov}
            if detail["state"] == "INCLUDED-TIMED":
                entry["gen_time"] = T.strftime("%Y-%m-%dT%H:%M:%SZ")
                entry["tsa_root_provenance"] = tsa_prov
            else:
                report["flags"].append(
                    "checkpoint seq=%d is INCLUDED-UNTIMED: membership in the "
                    "transparency log is evidenced, but NO trusted time is "
                    "present in the anchor, so this range cannot enter the "
                    "SPEC 10.3 time bound. The Verifier reports the absence "
                    "and asserts no cause for it." % c["seq"])
            if log_prov == "operator-supplied":
                report["flags"].append(
                    "checkpoint seq=%d: the transparency-log key is "
                    "OPERATOR-SUPPLIED (carried in the pack); supply auditor "
                    "pins via NOUS_REKOR_LOG_KEYS or rekor_log_keys.json"
                    % c["seq"])
            report["anchors"].append(entry)
        else:
            raise _TbVErr("ANCHOR_TYPE", seq=c["seq"], detail=str(atype))
        if T is None:
            continue
        anchored.append({"seq": c["seq"], "T": T, "kid": kid})

    covered = -1
    prev_T = None
    for a in anchored:
        for s in range(covered + 1, a["seq"] + 1):
            ts = _tb_parse_ts(events[s]["ts_wall"])
            if (ts - a["T"]).total_seconds() > tol:
                raise _TbVErr("TIME_BOUND_VIOLATION", seq=s, detail="above upper")
            if prev_T is not None and (prev_T - ts).total_seconds() > tol:
                raise _TbVErr("TIME_BOUND_VIOLATION", seq=s, detail="below lower")
            kid = events[s]["key_id"]
            if not (keys[kid]["nb"] <= a["T"] <= keys[kid]["na"]):
                raise _TbVErr("KEY_EXPIRED", seq=s)
        covered = a["seq"]
        prev_T = a["T"]

    salts_seen = {}
    for i, e in enumerate(events):
        for ref in e.get("payload_refs", []):
            if ref["class"] not in ("content", "evidence"):
                raise _TbVErr("PAYLOAD_CLASS", seq=i)
            loaded = _tb_load_payload(pack, ref["class"], ref["hash"])
            if loaded is None:
                if ref["class"] == "evidence":
                    raise _TbVErr("ASSIGNMENT_MISSING", seq=i, detail=ref["hash"])
                report["erased"].append({"seq": i, "hash": ref["hash"]})
                continue
            salt, _ = loaded
            if salt in salts_seen and salts_seen[salt] != ref["hash"]:
                raise _TbVErr("SALT_REUSE", seq=i)
            salts_seen[salt] = ref["hash"]

    n_proved = n_declared = 0
    for i, e in enumerate(events):
        if e["event_type"] != "policy_check":
            if e.get("obligation_ref") is not None and e["event_type"] in (
                    "run_start", "error", "checkpoint", "run_end"):
                raise _TbVErr("OBLIGATION_REF_FORBIDDEN", seq=i)
            continue
        oref = e.get("obligation_ref")
        if oref is None:
            raise _TbVErr("OBLIGATION_REF_REQUIRED", seq=i)
        o = obligations.get(oref["obligation_id"])
        if o is None:
            raise _TbVErr("OBLIGATION_UNKNOWN", seq=i)
        ah = oref["assignment_hash"]
        if not any(r["hash"] == ah and r["class"] == "evidence"
                   for r in e.get("payload_refs", [])):
            raise _TbVErr("ASSIGNMENT_REF_MISSING", seq=i)
        loaded = _tb_load_payload(pack, "evidence", ah)
        if loaded is None:
            raise _TbVErr("ASSIGNMENT_MISSING", seq=i)
        _, data = loaded
        try:
            env = _tb_jloads(data.decode('utf-8'))
        except (_TbFloatFound, ValueError):
            raise _TbVErr("ASSIGNMENT_PARSE", seq=i)
        declared_vars = {v["name"]: v["type"] for v in o["variables"]}
        if set(env.keys()) != set(declared_vars.keys()):
            raise _TbVErr("ASSIGNMENT_VARS_MISMATCH", seq=i)
        for name, t in declared_vars.items():
            v = env[name]
            ok = ((t == "int" and type(v) is int)
                  or (t == "bool" and type(v) is bool)
                  or (t == "string" and type(v) is str))
            if not ok:
                raise _TbVErr("ASSIGNMENT_VARS_MISMATCH", seq=i, detail=name)
        recomputed = _tb_evaluate(o["predicate"], env)
        if recomputed != oref["verdict"]:
            raise _TbVErr("VERDICT_MISMATCH", seq=i,
                          detail="recorded=%s recomputed=%s" % (
                              oref["verdict"], recomputed))
        if o["assurance"] == "proved":
            n_proved += 1
        else:
            n_declared += 1
        report["policy_checks"].append(
            {"seq": i, "label": o["label"], "verdict": oref["verdict"],
             "assurance": o["assurance"]})

    report["recomputed"] = {"total": n_proved + n_declared,
                            "proved": n_proved, "declared": n_declared}

    # __p5a_verdict_v1__ two independent reasons a record is not clean:
    # a structural gap (no run_end + final anchored checkpoint) and a
    # declared-vs-delivered shortfall. They are kept apart so the
    # reported reason is never the wrong one.
    structural = (events[-1]["event_type"] == "checkpoint"
                  and len(events) >= 2
                  and events[-2]["event_type"] == "run_end"
                  and anchored
                  and anchored[-1]["seq"] == events[-1]["seq"])
    complete = structural and not anchoring_shortfall
    report["verdict"] = "VALID" if complete else "INTEGRITY-OK/INCOMPLETE"
    return (0 if complete else 10), report


def _check_trace_bundle(manifest, ROOT):
    # __s2xx_trace_bundle_embed_v1__ NOUS-TRACE v0.2.1 runtime evidence
    # bundle. MONITOR, NOT GATE: returns 0 on VALID and on INTEGRITY-OK/
    # INCOMPLETE (the latter is a truthful adverse finding, not a process
    # failure); non-zero ONLY on integrity failure (sha mismatch of the
    # bundle manifest, missing-but-declared bundle, or any INVALID verdict
    # from the embedded per-event chain verifier: broken hash chain,
    # bad signature, verdict-recomputation mismatch, salt reuse, expired
    # key, time-bound violation, float-in-signed, missing evidence).
    #
    # Honest boundary: a VALID bundle EVIDENCES that a signed, unbroken
    # per-event chain was recorded and that every recorded policy verdict
    # re-computes from its signed assignment record under the declared
    # NOUS-EXPR predicate. It PROVES nothing; the only PROVES legs remain
    # Z3 cost bounds and Farkas. The anchor here is "rfc3161-sim" (a local
    # Ed25519 anchor simulating a TSA): it evidences monotone ordering
    # WITHIN the bundle, not trusted wall-clock time to an external party.
    # trust_anchors (both pubkeys), tolerance, and the keys/obligations
    # hashes live in the bundle manifest.json, which is sha-gated by the
    # signed dossier manifest here; everything else in the bundle is
    # transitively authenticated by signatures rooted in those pinned keys.
    import hashlib as _hl
    import sys as _sys

    field = manifest.get("trace_bundle_sha256")
    bundle_dir = ROOT / "trace_bundle"
    bundle_manifest = bundle_dir / "manifest.json"
    if field is None:
        if bundle_dir.is_dir():
            print("FAIL: manifest declares no trace_bundle_sha256 but a "
                  "trace_bundle/ directory is present (unexpected evidence)",
                  file=_sys.stderr)
            return 1
        return 0
    if not bundle_manifest.is_file():
        print("FAIL: signed manifest declares trace_bundle_sha256 but "
              "trace_bundle/manifest.json is missing (missing evidence / "
              "truncation)", file=_sys.stderr)
        return 1
    mb = bundle_manifest.read_bytes()
    if _hl.sha256(mb).hexdigest() != field:
        print("FAIL: trace_bundle/manifest.json sha256 does not match the "
              "signed manifest trace_bundle_sha256 (evidence bundle trust "
              "root tampered or substituted)", file=_sys.stderr)
        return 1

    try:
        code, report = _tb_verify_pack(str(bundle_dir))
    except _TbVErr as e:
        loc = "" if e.seq is None else (" at seq " + str(e.seq))
        det = (" (" + e.detail + ")") if e.detail else ""
        print("FAIL: NOUS-TRACE evidence bundle is INVALID" + loc + ": "
              + e.reason + det + " (the runtime evidence chain is tampered, "
              "truncated, or internally inconsistent)", file=_sys.stderr)
        return 1
    except _TbFloatFound:
        print("FAIL: NOUS-TRACE evidence bundle is INVALID: FLOAT_IN_SIGNED "
              "(a float appears in a signed object)", file=_sys.stderr)
        return 1
    except Exception as e:
        print("FAIL: NOUS-TRACE evidence bundle could not be verified: "
              + str(e), file=_sys.stderr)
        return 1

    rc = report.get("recomputed", {})
    print("OK   NOUS-TRACE evidence bundle authenticated "
          "(trace_bundle/manifest.json sha-gated by the signed dossier "
          "manifest; per-event chain verified)")
    print("     RECOMPUTED: %d policy verdict(s) re-computed from signed "
          "assignment records (%d proved-obligation, %d declared); "
          "%d anchored checkpoint(s)" % (
              rc.get("total", 0), rc.get("proved", 0), rc.get("declared", 0),
              len(report.get("anchors", []))))
    if report.get("erased"):
        print("     ERASURE: %d content payload(s) erased (GDPR); evidence "
              "payloads are non-erasable by construction and all present"
              % len(report["erased"]))
    if code == 0:
        print("OK   NOUS-TRACE verdict: VALID. The run recorded an unbroken "
              "signed event chain terminating in run_end + a final anchored "
              "checkpoint. This EVIDENCES tamper-evident runtime execution "
              "under the named anchor-sim assumption; it proves nothing and "
              "adjudicates nothing.")
    else:
        # __p5a_message_v1__ rc 10 now has two possible causes; naming
        # only one of them asserts a cause that may not have occurred.
        print("INFO NOUS-TRACE verdict: INTEGRITY-OK/INCOMPLETE. The event "
              "chain is signature-valid and internally consistent, but the "
              "record falls short of a clean run: either it does not "
              "terminate in run_end + a final anchored checkpoint, or a "
              "checkpoint delivered an anchor type other than the declared "
              "anchoring policy. The flags below state which. This is a "
              "TRUTHFUL detected state, not a process failure (monitor); "
              "no cause is asserted. An auditor should treat the run as "
              "INCOMPLETE evidence.")
        for fl in report.get("flags", []):
            print("     flag: " + fl)

    import json as _js
    verdict_obj = {
        "kind": "nous-trace-evidence-bundle-v1",
        "verdict": report.get("verdict"),
        "recomputed": rc,
        "anchors": len(report.get("anchors", [])),
        "erased": len(report.get("erased", [])),
        "basis": ("per-event Ed25519 chain + NOUS-EXPR verdict recomputation "
                  "over signed assignment records; anchor is rfc3161-sim "
                  "(monotone ordering, not trusted wall-clock); monitor, "
                  "not guard"),
    }
    print("TRACE_BUNDLE_VERDICT_JSON: "
          + _js.dumps(verdict_obj, sort_keys=True, separators=(",", ":")))
    return 0
