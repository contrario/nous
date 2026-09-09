# NOUS-TRACE Reason-Code Registry Coverage -- Innovation Gate (BUILD)

Origin: the measurement recorded as D347. Authority: the Innovation Gate
of `docs/ENGINEERING_CONSTITUTION.md`, ten required sections, in its
order. D346-14 records that the machine-checked form of this reading is
a BUILD and owes a full Gate; this document is that Gate.

All ten sections are present. Section 6 is written BEFORE section 7, as
the constitution requires: the rejection argument comes first.

MEASUREMENT PROVENANCE. Every number below was printed by an instrument
on the host at commit 58e9ec6, in the session that wrote this document,
by a body that wrote nothing. A number marked INHERITED was not
re-measured here and is not used as a premise.

---

## 1. Problem statement

The NOUS-TRACE reason-code registry exists in three hand-maintained
copies with no automated relation between them.

    the normative registry sentence   trace/SPEC.md, line 463
    the raise sites                   trace/reference/verifier.py
    the published conformance table   trace/RESULTS.md

WHICH SECTION CONTAINS LINE 463 WAS MEASURED AND NOT ASSUMED. The
heading census over the file returns `### 12.4 Reason-code registry and
ordering (E6)` at line 461 and `## 13.` at line 465, with no heading
between them, so line 463 lies inside section 12.4. The sentence on that
line names section 12.2, which is the ORDERING clause it points at and
not its own home. The spec body re-reads the nearest preceding heading
from the file, with a `case` pattern and no counted prefix length,
before it writes anything.

A fourth copy, the harness expectation mapping in
`trace/reference/run_tests.py`, decides what the vector corpus is
allowed to report.

Measured at 58e9ec6:

    registry codes                                        41
    distinct codes at raise sites                         42
    codes named in the published table                     9
    codes named in the harness mapping                     9
    registered with no raise site                          0
    raised but not registered                              1, JCS_TYPE
    named in the table but not registered                  0
    registered, implemented, driven by no vector          32
    table and harness code SETS                           identical
      SHAPE: the token inside each INVALID(...) occurrence, bare,
      sorted, DEDUPLICATED, one per line, digested whole.
      DIGEST 679b3b6db4da0d4c under that shape and no other.
      A PRECEDING SESSION MEASURED THE SAME RELATION UNDER A
      DIFFERENT SHAPE, the sorted MULTISET with the parentheses
      retained, and printed 9747259d9cdf7ea0. Both are correct and
      neither is usable without the shape beside it. R24 applies
      inside this document.

The registry is a flat list in prose. It does not say who may add a
code, by what procedure, or what it means when an implementation emits
a code the registry does not carry. Section 12.4 has no allocation
policy of any kind.

The consequence is already in the tree. `JCS_TYPE` is emitted by four
tracked executables and carried by a fifth tracked file in prose:

    trace/reference/verifier.py   the reference Verifier
    tb_check.py                   the shipped bundle checker
    trace_bridge.py               the bridge
    dossier.py                    inside _TRACE_BUNDLE_CHECK_EMBED,
                                  which travels as bytes inside every
                                  emitted verify_offline.py

The fourth is the one that matters to a reader outside this house. An
auditor running an emitted offline verifier can receive a reason code
that the normative registry does not list.

Adding one word to the registry closes this instance and prevents no
other. The absent allocation policy is the defect; the orphan is its
first observed instance.

## 2. Prior art

Fetched 2026-09-08. SECONDARY unless stated. NO NOVELTY IS CLAIMED
ANYWHERE IN THIS DOCUMENT.

ELIMINATIVE ARGUMENTATION, due to Goodenough, Weinstock and Klein,
resting on the eliminative induction of Bacon: confidence in a claim
rises as the reasons for doubting it are enumerated and eliminated, and
each such reason is a defeater. Its associated measure is written as a
resolved count beside a total count and is explicitly NOT a
probability. A registry with driven codes separated from undriven ones
is that measure applied to an evidence layer. The shape is decades old
and is not this house's.

REGISTRY ALLOCATION POLICY is settled IETF practice. RFC 8126
describes the well-known policies a registry declares and the named
ranges, including Private Use, that give an implementer a legal place
to put something the registry does not carry. RFC 9515 names the
failure this prevents: the use of an unregistered code point, which it
calls code point squatting, and argues for a low registration bar
precisely to avoid driving extension underground.

