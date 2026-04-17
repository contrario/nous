"""Static analysis for NOUS policy declarations.

__governance_lint_v2__

Lint rules:
  L000 file not found
  L001 duplicate policy name
  L002 empty policy name
  L003 invalid action (must be log_only/intervene/block/abort_cycle/inject_message)
  L004 weight out of range (0.0, 10.0]
  L006 empty signal expression
  L007 unknown event kind (info)
  L008 inject_message policy missing message field
  L009 empty policy file (no policies declared)
  L010 reserved name prefix (starts with __)
  L011 negative window
  L012 signal is literal constant (always/never fires)
  L100 parse error
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

Severity = Literal["error", "warning", "info"]

VALID_ACTIONS: frozenset[str] = frozenset({
    "log_only",
    "intervene",
    "block",
    "abort_cycle",
    "inject_message",
})

KNOWN_KINDS: frozenset[str] = frozenset({
    "llm.request",
    "llm.response",
    "llm.error",
    "sense.invoke",
    "sense.result",
    "sense.error",
    "memory.write",
    "governance.intervention",
})


@dataclass(frozen=True)
class LintIssue:
    rule: str
    severity: Severity
    policy: str
    message: str
    source_file: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "policy": self.policy,
            "message": self.message,
            "source_file": self.source_file,
        }


@dataclass(frozen=True)
class LintReport:
    issues: tuple[LintIssue, ...]
    source_file: str
    policy_count: int

    @property
    def errors(self) -> tuple[LintIssue, ...]:
        return tuple(i for i in self.issues if i.severity == "error")

    @property
    def warnings(self) -> tuple[LintIssue, ...]:
        return tuple(i for i in self.issues if i.severity == "warning")

    @property
    def infos(self) -> tuple[LintIssue, ...]:
        return tuple(i for i in self.issues if i.severity == "info")

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "policy_count": self.policy_count,
            "issue_count": len(self.issues),
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "info_count": len(self.infos),
            "issues": [i.to_dict() for i in self.issues],
        }


class GovernanceLinter:
    """Static analysis for policy declarations in .nous files."""

    def __init__(self) -> None:
        self._issues: list[LintIssue] = []

    def lint_source(self, source: str, source_file: str = "") -> LintReport:
        # __governance_lint_empty_shortcircuit_v1__
        if not source or not source.strip():
            return self._lint_policies([], source_file)
        try:
            from parser import parse_nous
            program = parse_nous(source)
        except Exception as exc:
            issue = LintIssue(
                rule="L100",
                severity="error",
                policy="",
                message=f"Parse error: {exc}",
                source_file=source_file,
            )
            return LintReport(
                issues=(issue,),
                source_file=source_file,
                policy_count=0,
            )
        world = getattr(program, "world", None)
        policies = list(getattr(world, "policies", []) or []) if world else []
        return self._lint_policies(policies, source_file)

    def lint_file(self, path: str | Path) -> LintReport:
        p = Path(path)
        if not p.exists():
            issue = LintIssue(
                rule="L000",
                severity="error",
                policy="",
                message=f"File not found: {p}",
                source_file=str(p),
            )
            return LintReport(
                issues=(issue,),
                source_file=str(p),
                policy_count=0,
            )
        source = p.read_text(encoding="utf-8")
        return self.lint_source(source, source_file=str(p))

    def _lint_policies(self, policies: list[Any], source_file: str) -> LintReport:
        self._issues = []

        if len(policies) == 0:
            self._issues.append(LintIssue(
                rule="L009",
                severity="warning",
                policy="",
                message="No policies found in file",
                source_file=source_file,
            ))

        seen_names: dict[str, int] = {}
        for p in policies:
            name = str(getattr(p, "name", "") or "")
            if name:
                seen_names[name] = seen_names.get(name, 0) + 1
        for name, count in seen_names.items():
            if count > 1:
                self._issues.append(LintIssue(
                    rule="L001",
                    severity="error",
                    policy=name,
                    message=f"Duplicate policy name '{name}' appears {count} times",
                    source_file=source_file,
                ))

        for p in policies:
            self._check_policy(p, source_file)

        return LintReport(
            issues=tuple(self._issues),
            source_file=source_file,
            policy_count=len(policies),
        )

    def _check_policy(self, p: Any, source_file: str) -> None:
        name = str(getattr(p, "name", "") or "")
        kind = getattr(p, "kind", None)
        kind_str = str(kind) if kind is not None else ""
        signal = getattr(p, "signal", None)
        try:
            weight = float(getattr(p, "weight", 0.0))
        except (TypeError, ValueError):
            weight = 0.0
        action = str(getattr(p, "action", "log_only") or "log_only")
        inject_as = getattr(p, "inject_as", None)
        inject_message = getattr(p, "message", None)
        try:
            window = int(getattr(p, "window", 0))
        except (TypeError, ValueError):
            window = 0

        if not name or name == "unknown":
            self._issues.append(LintIssue(
                rule="L002",
                severity="error",
                policy=name or "<unnamed>",
                message="Policy has no name",
                source_file=source_file,
            ))

        if name.startswith("__"):
            self._issues.append(LintIssue(
                rule="L010",
                severity="warning",
                policy=name,
                message=f"Policy name '{name}' uses reserved prefix '__'",
                source_file=source_file,
            ))

        if action and action not in VALID_ACTIONS:
            valid_sorted = sorted(VALID_ACTIONS)
            self._issues.append(LintIssue(
                rule="L003",
                severity="error",
                policy=name,
                message=f"Invalid action '{action}'. Valid: {valid_sorted}",
                source_file=source_file,
            ))

        if not (0.0 < weight <= 10.0):
            self._issues.append(LintIssue(
                rule="L004",
                severity="error",
                policy=name,
                message=f"Weight {weight} out of range (0.0, 10.0]",
                source_file=source_file,
            ))

        if signal is None or (isinstance(signal, str) and signal.strip() == ""):
            self._issues.append(LintIssue(
                rule="L006",
                severity="error",
                policy=name,
                message="Policy has empty signal expression",
                source_file=source_file,
            ))
        elif signal is True:
            self._issues.append(LintIssue(
                rule="L012",
                severity="info",
                policy=name,
                message="Signal is literal True -- policy always fires",
                source_file=source_file,
            ))
        elif signal is False:
            self._issues.append(LintIssue(
                rule="L012",
                severity="warning",
                policy=name,
                message="Signal is literal False -- policy never fires",
                source_file=source_file,
            ))

        if kind_str and kind_str not in KNOWN_KINDS:
            known_sorted = sorted(KNOWN_KINDS)
            self._issues.append(LintIssue(
                rule="L007",
                severity="info",
                policy=name,
                message=f"Unknown event kind '{kind_str}'. Known: {known_sorted}",
                source_file=source_file,
            ))

        if action == "inject_message":
            if inject_message is None or (isinstance(inject_message, str) and inject_message.strip() == ""):
                self._issues.append(LintIssue(
                    rule="L008",
                    severity="error",
                    policy=name,
                    message="Policy uses inject_message but has no message field",
                    source_file=source_file,
                ))

        if window < 0:
            self._issues.append(LintIssue(
                rule="L011",
                severity="error",
                policy=name,
                message=f"Window must be >= 0, got {window}",
                source_file=source_file,
            ))


def render_text(report: LintReport) -> str:
    lines: list[str] = []
    header = f"Lint: {report.source_file or '<source>'} -- {report.policy_count} policies"
    lines.append(header)
    lines.append("=" * len(header))
    if not report.issues:
        lines.append("OK -- no issues")
        return "\n".join(lines)
    markers = {"error": "ERR ", "warning": "WARN", "info": "INFO"}
    for issue in report.issues:
        sev_marker = markers[issue.severity]
        pol = f"[{issue.policy}]" if issue.policy else ""
        lines.append(f"{sev_marker} {issue.rule} {pol} {issue.message}")
    lines.append("")
    lines.append(
        f"Summary: {len(report.errors)} error(s), "
        f"{len(report.warnings)} warning(s), "
        f"{len(report.infos)} info"
    )
    return "\n".join(lines)


def render_json(report: LintReport) -> str:
    return json.dumps(report.to_dict(), indent=2)


def lint_cli(source_path: str, output_format: str = "text", strict: bool = False) -> int:
    """CLI entrypoint. Returns exit code."""
    linter = GovernanceLinter()
    report = linter.lint_file(source_path)
    if output_format == "json":
        print(render_json(report))
    else:
        print(render_text(report))
    if report.has_errors:
        return 1
    if strict and report.has_warnings:
        return 1
    return 0
