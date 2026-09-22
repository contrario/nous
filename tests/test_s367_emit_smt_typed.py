"""
NOUS Session 367 -- O2: emit_smt's raw pricing errors become a typed
refusal (docs/ONE_PRICE_SOURCE_DESIGN.md section 20).

A soul model the table does not carry, a removed model, a per-hour model
and a model too old for --smt raise UnpriceableSmtModel, an EmitError,
from emit_smt; `nous verify --smt`, `nous emit-smt` and `nous governance
ledger --source` refuse with the cause and no traceback; compiled trace
raises CompiledTraceError for a subject binding it cannot price and for
a source that does not parse. The priced model, a soul with no mind and
get_price_for_smt itself keep today's behaviour.

Each case runs with HOME and the working directory in a temporary
directory holding its own nous_prices.toml (layer 2), passed as --prices
where the command takes it, and the runtime's memoised table is reset.

# __s367_emit_smt_typed_tests_v1__
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import cli
import runtime
from parser import parse_nous
from pricing import get_price_for_smt, load_pricing
from smt_emit import EmitError, emit_smt

OK = "s367-ok"
KINDS: dict[str, str] = {
    "missing": "s367-absent",
    "removed": "s367-gone",
    "per_hour": "s367-hourly",
    "stale": "s367-old",
}
IDS = list(KINDS)


def _table_text() -> str:
    today = datetime.now(timezone.utc).date()
    fresh = (today - timedelta(days=5)).isoformat()
    per_token = 'pricing_model = "per_token"\ninput_per_1m = "1.00"\noutput_per_1m = "2.00"\n'
    out = f'_schema_version = "2.0"\n_last_verified = "{fresh}"\n_currency = "USD"\n'
    rows = (
        (OK, per_token + f'verified_date = "{fresh}"\n'),
        ("s367-gone", per_token + f'verified_date = "{fresh}"\nremoved_after = "{(today - timedelta(days=10)).isoformat()}"\n'),
        ("s367-hourly", f'pricing_model = "per_hour"\nhourly_cost = "2.50"\nverified_date = "{fresh}"\n'),
        ("s367-old", per_token + f'verified_date = "{(today - timedelta(days=120)).isoformat()}"\n'),
    )
    for name, body in rows:
        out += f'\n[models."{name}"]\nprovider = "s367"\n{body}verified_by = "manual"\n'
    return out


def _src(model: str | None) -> str:
    mind = f"  mind: {model} @ Tier1\n" if model is not None else ""
    return (
        "world W {\n  heartbeat = 10s\n  cost_cap: 1.00 USD\n  max_ticks: 4\n}\n"
        f"soul A {{\n{mind}  tokens: input = 100 output = 50\n"
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
    (work / "nous_prices.toml").write_text(_table_text(), encoding="utf-8")
    monkeypatch.setattr(runtime, "_RUNTIME_PRICING", None)
    return work


def _write_src(work: Path, model: str | None) -> Path:
    path = work / "prog.nous"
    path.write_text(_src(model), encoding="utf-8")
    return path


def _write_trace(work: Path) -> Path:
    from nous_trace import TraceEnvelope
    env = TraceEnvelope(
        nous_version="5.84.0", world_name="W", source_sha256="b" * 64,
        smt_spec_sha256="a" * 64, pricing_sha256="c" * 64, events=[],
    )
    path = work / "trace.json"
    path.write_text(env.model_dump_json(), encoding="utf-8")
    return path


def _run_cli(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
             argv: list[str]) -> tuple[int, str, str]:
    monkeypatch.setattr(sys, "argv", ["nous", *argv])
    try:
        rc = cli.main()
    except SystemExit as exc:
        rc = exc.code if isinstance(exc.code, int) else 1
    out, err = capsys.readouterr()
    return rc, out, err


def _emit(work: Path, model: str | None):
    src = _src(model)
    return emit_smt(parse_nous(src), load_pricing(work / "nous_prices.toml"), source_text=src)


def _raw_type(kind: str) -> str:
    return "KeyError" if kind == "missing" else "ValueError"


@pytest.mark.parametrize("kind", IDS)
def test_emit_smt_refusal_is_typed(iso: Path, kind: str) -> None:
    model = KINDS[kind]
    with pytest.raises(Exception) as ei:
        _emit(iso, model)
    exc = ei.value
    assert type(exc).__name__ == "UnpriceableSmtModel", f"raised {type(exc).__name__}: {exc}"
    assert isinstance(exc, EmitError)
    assert isinstance(exc, ValueError)
    msg = str(exc)
    assert msg.startswith("soul 'A': "), msg
    assert not msg.startswith("soul 'A': \""), msg
    assert model in msg, msg
    assert type(exc.__cause__).__name__ == _raw_type(kind), repr(exc.__cause__)


@pytest.mark.parametrize("kind", IDS)
def test_verify_smt_refusal_is_typed(iso: Path, kind: str, monkeypatch: pytest.MonkeyPatch,
                                     capsys: pytest.CaptureFixture[str]) -> None:
    model = KINDS[kind]
    src = _write_src(iso, model)
    rc, out, err = _run_cli(monkeypatch, capsys, [
        "verify", str(src), "--smt", "--prices", str(iso / "nous_prices.toml"),
        "--manifest-out", str(iso / "m.json"), "--key-path", str(iso / "m.key"),
    ])
    assert rc == 3, (rc, err[-400:])
    assert "ERROR: cannot emit SMT for prog.nous:" in err, err[-400:]
    assert "soul 'A': " in err and model in err, err[-400:]
    assert "Traceback" not in (out + err), (out + err)[-400:]
    assert not (iso / "m.json").exists()


@pytest.mark.parametrize("kind", IDS)
def test_emit_smt_cli_refusal_is_typed(iso: Path, kind: str, monkeypatch: pytest.MonkeyPatch,
                                       capsys: pytest.CaptureFixture[str]) -> None:
    model = KINDS[kind]
    src = _write_src(iso, model)
    rc, out, err = _run_cli(monkeypatch, capsys, [
        "emit-smt", str(src), "--prices", str(iso / "nous_prices.toml"),
    ])
    assert rc == 3, (rc, err[-400:])
    assert "ERROR: cannot emit SMT for prog.nous:" in err, err[-400:]
    assert "soul 'A': " in err and model in err, err[-400:]
    assert "Traceback" not in (out + err), (out + err)[-400:]
    assert out == "", out[:200]


@pytest.mark.parametrize("kind", IDS)
def test_ledger_source_refusal_is_typed(iso: Path, kind: str, monkeypatch: pytest.MonkeyPatch,
                                        capsys: pytest.CaptureFixture[str]) -> None:
    model = KINDS[kind]
    src = _write_src(iso, model)
    trace = _write_trace(iso)
    rc, out, err = _run_cli(monkeypatch, capsys, [
        "governance", "ledger", str(trace), "--source", str(src),
        "--prices", str(iso / "nous_prices.toml"),
    ])
    assert rc == 1, (rc, err[-400:])
    assert "REFUSED: --source emit failed: soul 'A': " in err, err[-400:]
    assert model in err, err[-400:]
    assert "Traceback" not in (out + err), (out + err)[-400:]
    assert out.strip() == "", out[:200]


@pytest.mark.parametrize("kind", IDS)
def test_compiled_trace_refusal_is_typed(iso: Path, kind: str) -> None:
    from compiled_trace import run_compiled_with_trace
    model = KINDS[kind]
    with pytest.raises(Exception) as ei:
        run_compiled_with_trace(_src(model), max_cycles=1)
    exc = ei.value
    assert type(exc).__name__ == "CompiledTraceError", f"raised {type(exc).__name__}: {exc}"
    msg = str(exc)
    assert msg.startswith("cannot derive the trace subject binding: soul 'A': "), msg
    assert model in msg, msg
    assert type(exc.__cause__).__name__ == "UnpriceableSmtModel", repr(exc.__cause__)


def test_compiled_trace_parse_failure_is_typed(iso: Path) -> None:
    from compiled_trace import run_compiled_with_trace
    with pytest.raises(Exception) as ei:
        run_compiled_with_trace("world W { this is not nous", max_cycles=1)
    exc = ei.value
    assert type(exc).__name__ == "CompiledTraceError", f"raised {type(exc).__name__}: {exc}"
    assert str(exc).startswith("parse failed: "), str(exc)
    assert exc.__cause__ is not None


def test_run_emit_trace_message_is_unquoted(iso: Path, monkeypatch: pytest.MonkeyPatch,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    model = KINDS["missing"]
    src = _write_src(iso, model)
    rc, out, err = _run_cli(monkeypatch, capsys, ["run", str(src), "--emit-trace", "--cycles", "1"])
    line = next((ln for ln in err.splitlines() if ln.startswith("Runtime error: ")), "")
    assert line.startswith(f"Runtime error: soul 'A': model '{model}'"), f"rc={rc} line={line!r}"
    assert rc == 1


def test_control_emit_smt_priced(iso: Path) -> None:
    spec = _emit(iso, OK)
    assert spec.world_name == "W"
    assert spec.soul_costs[0][0] == OK


def test_control_verify_smt_priced(iso: Path, monkeypatch: pytest.MonkeyPatch,
                                   capsys: pytest.CaptureFixture[str]) -> None:
    src = _write_src(iso, OK)
    rc, out, err = _run_cli(monkeypatch, capsys, [
        "verify", str(src), "--smt", "--prices", str(iso / "nous_prices.toml"),
        "--manifest-out", str(iso / "m.json"), "--key-path", str(iso / "m.key"),
    ])
    assert rc == 0, (rc, err[-400:])
    assert (iso / "m.json").is_file()


def test_control_emit_smt_cli_priced(iso: Path, monkeypatch: pytest.MonkeyPatch,
                                     capsys: pytest.CaptureFixture[str]) -> None:
    src = _write_src(iso, OK)
    rc, out, err = _run_cli(monkeypatch, capsys, [
        "emit-smt", str(src), "--prices", str(iso / "nous_prices.toml"),
    ])
    assert rc == 0, (rc, err[-400:])
    assert "(assert" in out


def test_control_ledger_source_priced_reaches_sha_check(iso: Path, monkeypatch: pytest.MonkeyPatch,
                                                         capsys: pytest.CaptureFixture[str]) -> None:
    src = _write_src(iso, OK)
    trace = _write_trace(iso)
    rc, out, err = _run_cli(monkeypatch, capsys, [
        "governance", "ledger", str(trace), "--source", str(src),
        "--prices", str(iso / "nous_prices.toml"),
    ])
    assert rc == 1, (rc, err[-400:])
    assert "REFUSED: --source smt_spec_sha256 mismatch" in err, err[-400:]


def test_control_compiled_trace_priced(iso: Path) -> None:
    from compiled_trace import run_compiled_with_trace
    env = run_compiled_with_trace(_src(OK), max_cycles=1)
    assert env.world_name == "W"


def test_control_missing_mind_stays_plain_emit_error(iso: Path) -> None:
    with pytest.raises(EmitError) as ei:
        _emit(iso, None)
    assert type(ei.value) is EmitError, type(ei.value).__name__
    assert "has no `mind:` declaration" in str(ei.value)


def test_control_get_price_for_smt_keeps_keyerror(iso: Path) -> None:
    table = load_pricing(iso / "nous_prices.toml")
    with pytest.raises(KeyError) as ei:
        get_price_for_smt(table, KINDS["missing"])
    assert type(ei.value) is KeyError
