# NOUS Rejected Ideas Ledger

<!-- __s198_rejected_ideas_ledger_v1__ -->

The Innovation Gate's negative output, made durable. When the Gate says DO NOT
BUILD, the reasoning is recorded here so it is not rediscovered from scratch and so
a future session does not re-propose a consciously-declined idea. Read before
proposing a new arc.

Discipline: append-only. A superseded rejection is annotated, never deleted; if a
revisit trigger fires and the idea is reconsidered, add a note pointing to the new
decision rather than removing the entry. Never seed a strawman: every entry is a
real idea that was actually considered and actually rejected, with its real recon
trail.

## CRITICAL distinction (do not mix two registers)

This ledger is for DO-NOT-BUILD ideas only.

BUILD-ELIGIBLE-DEFERRED frontiers -- closure attestation, the counterfactual-
invariance certificate, the Santander mech-gov interop, value-chain obligation
provenance -- are the OPPOSITE: the Gate said build-eligible, just not yet. They
live in their own design docs plus each session handoff's banked-frontier section,
NOT here. Do not file a deferred frontier as a rejection; do not treat a rejection
as merely deferred.

## Entry format

One block per rejected idea:

- Idea: one line, what was proposed.
- Searches run: the reproducible reconnaissance (so the rejection can be re-checked
  against a changed landscape).
- Rejection reason: one or more of -- commoditized / weak-or-absent security
  property / violates the honest boundary / composable-from-existing-primitives
  (name them) / duplicates shipped work / poor strategic leverage.
- Revisit trigger: the specific condition under which to reconsider. State "not
  yet" (a condition that could change) distinctly from "never" (a structural
  rejection that no landscape change reopens).

## Rejections

### R1 -- tlog-proof@v1 relabel of the envelope set-bundle (S196)

- Idea: reuse the Sigstore tlog-proof@v1 inclusion-proof format to label the
  envelope witness fan (the k-of-n cosignature set-commitment bundle).
- Searches run: C2SP tlog-cosignature spec review; Sigstore tlog-proof@v1 schema
  read; envelope_witness.py fan/leaf-order derivation trace.
- Rejection reason: weak-or-absent security property / violates the honest boundary.
  tlog-proof@v1 is a SINGLE-ENTRY inclusion format -- it attests one leaf's presence
  in a log. The witness fan is a SET commitment over n cosignatures (fan order ==
  leaf order == checkpoint order). Relabeling a set-bundle as a single-entry
  inclusion proof would misdescribe what the artifact evidences, an honest-boundary
  erosion. The 0x04 cosignature quorum path already carries the set correctly; no
  relabel is needed.
- Revisit trigger: not yet -- if a genuine single-entry inclusion use case ever
  appears (one leaf, one log, one inclusion claim), tlog-proof@v1 is the right
  format for THAT case, but never for the set-bundle fan.

### R2 -- NL->NOUS drafting via external-API LLM (prompt-grounding + bounded parse-retry) + intent-diff v2 (S219)
- Idea: let a user describe intent in English and receive NOUS source they review,
  drafted by an external-API LLM (DeepSeek v4-flash) grounded on the live EBNF + held-out
  few-shot, gated by a bounded parse-retry loop; plus the intent-diff v2 variant (the LLM
  proposes a verified-property checklist, the user confirms, a deterministic diff compares
  it against verifier output).
- Searches run: in-session R3 measurement, not a web recon. draft_spike.py over DeepSeek
  v4-flash (temperature 0, thinking disabled), grounded on distilled live v2.0 EBNF + three
  held-out few-shot bodies (router, scheduler, aml -- zero fixture bodies in the prompt),
  N=10 locked fixtures (9 = shipped templates, held out of the prompt) + a 4-fixture novel
  probe. Bounded retry appended the exact parser error. Four marks per fixture: first-pass
  parse / post-retry parse / verify-ok / intent-match.
- Result: first-pass parse 10/10 locked after a routing-grounding fix, but verify-ok 4/10
  and intent-match <= 2/10 (fixtures 01 and 07 are R2-class: they parse, verify clean, and
  encode the WRONG guarantee -- a per-cycle cap read as a total cap; a Publisher that
  re-listens the Draft so publish is not strictly gated behind the passing Review). Novel
  clean floor: 1/4 verify-ok. Parse rate and verify-ok moved in opposite directions across
  two prompt-grounding versions, so the parse numbers are prompt-fitting, not a stable
  estimate of drafting quality.
- Rejection reason: violates the honest boundary (drafts that parse and verify-clean but
  encode the wrong guarantee are silent R2 overclaims the parse ceiling hides) / weak
  strategic leverage (the wall is SEMANTIC, not syntactic; parse-level fixes do not clear
  it). intent-diff v2 falls with the arc: it SURFACES divergence but does not make the
  draft correct -- the user hand-corrects a wrong draft every time, and the checklist is
  itself LLM-extracted.
- Revisit trigger: not yet -- reopens only on a mechanism that closes the SEMANTIC gap:
  (a) a verify-ERROR-feedback repair loop (feed verify_program ERROR items back into the
  model, NOT just parser errors -- the one lever this spike did not test), or (b) a
  NOUS-semantics-tuned self-hosted model. NOT "better prompt". NOT GCD (guaranteed-valid
  decoding) alone -- GCD closes the syntactic gap, and R3 failed on the semantic axis.

### R3 -- durable-mark durability benchmark / removal-attack harness (S246)

- Idea: build a NOUS-side image-watermark durability harness -- embed marks, run
  removal/transformation attacks (re-encode, crop, compression, adversarial),
  score survival -- as the durability leg of a two-axis provenance-mark teardown.
- Searches run: WAVES repo + project page + arXiv 2401.08573 (ICML 2024) verified
  current -- 26+ attacks, Performance-vs-Quality 2D plots, HF datasets,
  leaderboard, still the reference; a May 2026 removal paper (arXiv 2605.16796)
  cites it as the benchmark. IMATAG API docs (issuer-gated detection, stored key,
  403 without contract). Image-domain impossibility/coupling anchors:
  arXiv 2311.04378 (strong watermarking impossible incl. private-detection
  setting), 2502.04901 (difficulty of robust + publicly-detectable), 2509.10577
  (sharp coding-limit threshold). NOTE: arXiv 2603.14968, cited in the kickoff as
  the secret-key impossibility anchor, is a TEXT/LLM framework paper (TTP-Detect),
  not an image-domain impossibility theorem; its coupling claim is real but the
  domain and genre are wrong for this lane.
- Rejection reason: duplicates shipped work (WAVES owns the durability leg,
  open-source, standardized, maintained) / poor strategic leverage (a rebuilt
  harness contributes nothing WAVES has not published and inherits its maintenance
  burden) / patent-dense field (IMATAG and others assert watermarking patents;
  building embed/detect wades in, a citation map does not). The durability axis is
  empirically measurable but is not a NOUS moat and sits outside the
  manifest-evidence substrate.
- Revisit trigger: never rebuild. If a durability measurement is ever required,
  use or extend WAVES; do not re-implement. SCOPE NOTE: this rejection covers the
  HARNESS only. The narrow a50-style two-axis MAP (durability CITED from WAVES,
  independent-verifiability CLASSIFIED as a structural trust-model property, no
  measurement claim, no "proves") is BUILD-ELIGIBLE-DEFERRED, not rejected -- it
  lives in its design doc + the S246 handoff banked-frontier section, banked
  behind the OJ flip and the 2 Dec 2026 Article 50(2) marking date.
