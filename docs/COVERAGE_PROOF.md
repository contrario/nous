# Policy Coverage Proof and the Farkas Certificate

Reference for the policy-coverage obligation (introduced S115, P3a) and its
Farkas certificate (S115 core, wired S116, P3b), both shipped in
`nous-lang 5.27.0`. ASCII-only.

Cross-references: `docs/SMT_VERIFICATION_DESIGN.md` (cost-proof soundness,
Z3 pin), `docs/VERIFY_DOSSIER.md` (dossier layout and verification paths),
`docs/ANNEX_IV_MAPPING.md` (evidence-to-Annex-IV crosswalk).

================================================================
1. What the coverage proof is (and is not)
================================================================

A NOUS world declares blocking policies -- policies whose action is `block`
or `abort_cycle`. The coverage obligation asks a precise question about that
set of policies relative to a declared risk threshold:

    For every input where <threshold> holds, does at least one blocking
    policy also fire?

If yes, the blocking-policy net has NO GAP over the threshold region. If no,
there is a concrete input that crosses the threshold yet escapes every
blocking policy -- a coverage gap.

HONEST BOUNDARY (load-bearing; do not overstate):

  - The coverage proof proves there is no gap in the declared blocking net
    over the declared threshold region. It does NOT prove that the agent
    cannot perform an undesired action. Policies are MONITORS, not hard
    guards on the model (see `intervention.py`).
  - What is proven is that the GOVERNANCE DECLARATION is sound (no gap) and
    that the cost envelope holds; the signed evidence attests that those
    declared policies were the ones in force. This is COVERAGE, not
    impossibility.

The coverage proof sits beside the cost proof (see
`docs/COST_VERIFICATION_GUIDE.md`). The cost proof is universal over all
execution paths in the proven bound; the coverage proof is universal over
all inputs in the declared threshold region.

================================================================
2. The SMT obligation
================================================================

For a threshold expression T and blocking signals s_1 ... s_k, coverage is
the UNSATISFIABILITY of:

    T  AND  NOT(s_1 OR ... OR s_k)
  = T  AND  (NOT s_1) AND ... AND (NOT s_k)

over the reals. Read: "an input that satisfies the threshold but no blocking
signal." If unsat, no such input exists -- coverage holds. If sat, the model
is a concrete counterexample -- a gap.

This is emitted as `coverage.smt2`, a human-inspectable SMT-LIB script:

    ; coverage obligation: blocking-policy net over threshold
    (declare-const amount Real)
    (assert (> amount 10000))                 ; threshold (protected region)
    (assert (not (or (> amount 50000)         ; blocking net is open
                     (> amount 10000))))
    (check-sat)                               ; unsat proves no gap

The translation (`policy_coverage.py`) refuses, fail-closed, anything it
cannot soundly translate (unsupported node kinds, cross-currency-unit
comparisons, missing blocking policy). Refuse over guess.

================================================================
3. CLI
================================================================

    nous verify --smt <file>.nous \
      --coverage-threshold "EXPR" \
      --manifest-out <dir>/source.manifest.json

  - The cost obligation is proven first (requires `cost_cap`, `max_ticks`,
    and per-soul `tokens`). See `docs/COST_VERIFICATION_GUIDE.md`.
  - The coverage obligation is then proven over EXPR (a NOUS threshold
    expression, e.g. `amount > 10000`).
  - On PROVEN coverage: the manifest binds `policy_coverage_sha256` and
    `coverage_smt2_sha256`; `coverage.smt2` is written next to the manifest;
    and, when the obligation is inside the certifiable fragment (Section 5),
    a Farkas certificate is extracted and written as `coverage.farkas.json`
    with `coverage_farkas_sha256` bound in the manifest.
  - On REFUTED coverage: NO manifest is written. The command exits non-zero.
    NOUS does not sign a system with an unproven coverage obligation. This is
    a deliberate fail-closed: a gap blocks evidence production entirely.

