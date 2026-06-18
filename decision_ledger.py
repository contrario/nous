"""Decision-ledger presentation view over a signed NOUS trace.  # __s152_u1_decision_ledger_module_v1__

PRESENTATION, NOT VERIFICATION. This module reads the authorization decisions
already recorded in a trace and presents their distribution for an auditor's
own review. It does NOT re-verify signatures, does NOT prove a decision correct,
does NOT prove the principal was authorized or the oversight meaningful (no
standard for "meaningful" oversight exists -- Green 2021), and NEVER gates a
verdict. The cryptographic proof that each decision verb is bound to its exact
(seq, action, proof envelope) is the job of `nous verify` / verify_conformance;
run that for the signature proof. This view surfaces the decision distribution
so the auditor's own rubber-stamping / "false comfort" test runs on data, not
trust. A denial or override is oversight EXERCISED, not a violation.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from nous_trace import TraceEnvelope, load_trace

_DECISION_VERBS: tuple[str, ...] = ("approved", "denied", "overridden")


def _parse_utc(value: str) -> Optional[datetime]:
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class ActionBreakdown(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    action: str = Field(min_length=1)
    approved: int = Field(default=0, ge=0)
    denied: int = Field(default=0, ge=0)
    overridden: int = Field(default=0, ge=0)
    total: int = Field(ge=0)


class QuorumBreakdown(BaseModel):  # __s154_u2_quorum_section_v1__
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    seq: int = Field(ge=0)
    action: str = Field(min_length=1)
    valid_distinct_approvers: int = Field(ge=0)
    approver_key_fps: tuple[str, ...] = Field(default=())
    decision_verbs_seen: tuple[str, ...] = Field(default=())
    k_declared: Optional[int] = Field(default=None)


class LedgerReport(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    world_name: str = Field(min_length=1)
    decisions_total: int = Field(ge=0)
    approved: int = Field(default=0, ge=0)
    denied: int = Field(default=0, ge=0)
    overridden: int = Field(default=0, ge=0)
    distinct_principals: int = Field(ge=0)
    principal_diversity: float = Field(ge=0.0, le=1.0)
    time_span_seconds: Optional[float] = Field(default=None)
    earliest_utc: Optional[str] = Field(default=None)
    latest_utc: Optional[str] = Field(default=None)
    per_action: tuple[ActionBreakdown, ...] = Field(default=())
    quorum: tuple[QuorumBreakdown, ...] = Field(default=())  # __s154_u2_quorum_section_v1__


def build_ledger(
    envelope: TraceEnvelope,
    quorum_by_action: Optional[dict[str, int]] = None,  # __s154_u2_quorum_section_v1__
) -> LedgerReport:
    verb_counts: Counter[str] = Counter()
    principals: set[str] = set()
    parsed_times: list[datetime] = []
    raw_times: list[str] = []
    per_action_counts: dict[str, Counter[str]] = {}

    for event in envelope.events:
        auth = event.authorization
        if auth is None:
            continue
        verb = auth.decision
        if verb not in _DECISION_VERBS:
            raise ValueError(
                f"unknown decision verb {verb!r} at seq {event.seq}; "
                f"expected one of {_DECISION_VERBS}"
            )
        verb_counts[verb] += 1
        principals.add(auth.principal_id)
        raw_times.append(auth.timestamp_utc)
        parsed = _parse_utc(auth.timestamp_utc)
        if parsed is not None:
            parsed_times.append(parsed)
        action = event.action if event.action is not None else "<unspecified>"
        per_action_counts.setdefault(action, Counter())[verb] += 1

    total = sum(verb_counts.values())
    distinct = len(principals)
    diversity = (distinct / total) if total else 0.0

    span_seconds: Optional[float] = None
    earliest: Optional[str] = None
    latest: Optional[str] = None
    if parsed_times:
        lo = min(parsed_times)
        hi = max(parsed_times)
        span_seconds = (hi - lo).total_seconds()
        earliest = lo.isoformat()
        latest = hi.isoformat()

    breakdowns: list[ActionBreakdown] = []
    for action in sorted(per_action_counts):
        counts = per_action_counts[action]
        breakdowns.append(
            ActionBreakdown(
                action=action,
                approved=counts.get("approved", 0),
                denied=counts.get("denied", 0),
                overridden=counts.get("overridden", 0),
                total=sum(counts.values()),
            )
        )

    from conformance import count_distinct_approving_keys
    quorum_rows: list[QuorumBreakdown] = []
    for event in envelope.events:
        if event.kind != "gated_action":
            continue
        approvers = count_distinct_approving_keys(
            envelope.smt_spec_sha256, event
        )
        verbs = sorted({
            att.decision
            for att in [event.authorization, *(event.co_authorizations or [])]
            if att is not None
        })
        label = (
            event.action if event.action is not None else "<unspecified>"
        )
        declared = None
        if quorum_by_action is not None and event.action is not None:
            declared = quorum_by_action.get(event.action)
        quorum_rows.append(
            QuorumBreakdown(
                seq=event.seq,
                action=label,
                valid_distinct_approvers=len(approvers),
                approver_key_fps=tuple(
                    sorted(key[:8] for key in approvers)
                ),
                decision_verbs_seen=tuple(verbs),
                k_declared=declared,
            )
        )
    quorum_rows.sort(key=lambda q: q.seq)

    return LedgerReport(
        world_name=envelope.world_name,
        decisions_total=total,
        approved=verb_counts.get("approved", 0),
        denied=verb_counts.get("denied", 0),
        overridden=verb_counts.get("overridden", 0),
        distinct_principals=distinct,
        principal_diversity=diversity,
        time_span_seconds=span_seconds,
        earliest_utc=earliest,
        latest_utc=latest,
        per_action=tuple(breakdowns),
        quorum=tuple(quorum_rows),
    )


def build_ledger_from_path(
    path: str,
    quorum_by_action: Optional[dict[str, int]] = None,  # __s154_u3_ledger_source_v1__
) -> LedgerReport:
    return build_ledger(load_trace(path), quorum_by_action)


_BOUND_FOOTER = (
    "NOTE: presentation only. This surfaces the recorded decision distribution; "
    "it does NOT verify signatures, prove any decision correct, prove the "
    "principal authorized, prove the oversight meaningful, or prove a refusal "
    "was enforced at runtime. Run `nous verify` for the cryptographic proof "
    "that each decision is bound to its exact (seq, action, proof envelope)."
)


_QUORUM_FOOTER = (  # __s154_u2_quorum_section_v1__
    "valid_distinct_approvers counts ONLY attestations whose Ed25519 "
    "signature verifies against (seq, action, proof envelope), "
    "approved_seq==seq, and decision==approved -- the same rule nous "
    "verify enforces. distinct-KEY count is the cryptographic floor; "
    "distinct-PERSON is unprovable. K_declared (when shown) is "
    "re-derived from --source and is meaningful only if its "
    "smt_spec_sha256 matches the trace. This is a presentation; "
    "\"K met\" is a verdict -- run nous verify."
)


def render_text(report: LedgerReport) -> str:
    lines: list[str] = []
    lines.append(f"Decision ledger -- world: {report.world_name}")
    lines.append(f"  decisions:    {report.decisions_total}")
    lines.append(f"    approved:   {report.approved}")
    lines.append(f"    denied:     {report.denied}")
    lines.append(f"    overridden: {report.overridden}")
    lines.append(
        f"  principals:   {report.distinct_principals} distinct "
        f"(diversity {report.principal_diversity:.3f})"
    )
    if report.time_span_seconds is not None:
        lines.append(
            f"  time span:    {report.time_span_seconds:.3f}s "
            f"({report.earliest_utc} .. {report.latest_utc})"
        )
    else:
        lines.append("  time span:    n/a")
    if report.per_action:
        lines.append("  per action:")
        for item in report.per_action:
            lines.append(
                f"    {item.action}: approved={item.approved} "
                f"denied={item.denied} overridden={item.overridden} "
                f"total={item.total}"
            )
    if report.quorum:
        lines.append("  quorum (gated actions):")
        for q in report.quorum:
            k_label = (
                f"K={q.k_declared}" if q.k_declared is not None else "K=?"
            )
            fps = ", ".join(q.approver_key_fps)
            verbs = (
                ",".join(q.decision_verbs_seen)
                if q.decision_verbs_seen else "-"
            )
            lines.append(
                f"    seq={q.seq} {q.action}: "
                f"valid_distinct_approvers={q.valid_distinct_approvers} "
                f"{k_label} [{fps}] verbs={verbs}"
            )
    lines.append("")
    lines.append(_BOUND_FOOTER)
    if report.quorum:
        lines.append("")
        lines.append(_QUORUM_FOOTER)
    return "\n".join(lines)
