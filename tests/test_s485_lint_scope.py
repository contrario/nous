"""S485 LINT2 (FG-S481-J): the claim lint reads what is served, and the
deploy gate reads the commit, not the working tree.

L2a: an exclude_dirs entry with a leading "/" names one directory from the
root, so "/examples" keeps examples/ out while website/examples/, which is
served, is linted. L2b: deploy_website.sh refuses a file rsync would serve
that no commit holds, and its gate lints an export of HEAD's commit, so
ignored scratch in the working tree neither moves the count nor refuses a
deploy.

# __s485_lint_scope_tests_v1__
"""
from __future__ import annotations

import importlib.util
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
LINT = REPO / "scripts" / "claim_lint.py"
CLAIMS = REPO / "claims.toml"
DEPLOY = REPO / "scripts" / "deploy_website.sh"
START = "# __s485_deploy_commit_bound_v1__"
END = "# __s485_deploy_commit_bound_end_v1__"
BAD = "Author identity is proven by the Ed25519 signature.\n"
needs_rsync = pytest.mark.skipif(shutil.which("rsync") is None, reason="no rsync")


def _lint():
    spec = importlib.util.spec_from_file_location("claim_lint_s485", LINT)
    m = importlib.util.module_from_spec(spec)
    sys.modules["claim_lint_s485"] = m
    spec.loader.exec_module(m)
    return m


def _cfg(m, tmp_path, dirs):
    text = CLAIMS.read_text(encoding="utf-8")
    new, n = re.subn(r"(?ms)^exclude_dirs = \[.*?\]", "exclude_dirs = %s" % (
        "[" + ", ".join('"%s"' % d for d in dirs) + "]"), text, count=1)
    assert n == 1
    p = tmp_path / "claims.toml"
    p.write_text(new, encoding="utf-8")
    return m.load_config(p)


def _walk(m, root, cfg):
    return sorted(p.relative_to(root).as_posix() for p in m.iter_files(root, cfg))


def _tree(root, files):
    for rel in files:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("plain text\n", encoding="utf-8")
    return root


FILES = ["examples/a.md", "website/examples/b.html", "website/.well-known/c.md",
         "website/d.html", "docs/website/.well-known/e.md"]


def test_V01_a_leading_slash_names_the_root_directory_only(tmp_path):
    m = _lint()
    root = _tree(tmp_path / "t", FILES)
    got = _walk(m, root, _cfg(m, tmp_path, ["/examples"]))
    assert "examples/a.md" not in got, got
    assert "website/examples/b.html" in got, got


def test_V02_a_bare_name_still_excludes_it_at_any_depth(tmp_path):
    assert "__s485_lint_anchored_exclude_v1__" in LINT.read_text(encoding="utf-8")
    m = _lint()
    root = _tree(tmp_path / "t", FILES)
    got = _walk(m, root, _cfg(m, tmp_path, ["examples"]))
    assert "examples/a.md" not in got and "website/examples/b.html" not in got, got


def test_V03_a_path_entry_still_excludes_that_path_only(tmp_path):
    assert "__s485_lint_anchored_exclude_v1__" in LINT.read_text(encoding="utf-8")
    m = _lint()
    root = _tree(tmp_path / "t", FILES)
    got = _walk(m, root, _cfg(m, tmp_path, ["website/.well-known"]))
    assert "website/.well-known/c.md" not in got, got
    assert "docs/website/.well-known/e.md" in got, got


def test_V04_a_malformed_entry_is_refused(tmp_path):
    m = _lint()
    for bad in ("", "/", "/x/"):
        with pytest.raises(m.ConfigError):
            _cfg(m, tmp_path, [".git", bad])


def test_V05_the_repo_config_lints_the_served_examples_page():
    m = _lint()
    got = _walk(m, REPO, m.load_config(CLAIMS))
    assert "website/examples/index.html" in got
    assert not [g for g in got if g.startswith("examples/")], got