`--coverage-threshold` is a flag on the existing `verify` subcommand; it adds
no new subcommand. Omit it and `verify` behaves exactly as before; cost-only
manifests stay byte-identical.

================================================================
4. Manifest fields (all drop-when-None)
================================================================

Three optional fields, each omitted from the canonical signed bytes when
None, so cost-only and coverage-only manifests remain byte-identical to
their pre-coverage form:

    policy_coverage_sha256   sha256 of the canonical CoverageBlock (the
                             semantic obligation: PCV/CD/CT/CO/CU lines).
    coverage_smt2_sha256     sha256 of the exact coverage.smt2 file bytes.
                             A crypto-only file-provenance binding.
    coverage_farkas_sha256   sha256 of the exact coverage.farkas.json bytes.
                             Present only when a Farkas certificate was
                             extracted (certifiable fragment).

All three are covered by the single Ed25519 signature over the canonical
manifest body. Tampering with any bound file breaks the signature.

================================================================
5. The Farkas certificate
================================================================

5.1 Why a certificate, not a solver re-run

Re-running the same solver to confirm "unsat" does not raise trust: a solver
bug that reports unsat-for-sat is reproduced by re-execution, not caught, and
it forces an auditor to install and trust a solver. The formal-methods
discipline (DRAT mandatory in SAT competitions since 2014; SMTCoq; Kind 2 /
LFSC) is to emit a CERTIFICATE checked by a SIMPLER, INDEPENDENT checker,
minimizing the trusted base. Auditor-side verification should be asymmetric:
orders of magnitude cheaper and lighter than the original proof search.

5.2 Why it is tractable here

The coverage obligation is a trivial SMT fragment: a single Real sort, linear
inequalities only, asking unsat of a conjunction. For unsatisfiability of a
conjunction of linear inequalities over the reals, Farkas' lemma gives a
vector of non-negative rational multipliers whose combination collapses to a
numeric contradiction (e.g. `0 < 0`). That multiplier list is the
certificate; checking it is multiply-and-add over fractions -- no solver, no
NOUS install, standard library only.

(There is no uniform serialization standard for LP/Farkas infeasibility
certificates -- VIPR targets mixed-integer programming, not linear-real --
so NOUS uses a self-contained structured JSON checked by a minimal
independent checker.)

5.3 Format (`coverage.farkas.json`)

A self-contained, JSON-serializable certificate. Each inequality is carried
as exact-rational coefficients in normalized "L (< or <=) 0" form:

    {
      "fragment": "linear-real-single-comparison",
      "threshold_expr": "amount > 10000",
      "constraints": [
        {"coeffs": {"amount": "-1", "": "10000"}, "strict": true},
        {"coeffs": {"amount": "1",  "": "-50000"}, "strict": false},
        {"coeffs": {"amount": "1",  "": "-10000"}, "strict": false}
      ],
      "multipliers": ["1", "0", "1"],
      "contradiction": "0 < 0"
    }

Coefficients and multipliers are exact rationals as strings (parsed with
`fractions.Fraction`); never floats. The empty-string key is the constant
term.

5.4 Checking (`coverage_farkas.check_serialized`, stdlib only)

    1. multipliers are equal in count to constraints, all non-negative, at
       least one positive;
    2. the multiplier-weighted sum of the inequalities cancels every
       variable coefficient;
    3. the residual constant yields a numeric contradiction:
         constant > 0                 (a non-strict "c <= 0" with c > 0), or
         constant == 0 AND some used inequality is strict   (a "0 < 0").

No AST, no solver, no NOUS install. `fractions` and `json` only.

5.5 The certifiable fragment (fail-closed)

The extractor (`coverage_farkas.extract_certificate` /
`coverage_farkas.serialize_system`) accepts a single linear comparison
(`>`, `>=`, `<`, `<=`) or a flat OR of such comparisons, over the reals.
It refuses, with a typed `FarkasError`, anything outside that fragment:
`==` / `!=`, boolean AND, nested NOT, non-linear terms (`*` `/` `%`).
A general boolean fragment (signals combined with AND/OR) needs DNF case-
splitting and multiple witnesses; it is deferred (P3b-bool) and refused today
so no unsound certificate is ever emitted.

