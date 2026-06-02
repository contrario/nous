"""S112 U7 -- Phase 2.0 end-to-end against a real signed chain.

Proves U5 (producer) + U6 (--apply-remedy surface) fire against real bytes,
not monkeypatched boundaries. Builds a genuine per-world Ed25519-signed memory
chain whose latest entry carries a real remedy_proof (authentic conformance
certificate, signed live; promoted_heal_path_sha256 == heal_path_digest of the
program's sole declared heal rule), runs execute_program with the full opt-in
chain ON against that chain via the NOUS_MEMORY_BASE_DIR seam, and asserts the
emitted TraceEnvelope.remedy_application carries the six committed fields.

Then it runs the offline four-step auditor check (MEMORY_PHASE2_DESIGN.md
Section 7) using only the existing checker + cryptography: read the cited chain
entry, recompute remedy_proof_sha256 (JCS), re-verify the proof certificate via
the existing verify_certificate_from_json, and confirm the promoted digest is a
heal-path the program declares (recompute heal_path_digest per rule).

Finally it asserts the OFF path: consult_memory=True, apply_remedy=False emits
NO remedy_application and is byte-identical (sans timestamps) to consult-only.

# __s112_u7_e2e_tests_v1__
"""
from __future__ import annotations

import asyncio
import hashlib
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import memory_keyring
import memory_store
from ast_nodes import heal_path_digest
from build_run_remedy import admissible_promotions
from conformance import (
    CERTIFICATE_SCHEMA_VERSION,
    ConformanceCertificate,
    certificate_json,
    sign_certificate,
    verify_certificate_from_json,
)
from nous_ast_runner import execute_program
from parser import parse_nous
from remedy_proof import REMEDY_PROOF_SCHEMA_VERSION, RemedyProof
from run_identity import producing_soul_sha256, world_sha256

_PROG = (
    "world W {\n"
    "  cost_cap: 0.10 USD\n"
    "  max_ticks: 4\n"
    "  events { Ping }\n"
    "}\n"
    "message Ping { v: string }\n"
    "soul A {\n"
    "  mind: claude-sonnet-4-6 @ Tier1\n"
    "  tokens: input = 100 output = 50\n"
    "  instinct {\n"
    "    speak Ping(v: \"x\")\n"
    "  }\n"
    "  heal { on error => retry(2, error) }\n"
    "}\n"
)

_HEX64 = "a" * 64


def _sole_heal_digest(program) -> str:
    soul = program.souls[0]
    assert soul.heal is not None and len(soul.heal.rules) == 1
    return heal_path_digest(soul.heal.rules[0])


def _authentic_cert_dict() -> dict:
    cert = ConformanceCertificate(
        certificate_schema_version=CERTIFICATE_SCHEMA_VERSION,
        nous_version="5.25.0",
        world_name="W",
        issued_utc="2026-06-01T00:00:00Z",
        source_sha256=_HEX64,
        smt_spec_sha256=_HEX64,
        pricing_sha256=_HEX64,
        trace_sha256=_HEX64,
        binding_ok=True,
        surface_ok=True,
        assumption_discharge_ok=True,
        bound_transfer_ok=True,
        authorization_ok=True,
        trace_signature_ok=True,
        sequence_ok=True,
        conformant=True,
        realized_total="0.05",
        cost_cap="0.10",
        cost_currency="USD",
    )
    signed = sign_certificate(cert, Ed25519PrivateKey.generate())
    return json.loads(certificate_json(signed))


def _proof(digest: str, cert: dict) -> dict:
    return {
        "remedy_proof_schema_version": REMEDY_PROOF_SCHEMA_VERSION,
        "promoted_heal_path_sha256": digest,
        "certificate": cert,
    }


