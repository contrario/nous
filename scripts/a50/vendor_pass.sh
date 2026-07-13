#!/usr/bin/env bash
# vendor_pass.sh — run the A50 teardown against real vendor samples, on an
# open-network machine, in a throwaway venv.
#
# WHY THIS EXISTS: a sandboxed/allowlisted machine can never reach an OCSP
# responder, so it always reads `ocsp.inaccessible` and CANNOT distinguish
# "responder unreachable" from "responder said the cert is live". The vendor
# pass is only meaningful from a machine with open outbound network.
#
# ISOLATION CONTRACT (do not violate):
#   - venv lives under /tmp. Nothing is installed into the NOUS editable install.
#   - nothing is written into any repo. nothing is committed.
#   - the venv is disposable; delete it when done.
#
# Usage:
#   ./vendor_pass.sh /path/to/samples_dir
#
# Sample dir must contain vendor outputs AS EMITTED BY THE GENERATOR — downloaded
# directly, never re-saved, never uploaded anywhere, never passed through a chat
# client, a CDN, or an image editor. Any of those strips the manifest and the run
# measures nothing.

set -euo pipefail

SAMPLES="${1:?usage: vendor_pass.sh <samples_dir>}"
VENV="/tmp/a50_venv"
WORK="/tmp/a50_vendor"

rm -rf "$VENV" "$WORK"
mkdir -p "$WORK"

python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q c2pa-python pillow

# Official conformance trust list. Without it, NOTHING can reach 'Trusted' and
# every result is untrusted BY CONFIGURATION rather than by evidence.
git clone --depth 1 -q https://github.com/c2pa-org/conformance-public.git "$WORK/conf"
cp "$WORK/conf/trust-list/C2PA-TRUST-LIST.pem" "$WORK/"
cp "$WORK/conf/trust-list/C2PA-TSA-TRUST-LIST.pem" "$WORK/"   # backs the TIMESTAMP leg

cp "$(dirname "$0")/a50_teardown.py" "$WORK/"
cd "$WORK"

# The script is NEVER edited. All three passes come from CLI flags, so the file a
# reader downloads is byte-identical to the one that produced these numbers.
echo "script sha256: $(sha256sum a50_teardown.py | cut -d' ' -f1)"

cat <<'LOCK'
======================================================================
EXPECTATION LOCK -- written BEFORE the run, so the result cannot be spun
======================================================================
Raw generator output is NEWLY CREATED: single manifest, no ingredients,
and per c2pa-rs README:61 ("supports C2PA v2 claims by default...
implementations should not generate deprecated v1 claims") almost
certainly claim_version 2.

THEREFORE THE LIKELY OUTCOME IS THAT FINDING 3 DOES NOT TRIGGER AT ALL.
That is the EXPECTED result. It is NOT a failure of the run.

If every sample is v2 with no ingredients, finding 3 must be published as:
  "Demonstrated on a claim_v1 fixture from c2pa-rs's OWN test suite.
   NOT observed in current raw generator output, which is v2. The v1 path
   remains live for legacy/archived files and for v1 INGREDIENTS inside
   modern manifests -- a case this run did NOT measure."
That is a bug report with a reproducer. It is publishable. It is NOT a
"vendors are exposed" story. Do not inflate it into one.

If any sample is v1, or carries a v1 ingredient (the store-wide check
catches both), finding 3 is LIVE on current output and the column proves it.

WHAT THIS RUN CANNOT ANSWER: edited content with an ingredient chain --
which is exactly where finding 3 most likely bites, and exactly what
Adobe's edit-history pitch produces. We are not measuring it. Say so.

Findings 1 and 2 are INDEPENDENT of claim version and stand either way.
======================================================================
POST-RUN ANNOTATION -- added 13 July 2026. S233-POST-RUN-ANNOTATION
THE LOCK ABOVE IS UNCHANGED. Nothing in it was deleted or softened.
These are the lines it got WRONG:
======================================================================
WRONG (1): "Findings 1 and 2 are INDEPENDENT of claim version and stand
  either way."  They did not. BOTH failed to appear on OpenAI and on
  Google, and surfaced only on Adobe. The lock reasoned entirely about the
  claim-version axis and never considered the VENDOR axis -- which turned
  out to be the one that decided the result.

WRONG (2): "If any sample is v1, OR CARRIES A V1 INGREDIENT (the store-wide
  check catches both), finding 3 is LIVE."  The ingredient half is FALSE.
  The file was constructed -- a v2 active manifest carrying the c2pa-rs v1
  fixture as a parentOf ingredient -- and read. The reader emits ONLY
  ingredient.manifest.validated: the hash matched. It does NOT re-verify the
  ingredient's signature, timestamp, or trust at read time. FINDING 3 DOES
  NOT REACH THROUGH INGREDIENTS. The same false claim was removed from
  a50_teardown.py (0.2.0 -> 0.3.0) in the same correction.