When the extractor refuses, `nous verify` FAILS OPEN with respect to Farkas:
the coverage proof (z3) still stands, `coverage.smt2` is still written, and
`coverage_farkas_sha256` simply stays None. The Farkas certificate is an
additive strengthening of HOW coverage is verified, never a precondition for
coverage itself.

================================================================
6. Dossier integration and offline verification
================================================================

A coverage-bearing dossier (`nous dossier ... --anchor none`) carries 8
files: `source.nous`, `manifest.json`, `pricing.toml`, `public_key.b64`,
`README.md`, `verify_offline.py`, `coverage.smt2`, and (when present)
`coverage.farkas.json`.

Verifier selection (offline, `--anchor none`):

  - Farkas certificate present -> the dossier ships the Farkas verifier. Its
    coverage trust path is rational arithmetic alone; z3, if installed, runs
    only as an optional SECOND OPINION and the verdict does not depend on it.
  - coverage.smt2 present, no Farkas -> the z3 re-check verifier (graceful
    skip if z3 absent; the crypto file-sha gate still holds).
  - cost-only -> the original verifier; byte-identical to pre-coverage.

The Farkas verifier checks, in order, fail-closed:

    1. Ed25519 signature over the canonical manifest body.
    2. source.nous sha256 == manifest.source_sha256.
    3. coverage.smt2 sha256 == manifest.coverage_smt2_sha256
       (human-inspectable obligation; O(1) crypto provenance gate).
    4. coverage.farkas.json sha256 == manifest.coverage_farkas_sha256
       (O(1) crypto gate BEFORE any arithmetic).
    5. Farkas certificate check (Section 5.4): the multipliers collapse the
       declared linear system to a numeric contradiction -- PROVEN by
       arithmetic, zero solver trust.
    6. z3 unsat re-check on coverage.smt2 -- OPTIONAL second opinion, skipped
       gracefully when z3 is absent.

The only hard dependency of the offline verifier is `cryptography` (for the
Ed25519 signature). The coverage claim itself needs no solver and no NOUS
install. Running with z3 deliberately removed yields the same PASS.

================================================================
7. Worked example (AML transaction screening)
================================================================

`aml_transaction_governance.nous` declares a Screener soul, `cost_cap 0.50
USD`, `max_ticks 1`, and three policies: `BlockVeryLargeTransfer`
(`amount > 50000`, block), `AbortHighRiskBand` (`amount > 10000`,
abort_cycle), `LogAllScreens` (`true`, log_only).

PROVEN over the rules' own threshold:

    nous verify --smt aml_transaction_governance.nous \
      --coverage-threshold "amount > 10000" --manifest-out out/m.json
    # PROVEN: total_cost <= $0.50 across all execution paths
    # Coverage PROVEN: no gap over threshold 'amount > 10000'
    # Farkas certificate extracted: contradiction '0 < 0'

  The certificate's multipliers are `[1, 0, 1]`: the threshold inequality
  plus the `AbortHighRiskBand` negation collapse to `0 < 0`; the
  `BlockVeryLargeTransfer` term is unused (multiplier 0).

REFUTED over a stricter declared threshold (fail-closed):

    nous verify --smt aml_transaction_governance.nous \
      --coverage-threshold "amount > 5000" --manifest-out out/gap.json
    # REFUSED: coverage not proven (verdict=refuted); no manifest written.

  A transaction of 5,001 satisfies "over 5,000" but escapes both blocking
  rules (which only fire above 10,000 and 50,000). The band 5,000-10,000 is
  an uncovered gap; NOUS refuses to produce evidence for it.

Offline replay of the proven dossier (z3 absent):

    cd out/dossier && PYTHONPATH=<dir-with-stub-z3> python3 verify_offline.py
    # OK Ed25519 signature verified
    # OK source.sha256 / coverage.smt2 sha256 / coverage.farkas.json sha256
    # OK Farkas certificate verified by rational arithmetic, no solver (0 < 0)
    # NOTE z3 not installed; the Farkas arithmetic proof above is sufficient
    # VERDICT: PASS

