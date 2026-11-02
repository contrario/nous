"""CLI surface for runtime conformance verification.

`nous conformance verify <trace.json> --manifest <m.json> --prices <p.toml>
--source <s.nous>` re-derives the SMT spec from the SIGNED source + pricing
(Option B: bounds are never read from the unsigned proof_assumptions sibling),
parses the manifest and trace, runs verify_conformance, and prints the six
independent obligation booleans plus a derived verdict.

Exit codes:
  0 = PASS (all six obligations hold)
  1 = FAIL (a verdict: at least one obligation is False)
  2 = precondition error (structurally unusable inputs; refuse over guess)

# __nous_cli_conformance_module_v1__
"""
from __future__ import annotations

import argparse
import json

from conformance_verifier import (  # __an_js_strict_v1__
    StrictJsonError, loads as _strict_loads)
from pathlib import Path

from conformance import (
    ConformancePreconditionError,
    verify_conformance,
)
from manifest import parse_manifest_json
from pricing import load_pricing
from parser import parse_nous
from smt_emit import emit_smt
from nous_trace import TraceEnvelope  # __an_js_r2_v1__
from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # __s145_u4b_cli_attest_import_v1__
    Ed25519PublicKey,
)
from attest_apr import (
    AttestationPinningRecord,
    load_trust_root_public_key,
    verify_trace_attestation,
)
from conformance import (  # __nous_cli_conformance_certify_v1__
    ConformanceDetail,
    build_certificate,
    sign_certificate,
    certificate_json,
)
from manifest import load_or_create_keypair  # __nous_cli_conformance_certify_v1__
from _version import __version__ as _NOUS_VERSION  # __nous_cli_conformance_certify_v1__

import base64 as _xf5_b64  # __xf5_xd2_pins_v1__
from manifest import public_key_b64 as _xf5_pub_b64  # __xf5_xd2_pins_v1__
from manifest import verify_manifest_signature  # __xf5_xd2_pins_v1__
from conformance import _x_pinned_raw  # __xf5_xd2_pins_v1__


class _SignerRefusal(Exception):  # __xf5_xd2_pins_v1__
    """INTEGRITY: a manifest signature or a signer the run refuses (exit 1)."""


def _add_signer_args(p: argparse.ArgumentParser) -> None:  # __xf5_xd2_args_v1__
    p.add_argument(
        "--expect-signer", metavar="BASE64", default=None,
        help=(
            "Raw Ed25519 public key (base64, 32 bytes) the trace must be "
            "signed under; the manifest too, unless "
            "--expect-manifest-signer is given. Another signer is "
            "INTEGRITY, exit 1. A PASS then evidences signing by the "
            "holder of the key; who holds it is established out of band. "
            "Without it each signature is checked only under the key its "
            "file carries."
        ),
    )
    p.add_argument(
        "--expect-manifest-signer", metavar="BASE64", default=None,
        help=(
            "Raw Ed25519 public key (base64, 32 bytes) the manifest must "
            "be signed under, when it is not --expect-signer's key; needs "
            "--expect-signer"
        ),
    )


def _signer_pins(args):  # __xf5_xd2_pins_v1__
    t_b64 = getattr(args, "expect_signer", None)
    m_b64 = getattr(args, "expect_manifest_signer", None)
    if t_b64 is None and m_b64 is None:
        return None, None
    if t_b64 is None:
        raise ConformancePreconditionError(
            "--expect-manifest-signer needs --expect-signer")
    t_raw = _x_pinned_raw(t_b64)
    if t_raw is None:
        raise ConformancePreconditionError(
            "--expect-signer is not a base64 Ed25519 public key (32 bytes)")
    if m_b64 is None:
        return t_raw, t_raw
    m_raw = _x_pinned_raw(m_b64)
    if m_raw is None:
        raise ConformancePreconditionError(
            "--expect-manifest-signer is not a base64 Ed25519 public key "
            "(32 bytes)")
    return t_raw, m_raw


