#!/bin/sh
# G2_R0_S372 THE SECOND OPENING BODY, GUARDED. SUCCESSOR OF G2_R0_S349,
# BUILT FROM ITS BYTES. IT DIFFERS ONLY BY FG-S370-A TO -F AND BY ONE
# EXIT CODE PER REFUSAL CLASS, 40 TO 57, WITH TOKENS OF ITS OWN PREFIX.
# EVERY OTHER LEG KEEPS ITS NAME, SHAPE AND VALUE. L7 IS UNCHANGED.
# WHAT IT READS AND WHAT IT WRITES ARE DECLARED IN L0 AND L8.
# T5 SELF CHECK RUNS BEFORE ANY cd.

SELF="$0"
if [ ! -f "$SELF" ] ; then
  echo "REFUSE T5_NOT_A_FILE"
  echo "SELF $SELF"
  exit 40
fi
if [ -z "$1" ] ; then
  echo "REFUSE T5_NO_DIGEST_ARGUMENT"
  echo "USAGE sh FILE EXPECTED_SHA256 [REPO_ROOT]"
  exit 41
fi
T5C=$(sha256sum "$SELF" | cut -d' ' -f1)
if [ "$T5C" != "$1" ] ; then
  echo "REFUSE T5_DIGEST_MISMATCH"
  echo "COMPUTED $T5C"
  echo "GIVEN    $1"
  exit 42
fi
echo "T5_OK $T5C"

DOCREL="docs/GLM_SUPERSESSION_DESIGN.md"
POSTOK='__s323_readme_version_current_v1__'

echo "== L0 SET, SHAPE, BLINDNESS. DECLARED BEFORE ANY VALUE."
echo "READ SET, EVERY PLACE A LEG READS: this file; the root given as"
echo "  argument two, or else the two default roots; the index, through"
echo "  ls-files and status; HEAD and its objects; the working tree: the"
echo "  gate document, README.md, the test file, six generator files,"
echo "  claims.toml, and every tracked file through git grep; for the one"
echo "  negative of G0, every file under the root outside .git, untracked"
echo "  and ignored files included; the local ref origin/main and its"
echo "  blob of the gate document; the local tags; the remote named"
echo "  origin, over the network, through one fetch, and FETCH_HEAD after"
echo "  it; /tmp/nous_s324; and in L7 whatever the suite, the claim lint"
echo "  and the mirror check read, not bounded here, the mirror check"
echo "  reading two fixed paths whatever the root is."
echo "WRITE SET: the fetch writes FETCH_HEAD, even when it fails, the"
echo "  remote tracking refs and their reflogs, the tags it follows, new"
echo "  objects, and whatever automatic maintenance git runs after a"
echo "  fetch. Both status calls run with optional locks off and write no"
echo "  index. L7 writes what the suite writes, not bounded here."
echo "SHAPE: anchored line patterns and fixed strings as written."
echo "BLIND TO: a different indent, a fenced block, any phrase split"
echo "  across a line break, any reference built at runtime, and any"
echo "  claim written in a file that is not tracked."
echo "THIS BODY COMPARES NOTHING ACROSS SESSIONS. It prints. The"
echo "  comparison is the reader's and is done off host. THE PREAMBLE"
echo "  OF THE SUPERSEDED PASTE CLAIMED IT COMPARED AGAINST AN OPENER"
echo "  SECTION. IT DID NOT, AND NEITHER DOES THIS."
echo "PROVENANCE: G2_R0_S349 was authored in the session after S348;"
echo "  this successor in S372, from those bytes. It pins no value"
echo "  from any earlier session except the two fixed strings it uses"
echo "  as positive controls, which are named in G0 and driven."
echo "== L0B STOP CONDITION SHAPE. DOC_SHA UNCHANGED FROM THE PRECEDING"
echo "   SEAL IS THE WHOLE CONDITION. The per namespace legs are"
echo "   READINGS and are not a stop condition: an occupied namespace"
echo "   cannot become empty again, and a leg that can only pass is"
echo "   not a condition. The digest covers every change and is the"
echo "   only side that does."

