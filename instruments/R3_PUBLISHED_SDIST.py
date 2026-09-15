#!/usr/bin/env python3
# R3 THE PUBLISHED SOURCE DISTRIBUTION, MEASURED AT THE INDEX.
#
# THIS BODY IS NOT WRITE FREE IN THE NETWORK SENSE AND SAYS SO.
#   IT WRITES: nothing, anywhere. No file, no directory, no temporary
#     path, no extraction. Every archive is held in memory only. The
#     SELFTEST builds its fixtures in memory and uses no tempdir.
#   IT SENDS: up to five HTTPS GET requests. Three to pypi.org for
#     metadata documents and two to the file host that metadata names,
#     for the sdist and the wheel of the pinned version. Request line
#     and a User-Agent. No credential, no token, no cookie, no query
#     string, no body, no referrer.
#   IT NEVER: builds, rebuilds, installs, resolves, runs pip, executes
#     any downloaded byte, imports any project module, touches an
#     egg-info, yanks, uploads, writes a repository, or reads a key.
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
import zipfile

ABSENT = object()
PROJECT = "nous-lang"
PIN = "5.78.0"
PRIOR = "5.77.0"
SOURCES_TAIL = "SOURCES.txt"
META_LIMIT = 8 * 1024 * 1024
MAX_BYTES = 200 * 1024 * 1024
TIMEOUT = 60
UA = "nous-r3"


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
    """True when a member name escapes the archive root. Checked on the
    RAW member name, before any root is stripped."""
    if not name:
        return False
    if name.startswith("/"):
        return True
    parts = name.replace("\\", "/").split("/")
    return ".." in parts


def pick_one(files, packagetype):
    """Select by the packagetype FIELD, never by a filename suffix.
    Returns (entry, count_seen). The caller decides what more than one
    means; this function never silently takes the first of many."""
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
        raise ValueError("R3_RESPONSE_OVER_LIMIT " + url)
    return data


def tar_read(blob):
    """Open a gzipped tar from memory. Returns (names, files, getter) or
    raises. files is the subset that are REGULAR FILES; a directory
    member is never a path in that set."""
    tf = tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz")
    names = tf.getnames()
    files = [m.name for m in tf.getmembers() if m.isfile()]
    return tf, names, files


def refuse(tok, *lines):
    print("REFUSE " + tok)
    for l in lines:
        print(l)
    sys.exit(9)


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
    refuse("R3_NO_MODE the mode is required and is never defaulted")
MODE = sys.argv[2]
if MODE not in ("SELFTEST", "HOST"):
    refuse("R3_UNKNOWN_MODE [%s]" % MODE)
if len(sys.argv) > 4:
    refuse("R3_TOO_MANY_ARGUMENTS %d" % (len(sys.argv) - 1))


def archive_legs(tag, blob, declared_sha, p):
    """Enumerate one source archive held in memory. Returns
    (rels_files, sources_raw, roots) or None on refusal."""
    got = sha_bytes(blob)
    p("  BYTES %d" % len(blob))
    p("  SHA256_COMPUTED %s" % got)
    p("  SHA256_DECLARED %s" % (declared_sha or "none given"))
    if declared_sha:
        v = cmp_whole(declared_sha, got)
        p("  DIGEST_MATCHES_DECLARED %s %s" % (v[0], v))
        if v[0] != "GREEN":
            p("  REFUSE_LEG R3_ARCHIVE_DIGEST_MISMATCH")
            return None
    try:
        tf, names, files = tar_read(blob)
    except Exception as exc:
        p("  REFUSE_LEG R3_TAR_UNREADABLE %s" % exc)
        return None
    p("  MEMBERS_TOTAL %d" % len(names))
    p("  MEMBERS_REGULAR_FILES %d" % len(files))
    p("  MEMBERS_NOT_FILES %d" % (len(names) - len(files)))
    trav = [n for n in names if is_traversal(n)]
    p("  TRAVERSAL_MEMBERS_MUST_BE_0 %d %s" % (len(trav), trav[:6]))
    if trav:
        p("  REFUSE_LEG R3_TRAVERSAL_MEMBER")
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
    froot = sorted([k[1] for k, v in counts.items() if k[0] == "FILE"])
    p("  TOP_LEVEL_DIRECTORIES %d" % len(dirs))
    for n, c in dirs:
        p("    DIR  %-38s %6d members" % (n, c))
    p("  FILES_AT_THE_ROOT %d" % len(froot))
    for n in froot:
        p("    FILE %s" % n)
    p("  TALLY_SUMS_TO %d MUST_EQUAL_RELS %d  %s"
      % (sum(counts.values()), len(rels_all),
         sum(counts.values()) == len(rels_all)))
    p("  ENUMERATOR_NEGATIVE_zzq %d MUST_BE_0"
      % counts.get(("DIR", "zzq_absent"), 0))
    cand = [n for n in names if n.rstrip("/").endswith("/" + SOURCES_TAIL)]
    p("  SOURCES_MEMBERS_FOUND %d %s" % (len(cand), cand))
    p("  SOURCES_NEGATIVE_zzq %d MUST_BE_0"
      % len([n for n in names if n.endswith("/ZZQ_ABSENT.txt")]))
    raw = None
    if cand:
        fh = tf.extractfile(cand[0])
        raw = fh.read() if fh else b""
        p("  SOURCES_BYTES %d SHA %s" % (len(raw), sha_bytes(raw)))
    else:
        p("  SOURCES_ABSENT_FROM_THE_ARCHIVE")
    return (rels_files, raw, roots)


