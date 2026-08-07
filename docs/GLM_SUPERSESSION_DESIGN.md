# GLM Supersession -- Innovation Gate (S304)

Status: DRAFT for operator decision (S304). No code precedes this gate. The
decision recorded here is whether to build, not how to build. ASCII-only.

Scope: the correction path for the served, signed Governance Layer Manifest
at `website/.well-known/governance-layer-manifest.json`.

Cross-references: `docs/adr/ADR-0011-supersedes-commits-to-published-bytes.md`
(the decided invariant), `docs/ENVELOPE_BINDING_DESIGN.md` (S119, the internal
chain that already implements this shape), `docs/adr/ADR-0010-...md` (the
evidence layer monitors, the runtime policy engine gates),
`docs/ENGINEERING_CONSTITUTION.md` (this gate's required sections, read in
full at S304).

================================================================
0. Substrate: live bytes read at S304, HEAD c985e73
================================================================

Everything in this section was measured this session. Nothing is inherited.

THE PUBLISHED CHAIN IS INTACT TODAY. Fetched from the origin over TLS:
the served manifest is 10673 bytes, sha256 3a0c10c5; the served predecessor
at the `supersedes` URL is 10250 bytes, sha256 2081c61a. The canonical
digest recomputed over the FETCHED predecessor bytes is c72fb0eb, which
equals the `supersedes_digest` carried in the served successor. The
positive arm of that comparison printed False in the same run, so the
comparison was capable of a different answer. Three copies of the archive
-- fetched, tracked mirror, and `/var/www` -- are byte-identical.

THE DEFECT IS THEREFORE DORMANT, NOT ACTIVE. It activates on the first
correction, never before.

THE CONFLATION IS FORCED BY A GUARD, NOT LEFT BY OMISSION. In
`scripts/sign_glm_manifest.py` (e8de230f), `cmd_build` reads the source
text at :198, parses it at :199, then calls `_check_source_is_sealed(
source, source_text)` at :202. That guard recomputes the source's own
canonical digest and refuses at :105-110 when it differs from the declared
value, with the message that the supersedes chain would otherwise carry a
false digest. An edited draft must therefore be resealed to pass, and resealing
writes the new digest into `manifest_digest.value`. `_transform_source`
then reads that same field at :136 and writes it as `supersedes_digest` at
:163. The guard that exists to prevent a false link is the mechanism that
guarantees a false link the moment a claim is corrected.

THE TOOL ALREADY RECORDS ITS OWN GAP. The docstring at :88-90 states that
the verifier which exists does not check `supersedes_digest` at all.

THE TWO HALVES OF THE LINK HAVE INDEPENDENT ORIGINS. `--supersedes-url` is
required at :369, and is never read back, never fetched, and never compared
with `--source`. No code relates the URL to the digest.

G4 FORBIDS EQUALITY, NOT REGRESSION. `_check_version_advances` (:113-123)
raises only when the new version string equals `owner.version` (:119). A
successor numbered BELOW its predecessor is accepted. Separately, the
version values are strings ("5.49.0", "5.37.0"): lexicographic comparison
happens to order these correctly and would misorder "5.9.0" against
"5.49.0". Any ordering predicate needs a parsed tuple, not a string
compare.

THE GENESIS CASE EXISTS AND IS SHAPED DIFFERENTLY. The archived 5.37.0
manifest carries the keys `supersedes` and `supersedes_digest` PRESENT with
null values, while the drop-when-None rule elsewhere omits absent fields
(the same file carries no `manifest_signature.public_key` at all). A chain
verifier must treat null-valued link fields as a chain root, not as an
error.

THE VERIFIER CANNOT HOST THE CHECK. `verify_glm_manifest` (glm_manifest.py
92fb4ea1, :175-181) takes a `served_text` and has no network parameter.
`canonical_glm_bytes` (:80-89) substitutes exactly two self-referential
values, so `supersedes_digest` sits inside the hashed bytes: it is covered
by the digest and by the Ed25519 signature over it, and compared with
nothing. `GlmVerifyDetail.ok` (:170-172) is `digest_ok and signature_ok`;
`anchor_ok` is excluded, and a suite test pins that exclusion.

PLACEMENT FACTS. `claims.toml` (f9919834) sets `surfaces.include` to
`*.py`, `*.md`, `*.html`; `exclude_dirs` does NOT contain `scripts`; and
`exclude_globs` contains `verify_*_offline.py`, so a tool named to match
that glob would leave the linter silently. `pyproject.toml` `py-modules`
lists top-level modules only -- none of the 20 tracked `scripts/` files
appear, including `sign_glm_manifest.py` itself -- so the dual-registration
rule does not apply to a script placed there. 14 of 616 tracked `*.py`
files already import `urllib` or `requests`, `sign_glm_manifest.py` among
them; network in a script is established practice, not a new dependency
shape.

