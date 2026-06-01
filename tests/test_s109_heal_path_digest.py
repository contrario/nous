"""S109 U1 -- known-answer tests for the heal-path digest producer.

Parses real heal blocks through the live parser so the projection is validated
against the actual AST, not hand-built nodes. Covers the sealed C-conditions:
  C1  producer preimage == exact hand-built JCS bytes (mode="json", coerced)
  C2  ensure_ascii default True, separators (",",":") -- house alignment; a
      non-ASCII error_type escapes to \\uXXXX and the preimage is pure ASCII
  C3  shape + leaf-type invariant: dumped key sets are exactly as enumerated AND
      no unquoted float survives anywhere in the preimage
  C4  action-order sensitivity
plus: determinism, reformatting-invariance (0.10 == 0.1), distinct delta ->
distinct digest, int/float canonical decimal string (1000 -> "1000", not E+3),
bool refusal, numeric-outside-params refusal.
"""
from __future__ import annotations

import json
import re

import pytest

from ast_nodes import (
    HealActionNode,
    HealPathProjectionError,
    HealRuleNode,
    HealStrategy,
    heal_path_digest,
    heal_path_preimage_bytes,
)
from parser import parse_nous


def _heal_rules(program: object) -> list[HealRuleNode]:
    found: list[HealRuleNode] = []

    def walk(node: object) -> None:
        if isinstance(node, HealRuleNode):
            found.append(node)
        for attr in getattr(type(node), "model_fields", {}):
            value = getattr(node, attr, None)
            items = value if isinstance(value, list) else [value]
            for item in items:
                if hasattr(type(item), "model_fields"):
                    walk(item)

    walk(program)
    return found


def _soul(heal_body: str) -> str:
    return (
        "soul S {\n"
        "    mind: gpt-4o@Tier1\n"
        "    heal {\n"
        + heal_body
        + "\n    }\n"
        "}\n"
    )


def _one_rule(heal_body: str) -> HealRuleNode:
    rules = _heal_rules(parse_nous(_soul(heal_body)))
    assert len(rules) == 1
    return rules[0]


def test_c1_preimage_byte_identical_to_hand_built_jcs() -> None:
    rule = _one_rule("        on hallucination => lower(temperature, 0.1)")
    expected = json.dumps(
        {
            "error_type": "hallucination",
            "actions": [
                {
                    "strategy": "lower",
                    "params": {"param": "temperature", "delta": "0.1"},
                }
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert heal_path_preimage_bytes(rule) == expected


def test_determinism() -> None:
    rule = _one_rule("        on timeout => retry(3, exponential)")
    assert heal_path_digest(rule) == heal_path_digest(rule)


def test_reformatting_invariance_trailing_zero() -> None:
    a = _one_rule("        on e => lower(x, 0.1)")
    b = _one_rule("        on e => lower(x, 0.10)")
    assert heal_path_digest(a) == heal_path_digest(b)


def test_distinct_delta_distinct_digest() -> None:
    a = _one_rule("        on e => lower(x, 0.1)")
    b = _one_rule("        on e => lower(x, 0.2)")
    assert heal_path_digest(a) != heal_path_digest(b)


def test_c4_action_order_sensitivity() -> None:
    forward = HealRuleNode(
        error_type="e",
        actions=[
            HealActionNode(strategy=HealStrategy.RETRY, params={"max": 1}),
            HealActionNode(strategy=HealStrategy.ALERT, params={"target": "ops"}),
        ],
    )
    reverse = HealRuleNode(
        error_type="e",
        actions=[
            HealActionNode(strategy=HealStrategy.ALERT, params={"target": "ops"}),
            HealActionNode(strategy=HealStrategy.RETRY, params={"max": 1}),
        ],
    )
    assert heal_path_digest(forward) != heal_path_digest(reverse)


def test_int_delta_canonical_no_e_notation() -> None:
    rule = HealRuleNode(
        error_type="e",
        actions=[
            HealActionNode(
                strategy=HealStrategy.LOWER, params={"param": "x", "delta": 1000}
            )
        ],
    )
    preimage = heal_path_preimage_bytes(rule).decode("utf-8")
    assert '"1000"' in preimage
    assert "E+" not in preimage
    assert "1e" not in preimage.lower()


def test_distinct_error_type_distinct_digest() -> None:
    a = _one_rule("        on timeout => retry(1, exponential)")
    b = _one_rule("        on api_error => retry(1, exponential)")
    assert heal_path_digest(a) != heal_path_digest(b)


def test_bool_under_params_refused() -> None:
    rule = HealRuleNode(
        error_type="e",
        actions=[
            HealActionNode(
                strategy=HealStrategy.LOWER, params={"param": "x", "delta": True}
            )
        ],
    )
    with pytest.raises(HealPathProjectionError):
        heal_path_preimage_bytes(rule)


def test_c3_no_unquoted_float_survives() -> None:
    rule = _one_rule("        on hallucination => lower(temperature, 0.1)")
    preimage = heal_path_preimage_bytes(rule).decode("utf-8")
    assert re.search(r"[:\[,]\s*-?\d+\.\d+", preimage) is None


def test_c3_shape_invariant_rule_keys() -> None:
    rule = _one_rule("        on e => retry(1, exponential)")
    dumped = rule.model_dump(mode="json")
    assert set(dumped.keys()) == {"error_type", "actions"}
    assert set(dumped["actions"][0].keys()) == {"strategy", "params"}


def test_c2_ensure_ascii_default_true_non_ascii_escaped() -> None:
    rule = HealRuleNode(
        error_type="\u03b8\u03b5\u03c1\u03b1\u03c0\u03b5\u03af\u03b1",
        actions=[HealActionNode(strategy=HealStrategy.RETRY, params={"max": 1})],
    )
    preimage = heal_path_preimage_bytes(rule)
    decoded = preimage.decode("ascii")
    assert "\\u03b8" in decoded


def test_numeric_outside_params_refused() -> None:
    from ast_nodes import _s109_normalize_projection

    with pytest.raises(HealPathProjectionError):
        _s109_normalize_projection(
            {"error_type": 5, "actions": []}, under_params=False
        )


def test_requires_heal_rule_node() -> None:
    with pytest.raises(HealPathProjectionError):
        heal_path_preimage_bytes("not a node")