MACHINE-CHECKED ASSURANCE CASES integrating formal and informal
evidence have been published since 2019, with tooling and case
studies. Tool qualification practice already requires a manual
describing a verification tool's failure modes, false negatives
included. The bridging of formal results to certification evidence is
an occupied field, not a gap. A preceding session declared it empty
without enumerating its occupants and was corrected by an outside
reader; that error is recorded and is not repeated here.

AN ADJACENT NEIGHBOUR. An April 2026 paper proposes OSCAL, the format
behind FedRAMP compliance-as-code, as an interchange format for AI
governance evidence. It is not the same object and it is close enough
to be named.

## 3. Patent landscape

THIS IS A WEAK NEGATIVE AND IS WRITTEN AS ONE.

A web reconnaissance was run in a preceding session and found academic
work and no patents. The instrument was a general search engine and not
a patent database, it was one query, and no seat here is a patent
attorney. The constitution says freedom to operate is never assumed.

SCOPE THAT MAKES THE WEAK NEGATIVE ACCEPTABLE. What this Gate
authorises is a test that runs inside this repository's own suite and a
policy sentence in this project's own specification. Nothing is
distributed as a product, nothing is licensed, and no coverage
artefact leaves the house.

THE CONDITION UNDER WHICH THIS SECTION MUST BE REDONE. If a signed
coverage table, a resolved-versus-total count, or any derived
attestation of registry coverage ever ships to a third party inside a
dossier or an evidence pack, real patent research is owed BEFORE that
ship, and this section is void until it is done.

## 4. Claim class

The claim created is narrow and is stated in full:

    OVER THE BYTES AS THEY STAND ON DISK WHEN THE CHECK RUNS, THE
    SET OF REASON CODES THE REFERENCE
    VERIFIER CAN EMIT IS A SUBSET OF THE SET THE NORMATIVE REGISTRY
    LISTS; THE SET THE PUBLISHED TABLE NAMES IS A SUBSET OF THE SAME
    REGISTRY; AND THE PUBLISHED TABLE AND THE HARNESS EXPECTATION
    MAPPING NAME THE SAME SET.

That is the whole claim. It is a claim about bytes on disk at the
moment the check runs, and NOT about a commit. It is not a claim about
behaviour, about reachability, about the adequacy of the vector
corpus, or about any implementation other than the reference Verifier.

WHY THE BYTES AND NOT A COMMIT. A suite test reads the WORKING TREE.
During this arc the two differ by design, while the test sits outside
the collected tree against an uncorrected specification, so a claim
naming a commit would be false at exactly the moment it matters most.
Reading the four files through git plumbing would make a
commit-shaped claim true and would make the test slower and stranger
for no gain.

The specification already asserts the third relation in prose: section
16 states that the codes the vector set exercises are exactly those
named per vector in RESULTS.md. The check makes an existing normative
sentence falsifiable. It does not invent an obligation.

## 5. Honest boundary

PROVED: nothing. `proves` is reserved for Z3 and Farkas results and
this arc produces none.

EVIDENCED: the three set relations above, over the bytes of four
tracked files, as they stand on disk when the check runs.

NOT CLAIMED, EXPLICITLY:

    that any raise site is REACHABLE. No reachability was measured in
      any session.
    that the 32 undriven codes are unreachable, or reachable.
    that a green check means the vector corpus is adequate. Fail-closed
      ordering reports the FIRST failing check, so a correct reason
      code is necessary and not sufficient.
    that any implementation other than the reference Verifier obeys
      the registry. Three other tracked executables emit reason codes
      and are outside the SET of this check by construction.
    any count as a durable property. The check reports numbers and
      asserts relations. It never asserts that the undriven count is
      32, because that number is a measurement and a number written
      into a guard is a copy of a measurement.

BLIND TO: a code written in lower case; a code split across a line
break; a code reached through a name bound elsewhere; a code emitted by
an implementation outside the SET.

## 6. Reasons this should never exist

WRITTEN BEFORE THE ACCEPTANCE ARGUMENT. If this section wins, stop.

R1. IT IS A LINT AGAINST A LIST. Three copies of one set are the
defect. A checker that verifies the copies agree preserves the copies
rather than removing them, and freezes a bad shape behind a green
light.

