"""S381: the same source gives the same parse-error text in every process.

__s381_parse_error_determinism_v1__

docs/PARSE_ERROR_DETERMINISM.md, D381-1 to D381-5. lark 1.3.1 prints the
expected tokens of a parse error in set iteration order, which follows the
per-process string hash seed. parse_nous prints them sorted by terminal name,
the order lark master uses, and keeps lark's class and attributes on the raised
object.

The first five tests are red on the tree before the fix. The last three are
green before and after by design: the same-seed control, and the guards for
K2 (class and attributes kept) and K4 (no process-wide patch of lark).
"""
from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PROGRAMS = ["customer_service.nous", "noosphere_migrated.nous"]
SEEDS = list(range(8))
CONTROL_SEED = 0
CLI_SEEDS = [1, 2, 3]
KEPT_ATTRIBUTES = (
    "token",
    "line",
    "column",
    "expected",
    "considered_rules",
    "token_history",
    "pos_in_stream",
    "args",
)

PROBE = """
import json
import sys
from lark.exceptions import UnexpectedInput
from parser import parse_nous

out = {}
for name in sys.argv[1:]:
    src = open(name, encoding="utf-8").read()
    try:
        parse_nous(src)
        out[name] = {"kind": "PARSED", "text": "", "sorted_block_in_text": False}
    except UnexpectedInput as e:
        text = str(e)
        items = getattr(e, "accepts", None) or getattr(e, "expected", None) or getattr(e, "allowed", None) or []
        block = type(e)._format_expected(e, sorted(items))
        out[name] = {"kind": type(e).__name__, "text": text, "sorted_block_in_text": block in text}
print(json.dumps(out, sort_keys=True))
"""


def _env(seed: int) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = str(seed)
    return env


def _probe(seed: int) -> dict[str, dict[str, object]]:
    r = subprocess.run(
        [sys.executable, "-c", PROBE, *PROGRAMS],
        cwd=ROOT,
        env=_env(seed),
        capture_output=True,
        text=True,
        timeout=120,
    )
    ok = r.returncode == 0
    assert ok, f"probe at seed {seed} exited {r.returncode}: {r.stderr[-800:]}"
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def runs() -> dict[int, dict[str, dict[str, object]]]:
    return {seed: _probe(seed) for seed in SEEDS}


@pytest.fixture(scope="module")
def control_run() -> dict[str, dict[str, object]]:
    return _probe(CONTROL_SEED)


def _catch(fn: Callable[[], object]) -> BaseException:
    try:
        fn()
    except BaseException as e:
        return e
    raise AssertionError("expected a parse error, the source parsed")


@pytest.mark.parametrize("program", PROGRAMS)
def test_text_same_across_hash_seeds(runs: dict[int, dict[str, dict[str, object]]], program: str) -> None:
    kinds = sorted({str(runs[s][program]["kind"]) for s in SEEDS})
    assert kinds == ["UnexpectedToken"], f"{program} no longer fails with UnexpectedToken: {kinds}"
    prefixed = all(str(runs[s][program]["text"]).startswith("Unexpected token") for s in SEEDS)
    assert prefixed, f"{program}: a text does not start with 'Unexpected token'"
    distinct = len({str(runs[s][program]["text"]) for s in SEEDS})
    assert distinct == 1, f"{program}: {distinct} distinct parse-error texts over PYTHONHASHSEED 0..7"


@pytest.mark.parametrize("program", PROGRAMS)
def test_expected_lines_in_sorted_terminal_order(runs: dict[int, dict[str, dict[str, object]]], program: str) -> None:
    unsorted_seeds = [s for s in SEEDS if runs[s][program]["sorted_block_in_text"] is not True]
    assert unsorted_seeds == [], f"{program}: expected lines not in sorted terminal-name order at seeds {unsorted_seeds}"


def test_cli_parse_error_same_across_hash_seeds() -> None:
    outs = []
    for seed in CLI_SEEDS:
        r = subprocess.run(
            [sys.executable, "cli.py", "compile", "customer_service.nous"],
            cwd=ROOT,
            env=_env(seed),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert r.returncode == 1, f"seed {seed}: cli compile exited {r.returncode}: {r.stderr[-800:]}"
        has_line = "Parse error: Unexpected token" in r.stderr
        assert has_line, f"seed {seed}: no 'Parse error: Unexpected token' line: {r.stderr[-800:]}"
        outs.append((r.stdout, r.stderr))
    distinct = len(set(outs))
    assert distinct == 1, f"cli compile customer_service.nous: {distinct} distinct outputs over PYTHONHASHSEED {CLI_SEEDS}"


def test_same_seed_control(
    runs: dict[int, dict[str, dict[str, object]]], control_run: dict[str, dict[str, object]]
) -> None:
    same = control_run == runs[CONTROL_SEED]
    assert same, f"two processes at PYTHONHASHSEED={CONTROL_SEED} gave different results"


def test_raised_object_keeps_lark_class_and_attributes() -> None:
    from lark.exceptions import UnexpectedInput, UnexpectedToken

    import parser as nous_parser

    src = (ROOT / "customer_service.nous").read_text(encoding="utf-8")
    hooked = _catch(lambda: nous_parser.parse_nous(src))
    raw = _catch(lambda: nous_parser._get_parser().parse(src))
    same_class = type(hooked) is UnexpectedToken and type(raw) is UnexpectedToken
    assert same_class, f"class changed: {type(hooked)!r} vs {type(raw)!r}"
    assert isinstance(hooked, UnexpectedInput)
    for name in KEPT_ATTRIBUTES:
        a = getattr(hooked, name)
        b = getattr(raw, name)
        kept = a == b and type(a) is type(b)
        assert kept, f"attribute {name} differs: {type(a).__name__} {a!r} vs {type(b).__name__} {b!r}"
    accepts_kept = hooked.accepts == raw.accepts and type(hooked.accepts) is type(raw.accepts)
    assert accepts_kept, f"accepts differs: {hooked.accepts!r} vs {raw.accepts!r}"


def test_no_process_wide_patch_of_lark() -> None:
    import lark
    import lark.exceptions as lx

    import parser as nous_parser

    src = (ROOT / "customer_service.nous").read_text(encoding="utf-8")
    _catch(lambda: nous_parser.parse_nous(src))
    classes = (lx.UnexpectedInput, lx.UnexpectedToken, lx.UnexpectedCharacters, lx.UnexpectedEOF)
    foreign = [
        f"{c.__name__}.{k}"
        for c in classes
        for k, v in vars(c).items()
        if inspect.isfunction(v) and v.__module__ != "lark.exceptions"
    ]
    assert foreign == [], f"functions from outside lark on lark's classes: {foreign}"
    raw = _catch(lambda: nous_parser._get_parser().parse(src))
    assert "_format_expected" not in vars(raw), "a raw lark exception carries an instance override"
    other = _catch(lambda: lark.Lark('start: "a" "b"', parser="lalr").parse("aa"))
    assert "_format_expected" not in vars(other), "an exception from another Lark instance carries an override"
