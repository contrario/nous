"""S170 -- cost-cap SCOPE lockstep: the offline verifier's printed SCOPE must
track the presence of a verified costProof leg, never understate and never
overclaim.  # __s170_cost_scope_lockstep_v1__

A cost leg present and verified  -> SCOPE says PROVES-cost under the declared
per-call token/tick estimates, and the cost-cap is NO LONGER listed as an
EVIDENCES-only out-of-scope item. A cost leg absent -> SCOPE says PROVES-cost:
none and the cost-cap stays an EVIDENCES-only out-of-scope item (byte-identical
to the pre-cost-leg verifier). A tampered or forged cost certificate is
rejected (the proof is re-checked offline by rational arithmetic, not trusted
on its sha alone). Coverage is held off in these bundles so the cost leg is the
only variable.
"""
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from _v3pin import vsa_pin_args  # __nt_v3_classes_tests_v1__
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)

import cost_farkas
import vsa
import vsa_verifier

# __nt_v1c_s170_real_canon_v1__ The fixture was a two-row toy system under a
# fake smt_spec_sha256: an unrelated infeasible system graded as PROVEN (the
# N6 class). It is now the certificate cost_farkas derives from one closed-
# shape spec canon, bound to the manifest by sha256, carried by the cert.
_CANON = "\n".join((
    "NV:test",
    "EV:1.0",
    "SS:" + "a" * 64,
    "PS:" + "c" * 64,
    "W:alpha",
    "CC:0.5|USD",
    "MT:5",
    "D:cost_S_per_call:Real",
    "D:cost_S_total:Real",
    "D:total_cost:Real",
    "A:(assert (= cost_S_per_call (/ (+ (* 1 100) (* 2 50)) 1000000)))",
    "A:(assert (= cost_S_total (* cost_S_per_call 5)))",
    "A:(assert (= total_cost cost_S_total))",
    "O:(assert (not (<= total_cost (/ 1 2))))",
))
_SMT = hashlib.sha256(_CANON.encode("utf-8")).hexdigest()
_PER_CALL, _MT, _CAP, _MARGIN = cost_farkas._cost_rederive_parse(_CANON)
_COST_FARKAS = cost_farkas.extract_cost_certificate(
    souls=[cost_farkas.SoulCost(name=k, per_call=v)
           for k, v in _PER_CALL.items()],
    max_ticks=_MT, cost_cap=_CAP, margin_pct=_MARGIN,
)
_COST_FARKAS_FORGED = dict(
    _COST_FARKAS,
    multipliers=["1"] * len(_COST_FARKAS["multipliers"]),
    contradiction="claimed but does not hold",
)