R2. THE REGISTRY COULD BE GENERATED FROM THE RAISE SITES, making the
check unnecessary by construction. This is the strongest objection in
this section.

R3. SOME LEGS ARE BORN GREEN. Only the leg named
RAISE_SITES_SUBSET_OF_REGISTRY has a live defect to catch; the legs
named PUBLISHED_TABLE_SUBSET_OF_REGISTRY and
TABLE_AND_HARNESS_NAME_THE_SAME_SET hold at this commit. A guard whose
legs have never gone red is the vacuity this whole reading is about,
reproduced inside the instrument that closes it.

R4. ITS SUBJECT IS DOCUMENTATION, NOT BEHAVIOUR. A suite is for
behaviour. Prose drift is a review problem.

R5. IT COSTS SUITE TIME FOREVER, for a defect observed once.

R6. A GREEN CHECK NAMES A NARROWER WORLD THAN A READER WILL ASSUME.
Its SET is one file; four executables emit these codes.

WHY THE REJECTION DOES NOT WIN.

Against R2, which is the one that matters: generating a normative
registry from one implementation's raise sites inverts the direction of
a specification. The registry would become a derivative of the
reference Verifier, and a second implementation could no longer be
wrong, because whatever the reference emits would be definitionally
registered. A specification that cannot be violated by its own
reference implementation is not a specification. R2 is rejected on
architecture, not on cost.

Against R1: the check is paired with an allocation policy in the
specification, so it enforces a stated rule rather than an accident of
three files agreeing. That is the difference between a lint and a
conformance check, and it is why the spec change is two sentences and
not one word.

Against R3: each leg gets its own synthetic fixture and is driven red
then green before any real file is read, and the pre-fix registry line
is FROZEN as a permanent fixture in the test, so the red on a real
defect is reproducible from bytes in the tree after the defect is
gone. A post-fix fixture drives the same parser green, so the pair
evidences that the correction is what changed the colour.

Against R4: the object is a normative document and a shipped
executable, and the relation between them is exactly what a
conformance suite is for. Section 16 of the specification already
asserts one of these relations in prose; prose that cannot go red is
the problem being fixed.

Against R5: the declared floor sits at 2722 against 2894 passing, so
the ratchet price today is zero. THAT ARITHMETIC IS NOT THE
MEASUREMENT, and the measurement was made because a number quoted
without measuring what depends on it is the class this document names
twice. WHAT DEPENDS ON THE FLOOR WAS READ: every tracked test naming
it either reads the literal out of scripts/release.py and compares it
to the hero stat in website/index.html, or reads it as a module
attribute and builds SYNTHETIC pytest output around it. NEITHER
COMPARES THE FLOOR TO A LIVE COUNT, so a further passing test turns no
existing test red. Had one done so, this Gate would owe a further step
or a different placement, and the answer to R5 would be wrong.

The zero price remains a property of a rule not being applied, not a
property of this design: the rule is that the floor sits just below the
live count. If the floor is re-tightened, the price appears. The floor
is release-time and moves in lockstep with the hero stat and is NOT
touched by this arc.

Against R6: the SET, the SHAPE and the BLIND TO are written into the
test file itself, not only into a ledger entry, so a reader six months
from now reads the boundary beside the green light. The allocation
policy names its subject explicitly for the same reason.

## 7. Commodity vs moat

COMMODITY: all of it. Token extraction, set difference, a digest over
a sorted multiset, a test file. A competent engineer reproduces this
in an afternoon.

MOAT: NONE IS CLAIMED BY THIS ARC. Claiming a moat for a registry
consistency check would be the overclaim this house exists to refuse.
The durable asset, if any, is the discipline of naming a SET and a
SHAPE before counting, which is a method and not an artefact and
cannot be fenced.

