"""AN-GATE-1 D4, round 3b: K-JS.7 fill (R3B_PREDICTIONS 09a59131).

Cases for the region call sites that no strict case reached: the ndec
registry file, the continuity receipt (installed walk and verify_link),
the auditor witness keys of the envelope and closure witness checks,
the PCE anchor's Rekor leaf, the chain_net prior-link coverage cert and
the trace bundle's evidence assignment. Two cases document a shadow: a
re-signed payload is refused at the iss peek, before the site after the
signature check. Every key is made under tmp_path or in memory.

# __an_js_strict_f_tests_v1__
"""
from __future__ import annotations

import base64
import hashlib
import json
import shutil

import pytest

import manifest as mf
import test_an_js_strict as A
import test_an_js_strict_b as B
import test_an_js_strict_c as C
import test_an_js_strict_d as D

MUTATIONS = A.MUTATIONS


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    import dated_prices
    root = tmp_path_factory.mktemp("an_js_f")
    mp = pytest.MonkeyPatch()
    mp.delenv("XDG_DATA_HOME", raising=False)  # __an_js_tmp_keys_v1__
    dated_prices.use_dated_shipped_prices(root / "prices", mp)
    default_key = mf.default_key_path()
    yield root
    made = default_key.exists()
    mp.undo()
    assert not made, "a test created the default key " + str(default_key)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _last(text: str) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


# ------------------------------------------------ ndec.2: registry file


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_f_registry_file(env, tmp_path, monkeypatch, capsys, mutation):
    import ndec
    import test_s148_u2_ndec_registry as t
    from cryptography.hazmat.primitives.asymmetric import ed25519
    out = t._build_mini_ndec(tmp_path)
    reg_key = ed25519.Ed25519PrivateKey.generate()
    reg, log_allow = t._logged_registry(
        "VERIFY_OFFLINE_PY_FARKAS", "5.99.0", t._mini_sha(), reg_key)
    raw, key = B._plant_bytes(json.dumps(reg).encode("utf-8"), mutation)
    reg_path = tmp_path / "reg.json"
    reg_path.write_bytes(raw)
    t._install_pins(monkeypatch, reg_key, log_allow)
    capsys.readouterr()
    rc = ndec.verify_ndec_file(
        out, strict_canonical=True, registry_path=str(reg_path),
        public_key=t.key_public(tmp_path / "k.key"))
    cap = capsys.readouterr()
    C._refused_ndec((rc, cap.out, cap.err), "verifier-registry.json",
                    mutation, key)


# ------------------------------------- continuity receipt, installed walk


@pytest.fixture(scope="module")
def cont(env):
    import test_s178_checkpoint_leg as t
    sub = env / "cont"
    sub.mkdir()
    op, cp = t._keys(sub)
    return t._build_priced_ledger(sub, op, cp, ["0.10", "0.20"]), sub, cp


def _plant_receipt(d, part, mutation, cp=None):
    p = d / "000" / "receipt.jws"
    doc = json.loads(p.read_text(encoding="utf-8"))
    raw, key = B._plant_bytes(B._unb64url(doc[part]), mutation)
    doc[part] = B._b64url(raw)
    if cp is not None:
        doc["signature"] = B._b64url(cp.sign(
            (doc["protected"] + "." + doc["payload"]).encode("ascii")))
    p.write_text(json.dumps(doc), encoding="utf-8")
    return key


@pytest.mark.parametrize("mutation", MUTATIONS)
@pytest.mark.parametrize("part", ["protected", "payload"])
def test_f_continuity_cli_receipt(cont, tmp_path, part, mutation):
    ledger, sub, _cp = cont
    d = tmp_path / "ledger"
    shutil.copytree(ledger, d)
    key = _plant_receipt(d, part, mutation)
    res = C._cli(["continuity", "verify", "--ledger", d, "--json"]
                 + C._cont_args(sub))
    D._refused_json(res, "receipt.jws " + part, mutation, key)


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_f_continuity_cli_resigned_payload_shadow(cont, tmp_path,
                                                  mutation):
    # a payload re-signed by the counterparty is still refused at the
    # iss peek (cled.3); the walk never reaches cled.2 with it
    ledger, sub, cp = cont
    d = tmp_path / "ledger"
    shutil.copytree(ledger, d)
    key = _plant_receipt(d, "payload", mutation, cp)
    res = C._cli(["continuity", "verify", "--ledger", d, "--json"]
                 + C._cont_args(sub))
    D._refused_json(res, "receipt.jws payload [js:cled.3]", mutation, key)


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_f_continuity_text_resigned_payload_shadow(cont, tmp_path,
                                                   mutation):
    # the same in the continuity text: refused at cnt.6, before cnt.2
    import test_s178_checkpoint_leg as t
    ledger, sub, cp = cont
    d = tmp_path / "ledger"
    shutil.copytree(ledger, d)
    key = _plant_receipt(d, "payload", mutation, cp)
    vdir = tmp_path / "v"
    vdir.mkdir()
    script = t._emit(vdir)
    rc, so, se = C._script(script, [d] + C._cont_args(sub))
    assert rc == 1, (A.RAN, mutation, rc, so[-400:], se[-400:])
    C._named(_last(se), "receipt.jws payload [js:cnt.6]", mutation, key)


