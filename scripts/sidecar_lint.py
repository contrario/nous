#!/usr/bin/env python3
"""nous-sidecar-lint -- every published .sha256 names the bytes beside it.

WHAT THIS CHECKS. For every *.sha256 under the scanned root:
  1. the sidecar is ASCII and is exactly one POSIX checksum line:
     <64 lowercase hex><two spaces><filename><newline>
  2. the filename it names is its own target (basename of the sidecar
     minus the .sha256 suffix), not some other file
  3. the target exists
  4. the recorded digest equals sha256(target bytes)

WHY IT EXISTS. The published verifier-registry.json.sha256 carried the
digest of the registry from eighteen releases earlier. Nothing wrote it,
nothing checked it, and the registry was re-minted without it. It was ALSO
bare hex with no filename field, so `sha256sum -c` errored out with "no
properly formatted checksum lines found" BEFORE it could report the
mismatch: the format defect concealed the integrity defect. An auditor
running the single most obvious check on a Rekor-anchored artifact would
have been told it was tampered.

HONEST BOUNDARY. A green result EVIDENCES that each sidecar is consumable
by sha256sum -c and describes the file shipped next to it. It PROVES
nothing about whether those bytes are the RIGHT bytes: a consistent
sidecar over tampered content is still consistent. Content is bound to an
identity by the Ed25519 signature and the transparency-log anchor, never
by a sidecar. This gate only ensures the integrity file an auditor will
actually run is not lying about its neighbour.

DECLARED BLIND SPOTS (real, and not patched around):
  1. It cannot detect a WRONG file with a correct sidecar. Regenerating a
     sidecar always makes this tool green. The tool checks consistency,
     not truth -- exactly the claim_lint distinction.
  2. It scans the REPO MIRROR only, never the served /var/www tree, so it
     is CI-portable. Deploy skew between the mirror and the served tree is
     out of scope here and is covered by the existing mirror-snapshot
     discipline (diff -q before commit).
  3. It cannot know that a file which has NO sidecar SHOULD have one.
     Completeness of the sidecar SET is not decidable from the tree.

Exit: 0 = every sidecar conformant. 1 = at least one violation.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

SIDECAR_SUFFIX = ".sha256"
POSIX_LINE = re.compile(r"([0-9a-f]{64})  (.+)\n\Z")

VERSION = "1.0.0"


class Violation:
    def __init__(self, path: Path, kind: str, detail: str) -> None:
        self.path = path
        self.kind = kind
        self.detail = detail

    def render(self, root: Path) -> str:
        try:
            rel = self.path.relative_to(root)
        except ValueError:
            rel = self.path
        return "  " + self.kind.ljust(16) + str(rel) + "\n      " + self.detail


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def check_sidecar(sidecar: Path) -> Violation | None:
    target = sidecar.with_name(sidecar.name[: -len(SIDECAR_SUFFIX)])

    raw = sidecar.read_bytes()
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        return Violation(sidecar, "NON-ASCII", "sidecar bytes are not ASCII")

    match = POSIX_LINE.fullmatch(text)
    if match is None:
        return Violation(
            sidecar,
            "BAD-FORMAT",
            "not a POSIX checksum line (sha256sum -c will refuse it): "
            + repr(text[:72]),
        )

    recorded, named = match.group(1), match.group(2)

    if named != target.name:
        return Violation(
            sidecar,
            "WRONG-NAME",
            "names " + repr(named) + " but its target is "
            + repr(target.name),
        )

    if not target.is_file():
        return Violation(
            sidecar, "NO-TARGET", "target file does not exist: " + target.name
        )

    actual = _sha256_file(target)
    if recorded != actual:
        return Violation(
            sidecar,
            "DIGEST-DRIFT",
            "records " + recorded[:16] + "... but " + target.name
            + " hashes to " + actual[:16] + "... (the sidecar names bytes "
            "that are not there)",
        )

    return None


def scan(root: Path) -> tuple[int, list[Violation]]:
    sidecars = sorted(root.rglob("*" + SIDECAR_SUFFIX))
    violations: list[Violation] = []
    for sidecar in sidecars:
        if not sidecar.is_file():
            continue
        found = check_sidecar(sidecar)
        if found is not None:
            violations.append(found)
    return len(sidecars), violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sidecar_lint",
        description=(
            "Check that every published .sha256 sidecar is a POSIX checksum "
            "line naming the file beside it. Passing EVIDENCES that an "
            "auditor running sha256sum -c gets a truthful answer; it PROVES "
            "nothing about whether the shipped bytes are correct."
        ),
    )
    parser.add_argument("--root", required=True)
    parser.add_argument(
        "--anchor",
        default=None,
        help="commit SHA this scan is pinned to (recorded, not verified).",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print("ERROR: root is not a directory: " + str(root), file=sys.stderr)
        return 1

    print("nous-sidecar-lint " + VERSION)
    print("anchor:  " + (args.anchor or "<none given>"))
    print("root:    " + str(root))

    total, violations = scan(root)
    print("scanned: " + str(total) + " sidecar(s)")
    print("")

    if violations:
        for violation in violations:
            print(violation.render(root))
        print("")
        print(str(len(violations)) + " violation(s).")
        return 1

    print("0 violation(s).")
    print("This result EVIDENCES that every sidecar is consumable by")
    print("sha256sum -c and names the bytes shipped beside it. It PROVES")
    print("nothing about whether those bytes are correct: a consistent")
    print("sidecar over tampered content is still consistent. Content is")
    print("bound to an identity by the signature and the log anchor, never")
    print("by a sidecar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
