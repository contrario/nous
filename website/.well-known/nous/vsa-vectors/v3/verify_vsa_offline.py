#!/usr/bin/env python3
"""Offline verification of a NOUS VSA (SLSA Verification Summary Attestation).

Usage: python3 -I verify_vsa_offline.py --expect-signer BASE64
Exit:  0 = PASS, 1 = INTEGRITY, 2 = ENVIRONMENT, 3 = OUTSIDE (NT-GATE-1
       D4). The last line on stdout names the class. No PASS without
       --expect-signer, the VSA signer's key. OUTSIDE: authentic, the
       certificate's verdict is non-conformant and the VSA says so.
Requires: cryptography library only (no NOUS install needed).

Expects in the same directory:
  vsa.intoto.json    the DSSE-wrapped in-toto Statement carrying the VSA
  manifest.json      the signed static-proof manifest      (input attestation)
  trace.json         the signed execution trace            (input attestation)
  conformance.json   the signed conformance certificate    (input attestation)
  coverage.farkas.json   OPTIONAL: the coverage Farkas certificate, present
                         iff the VSA carries a coverageProof leg

Trust model. The VSA is a SUMMARY a consumer who trusts the pinned NOUS VSA
verifier key may rely on to skip re-verification. This verifier does NOT
trust the recorded verdict: it re-derives the conformance status from the
certificate's own obligations and REJECTS a VSA whose verificationResult
disagrees. The trust anchor is the --expect-signer key; a key this
verifier was shipped with (inline or by registry) must equal it. The keyid
in the envelope is an unauthenticated hint and is never used for a decision.

Checks, in order, fail-closed:
  1. DSSE Ed25519 signature over PAE(payloadType, payload) against the
     --expect-signer key. The verified payload bytes are then parsed directly
     (the DSSE spec forbids re-parsing the envelope after verification).
  2. manifest / trace / certificate Ed25519 signatures verify over their
     canonical body bytes.
  3. inputAttestations digests == sha256 of the canonical bodies of the
     manifest / trace / certificate (and coverage.farkas.json when present).
  4. subject.digest == the codegen leg (or source leg) the artifacts name
     (subject-confusion guard).
  5. certificate <-> manifest binding (source/smt_spec/pricing shas, codegen
     leg when present) and certificate <-> trace binding.
  6. policy.digest == the recomputed obligation-set fingerprint.
  7. the verdict is RE-DERIVED from the certificate's obligations; the VSA
     verificationResult MUST match it (zero trust on the recorded string).
  8. when a costProof is present, the cost system is re-derived from the
     certificate's obligations_canon, whose sha256 must equal the
     manifest's signed smt_spec_sha256 and whose cap, ticks and margin
     must equal the manifest's; the cost certificate's constraints must
     equal it before its multipliers are graded. No canon: refused.
  9. when a coverageProof is present, the coverage Farkas certificate is
     re-checked by RATIONAL ARITHMETIC ALONE (fractions; no solver) and its
     sha must match both the manifest and the coverageProof.
 10. when the certificate carries its spec canon: binding, surface,
     assumption discharge and bound transfer are recomputed from
     trace.json (read strictly) and must equal the recorded booleans
     and realized_total; authorization and sequence are not.

SCOPE. PROVES (Z3/Farkas) is reserved for the coverage Farkas leg, which is
re-provable offline here. Everything else is EVIDENCES (Ed25519 authenticity
and sha-equality identity). Out of scope: execution attestation, program
re-derivation from source (the online path), the cost-cap SMT bound (PROVES by
rational arithmetic under the declared per-call token/tick estimates when a
costProof leg is present and verified here, EVIDENCES only otherwise), and
real-world
model faithfulness. The evidence layer is a monitor, not a guard.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).parent

_PINNED_VSA_PUBKEY_B64 = "F0VTtFbd38aQjsqxwQH+arIeK6oGF3lbfUOmNIKZP9U="
_PINNED_REGISTRY_PUBKEY_B64 = "__NOUS_REGISTRY_PINNED_PUBKEY_B64__"
NOUS_VSA_VERIFIER_ID = "https://nous-lang.org/vsa/verifier/v1"

IN_TOTO_STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
VSA_PREDICATE_TYPE = "https://slsa.dev/verification_summary/v1"
DSSE_PAYLOAD_TYPE = "application/vnd.in-toto+json"
NOUS_EXT_KEY = "https://nous-lang.org/vsa/ext/v1"

_BOOLS_V1 = (
    "binding_ok",
    "surface_ok",
    "assumption_discharge_ok",
    "bound_transfer_ok",
    "authorization_ok",
    "trace_signature_ok",
)
_BOOLS_V2 = _BOOLS_V1 + ("sequence_ok",)
_BOOLS_V4 = _BOOLS_V2 + ("codegen_binding_ok",)

_OBLIGATION_NAMES = (
    "binding_ok",
    "surface_ok",
    "assumption_discharge_ok",
    "bound_transfer_ok",
    "authorization_ok",
    "trace_signature_ok",
    "sequence_ok",
    "codegen_binding_ok",
)


def _bools_for(schema_version):
    if schema_version >= 4:
        return _BOOLS_V4
    return _BOOLS_V2 if schema_version >= 2 else _BOOLS_V1


def _fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    return 1


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _pae(payload_type, payload):
    pt = payload_type.encode("utf-8")
    return (
        b"DSSEv1 "
        + str(len(pt)).encode("ascii")
        + b" "
        + pt
        + b" "
        + str(len(payload)).encode("ascii")
        + b" "
        + payload
    )


def _manifest_canonical_body_bytes(doc):
    body = {
        k: v for k, v in doc.items()
        if k not in ("signature", "transparency_log")
    }
    return _canon(body)


def _trace_canonical_body_bytes(doc):
    body = {k: v for k, v in doc.items() if k != "signature"}
    return _canon(body)


def _cert_canonical_body_bytes(doc):
    body = {
        k: v for k, v in doc.items()
        if k not in ("signature", "transparency_log")
    }
    if int(body.get("certificate_schema_version", 1)) < 2:
        body.pop("sequence_ok", None)
    return _canon(body)


def _policy_digest(schema_version):
    fingerprint = {
        "certificate_schema_version": int(schema_version),
        "obligations": sorted(_OBLIGATION_NAMES),
    }
    return hashlib.sha256(_canon(fingerprint)).hexdigest()


def _verify_ed25519(pub_b64, sig_b64, body):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )
    from cryptography.exceptions import InvalidSignature
    try:
        pub = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(pub_b64, validate=True)
        )
        pub.verify(base64.b64decode(sig_b64, validate=True), body)
        return True
    except (InvalidSignature, ValueError):
        return False


def _check_serialized(doc):
    constraints = doc.get("constraints")
    multipliers = doc.get("multipliers")
    if not isinstance(constraints, list) or not isinstance(multipliers, list):
        return False
    if len(constraints) != len(multipliers):
        return False
    lam = []
    for m in multipliers:
        try:
            lam.append(Fraction(m))
        except (ValueError, TypeError, ZeroDivisionError):
            return False
    if any(x < 0 for x in lam):
        return False
    if not any(x > 0 for x in lam):
        return False
    combined = {}
    strict = False
    for x, c in zip(lam, constraints):
        if x == 0:
            continue
        if not isinstance(c, dict):
            return False
        coeffs = c.get("coeffs")
        if not isinstance(coeffs, dict):
            return False
        for k, v in coeffs.items():
            try:
                fv = Fraction(v)
            except (ValueError, TypeError, ZeroDivisionError):
                return False
            combined[k] = combined.get(k, Fraction(0)) + x * fv
        if c.get("strict"):
            strict = True
    for k, v in combined.items():
        if k != "" and v != 0:
            return False
    const = combined.get("", Fraction(0))
    if const > 0:
        return True
    if const == 0 and strict:
        return True
    return False



# --- cost rederive embed (shared text; canonical copy: cost_farkas.py) ---
# Every offline verifier that grades cost.farkas.json carries this region
# byte-for-byte; tests/test_nt_v1_cost_rederive.py names any copy that
# drifts. Standard library only. __nt_v1_cost_rederive_v1__
def _cost_rederive_grade(doc):
    from fractions import Fraction
    constraints = doc.get("constraints")
    multipliers = doc.get("multipliers")
    if not isinstance(constraints, list) or not isinstance(
        multipliers, list
    ):
        return False
    if len(constraints) != len(multipliers):
        return False
    lam = []
    for m in multipliers:
        try:
            lam.append(Fraction(m))
        except (ValueError, TypeError, ZeroDivisionError):
            return False
    if any(x < 0 for x in lam):
        return False
    if not any(x > 0 for x in lam):
        return False
    combined = {}
    strict = False
    for x, c in zip(lam, constraints):
        if x == 0:
            continue
        if not isinstance(c, dict):
            return False
        coeffs = c.get("coeffs")
        if not isinstance(coeffs, dict):
            return False
        for k, v in coeffs.items():
            try:
                fv = Fraction(v)
            except (ValueError, TypeError, ZeroDivisionError):
                return False
            combined[k] = combined.get(k, Fraction(0)) + x * fv
        if c.get("strict"):
            strict = True
    for k, v in combined.items():
        if k != "" and v != 0:
            return False
    const = combined.get("", Fraction(0))
    if const > 0:
        return True
    if const == 0 and strict:
        return True
    return False


def _cost_rederive_parse(canon_text):
    # The closed shapes smt_emit.canonical_str writes for the cost leg:
    # CC, MT, MARGIN, and four A: shapes. Any other A: line refuses.
    # Returns (per_call_by_soul, max_ticks, cap, margin) or a reason.
    import re
    from fractions import Fraction
    nm = r"[^\s()]+"
    rt = r"[0-9]+|\(/ [0-9]+ [0-9]+\)"
    re_cc = re.compile(r"CC:([0-9]+(?:\.[0-9]+)?)\|([A-Z]{3})")
    re_mt = re.compile(r"MT:([0-9]+)")
    re_mg = re.compile(r"MARGIN:([0-9]+)")
    re_pc = re.compile(
        r"A:\(assert \(= cost_(" + nm + r")_per_call \(/ \(\+ \(\* ("
        + rt + r") ([0-9]+)\) \(\* (" + rt + r") ([0-9]+)(?: ("
        + rt + r"))?\)\) 1000000\)\)\)"
    )
    re_tt = re.compile(
        r"A:\(assert \(= cost_(" + nm + r")_total \(\* cost_(" + nm
        + r")_per_call ([0-9]+)\)\)\)"
    )
    re_s1 = re.compile(
        r"A:\(assert \(= total_cost cost_(" + nm + r")_total\)\)"
    )
    re_sn = re.compile(
        r"A:\(assert \(= total_cost \(\+ ((?:cost_" + nm
        + r"_total)(?: cost_" + nm + r"_total)+)\)\)\)"
    )
    re_tok = re.compile(r"cost_(" + nm + r")_total")

    def rate(s):
        if s.startswith("(/ "):
            n, d = s[3:-1].split(" ")
            if int(d) == 0:
                return None
            return Fraction(int(n), int(d))
        return Fraction(int(s))

    head = {}
    per_call = {}
    totals = {}
    sums = []
    for line in canon_text.split("\n"):
        for tag, rx in (("CC", re_cc), ("MT", re_mt), ("MARGIN", re_mg)):
            if line.startswith(tag + ":"):
                if tag in head:
                    return "duplicate " + tag + " line"
                m = rx.fullmatch(line)
                if m is None:
                    return tag + " line outside the closed shape"
                head[tag] = m.group(1)
                break
        if not line.startswith("A:"):
            continue
        m = re_pc.fullmatch(line)
        if m is not None:
            soul = m.group(1)
            r_in, r_out = rate(m.group(2)), rate(m.group(4))
            mult = rate(m.group(6)) if m.group(6) else Fraction(1)
            if r_in is None or r_out is None or mult is None:
                return "zero denominator in a rate"
            if soul in per_call:
                return "duplicate per-call line for soul " + soul
            per_call[soul] = (
                r_in * int(m.group(3)) + r_out * int(m.group(5)) * mult
            ) / 1000000
            continue
        m = re_tt.fullmatch(line)
        if m is not None:
            if m.group(1) != m.group(2):
                return "total line names two souls"
            if m.group(1) in totals:
                return "duplicate total line for soul " + m.group(1)
            totals[m.group(1)] = int(m.group(3))
            continue
        m = re_s1.fullmatch(line)
        if m is not None:
            sums.append([m.group(1)])
            continue
        m = re_sn.fullmatch(line)
        if m is not None:
            sums.append([re_tok.fullmatch(t).group(1)
                         for t in m.group(1).split(" ")])
            continue
        return "A: line outside the closed shapes"
    if "CC" not in head or "MT" not in head:
        return "CC or MT line missing"
    max_ticks = int(head["MT"])
    margin = int(head.get("MARGIN", "0"))
    if max_ticks <= 0:
        return "max_ticks is not positive"
    if not 0 <= margin <= 99:
        return "margin out of range"
    if not per_call:
        return "no per-call cost line"
    if set(per_call) != set(totals):
        return "a soul lacks its per-call or its total line"
    if any(k != max_ticks for k in totals.values()):
        return "a total line multiplies by other than MT"
    if len(sums) != 1:
        return "expected exactly one total_cost line"
    if len(sums[0]) != len(set(sums[0])) or set(sums[0]) != set(per_call):
        return "total_cost does not sum each soul's total once"
    return per_call, max_ticks, Fraction(head["CC"]), margin


def _cost_rederive_leg(manifest, cost_doc, canon_text):
    # Re-derive the cost system from the spec canon the signed manifest
    # names (smt_spec_sha256), require the certificate's constraints to
    # equal it, then grade the multipliers. Pure; returns (bool, reason).
    import hashlib
    import json
    from fractions import Fraction
    if not isinstance(manifest, dict):
        return False, "manifest is not a JSON object"
    if not isinstance(canon_text, str):
        return False, (
            "no spec canon: the cost system cannot be re-derived, so the "
            "cost-cap Farkas certificate is not accepted"
        )
    want = manifest.get("smt_spec_sha256")
    got = hashlib.sha256(canon_text.encode("utf-8")).hexdigest()
    if not isinstance(want, str) or got != want:
        return False, (
            "spec canon sha256 != manifest smt_spec_sha256 (spec canon "
            "tampered or substituted)"
        )
    parsed = _cost_rederive_parse(canon_text)
    if isinstance(parsed, str):
        return False, "spec canon refused: " + parsed
    per_call, max_ticks, cap, margin = parsed
    try:
        man_cap = Fraction(str(manifest.get("cost_cap_usd")))
    except (ValueError, ZeroDivisionError):
        return False, "manifest cost_cap_usd is not a rational"
    if man_cap != cap:
        return False, "spec canon cap != manifest cost_cap_usd"
    man_mt = manifest.get("max_ticks")
    if type(man_mt) is not int or man_mt != max_ticks:
        return False, "spec canon max_ticks != manifest max_ticks"
    man_mg = manifest.get("safety_margin_pct")
    if man_mg is None:
        man_mg = 0
    if type(man_mg) is not int or man_mg != margin:
        return False, "spec canon margin != manifest safety_margin_pct"
    eff = cap if margin == 0 else cap * Fraction(100 - margin, 100)
    mt = Fraction(max_ticks)
    rows = []
    for soul in sorted(per_call):
        pc = "cost_" + soul + "_per_call"
        tt = "cost_" + soul + "_total"
        rows.append(({pc: Fraction(1), "": -per_call[soul]}, False))
        rows.append(({tt: Fraction(1), pc: -mt, "": Fraction(0)}, False))
    total = {"total_cost": Fraction(1), "": Fraction(0)}
    for soul in sorted(per_call):
        total["cost_" + soul + "_total"] = Fraction(-1)
    rows.append((total, False))
    rows.append(({"total_cost": Fraction(-1), "": eff}, True))

    def canon_rows(constraints):
        if not isinstance(constraints, list):
            return None
        out = []
        for c in constraints:
            if not isinstance(c, dict):
                return None
            coeffs = c.get("coeffs")
            if not isinstance(coeffs, dict):
                return None
            try:
                norm = {
                    str(k): str(Fraction(v))
                    for k, v in sorted(coeffs.items())
                }
            except (ValueError, TypeError, ZeroDivisionError):
                return None
            out.append(json.dumps(
                {"coeffs": norm, "strict": bool(c.get("strict"))},
                sort_keys=True, separators=(",", ":"),
            ))
        return sorted(out)

    if not isinstance(cost_doc, dict):
        return False, "cost certificate is not a JSON object"
    want_rows = canon_rows([{"coeffs": r, "strict": s} for r, s in rows])
    got_rows = canon_rows(cost_doc.get("constraints"))
    if got_rows is None or got_rows != want_rows:
        return False, (
            "cost certificate constraints != the cost system re-derived "
            "from the spec canon (substituted or forged certificate)"
        )
    if not _cost_rederive_grade(cost_doc):
        return False, (
            "cost-cap Farkas certificate does NOT prove the bound: the "
            "declared multipliers do not collapse the linear system to a "
            "numeric contradiction (cost overrun or forged certificate)"
        )
    return True, "re-derived from the spec canon, equal, and graded"
# --- end cost rederive embed ---

# __s158_u2a_registry_resolution_v1__
def _canonical_registry_body_bytes(reg):
    body = {
        k: v for k, v in reg.items()
        if k not in ("signature", "rekor_anchor")
    }
    return _canon(body)


def _resolve_pin_from_registry():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )
    from cryptography.exceptions import InvalidSignature
    if _PINNED_REGISTRY_PUBKEY_B64.startswith("__NOUS_REGISTRY_PINNED"):
        return None, "registry pin not provisioned"
    reg_path = ROOT / "verifier-registry.json"
    if not reg_path.is_file():
        return None, "verifier-registry.json not found in bundle"
    try:
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, "verifier-registry.json parse error: " + str(exc)
    if not isinstance(reg, dict):
        return None, "verifier-registry.json is not a JSON object"
    sig = reg.get("signature")
    if not isinstance(sig, dict):
        return None, "registry has no signature block"
    pub_b64 = sig.get("public_key_b64")
    sig_b64 = sig.get("signature_b64")
    if pub_b64 != _PINNED_REGISTRY_PUBKEY_B64:
        return None, "registry signer is not the pinned registry key"
    if not isinstance(sig_b64, str) or not sig_b64:
        return None, "registry signature is incomplete"
    body = _canonical_registry_body_bytes(reg)
    try:
        rpub = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(_PINNED_REGISTRY_PUBKEY_B64, validate=True)
        )
        rpub.verify(base64.b64decode(sig_b64, validate=True), body)
    except (InvalidSignature, ValueError) as exc:
        return None, (
            "registry Ed25519 signature does not verify: " + str(exc)
        )
    pins = reg.get("verifier_pins")
    if not isinstance(pins, list):
        return None, "registry has no verifier_pins"
    found = None
    for pin in pins:
        if not isinstance(pin, dict):
            continue
        if pin.get("verifier_id") == NOUS_VSA_VERIFIER_ID:
            if found is not None:
                return None, (
                    "registry has duplicate pins for this verifier_id"
                )
            found = pin.get("public_key_b64")
    if not isinstance(found, str) or not found:
        return None, "no verifier_pins entry for " + NOUS_VSA_VERIFIER_ID
    return found, ""


def _resolve_vsa_pubkey_shipped():
    inline = None
    if not _PINNED_VSA_PUBKEY_B64.startswith("__NOUS_VSA_PINNED"):
        inline = _PINNED_VSA_PUBKEY_B64
    registry, reg_err = _resolve_pin_from_registry()
    if inline is not None and registry is not None:
        if inline != registry:
            return None, "conflict", (
                "inline pinned VSA key disagrees with the authenticated "
                "registry pin for " + NOUS_VSA_VERIFIER_ID + " "
                "(incoherent bundle: the shipped verifier was pinned to "
                "a key the logged allowlist does not list; rejected)"
            )
        return inline, "inline+registry", ""
    if inline is not None:
        return inline, "inline", ""
    if registry is not None:
        return registry, "registry", ""
    return None, "none", (
        "no VSA pin available: neither an inline pinned key nor a "
        "registry resolution succeeded (" + (reg_err or "no registry")
        + ")"
    )


def _resolve_vsa_pubkey():  # __nt_v3_classes_wire_v1__
    shipped, source, err = _resolve_vsa_pubkey_shipped()
    if source in ("conflict", "none"):
        return None, source, err
    auditor = _v3_pin_b64()
    if shipped is not None and shipped != auditor:
        return None, "conflict", (
            "the key this verifier was shipped with (" + source
            + ") is not the --expect-signer key; rejected"
        )
    return auditor, "auditor", ""


def _verify_dsse(envelope):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )
    from cryptography.exceptions import InvalidSignature

    if not isinstance(envelope, dict):
        return None, "VSA envelope is not a JSON object"
    if envelope.get("payloadType") != DSSE_PAYLOAD_TYPE:
        return None, (
            "VSA payloadType is not " + DSSE_PAYLOAD_TYPE
        )
    payload_b64 = envelope.get("payload")
    signatures = envelope.get("signatures")
    if not isinstance(payload_b64, str) or not payload_b64:
        return None, "VSA payload missing or not a string"
    if not isinstance(signatures, list) or not signatures:
        return None, "VSA envelope has no signatures"
    try:
        payload = base64.b64decode(payload_b64, validate=True)
    except (ValueError, TypeError) as exc:
        return None, "VSA payload is not valid base64: " + str(exc)
    effective_pub_b64, _pin_source, resolve_err = _resolve_vsa_pubkey()
    if resolve_err:
        return None, resolve_err
    try:
        pinned = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(effective_pub_b64, validate=True)
        )
    except (ValueError, TypeError) as exc:
        return None, "resolved VSA key is not valid: " + str(exc)
    pae = _pae(DSSE_PAYLOAD_TYPE, payload)
    verified = False
    for sig in signatures:
        if not isinstance(sig, dict):
            continue
        sig_b64 = sig.get("sig")
        if not isinstance(sig_b64, str) or not sig_b64:
            continue
        try:
            raw_sig = base64.b64decode(sig_b64, validate=True)
        except (ValueError, TypeError):
            continue
        try:
            pinned.verify(raw_sig, pae)
            verified = True
            break
        except InvalidSignature:
            continue
    if not verified:
        return None, (
            "DSSE signature does NOT verify against the pinned NOUS VSA key"
        )
    try:
        statement = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, "verified VSA payload is not valid JSON: " + str(exc)
    if not isinstance(statement, dict):
        return None, "verified VSA payload is not a JSON object"
    return statement, ""


def _load_json(path, label):
    if not path.is_file():
        return None, label + " not found in " + str(ROOT)
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except json.JSONDecodeError as exc:
        return None, label + " parse error: " + str(exc)


# --- conformance recompute embed (shared text; canonical copy: conformance.py) ---
# Every offline conformance verifier carries this region byte-for-byte;
# tests/test_nt_v2_recompute.py names any copy that drifts. Standard
# library only. It recomputes the cost obligations (NT-GATE-1 D6 (i))
# from trace.json and the spec canon the certificate carries, bound by
# sha256 to the manifest's smt_spec_sha256. __nt_v2_recompute_v1__
_CONF_RC_MAX_BYTES = 16 * 1024 * 1024
_CONF_RC_MAX_DEPTH = 32
_CONF_RC_MAX_DIGITS = 64
_CONF_RC_KINDS = ("llm_call", "tool_call", "message", "gated_action")
_CONF_RC_SCOPE = (
    "binding_ok", "surface_ok", "assumption_discharge_ok",
    "bound_transfer_ok",
)


def _conf_rc_load(raw):
    # Strict JSON: UTF-8, non-ASCII only inside strings, bounded size
    # and nesting, no duplicate key, no NaN or Infinity, no float.
    # Returns (doc, "") or (None, why).
    import json
    if not isinstance(raw, (bytes, bytearray)):
        return None, "input is not bytes"
    if len(raw) > _CONF_RC_MAX_BYTES:
        return None, "larger than %d bytes" % _CONF_RC_MAX_BYTES
    try:
        text = bytes(raw).decode("utf-8")
    except UnicodeDecodeError:
        return None, "not UTF-8"
    depth = 0
    in_str = False
    esc = False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ord(ch) > 127:
            return None, "non-ASCII outside a string"
        elif ch in "[{":
            depth += 1
            if depth > _CONF_RC_MAX_DEPTH:
                return None, "nested deeper than %d" % _CONF_RC_MAX_DEPTH
        elif ch in "]}":
            depth -= 1

    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError("duplicate key " + repr(k))
            out[k] = v
        return out

    def no_constant(name):
        raise ValueError("non-finite number " + name)

    def no_float(s):
        raise ValueError("non-integer number " + s)

    try:
        doc = json.loads(text, object_pairs_hook=pairs,
                         parse_constant=no_constant, parse_float=no_float)
    except (ValueError, RecursionError) as exc:
        return None, str(exc)
    return doc, ""


def _conf_rc_rational(s):
    # "123" or "(/ 1 2)" -> Fraction; None outside the closed shape.
    import re
    from fractions import Fraction
    m = re.fullmatch(r"([0-9]+)|\(/ ([0-9]+) ([0-9]+)\)", s)
    if m is None:
        return None
    parts = [g for g in m.groups() if g is not None]
    if any(len(p) > _CONF_RC_MAX_DIGITS for p in parts):
        return None
    if m.group(1) is not None:
        return Fraction(int(m.group(1)))
    if int(m.group(3)) == 0:
        return None
    return Fraction(int(m.group(2)), int(m.group(3)))


def _conf_rc_decimal(s):
    # A decimal string, as Decimal prints one ("0.00105", "1E-7") ->
    # Fraction; None otherwise.
    import re
    from fractions import Fraction
    if not isinstance(s, str):
        return None
    m = re.fullmatch(r"(-?)([0-9]+)(?:\.([0-9]+))?(?:E([-+]?[0-9]{1,3}))?", s)
    if m is None or len(m.group(2)) + len(m.group(3) or "") > \
            _CONF_RC_MAX_DIGITS:
        return None
    frac = m.group(3) or ""
    v = Fraction(int(m.group(2) + frac), 10 ** len(frac))
    if m.group(4) is not None:
        v *= Fraction(10) ** int(m.group(4))
    return -v if m.group(1) else v


def _conf_rc_text(fr):
    # Exact decimal text of a Fraction whose denominator is 2^a 5^b.
    sign = "-" if fr < 0 else ""
    x = abs(fr)
    k = 0
    while x.denominator != 1 and k < 4 * _CONF_RC_MAX_DIGITS:
        x *= 10
        k += 1
    if x.denominator != 1:
        return sign + str(abs(fr))
    digits = str(x.numerator).rjust(k + 1, "0")
    if k == 0:
        return sign + digits
    head, tail = digits[:-k], digits[-k:].rstrip("0")
    return sign + head + ("." + tail if tail else "")


def _conf_rc_parse_canon(canon_text):
    # Closed shapes of smt_emit.canonical_str. Returns a dict, or a str
    # naming the first line outside the shapes.
    import re
    from fractions import Fraction
    if not isinstance(canon_text, str):
        return "spec canon is not text"
    # The grammar's NAME class (nous.lark): Latin and U+0370..U+03FF.
    gr = r"\u0370-\u03FF"
    nb = r"[A-Za-z_" + gr + r"][A-Za-z0-9_" + gr + r"]*"
    nm = "(" + nb + ")"
    rt = r"([0-9]+|\(/ [0-9]+ [0-9]+\))"
    re_pc = re.compile(
        r"A:\(assert \(= cost_" + nm + r"_per_call \(/ \(\+ \(\* " + rt
        + r" ([0-9]+)\) \(\* " + rt + r" ([0-9]+)(?: " + rt
        + r")?\)\) 1000000\)\)\)")
    re_tt = re.compile(
        r"A:\(assert \(= cost_" + nm + r"_total \(\* cost_" + nm
        + r"_per_call ([0-9]+)\)\)\)")
    re_t1 = re.compile(r"A:\(assert \(= total_cost cost_" + nm
                       + r"_total\)\)")
    re_tn = re.compile(r"A:\(assert \(= total_cost \(\+ ((?:cost_"
                       + nb + r"_total ?)+)\)\)\)")
    out = {"souls": {}, "ga": set(), "de": set()}
    seen = set()
    totals = {}
    sum_line = None
    for line in canon_text.split("\n"):
        tag, sep, rest = line.partition(":")
        if not sep:
            return "a line without a tag"
        if tag in ("CC", "MT", "MARGIN", "SS", "PS"):
            if tag in seen:
                return "duplicate " + tag + " line"
            seen.add(tag)
        if tag == "CC":
            m = re.fullmatch(r"([0-9]+)(?:\.([0-9]+))?\|([A-Z]{3})", rest)
            if m is None or len(m.group(1) + (m.group(2) or "")) > \
                    _CONF_RC_MAX_DIGITS:
                return "CC line outside the closed shape"
            out["cap"] = _conf_rc_decimal(
                m.group(1) + ("." + m.group(2) if m.group(2) else ""))
            out["currency"] = m.group(3)
        elif tag == "MT":
            if not re.fullmatch(r"[0-9]{1,9}", rest):
                return "MT line outside the closed shape"
            out["mt"] = int(rest)
        elif tag == "MARGIN":
            if not re.fullmatch(r"[0-9]{1,2}", rest):
                return "MARGIN line outside the closed shape"
        elif tag in ("SS", "PS"):
            if not re.fullmatch(r"[0-9a-f]{64}", rest):
                return tag + " line outside the closed shape"
            out[tag.lower()] = rest
        elif tag == "GA":
            out["ga"].add(rest)
        elif tag == "DE":
            out["de"].add(rest)
        elif tag == "A":
            m = re_pc.fullmatch(line)
            if m is not None:
                soul = m.group(1)
                if soul in out["souls"]:
                    return "duplicate per-call line for " + soul
                rin, rout = _conf_rc_rational(m.group(2)), \
                    _conf_rc_rational(m.group(4))
                mult = Fraction(1) if m.group(6) is None else \
                    _conf_rc_rational(m.group(6))
                if rin is None or rout is None or mult is None or \
                        len(m.group(3)) > 18 or len(m.group(5)) > 18:
                    return "per-call line outside the closed shape"
                out["souls"][soul] = (rin, int(m.group(3)), rout,
                                      int(m.group(5)), mult)
                continue
            m = re_tt.fullmatch(line)
            if m is not None:
                if m.group(1) != m.group(2) or m.group(1) in totals:
                    return "total line outside the closed shape"
                totals[m.group(1)] = int(m.group(3))
                continue
            m = re_t1.fullmatch(line) or re_tn.fullmatch(line)
            if m is not None:
                if sum_line is not None:
                    return "duplicate total_cost line"
                sum_line = sorted(re.findall(
                    r"cost_(" + nb + r")_total", m.group(1)
                    if m.re is re_tn else "cost_" + m.group(1) + "_total"))
                continue
            return "A: line outside the closed shapes"
        elif tag not in ("NV", "EV", "W", "D", "R", "O", "SD", "SA", "GQ"):
            return "unknown tag " + tag
    for need in ("cap", "mt", "ss", "ps"):
        if need not in out:
            return "spec canon lacks " + need.upper()
    if sorted(totals) != sorted(out["souls"]) or (
            out["souls"] and sum_line != sorted(out["souls"])):
        return "per-call, total and total_cost lines do not match"
    if any(t != out["mt"] for t in totals.values()):
        return "a total line multiplies by other than MT"
    return out


def _conf_rc_obligations(manifest, trace, canon_text):
    # The four obligations in scope, recomputed. ("refused", why) where
    # the online path raises a precondition, else
    # ("ok", {name: bool}, realized_total Fraction, [errors]).
    import hashlib
    from fractions import Fraction
    c = _conf_rc_parse_canon(canon_text)
    if isinstance(c, str):
        return ("refused", "spec canon refused: " + c)
    if not c["souls"]:
        return ("refused", "spec canon declares no costed soul")
    if not isinstance(manifest, dict) or not isinstance(trace, dict):
        return ("refused", "manifest or trace is not a JSON object")
    events = trace.get("events")
    if not isinstance(events, list):
        return ("refused", "trace has no event list")
    norm = []
    for i, ev in enumerate(events):
        if not isinstance(ev, dict):
            return ("refused", "event %d is not an object" % i)
        e = {}
        for key, dflt in (("seq", None), ("tick", None),
                          ("input_tokens", 0), ("output_tokens", 0)):
            v = ev.get(key, dflt)
            if type(v) is not int or v < 0:
                return ("refused", "event %d %s is not a non-negative "
                        "integer" % (i, key))
            e[key] = v
        for key in ("soul", "kind"):
            v = ev.get(key)
            if not isinstance(v, str) or not v:
                return ("refused", "event %d %s is not text" % (i, key))
            e[key] = v
        tc = _conf_rc_decimal(ev.get("tool_cost", "0"))
        if tc is None:
            return ("refused", "event %d tool_cost is not a decimal" % i)
        e["tool_cost"] = tc
        a = ev.get("action")
        if a is not None and not isinstance(a, str):
            return ("refused", "event %d action is not text" % i)
        e["action"] = a
        norm.append(e)
    souls, ga, de = c["souls"], c["ga"], c["de"]
    for e in norm:
        s = "event seq=%d " % e["seq"]
        if e["kind"] not in _CONF_RC_KINDS:
            return ("refused", s + "has an unknown kind")
        if e["soul"] not in souls:
            return ("refused", s + "names a soul the spec never declared")
        if e["kind"] == "tool_call" and e["tool_cost"] != 0:
            return ("refused", s + "is a priced tool_call")
        if e["kind"] == "gated_action" and e["action"] is not None and \
                e["action"] not in ga:
            return ("refused", s + "gated action is not declared")
        if e["action"] is not None and e["action"] in ga and \
                e["kind"] != "gated_action":
            return ("refused", s + "is a declared gated action recorded "
                    "under another kind")
        if e["kind"] == "tool_call" and de:
            if e["action"] is None or e["action"] not in de:
                return ("refused", s + "tool_call is outside the "
                        "declared events")
    ek = trace.get("evidence_kind")
    cb = trace.get("cost_binding")
    pti = trace.get("provider_token_integrity")
    if ek not in (None, "envelope", "witnessed_run") or cb not in (
            None, "envelope", "realized") or pti not in (
            None, "unattested", "tee_attested", "unverifiable"):
        return ("refused", "trust field outside its vocabulary")
    if sum(1 for v in (ek, cb, pti) if v is not None) not in (0, 3):
        return ("refused", "trust triple is partial (all three or none)")
    if (cb == "realized") != (ek == "witnessed_run"):
        return ("refused", "cost_binding and evidence_kind disagree")
    errors = []
    sha = hashlib.sha256(canon_text.encode("utf-8")).hexdigest()
    binding = (
        sha == manifest.get("smt_spec_sha256")
        and c["ss"] == manifest.get("source_sha256")
        and c["ps"] == manifest.get("pricing_sha256")
        and trace.get("source_sha256") == manifest.get("source_sha256")
        and trace.get("smt_spec_sha256") == manifest.get("smt_spec_sha256")
        and trace.get("pricing_sha256") == manifest.get("pricing_sha256")
    )
    if not binding:
        errors.append("binding: canon, manifest and trace shas disagree")
    discharge = True
    calls = {name: 0 for name in souls}
    max_tick = -1
    realized = Fraction(0)
    for e in norm:
        rin, max_in, rout, max_out, mult = souls[e["soul"]]
        max_tick = max(max_tick, e["tick"])
        if e["input_tokens"] > max_in or e["output_tokens"] > max_out:
            discharge = False
            errors.append("discharge: seq=%d tokens over the declared "
                          "bound" % e["seq"])
        if e["kind"] == "llm_call":
            calls[e["soul"]] += 1
            realized += (rin * e["input_tokens"]
                         + rout * e["output_tokens"] * mult) / 1000000
    for name, n in sorted(calls.items()):
        if n > c["mt"]:
            discharge = False
            errors.append("discharge: soul %s made %d llm_calls > %d"
                          % (name, n, c["mt"]))
    if max_tick >= c["mt"]:
        discharge = False
        errors.append("discharge: max tick %d >= %d" % (max_tick, c["mt"]))
    bound = realized <= c["cap"]
    if not bound:
        errors.append("bound_transfer: realized_total %s > cost_cap %s"
                      % (_conf_rc_text(realized), _conf_rc_text(c["cap"])))
    return ("ok", {"binding_ok": binding, "surface_ok": True,
                   "assumption_discharge_ok": discharge,
                   "bound_transfer_ok": bound}, realized, errors)


def _conf_recompute(manifest, cert, trace, canon_text):
    # ("absent", {}) without a canon; ("refused", {"reason"}); or
    # ("recomputed", {"line", "disagree", ...}). Reads no recorded
    # boolean to decide an obligation; compares them after.
    if canon_text is None:
        return ("absent", {})
    if not isinstance(cert, dict):
        return ("refused", {"reason": "certificate is not a JSON object"})
    r = _conf_rc_obligations(manifest, trace, canon_text)
    if r[0] == "refused":
        return ("refused", {"reason": r[1]})
    _ok, ob, realized, errors = r
    cap = _conf_rc_parse_canon(canon_text)["cap"]
    disagree = []
    for name in _CONF_RC_SCOPE:
        if name in cert and bool(cert[name]) != ob[name]:
            disagree.append(
                "certificate records %s=%s but recomputed from trace.json "
                "and the spec canon it is %s (recorded verdict disagrees "
                "with recomputation)" % (name, bool(cert[name]), ob[name]))
    rec = _conf_rc_decimal(cert.get("realized_total"))
    if rec != realized:
        disagree.append(
            "certificate records realized_total=%s but recomputed from "
            "trace.json and the spec canon it is %s (recorded verdict "
            "disagrees with recomputation)"
            % (cert.get("realized_total"), _conf_rc_text(realized)))
    line = (
        "RECOMPUTED (cost obligations, D6 (i)) from trace.json and the "
        "certificate's spec canon, equal to the recorded booleans: "
        + ", ".join("%s=%s" % (n, ob[n]) for n in _CONF_RC_SCOPE)
        + "; realized_total %s, cost_cap %s"
        % (_conf_rc_text(realized), _conf_rc_text(cap)))
    return ("recomputed", {"line": line, "disagree": disagree,
                           "obligations": ob, "realized_total": realized,
                           "errors": errors})
# --- end conformance recompute embed ---


# --- v3 verdict classes embed (shared text; canonical copy: conformance_verifier.py) ---
# Every offline verifier in NT-GATE-1 V3's scope carries this region
# byte-for-byte; tests/test_nt_v3_classes.py names any copy that drifts.
# Exit classes (D4 as amended): 0 PASS, 1 INTEGRITY, 2 ENVIRONMENT,
# 3 OUTSIDE; the last line on stdout names the class. No PASS without
# a public key the auditor supplies (--expect-signer). Standard
# library only. __nt_v3_classes_v1__
_V3_CLASSES = {0: "PASS", 1: "INTEGRITY", 2: "ENVIRONMENT", 3: "OUTSIDE"}
_V3_STATE = {"pin": None, "flags": frozenset(), "keys": {},
             "outside": False}
_V3_NO_PIN = (
    "no --expect-signer: this verifier gives no PASS without a public "
    "key the auditor supplies from outside the evidence"
)
_V3_NOT_CLAIMED = {
    "runtime": (
        "completeness: that the recorded events are all the events; the "
        "recorder runs in the operator's process",
        "token counts: provider-reported; unattested unless "
        "provider_token_integrity is tee_attested, and no receipt is "
        "verified here",
        "the served model: the recorder records the requested model",
        "tool labels in a world that declares no events: unchecked",
        "obligations outside the recomputed scope: reported as not "
        "recomputed, never folded into PASS",
        "prices outside the table's rate model: cache writes, batch "
        "tiers, failed attempts",
        "time: that the declared program existed before the run",
        "identity: the key names a party only through the auditor's pin",
        "the operator's honesty: the operator holds the key, runs the "
        "recorder and writes the numbers",
        "control: none. A monitor.",
        "regulatory status: none",
    ),
    "dossier": (
        "declared estimates: the cost bound is over the declared token "
        "estimates and prices; a dossier observes no run",
        "identity: the key names a party only through the auditor's pin",
        "the operator's honesty: the operator writes the source and holds "
        "the key",
        "control: none. A monitor.",
        "regulatory status: none",
    ),
}


def _v3_pin_raw(b64):
    import base64
    if not isinstance(b64, str):
        return None
    try:
        raw = base64.b64decode(b64, validate=True)
    except (ValueError, TypeError):
        return None
    return raw if len(raw) == 32 else None


def _v3_args(argv, flags=(), keyed=()):
    # Exactly one --expect-signer, each option of keyed at most once,
    # each with a base64 raw 32-byte key; each of flags at most once;
    # nothing else. Returns (pin, flags_seen, keys, "") or
    # (None, None, None, why).
    keys = {}
    seen = set()
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--expect-signer" or a in keyed:
            if a in keys or i + 1 >= len(argv):
                return None, None, None, (
                    a + " must be given once, with a key")
            raw = _v3_pin_raw(argv[i + 1])
            if raw is None:
                return None, None, None, (
                    a + " is not a base64 raw 32-byte Ed25519 public key")
            keys[a] = raw
            i += 2
            continue
        if a in flags and a not in seen:
            seen.add(a)
            i += 1
            continue
        return None, None, None, "unexpected argument " + repr(a)
    pin = keys.pop("--expect-signer", None)
    if pin is None:
        return None, None, None, _V3_NO_PIN
    return pin, frozenset(seen), keys, ""


def _v3_key(opt):
    # The auditor's key for opt, else the --expect-signer key.
    return _V3_STATE["keys"].get(opt) or _V3_STATE["pin"]


def _v3_is_pinned(pub_b64, opt="--expect-signer"):
    import base64
    pin = _v3_key(opt)
    if pin is None or not isinstance(pub_b64, str):
        return False
    try:
        return base64.b64decode(pub_b64, validate=True) == pin
    except (ValueError, TypeError):
        return False


def _v3_pin_b64(opt="--expect-signer"):
    import base64
    return base64.b64encode(_v3_key(opt)).decode("ascii")


def _v3_manifest_body(doc):
    import json
    body = {
        k: v for k, v in doc.items()
        if k not in ("signature", "transparency_log")
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode(
        "utf-8")


def _v3_not_claimed(kind):
    print()
    print("NOT CLAIMED (NT-GATE-1 5.5):")
    for line in _V3_NOT_CLAIMED[kind]:
        print("  - " + line)


def _v3_outside_manifest(manifest):
    # Marks the run OUTSIDE; main still returns 0 after every remaining
    # check, and _v3_run turns that 0 into 3. A later failing check
    # still returns 1 (INTEGRITY first).
    _V3_STATE["outside"] = True
    v = manifest.get("verdict")
    print()
    print("VERDICT: OUTSIDE (authentic manifest under the expected key; "
          "the solver verdict is " + repr(v) + ", not 'proven', so the "
          "declared bound is not established)")
    print("  world:      " + str(manifest.get("world_name", "?")))
    print("  verdict:    " + str(v))


def _v3_run(main_fn, flags=(), pass_argv=False, usage="", keyed=()):
    import sys
    pin, seen, keys, why = _v3_args(sys.argv[1:], flags, keyed)
    if why:
        if usage:
            print(usage, file=sys.stderr)
        print("ERROR: " + why, file=sys.stderr)
        print("CLASS: ENVIRONMENT")
        return 2
    _V3_STATE["pin"] = pin
    _V3_STATE["flags"] = seen
    _V3_STATE["keys"] = keys
    try:
        rc = main_fn(sys.argv[1:]) if pass_argv else main_fn()
    except SystemExit as exc:
        rc = exc.code if isinstance(exc.code, int) else 1
    except ImportError as exc:
        print("ERROR: a module this verifier needs is missing (" + str(exc)
              + "); install: pip install 'cryptography>=42'",
              file=sys.stderr)
        rc = 2
    except Exception as exc:
        print("FAIL: unhandled " + type(exc).__name__ + ": " + str(exc),
              file=sys.stderr)
        rc = 1
    if isinstance(rc, bool) or rc not in _V3_CLASSES:
        rc = 1
    if rc == 0 and _V3_STATE["outside"]:
        rc = 3
    print("CLASS: " + _V3_CLASSES[rc])
    return rc
# --- end v3 verdict classes embed ---


def main():
    try:
        import cryptography  # noqa: F401
    except ImportError:
        print(
            "ERROR: cryptography library required.\n"
            "Install: pip install 'cryptography>=42'",
            file=sys.stderr,
        )
        return 2

    if _PINNED_VSA_PUBKEY_B64.startswith("__NOUS_VSA_PINNED") and _PINNED_REGISTRY_PUBKEY_B64.startswith("__NOUS_REGISTRY_PINNED"):
        print(
            "ERROR: this verifier was provisioned with neither an inline VSA "
            "key nor a pinned registry key; re-emit it with a pinned VSA key "
            "and/or a pinned registry key.",
            file=sys.stderr,
        )
        return 2

    envelope, err = _load_json(ROOT / "vsa.intoto.json", "vsa.intoto.json")
    if err:
        return _fail(err)

    statement, err = _verify_dsse(envelope)
    if err:
        return _fail(err)
    print("OK   VSA DSSE Ed25519 signature verified against pinned key")

    if statement.get("_type") != IN_TOTO_STATEMENT_TYPE:
        return _fail("statement _type is not " + IN_TOTO_STATEMENT_TYPE)
    if statement.get("predicateType") != VSA_PREDICATE_TYPE:
        return _fail("predicateType is not " + VSA_PREDICATE_TYPE)
    predicate = statement.get("predicate")
    subject = statement.get("subject")
    if not isinstance(predicate, dict):
        return _fail("statement predicate is not an object")
    if not isinstance(subject, list) or not subject:
        return _fail("statement subject is empty")

    manifest, err = _load_json(ROOT / "manifest.json", "manifest.json")
    if err:
        return _fail(err)
    trace, err = _load_json(ROOT / "trace.json", "trace.json")
    if err:
        return _fail(err)
    cert, err = _load_json(ROOT / "conformance.json", "conformance.json")
    if err:
        return _fail(err)
    if isinstance(cert, dict) and cert.get("obligations_canon") is not None:  # __nt_v3_classes_wire_v1__
        trace, _why = _conf_rc_load((ROOT / "trace.json").read_bytes())
        if trace is None:
            return _fail("trace.json refused: " + _why)

    msig = manifest.get("signature")
    if not isinstance(msig, dict):
        return _fail("manifest has no signature block")
    if not _verify_ed25519(
        msig.get("public_key_b64", ""),
        msig.get("signature_b64", ""),
        _manifest_canonical_body_bytes(manifest),
    ):
        return _fail("manifest Ed25519 signature does NOT verify")

    csig = cert.get("signature")
    if not isinstance(csig, dict):
        return _fail("certificate has no signature block")
    if csig.get("algorithm") != "ed25519":
        return _fail("certificate signature algorithm is not ed25519")
    if not _verify_ed25519(
        csig.get("public_key_b64", ""),
        csig.get("signature_b64", ""),
        _cert_canonical_body_bytes(cert),
    ):
        return _fail("certificate Ed25519 signature does NOT verify")

    tsig = trace.get("signature")
    if not isinstance(tsig, dict):
        return _fail("trace has no signature block")
    if tsig.get("algorithm") != "ed25519":
        return _fail("trace signature algorithm is not ed25519")
    if not _verify_ed25519(
        tsig.get("public_key_b64", ""),
        tsig.get("signature_b64", ""),
        _trace_canonical_body_bytes(trace),
    ):
        return _fail("trace Ed25519 signature does NOT verify")
    print("OK   manifest / certificate / trace Ed25519 signatures verified")

    input_attestations = predicate.get("inputAttestations")
    if not isinstance(input_attestations, list):
        return _fail("predicate.inputAttestations is not a list")
    ia = {}
    for entry in input_attestations:
        if not isinstance(entry, dict):
            return _fail("an inputAttestation is not an object")
        uri = entry.get("uri")
        digest = entry.get("digest")
        if not isinstance(uri, str) or not isinstance(digest, dict):
            return _fail("an inputAttestation is malformed")
        ia[uri] = digest.get("sha256")

    bindings = (
        ("manifest.json", _manifest_canonical_body_bytes(manifest)),
        ("trace.json", _trace_canonical_body_bytes(trace)),
        ("conformance.json", _cert_canonical_body_bytes(cert)),
    )
    for uri, body in bindings:
        want = ia.get(uri)
        got = hashlib.sha256(body).hexdigest()
        if want != got:
            return _fail(
                "inputAttestation digest mismatch for " + uri
                + ": VSA=" + str(want)[:16] + "... actual=" + got[:16] + "..."
                + " (VSA names different bytes than the shipped artifact)"
            )
    print("OK   inputAttestations bind the shipped manifest/trace/cert bytes")

    ext = predicate.get(NOUS_EXT_KEY)
    if not isinstance(ext, dict):
        return _fail("predicate is missing the NOUS extension block")
    subj_sha = subject[0].get("digest", {}).get("sha256")
    kind = ext.get("subjectDigestKind")
    if kind == "codegen_sha256":
        cert_cg = cert.get("codegen_sha256")
        if cert_cg is None:
            return _fail(
                "subjectDigestKind=codegen_sha256 but certificate carries "
                "no codegen_sha256 (subject confusion)"
            )
        if subj_sha != cert_cg:
            return _fail(
                "subject.digest != certificate codegen_sha256 "
                "(VSA names a different compiled program than it certifies)"
            )
        man_cg = manifest.get("codegen_sha256")
        tr_cg = trace.get("codegen_sha256")
        if man_cg is not None and man_cg != subj_sha:
            return _fail("subject.digest != manifest codegen_sha256")
        if tr_cg is not None and tr_cg != subj_sha:
            return _fail("subject.digest != trace codegen_sha256")
    elif kind == "source_sha256":
        if subj_sha != manifest.get("source_sha256"):
            return _fail("subject.digest != manifest source_sha256")
        if subj_sha != cert.get("source_sha256"):
            return _fail("subject.digest != certificate source_sha256")
    else:
        return _fail("unknown subjectDigestKind: " + repr(kind))
    print("OK   subject.digest matches the program the artifacts name")

    for fld in ("source_sha256", "smt_spec_sha256", "pricing_sha256"):
        if cert.get(fld) != manifest.get(fld):
            return _fail(
                "cert." + fld + " != manifest." + fld
                + " (certificate not bound to this manifest)"
            )
    cert_cg = cert.get("codegen_sha256")
    if cert_cg is not None:
        man_cg = manifest.get("codegen_sha256")
        tr_cg = trace.get("codegen_sha256")
        if man_cg is not None and man_cg != cert_cg:
            return _fail("cert.codegen_sha256 != manifest.codegen_sha256")
        if tr_cg is not None and tr_cg != cert_cg:
            return _fail("cert.codegen_sha256 != trace.codegen_sha256")
    trace_sha = hashlib.sha256(
        _trace_canonical_body_bytes(trace)
    ).hexdigest()
    if cert.get("trace_sha256") != trace_sha:
        return _fail("cert.trace_sha256 != sha256(trace canonical body)")
    print("OK   certificate is bound to this manifest and this trace")

    schema_v = int(cert.get("certificate_schema_version", 1))
    policy = predicate.get("policy", {})
    pol_digest = policy.get("digest", {}).get("sha256") if isinstance(
        policy, dict
    ) else None
    if pol_digest != _policy_digest(schema_v):
        return _fail(
            "policy.digest != recomputed obligation-set fingerprint "
            "(the VSA names a different policy than the certificate's)"
        )

    bools = _bools_for(schema_v)
    missing = [b for b in bools if b not in cert]
    if missing:
        return _fail("certificate missing obligation fields: " + str(missing))
    derived = all(bool(cert[b]) for b in bools)
    recorded = bool(cert.get("conformant"))
    if derived != recorded:
        return _fail(
            "certificate conformant=" + str(recorded) + " but its "
            + str(len(bools)) + " obligations imply " + str(derived)
            + " (inconsistent certificate)"
        )
    vsa_result = predicate.get("verificationResult")
    expected = "PASSED" if derived else "FAILED"
    if vsa_result != expected:
        return _fail(
            "VSA verificationResult=" + repr(vsa_result) + " but the "
            + str(len(bools)) + " certificate obligations independently "
            "derive " + expected + " (the recorded verdict LIES; rejected)"
        )
    print(
        "OK   verdict re-derived from " + str(len(bools))
        + " obligations; VSA verificationResult matches (not trusted blindly)"
    )

    cost_proven_offline = False  # __s170_leg4_cost_scope_v1__
    cp = ext.get("costProof")
    if cp is not None:
        cp_sha = cp.get("sha256")
        man_cost = manifest.get("cost_farkas_sha256")
        cost_path = ROOT / "cost.farkas.json"
        if not cost_path.is_file():
            return _fail(
                "costProof present but cost.farkas.json is missing"
            )
        cost_bytes = cost_path.read_bytes()
        cost_sha = hashlib.sha256(cost_bytes).hexdigest()
        if cost_sha != cp_sha:
            return _fail(
                "cost.farkas.json sha != costProof.sha256 "
                "(cost-cap Farkas certificate tampered or substituted)"
            )
        if man_cost is not None and cost_sha != man_cost:
            return _fail(
                "cost.farkas.json sha != manifest.cost_farkas_sha256"
            )
        ia_cost = ia.get("cost.farkas.json")
        if ia_cost is not None and ia_cost != cost_sha:
            return _fail(
                "cost.farkas.json sha != its inputAttestation digest"
            )
        try:
            cost_doc = json.loads(cost_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return _fail("cost.farkas.json parse error: " + str(exc))
        # __nt_w_vsa_cost_rederive_v1__ re-derive, then grade
        _cost_ok, _cost_why = _cost_rederive_leg(
            manifest, cost_doc, cert.get("obligations_canon")
        )
        if not _cost_ok:
            return _fail(_cost_why)
        print(
            "OK   cost system re-derived from the certificate's "
            "obligations_canon (sha256 = signed smt_spec_sha256) and "
            "equal to the certificate"
        )
        cost_proven_offline = True
        print(
            "OK   cost-cap Farkas certificate PROVEN offline by rational "
            "arithmetic, no solver, under declared per-call token/tick "
            "(contradiction: " + str(cost_doc.get("contradiction", "?")) + ")"
        )

    proven_offline = False
    cov = ext.get("coverageProof")
    if cov is not None:
        cov_sha = cov.get("sha256")
        man_far = manifest.get("coverage_farkas_sha256")
        far_path = ROOT / "coverage.farkas.json"
        if not far_path.is_file():
            return _fail(
                "coverageProof present but coverage.farkas.json is missing"
            )
        far_bytes = far_path.read_bytes()
        far_sha = hashlib.sha256(far_bytes).hexdigest()
        if far_sha != cov_sha:
            return _fail(
                "coverage.farkas.json sha != coverageProof.sha256 "
                "(Farkas certificate tampered or substituted)"
            )
        if man_far is not None and far_sha != man_far:
            return _fail(
                "coverage.farkas.json sha != manifest.coverage_farkas_sha256"
            )
        ia_far = ia.get("coverage.farkas.json")
        if ia_far is not None and ia_far != far_sha:
            return _fail(
                "coverage.farkas.json sha != its inputAttestation digest"
            )
        try:
            far_doc = json.loads(far_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return _fail("coverage.farkas.json parse error: " + str(exc))
        if not _check_serialized(far_doc):
            return _fail(
                "Farkas certificate does NOT prove unsat: the declared "
                "multipliers do not collapse the linear system to a numeric "
                "contradiction (coverage gap or forged certificate)"
            )
        proven_offline = True
        print(
            "OK   coverage Farkas certificate PROVEN offline by rational "
            "arithmetic, no solver (contradiction: "
            + str(far_doc.get("contradiction", "?")) + ")"
        )

    _rc_status, _rc = _conf_recompute(  # __nt_v3_classes_wire_v1__
        manifest, cert, trace, cert.get("obligations_canon")
    )
    if _rc_status == "refused":
        return _fail("recomputation refused: " + _rc["reason"])
    if _rc_status == "recomputed":
        if _rc["disagree"]:
            return _fail(_rc["disagree"][0])
        print("OK   " + _rc["line"])
        print("NOT RECOMPUTED: authorization_ok, sequence_ok (the "
              "certificate's recorded booleans)")
    else:
        print("NOT RECOMPUTED: no spec canon in the certificate; the "
              "obligations are the certificate's recorded booleans")
    print()
    verdict = "PASS" if derived else "OUTSIDE"
    print("VERDICT: " + verdict + " (NOUS VSA, offline, --expect-signer key"
          + ("" if derived else "; authentic, the bound was not held")
          + ")")
    print("  world:            " + str(cert.get("world_name", "?")))
    print("  verificationResult: " + str(vsa_result))
    print("  verifiedLevels:   " + str(predicate.get("verifiedLevels")))
    print("  nous_version:     " + str(cert.get("nous_version", "?")))
    print("  issued_utc:       " + str(cert.get("issued_utc", "?")))
    print("  schema_version:   " + str(schema_v))
    pv = ext.get("policyViolations") or []
    if pv:
        print("  policy violations:")
        for v in pv:
            print("    - " + str(v.get("name")) + ": " + str(
                v.get("description")
            ))
    print()
    print("SCOPE (what this verdict cryptographically asserts):")
    print(
        "  EVIDENCES (Ed25519 authenticity + sha-equality identity): the VSA "
        "is signed by the --expect-signer key; manifest/trace/certificate "
        "are these exact signed bytes; the verdict was re-derived from the "
        "eight obligations, not trusted from the recorded string."
    )
    print(
        "  EVIDENCES (registry resolution): when the VSA public key is "
        "resolved from the bundled verifier-registry.json, that registry is "
        "Ed25519-verified against the pinned NOUS registry key and the pin "
        "is matched by verifier_id; this EVIDENCES logged-allowlist "
        "membership of the VSA identity. The registry Rekor v2 anchor "
        "travels in the bundle but is NOT re-derived here (toolchain-tier: "
        "cryptography and stdlib cannot reconstruct the inclusion proof). "
        "An inline pin that disagrees with the authenticated registry "
        "pin is rejected."
    )
    if proven_offline:
        print(
            "  PROVES (rational arithmetic, no solver, no NOUS install): the "
            "coverage Farkas certificate collapses the linear system to a "
            "numeric contradiction (policy-coverage gap refuted offline)."
        )
    else:
        print(
            "  PROVES: none carried in this VSA (no coverage Farkas leg)."
        )
    if cost_proven_offline:  # __s170_leg4_cost_scope_v1__
        print(
            "  PROVES-cost (rational arithmetic, no solver, no NOUS install): "
            "under the declared per-call token/tick estimates, no admissible "
            "execution exceeds the cost cap (cost-cap Farkas refutation). "
            "Runtime adherence to those estimates stays EVIDENCES via the "
            "signed trace."
        )
    else:
        print(
            "  PROVES-cost: none carried in this VSA (no cost-cap Farkas leg)."
        )
    if cost_proven_offline:
        print(
            "  OUT OF SCOPE: execution attestation; program re-derivation "
            "from source (the online path); real-world model faithfulness. "
            "The evidence layer is a monitor, not a guard."
        )
    else:
        print(
            "  OUT OF SCOPE: execution attestation; program re-derivation from "
            "source (the online path); the cost-cap SMT bound (EVIDENCES only -- "
            "no Farkas certificate is carried for it); real-world model "
            "faithfulness. The evidence layer is a monitor, not a guard."
        )
    _v3_not_claimed("runtime")
    return 0 if derived else 3


if __name__ == "__main__":
    sys.exit(_v3_run(main))