# ------------------------------- continuity receipt, verify_link directly


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_f_verify_link_payload(mutation):
    import continuity_ledger as cl
    import test_s176_continuity_ledger as t
    run = t._make_run(0, cl.GENESIS_PREV_RUN_DIGEST, t._h("head"))
    rec = dict(run["receipt"])
    raw, key = B._plant_bytes(cl._b64url_decode(rec["payload"]), mutation)
    rec["payload"] = t._b64url(raw)
    rec["signature"] = t._b64url(t._COUNTERPARTY.sign(
        (rec["protected"] + "." + rec["payload"]).encode("ascii")))
    exc = None
    try:
        cl.verify_link(cert=run["cert"], trace=run["trace"],
                       manifest=run["manifest"], link=run["link"],
                       receipt=rec, counterparty_public_key_pem=t._CP_PEM,
                       expected_issuer=t._ISS, expected_audience=t._AUD)
    except Exception as e:  # noqa: BLE001
        exc = e
    assert exc is not None, (A.RAN, mutation, "accepted")
    assert getattr(exc, "an_js_refusal", False), (A.RAN, mutation,
                                                  repr(exc))
    C._named(str(exc), "receipt.jws payload [js:cled.2]", mutation, key)


# ----------------------------------- ew.2: envelope witness auditor keys


