# Innovation Gate Dossier -- Conformity Declaration Attestation

STATUS: RESEARCH ONLY. No code, no patch, no release. Committed as a banked-frontier
record. NOTHING IN THIS DOSSIER IS IMPLEMENTED, and its presence in docs/ is not a claim
that any described object exists.
Session: S238. Recon anchored to repo commit bed268a (tree clean, HEAD == origin).
Board state re-reconciled at 6343689 immediately before commit; Section 9 reflects 6343689.
Gate per NOUS Engineering Constitution Article VI. Sections in order, none skipped.
Section 6 (Reasons This Should Never Exist) was written BEFORE Section 7, per Article V.

PROVENANCE NOTE. This file is a clean-room rewrite. An earlier draft of this dossier,
produced in the same session, carried content whose authorship could not be accounted for
line by line. Rather than commit a sha pointing at bytes of uncertain origin (Article XI:
a hash without accountable bytes pins nothing), the dossier was rewritten from scratch in
a single authored pass. The earlier file is retained, unmodified, for comparison. Nothing
in this file is inherited from it; every line here is authored deliberately.

LEDGER READ. docs/REJECTED_IDEAS.md @ bed268a. Two entries: R1 (tlog-proof@v1 relabel of
the envelope set-bundle), R2 (NL->NOUS drafting via external-API LLM). Neither is this idea
nor a neighbour of it. Not re-litigating anything.

---

## 0. THE ONE QUESTION, ANSWERED FIRST

**Does Annex V require a NAMED NATURAL PERSON? NAI.**

Annex V point 8, Regulation (EU) 2024/1689: the place and date of issue of the declaration,
the name and function of the person who signed it, as well as an indication for, or on
behalf of whom, that person signed, a signature.

Verified against the European Commission's own AI Act Service Desk
(ai-act-service-desk.ec.europa.eu/en/ai-act/annex-5) and three independent reproductions of
the OJ text of 13 June 2024. The kickoff's premise is NOT weaker than stated. It holds.

Three further primary-text findings the kickoff did not carry. Each one changes the design.

**(a) Annex V point 3 is a SECOND accountability hook.** The declaration must state that it
is issued under the SOLE RESPONSIBILITY OF THE PROVIDER. The Act therefore binds
responsibility twice: to the legal person (point 3, reinforced by Art 47(4)) and to the
natural signatory (point 8). The kickoff design binds only the natural person and drops the
provider-level hook entirely.

**(b) Art 47(1) ALREADY REQUIRES THE DoC TO BE MACHINE-READABLE.** Verbatim: the provider
"shall draw up a written machine readable, physical or electronically signed EU declaration
of conformity for each high-risk AI system." No other CE-marking regime surveyed (Machinery,
MDR, RED, LVD, EMC, RoHS) imposes machine-readability on the DoC itself. No format is
specified. None exists. That vacancy -- not the signing -- is the only ground this idea has
to stand on. See Section 7.

**(c) Art 47(2) BREAKS BYTE-DETERMINISM, AND THIS IS STRUCTURAL.** The DoC "shall be
translated into a language that can be easily understood by the national competent
authorities of the Member States in which the high-risk AI system is placed on the market."
A legally effective DoC is therefore an N-language family of documents. Canonical bytes and
translation are incompatible: the canonical bytes CANNOT BE the legal instrument. Any design
that does not confront this ships an object that cannot be what it claims to be.

**OMNIBUS CHECK, CLOSED: PUBLISHED AS REGULATION (EU) 2026/1744.** OJ L, 2026/1744,
24.7.2026, CELEX 32026R1744. Signed 8 July 2026, Strasbourg. Council adopted 29 Jun 2026,
Parliament 16 Jun 2026. ENTRY INTO FORCE 27 JULY 2026. Article 4 states only "the third day
following that of its publication"; the date itself is written VERBATIM FOUR TIMES in the
enacting text -- recital (18); Article 1(37)(a) replacing Article 97(2); Article 1(40)(c), the
new Article 113 third paragraph point (d); and Article 3(3)(a) amending Regulation (EU)
2023/1230 Article 47(2). The date is READ, NOT COMPUTED. PUBLISHED IS NOT IN FORCE, and it is
not in force at the time of this edit.

THAT FINDING IS NOW PRIMARY, NOT SECONDARY. A byte-read of the published enacting text
(Article 1 items (1)-(43) and Articles 2, 3, 4, read in full) carries NO amending instruction
against Article 47 and NONE against Annex V. Both survive intact -- FG-S239-A: in an amending
act, silence is survival, not removal. Recorded at commit 82a32bf.

