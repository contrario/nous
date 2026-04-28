# SMT Verification Design

**Status:** Design document, Session 61. Implementation begins Session 62.
**Companion to:** [`EU_AI_ACT_COMPLIANCE.md`](./EU_AI_ACT_COMPLIANCE.md)

This document specifies the architecture for adding SMT-verified
compilation to NOUS. The implementation arc spans Sessions 62-65 and
closes the only material gap in NOUS's EU AI Act compliance matrix
(Article 15: Accuracy, Robustness and Cybersecurity).

---

## 1. Goal

Make this true:

> **NOUS is the first agentic programming language where you can
> mathematically prove that your agent never violates its declared
> constraints, before deploying.**

No other agentic language ships verified-by-construction safety today.
LangGraph, CrewAI, AutoGen, MetaGPT are Python libraries with empirical
guardrails (red-teaming, post-hoc filters). VeriGuard (arXiv 2510.05156)
applies SMT proofs per-action but is not a language. Dafny verifies
code but is not agentic. AetherProof signs manifests but is not a
language.

NOUS combines all three primitives -- declarative constitution,
deterministic replay, SMT-proven constraints -- in one stack.

---

## 2. Scope and Non-Goals

### In scope

- Compile-time mathematical proof that declared **cost bounds** hold
  across all execution paths.
- Compile-time mathematical proof that declared **forbidden actions**
  cannot fire under any sense input.
- Compile-time mathematical proof that **rate limits** cannot be
  exceeded.
- Counterexample extraction: when Z3 finds a path that violates a
  constraint, emit a deterministic replay trace showing exactly when
  and how.
- Cryptographic publication: every successfully-verified compilation
  produces an AetherProof signed manifest published on
  `api.aetherlang.online`.
- CLI surface: `nous verify --smt`, `nous audit <manifest_id>`.

### Out of scope (explicit non-goals)

- **Proving LLM output correctness.** LLMs are stochastic black boxes;
  no SMT can prove `llm.respond("X") == Y`. We prove only constraints
  on the *orchestration layer* (which actions the agent may take, what
  bounds those actions respect, what data they may access).
- **Proving runtime resource exhaustion.** OOMs and timeouts are
  operating-system concerns, not language semantics.
- **Termination of arbitrary user code.** NOUS is Turing-complete via
  loops; we prove invariants that hold *if execution terminates*, not
  termination itself.
- **Replacing tests.** SMT proofs cover declared constraints; tests
  cover behavior. Both are required.

This boundary is deliberate. It is the same boundary VeriGuard draws.
It is what makes the problem tractable.

---

## 3. The Pipeline

```
.nous source
     |
     v
  parser.py (Lark)            -> AST (Pydantic V2 nodes)
     |
     v
  validator.py                -> structural / semantic checks (existing)
     |
     v
  smt_emit.py     [NEW]       -> SMT-LIB constraint set
     |
     v
  smt_verify.py   [NEW]       -> Z3 solver
     |                              |
     |                              +-- UNSAT -> "proven safe", continue
     |                              |
     |                              +-- SAT   -> counterexample model
     |                                            |
     |                                            v
     |                                   replay_emit.py [NEW]
     |                                            |
     |                                            v
     |                                   .replay trace + abort compile
     v
  codegen.py                  -> Python (existing)
     |
     v
  manifest_emit.py [NEW]      -> AetherProof signed manifest
     |
     v
  POST api.aetherlang.online  -> public, immutable, content-addressed
```

The dotted line: replay_emit.py reuses the existing Phase D event-log
machinery from `replay_runtime.py`. A counterexample is a deterministic
sequence of senses + LLM responses that reaches the violating state.
The auditor can replay it and observe the violation.

---

## 4. Module Specifications

### 4.1 `smt_emit.py` (Session 62-63)

**Purpose:** Walk the AST and emit SMT-LIB 2.6 constraints.

**Public API:**