echo "== G0 GUARDS. EVERY ENGINE IS DRIVEN POSITIVE AND NEGATIVE"
echo "   BEFORE ANY VALUE IS PRINTED. AN EMPTY RESULT FROM A BLIND"
echo "   ENGINE READS EXACTLY LIKE A DISCOVERY. THIS IS THE DEFECT"
echo "   THE SUPERSEDED PASTE DEMONSTRATED AT S329_HEAD_LINE."
echo "HOSTNAME $(hostname 2>/dev/null)"
echo "DATE_UTC $(date -u 2>/dev/null)"

REPO=""
if [ -n "$2" ] ; then
  if [ -d "$2/.git" ] ; then
    REPO="$2"
  else
    echo "REFUSE G2S372_GIVEN_ROOT_NOT_A_REPO"
    echo "GIVEN [$2]"
    echo "a given root is used or refused; it never falls through"
    exit 43
  fi
else
  for d in "/opt/aetherlang_agents/nous" "/opt/neuroaether/nous" ; do
    if [ -d "$d/.git" ] ; then
      REPO="$d"
      break
    fi
  done
fi
if [ -z "$REPO" ] ; then
  echo "REFUSE G2S372_NO_REPO_ROOT"
  echo "TRIED [/opt/aetherlang_agents/nous] [/opt/neuroaether/nous]"
  exit 44
fi
echo "REPO_ROOT $REPO"

GH=$(git -C "$REPO" rev-parse --verify --quiet HEAD 2>/dev/null)
echo "GIT_HEAD [$GH]"
if [ -z "$GH" ] ; then
  echo "REFUSE G2S372_GIT_BLIND git cannot read this repository here"
  echo "an empty result from a blind git reads exactly like a discovery"
  exit 45
fi
if ! printf '%s' "$GH" | grep -q -E '^[0-9a-f]{40}$' ; then
  echo "REFUSE G2S372_GIT_HEAD_NOT_A_COMMIT_ID"
  echo "GOT [$GH]"
  echo "git prints the literal word HEAD on stdout in a repository with"
  echo "no commits; a guard that accepts it is not a guard"
  exit 46
fi
NT=$(git -C "$REPO" ls-files 2>/dev/null | wc -l)
echo "TRACKED_FILES_MUST_BE_NONZERO $NT"
if [ "$NT" = "0" ] ; then
  echo "REFUSE G2S372_GIT_BLIND tracked file count is zero"
  exit 45
fi

DOCABS="$REPO/$DOCREL"
if [ ! -f "$DOCABS" ] ; then
  echo "REFUSE G2S372_GATE_DOC_ABSENT $DOCREL"
  exit 47
fi
DB=$(wc -c < "$DOCABS")
echo "GATE_DOC_BYTES_MUST_BE_NONZERO $DB"
if [ "$DB" = "0" ] ; then
  echo "REFUSE G2S372_GATE_DOC_EMPTY"
  exit 48
fi

GEP=$(grep -c -E '^  - S[0-9]' "$DOCABS" 2>/dev/null)
if [ -z "$GEP" ] ; then
  GEP=0
fi
echo "GREP_E_POSITIVE_MUST_BE_NONZERO $GEP"
if [ "$GEP" = "0" ] ; then
  echo "REFUSE G2S372_GREP_E_BLIND the head shape returns nothing"
  exit 49
fi
GEN=$(grep -c -E '^  - ZQ[0-9]' "$DOCABS" 2>/dev/null)
if [ -z "$GEN" ] ; then
  GEN=0
fi
echo "GREP_E_NEGATIVE_MUST_BE_ZERO $GEN"
if [ "$GEN" != "0" ] ; then
  echo "REFUSE G2S372_GREP_E_NEGATIVE_FIRED"
  exit 50
fi

AWP=$(awk '/^ {12}FG-S[0-9]/{c++} END{print c+0}' "$DOCABS" 2>/dev/null)
if [ -z "$AWP" ] ; then
  AWP=0
fi
echo "AWK_POSITIVE_MUST_BE_NONZERO $AWP"
if [ "$AWP" = "0" ] ; then
  echo "REFUSE G2S372_AWK_BLIND the strict finding shape returns nothing"
  exit 51
fi
AWN=$(awk '/^ {12}ZQ-S[0-9]/{c++} END{print c+0}' "$DOCABS" 2>/dev/null)
if [ -z "$AWN" ] ; then
  AWN=0
