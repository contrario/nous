"""Inc 1 PCE tests: byte-exact diff parity with the S187 blob, schema
validation, and per-step membership including the salami single-step case."""
from __future__ import annotations

import hashlib

import pytest

from envelope import (
    Envelope,
    EnvelopeError,
    MembershipResult,
    decide_per_step,
    diff_obligations,
    parse_canon,
    parse_envelope,
)

# S187 canon fixtures (verbatim from tests/test_s187b_policy_delta.py).
_SS = "SS:dummy"
_CANON_A = "NV:5\nEV:1\n" + _SS + "\nGA:approve\nGA:transfer\nGQ:approve:3\nSA:before(submit,approve)"
_CANON_WEAK = "NV:5\nEV:1\n" + _SS + "\nGA:approve\nGQ:approve:2\nSA:before(submit,approve)"
_CANON_STRONG = "NV:5\nEV:1\n" + _SS + "\nGA:approve\nGA:transfer\nGA:withdraw\nGQ:approve:4\nSA:before(submit,approve)"


def _sha(c: str) -> str:
    return hashlib.sha256(c.encode("utf-8")).hexdigest()


# ----- byte-exact parity with the S187 blob ------------------------------
class TestDiffParity:
    def test_weakening_strings_byte_exact(self) -> None:
        d = diff_obligations(_CANON_A, _CANON_WEAK)
        # blob/test asserts: "GA removed: transfer", "GQ approve quorum 3->2"
        assert "GA removed: transfer" in d["weakened"]
        assert "GQ approve quorum 3->2" in d["weakened"]
        assert d["strengthened"] == []

    def test_strengthening_strings_byte_exact(self) -> None:
        d = diff_obligations(_CANON_A, _CANON_STRONG)
        # blob/test asserts: "GA added: withdraw", "GQ approve quorum 3->4" strong
        assert "GA added: withdraw" in d["strengthened"]
        assert "GQ approve quorum 3->4" in d["strengthened"]
        assert d["weakened"] == []

    def test_constant_canon_no_delta(self) -> None:
        d = diff_obligations(_CANON_A, _CANON_A)
        assert d == {"weakened": [], "strengthened": []}

    def test_ordering_matches_blob(self) -> None:
        # blob order: SA, GA, GQ-removed, GQ-added, GQ-quorum; each sorted().
        prior = "SA:s2\nSA:s1\nGA:b\nGA:a\nGQ:x:3\nGQ:y:2"
        cur = "GA:c\nGQ:y:4"  # SA both removed, GA a/b removed + c added, GQ x removed, y 2->4
        d = diff_obligations(prior, cur)
        assert d["weakened"] == [
            "SA removed: s1", "SA removed: s2",
            "GA removed: a", "GA removed: b",
            "GQ removed: x",
        ]
        assert d["strengthened"] == ["GA added: c", "GQ y quorum 2->4"]

    def test_gq_action_with_colon_rsplit(self) -> None:
        # rsplit(":",1): action "ns:approve" quorum 3
        sa, ga, gq = parse_canon("GQ:ns:approve:3")
        assert gq == {"ns:approve": "3"}


# ----- schema validation -------------------------------------------------
def _min_env_doc() -> dict:
    return {
        "pce_schema_version": 1,
        "baseline_canon_sha256": _sha(_CANON_A),
        "per_step": {
            "SA": {"mutable": False},
            "GA": {"may_add": True, "may_remove": ["transfer"]},
            "GQ": {"may_add": True, "may_remove": False,
                   "quorum_bounds": {"approve": {"min": 2, "max": None}}},
        },
        "basis": "membership proof against a pre-committed envelope; "
                 "not a legal substantiality determination",
        "declared_utc": "2026-06-29T00:00:00+00:00",
    }


class TestSchema:
    def test_minimal_per_step_parses(self) -> None:
        env = parse_envelope(_min_env_doc())
        assert env.pce_schema_version == 1
        assert env.per_step.sa_mutable is False
        assert env.per_step.ga_may_remove == frozenset({"transfer"})
        assert env.per_step.gq.quorum_bounds["approve"] == (2, None)
        assert env.carries_cumulative is False

    def test_cumulative_carried_and_parsed(self) -> None:
        doc = _min_env_doc()
        doc["cumulative"] = {
            "SA": {"mutable": False},
            "GA": {"total_removable": ["transfer"], "total_addable": None},
            "GQ": {"quorum_drift_budget": {"approve": 1}},
        }
        env = parse_envelope(doc)
        assert env.carries_cumulative is True
        assert env.cumulative.gq_quorum_drift_budget == {"approve": 1}
        assert env.cumulative.ga_total_removable == frozenset({"transfer"})

    def test_basis_must_disclaim(self) -> None:
        doc = _min_env_doc()
        doc["basis"] = "this is a proof of compliance"
        with pytest.raises(EnvelopeError, match="disclaim substantiality"):
            parse_envelope(doc)

    def test_bad_schema_version_refused(self) -> None:
        doc = _min_env_doc()
        doc["pce_schema_version"] = 2
        with pytest.raises(EnvelopeError, match="unsupported"):
            parse_envelope(doc)

    def test_bad_baseline_sha_refused(self) -> None:
        doc = _min_env_doc()
        doc["baseline_canon_sha256"] = "deadbeef"
        with pytest.raises(EnvelopeError, match="64-hex"):
            parse_envelope(doc)

    def test_quorum_max_below_min_refused(self) -> None:
        doc = _min_env_doc()
        doc["per_step"]["GQ"]["quorum_bounds"]["approve"] = {"min": 5, "max": 2}
        with pytest.raises(EnvelopeError, match="max 2 < min 5"):
            parse_envelope(doc)

    def test_negative_drift_budget_refused(self) -> None:
        doc = _min_env_doc()
        doc["cumulative"] = {"SA": {}, "GA": {}, "GQ": {"quorum_drift_budget": {"approve": -1}}}
        with pytest.raises(EnvelopeError, match="non-negative"):
            parse_envelope(doc)


