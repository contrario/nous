"""
test_s130_farkas_mirror_pin.py -- U4 of the verifier-core integrity arc.

The dossier farkas embed is an INDEPENDENT re-implementation of the
coverage_farkas.py math core (N-version, by design -- the independence is
what lets U1's differential harness catch a bug in either side; collapsing
them, as U3 did for the minilang parser, would destroy that oracle). So
the embed is deliberately NOT single-sourced.

U2 already pins the embed side byte-for-byte; U1 checks the embed and the
production code agree behaviorally on a corpus. The remaining unguarded
half is the PRODUCTION side: a change to coverage_farkas.py's math that
U1's corpus does not happen to exercise could silently break the
"mirrors coverage_farkas.py exactly" claim. Differential testing cannot
close this on its own (shared-ancestry / corpus-coverage blind spot); the
fix is an EXTERNAL ORACLE that flags any production-math change
structurally, regardless of corpus coverage.

This is that oracle: a per-symbol provenance pin over the production
mirror-core symbols. When any pinned symbol's source changes, the test
fails and NAMES it, forcing a conscious re-validation: re-run U1
(test_s130_verifier_embed_equiv.py) to confirm the embed still agrees,
then re-bless this pin.

Honest boundary: the pin enforces mirror-MAINTENANCE discipline. It does
NOT prove the two implementations are equivalent -- that is U1's job. A
matching pin means "production math has not moved since the embed was last
validated against it", not "the embed is correct".

Re-bless gate: NOUS_UPDATE_FARKAS_PIN=1 (DISTINCT from the verifier
snapshot's NOUS_UPDATE_SNAPSHOTS, so re-blessing one concern never
silences the other). __s130_farkas_mirror_pin_v1__
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path

import coverage_farkas

_BASELINE_PATH = (
    Path(__file__).parent / "baselines" / "s130_farkas_mirror_pin.json"
)

# Production symbols the dossier farkas embed re-implements by shared name.
# The bundle/hop ENTRY POINTS are intentionally excluded: they are
# independently named in the embed (check_bundle_against_derived vs
# check_serialized_bundle) and their agreement is U1's behavioral concern,
# not a source-mirror concern.
MIRROR_CORE_SYMBOLS = (
    "FarkasError",
    "LinIneq",
    "_num",
    "_linear",
    "_add",
    "_scale",
    "_is_const_only",
    "_linear_mul",
    "_comparison_to_ineq",
    "_is_comparison",
    "_nnf",
    "_dnf",
    "_gap_disjuncts",
    "_hop_disjuncts",
    "_canon_constraint",
    "_canon_json",
    "_canon_system",
    "_check_multipliers",
    "_point_satisfies",
)


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _extract_symbol_segments(module_path: Path, names: tuple) -> dict:
    src = module_path.read_text(encoding="utf-8")
    src_lines = src.splitlines()
    tree = ast.parse(src)
    found = {}
    for node in tree.body:
        name = None
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            name = node.name
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    name = t.id
        elif isinstance(node, ast.AnnAssign) and isinstance(
            node.target, ast.Name
        ):
            name = node.target.id
        if name is None or name not in names:
            continue
        decorators = getattr(node, "decorator_list", [])
        if decorators:
            start = min(d.lineno for d in decorators)
            seg = "\n".join(src_lines[start - 1:node.end_lineno])
        else:
            seg = ast.get_source_segment(src, node)
        if seg is None:
            raise AssertionError(
                "could not extract source segment for " + name
            )
        found[name] = seg
    return found


def compute_pin() -> dict:
    module_path = Path(coverage_farkas.__file__)
    segs = _extract_symbol_segments(module_path, MIRROR_CORE_SYMBOLS)
    missing = [s for s in MIRROR_CORE_SYMBOLS if s not in segs]
    return {
        "symbols": {s: _sha(segs[s]) for s in segs},
        "missing": missing,
    }


def _maybe_update(pin: dict) -> None:
    if os.environ.get("NOUS_UPDATE_FARKAS_PIN") != "1":
        return
    _BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _BASELINE_PATH.write_text(
        json.dumps(pin, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_baseline() -> dict:
    if not _BASELINE_PATH.is_file():
        raise AssertionError(
            "farkas mirror pin missing: " + str(_BASELINE_PATH)
            + " -- regenerate with NOUS_UPDATE_FARKAS_PIN=1"
        )
    return json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))


def test_all_mirror_symbols_present() -> None:
    pin = compute_pin()
    assert not pin["missing"], (
        "production coverage_farkas.py no longer defines pinned mirror "
        "symbol(s) " + str(pin["missing"]) + "; the dossier farkas embed "
        "mirrors these by name -- a rename/removal needs the embed and "
        "this pin updated together"
    )


def test_production_farkas_mirror_pin() -> None:
    pin = compute_pin()
    _maybe_update(pin)
    baseline = _load_baseline()
    base_syms = baseline.get("symbols", {})
    live_syms = pin["symbols"]
    drifted = sorted(
        s for s in live_syms if base_syms.get(s) != live_syms[s]
    )
    dropped = sorted(set(base_syms) - set(live_syms))
    assert not dropped, (
        "pinned production symbol(s) vanished: " + str(dropped)
    )
    assert not drifted, (
        "production coverage_farkas.py math changed in " + str(drifted)
        + ". The dossier farkas embed is an INDEPENDENT N-version mirror "
        "of these symbols: re-run tests/test_s130_verifier_embed_equiv.py "
        "(U1) to confirm the embed still agrees with the new production "
        "code, update the embed in dossier.py if it does not, then "
        "re-bless this pin with NOUS_UPDATE_FARKAS_PIN=1"
    )


def test_pin_is_orthogonal_to_verifier_snapshot() -> None:
    # The two concerns use distinct baseline files and distinct re-bless
    # env vars, so re-blessing one cannot silence the other.
    snapshot_baseline = (
        Path(__file__).parent / "baselines" / "s130_verifier_snapshots.json"
    )
    assert _BASELINE_PATH != snapshot_baseline
    assert _BASELINE_PATH.name == "s130_farkas_mirror_pin.json"
