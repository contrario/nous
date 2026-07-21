#!/usr/bin/env python3
import os, sys, json, hashlib, base64, shutil, secrets, uuid
from datetime import datetime, timedelta, timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

SPEC = "0.2.0"
TAG_EVENT = b"NOUS-TRACE/v0.2/event"
TAG_CKPT = b"NOUS-TRACE/v0.2/checkpoint-root"
TAG_OBL = b"NOUS-TRACE/v0.2/obligation-manifest"
TAG_KEYS = b"NOUS-TRACE/v0.2/keys-manifest"
TAG_ANCH = b"NOUS-TRACE/v0.2/anchor-sim"

BASE = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)


def ts(minutes):
    return (BASE + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def jcs(obj):
    if obj is None:
        return 'null'
    if obj is True:
        return 'true'
    if obj is False:
        return 'false'
    if isinstance(obj, bool):
        return 'true' if obj else 'false'
    if isinstance(obj, int):
        return str(obj)
    if isinstance(obj, float):
        return repr(obj)
    if isinstance(obj, str):
        return json.dumps(obj, ensure_ascii=False)
    if isinstance(obj, list):
        return '[' + ','.join(jcs(x) for x in obj) + ']'
    if isinstance(obj, dict):
        ks = sorted(obj.keys(), key=lambda k: k.encode('utf-16-be'))
        return '{' + ','.join(json.dumps(k, ensure_ascii=False) + ':' + jcs(obj[k]) for k in ks) + '}'
    raise TypeError(type(obj))


def sha(b):
    return hashlib.sha256(b).digest()


def jh(o):
    return sha(jcs(o).encode('utf-8'))


def kid(pub):
    return sha(pub)[:8].hex()


class Key:
    def __init__(self):
        self.sk = Ed25519PrivateKey.generate()
        self.pub = self.sk.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.kid = kid(self.pub)

    def sign(self, tag, obj_hash):
        return self.sk.sign(tag + b"\x00" + obj_hash).hex()


class Signer:
    def __init__(self, key):
        self.key, self.state = key, {}

    def sign_event(self, ev_core):
        tid, seq = ev_core["trace_id"], ev_core["seq"]
        last_seq, last_hash = self.state.get(tid, (-1, "0" * 64))
        assert seq == last_seq + 1, "signer: non-monotonic seq refused"
        assert ev_core["prev_hash"] == last_hash, "signer: prev_hash mismatch refused"
        eh = jh(ev_core)
        self.state[tid] = (seq, eh.hex())
        return eh, self.key.sign(TAG_EVENT, eh)


def store_payload(pack, cls, data, salt=None):
    salt = salt or secrets.token_bytes(16)
    h = sha(salt + data).hex()
    d = os.path.join(pack, "payloads", cls)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, h), 'w') as f:
        json.dump({"salt": salt.hex(), "media_type": "application/json",
                   "data": base64.b64encode(data).decode()}, f)
    return h, salt


PRED_LIMIT = {"op": "or", "args": [
    {"op": "<=", "left": {"var": "amount_eur_cents"}, "right": {"int": 50000}},
    {"var": "human_approved"}]}
PRED_ALLOW = {"op": "and", "args": [
    {"op": "in", "left": {"var": "recipient_domain"}, "right": {"set": ["aade.gr", "efka.gov.gr"]}},
    {"op": "prefix_of", "left": {"str": "GR"}, "right": {"var": "vat_id"}}]}


