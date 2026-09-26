# Reserved Verb Audit -- where the tree says "proves" and what it earns (S376)

<!-- __s376_reserved_verb_audit_design_v1__ -->

Status: decisions D376-1 to D376-10 recorded before any code. Build notes
are appended in section 9 with the patches that implement them.

Marking. [container] is a value measured in the chat container on a
clone of 8ec9e61 whose bytes were tied to Server A by the 39 file shas
of the S376 RULE 0 paste (2026-09-25 00:28:01Z), on 2026-09-25 between
00:26Z and 09:13Z. [reading] is a statement from reading the source at
8ec9e61. [external] is a public source read on 2026-09-25.

---

## 1. Problem

README.md:36 reserves the word "proves" for the three Z3/Farkas legs:
the cost-cap bound, policy-coverage and sequence-ordering. Everything
else evidences. ADR-0004 states the same split. The operator asked
whether README.md:272 earns the word for Runtime Conformance. It does
not: conformance.py:17-20 says the verdict needs no Z3, and that
discharge and bound transfer are interval checks and a Decimal sum
[reading]. The same sentence ships as the `nous conformance` help text
(cli_conformance.py:53) and, through pyproject `readme = "README.md"`,
as the PyPI long description. claim_lint passes it, because a reserved
word is a violation only when it binds to a fixed list of objects that
does not include trace, run, verdict or certificate (claims.toml
[object]). A single line pointed at a class, so the whole tree was
classified.

## 2. Method [container]

Every occurrence of the verb family (prove, proves, proven, proved,
proving) in tracked *.md, *.html and *.py outside tests/ and
website/.well-known/ was extracted: 1156 occurrences in 152 files,
from prose, from Python string and comment tokens (identifiers
excluded by tokenize), with the sentence around each. Three base64
payloads in two wheel modules were decoded and scanned too: 20 more
occurrences (continuity_verifier.py CONTINUITY_VERIFY_OFFLINE_PY,
ndec.py VERIFY_NDEC_PY and README_NDEC_TXT).

Classes:

    EARNED    the object is a Z3 or Farkas result of a declared leg
    NEG       negated ("proves nothing", "does not prove")
    MENTION   the word is mentioned (rules, quoted defects, labels)
    PROCESS   engineering jargon (a test or a run demonstrated it)
    OVER      applied to signatures, hashes, trace checks or bindings
    SCOPE     a Z3/Farkas leg, but the object reaches past the leg
              (spend, "the rules", agent behaviour)
    EDGE      exact arithmetic that is neither a Z3 cost bound nor a
              Farkas certificate
    LATENT    code that would print the word for an untiered item
    STALE     repo-root scripts outside the wheel and the suite
    UNCLEAR   design-doc wording not settled by reading

All 769 occurrences not settled by an automatic rule were read one by
one. Of 264 automatic negations, the 34 whose negator is not adjacent
were read and 4 misreads fixed; the 230 with an adjacent negator were
not read individually. Of 117 automatic mentions, the 43 that are not
rule statements or bare schema strings were read, with no error.

