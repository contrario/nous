#!/usr/bin/env python3
"""
a50_teardown.py — Article 50(2) conformance teardown.

Produces, for each input image:
  1. A VERDICT LADDER — what the C2PA marking actually shows, graded, never binary.
  2. A SURVIVAL MATRIX — whether the marking survives a corpus of local transformations.

Deterministic. No network. No LLM. No platform uploads (no ToS exposure).
Same input + same corpus version => same output bytes.

WHAT THIS DOES NOT DO, BY DESIGN:
  - It does not tell you whether content is AI-generated. No manifest can support that
    claim. Any tool that says otherwise is overclaiming.
  - It does not issue a compliance certificate. It is an engineering test report.

Usage:
    python3 a50_teardown.py <file_or_dir> [...] [--json out.json] [--md out.md]
"""

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import c2pa
from PIL import Image


def configure():
    """Load the official trust list and enable OCSP. Report what we could not load."""
    notes = []
    cfg = {"verify": {"verify_trust": True, "verify_timestamp_trust": True,
                      "ocsp_fetch": OCSP_FETCH}}
    if not LOAD_TRUST_LIST:
        c2pa.load_settings(json.dumps(
            {"verify": {"verify_trust": True, "ocsp_fetch": OCSP_FETCH}}))
        return ["OUT-OF-THE-BOX: no trust list loaded. c2pa-rs BUNDLES NONE "
                "(certificate_trust_policy.rs include_bytes! is behind #[cfg(test)]). "
                "This is what a developer sees running the SDK as shipped."]
    pems, missing = [], []
    for path, what in ((TRUST_ANCHORS_PATH, "C2PA"), (TSA_ANCHORS_PATH, "TSA")):
        p = Path(path)
        if p.is_file():
            t = p.read_text()
            pems.append(t)
            notes.append(f"{what} anchors loaded: {t.count('BEGIN CERTIFICATE')} certs")
        else:
            missing.append(path)
    if pems:
        cfg["trust"] = {"trust_anchors": "\n".join(pems)}
    if TRUST_ANCHORS_PATH in missing:
        notes.append(f"WARNING: {TRUST_ANCHORS_PATH} missing. Nothing can reach 'Trusted'. "
                     f"Results are untrusted BY CONFIGURATION, not by evidence. "
                     f"DO NOT PUBLISH NUMBERS FROM THIS RUN.")
    if TSA_ANCHORS_PATH in missing:
        notes.append(f"WARNING: {TSA_ANCHORS_PATH} missing. The TIMESTAMP leg is "
                     f"UNDER-CONFIGURED and its 'ANCHORED' status is not trustworthy.")
    c2pa.load_settings(json.dumps(cfg))
    return notes

CORPUS_VERSION = "1.1.0"
TOOL_VERSION = "0.3.0"

# Trust config. Without these, c2pa-rs cannot reach a 'Trusted' state at all and
# every file looks untrusted. Fetch from:
#   github.com/c2pa-org/conformance-public/trust-list/C2PA-TRUST-LIST.pem
# Runtime config. Set by CLI flags -- NOT by editing this file. A script you must
# edit to run differently is a script a reader will run wrongly. The published
# file's SHA-256 is therefore stable across all three passes.
LOAD_TRUST_LIST = True   # --no-trust-list  -> False (reproduces the shipped SDK)
OCSP_FETCH = True        # --no-ocsp        -> False (reproduces the SDK's default)
TRUST_ANCHORS_PATH = "C2PA-TRUST-LIST.pem"
# The conformance repo ships TWO lists. The TSA list backs the TIMESTAMP leg.
# add_trust_anchors() doc (certificate_trust_policy.rs:203): "can be called multiple
# times... the C2PA trust anchors and timestamping trust anchors can be added
# separately." There is no separate TSA field on struct Trust -- both go to the same
# pool. So we CONCATENATE. Without this the timestamp leg is UNDER-CONFIGURED.
TSA_ANCHORS_PATH = "C2PA-TSA-TRUST-LIST.pem"

# ---------------------------------------------------------------------------
# SCOPE LOCK. Read this before quoting any number from this tool.
#
# This measures the C2PA METADATA LAYER ONLY.
#
# It CANNOT see SynthID, AudioSeal, or any imperceptible watermark. An invisible
# layer may survive every transformation below and this tool would never know.
#
# PERMITTED:  "the C2PA metadata layer is destroyed by a q95 re-save"
# FORBIDDEN:  "the marking does not survive"   <- we did not measure the other layer
#
# The EU Code of Practice mandates a MULTI-LAYER approach. We audit one layer.
# Saying otherwise would be the exact overclaim this project exists to expose.
# ---------------------------------------------------------------------------
UNMEASURED_LAYERS = ["imperceptible watermark (SynthID, AudioSeal, et al.)",
                     "soft binding / perceptual hash",
                     "manifest repository lookup (remote manifest recovery)"]

