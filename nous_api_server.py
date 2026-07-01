"""
NOUS HTTP API Server (FastAPI + slowapi + uvicorn).
# __nous_api_server_v1__
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
import tempfile
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from ast_nodes import NousProgram

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse  # __session77_skill_export_endpoint_v1__
from pydantic import BaseModel, ConfigDict, Field  # __session77_skill_export_endpoint_v1__
import zipfile  # __session77_skill_export_endpoint_v1__
from io import BytesIO  # __session77_skill_export_endpoint_v1__
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# Constants and Pydantic models live in nous_api.py
from nous_api import (
    VERSION,
    NOUS_DIR,
    TEMPLATES_DIR,
    LOG_FILE,
    START_TIME,
    API_KEYS,
    logger,
    CompileRequest,
    VerifyRequest,
    RunRequest,
    ChatRequest,
    WebhookPayload,
    DiffRequest,
    ErrorResponse,
)

# __parse_nous_global_import_v1__
from parser import parse_nous  # noqa: E402  top-level avoids NameError class

# __pipeline_globals_v1__
from validator import NousValidator  # noqa: E402
from typechecker import typecheck_program  # noqa: E402
from codegen import NousCodeGen  # noqa: E402
# __verify_program_global_v1__
from verifier import verify_program  # noqa: E402
# __mood_engine_global_v1__
from mood_engine import MoodEngine  # noqa: E402

def _build_mood_from_ast(_emotions_node: object) -> Optional[MoodEngine]:
    """Dead reference shim. Original symbol never defined; callers
    treat None as 'no mood configured' and continue. Logged so the
    absence is observable in production.
    """
    logger.warning(
        "_build_mood_from_ast called but not implemented; mood disabled"
    )
    return None

def _register_sense_world(*_args: object, **_kwargs: object) -> None:
    """Dead reference shim. Original symbol never defined; callers
    wrap this in try/except. Raising keeps the warning path active
    so removal becomes visible in logs rather than silent.
    """
    raise NotImplementedError("_register_sense_world is not implemented")

# Rate limiter (module-level; server-only)
limiter = Limiter(key_func=get_remote_address)

# Ensure NOUS_DIR is on sys.path for internal module imports below
if str(NOUS_DIR) not in sys.path:
    sys.path.insert(0, str(NOUS_DIR))





# ── Auth ──

def require_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    if not API_KEYS:
        return "no-auth"
    if not x_api_key:
        return "anonymous"
    if x_api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail={"error": "Invalid API key", "code": "AUTH001"})
    return x_api_key


# ── App ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"NOUS API v{VERSION} starting")
    TEMPLATES_DIR.mkdir(exist_ok=True)
    yield
    logger.info("NOUS API shutting down")

app = FastAPI(
    root_path="/api",
    title="NOUS API",
    version=VERSION,
    description="HTTP API for the NOUS programming language",
    lifespan=lifespan,
)

app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"error": "Rate limit exceeded", "code": "RATE001"},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ──

def _compile_pipeline(source: str) -> dict[str, Any]:
    program = parse_nous(source)
    if program.world and getattr(program, "custom_senses", None):
        try:
            _register_sense_world(program.world.name, program)
        except Exception as _sr_exc:
            logger.warning("sense registry load failed: %s", _sr_exc)

    val_result = NousValidator(program).validate()
    val_errors = [{"code": e.code, "severity": e.severity, "message": e.message, "location": e.location} for e in val_result.errors]
    val_warnings = [{"code": w.code, "severity": w.severity, "message": w.message, "location": w.location} for w in val_result.warnings]

    if not val_result.ok:
        return {
            "ok": False,
            "stage": "validate",
            "errors": val_errors,
            "warnings": val_warnings,
        }

    tc_result = typecheck_program(program)
    tc_errors = [{"code": e.code, "message": e.message} for e in tc_result.errors]
    tc_warnings = [{"code": w.code, "message": w.message} for w in tc_result.warnings]

    if not tc_result.ok:
        return {
            "ok": False,
            "stage": "typecheck",
            "errors": tc_errors,
            "warnings": val_warnings + tc_warnings,
        }

    gen = NousCodeGen(program)
    python_code = gen.generate()

    # __hx_pyc_leak_fix_v1__ in-memory compile; removes /tmp .py write + /tmp/__pycache__/.pyc leak
    try:
        compile(python_code, "<nous_api_compile>", "exec")
    except SyntaxError as _se:
        return {
            "ok": False,
            "stage": "py_compile",
            "errors": [{"code": "PY001", "message": f"SyntaxError: {_se.msg} at line {_se.lineno}"}],
            "warnings": val_warnings + tc_warnings,
        }
    except (ValueError, TypeError) as _ce:
        return {
            "ok": False,
            "stage": "py_compile",
            "errors": [{"code": "PY001", "message": f"{type(_ce).__name__}: {_ce}"}],
            "warnings": val_warnings + tc_warnings,
        }

    lines = python_code.strip().split("\n")
    soul_count = len(program.souls)
    message_count = len(program.messages)

    return {
        "ok": True,
        "stage": "complete",
        "python": python_code,
        "lines": len(lines),
        "souls": soul_count,
        "messages": message_count,
        "world": program.world.name if program.world else None,
        "errors": [],
        "warnings": val_warnings + tc_warnings,
    }


# ── Endpoints ──

@app.get("/v1/health")
@limiter.limit("200/minute")
async def health(request: Request):
    uptime = int(time.time() - START_TIME)
    return {
        "status": "ok",
        "version": VERSION,
        "uptime_seconds": uptime,
        "engines": 8,
        "subsystems": 12,
        "cli_commands": 61,  # __s196_incd_cli_count_61_v1__  # __s191_cli_count_60_v1__  # __s177_p1_cli_count_59_v1__  # __s170_leg6b_verify_cost_v1__  # __s167_p2b_cli_count_57_v1__  # __s157_u3_cli_count_56_v1__  # __s106_cli_count_53_v1__  # __s104_cli_commands_derived_v1__  # __phase2_stage6_cli_commands_46_v1__  # __s147_cli_count_55_v1__
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/v1/compile")
@limiter.limit("100/minute")
async def compile_source(request: Request, body: CompileRequest, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    logger.info(f"compile request: {len(body.source)} chars")

    try:
        result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _compile_pipeline, body.source),
            timeout=30.0,
        )
        return result
    except asyncio.TimeoutError:
        raise HTTPException(status_code=408, detail={"error": "Compilation timed out (30s)", "code": "TIMEOUT001"})
    except Exception as e:
        logger.error(f"compile error: {traceback.format_exc()}")
        raise HTTPException(status_code=422, detail={"error": str(e), "code": "COMPILE001"})


# __s189_vr003_default_pricing_v2__
_DEFAULT_PRICING = None
_DEFAULT_PRICING_LOADED = False


def _get_default_pricing():
    global _DEFAULT_PRICING, _DEFAULT_PRICING_LOADED
    if not _DEFAULT_PRICING_LOADED:
        try:
            from pricing import load_pricing
            _DEFAULT_PRICING = load_pricing()
        except Exception:
            _DEFAULT_PRICING = None
        _DEFAULT_PRICING_LOADED = True
    return _DEFAULT_PRICING


@app.post("/v1/verify")
@limiter.limit("100/minute")
async def verify_source(request: Request, body: VerifyRequest, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    logger.info(f"verify request: {len(body.source)} chars")

    try:
        def _do_verify():
            program = parse_nous(body.source)

            val_result = NousValidator(program).validate()
            if not val_result.ok:
                return {
                    "ok": False,
                    "stage": "validate",
                    "proven": [],
                    "errors": [{"code": e.code, "message": e.message} for e in val_result.errors],
                    "warnings": [{"code": w.code, "message": w.message} for w in val_result.warnings],
                }

            ver_result = verify_program(program, _get_default_pricing())  # __s189_vr003_wire_pricing_v2__

            proven = []
            warnings = []
            errors = []
            info = []
            for item in ver_result.items:
                entry = {
                    "code": item.code,
                    "category": item.category,
                    "message": item.message,
                    "severity": item.severity.value if hasattr(item.severity, 'value') else str(item.severity),
                    "tier": getattr(item, "tier", "PROVEN"),
                }
                _sev = entry["severity"]
                if _sev == "ERROR":
                    errors.append(entry)
                elif _sev == "WARNING":
                    warnings.append(entry)
                elif _sev == "INFO":
                    info.append(entry)
                else:
                    proven.append(entry)

            return {
                "ok": len(errors) == 0,
                "stage": "complete",
                "proven": proven,
                "errors": errors,
                "warnings": warnings,
                "info": info,
                "total_checks": len(ver_result.items),
            }

        result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _do_verify),
            timeout=30.0,
        )
        return result
    except asyncio.TimeoutError:
        raise HTTPException(status_code=408, detail={"error": "Verification timed out (30s)", "code": "TIMEOUT002"})
    except Exception as e:
        logger.error(f"verify error: {traceback.format_exc()}")
        raise HTTPException(status_code=422, detail={"error": str(e), "code": "VERIFY001"})


class SkillExportEndpointRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    source: str = Field(..., min_length=1, max_length=100_000)
    description: str = Field(..., min_length=1, max_length=1024)
    skill_name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    license: Optional[str] = Field(default=None, min_length=1, max_length=64)
    compatibility: Optional[str] = Field(default=None, min_length=1, max_length=500)
    tool_overrides: list[dict[str, Any]] = Field(default_factory=list)
    with_dossier: bool = Field(default=True)
    anchor: str = Field(default="none", pattern="^(none|rekor)$")  # __nous_aetherproof_api_dossier_anchor_v1__


@app.post("/v1/skill/export")  # __session77_skill_export_endpoint_v1__
@limiter.limit("10/minute")
async def skill_export_endpoint(
    request: Request,
    body: SkillExportEndpointRequest,
    x_api_key: Optional[str] = Header(None),
):
    require_api_key(x_api_key)
    from rekor_anchor import RekorRejected, RekorUnavailable
    logger.info(
        f"skill-export request: {len(body.source)} chars, "
        f"with_dossier={body.with_dossier}"
    )
    try:
        def _do_export() -> tuple[bytes, str]:
            from parser import parse_nous
            from skill_export import (
                ExportRequest,
                ToolBudgetOverride,
                export_skill,
            )
            program = parse_nous(body.source)
            overrides = [
                ToolBudgetOverride(**o) for o in body.tool_overrides
            ]
            export_req = ExportRequest(
                description=body.description,
                skill_name=body.skill_name,
                license=body.license,
                compatibility=body.compatibility,
                tool_overrides=overrides,
            )
            exported = export_skill(program, export_req)
            buf = BytesIO()
            with tempfile.TemporaryDirectory(
                prefix="nous_skill_export_"
            ) as td:
                td_path = Path(td)
                skill_dir = td_path / exported.skill_name
                skill_dir.mkdir()
                (skill_dir / "SKILL.md").write_text(
                    exported.skill_md, encoding="utf-8"
                )
                (skill_dir / "nous.yaml").write_text(
                    exported.nous_yaml, encoding="utf-8"
                )
                if body.with_dossier:
                    from dossier_spec import build_dossier_spec
                    output_dir = td_path / "_dossier_out"
                    key_path = td_path / "_ephemeral_signing.key"
                    dossier_result = build_dossier_spec(
                        skill_dir,
                        output=output_dir,
                        key_path=key_path,
                        anchor=getattr(body, "anchor", "none"),
                    )
                    try:
                        key_path.unlink()
                    except FileNotFoundError:
                        pass
                    with zipfile.ZipFile(
                        buf, "w", zipfile.ZIP_DEFLATED
                    ) as zf:
                        zf.writestr(
                            f"{exported.skill_name}/SKILL.md",
                            exported.skill_md,
                        )
                        zf.writestr(
                            f"{exported.skill_name}/nous.yaml",
                            exported.nous_yaml,
                        )
                        for fname in dossier_result.files:
                            src = output_dir / fname
                            zf.writestr(
                                f"{exported.skill_name}/dossier/{fname}",
                                src.read_bytes(),
                            )
                else:
                    with zipfile.ZipFile(
                        buf, "w", zipfile.ZIP_DEFLATED
                    ) as zf:
                        zf.writestr(
                            f"{exported.skill_name}/SKILL.md",
                            exported.skill_md,
                        )
                        zf.writestr(
                            f"{exported.skill_name}/nous.yaml",
                            exported.nous_yaml,
                        )
            return buf.getvalue(), exported.skill_name
        zip_bytes, skill_name = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _do_export),
            timeout=60.0,
        )
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=\"{skill_name}.zip\""
                ),
                "X-Skill-Name": skill_name,
            },
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=408,
            detail={
                "error": "skill-export timed out (60s)",
                "code": "TIMEOUT003",
            },
        )
    except RekorRejected as e:
        logger.warning(f"skill-export rekor rejected: {e}")
        raise HTTPException(
            status_code=400,
            detail={"error": str(e), "code": "REKOR_REJECTED"},
        )
    except RekorUnavailable as e:
        logger.warning(f"skill-export rekor unavailable: {e}")
        raise HTTPException(
            status_code=503,
            detail={"error": str(e), "code": "REKOR_UNAVAILABLE"},
        )
    except Exception as e:
        logger.error(f"skill-export error: {traceback.format_exc()}")
        raise HTTPException(
            status_code=422,
            detail={"error": str(e), "code": "SKILLEXPORT001"},
        )


# ====================================================================
# S81 #1: POST /v1/verify-dossier (public, unauthenticated, rate-limited).
#
# Convenience wrapper around manifest.parse_manifest_json_with_anchor +
# rekor_anchor.verify_rekor_anchor_offline_detail. The API is NOT in
# the trust path; offline verification with verify_offline.py remains
# the canonical surface. This endpoint exists so the verify.html page
# (S81 #3) and future browser-native verifiers can display structured
# PASS/FAIL results without requiring the user to install Python first.
#
# CORS: inherits global allow_origins=["*"] middleware at module top.
#
# # __session81_verify_dossier_endpoint_v1__
# ====================================================================


# ====================================================================
# S82 #1b: V2 surface for /v1/verify-dossier (state-of-the-art audit shape).
#
# Backward-compatible extension. When request.policy is present, the
# endpoint returns a structured V2 response with verdict + checks +
# evidence + human_readable. When policy is absent, the legacy V1
# response shape is returned unchanged. No existing V1 client breaks.
#
# # __session82_verify_dossier_v2_v1__
# ====================================================================

V2_SPEC_VERSION: str = "verify-dossier/v2"


class VerifyDossierPolicy(BaseModel):
    """Auditor-supplied trust policy for the V2 verification path."""
    model_config = ConfigDict(strict=True, extra="forbid")
    require_anchor: bool = True
    max_anchor_age_seconds: Optional[int] = Field(default=None, ge=0)
    require_pubkey_in_allowlist: bool = True


class CheckResult(BaseModel):
    """Single check outcome.

    ok is a discriminated union:
      - True/False: the check ran and produced a boolean result
      - "skipped_unanchored": no transparency_log block present
      - "skipped_no_policy": policy did not request this check
    """
    model_config = ConfigDict(strict=True, extra="forbid")
    ok: Union[bool, Literal["skipped_unanchored", "skipped_no_policy"]]
    errors: list[str] = Field(default_factory=list)


class V2Checks(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    manifest_well_formed: CheckResult
    manifest_signature_ed25519: CheckResult
    source_sha256_field_well_formed: CheckResult
    transparency_log_present: CheckResult
    rekor_public_key_in_allowlist: CheckResult
    rekor_signed_entry_timestamp: CheckResult
    rekor_leaf_inclusion: CheckResult
    rekor_anchor_age: CheckResult


class V2Evidence(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    manifest_sha256: str
    manifest_canonical_bytes_sha256: Optional[str] = None
    public_key_b64: Optional[str] = None
    rekor_log_index: Optional[int] = None
    rekor_integrated_at: Optional[str] = None
    rekor_log_id: Optional[str] = None
    rekor_anchor_age_seconds: Optional[int] = None


class V2HumanReadable(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    verdict_summary: str
    trust_explanation: str
    next_steps: list[str]


class VerifyDossierEndpointResponseV2(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    spec_version: str
    verdict: Literal["ACCEPT", "REJECT"]
    trust_level: Literal["rekor_anchored", "ed25519_only", "none"]
    policy_applied: VerifyDossierPolicy
    checks: V2Checks
    evidence: V2Evidence
    human_readable: V2HumanReadable


def _run_verification_checks(
    manifest_json_text: str,
    policy: Optional[VerifyDossierPolicy],
) -> "tuple[V2Checks, V2Evidence, str]":
    """Pure function: runs every check on a manifest_json and returns
    (checks, evidence, trust_level). Does NOT compute verdict
    (verdict requires policy + checks; computed by the caller).
    """
    import base64 as _b64
    from datetime import datetime as _dt, timezone as _tz
    from pydantic import ValidationError as _ValidationError

    manifest_well_formed = CheckResult(ok=False, errors=[])
    signature_check = CheckResult(ok=False, errors=[])
    source_sha_format = CheckResult(ok=False, errors=[])
    tlog_present = CheckResult(ok=False, errors=[])
    rekor_allowlist: CheckResult = CheckResult(ok="skipped_unanchored")
    rekor_set: CheckResult = CheckResult(ok="skipped_unanchored")
    rekor_inclusion: CheckResult = CheckResult(ok="skipped_unanchored")
    rekor_age: CheckResult = CheckResult(ok="skipped_unanchored")

    input_bytes = manifest_json_text.encode("utf-8")
    manifest_input_sha256 = hashlib.sha256(input_bytes).hexdigest()
    manifest_canonical_sha256: Optional[str] = None
    public_key_b64_str: Optional[str] = None
    rekor_log_index: Optional[int] = None
    rekor_integrated_at: Optional[str] = None
    rekor_log_id: Optional[str] = None
    rekor_anchor_age_seconds: Optional[int] = None

    try:
        from manifest import (
            parse_manifest_json_with_anchor,
            verify_manifest_signature,
            public_key_b64 as _pubkey_b64_fn,
        )
        m, sig, pub, anchor = parse_manifest_json_with_anchor(
            manifest_json_text
        )
        manifest_well_formed = CheckResult(ok=True)
    except (
        json.JSONDecodeError, KeyError, ValueError,
        TypeError, _ValidationError,
    ) as exc:
        manifest_well_formed = CheckResult(
            ok=False,
            errors=[f"parse_error: {type(exc).__name__}: {exc}"],
        )
    except Exception as exc:
        manifest_well_formed = CheckResult(
            ok=False,
            errors=[
                f"parse_error_unexpected: {type(exc).__name__}: {exc}"
            ],
        )

    if not manifest_well_formed.ok:
        checks = V2Checks(
            manifest_well_formed=manifest_well_formed,
            manifest_signature_ed25519=signature_check,
            source_sha256_field_well_formed=source_sha_format,
            transparency_log_present=tlog_present,
            rekor_public_key_in_allowlist=rekor_allowlist,
            rekor_signed_entry_timestamp=rekor_set,
            rekor_leaf_inclusion=rekor_inclusion,
            rekor_anchor_age=rekor_age,
        )
        evidence = V2Evidence(manifest_sha256=manifest_input_sha256)
        return (checks, evidence, "none")

    canonical_bytes = m.canonical_bytes()
    manifest_canonical_sha256 = hashlib.sha256(
        canonical_bytes
    ).hexdigest()
    public_key_b64_str = _pubkey_b64_fn(pub)

    try:
        sig_ok = verify_manifest_signature(m, sig, pub)
        if sig_ok:
            signature_check = CheckResult(ok=True)
        else:
            signature_check = CheckResult(
                ok=False, errors=["ed25519_signature_invalid"]
            )
    except Exception as exc:
        signature_check = CheckResult(
            ok=False,
            errors=[
                f"signature_check_error: {type(exc).__name__}: {exc}"
            ],
        )

    src_sha = m.source_sha256 or ""
    if (
        len(src_sha) == 64
        and all(c in "0123456789abcdef" for c in src_sha)
    ):
        source_sha_format = CheckResult(ok=True)
    else:
        source_sha_format = CheckResult(
            ok=False,
            errors=[
                f"source_sha256_field_malformed: got len={len(src_sha)}"
            ],
        )

    if anchor is None:
        tlog_present = CheckResult(
            ok=False,
            errors=["transparency_log_block_absent"],
        )
    else:
        tlog_present = CheckResult(ok=True)
        rekor_log_index = anchor.log_index
        rekor_log_id = anchor.log_id
        rekor_integrated_at = (
            _dt.fromtimestamp(anchor.integrated_time, tz=_tz.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
        now_ts = int(_dt.now(tz=_tz.utc).timestamp())
        rekor_anchor_age_seconds = max(
            0, now_ts - anchor.integrated_time
        )

        try:
            from rekor_anchor import (
                verify_rekor_anchor_offline_detail,
            )
            detail = verify_rekor_anchor_offline_detail(
                anchor=anchor,
                expected_manifest_canonical_bytes=canonical_bytes,
                expected_manifest_signature_b64=_b64.b64encode(
                    sig
                ).decode("ascii"),
                expected_manifest_public_key_b64=public_key_b64_str,
            )
            rekor_allowlist = CheckResult(
                ok=bool(detail.pubkey_in_allowlist),
                errors=[
                    e for e in detail.errors if "allowlist" in e
                ],
            )
            rekor_set = CheckResult(
                ok=bool(detail.set_signature_ok),
                errors=[
                    e for e in detail.errors
                    if "set_signature" in e or e.startswith("set_")
                ],
            )
            rekor_inclusion = CheckResult(
                ok=bool(detail.inclusion_body_ok),
                errors=[
                    e for e in detail.errors
                    if "inclusion" in e or "submitter" in e
                    or "leaf" in e
                ],
            )
        except Exception as exc:
            err_str = f"rekor_verify_error: {type(exc).__name__}: {exc}"
            rekor_allowlist = CheckResult(ok=False, errors=[err_str])
            rekor_set = CheckResult(ok=False, errors=[err_str])
            rekor_inclusion = CheckResult(ok=False, errors=[err_str])

        if policy is None or policy.max_anchor_age_seconds is None:
            rekor_age = CheckResult(ok="skipped_no_policy")
        else:
            if rekor_anchor_age_seconds <= policy.max_anchor_age_seconds:
                rekor_age = CheckResult(ok=True)
            else:
                rekor_age = CheckResult(
                    ok=False,
                    errors=[
                        f"anchor_too_old: age="
                        f"{rekor_anchor_age_seconds}s "
                        f"limit={policy.max_anchor_age_seconds}s"
                    ],
                )

    if not signature_check.ok:
        trust_level = "none"
    elif (
        tlog_present.ok
        and rekor_allowlist.ok is True
        and rekor_set.ok is True
        and rekor_inclusion.ok is True
    ):
        trust_level = "rekor_anchored"
    elif signature_check.ok and not tlog_present.ok:
        trust_level = "ed25519_only"
    else:
        trust_level = "none"

    checks = V2Checks(
        manifest_well_formed=manifest_well_formed,
        manifest_signature_ed25519=signature_check,
        source_sha256_field_well_formed=source_sha_format,
        transparency_log_present=tlog_present,
        rekor_public_key_in_allowlist=rekor_allowlist,
        rekor_signed_entry_timestamp=rekor_set,
        rekor_leaf_inclusion=rekor_inclusion,
        rekor_anchor_age=rekor_age,
    )
    evidence = V2Evidence(
        manifest_sha256=manifest_input_sha256,
        manifest_canonical_bytes_sha256=manifest_canonical_sha256,
        public_key_b64=public_key_b64_str,
        rekor_log_index=rekor_log_index,
        rekor_integrated_at=rekor_integrated_at,
        rekor_log_id=rekor_log_id,
        rekor_anchor_age_seconds=rekor_anchor_age_seconds,
    )
    return (checks, evidence, trust_level)


def _compute_v2_verdict(
    checks: V2Checks,
    trust_level: str,
    policy: VerifyDossierPolicy,
) -> str:
    if not checks.manifest_well_formed.ok:
        return "REJECT"
    if not checks.manifest_signature_ed25519.ok:
        return "REJECT"
    if trust_level == "rekor_anchored":
        if (
            policy.max_anchor_age_seconds is not None
            and checks.rekor_anchor_age.ok is False
        ):
            return "REJECT"
        return "ACCEPT"
    if trust_level == "ed25519_only":
        if policy.require_anchor:
            return "REJECT"
        return "ACCEPT"
    return "REJECT"


def _v2_human_readable(
    verdict: str,
    trust_level: str,
    checks: V2Checks,
    policy: VerifyDossierPolicy,
) -> V2HumanReadable:
    if verdict == "ACCEPT":
        if trust_level == "rekor_anchored":
            summary = (
                "Dossier accepted: full Sigstore Rekor anchor verified."
            )
            expl = (
                "The manifest's Ed25519 author signature verifies, "
                "the Rekor signed entry timestamp verifies under the "
                "pinned Sigstore public key, and the Rekor leaf body "
                "binds to the manifest's canonical bytes via "
                "ECDSA-P-256 (Path-beta dual signing)."
            )
            next_steps: list[str] = []
        else:
            summary = (
                "Dossier accepted: Ed25519 author signature verified "
                "(no public anchor)."
            )
            expl = (
                "The dossier carries no transparency_log block. "
                "Author identity is proven by the Ed25519 signature, "
                "but there is no public log entry confirming when "
                "this dossier was issued."
            )
            next_steps = [
                "To obtain anchored evidence, re-issue the dossier "
                "with NOUS v5.3.0 or later using --anchor rekor.",
            ]
    else:
        if not checks.manifest_well_formed.ok:
            summary = "Dossier rejected: manifest could not be parsed."
            expl = (
                "The manifest is malformed (invalid JSON, missing "
                "required fields, or wrong schema). The dossier "
                "cannot be verified."
            )
            next_steps = [
                "Verify the manifest.json file matches the NOUS "
                "manifest schema. See docs/VERIFY_DOSSIER.md.",
            ]
        elif not checks.manifest_signature_ed25519.ok:
            summary = (
                "Dossier rejected: Ed25519 signature invalid."
            )
            expl = (
                "The Ed25519 signature does not verify over the "
                "manifest's canonical bytes. The dossier was tampered "
                "with after signing, or the embedded public key does "
                "not match the signer."
            )
            next_steps = [
                "Do not trust this dossier. Request a freshly signed "
                "copy from the issuer.",
            ]
        elif trust_level == "ed25519_only":
            summary = (
                "Dossier rejected: policy requires a Sigstore Rekor "
                "anchor, none present."
            )
            expl = (
                "The Ed25519 author signature is valid, but the "
                "dossier has no transparency_log block. Audit policy "
                "(require_anchor=true) requires public-log inclusion."
            )
            next_steps = [
                "Either accept with require_anchor=false (Ed25519 "
                "evidence only), or obtain an anchored dossier.",
            ]
        elif (
            policy.max_anchor_age_seconds is not None
            and checks.rekor_anchor_age.ok is False
        ):
            summary = (
                "Dossier rejected: anchor is older than policy limit."
            )
            expl = (
                "The Rekor anchor verifies cryptographically, but "
                "its integrated_time is older than "
                "max_anchor_age_seconds. Audit policy requires "
                "fresher attestations."
            )
            next_steps = [
                "Re-anchor the dossier or relax the age policy.",
            ]
        else:
            summary = (
                "Dossier rejected: one or more checks failed."
            )
            expl = (
                "See the checks block for per-check error details. "
                "Each failed check carries an errors[] list naming "
                "the specific failure."
            )
            next_steps = [
                "Inspect the checks block for the specific failure "
                "(see also docs/VERIFY_DOSSIER.md).",
            ]
    return V2HumanReadable(
        verdict_summary=summary,
        trust_explanation=expl,
        next_steps=next_steps,
    )


def _render_v2_response(
    manifest_json_text: str,
    policy: VerifyDossierPolicy,
) -> VerifyDossierEndpointResponseV2:
    checks, evidence, trust_level = _run_verification_checks(
        manifest_json_text, policy
    )
    verdict = _compute_v2_verdict(checks, trust_level, policy)
    hr = _v2_human_readable(verdict, trust_level, checks, policy)
    return VerifyDossierEndpointResponseV2(
        spec_version=V2_SPEC_VERSION,
        verdict=verdict,
        trust_level=trust_level,
        policy_applied=policy,
        checks=checks,
        evidence=evidence,
        human_readable=hr,
    )


class VerifyDossierEndpointRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    manifest_json: str = Field(min_length=1, max_length=262144)
    policy: Optional[VerifyDossierPolicy] = None


class VerifyDossierEndpointResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    signature_ok: bool
    public_key_b64: Optional[str] = None
    rekor_inclusion_ok: Optional[bool] = None
    rekor_set_ok: Optional[bool] = None
    rekor_log_index: Optional[int] = None
    rekor_integrated_at: Optional[str] = None
    manifest_sha256: str
    errors: list[str] = Field(default_factory=list)


@app.post("/v1/verify-dossier", response_model=None)
@limiter.limit("30/minute")
async def verify_dossier_endpoint(
    request: Request,
    body: VerifyDossierEndpointRequest,
) -> VerifyDossierEndpointResponse:
    # No require_api_key call: this endpoint is public by design.
    # __session81_verify_dossier_endpoint_v1__
    # __session82_verify_dossier_v2_v1__ dispatch:
    if body.policy is not None:
        return _render_v2_response(
            body.manifest_json, body.policy
        )
    import base64 as _b64
    from datetime import datetime as _dt, timezone as _tz
    from pydantic import ValidationError as _ValidationError

    input_bytes: bytes = body.manifest_json.encode("utf-8")
    manifest_sha256_hex: str = hashlib.sha256(input_bytes).hexdigest()
    errors: list[str] = []
    public_key_b64_str: Optional[str] = None
    rekor_inclusion_ok: Optional[bool] = None
    rekor_set_ok: Optional[bool] = None
    rekor_log_index: Optional[int] = None
    rekor_integrated_at: Optional[str] = None
    signature_ok: bool = False

    try:
        from manifest import (
            parse_manifest_json_with_anchor,
            verify_manifest_signature,
            public_key_b64 as _pubkey_b64_fn,
        )
        m, sig, pub, anchor = parse_manifest_json_with_anchor(
            body.manifest_json
        )
    except (
        json.JSONDecodeError,
        KeyError,
        ValueError,
        TypeError,
        _ValidationError,
    ) as exc:
        errors.append(f"parse_error: {type(exc).__name__}: {exc}")
        return VerifyDossierEndpointResponse(
            signature_ok=False,
            manifest_sha256=manifest_sha256_hex,
            errors=errors,
        )
    except Exception as exc:
        errors.append(
            f"parse_error_unexpected: {type(exc).__name__}: {exc}"
        )
        return VerifyDossierEndpointResponse(
            signature_ok=False,
            manifest_sha256=manifest_sha256_hex,
            errors=errors,
        )

    canonical_bytes: bytes = m.canonical_bytes()
    manifest_sha256_hex = hashlib.sha256(canonical_bytes).hexdigest()
    public_key_b64_str = _pubkey_b64_fn(pub)

    try:
        signature_ok = verify_manifest_signature(m, sig, pub)
        if not signature_ok:
            errors.append("ed25519_signature_invalid")
    except Exception as exc:
        signature_ok = False
        errors.append(
            f"signature_check_error: {type(exc).__name__}: {exc}"
        )

    if anchor is not None:
        try:
            from rekor_anchor import (
                verify_rekor_anchor_offline_detail,
            )
            detail = verify_rekor_anchor_offline_detail(
                anchor=anchor,
                expected_manifest_canonical_bytes=canonical_bytes,
                expected_manifest_signature_b64=_b64.b64encode(
                    sig
                ).decode("ascii"),
                expected_manifest_public_key_b64=public_key_b64_str,
            )
            rekor_set_ok = bool(
                detail.pubkey_in_allowlist
                and detail.set_signature_ok
            )
            rekor_inclusion_ok = bool(detail.inclusion_body_ok)
            rekor_log_index = anchor.log_index
            rekor_integrated_at = (
                _dt.fromtimestamp(
                    anchor.integrated_time, tz=_tz.utc
                )
                .isoformat()
                .replace("+00:00", "Z")
            )
            for err in detail.errors:
                errors.append(f"rekor: {err}")
        except Exception as exc:
            rekor_set_ok = False
            rekor_inclusion_ok = False
            errors.append(
                f"rekor_verify_error: {type(exc).__name__}: {exc}"
            )

    return VerifyDossierEndpointResponse(
        signature_ok=signature_ok,
        public_key_b64=public_key_b64_str,
        rekor_inclusion_ok=rekor_inclusion_ok,
        rekor_set_ok=rekor_set_ok,
        rekor_log_index=rekor_log_index,
        rekor_integrated_at=rekor_integrated_at,
        manifest_sha256=manifest_sha256_hex,
        errors=errors,
    )


@app.post("/v1/run")
@limiter.limit("30/minute")
async def run_source(request: Request, body: RunRequest, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    logger.info(f"run request: {len(body.source)} chars, mode={body.mode}, cycles={body.max_cycles}")

    try:
        def _do_run():
            compile_result = _compile_pipeline(body.source)
            if not compile_result["ok"]:
                return {
                    "ok": False,
                    "stage": compile_result["stage"],
                    "errors": compile_result["errors"],
                    "output": None,
                }

            if body.mode == "dry-run":
                _trace_obj = None  # __s105_api_trace_v1__
                if body.emit_trace:
                    from nous_ast_runner import execute_program as _exec_prog
                    _cap: dict[str, Any] = {}
                    _prog = parse_nous(body.source)
                    asyncio.run(_exec_prog(
                        _prog,
                        mode="dry-run",
                        max_cycles=body.max_cycles,
                        source_text=body.source,
                        emit_trace=True,
                        consult_memory=body.consult_memory,  # __s107_u5_srv_consult_v1__
                        apply_remedy=body.apply_remedy,  # __s111_u6_srv_apply_v1__
                        trace_capture=_cap,
                    ))
                    _trace_obj = _cap.get("envelope")
                return {
                    "ok": True,
                    "mode": "dry-run",
                    "compiled": True,
                    "lines": compile_result["lines"],
                    "souls": compile_result["souls"],
                    "messages": compile_result["messages"],
                    "world": compile_result["world"],
                    "output": "Dry run complete. Code compiles and verifies successfully.",
                    "warnings": compile_result["warnings"],
                    "execution_kind": "dry-run",
                    "trace": _trace_obj,
                }

            return {
                "ok": True,
                "mode": "execute",
                "output": "Live execution not yet available via API. Use dry-run mode or nous run on the server.",
                "compiled": True,
                "lines": compile_result["lines"],
                "souls": compile_result["souls"],
                "execution_kind": "refused",  # __s105_exec_kind_v1__
            }

        result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _do_run),
            timeout=60.0,
        )
        return result
    except asyncio.TimeoutError:
        raise HTTPException(status_code=408, detail={"error": "Run timed out (60s)", "code": "TIMEOUT003"})
    except Exception as e:
        logger.error(f"run error: {traceback.format_exc()}")
        raise HTTPException(status_code=422, detail={"error": str(e), "code": "RUN001"})


_chat_sessions: dict[str, dict] = {}
_CHAT_SESSION_TTL = 1800
_MAX_CHAT_SESSIONS = 100


def _get_soul_configs(program) -> dict[str, dict]:
    configs = {}
    for soul in (program.souls or []):
        mind_model = ""
        mind_tier = ""
        if soul.mind:
            mind_model = soul.mind.model if hasattr(soul.mind, 'model') else str(soul.mind)
            if hasattr(soul.mind, 'tier'):
                t = soul.mind.tier
                mind_tier = t.value if hasattr(t, 'value') else str(t) if t else ""
        mem_fields = {}
        if soul.memory and hasattr(soul.memory, 'fields') and soul.memory.fields:
            for f in soul.memory.fields:
                fname = f.name if hasattr(f, 'name') else str(f)
                ftype = f.type_annotation if hasattr(f, 'type_annotation') else "any"
                fdefault = f.default if hasattr(f, 'default') else None
                mem_fields[fname] = {"type": str(ftype) if ftype else "any", "default": fdefault}
        senses_list = []
        if soul.senses:
            if hasattr(soul.senses, 'tools') and soul.senses.tools:
                senses_list = [s.tool if hasattr(s, 'tool') else str(s) for s in soul.senses.tools]
            elif isinstance(soul.senses, list):
                senses_list = [str(s) for s in soul.senses]
        configs[soul.name] = {
            "model": mind_model,
            "tier": mind_tier,
            "memory": mem_fields,
            "senses": senses_list,
        }
    _custom: dict[str, dict] = {}
    for cs in getattr(program, "custom_senses", []) or []:
        _transport = "http_get" if cs.http_get else ("http_post" if cs.http_post else ("shell" if cs.shell else "unknown"))
        _custom[cs.name] = {
            "description": cs.description or "",
            "transport": _transport,
            "returns": cs.returns,
        }
    if _custom:
        configs["__custom_senses__"] = _custom
    _emotions: dict[str, object] = {}
    for soul in (program.souls or []):
        if getattr(soul, "emotions", None) is not None and soul.emotions.enabled:
            _emotions[soul.name] = soul.emotions
    if _emotions:
        configs["__emotions__"] = _emotions
    return configs



SUPERBRAIN_URL = "http://localhost:8900"


async def _superbrain_search(query: str, n_results: int = 3) -> str:
    """Query Superbrain and return formatted knowledge context."""
    import httpx as _hx
    try:
        async with _hx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                f"{SUPERBRAIN_URL}/search",
                json={"query": query, "n_results": n_results, "expand": True},
            )
            data = resp.json()
    except Exception as e:
        logger.debug(f"superbrain query failed: {e}")
        return ""

    chunks = data.get("relevant_domains", data.get("results", []))
    if not chunks:
        return ""

    lines = []
    for c in chunks[:n_results]:
        if isinstance(c, dict):
            text = c.get("content", c.get("text", ""))
            domain = c.get("domain", "")
            if text:
                snippet = str(text)[:400]
                lines.append(f"[{domain}] {snippet}" if domain else snippet)

    if not lines:
        return ""

    return "\n".join(lines)


def _has_superbrain_sense(soul_cfg: dict) -> bool:
    """Check if a soul has superbrain_search in its senses."""
    senses = soul_cfg.get("senses", {})
    tools = senses.get("tools", []) if isinstance(senses, dict) else []
    for t in tools:
        name = t if isinstance(t, str) else getattr(t, "tool", "")
        if name == "superbrain_search":
            return True
    return False




def _get_or_create_mood(sess: dict, soul_name: str, heartbeat_seconds: float = 30.0) -> Optional[MoodEngine]:
    """Lazily create a MoodEngine per soul in the session; apply time-elapsed decay."""
    emotions_map = sess.get("soul_configs", {}).get("__emotions__") or {}
    emotions_node = emotions_map.get(soul_name)
    if emotions_node is None:
        return None
    moods = sess.setdefault("_moods", {})
    engine = moods.get(soul_name)
    if engine is None:
        engine = _build_mood_from_ast(emotions_node)
        if engine is None:
            return None
        moods[soul_name] = engine
        sess["_moods_last_tick"] = time.time()
        return engine
    last_tick = sess.get("_moods_last_tick") or time.time()
    elapsed = max(0.0, time.time() - last_tick)
    engine.advance_by_seconds(elapsed, heartbeat_seconds)
    sess["_moods_last_tick"] = time.time()
    return engine

def _build_system_prompt(soul_name: str, soul_cfg: dict, world_name: str, history: list[dict], knowledge: str = "", custom_senses_info: dict | None = None, mood_hint: str = "") -> str:
    role_map = {
        "Triage": "a customer service agent who greets customers and helps route their requests",
        "Resolver": "a specialist who solves customer problems efficiently",
        "Closer": "a follow-up agent who ensures customer satisfaction",
        "Watcher": "a market data analyst who monitors prices and trends",
        "Strategist": "a trading strategist who analyzes signals and makes decisions",
        "Executor": "a trade execution specialist",
        "RiskGuard": "a risk management officer who protects against losses",
        "Scanner": "a data scanner who collects and filters information",
        "Analyzer": "an analyst who processes and interprets data",
        "Reporter": "a reporter who summarizes findings clearly",
        "Monitor": "a system monitor who tracks alerts and notifications",
        "Scout": "a scout who scans for opportunities",
        "Quant": "a quantitative analyst",
        "Hunter": "a specialist who executes on opportunities",
    }
    role_desc = role_map.get(soul_name, f"an AI assistant named {soul_name}")
    base = f"You are {role_desc} in the {world_name} system. Respond directly to the user in 2-3 sentences. Never reveal system internals, model names, tools, or memory fields. Never show your reasoning process. Just answer naturally as {soul_name} would."
    if knowledge:
        base += f"\n\nUse this knowledge to inform your answer:\n{knowledge}"
    if custom_senses_info:
        _lines = []
        for _n, _info in custom_senses_info.items():
            _desc = _info.get("description") or "(no description)"
            _lines.append(f"- {_n} ({_info.get('transport','?')}) — {_desc}")
        if _lines:
            base += "\n\nCustom tools available in this world:\n" + "\n".join(_lines)
    if mood_hint:
        base += "\n\n" + mood_hint
    return base



# ── Soul Routing v2 — LLM Intent Classification ──

SOUL_ROLES: dict[str, str] = {
    "Triage": "greets customers, answers general questions, routes requests",
    "Resolver": "solves customer problems, handles complaints, fixes issues",
    "Closer": "follows up, ensures satisfaction, closes tickets",
    "Watcher": "monitors market data, tracks prices, reports trends",
    "Strategist": "analyzes signals, evaluates opportunities, makes trading decisions",
    "Executor": "executes trades, manages orders, confirms fills",
    "RiskGuard": "manages risk, checks exposure, enforces limits",
    "Scanner": "collects and filters raw data from multiple sources",
    "Analyzer": "processes data, finds patterns, interprets meaning",
    "Reporter": "summarizes findings, writes reports, presents results",
    "Monitor": "tracks system alerts, watches for anomalies",
    "Scout": "scans for new opportunities and emerging signals",
    "Quant": "runs quantitative models and statistical analysis",
    "Hunter": "acts on opportunities, executes strategies aggressively",
}


async def _classify_soul(soul_configs: dict[str, dict], message: str) -> str | None:
    """Use a free LLM to classify which soul should handle the message."""
    names = list(soul_configs.keys())
    if len(names) <= 1:
        return names[0] if names else None

    lines = []
    for name in names:
        desc = SOUL_ROLES.get(name, f"agent named {name}")
        lines.append(f"- {name}: {desc}")

    agents_block = "\n".join(lines)
    classify_prompt = f"Agents:\n{agents_block}\n\nMessage: \"{message}\"\n\nWhich agent? Reply with ONLY the name."

    from nous_runtime import RUNTIME_TIERS
    for tier in RUNTIME_TIERS:
        if not tier.available or not tier.is_free:
            continue
        try:
            result = await asyncio.wait_for(
                tier.call("You are a router. Output only the agent name, nothing else.", classify_prompt),
                timeout=5.0,
            )
            if result.get("success"):
                answer = result.get("text", "").strip().strip('"').strip("'").strip(".")
                for name in names:
                    if name.lower() == answer.lower():
                        return name
                for name in names:
                    if name.lower() in answer.lower():
                        return name
                logger.info(f"soul classify: LLM said '{answer}' — no match in {names}")
                return None
        except Exception as e:
            logger.debug(f"soul classify tier {tier.name} failed: {e}")
            continue

    return None


async def _route_soul(soul_configs: dict[str, dict], requested, message: str) -> str:
    """Smart routing: explicit request > LLM classification > simple fallback."""
    if requested and requested in soul_configs:
        return requested
    names = list(soul_configs.keys())
    if not names:
        return "Unknown"
    if len(names) == 1:
        return names[0]

    try:
        classified = await _classify_soul(soul_configs, message)
        if classified:
            logger.info(f"soul route: '{message[:50]}' -> {classified} (LLM)")
            return classified
    except Exception as e:
        logger.warning(f"soul classify error: {e}")

    result = _pick_soul(soul_configs, requested, message)
    logger.info(f"soul route: '{message[:50]}' -> {result} (fallback)")
    return result



def _pick_soul(soul_configs: dict, requested, message: str) -> str:
    if requested and requested in soul_configs:
        return requested
    names = list(soul_configs.keys())
    if not names:
        return "Unknown"
    if len(names) == 1:
        return names[0]
    msg_lower = message.lower()
    for name in names:
        if name.lower() in msg_lower:
            return name
    return names[0]


def _cleanup_sessions() -> None:
    import time as _t
    now = _t.time()
    expired = [sid for sid, s in _chat_sessions.items() if now - s.get("last_active", 0) > _CHAT_SESSION_TTL]
    for sid in expired:
        del _chat_sessions[sid]
    while len(_chat_sessions) > _MAX_CHAT_SESSIONS:
        oldest = min(_chat_sessions, key=lambda k: _chat_sessions[k].get("last_active", 0))
        del _chat_sessions[oldest]


@app.post("/v1/chat")
@limiter.limit("30/minute")
async def chat(request: Request, body: ChatRequest, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    import time as _time
    session_id = body.session_id or str(uuid.uuid4())
    logger.info(f"chat request: session={session_id}, soul={body.soul}, world={body.world}")

    _cleanup_sessions()

    if session_id in _chat_sessions:
        sess = _chat_sessions[session_id]
        sess["last_active"] = _time.time()
    else:
        tpl_path = TEMPLATES_DIR / f"{body.world}.nous"
        if not tpl_path.exists():
            available = [f.stem for f in TEMPLATES_DIR.glob("*.nous")] if TEMPLATES_DIR.exists() else []
            raise HTTPException(status_code=404, detail={
                "error": f"World '{body.world}' not found",
                "available": available,
                "code": "CHAT001",
            })
        try:
            source = tpl_path.read_text(encoding="utf-8")
            program = parse_nous(source)
            soul_configs = _get_soul_configs(program)
            world_name = program.world.name if program.world else body.world
        except Exception as e:
            logger.error(f"chat parse error: {e}")
            raise HTTPException(status_code=422, detail={"error": f"Failed to parse {body.world}: {e}", "code": "CHAT002"})

        sess = {
            "world": world_name,
            "template": body.world,
            "soul_configs": soul_configs,
            "history": [],
            "total_cost": 0.0,
            "created": _time.time(),
            "last_active": _time.time(),
        }
        _chat_sessions[session_id] = sess

    soul_configs = sess["soul_configs"]
    chosen_soul = await _route_soul(soul_configs, body.soul, body.message)
    soul_cfg = soul_configs.get(chosen_soul, {})

    sess["history"].append({"role": "user", "content": body.message})
    if len(sess["history"]) > 20:
        sess["history"] = sess["history"][-20:]

    _sb_ctx = ""
    if _has_superbrain_sense(soul_cfg):
        _sb_ctx = await _superbrain_search(body.message)
    _mood_engine = _get_or_create_mood(sess, chosen_soul)
    _mood_hint = _mood_engine.describe() if _mood_engine else ""
    if _mood_engine is not None:
        _msg_lower = body.message.lower()
        _positive_kw = ("thank", "thanks", "great", "awesome", "good job", "well done", "love")
        _negative_kw = ("hate", "stupid", "useless", "bad", "wrong", "terrible", "frustrated", "annoy")
        if any(k in _msg_lower for k in _positive_kw):
            _mood_engine.record_event("positive_message")
        elif any(k in _msg_lower for k in _negative_kw):
            _mood_engine.record_event("negative_message")
    system_prompt = _build_system_prompt(chosen_soul, soul_cfg, sess["world"], sess["history"], knowledge=_sb_ctx, custom_senses_info=sess["soul_configs"].get("__custom_senses__"), mood_hint=_mood_hint)

    context_parts = []
    for msg in sess["history"][:-1]:
        role = msg["role"]
        context_parts.append(f"{role}: {msg['content']}")
    if context_parts:
        user_prompt = "\n".join(context_parts) + f"\nuser: {body.message}\nassistant:"
    else:
        user_prompt = body.message

    if body.mode == "dry-run":
        reply = f"[DRY-RUN] {chosen_soul} in {sess['world']} would respond to: {body.message[:100]}"
        cost = 0.0
        tier_used = "dry-run"
        tokens_in = 0
        tokens_out = 0
        elapsed_ms = 0.0
    else:
        # __api_chat_llm_replay_v1__
        try:
            from nous_runtime import RUNTIME_TIERS
            reply = ""
            cost = 0.0
            tier_used = "none"
            tokens_in = 0
            tokens_out = 0
            elapsed_ms = 0.0

            _replay_mode = getattr(body, "replay_mode", "off")
            _replay_log = getattr(body, "replay_log", None)
            _replay_seed_base = getattr(body, "replay_seed_base", 0)
            _replay_ctx = None
            _replay_store = None
            if _replay_mode != "off":
                if not _replay_log:
                    raise HTTPException(status_code=422, detail={
                        "error": "replay_log is required when replay_mode != 'off'",
                        "code": "CHAT006",
                    })
                try:
                    from replay_runtime import ReplayContext
                    from replay_store import EventStore
                    _replay_store = EventStore.open(_replay_log, mode=_replay_mode)
                    _replay_ctx = ReplayContext(
                        store=_replay_store,
                        mode=_replay_mode,
                        seed_base=int(_replay_seed_base),
                    )
                except Exception as _rerr:
                    logger.error(f"chat replay init failed: {_rerr}")
                    raise HTTPException(status_code=500, detail={
                        "error": f"replay init failed: {_rerr}",
                        "code": "CHAT007",
                    })

            _turn_cycle = int(sess.get("_replay_turn", 0))
            sess["_replay_turn"] = _turn_cycle + 1

            try:
                for tier in RUNTIME_TIERS:
                    if not tier.available:
                        continue

                    async def _do_call(_t=tier) -> dict:
                        return await asyncio.wait_for(
                            _t.call(system_prompt, user_prompt),
                            timeout=35.0,
                        )

                    if _replay_ctx is not None:
                        _messages = [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ]
                        result = await _replay_ctx.record_or_replay_llm(
                            soul=chosen_soul,
                            cycle=_turn_cycle,
                            provider=tier.name,
                            model=getattr(tier, "model", tier.name),
                            messages=_messages,
                            temperature=float(getattr(tier, "temperature", 0.0)),
                            execute=_do_call,
                        )
                    else:
                        result = await _do_call()

                    if result.get("success"):
                        reply = result.get("text", "")
                        cost = result.get("cost", 0.0)
                        tier_used = result.get("tier", tier.name)
                        tokens_in = result.get("tokens_in", 0)
                        tokens_out = result.get("tokens_out", 0)
                        elapsed_ms = result.get("elapsed_ms", 0.0)
                        break
                    else:
                        logger.warning(f"chat tier {tier.name} failed: {result.get('error', '?')}")
                        continue

                if not reply:
                    raise HTTPException(status_code=503, detail={
                        "error": "All LLM tiers failed",
                        "code": "CHAT003",
                    })
            finally:
                if _replay_store is not None:
                    try:
                        _replay_store.close()
                    except Exception as _cerr:
                        logger.warning(f"chat replay store close failed: {_cerr}")

        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail={"error": "Chat timed out (35s)", "code": "CHAT004"})
        except HTTPException:
            raise
        except Exception as e:
            # __api_intervention_hook_v1__
            try:
                from intervention import InterventionBlocked, InterventionAborted
                _is_blocked = isinstance(e, InterventionBlocked)
                _is_aborted = isinstance(e, InterventionAborted)
            except Exception:
                _is_blocked = False
                _is_aborted = False
            if _is_blocked or _is_aborted:
                _outcome = getattr(e, "outcome", None)
                _code = "CHAT_INTERVENTION_BLOCKED" if _is_blocked else "CHAT_INTERVENTION_ABORTED"
                _detail: dict[str, Any] = {
                    "error": "intervention_blocked" if _is_blocked else "intervention_aborted",
                    "code": _code,
                    "action": getattr(_outcome, "action", "block" if _is_blocked else "abort_cycle"),
                    "policies": list(getattr(_outcome, "policy_names", ()) or ()),
                    "score": float(getattr(_outcome, "score", 0.0) or 0.0),
                    "reasons": list(getattr(_outcome, "reasons", ()) or ()),
                    "triggering_event_kind": getattr(_outcome, "event_kind", ""),
                }
                logger.warning(
                    f"chat intervention {_detail['action']}: "
                    f"policies={_detail['policies']} score={_detail['score']:.3f}"
                )
                raise HTTPException(status_code=422, detail=_detail)
            logger.error(f"chat LLM error: {e}")
            raise HTTPException(status_code=500, detail={"error": str(e), "code": "CHAT005"})

    sess["history"].append({"role": "assistant", "content": reply})
    sess["total_cost"] += cost

    return {
        "reply": reply,
        "soul": chosen_soul,
        "world": sess["world"],
        "session_id": session_id,
        "cost": round(cost, 6),
        "total_cost": round(sess["total_cost"], 6),
        "tier": tier_used,
        "tokens": {"in": tokens_in, "out": tokens_out},
        "elapsed_ms": round(elapsed_ms, 1),
        "turns": len([m for m in sess["history"] if m["role"] == "user"]),
        "mode": body.mode,
    }



# ── SSE Streaming Chat ──

@app.post("/v1/chat/stream")
@limiter.limit("30/minute")
async def chat_stream(request: Request, body: ChatRequest, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    _cleanup_sessions()

    session_id = body.session_id or str(uuid.uuid4())

    if session_id in _chat_sessions:
        sess = _chat_sessions[session_id]
    else:
        template_path = TEMPLATES_DIR / f"{body.world}.nous"
        if not template_path.exists():
            raise HTTPException(status_code=404, detail={
                "error": f"World \'{body.world}\' not found", "code": "CHAT001",
            })
        source = template_path.read_text(encoding="utf-8")
        try:
            program = parse_nous(source)
        except Exception as e:
            raise HTTPException(status_code=422, detail={
                "error": f"Parse error: {e}", "code": "CHAT002",
            })
        soul_configs = _get_soul_configs(program)
        if not soul_configs:
            raise HTTPException(status_code=422, detail={
                "error": "No souls found in template", "code": "CHAT002",
            })
        sess = {
            "world": body.world,
            "soul_configs": soul_configs,
            "history": [],
            "total_cost": 0.0,
            "created": time.time(),
            "last_active": time.time(),
        }
        _chat_sessions[session_id] = sess

    sess["last_active"] = time.time()
    chosen_soul = await _route_soul(sess["soul_configs"], getattr(body, "soul", None), body.message)
    soul_cfg = sess["soul_configs"].get(chosen_soul, {})
    _sb_ctx = ""
    if _has_superbrain_sense(soul_cfg):
        _sb_ctx = await _superbrain_search(body.message)
    _mood_engine = _get_or_create_mood(sess, chosen_soul)
    _mood_hint = _mood_engine.describe() if _mood_engine else ""
    if _mood_engine is not None:
        _msg_lower = body.message.lower()
        _positive_kw = ("thank", "thanks", "great", "awesome", "good job", "well done", "love")
        _negative_kw = ("hate", "stupid", "useless", "bad", "wrong", "terrible", "frustrated", "annoy")
        if any(k in _msg_lower for k in _positive_kw):
            _mood_engine.record_event("positive_message")
        elif any(k in _msg_lower for k in _negative_kw):
            _mood_engine.record_event("negative_message")
    system_prompt = _build_system_prompt(chosen_soul, soul_cfg, sess["world"], sess["history"], knowledge=_sb_ctx, custom_senses_info=sess["soul_configs"].get("__custom_senses__"), mood_hint=_mood_hint)

    history_text = ""
    for h in sess["history"][-20:]:
        history_text += f"{h['role']}: {h['content']}\n"
    user_prompt = f"{history_text}user: {body.message}\nassistant:"

    sess["history"].append({"role": "user", "content": body.message})

    if body.mode == "dry-run":
        async def _dry_gen():
            reply = f"[dry-run] {chosen_soul} acknowledges: {body.message}"
            yield f"event: start\ndata: {json.dumps({'soul': chosen_soul, 'tier': 'dry-run', 'session_id': session_id})}\n\n"
            yield f"event: token\ndata: {json.dumps({'t': reply})}\n\n"
            sess["history"].append({"role": "assistant", "content": reply})
            turns = len([m for m in sess["history"] if m["role"] == "user"])
            done_data = json.dumps({"soul": chosen_soul, "world": sess["world"], "session_id": session_id, "elapsed_ms": 0, "cost": 0, "total_cost": round(sess["total_cost"], 6), "tokens": {"in": 0, "out": 0}, "turns": turns, "tier": "dry-run", "mode": "dry-run"})
            yield f"event: done\ndata: {done_data}\n\n"
        return StreamingResponse(
            _dry_gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
        )

    async def _stream_gen():
        from nous_runtime import RUNTIME_TIERS
        nonlocal chosen_soul

        for tier in RUNTIME_TIERS:
            if not tier.available:
                continue

            gen = tier.stream_call(system_prompt, user_prompt)
            first_event = None
            try:
                first_event = await anext(gen)
            except StopAsyncIteration:
                continue

            if first_event[0] == "error":
                logger.warning(f"stream tier {tier.name} failed: {first_event[1].get('error', '?')}")
                await gen.aclose()
                continue

            yield f"event: start\ndata: {json.dumps({'soul': chosen_soul, 'tier': tier.name, 'session_id': session_id})}\n\n"

            if first_event[0] == "token":
                yield f"event: token\ndata: {json.dumps({'t': first_event[1]})}\n\n"

            full_text = first_event[1] if first_event[0] == "token" else ""
            result_data = {}

            if first_event[0] == "done":
                result_data = first_event[1]
                full_text = result_data.get("text", "")
            else:
                async for evt_type, evt_data in gen:
                    if evt_type == "token":
                        yield f"event: token\ndata: {json.dumps({'t': evt_data})}\n\n"
                    elif evt_type == "done":
                        result_data = evt_data
                        full_text = evt_data.get("text", "")
                    elif evt_type == "error":
                        logger.warning(f"stream tier {tier.name} mid-stream error: {evt_data.get('error', '?')}")
                        yield f"event: error\ndata: {json.dumps({'error': evt_data.get('error', 'Stream interrupted'), 'tier': tier.name})}\n\n"
                        return

            sess["history"].append({"role": "assistant", "content": full_text})
            cost = result_data.get("cost", 0.0)
            sess["total_cost"] += cost
            turns = len([m for m in sess["history"] if m["role"] == "user"])

            done_data = json.dumps({"soul": chosen_soul, "world": sess["world"], "session_id": session_id, "elapsed_ms": round(result_data.get("elapsed_ms", 0), 1), "cost": round(cost, 6), "total_cost": round(sess["total_cost"], 6), "tokens": {"in": result_data.get("tokens_in", 0), "out": result_data.get("tokens_out", 0)}, "turns": turns, "tier": result_data.get("tier", tier.name), "mode": "live"})
            yield f"event: done\ndata: {done_data}\n\n"
            return

        yield f"event: error\ndata: {json.dumps({'error': 'All LLM tiers failed', 'code': 'CHAT003'})}\n\n"

    return StreamingResponse(
        _stream_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )



# ── Superbrain Proxy ──

@app.get("/v1/superbrain/health")
@limiter.limit("60/minute")
async def superbrain_health(request: Request, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    import httpx as _hx
    try:
        async with _hx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{SUPERBRAIN_URL}/health")
            return resp.json()
    except Exception as e:
        raise HTTPException(status_code=503, detail={"error": f"Superbrain unreachable: {e}", "code": "SB001"})


@app.get("/v1/superbrain/domains")
@limiter.limit("60/minute")
async def superbrain_domains(request: Request, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    import httpx as _hx
    try:
        async with _hx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{SUPERBRAIN_URL}/domains")
            return resp.json()
    except Exception as e:
        raise HTTPException(status_code=503, detail={"error": f"Superbrain unreachable: {e}", "code": "SB002"})


class SuperbrainSearchRequest(BaseModel):
    query: str
    n_results: int = Field(default=3, ge=1, le=20)
    expand: bool = True


@app.post("/v1/superbrain/search")
@limiter.limit("30/minute")
async def superbrain_search_endpoint(request: Request, body: SuperbrainSearchRequest, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    import httpx as _hx
    try:
        async with _hx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{SUPERBRAIN_URL}/search",
                json={"query": body.query, "n_results": body.n_results, "expand": body.expand},
            )
            return resp.json()
    except Exception as e:
        raise HTTPException(status_code=503, detail={"error": f"Superbrain unreachable: {e}", "code": "SB003"})


@app.get("/v1/templates")
@limiter.limit("200/minute")
async def list_templates(request: Request):
    templates = []
    if TEMPLATES_DIR.exists():
        for f in sorted(TEMPLATES_DIR.glob("*.nous")):
            source = f.read_text(encoding="utf-8")
            soul_count = source.count("soul ")
            lines = len(source.strip().split("\n"))
            templates.append({
                "name": f.stem,
                "file": f.name,
                "souls": soul_count,
                "lines": lines,
                "size": len(source),
            })
    return {"templates": templates, "count": len(templates)}


@app.get("/v1/templates/{name}")
@limiter.limit("200/minute")
async def get_template(request: Request, name: str):
    path = TEMPLATES_DIR / f"{name}.nous"
    if not path.exists():
        raise HTTPException(status_code=404, detail={"error": f"Template '{name}' not found", "code": "TPL001"})

    source = path.read_text(encoding="utf-8")
    return {
        "name": name,
        "file": path.name,
        "source": source,
        "lines": len(source.strip().split("\n")),
    }




CYCLES_PER_DAY = 288
DAYS_PER_MONTH = 30


def _transform_diff_for_ide(
    result_dict: dict,
    old_program: "NousProgram",
    new_program: "NousProgram",
) -> dict:
    from ast_nodes import (
        SoulNode, RouteNode, MatchRouteNode, FanInNode, FanOutNode, FeedbackNode,
    )
    items = result_dict.get("items", [])
    cost_data = result_dict.get("cost", {})
    per_soul_raw = cost_data.get("per_soul", [])

    old_souls: dict[str, SoulNode] = {s.name: s for s in (old_program.souls or [])}
    new_souls: dict[str, SoulNode] = {s.name: s for s in (new_program.souls or [])}
    all_soul_names = sorted(set(list(old_souls.keys()) + list(new_souls.keys())))

    def _get_tier(soul: SoulNode | None) -> str | None:
        if not soul or not soul.mind:
            return None
        t = soul.mind.tier
        return t.value if hasattr(t, "value") else str(t) if t else None

    def _get_senses(soul: SoulNode | None) -> set[str]:
        if not soul or not soul.senses:
            return set()
        return {s.tool for s in soul.senses.tools} if hasattr(soul.senses, "tools") and soul.senses.tools else set()

    def _get_memory_fields(soul: SoulNode | None) -> dict[str, str]:
        if not soul or not soul.memory:
            return {}
        fields = {}
        if hasattr(soul.memory, "fields") and soul.memory.fields:
            for f in soul.memory.fields:
                fname = f.name if hasattr(f, "name") else str(f)
                ftype = f.type_annotation if hasattr(f, "type_annotation") else "any"
                fields[fname] = str(ftype) if ftype else "any"
        return fields

    def _get_wake(soul: SoulNode | None) -> str | None:
        if not soul or not soul.instinct:
            return None
        if hasattr(soul.instinct, "wake") and soul.instinct.wake:
            return str(soul.instinct.wake)
        return None

    def _get_routes(program: "NousProgram") -> list[tuple[str, str]]:
        # __NERVE_DISPATCH_NOUS_API_SERVER_NESTED_v1__
        from ast_nodes import iter_route_edges
        return [(s, t) for s, t, _ in iter_route_edges(program.nervous_system)]

    cost_lookup = {e["soul"]: e for e in per_soul_raw}
    souls_list = []
    for name in all_soul_names:
        old_s = old_souls.get(name)
        new_s = new_souls.get(name)
        c = cost_lookup.get(name, {})
        souls_list.append({
            "name": name,
            "before": c.get("old", 0.0) if old_s else None,
            "after": c.get("new", 0.0) if new_s else None,
            "tier_before": _get_tier(old_s),
            "tier_after": _get_tier(new_s),
        })

    total_before = cost_data.get("old_total", 0.0)
    total_after = cost_data.get("new_total", 0.0)

    senses_added = []
    senses_removed = []
    fields_added = []
    fields_removed = []
    wake_changes = []

    for name in all_soul_names:
        old_s = old_souls.get(name)
        new_s = new_souls.get(name)
        old_senses = _get_senses(old_s)
        new_senses = _get_senses(new_s)
        for s in new_senses - old_senses:
            senses_added.append({"soul": name, "sense": s})
        for s in old_senses - new_senses:
            senses_removed.append({"soul": name, "sense": s})
        old_mem = _get_memory_fields(old_s)
        new_mem = _get_memory_fields(new_s)
        for f in set(new_mem.keys()) - set(old_mem.keys()):
            fields_added.append({"soul": name, "field": f, "type": new_mem[f]})
        for f in set(old_mem.keys()) - set(new_mem.keys()):
            fields_removed.append({"soul": name, "field": f, "type": old_mem[f]})
        old_wake = _get_wake(old_s)
        new_wake = _get_wake(new_s)
        if old_wake != new_wake and old_s and new_s:
            wake_changes.append({"soul": name, "from": old_wake or "NONE", "to": new_wake or "NONE"})

    old_routes = _get_routes(old_program)
    new_routes = _get_routes(new_program)
    route_changes = []
    for r in old_routes:
        if r not in new_routes:
            route_changes.append({"from": f"{r[0]}\u2192{r[1]}", "to": None, "type": "removed"})
    for r in new_routes:
        if r not in old_routes:
            route_changes.append({"from": None, "to": f"{r[0]}\u2192{r[1]}", "type": "added"})

    sev_map = {"CRITICAL": "CRITICAL", "WARN": "WARNING", "WARNING": "WARNING", "INFO": "INFO"}
    c_count = w_count = i_count = 0
    findings = []
    cc = wc = ic = 0
    for item in items:
        raw_sev = item.get("severity", "INFO")
        sev = sev_map.get(raw_sev, "INFO")
        if sev == "CRITICAL":
            cc += 1
            c_count += 1
            code = f"BD-C{cc:03d}"
        elif sev == "WARNING":
            wc += 1
            w_count += 1
            code = f"BD-W{wc:03d}"
        else:
            ic += 1
            i_count += 1
            code = f"BD-I{ic:03d}"
        findings.append({
            "severity": sev,
            "code": code,
            "category": item.get("category", "General"),
            "message": item.get("message", ""),
        })

    return {
        "source": "original.nous",
        "target": "modified.nous",
        "verdict": {"critical": c_count, "warning": w_count, "info": i_count},
        "topology": {
            "added": result_dict.get("souls_added", []),
            "removed": result_dict.get("souls_removed", []),
            "modified": result_dict.get("souls_modified", []),
            "route_changes": route_changes,
        },
        "cost": {
            "souls": souls_list,
            "total_before": total_before,
            "total_after": total_after,
            "daily_before": round(total_before * CYCLES_PER_DAY, 2),
            "daily_after": round(total_after * CYCLES_PER_DAY, 2),
            "monthly_before": round(total_before * CYCLES_PER_DAY * DAYS_PER_MONTH, 2),
            "monthly_after": round(total_after * CYCLES_PER_DAY * DAYS_PER_MONTH, 2),
        },
        "protocol": {
            "messages_added": result_dict.get("messages_added", []),
            "messages_removed": result_dict.get("messages_removed", []),
            "mismatches": [],
        },
        "performance": {
            "heartbeat_changes": [],
            "wake_strategy_changes": wake_changes,
        },
        "capabilities": {
            "senses_added": senses_added,
            "senses_removed": senses_removed,
        },
        "memory": {
            "fields_added": fields_added,
            "fields_removed": fields_removed,
        },
        "findings": findings,
    }


@app.post("/v1/diff")
@limiter.limit("60/minute")
async def diff_source(request: Request, body: DiffRequest, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    logger.info("diff request")
    try:
        loop = asyncio.get_event_loop()

        def _run_diff() -> dict:
            import tempfile
            from behavioral_diff import behavioral_diff

            old_program = parse_nous(body.original)
            new_program = parse_nous(body.modified)
            result = behavioral_diff(old_program, new_program)
            raw = result.to_dict()
            return _transform_diff_for_ide(raw, old_program, new_program)

        result = await asyncio.wait_for(
            loop.run_in_executor(None, _run_diff),
            timeout=30.0,
        )
        # __DIFF_SIDE_RESPONSE_LABELS_v1__
        from nous_api import render_diff_side
        result["original_label"] = render_diff_side(body.original_side)
        result["modified_label"] = render_diff_side(body.modified_side)
        return JSONResponse(content={"ok": True, "diff": result})
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Diff timed out (30s)")
    except Exception as e:
        logger.error(f"diff error: {e}")
        raise HTTPException(status_code=422, detail=str(e))




# ── Webhook Internals ──

_tg_worlds: dict[int, str] = {}


async def _webhook_chat(
    message: str,
    world: str = "customer_service",
    soul: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Internal chat for webhook handlers. Returns reply dict or error dict."""
    import httpx as _hx
    session_id = session_id or str(uuid.uuid4())
    _cleanup_sessions()

    if session_id in _chat_sessions:
        sess = _chat_sessions[session_id]
    else:
        template_path = TEMPLATES_DIR / f"{world}.nous"
        if not template_path.exists():
            return {"error": f"World '{world}' not found"}
        source = template_path.read_text(encoding="utf-8")
        try:
            program = parse_nous(source)
        except Exception as e:
            return {"error": f"Parse error: {e}"}
        soul_configs = _get_soul_configs(program)
        if not soul_configs:
            return {"error": "No souls in template"}
        sess = {
            "world": world,
            "soul_configs": soul_configs,
            "history": [],
            "total_cost": 0.0,
            "created": time.time(),
            "last_active": time.time(),
        }
        _chat_sessions[session_id] = sess

    sess["last_active"] = time.time()
    chosen_soul = await _route_soul(sess["soul_configs"], soul, message)
    soul_cfg = sess["soul_configs"].get(chosen_soul, {})
    _sb_ctx = ""
    if _has_superbrain_sense(soul_cfg):
        _sb_ctx = await _superbrain_search(message)
    _mood_engine = _get_or_create_mood(sess, chosen_soul)
    _mood_hint = _mood_engine.describe() if _mood_engine else ""
    if _mood_engine is not None:
        _msg_lower = (message or "").lower()
        _positive_kw = ("thank", "thanks", "great", "awesome", "good job", "well done", "love")
        _negative_kw = ("hate", "stupid", "useless", "bad", "wrong", "terrible", "frustrated", "annoy")
        if any(k in _msg_lower for k in _positive_kw):
            _mood_engine.record_event("positive_message")
        elif any(k in _msg_lower for k in _negative_kw):
            _mood_engine.record_event("negative_message")
    system_prompt = _build_system_prompt(chosen_soul, soul_cfg, sess["world"], sess["history"], knowledge=_sb_ctx, custom_senses_info=sess["soul_configs"].get("__custom_senses__"), mood_hint=_mood_hint)

    history_text = ""
    for h in sess["history"][-20:]:
        history_text += f"{h['role']}: {h['content']}\n"
    user_prompt = f"{history_text}user: {message}\nassistant:"

    sess["history"].append({"role": "user", "content": message})

    from nous_runtime import RUNTIME_TIERS
    reply = ""
    cost = 0.0
    tier_used = "none"
    tokens_in = 0
    tokens_out = 0
    elapsed_ms = 0.0

    for tier in RUNTIME_TIERS:
        if not tier.available:
            continue
        try:
            result = await asyncio.wait_for(
                tier.call(system_prompt, user_prompt),
                timeout=35.0,
            )
            if result.get("success"):
                reply = result.get("text", "")
                cost = result.get("cost", 0.0)
                tier_used = result.get("tier", tier.name)
                tokens_in = result.get("tokens_in", 0)
                tokens_out = result.get("tokens_out", 0)
                elapsed_ms = result.get("elapsed_ms", 0.0)
                break
            else:
                logger.warning(f"webhook tier {tier.name} failed: {result.get('error', '?')}")
        except Exception as e:
            logger.warning(f"webhook tier {tier.name} exception: {e}")
            continue

    if not reply:
        sess["history"].pop()
        return {"error": "All LLM tiers failed"}

    sess["history"].append({"role": "assistant", "content": reply})
    sess["total_cost"] += cost
    turns = len([m for m in sess["history"] if m["role"] == "user"])

    return {
        "reply": reply,
        "soul": chosen_soul,
        "world": sess["world"],
        "session_id": session_id,
        "cost": round(cost, 6),
        "total_cost": round(sess["total_cost"], 6),
        "tier": tier_used,
        "tokens": {"in": tokens_in, "out": tokens_out},
        "elapsed_ms": round(elapsed_ms, 1),
        "turns": turns,
    }


