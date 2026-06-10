# Chain Hop Containment via Farkas Bundles (S126 design freeze)

Status: FROZEN (S126). Supersedes the closed-form monotonicity hop of
S121 for bundle-bearing chains. Plain v1 chains are unaffected.

## 1. Motivation

The v5.33.0 chain verifier proves coverage-region monotonicity across a
re-binding hop with a closed-form proportionality check over a SINGLE
linear inequality per link. Consequences:

- A prior link whose coverage bundle has a boolean threshold (no single
  comparison) carries no threshold_constraint. The hop is unprovable,
  so such priors are REFUSED at issuance and fail closed in the
  verifier (S125 gates).
- Two thresholds over different variable sets are refused as
  syntactically INCOMPARABLE even when containment semantically holds
  or fails in the joint space.
- The verifier embeds a complete Farkas proof engine (minilang, NNF,
  DNF, canonical forms, multiplier check) but uses it for exactly one
  obligation (coverage), while monotonicity uses separate, weaker,
  bespoke code.

## 2. The claim and its obligation

Region containment over the reals reduces to unsatisfiability:

    T_prev subset-of T_cur   <=>   T_prev AND NOT(T_cur)  is unsat

This is the SAME shape as the coverage obligation
(T AND NOT(B_1) AND ... AND NOT(B_n) unsat). Within the disjunctive
linear fragment (boolean combinations of linear comparisons, QF_LRA),
Farkas' lemma is complete: every unsatisfiable DNF disjunct has a
rational multiplier witness, and every satisfiable disjunct has none.
A hop proof is therefore a theorem object, not a heuristic:

- expand NNF(T_prev) AND NNF(NOT T_cur) to DNF (DISJUNCT_BOUND 64);
- refute every disjunct with non-negative rational multipliers;
- a satisfiable disjunct (real region regression, or genuine
  non-containment across variable spaces) admits no witness and the
  build REFUSES at issuance.

The syntactic INCOMPARABLE refusal becomes a semantic check in the
joint variable space.

## 3. Artifact

Per hop k -> k+1 (the last hop targets the current manifest), the
dossier carries one hop bundle:

    chain/NNN_hop.farkas.json     (NNN = predecessor link index)

Shape (cert entries byte-identical to coverage-bundle certs):

    {
      "fragment": "hop-containment-bundle",
      "prev_threshold_expr": "<string>",
      "cur_threshold_expr": "<string>",
      "disjunct_count": N,
      "certs": [
        {"constraints": [...], "multipliers": [...],
         "contradiction": "..."},
        ...
      ]
    }

## 4. Trust model: unsigned and self-certifying

Hop bundles carry NO signature and bind to NO manifest field. The two
inputs that define the obligation are already authenticated:

- each link's threshold_expr lives in that link's coverage.farkas.json,
  whose sha256 is signed in that link's manifest (coverage_farkas_sha256);
- the chain walk (S120) already authenticates every link manifest.

The verifier takes prev/cur threshold expressions from the two
AUTHENTICATED sidecars -- never from the hop doc -- re-derives the
disjunct set independently, and demands a bijection: exactly one valid
certificate per derived disjunct. The hop doc's own expr fields are
cross-checked for equality and otherwise informational.

Consequences, fail-closed:

- forged multipliers fail rational arithmetic;
- omitted disjunct / surplus or duplicate cert fails the bijection;
- deleted hop file: a (has, has) hop without its bundle FAILS;
- unexpected hop file where either side declares no coverage: REFUSE
  (unexpected evidence, mirrors _authenticated_threshold);
- a tampered hop doc cannot widen the claim because the obligation is
  re-derived from signed inputs.

Issuer trust added: zero. Solver trust added: zero (issuance witness
search is the existing stdlib nullspace; verification is fractions).

## 5. Hop applicability matrix (unchanged semantics, stronger proof)

