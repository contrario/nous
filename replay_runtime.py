"""
replay_runtime.py — Runtime dispatch layer for deterministic replay.

ReplayContext is the primary interface that sits between a soul's generated
code and its non-deterministic inputs. It has three modes:

  OFF:     Pass-through. Zero overhead. No store, no wrapping.
  RECORD:  Execute real logic, record (inputs, outputs, timestamps) to store.
  REPLAY:  Skip real logic, return recorded outputs from store.

Non-deterministic sources covered in Phase A:
  - Wall clock           (ctx.now())
  - Random numbers       (ctx.rand(), ctx.randint())
  - LLM request seeds    (ctx.llm_seed(...))
  - Sense invocations    (ctx.record_or_replay_sense(...))
  - Memory writes        (ctx.record_memory_write(...))

Each wrapped call produces a single event in the store. In replay mode, the
event is matched by (soul, cycle, kind, key) — where `key` is a
deterministic identifier for this call site (e.g. sense_name + canonical_args).

The matching strategy is STRICT by default: if replay reaches a call site
and the next event does not match, a ReplayDivergence is raised with the
full context of what was expected vs. what was found. This is the core
value — divergence means the code path changed, which is exactly what you
want to detect in regression testing.
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from typing import Any, Awaitable, Callable, Optional

from replay_store import Event, EventStore, Mode

logger = logging.getLogger("nous.replay_runtime")


class ReplayDivergence(Exception):
    """Raised when replay encounters an event that doesn't match the expected call."""

    def __init__(
        self,
        expected_soul: str,
        expected_cycle: int,
        expected_kind: str,
        expected_key: str,
        actual_event: Optional[Event],
    ) -> None:
        self.expected_soul = expected_soul
        self.expected_cycle = expected_cycle
        self.expected_kind = expected_kind
        self.expected_key = expected_key
        self.actual_event = actual_event
        if actual_event is None:
            msg = (
                f"replay divergence: expected {expected_kind} from {expected_soul} "
                f"cycle={expected_cycle} key={expected_key}, but event log is exhausted"
            )
        else:
            msg = (
                f"replay divergence: expected {expected_kind} from {expected_soul} "
                f"cycle={expected_cycle} key={expected_key}, got "
                f"{actual_event.kind} from {actual_event.soul} cycle={actual_event.cycle}"
            )
        super().__init__(msg)


