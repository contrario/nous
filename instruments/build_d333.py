"""Build the D332 payload.

Every guard REFUSES. None of them prints a warning and continues.
Every comparison value that a guard uses enters as an ARGUMENT and is
never computed from the payload being checked, which is the defect
D330 carried and D331 corrected.

Usage:
  python3 build.py --out PATH --expect-items N --expect-s331 N
                   --expect-s332 N [--arm NAME]

--arm drives a single refuse arm red and exits non-zero. With no --arm
the builder writes the payload.
"""

import argparse
import re
import sys

import importlib
C = None
SESSION = 332
NS_A = 331
NS_B = 332

HEAD_COL = 2
PROSE_COL = 4
ITEM_COL = 4
FIND_COL = 12
FIND_CONT = 23
WRAP_MAX = 72
GLUE = "\x00"


def glue_fg(text):
    """No FG-S and no D-code token may begin a wrapped line. Bind each
    to the word before it. Anchors are rendered separately and are
    intended. The class is unconstructible, not merely guarded."""
    text = re.sub(r" (FG-S)", GLUE + r"\1", text)
    return re.sub(r" (D[0-9]{3}-)", GLUE + r"\1", text)


class Refuse(Exception):
    pass


def nb(text):
    """Opt-in glue. Spaces inside become non-breaking for the wrapper."""
    return text.replace(" ", GLUE)


def wrap(text, first_col, cont_col, limit=WRAP_MAX):
    words = text.split(" ")
    lines = []
    cur = " " * first_col
    curlen = first_col
    started = False
    for w in words:
        if not w:
            continue
        add = len(w) if not started else len(w) + 1
        if started and curlen + add > limit:
            lines.append(cur)
            cur = " " * cont_col + w
            curlen = cont_col + len(w)
        else:
            cur = cur + (" " if started else "") + w
            curlen = curlen + add
            started = True
    lines.append(cur)
    return [l.replace(GLUE, " ") for l in lines]


def render(items, f331, f332):
    if C.HEAD is None:
        out = []
    else:
        out = [""]
        out += wrap(glue_fg("- S%d " % SESSION + C.HEAD),
                    HEAD_COL, PROSE_COL)
    for para in C.PROSE:
        out.append("")
        out += wrap(glue_fg(para), PROSE_COL, PROSE_COL)
    for n, (code, text) in enumerate(items):
        if not (C.HEAD is None and n == 0):
            out.append("")
        cont = ITEM_COL + len(code) + 2
        out += wrap(code + GLUE + GLUE + glue_fg(text), ITEM_COL, cont)
    out.append("")
    out.append(" " * PROSE_COL + "FINDINGS")
    for group in (f331, f332):
        for code, label, text in group:
            out.append("")
            out += wrap(code + GLUE + GLUE + label + ". "
                        + glue_fg(text), FIND_COL, FIND_CONT)
    return out


# ---------------------------------------------------------------- guards

STRICT = re.compile(r"^ {12}FG-S[0-9]+-[A-Z]+")
STRICT_A = re.compile(r"^ {12}FG-S[0-9]")
LOOSE = re.compile(r"^ +FG-S[0-9]+-[A-Z]+")
HEADLINE = re.compile(r"^  - S[0-9]")
ITEMLINE = re.compile(r"^    D[0-9]+-[0-9]+  ")


def g_ascii(lines):
    for i, l in enumerate(lines):
        for ch in l:
            if ord(ch) < 32 or ord(ch) > 126:
                raise Refuse("NONASCII at payload line %d" % (i + 1))


def g_width(lines, limit):
    for i, l in enumerate(lines):
        if len(l) > limit:
            raise Refuse("LINE_OVER_%d at payload line %d, len %d"
                         % (limit, i + 1, len(l)))


def g_trailws(lines):
    for i, l in enumerate(lines):
        if l != l.rstrip(" "):
            raise Refuse("TRAILING_WS at payload line %d" % (i + 1))


def g_shape_agreement(lines):
    """The house censuses this document with a BRE that needs only a
    digit after FG-S. A shape narrower than the census shape is not a
    guard on the census."""
    a = sum(1 for l in lines if STRICT_A.match(l))
    b = sum(1 for l in lines if STRICT.match(l))
    if a != b:
        for i, l in enumerate(lines):
            if STRICT_A.match(l) and not STRICT.match(l):
                raise Refuse("SHAPE_DISAGREE at payload line %d: %s"
                             % (i + 1, l[:44]))
        raise Refuse("SHAPE_DISAGREE %d vs %d" % (a, b))
    return a


