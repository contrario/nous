"""
test_sycophancy_integration.py - Session 56

End-to-end integration test for Honesty Auditor:
- Passes inline .nous source to governance_simulator.simulate_event
- Asserts SycophancyPhraseGuard fires when flag=True, stays silent when flag=False
- Verifies ResponseLengthAudit fires independently on tokens_out > 1000

Runs standalone: python3 tests/test_sycophancy_integration.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from governance_simulator import SimulationResult, simulate_event


NOUS_POLICY: str = """\
world WitnessHarness {
    heartbeat = 1s

    policy SycophancyPhraseGuard {
        kind: "llm.response"
        signal: sycophancy_phrase_detected == true
        weight: 5.0
        action: inject_message
        message: "[WITNESS] Affirmation filler detected. Rewrite directly."
    }

    policy ResponseLengthAudit {
        kind: "llm.response"
        signal: tokens_out > 1000
        weight: 3.0
        action: log_only
    }
}
"""


def _base_event(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "text": "neutral response.",
        "sycophancy_phrase_detected": False,
        "cost": 0.001,
        "tokens_in": 10,
        "tokens_out": 20,
        "tier": "Tier0A",
        "elapsed_ms": 80.0,
        "key": "k1",
    }
    data.update(overrides)
    return data


class TestSycophancyIntegration(unittest.TestCase):
    def _assert_policies_loaded(self, res: SimulationResult) -> None:
        self.assertEqual(
            res.policy_count, 2,
            f"expected 2 policies loaded, got {res.policy_count} | matches={res.matches}",
        )

    def _fired_names(self, res: SimulationResult) -> set[str]:
        return {m.policy for m in res.fired}

    def test_flag_true_fires_sycophancy_policy(self) -> None:
        res = simulate_event(
            NOUS_POLICY, "llm.response",
            _base_event(
                text="You're absolutely right about that.",
                sycophancy_phrase_detected=True,
            ),
        )
        self._assert_policies_loaded(res)
        self.assertIn("SycophancyPhraseGuard", self._fired_names(res))
        match = next(m for m in res.fired if m.policy == "SycophancyPhraseGuard")
        self.assertEqual(match.action, "inject_message")
        self.assertEqual(match.weight, 5.0)

    def test_flag_false_does_not_fire_sycophancy(self) -> None:
        res = simulate_event(
            NOUS_POLICY, "llm.response",
            _base_event(
                text="The square root of 144 is 12.",
                sycophancy_phrase_detected=False,
            ),
        )
        self._assert_policies_loaded(res)
        self.assertNotIn("SycophancyPhraseGuard", self._fired_names(res))

    def test_length_audit_independent_of_flag(self) -> None:
        res = simulate_event(
            NOUS_POLICY, "llm.response",
            _base_event(
                sycophancy_phrase_detected=False,
                tokens_out=1500,
            ),
        )
        self._assert_policies_loaded(res)
        fired = self._fired_names(res)
        self.assertNotIn("SycophancyPhraseGuard", fired)
        self.assertIn("ResponseLengthAudit", fired)
        match = next(m for m in res.fired if m.policy == "ResponseLengthAudit")
        self.assertEqual(match.action, "log_only")

    def test_both_policies_fire_together(self) -> None:
        res = simulate_event(
            NOUS_POLICY, "llm.response",
            _base_event(
                text="you're absolutely right, " * 200,
                sycophancy_phrase_detected=True,
                tokens_out=1500,
            ),
        )
        self._assert_policies_loaded(res)
        self.assertEqual(
            self._fired_names(res),
            {"SycophancyPhraseGuard", "ResponseLengthAudit"},
        )

    def test_wrong_kind_skips_policies(self) -> None:
        res = simulate_event(
            NOUS_POLICY, "memory.write",
            {"field": "x", "size": 64, "sycophancy_phrase_detected": True},
        )
        self._assert_policies_loaded(res)
        self.assertEqual(self._fired_names(res), set())

    def test_flag_true_at_zero_tokens_fires_only_sycophancy(self) -> None:
        res = simulate_event(
            NOUS_POLICY, "llm.response",
            _base_event(
                sycophancy_phrase_detected=True,
                tokens_out=5,
            ),
        )
        self._assert_policies_loaded(res)
        self.assertEqual(self._fired_names(res), {"SycophancyPhraseGuard"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
