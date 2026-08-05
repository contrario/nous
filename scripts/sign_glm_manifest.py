from __future__ import annotations

import argparse
import base64
import json
import os
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import glm_manifest

# __s150_u1_sign_glm_manifest_tool_v1__


class CeremonyError(Exception):
    """An operator-ceremony precondition failed."""


def _atomic_write(path: Path, data: bytes, mode: int) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load_operator_key(key_path: Path) -> Ed25519PrivateKey:
    if not key_path.is_file():
        raise CeremonyError(
            "operator key not found at " + str(key_path)
            + " (generate it manually with O_EXCL; this tool never creates it)"
        )
    key = serialization.load_pem_private_key(
        key_path.read_bytes(), password=None
    )
    if not isinstance(key, Ed25519PrivateKey):
        raise CeremonyError(
            "key at " + str(key_path) + " is not an Ed25519 private key"
        )
    return key


def _public_key_b64(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return base64.b64encode(raw).decode("ascii")


# __s298_ceremony_guards_v1__
_GLM_HEX = "0123456789abcdef"


def _is_glm_hex64(value: object) -> bool:
    """True for exactly 64 lowercase hex digits."""
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(c in _GLM_HEX for c in value)
    )


def _is_iso_date(value: object) -> bool:
    """True for exactly YYYY-MM-DD. valid_from is concatenated into
    generated_at, never parsed, so a timestamp would yield ...ZT00:00:00Z."""
    if not isinstance(value, str) or len(value) != 10:
        return False
    if value[4] != "-" or value[7] != "-":
        return False
    return value[:4].isdigit() and value[5:7].isdigit() and value[8:].isdigit()


def _check_source_is_sealed(source: dict, source_text: str) -> None:
    """G1: recompute the predecessor digest instead of trusting the declared
    value. A stale or tampered source would otherwise put a false
    supersedes_digest inside a freshly signed artifact, and the verifier that
    exists does not check supersedes_digest at all."""
    block = source.get("manifest_digest")
    declared = block.get("value") if isinstance(block, dict) else None
    if not _is_glm_hex64(declared):
        raise CeremonyError(
            "source manifest_digest.value is not 64 lowercase hex digits; "
            "an unsealed template cannot be a predecessor"
        )
    try:
        computed = glm_manifest.compute_glm_digest(source_text)
    except glm_manifest.GlmManifestError as exc:
        raise CeremonyError(
            "source manifest is not digest-computable as served ("
            + str(exc) + "); it cannot be a predecessor"
        ) from exc
    if computed != declared:
        raise CeremonyError(
            "source manifest_digest.value does not match the source bytes "
            "(declared " + declared[:16] + "..., computed " + computed[:16]
            + "...); the supersedes chain would carry a false digest"
        )


def _check_version_advances(source: dict, new_version: object) -> None:
    """G4: two bodies do not carry one version."""
    if not isinstance(new_version, str) or not new_version:
        raise CeremonyError("new_version is missing")
    owner = source.get("owner")
    current = owner.get("version") if isinstance(owner, dict) else None
    if isinstance(current, str) and current == new_version:
        raise CeremonyError(
            "new_version " + repr(new_version) + " equals the source "
            "owner.version; a successor must carry a different version"
        )


