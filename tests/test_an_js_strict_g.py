"""AN-GATE-1 D4, R4 (RULING 14:01Z on 10-30; R4_PREDICTIONS eaef233b).

The region raises one exception type (RULING 02:11Z, a): bytes that
are not UTF-8, and a UTF-8 byte order mark, are refused as
StrictJsonError with their label, not raised as UnicodeDecodeError or
json.JSONDecodeError. RFC 8259 8.1 and RFC 7493 2.1 make exchanged
JSON UTF-8; 8.1 lets a parser treat a BOM as an error. A signer can
sign such bytes, so the refusal is not by itself evidence of
tampering. Any other malformed JSON still raises json.JSONDecodeError.
Every key is made under tmp_path or in memory.

# __an_js_strict_g_tests_v1__
"""
from __future__ import annotations

import json
import shutil

import pytest

import test_an_js_strict as A
import test_an_js_strict_b as B
import test_an_js_strict_c as C
from test_an_js_strict_f import cont, env  # noqa: F401

ENCS = {"utf16": lambda b: b.decode("utf-8").encode("utf-16"),
        "bom": lambda b: b"\xef\xbb\xbf" + b}
EXPECT = {"utf16": "refused: not UTF-8", "bom": "refused: UTF-8 BOM"}
PHRASE = "not by itself evidence of tampering"


def _named_enc(text, label, enc):
    assert label in text, (A.RAN, label, enc, text)
    assert EXPECT[enc] in text, (A.RAN, label, enc, text)
    assert PHRASE in text, (A.RAN, label, enc, text)
    A.HITS.update(A.TAG.findall(text))


def _resigned(d, cp, enc):
    p = d / "000" / "receipt.jws"
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc["payload"] = B._b64url(ENCS[enc](B._unb64url(doc["payload"])))
    doc["signature"] = B._b64url(cp.sign(
        (doc["protected"] + "." + doc["payload"]).encode("ascii")))
    p.write_text(json.dumps(doc), encoding="utf-8")


# ------------------------------- the receipt signed by the counterparty


@pytest.mark.parametrize("enc", sorted(ENCS))
def test_g_continuity_cli_json(cont, tmp_path, enc):
    ledger, sub, cp = cont
    d = tmp_path / "ledger"
    shutil.copytree(ledger, d)
    _resigned(d, cp, enc)
    rc, so, se = C._cli(["continuity", "verify", "--ledger", d, "--json"]
                        + C._cont_args(sub))
    assert "Traceback" not in se, (A.RAN, enc, se[-600:])
    assert rc == 1, (A.RAN, enc, rc, so[-400:], se[-400:])
    lines = [ln for ln in so.splitlines() if ln.strip()]
    assert lines, (A.RAN, enc, "no stdout", se[-400:])
    doc = json.loads(lines[-1])
    assert doc.get("verdict") == "FAIL", (A.RAN, enc, doc)
    _named_enc(str(doc.get("error")), "receipt.jws payload", enc)


@pytest.mark.parametrize("enc", sorted(ENCS))
def test_g_continuity_text(cont, tmp_path, enc):
    import test_s178_checkpoint_leg as t
    ledger, sub, cp = cont
    d = tmp_path / "ledger"
    shutil.copytree(ledger, d)
    _resigned(d, cp, enc)
    vdir = tmp_path / "v"
    vdir.mkdir()
    rc, so, se = C._script(t._emit(vdir), [d] + C._cont_args(sub))
    assert "Traceback" not in se, (A.RAN, enc, se[-600:])
    assert rc == 1, (A.RAN, enc, rc, so[-400:], se[-400:])
    lines = [ln for ln in se.splitlines() if ln.strip()]
    _named_enc(lines[-1] if lines else "", "receipt.jws payload", enc)


# ------------------------------------------------------- the region


REGION = {
    "bom": (b"\xef\xbb\xbf{\"a\": 1}", "refused: UTF-8 BOM"),
    "utf16": ('{"a": 1}'.encode("utf-16"), "refused: not UTF-8"),
    "utf32": ('{"a": 1}'.encode("utf-32"), "refused: not UTF-8"),
    "surrogate": (b'{"a": "\xed\xa0\x80"}', "refused: not UTF-8"),
    "truncated": (b'{"a": ', None),
    "utf16le_no_bom": ('{"a": 1}'.encode("utf-16-le"), None),
}


@pytest.mark.parametrize("case", sorted(REGION))
def test_g_region_encoding(case):
    import conformance_verifier as cv
    raw, want = REGION[case]
    exc = None
    try:
        cv.loads(raw, "x.json")
    except Exception as e:  # noqa: BLE001
        exc = e
    assert exc is not None, (A.RAN, case, "accepted")
    if want is None:
        # any other malformed JSON keeps the json module's own error
        assert type(exc) is json.JSONDecodeError, (A.RAN, case, repr(exc))
        return
    assert type(exc) is cv.StrictJsonError, (A.RAN, case, repr(exc))
    msg = str(exc)
    assert msg.startswith("x.json " + want), (A.RAN, case, msg)
    assert PHRASE in msg, (A.RAN, case, msg)


# ---------------------------------------------------- the vendor body


USAGE = '{"usage": {"prompt_tokens": 3, "completion_tokens": 4}}'
VENDOR = {"body_bom": "﻿" + USAGE,
          "chunk_bom": ("data: ﻿" + USAGE + "\ndata: " + USAGE
                        + "\ndata: [DONE]\n")}


@pytest.mark.parametrize("case", sorted(VENDOR))
def test_g_vendor_bom(case):
    import attest_apr
    exc = None
    try:
        attest_apr._parse_vendor_usage(VENDOR[case])
    except Exception as e:  # noqa: BLE001
        exc = e
    assert exc is not None, (A.RAN, case, "accepted")
    assert getattr(exc, "an_js_refusal", False), (A.RAN, case, repr(exc))
    msg = str(exc)
    _named_enc(msg, "vendor_response_body", "bom")
    assert "two readings" not in msg, (A.RAN, case, msg)
