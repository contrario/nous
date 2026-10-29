"""
offline_verifier_builder.py -- assemble a standalone verify_offline.py for
Rekor v2-anchored NOUS dossiers.

DERIVED, not transcribed. The v2 read-path logic is extracted at build time
from the three wheel-shipped modules (rekor_entry, rekor_checkpoint,
rekor_verify_v2) so the assembled verifier and the in-package verifier share
a single source of truth (axiom 1). The assembled verifier runs with
cryptography + stdlib only (no pydantic, no nous install): the one pydantic
class in the v2 path (RekorAnchorV2) is replaced by a behavior-identical
pydantic-free shim, pinned by the anti-drift test.

Extraction is AST-segment based with per-symbol sha256 pins. Each required
symbol is located by name; the sha256 of its exact source segment is checked
against a pinned value. Drift in a pinned symbol refuses; drift elsewhere is
ignored. __session90_offline_verifier_builder_v1__
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent


class OfflineVerifierBuildError(RuntimeError):
    """Assembly precondition failed (missing symbol or pinned-segment drift)."""


_ENTRY_SYMBOLS = (
    "RekorEntryError",
    "RekorEntryUnsupported",
    "RekorEntryMalformed",
    "_HEXDIGITS",
    "_V2_HASH_ALGORITHMS",
    "NormalizedLeaf",
    "_require_mapping",
    "_require_str",
    "_b64_to_bytes",
    "_pem_b64_to_der",
    "_digest_hex_from_hex",
    "_digest_hex_from_b64",
    "_parse_v1",
    "_parse_v2",
    "parse_rekor_leaf",
)
_CHECKPOINT_SYMBOLS = (
    "_SIG_PREFIX",
    "_LEAF_PREFIX",
    "_NODE_PREFIX",
    "_ED25519_SIG_TYPE",
    "_SHA256_LEN",
    "CheckpointError",
    "CheckpointMalformed",
    "InclusionProofError",
    "CheckpointSignature",
    "Checkpoint",
    "_b64decode",
    "parse_checkpoint",
    "ed25519_key_id",
    "verify_checkpoint_ed25519",
    "rfc6962_leaf_hash",
    "verify_inclusion_proof",
)
_V2_SYMBOLS = (
    "RekorV2Error",
    "RekorV2AnchorMalformed",
    "RekorV2VerifyDetail",
    "load_trusted_log_keys",
    "verify_rekor_v2_anchor",
)
_TSA_SYMBOLS = (
    "OID_SIGNED_DATA",
    "OID_CT_TSTINFO",
    "OID_ATTR_CONTENT_TYPE",
    "OID_ATTR_MESSAGE_DIGEST",
    "KNOWN_TSA_ROOT_CERTS",
    "_ECDSA_SIG_OIDS",
    "_RSA_SIG_OIDS",
    "_DIGEST_OIDS",
    "Rfc3161Error",
    "Rfc3161Malformed",
    "Rfc3161VerifyDetail",
    "_der_len",
    "_tlv",
    "_children",
    "_oid_str",
    "_parse_token",
    "_parse_tstinfo",
    "verify_rfc3161_timestamp",
)  # __nous_s92_tsa_in_offline_verifier_v1__


_HOISTED_IMPORTS = (
    "from __future__ import annotations\n"
    "\n"
    "import argparse\n"
    "import base64\n"
    "import binascii\n"
    "import hashlib\n"
    "import json\n"
    "import sys\n"
    "from collections.abc import Mapping\n"
    "from dataclasses import dataclass, field\n"
    "from pathlib import Path\n"
    "from datetime import datetime, timezone\n"
    "\n"
    "try:  # __nt_v3_classes_wire_v1__ __nt_v3_review_v1__\n"
    "    from cryptography.exceptions import InvalidSignature\n"
    "    from cryptography import x509\n"
    "    from cryptography.hazmat.primitives import hashes\n"
    "    from cryptography.hazmat.primitives.asymmetric import ec, padding\n"
    "    from cryptography.hazmat.primitives.asymmetric.ec import ECDSA\n"
    "    from cryptography.hazmat.primitives.asymmetric.ed25519 import "
    "Ed25519PublicKey\n"
    "    from cryptography.x509.oid import ExtendedKeyUsageOID\n"
    "    from cryptography.hazmat.primitives.serialization import (\n"
    "        Encoding,\n"
    "        PublicFormat,\n"
    "        load_der_public_key,\n"
    "    )\n"
    "except ImportError as _v3_exc:\n"
    "    print(\"ERROR: a module this verifier needs is missing (\"\n"
    "          + str(_v3_exc) + \"); install: pip install \"\n"
    "          \"'cryptography>=42'\", file=sys.stderr)\n"
    "    print(\"CLASS: ENVIRONMENT\")\n"
    "    sys.exit(2)\n"
)


_ANCHOR_SHIM_LINES = (
    "",
    "",
    "@dataclass(frozen=True, slots=True)",
    "class RekorAnchorV2:",
    "    rekor_api_version: int",
    "    log_id: str",
    "    log_index: int",
    "    body_b64: str",
    "    checkpoint_envelope: str",
    "    inclusion_proof_hashes: tuple",
    "    rfc3161_token_b64: str | None = None",
    "",
    "    @classmethod",
    "    def from_manifest_block(cls, block):",
    "        if block.get('rekor_api_version') != 2:",
    "            raise RekorV2AnchorMalformed(",
    "                'block rekor_api_version is not 2 "
    "(not a v2 anchor block)'",
    "            )",
    "        try:",
    "            hashes_field = block['inclusion_proof_hashes']",
    "            if not isinstance(hashes_field, list):",
    "                raise TypeError("
    "'inclusion_proof_hashes is not a list')",
    "            log_id = block['log_id']",
    "            body_b64 = block['body_b64']",
    "            checkpoint_envelope = block['checkpoint_envelope']",
    "            if not isinstance(log_id, str) or len(log_id) < 1:",
    "                raise ValueError("
    "'log_id must be a non-empty string')",
    "            if not isinstance(body_b64, str) or len(body_b64) < 1:",
    "                raise ValueError("
    "'body_b64 must be a non-empty string')",
    "            if (",
    "                not isinstance(checkpoint_envelope, str)",
    "                or len(checkpoint_envelope) < 1",
    "            ):",
    "                raise ValueError(",
    "                    'checkpoint_envelope must be a non-empty string'",
    "                )",
    "            log_index = block['log_index']",
    "            if isinstance(log_index, bool) or not isinstance("
    "log_index, int):",
    "                raise ValueError('log_index must be an int')",
    "            if log_index < 0:",
    "                raise ValueError('log_index must be >= 0')",
    "            return cls(",
    "                rekor_api_version=2,",
    "                log_id=log_id,",
    "                log_index=log_index,",
    "                body_b64=body_b64,",
    "                checkpoint_envelope=checkpoint_envelope,",
    "                inclusion_proof_hashes=tuple("
    "str(h) for h in hashes_field),",
    "                rfc3161_token_b64=(",
    "                    str(block['rfc3161_token_b64'])",
    "                    if block.get('rfc3161_token_b64') is not None",
    "                    else None",
    "                ),",
    "            )",
    "        except (KeyError, TypeError, ValueError) as exc:",
    "            raise RekorV2AnchorMalformed(",
    "                'invalid v2 anchor block: ' + str(exc)",
    "            ) from exc",
    "",
)


_DISPATCH_MAIN_LINES = (
    "",
    "",
    "ROOT = Path(__file__).resolve().parent",
    "",
    "",
    "def _fail(msg):",
    "    print('FAIL: ' + msg, file=sys.stderr)",
    "    return 1",
    "",
    "",
    "def _load_manifest_body_bytes(manifest):",
    "    body = {",
    "        k: v for k, v in manifest.items()",
    "        if k not in ('signature', 'transparency_log')",
    "    }",
    "    return json.dumps(",
    "        body, sort_keys=True, separators=(',', ':')",
    "    ).encode('utf-8')",
    "",
    "",
    "def _verify_ed25519_author(manifest, body_bytes):",
    "    sig_block = manifest.get('signature')",
    "    if not sig_block:",
    "        return _fail('manifest has no signature block')",
    "    pub_b64 = sig_block.get('public_key_b64', '')",
    "    sig_b64 = sig_block.get('signature_b64', '')",
    "    if not pub_b64 or not sig_b64:",
    "        return _fail('manifest signature block incomplete')",
    "    if not _v3_is_pinned(pub_b64):  # __nt_v3_classes_wire_v1__",
    "        return _fail(",
    "            'manifest signer is not the expected key (--expect-signer)'",
    "        )",
    "    try:",
    "        pub_key = Ed25519PublicKey.from_public_bytes(",
    "            base64.b64decode(pub_b64)",
    "        )",
    "        pub_key.verify(base64.b64decode(sig_b64), body_bytes)",
    "    except InvalidSignature:",
    "        return _fail('Ed25519 signature does NOT verify')",
    "    except Exception as e:",
    "        return _fail('signature verification error: ' + str(e))",
    "    print('OK   Ed25519 manifest signature verified')",
    "    return 0",
    "",
    "",
    "def _verify_source(manifest, root):",
    "    source_path = root / 'source.nous'",
    "    if not source_path.is_file():",
    "        return _fail('source.nous not found in ' + str(root))",
    "    src_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()",
    "    expected = manifest.get('source_sha256', '')",
    "    if src_sha != expected:",
    "        return _fail(",
    "            'source.sha256 mismatch: file=' + src_sha[:16] + '... '",
    "            'manifest=' + expected[:16] + '...'",
    "        )",
    "    print('OK   source.sha256 matches manifest "
    "(' + src_sha[:16] + '...)')",
    "    return 0",
    "",
    "",
    "def main(argv=None):",
    "    parser = argparse.ArgumentParser(",
    "        description=(",
    "            'Offline verification of a NOUS dossier with a Sigstore "
    "Rekor '",
    "            'v2 (tile-backed) transparency log anchor'",
    "        )",
    "    )",
    "    parser.add_argument(",
    "        '--allow-unanchored',",
    "        action='store_true',",
    "        help=(",
    "            'accept dossiers without a transparency_log block; only "
    "the '",
    "            'Ed25519 author signature and source identity are then "
    "verified'",
    "        ),",
    "    )",
    "    parser.add_argument('--expect-signer', default=None)  # __nt_v3_classes_wire_v1__",
    "    args = parser.parse_args(argv)",
    "",
    "    manifest_path = ROOT / 'manifest.json'",
    "    if not manifest_path.is_file():",
    "        return _fail('manifest.json not found in ' + str(ROOT))",
    "    try:",
    "        manifest = json.loads("
    "manifest_path.read_text(encoding='utf-8'))",
    "    except json.JSONDecodeError as e:",
    "        return _fail('manifest.json parse error: ' + str(e))",
    "",
    "    body_bytes = _load_manifest_body_bytes(manifest)",
    "",
    "    rc = _verify_ed25519_author(manifest, body_bytes)",
    "    if rc != 0:",
    "        return rc",
    "    rc = _verify_source(manifest, ROOT)",
    "    if rc != 0:",
    "        return rc",
    "",
    "    print('SCOPE: this verifier carries no cost-cap check (NT-GATE-1 K1.3); '  # __nt_v3_classes_wire_v1__",
    "          'a cost.farkas.json in this dossier is not graded here')",
    "    tlog = manifest.get('transparency_log')",
    "    if tlog is None:",
    "        if not args.allow_unanchored:",
    "            return _fail(",
    "                'transparency_log block missing; the dossier is '",
    "                'unanchored. Re-run with --allow-unanchored to "
    "accept '",
    "                'Ed25519-only verification.'",
    "            )",
    "        if manifest.get('verdict') != 'proven':  # __nt_v3_classes_wire_v1__",
    "            _v3_outside_manifest(manifest)",
    "            _v3_not_claimed('dossier')",
    "            return 0",
    "        print()",
    "        print(",
    "            'VERDICT: PASS (Ed25519 manifest only -- "
    "unanchored dossier)'",
    "        )",
    "        print('  world:        ' + "
    "str(manifest.get('world_name', '?')))",
    "        print(",
    "            '  cost_cap:     $' + "
    "str(manifest.get('cost_cap_usd', '?'))",
    "            + ' USD'",
    "        )",
    "        print('  verdict:      ' + "
    "str(manifest.get('verdict', '?')))",
    "        _v3_not_claimed('dossier')",
    "        return 0",
    "",
    "    if not isinstance(tlog, dict):",
    "        return _fail('transparency_log is not an object')",
    "",
    "    api_version = tlog.get('rekor_api_version')",
    "    if api_version != 2:",
    "        return _fail(",
    "            'transparency_log.rekor_api_version is not 2 (got '",
    "            + repr(api_version)",
    "            + '); this verifier ships with a Rekor v2-anchored "
    "dossier'",
    "        )",
    "",
    "    trusted = load_trusted_log_keys()",
    "    detail = verify_rekor_v2_anchor(",
    "        manifest_body_bytes=body_bytes,",
    "        block=tlog,",
    "        trusted_log_keys=trusted,",
    "    )",
    "",
    "    print(",
    "        '     leaf_digest_ok=' + str(detail.leaf_digest_ok)",
    "        + ' leaf_sig_ok=' + str(detail.leaf_sig_ok)",
    "        + ' checkpoint_sig_ok=' + str(detail.checkpoint_sig_ok)",
    "        + ' inclusion_proof_ok=' + str(detail.inclusion_proof_ok)",
    "    )",
    "    if not detail.ok:",
    "        for err in detail.errors:",
    "            print('     - ' + err, file=sys.stderr)",
    "        return _fail(",
    "            'Rekor v2 anchor verification failed "
    "(see per-step flags above)'",
    "        )",
    "    print(",
    "        'OK   Rekor v2 anchor verified '",
    "        '(log_index=' + str(detail.log_index)",
    "        + ' origin=' + str(detail.checkpoint_origin)",
    "        + ' tree_size=' + str(detail.tree_size) + ')'",
    "    )",
    "    if tlog.get('rfc3161_token_b64') is not None:",
    "        if not detail.timestamp_ok:",
    "            for err in detail.errors:",
    "                print('     - ' + err, file=sys.stderr)",
    "            return _fail(",
    "                'RFC 3161 trusted-timestamp verification failed'",
    "            )",
    "        print(",
    "            'OK   RFC 3161 trusted timestamp ('",
    "            + str(detail.trusted_time) + ')'",
    "        )",
    "",
    "    if manifest.get('verdict') != 'proven':  # __nt_v3_classes_wire_v1__",
    "        _v3_outside_manifest(manifest)",
    "        _v3_not_claimed('dossier')",
    "        return 0",
    "    print()",
    "    print(",
    "        'VERDICT: PASS (Ed25519 manifest + Sigstore Rekor v2 "
    "tile-backed '",
    "        'anchor: leaf ECDSA tie + checkpoint Ed25519 + RFC 6962 "
    "inclusion)'",
    "    )",
    "    print('  world:        ' + str(manifest.get('world_name', '?')))",
    "    cap = manifest.get('cost_cap_usd', '?')",
    "    print('  cost_cap:     $' + str(cap) + ' USD')",
    "    margin = manifest.get('safety_margin_pct')",
    "    if margin:",
    "        try:",
    "            from decimal import Decimal",
    "            eff = Decimal(str(cap)) * Decimal(100 - margin) / "
    "Decimal(100)",
    "            print(",
    "                '  effective:    $' + str(eff)",
    "                + ' USD (' + str(margin) + '% safety margin)'",
    "            )",
    "        except Exception:",
    "            print('  margin:       ' + str(margin) + '%')",
    "    print('  verdict:      ' + str(manifest.get('verdict', '?')))",
    "    print('  solver:       ' + "
    "str(manifest.get('solver_version', '?')))",
    "    print('  timestamp:    ' + "
    "str(manifest.get('timestamp_utc', '?')))",
    "    print('  rekor_log_id: ' + str(tlog.get('log_id')))",
    "    print('  rekor_index:  ' + str(tlog.get('log_index')))",
    "    _v3_not_claimed('dossier')",
    "    return 0",
    "",
    "",
    "if __name__ == '__main__':",
    "    sys.exit(_v3_run(main, ('--allow-unanchored',), True))",
    "",
)


ENTRY_PINS: dict[str, str] = {}
CHECKPOINT_PINS: dict[str, str] = {}
V2_PINS: dict[str, str] = {}
TSA_PINS: dict[str, str] = {}


def _extract_segments(
    module_path: Path,
    symbol_names: tuple[str, ...],
    pins: dict[str, str],
) -> str:
    src = module_path.read_text(encoding="utf-8")
    src_lines = src.splitlines()
    tree = ast.parse(src)
    found: dict[str, str] = {}
    for node in tree.body:
        name = None
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            name = node.name
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    name = t.id
        elif isinstance(node, ast.AnnAssign) and isinstance(
            node.target, ast.Name
        ):
            name = node.target.id
        if name is None or name not in symbol_names:
            continue
        decorators = getattr(node, "decorator_list", [])
        if decorators:
            start_line = min(d.lineno for d in decorators)
            end_line = node.end_lineno
            seg = "\n".join(src_lines[start_line - 1:end_line])
        else:
            seg = ast.get_source_segment(src, node)
        if seg is None:
            raise OfflineVerifierBuildError(
                "could not extract source segment for "
                + name + " in " + module_path.name
            )
        found[name] = seg
    missing = [s for s in symbol_names if s not in found]
    if missing:
        raise OfflineVerifierBuildError(
            "missing symbols in " + module_path.name + ": "
            + ", ".join(missing)
        )
    ordered: list[str] = []
    for s in symbol_names:
        seg = found[s]
        seg_sha = hashlib.sha256(seg.encode("utf-8")).hexdigest()
        pinned = pins.get(s)
        if pinned is not None and pinned != seg_sha:
            raise OfflineVerifierBuildError(
                "pinned-segment drift for " + s + " in "
                + module_path.name + ": expected " + pinned[:16]
                + "... got " + seg_sha[:16] + "..."
            )
        ordered.append(seg)
    return "\n\n".join(ordered)


def build_offline_verifier_v2(allowlist_literal: str = "{}") -> str:
    """Assemble and return the standalone verify_offline.py source string.

    allowlist_literal: a Python dict literal (as text) for
    KNOWN_REKOR_V2_LOG_KEYS, injected at emit time. Defaults to empty
    (fail-closed) for P3d; P3e supplies the pinned production log key.
    """
    entry_body = _extract_segments(
        _PKG_DIR / "rekor_entry.py", _ENTRY_SYMBOLS, ENTRY_PINS
    )
    checkpoint_body = _extract_segments(
        _PKG_DIR / "rekor_checkpoint.py", _CHECKPOINT_SYMBOLS, CHECKPOINT_PINS
    )
    tsa_body = _extract_segments(
        _PKG_DIR / "tsa_verify.py", _TSA_SYMBOLS, TSA_PINS
    )
    v2_body = _extract_segments(
        _PKG_DIR / "rekor_verify_v2.py", _V2_SYMBOLS, V2_PINS
    )

    header = (
        "#!/usr/bin/env python3\n"
        '"""Offline verification of a NOUS dossier (Annex IV) anchored in '
        "a\n"
        "Sigstore Rekor v2 (tile-backed) transparency log.\n"
        "\n"
        "Assembled by offline_verifier_builder.py from the NOUS Rekor v2\n"
        "read-path modules. Runs with cryptography + stdlib only; no NOUS\n"
        "install and no pydantic required.\n"
        "\n"
        "Usage: python3 -I verify_offline.py [--allow-unanchored]"
        " --expect-signer BASE64\n"
        "Exit:  0 = PASS, 1 = INTEGRITY, 2 = ENVIRONMENT, 3 = OUTSIDE (NT-GATE-1\n"
        "       D4). The last line on stdout names the class. No PASS\n"
        "       without --expect-signer. This verifier carries no\n"
        "       cost-cap check: a cost.farkas.json in the dossier is\n"
        "       not graded here (NT-GATE-1 K1.3).\n"  # __nt_v3_classes_wire_v1__
        '"""\n'
    )

    allowlist_block = (
        "\n\nKNOWN_REKOR_V2_LOG_KEYS = " + allowlist_literal + "\n"
    )
    anchor_shim = "\n".join(_ANCHOR_SHIM_LINES)
    dispatch_main = "\n".join(_DISPATCH_MAIN_LINES)

    parts = [
        header,
        _HOISTED_IMPORTS,
        allowlist_block,
        "\n\n" + entry_body + "\n",
        "\n\n" + checkpoint_body + "\n",
        "\n\n" + tsa_body + "\n",
        "\n\n" + v2_body + "\n",
        anchor_shim,
        "\n\n" + _v3_classes_region() + "\n",  # __nt_v3_classes_wire_v1__
        dispatch_main,
    ]
    return "".join(parts)


