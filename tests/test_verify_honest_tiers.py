"""S-verify-tier increment 1a: honest verification tiers.

The static verifier must label cost as ESTIMATED, decidable structural checks
as VERIFIED, and declared config as REPORTED -- and NEVER as PROVEN, which is
reserved for the SMT/Farkas leg (increment 2). The `severity` axis is left
untouched (dual-axis), so every affirmative item keeps severity PROVEN and no
existing consumer of `.proven` changes behaviour.
"""
from __future__ import annotations

from parser import parse_nous
from verifier import verify_program, VerificationTier, VerificationSeverity


_SRC = """
world Pipeline {
    law cost_ceiling = $2.00 per cycle
    heartbeat = 5m
    telemetry {
        enabled: true
        exporter: console
        sample_rate: 1.0
    }
}
message Ping { ts: float = 0.0 }
soul A {
    mind: claude-sonnet @ Tier0A
    memory { count: int = 0 }
    instinct {
        remember count += 1
        speak Ping(ts: now())
    }
    heal { on timeout => retry(3, exponential) }
}
soul B {
    mind: claude-sonnet @ Tier0A
    memory { received: int = 0 }
    instinct {
        let msg = listen A::Ping
        remember received += 1
    }
    heal { on timeout => retry(3, exponential) }
}
nervous_system { A -> B }
"""


def _items_by_code(result: object) -> dict:
    out: dict = {}
    for i in result.items:
        out.setdefault(i.code, i)
    return out


def test_cost_is_estimated_not_proven() -> None:
    result = verify_program(parse_nous(_SRC))
    by = _items_by_code(result)
    cost = [by[c] for c in ("VR001", "VR002") if c in by]
    assert cost, "expected a resource_bound cost item"
    for item in cost:
        assert item.tier == VerificationTier.ESTIMATED, (
            item.code + " must be ESTIMATED (token heuristic), got " + item.tier
        )


def test_structural_checks_are_verified() -> None:
    result = verify_program(parse_nous(_SRC))
    by = _items_by_code(result)
    structural = [c for c in ("VD001", "VE001", "VL002", "VM001", "VP003")
                  if c in by]
    assert structural, "expected at least one decidable structural check"
    for code in structural:
        assert by[code].tier == VerificationTier.VERIFIED, (
            code + " must be VERIFIED, got " + by[code].tier
        )


def test_declared_config_is_reported() -> None:
    result = verify_program(parse_nous(_SRC))
    by = _items_by_code(result)
    assert "VTL001" in by, "expected telemetry-enabled item"
    assert by["VTL001"].tier == VerificationTier.REPORTED, (
        "declared telemetry config must be REPORTED, got " + by["VTL001"].tier
    )


def test_no_static_check_is_falsely_proven() -> None:
    result = verify_program(parse_nous(_SRC))
    affirmative = [i for i in result.items
                   if i.severity == VerificationSeverity.PROVEN]
    proven_tier = [i for i in affirmative
                   if i.tier == VerificationTier.PROVEN]
    assert proven_tier == [], (
        "the static surface carries no Z3/Farkas proof; nothing may be tier "
        "PROVEN until the SMT leg (increment 2): "
        + ", ".join(i.code for i in proven_tier)
    )


def test_dual_axis_is_non_breaking() -> None:
    result = verify_program(parse_nous(_SRC))
    affirmative = [i for i in result.items
                   if i.severity == VerificationSeverity.PROVEN]
    assert len(result.proven) == len(affirmative), (
        "`.proven` (severity axis) must still return every affirmative item "
        "so existing consumers are unchanged"
    )
    assert all(hasattr(i, "tier") for i in result.items)


def test_summary_reports_four_tiers() -> None:
    result = verify_program(parse_nous(_SRC))
    tail = result.summary().splitlines()[-1].lower()
    for word in ("proven", "verified", "estimated", "reported"):
        assert word in tail, "summary tally missing tier: " + word
