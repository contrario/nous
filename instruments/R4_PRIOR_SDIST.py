#!/usr/bin/env python3
# R4 THE PRIOR VERSION'S PUBLISHED SOURCE DISTRIBUTION.
#
#   IT WRITES: nothing, anywhere. No file, no directory, no temporary
#     path, no extraction. Archives are held in memory only.
#   IT SENDS: up to two HTTPS GET requests. One to pypi.org for the
#     5.77.0 version metadata and one to the file host that metadata
#     names, for the sdist. Request line and a User-Agent. No
#     credential, no token, no cookie, no query string, no body.
#   IT NEVER: builds, installs, runs pip, executes any downloaded
#     byte, imports a project module, touches an egg-info, yanks,
#     uploads, writes a repository, or reads a key.
#   IT DOES NOT FETCH 5.78.0 AND DOES NOT FETCH ANY WHEEL.
# T5 SELF CHECK RUNS BEFORE ANY NETWORK CALL AND BEFORE ANY chdir.
#
#   python3 FILE DIGEST SELFTEST
#   python3 FILE DIGEST HOST [REPO_ROOT]

import hashlib
import io
import itertools
import json
import os
import subprocess
import sys
import tarfile
import urllib.request

ABSENT = object()
PROJECT = "nous-lang"
PRIOR = "5.77.0"
SOURCES_TAIL = "SOURCES.txt"
META_LIMIT = 8 * 1024 * 1024
MAX_BYTES = 200 * 1024 * 1024
TIMEOUT = 60
UA = "nous-r4"
WATCHED = ("fullstack_builders.nous", "noesis_integration_test.nous",
           "noesis_phase9_test.nous")


def cmp_whole(a, b):
    i = -1
    for i, (x, y) in enumerate(itertools.zip_longest(a, b, fillvalue=ABSENT)):
        if x is not y and x != y:
            return ("RED", i)
    return ("GREEN", i + 1)


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def strip_root(name, root):
    if name == root or name == root + "/":
        return None
    pre = root + "/"
    if not name.startswith(pre):
        return None
    return name[len(pre):]


def top_of(rel):
    rel = rel.rstrip("/")
    if not rel:
        return None
    if "/" not in rel:
        return ("FILE", rel)
    return ("DIR", rel.split("/")[0])


def tally(rels):
    counts = {}
    for r in rels:
        t = top_of(r)
        if t is None:
            continue
        counts[t] = counts.get(t, 0) + 1
    return counts


def is_traversal(name):
    if not name:
        return False
    if name.startswith("/"):
        return True
    return ".." in name.replace("\\", "/").split("/")


def pick_one(files, packagetype):
    hits = [f for f in files if f.get("packagetype") == packagetype]
    return (hits[0] if hits else None, len(hits))


def git(root, *a):
    try:
        p = subprocess.run(("git", "-C", root) + a, capture_output=True,
                           text=True, timeout=600)
        return p.returncode, p.stdout, p.stderr
    except Exception as exc:
        return 99, "", str(exc)


def get(url, limit):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError("R4_RESPONSE_OVER_LIMIT " + url)
    return data