_CONFORMANCE_DISPATCH_MAIN_LINES = (
    "",
    "",
    "ROOT = Path(__file__).resolve().parent",
    "",
    "_BOOLS_V1 = (",  # __phase2_stage5b_anchored_tpl_v1__
    "    'binding_ok', 'surface_ok', 'assumption_discharge_ok',",
    "    'bound_transfer_ok', 'authorization_ok', 'trace_signature_ok',",
    ")",
    "_BOOLS_V2 = _BOOLS_V1 + ('sequence_ok',)",
    "_BOOLS_V4 = _BOOLS_V2 + ('codegen_binding_ok',)",
    "",
    "def _bools_for(schema_version):",
    "    if schema_version >= 4:",
    "        return _BOOLS_V4",
    "    return _BOOLS_V2 if schema_version >= 2 else _BOOLS_V1",
    "",
    "",
    "def _cfail(msg):",
    "    print('FAIL: ' + msg, file=sys.stderr)",
    "    return 1",
    "",
    "",
    "def _canon(doc, drop):",
    "    body = {k: v for k, v in doc.items() if k not in drop}",
    "    return json.dumps(",
    "        body, sort_keys=True, separators=(',', ':')",
    "    ).encode('utf-8')",
    "",
    "",
    "def _ed25519_ok(pub_b64, sig_b64, body):",
    "    try:",
    "        pub = Ed25519PublicKey.from_public_bytes(",
    "            base64.b64decode(pub_b64, validate=True)",
    "        )",
    "        pub.verify(base64.b64decode(sig_b64, validate=True), body)",
    "        return True",
    "    except (InvalidSignature, ValueError):",
    "        return False",
    "",
    "",
    "# __x_g2_expect_signer_v1__ the expected signer is an auditor argument,",
    "# never a constant in this script, which ships with the evidence.",
    "_PIN_BADKEY = (",
    "    'ERROR: --expect-signer is not a base64 raw 32-byte Ed25519 public key'",
    ")",
    "_SIGNER_SCOPE = (",
    "    'SIGNER: pinned to the auditor-supplied --expect-signer key; who holds '",
    "    'that key is established out of band.'",
    ")",
    "",
    "",
    "def _pin_raw(b64):",
    "    try:",
    "        raw = base64.b64decode(b64, validate=True)",
    "    except (ValueError, TypeError):",
    "        return None",
    "    return raw if len(raw) == 32 else None",
    "",
    "",
    "def main(argv=None):",
    "    parser = argparse.ArgumentParser(",
    "        description=(",
    "            'Offline verification of a NOUS runtime conformance '",
    "            'certificate anchored in a Sigstore Rekor v2 log'",
    "        )",
    "    )",
    "    parser.add_argument('--allow-unanchored', action='store_true')",
    "    parser.add_argument('--expect-signer', default=None)",
    "    parser.add_argument('--expect-manifest-signer', default=None)  # __nt_v3_classes_wire_v1__",
    "    args = parser.parse_args(argv)",
    "    pin = None",
    "    if args.expect_signer is not None:",
    "        pin = _pin_raw(args.expect_signer)",
    "        if pin is None:",
    "            print(_PIN_BADKEY, file=sys.stderr)",
    "            return 2",
    "",
    "    cert_p = ROOT / 'conformance.json'",
    "    trace_p = ROOT / 'trace.json'",
    "    man_p = ROOT / 'manifest.json'",
    "    for label, pth in (",
    "        ('conformance.json', cert_p),",
    "        ('trace.json', trace_p),",
    "        ('manifest.json', man_p),",
    "    ):",
    "        if not pth.is_file():",
    "            return _cfail(label + ' not found in ' + str(ROOT))",
    "    try:",
    "        cert = json.loads(cert_p.read_text(encoding='utf-8'))",
    "        manifest = json.loads(man_p.read_text(encoding='utf-8'))",
    "    except json.JSONDecodeError as e:",
    "        return _cfail('JSON parse error: ' + str(e))",
    "    # __nt_v2_recompute_wire_v1__ strict trace when a canon is carried",
    "    if isinstance(cert, dict) and cert.get('obligations_canon') is not None:",
    "        trace, _why = _conf_rc_load(trace_p.read_bytes())",
    "        if trace is None:",
    "            return _cfail('trace.json refused: ' + _why)",
    "    else:",
    "        try:",
    "            trace = json.loads(trace_p.read_text(encoding='utf-8'))",
    "        except json.JSONDecodeError as e:",
    "            return _cfail('JSON parse error: ' + str(e))",
    "",
    "    csig = cert.get('signature')",
    "    if not isinstance(csig, dict):",
    "        return _cfail('certificate has no signature block')",
    "    cert_body = _canon(cert, ('signature', 'transparency_log'))",
    "    cpub = csig.get('public_key_b64', '')",
    "    if pin is not None:",
    "        try:",
    "            if base64.b64decode(cpub, validate=True) != pin:",
    "                return _cfail('certificate signer is not the expected key')",
    "        except (ValueError, TypeError):",
    "            return _cfail('certificate signer is not the expected key')",
    "        cpub = base64.b64encode(pin).decode('ascii')",
    "    if not _ed25519_ok(",
    "        cpub,",
    "        csig.get('signature_b64', ''),",
    "        cert_body,",
    "    ):",
    "        return _cfail('certificate Ed25519 signature does NOT verify')",
    "    print('OK   certificate Ed25519 signature verified')",
    "    if pin is not None:",
    "        print('OK   certificate signer is the expected key (--expect-signer)')",
    "    msig = manifest.get('signature')  # __nt_v3_classes_wire_v1__",
    "    if not isinstance(msig, dict) or not _v3_is_pinned(",
    "        msig.get('public_key_b64', ''), '--expect-manifest-signer'",
    "    ):",
    "        return _cfail('manifest signer is not the expected key '",
    "                      '(--expect-manifest-signer, else '",
    "                      '--expect-signer)')",
    "    if not _ed25519_ok(",
    "        _v3_pin_b64('--expect-manifest-signer'),",
    "        msig.get('signature_b64', ''),",
    "        _v3_manifest_body(manifest),",
    "    ):",
    "        return _cfail('manifest Ed25519 signature does NOT verify under '",
    "                      'the expected key')",
    "    print('OK   manifest signed by the expected key')",
    "",
    "    trace_sha = hashlib.sha256(",
    "        _canon(trace, ('signature',))",
    "    ).hexdigest()",
    "    if cert.get('trace_sha256') != trace_sha:",
    "        return _cfail('cert.trace_sha256 != sha256(trace body)')",
    "    print('OK   certificate bound to this trace (sha256 match)')",
    "",
    "    for fld in ('source_sha256', 'smt_spec_sha256', 'pricing_sha256'):",
    "        if cert.get(fld) != manifest.get(fld):",
    "            return _cfail('cert.' + fld + ' != manifest.' + fld)",
    "    print('OK   certificate bound to this manifest (3 shas match)')",
    "",
    "    cert_cg = cert.get('codegen_sha256')",
    "    if cert_cg is not None:",
    "        man_cg = manifest.get('codegen_sha256')",
    "        if man_cg is not None and man_cg != cert_cg:",
    "            return _cfail('cert.codegen_sha256 != manifest.codegen_sha256')",
    "        tr_cg = trace.get('codegen_sha256')",
    "        if tr_cg is not None and tr_cg != cert_cg:",
    "            return _cfail('cert.codegen_sha256 != trace.codegen_sha256')",
    "        print('OK   codegen leg: one compiled program (sha-equality)')",
    "",
    "    tsig = trace.get('signature')",
    "    if not isinstance(tsig, dict):",
    "        return _cfail('trace has no signature block')",
    "    if not _ed25519_ok(",
    "        tsig.get('public_key_b64', ''),",
    "        tsig.get('signature_b64', ''),",
    "        _canon(trace, ('signature',)),",
    "    ):",
    "        return _cfail('trace Ed25519 signature does NOT verify')",
    "    print('OK   trace Ed25519 signature verified')",
    "",
    "    schema_v = int(cert.get('certificate_schema_version', 1))",  # __phase2_stage5b_anchored_tpl_v1__
    "    bools = _bools_for(schema_v)",
    "    missing = [b for b in bools if b not in cert]",
    "    if missing:",
    "        return _cfail('certificate missing fields: ' + str(missing))",
    "    derived = all(bool(cert[b]) for b in bools)",
    "    recorded = bool(cert.get('conformant'))",
    "    if derived != recorded:",
    "        return _cfail(",
    "            'conformant=' + str(recorded) + ' inconsistent with '",
    "            'the ' + str(len(bools)) + ' obligations (' + str(derived) + ')'",
    "        )",
    "    print('OK   recorded verdict consistent with ' + str(len(bools)) + ' obligations (schema v' + str(schema_v) + ')')",
    "    _rc_status, _rc = _conf_recompute(  # __nt_v2_recompute_wire_v1__",
    "        manifest, cert, trace, cert.get('obligations_canon')",
    "    )",
    "    if _rc_status == 'refused':",
    "        return _cfail('recomputation refused: ' + _rc['reason'])",
    "    if _rc_status == 'recomputed':",
    "        if _rc['disagree']:",
    "            return _cfail(_rc['disagree'][0])",
    "        print('OK   ' + _rc['line'])",
    "        print('NOT RECOMPUTED: authorization_ok, sequence_ok (the '",
    "              \"certificate's recorded booleans)\")",
    "    else:",
    "        print('NOT RECOMPUTED: no spec canon in the certificate; the '",
    "              \"obligations are the certificate's recorded booleans\")",
    "",
    "    tlog = cert.get('transparency_log')",
    "    if tlog is None:",
    "        if not args.allow_unanchored:",
    "            return _cfail(",
    "                'transparency_log block missing; certificate is '",
    "                'unanchored. Re-run with --allow-unanchored to accept '",
    "                'Ed25519 + binding verification only.'",
    "            )",
    "        print()",
    "        print('VERDICT: ' + ('PASS' if recorded else 'OUTSIDE')  # __nt_v3_classes_wire_v1__",
    "              + ' (signed certificate, unanchored'",
    "              + ('' if recorded else '; authentic under the expected '",
    "                 'key, the bound was not held') + ')')",
    "        print(_SIGNER_SCOPE)",
    "        _v3_not_claimed('runtime')",
    "        return 0 if recorded else 3",
    "",
    "    if not isinstance(tlog, dict):",
    "        return _cfail('transparency_log is not an object')",
    "    if tlog.get('rekor_api_version') != 2:",
    "        return _cfail('transparency_log.rekor_api_version is not 2')",
    "",
    "    trusted = load_trusted_log_keys()",
    "    detail = verify_rekor_v2_anchor(",
    "        manifest_body_bytes=cert_body,",
    "        block=tlog,",
    "        trusted_log_keys=trusted,",
    "    )",
    "    print(",
    "        '     leaf_digest_ok=' + str(detail.leaf_digest_ok)",
    "        + ' leaf_sig_ok=' + str(detail.leaf_sig_ok)",
    "        + ' checkpoint_sig_ok=' + str(detail.checkpoint_sig_ok)",
    "        + ' inclusion_proof_ok=' + str(detail.inclusion_proof_ok)",
    "    )",
    "    if not detail.ok:",
    "        for err in detail.errors:",
    "            print('     - ' + err, file=sys.stderr)",
    "        return _cfail('Rekor v2 anchor verification failed')",
    "    print(",
    "        'OK   Rekor v2 anchor verified over certificate body '",
    "        '(log_index=' + str(detail.log_index) + ')'",
    "    )",
    "",
    "    print()",
    "    print('VERDICT: ' + ('PASS' if recorded else 'OUTSIDE')  # __nt_v3_classes_wire_v1__",
    "          + ' (signed certificate + Sigstore Rekor v2 anchor'",
    "          + ('' if recorded else '; authentic under the expected '",
    "             'key, the bound was not held') + ')')",
    "    print('  world:          ' + str(cert.get('world_name', '?')))",
    "    print('  realized_total: ' + str(cert.get('realized_total', '?'))",
    "          + ' ' + str(cert.get('cost_currency', '')))",
    "    print('  cost_cap:       ' + str(cert.get('cost_cap', '?'))",
    "          + ' ' + str(cert.get('cost_currency', '')))",
    "    print('  conformant:     ' + str(recorded))",
    "    _mc = trace.get('memory_consultation')",  # __s107_u6_memory_visibility_v1__
    "    if isinstance(_mc, dict):",
    "        print('  memory:         consulted (Phase 1)')",
    "        print('    soul:         ' + str(_mc.get('producing_soul_sha256', '?'))[:16] + '...')",
    "        print('    chain_head:   ' + str(_mc.get('consulted_chain_head', '?'))[:16] + '...')",
    "        print('    entries:      ' + str(_mc.get('consulted_seq_count', '?')))",
    "    print('  rekor_log_id:   ' + str(tlog.get('log_id')))",
    "    print('  rekor_index:    ' + str(tlog.get('log_index')))",
    "    print(_SIGNER_SCOPE)",
    "    _v3_not_claimed('runtime')",
    "    return 0 if recorded else 3",
    "",
    "",
    "if __name__ == '__main__':",
    "    sys.exit(_v3_run(main, ('--allow-unanchored',), True,",
    "                     keyed=('--expect-manifest-signer',)))",
    "",
)  # __nous_conformance_anchored_verifier_v1__


