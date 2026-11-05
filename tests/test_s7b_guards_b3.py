"""S7b B3: the inner hash writers refuse bytes the strict region refuses,
before they are hashed into a signed body; through a CLI, "REFUSED:
<reason>", exit 1, no traceback, no output. Failpoints as slice B's.
Predictions: S7B_B3_PREDICTIONS.txt. Every key under tmp_path.
# __s7b_b3_tests_v1__
"""
from __future__ import annotations

import argparse
import shutil

import pytest

from conformance_verifier import StrictJsonError
import conformance_verifier
from test_s7b_guards_b import (
    SKILLS, TEMPLATE, _empty_or_absent, _refused, _verify_args)

pytestmark = pytest.mark.usefixtures("dated_shipped_prices")


def _fp(monkeypatch, mod, label):
    """Failpoint that installs whether or not mod has _s7b_loads yet."""
    real = getattr(mod, "_s7b_loads", conformance_verifier.loads)

    def fake(raw, lab):
        if label in lab:
            raise StrictJsonError(lab + ": failpoint")
        return real(raw, lab)
    monkeypatch.setattr(mod, "_s7b_loads", fake, raising=False)


def test_f15_verify_smt_cost_farkas(tmp_path, monkeypatch, capsys):
    import cli_verify
    src = tmp_path / "source.nous"
    shutil.copy2(TEMPLATE, src)
    _fp(monkeypatch, cli_verify, "[js:w.cf.1]")
    rc = cli_verify.cmd_verify(_verify_args(src, tmp_path / "m.key"))
    _refused(rc, capsys.readouterr().err, "[js:w.cf.1]")
    left = sorted(p.name for p in tmp_path.iterdir()
                  if p.name.startswith("source.") or p.name.startswith("cost"))
    assert left == ["source.nous"], left


def test_f16_dossier_spec_cost_farkas(tmp_path, monkeypatch, capsys):
    import cli_dossier_spec
    import dossier_spec
    out = tmp_path / "out"
    _fp(monkeypatch, dossier_spec, "[js:w.cf.2]")
    ns = argparse.Namespace(
        skill_dir=str(SKILLS / "minimal"), cap="0.50USD",
        key=str(tmp_path / "k.key"), output=str(out), prices=None,
        smt_margin=0, anchor="none",
    )
    rc = cli_dossier_spec.cmd_dossier_spec(ns)
    _refused(rc, capsys.readouterr().err, "[js:w.cf.2]")
    assert _empty_or_absent(out)


def test_f17_ndec_manifest_body(tmp_path, monkeypatch, capsys):
    import cli_ndec
    import ndec
    from test_s147_u2_ndec_container import _make_dossier
    d = _make_dossier(tmp_path)
    out = tmp_path / "x.ndec"
    _fp(monkeypatch, ndec, "[js:w.ndec.0]")
    ns = argparse.Namespace(
        ndec_action="build", dossier_dir=str(d),
        key_path=str(tmp_path / "k.key"), output=str(out),
    )
    rc = cli_ndec.cmd_ndec(ns)
    _refused(rc, capsys.readouterr().err, "[js:w.ndec.0]")
    assert not out.exists()


def _checkpoint(tmp_path, monkeypatch, capsys, label):
    import continuity_checkpoint
    from test_s178_checkpoint_leg import _build_priced_ledger, _keys, _run
    op, cp = _keys(tmp_path)
    ledger = _build_priced_ledger(tmp_path, op, cp, ["0.10", "0.20"])
    capsys.readouterr()
    _fp(monkeypatch, continuity_checkpoint, label)
    rc = _run(["continuity", "checkpoint", "--ledger", str(ledger),
               "--log-key", str(tmp_path / "logkey"), "--budget", "1.00"])
    _refused(rc, capsys.readouterr().err, label)
    assert not (ledger / "checkpoint.note").exists()
    assert not (ledger / "aggregate.cost.farkas.json").exists()


def test_f18_checkpoint_leaf_set(tmp_path, monkeypatch, capsys):
    _checkpoint(tmp_path, monkeypatch, capsys, "[js:w.ckp.1]")


def test_f19_checkpoint_sidecar(tmp_path, monkeypatch, capsys):
    _checkpoint(tmp_path, monkeypatch, capsys, "[js:w.ckp.2]")


def test_f20_remedy_proof(tmp_path, monkeypatch):
    import run_identity
    from test_s111_u5_promotion_wiring import _HEX, _Entry, _patch, _proof
    d = _HEX("a")
    _patch(monkeypatch, [_Entry(5, _proof(d))], [d])
    _fp(monkeypatch, run_identity, "[js:w.rem.1]")
    with pytest.raises(StrictJsonError) as ei:
        run_identity.build_run_remedy_application(
            "W", "S", ["soul"], base_dir=str(tmp_path))
    assert "[js:w.rem.1]" in str(ei.value)