CORRECTION TO COMMIT 27d7a21. That commit stated the secondary-source detail about Annex VIII
section B points 7 and 9 was not covered by the read, and withdrew it. WRONG, in the
UNDERSTATING direction. Article 1(42) reads: in Annex VIII, section B, points 7 and 9 are
deleted. Recital (22) gives the reason (registration streamlining for Article 6(3) systems).
Item (42) is inside the (1)-(43) range that was read. The primary CONFIRMS the secondary and
the detail is restored. The error was treating silence in a commit MESSAGE as absence from the
READ -- FG-S239-A applied to the wrong artifact.

NOTED, and it does NOT disturb Article 47 or Annex V: Article 50 IS touched by this act.
Article 1(20) replaces Article 50(7), and recital (41) states that codes of practice have
limited legal effect and in particular do NOT grant a presumption of conformity. Article 50(2)
itself is unamended. The annexes this act touches are I, VIII, and the new XIV.

---

## 1. PROBLEM STATEMENT

NOUS today produces a signed manifest binding an artifact's digests (source_sha256,
ast_sha256, pricing_sha256, smt_obligations_sha256) to a Z3 cost envelope and Farkas
coverage certificates. It produces per-decision runtime attribution (AuthorizationAttestation:
WHO recorded a decision on a gated action) and per-envelope temporal pre-commitment (PCE:
WHEN the envelope was anchored relative to the build it governs).

It produces nothing that connects the person who assumes legal responsibility for the system
to the exact artifact whose properties were checked.

The Annex V DoC -- the instrument in which that responsibility is legally assumed -- exists
in the world today as an unstructured document with a typed name and a signature block. It
identifies the system by NAME and MODEL. It never identifies the artifact by DIGEST.
Consequently a signed DoC and a signed NOUS manifest describing the same system are two
documents with no cryptographic join: nothing prevents the DoC from being read against a
different build than the one that was checked.

That gap is real and observed. Whether anyone is paying to close it is Section 6, R3.

---

## 2. PRIOR ART (live recon; primary sources where reachable)

### 2.1 eIDAS / qualified electronic signatures -- THE ONE HONEST QUESTION

The kickoff asks it plainly: does a QES-signed, timestamped DoC already do all of this?

**Substantially yes, for every part NOUS cannot do at all.**

eIDAS Art 25(2): a qualified electronic signature has the equivalent legal effect of a
handwritten signature. It is created with a QSCD, backed by a qualified certificate from a
QTSP, carries automatic cross-border recognition in all Member States, and REVERSES THE
BURDEN OF PROOF -- a challenger must establish it invalid. A qualified timestamp binds the
time with legal effect. Art 47(1) explicitly contemplates an "electronically signed" DoC.

A QES-signed DoC therefore binds:
  - the natural person to the declaration, with a statutory presumption NOUS cannot approach
  - the time, with legal effect
  - the document bytes, tamper-evidently

It does NOT bind:
  - the DIGEST of the artifact whose properties were checked

**That single residual is the entire NOUS contribution. Nothing else.** It is narrow, and
the dossier says so rather than dressing it up.

And the residual is itself attackable: a provider can TYPE the digests into the DoC text and
QES-sign it. That yields identity + time + digest with better legal force than anything NOUS
can emit. What it does not yield is a MACHINE-CHECKABLE object: no verifier can mechanically
confirm the typed digest matches a shipped artifact, and a transcription error is invisible.
Whether that survives as a moat is Section 7. It barely does.

### 2.2 SCITT -- RFC 9943 (June 2026). THE LANDSCAPE MOVED, AND THIS POST-DATES THE PRIOR.

SCITT IS NO LONGER A DRAFT. RFC 9943 (An Architecture for Trustworthy and Transparent
Digital Supply Chains, DOI 10.17487/RFC9943) and RFC 9942 (COSE Receipts) were published in
June 2026. Independently verified by the operator against the IETF announce list.

SCITT's architecture is, structurally, the object the kickoff proposes:
  - an Issuer makes a Signed Statement about an Artifact
  - the Issuer identity MUST be bound into the COSE protected header
  - the statement is correlated to the artifact by a Subject claim
  - it is registered with a Transparency Service, which returns a Receipt
  - the ledger is a linear, irrevocable history of statements made

The kickoff's non-commodity claim -- "the thing nobody does is bind the accountability
declaration to the digest of the artifact whose properties were checked, with the time bound
by a party that is not the declarer" -- describes a SCITT Signed Statement with a Receipt. It is standardized, it
is a published RFC, and the WG designed it explicitly for compliance with auditing and
regulatory requirements.

**The claim "this chain is new" is FALSE. The dossier states that plainly.**

Consequence, not fatal but decisive: **any bespoke NOUS envelope for this object is a worse
SCITT.** If it is ever built, the PAYLOAD is the contribution and the ENVELOPE is SCITT/COSE.

