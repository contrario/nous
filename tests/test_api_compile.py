"""Tests for /v1/compile endpoint and NOUS_API_KEYS env scrub.

(1) HX-NOUS-COMPILE-PYC-LEAK fix verification (in-memory compile, stage marker preserved)
(2) HX-NOUS-API-CUSTOMER-CODE-ENV-EXPOSURE mitigation #1 verification (env scrub at import)

# __hx_pyc_leak_fix_v1__
# __hx_pyc_leak_fix_v1_p2__ source uses real production template (sycophancy_guard.nous)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


GOOD_KEY: str = "test_key_pyc_leak_fix"
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
KNOWN_GOOD_TEMPLATE: Path = PROJECT_ROOT / "templates" / "sycophancy_guard.nous"


@pytest.fixture
def clean_source() -> str:
    return KNOWN_GOOD_TEMPLATE.read_text(encoding="utf-8")


@pytest.fixture
def with_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    import nous_api_server
    monkeypatch.setattr(nous_api_server, "API_KEYS", {GOOD_KEY})


@pytest.fixture
def client() -> TestClient:
    from nous_api_server import app
    return TestClient(app)


def test_compile_success_path_returns_python(
    client: TestClient,
    with_keys: None,
    clean_source: str,
) -> None:
    """Valid NOUS source compiles in-memory and returns ok=true with python field."""
    resp = client.post(
        "/v1/compile",
        json={"source": clean_source},
        headers={"X-API-Key": GOOD_KEY},
    )
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    assert body["ok"] is True, body
    assert body["stage"] == "complete"
    assert isinstance(body.get("python"), str) and len(body["python"]) > 0


def test_compile_syntax_error_stage_marker_preserved(
    client: TestClient,
    with_keys: None,
    clean_source: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stage marker 'py_compile' is preserved across migration to in-memory compile.
    Backward-compatible contract for existing API consumers.
    """
    import nous_api_server

    class _BadGen:
        def __init__(self, _program: Any) -> None:
            pass

        def generate(self) -> str:
            return "def f(:\n    return 1\n"

    monkeypatch.setattr(nous_api_server, "NousCodeGen", _BadGen)

    resp = client.post(
        "/v1/compile",
        json={"source": clean_source},
        headers={"X-API-Key": GOOD_KEY},
    )
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    assert body["ok"] is False, body
    assert body["stage"] == "py_compile", body
    error_codes = {e["code"] for e in body.get("errors", [])}
    assert "PY001" in error_codes, body


def test_nous_api_keys_env_scrubbed_at_import() -> None:
    """After `import nous_api`, NOUS_API_KEYS is removed from os.environ.
    Hermetic subprocess test avoids pytest-collection ordering hazards.
    """
    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", ""),
        "NOUS_API_KEYS": "scrub_test_value_should_not_be_visible",
        "PYTHONPATH": str(PROJECT_ROOT),
    }
    script: str = (
        "import nous_api, os, sys\n"
        "sys.stdout.write(os.environ.get('NOUS_API_KEYS', '<SCRUBBED>'))\n"
        "sys.stdout.write('|')\n"
        "sys.stdout.write(','.join(sorted(nous_api.API_KEYS)))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    parts = result.stdout.split("|")
    assert len(parts) == 2, f"unexpected stdout: {result.stdout!r}"
    env_after, api_keys_set = parts
    assert env_after == "<SCRUBBED>", f"NOUS_API_KEYS still in os.environ: {env_after!r}"
    assert "scrub_test_value_should_not_be_visible" in api_keys_set, (
        f"key not loaded into API_KEYS before scrub: {api_keys_set!r}"
    )
