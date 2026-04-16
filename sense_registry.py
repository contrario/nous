"""
sense_registry.py — Scoped custom sense registry (Senses v2).

Each compiled world has its own SenseRegistry. Builtin senses are global
and act as a fallback when a requested sense is not world-scoped.

Usage:
    from sense_registry import SenseRegistry

    reg = SenseRegistry.from_program(program)
    result = await reg.invoke("stock_price", {"symbol": "BTCUSDT"})

Security:
  - Env var substitution only with ${VAR_NAME} syntax
  - Only vars in ALLOWED_ENV_VARS are substituted (others → empty string)
  - Shell transport disabled unless NOUS_SENSE_SHELL_ENABLED=1
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger("nous.sense_registry")

_ENV_VAR_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")
_TEMPLATE_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

ALLOWED_ENV_VARS: frozenset[str] = frozenset({
    "BINANCE_API_KEY",
    "OPENROUTER_API_KEY",
    "DEEPSEEK_API_KEY",
    "ANTHROPIC_API_KEY",
    "NOUS_API_KEYS",
    "TELEGRAM_BOT_TOKEN",
    "SLACK_BOT_TOKEN",
    "SENSE_AUTH_TOKEN",
})

SHELL_ENABLED: bool = os.environ.get("NOUS_SENSE_SHELL_ENABLED", "0") == "1"


class SenseError(Exception):
    """Raised when a sense invocation fails validation or execution."""


class _CachedResult:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, expires_at: float) -> None:
        self.value = value
        self.expires_at = expires_at


class SenseDef:
    """Compiled custom sense definition."""

    __slots__ = (
        "name",
        "description",
        "http_get",
        "http_post",
        "shell",
        "method",
        "timeout",
        "headers",
        "body_template",
        "returns",
        "cache_ttl",
    )

    def __init__(
        self,
        name: str,
        description: Optional[str] = None,
        http_get: Optional[str] = None,
        http_post: Optional[str] = None,
        shell: Optional[str] = None,
        method: Optional[str] = None,
        timeout: int = 10,
        headers: Optional[dict[str, Any]] = None,
        body_template: Optional[str] = None,
        returns: str = "string",
        cache_ttl: int = 0,
    ) -> None:
        self.name = name
        self.description = description
        self.http_get = http_get
        self.http_post = http_post
        self.shell = shell
        self.method = method
        self.timeout = timeout
        self.headers = headers or {}
        self.body_template = body_template
        self.returns = returns
        self.cache_ttl = cache_ttl

    @property
    def transport(self) -> str:
        if self.http_get is not None:
            return "http_get"
        if self.http_post is not None:
            return "http_post"
        if self.shell is not None:
            return "shell"
        raise SenseError(f"sense {self.name} has no transport")


def _substitute_env(text: str) -> str:
    def _replace(m: re.Match[str]) -> str:
        var = m.group(1)
        if var not in ALLOWED_ENV_VARS:
            logger.warning("sense: env var %s not in allowlist", var)
            return ""
        return os.environ.get(var, "")
    return _ENV_VAR_RE.sub(_replace, text)


def _substitute_args(text: str, args: dict[str, Any]) -> str:
    def _replace(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in args:
            return ""
        return str(args[key])
    return _TEMPLATE_RE.sub(_replace, text)


def _render(text: str, args: dict[str, Any]) -> str:
    return _substitute_args(_substitute_env(text), args)


class SenseRegistry:
    """Per-world registry of custom senses + builtin dispatch."""

    def __init__(self) -> None:
        self._senses: dict[str, SenseDef] = {}
        self._cache: dict[str, _CachedResult] = {}
        self._telemetry_engine: Optional[Any] = None
        self._telemetry_soul: str = "unknown"

    @classmethod
    def from_program(cls, program: Any) -> "SenseRegistry":
        reg = cls()
        for node in getattr(program, "custom_senses", []):
            reg.register(
                SenseDef(
                    name=node.name,
                    description=node.description,
                    http_get=node.http_get,
                    http_post=node.http_post,
                    shell=node.shell,
                    method=node.method,
                    timeout=node.timeout,
                    headers=dict(node.headers) if node.headers else {},
                    body_template=node.body_template,
                    returns=node.returns,
                    cache_ttl=node.cache_ttl,
                )
            )
        return reg

    def register(self, sense: SenseDef) -> None:
        if sense.name in self._senses:
            raise SenseError(f"duplicate custom sense: {sense.name}")
        self._senses[sense.name] = sense

    def set_telemetry(self, engine: Any, soul_name: str = "unknown") -> None:
        self._telemetry_engine = engine
        self._telemetry_soul = soul_name

    def has(self, name: str) -> bool:
        return name in self._senses

    def names(self) -> list[str]:
        return sorted(self._senses.keys())

    def get(self, name: str) -> Optional[SenseDef]:
        return self._senses.get(name)

    async def invoke(self, name: str, args: dict[str, Any]) -> Any:
        sense = self._senses.get(name)
        if sense is None:
            raise SenseError(f"unknown custom sense: {name}")

        cache_key: Optional[str] = None
        if sense.cache_ttl > 0:
            cache_key = f"{name}::{sorted(args.items())}"
            hit = self._cache.get(cache_key)
            if hit and hit.expires_at > time.time():
                logger.debug("sense cache hit: %s", name)
                return hit.value

        start = time.time()
        _span = None
        if self._telemetry_engine is not None:
            try:
                from telemetry_engine import SpanKind
                _span = self._telemetry_engine.start_span(
                    SpanKind.SENSE,
                    self._telemetry_soul,
                    sense_name=name,
                    transport=sense.transport,
                    custom=True,
                )
            except Exception:
                _span = None
        try:
            if sense.http_get is not None:
                result = await self._invoke_http(sense, args, method="GET")
            elif sense.http_post is not None:
                result = await self._invoke_http(sense, args, method="POST")
            elif sense.shell is not None:
                result = await self._invoke_shell(sense, args)
            else:
                raise SenseError(f"sense {name} has no transport")
        except SenseError as _se:
            if _span is not None and self._telemetry_engine is not None:
                try:
                    from telemetry_engine import SpanStatus
                    _span.finish(SpanStatus.ERROR, error=str(_se))
                    await self._telemetry_engine.record(_span)
                except Exception:
                    pass
            raise
        except Exception as exc:
            elapsed_ms = (time.time() - start) * 1000
            logger.error(
                "sense_invoke_failed name=%s elapsed_ms=%.1f error=%s",
                name, elapsed_ms, exc,
            )
            if _span is not None and self._telemetry_engine is not None:
                try:
                    from telemetry_engine import SpanStatus
                    _span.finish(SpanStatus.ERROR, error=str(exc))
                    await self._telemetry_engine.record(_span)
                except Exception:
                    pass
            raise SenseError(f"sense {name} execution failed: {exc}") from exc

        elapsed_ms = (time.time() - start) * 1000
        logger.info(
            "sense_invoke_ok name=%s transport=%s elapsed_ms=%.1f",
            name, sense.transport, elapsed_ms,
        )
        if _span is not None and self._telemetry_engine is not None:
            try:
                from telemetry_engine import SpanStatus
                _span.finish(SpanStatus.OK, elapsed_ms=elapsed_ms)
                await self._telemetry_engine.record(_span)
            except Exception:
                pass

        if cache_key is not None:
            self._cache[cache_key] = _CachedResult(
                value=result,
                expires_at=time.time() + sense.cache_ttl,
            )
        return result

    async def _invoke_http(
        self, sense: SenseDef, args: dict[str, Any], method: str,
    ) -> Any:
        url_tpl = sense.http_get if method == "GET" else sense.http_post
        assert url_tpl is not None
        url = _render(url_tpl, args)

        headers: dict[str, str] = {}
        for k, v in sense.headers.items():
            headers[str(k)] = _render(str(v), args)

        body: Any = None
        if method == "POST" and sense.body_template:
            body = _render(sense.body_template, args)

        timeout = httpx.Timeout(
            connect=min(sense.timeout, 5),
            read=sense.timeout,
            write=5,
            pool=5,
        )
        async with httpx.AsyncClient(timeout=timeout) as client:
            if method == "GET":
                resp = await client.get(url, headers=headers or None)
            else:
                if body is not None and "Content-Type" not in headers:
                    headers["Content-Type"] = "application/json"
                resp = await client.post(url, headers=headers or None, content=body)
        resp.raise_for_status()

        if sense.returns == "json":
            return resp.json()
        if sense.returns == "int":
            return int(resp.text.strip())
        if sense.returns == "float":
            return float(resp.text.strip())
        if sense.returns == "bool":
            return resp.text.strip().lower() in ("true", "1", "yes")
        return resp.text

    async def _invoke_shell(
        self, sense: SenseDef, args: dict[str, Any],
    ) -> str:
        if not SHELL_ENABLED:
            raise SenseError(
                f"shell sense '{sense.name}' disabled. "
                "Set NOUS_SENSE_SHELL_ENABLED=1 to enable."
            )
        assert sense.shell is not None
        cmd_str = _render(sense.shell, args)
        argv = shlex.split(cmd_str)
        if not argv:
            raise SenseError(f"empty shell command for sense {sense.name}")

        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=sense.timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise SenseError(f"shell sense {sense.name} timeout after {sense.timeout}s")

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            raise SenseError(
                f"shell sense {sense.name} exit {proc.returncode}: {err[:200]}"
            )
        return stdout.decode("utf-8", errors="replace")


_GLOBAL_REGISTRIES: dict[str, SenseRegistry] = {}


def register_world(world_name: str, program: Any) -> SenseRegistry:
    reg = SenseRegistry.from_program(program)
    _GLOBAL_REGISTRIES[world_name] = reg
    logger.info(
        "sense_registry_loaded world=%s senses=%s",
        world_name, reg.names(),
    )
    return reg


def get_world(world_name: str) -> Optional[SenseRegistry]:
    return _GLOBAL_REGISTRIES.get(world_name)


def clear_all() -> None:
    _GLOBAL_REGISTRIES.clear()