def _pub_b64(priv: Ed25519PrivateKey) -> str:
    raw = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def _manifest_canon(doc: dict) -> bytes:
    body = {
        k: v for k, v in doc.items()
        if k not in ("signature", "transparency_log")
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def _trace_canon(doc: dict) -> bytes:
    body = {k: v for k, v in doc.items() if k != "signature"}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def _cert_canon(doc: dict) -> bytes:
    body = {
        k: v for k, v in doc.items()
        if k not in ("signature", "transparency_log")
    }
    if int(body.get("certificate_schema_version", 1)) < 2:
        body.pop("sequence_ok", None)
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def _sign(doc: dict, priv: Ed25519PrivateKey, canon, algorithm: bool = True) -> dict:
    sig = priv.sign(canon(doc))
    block = {
        "public_key_b64": _pub_b64(priv),
        "signature_b64": base64.b64encode(sig).decode("ascii"),
    }
    if algorithm:
        block["algorithm"] = "ed25519"
    out = dict(doc)
    out["signature"] = block
    return out


def _run(dirp) -> tuple[int, str, str]:
    r = subprocess.run(
        [sys.executable, str(dirp / "verify_vsa_offline.py")]
        + vsa_pin_args(dirp),
        capture_output=True, text=True, cwd=str(dirp),
    )
    return r.returncode, r.stdout, r.stderr


def _cost_bundle(dirp, *, with_cost: bool = True, cost_doc: dict | None = None):
    mk = Ed25519PrivateKey.generate()
    tk = Ed25519PrivateKey.generate()
    ck = Ed25519PrivateKey.generate()
    vk = Ed25519PrivateKey.generate()
    src, smt, pri, cg = "a" * 64, _SMT, "c" * 64, "d" * 64

    doc = cost_doc if cost_doc is not None else _COST_FARKAS
    cost_bytes = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
    cost_sha = hashlib.sha256(cost_bytes).hexdigest()

    manifest = {
        "world_name": "alpha", "source_sha256": src,
        "smt_spec_sha256": smt, "pricing_sha256": pri,
        "codegen_sha256": cg, "cost_cap_usd": "0.5", "max_ticks": 5,
    }
    if with_cost:
        manifest["cost_farkas_sha256"] = cost_sha
    manifest = _sign(manifest, mk, _manifest_canon, algorithm=False)

    trace = {"world_name": "alpha", "codegen_sha256": cg,
             "source_sha256": src, "smt_spec_sha256": smt,
             "pricing_sha256": pri, "events": []}  # __nt_v3_classes_tests_v1__
    trace = _sign(trace, tk, _trace_canon)
    trace_sha = hashlib.sha256(_trace_canon(trace)).hexdigest()

    bools = {b: True for b in vsa.OBLIGATION_NAMES}
    cert = {
        "certificate_schema_version": 4, "nous_version": "5.55.0",
        "world_name": "alpha", "issued_utc": "2026-06-19T11:00:00Z",
        "source_sha256": src, "smt_spec_sha256": smt, "pricing_sha256": pri,
        "trace_sha256": trace_sha, "conformant": True, "errors": [],
        "realized_total": "0",  # __nt_v3_classes_tests_v1__
        "codegen_sha256": cg,
    }
    cert.update(bools)
    if with_cost:
        cert["obligations_canon"] = _CANON
    cert = _sign(cert, ck, _cert_canon)

    man_sha = hashlib.sha256(_manifest_canon(manifest)).hexdigest()
    cert_sha = hashlib.sha256(_cert_canon(cert)).hexdigest()
    stmt = vsa.build_vsa_statement(
        world_name="alpha", nous_version="5.55.0",
        issued_utc="2026-06-19T11:00:00Z", codegen_sha256=cg,
        source_sha256=src, manifest_canonical_sha256=man_sha,
        trace_canonical_sha256=trace_sha,
        certificate_canonical_sha256=cert_sha, conformant=True,
        errors=(), certificate_schema_version=4,
        coverage_farkas_sha256=None, coverage_farkas_doc=None,
        cost_farkas_sha256=(cost_sha if with_cost else None),
        cost_farkas_doc=(doc if with_cost else None),
    )
    env = vsa.sign_vsa(stmt, vk)
    dirp.mkdir(parents=True, exist_ok=True)
    (dirp / "manifest.json").write_text(json.dumps(manifest))
    (dirp / "trace.json").write_text(json.dumps(trace))
    (dirp / "conformance.json").write_text(json.dumps(cert))
    (dirp / "vsa.intoto.json").write_text(json.dumps(env))
    if with_cost:
        (dirp / "cost.farkas.json").write_bytes(cost_bytes)
    return vk, cost_sha


_EVIDENCES_ONLY = "the cost-cap SMT bound (EVIDENCES only"
_PROVES_COST = "PROVES-cost (rational arithmetic, no solver, no NOUS install)"
_DECLARED = "under the declared per-call token/tick estimates"


def test_cost_leg_present_proves_cost_under_declared_estimates(tmp_path):
    vk, _ = _cost_bundle(tmp_path, with_cost=True)
    vsa_verifier.emit_vsa_verifier(
        str(tmp_path), vsa.public_key_raw_b64(vk.public_key())
    )
    rc, out, err = _run(tmp_path)
    assert rc == 0, err
    assert "cost-cap Farkas certificate PROVEN offline" in out
    assert _PROVES_COST in out
    assert _DECLARED in out
    assert "Runtime adherence to those estimates stays EVIDENCES" in out
    assert _EVIDENCES_ONLY not in out


def test_cost_leg_absent_stays_evidences_only(tmp_path):
    vk, _ = _cost_bundle(tmp_path, with_cost=False)
    vsa_verifier.emit_vsa_verifier(
        str(tmp_path), vsa.public_key_raw_b64(vk.public_key())
    )
    rc, out, err = _run(tmp_path)
    assert rc == 0, err
    assert "PROVES-cost: none carried in this VSA (no cost-cap Farkas leg)." in out
    assert _EVIDENCES_ONLY in out
    assert _PROVES_COST not in out


def test_cost_leg_does_not_disturb_coverage_proves_none(tmp_path):
    vk, _ = _cost_bundle(tmp_path, with_cost=True)
    vsa_verifier.emit_vsa_verifier(
        str(tmp_path), vsa.public_key_raw_b64(vk.public_key())
    )
    rc, out, err = _run(tmp_path)
    assert rc == 0, err
    assert "PROVES: none carried in this VSA (no coverage Farkas leg)." in out


def test_tampered_cost_farkas_sha_rejected(tmp_path):
    vk, _ = _cost_bundle(tmp_path, with_cost=True)
    raw = (tmp_path / "cost.farkas.json").read_bytes()
    (tmp_path / "cost.farkas.json").write_bytes(raw + b" ")
    vsa_verifier.emit_vsa_verifier(
        str(tmp_path), vsa.public_key_raw_b64(vk.public_key())
    )
    rc, out, err = _run(tmp_path)
    assert rc != 0
    assert "cost.farkas.json sha != costProof.sha256" in (out + err)
    assert _PROVES_COST not in out


def test_forged_cost_farkas_math_rejected(tmp_path):
    vk, _ = _cost_bundle(tmp_path, with_cost=True, cost_doc=_COST_FARKAS_FORGED)
    vsa_verifier.emit_vsa_verifier(
        str(tmp_path), vsa.public_key_raw_b64(vk.public_key())
    )
    rc, out, err = _run(tmp_path)
    assert rc != 0
    assert "cost-cap Farkas certificate does NOT prove the bound" in (out + err)
    assert _PROVES_COST not in out
