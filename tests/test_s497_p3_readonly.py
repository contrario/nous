"""S497 phase 3: the API runs with its code read-only.

BudgetGuard persists where NOUS_BUDGET_FILE says (A sets it to the state
dir) and says so, once, when it cannot persist; PUT /v1/templates
refuses with TPL006 when the templates dir is not writable, before any
backup or write."""
import json
import logging
import os
from pathlib import Path

import pytest

import nous_runtime

KEY = "test_key_s497_p3"


def test_t1_budget_file_from_env(tmp_path, monkeypatch):
    p = tmp_path / "state" / "budget.json"
    p.parent.mkdir()
    monkeypatch.setenv("NOUS_BUDGET_FILE", str(p))
    g = nous_runtime.BudgetGuard()
    g.record(0.5)
    assert json.loads(p.read_text())["today_spend"] == 0.5


def test_t2_budget_default_path_unchanged(monkeypatch):
    monkeypatch.delenv("NOUS_BUDGET_FILE", raising=False)
    g = nous_runtime.BudgetGuard()
    assert g._log_path == Path("/opt/aetherlang_agents/nous/runtime_budget.json")


def test_t3_failed_save_warns_once(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("NOUS_BUDGET_FILE", str(tmp_path / "absent_dir" / "b.json"))
    caplog.set_level(logging.WARNING, logger="nous.runtime")
    g = nous_runtime.BudgetGuard()
    g.record(0.1)
    g.record(0.1)
    hits = [r for r in caplog.records if r.name == "nous.runtime"
            and "could not persist" in r.getMessage()]
    assert len(hits) == 1


def _app(monkeypatch, tdir):
    pytest.importorskip("fastapi")
    pytest.importorskip("slowapi")
    import nous_api_server as s
    monkeypatch.setattr(s, "API_KEYS", {KEY})
    monkeypatch.setattr(s, "TEMPLATES_DIR", tdir)
    monkeypatch.setattr(s.limiter, "enabled", False)
    from fastapi.testclient import TestClient
    return TestClient(s.app, raise_server_exceptions=False)


SRC = "world W {\n    heartbeat = 5m\n}\n"


def test_t4_templates_read_only_refused(tmp_path, monkeypatch):
    tdir = tmp_path / "templates"
    tdir.mkdir()
    (tdir / "w.nous").write_text("old\n")
    real = os.access

    def access(p, mode, *a, **k):
        if Path(p).resolve() == tdir.resolve() and mode & os.W_OK:
            return False
        return real(p, mode, *a, **k)

    monkeypatch.setattr(os, "access", access)
    c = _app(monkeypatch, tdir)
    r = c.put("/v1/templates/w", headers={"X-API-Key": KEY},
              json={"source": SRC, "force": True})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "TPL006"
    assert sorted(x.name for x in tdir.iterdir()) == ["w.nous"]
    assert (tdir / "w.nous").read_text() == "old\n"


def test_t5_templates_writable_saves(tmp_path, monkeypatch):
    tdir = tmp_path / "templates"
    tdir.mkdir()
    c = _app(monkeypatch, tdir)
    r = c.put("/v1/templates/w", headers={"X-API-Key": KEY},
              json={"source": SRC, "force": True})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert (tdir / "w.nous").read_text() == SRC
