"""End-to-end tests for governance lint v2.

__governance_lint_tests_v2__
"""
from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from governance_lint import (
    GovernanceLinter,
    LintIssue,
    LintReport,
    lint_cli,
    render_json,
    render_text,
    VALID_ACTIONS,
    KNOWN_KINDS,
)


@dataclass
class _StubPolicy:
    """Mimics PolicyNode attributes (not PolicyInfo)."""
    name: str
    kind: str = "llm.request"
    signal: object = "cost > 0.5"
    weight: float = 5.0
    window: int = 0
    action: str = "log_only"
    inject_as: Optional[str] = None
    message: Optional[str] = None
    description: str = ""


PASSED: list[str] = []
FAILED: list[tuple[str, str]] = []


def _check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASSED.append(label)
    else:
        FAILED.append((label, detail))


def test_empty_file_warns() -> None:
    linter = GovernanceLinter()
    report = linter._lint_policies([], "test.nous")
    _check(
        "empty_file_warns",
        len(report.warnings) == 1 and report.warnings[0].rule == "L009",
        f"issues={report.issues}",
    )


def test_duplicate_names_error() -> None:
    linter = GovernanceLinter()
    policies = [
        _StubPolicy(name="dup"),
        _StubPolicy(name="dup"),
    ]
    report = linter._lint_policies(policies, "")
    dup_errors = [i for i in report.errors if i.rule == "L001"]
    _check(
        "duplicate_names_error",
        len(dup_errors) == 1 and dup_errors[0].policy == "dup",
        f"errors={report.errors}",
    )


def test_empty_name_error() -> None:
    linter = GovernanceLinter()
    report = linter._lint_policies([_StubPolicy(name="")], "")
    l002 = [i for i in report.errors if i.rule == "L002"]
    _check("empty_name_error", len(l002) == 1, f"issues={report.issues}")


def test_invalid_action_error() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(name="bad", action="warn")  # 'warn' is NOT valid in NOUS
    report = linter._lint_policies([pol], "")
    l003 = [i for i in report.errors if i.rule == "L003"]
    _check("invalid_action_error", len(l003) == 1, f"issues={report.issues}")


def test_action_intervene_valid() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(name="p", action="intervene")
    report = linter._lint_policies([pol], "")
    l003 = [i for i in report.errors if i.rule == "L003"]
    _check("action_intervene_ok", len(l003) == 0, f"errors={report.errors}")


def test_action_abort_cycle_valid() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(name="p", action="abort_cycle")
    report = linter._lint_policies([pol], "")
    l003 = [i for i in report.errors if i.rule == "L003"]
    _check("action_abort_cycle_ok", len(l003) == 0, f"errors={report.errors}")


def test_weight_zero_error() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(name="zero", weight=0.0)
    report = linter._lint_policies([pol], "")
    l004 = [i for i in report.errors if i.rule == "L004"]
    _check("weight_zero_error", len(l004) == 1, f"issues={report.issues}")


def test_weight_over_ten_error() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(name="high", weight=11.0)
    report = linter._lint_policies([pol], "")
    l004 = [i for i in report.errors if i.rule == "L004"]
    _check("weight_over_ten", len(l004) == 1, f"issues={report.issues}")


def test_weight_ten_ok() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(name="max", weight=10.0)
    report = linter._lint_policies([pol], "")
    l004 = [i for i in report.errors if i.rule == "L004"]
    _check("weight_ten_ok", len(l004) == 0, f"errors={report.errors}")


def test_weight_negative_error() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(name="neg", weight=-0.1)
    report = linter._lint_policies([pol], "")
    l004 = [i for i in report.errors if i.rule == "L004"]
    _check("weight_negative", len(l004) == 1, f"issues={report.issues}")


def test_empty_signal_error() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(name="nosig", signal="")
    report = linter._lint_policies([pol], "")
    l006 = [i for i in report.errors if i.rule == "L006"]
    _check("empty_signal_error", len(l006) == 1, f"issues={report.issues}")


