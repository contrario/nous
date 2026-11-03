"""FG-S427-I: a negative price must not make the cost verdict vacuous.

A pricing table with a negative price loaded, the spec asserted a
negative per-call cost and per-call >= 0 together, and the run came out
'proven' at any cap; its dossier verified PASS offline. These tests pin
the three refusals the operator ruled (11-03): the loader rejects a
price that is not a finite number >= 0 before any spec is built;
emit_smt refuses one with EmitError (a table built without
validation); the offline verifier binds the carried table to the signed
pricing_sha256 and refuses one, CLASS INTEGRITY. The check lives in the
dossier verifier templates themselves (ruling 11-03 09:55Z), so an
emitted verifier still equals its template and ndec's canonical set
still recognises it. The region's branches are also run directly
(test_region_*): each refusal, each kind of bad price, and acceptance.

Fixtures that need a negative table past the loader replace
pricing._require_finite_nonnegative with a no-op: the shape of a
producer without the check. Every manifest is made once by cmd_verify
under a fresh key in tmp; nothing is re-signed.

# __fg_s427_i_negative_price_v1__
"""
from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

import dossier as D
import pricing
import test_s97_certificate as s97
from _v3pin import manifest_signer_args
from cli_verify import cmd_verify
from dossier import build_dossier
from parser import parse_nous
from smt_emit import EmitError, emit_smt

ROOT = Path(__file__).resolve().parent.parent
TEXT = "finite number >= 0"
CALL = "_rc_pricing = _check_pricing(manifest, ROOT)"
FIELDS = (
    "input_per_1m",
    "output_per_1m",
    "input_cached_per_1m",
    "input_cache_write_per_1m",
    "reasoning_token_multiplier",
    "hourly_cost",
)
NEGATIVE = ("-1.00", "-0.000001")
NONFINITE = ("NaN", "Infinity")
M1 = 'input_per_1m = "1.00"\noutput_per_1m = "5.00"'
TEMPLATES = (
    "VERIFY_OFFLINE_PY",
    "VERIFY_OFFLINE_PY_WITH_REKOR",
    "VERIFY_OFFLINE_PY_CHAIN",
    "VERIFY_OFFLINE_PY_BUNDLE",
    "VERIFY_OFFLINE_PY_FARKAS",
    "VERIFY_OFFLINE_PY_COVERAGE",
    "VERIFY_OFFLINE_PY_CHAIN_BUNDLE",
    "build_chain_net_verifier",
    "build_gap_witness_verifier",
    "build_offline_verifier_v2",
)


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
    gap_witness = False
    coverage_threshold = None

    def __init__(self, **over: object) -> None:
        for k, v in over.items():
            setattr(self, k, v)


def _table_text(field: str, value: str) -> str:
    base = s97.PRICING_TOML
    assert base.count(M1) == 1
    if field == "hourly_cost":
        entry = 'pricing_model = "per_hour"\nhourly_cost = "%s"' % value
        return base.replace('pricing_model = "per_token"\n' + M1, entry, 1)
    if field in ("input_per_1m", "output_per_1m"):
        old = "1.00" if field == "input_per_1m" else "5.00"
        return base.replace(M1, M1.replace(
            '%s = "%s"' % (field, old), '%s = "%s"' % (field, value)), 1)
    if field == "reasoning_token_multiplier":
        return base.replace(
            M1 + '\nreasoning_token_multiplier = "1.0"',
            M1 + '\nreasoning_token_multiplier = "%s"' % value, 1)
    return base.replace(M1, M1 + '\n%s = "%s"' % (field, value), 1)


def _negative_table() -> str:
    return s97.PRICING_TOML.replace(
        M1, 'input_per_1m = "-1.00"\noutput_per_1m = "-5.00"', 1)


def _source(cap: str = "0.50") -> str:
    src = s97._SOULED_SOURCE
    assert src.count("cost_cap: 0.50 USD") == 1
    return src.replace("cost_cap: 0.50 USD", "cost_cap: %s USD" % cap)


def _write(p: Path, text: str) -> Path:
    p.write_text(text, encoding="utf-8")
    return p


def _no_check(monkeypatch) -> None:
    monkeypatch.setattr(pricing, "_require_finite_nonnegative",
                        lambda *a, **k: None, raising=False)


def _dossier(tmp_path: Path, table: str, cap: str) -> Path:
    src = _write(tmp_path / "source.nous", _source(cap))
    prices = _write(tmp_path / "prices.toml", table)
    mout = tmp_path / "source.manifest.json"
    args = _Args(file=str(src), manifest_out=str(mout),
                 key_path=str(tmp_path / "signing.key"), prices=str(prices))
    assert cmd_verify(args) == 0
    out = tmp_path / "dossier"
    build_dossier(src, manifest=mout, prices=prices, output=out)
    return out


