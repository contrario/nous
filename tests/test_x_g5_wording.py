"""X-G5b -- the signer wording of the dossier verifiers, the v2 builder,
the GLM docstring and verify-cost (S426, ruling B, whole).

The X-G4 convention (tests/test_x_g4_wording.py): a sentence that calls
a signature "authentic", an "author signature" or a "verified identity"
names its scope in the same sentence. The dossier verifiers check the
manifest signature under the key the manifest carries and take no
expected signer, so their text drops the authorship term instead of
scoping it; the seven sidecar lines say "bound to the manifest" where
they said "authenticated", in dossier.py and in tb_check.py, its
tracked source. verify-cost --manifest compares a sha and
does not check the manifest signature, so its text says so. The printed
"signature verified" lines are the boundary of the ruling and stay.

The lint is blind to these surfaces (template literals); these tests
hold them. # __x_g5_wording_tests_v1__
"""
from __future__ import annotations

import argparse
import contextlib
import io
from pathlib import Path

import cli_verify_cost
import dossier
import glm_manifest
import offline_verifier_builder

REPO = Path(__file__).resolve().parent.parent
_VEC = REPO / "website" / ".well-known" / "nous" / "vsa-vectors" / "v1"

_OLD_OK = (
    "materiality classification authenticated",
    "predetermined-change envelope authenticated",
    "pre-commitment receipt authenticated",
    "envelope witness evidence authenticated",
    "closure witness evidence authenticated",
    "NOUS-TRACE evidence bundle authenticated",
    "bundle temporal-existence receipt authenticated",
)
_NEW_OK = (
    "materiality classification bound to the manifest",
    "predetermined-change envelope bound to the manifest",
    "pre-commitment receipt bound to the manifest",
    "envelope witness evidence bound to the manifest",
    "closure witness evidence bound to the manifest",
    "NOUS-TRACE evidence bundle bound to the dossier manifest",
    "bundle temporal-existence receipt bound to the manifest",
)


def _sources() -> dict[str, str]:
    out = {n: getattr(dossier, n) for n in dir(dossier)
           if n.startswith("VERIFY_OFFLINE_PY")
           and isinstance(getattr(dossier, n), str)}
    out["build_chain_net_verifier"] = dossier.build_chain_net_verifier()
    out["build_gap_witness_verifier"] = dossier.build_gap_witness_verifier()
    return out


def test_g5_t1_no_author_signature_in_dossier_verifiers() -> None:
    bad = sorted(n for n, s in _sources().items()
                 if "author signature" in s.lower())
    assert not bad, bad


def test_g5_t2_v2_builder_help_has_no_author_signature() -> None:
    src = offline_verifier_builder.build_offline_verifier_v2()
    assert "author signature" not in src.lower()
    assert "'Ed25519 signature and source identity are then " in src


def test_g5_t3_sidecar_ok_lines_bound_not_authenticated() -> None:
    text = Path(dossier.__file__).read_text(encoding="utf-8")
    assert [p for p in _OLD_OK if p in text] == []
    assert [text.count(p) for p in _NEW_OK] == [1] * 7


def _run_verify_cost() -> tuple[int, str]:
    ns = argparse.Namespace(file=str(_VEC / "cost.farkas.json"),
                            manifest=str(_VEC / "manifest.json"))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli_verify_cost.cmd_verify_cost(ns)
    return rc, buf.getvalue()


def test_g5_t4_verify_cost_output_says_signature_not_checked() -> None:
    rc, out = _run_verify_cost()
    assert rc == 0
    assert "the one the manifest names" in out
    assert "signature is not checked here." in out
    assert "signed manifest" not in out


def test_g5_t5_verify_cost_text_claims_no_signature() -> None:
    sub = argparse.ArgumentParser().add_subparsers()
    cli_verify_cost.build_verify_cost_parser(sub)
    p = sub.choices["verify-cost"]
    texts = [cli_verify_cost.__doc__ or "", p.description or "",
             p.format_help()]
    joined = " ".join(" ".join(t.split()) for t in texts)
    assert "signed manifest" not in joined
    assert "through the signature" not in joined
    assert joined.count("not checked") >= 3


def test_g5_t6_glm_docstring_names_the_pinned_allowlist() -> None:
    doc = " ".join((glm_manifest.verify_glm_manifest.__doc__ or "").split())
    assert "empty pinned allowlist" not in doc
    assert "no signing ceremony has run" not in doc
    assert "KNOWN_GLM_MANIFEST_PUBLIC_KEYS_B64" in doc
    assert len(glm_manifest.KNOWN_GLM_MANIFEST_PUBLIC_KEYS_B64) >= 1


def test_g5_t7_signature_verified_lines_stay() -> None:
    s = _sources()
    plain = 'print("OK   Ed25519 signature verified")'
    for n in ("VERIFY_OFFLINE_PY", "VERIFY_OFFLINE_PY_CHAIN",
              "VERIFY_OFFLINE_PY_FARKAS", "VERIFY_OFFLINE_PY_COVERAGE",
              "build_gap_witness_verifier"):
        assert plain in s[n], n
    assert ('print("OK   Ed25519 manifest signature verified")'
            in s["VERIFY_OFFLINE_PY_WITH_REKOR"])
    v2 = offline_verifier_builder.build_offline_verifier_v2()
    assert "print('OK   Ed25519 manifest signature verified')" in v2
