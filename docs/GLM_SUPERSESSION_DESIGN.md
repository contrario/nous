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

  - S307. THE ARCHIVE ROOT IS DIGEST-ONLY BY DECLARATION, AND SECTION 5
    OVERSTATES WHAT THE LINK CAN EVIDENCE. Measured 2026-08-07 against
    the tracked bytes of both manifests. scripts/sign_glm_manifest.py
    verify (e8de230f) was run on each with no sidecar; both manifest
    digests and the tool's own digest were identical before and after,
    and porcelain was the same two untracked entries throughout.
    Nothing was written.

    WHAT PRINTED. On the archived 5.37.0 manifest: digest_ok True,
    signature_present False, signer_pinned False, signature_ok False,
    owner_version 5.37.0, rc 2, and one error naming the class,
    "manifest carries no Ed25519 signature (digest-only: content
    integrity without authorship)". On the published manifest in the
    same paste as the positive arm: digest_ok True, signature_present
    True, signer_pinned True, signature_ok True, rc 0. The arm was
    capable of a different answer and gave one.

    THE ROOT'S SIGNATURE IS ABSENT BY DECLARATION, NOT MISSING BY
    OMISSION. Its manifest_signature carries note and
    planned_extensions with type and value both null, and the note
    states that a signature was not implemented in that version, that
    the digest verifies content integrity, and that a signature would
    verify authorship. The same shape as the null-valued supersedes
    fields: keys present, values null, deliberate. The archived root
    therefore carries two independent properties, not one.

    SECTION 5 ELEMENT E3 IS FALSE OVER THE PUBLISHED BYTES. It reads
    "That both carry an Ed25519 signature from the pinned operator
    key". The successor does. The predecessor does not, and by its own
    text never did. This is a correction, recorded as an entry and not
    as an edit above, per ADR-0011 constraint 2.

    THE PRECEDING S307 ENTRY IS CORRECTED ON ONE LINE. It recorded
    "Whether the archived 5.37.0 signature verifies under the pinned
    key is UNMEASURED". That presupposes a signature to verify. The
    question was asked one level too late and the answer is that there
    is none. The line stands above as written and is corrected here.

    THE FIXTURE RECIPE CONFLATES TWO PROPERTIES. THIS IS A REFINEMENT
    AND NOT A CORRECTION. The S306 entry names its second case as "the
    null-valued root". A fixture built on the null link alone is not
    the published root and a tool exercised only against it would never
    meet an unsigned predecessor. The two properties are separable in
    principle -- a signed manifest may carry a null link, and a linked
    manifest may be unsigned -- so they are two cases and not one. The
    six-case recipe is therefore under-specified at that case, and the
    tool gate writes the fixtures from this entry rather than from the
    S306 count.

    WHAT THIS ENTRY DOES NOT DECIDE. What the checker reports when a
    predecessor is unsigned. The shipped verifier returns rc 2, but the
    S306 scripts/ census recorded that rc 2 carries at least six
    meanings under that directory and that an exit vocabulary is to be
    chosen and declared, never inherited. The choice belongs to the
    tool gate; it is named here and not taken.

    AUTHORISES NOTHING NEW. No file created, no test changed, no
    manifest touched, no DN[5] wording drafted. The ceremony change (b)
    remains unauthorised on the terms of the S305 entry. Section 12
    stands unchanged and this entry does not widen it.

  - S307. THE VERIFIER MODULE WAS READ END TO END, AND TWO INHERITED
    LABELS ARE DISCHARGED BY READING RATHER THAN BY EXECUTION.
    glm_manifest.py (92fb4ea1, 312 lines, 11192 bytes, worktree equal to
    origin/main) was read in full on 2026-08-07. Nothing was written.

    A RESEAL IS WHAT WRITES manifest_digest.value, AND THIS IS NOW READ
    FROM THE FUNCTION. seal_glm_manifest sets that field to the digest
    placeholder at :119, serializes at :138, hashes the placeholder form
    at :142, and substitutes the computed hex at :143. The S306 entry
    above left this INHERITED on the ground that seal_glm_manifest
    requires the operator key. It does not require the key to be read.
    The label is discharged; the S306 entry stands as written.

    THE UNSIGNED ROOT IS A CODE PATH, NOT A RELIC. With private_key None
    the same function writes manifest_signature type None and value None
    at :134-136. That is exactly the shape of the archived 5.37.0
    manifest measured earlier in this session. The archive root was
    sealed by this code without a key; it is not the residue of an
    earlier scheme.

    FOUR SHAPE FACTS THE TOOL MUST OBEY, EACH FROM A NAMED LINE.
      GlmVerifyDetail.ok is digest_ok and signature_ok at :170-172. For
      the archived root signature_ok is False while digest_ok is True,
      so ok is False on an intact predecessor. The tool reads the
      per-step booleans and never ok.
      canonical_glm_bytes performs exactly two substitutions, at :83 and
      :89. supersedes_digest therefore sits inside the hashed bytes,
      covered by the digest and by the signature over it, and compared
      with nothing. Previously a reading of section 0; now read from the
      function.
      canonical_glm_bytes raises rather than returning a verdict.
      _require_single at :36-42 raises GlmManifestError when the digest
      value does not occur exactly once as a quoted string. On fetched
      predecessor bytes that is a reachable path, so the tool catches
      GlmManifestError; otherwise a malformed response leaves as a
      traceback instead of a verdict.
      The signature covers the digest, not the bytes. It is made over
      bytes.fromhex(declared) at :148 and verified over the same at
      :264, so the key binds the digest and the digest binds the
      canonical bytes, in two steps. Without a hex manifest_digest.value
      no signature check runs at all, per :254-255.

    ONE DOCSTRING IS STALE. NAMED, NOT CORRECTED. :189-191 states that
    the default pinned allowlist is empty because no signing ceremony
    has run. KNOWN_GLM_MANIFEST_PUBLIC_KEYS_B64 at :23-25 carries one
    key, and it is the key the published manifest carries. The described
    behaviour holds; its stated premise does not. claim_lint does not
    reach this because it checks vocabulary, not truth. This is a source
    file and section 12 forbids code in this gate, so it is recorded and
    left alone.

    PLACEMENT FACTS FOR THE TOOL, MEASURED 2026-08-07. scripts/ is not a
    package: tests load a script by file path through
    importlib.util, stated in tests/test_s159_u2 and tests/test_s297 and
    implemented as _load_signer in tests/test_s298. The GLM test
    convention is inline dicts plus tmp_path, not fixture files: of the
    41 tracked non-.py files under tests/ none is a GLM manifest by
    name, and the only real manifest any GLM test reads is the archive
    root. A fixture built on the _source_manifest helper of
    tests/test_s298 does NOT reproduce the published root: that helper
    writes signature type "ed25519" with value None, while the root
    carries type null and value null.
    glm_manifest.py runs to 80 columns, so the 79-column rule of this
    document is a document rule and not a source rule.

    THE LOCK SET IS FOUR MARKERS AND A NEW SCRIPT REDDENS NONE OF THEM.
    __s233_p3_sidecar_lock_test_v1__, __s236_p1_alias_lock_test_v1__,
    __s236_p3_claim_lint_lock_test_v1__ and
    __s236_p4_cold_audit_lock_test_v1__, each occurring exactly once, on
    line 1 of its own test file. No test under tests/ pins a claim_lint
    scanned-file count, and no test pins a file set under scripts/: none
    of the five directory enumerations in tests/ reaches scripts/.
    The S305 bound says three locks without naming them and the tree
    yields four under this phrasing; the tool is held to reddening none
    of the four, which satisfies either reading. Bound 6 is a prediction
    discipline and not a redness guard: claim_lint scans 420 files
    today and a new scripts/*.py makes it 421.

    AUTHORISES NOTHING NEW. No file created, no test changed, no source
    edited, no manifest touched. The ceremony change (b) remains
    unauthorised. Section 12 stands unchanged and this entry does not
    widen it.

  - S307. THE OPERATOR'S DECISION ON THE CHECKER'S RESULT VOCABULARY,
    RECORDED AS D307-1. THE CONTRACT IS THE VERDICT TOKEN; THE EXIT CODE
    IS A PROJECTION OF IT. The tool prints a named verdict and projects
    that name onto an exit code. Fixtures assert the name. One separate
    test asserts the projection. A later change to the projection then
    touches one test and no fixture.

    THE GROUND IS A MEASURED COLLISION, NOT A PREFERENCE. Two shipped
    tools in this tree use rc 1 and rc 2 for opposite things.
    scripts/served_mirror_check.py returns 1 for a negative verdict
    (drift, :123) and 2 for FAILED MEASUREMENT (:76, :79, :99, :105).
    scripts/sign_glm_manifest.py returns 1 when it cannot read its
    inputs (:330, :340) and 2 for a negative verdict (:351, "0 if
    detail.ok else 2"), which is what it printed against the archived
    root earlier in this session. No single rc table agrees with both.
    Choosing a table was therefore the wrong thing to be deciding.

    THE PRECEDENT FOR NAMES-OVER-CODES IS ALREADY IN THE TREE.
    served_mirror_check declares DIFFER, MISSING_SERVED and
    ORPHAN_SERVED as classes in its own docstring at :14-17 and prints
    RESULT plus per-file class names at :107-125; the rc is one branch
    over those names. scripts/claim_lint.py carries the same split with
    --sarif and --json output and a single projection line repeated at
    :970, :983 and :1011.

    EXTERNAL PRACTICE, READ 2026-08-07. HashiCorp's terraform plan
    documents -detailed-exitcode as a flag that CHANGES the exit codes
    and their meanings when provided (0 empty diff, 1 error, 2 non-empty
    diff), so the granular vocabulary is an opt-in projection and not
    the command's contract. clig.dev holds that machine-readable output
    belongs on stdout, that messages belong on stderr, and that non-zero
    codes should be mapped to the most important failure modes. The
    Pigweed CLI style guide, which defers to clig.dev, holds that when
    multiple non-zero codes are used they must be documented and treated
    as a stable API, and that codes 126 and above are to be avoided
    because shells return them.

    THE TOKEN SET, DERIVED HERE AND NOT COUNTED BY EYE. The rule is one
    token per distinct condition a fixture can exhibit. Applying it to
    the conditions measured this session yields nine, in three classes.
    A count of six was floated before the derivation and is wrong; it is
    left visible here rather than quietly replaced.
      CHECKED, NOTHING WRONG.
        VERIFIED         the fetched predecessor hashes to the declared
                         supersedes_digest.
        ROOT             supersedes and supersedes_digest are both
                         present and null; the archived 5.37.0 manifest
                         is exactly this shape.
        DIGEST_ONLY      the digest matches and the predecessor carries
                         no signature, which the shipped verifier
                         already names "digest-only: content integrity
                         without authorship".
      CHECKED, WRONG.
        DIGEST_MISMATCH  fetched predecessor bytes do not hash to the
                         declared value.
        VERSION_REGRESSED  the successor's owner.version does not
                         advance over the predecessor's, compared as a
                         parsed tuple and never as a string.
        MALFORMED_LINK   the link is not a link: one of the two fields
                         null and not the other, or a supersedes_digest
                         that is not 64 lowercase hex, such as the
                         publish-time placeholder.
        SIGNATURE_BAD    the predecessor carries a signature that does
                         not verify under the pinned allowlist. This is
                         the honest completion of section 5's E3, whose
                         "both" was corrected earlier in this ledger:
                         unsigned is reported, badly signed is not.
      COULD NOT CHECK.
        UNREACHABLE      the predecessor could not be obtained: network
                         failure, non-200, or a redirect ending
                         elsewhere.
        UNREADABLE       bytes were obtained but are not a
                         digest-computable manifest. glm_manifest.py
                         raises GlmManifestError here rather than
                         returning a verdict (:36-42), so the tool
                         catches it; an HTML page returned 200 by an SPA
                         catch-all lands in this token and never in a
                         traceback.
    This set is derived from the conditions measured in this session and
    is not claimed complete. A condition found later takes a new token;
    it does not get folded into an existing one.

    THE PROJECTION. rc 0 for the first class, rc 2 for the second, rc 3
    for the third. 2 is chosen because the sibling tool on this same
    artifact uses 2 for a negative verdict at :351. 3 is chosen because
    no tracked script uses 3 as a verdict, so "could not check" gets a
    code it does not share with a judgement, which is what section 11
    requires when it says a fetch failure is reported as UNKNOWN and
    never as PASS. rc 1 is left unassigned. The tool declares this table
    in its own docstring, per the Pigweed rule that non-zero codes are a
    stable API.

    THE OBJECTION, STATED AND NOT DISMISSED. A reader who inspects only
    $? loses the token. That is the shape of the standing F1 finding,
    where scripts/release.py gates on a pass count and never reads
    failed. It is mitigated but not removed by the projection: no
    verdict outside the first class reaches 0, so $? stays sound as a
    coarse signal. The token remains the truth and the code the summary,
    and the tool says so where it prints.

    NOT IN THIS DECISION. A --json mode: the named token on stdout is
    enough for a first read-only tool, and structured output is a later
    question. The rc vocabulary of any other tool in the tree is
    untouched; served_mirror_check keeps 2 for FAILED MEASUREMENT and
    this checker uses 3, and that residual difference is recorded rather
    than resolved.

    AUTHORISES NOTHING NEW. No file created, no test changed, no source
    edited, no manifest touched. The ceremony change (b) remains
    unauthorised. Section 12 stands unchanged and this entry does not
    widen it. Sequence: this entry first, then the fixtures, then the
    tool, in separate gates.

  - S308. THE OPERATOR'S DECISION ON THE VERSION TOKEN, RECORDED AS
    D308-1. VERSION_REGRESSED LEAVES THE SET; THE VERSIONS ARE REPORTED
    AND NOT JUDGED. The checker prints the owner.version pair and the
    manifest_version pair as observations, carries no verdict token for
    either, and states at the point of printing that it is reporting and
    not judging. The set defined at S307 goes from nine tokens to eight.
    The projection is unchanged: rc 0, rc 2, rc 3, rc 1 unassigned.

    THE GROUND IS AN ABSENT DECLARATION, MEASURED THREE WAYS AND NOT
    INFERRED ONCE. A verdict asserts that a rule was broken. No rule
    about owner.version exists to break.
      IN THE ARTIFACT. Both published bodies were read field by field on
      2026-08-08. timing_axis declares a position on the bind axis,
      "pre-bind", and is not an ordering of manifests. glm_compatibility
      declares a change policy -- "major version increment required",
      "minor version increment, backward compatible within major
      version" -- and declares it for the GLM SCHEMA version, which is
      "1.1" in both bodies. The manifest knows how to declare a version
      policy and declares one for schema_version only. The two bodies
      carry identical top-level key sets, both differences empty.
      IN THE SPECIFICATION. The provisional schema reference declared by
      both bodies was fetched from Server A at 2026-08-08T01:43:59Z:
      270374 bytes, sha256 35d36e67. It is now v2.0 at schema 1.3, while
      both NOUS bodies declare schema_version 1.1. It defines
      manifest_version as the version of the specific manifest document,
      distinct from the schema version, and encourages monotonically
      increasing manifest_version values for archival ordering. That is
      the designated ordering field, and it is ENCOURAGED, not required.
      NOUS carries manifest_version "1.0" in BOTH bodies: the designated
      field has never moved. The specification's field list carries no
      top-level owner; identity is structured under layer. The live
      conformant peer manifest at the same origin -- 12082 bytes, sha256
      72ebb45e, schema_version 1.2, manifest_version "6.0" -- carries 24
      top-level keys against our 22, sharing 21. It lacks
      supersedes_note, valid_until and vendor_framework_constructs from
      our side; owner is the ONLY key we carry that it does not.
      IN THE CEREMONY. _check_version_advances raises only on string
      equality, at :119. This document already records at :644 that the
      tool ACCEPTED "1.0.0" against owner.version "5.49.0". The producer
      permits regression today.

    WHAT A PARSER WOULD HAVE COST, MEASURED SO THAT NO SEAT RE-DERIVES
    IT. registry._version_tuple at :149-156 is the only shipped
    comparator and it CANNOT FAIL: every non-numeric component becomes
    0. Executed on Server A, "0.0.0-test" and "0.0.0" both give
    (0, 0, 0); "abc" and "" both give (0,); "v5.49.0" gives (0, 49, 0)
    and therefore orders BELOW "5.37.0". A comparator that cannot fail
    cannot separate a regression from a field that is not a version, so
    it would have emitted a judgement on a false premise. packaging 26.2
    is present on Server A at /usr/local/lib/python3.12/dist-packages
    and is NOT declared: pyproject.toml lists six runtime dependencies
    and importlib.metadata.requires("nous-lang") returns fourteen
    entries, none of them packaging. It discriminates correctly --
    Version("5.9.0") < Version("5.49.0") is True while the same
    comparison on the raw strings is False, and Version("0.0.0-test")
    raises InvalidVersion -- but it accepts "v5.49.0" as equal to
    "5.49.0", so not even PEP 440 is uniformly strict, and adopting it
    is a pyproject edit that D305-1(a) does not authorise.

    EXTERNAL PRACTICE, READ 2026-08-08. Every ordering mechanism read
    this session uses a dedicated monotonic integer whose only job is
    ordering. TUF requires the new root version to be exactly N+1 and
    otherwise discards it, aborts the cycle and reports a rollback
    attack. gittuf's fix for a policy rollback, reported in 2026, was to
    add a monotonically increasing number to all policy metadata files.
    RFC 5280 requires the CRL Number extension in conforming CRLs, a
    monotonic sequence number whose stated purpose is to determine when
    one CRL supersedes another. NOUS already carries that pattern
    internally twice, at CONTINUITY_LEDGER.md:130 and
    MEMORY_EVIDENCE_DESIGN.md:184. None of them orders by a product
    release string. SemVer 2.0.0 places build metadata outside
    precedence entirely, so even a well-formed version string orders
    only once its dialect is known, and no NOUS surface declares a
    dialect. THE STRONGEST PRECEDENT IS FOR DELETION RATHER THAN
    IMPLEMENTATION: RFC 9829 mandates that RPKI relying parties IGNORE
    the CRL Number extension where another monotonic number already
    orders the objects, on the ground that processing it adds
    complexity and fragility. This decision has that shape.

    THE SHAPE OF A NON-VERDICT IS ALREADY STANDARDISED. SARIF 2.1.0
    separates result.kind -- pass, fail, open, review, informational,
    notApplicable -- from result.level, and requires that when kind is
    anything other than "fail" the level is "none": a result that is not
    a judgement carries no severity. The S307 entry records at :908-910
    that scripts/claim_lint.py already carries --sarif output. The
    checker's observations take that shape, printed and unlevelled and
    outside the token set, rather than becoming a tenth token.

    F308-10, CORRECTED HERE AND NOT BY EDITING THE SECTION ABOVE. The
    S307 entry defines MALFORMED_LINK at :945-948 as including a
    supersedes_digest that is "not 64 lowercase hex". That is stricter
    than the specification and stricter than the ecosystem. The GLM
    specification states that the digest comparison is character for
    character and CASE-INSENSITIVE, and the live peer manifest carries
    its supersedes_digest in UPPERCASE hex. The families genuinely
    differ: the OCI image specification mandates lowercase by grammar,
    hex := /[a-f0-9]+/, RFC 4648 calls base16 the standard
    case-insensitive hex encoding, and BagIt permits either case.
    CORRECTED RULE: the shape test is 64 hexadecimal characters with no
    case constraint, and the comparison normalises case before
    comparing. Nothing in the NOUS chain changes -- our own producer
    writes lowercase and LINK_OK is True today -- but the token's
    definition was written as a general rule and would have reddened a
    conformant peer.

    MISSES SCORED THIS SESSION, LEFT VISIBLE. Three predictions failed
    and each failure changed a design input. Predicted that no
    version-comparison helper existed in this tree: several do, and
    registry._version_tuple is a shipped py-module. Predicted that it
    raises on "0.0.0-test": it coerces silently, which is precisely what
    disqualified it. Predicted zero occurrences of "monoton" in tracked
    files: 38 files carry it, two of them the prior-art sites named
    above. Separately, one instrument defect recurred three times and
    was caught only by pairing instruments: dict.get() cannot
    distinguish an absent key from a null value, and key presence must
    be tested with "in".

    AUTHORISES NOTHING NEW. No file created, no test changed, no source
    edited, no manifest touched, no dependency declared. The ceremony
    change (b) remains unauthorised and is made no more likely by any
    measurement recorded here. Section 12 stands unchanged and this
    entry does not widen it. Sequence: this entry first, then the
    fixtures, then the tool, in separate gates.

  - S308. THE FIXTURE SET IS SIX CONSTRUCTED, ONE DEFERRED AND ONE READ,
    RECORDED AS D308-3. The S307 entry names eight tokens after D308-1
    removed the ninth, and reads as though all eight are asserted by
    constructed fixtures. They are not, and the departure is recorded
    here rather than discovered in the fixture gate.
      CONSTRUCTED, SIX. ROOT, DIGEST_ONLY, DIGEST_MISMATCH,
      MALFORMED_LINK, SIGNATURE_BAD, UNREADABLE. Each is a property of
      bytes and each is built in memory.
      DEFERRED, ONE. UNREACHABLE is a property of the transport, not of
      any manifest: a non-200, a network failure, or a redirect ending
      elsewhere. It cannot be exhibited by bytes and its fixture waits
      for the tool's own fetch seam, in the tool's gate.
      READ, NOT CONSTRUCTED, ONE. VERIFIED. See below.

    THE ROOT SHAPE IS REPRODUCIBLE IN MEMORY, MEASURED 2026-08-08. An
    inline dict passed to seal_glm_manifest with private_key None
    returns text whose manifest_signature is exactly {"type": null,
    "value": null} and whose supersedes and supersedes_digest keys are
    both PRESENT with null values, confirmed by "in" and not by get().
    verify_glm_manifest on that text returns digest_ok True,
    signature_present False, ok False, one error. That is the published
    archive root's shape, element for element. F307-10 and F307-11 are
    therefore closed without any file under tests/fixtures/ and without
    the _source_manifest helper of tests/test_s298, which writes
    signature type "ed25519" where the root carries null.

    VERIFIED CANNOT BE CONSTRUCTED, AND THE THREE ROUTES ARE CLOSED BY
    MEASUREMENT RATHER THAN BY OPINION. signature_ok True under the
    DEFAULT allowlist requires the operator's private key.
      Monkeypatching KNOWN_GLM_MANIFEST_PUBLIC_KEYS_B64 does not work.
      The default is bound at definition time at :179, so rebinding the
      module attribute after import leaves the parameter default
      pointing at the original tuple. Executed: after rebinding to an
      ephemeral public key, signer_pinned stayed False and
      signature_ok stayed False.
      Passing trusted_keys_b64 explicitly does work -- an ephemeral key
      gives signer_pinned True, signature_ok True, ok True, zero errors
      -- but it exercises a call the tool never makes. F307-8 fixed
      that the checker calls verify_glm_manifest with the DEFAULT
      allowlist and never with a key found inside the document, so a
      fixture built on the explicit form asserts a path that does not
      exist in production.
      Using the real operator key in a test is forbidden.
    VERIFIED is therefore covered by READING the published manifest,
    which returns ok True under the default allowlist today, and whose
    bytes tests/test_s297 already locks. Construction is not available;
    the reading is honest and is labelled as a reading.
    SIGNATURE_BAD is unaffected: an ephemeral key against the default
    allowlist gives digest_ok True, signature_present True,
    signer_pinned False, signature_ok False -- constructed, not read.

    FOUR FACTS THE TOOL MUST OBEY, EACH EXECUTED AND EACH BOUND TO A
    LINE.
      anchor_present IS A PROPERTY OF THE CALL, NOT OF THE DOCUMENT. It
      is rekor_anchor is not None at :272. The published manifest
      verified without a sidecar returns anchor_present False and ZERO
      errors. The absence of an anchor is not a defect of a
      predecessor and the tool must not read it as one.
      A NON-EMPTY errors TUPLE IS NOT A NEGATIVE VERDICT. The intact
      unsigned root returns digest_ok True together with one error, the
      digest-only string emitted at :244-246. That combination IS the
      DIGEST_ONLY token, which projects to rc 0. The discriminator is
      the pair digest_ok True with signature_present False, never the
      length of errors.
      THERE ARE THREE RAISE SITES AND ONE EXCEPTION TYPE. json.loads
      inside verify_glm_manifest at :196-198, _block_value at :50, and
      _require_single at :39-42, all raising GlmManifestError, so one
      except clause suffices. This corrects an emphasis in the S307
      entry: an HTML page returned 200 by a catch-all lands at
      :196-198, not at _require_single. Executed: HTML, empty string
      and a digest-less JSON object all raise GlmManifestError.
      THE OBSERVATION FIELDS SURVIVE FAILURE. A tampered root returns
      digest_ok False while owner_version still reads "5.37.0", so the
      D308-1 requirement to report the version pair is implementable on
      every branch, including the failing ones.

    MISSES SCORED, LEFT VISIBLE. Predicted that the published manifest
    would verify with six True legs as it does in RULE 0; measured
    anchor_present False and anchor_ok False, because RULE 0 passes a
    sidecar and that call did not. A result was carried across two
    different call signatures, which is the FG-S307-A class. Separately
    and worse, a set of byte counts and sha values for this very
    payload was written into a message before the file existed. No
    instrument produced them. They were withdrawn in the next message
    and the real values were measured before any transfer.

    AUTHORISES NOTHING NEW BEYOND THE FIXTURES THE OPERATOR RELEASED.
    The prohibition on writing under tests/ was lifted by the operator
    on 2026-08-08, for the D305-1(a) fixtures and for nothing else, and
    that release is recorded as D308-2. No source is edited, no
    manifest is touched, no dependency is declared, no existing test is
    changed. The ceremony change (b) remains unauthorised. Section 12
    stands unchanged. Sequence: this entry first, then the fixtures,
    then the tool, in separate gates.

  - S309. THE FIXTURE UNIT IS A PAIR AND THE TOKEN IS GIVEN, RECORDED
    AS D309-1. D308-3 fixes WHAT is constructed. This entry fixes the
    FORM: what one fixture is, what it asserts, and what allows the
    file to redden. An earlier proposal, that the fixtures assert only
    the observable booleans of verify_glm_manifest, was put to the
    operator and REJECTED on 2026-08-08 on the ground that a fixture
    which cannot fail is not a control. What follows is the operator's
    decision and not a restatement of the proposal.

      THE UNIT IS A PAIR, NOT A DOCUMENT. Each case is
      (successor_text, predecessor_text_or_None). ROOT and
      MALFORMED_LINK need the successor alone; DIGEST_ONLY,
      DIGEST_MISMATCH, SIGNATURE_BAD and UNREADABLE need both.
      Fixtures built as single documents cannot express the link at
      all, and the link is what the checker checks.
      THE TOKEN IS GIVEN, NOT DERIVED. Every case carries its own
      token name as a literal string in a table. No classifier and no
      branch. This is how the D307-1 requirement that the fixtures
      assert the token is honoured before the tool that emits tokens
      exists.

    THREE GROUPS OF ASSERTIONS, EACH WITH A DIFFERENT JOB.
      PROPERTY. Each case exhibits the observable state its token
      names: digest_ok, signature_present, signer_pinned,
      signature_ok, the shape of the two link fields, and raise or no
      raise.
      SELF-CONSISTENCY. Where a pair must link,
      gm.compute_glm_digest(predecessor_text) equals
      successor["supersedes_digest"]. For DIGEST_MISMATCH the same
      expression is asserted NOT equal. Without this group a fixture
      drifts silently into a different token.
      PAIRWISE DISTINGUISHABILITY. No two cases share one observation
      tuple. This is the assertion that can redden and it is the
      reason the gate exists.

    THE LINK-FIELD SHAPE IS LOAD-BEARING, NOT DECORATIVE. ROOT and
    DIGEST_ONLY share all four booleans: digest_ok True,
    signature_present False, signer_pinned False, signature_ok False.
    The archived root is unsigned, measured at S308 and recorded at
    lines 1138 to 1148 of this ledger. Without the link fields in the
    observation tuple the distinguishability test cannot separate the
    two and two cases become one case. ROOT is discriminated by
    supersedes and supersedes_digest PRESENT with null values;
    DIGEST_ONLY by a real 64-character hexadecimal value.

    MALFORMED_LINK CARRIES NO PREDECESSOR BY CONSTRUCTION, NOT BY
    OMISSION. Its successor's link field is malformed, so no
    predecessor bytes exist that could match it and the
    self-consistency group has nothing to assert for it. Recorded so
    that a later seat does not read the absent assertion as an
    oversight and supply one.

    COMPLETENESS IS TESTED, NOT ASSUMED. A frozen tuple carries the
    eight token names. One test asserts that the constructed set is
    exactly six and that the two absent names are exactly UNREACHABLE,
    deferred to the tool's fetch seam, and VERIFIED, covered by
    reading the published manifest. A ninth token added anywhere
    reddens the file.

    THE LIBRARY BUILDS THE BYTES, NOT A TEST-LOCAL COPY.
    gm.seal_glm_manifest with private_key None is the constructor for
    the root shape, and with an ephemeral key for SIGNATURE_BAD. Both
    behaviours are INHERITED from the S308 entry at lines 1138 to 1148
    and 1171 to 1173 and are discharged by reading glm_manifest.py
    bytes inside the fixture gate, before the payload is built.
    The _sealed_source_text helper at tests/test_s298:71-78 does the
    same job for that file's own cases, but it writes
    manifest_signature type "ed25519" where the root carries null, so
    it does not produce the root shape. It is an existing test and it
    is not touched.

    KEY PRESENCE IS LOCKED WITH "in". tests/test_s298:213-214 asserts
    doc.get("supersedes") is None and doc.get("supersedes_digest") is
    None. get() cannot distinguish an absent key from a null value, so
    deleting both keys from the archived root would leave that test
    green. The null-valued keys are what root detection rests on and
    nothing currently locks their presence. The new file closes the
    gap with assert "supersedes" in doc, which D308-2 permits and
    which touches no existing test.

    FILE CONVENTIONS, READ FROM THE TWO GLM TEST FILES AS FILES IN
    THIS SESSION AND NOT INFERRED FROM AN INDEX.
      One file under tests/. Module-level helpers, no class and no
      conftest reference.
      Bare import glm_manifest as gm, as at tests/test_s297:21 and
      tests/test_s298:28. Neither file inserts sys.path.
      A marker of the form __s309_<subject>_v1__, alone on the last
      line of the module docstring, matching the markers at
      tests/test_s297:9 and tests/test_s298:16. Neither file carries
      a marker of the lock_test_v1 family.
      MAXLEN 80, as measured in tests/test_s297; tests/test_s298
      measures 78. ASCII only, no tabs, no trailing whitespace.
      claim_lint scans 420 files today. A new tests/*.py makes it
      421, ARITHMETIC, to be confirmed after the file lands.

    WHAT THE TOOL'S GATE INHERITS FROM THIS FILE. The tool's own tests
    import the table and assert that classify of a case equals the
    token the table already carries. The fixture file is not edited in
    that gate. That is the reason the token is given now rather than
    derived later.

    TWO FACTS READ FROM THE TEST FILES, RECORDED WITHOUT ACTION.
      The ceremony still refuses an uppercase predecessor digest,
      locked at tests/test_s298:111-120, while D308-1 removed the
      lowercase constraint from the checker's MALFORMED_LINK shape
      test. These are two different objects. A fixture asserting
      case-insensitive acceptance is scoped to the checker and makes
      no claim about the ceremony.
      tests/test_s297:172 locks the published predecessor digest as
      lowercase. That is a lock on our own published bytes and is
      unaffected by the specification's case-insensitive comparison.

    MISSES SCORED, LEFT VISIBLE. Predicted that continuation lines
    under an entry head are indented four spaces; measured two levels,
    four and six, the second for enumerated sub-items. That was a
    single-level prediction taken from an index rather than from
    bytes. Separately, a census phrased as the lock_test_v1 marker
    family was carried into a sentence about markers in general; both
    test files do carry a marker, of a different convention. That is
    the S308 MISS 1 class, caught before it reached a decision.

    AUTHORISES NOTHING NEW. No source is edited, no manifest is
    touched, no dependency is declared and no existing test is
    changed. The only write permitted is the single file released by
    D308-2. The ceremony change (b) remains unauthorised and nothing
    recorded here makes it more likely. Section 12 stands unchanged
    and this entry does not widen it. Sequence: this entry first, then
    the fixture file, then the tool, in separate gates.

  - S309. THE TOKEN NAMES THE LINK AND EVERY ROW CARRIES ITS SUBJECT,
    RECORDED AS D309-2. D309-1 fixed the form of a fixture. This entry
    withdraws one reason inside it, states the scoping that the wrong
    reason concealed, adds a seventh row, and records where each of its
    measurements was printed. It takes its own gate and precedes the
    fixture file, because it determines what the fixtures assert.

    THE CORRECTION. The D309-1 paragraph opening THE LINK-FIELD SHAPE
    IS LOAD-BEARING states that ROOT and DIGEST_ONLY share all four
    verifier booleans. Measured: ROOT carries no predecessor, so it has
    no verifier booleans at all and there is nothing to share. The
    reason is withdrawn. The conclusion is not: it survives twice over,
    and the paragraph is left exactly as written, since corrections are
    appends.

    THE SCOPING. A token names the LINK, and a link has two ends. Which
    end a row speaks about is a field, written beside the token, not
    inferred by a reader.
      SUBJECT LINK, no fetch was performed. ROOT and MALFORMED_LINK.
      Every verifier field is absent. That is not a collision between
      two cases; it is the signature of no predecessor having been
      examined.
      SUBJECT PREDECESSOR, a fetch was performed. VERIFIED,
      DIGEST_ONLY, DIGEST_MISMATCH, SIGNATURE_BAD, UNREADABLE and
      UNREACHABLE.

    THE TABLE IS SEVEN ROWS CARRYING THREE PROVENANCE LABELS. One
    label across all rows would be false.
      CONSTRUCTED, six. ROOT, DIGEST_ONLY, DIGEST_MISMATCH,
      MALFORMED_LINK, SIGNATURE_BAD, UNREADABLE.
      READ, one. VERIFIED. It is not constructible under the default
      allowlist, per the S308 entry, and it is read from the published
      manifest instead.
      ABSENT BY DECISION, one. UNREACHABLE appears INSIDE the table as
      a row whose absence is its content. An absence shown is
      measurable; an absence left outside the table is an omission
      that resembles a decision.

    DISTINGUISHABILITY IS MEASURED WITHIN A SUBJECT, NEVER ACROSS ONE.
      LINK: two cases, two distinct values of the link-field shape,
      NULL and MALFORMED.
      PREDECESSOR, constructed rows only: four cases, three distinct
      on the four booleans.
      PREDECESSOR with the READ row included: five cases, four
      distinct on the four booleans. The seventh row earns its place
      by adding a distinction, and it is the only row reaching
      signer_pinned True.
      PREDECESSOR on the booleans together with the link comparison:
      five distinct. The surviving pair on booleans alone is
      DIGEST_ONLY with DIGEST_MISMATCH.

    THE POSITION SURVIVES ACROSS AND WITHIN. Without the link
    dimension the six constructed cases fall to four distinct
    observations, which is the across-subject artifact that produced
    the withdrawn reason. Within the PREDECESSOR subject the link
    comparison is load-bearing again, separating DIGEST_ONLY from
    DIGEST_MISMATCH, which share their booleans exactly. D309-1
    reached a correct requirement through an incorrect argument, and
    the requirement is confirmed by a second measurement that does not
    depend on the first.

    HEX64 IS THE TRANSITION, NOT A TOKEN. The link-field shape takes
    three values. NULL yields ROOT. MALFORMED yields MALFORMED_LINK.
    HEX64 yields NO token: it is the condition under which the tool
    proceeds to a fetch and the subject changes to PREDECESSOR. Every
    PREDECESSOR row carries HEX64 and no LINK row does. Stated here so
    that a later reader does not hunt for a third LINK token.

    THE SEVENTH ROW HAS AN EXISTING CONVENTION AND A COST.
      tests/test_s297:145-158 already reads the published manifest and
      calls verify_glm_manifest on it. The VERIFIED row follows that
      shape rather than inventing one.
      Its four booleans are digest_ok, signature_present,
      signer_pinned and signature_ok, all True, printed by the RULE 0
      GLM verify leg of this session. Those four do not depend on the
      sidecar; that they do not is INHERITED from the S308 entry and
      is labelled, not leaned on.
      THE COST. Two files will now redden when the manifest is
      resealed, where one did before. They are not duplicates: 297
      locks the published bytes, and this row states that VERIFIED is
      observable and distinct. Two statements over one artifact, which
      is acceptable and is recorded rather than discovered later.

    THE FIXTURE SUPPLIES ALL FOUR SIGNATURE KEYS. seal_glm_manifest
    forces only type and value to null at :134-136 and passes every
    other key through, so the shape of manifest_signature is a
    property of the input dict. A fixture that omits note and
    planned_extensions reproduces a two-key block, and the D308-3
    phrase about the published root's shape element for element would
    become false. Executed with all four supplied, the constructed
    root printed note, planned_extensions, type and value.

    THE TOOL DOES NOT VERIFY THE SUCCESSOR. scripts/sign_glm_manifest
    verify already does that, six legs and rc 0 at every RULE 0. A
    second oracle over one artifact is the FG-S244-A shape and the
    RFC 9829 shape at once: a second ordering mechanism adds
    complexity and fragility where one already governs. The checker
    reads the successor's link fields and nothing else from it.

    PRIOR ART, EXTERNAL, SUPPLIED BY THE OPERATOR ON 2026-08-08 AND
    NOT FETCHED BY THIS SEAT.
      C2PA 2.4. A validation status entry carries code, url and
      explanation, where url is the JUMBF URI the status applies to.
      validationResults are per-manifest, with ingredientDeltas as a
      sibling for statuses belonging to a referenced ingredient. The
      code manifest.inaccessible, a referenced ingredient manifest
      that cannot be found, is our UNREACHABLE: a status about the
      referenced object, recorded in the referring one.
      in-toto. subject is a required field, matched by digest, and the
      predicate is metadata about that subject.
      Both families reach the same conclusion. The record names its
      subject explicitly; a bare token does not carry enough.

    RECORDED, NO ACTION. C2PA warns validators that follow ingredient
    url chains to guard against unbounded recursion. D305-1(a) checks
    ONE link and not a chain, so the hazard is out of reach by
    construction rather than by a defence, and no defence is written.

    PROVENANCE OF THE MEASUREMENTS IN THIS ENTRY.
      glm_manifest.py was read end to end on Server A: 312 lines,
      11192 bytes, sha 92fb4ea1.
      That module was then reconstructed inside the seat's container
      and its sha matched 92fb4ea1 before anything was executed
      against it. The six constructed rows, the partition and every
      distinctness count above were executed THERE and NOT on
      Server A.
      The VERIFIED booleans came from the RULE 0 GLM verify leg on
      Server A.
      Confirmation on Server A needs no gate of its own. The fixtures
      will run there and will fail there if any count above is wrong.

    ERRORS NAMED IN THIS GATE.
      FG-S309-A, AN ABSENCE ASSERTED WITHOUT A READ. The seat wrote
      that nothing fixed which document the tokens describe, while the
      entry defining the token set sat unread in this same file. This
      is the inverse of an untested inherited claim: a gap asserted
      without the instrument that would have found it filled.
      FG-S309-B, A RULE READ THREE TIMES DID NOT HOLD. A table of sha
      and byte counts for a payload was written into a message before
      the payload existed, one message after the seat itself named
      FG-S308-A, which is the same act. The rule was in the handoff,
      in the opener, and in the seat's own prose. The finding is not
      the repetition; it is that a rule can be read, restated and
      still not bind. The standing fix is mechanical rather than
      verbal: build, measure, paste the instrument output, and only
      then write prose. A number that does not yet have a paste behind
      it does not get written, and intending to measure it afterwards
      is the failure itself.
      Three predictions in this gate were relabelled DERIVED and not
      scored, because re-partitioning a table already in hand cannot
      surprise. One further prediction was withdrawn as unfalsifiable.

    AUTHORISES NOTHING NEW. No source is edited, no manifest is
    touched, no dependency is declared and no existing test is
    changed. The only write still permitted is the single fixture file
    released by D308-2. The ceremony change (b) remains unauthorised
    and nothing here makes it more likely. Section 12 stands unchanged
    and this entry does not widen it. Sequence: this entry first, then
    the fixture file, then the tool, in separate gates.
