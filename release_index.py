"""release_index -- a release-VSA directory's index.json, checked as the image
of inputs the verifier has already authenticated (S502, D502-1 to D502-9).

# __s502_release_index_closure_v1__

index.json is not signed. nous build-attest-verify (cli_verify_release)
derives it again from what ROOT 1, ROOT 2 and BINDING verified and accepts
it only if the bytes are equal (D502-2):

  the statement        the payload ROOT 1 verified under the pinned key
  the Rekor bundle     the bundle ROOT 2 verified, and its RFC3161 time
  vsaPayloadSha256     sha256 of that payload
  the VSA, the bundle  sha256 of the bytes ROOT 1 and ROOT 2 read, under
                       the version's file names
  the key record       release-verifier-key.json, byte-equal to the
                       canonical record of the pinned key
  the verifier         verify_build_vsa_offline.py, its sha256 the one
                       committed below for the version
  the Rekor boundary   the text committed below for the version (D502-4)

emittedAt is the one field not derived: its form is checked, its value is
not evidenced. The derivation mirrors mint_release_vsa.build_release_index
and is held byte-equal to it by tests (D502-6); this module does not import
the mint. Pure: no network, no root guard, reads only index.json, the
verifier and the key record of the directory it is given.

Boundary (D502-9): see BOUNDARY. PROVES nothing.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

from conformance_verifier import StrictJsonError, loads as _strict_loads

PASS = "PASS"
FAIL = "FAIL"
ABSENT = "ABSENT"

INDEX_FILENAME = "index.json"
VERIFIER_FILENAME = "verify_build_vsa_offline.py"
VERIFIER_KEY_FILENAME = "release-verifier-key.json"
MAX_READ_BYTES = 1048576

INDEX_SCHEMA = "nous.release_vsa.index.v1"
EXT_KEY = "https://nous-lang.org/build-vsa/ext/v1"
BASE_URL = "https://nous-lang.org/.well-known/nous/release-vsa/"
PYPI_PROJECT_URL = "https://pypi.org/project/nous-lang/"
KEY_RECORD_SCHEMA = "nous.release_vsa.verifier_key.v1"
KEY_RECORD_LEVELS = ("SLSA_BUILD_LEVEL_2",)
RELEASE_VERIFIER_ID = "https://nous-lang.org/verifiers/release-operator/v1"

_REKOR_BOUNDARY_HEAD = (
    "EVIDENCES public, append-only, RFC3161-timestamped inclusion of the VSA "
    "payload digest in the Rekor v2 transparency log. The bundle is "
    "self-contained: it carries the RFC6962 inclusion proof, the C2SP "
    "signed-note checkpoint, and the RFC3161 timestamp token, and is "
    "verifiable fully offline with cryptography + Python stdlib only. It "
    "PROVES nothing (no Z3/Farkas leg). "
)
REKOR_BOUNDARY_BEFORE_5_79_0 = _REKOR_BOUNDARY_HEAD + "NOUS is a monitor, not a guard."
REKOR_BOUNDARY_FROM_5_79_0 = (
    _REKOR_BOUNDARY_HEAD + "The evidence layer is a monitor, not a guard.")

# (first version, value); a version takes the last row at or below it. A
# version below the first row has no release VSA and fails.
REKOR_BOUNDARY_ERAS = (
    ((5, 60, 1), REKOR_BOUNDARY_BEFORE_5_79_0),
    ((5, 79, 0), REKOR_BOUNDARY_FROM_5_79_0),
)
VERIFIER_SHA256_ERAS = (
    ((5, 60, 1), "8bdb7a5e7777a3d31b027fc5231e87ffc70e2b7c48bcdeb26d37aecb0f21cb94"),
    ((5, 79, 0), "2d24b70d57410f8b66a0ba713fc78de06bd0c2a02f430e2393886adbba041b29"),
    ((9, 0, 0), "cca57a4cdc84a40873afe6819bb8103a0d80abc96bbb80ceb7e8f79661e7ad41"),
)

EMITTED_AT_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_VERSION_RE = re.compile(r"([0-9]+)\.([0-9]+)\.([0-9]+)")

BOUNDARY = (
    "EVIDENCES that index.json is the deterministic image of the verified "
    "VSA payload, the verified Rekor bundle and time, the pinned key and a "
    "known verifier; emittedAt is not evidenced. PROVES nothing."
)


class IndexClosureError(ValueError):
    """index.json cannot be derived or read; the message is the reason."""


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def read_regular(path: Path, cap: int = MAX_READ_BYTES) -> bytes:
    """The bytes of a regular file, refused past cap without reading on."""
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(str(path), flags)
    except OSError as exc:
        raise IndexClosureError(path.name + " cannot be opened: " + exc.__class__.__name__) from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise IndexClosureError(path.name + " is not a regular file")
        chunks, n = [], 0
        while n <= cap:
            b = os.read(fd, min(65536, cap + 1 - n))
            if not b:
                break
            chunks.append(b)
            n += len(b)
    finally:
        os.close(fd)
    if n > cap:
        raise IndexClosureError(
            path.name + " is larger than " + str(cap) + " bytes; not parsed")
    return b"".join(chunks)


def version_tuple(version: Any) -> tuple[int, int, int]:
    m = _VERSION_RE.fullmatch(version) if isinstance(version, str) else None
    if m is None:
        raise IndexClosureError("no release version: " + repr(version)[:40])
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _era(table: tuple, version: str, what: str) -> Any:
    vt = version_tuple(version)
    value = None
    for first, v in table:
        if vt >= first:
            value = v
    if value is None:
        raise IndexClosureError("no committed " + what + " for version " + version)
    return value


def rekor_boundary(version: str) -> str:
    return _era(REKOR_BOUNDARY_ERAS, version, "Rekor leg boundary")


def verifier_sha256(version: str) -> str:
    return _era(VERIFIER_SHA256_ERAS, version, "offline verifier digest")


def key_record_bytes(pin_b64: str) -> bytes:
    doc = {
        "alg": "ed25519",
        "keyid": _sha256(base64.b64decode(pin_b64, validate=True)),
        "publicKeyRaw": pin_b64,
        "schema": KEY_RECORD_SCHEMA,
        "verifiedLevels": list(KEY_RECORD_LEVELS),
        "verifierId": RELEASE_VERIFIER_ID,
    }
    return json.dumps(doc, sort_keys=True, indent=2).encode("utf-8")


def index_bytes(index: dict[str, Any]) -> bytes:
    return json.dumps(index, sort_keys=True, indent=2).encode("utf-8")


def _rekor_artifact(bundle: dict[str, Any], *, name: str, file_sha256: str, version: str,
                    vsa_payload_sha256_hex: str, rfc3161_gen_time: str) -> dict[str, Any]:
    tle = bundle["transparency_log_entry"]
    body_b64 = str(tle["canonicalized_body"])
    ip = tle["inclusion_proof"]
    checkpoint = str(ip["checkpoint"])
    body_raw = base64.b64decode(body_b64, validate=True)
    body = _strict_loads(body_raw, "rekor bundle canonicalized_body [js:rix.2]")
    if not isinstance(body, dict):
        raise IndexClosureError("canonicalized_body is not a JSON object")
    spec = body.get("spec")
    if not isinstance(spec, dict):
        raise IndexClosureError("canonicalized_body has no spec object")
    leaf = spec.get("hashedRekordV002") or spec.get("hashedRekord") or spec
    if not isinstance(leaf, dict):
        raise IndexClosureError("canonicalized_body spec leaf is not an object")
    anchored = base64.b64decode(str(leaf["data"]["digest"]), validate=True).hex()
    if anchored != vsa_payload_sha256_hex:
        raise IndexClosureError("the anchored digest is not the VSA payload digest")
    kind, api = str(body.get("kind", "")), str(body.get("apiVersion", ""))
    if not kind or not api:
        raise IndexClosureError("canonicalized_body missing kind/apiVersion")
    lines = checkpoint.splitlines()
    if not lines or not lines[0]:
        raise IndexClosureError("checkpoint envelope has no origin line")
    return {
        "anchoredDigestSha256": anchored,
        "boundary": rekor_boundary(version),
        "entryKind": kind + "/" + api,
        "kind": "rekor_v2_transparency_log",
        "leafHash": _sha256(b"\x00" + body_raw),
        "logIndex": int(tle["log_index"]),
        "name": name,
        "rekorShard": "https://" + lines[0],
        "rfc3161GenTime": rfc3161_gen_time,
        "sha256": file_sha256,
        "treeSize": int(ip["tree_size"]),
        "url": BASE_URL + version + "/" + name,
    }


def derive_index(*, version: str, statement: dict[str, Any], bundle: dict[str, Any],
                 vsa_bytes: bytes, bundle_bytes: bytes, verifier_bytes: bytes,
                 key_bytes: bytes, pin_b64: str, vsa_payload_sha256_hex: str,
                 rfc3161_gen_time: str, emitted_at: str) -> dict[str, Any]:
    """The index mint_release_vsa.build_release_index writes for these inputs."""
    try:
        predicate = statement["predicate"]
        ext = predicate[EXT_KEY]
        bid = ext["buildIdentity"]
        base = BASE_URL + version + "/"
        vsa_n = "nous_lang-" + version + ".build-vsa.intoto.json"
        bundle_n = "nous_lang-" + version + ".rekor-v2-bundle.json"
        name_to_sha: dict[str, str] = {}
        for s in statement["subject"]:
            name_to_sha[str(s["name"])] = str(s["digest"]["sha256"])
        wheel = sdist = None
        for name in name_to_sha:
            if name.endswith(".whl"):
                wheel = name
            elif name.endswith(".tar.gz"):
                sdist = name
        if wheel is None or sdist is None:
            raise IndexClosureError("statement subjects missing wheel or sdist")
        arts: list[dict[str, Any]] = [
            {"kind": "release_vsa_dsse", "name": vsa_n, "sha256": _sha256(vsa_bytes),
             "url": base + vsa_n},
            {"kind": "offline_verifier", "name": VERIFIER_FILENAME,
             "sha256": _sha256(verifier_bytes), "url": base + VERIFIER_FILENAME,
             "verifierKeyPinned": pin_b64},
            {"kind": "release_verifier_key", "name": VERIFIER_KEY_FILENAME,
             "sha256": _sha256(key_bytes), "url": base + VERIFIER_KEY_FILENAME},
        ]
        for kind, name in (("wheel", wheel), ("sdist", sdist)):
            arts.append({"kind": kind, "name": name, "sha256": name_to_sha[name],
                         "source": "pypi", "url": PYPI_PROJECT_URL + version + "/"})
        fed = ext["subjectFederation"]
        wheel_entry = None
        for entry in fed:
            if str(entry["name"]).endswith(".whl"):
                wheel_entry = entry
        if wheel_entry is None:
            raise IndexClosureError("subjectFederation has no wheel entry")
        bl = wheel_entry["buildLeg"]
        for entry in fed:
            if str(entry["buildLeg"]["payloadSha256"]) != str(bl["payloadSha256"]):
                raise IndexClosureError(
                    "federation build legs do not share one provenance payloadSha256")
        arts.append({"kind": "federation_build_leg", "payloadSha256": str(bl["payloadSha256"]),
                     "predicateType": str(bl["predicateType"]), "uri": str(bl["uri"])})
        for entry in fed:
            pl = entry["publishLeg"]
            arts.append({"kind": "federation_publish_leg", "name": str(entry["name"]),
                         "payloadSha256": str(pl["payloadSha256"]),
                         "predicateType": str(pl["predicateType"]), "uri": str(pl["uri"])})
        arts.append(_rekor_artifact(
            bundle, name=bundle_n, file_sha256=_sha256(bundle_bytes), version=version,
            vsa_payload_sha256_hex=vsa_payload_sha256_hex, rfc3161_gen_time=rfc3161_gen_time))
        index: dict[str, Any] = {
            "artifacts": arts,
            "boundary": str(ext["boundary"]),
            "buildIdentity": {k: str(bid[k]) for k in (
                "buildType", "builderId", "path", "ref", "repository", "sourceCommit")},
            "emittedAt": emitted_at,
            "policyDigest": str(predicate["policy"]["digest"]["sha256"]),
            "policyId": str(predicate["policy"]["uri"]),
            "schema": INDEX_SCHEMA,
            "verifiedLevels": [str(x) for x in predicate["verifiedLevels"]],
            "verifierId": str(predicate["verifier"]["id"]),
            "verifierKeyid": _sha256(base64.b64decode(pin_b64, validate=True)),
            "verifierPublicKeyRaw": pin_b64,
            "version": version,
            "vsaPayloadSha256": vsa_payload_sha256_hex,
        }
        bf = ext.get("backfill")
        if isinstance(bf, dict):
            index["backfill"] = bf
        return index
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise IndexClosureError(
            "the verified inputs do not have the shape the index is built from: "
            + exc.__class__.__name__ + " " + str(exc)[:80]) from exc
    except ValueError as exc:
        if isinstance(exc, IndexClosureError):
            raise
        raise IndexClosureError("a field cannot be decoded: " + str(exc)[:80]) from exc


def _first_diff(a: bytes, b: bytes) -> int:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n


def _leg(status: str, detail: str) -> dict[str, Any]:
    return {"root": "index", "status": status, "detail": detail, "boundary": BOUNDARY}


def check_index(bundle_dir: str | Path, *, version: str | None,
                statement: dict[str, Any] | None, bundle: dict[str, Any] | None,
                vsa_bytes: bytes, bundle_bytes: bytes, pin_b64: str,
                vsa_payload_sha256_hex: str,
                rfc3161_gen_time: str | None) -> dict[str, Any]:
    """The INDEX leg. statement, bundle and rfc3161_gen_time are None unless
    ROOT 1, ROOT 2 and BINDING passed. ABSENT when the directory has no
    index.json; FAIL on any refusal; PASS only on byte equality."""
    bdir = Path(bundle_dir)
    p = bdir / INDEX_FILENAME
    if not os.path.lexists(str(p)):
        return _leg(ABSENT, "no index.json in the bundle directory; nothing checked, "
                    "the convergence is unchanged")
    try:
        raw = read_regular(p)
        doc = _strict_loads(raw, "index.json [js:rix.1]")
    except (IndexClosureError, StrictJsonError) as exc:
        return _leg(FAIL, str(exc))
    except ValueError as exc:
        return _leg(FAIL, "index.json is not JSON: " + str(exc)[:120])
    emitted = doc.get("emittedAt") if isinstance(doc, dict) else None
    if not isinstance(emitted, str) or EMITTED_AT_RE.fullmatch(emitted) is None:
        return _leg(FAIL, "index.json emittedAt is missing or not of the form "
                    "YYYY-MM-DDTHH:MM:SSZ")
    if statement is None or bundle is None or rfc3161_gen_time is None:
        return _leg(FAIL, "index.json not derived: ROOT 1, ROOT 2 or BINDING did "
                    "not verify its inputs")
    try:
        version_tuple(version)
        verifier = read_regular(bdir / VERIFIER_FILENAME)
        key = read_regular(bdir / VERIFIER_KEY_FILENAME)
        if key != key_record_bytes(pin_b64):
            return _leg(FAIL, VERIFIER_KEY_FILENAME + " is not the canonical record of "
                        "the pinned key")
        if _sha256(verifier) != verifier_sha256(version):
            return _leg(FAIL, VERIFIER_FILENAME + " sha256 " + _sha256(verifier)[:16]
                        + "... is not the verifier committed for " + str(version))
        want = index_bytes(derive_index(
            version=str(version), statement=statement, bundle=bundle,
            vsa_bytes=vsa_bytes, bundle_bytes=bundle_bytes, verifier_bytes=verifier,
            key_bytes=key, pin_b64=pin_b64, vsa_payload_sha256_hex=vsa_payload_sha256_hex,
            rfc3161_gen_time=rfc3161_gen_time, emitted_at=emitted))
    except (IndexClosureError, StrictJsonError) as exc:
        return _leg(FAIL, str(exc))
    if want != raw:
        return _leg(FAIL, "index.json (" + str(len(raw)) + " B) is not the image of the "
                    "verified inputs (" + str(len(want)) + " B); first difference at byte "
                    + str(_first_diff(raw, want)))
    return _leg(PASS, "index.json (" + str(len(raw)) + " B) equals, byte for byte, the "
                "image of the verified inputs; emittedAt " + emitted + " is not evidenced")