def build_golden(pack, runtime_expired=False):
    os.makedirs(pack, exist_ok=True)
    dep, rt, anch = Key(), Key(), Key()
    trace_id = str(uuid.uuid4())

    proof_blob = jcs({"solver": "z3-4.13", "predicate_id": jh(PRED_LIMIT).hex(),
                      "result": "unsat", "core": ["!P"]}).encode()
    os.makedirs(os.path.join(pack, "proofs"), exist_ok=True)
    ph = sha(proof_blob).hex()
    with open(os.path.join(pack, "proofs", ph), 'wb') as f:
        f.write(proof_blob)

    obligations = [
        {"obligation_id": jh(PRED_LIMIT).hex(), "label": "max_refund_without_human",
         "predicate": PRED_LIMIT,
         "variables": [{"name": "amount_eur_cents", "type": "int"},
                       {"name": "human_approved", "type": "bool"}],
         "assurance": "proved", "proof_artifact_hash": ph, "dossier_ref": "nous://dossier/demo/1"},
        {"obligation_id": jh(PRED_ALLOW).hex(), "label": "gov_recipient_allowlist",
         "predicate": PRED_ALLOW,
         "variables": [{"name": "recipient_domain", "type": "string"},
                       {"name": "vat_id", "type": "string"}],
         "assurance": "declared", "proof_artifact_hash": None, "dossier_ref": None}]
    obl_core = {"obligations": obligations}
    obldoc = {"obligations": obligations, "sig": dep.sign(TAG_OBL, jh(obl_core))}
    with open(os.path.join(pack, "obligations.json"), 'w') as f:
        json.dump(obldoc, f)

    na = ts(-120) if runtime_expired else ts(600)
    keys = [{"key_id": rt.kid, "public_key": rt.pub.hex(), "role": "runtime",
             "not_before": ts(-1440), "not_after": na},
            {"key_id": dep.kid, "public_key": dep.pub.hex(), "role": "deployment",
             "not_before": ts(-14400), "not_after": ts(52560)}]
    keys_core = {"keys": keys}
    keysdoc = {"keys": keys, "sig": dep.sign(TAG_KEYS, jh(keys_core))}
    with open(os.path.join(pack, "keys.json"), 'w') as f:
        json.dump(keysdoc, f)

    signer = Signer(rt)
    events, ehashes, prev = [], [], "0" * 64

    def emit(etype, minute, body, payload_refs=None, obligation_ref=None):
        nonlocal prev
        core = {"spec_version": SPEC, "trace_id": trace_id, "seq": len(events),
                "ts_wall": ts(minute), "event_type": etype, "actor": "aetherlang.greek_tax_advisor",
                "body": body, "payload_refs": payload_refs or [],
                "obligation_ref": obligation_ref, "prev_hash": prev,
                "key_id": rt.kid}
        eh, sig = signer.sign_event(core)
        core["sig"] = sig
        events.append(core)
        ehashes.append(eh)
        prev = eh.hex()
        return core

    def checkpoint(minute, from_seq, gen_minute=None, anchor=True):
        root = merkle(ehashes[from_seq:])
        body = {"range": {"from_seq": from_seq, "to_seq": len(events) - 1},
                "merkle_root": root.hex(), "root_sig": rt.sign(TAG_CKPT, root)}
        if anchor:
            gt = ts(gen_minute if gen_minute is not None else minute)
            tok = anch.sign(TAG_ANCH, sha(root + gt.encode()))
            body["anchor"] = {"type": "rfc3161-sim", "gen_time": gt, "token": tok}
        else:
            body["anchor"] = None
        return emit("checkpoint", minute, body)

    def merkle(leaves):
        if not leaves:
            return sha(b'')
        if len(leaves) == 1:
            return sha(b'\x00' + leaves[0])
        k = 1
        while k * 2 < len(leaves):
            k *= 2
        return sha(b'\x01' + merkle(leaves[:k]) + merkle(leaves[k:]))

    emit("run_start", 0, {"obligation_manifest_hash": jh(obl_core).hex(),
                          "keys_manifest_hash": jh(keys_core).hex(),
                          "dossier_ref": "nous://dossier/demo/1",
                          "producer": "aetherlang-trace/0.2.0-ref",
                          "anchoring": "rfc3161-sim", "tolerance_s": 600})

    inp_h, _ = store_payload(pack, "content", jcs({"query": "refund for invoice 4411"}).encode())
    out_h, _ = store_payload(pack, "content", jcs({"reply": "processing refund"}).encode())
    emit("llm_call", 2, {"model": "claude-sonnet-4-6", "provider": "anthropic",
                         "params_hash": sha(b"t0.2").hex()},
         [{"role": "input", "class": "content", "hash": inp_h},
          {"role": "output", "class": "content", "hash": out_h}])

    asn1 = jcs({"amount_eur_cents": 42000, "human_approved": False}).encode()
    a1_h, _ = store_payload(pack, "evidence", asn1)
    emit("policy_check", 3, {"checker": "aetherlang.guard/3.1"},
         [{"role": "assignment", "class": "evidence", "hash": a1_h}],
         {"obligation_id": jh(PRED_LIMIT).hex(), "verdict": "pass", "assignment_hash": a1_h})

    erased_h = sha(secrets.token_bytes(16) + b"erased-content").hex()
    emit("tool_call", 4, {"tool": "mydata_submit", "adapter": "n8n/1.9"},
         [{"role": "input", "class": "content", "hash": erased_h}])

    checkpoint(5, 0)

    asn2 = jcs({"recipient_domain": "aade.gr", "vat_id": "GR123456789"}).encode()
    a2_h, _ = store_payload(pack, "evidence", asn2)
    emit("policy_check", 6, {"checker": "aetherlang.guard/3.1"},
         [{"role": "assignment", "class": "evidence", "hash": a2_h}],
         {"obligation_id": jh(PRED_ALLOW).hex(), "verdict": "pass", "assignment_hash": a2_h})

    op_h, _ = store_payload(pack, "evidence", jcs({"operator_hash": sha(b"op:hlia").hex(),
                                                   "decision": "approved"}).encode())
    emit("human_override", 8, {"decision": "approved"},
         [{"role": "decision", "class": "evidence", "hash": op_h}])

    emit("run_end", 9, {"outcome": "completed", "events_total": 7})
    checkpoint(9, 4)

    with open(os.path.join(pack, "trace.ndjson"), 'w') as f:
        for e in events:
            f.write(json.dumps(e, separators=(',', ':')) + "\n")

    with open(os.path.join(pack, "dossier_ref.json"), 'w') as f:
        json.dump({"ref": "nous://dossier/demo/1", "hash": sha(b"dossier-demo").hex()}, f)

    hashes = {}
    for fn in ("keys.json", "obligations.json"):
        with open(os.path.join(pack, fn), 'rb') as f:
            hashes[fn] = sha(f.read()).hex()
    with open(os.path.join(pack, "manifest.json"), 'w') as f:
        json.dump({"spec_version": SPEC, "anchoring": "rfc3161-sim", "tolerance_s": 600,
                   "trust_anchors": {"deployment_pub": dep.pub.hex(), "anchor_pub": anch.pub.hex()},
                   "hashes": hashes}, f)

    return {"events": events, "rt": rt, "anch": anch, "trace_id": trace_id}


