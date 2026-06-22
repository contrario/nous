#!/usr/bin/env python3
"""nous build-attest-verify -- offline dual-root convergence verifier (Option A).

# __s167_p2_verify_release_v1__

Given a local bundle directory for a published NOUS release, this verifies, with
cryptography + Python stdlib ONLY (no network, no sigstore/rfc3161 client as a
shipped dependency), that two INDEPENDENT verification roots converge on the
exact same artifact -- the release VSA payload:

  ROOT 1  operator endorsement : the release VSA is DSSE Ed25519-signed by the
          PINNED NOUS release-operator key, names the expected verifier identity
          and release-federation policy, and records verificationResult PASSED.
          (reuses build_vsa canonical PAE + constants -- no second impl.)

  ROOT 2  transparency log      : the VSA payload digest is included in the
          public, append-only Rekor v2 log under a checkpoint signed by the
          pinned log key, RFC3161-timestamped against the pinned TSA chain.
          (reuses rekor_v2_offline.load_pins + verify_entry -- the committed,
          self-tested orchestrator; no second impl.)

  BINDING the two roots are about the SAME bytes : the digest the log proves
          inclusion of equals sha256(the exact VSA payload ROOT 1 verified).
          Without this leg, ROOT 2 would only evidence "some entry exists," not
          "the log entry is about THIS VSA." This leg is the lynchpin.

Honest boundary: a PASS EVIDENCES (Ed25519 authenticity + append-only,
timestamped public-log inclusion + digest-equality binding) that the pinned
operator endorsed this VSA AND that endorsement's payload digest is publicly
logged. It does NOT re-derive the named federation attestations (SLSA build
provenance, PEP 740 publish attestation) -- that is the toolchain tier (fetch +
Sigstore). It PROVES nothing: "proves" is reserved for Z3 cost bounds and Farkas
certificates. NOUS is a monitor, not a guard.

The pinned release-operator public key below is the ONLY trust anchor for ROOT 1
and is a first-party, version-controlled constant -- it is NEVER read from the
bundle under verification (that would let an attacker who swaps the VSA also swap
the key). The pinned log/TSA roots for ROOT 2 come from the TUF-pinned
trusted_root.json + tsa_chain.pem the caller supplies as durable pins.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import build_vsa
import rekor_v2_offline

NOUS_RELEASE_PINNED_PUBKEY_B64 = "E3FNG9zFMRjhg/iVkOu9K3gH5mmG6Uwvdy8EvwHsYVo="

VSA_FILENAME = "build-vsa.intoto.json"
REKOR_FILENAME = "rekor-v2-bundle.json"
TRUSTED_ROOT_FILENAME = "trusted_root.json"
TSA_CHAIN_FILENAME = "tsa_chain.pem"

BOUNDARY = (
    "EVIDENCES (Ed25519 authenticity + append-only RFC3161-timestamped "
    "public-log inclusion + digest-equality binding): the pinned NOUS "
    "release-operator key endorsed this VSA AND the exact VSA payload digest is "
    "included in the public Rekor v2 transparency log -- two independent roots "
    "agreeing on the same artifact, re-checked fully offline with cryptography "
    "+ stdlib. Does NOT re-derive the named federation attestations (toolchain "
    "tier). PROVES nothing: 'proves' is reserved for Z3 cost bounds and Farkas "
    "certificates. NOUS is a monitor, not a guard."
)

_PASS = "PASS"
_FAIL = "FAIL"
_SKIP = "SKIP"

_VERSION_RE = re.compile(r"^nous_lang-(\d+\.\d+\.\d+)")


class ConvergenceInputError(ValueError):
    """Raised when the bundle/pins are missing or malformed (an environment
    problem, not a verification verdict). The message starts with the cause."""


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ConvergenceInputError(label + " not found: " + str(path))
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConvergenceInputError(
            label + " is not valid JSON: " + str(exc)
        ) from exc
    if not isinstance(obj, dict):
        raise ConvergenceInputError(label + " is not a JSON object")
    return obj


def _vsa_payload_bytes(envelope: dict[str, Any]) -> bytes:
    if envelope.get("payloadType") != build_vsa.DSSE_PAYLOAD_TYPE:
        raise ConvergenceInputError(
            "VSA payloadType is not " + build_vsa.DSSE_PAYLOAD_TYPE
        )
    payload_b64 = envelope.get("payload")
    if not isinstance(payload_b64, str) or not payload_b64:
        raise ConvergenceInputError("VSA payload missing or not a string")
    try:
        return base64.b64decode(payload_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise ConvergenceInputError(
            "VSA payload is not valid base64: " + str(exc)
        ) from exc


def _verify_operator_root(
    envelope: dict[str, Any], payload: bytes, pinned_pubkey_b64: str
) -> tuple[bool, str, dict[str, Any] | None]:
    """ROOT 1. Returns (ok, detail, verified_statement_or_None). Reuses
    build_vsa's canonical PAE + identity/policy constants (no second impl)."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )

    signatures = envelope.get("signatures")
    if not isinstance(signatures, list) or not signatures:
        return False, "VSA envelope has no signatures", None
    try:
        pinned = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(pinned_pubkey_b64, validate=True)
        )
    except (ValueError, TypeError) as exc:
        return False, "pinned release key is not valid: " + str(exc), None

    pae = build_vsa._pae(build_vsa.DSSE_PAYLOAD_TYPE, payload)
    verified = False
    for sig in signatures:
        if not isinstance(sig, dict):
            continue
        sig_b64 = sig.get("sig")
        if not isinstance(sig_b64, str) or not sig_b64:
            continue
        try:
            raw_sig = base64.b64decode(sig_b64, validate=True)
        except (ValueError, TypeError):
            continue
        try:
            pinned.verify(raw_sig, pae)
            verified = True
            break
        except InvalidSignature:
            continue
    if not verified:
        return (
            False,
            "DSSE signature does not verify against the pinned NOUS "
            "release-operator key",
            None,
        )

    try:
        statement = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return False, "verified VSA payload is not valid JSON: " + str(exc), None
    if not isinstance(statement, dict):
        return False, "verified VSA payload is not a JSON object", None

    if statement.get("_type") != build_vsa.IN_TOTO_STATEMENT_TYPE:
        return False, "statement _type is not in-toto Statement v1", None
    if statement.get("predicateType") != build_vsa.VSA_PREDICATE_TYPE:
        return False, "predicateType is not SLSA verification_summary v1", None
    predicate = statement.get("predicate")
    if not isinstance(predicate, dict):
        return False, "statement predicate is not an object", None

    verifier = predicate.get("verifier")
    if (
        not isinstance(verifier, dict)
        or verifier.get("id") != build_vsa.NOUS_RELEASE_VERIFIER_ID
    ):
        return (
            False,
            "predicate.verifier.id is not the pinned release-operator id",
            None,
        )

    policy = predicate.get("policy")
    pol_digest = (
        policy.get("digest", {}).get("sha256")
        if isinstance(policy, dict)
        else None
    )
    if pol_digest != build_vsa.build_policy_fingerprint():
        return (
            False,
            "policy.digest does not match the release-federation policy "
            "fingerprint (different or weaker policy than expected)",
            None,
        )

    if predicate.get("verificationResult") != "PASSED":
        return (
            False,
            "predicate.verificationResult is not PASSED",
            None,
        )

    return True, "operator endorsement authentic; identity+policy match", statement


