"""S485 LINT4 (FG-S481-J): the release's claim gate, phase 5b, reads the
commit, not the working tree.

phase_claim_lint exports HEAD's commit with git archive and runs the
export's own claim lint and config over the export, --anchor the commit.
A file that no commit holds, ignored scratch in the release host's tree,
neither moves the scanned count nor refuses a release; a violation that a
commit holds still refuses it.

# __s485_release_lint_tests_v1__
"""
from __future__ import annotations

import ast
import importlib.util
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
RELEASE = REPO / "scripts" / "release.py"
LINT = REPO / "scripts" / "claim_lint.py"
CLAIMS = REPO / "claims.toml"
BAD = "Author identity is proven by the Ed25519 signature.\n"


def _load():
    spec = importlib.util.spec_from_file_location("_s485_release_lint", RELEASE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _phase_source() -> str:
    src = RELEASE.read_text(encoding="utf-8")
    node = next(n for n in ast.parse(src).body
                if isinstance(n, ast.FunctionDef) and n.name == "phase_claim_lint")
    return "".join(src.splitlines(True)[node.lineno - 1:node.end_lineno])


def _git(repo, *a):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"] + list(a),
                   check=True, capture_output=True)


def _repo(tmp_path, extra=None):
    repo = tmp_path / "r"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "claim_lint.py").write_text(LINT.read_text(encoding="utf-8"), encoding="utf-8")
    (repo / "claims.toml").write_text(CLAIMS.read_text(encoding="utf-8"), encoding="utf-8")
    (repo / "doc.md").write_text("plain text\n", encoding="utf-8")
    (repo / ".gitignore").write_text("scratch_*.md\n", encoding="utf-8")
    for rel, data in (extra or {}).items():
        (repo / rel).write_text(data, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fixture")
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()
    return repo, head


def _armed(repo, monkeypatch, tmp_path):
    m = _load()
    m.REPO_ROOT = repo
    t = tmp_path / "tmp"
    t.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(t))
    return m, t


def test_W01_the_phase_exports_the_commit_and_names_it():
    src = _phase_source()
    assert "__s485_release_lint_commit_v1__" in src
    assert '"archive"' in src and '"--anchor"' in src
    assert '"--root", "."' not in src


def test_W02_a_clean_commit_passes_and_is_named(tmp_path, monkeypatch, capsys):
    repo, head = _repo(tmp_path)
    m, _ = _armed(repo, monkeypatch, tmp_path)
    m.phase_claim_lint()
    out = capsys.readouterr().out
    assert "anchor:  %s" % head in out, out
    assert "scanned: " in out, out


def test_W03_an_ignored_file_no_commit_holds_is_not_read(tmp_path, monkeypatch):
    repo, _ = _repo(tmp_path)
    (repo / "scratch_1.md").write_text(BAD, encoding="utf-8")
    m, _ = _armed(repo, monkeypatch, tmp_path)
    m.phase_claim_lint()


def test_W04_a_committed_violation_still_refuses(tmp_path, monkeypatch):
    repo, _ = _repo(tmp_path, {"bad.md": BAD})
    m, _ = _armed(repo, monkeypatch, tmp_path)
    with pytest.raises(m.ReleaseError):
        m.phase_claim_lint()


def test_W05_no_repository_is_a_named_failure(tmp_path, monkeypatch):
    root = tmp_path / "plain"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "claim_lint.py").write_text(LINT.read_text(encoding="utf-8"), encoding="utf-8")
    (root / "claims.toml").write_text(CLAIMS.read_text(encoding="utf-8"), encoding="utf-8")
    m, _ = _armed(root, monkeypatch, tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    with pytest.raises(m.ReleaseError):
        m.phase_claim_lint()


def test_W06_the_export_is_removed(tmp_path, monkeypatch):
    repo, _ = _repo(tmp_path)
    m, t = _armed(repo, monkeypatch, tmp_path)
    m.phase_claim_lint()
    assert list(t.iterdir()) == []
