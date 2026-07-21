"""C2 conformance suite: every normative property of SPEC 3.1.2, verified
against the SHIPPED emitted verifier (build_dossier -> verify_offline.py),
not a copy. Each vector maps one-to-one to a normative property; this is a
conformance suite, not a regression suite.

Two tiers:
  offline  hermetic, no network; copies the committed C1-valid reference
           bundle and mutates the committed reference token / receipt.
  live     P1/B1 against a real production TSA; run only with --run-live.

Reference evidence (tests/reference_evidence/, produced by
capture_c2_reference_evidence.py): the complete C1-valid trace bundle plus a
real Sigstore token over its manifest bytes. If the pinned TSA root ever
rotates, the crypto vectors here will FAIL by design -- the signal to
re-capture, not a defect.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import base64
import dataclasses
import hashlib
import json
import shutil
import subprocess

import pytest

manifest_mod = pytest.importorskip("manifest")
trace_bridge = pytest.importorskip("trace_bridge")
dossier = pytest.importorskip("dossier")
cli_verify = pytest.importorskip("cli_verify")
tba_mod = pytest.importorskip("trace_bundle_anchor")

_REPO = _Path(__file__).resolve().parent.parent
_TEMPLATE = _REPO / "templates" / "cost_cap_with_souls.nous"
_REF = _REPO / "tests" / "reference_evidence"


def _ref_token():
    p = _REF / "trace_bundle_c2_token.der"
    if not p.is_file():
        pytest.skip("reference evidence missing; run capture_c2_reference_evidence.py")
    return p.read_bytes()


def _ref_bundle_dir():
    d = _REF / "trace_bundle"
    if not (d / "manifest.json").is_file():
        pytest.skip("reference bundle missing; run capture_c2_reference_evidence.py")
    return d


def _signed_source(tmp_path):
    if not _TEMPLATE.is_file():
        pytest.skip("template not present")
    src = tmp_path / "source.nous"
    shutil.copy2(_TEMPLATE, src)

    class Args:
        file = str(src); smt = True; prices = None; timeout_ms = 30000
        no_manifest = False; manifest_out = None; key_path = None
        smt_margin = 0; no_lint = True; lint_strict = False; lint_error_on = None

    if cli_verify.cmd_verify(Args()) != 0:
        pytest.skip("cmd_verify could not prove the template")
    return src, src.with_suffix(".manifest.json")


def _build_pack(where):
    with trace_bridge.TraceBridge(str(where / "trace_bundle"), "actor", [],
                                  str(where / "keys")) as tb:
        tb.tool_call("t", "ad", input_bytes=b"{}")
        tb.checkpoint()


def _run_emitted(out):
    r = subprocess.run(["python3", str(out / "verify_offline.py")],
                       capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def _assemble_from_reference(tmp_path, token_der, **kw):
    """Assemble a dossier input using the COMPLETE committed reference bundle
    (C1-valid), so the reference token's imprint binds and C1 passes, letting
    the C2 leg run. Copies the whole tree; overwrites nothing inside it."""
    src, mpath = _signed_source(tmp_path)
    ref = _ref_bundle_dir()
    dst = tmp_path / "trace_bundle"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(ref, dst)
    ref_bm = (dst / "manifest.json").read_bytes()
    tb_sha = hashlib.sha256(ref_bm).hexdigest()

    anchored = kw.get("anchored_sha_override") or tb_sha
    receipt = {"trace_bundle_anchor_schema_version": kw.get("schema_version", 1),
               "anchored_bundle_sha256": anchored}
    if not kw.get("drop_token"):
        receipt["tsa_rfc3161_token_b64"] = base64.b64encode(token_der).decode()
    rb = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
    (tmp_path / "trace_bundle.anchor.json").write_bytes(rb)
    tba_sha = hashlib.sha256(rb).hexdigest()

    parsed, _, _ = manifest_mod.parse_manifest_json(mpath.read_text())
    parsed = dataclasses.replace(
        parsed,
        trace_bundle_sha256=(tb_sha if kw.get("with_c1", True) else None),
        trace_bundle_anchor_sha256=tba_sha)
    priv, pub, _ = manifest_mod.load_or_create_keypair(None)
    mpath.write_text(
        manifest_mod.manifest_json(parsed, manifest_mod.sign_manifest(parsed, priv), pub),
        encoding="utf-8")
    return src, mpath


# =====================================================================
# OFFLINE conformance -- hermetic.
# =====================================================================

@pytest.mark.offline
def test_P1_offline_reference_token_valid(tmp_path):
    # Positive: committed reference token verifies through the emitted verifier.
    src, _ = _assemble_from_reference(tmp_path, _ref_token())
    out = tmp_path / "out"
    dossier.build_dossier(src, output=out)
    rc, so, se = _run_emitted(out)
    assert rc == 0, (so, se)
    assert "ANCHORED-ABSOLUTE" in so
    meta = json.loads((_REF / "trace_bundle_c2_meta.json").read_text())
    assert meta["t_attest_utc"] in so


@pytest.mark.offline
def test_I1_receipt_hash_mismatch(tmp_path):
    # Identity: receipt bytes changed after signing -> sha-gate refuses at build.
    src, _ = _assemble_from_reference(tmp_path, _ref_token())
    rp = tmp_path / "trace_bundle.anchor.json"
    r = json.loads(rp.read_text()); r["anchored_bundle_sha256"] = "aa" * 32
    rp.write_text(json.dumps(r, sort_keys=True, separators=(",", ":")))
    with pytest.raises(Exception) as ei:
        dossier.build_dossier(src, output=tmp_path / "out")
    assert "sha256 mismatch" in str(ei.value)


@pytest.mark.offline
def test_I3_c2_without_c1_refused(tmp_path):
    # Identity: C2 present, C1 absent -> refused at build (C2 presupposes C1).
    src, _ = _assemble_from_reference(tmp_path, _ref_token(), with_c1=False)
    with pytest.raises(Exception) as ei:
        dossier.build_dossier(src, output=tmp_path / "out")
    assert "presupposes C1" in str(ei.value) or "no trace_bundle_sha256" in str(ei.value)


@pytest.mark.offline
def test_R1_schema_version_wrong(tmp_path):
    # Receipt-format: emitted verifier rejects an unknown schema version.
    src, _ = _assemble_from_reference(tmp_path, _ref_token(), schema_version=2)
    out = tmp_path / "out"
    dossier.build_dossier(src, output=out)
    rc, so, se = _run_emitted(out)
    assert rc == 1 and "schema_version" in se


@pytest.mark.offline
def test_R2_token_missing(tmp_path):
    # Receipt-format: no token field.
    src, _ = _assemble_from_reference(tmp_path, _ref_token(), drop_token=True)
    out = tmp_path / "out"
    dossier.build_dossier(src, output=out)
    rc, so, se = _run_emitted(out)
    assert rc == 1 and "tsa_rfc3161_token_b64" in se


@pytest.mark.offline
def test_C1_tampered_signature(tmp_path):
    # Cryptographic: flip a byte deep in the token -> token invalid / malformed.
    tampered = bytearray(_ref_token()); tampered[-40] ^= 0x01
    src, _ = _assemble_from_reference(tmp_path, bytes(tampered))
    out = tmp_path / "out"
    dossier.build_dossier(src, output=out)
    rc, so, se = _run_emitted(out)
    assert rc == 1 and ("does NOT verify" in se or "malformed" in se
                        or "RFC 3161" in se)


@pytest.mark.offline
def test_C3_corrupted_asn1(tmp_path):
    # Cryptographic: a tiny bogus DER -> malformed token.
    src, _ = _assemble_from_reference(tmp_path, b"\x30\x03\x02\x01\x07")
    out = tmp_path / "out"
    dossier.build_dossier(src, output=out)
    rc, so, se = _run_emitted(out)
    assert rc == 1 and ("malformed" in se or "does NOT verify" in se
                        or "RFC 3161" in se)


@pytest.mark.offline
def test_BY_bundle_bytes_drift_breaks_imprint_or_identity(tmp_path):
    # Byte-identity: re-serialize the bundle manifest (canonical drift) while the
    # receipt still claims the original sha -> identity/imprint FAIL.
    src, _ = _assemble_from_reference(tmp_path, _ref_token())
    out = tmp_path / "out"
    dossier.build_dossier(src, output=out)
    bmf = out / "trace_bundle" / "manifest.json"
    reser = json.dumps(json.loads(bmf.read_text()),
                       sort_keys=True, separators=(",", ":")).encode()
    if reser == bmf.read_bytes():
        pytest.skip("reference bundle already canonical; no drift to induce")
    bmf.write_bytes(reser)
    rc, so, se = _run_emitted(out)
    assert rc == 1


@pytest.mark.offline
def test_P2_P3_purity_determinism(tmp_path):
    # Purity + determinism: identical output + stable T_attest across runs.
    src, _ = _assemble_from_reference(tmp_path, _ref_token())
    out = tmp_path / "out"
    dossier.build_dossier(src, output=out)
    runs = [_run_emitted(out) for _ in range(3)]
    assert len({r[0] for r in runs}) == 1 and runs[0][0] == 0, runs[0]
    meta = json.loads((_REF / "trace_bundle_c2_meta.json").read_text())
    for _, so, _ in runs:
        assert meta["t_attest_utc"] in so


# =====================================================================
# LIVE profile verification -- real TSA.
# =====================================================================

@pytest.mark.live
def test_P1_live_full_chain(tmp_path):
    from tsa_client import anchor_timestamp, TSA_DEFAULT_URL
    src, mpath = _signed_source(tmp_path)
    _build_pack(tmp_path)
    bm = (tmp_path / "trace_bundle" / "manifest.json").read_bytes()
    tb_sha = hashlib.sha256(bm).hexdigest()
    token = anchor_timestamp(timestamped_data=bm, base_url=TSA_DEFAULT_URL,
                             timeout_seconds=30)
    receipt = tba_mod.build_trace_bundle_anchor_receipt(
        bundle_manifest_bytes=bm, tsa_rfc3161_token_der=token)
    rb = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
    (tmp_path / "trace_bundle.anchor.json").write_bytes(rb)
    tba_sha = hashlib.sha256(rb).hexdigest()
    parsed, _, _ = manifest_mod.parse_manifest_json(mpath.read_text())
    parsed = dataclasses.replace(parsed, trace_bundle_sha256=tb_sha,
                                 trace_bundle_anchor_sha256=tba_sha)
    priv, pub, _ = manifest_mod.load_or_create_keypair(None)
    mpath.write_text(
        manifest_mod.manifest_json(parsed, manifest_mod.sign_manifest(parsed, priv), pub),
        encoding="utf-8")
    out = tmp_path / "out"
    dossier.build_dossier(src, output=out)
    rc, so, se = _run_emitted(out)
    assert rc == 0 and "ANCHORED-ABSOLUTE" in so, (so, se)


@pytest.mark.live
def test_B1_live_imprint_binding(tmp_path):
    # Valid production token over bundle A, dossier bundle is B -> imprint FAIL.
    from tsa_client import anchor_timestamp, TSA_DEFAULT_URL
    src, mpath = _signed_source(tmp_path)
    _build_pack(tmp_path)
    bmB = (tmp_path / "trace_bundle" / "manifest.json").read_bytes()
    tbB = hashlib.sha256(bmB).hexdigest()
    tokenA = anchor_timestamp(timestamped_data=bmB + b" ",
                              base_url=TSA_DEFAULT_URL, timeout_seconds=30)
    receipt = {"trace_bundle_anchor_schema_version": 1,
               "anchored_bundle_sha256": tbB,
               "tsa_rfc3161_token_b64": base64.b64encode(tokenA).decode()}
    rb = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
    (tmp_path / "trace_bundle.anchor.json").write_bytes(rb)
    tba_sha = hashlib.sha256(rb).hexdigest()
    parsed, _, _ = manifest_mod.parse_manifest_json(mpath.read_text())
    parsed = dataclasses.replace(parsed, trace_bundle_sha256=tbB,
                                 trace_bundle_anchor_sha256=tba_sha)
    priv, pub, _ = manifest_mod.load_or_create_keypair(None)
    mpath.write_text(
        manifest_mod.manifest_json(parsed, manifest_mod.sign_manifest(parsed, priv), pub),
        encoding="utf-8")
    out = tmp_path / "out"
    dossier.build_dossier(src, output=out)
    rc, so, se = _run_emitted(out)
    assert rc == 1 and "messageImprint" in se, (so, se)