def _verify(out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(out / "verify_offline.py")]
        + manifest_signer_args(out),
        capture_output=True, text=True,
    )


def _last(stdout: str) -> str:
    lines = [x for x in stdout.splitlines() if x.strip()]
    return lines[-1] if lines else ""


@pytest.mark.parametrize("value", NEGATIVE)
@pytest.mark.parametrize("field", FIELDS)
def test_loader_rejects_negative(tmp_path, field, value):
    p = _write(tmp_path / "t.toml", _table_text(field, value))
    with pytest.raises(ValueError, match=TEXT):
        pricing.load_pricing(p)


@pytest.mark.parametrize("value", NONFINITE)
@pytest.mark.parametrize("field", FIELDS)
def test_loader_rejects_nonfinite(tmp_path, field, value):
    p = _write(tmp_path / "t.toml", _table_text(field, value))
    with pytest.raises(ValueError, match="finite number"):
        pricing.load_pricing(p)


@pytest.mark.parametrize("field", FIELDS)
def test_loader_accepts_zero(tmp_path, field):
    p = _write(tmp_path / "t.toml", _table_text(field, "0"))
    table = pricing.load_pricing(p)
    assert "m1" in table.model_names()


def test_emit_refuses_negative_rate():
    today = datetime.now(timezone.utc).date()

    def entry(i, o):
        return pricing.PricingEntry.model_construct(
            provider="test", pricing_model="per_token",
            input_per_1m=Decimal(i), output_per_1m=Decimal(o),
            reasoning_token_multiplier=Decimal("1.0"), verified_date=today)

    table = pricing.PricingTable.model_construct(
        schema_version="2.0", currency="USD",
        models={"m1": entry("-1.00", "-5.00"), "m2": entry("0.50", "2.00")})
    src = _source()
    with pytest.raises(EmitError, match=TEXT):
        emit_smt(parse_nous(src), table, source_text=src)


def test_cli_verify_refuses_negative_table(tmp_path):
    src = _write(tmp_path / "source.nous", _source("0.000001"))
    prices = _write(tmp_path / "neg.toml", _negative_table())
    mout = tmp_path / "m.json"
    env = dict(os.environ, HOME=str(tmp_path))
    env.pop("XDG_DATA_HOME", None)
    r = subprocess.run(
        [sys.executable, "-B", str(ROOT / "cli.py"), "verify", str(src),
         "--smt", "--no-lint", "--prices", str(prices),
         "--key-path", str(tmp_path / "k.key"), "--manifest-out", str(mout)],
        cwd=tmp_path, env=env, capture_output=True, text=True)
    out = r.stdout + r.stderr
    assert r.returncode == 3, out
    assert "PROVEN" not in out
    assert TEXT in out
    assert not mout.exists()


def test_dossier_negative_table_is_integrity(tmp_path, monkeypatch):
    _no_check(monkeypatch)
    out = _dossier(tmp_path, _negative_table(), "0.000001")
    r = _verify(out)
    assert r.returncode == 1, r.stdout + r.stderr
    assert _last(r.stdout) == "CLASS: INTEGRITY"
    assert TEXT in r.stdout + r.stderr


def _template(name: str) -> str:
    if name == "build_offline_verifier_v2":
        from offline_verifier_builder import build_offline_verifier_v2
        from rekor_verify_v2 import KNOWN_REKOR_V2_LOG_KEYS
        return build_offline_verifier_v2(repr(KNOWN_REKOR_V2_LOG_KEYS))
    obj = getattr(D, name)
    return obj() if callable(obj) else obj


@pytest.mark.parametrize("name", TEMPLATES)
def test_every_template_carries_the_region(name):
    text = _template(name)
    assert text.count(pricing.PRICING_CHECK_EMBED) == 1
    assert text.count("def _check_pricing(") == 1
    assert text.count(CALL) == 1
    lines = text.split("\n")
    src = [i for i, x in enumerate(lines)
           if "OK   source.sha256 matches manifest" in x]
    assert len(src) == 1
    assert lines[src[0] + 1] == "    " + CALL


def test_region_fields_are_the_loader_fields():
    import ast
    tree = ast.parse(pricing.PRICING_CHECK_EMBED)
    loops = [n for n in ast.walk(tree) if isinstance(n, ast.For)
             and isinstance(n.target, ast.Name) and n.target.id == "key"]
    assert len(loops) == 1
    assert ast.literal_eval(loops[0].iter) == pricing.PRICE_FIELDS
    assert pricing.PRICE_FIELDS == FIELDS


def _region():
    import json
    ns = {"loads": lambda data, label: json.loads(data)}
    exec(compile(pricing.PRICING_CHECK_EMBED, "<pricing embed>", "exec"), ns)
    return ns["_check_pricing"]


