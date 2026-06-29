"""
NOUS CLI — `verify` subcommand.

Wires the full chain: parse -> AST -> pricing -> emit -> z3 -> manifest.
The flagship user-facing command of the cost_cap arc.

Usage:
  nous verify file.nous --smt
  nous verify file.nous --smt --prices /path/to/x.toml
  nous verify file.nous --smt --no-manifest
  nous verify file.nous --smt --manifest-out audit.json
  nous verify file.nous --smt --timeout-ms 60000
  nous verify file.nous --smt --smt-margin 20

Exit codes:
  0  proven
  1  refuted (counterexample shown)
  2  unknown / solver timeout
  3  error (missing decls, bad pricing, etc.)

# __nous_cli_verify_v1__
"""
from __future__ import annotations
# __session64_publish_removal_v1__
# __session64_smt_margin_v1__

import argparse
import sys
from pathlib import Path
from typing import Optional

from manifest import (
    load_or_create_keypair,
    manifest_from_verify,
    manifest_json,
    parse_manifest_json,  # __s119_supersedes_producer_v1__
    sign_manifest,
    verify_manifest_signature,  # __s119_supersedes_producer_v1__
)
from parser import parse_nous
from pricing import load_pricing
from smt_emit import EmitError, emit_smt
from smt_verify import format_verdict, verify
from smt_emit import with_coverage  # __s115_coverage_threshold_v1__
from smt_verify import verify_coverage  # __s115_coverage_threshold_v1__
from policy_coverage import (  # __s115_coverage_threshold_v1__
    CoverageEmitError,
    build_threshold_claim,
)
import dataclasses as _dc_s115  # __s115_coverage_threshold_v1__
import hashlib as _hashlib_s115  # __s115_coverage_smt2_sha_v1__
import json as _json_s116  # __s116_cli_farkas_v1__
from cost_farkas import (  # __s170_leg1_cost_emit_v1__
    CostFarkasError,
    cost_certificate_from_smtspec,
    cost_farkas_json_bytes,
    cost_farkas_sha256,
)
from coverage_farkas import (  # __s116_cli_farkas_v1__
    serialize_auto as _farkas_serialize,  # __s124_cli_serialize_auto_v1__
    FarkasError as _FarkasError,
)


def _import_nous_version() -> str:
    try:
        from _version import __version__
        return str(__version__)
    except Exception:
        return "4.13.0-dev"


