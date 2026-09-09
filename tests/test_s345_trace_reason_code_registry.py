"""The reason-code registry, its implementation and its published table,
checked against each other instead of maintained in parallel by hand.

WHY THIS EXISTS. NOUS-TRACE keeps one set of reason codes in three
tracked places: the normative registry sentence in trace/SPEC.md, the
raise sites in trace/reference/verifier.py, and the conformance table in
trace/RESULTS.md, with a fourth copy in the harness expectation mapping
of trace/reference/run_tests.py. Nothing related them. Section 16 of the
specification already asserts one of those relations in prose; prose
that cannot go red is what this file replaces. The decision to build it,
its rejection argument, its prior art and its honest boundary live in
docs/NOUS_TRACE_REGISTRY_COVERAGE_DESIGN.md.

SET. Four tracked files, read from the resolved repository root: the
specification, the reference Verifier, the conformance table, the
harness expectation mapping. THE SUBJECT OF THE CLOSED RULE IS THE
REFERENCE VERIFIER ALONE. Other tracked executables emit reason codes
and are outside this SET by construction, which is recorded in the
design document rather than smuggled in here.

SHAPE. Uppercase token extraction with the prose word FIRST excluded BY
NAME; the raise sites matched through the exception constructor; the
table and the harness matched inside INVALID(...). Set relations by
subset and equality. NUMBERS ARE REPORTED AND NEVER ASSERTED.

BLIND TO. A code written in lower case. A code split across a line
break. A code reached through a name bound elsewhere. THE REACHABILITY
of any raise site. Any implementation outside the SET.

WHAT IS CLAIMED. Only that, over the bytes as they stand on disk when
this runs, the raised set is a subset of the registered set, the
published set is a subset of the registered set, and the published set
equals the harness set. NOTHING IS PROVED HERE; proved is reserved for
Z3 and Farkas results elsewhere in this project.

ANTECEDENT FAILURE IS CLOSED HERE TOO. A subset relation with an empty
left side is trivially true, so a broken extractor would leave the
relation legs green while nothing was measured. Each of the four sets
therefore asserts its own non-emptiness, as a relation and never as a
count.

THE WORKING DIRECTORY MATTERS AND THAT IS DECLARED. The root is
resolved by walking the ancestors of this file and then the ancestors
of the working directory until one carries all four files. There is NO
environment override: a SET that a variable can redirect is a guard
that can be silently resolved. The identity of the resolved tree is
ASSERTED and not merely printed, because a printed root is testimony,
and a walk landing on some other tree carrying similar files would
otherwise pass every leg.

NON-ASCII, DELIBERATE AND CONTAINED. The frozen registry fixture below
is a VERBATIM copy of the registry line as it stood before the
correction this file accompanies, and that line carries a section sign,
which is not ASCII. The house rule against non-ASCII in inserted
content and the requirement that a frozen fixture be verbatim are in
direct conflict here, and verbatim wins: a fixture with the sign
replaced by its name is a paraphrase, and a paraphrase cannot evidence
that a parser went red on the bytes that were actually there. A base64
form was considered and rejected: byte-exact, but a reader cannot see
what went red. A leg below asserts that the ONLY non-ASCII bytes in
this file lie inside that fixture.

THE FIXTURES WERE NOT TRANSCRIBED. They were spliced on the host from
the live files, so the bytes never passed through a terminal or a
conversation.
"""
from __future__ import annotations

import re
from pathlib import Path