fi
echo "AWK_NEGATIVE_MUST_BE_ZERO $AWN"
if [ "$AWN" != "0" ] ; then
  echo "REFUSE G2S372_AWK_NEGATIVE_FIRED"
  exit 52
fi

if [ ! -f "$REPO/README.md" ] ; then
  echo "REFUSE G2S372_README_ABSENT"
  exit 53
fi
GFP=$(grep -c -F -e "$POSTOK" "$REPO/README.md" 2>/dev/null)
if [ -z "$GFP" ] ; then
  GFP=0
fi
echo "GREP_F_POSITIVE_MUST_BE_NONZERO $GFP"
if [ "$GFP" = "0" ] ; then
  echo "REFUSE G2S372_GREP_F_BLIND the pinned marker is not where it was"
  exit 54
fi
NEGTOK=$(printf '%s' "$POSTOK" | sed 's/.$/Q/')
if [ "$NEGTOK" = "$POSTOK" ] ; then
  NEGTOK=$(printf '%s' "$POSTOK" | sed 's/.$/R/')
fi
GFN=$(grep -r -l -F -e "$NEGTOK" "$REPO" --exclude-dir=.git 2>/dev/null | wc -l)
echo "GREP_F_NEGATIVE_MUST_BE_ZERO $GFN"
if [ "$GFN" != "0" ] ; then
  echo "REFUSE G2S372_GREP_F_NEGATIVE_FIRED"
  exit 55
fi

echo "GUARDS_ALL_GREEN five engines driven, three positive, three"
echo "  negative, and neither the git leg nor the document leg can"
echo "  return an empty string that a reader mistakes for an absence."

cd "$REPO" || { echo "REFUSE G2S372_CD_FAILED" ; exit 56 ; }

echo "== L1 GIT"
git fetch origin --quiet
FRC=$?
printf 'FETCH_RC %s\n' "$FRC"
FH=$(git rev-parse --git-path FETCH_HEAD)
if [ -f "$FH" ] ; then
  printf 'FETCH_HEAD_BYTES %s\n' "$(wc -c < "$FH")"
  printf 'FETCH_HEAD_MTIME %s\n' "$(date -u -r "$FH" '+%Y-%m-%dT%H:%M:%S.%NZ')"
  printf 'FETCH_HEAD_MAIN_LINES %s\n' "$(awk -F '\t' '$3 ~ /^branch .main. of /{c++} END{print c+0}' "$FH")"
  awk -F '\t' '$3 ~ /^branch .main. of /{printf "FETCH_HEAD_MAIN %s [%s]\n", $1, $2}' "$FH"
else
  echo "FETCH_HEAD_ABSENT"
fi
if [ "$FRC" != "0" ] ; then
  echo "REFUSE G2S372_FETCH_FAILED"
  echo "after a failed fetch the remote ref is not a reading"
  exit 57
fi
printf 'HEAD %s\n' "$(git rev-parse --short HEAD)"
printf 'ORIGIN %s\n' "$(git rev-parse --short origin/main)"
printf 'AHEAD %s\n' "$(git rev-list --count origin/main..HEAD)"
printf 'BEHIND %s\n' "$(git rev-list --count HEAD..origin/main)"
git log --oneline -3 | cat

echo "== L1B THE TAG, AUTO ENUMERATED BY TWO ORACLES. THE SUPERSEDED"
echo "   PASTE HARDCODED ONE TAG AND WOULD HAVE COUNTED FROM IT AFTER"
echo "   THE NEXT ONE WAS CUT, WHILE scripts/rule0.sh ENUMERATED. TWO"
echo "   ORACLES THAT AGREE TODAY AND DIVERGE SILENTLY LATER ARE ONE"
echo "   ORACLE WITH A DELAY."
TAGD=$(git describe --tags --abbrev=0 2>/dev/null)
TAGV=$(git tag --sort=-v:refname 2>/dev/null | head -1)
printf 'LATEST_TAG_DESC [%s]\n' "$TAGD"
printf 'LATEST_TAG_VSORT [%s]\n' "$TAGV"
if [ -z "$TAGD" ] ; then
  echo "TAG_ABSENT_UNDER_DESCRIBE no distance is computed from it"
