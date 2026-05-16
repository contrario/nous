"""
Tests for skill_md.py Pydantic V2 schema layer.
# __session77_skill_md_tests_v1__
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from skill_md import (
    MoneyAmount,
    NousSidecar,
    NousToolSpec,
    SkillMDFrontmatter,
)


def test_money_amount_parse_eur() -> None:
    m = MoneyAmount.parse("0.50EUR")
    assert m.amount == 0.5
    assert m.currency == "EUR"


def test_money_amount_parse_usd_integer() -> None:
    m = MoneyAmount.parse("5USD")
    assert m.amount == 5.0
    assert m.currency == "USD"


def test_money_amount_parse_rejects_lowercase_currency() -> None:
    with pytest.raises((ValueError, ValidationError)):
        MoneyAmount.parse("0.50eur")


def test_money_amount_parse_rejects_missing_currency() -> None:
    with pytest.raises((ValueError, ValidationError)):
        MoneyAmount.parse("0.50")


def test_money_amount_frozen() -> None:
    m = MoneyAmount.parse("1USD")
    with pytest.raises((ValidationError, TypeError, AttributeError)):
        m.amount = 2.0  # type: ignore[misc]


def test_tool_spec_rejects_zero_input_and_output() -> None:
    with pytest.raises(ValidationError):
        NousToolSpec(
            name="t", max_calls=1, input_tokens=0, output_tokens=0,
        )


def test_tool_spec_rejects_negative_max_calls() -> None:
    with pytest.raises(ValidationError):
        NousToolSpec(
            name="t", max_calls=0, input_tokens=10, output_tokens=10,
        )


def test_sidecar_requires_spec_version_one_zero() -> None:
    with pytest.raises(ValidationError):
        NousSidecar.model_validate({
            "spec_version": "2.0",
            "cost_cap": "0.50USD",
            "tools": [{
                "name": "t", "max_calls": 1,
                "input_tokens": 10, "output_tokens": 10,
            }],
        })


def test_sidecar_rejects_duplicate_tool_names() -> None:
    with pytest.raises(ValidationError):
        NousSidecar.model_validate({
            "spec_version": "1.0",
            "cost_cap": "0.50USD",
            "tools": [
                {
                    "name": "t", "max_calls": 1,
                    "input_tokens": 10, "output_tokens": 10,
                },
                {
                    "name": "t", "max_calls": 2,
                    "input_tokens": 20, "output_tokens": 20,
                },
            ],
        })


def test_sidecar_coerces_string_cost_cap() -> None:
    s = NousSidecar.model_validate({
        "spec_version": "1.0",
        "cost_cap": "0.50EUR",
        "tools": [{
            "name": "t", "max_calls": 1,
            "input_tokens": 10, "output_tokens": 10,
        }],
    })
    assert isinstance(s.cost_cap, MoneyAmount)
    assert s.cost_cap.currency == "EUR"


def test_sidecar_requires_at_least_one_tool() -> None:
    with pytest.raises(ValidationError):
        NousSidecar.model_validate({
            "spec_version": "1.0",
            "cost_cap": "0.50USD",
            "tools": [],
        })


def test_frontmatter_name_kebab_case_regex() -> None:
    SkillMDFrontmatter.model_validate({
        "name": "research-agent",
        "description": "Searches papers.",
    })
    with pytest.raises(ValidationError):
        SkillMDFrontmatter.model_validate({
            "name": "Research_Agent",
            "description": "Searches papers.",
        })


def test_frontmatter_ignores_vendor_extensions() -> None:
    fm = SkillMDFrontmatter.model_validate({
        "name": "research-agent",
        "description": "Searches papers.",
        "context": "fork",
        "disable-model-invocation": True,
    })
    assert fm.name == "research-agent"
