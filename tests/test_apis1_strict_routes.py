"""APIS-1 (seat S440, Gate NOUS_S440_GATE_SPLIT r2, D1): the public
verification routes read a signed artifact's text through the canonical
strict region, conformance_verifier.loads, before any other check, as
the offline verifiers do.

POST /v1/verify-conformance reads certificate_json, trace_json and
manifest_json (api.1 to api.3); a refusal is MALFORMED, the lib's own
form. POST /v1/verify-dossier reads manifest_json on the policy path
(api.4, manifest_well_formed fails, REJECT) and on the V1 path (api.5,
signature_ok false, a parse_error). Each message is the region's,
label first. Parity: on the same bytes the offline text exits
INTEGRITY and the route gives no PASS.

Every bundle is built fresh by test_xd5_outside_conformance._bundle,
each artifact signed once under a key made inside tmp_path; each
variant is a text edit that leaves the signed canonical body as it
was. No network.

# __apis1_strict_test_v1__
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import conformance_verifier as CV
import test_xd5_outside_conformance as X5

REPO = Path(__file__).resolve().parent.parent
PERM = {"require_anchor": False, "require_pubkey_in_allowlist": False}
SERVER = REPO / "nous_api_server.py"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import nous_api_server as srv

    monkeypatch.setattr(srv.limiter, "enabled", False)
    return TestClient(srv.app)


@pytest.fixture
def bundle(tmp_path):
    d, ck, mk = X5._bundle(tmp_path, "proven", "b")
    texts = {f: (d / f).read_text(encoding="utf-8")
             for f in ("conformance.json", "trace.json", "manifest.json")}
    return d, ck, mk, texts


def _first(text: str, key: str, value) -> str:
    s = text.lstrip()
    assert s[0] == "{"
    return "{" + json.dumps(key) + ":" + json.dumps(value) + "," + s[1:]


def _before_sig(text: str, ins: str) -> str:
    assert text.count('"signature_b64"') == 1
    i = text.index('"signature_b64"')
    return text[:i] + ins + text[i:]


def _bool_key(text: str) -> str:
    doc = json.loads(text)
    return sorted(k for k, v in doc.items() if isinstance(v, bool))[0]


def _variant(texts: dict, kind: str) -> dict:
    t = dict(texts)
    c = texts["conformance.json"]
    if kind == "cert_dup":
        k = _bool_key(c)
        t["conformance.json"] = _first(c, k, not json.loads(c)[k])
    elif kind == "cert_nan":
        t["conformance.json"] = _before_sig(c, '"x_probe": NaN, ')
    elif kind == "cert_bom":
        t["conformance.json"] = "\ufeff" + c
    elif kind == "trace_dup":
        t["trace.json"] = _first(texts["trace.json"], "world_name", "X")
    elif kind == "manifest_dup":
        t["manifest.json"] = _first(texts["manifest.json"], "verdict",
                                    "refuted")
    else:
        raise AssertionError(kind)
    return t


VARIANTS = {
    "cert_dup": ("certificate_json [js:api.1] refused: duplicate key"),
    "cert_nan": ("certificate_json [js:api.1] refused: non-finite number "
                 "NaN"),
    "cert_bom": "certificate_json [js:api.1] refused: UTF-8 BOM",
    "trace_dup": ("trace_json [js:api.2] refused: duplicate key "
                  "'world_name'"),
    "manifest_dup": ("manifest_json [js:api.3] refused: duplicate key "
                     "'verdict'"),
}


def _conf(client, texts, ck, mk):
    body = {"certificate_json": texts["conformance.json"],
            "trace_json": texts["trace.json"],
            "manifest_json": texts["manifest.json"],
            "expected_signer_b64": ck,
            "expected_manifest_signer_b64": mk}
    return client.post("/v1/verify-conformance", json=body)


def _dossier(client, text, policy=PERM):
    body = {"manifest_json": text}
    if policy is not None:
        body["policy"] = policy
    return client.post("/v1/verify-dossier", json=body)


# --------------------------------------------- /v1/verify-conformance


def test_conf_honest_is_pass(client, bundle):
    _d, ck, mk, texts = bundle
    r = _conf(client, texts, ck, mk)
    assert r.status_code == 200, r.text
    assert r.json()["verdict"] == "PASS"


@pytest.mark.parametrize("kind", sorted(VARIANTS))
def test_conf_variant_is_malformed_by_name(client, bundle, kind):
    _d, ck, mk, texts = bundle
    r = _conf(client, _variant(texts, kind), ck, mk)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["verdict"] == "MALFORMED"
    assert doc["parsed"] is False
    assert doc["errors"][0].startswith(VARIANTS[kind]), doc["errors"]


def test_helper_refuses_a_lone_surrogate_by_name():
    # An unpaired surrogate escape in the request body never reaches the
    # route: pydantic refuses the field (string_unicode) first. The
    # helper still encodes with surrogatepass, so a str holding one
    # from any other caller is the region's "not UTF-8", not a
    # UnicodeEncodeError.
    import conformance_verifier
    import nous_api_server as srv

    with pytest.raises(conformance_verifier.StrictJsonError) as e:
        srv._apis_strict('{"a": "\ud800"}', "probe [js:api.0]")
    assert str(e.value).startswith("probe [js:api.0] refused: not UTF-8")


@pytest.mark.parametrize("kind", sorted(VARIANTS))
def test_parity_offline_integrity_and_no_pass(client, bundle, kind,
                                              tmp_path):
    d, ck, mk, texts = bundle
    t = _variant(texts, kind)
    e = tmp_path / ("off_" + kind)
    e.mkdir()
    for name in ("source.nous", "pricing.toml"):
        (e / name).write_bytes((d / name).read_bytes())
    for name, text in t.items():
        (e / name).write_bytes(text.encode("utf-8"))
    rc, out, err, last = X5._offline(e, CV.CONFORMANCE_VERIFY_OFFLINE_PY,
                                     X5._pins(ck, mk))
    assert rc == 1 and last == "CLASS: INTEGRITY", (rc, last)
    assert "refused:" in out + err
    r = _conf(client, t, ck, mk)
    assert r.json()["verdict"] != "PASS"


# ------------------------------------------------ /v1/verify-dossier


@pytest.mark.parametrize("policy", [PERM, None], ids=["policy", "v1"])
def test_dossier_honest(client, bundle, policy):
    _d, _ck, _mk, texts = bundle
    doc = _dossier(client, texts["manifest.json"], policy).json()
    if policy is None:
        assert doc["signature_ok"] is True, doc
    else:
        assert doc["verdict"] == "ACCEPT", doc


def test_dossier_policy_duplicate_is_reject_by_name(client, bundle):
    _d, _ck, _mk, texts = bundle
    text = _first(texts["manifest.json"], "verdict", "refuted")
    doc = _dossier(client, text).json()
    assert doc["verdict"] == "REJECT", doc
    errs = doc["checks"]["manifest_well_formed"]["errors"]
    assert errs[0].startswith(
        "parse_error: StrictJsonError: manifest_json [js:api.4] refused: "
        "duplicate key 'verdict'"), errs


def test_dossier_policy_nan_is_reject_by_name(client, bundle):
    _d, _ck, _mk, texts = bundle
    text = _first(texts["manifest.json"], "zz", "@@").replace(
        '"@@"', "NaN")
    doc = _dossier(client, text).json()
    assert doc["verdict"] == "REJECT", doc
    errs = doc["checks"]["manifest_well_formed"]["errors"]
    assert "[js:api.4] refused: non-finite number NaN" in errs[0], errs


def test_dossier_v1_duplicate_is_parse_error_by_name(client, bundle):
    _d, _ck, _mk, texts = bundle
    text = _first(texts["manifest.json"], "verdict", "refuted")
    doc = _dossier(client, text, None).json()
    assert doc["signature_ok"] is False, doc
    assert doc["errors"][0].startswith(
        "parse_error: StrictJsonError: manifest_json [js:api.5] refused: "
        "duplicate key 'verdict'"), doc["errors"]


# ------------------------------------------------------ static guard


ARTIFACT_FIELDS = {
    ("VerifyDossierEndpointRequest", "manifest_json"),
    ("VerifyConformanceEndpointRequest", "certificate_json"),
    ("VerifyConformanceEndpointRequest", "trace_json"),
    ("VerifyConformanceEndpointRequest", "manifest_json"),
}
SITES = {"api.1", "api.2", "api.3", "api.4", "api.5"}


def _tree():
    return ast.parse(SERVER.read_text(encoding="utf-8"))


def test_census_of_request_fields_that_carry_an_artifact():
    found = set()
    for n in _tree().body:
        if isinstance(n, ast.ClassDef) and any(
                getattr(b, "id", None) == "BaseModel" for b in n.bases):
            for s in n.body:
                if (isinstance(s, ast.AnnAssign)
                        and isinstance(s.target, ast.Name)
                        and s.target.id.endswith("_json")):
                    found.add((n.name, s.target.id))
    assert found == ARTIFACT_FIELDS


def test_every_artifact_field_is_read_through_the_region():
    tags = []
    for n in ast.walk(_tree()):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "_apis_strict"):
            lab = n.args[1]
            assert isinstance(lab, ast.Constant), ast.dump(lab)
            tags.append(lab.value.split("[js:")[1].rstrip("]"))
    assert sorted(tags) == sorted(SITES), tags


def test_the_helper_imports_the_region_and_keeps_surrogates():
    src = SERVER.read_text(encoding="utf-8")
    fn = [n for n in _tree().body
          if isinstance(n, ast.FunctionDef) and n.name == "_apis_strict"]
    assert len(fn) == 1
    body = ast.get_source_segment(src, fn[0])
    assert "from conformance_verifier import loads" in body
    assert '"surrogatepass"' in body
    assert "def loads(" not in src