def _verdict_line(manifest):  # __xd5_verdict_line_v1__
    v = getattr(manifest, "verdict", None)
    if v == "proven":
        return None
    return ("  solver verdict       " + repr(v) + ", not 'proven': the "
            "cost bound is not established")


def _signers_line(args) -> str:  # __xf5_xd2_signers_v1__
    if getattr(args, "expect_signer", None) is not None:
        return ("  signers              pinned: the trace and the manifest "
                "are signed under the expected keys")
    return ("  signers              NOT PINNED: each signature checked only "
            "under the key its file carries")


def build_conformance_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "conformance",
        help=(
            "Runtime conformance: check a signed execution trace against the "
            "envelope the static cost proof assumed (interval checks, a "
            "Decimal sum and Ed25519; no Z3)"
        ),
    )
    cs = p.add_subparsers(dest="conformance_cmd")
    v = cs.add_parser(
        "verify",
        help=(
            "Verify a trace against a manifest + re-derived proof bounds"
        ),
    )
    v.add_argument(
        "trace",
        help="Path to the signed trace JSON (TraceEnvelope)",
    )
    v.add_argument(
        "--manifest", metavar="PATH", required=True,
        help="Path to the signed dossier manifest JSON",
    )
    v.add_argument(
        "--prices", metavar="PATH", required=True,
        help=(
            "Path to the pricing TOML pinned by the manifest "
            "(pricing_sha256 must match)"
        ),
    )
    v.add_argument(  # __s144_u4_cert_trust_fields_v1__
        "--require-attestation", action="store_true",
        help="FAIL unless provider_token_integrity == 'tee_attested' "
             "(verified inference receipt). Default: report the tier, "
             "do not gate on it.",
    )
    v.add_argument(  # __s145_u4b_apr_args_v1__
        "--apr", metavar="PATH", action="append", default=None,
        help="Path to a signed Attestation Pinning Record JSON (repeatable). "
             "Required to verify a tee_attested claim.",
    )
    v.add_argument(
        "--attest-root", metavar="PATH", default=None,
        help="Path to the pinned attestation trust-root public key (PEM).",
    )
    v.add_argument(
        "--source", metavar="PATH", required=True,
        help=(
            "Path to the source .nous the manifest was produced from "
            "(bounds are re-derived from it, not read from the manifest)"
        ),
    )
    _add_signer_args(v)  # __xf5_xd2_args_v1__

    c = cs.add_parser(  # __nous_cli_conformance_certify_v1__
        "certify",
        help=(
            "Verify a trace, then emit a standalone signed conformance.json "
            "certificate (PASS or FAIL verdict are both signed results)"
        ),
    )
    c.add_argument("trace", help="Path to the signed trace JSON (TraceEnvelope)")
    c.add_argument(
        "--manifest", metavar="PATH", required=True,
        help="Path to the signed dossier manifest JSON",
    )
    c.add_argument(
        "--prices", metavar="PATH", required=True,
        help="Path to the pricing TOML pinned by the manifest",
    )
    c.add_argument(
        "--source", metavar="PATH", required=True,
        help="Path to the source .nous the manifest was produced from",
    )
    c.add_argument(
        "--out", metavar="PATH", required=True,
        help="Path to write the signed conformance.json certificate",
    )
    c.add_argument(
        "--key-path", metavar="PATH", default=None,
        help=(
            "ed25519 signing key path "
            "(default: ~/.local/share/nous/keys/signing.key)"
        ),
    )
    c.add_argument(
        "--issued-utc", metavar="ISO8601", default=None,
        help=(
            "issuance timestamp (default: current UTC at run time); explicit "
            "value makes the certificate byte-deterministic"
        ),
    )
    c.add_argument(
        "--anchor", metavar="MODE", default=None, choices=["rekor_v2"],
        help="anchor the certificate in a transparency log (S97 step 5)",
    )
    c.add_argument(
        "--emit-obligations-canon", action="store_true",  # __s187b_1a_cli_flag_v1__
        help=(
            "embed the governing spec canonical preimage (obligations_canon) "
            "as a root-committed cert field for governance-change "
            "attestation; always embedded when the manifest declares a cost "
            "proof (cost_farkas_sha256), so the offline verifier can "
            "re-derive the cost system; this flag forces it otherwise. "
            "DISCLOSURE: the canon is part of the signed certificate and "
            "carries, per soul, the model rates and the token estimates "
            "(input and output tokens, reasoning multiplier), the "
            "currency, the NOUS version (NV), and the governance lines: "
            "gated actions (GA), quorums (GQ), sequence laws (SA/SD) and "
            "declared events (DE)"  # __nt_v1d_disclosure_help_v1__
        ),
    )
    _add_signer_args(c)  # __xf5_xd2_args_v1__