**CONVERGENT SEPARATION, AND A PRECISION THAT MUST NOT BE LOST.**

The formulation "a valid receipt does not prove that a claim is true; it proves that a signed
statement was registered and that the receipt verifies" appears in
draft-nobuo-scitt-hardware-iot-cloud-use-cases-00 -- an INTERNET-DRAFT that CITES RFC 9943.
IT IS NOT TEXT OF RFC 9943.

And the VOCABULARY is not ours. That draft writes "it PROVES that a signed statement was
registered." Under claims.toml that is a reserved-word violation: NOUS spends "proves" only
on the three Z3/Farkas legs and would write "evidences" there.

So the only statement any NOUS surface may make: THE SEPARATION IS CONVERGENT. An independent
standards body, facing the same problem, drew the same line between a registered signature
and the truth of what it says. THE RESERVED-WORD DISCIPLINE IS NOT SHARED, AND THE IETF HAS
NOT ENDORSED IT.

FORBIDDEN COPY: "the IETF adopted this doctrine in an RFC." It is false. It would be a
shipped overclaim, sourced to a session in which it was briefly believed.

**PROFILES: RFC 9943'S OWN EXTENSION MECHANISM, AND IT CUTS BOTH WAYS.**

SCITT is content-agnostic by design and extends via PROFILES. Evidence:
draft-ietf-scitt-receipts-ccf-profile exists, and the WG's public framing of RFC 9943 is as
a foundation others build profiles on.

CAVEAT, STATED BECAUSE IT IS NOT YET A BYTE READ: RFC 9943's normative profile text has NOT
been read. That read is REQUIRED before any claim about what a profile may specify. Nothing
in this dossier depends on it.

The inverse reading of the kill criterion is therefore real, and it is carried in Section 8
as K1b -- with its trap named, because it is attractive and it is a trap.

### 2.3 CE marking / DoC practice in existing product regulation

How does the incumbent regime bind the signatory today? IT DOES NOT, CRYPTOGRAPHICALLY.

EN ISO/IEC 17050-1 is the generic DoC standard. Machinery Regulation (EU) 2023/1230 Art 10(8)
permits a digital DoC accessible via an internet address or machine-readable code -- in
practice, a QR code pointing at a PDF. Across MDR, RED, LVD, EMC and RoHS the pattern is
uniform: a document with a name, a function, a place, a date, and a wet or digital signature.
Traceability to the product is by serial / model / type identification. Never by digest.

**The incumbent practice IS "a person signs a PDF."** The AI Act's Art 47(1)
machine-readability requirement is the anomaly, and nothing in the surveyed landscape
satisfies it in any structured way.

### 2.4 AI Act tooling already emitting a DoC

AnnexOps (annexops.com) generates Article 47 declarations of conformity from system data,
"signed, dated, and ready for submission," with documents hashed on upload, the hash stored
in its database and verified on every read, marketed as "cryptographic proof that documents
have not been altered," plus a signed evidence-package export for market surveillance.

Two observations, stated without heat:
  - A hash stored in the vendor's own database is not tamper-evidence AGAINST THE VENDOR.
    There is no independent anchor and no external time. Calling that "cryptographic proof"
    is precisely the class of overclaim the NOUS honest boundary exists to refuse.
  - It hashes the DOCUMENT. It does not bind the ARTIFACT. The join NOUS would add is absent,
    and it is absent because the tool has no proof substrate to join to.

This is the closest AI-Act-specific prior art found. It is a real competitor occupying the
space with a weaker claim. It is named, not omitted, per Article VI section 2.

### 2.5 in-toto / SLSA / C2PA

in-toto attestations bind a predicate to a subject digest. The SLSA release-VSA NOUS already
mints IS exactly this shape, and it is ALREADY SHIPPED. C2PA assertions bind claims to media,
not to a legal declarant. Neither carries a natural-person responsibility statement.

---

## 3. PATENT LANDSCAPE

HONEST UNKNOWN. No professional FTO search has been run. This is a kill-criterion gate, never
a clearance claim.

