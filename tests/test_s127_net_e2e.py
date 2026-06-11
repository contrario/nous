"""S127 blocking-net-full adversarial e2e tests.

A full-mode chain dossier carries per-link source.nous (sha-gated by each
link's signed source_sha256) and one self-certifying blocking-net bundle
per non-vacuous hop. The emitted verifier RE-DERIVES the obligation
OR(prev_sigs) AND AND(NOT cur_sigs) from the two authenticated sources,
never trusting a bundle. These tests prove: a clean chain admits; a forged
carried source fails offline; a deleted net bundle fails offline; net
shrink refuses at issuance; a threshold-only chain carries no net files;
and a forged net multiplier fails offline arithmetic.

# __s127_net_e2e_test_v1__
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


# Two source variants. NET_WIDE blocks a strictly LARGER region than
# NET_NARROW on amount (>2000 contains >4000), so NARROW -> WIDE grows the
# net (contained) and WIDE -> NARROW shrinks it (refused).
def _src(amount_threshold: str, cost_cap: str) -> str:
    return (
        "world NetChain {\n"
        "    law CostCeiling = $0.50 per cycle\n"
        "    heartbeat = 10s\n"
        "    cost_cap: " + cost_cap + " USD\n"
        "    max_ticks: 1\n"
        "    policy BlockHighAmount {\n"
        '        kind: "loan.decision"\n'
        "        signal: amount > " + amount_threshold + "\n"
        "        weight: 10.0\n"
        "        action: block\n"
        "    }\n"
        "    policy LogAllDecisions {\n"
        '        kind: "loan.decision"\n'
        "        signal: true\n"
        "        weight: 1.0\n"
        "        action: log_only\n"
        "    }\n"
        "}\n"
        "message LoanApplication {\n"
        "    application_id: string\n"
        "    amount: float\n"
        "}\n"
        "soul Underwriter {\n"
        "    mind: claude-haiku-4-5 @ Tier0A\n"
        "    tokens: input = 500 output = 200\n"
        "    senses: [http_get]\n"
        "    memory {\n"
        "        evaluated: int = 0\n"
        "    }\n"
        "    instinct {\n"
        "        let app = listen Intake::LoanApplication\n"
        "        guard app != null else sleep 5s\n"
        "        speak LoanApplication(application_id: app.application_id, "
        "amount: app.amount)\n"
        "        remember evaluated = evaluated + 1\n"
        "    }\n"
        "    heal {\n"
        "        on timeout => retry(2, timeout)\n"
        "    }\n"
        "}\n"
    )


def _nous_cli() -> str:
    exe = shutil.which("nous")
    if exe is None:
        pytest.skip("nous CLI not on PATH")
    return exe


def _run(args, cwd=None):
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, timeout=120
    )


def _verify(
    nous, src, man, cost_cap, amount_thr, full, prev_manifest
):
    src.write_text(_src(amount_thr, cost_cap), encoding="utf-8")
    vargs = [nous, "verify", str(src), "--smt", "--manifest-out", str(man)]
    if prev_manifest is not None:
        vargs += ["--supersedes", str(prev_manifest)]
        if full:
            vargs += ["--chain-coverage", "full"]
    return _run(vargs)


def _dossier(nous, src, man, dout, prev_dossier):
    dargs = [nous, "dossier", str(src), "--manifest", str(man),
             "--output", str(dout)]
    if prev_dossier is not None:
        dargs += ["--supersedes", str(prev_dossier)]
    return _run(dargs)


def _build_full_chain(nous, tmp):
    # link 1 (genesis): block amount > 4000
    s1 = tmp / "s1.nous"
    m1 = tmp / "m1.json"
    r = _verify(nous, s1, m1, "0.50", "4000", False, None)
    assert r.returncode == 0, r.stderr
    d1 = tmp / "d1"
    r = _dossier(nous, s1, m1, d1, None)
    assert r.returncode == 0, r.stderr
    # link 2: block amount > 2000 (net grows: >2000 contains >4000)
    s2 = tmp / "s2.nous"
    m2 = tmp / "m2.json"
    r = _verify(nous, s2, m2, "0.40", "2000", True, m1)
    assert r.returncode == 0, r.stderr
    d2 = tmp / "d2"
    r = _dossier(nous, s2, m2, d2, d1)
    assert r.returncode == 0, r.stderr
    return d2


def test_full_chain_admits(tmp_path: Path) -> None:
    nous = _nous_cli()
    d2 = _build_full_chain(nous, tmp_path)
    assert (d2 / "chain" / "000_source.nous").is_file()
    assert (d2 / "chain" / "000_net.farkas.json").is_file()
    r = _run([sys.executable, "verify_offline.py"], cwd=str(d2))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "blocking-net containment verified" in r.stdout
    assert "VERDICT: PASS" in r.stdout


def test_forged_carried_source_fails_offline(tmp_path: Path) -> None:
    nous = _nous_cli()
    d2 = _build_full_chain(nous, tmp_path)
    src_path = d2 / "chain" / "000_source.nous"
    src_path.write_bytes(src_path.read_bytes() + b"\n# tamper\n")
    r = _run([sys.executable, "verify_offline.py"], cwd=str(d2))
    assert r.returncode != 0
    assert "does not match the signed source_sha256" in (
        r.stdout + r.stderr
    )


def test_deleted_net_bundle_fails_offline(tmp_path: Path) -> None:
    nous = _nous_cli()
    d2 = _build_full_chain(nous, tmp_path)
    (d2 / "chain" / "000_net.farkas.json").unlink()
    r = _run([sys.executable, "verify_offline.py"], cwd=str(d2))
    assert r.returncode != 0
    assert "containment bundle missing" in (r.stdout + r.stderr)


def test_forged_net_multiplier_fails_offline(tmp_path: Path) -> None:
    nous = _nous_cli()
    d2 = _build_full_chain(nous, tmp_path)
    net_path = d2 / "chain" / "000_net.farkas.json"
    doc = json.loads(net_path.read_text(encoding="utf-8"))
    doc["certs"][0]["multipliers"][0] = "-1"
    net_path.write_text(json.dumps(doc), encoding="utf-8")
    r = _run([sys.executable, "verify_offline.py"], cwd=str(d2))
    assert r.returncode != 0
    assert "BLOCKING-NET REGRESSION" in (r.stdout + r.stderr)


def test_net_shrink_refused_at_issuance(tmp_path: Path) -> None:
    nous = _nous_cli()
    # genesis blocks amount > 2000; successor blocks amount > 4000 (shrinks)
    s1 = tmp_path / "s1.nous"
    m1 = tmp_path / "m1.json"
    r = _verify(nous, s1, m1, "0.50", "2000", False, None)
    assert r.returncode == 0, r.stderr
    d1 = tmp_path / "d1"
    assert _dossier(nous, s1, m1, d1, None).returncode == 0
    s2 = tmp_path / "s2.nous"
    m2 = tmp_path / "m2.json"
    r = _verify(nous, s2, m2, "0.40", "4000", True, m1)
    assert r.returncode == 0, r.stderr
    d2 = tmp_path / "d2"
    r = _dossier(nous, s2, m2, d2, d1)
    assert r.returncode != 0
    assert "blocking-net containment REFUSED" in (r.stdout + r.stderr)


def test_threshold_only_chain_carries_no_net_files(tmp_path: Path) -> None:
    nous = _nous_cli()
    # same chain WITHOUT --chain-coverage full
    s1 = tmp_path / "s1.nous"
    m1 = tmp_path / "m1.json"
    assert _verify(
        nous, s1, m1, "0.50", "4000", False, None
    ).returncode == 0
    d1 = tmp_path / "d1"
    assert _dossier(nous, s1, m1, d1, None).returncode == 0
    s2 = tmp_path / "s2.nous"
    m2 = tmp_path / "m2.json"
    assert _verify(
        nous, s2, m2, "0.40", "2000", False, m1
    ).returncode == 0
    d2 = tmp_path / "d2"
    assert _dossier(nous, s2, m2, d2, d1).returncode == 0
    assert not (d2 / "chain" / "000_net.farkas.json").exists()
    assert not (d2 / "chain" / "000_source.nous").exists()
    r = _run([sys.executable, "verify_offline.py"], cwd=str(d2))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "blocking-net containment" not in r.stdout
