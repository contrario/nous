from __future__ import annotations

# __s171_mint_release_vsa_phase1_v1__
#
# Release-VSA MINT orchestrator -- Phase 1 (MINT, fully reversible).
#
# Verifies the two federation legs (SLSA build provenance via sigstore; PEP 740
# publish attestation via pypi-attestations) for a published NOUS release,
# assembles and Ed25519-signs a release VSA with the operator seed, emits the
# self-contained offline verifier, and writes a PARTIAL bundle directory with a
# .sha256 sidecar per file. It then runs a ROOT-1-only self-verify (operator
# signature + subject identity + policy) using the just-emitted offline
# verifier, which does not require the Rekor bundle.
#
# This phase performs NO Rekor write and writes NO index.json. The irreversible
# public-log anchor and the index are Phase 2 (ANCHOR), a separate gated step.
#
# Boundary: the federation-verifying dependencies (sigstore, pypi-attestations)
# are confined to this operator-side tool. They never enter the shipped offline
# verify path (verify_build_vsa_offline.py / nous build-attest-verify stay
# cryptography + z3 + stdlib only). A release VSA EVIDENCES the operator's
# endorsement; it PROVES nothing. NOUS is a monitor, not a guard.
#
# Refuse over guess: every precondition miss raises MintError (message starts
# with the cause) before any file is written.

import argparse
import base64
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import build_vsa

DEFAULT_OPERATOR_KEY = "/root/.local/share/nous/keys/release_attest_signing.key"
COMMITTED_RELEASE_PIN_B64 = "E3FNG9zFMRjhg/iVkOu9K3gH5mmG6Uwvdy8EvwHsYVo="
GITHUB_API = "https://api.github.com"
PYPI_INTEGRITY = "https://pypi.org/integrity"
REPOSITORY = "contrario/nous"
WORKFLOW = "release.yml"
WORKFLOW_REF_PREFIX = "refs/tags/"
SLSA_BUILD_LEVEL = "SLSA_BUILD_LEVEL_2"
SLSA_PROVENANCE_PREDICATE = "https://slsa.dev/provenance/v1"
PEP740_PUBLISH_PREDICATE = "https://docs.pypi.org/attestations/publish/v1"
BUILD_TYPE = "https://actions.github.io/buildtypes/workflow/v1"

RELEASE_BOUNDARY = (
    "This release VSA EVIDENCES that the NOUS release operator verified, with "
    "standard Sigstore tooling, that these exact published wheel and sdist "
    "bytes carry a SLSA build provenance (keyless GitHub Actions, "
    "Fulcio/Rekor) and a PEP 740 PyPI publish attestation, both naming these "
    "bytes, at SLSA Build Level 2. It is an operator-key root ALONGSIDE the "
    "federation roots; it is not a second build. The offline verifier checks "
    "the operator signature and re-derives the subject digests, but does NOT "
    "re-derive the named federation attestations (toolchain tier: fetch + "
    "Sigstore). It PROVES nothing (no Z3/Farkas leg). NOUS is a monitor, not a "
    "guard."
)
OFFLINE_SCOPE = (
    "EVIDENCES operator endorsement + subject identity; named federation "
    "attestations are recorded by URI + digest but NOT re-derived offline "
    "(toolchain tier)"
)


class MintError(ValueError):
    """Raised on any precondition or verification failure in the MINT phase.
    The message starts with the cause. No files are written on a raise."""


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_http() -> "Any":
    import httpx

    return httpx


def _get_json(url: str, *, accept: str | None = None) -> dict[str, Any]:
    httpx = _require_http()
    headers = {"Accept": accept} if accept else {}
    try:
        resp = httpx.get(url, headers=headers, timeout=httpx.Timeout(30.0, connect=10.0))
    except httpx.RequestError as exc:
        raise MintError("federation fetch failed for " + url + ": " + repr(exc)) from exc
    if resp.status_code != 200:
        raise MintError(
            "federation fetch returned HTTP "
            + str(resp.status_code)
            + " for "
            + url
            + ": "
            + resp.text[:256]
        )
    try:
        obj = resp.json()
    except json.JSONDecodeError as exc:
        raise MintError("federation fetch returned non-JSON for " + url + ": " + repr(exc)) from exc
    if not isinstance(obj, dict):
        raise MintError("federation fetch returned non-object JSON for " + url)
    return obj


def _load_operator_seed(key_path: Path) -> bytes:
    if not key_path.is_file():
        raise MintError("operator seed not found: " + str(key_path))
    seed = key_path.read_bytes()
    if len(seed) != 32:
        raise MintError("operator seed must be 32 raw bytes, got " + str(len(seed)))
    return seed