def sources_entries(raw):
    if raw is None:
        return []
    return [x for x in raw.decode("utf-8", "replace").split("\n") if x.strip()]


def host_legs(repo, quiet=False):
    def p(*a):
        if not quiet:
            print(*a)

    p("== L0 SET, SHAPE, BLINDNESS. DECLARED BEFORE ANY VALUE.")
    p("SET: every member name of the sdist and the wheel the index")
    p("  serves for the pinned version; the SOURCES.txt inside each")
    p("  archive read; the egg-info SOURCES.txt on this disk; and two")
    p("  git path sets named below.")
    p("SHAPE: top-level membership is the FIRST PATH COMPONENT after the")
    p("  single archive root. A member with no slash is a FILE AT THE")
    p("  ROOT and is never folded into a directory bucket. Only REGULAR")
    p("  FILE members enter a set compared against git, because a")
    p("  directory member is not a path git tracks and would read as a")
    p("  false positive.")
    p("BASELINE ONE: git ls-tree -r --name-only v%s. BLIND if the" % PIN)
    p("  published artifact was not built at that tag.")
    p("BASELINE TWO: the path field of git rev-list --objects --all,")
    p("  which walks merge trees. BLIND ONLY to paths that live in")
    p("  unreachable commits. It is a SUPERSET: tree objects contribute")
    p("  directory paths, so it can call a path known when only a")
    p("  directory of that name existed.")
    p("BLIND TO: what a build would do today. These are published")
    p("  bytes. BLIND TO any file the index does not serve.")
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
        p("REFUSE R3_GIT_HEAD_NOT_A_COMMIT_ID")
        return 9
    code, out, _ = git(repo, "ls-files")
    tracked = set(x for x in out.split("\n") if x)
    p("TRACKED_FILES_MUST_BE_NONZERO %d" % len(tracked))
    if not tracked:
        p("REFUSE R3_GIT_BLIND")
        return 9

    p("")
    p("== L2 THE INDEX. METADATA ONLY. NO ARTIFACT BYTES YET.")
    try:
        proj = json.loads(get("https://pypi.org/pypi/" + PROJECT + "/json",
                              META_LIMIT).decode("utf-8"))
    except Exception as exc:
        p("REFUSE R3_INDEX_UNREACHABLE %s" % str(exc)[:160])
        return 9
    latest = proj.get("info", {}).get("version", "")
    p("INDEX_LATEST_VERSION %s" % latest)
    p("BODY_PINNED_VERSION %s" % PIN)
    p("VERSION_ORACLES_AGREE %s" % ("YES" if latest == PIN else "NO"))
    if latest != PIN:
        p("  the index has moved past the pin; THIS RUN MEASURES THE PIN")

    metas = {}
    for v in (PIN, PRIOR):
        try:
            metas[v] = json.loads(get(
                "https://pypi.org/pypi/" + PROJECT + "/" + v + "/json",
                META_LIMIT).decode("utf-8"))
        except Exception as exc:
            p("REFUSE R3_VERSION_METADATA_UNREACHABLE %s %s"
              % (v, str(exc)[:160]))
            return 9
        info = metas[v].get("info", {})
        p("RELEASE %s YANKED %s REASON %s"
          % (v, info.get("yanked", "unknown"),
             (info.get("yanked_reason") or "none")))
        for u in metas[v].get("urls", []):
            p("  FILE %-46s %-13s %10s bytes yanked=%s"
              % (u.get("filename", ""), u.get("packagetype", ""),
                 u.get("size", ""), u.get("yanked", "")))
            p("       sha256 %s" % u.get("digests", {}).get("sha256", ""))

    sd78, n78 = pick_one(metas[PIN].get("urls", []), "sdist")
    wh78, w78 = pick_one(metas[PIN].get("urls", []), "bdist_wheel")
    sd77, n77 = pick_one(metas[PRIOR].get("urls", []), "sdist")
    p("SDIST_COUNT_%s %d" % (PIN, n78))
    p("WHEEL_COUNT_%s %d" % (PIN, w78))
    p("SDIST_COUNT_%s %d" % (PRIOR, n77))
    if n78 != 1:
        p("NOTE sdist count for the pin is not one; the first is measured")
    if sd78 is None:
        p("REFUSE R3_NO_SDIST_PUBLISHED_FOR_THE_PIN")
        return 9

    p("")
    p("== L3 A1. IS THE LOCAL 5.77.0 ARCHIVE THE PUBLISHED ONE.")
    p("   EVERY PRIOR FINDING ABOUT A PUBLISHED SOURCE DISTRIBUTION IN")
    p("   THIS HOUSE WAS MEASURED ON A LOCAL FILE. THIS LEG DECIDES")
    p("   WHETHER THOSE FINDINGS NAME THE OBJECT THEY CLAIM.")
    dd = os.path.join(repo, "dist")
    local77 = None
    if not os.path.isdir(dd):
        p("NO_DIST_DIRECTORY %s" % dd)
    else:
        cands = []
        for n in sorted(os.listdir(dd)):
            fp = os.path.join(dd, n)
            if os.path.isfile(fp) and n.endswith(".tar.gz") and PRIOR in n:
                cands.append(fp)
        p("LOCAL_PRIOR_SDIST_CANDIDATES %d %s"
          % (len(cands), [os.path.basename(c) for c in cands]))
        if len(cands) == 1:
            with open(cands[0], "rb") as fh:
                local77 = fh.read()
            p("LOCAL_PATH %s" % cands[0])
            p("LOCAL_BYTES %d" % len(local77))
            p("LOCAL_SHA256 %s" % sha_bytes(local77))
        elif len(cands) > 1:
            p("AMBIGUOUS more than one candidate; none is measured")
    if sd77 is None:
        p("PUBLISHED_PRIOR_SDIST none on the index")
    else:
        dsha = sd77.get("digests", {}).get("sha256", "")
        p("PUBLISHED_FILENAME %s" % sd77.get("filename", ""))
        p("PUBLISHED_BYTES %s" % sd77.get("size", ""))
        p("PUBLISHED_SHA256 %s" % dsha)
        if local77 is not None:
            v = cmp_whole(dsha, sha_bytes(local77))
            p("LOCAL_IS_THE_PUBLISHED_ARTIFACT %s %s" % (v[0], v))
            if v[0] == "GREEN":
                p("  PRIOR FINDINGS TRANSFER TO THE PUBLISHED ARTIFACT")
            else:
                p("  PRIOR FINDINGS DO NOT NAME THE PUBLISHED ARTIFACT")
                p("  AND OWE A CORRECTION BY APPEND")
        else:
            p("LOCAL_IS_THE_PUBLISHED_ARTIFACT UNDECIDED no local bytes")

    p("")
    p("== L4 THE PUBLISHED SDIST FOR THE PIN, IN MEMORY.")
    dsha78 = sd78.get("digests", {}).get("sha256", "")
    dsize78 = sd78.get("size", 0) or 0
    p("FILENAME %s" % sd78.get("filename", ""))
    p("DECLARED_BYTES %s" % dsize78)
    p("DECLARED_SHA256 %s" % dsha78)
    p("YANKED %s" % sd78.get("yanked", ""))
    if dsize78 and dsize78 > MAX_BYTES:
        p("REFUSE R3_SDIST_OVER_LIMIT %d" % dsize78)
        return 9
    if not dsha78:
        p("REFUSE R3_INDEX_PUBLISHES_NO_DIGEST")
        return 9
    try:
        blob78 = get(sd78["url"], MAX_BYTES)
    except Exception as exc:
        p("REFUSE R3_SDIST_UNREACHABLE %s" % str(exc)[:160])
        return 9
    r = archive_legs(PIN, blob78, dsha78, p)
    if r is None:
        p("REFUSE R3_SDIST_LEG_FAILED")
        return 9
    rels78, raw78, roots78 = r

    p("")
    p("== L5 THE TWO BASELINES, AND WHAT THE ARCHIVE CARRIES THAT")
    p("   NEITHER KNOWS.")
    tagname = "v" + PIN
    code, out, _ = git(repo, "rev-parse", "--verify", "--quiet",
                       tagname + "^{commit}")
    at_tag = set()
    if code == 0 and out.strip():
        p("TAG %s RESOLVES %s" % (tagname, out.strip()[:12]))
        code, out, _ = git(repo, "ls-tree", "-r", "--name-only", tagname)
        at_tag = set(x for x in out.split("\n") if x)
    else:
        p("TAG %s NOT_RESOLVABLE" % tagname)
    p("BASELINE_ONE_TRACKED_AT_TAG %d" % len(at_tag))

    code, out, _ = git(repo, "rev-list", "--objects", "--all")
    ever = set()
    for line in out.split("\n"):
        if " " in line:
            ever.add(line.split(" ", 1)[1])
    p("BASELINE_TWO_PATHS_EVER_REACHABLE %d" % len(ever))
    p("BASELINE_TWO_NEGATIVE_zzq %d MUST_BE_0"
      % len({"zzq_absent_path"} & ever))
    if not ever:
        p("REFUSE R3_REVLIST_BLIND")
        return 9

    s78 = set(rels78)
    p("ARCHIVE_FILE_PATHS %d" % len(s78))
    not_at_tag = sorted(s78 - at_tag) if at_tag else []
    never = sorted(s78 - ever)
    p("IN_ARCHIVE_NOT_TRACKED_AT_TAG %d" % len(not_at_tag))
    for x in not_at_tag[:40]:
        p("  NOT_AT_TAG %s" % x)
    if len(not_at_tag) > 40:
        p("  NOT_AT_TAG ... %d more" % (len(not_at_tag) - 40))
    p("IN_ARCHIVE_AND_IN_NO_REACHABLE_COMMIT %d" % len(never))
    for x in never:
        p("  NO_COMMIT %s" % x)
    if at_tag:
        only_git = sorted(at_tag - s78)
        p("TRACKED_AT_TAG_NOT_IN_ARCHIVE %d" % len(only_git))
        gc = tally(only_git)
        for n, c in sorted([(k[1], v) for k, v in gc.items()
                            if k[0] == "DIR"]):
            p("  MISSING_DIR  %-36s %6d" % (n, c))
        gf = sorted([k[1] for k, v in gc.items() if k[0] == "FILE"])
        p("  MISSING_FILES_AT_ROOT %d" % len(gf))
        for x in gf[:30]:
            p("    MISSING_FILE %s" % x)

    p("")
    p("== L6 SOURCES.txt, THREE WAYS.")
    e78 = sources_entries(raw78)
    p("PUBLISHED_%s_SOURCES_ENTRIES %d" % (PIN, len(e78)))
    sc = tally(e78)
    for n, c in sorted([(k[1], v) for k, v in sc.items() if k[0] == "DIR"]):
        p("  SRCDIR  %-36s %6d" % (n, c))
    p("  SRCFILES_AT_ROOT %d" % len([1 for k in sc if k[0] == "FILE"]))

    e77 = []
    if local77 is not None:
        p("LOCAL_%s ARCHIVE" % PRIOR)
        r77 = archive_legs(PRIOR, local77, None, p)
        if r77 is not None:
            rels77, raw77, _ = r77
            e77 = sources_entries(raw77)
            p("  LOCAL_%s_SOURCES_ENTRIES %d" % (PRIOR, len(e77)))
            s77 = set(rels77)
            never77 = sorted(s77 - ever)
            p("  %s_IN_NO_REACHABLE_COMMIT %d" % (PRIOR, len(never77)))
            for x in never77:
                p("    NO_COMMIT_%s %s" % (PRIOR, x))
            both = sorted(set(never) & set(never77))
            p("  SAME_NO_COMMIT_PATHS_IN_BOTH_RELEASES %d" % len(both))
            for x in both:
                p("    IN_BOTH %s" % x)

    eggs = sorted(n for n in os.listdir(repo) if n.endswith(".egg-info"))
    p("EGG_INFO_DIRECTORIES %d %s" % (len(eggs), eggs))
    ed = []
    for e in eggs:
        sp = os.path.join(repo, e, SOURCES_TAIL)
        if os.path.isfile(sp):
            with open(sp, "rb") as fh:
                b = fh.read()
            ed = sources_entries(b)
            p("  ON_DISK %s BYTES %d SHA %s" % (e, len(b), sha_bytes(b)))
            p("  ON_DISK_SOURCES_ENTRIES %d" % len(ed))
            p("  ON_DISK_TRACKED_IN_GIT %s"
              % (os.path.join(e, SOURCES_TAIL) in tracked))
        else:
            p("  NO_SOURCES_TXT_ON_DISK %s" % e)

    def diff(an, a, bn, b):
        sa, sb = set(a), set(b)
        p("  %s_MINUS_%s %d" % (an, bn, len(sa - sb)))
        for x in sorted(sa - sb)[:20]:
            p("    ONLY_%s %s" % (an, x))
        p("  %s_MINUS_%s %d" % (bn, an, len(sb - sa)))
        for x in sorted(sb - sa)[:20]:
            p("    ONLY_%s %s" % (bn, x))

    p("SOURCES_DIFFERENCES")
    diff("PUB78", e78, "ONDISK", ed)
    diff("PUB78", e78, "LOCAL77", e77)

    p("")
    p("== L7 THE WHEEL, FOR THE ONE QUESTION R2 CANNOT ANSWER.")
    if wh78 is None:
        p("NO_WHEEL_PUBLISHED_FOR_THE_PIN")
    else:
        wsha = wh78.get("digests", {}).get("sha256", "")
        p("WHEEL_FILENAME %s" % wh78.get("filename", ""))
        p("WHEEL_DECLARED_BYTES %s" % wh78.get("size", ""))
        p("WHEEL_DECLARED_SHA256 %s" % wsha)
        p("WHEEL_YANKED %s" % wh78.get("yanked", ""))
        try:
            wblob = get(wh78["url"], MAX_BYTES)
        except Exception as exc:
            p("REFUSE R3_WHEEL_UNREACHABLE %s" % str(exc)[:160])
            return 9
        p("WHEEL_BYTES_FETCHED %d" % len(wblob))
        v = cmp_whole(wsha, sha_bytes(wblob))
        p("WHEEL_DIGEST_MATCHES_DECLARED %s %s" % (v[0], v))
        if v[0] != "GREEN":
            p("REFUSE R3_WHEEL_DIGEST_MISMATCH")
            return 9
        try:
            zf = zipfile.ZipFile(io.BytesIO(wblob))
        except Exception as exc:
            p("REFUSE R3_WHEEL_NOT_A_ZIP %s" % str(exc)[:160])
            return 9
        wnames = zf.namelist()
        p("WHEEL_MEMBERS %d" % len(wnames))
        p("WHEEL_HAS_NO_SINGLE_ROOT the tally below is a different")
        p("  object from the sdist tally and is not merged with it")
        wc = tally(wnames)
        wdirs = sorted([(k[1], v) for k, v in wc.items() if k[0] == "DIR"])
        wfiles = sorted([k[1] for k, v in wc.items() if k[0] == "FILE"])
        p("WHEEL_TOP_LEVEL_DIRECTORIES %d" % len(wdirs))
        for n, c in wdirs:
            p("  WDIR  %-38s %6d" % (n, c))
        p("WHEEL_FILES_AT_THE_ROOT %d" % len(wfiles))
        for n in wfiles:
            p("  WFILE %s" % n)
        tracked_tops = sorted(set(x.split("/")[0] for x in tracked
                                  if "/" in x))
        p("TRACKED_TOP_LEVEL_DIRECTORIES %d" % len(tracked_tops))
        p("  %s" % " ".join(tracked_tops))
        carried = sorted(set(n for n, c in wdirs) & set(tracked_tops))
        p("TRACKED_TOP_LEVEL_DIRECTORIES_THE_WHEEL_CARRIES %d" % len(carried))
        p("  %s" % " ".join(carried))

    p("")
    p("== L8 WHAT THIS RUN CANNOT SAY")
    p("It cannot say the index will serve the same bytes tomorrow. The")
    p("  digests above are recorded so a later session can tell.")
    p("It cannot say why a path is in the archive. It read a list.")
    p("It cannot say a path in no reachable commit was never committed.")
    p("  An unreachable commit is invisible to rev-list --all.")
    p("It cannot say the pinned version is the one a user installs.")
    p("It cannot say a remedy. It was told to measure and it measured.")
    p("IT WROTE NOTHING AND EXTRACTED NOTHING.")
    p("== END")
    return 0