def g_anchor_collision(lines, intended):
    """A strict finding anchor on a line that is not an intended
    finding head is a collision. intended is a set of line indices."""
    for i, l in enumerate(lines):
        if STRICT_A.match(l) and i not in intended:
            raise Refuse("ANCHOR_COLLISION at payload line %d: %s"
                         % (i + 1, l[:40]))


def g_shallow_code(lines):
    """The 1488 and 1576 class: a code beginning a line at any indent
    other than twelve."""
    for i, l in enumerate(lines):
        if LOOSE.match(l) and not STRICT.match(l):
            raise Refuse("CODE_AT_WRONG_INDENT at payload line %d: %s"
                         % (i + 1, l[:40]))


def g_counts(lines, expect_items, expect_s331, expect_s332):
    items = sum(1 for l in lines if ITEMLINE.match(l))
    if items != expect_items:
        raise Refuse("ITEM_COUNT %d expected %d" % (items, expect_items))
    s331 = sum(1 for l in lines
               if re.match(r"^ {12}FG-S%d-" % NS_A, l))
    s332 = sum(1 for l in lines
               if re.match(r"^ {12}FG-S%d-" % NS_B, l))
    if s331 != expect_s331:
        raise Refuse("S331_FINDINGS %d expected %d" % (s331, expect_s331))
    if s332 != expect_s332:
        raise Refuse("S332_FINDINGS %d expected %d" % (s332, expect_s332))
    return items, s331, s332


def g_duplicate_codes(lines):
    seen = {}
    for i, l in enumerate(lines):
        m = STRICT.match(l)
        if m:
            code = l[12:].split("  ")[0]
            if code in seen:
                raise Refuse("DUPLICATE_CODE %s at lines %d and %d"
                             % (code, seen[code] + 1, i + 1))
            seen[code] = i
    return len(seen)


def g_heads(lines, expect):
    n = sum(1 for l in lines if HEADLINE.match(l))
    if n != expect:
        raise Refuse("HEAD_COUNT %d expected %d" % (n, expect))


def g_seam(lines, entry_mode):
    if entry_mode:
        if lines[0] != "":
            raise Refuse("SEAM: an entry payload must open with one blank line")
        if lines[1].strip() == "":
            raise Refuse("SEAM: two blank lines at the head")
    else:
        if lines[0].strip() == "":
            raise Refuse("SEAM: a continuation must not open with a blank line, the document already ends with one")
    if lines[-1].strip() == "":
        raise Refuse("SEAM: no payload may close with a blank line, the document must end on a line that is not blank")


SESSION_COUNT = re.compile(
    r"(?<![-\w])(one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|"
    r"eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|"
    r"eighty|ninety|hundred|[0-9]+)"
    r"\s+(?:\S+\s+){0,3}(gates|gate|pastes|paste)\b",
    re.IGNORECASE)


def g_no_session_count(text):
    """An entry may not state a number that counts the session that
    contains it. See D332-18."""
    m = SESSION_COUNT.search(text)
    if m:
        raise Refuse("SESSION_COUNT: the payload contains %r" % m.group(0))


def g_no_self_size(text, forbidden):
    """forbidden is a list of strings the content may not contain,
    supplied by the caller. Used for the payload byte and line counts
    so that no sentence can state the size of the file it lives in."""
    for tok in forbidden:
        if tok in text:
            raise Refuse("SELF_SIZE: the payload contains %r" % tok)


def g_blank_before_head(lines):
    for i, l in enumerate(lines):
        if HEADLINE.match(l):
            if i == 0 or lines[i - 1].strip() != "":
                raise Refuse("TEXT_BEFORE_HEAD at payload line %d" % (i + 1))


GUARDS = ["ascii", "width", "trailws", "shallow_code",
          "item_count", "s331_count", "s332_count", "duplicate_codes",
          "head_count", "seam_open", "self_size",
          "blank_before_head", "width_71", "shape_disagree",
          "anchor_raw", "session_count", "seam_trailing_blank"]


