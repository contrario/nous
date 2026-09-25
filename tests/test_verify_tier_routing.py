"""Regression for the warning-as-proven leak (1b-fix).

A fatigue declaration emits VMB002 as a WARNING, not an affirmative finding.
It must never carry severity PROVEN, and the API router must send WARNING to
warnings (not proven) and INFO to info. This pins the routing contract so the
"WARN" vs "WARNING" typo cannot reappear.

S378 (docs/RESERVED_VERB_AUDIT_DESIGN.md 9.3, D378-4 and D378-10): the
served body is schema_version 2. A passing item (severity PROVEN) goes to
"proven" only when its tier is PROVEN and to "evidenced" otherwise, and a
severity the router does not know is refused. The routing copy below is
amended to that contract, not deleted; the route itself is checked by
tests/test_s378_verify_v2_body.py.
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
    """The API routing contract, schema_version 2 (S378)."""
    proven, evidenced, warnings, errors, info = [], [], [], [], []
    for it in items:
        sev = it.severity
        if sev == "ERROR":
            errors.append(it)
        elif sev == "WARNING":
            warnings.append(it)
        elif sev == "INFO":
            info.append(it)
        elif sev == "PROVEN":
            if it.tier == VerificationTier.PROVEN:
                proven.append(it)
            else:
                evidenced.append(it)
        else:
            raise ValueError("unknown verifier severity: " + repr(sev))
    return {"proven": proven, "evidenced": evidenced, "warnings": warnings,
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
    affirmative = routed["proven"] + routed["evidenced"]
    codes_in_proven = [i.code for i in affirmative]
    assert "VMB002" not in [
        i.code for i in affirmative if "fatigue" in i.message
    ], "a fatigue warning leaked into the passing arrays: " + str(codes_in_proven)
    assert any(i.code == "VMB002" for i in routed["warnings"]), (
        "the fatigue warning must land in the warnings array"
    )


def test_proven_array_holds_only_affirmatives() -> None:
    result = verify_program(parse_nous(_FATIGUE))
    routed = _route(result.items)
    for item in routed["proven"] + routed["evidenced"]:
        assert item.severity == VerificationSeverity.PROVEN, (
            "non-affirmative " + item.code + " (" + item.severity
            + ") must not be in a passing array"
        )
    # and nothing on the static surface is tier PROVEN
    assert routed["proven"] == [], (
        "no static check may be tier PROVEN until the SMT leg"
    )
    assert not [i for i in routed["evidenced"]
                if i.tier == VerificationTier.PROVEN], (
        "a tier PROVEN item was routed to evidenced"
    )
