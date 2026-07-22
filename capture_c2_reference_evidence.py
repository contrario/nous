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

Longevity / rotation procedure: the token chains to the pinned Sigstore TSA
root, which expires 2035-04-06. When it expires -- or if it rotates earlier --
the offline crypto vectors begin to FAIL by design. That is the signal to
rotate the pinned root and RUN THIS SCRIPT WITH NO ARGUMENTS, which mints a
fresh token over the EXISTING bundle manifest.

Do NOT rebuild the bundle for a rotation. The bundle is sim-anchored (Ed25519
only) and has no dependency on any TSA root, and it doubles as the golden pack
for the wire-compatibility test (tests/test_wire_compat.py), which requires it
to stay byte-identical. The token commits to sha256(manifest.json), so a new
token over an unchanged bundle is all a rotation needs.

--rebuild-bundle exists for the separate case of deliberately moving that
baseline (e.g. a bundle-format change). It will fail test_golden_pack_is_
unmodified until the new baseline is recorded -- by design, so the move cannot
happen silently.
"""
import argparse
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

_ap = argparse.ArgumentParser(description="capture C2 reference evidence")
_ap.add_argument("--rebuild-bundle", action="store_true",
                 help="rebuild the trace bundle from scratch. This MOVES the "
                      "golden-pack baseline used by the wire-compatibility "
                      "test and must be a recorded decision, not routine. The "
                      "default refreshes only the TSA token, which is what a "
                      "pinned-root rotation actually requires.")
_args = _ap.parse_args()

ref_bundle = OUT / "trace_bundle"
if _args.rebuild_bundle or not (ref_bundle / "manifest.json").is_file():
    # a real, complete, C1-valid trace bundle
    work = Path(tempfile.mkdtemp())
    with trace_bridge.TraceBridge(str(work / "trace_bundle"), "actor", [],
                                  str(work / "keys")) as tb:
        tb.tool_call("t", "ad", input_bytes=b"{}")
        tb.checkpoint()
    src_bundle = work / "trace_bundle"
    _rebuilt = True
else:
    # DEFAULT: keep the committed bundle byte-for-byte; only the token is
    # refreshed. The bundle is sim-anchored (Ed25519 only) and has no
    # dependency on any TSA root, so a rotation does not invalidate it.
    src_bundle = ref_bundle
    _rebuilt = False
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

# persist the bundle tree only when it was rebuilt; otherwise leave the
# committed golden pack untouched (test_golden_pack_is_unmodified guards it)
if _rebuilt:
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
             "trace_bundle/manifest.json. That bundle is also the golden pack "
             "for wire-compatibility and MUST stay byte-identical. On a pinned-root "
             "rotation run capture_c2_reference_evidence.py with NO arguments: it "
             "mints a fresh token over the unchanged bundle. Do NOT rebuild "
             "the bundle."),
}
(OUT / "trace_bundle_c2_meta.json").write_text(
    json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")

files = sorted(p.relative_to(ref_bundle).as_posix()
               for p in ref_bundle.rglob("*") if p.is_file())
print("captured reference evidence under", OUT)
print("  bundle:", "REBUILT (golden-pack baseline moved)" if _rebuilt
      else "unchanged (token refreshed only)")
print("  bundle files:", files)
print("  anchored_bundle_sha256:", anchored[:16], "...")
print("  T_attest:", t_attest.isoformat())
print("  token:", len(token), "DER bytes; verifies against pinned root: True")
