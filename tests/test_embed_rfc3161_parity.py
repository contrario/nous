"""Guard rail: the three embedded RFC 3161 verifiers must stay identical.

dossier.py ships the same RFC 3161 implementation three times, once per leg,
deliberately (leg independence: each embedded verifier must run standalone and
compose in any order inside the emitted verify_offline.py):

    _PCE_ANCHOR_CHECK_EMBED           -> _pa_   (PCE anchor, Art 43(4))
    _TRACE_BUNDLE_ANCHOR_CHECK_EMBED  -> _tba_  (C2 bundle temporal existence)
    _TRACE_BUNDLE_CHECK_EMBED         -> _tbrv_ (C3 per-checkpoint anchors)

They were produced by extraction, not by rewriting -- but "identical by
construction" is a statement about the past, not an invariant. Without this
test, a fix applied to one leg (an ASN.1 edge case, a chain-validation
tightening) silently leaves the other two behind, and the emitted verifier
carries two stale copies of security-critical code.

This test normalises the prefixes and compares the three byte-for-byte, so any
divergence fails loudly and names which leg drifted.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

dossier = pytest.importorskip("dossier")

# (embed attribute, prefix pair, marker that ends the RFC 3161 section)
_LEGS = [
    ("_PCE_ANCHOR_CHECK_EMBED", "_PA_", "_pa_"),
    ("_TRACE_BUNDLE_ANCHOR_CHECK_EMBED", "_TBA_", "_tba_"),
    ("_TRACE_BUNDLE_CHECK_EMBED", "_TBRV_", "_tbrv_"),
]

# the RFC 3161 section of every copy ends with the verifier's return statement
_END_MARKER = "    return ok, gen_time, errors\n"


def _extract_rfc3161(embed: str, upper: str, lower: str) -> str:
    """Return the RFC 3161 section of an embed, prefix-normalised."""
    start_tok = upper + "OID_SIGNED_DATA"
    assert start_tok in embed, "no RFC 3161 section found (%s)" % start_tok
    i = embed.index(start_tok)
    j = embed.index(_END_MARKER, i) + len(_END_MARKER)
    section = embed[i:j]
    # normalise both the SCREAMING and the lower-case prefixes to a common one
    section = section.replace(upper, "_X_").replace(lower, "_x_")
    # the malformed-exception class name follows the same pattern per leg
    for cls in ("_PaMalformed", "_TbaMalformed", "_TbrvMalformed"):
        section = section.replace(cls, "_XMalformed")
    return section


def _sections():
    out = {}
    for attr, upper, lower in _LEGS:
        embed = getattr(dossier, attr)
        out[attr] = _extract_rfc3161(embed, upper, lower)
    return out


def test_all_three_rfc3161_copies_are_byte_identical():
    secs = _sections()
    ref_name, ref = next(iter(secs.items()))
    for name, sec in secs.items():
        if sec == ref:
            continue
        # produce a useful failure: first differing line
        a, b = ref.splitlines(), sec.splitlines()
        first = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]),
                     min(len(a), len(b)))
        pytest.fail(
            "embedded RFC 3161 verifier DRIFT between %s and %s\n"
            "  first difference at normalised line %d:\n"
            "    %s: %r\n"
            "    %s: %r\n"
            "  (lines: %d vs %d)\n"
            "  Fix: re-extract the changed leg from the others; all three must "
            "carry the same implementation."
            % (ref_name, name, first + 1,
               ref_name, a[first] if first < len(a) else "<eof>",
               name, b[first] if first < len(b) else "<eof>",
               len(a), len(b)))


def test_each_rfc3161_section_is_nonempty_and_parses():
    # a section that silently became empty would make the comparison vacuous
    for attr, sec in _sections().items():
        assert len(sec) > 4000, "%s RFC 3161 section suspiciously small (%d)" % (
            attr, len(sec))
        assert "_x_verify_rfc3161" in sec, attr


def test_every_embed_parses_standalone():
    # each embed is spliced verbatim into the emitted verify_offline.py; if one
    # stops being valid Python the generated verifier will not run at all.
    names = [n for n in dir(dossier) if n.endswith("_CHECK_EMBED")
             or n.endswith("_CORE_EMBED")]
    assert names, "no embeds discovered"
    for n in names:
        src = getattr(dossier, n)
        if not isinstance(src, str):
            continue
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail("%s does not parse standalone: %s" % (n, e))
