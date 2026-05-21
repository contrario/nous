"""rekor_signing_config.py -- Sigstore SigningConfig v0.2 loader + Rekor
tlog endpoint selector.

NOUS S86 Rekor v2 P2 (read/selection groundwork). This module makes the
Sigstore SigningConfig (mediaType
application/vnd.dev.sigstore.signingconfig.v0.2+json) the single source
of truth for which Rekor transparency-log endpoint NOUS submits to,
removing the hardcoded REKOR_* URL/path assumptions in rekor_anchor.py.

Per the Rekor v2 client specification
(github.com/sigstore/rekor-tiles/blob/main/CLIENTS.md):
  - The v2 instance URL MUST NOT be hardcoded; it is rotated and the
    previous instance frozen. Read it from the SigningConfig.
  - Clients select the rekorTlogUrl with the HIGHEST major API version
    they support, grouping by operator and selecting at most one per
    operator.
  - Clients MUST gracefully fail (typed error, fail closed) when only a
    higher-than-supported API version is available, rather than silently
    treating a v2 entry/endpoint as v1.

NOUS supports Rekor API v1 only today (MAX_SUPPORTED_REKOR_API_VERSION).
Raising support to v2 is a deliberate future change paired with the v2
verifier (tiles / inclusion-proof / checkpoint), not an accidental
silent upgrade.

This module performs NO network I/O and NO cryptography. It parses
config and selects an endpoint. Submission and offline verification stay
in rekor_anchor.py.

# __session86_rekor_signing_config_module_v1__
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

MAX_SUPPORTED_REKOR_API_VERSION: int = 1

SIGNING_CONFIG_MEDIA_TYPE_V0_2: str = (
    "application/vnd.dev.sigstore.signingconfig.v0.2+json"
)

REKOR_V1_SUBMIT_PATH: str = "/api/v1/log/entries"
REKOR_V1_PUBKEY_PATH: str = "/api/v1/log/publicKey"
REKOR_V2_ENTRIES_PATH: str = "/api/v2/log/entries"


class SigningConfigError(ValueError):
    """SigningConfig is malformed, unsupported, or selects no endpoint."""


class RekorApiVersionUnsupported(SigningConfigError):
    """Only tlog endpoints above MAX_SUPPORTED_REKOR_API_VERSION exist.

    Fail-closed: the client refuses to submit rather than mis-handle a
    higher-version endpoint as v1.
    """


class RekorTlogEndpoint(BaseModel):
    """One entry from SigningConfig.rekorTlogUrls."""

    model_config = ConfigDict(strict=True, extra="ignore", frozen=True)
    url: str = Field(min_length=1)
    major_api_version: int = Field(ge=1)
    valid_for_start: datetime
    valid_for_end: Optional[datetime] = None
    operator: str = Field(min_length=1)


class ResolvedRekorEndpoint(BaseModel):
    """The selected endpoint plus the request paths for its API version."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    base_url: str = Field(min_length=1)
    major_api_version: int = Field(ge=1)
    operator: str = Field(min_length=1)
    submit_path: str = Field(min_length=1)
    pubkey_path: Optional[str] = None


