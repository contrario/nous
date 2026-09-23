"""
NOUS Session 369 -- D7: `nous dossier` reports a pricing refusal that
arises after signing as a dossier build failure, not as an unexpected
failure (docs/ONE_PRICE_SOURCE_DESIGN.md section 22).

A manifest is signed by `nous verify --smt` on the real clock for a model
that is usable today. The build then runs with the clock 10 days on, when
the model has been removed or is more than 90 days old. build_dossier
raises DossierError "SMT emit failed (UnpriceableSmtModel): soul 'A': ..."
from the UnpriceableSmtModel, and `nous dossier` exits 1 with "ERROR:
dossier build failed: ...". A priced model, a source changed after
signing and a failure that is not an EmitError keep today's behaviour.

Each case runs with HOME and the working directory in a temporary
directory; the table is passed as --prices.

# __s369_dossier_refusal_typed_tests_v1__
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import cli
import dossier
import runtime
import smt_emit
from dossier import build_dossier

OK = "s369-ok"
LATER: dict[str, str] = {
    "removed": "s369-gone-later",
    "stale": "s369-old-later",
}
IDS = list(LATER)
SHIFT_DAYS = 10


class _Later(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return datetime.now(tz) + timedelta(days=SHIFT_DAYS)


def _table_text() -> str:
    today = datetime.now(timezone.utc).date()
    fresh = (today - timedelta(days=5)).isoformat()
    per_token = 'pricing_model = "per_token"\ninput_per_1m = "1.00"\noutput_per_1m = "2.00"\n'
    out = f'_schema_version = "2.0"\n_last_verified = "{fresh}"\n_currency = "USD"\n'
    rows = (
        (OK, per_token + f'verified_date = "{fresh}"\n'),
        ("s369-gone-later", per_token + f'verified_date = "{fresh}"\nremoved_after = "{(today + timedelta(days=1)).isoformat()}"\n'),
        ("s369-old-later", per_token + f'verified_date = "{(today - timedelta(days=85)).isoformat()}"\n'),
    )
    for name, body in rows:
        out += f'\n[models."{name}"]\nprovider = "s369"\n{body}verified_by = "manual"\n'
    return out


def _src(model: str) -> str:
    return (
        "world W {\n  heartbeat = 10s\n  cost_cap: 1.00 USD\n  max_ticks: 4\n}\n"
        f"soul A {{\n  mind: {model} @ Tier1\n  tokens: input = 100 output = 50\n"
        "  memory {\n    n: int = 0\n  }\n"
        "  instinct {\n    remember n = n + 1\n  }\n"
        "  heal {\n    on error => alert(operator)\n  }\n}\n"
    )


@pytest.fixture()
def iso(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    work = tmp_path / "work"
    home.mkdir()
    work.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(work)
    (work / "table.toml").write_text(_table_text(), encoding="utf-8")
    monkeypatch.setattr(runtime, "_RUNTIME_PRICING", None)
    return tmp_path


def _run_cli(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
             argv: list[str]) -> tuple[int, str, str]:
    monkeypatch.setattr(sys, "argv", ["nous", *argv])
    try:
        rc = cli.main()
    except SystemExit as exc:
        rc = exc.code if isinstance(exc.code, int) else 1
    cap = capsys.readouterr()
    return (rc if isinstance(rc, int) else 0), cap.out, cap.err


def _sign(iso: Path, model: str, monkeypatch: pytest.MonkeyPatch,
          capsys: pytest.CaptureFixture[str]) -> Path:
    work = iso / "work"
    (work / "prog.nous").write_text(_src(model), encoding="utf-8")
    rc, out, err = _run_cli(monkeypatch, capsys, [
        "verify", "prog.nous", "--smt", "--prices", str(work / "table.toml"),
        "--manifest-out", "prog.manifest.json", "--key-path", str(iso / "k.key"), "--no-lint",
    ])
    assert rc == 0 and (work / "prog.manifest.json").is_file(), "setup rc " + str(rc) + " " + err[:300]
    return work


def _dossier_argv(iso: Path) -> list[str]:
    work = iso / "work"
    return ["dossier", "prog.nous", "--manifest", "prog.manifest.json",
            "--prices", str(work / "table.toml"), "--output", str(iso / "dos")]


def _first(text: str) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[0] if lines else ""


@pytest.mark.parametrize("kind", IDS)
def test_build_dossier_refusal_is_typed(iso: Path, kind: str, monkeypatch: pytest.MonkeyPatch,
                                        capsys: pytest.CaptureFixture[str]) -> None:
    model = LATER[kind]
    work = _sign(iso, model, monkeypatch, capsys)
    later = datetime.now(timezone.utc).date() + timedelta(days=SHIFT_DAYS)
    with pytest.raises(Exception) as ei:
        build_dossier(work / "prog.nous", manifest=work / "prog.manifest.json",
                      prices=work / "table.toml", output=iso / "dos", today=later)
    exc = ei.value
    assert type(exc).__name__ == "DossierError", "raised " + type(exc).__name__ + ": " + str(exc)[:200]
    msg = str(exc)
    assert msg.startswith("SMT emit failed (UnpriceableSmtModel): soul 'A': "), msg[:200]
    assert model in msg, msg[:200]
    assert type(exc.__cause__).__name__ == "UnpriceableSmtModel", "cause " + type(exc.__cause__).__name__


@pytest.mark.parametrize("kind", IDS)
def test_cli_dossier_refusal_is_typed(iso: Path, kind: str, monkeypatch: pytest.MonkeyPatch,
                                      capsys: pytest.CaptureFixture[str]) -> None:
    model = LATER[kind]
    _sign(iso, model, monkeypatch, capsys)
    monkeypatch.setattr(smt_emit, "datetime", _Later)
    rc, out, err = _run_cli(monkeypatch, capsys, _dossier_argv(iso))
    assert rc == 1, "rc " + str(rc) + " stderr " + _first(err)[:220]
    assert "ERROR: dossier build failed: SMT emit failed (UnpriceableSmtModel): soul 'A': " in err, err[:300]
    assert model in err, err[:300]
    assert "unexpected failure" not in err, err[:300]
    assert "Traceback" not in err + out, err[:300]


def test_build_dossier_priced_same_day(iso: Path, monkeypatch: pytest.MonkeyPatch,
                                       capsys: pytest.CaptureFixture[str]) -> None:
    work = _sign(iso, OK, monkeypatch, capsys)
    result = build_dossier(work / "prog.nous", manifest=work / "prog.manifest.json",
                           prices=work / "table.toml", output=iso / "dos")
    assert result.output_dir.is_dir(), str(result.output_dir)
    assert "manifest.json" in result.files, str(result.files)


def test_cli_dossier_priced_same_day(iso: Path, monkeypatch: pytest.MonkeyPatch,
                                     capsys: pytest.CaptureFixture[str]) -> None:
    _sign(iso, OK, monkeypatch, capsys)
    rc, out, err = _run_cli(monkeypatch, capsys, _dossier_argv(iso))
    assert rc == 0 and "Dossier emitted" in out, "rc " + str(rc) + " " + err[:300]


def test_cli_dossier_priced_clock_later(iso: Path, monkeypatch: pytest.MonkeyPatch,
                                        capsys: pytest.CaptureFixture[str]) -> None:
    _sign(iso, OK, monkeypatch, capsys)
    monkeypatch.setattr(smt_emit, "datetime", _Later)
    rc, out, err = _run_cli(monkeypatch, capsys, _dossier_argv(iso))
    assert rc == 0 and "Dossier emitted" in out, "rc " + str(rc) + " " + err[:300]


def test_cli_dossier_source_changed_still_validation(iso: Path, monkeypatch: pytest.MonkeyPatch,
                                                     capsys: pytest.CaptureFixture[str]) -> None:
    work = _sign(iso, OK, monkeypatch, capsys)
    with (work / "prog.nous").open("a", encoding="utf-8") as fh:
        fh.write("\n")
    rc, out, err = _run_cli(monkeypatch, capsys, _dossier_argv(iso))
    assert rc == 1, "rc " + str(rc) + " " + err[:300]
    assert "ERROR: dossier build failed: source.sha256 mismatch" in err, err[:300]


def test_cli_dossier_other_failure_still_unexpected(iso: Path, monkeypatch: pytest.MonkeyPatch,
                                                    capsys: pytest.CaptureFixture[str]) -> None:
    _sign(iso, OK, monkeypatch, capsys)

    def _boom(text: str) -> None:
        raise RuntimeError("s369 not an emit error")

    monkeypatch.setattr(dossier, "parse_nous", _boom)
    rc, out, err = _run_cli(monkeypatch, capsys, _dossier_argv(iso))
    assert rc == 3, "rc " + str(rc) + " " + err[:300]
    assert "ERROR: unexpected failure: RuntimeError: s369 not an emit error" in err, err[:300]