def test_none_signal_error() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(name="nosig", signal=None)
    report = linter._lint_policies([pol], "")
    l006 = [i for i in report.errors if i.rule == "L006"]
    _check("none_signal_error", len(l006) == 1, f"issues={report.issues}")


def test_signal_true_info() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(name="always", signal=True)
    report = linter._lint_policies([pol], "")
    l012 = [i for i in report.infos if i.rule == "L012"]
    _check("signal_true_info", len(l012) == 1, f"issues={report.issues}")


def test_signal_false_warn() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(name="never", signal=False)
    report = linter._lint_policies([pol], "")
    l012 = [i for i in report.warnings if i.rule == "L012"]
    _check("signal_false_warn", len(l012) == 1, f"issues={report.issues}")


def test_unknown_kind_info() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(name="weird", kind="unicorn.hoof")
    report = linter._lint_policies([pol], "")
    l007 = [i for i in report.infos if i.rule == "L007"]
    _check("unknown_kind_info", len(l007) == 1, f"issues={report.issues}")


def test_known_kind_llm_request_ok() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(name="p", kind="llm.request")
    report = linter._lint_policies([pol], "")
    l007 = [i for i in report.infos if i.rule == "L007"]
    _check("known_kind_no_info", len(l007) == 0, f"infos={report.infos}")


def test_reserved_prefix_warns() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(name="__internal")
    report = linter._lint_policies([pol], "")
    l010 = [i for i in report.warnings if i.rule == "L010"]
    _check("reserved_prefix_warn", len(l010) == 1, f"issues={report.issues}")


def test_inject_without_message_error() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(name="bad_inj", action="inject_message", message=None)
    report = linter._lint_policies([pol], "")
    l008 = [i for i in report.errors if i.rule == "L008"]
    _check("inject_no_message", len(l008) == 1, f"issues={report.issues}")


def test_inject_with_message_ok() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(
        name="good_inj",
        action="inject_message",
        message="stay safe",
        inject_as="system",
    )
    report = linter._lint_policies([pol], "")
    l008 = [i for i in report.errors if i.rule == "L008"]
    _check("inject_with_message_ok", len(l008) == 0, f"errors={report.errors}")


def test_inject_empty_message_error() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(name="bad_inj2", action="inject_message", message="   ")
    report = linter._lint_policies([pol], "")
    l008 = [i for i in report.errors if i.rule == "L008"]
    _check("inject_empty_message", len(l008) == 1, f"issues={report.issues}")


def test_negative_window_error() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(name="neg_w", window=-1)
    report = linter._lint_policies([pol], "")
    l011 = [i for i in report.errors if i.rule == "L011"]
    _check("negative_window_error", len(l011) == 1, f"issues={report.issues}")


def test_clean_policy_no_issues() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(
        name="clean_policy",
        kind="llm.request",
        signal="cost > 0.05",
        weight=3.0,
        window=0,
        action="log_only",
    )
    report = linter._lint_policies([pol], "")
    _check(
        "clean_policy_no_issues",
        len(report.issues) == 0,
        f"unexpected: {report.issues}",
    )


def test_clean_inject_policy_no_issues() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(
        name="safety",
        kind="llm.request",
        signal="cost > 0.0",
        weight=5.0,
        action="inject_message",
        inject_as="system",
        message="Follow safety guidelines.",
    )
    report = linter._lint_policies([pol], "")
    _check(
        "clean_inject_policy",
        len(report.issues) == 0,
        f"unexpected: {report.issues}",
    )


def test_has_errors_property() -> None:
    linter = GovernanceLinter()
    bad = _StubPolicy(name="bad", action="bogus")
    good = _StubPolicy(name="good")
    r1 = linter._lint_policies([bad], "")
    r2 = linter._lint_policies([good], "")
    _check(
        "has_errors_property",
        r1.has_errors is True and r2.has_errors is False,
        f"r1={r1.errors} r2={r2.errors}",
    )