async def _handle_telegram(payload: dict) -> JSONResponse:
    import httpx as _hx

    msg = payload.get("message") or payload.get("edited_message") or {}
    text = (msg.get("text") or "").strip()
    chat_id = msg.get("chat", {}).get("id")
    user_name = msg.get("from", {}).get("first_name", "User")

    if not chat_id:
        return JSONResponse({"ok": True})

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")

    async def _tg_reply(reply_text: str) -> None:
        if not bot_token:
            return
        try:
            async with _hx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": reply_text},
                )
        except Exception as e:
            logger.error(f"telegram send failed: {e}")

    if not text:
        return JSONResponse({"ok": True})

    session_key = f"tg_{chat_id}"

    if text == "/start" or text == "/help":
        worlds = []
        if TEMPLATES_DIR.exists():
            worlds = [f.stem for f in sorted(TEMPLATES_DIR.glob("*.nous"))]
        help_lines = [
            "NOUS Agent Bot",
            "",
            "/world <name> - Switch world",
            "/worlds - List available worlds",
            "/status - Session info",
            "/clear - Reset session",
            "",
            "Available worlds: " + ", ".join(worlds) if worlds else "No worlds configured",
            "",
            "Just type to chat!",
        ]
        await _tg_reply("\n".join(help_lines))
        return JSONResponse({"ok": True})

    if text == "/worlds":
        worlds = []
        if TEMPLATES_DIR.exists():
            worlds = [f.stem for f in sorted(TEMPLATES_DIR.glob("*.nous"))]
        current = _tg_worlds.get(chat_id, "customer_service")
        lines = ["Available worlds:"]
        for w in worlds:
            marker = " (active)" if w == current else ""
            lines.append(f"  {w}{marker}")
        await _tg_reply("\n".join(lines))
        return JSONResponse({"ok": True})

    if text.startswith("/world "):
        world_name = text[7:].strip()
        template_path = TEMPLATES_DIR / f"{world_name}.nous"
        if template_path.exists():
            _chat_sessions.pop(session_key, None)
            _tg_worlds[chat_id] = world_name
            await _tg_reply(f"Switched to world: {world_name}")
        else:
            worlds = [f.stem for f in sorted(TEMPLATES_DIR.glob("*.nous"))] if TEMPLATES_DIR.exists() else []
            await _tg_reply(f"World '{world_name}' not found. Available: {', '.join(worlds)}")
        return JSONResponse({"ok": True})

    if text == "/clear":
        _chat_sessions.pop(session_key, None)
        await _tg_reply("Session cleared.")
        return JSONResponse({"ok": True})

    if text == "/status":
        sess = _chat_sessions.get(session_key)
        if sess:
            turns = len([m for m in sess["history"] if m["role"] == "user"])
            lines = [
                f"World: {sess['world']}",
                f"Turns: {turns}",
                f"Cost: ${sess['total_cost']:.4f}",
            ]
            await _tg_reply("\n".join(lines))
        else:
            await _tg_reply("No active session. Send a message to start.")
        return JSONResponse({"ok": True})

    if text.startswith("/"):
        await _tg_reply("Unknown command. Send /help for usage.")
        return JSONResponse({"ok": True})

    world = _tg_worlds.get(chat_id, "customer_service")
    logger.info(f"telegram: chat_id={chat_id} user={user_name} world={world}")

    result = await _webhook_chat(text, world=world, session_id=session_key)

    if "error" in result:
        await _tg_reply(f"Error: {result['error']}")
    else:
        await _tg_reply(result["reply"])

    return JSONResponse({"ok": True})


