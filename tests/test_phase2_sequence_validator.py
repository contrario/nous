from __future__ import annotations

# __phase2_stage2_events_tests_v1__
# Phase 2 Stage 2: validator for sequence-law event declarations.

from parser import parse_nous
from validator import validate_program


def _validate(src: str):
    return validate_program(parse_nous(src))


def test_phase2_stage2_events_happy_path() -> None:
    r = _validate("world W { law before(a, b) events { a, b } }")
    assert r.ok, r.summary()


def test_phase2_stage2_events_missing_block_with_sequence_laws() -> None:
    r = _validate("world W { law before(a, b) }")
    assert not r.ok
    assert any(e.code == "SE001" for e in r.errors)


def test_phase2_stage2_events_undeclared_before_label() -> None:
    r = _validate("world W { law before(a, b) events { b } }")
    assert not r.ok
    se002 = [e for e in r.errors if e.code == "SE002"]
    assert len(se002) == 1
    assert "'a'" in se002[0].message


def test_phase2_stage2_events_undeclared_after_label() -> None:
    r = _validate("world W { law before(a, b) events { a } }")
    assert not r.ok
    se002 = [e for e in r.errors if e.code == "SE002"]
    assert len(se002) == 1
    assert "'b'" in se002[0].message


def test_phase2_stage2_events_both_undeclared() -> None:
    r = _validate("world W { law before(a, b) events { x, y } }")
    assert not r.ok
    se002 = [e for e in r.errors if e.code == "SE002"]
    assert len(se002) == 2


def test_phase2_stage2_events_duplicate_in_block() -> None:
    r = _validate("world W { law before(a, b) events { a, a, b } }")
    assert not r.ok
    assert any(e.code == "SE003" for e in r.errors)


def test_phase2_stage2_events_multi_law_shared_alphabet() -> None:
    r = _validate(
        "world W { law before(a, b) law before(b, c) events { a, b, c } }"
    )
    assert r.ok, r.summary()