# --- the frozen pair -------------------------------------------------
# Spliced from the live files BEFORE the registration this arc applies.
FROZEN_REGISTRY_LINE_BEFORE = """Fail-closed ordering is normative: the reported reason is the FIRST failing check in §12.2 order. Registry (v0.2.4; `RUN_START_ANCHORING` added in 0.2.4, otherwise unchanged since v0.2.1): `SPEC_VERSION, TOLERANCE_INVALID, MANIFEST_FILE_HASH, KEYS_MANIFEST_SIG, KEY_ID_MISMATCH, OBLIGATION_MANIFEST_SIG, OBLIGATION_ID_MISMATCH, PROOF_ARTIFACT_MISSING, PROOF_ARTIFACT_HASH, ASSURANCE_INVALID, FLOAT_IN_SIGNED, INT_RANGE, EMPTY_TRACE, TRACE_ID_MIXED, SEQ_ORDER, HASH_CHAIN_BREAK, KEY_UNKNOWN, SIG_INVALID, STRUCT_NO_RUN_START, RUN_START_KEYS_HASH, RUN_START_OBL_HASH, RUN_START_TOLERANCE, RUN_START_ANCHORING, CKPT_RANGE, MERKLE_MISMATCH, CKPT_ROOT_SIG, ANCHOR_TYPE, ANCHOR_INVALID, TIME_BOUND_VIOLATION, KEY_EXPIRED, PAYLOAD_CLASS, PAYLOAD_HASH_MISMATCH, ASSIGNMENT_MISSING, ASSIGNMENT_REF_MISSING, ASSIGNMENT_PARSE, ASSIGNMENT_VARS_MISMATCH, OBLIGATION_UNKNOWN, OBLIGATION_REF_REQUIRED, OBLIGATION_REF_FORBIDDEN, VERDICT_MISMATCH, SALT_REUSE`. Wrong-tag signatures (E4) are indistinguishable from bad signatures by construction and are reported as `SIG_INVALID`."""

FROZEN_RAISE_SITES_BEFORE = """ANCHOR_INVALID
ANCHOR_TYPE
ASSIGNMENT_MISSING
ASSIGNMENT_PARSE
ASSIGNMENT_REF_MISSING
ASSIGNMENT_VARS_MISMATCH
ASSURANCE_INVALID
CKPT_RANGE
CKPT_ROOT_SIG
EMPTY_TRACE
FLOAT_IN_SIGNED
HASH_CHAIN_BREAK
INT_RANGE
JCS_TYPE
KEYS_MANIFEST_SIG
KEY_EXPIRED
KEY_ID_MISMATCH
KEY_UNKNOWN
MANIFEST_FILE_HASH
MERKLE_MISMATCH
OBLIGATION_ID_MISMATCH
OBLIGATION_MANIFEST_SIG
OBLIGATION_REF_FORBIDDEN
OBLIGATION_REF_REQUIRED
OBLIGATION_UNKNOWN
PAYLOAD_CLASS
PAYLOAD_HASH_MISMATCH
PROOF_ARTIFACT_HASH
PROOF_ARTIFACT_MISSING
RUN_START_ANCHORING
RUN_START_KEYS_HASH
RUN_START_OBL_HASH
RUN_START_TOLERANCE
SALT_REUSE
SEQ_ORDER
SIG_INVALID
SPEC_VERSION
STRUCT_NO_RUN_START
TIME_BOUND_VIOLATION
TOLERANCE_INVALID
TRACE_ID_MIXED
VERDICT_MISMATCH"""

# THE AFTER SIDE IS DERIVED AND NOT FROZEN, and it is named for what it
# is. The corrected line does not exist at the moment the frozen bytes
# must be taken, so a fixture called frozen over something computed
# would be the class this file exists to close, written into the
# instrument that closes it. The derived pair evidences that THIS
# TRANSFORMATION changes the colour. Whether the live specification
# received it is the subject of the live legs, and the derived pair is
# never compared against the live file, so a later registration cannot
# turn it red.
_REGISTRATION_ANCHOR = "INT_RANGE, "
_REGISTRATION_RESULT = "INT_RANGE, JCS_TYPE, "

_CODE = re.compile(r"[A-Z][A-Z_]{2,}")
_RAISE = re.compile(r'VErr\("([A-Z][A-Z_]+)"')
_TABLE = re.compile(r"INVALID\(([A-Z_]+)\)")
_REGISTRY_LOCATOR = "Fail-closed ordering is normative"
_SPEC_HEADER = "# NOUS-TRACE Specification"

