"""
test_s130_verifier_snapshot.py -- U2 of the verifier-core integrity arc.

Three guards over the emitted offline verifiers, in one file, all test-only
and shipping nothing:

  U2a SNAPSHOT. Every emitted verifier source (the eight VERIFY_OFFLINE_PY*
      constants plus the assembled build_chain_net_verifier output) is
      SHA-256 pinned against tests/baselines/s130_verifier_snapshots.json.
      Any byte change turns the gate red and NAMES the verifier; an
      intentional change is re-blessed in the same patch by running with
      NOUS_UPDATE_SNAPSHOTS=1. Signatures are not involved, so the bytes
      are deterministic. build_offline_verifier_v2 is intentionally NOT
      snapshotted here: it is already drift-guarded behaviorally by
      test_offline_verifier_v2_equiv.py (the Rekor v2 path).

  U2b MINILANG SINGLE SOURCE. The minilang core lives verbatim in more
      than one verifier template and is byte-identical to the marked
      region of coverage_minilang.py (OPEN 6.1, header included). The
      invariant requires the canonical region and every embedded copy to
      collapse to EXACTLY ONE SHA, and NAMES any copy that drifts.

  U2c FARKAS SHARED-CORE PREFIX. The farkas embed is NOT monolithic: the
      bundle verifier carries the shared core, and the chain-bundle
      verifier carries that SAME core followed by chain-only hop functions
      (_hop_disjuncts / check_hop_bundle, marker __s126_hop_embed_v1__).
      So the invariant is a prefix relation, not equality: the canonical
      core is the SHORTEST occurrence body (region minus its END marker),
      and every occurrence body must START with that core byte-for-byte.
      A chain-only extension is admitted; an edit to the shared core in
      any one copy breaks the prefix and is NAMED. The whole chain-bundle
      region (extension included) is still pinned end-to-end by U2a, so
      the extension cannot change unnoticed either.

  These are orthogonal to U2a: re-blessing the snapshot does NOT silence a
  divergent-copy or broken-prefix violation.

Single source of truth: ONE function (compute_snapshot) produces both the
asserted value and, under update mode, the written baseline, so they
cannot drift apart. __s130_verifier_snapshot_v1__
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Optional

import coverage_minilang
import dossier

_BASELINE_PATH = (
    Path(__file__).parent / "baselines" / "s130_verifier_snapshots.json"
)

VERIFIER_CONSTANTS = (
    "VERIFY_OFFLINE_PY",
    "VERIFY_OFFLINE_PY_WITH_REKOR",
    "VERIFY_OFFLINE_PY_COVERAGE",
    "VERIFY_OFFLINE_PY_FARKAS",
    "VERIFY_OFFLINE_PY_CHAIN",
    "VERIFY_OFFLINE_PY_BUNDLE",
    "VERIFY_OFFLINE_PY_CHAIN_BUNDLE",
)
VERIFIER_BUILDERS = ("build_chain_net_verifier",)

_MINILANG_START = (
    "# --- minilang core (shared text; do not edit one copy "
    "without the other) ---"
)
_MINILANG_END = "# --- end minilang core ---"
_FARKAS_START = (
    "# --- farkas embed (shared text; mirrors coverage_farkas.py "
    "exactly) ---"
)
_FARKAS_END = "# --- end farkas embed ---"

_EMBED_HOSTS = ("VERIFY_OFFLINE_PY_BUNDLE", "VERIFY_OFFLINE_PY_CHAIN_BUNDLE")


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _slice_inclusive(
    text: str, start_anchor: str, end_anchor: str
) -> Optional[str]:
    i = text.find(start_anchor)
    if i < 0:
        return None
    j = text.find(end_anchor, i)
    if j < 0:
        return None
    return text[i:j + len(end_anchor)]


def _region_body(region: Optional[str], end_anchor: str) -> Optional[str]:
    # The shared body is the region with its trailing END marker removed,
    # so a chain-only extension that lives between core and END is included
    # in the body and a prefix relation can distinguish core from extension.
    if region is None:
        return None
    e = region.rfind(end_anchor)
    return region[:e] if e >= 0 else region


def _verifier_source(name: str) -> str:
    obj = getattr(dossier, name)
    return obj() if callable(obj) else obj


def _canonical_minilang() -> str:
    text = Path(coverage_minilang.__file__).read_text(encoding="utf-8")
    region = _slice_inclusive(text, _MINILANG_START, _MINILANG_END)
    if region is None:
        raise AssertionError(
            "minilang marked region not found in coverage_minilang.py"
        )
    return region


def compute_snapshot() -> dict:
    verifiers = {}
    for name in VERIFIER_CONSTANTS + VERIFIER_BUILDERS:
        verifiers[name] = _sha(_verifier_source(name))

    minilang_canonical = _sha(_canonical_minilang())
    minilang_occ = {}
    farkas_bodies = {}
    for host in _EMBED_HOSTS:
        src = _verifier_source(host)
        m = _slice_inclusive(src, _MINILANG_START, _MINILANG_END)
        minilang_occ[host] = _sha(m) if m is not None else None
        f = _slice_inclusive(src, _FARKAS_START, _FARKAS_END)
        farkas_bodies[host] = _region_body(f, _FARKAS_END)

    # farkas canonical core = the shortest present occurrence body; every
    # occurrence body must start with it (chain-only extensions allowed).
    present = {k: v for k, v in farkas_bodies.items() if v is not None}
    if present:
        core_name = min(present, key=lambda n: len(present[n]))
        canonical_core = present[core_name]
        core_sha = _sha(canonical_core)
    else:
        core_name = None
        canonical_core = None
        core_sha = None

    farkas_occ = {}
    for host in _EMBED_HOSTS:
        body = farkas_bodies[host]
        if body is None or canonical_core is None:
            farkas_occ[host] = {"core_sha": None, "extends": None}
            continue
        prefix = body[:len(canonical_core)]
        farkas_occ[host] = {
            "core_sha": _sha(prefix),
            "extends": bool(len(body) > len(canonical_core)),
        }

    return {
        "verifiers": verifiers,
        "shared_regions": {
            "minilang_core": {
                "canonical_source": "coverage_minilang.py",
                "mode": "strict-equal",
                "canonical_sha": minilang_canonical,
                "occurrences": minilang_occ,
            },
            "farkas_embed": {
                "canonical_source": "shortest-occurrence core "
                "(re-implementation; chain adds hop extension)",
                "mode": "prefix-core",
                "canonical_core_name": core_name,
                "canonical_core_sha": core_sha,
                "occurrences": farkas_occ,
            },
        },
    }


def _minilang_violations(rec: dict) -> list:
    out = []
    shas = set()
    for vname, sha in rec["occurrences"].items():
        if sha is None:
            out.append("missing minilang region in " + vname)
        else:
            shas.add(sha)
    if rec["canonical_sha"] is not None:
        shas.add(rec["canonical_sha"])
    if len(shas) > 1:
        out.append(
            "minilang divergent copies: " + json.dumps(
                {
                    "canonical": (rec["canonical_sha"] or "")[:12],
                    **{
                        k: (v[:12] if v else None)
                        for k, v in rec["occurrences"].items()
                    },
                },
                sort_keys=True,
            )
        )
    return out


def _farkas_violations(rec: dict) -> list:
    out = []
    core = rec["canonical_core_sha"]
    if core is None:
        return ["farkas core absent from all hosts"]
    for vname, occ in rec["occurrences"].items():
        if occ["core_sha"] is None:
            out.append("missing farkas region in " + vname)
        elif occ["core_sha"] != core:
            out.append(
                "farkas shared core diverged in " + vname
                + " (core " + occ["core_sha"][:12]
                + " != canonical " + core[:12] + ")"
            )
    return out


def _region_violations(snapshot: dict) -> list:
    out = []
    ml = _minilang_violations(snapshot["shared_regions"]["minilang_core"])
    out.extend(("minilang_core", m) for m in ml)
    fk = _farkas_violations(snapshot["shared_regions"]["farkas_embed"])
    out.extend(("farkas_embed", m) for m in fk)
    return out


def _maybe_update(snapshot: dict) -> None:
    if os.environ.get("NOUS_UPDATE_SNAPSHOTS") != "1":
        return
    _BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _BASELINE_PATH.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_baseline() -> dict:
    if not _BASELINE_PATH.is_file():
        raise AssertionError(
            "baseline missing: " + str(_BASELINE_PATH)
            + " -- regenerate with NOUS_UPDATE_SNAPSHOTS=1"
        )
    return json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))


def test_snapshot_matches_baseline() -> None:
    snapshot = compute_snapshot()
    _maybe_update(snapshot)
    baseline = _load_baseline()
    base_v = baseline.get("verifiers", {})
    live_v = snapshot["verifiers"]
    changed = sorted(n for n in live_v if base_v.get(n) != live_v[n])
    missing = sorted(set(base_v) - set(live_v))
    assert not missing, (
        "baseline has verifiers no longer emitted: " + str(missing)
    )
    assert not changed, (
        "emitted verifier source drift (re-bless with "
        "NOUS_UPDATE_SNAPSHOTS=1 if intended): " + str(changed)
    )


def test_shared_region_single_source_invariant() -> None:
    snapshot = compute_snapshot()
    _maybe_update(snapshot)
    violations = _region_violations(snapshot)
    assert not violations, (
        "shared verifier-core regions diverged across templates "
        "(a copy was edited without the others): " + json.dumps(violations)
    )


def test_baseline_records_region_modes() -> None:
    # Guard the registry shape itself so a future refactor cannot silently
    # downgrade farkas back to a monolithic-equality check.
    baseline = _load_baseline()
    regions = baseline["shared_regions"]
    assert regions["minilang_core"]["mode"] == "strict-equal"
    assert regions["farkas_embed"]["mode"] == "prefix-core"


def test_minilang_canonical_matches_open_6_1_pin() -> None:
    # OPEN 6.1 (S130) proved the embedded minilang region is byte-identical
    # to coverage_minilang.py's HEADER..END region, sha 8c9e41b4...
    pin = "8c9e41b45c4efdd3bdd61e99fff5cb1f2800031bc362b6b7a70a498c38d1fc0e"
    assert _sha(_canonical_minilang()) == pin, (
        "coverage_minilang.py marked region SHA changed vs the OPEN 6.1 "
        "pin; minilang single source moved (expected if a minilang edit "
        "was made -- update the pin deliberately)"
    )


def test_minilang_embeds_equal_canonical() -> None:
    canonical = _sha(_canonical_minilang())
    for host in _EMBED_HOSTS:
        region = _slice_inclusive(
            _verifier_source(host), _MINILANG_START, _MINILANG_END
        )
        assert region is not None, host + " carries no minilang region"
        assert _sha(region) == canonical, (
            host + " minilang embed diverged from coverage_minilang.py"
        )


def test_farkas_core_is_common_prefix() -> None:
    bodies = {}
    for host in _EMBED_HOSTS:
        f = _slice_inclusive(
            _verifier_source(host), _FARKAS_START, _FARKAS_END
        )
        body = _region_body(f, _FARKAS_END)
        assert body is not None, host + " carries no farkas region"
        bodies[host] = body
    core_name = min(bodies, key=lambda n: len(bodies[n]))
    core = bodies[core_name]
    for host, body in bodies.items():
        assert body.startswith(core), (
            host + " farkas shared core diverged from canonical "
            + core_name
        )
    # the chain-bundle host carries the core plus the hop extension
    chain = bodies["VERIFY_OFFLINE_PY_CHAIN_BUNDLE"]
    assert chain.startswith(core)
    assert len(chain) >= len(core)


def test_assembled_net_verifier_builds_and_keeps_regions() -> None:
    out = dossier.build_chain_net_verifier()
    assert isinstance(out, str) and out
    for anchor in (
        _MINILANG_START, _MINILANG_END, _FARKAS_START, _FARKAS_END,
    ):
        assert out.count(anchor) == 1, (
            "assembled net verifier missing/duplicated anchor: " + anchor
        )
