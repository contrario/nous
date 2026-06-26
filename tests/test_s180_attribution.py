"""S180 signed-attribution core: mandatory tests, repo-import form.
Imports manifest + continuity_ledger by name (real installed modules).
Byte-identity vs the unpatched release is proven in the authoring sandbox;
here the drop-when-None invariant is asserted directly (no second module)."""
import base64
import dataclasses
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

import manifest as M
import continuity_ledger as L

FIELDS = dict(
    schema_version="1", nous_version="5.66.0", smt_emit_version="1",
    source_sha256="a" * 64, pricing_sha256="b" * 64, smt_spec_sha256="c" * 64,
    world_name="w", cost_cap_usd="1.00", max_ticks=10, verdict="SAFE",
    solver_name="z3", solver_version="4.16.0", elapsed_ms=5,
    timestamp_utc="2026-06-26T00:00:00Z",
)


def _pub_pem(sk):
    return sk.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _attestation_for(run_digest, authz_sk):
    raw = authz_sk.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    kid = L.authorizer_key_id(raw)
    receipt = L.build_authorization_receipt(
        run_digest=run_digest, authorizer_signing_key=authz_sk,
        authorizer_kid=kid,
    )
    attr = M.Attribution(
        actor_identity="Hlias Staurou", role="Authorized_Operator",
        key_id=kid, attribution_kind="attested",
        authorizer_pubkey_b64=base64.b64encode(raw).decode("ascii"),
        authorization_receipt=L.receipt_compact(receipt),
    )
    return attr, kid


def _split(compact):
    p, pl, s = compact.split(".")
    return {"protected": p, "payload": pl, "signature": s}


def test_backward_compat_no_attribution_invariant():
    m = M.Manifest(**FIELDS)
    assert "attribution" not in json.loads(m.canonical_bytes())
    sk = Ed25519PrivateKey.generate()
    sig = M.sign_manifest(m, sk)
    assert M.verify_manifest_signature(m, sig, sk.public_key())
    # run_digest of an attribution-absent manifest == sha256(canonical_bytes)
    import hashlib
    assert m.run_digest() == hashlib.sha256(m.canonical_bytes()).hexdigest()


def test_tamper_actor_identity_breaks_manifest_signature():
    authz_sk = Ed25519PrivateKey.generate()
    base = M.Manifest(**FIELDS)
    attr, _ = _attestation_for(base.run_digest(), authz_sk)
    m = dataclasses.replace(base, attribution=attr)
    op_sk = Ed25519PrivateKey.generate()
    sig = M.sign_manifest(m, op_sk)
    assert M.verify_manifest_signature(m, sig, op_sk.public_key())
    tampered = dataclasses.replace(
        m, attribution=dataclasses.replace(attr, actor_identity="Mallory"))
    assert not M.verify_manifest_signature(tampered, sig, op_sk.public_key())


def test_tamper_receipt_breaks_manifest_signature():
    authz_sk = Ed25519PrivateKey.generate()
    base = M.Manifest(**FIELDS)
    attr, _ = _attestation_for(base.run_digest(), authz_sk)
    m = dataclasses.replace(base, attribution=attr)
    op_sk = Ed25519PrivateKey.generate()
    sig = M.sign_manifest(m, op_sk)
    bad = dataclasses.replace(
        m, attribution=dataclasses.replace(
            attr,
            authorization_receipt=attr.authorization_receipt[:-4] + "AAAA"))
    assert not M.verify_manifest_signature(bad, sig, op_sk.public_key())


