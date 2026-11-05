"""S7b, the API's writer refusal (seat S457): POST /v1/skill/export
answers a refusal by a guarded writer with HTTP 422 and its own code,
STRICT_JSON_REFUSED, "REFUSED: <reason>", logged at WARNING without a
traceback; every other refusal keeps SKILLEXPORT001.

T2's cases are found at run time: a recorder on every guarded module's
_s7b_loads lists the guards the request crosses, then a failpoint is
set at each of them in turn. T1 pins that list, so a new guard on this
path is covered by T2 and shows in T1. Every key is ephemeral, made by
the endpoint inside its own temp dir. Predictions:
API_PREDICTIONS.txt (seat S457). These tests evidence the contract on
this path; they do not prove it for other inputs.
# __s7b_api_refusal_tests_v1__
"""
from __future__ import annotations

import importlib
import logging
import os
import re
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conformance_verifier import StrictJsonError

pytestmark = pytest.mark.usefixtures("dated_shipped_prices")

KEY = "test_key_s7b_api"
ROOT = Path(__file__).resolve().parent.parent
SRC = """world MarketMonitor {
    law cost_ceiling = $3.00 per cycle
    heartbeat = 20s
}
soul Scanner {
    mind: claude-sonnet-4-6 @ Tier1
    senses: [http_get]
    memory { count: int = 0 }
}
"""
GUARDED = ("annex_iv_map", "attest_apr", "build_vsa", "cli_verify",
           "conformance", "continuity_checkpoint", "continuity_ledger",
           "dossier", "dossier_spec", "guardrails_adapter",
           "llm_guard_adapter", "manifest", "ndec", "nous_trace",
           "provenance", "run_identity", "verifier_registry", "vsa")


@pytest.fixture
def client(monkeypatch):
    import nous_api_server
    monkeypatch.setattr(nous_api_server, "API_KEYS", {KEY})
    # the route is rate-limited per process; these tests must not spend
    # the budget of the files that run after them
    monkeypatch.setattr(nous_api_server.limiter, "enabled", False)
    return TestClient(nous_api_server.app)


def _recorder(monkeypatch, fail=None):
    seen, count = [], {}
    for name in GUARDED:
        mod = importlib.import_module(name)
        real = getattr(mod, "_s7b_loads", None)
        if real is None:
            continue

        def wrap(raw, lab, _real=real):
            m = re.search(r"\[js:([^\]]+)\]", lab)
            code = m.group(1) if m else lab
            count[code] = count.get(code, 0) + 1
            seen.append(code)
            if fail is not None and fail == (code, count[code]):
                raise StrictJsonError(lab + ": failpoint")
            return _real(raw, lab)
        monkeypatch.setattr(mod, "_s7b_loads", wrap)
    return seen


def _export(client, with_dossier=True, source=SRC):
    return client.post("/v1/skill/export", headers={"X-API-Key": KEY},
                       json={"source": source, "description": "demo",
                             "with_dossier": with_dossier})


def _discover(client, monkeypatch):
    with monkeypatch.context() as mp:
        seen = _recorder(mp)
        r = _export(client)
    assert r.status_code == 200, r.text[:300]
    return list(seen)


def _temp_dirs():
    return {n for n in os.listdir(tempfile.gettempdir())
            if n.startswith("nous_skill_export_")}


def test_t1_the_dossier_export_crosses_these_guards(client, monkeypatch):
    assert _discover(client, monkeypatch) == ["w.cf.2", "w.man.1"]


def test_t2_each_crossed_guard_refuses_with_its_code(client, monkeypatch,
                                                     caplog):
    seen = _discover(client, monkeypatch)
    assert seen, "the export crossed no guard"
    k = {}
    for code in seen:
        k[code] = k.get(code, 0) + 1
        before = _temp_dirs()
        caplog.clear()
        caplog.set_level(logging.INFO)
        with monkeypatch.context() as mp:
            _recorder(mp, fail=(code, k[code]))
            r = _export(client)
        assert r.status_code == 422, (code, r.status_code, r.text[:300])
        det = r.json()["detail"]
        assert det["code"] == "STRICT_JSON_REFUSED", (code, det)
        assert det["error"].startswith("REFUSED: "), det
        assert "[js:" + code + "]" in det["error"], det
        assert tempfile.gettempdir() not in det["error"], det
        assert _temp_dirs() <= before, "a temp dir was left"
        errs = [x for x in caplog.records if x.levelno >= logging.ERROR]
        assert not errs, [x.getMessage()[:200] for x in errs]
        warns = [x for x in caplog.records if x.levelno == logging.WARNING
                 and "[js:" + code + "]" in x.getMessage()]
        assert warns, "no WARNING naming the guard"
        assert all("Traceback" not in x.getMessage() for x in warns)


def test_t3_other_refusals_keep_skillexport001(client):
    r = _export(client, source="world {")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "SKILLEXPORT001"


def test_t4_without_a_dossier_no_guard_is_crossed(client, monkeypatch):
    seen = _recorder(monkeypatch)
    r = _export(client, with_dossier=False)
    assert r.status_code == 200
    assert seen == []


def test_t5_the_docs_name_both_codes():
    src = (ROOT / "nous_api_server.py").read_text(encoding="utf-8")
    doc = (ROOT / "docs" / "SKILL_EXPORT.md").read_text(encoding="utf-8")
    assert '"code": "STRICT_JSON_REFUSED"' in src
    assert '"code": "STRICT_JSON_REFUSED"' in doc
    assert '"code": "SKILLEXPORT001"' in doc
