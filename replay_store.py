"""
replay_store.py — Event store primitive for NOUS deterministic replay.

Design goals:
  - Append-only, content-addressed (SHA256), tamper-evident chain
  - Human-readable storage (JSONL) — auditable with grep/cat/jq
  - Sync write by default — zero event loss on crash
  - Opt-in: no overhead when replay is not enabled in the world

An event has:
  seq_id     : monotonic sequence number (0, 1, 2, ...)
  parent_id  : seq_id of causally preceding event (-1 for root)
  soul       : soul name emitting the event
  cycle      : cycle number within the soul
  kind       : event type (sense.invoke, sense.result, llm.request, ...)
  timestamp  : wall clock at emission (float, unix epoch)
  data       : JSON-serializable event payload
  prev_hash  : SHA256 of previous event's hash field
  hash       : SHA256(prev_hash + canonical_json(content))

The hash chain property: any tampered event invalidates every subsequent
hash. `verify()` recomputes the chain and reports first divergence.

Usage:
    store = EventStore.open("/var/nous/events.jsonl", mode="record")
    ev = store.append(
        soul="Watcher", cycle=1, kind="sense.invoke",
        parent_id=-1, data={"tool": "stock_price"},
    )
    store.close()

    # Replay
    store = EventStore.open("/var/nous/events.jsonl", mode="replay")
    for ev in store:
        print(ev.kind, ev.data)
    store.close()
"""
from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Literal, Optional

logger = logging.getLogger("nous.replay_store")

Mode = Literal["record", "replay", "off"]


@dataclass(frozen=True)
class Event:
    seq_id: int
    parent_id: int
    soul: str
    cycle: int
    kind: str
    timestamp: float
    data: dict[str, Any]
    prev_hash: str
    hash: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Event":
        return cls(
            seq_id=int(d["seq_id"]),
            parent_id=int(d["parent_id"]),
            soul=str(d["soul"]),
            cycle=int(d["cycle"]),
            kind=str(d["kind"]),
            timestamp=float(d["timestamp"]),
            data=dict(d["data"]),
            prev_hash=str(d["prev_hash"]),
            hash=str(d["hash"]),
        )


GENESIS_HASH = "0" * 64  # All-zero SHA256 for the first event's prev_hash.


