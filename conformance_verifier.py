"""Standalone offline-verifier template for NOUS conformance certs.

# __phase2_stage5b_tpl_v1__
This module exports CONFORMANCE_VERIFY_OFFLINE_PY (a Python source
string) and emit_conformance_verifier (writes it to disk). The template
is v1/v2-aware: it reads cert.certificate_schema_version and selects the
six-obligation (v1) or seven-obligation (v2, with sequence_ok) check.

The anchored (Rekor v2) verifier is assembled by
offline_verifier_builder.build_conformance_verifier_v2 -- a separate path
with the same v1/v2 dispatch.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

CONFORMANCE_VERIFY_OFFLINE_PY: str = '#!/usr/bin/env python3\n"""Offline verification of a NOUS runtime conformance certificate.\n\nUsage: python3 verify_conformance_offline.py\nExit:  0 = PASS, 1 = FAIL, 2 = environment error.\nRequires: cryptography library (no NOUS install needed).\n\nExpects in the same directory:\n  conformance.json   the signed certificate\n  trace.json         the signed execution trace it certifies\n  manifest.json      the signed static-proof manifest it binds to\n\nChecks (cryptography + stdlib only):\n  1. certificate Ed25519 signature over its canonical body bytes\n  2. cert.trace_sha256 == sha256(trace canonical body)        cert<->trace bind\n  3. cert {source,smt_spec,pricing}_sha256 == manifest\'s      cert<->manifest bind\n  4. trace Ed25519 signature over its canonical body bytes\n  5. recorded obligation booleans consistent with conformant\n     (six obligations for schema v1; seven for v2 with sequence_ok)\n\nSCOPE: this proves the signed verdict is AUTHENTIC and BOUND to these exact\nartifacts -- not that the SMT bounds were re-derived (that needs the NOUS\ntoolchain; it is the online `nous conformance verify` path).\n"""\nfrom __future__ import annotations\n\nimport base64\nimport hashlib\nimport json\nimport sys\nfrom pathlib import Path\n\nROOT = Path(__file__).parent\n\n_BOOLS_V1 = (\n    "binding_ok",\n    "surface_ok",\n    "assumption_discharge_ok",\n    "bound_transfer_ok",\n    "authorization_ok",\n    "trace_signature_ok",\n)\n\n_BOOLS_V2 = _BOOLS_V1 + ("sequence_ok",)\n\n\ndef _bools_for(schema_version: int) -> tuple:\n    return _BOOLS_V2 if schema_version >= 2 else _BOOLS_V1\n\n\ndef _fail(msg: str) -> int:\n    print("FAIL: " + msg, file=sys.stderr)\n    return 1\n\n\ndef _canonical_body_bytes(doc: dict) -> bytes:\n    body = {k: v for k, v in doc.items() if k != "signature"}\n    return json.dumps(\n        body, sort_keys=True, separators=(",", ":")\n    ).encode("utf-8")\n\n\ndef _cert_canonical_body_bytes(doc: dict) -> bytes:\n    body = {\n        k: v for k, v in doc.items()\n        if k not in ("signature", "transparency_log")\n    }\n    if int(body.get("certificate_schema_version", 1)) < 2:\n        body.pop("sequence_ok", None)\n    return json.dumps(\n        body, sort_keys=True, separators=(",", ":")\n    ).encode("utf-8")\n\n\ndef _verify_ed25519(pub_b64: str, sig_b64: str, body: bytes) -> bool:\n    from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n        Ed25519PublicKey,\n    )\n    from cryptography.exceptions import InvalidSignature\n    try:\n        pub = Ed25519PublicKey.from_public_bytes(\n            base64.b64decode(pub_b64, validate=True)\n        )\n        pub.verify(base64.b64decode(sig_b64, validate=True), body)\n        return True\n    except (InvalidSignature, ValueError):\n        return False\n\n\ndef main() -> int:\n    try:\n        import cryptography  # noqa: F401\n    except ImportError:\n        print(\n            "ERROR: cryptography library required.\\n"\n            "Install: pip install \\\'cryptography>=42\\\'",\n            file=sys.stderr,\n        )\n        return 2\n\n    cert_path = ROOT / "conformance.json"\n    trace_path = ROOT / "trace.json"\n    manifest_path = ROOT / "manifest.json"\n    for label, pth in (\n        ("conformance.json", cert_path),\n        ("trace.json", trace_path),\n        ("manifest.json", manifest_path),\n    ):\n        if not pth.is_file():\n            return _fail(label + " not found in " + str(ROOT))\n\n    try:\n        cert = json.loads(cert_path.read_text(encoding="utf-8"))\n        trace = json.loads(trace_path.read_text(encoding="utf-8"))\n        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))\n    except json.JSONDecodeError as e:\n        return _fail("JSON parse error: " + str(e))\n\n    schema_v = int(cert.get("certificate_schema_version", 1))\n    bools = _bools_for(schema_v)\n\n    csig = cert.get("signature")\n    if not isinstance(csig, dict):\n        return _fail("certificate has no signature block")\n    if csig.get("algorithm") != "ed25519":\n        return _fail("certificate signature algorithm is not ed25519")\n    cpub = csig.get("public_key_b64", "")\n    csigb = csig.get("signature_b64", "")\n    if not cpub or not csigb:\n        return _fail("certificate signature block incomplete")\n    if not _verify_ed25519(cpub, csigb, _cert_canonical_body_bytes(cert)):\n        return _fail("certificate Ed25519 signature does NOT verify")\n    print("OK   certificate Ed25519 signature verified")\n\n    trace_sha = hashlib.sha256(_canonical_body_bytes(trace)).hexdigest()\n    if cert.get("trace_sha256") != trace_sha:\n        return _fail(\n            "cert.trace_sha256 != sha256(trace canonical body): "\n            "cert=" + str(cert.get("trace_sha256"))[:16] + "... "\n            "trace=" + trace_sha[:16] + "..."\n        )\n    print("OK   certificate is bound to this trace (sha256 match)")\n\n    for fld in ("source_sha256", "smt_spec_sha256", "pricing_sha256"):\n        if cert.get(fld) != manifest.get(fld):\n            return _fail(\n                "cert." + fld + " != manifest." + fld + " "\n                "(certificate is not bound to this manifest)"\n            )\n    print("OK   certificate is bound to this manifest (3 shas match)")\n\n    tsig = trace.get("signature")\n    if not isinstance(tsig, dict):\n        return _fail("trace has no signature block")\n    if tsig.get("algorithm") != "ed25519":\n        return _fail("trace signature algorithm is not ed25519")\n    if not _verify_ed25519(\n        tsig.get("public_key_b64", ""),\n        tsig.get("signature_b64", ""),\n        _canonical_body_bytes(trace),\n    ):\n        return _fail("trace Ed25519 signature does NOT verify")\n    print("OK   trace Ed25519 signature verified")\n\n    missing = [b for b in bools if b not in cert]\n    if missing:\n        return _fail("certificate missing obligation fields: " + str(missing))\n    derived = all(bool(cert[b]) for b in bools)\n    recorded = bool(cert.get("conformant"))\n    if derived != recorded:\n        return _fail(\n            "certificate conformant=" + str(recorded) + " but the "\n            + str(len(bools)) + " obligations imply " + str(derived)\n            + " (inconsistent record)"\n        )\n    print(\n        "OK   recorded verdict consistent with " + str(len(bools))\n        + " obligations (schema v" + str(schema_v) + ")"\n    )\n\n    print()\n    verdict = "PASS" if recorded else "FAIL"\n    print("VERDICT: " + verdict + " (signed conformance certificate)")\n    print("  world:          " + str(cert.get("world_name", "?")))\n    print("  realized_total: " + str(cert.get("realized_total", "?"))\n          + " " + str(cert.get("cost_currency", "")))\n    print("  cost_cap:       " + str(cert.get("cost_cap", "?"))\n          + " " + str(cert.get("cost_currency", "")))\n    print("  conformant:     " + str(recorded))\n    print("  schema_version: " + str(schema_v))\n    print("  issued_utc:     " + str(cert.get("issued_utc", "?")))\n    print("  trace_sha256:   " + str(cert.get("trace_sha256", "?"))[:16]\n          + "...")\n    errs = cert.get("errors") or []\n    if errs:\n        print("  obligation failures:")\n        for e in errs:\n            print("    - " + str(e))\n    print()\n    print(\n        "SCOPE: authenticity + binding verified offline. SMT bound "\n        "re-derivation is the online `nous conformance verify` path."\n    )\n    return 0 if recorded else 1\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'


def emit_conformance_verifier(
    output_dir: str, anchored: bool = False,  # __nous_conformance_anchored_verifier_v1__
) -> Path:
    """Write verify_conformance_offline.py (0644) into output_dir; return path.

    anchored=False: standalone Ed25519 + binding verifier (this module's
    string template; no Rekor dependency).
    anchored=True: assembled Rekor v2 conformance verifier with the pinned
    production KNOWN_REKOR_V2_LOG_KEYS allowlist.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / "verify_conformance_offline.py"
    if anchored:
        from offline_verifier_builder import build_conformance_verifier_v2
        from rekor_verify_v2 import KNOWN_REKOR_V2_LOG_KEYS
        payload = build_conformance_verifier_v2(
            repr(KNOWN_REKOR_V2_LOG_KEYS)
        )
    else:
        payload = CONFORMANCE_VERIFY_OFFLINE_PY
    fd, tmp = tempfile.mkstemp(dir=str(out), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.chmod(tmp, 0o644)
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return target
