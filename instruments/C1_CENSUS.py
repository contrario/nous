#!/usr/bin/env python3
# C1 THE CENSUS OF THE LEDGER. FOUR SHAPES, THEIR DIFFERENCES IN BOTH
# DIRECTIONS, AND A BOUND ON WHAT NO LINE ORIENTED SHAPE CAN SEE.
#
# THIS BODY IS WRITE FREE AND THE CLAIM IS TESTABLE FROM ITS OWN
# OUTPUT. No file is opened for writing. No directory is created. No
# temporary path is used. No network call is made. No key is read.
# THREE GIT VERBS ARE RUN AND ALL THREE ARE READ ONLY:
#   rev-parse --verify --quiet HEAD
#   ls-files
#   cat-file -p <ref>:<path>
# THERE IS NO FETCH. FETCH_HEAD AND THE REMOTE TRACKING REFS ARE NOT
# WRITTEN BY THIS BODY. The preceding opening instrument carried a
# header claiming no write while its body fetched; this one does not,
# and L1 prints the verbs so the header can be checked against them.
#
# T5 SELF CHECK RUNS BEFORE ANY chdir AND BEFORE ANY REPOSITORY READ.
#
# USAGE
#   python3 FILE EXPECTED_SHA256 [REPO_ROOT] [BUILDER_DIR]
# BUILDER_DIR defaults to the directory this body was invoked from.
# THIS BODY HARDCODES NO FILENAME EXCEPT THE PATH OF THE LEDGER
# INSIDE THE REPOSITORY, WHICH IS THE OBJECT ITSELF.

import hashlib
import os
import re
import subprocess
import sys

DOCREL = "docs/GLM_SUPERSESSION_DESIGN.md"
BUILDER_PIN = ("1b8093f48abd748e9d9b754c4ab19224111d5107"
               "e74396d2a19cd23cededcf80")
GLUE_MARK = "glue_fg"
BUILDER_NAME_ENTRY = 333
STRICT_INDENT = 12
CTX = 100


def out(s):
    sys.stdout.write(s + "\n")


def refuse(tok, *lines):
    out("REFUSE " + tok)
    for l in lines:
        out(l)
    sys.exit(9)


# ---------------------------------------------------------------- T5
SELF = sys.argv[0]
if not os.path.isfile(SELF):
    refuse("T5_NOT_A_FILE", "SELF " + str(SELF))
if len(sys.argv) < 2 or not sys.argv[1]:
    refuse("T5_NO_DIGEST_ARGUMENT",
           "USAGE python3 FILE EXPECTED_SHA256 [REPO_ROOT] [BUILDER_DIR]")
with open(SELF, "rb") as fh:
    T5C = hashlib.sha256(fh.read()).hexdigest()
if T5C != sys.argv[1]:
    refuse("T5_DIGEST_MISMATCH", "COMPUTED " + T5C, "GIVEN    " + sys.argv[1])
out("T5_OK " + T5C)


# ----------------------------------------------------- THE FOUR SHAPES
# Every shape carries the same delimiter guard on both ends, so a
# substring is never a member. FG-S350-A is not found inside
# FG-S350-AB, and XFG-S350-A is not a code.
LEFT = r"(?<![0-9A-Za-z-])"
RIGHT = r"(?![0-9A-Za-z])"
BODY = r"FG-S([0-9]+)-([A-Z]+)"

RE_ANY = re.compile(LEFT + BODY + RIGHT)
RE_STRICT = re.compile(r"^( {12})" + BODY + RIGHT)
RE_LOOSE = re.compile(r"^( +)" + BODY + RIGHT)
RE_HEAD = re.compile(r"^  - S([0-9]+)")
RE_DANCH = re.compile(r"^    D([0-9]+)-")
RE_WIDE = re.compile(LEFT + r"FG-S([0-9]+)-([A-Za-z0-9]+)" + RIGHT)
RE_CASE = re.compile(LEFT + r"[Ff][Gg]-[Ss]([0-9]+)-([A-Za-z]+)" + RIGHT)


def codes_any(text):
    return [m.group(0) for m in RE_ANY.finditer(text)]


