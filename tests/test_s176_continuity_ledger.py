"""S176: counterparty-witnessed continuity ledger -- behavior lock.

Memorializes the contiguous, signature-verifying ledger walk and every
fail-closed branch of continuity_ledger.verify_link / walk_continuity_ledger.
cryptography + stdlib only (no NOUS install, no PyJWT) so the receipt legs run
identically wherever cryptography is present.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import time

import pytest

import continuity_ledger as cl
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


_OPERATOR = Ed25519PrivateKey.generate()
_COUNTERPARTY = Ed25519PrivateKey.generate()
_CP_PEM = _COUNTERPARTY.public_key().public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
)
_ISS = "https://counterparty.example"
_WORLD = hashlib.sha256(b"world-A").hexdigest()
_SOUL = hashlib.sha256(b"soul-1").hexdigest()
_AUD = "world:" + _WORLD


def _h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _operator_signature(body: bytes) -> dict:
    pub = _OPERATOR.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return {
        "algorithm": "ed25519",
        "public_key_b64": base64.b64encode(pub).decode("ascii"),
        "signature_b64": base64.b64encode(_OPERATOR.sign(body)).decode("ascii"),
    }


def _make_run(seq: int, prev_digest: str, head: str,
              *, witnessed: bool = True) -> dict:
    src, smt, pri = _h("src"), _h("smt"), _h("pri")
    trace = {
        "world_name": "world-A",
        "memory_consultation": {
            "world_sha256": _WORLD,
            "producing_soul_sha256": _SOUL,
            "consulted_chain_head": head,
            "consulted_seq_count": seq,
        },
    }
    trace["signature"] = _operator_signature(cl._doc_canonical_body_bytes(trace))
    trace_sha = hashlib.sha256(cl._doc_canonical_body_bytes(trace)).hexdigest()
    manifest = {
        "source_sha256": src, "smt_spec_sha256": smt, "pricing_sha256": pri,
    }
    cert = {
        "certificate_schema_version": 2, "conformant": True,
        "binding_ok": True, "surface_ok": True,
        "assumption_discharge_ok": True, "bound_transfer_ok": True,
        "authorization_ok": True, "trace_signature_ok": True,
        "sequence_ok": True, "trace_sha256": trace_sha,
        "source_sha256": src, "smt_spec_sha256": smt, "pricing_sha256": pri,
    }
    cert["signature"] = _operator_signature(cl._cert_canonical_body_bytes(cert))
    link = cl.build_link(
        cert=cert, trace=trace, prev_run_digest=prev_digest,
        counterparty_key_uri=(_ISS + "/keys") if witnessed else None,
    )
    bundle = {"cert": cert, "trace": trace, "manifest": manifest, "link": link}
    if witnessed:
        bundle["receipt"] = cl.build_counterparty_receipt(
            cert=cert, trace=trace, counterparty_signing_key=_COUNTERPARTY,
            counterparty_kid="cp-1", issuer=_ISS, audience=_AUD,
            prev_run_digest=prev_digest, issued_at=int(time.time()),
        )
    return bundle


def _recompute_link_digest(link: dict) -> None:
    src = {k: v for k, v in link.items() if k != "this_link_digest"}
    link["this_link_digest"] = hashlib.sha256(
        cl._canonical_bytes(src)
    ).hexdigest()


def _resign_receipt(receipt: dict, mutate) -> dict:
    claims = json.loads(cl._b64url_decode(receipt["payload"]))
    mutate(claims)
    protected = receipt["protected"]
    payload = _b64url(cl._canonical_bytes(claims))
    sig = _b64url(_COUNTERPARTY.sign((protected + "." + payload).encode("ascii")))
    return {"protected": protected, "payload": payload, "signature": sig}


def _genesis_chain(n: int, *, witnessed: bool = True) -> list:
    runs = []
    prev = cl.GENESIS_PREV_RUN_DIGEST
    for i in range(n):
        r = _make_run(i, prev, _h("chain" + str(i)), witnessed=witnessed)
        runs.append(r)
        prev = r["link"]["this_link_digest"]
    return runs


def _keys() -> dict:
    return {_ISS: _CP_PEM}


def test_genesis_sentinel_deterministic_and_distinct() -> None:
    assert cl.GENESIS_PREV_RUN_DIGEST == hashlib.sha256(
        b"nous:continuity-ledger:genesis:v1"
    ).hexdigest()
    assert len(cl.GENESIS_PREV_RUN_DIGEST) == 64
    assert cl.GENESIS_PREV_RUN_DIGEST != "0" * 64


def test_frozen_vocabulary() -> None:
    assert cl.LINK_KIND == "run"
    assert cl.WITNESS_KIND == "counterparty"
    assert cl.RECEIPT_FORMAT == "jws_eddsa_v1"
    assert cl.RECEIPT_ALG == "EdDSA"
    assert cl.RECEIPT_TYP == "application/nous-counterparty-receipt+jwt"


def test_unwitnessed_link_drops_counterparty_key_uri() -> None:
    r = _make_run(0, cl.GENESIS_PREV_RUN_DIGEST, _h("g"), witnessed=False)
    assert "counterparty_key_uri" not in r["link"]
    assert r["link"]["link_kind"] == "run"


def test_run_identity_digest_binds_cert_body() -> None:
    r = _make_run(0, cl.GENESIS_PREV_RUN_DIGEST, _h("g"))
    rid_a = r["link"]["run_identity_digest"]
    cert2 = copy.deepcopy(r["cert"])
    cert2["realized_total"] = 999
    rid_b = cl.run_identity_digest(
        world_sha256=_WORLD, producing_soul_sha256=_SOUL,
        cert_body_sha256=cl.certificate_body_digest(cert2),
        consulted_chain_head=_h("g"), consulted_seq_count=0,
    )
    assert rid_a != rid_b


def test_certificate_body_digest_matches_offline_formula() -> None:
    r = _make_run(0, cl.GENESIS_PREV_RUN_DIGEST, _h("g"))
    cert = r["cert"]
    body = {k: v for k, v in cert.items()
            if k not in ("signature", "transparency_log")}
    ref = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert cl.certificate_body_digest(cert) == ref


def test_receipt_verifies_raw_ed25519_openssl_path() -> None:
    r = _make_run(0, cl.GENESIS_PREV_RUN_DIGEST, _h("g"))
    rec = r["receipt"]
    pub = serialization.load_pem_public_key(_CP_PEM)
    signing_input = (rec["protected"] + "." + rec["payload"]).encode("ascii")
    pub.verify(cl._b64url_decode(rec["signature"]), signing_input)
    claims = json.loads(cl._b64url_decode(rec["payload"]))
    assert claims["sub"] == r["link"]["run_identity_digest"]
    assert claims["iss"] == _ISS and claims["aud"] == _AUD


def test_full_witnessed_ledger_walks_green() -> None:
    ledger = _genesis_chain(3)
    rep = cl.walk_continuity_ledger(
        ledger, counterparty_keys=_keys(), expected_audience=_AUD
    )
    assert rep["n_links"] == 3
    assert rep["n_witnessed"] == 3
    assert rep["witnessed_ratio"] == 1.0


def test_unordered_input_is_ordered_by_chain() -> None:
    a, b, c = _genesis_chain(3)
    rep = cl.walk_continuity_ledger(
        [c, a, b], counterparty_keys=_keys(), expected_audience=_AUD
    )
    assert rep["order"] == [
        a["link"]["this_link_digest"],
        b["link"]["this_link_digest"],
        c["link"]["this_link_digest"],
    ]


def test_mixed_witnessed_and_unwitnessed_ratio() -> None:
    a = _make_run(0, cl.GENESIS_PREV_RUN_DIGEST, _h("0"))
    b = _make_run(1, a["link"]["this_link_digest"], _h("1"), witnessed=False)
    rep = cl.walk_continuity_ledger(
        [a, b], counterparty_keys=_keys(), expected_audience=_AUD
    )
    assert rep["n_links"] == 2 and rep["n_witnessed"] == 1
    assert rep["witnessed_ratio"] == 0.5


def test_refuse_tampered_certificate() -> None:
    ledger = _genesis_chain(2)
    ledger[1]["cert"]["source_sha256"] = _h("EVIL")
    with pytest.raises(cl.ContinuityLedgerError):
        cl.walk_continuity_ledger(
            ledger, counterparty_keys=_keys(), expected_audience=_AUD
        )


def test_refuse_manifest_bind_mismatch() -> None:
    a = _make_run(0, cl.GENESIS_PREV_RUN_DIGEST, _h("g"))
    a["manifest"]["source_sha256"] = _h("OTHER")
    with pytest.raises(cl.ContinuityLedgerError):
        cl.verify_link(cert=a["cert"], trace=a["trace"],
                       manifest=a["manifest"], link=a["link"])


def test_refuse_tampered_link_digest() -> None:
    ledger = _genesis_chain(2)
    ledger[0]["link"]["this_link_digest"] = _h("nope")
    with pytest.raises(cl.ContinuityLedgerError):
        cl.walk_continuity_ledger(
            ledger, counterparty_keys=_keys(), expected_audience=_AUD
        )


def test_refuse_dangling_prev() -> None:
    ledger = _genesis_chain(2)
    ledger[1]["link"]["prev_run_digest"] = _h("ghost")
    _recompute_link_digest(ledger[1]["link"])
    ledger[1]["receipt"] = _resign_receipt(
        ledger[1]["receipt"], lambda c: c.__setitem__("prev_run_digest", _h("ghost"))
    )
    with pytest.raises(cl.ContinuityLedgerError):
        cl.walk_continuity_ledger(
            ledger, counterparty_keys=_keys(), expected_audience=_AUD
        )


def test_refuse_two_genesis() -> None:
    ledger = _genesis_chain(2)
    ledger[1]["link"]["prev_run_digest"] = cl.GENESIS_PREV_RUN_DIGEST
    _recompute_link_digest(ledger[1]["link"])
    with pytest.raises(cl.ContinuityLedgerError):
        cl.walk_continuity_ledger(
            ledger, counterparty_keys=_keys(), expected_audience=_AUD
        )


def test_refuse_fork() -> None:
    a = _make_run(0, cl.GENESIS_PREV_RUN_DIGEST, _h("0"))
    b = _make_run(1, a["link"]["this_link_digest"], _h("1"))
    c = _make_run(1, a["link"]["this_link_digest"], _h("2"))
    with pytest.raises(cl.ContinuityLedgerError):
        cl.walk_continuity_ledger(
            [a, b, c], counterparty_keys=_keys(), expected_audience=_AUD
        )


def test_refuse_disconnected_not_contiguous() -> None:
    a = _make_run(0, cl.GENESIS_PREV_RUN_DIGEST, _h("0"))
    b = _make_run(1, a["link"]["this_link_digest"], _h("1"))
    orphan = _make_run(2, _h("island"), _h("2"))
    _recompute_link_digest(orphan["link"])
    orphan["receipt"] = _resign_receipt(
        orphan["receipt"], lambda c: c.__setitem__("prev_run_digest", _h("island"))
    )
    with pytest.raises(cl.ContinuityLedgerError):
        cl.walk_continuity_ledger(
            [a, b, orphan], counterparty_keys=_keys(), expected_audience=_AUD
        )


def test_refuse_wrong_counterparty_key() -> None:
    other = Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    ledger = _genesis_chain(2)
    with pytest.raises(cl.ContinuityLedgerError):
        cl.walk_continuity_ledger(
            ledger, counterparty_keys={_ISS: other}, expected_audience=_AUD
        )


def test_refuse_no_published_key() -> None:
    ledger = _genesis_chain(2)
    with pytest.raises(cl.ContinuityLedgerError):
        cl.walk_continuity_ledger(
            ledger, counterparty_keys={}, expected_audience=_AUD
        )


def test_refuse_forged_receipt_sub() -> None:
    ledger = _genesis_chain(2)
    ledger[1]["receipt"] = _resign_receipt(
        ledger[1]["receipt"], lambda c: c.__setitem__("sub", _h("forged"))
    )
    with pytest.raises(cl.ContinuityLedgerError):
        cl.walk_continuity_ledger(
            ledger, counterparty_keys=_keys(), expected_audience=_AUD
        )


def test_refuse_forged_receipt_cert_body() -> None:
    ledger = _genesis_chain(2)
    ledger[1]["receipt"] = _resign_receipt(
        ledger[1]["receipt"],
        lambda c: c.__setitem__("cert_body_sha256", _h("forged")),
    )
    with pytest.raises(cl.ContinuityLedgerError):
        cl.walk_continuity_ledger(
            ledger, counterparty_keys=_keys(), expected_audience=_AUD
        )


def test_refuse_receipt_conformant_mismatch() -> None:
    ledger = _genesis_chain(2)
    ledger[1]["receipt"] = _resign_receipt(
        ledger[1]["receipt"], lambda c: c.__setitem__("conformant", False)
    )
    with pytest.raises(cl.ContinuityLedgerError):
        cl.walk_continuity_ledger(
            ledger, counterparty_keys=_keys(), expected_audience=_AUD
        )


def test_refuse_receipt_aud_mismatch() -> None:
    ledger = _genesis_chain(2)
    with pytest.raises(cl.ContinuityLedgerError):
        cl.walk_continuity_ledger(
            ledger, counterparty_keys=_keys(), expected_audience="world:wrong"
        )


def test_refuse_receipt_without_expected_audience() -> None:
    ledger = _genesis_chain(2)
    with pytest.raises(cl.ContinuityLedgerError):
        cl.walk_continuity_ledger(ledger, counterparty_keys=_keys())


def test_refuse_seq_decrease_monotonicity() -> None:
    a = _make_run(0, cl.GENESIS_PREV_RUN_DIGEST, _h("0"))
    b = _make_run(5, a["link"]["this_link_digest"], _h("5"))
    c = _make_run(2, b["link"]["this_link_digest"], _h("2"))
    with pytest.raises(cl.ContinuityLedgerError):
        cl.walk_continuity_ledger(
            [a, b, c], counterparty_keys=_keys(), expected_audience=_AUD
        )


def test_refuse_empty_ledger() -> None:
    with pytest.raises(cl.ContinuityLedgerError):
        cl.walk_continuity_ledger([], expected_audience=_AUD)


def test_refuse_missing_memory_consultation() -> None:
    cert = {"certificate_schema_version": 2, "conformant": True}
    with pytest.raises(cl.ContinuityLedgerError):
        cl.build_link(cert=cert, trace={},
                      prev_run_digest=cl.GENESIS_PREV_RUN_DIGEST)


def test_refuse_link_kind_not_run() -> None:
    a = _make_run(0, cl.GENESIS_PREV_RUN_DIGEST, _h("g"))
    a["link"]["link_kind"] = "build"
    _recompute_link_digest(a["link"])
    with pytest.raises(cl.ContinuityLedgerError):
        cl.verify_link(cert=a["cert"], trace=a["trace"],
                       manifest=a["manifest"], link=a["link"])


def test_refuse_receipt_signature_invalid() -> None:
    r = _make_run(0, cl.GENESIS_PREV_RUN_DIGEST, _h("g"))
    rec = dict(r["receipt"])
    rec["signature"] = _b64url(b"\x00" * 64)
    with pytest.raises(cl.ContinuityLedgerError):
        cl.verify_link(
            cert=r["cert"], trace=r["trace"], manifest=r["manifest"],
            link=r["link"], receipt=rec,
            counterparty_public_key_pem=_CP_PEM,
            expected_audience=_AUD,
        )