================================================================
1. Problem statement
================================================================

The GLM is a signed, served, publicly fetchable declaration of what the
NOUS governance layer does and does not do. One of its entries is known to
be wrong: `operational_scope.does_not` index 5, "Enforce, authorize, halt,
or intervene in execution", is stated bare, while indices 0 through 4 each
carry their own scoping clause. Per ADR-0010 the evidence layer monitors
and the runtime policy engine gates, so the entry as written understates
the system. The defect class is an UNSCOPED statement, not a false one, and
it is the same class already corrected twice elsewhere (S265 and S296).

There is today no path by which that entry can be corrected without
producing a successor whose `supersedes_digest` names the edited draft
rather than the bytes actually published. ADR-0011 forbids exactly that.

So the problem is not "the chain is broken". The chain is intact. The
problem is that the only available correction procedure violates a decided
invariant, and nothing in the tree would detect the violation if it
shipped.

================================================================
2. Prior art
================================================================

INTERNAL, AND IT IS THE STRONGEST ENTRY. NOUS solved this problem at S119
and S120 for a different artifact. `docs/ENVELOPE_BINDING_DESIGN.md`
(678acd83, 421 lines, Status: DESIGN FROZEN S119) specifies at 5.1 a
`prior_digest` field holding the sha256 of the predecessor's canonical
body bytes, at 5.2 the presence of that field as the genesis discriminator,
and at 5.4 six fail-closed conditions for an offline chain-walk: bad
signature, missing link, altered link, non-termination at genesis, no-op
re-binding, and cycle or multiple genesis.

It shipped. `prior_digest` occurs in 15 tracked files including
`manifest.py`, `envelope.py`, `cli_verify.py` and five test files.
`resolve_prior_digest` (cli_verify.py:683-733, marker
`__s119_supersedes_producer_v1__`) takes the predecessor as a SEPARATE
path argument, verifies the predecessor's own Ed25519 signature and
refuses to chain onto a non-authentic one (:712-719), refuses a no-op
re-binding when no sha-bearing field moved (:724-730), and returns
`sha256(prior_manifest.canonical_bytes())` -- the digest of the
predecessor's OWN bytes (:731-733). Eight tests cover it; one production
caller at :525.

Its docstring at :690-693 states the architectural split precisely: this is
issuance admission control, NOT the trust boundary, and the offline
verifier enforces the same rule with zero issuer trust.

That is ADR-0011 constraint 1, implemented and tested 185 sessions before
the ADR named it a decision. The GLM ceremony never received it.

ONE INTERNAL RULE DOES NOT TRANSFER, AND THE REASON IS NAMED. Section 5.3
of the S119 freeze rejects a digest-only link (option b) in favour of
carrying the predecessor's bytes (option a), on the ground that without
those bytes a verifier must trust that the issuer enforced movement at
issuance. The GLM case differs: the predecessor is published at a stable
URL and the verifier fetches it itself, so fetch-and-compare does not
require issuer trust. The rejection of option (b) does not carry over.

ONE INTERNAL DECISION MUST BE REOPENED EXPLICITLY. Section 7 of the same
freeze places GLM `supersedes_digest` interoperability OUT OF SCOPE,
calling it an external, still-evolving schema not coupled to the internal
chain. That exclusion was honoured: neither
`docs/CHAIN_BUNDLE_COMPOSITION_DESIGN.md` nor
`docs/MATERIALITY_CLASSIFICATION.md` mentions the GLM at all. The exclusion
is weaker in 2026 than in the session that wrote it, because the GLM is
NOUS's own published artifact rather than a third party's schema, but
reopening a freeze is a decision and is recorded here as one.

