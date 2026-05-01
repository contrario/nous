"""IDE wiring for v4.18.0 diff source labels.

Three changes to /var/www/nous-lang.org/ide.html:
1. Add _kindToSide() helper translating internal kind strings to DiffSide objects.
2. Pass original_side / modified_side in the /v1/diff fetch body.
3. Prefer server-rendered original_label / modified_label in renderDiff;
   fall back to legacy d.source / d.target for safety.

Idempotent. Atomic write. chmod 0o644 after.
"""
from __future__ import annotations
import os
import tempfile
from pathlib import Path

P = Path("/var/www/nous-lang.org/ide.html")
MARKER_HELPER = "// __DIFF_SIDE_KIND_TO_SIDE_v1__"
MARKER_FETCH = "// __DIFF_SIDE_FETCH_BODY_v1__"
MARKER_RENDER = "// __DIFF_SIDE_RENDER_LABELS_v1__"

src = P.read_text(encoding="utf-8")

if (
    MARKER_HELPER in src
    and MARKER_FETCH in src
    and MARKER_RENDER in src
):
    print("SKIP: all three markers present")
    raise SystemExit(0)

# ── 1. Insert _kindToSide() helper right after _resolveDiffSource ───────
HELPER_ANCHOR = (
    "  return { source: data.source || '', kind: 'template:' + val };\n"
    "}\n"
)
HELPER_INSERT = HELPER_ANCHOR + (
    "\n"
    + MARKER_HELPER + "\n"
    "function _kindToSide(kind) {\n"
    "  // Translate internal kind strings into v4.18.0 DiffSide objects.\n"
    "  // 'editor' -> {kind:'editor'}\n"
    "  // 'paste' -> {kind:'paste'}\n"
    "  // 'template:<name>' -> {kind:'template', identifier:<name>}\n"
    "  if (!kind) return { kind: 'unknown' };\n"
    "  if (kind === 'editor') return { kind: 'editor' };\n"
    "  if (kind === 'paste') return { kind: 'paste' };\n"
    "  if (kind.indexOf('template:') === 0) {\n"
    "    return { kind: 'template', identifier: kind.slice('template:'.length) };\n"
    "  }\n"
    "  return { kind: 'unknown' };\n"
    "}\n"
)

if MARKER_HELPER not in src:
    if HELPER_ANCHOR not in src:
        print("FAIL: helper anchor not found")
        raise SystemExit(1)
    src = src.replace(HELPER_ANCHOR, HELPER_INSERT, 1)

# ── 2. Add original_side / modified_side to fetch body ──────────────────
FETCH_ANCHOR = (
    "    var resp = await fetch('/api/v1/diff', {\n"
    "      method: 'POST',\n"
    "      headers: { 'Content-Type': 'application/json' },\n"
    "      body: JSON.stringify({ original: origRes.source, modified: modRes.source })\n"
    "    });\n"
)
FETCH_INSERT = (
    "    " + MARKER_FETCH + "\n"
    "    var resp = await fetch('/api/v1/diff', {\n"
    "      method: 'POST',\n"
    "      headers: { 'Content-Type': 'application/json' },\n"
    "      body: JSON.stringify({\n"
    "        original: origRes.source,\n"
    "        modified: modRes.source,\n"
    "        original_side: _kindToSide(origRes.kind),\n"
    "        modified_side: _kindToSide(modRes.kind)\n"
    "      })\n"
    "    });\n"
)

if MARKER_FETCH not in src:
    if FETCH_ANCHOR not in src:
        print("FAIL: fetch anchor not found")
        raise SystemExit(1)
    src = src.replace(FETCH_ANCHOR, FETCH_INSERT, 1)

# ── 3. Prefer original_label / modified_label in renderDiff ─────────────
RENDER_ANCHOR = (
    "  html += '<div class=\"v-sub\">' + d.source + ' \\u2192 ' + d.target + ' \\u00B7 ' + d.findings.length + ' findings</div>';\n"
)
RENDER_INSERT = (
    "  " + MARKER_RENDER + "\n"
    "  var srcLabel = d.original_label || d.source || 'original';\n"
    "  var tgtLabel = d.modified_label || d.target || 'modified';\n"
    "  html += '<div class=\"v-sub\">' + srcLabel + ' \\u2192 ' + tgtLabel + ' \\u00B7 ' + d.findings.length + ' findings</div>';\n"
)

if MARKER_RENDER not in src:
    if RENDER_ANCHOR not in src:
        print("FAIL: render anchor not found")
        raise SystemExit(1)
    src = src.replace(RENDER_ANCHOR, RENDER_INSERT, 1)

# ── Atomic write + chmod 0o644 (nginx readability) ──────────────────────
tmp_fd, tmp_path = tempfile.mkstemp(
    dir=str(P.parent), prefix=".ide.html.", suffix=".tmp"
)
try:
    with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
        f.write(src)
    os.chmod(tmp_path, 0o644)
    os.replace(tmp_path, str(P))
except Exception:
    try:
        os.unlink(tmp_path)
    except FileNotFoundError:
        pass
    raise

print(f"OK: ide.html patched (3 sites), {P.stat().st_size} bytes, mode 644")