Result, current surfaces (README, website pages other than the blog
index, docs, the wheel's strings and embedded verifiers): 53 OVER in 26
files plus 8 in the decoded continuity verifier, 11 SCOPE in 5 files,
9 EDGE in 3 files, 2 LATENT. History: 36 OVER in the blog index, 6 in
CHANGELOG, 15 in design docs.

Reproducer: s376_classify.tar.gz (scripts, inputs, every decision) and
S376_PROVE_CLASSIFICATION.tsv, held in the operator's downloads; their
sha256 are in the S376 handoff. Not covered: the noun proof/proofs
(835 lines), guarantee/ensure/prevent (108 lines), tests/, and
bytes.fromhex or zlib payloads in 10 files (not read).

## 3. Findings on current surfaces [container]

F1. The continuity offline verifier prints "PROVES:" for three checks
that are neither Z3 nor Farkas (decoded payload lines 1043, 1050,
1073): segment in-envelope conformance (S185, a boolean over committed
certificate fields), segment cap-value monotonicity (S186, a value
comparison) and segment policy-digest constancy (S187, digest
equality). Under --json it emits `"proven"` keys in the
segment_inenvelope, segment_cap_monotonic and segment_policy_monotonic
objects. The source is base64, so neither claim_lint nor a text search
sees it. docs/CONTINUITY_LEDGER.md:176 argues for the word on purpose;
the same doc says at :18 and :77 that the budget envelope is the only
such leg, README.md:36 lists continuity cosignatures as evidence, and
README.md:287 already describes the S185 leg with "VERIFIES".
CONTINUITY_LEDGER.md does not document S186 or S187 at all, and still
calls cap monotonicity future work.

F2. Runtime conformance: README.md:272; cli_conformance.py:53;
docs/RUNTIME_CONFORMANCE.md:12, 138, 158, 169, 217, 252;
docs/GATED_ACTIONS.md:16, 107, 109, 116; docs/SEQUENCE_LAWS.md:38,
258; docs/ANNEX_IV_MAPPING.md:178; conformance_verifier.py:19. The
spread traces to docs/RUNTIME_TRACE_EMISSION_DESIGN.md:56, which asked
for its conformance sentence to reach every public surface verbatim.
RUNTIME_CONFORMANCE.md:12 is also false as stated: the Z3 bound is over
the declared envelope, and a run can exceed its declared envelope,
which is what the certificate checks.

F3. Signature, hash and transparency evidence given the verb: the
Annex IV sidecar (annex_iv_map.py:9, 463 and the printed boundary line
at :610; cli_dossier.py:177); rekor_anchor.py:183; trace_anchor.py:4;
remedy_proof.py:4; signerctl.py:23; trace_bridge.py:476 (comment);
cli_verify_release.py:22; envelope.py:20, 400, 401 (a docstring and
comments naming a "tier" for set operations);
docs/ANNEX_IV_MAPPING.md:316, 763; docs/ATTESTATION_RECEIPT.md:14, 16,
185, 280; docs/WITNESSED_RUN_EVIDENCE.md:15, 49, 54;
docs/VERIFY_DOSSIER.md:16; trace/SPEC.md:58, which contradicts its own
rule at :55.

F4. Site: website/runtime.html:289 ("the behaviour NOUS" plus the
verb); website/lending.html:365, a heading over evidenced items next to
"zero trust in any party"; website/docs/index.html:625, a sample output
in the pre-S228 severity-count format.

F5. Scope: website/index.html:331, 372, 492, 524, 570, 748 and 910 say
the declared rules hold across every path the agent could take; the
same page at :430 already uses the exact scope ("on every path the
declarations allow"). Also docs/EU_AI_ACT_COMPLIANCE.md:35 (generic
"constraints"), website/lending.html:176, docs/SEQUENCE_LAWS.md:162 and
docs/COST_VERIFICATION_GUIDE.md:479 (spend readings).

F6. docs/COST_VERIFICATION_GUIDE.md:477 and :529, a demo script: it
says NOUS establishes reliability, claims to be the first language of
its kind, and attributes to EU AI Act Article 15 a duty to "declare and
prove" performance metrics.

F7. Edge: the coverage gap witness (cli_verify.py:812, 933;
coverage_farkas.py:1370, 1381, 1625; dossier.py:1766, 1769) is a Z3
counterexample re-checked in Fraction arithmetic. The S121 monotonicity
text in the VERIFY_OFFLINE_PY_CHAIN template (dossier.py:214) describes
a closed-form containment check with no solver.

F8. Latent: website/ide.html:1757 counts an item with no tier as
PROVEN. Every PROVEN-severity item carries a tier today
(verifier.py:148-158), so nothing prints wrong now.

## 4. Prior art in the tree [reading]

S361 and S362 swept spend claims (docs/ONE_PRICE_SOURCE_DESIGN.md 14.1
and 14.11): blog lines were corrected in place, design documents were
left as dated records, a CHANGELOG error was corrected by a later
entry, and the corrected copy is bound by tests/test_s361_runtime_copy.py
and tests/test_s362_claims_copy.py. That sweep did not audit CLI help
strings or .py docstrings, which is why cli_conformance.py:53 survived.
Two lines it judged acceptable (website/index.html:857,
website/coverage.html:79, "in the proven bound") stay as judged.
scripts/claim_lint.py:25 already names the blind spot: a decidable
boolean check given the verb is not caught. docs/NOUS_VSA.md:122 fixes
the output convention used below: a verifier banner names each leg as
PROVES or EVIDENCES.

External [external]: RFC 9943 (SCITT) uses "proof" loosely for
registration evidence, so the rule here is stricter than the standards
on purpose; the terms of art "inclusion proof" and "consistency proof"
stay. GNATprove reports each check under the method that settled it
(flow, interval, provers, justified), which is the practice D376-3
follows. Google AIP-180 treats renaming a field as removing it.

## 5. Reasons the correction should not exist (Article V)

R1. Churn with no reader benefit: readers understand the lines as
written. Rejected: the reader NOUS writes for is an auditor, and the
distinction is the product (ADR-0004).

R2. The standards use "proof" for transparency receipts, so the rule
fights the field. Rejected: the terms of art stay; the rule governs the
verb NOUS applies to its own results.

R3. Renaming a JSON key breaks --json consumers (AIP-180). Weighed in
D376-3: the verifier is emitted by the installed nous, so nothing
changes for a consumer until they upgrade and re-emit; the only
consumers in the tree are four test files; the output is printed, not
signed or anchored. A kill criterion (K5) covers a consumer appearing.

R4. Overcorrection turns true claims into weaker ones (Article IV,
understatement). Answered by D376-2: only OVER and SCOPE occurrences
are edited, each by id, and every replacement names the method.

R5. Editing dated blog posts rewrites history. Answered by the S362
precedent and by git: posts keep their dates, the diff is public.

R6. Opportunity cost: the claude price cliff (D8) lands 2026-12-08.
Answered: D8 is an operator pricing decision with no build work until
it is taken; this audit needs no release until the next one.

## 6. Decisions

D376-1. The rule, stated once. "Proves" is used only for (i) a Z3
result on the cost-cap, policy-coverage or sequence-ordering leg,
including a refutation of such a leg re-checked in exact arithmetic
(the coverage gap witness), and (ii) a Farkas certificate checked in
exact rational arithmetic (cost cap, coverage, budget envelope, hop and
net containment). Everything else evidences or verifies and names its
method. ADR-0004 gains an evidence-ledger line pointing here, in
patch A.

D376-2. Scope. Corrected: README, website pages other than the blog
index, docs/*.md that are not design records, trace/SPEC.md, CLI help
and printed output, docstrings and comments in wheel modules, and
embedded verifier sources including base64 payloads. History: the blog
index is corrected in place (S362 precedent); CHANGELOG is corrected by
a new entry; design documents and trace/archive/ stay as dated records,
and this document supersedes RUNTIME_TRACE_EMISSION_DESIGN.md:56 on the
point of wording. Out of scope: repo-root scripts outside the wheel,
another lane's files, signed or pinned artifacts already published.
Only occurrences classified OVER or SCOPE are edited, each named by its
id in the classification.

D376-3. Continuity verifier (F1). The printed prefix of the S185, S186
and S187 lines changes from PROVES to EVIDENCES, and "NOT proven" in
their NOTE lines becomes "does not hold". In the three --json objects
the key `proven` becomes `holds` (a false value must read as a failed
property, which `checked` would not), and every --json object the
verifier prints carries `report_schema_version: 2`. The fail-closed
behaviour, the exit codes and the PROVES-budget line (a Farkas leg)
are unchanged. CONTINUITY_LEDGER.md replaces the argument at :176 with
the reason the leg evidences, documents S186 and S187, and maps the old
keys to the new ones; CHANGELOG marks the change breaking for --json.

D376-4. Conformance (F2). Conformance copy says the certificate checks
and evidences: six obligations recomputed from the signed trace, a
signed verdict, fail-closed on preconditions. RUNTIME_CONFORMANCE.md:12
states the true relation: Z3 bounds the declared envelope against the
cap; a run can exceed its declarations, and the certificate checks
whether it did.

D376-5. Edge (F7). The gap witness keeps the verb under D376-1(i); its
text already limits the claim to the carried point. The S121 wording in
VERIFY_OFFLINE_PY_CHAIN becomes "verified (closed-form containment)",
provided a search shows no committed copy or pinned digest of that
template other than the verifier registry. A changed template gets a
new registry entry at the next release; entries of released versions
do not change.

D376-6. Scope copy (F5). The homepage lines take the wording of
website/index.html:430. EU_AI_ACT_COMPLIANCE.md:35 names the three
legs. The spend readings are scoped to the declared envelope, as S362
did.

D376-7. Site and demo copy (F4, F6). The verb leaves runtime.html:289
and the lending heading; the lending page states the trust it actually
needs (pinned keys, operator-asserted binding of key to name). The
docs sample output is regenerated from the current verifier. The demo
script loses the reliability line, the first-language claim and the
Article 15 sentence; no new legal statement replaces it.

D376-8. Binding. Each patch carries a copy test in the pattern of
tests/test_s362_claims_copy.py: every corrected site no longer carries
its old phrase, and the decoded base64 payloads carry no PROVES label
other than PROVES-budget. Each test is red on the tree before its
patch, by set and reason.

D376-9. Lint last. claims.toml is widened only after both patches, and
only with a false-positive rate measured on the corrected tree
(claims.toml records a predicate killed at 100% false positives).
Whether claim_lint decodes base64 payloads is decided then.

D376-10. Deferred, recorded: F8 (the IDE tier default); the tension
between README.md:36 and ADR-0010 on runtime gating; the noun and the
guarantee/ensure/prevent families; the STALE root scripts; the 9
UNCLEAR design-doc lines on chain completeness.

Order: this document first (docs only); then patch A (README, site,
docs; the site deploy takes its own approval); then patch B (the wheel:
continuity verifier, help strings, docstrings, tests, CHANGELOG),
which reaches users only with the next release.

## 7. Kill criteria

K1. An edit would change a published signed or pinned artifact
(website/.well-known, a released VSA bundle, a registry entry of a
released version): that edit stops.

K2. An edit touches an occurrence classified EARNED, NEG or MENTION:
rejected.

K3. A relabel changes a verdict, an exit code or a fail-closed path:
stop; the change is no longer vocabulary.

K4. A copy test cannot be made red on the tree before its patch: it
has no teeth and does not ship.

K5. A consumer of the continuity --json keys outside this repository
becomes known before patch B ships: D376-3 switches to adding `holds`
beside a deprecated `proven`, removed at the next major version.

K6. A replacement introduces a word outside claims.toml's allowed claim
words or a new overclaim of its own, read by hand (claim_lint misses
claim classes).

## 8. Honest boundary

This audit classifies wording; it changes no verifier result. The
classification is one reader's single pass with the controls stated in
section 2; the adjacent-negation class was not read line by line. A
line marked EARNED says the word matches the rule of D376-1, not that
the claim around it is complete.

## 9. Build notes

(appended with the patches)

### 9.1 Patch A (S377)

<!-- __s377_reserved_verb_patch_a_notes_v1__ -->

Input. S376_PROVE_CLASSIFICATION.tsv at its sealed sha256 (3b9a59f0...). The
copy first uploaded in S377 was the file as it stood before the S376 09:12Z
correction (sha256 950f39ca...); replaying that correction (the note column of
b0005 to b0009, all py-b64 rows of patch B) reproduced the sealed bytes, and a
mutated control did not [container].

Scope applied. 79 edits in 16 files cover 82 OVER and
SCOPE ids on README, website pages, the blog index, docs and trace/SPEC.md,
plus the D376-7 trust line of website/lending.html and the ADR-0004 ledger
line (D376-1). In 17 of the 82 ids the verb stays because the
corrected sentence is a Z3 or Farkas leg once its object is scoped (the
homepage lines of D376-6, the spend readings, index.html:910 and
lending.html:176 as the coverage leg, the regenerated sample's tier count);
in the other 65 it is replaced by a verb from claims.toml's
allowed claim words, with the method named in the sentence or its paragraph.

D377-1. The seven OVER ids in docs/CONTINUITY_LEDGER.md move to patch B. Three
of them (:174, :186, :198) describe the verifier's printed label and --json
key, which change only in patch B; editing them first would make the doc
describe output that has not shipped. The file is edited once, with the
relabel, the S186 and S187 sections and the key map of D376-3.

D377-2. The OVER id in trace/archive/NOUS-TRACE-spec-v0.2.md stays unedited:
trace/archive is a dated record under D376-2.

D377-3. website/docs/index.html: the sample output is regenerated (D376-7)
from templates/sequence_law_demo.nous, which ships in the wheel.
gate_alpha.nous, the program the old sample showed, now verifies FAILED (two
of its models are not in the pricing table), and a failing run would not
illustrate the section. The block is the verbatim output of `nous verify` in
the chat container on 2026-09-25 10:27:29Z (z3 4.16.0, clone tied to Server A
by sha256), with non-ASCII characters written as HTML entities so the
inserted bytes are ASCII. Its cost lines depend on the shipped prices and its
elapsed_ms line on the machine.

D377-4. The blog's sample output (history, hand-abbreviated at the time)
keeps its form; its pre-S228 severity count reads "10 checked" instead of
"10 proven". It is not regenerated.

D377-5. No marker is added at the edited sentences. Each site is bound by
tests/test_s377_reserved_verb_copy.py, parametrized by classification id:
the old phrase is absent and the corrected phrase present, with whitespace
normalized so a phrase may span a wrapped line. The test was red on the tree
before the patch for every id, by set and reason.

Observed, not edited (outside the classified ids): website/lending.html keeps
"0 trust in the issuer" (stat card) and "zero trust in the issuer" (list
item), while its boundary line now names the pinned keys and the
operator-asserted binding; docs/COST_VERIFICATION_GUIDE.md keeps "audit-ready
Annex IV compliance" in the demo script; website/index.html:492 keeps
"all-paths proof of conformance" (the noun family, D376-10); the blog's EDGE
ids on its v5.30.0 lines are unchanged (D376-5 covers only the wheel).

### 9.2 Patch B (S377)

<!-- __s377_reserved_verb_patch_b_notes_v1__ -->

Scope applied. The wheel's OVER ids: 12 in Python strings and 3 in comments
(annex_iv_map.py, cli_conformance.py, cli_dossier.py, cli_verify_release.py,
conformance_verifier.py, envelope.py, rekor_anchor.py, remedy_proof.py,
signerctl.py, trace_anchor.py, trace_bridge.py), the 8 decoded continuity
verifier ids (D376-3), and the 7 docs/CONTINUITY_LEDGER.md ids moved here by
D377-1, with the S186 and S187 sections and the key map D376-3 asks for. The
CHANGELOG [Unreleased] section marks the --json change as breaking.

D377-6. The S121 wording in VERIFY_OFFLINE_PY_CHAIN (dossier.py:214) stays.
D376-5 made its change conditional on no committed copy or pinned digest of
the template other than the verifier registry; the search found one,
tests/baselines/s130_verifier_snapshots.json (test_s130_verifier_snapshot.py),
which pins VERIFY_OFFLINE_PY_CHAIN at a0e0b83a... [container, 1e48bce]. The gap
witness keeps the verb (D376-5), so the 8 EDGE ids of the wheel are unchanged.

D377-7. K5 was searched before the rename: in the tree, the consumers of the
three --json objects are tests/test_s185, s186, s187 and s187b; a web search
for "segment_inenvelope" found no outside use; GitHub code search needs an
authenticated token and was not run. No outside consumer is known, so D376-3
option (a) stands.

D377-8. The continuity verifier payload is decoded, edited at 12 anchors (the
three labels, the two NOTE lines, the five keys, report_schema_version on the
FAIL and PASS objects) and re-encoded in the original format (76-character
chunks in the same wrapper). Before the edit, re-encoding the unedited payload
reproduced the file byte for byte [container]. The patch markers inside the
payload (__s185_p1_proves_print_v1__ and the S186 and S187 ones) are
identifiers and stay.

D377-9. The four test files change their label constants and the JSON
expectations (FG-S376-C). With only the tests changed, every positive
assertion on the new labels and keys fails against the unedited verifier; the
fail-path assertions then check that the new label is absent. Comments in
those tests that describe the old label are outside the audit and stay.

D377-10. tests/test_s377b_reserved_verb_wheel.py binds patch B: the decoded
continuity payload carries no PROVES label other than PROVES-budget, no
"proven" key, five "holds" keys and two report_schema_version fields; each
corrected string, the ledger ids and the CHANGELOG entry by id. The ndec
payloads carry no PROVES label today, so a check on them would have no red
state before this patch and is not added (K4).

### 9.3 /v1/verify labels (S378)

<!-- __s378_verify_labels_notes_v1__ -->

Input. The ledger lane's brief to the release lane,
NOUS_S373_BRIEF_V1_VERIFY_LABELS.md (sha256
abcea3e3463f0a21b884de6fdc2ab0602732fa03886d3f380b75c417b7049da9), its
byte references candidate.py (sha256
db3d5ed41045a314cb740b4202b22d5c2e90053e0490e96d311edde19f75014a), both
held outside the repository, and the operator's rulings of 2026-09-25:
option B (the 200 body of /v1/verify changes in place, in the release
that carries patch B) and D378-1 with four amendments.

Marking. [container] is a value measured in the chat container on a
clone of 4738cd3 tied to Server A by the 45 file shas of the S378 RULE 0
paste (12:18:20Z). nous_api_server.py, verifier.py and website/ide.html
are unchanged since 8ec9e61, the tree the classification was made on.

D378-1. K2 yields to the brief only where an edit cannot be avoided.
One classified occurrence is edited: o1109, the fallback in
website/ide.html:1757 that counts an item with no tier as PROVEN (F8,
deferred by D376-10, closed here). o1110 (:1758) and o1112 (:1765) stay
byte-unchanged, because the v2 path filters by tier and needs no edit
there. A checker compared every classified line of the three files the
arc edits, before and after the drafted edit: one EARNED, NEG or MENTION
row changes, and it is o1109 [container].

D378-2. o0698 and o0699 (nous_api_server.py:287 and :319, the served
"proven" key) stay byte-unchanged. Their EARNED class was not true when
S376 sealed it: the key carried every passing item whatever its tier.
S373 N1 (Server A, 09:01:58Z) found 6 items in it for
aml_transaction_governance.nous, tiers ESTIMATED 2, PROVEN 1 and
VERIFIED 3. Over the 48 tracked .nous programs the route answers with
200, it carried ESTIMATED 98, VERIFIED 143, REPORTED 115 and PROVEN 9
items [container, 12:24Z]. The class becomes true with the v2 body,
where the key carries tier PROVEN only.

D378-3. The sealed classification is inconsistent at one place: o1109
(ide.html:1757) is EARNED, while the LATENT rows o1111 (:1763) and o1114
(:1778) name the same fallback as their cause. The TSV stays as sealed
(3b9a59f0...); this note is the record.

D378-4. The v2 body (brief section 4), for the 200 body only.
"schema_version": 2 is the first key. The keys that follow keep their
order and values, except that "proven" holds the passing items whose
tier is exactly "PROVEN", and "evidenced", inserted right after it,
holds every other passing item (tier VERIFIED, ESTIMATED, REPORTED, null
or absent), each list in the verifier's order. Every item in both lists
carries severity "PASS"; code, category, message, tier and the item's
key order are unchanged. ok, stage, errors, warnings, info and
total_checks are unchanged. The validate branch carries "proven": [] and
then "evidenced": []. A passing item is an item of severity PROVEN. An
item of any severity other than ERROR, WARNING, INFO and PROVEN makes
the route refuse with 422 VERIFY001 instead of being relabelled PASS
(axiom 5). Error bodies are out of scope and unchanged.
KEY = "evidenced": the operator's amendment to brief section 8, decided
by the skillctx replication at 11:38Z (no significant excess of empty
responses on either provider; Chutes Holm p 0.549, Parasail Holm p
0.413). That result is testimony from the skillctx lane, not re-measured
here.

D378-5. Two surfaces, two names. The continuity verifier's --json uses
"holds" with report_schema_version 2 (D376-3), for a boolean property
that may be false. The /v1/verify body uses "proven" (tier PROVEN only)
and "evidenced" with schema_version 2, for lists of passing items. The
/v1/verify names are the ones the skillctx lane tested; neither surface
is renamed without a new test.

D378-6. E5 of docs/CLAIM_LINT.md is amended by one table row added below
its row, not by an edit of it. o0249 and o0250 (:177) keep their bytes
and their line number [container, the checker of D378-1].

D378-7. The IDE (website/ide.html) reads both shapes: schema_version 2
means "proven" plus "evidenced"; no schema_version means the legacy
"proven"; any other value renders a refusal and no counts. The tier
fallback of o1109 is removed. An item whose tier is none of the four is
listed as UNTIERED and counted in no tier; the count lines name that
group only when it is non-empty. website/verify-fix.js was read whole:
no tracked page loads it (git grep finds it only in website/README.md),
so it stays unchanged and needs no cache purge.

D378-8. Order: the website deploy precedes the nous-api restart on
Server A. The IDE deployed today opens its result view only on a
non-empty "proven"; under v2, 30 of the 39 tracked programs that
complete verification come back with an empty "proven" [container], and
that IDE would show them as failed.

D378-9. Out of scope (brief section 5): the severity axis and
VerificationResult.proven in verifier.py (PyPI consumers; S228 guards
the renders), cli.py, mitosis_engine.py and the error shapes. The NOUS
skill's SKILL.md changes after the release (brief section 6, step 7).

D378-10. Tests. A contract test on the route checks (a) no item with a
tier other than PROVEN in "proven", (b) no "severity":"PROVEN" anywhere
in a 200 body, (c) "proven" plus "evidenced" equals the verifier's
passing items in order, (d) schema_version is the first key and equals
2, and (e) the validate-branch shape. It is red on the tree before the
arc, by set and reason. tests/test_verify_tier_routing.py keeps a local
copy of the routing contract; the copy is amended to v2 with the
rationale in its docstring, not deleted.

The version of the release is the operator's ruling at the bump. The
release carries two breaking changes to machine-read output: this body
and the continuity --json of D376-3.

### 9.4 The docs positioning line (S379)

<!-- __s379_positioning_line_notes_v1__ -->

Marking. [container] is a value measured in the chat container on a
clone of 31b7f73 tied to Server A by the 53 file shas of the S379 RULE 0
paste (2026-09-26 00:29:36Z).

Finding. website/docs/index.html:206, written in S171 (marker
__s171vsa_docs_positioning_v1__), says NOUS "is a formally-verified
language and runtime for governed agentic AI". What NOUS proves is the
declared envelope, with Z3 and Farkas certificates, and the next
sentence of the same paragraph (line 207) states exactly that. The tree
tracks no proof file for the language or the runtime (no .v, .lean,
.thy, .tla or .agda file) [container]. The line is the only
self-description of that form in website/ and README.md [container]. The
S376 classification has no row for it (the classification covers the
"prove" family), and claim lint, tests/test_s362_claims_copy.py and
tests/test_s377_reserved_verb_copy.py do not bind it [container]. The
nous skill's SKILL.md repeats it on line 8; the release lane removed it
in the draft c036944f sent to skillctx, outside the repository.

A correction of an overclaim inside this audit, not a new arc: no
Innovation Gate (Constitution, Article VI).

D379-1. Line 206 only. " is a formally-verified language and runtime
for governed agentic AI." becomes " is a language and runtime for
governed agentic AI." No word is added. The proved claim stays in line
207, so the edit removes an overclaim and adds no underclaim. File sha
pre 9dbb5f80fde7d985, post 8bfdd88b85871ebc [container].

D379-2. The scope is the self-description only. "Formal Verification"
as the name of the verify stage stays, under D376-10 (the noun family):
verifier.py:1212 (the printed banner, in the wheel), cli.py:1853 (help),
website/docs/index.html:157, 470, 601, 603, 715, 755, 916 and 1869,
website/index.html:9, 395, 401, 776 and 1053, website/runtime.html:702,
and the post title at website/blog/index.html:913 and 3410. The site
demos copy the verifier's output, so renaming the stage on the site
alone would make the site disagree with the tool. The nearest next
candidate is the heading "Formally Verified" at website/index.html:395.

D379-3. tests/test_s379_formally_verified_copy.py, red on the tree
before the edit (K4): (a) the old phrase is absent from
website/docs/index.html; (b) the new sentence is present there, so (a)
cannot pass by deleting the paragraph (FG-S376-C); (c) neither README.md
nor any .html file under website/ says "is a formally-verified" or "is a
formally verified", so the self-description cannot return elsewhere.
Each assertion is on a precomputed value (FG-S377-B). docs/ is not
scanned: design documents quote the old phrase, this section included.

D379-4. The site and one test; no file in the wheel changes, so no
PyPI release. Order: this section (commit, push); then patch B (the
test red first, the edit, the host gates); commit; push; deploy through
scripts/deploy_website.sh after the commit, dry run first; the served
mirror check after the deploy. Each irreversible step has its own
approval.