```python
def emit_smt(program: NousProgram) -> SMTSpec:
    """Produce SMT-LIB constraints for a parsed NOUS program.

    Returns SMTSpec with:
      - declarations: typed variables for every cost, signal, action
      - assertions: constraints from laws, policies, cost_caps
      - obligations: properties to prove (negations are queried)
    """
```

**Emission rules (initial set, Session 62):**

| AST node                                     | SMT translation                                                |
|----------------------------------------------|----------------------------------------------------------------|
| `cost_cap: 0.05 USD`                         | `(declare-const total_cost Real)` + `(assert (<= total_cost 0.05))` |
| LLM call with model M, est. tokens N         | `(assert (= cost_call_i (* token_price_M N)))` |
| Sequential calls in `senses:` block          | `(assert (= total_cost (+ cost_call_1 ... cost_call_n)))` |
| Branching (`if X then call A else call B`)   | `(assert (=> X (= cost_branch cost_A)))` + symmetric |
| Loop with declared bound `<= N iterations`   | unrolled N times; without bound -> compile error |

**Session 63 additions:**

| AST node                                     | SMT translation                                                |
|----------------------------------------------|----------------------------------------------------------------|
| `forbid action <name>`                       | `(assert (not <name>_invoked))` -- prove unsat under any sense |
| `rate_limit: <action> <= N per <window>`     | finite-window counter, prove never exceeds N |
| `data_scope: <action> reads only <set>`      | type-level scope, prove no out-of-scope read predicate fires |

**Format:** SMT-LIB 2.6. Solver-agnostic in principle; Z3 only in
practice for Session 62.

<!-- __cost_cap_phase3a_design_note_v1__ -->
**Phase 3a status (Session 62):** AST/grammar foundations landed.
New constructs:
- `tokens: input=N output=M` (per soul) — declares upper-bound
  token count for SMT cost emission.
- `max_ticks: K` (per world) — bounds total execution length.
Both are mandatory under `--smt` (Phase 3c will wire the check).
Phase 5 extends `tokens` to interval ranges `[min,max]`.

---

### 4.2 `smt_verify.py` (Session 62)

**Purpose:** Run Z3 on the SMTSpec, return verdict.

**Public API:**

```python
@dataclass
class VerifyResult:
    proven_safe: bool
    counterexample: Optional[Z3Model]
    constraint_id: str         # which obligation failed
    elapsed_ms: int

def verify(spec: SMTSpec, timeout_ms: int = 30_000) -> VerifyResult:
    ...
```

**Dependency:** `z3-solver` (PyPI). Pinned to a specific version in
`pyproject.toml` extras: `[smt]`. Optional install -- core NOUS must
not require Z3.

<!-- __smt_z3_pin_note_v1__ -->
**Verified pin (2026-04-28, Session 62 Phase 1):**
`z3-solver>=4.15.0,<4.17.0`. PyPI latest at the time was `4.16.0.0`
(released 2026-02-19). The `"z3_version": "4.13.0"` value in the
manifest schema example below (§4.4) is illustrative; the live
manifest writes whatever Z3 version the compiling host has installed.

**Failure modes:**

- `unknown` (Z3 cannot decide within timeout) -> treated as failed
  proof. Compile aborts. Operator can extend `timeout_ms` or simplify
  constraints.
- `sat` (counterexample found) -> compile aborts, replay trace emitted.
- `unsat` of the negated obligation -> proof succeeds.

---

### 4.3 `replay_emit.py` (Session 63)

**Purpose:** Translate a Z3 counterexample into a deterministic replay
trace using the existing Phase D event-log format.

**Public API:**

```python
def emit_replay_from_counterexample(
    cex: Z3Model,
    program: NousProgram,
) -> Path:
    """Write a .replay file at /tmp/nous_cex_<hash>.replay.

    The file is a JSONL event log with synthetic sense + llm.response
    events that reach the violating state. Auditor can run:
        nous replay verify <file>
    """
```

**Why this matters:** auditors and regulators do not read SMT models.
They want a step-by-step trace. We give them the trace in the same
format we already use for production replay logs.

