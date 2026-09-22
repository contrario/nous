"""
NOUS Session 366 -- FG-S364-A: an explicit pricing path that is not a
regular file is an error in load_pricing itself, not a silent fall-through
to the project, user or shipped layer (docs/ONE_PRICE_SOURCE_DESIGN.md
section 18).

Every case isolates HOME and the working directory, so layers 2 and 3 are
absent. The new exception is checked by type name and by isinstance of
FileNotFoundError, never imported, so this file collects before the code.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import cli
import pricing
import run_shas
from pricing import load_pricing

ROOT = Path(__file__).resolve().parent.parent
CAUSE = "explicit pricing path is not a file: "
SKILL_FIXTURE = ROOT / "tests" / "skill_md_fixtures" / "basic"

PROGRAM = (
    "world W {\n"
    "  cost_cap: 0.50 USD\n"
    "  max_ticks: 3\n"
    "}\n"
    "soul A {\n"
    "  mind: s366-model @ Tier1\n"
    "  tokens: input=100 output=50\n"
    "  heal {\n"
    "    on error => alert(operator)\n"
    "  }\n"
    "}\n"
)


def _table_text() -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    return (
        "_schema_version = \"2.0\"\n"
        f"_last_verified  = \"{today}\"\n"
        "_currency       = \"USD\"\n"
        "\n"
        "[models.\"s366-model\"]\n"
        "provider       = \"s366\"\n"
        "pricing_model  = \"per_token\"\n"
        "input_per_1m  = \"1.00\"\n"
        "output_per_1m = \"2.00\"\n"
        "reasoning_token_multiplier = \"1.0\"\n"
        f"verified_date = \"{today}\"\n"
        "verified_by   = \"manual\"\n"
    )


@pytest.fixture()
def iso(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    work = tmp_path / "work"
    home.mkdir()
    work.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(work)
    assert not (work / "nous_prices.toml").exists()
    assert not (home / ".config" / "nous" / "prices.toml").exists()
    (work / "prog.nous").write_text(PROGRAM, encoding="utf-8")
    (work / "table.toml").write_text(_table_text(), encoding="utf-8")
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


def _assert_refusal(exc: BaseException, path: Path) -> None:
    assert type(exc).__name__ == "PricingPathError", "type " + type(exc).__name__ + ": " + str(exc)[:200]
    assert isinstance(exc, FileNotFoundError), "not a FileNotFoundError: " + type(exc).__name__
    assert str(exc).startswith(CAUSE), "message: " + str(exc)[:200]
    assert str(path) in str(exc), "path not named: " + str(exc)[:200]


def test_loader_refuses_missing_explicit_path(iso: Path) -> None:
    missing = iso / "missing.toml"
    try:
        table = load_pricing(missing)
    except FileNotFoundError as exc:
        assert str(exc).startswith(CAUSE), "message: " + str(exc)[:200]
        return
    pytest.fail("no refusal; loaded layer " + str(table.layer_index) + " from " + str(table.source_path))


def test_loader_refuses_directory_explicit_path(iso: Path) -> None:
    adir = iso / "adir"
    adir.mkdir()
    try:
        table = load_pricing(adir)
    except FileNotFoundError as exc:
        assert str(exc).startswith(CAUSE), "message: " + str(exc)[:200]
        return
    pytest.fail("no refusal; loaded layer " + str(table.layer_index) + " from " + str(table.source_path))


def test_loader_refusal_type(iso: Path) -> None:
    missing = iso / "missing.toml"
    try:
        table = load_pricing(missing)
    except Exception as exc:
        _assert_refusal(exc, missing)
        return
    pytest.fail("no refusal; loaded layer " + str(table.layer_index) + " from " + str(table.source_path))


def test_loader_none_path_unchanged(iso: Path) -> None:
    table = load_pricing(None)
    shipped = pricing._resolve_shipped_defaults()
    assert table.layer_index == 4, "layer " + str(table.layer_index)
    assert table.source_path == shipped, str(table.source_path) + " != " + str(shipped)


def test_loader_existing_explicit_path_is_layer_1(iso: Path) -> None:
    path = iso / "work" / "table.toml"
    table = load_pricing(path)
    assert table.layer_index == 1, "layer " + str(table.layer_index)
    assert table.source_path == path, str(table.source_path)
    assert table.model_names() == ["s366-model"], str(table.model_names())


SITES = {
    "verify-smt": (["verify", "prog.nous", "--smt", "--prices", "{m}", "--no-manifest"], 3, "ERROR: pricing load failed: "),
    "emit-smt": (["emit-smt", "prog.nous", "--prices", "{m}", "-o", "out.smt2"], 2, "ERROR: failed to load pricing: "),
    "prices-verify": (["prices", "--prices", "{m}", "verify", "s366-model"], 2, "ERROR loading pricing: "),
    "prices-age": (["prices", "--prices", "{m}", "age"], 2, "ERROR loading pricing: "),
    "dossier-spec": (["dossier-spec", str(SKILL_FIXTURE), "--prices", "{m}", "--output", "dspec", "--key", "k.key"], 1, "ERROR: dossier-spec build failed: pricing load failed: "),
}


@pytest.mark.parametrize("site", sorted(SITES))
def test_cli_site_refuses(site: str, iso: Path, monkeypatch: pytest.MonkeyPatch,
                          capsys: pytest.CaptureFixture[str]) -> None:
    argv, want_rc, prefix = SITES[site]
    missing = iso / "missing.toml"
    argv = [a.replace("{m}", str(missing)) for a in argv]
    rc, out, err = _run_cli(monkeypatch, capsys, argv)
    assert (prefix + CAUSE) in err, site + " rc " + str(rc) + " stderr " + err[:300] + " stdout " + out[:200]
    assert str(missing) in err, site + " path not named: " + err[:300]
    assert rc == want_rc, site + " rc " + str(rc) + " want " + str(want_rc)


def test_prices_show_refuses_without_active_layer(iso: Path, monkeypatch: pytest.MonkeyPatch,
                                                  capsys: pytest.CaptureFixture[str]) -> None:
    missing = iso / "missing.toml"
    rc, out, err = _run_cli(monkeypatch, capsys, ["prices", "--prices", str(missing), "show"])
    assert ("ERROR loading pricing: " + CAUSE) in err, "rc " + str(rc) + " stderr " + err[:300] + " stdout " + out[:300]
    assert "ACTIVE" not in out, "a layer is marked ACTIVE: " + out[:400]
    layer1 = [line for line in out.splitlines() if line.strip().startswith("1. ")]
    assert len(layer1) == 1 and layer1[0].rstrip().endswith("not found"), "layer 1 line: " + repr(layer1)
    assert rc == 2, "rc " + str(rc)


def test_ledger_refuses_missing_prices(iso: Path, monkeypatch: pytest.MonkeyPatch,
                                       capsys: pytest.CaptureFixture[str]) -> None:
    from nous_trace import TraceEnvelope
    env = TraceEnvelope(
        nous_version="5.83.0", world_name="W", source_sha256="a" * 64,
        smt_spec_sha256="b" * 64, pricing_sha256="c" * 64, events=[],
    )
    trace = iso / "work" / "trace.json"
    trace.write_text(env.model_dump_json(), encoding="utf-8")
    missing = iso / "missing.toml"
    rc, out, err = _run_cli(monkeypatch, capsys, [
        "governance", "ledger", str(trace), "--source", "prog.nous", "--prices", str(missing),
    ])
    assert ("REFUSED: --source pricing load failed: " + CAUSE) in err, "rc " + str(rc) + " stderr " + err[:300]
    assert rc == 1, "rc " + str(rc)


def test_dossier_refuses_missing_prices(iso: Path, monkeypatch: pytest.MonkeyPatch,
                                        capsys: pytest.CaptureFixture[str]) -> None:
    work = iso / "work"
    rc0, out0, err0 = _run_cli(monkeypatch, capsys, [
        "verify", "prog.nous", "--smt", "--prices", str(work / "table.toml"),
        "--manifest-out", "prog.manifest.json", "--key-path", str(iso / "k.key"), "--no-lint",
    ])
    assert rc0 == 0 and (work / "prog.manifest.json").is_file(), "setup rc " + str(rc0) + " " + err0[:300]
    missing = iso / "missing.toml"
    rc, out, err = _run_cli(monkeypatch, capsys, [
        "dossier", "prog.nous", "--manifest", "prog.manifest.json",
        "--prices", str(missing), "--output", str(iso / "dos"),
    ])
    assert ("ERROR: dossier build failed: " + CAUSE) in err, "rc " + str(rc) + " stderr " + err[:300]
    assert str(missing) in err, "path not named: " + err[:300]
    assert rc == 1, "rc " + str(rc)


@pytest.mark.parametrize("fn", ["compute_run_shas", "compute_run_gated_actions"])
def test_run_shas_refuses(fn: str, iso: Path) -> None:
    missing = iso / "missing.toml"
    try:
        got = getattr(run_shas, fn)(PROGRAM, missing)
    except Exception as exc:
        _assert_refusal(exc, missing)
        return
    pytest.fail(fn + " did not refuse; returned " + repr(got)[:200])


@pytest.mark.parametrize("sub", ["verify", "certify"])
def test_conformance_already_refuses(sub: str, iso: Path, monkeypatch: pytest.MonkeyPatch,
                                     capsys: pytest.CaptureFixture[str]) -> None:
    work = iso / "work"
    for name in ("trace.json", "m.json"):
        (work / name).write_text("{}", encoding="utf-8")
    missing = iso / "missing.toml"
    argv = ["conformance", sub, "trace.json", "--manifest", "m.json", "--prices", str(missing), "--source", "prog.nous"]
    if sub == "certify":
        argv += ["--out", str(iso / "cert.json")]
    rc, out, err = _run_cli(monkeypatch, capsys, argv)
    assert ("prices file not found: " + str(missing)) in (out + err), "rc " + str(rc) + " " + (out + err)[:300]
    assert rc == 2, "rc " + str(rc)


def test_plain_verify_helper_already_refuses(iso: Path, monkeypatch: pytest.MonkeyPatch,
                                             capsys: pytest.CaptureFixture[str]) -> None:
    missing = iso / "missing.toml"
    rc, out, err = _run_cli(monkeypatch, capsys, ["verify", "prog.nous", "--prices", str(missing), "--no-lint"])
    assert "Error: pricing table could not be loaded" in err, "rc " + str(rc) + " " + err[:300]
    assert "--prices path is not a file: " + str(missing) in err, err[:300]
    assert rc == 1, "rc " + str(rc)