else
  if git merge-base --is-ancestor "$TAGD" HEAD 2>/dev/null ; then
    echo "TAG_DESC_REACHABLE_FROM_HEAD YES"
    printf 'AHEAD_OF_TAG_DESC %s\n' "$(git rev-list --count "$TAGD"..HEAD 2>/dev/null)"
  else
    echo "TAG_DESC_REACHABLE_FROM_HEAD NO"
    echo "AHEAD_OF_TAG_DESC WITHHELD A DISTANCE FROM AN UNREACHABLE TAG IS NOT A DISTANCE"
  fi
fi
if [ -z "$TAGV" ] ; then
  echo "TAG_ABSENT_UNDER_VSORT no distance is computed from it"
else
  if git merge-base --is-ancestor "$TAGV" HEAD 2>/dev/null ; then
    echo "TAG_VSORT_REACHABLE_FROM_HEAD YES"
    printf 'AHEAD_OF_TAG_VSORT %s\n' "$(git rev-list --count "$TAGV"..HEAD 2>/dev/null)"
  else
    echo "TAG_VSORT_REACHABLE_FROM_HEAD NO"
    echo "AHEAD_OF_TAG_VSORT WITHHELD A DISTANCE FROM AN UNREACHABLE TAG IS NOT A DISTANCE"
  fi
fi
if [ -z "$TAGD" ] ; then
  echo "TAG_ORACLES_UNDECIDABLE both sides are empty and two silences"
  echo "  are not an agreement"
else
  if [ -z "$TAGV" ] ; then
    echo "TAG_ORACLES_UNDECIDABLE one side is empty"
  else
    if [ "$TAGD" = "$TAGV" ] ; then
      echo "TAG_ORACLES_AGREE YES"
    else
      echo "TAG_ORACLES_AGREE NO, REACHABILITY AND VERSION ORDER DISAGREE"
    fi
  fi
fi
printf 'GIT_DESCRIBE_LONG %s\n' "$(git describe --tags 2>/dev/null)"
printf 'TAGS_TOTAL %s\n' "$(git tag 2>/dev/null | wc -l)"

echo "== L2 PORCELAIN"
GIT_OPTIONAL_LOCKS=0 git status --porcelain
printf 'PORCELAIN_LINES %s\n' "$(GIT_OPTIONAL_LOCKS=0 git status --porcelain | wc -l)"

echo "== L3 GATE DOC"
printf 'DOC_SHA %s\n' "$(sha256sum "$DOCREL" | cut -d' ' -f1)"
printf 'DOC_BLOB_ORIGIN_MAIN %s\n' "$(git rev-parse origin/main:"$DOCREL")"
printf 'DOC_BLOB_HEAD %s\n' "$(git rev-parse HEAD:"$DOCREL")"
printf 'DOC_LINES %s\n' "$(wc -l < "$DOCREL")"
printf 'DOC_BYTES %s\n' "$(wc -c < "$DOCREL")"
printf 'MAXLEN %s\n' "$(awk 'length>m{m=length}END{print m+0}' "$DOCREL")"
printf 'NONASCII_LINES %s\n' "$(LC_ALL=C grep -c '[^ -~]' "$DOCREL")"
printf 'TRAILWS_LINES %s\n' "$(grep -c -E '[ ]+$' "$DOCREL")"
for s in 344 343 340 339 338 337 336 335 334 333 332 331 330 329 328 327 326 325 324 323 322 ; do
  v=$(grep -n "^  - S$s" "$DOCREL" | cut -d: -f1)
  if [ -z "$v" ] ; then
    v="ABSENT_AND_THE_ENGINE_WAS_DRIVEN_IN_G0"
  fi
  printf 'S%s_HEAD_LINE %s\n' "$s" "$v"
done
for d in 344 343 340 339 338 337 336 335 334 333 332 331 330 329 328 327 326 325 324 323 ; do
  v=$(grep -c "^    D$d-" "$DOCREL")
  if [ -z "$v" ] ; then
    v=0
  fi
  printf 'D%s_ANCHORED %s\n' "$d" "$v"
done
printf 'DOC_WORKTREE_EQ_ORIGIN_MAIN_BLOB %s\n' "$(if [ "$(git cat-file -p origin/main:"$DOCREL" | sha256sum | cut -d' ' -f1)" = "$(sha256sum "$DOCREL" | cut -d' ' -f1)" ] ; then echo YES ; else echo NO ; fi)"