def _canonical_key(*parts: Any) -> str:
    """Build a deterministic call-site key from arbitrary parts."""
    canonical = json.dumps(list(parts), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class ReplayContext:
    """Primary runtime interface for deterministic replay."""

    def __init__(
        self,
        store: Optional[EventStore] = None,
        mode: Mode = "off",
        seed_base: int = 0,
        intervention_engine: Optional[Any] = None,
    ) -> None:
        # __intervention_runtime_hook_v1__
        self._store = store
        self._mode = mode
        self._seed_base = seed_base
        self._fake_now: float = 0.0
        self._last_parent: int = -1
        self._intervention_engine: Optional[Any] = intervention_engine
        if mode == "replay" and store is None:
            raise ValueError("replay mode requires a store")
        if mode == "record" and store is None:
            raise ValueError("record mode requires a store")

    # __intervention_runtime_hook_v1__
    def set_intervention_engine(self, engine: Optional[Any]) -> None:
        """Attach or replace the InterventionEngine. Takes effect on next event."""
        self._intervention_engine = engine

    def _intervention_check(
        self,
        soul: str,
        cycle: int,
        kind: str,
        data: dict[str, Any],
    ) -> Any:
        """
        Run policy engine against a pending event. Record mode only.

        On triggered outcome, emits a governance.intervention audit event
        to the store. For block/abort_cycle actions, re-raises the
        corresponding InterventionError after the audit emission so the
        caller never proceeds to the real side-effect.

        Replay / off mode: no-op (determinism preserved; governance events
        are reproduced from the recorded log).
        """
        engine = self._intervention_engine
        if engine is None or not getattr(engine, "enabled", False):
            return
        if self._mode != "record":
            return

        try:
            from intervention import (
                InterventionBlocked,
                InterventionAborted,
                InterventionError,
            )
        except Exception:
            return

        class _ProbeEvent:
            __slots__ = (
                "seq_id", "parent_id", "soul", "cycle",
                "kind", "timestamp", "data", "prev_hash", "hash",
            )

            def __init__(self, _soul: str, _cycle: int, _kind: str, _data: dict[str, Any]) -> None:
                self.seq_id = 0
                self.parent_id = -1
                self.soul = _soul
                self.cycle = _cycle
                self.kind = _kind
                self.timestamp = 0.0
                self.data = _data
                self.prev_hash = ""
                self.hash = ""

        probe = _ProbeEvent(soul, cycle, kind, data)

        try:
            outcome = engine.check(probe)
        except InterventionError as exc:
            self._emit_intervention_audit(soul, cycle, exc.outcome)
            raise
        except Exception:
            return

        # __inject_message_replay_v1__
        if outcome.triggered:
            self._emit_intervention_audit(soul, cycle, outcome)
            return outcome
        return None

    def _emit_intervention_audit(
        self,
        soul: str,
        cycle: int,
        outcome: Any,
    ) -> None:
        """Append a governance.intervention event to the store (record mode only)."""
        if self._mode != "record" or self._store is None:
            return
        try:
            audit_data: dict[str, Any] = outcome.to_audit_data()
        except Exception:
            audit_data = {
                "action": getattr(outcome, "action", "unknown"),
                "policies": list(getattr(outcome, "policy_names", ())),
                "score": float(getattr(outcome, "score", 0.0)),
            }
        try:
            ev = self._store.append(
                soul=soul,
                cycle=cycle,
                kind="governance.intervention",
                parent_id=self._last_parent,
                data=audit_data,
            )
            self._last_parent = ev.seq_id
        except Exception:
            return

    @property
    def mode(self) -> Mode:
        return self._mode

    @property
    def store(self) -> Optional[EventStore]:
        return self._store

    @property
    def enabled(self) -> bool:
        return self._mode != "off"

    # ─────────────────────────────────────────────────────────
    # Deterministic clock
    # ─────────────────────────────────────────────────────────
    def now(self, soul: str = "runtime", cycle: int = 0) -> float:
        """Return current time. In replay, returns the recorded time."""
        if self._mode == "off":
            return time.time()
        if self._mode == "record":
            assert self._store is not None
            t = time.time()
            self._store.append(
                soul=soul, cycle=cycle, kind="clock.now",
                parent_id=self._last_parent, data={"t": t},
            )
            return t
        # replay
        ev = self._expect_event(soul, cycle, "clock.now", key=None)
        return float(ev.data.get("t", 0.0))

    # ─────────────────────────────────────────────────────────
    # Deterministic random
    # ─────────────────────────────────────────────────────────
    def rand(self, soul: str = "runtime", cycle: int = 0) -> float:
        if self._mode == "off":
            return random.random()
        if self._mode == "record":
            assert self._store is not None
            v = random.random()
            self._store.append(
                soul=soul, cycle=cycle, kind="random.rand",
                parent_id=self._last_parent, data={"v": v},
            )
            return v
        ev = self._expect_event(soul, cycle, "random.rand", key=None)
        return float(ev.data.get("v", 0.0))

    def randint(self, low: int, high: int, soul: str = "runtime", cycle: int = 0) -> int:
        if self._mode == "off":
            return random.randint(low, high)
        if self._mode == "record":
            assert self._store is not None
            v = random.randint(low, high)
            self._store.append(
                soul=soul, cycle=cycle, kind="random.randint",
                parent_id=self._last_parent,
                data={"v": v, "low": low, "high": high},
            )
            return v
        ev = self._expect_event(soul, cycle, "random.randint", key=None)
        return int(ev.data.get("v", 0))

    # ─────────────────────────────────────────────────────────
    # LLM seed — deterministic seed generation for sampling replay
    # ─────────────────────────────────────────────────────────
    def llm_seed(self, soul: str, cycle: int, prompt_hash: str) -> int:
        """Generate a deterministic seed for an LLM call.

        The seed is derived from (seed_base, soul, cycle, prompt_hash) so it
        is identical across record+replay runs. When the LLM provider supports
        seed parameter (OpenAI-compatible), this enables sampling-level replay.
        """
        payload = f"{self._seed_base}:{soul}:{cycle}:{prompt_hash}"
        h = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return int(h[:8], 16)

    # ─────────────────────────────────────────────────────────
    # Sense invocation record-or-replay
    # ─────────────────────────────────────────────────────────
    async def record_or_replay_sense(
        self,
        soul: str,
        cycle: int,
        sense_name: str,
        args: dict[str, Any],
        execute: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Wrap a sense invocation. Record in record mode, replay in replay mode."""
        key = _canonical_key(sense_name, sorted(args.items()))
        if self._mode == "off":
            return await execute()
        if self._mode == "record":
            assert self._store is not None
            # __intervention_runtime_hook_v1__
            self._intervention_check(
                soul, cycle, "sense.invoke",
                {"sense": sense_name, "args": args, "key": key},
            )
            invoke_ev = self._store.append(
                soul=soul, cycle=cycle, kind="sense.invoke",
                parent_id=self._last_parent,
                data={"sense": sense_name, "args": args, "key": key},
            )
            self._last_parent = invoke_ev.seq_id
            try:
                result = await execute()
                self._store.append(
                    soul=soul, cycle=cycle, kind="sense.result",
                    parent_id=invoke_ev.seq_id,
                    data={"sense": sense_name, "key": key, "value": result},
                )
                return result
            except Exception as exc:
                self._store.append(
                    soul=soul, cycle=cycle, kind="sense.error",
                    parent_id=invoke_ev.seq_id,
                    data={"sense": sense_name, "key": key, "error": repr(exc)},
                )
                raise
        # replay
        invoke = self._expect_event(soul, cycle, "sense.invoke", key=key)
        self._last_parent = invoke.seq_id
        follow = self._expect_one_of(
            soul=soul, cycle=cycle, kinds=("sense.result", "sense.error"), key=key,
        )
        if follow.kind == "sense.error":
            raise RuntimeError(
                f"replay: sense {sense_name} was an error in recorded run: "
                f"{follow.data.get('error')}"
            )
        return follow.data.get("value")

    # __replay_llm_wrap_v1__
    async def record_or_replay_llm(
        self,
        soul: str,
        cycle: int,
        provider: str,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
        execute: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        """Wrap an LLM call. Record in record mode, replay in replay mode.

        `execute` must be a zero-arg async callable that performs the real LLM
        call and returns a dict with at least: text, cost, tier, tokens_in,
        tokens_out, elapsed_ms. Extra keys are preserved in the event payload.

        Match key is sha256(canonical(provider|model|messages|temperature))[:16].
        In replay, the recorded response dict is returned verbatim.
        """
        payload = {
            "provider": provider,
            "model": model,
            "messages": messages,
            "temperature": float(temperature),
        }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        prompt_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        key = prompt_hash[:16]

        if self._mode == "off":
            return await execute()

        if self._mode == "record":
            assert self._store is not None
            seed = self.llm_seed(soul=soul, cycle=cycle, prompt_hash=prompt_hash)
            messages_preview: list[dict[str, str]] = []
            for m in messages:
                role = str(m.get("role", ""))
                content = str(m.get("content", ""))
                if len(content) > 400:
                    content = content[:400] + "...<truncated>"
                messages_preview.append({"role": role, "content": content})
            # __intervention_runtime_hook_v1__
            _llm_probe_data: dict[str, Any] = {
                "provider": provider,
                "model": model,
                "prompt_hash": prompt_hash,
                "messages_preview": messages_preview,
                "temperature": float(temperature),
                "seed": seed,
                "key": key,
            }
            _inject_outcome = self._intervention_check(soul, cycle, "llm.request", _llm_probe_data)
            if _inject_outcome is not None and _inject_outcome.action == "inject_message":
                _inject_role = getattr(_inject_outcome, "inject_role", "system")
                _inject_content = getattr(_inject_outcome, "inject_content", "")
                if _inject_content:
                    # __inject_message_rehash_v1__
                    messages.insert(0, {"role": _inject_role, "content": _inject_content})
                    _post_inject_payload = {
                        "provider": provider,
                        "model": model,
                        "messages": messages,
                        "temperature": float(temperature),
                    }
                    _post_inject_canonical = json.dumps(
                        _post_inject_payload,
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    _post_inject_hash = hashlib.sha256(
                        _post_inject_canonical.encode("utf-8")
                    ).hexdigest()
                    _llm_probe_data["prompt_hash_post_inject"] = _post_inject_hash
                    _llm_probe_data["injected_role"] = _inject_role
                    _llm_probe_data["injected_policies"] = list(_inject_outcome.policy_names)
            req_ev = self._store.append(
                soul=soul, cycle=cycle, kind="llm.request",
                parent_id=self._last_parent,
                data=_llm_probe_data,
            )
            self._last_parent = req_ev.seq_id
            try:
                result = await execute()
                resp_data = {
                    "text": str(result.get("text", "")),
                    "cost": float(result.get("cost", 0.0)),
                    "tier": str(result.get("tier", "")),
                    "tokens_in": int(result.get("tokens_in", 0)),
                    "tokens_out": int(result.get("tokens_out", 0)),
                    "elapsed_ms": float(result.get("elapsed_ms", 0.0)),
                    "key": key,
                }
                self._store.append(
                    soul=soul, cycle=cycle, kind="llm.response",
                    parent_id=self._last_parent,
                    data=resp_data,
                )
                return result
            except Exception as exc:
                self._store.append(
                    soul=soul, cycle=cycle, kind="llm.error",
                    parent_id=self._last_parent,
                    data={"error": repr(exc), "key": key},
                )
                raise

        # replay
        req = self._expect_event(soul, cycle, "llm.request", key=key)
        self._last_parent = req.seq_id
        follow = self._expect_one_of(
            soul=soul, cycle=cycle, kinds=("llm.response", "llm.error"), key=key,
        )
        if follow.kind == "llm.error":
            raise RuntimeError(
                f"replay: llm call was an error in recorded run: "
                f"{follow.data.get('error')}"
            )
        return {
            "success": True,
            "text": follow.data.get("text", ""),
            "cost": float(follow.data.get("cost", 0.0)),
            "tier": follow.data.get("tier", ""),
            "tokens_in": int(follow.data.get("tokens_in", 0)),
            "tokens_out": int(follow.data.get("tokens_out", 0)),
            "elapsed_ms": float(follow.data.get("elapsed_ms", 0.0)),
        }

    # ─────────────────────────────────────────────────────────
    # Memory write audit
    # ─────────────────────────────────────────────────────────
    def record_memory_write(
        self, soul: str, cycle: int, field: str, old_value: Any, new_value: Any,
    ) -> None:
        """In record mode, log a memory write. In replay mode, verify it matches."""
        if self._mode == "off":
            return
        if self._mode == "record":
            assert self._store is not None
            # __intervention_memory_hook_v1__
            self._intervention_check(
                soul, cycle, "memory.write",
                {"field": field, "old": old_value, "new": new_value},
            )
            self._store.append(
                soul=soul, cycle=cycle, kind="memory.write",
                parent_id=self._last_parent,
                data={"field": field, "old": old_value, "new": new_value},
            )
            return
        # replay: verify
        key = _canonical_key(field)
        ev = self._expect_event(soul, cycle, "memory.write", key=None)
        if ev.data.get("field") != field:
            raise ReplayDivergence(soul, cycle, "memory.write", key, ev)

    # ─────────────────────────────────────────────────────────
    # Cycle boundaries (for grouping / indexing)
    # ─────────────────────────────────────────────────────────
    def record_cycle_start(self, soul: str, cycle: int) -> None:
        # __replay_cycle_consume_v1__
        if self._mode == "record":
            assert self._store is not None
            ev = self._store.append(
                soul=soul, cycle=cycle, kind="cycle.start",
                parent_id=self._last_parent, data={},
            )
            self._last_parent = ev.seq_id
            return
        if self._mode == "replay":
            ev = self._expect_event(soul, cycle, "cycle.start", key=None)
            self._last_parent = ev.seq_id
            return
        # mode == "off": no-op

    def record_cycle_end(self, soul: str, cycle: int, status: str = "ok") -> None:
        if self._mode == "record":
            assert self._store is not None
            self._store.append(
                soul=soul, cycle=cycle, kind="cycle.end",
                parent_id=self._last_parent, data={"status": status},
            )
            return
        if self._mode == "replay":
            self._expect_event(soul, cycle, "cycle.end", key=None)
            return
        # mode == "off": no-op

    # ─────────────────────────────────────────────────────────
    # Internal: replay event matching
    # ─────────────────────────────────────────────────────────
    def _expect_event(
        self, soul: str, cycle: int, kind: str, key: Optional[str],
    ) -> Event:
        assert self._store is not None
        ev = self._store.next_event()
        if ev is None:
            raise ReplayDivergence(soul, cycle, kind, key or "", None)
        if ev.soul != soul or ev.cycle != cycle or ev.kind != kind:
            raise ReplayDivergence(soul, cycle, kind, key or "", ev)
        if key is not None:
            recorded_key = ev.data.get("key")
            if recorded_key is not None and recorded_key != key:
                raise ReplayDivergence(soul, cycle, kind, key, ev)
        return ev

    def _expect_one_of(
        self, soul: str, cycle: int, kinds: tuple[str, ...], key: Optional[str],
    ) -> Event:
        assert self._store is not None
        ev = self._store.next_event()
        if ev is None:
            raise ReplayDivergence(soul, cycle, kinds[0], key or "", None)
        if ev.soul != soul or ev.cycle != cycle or ev.kind not in kinds:
            raise ReplayDivergence(soul, cycle, "/".join(kinds), key or "", ev)
        if key is not None:
            recorded_key = ev.data.get("key")
            if recorded_key is not None and recorded_key != key:
                raise ReplayDivergence(soul, cycle, ev.kind, key, ev)
        return ev


def build_context(
    mode: Mode,
    path: Optional[str] = None,
    fsync: str = "every_event",
    seed_base: int = 0,
) -> ReplayContext:
    """Factory for ReplayContext. Returns a no-op context when mode='off'."""
    if mode == "off":
        return ReplayContext(store=None, mode="off", seed_base=seed_base)
    if path is None:
        raise ValueError(f"path is required for mode={mode}")
    store = EventStore.open(path, mode=mode, fsync=fsync)  # type: ignore[arg-type]
    return ReplayContext(store=store, mode=mode, seed_base=seed_base)
