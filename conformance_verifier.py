"""NOUS runtime conformance -- standalone offline verifier emitter.

Holds CONFORMANCE_VERIFY_OFFLINE_PY (a self-contained verifier that runs with
cryptography + stdlib only) and emit_conformance_verifier(output_dir), mirroring
the dossier.VERIFY_OFFLINE_PY string-constant pattern. The emitted verifier
checks a signed conformance certificate's authenticity and its binding to the
trace + manifest it certifies; it does NOT re-derive the SMT bounds (that is the
online toolchain path).

# __nous_conformance_verifier_module_v1__
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

CONFORMANCE_VERIFY_OFFLINE_PY: str = '#!/usr/bin/env python3\n"""Offline verification of a NOUS runtime conformance certificate.\n\nUsage: python3 verify_conformance_offline.py\nExit:  0 = PASS, 1 = FAIL, 2 = environment error.\nRequires: cryptography library (no NOUS install needed).\n\nExpects in the same directory:\n  conformance.json   the signed certificate\n  trace.json         the signed execution trace it certifies\n  manifest.json      the signed static-proof manifest it binds to\n\nChecks (cryptography + stdlib only):\n  1. certificate Ed25519 signature over its canonical body bytes\n  2. cert.trace_sha256 == sha256(trace canonical body)        cert<->trace bind\n  3. cert {source,smt_spec,pricing}_sha256 == manifest\'s      cert<->manifest bind\n  4. trace Ed25519 signature over its canonical body bytes\n  5. recorded six obligation booleans are consistent with conformant\n\nSCOPE: this proves the signed verdict is AUTHENTIC and BOUND to these exact\nartifacts -- not that the SMT bounds were re-derived (that needs the NOUS\ntoolchain; it is the online `nous conformance verify` path).\n"""\nfrom __future__ import annotations\n\nimport base64\nimport hashlib\nimport json\nimport sys\nfrom pathlib import Path\n\nROOT = Path(__file__).parent\n\n_BOOLS = (\n    "binding_ok",\n    "surface_ok",\n    "assumption_discharge_ok",\n    "bound_transfer_ok",\n    "authorization_ok",\n    "trace_signature_ok",\n)\n\n\ndef _fail(msg: str) -> int:\n    print("FAIL: " + msg, file=sys.stderr)\n    return 1\n\n\ndef _canonical_body_bytes(doc: dict) -> bytes:\n    body = {k: v for k, v in doc.items() if k != "signature"}\n    return json.dumps(\n        body, sort_keys=True, separators=(",", ":")\n    ).encode("utf-8")\n\n\ndef _verify_ed25519(pub_b64: str, sig_b64: str, body: bytes) -> bool:\n    from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n        Ed25519PublicKey,\n    )\n    from cryptography.exceptions import InvalidSignature\n    try:\n        pub = Ed25519PublicKey.from_public_bytes(\n            base64.b64decode(pub_b64, validate=True)\n        )\n        pub.verify(base64.b64decode(sig_b64, validate=True), body)\n        return True\n    except (InvalidSignature, ValueError):\n        return False\n\n\ndef main() -> int:\n    try:\n        import cryptography  # noqa: F401\n    except ImportError:\n        print(\n            "ERROR: cryptography library required.\\n"\n            "Install: pip install \'cryptography>=42\'",\n            file=sys.stderr,\n        )\n        return 2\n\n    cert_path = ROOT / "conformance.json"\n    trace_path = ROOT / "trace.json"\n    manifest_path = ROOT / "manifest.json"\n    for label, pth in (\n        ("conformance.json", cert_path),\n        ("trace.json", trace_path),\n        ("manifest.json", manifest_path),\n    ):\n        if not pth.is_file():\n            return _fail(label + " not found in " + str(ROOT))\n\n    try:\n        cert = json.loads(cert_path.read_text(encoding="utf-8"))\n        trace = json.loads(trace_path.read_text(encoding="utf-8"))\n        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))\n    except json.JSONDecodeError as e:\n        return _fail("JSON parse error: " + str(e))\n\n    # 1. certificate signature\n    csig = cert.get("signature")\n    if not isinstance(csig, dict):\n        return _fail("certificate has no signature block")\n    if csig.get("algorithm") != "ed25519":\n        return _fail("certificate signature algorithm is not ed25519")\n    cpub = csig.get("public_key_b64", "")\n    csigb = csig.get("signature_b64", "")\n    if not cpub or not csigb:\n        return _fail("certificate signature block incomplete")\n    if not _verify_ed25519(cpub, csigb, _canonical_body_bytes(cert)):\n        return _fail("certificate Ed25519 signature does NOT verify")\n    print("OK   certificate Ed25519 signature verified")\n\n    # 2. cert <-> trace binding\n    trace_sha = hashlib.sha256(_canonical_body_bytes(trace)).hexdigest()\n    if cert.get("trace_sha256") != trace_sha:\n        return _fail(\n            "cert.trace_sha256 != sha256(trace canonical body): "\n            "cert=" + str(cert.get("trace_sha256"))[:16] + "... "\n            "trace=" + trace_sha[:16] + "..."\n        )\n    print("OK   certificate is bound to this trace (sha256 match)")\n\n    # 3. cert <-> manifest binding\n    for fld in ("source_sha256", "smt_spec_sha256", "pricing_sha256"):\n        if cert.get(fld) != manifest.get(fld):\n            return _fail(\n                "cert." + fld + " != manifest." + fld + " "\n                "(certificate is not bound to this manifest)"\n            )\n    print("OK   certificate is bound to this manifest (3 shas match)")\n\n    # 4. trace signature\n    tsig = trace.get("signature")\n    if not isinstance(tsig, dict):\n        return _fail("trace has no signature block")\n    if tsig.get("algorithm") != "ed25519":\n        return _fail("trace signature algorithm is not ed25519")\n    if not _verify_ed25519(\n        tsig.get("public_key_b64", ""),\n        tsig.get("signature_b64", ""),\n        _canonical_body_bytes(trace),\n    ):\n        return _fail("trace Ed25519 signature does NOT verify")\n    print("OK   trace Ed25519 signature verified")\n\n    # 5. recorded booleans consistent with the conformant verdict\n    missing = [b for b in _BOOLS if b not in cert]\n    if missing:\n        return _fail("certificate missing obligation fields: " + str(missing))\n    derived = all(bool(cert[b]) for b in _BOOLS)\n    recorded = bool(cert.get("conformant"))\n    if derived != recorded:\n        return _fail(\n            "certificate conformant=" + str(recorded) + " but the six "\n            "obligations imply " + str(derived) + " (inconsistent record)"\n        )\n    print("OK   recorded verdict consistent with six obligations")\n\n    print()\n    verdict = "PASS" if recorded else "FAIL"\n    print("VERDICT: " + verdict + " (signed conformance certificate)")\n    print("  world:          " + str(cert.get("world_name", "?")))\n    print("  realized_total: " + str(cert.get("realized_total", "?"))\n          + " " + str(cert.get("cost_currency", "")))\n    print("  cost_cap:       " + str(cert.get("cost_cap", "?"))\n          + " " + str(cert.get("cost_currency", "")))\n    print("  conformant:     " + str(recorded))\n    print("  issued_utc:     " + str(cert.get("issued_utc", "?")))\n    print("  trace_sha256:   " + str(cert.get("trace_sha256", "?"))[:16]\n          + "...")\n    errs = cert.get("errors") or []\n    if errs:\n        print("  obligation failures:")\n        for e in errs:\n            print("    - " + str(e))\n    print()\n    print(\n        "SCOPE: authenticity + binding verified offline. SMT bound "\n        "re-derivation is the online `nous conformance verify` path."\n    )\n    return 0 if recorded else 1\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'


def emit_conformance_verifier(
    output_dir: str, anchored: bool = False  # __nous_conformance_anchored_verifier_v1__
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
