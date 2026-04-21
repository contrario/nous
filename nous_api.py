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
from typing import Any, Optional

from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# === Version & Paths ===

VERSION: str = "4.11.1"
NOUS_DIR: Path = Path(__file__).parent
TEMPLATES_DIR: Path = NOUS_DIR / "templates"
LOG_FILE: Path = Path("/var/log/nous_api.log")
START_TIME: float = time.time()

# === API keys (loaded from NOUS_API_KEYS env var) ===

API_KEYS: set[str] = set()
_raw_keys: str = os.getenv("NOUS_API_KEYS", "")
if _raw_keys:
    API_KEYS = {k.strip() for k in _raw_keys.split(",") if k.strip()}

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


# === Backward-compat shim ===
# Allows `uvicorn nous_api:app` and `from nous_api import app` to keep working
# when HTTP server extras are installed. Silently no-ops otherwise.
try:
    from nous_api_server import app  # noqa: F401
    _HTTP_SERVER_AVAILABLE: bool = True
except ImportError:
    _HTTP_SERVER_AVAILABLE = False