def test_to_dict_serialization() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(name="x", signal="")
    report = linter._lint_policies([pol], "file.nous")
    d = report.to_dict()
    ok = (
        d["source_file"] == "file.nous"
        and d["policy_count"] == 1
        and d["error_count"] >= 1
        and isinstance(d["issues"], list)
    )
    _check("to_dict_serialization", ok, f"dict={d}")


def test_render_text_with_errors() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(name="bad", action="nope")
    report = linter._lint_policies([pol], "/tmp/x.nous")
    text = render_text(report)
    ok = "Lint:" in text and "ERR" in text and "L003" in text
    _check("render_text_errors", ok, f"text={text!r}")


def test_render_text_clean() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(name="ok")
    report = linter._lint_policies([pol], "/tmp/x.nous")
    text = render_text(report)
    ok = "OK" in text and "no issues" in text
    _check("render_text_clean", ok, f"text={text!r}")


def test_render_json_valid() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(name="x", signal="")
    report = linter._lint_policies([pol], "f")
    js = render_json(report)
    try:
        parsed = json.loads(js)
        ok = parsed["policy_count"] == 1 and len(parsed["issues"]) >= 1
    except json.JSONDecodeError:
        ok = False
    _check("render_json_valid", ok, f"json={js!r}")


def test_file_not_found() -> None:
    linter = GovernanceLinter()
    report = linter.lint_file("/tmp/__nonexistent_policy_xyz__.nous")
    l000 = [i for i in report.errors if i.rule == "L000"]
    _check("file_not_found", len(l000) == 1 and report.has_errors, f"issues={report.issues}")


def test_lint_cli_empty_exit_codes() -> None:
    fd = tempfile.NamedTemporaryFile(mode="w", suffix=".nous", delete=False, encoding="utf-8")
    fd.write("")
    fd.close()
    try:
        code = lint_cli(fd.name, output_format="text", strict=False)
        _check("cli_empty_non_strict_zero", code == 0, f"code={code}")
        code_strict = lint_cli(fd.name, output_format="text", strict=True)
        _check("cli_empty_strict_one", code_strict == 1, f"code={code_strict}")
    finally:
        Path(fd.name).unlink(missing_ok=True)


def test_multiple_rules_one_policy() -> None:
    linter = GovernanceLinter()
    pol = _StubPolicy(
        name="",
        signal=None,
        weight=15.0,
        action="nope",
        window=-5,
    )
    report = linter._lint_policies([pol], "")
    rules = {i.rule for i in report.issues}
    ok = {"L002", "L003", "L004", "L006", "L011"}.issubset(rules)
    _check("multiple_rules_one_policy", ok, f"rules={rules}")


def test_integration_parse_real_source() -> None:
    """Lint actual .nous source via full parse_nous() pipeline."""
    source = (
        'world InjectDemo {\n'
        '    heartbeat = 1s\n'
        '    policy SafetyGuard {\n'
        '        kind: "llm.request"\n'
        '        signal: cost > 0.0\n'
        '        weight: 5.0\n'
        '        action: inject_message\n'
        '        inject_as: system\n'
        '        message: "Follow safety guidelines at all times."\n'
        '    }\n'
        '    policy BlockCost {\n'
        '        kind: "llm.request"\n'
        '        signal: cost > 0.05\n'
        '        weight: 3.0\n'
        '        action: block\n'
        '    }\n'
        '}\n'
        'soul S {\n'
        '    mind: test @ Tier0A\n'
        '    senses: [http_get]\n'
        '    memory { x: int = 0 }\n'
        '    instinct { let y = x + 1 }\n'
        '}\n'
    )
    linter = GovernanceLinter()
    report = linter.lint_source(source, source_file="<integration>")
    ok_count = report.policy_count == 2
    ok_clean = not report.has_errors
    _check(
        "integration_parse_two_clean_policies",
        ok_count and ok_clean,
        f"policy_count={report.policy_count} errors={report.errors} issues={report.issues}",
    )


