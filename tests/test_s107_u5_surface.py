"""U5 regressions -- surface threading of consult_memory (S107).

Proves the boolean is plumbed from the surfaces to the engines: the API request
model carries it, and execute_program / run_program / run_compiled_with_trace all
accept it defaulting False. Engine behavior + fail-closed gate are U4; the real
chain E2E is U6.

# __s107_u5_tests_v1__
"""
from __future__ import annotations

import inspect

from compiled_trace import run_compiled_with_trace
from nous_api import RunRequest
from nous_ast_runner import execute_program, run_program


def test_runrequest_consult_default_false() -> None:
    assert RunRequest(source="x").consult_memory is False


def test_runrequest_consult_settable() -> None:
    assert RunRequest(source="x", consult_memory=True).consult_memory is True


def test_execute_program_has_consult_param() -> None:
    p = inspect.signature(execute_program).parameters["consult_memory"]
    assert p.default is False


def test_run_program_has_consult_param() -> None:
    p = inspect.signature(run_program).parameters["consult_memory"]
    assert p.default is False


def test_run_compiled_has_consult_param() -> None:
    p = inspect.signature(run_compiled_with_trace).parameters["consult_memory"]
    assert p.default is False