def _conformance_recompute_region() -> str:  # __nt_v2_recompute_wire_v1__
    """The conformance recompute region, read from its canonical copy
    in conformance.py so that both offline conformance texts carry one
    text byte for byte."""
    text = (_PKG_DIR / "conformance.py").read_text(encoding="utf-8")
    start = ("# --- conformance recompute embed (shared text; "
             "canonical copy: conformance.py) ---")
    end = "# --- end conformance recompute embed ---"
    if text.count(start) != 1 or text.count(end) != 1:
        raise RuntimeError("conformance recompute region not found once")
    i = text.index(start)
    return text[i:text.index(end, i) + len(end)]


def _v3_classes_region() -> str:  # __nt_v3_classes_wire_v1__
    """The v3 verdict classes region, read from its canonical copy
    in conformance_verifier.py so that every text in scope carries
    one text byte for byte."""
    text = (_PKG_DIR / "conformance_verifier.py").read_text(encoding="utf-8")
    start = ("# --- v3 verdict classes embed (shared text; "
             "canonical copy: conformance_verifier.py) ---")
    end = "# --- end v3 verdict classes embed ---"
    m = re.search("(?ms)^" + re.escape(start) + "$.*?^"
                  + re.escape(end) + "$", text)
    if m is None:
        raise RuntimeError("v3 verdict classes region not found")
    return m.group(0)