RIGHT:     "the likely outcome is that finding 3 does not trigger at all"
  -- for OpenAI and Google. It DID trigger on Adobe Firefly, which is v1.

The lock is kept verbatim because a teardown that reports only its hits is
not evidence, it is advocacy. The wrong prediction is the credential.
======================================================================
LOCK

echo "== network reachability check (OCSP must be reachable or the run is void) =="
python3 - <<'PY'
import socket, sys
for host in ("ocsp.digicert.com", "ocsp.globalsign.com"):
    try:
        socket.create_connection((host, 80), timeout=5).close()
        print(f"  {host:26s} REACHABLE")
    except Exception as e:
        print(f"  {host:26s} UNREACHABLE ({type(e).__name__}) "
              f"-- results will read ocsp.inaccessible and mean nothing")
PY

echo
echo "== PASS 0: OUT OF THE BOX — no trust list, ocsp_fetch=false. THE SHIPPED SDK. =="
echo "   c2pa-rs bundles NO trust list (include_bytes! is behind #[cfg(test)]),"
echo "   so out of the box NOTHING can ever reach 'Trusted'. This is what a"
echo "   developer sees who has not fetched and configured a list themselves."
"$VENV/bin/python" a50_teardown.py "$SAMPLES" --no-trust-list --no-ocsp \
    --json vendor_oob.json --md vendor_oob.md

echo "== PASS 1: trust lists loaded, ocsp_fetch=false (the SDK's OCSP default) =="
"$VENV/bin/python" a50_teardown.py "$SAMPLES" --no-ocsp \
    --json vendor_default.json --md vendor_default.md

echo "== PASS 2: trust lists loaded, ocsp_fetch=true =="
"$VENV/bin/python" a50_teardown.py "$SAMPLES" \
    --json vendor_ocsp.json --md vendor_ocsp.md

echo
echo "== THE MATRIX =="
"$VENV/bin/python" - <<'PY'
import json

b = json.load(open("vendor_oob.json"))
d = json.load(open("vendor_default.json"))
o = json.load(open("vendor_ocsp.json"))
bmap = {f["ladder"]["file"]: f["ladder"] for f in b["files"]}
omap = {f["ladder"]["file"]: f["ladder"] for f in o["files"]}

hdr = ("file", "generator", "claim_v", "OUT-OF-BOX", "configured", "revocation checked via",
       "revocation (default)", "revocation (ocsp on)", "survival")
rows = []
for f in d["files"]:
    L = f["ladder"]
    if L["marking"] != "PRESENT":
        rows.append((L["file"][:24], "-", "-", "-", "-", "-", "NO C2PA MANIFEST", "-", "-"))
        continue
    O = omap.get(L["file"], {})
    surv = {k: v for k, v in f["survival"].items() if k != "__scope__"}
    stripped = sum(1 for v in surv.values() if v.get("c2pa_manifest") == "STRIPPED")
    st = L.get("store", {})
    vs = sorted({v for v in st.get("claim_versions", {}).values() if v})
    cv = "/".join(f"v{v}" for v in vs) if vs else "?"
    if st.get("manifest_count", 1) > 1:
        cv += f" ({st['manifest_count']}mf)"
    B = bmap.get(L["file"], {})
    gen = (L["legs"]["assertions"].get("claim_generator") or "?")[:22]
    rows.append((
        L["file"][:24],
        gen,
        cv,
        B.get("sdk_top_level_state", "?"),
        L["sdk_top_level_state"],
        L["legs"]["revocation"]["checked_via"],
        L["legs"]["revocation"]["status"],
        O.get("legs", {}).get("revocation", {}).get("status", "?"),
        f"{stripped}/{len(surv)} stripped",
    ))