def test_replay_receipt_from_another_run_fails():
    authz_sk = Ed25519PrivateKey.generate()
    run_a = M.Manifest(**FIELDS)
    run_b = M.Manifest(**dict(FIELDS, world_name="other", cost_cap_usd="2.00"))
    rd_a, rd_b = run_a.run_digest(), run_b.run_digest()
    assert rd_a != rd_b
    attr_a, kid = _attestation_for(rd_a, authz_sk)
    receipt = _split(attr_a.authorization_receipt)
    pem = _pub_pem(authz_sk)
    assert L.verify_authorization_receipt(
        receipt=receipt, authorizer_public_key_pem=pem,
        expected_run_digest=rd_a, expected_key_id=kid)
    assert not L.verify_authorization_receipt(
        receipt=receipt, authorizer_public_key_pem=pem,
        expected_run_digest=rd_b, expected_key_id=kid)


def test_circularity_run_digest_stable_with_attribution_present():
    authz_sk = Ed25519PrivateKey.generate()
    base = M.Manifest(**FIELDS)
    rd_before = base.run_digest()
    attr, kid = _attestation_for(rd_before, authz_sk)
    m = dataclasses.replace(base, attribution=attr)
    assert m.run_digest() == rd_before
    assert L.verify_authorization_receipt(
        receipt=_split(attr.authorization_receipt),
        authorizer_public_key_pem=_pub_pem(authz_sk),
        expected_run_digest=m.run_digest(), expected_key_id=kid)

# ============================================================
# __s180_attribution_reach_tests_v1__  (increment-2: verifier reach)
# ============================================================
import os
import subprocess
import sys
import tempfile

import dossier as D

_DISCLAIMER_AUDITOR_SENTENCE = (
    "that identity check is YOUR step, not this verifier's"
)


def _emit_verifier_text(parsed):
    # Mirror the real build_dossier emit order using only PUBLIC dossier
    # symbols that exist on Server A post-patch (no sandbox-only harness):
    # base template, materiality splice iff materiality_sha256, attribution
    # splice iff attribution.
    src = D.VERIFY_OFFLINE_PY
    if parsed.materiality_sha256 is not None:
        src = D._splice_materiality_check(src)
    if parsed.attribution is not None:
        src = D._splice_attribution_check(src)
    return src


def _emit_and_run(tmp, m, op_sk, *, extra_files=None):
    import hashlib
    from pathlib import Path
    d = Path(tmp)
    # make source.nous real so the base verifier source-leg passes
    source_bytes = b"world demo {}\n"
    src_sha = hashlib.sha256(source_bytes).hexdigest()
    m = dataclasses.replace(m, source_sha256=src_sha)
    sig = M.sign_manifest(m, op_sk)
    mj = M.manifest_json(m, sig, op_sk.public_key())
    (d / "manifest.json").write_text(mj, encoding="utf-8")
    (d / "source.nous").write_bytes(source_bytes)
    for name, data in (extra_files or {}).items():
        (d / name).write_bytes(data)
    parsed, _, _ = M.parse_manifest_json(mj)
    verify_text = _emit_verifier_text(parsed)
    vp = d / "verify_offline.py"
    vp.write_text(verify_text, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(vp)], cwd=str(d),
        capture_output=True, text=True,
    )
    return proc, verify_text, m


def test_attested_dossier_verifier_passes_and_prints_disclaimer():
    authz_sk = Ed25519PrivateKey.generate()
    op_sk = Ed25519PrivateKey.generate()
    with tempfile.TemporaryDirectory() as tmp:
        base = M.Manifest(**FIELDS)
        # attribution co-signs the FINAL run_digest; recompute after source fix
        import hashlib
        source_bytes = b"world demo {}\n"
        base = dataclasses.replace(
            base, source_sha256=hashlib.sha256(source_bytes).hexdigest())
        attr, kid = _attestation_for(base.run_digest(), authz_sk)
        m = dataclasses.replace(base, attribution=attr)
        proc, vtext, _ = _emit_and_run(tmp, m, op_sk)
        assert "_check_attribution" in vtext
        assert proc.returncode == 0, proc.stderr + "\n" + proc.stdout
        out = proc.stdout
        assert "authorizer co-signature verified" in out
        assert "Hlias Staurou" in out
        assert kid in out
        assert "Cryptographic Attribution Disclosure" in out
        assert _DISCLAIMER_AUDITOR_SENTENCE in out