EXTERNAL. Two individual Internet-Drafts derive the same rule
independently. Neither is endorsed by the IETF and neither has formal
standing; both expire in January 2027.

  draft-nobuo-scitt-protected-object-binding-00 (Aoki, SOKENDAI, 7 July
  2026) defines at section 9 a Statement Reference and states normatively
  that a verifier must not trust a URI by itself and that when a digest is
  present the retrieved statement must match it. Section 12 defines the
  relation names `supersedes` and `revokes`; section 14 names a
  supersession statement as a statement about a statement; section 11
  requires a policy stating which issuers may assert which relations, and
  holds that a valid signature alone confers no such authority; section 20
  names the risks unauthorized revocation, stale graph, omitted conflict,
  and ambiguous encoding; section 16 leaves the graph digest algorithm
  undefined and advises against cross-implementation digest comparison
  until it is.

  draft-mih-sokolov-scitt-payload-binding-01 (27 July 2026) holds at
  section 11.4 that a content URL which is not content-addressed is not
  evidence, and at section 7 that bare hexadecimal equality is not a join;
  its section 10 names record relations and defers them to a companion
  document. S303 recorded that no such companion existed. The Aoki draft,
  filed twenty days earlier by a different author, occupies that space.
  That correction is entered here.

  TUF supplies the missing ordering predicate. Its client workflow makes
  the rollback check normative -- the trusted version must be less than or
  equal to the new version, and on failure the client discards the file,
  aborts the cycle, and reports -- and names the converse fast-forward
  attack, where version numbers are inflated far beyond the current value.
  NOUS G4 implements neither direction.

  C2PA is the only widely deployed correction pattern. An update manifest
  adds or redacts an assertion without deleting the predecessor, which
  becomes an ingredient reference bound to its bytes. Redaction lives in a
  secondary claim. Same shape as ADR-0011 constraint 2.

  W3C Bitstring Status List publishes suspension or revocation status for a
  credential. It can say a document is no longer current. It cannot say
  what the corrected statement is, nor bind that correction to the bytes it
  replaces. Recorded as considered and not adopted.

  sigstore/model-transparency was measured at S303 under the standing
  obligation at REJECTED_IDEAS.md:157-163: it signs a manifest of (path,
  digest) subjects in in-toto plus DSSE plus a Sigstore bundle and carries
  no predecessor or successor relation at all. RFC 9943 section 9.2 allows
  a later Signed Statement from the same Issuer for the same subject and
  establishes only that the Issuer produced it.

================================================================
3. Patent landscape
================================================================

UNKNOWN. One keyword scan was run at S304 and returned only adjacent art:
a ledger-based attestation revocation family that revokes by spending
cryptocurrency associated with the attestation transaction (US 10333706,
10361849, 10558974, 11743038, 12126715), and an attestation-manifest
derivation patent covering re-attestation after a software update
(US 11327735, Intel). Neither reads on a supersession link that commits to
published bytes.

A single keyword scan is not a clearance and this project has no patent
counsel. Freedom to operate is NOT established. Per the Constitution, never
assume it. This section stays UNKNOWN until a professional search is
commissioned, and that cost belongs in section 9.

================================================================
4. Claim class
================================================================

The claim is NOT "NOUS invented supersession binding". Three independent
parties -- NOUS at S119, Aoki, and Mih and Sokolov -- state the same rule.
The rule is commodity and this document says so.

The claim is narrower and factual: a governance self-declaration published
by its subject can be corrected without the correction silently
recharacterising what was previously published, because each successor
commits by digest to the predecessor's served bytes and a third party can
check that commitment from the public web with a standard runtime.

Nothing here is claimed under the reserved word, which stays bound to Z3
and Farkas results. This mechanism evidences the
integrity of a link; it evidences nothing about the truth of any statement
inside either manifest.

================================================================
5. Honest boundary
================================================================

WHAT IS EVIDENCED. That the bytes served at the `supersedes` URL hash to
the value carried in the successor. That the successor's own digest matches
its served bytes. That both carry an Ed25519 signature from the pinned
operator key. That the successor's version does not regress. That at least
one non-ceremonial field moved.

WHAT IS NOT CLAIMED. That any statement inside either manifest is true.
That the operator is honest. That the published predecessor is the only
document ever served at that URL -- the check is point-in-time and a
transparency anchor, not this mechanism, bounds when the bytes existed.
That the correction is complete or that no further error remains.

THE STRUCTURAL LIMIT, STATED PLAINLY. The GLM has one issuer, one signing
key, and one subject, and they are the same party. NOUS supersedes its own
statements with its own key. The Aoki draft's section 11 requirement -- a
policy stating which issuers may assert which relations -- is degenerate
here. This mechanism raises the cost of an undetected silent edit; it does
not make the operator trustworthy, and no surface may imply otherwise.

MEASUREMENT LIMIT. The S304 fetch resolved to 127.0.0.1 and therefore
measured the origin. Whether the CDN edge serves identical bytes to the
public was not measured.

================================================================
6. Reasons this should never exist
================================================================

Written before the acceptance argument, per the Constitution.

1. NOTHING IS BROKEN. Measured this session: the link is intact over
   fetched bytes, all three archive copies agree. Building correction
   machinery for a defect that has never fired is speculative work, and
   the Constitution's plateau discipline exists for exactly this.

2. THERE IS NO MOAT. The rule has been derived independently three times,
   once inside this very repository. A world-class competitor reproduces
   it in an afternoon. Section 7 of the Constitution warns that the moat
   is never "we use signatures".

