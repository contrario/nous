"""Content for D353.

Shape copied from content_d352.py, sha256 2231130c, which the builder
build_d333.py sha256 1b8093f4 renders.

HEAD           str, rendered as a head line carrying the ENTRY number.
PROSE          list of str.
ITEMS          list of (anchor, text).
FINDINGS_S331  group A, keyed to the preceding namespace, EMPTY HERE.
FINDINGS_S332  group B, triples of (code, label, text).

THE TWO GROUP NAMES ARE STALE AND LOAD BEARING AT ONCE. They were
frozen by an earlier copy and no longer describe their contents; the
builder reads these exact identifiers, so they are not corrected here.
The note travels with the shape and is not tidied.

NO FULL DIGEST APPEARS IN THE RENDERED TEXT. At the finding
continuation column a sixty-four character word renders past the width
guard, so identity in the payload is carried by byte counts and by
short forms named as short forms.

NO FINDING CODE AND NO PRIOR ANCHOR IS CITED IN THE PROSE. The
substitution that keeps a cited code out of the census column binds
only a token preceded by a space, and the pattern the house censuses
D-families with is not recorded in any artifact this seat holds.
"""

HEAD = (
    "the source distribution this project publishes to an index is "
    "read for the first time and the finding the preceding entry led "
    "with does not survive the reading, the archive that entry "
    "measured is not the artifact the index serves, the three files "
    "it reported as existing in no commit reached no index at all, "
    "the clone on which every such absence was computed is found to "
    "be grafted, and the decision gate that had been announced as "
    "placed twice and was absent both times is placed and read back "
    "from the remote"
)

PROSE = [
    "R24 GOVERNS EVERY VALUE BELOW. Each was printed by a named "
    "instrument on a named host in the session that carries this "
    "entry. Each instrument declared its set, its shape and what it "
    "was blind to before any value was printed, and each was driven "
    "green and driven red on synthetic fixtures before it touched a "
    "host or a network. Where a value below is derived by arithmetic "
    "or by reclassification rather than printed, the sentence "
    "carrying it says so.",

    "READ THIS PARAGRAPH BEFORE ANY OTHER. NO INDEX HAS SERVED A "
    "BYTE OF THIS PROJECT THAT ITS OWN HISTORY CANNOT ACCOUNT FOR, "
    "beyond two files that every source distribution of this "
    "packaging tool generates and that the shipped file list does "
    "not claim. The entry immediately above this one says otherwise "
    "in its fifth item. That sentence is wrong in two independent "
    "ways and both are corrected here. A READER WHO FINISHES THIS "
    "ENTRY BELIEVING THE INDEX IS SERVING ORPHAN BYTES HAS READ AN "
    "ENTRY THAT FAILED.",

    "WHAT IS REAL IS SMALLER AND SHARPER THAN WHAT WAS CLAIMED. A "
    "build run on a working directory sweeps files into a source "
    "distribution by extension, and the file that lists what this "
    "project deliberately ignores is never consulted by the file "
    "that lists what a distribution includes. The two rule sets do "
    "not see each other. A build performed where the ignored files "
    "exist produces an archive carrying them; a build performed from "
    "a clean checkout does not. BOTH WERE MEASURED. Only the second "
    "kind has ever reached an index.",

    "THE SCOPE WAS THE OPERATOR'S AND SO WAS EVERY IRREVERSIBLE "
    "ACTION AND EVERY REQUEST THAT LEFT THE HOST. The opening rule "
    "ran first and in full. The operator then chose one object, "
    "authorised a bounded set of requests to a public index after "
    "the seat declared what each would send, and closed that surface "
    "when the set was spent. No artifact was built or rebuilt to "
    "settle a question, no packaging metadata was written, no "
    "release was cut, no distribution was withdrawn, no history was "
    "deepened, and the untracked cache this entry reports on was "
    "read and left exactly as it was found.",

    "WHAT THIS ENTRY DOES NOT CLOSE, STATED HERE SO NO LATER "
    "ARTIFACT HAS TO INFER IT. The reason a directory of tests "
    "reaches both published archives is unexplained with both "
    "declared inputs read end to end. The history this repository "
    "holds is truncated and every absence computed against it is a "
    "bound rather than a fact. And this ledger is still enforced by "
    "no test. A TRACKED FILE THAT NO TEST INVOKES IS NOT AN "
    "ENFORCEMENT.",
]