---

### 4.4 `manifest_emit.py` (Session 64)

**Purpose:** Sign and publish a compilation manifest via AetherProof.

**Manifest schema:**

```json
{
  "version": "1.0",
  "source_sha256": "...",
  "ast_sha256": "...",
  "policies_sha256": "...",
  "smt_obligations_sha256": "...",
  "smt_proof_status": "verified",
  "z3_version": "4.13.0",
  "compile_timestamp": "2026-04-28T...",
  "nous_version": "5.0.0",
  "ed25519_signature": "...",
  "root_of_trust_pubkey_sha256": "f95a45bdc15db8f6ef61fa853366e860726aefe16474e943ebe79b132a17e022"
}
```

**Publication:** `POST https://api.aetherlang.online/v1/manifests`.
Returns `request_id`; manifest is fetched via
`GET https://api.aetherlang.online/v1/manifests/{request_id}`.

**Verification flow (auditor side):**

```
$ nous audit  <request_id>
[1/4] Fetching manifest from api.aetherlang.online ... OK
[2/4] Verifying Ed25519 signature against root-of-trust ... OK
[3/4] Re-running SMT verification with stored obligations ... PROVEN
[4/4] Replaying source compilation byte-by-byte ... IDENTICAL

VERDICT: PASS. Manifest c8a1...e4f7 is authentic, complete, and
proves the constraints declared in the source.
```

---

### 4.5 CLI surface (Session 62-65)

**New flags:**

```
nous verify --smt              # default behavior in v5.0.0
nous verify --no-smt           # skip SMT for fast iteration
nous verify --smt-timeout 60s
nous compile --emit-manifest   # publish to AetherProof
nous compile --no-publish      # local manifest only
nous audit <manifest_id>       # auditor workflow
```

**Existing flags continue to work.** SMT is opt-in for Sessions 62-64,
becomes the default in v5.0.0 release (Session 65).

---

## 5. Session-by-Session Plan

### Session 62: Cost Bounds (Killer Feature 6)

**Deliverable:** `cost_cap: <amount> <currency>` constraint, proven by Z3.

- Z3 dependency added as `[smt]` optional install
- New AST node `CostCap(BaseModel)` with `amount: Decimal`, `currency: str`
- `smt_emit.py` covers cost arithmetic only
- `smt_verify.py` integrates Z3
- Test: a `.nous` program with `cost_cap: 0.05 USD` and 3 LLM calls
  totaling $0.07 -> compile fails with explicit overage report
- Regression: 0 changes to existing 54 templates (additive only)

**Exit criteria:** PYTEST_FLOOR raised by N (where N = number of new
SMT tests); 54/54 regression byte-identical; v4.13.0 released with
optional `[smt]` extra.

### Session 63: Full Law-Type Coverage

**Deliverable:** SMT emission for `forbid`, `rate_limit`, `data_scope`.

- Extend `smt_emit.py` to all law types currently in the validator
- `replay_emit.py` translates counterexamples to .replay files
- Test: deliberately broken policy -> Z3 finds counterexample -> .replay
  file produced -> `nous replay verify` confirms the violation
  reproduces deterministically
- Documentation: every law type in the grammar gets a "SMT semantics"
  section in the language reference

**Exit criteria:** Every grammar law type has an SMT translation and
at least one positive + one negative test; v4.14.0 released.

### Session 64: AetherProof Manifest Integration

**Deliverable:** Signed manifests, public API, auditor CLI.

- `manifest_emit.py` builds + signs the manifest
- `nous compile --emit-manifest` publishes to `api.aetherlang.online`
- `nous audit <id>` downloads, verifies, replays
- Server-side: extend AetherProof API to accept NOUS manifest schema
  (existing v1 schema for general LLM coding proofs, new v2 schema for
  NOUS programs)
- Test: round-trip compile -> publish -> audit -> verify, end-to-end