def test_integration_parse_detects_inject_without_message() -> None:
    """Real source with inject_message policy missing message field -> L008 error."""
    source = (
        'world BadInject {\n'
        '    heartbeat = 1s\n'
        '    policy NoMsg {\n'
        '        kind: "llm.request"\n'
        '        signal: cost > 0.0\n'
        '        weight: 5.0\n'
        '        action: inject_message\n'
        '    }\n'
        '}\n'
        'soul S {\n'
        '    mind: test @ Tier0A\n'
        '    senses: [http_get]\n'
        '    memory { x: int = 0 }\n'
        '    instinct { let y = x + 1 }\n'
        '}\n'
    )
    linter = GovernanceLinter()
    report = linter.lint_source(source, source_file="<integration-bad>")
    l008 = [i for i in report.errors if i.rule == "L008"]
    _check(
        "integration_detects_missing_message",
        len(l008) == 1 and report.has_errors,
        f"errors={report.errors}",
    )


def test_integration_parse_error_is_l100() -> None:
    linter = GovernanceLinter()
    report = linter.lint_source("this is not valid nous source")
    l100 = [i for i in report.errors if i.rule == "L100"]
    _check("integration_parse_error", len(l100) == 1, f"errors={report.errors}")


def test_valid_actions_constant() -> None:
    expected = {"log_only", "intervene", "block", "abort_cycle", "inject_message"}
    _check(
        "valid_actions_constant",
        set(VALID_ACTIONS) == expected,
        f"got={set(VALID_ACTIONS)}",
    )


def test_known_kinds_constant() -> None:
    must_have = {"llm.request", "sense.invoke", "memory.write", "governance.intervention"}
    _check(
        "known_kinds_constant",
        must_have.issubset(set(KNOWN_KINDS)),
        f"got={set(KNOWN_KINDS)}",
    )


# __governance_lint_tests_error_on_v1__
def test_parse_rule_codes_empty() -> None:
    from governance_lint import _parse_rule_codes
    _check("parse_empty", _parse_rule_codes("") == frozenset(), "empty")
    _check("parse_none", _parse_rule_codes(None) == frozenset(), "none")


def test_parse_rule_codes_single() -> None:
    from governance_lint import _parse_rule_codes
    got = _parse_rule_codes("L010")
    _check("parse_single", got == frozenset({"L010"}), f"got={got}")


def test_parse_rule_codes_multiple_with_whitespace() -> None:
    from governance_lint import _parse_rule_codes
    got = _parse_rule_codes(" L010 , L007 ")
    _check("parse_multiple", got == frozenset({"L010", "L007"}), f"got={got}")


def test_parse_rule_codes_lowercase_accepted() -> None:
    from governance_lint import _parse_rule_codes
    got = _parse_rule_codes("l012")
    _check("parse_lower", got == frozenset({"L012"}), f"got={got}")


def test_parse_rule_codes_invalid_raises() -> None:
    from governance_lint import _parse_rule_codes
    try:
        _parse_rule_codes("L999")
        _check("parse_invalid", False, "expected ValueError")
    except ValueError:
        _check("parse_invalid", True, "")


def test_lint_cli_error_on_elevates_warning() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".nous", delete=False) as fd:
        fd.write("")
        path = fd.name
    try:
        code_plain = lint_cli(path, output_format="text", strict=False)
        code_elev = lint_cli(path, output_format="text", strict=False, error_on="L009")
        _check("cli_elev_plain_zero", code_plain == 0, f"plain={code_plain}")
        _check("cli_elev_promoted_one", code_elev == 1, f"elev={code_elev}")
    finally:
        Path(path).unlink()


