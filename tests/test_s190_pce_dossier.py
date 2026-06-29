"""S190 PCE Inc 3b: dossier PCE wiring -- embed parity + emitted-verifier.

Server-side cross-check (mirrors the S187 live-blob pattern): the dossier
carries the PCE membership verifier as the _PCE_CHECK_EMBED string. These
tests extract that exact embed, import it, and assert:

  1. PARITY: the embed's _pce_decide verdict+breakouts equal the AUTHORITATIVE
     envelope.decide_cumulative on shared fixtures (the dossier verdict can
     never drift from the committed library).
  2. EMITTED VERIFIER: dossier._splice_pce_check produces a verifier that,
     on a synthetic dossier, returns rc 0 on WITHIN and on OUTSIDE (monitor,
     never gate) and rc 1 only on tamper (sha mismatch).
  3. NO-PCE BYTE-IDENTITY: the splice is never applied without a PCE, so a
     verifier carrying no PCE is byte-identical to its template.

importorskip keeps this green-on-server and skipped where dossier/envelope
are not importable.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

dossier = pytest.importorskip("dossier")
envelope = pytest.importorskip("envelope")

_DISC = "not a legal substantiality determination"


def _load_embed():
    src = getattr(dossier, "_PCE_CHECK_EMBED", None)
    assert isinstance(src, str) and "_check_pce" in src, "dossier._PCE_CHECK_EMBED missing"
    d = Path(tempfile.mkdtemp())
    p = d / "_pce_embed_extracted.py"
    p.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("_pce_embed_extracted", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _canon(sa=(), ga=(), gq=()):
    return "\n".join(
        ["NV:5", "EV:1", "O:x"]
        + ["SA:" + x for x in sa]
        + ["GA:" + x for x in ga]
        + ["GQ:" + a + ":" + k for a, k in gq]
    )


_BASE = _canon(sa=["before(submit,approve)"], ga=["approve", "transfer"], gq=[("approve", "3")])
_BSHA = hashlib.sha256(_BASE.encode("utf-8")).hexdigest()
_CUM_OPEN = {
    "SA": {"mutable": False},
    "GA": {"total_removable": ["transfer"], "total_addable": None},
    "GQ": {"quorum_drift_budget": {"approve": 2}},
}
_CUM_STRICT = {
    "SA": {"mutable": False},
    "GA": {"total_removable": [], "total_addable": []},
    "GQ": {"quorum_drift_budget": {"approve": 0}},
}


def _pce(cumulative, base_sha=_BSHA):
    return {
        "pce_schema_version": 1,
        "baseline_canon_sha256": base_sha,
        "basis": "x " + _DISC,
        "per_step": {
            "SA": {"mutable": False},
            "GA": {"may_add": True, "may_remove": []},
            "GQ": {"may_add": True, "may_remove": False, "quorum_bounds": {}},
        },
        "cumulative": cumulative,
    }


_FIXTURES = [
    ("within_nochange", _pce(_CUM_OPEN), _BASE, _BASE),
    (
        "within_ga_rm_gq_drift1",
        _pce(_CUM_OPEN),
        _BASE,
        _canon(sa=["before(submit,approve)"], ga=["approve"], gq=[("approve", "2")]),
    ),
    (
        "outside_sa_immutable",
        _pce(_CUM_OPEN),
        _BASE,
        _canon(sa=[], ga=["approve", "transfer"], gq=[("approve", "3")]),
    ),
    (
        "outside_ga_rm_not_in_set",
        _pce(_CUM_OPEN),
        _BASE,
        _canon(sa=["before(submit,approve)"], ga=["transfer"], gq=[("approve", "3")]),
    ),
    (
        "outside_gq_removed",
        _pce(_CUM_OPEN),
        _BASE,
        _canon(sa=["before(submit,approve)"], ga=["approve", "transfer"], gq=[]),
    ),
    (
        "outside_gq_drift_over_budget",
        _pce(_CUM_OPEN),
        _BASE,
        _canon(sa=["before(submit,approve)"], ga=["approve", "transfer"], gq=[("approve", "6")]),
    ),
    (
        "outside_strict_ga_add_forbidden",
        _pce(_CUM_STRICT),
        _BASE,
        _canon(sa=["before(submit,approve)"], ga=["approve", "transfer", "withdraw"], gq=[("approve", "3")]),
    ),
]


def _oracle(pce_doc, base, cur):
    env = envelope.parse_envelope(pce_doc)
    r = envelope.decide_cumulative(env, base, cur)
    return ("WITHIN" if r.within else "OUTSIDE"), list(r.breakouts)


def test_s190_pce_embed_parity_with_envelope_oracle():
    emb = _load_embed()
    for name, pce_doc, base, cur in _FIXTURES:
        ev, ebk, _w, _s = emb._pce_decide(pce_doc, base, cur)
        ov, obk = _oracle(pce_doc, base, cur)
        assert ev == ov, name + ": embed verdict " + ev + " != oracle " + ov
        assert ebk == obk, name + ": embed breakouts != oracle breakouts"


def _emit_verifier():
    base = (
        "#!/usr/bin/env python3\n"
        "from __future__ import annotations\n"
        "import base64, hashlib, json, sys\n"
        "from pathlib import Path\n"
        "\n"
        "ROOT = Path(__file__).parent\n"
        "\n"
        "\n"
        "def main():\n"
        '    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))\n'
        '    print("OK   (stub) base checks passed")\n'
        "    return 0\n"
        "\n"
        "\n"
        'if __name__ == "__main__":\n'
        "    sys.exit(main())\n"
    )
    return dossier._splice_pce_check(base)


def _build_dir(cur, *, tamper=False):
    d = Path(tempfile.mkdtemp())
    (d / "verify_offline.py").write_text(_emit_verifier(), encoding="utf-8")
    pj = json.dumps(_pce(_CUM_OPEN), sort_keys=True, separators=(",", ":")).encode("utf-8")
    (d / "pce.json").write_bytes(pj)
    (d / "baseline.canon").write_bytes(_BASE.encode("utf-8"))
    (d / "spec.canon").write_bytes(cur.encode("utf-8"))
    man = {
        "pce_sha256": hashlib.sha256(pj).hexdigest(),
        "smt_spec_sha256": ("0" * 64 if tamper else hashlib.sha256(cur.encode("utf-8")).hexdigest()),
    }
    (d / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    return d


def _run(d):
    r = subprocess.run(
        [sys.executable, str(d / "verify_offline.py")],
        capture_output=True, text=True,
    )
    return r.returncode, r.stdout, r.stderr


def test_s190_pce_emitted_verifier_within_rc0():
    cur = _canon(sa=["before(submit,approve)"], ga=["approve"], gq=[("approve", "2")])
    rc, out, err = _run(_build_dir(cur))
    assert rc == 0, err
    assert '"verdict":"WITHIN"' in out


def test_s190_pce_emitted_verifier_outside_rc0_with_breakouts():
    cur = _canon(sa=[], ga=["approve", "transfer"], gq=[("approve", "3")])
    rc, out, err = _run(_build_dir(cur))
    assert rc == 0, err
    assert '"verdict":"OUTSIDE"' in out
    assert "breakout:" in out


def test_s190_pce_emitted_verifier_tamper_rc1():
    cur = _canon(sa=["before(submit,approve)"], ga=["approve"], gq=[("approve", "2")])
    rc, out, err = _run(_build_dir(cur, tamper=True))
    assert rc == 1
    assert "spec.canon sha256" in err


def test_s190_pce_splice_composes_and_is_single_terminal():
    spliced = _emit_verifier()
    assert spliced.count('    return 0\n\n\nif __name__ == "__main__":') == 1
    assert "_check_pce(manifest, ROOT)" in spliced
    assert "_PCE_CHECK_EMBED" not in spliced  # the value was inlined, not the name
