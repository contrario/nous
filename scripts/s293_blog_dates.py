#!/usr/bin/env python3
"""S293 blog date corrections. Four edits, additive, idempotent.

APPLY  : all four markers absent, every anchor count == 1
SKIP   : marker present -> that edit is skipped, others still considered
REFUSE : any anchor count != 1 -> zero writes, exit 2

All-or-nothing write: the file is written once, atomically, or not at all.
"""
import os
import sys
import stat
import hashlib
import tempfile

TARGET = "website/blog/index.html"

M1 = "__s293_pce_omnibus_oj_update_v1__"
M2 = "__s293_a50_grace_clarification_v1__"
M3 = "__s293_general_application_date_update_v1__"
M4 = "__s293_card_excerpt_date_note_v1__"

A1 = (
    "        <p>The full evidence schema, the verdict objects, the offline "
    "verification path, and the regulatory mapping are documented in "
    "<code>docs/PCE.md</code>. <code>nous-lang 5.69.0</code> is on PyPI, "
    "built and published from CI under OIDC Trusted Publishing. "
    "<code>pip install nous-lang</code>.</p>\n"
)
A2 = "      <h3>Update -- 17 May 2026</h3>\n"
A2_CLOSE = "    </aside>\n"
A3 = (
    '    <p style="color:var(--dim);font-size:13px;margin-top:32px">This post '
    "is informational, not legal advice. Conformity assessment under the AI "
    "Act involves obligations beyond what any single tool can satisfy. "
    "Consult qualified counsel for your specific situation.</p>\n"
)
A4 = '<div class="post-excerpt">The EU AI Act becomes enforceable'

I1 = (
    "        <!-- " + M1 + " -->\n"
    '        <aside class="update-note">\n'
    "          <h3>Update -- 2 August 2026</h3>\n"
    "          <p>The Digital Omnibus on AI is no longer pending. It was "
    "published in the Official Journal on 24 July 2026 as Regulation (EU) "
    "2026/1744 (OJ L, 2026/1744, 24.7.2026; CELEX 32026R1744) and entered "
    "into force on 27 July 2026, the third day following publication. The "
    "high-risk system obligation dates it sets are 2 December 2027 for "
    "stand-alone Annex III systems and 2 August 2028 for AI embedded in "
    "Annex I regulated products. The paragraph above was written while the "
    "consolidated text was still pending; the argument it makes is "
    "unchanged.</p>\n"
    "        </aside>\n"
)

I2 = (
    "    <!-- " + M2 + " -->\n"
    '    <aside class="update-note">\n'
    "      <h3>Update -- 2 August 2026</h3>\n"
    "      <p>The note above was written on 17 May 2026, when the Digital "
    "Omnibus text was provisional. It is no longer provisional: it was "
    "published on 24 July 2026 as Regulation (EU) 2026/1744 and entered "
    "into force on 27 July 2026. One thing in that note is stated loosely "
    "and is corrected here. Article 50 applies from 2 August 2026. The 2 "
    "December 2026 date is not the activation of the Article 50(2) "
    "machine-readable marking obligation; it is a grace period under the "
    "new Article 111(4) for providers whose systems were placed on the "
    "market before 2 August 2026.</p>\n"
    "    </aside>\n"
)

I3 = (
    "    <!-- " + M3 + " -->\n"
    '    <aside class="update-note">\n'
    "      <h3>Update -- 2 August 2026</h3>\n"
    "      <p>This post opened with a relative count of days to the general "
    "application date. That count no longer reads correctly, so the dates "
    "are stated absolutely here. 2 August 2026 is the AI Act's general "
    "application date. The high-risk system obligations described above "
    "apply from 2 December 2027 for stand-alone Annex III systems and from "
    "2 August 2028 for AI embedded in Annex I regulated products, under "
    "Regulation (EU) 2026/1744, published on 24 July 2026 and in force "
    "from 27 July 2026.</p>\n"
    "    </aside>\n"
)

I4 = (
    " <em>Updated 2 August 2026: post-Omnibus the high-risk system "
    "obligation dates are 2 December 2027 for stand-alone Annex III "
    "systems and 2 August 2028 for AI embedded in Annex I regulated "
    "products, under Regulation (EU) 2026/1744.</em><!-- " + M4 + " -->"
)