3. A CONTRACT CHANGE ON A SIGNING PATH IS THE HIGHEST-RISK CATEGORY IN
   THE TREE. Any shape satisfying ADR-0011 constraint 1 turns two tests in
   test_s297_glm_ceremony.py red by design -- reported at S303 as :69-81
   and :113-126, INHERITED and not re-measured at S304. Red tests on a
   ceremony that holds the operator signing key is where a mistake costs
   the most.

4. AN S119 FREEZE ALREADY EXCLUDED THIS. Section 7 put GLM interop out of
   scope deliberately, and the exclusion was honoured across two
   subsequent design documents. "We noticed it again" is a weak reason to
   reopen a freeze.

5. A CHEAPER ALTERNATIVE EXISTS AND NEEDS NO CODE AT ALL. Never correct a
   GLM. Publish the next version with the entry stated correctly from the
   start, let the predecessor stand as a historical record, and note the
   change in prose. The existing ceremony already handles that case
   correctly, because a routine version bump reseals intact bytes and the
   conflation is invisible when nothing was edited. This alternative
   costs zero engineering time and zero risk, and it must be defeated
   before anything is built.

   WHY IT DOES NOT FULLY WIN. It works only while no correction is ever
   needed mid-version, and it leaves ADR-0011 as a decided invariant that
   nothing enforces. But it is a genuine option and it is cheaper than
   what follows.

6. THE VERIFIER REQUIRES NETWORK, in a project whose verification
   discipline is offline and dossier-embedded. That is a real tension,
   not a formality.

================================================================
7. Commodity vs moat
================================================================

COMMODITY -- everything easily reproduced: the digest comparison, the
fetch, the Ed25519 check, the version ordering predicate, the field shape.
All of it published, some of it normative in drafts, one implementation
already in this repo.

NOT COMMODITY -- and stated modestly, because it is small: that a published
governance self-declaration is subject to the same admission control the
project already applies to its build manifests, so a party who has never
met the operator can check the correction history of the operator's own
claims from the public web. The composition is the asset; no single part
of it is.

WHAT A COMPETITOR CANNOT COPY IN SIX MONTHS is not this mechanism. It is
the accumulated record of claims withdrawn on evidence. This gate should
not pretend otherwise.

================================================================
8. Kill criteria, assessed one by one
================================================================

The seven named criteria at ENGINEERING_CONSTITUTION.md:86-89.

PRIOR ART ALREADY EXISTS -- FIRES ON THE RULE, NOT ON THE ARTIFACT. Three
independent derivations. No new rule may be claimed. It does not fire on
the mechanism: no shipped tool checks a GLM supersedes link, the Aoki
draft is an information model with provisional CDDL and an undefined graph
digest, and `resolve_prior_digest` is bound to the frozen `Manifest` class
and cannot be called on a GLM dict. What transfers is the SHAPE, not the
code. If the operator reads this criterion as firing outright, the arc
stops here and alternative 5 in section 6 is taken instead.

A PATENT BLOCKS -- UNKNOWN. See section 3. Not cleared.

THE HONEST BOUNDARY CANNOT BE MAINTAINED -- DOES NOT FIRE, conditionally.
Section 5 states the boundary, including the degenerate single-issuer
case. If any surface begins to imply the mechanism makes the operator
trustworthy, this criterion fires retroactively.

IT REQUIRES OVERCLAIM -- DOES NOT FIRE. The reserved word is not used of
this mechanism anywhere in this document.

OFFLINE VERIFICATION IMPOSSIBLE -- PARTIALLY FIRES, AND THE MITIGATION IS
STRUCTURAL. Fetching a predecessor needs network. The mitigation is that
the core predicate takes BYTES, and fetching is a thin wrapper: the check
is then hermetically testable in the suite and usable offline against
supplied bytes. If a proposed shape puts the network call inside the
predicate, this criterion fires.

DETERMINISTIC REPLAY IMPOSSIBLE -- DOES NOT FIRE. Given the same two byte
strings the verdict is a pure function.

THE AUDITOR MUST TRUST THE OPERATOR -- TENSION, NOT A CLEAN PASS. The
mechanism reduces what must be taken on trust without eliminating it. This
is the criterion to revisit if the design drifts.

================================================================
9. Opportunity cost
================================================================

WHAT IS NOT BUILT IF THIS IS. Gate 4(b) itself remains blocked while this
is designed, and the DN[5] entry stays served in its unscoped form for
however long that takes. The three silent policy-failure paths
(FG-S299-A), the primary-read gate on Annex XIV and the Article 50
Guidelines, and the standing `scripts/release.py` F1 finding all wait.

