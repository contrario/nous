"""Two invariants that were asserted in prose but never checked.

(1) WIRE VERSION CONSISTENCY. The value written into signed objects
    (`spec_version`) is duplicated across five places: two implementations, the
    tracked embed source, the embed constant compiled into dossier.py, and the
    normative example in SPEC.md. Nothing tied them together, so they could
    drift the way the three RFC 3161 copies actually did.

(2) WIRE COMPATIBILITY OF PACKS. SPEC.md states that no revision since 0.2.0
    changed a field, tag, hash input or encoding, so packs stay byte-compatible
    across 0.2.x document revisions. That was a claim resting on nobody having
    broken it. This pins it to an artifact: a committed pack must keep verifying
    with the current verifier, unchanged.

HONEST SCOPE OF (2): the golden pack was captured at commit 1ef4dd5, i.e. under
document revision 0.2.1-draft -- not under 0.2.0. It therefore locks wire
compatibility from that point forward. It cannot retroactively prove that the
0.2.0 -> 0.2.1 errata fold preserved compatibility; no 0.2.0-era vector was ever
committed (trace/archive holds superseded spec TEXTS, not packs), so that proof
is unavailable. Stating this here rather than implying broader coverage.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

dossier = pytest.importorskip("dossier")
trace_bridge = pytest.importorskip("trace_bridge")

_GOLDEN = _REPO / "tests" / "reference_evidence" / "trace_bundle"
_GOLDEN_META = _REPO / "tests" / "reference_evidence" / "trace_bundle_c2_meta.json"


# --------------------------------------------------------------------------
# (1) wire version consistency across all five sites
# --------------------------------------------------------------------------

def _wire_version_sites():
    sites = {}

    src = (_REPO / "trace_bridge.py").read_text(encoding="utf-8")
    m = re.search(r'^SPEC = "([^"]+)"', src, re.M)
    sites["trace_bridge.SPEC"] = m.group(1) if m else None

    src = (_REPO / "trace" / "reference" / "verifier.py").read_text(encoding="utf-8")
    m = re.search(r'^SPEC = "([^"]+)"', src, re.M)
    sites["reference_verifier.SPEC"] = m.group(1) if m else None

    tb = _REPO / "tb_check.py"
    if tb.is_file():
        m = re.search(r'^_TB_SPEC = "([^"]+)"', tb.read_text(encoding="utf-8"), re.M)
        sites["tb_check._TB_SPEC"] = m.group(1) if m else None

    m = re.search(r'_TB_SPEC = "([^"]+)"', dossier._TRACE_BUNDLE_CHECK_EMBED)
    sites["dossier.embed._TB_SPEC"] = m.group(1) if m else None

    spec_md = (_REPO / "trace" / "SPEC.md").read_text(encoding="utf-8")
    m = re.search(r'"spec_version":\s*"([^"]+)"', spec_md)
    sites["SPEC.md.example"] = m.group(1) if m else None

    return sites


def test_wire_version_is_consistent_everywhere():
    sites = _wire_version_sites()
    missing = [k for k, v in sites.items() if v is None]
    assert not missing, "wire version not found in: %s" % missing
    values = set(sites.values())
    assert len(values) == 1, (
        "wire version (spec_version) has DRIFTED across the places that write "
        "it:\n" + "\n".join("    %-28s %s" % (k, v) for k, v in sites.items())
        + "\n  All five must agree; a pack written by one implementation must "
          "be accepted by the other and match the normative example.")


def test_wire_version_matches_the_runtime_constants():
    # belt and braces: the imported modules must agree with the parsed sources
    from trace_bridge import SPEC as bridge_spec
    assert bridge_spec == next(iter(set(_wire_version_sites().values())))


# --------------------------------------------------------------------------
# (2) the golden pack must keep verifying
# --------------------------------------------------------------------------

def _verifier():
    vp = _REPO / "trace" / "reference" / "verifier.py"
    spec = importlib.util.spec_from_file_location("_rv_wire", vp)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.mark.offline
def test_golden_pack_is_unmodified():
    """The pack is an immutable artifact. Regenerating it silently would void
    the compatibility check it exists to provide."""
    if not (_GOLDEN / "manifest.json").is_file():
        pytest.skip("golden pack not present")
    meta = json.loads(_GOLDEN_META.read_text(encoding="utf-8"))
    expected = meta["anchored_bundle_sha256"]
    actual = hashlib.sha256((_GOLDEN / "manifest.json").read_bytes()).hexdigest()
    assert actual == expected, (
        "the golden pack's manifest.json changed (%s != %s). If this was "
        "deliberate, the wire-compatibility baseline moved and that must be a "
        "conscious, recorded decision -- not a side effect."
        % (actual[:16], expected[:16]))


@pytest.mark.offline
def test_golden_pack_still_verifies_with_current_verifier():
    """Wire compatibility, pinned to an artifact rather than asserted in prose.

    If this fails, a change since commit 1ef4dd5 altered a field, tag, hash
    input or encoding in a way that breaks packs already in the wild -- which
    SPEC.md currently states cannot happen across 0.2.x document revisions.
    """
    if not (_GOLDEN / "manifest.json").is_file():
        pytest.skip("golden pack not present")
    tmp = Path(tempfile.mkdtemp())
    pack = tmp / "pack"
    shutil.copytree(_GOLDEN, pack)
    code, report = _verifier().verify_pack(str(pack))
    assert code == 0, (
        "the golden pack no longer verifies (code=%s, verdict=%s); wire "
        "compatibility has broken" % (code, report.get("verdict")))
    assert report["verdict"] == "VALID", report.get("verdict")
    # the pack declares the wire version the implementations write today
    man = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    assert man["spec_version"] == trace_bridge.SPEC
