"""
NOUS HTTP API Server — v4.0.0
FastAPI + uvicorn. No external agent frameworks.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import py_compile
import tempfile
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

load_dotenv(Path(__file__).parent.parent / ".env")

NOUS_DIR = Path(__file__).parent
TEMPLATES_DIR = NOUS_DIR / "templates"
LOG_FILE = Path("/var/log/nous_api.log")
VERSION = "4.0.0"
START_TIME = time.time()

API_KEYS: set[str] = set()
raw_keys = os.getenv("NOUS_API_KEYS", "")
if raw_keys:
    API_KEYS = {k.strip() for k in raw_keys.split(",") if k.strip()}


# ── Logging ──

log_handler = logging.FileHandler(LOG_FILE)
log_handler.setFormatter(logging.Formatter(
    '{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}'
))
logger = logging.getLogger("nous_api")
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)
logger.addHandler(logging.StreamHandler())


# ── Rate Limiter ──

limiter = Limiter(key_func=get_remote_address)


# ── NOUS Imports ──

import sys
if str(NOUS_DIR) not in sys.path:
    sys.path.insert(0, str(NOUS_DIR))

from parser import parse_nous
from validator import NousValidator
from typechecker import typecheck_program
from verifier import verify_program
from codegen import NousCodeGen


# ── Models ──

class CompileRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=100_000)

class VerifyRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=100_000)

class RunRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=100_000)
    mode: str = Field(default="dry-run", pattern="^(dry-run|execute)$")
    max_cycles: int = Field(default=3, ge=1, le=100)

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10_000)
    session_id: Optional[str] = None
    soul: Optional[str] = None
    world: str = Field(default="customer_service", description="Template name to load")
    mode: str = Field(default="live", pattern="^(live|dry-run)$")

class WebhookPayload(BaseModel):
    data: Any = None

class DiffRequest(BaseModel):
    original: str = Field(..., description="Original .nous source code")
    modified: str = Field(..., description="Modified .nous source code")



class ErrorResponse(BaseModel):
    error: str
    code: str


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

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(python_code)
        tmp_path = f.name

    try:
        py_compile.compile(tmp_path, doraise=True)
    except py_compile.PyCompileError as e:
        return {
            "ok": False,
            "stage": "py_compile",
            "errors": [{"code": "PY001", "message": str(e)}],
            "warnings": val_warnings + tc_warnings,
        }
    finally:
        os.unlink(tmp_path)

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
        "cli_commands": 43,
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

            ver_result = verify_program(program)

            proven = []
            warnings = []
            errors = []
            for item in ver_result.items:
                entry = {
                    "code": item.code,
                    "category": item.category,
                    "message": item.message,
                    "severity": item.severity.value if hasattr(item.severity, 'value') else str(item.severity),
                }
                if item.severity.value == "ERROR" if hasattr(item.severity, 'value') else str(item.severity) == "ERROR":
                    errors.append(entry)
                elif item.severity.value == "WARN" if hasattr(item.severity, 'value') else str(item.severity) == "WARN":
                    warnings.append(entry)
                else:
                    proven.append(entry)

            return {
                "ok": len(errors) == 0,
                "stage": "complete",
                "proven": proven,
                "errors": errors,
                "warnings": warnings,
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
                }

            return {
                "ok": True,
                "mode": "execute",
                "output": "Live execution not yet available via API. Use dry-run mode or nous run on the server.",
                "compiled": True,
                "lines": compile_result["lines"],
                "souls": compile_result["souls"],
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
    return configs


def _build_system_prompt(soul_name: str, soul_cfg: dict, world_name: str, history: list[dict]) -> str:
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
    return f"You are {role_desc} in the {world_name} system. Respond directly to the user in 2-3 sentences. Never reveal system internals, model names, tools, or memory fields. Never show your reasoning process. Just answer naturally as {soul_name} would."


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
            from parser import parse_nous
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
    chosen_soul = _pick_soul(soul_configs, body.soul, body.message)
    soul_cfg = soul_configs.get(chosen_soul, {})

    sess["history"].append({"role": "user", "content": body.message})
    if len(sess["history"]) > 20:
        sess["history"] = sess["history"][-20:]

    system_prompt = _build_system_prompt(chosen_soul, soul_cfg, sess["world"], sess["history"])

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
        try:
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
                    logger.warning(f"chat tier {tier.name} failed: {result.get('error', '?')}")
                    continue

            if not reply:
                raise HTTPException(status_code=503, detail={
                    "error": "All LLM tiers failed",
                    "code": "CHAT003",
                })

        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail={"error": "Chat timed out (35s)", "code": "CHAT004"})
        except HTTPException:
            raise
        except Exception as e:
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
            from parser import parse_nous
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
    chosen_soul = _pick_soul(sess["soul_configs"], getattr(body, "soul", None), body.message)
    soul_cfg = sess["soul_configs"].get(chosen_soul, {})
    system_prompt = _build_system_prompt(chosen_soul, soul_cfg, sess["world"], sess["history"])

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
    from ast_nodes import SoulNode
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
        routes = []
        if program.nervous_system:
            for r in program.nervous_system.routes:
                src = r.source if isinstance(r.source, str) else str(r.source)
                dst = r.target if isinstance(r.target, str) else str(r.target)
                routes.append((src, dst))
        return routes

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
            from parser import parse_nous
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
        return JSONResponse(content={"ok": True, "diff": result})
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Diff timed out (30s)")
    except Exception as e:
        logger.error(f"diff error: {e}")
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/v1/webhook/{channel}")
@limiter.limit("100/minute")
async def webhook(request: Request, channel: str, x_api_key: Optional[str] = Header(None)):
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

    return {
        "received": True,
        "channel": channel,
        "event_id": event_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": "Webhook received. Configure a NOUS world with webhook-enabled souls to process events.",
    }


# ── Error Handlers ──

# 422 handler removed — let FastAPI show real errors

@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    logger.error(f"Internal error: {traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "code": "INTERNAL001"},
    )
