"""PKG001 (seat S475): the wheel ships what its modules import.

FG-S349-Q: from 25 July 2026 to 8.0.0 the wheel shipped cli.py, whose
evolve and migrate commands import aevolver and migrate, two modules
the wheel did not ship. No test imported them and both servers run
editable installs, so nothing in the house saw it.

These tests read pyproject.toml with tomllib and every declared module
with ast; nothing is imported. Every import, of any kind (module level,
inside a def, under a try), from a declared module to a top-level module
of this tree must name a declared module or an entry of ALLOW, which
says why that module stays out of the wheel.

# __pkg001_s475_closure_v1__
"""
from __future__ import annotations

import ast
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

ALLOW = {
    "noesis_engine": "server only: imports noesis_*_patch modules that "
                     "no commit holds (.gitignore); nous_runtime reaches "
                     "it under try",
    "noesis_oracle": "server only: reads /opt/aetherlang_agents/.env; "
                     "nous_runtime reaches it under try",
}


def _declared() -> set[str]:
    with (REPO / "pyproject.toml").open("rb") as fh:
        st = tomllib.load(fh)["tool"]["setuptools"]
    return set(st.get("py-modules", [])) | set(st.get("packages", []))


def _local() -> set[str]:
    out = {p.stem for p in REPO.glob("*.py")}
    out |= {p.parent.name for p in REPO.glob("*/__init__.py")}
    return out


def _files(name: str) -> list[Path]:
    d = REPO / name
    if d.is_dir():
        return sorted(d.rglob("*.py"))
    return [REPO / (name + ".py")]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_bytes(), filename=str(path))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            out.add(node.module.split(".")[0])
    return out


def _edges() -> list[tuple[str, str]]:
    declared, local = _declared(), _local()
    edges = set()
    for m in sorted(declared & local):
        for f in _files(m):
            for t in _imports(f):
                if t in local and t not in declared and t != m:
                    edges.add((m, t))
    return sorted(edges)


def _required() -> set[str]:
    tree = ast.parse((REPO / "scripts" / "release.py").read_text(encoding="utf-8"))
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and fn.name == "phase_wheel_gate":
            for n in ast.walk(fn):
                if (isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
                        and n.target.id == "required" and isinstance(n.value, ast.List)):
                    return {e.value for e in n.value.elts if isinstance(e, ast.Constant)}
    raise AssertionError("phase_wheel_gate's required list not found")


def test_every_declared_import_resolves() -> None:
    bad = [e for e in _edges() if e[1] not in ALLOW]
    assert bad == [], "declared modules import unshipped local modules: %r" % (bad,)


def test_allow_entries_still_needed() -> None:
    declared, edges = _declared(), _edges()
    for name in ALLOW:
        assert name not in declared, "%s is declared; drop it from ALLOW" % name
        assert any(t == name for _, t in edges), "%s is no longer imported; drop it" % name


def test_migrate_not_declared() -> None:
    assert "migrate" not in _declared(), (
        "the import name migrate belongs to sqlalchemy-migrate on PyPI; "
        "the wheel ships nous_migrate_config")


def test_nous_migrate_config_declared() -> None:
    assert "nous_migrate_config" in _declared()


def test_wheel_gate_requires_both() -> None:
    missing = {"aevolver.py", "nous_migrate_config.py"} - _required()
    assert missing == set(), "wheel gate does not require %r" % (sorted(missing),)
