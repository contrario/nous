"""S137 prior-link coverage re-derivation teeth.

The blocking-net-full offline verifier (build_chain_net_verifier output)
re-proves, per PRIOR link, that the link's own declared blocking net actually
covers its threshold -- closing the gap that net-containment +
hop-monotonicity + current-link coverage leave open: a signed prior link
could ship a gapped or omitting Farkas cert that is sha-consistent with its
own manifest, and the chain would still pass. _walk_prior_coverage re-derives
each prior link's gap disjunct set from the sha-gated per-link source and the
sha-gated threshold_expr, requires a bijection against the sha-gated cert, and
refutes every disjunct by rational arithmetic.

These tests drive the EMBEDDED _walk_prior_coverage directly (the embed is the
TCB a third party runs), laying out a synthetic chain/ under a monkeypatched
ROOT:
  - a valid issuer-built prior cert PASSES (rc == 0);
  - a prior link declaring no coverage is SKIPPED (rc == 0);
  - a sha-consistent but GAPPED / forged cert (a disjunct dropped, a
    multiplier negated, a cert duplicated, a surplus cert added) -- written to
    disk with coverage_farkas_sha256 RE-POINTED at the mutated file so the
    O(1) sha gate PASSES -- is CAUGHT (rc != 0). This is exactly the
    trust-surface hole the feature closes: the bijection / multiplier check,
    not the sha gate, is what catches it;
  - a source/cert mismatch (source swapped in with its own source_sha256, cert
    kept) is CAUGHT, because the re-derived disjuncts no longer match;
  - a cert-file tamper without re-pointing the sha is CAUGHT by the O(1) gate
    (pre-existing behavior, asserted for completeness).

BOUNDARY: this drives the embed function on a synthetic layout; full
end-to-end issuance + emission is covered by test_s127_net_e2e.py. It proves
teeth, not universal equivalence. __s137_priorcov_test_v1__
"""
from __future__ import annotations

import copy
import hashlib
import json
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

import coverage_farkas
import coverage_minilang
import dossier


def _embed_ns() -> dict:
    src = dossier.build_chain_net_verifier()
    code = compile(src, "<embed:build_chain_net_verifier>", "exec")
    ns: dict = {"__file__": "<embed:build_chain_net_verifier>"}
    exec(code, ns)  # noqa: S102
    return ns


def _src(signal_threshold: str) -> str:
    return (
        "policy p0 {\n"
        "  kind: monitor\n"
        "  signal: amount > " + signal_threshold + "\n"
        "  action: block\n"
        "}\n"
    )


def _bundle(source: str, threshold: str) -> dict:
    t_ast = coverage_minilang.ml_parse(threshold)
    blk = coverage_minilang.ml_scan_blocking_signals(source)
    return coverage_farkas.serialize_bundle(
        t_ast, blk, threshold_expr=threshold
    )


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _layout(
    tmp: Path,
    source: str,
    far_doc: dict,
    far_sha_field: Any = None,
    src_sha_field: Any = None,
) -> list:
    chain = tmp / "chain"
    chain.mkdir(parents=True, exist_ok=True)
    src_bytes = source.encode("utf-8")
    far_bytes = json.dumps(far_doc).encode("utf-8")
    (chain / "000_source.nous").write_bytes(src_bytes)
    (chain / "000_coverage.farkas.json").write_bytes(far_bytes)
    link = {
        "coverage_farkas_sha256": (
            far_sha_field if far_sha_field is not None else _sha(far_bytes)
        ),
        "source_sha256": (
            src_sha_field if src_sha_field is not None else _sha(src_bytes)
        ),
    }
    return [
        ("000_manifest.json", link),
        ("manifest.json (current)", {}),
    ]


def _run(ns: dict, tmp: Path, ordered: list) -> int:
    ns["ROOT"] = tmp
    return ns["_walk_prior_coverage"](ordered)


def test_valid_prior_cert_passes(tmp_path: Path) -> None:
    ns = _embed_ns()
    source = _src("500")
    far = _bundle(source, "amount > 1000")
    ordered = _layout(tmp_path, source, far)
    assert _run(ns, tmp_path, ordered) == 0


def test_prior_link_without_coverage_skipped(tmp_path: Path) -> None:
    ns = _embed_ns()
    ordered = [
        ("000_manifest.json", {"source_sha256": "0" * 64}),
        ("manifest.json (current)", {}),
    ]
    assert _run(ns, tmp_path, ordered) == 0


def _m_drop(doc: dict) -> dict:
    if doc["certs"]:
        doc["certs"] = doc["certs"][1:]
    return doc


def _m_neg(doc: dict) -> dict:
    if doc["certs"] and doc["certs"][0]["multipliers"]:
        doc["certs"][0]["multipliers"][0] = "-1"
    return doc


def _m_dup(doc: dict) -> dict:
    if doc["certs"]:
        doc["certs"].append(copy.deepcopy(doc["certs"][0]))
    return doc


def _m_surplus(doc: dict) -> dict:
    if doc["certs"]:
        extra = copy.deepcopy(doc["certs"][0])
        co = dict(extra["constraints"][0]["coeffs"])
        co[""] = str(Fraction(co.get("", "0")) + 99)
        extra["constraints"][0]["coeffs"] = co
        doc["certs"].append(extra)
    return doc


@pytest.mark.parametrize(
    "name,mutator",
    [("drop", _m_drop), ("neg_mult", _m_neg), ("dup", _m_dup),
     ("surplus", _m_surplus)],
    ids=["drop", "neg_mult", "dup", "surplus"],
)
def test_sha_consistent_forged_prior_cert_caught(
    tmp_path: Path, name: str, mutator: Any
) -> None:
    ns = _embed_ns()
    source = _src("500")
    far = _bundle(source, "amount > 1000")
    mdoc = mutator(copy.deepcopy(far))
    # coverage_farkas_sha256 re-pointed at the MUTATED bytes by _layout
    # (default), so the O(1) sha gate PASSES; only re-derivation catches it.
    ordered = _layout(tmp_path, source, mdoc)
    assert _run(ns, tmp_path, ordered) != 0


def test_source_cert_mismatch_caught(tmp_path: Path) -> None:
    ns = _embed_ns()
    source_a = _src("500")
    far = _bundle(source_a, "amount > 1000")
    source_b = _src("900")
    # source_b written with its OWN source_sha256 (gate passes); cert is for
    # source_a -> re-derived disjuncts no longer match the carried cert.
    ordered = _layout(tmp_path, source_b, far)
    assert _run(ns, tmp_path, ordered) != 0


def test_far_sha_mismatch_caught_by_gate(tmp_path: Path) -> None:
    ns = _embed_ns()
    source = _src("500")
    far = _bundle(source, "amount > 1000")
    # coverage_farkas_sha256 NOT re-pointed: O(1) gate alone catches it.
    ordered = _layout(tmp_path, source, far, far_sha_field="0" * 64)
    assert _run(ns, tmp_path, ordered) != 0
