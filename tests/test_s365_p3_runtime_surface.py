"""
NOUS Session 365 -- arc B phase P3, clone admission and import surface
(docs/ONE_PRICE_SOURCE_DESIGN.md sections 17.2 P3.5 and 17.6).

Before P3 the mitosis runtime re-verify built every existing soul with
MindNode(model="runtime") and the parent and clone with
MindNode(model="cloned"), so the re-verified program named no real model.
P3 names the runner's model, still passes no pricing table, and leaves
the admission verdict unchanged.

RED before the P3 code stage for the model-naming tests, green after.

# __s365_p3_surface_test_v1__
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

import pytest

import mitosis_engine
import verifier

REPO: Path = Path(__file__).resolve().parent.parent


class _Runner:
    def __init__(self, name: str, model: Optional[str], tier: str = "Tier1") -> None:
        self.name = name
        self._model = model
        self._tier = tier


class _Runtime:
    def __init__(self, runners: list[_Runner], ceiling: float = 0.10) -> None:
        self._runners = runners
        self.cost_ceiling = ceiling


def _reverify(
    monkeypatch: pytest.MonkeyPatch, parent_model: Optional[str]
) -> tuple[bool, str, dict[str, Any]]:
    seen: dict[str, Any] = {}
    real = verifier.NousVerifier

    class Recording(real):
        def __init__(self, program: Any, *args: Any, **kwargs: Any) -> None:
            super().__init__(program, *args, **kwargs)
            seen["models"] = {
                s.name: (s.mind.model if s.mind else None) for s in program.souls
            }
            seen["pricing"] = getattr(self, "_pricing", "<absent>")

    monkeypatch.setattr(verifier, "NousVerifier", Recording)
    runners = [_Runner("Scout", parent_model), _Runner("Relay", "claude-haiku-4-5")]
    engine = mitosis_engine.MitosisEngine(_Runtime(runners))
    config = mitosis_engine.MitosisConfig(trigger_fn=lambda metrics: True)
    ok, report = asyncio.run(engine._verify_clone("Scout", "Scout_clone_1", config))
    return ok, report, seen


def test_reverify_names_the_runner_models(monkeypatch: pytest.MonkeyPatch) -> None:
    ok, report, seen = _reverify(monkeypatch, "deepseek-flash")
    want = {
        "Scout": "deepseek-flash",
        "Relay": "claude-haiku-4-5",
        "Scout_clone_1": "deepseek-flash",
    }
    assert seen.get("models") == want, f"models {seen.get('models')} report {report}"


def test_runner_without_a_model_reverifies_as_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ok, report, seen = _reverify(monkeypatch, None)
    models = seen.get("models") or {}
    got = (models.get("Scout"), models.get("Scout_clone_1"))
    assert got == ("unknown", "unknown"), f"models {models} report {report}"


def test_reverify_passes_no_pricing_table(monkeypatch: pytest.MonkeyPatch) -> None:
    ok, report, seen = _reverify(monkeypatch, "deepseek-flash")
    assert seen.get("pricing") is None, f"pricing {seen.get('pricing')!r} report {report}"


def test_reverify_verdict_does_not_depend_on_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = {
        str(model): _reverify(monkeypatch, model)[:2]
        for model in (None, "deepseek-flash", "s365-not-in-any-table")
    }
    assert len(set(results.values())) == 1, f"verdicts differ by model: {results}"


def test_importing_runtime_does_not_import_pricing() -> None:
    code = (
        "import sys; sys.path.insert(0, " + repr(str(REPO)) + "); "
        "import runtime; print('pricing' in sys.modules)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=120
    )
    detail = f"rc {out.returncode} stdout {out.stdout!r} stderr {out.stderr[-400:]!r}"
    assert out.returncode == 0, detail
    assert out.stdout.strip() == "False", detail