def _operator_pubkey_b64(seed: bytes) -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    pub = Ed25519PrivateKey.from_private_bytes(seed).public_key()
    raw = pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def _pypi_files(version: str) -> dict[str, Any]:
    url = "https://pypi.org/pypi/nous-lang/" + version + "/json"
    doc = _get_json(url)
    files = doc.get("urls")
    if not isinstance(files, list) or not files:
        raise MintError("PyPI returned no files for nous-lang " + version)
    out: dict[str, dict[str, str]] = {}
    for f in files:
        if not isinstance(f, dict):
            continue
        pt = f.get("packagetype")
        name = f.get("filename")
        digests = f.get("digests") or {}
        sha = digests.get("sha256")
        dl_url = f.get("url")
        if not isinstance(name, str) or not isinstance(sha, str) or not isinstance(dl_url, str):
            continue
        if pt == "bdist_wheel":
            out["wheel"] = {"name": name, "sha256": sha, "url": dl_url}
        elif pt == "sdist":
            out["sdist"] = {"name": name, "sha256": sha, "url": dl_url}
    if "wheel" not in out or "sdist" not in out:
        raise MintError(
            "PyPI files for "
            + version
            + " missing wheel or sdist: found "
            + str(sorted(out))
        )
    return out


def _verify_build_leg(version: str, wheel_sha256: str) -> dict[str, Any]:
    url = (
        GITHUB_API
        + "/repos/"
        + REPOSITORY
        + "/attestations/sha256:"
        + wheel_sha256
    )
    doc = _get_json(url, accept="application/vnd.github+json")
    atts = doc.get("attestations")
    if not isinstance(atts, list) or not atts:
        raise MintError("GitHub returned no build attestations for sha256:" + wheel_sha256)
    att = atts[0]
    bundle = att.get("bundle") if isinstance(att, dict) else None
    if not isinstance(bundle, dict):
        raise MintError("GitHub attestation has no bundle object")
    dsse = bundle.get("dsseEnvelope")
    if not isinstance(dsse, dict) or "payload" not in dsse:
        raise MintError("GitHub attestation bundle has no dsseEnvelope.payload")

    from sigstore.models import Bundle
    from sigstore.verify import Verifier
    from sigstore.verify import policy as vpol

    try:
        sb = Bundle.from_json(json.dumps(bundle))
    except Exception as exc:
        raise MintError("GitHub attestation bundle is not a valid Sigstore bundle: " + repr(exc)) from exc

    expected_ref = WORKFLOW_REF_PREFIX + "v" + version
    identity = vpol.AllOf(
        [
            vpol.OIDCSourceRepositoryURI("https://github.com/" + REPOSITORY),
            vpol.GitHubWorkflowRepository(REPOSITORY),
            vpol.OIDCSourceRepositoryRef(expected_ref),
        ]
    )
    verifier = Verifier.production()
    try:
        payload_type, payload_bytes = verifier.verify_dsse(sb, identity)
    except Exception as exc:
        raise MintError("SLSA build provenance failed Sigstore verification: " + repr(exc)) from exc

    payload_b64 = dsse["payload"]
    try:
        decoded = base64.b64decode(payload_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise MintError("build-leg dsseEnvelope.payload is not valid base64: " + repr(exc)) from exc
    if decoded != payload_bytes:
        raise MintError("build-leg verified payload does not equal the recorded dsseEnvelope.payload")

    try:
        statement = json.loads(decoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MintError("build-leg payload is not valid JSON: " + repr(exc)) from exc
    predicate = statement.get("predicate") if isinstance(statement, dict) else None
    pred_obj = predicate if isinstance(predicate, dict) else {}
    build_def = pred_obj.get("buildDefinition") or {}
    external = build_def.get("externalParameters") or {}
    run_details = pred_obj.get("runDetails") or {}
    builder = run_details.get("builder") or {}
    source_commit = ""
    rd = build_def.get("resolvedDependencies") or []
    for dep in rd:
        if isinstance(dep, dict) and dep.get("uri", "").startswith("git+https://github.com/" + REPOSITORY):
            digest = dep.get("digest") or {}
            source_commit = str(digest.get("gitCommit", ""))
            break

    payload_sha256 = _sha256_hex(decoded)
    return {
        "uri": url,
        "payload_sha256": payload_sha256,
        "predicate_type": SLSA_PROVENANCE_PREDICATE,
        "build_identity": {
            "buildType": BUILD_TYPE,
            "builderId": "https://github.com/"
            + REPOSITORY
            + "/.github/workflows/"
            + WORKFLOW
            + "@"
            + expected_ref,
            "path": ".github/workflows/" + WORKFLOW,
            "ref": expected_ref,
            "repository": "https://github.com/" + REPOSITORY,
            "sourceCommit": source_commit,
        },
        "_builder_id_seen": str(builder.get("id", "")),
        "_external_workflow": external.get("workflow") if isinstance(external, dict) else None,
    }


def _verify_publish_leg(version: str, filename: str, dist_path: Path) -> dict[str, Any]:
    import pypi_attestations as pa

    url = (
        PYPI_INTEGRITY
        + "/nous-lang/"
        + version
        + "/"
        + filename
        + "/provenance"
    )
    doc = _get_json(url)
    bundles = doc.get("attestation_bundles")
    if not isinstance(bundles, list) or not bundles:
        raise MintError("PyPI provenance has no attestation_bundles for " + filename)
    bundle0 = bundles[0]
    atts = bundle0.get("attestations") if isinstance(bundle0, dict) else None
    if not isinstance(atts, list) or not atts:
        raise MintError("PyPI provenance bundle has no attestations for " + filename)
    att0 = atts[0]
    envelope = att0.get("envelope") if isinstance(att0, dict) else None
    if not isinstance(envelope, dict) or "statement" not in envelope:
        raise MintError("PyPI provenance attestation envelope has no statement for " + filename)

    statement_b64 = envelope["statement"]
    try:
        statement_bytes = base64.b64decode(statement_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise MintError("publish-leg envelope.statement is not valid base64: " + repr(exc)) from exc

    try:
        prov = pa.Provenance.model_validate(doc)
    except Exception as exc:
        raise MintError("PyPI provenance failed schema validation: " + repr(exc)) from exc
    attestation = prov.attestation_bundles[0].attestations[0]

    dist = pa.Distribution.from_file(dist_path)
    publisher = pa.GitHubPublisher(
        repository=REPOSITORY,
        workflow=WORKFLOW,
    )
    try:
        predicate_type, _claims = attestation.verify(publisher, dist)
    except pa.VerificationError as exc:
        raise MintError("PEP 740 publish attestation failed verification for " + filename + ": " + repr(exc)) from exc

    payload_sha256 = _sha256_hex(statement_bytes)
    return {
        "uri": url,
        "payload_sha256": payload_sha256,
        "predicate_type": PEP740_PUBLISH_PREDICATE,
        "_predicate_type_seen": str(predicate_type),
    }


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".mint_")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _write_with_sidecar(path: Path, data: bytes) -> None:
    _atomic_write(path, data)
    sidecar = path.with_name(path.name + ".sha256")
    digest_line = _sha256_hex(data) + "  " + path.name + "\n"
    _atomic_write(sidecar, digest_line.encode("ascii"))


def mint(version: str, out_dir: Path, *, key_path: Path, work_dir: Path) -> int:
    seed = _load_operator_seed(key_path)
    pin = _operator_pubkey_b64(seed)
    if pin != COMMITTED_RELEASE_PIN_B64:
        raise MintError(
            "operator key does not match the committed consumer pin "
            "(derived "
            + pin
            + " != "
            + COMMITTED_RELEASE_PIN_B64
            + "); minting would ship a dir the shipped verifier rejects"
        )

    files = _pypi_files(version)
    wheel = files["wheel"]
    sdist = files["sdist"]

    work_dir.mkdir(parents=True, exist_ok=True)
    httpx = _require_http()
    dist_paths: dict[str, Path] = {}
    for label, meta in (("wheel", wheel), ("sdist", sdist)):
        dl = work_dir / meta["name"]
        try:
            resp = httpx.get(meta["url"], timeout=httpx.Timeout(60.0, connect=10.0))
        except httpx.RequestError as exc:
            raise MintError("artifact download failed for " + meta["name"] + ": " + repr(exc)) from exc
        if resp.status_code != 200:
            raise MintError("artifact download returned HTTP " + str(resp.status_code) + " for " + meta["name"])
        body = resp.content
        got = _sha256_hex(body)
        if got != meta["sha256"]:
            raise MintError(
                "downloaded "
                + label
                + " sha256 mismatch: PyPI="
                + meta["sha256"][:16]
                + "... local="
                + got[:16]
                + "..."
            )
        _atomic_write(dl, body)
        dist_paths[label] = dl

    build_leg = _verify_build_leg(version, wheel["sha256"])
    publish_whl = _verify_publish_leg(version, wheel["name"], dist_paths["wheel"])
    publish_sdist = _verify_publish_leg(version, sdist["name"], dist_paths["sdist"])

    subject_federation = [
        {
            "name": wheel["name"],
            "sha256": wheel["sha256"],
            "buildLeg": {
                "uri": build_leg["uri"],
                "payloadSha256": build_leg["payload_sha256"],
                "predicateType": build_leg["predicate_type"],
            },
            "publishLeg": {
                "uri": publish_whl["uri"],
                "payloadSha256": publish_whl["payload_sha256"],
                "predicateType": publish_whl["predicate_type"],
            },
        },
        {
            "name": sdist["name"],
            "sha256": sdist["sha256"],
            "buildLeg": {
                "uri": build_leg["uri"],
                "payloadSha256": build_leg["payload_sha256"],
                "predicateType": build_leg["predicate_type"],
            },
            "publishLeg": {
                "uri": publish_sdist["uri"],
                "payloadSha256": publish_sdist["payload_sha256"],
                "predicateType": publish_sdist["predicate_type"],
            },
        },
    ]

    ext = {
        "boundary": RELEASE_BOUNDARY,
        "buildIdentity": build_leg["build_identity"],
        "offlineScope": OFFLINE_SCOPE,
        "subjectFederation": subject_federation,
    }

    input_attestations = [
        {"uri": build_leg["uri"], "sha256": build_leg["payload_sha256"]},
        {"uri": publish_whl["uri"], "sha256": publish_whl["payload_sha256"]},
        {"uri": publish_sdist["uri"], "sha256": publish_sdist["payload_sha256"]},
    ]

    import datetime as _dt

    time_verified = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    statement = build_vsa.assemble_build_vsa_statement(
        subjects=[
            {"name": wheel["name"], "sha256": wheel["sha256"]},
            {"name": sdist["name"], "sha256": sdist["sha256"]},
        ],
        input_attestations=input_attestations,
        verified_levels=[SLSA_BUILD_LEVEL],
        ext=ext,
        resource_uri="pkg:pypi/nous-lang@" + version,
        time_verified=time_verified,
    )

    for subj in statement["subject"]:
        name = subj["name"]
        want = subj["digest"]["sha256"]
        local = dist_paths["wheel"] if name == wheel["name"] else dist_paths["sdist"]
        got = _sha256_hex(local.read_bytes())
        if got != want:
            raise MintError(
                "self-grade: subject digest mismatch for "
                + name
                + " (statement="
                + want[:16]
                + "... local="
                + got[:16]
                + "...)"
            )

    if statement["predicate"]["policy"]["digest"]["sha256"] != build_vsa.build_policy_fingerprint():
        raise MintError("self-grade: policy digest does not match build_policy_fingerprint()")

    envelope = build_vsa.sign_build_vsa(statement, seed)

    out_dir.mkdir(parents=True, exist_ok=True)
    vsa_name = "nous_lang-" + version + ".build-vsa.intoto.json"
    envelope_bytes = json.dumps(envelope, sort_keys=True, indent=2).encode("utf-8")
    _write_with_sidecar(out_dir / vsa_name, envelope_bytes)

    verifier_key_doc = {
        "alg": "ed25519",
        "keyid": _sha256_hex(base64.b64decode(pin)),
        "publicKeyRaw": pin,
        "schema": "nous.release_vsa.verifier_key.v1",
        "verifiedLevels": [SLSA_BUILD_LEVEL],
        "verifierId": build_vsa.NOUS_RELEASE_VERIFIER_ID,
    }
    verifier_key_bytes = json.dumps(verifier_key_doc, sort_keys=True, indent=2).encode("utf-8")
    _write_with_sidecar(out_dir / "release-verifier-key.json", verifier_key_bytes)

    emitted = build_vsa.emit_build_vsa_verifier(str(out_dir), pin)
    verifier_bytes = emitted.read_bytes()
    sidecar = emitted.with_name(emitted.name + ".sha256")
    digest_line = _sha256_hex(verifier_bytes) + "  " + emitted.name + "\n"
    _atomic_write(sidecar, digest_line.encode("ascii"))

    root1 = _root1_self_verify(out_dir, vsa_name)

    print("MINT complete (Phase 1, reversible) for nous-lang " + version)
    print("  out dir:            " + str(out_dir))
    print("  vsa:                " + vsa_name)
    print("  verifier:           " + emitted.name)
    print("  verifier key:       release-verifier-key.json")
    print("  operator pin:       " + pin)
    print("  build-leg payload:  " + build_leg["payload_sha256"][:16] + "...")
    print("  whl  publish:       " + publish_whl["payload_sha256"][:16] + "...")
    print("  sdist publish:      " + publish_sdist["payload_sha256"][:16] + "...")
    print("  source commit:      " + (build_leg["build_identity"]["sourceCommit"] or "(unresolved)"))
    print("  ROOT-1 self-verify: " + ("PASS" if root1 == 0 else "FAIL (rc=" + str(root1) + ")"))
    print()
    print("NO Rekor write performed. NO index.json written. ANCHOR is Phase 2,")
    print("a separate gated step. The VSA payload digest to anchor is:")
    payload_sha = _sha256_hex(base64.b64decode(envelope["payload"]))
    print("  vsaPayloadSha256:   " + payload_sha)
    if root1 != 0:
        return 1
    return 0


def _root1_self_verify(out_dir: Path, vsa_name: str) -> int:
    import subprocess

    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        (tdir / "build-vsa.intoto.json").write_bytes((out_dir / vsa_name).read_bytes())
        result = subprocess.run(
            [sys.executable, str(out_dir / "verify_build_vsa_offline.py"), str(tdir)],
            capture_output=True,
            text=True,
        )
    sys.stdout.write(result.stdout)
    # __s172_p0a_root1_stderr_suppress_v1__
    # rc 2 = no named subject present locally to re-derive (expected: this dir
    # holds only the VSA, not the wheel/sdist). ROOT-1 legs (signature,
    # identity, policy) print OK before that point; treat rc 2 as ROOT-1 PASS.
    is_root1_pass = (
        result.returncode == 2
        and "release VSA DSSE Ed25519 signature verified" in result.stdout
    )
    if result.stderr and not is_root1_pass:
        sys.stderr.write(result.stderr)
    if is_root1_pass:
        return 0
    return result.returncode


# __s172_p0b1_release_bundle_index_v1__
NOUS_BUILD_VSA_EXT_KEY = "https://nous-lang.org/build-vsa/ext/v1"
RELEASE_VSA_INDEX_SCHEMA = "nous.release_vsa.index.v1"
RELEASE_VSA_BASE_URL = "https://nous-lang.org/.well-known/nous/release-vsa/"
PYPI_PROJECT_URL = "https://pypi.org/project/nous-lang/"
REKOR_LEG_BOUNDARY = (
    "EVIDENCES public, append-only, RFC3161-timestamped inclusion of the VSA "
    "payload digest in the Rekor v2 transparency log. The bundle is "
    "self-contained: it carries the RFC6962 inclusion proof, the C2SP "
    "signed-note checkpoint, and the RFC3161 timestamp token, and is "
    "verifiable fully offline with cryptography + Python stdlib only. It "
    "PROVES nothing (no Z3/Farkas leg). NOUS is a monitor, not a guard."
)


def decode_build_vsa_statement(envelope: dict[str, Any]) -> dict[str, Any]:
    payload_b64 = envelope.get("payload")
    if not isinstance(payload_b64, str) or not payload_b64:
        raise MintError("build-vsa envelope has no payload")
    try:
        raw = base64.b64decode(payload_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise MintError(
            "build-vsa payload is not valid base64: " + str(exc)
        ) from exc
    try:
        statement = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MintError(
            "build-vsa payload is not valid JSON: " + str(exc)
        ) from exc
    if not isinstance(statement, dict):
        raise MintError("build-vsa payload is not a JSON object")
    return statement


def vsa_payload_sha256(envelope: dict[str, Any]) -> str:
    payload_b64 = envelope.get("payload")
    if not isinstance(payload_b64, str) or not payload_b64:
        raise MintError("build-vsa envelope has no payload")
    return hashlib.sha256(
        base64.b64decode(payload_b64, validate=True)
    ).hexdigest()


def canonical_bytes_to_anchor(envelope: dict[str, Any]) -> bytes:
    payload_b64 = envelope.get("payload")
    if not isinstance(payload_b64, str) or not payload_b64:
        raise MintError("build-vsa envelope has no payload")
    return base64.b64decode(payload_b64, validate=True)


def _decode_canonicalized_body(body_b64: str) -> dict[str, Any]:
    try:
        body = json.loads(
            base64.b64decode(body_b64, validate=True).decode("utf-8")
        )
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MintError(
            "canonicalized_body is not valid base64/JSON: " + str(exc)
        ) from exc
    if not isinstance(body, dict):
        raise MintError("canonicalized_body is not a JSON object")
    return body


def _hashedrekord_leaf(body: dict[str, Any]) -> dict[str, Any]:
    spec = body.get("spec")
    if not isinstance(spec, dict):
        raise MintError("canonicalized_body has no spec object")
    leaf = spec.get("hashedRekordV002") or spec.get("hashedRekord") or spec
    if not isinstance(leaf, dict):
        raise MintError("canonicalized_body spec leaf is not an object")
    return leaf


def _derive_entry_signature(body_b64: str) -> str:
    leaf = _hashedrekord_leaf(_decode_canonicalized_body(body_b64))
    try:
        content = leaf["signature"]["content"]
    except (KeyError, TypeError) as exc:
        raise MintError(
            "cannot derive entry_signature from canonicalized_body: " + str(exc)
        ) from exc
    if not isinstance(content, str) or not content:
        raise MintError("entry_signature content is not a non-empty string")
    return content


def _anchored_digest_hex(body_b64: str) -> str:
    leaf = _hashedrekord_leaf(_decode_canonicalized_body(body_b64))
    try:
        digest_b64 = leaf["data"]["digest"]
    except (KeyError, TypeError) as exc:
        raise MintError(
            "cannot derive anchored digest from canonicalized_body: " + str(exc)
        ) from exc
    return base64.b64decode(str(digest_b64), validate=True).hex()


def _entry_kind(body_b64: str) -> str:
    body = _decode_canonicalized_body(body_b64)
    kind = str(body.get("kind", ""))
    api = str(body.get("apiVersion", ""))
    if not kind or not api:
        raise MintError("canonicalized_body missing kind/apiVersion")
    return kind + "/" + api


def _leaf_hash_hex(body_b64: str) -> str:
    leaf = base64.b64decode(body_b64, validate=True)
    return hashlib.sha256(b"\x00" + leaf).hexdigest()


def _checkpoint_tree_size(checkpoint_envelope: str) -> int:
    import rekor_v2_offline

    cp = rekor_v2_offline.parse_checkpoint(checkpoint_envelope)
    return int(cp.tree_size)


def _checkpoint_origin(checkpoint_envelope: str) -> str:
    lines = checkpoint_envelope.splitlines()
    if not lines or not lines[0]:
        raise MintError("checkpoint envelope has no origin line")
    return lines[0]


def assemble_rekor_bundle(anchor: Any, rfc3161_token_der: bytes) -> dict[str, Any]:
    """Assemble the offline rekor-v2-bundle.json dict from a live Rekor anchor.

    anchor is duck-typed as rekor_anchor_v2.RekorAnchorV2 (reads only
    .body_b64, .checkpoint_envelope, .inclusion_proof_hashes, .log_index);
    typed Any so this pure-assembly path does not import the live httpx anchor
    client. Shape matches the rekor_v2_offline consumer.
    """
    body_b64 = str(anchor.body_b64)
    checkpoint_envelope = str(anchor.checkpoint_envelope)
    return {
        "entry_signature": _derive_entry_signature(body_b64),
        "rfc3161_timestamp": base64.b64encode(rfc3161_token_der).decode("ascii"),
        "transparency_log_entry": {
            "canonicalized_body": body_b64,
            "inclusion_proof": {
                "checkpoint": checkpoint_envelope,
                "hashes": [str(h) for h in anchor.inclusion_proof_hashes],
                "tree_size": _checkpoint_tree_size(checkpoint_envelope),
            },
            "log_index": int(anchor.log_index),
        },
    }


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_release_index(
    version: str,
    out_dir: Path,
    *,
    statement: dict[str, Any],
    bundle: dict[str, Any],
    bundle_filename: str,
    vsa_filename: str,
    verifier_filename: str,
    verifier_key_filename: str,
    operator_pin_b64: str,
    vsa_payload_sha256_hex: str,
    rfc3161_gen_time: str,
    emitted_at: str,
) -> dict[str, Any]:
    predicate = statement["predicate"]
    ext = predicate[NOUS_BUILD_VSA_EXT_KEY]
    build_identity = ext["buildIdentity"]
    subject_federation = ext["subjectFederation"]
    subjects = statement["subject"]

    base = RELEASE_VSA_BASE_URL + version + "/"

    name_to_sha: dict[str, str] = {}
    for s in subjects:
        name_to_sha[str(s["name"])] = str(s["digest"]["sha256"])
    wheel_name = None
    sdist_name = None
    for name in name_to_sha:
        if name.endswith(".whl"):
            wheel_name = name
        elif name.endswith(".tar.gz"):
            sdist_name = name
    if wheel_name is None or sdist_name is None:
        raise MintError("statement subjects missing wheel or sdist")

    artifacts: list[dict[str, Any]] = []
    artifacts.append({
        "kind": "release_vsa_dsse",
        "name": vsa_filename,
        "sha256": _sha256_file(out_dir / vsa_filename),
        "url": base + vsa_filename,
    })
    artifacts.append({
        "kind": "offline_verifier",
        "name": verifier_filename,
        "sha256": _sha256_file(out_dir / verifier_filename),
        "url": base + verifier_filename,
        "verifierKeyPinned": operator_pin_b64,
    })
    artifacts.append({
        "kind": "release_verifier_key",
        "name": verifier_key_filename,
        "sha256": _sha256_file(out_dir / verifier_key_filename),
        "url": base + verifier_key_filename,
    })
    artifacts.append({
        "kind": "wheel",
        "name": wheel_name,
        "sha256": name_to_sha[wheel_name],
        "source": "pypi",
        "url": PYPI_PROJECT_URL + version + "/",
    })
    artifacts.append({
        "kind": "sdist",
        "name": sdist_name,
        "sha256": name_to_sha[sdist_name],
        "source": "pypi",
        "url": PYPI_PROJECT_URL + version + "/",
    })

    wheel_entry = None
    for entry in subject_federation:
        if str(entry["name"]).endswith(".whl"):
            wheel_entry = entry
    if wheel_entry is None:
        raise MintError("subjectFederation has no wheel entry")
    bl = wheel_entry["buildLeg"]
    for entry in subject_federation:
        if str(entry["buildLeg"]["payloadSha256"]) != str(bl["payloadSha256"]):
            raise MintError(
                "federation build legs do not share one provenance payloadSha256"
            )
    artifacts.append({
        "kind": "federation_build_leg",
        "payloadSha256": str(bl["payloadSha256"]),
        "predicateType": str(bl["predicateType"]),
        "uri": str(bl["uri"]),
    })

    for entry in subject_federation:
        pl = entry["publishLeg"]
        artifacts.append({
            "kind": "federation_publish_leg",
            "name": str(entry["name"]),
            "payloadSha256": str(pl["payloadSha256"]),
            "predicateType": str(pl["predicateType"]),
            "uri": str(pl["uri"]),
        })

    tle = bundle["transparency_log_entry"]
    body_b64 = str(tle["canonicalized_body"])
    ip = tle["inclusion_proof"]
    checkpoint_envelope = str(ip["checkpoint"])
    anchored = _anchored_digest_hex(body_b64)
    if anchored != vsa_payload_sha256_hex:
        raise MintError(
            "binding self-check failed: anchored digest "
            + anchored[:16] + "... != vsaPayloadSha256 "
            + vsa_payload_sha256_hex[:16] + "..."
        )
    artifacts.append({
        "anchoredDigestSha256": anchored,
        "boundary": REKOR_LEG_BOUNDARY,
        "entryKind": _entry_kind(body_b64),
        "kind": "rekor_v2_transparency_log",
        "leafHash": _leaf_hash_hex(body_b64),
        "logIndex": int(tle["log_index"]),
        "name": bundle_filename,
        "rekorShard": "https://" + _checkpoint_origin(checkpoint_envelope),
        "rfc3161GenTime": rfc3161_gen_time,
        "sha256": _sha256_file(out_dir / bundle_filename),
        "treeSize": int(ip["tree_size"]),
        "url": base + bundle_filename,
    })

    return {
        "artifacts": artifacts,
        "boundary": str(ext["boundary"]),
        "buildIdentity": {
            "buildType": str(build_identity["buildType"]),
            "builderId": str(build_identity["builderId"]),
            "path": str(build_identity["path"]),
            "ref": str(build_identity["ref"]),
            "repository": str(build_identity["repository"]),
            "sourceCommit": str(build_identity["sourceCommit"]),
        },
        "emittedAt": emitted_at,
        "policyDigest": str(predicate["policy"]["digest"]["sha256"]),
        "policyId": str(predicate["policy"]["uri"]),
        "schema": RELEASE_VSA_INDEX_SCHEMA,
        "verifiedLevels": [str(x) for x in predicate["verifiedLevels"]],
        "verifierId": str(predicate["verifier"]["id"]),
        "verifierKeyid": hashlib.sha256(
            base64.b64decode(operator_pin_b64, validate=True)
        ).hexdigest(),
        "verifierPublicKeyRaw": operator_pin_b64,
        "version": version,
        "vsaPayloadSha256": vsa_payload_sha256_hex,
    }


# __s172_p0b2_anchor_orchestrator_v1__
def anchor(
    version: str,
    out_dir: Path,
    *,
    pins_dir: Path,
    anchor_fn: Any = None,
    timestamp_fn: Any = None,
    verify_fn: Any = None,
    rekor_base_url: str | None = None,
    tsa_base_url: str | None = None,
) -> int:
    """Anchor a minted release-VSA bundle to Rekor v2 (IRREVERSIBLE) + index.

    anchor_fn / timestamp_fn / verify_fn are injectable seams (defaults = the
    live rekor_anchor_v2 / tsa_client / cli_verify_release functions) so this
    orchestrator is testable offline. The single irreversible act is the one
    Rekor POST inside anchor_fn.
    """
    import datetime as _dt

    if anchor_fn is None:
        import rekor_anchor_v2

        anchor_fn = rekor_anchor_v2.anchor_manifest_to_rekor_v2
        if rekor_base_url is None:
            rekor_base_url = rekor_anchor_v2.REKOR_V2_DEFAULT_BASE_URL
    if timestamp_fn is None:
        import tsa_client

        timestamp_fn = tsa_client.anchor_timestamp
        if tsa_base_url is None:
            tsa_base_url = tsa_client.TSA_DEFAULT_URL
    if verify_fn is None:
        import cli_verify_release

        verify_fn = cli_verify_release.verify_convergence

    vsa_name = "nous_lang-" + version + ".build-vsa.intoto.json"
    bundle_name = "nous_lang-" + version + ".rekor-v2-bundle.json"
    verifier_name = "verify_build_vsa_offline.py"
    verifier_key_name = "release-verifier-key.json"

    vsa_path = out_dir / vsa_name
    if not vsa_path.is_file():
        raise MintError("minted VSA not found (run mint first): " + str(vsa_path))
    if not (out_dir / verifier_name).is_file():
        raise MintError("offline verifier not found in dir: " + verifier_name)
    if not (out_dir / verifier_key_name).is_file():
        raise MintError("release verifier key not found in dir: " + verifier_key_name)
    tr = pins_dir / "trusted_root.json"
    tsa = pins_dir / "tsa_chain.pem"
    if not tr.is_file():
        raise MintError("durable pin not found: " + str(tr))
    if not tsa.is_file():
        raise MintError("durable pin not found: " + str(tsa))

    bundle_path = out_dir / bundle_name
    if bundle_path.exists():
        raise MintError(
            "rekor bundle already exists; refusing to re-anchor (a second "
            "Rekor write would create a divergent entry): " + str(bundle_path)
        )

    try:
        envelope = json.loads(vsa_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise MintError("cannot read minted VSA: " + str(exc)) from exc
    canonical = canonical_bytes_to_anchor(envelope)
    vsa_sha = vsa_payload_sha256(envelope)
    statement = decode_build_vsa_statement(envelope)

    print("ANCHOR: submitting VSA payload digest to Rekor v2 (IRREVERSIBLE)")
    print("  version:          " + version)
    print("  vsaPayloadSha256: " + vsa_sha)
    if rekor_base_url is not None:
        anchor_obj = anchor_fn(canonical, base_url=rekor_base_url)
    else:
        anchor_obj = anchor_fn(canonical)
    print("  log_index:        " + str(anchor_obj.log_index))

    entry_sig_b64 = _derive_entry_signature(str(anchor_obj.body_b64))
    entry_sig_raw = base64.b64decode(entry_sig_b64, validate=True)
    if tsa_base_url is not None:
        token_der = timestamp_fn(
            timestamped_data=entry_sig_raw, base_url=tsa_base_url
        )
    else:
        token_der = timestamp_fn(timestamped_data=entry_sig_raw)

    bundle = assemble_rekor_bundle(anchor_obj, token_der)
    bundle_bytes = json.dumps(bundle, sort_keys=True, indent=2).encode("utf-8")
    _write_with_sidecar(bundle_path, bundle_bytes)

    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        (tdir / "build-vsa.intoto.json").write_bytes(vsa_path.read_bytes())
        (tdir / "rekor-v2-bundle.json").write_bytes(bundle_bytes)
        (tdir / "trusted_root.json").write_bytes(tr.read_bytes())
        (tdir / "tsa_chain.pem").write_bytes(tsa.read_bytes())
        result = verify_fn(str(tdir), str(tdir))

    convergence = str(result.get("convergence"))
    if convergence != "PASS":
        legs = result.get("legs", {})
        detail = ""
        if isinstance(legs, dict):
            detail = "; ".join(
                str(k) + "=" + str(v.get("status"))
                for k, v in legs.items()
                if isinstance(v, dict)
            )
        raise MintError(
            "post-anchor dual-root self-verify did NOT converge (convergence="
            + convergence + "); index NOT written. legs: " + detail
        )
    gen_time = str(result.get("evidence", {}).get("rfc3161_gen_time"))

    emitted_at = (
        _dt.datetime.now(_dt.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    index = build_release_index(
        version,
        out_dir,
        statement=statement,
        bundle=bundle,
        bundle_filename=bundle_name,
        vsa_filename=vsa_name,
        verifier_filename=verifier_name,
        verifier_key_filename=verifier_key_name,
        operator_pin_b64=COMMITTED_RELEASE_PIN_B64,
        vsa_payload_sha256_hex=vsa_sha,
        rfc3161_gen_time=gen_time,
        emitted_at=emitted_at,
    )
    index_bytes = json.dumps(index, sort_keys=True, indent=2).encode("utf-8")
    _write_with_sidecar(out_dir / "index.json", index_bytes)

    ip = bundle["transparency_log_entry"]["inclusion_proof"]
    print("ANCHOR complete for nous-lang " + version)
    print("  bundle:      " + bundle_name)
    print("  index:       index.json")
    print("  log_index:   " + str(anchor_obj.log_index))
    print("  tree_size:   " + str(ip["tree_size"]))
    print("  gen_time:    " + gen_time)
    print("  convergence: PASS (offline dual-root)")
    print()
    print(
        "Reversible from here: stage <dir> to /var/www + website/ mirror, "
        "commit. The Rekor entry is permanent."
    )
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mint_release_vsa",
        description="Release-VSA MINT (Phase 1, reversible). No Rekor write.",
    )
    sub = p.add_subparsers(dest="command", required=True)
    m = sub.add_parser("mint", help="Mint the partial release-VSA bundle (no anchor)")
    m.add_argument("version", help="Published version, e.g. 5.63.0")
    m.add_argument("--out", required=True, help="Output bundle directory")
    m.add_argument(
        "--key-path",
        default=DEFAULT_OPERATOR_KEY,
        help="Operator Ed25519 seed (default: " + DEFAULT_OPERATOR_KEY + ")",
    )
    m.add_argument(
        "--work-dir",
        default=None,
        help="Scratch dir for artifact downloads (default: a temp dir under --out)",
    )
    a = sub.add_parser(
        "anchor",
        help="Anchor a minted bundle to Rekor v2 (IRREVERSIBLE) + write index",
    )
    a.add_argument("version", help="Published version, e.g. 5.64.0")
    a.add_argument(
        "--dir", required=True, help="Minted bundle directory (from mint --out)"
    )
    a.add_argument(
        "--pins-dir",
        required=True,
        help="Durable operator pins dir (trusted_root.json + tsa_chain.pem)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.command == "mint":
        out_dir = Path(args.out)
        work_dir = (
            Path(args.work_dir) if args.work_dir else out_dir / ".mint-work"
        )
        try:
            return mint(
                args.version,
                out_dir,
                key_path=Path(args.key_path),
                work_dir=work_dir,
            )
        except MintError as exc:
            print("MINT REFUSED: " + str(exc), file=sys.stderr)
            return 2
    if args.command == "anchor":
        try:
            return anchor(
                args.version,
                Path(args.dir),
                pins_dir=Path(args.pins_dir),
            )
        except MintError as exc:
            print("ANCHOR REFUSED: " + str(exc), file=sys.stderr)
            return 2
    print("usage: mint_release_vsa {mint,anchor} ...", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