# ----- per-step membership ----------------------------------------------
class TestPerStepDecider:
    def test_within_quorum_drop_to_min(self) -> None:
        # 3->2, min=2, transfer removal pre-declared -> WITHIN
        env = parse_envelope(_min_env_doc())
        r = decide_per_step(env, _CANON_A, _CANON_WEAK)
        assert isinstance(r, MembershipResult)
        assert r.within is True, r.breakouts
        assert r.breakouts == ()

    def test_outside_quorum_below_min(self) -> None:
        # 3->1, min=2 -> OUTSIDE on the quorum, exact breakout
        env = parse_envelope(_min_env_doc())
        cur = "GA:approve\nGA:transfer\nGQ:approve:1\nSA:before(submit,approve)\nNV:5\nEV:1\n" + _SS
        r = decide_per_step(env, _CANON_A, cur)
        assert r.within is False
        assert any("quorum 1 outside [2,inf]" in b for b in r.breakouts)

    def test_outside_undeclared_ga_removal(self) -> None:
        # remove 'approve' (not in may_remove=['transfer']) -> OUTSIDE
        env = parse_envelope(_min_env_doc())
        cur = "GA:transfer\nGQ:approve:3\nSA:before(submit,approve)\nNV:5\nEV:1\n" + _SS
        r = decide_per_step(env, _CANON_A, cur)
        assert r.within is False
        assert any("GA removed: approve" in b and "not pre-declared" in b for b in r.breakouts)

    def test_outside_sa_mutation_when_immutable(self) -> None:
        env = parse_envelope(_min_env_doc())
        cur = "GA:approve\nGA:transfer\nGQ:approve:3\nSA:after(approve,submit)\nNV:5\nEV:1\n" + _SS
        r = decide_per_step(env, _CANON_A, cur)
        assert r.within is False
        # SA changed = one removed + one added; both flagged immutable
        assert any("SA removed: before(submit,approve)" in b for b in r.breakouts)
        assert any("SA added: after(approve,submit)" in b for b in r.breakouts)

    def test_within_strengthening_default_admissible(self) -> None:
        # add withdraw, quorum 3->4 (within [2,inf]) -> WITHIN
        env = parse_envelope(_min_env_doc())
        r = decide_per_step(env, _CANON_A, _CANON_STRONG)
        assert r.within is True, r.breakouts

    def test_salami_single_step_within_but_recorded(self) -> None:
        # one 3->2 step is within per-step; the cumulative risk is NOT caught
        # here (Inc 2). This test documents the gap the cumulative decider closes.
        env = parse_envelope(_min_env_doc())
        r = decide_per_step(env, _CANON_A, _CANON_WEAK)
        assert r.within is True
        assert "GQ approve quorum 3->2" in r.weakened  # the drift IS recorded


# ----- LIVE-BLOB CROSS-CHECK (server-only; the commit gate) --------------
# Drives the actual emitted S187 continuity verifier and asserts its
# segment_policy_delta equals the lifted diff_obligations on the same canons.
# Skips where the continuity harness is unavailable (sandbox); MUST pass on
# the server before Inc 1 is committed -- a red here means the lift is wrong
# and Inc 2 would inherit the bug.
import json as _json

import pytest as _pytest


def _run_blob_delta(tmp_path, canons):
    _pytest.importorskip("continuity_ledger")
    _pytest.importorskip("continuity_verifier")
    h = _pytest.importorskip("test_s187b_policy_delta")
    op, cp = h._keys(tmp_path)
    ledger = h._build(tmp_path, op, cp, canons)
    prior = h._prior_and_proof(tmp_path, ledger)
    script = h._emit(tmp_path)
    res = h._verify(
        script, ledger, cp_pub=tmp_path / "cp_pub.pem",
        prior_note=prior, as_json=True,
    )
    return _json.loads(res["out"].strip().splitlines()[-1])["segment_policy_delta"]


class TestLiveBlobParity:
    def test_lift_matches_blob_weakening(self, tmp_path) -> None:
        canons = [_CANON_A] * 5 + [_CANON_WEAK] * 4
        blob = _run_blob_delta(tmp_path, canons)
        mine = diff_obligations(_CANON_A, _CANON_WEAK)
        assert blob is not None
        assert blob["weakened"] == mine["weakened"]
        assert blob["strengthened"] == mine["strengthened"]

    def test_lift_matches_blob_strengthening(self, tmp_path) -> None:
        canons = [_CANON_A] * 5 + [_CANON_STRONG] * 4
        blob = _run_blob_delta(tmp_path, canons)
        mine = diff_obligations(_CANON_A, _CANON_STRONG)
        assert blob is not None
        assert blob["weakened"] == mine["weakened"]
        assert blob["strengthened"] == mine["strengthened"]
