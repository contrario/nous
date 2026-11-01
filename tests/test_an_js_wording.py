"""AN-GATE-1 D5: the wording that M10 measured, pinned on the strings.

The VSA text says the input attestations bind canonical bodies, not
the shipped bytes; the ndec docstring says "evidences", since "proves"
belongs to Z3 and Farkas only. The frozen served verifiers keep their
old lines (RULING A4).

# __an_js_wording_v1__
"""
from __future__ import annotations

import ndec
import vsa_verifier

OLD_VSA = ("bind the shipped manifest/trace/cert bytes",
           "are these exact signed bytes")
NEW_VSA = ('print("OK   inputAttestations bind the canonical bodies of '
           'manifest/trace/cert")',
           '"is signed by the --expect-signer key; the canonical bodies of "\n'
           '        "manifest/trace/certificate are the ones it attests; the '
           'verdict "')


def test_d5_vsa_lines():
    t = vsa_verifier.VSA_VERIFY_OFFLINE_PY
    for old in OLD_VSA:
        assert old not in t, old
    for new in NEW_VSA:
        assert t.count(new) == 1, new


def test_d5_vsa_mismatch_line():
    # round 3 (REVIEW 2 item 10): the third VSA string the change moves
    t = vsa_verifier.VSA_VERIFY_OFFLINE_PY
    assert "(VSA names different bytes than the shipped artifact)" not in t
    assert t.count("(the shipped artifact is not the one the VSA attests)") \
        == 1


def test_d5_ndec_docstring():
    doc = " ".join(ndec.canonical_verifier_digests.__doc__.split())
    assert "provably" not in doc
    assert "evidences that it is an unmodified official NOUS" in doc
