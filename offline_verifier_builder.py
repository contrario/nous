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
    "from cryptography.exceptions import InvalidSignature\n"
    "from cryptography import x509\n"
    "from cryptography.hazmat.primitives import hashes\n"
    "from cryptography.hazmat.primitives.asymmetric import "
    "ec, padding\n"
    "from cryptography.hazmat.primitives.asymmetric.ec import "
    "ECDSA\n"
    "from cryptography.hazmat.primitives.asymmetric.ed25519 import "
    "Ed25519PublicKey\n"
    "from cryptography.x509.oid import ExtendedKeyUsageOID\n"
    "from cryptography.hazmat.primitives.serialization import (\n"
    "    Encoding,\n"
    "    PublicFormat,\n"
    "    load_der_public_key,\n"
    ")\n"
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
    "    tlog = manifest.get('transparency_log')",
    "    if tlog is None:",
    "        if not args.allow_unanchored:",
    "            return _fail(",
    "                'transparency_log block missing; the dossier is '",
    "                'unanchored. Re-run with --allow-unanchored to "
    "accept '",
    "                'Ed25519-only verification.'",
    "            )",
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
    "    return 0",
    "",
    "",
    "if __name__ == '__main__':",
    "    sys.exit(main())",
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
        "Usage: python3 verify_offline.py [--allow-unanchored]\n"
        "Exit:  0 = PASS, 1 = FAIL, 2 = environment error.\n"
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
        dispatch_main,
    ]
    return "".join(parts)
