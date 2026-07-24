# NOUS-TRACE Reference Implementation — Results

**Date:** 2026-07-21
**Spec:** 0.2.0-draft
**Components:** `verifier.py` (445 lines, self-contained), `vectorgen.py` (411 lines, reference Producer/Signer for vectors), `run_tests.py` (harness)
**Dependencies:** Python 3.12, `cryptography` (Ed25519). Nothing else.
**Status:** dated point-in-time report, superseded by `trace/SPEC.md`. The spec revision and line counts above are as of the date above and are NOT updated here; SPEC.md is current. <!-- __s257_results_truth_pass_v1__ -->

## Conformance matrix — 13/13

| vector | expected | result |
|---|---|---|
| golden | VALID / exit 0 | PASS |
| t01 edited body | INVALID(SIG_INVALID) | PASS |
| t02 dropped event | INVALID(SEQ_ORDER) | PASS |
| t03 reordered events | INVALID(SEQ_ORDER) | PASS |
| t04 post-anchor forgery (attacker holds Runtime Key, not anchor) | INVALID(ANCHOR_INVALID) | PASS |
| t05 reused salt | INVALID(SALT_REUSE) | PASS |
| t06 verdict/assignment mismatch (dishonest checker, valid anchors) | INVALID(VERDICT_MISMATCH) | PASS |
| t07 missing evidence payload | INVALID(ASSIGNMENT_MISSING) | PASS |
| t08 wrong-tag signature | INVALID(SIG_INVALID) | PASS |
| t09 expired runtime key vs anchor time | INVALID(KEY_EXPIRED) | PASS |
| t10 backdated ts_wall beyond tolerance | INVALID(TIME_BOUND_VIOLATION) | PASS |
| t11 float in signed structure | INVALID(FLOAT_IN_SIGNED) | PASS |
| t12 truncated tail after last anchor | INTEGRITY-OK/INCOMPLETE / exit 10 | PASS |

Golden report demonstrates: independent predicate recomputation (1 proved + 1 declared obligation), a legitimately erased content payload not affecting validity, dual anchored checkpoints with time bounding.

Notable properties exercised:

- t04 demonstrates the anchor separation: an attacker with the Runtime Key rebuilds a fully self-consistent chain (valid sigs, valid Merkle roots, valid root_sig) and still fails, because the anchor token cannot be regenerated.
- t06 demonstrates recomputation: the trace is cryptographically perfect end-to-end; only the Verifier's own evaluation of the predicate over the recorded assignment exposes the lie.
- t08 demonstrates domain separation: a signature made under the checkpoint-root tag over the correct event hash does not verify as an event signature.

## Spec errata discovered during implementation (fold into v0.2.1)

1. **Checkpoint coverage rule was ambiguous.** Resolved: range `from_seq` of checkpoint N equals the `seq` of checkpoint N−1 (first range starts at 0), i.e. each checkpoint Event is Merkle-covered by the *next* checkpoint. The final checkpoint is covered by chain, signature, and its own anchor only.
2. **NOUS-EXPR concrete encoding was unspecified.** Implemented JSON AST: literals `{"int":n} {"str":s} {"bool":b} {"set":[...]}`, variables `{"var":name}`, connectives `{"op":"and|or","args":[...]}`, `{"op":"not","arg":…}`, comparisons/arithmetic `{"op":…,"left":…,"right":…}`. Must become normative.
3. **Payload Store entry format was unspecified.** Implemented: JSON `{salt: hex, media_type, data: base64}`, filename = salted hash.
4. **Wrong-tag attacks are reported as SIG_INVALID**, not a distinct code: indistinguishable by construction. Spec test-vector table should say so.
5. **Anchor backend for vectors** is `rfc3161-sim` (pinned anchor key signs `SHA-256(root‖gen_time)` under a dedicated tag). Structurally equivalent to a TSA token; real RFC 3161 (ASN.1) and Rekor backends are integration work, behind the same interface. This is a declared simulation, not a shortcut hidden in the claims.
6. **Verifier fail-closed order** (which check fires first for multi-fault traces) is now defined by the implementation's normative sequence; v0.2.1 should state that expected reason codes in vectors refer to the *first* check in §12.2 order.

## Next steps (in order)

1. **[SHIPPED]** Fold errata into spec v0.2.1.
2. **[SHIPPED]** Real anchor backends: RFC 3161 client (asn1crypto) + Rekor inclusion-proof verification.
3. **[SHIPPED]** Signer as a standalone process (UDS + SO_PEERCRED) — currently an in-process class enforcing the same monotonicity contract.
4. **[OPEN]** Producer adapter inside AetherLang; first dogfood target: greek_tax_advisor WhatsApp flow.