## 8. Kill criteria

    PRIOR ART ALREADY EXISTS. TRUE and DOES NOT FIRE. Prior art kills
      an idea that claims novelty. This arc claims none: section 2
      names the occupants and section 7 declines a moat. The
      criterion fires on a novelty claim and there is no novelty
      claim to collide with.
    A PATENT BLOCKS IMPLEMENTATION. UNKNOWN, weak negative, scope
      limited by section 3. Fires immediately if a signed coverage
      artefact is ever proposed for third-party distribution.
    THE HONEST BOUNDARY CANNOT BE MAINTAINED. Fires if this check is
      ever reported as coverage of the Verifier's BEHAVIOUR, or if
      any count it reports is written into a specification, a
      dossier, or a served surface as a durable fact.
    IT REQUIRES OVERCLAIM. Does not fire. The claim class in section
      4 is the whole claim and it is a statement about bytes.
    OFFLINE VERIFICATION IMPOSSIBLE. Not applicable. Nothing here
      enters an evidence pack.
    DETERMINISTIC REPLAY IMPOSSIBLE. Does not fire. The check is a
      pure read over tracked bytes.
    THE AUDITOR MUST TRUST THE OPERATOR. Does not fire. No auditor
      sees this artefact.

## 9. Opportunity cost

What is not built because this is built, all measured and all left
open. THE FIRST IS THE HIGHEST CONSEQUENCE, because it is the only one
with a reader outside this house:

    THE EMITTER THAT REACHES AN AUDITOR REMAINS UNBOUND. The check
      binds the reference Verifier. The embed inside dossier.py
      travels as bytes in every emitted verify_offline.py, and after
      this arc it can still emit a code no rule binds it to register.
      Registering JCS_TYPE removes the one observed instance from all
      four emitters at once; it does not bind three of them to
      anything. NAMED HERE SO THAT A GREEN CHECK IS NEVER READ AS
      COVERAGE OF THE SHIPPED SURFACE.

    THE CORPUS IS OUTSIDE THE SUITE. Ten tracked test files call the
      reference verify entry point and none names the corpus path.
      INHERITED from D347, not re-measured here. A separate defect,
      not closed by closing this one.
    A VECTOR FOR AN UNDRIVEN CODE. 32 codes are driven by nothing.
      RUN_START_ANCHORING is the strongest candidate because a later
      revision added it after a pack with a contradictory policy
      verified as valid.
    WHETHER THE CORPUS REGENERATES BYTE FOR BYTE. Not measured
      anywhere. The producer mints keys, which is the reason to
      doubt it. The measurement owed is two runs in two scratch
      trees, diffed against each other FIRST, because a single diff
      against the tracked corpus cannot distinguish not-reproducible
      from reproducible-but-drifted.
    THIS GATE'S OWN THESIS, OBSERVED IN PUBLIC AND NOT TOUCHED HERE.
      website/docs/index.html carries a suite count of 2495 against a
      floor of 2494; the live values are 2894 and 2722. README.md
      carries 2872. NOTHING BINDS EITHER NUMBER TO ANY ORACLE: only
      the hero stat has a test, and that test binds it to the floor
      LITERAL and not to any live count. A number written into a
      document is a copy of a measurement, and one of these copied and
      rotted on the surface a reader actually reaches. THIS ARC MUST
      NOT TOUCH EITHER: the prohibition on served surfaces holds. It
      is recorded as a WORLD finding and belongs on the board as its
      own object.

    THE SPECIFICATION ARCHIVE. Two earlier revisions under
      trace/archive, never read by this lane.
    THE MANIFEST REVISION AND THE MARKOVIAN WITNESS. Untouched for
      several sessions. INHERITED.

The suite is the shared resource this consumes. One further passing
test is the entire ongoing cost.

## 10. Generalization path

START NARROW AND STAY THERE. One registry, in one specification, with
one reference implementation as its subject.

DO NOT build a generic registry-consistency framework. DO NOT
parameterise over other documents. DO NOT extend the SET to the other
three executables that emit these codes: they are outside the subject
the policy binds, and widening the SET without widening the policy
would produce a guard that is red for a reason the specification does
not state.

The generalization trigger, if it ever fires: a second normative
registry appears in this project and the same three-copy shape is
measured again. Until then, one file, one subject.

## 11. DECISION (Innovation Gate outcome)

BUILD.