_FILES = (
    "trace/SPEC.md",
    "trace/reference/verifier.py",
    "trace/RESULTS.md",
    "trace/reference/run_tests.py",
)


def _resolve_root():
    """Walk to a tree carrying all four files. No counted parents and no
    environment override. Returns the root and which walk found it."""
    for start, how in ((Path(__file__).resolve(), "file"),
                       (Path.cwd().resolve(), "cwd")):
        for cand in (start, *start.parents):
            if all((cand / name).is_file() for name in _FILES):
                return cand, how
    raise RuntimeError(
        "no ancestor of this file or of the working directory carries "
        "all of " + ", ".join(_FILES))


# THE RAISE ABOVE IS DELIBERATE AND IT IS FAIL-CLOSED. A module that
# cannot find its subject has nothing to test, and inventing a fallback
# root would be far worse. THE CONSEQUENCE IS DECLARED HERE BECAUSE AN
# UNDECLARED FAIL-CLOSED PATH IS STILL UNDECLARED: this line runs at
# module scope, so NO ROOT AT ALL is a COLLECTION ERROR and not a
# failing leg. The runner reports an error, the passing count drops by
# this whole file, and the message is a traceback rather than the
# sentence below.
#
# THE TWO ROOT FAILURES ARE DIFFERENT OBJECTS. No root at all is the
# collection error just described, and nothing inside this file can
# exercise it. A root that EXISTS but is the wrong tree is the leg
# test_root_is_the_expected_tree, because the module imports fine and
# the header assertion catches it.
_ROOT, _HOW = _resolve_root()


_IN_WHERE = False


def _where() -> str:
    """The resolved root AND the four set sizes, carried in the message
    of every leg that can fail. THE COUNTS TRAVEL WITH THE FAILURES
    INSTEAD OF BEING PRINTED INTO A VOID: the runner captures output on
    a green run, so a function that only prints is a leg that cannot
    fail and cannot be read. This function must never raise, because it
    builds the message for the very failures a broken locator causes,
    and it must not re-enter itself for the same reason."""
    global _IN_WHERE
    bare = "root=%s found_by=%s" % (_ROOT, _HOW)
    if _IN_WHERE:
        return bare
    _IN_WHERE = True
    try:
        sizes = []
        for name, fn in (("registered", _registered), ("raised", _raised),
                         ("published", _published),
                         ("expected", _expected)):
            try:
                sizes.append("%s=%d" % (name, len(fn())))
            except Exception:
                sizes.append("%s=err" % name)
        return bare + " " + " ".join(sizes)
    finally:
        _IN_WHERE = False


def _read(name: str) -> str:
    return (_ROOT / name).read_text(encoding="utf-8")


def _codes(text: str) -> set:
    return {t for t in _CODE.findall(text) if t != "FIRST"}


def _registry_line(spec_text: str) -> str:
    hits = [ln for ln in spec_text.splitlines()
            if _REGISTRY_LOCATOR in ln]
    assert len(hits) == 1, (
        "the registry sentence must appear exactly once; found %d. %s"
        % (len(hits), _where()))
    return hits[0]


def _registered() -> set:
    return _codes(_registry_line(_read("trace/SPEC.md")))


def _raised() -> set:
    return set(_RAISE.findall(_read("trace/reference/verifier.py")))


def _published() -> set:
    return set(_TABLE.findall(_read("trace/RESULTS.md")))


def _expected() -> set:
    return set(_TABLE.findall(_read("trace/reference/run_tests.py")))


