from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import urllib.request
import urllib.error


COMMENT_MARKER = "<!-- nous-behavioral-diff -->"

SEVERITY_ICONS: dict[str, str] = {
    "CRITICAL": "🔴",
    "WARNING": "🟡",
    "INFO": "🟢",
}

SEVERITY_ORDER: dict[str, int] = {
    "CRITICAL": 0,
    "WARNING": 1,
    "INFO": 2,
}


def github_api(
    method: str,
    endpoint: str,
    token: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any] | list[Any]:
    url = f"https://api.github.com{endpoint}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"GitHub API error: {e.status} {e.read().decode()}", file=sys.stderr)
        raise


def find_existing_comment(repo: str, pr: int, token: str) -> int | None:
    comments: list[dict[str, Any]] = github_api(
        "GET", f"/repos/{repo}/issues/{pr}/comments", token
    )
    for c in comments:
        if COMMENT_MARKER in c.get("body", ""):
            return c["id"]
    return None


def upsert_comment(repo: str, pr: int, token: str, body: str) -> None:
    existing_id = find_existing_comment(repo, pr, token)
    if existing_id:
        github_api(
            "PATCH",
            f"/repos/{repo}/issues/comments/{existing_id}",
            token,
            {"body": body},
        )
    else:
        github_api(
            "POST",
            f"/repos/{repo}/issues/{pr}/comments",
            token,
            {"body": body},
        )


def format_cost(val: float) -> str:
    if val >= 1.0:
        return f"${val:,.2f}"
    if val >= 0.01:
        return f"${val:.4f}"
    return f"${val:.6f}"


def cost_delta_badge(old: float, new: float) -> str:
    if old == 0:
        return "🆕"
    pct = ((new - old) / old) * 100
    if pct < -5:
        return f"🟢 **{pct:+.1f}%**"
    if pct > 5:
        return f"🔴 **{pct:+.1f}%**"
    return f"⚪ {pct:+.1f}%"


def render_new_file(filename: str) -> str:
    return (
        f"### 🆕 `{filename}`\n\n"
        f"New NOUS program added. No baseline to diff against.\n"
    )


def render_diff(filename: str, diff: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"### 📄 `{filename}`\n")

    cost = diff.get("cost")
    if cost:
        old_daily = cost.get("old_daily", 0)
        new_daily = cost.get("new_daily", 0)
        old_monthly = cost.get("old_monthly", 0)
        new_monthly = cost.get("new_monthly", 0)
        badge = cost_delta_badge(old_monthly, new_monthly)

        lines.append("<table>")
        lines.append("<tr><th>Metric</th><th>Before</th><th>After</th><th>Change</th></tr>")
        lines.append(
            f"<tr><td><b>Monthly Cost</b></td>"
            f"<td><code>{format_cost(old_monthly)}/mo</code></td>"
            f"<td><code>{format_cost(new_monthly)}/mo</code></td>"
            f"<td>{badge}</td></tr>"
        )
        lines.append(
            f"<tr><td>Daily Cost</td>"
            f"<td><code>{format_cost(old_daily)}/day</code></td>"
            f"<td><code>{format_cost(new_daily)}/day</code></td>"
            f"<td>{cost_delta_badge(old_daily, new_daily)}</td></tr>"
        )

        soul_costs = cost.get("per_soul", [])
        for sc in soul_costs:
            name = sc.get("name", "?")
            s_old = sc.get("old_cost", 0)
            s_new = sc.get("new_cost", 0)
            lines.append(
                f"<tr><td>&nbsp;&nbsp;↳ {name}</td>"
                f"<td><code>{format_cost(s_old)}</code></td>"
                f"<td><code>{format_cost(s_new)}</code></td>"
                f"<td>{cost_delta_badge(s_old, s_new)}</td></tr>"
            )

        lines.append("</table>\n")

    topology = diff.get("topology")
    if topology:
        added = topology.get("souls_added", [])
        removed = topology.get("souls_removed", [])
        modified = topology.get("souls_modified", [])
        if added or removed or modified:
            lines.append("#### Topology\n")
            for s in added:
                lines.append(f"- 🟢 Soul added: **{s}**")
            for s in removed:
                lines.append(f"- 🔴 Soul removed: **{s}**")
            for s in modified:
                lines.append(f"- 🟡 Soul modified: **{s}**")
            lines.append("")

    protocol = diff.get("protocol")
    if protocol:
        msgs_added = protocol.get("messages_added", [])
        msgs_removed = protocol.get("messages_removed", [])
        if msgs_added or msgs_removed:
            lines.append("#### Protocol\n")
            for m in msgs_added:
                lines.append(f"- 🟢 Message type added: `{m}`")
            for m in msgs_removed:
                lines.append(f"- 🔴 Message type removed: `{m}`")
            lines.append("")

    findings = diff.get("findings", [])
    if findings:
        sorted_findings = sorted(
            findings,
            key=lambda f: SEVERITY_ORDER.get(f.get("severity", "INFO"), 99),
        )
        lines.append("#### Findings\n")
        lines.append("| | Severity | Code | Detail |")
        lines.append("|---|----------|------|--------|")
        for f in sorted_findings:
            sev = f.get("severity", "INFO")
            icon = SEVERITY_ICONS.get(sev, "⚪")
            code = f.get("code", "—")
            detail = f.get("detail", "")
            lines.append(f"| {icon} | {sev} | `{code}` | {detail} |")
        lines.append("")

    return "\n".join(lines)


