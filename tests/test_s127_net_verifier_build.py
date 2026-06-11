"""S127 U5 tests: blocking-net-full verifier splice.

__s127_net_verifier_build_tests_v1__
"""
from __future__ import annotations

import py_compile
import tempfile
from pathlib import Path

import dossier


def test_splice_compiles() -> None:
    src = dossier.build_chain_net_verifier()
    d = Path(tempfile.mkdtemp())
    p = d / "verify_offline.py"
    p.write_text(src, encoding="utf-8")
    py_compile.compile(str(p), doraise=True)


def test_splice_inserts_net_machinery() -> None:
    src = dossier.build_chain_net_verifier()
    assert src.count("__s127_net_walk_v1__") >= 3
    assert "def _walk_net_containment(ordered):" in src
    assert "def check_net_bundle(" in src
    assert "blocking-net-full" in src


def test_splice_grows_template_and_keeps_anchors() -> None:
    base = dossier.VERIFY_OFFLINE_PY_CHAIN_BUNDLE
    src = dossier.build_chain_net_verifier()
    assert len(src) > len(base)
    assert src.count("# --- end farkas embed ---") == 1
    assert src.count("def _walk_chain(current_manifest):") == 1
