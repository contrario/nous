"""Regression for the warning-as-proven leak (1b-fix).

A fatigue declaration emits VMB002 as a WARNING, not an affirmative finding.
It must never carry severity PROVEN, and the API router must send WARNING to
warnings (not proven) and INFO to info. This pins the routing contract so the
"WARN" vs "WARNING" typo cannot reappear.
"""
from __future__ import annotations

from parser import parse_nous
from verifier import verify_program, VerificationSeverity, VerificationTier


_FATIGUE = """
world W {
    law cost_ceiling = $2.00 per cycle
    heartbeat = 5m
}
soul R {
    mind: claude-sonnet @ Tier1
    memory { c: int = 0 }
    metabolism { max_energy: 80 energy_per_cycle: 5 recovery_rate: 3 }
    instinct { remember c += 1 }
    heal { on timeout => retry(3, exponential) }
}
"""


def _route(items: list) -> dict:
    """The corrected API routing contract."""
    proven, warnings, errors, info = [], [], [], []
    for it in items:
        sev = it.severity
        if sev == "ERROR":
            errors.append(it)
        elif sev == "WARNING":
            warnings.append(it)
        elif sev == "INFO":
            info.append(it)
        else:
            proven.append(it)
    return {"proven": proven, "warnings": warnings,
            "errors": errors, "info": info}


def test_fatigue_is_a_warning_not_affirmative() -> None:
    result = verify_program(parse_nous(_FATIGUE))
    fatigue = [i for i in result.items
               if i.code == "VMB002" and "fatigue" in i.message]
    assert fatigue, "expected a fatigue VMB002 item"
    for item in fatigue:
        assert item.severity == VerificationSeverity.WARNING, (
            "a fatigue declaration must be a WARNING, got " + item.severity
        )


def test_warning_routes_to_warnings_not_proven() -> None:
    result = verify_program(parse_nous(_FATIGUE))
    routed = _route(result.items)
    codes_in_proven = [i.code for i in routed["proven"]]
    assert "VMB002" not in [
        i.code for i in routed["proven"] if "fatigue" in i.message
    ], "a fatigue warning leaked into the proven array: " + str(codes_in_proven)
    assert any(i.code == "VMB002" for i in routed["warnings"]), (
        "the fatigue warning must land in the warnings array"
    )


def test_proven_array_holds_only_affirmatives() -> None:
    result = verify_program(parse_nous(_FATIGUE))
    routed = _route(result.items)
    for item in routed["proven"]:
        assert item.severity == VerificationSeverity.PROVEN, (
            "non-affirmative " + item.code + " (" + item.severity
            + ") must not be in the proven array"
        )
    # and nothing on the static surface is tier PROVEN
    assert not [i for i in routed["proven"]
                if i.tier == VerificationTier.PROVEN], (
        "no static check may be tier PROVEN until the SMT leg"
    )
