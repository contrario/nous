"""
mood_engine.py — Unified MoodEngine (Agent Emotions v1).

Represents mood as a 4D vector:
  - valence    (0=unpleasant, 1=pleasant)
  - arousal    (0=calm, 1=excited)
  - confidence (0=doubtful, 1=self-trusting)
  - fatigue    (0=fresh, 1=exhausted)

Events mutate dimensions. Per-cycle decay pulls valence/arousal/confidence
back toward neutral (0.5) and adds baseline fatigue.

Usage (runtime — called per cycle):
    mood = MoodEngine(config)
    mood.on_cycle_start()
    mood.record_event("sense_error")
    mood.record_event("sense_ok")
    prompt_hint = mood.describe()  # "cautious (low confidence)"

Usage (chat API — called per message with elapsed-time decay):
    mood.advance_by_seconds(elapsed_since_last, heartbeat_seconds=30.0)
    prompt_hint = mood.describe()
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("nous.mood_engine")


@dataclass
class MoodConfig:
    enabled: bool = True
    valence: float = 0.5
    arousal: float = 0.3
    confidence: float = 0.7
    fatigue: float = 0.0
    decay_rate: float = 0.05
    fatigue_per_cycle: float = 0.02


EVENT_DELTAS: dict[str, dict[str, float]] = {
    "sense_error":  {"arousal": +0.20, "valence": -0.15, "confidence": -0.10},
    "sense_ok":     {"valence": +0.05},
    "heal":         {"confidence": -0.20, "fatigue": +0.10, "arousal": +0.10},
    "cost_spike":   {"fatigue": +0.15, "arousal": +0.10, "valence": -0.05},
    "cycle_ok":     {"confidence": +0.02, "fatigue": +0.01},
    "cycle_failed": {"valence": -0.10, "confidence": -0.05, "arousal": +0.15},
    "llm_error":    {"arousal": +0.15, "confidence": -0.10},
    "llm_ok":       {"confidence": +0.03},
    "positive_message": {"valence": +0.08},
    "negative_message": {"valence": -0.10, "arousal": +0.05},
}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


class MoodEngine:
    """Thread-safe mood state tracker for a single soul."""

    def __init__(self, config: Optional[MoodConfig] = None) -> None:
        self._cfg = config or MoodConfig()
        self.valence: float = self._cfg.valence
        self.arousal: float = self._cfg.arousal
        self.confidence: float = self._cfg.confidence
        self.fatigue: float = self._cfg.fatigue
        self._lock = threading.Lock()
        self._last_update: float = time.time()
        self._total_events: int = 0
        self._cycle_count: int = 0

    @property
    def enabled(self) -> bool:
        return self._cfg.enabled

    def record_event(self, event: str) -> None:
        if not self._cfg.enabled:
            return
        deltas = EVENT_DELTAS.get(event)
        if not deltas:
            logger.debug("mood: unknown event %s", event)
            return
        with self._lock:
            for dim, delta in deltas.items():
                cur = getattr(self, dim)
                setattr(self, dim, _clamp(cur + delta))
            self._total_events += 1

    def apply_decay(self, cycles: float = 1.0) -> None:
        """Apply `cycles` worth of decay toward neutral, plus fatigue tick."""
        if not self._cfg.enabled or cycles <= 0:
            return
        rate = self._cfg.decay_rate * cycles
        if rate > 1.0:
            rate = 1.0
        fatigue_tick = self._cfg.fatigue_per_cycle * cycles
        with self._lock:
            self.valence = _clamp(self.valence + (0.5 - self.valence) * rate)
            self.arousal = _clamp(self.arousal + (0.5 - self.arousal) * rate)
            self.confidence = _clamp(self.confidence + (0.5 - self.confidence) * rate)
            self.fatigue = _clamp(self.fatigue + fatigue_tick)
            self._cycle_count += 1
            self._last_update = time.time()

    def advance_by_seconds(self, seconds: float, heartbeat_seconds: float) -> None:
        """Chat-API style decay based on real elapsed time."""
        if heartbeat_seconds <= 0:
            return
        cycles = seconds / heartbeat_seconds
        self.apply_decay(cycles)

    def on_cycle_start(self) -> None:
        self.apply_decay(1.0)

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return {
                "valence": self.valence,
                "arousal": self.arousal,
                "confidence": self.confidence,
                "fatigue": self.fatigue,
            }

    def label(self) -> str:
        """Composite mood label from the 4D vector."""
        v, a, c, f = self.valence, self.arousal, self.confidence, self.fatigue
        if f > 0.75:
            return "exhausted"
        if f > 0.55 and a < 0.4:
            return "tired"
        if c < 0.3 and a > 0.6:
            return "anxious"
        if c < 0.35:
            return "cautious"
        if v < 0.3 and a > 0.55:
            return "frustrated"
        if v < 0.35:
            return "discouraged"
        if v > 0.7 and c > 0.7 and a < 0.6:
            return "confident"
        if v > 0.7 and a > 0.6:
            return "enthusiastic"
        if a < 0.25 and f < 0.3:
            return "calm"
        if v > 0.6 and c > 0.55:
            return "engaged"
        return "neutral"

    def describe(self) -> str:
        """One-line prompt-injection description."""
        if not self._cfg.enabled:
            return ""
        lbl = self.label()
        hints: list[str] = []
        if self.confidence < 0.35:
            hints.append("low confidence")
        elif self.confidence > 0.75:
            hints.append("high confidence")
        if self.arousal > 0.7:
            hints.append("high arousal")
        elif self.arousal < 0.25:
            hints.append("calm")
        if self.fatigue > 0.6:
            hints.append("fatigued")
        if self.valence < 0.3:
            hints.append("negative outlook")
        hint_str = f" ({', '.join(hints)})" if hints else ""
        return f"Current mood: {lbl}{hint_str}."

    def stats(self) -> dict:
        return {
            "valence": round(self.valence, 3),
            "arousal": round(self.arousal, 3),
            "confidence": round(self.confidence, 3),
            "fatigue": round(self.fatigue, 3),
            "label": self.label(),
            "events": self._total_events,
            "cycles": self._cycle_count,
        }


def build_from_ast(emotions_node) -> Optional[MoodEngine]:
    """Construct a MoodEngine from an EmotionsNode AST node. Returns None if missing/disabled."""
    if emotions_node is None:
        return None
    if not getattr(emotions_node, "enabled", True):
        return None
    cfg = MoodConfig(
        enabled=True,
        valence=emotions_node.valence,
        arousal=emotions_node.arousal,
        confidence=emotions_node.confidence,
        fatigue=emotions_node.fatigue,
        decay_rate=emotions_node.decay_rate,
        fatigue_per_cycle=emotions_node.fatigue_per_cycle,
    )
    return MoodEngine(cfg)