w = [max(len(str(r[i])) for r in (rows + [hdr])) for i in range(len(hdr))]
line = lambda r: "  ".join(str(c).ljust(w[i]) for i, c in enumerate(r))
print(line(hdr))
print("  ".join("-" * x for x in w))
for r in rows:
    print(line(r))

print()
print("=" * 70)
print("THE OUT-OF-BOX COLUMN: c2pa-rs BUNDLES NO TRUST LIST")
print("=" * 70)
print("If OUT-OF-BOX=Valid while CONFIGURED=Trusted on the SAME genuinely-signed file,")
print("then a developer running the SDK as shipped cannot distinguish that file from a")
print("self-signed forgery. The trust signal requires fetching a list the SDK does not")
print("bundle, and 'Valid' reads as 'good' to everyone who has not. This is why the")
print("Krawetz forgery passed every tool EXCEPT the CAI reference site -- it loads the list.")
print()
print("=" * 70)
print("THE COLUMN THAT MATTERS MOST: claim_v")
print("=" * 70)
print("It DECIDES whether finding 3 is LIVE or HISTORICAL.")
print("  claim_v = 1 -> store.rs:1952 passes verify_trust=FALSE, the trust-check block")
print("               (verify.rs:535-583) is SKIPPED, and TIMESTAMP_TRUSTED is emitted")
print("               anyway at :590, outside the guard. The SDK affirms a timestamp")
print("               certificate is trusted having checked nothing. FINDING IS LIVE")
print("               ON CURRENT VENDOR OUTPUT.")
print("  claim_v = 2 -> verify_trust=TRUE, the check RUNS, ANCHORED means what it says.")
print("               Finding 3 is scoped to LEGACY/ARCHIVED files whose ACTIVE")
print("               manifest is v1. NOT to v1 ingredients inside newer manifests")
print("               -- that was tested and it does not hold. See below.")
print("               (README:61 -- v2 is the default for modern generators.)")
print("NEVER state finding 3 without the version qualifier.")
print()
print("claim_v is reported STORE-WIDE (all manifests, not just the active one), and")
print("'(Nmf)' = N manifests in the store, i.e. an ingredient chain is present.")
print()
print("CORRECTED 13 July 2026. AN EARLIER VERSION OF THIS BANNER CLAIMED that a v2")
print("active manifest carrying a v1 ingredient gets that ingredient's timestamp trust")
print("check skipped too, and that finding 3 may therefore bite inside a modern-looking")
print("file. THAT WAS FALSE. It was falsified by construction, not by argument: the file")
print("was built -- a v2 active manifest carrying the c2pa-rs v1 fixture as a parentOf")
print("ingredient -- and read. The reader emits ONLY ingredient.manifest.validated: the")
print("hash matched. It does NOT re-verify the ingredient's signature, timestamp, or")
print("trust at read time. FINDING 3 DOES NOT REACH THROUGH INGREDIENTS.")
print("The same claim was removed from a50_teardown.py in the same correction (0.3.0).")
print()
print("SECOND QUESTION: HOW is revocation checked, if at all?")
print("  TWO mechanisms exist (crypto/cose/ocsp.rs::check_ocsp_status):")
print("    (1) OCSP staple in the COSE unprotected header -- get_ocsp_der(sign1)")
print("    (3) c2pa.certificate-status ASSERTION")
print("  Either way revocation IS checked by default. BUT both are a SNAPSHOT taken at")
print("  SIGNING time: revocation AFTER signing stays invisible, consistent with the")
print("  spec's 'validate indefinitely'. Narrower finding, still real.")
print("  'not checked' -> the DoNotFetch terminal arm makes NO determination and emits")
print("  NO code at all. A revoked certificate is indistinguishable from a live one.")
print()
print("SCOPE LOCK: C2PA metadata layer ONLY. SynthID / AudioSeal / any imperceptible")
print("watermark is NOT measured and may survive every transformation above.")
print("Permitted: 'the C2PA metadata layer does not survive.'")
print("FORBIDDEN: 'the marking does not survive.'")
PY

echo
echo "artifacts: $WORK/vendor_default.{json,md}  $WORK/vendor_ocsp.{json,md}"
echo "cleanup:   rm -rf $VENV $WORK"