async def _handle_slack(payload: dict) -> dict[str, Any]:
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}

    if payload.get("type") == "event_callback":
        event = payload.get("event", {})
        if event.get("type") == "message" and not event.get("bot_id") and not event.get("subtype"):
            text = event.get("text", "")
            channel = event.get("channel", "")
            if text and channel:
                session_key = f"slack_{channel}"
                result = await _webhook_chat(text, world="customer_service", session_id=session_key)

                slack_token = os.environ.get("SLACK_BOT_TOKEN", "")
                if slack_token and "reply" in result:
                    import httpx as _hx
                    try:
                        async with _hx.AsyncClient(timeout=10.0) as client:
                            await client.post(
                                "https://slack.com/api/chat.postMessage",
                                headers={"Authorization": f"Bearer {slack_token}"},
                                json={"channel": channel, "text": result["reply"]},
                            )
                    except Exception as e:
                        logger.error(f"slack send failed: {e}")

    return {"ok": True}


async def _handle_generic(payload: dict) -> dict[str, Any]:
    message = payload.get("message", "")
    if not message:
        return {"error": "Missing 'message' field", "code": "WH001"}

    world = payload.get("world", "customer_service")
    soul = payload.get("soul")
    session_id = payload.get("session_id")
    callback_url = payload.get("callback_url")

    result = await _webhook_chat(message, world=world, soul=soul, session_id=session_id)

    if callback_url and "reply" in result:
        import httpx as _hx
        try:
            async with _hx.AsyncClient(timeout=10.0) as client:
                await client.post(callback_url, json=result)
            result["callback_sent"] = True
        except Exception as e:
            logger.warning(f"callback failed: {callback_url} -> {e}")
            result["callback_sent"] = False
            result["callback_error"] = str(e)

    return result