def _extract_anchored_digest(rekor_bundle: dict[str, Any]) -> bytes:
    """BINDING input. Return the raw bytes of the digest the Rekor entry
    anchors, read from the SAME canonicalized_body the inclusion proof covers."""
    tle = rekor_bundle.get("transparency_log_entry")
    if not isinstance(tle, dict):
        raise ConvergenceInputError(
            "rekor bundle has no transparency_log_entry object"
        )
    cb_b64 = tle.get("canonicalized_body")
    if not isinstance(cb_b64, str) or not cb_b64:
        raise ConvergenceInputError("canonicalized_body missing or not a string")
    try:
        body = json.loads(base64.b64decode(cb_b64, validate=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ConvergenceInputError(
            "canonicalized_body is not base64 JSON: " + str(exc)
        ) from exc
    if not isinstance(body, dict) or body.get("kind") != "hashedrekord":
        raise ConvergenceInputError(
            "canonicalized_body is not a hashedrekord entry"
        )
    try:
        data = body["spec"]["hashedRekordV002"]["data"]
        algorithm = data["algorithm"]
        digest_b64 = data["digest"]
    except (KeyError, TypeError) as exc:
        raise ConvergenceInputError(
            "hashedrekord data.digest path absent: " + str(exc)
        ) from exc
    if algorithm != "SHA2_256":
        raise ConvergenceInputError(
            "anchored digest algorithm is not SHA2_256: " + repr(algorithm)
        )
    try:
        raw = base64.b64decode(digest_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise ConvergenceInputError(
            "anchored digest is not valid base64: " + str(exc)
        ) from exc
    if len(raw) != 32:
        raise ConvergenceInputError(
            "anchored digest is not 32 bytes: got " + str(len(raw))
        )
    return raw


def _derive_version(statement: dict[str, Any] | None) -> str | None:
    if not isinstance(statement, dict):
        return None
    subjects = statement.get("subject")
    if isinstance(subjects, list):
        for s in subjects:
            if isinstance(s, dict):
                name = s.get("name")
                if isinstance(name, str):
                    m = _VERSION_RE.match(name)
                    if m:
                        return m.group(1)
    return None


def verify_convergence(
    bundle_dir: str | Path,
    pins_dir: str | Path | None = None,
    *,
    pinned_pubkey_b64: str = NOUS_RELEASE_PINNED_PUBKEY_B64,
) -> dict[str, Any]:
    """Offline dual-root convergence over a local release bundle directory.

    Returns a clinical result dict (the matrix + evidence). Raises
    ConvergenceInputError on missing/malformed inputs; a verification FAIL is a
    legitimate result recorded in the dict, never an exception. Pure and
    offline: no network, cryptography + stdlib only (rekor_v2_offline is
    cryptography+stdlib; build_vsa is stdlib+cryptography).

    Exposed as the zero-trust agentic core: an agent may call this directly and
    branch on result["convergence"] before trusting a release artifact.
    """
    bdir = Path(bundle_dir)
    pdir = Path(pins_dir) if pins_dir is not None else bdir

    envelope = _load_json(bdir / VSA_FILENAME, "release VSA")
    rekor_bundle = _load_json(bdir / REKOR_FILENAME, "rekor v2 bundle")

    payload = _vsa_payload_bytes(envelope)
    vsa_payload_sha256 = hashlib.sha256(payload).hexdigest()

    legs: dict[str, dict[str, Any]] = {}

    root1_ok, root1_detail, statement = _verify_operator_root(
        envelope, payload, pinned_pubkey_b64
    )
    legs["root1_operator_ed25519"] = {
        "root": "operator",
        "status": _PASS if root1_ok else _FAIL,
        "detail": root1_detail,
    }

    pins_err = ""
    verdict: rekor_v2_offline.Verdict | None = None
    tr = pdir / TRUSTED_ROOT_FILENAME
    tsa = pdir / TSA_CHAIN_FILENAME
    if not tr.is_file():
        pins_err = "pinned " + TRUSTED_ROOT_FILENAME + " not found: " + str(tr)
    elif not tsa.is_file():
        pins_err = "pinned " + TSA_CHAIN_FILENAME + " not found: " + str(tsa)
    else:
        try:
            pins = rekor_v2_offline.load_pins(pdir)
            verdict = rekor_v2_offline.verify_entry(
                rekor_bundle, pins, verify_time=True
            )
        except rekor_v2_offline.VerificationError as exc:
            pins_err = "rekor v2 verification failed: " + str(exc)
        except (KeyError, ValueError, TypeError) as exc:
            pins_err = "rekor v2 bundle/pins malformed: " + str(exc)

    inclusion_ok = verdict is not None and verdict.included
    checkpoint_ok = verdict is not None and verdict.checkpoint_ok
    timestamp_ok = verdict is not None and verdict.timestamp is not None

    legs["root2_rekor_inclusion"] = {
        "root": "transparency_log",
        "status": _PASS if inclusion_ok else _FAIL,
        "detail": (
            "RFC6962 Merkle inclusion under signed checkpoint root"
            if inclusion_ok
            else (pins_err or "inclusion not established")
        ),
    }
    legs["root2_checkpoint_signature"] = {
        "root": "transparency_log",
        "status": _PASS if checkpoint_ok else _FAIL,
        "detail": (
            "C2SP signed-note checkpoint verified against pinned log key"
            if checkpoint_ok
            else (pins_err or "checkpoint signature not established")
        ),
    }
    legs["root2_rfc3161_timestamp"] = {
        "root": "transparency_log",
        "status": _PASS if timestamp_ok else _FAIL,
        "detail": (
            "RFC3161 token verified against pinned TSA chain; genTime "
            + verdict.timestamp.isoformat().replace("+00:00", "Z")
            if (timestamp_ok and verdict is not None and verdict.timestamp)
            else (pins_err or "timestamp not established")
        ),
    }

    anchored_hex = ""
    try:
        anchored = _extract_anchored_digest(rekor_bundle)
        anchored_hex = anchored.hex()
        binding_ok = anchored == hashlib.sha256(payload).digest()
        binding_detail = (
            "log-anchored digest == sha256(VSA payload)"
            if binding_ok
            else (
                "log-anchored digest != sha256(VSA payload): anchored="
                + anchored_hex[:16]
                + "... vsa="
                + vsa_payload_sha256[:16]
                + "..."
            )
        )
    except ConvergenceInputError as exc:
        binding_ok = False
        binding_detail = str(exc)
    legs["binding_log_to_vsa"] = {
        "root": "binding",
        "status": _PASS if binding_ok else _FAIL,
        "detail": binding_detail,
    }

    root2_ok = inclusion_ok and checkpoint_ok and timestamp_ok
    convergence_ok = root1_ok and root2_ok and binding_ok

    result: dict[str, Any] = {
        "schema": "nous.build_attest_verify.v1",
        "bundle_dir": str(bdir),
        "pins_dir": str(pdir),
        "version": _derive_version(statement),
        "convergence": _PASS if convergence_ok else _FAIL,
        "legs": legs,
        "evidence": {
            "vsa_payload_sha256": vsa_payload_sha256,
            "anchored_digest_sha256": anchored_hex,
            "log_index": verdict.log_index if verdict is not None else None,
            "tree_size": verdict.tree_size if verdict is not None else None,
            "leaf_hash": verdict.leaf_hash_hex if verdict is not None else None,
            "rfc3161_gen_time": (
                verdict.timestamp.isoformat().replace("+00:00", "Z")
                if (verdict is not None and verdict.timestamp is not None)
                else None
            ),
            "verifier_id": (
                statement.get("predicate", {}).get("verifier", {}).get("id")
                if isinstance(statement, dict)
                else None
            ),
            "verified_levels": (
                statement.get("predicate", {}).get("verifiedLevels")
                if isinstance(statement, dict)
                else None
            ),
            "pinned_release_pubkey_b64": pinned_pubkey_b64,
        },
        "boundary": BOUNDARY,
    }
    return result


def _render_matrix(result: dict[str, Any]) -> str:
    legs = result["legs"]
    ev = result["evidence"]
    order = [
        ("root1_operator_ed25519", "ROOT 1  operator Ed25519 endorsement"),
        ("root2_rekor_inclusion", "ROOT 2  rekor v2 Merkle inclusion"),
        ("root2_checkpoint_signature", "ROOT 2  checkpoint signature"),
        ("root2_rfc3161_timestamp", "ROOT 2  RFC3161 timestamp"),
        ("binding_log_to_vsa", "BINDING log digest == sha256(VSA)"),
    ]
    lines = []
    lines.append("NOUS build-attest-verify -- dual-root convergence (offline)")
    lines.append("  bundle: " + result["bundle_dir"])
    if result.get("version"):
        lines.append("  version: " + str(result["version"]))
    lines.append("")
    for key, label in order:
        leg = legs[key]
        lines.append("  [" + leg["status"] + "]  " + label)
        lines.append("          " + leg["detail"])
    lines.append("")
    lines.append("  CONVERGENCE: " + result["convergence"])
    lines.append("")
    lines.append("  evidence:")
    lines.append("    vsa_payload_sha256:     " + str(ev["vsa_payload_sha256"]))
    lines.append("    anchored_digest_sha256: " + str(ev["anchored_digest_sha256"]))
    lines.append("    log_index:              " + str(ev["log_index"]))
    lines.append("    tree_size:              " + str(ev["tree_size"]))
    lines.append("    leaf_hash:              " + str(ev["leaf_hash"]))
    lines.append("    rfc3161_gen_time:       " + str(ev["rfc3161_gen_time"]))
    lines.append("    verifier_id:            " + str(ev["verifier_id"]))
    lines.append("    verified_levels:        " + str(ev["verified_levels"]))
    lines.append("")
    lines.append("  " + result["boundary"])
    return "\n".join(lines)


def build_verify_release_parser(sub: "argparse._SubParsersAction") -> None:
    p = sub.add_parser(
        "build-attest-verify",
        help=(
            "offline dual-root convergence verify of a release bundle "
            "(operator Ed25519 + Rekor v2 transparency log)"
        ),
    )
    p.add_argument(
        "--bundle-dir",
        required=True,
        help=(
            "directory holding " + VSA_FILENAME + " + " + REKOR_FILENAME
            + " (and the pins, unless --pins-dir is given)"
        ),
    )
    p.add_argument(
        "--pins-dir",
        default=None,
        help=(
            "directory holding " + TRUSTED_ROOT_FILENAME + " + "
            + TSA_CHAIN_FILENAME + " (defaults to --bundle-dir)"
        ),
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="emit the result dict as JSON instead of the matrix",
    )
    p.set_defaults(func=cmd_verify_release)


def cmd_verify_release(args: argparse.Namespace) -> int:
    try:
        result = verify_convergence(args.bundle_dir, args.pins_dir)
    except ConvergenceInputError as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(_render_matrix(result))
    return 0 if result["convergence"] == _PASS else 1


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="nous build-attest-verify",
        description="offline dual-root convergence verifier (Option A)",
    )
    sub = parser.add_subparsers(dest="_cmd")
    build_verify_release_parser(sub)
    ns = parser.parse_args(
        ["build-attest-verify"] + (argv if argv is not None else sys.argv[1:])
    )
    return cmd_verify_release(ns)


if __name__ == "__main__":
    raise SystemExit(_main())
