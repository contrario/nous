"""S464 option (A): the skill export's error contract and the global 422.

A client's input answers 422 and logs one WARNING line without a
traceback; a server fault answers 500 SKILLEXPORT500 with an error_id
that the ERROR record also holds; no reply carries a server path, an
exception's own text or a library URL; the writer emits only a SKILL.md
its own reader reads back unchanged; a lone surrogate in any request
body answers 422, not 500.
"""
import io
import json
import logging
import re
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.usefixtures("dated_shipped_prices")

KEY = "test_key_s464_errors"
ROOT = Path(__file__).resolve().parent.parent
NL = chr(10)
SRC = (
    "world MarketMonitor {" + NL
    + "    law cost_ceiling = $3.00 per cycle" + NL
    + "    heartbeat = 20s" + NL
    + "}" + NL
    + "soul Scanner {" + NL
    + "    mind: claude-sonnet-4-6 @ Tier1" + NL
    + "    senses: [http_get]" + NL
    + "    memory { count: int = 0 }" + NL
    + "}" + NL
)
LEAKS = ("/tmp/", "nous_skill_export_", "errors.pydantic.dev", "Traceback",
         "/srv/")
HOSTILE = [
    ("lf", "a" + NL + "b"),
    ("dashes", "x" + NL + "---" + NL + "y"),
    ("fs", "a" + chr(0x1C) + "b"),
    ("nel", "a" + chr(0x85) + "b"),
    ("ls", "a" + chr(0x2028) + "b"),
    ("nonchar", "a" + chr(0xFFFE) + "b"),
    ("nul", "a" + chr(0) + "b"),
    ("del", "a" + chr(0x7F) + "b"),
    ("vt", "a" + chr(0x0B) + "b"),
    ("tab", "a" + chr(9) + "b"),
    ("quotes", "q" + chr(34) + chr(92) + "z"),
    ("bom", "a" + chr(0xFEFF) + "b"),
]


@pytest.fixture
def client(monkeypatch):
    import nous_api_server
    monkeypatch.setattr(nous_api_server, "API_KEYS", {KEY})
    monkeypatch.setattr(nous_api_server.limiter, "enabled", False)
    return TestClient(nous_api_server.app, raise_server_exceptions=False)


def _post(client, **kw):
    body = {"source": SRC, "description": "demo", "with_dossier": False}
    body.update(kw)
    return client.post("/v1/skill/export", headers={"X-API-Key": KEY},
                       json=body)


def _skill_md(resp):
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    name = [n for n in z.namelist() if n.endswith("/SKILL.md")][0]
    return z.read(name).decode("utf-8")


def _frontmatter(text):
    import skill_md
    y, _ = skill_md._split_frontmatter(text, "SKILL.md")
    return skill_md._load_yaml_mapping(y, "SKILL.md", allow_empty=False)


def _records(caplog):
    errs = [r for r in caplog.records if r.levelno >= logging.ERROR]
    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    return errs, warns


def _no_leak(resp):
    for s in LEAKS:
        assert s not in resp.text, (s, resp.text[:300])


CLIENT_CASES = [
    ("parse", {"source": "world {"}),
    ("override", {"tool_overrides": [{"name": "http_get", "bogus": 1}]}),
    ("export", {"source": "soul Scanner {" + NL
                + "    mind: claude-sonnet-4-6 @ Tier1" + NL
                + "    senses: [http_get]" + NL + "}" + NL}),
    ("emit", {"source": SRC.replace("claude-sonnet-4-6", "no-such-model-9"),
              "with_dossier": True}),
    ("name", {"skill_name": "Bad_Name"}),
]


@pytest.mark.parametrize("cid,kw", CLIENT_CASES, ids=[c[0] for c in CLIENT_CASES])
def test_a1_client_errors_are_422_warning_without_traceback(client, caplog,
                                                            cid, kw):
    caplog.set_level(logging.INFO)
    r = _post(client, **kw)
    assert r.status_code == 422, r.text[:300]
    assert r.json()["detail"]["code"] == "SKILLEXPORT001"
    _no_leak(r)
    errs, warns = _records(caplog)
    assert not errs, [e.getMessage()[:200] for e in errs]
    assert warns
    assert all("Traceback" not in w.getMessage() for w in warns)