ITEMS = [
    ("D353-1",
     "THE OBJECT AND WHO CHOSE IT. The operator chose the published "
     "source distribution, fixed the scope at measurement, forbade "
     "every remedy, and required the seat to bring each instrument "
     "decided with its own attack on it. Before that object opened, "
     "the operator directed one write that was not the object: a "
     "decision gate existing in no repository was placed and "
     "committed. AT NO POINT DID THIS LANE CHOOSE THE OBJECT."),

    ("D353-2",
     "A DECISION GATE THAT EXISTED IN ONE COPY NOW EXISTS IN THREE. "
     "It had been announced as placed on the host in two earlier "
     "sessions and was absent both times. A search over every file "
     "on this host of its exact size returned sixteen candidates and "
     "none carried its digest, which made those announcements false "
     "rather than merely unverified. It was then written, copied, "
     "committed and read back from the remote at its source digest, "
     "and the sentence saying it is there was written after the "
     "measurement rather than before it. FILING A DOCUMENT OPENS "
     "NOTHING: the four decisions its own final section reserves to "
     "the operator remain reserved and untouched."),

    ("D353-3",
     "THE OPENING BODY OF EVERY SESSION BECAME SELF VERIFYING AND A "
     "NINTH BODY WAS FOUND BEHIND IT. Invoked by absolute path, the "
     "first body now prints that it is a file and prints its own "
     "digest whole, both true for the first time, with no byte of it "
     "changed. The remedy predicted by the preceding session held "
     "exactly. THE WORK THAT PRODUCES EVERY VALUE IT PRINTS IS DONE "
     "BY A SCRIPT IT CALLS, which is tracked, which no sealed "
     "artifact of this house pins, and whose only digest is the one "
     "printed by the leg that runs it."),

    ("D353-4",
     "THE PUBLISHED SOURCE DISTRIBUTION OF THE CURRENT VERSION IS "
     "READ. SET: the archive the index serves for the pinned "
     "version, fetched into memory and never written to disk, its "
     "digest verified against the one the index declares before any "
     "member was read. SHAPE: only regular file members enter a set "
     "compared against version control, because a directory member "
     "is not a path version control tracks and would read as a false "
     "positive. RESULT: one archive root, no member escaping it, "
     "five hundred regular files, four top-level directories, and "
     "one hundred and eighty-six files at the root. TWO PATHS EXIST "
     "IN NO COMMIT THIS CLONE CAN REACH, and they are exactly the "
     "two members that the shipped file list does not name. Both are "
     "generated at build time by the packaging tool."),

    ("D353-5",
     "THE FIRST CORRECTION BY APPEND: THE OBJECT WAS WRONG. The "
     "entry immediately above this one describes a published source "
     "distribution. What it measured was an archive sitting in the "
     "build output directory of this host. The index serves, for "
     "that same version, an archive of a different size and a "
     "different digest. The local file is larger by several thousand "
     "bytes and carries three members the served one does not. THAT "
     "IS NOT IMPRECISION ABOUT WHERE A FILE SITS. Every figure in "
     "that item describes an artifact no consumer has ever "
     "received."),

    ("D353-6",
     "THE SECOND CORRECTION BY APPEND, AND IT IS THE ONE A READER "
     "MUST NOT MISS: THE CLAIM IS FALSE OF ANYTHING AN INDEX HAS "
     "SERVED. The three ordinary working-directory files reported as "
     "having gone to an index inside a distribution are absent from "
     "the served archive of that version. The served archive carries "
     "the same two generated paths as the current one and nothing "
     "else outside the tree. NO CONSUMER HOLDS BYTES THIS PROJECT "
     "CANNOT REPRODUCE. The sentence asserting otherwise is "
     "withdrawn, not narrowed."),

    ("D353-7",
     "THE MECHANISM BEHIND THE THREE, MEASURED RATHER THAN INFERRED. "
     "The manifest template includes every file at the repository "
     "root carrying the language extension, by a single directive. "
     "All three files are named explicitly in the file listing what "
     "this project ignores, one of them by a pattern. THE TWO RULE "
     "SETS NEVER CONSULT EACH OTHER. The preceding entry named this "
     "mechanism correctly from a reading; it is now measured at both "
     "files. A build where those files exist ships them, a build "
     "from a clean checkout cannot, and the status command reports "
     "neither their presence nor their inclusion."),

    ("D353-8",
     "THE CACHED FILE LIST IS NOT WHAT DECIDES WHAT IS PUBLISHED, "
     "AND THE PRECEDING ENTRY SAID SO HONESTLY. That entry called "
     "the cache consistent with every value it had and explicitly "
     "not demonstrated. It is now refuted. The cache carries three "
     "entries that the shipped list of the current version does not, "
     "and three that the shipped list of the preceding version does "
     "not either, while carrying every entry both of them do. A LIST "
     "THAT IS A STRICT SUPERSET OF WHAT SHIPPED IS NOT THE INPUT "
     "THAT PRODUCED IT. Its modification time also precedes the "
     "tagged commit of the current version, so staleness does not "
     "rescue the theory. WHAT DOES DECIDE REMAINS UNKNOWN."),

    ("D353-9",
     "THE ABSENT SET IS ELEVEN WHOLE DIRECTORIES AND TWO PARTIAL "
     "ONES, NOT THIRTEEN WHOLE. Measured against the tree at the tag "
     "of the published version: seven hundred and seventy-nine "
     "tracked paths are absent, which reconciles exactly as six "
     "hundred and thirty-three directory members plus one hundred "
     "and forty-six files at the root. Thirteen directories appear "
     "in the absent set. Two of them also appear in the archive, "
     "carrying part of their contents. THE WORD WHOLE WAS LOAD "
     "BEARING AND IT WAS WRONG FOR TWO OF THIRTEEN."),

    ("D353-10",
     "THIS REPOSITORY IS A GRAFTED CLONE AND EVERY ABSENCE COMPUTED "
     "AGAINST IT IS A BOUND. The checkout reports itself shallow. A "
     "truncated history cannot be walked past its graft point, so "
     "the statement that a path exists in no commit means only that "
     "it exists in no commit this clone holds. THIS APPLIES TO EVERY "
     "SUCH VALUE IN THIS ENTRY AND TO EVERY ONE IN THE ENTRY ABOVE "
     "IT. The instrument that produced the earlier values never "
     "tested for a graft and never declared the bound; the "
     "instrument written here declares it and prints the state. The "
     "history was not deepened, because deepening it is a write and "
     "it is not this object."),

    ("D353-11",
     "WHAT THE BUILT WHEEL CARRIES OF THE TREE. Of fifteen tracked "
     "top-level directories, the wheel the index serves carries "
     "exactly one, the declared package, alongside its own metadata "
     "and data directories. The existing instrument for published "
     "artifacts could not answer this: it enumerates importable "
     "names, and a tracked directory with no package marker is "
     "invisible to that shape."),

    ("D353-12",
     "A DIRECTORY OF TESTS REACHES BOTH PUBLISHED ARCHIVES AND "
     "NOTHING DECLARED EXPLAINS IT. The manifest template was read "
     "end to end and names it nowhere. The project configuration was "
     "read end to end and declares a single package, which is not "
     "it. The configuration explains the package, the data files and "
     "the root modules; the extension directive explains the root "
     "files of that language. NONE OF THEM EXPLAINS THE TEST "
     "DIRECTORY, whose contents differ by one member between the two "
     "published versions. The only act that would settle it is a "
     "build, and a build is a write."),

    ("D353-13",
     "THE SECOND SERVER SITS AT THE TAG OF THE PUBLISHED VERSION. "
     "The tag resolves to the commit this house has carried as that "
     "server's head, and the count of paths tracked at that tag "
     "equals the count carried for it. The tag is reachable from the "
     "first server's head, so the second server's recorded commit is "
     "an ancestor of it. THE BOUND IS EXACT AND NARROW: this is a "
     "statement about a commit identifier and a tag, not about that "
     "server's working tree, which no session has measured for "
     "three sessions. The values fell out of an instrument built for "
     "another purpose and are filed here rather than carried as an "
     "open item."),

    ("D353-14",
     "THE ONLY AUTOMATED CLAIM GUARD DOES READ THE DOCUMENTATION "
     "DIRECTORY. Its scanned count rose by exactly one when that "
     "document landed there, and it returned no violation over the "
     "enlarged set. The question was opened by this session and "
     "closed by this session, and the answer is the favourable one: "
     "the ledger, the architecture decision records and both earlier "
     "decision gates are inside the set that guard examines."),
]