MAINTENANCE COST. A new checker on a signing path is code that must stay
correct across every future ceremony change. Two S297 tests must be
rewritten, and rewriting a test that guards a signing path is itself a
reviewable event.

RESEARCH COST NOT YET SPENT. A professional patent search, if section 3 is
to stop saying UNKNOWN.

COST IF NOT BUILT. The next correction to any published GLM claim ships a
link that names a document nobody published, and no instrument in the tree
reports it.

================================================================
10. Generalization path
================================================================

NARROW FIRST. One artifact family: the GLM and its archive. One relation:
supersedes. No graph, no manifest of manifests, no relation vocabulary
beyond the single link that already exists in the served bytes.

DO NOT GENERALIZE UNTIL. At least one real correction has been published
and verified end to end by a party who is not the operator.

ONLY THEN CONSIDER. Adopting the Aoki typed statement-reference shape in
place of the bare URL plus bare hex, which would change the canonical bytes
and therefore the digest and the signature for every future manifest;
aligning with a relation vocabulary if one of these drafts acquires
standing; a chain-walk beyond the immediate predecessor. None of these is
authorised by this gate.

NOTE FOR ANY FUTURE ALIGNMENT. ADR-0007 chose sorted-keys compact JSON and
not JCS, while the CPB draft registers jcs-n. NOUS sits in its own digest
context by an existing decision, and section 7.1 of that draft holds that
digests are comparable only within the same context.

================================================================
11. Security first
================================================================

The six elements required at ENGINEERING_CONSTITUTION.md:62-66.

ATTACK SURFACE. An outbound HTTPS fetch of an attacker-influenceable URL
taken from inside a signed document; the bytes returned; the local file
paths passed to the tool; the operator signing key, which the checker must
never touch.

ABUSE CASES. A `supersedes` URL pointed at an attacker-controlled host, so
the tool fetches arbitrary content -- the digest comparison contains this,
since unexpected bytes fail. A URL pointed at an internal address, making
the tool an SSRF probe: the URL comes from a signed document written by the
operator, which bounds but does not eliminate it. A very large response
exhausting memory: needs a size cap. A predecessor that is itself a valid
signed manifest but not the one named: caught by digest. A version pinned
downward: caught only if the ordering predicate is built, and today it is
not.

FAILURE MODES. Network unavailable, which must be reported as UNKNOWN and
never as PASS -- fail-closed means a fetch failure is not a green result.
The CDN serving different bytes than the origin. A redirect chain ending
somewhere unintended. Both manifests fetched at different instants, so the
pair is not a snapshot.

TRUST ASSUMPTIONS. TLS to the origin; the pinned operator public key; that
the archive URL is immutable in practice, which is asserted by the operator
and by the blog surface at website/blog/index.html:1176 and is enforced by
nothing.

BLAST RADIUS. A read-only checker touches no signed byte, no served byte,
no key, and no Rekor submission, and turns no existing suite lock red. A
ceremony change touches the signing path and turns two S297 tests red by
design. These are different risk classes and should not travel in one
gate.

ROLLBACK STRATEGY. For the checker: delete the file and its tests, revert
one commit; nothing published depends on it. For a ceremony change: there
is no rollback once a manifest is signed, served, and anchored. That
asymmetry is itself an argument for ordering.

================================================================
12. What this gate does NOT authorise
================================================================

No code. No edit to `scripts/sign_glm_manifest.py`. No new GLM version. No
signing, no serving, no Rekor submission. No correction of DN[5]. No change
to any test. No reopening of AXIS 0, D1, D2, or any closed item.

The single output of this gate is the operator's decision on section 8's
first criterion: does prior art kill this arc, or does the shape transfer?

================================================================
13. Open questions carried into the decision, not resolved here
================================================================

  - Must DN[5] be corrected in the NEXT successor, or may it ride a later
    version? Asked at S302, S303, and S304. Unanswered. The S304
    measurement changes its terms: the chain is intact, so nothing is
    urgent, but the correction remains impossible to make compliantly
    until this arc lands.
  - Does a corrected GLM require the version to advance, or may a
    correction be issued at the same version with a different digest? G4
    forbids version equality, which forces a bump, which conflates
    "corrected" with "changed".
  - What counts as a material change for a GLM? The S119 rule keys on
    sha-bearing build fields, which have no GLM analogue. The ceremony
    writes exactly seven fields; the other fifteen top-level keys,
    `operational_scope` among them, are the candidate set.
  - Does the CDN edge serve the same bytes as the origin? Unmeasured.
  - Which two of the twelve `docs/*_DESIGN.md` files carry no Status line
    in their first six lines? Measured as ten of twelve at S304; the two
    were not identified.

