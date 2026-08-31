"""The wheel content gate is the only phase that decides which modules
must be inside the artifact that leaves the house. Before S339 nothing in
the tree named it: the string phase_wheel_gate occurred only inside the
file that defines it, and no test called it or read it.

This file does not change the release path. It reads scripts/release.py
as a syntax tree, never importing it, and binds three properties of the
required list:

  the list is extractable exactly once, as a literal list of strings
  every python member of it is declared in pyproject py-modules
  the list does not shrink below a floor, a one way ratchet

The floor lives here for the same reason PYTEST_FLOOR lives in the
release script: it is a ratchet, not a second registration of the set.
Raise it when the list grows. Never lower it.

WHAT THIS FILE DOES NOT DO. It does not open a wheel. It says nothing
about what any built archive contains. The satisfaction rule written in
the gate matches an archive entry by suffix, so five of the required
names cannot be satisfied independently of another required name; that
is recorded in D339 and is not repaired here.
"""

import ast
import tomllib
from pathlib import Path

import pytest

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
RELEASE_PY: Path = REPO_ROOT / "scripts" / "release.py"
PYPROJECT: Path = REPO_ROOT / "pyproject.toml"

GATE_FUNC: str = "phase_wheel_gate"
GATE_LIST: str = "required"

# One way ratchet. Raise with the list, never lower.
REQUIRED_FLOOR: int = 74  # __s339_wheelgate_required_floor_74__


class ExtractionRefused(Exception):
    """The list could not be read under the shape this file declares."""


def _target_names(node: ast.AST) -> list[str]:
    out: list[str] = []
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name):
                out.append(t.id)
    elif isinstance(node, ast.AnnAssign):
        if isinstance(node.target, ast.Name):
            out.append(node.target.id)
    return out


def extract_required(source: str, func: str = GATE_FUNC,
                     name: str = GATE_LIST) -> list[str]:
    """Locate a literal list of strings assigned to name inside func.

    Refuses unless the function is found exactly once, the name is
    assigned exactly once inside it, the assigned value is a literal
    list or tuple, and every member is a string constant. Nothing is
    imported and no line number is assumed.
    """
    tree = ast.parse(source)
    funcs = [n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name == func]
    if len(funcs) != 1:
        raise ExtractionRefused(
            "function %s found %d times, expected exactly one"
            % (func, len(funcs)))
    hits = [n for n in ast.walk(funcs[0])
            if isinstance(n, (ast.Assign, ast.AnnAssign))
            and name in _target_names(n)]
    if len(hits) != 1:
        raise ExtractionRefused(
            "name %s assigned %d times inside %s, expected exactly one"
            % (name, len(hits), func))
    value = hits[0].value
    if not isinstance(value, (ast.List, ast.Tuple)):
        raise ExtractionRefused(
            "name %s is not a literal list, it is a %s"
            % (name, type(value).__name__))
    members: list[str] = []
    for element in value.elts:
        if not (isinstance(element, ast.Constant)
                and isinstance(element.value, str)):
            raise ExtractionRefused(
                "member at line %s is not a string constant"
                % getattr(element, "lineno", "unknown"))
        members.append(element.value)
    return members


def declared_modules(raw: bytes) -> list[str]:
    """Every declared module name, found without assuming the key path.

    Walks the whole document for lists whose members are all strings and
    selects the one whose dotted path ends with py-modules. Refuses if
    there is not exactly one such list.
    """
    document = tomllib.loads(raw.decode("utf-8"))
    found: list[tuple[str, list[str]]] = []

    def walk(node: object, path: list[str]) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, path + [str(key)])
        elif isinstance(node, list):
            if node and all(isinstance(x, str) for x in node):
                found.append((".".join(path), list(node)))

    walk(document, [])
    hits = [pair for pair in found if pair[0].endswith("py-modules")]
    if len(hits) != 1:
        raise ExtractionRefused(
            "py-modules lists found: %d, expected exactly one" % len(hits))
    return hits[0][1]


def _required_from_repo() -> list[str]:
    return extract_required(RELEASE_PY.read_text(encoding="utf-8"))


def _declared_from_repo() -> list[str]:
    return declared_modules(PYPROJECT.read_bytes())


# ------------------------------------------------------------------ live


