from __future__ import annotations
# __s180_p1_budget_in_tree__
# S180 PQ-durable transition: the budget Farkas cert is bound into a committed
# RFC 6962 leaf so the checkpoint root transitively commits it. Drop-when-absent
# keeps the un-priced checkpoint at tree_size n. Priced: tree_size n+1, root
# binds the budget, sidecar substitution flips the root and fails Lock 1, and
# the in-tree commitment cross-binds the extension cert. Reuses the s178 fixture.

import hashlib
import json

from test_s178_checkpoint_leg import (
    _keys,
    _build_priced_ledger,
    _run,
    _emit,
    _verify,
    _log_pub_pem,
)


def _parse_note(ledger):
    txt = (ledger / "checkpoint.note").read_text(encoding="utf-8")
    body = []
    for ln in txt.split("\n"):
        if ln == "":
            break
        body.append(ln)
    return body[0], int(body[1]), body[2], body[3:]


def test_unpriced_tree_size_and_pass(tmp_path):
    op, cp = _keys(tmp_path)
    ledger = _build_priced_ledger(tmp_path, op, cp, ["0.10", "0.20"])
    logkey = tmp_path / "logkey"
    assert _run(["continuity", "checkpoint", "--ledger", str(ledger),
                 "--log-key", str(logkey)]) == 0
    _origin, size, _root_b64, exts = _parse_note(ledger)
    assert size == 2
    assert not any(
        e.startswith("nous.aggregate.cost.farkas ") for e in exts)
    log_pub = _log_pub_pem(tmp_path, logkey)
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  log_pub=log_pub)
    assert res["rc"] == 0, res["err"]
    v = json.loads(res["out"])
    assert v["verdict"] == "PASS"
    assert v["checkpoint"]["tree_size"] == 2
    assert v["checkpoint"]["mode"] == "rail"


def test_priced_tree_size_n_plus_one(tmp_path):
    op, cp = _keys(tmp_path)
    ledger = _build_priced_ledger(tmp_path, op, cp, ["0.10", "0.20"])
    logkey = tmp_path / "logkey"
    assert _run(["continuity", "checkpoint", "--ledger", str(ledger),
                 "--log-key", str(logkey), "--budget", "1.00"]) == 0
    _origin, size, _root_b64, exts = _parse_note(ledger)
    assert size == 3
    assert any(
        e.startswith("nous.aggregate.cost.farkas ") for e in exts)
    log_pub = _log_pub_pem(tmp_path, logkey)
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  log_pub=log_pub)
    assert res["rc"] == 0, res["err"]
    v = json.loads(res["out"])
    assert v["verdict"] == "PASS"
    assert v["checkpoint"]["tree_size"] == 3
    assert v["checkpoint"]["mode"] == "budget"


def test_priced_root_differs_from_railonly(tmp_path):
    op, cp = _keys(tmp_path)
    ledger = _build_priced_ledger(tmp_path, op, cp, ["0.10", "0.20"])
    logkey = tmp_path / "logkey"
    assert _run(["continuity", "checkpoint", "--ledger", str(ledger),
                 "--log-key", str(logkey)]) == 0
    _o, _s, rail_root, _e = _parse_note(ledger)
    assert _run(["continuity", "checkpoint", "--ledger", str(ledger),
                 "--log-key", str(logkey), "--budget", "1.00"]) == 0
    _o2, _s2, priced_root, _e2 = _parse_note(ledger)
    assert rail_root != priced_root


def test_budget_substitution_flips_root_fails(tmp_path):
    op, cp = _keys(tmp_path)
    ledger = _build_priced_ledger(tmp_path, op, cp, ["0.10", "0.20"])
    logkey = tmp_path / "logkey"
    assert _run(["continuity", "checkpoint", "--ledger", str(ledger),
                 "--log-key", str(logkey), "--budget", "1.00"]) == 0
    side = ledger / "aggregate.cost.farkas.json"
    doc = json.loads(side.read_text(encoding="utf-8"))
    doc["caps"] = ["0.11", "0.20"]
    side.write_bytes(json.dumps(
        doc, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    log_pub = _log_pub_pem(tmp_path, logkey)
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  log_pub=log_pub)
    assert res["rc"] == 1
    v = json.loads(res["out"])
    assert v["verdict"] == "FAIL"


def test_crossbind_extension_cert_equals_sidecar_sha(tmp_path):
    op, cp = _keys(tmp_path)
    ledger = _build_priced_ledger(tmp_path, op, cp, ["0.10", "0.20"])
    logkey = tmp_path / "logkey"
    assert _run(["continuity", "checkpoint", "--ledger", str(ledger),
                 "--log-key", str(logkey), "--budget", "1.00"]) == 0
    _o, _s, _r, exts = _parse_note(ledger)
    bext = [e for e in exts
            if e.startswith("nous.aggregate.cost.farkas ")][0]
    kv = dict(t.split("=", 1) for t in bext.split(" ")[2:] if "=" in t)
    cert = kv["cert"]
    side = (ledger / "aggregate.cost.farkas.json").read_bytes()
    assert hashlib.sha256(side).hexdigest() == cert
