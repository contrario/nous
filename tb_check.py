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
        else:
            raise _TbVErr("ANCHOR_TYPE", seq=c["seq"], detail=str(atype))
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

    complete = (events[-1]["event_type"] == "checkpoint"
                and len(events) >= 2 and events[-2]["event_type"] == "run_end"
                and anchored and anchored[-1]["seq"] == events[-1]["seq"])
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
        print("INFO NOUS-TRACE verdict: INTEGRITY-OK/INCOMPLETE. The event "
              "chain is signature-valid and internally consistent, but does "
              "not terminate in run_end + a final anchored checkpoint (the "
              "run crashed or was truncated). This is a TRUTHFUL detected "
              "state, not a process failure (monitor). An auditor should "
              "treat the run as INCOMPLETE evidence.")
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
