"""Standalone offline-verifier template for NOUS conformance certs.

# __phase2_stage5b_tpl_v1__
This module exports CONFORMANCE_VERIFY_OFFLINE_PY (a Python source
string) and emit_conformance_verifier (writes it to disk). The template
is v1/v2-aware: it reads cert.certificate_schema_version and selects the
six-obligation (v1) or seven-obligation (v2, with sequence_ok) check.

The anchored (Rekor v2) verifier is assembled by
offline_verifier_builder.build_conformance_verifier_v2 -- a separate path
with the same v1/v2 dispatch.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

CONFORMANCE_VERIFY_OFFLINE_PY: str = '#!/usr/bin/env python3\n"""Offline verification of a NOUS runtime conformance certificate.\n\nUsage: python3 -I verify_conformance_offline.py --expect-signer BASE64\n       [--expect-manifest-signer BASE64]\nExit:  0 = PASS, 1 = INTEGRITY, 2 = ENVIRONMENT, 3 = OUTSIDE (NT-GATE-1\n       D4). The last line on stdout names the class. No PASS without\n       --expect-signer, the certificate signer\'s key; the manifest\n       signer must be --expect-manifest-signer when given, else the\n       same key. OUTSIDE: authentic, the bound not held.\nRequires: cryptography library (no NOUS install needed).\n\nExpects in the same directory:\n  conformance.json   the signed certificate\n  trace.json         the signed execution trace it certifies\n  manifest.json      the signed static-proof manifest it binds to\n\nChecks (cryptography + stdlib only):\n  1. certificate Ed25519 signature over its canonical body bytes; the\n     signer key must equal --expect-signer (EVIDENCES signed by the\n     holder of that key; who holds it is out of band); then\n     manifest.json signed by --expect-manifest-signer (else the\n     same key) over its body without signature and\n     transparency_log\n  2. cert.trace_sha256 == sha256(trace canonical body)        cert<->trace bind\n  3. cert {source,smt_spec,pricing}_sha256 == manifest\'s      cert<->manifest bind\n  4. trace Ed25519 signature over its canonical body bytes\n  5. recorded obligation booleans consistent with conformant\n     (six for schema v1; seven for v2; eight for v4 with codegen_binding_ok)\n  6. when present, cert.codegen_sha256 equals those of trace and manifest\n     (offline sha-equality; program re-derivation is the online path)\n  7. when the certificate carries the spec canon (obligations_canon,\n     sha256 = the manifest\'s smt_spec_sha256): binding, surface,\n     assumption discharge and bound transfer recomputed from\n     trace.json, realized_total exactly; each must equal the\n     recorded value. authorization and sequence stay recorded.\n\nSCOPE: this checks, by Ed25519 signatures and sha256 equality, that the signed\nverdict verifies under the key the certificate carries and is BOUND to these\nexact artifacts. That key must equal the one the auditor\nsupplies with --expect-signer; who holds that key is established out of\nband. It\ndoes not re-derive the SMT bounds (that needs the NOUS toolchain; it is the\nonline `nous conformance verify` path).\n"""\nfrom __future__ import annotations\n\nimport base64\nimport hashlib\nimport json\nimport sys\nfrom pathlib import Path\n\nROOT = Path(__file__).parent\n\n_BOOLS_V1 = (\n    "binding_ok",\n    "surface_ok",\n    "assumption_discharge_ok",\n    "bound_transfer_ok",\n    "authorization_ok",\n    "trace_signature_ok",\n)\n\n_BOOLS_V2 = _BOOLS_V1 + ("sequence_ok",)\n\n_BOOLS_V4 = _BOOLS_V2 + ("codegen_binding_ok",)\n\n\ndef _bools_for(schema_version: int) -> tuple:\n    if schema_version >= 4:\n        return _BOOLS_V4\n    return _BOOLS_V2 if schema_version >= 2 else _BOOLS_V1\n\n\ndef _fail(msg: str) -> int:\n    print("FAIL: " + msg, file=sys.stderr)\n    return 1\n\n\n# __x_g2_expect_signer_v1__ the expected signer is an argument the auditor\n# supplies; it is never a constant in this script, which ships with the\n# evidence under review.\n_USAGE = "usage: python3 -I verify_conformance_offline.py --expect-signer BASE64 [--expect-manifest-signer BASE64]"\n_PIN_BADKEY = (\n    "ERROR: --expect-signer is not a base64 raw 32-byte Ed25519 public key"\n)\n_SIGNER_SCOPE = (\n    "SIGNER: pinned to the auditor-supplied --expect-signer key; who holds "\n    "that key is established out of band."\n)\n\n\ndef _parse_pin(argv):\n    if not argv:\n        return True, None\n    if len(argv) == 2 and argv[0] == "--expect-signer":\n        return True, argv[1]\n    return False, None\n\n\ndef _pin_raw(b64):\n    try:\n        raw = base64.b64decode(b64, validate=True)\n    except (ValueError, TypeError):\n        return None\n    return raw if len(raw) == 32 else None\n\n\ndef _canonical_body_bytes(doc: dict) -> bytes:\n    body = {k: v for k, v in doc.items() if k != "signature"}\n    return json.dumps(\n        body, sort_keys=True, separators=(",", ":")\n    ).encode("utf-8")\n\n\ndef _cert_canonical_body_bytes(doc: dict) -> bytes:\n    body = {\n        k: v for k, v in doc.items()\n        if k not in ("signature", "transparency_log")\n    }\n    if int(body.get("certificate_schema_version", 1)) < 2:\n        body.pop("sequence_ok", None)\n    return json.dumps(\n        body, sort_keys=True, separators=(",", ":")\n    ).encode("utf-8")\n\n\ndef _verify_ed25519(pub_b64: str, sig_b64: str, body: bytes) -> bool:\n    from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n        Ed25519PublicKey,\n    )\n    from cryptography.exceptions import InvalidSignature\n    try:\n        pub = Ed25519PublicKey.from_public_bytes(\n            base64.b64decode(pub_b64, validate=True)\n        )\n        pub.verify(base64.b64decode(sig_b64, validate=True), body)\n        return True\n    except (InvalidSignature, ValueError):\n        return False\n\n\n# --- conformance recompute embed (shared text; canonical copy: conformance.py) ---\n# Every offline conformance verifier carries this region byte-for-byte;\n# tests/test_nt_v2_recompute.py names any copy that drifts. Standard\n# library only. It recomputes the cost obligations (NT-GATE-1 D6 (i))\n# from trace.json and the spec canon the certificate carries, bound by\n# sha256 to the manifest\'s smt_spec_sha256. __nt_v2_recompute_v1__\n_CONF_RC_MAX_BYTES = 16 * 1024 * 1024\n_CONF_RC_MAX_DEPTH = 32\n_CONF_RC_MAX_DIGITS = 64\n_CONF_RC_KINDS = ("llm_call", "tool_call", "message", "gated_action")\n_CONF_RC_SCOPE = (\n    "binding_ok", "surface_ok", "assumption_discharge_ok",\n    "bound_transfer_ok",\n)\n\n\ndef _conf_rc_load(raw):\n    # Strict JSON: UTF-8, non-ASCII only inside strings, bounded size\n    # and nesting, no duplicate key, no NaN or Infinity, no float.\n    # Returns (doc, "") or (None, why).\n    import json\n    if not isinstance(raw, (bytes, bytearray)):\n        return None, "input is not bytes"\n    if len(raw) > _CONF_RC_MAX_BYTES:\n        return None, "larger than %d bytes" % _CONF_RC_MAX_BYTES\n    try:\n        text = bytes(raw).decode("utf-8")\n    except UnicodeDecodeError:\n        return None, "not UTF-8"\n    depth = 0\n    in_str = False\n    esc = False\n    for ch in text:\n        if in_str:\n            if esc:\n                esc = False\n            elif ch == "\\\\":\n                esc = True\n            elif ch == \'"\':\n                in_str = False\n        elif ch == \'"\':\n            in_str = True\n        elif ord(ch) > 127:\n            return None, "non-ASCII outside a string"\n        elif ch in "[{":\n            depth += 1\n            if depth > _CONF_RC_MAX_DEPTH:\n                return None, "nested deeper than %d" % _CONF_RC_MAX_DEPTH\n        elif ch in "]}":\n            depth -= 1\n\n    def pairs(items):\n        out = {}\n        for k, v in items:\n            if k in out:\n                raise ValueError("duplicate key " + repr(k))\n            out[k] = v\n        return out\n\n    def no_constant(name):\n        raise ValueError("non-finite number " + name)\n\n    def no_float(s):\n        raise ValueError("non-integer number " + s)\n\n    try:\n        doc = json.loads(text, object_pairs_hook=pairs,\n                         parse_constant=no_constant, parse_float=no_float)\n    except (ValueError, RecursionError) as exc:\n        return None, str(exc)\n    return doc, ""\n\n\ndef _conf_rc_rational(s):\n    # "123" or "(/ 1 2)" -> Fraction; None outside the closed shape.\n    import re\n    from fractions import Fraction\n    m = re.fullmatch(r"([0-9]+)|\\(/ ([0-9]+) ([0-9]+)\\)", s)\n    if m is None:\n        return None\n    parts = [g for g in m.groups() if g is not None]\n    if any(len(p) > _CONF_RC_MAX_DIGITS for p in parts):\n        return None\n    if m.group(1) is not None:\n        return Fraction(int(m.group(1)))\n    if int(m.group(3)) == 0:\n        return None\n    return Fraction(int(m.group(2)), int(m.group(3)))\n\n\ndef _conf_rc_decimal(s):\n    # A decimal string, as Decimal prints one ("0.00105", "1E-7") ->\n    # Fraction; None otherwise.\n    import re\n    from fractions import Fraction\n    if not isinstance(s, str):\n        return None\n    m = re.fullmatch(r"(-?)([0-9]+)(?:\\.([0-9]+))?(?:E([-+]?[0-9]{1,3}))?", s)\n    if m is None or len(m.group(2)) + len(m.group(3) or "") > \\\n            _CONF_RC_MAX_DIGITS:\n        return None\n    frac = m.group(3) or ""\n    v = Fraction(int(m.group(2) + frac), 10 ** len(frac))\n    if m.group(4) is not None:\n        v *= Fraction(10) ** int(m.group(4))\n    return -v if m.group(1) else v\n\n\ndef _conf_rc_text(fr):\n    # Exact decimal text of a Fraction whose denominator is 2^a 5^b.\n    sign = "-" if fr < 0 else ""\n    x = abs(fr)\n    k = 0\n    while x.denominator != 1 and k < 4 * _CONF_RC_MAX_DIGITS:\n        x *= 10\n        k += 1\n    if x.denominator != 1:\n        return sign + str(abs(fr))\n    digits = str(x.numerator).rjust(k + 1, "0")\n    if k == 0:\n        return sign + digits\n    head, tail = digits[:-k], digits[-k:].rstrip("0")\n    return sign + head + ("." + tail if tail else "")\n\n\ndef _conf_rc_parse_canon(canon_text):\n    # Closed shapes of smt_emit.canonical_str. Returns a dict, or a str\n    # naming the first line outside the shapes.\n    import re\n    from fractions import Fraction\n    if not isinstance(canon_text, str):\n        return "spec canon is not text"\n    # The grammar\'s NAME class (nous.lark): Latin and U+0370..U+03FF.\n    gr = r"\\u0370-\\u03FF"\n    nb = r"[A-Za-z_" + gr + r"][A-Za-z0-9_" + gr + r"]*"\n    nm = "(" + nb + ")"\n    rt = r"([0-9]+|\\(/ [0-9]+ [0-9]+\\))"\n    re_pc = re.compile(\n        r"A:\\(assert \\(= cost_" + nm + r"_per_call \\(/ \\(\\+ \\(\\* " + rt\n        + r" ([0-9]+)\\) \\(\\* " + rt + r" ([0-9]+)(?: " + rt\n        + r")?\\)\\) 1000000\\)\\)\\)")\n    re_tt = re.compile(\n        r"A:\\(assert \\(= cost_" + nm + r"_total \\(\\* cost_" + nm\n        + r"_per_call ([0-9]+)\\)\\)\\)")\n    re_t1 = re.compile(r"A:\\(assert \\(= total_cost cost_" + nm\n                       + r"_total\\)\\)")\n    re_tn = re.compile(r"A:\\(assert \\(= total_cost \\(\\+ ((?:cost_"\n                       + nb + r"_total ?)+)\\)\\)\\)")\n    out = {"souls": {}, "ga": set(), "de": set()}\n    seen = set()\n    totals = {}\n    sum_line = None\n    for line in canon_text.split("\\n"):\n        tag, sep, rest = line.partition(":")\n        if not sep:\n            return "a line without a tag"\n        if tag in ("CC", "MT", "MARGIN", "SS", "PS"):\n            if tag in seen:\n                return "duplicate " + tag + " line"\n            seen.add(tag)\n        if tag == "CC":\n            m = re.fullmatch(r"([0-9]+)(?:\\.([0-9]+))?\\|([A-Z]{3})", rest)\n            if m is None or len(m.group(1) + (m.group(2) or "")) > \\\n                    _CONF_RC_MAX_DIGITS:\n                return "CC line outside the closed shape"\n            out["cap"] = _conf_rc_decimal(\n                m.group(1) + ("." + m.group(2) if m.group(2) else ""))\n            out["currency"] = m.group(3)\n        elif tag == "MT":\n            if not re.fullmatch(r"[0-9]{1,9}", rest):\n                return "MT line outside the closed shape"\n            out["mt"] = int(rest)\n        elif tag == "MARGIN":\n            if not re.fullmatch(r"[0-9]{1,2}", rest):\n                return "MARGIN line outside the closed shape"\n        elif tag in ("SS", "PS"):\n            if not re.fullmatch(r"[0-9a-f]{64}", rest):\n                return tag + " line outside the closed shape"\n            out[tag.lower()] = rest\n        elif tag == "GA":\n            out["ga"].add(rest)\n        elif tag == "DE":\n            out["de"].add(rest)\n        elif tag == "A":\n            m = re_pc.fullmatch(line)\n            if m is not None:\n                soul = m.group(1)\n                if soul in out["souls"]:\n                    return "duplicate per-call line for " + soul\n                rin, rout = _conf_rc_rational(m.group(2)), \\\n                    _conf_rc_rational(m.group(4))\n                mult = Fraction(1) if m.group(6) is None else \\\n                    _conf_rc_rational(m.group(6))\n                if rin is None or rout is None or mult is None or \\\n                        len(m.group(3)) > 18 or len(m.group(5)) > 18:\n                    return "per-call line outside the closed shape"\n                out["souls"][soul] = (rin, int(m.group(3)), rout,\n                                      int(m.group(5)), mult)\n                continue\n            m = re_tt.fullmatch(line)\n            if m is not None:\n                if m.group(1) != m.group(2) or m.group(1) in totals:\n                    return "total line outside the closed shape"\n                totals[m.group(1)] = int(m.group(3))\n                continue\n            m = re_t1.fullmatch(line) or re_tn.fullmatch(line)\n            if m is not None:\n                if sum_line is not None:\n                    return "duplicate total_cost line"\n                sum_line = sorted(re.findall(\n                    r"cost_(" + nb + r")_total", m.group(1)\n                    if m.re is re_tn else "cost_" + m.group(1) + "_total"))\n                continue\n            return "A: line outside the closed shapes"\n        elif tag not in ("NV", "EV", "W", "D", "R", "O", "SD", "SA", "GQ"):\n            return "unknown tag " + tag\n    for need in ("cap", "mt", "ss", "ps"):\n        if need not in out:\n            return "spec canon lacks " + need.upper()\n    if sorted(totals) != sorted(out["souls"]) or (\n            out["souls"] and sum_line != sorted(out["souls"])):\n        return "per-call, total and total_cost lines do not match"\n    if any(t != out["mt"] for t in totals.values()):\n        return "a total line multiplies by other than MT"\n    return out\n\n\ndef _conf_rc_obligations(manifest, trace, canon_text):\n    # The four obligations in scope, recomputed. ("refused", why) where\n    # the online path raises a precondition, else\n    # ("ok", {name: bool}, realized_total Fraction, [errors]).\n    import hashlib\n    from fractions import Fraction\n    c = _conf_rc_parse_canon(canon_text)\n    if isinstance(c, str):\n        return ("refused", "spec canon refused: " + c)\n    if not c["souls"]:\n        return ("refused", "spec canon declares no costed soul")\n    if not isinstance(manifest, dict) or not isinstance(trace, dict):\n        return ("refused", "manifest or trace is not a JSON object")\n    events = trace.get("events")\n    if not isinstance(events, list):\n        return ("refused", "trace has no event list")\n    norm = []\n    for i, ev in enumerate(events):\n        if not isinstance(ev, dict):\n            return ("refused", "event %d is not an object" % i)\n        e = {}\n        for key, dflt in (("seq", None), ("tick", None),\n                          ("input_tokens", 0), ("output_tokens", 0)):\n            v = ev.get(key, dflt)\n            if type(v) is not int or v < 0:\n                return ("refused", "event %d %s is not a non-negative "\n                        "integer" % (i, key))\n            e[key] = v\n        for key in ("soul", "kind"):\n            v = ev.get(key)\n            if not isinstance(v, str) or not v:\n                return ("refused", "event %d %s is not text" % (i, key))\n            e[key] = v\n        tc = _conf_rc_decimal(ev.get("tool_cost", "0"))\n        if tc is None:\n            return ("refused", "event %d tool_cost is not a decimal" % i)\n        e["tool_cost"] = tc\n        a = ev.get("action")\n        if a is not None and not isinstance(a, str):\n            return ("refused", "event %d action is not text" % i)\n        e["action"] = a\n        norm.append(e)\n    souls, ga, de = c["souls"], c["ga"], c["de"]\n    for e in norm:\n        s = "event seq=%d " % e["seq"]\n        if e["kind"] not in _CONF_RC_KINDS:\n            return ("refused", s + "has an unknown kind")\n        if e["soul"] not in souls:\n            return ("refused", s + "names a soul the spec never declared")\n        if e["kind"] == "tool_call" and e["tool_cost"] != 0:\n            return ("refused", s + "is a priced tool_call")\n        if e["kind"] == "gated_action" and e["action"] is not None and \\\n                e["action"] not in ga:\n            return ("refused", s + "gated action is not declared")\n        if e["action"] is not None and e["action"] in ga and \\\n                e["kind"] != "gated_action":\n            return ("refused", s + "is a declared gated action recorded "\n                    "under another kind")\n        if e["kind"] == "tool_call" and de:\n            if e["action"] is None or e["action"] not in de:\n                return ("refused", s + "tool_call is outside the "\n                        "declared events")\n    ek = trace.get("evidence_kind")\n    cb = trace.get("cost_binding")\n    pti = trace.get("provider_token_integrity")\n    if ek not in (None, "envelope", "witnessed_run") or cb not in (\n            None, "envelope", "realized") or pti not in (\n            None, "unattested", "tee_attested", "unverifiable"):\n        return ("refused", "trust field outside its vocabulary")\n    if sum(1 for v in (ek, cb, pti) if v is not None) not in (0, 3):\n        return ("refused", "trust triple is partial (all three or none)")\n    if (cb == "realized") != (ek == "witnessed_run"):\n        return ("refused", "cost_binding and evidence_kind disagree")\n    errors = []\n    sha = hashlib.sha256(canon_text.encode("utf-8")).hexdigest()\n    binding = (\n        sha == manifest.get("smt_spec_sha256")\n        and c["ss"] == manifest.get("source_sha256")\n        and c["ps"] == manifest.get("pricing_sha256")\n        and trace.get("source_sha256") == manifest.get("source_sha256")\n        and trace.get("smt_spec_sha256") == manifest.get("smt_spec_sha256")\n        and trace.get("pricing_sha256") == manifest.get("pricing_sha256")\n    )\n    if not binding:\n        errors.append("binding: canon, manifest and trace shas disagree")\n    discharge = True\n    calls = {name: 0 for name in souls}\n    max_tick = -1\n    realized = Fraction(0)\n    for e in norm:\n        rin, max_in, rout, max_out, mult = souls[e["soul"]]\n        max_tick = max(max_tick, e["tick"])\n        if e["input_tokens"] > max_in or e["output_tokens"] > max_out:\n            discharge = False\n            errors.append("discharge: seq=%d tokens over the declared "\n                          "bound" % e["seq"])\n        if e["kind"] == "llm_call":\n            calls[e["soul"]] += 1\n            realized += (rin * e["input_tokens"]\n                         + rout * e["output_tokens"] * mult) / 1000000\n    for name, n in sorted(calls.items()):\n        if n > c["mt"]:\n            discharge = False\n            errors.append("discharge: soul %s made %d llm_calls > %d"\n                          % (name, n, c["mt"]))\n    if max_tick >= c["mt"]:\n        discharge = False\n        errors.append("discharge: max tick %d >= %d" % (max_tick, c["mt"]))\n    bound = realized <= c["cap"]\n    if not bound:\n        errors.append("bound_transfer: realized_total %s > cost_cap %s"\n                      % (_conf_rc_text(realized), _conf_rc_text(c["cap"])))\n    return ("ok", {"binding_ok": binding, "surface_ok": True,\n                   "assumption_discharge_ok": discharge,\n                   "bound_transfer_ok": bound}, realized, errors)\n\n\ndef _conf_recompute(manifest, cert, trace, canon_text):\n    # ("absent", {}) without a canon; ("refused", {"reason"}); or\n    # ("recomputed", {"line", "disagree", ...}). Reads no recorded\n    # boolean to decide an obligation; compares them after.\n    if canon_text is None:\n        return ("absent", {})\n    if not isinstance(cert, dict):\n        return ("refused", {"reason": "certificate is not a JSON object"})\n    r = _conf_rc_obligations(manifest, trace, canon_text)\n    if r[0] == "refused":\n        return ("refused", {"reason": r[1]})\n    _ok, ob, realized, errors = r\n    cap = _conf_rc_parse_canon(canon_text)["cap"]\n    disagree = []\n    for name in _CONF_RC_SCOPE:\n        if name in cert and bool(cert[name]) != ob[name]:\n            disagree.append(\n                "certificate records %s=%s but recomputed from trace.json "\n                "and the spec canon it is %s (recorded verdict disagrees "\n                "with recomputation)" % (name, bool(cert[name]), ob[name]))\n    rec = _conf_rc_decimal(cert.get("realized_total"))\n    if rec != realized:\n        disagree.append(\n            "certificate records realized_total=%s but recomputed from "\n            "trace.json and the spec canon it is %s (recorded verdict "\n            "disagrees with recomputation)"\n            % (cert.get("realized_total"), _conf_rc_text(realized)))\n    line = (\n        "RECOMPUTED (cost obligations, D6 (i)) from trace.json and the "\n        "certificate\'s spec canon, equal to the recorded booleans: "\n        + ", ".join("%s=%s" % (n, ob[n]) for n in _CONF_RC_SCOPE)\n        + "; realized_total %s, cost_cap %s"\n        % (_conf_rc_text(realized), _conf_rc_text(cap)))\n    return ("recomputed", {"line": line, "disagree": disagree,\n                           "obligations": ob, "realized_total": realized,\n                           "errors": errors})\n# --- end conformance recompute embed ---\n\n\n# --- v3 verdict classes embed (shared text; canonical copy: conformance_verifier.py) ---\n# Every offline verifier in NT-GATE-1 V3\'s scope carries this region\n# byte-for-byte; tests/test_nt_v3_classes.py names any copy that drifts.\n# Exit classes (D4 as amended): 0 PASS, 1 INTEGRITY, 2 ENVIRONMENT,\n# 3 OUTSIDE; the last line on stdout names the class. No PASS without\n# a public key the auditor supplies (--expect-signer). Standard\n# library only. __nt_v3_classes_v1__\n_V3_CLASSES = {0: "PASS", 1: "INTEGRITY", 2: "ENVIRONMENT", 3: "OUTSIDE"}\n_V3_STATE = {"pin": None, "flags": frozenset(), "keys": {},\n             "outside": False}\n_V3_NO_PIN = (\n    "no --expect-signer: this verifier gives no PASS without a public "\n    "key the auditor supplies from outside the evidence"\n)\n_V3_NOT_CLAIMED = {\n    "runtime": (\n        "completeness: that the recorded events are all the events; the "\n        "recorder runs in the operator\'s process",\n        "token counts: provider-reported; unattested unless "\n        "provider_token_integrity is tee_attested, and no receipt is "\n        "verified here",\n        "the served model: the recorder records the requested model",\n        "tool labels in a world that declares no events: unchecked",\n        "obligations outside the recomputed scope: reported as not "\n        "recomputed, never folded into PASS",\n        "prices outside the table\'s rate model: cache writes, batch "\n        "tiers, failed attempts",\n        "time: that the declared program existed before the run",\n        "identity: the key names a party only through the auditor\'s pin",\n        "the operator\'s honesty: the operator holds the key, runs the "\n        "recorder and writes the numbers",\n        "control: none. A monitor.",\n        "regulatory status: none",\n    ),\n    "dossier": (\n        "declared estimates: the cost bound is over the declared token "\n        "estimates and prices; a dossier observes no run",\n        "identity: the key names a party only through the auditor\'s pin",\n        "the operator\'s honesty: the operator writes the source and holds "\n        "the key",\n        "control: none. A monitor.",\n        "regulatory status: none",\n    ),\n}\n\n\ndef _v3_pin_raw(b64):\n    import base64\n    if not isinstance(b64, str):\n        return None\n    try:\n        raw = base64.b64decode(b64, validate=True)\n    except (ValueError, TypeError):\n        return None\n    return raw if len(raw) == 32 else None\n\n\ndef _v3_args(argv, flags=(), keyed=()):\n    # Exactly one --expect-signer, each option of keyed at most once,\n    # each with a base64 raw 32-byte key; each of flags at most once;\n    # nothing else. Returns (pin, flags_seen, keys, "") or\n    # (None, None, None, why).\n    keys = {}\n    seen = set()\n    i = 0\n    while i < len(argv):\n        a = argv[i]\n        if a == "--expect-signer" or a in keyed:\n            if a in keys or i + 1 >= len(argv):\n                return None, None, None, (\n                    a + " must be given once, with a key")\n            raw = _v3_pin_raw(argv[i + 1])\n            if raw is None:\n                return None, None, None, (\n                    a + " is not a base64 raw 32-byte Ed25519 public key")\n            keys[a] = raw\n            i += 2\n            continue\n        if a in flags and a not in seen:\n            seen.add(a)\n            i += 1\n            continue\n        return None, None, None, "unexpected argument " + repr(a)\n    pin = keys.pop("--expect-signer", None)\n    if pin is None:\n        return None, None, None, _V3_NO_PIN\n    return pin, frozenset(seen), keys, ""\n\n\ndef _v3_key(opt):\n    # The auditor\'s key for opt, else the --expect-signer key.\n    return _V3_STATE["keys"].get(opt) or _V3_STATE["pin"]\n\n\ndef _v3_is_pinned(pub_b64, opt="--expect-signer"):\n    import base64\n    pin = _v3_key(opt)\n    if pin is None or not isinstance(pub_b64, str):\n        return False\n    try:\n        return base64.b64decode(pub_b64, validate=True) == pin\n    except (ValueError, TypeError):\n        return False\n\n\ndef _v3_pin_b64(opt="--expect-signer"):\n    import base64\n    return base64.b64encode(_v3_key(opt)).decode("ascii")\n\n\ndef _v3_manifest_body(doc):\n    import json\n    body = {\n        k: v for k, v in doc.items()\n        if k not in ("signature", "transparency_log")\n    }\n    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode(\n        "utf-8")\n\n\ndef _v3_not_claimed(kind):\n    print()\n    print("NOT CLAIMED (NT-GATE-1 5.5):")\n    for line in _V3_NOT_CLAIMED[kind]:\n        print("  - " + line)\n\n\ndef _v3_outside_manifest(manifest):\n    # Marks the run OUTSIDE; main still returns 0 after every remaining\n    # check, and _v3_run turns that 0 into 3. A later failing check\n    # still returns 1 (INTEGRITY first).\n    _V3_STATE["outside"] = True\n    v = manifest.get("verdict")\n    print()\n    print("VERDICT: OUTSIDE (authentic manifest under the expected key; "\n          "the solver verdict is " + repr(v) + ", not \'proven\', so the "\n          "declared bound is not established)")\n    print("  world:      " + str(manifest.get("world_name", "?")))\n    print("  verdict:    " + str(v))\n\n\ndef _v3_run(main_fn, flags=(), pass_argv=False, usage="", keyed=()):\n    import sys\n    pin, seen, keys, why = _v3_args(sys.argv[1:], flags, keyed)\n    if why:\n        if usage:\n            print(usage, file=sys.stderr)\n        print("ERROR: " + why, file=sys.stderr)\n        print("CLASS: ENVIRONMENT")\n        return 2\n    _V3_STATE["pin"] = pin\n    _V3_STATE["flags"] = seen\n    _V3_STATE["keys"] = keys\n    try:\n        rc = main_fn(sys.argv[1:]) if pass_argv else main_fn()\n    except SystemExit as exc:\n        rc = exc.code if isinstance(exc.code, int) else 1\n    except ImportError as exc:\n        print("ERROR: a module this verifier needs is missing (" + str(exc)\n              + "); install: pip install \'cryptography>=42\'",\n              file=sys.stderr)\n        rc = 2\n    except Exception as exc:\n        print("FAIL: unhandled " + type(exc).__name__ + ": " + str(exc),\n              file=sys.stderr)\n        rc = 1\n    if isinstance(rc, bool) or rc not in _V3_CLASSES:\n        rc = 1\n    if rc == 0 and _V3_STATE["outside"]:\n        rc = 3\n    print("CLASS: " + _V3_CLASSES[rc])\n    return rc\n# --- end v3 verdict classes embed ---\n\n\ndef main() -> int:\n    pin = _V3_STATE["pin"]  # __nt_v3_classes_wire_v1__\n    try:\n        import cryptography  # noqa: F401\n    except ImportError:\n        print(\n            "ERROR: cryptography library required.\\n"\n            "Install: pip install \\\'cryptography>=42\\\'",\n            file=sys.stderr,\n        )\n        return 2\n\n    cert_path = ROOT / "conformance.json"\n    trace_path = ROOT / "trace.json"\n    manifest_path = ROOT / "manifest.json"\n    for label, pth in (\n        ("conformance.json", cert_path),\n        ("trace.json", trace_path),\n        ("manifest.json", manifest_path),\n    ):\n        if not pth.is_file():\n            return _fail(label + " not found in " + str(ROOT))\n\n    try:\n        cert = json.loads(cert_path.read_text(encoding="utf-8"))\n        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))\n    except json.JSONDecodeError as e:\n        return _fail("JSON parse error: " + str(e))\n    # __nt_v2_recompute_wire_v1__ the trace that feeds the recomputation is\n    # read by the strict loader whenever the certificate carries a\n    # spec canon.\n    if isinstance(cert, dict) and cert.get("obligations_canon") is not None:\n        trace, _why = _conf_rc_load(trace_path.read_bytes())\n        if trace is None:\n            return _fail("trace.json refused: " + _why)\n    else:\n        try:\n            trace = json.loads(trace_path.read_text(encoding="utf-8"))\n        except json.JSONDecodeError as e:\n            return _fail("JSON parse error: " + str(e))\n\n    schema_v = int(cert.get("certificate_schema_version", 1))\n    bools = _bools_for(schema_v)\n\n    csig = cert.get("signature")\n    if not isinstance(csig, dict):\n        return _fail("certificate has no signature block")\n    if csig.get("algorithm") != "ed25519":\n        return _fail("certificate signature algorithm is not ed25519")\n    cpub = csig.get("public_key_b64", "")\n    csigb = csig.get("signature_b64", "")\n    if not cpub or not csigb:\n        return _fail("certificate signature block incomplete")\n    if pin is not None:\n        try:\n            if base64.b64decode(cpub, validate=True) != pin:\n                return _fail("certificate signer is not the expected key")\n        except (ValueError, TypeError):\n            return _fail("certificate signer is not the expected key")\n        cpub = base64.b64encode(pin).decode("ascii")\n    if not _verify_ed25519(cpub, csigb, _cert_canonical_body_bytes(cert)):\n        return _fail("certificate Ed25519 signature does NOT verify")\n    print("OK   certificate Ed25519 signature verified")\n    if pin is not None:\n        print("OK   certificate signer is the expected key (--expect-signer)")\n    msig = manifest.get("signature")  # __nt_v3_classes_wire_v1__\n    if not isinstance(msig, dict) or not _v3_is_pinned(\n        msig.get("public_key_b64", ""), "--expect-manifest-signer"\n    ):\n        return _fail(\n            "manifest signer is not the expected key "\n            "(--expect-manifest-signer, else --expect-signer)"\n        )\n    if not _verify_ed25519(\n        _v3_pin_b64("--expect-manifest-signer"),\n        msig.get("signature_b64", ""),\n        _v3_manifest_body(manifest),\n    ):\n        return _fail(\n            "manifest Ed25519 signature does NOT verify under the "\n            "expected key"\n        )\n    print("OK   manifest signed by the expected key")\n\n    trace_sha = hashlib.sha256(_canonical_body_bytes(trace)).hexdigest()\n    if cert.get("trace_sha256") != trace_sha:\n        return _fail(\n            "cert.trace_sha256 != sha256(trace canonical body): "\n            "cert=" + str(cert.get("trace_sha256"))[:16] + "... "\n            "trace=" + trace_sha[:16] + "..."\n        )\n    print("OK   certificate is bound to this trace (sha256 match)")\n\n    for fld in ("source_sha256", "smt_spec_sha256", "pricing_sha256"):\n        if cert.get(fld) != manifest.get(fld):\n            return _fail(\n                "cert." + fld + " != manifest." + fld + " "\n                "(certificate is not bound to this manifest)"\n            )\n    print("OK   certificate is bound to this manifest (3 shas match)")\n\n    cert_cg = cert.get("codegen_sha256")\n    if cert_cg is not None:\n        man_cg = manifest.get("codegen_sha256")\n        if man_cg is not None and man_cg != cert_cg:\n            return _fail(\n                "cert.codegen_sha256 != manifest.codegen_sha256 "\n                "(certificate names a different compiled program)"\n            )\n        tr_cg = trace.get("codegen_sha256")\n        if tr_cg is not None and tr_cg != cert_cg:\n            return _fail(\n                "cert.codegen_sha256 != trace.codegen_sha256 "\n                "(trace names a different compiled program)"\n            )\n        print(\n            "OK   codegen leg: cert/trace/manifest name one compiled "\n            "program (offline sha-equality)"\n        )\n\n    tsig = trace.get("signature")\n    if not isinstance(tsig, dict):\n        return _fail("trace has no signature block")\n    if tsig.get("algorithm") != "ed25519":\n        return _fail("trace signature algorithm is not ed25519")\n    if not _verify_ed25519(\n        tsig.get("public_key_b64", ""),\n        tsig.get("signature_b64", ""),\n        _canonical_body_bytes(trace),\n    ):\n        return _fail("trace Ed25519 signature does NOT verify")\n    print("OK   trace Ed25519 signature verified")\n\n    missing = [b for b in bools if b not in cert]\n    if missing:\n        return _fail("certificate missing obligation fields: " + str(missing))\n    derived = all(bool(cert[b]) for b in bools)\n    recorded = bool(cert.get("conformant"))\n    if derived != recorded:\n        return _fail(\n            "certificate conformant=" + str(recorded) + " but the "\n            + str(len(bools)) + " obligations imply " + str(derived)\n            + " (inconsistent record)"\n        )\n    print(\n        "OK   recorded verdict consistent with " + str(len(bools))\n        + " obligations (schema v" + str(schema_v) + ")"\n    )\n    _rc_status, _rc = _conf_recompute(  # __nt_v2_recompute_wire_v1__\n        manifest, cert, trace, cert.get("obligations_canon")\n    )\n    if _rc_status == "refused":\n        return _fail("recomputation refused: " + _rc["reason"])\n    if _rc_status == "recomputed":\n        if _rc["disagree"]:\n            return _fail(_rc["disagree"][0])\n        print("OK   " + _rc["line"])\n        print("NOT RECOMPUTED: authorization_ok, sequence_ok (the "\n              "certificate\'s recorded booleans)")\n    else:\n        print("NOT RECOMPUTED: no spec canon in the certificate; the "\n              "obligations are the certificate\'s recorded booleans")\n\n    print()\n    verdict = "PASS" if recorded else "OUTSIDE"\n    print("VERDICT: " + verdict + " (signed conformance certificate"\n          + ("" if recorded else "; authentic under the expected key, "\n             "the bound was not held") + ")")\n    print("  world:          " + str(cert.get("world_name", "?")))\n    print("  realized_total: " + str(cert.get("realized_total", "?"))\n          + " " + str(cert.get("cost_currency", "")))\n    print("  cost_cap:       " + str(cert.get("cost_cap", "?"))\n          + " " + str(cert.get("cost_currency", "")))\n    print("  conformant:     " + str(recorded))\n    print("  schema_version: " + str(schema_v))\n    print("  issued_utc:     " + str(cert.get("issued_utc", "?")))\n    print("  trace_sha256:   " + str(cert.get("trace_sha256", "?"))[:16]\n          + "...")\n    errs = cert.get("errors") or []\n    if errs:\n        print("  obligation failures:")\n        for e in errs:\n            print("    - " + str(e))\n    print()\n    # __x_g4_wording_v1__\n    print(\n        "SCOPE: signatures and binding verified offline, including the "\n        "codegen leg by sha-equality. The certificate is signed by the "\n        "--expect-signer key, the manifest by --expect-manifest-signer "\n        "or else the same key. SMT "\n        "bound re-derivation and program re-derivation remain the online "\n        "`nous conformance verify` path. With a spec canon in the "\n        "certificate, the cost obligations are recomputed from "\n        "trace.json; authorization and sequence are not."\n    )\n    print(_SIGNER_SCOPE)\n    _v3_not_claimed("runtime")\n    return 0 if recorded else 3\n\n\nif __name__ == "__main__":\n    sys.exit(_v3_run(main, usage=_USAGE,\n                     keyed=("--expect-manifest-signer",)))\n'


def emit_conformance_verifier(
    output_dir: str, anchored: bool = False,  # __nous_conformance_anchored_verifier_v1__
) -> Path:
    """Write verify_conformance_offline.py (0644) into output_dir; return path.

    anchored=False: standalone Ed25519 + binding verifier (this module's
    string template; no Rekor dependency).
    anchored=True: assembled Rekor v2 conformance verifier with the pinned
    production KNOWN_REKOR_V2_LOG_KEYS allowlist.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / "verify_conformance_offline.py"
    if anchored:
        from offline_verifier_builder import build_conformance_verifier_v2
        from rekor_verify_v2 import KNOWN_REKOR_V2_LOG_KEYS
        payload = build_conformance_verifier_v2(
            repr(KNOWN_REKOR_V2_LOG_KEYS)
        )
    else:
        payload = CONFORMANCE_VERIFY_OFFLINE_PY
    fd, tmp = tempfile.mkstemp(dir=str(out), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.chmod(tmp, 0o644)
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return target


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
