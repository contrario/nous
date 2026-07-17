# NOUS S246 Addendum -- post-seal corrections

The S246 handoff was sealed at HEAD b2ef2e4. Two commits and one external
correction landed afterward. This file records the deltas in repo-durable form so
the next RULE 0 reconciles against live bytes, not the stale download. It does not
supersede the handoff's other sections.

## HEAD progression after the sealed handoff

- b2ef2e4 -- R3 rejection (durability harness), the handoff's own commit.
- 54cda29 -- docs(a50): two-axis marking map design doc (this directory).
- cf2ece7 -- docs(a50): a50 page correction (see below). Current HEAD == origin/main.

RULE 0 expected HEAD for the next session is cf2ece7, not 54cda29.

## a50 page correction (post-seal, external)

Leonard Rosenthol (Chair, C2PA Technical Working Group, Adobe) flagged two points on
the a50 page after the seal. Both correct, both fixed and deployed at cf2ece7.

1. Spec vs implementation. The a50 SDK findings F2-F5 are behaviours of the measured
   implementation -- c2pa-rs 0.89.0 / c2pa-python 0.36.0 -- not of the C2PA
   specification (which ships no reference implementation). Attribute
   implementation-level behaviour to the library, never to "the standard." The one
   claim that stays spec/architectural: the metadata layer does not survive a
   re-save (a property of where the manifest lives).
2. AI-generation. The page previously said no C2PA manifest can answer whether a
   file is AI-generated. That was wrong and is fixed. A manifest can carry the
   signer's AI-generation declaration (a c2pa.created action with
   digitalSourceType: trainedAlgorithmicMedia). The honest statement: a manifest
   carries a signed, optional declaration -- it evidences who asserted which label,
   not whether the label is true; the spec does not mandate the disclosure, so its
   absence proves nothing.

Effect on the two-axis map design doc (this directory): none. The doc carries no
AI-origin wording and no spec-vs-implementation misattribution (verified against
bytes). Its C2PA characterization -- publicly verifiable when present, strippable --
is unchanged and consistent with the corrected page. The independent-verifiability
axis is unmoved: the AI-origin label being signer-asserted is a content-trust
property, not a signature-verifiability property.

## a50 F4/F5 upstream drafts (not committed, not filed)

Both findings were re-verified reproducing at c2pa-rs main HEAD
f8f26657162a4177746946234f8b071fae298569 by reading current source (the review
checkout was lost; line numbers re-anchored). The drafts are recoverable ONLY from
Hlias's saved downloads; they are not in any repo.

- F5 (timeStamp.trusted emitted outside the verify_trust guard, claim-v1 scope):
  real defect, not a duplicate. Emission introduced by #1191. Suggested fix: move
  the emission inside the guard (verify.rs:535-583); no timestamp-trust-skipped
  constant exists, so do not propose emitting one. File-ready. NOT filed.
- F4 (SIGNING_CREDENTIAL_OCSP_SKIPPED defined but emitted from no path): the
  "oversight" framing is an overclaim. PR #1489 (commit abaf71fb) codifies a
  deliberate silent-default OCSP pattern -- returning Ok(OcspResponse::default())
  without a status when a result cannot be validated. Reframe F4 as a low-priority
  observability feature-request, or drop it. Also check issue #1608
  (timestamp/OCSP no-status, closed) before any file. NOT filed.

Filing is Hlias's outreach; deferred with no deadline (the a50 six-week clock starts
at distribution, not deploy).
