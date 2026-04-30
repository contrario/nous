"""Tests for PUT /v1/templates/{name} (Session 65 Phase A.2).
# __session65_templates_save_v1__
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


CLEAN_SOURCE = "world Test {\n  mind: anthropic\n}\n"
GOOD_KEY = "test_key_session65"
BAD_KEY = "definitely_not_a_real_key"


@pytest.fixture
def templates_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "templates"
    d.mkdir()
    import nous_api_server
    monkeypatch.setattr(nous_api_server, "TEMPLATES_DIR", d)
    return d


@pytest.fixture
def with_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    import nous_api_server
    monkeypatch.setattr(nous_api_server, "API_KEYS", {GOOD_KEY})


@pytest.fixture
def no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    import nous_api_server
    monkeypatch.setattr(nous_api_server, "API_KEYS", set())


@pytest.fixture
def client() -> TestClient:
    from nous_api_server import app
    return TestClient(app)


def _ok_lint() -> MagicMock:
    report = MagicMock()
    report.has_errors = False
    report.has_warnings = False
    report.to_dict.return_value = {"errors": [], "warnings": []}
    return report


def _err_lint() -> MagicMock:
    report = MagicMock()
    report.has_errors = True
    report.has_warnings = False
    report.to_dict.return_value = {"errors": [{"rule": "X1", "message": "bad"}], "warnings": []}
    return report


def test_save_requires_keys_configured(client: TestClient, templates_dir: Path, no_keys: None) -> None:
    r = client.put("/v1/templates/foo", json={"source": CLEAN_SOURCE}, headers={"X-API-Key": GOOD_KEY})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "AUTH002"


def test_save_requires_key_present(client: TestClient, templates_dir: Path, with_keys: None) -> None:
    r = client.put("/v1/templates/foo", json={"source": CLEAN_SOURCE})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "AUTH003"


def test_save_rejects_invalid_key(client: TestClient, templates_dir: Path, with_keys: None) -> None:
    r = client.put("/v1/templates/foo", json={"source": CLEAN_SOURCE}, headers={"X-API-Key": BAD_KEY})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "AUTH001"


def test_save_clean_source_writes_file(
    client: TestClient, templates_dir: Path, with_keys: None
) -> None:
    with patch("governance_lint.GovernanceLinter") as MockLinter:
        MockLinter.return_value.lint_source.return_value = _ok_lint()
        r = client.put(
            "/v1/templates/alpha",
            json={"source": CLEAN_SOURCE},
            headers={"X-API-Key": GOOD_KEY},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["name"] == "alpha"
    assert body["bytes_written"] == len(CLEAN_SOURCE.encode("utf-8"))
    assert body["sha256"] == hashlib.sha256(CLEAN_SOURCE.encode("utf-8")).hexdigest()
    assert body["backup"] is None
    target = templates_dir / "alpha.nous"
    assert target.exists()
    assert target.read_text() == CLEAN_SOURCE


def test_save_creates_backup_on_overwrite(
    client: TestClient, templates_dir: Path, with_keys: None
) -> None:
    target = templates_dir / "beta.nous"
    target.write_text("// original\n")
    with patch("governance_lint.GovernanceLinter") as MockLinter:
        MockLinter.return_value.lint_source.return_value = _ok_lint()
        r = client.put(
            "/v1/templates/beta",
            json={"source": "// new\n"},
            headers={"X-API-Key": GOOD_KEY},
        )
    body = r.json()
    assert body["ok"] is True
    assert body["backup"] is not None
    assert "beta.nous.bak." in body["backup"]
    assert Path(body["backup"]).read_text() == "// original\n"
    assert target.read_text() == "// new\n"


def test_save_blocks_on_lint_errors(
    client: TestClient, templates_dir: Path, with_keys: None
) -> None:
    with patch("governance_lint.GovernanceLinter") as MockLinter:
        MockLinter.return_value.lint_source.return_value = _err_lint()
        r = client.put(
            "/v1/templates/gamma",
            json={"source": CLEAN_SOURCE},
            headers={"X-API-Key": GOOD_KEY},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["code"] == "TPL001"
    assert body["lint"]["errors"]
    assert not (templates_dir / "gamma.nous").exists()


def test_save_force_overrides_lint(
    client: TestClient, templates_dir: Path, with_keys: None
) -> None:
    with patch("governance_lint.GovernanceLinter") as MockLinter:
        MockLinter.return_value.lint_source.return_value = _err_lint()
        r = client.put(
            "/v1/templates/delta",
            json={"source": CLEAN_SOURCE, "force": True},
            headers={"X-API-Key": GOOD_KEY},
        )
    body = r.json()
    assert body["ok"] is True
    assert (templates_dir / "delta.nous").exists()
    assert body["lint"]["errors"]


def test_save_invalid_name_chars(
    client: TestClient, templates_dir: Path, with_keys: None
) -> None:
    with patch("governance_lint.GovernanceLinter") as MockLinter:
        MockLinter.return_value.lint_source.return_value = _ok_lint()
        # FastAPI URL-decodes the path; "..%2Fetc" becomes "../etc" but
        # cannot match the {name} single-segment route -> 404. We test
        # explicit invalid-but-single-segment chars instead.
        r = client.put(
            "/v1/templates/has.dot",
            json={"source": CLEAN_SOURCE},
            headers={"X-API-Key": GOOD_KEY},
        )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "TPL004"


def test_save_invalid_name_dot_prefix(
    client: TestClient, templates_dir: Path, with_keys: None
) -> None:
    with patch("governance_lint.GovernanceLinter") as MockLinter:
        MockLinter.return_value.lint_source.return_value = _ok_lint()
        r = client.put(
            "/v1/templates/.hidden",
            json={"source": CLEAN_SOURCE},
            headers={"X-API-Key": GOOD_KEY},
        )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "TPL004"


def test_save_too_long_name(
    client: TestClient, templates_dir: Path, with_keys: None
) -> None:
    with patch("governance_lint.GovernanceLinter") as MockLinter:
        MockLinter.return_value.lint_source.return_value = _ok_lint()
        long_name = "a" * 65
        r = client.put(
            f"/v1/templates/{long_name}",
            json={"source": CLEAN_SOURCE},
            headers={"X-API-Key": GOOD_KEY},
        )
    assert r.status_code == 403


def test_save_prunes_old_backups(
    client: TestClient, templates_dir: Path, with_keys: None
) -> None:
    with patch("governance_lint.GovernanceLinter") as MockLinter:
        MockLinter.return_value.lint_source.return_value = _ok_lint()
        for i in range(7):
            r = client.put(
                "/v1/templates/epsilon",
                json={"source": f"// rev {i}\n"},
                headers={"X-API-Key": GOOD_KEY},
            )
            assert r.json()["ok"] is True
    backups = sorted(templates_dir.glob("epsilon.nous.bak.*"))
    assert len(backups) == 5, [b.name for b in backups]


def test_save_lint_unavailable_does_not_block(
    client: TestClient, templates_dir: Path, with_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If governance_lint is missing, save proceeds (no gate)."""
    import builtins
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "governance_lint":
            raise ImportError("simulated missing module")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    r = client.put(
        "/v1/templates/zeta",
        json={"source": CLEAN_SOURCE},
        headers={"X-API-Key": GOOD_KEY},
    )
    body = r.json()
    assert body["ok"] is True
    assert body["lint"] is None
    assert (templates_dir / "zeta.nous").exists()


def test_save_lint_crash_blocks_without_force(
    client: TestClient, templates_dir: Path, with_keys: None
) -> None:
    """If linter crashes, treat as has_errors=True. force=true overrides."""
    with patch("governance_lint.GovernanceLinter") as MockLinter:
        MockLinter.return_value.lint_source.side_effect = RuntimeError("parse explosion")
        r = client.put(
            "/v1/templates/eta",
            json={"source": CLEAN_SOURCE},
            headers={"X-API-Key": GOOD_KEY},
        )
    body = r.json()
    assert body["ok"] is False
    assert body["lint"]["crashed"] is True
    assert not (templates_dir / "eta.nous").exists()
