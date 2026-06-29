"""NOUS Predetermined-Change Envelope (PCE).

Article 43(4) / Annex IV point 2(f) machine-checkable change envelope: the
EU-AI-Act software analogue of the FDA Predetermined Change Control Plan
(Section 515C FD&C Act). A provider declares, at initial conformity
assessment, the admissible region of obligation transitions; every later
build's structural obligation delta (S187: SA/GA/GQ weakened/strengthened)
is decided against it offline.

Dual-dimension from the first anchor:
  per_step   -- per-transition admissibility (Inc 1 decider, here)
  cumulative -- path invariant over the append-only change chain from the
                assessed baseline (carried, signed, anchorable NOW; decider
                banked to Inc 2). A pre-committed anchored envelope cannot be
                re-anchored without defeating temporal pre-commitment, so the
                schema must carry the cumulative dimension before its decider
                exists.

Honest boundary (inviolable):
  - NOUS PROVES (set ops over root-committed canon fields) that the delta is
    within the declared envelope. Within => not a substantial modification is
    the deduction Art 43(4) itself supplies; outside => flagged, never a legal
    determination. The notified body adjudicates.
  - The transparency anchor EVIDENCES pre-commitment-in-time, not envelope
    adequacy. NOUS runs no CA and certifies no identity.

The obligation-canon grammar and the diff classification here REPLICATE the
S187 continuity-verifier blob (_CONTINUITY_VERIFY_OFFLINE_B64) byte-exact;
test_pce_diff_parity asserts equality on the S187 canon fixtures.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class EnvelopeError(ValueError):
    """A PCE is malformed, undecidable, or self-contradictory. Fail closed."""


# --------------------------------------------------------------------------
# Obligation-canon parse + diff -- byte-exact lift of the S187 blob.
# Blob source (decoded continuity_verifier._CONTINUITY_VERIFY_OFFLINE_B64,
# _obs_set + the SA/GA/GQ diff loop): line-prefix split, sorted set diffs,
# GQ direction by signed integer delta.
# --------------------------------------------------------------------------
def parse_canon(canon: str) -> tuple[set[str], set[str], dict[str, str]]:
    """Parse an obligations_canon string into (SA, GA, GQ) obligation sets.

    SA/GA are sets of the post-prefix remainder; GQ maps action -> quorum
    string (rsplit on the last ':' so action names may contain ':').
    Byte-exact replica of the blob _obs_set.
    """
    sa: set[str] = set()
    ga: set[str] = set()
    gq: dict[str, str] = {}
    for ln in canon.split("\n"):
        if ln.startswith("SA:"):
            sa.add(ln[3:])
        elif ln.startswith("GA:"):
            ga.add(ln[3:])
        elif ln.startswith("GQ:"):
            parts = ln[3:].rsplit(":", 1)
            if len(parts) == 2:
                gq[parts[0]] = parts[1]
    return sa, ga, gq


def diff_obligations(prior_canon: str, current_canon: str) -> dict[str, list[str]]:
    """Structural obligation delta prior -> current.

    Returns {"weakened": [...], "strengthened": [...]} with transition strings
    byte-exact to the S187 blob. Ordering matches the blob: SA, GA, GQ-removed,
    GQ-added, GQ-quorum-changed, each inner group sorted().
    """
    psa, pga, pgq = parse_canon(prior_canon)
    csa, cga, cgq = parse_canon(current_canon)
    weak: list[str] = []
    strong: list[str] = []
    for x in sorted(psa - csa):
        weak.append("SA removed: " + x)
    for x in sorted(csa - psa):
        strong.append("SA added: " + x)
    for x in sorted(pga - cga):
        weak.append("GA removed: " + x)
    for x in sorted(cga - pga):
        strong.append("GA added: " + x)
    for a in sorted(set(pgq) - set(cgq)):
        weak.append("GQ removed: " + a)
    for a in sorted(set(cgq) - set(pgq)):
        strong.append("GQ added: " + a + ":" + cgq[a])
    for a in sorted(set(pgq) & set(cgq)):
        if pgq[a] != cgq[a]:
            try:
                dlt = int(cgq[a]) - int(pgq[a])
            except ValueError:
                dlt = 0
            msg = "GQ " + a + " quorum " + pgq[a] + "->" + cgq[a]
            if dlt < 0:
                weak.append(msg)
            else:
                strong.append(msg)
    return {"weakened": weak, "strengthened": strong}


# --------------------------------------------------------------------------
# PCE schema -- dual-dimension, drop-when-None on each axis.
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class GQPerStepRule:
    may_add: bool
    may_remove: bool
    quorum_bounds: dict[str, tuple[int, Optional[int]]]  # action -> (min, max|None)


@dataclass(frozen=True)
class PerStepRules:
    sa_mutable: bool
    ga_may_add: bool
    ga_may_remove: frozenset[str]  # actions whose removal is admissible
    gq: GQPerStepRule


@dataclass(frozen=True)
class CumulativeRules:
    """Carried + signed + anchored at v1; decider lands Inc 2."""
    sa_mutable: bool
    ga_total_removable: Optional[frozenset[str]]
    ga_total_addable: Optional[frozenset[str]]
    gq_quorum_drift_budget: dict[str, int]  # action -> max |cumulative drift|


@dataclass(frozen=True)
class Envelope:
    pce_schema_version: int
    baseline_canon_sha256: str
    per_step: PerStepRules
    cumulative: Optional[CumulativeRules]
    basis: str
    declared_utc: Optional[str]

    @property
    def carries_cumulative(self) -> bool:
        return self.cumulative is not None


_BASIS_DISCLAIMER = "not a legal substantiality determination"


def _req(d: dict, key: str, typ: type, ctx: str):
    if key not in d:
        raise EnvelopeError(f"missing required field {key!r} in {ctx}")
    v = d[key]
    if not isinstance(v, typ) or (typ is bool and not isinstance(v, bool)):
        raise EnvelopeError(
            f"field {key!r} in {ctx} must be {typ.__name__}, got {type(v).__name__}"
        )
    return v


def _parse_gq_bounds(raw: dict, ctx: str) -> dict[str, tuple[int, Optional[int]]]:
    out: dict[str, tuple[int, Optional[int]]] = {}
    for action, b in raw.items():
        if not isinstance(action, str):
            raise EnvelopeError(f"non-string GQ action in {ctx}")
        if not isinstance(b, dict):
            raise EnvelopeError(f"quorum_bounds[{action!r}] must be an object in {ctx}")
        lo = b.get("min")
        hi = b.get("max")
        if not isinstance(lo, int) or isinstance(lo, bool):
            raise EnvelopeError(f"quorum_bounds[{action!r}].min must be int in {ctx}")
        if hi is not None and (not isinstance(hi, int) or isinstance(hi, bool)):
            raise EnvelopeError(
                f"quorum_bounds[{action!r}].max must be int or null in {ctx}"
            )
        if hi is not None and hi < lo:
            raise EnvelopeError(
                f"quorum_bounds[{action!r}] max {hi} < min {lo} in {ctx}"
            )
        out[action] = (lo, hi)
    return out


def parse_envelope(doc: dict) -> Envelope:
    """Validate and parse a PCE document. Raises EnvelopeError, never guesses."""
    if not isinstance(doc, dict):
        raise EnvelopeError("PCE is not a JSON object")

    ver = _req(doc, "pce_schema_version", int, "PCE")
    if ver != 1:
        raise EnvelopeError(f"unsupported pce_schema_version {ver}; expected 1")

    baseline = _req(doc, "baseline_canon_sha256", str, "PCE")
    if len(baseline) != 64 or any(c not in "0123456789abcdef" for c in baseline):
        raise EnvelopeError("baseline_canon_sha256 is not a 64-hex sha256")

    basis = _req(doc, "basis", str, "PCE")
    if _BASIS_DISCLAIMER not in basis:
        raise EnvelopeError(
            f"PCE basis must disclaim substantiality "
            f"(must contain {_BASIS_DISCLAIMER!r}); refusing to present "
            f"membership as a legal determination"
        )

    ps = _req(doc, "per_step", dict, "PCE")
    sa_block = _req(ps, "SA", dict, "per_step")
    ga_block = _req(ps, "GA", dict, "per_step")
    gq_block = _req(ps, "GQ", dict, "per_step")

    sa_mutable = _req(sa_block, "mutable", bool, "per_step.SA")
    ga_may_add = _req(ga_block, "may_add", bool, "per_step.GA")
    ga_rm_raw = ga_block.get("may_remove", [])
    if not isinstance(ga_rm_raw, list) or any(not isinstance(x, str) for x in ga_rm_raw):
        raise EnvelopeError("per_step.GA.may_remove must be a list of strings")
    gq_may_add = _req(gq_block, "may_add", bool, "per_step.GQ")
    gq_may_remove = _req(gq_block, "may_remove", bool, "per_step.GQ")
    gq_bounds = _parse_gq_bounds(gq_block.get("quorum_bounds", {}), "per_step.GQ")

    per_step = PerStepRules(
        sa_mutable=sa_mutable,
        ga_may_add=ga_may_add,
        ga_may_remove=frozenset(ga_rm_raw),
        gq=GQPerStepRule(
            may_add=gq_may_add, may_remove=gq_may_remove, quorum_bounds=gq_bounds
        ),
    )

    cumulative: Optional[CumulativeRules] = None
    cum = doc.get("cumulative")
    if cum is not None:
        if not isinstance(cum, dict):
            raise EnvelopeError("cumulative must be an object or absent")
        c_sa = cum.get("SA", {})
        c_ga = cum.get("GA", {})
        c_gq = cum.get("GQ", {})
        if not isinstance(c_sa, dict) or not isinstance(c_ga, dict) or not isinstance(c_gq, dict):
            raise EnvelopeError("cumulative.SA/GA/GQ must each be objects")
        c_sa_mut = bool(c_sa.get("mutable", sa_mutable))
        c_rm = c_ga.get("total_removable")
        c_ad = c_ga.get("total_addable")
        if c_rm is not None and (not isinstance(c_rm, list) or any(not isinstance(x, str) for x in c_rm)):
            raise EnvelopeError("cumulative.GA.total_removable must be list of strings or null")
        if c_ad is not None and (not isinstance(c_ad, list) or any(not isinstance(x, str) for x in c_ad)):
            raise EnvelopeError("cumulative.GA.total_addable must be list of strings or null")
        budget_raw = c_gq.get("quorum_drift_budget", {})
        if not isinstance(budget_raw, dict):
            raise EnvelopeError("cumulative.GQ.quorum_drift_budget must be an object")
        budget: dict[str, int] = {}
        for a, v in budget_raw.items():
            if not isinstance(a, str) or not isinstance(v, int) or isinstance(v, bool) or v < 0:
                raise EnvelopeError(
                    "cumulative.GQ.quorum_drift_budget values must be non-negative ints"
                )
            budget[a] = v
        cumulative = CumulativeRules(
            sa_mutable=c_sa_mut,
            ga_total_removable=frozenset(c_rm) if c_rm is not None else None,
            ga_total_addable=frozenset(c_ad) if c_ad is not None else None,
            gq_quorum_drift_budget=budget,
        )

    return Envelope(
        pce_schema_version=ver,
        baseline_canon_sha256=baseline,
        per_step=per_step,
        cumulative=cumulative,
        basis=basis,
        declared_utc=(doc.get("declared_utc") if isinstance(doc.get("declared_utc"), str) else None),
    )


# --------------------------------------------------------------------------
# Per-step membership decider (Inc 1).
# A delta is WITHIN iff every transition is admitted by per_step.
# Strengthening is admissible by default (a stricter policy cannot reduce
# Section-2 compliance) UNLESS an immutable axis forbids the change.
# Each refused transition is reported as an exact breakout reason.
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class MembershipResult:
    within: bool
    breakouts: tuple[str, ...]   # exact transitions outside the envelope
    weakened: tuple[str, ...]
    strengthened: tuple[str, ...]


def _gq_action_of(transition: str) -> Optional[str]:
    # "GQ <action> quorum a->b" / "GQ removed: <action>" / "GQ added: <action>:k"
    if transition.startswith("GQ removed: "):
        return transition[len("GQ removed: "):]
    if transition.startswith("GQ added: "):
        return transition[len("GQ added: "):].rsplit(":", 1)[0]
    if transition.startswith("GQ ") and " quorum " in transition:
        return transition[len("GQ "):transition.index(" quorum ")]
    return None


def _gq_new_quorum(transition: str) -> Optional[int]:
    if " quorum " in transition and "->" in transition:
        try:
            return int(transition.rsplit("->", 1)[1])
        except ValueError:
            return None
    if transition.startswith("GQ added: "):
        try:
            return int(transition.rsplit(":", 1)[1])
        except ValueError:
            return None
    return None


def decide_per_step(env: Envelope, prior_canon: str, current_canon: str) -> MembershipResult:
    """Decide whether the prior->current delta is within env.per_step."""
    delta = diff_obligations(prior_canon, current_canon)
    weak = tuple(delta["weakened"])
    strong = tuple(delta["strengthened"])
    breakouts: list[str] = []
    ps = env.per_step

    for t in weak:
        if t.startswith("SA removed: "):
            if not ps.sa_mutable:
                breakouts.append(t + " (SA immutable)")
        elif t.startswith("GA removed: "):
            action = t[len("GA removed: "):]
            if action not in ps.ga_may_remove:
                breakouts.append(t + " (GA removal not pre-declared)")
        elif t.startswith("GQ removed: "):
            if not ps.gq.may_remove:
                breakouts.append(t + " (GQ removal forbidden)")
        elif t.startswith("GQ ") and " quorum " in t:
            action = _gq_action_of(t)
            newq = _gq_new_quorum(t)
            bound = ps.gq.quorum_bounds.get(action) if action is not None else None
            if bound is None:
                breakouts.append(t + " (no quorum bound declared for this action)")
            elif newq is None:
                breakouts.append(t + " (uninterpretable quorum)")
            else:
                lo, hi = bound
                if newq < lo or (hi is not None and newq > hi):
                    breakouts.append(
                        t + f" (quorum {newq} outside [{lo},{'inf' if hi is None else hi}])"
                    )
        else:
            breakouts.append(t + " (unrecognised weakening transition)")

    for t in strong:
        if t.startswith("SA added: "):
            if not ps.sa_mutable:
                breakouts.append(t + " (SA immutable)")
        elif t.startswith("GA added: "):
            if not ps.ga_may_add:
                breakouts.append(t + " (GA addition forbidden)")
        elif t.startswith("GQ added: "):
            if not ps.gq.may_add:
                breakouts.append(t + " (GQ addition forbidden)")
            else:
                action = _gq_action_of(t)
                newq = _gq_new_quorum(t)
                bound = ps.gq.quorum_bounds.get(action) if action is not None else None
                if bound is not None and newq is not None:
                    lo, hi = bound
                    if newq < lo or (hi is not None and newq > hi):
                        breakouts.append(
                            t + f" (quorum {newq} outside [{lo},{'inf' if hi is None else hi}])"
                        )
        elif t.startswith("GQ ") and " quorum " in t:
            action = _gq_action_of(t)
            newq = _gq_new_quorum(t)
            bound = ps.gq.quorum_bounds.get(action) if action is not None else None
            if bound is not None and newq is not None:
                lo, hi = bound
                if newq < lo or (hi is not None and newq > hi):
                    breakouts.append(
                        t + f" (quorum {newq} outside [{lo},{'inf' if hi is None else hi}])"
                    )
        else:
            breakouts.append(t + " (unrecognised strengthening transition)")

    return MembershipResult(
        within=(len(breakouts) == 0),
        breakouts=tuple(breakouts),
        weakened=weak,
        strengthened=strong,
    )


# --------------------------------------------------------------------------
# Cumulative path invariant (Inc 2): the salami-laundering defence.
#
# The composed delta is measured against the PRE-COMMITTED baseline_canon
# (PCE.baseline_canon_sha256), not the previous step. Drift = |current vs
# baseline|. Because the reference is FIXED, oscillating per-step changes
# cannot accumulate: no build's endpoint can exceed budget D from baseline
# without that build's own cumulative check failing. Salami is defeated by
# construction, not detected heuristically.
#
# Endpoint comparison is O(1) in chain length; the S120 prior_digest chain
# (verified separately by the dossier) proves current descends from the
# baseline-committing build. PROVES tier: set ops + integer drift bound;
# fails closed on any composed transition the cumulative envelope does not
# explicitly admit.
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class CumulativeResult:
    within: bool
    breakouts: tuple[str, ...]            # composed transitions outside the cumulative envelope
    composed_weakened: tuple[str, ...]
    composed_strengthened: tuple[str, ...]


def _gq_quorum_pair(transition: str) -> Optional[tuple[int, int]]:
    # "GQ <action> quorum X->Y" -> (X, Y)
    if " quorum " not in transition or "->" not in transition:
        return None
    try:
        tail = transition.split(" quorum ", 1)[1]
        prev_s, cur_s = tail.split("->", 1)
        return int(prev_s), int(cur_s)
    except ValueError:
        return None


def decide_cumulative(
    env: Envelope, baseline_canon: str, current_canon: str
) -> CumulativeResult:
    """Decide whether the composed baseline->current delta is within
    env.cumulative. Raises if no cumulative envelope was declared."""
    if env.cumulative is None:
        raise EnvelopeError(
            "no cumulative envelope declared; cannot decide cumulative membership "
            "(the envelope carries per_step only)"
        )
    cum = env.cumulative
    delta = diff_obligations(baseline_canon, current_canon)
    weak = tuple(delta["weakened"])
    strong = tuple(delta["strengthened"])
    breakouts: list[str] = []

    # SA: cumulatively immutable unless declared mutable.
    for t in weak + strong:
        if t.startswith("SA removed: ") or t.startswith("SA added: "):
            if not cum.sa_mutable:
                breakouts.append(t + " (SA cumulatively immutable)")

    # GA: composed removals must lie in total_removable; additions in
    # total_addable (None addable => unbounded additions admissible, since
    # adding a gated action strengthens oversight).
    for t in weak:
        if t.startswith("GA removed: "):
            action = t[len("GA removed: "):]
            if cum.ga_total_removable is None or action not in cum.ga_total_removable:
                breakouts.append(t + " (GA removal not in cumulative removable set)")
    for t in strong:
        if t.startswith("GA added: "):
            action = t[len("GA added: "):]
            if cum.ga_total_addable is not None and action not in cum.ga_total_addable:
                breakouts.append(t + " (GA addition not in cumulative addable set)")

    # GQ: a gated-quorum action removed cumulatively drops an oversight gate
    # (weakening); not admissible (no cumulative provision admits it).
    for t in weak:
        if t.startswith("GQ removed: "):
            breakouts.append(t + " (cumulative GQ removal drops an oversight gate)")
    # GQ added cumulatively strengthens; admissible by default.

    # GQ quorum drift (action present in both): |Y-X| <= budget. Checked in
    # BOTH directions -- a large strengthening can change intended purpose,
    # which Art 3(23) also keys on.
    for t in weak + strong:
        if t.startswith("GQ ") and " quorum " in t:
            action = _gq_action_of(t)
            pair = _gq_quorum_pair(t)
            if action is None or pair is None:
                breakouts.append(t + " (uninterpretable cumulative quorum drift)")
                continue
            prev_q, cur_q = pair
            drift = abs(cur_q - prev_q)
            budget = cum.gq_quorum_drift_budget.get(action)
            if budget is None:
                breakouts.append(
                    t + f" (cumulative drift {drift}; no drift budget declared for {action})"
                )
            elif drift > budget:
                breakouts.append(
                    t + f" (cumulative drift {drift} > budget {budget})"
                )

    return CumulativeResult(
        within=(len(breakouts) == 0),
        breakouts=tuple(breakouts),
        composed_weakened=weak,
        composed_strengthened=strong,
    )