def rows_strict(lines):
    r = []
    for i, l in enumerate(lines, 1):
        m = RE_STRICT.match(l)
        if m:
            r.append((i, "FG-S" + m.group(2) + "-" + m.group(3),
                      len(m.group(1))))
    return r


def rows_loose(lines):
    r = []
    for i, l in enumerate(lines, 1):
        m = RE_LOOSE.match(l)
        if m:
            r.append((i, "FG-S" + m.group(2) + "-" + m.group(3),
                      len(m.group(1))))
    return r


def fam(code):
    """FG-S350-A -> 350. The S is not part of the family number and a
    key that carries it renders FG-SS350- and sorts as a crash."""
    return code.split("-")[1][1:]


def heads(lines):
    return [(i, m.group(1)) for i, l in enumerate(lines, 1)
            for m in [RE_HEAD.match(l)] if m]


def anywhere(lines):
    r = []
    for i, l in enumerate(lines, 1):
        for m in RE_ANY.finditer(l):
            r.append((i, m.group(0)))
    return r


def attribute(lines, target_lines):
    """Map each target line number to the nearest preceding head line
    number. Returns dict lineno -> head value or None."""
    marks = []
    for i, l in enumerate(lines, 1):
        m = RE_HEAD.match(l)
        if m:
            marks.append((i, m.group(1)))
    res = {}
    for t in target_lines:
        cur = None
        for (i, v) in marks:
            if i <= t:
                cur = v
            else:
                break
        res[t] = cur
    return res


# ------------------------------------------- G0 SELFTEST, IN MEMORY
out("== G0 SELFTEST. EVERY SHAPE IS DRIVEN GREEN AND RED ON SYNTHETIC")
out("   TEXT BEFORE ANY REPOSITORY BYTE IS READ. AN EMPTY RESULT FROM")
out("   A BLIND ENGINE READS EXACTLY LIKE A DISCOVERY.")

SYN = [
    "  - S900 a synthetic head",
    "    D900-1",
    "            FG-S900-A  SEAT",
    "      FG-S900-B  a row at an indent no strict shape catches",
    "            FG-S900-A  SEAT",
    "prose that mentions FG-S900-C and never gives it a row",
    "a substring trap FG-S900-AB and a prefixed one XFG-S900-D",
    "  - S900 a repeated head",
    "            FG-S901-E  WORLD",
    "lower case fg-s900-f and a digit suffix FG-S900-G2",
]

s_rows = rows_strict(SYN)
if not s_rows:
    refuse("C1_SELFTEST_STRICT_BLIND")
out("SELFTEST_STRICT_ROWS " + " ".join(c for (_, c, _) in s_rows))
if [c for (_, c, _) in s_rows] != ["FG-S900-A", "FG-S900-A",
                                   "FG-S901-E"]:
    refuse("C1_SELFTEST_STRICT_MISMATCH")

l_rows = rows_loose(SYN)
out("SELFTEST_LOOSE_ROWS " + " ".join(c for (_, c, _) in l_rows))
if [c for (_, c, _) in l_rows] != ["FG-S900-A", "FG-S900-B",
                                   "FG-S900-A", "FG-S901-E"]:
    refuse("C1_SELFTEST_LOOSE_MISMATCH")

a_all = sorted(set(c for (_, c) in anywhere(SYN)))
out("SELFTEST_ANYWHERE " + " ".join(a_all))
if a_all != ["FG-S900-A", "FG-S900-AB", "FG-S900-B", "FG-S900-C",
             "FG-S901-E"]:
    refuse("C1_SELFTEST_ANYWHERE_MISMATCH", "GOT " + " ".join(a_all))
out("SELFTEST_SUBSTRING_IS_NOT_A_MEMBER OK  FG-S900-A not taken from")
out("  FG-S900-AB, and XFG-S900-D is not a code")

if "FG-S900-D" in a_all:
    refuse("C1_SELFTEST_LEFT_DELIMITER_BROKEN")
if len([c for c in a_all if c == "FG-S900-A"]) != 1:
    refuse("C1_SELFTEST_SET_BROKEN")

if fam("FG-S350-A") != "350" or fam("FG-S1-ZZ") != "1":
    refuse("C1_SELFTEST_FAMILY_KEY_WRONG",
           "GOT " + fam("FG-S350-A") + " AND " + fam("FG-S1-ZZ"))
