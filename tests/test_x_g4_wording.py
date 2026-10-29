"""X-G4 -- the wording slice of FG-S415-X and the lint that holds it.

X_INNOVATION_GATE.md 3.5 and XD4: on this leg's text, a sentence that
says a signature is "authentic", an "author signature" or a "verified
identity" must name its scope in the same sentence (the key the artifact
carries, the expected key, --expect-signer, or that who holds the key is
established out of band). claims.toml [signer] declares the convention;
scripts/claim_lint.py predicate_signer checks it on [signer].paths only.

The lint is blind to prose inside a template's own string literals (it
reads them as quoted mentions) and to a negator that negates something
else nearby. W6 to W8 hold those surfaces directly.

# __x_g4_wording_tests_v1__
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from _v3pin import conformance_pin_args  # __nt_v3_classes_tests_v1__
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parent.parent
LINT = REPO / "scripts" / "claim_lint.py"
CLAIMS = REPO / "claims.toml"
_VEC = REPO / "examples" / "demos" / "cert-4679350"
_NEW_SCOPE = "signed by the --expect-signer key"  # __nt_v3_classes_tests_v1__


def _lint_module():
    spec = importlib.util.spec_from_file_location("claim_lint_x_g4", LINT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["claim_lint_x_g4"] = mod
    spec.loader.exec_module(mod)
    return mod


def _lint_tree(tmp_path: Path, rel: str, text: str, capsys) -> list[dict]:
    root = tmp_path / "root"
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    shutil.copy(CLAIMS, tmp_path / "claims.toml")
    mod = _lint_module()
    mod.main([
        "--config", str(tmp_path / "claims.toml"),
        "--root", str(root), "--json", "--no-allowlist",
    ])
    return json.loads(capsys.readouterr().out)["violations"]


def test_w1_unscoped_term_in_scoped_path(tmp_path: Path, capsys) -> None:
    viols = _lint_tree(
        tmp_path, "conformance.py",
        '"""The verdict is authentic and bound to these artifacts."""\n',
        capsys,
    )
    assert [v["predicate"] for v in viols] == ["signer"]


def test_w2_scoped_term_passes(tmp_path: Path, capsys) -> None:
    viols = _lint_tree(
        tmp_path, "conformance.py",
        '"""The verdict is authentic under the key it carries."""\n',
        capsys,
    )
    assert viols == []


def test_w3_quoted_mention_passes(tmp_path: Path, capsys) -> None:
    viols = _lint_tree(
        tmp_path, "conformance.py",
        '"""The old wording said "authentic" and was corrected."""\n',
        capsys,
    )
    assert viols == []


def test_w4_unscoped_path_not_checked(tmp_path: Path, capsys) -> None:
    viols = _lint_tree(
        tmp_path, "unrelated_module.py",
        '"""The verdict is authentic and bound to these artifacts."""\n',
        capsys,
    )
    assert viols == []


def test_w5_live_tree_clean_and_signer_declared(capsys) -> None:
    mod = _lint_module()
    cfg = mod.load_config(CLAIMS)
    assert cfg.signer_terms and "conformance.py" in cfg.signer_paths
    rc = mod.main(["--config", str(CLAIMS), "--root", str(REPO), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["violations"] == []
    assert payload["allowlist_used"] == []
    assert payload["allowlist_stale"] == []


def _emit(tmp_path: Path, anchored: bool) -> Path:
    from conformance_verifier import emit_conformance_verifier

    d = tmp_path / ("anchored" if anchored else "unanchored")
    d.mkdir()
    for name in ("conformance.json", "trace.json", "manifest.json"):
        shutil.copy(_VEC / name, d / name)
    return emit_conformance_verifier(str(d), anchored=anchored)


def test_w6_unanchored_default_stdout_scoped(tmp_path: Path) -> None:
    script = _emit(tmp_path, False)
    r = subprocess.run(
        [sys.executable, "-I", script.name]
        + conformance_pin_args(script.parent), cwd=str(script.parent),
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert "authentic" not in r.stdout.lower()
    assert _NEW_SCOPE in r.stdout


def test_w7_anchored_file_scoped(tmp_path: Path) -> None:
    text = " ".join(_emit(tmp_path, True).read_text(encoding="utf-8").split())
    assert "authenticity" not in text
    assert _NEW_SCOPE in text


def test_w8_dossier_v2_summary_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    import nous_api_server as srv

    monkeypatch.setattr(srv.limiter, "enabled", False)
    r = TestClient(srv.app).post("/v1/verify-dossier", json={
        "manifest_json": (_VEC / "manifest.json").read_text(encoding="utf-8"),
        "policy": {"require_anchor": False},
    })
    hr = r.json()["human_readable"]
    assert "embedded key" in hr["verdict_summary"]
    assert "author signature" not in hr["verdict_summary"]
    assert "holder of the embedded public" in hr["trust_explanation"]


def test_w9_runtime_conformance_doc() -> None:
    text = (REPO / "docs" / "RUNTIME_CONFORMANCE.md").read_text(encoding="utf-8")
    flat = " ".join(text.split())
    assert "--expect-signer" in flat
    assert "verdict is authentic" not in flat
    assert "signed-statement guarantee" not in flat


def test_w10_blog_rescoped_with_errata() -> None:
    text = (REPO / "website" / "blog" / "index.html").read_text(encoding="utf-8")
    for retired in (
        "trace is authentic",
        "verdict is authentic",
        "checks authenticity and binding",
    ):
        assert retired not in text
    assert text.count("Erratum (25 Oct 2026)") == 2