def test_V06_the_apply_gate_is_the_commit_not_the_working_tree():
    text = DEPLOY.read_text(encoding="utf-8")
    assert text.count(START) == 1 and text.count(END) == 1
    assert "--root ." not in text
    gate = text[text.index('if [ "${APPLY}" -eq 0 ]'):]
    assert "if ! lint_commit; then" in gate
    assert re.search(r"(?m)^RSYNC_OPTS=\(-rc --exclude='\*\.bak\*' --exclude='__pycache__/' "
                     r"--exclude='\*\.pyc' --chmod=D0755,F0644\)$", text)


def _git(repo, *a):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"] + list(a),
                   check=True, capture_output=True)


def _repo(tmp_path, files):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    for rel, data in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fixture")
    return repo


def _bash(repo, body, opts=None):
    text = DEPLOY.read_text(encoding="utf-8")
    line = re.search(r"(?m)^RSYNC_OPTS=\(.*\)\s*$", text).group(0)
    if opts is not None:
        line = "RSYNC_OPTS=(%s)" % opts
    block = text[text.index(START):text.index(END)]
    script = "set -euo pipefail\n%s\n%s\ncd %s\n%s\n" % (line, block, shlex.quote(str(repo)), body)
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True)


def _served(repo, opts=None):
    return _bash(repo, 'untracked_served "%s/website/" website/' % repo, opts)


@needs_rsync
def test_V07_tracked_files_only_print_nothing(tmp_path):
    repo = _repo(tmp_path, {"website/a.html": "<p>a</p>\n", "website/s/b.css": "b\n"})
    p = _served(repo)
    assert p.returncode == 0 and p.stdout == "", (p.returncode, p.stdout, p.stderr)


@needs_rsync
def test_V08_an_ignored_served_file_is_printed(tmp_path):
    repo = _repo(tmp_path, {"website/a.html": "<p>a</p>\n", ".gitignore": "trace_*.json\n"})
    (repo / "website" / "trace_1.json").write_text("{}\n", encoding="utf-8")
    p = _served(repo)
    assert p.returncode == 0 and p.stdout.splitlines() == ["trace_1.json"], (p.stdout, p.stderr)


@needs_rsync
def test_V09_what_rsync_excludes_is_not_printed(tmp_path):
    repo = _repo(tmp_path, {"website/a.html": "<p>a</p>\n"})
    (repo / "website" / "a.html.bak").write_text("old\n", encoding="utf-8")
    (repo / "website" / "__pycache__").mkdir()
    (repo / "website" / "__pycache__" / "x.pyc").write_bytes(b"\0")
    p = _served(repo)
    assert p.returncode == 0 and p.stdout == "", (p.stdout, p.stderr)


@needs_rsync
def test_V10_a_failing_rsync_is_not_a_clean_list(tmp_path):
    repo = _repo(tmp_path, {"website/a.html": "<p>a</p>\n"})
    p = _served(repo, opts="-rc --no-such-option-s485")
    assert p.returncode == 3, (p.returncode, p.stdout, p.stderr)


def test_V11_the_gate_lints_the_commit(tmp_path):
    repo = _repo(tmp_path, {"scripts/claim_lint.py": LINT.read_text(encoding="utf-8"),
                            "claims.toml": CLAIMS.read_text(encoding="utf-8"),
                            "doc.md": "plain text\n", ".gitignore": "scratch_*.md\n"})
    assert _bash(repo, "lint_commit").returncode == 0
    (repo / "scratch_1.md").write_text(BAD, encoding="utf-8")
    p = _bash(repo, "lint_commit")
    assert p.returncode == 0, (p.stdout, p.stderr)
    (repo / "bad.md").write_text(BAD, encoding="utf-8")
    _git(repo, "add", "bad.md")
    _git(repo, "commit", "-q", "-m", "bad")
    p = _bash(repo, "lint_commit")
    assert p.returncode == 1, (p.returncode, p.stdout, p.stderr)