def _bound(tmp_path: Path, doc) -> dict:
    import hashlib
    import json
    data = doc if isinstance(doc, bytes) else json.dumps(doc).encode()
    (tmp_path / "pricing.canonical.json").write_bytes(data)
    return {"pricing_sha256": hashlib.sha256(data).hexdigest()}


REGION_REFUSALS = {
    "no_field": "carries no pricing_sha256",
    "missing": "pricing.canonical.json is missing",
    "mismatch": "does not match",
    "parse": "parse error",
    "no_models": "has no models object",
    "entry_not_object": "is not an object",
}
BAD_PRICES = ("-1.00", "-0.000001", "NaN", "Infinity", "-Infinity",
              "sNaN", "1e", 1, None)


@pytest.mark.parametrize("case", sorted(REGION_REFUSALS))
def test_region_refuses(tmp_path, capsys, case):
    check = _region()
    if case == "no_field":
        _bound(tmp_path, {"models": {}})
        man = {}
    elif case == "missing":
        man = {"pricing_sha256": "0" * 64}
    elif case == "mismatch":
        man = _bound(tmp_path, {"models": {}})
        (tmp_path / "pricing.canonical.json").write_bytes(
            b'{"models":{"m1":{}}}')
    elif case == "parse":
        man = _bound(tmp_path, b"{")
    elif case == "no_models":
        man = _bound(tmp_path, {"currency": "USD"})
    else:
        man = _bound(tmp_path, {"models": {"m1": 1}})
    assert check(man, tmp_path) == 1
    err = capsys.readouterr().err
    assert REGION_REFUSALS[case] in err, err


@pytest.mark.parametrize("value", BAD_PRICES, ids=repr)
def test_region_refuses_price(tmp_path, capsys, value):
    check = _region()
    for field in FIELDS:
        man = _bound(tmp_path, {"models": {"m1": {
            "input_per_1m": "1.00", field: value}}})
        assert check(man, tmp_path) == 1, field
        err = capsys.readouterr().err
        assert "'m1' " + field + " = " in err and TEXT in err, (field, err)


@pytest.mark.parametrize("value", ("0", "0.00", "1.00", "1E+2"))
def test_region_accepts_price(tmp_path, capsys, value):
    check = _region()
    man = _bound(tmp_path, {
        "currency": "USD", "schema_version": "2.0",
        "models": {"m1": {f: value for f in FIELDS},
                   "m2": {"provider": "test"}}})
    assert check(man, tmp_path) == 0
    out = capsys.readouterr()
    assert out.err == ""
    assert "OK   pricing table bound to the manifest" in out.out


def test_emitted_verifier_is_its_canonical_template(tmp_path):
    import hashlib
    import ndec
    out = _dossier(tmp_path, s97.PRICING_TOML, "0.50")
    text = (out / "verify_offline.py").read_text(encoding="utf-8")
    assert text == D.VERIFY_OFFLINE_PY
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert sha in ndec.canonical_verifier_digests().values()


def test_honest_dossier_binds_pricing(tmp_path):
    out = _dossier(tmp_path, s97.PRICING_TOML, "0.50")
    r = _verify(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _last(r.stdout) == "CLASS: PASS"
    assert "OK   pricing table bound to the manifest" in r.stdout


def test_mismatched_canonical_pricing_is_integrity(tmp_path):
    out = _dossier(tmp_path, s97.PRICING_TOML, "0.50")
    other = s97.PRICING_TOML.replace(
        M1, 'input_per_1m = "2.00"\noutput_per_1m = "5.00"', 1)
    table = pricing.PricingTable.model_validate(tomllib.loads(other))
    (out / "pricing.canonical.json").write_bytes(table.canonical_bytes())
    r = _verify(out)
    assert r.returncode == 1, r.stdout + r.stderr
    assert _last(r.stdout) == "CLASS: INTEGRITY"
    assert "pricing.canonical.json" in r.stdout + r.stderr


def test_missing_canonical_pricing_is_integrity(tmp_path):
    out = _dossier(tmp_path, s97.PRICING_TOML, "0.50")
    p = out / "pricing.canonical.json"
    if p.exists():
        p.unlink()
    r = _verify(out)
    assert r.returncode == 1, r.stdout + r.stderr
    assert _last(r.stdout) == "CLASS: INTEGRITY"
    assert "pricing.canonical.json" in r.stdout + r.stderr


@pytest.mark.usefixtures("dated_shipped_prices")
def test_spec_dossier_verifier_checks_pricing(tmp_path):
    from dossier_spec import build_dossier_spec
    out = tmp_path / "out"
    build_dossier_spec(
        ROOT / "tests" / "skill_md_fixtures" / "minimal",
        cap_override="0.50USD", output=out,
        key_path=tmp_path / "signing.key",
    )
    text = (out / "verify_offline.py").read_text(encoding="utf-8")
    assert "    " + CALL in text
    r = _verify(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK   pricing table bound to the manifest" in r.stdout
