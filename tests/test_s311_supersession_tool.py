"""S311 tests for scripts/check_glm_supersession.py: the token set is
one set in two files, and every output line carries a separator.

scripts/ is not a package, so the tool is loaded by file path, in the
shape already used by tests/test_s297_glm_ceremony.py:23-34. The
fixture is imported as a sibling test module: the fixture remains the
sole authority for the token set and if the two disagree the TOOL is
wrong (D310-5(b)). The sibling import is a NEW convention here: no
tracked test imported that module before this file, and it resolves
because pytest places tests/ on sys.path, measured in S311 with a
negative control that fails the import when it is not there.

The field-splitting control is driven over the tool's LABELS, NOT over
the output of one execution. Five of the thirteen labels are emitted
only when a predecessor was fetched, so an output-driven control never
reaches the two that carried FG-S310-L and would pass green while the
defect stood (D311-2(b)).

__s311_supersession_tool_tests_v1__
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import test_s309_supersession_cases as _fixture

_REPO = Path(__file__).resolve().parents[1]
_TOOL = _REPO / "scripts" / "check_glm_supersession.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("_s311_tool", _TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _call_site_labels() -> list[str]:
    """Every literal passed as the first argument of a _print call."""
    tree = ast.parse(_TOOL.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "_print":
            continue
        assert node.args, "a _print call with no arguments"
        first = node.args[0]
        assert isinstance(first, ast.Constant) and isinstance(
            first.value, str
        ), "a _print label that is not a string literal"
        out.append(first.value)
    return out


def test_the_fixture_imported_is_the_one_in_this_repository() -> None:
    """A set that agrees because the import found some other module of
    the same name is a pass with nothing behind it. The equality below
    means nothing until the identity of its right-hand side is fixed.
    """
    assert Path(_fixture.__file__).resolve() == (
        _REPO / "tests" / "test_s309_supersession_cases.py"
    ).resolve()


def test_the_token_set_is_the_same_set_in_both_files() -> None:
    tool = _load_tool()
    assert set(tool.TOKENS) == set(_fixture.TOKENS)


def test_the_token_names_are_not_duplicated_within_the_tool() -> None:
    tool = _load_tool()
    assert len(tool.TOKENS) == len(set(tool.TOKENS))


def test_every_label_renders_a_line_of_at_least_two_fields() -> None:
    tool = _load_tool()
    for label in tool.LABELS:
        line = tool._render(label, "SENTINEL")
        assert len(line.split()) >= 2, label


def test_fg_s310_l_the_two_longest_labels_still_carry_a_separator(
) -> None:
    tool = _load_tool()
    width = max(len(name) for name in tool.LABELS)
    longest = [name for name in tool.LABELS if len(name) == width]
    assert longest, "LABELS is empty"
    for label in longest:
        line = tool._render(label, False)
        assert line.split() == [label, "False"], line


def test_the_label_set_covers_every_call_site() -> None:
    tool = _load_tool()
    assert set(_call_site_labels()) == set(tool.LABELS)


def test_the_width_is_computed_and_is_not_written_down() -> None:
    """A literal here passes every value check on the day it is
    written and fails only once a longer label arrives, which is the
    FG-S310-L failure mode restated. The shape is asserted, not the
    value alone.
    """
    tool = _load_tool()
    assert tool._LABEL_WIDTH == max(len(name) for name in tool.LABELS)
    tree = ast.parse(_TOOL.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and (
                target.id == "_LABEL_WIDTH"
            ):
                found.append(node.value)
    assert len(found) == 1, "_LABEL_WIDTH is assigned %d times" % len(
        found
    )
    assert not isinstance(found[0], ast.Constant), (
        "_LABEL_WIDTH is a literal; it must be computed from LABELS"
    )