@pytest.fixture(scope="module")
def ew_dossier(env):
    import test_s196_envelope_witness_producer as t
    if not t.TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    sub = env / "ew"
    sub.mkdir()
    note, lines, pins, store_path, _fan, wkeys = t._ceremony(sub)
    met = t.PROD.assemble_witness_sidecar(note, lines, pins, 2,
                                          store_path=store_path)
    met_bytes = json.dumps(met, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    return t._build_dossier(sub, met_bytes, "met"), wkeys


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_f_envelope_witness_keys(ew_dossier, tmp_path, mutation):
    from _v3pin import manifest_signer_args
    out, wkeys = ew_dossier
    d = tmp_path / "d"
    shutil.copytree(out, d)
    raw, key = B._plant_bytes(json.dumps(wkeys).encode("utf-8"), mutation)
    (d / "witness_keys.json").write_bytes(raw)
    rc, so, se = C._script(d / "verify_offline.py",
                           manifest_signer_args(d), cwd=d)
    assert rc == 1, (A.RAN, mutation, rc, so[-400:], se[-400:])
    lines = [ln for ln in se.splitlines() if "witness_keys.json" in ln]
    assert lines, (A.RAN, mutation, se[-600:])
    C._named(lines[-1], "witness_keys.json [js:ew.2]", mutation, key)


# ------------------------------------ cw.2: closure witness auditor keys


def _closure_doc():
    import test_s207_closure_witness as t
    root_hex = t._closure_root()
    cp, idx, size, proof, _root = t._witnessed_log(root_hex)
    return {"closure_witness_schema_version": 1, "policy_id": t.POLICY,
            "interval_start": t.START, "interval_end": t.END,
            "root": root_hex, "checkpoint_note": cp["envelope_note"],
            "log_index": idx, "tree_size": size,
            "inclusion_proof": [base64.b64encode(h).decode("ascii")
                                for h in proof],
            "threshold": 1, "witnesses": []}


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_f_closure_witness_keys(tmp_path, mutation):
    import dossier
    d = tmp_path / "cw"
    d.mkdir()
    text = ("#!/usr/bin/env python3\n" + D._canonical_region() + "\n\n\n"
            + dossier._CLOSURE_WITNESS_CHECK_EMBED
            + D.HARNESS_MAIN.replace("CHECK", "_check_closure_witness"))
    (d / "harness.py").write_text(text, encoding="utf-8")
    (d / "closure.witness.json").write_text(
        json.dumps(_closure_doc(), sort_keys=True), encoding="utf-8")
    D._bind(d, "closure.witness.json", "closure_witness_sha256")
    keys = {"witnesses": [{"name": "test-witness",
                           "pubkey_b64": base64.b64encode(
                               b"\x00" * 32).decode("ascii")}]}
    raw, key = B._plant_bytes(json.dumps(keys).encode("utf-8"), mutation)
    (d / "witness_keys.json").write_bytes(raw)
    rc, so, se = C._script(d / "harness.py", [d], cwd=d)
    assert rc == 1, (A.RAN, mutation, rc, so[-400:], se[-400:])
    C._named(_last(se), "witness_keys.json [js:cw.2]", mutation, key)


# ---------------------------------------------- pca.2: PCE anchor leaf


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_f_pce_anchor_leaf(tmp_path, capsys, mutation):
    import test_s191_pce_anchor_verifier as t
    if not (t._have("token.der") and t._have("data.bin")):
        pytest.skip("tsa fixtures not present")
    ns = t._load_embed()
    data, token = t._fx("data.bin"), t._fx("token.der")
    manifest = t._dossier(tmp_path, data, token, tlog_token=token,
                          tlog_leaf_sig=data)
    tlog = manifest["transparency_log"]
    raw, key = B._plant_bytes(base64.b64decode(tlog["body_b64"]), mutation)
    tlog["body_b64"] = base64.b64encode(raw).decode("ascii")
    capsys.readouterr()
    rc, _verdict = t._run(ns, tmp_path, manifest)
    cap = capsys.readouterr()
    assert rc == 1, (A.RAN, mutation, rc, cap.out[-400:], cap.err[-400:])
    C._named(_last(cap.err), "transparency_log leaf [js:pca.2]", mutation,
             key)


# ---------------------------------- pcv.1: chain_net prior-link coverage


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_f_prior_link_coverage(tmp_path, capsys, mutation):
    import test_s137_prior_link_coverage as t
    ns = t._embed_ns()
    source = t._src("500")
    far = t._bundle(source, "amount > 1000")
    raw, key = B._plant_bytes(json.dumps(far).encode("utf-8"), mutation)
    chain = tmp_path / "chain"
    chain.mkdir()
    src_bytes = source.encode("utf-8")
    (chain / "000_source.nous").write_bytes(src_bytes)
    (chain / "000_coverage.farkas.json").write_bytes(raw)
    link = {"coverage_farkas_sha256": _sha(raw),
            "source_sha256": _sha(src_bytes)}
    ordered = [("000_manifest.json", link), ("manifest.json (current)", {})]
    capsys.readouterr()
    rc = t._run(ns, tmp_path, ordered)
    cap = capsys.readouterr()
    assert rc == 1, (A.RAN, mutation, rc, cap.out[-400:], cap.err[-400:])
    C._named(_last(cap.err + "\n" + cap.out),
             "000_coverage.farkas.json [js:pcv.1]", mutation, key)


# ------------------------------------- tb.6: trace bundle assignment


@pytest.fixture(scope="module")
def tbw(env):
    import test_trace_bundle_dossier_e2e as t
    w = env / "tbw"
    w.mkdir()
    t._signed_source(w)
    return w


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_f_trace_bundle_assignment(tbw, tmp_path, monkeypatch, mutation):
    import dossier
    import test_trace_bundle_dossier_e2e as t
    import trace_bridge
    w = tmp_path / "w"
    shutil.copytree(tbw, w)
    real = trace_bridge.TraceBridge.store_payload
    seen = {}

    def planted(self, cls, data, media_type="application/json"):
        if cls == "evidence" and "raw" not in seen:
            seen["raw"], seen["key"] = B._plant_bytes(data, mutation)
            data = seen["raw"]
        return real(self, cls, data, media_type)
    monkeypatch.setattr(trace_bridge.TraceBridge, "store_payload", planted)
    t._attach_bundle_and_resign(w, w / "source.manifest.json")
    monkeypatch.setattr(trace_bridge.TraceBridge, "store_payload", real)
    assert "raw" in seen, "no evidence payload was stored"
    out = tmp_path / "out"
    dossier.build_dossier(w / "source.nous", output=out)
    rc, so, se = B._run_dossier(out, B._pin_of(B._priv(w / "op.key")))
    assert rc != 0, (A.RAN, mutation, rc, so[-400:], se[-400:])
    lines = [ln for ln in (se + "\n" + so).splitlines()
             if "[js:tb.6]" in ln or " assignment" in ln]
    assert lines, (A.RAN, mutation, so[-600:], se[-600:])
    C._named(lines[-1], "assignment [js:tb.6]", mutation, seen["key"])
