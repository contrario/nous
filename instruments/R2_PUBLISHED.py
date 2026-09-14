#!/usr/bin/env python3
# R2 THE PUBLISHED ARTIFACT, MEASURED. THE DETECTOR IS FIXED FIRST.
#
# THIS BODY IS NOT WRITE FREE AND DOES NOT CLAIM TO BE.
#   IT WRITES: nothing to any filesystem. No file, no directory, no
#     temporary path. The wheel is held in memory only.
#   IT SENDS: up to three HTTPS GET requests, to pypi.org for two
#     metadata documents and to the file host named by that metadata
#     for the wheel bytes.
#   IT NEVER: installs, resolves dependencies, runs pip, executes any
#     downloaded byte, imports any project module, touches a service,
#     writes a repository, or reads a key.
# T5 SELF CHECK RUNS BEFORE ANY NETWORK CALL AND BEFORE ANY chdir.

import ast
import hashlib
import io
import json
import os
import subprocess
import sys
import urllib.request
import zipfile

PROJECT = "nous-lang"
PIN_VERSION = "5.78.0"
MAX_WHEEL_BYTES = 200 * 1024 * 1024
TIMEOUT = 60


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


# --------------------------------------------------- THE FIXED DETECTOR
CATCHES = ("ImportError", "ModuleNotFoundError", "Exception",
           "BaseException")


def _catches_import(handler):
    t = handler.type
    if t is None:
        return True
    names = []
    if isinstance(t, ast.Name):
        names = [t.id]
    elif isinstance(t, ast.Tuple):
        names = [e.id for e in t.elts if isinstance(e, ast.Name)]
    elif isinstance(t, ast.Attribute):
        names = [t.attr]
    return any(n in CATCHES for n in names)


def _weaker(a, b):
    order = {"UNCONDITIONAL": 0, "GUARDED": 1, "DEFERRED": 2}
    return a if order[a] >= order[b] else b


def scan_module(src, path):
    """Return list of (name, label, importerror_guarded, lineno) or None
    on parse failure. name is the TOP LEVEL module name; a relative
    import yields name None."""
    try:
        tree = ast.parse(src, filename=path)
    except SyntaxError:
        return None
    acc = []

    def emit(node, label, ieg):
        if isinstance(node, ast.Import):
            for a in node.names:
                acc.append((a.name.split(".")[0], label, ieg, node.lineno))
        else:
            if node.level and node.level > 0:
                acc.append((None, label, ieg, node.lineno))
            elif node.module:
                acc.append((node.module.split(".")[0], label, ieg,
                            node.lineno))

    def body(stmts, label, ieg):
        for st in stmts:
            stmt(st, label, ieg)

    def stmt(st, label, ieg):
        if isinstance(st, (ast.Import, ast.ImportFrom)):
            emit(st, label, ieg)
        elif isinstance(st, ast.Try) or (
                hasattr(ast, "TryStar") and isinstance(st, ast.TryStar)):
            caught = any(_catches_import(h) for h in st.handlers)
            body(st.body, _weaker(label, "GUARDED"), ieg or caught)
            for h in st.handlers:
                body(h.body, _weaker(label, "GUARDED"), ieg or caught)
            body(st.orelse, _weaker(label, "GUARDED"), ieg or caught)
            body(st.finalbody, label, ieg)
        elif isinstance(st, ast.If):
            body(st.body, _weaker(label, "GUARDED"), ieg)
            body(st.orelse, _weaker(label, "GUARDED"), ieg)
        elif isinstance(st, (ast.For, ast.AsyncFor, ast.While)):
            body(st.body, _weaker(label, "GUARDED"), ieg)
            body(st.orelse, _weaker(label, "GUARDED"), ieg)
        elif isinstance(st, (ast.With, ast.AsyncWith)):
            body(st.body, label, ieg)
        elif isinstance(st, ast.ClassDef):
            body(st.body, label, ieg)
        elif isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body(st.body, "DEFERRED", ieg)
        elif hasattr(ast, "Match") and isinstance(st, ast.Match):
            for c in st.cases:
                body(c.body, _weaker(label, "GUARDED"), ieg)
    body(tree.body, "UNCONDITIONAL", False)
    return acc


