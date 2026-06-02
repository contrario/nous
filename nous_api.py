"""
NOUS library constants + Pydantic request/response models.
Zero HTTP-server dependencies. Safe to import from library contexts.
# __nous_api_thin_v1__
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Optional, Literal

from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# === Version & Paths ===

# __cc_version_api_v1__
from _version import __version__ as _v
VERSION: str = _v  # __cost_cap_phase4_api_version_v1__ (version sourced from _version.py)
NOUS_DIR: Path = Path(__file__).parent
TEMPLATES_DIR: Path = NOUS_DIR / "templates"
LOG_FILE: Path = Path("/var/log/nous_api.log")
START_TIME: float = time.time()

# === API keys (loaded from NOUS_API_KEYS env var) ===

API_KEYS: set[str] = set()
_raw_keys: str = os.getenv("NOUS_API_KEYS", "")
if _raw_keys:
    API_KEYS = {k.strip() for k in _raw_keys.split(",") if k.strip()}

# __hx_env_scrub_nous_api_keys_v1__ __hx_pyc_leak_fix_v1_p3__ defense-in-depth: scrub from Python's os.environ.
# Effect: customer code calling os.getenv("NOUS_API_KEYS") receives None.
# Limitation: does NOT close /proc/self/environ surface. The kernel snapshots
# argv+envp at exec() time; Python's os.environ mutations do not propagate
# to the kernel-frozen /proc/<pid>/environ page (proc(5) behavior). Closure
# of that surface is tracked under HX-NOUS-API-PROC-ENVIRON-EXPOSURE
# (file-based secrets, re-exec with scrubbed environ, or sandbox isolation
# via HX-NOUS-API-CUSTOMER-CODE-SANDBOX).
os.environ.pop("NOUS_API_KEYS", None)

# === Logging (shared by server module) ===

try:
    _log_handler: logging.Handler = logging.FileHandler(LOG_FILE)
    _log_handler.setFormatter(logging.Formatter(
        '{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}'
    ))
    logger: logging.Logger = logging.getLogger("nous_api")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        logger.addHandler(_log_handler)
        logger.addHandler(logging.StreamHandler())
except (PermissionError, FileNotFoundError):
    # Fallback when /var/log/nous_api.log is not writable (e.g. library install)
    logger = logging.getLogger("nous_api")
    if not logger.handlers:
        logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.INFO)

# === Pydantic Request/Response Models ===

class CompileRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=100_000)

class VerifyRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=100_000)

class RunRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=100_000)
    mode: str = Field(default="dry-run", pattern="^(dry-run|execute)$")
    max_cycles: int = Field(default=3, ge=1, le=100)
    emit_trace: bool = Field(default=False)  # __s105_emit_trace_v1__
    consult_memory: bool = Field(default=False)  # __s107_u5_consult_field_v1__
    apply_remedy: bool = Field(default=False)  # __s111_u6_api_field_v1__

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

# __DIFF_SIDE_PROVENANCE_v1__
class DiffSide(BaseModel):
    """Provenance metadata for one side of a diff comparison.

    kind classifies WHERE the source came from. identifier disambiguates
    between multiple instances of the same kind. label is an optional
    display override; if absent, the renderer computes a deterministic
    string from kind + identifier.
    """
    kind: Literal[
        "template", "editor", "paste", "replay", "file", "unknown"
    ] = "unknown"
    identifier: Optional[str] = None
    label: Optional[str] = None


class DiffRequest(BaseModel):
    original: str = Field(..., description="Original .nous source code")
    modified: str = Field(..., description="Modified .nous source code")
    original_side: Optional[DiffSide] = Field(
        default=None,
        description="Provenance for original; if absent, treated as kind=unknown"
    )
    modified_side: Optional[DiffSide] = Field(
        default=None,
        description="Provenance for modified; if absent, treated as kind=unknown"
    )


# __DIFF_SIDE_RENDERER_v1__
def render_diff_side(side: Optional[DiffSide]) -> str:
    """Deterministic display string for one side of a diff.

    Server-computed so audit logs and dossier evidence stay stable across
    clients. If side is None or kind is unknown, returns "(unknown source)".
    If side.label is set, it overrides the computed string (escape hatch).
    """
    if side is None:
        return "(unknown source)"
    if side.label:
        return side.label
    kind = side.kind
    ident = side.identifier
    if kind == "template":
        if not ident:
            return "Template (unnamed)"
        return f"Template: {ident}"
    if kind == "editor":
        if not ident:
            return "Editor (current)"
        return f"Editor: {ident}"
    if kind == "paste":
        if not ident:
            return "Paste"
        return f"Paste {ident}"
    if kind == "replay":
        if not ident:
            return "Replay (unknown)"
        prefix = ident[:8] if len(ident) > 8 else ident
        return f"Replay {prefix}…"
    if kind == "file":
        if not ident:
            return "File (unnamed)"
        from pathlib import Path as _P
        return f"File: {_P(ident).name}"
    return "(unknown source)"

class ErrorResponse(BaseModel):
    error: str
    code: str


# === Backward-compat shim ===
# Allows `uvicorn nous_api:app` and `from nous_api import app` to keep working
# when HTTP server extras are installed. Silently no-ops otherwise.
try:
    from nous_api_server import app  # noqa: F401
    _HTTP_SERVER_AVAILABLE: bool = True
except ImportError:
    _HTTP_SERVER_AVAILABLE = False
