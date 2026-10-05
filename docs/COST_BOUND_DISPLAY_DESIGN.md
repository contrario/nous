# Cost Bound Display -- the declared total behind the cost-cap proof, read from its certificate (S400)

<!-- __s400_cost_bound_display_design_v1__ -->

Status: decisions D400-1 to D400-10, recorded before any code. The
operator approved shape A (display only, CLI headline and VR003
message) in S400. Build notes are appended in section 13 with the code
that implements them.

Marking. [reading] is a statement from reading the source at e8019b2,
the HEAD Server A printed at 2026-10-05 00:13:44Z and 10:47:01Z.
[container] is a value measured in the chat container on a clone of
e8019b2289f04a9d222687676bb97f06e0823e18 on 2026-10-05 with z3 4.16.0
(the smt extra's pin range) and a throwaway signing key. [A] is printed
on Server A, with its time. [testimony] is taken from an earlier
design doc or handoff and is not re-verified here.

---

## 1. Problem statement

`nous verify --smt aml_transaction_governance.nous` prints, on a proven
result [container, and the operator's run on A at 04:44:09Z]:

    PROVEN: total_cost <= $0.5 USD across all execution paths.
      bounded by: 1 soul(s) x 1 ticks

(The CLI prints U+2264 and U+00D7 where this ASCII file shows "<=" and
"x".) The program declares one soul, claude-haiku-4-5 at 1.00 and 5.00
USD per million tokens, tokens input = 500 output = 200, max_ticks 1,
cost_cap 0.50 USD. The declared total is 3/2000 USD = 0.0015 USD, which
is 1/333 of the cap. Nothing on the proven path prints it: not the CLI
block, not the VR003 message, not the manifest. A reader of the
headline cannot tell whether the declared envelope sits near the cap or
far below it. The refuted path already prints the per-soul figures
(smt_verify.format_verdict, REFUTED branch); the proven path does not.

## 2. What the code does [reading]

- The obligation. smt_emit.emit_smt prices each soul from its declared
  tokens and the governed table: per_call = (input_per_1m x
  tokens.input + output_per_1m x tokens.output [x
  reasoning_token_multiplier]) / 1000000; cost_<soul>_total = per_call x
  max_ticks; total_cost = sum of the soul totals; the negated obligation
  is `(assert (not (<= total_cost <cap>)))`, cap = cost_cap, or the
  effective cap under --smt-margin. The subject of the proof is the
  declared total; the cap is the constant.
- The certificate. cost_farkas.cost_certificate_from_smtspec builds,
  from spec.soul_assumptions, the upper-bound relaxation in rows L <= 0
  (L < 0 where strict): per soul, cost_<soul>_per_call - K_s <= 0 with
  multiplier max_ticks, and cost_<soul>_total - max_ticks x per_call
  <= 0 with multiplier 1; total_cost - sum of totals <= 0 with
  multiplier 1;
  cap - total_cost < 0 with multiplier 1. The weighted sum cancels every
  variable and leaves the constant cap - max_ticks x sum(K_s), the
  residual; the certificate's "contradiction" field is "<residual> < 0".
  cli_verify writes it beside --manifest-out as cost.farkas.json and
  binds its sha256 into the signed manifest (cost_farkas_sha256).
- The headline. smt_verify.format_verdict prints spec.cost_cap_amount
  (or the effective cap) in the PROVEN line, and len(spec.soul_costs) x
  spec.max_ticks in the "bounded by" line. It has one caller,
  cli_verify.py:162, which prints it before the certificate is
  extracted.
- VR003. verifier._verify_smt_cost_bound calls emit_smt and
  smt_verify.verify and, when proven, emits "Total declared cost
  provably <= world cost_cap <cap> <ccy> (Z3/Farkas over declared
  pricing). ..." It does not build the certificate. /v1/verify serves
  this message unchanged in "proven" (D378-4); "detail" is not served.
- The manifest. manifest_from_verify carries cost_cap_usd, max_ticks,
  verdict, smt_spec_sha256 and cost_farkas_sha256. On a proven result
  no field holds the declared total; counterexample_total_usd exists
  only on a refuted one and is dropped when None.
- VR001 and VR002 price a third figure: 300 input tokens plus 500 per
  sense call and 200 output tokens (verifier.py:55-57), not the declared
  tokens, against the law cost ceiling, not the world cost_cap. On the
  AML program they print 0.001300. This is D5 of
  ONE_PRICE_SOURCE_DESIGN.md, deferred to its phase P5 (its P2.5), and
  is out of scope here (D400-10).

## 3. Measurements

- [container] Reproduction of the operator's run: the same
  cost.farkas.json (sha256
  3ca7142eb580aff007355692aadf30ecc4e512c11319415684eeb66a4136d275) and
  a manifest equal in every field but elapsed_ms, timestamp and
  signature (smt_spec_sha256 855fd026db635afe..., source_sha256
  4bed54fa64c6586f..., pricing_sha256 d5d51912510a0467...).
- [A 2026-10-05 10:56:00Z, S400-AR-1] /tmp/cost.farkas.json has that
  sha256 and equals the manifest's cost_farkas_sha256; the stdlib grader
  accepts it; the four rows have multipliers 1, 1, 1, 1; the weighted
  sum cancels every variable; residual 997/2000; cost_cap minus residual
  3/2000 = 0.0015.
- [container] The contradiction is "0 < 0" only when the cap equals the
  declared total: a certificate built at cap 3/2000 reads "0 < 0" and
  grades true; at cap 3/2000 - 10^-9 extract_cost_certificate returns
  None.
- [container] Blast radius over the 12 shipped templates and the AML
  program under `nous verify --smt`: 5 reach PROVEN, each with a
  certificate (cost_cap_emit_demo 2 souls, 3 ticks, declared 63/20000
  of cap 1/5; cost_cap_with_souls 2 souls, 5 ticks, 171/4000 of 1/2;
  quorum_gated_demo 2 souls, 3 ticks, 2151/1000000 of 1/5;
  sequence_law_demo 3 souls, 5 ticks, 167/20000 of 1/2; AML 1 soul, 1
  tick, 3/2000 of 1/2). The other 8 stop at emit with rc 3 and print
  no proven block: 7 declare no cost_cap, cost_cap_basic declares no
  max_ticks.
- [container] No test file pins the PROVEN line, the VR003 message or
  the VR001 message text (0 files each). The PROVEN line's wording
  appears on 10 lines in 8 files outside tests: CHANGELOG.md,
  docs/ANNEX_IV_MAPPING.md (2), docs/COST_VERIFICATION_GUIDE.md,
  docs/COVERAGE_PROOF.md, docs/SMT_VERIFICATION_DESIGN.md,
  website/blog/index.html (2), website/coverage.html and
  dossier.py:210.

## 4. Claim class and honest boundary

What is proven does not change: Z3 shows the negated obligation
unsatisfiable, and the Farkas certificate shows, by rational arithmetic
alone, that the declared total cannot exceed the cap. The new line
adds no claim. It states two numbers read off that certificate: the
residual, which is the headroom, and cost_cap minus the residual, which
is the declared total. Both are rational arithmetic over the
certificate a third party already holds; neither is a second proof.

The declared total is not a bound on what a run costs, and the line
must not read as one:

- Dispatch does not send the declared output tokens. max_tokens is
  hardcoded to 300 in nous_runtime.call (lines 239, 246) and
  nous_runtime.stream_call (320, 328), in
  immune_engine._default_llm_caller (179) and noesis_oracle.call (133,
  142), and to 200 in dream_engine._call_dream_llm (385, 398).
  nous_runtime.py reads token counts only from provider responses
  (usage); no line of it reads a soul's declared tokens [reading]. A
  soul that declares output = 200 can be billed up to 300 output
  tokens a call, reasoning tokens included (ONE_PRICE_SOURCE_DESIGN.md section
  4, S353; the reasoning measurement is not pinned) [testimony].
- `nous run --mode live` dispatches the runtime cascade, not the
  declared mind (ONE_PRICE_SOURCE_DESIGN.md section 14.9, S362)
  [testimony].
- The runtime does not meter spend (ONE_PRICE_SOURCE_DESIGN.md section
  3) [testimony]. The cost model counts one generation per tick; a
  multi-step agent is bounded through max_ticks.
- Input tokens are whatever the declaration says; nothing measures the
  prompt that is actually sent against tokens.input.

So the declared total describes the envelope the author wrote, priced
at the governed table. The cap is the author's chosen ceiling for that
envelope. A tighter printed number is easier to mistake for a spend
figure than the cap is, which is why the wording in D400-5 is fixed
and tested.

## 5. Reasons this should never exist (written first)

R1. The cap is the obligation. A second, much smaller number beside a
    PROVEN line invites reading it as a proven spend bound (section 4).
R2. The value is already recoverable offline from cost.farkas.json
    (cost_cap minus the residual); printing it adds no evidence.
R3. Any copy change near a PROVEN surface risks the reserved verb
    drifting onto the declared figure (D376-1).
R4. It touches two shipped modules and the /v1/verify message content
    for a display: a release and a nous-api restart.

## 6. Case for building (after section 5)

- Answers R2: recoverable is not visible. An auditor reading the
  headline, the IDE or /v1/verify sees only the cap and cannot judge
  the margin without decoding the certificate by hand.
- Answers R1 and R3: the wording is fixed (D400-5) and a test fails on
  "prove", "proven", "spend", "<=" or U+2264 in the new text.
- The refuted path already shows the declared figures; the proven path
  becomes symmetric.
- Composes from shipped parts only (Article VII): the existing
  certificate, the existing zero-trust re-derivation
  (cost_farkas.check_serialized_cost) and the existing stdlib grader.
  No new module, trust root, dependency, artifact or manifest field.

## 7. Innovation Gate applicability

Not a new arc, frontier or claim class: an extension of the shipped
cost-cap leg's display. Article VI's dossier is therefore not run;
sections 4 to 6 and 10 to 11 carry the parts of it that bear on a
display change. The operator can rule otherwise.

## 8. Decisions

D400-1. Scope. Two surfaces: the PROVEN block of `nous verify --smt`
    (smt_verify.format_verdict) and the VR003 PROVEN message
    (verifier._verify_smt_cost_bound), which /v1/verify serves. The
    change is additive: the existing PROVEN line, the "bounded by" line
    and the existing VR003 text stay byte-identical, so the sample
    outputs quoted in section 3 stay true. Refuted and error output do
    not change.

D400-2. One source: the certificate. Every number printed comes from
    the cost-cap certificate that cost_certificate_from_smtspec returns
    for the same spec:
    - headroom = the residual, the constant left by the
      multiplier-weighted sum of the certificate's rows;
    - declared total = the certificate's cost_cap minus the residual;
    - per soul, per tick = minus the constant of that soul's
      cost_<soul>_per_call row; ticks = the certificate's max_ticks;
    - the cap shown = the certificate's cost_cap (the effective cap
      when --smt-margin is set).
    Nothing printed is recomputed from tokens x price.

D400-3. Binding gate, refuse over guess. Before anything is printed:
    coverage_farkas.check_serialized(doc) is true; the weighted sum
    cancels every variable; and cost_farkas.check_serialized_cost(doc,
    souls_from_smtspec(spec), spec.max_ticks, spec.cost_cap_amount,
    spec.cost_cap_margin_pct) is true, which re-derives the system from
    the spec's declared tokens and table rates and rejects any
    substitution, omission or surplus. The token x rate terms shown in
    the per-soul line (D400-5) come from spec.soul_assumptions and are
    displayed only after this gate has tied them to the certificate. If
    any check fails, or no certificate exists (CostFarkasError, None),
    no declared line is printed and a note names the cause. There is no
    fallback figure.

D400-4. Verdict untouched (K3). A display refusal never changes the
    verdict, the exit code, the manifest, the certificate file or the
    VR003 severity and tier. The CLI prints the note to stderr and
    continues; VR003 keeps its current message and adds the note's
    cause to it.

D400-5. Wording, ASCII only. For the AML program the CLI adds, after
    the "bounded by" line:

      declared total_cost = 0.0015 USD (3/2000) = cost_cap 1/2 - certificate residual 997/2000
      headroom = 0.4985 USD (997/2000), the certificate residual
        Screener: 500 in x 1.00/M + 200 out x 5.00/M = 3/2000 per tick x 1 ticks

    With --smt-margin p, "cost_cap 1/2" reads "effective cap <e>
    (cost_cap <c>, margin p%)". A reasoning multiplier other than 1
    appears as "200 out x 5.00/M x <m>". Souls are listed in the
    certificate's order (by name). The VR003 message keeps its text and
    appends: " Declared total_cost 0.0015 USD (3/2000) = cost_cap 1/2
    minus the Farkas certificate residual 997/2000 (the headroom);
    basis: declared tokens x table price x max_ticks." The new text says
    "declared"; it never contains "spend", "prove", "proven",
    "provably", "<=" or U+2264, and never a dollar sign: the amount is
    followed by the currency code, which is also correct for EUR.

D400-6. Exact rendering. The rational is always printed. The decimal
    beside it is the exact expansion when the denominator has no prime
    factor other than 2 and 5 (always the case for decimal prices and
    integer tokens); otherwise only the rational is printed. No float
    enters any printed figure.

D400-7. Placement. One helper in smt_verify.py,
    declared_cost_display(spec, cost_doc) -> DeclaredCostDisplay (a
    frozen dataclass), raising CostDisplayError(ValueError) whose
    message starts with the cause. format_verdict gains a keyword-only
    cost_certificate: Optional[dict] = None; without it the output is
    byte-identical to today. cli_verify computes the certificate
    before printing the verdict; its "Cost-cap Farkas certificate
    extracted" line keeps its place. verifier._verify_smt_cost_bound
    calls cost_certificate_from_smtspec on the proven path. No change
    to smt_emit.py (the spec and the regression harness stay
    byte-identical), cost_farkas.py or coverage_farkas.py (the graders
    stay as shipped), the manifest, or any .well-known artifact. No new
    module.

D400-8. Tests, red first (K4), in tests/test_s400_cost_bound_display.py:
    - the CLI on the AML program prints the three D400-5 lines exactly;
    - the printed declared total and headroom equal cost_cap minus the
      residual and the residual of the cost.farkas.json the same run
      wrote, recomputed in the test from that file's bytes;
    - the VR003 message keeps its current text as a byte-identical
      prefix and carries the same two figures;
    - wording: the new text contains "declared", is ASCII, and contains
      none of the D400-5 forbidden strings;
    - a tampered certificate (one per-call constant changed) and a
      missing certificate each give the note naming the cause, no
      declared figure in the output, and the verdict, exit code and
      manifest of the untampered run;
    - --smt-margin 10 on the AML program: effective cap 9/20, headroom
      897/2000, still read from the certificate;
    - one multi-soul template (sequence_law_demo, 3 souls, 5 ticks):
      per-soul lines in certificate order; their sum times ticks equals
      the declared total;
    - format_verdict without cost_certificate is byte-identical to
      today's output for the same result.
    Each test is read red on e8019b2, with its reason taken from
    --junitxml, before the code exists. The existing
    test_c_proven_plus_evidenced_equals_verifier_passing_items stays
    green because the served message still equals the verifier's.

D400-9. Ship. The code ships in a release with a CHANGELOG entry and a
    new section in docs/COST_VERIFICATION_GUIDE.md that shows the
    lines, explains section 4 in short, and gives the offline
    recomputation from cost.farkas.json. PYTEST_FLOOR rises with the
    new tests. The served /v1/verify message changes only after the
    release's nous-api restart on A and B (each its own pame). The IDE
    renders the message as it is and needs no change. Copy is read by a
    person as well as by claim_lint, which misses spend claims.

D400-10. Out of scope, recorded:
    - B, a second certificate at cap = declared total, to print a proven
      tight bound: rejected (docs/REJECTED_IDEAS.md R5).
    - C, a signed declared_total field in the manifest: deferred. The
      value is already bound through smt_spec_sha256 and
      cost_farkas_sha256; a new field needs a trace of every manifest
      consumer first.
    - D, VR001 and VR002 reading the declared tokens: D5 of
      ONE_PRICE_SOURCE_DESIGN.md, phase P5, its own unit.
    - The PROVEN line in the static dossier (dossier.py:210): a later
      decision, not part of this release.

## 9. Kill criteria

K1. If any printed figure differs from what the certificate gives,
    stop: the display is wrong by construction.
K2. If a reader review or a copy test finds the new text read as a
    bound on spend, remove the line rather than reword it twice.
K3. If any proven case among the five in section 3 has no certificate,
    revisit D400-3 before building.

## 10. Opportunity cost

This displaces nothing banked in the release lane. Ranked against it,
D5/P5 (one token model for VR001, VR002 and the bound) removes a real
inconsistency where this unit only reports; it is larger, changes
ESTIMATED figures and needs its own decisions.

## 11. Generalization path

Narrow first: the cost-cap leg only. The coverage and sequence legs
have their own certificates; whether their reports would gain from a
residual line is a separate question, not asked here.

## 12. Open

- Whether an outside consumer parses the VR003 message text from
  /v1/verify. Unknown; its key set and order do not change.
- The prior content of /tmp/cost.farkas.json on A: the file was created
  on 2026-09-03 10:37:06Z and rewritten in place at 04:44:09Z on
  2026-10-05 [A 10:56:00Z]; what wrote it first is not known.

## 13. Build notes

(empty until the code exists)

## 14. Amendment D401-1 and D401-2 (S401)

<!-- __s401_cost_bound_display_d401_v1__ -->

Recorded in S401 before any code. D401-1 amends D400-2, D400-3 and
D400-8; D401-2 makes D400-7 and D400-8 precise where the CLI is
concerned. Sections 1 to 13 are unchanged. [container] in this section
is a clone of ea899212ae3b8b462e8c4702aa5ae2d733780283 (the S400 docs
commit, code-identical to e8019b2) on 2026-10-05 with z3 4.16.0; the
D400-8 tests are read red on that commit. [testimony] marks a result
another lane reported and this lane did not re-run.

Finding [reading, container]. The three checks of D400-3 bind only the
certificate's rows. check_serialized reads "constraints" and
"multipliers" alone and accepts any positive multiple of a valid
witness; check_serialized_cost compares "constraints" alone against the
re-derived system and then calls check_serialized. Neither reads
"cost_cap", "max_ticks", "fragment" or "contradiction". Each of these
edits to the AML certificate passes all three checks [container; the
five reproduced by another lane on ea89921, testimony]:

- every multiplier times 2: the weighted constant reads 997/1000 and
  cost_cap minus it reads -497/1000, where the headroom is 997/2000 and
  the declared total 3/2000;
- "cost_cap" set to "1": cost_cap minus the residual reads 1003/2000;
- "max_ticks" set to 5: the ticks read 5, where the spec has 1;
- "contradiction" set to "0 < 0": not printed, still accepted;
- "fragment" changed: not printed, still accepted.

Under D400-2 as written, the first three would print a wrong figure
(K1 by construction). A changed per-call constant, the D400-8 case, is
rejected by check_serialized_cost [container].

D401-1. A fourth check, after the three of D400-3 and before anything
is printed: the certificate's canonical bytes equal the canonical bytes
of the certificate re-derived from the same spec,

    cost_farkas_json_bytes(doc) == cost_farkas_json_bytes(
        extract_cost_certificate(souls_from_smtspec(spec),
                                 spec.max_ticks,
                                 spec.cost_cap_amount,
                                 spec.cost_cap_margin_pct))

A re-derivation that returns None or raises CostFarkasError is a
refusal. Equality pins the multipliers (the cap row's multiplier is 1,
so the weighted constant is the headroom), "cost_cap", "max_ticks",
"fragment" and "contradiction". Every printed number is still read from
the certificate as D400-2 states; the re-derivation only binds the
certificate and is never printed. Both functions ship in
cost_farkas.py, which does not change.

- Positive control [container]: the certificates of the five programs
  of section 3 that reach PROVEN, each at --smt-margin 0 and 10, pass
  all four checks (10 of 10). At margin 10 the AML certificate reads
  cap 9/20, headroom 897/2000, declared total 3/2000.
- check_serialized_cost stays a check (operator preference, S401). A
  certificate byte-equal to the re-derived one always passes it,
  because extract_cost_certificate returns only a certificate that
  check_serialized grades true [reading]; it rejects nothing the fourth
  check admits. It ships, costs nothing, and names a narrower cause
  when a row differs.
- Order and cause. The checks run in a fixed order: check_serialized,
  variable cancellation, check_serialized_cost, byte equality. The note
  names the first check that fails. The note is new text and follows
  the wording rule of D400-5.
- No negative figure. A declared total below zero cannot pass the
  fourth check: the re-derived certificate has per-call constants of
  zero or more (cost_farkas._validated_souls refuses a negative one)
  and max_ticks of 1 or more [reading]. No separate sign check is
  added, because no input can reach it and an undriven branch is not
  a gate (FG-S374-D).

D401-2. Where the checks sit and how the tests reach them.

- smt_verify.format_verdict(result, cost_certificate=doc), on a proven
  result, runs the four checks through declared_cost_display and raises
  CostDisplayError when one fails. Without the keyword its output is
  byte-identical to today (D400-7); on a result that is not proven the
  keyword is ignored (D400-1).
- cli_verify extracts the certificate before it prints the verdict only
  when the verdict is proven, and reuses that certificate at the
  existing extraction step, whose stdout and stderr lines keep their
  place. On any other verdict the extraction runs where it runs today,
  so that output stays byte-identical. When format_verdict raises
  CostDisplayError, the CLI prints the note to stderr and prints the
  block without the declared lines. When the verdict is proven and no
  certificate exists, the CLI prints a note naming that cause to
  stderr.
- A tampered certificate is injected into the display only: the test
  wraps the format_verdict that cli_verify calls and hands it an edited
  copy. That run writes the untampered cost.farkas.json and manifest,
  so its verdict, exit code and manifest equal the untampered run's
  (D400-4), the fields that differ on every run aside (timestamp,
  elapsed_ms, signature; one throwaway key for both runs).
- A missing certificate is injected where it is produced
  (cost_certificate_from_smtspec returns None or raises
  CostFarkasError). That run, as today, writes no cost.farkas.json and
  its manifest carries no cost_farkas_sha256. Its verdict and exit code
  equal the untampered run's, and its manifest equals the untampered
  run's without cost_farkas_sha256 and the per-run fields. The display
  adds nothing to the manifest in either case.

D400-8 additions (tests/test_s400_cost_bound_display.py, red first):

- each of the five edits above gives the note naming the byte-equality
  check, no declared line, and the verdict, exit code and manifest of
  the untampered run (D401-2);
- the multipliers-times-2 case also asserts that no negative declared
  total is printed: neither "-497/1000" nor "-0.497" appears anywhere
  in the output; the line is refused;
- the per-call constant case of D400-8 names check_serialized_cost;
- VR003 gets the same five edits and the missing case: its severity,
  tier and existing text are unchanged, and the cause is appended.