def test_lint_cli_error_on_no_match_exit_zero() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".nous", delete=False) as fd:
        fd.write("")
        path = fd.name
    try:
        code = lint_cli(path, output_format="text", strict=False, error_on="L010")
        _check("cli_elev_no_match", code == 0, f"code={code}")
    finally:
        Path(path).unlink()


def test_lint_cli_error_on_invalid_code_exit_two() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".nous", delete=False) as fd:
        fd.write("")
        path = fd.name
    try:
        code = lint_cli(path, output_format="text", strict=False, error_on="L999")
        _check("cli_elev_invalid", code == 2, f"code={code}")
    finally:
        Path(path).unlink()


def test_lint_cli_error_on_accepts_frozenset() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".nous", delete=False) as fd:
        fd.write("")
        path = fd.name
    try:
        code = lint_cli(path, output_format="text", strict=False, error_on=frozenset({"L009"}))
        _check("cli_elev_frozenset", code == 1, f"code={code}")
    finally:
        Path(path).unlink()


def test_valid_rule_codes_constant() -> None:
    from governance_lint import VALID_RULE_CODES
    expected = {"L000", "L001", "L002", "L003", "L004", "L006", "L007",
                "L008", "L009", "L010", "L011", "L012", "L100"}
    _check("valid_rule_codes", set(VALID_RULE_CODES) == expected, f"got={set(VALID_RULE_CODES)}")


def run_all() -> int:
    tests = [
        test_empty_file_warns,
        test_duplicate_names_error,
        test_empty_name_error,
        test_invalid_action_error,
        test_action_intervene_valid,
        test_action_abort_cycle_valid,
        test_weight_zero_error,
        test_weight_over_ten_error,
        test_weight_ten_ok,
        test_weight_negative_error,
        test_empty_signal_error,
        test_none_signal_error,
        test_signal_true_info,
        test_signal_false_warn,
        test_unknown_kind_info,
        test_known_kind_llm_request_ok,
        test_reserved_prefix_warns,
        test_inject_without_message_error,
        test_inject_with_message_ok,
        test_inject_empty_message_error,
        test_negative_window_error,
        test_clean_policy_no_issues,
        test_clean_inject_policy_no_issues,
        test_has_errors_property,
        test_to_dict_serialization,
        test_render_text_with_errors,
        test_render_text_clean,
        test_render_json_valid,
        test_file_not_found,
        test_lint_cli_empty_exit_codes,
        test_multiple_rules_one_policy,
        test_integration_parse_real_source,
        test_integration_parse_detects_inject_without_message,
        test_integration_parse_error_is_l100,
        test_valid_actions_constant,
        test_known_kinds_constant,
        # __governance_lint_tests_run_all_error_on_v1__
        test_parse_rule_codes_empty,
        test_parse_rule_codes_single,
        test_parse_rule_codes_multiple_with_whitespace,
        test_parse_rule_codes_lowercase_accepted,
        test_parse_rule_codes_invalid_raises,
        test_lint_cli_error_on_elevates_warning,
        test_lint_cli_error_on_no_match_exit_zero,
        test_lint_cli_error_on_invalid_code_exit_two,
        test_lint_cli_error_on_accepts_frozenset,
        test_valid_rule_codes_constant,
    ]
    for t in tests:
        try:
            t()
        except Exception as exc:
            FAILED.append((t.__name__, f"exception: {exc!r}"))

    total = len(PASSED) + len(FAILED)
    if FAILED:
        print("=" * 60)
        print(f"GOVERNANCE LINT TESTS -- FAILED ({len(FAILED)}/{total})")
        for name, detail in FAILED:
            print(f"  FAIL {name}: {detail}")
        print("=" * 60)
        return 1
    print("=" * 60)
    print(f"GOVERNANCE LINT TESTS -- ALL GREEN ({len(PASSED)}/{total})")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
