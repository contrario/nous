"""
NOUS Immune Engine — Ανοσία (Anosia)
======================================
Adaptive error recovery with antibody generation.
When a soul encounters an unhandled error:
1. Captures error trace
2. Uses soul's mind (LLM) to generate a dynamic fallback
3. Caches the antibody
4. Broadcasts to all clones — they become immune instantly
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

log = logging.getLogger("nous.immune")


@dataclass
class Antibody:
    signature: str
    error_type: str
    error_message: str
    soul_name: str
    fallback_code: str
    fallback_fn: Optional[Callable[..., Coroutine[Any, Any, Any]]] = None
    created_at: float = 0.0
    expires_at: float = 0.0
    success_count: int = 0
    fail_count: int = 0
    source: str = "self"

    @property
    def is_expired(self) -> bool:
        if self.expires_at <= 0:
            return False
        return time.time() > self.expires_at

    @property
    def is_effective(self) -> bool:
        total = self.success_count + self.fail_count
        if total == 0:
            return True
        return self.success_count / total > 0.5


def _error_signature(error_type: str, error_msg: str) -> str:
    normalized = error_type.lower() + ":" + error_msg.lower()[:200]
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


@dataclass
class ImmuneConfig:
    adaptive_recovery: bool = True
    share_with_clones: bool = True
    antibody_lifespan_seconds: float = 3600.0
    max_antibodies: int = 50
    llm_generation: bool = True


@dataclass
class ImmuneMetrics:
    total_infections: int = 0
    total_antibodies_generated: int = 0
    total_antibodies_shared: int = 0
    total_recoveries: int = 0
    total_rejections: int = 0
    antibodies_expired: int = 0


class AntibodyCache:
    """Per-soul antibody cache with expiration and effectiveness tracking."""

    def __init__(self, max_size: int = 50) -> None:
        self._cache: dict[str, Antibody] = {}
        self._max_size = max_size

    def get(self, error_type: str, error_msg: str) -> Optional[Antibody]:
        sig = _error_signature(error_type, error_msg)
        ab = self._cache.get(sig)
        if ab is None:
            return None
        if ab.is_expired:
            del self._cache[sig]
            return None
        if not ab.is_effective:
            del self._cache[sig]
            return None
        return ab

    def put(self, antibody: Antibody) -> None:
        if len(self._cache) >= self._max_size:
            self._evict_oldest()
        self._cache[antibody.signature] = antibody

    def has(self, signature: str) -> bool:
        ab = self._cache.get(signature)
        if ab is None:
            return False
        if ab.is_expired:
            del self._cache[signature]
            return False
        return True

    def record_success(self, signature: str) -> None:
        ab = self._cache.get(signature)
        if ab:
            ab.success_count += 1

    def record_failure(self, signature: str) -> None:
        ab = self._cache.get(signature)
        if ab:
            ab.fail_count += 1

    def all_antibodies(self) -> list[Antibody]:
        now = time.time()
        expired = [k for k, v in self._cache.items() if v.is_expired]
        for k in expired:
            del self._cache[k]
        return list(self._cache.values())

    def purge_expired(self) -> int:
        expired = [k for k, v in self._cache.items() if v.is_expired]
        for k in expired:
            del self._cache[k]
        return len(expired)

    def _evict_oldest(self) -> None:
        if not self._cache:
            return
        oldest_key = min(self._cache, key=lambda k: self._cache[k].created_at)
        del self._cache[oldest_key]

    @property
    def size(self) -> int:
        return len(self._cache)


class ImmuneEngine:
    """Manages adaptive error recovery across all souls and their clones."""

    def __init__(
        self,
        runtime: Any,
        llm_caller: Optional[Callable[..., Coroutine[Any, Any, str]]] = None,
        purge_interval: float = 300.0,
    ) -> None:
        self._runtime = runtime
        self._llm_caller = llm_caller
        self._purge_interval = purge_interval
        self._configs: dict[str, ImmuneConfig] = {}
        self._caches: dict[str, AntibodyCache] = {}
        self._metrics: dict[str, ImmuneMetrics] = {}
        self._clone_groups: dict[str, set[str]] = {}
        self._alive = True
        if self._llm_caller is None:
            self._llm_caller = self._default_llm_caller


    async def _default_llm_caller(self, soul_name: str, prompt: str) -> str:
        import os
        providers = [
            ("DEEPSEEK_API_KEY", "https://api.deepseek.com/v1/chat/completions", "deepseek-chat"),
            ("MISTRAL_API_KEY", "https://api.mistral.ai/v1/chat/completions", "mistral-small-latest"),
            ("ANTHROPIC_API_KEY", "https://api.anthropic.com/v1/messages", "claude-3-haiku-20240307"),
        ]
        for env_key, base_url, model in providers:
            api_key = os.environ.get(env_key)
            if not api_key:
                continue
            try:
                import httpx
                if "anthropic" in base_url:
                    headers = {"x-api-key": api_key, "content-type": "application/json", "anthropic-version": "2023-06-01"}
                    payload = {"model": model, "max_tokens": 300, "messages": [{"role": "user", "content": prompt}]}
                else:
                    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                    payload = {"model": model, "max_tokens": 300, "messages": [{"role": "user", "content": prompt}]}
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(base_url, json=payload, headers=headers)
                    data = resp.json()
                    if "anthropic" in base_url:
                        return data["content"][0]["text"]
                    else:
                        return data["choices"][0]["message"]["content"]
            except Exception as e:
                log.warning(f"Immune LLM call failed ({env_key}): {e}")
                continue
        return ""

    def register(
        self,
        soul_name: str,
        config: ImmuneConfig,
        parent_name: Optional[str] = None,
    ) -> None:
        self._configs[soul_name] = config
        self._caches[soul_name] = AntibodyCache(max_size=config.max_antibodies)
        self._metrics[soul_name] = ImmuneMetrics()

        if parent_name:
            group = self._clone_groups.setdefault(parent_name, {parent_name})
            group.add(soul_name)
            parent_cache = self._caches.get(parent_name)
            if parent_cache and config.share_with_clones:
                for ab in parent_cache.all_antibodies():
                    clone_ab = Antibody(
                        signature=ab.signature,
                        error_type=ab.error_type,
                        error_message=ab.error_message,
                        soul_name=soul_name,
                        fallback_code=ab.fallback_code,
                        fallback_fn=ab.fallback_fn,
                        created_at=ab.created_at,
                        expires_at=ab.expires_at,
                        source=f"inherited:{ab.soul_name}",
                    )
                    self._caches[soul_name].put(clone_ab)
                log.info(
                    f"Immune: {soul_name} inherited "
                    f"{parent_cache.size} antibodies from {parent_name}"
                )

        log.info(
            f"Immune registered: {soul_name} "
            f"(adaptive={config.adaptive_recovery}, "
            f"share={config.share_with_clones}, "
            f"lifespan={config.antibody_lifespan_seconds}s)"
        )

    async def handle_error(
        self,
        soul_name: str,
        error: Exception,
        context: Optional[dict[str, Any]] = None,
    ) -> tuple[bool, Optional[Any]]:
        config = self._configs.get(soul_name)
        if not config or not config.adaptive_recovery:
            return False, None

        metrics = self._metrics[soul_name]
        metrics.total_infections += 1

        error_type = type(error).__name__
        error_msg = str(error)
        cache = self._caches[soul_name]

        existing = cache.get(error_type, error_msg)
        if existing:
            log.info(
                f"Immune [{soul_name}]: antibody found for "
                f"{error_type}, attempting recovery"
            )
            recovered, result = await self._apply_antibody(
                soul_name, existing, error, context
            )
            if recovered:
                cache.record_success(existing.signature)
                metrics.total_recoveries += 1
                return True, result
            else:
                cache.record_failure(existing.signature)
                log.warning(
                    f"Immune [{soul_name}]: cached antibody failed for {error_type}"
                )

        builtin = await self._try_builtin_antibody(soul_name, error, context, config)
        if builtin:
            recovered, result = await self._apply_antibody(soul_name, builtin, error, context)
            if recovered:
                cache.put(builtin)
                cache.record_success(builtin.signature)
                metrics.total_antibodies_generated += 1
                metrics.total_recoveries += 1
                if config.share_with_clones:
                    await self._broadcast_antibody(soul_name, builtin)
                log.info(
                    f"═══ BUILTIN ANTIBODY APPLIED: {soul_name} ═══\n"
                    f"  Error: {error_type}: {error_msg[:100]}\n"
                    f"  Signature: {builtin.signature}\n"
                    f"  ═══ IMMUNE RESPONSE COMPLETE ═══"
                )
                return True, result

        if config.llm_generation and self._llm_caller:
            antibody = await self._generate_antibody(
                soul_name, error, context, config
            )
            if antibody:
                recovered, result = await self._apply_antibody(
                    soul_name, antibody, error, context
                )
                if recovered:
                    cache.put(antibody)
                    cache.record_success(antibody.signature)
                    metrics.total_antibodies_generated += 1
                    metrics.total_recoveries += 1

                    if config.share_with_clones:
                        await self._broadcast_antibody(soul_name, antibody)

                    log.info(
                        f"═══ ANTIBODY GENERATED: {soul_name} ═══\n"
                        f"  Error: {error_type}: {error_msg[:100]}\n"
                        f"  Signature: {antibody.signature}\n"
                        f"  Shared: {config.share_with_clones}\n"
                        f"  ═══ IMMUNE RESPONSE COMPLETE ═══"
                    )
                    return True, result
                else:
                    metrics.total_rejections += 1
                    log.warning(
                        f"Immune [{soul_name}]: generated antibody "
                        f"failed validation for {error_type}"
                    )

        return False, None


    async def _try_builtin_antibody(
        self,
        soul_name: str,
        error: Exception,
        context: Optional[dict[str, Any]],
        config: ImmuneConfig,
    ) -> Optional[Antibody]:
        error_type = type(error).__name__
        error_msg = str(error).lower()
        sig = _error_signature(error_type, str(error))
        now = time.time()
        lifespan = config.antibody_lifespan_seconds

        fallback_code = None

        if any(k in error_msg for k in ["no address", "name resolution", "dns", "getaddrinfo"]):
            fallback_code = """async def fallback(error, context):
    return {"status": "dns_error", "data": None, "recovered": True, "message": "DNS resolution failed, returning safe default"}"""

        elif any(k in error_msg for k in ["timed out", "timeout", "read timeout"]):
            fallback_code = """async def fallback(error, context):
    return {"status": "timeout", "data": None, "recovered": True, "message": "Request timed out, returning safe default"}"""

        elif any(k in error_msg for k in ["connection refused", "connect error", "connection reset"]):
            fallback_code = """async def fallback(error, context):
    return {"status": "connection_error", "data": None, "recovered": True, "message": "Connection failed, returning safe default"}"""

        elif any(k in error_msg for k in ["rate limit", "429", "too many requests"]):
            fallback_code = """async def fallback(error, context):
    import asyncio
    await asyncio.sleep(2)
    return {"status": "rate_limited", "data": None, "recovered": True, "message": "Rate limited, backed off"}"""

        elif any(k in error_msg for k in ["401", "403", "unauthorized", "forbidden"]):
            fallback_code = """async def fallback(error, context):
    return {"status": "auth_error", "data": None, "recovered": True, "message": "Auth failed, returning safe default"}"""

        elif any(k in error_msg for k in ["500", "502", "503", "504", "server error", "internal server"]):
            fallback_code = """async def fallback(error, context):
    return {"status": "server_error", "data": None, "recovered": True, "message": "Server error, returning safe default"}"""

        elif any(k in error_msg for k in ["json", "decode", "parsing", "invalid"]):
            fallback_code = """async def fallback(error, context):
    return {"status": "parse_error", "data": None, "recovered": True, "message": "Parse error, returning safe default"}"""

        if not fallback_code:
            return None

        try:
            fallback_fn = self._compile_fallback(fallback_code, soul_name)
        except Exception:
            return None

        return Antibody(
            signature=sig,
            error_type=error_type,
            error_message=str(error)[:500],
            soul_name=soul_name,
            fallback_code=fallback_code,
            fallback_fn=fallback_fn,
            created_at=now,
            expires_at=now + lifespan if lifespan > 0 else 0,
            source="builtin",
        )

    async def _generate_antibody(
        self,
        soul_name: str,
        error: Exception,
        context: Optional[dict[str, Any]],
        config: ImmuneConfig,
    ) -> Optional[Antibody]:
        if not self._llm_caller:
            return None

        error_type = type(error).__name__
        error_msg = str(error)
        sig = _error_signature(error_type, error_msg)

        prompt = self._build_antibody_prompt(
            soul_name, error_type, error_msg, context
        )

        try:
            fallback_code = await self._llm_caller(
                soul_name=soul_name,
                prompt=prompt,
            )
        except Exception as e:
            log.error(f"Immune [{soul_name}]: LLM antibody generation failed: {e}")
            return None

        if not fallback_code or len(fallback_code.strip()) < 10:
            return None

        fallback_code = self._sanitize_code(fallback_code)

        try:
            fallback_fn = self._compile_fallback(fallback_code, soul_name)
        except Exception as e:
            log.warning(
                f"Immune [{soul_name}]: antibody compilation failed: {e}"
            )
            return None

        now = time.time()
        lifespan = config.antibody_lifespan_seconds

        return Antibody(
            signature=sig,
            error_type=error_type,
            error_message=error_msg[:500],
            soul_name=soul_name,
            fallback_code=fallback_code,
            fallback_fn=fallback_fn,
            created_at=now,
            expires_at=now + lifespan if lifespan > 0 else 0,
            source="generated",
        )

    def _build_antibody_prompt(
        self,
        soul_name: str,
        error_type: str,
        error_msg: str,
        context: Optional[dict[str, Any]],
    ) -> str:
        ctx_str = ""
        if context:
            safe_ctx = {
                k: str(v)[:200] for k, v in context.items()
                if k in ("tool_name", "args", "last_input", "cycle_count")
            }
            ctx_str = f"\nContext: {safe_ctx}"

        return (
            f"You are a NOUS soul error recovery system.\n"
            f"Soul '{soul_name}' encountered an error.\n"
            f"Error type: {error_type}\n"
            f"Error message: {error_msg[:300]}\n"
            f"{ctx_str}\n\n"
            f"Generate a Python async function that handles this error.\n"
            f"The function signature must be:\n"
            f"  async def fallback(error, context):\n"
            f"It must return a safe default value or None.\n"
            f"Do NOT import anything. Do NOT use eval/exec.\n"
            f"Keep it under 20 lines. Only output the function body.\n"
            f"Example:\n"
            f"  async def fallback(error, context):\n"
            f'      return {{"status": "recovered", "data": None}}\n'
        )

    def _sanitize_code(self, code: str) -> str:
        lines = code.strip().split("\n")
        clean: list[str] = []
        for line in lines:
            stripped = line.strip().lower()
            if any(
                banned in stripped
                for banned in [
                    "import ", "__import__", "eval(", "exec(",
                    "compile(", "open(", "os.", "sys.",
                    "subprocess", "shutil", "__builtins__",
                ]
            ):
                continue
            clean.append(line)
        return "\n".join(clean)

    def _compile_fallback(
        self,
        code: str,
        soul_name: str,
    ) -> Callable[..., Coroutine[Any, Any, Any]]:
        if not code.strip().startswith("async def fallback"):
            code = "async def fallback(error, context):\n" + "\n".join(
                "    " + line for line in code.strip().split("\n")
            )

        local_ns: dict[str, Any] = {}
        restricted_globals: dict[str, Any] = {
            "__builtins__": {
                "str": str, "int": int, "float": float, "bool": bool,
                "dict": dict, "list": list, "tuple": tuple, "set": set,
                "len": len, "max": max, "min": min, "abs": abs,
                "isinstance": isinstance, "type": type,
                "None": None, "True": True, "False": False,
                "Exception": Exception, "ValueError": ValueError,
                "TypeError": TypeError, "KeyError": KeyError,
                "AttributeError": AttributeError, "IndexError": IndexError,
                "RuntimeError": RuntimeError, "ZeroDivisionError": ZeroDivisionError,
                "FileNotFoundError": FileNotFoundError, "IOError": IOError,
                "ConnectionError": ConnectionError, "TimeoutError": TimeoutError,
                "StopIteration": StopIteration, "OSError": OSError,
                "json": __import__("json"),
                "re": __import__("re"),
                "str": str, "repr": repr, "print": print, "sorted": sorted,
                "hasattr": hasattr, "getattr": getattr, "setattr": setattr,
                "range": range, "enumerate": enumerate,
            },
            "asyncio": asyncio,
        }

        exec(code, restricted_globals, local_ns)

        fn = local_ns.get("fallback")
        if fn is None or not asyncio.iscoroutinefunction(fn):
            raise ValueError(f"Compiled code for {soul_name} did not produce async fallback")

        return fn

    async def _apply_antibody(
        self,
        soul_name: str,
        antibody: Antibody,
        error: Exception,
        context: Optional[dict[str, Any]],
    ) -> tuple[bool, Optional[Any]]:
        if not antibody.fallback_fn:
            return False, None
        try:
            result = await asyncio.wait_for(
                antibody.fallback_fn(error, context or {}),
                timeout=5.0,
            )
            return True, result
        except asyncio.TimeoutError:
            log.warning(
                f"Immune [{soul_name}]: antibody timed out "
                f"(sig={antibody.signature})"
            )
            return False, None
        except Exception as e:
            log.warning(
                f"Immune [{soul_name}]: antibody raised "
                f"{type(e).__name__}: {e}"
            )
            return False, None

    async def _broadcast_antibody(
        self,
        source_soul: str,
        antibody: Antibody,
    ) -> None:
        parent = source_soul
        for group_parent, members in self._clone_groups.items():
            if source_soul in members:
                parent = group_parent
                break

        group = self._clone_groups.get(parent, {parent})
        shared_count = 0

        for member in group:
            if member == source_soul:
                continue
            cache = self._caches.get(member)
            config = self._configs.get(member)
            if not cache or not config or not config.share_with_clones:
                continue

            if cache.has(antibody.signature):
                continue

            clone_ab = Antibody(
                signature=antibody.signature,
                error_type=antibody.error_type,
                error_message=antibody.error_message,
                soul_name=member,
                fallback_code=antibody.fallback_code,
                fallback_fn=antibody.fallback_fn,
                created_at=antibody.created_at,
                expires_at=antibody.expires_at,
                source=f"broadcast:{source_soul}",
            )
            cache.put(clone_ab)
            shared_count += 1

        if shared_count > 0:
            metrics = self._metrics.get(source_soul)
            if metrics:
                metrics.total_antibodies_shared += shared_count
            log.info(
                f"Immune [{source_soul}]: antibody {antibody.signature} "
                f"broadcast to {shared_count} clone(s)"
            )

    async def run(self) -> None:
        log.info(
            f"Immune engine started "
            f"(purge_interval={self._purge_interval}s)"
        )
        while self._alive:
            try:
                await asyncio.sleep(self._purge_interval)
                self._purge_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Immune engine error: {e}")

    def _purge_all(self) -> None:
        total_purged = 0
        for soul_name, cache in self._caches.items():
            purged = cache.purge_expired()
            if purged > 0:
                total_purged += purged
                metrics = self._metrics.get(soul_name)
                if metrics:
                    metrics.antibodies_expired += purged
        if total_purged > 0:
            log.info(f"Immune: purged {total_purged} expired antibodies")

    def stop(self) -> None:
        self._alive = False

    def status(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "souls": {},
            "clone_groups": {
                k: list(v) for k, v in self._clone_groups.items()
            },
        }
        for soul_name in self._configs:
            cache = self._caches[soul_name]
            metrics = self._metrics[soul_name]
            antibodies = cache.all_antibodies()
            result["souls"][soul_name] = {
                "antibodies": len(antibodies),
                "infections": metrics.total_infections,
                "recoveries": metrics.total_recoveries,
                "generated": metrics.total_antibodies_generated,
                "shared": metrics.total_antibodies_shared,
                "rejected": metrics.total_rejections,
                "expired": metrics.antibodies_expired,
                "antibody_list": [
                    {
                        "signature": ab.signature,
                        "error_type": ab.error_type,
                        "source": ab.source,
                        "successes": ab.success_count,
                        "failures": ab.fail_count,
                        "expires_in": max(
                            0, ab.expires_at - time.time()
                        )
                        if ab.expires_at > 0
                        else -1,
                    }
                    for ab in antibodies
                ],
            }
        return result

    def print_status(self) -> str:
        lines: list[str] = []
        lines.append("")
        lines.append("  ═══ NOUS Immune System Status ═══")
        lines.append("")

        total_ab = 0
        total_rec = 0
        total_inf = 0

        for soul_name in sorted(self._configs):
            cache = self._caches[soul_name]
            metrics = self._metrics[soul_name]
            antibodies = cache.all_antibodies()
            total_ab += len(antibodies)
            total_rec += metrics.total_recoveries
            total_inf += metrics.total_infections

            lines.append(f"  ── {soul_name} ──")
            lines.append(
                f"  Antibodies:    {len(antibodies)}"
                f"/{self._configs[soul_name].max_antibodies}"
            )
            lines.append(f"  Infections:    {metrics.total_infections}")
            lines.append(f"  Recoveries:    {metrics.total_recoveries}")
            lines.append(f"  Generated:     {metrics.total_antibodies_generated}")
            lines.append(f"  Shared:        {metrics.total_antibodies_shared}")
            if antibodies:
                for ab in antibodies[:5]:
                    src = ab.source
                    exp = ""
                    if ab.expires_at > 0:
                        remaining = max(0, ab.expires_at - time.time())
                        exp = f" expires={remaining:.0f}s"
                    lines.append(
                        f"    [{ab.signature}] {ab.error_type} "
                        f"src={src} ok={ab.success_count}{exp}"
                    )
            lines.append("")

        recovery_rate = (
            f"{(total_rec / total_inf * 100):.0f}%"
            if total_inf > 0
            else "N/A"
        )
        lines.append("  ══════════════════════════════════════")
        lines.append(
            f"  Total: {total_ab} antibodies, "
            f"{total_rec}/{total_inf} recoveries ({recovery_rate})"
        )
        return "\n".join(lines)