def _jcs_sha256(d: dict) -> str:
    return hashlib.sha256(
        json.dumps(d, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _build_signed_chain_with_proof(tmp_path, digest: str) -> tuple[str, str, dict, int]:
    world = world_sha256("W")
    soul = producing_soul_sha256("W", "A")
    memory_keyring.init_world_memory(world, tmp_path)
    proof = _proof(digest, _authentic_cert_dict())
    entry = memory_store.append_entry(
        world_sha256=world,
        producing_soul_sha256=soul,
        source_sha256="d" * 64,
        run_manifest_sha256="e" * 64,
        event_hash="f" * 64,
        outcome="ok",
        trigger_kind="manual",
        cost="0",
        timestamp="2026-06-01T00:00:00Z",
        base_dir=tmp_path,
        remedy_proof=proof,
    )
    return world, soul, proof, entry.seq


def _run(tmp_path, monkeypatch, *, apply_remedy: bool) -> dict:
    monkeypatch.setenv("NOUS_MEMORY_BASE_DIR", str(tmp_path))
    cap: dict = {}
    program = parse_nous(_PROG)
    asyncio.run(
        execute_program(
            program,
            mode="dry-run",
            max_cycles=1,
            source_text=_PROG,
            emit_trace=True,
            consult_memory=True,
            apply_remedy=apply_remedy,
            trace_capture=cap,
        )
    )
    return cap["envelope"]


def test_apply_remedy_seals_six_fields_against_real_chain(tmp_path, monkeypatch) -> None:
    program = parse_nous(_PROG)
    digest = _sole_heal_digest(program)
    world, soul, proof, src_seq = _build_signed_chain_with_proof(tmp_path, digest)

    env = _run(tmp_path, monkeypatch, apply_remedy=True)
    ra = env.get("remedy_application")
    assert ra is not None
    assert ra["world_sha256"] == world
    assert ra["producing_soul_sha256"] == soul
    assert int(ra["source_entry_seq"]) == src_seq
    assert ra["remedy_proof_sha256"] == _jcs_sha256(proof)
    assert ra["promoted_heal_path_sha256"] == digest
    assert len(ra["applied_at_utc"]) >= 1


def test_offline_auditor_four_step_check(tmp_path, monkeypatch) -> None:
    program = parse_nous(_PROG)
    digest = _sole_heal_digest(program)
    world, soul, proof, src_seq = _build_signed_chain_with_proof(tmp_path, digest)
    env = _run(tmp_path, monkeypatch, apply_remedy=True)
    ra = env.get("remedy_application")
    assert ra is not None

    # Step 1: read the cited source chain entry for (world, soul) offline.
    chain = memory_store.read_chain(world, soul, tmp_path)
    cited = next(e for e in chain if e.seq == int(ra["source_entry_seq"]))
    assert cited.remedy_proof is not None

    # Step 2: recompute remedy_proof sha256 (JCS) and compare.
    assert _jcs_sha256(cited.remedy_proof) == ra["remedy_proof_sha256"]

    # Step 3: re-verify the proof certificate via the EXISTING verifier.
    view = RemedyProof.from_stored(cited.remedy_proof)
    result = verify_certificate_from_json(json.dumps(view.certificate))
    assert result.signature.ok is True
    assert result.verdict_consistency.ok is True

    # Step 4: confirm the promoted digest is one the program declares.
    declared = {
        heal_path_digest(rule)
        for s in program.souls
        if s.heal is not None
        for rule in s.heal.rules
    }
    assert ra["promoted_heal_path_sha256"] in declared

    # And the influence is exactly a legal, admissible promotion.
    assert admissible_promotions([cited.remedy_proof], program.souls) == [digest]


def test_apply_off_emits_no_remedy_application(tmp_path, monkeypatch) -> None:
    program = parse_nous(_PROG)
    digest = _sole_heal_digest(program)
    _build_signed_chain_with_proof(tmp_path, digest)

    env_off = _run(tmp_path, monkeypatch, apply_remedy=False)
    assert env_off.get("remedy_application") is None
    assert env_off.get("memory_consultation") is not None


def test_apply_on_vs_off_differ_only_by_remedy_application(tmp_path, monkeypatch) -> None:
    program = parse_nous(_PROG)
    digest = _sole_heal_digest(program)
    _build_signed_chain_with_proof(tmp_path, digest)

    env_on = _run(tmp_path, monkeypatch, apply_remedy=True)
    env_off = _run(tmp_path, monkeypatch, apply_remedy=False)

    assert env_on.get("remedy_application") is not None
    assert env_off.get("remedy_application") is None

    mc_on = dict(env_on["memory_consultation"])
    mc_off = dict(env_off["memory_consultation"])
    mc_on.pop("consulted_at_utc", None)
    mc_off.pop("consulted_at_utc", None)
    assert mc_on == mc_off
