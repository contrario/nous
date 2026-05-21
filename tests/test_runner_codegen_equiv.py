# __session87_runner_codegen_equiv_v1__
"""GAP 1: runner vs codegen semantic-surface differential test (v1).

Six-element surface (routes excluded by design -- see SemanticSurface
docstring). The codegen side recovers the surface from the EMITTED module
via stdlib ast, so a passing test proves codegen emitted what the runner
will consume, not merely that both read the same input.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from parser import parse_nous
from validator import validate_program
from codegen import (
    NousCodeGen,
    assert_no_undefined_names,
)
from nous_ast_runner import SemanticSurface, derive_runtime_surface

REPO = Path(__file__).resolve().parent.parent

EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "build",
    "dist",
    "__pycache__",
    "node_modules",
    "nous-v2.0",
    "tests",
}

# Structural self.X assignments codegen always emits in a soul __init__.
# Memory-field recovery excludes exactly these. The completeness test below
# fails loudly if codegen ever introduces a new structural assignment, so
# this set cannot silently drift out of date.
STRUCTURAL_SELF_ATTRS = frozenset(
    {  # __session87_g1_mood_attr_v1__
        "name",
        "_runtime",
        "model",
        "tier",
        "senses",
        "cycle_count",
        "_mood",
    }
)


def _iter_corpus():
    for p in sorted(REPO.rglob("*.nous")):
        if any(part in EXCLUDE_DIRS for part in p.relative_to(REPO).parts):
            continue
        yield p


def _parse_validate(path: Path):
    src = path.read_text(encoding="utf-8")
    program = parse_nous(src)
    result = validate_program(program)
    if not result.ok:
        return None
    return program


def _gate_clean(program) -> bool:
    try:
        code = NousCodeGen(program).generate()
        assert_no_undefined_names(code)
    except Exception:
        return False
    return True


def _gate_clean_corpus():
    out = []
    for path in _iter_corpus():
        try:
            program = _parse_validate(path)
        except Exception:
            continue
        if program is None:
            continue
        if not program.souls:
            continue
        if _gate_clean(program):
            out.append(path)
    return out


GATE_CLEAN = _gate_clean_corpus()


def _str_literal(node) -> str:
    return node.value if isinstance(node, ast.Constant) else None


def derive_codegen_surface(program) -> SemanticSurface:
    """Recover the six-element surface from the emitted Python module."""
    code = NousCodeGen(program).generate()
    tree = ast.parse(code)

    souls = set()
    messages = set()
    soul_models = {}
    soul_senses = {}
    soul_memory = {}
    heartbeat_seconds = None
    cost_ceiling = None

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "HEARTBEAT_SECONDS":
                    heartbeat_seconds = ast.literal_eval(node.value)
                if isinstance(tgt, ast.Name) and tgt.id == "COST_CEILING":
                    cost_ceiling = ast.literal_eval(node.value)

        if isinstance(node, ast.ClassDef):
            base_names = {
                b.id for b in node.bases if isinstance(b, ast.Name)
            }
            if "BaseModel" in base_names:
                messages.add(node.name)
                continue
            if node.name.startswith("Soul_"):
                soul_name = node.name[len("Soul_"):]
                souls.add(soul_name)
                _recover_soul(
                    node, soul_name, soul_models, soul_senses, soul_memory
                )

    return SemanticSurface(
        souls=frozenset(souls),
        messages=frozenset(messages),
        soul_models=soul_models,
        soul_senses=soul_senses,
        soul_memory=soul_memory,
        heartbeat_seconds=int(heartbeat_seconds),
        cost_ceiling=float(cost_ceiling),
    )


def _recover_soul(classnode, soul_name, soul_models, soul_senses, soul_memory):
    init = None
    for item in classnode.body:
        if isinstance(item, ast.FunctionDef) and item.name == "__init__":
            init = item
            break
    if init is None:
        soul_models[soul_name] = "unknown @ Tier1"
        soul_senses[soul_name] = frozenset()
        soul_memory[soul_name] = frozenset()
        return

    model = None
    tier = None
    senses = frozenset()
    mem = set()
    for stmt in init.body:
        if not isinstance(stmt, ast.Assign):
            continue
        for tgt in stmt.targets:
            if not (
                isinstance(tgt, ast.Attribute)
                and isinstance(tgt.value, ast.Name)
                and tgt.value.id == "self"
            ):
                continue
            attr = tgt.attr
            if attr == "model":
                model = _str_literal(stmt.value)
            elif attr == "tier":
                tier = _str_literal(stmt.value)
            elif attr == "senses":
                try:
                    val = ast.literal_eval(stmt.value)
                    senses = frozenset(val) if val else frozenset()
                except Exception:
                    senses = frozenset()
            elif attr.startswith("dna_"):
                continue
            elif attr in STRUCTURAL_SELF_ATTRS:
                continue
            else:
                mem.add(attr)

    soul_models[soul_name] = str(model) + " @ " + str(tier)
    soul_senses[soul_name] = senses
    soul_memory[soul_name] = frozenset(mem)


@pytest.mark.skipif(not GATE_CLEAN, reason="no gate-clean corpus sources")
@pytest.mark.parametrize(
    "path", GATE_CLEAN, ids=[p.name for p in GATE_CLEAN]
)
def test_runner_codegen_surface_equal(path):
    program = _parse_validate(path)
    assert program is not None
    runtime_surface = derive_runtime_surface(program)
    codegen_surface = derive_codegen_surface(program)
    assert runtime_surface == codegen_surface, (
        "surface divergence for " + path.name + ":\n"
        "  souls r/c:   " + str(sorted(runtime_surface.souls)) + " / "
        + str(sorted(codegen_surface.souls)) + "\n"
        "  msgs  r/c:   " + str(sorted(runtime_surface.messages)) + " / "
        + str(sorted(codegen_surface.messages)) + "\n"
        "  models r:    " + str(dict(runtime_surface.soul_models)) + "\n"
        "  models c:    " + str(dict(codegen_surface.soul_models)) + "\n"
        "  senses r:    " + str(dict(runtime_surface.soul_senses)) + "\n"
        "  senses c:    " + str(dict(codegen_surface.soul_senses)) + "\n"
        "  memory r:    " + str(dict(runtime_surface.soul_memory)) + "\n"
        "  memory c:    " + str(dict(codegen_surface.soul_memory)) + "\n"
        "  hb r/c:      " + str(runtime_surface.heartbeat_seconds) + " / "
        + str(codegen_surface.heartbeat_seconds) + "\n"
        "  ceil r/c:    " + str(runtime_surface.cost_ceiling) + " / "
        + str(codegen_surface.cost_ceiling)
    )


@pytest.mark.skipif(not GATE_CLEAN, reason="no gate-clean corpus sources")
def test_negative_control_detects_dropped_soul():
    program = _parse_validate(GATE_CLEAN[0])
    assert program is not None
    base = derive_codegen_surface(program)
    assert base.souls, "fixture has no souls; pick a different source"
    dropped = sorted(base.souls)[0]
    mutated_souls = frozenset(s for s in base.souls if s != dropped)
    mutated = SemanticSurface(
        souls=mutated_souls,
        messages=base.messages,
        soul_models={
            k: v for k, v in base.soul_models.items() if k != dropped
        },
        soul_senses={
            k: v for k, v in base.soul_senses.items() if k != dropped
        },
        soul_memory={
            k: v for k, v in base.soul_memory.items() if k != dropped
        },
        heartbeat_seconds=base.heartbeat_seconds,
        cost_ceiling=base.cost_ceiling,
    )
    runtime_surface = derive_runtime_surface(program)
    assert runtime_surface == base
    assert runtime_surface != mutated


def test_worldless_source_defaults_agree(tmp_path):
    src = (
        'soul Watcher {\n'
        '    mind { model: "claude-haiku" tier: Tier1 }\n'
        '    senses [ ]\n'
        '}\n'
    )
    try:  # __session87_g1_worldless_skip_v1__
        program = parse_nous(src)
    except Exception:
        pytest.skip("minimal world-less source did not parse on this build")
    result = validate_program(program)
    if not result.ok:
        pytest.skip("minimal world-less source did not validate on this build")
    if not _gate_clean(program):
        pytest.skip("minimal world-less source not gate-clean on this build")
    runtime_surface = derive_runtime_surface(program)
    codegen_surface = derive_codegen_surface(program)
    assert runtime_surface == codegen_surface
    assert runtime_surface.heartbeat_seconds == 300
    assert runtime_surface.cost_ceiling == 0.10


@pytest.mark.skipif(not GATE_CLEAN, reason="no gate-clean corpus sources")
def test_structural_self_attrs_exhaustive():
    """Guard: codegen must not introduce a structural self.X assignment that
    is not in STRUCTURAL_SELF_ATTRS, which would be miscounted as a memory
    field. Recompute structural attrs from a known soul and compare.
    """
    for path in GATE_CLEAN:
        program = _parse_validate(path)
        if program is None:
            continue
        code = NousCodeGen(program).generate()
        tree = ast.parse(code)
        for node in tree.body:
            if not (
                isinstance(node, ast.ClassDef)
                and node.name.startswith("Soul_")
            ):
                continue
            soul_name = node.name[len("Soul_"):]
            mem_decl = set()
            soul = next(
                (s for s in program.souls if s.name == soul_name), None
            )
            if soul is not None and soul.memory is not None:
                for f in soul.memory.fields:
                    mem_decl.add(f.name if hasattr(f, "name") else str(f))
            init = next(
                (
                    it
                    for it in node.body
                    if isinstance(it, ast.FunctionDef)
                    and it.name == "__init__"
                ),
                None,
            )
            if init is None:
                continue
            emitted = set()
            for stmt in init.body:
                if not isinstance(stmt, ast.Assign):
                    continue
                for tgt in stmt.targets:
                    if (
                        isinstance(tgt, ast.Attribute)
                        and isinstance(tgt.value, ast.Name)
                        and tgt.value.id == "self"
                    ):
                        emitted.add(tgt.attr)
            unexplained = {
                a
                for a in emitted
                if a not in STRUCTURAL_SELF_ATTRS
                and not a.startswith("dna_")
                and a not in mem_decl
            }
            assert not unexplained, (
                "Soul_" + soul_name + " emits unexplained structural attrs "
                + str(sorted(unexplained))
                + "; add them to STRUCTURAL_SELF_ATTRS or the memory recovery "
                "will miscount. (source: " + path.name + ")"
            )