Adjacent activity found in a non-professional search, named because it is close:
  - US 11764974 and US 11075766 ("Method and system for certification and authentication of
    objects"): attestations signed by an attesting party's key, hashed, timestamped, recorded
    on a blockchain; attestations may be chained; parties and attestations may carry trust
    levels. The claim shape is signed-attestation-about-an-object + timestamp + ledger. Close
    enough that the claims must be read before any implementation.
  - The broader onchain "compliance attestation" space is crowded with signed-claim-plus-
    ledger constructions.

FTO GATE: a targeted search on "cryptographically binding a regulatory conformity declaration
to an artifact digest with independent temporal anchoring" is required before implementation.
It is NOT required to bank this dossier.

---

## 4. CLAIM CLASS

New claim class, or "sign one more thing"?

**NOT A NEW CLAIM CLASS.** It is an extension of the shipped evidence family: manifest spine
+ Ed25519 signature + RFC 3161 + Rekor anchor, with one new payload shape. Every primitive it
needs is in the tree. No new crypto, no new trust root, no new dependency, no new online
service.

Applying the Constitution's own test (Article VI section 7: if the moat is only the commodity,
the arc is a feature) and the kickoff's own test (if it is only "sign one more thing," it is
plumbing):

**THIS IS A FEATURE, NOT AN ARC.** A manifest field, an emitter, a verifier leg. Calling it an
arc would be an inflation, and the dossier refuses the inflation.

The minimal, exact claim the artifact could evidence:

> The holder of key K signed a declaration naming person P in function F, on behalf of
> provider O, assuming responsibility for the system whose canonical digests are D, and that
> declaration existed no later than time T, with T bound independently of K's holder.

Nothing in that sentence is proven. "Proves" remains reserved for the three Z3/Farkas legs
(cost-cap, policy-coverage, sequence-ordering). This artifact EVIDENCES.

---

## 5. HONEST BOUNDARY (at full strength, before any design is defended)

NOUS RUNS NO CA AND CERTIFIES NO IDENTITY. The name-to-key binding is OPERATOR-ASSERTED.
This is structural. It is not a gap to be patched.

The artifact CANNOT establish, and MUST NOT claim:

1. **That P is the holder of K.** There is no CA, no identity proof, no QTSP. A signature
   evidences that the holder of a key signed. The identity check is the auditor's out-of-band
   step, and the artifact must say so on its own face.
2. **That P had authority to bind the organisation.** Annex V point 8 requires an indication
   "for, or on behalf of whom, that person signed." NOUS can RECORD that indication. It cannot
   VERIFY it. Corporate authority is a question of company law, not of cryptography.
3. **That the declaration is TRUE** -- that the system actually conforms. A declaration is a
   speech act, not a finding. A signed false declaration is a signed false declaration.
4. **That this SATISFIES Article 47.** Article 47 requires a legal document containing the
   Annex V content, translated per Art 47(2), retained 10 years per Art 47(1). NOUS can produce
   EVIDENCE ABOUT such a declaration. It cannot BE one.
5. **That the canonical bytes are the legal instrument.** They are not and cannot be: the legal
   instrument is translated per Member State, and translation changes the bytes. The canonical
   object is a machine-readable ANNEX to the legal DoC, never a substitute. (Forced by
   finding 0(c). The kickoff did not carry this one.)

REKOR SEMANTICS, per the S216 correction, verbatim and non-negotiable: a Rekor anchor gives
public logging and ordering. IT IS NEVER TRUSTED TIME. Only the RFC 3161 token gives time. The
three temporal states (anchored-absolute / anchored / post-hoc) carry that distinction or they
are dishonest.

**If the design cannot survive stating all five at full strength on the artifact's own face, it
must not be built.** It can survive -- but only under the Section 7 reframing, which removes
NOUS from the identity business entirely instead of apologising for being in it.

---

## 6. REASONS THIS SHOULD NEVER EXIST

Written before Section 7. Argued as an adversary would.

**R1. LEGALLY HOLLOW AT THE JOIN, AND STRICTLY WEAKER THAN THE INSTRUMENT THE PROVIDER MUST
PRODUCE ANYWAY.** Art 47 obliges the provider to draw up a signed DoC. The strongest available
signature is a QES: statutory equivalence to a handwritten signature, cross-border recognition,
burden of proof reversed. A NOUS Ed25519 signature over the same content has none of that and
never can. The sketched object is therefore a LEGALLY WEAKER DUPLICATE of a document the
provider is already legally obliged to produce in a STRONGER form. Building a weaker copy of a
mandatory artifact is not a contribution. **This is the strongest kill argument and it is fatal
to the design AS SKETCHED.**

**R2. SCITT (RFC 9943) IS THIS ARCHITECTURE, STANDARDIZED, SINCE JUNE 2026.** The chain
"named declarant -> declaration -> artifact digest -> transparency anchor" is the SCITT chain:
Issuer, Signed Statement, Subject, Transparency Service, Receipt. A bespoke NOUS envelope for
the same shape is a worse SCITT with a smaller ecosystem and no interoperability.

**R3. NO FORCING FUNCTION.** No buyer. No request. No deployment. Zero users have a high-risk
AI system requiring an Annex V DoC. The cited signal -- practitioners reporting that attribution
is the record organisations miss first -- is a market observation from public discussion. IT IS
NOT DEMAND. Building an evidence surface for a system with zero deployments is manufacturing.