def fail(msg):
    sys.stderr.write("REFUSE: %s\n" % msg)
    sys.exit(2)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else TARGET
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    text = "".join(lines)

    before_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()

    for tag, payload in (("I1", I1), ("I2", I2), ("I3", I3), ("I4", I4)):
        try:
            payload.encode("ascii")
        except UnicodeEncodeError:
            fail("%s payload is not ASCII" % tag)

    plan = []

    # --- F1 ------------------------------------------------------------
    if M1 in text:
        plan.append(("F1", "SKIP", None, None))
    else:
        n = text.count(A1)
        if n != 1:
            fail("F1 anchor count %d, expected 1" % n)
        idx = lines.index(A1)
        plan.append(("F1", "APPLY", idx + 1, I1))

    # --- F2 ------------------------------------------------------------
    if M2 in text:
        plan.append(("F2", "SKIP", None, None))
    else:
        n = text.count(A2)
        if n != 1:
            fail("F2 anchor count %d, expected 1" % n)
        h3 = lines.index(A2)
        close = None
        for j in range(h3, min(h3 + 12, len(lines))):
            if lines[j] == A2_CLOSE:
                close = j
                break
        if close is None:
            fail("F2 closing </aside> not found within 12 lines of anchor")
        if text.count(A2_CLOSE) != 1:
            fail("F2 close anchor count %d, expected 1" % text.count(A2_CLOSE))
        plan.append(("F2", "APPLY", close + 1, I2))

    # --- F4 (the post at the end; inserted after its disclaimer) --------
    if M3 in text:
        plan.append(("F4", "SKIP", None, None))
    else:
        n = text.count(A3)
        if n != 1:
            fail("F4 anchor count %d, expected 1" % n)
        idx = lines.index(A3)
        plan.append(("F4", "APPLY", idx + 1, I3))

    # --- F3 (in-line, inside the card excerpt) --------------------------
    f3_line = None
    if M4 in text:
        plan.append(("F3", "SKIP", None, None))
    else:
        n = text.count(A4)
        if n != 1:
            fail("F3 anchor count %d, expected 1" % n)
        for j, ln in enumerate(lines):
            if A4 in ln:
                f3_line = j
                break
        if not lines[f3_line].rstrip("\n").endswith("</div>"):
            fail("F3 line does not end with </div>")
        plan.append(("F3", "APPLY", f3_line, None))

    applies = [p for p in plan if p[1] == "APPLY"]
    if not applies:
        for tag, act, _, _ in plan:
            print("%s %s" % (tag, act))
        print("NO_CHANGE sha256 %s" % before_sha)
        return 0

    out = list(lines)

    if f3_line is not None:
        ln = out[f3_line]
        body = ln.rstrip("\n")
        assert body.endswith("</div>")
        out[f3_line] = body[: -len("</div>")] + I4 + "</div>\n"

    for tag, act, pos, payload in sorted(
        [p for p in applies if p[3] is not None], key=lambda p: -p[2]
    ):
        out.insert(pos, payload)

    new_text = "".join(out)
    after_sha = hashlib.sha256(new_text.encode("utf-8")).hexdigest()
    if after_sha == before_sha:
        fail("no byte change produced despite APPLY plan")

    # additivity guard: removing each inserted payload once must reconstruct
    # the original bytes exactly. Nothing may be deleted or rewritten.
    check = new_text
    used = [p[3] for p in applies if p[3] is not None]
    if f3_line is not None:
        used = used + [I4]
    for payload in used:
        if check.count(payload) < 1:
            fail("additivity guard: payload absent from result")
        check = check.replace(payload, "", 1)
    if check != text:
        fail("additivity guard: result is not the original plus insertions")

    d = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".s293_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(new_text)
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise

    for tag, act, _, _ in plan:
        print("%s %s" % (tag, act))
    print("BEFORE %s" % before_sha)
    print("AFTER  %s" % after_sha)
    print("LINES  %d -> %d" % (text.count("\n"), new_text.count("\n")))
    print("BYTES  %d -> %d" % (
        len(text.encode("utf-8")), len(new_text.encode("utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