def selftest():
    print("== SELFTEST. IN MEMORY. ZERO FILESYSTEM WRITES, NO TEMPDIR.")
    print("   EVERY ENGINE DRIVEN RED BEFORE IT IS DRIVEN GREEN.")
    fails = []

    def arm(tag, got, want):
        ok = got == want
        print("  %-54s got %-16s want %-16s %s"
              % (tag, repr(got)[:16], repr(want)[:16],
                 "OK" if ok else "ARM_FAILED"))
        if not ok:
            fails.append(tag)

    d = "a" * 64
    arm("E1 exact", cmp_whole(d, d)[0], "GREEN")
    arm("E1 truncated by one", cmp_whole(d, d[:-1]), ("RED", 63))
    arm("E1 overlong correct prefix", cmp_whole(d, d + "b"), ("RED", 64))

    arm("E2 strip_root removes exactly one component",
        strip_root("r/tests/a.py", "r"), "tests/a.py")
    arm("E2 strip_root on the root itself", strip_root("r", "r"), None)
    arm("E2 strip_root refuses a foreign root", strip_root("o/x", "r"), None)
    arm("E2 strip_root does not match a prefix by string",
        strip_root("rr/x", "r"), None)

    arm("E3 top_of nested", top_of("tests/a.py"), ("DIR", "tests"))
    arm("E3 top_of root file", top_of("PKG-INFO"), ("FILE", "PKG-INFO"))
    arm("E3 top_of bare directory", top_of("tests/"), ("FILE", "tests"))
    arm("E3 top_of empty", top_of(""), None)

    t = tally(["tests/a", "tests/b", "docs/c", "PKG-INFO"])
    arm("E4 tally counts every bucket", len(t), 3)
    arm("E4 tally sums to the input", sum(t.values()), 4)
    arm("E4 tally negative", t.get(("DIR", "zzq"), 0), 0)

    arm("E5 traversal absolute", is_traversal("/etc/x"), True)
    arm("E5 traversal dotdot leading", is_traversal("../x"), True)
    arm("E5 traversal dotdot nested", is_traversal("r/../../x"), True)
    arm("E5 traversal negative on a normal path",
        is_traversal("r/docs/a.py"), False)
    arm("E5 traversal negative on a dotted name",
        is_traversal("r/..hidden/a.py"), False)

    FILES = [{"packagetype": "sdist", "filename": "s.tar.gz"},
             {"packagetype": "bdist_wheel", "filename": "w.whl"}]
    arm("E6 pick_one selects by field not suffix",
        pick_one(FILES, "sdist")[0]["filename"], "s.tar.gz")
    arm("E6 pick_one counts what it saw", pick_one(FILES, "sdist")[1], 1)
    arm("E6 pick_one absent", pick_one(FILES, "sdist_zzq"), (None, 0))
    arm("E6 pick_one reports more than one",
        pick_one(FILES + [{"packagetype": "sdist", "filename": "s2"}],
                 "sdist")[1], 2)

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
                  ("extras/f.txt", b"x"), ("PKG-INFO", b"Name: zzsyn\n"),
                  ("zzsyn.egg-info/" + SOURCES_TAIL,
                   b"PKG-INFO\ntests/f.txt\ndocs/f.txt\nextras/f.txt\n")],
                 dirs=("tests", "docs", "extras"))
    cap = []
    res = archive_legs("zz", body, sha_bytes(body), lambda *a: cap.append(
        " ".join(str(x) for x in a)))
    txt = "\n".join(" ".join(l.split()) for l in cap)
    arm("E7 archive_legs returns", res is not None, True)
    arm("E7 THREE DIRECTORIES ARE SEEN, NOT ONE",
        txt.count("DIR ") >= 3, True)
    for tok in ("TOP_LEVEL_DIRECTORIES 4", "DIR tests", "DIR docs",
                "DIR extras", "FILE PKG-INFO", "ARCHIVE_ROOTS 1",
                "TRAVERSAL_MEMBERS_MUST_BE_0 0", "SOURCES_MEMBERS_FOUND 1"):
        arm("E7 LEG %s" % tok[:38], tok in txt, True)
    arm("E7 LEG NEGATIVE absent bucket", "DIR zzq_absent " in txt, False)
    if res is not None:
        relf, raws, _ = res
        arm("E7 DIRECTORY MEMBERS ARE NOT FILE PATHS",
            "tests" in relf or "docs" in relf, False)
        arm("E7 file paths are the regular files only", len(relf), 5)
        arm("E7 SOURCES parsed", len(sources_entries(raws)), 4)

    cap2 = []
    bad = mktar([("../evil.py", b"x")])
    r2 = archive_legs("zz", bad, sha_bytes(bad),
                      lambda *a: cap2.append(" ".join(str(x) for x in a)))
    t2 = "\n".join(cap2)
    arm("E8 traversal member refuses the leg", r2, None)
    arm("E8 and says why", "R3_TRAVERSAL_MEMBER" in t2, True)

    cap3 = []
    r3 = archive_legs("zz", body, "b" * 64,
                      lambda *a: cap3.append(" ".join(str(x) for x in a)))
    arm("E9 a wrong declared digest refuses the leg", r3, None)
    arm("E9 and says why",
        "R3_ARCHIVE_DIGEST_MISMATCH" in "\n".join(cap3), True)

    A = {"a.py", "b/c.py"}
    B = {"a.py", "d.py"}
    arm("E10 set difference left", sorted(A - B), ["b/c.py"])
    arm("E10 set difference right", sorted(B - A), ["d.py"])
    arm("E10 set negative", len({"zzq_absent_path"} & A), 0)

    def invoke(args, want):
        r = subprocess.run([sys.executable, SELF] + args,
                           capture_output=True, text=True, timeout=180)
        ok = want in r.stdout and r.returncode == 9
        print("  %-54s rc %d %s"
              % ("REFUSE " + want, r.returncode, "OK" if ok else "ARM_FAILED"))
        if not ok:
            fails.append(want)

    invoke([T5C[:-1] + ("b" if T5C[-1] != "b" else "c"), "SELFTEST"],
           "T5_DIGEST_MISMATCH")
    invoke([T5C[:-1], "SELFTEST"], "T5_DIGEST_MISMATCH")
    invoke([T5C + "0", "SELFTEST"], "T5_DIGEST_MISMATCH")
    invoke([T5C], "R3_NO_MODE")
    invoke([T5C, "HOSTX"], "R3_UNKNOWN_MODE")
    invoke([T5C, "HOST", "/x", "EXTRA"], "R3_TOO_MANY_ARGUMENTS")

    print()
    if fails:
        print("REFUSE R3_SELFTEST_FAILED %s" % fails)
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
    print("REFUSE R3_NO_REPO_ROOT")
    print("TRIED %s" % [c for c in CAND if c])
    sys.exit(9)
sys.exit(host_legs(REPO))