def _canonical_json(obj: Any) -> str:
    """Deterministic JSON serialization for hashing.

    sort_keys=True guarantees identical output regardless of dict insertion
    order. separators removes whitespace ambiguity. ensure_ascii=False keeps
    Unicode readable but still deterministic.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _compute_hash(prev_hash: str, content: dict[str, Any]) -> str:
    """SHA256 of prev_hash concatenated with canonical content JSON.

    `content` must NOT include the `hash` field itself (would be recursive).
    """
    payload = prev_hash + _canonical_json(content)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class EventStoreError(Exception):
    """Base exception for event store issues."""


class HashChainBroken(EventStoreError):
    """Raised when verify() detects tampering or corruption."""


class EventStore:
    """Append-only JSONL-backed event store with SHA256 hash chain.

    Thread-safe for concurrent append() calls within a single process.
    Not safe for multi-process writes to the same file.
    """

    def __init__(
        self,
        path: Path,
        mode: Mode = "record",
        fsync: Literal["every_event", "every_second", "off"] = "every_event",
    ) -> None:
        self._path = path
        self._mode = mode
        self._fsync_policy = fsync
        self._lock = threading.Lock()
        self._seq_counter = 0
        self._last_hash = GENESIS_HASH
        self._fh: Optional[io.TextIOBase] = None
        self._last_fsync = time.time()
        self._closed = False
        # For replay mode only:
        self._replay_events: list[Event] = []
        self._replay_index = 0

    @classmethod
    def open(
        cls,
        path: str | Path,
        mode: Mode = "record",
        fsync: Literal["every_event", "every_second", "off"] = "every_event",
    ) -> "EventStore":
        p = Path(path)
        store = cls(p, mode=mode, fsync=fsync)
        store._init()
        return store

    @property
    def mode(self) -> Mode:
        return self._mode

    @property
    def path(self) -> Path:
        return self._path

    @property
    def seq_counter(self) -> int:
        return self._seq_counter

    @property
    def last_hash(self) -> str:
        return self._last_hash

    def _init(self) -> None:
        if self._mode == "off":
            return
        if self._mode == "record":
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # Resume: if file exists, scan for last seq + hash to continue chain.
            if self._path.exists() and self._path.stat().st_size > 0:
                last = self._scan_tail_for_resume()
                if last is not None:
                    self._seq_counter = last.seq_id + 1
                    self._last_hash = last.hash
                    logger.info(
                        "event store resumed: path=%s next_seq=%d",
                        self._path, self._seq_counter,
                    )
            self._fh = self._path.open("a", encoding="utf-8", buffering=1)
            return
        if self._mode == "replay":
            if not self._path.exists():
                raise EventStoreError(f"replay file not found: {self._path}")
            self._load_all_for_replay()
            return
        raise EventStoreError(f"unknown mode: {self._mode}")

    def _scan_tail_for_resume(self) -> Optional[Event]:
        """Read the file to find the last valid event for resume."""
        last: Optional[Event] = None
        try:
            with self._path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        last = Event.from_dict(d)
                    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                        logger.warning("skipping malformed event during resume: %s", exc)
        except OSError as exc:
            logger.error("failed to scan event store for resume: %s", exc)
            return None
        return last

    def _load_all_for_replay(self) -> None:
        events: list[Event] = []
        with self._path.open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    events.append(Event.from_dict(d))
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                    raise EventStoreError(
                        f"corrupt event at line {lineno}: {exc}"
                    ) from exc
        self._replay_events = events
        self._replay_index = 0
        logger.info("event store loaded for replay: %d events", len(events))

    def append(
        self,
        soul: str,
        cycle: int,
        kind: str,
        data: dict[str, Any],
        parent_id: int = -1,
        timestamp: Optional[float] = None,
    ) -> Event:
        """Record a new event. Returns the fully-formed Event with assigned seq_id + hash."""
        if self._mode != "record":
            raise EventStoreError(f"append() requires record mode, current={self._mode}")
        if self._closed:
            raise EventStoreError("store is closed")
        ts = timestamp if timestamp is not None else time.time()
        with self._lock:
            seq = self._seq_counter
            content = {
                "seq_id": seq,
                "parent_id": parent_id,
                "soul": soul,
                "cycle": cycle,
                "kind": kind,
                "timestamp": ts,
                "data": data,
                "prev_hash": self._last_hash,
            }
            h = _compute_hash(self._last_hash, content)
            event = Event(
                seq_id=seq,
                parent_id=parent_id,
                soul=soul,
                cycle=cycle,
                kind=kind,
                timestamp=ts,
                data=dict(data),
                prev_hash=self._last_hash,
                hash=h,
            )
            self._write_line(event.to_dict())
            self._seq_counter = seq + 1
            self._last_hash = h
        return event

    def _write_line(self, d: dict[str, Any]) -> None:
        assert self._fh is not None
        line = _canonical_json(d) + "\n"
        self._fh.write(line)
        if self._fsync_policy == "every_event":
            self._fh.flush()
            os.fsync(self._fh.fileno())
        elif self._fsync_policy == "every_second":
            now = time.time()
            if now - self._last_fsync >= 1.0:
                self._fh.flush()
                os.fsync(self._fh.fileno())
                self._last_fsync = now

    def __iter__(self) -> Iterator[Event]:
        if self._mode != "replay":
            raise EventStoreError(f"iteration requires replay mode, current={self._mode}")
        for ev in self._replay_events:
            yield ev

    def next_event(self) -> Optional[Event]:
        """Pop the next event in replay mode. Returns None when exhausted."""
        if self._mode != "replay":
            raise EventStoreError(f"next_event() requires replay mode, current={self._mode}")
        if self._replay_index >= len(self._replay_events):
            return None
        ev = self._replay_events[self._replay_index]
        self._replay_index += 1
        return ev

    def peek_event(self) -> Optional[Event]:
        """Look at next event without consuming it."""
        if self._mode != "replay":
            raise EventStoreError(f"peek_event() requires replay mode, current={self._mode}")
        if self._replay_index >= len(self._replay_events):
            return None
        return self._replay_events[self._replay_index]

    def find_by_key(self, soul: str, cycle: int, kind: str) -> Optional[Event]:
        """Replay-mode helper: locate first matching event without consuming position."""
        if self._mode != "replay":
            raise EventStoreError("find_by_key requires replay mode")
        for ev in self._replay_events[self._replay_index:]:
            if ev.soul == soul and ev.cycle == cycle and ev.kind == kind:
                return ev
        return None

    def verify(self) -> tuple[bool, Optional[int], Optional[str]]:
        """Verify hash chain integrity.

        Returns (ok, first_bad_seq, reason):
          - (True, None, None) if chain is intact
          - (False, seq, reason) pointing to the first broken event
        """
        events: list[Event] = (
            self._replay_events if self._mode == "replay" else self._load_events_for_verify()
        )
        prev = GENESIS_HASH
        for ev in events:
            content = {
                "seq_id": ev.seq_id,
                "parent_id": ev.parent_id,
                "soul": ev.soul,
                "cycle": ev.cycle,
                "kind": ev.kind,
                "timestamp": ev.timestamp,
                "data": ev.data,
                "prev_hash": ev.prev_hash,
            }
            if ev.prev_hash != prev:
                return (
                    False,
                    ev.seq_id,
                    f"prev_hash mismatch: got {ev.prev_hash[:12]}..., expected {prev[:12]}...",
                )
            expected = _compute_hash(prev, content)
            if ev.hash != expected:
                return (
                    False,
                    ev.seq_id,
                    f"hash mismatch: got {ev.hash[:12]}..., expected {expected[:12]}...",
                )
            prev = ev.hash
        return (True, None, None)

    def _load_events_for_verify(self) -> list[Event]:
        if not self._path.exists():
            return []
        events: list[Event] = []
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                events.append(Event.from_dict(json.loads(line)))
        return events

    def stats(self) -> dict[str, Any]:
        if self._mode == "replay":
            total = len(self._replay_events)
            kinds: dict[str, int] = {}
            souls: dict[str, int] = {}
            for ev in self._replay_events:
                kinds[ev.kind] = kinds.get(ev.kind, 0) + 1
                souls[ev.soul] = souls.get(ev.soul, 0) + 1
            return {
                "mode": "replay",
                "total_events": total,
                "kinds": kinds,
                "souls": souls,
                "first_seq": self._replay_events[0].seq_id if total else None,
                "last_seq": self._replay_events[-1].seq_id if total else None,
            }
        return {
            "mode": self._mode,
            "path": str(self._path),
            "seq_counter": self._seq_counter,
            "last_hash": self._last_hash[:12] + "...",
        }

    def close(self) -> None:
        if self._closed:
            return
        if self._fh is not None:
            try:
                self._fh.flush()
                try:
                    os.fsync(self._fh.fileno())
                except OSError:
                    pass
            finally:
                self._fh.close()
                self._fh = None
        self._closed = True

    def __enter__(self) -> "EventStore":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