Per ordered hop (prev, cur), where "has" means the link's signed
manifest declares coverage_farkas_sha256:

    (has,  has ) -> hop bundle REQUIRED; verified by re-derivation
    (has,  none) -> coverage VANISHED; refuse (unchanged from S121)
    (none, has ) -> net grew from nothing; no hop bundle; pass
    (none, none) -> skip

## 6. Issuance

At dossier build time, for every (has, has) hop in the assembled chain
(carried priors + predecessor + current):

1. read both sidecars' threshold_expr (each sha-gated against its
   signed manifest BEFORE use; mismatch refuses);
2. parse both via coverage_minilang (typed refuse outside fragment);
3. serialize_hop_bundle(prev_expr, cur_expr): NNF/DNF of
   prev AND NOT(cur), per-disjunct _find_farkas;
4. no witness for any disjunct => DossierError "region regression /
   non-containment at hop NNN" -- the regression is caught at
   ISSUANCE, matching the CT admission-control pattern;
5. write chain/NNN_hop.farkas.json.

The issuer computes ALL hops at every build (it holds every carried
sidecar), so chains predating this design gain full hop coverage on
the next link issued. No migration, no mixed state.

## 7. Gates lifted, scope held

- The S125 boolean-threshold issuance gates
  (__s125_chain_bundle_gate_v1__, current and carried-prior sites) are
  REMOVED: boolean-T links become admissible because the hop no longer
  needs a single-comparison threshold.
- Scope: VERIFY_OFFLINE_PY_CHAIN_BUNDLE only. The template's
  closed-form monotonicity walk (_region_contains et al.) is REPLACED
  by hop-bundle verification. Plain v1 chains (no bundle link) keep
  VERIFY_OFFLINE_PY_CHAIN byte-identically -- the v5.33.0 selector is
  unchanged. No silent merge across the discriminator.

## 8. Honest boundaries

- Proves the DECLARED threshold region never shrank across re-bindings.
  Not execution conformance, not real-world safety, not blocking-net
  containment (B_prev subset-of B_cur is a future obligation through
  the same primitive).
- DISJUNCT_BOUND 64 applies per hop; exceeding it refuses, never
  approximates.
- Fragment limits inherited: linear comparisons under && / || / !,
  constant*variable only; bilinear terms refuse.
- Prior links' COVERAGE validity is still attested by signature only
  (their bundles cannot be re-derived without their source). Full
  per-prior re-derivation remains the deferred Option 1 source-carry
  enrichment (opt-in, privacy-priced).

## 9. The general pattern

This is the second obligation discharged by the re-derivable Farkas
bundle (the first: coverage, S124). Any future chain obligation
expressible as "linear-boolean formula unsat" -- certificate remedy
conditions, envelope intersection, blocking-net containment -- flows
through the same primitive: issuer searches the witness, verifier
re-derives the obligation from signed inputs and checks with stdlib
fractions. One proof engine, many obligations.

## 10. Test plan (U6)

- e2e PASS: 3-link chain, boolean-T link admitted, hop bundles
  emitted, verifier re-derives + bijection + VERDICT PASS;
- regression refuse at issuance: cur threshold strictly smaller than
  prev (satisfiable hop disjunct, no witness);
- tamper: delete a hop file -> verifier FAIL; forge a multiplier ->
  FAIL; surplus cert -> FAIL; swap threshold_expr in hop doc -> FAIL
  (cross-check against authenticated sidecars);
- realign: S124 test_bool_chain_plus_bundle_refused_e2e and S125
  test_chain_over_boolean_threshold_prior_refused flip from refusal
  to PASS expectations;
- unit: serialize_hop_bundle / check_serialized_hop_bundle round-trip,
  variable-space mismatch (semantic non-containment) refuses at
  issuance.

## 11. North-star check

After this lands, a third party verifies offline -- cryptography plus
stdlib fractions -- that a lineage of boolean-net builds has monotone
declared threshold regions. Before, that exact case was a refusal.
The trust surface is unchanged: every byte the proof depends on is
either signed or re-derived. Strictly additive.