def build_comment(
    changed_files: list[str],
    diff_dir: Path,
) -> str:
    sections: list[str] = []
    total_critical = 0
    total_warnings = 0
    total_info = 0
    total_old_monthly = 0.0
    total_new_monthly = 0.0
    file_count = 0

    for filename in changed_files:
        slug = filename.replace("/", "_").removesuffix(".nous")
        diff_path = diff_dir / f"{slug}.json"
        if not diff_path.exists():
            continue

        try:
            diff = json.loads(diff_path.read_text())
        except (json.JSONDecodeError, OSError):
            sections.append(f"### ⚠️ `{filename}`\n\nFailed to parse diff output.\n")
            continue

        file_count += 1

        if diff.get("status") == "new_file":
            sections.append(render_new_file(filename))
            continue

        cost = diff.get("cost", {})
        total_old_monthly += cost.get("old_monthly", 0)
        total_new_monthly += cost.get("new_monthly", 0)

        for f in diff.get("findings", []):
            sev = f.get("severity", "INFO")
            if sev == "CRITICAL":
                total_critical += 1
            elif sev == "WARNING":
                total_warnings += 1
            else:
                total_info += 1

        sections.append(render_diff(filename, diff))

    if total_old_monthly > 0:
        pct = ((total_new_monthly - total_old_monthly) / total_old_monthly) * 100
        if pct < 0:
            cost_summary = f"🟢 **{format_cost(total_old_monthly)}/mo → {format_cost(total_new_monthly)}/mo ({pct:+.1f}%)**"
        elif pct > 0:
            cost_summary = f"🔴 **{format_cost(total_old_monthly)}/mo → {format_cost(total_new_monthly)}/mo ({pct:+.1f}%)**"
        else:
            cost_summary = f"⚪ No cost change ({format_cost(total_new_monthly)}/mo)"
    else:
        cost_summary = "No cost data"

    if total_critical > 0:
        status_icon = "🔴"
        status_text = "Breaking Changes Detected"
    elif total_warnings > 0:
        status_icon = "🟡"
        status_text = "Warnings Detected"
    else:
        status_icon = "🟢"
        status_text = "All Clear"

    header = f"""{COMMENT_MARKER}
## {status_icon} NOUS Behavioral Diff

> Semantic impact analysis for **{file_count}** modified `.nous` file{"s" if file_count != 1 else ""}

---

| | Summary |
|---|---------|
| **Cost Impact** | {cost_summary} |
| **Findings** | {total_critical} critical · {total_warnings} warnings · {total_info} info |
| **Status** | {status_icon} {status_text} |

---

"""

    footer = """
---

<sub>🧠 Generated by <b>NOUS Behavioral Diff</b> · <a href="https://nous-lang.org/docs#verification">docs</a></sub>
"""

    return header + "\n".join(sections) + footer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diff-dir", required=True, type=Path)
    parser.add_argument("--changed-files", required=True, type=Path)
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    pr_number = os.environ.get("PR_NUMBER")
    repo = os.environ.get("REPO")

    if not all([token, pr_number, repo]):
        print("Missing GITHUB_TOKEN, PR_NUMBER, or REPO env vars", file=sys.stderr)
        sys.exit(1)

    changed = [
        line.strip()
        for line in args.changed_files.read_text().splitlines()
        if line.strip()
    ]

    if not changed:
        print("No changed .nous files found.")
        return

    body = build_comment(changed, args.diff_dir)

    print("--- Generated Comment ---")
    print(body)
    print("--- End ---")

    upsert_comment(repo, int(pr_number), token, body)
    print(f"Comment posted to PR #{pr_number}")


if __name__ == "__main__":
    main()