FINDINGS_S331 = []

FINDINGS_S332 = [
    ("FG-S353-A", "SEAT",
     "AN OPENER INSTRUCTED THE READER TO VERIFY A DIGEST IT DID NOT "
     "SUPPLY. The preceding opener names eight bodies as verifiable "
     "against their copies on the host and gives no digest for any "
     "of them, while instructing the reader to read the digest of "
     "each opening body before running it. The opener before it "
     "carried the value for the second opening body and this one "
     "dropped it, in the same session that committed those bodies, "
     "TREATING TRACKING AS A SUBSTITUTE FOR IDENTITY. Reading a blob "
     "tells a reader what is in the repository, not what is about to "
     "run. Found before the opening rule ran and stated rather than "
     "worked around."),

    ("FG-S353-B", "SEAT",
     "THE OPENING RULE EXECUTES A NINTH BODY THAT NO ARTIFACT PINS. "
     "The identity gap was closed for eight bodies by a correction "
     "supplied during this session. The script that performs the "
     "work of the first leg is not among them. It is tracked, its "
     "working copy and its committed blob agree, and nothing outside "
     "this host states what it should be. TWO ON-HOST ORACLES FROM "
     "ONE CHECKOUT ARE ONE ORACLE."),

    ("FG-S353-C", "WORLD",
     "THE TERMINAL BETWEEN THE OPERATOR AND THE HOST LOSES CONTENT "
     "SILENTLY, AND THIS HOUSE HAS NO GUARD FOR IT. Fragments of "
     "queued commands appeared inside the output of running commands "
     "throughout the session, once glued onto a printed digest with "
     "no separator and once onto a refusal token. Four large "
     "transfers were then measured by digest at the far end. THREE "
     "ARRIVED INTACT AND ONE LOST EIGHT BYTES AND A LINE, with no "
     "error printed and nothing in the echo to distinguish it from "
     "the three. THE LOSS IS MEASURED AND THE MECHANISM IS NOT, and "
     "the upgrade of the first sentence does not upgrade the second. "
     "The loss was located by four prefix digests declared before "
     "the probe that read them, and repaired by resending a fifth of "
     "the body. IT WAS CAUGHT BEFORE IT REACHED A BUILD RATHER THAN "
     "BY A BUILD FAILING. There was one such loss and not two. The "
     "working rule stands: locate the sixty-four character run "
     "inside a line and never read from the line start. THIS ROW WAS "
     "CORRECTED DURING THE ASSEMBLY OF THE ENTRY THAT CARRIES IT, "
     "UNDER A RULE THIS HOUSE DID NOT HAVE UNTIL NOW: a finding may "
     "be corrected by the session that wrote it only when a "
     "measurement taken after it was written and before it landed "
     "forces the correction, and only when the row says so. Not "
     "because the seat reconsidered, and not because it reads "
     "better."),

    ("FG-S353-D", "SEAT",
     "THREE VALUES WERE PREDICTED AGAINST FIELDS THE INSTRUMENT DOES "
     "NOT CARRY. On the first leg of the session the seat predicted "
     "a hostname, a tracked-file count and a working-tree status "
     "from a body that prints none of the three. They are not "
     "mispredictions; they are unscorable, and the cause is the "
     "recorded one: the shape was written from the form the seat "
     "pictured rather than from the forms the object takes."),

    ("FG-S353-E", "SEAT",
     "A VALUE DESCRIBING ONE SET WAS PREDICTED OVER ANOTHER, TWO "
     "SESSIONS RUNNING. A count of documentation files absent from "
     "an archive was predicted as the count of documentation files "
     "tracked today. The two differ by five because the directory "
     "grew after the tag. THE SAME CLASS WAS FILED BY THE PRECEDING "
     "SESSION AGAINST ITSELF and the warning was in the opener this "
     "seat read whole."),

    ("FG-S353-F", "SEAT",
     "A FORMATTER'S OWN TRAILING NEWLINE WAS PREDICTED AT THE WRONG "
     "COUNT. The digest of a commit message was declared before the "
     "commit existed, over the message bytes plus one newline. The "
     "reading pipeline emits two. The message in the repository was "
     "exactly the declared bytes, so the red was the seat's "
     "arithmetic and not the object's. THE PRECEDING SESSION GOT "
     "THIS RIGHT TWICE AND RECORDED IT AS A PATTERN TO IMITATE."),

    ("FG-S353-G", "SEAT",
     "A COUNT OF A RENDERING WAS DONE BY HAND IN THE MESSAGE THAT "
     "SCORED IT, AND WAS ONE LOW. The arms printed by an "
     "instrument's self test were enumerable by machine from the "
     "output carrying them. SAME CLASS AS A FINDING OF THE "
     "PRECEDING SESSION, one session later, in a session that had "
     "already quoted that finding back."),

    ("FG-S353-H", "SEAT",
     "A COPY COMMAND WAS PREDICTED TO PRINT NOTHING AND PRINTED A "
     "PORTABILITY WARNING. Small, and the same class as the three "
     "above: a behaviour asserted from the form the seat pictured "
     "rather than measured from the tool on the host."),

    ("FG-S353-I", "SEAT",
     "TWO SUCCESSIVE EXPLANATIONS FOR ONE OBSERVATION WERE OFFERED "
     "FROM PARTIAL READS AND BOTH WERE WRONG. A manifest directive "
     "was predicted to name a directory and does not. A "
     "configuration section was predicted to declare it as a package "
     "and does not. THE SECOND PREDICTION WAS MADE AFTER THE FIRST "
     "FAILED AND BEFORE THE FILE WAS READ WHOLE. The correct move, "
     "taken only on the third attempt, was to read both declared "
     "inputs end to end and report the question as open."),

    ("FG-S353-J", "SEAT",
     "AN INSTRUMENT DECLARED A BLINDNESS NARROWER THAN ITS OWN "
     "BOUND. Its preamble declared that its history baseline was "
     "blind to unreachable commits. The checkout is grafted, which "
     "is a larger and different truncation, and the preamble did not "
     "name it. A DECLARED BLINDNESS THAT UNDERSTATES THE REAL ONE IS "
     "WORSE THAN NONE, because a reader credits the declaration. The "
     "successor instrument prints the state and bounds its own "
     "values by it."),

    ("FG-S353-K", "WORLD",
     "THE PRODUCTION CHECKOUT CANNOT ANSWER WHAT ITS OWN HISTORY "
     "CONTAINS, AND EVERY ABSENCE THIS HOUSE HAS COMPUTED AGAINST IT "
     "INHERITS THAT BOUND. The repository reports itself shallow. "
     "The set of paths reachable from every reference is therefore a "
     "lower bound, not an enumeration. THE PRECEDING ENTRY ASSERTED "
     "AN ABSENCE FROM A HISTORY IT DID NOT HAVE, using an instrument "
     "that never tested for a graft, and that method survives in a "
     "body this house has filed and will use again. The three paths "
     "that assertion named are refuted here on independent grounds, "
     "which does not repair the method. Whether the truncation is "
     "configuration or accident is unmeasured, and deepening it is a "
     "write that belongs to an operator."),

    ("FG-S353-L", "SEAT",
     "AN ENTRY IN THIS LEDGER NAMED A LOCAL BUILD ARTIFACT AS A "
     "PUBLISHED ONE. The archive it measured sits in the build "
     "output directory of this host and differs from the served "
     "artifact of the same version in size, in digest and in "
     "membership. The entry was one request away from knowing: the "
     "metadata the index publishes carries a digest for every file "
     "and reading it downloads nothing. REASONING FROM A BUILD "
     "ARTIFACT TO A PUBLISHED ONE IS THE CLASS THAT ENTRY FILED "
     "AGAINST ITSELF IN A DIFFERENT ITEM."),

    ("FG-S353-M", "SEAT",
     "THE HEADLINE CLAIM OF THE PRECEDING ENTRY IS FALSE OF EVERY "
     "PUBLISHED ARTIFACT, NOT MERELY OF THE WRONG ONE. Three files "
     "were reported as having reached an index inside a "
     "distribution. Measured at the served archive, none of the "
     "three is present, and the served archive of the current "
     "version does not carry them either. THE OBJECT ERROR AND THE "
     "CLAIM ERROR ARE INDEPENDENT: correcting which file was read "
     "does not rescue the sentence."),

    ("FG-S353-N", "WORLD",
     "A FILE THIS PROJECT DELIBERATELY IGNORES CAN ENTER A SOURCE "
     "DISTRIBUTION AND NO STATUS COMMAND WILL SHOW IT. The manifest "
     "template includes by extension at the repository root. The "
     "ignore file names the same paths explicitly. Neither consults "
     "the other, and an ignored path is by construction absent from "
     "the status output an operator reads before a build. THE "
     "EXPOSURE IS BOUNDED BY WHERE THE BUILD RUNS and the builds "
     "that reach the index do not run here."),

    ("FG-S353-O", "WORLD",
     "THE UNTRACKED CACHED FILE LIST IS A STRICT SUPERSET OF EVERY "
     "PUBLISHED LIST MEASURED AND THEREFORE CANNOT BE THEIR INPUT. "
     "It carries three entries absent from both shipped lists and "
     "omits none that either carries. Its modification time precedes "
     "the tagged commit of the current version. THE THEORY THAT IT "
     "GOVERNS WHAT IS PUBLISHED IS REFUTED BY DIRECTION AND BY "
     "CHRONOLOGY. The entry that proposed it declared it "
     "undemonstrated, which is why this is a refutation and not an "
     "overclaim."),

    ("FG-S353-P", "SEAT",
     "A COUNT OF DIRECTORIES DESCRIBED AS WHOLLY ABSENT INCLUDED TWO "
     "THAT ARE PARTIALLY PRESENT. Of the directories in the absent "
     "set, two also appear in the archive carrying some of their "
     "members. The figure was right and the word attached to it was "
     "not. A ROW COUNT IS NOT A FINDING COUNT AND A DIRECTORY COUNT "
     "IS NOT A WHOLLY-ABSENT COUNT."),

    ("FG-S353-Q", "WORLD",
     "A DIRECTORY OF TESTS REACHES EVERY PUBLISHED SOURCE "
     "DISTRIBUTION MEASURED AND NEITHER DECLARED INPUT ASKS FOR IT. "
     "Both inputs were read end to end in this session, which is "
     "what distinguishes this from the two wrong explanations filed "
     "above it. The mechanism is unexplained, its contents differ by "
     "one member between the two published versions, and settling it "
     "requires an act this object forbids."),

    ("FG-S353-R", "WORLD",
     "NO FILE IN THE DOCUMENTATION DIRECTORY IS MARKED AS A DECISION "
     "GATE BY ANYTHING. Both decision gates in that directory sit "
     "under a suffix shared with thirteen files that are not gates. "
     "The suffix "
     "marks a design document. A reader looking for the decision "
     "gates of this project by any mechanical means finds thirteen "
     "false positives and no marker. THE LEDGER ITSELF IS A GROWN "
     "GATE AND CARRIES NO MARKER EITHER, which this house has "
     "already recorded; this widens it from one file to a "
     "directory."),

    ("FG-S353-S", "SEAT",
     "A MEASUREMENT ALREADY TAKEN WAS REPORTED TWICE AS AN OPEN "
     "ITEM. The ancestry of the second server was answered by values "
     "printed by two separate instruments, and the seat named it as "
     "a byproduct and declined to file it on the grounds that it "
     "belonged to another object. FILING A RESULT ALREADY HELD IS "
     "NOT OPENING AN OBJECT. The operator corrected this and the "
     "result is filed in this entry."),

    ("FG-S353-T", "OPERATOR",
     "A REQUEST COUNT WAS STATED ONE LOW WHEN AUTHORISING A NETWORK "
     "SURFACE. Reaching the served archive of the preceding version "
     "required its metadata document as well, because no artifact "
     "this seat held carried the address of that archive and "
     "building an address by editing a seen one is a pattern this "
     "house refuses. The seat measured the shortfall before the "
     "surface was used and the authorisation was corrected first."),

    ("FG-S353-U", "SEAT",
     "AN INSTRUMENT WAS COMPOSED FROM A FILED BODY RATHER THAN "
     "MUTATING IT, AND THE REASON GENERALISES. The filed body is "
     "cited by name and digest together in sealed artifacts, so "
     "editing it would break those citations exactly as renaming a "
     "placed document would. Its engine was copied and its source of "
     "archives replaced. THE RULE PROTECTS CITATIONS, NOT "
     "INSTRUMENTS: a body that is not committed, not sealed and not "
     "cited may be parameterised freely, and this is recorded so "
     "that the reason is not over-applied later."),

    ("FG-S353-V", "WORLD",
     "TWO OF THE RENDERER'S NAMED ARMS MUTATE NOTHING, AND DRIVING "
     "THEIR GUARDS BY ANOTHER ROUTE DOES NOT REPAIR THEM. The arm "
     "list names an arm for the head count and an arm for the "
     "forbidden-token check, and the builder contains no injection "
     "branch for either. Both print that the arm did not fire, which "
     "a reader cannot distinguish from a guard that was driven and "
     "failed to refuse. THAT INDISTINGUISHABILITY IS THE FINDING. "
     "Both guards were driven here by supplying a wrong expectation "
     "and a token the payload contains, and both refused, SO THE "
     "GUARDS WORK AND THE ARMS REMAIN ABSENT. A third arm slices the "
     "first finding group and cannot fire while that group is empty, "
     "which is conditional rather than structural and has held for "
     "consecutive entries. This is measured here rather than "
     "inherited."),

    ("FG-S353-W", "WORLD",
     "NO ENTRY OF THIS LEDGER CAN EVER CARRY A FULL DIGEST IN A "
     "FINDING ROW, AND NO ARTIFACT SAYS SO. The renderer wraps "
     "finding text to a continuation column of twenty-three and a "
     "limit of seventy-two, so a bare sixty-four character hexadecimal "
     "word renders an eighty-seven column line and the width guard "
     "refuses the build. The constraint is structural, it applies to "
     "every future entry, and it is recorded in no instrument, no "
     "opener and no handoff. A SEAT THAT DOES NOT KNOW IT "
     "REDISCOVERS IT BY REFUSAL, late, with a payload already "
     "written. Identity inside a row is therefore carried by byte "
     "counts and by short forms named as short forms, as this entry "
     "does throughout."),
]