def read_archive(blob, declared_sha, p):
    got = sha_bytes(blob)
    p("  BYTES %d" % len(blob))
    p("  SHA256_COMPUTED %s" % got)
    p("  SHA256_DECLARED %s" % (declared_sha or "none given"))
    if declared_sha:
        v = cmp_whole(declared_sha, got)
        p("  DIGEST_MATCHES_DECLARED %s %s" % (v[0], v))
        if v[0] != "GREEN":
            p("  REFUSE_LEG R4_ARCHIVE_DIGEST_MISMATCH")
            return None
    try:
        tf = tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz")
        names = tf.getnames()
        files = [m.name for m in tf.getmembers() if m.isfile()]
    except Exception as exc:
        p("  REFUSE_LEG R4_TAR_UNREADABLE %s" % exc)
        return None
    p("  MEMBERS_TOTAL %d" % len(names))
    p("  MEMBERS_REGULAR_FILES %d" % len(files))
    trav = [n for n in names if is_traversal(n)]
    p("  TRAVERSAL_MEMBERS_MUST_BE_0 %d %s" % (len(trav), trav[:6]))
    if trav:
        p("  REFUSE_LEG R4_TRAVERSAL_MEMBER")
        return None
    roots = sorted(set(n.split("/")[0] for n in names))
    p("  ARCHIVE_ROOTS %d %s" % (len(roots), roots))
    rels_all = []
    rels_files = []
    for r in roots:
        rels_all.extend([x for x in (strip_root(n, r) for n in names) if x])
        rels_files.extend([x for x in (strip_root(n, r) for n in files) if x])
    counts = tally(rels_all)
    dirs = sorted([(k[1], v) for k, v in counts.items() if k[0] == "DIR"])
    p("  TOP_LEVEL_DIRECTORIES %d" % len(dirs))
    for n, c in dirs:
        p("    DIR  %-38s %6d members" % (n, c))
    p("  FILES_AT_THE_ROOT %d"
      % len([1 for k in counts if k[0] == "FILE"]))
    p("  TALLY_SUMS_TO %d MUST_EQUAL_RELS %d  %s"
      % (sum(counts.values()), len(rels_all),
         sum(counts.values()) == len(rels_all)))
    p("  ENUMERATOR_NEGATIVE_zzq %d MUST_BE_0"
      % counts.get(("DIR", "zzq_absent"), 0))
    cand = [n for n in names if n.rstrip("/").endswith("/" + SOURCES_TAIL)]
    p("  SOURCES_MEMBERS_FOUND %d %s" % (len(cand), cand))
    raw = None
    if cand:
        fh = tf.extractfile(cand[0])
        raw = fh.read() if fh else b""
        p("  SOURCES_BYTES %d SHA %s" % (len(raw), sha_bytes(raw)))
    else:
        p("  SOURCES_ABSENT_FROM_THE_ARCHIVE")
    return (rels_files, raw)


def entries_of(raw):
    if raw is None:
        return []
    return [x for x in raw.decode("utf-8", "replace").split("\n") if x.strip()]


SELF = sys.argv[0]
if not os.path.isfile(SELF):
    print("REFUSE T5_NOT_A_FILE")
    sys.exit(9)
if len(sys.argv) < 2 or not sys.argv[1]:
    print("REFUSE T5_NO_DIGEST_ARGUMENT")
    print("USAGE python3 FILE DIGEST SELFTEST")
    print("USAGE python3 FILE DIGEST HOST [REPO_ROOT]")
    sys.exit(9)
with open(SELF, "rb") as fh:
    T5C = sha_bytes(fh.read())
if cmp_whole(T5C, sys.argv[1])[0] != "GREEN":
    print("REFUSE T5_DIGEST_MISMATCH")
    print("COMPUTED %s" % T5C)
    print("GIVEN    %s" % sys.argv[1])
    sys.exit(9)
print("T5_OK %s" % T5C)

if len(sys.argv) < 3:
    print("REFUSE R4_NO_MODE the mode is required and is never defaulted")
    sys.exit(9)
MODE = sys.argv[2]
if MODE not in ("SELFTEST", "HOST"):
    print("REFUSE R4_UNKNOWN_MODE [%s]" % MODE)
    sys.exit(9)
if len(sys.argv) > 4:
    print("REFUSE R4_TOO_MANY_ARGUMENTS %d" % (len(sys.argv) - 1))
    sys.exit(9)


