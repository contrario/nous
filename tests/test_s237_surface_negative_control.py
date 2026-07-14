"""The negative control on the published surface -- in the script AND in the doc.
__s237_p2_surface_negative_control_v1__

S235 found nous-lang.org answering 200-with-the-homepage for every unresolved path
under /.well-known/. A mistyped version handed an auditor a web page where a signed
artifact belongs, and `curl -f` could not see it: -f fails on a 4xx and there was
no 4xx. The nginx carve-out fixed the server.

That fix was then re-checked exactly once per session, by a human remembering to
paste a curl into a terminal at RULE 0. A check that runs when someone remembers is
a snapshot of human vigilance, and the whole S234-S235-S236 arc is about what
happens to snapshots: the producer was never in the diff, so the next artifact was
wrong. This moves the control into the tool that runs the published procedure, so
it fires every time the procedure runs instead of every time a human recalls it.

TWO REQUIREMENTS, AND THE SECOND IS THE ONE PEOPLE GET WRONG.
  1. A 200 for a version that cannot exist is a HARD FAILURE. The surface is
     serving a page where an artifact belongs.
  2. Anything that is neither 200 nor 404 -- a timeout, a 5xx, a WAF block, a curl
     that cannot resolve DNS -- is INCONCLUSIVE, and inconclusive is NOT a pass. A
     control that goes green when the network is down is not a control. This is the
     failure mode that would quietly retire the check.

THE BOND. cold_audit.py runs the command docs/VERIFYING_A_RELEASE.md publishes.
Putting the control in the script and not the document would make the script run a
command no reader of the document would ever type -- FG-S235-A, in the tool built
to catch it. So it lands in BOTH, and the last two tests here hold them together.

AND IT MUST BE CALLED. OCSP_SKIPPED sits on this project's own outstanding list as
"defined, tested, NEVER EMITTED". A guard that exists and is never invoked checks
nothing, so test_main_actually_calls_the_preflight asserts the call by ast, and
test_the_preflight_aborts_before_any_class_is_audited asserts the abort by running
main() against a stubbed 200.

Network is stubbed at the subprocess seam; nothing here touches the wire.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_PATH = REPO_ROOT / "scripts" / "cold_audit.py"
DOC_PATH = REPO_ROOT / "docs" / "VERIFYING_A_RELEASE.md"


def _load():
    spec = importlib.util.spec_from_file_location("cold_audit_s237", AUDIT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["cold_audit_s237"] = module
    spec.loader.exec_module(module)
    return module


def test_the_impossible_version_cannot_exist() -> None:
    module = _load()
    assert module.IMPOSSIBLE_VERSION == "9.99.9"


def test_the_control_asks_for_a_release_vsa_index_that_cannot_exist() -> None:
    module = _load()
    seen: list[str] = []
    module._http_status = lambda url: seen.append(url) or 404
    module.preflight_negative_control()
    assert len(seen) == 1
    assert seen[0] == (
        "https://nous-lang.org/.well-known/nous/release-vsa/9.99.9/index.json"
    )


def test_a_404_is_the_pass() -> None:
    module = _load()
    module._http_status = lambda url: 404
    detail: str = module.preflight_negative_control()
    assert "404" in detail


def test_a_200_is_a_hard_failure() -> None:
    module = _load()
    module._http_status = lambda url: 200
    with pytest.raises(module.ColdAuditError) as exc:
        module.preflight_negative_control()
    message: str = str(exc.value)
    assert "200" in message
    assert "9.99.9" in message


def test_a_5xx_is_inconclusive_not_a_pass() -> None:
    module = _load()
    module._http_status = lambda url: 503
    with pytest.raises(module.ColdAuditError) as exc:
        module.preflight_negative_control()
    assert "INCONCLUSIVE" in str(exc.value), (
        "a 503 is not a 404; treating any non-200 as a pass is a control that "
        "goes green when the network is down"
    )


def test_a_403_is_inconclusive_not_a_pass() -> None:
    module = _load()
    module._http_status = lambda url: 403
    with pytest.raises(module.ColdAuditError) as exc:
        module.preflight_negative_control()
    assert "INCONCLUSIVE" in str(exc.value), (
        "Cloudflare 403s some user-agents on this very surface (FG-S235-B). A "
        "403 is a WAF verdict, not evidence the artifact is absent."
    )


def test_a_curl_failure_is_not_reported_as_a_status(monkeypatch) -> None:
    module = _load()

    class _Proc:
        returncode = 6
        stdout = ""
        stderr = "curl: (6) Could not resolve host: nous-lang.org"

    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: _Proc())
    with pytest.raises(module.ColdAuditError) as exc:
        module._http_status("https://nous-lang.org/whatever")
    assert "curl exited 6" in str(exc.value)


def test_main_actually_calls_the_preflight() -> None:
    tree = ast.parse(AUDIT_PATH.read_text(encoding="utf-8"))
    main_fn = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    called = {
        node.func.id
        for node in ast.walk(main_fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "preflight_negative_control" in called, (
        "main() does not call preflight_negative_control(). A control that is "
        "defined, tested and never invoked checks nothing -- that is the "
        "OCSP_SKIPPED defect, and this assertion exists to refuse it."
    )


def test_the_preflight_aborts_before_any_class_is_audited(monkeypatch) -> None:
    module = _load()
    audited: list[str] = []

    monkeypatch.setattr(module, "_http_status", lambda url: 200)
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/curl")
    monkeypatch.setattr(
        module, "audit_release_vsa",
        lambda v, w: audited.append("release-vsa") or "unreachable",
    )
    monkeypatch.setattr(
        module, "audit_provenance",
        lambda w: audited.append("provenance") or "unreachable",
    )
    monkeypatch.setattr(
        module, "audit_vsa_vectors",
        lambda w: audited.append("vsa-vectors") or "unreachable",
    )
    monkeypatch.setattr(
        module, "audit_verifier_registry",
        lambda w: audited.append("verifier-registry") or "unreachable",
    )
    monkeypatch.setattr(module.sys, "argv", ["cold_audit.py", "5.75.0"])

    rc: int = module.main()

    assert rc == 1, "a 200 on the negative control must fail the audit"
    assert audited == [], (
        "the surface failed its negative control and a class was audited "
        "anyway: " + repr(audited)
    )


def test_a_healthy_surface_still_audits(monkeypatch) -> None:
    module = _load()
    audited: list[str] = []

    monkeypatch.setattr(module, "_http_status", lambda url: 404)
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/curl")
    monkeypatch.setattr(
        module, "audit_verifier_registry",
        lambda w: audited.append("verifier-registry") or "stubbed",
    )
    monkeypatch.setattr(
        module.sys, "argv",
        ["cold_audit.py", "5.75.0", "--only", "verifier-registry"],
    )

    rc: int = module.main()

    assert rc == 0, "a 404 on the negative control must not block the audit"
    assert audited == ["verifier-registry"], (
        "the preflight passed but the selected class was never audited"
    )


def test_the_document_publishes_the_same_negative_control() -> None:
    doc: str = DOC_PATH.read_text(encoding="utf-8")
    assert "9.99.9" in doc, (
        "the document does not publish the negative control the script runs. A "
        "script that runs a command no reader of the document would type is "
        "FG-S235-A."
    )
    assert "%{http_code}" in doc
    assert "404" in doc


def test_the_document_names_the_inconclusive_case() -> None:
    doc: str = DOC_PATH.read_text(encoding="utf-8")
    assert "INCONCLUSIVE" in doc, (
        "the document must say that anything other than 404 or 200 is NOT a "
        "pass. A reader who treats a timeout as green has no control at all."
    )
