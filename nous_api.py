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
VERSION = "4.10.0"
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
from sense_registry import register_world as _register_sense_world
from mood_engine import MoodEngine, build_from_ast as _build_mood_from_ast
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
    # __api_chat_request_replay_v1__
    replay_mode: str = Field(default="off", pattern="^(off|record|replay)$")
    replay_log: Optional[str] = Field(default=None, max_length=1024)
    replay_seed_base: int = Field(default=0, ge=0)

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
        _msg_lower = body.message.lower() if hasattr(body, "message") else (message.lower() if "message" in dir() else "")
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
    chosen_soul = await _route_soul(sess["soul_configs"], getattr(body, "soul", None), body.message)
    soul_cfg = sess["soul_configs"].get(chosen_soul, {})
    _sb_ctx = ""
    if _has_superbrain_sense(soul_cfg):
        _sb_ctx = await _superbrain_search(body.message)
    _mood_engine = _get_or_create_mood(sess, chosen_soul)
    _mood_hint = _mood_engine.describe() if _mood_engine else ""
    if _mood_engine is not None:
        _msg_lower = body.message.lower() if hasattr(body, "message") else (message.lower() if "message" in dir() else "")
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
            from parser import parse_nous
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
        _msg_lower = body.message.lower() if hasattr(body, "message") else (message.lower() if "message" in dir() else "")
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


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    logger.error(f"Internal error: {traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "code": "INTERNAL001"},
    )