WHAT THIS GATE AUTHORISES, and nothing else:

    (a) trace/SPEC.md, section 12.4: register JCS_TYPE, and declare an
        allocation rule that names its subject. The rule is closed for
        the reference Verifier, which may emit only registered codes,
        and open for third-party implementations through a declared
        private-use prefix, so that extension has a legal place and is
        not driven into unregistered code points. Registering the
        orphan corrects every raise site at once; the policy binds
        what comes after.

        THE PREFIX IS NAMED HERE AND NOT CHOSEN BY A BODY, for the
        same reason the file paths are: a body that picks it is
        choosing normative vocabulary for a specification. THE
        PRIVATE-USE PREFIX IS `X_`. The shape was chosen so that a
        private-use code stays in the SAME LEXICAL CLASS as every
        registered code, an uppercase letter followed by uppercase
        letters and underscores, so that no extractor, no parser and
        no reader anywhere has to change to accommodate it. A
        hyphenated form would split under the token shape this house
        already uses everywhere. NON-COLLISION IS NOT ASSERTED HERE:
        the specification body measures it, over the registry set and
        the raise-site set together, and REFUSES TO WRITE if any
        member of either begins with that prefix. A seat reading of
        the printed registry found no member beginning with that
        letter, and a seat reading of printed output is testimony and
        is not the measurement.

        THE CHECK MUST NOT KNOW ABOUT THE PRIVATE-USE PREFIX. Its
        subject is the reference Verifier and the rule for that subject
        is CLOSED: every code it raises is registered, with no
        exemption of any kind. A check that learned the prefix and
        exempted it would pass a squatted code carrying the right
        prefix, and would be hollow for the exact class it exists to
        catch. THE PREFIX IS A RULE FOR THIRD PARTIES AND IS NOT AN
        INPUT TO THIS INSTRUMENT.
    (b) one tracked test file. ITS LEGS AND ITS FIXTURES ARE NAMED
        HERE AND NOT COUNTED, because a count written into a durable
        document about work not yet built is the same copy-of-a-
        measurement this Gate refuses in section 5.

        LEGS, each asserting a relation and reporting numbers:
          RAISE_SITES_SUBSET_OF_REGISTRY
          PUBLISHED_TABLE_SUBSET_OF_REGISTRY
          TABLE_AND_HARNESS_NAME_THE_SAME_SET

        FIXTURES, each driving its leg red and then green before any
        tracked file is read:
          SYNTHETIC_UNREGISTERED_RAISE
          SYNTHETIC_TABLE_CODE_NOT_REGISTERED
          SYNTHETIC_TABLE_AND_HARNESS_DIVERGE
          FROZEN_REGISTRY_LINE_BEFORE, a verbatim copy of the real
            registry line as it stands before the correction
          FROZEN_RAISE_SITES_BEFORE, a verbatim copy of the raise-site
            code set as it stands before the correction
          FROZEN_REGISTRY_LINE_AFTER, the corrected line

        BOTH SIDES OF THE FROZEN COMPARISON ARE FROZEN, AND THAT IS
        NOT DECORATION. A frozen registry line compared against the
        LIVE verifier yields a red that is a property of the live
        verifier still raising JCS_TYPE, not a property of bytes in
        the tree. The day that raise site is removed, such a fixture
        turns green and the test stops testing with nothing going red:
        a leg that cannot fail, sitting inside the instrument written
        to close exactly that class. So the frozen pair compares
        frozen against frozen, and FROZEN_REGISTRY_LINE_AFTER against
        FROZEN_RAISE_SITES_BEFORE drives the same parser green, which
        is what evidences that the correction is the thing that
        changed the colour. The synthetic fixtures already had this
        property; the frozen pair was the one place it was lost.

        The build may add fixtures. It may not remove a named one
        without a further decision.

        SET, SHAPE and BLIND TO are written inside the test file.

THE PATHS THIS GATE ALLOCATES, NAMED HERE BECAUSE A BODY THAT CHOOSES
A PATH IS CHOOSING WHERE A NORMATIVE DOCUMENT LIVES:

    docs/NOUS_TRACE_REGISTRY_COVERAGE_DESIGN.md   this document
    tests/test_s345_trace_reason_code_registry.py the check

The test name follows the convention READ FROM THE TREE and not
assumed: of the tracked paths under tests, the dominant filename shape
is test_s followed by digits followed by a subject. The digits are a
session label and not a count.

PLACEMENT, decided by measurement and not by preference: a suite test,
not a release phase. The behavioural diff workflow fires only on a
pull request touching a program file and this lane pushes to the
branch directly. The release workflow fires only on a version tag. A
suite test therefore runs at every session opening as well as at every
release; a release phase runs only at a release. A TEST DOMINATES A
PHASE IN REACH.