@app.post("/v1/webhook/{channel}")
@limiter.limit("100/minute")
async def webhook(request: Request, channel: str, x_api_key: Optional[str] = Header(None)):
    if channel not in ("telegram",):
        require_api_key(x_api_key)

    try:
        raw = await request.body()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw.decode("utf-8", errors="replace")}
    except Exception:
        payload = {}

    event_id = str(uuid.uuid4())
    logger.info(f"webhook: channel={channel}, event={event_id}, size={len(raw)}")

    if channel == "telegram":
        return await _handle_telegram(payload)
    elif channel == "slack":
        return await _handle_slack(payload)
    elif channel in ("n8n", "zapier", "generic", "make"):
        return await _handle_generic(payload)
    else:
        return {
            "received": True,
            "channel": channel,
            "event_id": event_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": "Unknown channel. Supported: telegram, slack, n8n, zapier, generic, make.",
        }


# ── Error Handlers ──

# 422 handler removed — let FastAPI show real errors


# --- Phase G Layer 4: Governance Dashboard Endpoints ---
# __governance_api_v1__

@app.get("/v1/governance/policies")
@limiter.limit("60/minute")
async def governance_policies(request: Request, world: Optional[str] = None, x_api_key: Optional[str] = Header(None)):
    """List active policies for a world template."""
    require_api_key(x_api_key)
    try:
        from governance import PolicyInspector
    except ImportError:
        raise HTTPException(status_code=501, detail={"error": "governance module not available", "code": "GOV001"})

    if world:
        tpl_path = TEMPLATES_DIR / f"{world}.nous"
        if not tpl_path.exists():
            available = [f.stem for f in TEMPLATES_DIR.glob("*.nous")] if TEMPLATES_DIR.exists() else []
            raise HTTPException(status_code=404, detail={
                "error": f"World '{world}' not found",
                "available": available,
                "code": "GOV002",
            })
        policies = PolicyInspector.from_file(tpl_path)
        return {"world": world, "policies": [p.to_dict() for p in policies]}

    all_policies: dict[str, list[dict]] = {}
    if TEMPLATES_DIR.exists():
        for tpl in sorted(TEMPLATES_DIR.glob("*.nous")):
            pols = PolicyInspector.from_file(tpl)
            if pols:
                all_policies[tpl.stem] = [p.to_dict() for p in pols]
    return {"worlds": all_policies, "total_worlds": len(all_policies)}