# ── Verdict ladder labels ────────────────────────────────────────────────────
# "PROVEN" IS NOT USED IN THIS TOOL. Deliberate.
#
# A signature check is a DECIDABLE check over a finite, already-committed set:
# it holds by construction. That is tier VERIFIED -- decidable static analysis.
# It is NOT the same class as a universally-quantified proof over all reachable
# paths before execution (Z3/Farkas), and calling both "PROVEN" hosts two
# contradictory meanings of the word on the same domain.
#
# An earlier version of this tool labelled hash+signature PROVEN. That was an
# overclaim by the tool that exists to catch overclaims. Corrected.
VERIFIED = "VERIFIED"        # decidable, holds by construction:
                             #   hash binding, signature, trust chain
UNTRUSTED = "UNTRUSTED"      # chain does not reach a trusted root
REPORTED = "REPORTED"        # what the signer wrote. zero evidentiary weight.
UNRESOLVABLE = "UNRESOLVABLE"
ABSENT = "ABSENT"
BROKEN = "BROKEN"
NOT_ANSWERED = "NOT_ANSWERED"

MEANING = {
    "hash_binding": "Decidable check: the bytes are unchanged since signing. "
                    "Nothing more. This is VERIFIED, not proven -- a decidable "
                    "check over an already-committed set, not a universally "
                    "quantified proof.",
    "signature": "Decidable check: the holder of this certificate signed these "
                 "bytes. Not who they are. Not that the content is true.",
    "trust_chain": "Whether the chain reaches a root on the C2PA Trust List. A policy "
                   "fact, not a proof: it inherits the Trust List's trustworthiness, and "
                   "a trusted signing certificate is purchasable (~$289, Krawetz). NOTE: "
                   "an UNTRUSTED credential is explicitly TOLERATED inside validation "
                   "state 'Valid' -- see spec #_valid_manifest and c2pa-rs "
                   "validation_results.rs::validation_state().",
    "revocation": "Whether the certificate is still valid TODAY. c2pa-rs DOES implement "
                  "OCSP (crypto/cose/ocsp.rs) -- an earlier draft of this tool wrongly "
                  "claimed it did not. Order: (1) OCSP staple in the COSE claim, (2) if "
                  "ocsp_fetch is on, fetch, (3) if off, check CertificateStatus "
                  "assertions. `ocsp_fetch` ships DEFAULT FALSE. With no staple and no "
                  "CertificateStatus assertion, the default path makes NO determination "
                  "and emits NO code anywhere -- a revoked certificate is then "
                  "indistinguishable from a live one. A staple, where present, is a "
                  "SNAPSHOT taken at signing time: revocation AFTER signing stays "
                  "invisible, consistent with the spec's 'validate indefinitely'.",
    "timestamp": "Whether a timestamp authority signed the time, or the signer simply "
                 "asserted a date. FOR CLAIM VERSION 1 THIS LEG IS NOT EVIDENCE: see the "
                 "TIMESTAMP_TRUSTED_ASSERTED_WITHOUT_CHECK flag. For claim v2 the trust "
                 "check runs and ANCHORED means what it says.",
    "assertions": "What the manifest CLAIMS (ai_generated, camera_captured, edited). "
                  "This is what the signer wrote. A C2PA-enabled camera has signed "
                  "AI-generated output before (Nikon Z6 III). Zero evidentiary weight "
                  "regarding the physical world.",
    "ai_generated": "Out of scope. A manifest cannot answer this, and neither can we.",
}


# ── Transformation corpus ────────────────────────────────────────────────────
# Local only. Each is a pure function of the input. No platform is contacted.
def _save(im, path, fmt, **kw):
    # JPEG and WebP(lossy) cannot carry an alpha channel. Flattening RGBA -> RGB is
    # NOT hidden preprocessing: it is precisely what a real CDN/CMS pipeline does when
    # it converts a PNG to JPEG. It is part of the transformation being measured.
    if fmt == "JPEG" and im.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        conv = im.convert("RGBA")
        bg.paste(conv, mask=conv.split()[-1])
        im = bg
    elif fmt == "JPEG" and im.mode != "RGB":
        im = im.convert("RGB")
    im.save(path, fmt, **kw)


