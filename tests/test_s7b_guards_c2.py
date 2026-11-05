"""S7b C2 with H6 and H7: the gap witness writer (cli_verify.
_issue_gap_witness_dossier) refuses, before any key, signature or
file, a witness its own emitted offline verifier would refuse, and a
G1 refusal reaches the CLI as "REFUSED: <reason>", exit 1 (G4).

F2 is a failpoint at G1. F23 is a differential corpus run through the
real path: cmd_verify issues; when it issues, build_dossier packages
and the EMITTED verify_offline.py checks it by subprocess. An input
the writer accepts must verify (exit 3, a verified refutation); an
input the verifier would refuse must be refused by the writer, with
the verifier's first failing check. Every key is made under tmp_path.
Predictions: S7C2_PREDICTIONS.txt (seat S457). These tests evidence
the writer-reader agreement on this corpus; they do not prove it for
every input.
# __s7b_c2_tests_v1__
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from _v3pin import manifest_signer_args
from conformance_verifier import StrictJsonError

pytestmark = pytest.mark.usefixtures("dated_shipped_prices")

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "aml_transaction_governance.nous"
NL = chr(10)


class _Args:
    smt = True
    prices = None
    timeout_ms = 30000
    no_manifest = False
    smt_margin = 0
    no_lint = True
    lint_strict = False
    lint_error_on = None
    supersedes = None
    chain_coverage = None
    gap_witness = True
    coverage_threshold = None

    def __init__(self, **over):
        for k, v in over.items():
            setattr(self, k, v)


def _issue(tmp_path, threshold, capsys):
    import cli_verify
    src = tmp_path / "source.nous"
    src.write_bytes(TEMPLATE.read_bytes())
    mout = tmp_path / "source.manifest.json"
    key = tmp_path / "signing.key"
    args = _Args(file=str(src), manifest_out=str(mout), key_path=str(key),
                 coverage_threshold=threshold)
    rc = cli_verify.cmd_verify(args)
    err = capsys.readouterr().err
    return src, mout, key, rc, err


def _verify_offline(tmp_path, src, mout):
    from dossier import build_dossier
    out = tmp_path / "out"
    build_dossier(src, manifest=mout, output=out)
    return subprocess.run(
        [sys.executable, str(out / "verify_offline.py")]
        + manifest_signer_args(out),
        capture_output=True, text=True, cwd=str(out))


def _refused(rc, err, needles):
    assert "Traceback" not in err, err[-600:]
    lines = [ln for ln in err.splitlines() if ln.startswith("REFUSED: ")]
    assert lines, "no REFUSED line; rc %r; stderr %r" % (rc, err[-600:])
    for n in needles:
        assert n in lines[0], lines[0]
    assert rc == 1, "rc %r; stderr %r" % (rc, err[-600:])


ACCEPT = {
    "A1": "amount > 5000",
    "A2": "amount > 5000" + NL,
    "A3": "amount >= 6000",
    "A4": "amount  >  5000",
    "A5": "(amount > 5000)",
}
REDERIVE = ("does not re-derive offline", "unsupported character '#'")
REFUSE = {
    "R1": ("amount > 5000 # note" + NL, REDERIVE),
    "R2": ("amount > 5000 #" + chr(0xFFFE) + NL, ("[js:w.gw.1]",)),
    "R3": ("amount > 5000 #" + chr(0xDC80) + NL, ("[js:w.gw.1]",)),
    "R4": ("amount > 5000 #" + chr(0xE9) + NL, REDERIVE),
}


def test_f2_g1_failpoint_refused(tmp_path, monkeypatch, capsys):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    import manifest
    real = manifest._s7b_loads

    def fake(raw, lab):
        if "[js:w.man.1]" in lab:
            raise StrictJsonError(lab + ": failpoint")
        return real(raw, lab)
    monkeypatch.setattr(manifest, "_s7b_loads", fake)
    src, mout, key, rc, err = _issue(tmp_path, "amount > 5000", capsys)
    _refused(rc, err, ("[js:w.man.1]",))
    assert not mout.exists()
    assert not (tmp_path / "coverage.gapwitness.json").exists()


@pytest.mark.parametrize("cid", sorted(ACCEPT))
def test_f23_accept_issues_and_verifies(cid, tmp_path, capsys):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src, mout, key, rc, err = _issue(tmp_path, ACCEPT[cid], capsys)
    assert rc == 0, err[-600:]
    p = _verify_offline(tmp_path, src, mout)
    assert p.returncode == 3, p.stdout[-600:] + p.stderr[-300:]
    assert "VERDICT: REFUTATION" in p.stdout


@pytest.mark.parametrize("cid", sorted(REFUSE))
def test_f23_refuse_what_the_verifier_refuses(cid, tmp_path, capsys):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    threshold, needles = REFUSE[cid]
    src, mout, key, rc, err = _issue(tmp_path, threshold, capsys)
    if rc == 0:
        p = _verify_offline(tmp_path, src, mout)
        pytest.fail("issued (rc 0); the emitted verifier exits %d: %s"
                    % (p.returncode, p.stdout.strip().splitlines()[-1:]))
    _refused(rc, err, needles)
    assert not mout.exists()
    assert not (tmp_path / "coverage.gapwitness.json").exists()
    assert not key.exists()
