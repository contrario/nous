"""API Gate (seat 427), APIG-1, APIG-2, APIG-3: the public verification
API gives no ACCEPT and no PASS over a cost bound that is not
established.

APIG-1. POST /v1/verify-dossier with a policy (spec_version
verify-dossier/v3) carries a ninth check, solver_verdict, and returns
OUTSIDE when every check the policy required passed and the manifest's
solver verdict is not 'proven'. Integrity and policy come first: a
manifest that fails one is REJECT whatever its verdict. The V1 path
(no policy) is unchanged.

APIG-2. conformance.verify_certificate_from_json (POST
/v1/verify-conformance, spec_version verify-conformance/v2) checks the
manifest's Ed25519 signature when a manifest is given, under
expected_manifest_signer_b64 when given, else under the key the
manifest carries, and returns OUTSIDE when every check ran and passed,
the certificate records a conformant run, and the manifest's solver
verdict is not 'proven'.

APIG-3. The two pages paint OUTSIDE neither green nor red and read
both spec versions; the documents name OUTSIDE and the new versions.

Every bundle is built fresh by test_xd5_outside_conformance's builder:
the manifest by manifest_from_verify, the trace by sign_trace, each
signed once under its own fresh key; the certificate by the real
certify. A failing manifest signature is a stub of
manifest.verify_manifest_signature; no artifact is altered or
re-signed. The manifest without a signature is a synthetic document
made here, not an edited one. No network.

# __apig_outside_api_test_v1__
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)
from fastapi.testclient import TestClient

import conformance
import manifest as mf
import test_xd5_outside_conformance as X5

REPO = Path(__file__).resolve().parent.parent
PERM = {"require_anchor": False, "require_pubkey_in_allowlist": False}
MAN_MISMATCH = "manifest signer is not the expected key"
MAN_BADKEY = ("expected manifest signer key is not a base64 raw 32-byte "
              "Ed25519 public key")
V1_KEYS = {"signature_ok", "public_key_b64", "rekor_inclusion_ok",
           "rekor_set_ok", "rekor_log_index", "rekor_integrated_at",
           "manifest_sha256", "errors"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import nous_api_server as srv

    monkeypatch.setattr(srv.limiter, "enabled", False)
    return TestClient(srv.app)


def _fresh_b64() -> str:
    raw = Ed25519PrivateKey.generate().public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def _read(d: Path, name: str) -> str:
    return (d / name).read_text(encoding="utf-8")


def _sig_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mf, "verify_manifest_signature",
                        lambda *a, **k: False)


def _dossier(client, d, policy=PERM, **extra):
    body = {"manifest_json": _read(d, "manifest.json")}
    if policy is not None:
        body["policy"] = policy
    body.update(extra)
    r = client.post("/v1/verify-dossier", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _lib(d, trace=True, manifest=True, **kw):
    return conformance.verify_certificate_from_json(
        _read(d, "conformance.json"),
        _read(d, "trace.json") if trace else None,
        _read(d, "manifest.json") if manifest else None,
        **kw)


def _conf(client, d, **extra):
    body = {"certificate_json": _read(d, "conformance.json"),
            "trace_json": _read(d, "trace.json"),
            "manifest_json": _read(d, "manifest.json")}
    body.update(extra)
    return client.post("/v1/verify-conformance", json=body)


# ------------------------------------------------------------ APIG-1


@pytest.mark.parametrize("verdict", ["refuted", "unknown"])
def test_d01_not_proven_is_outside(tmp_path, client, verdict):
    d, _ck, _mk = X5._bundle(tmp_path, verdict, "b")
    doc = _dossier(client, d)
    assert doc["spec_version"] == "verify-dossier/v3"
    assert doc["verdict"] == "OUTSIDE"
    assert doc["trust_level"] == "ed25519_only"
    assert doc["checks"]["manifest_signature_ed25519"] == {
        "ok": True, "errors": []}
    sv = doc["checks"]["solver_verdict"]
    assert sv["ok"] is False
    assert any(repr(verdict) in e for e in sv["errors"]), sv
    hr = doc["human_readable"]
    assert "not 'proven'" in hr["verdict_summary"]
    assert hr["next_steps"]
    assert "authentic" not in json.dumps(hr).lower()


def test_d02_proven_accept_guard(tmp_path, client):
    d, _ck, _mk = X5._bundle(tmp_path, "proven", "b")
    doc = _dossier(client, d)
    assert doc["verdict"] == "ACCEPT"
    assert doc["checks"]["manifest_signature_ed25519"]["ok"] is True


def test_d03_proven_names_the_check(tmp_path, client):
    d, _ck, _mk = X5._bundle(tmp_path, "proven", "b")
    doc = _dossier(client, d)
    assert doc["spec_version"] == "verify-dossier/v3"
    assert doc["checks"]["solver_verdict"] == {"ok": True, "errors": []}


def test_d04_refuted_default_policy_rejects_guard(tmp_path, client):
    d, _ck, _mk = X5._bundle(tmp_path, "refuted", "b")
    assert _dossier(client, d, policy={})["verdict"] == "REJECT"


def test_d05_refuted_other_signer_rejects_guard(tmp_path, client):
    d, _ck, _mk = X5._bundle(tmp_path, "refuted", "b")
    doc = _dossier(client, d, expected_signer_b64=_fresh_b64())
    assert doc["verdict"] == "REJECT"


def test_d06_refuted_signature_fails_rejects_guard(tmp_path, client,
                                                   monkeypatch):
    d, _ck, _mk = X5._bundle(tmp_path, "refuted", "b")
    _sig_fails(monkeypatch)
    doc = _dossier(client, d)
    assert doc["verdict"] == "REJECT"
    assert doc["trust_level"] == "none"


def test_d07_refuted_own_signer_is_outside(tmp_path, client):
    d, _ck, mk = X5._bundle(tmp_path, "refuted", "b")
    doc = _dossier(client, d, expected_signer_b64=mk)
    assert doc["verdict"] == "OUTSIDE"


def test_d08_outside_round_trips(tmp_path, client):
    from nous_api_server import VerifyDossierEndpointResponseV2

    d, _ck, _mk = X5._bundle(tmp_path, "refuted", "b")
    parsed = VerifyDossierEndpointResponseV2(**_dossier(client, d))
    assert parsed.verdict == "OUTSIDE"
    assert parsed.checks.solver_verdict.ok is False


def test_d09_unparsed_rejects_with_the_check(client):
    r = client.post("/v1/verify-dossier", json={
        "manifest_json": "not a manifest", "policy": PERM})
    doc = r.json()
    assert doc["verdict"] == "REJECT"
    assert doc["checks"]["solver_verdict"]["ok"] is False


def test_d10_v1_unchanged_guard(tmp_path, client):
    d, _ck, _mk = X5._bundle(tmp_path, "refuted", "b")
    doc = _dossier(client, d, policy=None)
    assert set(doc) == V1_KEYS
    assert doc["signature_ok"] is True
    assert doc["errors"] == []


# ------------------------------------------------------------ APIG-2


@pytest.mark.parametrize("verdict", ["refuted", "unknown"])
def test_c01_not_proven_is_outside(tmp_path, verdict):
    d, ck, _mk = X5._bundle(tmp_path, verdict, "b")
    res = _lib(d, expected_signer_b64=ck)
    assert res.spec_version == "verify-conformance/v2"
    assert res.verdict == "OUTSIDE"
    assert res.solver_verdict == verdict
    assert res.manifest_signature.ok is True
    assert res.conformant is True
    assert res.errors == []


def test_c02_proven_pass_guard(tmp_path):
    d, ck, _mk = X5._bundle(tmp_path, "proven", "b")
    assert _lib(d, expected_signer_b64=ck).verdict == "PASS"


def test_c03_proven_names_the_check(tmp_path):
    d, ck, _mk = X5._bundle(tmp_path, "proven", "b")
    res = _lib(d, expected_signer_b64=ck)
    assert res.spec_version == "verify-conformance/v2"
    assert res.solver_verdict == "proven"
    assert res.manifest_signature.ok is True
    assert res.manifest_signature.skipped is False


def test_c04_no_manifest_inconclusive_guard(tmp_path):
    d, ck, _mk = X5._bundle(tmp_path, "refuted", "b")
    assert _lib(d, manifest=False,
                expected_signer_b64=ck).verdict == "INCONCLUSIVE"


def test_c05_no_manifest_skips_the_check(tmp_path):
    d, ck, _mk = X5._bundle(tmp_path, "refuted", "b")
    res = _lib(d, manifest=False, expected_signer_b64=ck)
    assert res.manifest_signature.skipped is True
    assert res.solver_verdict is None


def test_c06_no_trace_inconclusive_guard(tmp_path):
    d, ck, _mk = X5._bundle(tmp_path, "refuted", "b")
    assert _lib(d, trace=False,
                expected_signer_b64=ck).verdict == "INCONCLUSIVE"


@pytest.mark.parametrize("verdict", ["proven", "refuted"])
def test_c07_manifest_signature_fails_is_fail(tmp_path, monkeypatch,
                                              verdict):
    d, ck, _mk = X5._bundle(tmp_path, verdict, "b")
    _sig_fails(monkeypatch)
    res = _lib(d, expected_signer_b64=ck)
    assert res.verdict == "FAIL"
    assert res.manifest_signature.ok is False
    assert res.manifest_binding.ok is True
    assert res.solver_verdict is None


def test_c08_expected_manifest_signer_own_key_passes(tmp_path):
    d, ck, mk = X5._bundle(tmp_path, "proven", "b")
    res = _lib(d, expected_signer_b64=ck, expected_manifest_signer_b64=mk)
    assert res.verdict == "PASS"


def test_c09_expected_manifest_signer_other_key_fails(tmp_path):
    d, ck, _mk = X5._bundle(tmp_path, "proven", "b")
    res = _lib(d, expected_signer_b64=ck,
               expected_manifest_signer_b64=_fresh_b64())
    assert res.verdict == "FAIL"
    assert res.manifest_signature.ok is False
    assert res.manifest_signature.detail == MAN_MISMATCH
    assert MAN_MISMATCH in res.errors


def test_c10_expected_manifest_signer_malformed(tmp_path):
    d, ck, _mk = X5._bundle(tmp_path, "proven", "b")
    res = _lib(d, expected_signer_b64=ck,
               expected_manifest_signer_b64="not base64 !")
    assert res.verdict == "MALFORMED"
    assert res.errors == [MAN_BADKEY]


def test_c11_non_conformant_refuted_fail_guard(tmp_path):
    d, ck, _mk = X5._bundle(tmp_path, "refuted", "b", events=X5.OVER)
    res = _lib(d, expected_signer_b64=ck)
    assert res.conformant is False
    assert res.verdict == "FAIL"


def test_c12_unsigned_manifest_with_matching_digests_fails(tmp_path):
    d, ck, _mk = X5._bundle(tmp_path, "proven", "b")
    cert = json.loads(_read(d, "conformance.json"))
    bare = json.dumps({k: cert[k] for k in (
        "source_sha256", "smt_spec_sha256", "pricing_sha256")})
    res = conformance.verify_certificate_from_json(
        _read(d, "conformance.json"), _read(d, "trace.json"), bare,
        expected_signer_b64=ck)
    assert res.manifest_binding.ok is True
    assert res.manifest_signature.ok is False
    assert res.verdict == "FAIL"


def test_c13_endpoint_outside(tmp_path, client):
    d, ck, _mk = X5._bundle(tmp_path, "refuted", "b")
    r = _conf(client, d, expected_signer_b64=ck)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["spec_version"] == "verify-conformance/v2"
    assert doc["verdict"] == "OUTSIDE"
    assert doc["solver_verdict"] == "refuted"


def test_c14_endpoint_passes_the_manifest_pin(tmp_path, client):
    d, ck, _mk = X5._bundle(tmp_path, "proven", "b")
    r = _conf(client, d, expected_signer_b64=ck,
              expected_manifest_signer_b64=_fresh_b64())
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["verdict"] == "FAIL"
    assert doc["manifest_signature"]["detail"] == MAN_MISMATCH


def test_c15_endpoint_fallback_names_v2(tmp_path, client, monkeypatch):
    d, _ck, _mk = X5._bundle(tmp_path, "proven", "b")

    def boom(**_kw):
        raise RuntimeError("stub")

    monkeypatch.setattr(conformance, "verify_certificate_from_json", boom)
    r = _conf(client, d)
    assert r.status_code == 500
    assert r.json()["spec_version"] == "verify-conformance/v2"


# ------------------------------------------------------------ APIG-3


@pytest.mark.parametrize("rel", ["website/verify.html", "website/ide.html"])
def test_p01_pages_render_outside_neither_green_nor_red(rel):
    text = (REPO / rel).read_text(encoding="utf-8")
    assert "__apig3_outside_render_v1__" in text
    assert "verdict === 'OUTSIDE' ? 'var(--gold)'" in text
    assert "verdict === 'OUTSIDE' ? 'var(--gold-d)'" in text
    assert "data.spec_version !== 'verify-dossier/v2'" in text
    assert "data.spec_version !== 'verify-dossier/v3'" in text


def test_p02_documents_name_outside_and_the_versions():
    flat = lambda rel: " ".join((REPO / rel).read_text(  # noqa: E731
        encoding="utf-8").split())
    vd = flat("docs/VERIFY_DOSSIER.md")
    assert '"spec_version": "verify-dossier/v3"' in vd
    assert '"spec_version": "verify-dossier/v2"' not in vd
    assert "`verdict` is ACCEPT, REJECT or OUTSIDE" in vd
    assert "__apig_outside_docs_v1__" in vd
    an = flat("docs/ANNEX_IV_MAPPING.md")
    assert "`verdict: ACCEPT | REJECT | OUTSIDE`" in an
    rc = flat("docs/RUNTIME_CONFORMANCE.md")
    assert "`verify-conformance/v2`" in rc
    assert "`expected_manifest_signer_b64`" in rc
    head = (REPO / "CHANGELOG.md").read_text(encoding="utf-8").split(
        "\n## [8.0.0]", 1)[0]
    assert "__apig_outside_changelog_v1__" in head
