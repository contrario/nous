from __future__ import annotations

import json
import pathlib

import pytest

MIRROR: pathlib.Path = (
    pathlib.Path(__file__).resolve().parent.parent
    / "infra"
    / "sigstore"
    / "signing_config.json"
)
EXPECTED_MEDIA_PREFIX: str = "application/vnd.dev.sigstore.signingconfig.v0.2"


@pytest.fixture(scope="module")
def config() -> dict:
    with open(MIRROR, "rb") as fh:
        return json.loads(fh.read())


def test_mirror_file_exists() -> None:
    assert MIRROR.is_file()


def test_media_type(config: dict) -> None:
    assert config["mediaType"].startswith(EXPECTED_MEDIA_PREFIX)


def test_rekor_tlog_urls_non_empty(config: dict) -> None:
    urls = config["rekorTlogUrls"]
    assert isinstance(urls, list)
    assert len(urls) >= 1


def test_rekor_entries_have_required_keys(config: dict) -> None:
    for entry in config["rekorTlogUrls"]:
        assert "url" in entry
        assert "majorApiVersion" in entry
        assert "validFor" in entry


def test_v1_url_present(config: dict) -> None:
    versions = {e["majorApiVersion"] for e in config["rekorTlogUrls"]}
    assert 1 in versions


def test_ca_and_tsa_present(config: dict) -> None:
    assert config["caUrls"]
    assert config["tsaUrls"]
