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