@app.get("/v1/governance/interventions")
@limiter.limit("60/minute")
async def governance_interventions(
    request: Request,
    log: str = "",
    soul: Optional[str] = None,
    action: Optional[str] = None,
    since: Optional[float] = None,
    limit: int = 100,
    x_api_key: Optional[str] = Header(None),
):
    """Query intervention events from a replay log."""
    require_api_key(x_api_key)
    if not log:
        raise HTTPException(status_code=422, detail={"error": "log parameter required (path to .jsonl event log)", "code": "GOV003"})
    try:
        from governance import GovernanceLog
    except ImportError:
        raise HTTPException(status_code=501, detail={"error": "governance module not available", "code": "GOV001"})

    from pathlib import Path as _P
    log_path = _P(log)
    if not log_path.exists():
        raise HTTPException(status_code=404, detail={"error": f"log file not found: {log}", "code": "GOV004"})

    try:
        glog = GovernanceLog(log_path)
        records = glog.query(soul=soul, action=action, since=since, limit=min(limit, 1000))
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": f"failed to read log: {exc}", "code": "GOV005"})

    return {
        "log": log,
        "total_in_log": glog.total_events,
        "interventions_returned": len(records),
        "interventions": [r.to_dict() for r in records],
    }


@app.get("/v1/governance/stats")
@limiter.limit("60/minute")
async def governance_stats(
    request: Request,
    log: str = "",
    x_api_key: Optional[str] = Header(None),
):
    """Aggregated governance statistics from a replay log."""
    require_api_key(x_api_key)
    if not log:
        raise HTTPException(status_code=422, detail={"error": "log parameter required (path to .jsonl event log)", "code": "GOV003"})
    try:
        from governance import GovernanceLog
    except ImportError:
        raise HTTPException(status_code=501, detail={"error": "governance module not available", "code": "GOV001"})

    from pathlib import Path as _P
    log_path = _P(log)
    if not log_path.exists():
        raise HTTPException(status_code=404, detail={"error": f"log file not found: {log}", "code": "GOV004"})

    try:
        glog = GovernanceLog(log_path)
        stats = glog.stats()
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": f"failed to read log: {exc}", "code": "GOV005"})

    return {
        "log": log,
        **stats.to_dict(),
    }


