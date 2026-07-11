"""
S226 -- release-VSA backfill disclosure (mint --backfill).

Offline. Locks the honest-boundary contract of the signed backfill note and
proves the index.json mirror is drop-when-absent. No network, no signing key.

__s226_backfill_disclosure_test_v1__
"""
from __future__ import annotations

import inspect

import mint_release_vsa as m


def test_backfill_flag_on_mint_subparser() -> None:
    p = m.build_arg_parser()
    ns = p.parse_args(["mint", "5.72.0", "--out", "x", "--backfill"])
    assert ns.backfill is True
    ns2 = p.parse_args(["mint", "5.72.0", "--out", "x"])
    assert ns2.backfill is False


def test_mint_signature_accepts_backfill_kw() -> None:
    params = inspect.signature(m.mint).parameters
    assert "backfill" in params
    assert params["backfill"].default is False


def test_backfill_note_is_ascii() -> None:
    m.BACKFILL_NOTE.encode("ascii")  # raises if non-ASCII


def test_backfill_note_honest_boundary_phrases() -> None:
    n = m.BACKFILL_NOTE
    assert "MINTED at backfilledAt" in n
    assert "no later than the anchor timestamp" in n
    assert "no lower bound" in n
    assert "do NOT evidence anchoring at release time" in n
    assert "named federation attestations" in n
    assert "PROVES nothing" in n
    assert "monitor, not a guard" in n
    # never claims proof, never claims release-time anchoring
    assert "proves that" not in n.lower()
    assert "anchored at release" not in n.lower()


def test_backfill_injection_is_guarded_in_source() -> None:
    src = inspect.getsource(m.mint)
    assert "if backfill:  # __s226_backfill_ext_v1__" in src
    assert 'ext["backfill"]' in src


def test_index_mirror_is_drop_when_absent_in_source() -> None:
    src = inspect.getsource(m.build_release_index)
    assert "__s226_backfill_index_mirror_v1__" in src
    assert 'bf = ext.get("backfill")' in src
    assert "if isinstance(bf, dict):" in src


def _fixture_statement(with_backfill: dict | None):
    whl = "nous_lang-9.9.9-py3-none-any.whl"
    sdist = "nous_lang-9.9.9.tar.gz"
    ext = {
        "boundary": "b",
        "buildIdentity": {
            "buildType": "bt",
            "builderId": "bi",
            "path": "p",
            "ref": "r",
            "repository": "repo",
            "sourceCommit": "sc",
        },
        "subjectFederation": [
            {
                "name": whl,
                "buildLeg": {"uri": "u", "payloadSha256": "PP", "predicateType": "pt"},
                "publishLeg": {"uri": "pw", "payloadSha256": "sw", "predicateType": "ppt"},
            },
            {
                "name": sdist,
                "buildLeg": {"uri": "u", "payloadSha256": "PP", "predicateType": "pt"},
                "publishLeg": {"uri": "ps", "payloadSha256": "ss", "predicateType": "ppt"},
            },
        ],
    }
    if with_backfill is not None:
        ext["backfill"] = with_backfill
    return {
        "subject": [
            {"name": whl, "digest": {"sha256": "a" * 64}},
            {"name": sdist, "digest": {"sha256": "b" * 64}},
        ],
        "predicate": {
            "policy": {"digest": {"sha256": "pol"}, "uri": "https://x/policy"},
            "verifiedLevels": ["SLSA_BUILD_LEVEL_2"],
            "verifier": {"id": m.build_vsa.NOUS_RELEASE_VERIFIER_ID},
            m.NOUS_BUILD_VSA_EXT_KEY: ext,
        },
    }, whl, sdist


def _call_build_index(monkeypatch, tmp_path, backfill_obj):
    vsa_sha = "c" * 64
    monkeypatch.setattr(m, "_anchored_digest_hex", lambda body: vsa_sha)
    monkeypatch.setattr(m, "_entry_kind", lambda body: "hashedrekord/0.0.2")
    monkeypatch.setattr(m, "_leaf_hash_hex", lambda body: "leaf")
    monkeypatch.setattr(m, "_checkpoint_origin", lambda cp: "log2025-1.rekor.sigstore.dev")
    statement, whl, sdist = _fixture_statement(backfill_obj)
    bundle = {
        "transparency_log_entry": {
            "canonicalized_body": "x",
            "inclusion_proof": {"checkpoint": "cp", "tree_size": 1},
            "log_index": 2,
        }
    }
    for fn in ("vsa.json", "verifier.py", "vkey.json", "bundle.json"):
        (tmp_path / fn).write_bytes(b"x")
    return m.build_release_index(
        "9.9.9",
        tmp_path,
        statement=statement,
        bundle=bundle,
        bundle_filename="bundle.json",
        vsa_filename="vsa.json",
        verifier_filename="verifier.py",
        verifier_key_filename="vkey.json",
        operator_pin_b64=m.COMMITTED_RELEASE_PIN_B64,
        vsa_payload_sha256_hex=vsa_sha,
        rfc3161_gen_time="2026-01-01T00:00:00Z",
        emitted_at="2026-01-01T00:00:00Z",
    )


def test_index_mirrors_backfill_when_present(monkeypatch, tmp_path) -> None:
    bf = {"backfilledAt": "2026-07-11T00:00:00Z", "originalReleaseTag": "v9.9.9", "note": "n"}
    index = _call_build_index(monkeypatch, tmp_path, bf)
    assert index["backfill"] == bf


def test_index_omits_backfill_when_absent(monkeypatch, tmp_path) -> None:
    index = _call_build_index(monkeypatch, tmp_path, None)
    assert "backfill" not in index
