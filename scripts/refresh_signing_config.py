#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import subprocess
import tempfile

DEFAULT_TOOL_PYTHON: str = "/opt/sigstore-tool/bin/python"
DEFAULT_OUT: str = "/var/lib/nous-sigstore/signing_config.json"
SIGNING_CONFIG_NAME: str = "signing_config.v0.2.json"
EXPECTED_MEDIA_PREFIX: str = "application/vnd.dev.sigstore.signingconfig.v0.2"


class RefreshError(Exception):
    pass


def cache_root() -> str:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache"
    )
    return os.path.join(base, "sigstore-python")


def run_tuf_refresh(tool_python: str) -> None:
    result = subprocess.run(
        [tool_python, "-m", "sigstore", "plumbing", "update-trust-root"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RefreshError(
            "sigstore update-trust-root failed (rc=%d): %s"
            % (result.returncode, result.stderr.strip())
        )


def locate_cached_config(root: str) -> str:
    matches = glob.glob(
        os.path.join(root, "**", SIGNING_CONFIG_NAME), recursive=True
    )
    if len(matches) != 1:
        raise RefreshError(
            "expected exactly 1 %s under %s, found %d"
            % (SIGNING_CONFIG_NAME, root, len(matches))
        )
    return matches[0]


def validate_config(raw: bytes) -> None:
    doc = json.loads(raw)
    media = doc.get("mediaType", "")
    if not media.startswith(EXPECTED_MEDIA_PREFIX):
        raise RefreshError("unexpected mediaType: %r" % media)
    urls = doc.get("rekorTlogUrls")
    if not isinstance(urls, list) or not urls:
        raise RefreshError("rekorTlogUrls missing or empty")
    for entry in urls:
        if "url" not in entry or "majorApiVersion" not in entry:
            raise RefreshError("rekorTlogUrls entry missing required keys")


def atomic_write(dest: str, data: bytes) -> None:
    dir_name = os.path.dirname(dest) or "."
    os.makedirs(dir_name, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, dest)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh the Sigstore SigningConfig mirror via the pinned sigstore "
            "tool venv. Writes to a staging path; never writes into the git "
            "repo directly and never imports sigstore into the NOUS runtime."
        )
    )
    parser.add_argument("--tool-python", default=DEFAULT_TOOL_PYTHON)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument(
        "--compare",
        default=None,
        help="path to the repo-pinned config for change detection",
    )
    args = parser.parse_args()

    run_tuf_refresh(args.tool_python)
    cached = locate_cached_config(cache_root())
    with open(cached, "rb") as fh:
        raw = fh.read()
    validate_config(raw)
    new_sha = hashlib.sha256(raw).hexdigest()
    atomic_write(args.out, raw)

    print("OUT:     %s" % args.out)
    print("SHA256:  %s" % new_sha)
    print("BYTES:   %d" % len(raw))

    if args.compare and os.path.exists(args.compare):
        with open(args.compare, "rb") as fh:
            old_sha = hashlib.sha256(fh.read()).hexdigest()
        print("PINNED:  %s" % old_sha)
        print("STATUS:  %s" % ("CHANGED" if old_sha != new_sha else "UNCHANGED"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