def _transform_source(
    source: dict,
    *,
    new_version: str,
    valid_from: str,
    supersedes_url: str,
) -> dict:
    digest_block = source.get("manifest_digest")
    if not isinstance(digest_block, dict):
        raise CeremonyError("source manifest has no manifest_digest object")
    predecessor_digest = digest_block.get("value")
    if not isinstance(predecessor_digest, str) or not predecessor_digest:
        raise CeremonyError("source manifest_digest.value is missing")
    if not _is_glm_hex64(predecessor_digest):
        raise CeremonyError(
            "source manifest_digest.value is not 64 lowercase hex digits: "
            + repr(predecessor_digest[:32])
            + "; a placeholder cannot become a supersedes_digest"
        )

    owner = source.get("owner")
    if not isinstance(owner, dict):
        raise CeremonyError("source manifest has no owner object")

    sig_block = source.get("manifest_signature")
    if not isinstance(sig_block, dict):
        raise CeremonyError("source manifest has no manifest_signature object")

    if not _is_iso_date(valid_from):
        raise CeremonyError(
            "valid_from must be YYYY-MM-DD, got " + repr(valid_from)
            + "; it is concatenated into generated_at, not parsed"
        )
    owner["version"] = new_version
    source["generated_at"] = valid_from + "T00:00:00Z"
    source["valid_from"] = valid_from
    source["supersedes"] = supersedes_url
    source["supersedes_digest"] = predecessor_digest

    digest_block["canonicalization_method"] = (
        "SHA-256 over the manifest text as served with manifest_digest.value "
        "set to the placeholder string <computed-at-publish-time> and, when a "
        "signature is present, manifest_signature.value set to the placeholder "
        "string <signed-at-publish-time>, during computation. A verifier "
        "reverses both substitutions on the served bytes and recomputes."
    )

    sig_block["type"] = "ed25519"
    sig_block["public_key"] = None
    sig_block["value"] = None
    sig_block["note"] = (
        "Ed25519 signature over the 32-byte manifest digest, binding the "
        "digest to the signer identity in public_key (raw key, base64). "
        "Independently checkable with a cryptography library and a standard "
        "runtime only. The digest verifies content integrity; this signature "
        "verifies authorship. It does not prove any claim in this manifest."
    )

    return source


def cmd_build(args: argparse.Namespace) -> int:
    source_path = Path(args.source)
    out_path = Path(args.out)
    if out_path.exists() and not args.overwrite:
        print(
            "REFUSED: output already exists at " + str(out_path)
            + "; pass --overwrite to replace it",
            file=sys.stderr,
        )
        return 1
    try:
        source_text = source_path.read_text(encoding="utf-8")
        source = json.loads(source_text)
        if not isinstance(source, dict):
            raise CeremonyError("source manifest is not a JSON object")
        _check_source_is_sealed(source, source_text)
        _check_version_advances(source, args.new_version)
        key = _load_operator_key(Path(args.key))
        transformed = _transform_source(
            source,
            new_version=args.new_version,
            valid_from=args.valid_from,
            supersedes_url=args.supersedes_url,
        )
        served = glm_manifest.seal_glm_manifest(
            transformed, private_key=key
        )
    except (CeremonyError, glm_manifest.GlmManifestError, OSError, ValueError) as exc:
        print("build: " + str(exc), file=sys.stderr)
        return 1

    detail = glm_manifest.verify_glm_manifest(
        served, trusted_keys_b64=(_public_key_b64(key),)
    )
    if not (detail.digest_ok and detail.signature_ok):
        print(
            "build: self-verify failed (digest_ok=" + str(detail.digest_ok)
            + " signature_ok=" + str(detail.signature_ok) + " errors="
            + repr(detail.errors) + ")",
            file=sys.stderr,
        )
        return 1

    _atomic_write(
        out_path,
        served.encode("utf-8"),
        stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH,
    )
    print("WROTE signed GLM manifest: " + str(out_path))
    print("  owner.version:     " + str(detail.owner_version))
    print("  manifest_digest:   " + str(detail.declared_digest))
    print("  tier:              signed (run 'anchor' to reach logged)")
    print("")
    print("PIN THIS GLM manifest public key into")
    print("glm_manifest.KNOWN_GLM_MANIFEST_PUBLIC_KEYS_B64:")
    print("  " + _public_key_b64(key))
    return 0


