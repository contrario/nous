"""C3 conformance: production RFC 3161 checkpoint anchors (SPEC 10.1/10.2/10.3).

offline: default sim unchanged + flagged, outage degrades to unanchored,
         unsupported backend refused, missing pinned roots fail closed.
live:    a real TSA anchor verifies end to end and carries no Producer-declared
         time.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

pytest.importorskip("trace_bridge")
from trace_bridge import TraceBridge, TraceBridgeError
import dossier


def _verifier():
    vp = _REPO / "trace" / "reference" / "verifier.py"
    spec = importlib.util.spec_from_file_location("_rv_t", vp)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _pinned_roots_pem(tmp_path):
    d = Path(tempfile.mkdtemp())
    ep = d / "_pa.py"
    ep.write_text(dossier._PCE_ANCHOR_CHECK_EMBED)
    sp = importlib.util.spec_from_file_location("_pa_t", ep)
    pa = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(pa)
    p = tmp_path / "tsa_roots.pem"
    p.write_text("".join(pa._PA_KNOWN_TSA_ROOT_CERTS))
    return p


@pytest.mark.offline
def test_default_sim_unchanged_and_flagged(tmp_path):
    pack = tmp_path / "pack"
    with TraceBridge(str(pack), "actor", [], str(tmp_path / "k")) as br:
        br.tool_call("t", "ad", input_bytes=b"{}")
    man = json.loads((pack / "manifest.json").read_text())
    assert man["anchoring"] == "rfc3161-sim"
    code, rep = _verifier().verify_pack(str(pack))
    assert code == 0 and rep["verdict"] == "VALID"
    assert rep["anchors"][0]["type"] == "rfc3161-sim"
    # SPEC 10.1: the sim backend must be flagged when not marked test_vector
    assert [f for f in rep["flags"] if "TEST backend" in f], rep["flags"]


@pytest.mark.offline
def test_unsupported_backend_refused(tmp_path):
    with pytest.raises(TraceBridgeError) as e:
        TraceBridge(str(tmp_path / "p"), "actor", [], str(tmp_path / "k"),
                    anchoring="rekor")
    assert "unsupported anchoring backend" in str(e.value)


@pytest.mark.offline
def test_tsa_outage_degrades_to_unanchored(tmp_path):
    # SPEC 10.2: a TSA failure must not fail the run.
    pack = tmp_path / "pack"
    with TraceBridge(str(pack), "actor", [], str(tmp_path / "k"),
                     anchoring="rfc3161",
                     tsa_url="http://127.0.0.1:9/no-tsa-here",
                     tsa_timeout_s=2) as br:
        br.tool_call("t", "ad", input_bytes=b"{}")
    # the final checkpoint runs in finalize(), i.e. on exit -- read after
    failures = list(br.anchor_failures)
    assert failures, "the outage must be recorded on the bridge"
    events = [json.loads(l) for l in
              (pack / "trace.ndjson").read_text().splitlines() if l.strip()]
    ckpts = [e for e in events if e["event_type"] == "checkpoint"]
    assert ckpts and all(e["body"]["anchor"] is None for e in ckpts)
    code, rep = _verifier().verify_pack(str(pack))
    assert code == 10, (code, rep["verdict"])          # gap, not a crash
    assert any("unanchored" in f for f in rep["flags"]), rep["flags"]


@pytest.mark.offline
def test_rfc3161_without_pinned_roots_fails_closed(tmp_path):
    # Build a pack with a syntactically valid but unverifiable rfc3161 anchor
    # and confirm the verifier refuses when no roots resolve.
    pack = tmp_path / "pack"
    with TraceBridge(str(pack), "actor", [], str(tmp_path / "k")) as br:
        br.tool_call("t", "ad", input_bytes=b"{}")
    lines = (pack / "trace.ndjson").read_text().splitlines()
    events = [json.loads(l) for l in lines if l.strip()]
    for e in events:
        if e["event_type"] == "checkpoint":
            e["body"]["anchor"] = {"type": "rfc3161", "token_b64": "AAAA"}
    (pack / "trace.ndjson").write_text(
        "".join(json.dumps(e, separators=(",", ":")) + "\n" for e in events))
    ver = _verifier()
    os.environ.pop("NOUS_TSA_ROOTS", None)
    with pytest.raises(ver.VErr) as e:
        ver.verify_pack(str(pack))
    # either no roots, or the chain check fails -- both are fail-closed
    assert e.value.reason in ("ANCHOR_INVALID", "SIG_INVALID"), e.value.reason


@pytest.mark.live
def test_production_anchor_end_to_end(tmp_path):
    pack = tmp_path / "pack"
    with TraceBridge(str(pack), "actor", [], str(tmp_path / "k"),
                     anchoring="rfc3161") as br:
        br.tool_call("t", "ad", input_bytes=b"{}")
    man = json.loads((pack / "manifest.json").read_text())
    assert man["anchoring"] == "rfc3161"
    events = [json.loads(l) for l in
              (pack / "trace.ndjson").read_text().splitlines() if l.strip()]
    ck = [e for e in events if e["event_type"] == "checkpoint"][-1]
    anchor = ck["body"]["anchor"]
    assert anchor["type"] == "rfc3161" and "token_b64" in anchor
    # the Producer must NOT declare the time; it is recovered from the token
    assert "gen_time" not in anchor
    roots = _pinned_roots_pem(tmp_path)
    os.environ["NOUS_TSA_ROOTS"] = str(roots)
    try:
        code, rep = _verifier().verify_pack(str(pack))
    finally:
        os.environ.pop("NOUS_TSA_ROOTS", None)
    assert code == 0 and rep["verdict"] == "VALID", rep
    a = [x for x in rep["anchors"] if x["type"] == "rfc3161"][0]
    assert a["gen_time"] and a["tsa_root_provenance"] == "auditor-pinned"
    assert not [f for f in rep["flags"] if "TEST backend" in f]