def test_attested_verifier_fails_closed_on_tampered_and_replayed():
    import hashlib
    op_sk = Ed25519PrivateKey.generate()
    authz_sk = Ed25519PrivateKey.generate()
    source_bytes = b"world demo {}\n"
    src_sha = hashlib.sha256(source_bytes).hexdigest()

    # (a) FORGED RECEIPT: operator re-signs over the tampered manifest so the
    # operator-signature leg PASSES; the standalone embed must still FAIL.
    with tempfile.TemporaryDirectory() as tmp:
        from pathlib import Path
        d = Path(tmp)
        base = dataclasses.replace(M.Manifest(**FIELDS), source_sha256=src_sha)
        attr, _ = _attestation_for(base.run_digest(), authz_sk)
        bad_compact = attr.authorization_receipt[:-4] + "AAAA"
        bad_attr = dataclasses.replace(
            attr, authorization_receipt=bad_compact)
        m = dataclasses.replace(base, attribution=bad_attr)
        sig = M.sign_manifest(m, op_sk)  # operator signs the forged manifest
        mj = M.manifest_json(m, sig, op_sk.public_key())
        (d / "manifest.json").write_text(mj, encoding="utf-8")
        (d / "source.nous").write_bytes(source_bytes)
        parsed, _, _ = M.parse_manifest_json(mj)
        assert M.verify_manifest_signature(m, sig, op_sk.public_key())
        vp = d / "verify_offline.py"
        vp.write_text(_emit_verifier_text(parsed), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(vp)], cwd=str(d),
            capture_output=True, text=True)
        assert proc.returncode == 1, proc.stdout
        assert "OK   Ed25519 signature verified" in proc.stdout
        assert "co-signature forged or tampered" in proc.stderr

    # (b) REPLAYED RECEIPT: a valid receipt co-signing a DIFFERENT run, glued
    # onto this manifest; operator re-signs. Embed must FAIL on run_digest.
    with tempfile.TemporaryDirectory() as tmp:
        from pathlib import Path
        d = Path(tmp)
        other = dataclasses.replace(
            M.Manifest(**FIELDS), source_sha256=src_sha, world_name="other")
        this = dataclasses.replace(M.Manifest(**FIELDS), source_sha256=src_sha)
        assert other.run_digest() != this.run_digest()
        attr_other, _ = _attestation_for(other.run_digest(), authz_sk)
        m = dataclasses.replace(this, attribution=attr_other)
        sig = M.sign_manifest(m, op_sk)
        mj = M.manifest_json(m, sig, op_sk.public_key())
        (d / "manifest.json").write_text(mj, encoding="utf-8")
        (d / "source.nous").write_bytes(source_bytes)
        parsed, _, _ = M.parse_manifest_json(mj)
        assert M.verify_manifest_signature(m, sig, op_sk.public_key())
        vp = d / "verify_offline.py"
        vp.write_text(_emit_verifier_text(parsed), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(vp)], cwd=str(d),
            capture_output=True, text=True)
        assert proc.returncode == 1, proc.stdout
        assert "OK   Ed25519 signature verified" in proc.stdout
        assert "replayed from another run" in proc.stderr


def test_no_attribution_dossier_verifier_is_byte_identical():
    # A dossier with neither materiality nor attribution must emit the base
    # template VERBATIM: the attribution splice never fires, no _check_*.
    base = M.Manifest(**FIELDS)
    assert base.attribution is None
    assert base.materiality_sha256 is None
    verify_text = _emit_verifier_text(base)
    assert verify_text == D.VERIFY_OFFLINE_PY
    assert "_check_attribution" not in verify_text
    assert "_check_materiality" not in verify_text

    # ...and it still verifies a real no-attribution dossier (rc 0).
    op_sk = Ed25519PrivateKey.generate()
    with tempfile.TemporaryDirectory() as tmp:
        proc, vtext, _ = _emit_and_run(tmp, base, op_sk)
        assert vtext == D.VERIFY_OFFLINE_PY
        assert proc.returncode == 0, proc.stderr + "\n" + proc.stdout
        assert "OK   Ed25519 signature verified" in proc.stdout


