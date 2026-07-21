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
        if a["type"] != "rfc3161-sim":
            raise _TbVErr("ANCHOR_TYPE", seq=c["seq"])
        tok_hash = _tb_sha256(root + a["gen_time"].encode())
        if not _tb_verify_sig(anch_pub, _TB_TAG_ANCH, tok_hash, a["token"]):
            raise _TbVErr("ANCHOR_INVALID", seq=c["seq"])
        T = _tb_parse_ts(a["gen_time"])
        anchored.append({"seq": c["seq"], "T": T, "kid": kid})
        report["anchors"].append({"seq": c["seq"], "gen_time": a["gen_time"]})

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