def cmd_anchor(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    sidecar_path = Path(args.sidecar)
    if sidecar_path.exists() and not args.overwrite:
        print(
            "REFUSED: sidecar already exists at " + str(sidecar_path)
            + "; pass --overwrite to replace it",
            file=sys.stderr,
        )
        return 1
    try:
        served = manifest_path.read_text(encoding="utf-8")
        body = glm_manifest.canonical_glm_bytes(served)
    except (OSError, glm_manifest.GlmManifestError) as exc:
        print("anchor: cannot read or canonicalize manifest: " + str(exc),
              file=sys.stderr)
        return 1

    from rekor_anchor_v2 import (
        REKOR_V2_DEFAULT_BASE_URL,
        anchor_manifest_to_rekor_v2,
    )
    from rekor_verify_v2 import KNOWN_REKOR_V2_LOG_KEYS

    base_url = REKOR_V2_DEFAULT_BASE_URL
    if args.signing_config:
        from rekor_signing_config import resolve_rekor_endpoint_from_file

        endpoint = resolve_rekor_endpoint_from_file(Path(args.signing_config))
        if endpoint.major_api_version != 2:
            print(
                "anchor: resolved signing-config endpoint is API version "
                + str(endpoint.major_api_version) + " (base_url="
                + endpoint.base_url + "); the v2 anchor speaks only Rekor v2, "
                "refusing to submit (fail closed)",
                file=sys.stderr,
            )
            return 1
        base_url = endpoint.base_url

    from urllib.parse import urlsplit

    anchor_host = urlsplit(base_url).netloc or urlsplit("//" + base_url).netloc
    if anchor_host not in KNOWN_REKOR_V2_LOG_KEYS:
        print(
            "anchor: target log " + repr(anchor_host) + " is not in the pinned "
            "v2 verify allowlist (KNOWN_REKOR_V2_LOG_KEYS); anchoring there "
            "would produce an anchor this install cannot verify offline, "
            "refusing (fail closed)",
            file=sys.stderr,
        )
        return 1

    try:
        v2 = anchor_manifest_to_rekor_v2(body, base_url=base_url)
    except Exception as exc:  # noqa: BLE001
        print("anchor: rekor submission failed: " + str(exc), file=sys.stderr)
        return 1

    sidecar = {
        "schema": "nous.glm.rekor_anchor.v1",
        "manifest_digest_sha256": glm_manifest.compute_glm_digest(served),
        "rekor_anchor": v2.to_manifest_block(),
    }
    data = (
        json.dumps(sidecar, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    _atomic_write(
        sidecar_path,
        data,
        stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH,
    )
    print("ANCHORED GLM manifest: " + str(manifest_path))
    print("  sidecar:   " + str(sidecar_path))
    print("  log_index: " + str(v2.log_index))
    print("  tier:      logged")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    try:
        served = Path(args.manifest).read_text(encoding="utf-8")
    except OSError as exc:
        print("verify: cannot read manifest: " + str(exc), file=sys.stderr)
        return 1
    anchor = None
    if args.sidecar:
        try:
            sidecar = json.loads(
                Path(args.sidecar).read_text(encoding="utf-8")
            )
            anchor = sidecar.get("rekor_anchor")
        except (OSError, ValueError) as exc:
            print("verify: cannot read sidecar: " + str(exc), file=sys.stderr)
            return 1
    detail = glm_manifest.verify_glm_manifest(served, rekor_anchor=anchor)
    print("digest_ok        " + str(detail.digest_ok))
    print("signature_present " + str(detail.signature_present))
    print("signer_pinned    " + str(detail.signer_pinned))
    print("signature_ok     " + str(detail.signature_ok))
    print("anchor_present   " + str(detail.anchor_present))
    print("anchor_ok        " + str(detail.anchor_ok))
    print("owner_version    " + str(detail.owner_version))
    print("declared_digest  " + str(detail.declared_digest))
    print("errors           " + repr(detail.errors))
    return 0 if detail.ok else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sign and anchor the NOUS GLM governance-layer-manifest (operator "
            "ceremony; never invoked automatically)."
        )
    )
    sub = parser.add_subparsers(dest="action", required=True)

    p_build = sub.add_parser("build", help="transform source, seal, sign")
    p_build.add_argument("--source", required=True)
    p_build.add_argument("--key", required=True)
    p_build.add_argument("--new-version", required=True, dest="new_version")
    p_build.add_argument("--valid-from", required=True, dest="valid_from")
    p_build.add_argument(
        "--supersedes-url", required=True, dest="supersedes_url"
    )
    p_build.add_argument("--out", required=True)
    p_build.add_argument("--overwrite", action="store_true")
    p_build.set_defaults(func=cmd_build)

    p_anchor = sub.add_parser("anchor", help="anchor to Rekor v2 (sidecar)")
    p_anchor.add_argument("--manifest", required=True)
    p_anchor.add_argument("--sidecar", required=True)
    p_anchor.add_argument("--signing-config", default=None)
    p_anchor.add_argument("--overwrite", action="store_true")
    p_anchor.set_defaults(func=cmd_anchor)

    p_verify = sub.add_parser("verify", help="offline verify")
    p_verify.add_argument("--manifest", required=True)
    p_verify.add_argument("--sidecar", default=None)
    p_verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
