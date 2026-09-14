#!/usr/bin/env python3
# R1 THE PACKAGING CLOSURE, BY SYNTAX TREE. READ ONLY.
# NO WRITE OF ANY KIND: no file is opened for writing, no directory is
# created, no git verb is run, no network is touched, no key is read.
# THIS BODY NEVER IMPORTS THE PROJECT. It reads bytes and parses them.
# T5 SELF CHECK RUNS BEFORE ANY chdir AND BEFORE ANY REPOSITORY READ.

import ast
import hashlib
import os
import subprocess
import sys

TARGETS = ["aevolver", "migrate", "noesis_engine", "noesis_oracle"]
DEPTH_LOW = 3
DEPTH_HIGH = 12


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
           "USAGE python3 FILE EXPECTED_SHA256 [REPO_ROOT]")
with open(SELF, "rb") as fh:
    T5C = hashlib.sha256(fh.read()).hexdigest()
if T5C != sys.argv[1]:
    refuse("T5_DIGEST_MISMATCH", "COMPUTED " + T5C, "GIVEN    " + sys.argv[1])
out("T5_OK " + T5C)


# ------------------------------------------------------- THE MACHINERY
def imports_of(src, path):
    """Return list of (name, kind, lineno, conditional) or None on parse
    failure. name is the TOP LEVEL module name only. A relative import
    yields name None and kind RELATIVE."""
    try:
        tree = ast.parse(src, filename=path)
    except SyntaxError:
        return None
    cond = set()
    for node in ast.walk(tree):
        inner = []
        if isinstance(node, ast.Try):
            inner = list(node.body)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            inner = list(node.body)
        elif isinstance(node, ast.If):
            inner = list(node.body) + list(node.orelse)
        for st in inner:
            for sub in ast.walk(st):
                cond.add(id(sub))
    found = []
    for node in ast.walk(tree):
        c = "CONDITIONAL" if id(node) in cond else "TOPLEVEL"
        if isinstance(node, ast.Import):
            for a in node.names:
                found.append((a.name.split(".")[0], "IMPORT", node.lineno, c))
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                found.append((None, "RELATIVE", node.lineno, c))
            elif node.module:
                found.append((node.module.split(".")[0], "FROM",
                              node.lineno, c))
    return found


def names_from(src, path):
    r = imports_of(src, path)
    if r is None:
        return None
    return sorted(set(n for (n, k, ln, c) in r if n))


# ------------------------------------------------- G0 INTERNAL SELFTEST
out("== G0 SELFTEST. THE PARSER AND THE MATCHER ARE DRIVEN GREEN AND")
out("   RED ON SYNTHETIC SOURCES BEFORE ANY REPOSITORY BYTE IS READ.")
out("   AN EMPTY RESULT FROM A BLIND PARSER READS AS A DISCOVERY.")

POS_SRC = (
    "import aevolver\n"
    "from noesis_engine import thing\n"
    "import os, sys\n"
    "from . import sibling\n"
    "try:\n"
    "    import migrate\n"
    "except ImportError:\n"
    "    migrate = None\n"
    "def f():\n"
    "    import noesis_oracle\n"
    "# import not_a_real_import_in_a_comment\n"
    "S = 'import also_not_an_import'\n"
)
NEG_SRC = "x = 1\ny = 2\n"
BAD_SRC = "def broken(:\n"

pos = imports_of(POS_SRC, "<pos>")
if pos is None:
    refuse("R1_PARSER_BLIND_ON_VALID_SOURCE")
pn = sorted(set(n for (n, k, l, c) in pos if n))
out("SELFTEST_POSITIVE_NAMES " + " ".join(pn))
need = ["aevolver", "migrate", "noesis_engine", "noesis_oracle", "os", "sys"]
if pn != sorted(need):
    refuse("R1_SELFTEST_POSITIVE_MISMATCH",
           "EXPECTED " + " ".join(sorted(need)),
           "GOT      " + " ".join(pn))
