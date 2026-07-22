"""The reference evidence is three artifacts that must describe each other:

    trace_bundle/            the golden pack (immutable; sim-anchored)
    trace_bundle_c2_token.der  an RFC 3161 token over that bundle's manifest
    trace_bundle_c2_meta.json  what the token says, in readable form

Nothing checked that they agree. A rotation refreshes the token and the meta
together, but if either is dropped from a commit -- or refreshed against a
different bundle -- the committed meta describes a token that no longer exists,
and the failure surfaces at audit time rather than at test time.

These tests make the three mutually verifiable, and pin the rotation procedure
itself (token refresh must not rebuild the bundle).
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

dossier = pytest.importorskip("dossier")

_REF = _REPO / "tests" / "reference_evidence"
_BUNDLE = _REF / "trace_bundle"
_TOKEN = _REF / "trace_bundle_c2_token.der"
_META = _REF / "trace_bundle_c2_meta.json"
_CAPTURE = _REPO / "capture_c2_reference_evidence.py"


def _rfc3161():
    """The shipped, live-proven verifier, loaded from the dossier embed."""
    d = Path(tempfile.mkdtemp())
    ep = d / "_pa_rec.py"
    ep.write_text(dossier._PCE_ANCHOR_CHECK_EMBED)
    sp = importlib.util.spec_from_file_location("_pa_rec", ep)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def _present():
    return _TOKEN.is_file() and _META.is_file() and (_BUNDLE / "manifest.json").is_file()


@pytest.mark.offline
def test_token_binds_the_committed_bundle():
    if not _present():
        pytest.skip("reference evidence not present")
    bm = (_BUNDLE / "manifest.json").read_bytes()
    ok, _, errs = _rfc3161()._pa_verify_rfc3161(_TOKEN.read_bytes(), bm)
    assert ok, (
        "the committed token does not verify over the committed bundle "
        "manifest: %s. Either the token was refreshed against a different "
        "bundle, or the pinned TSA root has rotated (run "
        "capture_c2_reference_evidence.py with NO arguments)." % errs)


@pytest.mark.offline
def test_meta_describes_the_committed_token_and_bundle():
    if not _present():
        pytest.skip("reference evidence not present")
    meta = json.loads(_META.read_text(encoding="utf-8"))
    bm = (_BUNDLE / "manifest.json").read_bytes()

    assert meta["anchored_bundle_sha256"] == hashlib.sha256(bm).hexdigest(), (
        "meta.anchored_bundle_sha256 does not match sha256(trace_bundle/"
        "manifest.json); the meta describes a different bundle")

    _, gen_time, _ = _rfc3161()._pa_verify_rfc3161(_TOKEN.read_bytes(), bm)
    assert meta["t_attest_utc"] == gen_time.isoformat(), (
        "meta.t_attest_utc (%s) is not the genTime of the committed token "
        "(%s). The two were refreshed separately, or one of them was dropped "
        "from a commit." % (meta["t_attest_utc"], gen_time.isoformat()))


@pytest.mark.offline
def test_meta_is_tracked_not_ignored():
    # .gitignore carries `trace_*.json`, which would swallow this file if it
    # were ever untracked. It is tracked today; assert the file exists and is
    # non-trivial so a silent loss is visible here rather than at audit time.
    if not _META.is_file():
        pytest.skip("reference evidence not present")
    meta = json.loads(_META.read_text(encoding="utf-8"))
    for key in ("anchored_bundle_sha256", "t_attest_utc", "tsa_url",
                "pinned_root_not_after"):
        assert key in meta, "meta lost field %r" % key


@pytest.mark.offline
def test_rotation_default_does_not_rebuild_the_bundle():
    """The documented rotation procedure is 'run the capture script with no
    arguments'. Its correctness depends on the default refreshing only the
    token. Pin that: the bundle write must be guarded by the rebuild flag."""
    if not _CAPTURE.is_file():
        pytest.skip("capture script not present")
    src = _CAPTURE.read_text(encoding="utf-8")
    assert "--rebuild-bundle" in src, (
        "the capture script no longer offers --rebuild-bundle; the rotation "
        "procedure documented in the script and the handoff assumes it")
    tree = ast.parse(src)

    # every rmtree/copytree that targets the reference bundle must sit inside
    # a branch testing the rebuild flag
    unguarded = []

    class V(ast.NodeVisitor):
        def __init__(self):
            self.guard_depth = 0

        def visit_If(self, node):
            g = ast.dump(node.test)
            guarded = "_rebuilt" in g or "rebuild_bundle" in g
            self.guard_depth += 1 if guarded else 0
            self.generic_visit(node)
            self.guard_depth -= 1 if guarded else 0

        def visit_Call(self, node):
            fn = ast.dump(node.func)
            if ("copytree" in fn or "rmtree" in fn) and self.guard_depth == 0:
                unguarded.append(getattr(node, "lineno", "?"))
            self.generic_visit(node)

    V().visit(tree)
    assert not unguarded, (
        "capture_c2_reference_evidence.py writes the bundle tree outside a "
        "rebuild guard (lines %s). A rotation must refresh the token only; "
        "rebuilding the bundle moves the golden-pack baseline and breaks "
        "test_golden_pack_is_unmodified." % unguarded)