def _derived_registry_line_after() -> str:
    """The frozen line with exactly the registration this arc applies.
    THE ANCHOR IS ASSERTED BEFORE IT IS USED: if the frozen line were
    ever edited so that the anchor vanished or appeared twice, a silent
    replace would produce something that is not the corrected line, and
    the pair below would evidence nothing."""
    seen = FROZEN_REGISTRY_LINE_BEFORE.count(_REGISTRATION_ANCHOR)
    assert seen == 1, (
        "the registration anchor %r appears %d times in the frozen "
        "line; the derivation is defined only when it appears once"
        % (_REGISTRATION_ANCHOR, seen))
    return FROZEN_REGISTRY_LINE_BEFORE.replace(
        _REGISTRATION_ANCHOR, _REGISTRATION_RESULT, 1)


# --- the root is asserted, not printed -------------------------------

_WITNESS = {
    "trace/SPEC.md": "# NOUS-TRACE Specification",
    "trace/reference/verifier.py": "class VErr(Exception):",
    "trace/RESULTS.md": "Conformance matrix",
    "trace/reference/run_tests.py": "EXPECT = {",
}


def test_root_is_the_expected_tree():
    """A printed root is testimony. An asserted root is a measurement."""
    for name in _FILES:
        assert (_ROOT / name).is_file(), (
            "resolved root does not carry %s. %s" % (name, _where()))
    first = _read("trace/SPEC.md").splitlines()[0]
    assert first.strip() == _SPEC_HEADER, (
        "the specification at the resolved root does not carry the "
        "header line by which that document names itself; the walk "
        "landed on some other tree. first line was %r. %s"
        % (first[:60], _where()))
    print("RESOLVED " + _where())


def test_the_four_paths_are_distinct_and_are_what_they_claim():
    """A locator pointed at the wrong tracked file can still return a
    populated set, so every emptiness leg passes and all three relations
    are measured over the wrong object. The paths must be distinct AND
    each must carry a phrase by which that file names its own kind."""
    resolved = [(_ROOT / name).resolve() for name in _FILES]
    assert len(set(resolved)) == len(resolved), (
        "the four paths are not distinct: %s. %s" % (resolved, _where()))
    for name in _FILES:
        witness = _WITNESS[name]
        assert witness in _read(name), (
            "%s does not carry the phrase by which that file names its "
            "own kind (%r); the set it yields would be measured over "
            "the wrong object. %s" % (name, witness, _where()))


# --- antecedent failure: an empty left side satisfies any subset -----

def test_the_registry_set_is_not_empty():
    assert _registered(), (
        "the registry sentence yielded no codes; its locator or the "
        "token shape is broken, and every subset leg below would pass "
        "while measuring nothing. " + _where())


def test_the_raise_site_set_is_not_empty():
    assert _raised(), (
        "no raise site was found in the reference Verifier; the "
        "constructor shape is broken. " + _where())


def test_the_published_set_is_not_empty():
    assert _published(), (
        "the conformance table yielded no codes. " + _where())


def test_the_harness_set_is_not_empty():
    assert _expected(), (
        "the harness expectation mapping yielded no codes. " + _where())


# --- the synthetic fixtures, driven red then green -------------------

_SYN_REGISTRY = "Registry: `AAA_BBB, CCC_DDD`."
_SYN_TABLE = "| x | INVALID(AAA_BBB) | PASS |"
_SYN_HARNESS = '"t01": (20, "INVALID(AAA_BBB)"),'


def test_synthetic_unregistered_raise_goes_red_then_green():
    registered = _codes(_SYN_REGISTRY)
    assert {"EEE_FFF"} - registered == {"EEE_FFF"}, (
        "SYNTHETIC_UNREGISTERED_RAISE did not go red")
    assert {"AAA_BBB", "CCC_DDD"} - registered == set(), (
        "the green side of the same fixture did not go green")


def test_synthetic_table_code_not_registered_goes_red_then_green():
    registered = _codes(_SYN_REGISTRY)
    assert set(_TABLE.findall("INVALID(ZZZ_YYY)")) - registered, (
        "SYNTHETIC_TABLE_CODE_NOT_REGISTERED did not go red")
    assert not set(_TABLE.findall(_SYN_TABLE)) - registered, (
        "the green side of the same fixture did not go green")