out("SELFTEST_POSITIVE_MUST_MATCH_EXACTLY OK")

for bad in ["not_a_real_import_in_a_comment", "also_not_an_import"]:
    if bad in pn:
        refuse("R1_SELFTEST_COMMENT_OR_STRING_COUNTED", "NAME " + bad)
out("SELFTEST_COMMENT_AND_STRING_NOT_COUNTED OK")

rel = [1 for (n, k, l, c) in pos if k == "RELATIVE"]
if len(rel) != 1:
    refuse("R1_SELFTEST_RELATIVE_NOT_SEEN", "COUNT " + str(len(rel)))
out("SELFTEST_RELATIVE_SEEN 1")

condn = sorted(set(n for (n, k, l, c) in pos
                   if c == "CONDITIONAL" and n))
out("SELFTEST_CONDITIONAL_NAMES " + " ".join(condn))
if condn != ["migrate", "noesis_oracle"]:
    refuse("R1_SELFTEST_CONDITIONAL_MISMATCH", "GOT " + " ".join(condn))
out("SELFTEST_CONDITIONAL_LABELLED OK")

neg = names_from(NEG_SRC, "<neg>")
out("SELFTEST_NEGATIVE_MUST_BE_EMPTY " + str(len(neg)))
if neg:
    refuse("R1_SELFTEST_NEGATIVE_FIRED", "GOT " + " ".join(neg))

if imports_of(BAD_SRC, "<bad>") is not None:
    refuse("R1_SELFTEST_BROKEN_SOURCE_NOT_DETECTED")
out("SELFTEST_UNPARSEABLE_IS_DISTINGUISHED_FROM_EMPTY OK")

MSET = set(["migrate", "noesis_engine"])
for probe, want in [("migr", False), ("migrate", True),
                    ("migrate_tool", False), ("noesis", False),
                    ("noesis_engine", True)]:
    got = probe in MSET
    if got != want:
        refuse("R1_SELFTEST_MATCHER_IS_NOT_EXACT", "PROBE " + probe)
out("SELFTEST_MATCHER_IS_EXACT_NOT_SUBSTRING OK")
out("SELFTEST_ALL_GREEN")


# ------------------------------------------------ G1 REPOSITORY GUARDS
out("== G1 REPOSITORY GUARDS")
out("HOST " + str(os.uname().nodename))
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
    refuse("R1_NO_REPO_ROOT", "TRIED " + " ".join(cands))
out("REPO_ROOT " + REPO)


def git(*a):
    try:
        p = subprocess.run(["git", "-C", REPO] + list(a),
                           capture_output=True, text=True, timeout=60)
    except Exception:
        return ""
    return p.stdout.strip()


GH = git("rev-parse", "--verify", "--quiet", "HEAD")
out("GIT_HEAD [" + GH + "]")
if len(GH) != 40 or any(ch not in "0123456789abcdef" for ch in GH):
    refuse("R1_GIT_BLIND_OR_NOT_A_COMMIT_ID", "GOT [" + GH + "]")
tracked = [l for l in git("ls-files").split("\n") if l]
out("TRACKED_FILES_MUST_BE_NONZERO " + str(len(tracked)))
if not tracked:
    refuse("R1_GIT_BLIND", "tracked file count is zero")

PYP = os.path.join(REPO, "pyproject.toml")
if not os.path.isfile(PYP):
    refuse("R1_PYPROJECT_ABSENT")
raw = open(PYP, "rb").read()
out("PYPROJECT_BYTES_MUST_BE_NONZERO " + str(len(raw)))
if not raw:
    refuse("R1_PYPROJECT_EMPTY")
try:
    import tomllib
except Exception:
    refuse("R1_NO_TOML_PARSER", "python " + sys.version.split()[0])
try:
    PT = tomllib.loads(raw.decode("utf-8"))