def _fault_dossier(monkeypatch):
    import dossier_spec

    def boom(skill_dir, **kw):
        raise OSError(28, "No space left on device",
                      str(Path(skill_dir).parent / "_dossier_out"))
    monkeypatch.setattr(dossier_spec, "build_dossier_spec", boom)
    return {"with_dossier": True}


def _fault_export(monkeypatch):
    import skill_export

    def boom(program, req):
        raise RuntimeError("internal fault at /srv/x")
    monkeypatch.setattr(skill_export, "export_skill", boom)
    return {}


@pytest.mark.parametrize("fault", [_fault_dossier, _fault_export],
                         ids=["dossier", "export"])
def test_a2_server_faults_are_500_with_an_id(client, monkeypatch, caplog,
                                             fault):
    kw = fault(monkeypatch)
    caplog.set_level(logging.INFO)
    r = _post(client, **kw)
    assert r.status_code == 500, r.text[:300]
    det = r.json()["detail"]
    assert set(det) == {"error", "code", "error_id"}
    assert det["code"] == "SKILLEXPORT500"
    assert re.fullmatch(r"[0-9a-f]{32}", det["error_id"])
    _no_leak(r)
    assert "No space" not in r.text and "internal fault" not in r.text
    errs, _ = _records(caplog)
    assert len(errs) == 1
    assert "Traceback" in errs[0].getMessage()
    assert det["error_id"] in errs[0].getMessage()


def test_a3_an_http_exception_inside_passes_through(client, monkeypatch):
    import skill_export
    from fastapi import HTTPException

    def teapot(program, req):
        raise HTTPException(status_code=418,
                            detail={"error": "teapot", "code": "T418"})
    monkeypatch.setattr(skill_export, "export_skill", teapot)
    r = _post(client)
    assert r.status_code == 418
    assert r.json()["detail"]["code"] == "T418"


@pytest.mark.parametrize("label,text", HOSTILE, ids=[h[0] for h in HOSTILE])
def test_a4_free_text_reads_back_unchanged(client, label, text):
    for field in ("description", "compatibility", "license"):
        r = _post(client, **{field: text})
        assert r.status_code == 200, (field, r.text[:300])
        fm = _frontmatter(_skill_md(r))
        assert fm[field] == text, (field, fm.get(field))


def test_a5_a_license_cannot_add_a_key(client):
    lic = "MIT" + NL + "allowed-tools: Bash"
    r = _post(client, license=lic)
    assert r.status_code == 200, r.text[:300]
    fm = _frontmatter(_skill_md(r))
    assert fm["license"] == lic
    assert "allowed-tools" not in fm


def test_a5b_a_license_cannot_add_a_key_with_the_dossier(client):
    lic = "MIT" + NL + "allowed-tools: Bash"
    r = _post(client, license=lic, with_dossier=True)
    assert r.status_code == 200, r.text[:300]
    fm = _frontmatter(_skill_md(r))
    assert fm["license"] == lic
    assert "allowed-tools" not in fm


def test_a6_plain_inputs_keep_their_bytes(client):
    r = _post(client, description="Monitors prices: fast # really",
              license="Apache-2.0", compatibility="Python 3.12, git")
    assert r.status_code == 200, r.text[:300]
    md = _skill_md(r)
    assert NL + 'description: "Monitors prices: fast # really"' + NL in md
    assert NL + "license: Apache-2.0" + NL in md
    assert NL + 'compatibility: "Python 3.12, git"' + NL in md