echo "== L3B HEADS AND FAMILIES, ENUMERATED. THE PINNED LEGS ABOVE ARE"
echo "   A NAME SWEEP OVER A SET THAT CAN SIMPLY BE ENUMERATED, AND"
echo "   THEY STOP AT S344. THIS LEG IS THE SECOND ORACLE AND DOES NOT"
echo "   REPLACE THEM."
printf 'HEADS_ENUMERATED %s\n' "$(grep -o -E '^  - S[0-9]+' "$DOCREL" | sed 's|^  - ||' | sort -u | tr '\n' ' ')"
printf 'HEADS_DISTINCT %s\n' "$(grep -o -E '^  - S[0-9]+' "$DOCREL" | sort -u | wc -l)"
printf 'D_FAMILIES_ENUMERATED %s\n' "$(grep -o -E '^    D[0-9]+-' "$DOCREL" | sed 's|^ *||' | sort -u | tr '\n' ' ')"

echo "== L4 EVERY ANCHOR FAMILY. R20. TWO SHAPES, THE SECOND DOES NOT REPLACE THE FIRST."
grep -o -E '^    D[0-9]+-' "$DOCREL" | sort | uniq -c
grep -o -E '^            FG-S[0-9]+-' "$DOCREL" | sort | uniq -c
printf 'STRICT_FG_OCC %s\n' "$(grep -c '^            FG-S[0-9]' "$DOCREL")"
printf 'STRICT_A %s\n' "$(grep -c -E '^ {12}FG-S[0-9]' "$DOCREL")"
printf 'STRICT_B %s\n' "$(grep -c -E '^ {12}FG-S[0-9]+-[A-Z]' "$DOCREL")"
printf 'AWK_A %s\n' "$(awk '/^ {12}FG-S[0-9]/{c++} END{print c+0}' "$DOCREL")"
printf 'AWK_B %s\n' "$(awk '/^ {12}FG-S[0-9]+-[A-Z]/{c++} END{print c+0}' "$DOCREL")"

echo "== L4B STRICT DELTA LISTING. MUST BE EMPTY. AWK_A AND AWK_B EVIDENCE THAT THE ENGINE SPEAKS."
awk '($0 ~ /^ {12}FG-S[0-9]/) != ($0 ~ /^ {12}FG-S[0-9]+-[A-Z]/){print NR": "substr($0,1,44)}' "$DOCREL"
printf 'LABELLED_FG %s\n' "$(grep -c -E '^ {12}FG-S[0-9]+-[A-Z]+  (SEAT|WORLD)' "$DOCREL")"
printf 'STRICT_DUP_ROWS %s\n' "$(awk 'match($0,/^ {12}FG-S[0-9]+-[A-Z]+/){k=substr($0,13,RLENGTH-12); c[k]=c[k]" "NR} END{r=0; for(k in c){n=split(c[k],a," "); if(n>1) r++} print r}' "$DOCREL")"
printf 'OTHER_INDENT_LINES %s\n' "$(grep -n -E '^ +FG-S[0-9]+-[A-Z]+' "$DOCREL" | grep -c -v -E '^[0-9]+: {12}FG-S')"
for f in 344 343 340 339 338 337 336 335 334 333 332 ; do
  printf 'FG_S%s_STRICT %s\n' "$f" "$(grep -c -E "^ {12}FG-S$f-" "$DOCREL")"
done
printf 'LOOSE_FG_OCC %s\n' "$(grep -c -E '^ +FG-S[0-9]+-[A-Z]+' "$DOCREL")"
printf 'LOOSE_FG_DISTINCT %s\n' "$(grep -o -E '^ +FG-S[0-9]+-[A-Z]+' "$DOCREL" | sed -E 's|^ +||' | sort -u | wc -l)"
printf 'LOOSE_FG_FAMILIES %s\n' "$(grep -o -E '^ +FG-S[0-9]+-' "$DOCREL" | sed -E 's|^ +||' | sort -u | wc -l)"
printf 'HEADS_TOTAL %s\n' "$(grep -c '^  - S[0-9]' "$DOCREL")"
printf 'BLANK_BEFORE %s\n' "$(awk '/^  - S[0-9]/{if(NR>1&&p=="")c++} {p=$0} END{print c+0}' "$DOCREL")"
printf 'TEXT_BEFORE %s\n' "$(awk '/^  - S[0-9]/{if(NR>1&&p!="")c++} {p=$0} END{print c+0}' "$DOCREL")"
printf 'ANCHOR4_TOTAL %s\n' "$(grep -c -E '^    D[0-9]+-' "$DOCREL")"