def _load_aprs(  # __s145_u4b_loader_v1__
    paths: list[str] | None,
) -> list[AttestationPinningRecord] | None:
    if not paths:
        return None
    records: list[AttestationPinningRecord] = []
    for raw in paths:
        pth = Path(raw)
        if not pth.is_file():
            raise ConformancePreconditionError(f"APR file not found: {pth}")
        raw = pth.read_bytes()
        _strict_loads(raw, pth.name + " [js:cconf.1]")  # __an_js_r2_v1__
        try:
            records.append(
                AttestationPinningRecord.model_validate_json(raw)
            )
        except Exception as exc:
            raise ConformancePreconditionError(
                f"APR file {pth} failed to parse: {exc}"
            ) from exc
    return records


def _load_attest_root(path: str | None) -> Ed25519PublicKey | None:
    if not path:
        return None
    pth = Path(path)
    if not pth.is_file():
        raise ConformancePreconditionError(
            f"attestation trust-root public key not found: {pth}"
        )
    return load_trust_root_public_key(pth)


def _derive_inputs(args: argparse.Namespace):  # __nous_cli_conformance_certify_v1__
    _pins = _signer_pins(args)  # __xf5_xd2_pins_v1__
    trace_path = Path(args.trace)
    manifest_path = Path(args.manifest)
    prices_path = Path(args.prices)
    source_path = Path(args.source)
    for label, pth in (
        ("trace", trace_path),
        ("manifest", manifest_path),
        ("prices", prices_path),
        ("source", source_path),
    ):
        if not pth.is_file():
            raise ConformancePreconditionError(f"{label} file not found: {pth}")

    manifest_raw = manifest_path.read_bytes()  # __an_js_r2_v1__
    _strict_loads(manifest_raw, "manifest.json [js:cconf.2]")
    manifest_text = manifest_raw.decode("utf-8")
    manifest, _sig, _pub = parse_manifest_json(manifest_text)
    if not verify_manifest_signature(manifest, _sig, _pub):  # __xf5_xd2_pins_v1__
        raise _SignerRefusal(
            "manifest.json: Ed25519 signature does not verify under the "
            "key it carries")
    if (_pins[1] is not None
            and _xf5_b64.b64decode(_xf5_pub_b64(_pub)) != _pins[1]):
        raise _SignerRefusal(
            "manifest.json: signer is not the expected key "
            "(--expect-manifest-signer, else --expect-signer)")
    source_text = source_path.read_text(encoding="utf-8")
    program = parse_nous(source_text)
    pricing = load_pricing(prices_path)
    margin = manifest.safety_margin_pct or 0
    spec = emit_smt(
        program, pricing, source_text=source_text, margin_pct=margin
    )
    trace = TraceEnvelope(**_strict_loads(  # __an_js_r2_v1__
        trace_path.read_bytes(), "trace.json [js:cconf.3]"))
    if _pins[0] is not None:  # __xf5_xd2_pins_v1__
        _tsig = getattr(trace, "signature", None)
        _tk = getattr(_tsig, "public_key_b64", None)
        if _tk is None or _x_pinned_raw(_tk) != _pins[0]:
            raise _SignerRefusal(
                "trace.json: signer is not the expected key "
                "(--expect-signer)")
    _aprs = _load_aprs(getattr(args, "apr", None))  # __s145_u4b_derive_wire_v1__
    _attest_root = _load_attest_root(getattr(args, "attest_root", None))
    from run_shas import compute_codegen_sha256  # __s155_u5_cli_codegen_wire_v1__
    _codegen = compute_codegen_sha256(source_text)
    detail = verify_conformance(
        trace, manifest, spec, pricing,
        aprs=_aprs, attest_trust_root_public_key=_attest_root,
        codegen_sha256=_codegen,
    )
    return manifest, spec, pricing, trace, detail


