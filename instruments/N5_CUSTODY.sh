#!/bin/sh
# N5 KEY CUSTODY BY ENUMERATION. READ ONLY. NO WRITE OF ANY KIND
# AND NO NETWORK CALL.
# SUPERSEDES N3, WHICH DECLARED SIX DIRECTORIES AND LEFT TWO THAT ITS
# OWN L5 FOUND UNMEASURED, AND WHOSE GIT GUARD ACCEPTED THE LITERAL
# WORD HEAD AS A COMMIT ID.
# SUPERSEDES THE N1 NAME SWEEP, WHICH UNDERCOUNTED TWICE OVER.
# NO KEY CONTENT IS PRINTED. DIGESTS ARE OFF UNLESS OPTED IN.
# T5 SELF CHECK RUNS BEFORE ANY cd.

SELF="$0"
if [ ! -f "$SELF" ] ; then
  echo "REFUSE T5_NOT_A_FILE"
  echo "SELF $SELF"
  exit 9
fi
if [ -z "$1" ] ; then
  echo "REFUSE T5_NO_DIGEST_ARGUMENT"
  echo "USAGE sh FILE EXPECTED_SHA256 EXPECTED_PIN [REPO_ROOT] [WITH_KEY_DIGESTS]"
  exit 9
fi
if [ -z "$2" ] ; then
  echo "REFUSE N5_NO_PIN_ARGUMENT"
  echo "USAGE sh FILE EXPECTED_SHA256 EXPECTED_PIN [REPO_ROOT] [WITH_KEY_DIGESTS]"
  exit 9
fi
T5C=$(sha256sum "$SELF" | cut -d' ' -f1)
if [ "$T5C" != "$1" ] ; then
  echo "REFUSE T5_DIGEST_MISMATCH"
  echo "COMPUTED $T5C"
  echo "GIVEN    $1"
  exit 9
fi
echo "T5_OK $T5C"

PIN="$2"
KDIG=0
if [ -n "$4" ] ; then
  if [ "$4" = "WITH_KEY_DIGESTS" ] ; then
    KDIG=1
  else
    echo "REFUSE N5_UNKNOWN_FLAG $4"
    echo "the only accepted value is WITH_KEY_DIGESTS"
    exit 9
  fi
fi

echo "== L0 SET, SHAPE, BLINDNESS. DECLARED BEFORE ANY VALUE."
echo "SET: every file in each DECLARED DIRECTORY below, enumerated, not"
echo "  name-matched. Plus tracked files of one repository."
echo "SHAPE: directory enumeration is the primary oracle. The TWO N1"
echo "  sweeps are modelled SEPARATELY as second oracles, by name only."
echo "  A is the word shapes. B is the key-extension shapes. B failed on"
echo "  DEPTH, not on name, and depth is tested in L4, not here."
echo "KEY_DIGESTS $KDIG"
if [ "$KDIG" = "0" ] ; then
  echo "  DIGESTS ARE OFF. NO KEY IS READ FOR ITS CONTENT. THEREFORE A"
  echo "  COPY CANNOT BE DISTINGUISHED FROM A COINCIDENCE OF NAME AND"
  echo "  SIZE. Cross-host equality is NOT decidable from this output."
else
  echo "  DIGESTS ARE ON BY EXPLICIT OPT IN. A digest reads bytes and"
  echo "  emits no plaintext. It is the identity a copy claim needs."
fi
echo "BLIND TO: every off-host copy, by construction. A file existing is"
echo "  not a copy being recoverable. An encrypted key is"
echo "  indistinguishable here from a usable one. A key outside every"
echo "  declared directory is found only by the weaker second oracle."
echo "THIS BODY COMPARES NOTHING ACROSS HOSTS. It prints. The"
echo "  comparison is the reader's and is done off host."

echo "== L1 HOST IDENTITY, SO TWO OUTPUTS CANNOT BE CONFUSED"
echo "HOSTNAME $(hostname 2>/dev/null)"
echo "UNAME $(uname -sr 2>/dev/null)"
echo "DATE_UTC $(date -u 2>/dev/null)"
echo "XDG_DATA_HOME [$XDG_DATA_HOME]"
echo "HOME [$HOME]"

echo "== L2 ROOT, GIT SENTINEL, CONTENT SENTINEL, NEGATIVE CONTROL"
CAND="$3 /opt/aetherlang_agents/nous /opt/neuroaether/nous"
REPO=""
for d in $CAND ; do
  if [ -d "$d/.git" ] ; then
    REPO="$d"
    break
  fi