except Exception as e:
    refuse("R1_PYPROJECT_UNPARSEABLE", str(e)[:120])
out("PYPROJECT_PARSED OK")


# --------------------------------------------- L1 THE DECLARED ORACLES
out("== L1 THE DECLARED SET. THREE ORACLES. NONE REPLACES ANOTHER.")
st = PT.get("tool", {}).get("setuptools", {})
o1 = sorted(set(st.get("py-modules", []) or []))
o1pkg = sorted(set(st.get("packages", []) or []))
out("O1_PYPROJECT_PY_MODULES_COUNT " + str(len(o1)))
out("O1_PYPROJECT_PACKAGES_COUNT " + str(len(o1pkg)))
if not o1 and not o1pkg:
    refuse("R1_DECLARED_SET_EMPTY",
           "neither py-modules nor packages is populated; the shape this",
           "body reads is not where this project declares its modules")
out("O1_PY_MODULES " + " ".join(o1))
out("O1_PACKAGES " + " ".join(o1pkg))

REL = os.path.join(REPO, "scripts", "release.py")
o2 = []
o2_state = "ABSENT"
if os.path.isfile(REL):
    rb = open(REL, "rb").read().decode("utf-8", "replace")
    t2 = None
    try:
        t2 = ast.parse(rb, filename=REL)
    except SyntaxError:
        o2_state = "UNPARSEABLE"
    if t2 is not None:
        o2_state = "PARSED"
        best = []
        for node in ast.walk(t2):
            if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
                vals = [e.value for e in node.elts
                        if isinstance(e, ast.Constant)
                        and isinstance(e.value, str)]
                if len(vals) >= 3:
                    hit = sum(1 for v in vals if v in set(o1))
                    if hit > len(best):
                        best = sorted(set(vals))
        o2 = best
out("O2_RELEASE_WHEEL_GATE_STATE " + o2_state)
out("O2_BEST_MODULE_LIKE_LITERAL_COUNT " + str(len(o2)))
out("O2_BEST_MODULE_LIKE_LITERAL " + " ".join(o2))
out("O2 IS A HEURISTIC. It picks the string literal list in that file")
out("  with the most members already declared in O1. IT IS NOT THE")
out("  WHEEL GATE BY NAME AND MUST NOT BE READ AS ONE.")

o3 = []
for e in sorted(os.listdir(REPO)):
    fp = os.path.join(REPO, e)
    if os.path.isfile(fp) and e.endswith(".py"):
        o3.append(e[:-3])
    elif os.path.isdir(fp) and os.path.isfile(os.path.join(fp,
                                                           "__init__.py")):
        o3.append(e)
o3 = sorted(set(o3))
out("O3_REPO_ROOT_IMPORTABLE_COUNT " + str(len(o3)))
out("O3_REPO_ROOT_IMPORTABLE " + " ".join(o3))

DECLARED = set(o1) | set(o1pkg)
FIRSTPARTY = set(o3)
out("DECLARED_TOTAL " + str(len(DECLARED)))
out("IN_TREE_NOT_DECLARED_COUNT " + str(len(FIRSTPARTY - DECLARED)))
out("IN_TREE_NOT_DECLARED " + " ".join(sorted(FIRSTPARTY - DECLARED)))
out("DECLARED_NOT_IN_TREE_COUNT " + str(len(DECLARED - FIRSTPARTY)))
out("DECLARED_NOT_IN_TREE " + " ".join(sorted(DECLARED - FIRSTPARTY)))

NEGNAME = "aevolverQQ_that_must_not_exist"
out("NEGATIVE_CONTROL_MUST_BE_ZERO " +
    str(int(NEGNAME in FIRSTPARTY or NEGNAME in DECLARED)))
if NEGNAME in FIRSTPARTY or NEGNAME in DECLARED:
    refuse("R1_NEGATIVE_CONTROL_FIRED")


