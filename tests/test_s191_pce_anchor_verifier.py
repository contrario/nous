"""S191 4d: PCE-anchor temporal verifier embed -- real-token round-trip.

The dossier carries _check_pce_anchor as the _PCE_ANCHOR_CHECK_EMBED string.
These tests extract that exact embed, exec it, and drive it against the
RECORDED Sigstore TSA fixtures (no network):

  1. PORT PARITY: the embed's _pa_verify_rfc3161 agrees with the AUTHORITATIVE
     tsa_verify.verify_rfc3161_timestamp on the real token.der/data.bin pair
     (same ok, same gen_time) -- the embedded port can never drift from the
     committed library.
  2. ANCHORED-ABSOLUTE: a receipt whose RFC 3161 token verifies over pce.json,
     with no in-dossier change-time -> rc 0, temporal_precedence
     "anchored-absolute", t_change null.
  3. RELATIONAL: with both an envelope token and a change-time token recovered
     from real fixtures, the four-state verdict equals the recovered genTime
     ordering (anchored iff t_env < t_change, else post-hoc). Monitor: rc 0.
  4. INTEGRITY (fail-closed, rc 1): receipt sha mismatch; anchored_pce_sha256
     != sha256(pce.json); an RFC 3161 token that does not bind its data.
  5. ABSENT: no pce_anchor_sha256 and no sidecar -> rc 0, silent.

importorskip keeps this green-on-server and skipped where dossier/tsa_verify
or the fixtures are not present.

# __s191_pce_anchor_embed_v1__
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import json
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import pytest

dossier = pytest.importorskip("dossier")
tsa_verify = pytest.importorskip("tsa_verify")

_FIXTURES = Path(__file__).resolve().parent / "tsa_fixtures"


def _have(name: str) -> bool:
    return (_FIXTURES / name).is_file()


def _fx(name: str) -> bytes:
    return (_FIXTURES / name).read_bytes()


def _load_embed():
    src = getattr(dossier, "_PCE_ANCHOR_CHECK_EMBED", None)
    assert isinstance(src, str) and "_check_pce_anchor" in src, (
        "dossier._PCE_ANCHOR_CHECK_EMBED missing"
    )
    ns: dict = {}
    exec(compile(src, "<embed>", "exec"), ns)
    return ns


def _run(ns: dict, root: Path, manifest: dict):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = ns["_check_pce_anchor"](manifest, root)
    verdict = None
    for ln in buf.getvalue().splitlines():
        if ln.startswith("PCE_ANCHOR_VERDICT_JSON: "):
            verdict = json.loads(ln.split(": ", 1)[1])
    return rc, verdict


def _leaf_body_b64(leaf_sig: bytes) -> str:
    leaf = {
        "spec": {
            "hashedRekordV002": {
                "signature": {
                    "content": base64.b64encode(leaf_sig).decode("ascii")
                }
            }
        }
    }
    return base64.b64encode(
        json.dumps(leaf).encode("utf-8")
    ).decode("ascii")


def _dossier(tmp: Path, pce_bytes: bytes, env_token: bytes, *,
             anchored_sha=None, tlog_token=None, tlog_leaf_sig=None,
             bad_receipt_sha=False) -> dict:
    (tmp / "pce.json").write_bytes(pce_bytes)
    pce_sha = hashlib.sha256(pce_bytes).hexdigest()
    receipt = {
        "pce_anchor_schema_version": 1,
        "anchored_pce_sha256": anchored_sha if anchored_sha is not None
        else pce_sha,
        "basis": "pre-commitment-in-time; not a legal determination",
        "pce_rfc3161_token_b64": base64.b64encode(env_token).decode("ascii"),
    }
    rb = json.dumps(receipt).encode("utf-8")
    (tmp / "pce.anchor.json").write_bytes(rb)
    manifest = {
        "pce_sha256": pce_sha,
        "pce_anchor_sha256": ("deadbeef" * 8) if bad_receipt_sha
        else hashlib.sha256(rb).hexdigest(),
    }
    if tlog_token is not None:
        manifest["transparency_log"] = {
            "rfc3161_token_b64": base64.b64encode(tlog_token).decode("ascii"),
            "body_b64": _leaf_body_b64(tlog_leaf_sig),
        }
    return manifest


def test_port_parity_against_installed_tsa_verify():
    if not (_have("token.der") and _have("data.bin")):
        pytest.skip("tsa fixtures not present")
    ns = _load_embed()
    token, data = _fx("token.der"), _fx("data.bin")
    ok, gen_time, errors = ns["_pa_verify_rfc3161"](token, data)
    auth = tsa_verify.verify_rfc3161_timestamp(
        token_der=token, timestamped_data=data
    )
    assert ok is True and not errors
    assert auth.ok is True
    assert gen_time == auth.gen_time


def test_anchored_absolute(tmp_path):
    if not (_have("token.der") and _have("data.bin")):
        pytest.skip("tsa fixtures not present")
    ns = _load_embed()
    data = _fx("data.bin")
    manifest = _dossier(tmp_path, data, _fx("token.der"))
    rc, verdict = _run(ns, tmp_path, manifest)
    assert rc == 0
    assert verdict["temporal_precedence"] == "anchored-absolute"
    assert verdict["t_change_utc"] is None
    assert verdict["t_env_utc"]


def test_relational_same_token_is_post_hoc(tmp_path):
    if not (_have("token.der") and _have("data.bin")):
        pytest.skip("tsa fixtures not present")
    ns = _load_embed()
    data = _fx("data.bin")
    token = _fx("token.der")
    # change-time token = same real token over the SAME bytes as leaf sig ->
    # t_env == t_change -> post-hoc (T_env >= T_change). Deterministic, real.
    manifest = _dossier(
        tmp_path, data, token, tlog_token=token, tlog_leaf_sig=data
    )
    rc, verdict = _run(ns, tmp_path, manifest)
    assert rc == 0
    assert verdict["temporal_precedence"] == "post-hoc"
    assert verdict["t_env_utc"] == verdict["t_change_utc"]


def test_relational_two_real_tokens_matches_ordering(tmp_path):
    need = ("token.der", "data.bin", "v2ts_token.der", "v2ts_sig.der")
    if not all(_have(n) for n in need):
        pytest.skip("second real-token fixture pair not present")
    ns = _load_embed()
    v2_ok, _t, _e = ns["_pa_verify_rfc3161"](
        _fx("v2ts_token.der"), _fx("v2ts_sig.der")
    )
    if not v2_ok:
        pytest.skip("v2ts token does not verify over v2ts_sig (not a pair)")
    data = _fx("data.bin")
    manifest = _dossier(
        tmp_path, data, _fx("token.der"),
        tlog_token=_fx("v2ts_token.der"), tlog_leaf_sig=_fx("v2ts_sig.der"),
    )
    rc, verdict = _run(ns, tmp_path, manifest)
    assert rc == 0
    from datetime import datetime as _dt
    t_env = _dt.fromisoformat(verdict["t_env_utc"])
    t_change = _dt.fromisoformat(verdict["t_change_utc"])
    expected = "anchored" if t_env < t_change else "post-hoc"
    assert verdict["temporal_precedence"] == expected


def test_integrity_bad_receipt_sha(tmp_path):
    if not (_have("token.der") and _have("data.bin")):
        pytest.skip("tsa fixtures not present")
    ns = _load_embed()
    data = _fx("data.bin")
    manifest = _dossier(tmp_path, data, _fx("token.der"), bad_receipt_sha=True)
    rc, verdict = _run(ns, tmp_path, manifest)
    assert rc == 1
    assert verdict is None


def test_integrity_anchored_bytes_mismatch(tmp_path):
    if not (_have("token.der") and _have("data.bin")):
        pytest.skip("tsa fixtures not present")
    ns = _load_embed()
    data = _fx("data.bin")
    manifest = _dossier(
        tmp_path, data, _fx("token.der"),
        anchored_sha=hashlib.sha256(b"other").hexdigest(),
    )
    rc, verdict = _run(ns, tmp_path, manifest)
    assert rc == 1
    assert verdict is None


def test_integrity_token_does_not_bind_envelope(tmp_path):
    if not (_have("token.der") and _have("data.bin")):
        pytest.skip("tsa fixtures not present")
    ns = _load_embed()
    # pce.json is NOT data.bin, so the real token.der imprint does not bind.
    manifest = _dossier(tmp_path, b"not the timestamped bytes", _fx("token.der"))
    rc, verdict = _run(ns, tmp_path, manifest)
    assert rc == 1
    assert verdict is None


def test_absent_receipt_silent(tmp_path):
    ns = _load_embed()
    rc, verdict = _run(ns, tmp_path, {"pce_sha256": "x"})
    assert rc == 0
    assert verdict is None