def test_required_is_extractable_exactly_once() -> None:
    members = _required_from_repo()
    assert members, "the required list is empty"
    assert all(isinstance(m, str) for m in members)


def test_required_has_no_duplicates() -> None:
    members = _required_from_repo()
    assert len(members) == len(set(members)), (
        "the required list carries a duplicate name")


def test_required_does_not_shrink_below_floor() -> None:
    members = _required_from_repo()
    assert len(members) >= REQUIRED_FLOOR, (
        "the wheel gate now checks %d names, below the floor of %d; a name "
        "left the list without the floor moving"
        % (len(members), REQUIRED_FLOOR))


def test_every_required_python_module_is_declared() -> None:
    members = _required_from_repo()
    declared = {name + ".py" for name in _declared_from_repo()}
    undeclared = sorted(m for m in members
                        if m.endswith(".py") and m not in declared)
    assert undeclared == [], (
        "the wheel gate requires names that pyproject does not declare: %s"
        % undeclared)


def test_declared_set_is_distinct() -> None:
    declared = _declared_from_repo()
    assert len(declared) == len(set(declared))


# --------------------------------------------------------------- fixtures
# Every rule above is driven red here. A rule that cannot fail binds
# nothing.

CLEAN = (
    "def phase_wheel_gate(whl, version):\n"
    "    required: list[str] = [\"alpha.py\", \"beta.py\", \"nous.lark\"]\n"
    "    return required\n"
)


def test_extractor_refuses_an_absent_function() -> None:
    with pytest.raises(ExtractionRefused):
        extract_required(CLEAN, func="phase_absent")


def test_extractor_refuses_an_absent_name() -> None:
    with pytest.raises(ExtractionRefused):
        extract_required(CLEAN, name="absent")


def test_extractor_refuses_a_name_assigned_twice() -> None:
    source = (
        "def phase_wheel_gate(whl, version):\n"
        "    required = [\"alpha.py\"]\n"
        "    required = [\"beta.py\"]\n"
        "    return required\n"
    )
    with pytest.raises(ExtractionRefused):
        extract_required(source)


def test_extractor_refuses_a_value_that_is_not_a_literal() -> None:
    source = (
        "def phase_wheel_gate(whl, version):\n"
        "    required = sorted(whl)\n"
        "    return required\n"
    )
    with pytest.raises(ExtractionRefused):
        extract_required(source)


def test_extractor_refuses_a_member_that_is_not_a_string() -> None:
    source = (
        "def phase_wheel_gate(whl, version):\n"
        "    required = [\"alpha.py\", 7]\n"
        "    return required\n"
    )
    with pytest.raises(ExtractionRefused):
        extract_required(source)


def test_extractor_reads_the_clean_fixture() -> None:
    assert extract_required(CLEAN) == ["alpha.py", "beta.py", "nous.lark"]


def test_declared_reader_finds_the_list_without_assuming_the_path() -> None:
    raw = (b"[project]\nname = \"x\"\n"
           b"[tool.setuptools]\npy-modules = [\"alpha\", \"beta\"]\n")
    assert declared_modules(raw) == ["alpha", "beta"]


def test_declared_reader_refuses_when_the_list_is_absent() -> None:
    raw = b"[project]\nname = \"x\"\nkeywords = [\"a\", \"b\"]\n"
    with pytest.raises(ExtractionRefused):
        declared_modules(raw)


def test_duplicate_rule_catches_a_repeated_name() -> None:
    members = extract_required(
        "def phase_wheel_gate(w, v):\n"
        "    required = [\"alpha.py\", \"alpha.py\"]\n"
        "    return required\n")
    assert len(members) != len(set(members))


def test_floor_rule_catches_a_shrunken_list() -> None:
    members = extract_required(CLEAN)
    assert len(members) < REQUIRED_FLOOR


def test_declared_rule_catches_an_undeclared_requirement() -> None:
    members = extract_required(CLEAN)
    declared = {name + ".py" for name in
                declared_modules(b"[tool.setuptools]\n"
                                 b"py-modules = [\"alpha\"]\n")}
    undeclared = sorted(m for m in members
                        if m.endswith(".py") and m not in declared)
    assert undeclared == ["beta.py"]
