# __s485_convergence_pins_test_v1__
"""S485 DOCS2 (FG-S481-R): the dual-root convergence verifier reads a
release-vsa directory as it is served, and picks the Rekor v2 log key by
the checkpoint's own origin.

A served directory carries nous_lang-<v>.rekor-v2-bundle.json, not the
canonical rekor-v2-bundle.json, and no tsa_chain.pem; the TSA root is the
last certificate of the trusted root's timestampAuthorities chain. A
trusted root that lists more than one PKIX_ED25519 tlog no longer has its
last one taken: the key is the one whose baseUrl host is the checkpoint
origin, and an ambiguous root is refused.
"""
from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

import cli_verify_release
import rekor_v2_offline

REPO = Path(__file__).resolve().parent.parent
RELVSA = REPO / "website" / ".well-known" / "nous" / "release-vsa"
SERVED = RELVSA / "5.60.1"
TR_SRC = REPO / "tests" / "fixtures" / "rekor_v2" / "trusted_root.json"
TSA_SRC = REPO / "tests" / "fixtures" / "rekor_v2" / "tsa_chain.pem"
ORIGIN = "log2025-1.rekor.sigstore.dev"

pytestmark = pytest.mark.skipif(
    not (SERVED.is_dir() and TR_SRC.is_file() and TSA_SRC.is_file()),
    reason="the served 5.60.1 dir or the rekor_v2 fixtures absent",
)


def _served(dst: Path, src: Path = SERVED) -> Path:
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.iterdir():
        if f.is_file():
            shutil.copy(f, dst / f.name)
    return dst


def _root(extra: dict | None = None, before: bool = False, tsa: bool = True) -> dict:
    t = json.loads(TR_SRC.read_text(encoding="utf-8"))
    if extra is not None:
        i = [k for k, x in enumerate(t["tlogs"]) if x.get("baseUrl") == "https://" + ORIGIN][0]
        t["tlogs"].insert(i if before else i + 1, extra)
    if not tsa:
        t.pop("timestampAuthorities", None)
    return t


def _tlog(host: str) -> dict:
    der = Ed25519PrivateKey.generate().public_key().public_bytes(
        Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    return {
        "baseUrl": "https://" + host,
        "hashAlgorithm": "SHA2_256",
        "publicKey": {"rawBytes": base64.b64encode(der).decode(),
                      "keyDetails": "PKIX_ED25519",
                      "validFor": {"start": "2099-01-01T00:00:00Z"}},
        "logId": {"keyId": base64.b64encode(hashlib.sha256(der).digest()).decode()},
    }


def _pins(d: Path, root: dict | None = None, tsa: bool = True) -> Path:
    (d / "trusted_root.json").write_text(json.dumps(root if root is not None else _root()),
                                         encoding="utf-8")
    if tsa:
        shutil.copy(TSA_SRC, d / "tsa_chain.pem")
    return d


def _canon(d: Path) -> Path:
    """Stage the canonical bundle name, so the test reads its own subject
    and not the version-named fallback."""
    shutil.copy(d / "nous_lang-5.60.1.rekor-v2-bundle.json", d / "rekor-v2-bundle.json")
    return d


def _detail(r: dict) -> str:
    return " ".join(str(v.get("detail")) for v in r["legs"].values())


def test_X01_the_served_files_verify_with_pins_beside(tmp_path):
    d = _pins(_served(tmp_path / "d"))
    assert not (d / "rekor-v2-bundle.json").exists()
    r = cli_verify_release.verify_convergence(d)
    assert r["convergence"] == "PASS", r
    assert r["evidence"]["log_index"] == 5272998


def test_X02_two_version_named_bundles_are_refused(tmp_path):
    d = _pins(_served(tmp_path / "d"))
    shutil.copy(d / "nous_lang-5.60.1.rekor-v2-bundle.json",
                d / "nous_lang-0.0.0.rekor-v2-bundle.json")
    with pytest.raises(cli_verify_release.ConvergenceInputError, match="more than one"):
        cli_verify_release.verify_convergence(d)


def test_X03_the_canonical_bundle_is_read_first(tmp_path):
    d = _pins(_served(tmp_path / "d"))
    shutil.copy(d / "nous_lang-5.60.1.rekor-v2-bundle.json", d / "rekor-v2-bundle.json")
    (d / "nous_lang-5.60.1.rekor-v2-bundle.json").write_text("not json", encoding="utf-8")
    r = cli_verify_release.verify_convergence(d)
    assert r["convergence"] == "PASS", r


def test_X04_no_tsa_chain_takes_the_root_from_the_trusted_root(tmp_path):
    d = _canon(_pins(_served(tmp_path / "d"), tsa=False))
    assert not (d / "tsa_chain.pem").exists()
    r = cli_verify_release.verify_convergence(d)
    assert r["convergence"] == "PASS", r
    assert r["legs"]["root2_rfc3161_timestamp"]["status"] == "PASS"


def test_X05_no_tsa_chain_and_no_timestamp_authorities_fails(tmp_path):
    d = _canon(_pins(_served(tmp_path / "d"), root=_root(tsa=False), tsa=False))
    r = cli_verify_release.verify_convergence(d)
    assert r["convergence"] == "FAIL"
    assert "timestampAuthorities" in _detail(r)


def test_X06_a_later_ed25519_tlog_does_not_displace_the_origin(tmp_path):
    d = _canon(_pins(_served(tmp_path / "d"), root=_root(_tlog("log2099-1.rekor.example"))))
    r = cli_verify_release.verify_convergence(d)
    assert r["convergence"] == "PASS", r


def test_X07_two_ed25519_tlogs_for_one_origin_are_refused(tmp_path):
    d = _canon(_pins(_served(tmp_path / "d"), root=_root(_tlog(ORIGIN))))
    r = cli_verify_release.verify_convergence(d)
    assert r["convergence"] == "FAIL"
    assert "more than one" in _detail(r)


def test_X08_load_pins_without_origin_refuses_two_ed25519_tlogs(tmp_path):
    _pins(tmp_path, root=_root(_tlog("log2099-1.rekor.example")))
    with pytest.raises(rekor_v2_offline.VerificationError, match="more than one"):
        rekor_v2_offline.load_pins(tmp_path)


def test_X09_load_pins_with_the_origin_takes_its_key(tmp_path):
    root = _root(_tlog("log2099-1.rekor.example"))
    _pins(tmp_path, root=root)
    want = [t for t in root["tlogs"] if t["baseUrl"] == "https://" + ORIGIN][0]
    pins = rekor_v2_offline.load_pins(tmp_path, origin=ORIGIN)
    assert pins.log_key_id == base64.b64decode(want["logId"]["keyId"])


def test_X10_the_cli_on_the_served_files_and_one_pin(tmp_path):
    d = _pins(_served(tmp_path / "d"), tsa=False)
    proc = subprocess.run(
        [sys.executable, "-m", "cli", "build-attest-verify", "--bundle-dir", str(d)],
        cwd=str(REPO), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "CONVERGENCE: PASS" in proc.stdout


def test_X11_every_served_release_dir_verifies_as_served(tmp_path):
    dirs = sorted(p for p in RELVSA.iterdir() if p.is_dir())
    assert len(dirs) >= 39
    bad = []
    for src in dirs:
        d = _pins(_served(tmp_path / src.name, src), tsa=False)
        r = cli_verify_release.verify_convergence(d)
        if r["convergence"] != "PASS":
            bad.append((src.name, _detail(r)[:160]))
    assert not bad, bad
