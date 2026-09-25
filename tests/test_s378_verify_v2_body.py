"""S378: the /v1/verify 200 body, schema_version 2. __s378_verify_v2_contract_v1__

docs/RESERVED_VERB_AUDIT_DESIGN.md 9.3, D378-1 to D378-10. Before S378 the
served "proven" key held every passing item (severity PROVEN) whatever its
tier, so a VERIFIED, ESTIMATED or REPORTED check travelled under the word
reserved for the Z3/Farkas legs. Schema version 2 keeps "proven" for tier
PROVEN only and puts every other passing item under "evidenced", with
severity PASS in both lists.

Route checks (brief section 7): (a) no item with a tier other than PROVEN
in "proven"; (b) no "severity":"PROVEN" anywhere in a 200 body; (c)
"proven" plus "evidenced" equals the verifier's passing items, in order;
(d) schema_version is the first key and equals 2; (e) the validate-branch
shape. Also: the item shape and PASS severity, an unknown severity is
refused, and the non-affirmative lists keep their severity (an invariant
that held before S378 too; its two ids are green on the pre tree). The
validate branch serves no item with a severity, so (b) runs on the complete
bodies only. File checks bind the IDE, the E5 addition of
docs/CLAIM_LINT.md and the CHANGELOG entry.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.usefixtures("dated_shipped_prices")

api_available = importlib.util.find_spec("slowapi") is not None
z3_available = importlib.util.find_spec("z3") is not None
needs_api = pytest.mark.skipif(not api_available, reason="slowapi not installed")
needs_api_z3 = pytest.mark.skipif(
    not (api_available and z3_available), reason="needs slowapi and z3"
)

AML = "aml_transaction_governance.nous"
MIN_WORLD = (
    "world W {\n"
    "    law cost_ceiling = $1.00 per cycle\n"
    "    heartbeat = 5m\n"
    "}\n"
)
SOUL_ONLY = (
    "soul R {\n"
    "    mind: claude-sonnet @ Tier1\n"
    "    memory { c: int = 0 }\n"
    "    instinct { remember c += 1 }\n"
    "    heal { on timeout => retry(3, exponential) }\n"
    "}\n"
)
ITEM_KEYS = ["code", "category", "message", "severity", "tier"]
COMPLETE_KEYS = ["schema_version", "ok", "stage", "proven", "evidenced",
                 "errors", "warnings", "info", "total_checks"]
VALIDATE_KEYS = ["schema_version", "ok", "stage", "proven", "evidenced",
                 "errors", "warnings"]
E5_ROW = (
    '| **E5** | a literal whose entire value is one reserved token is SCHEMA |'
    ' the `PROVEN` enum and the `"proven"` JSON key -- separated mechanically,'
    ' not allowlisted |'
)
E5_ADD_HEAD = '| | E5 on the `/v1/verify` 200 body since `"schema_version": 2` (S378) |'


def _source(name: str) -> str:
    if name == "aml":
        return (ROOT / AML).read_text(encoding="utf-8")
    if name == "min_world":
        return MIN_WORLD
    return SOUL_ONLY


def _post(source: str) -> Any:
    from fastapi.testclient import TestClient
    import nous_api_server as N
    return TestClient(N.app).post("/v1/verify", json={"source": source})


def _passing_from_verifier(source: str) -> list[tuple[str, str, str, Any]]:
    import nous_api_server as N
    from parser import parse_nous
    from verifier import verify_program
    result = verify_program(parse_nous(source), N._get_default_pricing())
    return [(i.code, i.category, i.message, i.tier) for i in result.items
            if i.severity == "PROVEN"]


COMPLETE = [
    pytest.param("aml", marks=needs_api_z3, id="aml"),
    pytest.param("min_world", marks=needs_api, id="min_world"),
]
ALL = COMPLETE + [pytest.param("soul_only", marks=needs_api, id="soul_only")]


@pytest.mark.parametrize("name", ALL)
def test_d_schema_version_is_first_key_and_2(name: str) -> None:
    r = _post(_source(name))
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    keys = list(body.keys())
    assert keys and keys[0] == "schema_version", "first key " + repr(keys[:2])
    assert body["schema_version"] == 2, repr(body["schema_version"])


@pytest.mark.parametrize("name", COMPLETE)
def test_a_proven_holds_tier_proven_only(name: str) -> None:
    body = _post(_source(name)).json()
    wrong = [(i["code"], i["tier"]) for i in body.get("proven", [])
             if i.get("tier") != "PROVEN"]
    assert wrong == [], "items in proven with another tier: " + repr(wrong)


@pytest.mark.parametrize("name", COMPLETE)
def test_b_no_severity_proven_in_a_200_body(name: str) -> None:
    r = _post(_source(name))
    assert r.status_code == 200, r.text[:300]
    n = r.content.count(b'"severity":"PROVEN"')
    assert n == 0, "severity PROVEN occurs " + str(n) + " times in the body"


@pytest.mark.parametrize("name", COMPLETE)
def test_c_proven_plus_evidenced_equals_verifier_passing_items(name: str) -> None:
    source = _source(name)
    body = _post(source).json()
    assert "evidenced" in body, "no evidenced key; keys " + repr(list(body.keys()))
    expected = _passing_from_verifier(source)
    got = [(i["code"], i["category"], i["message"], i["tier"])
           for i in body["proven"] + body["evidenced"]]
    want_proven = [e for e in expected if e[3] == "PROVEN"]
    want_evidenced = [e for e in expected if e[3] != "PROVEN"]
    assert got == want_proven + want_evidenced, (
        "served " + repr([g[0] for g in got]) + " verifier " + repr([e[0] for e in expected]))
    assert [i["code"] for i in body["proven"]] == [e[0] for e in want_proven]
    assert list(body.keys()) == COMPLETE_KEYS, repr(list(body.keys()))


@needs_api
def test_e_validate_branch_shape() -> None:
    r = _post(SOUL_ONLY)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert list(body.keys()) == VALIDATE_KEYS, repr(list(body.keys()))
    assert body["ok"] is False and body["stage"] == "validate"
    assert body["proven"] == [] and body["evidenced"] == []
    assert body["errors"], "the fixture no longer fails validation"


@pytest.mark.parametrize("name", COMPLETE)
def test_item_shape_and_pass_severity(name: str) -> None:
    body = _post(_source(name)).json()
    items = body.get("proven", []) + body.get("evidenced", [])
    assert items, "no passing item served"
    shapes = [list(i.keys()) for i in items if list(i.keys()) != ITEM_KEYS]
    assert shapes == [], repr(shapes)
    sev = sorted({i["severity"] for i in items})
    assert sev == ["PASS"], "severities " + repr(sev)


@needs_api
def test_unknown_severity_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    import nous_api_server as N
    from verifier import VerificationItem, VerificationResult
    real = N.verify_program

    def planted(program: Any, pricing: Any) -> VerificationResult:
        res = real(program, pricing)
        res.items.append(VerificationItem("BOGUS", "VX378", "planted", "planted item"))
        return res

    monkeypatch.setattr(N, "verify_program", planted)
    r = _post(MIN_WORLD)
    assert r.status_code == 422, str(r.status_code) + " " + r.text[:300]
    detail = r.json().get("detail", {})
    assert detail.get("code") == "VERIFY001", repr(detail)
    assert str(detail.get("error", "")).startswith("unknown verifier severity: 'BOGUS'"), repr(detail)


@pytest.mark.parametrize("name", COMPLETE)
def test_non_affirmative_lists_keep_their_severity(name: str) -> None:
    body = _post(_source(name)).json()
    wrong = []
    for key, sev in (("errors", "ERROR"), ("warnings", "WARNING"), ("info", "INFO")):
        for i in body.get(key, []):
            if "severity" in i and i["severity"] != sev:
                wrong.append((key, i.get("code"), i["severity"]))
    assert wrong == [], repr(wrong)


def test_ide_reads_both_shapes_and_drops_the_tier_fallback() -> None:
    text = (ROOT / "website" / "ide.html").read_text(encoding="utf-8")
    has_fallback = "x.tier||'PROVEN'" in text
    reads_v2 = "var _v2=d.schema_version===2;" in text
    reads_evidenced = "(d.proven||[]).concat(d.evidenced||[])" in text
    refuses_other = "Unsupported /v1/verify schema_version" in text
    untiered = "_TIERS.push(['UNTIERED',_U," in text
    assert not has_fallback, "ide.html still counts an untiered item as PROVEN"
    assert reads_v2 and reads_evidenced, "ide.html does not read the v2 shape"
    assert refuses_other, "ide.html does not refuse an unknown schema_version"
    assert untiered, "ide.html has no UNTIERED group"


def test_claim_lint_e5_row_kept_and_addition_below_it() -> None:
    lines = (ROOT / "docs" / "CLAIM_LINT.md").read_text(encoding="utf-8").split("\n")
    idx = [n for n, ln in enumerate(lines) if ln == E5_ROW]
    assert len(idx) == 1, "E5 row occurrences " + str(len(idx))
    below = lines[idx[0] + 1] if idx[0] + 1 < len(lines) else ""
    starts = below.startswith(E5_ADD_HEAD)
    assert starts, "no E5 addition right below the E5 row: " + repr(below[:80])


def test_changelog_unreleased_carries_the_v2_entry() -> None:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    head = text.split("\n## [5.85.1]", 1)[0]
    marker = "<!-- __s378_changelog_verify_v2_v1__ -->"
    in_unreleased = head.count(marker) == 1 and "## [Unreleased]" in head
    names_key = "`evidenced`" in head and '`"schema_version": 2`' in head
    assert in_unreleased, "the S378 entry is not in [Unreleased]"
    assert names_key, "the S378 entry does not name the v2 keys"
