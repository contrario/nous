from __future__ import annotations

import re
from pathlib import Path

import pytest

import continuity_verifier

ROOT: Path = Path(__file__).resolve().parent.parent
_WS: re.Pattern[str] = re.compile(r"\s+")
_LABEL: re.Pattern[str] = re.compile(r"PROVES(?:-[a-z]+)?(?=:| \()")

# __s377b_reserved_verb_wheel_v1__
# D376-8 for patch B: the decoded continuity verifier and every corrected
# string in the wheel, the ledger doc and the CHANGELOG, named by id in
# S376_PROVE_CLASSIFICATION.tsv.

OVERCLAIMS: tuple[tuple[str, str, str], ...] = (
    ('o0077', 'annex_iv_map.py', 'WHAT THE SIDECAR PROVES'),
    ('o0079', 'annex_iv_map.py', 'BOUNDARY: proves presence + authenticity + indexing'),
    ('o0081', 'annex_iv_map.py', 'boundary: proves presence + authenticity + indexing;'),
    ('o0103', 'cli_conformance.py', 'Runtime conformance: prove a signed execution trace stayed'),
    ('o0104', 'cli_dossier.py', 'it proves presence + authenticity +'),
    ('o0137', 'cli_verify_release.py', 'the digest the log proves inclusion of'),
    ('o0155', 'conformance_verifier.py', 'SCOPE: this proves the signed verdict'),
    ('o0661', 'envelope.py', 'NOUS PROVES (set ops over root-committed canon fields)'),
    ('o0662+o0663', 'envelope.py', '(verified separately by the dossier) proves current descends'),
    ('o0732', 'rekor_anchor.py', 'the Rekor anchor proves only'),
    ('o0736', 'remedy_proof.py', 'offline verifier, proves only two things'),
    ('o0765', 'signerctl.py', 'check later proves EQUAL'),
    ('o0834', 'trace_anchor.py', 'a third party can prove the trace existed'),
    ('o0842', 'trace_bridge.py', 'obligations.json VERBATIM, prove the'),
    ('o0276', 'docs/CONTINUITY_LEDGER.md', 'the segment in-envelope leg PROVES that'),
    ('o0277', 'docs/CONTINUITY_LEDGER.md', 'on success the verifier prints a `PROVES:` line'),
    ('o0278', 'docs/CONTINUITY_LEDGER.md', 'This earns `proves` because'),
    ('o0279+o0280#1', 'docs/CONTINUITY_LEDGER.md', 'it refuses the `PROVES:` line'),
    ('o0279+o0280#2', 'docs/CONTINUITY_LEDGER.md', 'consistency-proven append'),
    ('o0281', 'docs/CONTINUITY_LEDGER.md', 'It PROVES the witnessed segment'),
    ('D376-3-s186-now', 'docs/CONTINUITY_LEDGER.md', 'and remains future work.'),
    ('o0283', 'docs/CONTINUITY_LEDGER.md', '`current_tree_size`, `proven`)'),
)