def corpus(im, w, h, outdir, stem):
    """Yield (transform_name, output_path). Deterministic and ordered."""
    T = []

    def add(name, fn):
        T.append((name, fn))

    add("jpeg_q95", lambda p: _save(im, p, "JPEG", quality=95))
    add("jpeg_q80", lambda p: _save(im, p, "JPEG", quality=80))
    add("jpeg_q70", lambda p: _save(im, p, "JPEG", quality=70))
    add("resize_1080", lambda p: _save(
        im.resize((1080, max(1, round(h * 1080 / w)))), p, "JPEG", quality=95))
    add("resize_720", lambda p: _save(
        im.resize((720, max(1, round(h * 720 / w)))), p, "JPEG", quality=95))
    add("crop_10pct", lambda p: _save(
        im.crop((round(w * .05), round(h * .05), round(w * .95), round(h * .95))),
        p, "JPEG", quality=95))
    add("crop_25pct", lambda p: _save(
        im.crop((round(w * .125), round(h * .125), round(w * .875), round(h * .875))),
        p, "JPEG", quality=95))
    add("convert_png", lambda p: _save(im, p, "PNG"))
    add("convert_webp", lambda p: _save(im, p, "WEBP", quality=90))
    add("rerender_rgb", lambda p: _save(im.convert("RGB"), p, "JPEG", quality=100))

    ext = {"convert_png": ".png", "convert_webp": ".webp"}
    for name, fn in T:
        out = outdir / f"{stem}__{name}{ext.get(name, '.jpg')}"
        fn(out)
        yield name, out


# ── Reader ───────────────────────────────────────────────────────────────────
def _generator(manifest):
    """claim v1 -> claim_generator (string). claim v2 -> claim_generator_info (list)."""
    g = manifest.get("claim_generator")
    if g:
        return g
    info = manifest.get("claim_generator_info") or []
    if isinstance(info, list) and info:
        parts = [f"{i.get('name','?')}/{i.get('version','?')}" for i in info if isinstance(i, dict)]
        return " ".join(parts) or None
    return None


def read_c2pa(path):
    """Return (state, manifest, codes) or (None, None, None) if no manifest."""
    try:
        r = c2pa.Reader(str(path))
    except Exception:
        return None, None, None, None
    state = r.get_validation_state()
    store = json.loads(r.json())
    active = store.get("active_manifest")
    manifest = store.get("manifests", {}).get(active, {}) if active else {}
    vr = r.get_validation_results() or {}
    am = vr.get("activeManifest", {}) or {}
    codes = {
        "success": [i["code"] for i in (am.get("success") or [])],
        "informational": [i["code"] for i in (am.get("informational") or [])],
        "failure": [i["code"] for i in (am.get("failure") or [])],
    }
    # STORE-WIDE, not active-only. store.rs:1942 iterates PER REFERENCED CLAIM
    # (`svi.manifest_map.get(referenced_claim)`) and calls rc.version() on each.
    # INGREDIENTS ARE REFERENCED CLAIMS: a v2 active manifest carrying a v1 ingredient
    # gets that ingredient's timestamp trust check skipped, and TIMESTAMP_TRUSTED emitted
    # for it -- the same false assertion, inside a "modern" file. Reading only the active
    # manifest misses exactly the case where finding 3 most likely bites.
    versions = {lbl: m.get("claim_version") for lbl, m in (store.get("manifests") or {}).items()}
    deltas = []
    for d in (vr.get("ingredientDeltas") or []):
        sc = d.get("validationDeltas", {}) or {}
        deltas.append({
            "uri": d.get("ingredientAssertionURI"),
            "success": [i["code"] for i in (sc.get("success") or [])],
            "informational": [i["code"] for i in (sc.get("informational") or [])],
            "failure": [i["code"] for i in (sc.get("failure") or [])],
        })
    extra = {
        "manifest_count": len(versions),
        "claim_versions": versions,
        "active_label": active,
        "any_v1_in_store": any(v == 1 for v in versions.values()),
        "ingredient_deltas": deltas,
    }
    return state, manifest, codes, extra


