"""X-G3 -- an auditor-supplied expected signer on the two verify endpoints.

FG-S415-X, X_INNOVATION_GATE.md XD1-XD3: /v1/verify-conformance and
/v1/verify-dossier accept an optional expected_signer_b64 request field.
It is a request field, not a policy field, so that default responses,
which echo the policy, stay byte-identical. Absent or null: unchanged.

The bundle is a committed demo vector, unaltered. The "other" key is a
fresh public key that signs nothing.

Honest boundary: a pinned-signer pass EVIDENCES that the artifact was
signed by the holder of the expected key. Who holds that key is
established out of band; it is not a proof of the run.

# __x_g3_endpoint_pin_tests_v1__
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient

_VEC = Path(__file__).resolve().parents[1] / "examples" / "demos" / "cert-4679350"
_CERT_MISMATCH = "certificate signer is not the expected key"
_MAN_MISMATCH = "manifest signer is not the expected key"
_BADKEY = "expected signer key is not a base64 raw 32-byte Ed25519 public key"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import nous_api_server as srv

    monkeypatch.setattr(srv.limiter, "enabled", False)
    return TestClient(srv.app)


def _read(name: str) -> str:
    return (_VEC / name).read_text(encoding="utf-8")


def _key_of(name: str) -> str:
    return json.loads(_read(name))["signature"]["public_key_b64"]


def _fresh_key_b64() -> str:
    raw = Ed25519PrivateKey.generate().public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw
    )
    return base64.b64encode(raw).decode("ascii")


def _conf(client: TestClient, **extra):
    body = {
        "certificate_json": _read("conformance.json"),
        "trace_json": _read("trace.json"),
        "manifest_json": _read("manifest.json"),
    }
    body.update(extra)
    return client.post("/v1/verify-conformance", json=body)


def _dossier(client: TestClient, v2: bool, **extra):
    body = {"manifest_json": _read("manifest.json")}
    if v2:
        body["policy"] = {"require_anchor": False}
    body.update(extra)
    return client.post("/v1/verify-dossier", json=body)


def _strip_age(doc: dict) -> dict:
    ev = doc.get("evidence")
    if isinstance(ev, dict):
        ev.pop("rekor_anchor_age_seconds", None)
    return doc


def test_e1_conformance_null_equals_absent(client: TestClient) -> None:
    a = _conf(client)
    b = _conf(client, expected_signer_b64=None)
    assert a.status_code == 200 and b.status_code == 200
    assert a.json() == b.json()
    assert a.json()["verdict"] == "PASS"


def test_e2_conformance_own_key_equals_default(client: TestClient) -> None:
    a = _conf(client)
    b = _conf(client, expected_signer_b64=_key_of("conformance.json"))
    assert b.status_code == 200
    assert a.json() == b.json()


def test_e3_conformance_fresh_key_fails(client: TestClient) -> None:
    r = _conf(client, expected_signer_b64=_fresh_key_b64())
    assert r.status_code == 200
    doc = r.json()
    assert doc["verdict"] == "FAIL"
    assert doc["signature"]["ok"] is False
    assert doc["signature"]["detail"] == _CERT_MISMATCH


def test_e4_conformance_malformed_key(client: TestClient) -> None:
    r = _conf(client, expected_signer_b64="not base64 !")
    assert r.status_code == 200
    doc = r.json()
    assert doc["verdict"] == "MALFORMED"
    assert doc["errors"] == [_BADKEY]


def test_e5_dossier_v2_null_equals_absent(client: TestClient) -> None:
    a = _dossier(client, True)
    b = _dossier(client, True, expected_signer_b64=None)
    assert a.status_code == 200 and b.status_code == 200
    assert _strip_age(a.json()) == _strip_age(b.json())
    assert a.json()["verdict"] == "ACCEPT"


def test_e6_dossier_v2_own_key_equals_default(client: TestClient) -> None:
    a = _dossier(client, True)
    b = _dossier(client, True, expected_signer_b64=_key_of("manifest.json"))
    assert b.status_code == 200
    assert _strip_age(a.json()) == _strip_age(b.json())


def test_e7_dossier_v2_fresh_key_rejects(client: TestClient) -> None:
    r = _dossier(client, True, expected_signer_b64=_fresh_key_b64())
    assert r.status_code == 200
    doc = r.json()
    assert doc["verdict"] == "REJECT"
    sig = doc["checks"]["manifest_signature_ed25519"]
    assert sig["ok"] is False
    assert _MAN_MISMATCH in sig["errors"]


def test_e8_dossier_v2_malformed_key_rejects(client: TestClient) -> None:
    r = _dossier(client, True, expected_signer_b64="not base64 !")
    assert r.status_code == 200
    doc = r.json()
    assert doc["verdict"] == "REJECT"
    assert _BADKEY in doc["checks"]["manifest_signature_ed25519"]["errors"]


def test_e9_dossier_v1_fresh_key(client: TestClient) -> None:
    r = _dossier(client, False, expected_signer_b64=_fresh_key_b64())
    assert r.status_code == 200
    doc = r.json()
    assert doc["signature_ok"] is False
    assert _MAN_MISMATCH in doc["errors"]


def test_e10_dossier_v1_own_key_equals_default(client: TestClient) -> None:
    a = _dossier(client, False)
    b = _dossier(client, False, expected_signer_b64=_key_of("manifest.json"))
    assert b.status_code == 200
    assert a.json() == b.json()