def cmd_verify(args: argparse.Namespace) -> int:
    if not args.smt:
        print("ERROR: --smt is required for verify (other modes are "
              "deferred to future phases)", file=sys.stderr)
        return 3

    if (
        getattr(args, "materiality_against", None) is not None
        and getattr(args, "gap_witness", False)
    ):  # __s171_materiality_gapw_refuse_v1__
        print(
            "REFUSED: --materiality-against is incoherent with "
            "--gap-witness (a refutation artifact carries no minor/"
            "material change classification). No manifest written.",
            file=sys.stderr,
        )
        return 1
    if (
        getattr(args, "pce", None) is not None
        and getattr(args, "gap_witness", False)
    ):  # __s190_pce_gapw_refuse_v1__
        print(
            "REFUSED: --pce is incoherent with --gap-witness (a "
            "refutation artifact carries no predetermined-change-envelope "
            "membership). No manifest written.",
            file=sys.stderr,
        )
        return 1
    src_path = Path(args.file)
    if not src_path.is_file():
        print(f"ERROR: file not found: {src_path}", file=sys.stderr)
        return 3

    # 1. Parse
    try:
        source_text: str = src_path.read_text(encoding="utf-8")
        program = parse_nous(source_text)
    except Exception as e:
        print(f"ERROR: parse failed for {src_path.name}: {e}",
              file=sys.stderr)
        return 3
    print(f"Parsed {src_path.name}: world="
          f"{program.world.name if program.world else 'NONE'}, "
          f"souls={len(program.souls)}")

    # 2. Pricing
    custom_prices: Optional[Path] = (
        Path(args.prices) if args.prices else None
    )
    try:
        pricing = load_pricing(custom_prices)
    except Exception as e:
        print(f"ERROR: pricing load failed: {e}", file=sys.stderr)
        return 3
    print(f"Loaded pricing: layer {pricing.layer_index}, "
          f"{len(pricing.model_names())} models, "
          f"sha256 {pricing.sha256()[:16]}…")

    # 3. Emit
    try:
        margin_pct: int = getattr(args, "smt_margin", 0)
        spec = emit_smt(
            program, pricing,
            source_text=source_text,
            margin_pct=margin_pct,
        )
    except EmitError as e:
        print(f"ERROR: cannot emit SMT for {src_path.name}:",
              file=sys.stderr)
        print(f"  {e}", file=sys.stderr)
        return 3
    print(f"Emitted SMT-LIB: spec sha256 {spec.sha256()[:16]}…")

    # 4. Verify
    print(f"Running solver (timeout {args.timeout_ms}ms)...")
    result = verify(spec, timeout_ms=args.timeout_ms)
    print()
    print(format_verdict(result))

    if result.verdict == "error":
        return 3

    # 4b. Coverage obligation (S115 P3a). __s115_coverage_threshold_v1__
    coverage_sha: Optional[str] = None
    coverage_script: Optional[str] = None
    coverage_farkas_script: Optional[str] = None  # __s116_cli_farkas_v1__
    coverage_farkas_sha: Optional[str] = None  # __s116_cli_farkas_v1__
    cov_threshold = getattr(args, "coverage_threshold", None)
    if getattr(args, "gap_witness", False) and not cov_threshold:  # __s134_gapw_issue_v1__
        print(
            "REFUSED: --gap-witness requires --coverage-threshold "
            "(a refutation needs a threshold to witness a gap "
            "against). No manifest written.",
            file=sys.stderr,
        )
        return 1
    if cov_threshold:
        try:
            cov_src = (
                "world _ThresholdProbe {\n"
                "    policy _P { kind: \"x\" signal: "
                + cov_threshold + " action: log_only }\n}\n"
            )
            cov_prog = parse_nous(cov_src)
            th_ast = cov_prog.world.policies[0].signal
            claim = build_threshold_claim(th_ast, cov_threshold)
            policies = list(
                getattr(program.world, "policies", None) or []
            )
            cov_spec = with_coverage(spec, policies, claim)
        except (CoverageEmitError, Exception) as e:
            print(
                f"ERROR: coverage threshold build failed: {e}",
                file=sys.stderr,
            )
            return 3
        cov_result = verify_coverage(
            cov_spec, timeout_ms=args.timeout_ms
        )
        if cov_result.verdict != "proven":
            if getattr(args, "gap_witness", False):  # __s134_gapw_issue_v1__
                return _issue_gap_witness_dossier(
                    args, result, th_ast, policies, cov_threshold,
                    src_path,
                )
            print(
                f"\nREFUSED: coverage not proven "
                f"(verdict={cov_result.verdict}); no manifest written. "
                f"NOUS does not sign a system with an unproven "
                f"coverage obligation.",
                file=sys.stderr,
            )
            return 1
        coverage_sha = cov_spec.coverage_sha256()
        coverage_script = cov_spec.serialize_coverage()
        coverage_smt2_sha = _hashlib_s115.sha256(  # __s115_coverage_smt2_sha_v1__
            coverage_script.encode("utf-8")
        ).hexdigest()
        print(
            f"Coverage PROVEN: no gap over threshold "
            f"'{cov_threshold}' (sha256 {coverage_sha[:16]}...)"
        )
        # S116 P3b: Farkas certificate (stdlib-checkable, drop-when-None).  __s116_cli_farkas_v1__
        try:
            _farkas_blocking = [
                p.signal for p in policies
                if getattr(p, "action", None) in ("block", "abort_cycle")
            ]
            _farkas_doc = _farkas_serialize(
                th_ast, _farkas_blocking, threshold_expr=cov_threshold
            )
            coverage_farkas_script = _json_s116.dumps(
                _farkas_doc, sort_keys=True, indent=2
            ) + "\n"
            coverage_farkas_sha = _hashlib_s115.sha256(
                coverage_farkas_script.encode("utf-8")
            ).hexdigest()
            if _farkas_doc.get("fragment") == "disjunctive-linear-bundle":  # __s124_cli_cross_derivation_v1__
                from coverage_minilang import (
                    MinilangError as _MlError_s124,
                    bundle_cert_keys as _ml_keys_s124,
                    derive_disjunct_constraints as _ml_derive_s124,
                )
                try:
                    _ml_derived_s124 = _ml_derive_s124(
                        src_path.read_text(encoding="utf-8"),
                        cov_threshold,
                    )
                except (_MlError_s124, _FarkasError) as _me:
                    raise _FarkasError(
                        "cross-derivation gate: minilang re-derivation "
                        "refused (" + str(_me) + "); bundle not signed"
                    )
                if set(_ml_derived_s124) != _ml_keys_s124(_farkas_doc):
                    raise _FarkasError(
                        "cross-derivation gate: minilang-derived disjunct "
                        "set differs from the produced bundle; bundle not "
                        "signed (parser divergence)"
                    )
            if "contradiction" in _farkas_doc:  # __s124_cli_serialize_auto_v1__
                print(
                    f"Farkas certificate extracted: contradiction "
                    f"{_farkas_doc['contradiction']!r} "
                    f"(sha256 {coverage_farkas_sha[:16]}...)"
                )
            else:
                print(
                    f"Farkas bundle extracted: "
                    f"{_farkas_doc.get('disjunct_count', '?')} "
                    f"disjunct cert(s) "
                    f"(sha256 {coverage_farkas_sha[:16]}...)"
                )
        except _FarkasError as _fe:
            coverage_farkas_script = None
            coverage_farkas_sha = None
            print(
                f"NOTE: Farkas certificate not extracted "
                f"(z3 coverage proof stands): {_fe}",
                file=sys.stderr,
            )

    # 5. Manifest (always built; written if --manifest-out, optionally published)
    nous_version = _import_nous_version()
    from run_shas import compute_codegen_sha256  # __s156_u1_cli_codegen_import_v1__
    _codegen_sha = compute_codegen_sha256(source_text)
    manifest = manifest_from_verify(
        result, nous_version=nous_version, codegen_sha256=_codegen_sha,
    )
    if coverage_sha is not None:  # __s115_coverage_threshold_v1__
        manifest = _dc_s115.replace(
            manifest,
            policy_coverage_sha256=coverage_sha,
            coverage_smt2_sha256=coverage_smt2_sha,  # __s115_coverage_smt2_sha_v1__
            coverage_farkas_sha256=coverage_farkas_sha,  # __s116_cli_farkas_v1__
        )

    _cost_doc_s170: Optional[dict] = None  # __s170_leg1_cost_emit_v1__
    _cost_sha_s170: Optional[str] = None  # __s170_leg1_cost_emit_v1__
    _cost_bytes_s170: Optional[bytes] = None  # __s170_leg1_cost_emit_v1__
    try:  # __s170_leg1_cost_emit_v1__
        _cost_doc_s170 = cost_certificate_from_smtspec(spec)
    except CostFarkasError as _ce_s170:  # __s170_leg1_cost_emit_v1__
        print(
            f"NOTE: cost-cap Farkas certificate not extracted "
            f"(z3 cost proof stands): {_ce_s170}",
            file=sys.stderr,
        )
    if _cost_doc_s170 is not None:  # __s170_leg1_cost_emit_v1__
        _cost_bytes_s170 = cost_farkas_json_bytes(_cost_doc_s170)
        _cost_sha_s170 = cost_farkas_sha256(_cost_doc_s170)
        manifest = _dc_s115.replace(
            manifest, cost_farkas_sha256=_cost_sha_s170
        )
        print(
            f"Cost-cap Farkas certificate extracted "
            f"(sha256 {_cost_sha_s170[:16]}...)"
        )

    materiality_against = getattr(args, "materiality_against", None)  # __s171_materiality_emit_v1__
    _mat_bytes = None  # __s171_materiality_emit_v1__
    if materiality_against is not None:
        if getattr(args, "gap_witness", False):
            print(
                "REFUSED: --materiality-against is incoherent with "
                "--gap-witness (a refutation artifact carries no minor/"
                "material change classification). No manifest written.",
                file=sys.stderr,
            )
            return 1
        from parser import parse_nous as _parse_nous_mat
        from behavioral_diff import (
            behavioral_diff as _bdiff_mat,
            classify_materiality as _classify_mat,
        )
        _prior_src_mat = Path(materiality_against).read_text(
            encoding="utf-8"
        )
        _mat_threshold = float(
            getattr(args, "materiality_threshold_pct", 10.0)
        )
        _mat_verdict = _classify_mat(
            _bdiff_mat(
                _parse_nous_mat(_prior_src_mat),
                _parse_nous_mat(source_text),
            ),
            _mat_threshold,
        )
        _mat_bytes = _json_s116.dumps(
            _mat_verdict, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        _mat_sha = _hashlib_s115.sha256(_mat_bytes).hexdigest()
        manifest = _dc_s115.replace(
            manifest, materiality_sha256=_mat_sha
        )
        print(
            "Materiality classified vs " + str(materiality_against)
            + ": " + _mat_verdict["verdict"]
            + " (sha256 " + _mat_sha[:16] + "...)"
        )
    pce_against = getattr(args, "pce", None)  # __s190_pce_producer_v1__
    pce_baseline = getattr(args, "pce_baseline", None)  # __s190_pce_producer_v1__
    _pce_bytes = None  # __s190_pce_producer_v1__
    _pce_baseline_bytes = None  # __s190_pce_producer_v1__
    if pce_against is not None:
        if pce_baseline is None:
            print(
                "REFUSED: --pce requires --pce-baseline (the committed baseline "
                "obligations canon the envelope binds to). No manifest written.",
                file=sys.stderr,
            )
            return 1
        if not Path(pce_against).is_file():
            print(
                "REFUSED: --pce file not found: " + str(pce_against)
                + ". No manifest written.",
                file=sys.stderr,
            )
            return 1
        if not Path(pce_baseline).is_file():
            print(
                "REFUSED: --pce-baseline file not found: " + str(pce_baseline)
                + ". No manifest written.",
                file=sys.stderr,
            )
            return 1
        import envelope as _envelope_s190
        _pce_bytes = Path(pce_against).read_bytes()
        try:
            _pce_doc_s190 = _json_s116.loads(_pce_bytes.decode("utf-8"))
        except Exception as _pce_e_s190:
            print(
                "REFUSED: --pce file is not valid JSON: " + str(_pce_e_s190)
                + ". No manifest written.",
                file=sys.stderr,
            )
            return 1
        try:
            _envelope_s190.parse_envelope(_pce_doc_s190)
        except _envelope_s190.EnvelopeError as _pce_ee_s190:
            print(
                "REFUSED: --pce envelope is not well-formed: "
                + str(_pce_ee_s190) + ". No manifest written.",
                file=sys.stderr,
            )
            return 1
        _pce_baseline_bytes = Path(pce_baseline).read_bytes()
        _pce_baseline_sha = _hashlib_s115.sha256(_pce_baseline_bytes).hexdigest()
        _pce_committed_base = _pce_doc_s190["baseline_canon_sha256"]
        if _pce_baseline_sha != _pce_committed_base:
            print(
                "REFUSED: --pce-baseline sha256 " + _pce_baseline_sha[:16]
                + "... does not match the envelope committed "
                "baseline_canon_sha256 " + _pce_committed_base[:16]
                + "... No manifest written.",
                file=sys.stderr,
            )
            return 1
        _pce_sha_s190 = _hashlib_s115.sha256(_pce_bytes).hexdigest()
        manifest = _dc_s115.replace(manifest, pce_sha256=_pce_sha_s190)
        print(
            "Predetermined-change envelope bound (--pce " + str(pce_against)
            + "): pce_sha256 " + _pce_sha_s190[:16] + "..."
            + (" (cumulative)" if _pce_doc_s190.get("cumulative") is not None
               else " (per-step only)")
        )
    chain_coverage_mode = getattr(args, "chain_coverage", None)  # __s127_chain_coverage_flag_v1__
    supersedes_path = getattr(args, "supersedes", None)  # __s119_supersedes_producer_v1__
    if chain_coverage_mode == "full" and not supersedes_path:  # __s127_chain_coverage_flag_v1__
        print(
            "REFUSED: --chain-coverage full requires --supersedes "
            "(full mode carries per-link sources and net-containment "
            "proofs across hops; there is no chain without a "
            "predecessor). No manifest written.",
            file=sys.stderr,
        )
        return 1
    if supersedes_path:
        try:
            _prior_digest = resolve_prior_digest(
                manifest, supersedes_path
            )
        except SupersedesError as e:
            print(
                "REFUSED: " + str(e) + ". No manifest written.",
                file=sys.stderr,
            )
            return 1
        manifest = _dc_s115.replace(
            manifest,
            prior_digest=_prior_digest,
            chain_coverage_mode=(  # __s127_chain_coverage_flag_v1__
                "blocking-net-full"
                if chain_coverage_mode == "full"
                else None
            ),
        )
        print(
            "Re-binding: supersedes " + str(supersedes_path)
            + " (prior_digest " + _prior_digest[:16] + "...)"
        )

    if args.no_manifest:
        return _exit_for_verdict(result.verdict)

    try:
        priv, pub, key_path = load_or_create_keypair(
            Path(args.key_path) if args.key_path else None
        )
    except Exception as e:
        print(f"\nWARN: keypair unavailable; manifest unsigned. "
              f"Reason: {e}", file=sys.stderr)
        return _exit_for_verdict(result.verdict)

    try:
        sig = sign_manifest(manifest, priv)
        doc = manifest_json(manifest, sig, pub)
    except Exception as e:
        print(f"\nWARN: signing failed: {e}", file=sys.stderr)
        return _exit_for_verdict(result.verdict)

    out_path: Path = (
        Path(args.manifest_out) if args.manifest_out
        else src_path.with_suffix(".manifest.json")
    )
    try:
        out_path.write_text(doc, encoding="utf-8")
        if coverage_script is not None:  # __s115_coverage_threshold_v1__
            cov_path = out_path.parent / "coverage.smt2"
            cov_path.write_text(coverage_script, encoding="utf-8")
            print(f"Coverage SMT written: {cov_path}")
            if coverage_farkas_script is not None:  # __s116_cli_farkas_v1__
                farkas_path = (
                    out_path.parent / "coverage.farkas.json"
                )
                farkas_path.write_text(
                    coverage_farkas_script, encoding="utf-8"
                )
                print(
                    f"Coverage Farkas written: {farkas_path}"
                )
        if _cost_bytes_s170 is not None:  # __s170_leg1_cost_emit_v1__
            cost_path = out_path.parent / "cost.farkas.json"  # __s170_leg1_cost_emit_v1__
            cost_path.write_bytes(_cost_bytes_s170)  # __s170_leg1_cost_emit_v1__
            print(f"Cost-cap Farkas written: {cost_path}")  # __s170_leg1_cost_emit_v1__
        if _mat_bytes is not None:  # __s171_materiality_emit_v1__
            mat_path = out_path.parent / "materiality.json"
            mat_path.write_bytes(_mat_bytes)
            print(f"Materiality written: {mat_path}")
        if _pce_bytes is not None:  # __s190_pce_producer_v1__
            pce_out_path = out_path.parent / "pce.json"
            pce_out_path.write_bytes(_pce_bytes)
            baseline_out_path = out_path.parent / "baseline.canon"
            baseline_out_path.write_bytes(_pce_baseline_bytes)
            print(f"Predetermined-change envelope written: {pce_out_path}")
            print(f"Committed baseline canon written: {baseline_out_path}")
        print()
        print(f"Manifest signed: {out_path}")
        print(f"  key:    {key_path}")
        print(f"  sha256 spec: {spec.sha256()}")
    except Exception as e:
        print(f"\nWARN: could not write manifest to {out_path}: {e}",
              file=sys.stderr)
        return _exit_for_verdict(result.verdict)

    return _exit_for_verdict(result.verdict)


def _exit_for_verdict(v: str) -> int:
    return {
        "proven": 0,
        "refuted": 1,
        "unknown": 2,
        "error": 3,
    }.get(v, 3)


_SHA_BEARING_FIELDS = (  # __s119_supersedes_producer_v1__
    "source_sha256",
    "pricing_sha256",
    "smt_spec_sha256",
    "cost_cap_usd",
    "max_ticks",
)


class SupersedesError(Exception):  # __s119_supersedes_producer_v1__
    """Re-binding admission control failed; message starts with the cause."""


def resolve_prior_digest(  # __s119_supersedes_producer_v1__
    manifest: "object", supersedes_path: str
) -> str:
    """Verify the immediate predecessor and return its canonical-body sha256.

    Fail-closed: raises SupersedesError on a missing file, a parse failure,
    an invalid predecessor Ed25519 signature, or a no-op re-binding (no
    sha-bearing field moved vs the predecessor). Signature-check is of the
    IMMEDIATE predecessor only; this performs NO chain-walk. This is issuance
    admission control, NOT the trust boundary -- the offline verifier
    enforces the same rule with zero issuer trust.
    """
    prior_path = Path(supersedes_path)
    if not prior_path.is_file():
        raise SupersedesError(
            "predecessor manifest not found: " + str(prior_path)
        )
    try:
        prior_text = prior_path.read_text(encoding="utf-8")
        prior_manifest, prior_sig, prior_pub = parse_manifest_json(
            prior_text
        )
    except SupersedesError:
        raise
    except Exception as e:
        raise SupersedesError(
            "cannot parse predecessor manifest "
            + str(prior_path) + ": " + str(e)
        )
    if not verify_manifest_signature(
        prior_manifest, prior_sig, prior_pub
    ):
        raise SupersedesError(
            "predecessor manifest " + str(prior_path)
            + " Ed25519 signature does NOT verify; refusing to chain onto "
            "a non-authentic predecessor"
        )
    moved = [
        f for f in _SHA_BEARING_FIELDS
        if getattr(manifest, f) != getattr(prior_manifest, f)
    ]
    if not moved:
        raise SupersedesError(
            "no-op re-binding: --supersedes given but no sha-bearing "
            "field moved vs " + str(prior_path) + ". A material change "
            "must alter at least one of "
            + ", ".join(_SHA_BEARING_FIELDS)
        )
    return _hashlib_s115.sha256(
        prior_manifest.canonical_bytes()
    ).hexdigest()


def build_verify_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "verify",
        help="Verify a .nous program with the SMT solver.",
        description=(
            "Runs the full cost_cap proof chain: parse -> emit -> "
            "z3 -> signed manifest. Phase 4 of NOUS Session 62."
        ),
    )
    p.add_argument("file", help="Path to .nous source file.")
    p.add_argument(
        "--smt", action="store_true", required=True,
        help="Enable SMT verification (currently the only mode).",
    )
    p.add_argument(
        "--prices", metavar="PATH",
        help="Override pricing TOML path.",
    )
    p.add_argument(
        "--timeout-ms", type=int, default=30000,
        help="Z3 solver timeout in milliseconds (default: 30000).",
    )
    p.add_argument(
        "--no-manifest", action="store_true",
        help="Skip signed manifest generation.",
    )
    p.add_argument(
        "--manifest-out", metavar="PATH",
        help="Write manifest to this path "
             "(default: <source>.manifest.json).",
    )
    p.add_argument(
        "--key-path", metavar="PATH",
        help="ed25519 signing key path "
             "(default: ~/.local/share/nous/keys/signing.key).",
    )
    p.add_argument(  # __s115_coverage_threshold_v1__
        "--coverage-threshold", metavar="EXPR", default=None,
        help="Also prove policy coverage over this NOUS threshold "
             "expression (e.g. \"amount > 10000\") and bind its "
             "sha256 into the signed manifest. REFUTED coverage "
             "fails closed: no manifest is written.",
    )
    p.add_argument(  # __s134_gapw_issue_v1__
        "--gap-witness", action="store_true", default=False,
        help="When --coverage-threshold is NOT proven, issue a "
             "coverage-gap-witness (refutation) dossier instead of "
             "refusing: find a rational point in the threshold "
             "region that escapes every blocking signal and bind it "
             "as source_kind=gap-witness. Requires "
             "--coverage-threshold.",
    )
    p.set_defaults(func=cmd_verify)