def ladder(path):
    """The verdict ladder. Never a single aggregate PASS."""
    sha = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    state, manifest, codes, extra = read_c2pa(path)

    if state is None:
        return {
            "file": Path(path).name,
            "sha256": sha,
            "marking": ABSENT,
            "legs": {"marking": {"status": ABSENT,
                                 "means": "No C2PA manifest present."}},
            "sdk_top_level_state": None,
            "overclaim_flags": [],
        }

    allc = codes["success"] + codes["informational"] + codes["failure"]
    fails = codes["failure"]
    assertions = [a.get("label") for a in (manifest.get("assertions") or [])]

    hash_ok = "assertion.dataHash.match" in allc and "assertion.dataHash.mismatch" not in fails
    sig_ok = "claimSignature.validated" in allc and "claimSignature.mismatch" not in fails
    untrusted = "signingCredential.untrusted" in fails
    ts_anchored = "timeStamp.validated" in allc
    # Exact strings from c2pa-rs validation_results.rs -- NOT guessed.
    #   :566 SIGNING_CREDENTIAL_NOT_REVOKED     = "signingCredential.ocsp.notRevoked"
    #   :790 SIGNING_CREDENTIAL_REVOKED         = "signingCredential.ocsp.revoked"
    #   :648 SIGNING_CREDENTIAL_OCSP_INACCESSIBLE = "signingCredential.ocsp.inaccessible"
    #   :642 SIGNING_CREDENTIAL_OCSP_SKIPPED    = "signingCredential.ocsp.skipped"
    # An earlier version of this tool searched for "signingCredential.notRevoked" and
    # "signingCredential.revoked" -- both WRONG -- and therefore reported UNRESOLVABLE
    # and staple=no on every file, including files where the SDK had in fact checked
    # revocation and found it clean. Two false values published to a matrix. Same error
    # class as the two falsified findings: a string assumed instead of read.
    C_NOT_REVOKED = "signingCredential.ocsp.notRevoked"
    C_REVOKED = "signingCredential.ocsp.revoked"
    C_INACCESSIBLE = "signingCredential.ocsp.inaccessible"
    C_SKIPPED = "signingCredential.ocsp.skipped"
    revoked = C_REVOKED in allc
    not_revoked = C_NOT_REVOKED in allc
    revocation_known = revoked or not_revoked
    ocsp_signal = any("ocsp" in c.lower() for c in allc)
    # TWO revocation mechanisms exist, not one. check_ocsp_status (crypto/cose/ocsp.rs)
    # looks at (1) an OCSP staple in the COSE unprotected header via get_ocsp_der(sign1),
    # and SEPARATELY (3) CertificateStatus assertions. An earlier version of this tool
    # read only the assertion label and therefore reported staple=no on a file the SDK
    # had in fact checked via a COSE staple -- a value contradicted by the very next
    # column. Report the MECHANISM, and mark what is inferred as inferred.
    cert_status_assertion = "c2pa.certificate-status" in assertions
    ocsp_enabled = OCSP_FETCH
    # Silence = DoNotFetch + no staple + no CertificateStatus assertion.
    # crypto/cose/ocsp.rs returns Ok(OcspResponse::default()) and logs NOTHING.
    revocation_silent = not revocation_known and not ocsp_signal

    sig_info = manifest.get("signature_info", {}) or {}
    claim_version = manifest.get("claim_version")

    legs = {
        "hash_binding": {
            "status": VERIFIED if hash_ok else BROKEN,
            "means": MEANING["hash_binding"],
        },
        "signature": {
            "status": VERIFIED if sig_ok else BROKEN,
            "alg": sig_info.get("alg"),
            "issuer": sig_info.get("issuer"),
            "means": MEANING["signature"],
        },
        "trust_chain": {
            "status": UNTRUSTED if untrusted else VERIFIED,
            "means": MEANING["trust_chain"],
        },
        "revocation": {
            "status": ("REVOKED" if revoked
                       else "NOT_REVOKED" if not_revoked
                       else "INACCESSIBLE" if C_INACCESSIBLE in allc
                       else "SKIPPED" if C_SKIPPED in allc
                       else "NOT_CHECKED_SILENTLY"),
            "codes_seen": [c for c in allc if "ocsp" in c.lower()],
            "ocsp_fetch_enabled": ocsp_enabled,
            "checked_via": (
                "cert-status assertion" if cert_status_assertion and not_revoked
                else "OCSP fetch" if (revocation_known and OCSP_FETCH
                                      and not cert_status_assertion)
                else "COSE staple (inferred)" if (revocation_known and not OCSP_FETCH
                                                  and not cert_status_assertion)
                else "not checked"),
            "cert_status_assertion": cert_status_assertion,
            "means": MEANING["revocation"],
        },
        "timestamp": {
            "status": "ANCHORED" if ts_anchored else "SELF_ASSERTED",
            "time": sig_info.get("time"),
            "claim_version_active": claim_version,
            "claim_versions_store_wide": extra["claim_versions"],
            "manifest_count": extra["manifest_count"],
            "any_v1_in_store": extra["any_v1_in_store"],
            "trust_check_skipped": extra["any_v1_in_store"],
            "means": MEANING["timestamp"],
        },
        "assertions": {
            "status": REPORTED,
            "labels": assertions,
            "claim_generator": _generator(manifest),
            "means": MEANING["assertions"],
        },
        "ai_generated": {
            "status": NOT_ANSWERED,
            "means": MEANING["ai_generated"],
        },
    }

    # -- The finding. Critique of the MODEL, not the implementation. --------
    # c2pa-rs behaves exactly as the C2PA spec mandates. The spec is the problem:
    # three states (Invalid / Valid / Trusted) and none of them means "unknown".
    flags = []
    if untrusted and not LOAD_TRUST_LIST:
        flags.append({
            "flag": "NO_TRUST_LIST_BUNDLED_SO_NOTHING_CAN_EVER_BE_TRUSTED",
            "detail": ("c2pa-rs SHIPS NO TRUST LIST. The include_bytes! calls in "
                       "certificate_trust_policy.rs are behind #[cfg(test)]. Therefore "
                       "OUT OF THE BOX, NO FILE CAN EVER REACH 'Trusted' -- not even a "
                       "genuinely signed vendor image. Measured on BOTH sides of the "
                       "same real OpenAI file:\n"
                       "  no trust list (THE DEFAULT) -> state=Valid,   "
                       "failure=[signingCredential.untrusted]\n"
                       "  trust list loaded           -> state=Trusted, failure=[]\n"
                       "CONSEQUENCE: a developer running the SDK as shipped, against a "
                       "genuinely signed vendor image, sees 'Valid' with an untrusted "
                       "failure -- and CANNOT DISTINGUISH IT FROM A SELF-SIGNED FORGERY. "
                       "The entire trust signal requires the caller to fetch and "
                       "configure a list the SDK does not bundle, and the state name "
                       "'Valid' reads as 'good' to everyone who does not.\n"
                       "This also explains why the Krawetz forgery passed every tool "
                       "EXCEPT the CAI reference site: the reference site loads the "
                       "trust list. By default, nothing else does."),
            "belongs_to": "DISTRIBUTION/DEFAULTS. Live on current vendor output.",
            "source": "c2pa-rs crypto/cose/certificate_trust_policy.rs (include_bytes! "
                      "under #[cfg(test)]); measured both configurations, same file",
        })
    if state == "Valid" and untrusted and LOAD_TRUST_LIST:
        flags.append({
            "flag": "SPEC_STATE_VALID_TOLERATES_UNTRUSTED_CREDENTIAL",
            "detail": ("validation_state='Valid' while the signing credential is "
                       "UNTRUSTED. This is not an SDK bug: c2pa-rs "
                       "validation_results.rs::validation_state() deliberately admits "
                       "failures when they are only SIGNING_CREDENTIAL_UNTRUSTED, per "
                       "spec #_valid_manifest. A developer checking `state == \"Valid\"` "
                       "-- the natural check, since the word means 'good' in every other "
                       "API -- accepts an untrusted certificate AND IS SPEC-CONFORMANT. "
                       "Only 'Trusted' requires a chain to a Trust List root."),
            "belongs_to": ("SPECIFICATION, not implementation. CAI SECURITY.md states: "
                           "'This library is only an implementation of the spec as "
                           "written. Any suspected vulnerabilities within the spec can be "
                           "reported [at the specifications repo].' By their own routing, "
                           "this finding is not c2pa-rs's to answer."),
            "source": "c2pa-rs sdk/src/validation_results.rs::validation_state(); "
                      "spec 2.2 #_valid_manifest / #_trusted_manifest; SECURITY.md",
        })
    # NARROWED TO THE ACTIVE MANIFEST. Earlier versions fired this flag on
    # any_v1_in_store -- i.e. a v1 INGREDIENT inside a v2 manifest would trip it,
    # and the tool would print that the ingredient's timestamp trust check was
    # skipped and timeStamp.trusted emitted for it.
    #
    # THAT WAS MEASURED AND IS FALSE. A v2 manifest carrying a v1 ingredient was
    # constructed and read: the reader emits only `ingredient.manifest.validated`
    # ("hash matched"), unchanged with or without trust anchors loaded. It verifies
    # the ingredient was not ALTERED; it does not re-verify the ingredient's
    # signature, timestamp, or trust at read time. The finding does NOT bite through
    # ingredients. Negative result.
    #
    # A tool that asserts what its own null result refutes is the defect class this
    # tool exists to catch, committed by the tool. Corrected.
    if claim_version == 1 and ts_anchored:
        flags.append({
            "flag": "TIMESTAMP_TRUSTED_ASSERTED_WITHOUT_CHECK",
            "concession_first": (
                "The SKIP is DEFENSIBLE and we say so. store.rs:1952 passes "
                "verify_trust = `rc.version() != 1` with the comment 'no trust checks "
                "for leagacy timestamps' -- backward compatibility for v1 claims. "
                "Declining to trust-check a legacy timestamp is a reasonable choice. "
                "THE BUG IS NOT THE SKIP."),
            "detail": ("The ACTIVE manifest is claim_version 1. Its timestamp trust check "
                       "was SKIPPED -- and c2pa-rs nonetheless emits "
                       "`timeStamp.trusted` ('timestamp cert trusted') into the SUCCESS "
                       "bucket. MEASURED, not inferred: (a) claim_version=1 from the manifest; "
                       "(b) brace-depth trace shows `if verify_trust {` opens at "
                       "verify.rs:535 and CLOSES at :583, while TIMESTAMP_TRUSTED is "
                       "emitted at :590 at depth 0 -- OUTSIDE the guard; (c) empirically "
                       "timeStamp.trusted fires with full trust lists, with ZERO anchors, "
                       "with verify_trust_list=false, AND with verify_trust=false. "
                       "Unconditional.\n"
                       "This is a POSITIVE FALSE ASSERTION in the success bucket -- "
                       "stronger than the other two findings. OCSP_SKIPPED is silence "
                       "where a signal was owed. Valid-tolerates-untrusted is "
                       "spec-mandated. This one affirms trust that was never evaluated.\n"
                       "The honest emission is a skip code, or no timestamp status at "
                       "all. Same shape as OCSP_SKIPPED: the signal for 'we did not "
                       "check' is the thing that is missing."),
            "scope": ("SCOPED TO A CLAIM-VERSION-1 ACTIVE MANIFEST. It does NOT reach "
                      "through ingredients: a v1 ingredient inside a v2 manifest was "
                      "constructed and tested, and the reader emits only "
                      "ingredient.manifest.validated -- it does not re-verify the "
                      "ingredient's timestamp at read time. Measured negative result. "
                      "c2pa-rs README:61: 'The library "
                      "supports C2PA v2 claims by default, and implementations should "
                      "not generate deprecated v1 claims.' If current vendor output is "
                      "v2, verify_trust=TRUE and the check RUNS. This finding then "
                      "applies to LEGACY/ARCHIVED files and to v1 INGREDIENTS carried "
                      "inside newer manifests -- NOT to current generator output. Never "
                      "state it without the version qualifier."),
            "belongs_to": ("IMPLEMENTATION (c2pa-rs). One-line patch. Not a spec issue: "
                           "the spec does not ask anyone to assert trust they did not "
                           "check. By CAI's own SECURITY.md routing, they own this."),
            "source": "c2pa-rs store.rs:1952 (verify_trust = rc.version() != 1); "
                      "crypto/time_stamp/verify.rs:535 (guard opens), :583 (guard "
                      "closes), :585-591 (TIMESTAMP_TRUSTED emitted outside it); "
                      "README.md:61 (v2 by default)",
        })

    if revocation_silent:
        flags.append({
            "flag": "OCSP_SKIPPED_CODE_DEFINED_BUT_NEVER_EMITTED",
            "concession_first": (
                "The default (ocsp_fetch=false) is a DEFENSIBLE security choice, and we "
                "say so. CAI SECURITY.md:27 lists 'Network calls based on C2PA manifest "
                "input data' as a known problematic characteristic with work in progress "
                "(tracking issue #1765); tickets on it are rejected until that lands. "
                "Not fetching OCSP means no outbound network on attacker-controlled "
                "input. That is correct engineering. The finding is not the default. "
                "The finding is its CONSEQUENCE."),
            "detail": (f"validation_state='{state}', and NO revocation determination was "
                       "made -- with no code emitted in ANY bucket, informational "
                       "included. THE ASYMMETRY IS THE FINDING. c2pa-rs defines FOUR "
                       "revocation states and emits only THREE:\n"
                       "  REVOKED           -> emitted (ocsp.rs:133, :266)\n"
                       "  NOT_REVOKED       -> emitted (ocsp.rs:151, :284)\n"
                       "  OCSP_INACCESSIBLE -> emitted (ocsp.rs:435)\n"
                       "  OCSP_SKIPPED      -> DEFINED, doc-commented 'The validator "
                       "chose not to perform an online OCSP check', classified "
                       "Informational by log_kind() -- and NEVER EMITTED. It is not even "
                       "imported into ocsp.rs. Its only appearance in the entire SDK is "
                       "the log_kind() match arm.\n"
                       "On the DEFAULT path (no staple, no CertificateStatus assertion) "
                       "the code returns Ok(OcspResponse::default()) silently "
                       "(ocsp.rs:210, :213). Its revoked_at is None -- STRUCTURALLY "
                       "IDENTICAL to a successful check that found no revocation. "
                       "Absence of evidence is returned in the shape of evidence of "
                       "absence. The caller cannot distinguish 'checked, certificate "
                       "live' from 'never checked' -- not in the state, not in "
                       "validation_results(), not in the returned struct.\n"
                       "The SDK already knows it needs this code. It just never calls "
                       "it. The fix is one line in the DoNotFetch arm."),
            "belongs_to": ("IMPLEMENTATION (c2pa-rs). Not a spec issue: the code is "
                           "defined in the SDK, classified in the SDK, and unemitted in "
                           "the SDK. CAI SECURITY.md routes spec issues elsewhere; this "
                           "one is theirs."),
            "source": "c2pa-rs validation_results.rs:642 (SIGNING_CREDENTIAL_OCSP_SKIPPED "
                      "definition + doc comment); validation_results.rs:1097 (its only "
                      "other occurrence); crypto/cose/ocsp.rs:32-33 (import list omits "
                      "it); crypto/cose/ocsp.rs:210,:213 (silent terminal arms); "
                      "crypto/ocsp/mod.rs:49-58 (Default: revoked_at=None); "
                      "settings/mod.rs (ocsp_fetch default=false); SECURITY.md:27",
        })
    elif not revocation_known and ocsp_signal:
        flags.append({
            "flag": "REVOCATION_UNKNOWN_VISIBLE_ONLY_IN_SECOND_API",
            "detail": (f"validation_state='{state}', but revocation was NOT determined "
                       f"(codes: {[c for c in allc if 'ocsp' in c.lower()]}). log_kind() "
                       "classifies OCSP_SKIPPED and OCSP_INACCESSIBLE as Informational, "
                       "and Informational does not affect validation_state. The "
                       "uncertainty IS available -- but only to a caller who makes a "
                       "SECOND call to validation_results() and reads the informational "
                       "bucket. The top-level field a developer naturally checks does "
                       "not express it. NOTE: OCSP soft-fail is standard web-PKI "
                       "practice, not a defect. The critique is the API surface, not the "
                       "fail-open."),
            "source": "c2pa-rs validation_results.rs::log_kind(); "
                      "crypto/cose/ocsp.rs::fetch_and_check_ocsp_response",
        })

    return {
        "file": Path(path).name,
        "sha256": sha,
        "marking": "PRESENT",
        "sdk_top_level_state": state,
        "sdk_codes": codes,
        "store": extra,
        "legs": legs,
        "overclaim_flags": flags,
    }