# __policy_preview_api_v1__

class _PolicyPreviewRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=200_000)


@app.post("/v1/governance/policies/preview")
@limiter.limit("60/minute")
async def governance_policies_preview(request: Request, body: _PolicyPreviewRequest, x_api_key: Optional[str] = Header(None)):
    """Parse raw .nous source and return declared policies.

    Used by the policies editor UI to live-preview policy declarations
    without requiring a world template on disk.
    """
    require_api_key(x_api_key)
    try:
        from governance import PolicyInspector
    except ImportError:
        raise HTTPException(status_code=501, detail={"error": "governance module not available", "code": "GOV001"})

    try:
        policies = PolicyInspector.from_source(body.source, source_file="<editor>")
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "code": "GOV006",
            "policies": [],
        }

    return {
        "ok": True,
        "policies": [p.to_dict() for p in policies],
        "count": len(policies),
    }


# __governance_lint_api_v1__

class _PolicyLintRequest(BaseModel):
    source: str = Field(default="", max_length=200_000)
    strict: bool = False


@app.post("/v1/governance/lint")
@limiter.limit("60/minute")
async def governance_lint(request: Request, body: _PolicyLintRequest, x_api_key: Optional[str] = Header(None)):
    """Run static analysis on .nous source.

    Returns a structured lint report: errors, warnings, infos per rule.
    Used by the IDE governance tab for live policy QA.
    """
    require_api_key(x_api_key)
    try:
        from governance_lint import GovernanceLinter
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail={"error": "governance_lint module not available", "code": "LNT001"},
        )
    try:
        linter = GovernanceLinter()
        report = linter.lint_source(body.source, source_file="<editor>")
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "code": "LNT002",
            "report": None,
        }
    return {
        "ok": True,
        "report": report.to_dict(),
        "would_fail_strict": bool(report.has_errors or (body.strict and report.has_warnings)),
    }