def test_a6b_the_escape_equals_the_old_one_on_ordinary_text():
    import skill_export
    corpus = ["plain", "a: b # c", "q" + chr(34) + chr(92), "  lead",
              chr(0x395) + chr(0x3BB) + chr(0x3BB), "emoji " + chr(0x1F600),
              "nbsp" + chr(0xA0) + "x", "x" * 300]
    for s in corpus:
        old = chr(34) + s.replace(chr(92), chr(92) * 2).replace(
            chr(34), chr(92) + chr(34)) + chr(34)
        assert skill_export._escape_yaml_scalar(s) == old, s


def test_a7_the_check_refuses_a_frontmatter_that_does_not_read_back():
    import skill_export
    want = {"name": "x", "description": "a" + NL + "---" + NL + "b"}
    bad = ("---" + NL + "name: x" + NL + 'description: "a' + NL + "---"
           + NL + 'b"' + NL + "---" + NL + "body" + NL)
    with pytest.raises(skill_export.SkillExportError) as ei:
        skill_export._check_frontmatter_reads_back(bad, want)
    assert "/tmp/" not in str(ei.value)
    good = ("---" + NL + "name: x" + NL + 'description: "a"' + NL + "---"
            + NL + "body" + NL)
    skill_export._check_frontmatter_reads_back(
        good, {"name": "x", "description": "a"})
    with pytest.raises(skill_export.SkillExportError):
        skill_export._check_frontmatter_reads_back(
            good, {"name": "x", "description": "b"})


def test_a8_a_client_text_logs_on_one_line(client, caplog):
    caplog.set_level(logging.INFO)
    r = _post(client, source="world {" + NL + "FORGED LINE")
    assert r.status_code == 422
    _, warns = _records(caplog)
    assert warns
    assert all(NL not in w.getMessage() for w in warns)


def _surrogate_body(field, base):
    body = json.dumps(dict(base, **{field: "SURR"}))
    return body.replace('"SURR"', '"x' + chr(92) + 'ud800"').encode("ascii")


def test_a9_a_lone_surrogate_is_422_on_the_skill_export(client, caplog):
    caplog.set_level(logging.INFO)
    raw = _surrogate_body("description", {"source": SRC})
    r = client.post("/v1/skill/export", content=raw,
                    headers={"X-API-Key": KEY,
                             "content-type": "application/json"})
    assert r.status_code == 422, r.text[:300]
    det = r.json()["detail"]
    assert isinstance(det, list) and det[0]["loc"] == ["body", "description"]
    errs, _ = _records(caplog)
    assert not errs


def test_a9b_a_lone_surrogate_is_422_on_the_public_route(client, caplog):
    caplog.set_level(logging.INFO)
    raw = _surrogate_body("manifest_json", {})
    r = client.post("/v1/verify-dossier", content=raw,
                    headers={"content-type": "application/json"})
    assert r.status_code == 422, r.text[:300]
    errs, _ = _records(caplog)
    assert not errs


def test_a10_an_ordinary_validation_reply_equals_fastapis_own(client):
    from fastapi import FastAPI
    import nous_api_server
    plain = FastAPI()

    @plain.post("/x")
    def _x(body: nous_api_server.SkillExportEndpointRequest):
        return {}
    payloads = [{"source": SRC}, {"source": SRC, "description": ""},
                {"source": SRC, "description": "d", "bogus": 1},
                {"source": 7, "description": "d"}]
    ref = TestClient(plain)
    for p in payloads:
        a = client.post("/v1/skill/export", headers={"X-API-Key": KEY},
                        json=p)
        b = ref.post("/x", json=p)
        assert a.status_code == b.status_code == 422
        assert a.content == b.content, (a.text[:300], b.text[:300])


def test_a11_the_docs_and_the_code_name_skillexport500():
    src = (ROOT / "nous_api_server.py").read_text(encoding="utf-8")
    doc = (ROOT / "docs" / "SKILL_EXPORT.md").read_text(encoding="utf-8")
    assert '"code": "SKILLEXPORT500"' in src
    assert '"code": "SKILLEXPORT500"' in doc
    assert "error_id" in doc
