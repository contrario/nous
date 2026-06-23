"""nous vsa -- emit and verify a SLSA Verification Summary Attestation.
# __s157_u3_cli_vsa_module_v1__

`nous vsa emit <trace.json> --manifest <m.json> --cert <c.json>
   [--coverage <coverage.farkas.json>] --out <dir> [--key-path <p>]`
   Builds a DSSE-wrapped in-toto VSA over the signed manifest / trace /
   certificate, signs it with the persistent NOUS VSA key, and writes a
   complete self-verifying bundle into <dir>: the input artifacts (copied
   byte-for-byte), vsa.intoto.json, and verify_vsa_offline.py.

`nous vsa verify <vsa.intoto.json> [--dir <d>] [--key-path <p>]`
   Internal validation path: copies the bundle into a temp directory, emits
   the offline verifier pinned to the local VSA key, and runs it. This
   executes the EXACT artifact a consumer runs (single source, zero drift)
   without mutating the bundle. Third-party verification uses the shipped
   verify_vsa_offline.py with the registry-pinned key.

Digest discipline. The manifest / trace / certificate input-attestation
digests are computed by the SAME file-strip canonical method the offline
verifier uses (strip signature/transparency_log, sorted-keys compact JSON,
sha256), so the emitted digests equal what the verifier recomputes. The
conformance verdict is re-derived from the certificate's eight obligations,
never trusted from its recorded boolean, so the VSA can never be internally
inconsistent with what the verifier independently derives.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import vsa
import vsa_verifier

_INPUT_NAMES = (
    "manifest.json",
    "trace.json",
    "conformance.json",
    "coverage.farkas.json",
    "cost.farkas.json",  # __s170_leg3b_cli_vsa_cost_v1__
)


def _canon(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _manifest_canonical_body_bytes(doc: dict) -> bytes:
    body = {
        k: v for k, v in doc.items()
        if k not in ("signature", "transparency_log")
    }
    return _canon(body)


def _trace_canonical_body_bytes(doc: dict) -> bytes:
    body = {k: v for k, v in doc.items() if k != "signature"}
    return _canon(body)


def _cert_canonical_body_bytes(doc: dict) -> bytes:
    body = {
        k: v for k, v in doc.items()
        if k not in ("signature", "transparency_log")
    }
    if int(body.get("certificate_schema_version", 1)) < 2:
        body.pop("sequence_ok", None)
    return _canon(body)


def build_vsa_parser(sub: "argparse._SubParsersAction") -> None:
    p = sub.add_parser(
        "vsa",
        help="Emit/verify a SLSA Verification Summary Attestation (VSA)",
    )
    vs = p.add_subparsers(dest="vsa_command", required=True)

    e = vs.add_parser(
        "emit",
        help="Emit a signed VSA + offline verifier bundle",
    )
    e.add_argument("trace", help="Path to the signed trace.json")
    e.add_argument(
        "--manifest", required=True, help="Path to the signed manifest.json"
    )
    e.add_argument(
        "--cert", required=True, dest="cert",
        help="Path to the signed conformance.json certificate",
    )
    e.add_argument(
        "--coverage", default=None,
        help="Optional coverage.farkas.json (adds the offline PROVES leg)",
    )
    e.add_argument(  # __s170_leg3b_cli_vsa_cost_v1__
        "--cost", default=None,
        help="Optional cost.farkas.json (adds the offline cost-cap "
             "Farkas PROVES leg, bounded to declared token/tick)",
    )
    e.add_argument(
        "--out", required=True, help="Output bundle directory"
    )
    e.add_argument(
        "--registry", default=None,
        help="Optional signed verifier-registry.json to bundle; its "
        "pinned operator key is baked into the emitted verifier so a "
        "consumer can resolve the VSA key by verifier_id. Off by "
        "default; bundles are byte-identical unless passed.",
    )
    e.add_argument(
        "--no-inline-pin", action="store_true",
        help="Emit a registry-only verifier: leave the inline VSA key "
        "unprovisioned so the consumer MUST resolve it from the bundled "
        "registry. Requires --registry.",
    )
    e.add_argument(
        "--key-path", default=None,
        help="VSA signing key path (default: ~/.local/share/nous/keys/"
             "vsa_signing.key)",
    )

    v = vs.add_parser(
        "verify",
        help="Verify a VSA bundle in-process (internal validation path)",
    )
    v.add_argument("vsa", help="Path to vsa.intoto.json")
    v.add_argument(
        "--dir", default=None,
        help="Bundle directory (default: the vsa.intoto.json directory)",
    )
    v.add_argument(
        "--key-path", default=None, help="VSA signing key path"
    )


def _load_json(path: Path, label: str) -> dict:
    if not path.is_file():
        raise FileNotFoundError(label + " not found: " + str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _cmd_emit(args: argparse.Namespace) -> int:
    trace_path = Path(args.trace)
    manifest_path = Path(args.manifest)
    cert_path = Path(args.cert)
    out_dir = Path(args.out)

    _registry_arg = getattr(args, "registry", None)  # __s158_u2b_fix_getattr_v1__
    registry_src = Path(_registry_arg) if _registry_arg else None
    registry_pin = None
    reg_vsa_pub = None
    if getattr(args, "no_inline_pin", False) and registry_src is None:
        print(
            "PRECONDITION ERROR: --no-inline-pin requires --registry "
            "(registry-only mode needs a registry to resolve the VSA "
            "key)",
            file=sys.stderr,
        )
        return 2
    if registry_src is not None:
        import verifier_registry
        if not registry_src.is_file():
            print(
                "PRECONDITION ERROR: registry not found: "
                + str(registry_src),
                file=sys.stderr,
            )
            return 2
        try:
            registry_doc = json.loads(
                registry_src.read_text(encoding="utf-8")
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(
                "PRECONDITION ERROR: registry parse error: " + str(exc),
                file=sys.stderr,
            )
            return 2
        det = verifier_registry.verify_registry(registry_doc)
        if not det.signature_ok:
            print(
                "PRECONDITION ERROR: registry signature does not verify "
                "against a pinned operator key (errors: "
                + str(det.errors) + ")",
                file=sys.stderr,
            )
            return 2
        sigblock = registry_doc.get("signature") or {}
        registry_pin = sigblock.get("public_key_b64")
        if not registry_pin:
            print(
                "PRECONDITION ERROR: registry has no signer public key",
                file=sys.stderr,
            )
            return 2
        for pin in registry_doc.get("verifier_pins") or []:
            if (
                isinstance(pin, dict)
                and pin.get("verifier_id") == vsa.NOUS_VSA_VERIFIER_ID
            ):
                reg_vsa_pub = pin.get("public_key_b64")
                break
        if reg_vsa_pub is None:
            print(
                "PRECONDITION ERROR: registry has no verifier_pins entry "
                "for " + vsa.NOUS_VSA_VERIFIER_ID,
                file=sys.stderr,
            )
            return 2

    try:
        manifest_doc = _load_json(manifest_path, "manifest")
        trace_doc = _load_json(trace_path, "trace")
        cert_doc = _load_json(cert_path, "certificate")
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print("PRECONDITION ERROR: " + str(exc), file=sys.stderr)
        return 2

    manifest_sha = hashlib.sha256(
        _manifest_canonical_body_bytes(manifest_doc)
    ).hexdigest()
    trace_sha = hashlib.sha256(
        _trace_canonical_body_bytes(trace_doc)
    ).hexdigest()
    cert_sha = hashlib.sha256(
        _cert_canonical_body_bytes(cert_doc)
    ).hexdigest()

    schema_v = int(cert_doc.get("certificate_schema_version", 1))
    derived = all(
        bool(cert_doc.get(b)) for b in vsa.OBLIGATION_NAMES
    )
    errors = tuple(cert_doc.get("errors") or ())

    coverage_sha = None
    coverage_doc = None
    coverage_bytes = None
    if args.coverage is not None:
        cov_path = Path(args.coverage)
        if not cov_path.is_file():
            print(
                "PRECONDITION ERROR: coverage file not found: "
                + str(cov_path),
                file=sys.stderr,
            )
            return 2
        coverage_bytes = cov_path.read_bytes()
        coverage_sha = hashlib.sha256(coverage_bytes).hexdigest()
        man_far = manifest_doc.get("coverage_farkas_sha256")
        if man_far is None:
            print(
                "PRECONDITION ERROR: --coverage given but the manifest "
                "declares no coverage_farkas_sha256 (no coverage proof was "
                "bound at verification time)",
                file=sys.stderr,
            )
            return 2
        if man_far != coverage_sha:
            print(
                "PRECONDITION ERROR: coverage.farkas.json sha256 does not "
                "match manifest.coverage_farkas_sha256 (wrong or tampered "
                "Farkas certificate)",
                file=sys.stderr,
            )
            return 2
        try:
            coverage_doc = json.loads(coverage_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(
                "PRECONDITION ERROR: coverage.farkas.json parse error: "
                + str(exc),
                file=sys.stderr,
            )
            return 2

    cost_sha = None  # __s170_leg3b_cli_vsa_cost_v1__
    cost_doc = None
    cost_bytes = None
    _cost_arg = getattr(args, "cost", None)  # __s170_leg3b_hotfix_getattr_v1__
    if _cost_arg is not None:
        cost_path = Path(_cost_arg)
        if not cost_path.is_file():
            print(
                "PRECONDITION ERROR: cost file not found: "
                + str(cost_path),
                file=sys.stderr,
            )
            return 2
        cost_bytes = cost_path.read_bytes()
        cost_sha = hashlib.sha256(cost_bytes).hexdigest()
        man_cost = manifest_doc.get("cost_farkas_sha256")
        if man_cost is None:
            print(
                "PRECONDITION ERROR: --cost given but the manifest "
                "declares no cost_farkas_sha256 (no cost-cap proof was "
                "bound at verification time)",
                file=sys.stderr,
            )
            return 2
        if man_cost != cost_sha:
            print(
                "PRECONDITION ERROR: cost.farkas.json sha256 does not "
                "match manifest.cost_farkas_sha256 (wrong or tampered "
                "Farkas certificate)",
                file=sys.stderr,
            )
            return 2
        try:
            cost_doc = json.loads(cost_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(
                "PRECONDITION ERROR: cost.farkas.json parse error: "
                + str(exc),
                file=sys.stderr,
            )
            return 2

    nous_version = cert_doc.get("nous_version")
    if not nous_version:
        from _version import __version__ as nous_version

    statement = vsa.build_vsa_statement(
        world_name=cert_doc.get("world_name", ""),
        nous_version=nous_version,
        issued_utc=cert_doc.get("issued_utc", ""),
        codegen_sha256=cert_doc.get("codegen_sha256"),
        source_sha256=cert_doc.get("source_sha256", ""),
        manifest_canonical_sha256=manifest_sha,
        trace_canonical_sha256=trace_sha,
        certificate_canonical_sha256=cert_sha,
        conformant=derived,
        errors=errors,
        certificate_schema_version=schema_v,
        coverage_farkas_sha256=coverage_sha,
        coverage_farkas_doc=coverage_doc,
        cost_farkas_sha256=cost_sha,  # __s170_leg3b_cli_vsa_cost_v1__
        cost_farkas_doc=cost_doc,
    )

    priv, pub, key_path = vsa.load_or_create_vsa_keypair(
        Path(args.key_path) if args.key_path else None
    )
    envelope = vsa.sign_vsa(statement, priv)

    out_dir.mkdir(parents=True, exist_ok=True)
    src_by_name = {
        "manifest.json": manifest_path,
        "trace.json": trace_path,
        "conformance.json": cert_path,
    }
    for name, src in src_by_name.items():
        dst = out_dir / name
        if src.resolve() != dst.resolve():
            dst.write_bytes(src.read_bytes())
    if coverage_bytes is not None:
        (out_dir / "coverage.farkas.json").write_bytes(coverage_bytes)
    if cost_bytes is not None:  # __s170_leg3b_cli_vsa_cost_v1__
        (out_dir / "cost.farkas.json").write_bytes(cost_bytes)
    if registry_src is not None:
        (out_dir / "verifier-registry.json").write_bytes(
            registry_src.read_bytes()
        )

    (out_dir / "vsa.intoto.json").write_text(
        json.dumps(envelope, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    inline_pin = (
        None if getattr(args, "no_inline_pin", False)
        else vsa.public_key_raw_b64(pub)
    )
    if (
        registry_src is not None
        and not getattr(args, "no_inline_pin", False)
        and reg_vsa_pub != vsa.public_key_raw_b64(pub)
    ):
        print(
            "PRECONDITION ERROR: the registry pinned VSA key does not "
            "match this bundle signing key; emitting would ship a bundle "
            "the offline verifier rejects (hard-fail-on-conflict). "
            "Re-anchor the registry for this VSA identity, or use "
            "--no-inline-pin.",
            file=sys.stderr,
        )
        return 2
    verifier_path = vsa_verifier.emit_vsa_verifier(
        str(out_dir),
        pinned_pubkey_b64=inline_pin,
        pinned_registry_pubkey_b64=registry_pin,
    )

    print("VSA bundle written to " + str(out_dir))
    print("  vsa.intoto.json")
    print("  verify_vsa_offline.py")
    for name in src_by_name:
        print("  " + name)
    if coverage_bytes is not None:
        print("  coverage.farkas.json")
    if cost_bytes is not None:  # __s170_leg3b_cli_vsa_cost_v1__
        print("  cost.farkas.json")
    print(
        "verificationResult   "
        + statement["predicate"]["verificationResult"]
    )
    print(
        "subject.digest       "
        + statement["subject"][0]["digest"]["sha256"][:16] + "..."
        + " (" + statement["predicate"][vsa.NOUS_EXT_KEY]["subjectDigestKind"]
        + ")"
    )
    print("signing key          " + str(key_path))
    print("verifier             " + str(verifier_path))
    if coverage_sha is not None:
        print("coverageProof        PROVES (Farkas, offline-re-provable)")
    else:
        print("coverageProof        none (no Farkas leg carried)")
    if cost_sha is not None:  # __s170_leg3b_cli_vsa_cost_v1__
        print("costProof            PROVES (Farkas, offline-re-provable, "
              "bounded to declared token/tick)")
    else:
        print("costProof            none (no Farkas leg carried)")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    vsa_path = Path(args.vsa)
    if not vsa_path.is_file():
        print(
            "PRECONDITION ERROR: vsa.intoto.json not found: " + str(vsa_path),
            file=sys.stderr,
        )
        return 2
    bundle_dir = Path(args.dir) if args.dir else vsa_path.parent

    priv, pub, _key_path = vsa.load_or_create_vsa_keypair(
        Path(args.key_path) if args.key_path else None
    )
    pinned = vsa.public_key_raw_b64(pub)

    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        (tdir / "vsa.intoto.json").write_bytes(vsa_path.read_bytes())
        for name in _INPUT_NAMES:
            src = bundle_dir / name
            if src.is_file():
                (tdir / name).write_bytes(src.read_bytes())
        vsa_verifier.emit_vsa_verifier(str(tdir), pinned)
        result = subprocess.run(
            [sys.executable, str(tdir / "verify_vsa_offline.py")],
            capture_output=True, text=True, cwd=str(tdir),
        )
    sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


def cmd_vsa(args: argparse.Namespace) -> int:
    command = getattr(args, "vsa_command", None)
    if command == "emit":
        return _cmd_emit(args)
    if command == "verify":
        return _cmd_verify(args)
    print("usage: nous vsa {emit|verify}", file=sys.stderr)
    return 1