**R4. IT DOES NOT WIDEN THE DETERMINISM BOUNDARY.** The through-line test (project instructions
Section 2): every feature must widen the determinism boundary, sharpen the evidence, or improve
the surface across which evidence flows. Binding a person's name to a digest does not make the
system more verifiable. It makes an ADMINISTRATIVE record more traceable. That is the third leg
at best, and weakly.

**R5. THE TRANSLATION REQUIREMENT BREAKS BYTE-DETERMINISM.** Art 47(2) requires translation. A
byte-deterministic canonical declaration cannot be the translated legal document. A design that
does not confront this ships an object whose relationship to the legal instrument is unstated --
and an unstated relationship is where overclaims breed.

**R6. ARTICLE 47 MAY NEVER APPLY TO NOUS OR ITS USERS.** It is provider-side, for HIGH-RISK
systems. NOUS is a monitor and a DSL. It is not itself a high-risk AI system, and nothing forces
its users to be providers of one.

None of R1-R6 is answered by "it would be good to have."

---

## 7. COMMODITY VS MOAT, AND THE ONE REFRAMING THAT SURVIVES

Commodity, all of it already shipped in-tree: Ed25519 signing, canonical serialization, RFC 3161
timestamping, Rekor v2 anchoring, digest computation, offline verification. None of it is hard.
A competent engineer rebuilds the mechanism in a week.

The Artifact Y floor applies: schema-mandatory digest binding is the commodity floor. The idea
AS SKETCHED sits exactly ON that floor. It is another instance of digest binding.

**So the sketch fails. What survives R1, R2, R4 and R5 is a DIFFERENT OBJECT:**

> **NOUS DOES NOT SIGN THE DECLARATION. NOUS EMITS THE DECLARATION BODY.**

NOUS deterministically constructs the Annex V-shaped, machine-readable declaration BODY -- all
eight Annex V points, with the system identified BY DIGEST (Annex V point 1's "additional
unambiguous reference allowing the identification and traceability of the AI system" is exactly
where source_sha256 / ast_sha256 / the manifest digest belong) -- canonically serialized so that
a signature over it means something exact. The PROVIDER then applies whatever legal instrument
they hold, ideally a QES, over the NOUS-emitted bytes. NOUS optionally anchors the body digest
for public ordering.

What the reframing does:

  - **Dissolves R1 entirely.** NOUS never asserts an identity. The name-to-key gap is not
    patched; it is REMOVED FROM SCOPE. The artifact COMPOSES WITH the strongest available legal
    instrument instead of competing with a weaker one. The QTSP does identity. NOUS does bytes.
    Each does the thing it can actually do.
  - **Answers R4.** It improves the SURFACE across which existing evidence flows: it is the join
    that carries the Z3-checked envelope into the legal accountability record. It adds no new
    claim; it makes an existing one reachable from a document an auditor already reads.
  - **Answers R5.** The canonical body is the machine-readable annex REQUIRED BY Art 47(1),
    sitting alongside the translated human-readable DoC. It never pretends to be the legal
    instrument. Art 47(1) demands machine-readability and no format exists. That vacancy is real.
  - **Does NOT answer R2.** The correct envelope is SCITT/COSE, not a bespoke NOUS shape. If
    built: build the payload, adopt the standard envelope.
  - **Does NOT answer R3.** There is still no forcing function.

**The residual moat, stated so it can be attacked.** Not the signing. Not the anchoring. Not the
format. It is that NOUS is the only producer in the surveyed landscape that HAS a Z3/Farkas-
checked artifact to bind the declaration TO. AnnexOps hashes a PDF because it has nothing else to
hash. The declaration body is only interesting because the digest it names points at an envelope
somebody actually checked. **That is a SUBSTRATE advantage, not a MECHANISM advantage, and a
substrate advantage is the only kind that does not commoditize.**

It is also, honestly, thin: one field in a document nobody has yet asked NOUS for.

---

## 8. KILL CRITERIA (testable; a later kill is a lookup, not a debate)

