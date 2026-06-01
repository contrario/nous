"""S110 U3 -- the build_run_remedy admissibility gate (Phase 2.0).

Pure predicate. Given a list of stored remedy_proof dicts and the current
program's souls, decide which promoted heal-paths are ADMISSIBLE for promotion
this run. Touches no signed bytes, emits nothing, performs no I/O and no
network. Promotion ORDERING is a later unit (U5); this gate only decides
admissibility, and refuses -- fail-closed -- when the consulted memory is
inconsistent with the current program.

A promotion is admissible only if all three hold, evaluated in this exact
order:

  (a) PARSE      -- the stored dict parses via RemedyProof.from_stored (U2),
                    fail-closed. A malformed proof raises RemedyProofError
                    (propagated from U2); it is a corrupt input, not a
                    non-admission.
  (b) AUTHENTIC  -- the embedded conformance certificate re-verifies via the
                    EXISTING pure conformance.verify_certificate_from_json
                    (no new crypto, no TCB growth). The remedy_proof carries
                    ONLY the certificate, so only the two cert-self-contained
                    checks can run: the certificate Ed25519 signature over its
                    canonical body (check 1) and the recorded-obligation /
                    conformant consistency (check 5). The trace and manifest
                    binding checks are structurally out of reach -- the proof
                    does not carry trace.json or manifest.json -- so the
                    callable returns verdict INCONCLUSIVE with those binding
                    checks marked skipped (not failed). That is expected and
                    correct: this is the advisory-but-authenticated boundary
                    documented in remedy_proof.py. A proof whose certificate
                    signature does not verify, or whose recorded verdict is
                    inconsistent with its obligation booleans, is silently
                    NON-ADMISSIBLE (excluded from the result, not raised).
  (c) DECLARED   -- promoted_heal_path_sha256 is a heal-path the CURRENT
                    program declares: recompute heal_path_digest (U1) over
                    every soul.heal.rules and require a match. This is what
                    closes the U2 program-binding gap: the signed trace
                    records no heal-path, so the proof is PROGRAM-BOUND, not
                    run-bound. A digest the current program does not declare
                    is silently NON-ADMISSIBLE (excluded, not raised) -- it
                    has no (soul, error_type) to resolve and never reaches the
                    conflict check.

Then, over the SURVIVORS only (parsed + authentic + declared):

  (d) FQ2 CONFLICT -- refuse-on-conflict, fail-closed, GLOBAL abort. The
                    conflict key is (soul_name, error_type), not the bare
                    digest and not the bare error_type:
                      - per-soul, because heal dispatch is per-soul
                        (codegen emits _soul_<name>.heal); two souls that
                        share an error_type name are different trigger
                        classes and never compete.
                      - whole-rule digests (error_type + actions), so two
                        identical digests under one key are the SAME path and
                        collapse (not a conflict); two DIFFERENT digests under
                        one key promote different recoveries for the same
                        trigger in the same soul -- only one can fire first --
                        and that is the FQ2 conflict.
                    Any single conflict aborts the WHOLE call (no promotions
                    applied; the run proceeds in pure default order). Refusing
                    every promotion -- not just the conflicted key -- is the
                    fail-closed reading: a conflict signals that the consulted
                    memory is inconsistent with the current program (a
                    state-level anomaly), so no promotion from that memory is
                    trusted. The raise carries the conflicting key and both
                    colliding digests so the refusal is diagnosable from the
                    exception alone, without re-running the gate.

# __s110_u3_build_run_remedy_module_v1__
"""
from __future__ import annotations

import json

from ast_nodes import SoulNode, heal_path_digest
from conformance import verify_certificate_from_json
from remedy_proof import RemedyProof
from run_identity import MemoryConsultationError


def _program_heal_path_index(
    souls: list[SoulNode],
) -> dict[str, set[tuple[str, str]]]:
    """Map every declared heal-path digest to the set of (soul_name,
    error_type) keys that declare it in the current program.

    A digest can map to more than one key only if byte-identical heal rules
    are declared under different keys; identical digest means identical path,
    so such entries collapse naturally when resolved per key.
    """
    index: dict[str, set[tuple[str, str]]] = {}
    for soul in souls:
        if soul.heal is None:
            continue
        for rule in soul.heal.rules:
            digest = heal_path_digest(rule)
            key = (soul.name, rule.error_type)
            index.setdefault(digest, set()).add(key)
    return index


def _certificate_is_authentic(proof: RemedyProof) -> bool:
    """Run the two cert-self-contained checks via the existing pure verifier.

    Cert-only (no trace_json, no manifest_json), so the verdict is
    INCONCLUSIVE by design; admissibility keys on the two checks that DO run
    cert-only -- signature and verdict_consistency -- never on the verdict.
    A MALFORMED certificate sets signature.ok False, so requiring
    signature.ok True also excludes MALFORMED.
    """
    result = verify_certificate_from_json(json.dumps(proof.certificate))
    return bool(result.signature.ok) and bool(result.verdict_consistency.ok)


def admissible_promotions(
    stored_proofs: list[object],
    souls: list[SoulNode],
) -> list[str]:
    """Return the deduplicated list of promoted_heal_path_sha256 digests that
    are admissible for promotion this run.

    Order of evaluation per proof: parse (a) -> authentic (b) -> declared (c).
    Then FQ2 conflict (d) over survivors, keyed on (soul_name, error_type),
    global-abort fail-closed.

    Raises:
        RemedyProofError: a stored proof is malformed (propagated from U2).
        MemoryConsultationError: an FQ2 (soul, error_type) conflict -- two
            admissible proofs promote different heal-paths for the same
            trigger in the same soul. The message carries the key and both
            colliding digests. No promotion is applied; the caller proceeds
            in default order.
    """
    index = _program_heal_path_index(souls)

    admissible_digests: list[str] = []
    seen_digests: set[str] = set()
    for stored in stored_proofs:
        proof = RemedyProof.from_stored(stored)
        digest = proof.promoted_heal_path_sha256
        if not _certificate_is_authentic(proof):
            continue
        if digest not in index:
            continue
        if digest in seen_digests:
            continue
        seen_digests.add(digest)
        admissible_digests.append(digest)

    key_to_digest: dict[tuple[str, str], str] = {}
    for digest in admissible_digests:
        for key in sorted(index[digest]):
            existing = key_to_digest.get(key)
            if existing is None:
                key_to_digest[key] = digest
            elif existing != digest:
                raise MemoryConsultationError(
                    "FQ2 promotion conflict for trigger "
                    + repr(key)
                    + ": two admissible remedy_proofs promote different "
                    "heal-paths for the same (soul, error_type); promotion "
                    "refused globally, run proceeds in default order. "
                    "colliding digests: "
                    + existing
                    + " and "
                    + digest
                )

    return admissible_digests