if not fam("FG-S350-A").isdigit():
    refuse("C1_SELFTEST_FAMILY_KEY_NOT_A_NUMBER")
out("SELFTEST_FAMILY_KEY_IS_THE_DIGITS OK  FG-S350-A -> " +
    fam("FG-S350-A"))

h = heads(SYN)
out("SELFTEST_HEADS " + " ".join(v for (_, v) in h))
if [v for (_, v) in h] != ["900", "900"]:
    refuse("C1_SELFTEST_HEAD_MISMATCH")
out("SELFTEST_HEAD_DUPLICATE_SEEN 1")

att = attribute(SYN, [4, 9])
out("SELFTEST_ATTRIBUTION line4=" + str(att[4]) + " line9=" + str(att[9]))
if att[4] != "900" or att[9] != "900":
    refuse("C1_SELFTEST_ATTRIBUTION_MISMATCH")
if attribute(["            FG-S900-A"], [1])[1] is not None:
    refuse("C1_SELFTEST_ATTRIBUTION_INVENTED_A_HEAD")
out("SELFTEST_ROW_BEFORE_ANY_HEAD_ATTRIBUTES_TO_NOTHING OK")

neg = codes_any("x = 1\nnothing here at all\nFGS900A no hyphens\n")
out("SELFTEST_NEGATIVE_MUST_BE_EMPTY " + str(len(neg)))
if neg:
    refuse("C1_SELFTEST_NEGATIVE_FIRED", " ".join(neg))

wide = sorted(set(m.group(0) for m in RE_WIDE.finditer("\n".join(SYN))))
out("SELFTEST_WIDE_PROBE_SEES_DIGIT_SUFFIX " +
    str(int("FG-S900-G2" in wide)))
if "FG-S900-G2" not in wide:
    refuse("C1_SELFTEST_WIDE_PROBE_BLIND")
case = sorted(set(m.group(0) for m in RE_CASE.finditer("\n".join(SYN))))
out("SELFTEST_CASE_PROBE_SEES_LOWER " + str(int("fg-s900-f" in case)))
if "fg-s900-f" not in case:
    refuse("C1_SELFTEST_CASE_PROBE_BLIND")

split_src = ["a wrapped reference to FG-S9", "02-H continues here"]
j = split_src[0].rstrip() + split_src[1].lstrip()
found_join = set(codes_any(j))
found_lines = set(codes_any(split_src[0])) | set(codes_any(split_src[1]))
out("SELFTEST_WRAP_CANDIDATE " + " ".join(sorted(found_join -
                                                 found_lines)))
if "FG-S902-H" not in (found_join - found_lines):
    refuse("C1_SELFTEST_WRAP_LEG_BLIND")
out("SELFTEST_ALL_GREEN nine shapes and one join, driven both ways")