def _print_detail(detail: "ConformanceDetail") -> None:  # __nous_cli_conformance_certify_v1__
    def _mark(b: bool) -> str:
        return "PASS" if b else "FAIL"

    print("NOUS runtime conformance")
    print("-" * 56)
    print(f"  binding              {_mark(detail.binding_ok)}")
    print(f"  surface              {_mark(detail.surface_ok)}")
    print(f"  assumption_discharge {_mark(detail.assumption_discharge_ok)}")
    print(f"  bound_transfer       {_mark(detail.bound_transfer_ok)}")
    print(f"  authorization        {_mark(detail.authorization_ok)}")
    print(f"  trace_signature      {_mark(detail.trace_signature_ok)}")
    print("-" * 56)
    print(f"  realized_total       {detail.realized_total}")
    print(f"  cost_cap             {detail.cost_cap}")
    if detail.errors:
        print("  failures:")
        for e in detail.errors:
            print(f"    - {e}")
    print("-" * 56)


def _cmd_certify(args: argparse.Namespace) -> int:  # __nous_cli_conformance_certify_v1__
    try:
        manifest, _spec, _pricing, trace, detail = _derive_inputs(args)
    except _SignerRefusal as e:  # __xf5_xd2_pins_v1__
        import sys
        print("FAIL: " + str(e), file=sys.stderr)
        return 1
    except StrictJsonError as e:  # __an_js_strict_v1__
        import sys
        print("FAIL: " + str(e), file=sys.stderr)
        return 1
    except ConformancePreconditionError as e:
        print(f"PRECONDITION ERROR: {e}")
        return 2
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"PRECONDITION ERROR: {type(e).__name__}: {e}")
        return 2

    if args.issued_utc is not None:
        issued = args.issued_utc
    else:
        from datetime import datetime, timezone
        issued = (
            datetime.now(timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        )

    priv, _pub, _key_path = load_or_create_keypair(
        Path(args.key_path) if args.key_path else None
    )
    from conformance import obligations_canon_for  # __nt_v1b_certify_canon_rule_v1__
    _ob_canon = obligations_canon_for(  # __s187b_1a_cli_pass_canon_v1__
        manifest, _spec,
        emit=bool(getattr(args, "emit_obligations_canon", False)),
    )
    cert = build_certificate(
        detail, trace, manifest,
        nous_version=_NOUS_VERSION, issued_utc=issued,
        obligations_canon=_ob_canon,
    )
    signed = sign_certificate(cert, priv)

    if args.anchor == "rekor_v2":  # __nous_conformance_anchored_verifier_v1__
        from rekor_anchor_v2 import anchor_manifest_to_rekor_v2
        from conformance import ConformanceCertificate
        try:
            anchor = anchor_manifest_to_rekor_v2(
                signed.certificate_canonical_body_bytes()
            )
        except Exception as e:
            print(f"PRECONDITION ERROR: anchoring failed: "
                  f"{type(e).__name__}: {e}")
            return 2
        signed = ConformanceCertificate(
            **{**signed.model_dump(),
               "transparency_log": anchor.to_manifest_block()}
        )

    out_path = Path(args.out)
    out_path.write_text(certificate_json(signed), encoding="utf-8")

    _print_detail(detail)
    print(_signers_line(args))  # __xf5_xd2_signers_v1__
    _vl = _verdict_line(manifest)  # __xd5_verdict_line_v1__
    if _vl is not None:
        print(_vl)
    print(f"certificate          {out_path}")
    if signed.transparency_log is not None:
        print(f"anchored             rekor_v2 "
              f"log_index={signed.transparency_log.get('log_index')}")
    print(f"VERDICT: {'PASS' if detail.ok else 'FAIL'} "
          f"(signed; trace_sha256={signed.trace_sha256[:16]}...)")
    return 0


def cmd_conformance(args: argparse.Namespace) -> int:
    sub = getattr(args, "conformance_cmd", None)
    if sub == "certify":  # __nous_cli_conformance_certify_v1__
        return _cmd_certify(args)
    if sub != "verify":
        print(
            "usage: nous conformance {verify|certify} <trace.json> "
            "--manifest <m> --prices <p> --source <s>"
        )
        return 2

    try:
        manifest, _spec, _pricing, trace, detail = _derive_inputs(args)
    except _SignerRefusal as e:  # __xf5_xd2_pins_v1__
        import sys
        print("FAIL: " + str(e), file=sys.stderr)
        return 1
    except StrictJsonError as e:  # __an_js_strict_v1__
        import sys
        print("FAIL: " + str(e), file=sys.stderr)
        return 1
    except ConformancePreconditionError as e:
        print(f"PRECONDITION ERROR: {e}")
        return 2
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"PRECONDITION ERROR: {type(e).__name__}: {e}")
        return 2

    def _mark(b: bool) -> str:
        return "PASS" if b else "FAIL"

    print("NOUS runtime conformance")
    print("-" * 56)
    print(f"  binding              {_mark(detail.binding_ok)}")
    print(f"  surface              {_mark(detail.surface_ok)}")
    print(f"  assumption_discharge {_mark(detail.assumption_discharge_ok)}")
    print(f"  bound_transfer       {_mark(detail.bound_transfer_ok)}")
    print(f"  authorization        {_mark(detail.authorization_ok)}")
    print(f"  trace_signature      {_mark(detail.trace_signature_ok)}")
    print("-" * 56)
    print(f"  realized_total       {detail.realized_total}")
    print(f"  cost_cap             {detail.cost_cap}")
    if detail.errors:
        print("  failures:")
        for e in detail.errors:
            print(f"    - {e}")
    _attest_ok = True  # __s145_u4b_strict_gate_v1__
    if getattr(args, "require_attestation", False):
        _attest_ok = detail.provider_token_integrity == "tee_attested"
        if _attest_ok:
            _strict_aprs = _load_aprs(getattr(args, "apr", None))
            _strict_root = _load_attest_root(getattr(args, "attest_root", None))
            if _strict_aprs is None or _strict_root is None:
                _attest_ok = False
            else:
                _attest_ok = verify_trace_attestation(
                    trace, _strict_aprs, _strict_root, strict_no_test=True
                ).attested
        if not _attest_ok:
            print(
                "  attestation         FAIL (require-attestation: tier="
                + repr(detail.provider_token_integrity) + ")"
            )
    print(f"  provider_token_integrity {detail.provider_token_integrity!r}")
    print(_signers_line(args))  # __xf5_xd2_signers_v1__
    _vl = _verdict_line(manifest)  # __xd5_verdict_line_v1__
    if _vl is not None:
        print(_vl)
    print("-" * 56)
    _verdict_ok = detail.ok and _attest_ok
    print(f"VERDICT: {'PASS' if _verdict_ok else 'FAIL'}")
    return 0 if _verdict_ok else 1
