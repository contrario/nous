"""The Rekor leg of the cold audit, and index.json bound to the VSA.
__s485_cold_audit_rekor_test_v1__

FG-S485-AF: a stranger with the served release directory and the published
procedure could not reach the Rekor leg. Section 1.5 of
docs/VERIFYING_A_RELEASE.md now names the step, and cold_audit.py runs it as
the class "release-vsa-rekor". The trust root comes from Sigstore's TUF
repository through Sigstore's own client, never from nous-lang.org: a root
served beside the bundle would let whoever controls the origin replace both.

Measured on Server B (B11M, 11-21): sigstore-python writes its embedded
trusted_root.json at the TUF targets path BEFORE it refreshes, so the file is
there even when the update failed. The class must fail closed on the update's
exit code, not on the file's presence (T2).

Network is stubbed at the _fetch_all and _run seams; nothing here touches the
wire.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_PATH = REPO_ROOT / "scripts" / "cold_audit.py"
DOC_PATH = REPO_ROOT / "docs" / "VERIFYING_A_RELEASE.md"

V = "10.0.0"
WHEEL = "nous_lang-" + V + "-py3-none-any.whl"
SDIST = "nous_lang-" + V + ".tar.gz"
WHEEL_SHA = "4637f996a642fcd5c8e117bb27e0f68762dc2bb9290bb6a4c1d12fc8f1cf157c"
SDIST_SHA = "70a544a5959413edb1e26382cfe06bbd8f694c3f5095387eef44b688f3ee64fd"
BUNDLE = "nous_lang-" + V + ".rekor-v2-bundle.json"
PASS_OUT = "  CONVERGENCE: PASS\n    log_index:              208592459\n"
FAIL_OUT = "  CONVERGENCE: FAIL\n"


def _load():
    spec = importlib.util.spec_from_file_location("cold_audit", AUDIT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["cold_audit"] = module
    spec.loader.exec_module(module)
    return module


def _posix(data: bytes, name: str) -> bytes:
    return (hashlib.sha256(data).hexdigest() + "  " + name + "\n").encode("ascii")


def _vsa(wheel_sha: str = WHEEL_SHA) -> tuple[bytes, str]:
    st = {"subject": [{"name": WHEEL, "digest": {"sha256": wheel_sha}},
                      {"name": SDIST, "digest": {"sha256": SDIST_SHA}}]}
    payload = json.dumps(st, sort_keys=True).encode()
    env = {"payloadType": "application/vnd.in-toto+json",
           "payload": base64.b64encode(payload).decode(), "signatures": []}
    return (json.dumps(env) + "\n").encode(), hashlib.sha256(payload).hexdigest()


def _files(into: Path, *, idx_payload: str | None = None, idx_wheel_sha: str = WHEEL_SHA) -> None:
    vsa, psha = _vsa()
    (into / "build-vsa.intoto.json").write_bytes(vsa)
    (into / "build-vsa.intoto.json.sha256").write_bytes(_posix(vsa, "build-vsa.intoto.json"))
    b = (json.dumps({"transparency_log_entry": {"log_index": 208592459}}) + "\n").encode()
    (into / BUNDLE).write_bytes(b)
    (into / (BUNDLE + ".sha256")).write_bytes(_posix(b, BUNDLE))
    (into / "verify_build_vsa_offline.py").write_bytes(b"# stub\n")
    (into / "verify_build_vsa_offline.py.sha256").write_bytes(
        _posix(b"# stub\n", "verify_build_vsa_offline.py"))
    (into / "index.json").write_text(json.dumps({
        "version": V, "vsaPayloadSha256": idx_payload or psha,
        "artifacts": [{"kind": "wheel", "name": WHEEL, "sha256": idx_wheel_sha},
                      {"kind": "sdist", "name": SDIST, "sha256": SDIST_SHA}]}), encoding="utf-8")


class _Runner:
    """Stands in for _run. tuf_rc: the update's exit; pos/neg: (rc, stdout)
    of build-attest-verify on the served copy and on the tampered one."""

    def __init__(self, module, tuf_rc=0, pos=(0, PASS_OUT), neg=(1, FAIL_OUT)):
        self.m, self.tuf_rc, self.pos, self.neg = module, tuf_rc, pos, neg
        self.calls: list[list[str]] = []

    def __call__(self, argv, cwd, env=None):
        argv = [str(a) for a in argv]
        self.calls.append(argv)
        if argv[1:3] == ["-m", "venv"]:
            return 0, "", ""
        if "pip" in argv and "install" in argv:
            return 0, "", ""
        if argv[-2:] == ["plumbing", "update-trust-root"]:
            if self.tuf_rc == 0:
                d = Path(env["XDG_CACHE_HOME"]) / "sigstore-python" / "tuf" / \
                    "https%3A%2F%2Ftuf-repo-cdn.sigstore.dev"
                d.mkdir(parents=True, exist_ok=True)
                (d / "trusted_root.json").write_text("{}\n", encoding="utf-8")
            return self.tuf_rc, "", "tuf"
        if "build-attest-verify" in argv:
            bdir = argv[argv.index("--bundle-dir") + 1]
            rc, out = self.neg if Path(bdir).name == "neg" else self.pos
            return rc, out, ""
        raise AssertionError("unexpected call " + repr(argv))


def _rekor(module, tmp_path, monkeypatch, runner):
    monkeypatch.setattr(module, "_fetch_all", lambda base, names, into: _files(into))
    monkeypatch.setattr(module, "_run", runner)
    return module.audit_release_vsa_rekor(V, tmp_path)


def test_t1_the_rekor_class_is_audited() -> None:
    module = _load()
    assert "release-vsa-rekor" in module.CLASSES
    for name in ("release-vsa", "provenance", "vsa-vectors", "verifier-registry"):
        assert name in module.CLASSES


def test_t2_a_failed_tuf_update_fails_the_class_even_with_a_file_there(tmp_path, monkeypatch) -> None:
    """NEGATIVE CONTROL, measured on B: the seeded file is present after a failed
    update; its presence is not a TUF check."""
    module = _load()
    seeded = tmp_path / "cache" / "sigstore-python" / "tuf" / "https%3A%2F%2Ftuf-repo-cdn.sigstore.dev"
    seeded.mkdir(parents=True)
    (seeded / "trusted_root.json").write_text("{}\n", encoding="utf-8")
    runner = _Runner(module, tuf_rc=1)
    with pytest.raises(module.ColdAuditError, match="TUF"):
        _rekor(module, tmp_path, monkeypatch, runner)
    assert not any("build-attest-verify" in c for c in runner.calls)


def test_t3_rc0_without_convergence_pass_fails(tmp_path, monkeypatch) -> None:
    module = _load()
    with pytest.raises(module.ColdAuditError, match="CONVERGENCE: PASS"):
        _rekor(module, tmp_path, monkeypatch, _Runner(module, pos=(0, "  [PASS] something\n")))


def test_t4_a_tampered_copy_that_passes_fails_the_class(tmp_path, monkeypatch) -> None:
    """The control: a verifier that passes a bundle whose log_index moved is not
    checking the inclusion proof, and its PASS on the real bundle means nothing."""
    module = _load()
    with pytest.raises(module.ColdAuditError, match="NEGATIVE CONTROL"):
        _rekor(module, tmp_path, monkeypatch, _Runner(module, neg=(0, PASS_OUT)))


def test_t5_a_tampered_copy_that_errors_fails_the_class(tmp_path, monkeypatch) -> None:
    module = _load()
    with pytest.raises(module.ColdAuditError, match="NEGATIVE CONTROL"):
        _rekor(module, tmp_path, monkeypatch, _Runner(module, neg=(2, "")))


def test_t6_the_green_path(tmp_path, monkeypatch) -> None:
    module = _load()
    runner = _Runner(module)
    detail = _rekor(module, tmp_path, monkeypatch, runner)
    assert "CONVERGENCE: PASS" in detail and "FAIL" in detail
    neg = json.loads((tmp_path / "neg" / BUNDLE).read_text(encoding="utf-8"))
    assert neg["transparency_log_entry"]["log_index"] == 208592460
    tuf = [c for c in runner.calls if c[-2:] == ["plumbing", "update-trust-root"]]
    assert len(tuf) == 1


def _release_vsa(module, tmp_path, monkeypatch, **kw):
    monkeypatch.setattr(module, "_fetch_all", lambda base, names, into: _files(into, **kw))

    def no_run(*a, **k):
        raise AssertionError("the binding must refuse before anything runs")
    monkeypatch.setattr(module, "_run", no_run)
    return module.audit_release_vsa(V, tmp_path)


def test_t7_an_index_payload_not_the_vsas_fails(tmp_path, monkeypatch) -> None:
    module = _load()
    with pytest.raises(module.ColdAuditError, match="vsaPayloadSha256"):
        _release_vsa(module, tmp_path, monkeypatch, idx_payload="0" * 64)


def test_t8_an_index_wheel_not_the_vsas_fails(tmp_path, monkeypatch) -> None:
    module = _load()
    with pytest.raises(module.ColdAuditError, match="wheel"):
        _release_vsa(module, tmp_path, monkeypatch, idx_wheel_sha="1" * 64)


def test_t9_the_document_and_the_script_name_the_same_step() -> None:
    if not DOC_PATH.is_file():
        pytest.skip("docs/VERIFYING_A_RELEASE.md not in this checkout")
    module = _load()
    doc = DOC_PATH.read_text(encoding="utf-8")
    i = doc.index("### 1.5 ")
    sec = doc[i:doc.index("\n## ", i)]
    assert module.SIGSTORE_REQ in sec
    assert "plumbing update-trust-root" in sec
    assert module.TUF_TARGETS_SUBDIR in sec
    assert "build-attest-verify --bundle-dir rel --pins-dir" in sec
    assert "3.11" in sec