def build_conformance_verifier_v2(allowlist_literal: str = "{}") -> str:
    """Assemble a standalone conformance verifier with Rekor v2 anchor check.

    Reuses the same extracted v2 read-path segments + hoisted imports + anchor
    shim as build_offline_verifier_v2 (single source of truth); only the
    dispatch main() differs (certificate-shaped). __nous_conformance_anchored_verifier_v1__
    """
    entry_body = _extract_segments(
        _PKG_DIR / "rekor_entry.py", _ENTRY_SYMBOLS, ENTRY_PINS
    )
    checkpoint_body = _extract_segments(
        _PKG_DIR / "rekor_checkpoint.py", _CHECKPOINT_SYMBOLS, CHECKPOINT_PINS
    )
    tsa_body = _extract_segments(
        _PKG_DIR / "tsa_verify.py", _TSA_SYMBOLS, TSA_PINS
    )
    v2_body = _extract_segments(
        _PKG_DIR / "rekor_verify_v2.py", _V2_SYMBOLS, V2_PINS
    )
    header = (
        "#!/usr/bin/env python3\n"
        '"""Offline verification of a NOUS runtime conformance certificate\n'
        "anchored in a Sigstore Rekor v2 (tile-backed) transparency log.\n"
        "\n"
        "Assembled by offline_verifier_builder.build_conformance_verifier_v2\n"
        "from the NOUS Rekor v2 read-path modules. cryptography + stdlib only.\n"
        "\n"
        "Verifies, offline: certificate Ed25519 signature, cert<->trace and\n"
        "cert<->manifest binding, trace Ed25519 signature, recorded-verdict\n"
        "consistency, and the Rekor v2 anchor over the certificate body bytes.\n"
        "SCOPE: signatures + binding (including the codegen leg by\n"
        "sha-equality) + anchor inclusion; NOT SMT bound or program\n"
        "re-derivation (those are the online toolchain path). With a\n"
        "spec canon in the certificate, the cost obligations are\n"
        "recomputed from trace.json. The certificate must be signed\n"
        "by the --expect-signer key, the manifest by\n"
        "--expect-manifest-signer or else the same key.\n"  # __x_g4_wording_v1__
        "\n"
        "Usage: python3 -I verify_conformance_offline.py [--allow-unanchored]\n"
        "       --expect-signer BASE64 [--expect-manifest-signer "
        "BASE64]  # __x_g2_expect_signer_v1__\n"
        "Exit:  0 = PASS, 1 = INTEGRITY, 2 = ENVIRONMENT, 3 = OUTSIDE (NT-GATE-1\n"
        "       D4). The last line on stdout names the class.\n"  # __nt_v3_classes_wire_v1__
        '"""\n'
    )
    allowlist_block = (
        "\n\nKNOWN_REKOR_V2_LOG_KEYS = " + allowlist_literal + "\n"
    )
    anchor_shim = "\n".join(_ANCHOR_SHIM_LINES)
    dispatch_main = "\n".join(_CONFORMANCE_DISPATCH_MAIN_LINES)
    recompute = "\n\n" + _conformance_recompute_region() + "\n"  # __nt_v2_recompute_wire_v1__
    parts = [
        header,
        _HOISTED_IMPORTS,
        allowlist_block,
        "\n\n" + entry_body + "\n",
        "\n\n" + checkpoint_body + "\n",
        "\n\n" + tsa_body + "\n",
        "\n\n" + v2_body + "\n",
        anchor_shim,
        recompute,
        "\n\n" + _v3_classes_region() + "\n",  # __nt_v3_classes_wire_v1__
        dispatch_main,
    ]
    return "".join(parts)