ORDER. IT IS NUMBERED BECAUSE JOINING TWO SENTENCES IS HOW IT GETS
DONE BACKWARDS, AND THE LIVE RED CANNOT BE RETRIED. The defect is
corrected once; if the specification commit lands before the live run,
the leg named RAISE_SITES_SUBSET_OF_REGISTRY is green and the red on a
real defect never existed.

    1. The test file sits OUTSIDE THE COLLECTED TREE, at an absolute
       path under /root, and the specification is UNCORRECTED. The
       test runs against the live tree and that leg is RED. The run is
       a body under the same discipline as every other: self digest,
       no writes, porcelain members read by name before and after,
       output kept whole.
    2. The specification is corrected and committed.
    3. The test file is MOVED into the collected tree and staged in
       the same body, and committed, green. The move uses the pattern
       already proven on this host: copy into the TARGET DIRECTORY
       under noclobber, digest the copy THERE, rename within that
       directory, then stage. os.replace is atomic within one
       filesystem only, and the absolute path and the repository may
       not share one. If anything fails between the copy and the
       commit, the body removes the copy BY NAME and says so.

THE WINDOW AT STEP 3 IS NOT THE HAZARD OF STEP 1, AND CONFUSING THEM
PRODUCES EITHER A GUARD NOBODY NEEDS OR A FEAR OF THE RIGHT ORDER. At
step 3 the specification is already corrected, so the file landing
under the collected tree is GREEN. An untracked GREEN test for the
seconds between the copy and the commit harms nothing. The hazard at
step 1 is an untracked RED test under the collected tree, which is why
the file is not there at all until this point.

THE FILE MUST NOT SIT UNTRACKED UNDER tests/ FOR ANY WINDOW. Pytest
collects by path and by name and not by git status, so an untracked
red test under the collected tree makes the WHOLE SUITE red on this
machine for anything that runs it in that window: a release, the
opening protocol of any session, or the other lane, which shares this
worktree and does not read this Gate. The cost of avoiding it is
nothing.

BECAUSE THE BYTES MUST WORK IN BOTH PLACES UNCHANGED, the check does
not compute the repository root by counting parents. It resolves the
root by walking the ancestors of its own file, and then the ancestors
of the working directory, until it finds one carrying both the
specification and the reference Verifier. The bytes that produce the
live red are byte-identical to the bytes that land.

NO ENVIRONMENT OVERRIDE. A SET THAT A VARIABLE CAN REDIRECT IS A GUARD
THAT CAN BE SILENTLY RESOLVED, and nothing needs it here. After the
move, the ancestors of the file find the root immediately. Before the
move, the body that runs the check sets the working directory to the
repository and the second walk finds it. THE DEPENDENCE ON THE WORKING
DIRECTORY IS DECLARED IN THE TEST FILE BESIDE ITS SET, so a reader
knows what makes the walk terminate.

THE RESOLVED ROOT AND WHICH WALK FOUND IT ARE PRINTED ON EVERY RUN,
GREEN OR RED. A SET THAT IS NOT PRINTED IS NOT DECLARED.

No commit that reaches the remote carries a red test. The reverse
order would put a policy on the remote with nothing enforcing it.

THE CHOSEN ORDER DOES NOT ELIMINATE THAT STATE. IT SHORTENS IT, AND
THAT IS A COST AND NOT A DEFECT. Between step 2 and step 3 the remote
carries a policy that nothing enforces. It cannot be avoided while the
no-red-commit rule holds. IF THE SESSION ENDS INSIDE THAT WINDOW, the
handoff names the policy as COMMITTED AND UNENFORCED, and the first
object of the next session is step 3 and nothing else. An unwritten
window is how a policy sits unenforced for thirty sessions.

THE POST-CONDITION THIS GATE EXPECTS, DECLARED BEFORE THE ARC RUNS,
AS AN EXPECTATION OF THE ARC AND NOT AS AN ASSERTION INSIDE THE TEST.
After the specification change lands, the registry carries JCS_TYPE,
so the registered set equals the raised set, the unregistered set is
empty, AND THE COUNT OF REGISTERED CODES DRIVEN BY NO VECTOR RISES BY
ONE, because the newly registered code has no vector either.

THE CORRECTION MAKES THE UNDRIVEN SET LARGER. That is written plainly
here so that a reader who sees the number move upward after a fix
finds the reason recorded rather than deriving it. It is also the
plainest demonstration of why the test must never pin that count.