# __governance_simulate_api_v1__

class _PolicySimulateRequest(BaseModel):
    source: str = Field(default="", max_length=200_000)
    event_kind: str = Field(default="", max_length=256)
    event_data: dict[str, Any] = Field(default_factory=dict)


@app.post("/v1/governance/simulate")
@limiter.limit("60/minute")
async def governance_simulate(request: Request, body: _PolicySimulateRequest, x_api_key: Optional[str] = Header(None)):
    """Simulate an event against declared policies and return which fire.

    Body:    {source, event_kind, event_data}
    Returns: {ok, result} where result has matches[], fired_count, policy_count.
    """
    require_api_key(x_api_key)
    if not body.event_kind:
        raise HTTPException(
            status_code=422,
            detail={"error": "event_kind is required", "code": "SIM001"},
        )
    try:
        from governance_simulator import simulate_event
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail={"error": "governance_simulator module not available", "code": "SIM002"},
        )
    try:
        result = simulate_event(body.source, body.event_kind, body.event_data)
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "code": "SIM003",
            "result": None,
        }
    return {
        "ok": True,
        "result": result.to_dict(),
    }


# __replay_api_v1__

@app.get("/v1/replay/summary")
@limiter.limit("60/minute")
async def replay_summary(request: Request, log: str = "", x_api_key: Optional[str] = Header(None)):
    """Summary of a replay log: event counts by kind, souls seen, time range, hash-chain head."""
    require_api_key(x_api_key)
    if not log:
        raise HTTPException(status_code=422, detail={"error": "log parameter required", "code": "REP003"})
    from pathlib import Path as _P
    log_path = _P(log)
    if not log_path.exists():
        raise HTTPException(status_code=404, detail={"error": f"log file not found: {log}", "code": "REP002"})
    try:
        import json as _json
        by_kind: dict[str, int] = {}
        souls: set[str] = set()
        total = 0
        first_ts: Optional[float] = None
        last_ts: Optional[float] = None
        last_hash: str = ""
        last_seq: int = -1
        with log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = _json.loads(line)
                except Exception:
                    continue
                total += 1
                k = ev.get("kind", "")
                if k:
                    by_kind[k] = by_kind.get(k, 0) + 1
                s = ev.get("soul", "")
                if s:
                    souls.add(s)
                ts = ev.get("timestamp")
                if ts is not None:
                    try:
                        ts_f = float(ts)
                        if first_ts is None or ts_f < first_ts:
                            first_ts = ts_f
                        if last_ts is None or ts_f > last_ts:
                            last_ts = ts_f
                    except Exception:
                        pass
                h = ev.get("hash", "")
                if h:
                    last_hash = h
                sq = ev.get("seq_id", -1)
                try:
                    sq_i = int(sq)
                    if sq_i > last_seq:
                        last_seq = sq_i
                except Exception:
                    pass
        return {
            "log": log,
            "total_events": total,
            "by_kind": by_kind,
            "souls": sorted(souls),
            "first_timestamp": first_ts,
            "last_timestamp": last_ts,
            "last_seq_id": last_seq if last_seq >= 0 else None,
            "last_hash": last_hash,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": f"failed to read log: {exc}", "code": "REP004"})


@app.get("/v1/replay/events")
@limiter.limit("60/minute")
async def replay_events(
    request: Request,
    log: str = "",
    kind: Optional[str] = None,
    soul: Optional[str] = None,
    since: Optional[float] = None,
    limit: int = 100,
    offset: int = 0,
    x_api_key: Optional[str] = Header(None),
):
    """Return a filtered slice of events from a replay log. Events returned as-recorded."""
    require_api_key(x_api_key)
    if not log:
        raise HTTPException(status_code=422, detail={"error": "log parameter required", "code": "REP003"})
    from pathlib import Path as _P
    log_path = _P(log)
    if not log_path.exists():
        raise HTTPException(status_code=404, detail={"error": f"log file not found: {log}", "code": "REP002"})

    try:
        import json as _json
        matched: list[dict] = []
        skipped = 0
        total_scanned = 0
        max_limit = min(max(1, int(limit)), 1000)
        max_offset = max(0, int(offset))
        with log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                total_scanned += 1
                try:
                    ev = _json.loads(line)
                except Exception:
                    continue
                if kind and ev.get("kind") != kind:
                    continue
                if soul and ev.get("soul") != soul:
                    continue
                if since is not None:
                    try:
                        if float(ev.get("timestamp", 0)) < float(since):
                            continue
                    except Exception:
                        continue
                if skipped < max_offset:
                    skipped += 1
                    continue
                matched.append(ev)
                if len(matched) >= max_limit:
                    break
        return {
            "log": log,
            "total_scanned": total_scanned,
            "returned": len(matched),
            "offset": max_offset,
            "limit": max_limit,
            "events": matched,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": f"failed to read log: {exc}", "code": "REP004"})


@app.get("/v1/replay/verify")
@limiter.limit("30/minute")
async def replay_verify(request: Request, log: str = "", x_api_key: Optional[str] = Header(None)):
    """Verify SHA256 hash chain integrity. Returns first divergence if any, else OK."""
    require_api_key(x_api_key)
    if not log:
        raise HTTPException(status_code=422, detail={"error": "log parameter required", "code": "REP003"})
    from pathlib import Path as _P
    log_path = _P(log)
    if not log_path.exists():
        raise HTTPException(status_code=404, detail={"error": f"log file not found: {log}", "code": "REP002"})

    try:
        try:
            from replay_store import EventStore
        except ImportError:
            raise HTTPException(status_code=501, detail={"error": "replay module not available", "code": "REP001"})

        store = EventStore.open(log_path, mode="replay")
        total = 0
        last_seq = -1
        last_hash = ""
        try:
            for ev in store:
                total += 1
                last_seq = getattr(ev, "seq_id", last_seq)
                last_hash = getattr(ev, "hash", last_hash)
        finally:
            try:
                store.close()
            except Exception:
                pass

        return {
            "log": log,
            "status": "ok",
            "verified_events": total,
            "last_seq_id": last_seq if last_seq >= 0 else None,
            "last_hash": last_hash,
        }
    except HTTPException:
        raise
    except Exception as exc:
        # EventStore raises on chain mismatch. Report as verification failure, not 500.
        return {
            "log": log,
            "status": "tampered",
            "error": str(exc),
            "code": "REP005",
        }


# __session65_replay_list_diff_v1__

NOUS_REPLAY_DIR: Path = Path(os.environ.get("NOUS_REPLAY_DIR", "/var/lib/nous/replays"))


def _resolve_replay_log(name: str) -> Path:
    """Resolve a replay log filename to an absolute path inside NOUS_REPLAY_DIR.

    Rejects empty name, path separators, leading dot, parent-dir traversal,
    and symlinks pointing outside the dir. Returns a regular-file Path.
    """
    if not name:
        raise HTTPException(status_code=422, detail={"error": "name required", "code": "REP003"})
    if "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(status_code=403, detail={"error": "invalid filename", "code": "REP006"})
    base = NOUS_REPLAY_DIR.resolve()
    if not base.exists():
        raise HTTPException(status_code=404, detail={"error": "replay dir not configured", "code": "REP007"})
    candidate = (base / name).resolve()
    if not candidate.is_relative_to(base):
        raise HTTPException(status_code=403, detail={"error": "path outside replay dir", "code": "REP006"})
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail={"error": f"log not found: {name}", "code": "REP002"})
    return candidate


def _tail_last_line(path: Path, tail_bytes: int = 8192) -> str:
    """Read the last non-empty line of a JSONL file in O(tail_bytes)."""
    size = path.stat().st_size
    if size == 0:
        return ""
    with path.open("rb") as fh:
        if size <= tail_bytes:
            data = fh.read()
        else:
            fh.seek(-tail_bytes, os.SEEK_END)
            data = fh.read()
    text = data.decode("utf-8", errors="replace")
    non_empty = [ln for ln in text.splitlines() if ln.strip()]
    return non_empty[-1] if non_empty else ""


class ReplayDiffRequest(BaseModel):
    """POST body for /v1/replay/diff. Filenames are resolved inside NOUS_REPLAY_DIR."""
    a: str = Field(..., description="Filename of first replay log inside NOUS_REPLAY_DIR")
    b: str = Field(..., description="Filename of second replay log inside NOUS_REPLAY_DIR")
    max_events: int = Field(default=100000, ge=1, le=10_000_000, description="Hard cap on common-prefix scan length")


@app.get("/v1/replay/list")
@limiter.limit("60/minute")
async def replay_list(request: Request, x_api_key: Optional[str] = Header(None)) -> dict[str, Any]:
    """List *.jsonl replay logs in NOUS_REPLAY_DIR with cheap last-line metadata.

    Does NOT validate hash chains (use /v1/replay/verify for that).
    Empty / missing dir returns empty list, status 200.
    """
    require_api_key(x_api_key)
    base = NOUS_REPLAY_DIR.resolve()
    if not base.exists() or not base.is_dir():
        return {"replay_dir": str(base), "logs": []}
    logs: list[dict[str, Any]] = []
    for entry in sorted(base.iterdir()):
        if entry.is_symlink():
            try:
                if not entry.resolve().is_relative_to(base):
                    continue
            except (OSError, ValueError):
                continue
        if not entry.is_file():
            continue
        if entry.suffix != ".jsonl":
            continue
        try:
            st = entry.stat()
        except OSError:
            continue
        last_line = _tail_last_line(entry)
        last_seq: Optional[int] = None
        last_hash: str = ""
        last_kind: str = ""
        if last_line:
            try:
                ev = json.loads(last_line)
                last_seq = int(ev.get("seq_id", -1))
                last_hash = str(ev.get("hash", ""))
                last_kind = str(ev.get("kind", ""))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        logs.append({
            "name": entry.name,
            "size_bytes": st.st_size,
            "mtime": st.st_mtime,
            "last_seq_id": last_seq,
            "last_hash": last_hash,
            "last_kind": last_kind,
        })
    return {"replay_dir": str(base), "logs": logs}


@app.post("/v1/replay/diff")
@limiter.limit("30/minute")
async def replay_diff(request: Request, body: ReplayDiffRequest, x_api_key: Optional[str] = Header(None)) -> dict[str, Any]:
    """Compare two replay logs in NOUS_REPLAY_DIR by (seq_id, hash) lockstep walk.

    Returned body status field:
      identical    : both exhausted, every event matched
      divergent    : first non-matching event before either exhausted
      truncated_a  : a exhausted before b
      truncated_b  : b exhausted before a
      error        : iteration raised (typically tampered hash chain)
    """
    require_api_key(x_api_key)
    path_a = _resolve_replay_log(body.a)
    path_b = _resolve_replay_log(body.b)

    try:
        from replay_store import EventStore
    except ImportError:
        raise HTTPException(status_code=501, detail={"error": "replay module not available", "code": "REP001"})

    store_a = EventStore.open(path_a, mode="replay")
    store_b = EventStore.open(path_b, mode="replay")
    iter_a = iter(store_a)
    iter_b = iter(store_b)

    common_prefix = 0
    a_total = 0
    b_total = 0
    divergence: Optional[dict[str, Any]] = None
    status = "identical"
    error: Optional[str] = None

    try:
        while True:
            try:
                ea = next(iter_a)
            except StopIteration:
                ea = None
            try:
                eb = next(iter_b)
            except StopIteration:
                eb = None

            if ea is None and eb is None:
                break
            if ea is not None:
                a_total += 1
            if eb is not None:
                b_total += 1

            if ea is None and eb is not None:
                status = "truncated_a"
                divergence = {
                    "at_seq_id": eb.seq_id,
                    "kind": "truncated",
                    "a_event": None,
                    "b_event": eb.to_dict(),
                }
                for _rest in iter_b:
                    b_total += 1
                break
            if eb is None and ea is not None:
                status = "truncated_b"
                divergence = {
                    "at_seq_id": ea.seq_id,
                    "kind": "truncated",
                    "a_event": ea.to_dict(),
                    "b_event": None,
                }
                for _rest in iter_a:
                    a_total += 1
                break

            if ea.hash == eb.hash and ea.seq_id == eb.seq_id:
                common_prefix += 1
                if common_prefix >= body.max_events:
                    break
                continue

            status = "divergent"
            divergence = {
                "at_seq_id": ea.seq_id if ea.seq_id == eb.seq_id else None,
                "kind": "hash_mismatch" if ea.seq_id == eb.seq_id else "seq_mismatch",
                "a_event": ea.to_dict(),
                "b_event": eb.to_dict(),
            }
            for _rest in iter_a:
                a_total += 1
            for _rest in iter_b:
                b_total += 1
            break
    except Exception as exc:
        status = "error"
        error = str(exc)
    finally:
        try:
            store_a.close()
        except Exception:
            pass
        try:
            store_b.close()
        except Exception:
            pass

    result: dict[str, Any] = {
        "a": body.a,
        "b": body.b,
        "status": status,
        "a_total_events": a_total,
        "b_total_events": b_total,
        "common_prefix_length": common_prefix,
        "divergence": divergence,
    }
    if error is not None:
        result["error"] = error
        result["code"] = "REP005"
    return result


# __session65_templates_save_v1__

def require_write_api_key(x_api_key: Optional[str]) -> str:
    """Strict variant of require_api_key for write endpoints.

    Differences from require_api_key:
      - If API_KEYS is empty (server not configured for writes) -> 403.
        Reads are public-safe, writes are not.
      - Missing key -> 401 (not "anonymous").
      - Invalid key -> 401 (same as existing).
    """
    if not API_KEYS:
        raise HTTPException(
            status_code=403,
            detail={"error": "write endpoints disabled (API_KEYS not configured)", "code": "AUTH002"},
        )
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail={"error": "API key required for write endpoints", "code": "AUTH003"},
        )
    if x_api_key not in API_KEYS:
        raise HTTPException(
            status_code=401,
            detail={"error": "Invalid API key", "code": "AUTH001"},
        )
    return x_api_key