Any one true -> stop or downgrade:

  **K1a.** A SCITT profile, IETF draft, or vendor implementation for an EU AI Act declaration of
    conformity appears, AUTHORED BY ANYONE ELSE. -> KILL the format work. Adopt theirs. Do not
    compete with a profile of a standard. (Check: IETF datatracker + SCITT WG mailing list,
    twice a year.)

  **K1b.** THE INVERSE READING, WHICH IS NOT A KILL AND IS NOT A LICENCE. RFC 9943 designates
    PROFILES as its sanctioned extension mechanism, so the AI Act DoC profile slot is OPEN, and
    NOUS could occupy it rather than compete with it. RECORD THIS COLDLY: that is STANDARDS work
    -- WG participation, draft authoring, review cycles, years -- not build work. It carries its
    OWN forcing-function problem and is gated on the SAME T1 (a real user who must produce a DoC).
    A profile with no implementers is a standards vanity artifact. AN OPEN SLOT IS NOT DEMAND.
    If this dossier is ever read as licensing profile work before T1 is satisfied, it has been
    misread. Recorded, not proposed.

  **K2.** The Commission adopts a delegated act under Art 47(5) (which empowers it to amend
    Annex V in light of technical progress) specifying a machine-readable DoC format. -> KILL.
    Implement the Commission's format. Do not compete with it.

  **K3.** CEN-CENELEC JTC21 publishes a harmonised standard covering DoC structure. -> As K2.

  **K4. TESTED AGAINST THE PUBLISHED PRIMARY. DID NOT FIRE.** The criterion read: the Omnibus
    final text, once in the OJ, removes the Art 47(1) machine-readability requirement OR the
    Annex V point 8 named natural person. -> The premise collapses. STOP, and retire this
    dossier to REJECTED_IDEAS.md with the recon intact.
    OUTCOME: Regulation (EU) 2026/1744 (OJ L, 2026/1744, 24.7.2026) carries NO amending
    instruction against Article 47 and NONE against Annex V. Article 1 items (1)-(43) and
    Articles 2, 3, 4 were read in full. K4 DOES NOT FIRE on this act. A LATER amending act
    reopens the criterion; this one is settled. Recorded at commit 82a32bf. The read procedure,
    and the reason the obvious grep was unsound, are preserved in Section 11 (T2).

  **K5.** A professional FTO finds a blocking patent (Section 3). -> STOP.

  **K6.** The design drifts toward Article 26(2) (deployer-side human oversight assignment).
    -> KILL IMMEDIATELY. That is the deployer's lane, not NOUS's. Article 47 is provider-side.
    This is the drift the kickoff named, and it is the correct kill.

  **K7.** Any surface, in any register, states or implies that the artifact establishes P's
    identity, P's authority, the declaration's truth, or Article 47 compliance. -> The honest
    boundary is breached. STOP AND REVERT.

---

## 9. OPPORTUNITY COST

Against the live board at bed268a:

| Item | Status at 6343689 | Ranks above this? |
|---|---|---|
| OJ publication (docs/PCE.md flip) | CLOSED by 82a32bf. Reg (EU) 2026/1744, OJ L, 24.7.2026 | -- |
| release-VSA fixed-filename defect | CLOSED by c1a3980 (the bundle now ships the filename its offline verifier reads) | -- |
| registry sidecar / published-sidecar gate | CLOSED by 207c927 + 4b237a6 | -- |
| claim_lint.py lock test | OPEN. P1: the tool is a release gate and nothing guards it | YES |
| pyflakes debt | OPEN. P2 | Roughly equal |
| THIS | Banked research | NO |

The two P1s that stood above this dossier when the Gate opened were closed by a parallel lane
mid-session. The board is now thinner than the Gate assumed -- and the verdict does not move,
because it never rested on opportunity cost. It rests on R3: THERE IS STILL NO FORCING
FUNCTION. A cleared board is not a reason to build. It is only a reason not to be blocked.

**It displaces nothing, and it should displace nothing.** A dossier costs a research session and
no tree state. An arc would cost a release window, and this does not earn one.

Constitution Article VII: do not accumulate unreleased work. Ship built arcs before starting new
ones. Nothing here becomes code until the board is clear AND a trigger fires.

---

## 10. GENERALIZATION PATH

Narrow first. General last, and only once the narrow leg is shown to be additive.

  **Leg 1 (narrow).** An Annex V body emitter: deterministic, digest-bound to an existing signed
    manifest, canonical JSON per the shipped convention (sorted-keys compact, NOT JCS),
    drop-when-None so no existing manifest changes a byte. An offline verifier leg confirming the
    declared digests match the artifact. NO SIGNING BY NOUS.
  **Leg 2 (only if Leg 1 is used).** Optional RFC 3161 + Rekor anchor of the body digest; three
    temporal states mirroring PCE, carrying the S216 Rekor-is-not-time correction verbatim.
  **Leg 3 (only if a standard exists to target).** SCITT/COSE envelope per RFC 9943, after the
    normative profile text has actually been read.

DO NOT build a general "regulatory declaration framework." The generalization (any regulation,
any annex, any digest) is the abstraction that gets built last, or never.

---

## 11. DECISION (Innovation Gate outcome)

