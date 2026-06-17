from __future__ import annotations

import pathlib
from urllib.parse import urlsplit

from rekor_signing_config import resolve_rekor_endpoint_from_file
from rekor_verify_v2 import KNOWN_REKOR_V2_LOG_KEYS

# __s149_u1b_optin_pin_test_v1__

OPTIN: pathlib.Path = (
    pathlib.Path(__file__).resolve().parent.parent
    / "infra"
    / "sigstore"
    / "signing_config.rekor_v2.json"
)


def test_optin_config_exists() -> None:
    assert OPTIN.is_file()


def test_optin_resolves_to_v2() -> None:
    endpoint = resolve_rekor_endpoint_from_file(OPTIN)
    assert endpoint.major_api_version == 2
    assert endpoint.submit_path == "/api/v2/log/entries"


def test_optin_target_is_a_pinned_verify_log() -> None:
    endpoint = resolve_rekor_endpoint_from_file(OPTIN)
    host = urlsplit(endpoint.base_url).netloc or urlsplit(
        "//" + endpoint.base_url
    ).netloc
    assert host in KNOWN_REKOR_V2_LOG_KEYS


def test_optin_retains_v1_fallback() -> None:
    import json

    raw = json.loads(OPTIN.read_text(encoding="utf-8"))
    versions = {e["majorApiVersion"] for e in raw["rekorTlogUrls"]}
    assert 1 in versions
    assert 2 in versions


def test_pinned_v2_allowlist_non_empty() -> None:
    assert len(KNOWN_REKOR_V2_LOG_KEYS) >= 1