================================================================
14. Evidence ledger (append-only)
================================================================

Entries are appended, never edited. A correction to this document is an
entry here, not a rewrite above, per ADR-0011 constraint 2 applied to the
document itself.

  - S304, AFTER THIS DOCUMENT WAS COMMITTED AT 9b3e055. Every inherited
    citation above was checked against bytes in the same session.
    ADR-0011's two constraints read as cited, at :59-62 and :64-68.
    tests/test_s297_glm_ceremony.py:77 asserts the transformed
    supersedes_digest equals the source digest constant, and :114-115
    states that the predecessor digest it reads is never one of the
    fields it writes: both as cited, so the INHERITED label in section 6
    is discharged. ADR-0007 states plain sorted-keys compact JSON and not
    JCS at :1, :17 and :19. docs/REJECTED_IDEAS.md:157-163 carries the
    standing prior-art obligation naming sigstore/model-transparency. No
    citation in this document was falsified.

  - S304. THE LAST OPEN QUESTION IN SECTION 13 IS CLOSED. The two
    docs/*_DESIGN.md files carrying no Status line in their first six
    lines are COUNTERPARTY_WITNESSED_CONTINUITY_DESIGN.md and
    ENVELOPE_BINDING_DESIGN.md. The second is the load-bearing internal
    prior art of section 2. With this file the census is thirteen files,
    eleven with a Status line -- not twelve of twelve as previously
    recorded.

  - S304. SECTION 2 OVERSTATES ONE TRANSFER, AND THE OVERSTATEMENT IS
    NAMED HERE RATHER THAN EDITED ABOVE. Section 2 presents the
    sha-movement requirement of resolve_prior_digest
    (cli_verify.py:724-730) as part of the structure that carries over to
    the GLM. ADR-0011:113-117 describes the missing artifact as a
    comparison of supersedes_digest against fetched predecessor bytes,
    admitting a null link for the root, and states no movement
    requirement at all. The S119 rule exists because a no-op re-binding
    is suspect in a build chain; for a correction to published text the
    correction is itself the change, and a movement check over fields the
    ceremony rewrites unconditionally (generated_at, owner.version,
    canonicalization_method) would pass vacuously. Section 13 already
    carries "what counts as a material change for a GLM" as open; that
    framing is correct and section 2's is too confident. The conclusion
    of section 2 stands -- the shape transfers -- while one named element
    of it does not.

  - S304. ADR-0011:113-117 ALREADY SPECIFIES THE ARTIFACT THIS GATE RANKS
    FIRST, including the null-link requirement for the archive root, and
    already records at :141-148 that test_s297:167-174 checks the shape of
    supersedes_digest without fetching or comparing. This document and
    that record do not conflict; this document adds the cost, the prior
    art, and the rejection argument that the record does not carry.

  - S305. THE OPERATOR'S DECISION ON SECTION 8, RECORDED AS D305-1. The
    first kill criterion, "prior art already exists", FIRES ON THE RULE
    AND NOT ON THE ARTIFACT. The rule is settled and no new rule may be
    claimed here. Nothing installable exists: the Aoki draft is an
    information model whose graph digest algorithm is left undefined at
    its section 16; the CPB draft defers record relations to that
    companion; a C2PA update manifest is a different format; and
    sigstore/model-transparency carries no successor relation at all.
    The project's own resolve_prior_digest does not transfer either --
    it consumes a frozen Manifest and returns sha256 over
    prior_manifest.canonical_bytes() (cli_verify.py:731-733, INHERITED
    from the S304 reading), while a GLM is a plain dict digested by
    canonical_glm_bytes. No one can adopt someone else's. The arc
    therefore does NOT close as a rejected idea, and alternative 5 of
    section 6 is NOT taken.

  - S305. THE ARC IS SPLIT BY RISK CLASS AND ONLY ONE HALF IS
    AUTHORISED. (a) THE CHAIN CHECKER IS APPROVED, NARROWLY: read-only,
    no signed byte, no served byte, and it must redden none of the three
    suite locks. It is not a new idea -- it is the implementation of an
    invariant already decided and already recorded as a consequence at
    ADR-0011:113-117, and its hand-run form ran as leg L18 of the
    session supplement on 2026-08-06 (link intact over fetched bytes,
    positive arm False in the same run). (b) THE CEREMONY CHANGE IS NOT
    AUTHORISED. A contract change on a signing path is the highest-risk
    category this gate names at its section 6, and the change reddens
    two S297 tests by design. It is NOT deferred until (a) lands: it
    waits until a real correction to published text is owed, and the
    chain is intact over fetched bytes, so nothing presses. NAMING (b)
    AS THE NEXT STEP BECAUSE (a) CLOSED WOULD BE THE FG-S304-D ERROR
    CLASS AND IS REFUSED IN ADVANCE. SEQUENCE: this ledger entry first,
    the tool afterwards, in separate gates.

  - S305. BOUNDS ON (a), EACH PREVIOUSLY MEASURED, RESTATED HERE AS THE
    DECISION'S OWN TERMS. The core predicate takes BYTES and the fetch
    is a thin wrapper around it, or the offline-verification kill
    criterion of section 8 fires. The TUF rollback predicate needs a
    PARSED version tuple: owner.version values are strings, and "5.9.0"
    against "5.49.0" breaks lexicographic order. A null-valued
    supersedes link is the root of the chain and not an error -- the
    archived 5.37.0 manifest carries both keys present with null
    values. The tool must not be named verify_*_offline.py, which
    claims.toml excludes by glob and which would drop it out of the
    linter silently. Rule 9 dual-registration does not apply under
    scripts/. The new claim_lint scanned-file count is predicted before
    the linter runs, not read off it afterwards. NOT AUTHORISED BY THIS
    DECISION: any edit to sign_glm_manifest.py, a new GLM version, a
    signature, a serving step, a Rekor submission, the DN[5]
    correction, or a change to any test. Section 12 stands unchanged
    and this entry does not widen it.

  - S306. THE CEREMONY'S SUPERSESSION BEHAVIOUR WAS EXECUTED, NOT READ.
    _transform_source and the two guards were imported from
    scripts/sign_glm_manifest.py at a76b5d4 and run against the served
    manifest bytes on 2026-08-06. No key was loaded, seal_glm_manifest was
    never called, and nothing was written: porcelain and both file digests
    were identical before and after the run. The records above cite line
    numbers; this entry cites executions.

    THE GUARD FIRES ON AN EDITED DRAFT. _check_source_is_sealed accepted
    the served bytes unchanged and refused them after a single-token edit
    to operational_scope.does_not[5], raising at :106 -- "the supersedes
    chain would carry a false digest", declared b73a0e2f..., computed
    83ee4842.... The edit was the marker ZZ_S306_PROBE appended to that
    entry in memory; no wording was drafted and no served byte was
    touched. An edited draft must therefore be resealed to pass.

    A RESEALED DRAFT CARRIES ITS OWN DIGEST FORWARD. Given the edited text
    with manifest_digest.value set to the edited document's own digest,
    _transform_source wrote supersedes_digest 83ee4842... while supersedes
    pointed at the live published URL. That is a manifest asserting it
    replaces bytes whose digest it does not carry.

    ONE STEP OF THAT CHAIN WAS NOT EXECUTED AND IS NOT CLAIMED HERE. That
    a reseal is what writes manifest_digest.value was CONSTRUCTED BY HAND
    in this run, because seal_glm_manifest requires the operator key and
    signing sits outside the read-only bound of D305-1(a). It is supported
    by the digest of the served bytes matching their declared value and by
    the canonicalization_method text the ceremony writes at :165-171, and
    it stays INHERITED, not measured.

    THE GUARD AND THE CARRIER ARE INDEPENDENT. With manifest_digest.value
    replaced by sixty-four zeros, _transform_source copied that value into
    supersedes_digest without complaint. _check_source_is_sealed binds a
    source's declared digest to that source's own bytes; nothing binds a
    successor's supersedes_digest to the bytes served at its supersedes
    URL. The second binding is the predicate the checker approved under
    D305-1(a) implements, recorded now as an execution and no longer as a
    reading of :136 and :163.

    URL AND DIGEST ARE NEVER COMPARED. Run against the unmodified served
    manifest with supersedes_url https://zz.invalid/s306-probe,
    _transform_source produced the correct published digest beside a URL
    that resolves to nothing. Neither half constrains the other.

    G4 ACCEPTS A REGRESSION, MEASURED. _check_version_advances refused
    new_version "5.49.0" at :120 and ACCEPTED "1.0.0" against owner.version
    5.49.0, so the TUF ordering bound recorded in the preceding entry is
    now bound to an execution. Two independent implementations shipped
    this predicate wrong: go-tuf did not implement the rollback checks
    correctly (CVE-2022-29173), and tough ran its check only after
    persisting the metadata it was checking (CVE-2025-2888). The checker
    therefore evaluates before it reports, never after a write.

    THE NEGATIVE ARM THE APPROVED TOOL LACKED NOW EXISTS AS A RECIPE. The
    published chain has one link and it passes, so every input the tool
    would otherwise have seen was a passing one. Four failing shapes are
    derivable from the ceremony itself: a correct digest beside an
    unfetchable URL; a placeholder digest copied through; a successor
    digest that is its own; and a version that regresses. With the
    null-valued root and the live link that is six cases. None was written
    to disk in this session and none is a fixture until it is.

    NO CORRECTION IS OWED AND THIS ENTRY AUTHORISES NOTHING NEW. The
    published chain remains intact over fetched bytes. DN[5] was not
    corrected, drafted, or worded. The ceremony change (b) remains
    unauthorised on the terms of the preceding entry, and measuring what
    the ceremony would do is not an argument for changing it. Section 12
    stands unchanged and this entry does not widen it.

  - S307. THE HONEST BOUNDARY AND THE BOUNDS WERE RECONCILED ONE BY ONE,
    AND THE MOVEMENT CHECK IS DECIDED OUT. Section 5 was written at S304
    and the six bounds at S305; no session compared the two. This entry
    is that comparison. The instrument's reach is declared first: the
    bounds constrain what the approved tool may do, they are not the
    grant, and the grant is the S305 entry above together with
    ADR-0011:113-117. An element falling outside the bounds is therefore
    not thereby unauthorised.

    THE FIVE EVIDENCED ELEMENTS OF SECTION 5, EACH AGAINST THE SIX
    BOUNDS.
      E1, the predecessor bytes hash to the value carried in the
      successor: PARTIAL. No bound names it. Bound 1 fixes its shape,
      the predicate taking bytes with the fetch as a wrapper, and bound
      3 removes the null-valued root from it. E1 is the grant itself.
      E2, the successor's own digest matches its served bytes: NOT
      COVERED, and not needed. verify_glm_manifest already performs it
      and printed digest_ok True on 2026-08-07.
      E3, both manifests carry an Ed25519 signature from the pinned
      operator key: PARTIAL. The successor half is shipped and printed
      signature_ok True with signer_pinned True on 2026-08-07. The
      predecessor half is performed by nothing in the tree and is
      required by no bound. Whether the archived 5.37.0 signature
      verifies under the pinned key is UNMEASURED. Named here, not
      resolved here.
      E4, the successor's version does not regress: COVERED. Bound 2
      names it and names the implementation, a parsed tuple and not a
      string compare.
      E5, at least one non-ceremonial field moved: NOT COVERED, and
      decided out below.

    THE NON-CLAIMS AND THE TWO LIMITS ARE UNTOUCHED. Section 5's four
    what-is-not-claimed sentences, the single-issuer structural limit,
    and the measurement limit recording that the S304 fetch resolved to
    the origin are negative statements. No bound reaches them and none
    contradicts them.

    THE MOVEMENT CHECK DOES NOT ENTER THE TOOL. The operator's grounds,
    recorded as given: the S304 entry above already killed it for
    vacuous passage and that reason does not stop at section 2; none of
    the six bounds names it; materiality is carried as open in section
    13, so the check is decidable but insignificant; it rejects a
    legitimate re-anchor; and it merges a binding with a materiality
    judgement under a single rc. IF THE INFORMATION IS WANTED IT LEAVES
    AS A REPORTED CLASS AT rc 0, on the served_mirror_check
    ORPHAN_SERVED pattern, reported and not condemned. The section 5
    sentence "That at least one non-ceremonial field moved" is
    superseded by this entry and is not edited above, per ADR-0011
    constraint 2 applied to this document.

    FOUR OF FIVE ELEMENTS ARE NOT CLEANLY COVERED, AND THAT IS A FINDING
    ABOUT THIS GATE AND NOT ABOUT THE TOOL. One mismatched line would be
    a correction. Two PARTIAL and two NOT COVERED are evidence that the
    section stating the honest boundary and the section stating the
    tool's bounds were authored in different sessions and were never
    bound to each other. The bounds were written as construction limits,
    not as coverage of section 5, and nothing in either section says so.
    Any future bound list states which section 5 element each bound
    serves.

    PLACEMENT, MEASURED 2026-08-07. docs/GLM_SUPERSESSION_DESIGN.md is
    the only tracked path carrying that name. It is not under website/,
    it is absent from /var/www/nous-lang.org, and the only served .md is
    README.md. claims.toml exclude_dirs does not contain docs, so this
    document is linted. Its readers are the public repository and the
    linter and not the served surface, so a correction to it is a docs
    commit and not a deploy.

    THIS ENTRY AUTHORISES NO CODE. No file was created, no test changed,
    no manifest touched, and no DN[5] wording drafted. The ceremony
    change (b) remains unauthorised on the terms of the S305 entry.
    Section 12 stands unchanged and this entry does not widen it.
    Sequence, per the S305 entry: this entry first, the tool afterwards,
    in separate gates.