# ---------------------------------------- L2 THE PREMISE, RE-MEASURED
out("== L2 THE INHERITED PREMISE, RE-MEASURED. R24.")
out("   THE BOARD SAYS TWO SHIPPED MODULES IMPORT FOUR THAT DO NOT")
out("   SHIP. THAT IS INHERITED. THIS LEG MEASURES IT.")


def srcpath(mod):
    a = os.path.join(REPO, mod + ".py")
    if os.path.isfile(a):
        return a
    b = os.path.join(REPO, mod, "__init__.py")
    if os.path.isfile(b):
        return b
    return None


TARGET_SET = set(TARGETS)
importers = {}
scanned = 0
unparseable = []
for mod in sorted(DECLARED | FIRSTPARTY):
    sp = srcpath(mod)
    if not sp:
        continue
    scanned += 1
    ns = names_from(open(sp, "rb").read().decode("utf-8", "replace"), sp)
    if ns is None:
        unparseable.append(mod)
        continue
    for t in TARGET_SET:
        if t in ns:
            importers.setdefault(t, []).append(mod)
out("MODULES_SCANNED_FOR_THE_PREMISE " + str(scanned))
out("UNPARSEABLE_MODULES " + str(len(unparseable)) + " " +
    " ".join(unparseable))
for t in TARGETS:
    who = sorted(set(importers.get(t, [])))
    st2 = "DECLARED" if t in DECLARED else "NOT_DECLARED"
    ex = "IN_TREE" if t in FIRSTPARTY else "NOT_IN_TREE"
    out("TARGET " + t + "  " + st2 + "  " + ex +
        "  IMPORTED_BY " + (" ".join(who) if who else "NOBODY"))
allimp = sorted(set(m for v in importers.values() for m in v))
out("DISTINCT_IMPORTERS_OF_THE_FOUR " + str(len(allimp)) + " " +
    " ".join(allimp))
present = [t for t in TARGETS if srcpath(t)]
out("TARGETS_PRESENT_IN_TREE " + str(len(present)) + " " +
    " ".join(present))
if not present:
    refuse("R1_NO_TARGET_FOUND",
           "none of the four named modules exists in this tree; the",
           "inherited premise names a set this repository does not hold")


# ------------------------------------------------- L3 THE CLOSURE
out("== L3 THE CLOSURE. WHAT THE FOUR THEMSELVES IMPORT.")
out("   FIVE CLASSES. AN IMPORT NAME IS NOT A DISTRIBUTION NAME AND")
out("   THIS BODY REFUSES TO GUESS THAT MAPPING. EXTERNAL_OR_UNKNOWN")
out("   IS PRINTED WHOLE, NEVER SUMMARISED, SO NOTHING HIDES IN IT.")
STD = set(getattr(sys, "stdlib_module_names", set()))
out("STDLIB_SET_SIZE_ON_THIS_INTERPRETER " + str(len(STD)))
if not STD:
    refuse("R1_STDLIB_SET_BLIND")


def classify(n):
    if n in STD:
        return "STDLIB"
    if n in DECLARED:
        return "FIRST_PARTY_DECLARED"
    if n in FIRSTPARTY:
        return "FIRST_PARTY_UNDECLARED"
    return "EXTERNAL_OR_UNKNOWN"


def walk(bound):
    seen = set()
    frontier = [(t, 0) for t in present]
    edges = []
    undeclared = set()
    external = set()
    truncated = False
    while frontier:
        mod, depth = frontier.pop(0)
        if mod in seen:
            continue
        seen.add(mod)
        if depth >= bound:
            truncated = True
            continue
        sp = srcpath(mod)
        if not sp:
            continue
        rows = imports_of(open(sp, "rb").read().decode("utf-8", "replace"),
                          sp)
        if rows is None:
            edges.append((mod, "UNPARSEABLE", "", 0, ""))
            continue
        for (n, k, ln, c) in rows:
            if n is None:
                edges.append((mod, "(relative)", "RELATIVE", ln, c))
                continue
            cl = classify(n)
            edges.append((mod, n, cl, ln, c))
            if cl == "FIRST_PARTY_UNDECLARED":
                undeclared.add(n)
                if n not in seen:
                    frontier.append((n, depth + 1))
            elif cl == "EXTERNAL_OR_UNKNOWN":
                external.add(n)
    return seen, edges, undeclared, external, truncated


