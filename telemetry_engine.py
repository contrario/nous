"""
NOUS Telemetry Engine — Τηλεμετρία (Tilemetria)
=================================================
Observability for all soul activity.
Traces: cycle, sense, heal, immune, dream, mitosis, retirement.
Exporters: console, jsonl, http (Langfuse/OTLP compatible).
Zero-cost when disabled.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

log = logging.getLogger("nous.telemetry")


class SpanKind(str, Enum):
    CYCLE = "cycle"
    SENSE = "sense"
    LLM = "llm"
    HEAL = "heal"
    IMMUNE = "immune"
    DREAM = "dream"
    MITOSIS = "mitosis"
    RETIREMENT = "retirement"
    SPEAK = "speak"
    LISTEN = "listen"


class SpanStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class Span:
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    kind: SpanKind
    soul_name: str
    start_time: float
    end_time: float = 0.0
    status: SpanStatus = SpanStatus.OK
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        if self.end_time <= 0:
            return 0.0
        return (self.end_time - self.start_time) * 1000

    def finish(self, status: SpanStatus = SpanStatus.OK, **attrs: Any) -> None:
        self.end_time = time.time()
        self.status = status
        self.attributes.update(attrs)

    def add_event(self, name: str, **attrs: Any) -> None:
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attrs,
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "kind": self.kind.value,
            "soul": self.soul_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": round(self.duration_ms, 2),
            "status": self.status.value,
            "attributes": self.attributes,
            "events": self.events,
        }


class NoopSpan:
    """Zero-cost span when telemetry is disabled or sampled out."""

    def __init__(self) -> None:
        self.trace_id = ""
        self.span_id = ""
        self.parent_span_id = None
        self.kind = SpanKind.CYCLE
        self.soul_name = ""
        self.status = SpanStatus.OK
        self.attributes: dict[str, Any] = {}

    def finish(self, status: SpanStatus = SpanStatus.OK, **attrs: Any) -> None:
        pass

    def add_event(self, name: str, **attrs: Any) -> None:
        pass

    def to_dict(self) -> dict[str, Any]:
        return {}

    @property
    def duration_ms(self) -> float:
        return 0.0


_NOOP = NoopSpan()


class Exporter:
    """Base exporter — subclassed for each output target."""

    async def export(self, spans: list[Span]) -> None:
        pass

    async def shutdown(self) -> None:
        pass


class ConsoleExporter(Exporter):
    """Structured log output for each completed span."""

    async def export(self, spans: list[Span]) -> None:
        for span in spans:
            dur = f"{span.duration_ms:.1f}ms"
            status_icon = "✓" if span.status == SpanStatus.OK else "✗"
            attrs = ""
            if span.attributes:
                key_attrs = {k: v for k, v in span.attributes.items() if k in (
                    "tool", "model", "tokens_in", "tokens_out", "cost",
                    "error_type", "clone_name", "cache_hit", "antibody_id",
                )}
                if key_attrs:
                    attrs = " " + " ".join(f"{k}={v}" for k, v in key_attrs.items())
            log.info(
                f"[TRACE] {status_icon} {span.soul_name}/{span.kind.value} "
                f"{dur}{attrs} trace={span.trace_id[:8]}"
            )


class JsonlExporter(Exporter):
    """Append spans to a JSONL file for offline analysis."""

    def __init__(self, path: str = "nous_telemetry.jsonl") -> None:
        self._path = path
        self._lock = asyncio.Lock()

    async def export(self, spans: list[Span]) -> None:
        async with self._lock:
            with open(self._path, "a") as f:
                for span in spans:
                    f.write(json.dumps(span.to_dict()) + "\n")

    async def shutdown(self) -> None:
        log.info(f"Telemetry JSONL written to {self._path}")


class HttpExporter(Exporter):
    """Post spans to HTTP endpoint (Langfuse/OTLP compatible)."""

    def __init__(self, endpoint: str, headers: Optional[dict[str, str]] = None) -> None:
        self._endpoint = endpoint
        self._headers = headers or {}
        self._client: Optional[Any] = None

    async def _get_client(self) -> Any:
        if self._client is None:
            import httpx
            auth_headers = dict(self._headers)
            langfuse_pk = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
            langfuse_sk = os.environ.get("LANGFUSE_SECRET_KEY", "")
            if langfuse_pk and langfuse_sk:
                import base64
                creds = base64.b64encode(f"{langfuse_pk}:{langfuse_sk}".encode()).decode()
                auth_headers["Authorization"] = f"Basic {creds}"
            auth_headers.setdefault("Content-Type", "application/json")
            self._client = httpx.AsyncClient(timeout=10.0, headers=auth_headers)
        return self._client

    async def export(self, spans: list[Span]) -> None:
        try:
            client = await self._get_client()
            payload = {
                "batch": [span.to_dict() for span in spans],
                "metadata": {
                    "sdk": "nous-telemetry",
                    "version": "1.0",
                },
            }
            resp = await client.post(self._endpoint, json=payload)
            if resp.status_code >= 400:
                log.warning(f"Telemetry HTTP export failed: {resp.status_code}")
        except Exception as e:
            log.warning(f"Telemetry HTTP export error: {e}")

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


@dataclass
class TelemetryConfig:
    enabled: bool = True
    exporter: str = "console"
    endpoint: Optional[str] = None
    sample_rate: float = 1.0
    trace_senses: bool = True
    trace_llm: bool = True
    buffer_size: int = 1000


class TelemetryEngine:
    """Central telemetry collector and exporter for all soul activity."""

    def __init__(self, config: TelemetryConfig) -> None:
        self._config = config
        self._buffer: list[Span] = []
        self._lock = asyncio.Lock()
        self._alive = True
        self._exporter = self._build_exporter()
        self._total_spans = 0
        self._total_exported = 0
        self._active_traces: dict[str, str] = {}

    def _build_exporter(self) -> Exporter:
        name = self._config.exporter.lower()
        if name == "console":
            return ConsoleExporter()
        elif name == "jsonl":
            return JsonlExporter()
        elif name in ("http", "langfuse", "otlp"):
            endpoint = self._config.endpoint or ""
            return HttpExporter(endpoint)
        else:
            log.warning(f"Unknown exporter '{name}', falling back to console")
            return ConsoleExporter()

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def _should_sample(self) -> bool:
        if self._config.sample_rate >= 1.0:
            return True
        return random.random() < self._config.sample_rate

    def start_trace(self, soul_name: str) -> str:
        trace_id = uuid.uuid4().hex[:16]
        self._active_traces[soul_name] = trace_id
        return trace_id

    def get_trace_id(self, soul_name: str) -> str:
        return self._active_traces.get(soul_name, uuid.uuid4().hex[:16])

    def start_span(
        self,
        kind: SpanKind,
        soul_name: str,
        parent_span_id: Optional[str] = None,
        **attributes: Any,
    ) -> Span | NoopSpan:
        if not self._config.enabled:
            return _NOOP
        if kind == SpanKind.SENSE and not self._config.trace_senses:
            return _NOOP
        if kind == SpanKind.LLM and not self._config.trace_llm:
            return _NOOP
        if not self._should_sample():
            return _NOOP

        trace_id = self.get_trace_id(soul_name)
        span = Span(
            trace_id=trace_id,
            span_id=uuid.uuid4().hex[:12],
            parent_span_id=parent_span_id,
            kind=kind,
            soul_name=soul_name,
            start_time=time.time(),
            attributes=dict(attributes),
        )
        return span

    async def record(self, span: Span | NoopSpan) -> None:
        if isinstance(span, NoopSpan):
            return
        async with self._lock:
            self._buffer.append(span)
            self._total_spans += 1
            if len(self._buffer) >= self._config.buffer_size:
                await self._flush_locked()

    async def _flush_locked(self) -> None:
        if not self._buffer:
            return
        batch = list(self._buffer)
        self._buffer.clear()
        try:
            await self._exporter.export(batch)
            self._total_exported += len(batch)
        except Exception as e:
            log.error(f"Telemetry flush error: {e}")

    async def flush(self) -> None:
        async with self._lock:
            await self._flush_locked()

    async def run(self) -> None:
        log.info(
            f"Telemetry engine started (exporter={self._config.exporter}, "
            f"sample_rate={self._config.sample_rate})"
        )
        while self._alive:
            try:
                await asyncio.sleep(5.0)
                await self.flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Telemetry engine error: {e}")

        await self.flush()
        await self._exporter.shutdown()
        log.info(
            f"Telemetry engine stopped: {self._total_spans} spans collected, "
            f"{self._total_exported} exported"
        )

    def stop(self) -> None:
        self._alive = False

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self._config.enabled,
            "exporter": self._config.exporter,
            "sample_rate": self._config.sample_rate,
            "total_spans": self._total_spans,
            "total_exported": self._total_exported,
            "buffer_size": len(self._buffer),
            "active_traces": len(self._active_traces),
        }

    def print_status(self) -> str:
        lines: list[str] = []
        lines.append("")
        lines.append("  ═══ NOUS Telemetry Status ═══")
        lines.append("")
        lines.append(f"  Enabled:          {self._config.enabled}")
        lines.append(f"  Exporter:         {self._config.exporter}")
        if self._config.endpoint:
            lines.append(f"  Endpoint:         {self._config.endpoint}")
        lines.append(f"  Sample rate:      {self._config.sample_rate}")
        lines.append(f"  Trace senses:     {self._config.trace_senses}")
        lines.append(f"  Trace LLM:        {self._config.trace_llm}")
        lines.append(f"  Buffer capacity:  {self._config.buffer_size}")
        lines.append("")
        lines.append(f"  Total spans:      {self._total_spans}")
        lines.append(f"  Exported:         {self._total_exported}")
        lines.append(f"  In buffer:        {len(self._buffer)}")
        lines.append(f"  Active traces:    {len(self._active_traces)}")
        lines.append("")
        lines.append("  ══════════════════════════════════════")
        return "\n".join(lines)