**THE DESIGN AS SKETCHED: REJECTED.** It fails on R1 (a legally weaker duplicate of a QES-signed
DoC the provider must produce anyway) and R2 (SCITT RFC 9943 already occupies the chain the
kickoff claimed nobody does). A NOUS-signed conformity declaration naming a person is an object
that competes with a qualified electronic signature and loses.

**THE REFRAMING (Section 7): PASS -- BUILD-ELIGIBLE-DEFERRED, AND DOWNGRADED FROM ARC TO
FEATURE.** NOUS as the emitter of a canonical, digest-bound, Annex V-shaped machine-readable
declaration BODY -- with identity, legal signature and legal effect supplied by an instrument
NOUS does not own -- survives every reason it should not exist except R3.

**R3 IS UNRESOLVED: THERE IS NO FORCING FUNCTION.** No buyer, no request, no deployment. The
attribution signal is a market observation, not demand. Per Article IX that is a legitimate state
and the honest one. It is BANKED, NOT BUILT.

**REVISIT TRIGGERS (specific, testable; ALL THREE required):**

  **T1.** A real user or deployment exists that MUST produce an Annex V DoC for a NOUS-governed
    system. Not "would benefit from." MUST PRODUCE.

  **T2. EXECUTED AGAINST THE PUBLISHED PRIMARY. SATISFIED.** The trigger read: Art 47(1)'s
    machine-readability requirement survives the Omnibus in the PUBLISHED OJ text, verified
    against the L-series entry, not a secondary source.
    OUTCOME: Regulation (EU) 2026/1744, OJ L, 2026/1744, 24.7.2026, CELEX 32026R1744. Article 1
    items (1)-(43) and Articles 2, 3, 4 read in full. NO amending instruction against Article 47,
    NONE against Annex V. Both survive intact. T2 IS SATISFIED. Recorded at commit 82a32bf.
    THAT CLOSES ONE TRIGGER OF THREE, WHICH IS A TEST, NOT A BUILD DECISION. T1 IS UNSATISFIED
    -- there is still no forcing function (Section 6, R3) -- and the feature REMAINS BANKED.
    Reading this section as a promotion to build is a misreading; ALL THREE are required.

  > **THE PROCEDURE BELOW IS EXECUTED. IT IS PRESERVED FOR ITS REASONING, NOT FOR RE-RUNNING.**
  > It records why the obvious grep would have produced a FALSE KILL, and that lesson generalises
  > to the next amending act. Do not re-run it against 2026/1744.
  >
  > **T2 AND K4 ARE THE SAME READ, AND IT IS FREE.** The OJ flip session is already scheduled and
  > already opens the published text. Add one pass over that same document.
  >
  > **THE OBVIOUS TEST IS UNSOUND. IT FAILS TOWARD A FALSE KILL. DO NOT RUN IT.**
  > The obvious test reads: does Art 47(1) still say "written machine readable"? does Annex V
  > point 8 still require "the name and function of the person who signed"? Either absent -> K4
  > fires. That test is wrong for two independent reasons, and BOTH POINT THE SAME WAY -- toward
  > retiring a correct dossier on a measurement error rather than on the law.
  >
  >   (a) THE OMNIBUS IS AN AMENDING REGULATION. Its published text carries only the AMENDMENTS.
  >       It does NOT restate Article 47(1) or Annex V point 8 unless it CHANGES them. The phrase
  >       is therefore ABSENT FROM THE OJ TEXT PRECISELY WHEN ART 47(1) IS UNTOUCHED -- which is
  >       the case in which T2 should CLOSE. ABSENCE IN AN AMENDING ACT MEANS UNCHANGED. The
  >       obvious test reads it as REMOVED. The routing is inverted.
  >
  >   (b) FG-S239-A. A line-oriented grep cannot see a phrase that WRAPS. "written machine
  >       readable" is multi-word; in OJ HTML it is split by markup and line breaks. It can
  >       grep-MISS even in the branch where it is PRESENT.
  >
  > **THE SOUND TEST.** Do not ask what Article 47(1) SAYS. Ask whether the Omnibus TOUCHES it.
  > Single tokens only -- a word cannot be split by a line wrap:
  >
  >       Article 47 | Annex V | point 8 | machine | readable | signed | declaration
  >
  > ROUTING:
  >   - NO amending instruction against Article 47 or Annex V -> they SURVIVE INTACT -> T2 CLOSED.
  >     SILENCE IS SURVIVAL, NOT DEATH.
  >   - AN amending instruction against Article 47 or Annex V appears -> READ IT IN FULL and
  >     adjudicate against the actual instruction. ONLY THEN can K4 fire.
  >
  > Section 13's recon recorded "no reported amendment to Art 47 or Annex V" from SECONDARY
  > sources. The published L-series entry is PRIMARY. If the primary contradicts the secondary,
  > the primary wins and K4 is live.
  >
  > Zero marginal cost: one read of a document that session opens anyway. DO NOT schedule a
  > separate session for it. It rides the flip.

  **T3.** No SCITT profile, delegated act, or harmonised standard has occupied the format
    (K1a, K2, K3 all still false).