CORRECTED: tuple[tuple[str, str, str], ...] = (
    ('o0077', 'annex_iv_map.py', 'WHAT THE SIDECAR CHECKS (offline, fail-closed; Ed25519 and sha256):'),
    ('o0079', 'annex_iv_map.py', 'BOUNDARY: checks presence + authenticity + indexing of the declared evidence (sha256 digests and an Ed25519 signature).'),
    ('o0081', 'annex_iv_map.py', 'boundary: checks presence + authenticity + indexing (sha256 + " "Ed25519); NOT legal'),
    ('o0103', 'cli_conformance.py', 'Runtime conformance: check a signed execution trace against the " "envelope the static cost proof assumed (interval checks, a " "Decimal sum and Ed25519; no Z3)'),
    ('o0104', 'cli_dossier.py', 'it checks presence + authenticity + " "indexing (sha256 and Ed25519) of declared Annex IV'),
    ('o0137', 'cli_verify_release.py', 'the digest whose log inclusion ROOT 2 verified equals sha256(the exact VSA payload ROOT 1 verified).'),
    ('o0155', 'conformance_verifier.py', 'SCOPE: this checks, by Ed25519 signatures and sha256 equality, that the signed\\nverdict is AUTHENTIC'),
    ('o0661', 'envelope.py', 'NOUS CHECKS (set ops over root-committed canon fields) that the delta is within the declared envelope.'),
    ('o0662+o0663', 'envelope.py', '(verified separately by the dossier) evidences that current descends from # the baseline-committing build. Checked by set ops and an integer drift bound;'),
    ('o0732', 'rekor_anchor.py', 'the Rekor anchor evidences only "this SHA-256 was anchored at integrated_time T".'),
    ('o0736', 'remedy_proof.py', 're-verified by the EXISTING S97/v5.13 offline verifier, evidences only two things:'),
    ('o0765', 'signerctl.py', "check later verifies to be EQUAL to the live signer's HELLO,"),
    ('o0834', 'trace_anchor.py', 'log so a third party can verify the trace existed at a point in time and was not altered after.'),
    ('o0842', 'trace_bridge.py', '# Load pre-signed keys.json + obligations.json VERBATIM, verify the # active signer matches'),
    ('o0276', 'docs/CONTINUITY_LEDGER.md', 'the segment in-envelope leg EVIDENCES that every run appended'),
    ('o0277', 'docs/CONTINUITY_LEDGER.md', 'on success the verifier prints an `EVIDENCES:` line.'),
    ('o0278', 'docs/CONTINUITY_LEDGER.md', 'That is why the leg evidences: the same description fits an Ed25519 signature check'),
    ('o0279+o0280', 'docs/CONTINUITY_LEDGER.md', 'it refuses the `EVIDENCES:` line and fails the verification when the append verified by the consistency proof contains'),
    ('o0281', 'docs/CONTINUITY_LEDGER.md', 'The honest boundary. It EVIDENCES that the witnessed segment is conformance-certified'),
    ('D376-3-s186-now', 'docs/CONTINUITY_LEDGER.md', 'did not rise across the segment; that is the S186 leg below.'),
    ('o0283', 'docs/CONTINUITY_LEDGER.md', '(`prior_tree_size`, `current_tree_size`, `holds`) alongside the `consistency`'),
    ('D376-3-ledger-keymap', 'docs/CONTINUITY_LEDGER.md', 'Version 2 renames the key `proven` to `holds` in `segment_inenvelope`, `segment_cap_monotonic` and `segment_policy_monotonic`.'),
    ('D376-3-changelog', 'CHANGELOG.md', 'Breaking for `--json` consumers of that verifier: the key `proven` in `segment_inenvelope`, `segment_cap_monotonic` and `segment_policy_monotonic` is renamed `holds`'),
)


def _text(rel: str) -> str:
    return _WS.sub(" ", (ROOT / rel).read_text(encoding="utf-8"))


def _payload() -> str:
    return continuity_verifier.CONTINUITY_VERIFY_OFFLINE_PY


def test_continuity_payload_prints_only_the_farkas_label() -> None:
    labels: list[str] = sorted(set(_LABEL.findall(_payload())))
    assert labels == ["PROVES-budget"], f"PROVES labels in the continuity verifier: {labels}"


def test_continuity_payload_json_key_is_holds() -> None:
    counts: tuple[int, int] = (_payload().count('"proven"'), _payload().count('"holds"'))
    assert counts == (0, 5), f"continuity verifier (proven, holds) key counts: {counts}"


def test_continuity_payload_reports_schema_version_2() -> None:
    n: int = _payload().count('"report_schema_version": 2')
    assert n == 2, f"report_schema_version fields in the continuity verifier: {n}"


def test_continuity_payload_notes_say_does_not_hold() -> None:
    counts: tuple[int, int] = (_payload().count("NOT proven"), _payload().count("does not hold"))
    assert counts == (0, 2), f"continuity verifier (NOT proven, does not hold) counts: {counts}"


@pytest.mark.parametrize("site,rel,phrase", OVERCLAIMS, ids=[r[0] for r in OVERCLAIMS])
def test_wheel_overclaim_absent(site: str, rel: str, phrase: str) -> None:
    present: bool = phrase in _text(rel)
    assert present is False, f"{site}: overclaim still present in {rel}: {phrase!r}"


@pytest.mark.parametrize("site,rel,phrase", CORRECTED, ids=[r[0] for r in CORRECTED])
def test_wheel_corrected_copy_present(site: str, rel: str, phrase: str) -> None:
    present: bool = phrase in _text(rel)
    assert present is True, f"{site}: corrected copy missing in {rel}: {phrase!r}"