A CONSEQUENCE FOR FUTURE WORK, WRITTEN BECAUSE UNWRITTEN IT PRODUCES A
SESSION SPENT FIGHTING A RED TEST. Leg
RAISE_SITES_SUBSET_OF_REGISTRY plus the rule that no commit reaching
the remote carries a red test means the reference Verifier and the
specification MUST MOVE IN THE SAME COMMIT whenever a new reason code
appears. This house habitually splits such a change into a commit for
the code and a separate commit for the document. After this arc that
habit is a red tree for the
verifier-and-registry pair. It is a real constraint and it is not an
argument against building.

THE MEASUREMENTS THE ARC OWES, WRITTEN HERE AS STEPS AND NOT LEFT TO
THE SEAL. Both are the class named in D347: a number bound to a head and
carried past it.

    THE SUITE COUNT MOVES WHEN THE TEST LANDS. The passing count and the
    collected count are quoted in the positive controls of the opening
    rule and in the opener expectation list, and both become wrong at
    that moment. The re-measurement runs AFTER the test commit and
    BEFORE the ledger payload is built, on the same tree, with the house
    invocation read from scripts/rule0.sh and not guessed. The declared
    floor is not touched.

    THE MODIFIED TRACKED SET IS NOT A SINGLETON DURING THE
    SPECIFICATION COMMIT. pricing/defaults.toml is modified and is not
    this lane's, so at that moment the modified tracked set is that
    file AND trace/SPEC.md. Every body of the preceding arc pinned the
    modified count at one. A body that copies that leg goes RED FOR
    THE CORRECT STATE, and the temptation at that moment is to make
    the tree match the leg. SO NO BODY OF THIS ARC PINS A TOTAL: every
    body pins the MEMBERS BY NAME, asserts that the foreign path is
    present and untouched, stages by explicit pathspec, and reads the
    index back to show the foreign path did not enter it.

    THE UNTRACKED SET MOVES FIRST. Capturing the live red requires the
    test file to sit untracked in the working tree while the
    specification is still uncorrected, so during the specification
    commit the untracked set carries the test file in addition to the
    three known untracked paths. EVERY BODY PINS THE PORCELAIN MEMBERS
    BY NAME AND NOT BY COUNT, so that a foreign path appearing in
    either lane cannot hide inside an incremented total.

    A THIRD PATH IS ALREADY MODIFIED AND IS NOT THIS LANE'S:
    pricing/defaults.toml, uncommitted. No body of this arc may
    restore, stage or discard it, and no body may run any command that
    WRITES it, which rules out anything that could regenerate pricing
    and not merely the restore and discard verbs. No bare checkout, no
    --hard, no add -A, at any point, including in an undo.

WHAT THIS GATE DOES NOT AUTHORISE: any change to the vector corpus,
any run of the producer, any change to the harness, any served
surface, any signing ceremony, any change to the suite floor, and any
widening of the SET beyond the reference Verifier.

END OF GATE

---

## 12. CORRECTION BY APPEND. THE PATH LIST OF SECTION 11 WAS INCOMPLETE.

NOTHING ABOVE THIS LINE IS EDITED. A Gate rewritten whenever the world
contradicts it is not a Gate: it is a document that is always right
because it is edited to be right. THE TEST THIS GATE APPLIES TO A
SPECIFICATION APPLIES TO THE GATE. A specification that cannot be
violated by its own reference implementation is not a specification, and
a Gate that cannot be falsified by measurement is not a Gate. This one
was falsified. The falsification is recorded here rather than smoothed
away above.

### 12.1 What was wrong

Section 11 allocates two paths. A third is required:

    tests/spec_normative_baseline.json

### 12.2 Why it was wrong, which is worth more than the path

SECTION 11 MEASURED THE FILES THE CHECK WOULD READ AND NOT THE TRACKED
FILES THAT READ THE OBJECT THIS ARC WRITES TO. THE GATE MEASURED ITS OWN
INPUTS AND NOT ITS OWN BLAST RADIUS. That is a class, not an oversight.

The evidence that it is a class: two further tracked tests name the
specification and either could have been bound to the revision number.
tests/test_wire_compat.py reads only the wire version out of the
normative example, and tests/test_s257_f4_checkpoint_cadence.py names
the specification in prose and reads packs instead. Neither is bound to
the revision, SO NEITHER MOVES. THAT IS LUCK AND NOT DESIGN. The read
that found the baseline found those only because it was widened to every
tracked file naming the specification, and it was widened after this
Gate was written.