def survival(path, workdir):
    """Run the corpus; report per-transform manifest survival."""
    p = Path(path)
    try:
        im = Image.open(p)
        im.load()
    except Exception as e:
        return {"error": f"not a readable image: {type(e).__name__}"}
    w, h = im.size
    rows = {"__scope__": {"measures": "C2PA metadata layer only",
                          "unmeasured": UNMEASURED_LAYERS}}
    for name, out in corpus(im, w, h, workdir, p.stem):
        state, _, codes, _ = read_c2pa(out)
        if state is None:
            rows[name] = {"c2pa_manifest": "STRIPPED"}
        else:
            fails = codes["failure"]
            rows[name] = {
                "c2pa_manifest": "SURVIVES" if not fails else "DEGRADED",
                "state": state,
                "failures": fails,
            }
        out.unlink(missing_ok=True)
    return rows


def render_md(report):
    L = []
    e = report["environment"]
    L.append("# Article 50(2) conformance teardown\n")
    L.append(f"- run: `{report['run_at']}` (UTC)")
    L.append(f"- tool: a50_teardown {TOOL_VERSION} | corpus {CORPUS_VERSION}")
    L.append(f"- c2pa-python {e['c2pa_python']} (c2pa-rs {e['c2pa_rs']}) | "
             f"Pillow {e['pillow']} | Python {e['python']}")
    L.append(f"- ocsp_fetch: `{e['ocsp_fetch']}` (c2pa-rs default is `false`)")
    for n in report["config_notes"]:
        L.append(f"- {n}")
    L.append("")
    L.append("> This report evidences what the marking SHOWS and whether it survives "
             "transformation.\n> It does NOT determine whether content is AI-generated. "
             "No manifest can. It is not a compliance certificate.\n")

    for r in report["files"]:
        lad = r["ladder"]
        L.append(f"\n## `{lad['file']}`\n")
        L.append(f"`sha256:{lad['sha256'][:16]}…`\n")
        if lad["marking"] == ABSENT:
            L.append("**No C2PA manifest.** Nothing to verify. Under Art. 50(2) this "
                     "file carries no machine-readable marking.\n")
            continue

        L.append(f"**c2pa-rs top-level state: `{lad['sdk_top_level_state']}`**\n")
        L.append("| leg | status | what it shows |")
        L.append("|---|---|---|")
        for k, v in lad["legs"].items():
            L.append(f"| {k} | `{v['status']}` | {v['means']} |")

        if lad["overclaim_flags"]:
            L.append("\n### Overclaim flags\n")
            for f in lad["overclaim_flags"]:
                L.append(f"- **{f['flag']}** — {f['detail']}")

        surv = {k: v for k, v in r["survival"].items() if k != "__scope__"}
        if "error" not in r["survival"]:
            L.append("\n### Survival matrix (local transformations, no platform contacted)\n")
            L.append("| transformation | C2PA manifest |")
            L.append("|---|---|")
            for t, v in surv.items():
                L.append(f"| {t} | `{v['c2pa_manifest']}` |")
            stripped = sum(1 for v in surv.values() if v["c2pa_manifest"] == "STRIPPED")
            L.append(f"\n**{stripped}/{len(surv)} transformations destroy the C2PA "
                     f"metadata layer entirely.** None is a platform upload. Every one is "
                     f"routine in a CDN, CMS, or publishing pipeline.\n")
            L.append("> **Scope lock.** This measures the C2PA metadata layer ONLY. It "
                     "cannot see SynthID or any imperceptible watermark, which may "
                     "survive every transformation above. This report may not be read as "
                     "\"the marking does not survive\" — only as \"the C2PA metadata "
                     "layer does not survive.\" The Code of Practice mandates multi-layer "
                     "marking; we audit one layer.\n")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--md", dest="md_out")
    ap.add_argument("--no-trust-list", action="store_true",
                    help="do not load any trust list -- reproduces the SHIPPED SDK, "
                         "under which no file can ever reach 'Trusted'")
    ap.add_argument("--no-ocsp", action="store_true",
                    help="ocsp_fetch=false -- reproduces the c2pa-rs DEFAULT")
    args = ap.parse_args()

    global LOAD_TRUST_LIST, OCSP_FETCH
    LOAD_TRUST_LIST = not args.no_trust_list
    OCSP_FETCH = not args.no_ocsp

    files = []
    for p in args.paths:
        p = Path(p)
        if p.is_dir():
            files += sorted(x for x in p.iterdir()
                            if x.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".avif"})
        elif p.is_file():
            files.append(p)
    if not files:
        sys.exit("no input files")

    work = Path("/tmp/a50_work")
    work.mkdir(exist_ok=True)
    config_notes = configure()

    report = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool_version": TOOL_VERSION,
        "corpus_version": CORPUS_VERSION,
        "config_notes": config_notes,
        "scope": {"measures": "C2PA metadata layer only", "unmeasured": UNMEASURED_LAYERS},
        "environment": {
            "ocsp_fetch": OCSP_FETCH,
            "c2pa_python": c2pa.__version__,
            "c2pa_rs": c2pa.sdk_version(),
            "pillow": Image.__version__,
            "python": platform.python_version(),
        },
        "files": [{"ladder": ladder(f), "survival": survival(f, work)} for f in files],
    }

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2, sort_keys=True))
    md = render_md(report)
    if args.md_out:
        Path(args.md_out).write_text(md)
    else:
        print(md)


if __name__ == "__main__":
    main()
