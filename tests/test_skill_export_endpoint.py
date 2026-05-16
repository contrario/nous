"""
tests/test_skill_export_endpoint.py

Coverage for POST /v1/skill/export. Uses FastAPI TestClient, no
network. Tests are real end-to-end through SMT (Z3) and Ed25519
signing, since these are local libraries and run in milliseconds.

# __session77_test_skill_export_endpoint_v1__
# __session77_B09_fix_auth_test_applied_v1__
"""
from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

GOOD_KEY: str = "test_key_skill_export"

SIMPLE_NOUS: str = """world MarketMonitor {
    law cost_ceiling = $3.00 per cycle
    heartbeat = 20s
}
soul Scanner {
    mind: claude-sonnet-4-6 @ Tier1
    senses: [http_get]
    memory { count: int = 0 }
}
"""


@pytest.fixture
def with_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    import nous_api_server
    monkeypatch.setattr(nous_api_server, "API_KEYS", {GOOD_KEY})


@pytest.fixture
def client(with_keys: None) -> TestClient:
    from nous_api_server import app
    return TestClient(app)


def test_endpoint_rejects_wrong_api_key(client: TestClient) -> None:
    """Wrong key -> 401. Empty header is 'anonymous' bypass, not
    a rejection; that is the intended require_api_key() shape.
    """
    resp = client.post(
        "/v1/skill/export",
        headers={"X-API-Key": "this-key-is-wrong"},
        json={"source": SIMPLE_NOUS, "description": "demo"},
    )
    assert resp.status_code == 401


def test_endpoint_returns_zip_with_dossier(client: TestClient) -> None:
    resp = client.post(
        "/v1/skill/export",
        headers={"X-API-Key": GOOD_KEY},
        json={
            "source": SIMPLE_NOUS,
            "description": "Demo export",
            "with_dossier": True,
        },
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    names = z.namelist()
    assert "market-monitor/SKILL.md" in names
    assert "market-monitor/nous.yaml" in names
    assert "market-monitor/dossier/source.nous" in names
    assert "market-monitor/dossier/manifest.json" in names
    assert "market-monitor/dossier/public_key.b64" in names
    assert "market-monitor/dossier/verify_offline.py" in names


def test_endpoint_returns_zip_without_dossier(client: TestClient) -> None:
    resp = client.post(
        "/v1/skill/export",
        headers={"X-API-Key": GOOD_KEY},
        json={
            "source": SIMPLE_NOUS,
            "description": "Demo export",
            "with_dossier": False,
        },
    )
    assert resp.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    names = z.namelist()
    assert "market-monitor/SKILL.md" in names
    assert "market-monitor/nous.yaml" in names
    assert not any("/dossier/" in n for n in names)


def test_endpoint_content_disposition_header(client: TestClient) -> None:
    resp = client.post(
        "/v1/skill/export",
        headers={"X-API-Key": GOOD_KEY},
        json={"source": SIMPLE_NOUS, "description": "x"},
    )
    assert resp.status_code == 200
    cd = resp.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert "market-monitor.zip" in cd


def test_endpoint_x_skill_name_header(client: TestClient) -> None:
    resp = client.post(
        "/v1/skill/export",
        headers={"X-API-Key": GOOD_KEY},
        json={"source": SIMPLE_NOUS, "description": "x"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("x-skill-name") == "market-monitor"


def test_endpoint_skill_name_override(client: TestClient) -> None:
    resp = client.post(
        "/v1/skill/export",
        headers={"X-API-Key": GOOD_KEY},
        json={
            "source": SIMPLE_NOUS,
            "description": "x",
            "skill_name": "my-custom-name",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("x-skill-name") == "my-custom-name"


def test_endpoint_invalid_source_returns_422(client: TestClient) -> None:
    resp = client.post(
        "/v1/skill/export",
        headers={"X-API-Key": GOOD_KEY},
        json={"source": "this is not valid nous", "description": "x"},
    )
    assert resp.status_code == 422


def test_endpoint_empty_description_rejected(client: TestClient) -> None:
    resp = client.post(
        "/v1/skill/export",
        headers={"X-API-Key": GOOD_KEY},
        json={"source": SIMPLE_NOUS, "description": ""},
    )
    assert resp.status_code == 422


def test_endpoint_no_cost_law_returns_422(client: TestClient) -> None:
    no_cost = (
        "world X {\n    heartbeat = 20s\n}\n"
        "soul S {\n    mind: m @ Tier1\n    senses: [t]\n}\n"
    )
    resp = client.post(
        "/v1/skill/export",
        headers={"X-API-Key": GOOD_KEY},
        json={"source": no_cost, "description": "x"},
    )
    assert resp.status_code == 422


def test_endpoint_dossier_verifies_offline(
    client: TestClient, tmp_path: Path
) -> None:
    """End-to-end: ZIP -> extract -> run verify_offline.py -> PASS.

    Confirms the Ed25519 signature chain holds across the API boundary.
    """
    import subprocess
    import sys
    resp = client.post(
        "/v1/skill/export",
        headers={"X-API-Key": GOOD_KEY},
        json={
            "source": SIMPLE_NOUS,
            "description": "End-to-end verifier test",
        },
    )
    assert resp.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    z.extractall(tmp_path)
    dossier = tmp_path / "market-monitor" / "dossier"
    assert (dossier / "verify_offline.py").is_file()
    result = subprocess.run(
        [sys.executable, "verify_offline.py"],
        cwd=str(dossier),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "VERDICT: PASS" in result.stdout
    assert "Ed25519 signature verified" in result.stdout


def test_endpoint_tool_overrides_applied(client: TestClient) -> None:
    resp = client.post(
        "/v1/skill/export",
        headers={"X-API-Key": GOOD_KEY},
        json={
            "source": SIMPLE_NOUS,
            "description": "x",
            "tool_overrides": [
                {
                    "name": "http_get",
                    "max_calls": 3,
                    "input_tokens": 100,
                    "output_tokens": 50,
                }
            ],
            "with_dossier": False,
        },
    )
    assert resp.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    yaml_text = z.read("market-monitor/nous.yaml").decode("utf-8")
    assert "max_calls: 3" in yaml_text
    assert "input_tokens: 100" in yaml_text
    assert "output_tokens: 50" in yaml_text