def host_legs(repo):
    def p(*a):
        print(*a)

    p("== L0 SET, SHAPE, BLINDNESS. DECLARED BEFORE ANY VALUE.")
    p("SET: the member names of the sdist the index serves for %s,"
      % PRIOR)
    p("  the same for the archive of that version in dist/ if one is")
    p("  there, and the path field of git rev-list --objects --all.")
    p("SHAPE: only REGULAR FILE members enter a set compared against")
    p("  git. A directory member is not a path git tracks.")
    p("THE REPOSITORY MAY BE SHALLOW AND THE PRECEDING BODY DID NOT")
    p("  SAY SO. A grafted history truncates rev-list, so a path")
    p("  reported as in no reachable commit may live in a commit this")
    p("  clone does not have. THE SHALLOW STATE IS PRINTED BELOW AND")
    p("  BOUNDS EVERY NO_COMMIT VALUE IN THIS RUN.")
    p("BLIND TO: why a path is in an archive. It reads lists.")
    p("THIS BODY MEASURES. IT PROPOSES NO REMEDY AND BUILDS NOTHING.")

    p("")
    p("== L1 IDENTITY AND GUARDS")
    p("HOSTNAME %s" % os.uname().nodename)
    p("DATE_UTC %s" % subprocess.run(("date", "-u"), capture_output=True,
                                     text=True).stdout.strip())
    p("REPO_ROOT %s" % repo)
    code, out, _ = git(repo, "rev-parse", "--verify", "--quiet", "HEAD")
    gh = out.strip()
    p("GIT_HEAD [%s]" % gh)
    if len(gh) != 40:
        p("REFUSE R4_GIT_HEAD_NOT_A_COMMIT_ID")
        return 9
    code, out, _ = git(repo, "rev-parse", "--is-shallow-repository")
    shallow = out.strip()
    p("IS_SHALLOW_REPOSITORY %s" % shallow)
    code, out, _ = git(repo, "rev-list", "--objects", "--all")
    ever = set()
    for line in out.split("\n"):
        if " " in line:
            ever.add(line.split(" ", 1)[1])
    p("PATHS_EVER_REACHABLE_MUST_BE_NONZERO %d" % len(ever))
    p("NEGATIVE_zzq %d MUST_BE_0" % len({"zzq_absent_path"} & ever))
    if not ever:
        p("REFUSE R4_REVLIST_BLIND")
        return 9
    if shallow == "true":
        p("THE VALUE ABOVE IS A LOWER BOUND. THIS CLONE IS GRAFTED.")

    p("")
    p("== L2 THE INDEX. METADATA FOR %s ONLY." % PRIOR)
    try:
        meta = json.loads(get("https://pypi.org/pypi/" + PROJECT + "/" +
                              PRIOR + "/json", META_LIMIT).decode("utf-8"))
    except Exception as exc:
        p("REFUSE R4_VERSION_METADATA_UNREACHABLE %s" % str(exc)[:160])
        return 9
    info = meta.get("info", {})
    p("RELEASE %s YANKED %s REASON %s"
      % (PRIOR, info.get("yanked", "unknown"),
         (info.get("yanked_reason") or "none")))
    sd, n = pick_one(meta.get("urls", []), "sdist")
    p("SDIST_COUNT %d" % n)
    if sd is None:
        p("REFUSE R4_NO_SDIST_PUBLISHED")
        return 9
    dsha = sd.get("digests", {}).get("sha256", "")
    p("PUBLISHED_FILENAME %s" % sd.get("filename", ""))
    p("PUBLISHED_BYTES %s" % sd.get("size", ""))
    p("PUBLISHED_SHA256 %s" % dsha)
    p("PUBLISHED_YANKED %s" % sd.get("yanked", ""))
    if not dsha:
        p("REFUSE R4_INDEX_PUBLISHES_NO_DIGEST")
        return 9
    if (sd.get("size", 0) or 0) > MAX_BYTES:
        p("REFUSE R4_SDIST_OVER_LIMIT")
        return 9

    p("")
    p("== L3 THE PUBLISHED ARCHIVE, IN MEMORY.")
    try:
        blob = get(sd["url"], MAX_BYTES)
    except Exception as exc:
        p("REFUSE R4_SDIST_UNREACHABLE %s" % str(exc)[:160])
        return 9
    r = read_archive(blob, dsha, p)
    if r is None:
        p("REFUSE R4_PUBLISHED_LEG_FAILED")
        return 9
    pub_files, pub_raw = r
    pub = set(pub_files)

    p("")
    p("== L4 THE QUESTION THIS BODY EXISTS FOR.")
    p("   DID THE PUBLISHED %s CARRY THE THREE IGNORED FILES." % PRIOR)
    for w in WATCHED:
        p("  WATCHED %-34s IN_PUBLISHED %s" % (w, w in pub))
    p("  WATCHED_PRESENT_COUNT %d of %d"
      % (len([w for w in WATCHED if w in pub]), len(WATCHED)))
    p("  WATCHED_NEGATIVE_zzq %s MUST_BE_False"
      % ("zzq_absent_file.nous" in pub))
    never = sorted(pub - ever)
    p("  PUBLISHED_PATHS_IN_NO_REACHABLE_COMMIT %d" % len(never))
    for x in never:
        p("    NO_COMMIT %s" % x)
    if shallow == "true":
        p("  BOUNDED BY THE GRAFT. SEE L0.")

    p("")
    p("== L5 THE PUBLISHED ARCHIVE AGAINST THE ONE IN dist/.")
    dd = os.path.join(repo, "dist")
    loc = None
    if not os.path.isdir(dd):
        p("NO_DIST_DIRECTORY %s" % dd)
    else:
        cands = [os.path.join(dd, x) for x in sorted(os.listdir(dd))
                 if x.endswith(".tar.gz") and PRIOR in x
                 and os.path.isfile(os.path.join(dd, x))]
        p("LOCAL_CANDIDATES %d %s"
          % (len(cands), [os.path.basename(c) for c in cands]))
        if len(cands) == 1:
            with open(cands[0], "rb") as fh:
                loc = fh.read()
            p("LOCAL_PATH %s" % cands[0])
            p("LOCAL_BYTES %d" % len(loc))
            p("LOCAL_SHA256 %s" % sha_bytes(loc))
            p("BYTE_IDENTICAL %s" % cmp_whole(dsha, sha_bytes(loc))[0])
    if loc is not None:
        p("LOCAL ARCHIVE")
        rl = read_archive(loc, None, p)
        if rl is not None:
            loc_files, loc_raw = rl
            lset = set(loc_files)
            p("  LOCAL_ONLY %d" % len(lset - pub))
            for x in sorted(lset - pub):
                p("    ONLY_LOCAL %s" % x)
            p("  PUBLISHED_ONLY %d" % len(pub - lset))
            for x in sorted(pub - lset):
                p("    ONLY_PUBLISHED %s" % x)
            pe, le = entries_of(pub_raw), entries_of(loc_raw)
            p("  PUBLISHED_SOURCES_ENTRIES %d" % len(pe))
            p("  LOCAL_SOURCES_ENTRIES %d" % len(le))
            p("  SOURCES_IDENTICAL %s"
              % cmp_whole(sha_bytes(pub_raw or b""),
                          sha_bytes(loc_raw or b""))[0])
            p("  PUB_MINUS_LOCAL %d %s"
              % (len(set(pe) - set(le)), sorted(set(pe) - set(le))[:20]))
            p("  LOCAL_MINUS_PUB %d %s"
              % (len(set(le) - set(pe)), sorted(set(le) - set(pe))[:20]))

    p("")
    p("== L6 WHAT THIS RUN CANNOT SAY")
    p("It cannot say why a file is in an archive. It read lists.")
    p("It cannot say a NO_COMMIT path was never committed. This clone")
    p("  may be grafted; see IS_SHALLOW_REPOSITORY above.")
    p("It cannot say the index will serve these bytes tomorrow.")
    p("It cannot say a remedy. It measured.")
    p("IT WROTE NOTHING AND EXTRACTED NOTHING.")
    p("== END")
    return 0


