"""S120 unit (b): chain-walk verifier end-to-end tests.

Builds a real re-binding dossier through the real producer (cmd_verify
--smt --supersedes) and patched build_dossier, then runs the EMITTED
verify_offline.py (VERIFY_OFFLINE_PY_CHAIN) as a subprocess:

  - depth-1 re-binding dossier emits the chain verifier and it PASSes
  - depth-2 likewise
  - tampering a chain link's prior_digest is caught (FAIL, exit 1)
  - build-time refuses chain + rekor anchor

The verifier runs with cryptography + stdlib only, zero issuer trust.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cli_verify import cmd_verify
from dossier import DossierError, build_dossier

TEMPLATE = Path(__file__).resolve().parent.parent / (
    "aml_transaction_governance.nous"
)


def _produce(
    tmp_path: Path,
    *,
    source_bytes: bytes,
    supersedes: str | None = None,
) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    src = tmp_path / "source.nous"
    src.write_bytes(source_bytes)
    mout = tmp_path / "source.manifest.json"

    class Args:
        file = str(src)
        smt = True
        prices = None
        timeout_ms = 30000
        no_manifest = False
        manifest_out = str(mout)
        key_path = str(tmp_path / "signing.key")
        smt_margin = 0
        coverage_threshold = "amount > 10000"
        no_lint = True
        lint_strict = False
        lint_error_on = None

    Args.supersedes = supersedes
    rc = cmd_verify(Args())
    assert rc == 0
    return src, mout


def _genesis(tmp_path: Path) -> tuple[Path, Path]:
    return _produce(tmp_path, source_bytes=TEMPLATE.read_bytes())


def _child(
    tmp_path: Path, predecessor_manifest: Path, marker: bytes
) -> tuple[Path, Path]:
    return _produce(
        tmp_path,
        source_bytes=TEMPLATE.read_bytes() + marker,
        supersedes=str(predecessor_manifest),
    )


def _run_verifier(dossier_dir: Path) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(
        [sys.executable, str(dossier_dir / "verify_offline.py")],
        capture_output=True,
        text=True,
        cwd=str(dossier_dir),
    )


def _emits_chain_verifier(dossier_dir: Path) -> bool:
    text = (dossier_dir / "verify_offline.py").read_text(encoding="utf-8")
    return "envelope-binding chain" in text and "_walk_chain" in text


def test_depth1_emits_chain_verifier_and_passes(tmp_path: Path) -> None:
    g = tmp_path / "g"
    gsrc, gmout = _genesis(g)
    out0 = tmp_path / "d0"
    build_dossier(gsrc, manifest=gmout, output=out0)

    c = tmp_path / "c"
    csrc, cmout = _child(c, gmout, b"\n# rebind v1\n")
    out1 = tmp_path / "d1"
    build_dossier(csrc, manifest=cmout, output=out1, supersedes=out0)

    assert _emits_chain_verifier(out1)
    proc = _run_verifier(out1)
    assert proc.returncode == 0, (
        "stdout=" + proc.stdout + " stderr=" + proc.stderr
    )
    assert "VERDICT: PASS" in proc.stdout
    assert "chain walk verified: 1 prior link" in proc.stdout


def test_depth2_chain_verifier_passes(tmp_path: Path) -> None:
    g = tmp_path / "g"
    gsrc, gmout = _genesis(g)
    out0 = tmp_path / "d0"
    build_dossier(gsrc, manifest=gmout, output=out0)

    c1 = tmp_path / "c1"
    c1src, c1mout = _child(c1, gmout, b"\n# rebind v1\n")
    out1 = tmp_path / "d1"
    build_dossier(c1src, manifest=c1mout, output=out1, supersedes=out0)

    c2 = tmp_path / "c2"
    c2src, c2mout = _child(c2, c1mout, b"\n# rebind v2\n")
    out2 = tmp_path / "d2"
    build_dossier(c2src, manifest=c2mout, output=out2, supersedes=out1)

    assert _emits_chain_verifier(out2)
    proc = _run_verifier(out2)
    assert proc.returncode == 0, (
        "stdout=" + proc.stdout + " stderr=" + proc.stderr
    )
    assert "chain walk verified: 2 prior link" in proc.stdout


def test_tampered_chain_link_caught(tmp_path: Path) -> None:
    g = tmp_path / "g"
    gsrc, gmout = _genesis(g)
    out0 = tmp_path / "d0"
    build_dossier(gsrc, manifest=gmout, output=out0)

    c = tmp_path / "c"
    csrc, cmout = _child(c, gmout, b"\n# rebind v1\n")
    out1 = tmp_path / "d1"
    build_dossier(csrc, manifest=cmout, output=out1, supersedes=out0)

    link = out1 / "chain" / "000_manifest.json"
    doc = json.loads(link.read_text(encoding="utf-8"))
    doc["source_sha256"] = "f" * 64
    link.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    proc = _run_verifier(out1)
    assert proc.returncode == 1
    assert (
        "signature does NOT verify" in proc.stderr
        or "chain broken" in proc.stderr
    )


def test_chain_plus_rekor_refused_at_build(tmp_path: Path) -> None:
    g = tmp_path / "g"
    gsrc, gmout = _genesis(g)
    out0 = tmp_path / "d0"
    build_dossier(gsrc, manifest=gmout, output=out0)

    c = tmp_path / "c"
    csrc, cmout = _child(c, gmout, b"\n# rebind v1\n")
    out1 = tmp_path / "d1"
    with pytest.raises(DossierError, match="chain . rekor anchor not yet"):
        build_dossier(
            csrc,
            manifest=cmout,
            output=out1,
            supersedes=out0,
            anchor="rekor",
        )