done
if [ -z "$REPO" ] ; then
  echo "REFUSE N5_NO_REPO_ROOT"
  echo "TRIED $CAND"
  exit 9
fi
echo "REPO_ROOT $REPO"

GH=$(git -C "$REPO" rev-parse --verify --quiet HEAD 2>/dev/null)
echo "GIT_HEAD [$GH]"
if [ -z "$GH" ] ; then
  echo "REFUSE N5_GIT_BLIND git cannot read this repository here"
  echo "an empty result from a blind git reads exactly like a discovery"
  exit 9
fi
if ! printf '%s' "$GH" | grep -q -E '^[0-9a-f]{40}$' ; then
  echo "REFUSE N5_GIT_HEAD_NOT_A_COMMIT_ID"
  echo "GOT [$GH]"
  echo "git prints the literal word HEAD on stdout in a repository with"
  echo "no commits, and N3 accepted it"
  exit 9
fi
NT=$(git -C "$REPO" ls-files 2>/dev/null | wc -l)
echo "TRACKED_FILES_MUST_BE_NONZERO $NT"
if [ "$NT" = "0" ] ; then
  echo "REFUSE N5_GIT_BLIND tracked file count is zero"
  exit 9
fi

SENT=$(grep -c -F -e nous "$REPO/pyproject.toml" 2>/dev/null)
if [ -z "$SENT" ] ; then
  SENT=0
fi
echo "CONTENT_SENTINEL_MUST_BE_NONZERO $SENT"
if [ "$SENT" = "0" ] ; then
  echo "REFUSE N5_SENTINEL_BLIND"
  exit 9
fi

PINBAD=$(printf '%s' "$PIN" | sed 's/.$/Q/')
if [ "$PINBAD" = "$PIN" ] ; then
  PINBAD=$(printf '%s' "$PIN" | sed 's/.$/R/')
fi
NBAD=$(grep -r -l -F -e "$PINBAD" "$REPO" --exclude-dir=.git 2>/dev/null | wc -l)
echo "NEGATIVE_CONTROL_MUST_BE_ZERO $NBAD"
if [ "$NBAD" != "0" ] ; then
  echo "REFUSE N5_NEGATIVE_CONTROL_FIRED"
  exit 9
fi