### 12.3 The third path is a different kind, and the difference matters

    AUTHORED, by this arc:
      docs/NOUS_TRACE_REGISTRY_COVERAGE_DESIGN.md
      tests/test_s345_trace_reason_code_registry.py

    REGENERATED, by the test that guards it:
      tests/spec_normative_baseline.json

The baseline record is not content this arc writes. It is the output of
tests/test_spec_normative_baseline.py, which fails ON PURPOSE when the
normative text and the revision have both moved, and which PRINTS THE
EXACT RECORD TO WRITE. The record is transcribed from that failing
output and is never computed a second time by any other instrument,
because a second implementation of the same hash is a second thing that
can drift. NO BODY OF THIS ARC HAND EDITS THAT FILE.

### 12.4 The revision bump is the act of registering, not a further act

Section 11(a) authorises registering a code and declaring a policy. It
does not mention the document revision, and the seat that wrote it
leaned toward leaving the revision alone on the strength of a single
instance. THAT LEAN WAS WRONG FOR THE SAME REASON THE PATH LIST WAS
INCOMPLETE: it reasoned from a single instance and did not read the
file.

The file answers it. The header carries a Version line, a Status line
naming what it supersedes, and a Changes block for every revision since
0.2.0. THE EXACT PRECEDENT IS THE 0.2.3 TO 0.2.4 BLOCK: a reason code
registered in section 12.4, placed to match the section 12.2 check
order, and the revision moved with it. A REVISION BUMP IS HOW THIS FILE
REGISTERS A CODE. It is the act, not a further act requiring further
authority, and the specification body transcribes a measured convention
instead of choosing one.

The registry parenthetical names the revision in which THE REGISTRY last
changed, not the revision of the document: it reads v0.2.4 while the
document reads 0.2.6, because the revisions between them changed other
sections. That is measured, and it is what makes the parenthetical
correct today rather than stale.

### 12.5 The normative hash moves BY DESIGN

The allocation policy carries MUST. A policy without MUST is not
normative and the check would enforce nothing declared. So the policy
enters the RFC 2119 surface that tests/test_spec_normative_baseline.py
hashes, and the hash moves.

THAT IS INTENDED AND IT IS WRITTEN HERE BEFORE IT HAPPENS, so that it is
a design decision rather than a test that had to be appeased. The
registry line itself carries no RFC 2119 keyword, so registering the
code alone would not move the hash. The policy is what moves it, and the
policy is the part that has force.

### 12.6 The order the third path imposes

THE SPECIFICATION AND THE BASELINE RECORD MOVE IN THE SAME COMMIT. The
record is a statement about the bytes of that specification, so a commit
carrying either without the other leaves the tree red between them.

This is the constraint section 11 already recorded for the reference
Verifier and the registry, now observed on a different pair inside this
same arc. IT GENERALISES, AND THE GENERALISATION IS THE FINDING:
WHENEVER A TRACKED ARTEFACT RECORDS A PROPERTY OF ANOTHER TRACKED
ARTEFACT, THE TWO MOVE IN THE SAME COMMIT.

### 12.7 The order as it now stands

    1. The Gate lands.
    2. This correction lands by append.
    3. The test file sits at an absolute path OUTSIDE the collected
       tree, the specification is UNCORRECTED, the check runs, and the
       leg named RAISE_SITES_SUBSET_OF_REGISTRY is RED. THE FROZEN
       FIXTURES ARE TAKEN HERE, from the file as it stands, printed
       whole by the body that captures the red. They are never
       reconstructed afterwards from memory of what the line said.
    4. trace/SPEC.md and tests/spec_normative_baseline.json together:
       the code registered, the policy declared, the revision bumped,
       the Changes block added, and the record transcribed from the
       failing output of its own producer.
    5. The test file is moved into the collected tree and committed,
       green.
    6. The ledger entry.

    Then the push. The window in which a policy is committed with
    nothing enforcing it exists only on this machine and never reaches
    the remote. IF THE SESSION ENDS INSIDE IT, the handoff names a state
    this Gate did not: work committed locally, invisible to the other
    lane, recoverable only from this machine.

END OF CORRECTION