def test_materiality_and_attribution_splices_compose_either_order():
    import py_compile  # noqa: F401  (compile via builtins.compile)
    base = D.VERIFY_OFFLINE_PY

    mat_then_attr = D._splice_attribution_check(
        D._splice_materiality_check(base))
    attr_then_mat = D._splice_materiality_check(
        D._splice_attribution_check(base))

    for label, text in (("mat_then_attr", mat_then_attr),
                        ("attr_then_mat", attr_then_mat)):
        compile(text, "<" + label + ">", "exec")  # raises on bad syntax
        assert text.count("def _check_materiality(") == 1, label
        assert text.count("def _check_attribution(") == 1, label
        assert "_rc_mat = _check_materiality(manifest, ROOT)" in text, label
        assert "_rc_attr = _check_attribution(manifest, ROOT)" in text, label
        assert text.count('if __name__ == "__main__":') == 1, label
        # both checks run before the final return 0
        i_mat = text.index("_rc_mat = _check_materiality")
        i_attr = text.index("_rc_attr = _check_attribution")
        i_main = text.index('if __name__ == "__main__":')
        assert i_mat < i_main and i_attr < i_main, label


def test_realistic_priced_manifest_run_digest_paths_agree():
    # confirmation #2: the dataclass run_digest (from canonical_dict) and the
    # embed's recompute (from the SERIALIZED-then-parsed JSON dict, stripping
    # signature/transparency_log/attribution) must agree on a FULL manifest --
    # float cost_cap and every optional sha256 field populated -- not only a
    # minimal one.
    import hashlib
    # Populate every OPTIONAL field the live Manifest actually exposes, so the
    # canonical body is a full one. Filter through dataclasses.fields so an
    # optional name that is not a real constructor param on Server A is simply
    # skipped (no TypeError) rather than betting the test on a memorized list.
    candidate_optionals = dict(
        cost_cap_usd=12.55,                 # float, not the "1.00" string
        codegen_sha256="3" * 64,
        cost_farkas_sha256="4" * 64,
        materiality_sha256="5" * 64,
        safety_margin_pct=10,
    )
    real_fields = {f.name for f in dataclasses.fields(M.Manifest)}
    updates = {k: v for k, v in candidate_optionals.items()
               if k in real_fields}
    assert "cost_cap_usd" in updates  # float cost is the headline of this test
    full = dataclasses.replace(M.Manifest(**FIELDS), **updates)
    rd_dataclass = full.run_digest()

    authz_sk = Ed25519PrivateKey.generate()
    op_sk = Ed25519PrivateKey.generate()
    attr, kid = _attestation_for(rd_dataclass, authz_sk)
    m = dataclasses.replace(full, attribution=attr)

    # round-trip exactly as the dossier ships it / the verifier reads it
    sig = M.sign_manifest(m, op_sk)
    doc = json.loads(M.manifest_json(m, sig, op_sk.public_key()))
    body = {k: v for k, v in doc.items()
            if k not in ("signature", "transparency_log", "attribution")}
    rd_embed = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode(
            "utf-8")).hexdigest()

    assert rd_embed == rd_dataclass
    # float survived the JSON round-trip with stable repr
    assert doc["cost_cap_usd"] == 12.55

    # and the embed verifies the receipt for this realistic run_digest
    ns = {}
    exec(D._ATTRIBUTION_CHECK_EMBED, ns)
    with tempfile.TemporaryDirectory() as tmp:
        from pathlib import Path
        rc = ns["_check_attribution"](doc, Path(tmp))
    assert rc == 0