def selftest():
    print("== SELFTEST. IN MEMORY. ZERO FILESYSTEM WRITES, NO TEMPDIR.")
    fails = []

    def arm(tag, got, want):
        ok = got == want
        print("  %-50s got %-14s want %-14s %s"
              % (tag, repr(got)[:14], repr(want)[:14],
                 "OK" if ok else "ARM_FAILED"))
        if not ok:
            fails.append(tag)

    d = "a" * 64
    arm("E1 exact", cmp_whole(d, d)[0], "GREEN")
    arm("E1 truncated", cmp_whole(d, d[:-1]), ("RED", 63))
    arm("E1 overlong prefix", cmp_whole(d, d + "b"), ("RED", 64))
    arm("E2 strip_root one component",
        strip_root("r/tests/a.py", "r"), "tests/a.py")
    arm("E2 strip_root root itself", strip_root("r", "r"), None)
    arm("E2 strip_root foreign root", strip_root("o/x", "r"), None)
    arm("E2 strip_root not a string prefix", strip_root("rr/x", "r"), None)
    arm("E3 top_of nested", top_of("tests/a.py"), ("DIR", "tests"))
    arm("E3 top_of root file", top_of("PKG-INFO"), ("FILE", "PKG-INFO"))
    arm("E3 top_of bare dir", top_of("tests/"), ("FILE", "tests"))
    arm("E4 tally buckets", len(tally(["a/x", "a/y", "b/z", "R"])), 3)
    arm("E4 tally sums", sum(tally(["a/x", "a/y", "b/z", "R"]).values()), 4)
    arm("E5 traversal absolute", is_traversal("/etc/x"), True)
    arm("E5 traversal dotdot", is_traversal("r/../x"), True)
    arm("E5 traversal negative", is_traversal("r/a.py"), False)
    arm("E5 traversal dotted name", is_traversal("r/..h/a.py"), False)
    F = [{"packagetype": "sdist", "filename": "s.tar.gz"},
         {"packagetype": "bdist_wheel", "filename": "w.whl"}]
    arm("E6 pick_one by field", pick_one(F, "sdist")[0]["filename"],
        "s.tar.gz")
    arm("E6 pick_one absent", pick_one(F, "zzq"), (None, 0))

    def mktar(entries, root="zzsyn-1.0", dirs=()):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            for dn in dirs:
                ti = tarfile.TarInfo(root + "/" + dn)
                ti.type = tarfile.DIRTYPE
                tf.addfile(ti)
            for name, data in entries:
                ti = tarfile.TarInfo(root + "/" + name)
                ti.size = len(data)
                tf.addfile(ti, io.BytesIO(data))
        return buf.getvalue()

    body = mktar([("tests/f.txt", b"x"), ("docs/f.txt", b"x"),
                  ("extras/f.txt", b"x"), ("PKG-INFO", b"n\n"),
                  ("fullstack_builders.nous", b"x"),
                  ("zz.egg-info/" + SOURCES_TAIL, b"PKG-INFO\ntests/f.txt\n")],
                 dirs=("tests", "docs", "extras"))
    cap = []
    res = read_archive(body, sha_bytes(body),
                       lambda *a: cap.append(" ".join(str(x) for x in a)))
    txt = "\n".join(" ".join(l.split()) for l in cap)
    arm("E7 returns", res is not None, True)
    arm("E7 THREE DIRECTORIES SEEN NOT ONE", txt.count("DIR ") >= 3, True)
    for tok in ("TOP_LEVEL_DIRECTORIES 4", "ARCHIVE_ROOTS 1",
                "TRAVERSAL_MEMBERS_MUST_BE_0 0", "SOURCES_MEMBERS_FOUND 1"):
        arm("E7 LEG %s" % tok[:34], tok in txt, True)
    arm("E7 negative bucket", "DIR zzq_absent " in txt, False)
    if res is not None:
        rf, rr = res
        arm("E7 directory members are not file paths", "tests" in rf, False)
        arm("E7 regular files only", len(rf), 6)
        arm("E8 WATCHED positive detected",
            WATCHED[0] in set(rf), True)
        arm("E8 WATCHED negative not detected",
            WATCHED[1] in set(rf), False)
        arm("E8 SOURCES parsed", len(entries_of(rr)), 2)

    cap2 = []
    bad = mktar([("../evil.py", b"x")])
    arm("E9 traversal refuses",
        read_archive(bad, sha_bytes(bad),
                     lambda *a: cap2.append(" ".join(str(x) for x in a))),
        None)
    arm("E9 says why", "R4_TRAVERSAL_MEMBER" in "\n".join(cap2), True)
    cap3 = []
    arm("E10 wrong digest refuses",
        read_archive(body, "b" * 64,
                     lambda *a: cap3.append(" ".join(str(x) for x in a))),
        None)
    arm("E10 says why",
        "R4_ARCHIVE_DIGEST_MISMATCH" in "\n".join(cap3), True)

    def invoke(args, want):
        r = subprocess.run([sys.executable, SELF] + args,
                           capture_output=True, text=True, timeout=180)
        ok = want in r.stdout and r.returncode == 9
        print("  %-50s rc %d %s"
              % ("REFUSE " + want, r.returncode, "OK" if ok else "ARM_FAILED"))
        if not ok:
            fails.append(want)

    invoke([T5C[:-1] + ("b" if T5C[-1] != "b" else "c"), "SELFTEST"],
           "T5_DIGEST_MISMATCH")
    invoke([T5C[:-1], "SELFTEST"], "T5_DIGEST_MISMATCH")
    invoke([T5C + "0", "SELFTEST"], "T5_DIGEST_MISMATCH")
    invoke([T5C], "R4_NO_MODE")
    invoke([T5C, "HOSTX"], "R4_UNKNOWN_MODE")
    invoke([T5C, "HOST", "/x", "EXTRA"], "R4_TOO_MANY_ARGUMENTS")

    print()
    if fails:
        print("REFUSE R4_SELFTEST_FAILED %s" % fails)
        return 9
    print("SELFTEST_ALL_GREEN")
    return 0


if MODE == "SELFTEST":
    sys.exit(selftest())

CAND = [sys.argv[3] if len(sys.argv) > 3 else "",
        "/opt/aetherlang_agents/nous", "/opt/neuroaether/nous"]
REPO = ""
for c in CAND:
    if c and os.path.isdir(os.path.join(c, ".git")):
        REPO = c
        break
if not REPO:
    print("REFUSE R4_NO_REPO_ROOT")
    print("TRIED %s" % [c for c in CAND if c])
    sys.exit(9)
sys.exit(host_legs(REPO))
