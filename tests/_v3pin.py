"""NT-GATE-1 V3 test helper: the --expect-signer arguments for a test
whose own fixture signed the evidence and which does not exercise a
forged signer. The key is read from the artifact the fixture wrote, so
it is the fixture's key; a test about a forged or substituted signer
passes an explicit key instead, never this helper's.

# __nt_v3_classes_tests_v1__
"""
from __future__ import annotations

import json
from pathlib import Path


def _signer(path: Path) -> str:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return doc["signature"]["public_key_b64"]


def manifest_signer_args(d) -> list:
    """--expect-signer for a dossier or bundle: the manifest's key."""
    return ["--expect-signer", _signer(Path(d) / "manifest.json")]


def vsa_pin_args(d) -> list:
    """--expect-signer for a VSA bundle: the key the test provisioned
    into the emitted verifier, inline or through its registry."""
    import re
    d = Path(d)
    text = (d / "verify_vsa_offline.py").read_text(encoding="utf-8")
    m = re.search(r'(?m)^_PINNED_VSA_PUBKEY_B64 = "([^"]*)"$', text)
    if m and not m.group(1).startswith("__NOUS_VSA_PINNED"):
        return ["--expect-signer", m.group(1)]
    vid = re.search(r'(?m)^NOUS_VSA_VERIFIER_ID = "([^"]*)"$', text).group(1)
    reg = json.loads((d / "verifier-registry.json").read_text(
        encoding="utf-8"))
    pins = [p["public_key_b64"] for p in reg["verifier_pins"]
            if p.get("verifier_id") == vid]
    return ["--expect-signer", pins[0]]


def cert_signer_args(d) -> list:
    """--expect-signer for a conformance bundle: the certificate's key.
    V3 also requires the manifest to be signed by it."""
    return ["--expect-signer", _signer(Path(d) / "conformance.json")]


def key_public(path):
    """The Ed25519 public key of a key file a fixture created (for an
    auditor key passed to ndec.verify_ndec_file)."""
    import manifest
    return manifest.load_or_create_keypair(Path(path))[1]


def key_public_b64(path) -> str:
    """The same key as key_public, as the base64 an --expect-signer
    argument takes."""
    import manifest
    return manifest.public_key_b64(key_public(path))


def default_operator_key():
    """The private key `nous verify --smt` signs with when no
    --key-path is given (manifest.default_key_path()); a test that lets
    cmd_verify sign the manifest that way signs its certificate with the
    same key, as certify does by default."""
    import manifest
    return manifest.load_or_create_keypair(None)[0]


def conformance_pin_args(d) -> list:
    """--expect-signer (the certificate's key) and
    --expect-manifest-signer (the manifest's key) for a conformance
    bundle the fixture signed. Where a test re-signed the certificate
    with a forger's key to reach a later check, this pins that key, and
    the test says so."""
    d = Path(d)
    return ["--expect-signer", _signer(d / "conformance.json"),
            "--expect-manifest-signer", _signer(d / "manifest.json")]
