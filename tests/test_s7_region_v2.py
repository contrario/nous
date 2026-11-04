"""S7, region v2 (seat S440, Gate NOUS_S440_GATE_SPLIT r3, section 14;
RULING 11-03 13:42Z): the strict JSON region also refuses a number
whose value is not finite in a double, an unpaired surrogate or a
noncharacter in a string or a member name (RFC 7493 2.1, 2.2) and
nesting deeper than 128, each by label. D4's refusals and messages
stay. An integer past 2**53 - 1 and an underflow are not refused.

K-JS.2 (tests/test_an_js_strict.py) holds every carrier to the
canonical copy byte for byte; this file tests the canonical copy, two
carriers end to end, and the census of the tracked JSON files (Gate
14.8, KS1). Bundles by test_xd5_outside_conformance._bundle, keys
inside tmp_path. No network.

# __an_js_s7_test_v1__
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import conformance_verifier as CV
import test_xd5_outside_conformance as X5

REPO = Path(__file__).resolve().parent.parent
PERM = {"require_anchor": False, "require_pubkey_in_allowlist": False}
TAIL = ("(a signer can sign these bytes, so this refusal is not by "
        "itself evidence of tampering)")

REFUSED = {
    "overflow": (b'{"a":1e400}', "number out of range 1e400"),
    "overflow_neg": (b'{"a":[-1e400]}', "number out of range -1e400"),
    "surrogate_high": (b'{"a":"\\ud800"}', "unpaired surrogate U+D800"),
    "surrogate_low": (b'["x\\udc00"]', "unpaired surrogate U+DC00"),
    "nonchar_name": (b'{"\\ufdd0":1}', "noncharacter U+FDD0"),
    "nonchar_raw": (b'{"a":"\xef\xbf\xbe"}', "noncharacter U+FFFE"),
    "nonchar_astral": (b'{"a":"\\ud83f\\udffe"}', "noncharacter U+1FFFE"),
    "deep_129_arrays": (b"[" * 129 + b"]" * 129, "nesting deeper than 128"),
    "deep_129_objects": (b'{"a":' * 129 + b"0" + b"}" * 129,
                         "nesting deeper than 128"),
    "deep_60000": (b"[" * 60000 + b"]" * 60000, "nesting deeper than 128"),
}

ACCEPTED = {
    "underflow": (b'{"a":1e-400}', {"a": 0.0}),
    "big_integer": (b'{"a":1152921504606846976}',
                    {"a": 1152921504606846976}),
    "valid_pair": (b'{"a":"\\ud83d\\ude00"}', {"a": "\U0001F600"}),
    "deep_128": (b"[" * 128 + b"]" * 128, None),
    "brackets_in_string": (b'{"a":"' + b"[" * 200 + b'"}',
                           {"a": "[" * 200}),
    "escaped_quote_then_brackets": (
        b'{"a":"\\"' + b"[" * 200 + b'"}', {"a": '"' + "[" * 200}),
}


@pytest.mark.parametrize("name", sorted(REFUSED))
def test_v2_refuses_by_name(name):
    raw, phrase = REFUSED[name]
    with pytest.raises(CV.StrictJsonError) as e:
        CV.loads(raw, "probe [js:s7.0]")
    msg = str(e.value)
    assert msg.startswith("probe [js:s7.0] refused: " + phrase), msg
    assert msg.endswith(TAIL), msg


@pytest.mark.parametrize("name", sorted(ACCEPTED))
def test_v2_accepts(name):
    raw, want = ACCEPTED[name]
    got = CV.loads(raw, "probe [js:s7.0]")
    if want is not None:
        assert got == want


@pytest.mark.parametrize("raw,phrase", [
    (b'{"a":1,"a":2}', "duplicate key 'a'"),
    (b'{"a":NaN}', "non-finite number NaN (a NOUS writer can write this "
                   "token, so this refusal is not by itself evidence of "
                   "tampering)"),
    (b'\xef\xbb\xbf{}', "UTF-8 BOM (RFC 8259 8.1; a signer can sign these "
                        "bytes, so this refusal is not by itself evidence "
                        "of tampering)"),
    (b'{"a":"\xff"}', "not UTF-8 (RFC 8259 8.1, RFC 7493 2.1; a signer "
                      "can sign these bytes, so this refusal is not by "
                      "itself evidence of tampering)"),
], ids=["duplicate", "nan", "bom", "not_utf8"])
def test_d4_messages_unchanged(raw, phrase):
    with pytest.raises(CV.StrictJsonError) as e:
        CV.loads(raw, "probe")
    assert str(e.value) == "probe refused: " + phrase


def test_census_every_tracked_json_file_reads():
    p = subprocess.run(["git", "-C", str(REPO), "ls-files", "*.json"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        pytest.skip("git ls-files unavailable: " + p.stderr[:80])
    files = p.stdout.split()
    assert len(files) >= 300
    refused = []
    for f in files:
        try:
            CV.loads((REPO / f).read_bytes(), f)
        except CV.StrictJsonError as e:
            refused.append(str(e)[:120])
    assert refused == []


def _with_overflow_member(text: str) -> str:
    s = text.lstrip()
    assert s[0] == "{"
    return '{"zz":1e400,' + s[1:]


def test_offline_conformance_text_refuses_overflow(tmp_path):
    d, ck, mk = X5._bundle(tmp_path, "proven", "b")
    e = tmp_path / "e"
    e.mkdir()
    for name in ("conformance.json", "trace.json", "source.nous",
                 "pricing.toml"):
        (e / name).write_bytes((d / name).read_bytes())
    (e / "manifest.json").write_text(
        _with_overflow_member((d / "manifest.json").read_text()))
    rc, out, err, last = X5._offline(
        e, CV.CONFORMANCE_VERIFY_OFFLINE_PY, X5._pins(ck, mk))
    assert rc == 1 and last == "CLASS: INTEGRITY", (rc, last)
    assert ("manifest.json [js:conf.2] refused: number out of range "
            "1e400") in out + err


def test_api_route_refuses_overflow(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import nous_api_server as srv

    monkeypatch.setattr(srv.limiter, "enabled", False)
    d, _ck, _mk = X5._bundle(tmp_path, "proven", "b")
    text = _with_overflow_member((d / "manifest.json").read_text())
    doc = TestClient(srv.app).post(
        "/v1/verify-dossier",
        json={"manifest_json": text, "policy": PERM}).json()
    assert doc["verdict"] == "REJECT", doc
    errs = doc["checks"]["manifest_well_formed"]["errors"]
    assert ("manifest_json [js:api.4] refused: number out of range "
            "1e400") in errs[0], errs