s_lo, e_lo, u_lo, x_lo, tr_lo = walk(DEPTH_LOW)
s_hi, e_hi, u_hi, x_hi, tr_hi = walk(DEPTH_HIGH)
out("DEPTH_BOUND_LOW " + str(DEPTH_LOW) + " REACHED_MODULES " +
    str(len(s_lo)) + " UNDECLARED " + str(len(u_lo)) +
    " TRUNCATED " + str(tr_lo))
out("DEPTH_BOUND_HIGH " + str(DEPTH_HIGH) + " REACHED_MODULES " +
    str(len(s_hi)) + " UNDECLARED " + str(len(u_hi)) +
    " TRUNCATED " + str(tr_hi))
if len(s_lo) != len(s_hi) or u_lo != u_hi:
    out("BOUND_WAS_TRUNCATING the low bound did not reach the fixpoint")
else:
    out("BOUND_CLEARS both bounds agree; a bound the data clears")

out("-- EVERY EDGE AT THE HIGH BOUND, GROUPED BY SOURCE MODULE --")
bysrc = {}
for (m, n, cl, ln, c) in e_hi:
    bysrc.setdefault(m, []).append((n, cl, ln, c))
for m in sorted(bysrc):
    rows = sorted(set(bysrc[m]))
    out("  MODULE " + m + "  EDGES " + str(len(rows)))
    for (n, cl, ln, c) in rows:
        out("    " + str(ln).rjust(5) + "  " + cl.ljust(22) + c.ljust(12) +
            n)

out("-- THE CLOSURE, WHICH IS THE OBJECT --")
out("FIRST_PARTY_UNDECLARED_IN_CLOSURE_COUNT " + str(len(u_hi)))
out("FIRST_PARTY_UNDECLARED_IN_CLOSURE " + " ".join(sorted(u_hi)))
newly = sorted(u_hi - TARGET_SET)
out("BEYOND_THE_FOUR_NAMED_COUNT " + str(len(newly)))
out("BEYOND_THE_FOUR_NAMED " + " ".join(newly))
out("EXTERNAL_OR_UNKNOWN_COUNT " + str(len(x_hi)))
out("EXTERNAL_OR_UNKNOWN " + " ".join(sorted(x_hi)))
cond_rows = sorted(set((m, n) for (m, n, cl, ln, c) in e_hi
                       if c == "CONDITIONAL"
                       and cl == "FIRST_PARTY_UNDECLARED"))
out("UNDECLARED_IMPORTED_ONLY_UNDER_A_CONDITION_COUNT " +
    str(len(cond_rows)))
for (m, n) in cond_rows:
    out("  " + m + " -> " + n)

out("== L4 WHAT THIS RUN CANNOT SAY")
out("It cannot say what the PUBLISHED wheel contains. It read a working")
out("  tree at one commit. The defect lives on an artifact on an index.")
out("It cannot say an EXTERNAL_OR_UNKNOWN name is undeclared. An import")
out("  name is not a distribution name and the mapping was refused.")
out("It cannot say a name built at runtime is absent. importlib, a")
out("  dunder import, and a name assembled from a variable are all")
out("  invisible to a syntax tree, and none appears in these counts.")
out("It cannot say the stdlib set it used is the consumer's stdlib set.")
out("  It is this interpreter's.")
out("It cannot say the remedy. It computes what the remedy must cover.")
out("== END")
