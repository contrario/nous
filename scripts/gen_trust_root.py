from __future__ import annotations

import argparse
import base64
import os
import stat
import sys
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import attest_apr  # noqa: E402


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the NOUS attestation trust-root Ed25519 keypair. "
            "This is an explicit, one-time operator ceremony; it is never "
            "invoked automatically."
        )
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing trust-root key (refused by default)",
    )
    args = parser.parse_args(argv)

    private_path = attest_apr.trust_root_private_key_path()
    public_path = attest_apr.trust_root_public_key_path()
    fingerprint_path = Path(str(public_path) + ".fingerprint")

    if private_path.exists() and not args.overwrite:
        print(
            f"REFUSED: trust-root private key already exists at {private_path}",
            file=sys.stderr,
        )
        print(
            "A long-lived trust-root must not be silently replaced. "
            "Pass --overwrite to replace it intentionally.",
            file=sys.stderr,
        )
        return 1

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    pem_private = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pem_public = public_key.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    raw_public = public_key.public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    fingerprint = attest_apr.public_key_fingerprint(public_key)
    raw_public_b64 = base64.b64encode(raw_public).decode("ascii")

    _atomic_write(private_path, pem_private, stat.S_IRUSR | stat.S_IWUSR)
    _atomic_write(
        public_path,
        pem_public,
        stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH,
    )
    _atomic_write(
        fingerprint_path,
        (fingerprint + "\n").encode("ascii"),
        stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH,
    )

    print("NOUS attestation trust-root keypair generated.")
    print(f"  private (0600): {private_path}")
    print(f"  public  (0644): {public_path}")
    print(f"  fingerprint   : {fingerprint_path}")
    print("")
    print("PINNED TRUST-ROOT PUBLIC KEY (record this; offline verifiers pin it):")
    print(f"  fingerprint (sha256 of raw pubkey): {fingerprint}")
    print(f"  raw pubkey (base64)               : {raw_public_b64}")
    print("")
    print(
        "WARNING: the private key is stored UNENCRYPTED at rest (0600). Protect "
        "it via filesystem permissions and disk encryption. At-rest passphrase "
        "encryption is a later hardening item, not part of S145."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
