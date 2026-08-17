#!/usr/bin/env python3
"""Post-publish cold audit of every published NOUS artifact class.

    python3 scripts/cold_audit.py <version> [--keep] [--only CLASS]

Runs the procedure published in docs/VERIFYING_A_RELEASE.md, verbatim: a fresh
empty directory, public URLs only, the verifier invoked bare, exit 0 asserted.
No repo bytes are read. No producer knowledge is supplied. Nothing is renamed.

Every fetched artifact is rejected if it comes back as an HTML page, and the
release-VSA index.json must record the version that was requested. Both checks
exist because a 200 is not evidence a file exists: an SPA fallback serves the
homepage for any unresolved path (S235), and `curl -f` has no 4xx to fail on.

The fetch shells out to curl BECAUSE THE DOCUMENT SAYS curl. A fetch performed
by a different client is a different input, and a check whose input differs from
the consumer's is not a check of what the consumer holds (S234). This is not a
theoretical point: nous-lang.org sits behind Cloudflare, which 403s the
Python-urllib user-agent while serving curl, requests, httpx and wget normally.
The first draft of this script used urllib and failed 4/4 against a surface that
was entirely healthy.

FIRST, A NEGATIVE CONTROL, AND IT IS FATAL. Before any class is audited, this
script asks the site for a version that CANNOT exist and requires a 404. A 200
there means an SPA fallback is answering under /.well-known/, and every artifact
fetched below would be a web page wearing the name of a signed file. Anything that
is neither 404 nor 200 -- a timeout, a 5xx, a WAF block, a DNS failure -- is
INCONCLUSIVE, and inconclusive is never a pass: a control that goes green when the
network is down is not a control. If the surface does not answer 404, NO class is
audited, because nothing fetched from that surface would mean anything.

NOT A RELEASE PHASE, and it must never become one. At release time the release
VSA is not minted and the wheel is not on PyPI, so a release-time check could
only pass by constructing its own input -- which is the exact defect this tool
exists to catch. It belongs after the publish step of the release ceremony.

Exit: 0 = every audited class verified cold
      1 = at least one class failed
      2 = usage or environment error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WELL_KNOWN = "https://nous-lang.org/.well-known"
NOUS_BASE = WELL_KNOWN + "/nous"

IMPOSSIBLE_VERSION = "9.99.9"

RELEASE_VSA_FILES: tuple[str, ...] = (
    "index.json",
    "build-vsa.intoto.json",
    "build-vsa.intoto.json.sha256",
    "verify_build_vsa_offline.py",
    "verify_build_vsa_offline.py.sha256",
)

PROVENANCE_PUBLISHED_VERSION = "5.58.0"
PROVENANCE_FILES: tuple[str, ...] = (
    "index.json",
    "builder-key.json",
    "verify_provenance_offline.py",
    "nous_lang-" + PROVENANCE_PUBLISHED_VERSION + ".provenance.intoto.json",
    "nous_lang-" + PROVENANCE_PUBLISHED_VERSION + ".tar.gz",
)

VECTOR_FILES: tuple[str, ...] = (
    "index.json",
    "vsa.intoto.json",
    "manifest.json",
    "trace.json",
    "conformance.json",
    "coverage.farkas.json",
    "cost.farkas.json",
    "verify_vsa_offline.py",
    "expected_stdout.txt",
    "expected_exit.txt",
)

REGISTRY_FILES: tuple[str, ...] = (
    "verifier-registry.json",
    "verifier-registry.json.sha256",
)

CLASSES: tuple[str, ...] = (
    "release-vsa",
    "provenance",
    "vsa-vectors",
    "verifier-registry",
)

_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_POSIX_SIDECAR_RE = re.compile(r"^([0-9a-f]{64})  (\S.*)$")


class ColdAuditError(Exception):
    pass


def _fetch(url: str, dest: Path) -> None:
    proc = subprocess.run(
        ["curl", "-fsSL", "-o", str(dest), url],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise ColdAuditError(
            "curl exited " + str(proc.returncode) + " for " + url + ": "
            + proc.stderr.strip()
        )
    if not dest.is_file():
        raise ColdAuditError("curl reported success but wrote no file: " + url)
    head: bytes = dest.read_bytes()[:512].lstrip()
    if head[:9].lower() == b"<!doctype" or head[:5].lower() == b"<html":
        raise ColdAuditError(
            "the site returned an HTML PAGE, not the artifact, for " + url
            + " -- a 200 carrying a web page means the path does not exist and "
            "an SPA fallback served index.html. curl -f cannot catch this: "
            "there is no 4xx to fail on."
        )


def _http_status(url: str) -> int:
    proc = subprocess.run(
        ["curl", "-s", "-o", os.devnull, "-w", "%{http_code}", url],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise ColdAuditError(
            "curl exited " + str(proc.returncode) + " for " + url + ": "
            + proc.stderr.strip()
            + " -- a curl that could not complete is INCONCLUSIVE, not a pass"
        )
    code: str = proc.stdout.strip()
    if not code.isdigit():
        raise ColdAuditError(
            "curl did not report an HTTP status for " + url + ": " + repr(code)
        )
    return int(code)


def preflight_negative_control() -> str:
    """The surface must refuse an artifact that cannot exist.

    S235: nous-lang.org answered 200-with-the-homepage for every unresolved path
    under /.well-known/, and `curl -f` could not see it -- -f fails on a 4xx and
    there was no 4xx. The nginx carve-out fixed the server, but it lives in a
    config no code path writes, so this tool must never assume it is still there.
    The tracked copy under infra/nginx/ is a recovery record; THIS is the check.
    """
    url: str = NOUS_BASE + "/release-vsa/" + IMPOSSIBLE_VERSION + "/index.json"
    code: int = _http_status(url)
    if code == 200:
        raise ColdAuditError(
            "NEGATIVE CONTROL FAILED: the surface answered 200 for version "
            + IMPOSSIBLE_VERSION + ", which cannot exist. An SPA fallback is "
            "serving the homepage where a signed artifact belongs; `curl -f` has "
            "no 4xx to fail on; and every artifact fetched below would be a web "
            "page wearing the name of a signed file. The nginx /.well-known/ "
            "=404 carve-out is absent or has been reverted. url=" + url
        )
    if code != 404:
        raise ColdAuditError(
            "NEGATIVE CONTROL INCONCLUSIVE: expected HTTP 404 for " + url
            + ", got " + str(code) + ". A 5xx, a WAF block or a proxy error is "
            "not a 404, and a control that goes green when the network is down "
            "is not a control."
        )
    return (
        "HTTP 404 for " + IMPOSSIBLE_VERSION
        + " -- the surface refuses what it does not have"
    )


def _fetch_all(base: str, names: tuple[str, ...], into: Path) -> None:
    for name in names:
        _fetch(base + "/" + name, into / name)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_sidecar(sidecar: Path) -> None:
    raw: bytes = sidecar.read_bytes()
    try:
        text: str = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ColdAuditError(
            "sidecar is not ASCII: " + sidecar.name
        ) from exc
    line: str = text.strip("\n")
    match = _POSIX_SIDECAR_RE.match(line)
    if match is None:
        raise ColdAuditError(
            "sidecar is not a POSIX checksum line (64 lowercase hex, two "
            "spaces, filename): " + sidecar.name + " -> " + repr(line)
        )
    want: str = match.group(1)
    named: str = match.group(2)
    target: Path = sidecar.parent / named
    if not target.is_file():
        raise ColdAuditError(
            "sidecar names a file that is not present: "
            + sidecar.name + " -> " + named
        )
    got: str = _sha256_file(target)
    if got != want:
        raise ColdAuditError(
            "sidecar digest mismatch for " + named
            + ": sidecar=" + want[:16] + "... actual=" + got[:16] + "..."
        )


def _run(argv: list[str], cwd: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        argv,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=600,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _require_rc0(argv: list[str], cwd: Path, label: str) -> str:
    rc, out, err = _run(argv, cwd)
    if rc != 0:
        raise ColdAuditError(
            label + " exited " + str(rc) + " (expected 0)\n"
            + "--- stdout ---\n" + out + "--- stderr ---\n" + err
        )
    return out


def audit_release_vsa(version: str, workdir: Path) -> str:
    base: str = NOUS_BASE + "/release-vsa/" + version
    _fetch_all(base, RELEASE_VSA_FILES, workdir)

    _check_sidecar(workdir / "build-vsa.intoto.json.sha256")
    _check_sidecar(workdir / "verify_build_vsa_offline.py.sha256")

    try:
        index = json.loads((workdir / "index.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ColdAuditError(
            "index.json is not JSON: " + str(exc)
        ) from exc
    recorded: str = str(index.get("version"))
    if recorded != version:
        raise ColdAuditError(
            "index.json records version " + repr(recorded)
            + " but " + repr(version) + " was requested; the bundle fetched is "
            "not the bundle asked for"
        )
    wheels = [
        a for a in index.get("artifacts", [])
        if isinstance(a, dict) and a.get("kind") == "wheel"
    ]
    if len(wheels) != 1:
        raise ColdAuditError(
            "index.json names " + str(len(wheels))
            + " artifacts of kind 'wheel' (expected exactly 1)"
        )
    wheel_name: str = str(wheels[0].get("name"))
    wheel_sha: str = str(wheels[0].get("sha256"))

    _require_rc0(
        [
            sys.executable, "-m", "pip", "download",
            "nous-lang==" + version,
            "--no-deps", "--only-binary", ":all:", "-d", ".", "-q",
        ],
        workdir,
        "pip download nous-lang==" + version,
    )

    wheel: Path = workdir / wheel_name
    if not wheel.is_file():
        raise ColdAuditError(
            "pip did not produce the wheel index.json names: " + wheel_name
        )
    got: str = _sha256_file(wheel)
    if got != wheel_sha:
        raise ColdAuditError(
            "PyPI wheel bytes do not match the digest index.json records: "
            "index=" + wheel_sha[:16] + "... pypi=" + got[:16] + "..."
        )

    out: str = _require_rc0(
        [sys.executable, "verify_build_vsa_offline.py"],
        workdir,
        "verify_build_vsa_offline.py (bare)",
    )
    if "VERDICT: PASS" not in out:
        raise ColdAuditError(
            "verifier exited 0 but did not print VERDICT: PASS"
        )
    return "wheel " + wheel_sha[:16] + "... bound; VERDICT: PASS"


def audit_provenance(workdir: Path) -> str:
    _fetch_all(NOUS_BASE + "/provenance", PROVENANCE_FILES, workdir)
    out: str = _require_rc0(
        [sys.executable, "verify_provenance_offline.py"],
        workdir,
        "verify_provenance_offline.py (bare)",
    )
    if "VERDICT: PASS" not in out:
        raise ColdAuditError(
            "verifier exited 0 but did not print VERDICT: PASS"
        )
    return "bundle " + PROVENANCE_PUBLISHED_VERSION + "; VERDICT: PASS"


def audit_vsa_vectors(workdir: Path) -> str:
    _fetch_all(NOUS_BASE + "/vsa-vectors/v1", VECTOR_FILES, workdir)
    out: str = _require_rc0(
        [sys.executable, "verify_vsa_offline.py"],
        workdir,
        "verify_vsa_offline.py (bare)",
    )
    expected: str = (workdir / "expected_stdout.txt").read_text(
        encoding="utf-8"
    )
    if out != expected:
        raise ColdAuditError(
            "verifier stdout is not byte-identical to the published "
            "expected_stdout.txt"
        )
    expected_exit: str = (workdir / "expected_exit.txt").read_text(
        encoding="utf-8"
    ).strip()
    if expected_exit != "0":
        raise ColdAuditError(
            "published expected_exit.txt is " + repr(expected_exit)
            + ", not '0'"
        )
    return "stdout byte-identical to expected_stdout.txt; exit 0"


def audit_verifier_registry(workdir: Path) -> str:
    _fetch_all(WELL_KNOWN + "/nous", REGISTRY_FILES, workdir)
    _check_sidecar(workdir / "verifier-registry.json.sha256")
    digest: str = _sha256_file(workdir / "verifier-registry.json")
    return "sidecar OK (transport only); registry " + digest[:16] + "..."


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cold-audit the published NOUS artifact classes."
    )
    parser.add_argument("version", help="released version, e.g. 5.75.0")
    parser.add_argument(
        "--only",
        choices=CLASSES,
        default=None,
        help="audit a single class instead of all four",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="keep the temporary directory instead of removing it",
    )
    args = parser.parse_args()

    if shutil.which("curl") is None:
        print(
            "ERROR: curl not found on PATH. The published procedure fetches "
            "with curl; this script runs that procedure verbatim.",
            file=sys.stderr,
        )
        return 2

    if not _VERSION_RE.match(args.version):
        print(
            "ERROR: version must be X.Y.Z, got " + repr(args.version),
            file=sys.stderr,
        )
        return 2

    selected: tuple[str, ...] = (
        (args.only,) if args.only else CLASSES
    )

    print("PREFLIGHT   the surface must refuse an artifact that cannot exist")
    try:
        pre: str = preflight_negative_control()  # __s237_p2_preflight_call_v1__
    except ColdAuditError as exc:
        print("FAIL  preflight  " + str(exc))
        print()
        print(
            "RESULT: 0 classes audited. The surface did not answer correctly, so "
            "nothing fetched from it would mean anything."
        )
        return 1
    print("PASS  preflight  " + pre)
    print()

    root: Path = Path(tempfile.mkdtemp(prefix="nous-cold-audit-"))
    print("COLD AUDIT  version=" + args.version + "  root=" + str(root))
    print("  fresh empty directory, public URLs only, verifier run bare")
    print()

    results: list[tuple[str, bool, str]] = []
    for name in selected:
        cell: Path = root / name
        cell.mkdir(parents=True)
        try:
            if name == "release-vsa":
                detail: str = audit_release_vsa(args.version, cell)
            elif name == "provenance":
                detail = audit_provenance(cell)
            elif name == "vsa-vectors":
                detail = audit_vsa_vectors(cell)
            else:
                detail = audit_verifier_registry(cell)
            results.append((name, True, detail))
            print("PASS  " + name.ljust(20) + detail)
        except ColdAuditError as exc:
            results.append((name, False, str(exc)))
            print("FAIL  " + name.ljust(20) + str(exc))

    failures: int = sum(1 for _, ok, _ in results if not ok)

    print()
    print(
        "RESULT: " + str(len(results) - failures) + "/" + str(len(results))
        + " classes verified cold"
    )
    print(
        "  EVIDENCES that each published class runs, as published, for a "
        "stranger. It PROVES nothing about whether the shipped bytes are the "
        "bytes any given party intended: content is bound to an identity by "
        "the Ed25519 signature and the transparency-log anchor, never by a "
        "sidecar or an exit code. The evidence layer is a monitor, not a guard."
    )

    if args.keep:
        print("  kept: " + str(root))
    else:
        shutil.rmtree(root, ignore_errors=True)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
