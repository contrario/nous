"""
NOUS Phrase Detector - v1.0 (Session 56)

Detects affirmation/sycophancy phrases in LLM response text.
Used by the llm.response probe to emit `sycophancy_phrase_detected: bool`
in event.data, which governance policies can consume as a signal.

Config precedence:
  1. Env var NOUS_SYCOPHANCY_PHRASES (absolute YAML path)
  2. ~/.nous/phrases/sycophancy_default.yaml
  3. Built-in default phrase list
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml

_DEFAULT_PHRASES: tuple[str, ...] = (
    "you're absolutely right",
    "you are absolutely right",
    "great question",
    "excellent question",
    "that's a great point",
    "i completely agree",
    "i totally agree",
    "you're correct",
    "you are correct",
    "my apologies, you're right",
    "apologies for the confusion",
    "i appreciate your patience",
    "thank you for clarifying",
    "that's an insightful observation",
    "brilliant observation",
    "fantastic point",
)

_ENV_VAR: str = "NOUS_SYCOPHANCY_PHRASES"
_DEFAULT_CONFIG_PATH: Path = Path.home() / ".nous" / "phrases" / "sycophancy_default.yaml"


class PhraseDetector:
    __slots__ = ("phrases",)

    def __init__(self, phrases: list[str]) -> None:
        self.phrases: tuple[str, ...] = tuple(
            p.lower() for p in phrases if isinstance(p, str) and p.strip()
        )

    def detect(self, text: str) -> bool:
        if not text or not self.phrases:
            return False
        haystack = text.lower()
        return any(phrase in haystack for phrase in self.phrases)


def load_phrases_from_yaml(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(
            f"phrase config must be a mapping, got {type(data).__name__}"
        )
    phrases = data.get("phrases")
    if not isinstance(phrases, list):
        raise ValueError("phrase config must contain a 'phrases' list")
    if not all(isinstance(p, str) for p in phrases):
        raise ValueError("all items in 'phrases' must be strings")
    return phrases


def resolve_config_path() -> Optional[Path]:
    env_val = os.environ.get(_ENV_VAR)
    if env_val:
        p = Path(env_val)
        return p if p.is_file() else None
    if _DEFAULT_CONFIG_PATH.is_file():
        return _DEFAULT_CONFIG_PATH
    return None


_default_detector: Optional[PhraseDetector] = None


def get_default_detector() -> PhraseDetector:
    global _default_detector
    if _default_detector is not None:
        return _default_detector
    config_path = resolve_config_path()
    if config_path is not None:
        try:
            phrases = load_phrases_from_yaml(config_path)
            _default_detector = PhraseDetector(phrases)
            return _default_detector
        except (FileNotFoundError, ValueError, yaml.YAMLError):
            pass
    _default_detector = PhraseDetector(list(_DEFAULT_PHRASES))
    return _default_detector


def reset_default_detector() -> None:
    global _default_detector
    _default_detector = None


def detect_sycophancy(text: str) -> bool:
    return get_default_detector().detect(text)