echo "== L4C CODES ANYWHERE. SHAPE: the letters FG-S, digits, a hyphen and one or more capitals, matched ANYWHERE in a line with NO anchor. This set is wider than every anchored count above and replaces none of them. BLIND TO: a code split across a line break, and a code written in lower case."
printf 'CODES_ANYWHERE_OCC %s\n' "$(grep -o -E 'FG-S[0-9]+-[A-Z]+' "$DOCREL" | wc -l)"
printf 'CODES_ANYWHERE_DISTINCT %s\n' "$(grep -o -E 'FG-S[0-9]+-[A-Z]+' "$DOCREL" | sort -u | wc -l)"

echo "== L5 THE OBJECTS THE LAST TWO SESSIONS LANDED"
printf 'README_SHA %s\n' "$(sha256sum README.md | cut -c1-8)"
printf 'README_LINES %s\n' "$(wc -l < README.md)"
printf 'README_MARKER %s\n' "$(grep -c -F -e "$POSTOK" README.md)"
printf 'TESTFILE_SHA %s\n' "$(sha256sum tests/test_version_consistency.py | cut -c1-8)"
printf 'TESTFILE_LINES %s\n' "$(wc -l < tests/test_version_consistency.py)"
printf 'GEN_SHAS %s\n' "$(for f in build_vsa.py vsa_verifier.py mint_release_vsa.py provenance.py provenance_verifier.py scripts/cold_audit.py ; do sha256sum $f | cut -c1-8 ; done | tr '\n' ' ')"

echo "== L6 THE SURFACE, THE OPEN OBJECT"
printf 'MONITOR_ANY %s\n' "$(git grep -n -i -F -e 'is a monitor' -e 'remains a monitor' -- . | wc -l)"
printf 'FALSE_SUBJECT %s\n' "$(git grep -n -i -F -e 'NOUS is a monitor' -e 'NOUS remains a monitor' -- . | wc -l)"
printf 'NEW_SUBJECT %s\n' "$(git grep -n -i -F -e 'evidence layer is a monitor' -- . | wc -l)"
printf 'CLAIMLINT_ENFORCE_WORDS %s\n' "$(grep -c -i -F -e 'enforce' -e 'guard' -e 'gate' claims.toml)"
printf 'FLOOR_HITS_TRACKED %s\n' "$(git grep -n -F 'PYTEST_FLOOR' -- . | wc -l)"

echo "== L7 SUITE, LINT, MIRROR"
printf 'COLLECT_TESTS %s\n' "$(python3 -m pytest tests/ -q -p no:cacheprovider --collect-only 2>/dev/null | tail -1)"
printf 'COLLECT_BARE %s\n' "$(python3 -m pytest -q -p no:cacheprovider --collect-only 2>/dev/null | tail -1)"
python3 -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -2
LOUT=$(python3 scripts/claim_lint.py --config claims.toml --root .)
LRC=$?
printf 'LINT_RC %s\n' "$LRC"
printf '%s\n' "$LOUT" | grep -E 'scanned|violation'
MOUT=$(python3 scripts/served_mirror_check.py)
MRC=$?
printf 'MIRROR_RC %s\n' "$MRC"
printf '%s\n' "$MOUT" | tail -1
printf 'TMP_S324 %s\n' "$(ls -1 /tmp/nous_s324 2>/dev/null | tr '\n' ' ')"

echo "== L8 WHAT THIS RUN CANNOT SAY"
echo "It cannot say a pinned leg that printed ABSENT is a defect. It"
echo "  can say the engine spoke and the head is not there."
echo "It cannot say the two tag oracles will still agree tomorrow."
echo "It cannot say anything about a phrase split across two lines."
echo "It cannot say a served sentence is true. It reads the places"
echo "  named in L0."
echo "IT IS NOT WRITE FREE. The fetch writes FETCH_HEAD, the remote"
echo "  tracking refs and their reflogs, the tags it follows, objects"
echo "  and git's own maintenance; L7 writes what the suite writes."
echo "== END"
