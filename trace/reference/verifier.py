#!/usr/bin/env python3
import sys, os, json, hashlib, base64, re
from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

SPEC = "0.2.0"
TAG_EVENT = b"NOUS-TRACE/v0.2/event"
TAG_CKPT = b"NOUS-TRACE/v0.2/checkpoint-root"
TAG_OBL = b"NOUS-TRACE/v0.2/obligation-manifest"
TAG_KEYS = b"NOUS-TRACE/v0.2/keys-manifest"
TAG_ANCH = b"NOUS-TRACE/v0.2/anchor-sim"
MAX_INT = 2**53 - 1


# --- SPEC 10.1 production anchor backend: RFC 3161 -------------------------
# Extracted verbatim from the shipped _pa_ implementation (dossier.py) and
# renamed to _rv_; identical, already-proven code, kept inline so this
# reference verifier remains standalone.

_RV_OID_SIGNED_DATA = "1.2.840.113549.1.7.2"
_RV_OID_CT_TSTINFO = "1.2.840.113549.1.9.16.1.4"
_RV_OID_ATTR_CONTENT_TYPE = "1.2.840.113549.1.9.3"
_RV_OID_ATTR_MESSAGE_DIGEST = "1.2.840.113549.1.9.4"

_RV_KNOWN_TSA_ROOT_CERTS = [
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


class _RvMalformed(ValueError):
    pass


def _rv_der_len(buf, off):
    b = buf[off]
    if b < 0x80:
        return b, off + 1
    n = b & 0x7F
    if n == 0 or n > 4:
        raise _RvMalformed("unsupported DER length form")
    return int.from_bytes(buf[off + 1:off + 1 + n], "big"), off + 1 + n


def _rv_tlv(buf, off):
    length, hdr_end = _rv_der_len(buf, off + 1)
    end = hdr_end + length
    if end > len(buf):
        raise _RvMalformed("DER length exceeds buffer")
    return buf[off], off, hdr_end, end


def _rv_children(buf, start, end):
    out = []
    off = start
    while off < end:
        tag, tlv_start, c_off, c_end = _rv_tlv(buf, off)
        out.append((tag, tlv_start, c_off, c_end))
        off = c_end
    return out


def _rv_oid_str(buf, c_off, c_end):
    data = buf[c_off:c_end]
    if not data:
        raise _RvMalformed("empty OID")
    first = data[0]
    parts = [str(first // 40), str(first % 40)]
    val = 0
    for byte in data[1:]:
        val = (val << 7) | (byte & 0x7F)
        if not byte & 0x80:
            parts.append(str(val))
            val = 0
    return ".".join(parts)


def _rv_parse_token(token_der):
    try:
        _, _, ci_c, ci_end = _rv_tlv(token_der, 0)
        ci_kids = _rv_children(token_der, ci_c, ci_end)
        if _rv_oid_str(token_der, ci_kids[0][2], ci_kids[0][3]) != \
                _RV_OID_SIGNED_DATA:
            raise _RvMalformed("token is not a CMS SignedData")
        sd = _rv_children(token_der, ci_kids[1][2], ci_kids[1][3])[0]
        sd_kids = _rv_children(token_der, sd[2], sd[3])
        enc = next(k for k in sd_kids if k[0] == 0x30)
        enc_kids = _rv_children(token_der, enc[2], enc[3])
        if _rv_oid_str(token_der, enc_kids[0][2], enc_kids[0][3]) != \
                _RV_OID_CT_TSTINFO:
            raise _RvMalformed("eContentType is not id-ct-TSTInfo")
        oct0 = _rv_children(token_der, enc_kids[1][2], enc_kids[1][3])[0]
        tstinfo = token_der[oct0[2]:oct0[3]]
        certs = []
        for k in sd_kids:
            if k[0] == 0xA0:
                for c in _rv_children(token_der, k[2], k[3]):
                    certs.append(token_der[c[1]:c[3]])
                break
        signer_set = [k for k in sd_kids if k[0] == 0x31 and k[1] > enc[3]][0]
        si = _rv_children(token_der, signer_set[2], signer_set[3])[0]
        si_kids = _rv_children(token_der, si[2], si[3])
        i = 2
        digest_alg = _rv_children(token_der, si_kids[i][2], si_kids[i][3])
        digest_oid = _rv_oid_str(token_der, digest_alg[0][2], digest_alg[0][3])
        i += 1
        signed_attrs_der = None
        signed_attrs_span = None
        if si_kids[i][0] == 0xA0:
            sa = si_kids[i]
            signed_attrs_der = b"\x31" + token_der[sa[1] + 1:sa[3]]
            signed_attrs_span = (sa[2], sa[3])
            i += 1
        sig_alg = _rv_children(token_der, si_kids[i][2], si_kids[i][3])
        sig_alg_oid = _rv_oid_str(token_der, sig_alg[0][2], sig_alg[0][3])
        i += 1
        signature = token_der[si_kids[i][2]:si_kids[i][3]]
        attrs = {}
        if signed_attrs_span is not None:
            for a in _rv_children(token_der, *signed_attrs_span):
                ak = _rv_children(token_der, a[2], a[3])
                a_oid = _rv_oid_str(token_der, ak[0][2], ak[0][3])
                vset = _rv_children(token_der, ak[1][2], ak[1][3])[0]
                attrs[a_oid] = (vset[2], vset[3])
    except _RvMalformed:
        raise
    except (IndexError, StopIteration, ValueError) as exc:
        raise _RvMalformed("malformed TimeStampToken: " + repr(exc)) from exc
    if signed_attrs_der is None:
        raise _RvMalformed("TimeStampToken has no signed attributes")
    return {
        "tstinfo": tstinfo, "certs": certs, "digest_oid": digest_oid,
        "signed_attrs_der": signed_attrs_der, "sig_alg_oid": sig_alg_oid,
        "signature": signature, "attrs": attrs, "buf": token_der,
    }


def _rv_parse_tstinfo(tstinfo):
    import datetime as _dt
    try:
        _, _, c, e = _rv_tlv(tstinfo, 0)
        kids = _rv_children(tstinfo, c, e)
        mi = next(k for k in kids if k[0] == 0x30)
        mi_kids = _rv_children(tstinfo, mi[2], mi[3])
        alg_kids = _rv_children(tstinfo, mi_kids[0][2], mi_kids[0][3])
        imprint_alg_oid = _rv_oid_str(tstinfo, alg_kids[0][2], alg_kids[0][3])
        hashed = tstinfo[mi_kids[1][2]:mi_kids[1][3]]
        gt = next(k for k in kids if k[0] == 0x18)
        gen = tstinfo[gt[2]:gt[3]].decode("ascii")
    except (IndexError, StopIteration, ValueError, UnicodeDecodeError) as exc:
        raise _RvMalformed("malformed TSTInfo: " + repr(exc)) from exc
    dt = _dt.datetime.strptime(gen.rstrip("Z"), "%Y%m%d%H%M%S").replace(
        tzinfo=_dt.timezone.utc
    )
    return hashed, imprint_alg_oid, dt


def _rv_verify_rfc3161(token_der, timestamped_data):
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
    parsed = _rv_parse_token(token_der)
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
        for root_pem in _RV_KNOWN_TSA_ROOT_CERTS:
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
    ct_span = parsed["attrs"].get(_RV_OID_ATTR_CONTENT_TYPE)
    if ct_span is None:
        errors.append("missing content-type signed attribute")
    else:
        content_type_ok = (
            _rv_oid_str(parsed["buf"], ct_span[0], ct_span[1])
            == _RV_OID_CT_TSTINFO
        )
        if not content_type_ok:
            errors.append("content-type signed attribute is not id-ct-TSTInfo")

    message_digest_ok = False
    md_span = parsed["attrs"].get(_RV_OID_ATTR_MESSAGE_DIGEST)
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

    hashed, imprint_alg_oid, gen_time = _rv_parse_tstinfo(parsed["tstinfo"])
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


def _rv_resolve_tsa_roots(pack, man):
    """Return (roots, provenance). Auditor pins win; pack-carried roots are
    accepted but downgrade the report (the operator asserts its own trust
    root). No roots -> ([], "none")."""
    import os as _os
    path = _os.environ.get("NOUS_TSA_ROOTS")
    if not path:
        cand = _os.path.join(pack, "tsa_roots.pem")
        path = cand if _os.path.isfile(cand) else None
    if path and _os.path.isfile(path):
        with open(path, "r", encoding="ascii") as f:
            blob = f.read()
        roots = [m.group(0) for m in re.finditer(
            r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----\n?",
            blob, re.S)]
        if roots:
            return roots, "auditor-pinned"
    carried = (man.get("trust_anchors") or {}).get("tsa_roots")
    if isinstance(carried, list) and carried:
        return list(carried), "operator-supplied"
    return [], "none"



class VErr(Exception):
    def __init__(self, reason, seq=None, detail=""):
        self.reason, self.seq, self.detail = reason, seq, detail
        super().__init__(f"{reason} seq={seq} {detail}")


class FloatFound(Exception):
    pass


def _reject_float(_s):
    raise FloatFound()


def jloads(s):
    return json.loads(s, parse_float=_reject_float)


def _jcs_str(s):
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


def jcs(obj):
    if obj is None:
        return 'null'
    if obj is True:
        return 'true'
    if obj is False:
        return 'false'
    if isinstance(obj, int):
        if abs(obj) > MAX_INT:
            raise VErr("INT_RANGE", detail=str(obj))
        return str(obj)
    if isinstance(obj, float):
        raise VErr("FLOAT_IN_SIGNED")
    if isinstance(obj, str):
        return _jcs_str(obj)
    if isinstance(obj, list):
        return '[' + ','.join(jcs(x) for x in obj) + ']'
    if isinstance(obj, dict):
        keys = sorted(obj.keys(), key=lambda k: k.encode('utf-16-be'))
        return '{' + ','.join(_jcs_str(k) + ':' + jcs(obj[k]) for k in keys) + '}'
    raise VErr("JCS_TYPE", detail=type(obj).__name__)


def sha256(b):
    return hashlib.sha256(b).digest()


def jcs_hash(obj):
    return sha256(jcs(obj).encode('utf-8'))


def key_id_of(pub_raw):
    return sha256(pub_raw)[:8].hex()


def verify_sig(pub_raw, tag, obj_hash, sig_hex):
    try:
        Ed25519PublicKey.from_public_bytes(pub_raw).verify(bytes.fromhex(sig_hex), tag + b"\x00" + obj_hash)
        return True
    except (InvalidSignature, ValueError):
        return False


def merkle_root(leaves):
    if not leaves:
        return sha256(b'')
    if len(leaves) == 1:
        return sha256(b'\x00' + leaves[0])
    k = 1
    while k * 2 < len(leaves):
        k *= 2
    return sha256(b'\x01' + merkle_root(leaves[:k]) + merkle_root(leaves[k:]))


def parse_ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


class EvalError(Exception):
    pass


def ev(node, env):
    if not isinstance(node, dict):
        raise EvalError()
    if "var" in node:
        if node["var"] not in env:
            raise EvalError()
        return env[node["var"]]
    if "int" in node:
        if type(node["int"]) is not int:
            raise EvalError()
        return node["int"]
    if "str" in node:
        if type(node["str"]) is not str:
            raise EvalError()
        return node["str"]
    if "bool" in node:
        if type(node["bool"]) is not bool:
            raise EvalError()
        return node["bool"]
    if "set" in node:
        if not isinstance(node["set"], list) or not all(type(x) is str for x in node["set"]):
            raise EvalError()
        return frozenset(node["set"])
    op = node.get("op")
    if op == "and":
        return all(_b(ev(a, env)) for a in node["args"])
    if op == "or":
        return any(_b(ev(a, env)) for a in node["args"])
    if op == "not":
        return not _b(ev(node["arg"], env))
    if op in ("+", "-", "*"):
        l, r = _i(ev(node["left"], env)), _i(ev(node["right"], env))
        return l + r if op == "+" else l - r if op == "-" else l * r
    if op in ("=", "!="):
        l, r = ev(node["left"], env), ev(node["right"], env)
        if type(l) is not type(r) or isinstance(l, frozenset):
            raise EvalError()
        return (l == r) if op == "=" else (l != r)
    if op in ("<", "<=", ">", ">="):
        l, r = _i(ev(node["left"], env)), _i(ev(node["right"], env))
        return {"<": l < r, "<=": l <= r, ">": l > r, ">=": l >= r}[op]
    if op == "prefix_of":
        l, r = _s(ev(node["left"], env)), _s(ev(node["right"], env))
        return r.startswith(l)
    if op == "in":
        l = _s(ev(node["left"], env))
        r = ev(node["right"], env)
        if not isinstance(r, frozenset):
            raise EvalError()
        return l in r
    raise EvalError()


def _b(v):
    if type(v) is not bool:
        raise EvalError()
    return v


def _i(v):
    if type(v) is not int or type(v) is bool:
        raise EvalError()
    return v


def _s(v):
    if type(v) is not str:
        raise EvalError()
    return v


def evaluate(pred, env):
    try:
        return "pass" if _b(ev(pred, env)) else "fail"
    except EvalError:
        return "error"


def load_payload(pack, cls, h):
    p = os.path.join(pack, "payloads", cls, h)
    if not os.path.exists(p):
        return None
    with open(p) as f:
        entry = jloads(f.read())
    salt = bytes.fromhex(entry["salt"])
    data = base64.b64decode(entry["data"])
    if sha256(salt + data).hex() != h:
        raise VErr("PAYLOAD_HASH_MISMATCH", detail=h)
    return salt, data


def verify_pack(pack):
    report = {"pack": pack, "flags": [], "erased": [], "policy_checks": [], "anchors": []}

    with open(os.path.join(pack, "manifest.json")) as f:
        man = jloads(f.read())
    if man["spec_version"] != SPEC:
        raise VErr("SPEC_VERSION", detail=man["spec_version"])
    dep_pub = bytes.fromhex(man["trust_anchors"]["deployment_pub"])
    anch_pub = bytes.fromhex(man["trust_anchors"]["anchor_pub"])
    tol = man["tolerance_s"]
    if not isinstance(tol, int) or tol > 3600:
        raise VErr("TOLERANCE_INVALID")

    for fn in ("keys.json", "obligations.json"):
        with open(os.path.join(pack, fn), 'rb') as f:
            if sha256(f.read()).hex() != man["hashes"][fn]:
                raise VErr("MANIFEST_FILE_HASH", detail=fn)

    with open(os.path.join(pack, "keys.json")) as f:
        keysdoc = jloads(f.read())
    keys_core = {"keys": keysdoc["keys"]}
    keys_hash = jcs_hash(keys_core)
    if not verify_sig(dep_pub, TAG_KEYS, keys_hash, keysdoc["sig"]):
        raise VErr("KEYS_MANIFEST_SIG")
    keys = {}
    for k in keysdoc["keys"]:
        raw = bytes.fromhex(k["public_key"])
        if key_id_of(raw) != k["key_id"]:
            raise VErr("KEY_ID_MISMATCH", detail=k["key_id"])
        keys[k["key_id"]] = {"raw": raw, "role": k["role"],
                             "nb": parse_ts(k["not_before"]), "na": parse_ts(k["not_after"])}

    with open(os.path.join(pack, "obligations.json")) as f:
        obldoc = jloads(f.read())
    obl_core = {"obligations": obldoc["obligations"]}
    obl_hash = jcs_hash(obl_core)
    if not verify_sig(dep_pub, TAG_OBL, obl_hash, obldoc["sig"]):
        raise VErr("OBLIGATION_MANIFEST_SIG")
    obligations = {}
    for o in obldoc["obligations"]:
        if jcs_hash(o["predicate"]).hex() != o["obligation_id"]:
            raise VErr("OBLIGATION_ID_MISMATCH", detail=o["label"])
        if o["assurance"] == "proved":
            pf = os.path.join(pack, "proofs", o["proof_artifact_hash"])
            if not os.path.exists(pf):
                raise VErr("PROOF_ARTIFACT_MISSING", detail=o["label"])
            with open(pf, 'rb') as f:
                if sha256(f.read()).hex() != o["proof_artifact_hash"]:
                    raise VErr("PROOF_ARTIFACT_HASH", detail=o["label"])
        elif o["assurance"] != "declared":
            raise VErr("ASSURANCE_INVALID", detail=o["label"])
        obligations[o["obligation_id"]] = o

    events = []
    with open(os.path.join(pack, "trace.ndjson")) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                e = jloads(line)
            except FloatFound:
                raise VErr("FLOAT_IN_SIGNED", seq=i)
            events.append(e)
    if not events:
        raise VErr("EMPTY_TRACE")

    trace_id = events[0]["trace_id"]
    prev = "0" * 64
    ehashes = []
    for i, e in enumerate(events):
        if e.get("spec_version") != SPEC:
            raise VErr("SPEC_VERSION", seq=i)
        if e.get("trace_id") != trace_id:
            raise VErr("TRACE_ID_MIXED", seq=i)
        if e.get("seq") != i:
            raise VErr("SEQ_ORDER", seq=i, detail=f"got {e.get('seq')}")
        if e.get("prev_hash") != prev:
            raise VErr("HASH_CHAIN_BREAK", seq=i)
        core = {k: v for k, v in e.items() if k != "sig"}
        try:
            eh = jcs_hash(core)
        except VErr as ve:
            ve.seq = i
            raise
        kid = e.get("key_id")
        if kid not in keys or keys[kid]["role"] != "runtime":
            raise VErr("KEY_UNKNOWN", seq=i, detail=str(kid))
        if not verify_sig(keys[kid]["raw"], TAG_EVENT, eh, e["sig"]):
            raise VErr("SIG_INVALID", seq=i)
        ehashes.append(eh)
        prev = eh.hex()

    if events[0]["event_type"] != "run_start":
        raise VErr("STRUCT_NO_RUN_START", seq=0)
    rs = events[0]["body"]
    if rs["keys_manifest_hash"] != keys_hash.hex():
        raise VErr("RUN_START_KEYS_HASH", seq=0)
    if rs["obligation_manifest_hash"] != obl_hash.hex():
        raise VErr("RUN_START_OBL_HASH", seq=0)
    if rs["tolerance_s"] != tol:
        raise VErr("RUN_START_TOLERANCE", seq=0)

    ckpts = [e for e in events if e["event_type"] == "checkpoint"]
    expected_from = 0
    anchored = []
    for c in ckpts:
        b = c["body"]
        fr, to = b["range"]["from_seq"], b["range"]["to_seq"]
        if fr != expected_from or to != c["seq"] - 1:
            raise VErr("CKPT_RANGE", seq=c["seq"])
        expected_from = c["seq"]
        root = merkle_root(ehashes[fr:to + 1])
        if root.hex() != b["merkle_root"]:
            raise VErr("MERKLE_MISMATCH", seq=c["seq"])
        kid = c["key_id"]
        if not verify_sig(keys[kid]["raw"], TAG_CKPT, root, b["root_sig"]):
            raise VErr("CKPT_ROOT_SIG", seq=c["seq"])
        a = b.get("anchor")
        if a is None:
            report["flags"].append(f"unanchored checkpoint seq={c['seq']}")
            continue
        atype = a.get("type")
        if atype == "rfc3161-sim":
            # E5 test backend: a pinned local key signs SHA-256(root || gen_time).
            # Production packs MUST NOT declare it (SPEC 10.1); flag it here.
            tok_hash = sha256(root + a["gen_time"].encode())
            if not verify_sig(anch_pub, TAG_ANCH, tok_hash, a["token"]):
                raise VErr("ANCHOR_INVALID", seq=c["seq"])
            T = parse_ts(a["gen_time"])
            if not man.get("test_vector", False):
                report["flags"].append(
                    "checkpoint seq=%d uses the rfc3161-sim TEST backend but "
                    "the pack is not marked test_vector; it evidences no "
                    "trusted time to an external auditor (SPEC 10.1)"
                    % c["seq"])
            report["anchors"].append({"seq": c["seq"], "type": atype,
                                      "gen_time": a["gen_time"]})
        elif atype == "rfc3161":
            # Production backend: an RFC 3161 token over the Merkle root. The
            # time is the TSA's genTime, recovered from the token -- never a
            # Producer-declared field.
            roots, provenance = _rv_resolve_tsa_roots(pack, man)
            report.setdefault("tsa_root_provenance", provenance)
            if not roots:
                raise VErr("ANCHOR_INVALID", seq=c["seq"],
                           detail="no pinned TSA roots available "
                                  "(NOUS_TSA_ROOTS, tsa_roots.pem, or "
                                  "manifest.trust_anchors.tsa_roots)")
            tok_b64 = a.get("token_b64")
            if not isinstance(tok_b64, str) or not tok_b64:
                raise VErr("ANCHOR_INVALID", seq=c["seq"],
                           detail="rfc3161 anchor carries no token_b64")
            try:
                token_der = base64.b64decode(tok_b64, validate=True)
            except Exception as e:
                raise VErr("ANCHOR_INVALID", seq=c["seq"],
                           detail="token_b64 decode: " + str(e))
            saved = globals()["_RV_KNOWN_TSA_ROOT_CERTS"]
            try:
                globals()["_RV_KNOWN_TSA_ROOT_CERTS"] = roots
                ok, T, errs = _rv_verify_rfc3161(token_der, root)
            except _RvMalformed as e:
                raise VErr("ANCHOR_INVALID", seq=c["seq"],
                           detail="malformed token: " + str(e))
            finally:
                globals()["_RV_KNOWN_TSA_ROOT_CERTS"] = saved
            if not ok:
                raise VErr("ANCHOR_INVALID", seq=c["seq"],
                           detail="; ".join(errs))
            if provenance == "operator-supplied":
                report["flags"].append(
                    "checkpoint seq=%d: the RFC 3161 token verifies, but the "
                    "TSA trust root is OPERATOR-SUPPLIED (carried in the pack). "
                    "Supply auditor pins via NOUS_TSA_ROOTS or tsa_roots.pem to "
                    "establish an independent trust root." % c["seq"])
            report["anchors"].append({"seq": c["seq"], "type": atype,
                                      "gen_time": T.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                      "tsa_root_provenance": provenance})
        else:
            raise VErr("ANCHOR_TYPE", seq=c["seq"], detail=str(atype))
        anchored.append({"seq": c["seq"], "T": T, "kid": kid})

    covered = -1
    prev_T = None
    for a in anchored:
        for s in range(covered + 1, a["seq"] + 1):
            ts = parse_ts(events[s]["ts_wall"])
            if (ts - a["T"]).total_seconds() > tol:
                raise VErr("TIME_BOUND_VIOLATION", seq=s, detail="above upper")
            if prev_T is not None and (prev_T - ts).total_seconds() > tol:
                raise VErr("TIME_BOUND_VIOLATION", seq=s, detail="below lower")
            kid = events[s]["key_id"]
            if not (keys[kid]["nb"] <= a["T"] <= keys[kid]["na"]):
                raise VErr("KEY_EXPIRED", seq=s)
        covered = a["seq"]
        prev_T = a["T"]

    salts_seen = {}
    for i, e in enumerate(events):
        for ref in e.get("payload_refs", []):
            if ref["class"] not in ("content", "evidence"):
                raise VErr("PAYLOAD_CLASS", seq=i)
            loaded = load_payload(pack, ref["class"], ref["hash"])
            if loaded is None:
                if ref["class"] == "evidence":
                    raise VErr("ASSIGNMENT_MISSING", seq=i, detail=ref["hash"])
                report["erased"].append({"seq": i, "hash": ref["hash"]})
                continue
            salt, _ = loaded
            if salt in salts_seen and salts_seen[salt] != ref["hash"]:
                raise VErr("SALT_REUSE", seq=i)
            salts_seen[salt] = ref["hash"]

    n_proved = n_declared = 0
    for i, e in enumerate(events):
        if e["event_type"] != "policy_check":
            if e.get("obligation_ref") is not None and e["event_type"] in ("run_start", "error", "checkpoint", "run_end"):
                raise VErr("OBLIGATION_REF_FORBIDDEN", seq=i)
            continue
        oref = e.get("obligation_ref")
        if oref is None:
            raise VErr("OBLIGATION_REF_REQUIRED", seq=i)
        o = obligations.get(oref["obligation_id"])
        if o is None:
            raise VErr("OBLIGATION_UNKNOWN", seq=i)
        ah = oref["assignment_hash"]
        if not any(r["hash"] == ah and r["class"] == "evidence" for r in e.get("payload_refs", [])):
            raise VErr("ASSIGNMENT_REF_MISSING", seq=i)
        loaded = load_payload(pack, "evidence", ah)
        if loaded is None:
            raise VErr("ASSIGNMENT_MISSING", seq=i)
        _, data = loaded
        try:
            env = jloads(data.decode('utf-8'))
        except (FloatFound, ValueError):
            raise VErr("ASSIGNMENT_PARSE", seq=i)
        declared_vars = {v["name"]: v["type"] for v in o["variables"]}
        if set(env.keys()) != set(declared_vars.keys()):
            raise VErr("ASSIGNMENT_VARS_MISMATCH", seq=i)
        for name, t in declared_vars.items():
            v = env[name]
            ok = (t == "int" and type(v) is int) or (t == "bool" and type(v) is bool) or (t == "string" and type(v) is str)
            if not ok:
                raise VErr("ASSIGNMENT_VARS_MISMATCH", seq=i, detail=name)
        recomputed = evaluate(o["predicate"], env)
        if recomputed != oref["verdict"]:
            raise VErr("VERDICT_MISMATCH", seq=i,
                       detail=f"recorded={oref['verdict']} recomputed={recomputed}")
        if o["assurance"] == "proved":
            n_proved += 1
        else:
            n_declared += 1
        report["policy_checks"].append({"seq": i, "label": o["label"],
                                        "verdict": oref["verdict"], "assurance": o["assurance"]})

    report["recomputed"] = {"total": n_proved + n_declared, "proved": n_proved, "declared": n_declared}

    complete = (events[-1]["event_type"] == "checkpoint"
                and len(events) >= 2 and events[-2]["event_type"] == "run_end"
                and anchored and anchored[-1]["seq"] == events[-1]["seq"])
    if complete:
        report["verdict"] = "VALID"
        return 0, report
    report["verdict"] = "INTEGRITY-OK/INCOMPLETE"
    report["flags"].append("no run_end + final anchored checkpoint; adverse finding in audit context")
    return 10, report


def main():
    pack = sys.argv[1]
    try:
        code, report = verify_pack(pack)
    except VErr as e:
        report = {"pack": pack, "verdict": f"INVALID({e.reason})", "seq": e.seq, "detail": e.detail}
        code = 20
    except FloatFound:
        report = {"pack": pack, "verdict": "INVALID(FLOAT_IN_SIGNED)"}
        code = 20
    print(json.dumps(report, indent=2))
    sys.exit(code)


if __name__ == "__main__":
    main()