# ------------------------------------------------ G0 DETECTOR SELFTEST
out("== G0 THE DETECTOR IS DRIVEN ON EVERY CONSTRUCT BEFORE ANY")
out("   NETWORK CALL. THE PRECEDING BODY LABELLED AN except HANDLER")
out("   UNCONDITIONAL, WHICH IS THE ONE SHAPE THAT DISTINGUISHES A")
out("   CRASH FROM A DEGRADATION. THAT DEFECT IS THE REASON FOR THIS.")

SRC = (
    "import m_top\n"
    "with open('x') as f:\n"
    "    import m_with\n"
    "class C:\n"
    "    import m_class\n"
    "try:\n"
    "    import m_try_body\n"
    "except ImportError:\n"
    "    import m_try_handler\n"
    "else:\n"
    "    import m_try_else\n"
    "finally:\n"
    "    import m_try_finally\n"
    "try:\n"
    "    import m_try_valueerror\n"
    "except ValueError:\n"
    "    pass\n"
    "if X:\n"
    "    import m_if\n"
    "else:\n"
    "    import m_ifelse\n"
    "for i in y:\n"
    "    import m_for\n"
    "while z:\n"
    "    import m_while\n"
    "def g():\n"
    "    import m_func\n"
    "    try:\n"
    "        import m_func_try\n"
    "    except ImportError:\n"
    "        pass\n"
    "class D:\n"
    "    def h(self):\n"
    "        import m_method\n"
    "from . import m_rel\n"
)

EXPECT = {
    "m_top": ("UNCONDITIONAL", False),
    "m_with": ("UNCONDITIONAL", False),
    "m_class": ("UNCONDITIONAL", False),
    "m_try_body": ("GUARDED", True),
    "m_try_handler": ("GUARDED", True),
    "m_try_else": ("GUARDED", True),
    "m_try_finally": ("UNCONDITIONAL", False),
    "m_try_valueerror": ("GUARDED", False),
    "m_if": ("GUARDED", False),
    "m_ifelse": ("GUARDED", False),
    "m_for": ("GUARDED", False),
    "m_while": ("GUARDED", False),
    "m_func": ("DEFERRED", False),
    "m_func_try": ("DEFERRED", True),
    "m_method": ("DEFERRED", False),
}

rows = scan_module(SRC, "<selftest>")
if rows is None:
    refuse("R2_DETECTOR_BLIND_ON_VALID_SOURCE")
got = {}
rel = 0
for (n, lab, ieg, ln) in rows:
    if n is None:
        rel += 1
    else:
        got[n] = (lab, ieg)
bad = []
for k in sorted(set(list(EXPECT.keys()) + list(got.keys()))):
    e = EXPECT.get(k)
    g = got.get(k)
    mark = "OK " if e == g else "BAD"
    if e != g:
        bad.append(k)
    out("  %s %-20s EXPECT %-30s GOT %s" % (mark, k, str(e), str(g)))
out("  RELATIVE_IMPORTS_SEEN " + str(rel))
if rel != 1:
    refuse("R2_SELFTEST_RELATIVE", "COUNT " + str(rel))
if bad:
    refuse("R2_SELFTEST_LABEL_MISMATCH", "NAMES " + " ".join(bad))
if scan_module("def broken(:\n", "<bad>") is not None:
    refuse("R2_SELFTEST_UNPARSEABLE_NOT_DETECTED")
if scan_module("x = 1\n# import nope\ns = 'import nope2'\n", "<neg>") != []:
    refuse("R2_SELFTEST_NEGATIVE_FIRED")
out("  UNPARSEABLE_DISTINGUISHED_FROM_EMPTY OK")
out("  NEGATIVE_MUST_BE_EMPTY OK")
out("SELFTEST_ALL_GREEN fifteen constructs, three labels, one flag")

STD = set(getattr(sys, "stdlib_module_names", set()))
out("STDLIB_SET_SIZE " + str(len(STD)))
if not STD:
    refuse("R2_STDLIB_SET_BLIND")
out("PYTHON " + sys.version.split()[0])


