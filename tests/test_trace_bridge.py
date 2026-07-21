#!/usr/bin/env python3
import json, os, shutil, subprocess, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from trace_bridge import TraceBridge, jcs, jcs_hash

VER = os.path.join(REPO, "trace", "reference", "verifier.py")
ROOT = "/tmp/trace_bridge_test"

PRED_LIMIT = {"op": "or", "args": [
    {"op": "<=", "left": {"var": "amount_eur_cents"}, "right": {"int": 50000}},
    {"var": "human_approved"}]}
PRED_ALLOW = {"op": "and", "args": [
    {"op": "in", "left": {"var": "recipient_domain"},
     "right": {"set": ["aade.gr", "efka.gov.gr"]}},
    {"op": "prefix_of", "left": {"str": "GR"}, "right": {"var": "vat_id"}}]}

OBLS = [
    {"label": "max_refund_without_human", "predicate": PRED_LIMIT,
     "variables": [{"name": "amount_eur_cents", "type": "int"},
                   {"name": "human_approved", "type": "bool"}],
     "assurance": "proved",
     "proof_artifact": jcs({"solver": "z3-4.13",
                            "predicate_id": jcs_hash(PRED_LIMIT).hex(),
                            "result": "unsat"}).encode(),
     "dossier_ref": "nous://dossier/demo/1"},
    {"label": "gov_recipient_allowlist", "predicate": PRED_ALLOW,
     "variables": [{"name": "recipient_domain", "type": "string"},
                   {"name": "vat_id", "type": "string"}],
     "assurance": "declared", "proof_artifact": None, "dossier_ref": None},
]


def run_verifier(pack):
    p = subprocess.run([sys.executable, VER, pack], capture_output=True, text=True)
    rep = json.loads(p.stdout)
    return p.returncode, rep


def build_pack(pack, keys):
    with TraceBridge(pack, "aetherlang.greek_tax_advisor", OBLS, keys,
                     dossier_ref="nous://dossier/demo/1") as tb:
        tb.llm_call("claude-sonnet-4-6", "anthropic", "deadbeef" * 8,
                    input_bytes=jcs({"query": "refund invoice 4411"}).encode(),
                    output_bytes=jcs({"reply": "processing"}).encode())
        v1 = tb.policy_check("max_refund_without_human",
                             {"amount_eur_cents": 42000, "human_approved": False})
        tb.tool_call("mydata_submit", "n8n/1.9",
                     input_bytes=jcs({"invoice": 4411}).encode())
        tb.checkpoint()
        v2 = tb.policy_check("gov_recipient_allowlist",
                             {"recipient_domain": "aade.gr",
                              "vat_id": "GR123456789"})
        tb.human_override("approved", {"operator": "hlia", "decision": "approved"})
    return v1, v2


def main():
    shutil.rmtree(ROOT, ignore_errors=True)
    keys = os.path.join(ROOT, "keys")

    pack = os.path.join(ROOT, "p_valid")
    v1, v2 = build_pack(pack, keys)
    code, rep = run_verifier(pack)
    print("T1 valid:", code, rep["verdict"], "verdicts:", v1, v2,
          "recomputed:", rep.get("recomputed"))
    assert code == 0 and rep["verdict"] == "VALID" and v1 == v2 == "pass"

    pack = os.path.join(ROOT, "p_fail_verdict")
    with TraceBridge(pack, "a", OBLS, keys) as tb:
        v = tb.policy_check("max_refund_without_human",
                            {"amount_eur_cents": 99000, "human_approved": False})
    code, rep = run_verifier(pack)
    print("T2 honest-fail:", code, rep["verdict"], "verdict:", v)
    assert code == 0 and v == "fail"

    pack = os.path.join(ROOT, "p_crash")
    child = (
        "import os, sys, time\n"
        "sys.path.insert(0, %r)\n"
        "from trace_bridge import TraceBridge\n"
        "tb = TraceBridge(%r, 'a', [], %r)\n"
        "tb.tool_call('t', 'ad', input_bytes=b'{}')\n"
        "print('READY', flush=True)\n"
        "time.sleep(30)\n" % (REPO, pack, keys))
    p = subprocess.Popen([sys.executable, "-c", child],
                         stdout=subprocess.PIPE, text=True)
    line = p.stdout.readline()
    assert "READY" in line
    p.kill(); p.wait()
    code, rep = run_verifier(pack)
    print("T3 crash:", code, rep["verdict"], rep.get("flags"))
    assert code == 10 and rep["verdict"] == "INTEGRITY-OK/INCOMPLETE"

    pack_t = os.path.join(ROOT, "p_tamper")
    shutil.copytree(os.path.join(ROOT, "p_valid"), pack_t)
    tf = os.path.join(pack_t, "trace.ndjson")
    ev = [json.loads(l) for l in open(tf) if l.strip()]
    ev[1]["body"]["model"] = "gpt-99"
    with open(tf, 'w') as f:
        for e in ev:
            f.write(json.dumps(e, separators=(',', ':')) + "\n")
    code, rep = run_verifier(pack_t)
    print("T4 tamper:", code, rep["verdict"])
    assert code == 20 and "SIG_INVALID" in rep["verdict"]

    pack_e = os.path.join(ROOT, "p_erase")
    build_pack(pack_e, keys)
    cdir = os.path.join(pack_e, "payloads", "content")
    victim = sorted(os.listdir(cdir))[0]
    os.remove(os.path.join(cdir, victim))
    code, rep = run_verifier(pack_e)
    print("T5 erase:", code, rep["verdict"], "erased:", len(rep.get("erased", [])))
    assert code == 0 and rep["verdict"] == "VALID" and len(rep["erased"]) == 1

    try:
        tb = TraceBridge(os.path.join(ROOT, "p_float"), "a", [], keys)
        tb._emit("tool_call", {"temperature": 0.7})
        print("T6 float: NOT refused"); sys.exit(1)
    except Exception as e:
        print("T6 float refused at producer:", type(e).__name__)

    print("ALL BRIDGE TESTS PASS")


if __name__ == "__main__":
    main()
