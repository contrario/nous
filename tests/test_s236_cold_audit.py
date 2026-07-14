"""Lock test for scripts/cold_audit.py.  __s236_p4_cold_audit_lock_test_v1__

cold_audit.py is named as step 7 of the release ceremony and runs the procedure
docs/VERIFYING_A_RELEASE.md publishes. It is NOT a release gate -- deliberately,
and it must never become one -- so nothing breaks if it rots. That is exactly
why it needs a lock test: a silently-broken cold audit means the post-publish
check stops being run, and nobody finds out until an auditor does.

Its two semantic guards (S235) are the load-bearing part and are reproduced here
as negative controls:

  1. AN HTML BODY IS REJECTED OUTRIGHT. nous-lang.org served 200-with-the-
     homepage for every missing artifact path, and `curl -f` cannot see it:
     -f fails on 4xx and there is no 4xx. The nginx =404 carve-out fixed the
     server; it lives only on Server A's filesystem, so the TOOL must not trust
     the surface either.
  2. index.json MUST RECORD THE VERSION REQUESTED, or the bundle fetched is not
     the bundle asked for.

And the S233 sidecar defect, which the cold path is the last line against: a
bare-hex sidecar makes `sha256sum -c` refuse the file BEFORE it can report the
digest mismatch, so the format defect conceals the integrity defect. A refusal
to run is not a pass.

Network is stubbed at the subprocess seam; nothing here touches the wire.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_PATH = REPO_ROOT / "scripts" / "cold_audit.py"
RELEASE_PATH = REPO_ROOT / "scripts" / "release.py"
DOC_PATH = REPO_ROOT / "docs" / "VERIFYING_A_RELEASE.md"

ALIAS = "build-vsa.intoto.json"
STALE_SHA = "b5af4d0532959be530ec2b89a0c86270dd185a7d919ff3d6c8eb43cb80212e7e"


def _load():
    spec = importlib.util.spec_from_file_location("cold_audit", AUDIT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["cold_audit"] = module
    spec.loader.exec_module(module)
    return module


def _posix(data: bytes, name: str) -> bytes:
    return (hashlib.sha256(data).hexdigest() + "  " + name + "\n").encode("ascii")


def test_audit_script_exists() -> None:
    assert AUDIT_PATH.is_file(), "scripts/cold_audit.py is release ceremony step 7"


def test_it_fetches_the_alias_the_verifier_actually_reads() -> None:
    """The bond to S236. The offline verifier reads exactly one filename; if
    the audit stops fetching it, the audit stops testing what a stranger runs."""
    module = _load()
    assert ALIAS in module.RELEASE_VSA_FILES
    assert ALIAS + ".sha256" in module.RELEASE_VSA_FILES


def test_all_four_published_classes_are_audited() -> None:
    module = _load()
    for name in ("release-vsa", "provenance", "vsa-vectors", "verifier-registry"):
        assert name in module.CLASSES


def test_a_conformant_sidecar_passes(tmp_path: Path) -> None:
    """POSITIVE CONTROL. A correct sidecar must be accepted, or the predicate
    always fires and checks nothing."""
    module = _load()
    body = b'{"ok":true}\n'
    (tmp_path / ALIAS).write_bytes(body)
    (tmp_path / (ALIAS + ".sha256")).write_bytes(_posix(body, ALIAS))
    module._check_sidecar(tmp_path / (ALIAS + ".sha256"))


def test_the_s233_bare_hex_sidecar_is_rejected(tmp_path: Path) -> None:
    """NEGATIVE CONTROL, and the reproducer. `sha256sum -c` errors out on this
    shape BEFORE it can compare the digest -- the format defect concealing the
    integrity defect. The audit must name the format, not fall silent."""
    module = _load()
    (tmp_path / ALIAS).write_bytes(b'{"ok":true}\n')
    (tmp_path / (ALIAS + ".sha256")).write_bytes((STALE_SHA + "\n").encode("ascii"))
    with pytest.raises(module.ColdAuditError, match="POSIX"):
        module._check_sidecar(tmp_path / (ALIAS + ".sha256"))


def test_a_digest_mismatch_is_rejected(tmp_path: Path) -> None:
    """The defect the format bug was HIDING."""
    module = _load()
    (tmp_path / ALIAS).write_bytes(b'{"ok":true}\n')
    (tmp_path / (ALIAS + ".sha256")).write_bytes(
        (STALE_SHA + "  " + ALIAS + "\n").encode("ascii")
    )
    with pytest.raises(module.ColdAuditError, match="mismatch"):
        module._check_sidecar(tmp_path / (ALIAS + ".sha256"))


def test_a_sidecar_naming_an_absent_file_is_rejected(tmp_path: Path) -> None:
    module = _load()
    (tmp_path / (ALIAS + ".sha256")).write_bytes(_posix(b"x", ALIAS))
    with pytest.raises(module.ColdAuditError, match="not present"):
        module._check_sidecar(tmp_path / (ALIAS + ".sha256"))


def test_a_non_ascii_sidecar_is_rejected(tmp_path: Path) -> None:
    """FG-S235-F: the 9.99.9 control first failed HERE, by luck, because the
    homepage happens to contain non-ASCII. A check that fires for a reason you
    did not design is a second defect announcing itself -- but the predicate
    itself is real and must stay."""
    module = _load()
    (tmp_path / (ALIAS + ".sha256")).write_bytes(b"\xff\xfe not ascii\n")
    with pytest.raises(module.ColdAuditError, match="ASCII"):
        module._check_sidecar(tmp_path / (ALIAS + ".sha256"))


def test_an_html_body_is_rejected_outright(tmp_path: Path, monkeypatch) -> None:
    """NEGATIVE CONTROL for FG-S235-E, the defect only the negative control
    found. A 200 carrying a web page means the path does not exist and an SPA
    fallback served index.html. `curl -f` cannot catch it. The server is fixed;
    the tool must not depend on that."""
    module = _load()
    dest = tmp_path / "index.json"

    class _Proc:
        returncode = 0
        stderr = ""

    class _FakeSubprocess:
        @staticmethod
        def run(argv, **kwargs):
            dest.write_bytes(b"<!DOCTYPE html>\n<html><head><title>NOUS</title>\n")
            return _Proc()

    monkeypatch.setattr(module, "subprocess", _FakeSubprocess)
    with pytest.raises(module.ColdAuditError, match="HTML PAGE"):
        module._fetch("https://nous-lang.org/whatever", dest)


def test_a_curl_failure_is_not_swallowed(tmp_path: Path, monkeypatch) -> None:
    module = _load()

    class _Proc:
        returncode = 22
        stderr = "404"

    class _FakeSubprocess:
        @staticmethod
        def run(argv, **kwargs):
            return _Proc()

    monkeypatch.setattr(module, "subprocess", _FakeSubprocess)
    with pytest.raises(module.ColdAuditError, match="curl exited 22"):
        module._fetch("https://nous-lang.org/9.99.9/index.json", tmp_path / "x")


def test_index_must_record_the_version_requested(tmp_path: Path, monkeypatch) -> None:
    """NEGATIVE CONTROL. An auditor pointed at a mirror, a proxy, or a future
    misconfiguration must not be handed a different bundle than the one asked
    for, however healthy the 200 looks."""
    module = _load()
    body = b'{"payloadType":"application/vnd.in-toto+json"}\n'

    def fake_fetch_all(base, names, into):
        (into / ALIAS).write_bytes(body)
        (into / (ALIAS + ".sha256")).write_bytes(_posix(body, ALIAS))
        (into / "verify_build_vsa_offline.py").write_bytes(b"# stub\n")
        (into / "verify_build_vsa_offline.py.sha256").write_bytes(
            _posix(b"# stub\n", "verify_build_vsa_offline.py")
        )
        (into / "index.json").write_text(
            json.dumps({"version": "9.99.9", "artifacts": []}), encoding="utf-8"
        )

    monkeypatch.setattr(module, "_fetch_all", fake_fetch_all)
    with pytest.raises(module.ColdAuditError, match="not the bundle asked for"):
        module.audit_release_vsa("5.75.0", tmp_path)


def test_it_is_not_a_release_phase() -> None:
    """A phase that can never run is a lie: at release time the VSA is not
    minted and the wheel is not on PyPI, so a release-time cold audit could
    only pass by CONSTRUCTING ITS OWN INPUT -- the exact defect it exists to
    catch. It is named in the ceremony and invoked by NO phase."""
    release = RELEASE_PATH.read_text(encoding="utf-8")
    assert "__s235_p4_ceremony_cold_audit_v1__" in release
    assert "cold_audit.py" in release
    assert "def phase_cold_audit" not in release


def test_the_document_and_the_script_run_the_same_command() -> None:
    """FG-S235-A. The first draft fetched with urllib where the doc said curl,
    and failed 4/4 against a surface that was entirely healthy. A check whose
    input is fetched differently from the consumer's is not a check of what the
    consumer holds.

    This asserts on the IMPORTS and CALLS, not on the string 'urllib'. The
    script's own docstring records the Cloudflare WAF finding by name, and a
    predicate that flags the sentence explaining its own rule is the defect
    claim_lint's mention exemption exists to prevent. FG-S236-A: I wrote that
    defect into the first draft of this test."""
    if not DOC_PATH.is_file():
        pytest.skip("docs/VERIFYING_A_RELEASE.md not in this checkout")
    src = AUDIT_PATH.read_text(encoding="utf-8")
    assert '"curl", "-fsSL"' in src, "the audit must fetch with the documented curl"
    assert "curl" in DOC_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("urllib"), (
                    "the audit imports urllib; it must fetch with the command "
                    "the document tells a stranger to type"
                )
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("urllib"), (
                "the audit imports from urllib; it must fetch with curl"
            )
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            assert name != "urlopen", "the audit must not call urlopen"