def _resolve_template_path(name: str) -> Path:
    """Resolve a template name to an absolute *.nous path inside TEMPLATES_DIR.

    Rejects: empty, leading dot, non-alphanumeric chars, separators,
    paths resolving outside TEMPLATES_DIR. Returns target path
    (which may or may not exist).
    """
    import re as _re
    if not name:
        raise HTTPException(status_code=422, detail={"error": "name required", "code": "TPL003"})
    if not _re.match(r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$", name):
        raise HTTPException(
            status_code=403,
            detail={"error": "invalid template name (allowed: [A-Za-z0-9_-], 1-64 chars, no leading dot)", "code": "TPL004"},
        )
    base = TEMPLATES_DIR.resolve()
    base.mkdir(parents=True, exist_ok=True)
    candidate = (base / f"{name}.nous").resolve()
    if not candidate.is_relative_to(base):
        raise HTTPException(status_code=403, detail={"error": "path outside templates dir", "code": "TPL005"})
    return candidate


def _backup_template_if_exists(target: Path, max_keep: int = 5) -> Optional[str]:
    """If target exists, copy to <stem>.nous.bak.<ts>, prune to max_keep newest."""
    import shutil as _shutil
    if not target.exists():
        return None
    ts = time.strftime("%Y%m%dT%H%M%S") + f"_{int((time.time() * 1_000_000) % 1_000_000):06d}"
    backup = target.with_name(f"{target.stem}.nous.bak.{ts}")
    _shutil.copy2(target, backup)
    bak_pattern = f"{target.stem}.nous.bak.*"
    bak_files = sorted(target.parent.glob(bak_pattern))
    while len(bak_files) > max_keep:
        old = bak_files.pop(0)
        try:
            old.unlink()
        except OSError:
            pass
    return str(backup)


def _atomic_write_bytes(target: Path, content: bytes) -> None:
    """tempfile + fsync + os.replace. No partial writes visible to readers."""
    fd, tmppath = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmppath, target)
    except Exception:
        try:
            os.unlink(tmppath)
        except OSError:
            pass
        raise


class TemplateSaveRequest(BaseModel):
    """PUT /v1/templates/{name} body. The name lives in the path, not here."""
    source: str = Field(..., min_length=1, max_length=1_000_000, description="Full .nous source text")
    force: bool = Field(default=False, description="If true, save even when lint produces errors")


@app.put("/v1/templates/{name}")
@limiter.limit("10/minute")
async def templates_save(
    request: Request,
    name: str,
    body: TemplateSaveRequest,
    x_api_key: Optional[str] = Header(None),
) -> dict[str, Any]:
    """Save a .nous template to TEMPLATES_DIR.

    Pipeline:
      1. require_write_api_key (hard auth)
      2. _resolve_template_path (name + traversal safety)
      3. governance_lint (errors block save unless force=true)
      4. _backup_template_if_exists (rotates last 5)
      5. _atomic_write_bytes
      6. sha256 of content

    Response on success:
        {ok, name, path, bytes_written, sha256, backup?, lint?}
    Response on lint-blocked:
        {ok: false, error, code: "TPL001", lint: {...}}  (HTTP 200)
    """
    require_write_api_key(x_api_key)
    target = _resolve_template_path(name)

    lint_dict: Optional[dict[str, Any]] = None
    lint_failed = False
    try:
        from governance_lint import GovernanceLinter
        try:
            linter = GovernanceLinter()
            report = linter.lint_source(body.source, source_file=f"{name}.nous")
            lint_failed = bool(getattr(report, "has_errors", False))
            lint_dict = report.to_dict() if hasattr(report, "to_dict") else None
        except Exception as exc:
            lint_failed = True
            lint_dict = {"error": str(exc), "crashed": True}
    except ImportError:
        pass

    if lint_failed and not body.force:
        return {
            "ok": False,
            "error": "lint produced errors; pass force=true to save anyway",
            "code": "TPL001",
            "lint": lint_dict,
        }

    content = body.source.encode("utf-8")
    backup = _backup_template_if_exists(target)
    try:
        _atomic_write_bytes(target, content)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": f"write failed: {exc}", "code": "TPL002"},
        )
    sha = hashlib.sha256(content).hexdigest()

    return {
        "ok": True,
        "name": name,
        "path": str(target),
        "bytes_written": len(content),
        "sha256": sha,
        "backup": backup,
        "lint": lint_dict,
    }



# __nous_s98_stage2_endpoint_v1__
# ====================================================================
# POST /v1/verify-conformance  (public, unauthenticated, rate-limited)
#
# Convenience wrapper around conformance.verify_certificate_from_json.
# Mirrors the trust model of /v1/verify-dossier: NOT in the trust path;
# offline verification with the emitted verify_conformance_offline.py
# remains canonical. This endpoint exists so verify.html and any other
# browser-native verifier can display structured PASS/FAIL without
# requiring the user to install Python first.
# ====================================================================


class VerifyConformanceEndpointRequest(BaseModel):
    """Request body for POST /v1/verify-conformance.

    `certificate_json` is required (the artifact being verified).
    `trace_json` and `manifest_json` are optional; when absent, the
    corresponding binding checks are marked skipped (not failed) and the
    verdict can be INCONCLUSIVE rather than PASS, mirroring the lib API.
    """
    model_config = ConfigDict(strict=True, extra="forbid")
    certificate_json: str = Field(min_length=1, max_length=262144)
    trace_json: Optional[str] = Field(
        default=None, max_length=524288
    )
    manifest_json: Optional[str] = Field(
        default=None, max_length=262144
    )


@app.post("/v1/verify-conformance", response_model=None)
@limiter.limit("30/minute")
async def verify_conformance_endpoint(
    request: Request,
    body: VerifyConformanceEndpointRequest,
):
    # No require_api_key call: public by design (parity with verify-dossier).
    from conformance import verify_certificate_from_json
    try:
        result = verify_certificate_from_json(
            cert_json=body.certificate_json,
            trace_json=body.trace_json,
            manifest_json=body.manifest_json,
        )
        return result
    except Exception as exc:  # last-resort: lib promises no raise on bad input
        return JSONResponse(
            status_code=500,
            content={
                "spec_version": "verify-conformance/v1",
                "parsed": False,
                "verdict": "MALFORMED",
                "errors": [
                    f"unexpected_server_error: {type(exc).__name__}: {exc}"
                ],
            },
        )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    logger.error(f"Internal error: {traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "code": "INTERNAL001"},
    )