def build(args):
    items = list(C.ITEMS)
    f331 = list(C.FINDINGS_S331)
    f332 = list(C.FINDINGS_S332)
    arm = args.arm

    if arm == "item_count":
        items = items[:-1]
    if arm == "s331_count":
        f331 = f331[:-1]
    if arm == "s332_count":
        f332 = f332[:-1]
    if arm == "duplicate_codes":
        f332 = f332 + [f332[0]]
    if arm == "ascii":
        items = items + [("D%d-99" % SESSION,
                          "a non ascii char follows: \u2014")]
    if arm == "width":
        items = items + [("D%d-99" % SESSION, "x" * 200)]

    lines = render(items, f331, f332)

    if arm == "trailws":
        lines = lines + ["    trailing space here "]
    if arm == "shallow_code":
        lines = lines + ["      FG-S%d-Z at six spaces" % NS_B]
    if arm == "shape_disagree":
        lines = lines + ["            FG-S%d hold 101 of which 100" % NS_A]
    if arm == "anchor_raw":
        lines = lines + ["            FG-S%d-Z  SEAT. injected" % NS_B]
    if arm == "seam_open":
        if C.HEAD is None:
            lines = [""] + lines
        else:
            lines = lines[1:]
    if arm == "seam_trailing_blank":
        lines = lines + [""]
    if arm == "blank_before_head":
        lines = [lines[0], "    text before the head"] + lines[1:]

    intended = set()
    for i, l in enumerate(lines):
        if STRICT.match(l):
            code = l[12:].split("  ")[0]
            if code in [c for c, _, _ in f331] + [c for c, _, _ in f332]:
                nxt = l[12 + len(code):]
                if nxt.startswith("  "):
                    intended.add(i)

    g_ascii(lines)
    g_width(lines, 71 if arm == "width_71" else WRAP_MAX)
    g_trailws(lines)
    g_shallow_code(lines)
    g_shape_agreement(lines)
    g_anchor_collision(lines, intended)
    g_seam(lines, C.HEAD is not None)
    g_blank_before_head(lines)
    ndistinct = g_duplicate_codes(lines)
    nitems, n331, n332 = g_counts(lines, args.expect_items,
                                  args.expect_s331, args.expect_s332)
    g_heads(lines, args.expect_heads)

    text = "\n".join(lines) + "\n"
    g_no_self_size(text, args.forbid)
    if args.no_session_count:
        g_no_session_count(text)
    if arm == "session_count":
        g_no_session_count("this block ran thirteen gates in total")

    return lines, text, nitems, n331, n332, ndistinct


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out")
    p.add_argument("--expect-items", type=int)
    p.add_argument("--expect-s331", type=int)
    p.add_argument("--expect-s332", type=int)
    p.add_argument("--forbid", nargs="*", default=[])
    p.add_argument("--arm", default=None)
    p.add_argument("--content", default="content_d332")
    p.add_argument("--session", type=int, default=332)
    p.add_argument("--ns-first", type=int, default=None)
    p.add_argument("--ns-second", type=int, default=None)
    p.add_argument("--expect-heads", type=int, default=1)
    p.add_argument("--no-session-count", action="store_true")
    p.add_argument("--list-arms", action="store_true")
    args = p.parse_args()

    global C, SESSION, NS_A, NS_B
    C = importlib.import_module(args.content)
    SESSION = args.session
    NS_A = args.ns_first if args.ns_first is not None else SESSION - 1
    NS_B = args.ns_second if args.ns_second is not None else SESSION

    if args.list_arms:
        for a in GUARDS:
            print(a)
        return 0

    if args.expect_items is None or args.expect_s331 is None or args.expect_s332 is None:
        print("REFUSE MISSING_EXPECTATION: every count must enter as an argument")
        return 5

    if args.arm is not None and args.arm not in GUARDS:
        print("REFUSE UNKNOWN_ARM %s" % args.arm)
        return 3

    try:
        lines, text, ni, n1, n2, nd = build(args)
    except Refuse as e:
        print("REFUSE %s" % e)
        return 2

    if args.arm is not None:
        print("ARM_DID_NOT_FIRE %s" % args.arm)
        return 4

    print("ITEMS %d" % ni)
    print("FINDINGS_S331 %d" % n1)
    print("FINDINGS_S332 %d" % n2)
    print("DISTINCT_CODES %d" % nd)
    print("PAYLOAD_LINES %d" % len(lines))
    print("MAXLEN %d" % max(len(l) for l in lines))
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(text)
        print("WROTE %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
