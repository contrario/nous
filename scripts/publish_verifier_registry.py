"""Publish the NOUS verifier-digest registry.
# __s148_u3_publish_tool_v1__

An explicit operator ceremony, never invoked automatically and never shipped
in the wheel (scripts/ is excluded from packaging). It is the SINGLE producer
shared by the real ceremony and the conformance fixtures: the same code that
the tests exercise offline is the code an operator runs to publish.

Two subcommands:

  build   Offline, network-free. Serializes this install's local canonical
          verifier allowlist (ndec.canonical_verifier_digests at the current
          _version) into the portable registry format, optionally UNIONs a
          prior signed registry's entries (--merge) to accrete across NOUS
          versions, signs with an OPERATOR-SUPPLIED Ed25519 key (--key; never
          auto-generated), and writes the signed registry JSON. Prints the
          registry public key for the operator to pin into
          verifier_registry.KNOWN_REGISTRY_PUBLIC_KEYS_B64.

  anchor  The deferred live step (explicit subcommand; build never touches the
          network). Submits the signed registry's canonical body to a Rekor v2
          log as a hashedrekord, attaches the resulting inclusion proof +
          checkpoint as rekor_anchor, and rewrites the registry at the logged
          tier.

Honest boundary: the registry EVIDENCES that a verifier digest is an
officially-published (signed) and, once anchored, publicly-logged template. It
does NOT prove the verifier correct, the decision correct, or compliance.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import _version  # noqa: E402
import ndec  # noqa: E402
import verifier_registry  # noqa: E402


class PublishError(RuntimeError):
    pass


def _atomic_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def current_nous_version() -> str:
    version = getattr(_version, "__version__", None)
    if not isinstance(version, str) or not version:
        raise PublishError(
            "_version.__version__ is missing or not a string; cannot stamp "
            "registry entries"
        )
    return version


def current_entries() -> list[dict]:
    version = current_nous_version()
    digests = ndec.canonical_verifier_digests()
    return [
        {
            "template_name": name,
            "template_sha256": sha,
            "nous_version": version,
        }
        for name, sha in sorted(digests.items())
    ]


def _entries_from_signed(doc: dict) -> list[dict]:
    entries = doc.get("entries")
    if not isinstance(entries, list):
        raise PublishError("merge source has no entries list")
    out: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise PublishError("merge source entry is not an object")
        out.append(
            {
                "template_name": entry.get("template_name"),
                "template_sha256": entry.get("template_sha256"),
                "nous_version": entry.get("nous_version"),
            }
        )
    return out


def _union_entries(
    base: list[dict], extra: list[dict]
) -> list[dict]:
    by_key: dict[tuple, dict] = {}
    for entry in base + extra:
        key = (entry.get("template_name"), entry.get("nous_version"))
        if key in by_key:
            if by_key[key].get("template_sha256") != entry.get(
                "template_sha256"
            ):
                raise PublishError(
                    "merge conflict: two different sha256 values for "
                    "(template_name=" + repr(key[0]) + ", nous_version="
                    + repr(key[1]) + "); refusing"
                )
            continue
        by_key[key] = entry
    return list(by_key.values())


def build_registry_doc(
    entries: list[dict], *, merge_path: Path | None = None
) -> dict:
    all_entries = list(entries)
    if merge_path is not None:
        prior = json.loads(merge_path.read_text(encoding="utf-8"))
        all_entries = _union_entries(
            all_entries, _entries_from_signed(prior)
        )
    return verifier_registry.build_registry(all_entries)


def _load_operator_key(key_path: Path) -> Ed25519PrivateKey:
    if not key_path.is_file():
        raise PublishError(
            "registry signing key not found at " + str(key_path)
            + "; it must be supplied by the operator and is NEVER "
            "auto-generated (see gen_trust_root.py for the key-ceremony "
            "discipline)"
        )
    key = serialization.load_pem_private_key(
        key_path.read_bytes(), password=None
    )
    if not isinstance(key, Ed25519PrivateKey):
        raise PublishError(
            "registry signing key at " + str(key_path)
            + " is not an Ed25519 private key"
        )
    return key


def sign_doc(unsigned: dict, key_path: Path) -> dict:
    key = _load_operator_key(key_path)
    return verifier_registry.sign_registry(unsigned, key)


def registry_public_key_b64(key_path: Path) -> str:
    key = _load_operator_key(key_path)
    raw = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return base64.b64encode(raw).decode("ascii")


def attach_anchor(signed: dict, anchor_block: dict) -> dict:
    if "signature" not in signed:
        raise PublishError(
            "cannot anchor an unsigned registry; sign it first"
        )
    if "rekor_anchor" in signed:
        raise PublishError("registry is already anchored")
    out = dict(signed)
    out["rekor_anchor"] = anchor_block
    return out


def cmd_build(args: argparse.Namespace) -> int:
    output = Path(args.output)
    if output.exists() and not args.overwrite:
        print(
            "REFUSED: registry already exists at " + str(output)
            + "; pass --overwrite to replace it",
            file=sys.stderr,
        )
        return 1
    key_path = Path(args.key)
    merge_path = Path(args.merge) if args.merge else None
    try:
        unsigned = build_registry_doc(
            current_entries(), merge_path=merge_path
        )
        signed = sign_doc(unsigned, key_path)
        pub_b64 = registry_public_key_b64(key_path)
    except (PublishError, verifier_registry.RegistryError) as exc:
        print("build: " + str(exc), file=sys.stderr)
        return 1
    data = (
        json.dumps(signed, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    _atomic_write(
        output,
        data,
        stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH,
    )
    print("WROTE signed verifier-digest registry: " + str(output))
    print("  entries: " + str(len(signed.get("entries", []))))
    print("  tier:    signed (run 'anchor' to reach the logged tier)")
    print("")
    print("PIN THIS registry public key into")
    print("verifier_registry.KNOWN_REGISTRY_PUBLIC_KEYS_B64:")
    print("  " + pub_b64)
    return 0


def cmd_anchor(args: argparse.Namespace) -> int:
    registry_path = Path(args.registry)
    try:
        signed = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("anchor: cannot read registry: " + str(exc), file=sys.stderr)
        return 1
    try:
        body = verifier_registry.canonical_registry_body_bytes(signed)
    except Exception as exc:  # noqa: BLE001
        print("anchor: malformed registry: " + str(exc), file=sys.stderr)
        return 1

    from rekor_anchor_v2 import anchor_manifest_to_rekor_v2

    base_url = None
    if args.signing_config:
        from rekor_signing_config import resolve_rekor_endpoint_from_file

        endpoint = resolve_rekor_endpoint_from_file(
            Path(args.signing_config)
        )
        base_url = endpoint.base_url

    try:
        if base_url is not None:
            v2 = anchor_manifest_to_rekor_v2(body, base_url=base_url)
        else:
            v2 = anchor_manifest_to_rekor_v2(body)
    except Exception as exc:  # noqa: BLE001
        print("anchor: rekor submission failed: " + str(exc), file=sys.stderr)
        return 1

    try:
        anchored = attach_anchor(signed, v2.to_manifest_block())
    except PublishError as exc:
        print("anchor: " + str(exc), file=sys.stderr)
        return 1

    data = (
        json.dumps(anchored, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    _atomic_write(
        registry_path,
        data,
        stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH,
    )
    print("ANCHORED registry: " + str(registry_path))
    print("  log_index: " + str(v2.log_index))
    print("  tier:      logged")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Publish the NOUS verifier-digest registry (operator ceremony; "
            "never invoked automatically)."
        )
    )
    sub = parser.add_subparsers(dest="action", required=True)

    b = sub.add_parser(
        "build",
        help="offline: build + sign the registry from this install",
    )
    b.add_argument(
        "--key", required=True,
        help="path to the operator Ed25519 private key (PEM); never "
             "auto-generated",
    )
    b.add_argument(
        "--output", required=True, help="path to write the signed registry"
    )
    b.add_argument(
        "--merge", default=None,
        help="optional prior registry whose entries are unioned in to "
             "accrete across NOUS versions",
    )
    b.add_argument(
        "--overwrite", action="store_true",
        help="replace an existing output registry",
    )
    b.set_defaults(func=cmd_build)

    a = sub.add_parser(
        "anchor",
        help="deferred live step: anchor a signed registry to Rekor v2",
    )
    a.add_argument("registry", help="path to a signed registry to anchor")
    a.add_argument(
        "--signing-config", default=None,
        help="optional Rekor signing-config to resolve the log endpoint "
             "(avoids hardcoding the log URL)",
    )
    a.set_defaults(func=cmd_anchor)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
