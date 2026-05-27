# NOUS runtime conformance demo bundle

This directory contains the complete, reproducible artifacts for a
single live-anchored NOUS runtime conformance certificate.

**Log index (Sigstore Rekor v2):** 4679350
**Anchored:** 2026-05-27T19:37:09+00:00
**NOUS version:** 5.13.1

## Files

- `conformance.json` -- signed runtime conformance certificate (anchored)
- `trace.json` -- signed execution trace this certifies
- `manifest.json` -- signed static-proof manifest the trace runs against
- `source.nous` -- the NOUS program (souls-bearing, cost-capped)
- `pricing.toml` -- the resolved pricing table used by the proof
- `verify_conformance_offline.py` -- the offline verifier (cryptography + stdlib)

## How to verify yourself offline

```bash
pip install cryptography>=42
python3 verify_conformance_offline.py
```

The verifier checks: certificate Ed25519 signature, certificate-to-trace and certificate-to-manifest bindings, trace Ed25519 signature, recorded verdict consistency, and the full Rekor v2 inclusion proof over the certificate body.

Expected output: `VERDICT: PASS` with `conformant: True` and the Rekor v2 anchor verified.

No NOUS install required.