# ------------------------------------------------ G1 REPOSITORY GUARDS
out("== G1 REPOSITORY GUARDS")
out("HOST " + str(os.uname().nodename))
try:
    import datetime
    out("DATE_UTC " + datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
except Exception:
    out("DATE_UTC UNAVAILABLE")

cands = []
if len(sys.argv) > 2 and sys.argv[2]:
    cands.append(sys.argv[2])
cands += ["/opt/aetherlang_agents/nous", "/opt/neuroaether/nous"]
REPO = ""
for d in cands:
    if os.path.isdir(os.path.join(d, ".git")):
        REPO = d
        break
if not REPO:
    refuse("C1_NO_REPO_ROOT", "TRIED " + " ".join(cands))
out("REPO_ROOT " + REPO)


def git(*a):
    try:
        p = subprocess.run(["git", "-C", REPO] + list(a),
                           capture_output=True, text=True, timeout=120)
    except Exception:
        return ""
    return p.stdout


GH = git("rev-parse", "--verify", "--quiet", "HEAD").strip()
out("GIT_VERB_1 rev-parse --verify --quiet HEAD")
out("GIT_HEAD [" + GH + "]")
if len(GH) != 40 or any(c not in "0123456789abcdef" for c in GH):
    refuse("C1_GIT_HEAD_NOT_A_COMMIT_ID", "GOT [" + GH + "]",
           "git prints the literal word HEAD in a repository with no",
           "commits and a guard that tests only for emptiness passes it")
tracked = [l for l in git("ls-files").split("\n") if l]
out("GIT_VERB_2 ls-files")
out("TRACKED_FILES_MUST_BE_NONZERO " + str(len(tracked)))
if not tracked:
    refuse("C1_GIT_BLIND", "tracked file count is zero")

DOCABS = os.path.join(REPO, DOCREL)
if not os.path.isfile(DOCABS):
    refuse("C1_GATE_DOC_ABSENT", DOCREL)
raw = open(DOCABS, "rb").read()
out("GATE_DOC_BYTES_MUST_BE_NONZERO " + str(len(raw)))
if not raw:
    refuse("C1_GATE_DOC_EMPTY")
DOCSHA = hashlib.sha256(raw).hexdigest()
out("DOC_SHA " + DOCSHA)
text = raw.decode("utf-8", "replace")
lines = text.split("\n")
if lines and lines[-1] == "":
    lines = lines[:-1]
out("DOC_LINES " + str(len(lines)))

blob = git("cat-file", "-p", "origin/main:" + DOCREL)
out("GIT_VERB_3 cat-file -p origin/main:" + DOCREL)
if blob:
    bsha = hashlib.sha256(blob.encode("utf-8", "replace")).hexdigest()
    same = (bsha == DOCSHA)
    out("ORIGIN_BLOB_SHA " + bsha)
    out("WORKTREE_EQ_ORIGIN_NOW " + ("YES" if same else "NO"))
    if not same:
        out("  THE OBJECT MOVED SINCE THE OPENING RULE READ IT, OR THE")
        out("  ENCODING ROUND TRIP DIFFERS. EVERY COUNT BELOW IS OVER")
        out("  THE WORKTREE FILE AND OVER NOTHING ELSE.")
else:
    out("ORIGIN_BLOB WITHHELD no origin/main object was returned")
    out("  A MISSING SECOND ORACLE IS NOT AN AGREEMENT.")


# ----------------------------------- G2 ENGINE SENTINELS ON THE OBJECT
out("== G2 SENTINELS DRIVEN ON THE OBJECT ITSELF, NOT ON A SYNTHETIC")
out("   COPY. A CONTROL THAT CANNOT REACH THE OBJECT UNDER TEST IS")
out("   NOT A CONTROL.")

R_STRICT = rows_strict(lines)
R_LOOSE = rows_loose(lines)
R_ANY = anywhere(lines)
H_ALL = heads(lines)

out("STRICT_ROWS_MUST_BE_NONZERO " + str(len(R_STRICT)))
if not R_STRICT:
    refuse("C1_STRICT_ENGINE_BLIND")
out("LOOSE_ROWS_MUST_BE_NONZERO " + str(len(R_LOOSE)))
if not R_LOOSE:
    refuse("C1_LOOSE_ENGINE_BLIND")
out("ANYWHERE_HITS_MUST_BE_NONZERO " + str(len(R_ANY)))
if not R_ANY:
    refuse("C1_ANYWHERE_ENGINE_BLIND")
out("HEAD_LINES_MUST_BE_NONZERO " + str(len(H_ALL)))
if not H_ALL:
    refuse("C1_HEAD_ENGINE_BLIND")
D_ANCH = [i for i, l in enumerate(lines, 1) if RE_DANCH.match(l)]
out("D_ANCHORS_MUST_BE_NONZERO " + str(len(D_ANCH)))
if not D_ANCH:
    refuse("C1_DANCHOR_ENGINE_BLIND")

NEGTOK = "FG-S99999-ZQQQ"
nhits = len([1 for (_, c) in R_ANY if c == NEGTOK])
out("NEGATIVE_CONTROL_ON_THE_OBJECT_MUST_BE_ZERO " + str(nhits))
if nhits:
    refuse("C1_NEGATIVE_CONTROL_FIRED", NEGTOK)

plant_lines = list(lines)
plant_lines.insert(len(plant_lines) // 2, " " * STRICT_INDENT + NEGTOK +
                   "  SEAT")
plant_lines.insert(len(plant_lines) // 3, "  prose planting " + NEGTOK)
ps = len(rows_strict(plant_lines)) - len(R_STRICT)
pl = len(rows_loose(plant_lines)) - len(R_LOOSE)
pa = len(anywhere(plant_lines)) - len(R_ANY)
out("PLANT_CONTROL_ON_A_COPY_OF_THE_OBJECT strict+" + str(ps) +
    " loose+" + str(pl) + " anywhere+" + str(pa))
if (ps, pl, pa) != (1, 1, 2):
    refuse("C1_PLANT_CONTROL_DID_NOT_LAND",
           "the shapes did not move by the planted amount, so a zero",
           "from any of them evidences nothing about this document")
out("  THE COPY IS IN MEMORY. THE FILE ON DISK IS NOT TOUCHED.")

POSTOK = R_STRICT[0][1]
p1 = len([1 for (_, c, _) in R_STRICT if c == POSTOK])
p2 = len([1 for (_, c, _) in R_LOOSE if c == POSTOK])
p3 = len([1 for (_, c) in R_ANY if c == POSTOK])
out("POSITIVE_CONTROL " + POSTOK + " strict " + str(p1) + " loose " +
    str(p2) + " anywhere " + str(p3))
if not (p1 and p2 and p3):
    refuse("C1_POSITIVE_CONTROL_DID_NOT_REACH_EVERY_SHAPE")
out("SENTINELS_ALL_GREEN")


# ----------------------------------------------- L1 THE FOUR SHAPES
out("== L1 THE FOUR SHAPES. NO ONE OF THEM REPLACES ANOTHER.")
S_SET = set(c for (_, c, _) in R_STRICT)
L_SET = set(c for (_, c, _) in R_LOOSE)
A_SET = set(c for (_, c) in R_ANY)
S_FAM = set(fam(c) for c in S_SET)
L_FAM = set(fam(c) for c in L_SET)
A_FAM = set(fam(c) for c in A_SET)

out("SHAPE_1_STRICT      indent exactly 12   OCC " + str(len(R_STRICT)) +
    "  DISTINCT " + str(len(S_SET)) + "  FAMILIES " + str(len(S_FAM)))
out("SHAPE_2_LOOSE       any indent, line leading   OCC " +
    str(len(R_LOOSE)) + "  DISTINCT " + str(len(L_SET)) +
    "  FAMILIES " + str(len(L_FAM)))
out("SHAPE_3_ANYWHERE    no anchor at all   OCC " + str(len(R_ANY)) +
    "  DISTINCT " + str(len(A_SET)) + "  FAMILIES " + str(len(A_FAM)))
out("SHAPE_4_FAMILY      distinct S numbers behind each shape above")
out("HEAD_LINES OCC " + str(len(H_ALL)) + "  DISTINCT " +
    str(len(set(v for (_, v) in H_ALL))))
out("D_ANCHOR_LINES OCC " + str(len(D_ANCH)))


# --------------------------------- L2 THE DIFFERENCES, BOTH DIRECTIONS
out("== L2 THE DIFFERENCES, PRINTED IN BOTH DIRECTIONS. DERIVED.")
out("DERIVED LOOSE_MINUS_STRICT_OCC " + str(len(R_LOOSE) - len(R_STRICT)))
out("DERIVED STRICT_MINUS_LOOSE_OCC " + str(len(R_STRICT) - len(R_LOOSE)))
ls_codes = sorted(L_SET - S_SET)
sl_codes = sorted(S_SET - L_SET)
out("CODES_LOOSE_NOT_STRICT " + str(len(ls_codes)) + "  " +
    " ".join(ls_codes))
out("CODES_STRICT_NOT_LOOSE " + str(len(sl_codes)) + "  " +
    " ".join(sl_codes))
al_codes = sorted(A_SET - L_SET)
la_codes = sorted(L_SET - A_SET)
out("CODES_ANYWHERE_NOT_A_ROW " + str(len(al_codes)))
out("CODES_A_ROW_BUT_NOT_ANYWHERE " + str(len(la_codes)) + "  " +
    " ".join(la_codes))
if la_codes:
    out("  A NONEMPTY SET HERE IS AN INSTRUMENT DEFECT, NOT A FINDING:")
    out("  every row is a line and every line is searched anywhere.")
out("FAMILIES_LOOSE_NOT_STRICT " + str(len(L_FAM - S_FAM)) + "  " +
    " ".join(sorted(L_FAM - S_FAM)))
out("FAMILIES_ANYWHERE_NOT_LOOSE " + str(len(A_FAM - L_FAM)) + "  " +
    " ".join(sorted(A_FAM - L_FAM)))
out("FAMILIES_STRICT_NOT_LOOSE " + str(len(S_FAM - L_FAM)) + "  " +
    " ".join(sorted(S_FAM - L_FAM)))


# ------------------------------------------- L3 THE INVISIBLE FAMILIES
out("== L3 THE FAMILIES THAT EXIST AT A LOOSE INDENT AND NOT AT THE")
out("   STRICT ONE. EVERY SEALED FG FIGURE OF THIS HOUSE IS STRICT.")
inv = sorted(L_FAM - S_FAM, key=lambda x: int(x))
out("INVISIBLE_FAMILIES " + str(len(inv)) + "  " + " ".join(inv))
inv_lines = [i for (i, c, w) in R_LOOSE if fam(c) in set(inv)]
att_inv = attribute(lines, inv_lines)
for f in inv:
    out("  FAMILY FG-S" + f + "-")
    for (i, c, w) in R_LOOSE:
        if fam(c) == f:
            out("    LINE " + str(i).rjust(6) + "  INDENT " +
                str(w).rjust(3) + "  ENTRY " + str(att_inv.get(i)) +
                "  " + c)
            out("      TEXT " + lines[i - 1].strip()[:CTX])


# --------------------------------------------- L4 THE PROSE ONLY CODES
out("== L4 CODES THAT OCCUR AND NEVER LEAD A LINE. A REFERENCE IS NOT")
out("   A FINDING. EACH IS PRINTED WITH EVERY LINE THAT CARRIES IT, SO")
out("   A DANGLING REFERENCE IS DISTINGUISHED FROM A ROW AT AN INDENT")
out("   NO SHAPE CATCHES.")
prose_only = sorted(A_SET - L_SET)
out("PROSE_ONLY_DISTINCT " + str(len(prose_only)))
for c in prose_only:
    where = [i for (i, cc) in R_ANY if cc == c]
    a = attribute(lines, where)
    out("  CODE " + c + "  OCCURRENCES " + str(len(where)))
    for i in where:
        out("    LINE " + str(i).rjust(6) + "  ENTRY " + str(a.get(i)) +
            "  " + lines[i - 1].strip()[:CTX])


# -------------------------------------- L5 THE OFF INDENT ROWS IN FULL
out("== L5 EVERY ROW WHOSE INDENT IS NOT TWELVE, WITH THE LINE BEFORE")
out("   AND THE LINE AFTER. THE HYPOTHESIS IS THAT THESE ARE WRAPPED")
out("   PROSE, NOT ROWS. THE CONTEXT DECIDES IT AND IS PRINTED WHOLE.")
off = [(i, c, w) for (i, c, w) in R_LOOSE if w != STRICT_INDENT]
out("OFF_INDENT_ROWS " + str(len(off)))
att_off = attribute(lines, [i for (i, _, _) in off])
for (i, c, w) in off:
    out("  ROW LINE " + str(i) + "  INDENT " + str(w) + "  ENTRY " +
        str(att_off.get(i)) + "  " + c)
    prev = lines[i - 2] if i >= 2 else ""
    nxt = lines[i] if i < len(lines) else ""
    pe = prev.rstrip()[-1:] if prev.strip() else "(blank)"
    out("    PREV " + prev.strip()[:CTX])
    out("    PREV_ENDS_WITH [" + pe + "]")
    out("    THIS " + lines[i - 1].strip()[:CTX])
    out("    NEXT " + nxt.strip()[:CTX])
out("ENTRIES_CARRYING_AN_OFF_INDENT_ROW " +
    " ".join(sorted(set(str(att_off.get(i)) for (i, _, _) in off))))


# -------------------------------------------------- L6 THE BUILDER LEG
out("== L6 THE GUARD THE HYPOTHESIS NAMES. THE BUILDER IS LOCATED BY")
out("   DIGEST AND NEVER BY NAME.")
bdir = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else \
    os.path.dirname(os.path.abspath(SELF))
out("BUILDER_SEARCH_DIR " + bdir)
found = []
try:
    for e in sorted(os.listdir(bdir)):
        p = os.path.join(bdir, e)
        if not os.path.isfile(p):
            continue
        try:
            d = hashlib.sha256(open(p, "rb").read()).hexdigest()
        except Exception:
            continue
        if d == BUILDER_PIN:
            found.append((e, p))
except Exception as ex:
    out("BUILDER_DIR_UNREADABLE " + str(ex)[:80])
out("BUILDER_MATCHES_BY_DIGEST " + str(len(found)))
if len(found) != 1:
    out("BUILDER WITHHELD. The pinned bytes are not in that directory,")
    out("  or are there more than once. NO CLAIM IS MADE ABOUT THE")
    out("  GUARD, AND THE HYPOTHESIS IS NEITHER SUPPORTED NOR REFUTED.")
else:
    bname, bpath = found[0]
    bsrc = open(bpath, "rb").read().decode("utf-8", "replace")
    out("BUILDER_FILE_AS_IT_IS_NAMED_HERE " + bname)
    out("BUILDER_SHA " + BUILDER_PIN)
    n = bsrc.count(GLUE_MARK)
    out("GLUE_MARK_OCCURRENCES " + str(n))
    if n == 0:
        out("  THE MARK IS ABSENT FROM THE PINNED BYTES. The hypothesis")
        out("  names a guard this file does not contain.")
    for k, l in enumerate(bsrc.split("\n"), 1):
        if GLUE_MARK in l:
            out("    LINE " + str(k).rjust(5) + "  " + l.strip()[:CTX])
out("BOUNDARY_ENTRY_FROM_THE_BUILDER_FILENAME " +
    str(BUILDER_NAME_ENTRY))
out("  DERIVED_FROM_A_FILENAME. A NAME IS NOT A MEASUREMENT. This")
out("  body classifies nothing by it and prints it beside the entry")
out("  numbers in L5 so the reader can.")


# ------------------------------------------------ L7 THE HEAD LINES
out("== L7 WHICH HEAD LINES REPEAT A SESSION NUMBER. NAMED, NOT")
out("   COUNTED.")
seen = {}
for (i, v) in H_ALL:
    seen.setdefault(v, []).append(i)
dups = sorted([(v, ls) for (v, ls) in seen.items() if len(ls) > 1],
              key=lambda x: int(x[0]))
out("HEAD_OCCURRENCES " + str(len(H_ALL)))
out("HEAD_DISTINCT " + str(len(seen)))
out("DERIVED REPEATED_HEAD_LINES " + str(len(H_ALL) - len(seen)))
out("HEAD_VALUES_WITH_MORE_THAN_ONE_LINE " + str(len(dups)))
for (v, ls) in dups:
    out("  S" + v + "  LINES " + " ".join(str(x) for x in ls))
    for x in ls:
        out("    " + str(x).rjust(6) + "  " + lines[x - 1].strip()[:CTX])
out("HEADS_ENUMERATED " +
    " ".join("S" + v for v in sorted(seen, key=lambda x: int(x))))


# ------------------------------------------------- L8 THE POPULATION
out("== L8 THE POPULATION. THE SHAPE IS PRINTED BESIDE EVERY FIGURE.")
out("P1 ROW_LEADING_AT_ANY_INDENT_DISTINCT " + str(len(L_SET)))
out("   SHAPE: a code whose token begins the content of a line.")
out("   THIS IS THE FIGURE THIS BODY DEFENDS AS THE POPULATION.")
out("P1_OCCURRENCES " + str(len(R_LOOSE)))
out("DERIVED P1_ROWS_MINUS_P1_DISTINCT " +
    str(len(R_LOOSE) - len(L_SET)) + "  codes with more than one row")
mult = sorted([c for c in L_SET
               if len([1 for (_, cc, _) in R_LOOSE if cc == c]) > 1])
out("CODES_WITH_MORE_THAN_ONE_ROW " + str(len(mult)) + "  " +
    " ".join(mult))
out("P0 STRICT_ONLY_DISTINCT " + str(len(S_SET)) +
    "   SHAPE: indent exactly twelve. THE SEALED FIGURE OF THIS HOUSE.")
out("DERIVED P1_MINUS_P0 " + str(len(L_SET) - len(S_SET)))
out("P2 EVERY_DISTINCT_CODE_ANYWHERE " + str(len(A_SET)))
out("   SHAPE: any occurrence. NOT A POPULATION OF FINDINGS. It is")
out("   the reference set and it is printed so the choice behind P1")
out("   is visible and reversible without another run.")
out("DERIVED P2_MINUS_P1 " + str(len(A_SET) - len(L_SET)))


# ---------------------------------------------- L9 THE WRAP BLINDNESS
out("== L9 WHAT NO LINE ORIENTED SHAPE CAN SEE. DECLARED BEFORE THE")
out("   NUMBER: a code broken across a line break is invisible to")
out("   every shape above, including SHAPE_3.")
cand = []
for i in range(len(lines) - 1):
    a = lines[i].rstrip()
    b = lines[i + 1].lstrip()
    if not a or not b:
        continue
    if "FG-S" not in a[-12:] and not a.endswith("FG-") and \
       "FG" not in a[-4:]:
        continue
    j = a + b
    fj = set(codes_any(j))
    fl = set(codes_any(lines[i])) | set(codes_any(lines[i + 1]))
    for c in sorted(fj - fl):
        cand.append((i + 1, c, a[-40:], b[:40]))
out("WRAP_SPLIT_CANDIDATES " + str(len(cand)))
out("  THIS IS A BOUND AND NOT A COUNT. Joining two lines with no")
out("  separator manufactures a code whenever a line ends inside one.")
for (i, c, a, b) in cand:
    out("  LINES " + str(i) + "/" + str(i + 1) + "  CANDIDATE " + c)
    out("    LEFT  ..." + a)
    out("    RIGHT " + b + "...")
out("DERIVED P3_UPPER_BOUND_ON_ROW_LEADING " +
    str(len(L_SET) + len(set(c for (_, c, _, _) in cand))))
out("  P1 PLUS EVERY SPLIT CANDIDATE, WHICH ASSUMES EVERY CANDIDATE IS")
out("  REAL AND IS A ROW. BOTH ASSUMPTIONS ARE FALSE IN GENERAL.")

wide_all = sorted(set(m.group(0) for m in RE_WIDE.finditer(text)))
case_all = sorted(set(m.group(0) for m in RE_CASE.finditer(text)))
out("ADVISORY_WIDE_PROBE_DISTINCT " + str(len(wide_all)) +
    "  DERIVED WIDE_MINUS_P2 " + str(len(wide_all) - len(A_SET)))
out("  SHAPE: suffix of letters OR digits. Bounds a code this body")
out("  cannot see. NOT IN ANY POPULATION FIGURE ABOVE.")
extra_wide = sorted(set(wide_all) - A_SET)
out("  MEMBERS " + " ".join(extra_wide[:40]))
out("ADVISORY_CASE_PROBE_DISTINCT " + str(len(case_all)) +
    "  DERIVED CASE_MINUS_P2 " + str(len(case_all) - len(A_SET)))
extra_case = sorted(set(case_all) - A_SET)
out("  MEMBERS " + " ".join(extra_case[:40]))


# ------------------------------------------- L10 WHAT IT CANNOT SAY
out("== L10 WHAT THIS RUN CANNOT SAY")
out("It cannot say that P1 is the number of findings this project has")
out("  made. It is the number of codes that lead a line in one file.")
out("It cannot say a prose-only code is a defect. It can say the code")
out("  is referenced and has no row at any indent in this document.")
out("It cannot say an off-indent row is a wrapping artifact. It prints")
out("  the context and the entry number and the reader decides.")
out("It cannot say when the guard the hypothesis names came into use.")
out("  A filename is not a date and this body classifies nothing by it.")
out("It cannot say anything about a code written in lower case or with")
out("  a digit in its suffix beyond the two advisory bounds in L9.")
out("It cannot say what any sealed artifact claimed. It reads one file")
out("  at one head on one host.")
out("IT IS WRITE FREE. Three git verbs, all read only, no fetch. The")
out("  plant control mutates a list in memory and not the file.")
out("== END")