**Exit criteria:** A third party with only an `<manifest_id>` can
verify a NOUS program ran correctly and respected its declared
constraints; v4.15.0 released.

### Session 65: v5.0.0 Public Launch

**Deliverable:** Default-on SMT, full compliance dossier, public benchmark.

- `--smt` becomes default; `--no-smt` is opt-out
- `nous compile --emit-dossier` produces Annex IV-aligned PDF
- Compliance matrix doc updated: Article 15 status changes COVERED
- Benchmark: NOUS vs LangGraph on a fixed agent task, with NOUS
  reporting "proven safe" and LangGraph reporting "tested in 1000 runs"
- Blog post + Show HN submission + GitHub release notes
- Homepage hero updated: "AI Act Compliant by Construction"

**Exit criteria:** v5.0.0 on PyPI; public repository compliance dossier
example; at least one external user has invoked `nous audit` on their
own manifest.

---

## 6. Risks and Mitigations

| Risk                                         | Likelihood | Mitigation                                                |
|----------------------------------------------|------------|-----------------------------------------------------------|
| Z3 timeout on real programs                  | Medium     | Document patterns; offer `--smt-timeout`; provide simplification helpers |
| SMT-LIB emission grows unmaintainable        | Low        | One translation table per law type; lint test catches drift |
| AetherProof API outage                       | Low        | `--no-publish` falls back to local-only manifest |
| Digital Omnibus delays Aug 2026 enforcement  | Medium     | Compliance positioning has independent value (audit, debugging, formal correctness) |
| Contributors lack SMT background             | High       | Z3 stays optional; core NOUS unchanged for non-SMT users |
| User declares an unprovable constraint       | High       | Clear error messages; "if this happens, the constraint is not the kind of property SMT can decide" |

---

## 7. Open Architectural Questions

These are deferred to start-of-Session-62 discussion, not decided now:

1. **One SMT context per `.nous` file, or one per `world` block?**
   Per-file is simpler; per-world allows independent verification of
   composed worlds.

2. **Unrolling vs induction for loops with declared bounds.**
   Unrolling is simpler and matches Z3 strengths; induction handles
   unbounded loops but requires a loop-invariant declaration in the
   source. Probable answer: unrolling first, induction later.

3. **Manifest revocation semantics.** If a vulnerability is found in
   NOUS itself (not the user program), how do we mark previously-issued
   manifests as no-longer-trustworthy? Possible answer: add a
   `nous_version_min_compat` field; auditors check this against a
   public revocation list.

4. **Should Z3 version be pinned in the manifest, or is solver-version
   irrelevant if the proof is checkable?** Probable answer: pin it for
   reproducibility; later add a "re-prove with newer Z3" path.

---

## 8. Success Criteria for the Arc

By end of Session 65, all five must hold:

1. A `.nous` program with `cost_cap: X` either compiles with proof, or
   fails with a deterministic counterexample.
2. The same holds for `forbid`, `rate_limit`, `data_scope`.
3. Every successful compile produces a public, signed, content-addressed
   manifest.
4. `nous audit <id>` returns PASS or FAIL deterministically, with a
   human-readable report.
5. The EU AI Act compliance matrix shows COVERED on Article 15.

---

## 9. References

- VeriGuard (per-action SMT for LLM agents): https://arxiv.org/abs/2510.05156
- Z3 SMT solver: https://github.com/Z3Prover/z3
- SMT-LIB Standard 2.6: https://smtlib.cs.uiowa.edu/papers/smt-lib-reference-v2.6-r2021-05-12.pdf
- Dafny (verified programming): https://dafny.org/
- AetherProof: https://releases.aetherlang.online/
- NOUS Phase D Replay: see `replay_runtime.py`, v4.8.2 release notes
- NOUS EU AI Act compliance: [`EU_AI_ACT_COMPLIANCE.md`](./EU_AI_ACT_COMPLIANCE.md)

---

*Last updated: Session 61, 28 April 2026 (HEAD: c9f746b)*
*Implementation begins: Session 62*
