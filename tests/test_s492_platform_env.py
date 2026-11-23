"""S492: credential isolation of the API process.

FG-S492-E: nous_runtime, noesis_oracle and noesis_telegram each read
/opt/aetherlang_agents/.env at import and set every name the process
lacks. A process that declares its credential file through
NOUS_ENV_FILE (the API units on Server A and Server B) must not merge
the platform file as well: each loader returns at once when
NOUS_ENV_FILE is set, and loads as before when it is not (the
standalone noesis scripts and bots, the CLI run path).

FG-S492-J: nous_api loads NOUS_ENV_FILE only. It no longer falls back
to the .env of the directory above the tree, which loaded the platform
file into any process importing nous_api without NOUS_ENV_FILE.

The loaders are read from source by ast and run with their path
constant pointed at a temporary file: importing noesis_telegram needs
modules that are not in the repository.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LOADERS = [
    ("nous_runtime.py", "ENV_PATH"),
    ("noesis_oracle.py", "_ENV_PATH"),
    ("noesis_telegram.py", "ENV_PATH"),
]
NAME = "S492_PLATFORM_ONLY_NAME"


def _tree(fname):
    return ast.parse((ROOT / fname).read_text(encoding="utf-8"), fname)


def _loader(fname, const, path):
    fns = [n for n in _tree(fname).body
           if isinstance(n, ast.FunctionDef) and n.name == "_load_env"]
    assert len(fns) == 1, fname
    ns = {"os": os, "Path": Path, const: path}
    exec(compile(ast.Module(body=fns, type_ignores=[]), fname, "exec"), ns)
    return ns["_load_env"]


def _platform_file(tmp_path):
    f = tmp_path / "platform.env"
    f.write_text("# platform\n%s=from-platform\nexport OTHER_S492=x\n" % NAME, encoding="utf-8")
    return f


@pytest.mark.parametrize("fname,const", LOADERS)
def test_loader_skips_when_nous_env_file_is_set(fname, const, tmp_path, monkeypatch):
    monkeypatch.delenv(NAME, raising=False)
    monkeypatch.setenv("NOUS_ENV_FILE", str(tmp_path / "cred.env"))
    _loader(fname, const, _platform_file(tmp_path))()
    assert NAME not in os.environ


@pytest.mark.parametrize("fname,const", LOADERS)
def test_loader_loads_when_nous_env_file_is_unset(fname, const, tmp_path, monkeypatch):
    monkeypatch.delenv(NAME, raising=False)
    monkeypatch.delenv("NOUS_ENV_FILE", raising=False)
    _loader(fname, const, _platform_file(tmp_path))()
    assert os.environ.get(NAME) == "from-platform"


@pytest.mark.parametrize("fname,const", LOADERS)
def test_loader_is_still_called_at_import(fname, const):
    calls = [n for n in _tree(fname).body
             if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
             and getattr(n.value.func, "id", None) == "_load_env"]
    assert len(calls) == 1, fname


def _nous_api_copy(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    for n in ("nous_api.py", "_version.py"):
        (tree / n).write_bytes((ROOT / n).read_bytes())
    (tmp_path / ".env").write_text("%s=from-parent\n" % NAME, encoding="utf-8")
    return tree


def _import_nous_api(tree, extra):
    env = {k: v for k, v in os.environ.items() if k not in ("NOUS_ENV_FILE", NAME)}
    env.update(extra)
    code = ("import os, sys; sys.path.insert(0, %r); import nous_api; "
            "print('VALUE', os.environ.get(%r))" % (str(tree), NAME))
    return subprocess.run([sys.executable, "-c", code], env=env, cwd=str(tree),
                          capture_output=True, text=True, timeout=120)


def test_nous_api_does_not_load_the_parent_dotenv(tmp_path):
    r = _import_nous_api(_nous_api_copy(tmp_path), {})
    assert r.returncode == 0, r.stderr[-600:]
    assert "VALUE None" in r.stdout


def test_nous_api_loads_nous_env_file(tmp_path):
    tree = _nous_api_copy(tmp_path)
    cred = tmp_path / "cred.env"
    cred.write_text("%s=from-cred\n" % NAME, encoding="utf-8")
    r = _import_nous_api(tree, {"NOUS_ENV_FILE": str(cred)})
    assert r.returncode == 0, r.stderr[-600:]
    assert "VALUE from-cred" in r.stdout


def test_nous_api_refuses_a_missing_nous_env_file(tmp_path):
    tree = _nous_api_copy(tmp_path)
    r = _import_nous_api(tree, {"NOUS_ENV_FILE": str(tmp_path / "absent.env")})
    assert r.returncode != 0
    assert "NOUS_ENV_FILE did not load" in r.stderr