echo "== L3 DECLARED DIRECTORIES, ENUMERATED WHOLE. PRIMARY ORACLE."
DIRS="/root/.local/share/nous/keys /root/.config/nous /root/.nous /etc/nous /etc/aetherproof /root/.local/share/nous /etc/aether-shield/keys /root/nous-toolgap-20260904/keys"
TOTAL=0
MISSED=0
for d in $DIRS ; do
  if [ ! -d "$d" ] ; then
    echo "DIR_ABSENT  $d"
    continue
  fi
  echo "DIR_PRESENT $d"
  stat -c '  DIRMODE %a %U:%G' "$d" 2>/dev/null
  for f in "$d"/* ; do
    if [ ! -f "$f" ] ; then
      continue
    fi
    TOTAL=$(expr $TOTAL + 1)
    b=$(basename "$f")
    sz=$(stat -c '%s' "$f" 2>/dev/null)
    pv=$(grep -c -F -e 'PRIVATE KEY' "$f" 2>/dev/null)
    if [ -z "$pv" ] ; then
      pv=0
    fi
    pb=$(grep -c -F -e 'PUBLIC KEY' "$f" 2>/dev/null)
    if [ -z "$pb" ] ; then
      pb=0
    fi
    hp=$(grep -c -F -e "$PIN" "$f" 2>/dev/null)
    if [ -z "$hp" ] ; then
      hp=0
    fi
    kind=OTHER
    if [ "$pv" != "0" ] ; then
      kind=PEM_PRIVATE
    fi
    if [ "$sz" = "32" ] ; then
      kind=SEED32_SHAPE
    fi
    case "$b" in
      *operator*key*|*signing*|*rekor*|*cosign*|*ed25519*|*.jwk|*nous*key*)
        sa=A_MATCH ;;
      *)
        sa=A_MISS
        MISSED=$(expr $MISSED + 1) ;;
    esac
    case "$b" in
      *.pem|*.key|*.pub|*.asc|*.gpg|*.p12|id_*)
        sb=B_MATCH ;;
      *)
        sb=B_MISS ;;
    esac
    seen="$sa $sb"
    echo "  FILE $b"
    echo "    $(stat -c 'MODE %a OWNER %U:%G SIZE %s MTIME %y' "$f" 2>/dev/null)"
    echo "    KIND $kind  PIN_MATCH $hp  PUBLIC_MARKER $pb  $seen"
    if [ "$KDIG" = "1" ] ; then
      echo "    SHA256 $(sha256sum "$f" | cut -d' ' -f1)"
    fi
  done
done
echo "ENUMERATED_FILES_TOTAL $TOTAL"
echo "N1_SWEEP_A_WORD_SHAPES_WOULD_HAVE_MISSED $MISSED"
echo "N1_SWEEP_B_MATCHED_BY_NAME_BUT_ITS_DEPTH_IS_TESTED_IN_L4"

echo "== L4 THE DEPTH BOUND, DRIVEN. A BOUND THE DATA REACHES IS NOT"
echo "   A BOUND THE DATA CLEARS."
D4=$(find /root /home -maxdepth 4 -type f -name '*.key' 2>/dev/null | wc -l)
D5=$(find /root /home -maxdepth 5 -type f -name '*.key' 2>/dev/null | wc -l)
D8=$(find /root /home -maxdepth 8 -type f -name '*.key' 2>/dev/null | wc -l)
echo "DOTKEY_AT_DEPTH_4 $D4"
echo "DOTKEY_AT_DEPTH_5 $D5"
echo "DOTKEY_AT_DEPTH_8 $D8"
if [ "$D4" != "$D8" ] ; then
  echo "BOUND_WAS_TRUNCATING the N1 depth of 4 was not a bound for this tree"
fi

echo "== L5 EVERY DIRECTORY NAMED keys, CROSS CHECKED AGAINST THE"
echo "   DECLARED LIST ABOVE. N3 PRINTED THIS LIST AND COMPARED IT TO"
echo "   NOTHING, SO TWO ENTRIES SAT UNMEASURED FOR A WHOLE ARC."
FOUND=$(find /root /home /opt /etc /srv -maxdepth 6 -type d -name keys 2>/dev/null | sort)
echo "FOUND_KEYS_DIRECTORIES $(printf '%s\n' "$FOUND" | grep -c .)"
printf '%s\n' "$FOUND" | sed 's/^/  FOUND /'
UNDECL=0
for f in $FOUND ; do
  hit=0
  for d in $DIRS ; do
    if [ "$f" = "$d" ] ; then
      hit=1
    fi
  done
  if [ "$hit" = "0" ] ; then
    echo "  NOT_IN_THE_DECLARED_LIST $f"
    UNDECL=$(expr $UNDECL + 1)
  fi
done
echo "FOUND_BUT_NOT_DECLARED $UNDECL"
echo "A NONZERO VALUE HERE IS NOT A REFUSAL. It is the same finding"
echo "  this body was built to stop hiding, and it is the reader's."
DECLABS=0
for d in $DIRS ; do
  if [ ! -d "$d" ] ; then
    DECLABS=$(expr $DECLABS + 1)
  fi
done
echo "DECLARED_BUT_ABSENT $DECLABS" 

echo "== L6 CREDENTIAL DIRECTORIES. NAMES AND MODES ONLY."
for d in /root/.gnupg /root/.gnupg/private-keys-v1.d /root/.ssh /root/.sigstore ; do
  if [ -d "$d" ] ; then
    echo "DIR_PRESENT $d"
    ls -la "$d" 2>/dev/null
  else
    echo "DIR_ABSENT  $d"
  fi
done

echo "== L7 UNIT CUSTODY. LEFT SIDE OF EVERY ASSIGNMENT. NEVER A VALUE."
UNITS=$(systemctl list-unit-files --no-pager --no-legend 2>/dev/null | grep -i nous | awk '{print $1}')
echo "NOUS_UNITS $(printf '%s\n' "$UNITS" | grep -c .)"
for u in $UNITS ; do
  echo "UNIT $u"
  systemctl cat "$u" 2>/dev/null | grep -i -E 'EnvironmentFile|^Environment=|^User=|^ExecStart=' | cut -d= -f1,2 | sed 's/^/    /'
done

echo "== L8 WHAT THIS RUN CANNOT SAY"
echo "It cannot say that no copy exists. It searched one host."
echo "It cannot say that any file found is recoverable."
if [ "$KDIG" = "0" ] ; then
  echo "It cannot say that a key here is the same key as one elsewhere."
fi
echo "It cannot say that a 32 byte file is an Ed25519 seed. That is a"
echo "  size, not an identity."
echo "== END"
