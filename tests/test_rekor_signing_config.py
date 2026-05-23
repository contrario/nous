"""test_rekor_signing_config.py

S86 Rekor v2 P2 -- SigningConfig v0.2 loader + tlog endpoint selector.
Covers spec-compliant selection (highest supported API version), fail-
closed on v2-only, validFor windowing, malformed configs, and parsing
the real mirrored infra/sigstore/signing_config.json.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rekor_signing_config import (  # noqa: E402
    MAX_SUPPORTED_REKOR_API_VERSION,
    RekorApiVersionUnsupported,
    SigningConfigError,
    load_signing_config,
    parse_signing_config,
    select_rekor_tlog,
)

MIRRORED_CONFIG = ROOT / "infra" / "sigstore" / "signing_config.json"

_V1 = {
    "url": "https://rekor.sigstore.dev",
    "majorApiVersion": 1,
    "validFor": {"start": "2021-01-12T11:53:27.000Z"},
    "operator": "sigstore.dev",
}
_V2 = {
    "url": "https://log2025-1.rekor.sigstore.dev",
    "majorApiVersion": 2,
    "validFor": {"start": "2025-10-06T00:00:00Z"},
    "operator": "sigstore.dev",
}


def _sel(cfg: dict[str, object], **kw: object):
    return select_rekor_tlog(parse_signing_config(cfg), **kw)  # type: ignore[arg-type]


class TestSelection:
    def test_v1_only_selects_v1(self) -> None:
        r = _sel({"rekorTlogUrls": [_V1]})
        assert r.major_api_version == 1
        assert r.submit_path == "/api/v1/log/entries"
        assert r.pubkey_path == "/api/v1/log/publicKey"
        assert r.base_url == "https://rekor.sigstore.dev"

    def test_v2_present_client_max_1_selects_v1(self) -> None:
        r = _sel({"rekorTlogUrls": [_V2, _V1]}, max_supported_version=1)
        assert r.major_api_version == 1
        assert r.base_url == "https://rekor.sigstore.dev"

    def test_v2_only_fails_closed(self) -> None:
        with pytest.raises(RekorApiVersionUnsupported):
            _sel({"rekorTlogUrls": [_V2]}, max_supported_version=1)

    def test_default_client_max_selects_v2(self) -> None:
        # __nous_s91_default_max_v2_test_v1__
        r = _sel({"rekorTlogUrls": [_V2, _V1]})
        assert r.major_api_version == 2
        assert r.submit_path == "/api/v2/log/entries"
        assert r.base_url == "https://log2025-1.rekor.sigstore.dev"

    def test_future_client_max_2_selects_v2(self) -> None:
        r = _sel({"rekorTlogUrls": [_V2, _V1]}, max_supported_version=2)
        assert r.major_api_version == 2
        assert r.submit_path == "/api/v2/log/entries"
        assert r.base_url == "https://log2025-1.rekor.sigstore.dev"

    def test_url_trailing_slash_stripped(self) -> None:
        cfg = {"rekorTlogUrls": [dict(_V1, url="https://rekor.sigstore.dev/")]}
        r = _sel(cfg)
        assert r.base_url == "https://rekor.sigstore.dev"


class TestValidForWindow:
    def test_not_yet_active_excluded(self) -> None:
        future = dict(_V1, validFor={"start": "2099-01-01T00:00:00Z"})
        with pytest.raises(SigningConfigError):
            _sel({"rekorTlogUrls": [future]})

    def test_ended_endpoint_excluded(self) -> None:
        ended = dict(
            _V1,
            validFor={"start": "2020-01-01T00:00:00Z", "end": "2021-01-01T00:00:00Z"},
        )
        with pytest.raises(SigningConfigError):
            _sel({"rekorTlogUrls": [ended]})

    def test_now_override_respected(self) -> None:
        r = _sel(
            {"rekorTlogUrls": [_V1]},
            now=datetime(2022, 1, 1, tzinfo=timezone.utc),
        )
        assert r.major_api_version == 1


class TestMalformed:
    def test_empty_tlog_list_raises(self) -> None:
        with pytest.raises(SigningConfigError):
            parse_signing_config({"rekorTlogUrls": []})

    def test_missing_tlog_key_raises(self) -> None:
        with pytest.raises(SigningConfigError):
            parse_signing_config({"mediaType": "x"})

    def test_missing_url_raises(self) -> None:
        bad = {"majorApiVersion": 1, "validFor": {"start": "2021-01-12T11:53:27Z"},
               "operator": "sigstore.dev"}
        with pytest.raises(SigningConfigError):
            parse_signing_config({"rekorTlogUrls": [bad]})

    def test_bool_majorapiversion_rejected(self) -> None:
        bad = dict(_V1, majorApiVersion=True)
        with pytest.raises(SigningConfigError):
            parse_signing_config({"rekorTlogUrls": [bad]})

    def test_non_rfc3339_start_raises(self) -> None:
        bad = dict(_V1, validFor={"start": "not-a-date"})
        with pytest.raises(SigningConfigError):
            parse_signing_config({"rekorTlogUrls": [bad]})


class TestMirroredConfigFile:
    def test_mirrored_file_parses_and_selects_v1(self) -> None:
        if not MIRRORED_CONFIG.exists():
            pytest.skip("mirrored signing_config.json not present")
        endpoints = load_signing_config(MIRRORED_CONFIG)
        assert endpoints
        r = select_rekor_tlog(endpoints)
        assert r.major_api_version <= MAX_SUPPORTED_REKOR_API_VERSION
        assert r.submit_path.startswith("/api/v")
