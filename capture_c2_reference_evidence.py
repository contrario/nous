#!/usr/bin/env python3
"""One-shot: capture C2 reference evidence for the hermetic conformance suite.

Run once (needs network). Produces, under tests/reference_evidence/:
  trace_bundle/                the COMPLETE, C1-valid trace bundle (manifest.json,
                               keys.json, obligations.json, trace.ndjson,
                               payloads/...). Copied verbatim by the offline
                               suite so the C1 integrity layer passes and the C2
                               leg actually runs.
  trace_bundle_c2_token.der    a real Sigstore production RFC 3161 token over the
                               exact bytes of trace_bundle/manifest.json
  trace_bundle_c2_meta.json    {anchored_bundle_sha256, t_attest_utc, tsa_url,
                               captured_at, pinned_root_not_after}

Provenance is deliberately transparent: this script is committed so the
reference evidence can be regenerated (e.g. after the pinned Sigstore TSA root
rotates). The offline conformance suite consumes these without network.

Longevity: the token chains to the pinned Sigstore TSA root, which expires
2035-04-06. When it does, the offline crypto vectors will begin to FAIL by
design -- the signal to rotate the pinned root and re-capture, not a defect.
"""
import base64
import datetime as dt
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
import trace_bridge
from tsa_client import anchor_timestamp, TSA_DEFAULT_URL

OUT = REPO / "tests" / "reference_evidence"
OUT.mkdir(parents=True, exist_ok=True)

# a real, complete, C1-valid trace bundle
work = Path(tempfile.mkdtemp())
with trace_bridge.TraceBridge(str(work / "trace_bundle"), "actor", [],
                              str(work / "keys")) as tb:
    tb.tool_call("t", "ad", input_bytes=b"{}")
    tb.checkpoint()
src_bundle = work / "trace_bundle"
bm = (src_bundle / "manifest.json").read_bytes()
anchored = hashlib.sha256(bm).hexdigest()

token = anchor_timestamp(timestamped_data=bm, base_url=TSA_DEFAULT_URL,
                         timeout_seconds=30)

# recover T_attest via the shipped verifier so meta is truthful
import dossier, importlib.util
d = Path(tempfile.mkdtemp()); ep = d / "_pa.py"
ep.write_text(dossier._PCE_ANCHOR_CHECK_EMBED)
spec = importlib.util.spec_from_file_location("_pa", ep)
pa = importlib.util.module_from_spec(spec); spec.loader.exec_module(pa)
ok, t_attest, errs = pa._pa_verify_rfc3161(token, bm)
assert ok, ("captured token does not verify against the pinned root", errs)

# persist the WHOLE bundle tree (C1 verifies every file)
ref_bundle = OUT / "trace_bundle"
if ref_bundle.exists():
    shutil.rmtree(ref_bundle)
shutil.copytree(src_bundle, ref_bundle)

(OUT / "trace_bundle_c2_token.der").write_bytes(token)
meta = {
    "anchored_bundle_sha256": anchored,
    "t_attest_utc": t_attest.isoformat(),
    "tsa_url": TSA_DEFAULT_URL,
    "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    "pinned_root_not_after": "2035-04-06T06:59:43+00:00",
    "note": ("Real Sigstore production RFC 3161 token over the exact bytes of "
             "trace_bundle/manifest.json. The complete trace_bundle/ tree is "
             "committed alongside so the offline C2 conformance suite copies a "
             "C1-valid bundle. Regenerate with capture_c2_reference_evidence.py "
             "after a pinned-root rotation."),
}
(OUT / "trace_bundle_c2_meta.json").write_text(
    json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")

files = sorted(p.relative_to(ref_bundle).as_posix()
               for p in ref_bundle.rglob("*") if p.is_file())
print("captured reference evidence under", OUT)
print("  bundle files:", files)
print("  anchored_bundle_sha256:", anchored[:16], "...")
print("  T_attest:", t_attest.isoformat())
print("  token:", len(token), "DER bytes; verifies against pinned root: True")