def _parse_rfc3339(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_signing_config(raw: dict[str, object]) -> list[RekorTlogEndpoint]:
    """Extract and validate rekorTlogUrls from a parsed SigningConfig.

    Tolerant of the exact v0.2 mediaType but does not require it (other
    Sigstore-compatible configs share the rekorTlogUrls shape). Raises
    SigningConfigError on a structurally invalid config.
    """
    media_type = raw.get("mediaType")
    if media_type is not None and not isinstance(media_type, str):
        raise SigningConfigError("mediaType is present but not a string")

    tlog_urls = raw.get("rekorTlogUrls")
    if not isinstance(tlog_urls, list) or not tlog_urls:
        raise SigningConfigError(
            "rekorTlogUrls missing, not a list, or empty"
        )

    endpoints: list[RekorTlogEndpoint] = []
    for idx, item in enumerate(tlog_urls):
        if not isinstance(item, dict):
            raise SigningConfigError(
                f"rekorTlogUrls[{idx}] is not an object"
            )
        url = item.get("url")
        major = item.get("majorApiVersion")
        operator = item.get("operator")
        valid_for = item.get("validFor")
        if not isinstance(url, str) or not url:
            raise SigningConfigError(
                f"rekorTlogUrls[{idx}].url missing or not a string"
            )
        if not isinstance(major, int) or isinstance(major, bool):
            raise SigningConfigError(
                f"rekorTlogUrls[{idx}].majorApiVersion missing or not an int"
            )
        if not isinstance(operator, str) or not operator:
            raise SigningConfigError(
                f"rekorTlogUrls[{idx}].operator missing or not a string"
            )
        if not isinstance(valid_for, dict):
            raise SigningConfigError(
                f"rekorTlogUrls[{idx}].validFor missing or not an object"
            )
        start_raw = valid_for.get("start")
        if not isinstance(start_raw, str) or not start_raw:
            raise SigningConfigError(
                f"rekorTlogUrls[{idx}].validFor.start missing"
            )
        try:
            start = _parse_rfc3339(start_raw)
        except ValueError as exc:
            raise SigningConfigError(
                f"rekorTlogUrls[{idx}].validFor.start not RFC3339: {exc}"
            ) from exc
        end: Optional[datetime] = None
        end_raw = valid_for.get("end")
        if end_raw is not None:
            if not isinstance(end_raw, str) or not end_raw:
                raise SigningConfigError(
                    f"rekorTlogUrls[{idx}].validFor.end present but invalid"
                )
            try:
                end = _parse_rfc3339(end_raw)
            except ValueError as exc:
                raise SigningConfigError(
                    f"rekorTlogUrls[{idx}].validFor.end not RFC3339: {exc}"
                ) from exc
        endpoints.append(
            RekorTlogEndpoint(
                url=url.rstrip("/"),
                major_api_version=major,
                valid_for_start=start,
                valid_for_end=end,
                operator=operator,
            )
        )
    return endpoints


def load_signing_config(path: Path) -> list[RekorTlogEndpoint]:
    """Load and parse a SigningConfig JSON file from disk."""
    if not path.exists():
        raise SigningConfigError(f"signing config not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SigningConfigError(
            f"signing config is not valid JSON: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise SigningConfigError("signing config top level is not an object")
    return parse_signing_config(raw)


def _paths_for_version(major: int) -> tuple[str, Optional[str]]:
    if major == 1:
        return REKOR_V1_SUBMIT_PATH, REKOR_V1_PUBKEY_PATH
    if major == 2:
        return REKOR_V2_ENTRIES_PATH, None
    raise SigningConfigError(f"no known request paths for API version {major}")


def select_rekor_tlog(
    endpoints: list[RekorTlogEndpoint],
    max_supported_version: int = MAX_SUPPORTED_REKOR_API_VERSION,
    now: Optional[datetime] = None,
) -> ResolvedRekorEndpoint:
    """Select the Rekor tlog endpoint to submit to.

    Spec rule (rekor-tiles CLIENTS.md): pick the highest major API
    version the client supports; group by operator and select at most
    one per operator; honor validFor windows.

    Fail closed: if the config lists tlog endpoints but every one
    requires an API version above max_supported_version (e.g. a
    v2-only production rollout), raise RekorApiVersionUnsupported rather
    than silently downgrading or mis-parsing.
    """
    if not endpoints:
        raise SigningConfigError("no rekor tlog endpoints to select from")

    if now is None:
        now = datetime.now(timezone.utc)

    active = [
        e for e in endpoints
        if e.valid_for_start <= now
        and (e.valid_for_end is None or e.valid_for_end > now)
    ]
    if not active:
        raise SigningConfigError(
            "no rekor tlog endpoint is currently within its validFor window"
        )

    highest_available = max(e.major_api_version for e in active)
    supported = [
        e for e in active
        if e.major_api_version <= max_supported_version
    ]
    if not supported:
        raise RekorApiVersionUnsupported(
            "all active rekor tlog endpoints require API version "
            f"{highest_available} > client max {max_supported_version}; "
            "refusing to submit (fail closed)"
        )

    best_version = max(e.major_api_version for e in supported)
    candidates = [e for e in supported if e.major_api_version == best_version]
    # at most one per operator: deterministic tie-break by latest start
    candidates.sort(key=lambda e: e.valid_for_start, reverse=True)
    chosen = candidates[0]

    submit_path, pubkey_path = _paths_for_version(chosen.major_api_version)
    return ResolvedRekorEndpoint(
        base_url=chosen.url,
        major_api_version=chosen.major_api_version,
        operator=chosen.operator,
        submit_path=submit_path,
        pubkey_path=pubkey_path,
    )


def resolve_rekor_endpoint_from_file(
    path: Path,
    max_supported_version: int = MAX_SUPPORTED_REKOR_API_VERSION,
    now: Optional[datetime] = None,
) -> ResolvedRekorEndpoint:
    """Convenience: load a SigningConfig file and select an endpoint."""
    return select_rekor_tlog(
        load_signing_config(path),
        max_supported_version=max_supported_version,
        now=now,
    )