def cmd_verify_impl_guard_for_test(  # __s127_chain_coverage_flag_v1__
    chain_coverage: "str | None",
    supersedes: "str | None",
) -> int:
    """Test-only shim exposing the full-requires-supersedes admission
    rule in isolation (the same condition enforced inline in the verify
    pipeline). Returns 1 if the combination is refused, 0 otherwise."""
    if chain_coverage == "full" and not supersedes:
        return 1
    return 0


def _issue_gap_witness_dossier(  # __s134_gapw_issue_v1__
    args, result, th_ast, policies, cov_threshold, src_path
) -> int:
    """Issue a coverage-gap-witness (refutation) dossier when the coverage
    obligation over cov_threshold is NOT proven. Returns 0 if a signed
    gap-witness manifest + coverage.gapwitness.json were written, 1 on any
    refusal (no usable witness, signing/IO failure, or an incompatible flag).
    The witness is UNTRUSTED at issuance: it is independently re-checked by
    the emitted verify_offline.py via rational arithmetic, zero solver, zero
    issuer trust. It proves a gap EXISTS at the carried point; NOT a
    compliance pass, NOT misbehavior, NOT uniqueness or maximality.
    """
    from coverage_farkas import (
        find_gap_witness_point as _find_gw_point,
        serialize_gap_witness as _ser_gw,
        FarkasError as _FarkasError_gw,
    )

    if getattr(args, "no_manifest", False):
        print(
            "REFUSED: --gap-witness writes a signed refutation dossier and "
            "is incompatible with --no-manifest. No manifest written.",
            file=sys.stderr,
        )
        return 1
    if getattr(args, "supersedes", None):
        print(
            "REFUSED: --gap-witness issues a standalone refutation artifact "
            "with no chain semantics; --supersedes is not applicable. No "
            "manifest written.",
            file=sys.stderr,
        )
        return 1

    blocking = [
        p.signal for p in policies
        if getattr(p, "action", None) in ("block", "abort_cycle")
    ]
    try:
        point = _find_gw_point(th_ast, blocking)
    except _FarkasError_gw as e:
        print(
            "REFUSED: coverage not proven and the gap-witness search "
            "refused (" + str(e) + "); no manifest written.",
            file=sys.stderr,
        )
        return 1
    if point is None:
        print(
            "REFUSED: coverage not proven by the solver, but no rational "
            "gap-witness point could be constructed over the linear "
            "fragment (the gap may be non-linear); no manifest written.",
            file=sys.stderr,
        )
        return 1
    try:
        gw_doc = _ser_gw(
            th_ast, blocking, point, threshold_expr=cov_threshold
        )
    except _FarkasError_gw as e:
        print(
            "REFUSED: gap-witness serialization refused (" + str(e)
            + "); no manifest written.",
            file=sys.stderr,
        )
        return 1

    gw_script = _json_s116.dumps(gw_doc, sort_keys=True, indent=2) + "\n"
    gw_sha = _hashlib_s115.sha256(gw_script.encode("utf-8")).hexdigest()

    nous_version = _import_nous_version()
    manifest = manifest_from_verify(result, nous_version=nous_version)
    manifest = _dc_s115.replace(
        manifest,
        source_kind="gap-witness",
        gap_witness_sha256=gw_sha,
    )

    try:
        priv, pub, key_path = load_or_create_keypair(
            Path(args.key_path)
            if getattr(args, "key_path", None) else None
        )
    except Exception as e:
        print(
            "WARN: keypair unavailable; gap-witness manifest unsigned. "
            "Reason: " + str(e),
            file=sys.stderr,
        )
        return 1
    try:
        sig = sign_manifest(manifest, priv)
        doc = manifest_json(manifest, sig, pub)
    except Exception as e:
        print(
            "WARN: gap-witness signing failed: " + str(e), file=sys.stderr
        )
        return 1

    out_path = (
        Path(args.manifest_out)
        if getattr(args, "manifest_out", None)
        else src_path.with_suffix(".manifest.json")
    )
    try:
        out_path.write_text(doc, encoding="utf-8")
        gw_path = out_path.parent / "coverage.gapwitness.json"
        gw_path.write_text(gw_script, encoding="utf-8")
    except Exception as e:
        print(
            "WARN: could not write gap-witness dossier to "
            + str(out_path) + ": " + str(e),
            file=sys.stderr,
        )
        return 1

    print()
    print(
        "REFUTATION ISSUED: coverage NOT proven over threshold '"
        + cov_threshold + "'; a coverage-gap-witness was constructed."
    )
    print(
        "  gap-witness:  " + str(gw_path) + " (sha256 " + gw_sha[:16] + "...)"
    )
    print(
        "  manifest:     " + str(out_path)
        + " (source_kind=gap-witness, unsigned-coverage refutation)"
    )
    print("  key:          " + str(key_path))
    print(
        "  boundary:     proves a gap EXISTS at the carried point; NOT a "
        "compliance pass, NOT misbehavior, NOT unique or maximal."
    )
    return 0
