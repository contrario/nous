#!/usr/bin/env python3
"""
Patch: blog post bundle for NOUS v4.15.0 -> v4.18.0
Target:    /var/www/nous-lang.org/blog/index.html
Idempotent marker: __session68_blog_v418_bundle__
Backup:    <target>.bak.session68.v418_bundle.<ts>
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

TARGET: Path = Path("/var/www/nous-lang.org/blog/index.html")
MARKER: str = "__session68_blog_v418_bundle__"
BACKUP_SUFFIX: str = f".bak.session68.v418_bundle.{int(time.time())}"

POST_CARD_ANCHOR: str = (
    "<a class=\"post-card\" href=\"#\" "
    "onclick=\"showPost('v4133-smt-margin');return false\">"
)
POST_FULL_ANCHOR: str = "<div class=\"post-full\" id=\"post-v4133-smt-margin\">"

NEW_POST_CARD: str = (
    "<!-- " + MARKER + " -->\n"
    "    <a class=\"post-card\" href=\"#\" onclick=\"showPost('v418-bundle');return false\">\n"
    "      <div class=\"post-meta\">\n"
    "        <span class=\"post-date\">02 MAY 2026</span>\n"
    "        <span class=\"post-tag\" style=\"background:rgba(201,165,84,0.1);border:1px solid rgba(201,165,84,0.2);color:var(--gold)\">Release Bundle</span>\n"
    "      </div>\n"
    "      <div class=\"post-title\">NOUS v4.15.0 &rarr; v4.18.0 &mdash; A Fleet-Operable Compiler with Audit-Stable Diffs</div>\n"
    "      <div class=\"post-excerpt\">Five releases turn NOUS from a single-machine compiler into a fleet-operable system with audit-stable comparisons. v4.15.0 adds <code>GET /v1/replay/list</code> and <code>POST /v1/replay/diff</code> for cross-machine log inspection and lockstep comparison. v4.16.0 adds <code>PUT /v1/templates/{name}</code> with hard auth, lint gating, atomic writes, and pruned backups. v4.16.1 fixes a <code>/v1/diff</code> crash on <code>FeedbackNode</code> / <code>FanIn</code> / <code>FanOut</code> routes. v4.17.0 promotes <code>cryptography</code> to a base dependency so clean-venv installs no longer need the <code>[smt]</code> extra. v4.18.0 adds <code>DiffSide</code> provenance: every comparison carries server-rendered, contract-defined source labels for Annex IV evidence. Pytest floor 278 &rarr; 337, 0 regression drift across 57 templates.</div>\n"
    "      <span class=\"post-read\">Read post &rarr;</span>\n"
    "    </a>\n\n    "
)

NEW_POST_FULL: str = (
    "<!-- " + MARKER + " -->\n"
    "  <div class=\"post-full\" id=\"post-v418-bundle\">\n"
    "    <button class=\"post-back\" onclick=\"showList()\">&larr; All posts</button>\n"
    "    <h1 class=\"post-full-title\">NOUS v4.15.0 &rarr; v4.18.0 &mdash; A Fleet-Operable Compiler with Audit-Stable Diffs</h1>\n"
    "    <div class=\"post-full-meta\">2 May 2026 &middot; Session 68 &middot; 6 min read</div>\n"
    "\n"
    "    <h2>The arc</h2>\n"
    "    <p>Between v4.14.0 and v4.18.0, NOUS stopped being a compiler that runs on one machine and started being a compiler whose state is legible across a fleet. Five releases, one direction: cross-machine replay logs become inspectable, world templates become writable over HTTP, the diff path stops crashing on non-route nerves, the install no longer needs an extra to work, and every comparison labels its own sources in a way an auditor can trust.</p>\n"
    "    <p>The throughline is provenance. A regulator under EU AI Act Annex IV does not ask &ldquo;did your tests pass&rdquo; &mdash; they ask &ldquo;show me what changed, where, and how you know.&rdquo; This bundle is the surface area for that question.</p>\n"
    "\n"
    "    <h2>v4.15.0 &mdash; Reading the replay fleet</h2>\n"
    "    <p>Two read-only HTTP endpoints, both sandboxed to <code>NOUS_REPLAY_DIR</code> (default <code>/var/lib/nous/replays</code>):</p>\n"
    "    <p><code>GET /v1/replay/list</code> enumerates <code>*.jsonl</code> logs with cheap last-line metadata: size, mtime, last <code>seq_id</code>, last hash, last event kind. Tail-reads the final 8&nbsp;KB of each file. No chain validation &mdash; that remains <code>/v1/replay/verify</code>&rsquo;s job. The list endpoint is for fleet dashboards: which machines logged, when, how far.</p>\n"
    "    <p><code>POST /v1/replay/diff</code> compares two logs lockstep by <code>(seq_id, hash)</code>. Verdicts are a closed set: <code>identical</code>, <code>divergent</code>, <code>truncated_a</code>, <code>truncated_b</code>, <code>error</code>. The first divergence event is reported side-by-side &mdash; not a textual diff, an event-level one, because hashes diverge at events, not at lines.</p>\n"
    "    <p>Path safety is non-negotiable: filenames are rejected on path separators, leading dot, parent-dir traversal, and outward-pointing symlinks. The endpoint cannot be used to read anything outside the replay directory regardless of how clever the client is. 11 tests, pytest floor 278 &rarr; 289.</p>\n"
    "\n"
    "    <h2>v4.16.0 &mdash; Writing templates over HTTP</h2>\n"
    "    <p><code>PUT /v1/templates/{name}</code> is the RESTful counterpart to the existing GET. Saving a <code>.nous</code> world template runs the full safety pipeline before a single byte hits disk:</p>\n"
    "    <ol>\n"
    "      <li><strong>Hard auth.</strong> An empty <code>NOUS_API_KEYS</code> environment returns 403 (server unconfigured for writes). Missing or invalid keys return 401. The GET path keeps soft auth for backward compatibility; writes do not.</li>\n"
    "      <li><strong>Name sanitisation.</strong> Pattern <code>^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$</code>, plus a resolved-path check that the file lands inside <code>TEMPLATES_DIR</code>.</li>\n"
    "      <li><strong>Lint gate.</strong> The <code>governance_lint</code> linter runs against the submitted source. Errors block the save unless the client passes <code>force=true</code>. A linter crash is treated as having errors, not as a green light.</li>\n"
    "      <li><strong>Backup.</strong> An existing file is copied to <code>&lt;name&gt;.nous.bak.&lt;ts_us&gt;</code> and the directory is pruned to the 5 most recent backups.</li>\n"
    "      <li><strong>Atomic write.</strong> Tempfile + fsync + <code>os.replace</code>. No reader ever sees a partial file.</li>\n"
    "      <li><strong>SHA-256 receipt.</strong> The response includes the hash of the bytes written, so the client can verify what landed without re-fetching.</li>\n"
    "    </ol>\n"
    "    <p>The original Session 64 plan listed <code>/v1/policies/{list,validate,save}</code>. Aliasing was rejected because list and validate already exist as <code>/v1/governance/{policies,lint}</code>, and a <code>.nous</code> file is a full world (souls, mind, governance) &mdash; there are no separate policy files in NOUS. The save endpoint is named after the artifact it produces. 13 tests, pytest floor 289 &rarr; 302.</p>\n"
    "\n"
    "    <h2>v4.16.1 &mdash; Diffs that do not crash</h2>\n"
    "    <p>Three call sites in the diff path were doing blind <code>route.source</code> / <code>route.target</code> attribute access. Correct for <code>RouteNode</code>; dead wrong for every other nerve statement: <code>MatchRouteNode</code>, <code>FanInNode</code>, <code>FanOutNode</code>, <code>FeedbackNode</code>. The trading_floor template (which uses <code>FeedbackNode</code>) hit <code>AttributeError</code> &rarr; HTTP 422 on every diff request.</p>\n"
    "    <p>The fix: <code>isinstance</code>-dispatch over the five nerve variants in <code>behavioral_diff._get_routes</code>, <code>behavioral_diff._get_entrypoints</code>, and the nested <code>_get_routes</code> inside <code>nous_api_server._transform_diff_for_ide</code>. Each variant emits the correct <code>(src, dst)</code> edges (or, for entrypoints, the correct &ldquo;is-a-target&rdquo; set).</p>\n"
    "    <p>The lesson is older than this bug: when a base type has variants, attribute access without dispatch is a latent crash. 8 regression tests pinned to the four non-route variants. Pytest floor 302 &rarr; 310.</p>\n"
    "\n"
    "    <h2>v4.17.0 &mdash; Install you can trust</h2>\n"
    "    <p>Since Session 64, <code>cli.py</code> imports <code>cli_dossier</code> at module load, which transitively imports <code>cryptography</code> for Ed25519 signing. The dependency was already a hard runtime requirement &mdash; it was just hidden behind the <code>[smt]</code> extra. A clean <code>pip install nous-lang</code> in a fresh venv would import-fail before printing the help text.</p>\n"
    "    <p>The fix is small and the message is honest: <code>cryptography</code> moves to base. The <code>[smt]</code> extra now contains only what it claims to: Z3. <code>pip install nous-lang</code> is sufficient for the entire CLI surface, including <code>nous dossier</code> and signed manifests. Optional remains optional; required becomes visibly required.</p>\n"
    "\n"
    "    <h2>v4.18.0 &mdash; Diffs that name themselves</h2>\n"
    "    <p>Before v4.18.0, the IDE&rsquo;s &ldquo;Safe to Deploy&rdquo; card hardcoded the strings <code>original.nous</code> and <code>modified.nous</code>. Fine when both sides were in-editor pastes. A liability the moment a diff could be saved-template-vs-editor, paste-vs-paste, or replay-vs-replay &mdash; the labels lied about where the bytes came from, and a <code>nous dossier</code> bundle would inherit the lie.</p>\n"
    "    <p>v4.18.0 adds a <code>DiffSide</code> Pydantic model with a closed <code>Literal</code> enum of source kinds: <code>editor</code>, <code>paste</code>, <code>template</code>, <code>replay</code>, <code>file</code>, <code>unknown</code>. The server runs <code>render_diff_side()</code> &mdash; one canonical renderer &mdash; and returns <code>original_label</code> and <code>modified_label</code> in the <code>/v1/diff</code> response. The IDE renders what the server says. Audit logs record what the server said. <code>nous dossier</code> evidence captures what the server said. Three different consumers, one label string, no drift.</p>\n"
    "    <p>Backward compatibility is intentional: clients on 4.16.x that do not send provenance still get a valid response &mdash; both labels render as <code>(unknown source)</code>. New kinds are explicit additions to the <code>Literal</code> enum; silent string drift is a parse error, not a deployment surprise. 17 tests, pytest floor 320 &rarr; 337.</p>\n"
    "\n"
    "    <h2>The bundle in numbers</h2>\n"
    "    <ul>\n"
    "      <li><strong>5 releases</strong> shipped: v4.15.0, v4.16.0, v4.16.1, v4.17.0, v4.18.0.</li>\n"
    "      <li><strong>Pytest floor 278 &rarr; 337</strong> (+59 tests, +21%).</li>\n"
    "      <li><strong>57/57 regression templates</strong> baseline-stable across the bundle. Zero drift.</li>\n"
    "      <li><strong>3 new HTTP endpoints</strong>: <code>GET /v1/replay/list</code>, <code>POST /v1/replay/diff</code>, <code>PUT /v1/templates/{name}</code>.</li>\n"
    "      <li><strong>1 install-time bug</strong> retired (cryptography extra).</li>\n"
    "      <li><strong>1 audit-trail liability</strong> closed (hardcoded diff labels).</li>\n"
    "    </ul>\n"
    "\n"
    "    <h2>Try it</h2>\n"
    "    <p><code>pip install --upgrade nous-lang</code> &mdash; no extras required for the full CLI surface, including <code>nous dossier</code>.</p>\n"
    "    <p>Ship logs:\n"
    "      <a href=\"https://github.com/contrario/nous/releases/tag/v4.15.0\">v4.15.0</a> &middot;\n"
    "      <a href=\"https://github.com/contrario/nous/releases/tag/v4.16.0\">v4.16.0</a> &middot;\n"
    "      <a href=\"https://github.com/contrario/nous/releases/tag/v4.16.1\">v4.16.1</a> &middot;\n"
    "      <a href=\"https://github.com/contrario/nous/releases/tag/v4.17.0\">v4.17.0</a> &middot;\n"
    "      <a href=\"https://github.com/contrario/nous/releases/tag/v4.18.0\">v4.18.0</a> &middot;\n"
    "      <a href=\"https://pypi.org/project/nous-lang/4.18.0/\">pypi.org/project/nous-lang/4.18.0</a>.\n"
    "    </p>\n"
    "  </div>\n"
    "\n  "
)


def atomic_write(path: Path, data: str, mode: int = 0o644) -> None:
    parent: Path = path.parent
    fd, tmp_path_str = tempfile.mkstemp(prefix=path.name + ".", dir=str(parent))
    tmp_path: Path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    if not TARGET.is_file():
        print(f"FAIL: target not found: {TARGET}", file=sys.stderr)
        return 2

    src: str = TARGET.read_text(encoding="utf-8")

    if MARKER in src:
        print(f"SKIP: marker {MARKER} already present; no changes")
        return 0

    if POST_CARD_ANCHOR not in src:
        print("FAIL: post-card anchor not found", file=sys.stderr)
        return 3
    if src.count(POST_CARD_ANCHOR) != 1:
        print(
            f"FAIL: post-card anchor matched {src.count(POST_CARD_ANCHOR)} times; expected 1",
            file=sys.stderr,
        )
        return 4
    if POST_FULL_ANCHOR not in src:
        print("FAIL: post-full anchor not found", file=sys.stderr)
        return 5
    if src.count(POST_FULL_ANCHOR) != 1:
        print(
            f"FAIL: post-full anchor matched {src.count(POST_FULL_ANCHOR)} times; expected 1",
            file=sys.stderr,
        )
        return 6

    backup: Path = TARGET.with_suffix(TARGET.suffix + BACKUP_SUFFIX)
    shutil.copy2(TARGET, backup)
    print(f"BACKUP: {backup}")

    patched: str = src.replace(POST_CARD_ANCHOR, NEW_POST_CARD + POST_CARD_ANCHOR, 1)
    patched = patched.replace(POST_FULL_ANCHOR, NEW_POST_FULL + POST_FULL_ANCHOR, 1)

    if patched.count(MARKER) != 2:
        print(
            f"FAIL: post-patch marker count = {patched.count(MARKER)}; expected 2",
            file=sys.stderr,
        )
        return 7
    if 'id="post-v418-bundle"' not in patched:
        print("FAIL: new full-post id missing after patch", file=sys.stderr)
        return 8
    if "showPost('v418-bundle')" not in patched:
        print("FAIL: new post-card onclick missing after patch", file=sys.stderr)
        return 9

    atomic_write(TARGET, patched, mode=0o644)
    print(f"OK: patched {TARGET}")
    print(f"OK: bytes {len(src)} -> {len(patched)} (+{len(patched) - len(src)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
