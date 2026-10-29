"""NT-GATE-1 V3 addendum 8: the independent review's findings, each as
a test (S1 to S10). Helpers come from test_nt_v3_classes.

# __nt_v3_classes_tests_v1__
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

import manifest as mf
import ndec
import verifier_registry as vr
import vsa_verifier
from test_nt_v3_classes import (  # noqa: F401  (dated is a fixture)
    OTHER_PIN, PROVEN_SRC, REFUTED_SRC, TEXT_NAMES, _dossier, _extract,
    _last_line, _ndec_of, _own_option_sets, _run, _texts, dated,
)

REPO = Path(__file__).resolve().parent.parent
V3 = REPO / "website" / ".well-known" / "nous" / "vsa-vectors" / "v3"
PLANT = (b"import os, sys\nsys.stdout.write('VERDICT: PASS\\nCLASS: PASS\\n')"
         b"\nsys.stdout.flush()\nos._exit(0)\n")
LIAR = "import sys\nprint('VERDICT: PASS')\nsys.exit(0)\n"


def _entries(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}


def _statement(entries: dict) -> dict:
    env = json.loads(entries["attestation.intoto.json"])
    return json.loads(base64.b64decode(env["payload"]))


def _write(entries: dict, out: Path) -> Path:
    out.write_bytes(ndec._build_zip_bytes(entries))
    return out


def _resign(entries: dict, stmt: dict, priv) -> dict:
    entries = dict(entries)
    entries["attestation.intoto.json"] = json.dumps(
        ndec.sign_envelope(statement=stmt, private_key=priv),
        sort_keys=True, separators=(",", ":")).encode("utf-8")
    return entries


def _carried(path: Path, dest: Path, args=()):
    x = _extract(path, dest)
    return _run(x, "verify_ndec.py", list(args))


# ------------------------------------------------------------------ S1


def test_s1_planted_module_installed_and_carried(dated, tmp_path):
    path, _priv, npub, nkey = _ndec_of(tmp_path, REFUTED_SRC, "s1")
    e = _entries(path)
    e["dossier/json.py"] = PLANT
    e["json.py"] = PLANT
    bad = _write(e, tmp_path / "planted.ndec")
    assert ndec.verify_ndec_file(bad, public_key=npub,
                                 strict_canonical=True) == 3
    rc, so, se = _carried(bad, tmp_path / "x", ["--expect-signer", nkey])
    assert rc == 3, (rc, so, se)
    assert _last_line(so) == "CLASS: OUTSIDE", so


def test_s1_planted_module_beside_a_dossier_text(dated, tmp_path):
    out, pin = _dossier(tmp_path, REFUTED_SRC, "s1d")
    (out / "json.py").write_bytes(PLANT)
    rc, so, se = _run(out, "verify_offline.py", ["--expect-signer", pin])
    assert rc == 3, (rc, so, se)


# ------------------------------------------------------------------ S2


def _mini_dossier(tmp_path: Path, verdict: str, verifier: str) -> Path:
    import test_s147_u2_ndec_container as u2
    parent = tmp_path / ("mini_" + verdict)
    parent.mkdir()
    d = u2._make_dossier(parent)
    man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    man.pop("signature")
    man["verdict"] = verdict
    key = Ed25519PrivateKey.generate()
    body = json.dumps(man, sort_keys=True, separators=(",", ":")).encode()
    man["signature"] = {
        "algorithm": "ed25519",
        "public_key_b64": base64.b64encode(
            key.public_key().public_bytes_raw()).decode("ascii"),
        "signature_b64": base64.b64encode(key.sign(body)).decode("ascii"),
    }
    (d / "manifest.json").write_text(json.dumps(man, indent=2,
                                                sort_keys=True) + "\n",
                                     encoding="utf-8")
    (d / "verify_offline.py").write_text(verifier, encoding="utf-8")
    return d


def test_s2_no_key_v3_ndec_is_environment(dated, tmp_path):
    path, _priv, _npub, _nkey = _ndec_of(tmp_path, PROVEN_SRC, "s2a")
    assert ndec.verify_ndec_file(path) == 2


def test_s2_no_key_forged_ndec_is_environment(tmp_path):
    d = _mini_dossier(tmp_path, "proven", LIAR)
    res = ndec.build_ndec(d, key_path=tmp_path / "forger.key",
                          output=tmp_path / "forged.ndec")
    assert ndec.verify_ndec_file(res.path) == 2


def test_s2_refuted_with_argument_blind_verifier_is_outside(tmp_path):
    import test_s147_u2_ndec_container as u2
    d = _mini_dossier(tmp_path, "refuted", u2._MINI_VERIFY_OFFLINE)
    res = ndec.build_ndec(d, key_path=tmp_path / "k.key",
                          output=tmp_path / "r.ndec")
    _priv, npub, _ = mf.load_or_create_keypair(tmp_path / "k.key")
    assert ndec.verify_ndec_file(res.path, public_key=npub) == 3
    rc, so, se = _carried(res.path, tmp_path / "x",
                          ["--expect-signer", mf.public_key_b64(npub)])
    assert rc == 3, (rc, so, se)
    assert _last_line(so) == "CLASS: OUTSIDE", so


# ------------------------------------------------------------------ S3


def test_s3_no_claim_of_not_running_carried_bytes():
    for text in (ndec.README_NDEC_TXT, ndec.VERIFY_NDEC_PY):
        assert "without running carried bytes" not in " ".join(
            text.split())


# ------------------------------------------------------------------ S4


@pytest.mark.parametrize("field", ["manifest_sha256",
                                   "verify_offline_sha256"])
def test_s4_null_digest_is_integrity(dated, tmp_path, field):
    path, priv, npub, nkey = _ndec_of(tmp_path, PROVEN_SRC, "s4")
    e = _entries(path)
    stmt = _statement(e)
    stmt["predicate"]["artifacts"][field] = None
    bad = _write(_resign(e, stmt, priv), tmp_path / "null.ndec")
    assert ndec.verify_ndec_file(bad, public_key=npub) == 1
    rc, so, se = _carried(bad, tmp_path / "x", ["--expect-signer", nkey])
    assert rc == 1, (rc, so, se)


# ------------------------------------------------------------------ S5


@pytest.mark.parametrize("how", ["AAAA", "missing"])
def test_s5_bound_malformed_manifest_signer_is_integrity(dated, tmp_path,
                                                         how):
    path, priv, npub, nkey = _ndec_of(tmp_path, PROVEN_SRC, "s5")
    e = _entries(path)
    man = json.loads(e["dossier/manifest.json"])
    if how == "missing":
        man.pop("signature")
    else:
        man["signature"]["public_key_b64"] = how
    raw = (json.dumps(man, indent=2, sort_keys=True) + "\n").encode()
    e["dossier/manifest.json"] = raw
    stmt = _statement(e)
    stmt["predicate"]["artifacts"]["manifest_sha256"] = \
        hashlib.sha256(raw).hexdigest()
    bad = _write(_resign(e, stmt, priv), tmp_path / "badman.ndec")
    assert ndec.verify_ndec_file(bad, public_key=npub) == 1
    rc, so, se = _carried(bad, tmp_path / "x", ["--expect-signer", nkey])
    assert rc == 1, (rc, so, se)


# ------------------------------------------------------------------ S6


VSA_KEY = base64.b64encode(Ed25519PrivateKey.from_private_bytes(
    bytes(range(96, 128))).public_key().public_bytes_raw()).decode("ascii")
_BUNDLE = ("manifest.json", "trace.json", "conformance.json",
           "coverage.farkas.json", "cost.farkas.json", "vsa.intoto.json")


def _registry_only(tmp_path: Path, name: str):
    d = tmp_path / name
    d.mkdir()
    for n in _BUNDLE:
        (d / n).write_bytes((V3 / n).read_bytes())
    reg = Ed25519PrivateKey.generate()
    regb64 = base64.b64encode(reg.public_key().public_bytes_raw()).decode()
    vsa_verifier.emit_vsa_verifier(str(d), None, regb64)
    return d, reg


def _signed_registry(reg, pin_b64):
    entry = {"template_name": "VERIFY_OFFLINE_PY",
             "template_sha256": "a" * 64, "nous_version": "7.0.0"}
    body = vr.build_registry([entry], verifier_pins=[
        {"verifier_id": "https://nous-lang.org/vsa/verifier/v1",
         "public_key_b64": pin_b64}])
    return vr.sign_registry(body, reg)


@pytest.mark.parametrize("case", ["missing", "forged", "valid"])
def test_s6_registry_only_vsa_verifier(tmp_path, case):
    d, reg = _registry_only(tmp_path, case)
    if case == "forged":
        doc = _signed_registry(reg, VSA_KEY)
        doc["signature"]["signature_b64"] = base64.b64encode(
            b"\0" * 64).decode()
        (d / "verifier-registry.json").write_text(json.dumps(doc))
    elif case == "valid":
        (d / "verifier-registry.json").write_text(
            json.dumps(_signed_registry(reg, VSA_KEY)))
    rc, so, se = _run(d, "verify_vsa_offline.py",
                      ["--expect-signer", VSA_KEY])
    want = 0 if case == "valid" else 1
    assert rc == want, (case, rc, so, se)


# ------------------------------------------------------------------ S7


@pytest.mark.parametrize("name", TEXT_NAMES)
def test_s7_broken_cryptography_is_environment(name, tmp_path):
    stub = tmp_path / "stub" / "cryptography"
    stub.mkdir(parents=True)
    (stub / "__init__.py").write_text("", encoding="utf-8")
    d = tmp_path / "run"
    d.mkdir()
    text = _texts()[name]
    args = _own_option_sets(text)[-1]
    if name in ("conformance.standalone", "builder.conformance_v2"):
        # real inputs and the right keys, so the run reaches the first
        # import of a cryptography submodule (empty inputs fail first)
        idx = json.loads((V3 / "index.json").read_text(encoding="utf-8"))
        keys = idx["vectorKeys"]
        for n in ("manifest.json", "trace.json", "conformance.json"):
            (d / n).write_bytes((V3 / n).read_bytes())
        args = ["--expect-signer", keys["certificatePubkeyB64"],
                "--expect-manifest-signer", keys["manifestPubkeyB64"]]
        if name == "builder.conformance_v2":
            args = ["--allow-unanchored"] + args
    if name == "vsa.template":
        # the raw template is unprovisioned (2 before any import); run
        # the provisioned text on the v3 bundle instead
        for n in _BUNDLE:
            (d / n).write_bytes((V3 / n).read_bytes())
        vsa_verifier.emit_vsa_verifier(str(d), VSA_KEY)
        text = (d / "verify_vsa_offline.py").read_text(encoding="utf-8")
    (d / "v.py").write_text(text, encoding="utf-8")
    for n in ("manifest.json", "conformance.json", "trace.json",
              "vsa.intoto.json"):
        if not (d / n).exists():
            (d / n).write_text("{}", encoding="utf-8")
    code = ("import runpy, sys\nsys.path.insert(0, %r)\n"
            "sys.argv = ['v.py'] + %r\n"
            "runpy.run_path('v.py', run_name='__main__')\n"
            % (str(stub.parent), args))
    p = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", code],
                       cwd=str(d), capture_output=True, text=True,
                       timeout=120)
    assert p.returncode == 2, (name, p.returncode, p.stdout, p.stderr)
    assert _last_line(p.stdout) == "CLASS: ENVIRONMENT", (name, p.stdout)


# ------------------------------------------------------------------ S8


def test_s8_predicate_signer_field_must_be_the_key(dated, tmp_path):
    path, priv, npub, _nkey = _ndec_of(tmp_path, PROVEN_SRC, "s8a")
    e = _entries(path)
    stmt = _statement(e)
    stmt["predicate"]["signer_public_key_b64"] = OTHER_PIN
    bad = _write(_resign(e, stmt, priv), tmp_path / "field.ndec")
    assert ndec.verify_ndec_file(bad, public_key=npub) == 1


def test_s8_keyid_must_be_sha256_of_the_key(dated, tmp_path):
    path, _priv, npub, _nkey = _ndec_of(tmp_path, PROVEN_SRC, "s8b")
    e = _entries(path)
    env = json.loads(e["attestation.intoto.json"])
    env["signatures"][0]["keyid"] = "0" * 64
    e["attestation.intoto.json"] = json.dumps(
        env, sort_keys=True, separators=(",", ":")).encode()
    bad = _write(e, tmp_path / "keyid.ndec")
    assert ndec.verify_ndec_file(bad, public_key=npub) == 1


# ------------------------------------------------------------------ S9


def test_s9_pass_blocks_do_not_claim_a_coverage_net(dated, tmp_path,
                                                    capsys):
    path, _priv, npub, nkey = _ndec_of(tmp_path, PROVEN_SRC, "s9")
    assert ndec.verify_ndec_file(path, public_key=npub) == 0
    out = capsys.readouterr().out
    assert "coverage of declared net" not in out, out
    rc, so, se = _carried(path, tmp_path / "x", ["--expect-signer", nkey])
    assert rc == 0, (rc, so, se)
    assert "coverage of declared net" not in so, so


def test_s9_docs_wording():
    annex = " ".join((REPO / "docs" / "ANNEX_IV_MAPPING.md").read_text(
        encoding="utf-8").split())
    assert "proves the cost-cap / coverage claim" not in annex
    cov = (REPO / "website" / "coverage.html").read_text(encoding="utf-8")
    i = cov.index("VERDICT: PASS\nNOT CLAIMED")
    assert cov.index("CLASS: PASS</pre>") > i


# ----------------------------------------------------------------- S10


@pytest.mark.parametrize("name", TEXT_NAMES)
def test_s10_usage_names_isolated_mode(name):
    text = _texts()[name]
    m = re.search(r"(?m)^Usage: (.*)$", text)
    assert m, name
    assert m.group(1).startswith("python3 -I "), (name, m.group(1))


# ------------------------------------------- S1c (after mutant VY17)


def test_s1c_planted_module_never_runs(dated, tmp_path, monkeypatch):
    # The refuted case of S1 is also caught by D10's verdict gate; this
    # one isolates D9: a proven .ndec, a planted module that only leaves
    # a mark. Run isolated, the mark never appears.
    mark = tmp_path / "planted_ran"
    monkeypatch.setenv("NT_PLANTED_MARK", str(mark))
    plant = (b"import os\np = os.environ.get('NT_PLANTED_MARK')\n"
             b"if p:\n    open(p, 'w').write('ran')\nos._exit(0)\n")
    path, _priv, npub, nkey = _ndec_of(tmp_path, PROVEN_SRC, "s1c")
    e = _entries(path)
    e["dossier/json.py"] = plant
    e["json.py"] = plant
    bad = _write(e, tmp_path / "planted.ndec")
    assert ndec.verify_ndec_file(bad, public_key=npub) == 0
    assert not mark.exists(), "installed path ran a planted module"
    rc, so, se = _carried(bad, tmp_path / "x", ["--expect-signer", nkey])
    assert rc == 0, (rc, so, se)
    assert not mark.exists(), "carried path ran a planted module"