# ------------------------------------------------- G1 OPTIONAL REPO
REPO = ""
cands = []
if len(sys.argv) > 2 and sys.argv[2]:
    cands.append(sys.argv[2])
cands += ["/opt/aetherlang_agents/nous", "/opt/neuroaether/nous"]
for d in cands:
    if os.path.isdir(os.path.join(d, ".git")):
        REPO = d
        break
TREE = set()
if REPO:
    p = subprocess.run(["git", "-C", REPO, "rev-parse", "--verify",
                        "--quiet", "HEAD"], capture_output=True, text=True)
    gh = p.stdout.strip()
    out("REPO_ROOT " + REPO)
    out("GIT_HEAD [" + gh + "]")
    if len(gh) != 40:
        refuse("R2_GIT_BLIND_OR_NOT_A_COMMIT_ID", "GOT [" + gh + "]")
    for e in sorted(os.listdir(REPO)):
        fp = os.path.join(REPO, e)
        if os.path.isfile(fp) and e.endswith(".py"):
            TREE.add(e[:-3])
        elif os.path.isdir(fp) and os.path.isfile(
                os.path.join(fp, "__init__.py")):
            TREE.add(e)
    out("REPO_ROOT_IMPORTABLE_MUST_BE_NONZERO " + str(len(TREE)))
    if not TREE:
        refuse("R2_TREE_BLIND")
else:
    out("REPO_ROOT ABSENT the first-party cross reference is unavailable")
    out("  and every NOT_PROVIDED name will be reported without it")


# ------------------------------------------------------- L1 METADATA
out("== L1 THE INDEX. TWO ORACLES ON WHICH VERSION IS CURRENT.")