def test_synthetic_table_and_harness_diverge_goes_red_then_green():
    assert (set(_TABLE.findall(_SYN_TABLE))
            != set(_TABLE.findall("INVALID(CCC_DDD)"))), (
        "SYNTHETIC_TABLE_AND_HARNESS_DIVERGE did not go red")
    assert (set(_TABLE.findall(_SYN_TABLE))
            == set(_TABLE.findall(_SYN_HARNESS))), (
        "the green side of the same fixture did not go green")


# --- the frozen pair -------------------------------------------------

def test_frozen_pair_reproduces_the_real_red_then_green():
    """The red this check was built for, kept reproducible from bytes in
    the tree after the defect is gone. BOTH SIDES ARE FROZEN: comparing
    a frozen line against the LIVE verifier would yield a red that is a
    property of the live verifier rather than of these bytes, and would
    turn green by itself the day that raise site changes."""
    frozen_registered = _codes(FROZEN_REGISTRY_LINE_BEFORE)
    frozen_raised = set(FROZEN_RAISE_SITES_BEFORE.split())
    assert frozen_registered, "the frozen registry fixture is empty"
    assert frozen_raised, "the frozen raise-site fixture is empty"

    unregistered = frozen_raised - frozen_registered
    assert unregistered, (
        "the frozen pair no longer reproduces the red it was taken for")
    assert unregistered == {"JCS_TYPE"}, (
        "the frozen red is not the one recorded: %s"
        % sorted(unregistered))

    after = _derived_registry_line_after()
    assert after != FROZEN_REGISTRY_LINE_BEFORE, (
        "the derivation produced the line it started from")
    assert not (frozen_raised - _codes(after)), (
        "the registration does not turn the frozen red green, so the "
        "correction is not what changes the colour")


def test_only_the_frozen_fixture_carries_non_ascii():
    src = Path(__file__).read_text(encoding="utf-8")
    rest = src.replace(FROZEN_REGISTRY_LINE_BEFORE, "")
    offenders = [ln.strip()[:70] for ln in rest.splitlines()
                 if not ln.isascii()]
    assert not offenders, (
        "non-ASCII outside the frozen fixture: %s" % offenders)


# --- the three live legs ---------------------------------------------

def test_raise_sites_subset_of_registry():
    registered, raised = _registered(), _raised()
    unregistered = raised - registered
    assert not unregistered, (
        "the reference Verifier can emit reason codes the normative "
        "registry does not list: %s. Register them in the registry "
        "sentence of section 12.4, or stop raising them. %s"
        % (sorted(unregistered), _where()))


def test_published_table_subset_of_registry():
    registered, published = _registered(), _published()
    unregistered = published - registered
    assert not unregistered, (
        "the published conformance table names reason codes the "
        "registry does not list: %s. %s"
        % (sorted(unregistered), _where()))


def test_table_and_harness_name_the_same_set():
    published, expected = _published(), _expected()
    assert published == expected, (
        "the published conformance table and the harness expectation "
        "mapping disagree; section 16 of the specification states they "
        "name the same set. only in table: %s. only in harness: %s. %s"
        % (sorted(published - expected), sorted(expected - published),
           _where()))


# --- the counts are not a leg -----------------------------------------
# A function that computes four sets and calls print asserts nothing.
# It passes forever, and the runner swallows its output on green, which
# is the same trap the printed-root requirement was refused for. The
# counts travel in _where(), inside the message of every leg that can
# fail. THE LEDGER TAKES ITS NUMBERS FROM THE READ-ONLY BODY, which is
# where a measurement belongs.
#
# An identity relating the four sets to one another would not rescue a
# fourteenth leg either: any such algebra is a tautology and cannot
# fail, which is worse than a print.