def load_trace(pack):
    with open(os.path.join(pack, "trace.ndjson")) as f:
        return [json.loads(l) for l in f if l.strip()]


def write_trace(pack, events):
    with open(os.path.join(pack, "trace.ndjson"), 'w') as f:
        for e in events:
            f.write(json.dumps(e, separators=(',', ':')) + "\n")


def clone(src, dst):
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "vectors"
    os.makedirs(root, exist_ok=True)
    g = os.path.join(root, "golden")
    if os.path.exists(g):
        shutil.rmtree(g)
    ctx = build_golden(g)
    rt = ctx["rt"]

    v = os.path.join(root, "t01_edited_body")
    clone(g, v)
    ev = load_trace(v)
    ev[1]["body"]["model"] = "gpt-99"
    write_trace(v, ev)

    v = os.path.join(root, "t02_dropped_event")
    clone(g, v)
    ev = load_trace(v)
    del ev[3]
    write_trace(v, ev)

    v = os.path.join(root, "t03_reordered")
    clone(g, v)
    ev = load_trace(v)
    ev[2], ev[3] = ev[3], ev[2]
    write_trace(v, ev)

    v = os.path.join(root, "t04_post_anchor_forgery")
    clone(g, v)
    ev = load_trace(v)
    ev[1]["body"]["model"] = "forged-model"
    prev = "0" * 64
    ehashes = []
    for e in ev:
        e["prev_hash"] = prev
        core = {k: x for k, x in e.items() if k != "sig"}
        eh = jh(core)
        e["sig"] = rt.sign(TAG_EVENT, eh)
        if e["event_type"] == "checkpoint":
            fr = e["body"]["range"]["from_seq"]
            def mk(ls):
                if len(ls) == 1:
                    return sha(b'\x00' + ls[0])
                k = 1
                while k * 2 < len(ls):
                    k *= 2
                return sha(b'\x01' + mk(ls[:k]) + mk(ls[k:]))
            root_new = mk(ehashes[fr:])
            e["body"]["merkle_root"] = root_new.hex()
            e["body"]["root_sig"] = rt.sign(TAG_CKPT, root_new)
            core = {k: x for k, x in e.items() if k != "sig"}
            eh = jh(core)
            e["sig"] = rt.sign(TAG_EVENT, eh)
        ehashes.append(eh)
        prev = eh.hex()
    write_trace(v, ev)

    v = os.path.join(root, "t05_reused_salt")
    clone(g, v)
    pdir = os.path.join(v, "payloads", "content")
    ev = load_trace(v)
    keep_h = ev[1]["payload_refs"][0]["hash"]
    with open(os.path.join(pdir, keep_h)) as f:
        e0 = json.load(f)
    salt = bytes.fromhex(e0["salt"])
    data2 = jcs({"reply": "second payload same salt"}).encode()
    h2 = sha(salt + data2).hex()
    with open(os.path.join(pdir, h2), 'w') as f:
        json.dump({"salt": e0["salt"], "media_type": "application/json",
                   "data": base64.b64encode(data2).decode()}, f)
    ev[1]["payload_refs"][1]["hash"] = h2
    rechain(ev, rt, ctx["anch"])
    write_trace(v, ev)

    v = os.path.join(root, "t06_verdict_mismatch")
    clone(g, v)
    ev = load_trace(v)
    bad_asn = jcs({"amount_eur_cents": 99000, "human_approved": False}).encode()
    salt = secrets.token_bytes(16)
    bh = sha(salt + bad_asn).hex()
    edir = os.path.join(v, "payloads", "evidence")
    with open(os.path.join(edir, bh), 'w') as f:
        json.dump({"salt": salt.hex(), "media_type": "application/json",
                   "data": base64.b64encode(bad_asn).decode()}, f)
    ev[2]["payload_refs"][0]["hash"] = bh
    ev[2]["obligation_ref"]["assignment_hash"] = bh
    rechain(ev, rt, ctx["anch"])
    write_trace(v, ev)

    v = os.path.join(root, "t07_missing_evidence")
    clone(g, v)
    ev = load_trace(v)
    target = ev[2]["obligation_ref"]["assignment_hash"]
    os.remove(os.path.join(v, "payloads", "evidence", target))
    write_trace(v, ev)

    v = os.path.join(root, "t08_wrong_tag")
    clone(g, v)
    ev = load_trace(v)
    core = {k: x for k, x in ev[2].items() if k != "sig"}
    ev[2]["sig"] = rt.sign(TAG_CKPT, jh(core))
    write_trace(v, ev)

    v = os.path.join(root, "t09_expired_key")
    build_golden(v, runtime_expired=True)

    v = os.path.join(root, "t10_backdated")
    clone(g, v)
    ev = load_trace(v)
    ev[6]["ts_wall"] = "2026-01-05T09:00:00Z"
    rechain(ev, rt, ctx["anch"])
    write_trace(v, ev)

    v = os.path.join(root, "t11_float_signed")
    clone(g, v)
    ev = load_trace(v)
    ev[1]["body"]["temperature"] = 0.7
    core = {k: x for k, x in ev[1].items() if k != "sig"}
    ev[1]["sig"] = rt.sign(TAG_EVENT, jh(core))
    with open(os.path.join(v, "trace.ndjson"), 'w') as f:
        for e in ev:
            f.write(json.dumps(e, separators=(',', ':')) + "\n")

    v = os.path.join(root, "t12_truncated_tail")
    clone(g, v)
    ev = load_trace(v)
    write_trace(v, ev[:5])

    print("vectors written to", root)


def rechain(ev, rt, anch=None):
    prev = "0" * 64
    ehashes = []
    for e in ev:
        e["prev_hash"] = prev
        if e["event_type"] == "checkpoint":
            fr = e["body"]["range"]["from_seq"]
            def mk(ls):
                if len(ls) == 1:
                    return sha(b'\x00' + ls[0])
                k = 1
                while k * 2 < len(ls):
                    k *= 2
                return sha(b'\x01' + mk(ls[:k]) + mk(ls[k:]))
            root_new = mk(ehashes[fr:])
            e["body"]["merkle_root"] = root_new.hex()
            e["body"]["root_sig"] = rt.sign(TAG_CKPT, root_new)
            if anch is not None and e["body"].get("anchor"):
                gt = e["body"]["anchor"]["gen_time"]
                e["body"]["anchor"]["token"] = anch.sign(TAG_ANCH, sha(root_new + gt.encode()))
        core = {k: x for k, x in e.items() if k != "sig"}
        eh = jh(core)
        e["sig"] = rt.sign(TAG_EVENT, eh)
        ehashes.append(eh)
        prev = eh.hex()


if __name__ == "__main__":
    main()