def get(url, limit):
    req = urllib.request.Request(url, headers={"User-Agent": "nous-r2"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        refuse("R2_RESPONSE_OVER_LIMIT", url)
    return data


try:
    proj = json.loads(get("https://pypi.org/pypi/" + PROJECT + "/json",
                          8 * 1024 * 1024).decode("utf-8"))
except Exception as e:
    refuse("R2_INDEX_UNREACHABLE",
           "an unreachable index returns nothing and nothing reads as a",
           "clean package; this refuses instead", str(e)[:160])
latest = proj.get("info", {}).get("version", "")
out("INDEX_LATEST_VERSION " + latest)
out("BODY_PINNED_VERSION " + PIN_VERSION)
if latest != PIN_VERSION:
    out("VERSION_ORACLES_DISAGREE the index has moved past the pin;")
    out("  THIS RUN MEASURES THE PIN, NOT THE LATEST")
else:
    out("VERSION_ORACLES_AGREE YES")

try:
    ver = json.loads(get("https://pypi.org/pypi/" + PROJECT + "/" +
                         PIN_VERSION + "/json",
                         8 * 1024 * 1024).decode("utf-8"))
except Exception as e:
    refuse("R2_VERSION_METADATA_UNREACHABLE", str(e)[:160])

wheels = [u for u in ver.get("urls", [])
          if u.get("packagetype") == "bdist_wheel"]
out("WHEELS_PUBLISHED_FOR_THE_PIN " + str(len(wheels)))
for w in wheels:
    out("  " + w.get("filename", "") + "  " + str(w.get("size", "")) +
        " bytes  sha256 " + w.get("digests", {}).get("sha256", "")[:16])
if not wheels:
    refuse("R2_NO_WHEEL_PUBLISHED",
           "the pinned version publishes no bdist_wheel")
W = wheels[0]
if len(wheels) > 1:
    out("MORE_THAN_ONE_WHEEL the first is measured and the rest are not")

out("== L2 THE WHEEL BYTES, IN MEMORY, VERIFIED AGAINST THE INDEX")
declared_sha = W.get("digests", {}).get("sha256", "")
declared_size = W.get("size", 0)
if not declared_sha:
    refuse("R2_INDEX_PUBLISHES_NO_DIGEST")
if declared_size and declared_size > MAX_WHEEL_BYTES:
    refuse("R2_WHEEL_OVER_LIMIT", str(declared_size))
try:
    blob = get(W["url"], MAX_WHEEL_BYTES)
except Exception as e:
    refuse("R2_WHEEL_UNREACHABLE", str(e)[:160])
got_sha = hashlib.sha256(blob).hexdigest()
out("WHEEL_FILENAME " + W.get("filename", ""))
out("WHEEL_BYTES_FETCHED " + str(len(blob)))
out("WHEEL_BYTES_DECLARED " + str(declared_size))
out("WHEEL_SHA256_COMPUTED " + got_sha)
out("WHEEL_SHA256_DECLARED " + declared_sha)
if got_sha != declared_sha:
    refuse("R2_WHEEL_DIGEST_MISMATCH")
out("WHEEL_DIGEST_MATCHES_THE_INDEX YES")

try:
    zf = zipfile.ZipFile(io.BytesIO(blob))
except Exception as e:
    refuse("R2_WHEEL_NOT_A_ZIP", str(e)[:160])
members = zf.namelist()
out("WHEEL_MEMBERS " + str(len(members)))
if not members:
    refuse("R2_WHEEL_EMPTY")
pys = [m for m in members if m.endswith(".py")]
out("WHEEL_PY_MEMBERS " + str(len(pys)))
if not pys:
    refuse("R2_WHEEL_HAS_NO_PYTHON")

meta = [m for m in members if m.endswith(".dist-info/METADATA")]
reqs = set()
if meta:
    mt = zf.read(meta[0]).decode("utf-8", "replace")
    for line in mt.split("\n"):
        if line.startswith("Requires-Dist:"):
            v = line.split(":", 1)[1].strip()
            for stop in [";", "(", "[", "<", ">", "=", "!", "~", " "]:
                v = v.split(stop)[0]
            if v:
                reqs.add(v.strip().lower().replace("_", "-").replace(".",
                                                                     "-"))
out("REQUIRES_DIST_COUNT " + str(len(reqs)))
out("REQUIRES_DIST " + " ".join(sorted(reqs)))


# --------------------------------------------- L3 WHAT THE WHEEL SHIPS
out("== L3 WHAT THE WHEEL ACTUALLY PROVIDES")
PROV = set()
for m in members:
    if m.endswith(".dist-info/") or ".dist-info/" in m:
        continue
    if ".data/" in m:
        continue
    parts = m.split("/")
    if len(parts) == 1 and m.endswith(".py"):
        PROV.add(m[:-3])
    elif len(parts) >= 2 and parts[-1] == "__init__.py":
        PROV.add(parts[0])
PROV.discard("__init__")
out("WHEEL_PROVIDES_COUNT " + str(len(PROV)))
out("WHEEL_PROVIDES " + " ".join(sorted(PROV)))
NEG = "aevolverQQ_must_not_be_provided"
out("NEGATIVE_CONTROL_MUST_BE_ZERO " + str(int(NEG in PROV)))
if NEG in PROV:
    refuse("R2_NEGATIVE_CONTROL_FIRED")
if REPO:
    out("PROVIDED_BUT_NOT_IN_TREE " +
        " ".join(sorted(PROV - TREE)) or "PROVIDED_BUT_NOT_IN_TREE none")


# ----------------------------------------------------- L4 THE SEVERITY
out("== L4 THE SEVERITY. WHAT A CLEAN INSTALL CANNOT IMPORT.")
out("   A NAME IS NOT_PROVIDED WHEN THE WHEEL DOES NOT CARRY IT, IT IS")
out("   NOT STDLIB ON THIS INTERPRETER, AND IT DOES NOT MATCH A")
out("   Requires-Dist NAME EXACTLY. AN IMPORT NAME IS NOT A")
out("   DISTRIBUTION NAME, SO THAT LAST TEST IS WEAK IN ONE DIRECTION:")
out("   IT CAN CALL A DECLARED DEPENDENCY NOT_PROVIDED. IT CANNOT HIDE")
out("   A MISSING FIRST PARTY MODULE, WHICH IS THE OBJECT.")
hard = []
soft = []
deferred = []
unparse = []
for m in sorted(pys):
    parts = m.split("/")
    if ".dist-info/" in m or ".data/" in m:
        continue
    if len(parts) == 1:
        mod = parts[0][:-3]
    else:
        mod = parts[0]
    rows = scan_module(zf.read(m).decode("utf-8", "replace"), m)
    if rows is None:
        unparse.append(m)
        continue
    for (n, lab, ieg, ln) in rows:
        if n is None or n in PROV or n in STD:
            continue
        nn = n.lower().replace("_", "-").replace(".", "-")
        if nn in reqs:
            continue
        fp = "FIRST_PARTY_IN_TREE" if (REPO and n in TREE) else "UNKNOWN"
        weak = ""
        for r in sorted(reqs):
            if nn in r or r in nn:
                weak = "  WEAK_MATCH_TO_Requires-Dist:" + r
                break
        rec = (m, ln, n, fp + weak, ieg)
        if lab == "UNCONDITIONAL":
            hard.append(rec)
        elif lab == "GUARDED":
            soft.append(rec)
        else:
            deferred.append(rec)
out("UNPARSEABLE_WHEEL_MEMBERS " + str(len(unparse)) + " " +
    " ".join(unparse))
out("")
out("HARD_UNCONDITIONAL_NOT_PROVIDED " + str(len(hard)))
for (m, ln, n, fp, ieg) in hard:
    out("  BREAKS " + m + ":" + str(ln) + "  " + n + "  " + fp)
out("")
out("GUARDED_NOT_PROVIDED " + str(len(soft)))
gi = [r for r in soft if r[4]]
gn = [r for r in soft if not r[4]]
out("  OF WHICH INSIDE A try THAT CATCHES ImportError " + str(len(gi)))
out("  OF WHICH GUARDED BY SOMETHING ELSE " + str(len(gn)))
for (m, ln, n, fp, ieg) in gn:
    out("    NOT_IMPORTERROR_GUARDED " + m + ":" + str(ln) + "  " + n +
        "  " + fp)
out("")
out("DEFERRED_NOT_PROVIDED " + str(len(deferred)))
out("  RUNS ONLY WHEN THE ENCLOSING FUNCTION IS CALLED. NEVER AT")
out("  IMPORT. EVERY ONE IS PRINTED, BECAUSE THE PRECEDING RUN")
out("  SUMMARISED THIS CLASS AND THE SUMMARY HID THE ANSWER.")
for (m, ln, n, fp, ieg) in deferred:
    out("    DEFERRED " + m + ":" + str(ln) + "  " + n + "  " + fp)
dn = sorted(set(r[2] for r in deferred))
out("  DISTINCT_NAMES " + " ".join(dn))
out("")
hm = sorted(set(r[0] for r in hard))
out("SHIPPED_MEMBERS_THAT_CANNOT_IMPORT_ON_A_CLEAN_INSTALL " + str(len(hm)))
out("  " + " ".join(hm))
hn = sorted(set(r[2] for r in hard))
out("DISTINCT_MISSING_NAMES_AT_IMPORT_TIME " + str(len(hn)))
out("  " + " ".join(hn))
hw = [r for r in hard if "WEAK_MATCH" in r[3]]
out("OF THE HARD ROWS, CARRYING A WEAK MATCH TO A DECLARED")
out("  DEPENDENCY AND THEREFORE PROBABLY NOT A BREAKAGE " + str(len(hw)))
out("OF THE HARD ROWS, WITH NO SUCH MATCH " + str(len(hard) - len(hw)))
out("THE SECOND NUMBER IS THE ONE THAT MEANS SOMETHING. THE FIRST IS")
out("  THIS BODY REFUSING TO MAP AN IMPORT NAME TO A DISTRIBUTION")
out("  NAME AND SAYING SO INSTEAD OF GUESSING.")

out("== L5 WHAT THIS RUN CANNOT SAY")
out("It cannot say the package is broken for a user. A module that")
out("  cannot be imported harms nobody who never imports it.")
out("It cannot say a NOT_PROVIDED name is truly absent at runtime. A")
out("  consumer may already have that distribution installed.")
out("It cannot say a name built at runtime is absent. importlib and a")
out("  dunder import are invisible to a syntax tree.")
out("It cannot say the sdist has the same shape. It read one wheel.")
out("It cannot say the stdlib set is the consumer's. It is this")
out("  interpreter's, on this host, at this version.")
out("== END")