================================================================
8. Trust model summary
================================================================

  - Producer (writes proofs + dossier): needs `nous-lang[smt]` (pulls the
    solver, used once at build time).
  - Verifier (auditor): needs `cryptography` only. No nous-lang, no solver,
    no network. The coverage claim is checked by standard-library rational
    arithmetic; z3 is an optional second opinion.
  - Binding: the Ed25519-signed manifest pins the source, the pricing table,
    the coverage obligation, and the Farkas certificate by sha256. The
    certificate's linear system is bound to the real obligation at the same
    trust level as P3a (signed source + human-inspectable coverage.smt2).
    Farkas removes solver trust; it does not change the source-binding story.

================================================================
9. Version history
================================================================

  P3a (S115, shipped in v5.27.0): coverage obligation, `coverage.smt2` in the
       dossier, `policy_coverage_sha256` + `coverage_smt2_sha256` manifest
       fields, `--coverage-threshold` flag, REFUTED fail-closed, z3-re-check
       offline verifier.
  P3b (S115 core, wired S116, shipped in v5.27.0): `coverage_farkas.py`
       (`serialize_system`, `check_serialized`), `coverage_farkas_sha256`
       manifest field, `coverage.farkas.json` as the 8th dossier file, and
       the stdlib-only offline verifier with z3 demoted to optional second
       opinion.


## P3b-bool: the Farkas DNF bundle (v5.32.0)  <!-- __s124_coverage_proof_doc_v1__ -->

Since v5.32.0 the stdlib-checkable certificate covers full Disjunctive
Linear Arithmetic: boolean combinations of linear comparisons via
`&&`, `||`, `!` in blocking signals and in the coverage threshold.

Mechanism. The gap search `T && NOT(B_1) && ... && NOT(B_n)` is expanded
to disjunctive normal form over the NEGATION. Each disjunct is a
conjunction of linear comparisons, i.e. one linear system, and Farkas'
lemma is complete for it: the disjunct is unsatisfiable iff non-negative
multipliers collapse it to a numeric contradiction. Coverage is PROVEN
iff EVERY disjunct of the negation carries such a witness.
`coverage.farkas.json` becomes a bundle: `fragment` is
`"disjunctive-linear-bundle"` and `certs` is an array of per-disjunct
certificates, each carrying canonical constraints and multipliers.
Purely linear obligations keep emitting the v1 single-system format
byte-identically.

Zero-trust verification. The offline verifier does NOT iterate the
handed bundle. It re-derives the disjunct set independently from the
SIGNED source: `source.nous` is sha-gated by the signed manifest, the
threshold expression is sha-gated through `coverage.farkas.json`, and a
pure-stdlib scanner plus an expression parser that mirrors the grammar
precedence reconstruct the obligation. The verifier then requires a
BIJECTION -- exactly one valid certificate per derived disjunct, keyed
by the full canonical serialization of the disjunct's constraints. A
bundle that omits the gap disjunct (overclaim-by-omission), carries a
surplus or duplicate certificate, substitutes a constraint, or forges a
multiplier FAILS even when the enclosing manifest signature is valid.
This is boolean ENUMERATION from signed source, never boolean solving;
the verifier stays solver-free.

Issuance gate. The producer signs a bundle only when an independent
text-level derivation (`coverage_minilang`) reproduces the Lark-side
disjunct set; divergence drops the certificate to z3-only evidence
(drop-when-None), never a mismatched signature.

Bounds and honest boundary. DNF expansion is exponential in the worst
case; the producer refuses (typed) above `DISJUNCT_BOUND = 64` rather
than sign an unbounded case-split. `var * var` stays REFUSED: bilinear
constraints are outside QF_LRA and no cheap stdlib certificate exists.
Chain (envelope-binding) + bundle composition is REFUSED at dossier
build until the chain verifier learns bundle certificates.
