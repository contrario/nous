#!/usr/bin/env python3
import sys, os, json, hashlib, base64
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
        if a["type"] != "rfc3161-sim":
            raise VErr("ANCHOR_TYPE", seq=c["seq"])
        tok_hash = sha256(root + a["gen_time"].encode())
        if not verify_sig(anch_pub, TAG_ANCH, tok_hash, a["token"]):
            raise VErr("ANCHOR_INVALID", seq=c["seq"])
        T = parse_ts(a["gen_time"])
        anchored.append({"seq": c["seq"], "T": T, "kid": kid})
        report["anchors"].append({"seq": c["seq"], "gen_time": a["gen_time"]})

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