**THIS IS NOT A REJECTED_IDEAS.md ENTRY.** That ledger is DO-NOT-BUILD only, and the reframed
object is build-eligible. Filing it there would mix the two registers, which is the one thing that
ledger forbids. It lives here, and in the handoff's banked-frontier section, alongside the composed
multi-agent envelope arc and the closure attestation.

---

## 12. FORBIDDEN INTERPRETATIONS (machine-readable; same register as the GLM manifest block)

```json
{
  "artifact": "conformity_declaration_body",
  "status": "design_only_not_implemented",
  "evidences": [
    "the holder of key K signed a body naming person P in function F on behalf of provider O",
    "the body names canonical artifact digests D",
    "the body existed no later than time T (RFC 3161 token only; a Rekor anchor gives public logging and ordering, never trusted time)"
  ],
  "forbidden_interpretations": [
    "that person P is the holder of key K (NOUS runs no CA and certifies no identity; the name-to-key binding is operator-asserted)",
    "that person P had authority to bind provider O (a question of company law, not of cryptography)",
    "that the declaration is true, i.e. that the system conforms (a declaration is a speech act, not a finding)",
    "that this artifact satisfies Article 47 of Regulation (EU) 2024/1689 (Article 47 requires a legal document with Annex V content, translated per Art 47(2) and retained 10 years; NOUS produces evidence ABOUT such a declaration, it does not BE one)",
    "that the canonical bytes are the legal instrument (the legal instrument is translated per Member State; translation changes the bytes; this body is a machine-readable annex, never a substitute)",
    "that the IETF has endorsed the NOUS reserved-word discipline (RFC 9943 and the SCITT drafts reach a convergent SEPARATION between a registered signature and the truth of what it says; they do NOT share the vocabulary, and SCITT spends 'proves' on registration)"
  ],
  "proves": [],
  "note": "The reserved word 'proves' applies in NOUS only to the three declared proof legs: cost-cap, policy-coverage, sequence-ordering. This artifact proves nothing."
}
```

---

## 13. RECON TRAIL (reproducible)

**Primary text.** Regulation (EU) 2024/1689 Art 47(1)-(5) and Annex V points 1-8, via
ai-act-service-desk.ec.europa.eu (European Commission) and three independent reproductions of the
OJ text of 13 June 2024.

**Landscape.**
  - eIDAS, Regulation (EU) No 910/2014, Art 25(1)-(2); the QES / QTSP / QSCD chain; eIDAS 2.0
    EUDI wallet timeline.
  - IETF SCITT: RFC 9943 (architecture, June 2026, DOI 10.17487/RFC9943), RFC 9942 (COSE Receipts,
    June 2026); draft-ietf-scitt-scrapi-10; draft-ietf-scitt-receipts-ccf-profile;
    draft-fassbender-scitt-time-anchor-01; draft-nobuo-scitt-hardware-iot-cloud-use-cases-00.
    RFC 9943 normative profile text NOT YET READ -- see the caveat in Section 2.2.
  - Machinery Regulation (EU) 2023/1230 Art 10(8) digital DoC; EN ISO/IEC 17050-1; CE-marking DoC
    practice across MDR / RED / LVD / EMC / RoHS.
  - AnnexOps (annexops.com): AI Act Article 47 DoC generator; document-hash-in-vendor-database
    integrity model.
  - in-toto / SLSA provenance (already shipped in-tree as the release-VSA); C2PA assertions.

**Patents** (non-professional, kill-gate only, NOT a clearance): US 11764974, US 11075766 --
signed attestation about an object + timestamp + ledger.

**Omnibus status, CLOSED: published as Regulation (EU) 2026/1744, OJ L, 2026/1744,
24.7.2026, CELEX 32026R1744.** Signed 8 July 2026, Strasbourg. Entry into force 27 July 2026;
Article 4 states the third day following publication, and the date is written verbatim four
times in the enacting text (see Section 0). Council adopted 29 Jun 2026, Parliament 16 Jun
2026. The 2026-07-13 secondary-source recon was CONFIRMED by a primary byte-read of the
enacting text at commit 82a32bf, on BOTH counts: no amending instruction against Article 47 and
none against Annex V; and Annex VIII section B points 7 and 9 ARE deleted, by Article 1(42).
