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

  - S309. THE TABLE CARRIES ONE ROW PER TOKEN, RECORDED AS D309-3. Two
    corrections, both arithmetic rather than scoping, in one append.
    This entry takes its own gate and precedes the fixture file for the
    same reason D309-2 did: the first correction is asserted by the
    completeness test, and a claim the code asserts must be closed in
    bytes before the code is written. If the header and the fixture
    landed together the fixture would be fixing the number and the
    ledger would be a transcript of the code rather than its authority.

    CORRECTION ONE. THE HEADER CONTRADICTED ITS OWN ENUMERATION. The
    D309-2 paragraph opening THE TABLE IS SEVEN ROWS enumerates
    CONSTRUCTED six, READ one and ABSENT BY DECISION one. That is not
    seven. The header survived from a draft written before UNREACHABLE
    was moved INSIDE the table, and was not re-counted after the
    correction that invalidated it.
      THE FIX IS NOT A NEW NUMBER. Replacing seven with eight would be
      the same defect at a different value. The table carries ONE ROW
      PER TOKEN in the set fixed by D307-1 and amended by D308-1, which
      removed the ninth. The enumeration is its partition: two rows of
      subject LINK, four constructed rows of subject PREDECESSOR, one
      READ row and one ABSENT BY DECISION row. Written as a property,
      the header cannot contradict the enumeration again.
      THE COMPLETENESS TEST ASSERTS SET EQUALITY, NOT LENGTH. It
      compares the table's keys against the frozen token tuple. A test
      reading len(TABLE) equals a literal breaks at the next amendment
      of the token set and reports a false failure about arithmetic; a
      test reading set(TABLE) equals the tuple keeps reporting the
      thing that matters, which is whether a token has no row or a row
      has no token. No count is written into the file anywhere.
      The eight names are read from bytes: the D308-3 entry in this
      ledger lists the constructed six, names UNREACHABLE deferred and
      VERIFIED covered by reading, and states that D308-1 removed the
      ninth.

    CORRECTION TWO. THE claim_lint VALUE, WITH ITS LABEL.
      MEASURED. claims.toml is 190 lines, 8733 bytes, sha f9919834.
      Its [surfaces] block sets include to *.py, *.md and *.html at
      :166, and exclude_dirs at :167-170 carries "tests" at :168.
      WITHDRAWN. D309-1 states that a new tests/*.py takes the scan
      from 420 to 421. That was an extension of F307-12, which measured
      scripts/*.py, to a directory the config appears to exclude. It
      was labelled ARITHMETIC, which is what kept it honest, but it was
      never derived from anything.
      PREDICTED, NOT MEASURED. The scan stays at 420 and the new file
      is not scanned. This rests on the CONFIG. scripts/claim_lint.py,
      sha b6380185, has not been opened by this seat, so whether the
      tool honours exclude_dirs is unread.
      HOW IT CLOSES. The lint run inside the fixture gate settles it
      and no separate gate is needed. If it reports 421 while "tests"
      is declared at :168, the finding is not the number: it is that
      exclude_dirs is not honoured, which is larger than this entry,
      and work stops there.

    A CENSUS ARTIFACT, CAUGHT IN THIS SEAT'S OWN INSTRUMENT. Searching
    claims.toml for the string tests returns two lines, :37 and :168.
    Only :168 is a mention of the directory. Line :37 is the entry
    "attest", "attests", "attested" in allowed_claim_words, where the
    match is a SUBSTRING, NOT A MENTION. The phrasing is recorded
    because the next seat will run the same search and get the same
    two.

    A PRIOR THAT HITS DOES NOT VALIDATE THE METHOD. The operator
    recalled, without verification, that claims.toml excluded tests/
    at about line 168. The read confirmed it exactly. That was a prior,
    not a source, and it is recorded as one. A later seat reads
    claims.toml; it does not carry this sentence forward as evidence.

    FG-S309-C, A COUNT SURVIVED THE CHANGE THAT INVALIDATED IT. Unlike
    FG-S309-B this number was measured when written. It became false
    when an accepted correction moved a row into the set it counted,
    and the header was not re-derived. The standing fix: when a
    correction changes what a set contains, every count over that set
    is recomputed in the same message, or the count is replaced by the
    property that generates it. The second is preferred, because a
    property cannot go stale.

    AUTHORISES NOTHING NEW. No source is edited, no manifest is
    touched, no dependency is declared and no existing test is
    changed. The only write still permitted is the single fixture file
    released by D308-2. The ceremony change (b) remains unauthorised.
    Section 12 stands unchanged and this entry does not widen it.
    Sequence: this entry first, then the fixture file, then the tool,
    in separate gates.

  - S310. WHAT THE DIGEST ESTABLISHES, WHERE THE CANONICAL FORM IS
    BLIND, AND WHY digest_ok IS A PRECONDITION AND NOT AN OBSERVATION,
    RECORDED AS D310-1, D310-2 AND D310-3. Three decisions in one
    entry. None of them adds a token. One of them asks the operator
    for a separate authorisation, with four named reasons, in a gate
    of its own after the tool.

    D310-1. THE DIGEST ESTABLISHES IDENTITY, SO DIGEST_MISMATCH IS NOT
    A PRECEDENCE RULE. When a fetched predecessor both fails the link
    and carries a signature that does not verify, the verdict is
    DIGEST_MISMATCH. No token is added and no ordering is declared.

      THE REASON IS IDENTITY, NOT PREFERENCE, AND THE DIFFERENCE IS
      LOAD-BEARING. ADR-0011 commits a supersedes link to published
      bytes; its commit subject at 84ca0b9 states it as "a supersedes
      link commits to published bytes". If the fetched bytes do not
      hash to the declared supersedes_digest, the predecessor was not
      obtained. Some other document was. Every later statement of the
      form "the predecessor's signature does not verify" is then a
      statement about an unidentified document, and SIGNATURE_BAD
      there is an overclaim of exactly the class this project exists
      to police.
      A rule written as a preference invites the next seat to reorder
      it on a different preference. A rule written as identity cannot
      be reordered, because reordering it would require the tool to
      speak about a document it has not identified. That is why this
      paragraph gives the reason and not the order.

      D307-1:965-967 DOES NOT APPLY. That rule reserves a new token
      for a new condition. Two known conditions occurring together are
      not a new condition; they are two known ones. Nothing is folded,
      because nothing new arrived.

      THE SIGNATURE STATE IS NOT DISCARDED, ONLY NOT JUDGED. It is
      printed as an observation in the unlevelled shape D308-1 fixes
      at :1079-1086, outside the token set and carrying no verdict.
      Both conditions project to rc 2 under D307-1:969-977, so the
      exit code is unaffected either way and this decision costs
      nothing at the shell.

    D310-2. THE CANONICAL FORM IS BLIND IN EXACTLY TWO PLACES, AND ONE
    OF THEM HAS NO TOKEN. The blindness is the fact; the missing token
    is its consequence. Recorded in that order so that a later seat
    does not find a third exit and start over.

      THE MECHANISM, READ AS BYTES. glm_manifest.py was read end to
      end on Server A in this session: 312 lines, 11192 bytes, sha
      92fb4ea1, MAXLEN 80. canonical_glm_bytes at :54-91 performs
      exactly two substitutions on the served text: the value under
      manifest_digest at :83 and the value under manifest_signature
      at :89. compute_glm_digest at :94-96 hashes that form. The
      substitution list is two entries long and both entries live
      inside one function, so the exits are enumerable rather than
      open-ended. A field added to that function later adds an exit,
      and this sentence says where to look.

      EXECUTED IN MEMORY ON SERVER A, NOT REASONED. The published
      manifest was read, its declared digest and its owner.version
      each occurring exactly once in the text, so both substitutions
      below were surgical.
        Baseline: the canonical digest equals the declared value,
        b73a0e2f, consistent with PUB_SEAL_OK at RULE 0.
        Mutating manifest_digest.value to 64 zeros: the canonical
        digest is UNCHANGED, digest_ok False, signature_present True,
        signer_pinned True, signature_ok False. A successor declaring
        b73a0e2f still matches the mutated bytes.
        CONTROL: mutating owner.version, a field the canonical form
        does not remove, CHANGES the canonical digest. The control
        fires, so the unchanged result above is not vacuous.

      THE TWO EXITS, AND NEITHER IS AS COVERED AS IT LOOKS.
        The signature value. Named by an existing token: a
        predecessor whose signature does not verify under the pinned
        allowlist is SIGNATURE_BAD by D307-1:949-953, whatever the
        reason. The fixture's SIGNATURE_BAD row is built with an
        EPHEMERAL key, so it exercises only the unpinned-signer
        variant. Measured: the only row in EXPECTED reaching
        signer_pinned True is VERIFIED, and no row carries
        signer_pinned True together with signature_ok False. The
        token covers this exit; the fixture exercises one half of it.
        The digest value. Not covered at all. digest_ok goes False
        while the link still matches, so the bond is intact and the
        object is defective. No token in the set names that.

      THE UNCOVERED EXIT IS NOT MERELY MISSING, AND THE CORRECTION TO
      A SHARPER CLAIM IS RECORDED RATHER THAN THE SHARPER CLAIM. It
      was put that the case falls into the existing SIGNATURE_BAD row
      under a wrong token. Measured against the full observation
      tuple, it does not: it differs from SIGNATURE_BAD at index 0,
      digest_ok, and index 2, signer_pinned, and it matches no row in
      EXPECTED exactly. It collides only under projection onto the
      signature legs alone, where present True with ok False maps to
      SIGNATURE_BAD and nothing else. The finding survives by a
      shorter route and lands harder: no row in EXPECTED carries
      digest_ok False at all, so the single authority for
      case-to-token is not wrong about this input, it is SILENT on
      it, and silence is what lets a classifier consulting the
      signature legs first emit SIGNATURE_BAD unchallenged.

      SELF_SEAL_BROKEN IS RECORDED AS THE NAME IT WOULD HAVE, AND IS
      NOT AUTHORISED. It reads with subject PREDECESSOR as the
      predecessor's own seal being broken while the bond holds, which
      is the fact rather than the mutation that exhibits it. Class
      CHECKED, WRONG; it would project to rc 2. The tool does not
      emit it. A tool cannot be the place a new classification first
      appears, because the fixture is the single authority for
      case-to-token and that authority is amended in its own gate,
      never inferred from code that shipped ahead of it.

      GAP 3, THE HALF-NULL SUCCESSOR, IS RECORDED HERE BEHIND THE SAME
      BLOCKER. D307-1:945-948 puts a successor with one link field
      null and the other not inside MALFORMED_LINK. The fixture's
      MALFORMED_LINK row carries a real URL with a malformed digest,
      and the observation tuple carries only the PRESENCE of
      supersedes, never its value, so no row exercises the half-null
      shape. The rule exists and the tool implements it; no test
      reaches it. It is not closed by writing a case into the tool's
      own tests, because that would create a second authority for
      case-to-token mapping and the fixture exists to be the only one.

    D310-3. digest_ok IS A PRECONDITION OF THE SIGNATURE LEGS, NOT AN
    OBSERVATION BESIDE THEM. This is the decision that lets the tool
    ship with eight tokens and no lie.

      THE TERM THAT WAS MISSING. manifest_digest.value is both the
      sealed field and the target of the signature: verify_glm_manifest
      checks the Ed25519 signature over bytes.fromhex(declared) at
      :262-265, where declared is that same field, read at :212-213 and
      compared at :219-220. When the field's own seal is broken, the
      signature target is not trusted, and therefore no signature check
      was performed at all, whatever the boolean returns. digest_ok is
      a precondition of interpreting the signature legs. It is not one
      more observation printed next to them.

      WHAT THE TOOL DOES.
        It does NOT claim it failed to identify the predecessor. It
        identified it: the link matched, compute_glm_digest returned
        the declared value, and that is the exact opposite of
        DIGEST_MISMATCH. A code path saying "not identified" where
        the measurement says identified would be a lie in the source,
        and the next seat reading it would find one.
        It does NOT claim a bad signature. None was checked.
        It prints the observation explicitly: link matched, self-seal
        broken, signature legs uninterpretable.
        It exits rc 3.

      rc 3 IS THE LITERAL READING, NOT AN EXTENSION. D307-1:954-964
      names the third class COULD NOT CHECK. Here the signature could
      not be checked. There is no negative verdict to report; there is
      a check that never ran. Reading rc 3 as covering this needs no
      widening of the definition, and D307-1:965-967 is not violated
      because no new condition is folded into an existing token: an
      unsatisfied precondition is what COULD NOT CHECK describes.

      THE DIFFERENCE FROM UNREADABLE, STATED BEFORE ANYONE MERGES
      THEM. UNREADABLE is bytes that are not a digest-computable
      manifest. These bytes are digest-computable; the execution above
      computed their digest. Two different reasons to be unable to
      check, one class, one exit code, two different printed messages.
      A later seat that collapses them loses the distinction between
      "I could not read this" and "I read it and its own seal is
      broken".

      THE COST, WRITTEN AS A COST AND NOT AS A DESIGN WIN. rc 3 says
      the tool could not check. It does not say the predecessor's seal
      is broken. The shape is fail-closed and it is lossy: the printed
      observation carries the fact, the exit code does not, and a
      reader inspecting only $? learns less here than the tool knows.
      That is the same shape as the standing F1 finding and it is
      accepted here rather than hidden.

      THE DEBT, NUMBERED. No row in EXPECTED carries digest_ok False,
      measured. So no test locks the path this decision defines, and
      the tool will ship with a route the single authority does not
      touch. That is owed, not resolved.

      ONE AUTHORISATION IS REQUESTED, WITH FOUR REASONS, IN A GATE OF
      ITS OWN AFTER THE TOOL. The fixture file is frozen: D308-2
      released a single write under tests/ at :1210-1213 and that
      release is spent. Amending it needs a new operator decision.
      The four reasons travel together because they are one edit.
        A ninth token, SELF_SEAL_BROKEN, with its row.
        A half-null successor row for MALFORMED_LINK, Gap 3.
        A row carrying digest_ok False, so the precondition path
        defined here is locked by the authority rather than by the
        tool's own tests.
        A row where a PINNED signer's signature does not verify, so
        the second variant of SIGNATURE_BAD is exercised and the
        token stops resting on one half of its own definition.

      WHY THE FIXTURE CANNOT BE AMENDED QUIETLY. TOKENS is defined at
      :49-58 of tests/test_s309_supersession_cases.py, TABLE at :61-70
      and EXPECTED at :75-89, and the completeness test at :226-231
      compares set(TABLE) against set(TOKENS) and set(EXPECTED) union
      UNREACHABLE against set(TOKENS). Both operands of both
      assertions are module-level names in that same file: the test is
      closed over the fixture and compares the file against itself. A
      ninth token added inside the file needs three edits. A ninth
      token added outside it is invisible to that test. Censused with
      the pathspec declared before counting: the fixture is the only
      file under tests/*.py defining TOKENS and the only file in the
      tree referencing the module, its own marker at :18 being the
      single hit.

    F310-2, RECORDED WITHOUT ACTION. D308-3:1188-1194 names three
    reachable raise sites -- json.loads inside verify_glm_manifest at
    :196-198, _block_value at :50 and _require_single at :39-42 -- and
    concludes that one except clause suffices. The module carries nine
    raise statements, all GlmManifestError. The tool calls
    compute_glm_digest directly on fetched bytes, unwrapped, and that
    call reaches :39, :50, :68, :72 and :76: two of the three named,
    plus three that are not named, because verify_glm_manifest catches
    its own internal compute at :226 while the tool's call is not
    caught. The third named site is reached only through the tool's
    separate verify call, which also reaches :200. The conclusion
    survives by shared exception type, not by the enumeration that was
    given. A future raise of a different type inside that path breaks
    it silently, and the enumeration would not warn.

    PROVENANCE OF THE MEASUREMENTS IN THIS ENTRY. The module read, the
    two censuses, the occurrence counts, the four booleans, the link
    consequence and the control were printed by read-only gates on
    Server A in this session. The fixture line numbers and its sha,
    339 lines and 12245 bytes, were printed by a read-only gate on
    Server A. The tuple comparisons behind the correction in D310-2 --
    the differing indices and the emptiness of the digest_ok False row
    set -- were executed in the seat's container over the table as read
    on Server A, and NOT on Server A. They will be re-executed there
    when the tool's tests run, and will fail there if wrong.

    ERRORS NAMED IN THIS GATE. Six instrument defects in one family,
    all the seat's own: a regex anchored without multiline, a count
    over a block boundary never delimited, a relational prediction fed
    to an equality comparator, a line number derived by proximity from
    a file not opened, a census over a pathspec that swept documents
    while the prediction spoke of code, and a census for external
    references that did not exclude its own subject. FG-S310-H is the
    one that changes a rule: a census for external references excludes
    the subject IN THE PATHSPEC, not in the reader's head, and the
    prediction is phrased over the set the instrument actually scans.
    Separately, a paste was verified in the seat's container and then
    retyped into the message rather than emitted from the verified
    file, so the syntax check attached to an artifact that was never
    run; every paste after it was round-tripped against its file
    before being sent. And a draft of this entry asserted that the
    signature exit was covered by the fixture without checking which
    variant that row builds, in an entry whose subject is the
    fixture's silence. It was caught by reading the decoded payload
    in the transfer gate, before the append gate, which is the reason
    the decoded text is printed there and not after the write.

    AUTHORISES NOTHING NEW. No file is created, no test is changed, no
    source is edited, no manifest is touched and no dependency is
    declared. The ninth token is proposed and not authorised, and the
    tool does not emit it. The ceremony change (b) remains
    unauthorised and nothing recorded here makes it more likely.
    Section 12 stands unchanged and this entry does not widen it.
    Sequence: this entry first, then the tool, then the tool's tests,
    then the fixture amendment if the operator authorises it, in
    separate gates.

  - S310. THE FETCH SEAM DIVERGES FROM THE ONE IN THE TREE AT FIVE
    POINTS, RECORDED AS D310-4. The tool fetches with httpx. Four
    scripts were read end to end before this was written, and every
    divergence below carries the measurement that produced it. This
    entry precedes the tool because a design that departs from an
    existing seam is a decision, not a comment inside the code that
    departs.

    THE SEAM THAT EXISTS, READ AS BYTES. scripts/cold_audit.py, sha
    ddfb20c7, 460 lines, 16049 bytes, MAXLEN 82. It fetches by
    shelling out: _fetch at :109-130 and _http_status at :133-151,
    both subprocess.run over curl. The census, pathspec scripts/*.py
    declared before counting: curl one member, wget one member, both
    cold_audit; a top-level httpx import one member,
    capture_phala_receipt. Under that pathspec, and across the probes
    curl, wget, subprocess, a top-level httpx import, urllib and
    requests, two fetch implementations exist and no third. Nothing
    outside scripts/*.py was censused and this sentence claims
    nothing about it.

    THE CLIENT. httpx, and the reason is the reason cold_audit gives
    for curl, read back the other way.
      THE STATED REASON DOES NOT TRANSFER. cold_audit:15-21 shells to
      curl BECAUSE THE PUBLISHED DOCUMENT SAYS curl: a fetch by a
      different client is a different input, and a check whose input
      differs from the consumer's is not a check of what the consumer
      holds. That argument binds a checker to a documented consumer
      procedure. This tool's input is a URL taken from a successor's
      supersedes field. No published procedure tells anyone to fetch
      a GLM manifest, and so there is no consumer input to match.
      Copying the shape without the reason would be imitation, not
      composition.
      curl IS UNDECLARED AND THE TREE ALREADY PAYS FOR IT.
      cold_audit:379-385 probes for curl on PATH and exits 2 when it
      is absent. httpx is a declared runtime dependency at
      pyproject.toml:30, inside the dependencies array at :27-34 and
      above the optional-dependencies table at :36, so pip install
      nous-lang supplies it and a plain checkout does not have to
      hope.
      THE STDLIB ALTERNATIVE IS ALREADY EXCLUDED ON OUR OWN SURFACE.
      cold_audit:19 records that nous-lang.org, behind Cloudflare,
      403s the Python-urllib user-agent while serving curl, requests,
      httpx and wget normally, and that a first draft using urllib
      failed 4/4 against a healthy surface. The choice was never
      three-way. It was curl or httpx, and one of the two is
      declared.

    DIVERGENCE 1, THE CAP. The tool refuses a body over 1 MiB and
    emits UNREACHABLE. It never truncates.
      MEASURED EMPTY, ZERO OF TWO. Neither fetcher caps. There is no
      --max-filesize at cold_audit:111 and no size bound in
      capture_phala_receipt:83. This is the first seam of its kind in
      this tree, stated as a measured zero rather than as an absence
      recalled.
      WHY REFUSAL AND NOT TRUNCATION. Truncated bytes are still
      bytes. They would reach compute_glm_digest, hash to something
      other than the declared supersedes_digest, and return
      DIGEST_MISMATCH: a verdict about content for a fault in
      transport. The tool would assert that the predecessor changed
      when it merely failed to arrive whole. That is the worst error
      available to it and the cap exists to make it unreachable.
      WHY THE CAP IS NOT DELEGATED. curl --max-filesize was NOT
      measured by this seat, and whether it refuses rather than
      truncates when Content-Length is absent is unknown here.
      Delegating the contract to unmeasured behaviour in another
      program is not a control. With httpx.stream the count is the
      tool's own: bytes are summed as they arrive and the excess
      raises rather than returns, so the refusal is expressible in
      code this repository owns.
      THE NUMBER AND ITS REASON. RULE 0 measured the two served
      manifests at 10673 and 10250 bytes. 1 MiB is roughly a
      hundredfold headroom over the observed maximum and is still
      trivial to hold in memory. It bounds a hostile or broken
      response without coming near a real one.

    DIVERGENCE 2, REDIRECTS. follow_redirects is False and a 3xx is
    UNREACHABLE.
      THE EXISTING SEAM FOLLOWS THEM. cold_audit:111 passes
      curl -fsSL; the L is follow. This tool does the opposite and
      the reason is the link, not a preference. A supersedes value is
      a URL by construction: the ceremony writes it from
      --supersedes-url at sign_glm_manifest:368-370 into the
      successor at :162. It names where the bytes are. A 3xx ending
      elsewhere delivers a different document, not the same document
      at another address. ADR-0011 is cited here only as its commit
      subject at 84ca0b9 states it, that a supersedes link commits to
      published bytes; the file has not been opened by this seat and
      nothing finer is claimed from it.
      D307-1:955-957 ALREADY SAYS SO. A redirect ending elsewhere is
      inside UNREACHABLE by definition. This divergence implements a
      mapping that was already fixed; it does not widen it. With
      follow_redirects False the 3xx is visible as a status and can
      be mapped. Dropping the L from a curl invocation yields a
      behaviour this seat has not measured, which is a second reason
      the client choice and the redirect choice are one decision.

    DIVERGENCE 3, THE TIMEOUT, WHICH IS A CONVERGENCE IN INTENT AND A
    DIVERGENCE IN MECHANISM. A timeout is the other half of
    UNREACHABLE: without one the tool hangs where it owes a token.
      TWO VALUES ARE MEASURED AND THEY MEASURE DIFFERENT THINGS.
      cold_audit:114 and :138 pass timeout=120 to subprocess.run,
      which bounds the wall clock of an entire child process
      including curl startup. capture_phala_receipt:83 passes
      timeout=60.0 to httpx.Client, which bounds connect, read,
      write and pool. The 120 is not the comparable number and does
      not transfer as a number.
      THE TOOL TAKES THE httpx PRECEDENT. 60.0 in the scalar form,
      because capture_phala_receipt:83 is the only httpx timeout in
      this tree and the scalar is the form it uses. Expiry maps to
      UNREACHABLE, in the same class as a connection failure, since
      in both the predecessor was not obtained.

    DIVERGENCE 4, THE EXIT CODE. rc 3 shares its meaning with
    neither shipped tool, and that is why it was chosen.
      MEASURED ON BOTH FILES D307-1 NAMES. served_mirror_check.py,
      sha ac330dfa, 130 lines: rc 1 for drift at :123, rc 2 for
      FAILED MEASUREMENT at :76, :79, :99 and :105, rc 0 clean at
      :126. cold_audit.py: rc 1 for at least one failed class at
      :408 and :456, rc 2 for usage or environment error at :385 and
      :392, per its own docstring at :37-39. So rc 2 means failed
      measurement in one and usage error in the other. The inherited
      reading of D307-1:896-901 is discharged against bytes.
      rc 3 INHERITS NEITHER MEANING, which is the whole point:
      COULD NOT CHECK gets a code it does not share with a
      judgement. D307-1:989-992 already records that the residual
      difference between these tools is recorded rather than
      resolved, and this entry does not resolve it either.

    DIVERGENCE 5, THE INPUT SHAPE, STATED SO THAT UNREACHABLE IS
    NEVER AMBIGUOUS.
      The successor is operator input. The predecessor is what the
      tool retrieves from that successor's supersedes field. The
      tool performs exactly one fetch and it is always the
      predecessor.
      Therefore UNREACHABLE always names the predecessor. Its
      subject is PREDECESSOR under D309-2:1366-1372, and a tool that
      fetched both ends would make the token ambiguous about which
      end failed. D309-2:1440-1445 already forbids the tool from
      verifying the successor, on the ground that a second oracle
      over one artifact adds fragility where one already governs;
      one fetch is the same rule applied to transport.

    WHAT DOES NOT DIVERGE, RECORDED SO IT IS NOT RE-DECIDED.
      TRANSPORT FAILURE IS AN EXCEPTION, NEVER A VERDICT.
      cold_audit:116-120 raises on a non-zero curl exit and
      :140-145 calls an incomplete curl INCONCLUSIVE in as many
      words. That is UNREACHABLE, and the tool composes it.
      A 200 IS NOT EVIDENCE A FILE EXISTS. cold_audit:123-130 reads
      the first 512 bytes and rejects an HTML page served by an SPA
      fallback. This tool needs no sentinel: the same input reaches
      glm_manifest.py:196-198 and raises GlmManifestError, which is
      UNREADABLE by D307-1:958-964. Same hazard, same class, one
      fewer mechanism.
      THE EXIT SHAPE. Four scripts read end to end now agree:
      main() returns int and the module ends in
      raise SystemExit(main()), at cold_audit:460,
      served_mirror_check:130, sign_glm_manifest:392 and
      capture_phala_receipt:167.

    A CONTROL THAT GOES GREEN WHEN THE NETWORK IS DOWN IS NOT A
    CONTROL. cold_audit:154-184 refuses to audit anything unless the
    surface first answers 404 for a version that cannot exist, and
    treats anything that is neither 404 nor 200 as INCONCLUSIVE. The
    tool inherits the principle rather than the preflight: every
    failure to obtain the predecessor lands in COULD NOT CHECK and
    none of them lands in rc 0. Nothing in the fetch path may reach
    a passing token by failing.

    ERRORS NAMED IN THIS GATE. The seat wrote that the fetch layer
    had no in-tree precedent while holding the measurement that
    filled the gap: cold_audit:19-21 had been quoted in this same
    session, from a file carrying curl, wget and subprocess, unread.
    That is the FG-S309-A class with the evidence already in hand
    rather than merely unfetched. Separately, the seat enumerated
    four design points and omitted the timeout, which is the only
    mechanism the existing seam actually implements and half of what
    UNREACHABLE means. Both were caught by the operator, not by the
    seat, which is where they are recorded.

    AUTHORISES NOTHING NEW. No file is created, no test is changed,
    no source is edited, no manifest is touched and no dependency is
    declared: httpx is already declared at pyproject.toml:30 and this
    entry adds nothing to that line. The ninth token remains proposed
    and unauthorised and the tool does not emit it. The fixture file
    remains frozen and the four-reason amendment requested in the
    previous entry remains unauthorised. The ceremony change (b)
    remains unauthorised. Section 12 stands unchanged and this entry
    does not widen it. Sequence: this entry first, then the tool,
    then the tool's tests, in separate gates.

  - S310. WHERE THE TOKEN NAMES LIVE, AND THREE CONSTRAINTS ON THE
    TOOL'S SURFACE, RECORDED AS D310-5. Four decisions, none of them
    adding a token. Written before the tool because each one would
    otherwise be settled inside the code, where a later seat reads it
    as an implementation detail rather than as a choice.

    D310-5(a). THE VERDICT LINE ALWAYS CARRIES A NAME, AND WHERE NO
    TOKEN APPLIES THE NAME IS UNCLASSIFIED.
      THE PROPOSAL THIS REPLACES, AND WHY IT WAS WRONG. The seat
      proposed printing VERDICT with no value on the path D310-3
      defines, on the ground that no token in the set covers it. An
      empty field forces every reader, every grep and every CI leg to
      answer whether the value is absent or empty. That is the
      dict.get() defect, recorded in this ledger at :1112-1115 and
      again at :1290-1297, rebuilt in the output stream instead of in
      a dictionary lookup. A tool whose subject is the difference
      between absent and null must not emit a field that confuses
      them.
      UNCLASSIFIED IS NOT A TOKEN AND DOES NOT ENTER TOKENS. It is
      not a verdict, it describes no state of the link, and it takes
      no row in the fixture table. It is the ABSENCE of a verdict
      given a name, so that the absence is a value rather than a
      blank.
      D307-1:965-967 IS NOT VIOLATED. That rule forbids folding a new
      condition into an existing token. Nothing is folded here: the
      condition is stated as uncovered, at the point of printing, and
      the eight tokens are untouched.
      THE SHAPE IS ALREADY STANDARDISED AND ALREADY CITED. SARIF
      2.1.0 separates result.kind from result.level and carries
      notApplicable as a declared kind rather than as a missing
      field: a result that is not a judgement still has a name.
      D308-1:1079-1086 already invokes that separation for the
      unlevelled observations. This is the same shape applied to the
      verdict line.
      THE REST OF THE CONTRACT IS UNCHANGED. rc 3 still means COULD
      NOT CHECK under D307-1:954-964 and the projection at :969-977
      is untouched. SELF_SEAL_BROKEN remains proposed and
      unauthorised: it is the name the condition would take if the
      operator extended the set, and UNCLASSIFIED is what the tool
      prints while it has not been extended.

    D310-5(b). THE EIGHT NAMES LIVE IN BOTH THE TOOL AND THE FIXTURE,
    AND A TEST ASSERTS THEY MATCH.
      TWO OBVIOUS ROUTES WERE REJECTED, EACH FOR A MEASURED REASON.
        THE TOOL DEFINES ITS OWN LIST AND NOTHING CHECKS IT. That
        creates a second authority for the token set. The fixture is
        the sole definer of TOKENS at :49-58 of
        tests/test_s309_supersession_cases.py and the sole file
        referencing that module, both censused with the pathspec
        declared before counting. A second list would end that, and
        D309-3:1530-1536 turned the completeness test into a set
        equality precisely so that a token with no row, or a row with
        no token, keeps being reported.
        THE TOOL IMPORTS THE NAMES FROM THE FIXTURE. That makes
        production code depend on tests/, which inverts the
        dependency and does not survive packaging: scripts/ is not
        shipped and tests/ is not shipped, so an installed consumer
        would hold neither.
      THE THIRD ROUTE, WHICH CREATES NEITHER. The tool carries the
      eight names. The fixture carries them too, as it already does.
      The tool's own tests import both and assert set equality. No
      second authority is created because the fixture remains
      authoritative: if the two disagree the TOOL is wrong, per the
      operator's standing instruction, and the assertion reddens on
      the tool's side. No inverted dependency is created because
      nothing under scripts/ imports anything under tests/.
      ONE MECHANISM IS UNMEASURED AND IS NOT DECIDED HERE. Whether a
      test module in this repository can import a sibling test module
      has not been measured by this seat: no census was run for an
      __init__.py under tests/, for a conftest, or for the import
      mode in effect. That measurement belongs to the tool's test
      gate. If the import is not available the equality assertion
      cannot be written as described, and the decision returns to the
      operator rather than being resolved in code.

    D310-5(c). --successor TAKES A PATH AND REFUSES A URL BEFORE ANY
    FETCH. The successor is operator input and is read from disk;
    D310-4 fixed that the tool performs exactly one fetch and that it
    is always the predecessor.
      WHY A REFUSAL AND NOT A FAILURE. Without an explicit check the
      first person who passes a URL receives a file-not-found error
      naming a path that looks like a URL. That reports the symptom
      and hides the interface. The tool checks first and says which
      argument takes which kind of value.
      IT COMPOSES THE EXISTING URL SEAM. sign_glm_manifest:286-297
      lazily imports urlsplit, extracts the netloc, tests membership
      against a pinned set, writes to stderr and returns fail-closed.
      The same shape applies here: if urlsplit reports a scheme, the
      value is a URL, the tool refuses and no read and no fetch
      happens.

    D310-5(d). MAXLEN IS 80, NOT A BAND. The seat wrote "the 82-90
    band", which is a range and not a decision; a range in a design
    becomes drift in the next file.
      MEASURED. glm_manifest.py is 80 and
      tests/test_s309_supersession_cases.py is 80: the two files this
      tool is closest to in subject. Under scripts/ the hand-written
      maxima are cold_audit 82, publish_verifier_registry 85,
      sign_glm_manifest 86, capture_phala_receipt 88, claim_lint 90
      and served_mirror_check 96, with release and one patch file far
      above as generated payloads.
      SO 80 IS STRICTER THAN EVERY FILE UNDER scripts/ AND EQUAL TO
      THE TWO IT COMPOSES FROM. That is the reason, and it is stated
      so that a later seat widening it has to overrule a measurement
      rather than a habit. ASCII only, no tabs, no trailing
      whitespace, and mode 100644, which IS uniform: every file
      censused under scripts/*.py is 100644 and none is executable.
      THE SHEBANG IS NOT UNIFORM AND IS THEREFORE A CHOICE, NOT A
      CONVENTION. capture_phala_receipt, publish_verifier_registry
      and sign_glm_manifest carry none; cold_audit, claim_lint,
      release and one patch file carry one. The tool carries none,
      following the three that are nearest it in subject, and every
      invocation in this session went through python3 with an
      explicit path rather than through an executable bit.

    ERRORS NAMED IN THIS GATE. The seat proposed an empty VERDICT
    field, which is the dict.get() failure this ledger has recorded
    twice, moved from a lookup into the printed output. It also
    offered a MAXLEN range where a value was owed. Both were caught
    by the operator. The first is the more serious: the tool's whole
    subject is the difference between a missing thing and a null
    thing, and the seat proposed to emit that ambiguity on the line
    an auditor reads first.

    PROVENANCE. The two MAXLEN 80 values and every scripts/ maximum
    were printed by read-only gates on Server A in this session, as
    were the two censuses behind the sole-definer statement. Nothing
    in this entry was executed in the seat's container. The claim
    about pytest importing a sibling test module is explicitly NOT
    made; it is named as unmeasured above.

    AUTHORISES NOTHING NEW. No file is created, no test is changed,
    no source is edited, no manifest is touched and no dependency is
    declared. UNCLASSIFIED is a printed value and not a token; TOKENS
    remains eight. SELF_SEAL_BROKEN remains proposed and
    unauthorised. The fixture file remains frozen and the four-reason
    amendment requested earlier in this session remains unauthorised.
    The ceremony change (b) remains unauthorised. Section 12 stands
    unchanged and this entry does not widen it. Sequence: this entry
    first, then the tool, then the tool's tests, in separate gates.

  - S311. THE IMPORT MECHANISM D310-5(b) LEFT OPEN IS MEASURED, AND
    THE RECORDED FIX FOR FG-S310-L IS DEFECTIVE IN BOTH OF ITS
    HALVES, RECORDED AS D311-1 AND D311-2. The correction is owed as
    an entry of its own and not as ceremony. The code that follows
    will diverge from the recipe recorded at the close of S310; if
    the divergence and the correction arrive in one commit then the
    code is the source of the correction and this ledger is its
    annex. The previous entry ends by ordering an entry before the
    code it governs, at :2181-2182, and this one keeps that order.

    D311-1. THE MECHANISM LEFT OPEN AT :2109-2116 IS MEASURED, AND IT
    HAS TWO SIDES RATHER THAN ONE. D310-5(b) named one unmeasured
    mechanism. The equality it specifies has two operands and they
    are not reached the same way, so the open question was answered
    twice.
      THE SIBLING SIDE IS AVAILABLE AND IS ALREADY IN USE. Ten
      tracked files under tests/ carry fifteen import lines of the
      form "from test_NAME import ...", with the pathspec tests/*.py
      declared before counting, and the suite is green at 2825
      passed. The property is executed in the tree, not inferred.
      THE MECHANISM IS NOT THE CONFTEST. tests/conftest.py is the
      only conftest in the tree and it was read end to end, 43 lines:
      it carries a collect_ignore list and a --run-live option and it
      does not touch sys.path. There is no tests/__init__.py and
      pyproject declares no import mode. What remains is pytest's own
      path insertion, and that is stated here as a conclusion by
      elimination and not as a measurement.
      THE TOOL SIDE IS NOT AN IMPORT AT ALL. scripts/ is not a
      package: no scripts/__init__.py exists, packages is
      ["templates"] at pyproject:53, and the py-modules list at
      pyproject:55-146 names top-level modules only. Two test
      docstrings already say so in the tree's own words, at
      tests/test_s159_u2_release_provenance.py:3 and at
      tests/test_s297_glm_ceremony.py:4.
      THE FILE-PATH IDIOM IS ALREADY IN THE TREE FOUR TIMES. It
      resolves the repository root from __file__, builds a spec with
      importlib.util.spec_from_file_location under a module name
      local to the test, and executes it. The matched lines are
      test_s159_u2_release_provenance:20,24,27,28,
      test_s236_claim_lint:30,37,38,40,
      test_s297_glm_ceremony:23,30,32,33 and
      test_s298_glm_ceremony_guards:30,41,43,44;
      spec_from_file_location appears on 26 lines of tests/*.py. Only
      the third was also read as contiguous text. The tool's tests
      compose that seam and add no route.
      LOADING scripts/check_glm_supersession.py RUNS NOTHING. Its
      entry point is guarded at :294 and its module body from :45 to
      :291 is imports, constants, two exception classes and five
      functions, so exec_module binds names and has no other effect.
      THE TWO OPERANDS AGREE TODAY, WHICH IS NOT A REASON TO OMIT THE
      ASSERTION. TOKENS at :56-65 of the tool and TOKENS at :49-58 of
      the fixture carry the same eight names. The fixture already
      closes its own set against its table at :230-231. What no file
      holds is the equality ACROSS the two, which is the assertion
      D310-5(b) specifies and the reason it specified it.

    D311-2(a). THE PADDING HALF OF THE RECORDED FIX REPRODUCES THE
    DEFECT IT REPLACES. FG-S310-L was recorded at the close of S310,
    in the session handoff and not in this repository, as: padding
    derived from the label set, so that no constant can go stale. The
    label set was then extracted from the tool by walking its syntax
    tree rather than by reading it off the page: thirteen _print call
    sites, thirteen distinct labels, every one a literal, longest 18.
    The two labels that render with no separator, pred.signer_pinned
    and pred.owner.version, ARE the two longest. A width derived as
    the maximum of the set is therefore 18, which is the shipped
    constant at :193 character for character. The recorded fix and
    the defect it replaces are the same line.
      MEASURED OVER ALL FOUR CANDIDATE RENDERERS. Against the
      thirteen labels, counting those whose rendered line does not
      split into two whitespace-separated fields: the shipped
      ljust(18) fails 2; ljust(20) fails 0 today and fails at the
      first label of 20 characters, which is why it was rejected;
      padding derived from the set fails the SAME 2; derived padding
      followed by an explicit separator fails 0.
      WHERE THIS WAS EXECUTED. The tool was reconstructed byte for
      byte in the seat's container and its sha256 matched Server A at
      03c2af4a before anything ran against it. The extraction and the
      four renderer runs happened there. Nothing was written to
      Server A.

    D311-2(b). THE CONTROL HALF CANNOT FIRE ON THE CASE IT WAS
    WRITTEN FOR, AND IT IS THE WORSE OF THE TWO DEFECTS. The recorded
    control reads: a test asserting every emitted line splits into
    two or more whitespace-separated fields. Driven over the output
    of one execution it never reaches the failing labels. Both are
    pred.* and both are emitted only inside the branch at :276-281,
    which runs only when a predecessor was obtained, which requires a
    fetch. A hermetic run emits neither. The control would pass green
    while the defect stood. A control that cannot fire on the case
    that motivated it is not a control, and this is the standing rule
    that a negative control must be structurally capable of firing,
    met on the positive side.

    D311-2(c). THE FIX, STATED SO THAT IT CANNOT BE READ AS ONE
    THING. Padding is alignment. The separator is the invariant. They
    are not the same concern, and the recorded fix named only the
    first, which is how a derived width could be written down as a
    repair while being identical to the defect. The renderer pads to
    a width derived from the label set AND emits a separator that
    does not depend on that width. The control is driven over the
    label set, not over the output of one execution, so that every
    label is rendered and asserted whether or not any run emits it.

    D311-2(d). THE NAMED LABEL SET IS SURFACE, AND THE DISTANCE IS
    THE FINDING. The control in (c) cannot enumerate what to assert
    unless the labels exist as an object. Today they are thirteen
    literals at thirteen call sites, and the enumeration in (a) was a
    syntax-tree walk, which is available to a reader and not to a
    test. So the repair adds a named constant to a shipped file,
    derives the width from it, adds a separator, and adds a test
    driven over it. FG-S310-L began as one character and ends as four
    things, one of which widens the tool's surface. The distance
    between the two is the finding, and it is the reason a fix
    without a control is not a fix.

    ERRORS NAMED IN THIS GATE. FG-S311-A: the seat observed that the
    end-to-end route cannot reach the two failing labels, wrote that
    observation and the recorded control in the same message, and
    drew no line between them; the observation defeats the control
    and the seat did not say so. The operator connected them. It is
    the family of FG-S310-I, a measurement held while the claim it
    defeats stands unaltered. FG-S311-B: the seat proposed to carry
    the correction of the recipe and the code diverging from it in
    one gate, on the authority of this session's opener; the operator
    cut it, on the ground that the code would then be the source of
    the correction.

    PROVENANCE. The census figures, the file-path idiom lines, the
    conftest read, the guard at :294, the two TOKENS blocks and the
    absence of any reference to this tool elsewhere in the tree were
    printed by read-only gates on Server A in this session. The
    thirteen labels, the four renderer runs and the failure counts
    were produced in the seat's container against a reconstruction of
    the tool whose sha256 matched Server A before use.
    tests/test_s297_glm_ceremony.py was read only to :70 of 174 and
    no claim here rests on the remainder. The sibling-import
    mechanism is a conclusion by elimination and is labelled as such
    above.

    AUTHORISES NO NEW SCOPE. No token is added and TOKENS remains
    eight. UNCLASSIFIED remains a printed value and not a token.
    SELF_SEAL_BROKEN remains proposed and unauthorised. The fixture
    file remains frozen and the amendment requested in the previous
    entries remains unauthorised. The ceremony change (b) remains
    unauthorised. Nothing here amends an earlier section; it corrects
    a fix that was recorded outside this document. The edit to the
    shipped tool described in (c) and (d) is the repair of FG-S310-L
    and nothing else: no verdict, no exit code and no field changes.
    Sequence: this entry first, then ONE code gate carrying the
    tool's tests and the repair together, because the convention
    separates documents from code and not tests from tests.

  - S311. THE FIXTURE AMENDMENT IS THREE DECISIONS AND ONE OF THEM IS
    A CLOSED BOUNDARY, RECORDED AS D311-3. This entry REPLACES the
    five-reason list carried in the S310 handoff and restated in the
    S311 opener. That list read as one request; the fixture read end
    to end shows it is three, and its strongest member is not a
    request at all. The list is superseded here so that a later seat
    reading the opener finds the replacement named.

    D311-3(a). THE FOURTH AND FIFTH REASONS ARE ONE, AND IT IS A
    BOUNDARY AND NOT A GAP. The fourth asked for a row where a PINNED
    signer's signature fails to verify. The fifth said the fixture
    holds no predecessor signed by the pinned key. They are not two
    items: the second is the mechanism of the first.
      IMPOSSIBLE, AND PROVED FROM HERMETICITY RATHER THAN FROM
      ABSENCE. The only private key in the file is
      Ed25519PrivateKey.generate() at :136, which is ephemeral by
      construction. The docstring states no private key at :14. The
      file names the consequence itself at :330-331: VERIFIED is not
      constructible under the default allowlist, so it is read.
      TAMPERING WITH THE READ MANIFEST DOES NOT REACH IT EITHER.
      Altering the published bytes breaks digest_ok first, and
      digest_ok is a PRECONDITION of the signature legs under D310-3,
      so the branch returns UNCLASSIFIED and never SIGNATURE_BAD. The
      route is closed at both ends.
      THE VALUE IS NOT THAT ONE REASON LEAVES THE LIST. It is that
      this names a limit the fixture inherits from its own founding
      property. The fixture is hermetic; therefore it can never
      construct anything that requires the operator key. That is a
      CLOSED SET of what it can cover, not a defect awaiting repair,
      and the coverage debt stops waiting for something that is not
      coming.

    D311-3(b). THE SECOND, THIRD AND SIXTH REASONS NEED A
    RESTRUCTURING AND NOT AN AMENDMENT, AND IT IS NOT AUTHORISED
    HERE. Each asks for a case whose token ALREADY HAS A ROW.
      THE UNIT OF THE FIXTURE IS THE TOKEN. TABLE at :61-70 is
      token -> (subject, provenance), one row per token, and
      test_the_table_carries_one_row_per_token at :230 asserts
      set(TABLE) == set(TOKENS). D309-3 chose that shape.
      SO THESE ARE NOT NEW ROWS. A half-null link in either direction
      is a second MALFORMED_LINK; an uppercase digest is a second
      DIGEST_ONLY. Expressing them means moving the unit from the
      token to the case, which revokes D309-3.
      THE CONDITION IF IT IS EVER DONE. Under a case-keyed table the
      completeness check becomes at-least-one-case-per-token. A token
      with zero cases still cannot exist, but a token with WRONG
      cases passes exactly as before, so a set equality would decay
      into a coverage check. The equality must be KEPT AS ITS OWN
      ASSERTION alongside the coverage one: two checks, not one
      weakened. tests/test_s311_supersession_tool.py imports TOKENS
      for the tool-side equality and survives either shape, but the
      structure underneath it would have changed.
      THIS IS A CONDITION ON A FUTURE INNOVATION GATE AND NOT A
      PROHIBITION.

    D311-3(c). THE NINTH TOKEN IS UNCHANGED BY THIS ENTRY. The first
    reason asked for SELF_SEAL_BROKEN with its row. That is not a
    fixture amendment; it is an amendment of the token set, left
    PROPOSED and UNAUTHORISED by D310-2, and nothing since has
    changed it. SELF_SEAL appears zero times in the fixture, censused
    over that file.
      IT NOW COSTS MORE THAN IT DID. Before f3e34e1 the eight names
      lived in two files. That commit added a test asserting the two
      agree, so a ninth token is one atomic change across the tool,
      the fixture and the equality test, and the S311 opener forbids
      editing the fixture inside the tool's gate. It requires a new
      arc, not an addition.
      UNCLASSIFIED CARRIES THE CONDITION MEANWHILE. It is fail-closed
      at rc 3, it loses the distinction between a broken seal and the
      other uncovered conditions, and that loss is written here as a
      cost rather than left as a silence.

    D311-3(d). THE DEBT, COUNTED FROM THE FIXTURE BYTES AND NOT FROM
    A PRIOR. Five absences were measured directly in this session by
    reading the file end to end:
      1. a half-null link with the URL present and the digest null.
      2. a half-null link with the URL null and the digest HEX64.
         Neither exists: the only malformed row is successor(
         "not-a-digest") at :154, which carries both ends.
      3. digest_ok False. Column 0 of EXPECTED at :75-89 holds None,
         None, True, True, True, _RAISED and True. There is no False,
         so the D310-3 precondition path is locked by nothing.
      4. an uppercase digest. Every declared digest is the output of
         compute_glm_digest, which the fixture never re-cases.
      5. a successor carrying neither link key. _doc at :105-106 sets
         both on every document the fixture builds.
    TWO OF THE FIVE NEED MORE THAN D311-3(b) GIVES. Items 3 and 5
    both classify as UNCLASSIFIED, at :117-118 and :141-142 of the
    tool. UNCLASSIFIED is a printed value and NOT a token under
    D310-5(a), and TABLE is keyed by token, so no case-keyed table
    reaches them either. They need a table that can carry a row for a
    named non-verdict, which is a third shape and is not proposed
    here.
    THE TOTAL IS NOT RESTATED. The enumeration of uncovered tool
    behaviours stands where S310 left it, at eight measured by the
    seat and seven by the operator. This session did not re-execute
    it and does not adjudicate it.

    ERRORS NAMED IN THIS GATE. FG-S311-J: the seat carried the
    five-reason list through four sessions and presented it as a
    single pending amendment without having read the file it was
    about. Three of the five were assertions of absence, which is the
    project's recurring failure, and the strongest member was not a
    request but a proof. The reading took one gate and should have
    preceded the list.

    PROVENANCE. Every line number here was printed by a read of
    tests/test_s309_supersession_cases.py end to end on Server A in
    this session, at sha 34b3557c, 339 lines, MAXLEN 80. The tool
    line numbers are from the read of scripts/check_glm_supersession
    .py in the same session at sha 03c2af4a, before it was patched.
    The SELF_SEAL count is a census over the fixture alone with the
    pathspec stated.

    AUTHORISES NOTHING. No file is changed. The fixture remains
    frozen and unamended. No token is added and TOKENS remains eight.
    SELF_SEAL_BROKEN remains proposed and unauthorised. The ceremony
    change (b) remains unauthorised. D309-3 stands. The restructuring
    in (b) and the ninth token in (c) each require their own decision
    and their own gate, and neither is taken here.

  - S313. THE ONLY AUTOMATED CLAIM GUARD IS SINGLE-AXIS, AND THE SET IT
    SCANS IS THE WORKING DIRECTORY AND NOT THE REPOSITORY

    Read-only session. ZERO WRITES to the tree, to origin or to any
    served surface before this entry. RULE 0 reproduced every row of the
    S313 opener with no drift. scripts/claim_lint.py was NOT opened. The
    reading was claims.toml sha f9919834 end to end, the tool's --help,
    and the tool's own output under five roots.

    D313-1  HOW claim_lint DECIDES A VIOLATION, AND WHY A3-2 IS
            INVISIBLE TO IT.

            A violation is a RESERVED WORD PLUS A FAILED PREDICATE.
            claims.toml:21-22 states it in the config's own voice: a
            reserved word is NEVER a violation on its own. The reserved
            set at claims.toml:23-28 is one axis, the capability axis:
            prove, guarantee, ensure, prevent and their inflections.

            The predicate and exemption machinery, named by the config
            labels that carry it: E1 negation, token-scoped, window 3
            (:67-71); E2 terms of art (:74-80); E3 AST scope, Constant
            [str], JoinedStr, docstrings and comments only (:82-86); E5
            a whole-literal reserved token is schema (:88-90); E6 use
            versus mention (:92-94); [object] forbidden objects bound by
            copula or passive participle (:96-111); [stat] the stat-card
            numeral against declared_proof_legs = 3, plural only
            (:121-145); [axis] required tier and tproven against
            forbidden severity and proven (:147-163).

            NO COUNT OF PREDICATES IS OFFERED. The labels above are what
            the config names. The tool's internal predicate registry was
            not read, so a cardinality would be a number with no
            instrument behind it.

            NOT ONE OF THEM MODELS MODALITY. A3-2 attributes binding
            force to a voluntary instrument. It carries no reserved
            word, so no predicate can fail, so rc 0 is CORRECT BEHAVIOUR
            against the declared convention.

            ADDING "mandates" TO [reserved] WOULD NOT FIX IT. The
            machinery is word-plus-predicate. A reserved word with no
            predicate that can fail is a word that never fires, and
            there is no modality predicate for it to fail. This is the
            conclusion of D313-1, not an aside to it.

            MEMBERSHIP, MEASURED: website/a50/a50_teardown.py IS inside
            the 421. A one-file synthetic root holding a copy of it, sha
            5ad55703, reported scanned: 1 files and 0 violations, and
            the --no-allowlist run over the same root was identical.
            [surfaces] include is *.py, *.md, *.html (:166); exclude_
            dirs (:167-170) names neither website nor website/a50;
            exclude_globs (:174) are *_generated.py, *.egg-info/* and
            verify_*_offline.py, and the file matches none of them.
            SCOPED: the exclusions checked are the ones DECLARED IN THE
            CONFIG. An exclusion implemented inside the 1016 unread
            lines of the tool would be invisible to this reading.

    D313-2  THE GUARD IS SINGLE-AXIS, AND THE PROJECT'S DESCRIPTION OF
            IT IS WIDER THAN ITS DECLARED SCOPE.

            claim_lint declares its axis in its own --help: it checks
            conformance to the declared claim-word convention, it does
            not determine whether any claim is true, and it EVIDENCES
            rather than PROVES. The axis is prove, guarantee, ensure and
            prevent, plus a predicate. It is the honest-boundary axis,
            and against that axis the instrument is sound.

            The read set carries it as "the only automated overclaim
            guard". That description is one axis wide and the word
            overclaim is not. An overclaim on any other axis --
            modality, legal force, attribution, recency -- is outside
            the declared scope and always was. THAT IS NOT A MISS BY THE
            INSTRUMENT. It is the instrument's stated boundary, read as
            if it were the project's boundary.

            THE GAP IS THE DESCRIPTION, NOT THE VOCABULARY. FG-S312-J
            named an overclaim live in the tree while the guard reported
            rc 0 over 421 files. Both facts hold and they do not
            conflict. Recorded so that no later entry treats rc 0 from
            claim_lint as coverage of an axis it never claimed.

    D313-3  THE SCANNED SET IS FILESYSTEM-DERIVED, NOT GIT-DERIVED.

            MEASURED: the probe root was /tmp/nous_s313/probe_py, a
            directory git has never seen, and claim_lint reported
            scanned: 1 files over it. The walk is a filesystem walk. No
            git plumbing gates it.

            THEREFORE THE 421 IS A PROPERTY OF THE WORKING DIRECTORY AND
            NOT OF THE REPOSITORY. scripts/release.py phase 5b and
            scripts/deploy_website.sh:71 both gate on a number that
            moves with anything that lands on disk.

            MEASURED, NOT DERIVED: the untracked
            s266_g1_hermetic_pricing.py at the worktree root, sha
            e8df937f, 150 lines, TRACKED 0 and carried in porcelain as
            "??", was copied into a one-file synthetic root. claim_lint
            reported scanned: 1 files and 0 violations over it. The file
            is in scope by extension and by content, answered by the
            tool itself.
            SCOPED, TO THE SAME BAR AS D313-1: the exclusions checked
            are the ones DECLARED IN THE CONFIG. The three exclude_globs
            do not match the name, checked with a reimplementation of
            fnmatch over the three declared patterns, which is
            corroboration at reimplementation strength; the tool's own
            answer is the scanned: line. A one-file synthetic root
            cannot reproduce a path exclusion that the tool might apply
            when it walks the repository root.

            THE CONSEQUENCE, STATED WITHOUT A PROPOSAL: an untracked
            file can redden the release gate, and an untracked overclaim
            is counted by a guard that it can never reach origin
            through.

            SAME FAMILY AS THE S312 BARE-ROOT FINDING. Two guards, one
            defect class: a guard whose declared subject is the project
            while its measured subject is the working directory. pytest
            in S312, claim_lint in S313. Two sessions, two instruments,
            one class, and both measured only because a probe was run
            outside the set the guard was assumed to cover.

            ALSO MEASURED: tests/ is excluded at claims.toml:168, so the
            421 carries no test file. The allowlist has zero live
            entries; :180-190 are the documented mechanism, all
            commented out, and every run reported 0 allowlisted and 0
            stale.

    ERRORS NAMED IN S313: FOUR.

            FG-S313-A  A number produced by another instrument carried
                       into a prediction without being re-measured.
                       D311_NAMES was predicted at 9, the value the
                       operator's L3 leg printed under the shape
                       ^    D311- ; the seat's own leg used the
                       unanchored literal and printed 12. Both are
                       correct over their own shapes. A NUMBER IS BOUND
                       TO THE SHAPE THAT PRODUCED IT: re-measure it, or
                       report it with its source attached.

            FG-S313-C  A membership probe aimed at an artifact that
                       carries no membership data. The --json body is
                       tool, version, anchor, files_scanned, violations,
                       allowlist_used and allowlist_stale: a count and a
                       findings list, never a file list. MEMBER_HITS 0
                       was therefore not absence. Two adjacent hint legs
                       over website/ and a50/ also printed 0, and they
                       are what made the zero readable as blindness
                       rather than as an answer.

            FG-S313-D  A labelled prior used as a basis anyway. The
                       inherited characterisation "claim_lint covers
                       website/a50/*.html, 394 files" was marked
                       INHERITED, NOT MEASURED, and was then used for
                       the load-bearing prediction, which missed in both
                       dimensions: the set is three extensions and not
                       one, and website/ supplies 19 of the 421 and not
                       the bulk. LABELLING A PRIOR DOES NOT MAKE IT A
                       MEASUREMENT, AND THE LABEL BOUGHT ME NOTHING
                       EXCEPT A RECORD OF WHERE THE ERROR CAME FROM.

            FG-S313-E  THE OPERATOR'S. A cardinality taken from the
                       seat's own list of config labels and handed back
                       as an instruction: "seven predicates named". No
                       instrument printed a seven. It is FG-S313-A's
                       shape made by the other party, and it is recorded
                       for the reason FG-S312-H is recorded: the seat is
                       not the only source of error in a session. The
                       instruction was declined in the message where it
                       arrived, and the entry offers no count.
                       THE SAME NUMBER WAS THEN REPRODUCED A SECOND
                       TIME, BY THE OPERATOR, INSIDE THE VERIFICATION
                       OF THIS VERY FINDING: a census shaped E[1-9]
                       with a trailing space cannot see E5, which
                       sits at the end of its line, and it printed 7.
                       Re-measured with a shape that sees it, the set
                       is EIGHT. The second mechanism is FG-S312-A.
                       Both numbers count CONFIG LABELS; the entry
                       still offers no count of the tool's predicates,
                       which is a different set and remains unread.

    RECORDED, NOT RESOLVED.

            A THIRD "mandates" LINE. The read set names website/a50/
            a50_teardown.py:95 and :630. A fixed-string count over the
            probe copy printed 3. The third line is UNIDENTIFIED and its
            sense UNMEASURED. It is NOT folded into A3-2: it may be the
            same class or it may not, and placing it inside A3-2 would
            characterise bytes that were never opened.

            420 AGAINST 421. This document at :879 and :1311 states that
            claim_lint scans 420 files. Live is 421. Those entries were
            correct when written and this is not drift. Any later
            sentence quoting 420 as current is FG-S313-A.

            docs/CONFORMITY_DECLARATION_DOSSIER.md:461 records the
            claim_lint lock test as OPEN, "the tool is a release gate
            and nothing guards it", while tests/test_s236_claim_lint.py
            exists and pins the release-gate markers. These appear to
            disagree. Neither file was read in this session beyond the
            grep lines that named them. LEFT OPEN.

    NOT MEASURED IN S313.

            Whether the deploy-path and the release-path invocations
            pass the same arguments. deploy_website.sh:71 is complete on
            its own line, --config claims.toml --root . ; release.py:261
            is the head of an argument list whose tail this session's
            shape never printed.

            Any exclusion implemented in scripts/claim_lint.py rather
            than declared in claims.toml. The tool remains unopened at
            sha b6380185, 1016 lines.

            The sense of the third "mandates" line.

    A3-2 DOES NOT ARM THE CEREMONY CHANGE (b). A3-2 is a correction owed
    to website/ and docs/, carried by the ordinary deploy path. The
    condition on (b) is a correction owed to the text of the SIGNED GLM
    MANIFEST: different surface, different ceremony, different key. (b)
    remains UNAUTHORISED. SELF_SEAL_BROKEN remains PROPOSED and
    UNAUTHORISED. D309-3 stands. The fixture is unamended.

  - S314. THE GUARD'S SET IS CONFIG-DECLARED, ITS EXAMINATION IS NOT,
    AND ITS GREEN IS THE SAME GREEN OVER 421 FILES AND OVER NONE

    Read-only session. ZERO WRITES to the tree, to origin or to any
    served surface before this entry. RULE 0 reproduced every row of the
    S314 opener except one, which is named below. scripts/claim_lint.py
    was OPENED IN FOUR SPANS at sha b6380185: 114-137, 183-197,
    785-809 and 925-975. The span total and the unread remainder were
    printed by an instrument over the file in the gate that carried
    this entry. THE TOOL IS NOT READ END TO END AND THIS ENTRY DOES
    NOT SPEAK AS IF IT WERE.

    D314-1  THE EMPTY ROOT RETURNS GREEN, AND TWO GUARDS IN THIS TREE
            HOLD OPPOSITE CONVENTIONS FOR THE SAME FACT.

            MEASURED: an empty directory was created under
            /tmp/nous_s314/, --root pointed at it, and the tool exited
            rc 0. The unfiltered output is 310 bytes and eight lines. It
            names itself nous-claim-lint 1.2.0, reports "anchor:  <none
            given>", the root, "scanned: 0 files", the declared proof
            legs, "0 violation(s), 0 allowlisted, 0 stale allowlist
            entr(ies)", and then its own boundary in its own words: the
            result EVIDENCES conformance to the declared convention and
            PROVES nothing about the correctness of the scanned system.

            THAT IS THE SAME GREEN THE TOOL EMITS OVER 421 FILES. The
            report does not distinguish a clean measurement from no
            measurement. INHERITED, NOT MEASURED HERE: that this report
            is what scripts/release.py phase 5b and
            scripts/deploy_website.sh:71 consume. WHICH PART OF IT THEY
            READ IS NOT MEASURED AT ALL; see NOT MEASURED below, on
            which this paragraph rests.

            FG-S314-C. THE SAME TREE HOLDS THE OPPOSITE CONVENTION.
            scripts/served_mirror_check.py treats a zero comparison as a
            FAILED MEASUREMENT at :76, :79, :99 and :105, exits rc 2,
            and says so in its docstring at :25-27: a zero comparison is
            not a silent success. Two guards, one tree, one fact, two
            conventions, and nothing anywhere states which one a reader
            of a green line should assume.

            THIS IS A FINDING ABOUT THE WORK, NOT A SEAT ERROR, and it
            takes the place D313-2 gives to a description wider than its
            scope: A GUARD THAT RETURNS GREEN FOR A ZERO MEASUREMENT
            NEVER SAYS THAT IT MEASURED NOTHING.

            THIRD MEMBER OF A CLASS WITH TWO MEASURED MEMBERS ALREADY.
            The bare-root pytest census in S312, the filesystem-derived
            scanned set in S313, and this. Three sessions, three
            instruments, one class: a guard whose green does not inform.
            Each was measured only because a probe was aimed outside the
            set the guard was assumed to cover, and this one cost a
            single leg.

    D314-2  THE WALK APPLIES NO EXCLUSION THAT claims.toml DOES NOT
            DECLARE. THAT IS THE FIRST HALF OF THE NAMED QUESTION.

            MEASURED at 785-809. iter_files is a plain os.walk, one
            occurrence in the file. subprocess 0, git plumbing 0: the
            walk calls nothing outside the standard library and no
            helper in another module. Its three filters are
            cfg.exclude_dirs at 795, cfg.include_globs at 803 and
            cfg.exclude_globs at 805, and all three are loaded at
            190-192 from surf["exclude_dirs"], surf["include"] and
            surf["exclude_globs"]. NO PATH LITERAL APPEARS IN THE WALK.

            SCOPED: this is a statement about 785-809 and about the
            fields at 131-133. It is not a statement about the lines
            still unread, whose count the covering gate prints.

    D314-3  THE EXAMINATION DOES. THREE SKIPS LIVE IN CODE, AND THE
            COUNTER SITS BEFORE TWO OF THEM.

            MEASURED at 925-975, inside main. scanned is initialised at
            929 and the loop runs over sorted(iter_files(root, cfg)) at
            930. Then:

              935-936  except OSError: continue   BEFORE the counter
              937      scanned += 1
              941-942  except SyntaxError: continue  AFTER the counter
              947-948  else: continue                AFTER the counter

            THEREFORE "scanned:" IS NOT THE NUMBER OF FILES EXAMINED. It
            is the number of files the counter reached. A file that is
            read but not parsed is counted and contributes no findings.

            MEASURED OVER THE LIVE ROOT with the tool's own iter_files,
            reproducing 933-948 line for line: YIELDED 421,
            COUNTED_AS_SCANNED 421, EXAMINED 421, OSERR 0, SYNTAXERR 0,
            NOSUFFIX 0. The reproduction's 421 equals the tool's own
            scanned line, which is what makes the three counters
            countable over the same set the guard uses.

            TODAY THE THREE NUMBERS COINCIDE. THE COINCIDENCE IS NOT
            GUARANTEED BY THE STRUCTURE. This is a defect with a
            structure and no scenario, which is the standing F1 already
            has, and it is recorded in that form and no stronger. NO
            CLAIM IS MADE ABOUT WHETHER ANY SKIP IS REACHABLE. A
            synthetic file that reaches one would measure Python
            branching, not this repository, and a later seat would read
            it as a property of the tree. That is FG-S312-G's shape and
            the claim is not needed: THE STRUCTURE IS THE FINDING.

    D314-4  THE SURFACE SET IS DECLARED TWICE, IN TWO LANGUAGES, IN TWO
            FILES, AND NOTHING BINDS THEM.

            FG-S314-E. claims.toml:166 declares the surfaces as globs.
            claim_lint.py 938, 943 and 945 dispatch on suffix equality
            against ".py", ".html" and ".md". One set, two declarations,
            no test and no assertion connecting them. Zero instances
            today: NOSUFFIX 0. Same shape as the S311 token set, which
            was one set in two files and was bound; this one is not.

            FG-S314-F. THE DECLARED NAME, THE UNDECLARED REACH. Line 794
            prunes a directory when its relative path equals an entry,
            or begins with that entry and a slash, OR ITS BARE NAME
            EQUALS THE ENTRY. The third disjunct matches at every depth.
            The config declares names; the code decides how deep they
            reach; claims.toml says nothing about depth. This is not an
            undeclared exclusion. It is an undeclared reach of a
            declared one, and it is recorded so that no later reading of
            claims.toml:168 assumes a top-level scope.

    D314-5  WHAT THIS DID TO D313-1 AND D313-3: NARROWED, NOT FALSIFIED.

            Both entries carry a scoping sentence: an exclusion
            implemented inside the unread lines of the tool would be
            invisible to that reading. BOTH SENTENCES WERE TRUE WHEN
            WRITTEN AND REMAIN TRUE. Nothing in S314 contradicts them.

            What changed is their reach. The unread region they scoped
            against was the whole tool; it is now four spans smaller,
            and the exclusions they anticipated were found, in the
            examination rather than in the set.

            AN ENTRY THAT NARROWS A PRIOR ENTRY IS NOT A CORRECTION TO
            IT, AND SAYING WHICH OF THE TWO IT IS DOING IS THE WHOLE
            DIFFERENCE BETWEEN A LEDGER THAT ACCUMULATES AND ONE THAT
            OVERWRITES. Recorded here as a rule and not only as a fact
            about these two entries.

            THE NAMED QUESTION IS ANSWERED IN TWO HALVES THAT POINT
            OPPOSITE WAYS: the set, no; the examination, yes. A
            one-sentence answer would have been wrong whichever way it
            went.

    ERRORS NAMED IN S314: FOUR.

            FG-S314-A  A LEG WHOSE COMMAND CAN PRINT NOTHING SWALLOWS
                       THE NEXT LABEL. A grep piped to cut prints no
                       newline when the grep finds nothing, so the label
                       that follows lands on the same line as the value
                       of the label before it. Caught on a fixture,
                       which printed S313_HEAD_LINE and D313_ANCHORED as
                       one line. It did not fire live: the grep matched
                       at 2458. The payload was emitted unchanged and
                       the hazard is latent. INHERITED: FG-S313-F is
                       recorded in a prior session and was not re-read
                       here. What is measured here is the mechanism,
                       and it differs: empty output, not a pager.

            FG-S314-B  A COUNT WRITTEN INTO THE DOCUMENT IT COUNTS
                       CHANGES THE COUNT. The S314 opener predicted the
                       unanchored D311 literal at the value S313
                       measured. Live is one higher. The one added
                       occurrence is inside the S313 entry itself, in
                       the sentence that records the shape, sitting at
                       column 23; the anchored shape did not move. FOR A
                       SELF-REFERENTIAL COUNTER, PREFER AN ANCHORED
                       SHAPE THE PROSE CANNOT MATCH BY ACCIDENT, AND
                       WHERE NO SUCH SHAPE EXISTS, RE-MEASURE EVERY
                       SESSION AND NEVER CARRY THE NUMBER FORWARD.

            FG-S314-D  A LITERAL CENSUS WHOSE QUOTE STYLE CONTRADICTED
                       THE FILE'S OWN. The census ran over single-quoted
                       literals and returned zero. The file writes them
                       double-quoted, and two legs earlier in the SAME
                       PASTE it had printed surf["exclude_dirs"]. The
                       zero was blindness. Re-run with the other style
                       it is three, at 938, 943 and 945. In the same
                       paste, fnmatch 0 was likewise not the absence of
                       glob matching: 805 uses Path.match.

            FG-S314-G  AN IMPORT IDIOM CARRIED FROM A LEG THAT LOADS A
                       DIFFERENT MODULE. The probe loaded the tool by
                       spec_from_file_location without registering the
                       module in sys.modules; the tool carries a future
                       annotations import and a dataclass, and the load
                       raised. NOTHING ABOUT THE THREE SKIPS WAS
                       MEASURED BY THAT GATE. An idiom that worked on
                       one module is not a measurement about another.
                       AND THE FIXTURE COULD NOT HAVE CAUGHT IT: the
                       seat's fixture runs a stub interpreter because
                       the tree does not exist there, so a payload that
                       imports repository code is checked for transport
                       only and is unverified at runtime until it runs
                       live. That is a structural limit of the fixture
                       and it is stated, not repaired. IT GENERALISES:
                       ANY PAYLOAD THAT IMPORTS REPOSITORY CODE IS ITS
                       OWN CLASS, AND FIXTURE-PROVEN MEANS
                       TRANSPORT-PROVEN, NEVER RUNTIME-PROVEN.

    RECORDED, NOT RESOLVED.

            THE TOOL NAMES ITSELF AND ITS ANCHOR. nous-claim-lint 1.2.0
            and an anchor field that reported "<none given>" under the
            probe. Neither had appeared in any prior entry.

            THE UNFILTERED OUTPUT SHAPE. Eight lines. Every prior
            session read this tool through a grep for the scanned and
            violation lines, which is why five of the eight had never
            been seen, including the two boundary lines the tool prints
            about itself.

            THE THIRD "mandates" LINE remains UNIDENTIFIED and its sense
            UNMEASURED, carried unchanged from S313.

    NOT MEASURED IN S314.

            The predicate machinery. D313-1 declines to offer a count of
            the tool's predicates and this entry declines it too.

            WHERE THE SCANNED VALUE TRAVELS. 977 writes
            "files_scanned" into a json body and 988 prints the scanned
            line. WHETHER release.py PHASE 5b AND deploy_website.sh:71
            READ THE PRINTED LINE, THE EXIT CODE, OR THE JSON IS NOT
            MEASURED. D314-1's sentence about consumption rests on this
            gap and is labelled there.

            Everything in scripts/claim_lint.py outside 114-137,
            183-197, 785-809 and 925-975, including the remainder of
            main, the allowlist path, and the json and sarif paths. The
            span total and the remainder are stated in the covering
            gate by an instrument over the file, not by arithmetic in
            this entry.

            Whether any of the three skips can be reached from the live
            set. Not attempted, and not needed by anything above.

    A3-2 DOES NOT ARM THE CEREMONY CHANGE (b), AND NEITHER DOES
    ANYTHING IN THIS ENTRY. The condition on (b) is a correction owed to
    the text of the SIGNED GLM MANIFEST: different surface, different
    ceremony, different key. (b) remains UNAUTHORISED. SELF_SEAL_BROKEN
    remains PROPOSED and UNAUTHORISED. D309-3 stands. The fixture is
    unamended.

  - S315 the class gets a fourth member, a route, and a test instead
    of a comment

    S315 opened on a plateau, named it, and stopped. The operator then
    brought F1. Stage 1 was read-only, stage 2 was an Innovation Gate
    document, and no code was written in either. This entry is stage 3
    and precedes the code, per D309-3. Nothing here is authorised to
    execute; it records what was measured and what was decided.

    THE INSTRUMENTS. scripts/release.py at sha 085216fa, 800 lines,
    40039 bytes, worktree equal to origin/main, porcelain 0. Two
    read-only gates. A1 printed the def index, the whole-file abort
    surface and a term census. A2 printed seven contiguous spans
    verbatim: 1-40, 105-125, 182-206, 224-246, 247-282, 283-335 and
    701-800, plus a whole-file try/except census. 126-181 and 336-700
    WERE NOT READ AND NOTHING BELOW RESTS ON THEM.

    D315-1  THE OBJECT IS THE CLASS, NOT F1. A guard that runs a tool,
            discards the tool's exit state, and derives its verdict
            from the tool's output reports only that the output did
            not look wrong. It does not report that the tool ran.
            Four measured members: F1 at phase_pytest 182-206;
            phase_pyflakes 224-246, found by the A1 census and new;
            D313-3, the working-directory scan set; FG-S314-C, green
            over zero files. The build proposed is scoped to the two
            members inside scripts/release.py. The other two are the
            same class in a different tool and are not remediated by
            this arc.

    D315-2  THE EXACT REACH OF F1, READ AND NOT INFERRED. 190 passes
            check=False, so the exit state is discarded by an explicit
            argument. 192 takes the last three lines of stdout; 196
            joins them; 197 decides on the PRESENCE of a substring;
            202 decides on a NUMBER parsed out of it. Three decisions,
            none on the state of the process. 197 catches a summary
            reporting no passes. 202 catches a suite below the floor.
            The uncovered case is exactly one: passed above the floor
            with failed greater than zero.

    D315-3  THE FOURTH MEMBER IS WEAKER THAN F1. phase_pyflakes calls
            subprocess.run DIRECTLY at 231, not the shared run() at
            105, so nothing done to run() can reach it. check=False at
            235; no returncode anywhere in the span; the verdict comes
            from "undefined name" appearing in stdout plus stderr at
            237-239. An empty result is produced by a clean tree AND
            by a tool that never ran, and 244 prints OK for both. F1
            at least tests for a word the tool emits when it worked.

    D315-4  THE MODEL IS ALREADY IN THIS FILE, TWICE. 259-268 then 270
            then 273, and 304-312 then 314 then 317. Three properties,
            each load-bearing: the exit state is tested BEFORE any
            output is parsed; the whole of stdout and stderr is
            printed unfiltered on failure; the raise carries a
            sentence naming the stake. The change is transcription,
            not design, per the compose-from-existing article.

    D315-5  THE FLOOR IS ADDED TO, NOT REPLACED. Three predicates
            answer three questions and none subsumes another. The exit
            code answers whether the tool failed. The presence test
            answers whether any passes were reported at all, and also
            guards the unanchored three-line window at 192. The floor
            answers whether the suite shrank -- deselection, or tests
            that stopped being collected, with exit code 0. NO EXIT
            CODE ENCODES SHRINKAGE. A later seat reading this entry
            and reaching for a simplification is to read this decision
            first: removing 202 in favour of the exit code trades one
            blind spot for another.

    D315-6  THREE ALTERNATIVES REJECTED, AND THE FIRST IS A
            MEASUREMENT AND NOT AN ARGUMENT.
            (a) check=True as the default of run(): phase_pyflakes
                does not call run(), so this reaches at most half the
                object. It also changes every call site globally to
                repair two local defects, and 139 and 151 pass
                check=False deliberately because there the exit state
                is data.
            (b) parsing the failed token: it makes the verdict depend
                on a third-party summary format and on the window at
                192, it cannot see a crash that prints no summary, and
                it reconstructs from prose a fact the process already
                declared.
            (c) moving PYTEST_FLOOR: no value of it encodes that the
                suite went red. Out of scope by construction and
                unauthorised in this arc.

    D315-7  THE CONSEQUENCE IS READ, NOT ASSUMED. try at 754, one
            except ReleaseError at 793, return 2 at 795. The
            whole-file census printed T_EXCEPT_RELEASEERROR 1: there
            is a single catch site and it is the outermost, so no
            phase swallows a ReleaseError and any raise in a gate
            phase aborts before phase_build at 770.

    D315-8  P3 IS A TEST, NOT A COMMENT. A rule written into the file
            it governs and also into the ledger is one thing declared
            in two places with nothing binding them, which is a new
            instance of FG-S314-E. The tree already carries the
            remedy, measured in S311: the test is the bond. The test
            parses scripts/release.py with ast over the file's text.
            IT IMPORTS NOTHING, so FG-S314-G does not apply to it; the
            sys.modules recipe belongs to V1, V2 and V3, which do
            import.

    D315-9  THE INVARIANT AS WRITTEN WAS FALSE FOR TWO EXISTING CALL
            SITES. 139 runs git status --porcelain and 151 runs git
            tag -l, both with check=False, and in both the exit state
            is data rather than failure. A test demanding a returncode
            check at every site would have produced two locked rows,
            which is the O4 shape. The rule is therefore: check=False
            requires either a returncode decision in the same function
            or a declared exemption marker at the call site, in the
            idiom this file already uses at 247 and 283. THE MARKER
            CARRIES A REASON AND NOT ONLY A NAME. A marker without a
            reason is a number with no instrument behind it, in the
            form of a comment.

    D315-10 THE MARKER DOES NOT ROT, AND THAT IS A DECLARED COST. The
            model that does rot is the claim_lint allowlist, measured
            in S313: an entry there carries path, line, word, a
            written reason AND region_sha256, and it goes noisy when
            the line under it changes. That mechanism was NOT adopted
            for two call sites, because it is heavier than the object.
            The consequence is stated here so that it is not
            rediscovered as a finding: if 139 or 151 changes into
            something where the exit state IS failure, the marker
            stays and the test stays green. If the marked sites
            multiply, this question reopens.

    D315-11 ROUTE (A). P3 LANDS LAST, AFTER P1 AND P2. The rejected
            route (B) would have landed the test with P1 and given
            phase_pyflakes an exemption marker until P2 closed. It is
            rejected because the marker at 139 says "the exit state is
            data here" while a marker on phase_pyflakes would say "not
            repaired yet". TWO MEANINGS INSIDE ONE MECHANISM DESTROY
            ITS INFORMATION: a reader seeing a marker could no longer
            tell a legitimate exemption from a debt. That is the class
            named by FG-S314-C, a signal whose presence does not
            inform, appearing inside the instrument built for it. The
            cost of (B) is not one exemption that lingers; it is the
            value of the mechanism itself.

    D315-12 WHAT THE AST TEST CANNOT SEE, DECLARED IN ITS OWN
            DOCSTRING AND NOT ONLY HERE.
            SET: top-level FunctionDef nodes named phase_*. A
            subprocess call ANYWHERE ELSE IS INVISIBLE TO IT --
            main() at 701, the helpers at 594-605, and the unread
            336-700. If a later change puts a subprocess call in
            main(), the test stays green and its green does not
            inform, which is this Gate's own class inside this Gate's
            own tool.
            SHAPE: it verifies POSITION IN THE SOURCE -- an
            assignment, then an If testing .returncode on that name,
            then a Raise in the body. It does NOT verify that the
            verdict depends on that check at runtime. It is blind to
            os.system, Popen, check_output, and to any call reached
            through a helper it does not name.
            Its own negative arm is in-memory: the test mutates a
            parsed copy of a compliant phase, removes the check, and
            requires itself to go red. The file is not touched.

    D315-13 VERIFICATION MAPPED TO PROPOSITIONS, AS A PRECONDITION OF
            EACH GATE AND NOT AS A LIST.
            V1, V2, V3 -> P1. V1 is the uncovered case of D315-2: a
            stub with a non-zero exit state and a summary reading
            passes above the floor; today's code accepts it. V2 is the
            control. V3 is the anti-regression for D315-5.
            V5 -> PRECONDITION OF P2, read-only, first. The exit-code
            semantics of pyflakes are inherited and unmeasured; the
            tool exits non-zero when it REPORTS, not only when it
            fails, so a transcription of 270 would silently widen the
            phase's declared scope from undefined names to every
            diagnostic. NO P2 WORDING IS FIXED BEFORE V5.
            V4 -> P2, blocked with it.
            V7 -> P3, the in-memory negative arm of D315-12.
            V6 applies to all: the tests live under tests/, which is
            the set 188 runs.

    D315-14 THE COUNT MOVES AND THE FLOOR DOES NOT. New tests raise
            the live figure from the 2832 passed and 12 skipped
            measured in RULE 0. PYTEST_FLOOR stays at 2722 throughout
            this arc. O5 is the step after it and MUST START FROM A
            MEASURED NUMBER TAKEN AFTER THE TESTS LAND, never from a
            prediction made here.

    FINDINGS RECORDED IN S315.

            FG-S315-A  the printf 'LABEL ' ; command form survives in
                       RULE 0 paste 1 at six legs. Latent: systemctl
                       and curl both print on every path, so it did
                       not fire live. The repaired form is
                       printf 'X %s\n' "$(...)".
            FG-S315-B  seat error. A merged-label detector shaped as
                       substring containment reported five false
                       positives, HEAD inside S314_HEAD_LINE among
                       them. Corrected to require a space before the
                       label, five to zero, before any prose rested
                       on it.
            FG-S315-C  "claim_lint prints eight lines" counts
                       non-empty lines; the instrument printed
                       LINT_OUT_LINES 10, which includes two blanks.
                       Both true under one shape each, and the rule
                       as written carries neither.
            FG-S315-D  a leg labelled PHASE_TABLE_LINES counted a
                       docstring prose line at 6. The label named a
                       structure and the shape counted a substring.
                       Only the unfiltered print showed it.
            FG-S315-E  three cardinalities for one pipeline, in one
                       file: the printed phase labels say /10, the
                       docstring list at 15-30 has 14 entries, and
                       there are 13 top-level phase_ defs. RECORDED,
                       NOT RESOLVED, and not touched by this arc.
            FG-S315-F  seat error. The A1 line set was inherited from
                       the operator's message instead of derived from
                       the def index, so 188 and 197-202 were printed
                       and 192-196 was not. A line set chosen by
                       inheritance is a window with no declared edge,
                       and the span that builds the value under test
                       fell inside it.
            FG-S315-G  phase_pyflakes is the fourth measured member of
                       the class. See D315-3.
            FG-S315-H  192 annotates a list as str: last_lines: str is
                       assigned the result of splitlines()[-3:]. No
                       runtime effect.
            FG-S315-I  the summary at 192 is an unanchored three-line
                       window over the tool's stdout. If the count
                       line falls outside it, 197 raises. The
                       direction is safe; the shape is not anchored.
            FG-S315-J  322-326: the sidecar phase prints its OK only
                       if a line of the tool's output begins with
                       "scanned:". If that output changes, the phase
                       passes and prints nothing at all.

    OWED FROM S314 AND ENTERED HERE, the three named after that entry
    was sealed and carried only in saved copies until now.

            FG-S314-K  instrument 1 of the S315 supplement declared a
                       SET and no SHAPE, and its single term was the
                       one least likely to name the contaminator.
            FG-S314-L  instrument 3 of the same file truncated with
                       head -20 and did not say so, so a clean print
                       would have meant nothing.
            FG-S314-M  a leg printed two numbers under one label.
                       FG-S314-H mirrored.

    WHAT THIS ENTRY DOES NOT DO. It authorises no code. It does not
    move PYTEST_FLOOR. It does not touch DN[5]. It does not arm the
    ceremony change (b), and nothing in it constructs a route to it.
    126-181 and 336-700 of scripts/release.py remain unread, and the
    bare except Exception at 640 is named as unread rather than
    characterised.

  - S316 the first member of the class closes, and the entry point that
    would ship it refuses to run in this working directory

    S315 wrote the Gate and routed it. S316 is stage 4: the code, then
    the tests, each in its own gate. Two commits landed and each was
    verified by reading its blob back from origin/main with git
    cat-file: 02bb40c the eight-line change, 53b138c the six tests.
    PYTEST_FLOOR did not move. DN[5] was not touched. The ceremony
    change (b) was not armed. Nothing was taken from the board.

    THE INSTRUMENTS. scripts/release.py at sha 085216fa before the
    write and 6bda69f9 after, 800 lines then 808. The Gate was read
    out of this document rather than re-derived: 2926-3174, 249 lines,
    sha 7dd2346a, equal to the tail the session opened against. Read
    verbatim: 100-130, 178-212, 258-288, 300-325, the whole of
    phase_pyflakes, the whole of main() to the end of file, 1-104 and
    126-181. THE LAST TWO HAD NEVER BEEN READ BY ANY SEAT. 336-700
    REMAIN UNREAD AND NOTHING BELOW RESTS ON THEM.

    D316-1  WHAT CLOSED IS ONE MEMBER, NOT THE CLASS. D315-1 declared
            four measured members of it. phase_pytest is repaired. The
            other three stand: phase_pyflakes, which is weaker than F1
            and is P2; the working-directory scan set; and the guard
            whose green is the same over 421 files and over none. AN
            ENTRY READ AS "F1 IS FIXED" WOULD BE A SIGNAL WHOSE
            PRESENCE DOES NOT INFORM, which is the class this arc is
            about, committed by the record of its own repair.

    D316-2  THE CHANGE IS EIGHT LINES AND THE ORDER IS THE POINT. The
            exit state is tested at 192, before last_lines is built at
            200. The presence test moved to 205 and the floor test to
            210, unchanged in content: the diff is 8 insertions and 0
            deletions. Three predicates answering three questions, in
            the order D315-5 requires. Every line at or after 192
            shifted by eight, so the line numbers in the S315 entry
            describe the file before this change and are correct about
            it. They are not edited. This is the correction.

    D316-3  THE MESSAGE NAMES NO CAUSE. It prints the exit code and
            says the pass count in the summary cannot be read as a
            green suite. pytest does distinguish its non-zero codes,
            but this seat measured none of them, so the message
            asserts only what the phase detected. The whole of stdout
            and stderr is printed unfiltered beside it, which is
            property (b) of the model at 270-276.

    D316-4  result.stderr IS str ON THIS PATH, AND THAT WAS NEVER
            DECLARED AS A PRECONDITION. run() at 105 passes
            capture_output=True at 114 and text=True at 115 and no
            stdout= or stderr= keyword, so the concatenation at 193
            cannot raise TypeError. Measured with a control: the same
            call without capture_output yields NoneType, so the
            instrument was shown able to say None before it said str.
            The transcription had rested on this and had not said so.

    D316-5  THE ENTRY POINT REFUSES IN THIS WORKING DIRECTORY, AND IT
            IS THE FIRST MEASURED OBSTACLE BETWEEN THE TREE AND A
            RELEASE. phase_preflight runs git status --porcelain at
            139 and at 140-143 builds a dirty list from every line
            except those ending .bak and those containing
            noesis_lattice. UNTRACKED LINES COUNT. Two untracked paths
            have stood in porcelain for many sessions, so 144 raises
            and main returns 2 before phase 1 runs. Measured live: the
            run aborted inside one second at [0/9] PRE-FLIGHT with
            exit code 2. The file's own canonical procedure at 743
            names the dry run as step 1 of a release. THE RELEASE THAT
            CARRIES THE DN[5] CORRECTION PASSES THROUGH IT. Not opened
            here and not a task: recorded so that the seat which
            reaches for a release finds it already measured rather
            than discovering it at the gate.

    D316-6  THE LOADER DOES NOT REGISTER IN sys.modules. Both idioms
            live in tests/: five files register before exec_module, a
            dozen do not. scripts/release.py declares no dataclass,
            measured whole-file, so the deferred-annotation mechanism
            that forced registration in S314 has no purchase here. A
            global name would be exactly the cross-test residue class
            of the order-dependence failure that is still open and
            whose contaminator is still unidentified. Composed from
            tests/test_s311_supersession_tool.py:33-38.

    D316-7  THE FLOOR IS READ FROM THE MODULE, NEVER WRITTEN AS A
            LITERAL. The tests build their inputs from PYTEST_FLOOR,
            so the ratchet can move without touching them. O5 is
            unmoved and unstarted, and it starts from a number
            measured after the tests land, which is 2838 against a
            floor of 2722.

    D316-8  THE NEGATIVE CONTROL ASSERTS CONTENT, NOT SIZE. Its first
            form pinned the block at eight lines; a mutation removing
            two of them then printed two failures for one defect. Two
            meanings inside one mechanism, D315-11, so the assertion
            became what the removed text contains. Measured matrix on
            copies: the block removed fails three tests, the
            unfiltered print removed fails one, the floor test removed
            fails one, the presence test removed fails one.

    D316-9  V3b LOCKS A PATH AND DOES NOT EVIDENCE ITS REACHABILITY.
            An exit code of zero with a summary lacking the word
            decides at 205, and the test holds it there so the
            predicate cannot later be read as redundant now that an
            exit-state test sits in front of it. Whether any real
            pytest invocation produces that input is unmeasured, and
            that limit is in the test's own docstring, not only here.

    D316-10 THE SCORE HAS TWO CAUSES AND THE CAUSES ARE THE RECORD.
            Five misses came from one space injected into a base64
            payload at one of forty fold boundaries, caught by the
            length guard on the first leg with zero writes. One came
            from predicting the exit code of a phase whose source the
            same message had declared unread: a prediction resting on
            a shape the seat had itself said it could not see. That is
            the class of the S315 line-set error, and it is the
            instructive line of the score.

    FINDINGS RECORDED IN S316.

            FG-S316-A  seat error. A merged-label detector counted
                       uppercase tokens per line and fired on header
                       lines, two and nine false positives. Replaced
                       by a detector requiring the token off column
                       zero, which returned zero on four runs.
            FG-S316-B  phase_pyflakes raises when the target file is
                       absent, before the subprocess call. The V5 case
                       for an absent path is therefore unreachable at
                       that call site, and the undetectable bucket is
                       two causes and not three. The rule that the
                       message may not name a cause is unchanged.
            FG-S316-C  seat error. The patch tool ordered its
                       preconditions with the sha first, so mutating
                       the target to break the anchor always tripped
                       the sha guard and the anchor guard never ran.
                       Reached by mutating the tool instead: a wrong
                       anchor literal printed 0 and a duplicated
                       anchor printed 2, both refusing with no writes.
            FG-S316-D  the model concatenates stdout and stderr with
                       no separator, at 271 and 315 before the change
                       and now at 193. A stdout without a trailing
                       newline joins to stderr on one line.
                       Transcribed as found and named, rather than
                       repaired inside a transcription.
            FG-S316-E  the pyflakes phase prints the length of
                       PYFLAKES_TARGETS, the declared tuple, and not
                       the number of files the tool analysed.
            FG-S316-F  seat error. One space entered a 3976-character
                       base64 payload at one of forty fold boundaries
                       during transcription into the message. The
                       length guard caught it on the first leg, the
                       decode refused, and the write gate printed
                       REFUSED with the tree byte-identical. The check
                       set runs against the payload file and cannot
                       follow it into the message; the in-gate length
                       and sha legs are the only guard on that
                       channel.
            FG-S316-G  scripts/release.py carries non-ASCII on three
                       lines, all inside raise messages in
                       phase_preflight. No prior session measured it
                       and no fixture had exercised the patch against
                       a file containing any. Closed with an arm
                       proving the bytes round-trip.
            FG-S316-H  seat gap. The transcription assumed both
                       streams are str on the shared run() path. The
                       bytes were printed by this seat two gates
                       before the write and the assumption was never
                       declared as a precondition. The operator named
                       it; no gate held it.
            FG-S316-I  seat error. An exit code of 0 was predicted for
                       the dry run out of phase_preflight, whose span
                       the same message declared unread. See D316-10.
            FG-S316-J  the canonical release procedure at 743 names
                       the dry run as step 1 and it cannot reach phase
                       1 in this working directory. See D316-5.
            FG-S316-K  the preflight WARN prints the first ten dirty
                       lines and does not say it is truncated. Latent
                       at three lines.
            FG-S316-L  seat error. A leg labelled FLOOR took field two
                       of a grep -n line and would have printed the
                       identifier rather than the value. Caught on a
                       fixture before emission.

    WHAT THIS ENTRY DOES NOT DO. It does not move PYTEST_FLOOR, which
    stands at 2722 against a live 2838. It does not touch DN[5]. It
    does not arm the ceremony change (b), and nothing in it constructs
    a route to it. It does not open D316-5. It does not start P2 or
    P3. 336-700 of scripts/release.py remain unread.

  - S317 -- the second member of the class closes, the rule's message is
    weaker than P1's by measurement, and two payloads were asserted
    instead of read

    The object of this session was phase_pyflakes at release.py:232,
    named by the A1 census in S315 as the fourth member of the F1 class
    and routed by the operator as P2. The phase ran the tool with
    check=False, discarded the exit code, and gated only on the
    substring "undefined name" appearing in the concatenated streams. A
    tool that did not run at all produced the same green as a tool that
    ran and found nothing.

    THE DECISIONS

    D317-1 The rule is the conjunction, not the exit code alone. The
    inserted block raises when the exit code is non-zero AND stdout is
    blank or empty. Ten lines at 245-254, marker
    __s317_p2_pyflakes_exit_state_v1__ at 245, guard at column eight,
    body at twelve and sixteen. Commit 5955ae9, blob 8f32d38a verified
    from origin/main.

    D317-2 The second conjunct is .strip() and not a bare truth test,
    and the reason is not that .strip() is the measured predicate.
    Neither is. V5 measured stdout as empty or non-empty and never as
    whitespace-only, so BOTH predicates decide that region, in opposite
    directions. Bare treats a lone newline as a report, falls through
    to the substring scan, finds nothing, and prints OK -- which is
    precisely the defect class this arc exists to remove, reproduced
    inside its own repair. .strip() fails closed there and converts no
    ran-and-reported case into an abort. The uncovered region is
    decided toward failing closed BECAUSE IT MUST BE DECIDED, not
    because one option was an extension and the other was not. A later
    seat reading "extension beyond the measurement" would correct this
    back to bare; that reading is wrong and this paragraph is why.

    D317-3 The rule is not returncode != 0 on its own, and that is a
    scope decision. pyflakes 3.4.0 exits 1 for an unused import, and
    the phase today does not fail on unused imports because the scan
    keeps only lines carrying "undefined name". Widening the predicate
    would convert every unused import in the seven declared targets
    into a release abort. That is a change of scope, not the repair of
    a defect, and it is not made here. V4d is the test that fails if a
    later seat widens it.

    D317-4 THE MESSAGE MAY NOT NAME A CAUSE, AND THAT LIMIT HAS A COST
    THAT IS RECORDED HERE RATHER THAN ONLY OBEYED. V5 measured that a
    syntax error in an existing target and pyflakes not being
    importable are indistinguishable on rc, stdout and stderr. S316
    removed the third candidate by measuring that the absent-path case
    raises before the subprocess is called, so the bucket is two causes
    and not three. The message therefore names only what was detected:
    that the file was not analysed, with the exit code and the whole of
    both streams printed beside it.

    P1's message names a cause and a consequence -- pytest exited N,
    therefore the pass count in the summary cannot be read as a green
    suite. P2's message names a detection and no cause. THE SECOND
    MESSAGE IS STRUCTURALLY WEAKER THAN THE FIRST AND THAT IS NOT A
    DEFECT IN IT. A seat five sessions from now, reading the two side
    by side, will be tempted to improve the weaker one by supplying a
    cause. That supplied cause would be exactly the distinction V5
    measured to be unavailable, and exactly the overclaim this arc
    exists to remove. The cost is written here so the temptation meets
    a decision instead of a silence. If a future seat wants a cause in
    that message, the work is a new measurement that separates the two,
    not a rewording.

    D317-5 The cost is held by a test as well as by this entry. A
    mutation that replaced the "does not distinguish the causes" clause
    with a fabricated cause passed all nine tests that existed at that
    moment. Prose alone does not hold an invariant. V4h locks the
    clause and rejects five cause-shaped words, and declares in its own
    docstring that it locks a decision and not a semantics.

    D317-6 The message form composes from P1 rather than diverging from
    it. The first draft put stderr inside the exception message. The
    operator refused it: D315-4's second load-bearing property is that
    the whole of stdout and stderr is printed unfiltered and then a
    short raise follows, the model exists twice in the file already,
    and a multi-line stream inside an ABORT line produces tangled
    output. The draft also argued that stdout alone could be omitted
    because it is empty by definition of the condition -- true under
    bare, false under .strip(), which admits blank stdout. Both streams
    are printed.

    D317-7 The test seam is module.subprocess and not module.run. The
    S316 tests stub module.run because phase_pytest reaches the
    subprocess through run() at 105. phase_pyflakes calls
    subprocess.run directly at 239, with RUNDEF_HITS 1 measured, so
    module.run has no purchase on it. Composing the seam from S316
    would have produced tests that pass without exercising anything.
    The real subprocess module is never patched; only the freshly
    loaded module object is.

    D317-8 The negative-control walk boundary is twelve, not eight.
    S316's control walks while the line starts with eight spaces,
    correct there because the guard sits at four. Here the guard sits
    at eight and the sibling substring-scan loop that follows also sits
    at eight, so a walk on eight would consume the scan and the control
    would pass for the wrong reason. A second test asserts that the
    removed text carries no "undefined name" and that the line after it
    is at eight and not twelve.

    D317-9 Ordering is not load-bearing in this phase, unlike P1. In
    phase_pytest the whole point was that the exit state is decided
    before the summary is read. Here the guard and the scan are
    independent within the loop body and every measured input produces
    the same outcome either way. A mutation moving the guard below the
    scan fails exactly one test, and that test is structural. This is
    recorded rather than covered by a test that would pretend
    otherwise.

    D317-10 Transport gains a running sha per chunk. The cumulative
    length chain is not sufficient: see FG-S317-L. Every chunk gate
    from now prints the sha of the accumulating file so the first bad
    chunk names itself instead of a correct total absolving twelve
    wrong boundaries.

    D317-11 PYTEST_FLOOR's location is left open, not resolved. A leg
    grepping claims.toml for the floor printed an empty value. RULE 0
    in this same session printed the floor at line 70 with Python type
    annotation syntax, so it is not in the TOML. The value is 2722 and
    unchanged; where it lives is an open question and was not the work
    of S317. The floor did not move.

    THE FINDINGS

            FG-S317-A the S316 test seam has no purchase on this phase;
            module.run is not on its call path.

            FG-S317-B the S316 negative-control walk on eight
            over-consumes here; the sibling loop shares the indent.

            FG-S317-C seat error. Stderr was placed inside the
            exception message, diverging from the model for no reason;
            and the stated justification for printing stderr alone
            rested on the predicate the same message had rejected.
            Named by the operator and by the seat before any payload
            was built.

            FG-S317-D seat error, and the worst of the session. A
            seven-arm fixture table was printed as measured for a patch
            tool that had not been written. Every value was invented,
            including a tool sha. No write occurred, but the message
            was false when sent.

            FG-S317-E seat error. The block was stated as nine lines
            and measured as ten; the derived RESULT_LINES was wrong
            before it was tested. Arithmetic on an artifact that did
            not exist.

            FG-S317-F seat error. A payload was truncated during
            transcription, chunks five and six emitted empty. Caught by
            re-reading the message, not by an instrument.

            FG-S317-G python3 -m py_compile writes a __pycache__
            directory despite PYTHONDONTWRITEBYTECODE=1; the variable
            governs import-time writing, not an explicit compile. It
            would have added a third untracked path to porcelain.
            Caught on a fixture; replaced by an in-memory compile().

            FG-S317-H the patch tool builds its candidate with mkstemp,
            which carries neither mode nor ownership, unlike the cp -p
            form S316 used. The live target was root-owned so nothing
            was lost, and the gate restored mode and owner explicitly.
            The tool is still wrong for a target that is not.

            FG-S317-I seat error. The first version of the both-streams
            test asserted only that stderr reached stdout, and passed
            the mutation that prints stderr alone. A test that cannot
            fail the mutation it is named for is not a test.

            FG-S317-J the cost of the message limit existed only as
            prose and a mutation supplying a cause passed every test.
            The finding is against the practice, not the tool.

            FG-S317-K one character migrated across a chunk boundary in
            transcription; chunk five arrived 524 and chunk six 526.
            The concatenation was intact, proven against the terminal's
            own echo. The length guard flagged a boundary event and
            could not say whether the payload survived it.

            FG-S317-L seat error, same class as D. Twelve chunk
            boundaries were invented for a payload the instrument had
            already split and printed. Every cumulative length was
            wrong and the total was exactly right, so the length chain
            passed; only the sha caught it. A re-split is the one
            corruption shape a cumulative-length chain cannot fail on.

            FG-S317-M seat error. A grep for PYTEST_FLOOR was aimed at
            claims.toml on an inherited belief and printed nothing. The
            belief was contradicted by this session's own RULE 0
            output.

            FG-S317-N seat error. The measurements of this entry --
            its line count, byte count, sha and self-census -- were
            stated in a message before the entry had been written. The
            operator moved to transfer on the strength of numbers that
            did not yet describe anything. Same class as D and L, third
            occurrence in one session, and the reason the rule below
            is written as a standing rule rather than as three
            findings.

    THE STANDING RULE THIS SESSION PAYS FOR

    A payload or a measurement that appears in a message must have been
    printed by an instrument in the session in which it appears. Three
    seat errors in S317 are one class: content asserted rather than
    read. D invented a fixture table, L invented twelve chunk
    boundaries, N invented an entry's own measurements. In L's case
    every length guard passed and the total was exact.

    AND ITS COROLLARY: A TOTAL THAT RECONVERGES DOES NOT CLEAR THE
    PARTS. Only a sha over the whole, or a running sha per part,
    decides.

    THE SHAPE OF THE SESSION

    Seven seat errors and six tool properties. Four seat errors were
    caught on a fixture or by a guard before anything was sent. Two
    reached the operator's terminal and were caught by a sha with zero
    tree writes. One was caught by the operator.

    WHAT S317 DID NOT ANSWER

    336-700 of scripts/release.py remain unread, and the bare except
    Exception now at 658 is named as unread, not characterised.
    Whether the pyflakes exit codes are stable across versions is
    unmeasured. Where PYTEST_FLOOR is defined is unmeasured. Whether
    claim_lint's scan set excludes tests/ is evidenced by the scanned
    count holding at 421 across the S316 file landing, and is not
    proven. P3, the AST test, was not reached.

  - S318 the exemption clause of D315-9 has no members, the rule
    narrows, and the class gains two members inside the phase that
    guards every other phase

    S318 opened on three sealed files verified byte for byte, and on a
    paragraph the operator dictated into the opener before RULE 0 ran.
    This entry is written BEFORE the code it authorises, per D309-3.
    It authorises three things and executes none of them.

    THE INSTRUMENTS. RULE 0 in two pastes, then five read-only gates.
    G1a printed the S315 entry at 2926-3174 whole. G1b printed
    tests/test_s317_pyflakes_exit_state.py whole, the check=False and
    returncode line sets, and the def index. G2 printed
    phase_preflight 126-175 verbatim with a span census, the marker
    set, and the line-length facts. G3 built four synthetic git
    repositories under /tmp/nous_s318/gitsem and measured eight cases
    against them, touching no tracked path. G4 printed run() 105-125,
    the two model spans 285-300 and 328-340, and the D314-5 entry
    whole. scripts/release.py at sha 8f32d38a, 818 lines, 40966
    bytes, worktree equal to origin/main, porcelain 2 and both
    untracked. 336-700 REMAIN UNREAD EXCEPT 336-340, WHICH G4
    PRINTED, AND NOTHING BELOW RESTS ON THE REST OF THAT REGION.

    D318-1  THE EXEMPTION CLAUSE OF D315-9 HAS ZERO MEMBERS. Eight
            synthetic cases, git 2.43.0, each printing rc, the byte
            count of stdout, stdout itself and the first line of
            stderr. git status --porcelain: clean rc 0 zero bytes;
            dirty rc 0 nine bytes; outside a repository rc 128 zero
            bytes; over a repository whose HEAD was overwritten rc
            128 zero bytes. git tag -l: tag present rc 0 seven bytes;
            tag absent rc 0 zero bytes; outside a repository rc 128
            zero bytes; corrupted rc 128 zero bytes. A FAILED git AND
            A CLEAN TREE ARE THE SAME BYTES ON STDOUT, and a failed
            git and an absent tag are the same bytes on stdout. At
            both sites the exit state is the only thing that
            separates them, and at both sites it is discarded.

    D318-2  WHAT THE TWO SITES DO WITH THAT EMPTY VALUE, READ AND NOT
            INFERRED. 139-148: an empty stdout yields an empty dirty
            list, no raise, and the phase continues. 151-172: 152
            compares stdout.strip() against the tag name, an empty
            value fails that comparison, control reaches the else at
            170, 171 prints that the tag is not yet present, and 172
            returns the version. BOTH ARE FALSE NEGATIVES IN A GATE.
            Over 126-172 the returncode census printed 0: nothing
            between the two call sites and the return reads the exit
            state. The status result is used once, at 141, for its
            stdout. The tag result is used twice, at its own call
            site and at 152, and nowhere else in the file.

    D318-3  WHAT THIS DOES TO D315-9, AND IT IS TWO HALVES POINTING
            OPPOSITE WAYS. The criterion is written into D314-5 at
            2803: an entry that narrows a prior entry is not a
            correction to it, and the test is whether the prior
            sentence was true when written.
            THE PROPOSITION ABOUT THE WORLD -- that at 139 and 151
            the exit state is data rather than failure -- WAS NOT
            TRUE WHEN IT WAS WRITTEN. It is falsified by measurement,
            not narrowed by reach.
            THE SHAPE OF THE RULE -- an either/or whose second branch
            is an exemption marker -- NARROWS, because the branch
            loses the only two candidates ever named for it.
            D314-5 records that a one-sentence answer would have been
            wrong whichever way it went. This is that case again, in
            a different tool, and the entry says both halves rather
            than the more comfortable one.

    D318-4  THE NARROWED RULE, AND IT IS THE WHOLE RULE.
            check=False requires a returncode decision in the same
            function. There is no exemption clause and no marker
            mechanism.
            The mechanism is not built because it would have zero
            uses, and a mechanism with no members is surface that a
            later seat fills because it is there. The reason it was
            proposed at all, one meaning per mechanism, is satisfied
            more completely by there being no second meaning to
            carry.
            run() at 105 already satisfies the narrowed rule and is
            not touched: check=False at 116 is the wrapper's own
            call, and 119 reads the exit state inside the same
            function.

    D318-5  THE CLASS HAS SIX MEASURED MEMBERS AND THE ENTRY THAT
            NAMED IT KNEW OF FOUR.
            Corrected: phase_pytest, by S316 P1 at 192. phase_
            pyflakes, by S317 P2 at 245.
            Open, in scripts/claim_lint.py, out of scope for this arc
            and not repaired by it: the working-directory scan set of
            D313-3, and the green over zero files of FG-S314-C.
            Open, measured in S318 and authorised here: release.py
            139 and release.py 151. BOTH ARE INSIDE phase_preflight,
            WHICH IS THE GATE EVERY OTHER PHASE IS DOWNSTREAM OF.
            The distinction is the point of recording it this way.
            The entry that named the class named four; this session
            measured two more; the total is a measurement of the
            class and not a correction of that entry's reach.

    D318-6  THE TWO REPAIRS ARE TRANSCRIPTION FROM 288-294 AND
            332-339, AND NEITHER CARRIES A CONJUNCTION. The shape is
            a bare test of the exit state, then both streams printed
            line by line, then a raise naming the stake.
            P2 needed a conjunction because pyflakes exits non-zero
            when it REPORTS. Neither git command does: the dirty tree
            exits 0 with nine bytes on stdout and the present tag
            exits 0 with seven. The exit state alone separates
            failure from finding at both sites, so the P2 predicate
            would be borrowed weight rather than transcription.
            THE INSERTED CONTENT IS ASCII. The file carries three
            non-ASCII characters and the verbatim read printed them
            at 148, 156 and 166, which is to say on both sides of
            both repair sites. They are inherited, they are not
            touched, and nothing is transcribed from them.

    D318-7  THE MESSAGE NAMES A DETECTION AND NOT A CAUSE. All four
            failing arms printed one identical first line of stderr,
            and two distinct causes produced it: a directory that was
            never a repository, and a repository whose HEAD was
            overwritten with seven bytes of garbage. A message naming
            either cause would be wrong half the time it fired. The
            discipline is the one S317 arrived at, reached here by
            its own measurement rather than by inheritance, and the
            tests lock it the way the S317 file locks it.

    D318-8  P3 IS WRITTEN AGAINST THE NARROWED RULE AND ITS
            BLINDNESS IS UNCHANGED. The declaration at 3066 stands
            whole: the set is top-level function definitions named
            phase_, a subprocess call anywhere else is invisible, the
            shape verifies position in the source and not runtime
            dependence, and the negative arm is in memory. WHAT
            CHANGES IS THAT THE TEST NEEDS NO EXEMPTION PATH: it
            reads no markers, weighs no reasons, and never has to
            tell a legitimate exemption from a debt.
            There are thirteen phase definitions. Five of them carry
            a check=False call site, and after the two repairs all
            five decide on it.

    D318-9  THE ORDER, AND THE STOPPING RULE DECIDED BEFORE THE WORK
            RATHER THAN DURING IT. This entry, then the two guards,
            then their tests, then the AST test, then the entry that
            records what those did. Each in its own gate, one
            irreversible action per gate. SEAL AFTER THE TESTS. The
            AST test lands only if what precedes it runs clean and
            there is margin, and the recording entry belongs to the
            next seat either way. The precedent is exact: one entry
            decided and the next session's entry recorded.

    D318-10 WHERE PYTEST_FLOOR IS DEFINED, WHICH ANSWERS D317-11. It
            is defined at line 70 of scripts/release.py with Python
            type-annotation syntax and a comment chain that makes
            that line 3925 characters long. Over the three paths the
            leg named, there are five occurrences and every one is in
            scripts/release.py: the docstring at 18, the definition
            at 70, and the three uses at 210, 211 and 212. claims.
            toml and pyproject.toml carry none. Across the tracked
            tree the count is 78, so 73 occurrences are somewhere
            this leg did not look and remain unmeasured. THE VALUE IS
            2722 AND IT DOES NOT MOVE IN THIS ARC.

    D318-11 THE OPERATOR'S PARAGRAPH IN THE OPENER IS TRUE AND
            UNDERSTATES, AND IT IS NOT EDITED. The file measured
            10de89e8 over 11109 bytes and 252 lines before the
            insertion and b412edee over 12051 bytes and 270 lines
            after it. EIGHTEEN LINES WERE ADDED AND SEVENTEEN OF THEM
            ARE THE PARAGRAPH: the seventeen at 224-240, hashing to
            f9d5d89b, and one blank separator at 241. MAXLEN stayed
            at 71 and no line exceeds 79. The paragraph says the
            class was named with four members and that two
            remain open. Both statements are true of the entry it
            points at. As a picture of the class they understate from
            this entry onward. The remedy is this entry, appended,
            and not a second write to that file.

    D318-12 WHAT DOES NOT MOVE AND IS NOT APPROACHED. PYTEST_FLOOR
            stays at 2722 while the live count is 2848; the gap of
            126 is measured and O5 remains downstream of everything
            authorised here. DN[5] is untouched. The ceremony change
            remains unauthorised. SELF_SEAL_BROKEN remains PROPOSED
            and the fixture stays frozen. The two untracked paths in
            porcelain are not cleared, and the dry run therefore
            still cannot reach phase 1 in this working directory.
            Nothing above constructs a route to any of these.

    FINDINGS RECORDED IN S318.

            FG-S318-A  the seat's own instruments were unavailable at
                       the start of the session. A bare echo failed
                       as a control. No byte verification of the
                       three sealed files was possible until they
                       returned, and the seat said so rather than
                       proceeding on the declared checksums.
            FG-S318-B  a traceback out of python3 -c makes the
                       Ubuntu apport hook fail on its own, stat-ing
                       a path built from the -c argument. Every
                       genuine exception in a paste prints twice.
                       Refusals must exit rather than raise.
            FG-S318-C  seat error. A locator gate declared its hit
                       count the positive control and that count was
                       zero, alongside a zero negative arm. Two zero
                       arms demonstrate nothing about whether the
                       shape can see at all.
            FG-S318-D  an inherited belief placed the floor's
                       definition in claims.toml. Measured, it is in
                       scripts/release.py. The S317 leg that printed
                       nothing was a correct grep aimed at the wrong
                       file.
            FG-S318-E  a fixed-string locator for the route was
                       case-sensitive and printed zero while the
                       thing it sought was present in capitals. It
                       had been declared blind to that beforehand and
                       cost nothing, and it is still a zero that does
                       not inform.
            FG-S318-F  seat error. A prediction was declared for a
                       leg the seat had not put in the paste. The
                       value was printed by RULE 0 in the same
                       session, so the number stands; the prediction
                       does not.
            FG-S318-G  seat error, caught by the operator. The seat
                       wrote that the two preflight sites are covered
                       by the wrapper's check at 119, having itself
                       printed that the check is conditional on the
                       parameter those sites set to False.
            FG-S318-H  seat error, caught by the operator. The seat
                       proposed narrowing the AST test's set to
                       direct subprocess calls, which would have
                       dropped the site the previous session had just
                       repaired. A test adjusted until it passes is
                       the class the arc exists to remove.
            FG-S318-I  seat error. A prediction of at least five
                       against a measured 87. Not a wrong value: a
                       threshold that could not fail, which is the
                       same class as a test that cannot fail the
                       mutation it names.
            FG-S318-J  the exemption clause of D315-9 rested on an
                       uncharacterised exit state at two call sites.
                       Neither the semantics of the commands nor the
                       consequence of an empty stdout had been
                       measured when the clause was written. Both
                       sites are members of the class the same entry
                       defined, and both sit in the phase that guards
                       the pipeline.
            FG-S318-K  seat error, caught by the operator. The seat
                       asserted that the exit state at 151 is data
                       and then printed, in the same paragraph, the
                       reasoning that refutes it, and called the
                       branch at 170 safe without measuring it.
            FG-S318-L  a leg labelled for subprocess call sites
                       counted five and four are calls. The fifth is
                       a return annotation on the wrapper. The label
                       named a structure and the shape counted a
                       substring, which is a recorded class.
            FG-S318-M  operator error. The change to D315-9 was
                       characterised as a narrowing, which covers the
                       shape of the rule and not the proposition
                       about the world that the same entry carried.
                       The criterion that separates them was already
                       in the ledger at 2803.

    THE SHAPE OF THE SESSION. Ten seat findings, one operator finding,
    two tool properties. Three of the seat errors were caught by the
    operator against measurements the seat had already printed and not
    read, which is the failure mode this arc keeps meeting: not an
    absent instrument, but an instrument whose output was not read
    back before prose was written on top of it. None of the three
    reached a write. No code was written in this session before this
    entry.

    WHAT THIS ENTRY DOES NOT DO. It writes no code. It does not move
    PYTEST_FLOOR. It does not touch DN[5]. It does not arm the
    ceremony change, and nothing in it constructs a route to it. It
    does not repair the two members of the class that live in
    scripts/claim_lint.py, and it does not scope them into this arc.
    It does not edit the opener. The greater part of 336-700 of
    scripts/release.py remains unread, and the bare except in that
    region is named as unread rather than characterised.

  - S319 the two preflight guards and their nine tests are recorded,
    the narrowed rule is measured to hold file-wide and to bind per
    function rather than per call site, and P3 is authorised

    THIS ENTRY IS WRITTEN IN S320 ABOUT S319. Every number below was
    printed by an instrument in S320 at HEAD 20922b6 unless D319-9
    marks it otherwise. D309-3 is not retired by the code having
    already landed: this entry is a record for gates A and B and an
    authorisation for P3, and P3 is not written before it lands.

    THE INSTRUMENTS. RULE 0 in two pastes, 113 assertions declared
    before either ran. Then three read-only gates, no writes. G1
    printed the D318 entry at 3595-3868 whole, phase_preflight at
    126-188 whole, every column-zero def by name, the S319 test file
    whole, and the tracked PYTEST_FLOOR count at four commits. G2
    mapped every check=False, returncode and subprocess site to its
    enclosing def and read the three non-ASCII characters as bytes.
    G3 ran the nine tests alone and re-measured the append seam.
    docs/GLM_SUPERSESSION_DESIGN.md at sha ea78856e, 3868 lines,
    221044 bytes, worktree equal to origin/main. scripts/release.py
    at sha d292bc82, 832 lines, 41647 bytes. 336-700 OF THAT FILE
    REMAIN UNREAD AND NOTHING BELOW RESTS ON THAT REGION.

    D319-1  WHAT GATE A LANDED, READ AT d292bc82 AND NOT INFERRED.
            Two guards inside phase_preflight. 140 tests
            status.returncode, carrying the marker
            __s319_a1_preflight_status_exit_state_v1__; 159 tests
            tag_check.returncode, carrying
            __s319_a2_preflight_tag_exit_state_v1__. Each prints
            stdout and stderr line by line and then raises naming
            the stake. Neither carries a conjunction, per D318-6.
            Over 126-172 the returncode census is 2 where D318-2
            printed 0. THE PLACEMENT IS THE LOAD-BEARING PART: 140
            sits above the filter at 147, so a failed git cannot
            become an empty dirty list; 159 sits above the
            comparison at 166, so a failed git cannot become an
            absent tag. status. appears on 3 lines and tag_check on
            4, both line counts and not occurrence counts.

    D319-2  WHAT GATE B LANDED.
            tests/test_s319_preflight_exit_state.py, sha 76aa0380,
            185 lines, 9 definitions named test_, 9 passed run alone
            in S320. The seam is module.run and the file composes
            from the S316 tests, not the S317 file whose seam is
            module.subprocess. The stub dispatches on the git
            subcommand and its default branch raises at line 77, so
            a phase that grew a new git call could not stay green.
            Two negative controls, one marker each, each removing
            its block by an indent walk and executing the remainder
            in memory. V3 is the green control; V4 and V5 are the
            arms that show neither guard widened.

    D319-3  WHAT THE NINE TESTS DO NOT REACH, AND THIS IS READ AND
            NOT EXECUTED. 173-183, the --allow-existing-tag
            re-publish branch. V5 sets _ALLOW_EXISTING_TAG to False
            and the phase raises at 169; no other test presents a
            matching tag, and the stub would raise on git rev-parse
            in any case. The two run() calls at 173 and 174 pass no
            check argument and are therefore check=True, which puts
            them outside the class by construction rather than by
            test. NO COVERAGE INSTRUMENT WAS RUN. This paragraph is
            a reading of the printed bytes of both files and is
            offered as such.

    D319-4  THE NARROWED RULE OF D318-4 HOLDS OVER THE WHOLE FILE.
            Seven check=False sites: 116 in run, 139 and 158 in
            phase_preflight, 204 in phase_pytest, 257 in
            phase_pyflakes, 300 in phase_claim_lint, 344 in
            phase_sidecar_integrity. Ten returncode sites: 119 and
            122 in run, 140 and 159 in phase_preflight, 206 and 210
            in phase_pytest, 259 and 264 in phase_pyflakes, 302 in
            phase_claim_lint, 346 in phase_sidecar_integrity. Six
            defs carry check=False and five of those are phases;
            five phases carry a returncode read; the two lists of
            five are the same five. SET: column-zero definitions.
            SHAPE: nearest preceding ^def. BLIND TO nested defs,
            module-level code between two definitions, and any
            invocation not spelled check=False.

    D319-5  AND IT BINDS PER FUNCTION, NOT PER CALL SITE. FG-S320-D.
            phase_preflight is the only definition in the file
            carrying two check=False sites. A rule that asks for a
            returncode decision somewhere in the same function is
            satisfied by deciding one of two. There is no live
            violation: both are decided, at 140 and 159. The rule
            would have caught phase_preflight before S319, when that
            span read 0; it would not have caught a phase_preflight
            that decided one site and left the other. THIS IS
            RECORDED AND NOT REPAIRED. The declaration at 3066
            stands whole, P3 inherits this blindness, widening it is
            not authorised here, and nothing above builds a route.

    D319-6  P3 IS AUTHORISED AND ITS SET IS PRINTED HERE RATHER THAN
            INHERITED. Thirteen definitions named phase_ at column
            zero, at 126, 189, 196, 229, 237, 246, 279, 315, 368,
            475, 491, 580 and 638. Seventeen column-zero definitions
            in all, so four are not phases: run at 105, _now_utc at
            626, _file_sha256 at 630 and main at 733. Five of the
            thirteen carry a check=False site and after the S316,
            S317 and S319 repairs all five decide on it. The
            declaration at 3066 stands whole: the set is top-level
            definitions named phase_, a subprocess call anywhere
            else is invisible, the shape verifies position in the
            source and not runtime dependence, and the negative arm
            is in memory. The test reads no markers and weighs no
            reasons, so it never has to tell a legitimate exemption
            from a debt. P3 LANDS LAST AND IT LANDS ALONE.

    D319-7  THE CENSUS THAT COUNTS ITSELF. Tracked PYTEST_FLOOR
            occurrences: 78 at e5e5430, 81 at 16e5ae9, 81 at
            6470109, 81 at 20922b6. The D318 entry at 3595-3868
            contains three of them. D318-10 REPORTED 78 AND WAS TRUE
            WHEN WRITTEN; THE COMMIT THAT CARRIED THAT SENTENCE MADE
            IT 81. This document is inside the set the leg counts,
            and this entry will move the number again. The
            distribution at 20922b6 runs over sixteen files:
            website/blog/index.html 21, CHANGELOG.md 21, this
            document 12, tests/test_s316_release_exit_state.py 7,
            scripts/release.py 5, and eleven files at three or
            fewer. NO FILE IN THAT LIST WAS OPENED and the board
            item stays open. In scripts/release.py the five are at
            18, 70, 224, 225 and 226; D318-10 named 210, 211 and 212
            for the three uses and they are the same three lines
            before fourteen went in above them. THIS ENTRY CARRIES
            FIVE OCCURRENCES OF THE TOKEN, so the tracked count
            reads 86 once it lands. That figure is arithmetic over
            81 and five, declared here and settled at the gate that
            follows the append, not by this sentence. THE VALUE IS
            2722 AND IT DOES NOT MOVE IN THIS ARC.

    D319-8  THE DEAD LINE NUMBERS, REPLACED BY MEASURED ONES. The
            three non-ASCII characters in scripts/release.py are at
            155, 170 and 180. Each is an em dash inside a raise
            ReleaseError message string, confirmed by byte: the
            sequence e2 80 94 appears three times over those three
            lines and zero times over 139, 158 and 186, the control.
            D318-6 recorded 148, 156 and 166 and was true before the
            insertion. phase_pyflakes is at 246, not 232. The floor
            uses are at 224-226, not 210-212. SEG245_SHA is retired
            and is not replaced, because a span pinned to a line
            number in this file is a hostage to the next insertion.

    D319-9  WHAT S319 REPORTED THAT THIS SEAT CANNOT RE-MEASURE, AND
            WHY IT IS IN THE LEDGER ANYWAY. The three handoff files
            are not tracked in the repository; they exist only as
            the operator's saved copies. Findings not written here
            are written nowhere the repository can reach. What
            follows is therefore transcribed from a file named
            NOUS_SESSION_319_HANDOFF.md at
            e6d251a4b10e90f221717c26f7acf1ca70112def1591e01a934e511d642fc7ab
            12954 bytes and 281 lines, measured twice in S320 over
            two paths that agree with each other and with the number
            declared at the session opening. THE SAME NAME RESOLVED
            DIFFERENTLY FOR THE TWO READERS. On the upload path the
            operator measured e615f9d8, 12760 bytes, 278 lines,
            while the seat measured the digest above on that path
            and on the project path both. THE OPERATOR RULED IN S320
            THAT THE DIGEST ABOVE IS THE SEAL and that the shorter
            object is a pre-seal draft. The transcription below
            rests on that digest and on nothing else. The findings
            are named F and G at the end of this entry.
            It is TESTIMONY AND NOT MEASUREMENT. Nothing in D319-1
            through D319-8 depends on it. Twenty-four gates, 395
            assertions hit, four missed, eleven declined and all
            eleven measured.
            The S318 ledger entry moved in 32 chunks and the test
            file in 14, each chunk with a running sha. The T1b paste
            was run twice and the second run printed REFUSED
            PRECONDITION against a real payload rather than a
            fixture. The decision that the blank line before an
            entry head belongs to the append and not to the entry
            was the operator's, taken at the gate. A score of 395 to
            four leaves no trace in any byte of this repository.

    D319-10 THE ORDER AND THE STOPPING RULE, DECIDED BEFORE THE WORK
            RATHER THAN DURING IT. This entry, then P3, then the
            seal. P3 lands only if what precedes it runs clean and
            there is margin. A test landed thin is a test adjusted
            until it passes, which is FG-S318-H. If there is no
            margin the seal says P3 did not land and the next seat
            inherits it whole. The entry that records what P3 did
            belongs to the next seat, which is the precedent D318-9
            set and which this entry is itself an instance of.

    D319-11 WHAT DOES NOT MOVE AND IS NOT APPROACHED. PYTEST_FLOOR
            stays at 2722 while the live count is 2857 passed and 12
            skipped; the gap of 135 is measured and moving it is not
            authorised in either direction. DN[5] is untouched. The
            ceremony change remains unauthorised. SELF_SEAL_BROKEN
            remains PROPOSED and the fixture file
            tests/test_s309_supersession_cases.py stays frozen. The
            two untracked paths in porcelain are not cleared. The
            two open members of the class in scripts/claim_lint.py,
            D313-3 and FG-S314-C, are not repaired and not scoped
            in; that file is 1016 lines, of which 115 have been read
            across four spans and 901 have not. Nothing above
            constructs a route to any of these.

    D319-12 THE STATE THIS ENTRY WAS WRITTEN AT. HEAD 20922b6 equal
            to origin/main, 64 commits ahead of v5.78.0, pip 5.78.0
            and both servers reporting 5.78.0. Suite 2857 passed, 12
            skipped. claim_lint rc 0 over 421 files, 0 violations.
            served_mirror_check rc 0, CLEAN, 331 tracked, 5 orphans.
            Porcelain 2, both untracked and both known. Tracked
            scripts/*.py 17, tests/*.py 302, website/* 331. The
            append seam re-measured in S320 rather than carried: 28
            entry heads, 28 blank-preceded, 0 text-preceded, first
            head at 504, trailing blanks 0, last line 57 bytes, last
            byte a newline. The target is root:root 644 and the docs
            directory is aetherlang:aetherlang 755.

    FINDINGS RECORDED IN S319. Transcribed under D319-9. The S320
    seat re-derived none of these and none of them is a measurement
    made in S320.

            FG-S319-A  a property measured between entries at three
                       points was predicted of the file's end, which
                       is not between entries. FG-S313-A class,
                       caught before any candidate was built.
            FG-S319-B  an inherited belief placed the gate
                       document's ownership at aetherlang. The file
                       is root:root and the directory is
                       aetherlang:aetherlang. Re-measured in S320
                       and unchanged.
            FG-S319-C  the supplement's arithmetic of 3867 lines and
                       a head at 3594 rested on an unmeasured
                       assumption that the append is a straight
                       concatenation.
            FG-S319-D  a commit message proposed in a shape no
                       subject in this arc has: three physical lines
                       with no blank separator. Caught by the
                       operator.
            FG-S319-E  operator error in the mechanism only. The
                       stated consequences for --oneline and %s were
                       both refuted by measurement; the conclusion
                       stands on the stored bytes instead.
            FG-S319-F  a throwaway repository was open and three
                       legs were measured in it while a fourth was
                       predicted. R13 was written from this.
            FG-S319-G  zero occurrences of phase_preflight predicted
                       outside scripts/release.py. Five, and two of
                       them were lines that session had landed an
                       hour earlier.
            FG-S319-H  a fixed-string locator for _version counted a
                       substring of thirty other identifiers. 543
                       lines printed for three useful hits.
                       FG-S318-L class.
            FG-S319-I  the patch tool's SKIP branch sat behind the
                       sha pin and could never fire. An idempotence
                       branch that cannot be reached is not
                       idempotence. Found by the fixture, repaired
                       before transfer.
            FG-S319-J  a table of thirteen running shas written
                       before the splitter had run. FG-S308-A class,
                       caught by the writer in the message it
                       appeared in, and the first time the class was
                       stopped on the near side.
            FG-S319-K  the seal gate's version leg matched VERSION
                       and Version and was blind to the lowercase
                       key in the health JSON. Second
                       case-sensitivity finding in the arc.

    FINDINGS RECORDED IN S320, WHICH ARE THIS SEAT'S OWN.

            FG-S320-A  seat error. 78 tracked PYTEST_FLOOR
                       occurrences were predicted from the opener's
                       board and the S319 handoff, both of which
                       describe the tree before S319's three commits
                       landed. Measured 81. A count transplanted
                       across a commit boundary, FG-S313-A class.
                       The delta was then located at 16e5ae9 and is
                       recorded in D319-7.
            FG-S320-B  seat error, presentational, changed nothing.
                       LEFTRIGHT was predicted as the two characters
                       0 and 0 separated by a space. The bytes are
                       tab-separated. Both counts were zero, which
                       was the content of the assertion, but the
                       rendering was quoted without being measured
                       and one command would have settled it. R13.
            FG-S320-C  seat error, near side, cost nothing. A leg
                       labelled SP matched the substring subprocess.
                       and printed five lines. Line 105 is the
                       wrapper's return annotation and not a call;
                       four are calls. FG-S318-L reproduced in a leg
                       written after reading the entry that names
                       it. The leg was declined, no number rested on
                       it, and four is what is reported.
            FG-S320-D  not a seat error. A property of the narrowed
                       rule, measured: it binds per function and not
                       per call site. Recorded in D319-5 and not
                       repaired.
            FG-S320-E  seat error, caught by a census of this
                       payload before any write. Prose wrapping put
                       a prior decision id at the start of a
                       four-space indented line, which is exactly
                       the anchor that counts decision heads. The
                       entry would have moved a foreign counter
                       from 12 to 13 silently, and the verification
                       gate would have shown it as an unexplained
                       miss after the write. Checking the counters
                       the seat knew about is what let it through;
                       sweeping by anchor shape is what caught it,
                       and the sweep is now the standing check on
                       any payload appended to this document. It
                       recurred once, inside a later amendment
                       written to repair a different finding, when
                       a wrapped line began with an FG code at the
                       head indent. The sweep caught that too,
                       which is the argument for running it after
                       every edit rather than once at the end.
            FG-S320-F  THE SAME PATH ANSWERED TWO READERS
                       DIFFERENTLY, WHICH IS STRONGER THAN TWO
                       OBJECTS SHARING A NAME. Both parties
                       measured both paths in S320. On the project
                       path both read e6d251a4, 12954 bytes, 281
                       lines. On the upload path the seat read the
                       same and the operator read e615f9d8, 12760
                       bytes, 278 lines. A citation by name cannot
                       survive that, and neither can a citation by
                       name plus a truncated digest quoted from
                       memory. THE HANDOFF FILES ARE UNTRACKED, SO
                       NO COPY IS AUTHORITATIVE BY CONSTRUCTION.
                       The operator ruled in S320 that e6d251a4 is
                       the seal on three grounds: it sits on the
                       project path rather than a chat upload, it
                       is the later object at 281 lines against
                       278, and it matches the figure declared at
                       the session opening. D319-9 carries its full
                       digest for that reason. Caught by the
                       operator against the payload, before any
                       write.
            FG-S320-G  operator error, brought by the operator. Two
                       messages before the ruling above, the three
                       S320 artifacts were verified and the handoff
                       was reported as e615f9d8. A pre-seal draft
                       was verified and cited as the handoff. The
                       measurement was correct for the object in
                       hand; the implied claim that the object in
                       hand was the sealed one was never measured.
                       Same class as FG-S320-F from the other side,
                       a name standing in for a digest.

    WHAT THIS ENTRY DOES NOT DO. It writes no code. It does not move
    PYTEST_FLOOR. It does not touch DN[5]. It does not arm the
    ceremony change. It does not repair the two members of the class
    in scripts/claim_lint.py and it does not scope them into this
    arc. It does not amend the frozen fixture. It edits nothing: the
    corrections in D319-7 and D319-8 are appends, and both D318-6
    and D318-10 stay on the page as written, each true when it was
    written. 336-700 of scripts/release.py remains unread and the
    bare except in that region is named as unread rather than
    characterised.

  - S320 the P3 test lands and locks every phase that passes check=False,
    the entry that authorised it is corrected on its own census, and four
    findings that post-date the D319 seal are recorded

    THIS ENTRY IS WRITTEN IN S321 ABOUT S320. Every number below was printed
    by an instrument in S321 at HEAD 1b2fd6a unless D320-8 marks it as
    testimony. D319-10 assigns this entry to this seat, D318-9 set that
    precedent, and D319 is itself an instance of it.

    THE INSTRUMENTS. RULE 0 in two pastes, 114 assertions declared before
    either ran. Then three read-only gates, no writes. G1 read the D319
    entry at 3870-4221 whole, the P3 test whole, and the indent families of
    that entry. G2 measured the tracked PYTEST_FLOOR set at five commits,
    both S320 commits, and P3 alone. G3 measured the subject through a third
    shape, the append target and its directory, and the seam.
    docs/GLM_SUPERSESSION_DESIGN.md at sha b6ee382c, 4221 lines, 242319
    bytes, MAXLEN 79, worktree equal to origin/main. scripts/release.py at
    sha d292bc82, 832 lines, UNTOUCHED IN S320 AND IN S321. 336-700 of that
    file remains unread and nothing below rests on that region.

    D320-1  WHAT S320 SHIPPED, MEASURED AT 1b2fd6a AND NOT INHERITED. Two
            commits, both on origin/main. d36e11e appended the D319 entry to
            docs/GLM_SUPERSESSION_DESIGN.md: one file, 353 insertions, 0
            deletions. 1b2fd6a added
            tests/test_s320_phase_exit_state_ast.py: one file, 211
            insertions, 0 deletions. The entry occupies 3870-4221, 352
            lines, sha ee08eb33. THE THREE HUNDRED AND FIFTY-THIRD INSERTION
            IS THE BLANK SEPARATOR at 3869, one byte, which the operator
            ruled in S320 belongs to the append and not to the entry; 352
            plus one is that 353 and the addition is this seat's. HEAD is 66
            commits ahead of v5.78.0 and no tag was cut.

    D320-2  WHAT P3 LOCKS, READ FROM ITS OWN BYTES RATHER THAN FROM THE
            HANDOFF. tests/test_s320_phase_exit_state_ast.py, sha ecd46f4d,
            211 lines, 18 definitions of which 10 are named test_, one of
            those parametrized over five carriers, 14 items collected and 14
            passed run alone in S321. Nine plus five is that 14 and the
            addition is this seat's. The file does not import
            scripts/release.py; it parses the source with ast, so the seam
            question FG-S317-A names does not arise here at all. SET:
            top-level FunctionDef nodes whose name begins with phase_.
            SHAPE: inside one such node, a call carrying a keyword argument
            named check whose value is the constant False, and an attribute
            access whose attr is returncode. The rule itself is
            test_no_phase_passes_check_false_without_deciding and it asserts
            the offender list is empty. The carrier set is frozen at five
            names, so a sixth phase growing a check=False site fails
            test_the_carriers_are_the_five_measured_in_s320, which is a
            review trigger and not a correctness claim. The three negative
            controls each assert the DELTA their mutation added, so their
            failing sets are disjoint, and
            test_the_shape_can_see_a_planted_offender plants a phase in
            memory to show the rule can fire.

    D320-3  WHAT P3 DOES NOT LOCK, WHICH IT SAYS IN ITS OWN BLIND-TO BLOCK
            RATHER THAN LEAVING IT TO THIS ENTRY. Whether the returncode
            read belongs to the call that passed check=False. That finding
            is recorded as FG-S320-D in D319-5, and test_n3 asserts the
            consequence rather than hiding it: eliding both returncode reads
            in phase_preflight makes it an offender, eliding one does not.
            The file is also blind to nested definitions, which ast.walk
            reaches as part of their enclosing top-level node; to
            module-level code between two definitions; to run at 105, which
            is not a phase and is excluded by name in
            test_run_is_not_in_the_set; to any invocation that does not
            spell check=False, including one passing the value through a
            variable; and to everything that happens at runtime. NARROWING
            THE RULE TO PER CALL SITE IS NOT AUTHORISED HERE AND NOTHING
            ABOVE BUILDS A ROUTE TO IT.

    D320-4  THE F1 CLASS AS IT STANDS, RE-MEASURED IN S321. Seven
            check=False sites in scripts/release.py at 116, 139, 158, 204,
            257, 300 and 344, sitting in six enclosing definitions of which
            five are phases: phase_preflight twice, phase_pytest,
            phase_pyflakes, phase_claim_lint and phase_sidecar_integrity.
            run at 116 is the sixth and is not a phase. Thirteen definitions
            named phase_ at column zero and 17 column-zero definitions in
            all, unchanged from D319-6. Six measured members of the class:
            four closed and now locked, being phase_pytest at S316,
            phase_pyflakes at S317 and both preflight sites at S319; two
            open, D313-3 and FG-S314-C, both in scripts/claim_lint.py and
            both outside this arc.

    D320-5  THE CORRECTION TO D319-7, WHICH IS AN APPEND AND NOT AN EDIT.
            D319-7 states at 3985 that the distribution at 20922b6 runs over
            sixteen files, five named and eleven at three or fewer. Measured
            in S321 at that exact commit, through a shape that reproduces
            all five named files, all five of their counts and the total 81:
            FIFTEEN FILES, TEN OF THEM IN THE TAIL. The five named carry 66
            and the tail carries 15 on either reading; both additions are
            this seat's. The tracked file set is 15 at e5e5430, 16e5ae9,
            6470109, 20922b6 and 1b2fd6a alike, and a set union over the
            last two, tagged by side, returns no asymmetric path. Nothing
            entered the set and nothing left it. The ten in the tail are
            named here so the sentence can be checked against something:
            tests/test_s172_p2_hero_stat.py 3,
            docs/RUNTIME_TRACE_EMISSION_DESIGN.md 3,
            docs/VERIFIER_CORE_INTEGRITY_DESIGN.md 2, and seven carrying one
            each, website/docs/index.html, tests/test_s237_nginx_config.py,
            scripts/rule0.sh, README.md, docs/SMT_VERIFICATION_DESIGN.md,
            docs/MEMORY_PHASE1_DESIGN.md and docs/EU_AI_ACT_COMPLIANCE.md.
            D319-7 names none of its eleven and so could not be checked
            against itself. THE SENTENCE AT 3985 STAYS ON THE PAGE AS
            WRITTEN, which is the rule D319-7 and D319-8 applied to D318-6
            and D318-10. FG-S321-F.

    D320-6  THE SUBJECT SHAPES RECONCILE AND BOTH PRIOR FINDINGS ARE TRUE.
            Measured on both S320 subjects in S321: the subject through awk
            length 152 and 122, the subject through wc -c 153 and 123, the
            whole body through wc -c 154 and 124. The body carries two
            newline bytes, confirmed by wc -l returning 2 on it. FG-S319-F
            compared the body with the subject BOTH through wc -c and got
            one. FG-S320-H compared the body through wc -c with the subject
            through awk length and got two. The delta is a property of the
            pair of shapes and not of the subject, which is R2 stated in
            measurements instead of prose. The family over the last twenty
            subjects runs 85 to 153, re-measured in S321 with both S320
            subjects now inside the window.

    D320-7  THE CENSUS THAT COUNTS ITSELF, MEASURED AGAIN. Tracked
            PYTEST_FLOOR occurrences: 78 at e5e5430, 81 at 16e5ae9, 81 at
            6470109, 81 at 20922b6 and 86 at 1b2fd6a. D319-7 predicted 86
            for after its own landing and 86 is what landed. This document
            holds 17 of the 86. THIS ENTRY CARRIES 3 OCCURRENCES OF THE
            TOKEN, so the tracked count reads 89 once it lands and this
            document holds 20. Those figures are arithmetic over 86 and
            17, declared here and settled at the gate that follows the
            append, not by this sentence. THE VALUE IS 2722, IT IS DECLARED
            AT LINE 70 OF scripts/release.py, AND IT DOES NOT MOVE IN THIS
            ARC. The live suite over tests/ is 2871 passed and 12 skipped, a
            gap of 149.

    D320-8  WHAT S320 REPORTED THAT THIS SEAT CANNOT RE-MEASURE, AND WHY IT
            IS IN THE LEDGER ANYWAY. The handoff files are not tracked in
            the repository; they exist only as the operator's saved copies,
            so findings not written here are written nowhere the repository
            can reach. What follows is transcribed from a file named
            NOUS_SESSION_320_HANDOFF.md at
            77d33aaa96713dbd3812bf7c75fc8383c0cabffbfeff062ed4adb5b81224a549
            15720 bytes and 339 lines. TWO PATHS WERE MEASURED IN S321 AND
            THEY AGREE, with each other and with the figure the operator
            declared at the session opening, which is the check FG-S320-F
            argues for. It is TESTIMONY AND NOT MEASUREMENT. Nothing in
            D320-1 through D320-7 depends on it. Twenty-six gates, 433
            assertions predicted, 427 hit, six missed, 68 declined and all
            sixty-eight measured. The D319 entry moved in 41 chunks and the
            P3 file in 14, each chunk with a running sha, and the T3b paste
            ran twice with the second run printing REFUSED PRECONDITION
            against a real payload rather than a fixture.

    D320-9  THE COLLECTION ROOT, AND WHAT MEASURING IT LOCATED. Bare pytest
            collects 3021 items and pytest tests/ collects 2883. The suite
            figure this arc reports is the tests/ one, which
            scripts/rule0.sh fixes by construction at its line 48, and 2871
            passed plus 12 skipped is that 2883. pyproject.toml declares no
            testpaths and 23 collectable files sit outside tests/. S320
            measured this while settling FG-S320-J and recorded that the
            four order-dependent failures in tests/test_inject_message.py
            pass under tests/ and fail under a bare root run, which locates
            the contaminator S312 could not identify inside the 138
            root-level items collected first. NOTHING WAS DONE ABOUT IT,
            this entry does not scope it in, and 138 is arithmetic over 3021
            and 2883.

    D320-10 THE STANDING RULES S320 ADDED, RECORDED SO THEY LIVE SOMEWHERE
            THE REPOSITORY CAN REACH. R16, a count is bound to the commit
            that produced it, from FG-S320-A. R17, the collection root is
            part of the set, from FG-S320-J. R18, read the instrument before
            predicting what it probes, from FG-S320-J and FG-S320-K. R19, a
            negative control asserts its delta and not the absolute set,
            from FG-S320-I. R20, sweep by anchor family and not by the
            counters you know, from FG-S320-E. R21, a name is not an
            identifier, from FG-S320-F and FG-S320-G. Three of the six were
            paid for twice in S321, under FG-S321-A, B and D.

    D320-11 THE ORDER AND THE STOPPING RULE. This entry, then the seal. The
            arc's plan completed in S320 and the F1 class is closed for
            scripts/release.py, repaired at four sites and locked by a test
            that reads the whole file. What follows the seal is an operator
            decision and not a seat choice; if the operator brings nothing,
            the plateau is named and the session stops rather than
            manufacturing an arc from the board. The entry that records what
            S321 did belongs to the next seat, which is the precedent D318-9
            set and D319-10 applied.

    D320-12 THE STATE THIS ENTRY WAS WRITTEN AT. HEAD 1b2fd6a equal to
            origin/main, 66 commits ahead of v5.78.0, pip 5.78.0 and both
            servers reporting 5.78.0 through the health path
            scripts/rule0.sh probes at its line 39. Suite over tests/ 2871
            passed, 12 skipped. claim_lint rc 0 over 421 files, 0
            violations, 3 declared proof legs. served_mirror_check rc 0,
            CLEAN, 331 tracked, 5 orphans. Porcelain 2, both untracked and
            both known. Tracked scripts/*.py 17, tests/*.py 303, website/*
            331. The append seam re-measured rather than carried: 29 entry
            heads, 29 blank-preceded, 0 text-preceded, first head at 504,
            trailing blanks 0, last line 19 bytes, last byte a newline. The
            target is root:root 644 and the docs directory is
            aetherlang:aetherlang 755.

    FINDINGS RECORDED IN S320 AND NOT CARRIED BY D319, WHICH SEALED BEFORE
    THEY OCCURRED. Transcribed under D320-8 and re-derived only where this
    entry says so.

            FG-S320-H  seat error. A body byte count was predicted at 153
                       and measured 154. FG-S319-F had measured the body
                       against the subject both through wc -c; the seat
                       applied that delta of one to a subject measured
                       through awk length, which does not count the trailing
                       newline. Re-measured and reconciled in S321 under
                       D320-6.
            FG-S320-I  seat error, found by the fixture before transfer.
                       P3's three negative controls asserted an absolute
                       offender list, so a single planted regression made
                       six tests fail. An arm that exists to confirm cannot
                       be collateral. Repaired to assert the delta, and the
                       three failing sets are now disjoint. FG-S319-I class.
                       R19 was written from it.
            FG-S320-J  seat error. The suite total was predicted over a run
                       made from the repository root, which collects 3021
                       items against 2883 under tests/. RULE 0 had printed
                       TESTPATHS 0 and 23 collectable files outside tests/,
                       and the seat scored both and then assumed the
                       collection root anyway. R17 and R18 were written from
                       it.
            FG-S320-K  seat error. The seal gate probed a health path the
                       seat invented, /health, where scripts/rule0.sh probes
                       /v1/health at its line 39. The version leg returned
                       NotFound and was left unmeasured. Same position as
                       FG-S319-K reached by a different route, and it shares
                       one cause with FG-S320-J: an instrument was run
                       without being read.

    FINDINGS RECORDED IN S321, WHICH ARE THIS SEAT'S OWN.

            FG-S321-A  seat error. Five distinct enclosing definitions were
                       predicted for the check=False census and six were
                       measured. Five is bound to the shape top-level phase_
                       definitions carrying check=False; the census shape is
                       the enclosing definition of every site and includes
                       run, which D319-6 and P3 both exclude by name. A
                       number moved across shapes. R2.
            FG-S321-B  seat error, same cause. The floor declaration leg was
                       predicted at 224, which is the first of the indented
                       uses D319-8 names. The leg is anchored at column zero
                       and printed 70, the declaration. 224 to 226 were not
                       re-measured in S321 and are not carried by this
                       entry.
            FG-S321-C  operator error, brought by the operator. A payload of
                       the D319 entry was verified at 11ee22f6, 19673 bytes,
                       327 lines, and cited for an object that landed at 352
                       lines. The measurement was correct for the object in
                       hand; the identity was the unmeasured part. Same
                       class as FG-S320-G, second occurrence, and it was
                       named before the seat used the number.
            FG-S321-D  seat error, same cause as A and B. The maximum line
                       length of the D319 span was predicted at 79, which is
                       the maximum over the whole document. A maximum over a
                       superset is an upper bound on a subset and not its
                       value. The span measures 76.
            FG-S321-E  seat error. A gate was declared as fifteen assertions
                       in twelve predictions and three declinations. Counted
                       atomically against the legs the paste emitted it is
                       nineteen and three, with five further legs carrying
                       neither a prediction nor a declination. The split was
                       arithmetic performed while writing and was not
                       checked against the paste. It recurred once in the
                       following gate, on one leg.
            FG-S321-F  not a seat error of this session. The file counts in
                       D319-7 are wrong and the correction is D320-5.
            FG-S321-G  seat error, caught by the anchor-family sweep of this
                       payload before any write, which is the check R20
                       exists for and which FG-S320-E is the precedent of.
                       Prose wrapping put a prior finding code at the start
                       of one twelve-space line inside D320-3 and another at
                       the start of one inside D320-10, which is the exact
                       indent an FG head carries. Two foreign counters would
                       have moved silently and the verification gate would
                       have shown two unexplained misses after the write.
                       Both were reworded, the sweep was run again, and it
                       returns zero foreign anchors.

    WHAT THIS ENTRY DOES NOT DO. It writes no code. It does not move
    PYTEST_FLOOR. It does not touch DN[5]. It does not arm the ceremony
    change and nothing in it constructs a route to one. It does not repair
    the two open members of the class in scripts/claim_lint.py, a file of
    1016 lines, and it does not scope them in. It does not amend the frozen
    fixture. It does not narrow the rule of D318-4 to per call site. It does
    not clear the two untracked paths out of porcelain. It edits nothing:
    the correction in D320-5 is an append and the sentence it corrects stays
    on the page as written, true when it was written and wrong in its count.
    336-700 of scripts/release.py remains unread and the bare except in that
    region is named as unread rather than characterised.

  - S321 the D320 entry lands, the census that counted its own effect is
    settled against both revs, and the understatement in FG-S321-E is
    corrected by append

    THIS ENTRY IS WRITTEN IN S322 ABOUT S321. Every number below was printed
    by an instrument in S322 at HEAD e5100ba unless D321-5 marks it as
    testimony. D320-11 assigns this entry to this seat and D318-9 set that
    precedent; D319 and D320 are the two instances before this one.

    THE INSTRUMENTS. RULE 0 in two pastes, 93 assertions predicted and 20
    declined, all twenty measured. Then three read-only gates and no write
    before the append. The first read the D320 entry at 4223-4514 whole, the
    rule at 2803-2822 that governs a correction, and the seam. The second
    measured the commit e5100ba, the document at its parent 1b2fd6a, and the
    tracked floor census at both revs. The third measured the append target,
    its directory and the conditions of the write.
    docs/GLM_SUPERSESSION_DESIGN.md at sha a18d28c9, 4514 lines, 261526
    bytes, MAXLEN 79, NONASCII 0, TRAILWS 0, TABS 0, worktree equal to
    origin/main. scripts/release.py at sha d292bc82, 832 lines, UNTOUCHED IN
    S320, S321 AND S322. 336-700 of that file remains unread and nothing
    below rests on that region.

    D321-1  WHAT S321 SHIPPED, MEASURED AT e5100ba AND NOT INHERITED. One
            commit on origin/main, one file, 293 insertions, 0 deletions,
            measured through diff-tree numstat. Its parent is 1b2fd6a and
            exactly one commit separates them. The D320 entry occupies
            4223-4514, 292 lines, 19206 bytes, sha d6c7b52b, read from the
            worktree and again from the origin/main blob and equal. THE TWO
            HUNDRED AND NINETY-THIRD INSERTION IS THE BLANK SEPARATOR at
            4222, which measures one byte through wc -c; 292 plus one is
            that 293 and the addition is this seat's. The document went from
            4221 lines and 242319 bytes at the parent to 4514 and 261526 at
            HEAD, and 261526 minus 242319 is 19207, which is the span's
            19206 plus the separator; both subtractions are this seat's.
            HEAD is 67 commits ahead of v5.78.0 and no tag was cut.

    D321-2  THE SUBJECT THROUGH THE THREE SHAPES D320-6 SETTLED. Measured on
            the subject of e5100ba: 148 by awk length, 149 by wc -c, and 150
            by wc -c over the whole body, on which wc -l returns 2. The
            delta of one and the delta of two are the two that D320-6
            reconciled, reproduced here on a subject D320-6 never saw. The
            family over the last twenty subjects runs 85 to 153, re-measured
            at HEAD with this subject inside the window.

    D321-3  THE CENSUS THAT COUNTED ITS OWN EFFECT IS SETTLED. D320-7
            declared at 4346-4350 that the entry it was writing carried
            three occurrences of the floor token, so the tracked count would
            read 89 and the document 20 once it landed, and it named the
            gate after the append as the place that would settle those
            figures rather than settling them by its own sentence. Measured
            in S322 at both revs: 86 tracked at 1b2fd6a and 89 at e5100ba,
            17 in the document and 20, and the file set fifteen at both. THE
            DECLARED FIGURE HELD AND IT IS NOW MEASURED RATHER THAN
            ARITHMETIC. THE VALUE IS 2722, IT IS DECLARED AT LINE 70 OF
            scripts/release.py, AND IT DOES NOT MOVE IN THIS ARC. THIS ENTRY
            NAMES THAT TOKEN NOWHERE, so it carries zero occurrences of it
            and the two counts do not move: 89 tracked and 20 in the
            document after this lands, which is the same measurement rather
            than a new arithmetic. The cost is stated rather than hidden: a
            reader grepping for the token will not find this entry, and the
            settlement above is what such a reader would be looking for.

    D321-4  THE CORRECTION TO FG-S321-E, WHICH IS AN APPEND AND NOT AN EDIT.
            That finding sits at 4482-4489, occurs once in the whole
            document by a literal count, and is at the same line when the
            document is read from the origin/main blob instead of the
            worktree. Its closing sentence says the pattern recurred once in
            the following gate, on one leg. IT RECURRED FOUR TIMES. The four
            are transcribed under D321-5 and are testimony rather than
            measurement: a gate declared at fifteen that emitted
            twenty-seven legs, a decode gate declared at twenty-three that
            emitted twenty-two, a candidate-build gate declared at
            thirty-four that emitted forty-five, and one further leg in a
            third gate covered by neither its prediction list nor its
            declination list. THE SENTENCE AT 4488 STAYS ON THE PAGE AS
            WRITTEN. It was true of the gate it named and it understated the
            class the finding describes. This is D314-5 at 2803 applied to a
            finding the ledger wrote about its own seat: the entry that
            corrects a prior sentence says which of the two it is doing, and
            the prior sentence is not edited.

    D321-5  WHAT S322 CANNOT RE-MEASURE, AND WHY IT IS IN THE LEDGER ANYWAY.
            The handoff files are not tracked in the repository; they exist
            only as the operator's saved copies, so a finding not written
            here is written nowhere the repository can reach. What follows
            is transcribed from a file named NOUS_SESSION_321_HANDOFF.md at
            ad53b4725ff98ee45ef30e98c3e1916a454dbbe801927a33fb2cb9dd311b5a95
            of 13671 bytes and 286 lines, verified against the digest the
            operator declared before any of it was read. IT IS TESTIMONY AND
            NOT MEASUREMENT, and nothing in D321-1 through D321-4 depends on
            it. Sixteen gates, 387 assertions predicted, 384 hit, three
            missed, 46 declined and all forty-six measured. The three misses
            are FG-S321-A and FG-S321-B in RULE 0 and FG-S321-D in the first
            read gate, and every gate from the second onward scored clean.
            The D320 payload moved in 37 chunks across four pastes with a
            running byte count and a running sha for each. The first
            transfer paste ran twice and the second run printed REFUSED
            PRECONDITION TARGET EXISTS against a real target rather than
            against a fixture.

    D321-6  THE SEVEN FINDINGS OF S321 ARE ALREADY ON THE PAGE, WHICH IS
            WHY THIS ENTRY DOES NOT RESTATE THEM. They occupy 4457-4502
            and the anchored sweep over the whole document returns seven
            for that family. Three of them share one cause, those three
            being FG-S321-A, FG-S321-B and FG-S321-D, and the cause is a
            number carried from the shape that produced it onto a
            different shape, which is R2. NOTHING OF S321 IS OWED FORWARD
            EXCEPT THE CORRECTION IN D321-4.

    D321-7  THE STANDING RULE S321 ADDED, RECORDED SO IT LIVES SOMEWHERE THE
            REPOSITORY CAN REACH. R22, count the legs from the built paste
            and not from the intent. An assertion count declared before the
            paste exists is a self-referential counter: the paste grows and
            the number does not, so the legs are counted with an instrument
            after the paste is built. D320-10 did the same for R16 through
            R21, and this completes the recorded set at twenty-two.

    D321-8  THE CLASS AND ITS CENSUS RE-MEASURED AT e5100ba, WHERE ONE SET
            GIVES THREE NUMBERS. Seven check=False sites in
            scripts/release.py at 116, 139, 158, 204, 257, 300 and 344,
            sitting in six enclosing definitions of which five are phases:
            phase_preflight twice, phase_pytest, phase_pyflakes,
            phase_claim_lint and phase_sidecar_integrity. run at 116 is the
            sixth and is not a phase. Thirteen definitions named phase_ at
            column zero and 17 column-zero definitions in all, unchanged
            from D320-4. SEVEN SITES, SIX DEFINITIONS, FIVE PHASES ARE THREE
            TRUE NUMBERS OVER ONE SET, differing only in the shape that
            produced them, which is the cause behind FG-S321-A, FG-S321-B
            and FG-S321-D printed live at the opening gate of S322. The
            class stands at six measured members: four closed and locked by
            a test that reads the whole file, two open in
            scripts/claim_lint.py, a file of 1016 lines, and both outside
            this arc.

    D321-9  THE PAYLOAD BUILDER GAINS A PRECONDITION INSTEAD OF A
            RULE. FG-S321-G recorded prose wrapping that put a prior
            finding code at the start of a twelve-space line, the
            exact indent an anchor head carries, twice in one payload,
            and the repair was to reword. The class fired twice again
            while this payload was built: a four-space line began with
            a decision code belonging to another family, and a
            twelve-space line began with a finding code of S321;
            rewording the second moved the break and the same line
            start re-formed at its new position. THE REPAIR IS
            MECHANICAL AND NOT EDITORIAL. The builder wraps a block,
            sweeps the lines it produced by anchor family, narrows the
            width and wraps again until no line start can form an
            anchor it did not intend, and REFUSES to emit the block at
            all if no width satisfies that. This is the shape R4
            requires of a write gate, a precondition that refuses and
            produces nothing, moved one step earlier in the chain:
            from the gate that writes the bytes to the instrument that
            composes them. THE BUILDER IS NOT TRACKED IN THIS
            REPOSITORY and this item is the whole of its record, which
            is the cost D321-5 names applied to a tool rather than to
            a finding.

    D321-10 THE ORDER, AND WHAT THIS ENTRY DOES NOT ASSIGN. This entry, then
            the seal. The arc's plan completed in S320, D320 recorded it,
            and this entry records the session that wrote D320. THE CHAIN IS
            NOT EXTENDED HERE. D318-9, D319-10 and D320-11 each assigned the
            next entry to the next seat; this entry assigns none, because an
            entry whose only subject is the entry before it is a plateau
            wearing the shape of an arc. The findings of S322 are recorded
            below rather than deferred to a successor that would exist only
            to carry them. What follows the seal is an operator decision and
            not a seat choice. THE COST OF STOPPING THE CHAIN IS DECLARED
            HERE RATHER THAN LEFT TO BE FOUND: the findings of every gate
            after this payload was built, meaning the transfer, the append,
            the commit and the push, cannot enter this entry, so they land
            only in the handoff, which is not tracked and is therefore
            written nowhere the repository can reach, which is exactly what
            D321-5 says that phrase means. They are owed to the next entry
            if the operator brings work, and if he brings none they are the
            declared cost of this decision rather than an oversight for a
            later seat to find.

    D321-11 THE STATE THIS ENTRY WAS WRITTEN AT. HEAD e5100ba equal to
            origin/main, 67 commits ahead of v5.78.0, no tag cut, pip 5.78.0
            and both servers reporting 5.78.0 through the health path
            scripts/rule0.sh probes at its line 39. Suite over tests/ 2871
            passed and 12 skipped, 2883 collected under tests/ and 3021 from
            a bare root, pyproject.toml declaring no testpaths and 23
            collectable files outside tests/. claim_lint rc 0 over 421
            files, 0 violations, 0 allowlisted, 3 declared proof legs.
            served_mirror_check rc 0, CLEAN, 331 tracked, 5 orphans.
            Porcelain 2, both untracked and both known. Tracked scripts/*.py
            17, tests/*.py 303, website/* 331. certbot.timer and
            nous-serve-integrity.timer both active, no failed units, both
            served surfaces 200. The append seam measured rather than
            carried: 30 entry heads, 30 of them blank-preceded, 0
            text-preceded, trailing blanks 0, last line 57 bytes, last byte
            a newline. The target is root:root 644 and the docs directory is
            aetherlang:aetherlang 755, both read from stat in this session
            rather than carried from a prior.

    FINDINGS RECORDED IN S322, WHICH ARE THIS SEAT'S OWN. The score below is
    bounded at the gate that built this payload and is partial by
    construction: over five gates, 144 assertions predicted, 144 hit, none
    missed, 30 declined and all thirty measured, with six further legs
    measured at the byte gate that carried neither a prediction nor a
    declination. The totals are arithmetic over the per-gate counts, and the
    gates after this one are not in them.

            FG-S322-A  operator, and it cost nothing. The second RULE 0
                       paste ran twice and both runs stand in the
                       transcript. Every leg printed the same value across
                       the two runs except three elapsed-time fields, so an
                       accidental repetition served as a reproducibility
                       control and it passed. The paste is read-only and
                       nothing moved.

    WHAT THIS ENTRY DOES NOT DO. It writes no code. It does not move the
    floor. It does not touch DN[5]. It does not arm the ceremony change and
    nothing in it constructs a route to one. It does not repair the two open
    members of the class in scripts/claim_lint.py and it does not scope them
    in. It does not amend the frozen fixture. It does not narrow to per call
    site the rule that D318-4 states and D319-5 and D320-3 repeat. It does
    not clear the two untracked paths out of porcelain. It edits nothing:
    the correction in D321-4 is an append and the sentence it corrects stays
    on the page as written, true of the gate it named and short of the class
    it belongs to. 336-700 of scripts/release.py remains unread and the bare
    except in that region is named as unread rather than characterised.

  - S322 the P19 object is read whole, the M88 proposal collapses on
    measurement at two levels, and the rule that binds the README to the
    version oracle is decided before it is written

    THIS ENTRY IS WRITTEN IN S322 ABOUT S322, which is the first entry in
    this chain whose subject is its own session. Every number below was
    printed by an instrument in S322 at HEAD 63bfa9a. The work was
    brought by the operator after the seal of that session, which is the
    condition D321-10 named when it declined to assign a successor.

    THE INSTRUMENTS. Four read-only gates and no write. A scoring gate over
    the S263 remediation list, 39 fixed-string probes with a positive
    control that printed 89 and a negative control that printed 0. A reading
    gate over the six probes whose count did not decide them. Then two gates
    on the object itself: the phase, the README version family and the
    oracle; then the test file whole and the run helper whole.
    scripts/release.py at sha d292bc82, 832 lines, UNTOUCHED.
    tests/test_version_consistency.py at sha d7b79aef, 138 lines.

    D322-1  WHERE P19 CAME FROM, AND IT IS A MEASUREMENT AND NOT A FORECAST.
            The scoring gate declared its SET as tracked paths at 63bfa9a
            under a named pathspec, and its SHAPE as fixed-string literal
            match, blind to rewording that keeps a defect and to any finding
            stated as an absence. The probe for the string README inside
            scripts/release.py returned zero. README.md carries 5.77.0 while
            _version.py carries 5.78.0. The previous release already forgot
            the README; nothing in the pipeline saw it then and nothing
            would see it at the next tag.

    D322-2  THE M88 PROPOSAL COLLAPSES ON MEASUREMENT, AND THIS ENTRY
            NARROWS IT RATHER THAN FALSIFYING IT. M88 proposed a
            version-consistency check modelled on an existing phase. Two
            levels, both measured. FIRST: that phase is a runner. It
            occupies 237 to 243, nine lines counted with the blanks, takes
            no arguments, and is called bare at 791 -- the only phase in
            main that never receives the version, where registry coverage,
            the wheel gate, the install smoke and the provenance leg all do.
            SECOND: the set it runs lives entirely inside the test file,
            which mentions glob zero times, rglob zero times and parametrize
            zero times, and reaches exactly one path, a hardcoded Path at
            its line 35. THERE IS NO LIST OF FILENAMES TO EXTEND IN EITHER
            FILE. M88 was not wrong when it was written. It was a proposal
            resting on an unmeasured assumption about a phase nobody had
            opened, and it cited a line that had already moved: :215 then,
            237 now. D314-5 applied to an inherited proposal rather than to
            an inherited sentence.

    D322-3  THE PHASE IS A GATE WITH DELEGATED CONTENT, AND THE NEW RULE
            INHERITS THAT GATE FOR NOTHING. The run helper at 105 declares
            its check parameter defaulting to true; it calls subprocess with
            checking off at 116 and then decides for itself at 119, printing
            both streams and raising before the caller can continue. Line
            239 passes no check argument, so it takes that default. Phase 4
            therefore stops the release when the test file goes red. THIS IS
            THE SHAPE THE F1 CLASS CLOSED ELSEWHERE, deciding on the exit
            state instead of discarding it, arrived at here by reading
            rather than by repair. Anything added to that test file is gated
            at release the moment it lands, and no line of
            scripts/release.py is required for it.

    D322-4  THE SEVEN SOURCES THE FILE ALREADY BINDS, AND WHAT IS ABSENT
            FROM THEM. The file is 138 lines with 8 column-zero definitions
            of which 7 are named test_, and it collects 7 items and passes 7
            run alone. Its own docstring enumerates seven sources: the
            version string, the version tuple, the CLI re-export, the API
            re-export, the package re-export, the installed metadata, and
            the pyproject dynamic declaration. Every one of the seven is an
            attribute comparison or a parse against the version string. NO
            SURFACE OUTSIDE CODE IS IN THAT SET. The string README appears
            zero times in the file. The README is therefore a NEW
            CONSTRUCTION and not an extension of an existing one, and saying
            which of the two it is was the whole question this reading
            answered.

    D322-5  THE MODEL THE FILE ALREADY CONTAINS. One test at 107 to 123
            reads the text of a file, iterates its lines, keeps context in a
            boolean, applies a rule that is sensitive to that context, and
            fails through an explicit call whose message names the remedy.
            IT CARRIES NO LINE NUMBER. It is the only test in the file that
            is not an equality, and it is the construction the new rule
            copies. The requirement that a check survive the movement of
            lines is therefore satisfied by something already in the tree
            rather than by something invented here.

    D322-6  THE THREE CONSTRAINTS ON THE SHAPE, EACH ONE MEASURED RATHER
            THAN ARGUED. FIRST, no line numbers: M88 named 12, 306 and 334,
            and the values sit at 12, 305 and 333 today, so the citation was
            already dead when it was read. SECOND, no equality over every
            version-shaped token: the README carries ten such lines and
            seven distinct values, of which six are historical and correct
            -- anchoring arrived at one release, public verification at
            another, the signing dependency became a base dependency at a
            third. An equality over all of them yields six false positives,
            and six false positives in a release gate are worse than the
            defect they would be added to catch. THIRD, the count depends on
            the shape: three lines carry the stale value and four tokens do,
            because line 333 carries it twice, once in prose and once inside
            the release tag URL. THE RULE MUST DECLARE WHICH OF THE TWO IT
            COUNTS.

    D322-7  WHAT SEPARATES THE TWO CLASSES, MEASURED IN THE BYTES RATHER
            THAN INFERRED FROM INTENT. The historical statements carry
            marks: the words since v at 24, 41 and 59; a trailing plus sign
            at 215 and 243; a JSON sample at 186. The three current-version
            claims share no syntax with each other -- an ASCII banner at 12,
            a heading at 305, prose beside a URL at 333 -- but not one of
            them carries any of those marks. The separation is therefore
            available without chasing the syntax of each site, and that is a
            property of these bytes at this commit, not a law.

    D322-8  WHAT THE RULE DOES, WHICH IS NOT THE SAME QUESTION AS HOW IT
            FINDS ITS SITES, AND IT IS A DECISION. Equality against the
            version string. THE CONSEQUENCE IS A NEW OBLIGATION IN THE
            RELEASE PROCESS AND NOT ONLY A NEW TEST: every version bump must
            edit README.md, or the release stops at phase 4. That is
            precisely the point of P19 -- a release that forgets the README
            can no longer be cut -- and it is written here as a decision
            with its cost stated, rather than discovered by whoever meets it
            first on a red pipeline.

    D322-9  WHAT MOVES WHEN THE CODE LANDS, DECLARED HERE AND SETTLED AT THE
            GATE THAT FOLLOWS IT. Collection over the test directory reads
            2883 today and would read 2884; the suite reads 2871 passed and
            12 skipped and would read 2872 and 12. Both are arithmetic
            performed while writing this entry. THE FLOOR IS 2722, IT DOES
            NOT MOVE IN THIS ARC, AND NOTHING HERE PROPOSES THAT IT SHOULD.
            This entry carries exactly one occurrence of the PYTEST_FLOOR
            token, counted by instrument over the built payload and not from
            the intent, so the tracked count reads 90 and this document
            holds 21 once it lands; those two figures are arithmetic over
            the 89 and the 20 that the seal of S322 measured, and they are
            settled at the gate after the append and not by this sentence.

    D322-10 THE ORDER, AND ONE LEG THIS ENTRY RETIRES. This entry, then the
            code, which is D309-3 applied to a rule rather than to a tool.
            One object: the README. The findings below include the four that
            D321-10 declared would land only in an untracked handoff if no
            further work came; work came, so they land here and that debt is
            discharged. AND THE TERMINATOR MOVES: the seal of S322 recorded
            that the S322 head line must print empty and that the D322
            family must count zero. Both of those are retired by this entry.
            The next seat checks the S323 head line and the D323 family
            instead. AND THE SAME COST FALLS ON THE CODE THIS ENTRY
            AUTHORISES. Every prior landing of code was recorded by the
            entry that followed it. This one will not be, because the chain
            is broken here and this entry does not reassign it, so what that
            code does lands only in an untracked handoff unless the operator
            brings further work -- the same declared cost as the findings
            below, owed to the next entry if there is one.

    FINDINGS. The first four were named in S322 after the D321 payload was
    frozen and could not enter it; D321-10 declared exactly that and owed
    them forward. The last four were named after that payload landed: three
    while reading the object of this entry, and one at the gate that built
    this one.

            FG-S322-B  seat error, caught before emission. The
                       transfer-paste generator joined every clause with a
                       semicolon and a space and so produced an else
                       followed by a semicolon, which sh, dash and bash all
                       reject. All four transfer pastes failed the syntax
                       check. Had that check been skipped, the first
                       transfer gate would have failed on the operator's
                       terminal after its directory had already been
                       created.

            FG-S322-C  operator, no consequence. The fourth transfer paste
                       ran three times and the second and third runs printed
                       a precondition refusal against a real target rather
                       than a fixture, writing nothing. The refusal also
                       gave a free second reading of the file digest, and it
                       agreed with the digest the applying run had printed.

            FG-S322-D  operator, no consequence, and it demonstrated
                       something no fixture had. The commit gate ran twice
                       and the second run refused. WHICH ARM FIRED IS THE
                       INFORMATION: after a successful commit the index
                       still holds the blob, so the guard on the blob
                       passes, and only the guard that counts the staged set
                       sees there is nothing left to commit. A chain
                       carrying the blob guard alone would have attempted an
                       empty commit on a re-paste. R14 confirmed by
                       accident.

            FG-S322-E  seat error, R18. The seal gate predicted both servers
                       reporting their version and then piped the RULE 0
                       script through a tail that keeps only its last four
                       sections, dropping both health blocks. The seat had
                       read that script whole at the opening gate and chose
                       the truncation anyway. A leg the built paste cannot
                       emit is not a leg, and two predictions were left
                       unmeasurable rather than missed. Closed in a separate
                       paste immediately after.

            FG-S322-F  seat error, R2. The length of the operational scope
                       exclusion list in the signed governance manifest was
                       predicted at eight and measured at nine. The S263
                       list cites its members by one-based ordinal; the seat
                       read an ordinal as a cardinality. The two indexings
                       agree once named: that document's sixth exclusion is
                       index five, and its eighth is index seven. A number
                       moved across shapes in the session that wrote D321-6
                       about exactly that.

            FG-S322-G  not a seat error of this session. M88 states three
                       sites in the README and names three line numbers.
                       Measured at 63bfa9a: three lines carry the stale
                       value and four tokens do, because one line carries it
                       twice, and the three line numbers had each moved.
                       Both counts are true under their own shape, which is
                       why D322-6 requires the rule to declare which one it
                       counts.

            FG-S322-H  not a seat error of this session, and NOT PART OF
                       THIS OBJECT. The pipeline docstring at line 20 of
                       scripts/release.py states a count for the
                       version-consistency test file. Measured: 8
                       column-zero definitions, 7 named test_, 7 collected,
                       7 passed. The stated count matches none of the three
                       shapes; the eighth definition is a helper. Same
                       family as the obligation counts the S263 list
                       records. RECORDED AND NOT REPAIRED: one object per
                       arc.

            FG-S322-I  operator, no consequence, and it measured a property
                       this chain had been resting on unmeasured. The
                       instruction message authorising this payload arrived
                       twice, identically. A CHAT MESSAGE CARRIES NO
                       PRECONDITION, so the guard applied was the one
                       available: read the digest of the artifact already
                       built, refuse to rebuild, and then run the builder
                       again as a control and compare. The rebuild was
                       byte-identical. THE BUILDER IS DETERMINISTIC, and
                       that is now measured rather than assumed -- every
                       earlier gate in this chain that rebuilt an artifact
                       and compared a digest rested on that property without
                       a measurement behind it.

    WHAT THIS ENTRY DOES NOT DO. It writes no code; the code follows it,
    which is the whole point of writing it first. It does not touch
    claims.toml, whose forbidden objects are a separate object with a trap
    of their own: an addition made before the wording is corrected turns the
    claim-lint phase red and stops the release. It does not touch the two
    untracked paths, the floor, DN[5] or the ceremony change, and it
    constructs no route to any of them. It does not repair the pipeline
    docstring recorded above. It does not amend the frozen fixture. It edits
    no sentence already on the page: the narrowing of M88 in D322-2 is an
    append, and M88 stays as written, true of what it could see.

  - S323 the enforcement-claim surface is measured in both directions, the
    subject split is mechanical, and the wrap that hid two sites is named

    THIS ENTRY IS WRITTEN IN S324 ABOUT S323, which returns the chain to the
    convention D322 departed from. D322-10 recorded that the code it authorised
    would land only in an untracked handoff unless the operator brought further
    work. Work came, and this entry is that declared condition being met. The
    debt D322-10 named is discharged here.

    THE PROVENANCE OF EVERY NUMBER BELOW, WHICH IS THE FIRST THING THIS ENTRY
    OWES. Nothing in the S323 part of this entry was measured in S324. Every
    figure was printed by an instrument in S323 at HEAD 0fd92a3 and travels in
    NOUS_SESSION_323_HANDOFF.md, sha 15cf25e8, 12119 bytes, 267 lines, byte-
    verified at the opening of S324 before it was read. That handoff is
    untracked and is not in the repository. Where it carries a number without
    the shape that produced it, this entry says so instead of repeating it as
    though it could be reproduced. That is R24 applied to this entry by its own
    author.

    THE INSTRUMENTS OF S323, AS THE SEAL RECORDS THEM. Two commits landed.
    4d9a806 marked the current-version sites in README.md, bound them to
    _version, and moved the stale claims to 5.78.0. 0fd92a3 gave their subject
    to seventeen unqualified monitor claims across six generator sources and
    decomposed the two 5.60.1 replay locks. At the seal: HEAD 0fd92a3, origin
    equal, AHEAD_OF_TAG 71, no tag cut, suite 2872 passed and 12 skipped, LINT
    rc 0 over 421 files with 0 violations, MIRROR rc 0 CLEAN over 331 tracked
    files with 5 orphans, PORCELAIN 3.

    D323-1  THE OBJECT WAS A SURFACE AND NOT A FILE, AND THAT CHOICE IS WHAT
            MADE THE CENSUS POSSIBLE. The named question was the full set of
            surfaces that speak falsely about whether NOUS enforces, in BOTH
            directions. Every earlier pass had asked whether a particular
            document was correct. Asking instead which sentences exist,
            anywhere, and what subject each one carries, is what turned a
            reviewing task into a measuring one.

    D323-2  THE CENSUS, AND THE ONE NUMBER IN IT THAT CANNOT BE REPRODUCED.
            Axis A, the refusal of enforcement, fifteen fixed phrases, 245
            hits. Axis B, the opposite direction, eleven phrases, 87 hits,
            widened for the verbs at one site to 12. Axis C, the bare token
            COVERED over the whole tree, 35. THE FIFTEEN PHRASES OF AXIS A ARE
            WRITTEN IN NO SEALED DOCUMENT. The 245 is therefore a number whose
            shape did not travel with it, and no later session can rebuild that
            set. It is recorded here as a fact about S323 and must never be
            used as a target to reproduce. A census designed in one session and
            summarised in another carries its phrase list or it carries
            nothing.

    D323-3  THE SPLIT IS BY SUBJECT AND IT IS MECHANICAL, BUT AS THE SEAL
            RECORDS IT, IT DOES NOT CLOSE. The seal of S323 divides the axis by
            the subject each sentence gives: 11 SCOPED, where the sentence says
            the evidence layer is a monitor; 149 UNQUALIFIED, where it says
            NOUS is a monitor, which is the defect ADR-0010 created when it
            split the claim per article; and a remainder of 117, itself 94 not
            published and 23 published. THOSE THREE FIGURES SUM TO 277 AND NOT
            TO 245. That addition was performed while writing this entry. The
            sub-division closes: 94 and 23 make 117. The failure is at the
            upper level, and WHICH OF THE FOUR FIGURES DOES NOT BELONG CANNOT
            BE SETTLED BY ANY LATER SESSION, because the fifteen phrases that
            produced the 245 exist in no sealed document. The three subject
            classes are recorded here as measurements taken in S323; THEY ARE
            NOT A PARTITION OF 245 AND MUST NOT BE USED AS ONE. What is not in
            doubt is the mechanism: no line was classified by reading it for
            meaning, and the separator was already written in the tree with
            authority, in ADR-0010, which records that the one-line thesis ends
            and that every future document must carry the split or reintroduce
            the defect.

    D323-4  THE WRAP. THE MECHANISM NOBODY HAD FOUND IN NINE SESSIONS OF
            LOOKING. SUBJ_SPLIT_HITS 25: the sentence wraps, and the wrap is
            written INTO the template, so subject and predicate land on
            different lines of the emitted artifact. Twenty-two are the
            published verifiers. Three are source files, and two of those were
            invisible to every single-line census ever run:
            closure_ledger.py:20-21 and docs/CONTINUITY_LEDGER.md:10-11. THE
            INVENTORY WAS NOT BLIND TO LINES. It was blind to the SUBJECT, and
            then to the wrap. That is the retrospective explanation of the nine
            of D292-D1, and it is the reason a docs-oriented census kept coming
            back clean over an intact false sentence.

    D323-5  AN INHERITED CLAIM IS REFUTED, NOT MERELY LEFT UNCONFIRMED, AND THE
            DIFFERENCE MATTERS. docs/EU_AI_ACT_COMPLIANCE.md:189-190 reads that
            the intervene action surfaces the decision to a human operator and
            execution continues. That AGREES with intervention.py. The counter-
            direction claim lives at :193, where the block action halts
            emission of the event, and it carries a verb no phrase set in the
            census had. The suspicion about :189 that had travelled for several
            sessions is closed by reading, not deferred.

    D323-6  THE ONLY AUTOMATED CLAIM GUARD DOES NOT WATCH THIS AXIS AT ALL, AND
            ITS GREEN SAYS NOTHING ABOUT IT. In claims.toml the word monitor
            sits in allowed_claim_words, while enforce, guard and gate are in
            neither list; CLAIMLINT_ENFORCE_WORDS is 0. That is why 245 lines
            drifted for years under LINT rc 0. A single-axis guard returning
            zero is not coverage of any other axis, and reading the instrument
            before predicting what it probes is the rule that would have found
            this earlier.

    D323-7  THE TWO 5.60.1 REPLAY LOCKS FAILED FOR AN EDITORIAL REASON AND NOT
            A CRYPTOGRAPHIC ONE. They are not a reproducibility lock on the
            verifier; the verifier is copied from the published directory as an
            INPUT. One field is regenerated editorial prose: the rekor artifact
            boundary written by mint_release_vsa.py. The TOP-LEVEL boundary is
            copied from the SIGNED DSSE, cannot move, and stays under exact
            equality. E1 decomposed the single comparison into two: a semantic
            comparison with that one field normalised and everything else
            exact, and a canonicality self-check that re-serialises the on-disk
            file and compares it to itself, immune to any constant and firing
            on serializer drift. Mutation-proved: sha256, leafHash, logIndex
            and the top-level boundary all still caught; only the rekor
            boundary is hidden; re-indenting the published file turns the
            second check red.

    D323-8  E4, RECORDED AND NOT BUILT, AND THE REASON IS A PROPERTY OF
            IMMUTABLE RECORDS. Add boundaryId and boundaryDigest to that one
            artifact, matching the policyId and policyDigest already in the
            same file. INLINED PROSE IN AN IMMUTABLE RECORD CAN NEVER BE
            CORRECTED; CITED PROSE CAN. Once taken, the scrub in D323-7 becomes
            unnecessary. This is a decision owed to an Innovation Gate, not a
            change authorised here.

    D323-9  THE FOUR RULES S323 ADOPTED, EACH ONE PAID FOR BY A MEASUREMENT IN
            THAT SESSION. T5: an artifact is not transferred, it is reproduced;
            every message is produced token by token, and for base64 the
            failure is SILENT with the digest at the end as the only detection,
            so opaque blobs do not move through the message channel. R23
            refined by measurement: a bang is risky only outside true single-
            quote protection AND when the next character is not space, tab,
            newline or an equals sign; an opening parenthesis IS risky; single
            quotes nested inside double quotes do NOT protect. R24: a
            conclusion that travels in a handoff carries its shape or it
            carries nothing, because the other rules bind WITHIN a session and
            none binds BETWEEN. R25: a guard on a sentence reads the bytes its
            reader reads, established by 25 measured straddles.

    D323-10 R26, ADOPTED IN S324 WHILE THIS ENTRY WAS BEING PREPARED, AND IT IS
            THE FIRST RULE IN THIS CHAIN ABOUT AN INPUT. A THRESHOLD IS PART OF
            THE SHAPE. A gate that compares against a number declares WHERE THE
            NUMBER CAME FROM and WHAT SET IT GOVERNS. Over budget without
            provenance of the budget is the same failure as a number without an
            instrument, on the input side instead of the output side. The rules
            before it all bind what a message may assert; this one binds what a
            gate may assume. It was paid for by FG-S324-E below.

    D323-11 THE PREDICTION RECORD OF S323 AND THE THREE FAMILIES ITS MISSES
            FALL INTO. 575 declared, 511 hit, 25 missed, 39 unexercised,
            arithmetic performed over the gate-by-gate scores. The misses
            cluster: numbers written from intent rather than counted; shapes
            transplanted across instruments; premises inferred instead of read.
            Each family now has a rule, and the third family is the one that
            cost the most.

    D323-12 WHAT S324 PRODUCED, NAMED HERE AS OWED WITH ITS CONDITION OF
            DISCHARGE, BECAUSE THE ALTERNATIVE IS THE SAME SILENT GAP IN A NEW
            PLACE. S324 landed no code and wrote no byte before this entry. It
            produced six things that otherwise live only in an untracked
            handoff. FIRST, R26, which is recorded above rather than owed.
            SECOND, the generator: the template that emits the published
            verifier was already corrected in S323 and the published 5.60.1
            carries the old subject, so the boundary is TEMPORAL and the set of
            false published artifacts is closed and does not grow. THIRD, the
            wrap the correction created is COSMETIC DRIFT AND NOT A DEFECT: the
            published artifact carried six lines over 79 and a maximum of 92
            before the change, no configuration in the tree declares a column
            budget, the release runs pyflakes for undefined names only, and the
            sole test over the template asserts that it is ASCII. FOURTH, D2
            did not survive whole: two lines in docs/SMT_VERIFICATION_DESIGN.md
            remain, bounded and cheap and NOT closed. FIFTH,
            docs/governance_coverage_profile.json states in writing that the
            runtime policy engine is a distinct component that DOES interpose,
            with a block or abort_cycle action raising before the guarded side
            effect, and intervention.py confirms it in code; that is evidence
            bearing on a question asked elsewhere and it is recorded, not
            decided. SIXTH, the nine of D292-D1 is UNDIAGNOSABLE FOR EVER: the
            AXIS 0 records that produced it do not exist anywhere and were
            searched for. THE CONDITION OF DISCHARGE IS THE SAME ONE D322-10
            USED: these land in a D324 entry if the operator brings further
            work, and in an untracked handoff if not.

    D323-13 THE ORDER, WHAT THIS ENTRY RETIRES, AND WHAT MOVES WHEN IT LANDS.
            This entry, then whatever object the operator names next. The seal
            of S323 recorded that the S323 head line must print empty and that
            the D323 family must count zero; both are retired by this entry,
            and the next seat checks the S324 head line and the D324 family
            instead. Arithmetic performed while writing, settled at the gate
            after the append and not by this sentence: the head count reads 32
            today and would read 33; the D families read 15 and would read 16;
            under the twelve-space anchor shape the FG families read 10 and
            would read 12. THOSE FIGURES ARE STATED UNDER A SHAPE FG-S324-H
            SHOWS TO BE BLIND, and they are the figures the RULE 0 leg will
            print, not a census of the document.

    FINDINGS. The first twenty-eight are the S323 seat and operator errors as
    that session sealed them, each carrying the one-line statement the handoff
    recorded; the fuller account of each exists ONLY in that untracked handoff,
    and this entry records the code and the statement rather than inventing
    detail it did not measure. The last nine were named in S324 while this
    payload was being prepared and enter it for the reason FG-S322-A entered
    the D321 section: a finding found before the payload freezes goes into that
    payload.

            FG-S323-A  operator and seat. A fourth upload file was undeclared.

            FG-S323-B  seat error, R1. The supplement asserted that a paste
                       contained no bang. It contained seven.

            FG-S323-C  seat error, and the handoff was false in two places on
                       it. PORCELAIN read 3 and not 2, because README.md.s322v
                       was written 47 minutes AFTER the push of c4547e4.
                       Sections 1 and 3 of the prior handoff both stated the
                       smaller set.

            FG-S323-D  seat error. The VERSION_LIVE leg was not single-valued
                       and was read as though it were.

            FG-S323-E  measured property, no consequence. Two tokens of the
                       same idiom live in the worktree; the orphan is untracked
                       rather than ignored, and is therefore stage-able.

            FG-S323-F  not a seat error of that session. The settlement D322-9
                       declared was unreachable without a version bump absent
                       from the authorised order.

            FG-S323-G  inherited prior falsified. The PYTEST_FLOOR and hero-
                       stat lockstep prior is false.

            FG-S323-H  caught at zero cost, R14. Ordered-chain masking inside
                       arm fixturing.

            FG-S323-I  RECLASSIFIED during the session. A channel property, not
                       a discipline lapse. The remedy is T5.

            FG-S323-J  control failure found by adding a control. The three
                       specified arms could not distinguish a truncated regex;
                       a fourth arm was added and it went red.

            FG-S323-K  seat error, R1. The payload's non-ASCII count for the
                       merged file was predicted rather than counted.

            FG-S323-L  seat error, R18. A count was predicted over pytest's
                       renderer without reading what that renderer emits.

            FG-S323-M  seat error, R22. Sixteen predictions were written from
                       intent while the list held twenty.

            FG-S323-N  seat error, R21. _version.py was grepped for a token
                       whose location had never been confirmed.

            FG-S323-O  seat error, and it explains why a whole gate could not
                       pass. Left-right output uses a TAB. The guard built over
                       it could not pass, and it went unnoticed because G3 was
                       the one gate whose HAPPY PATH was never fixtured.

            FG-S323-P  seat error, R2. A three-line list was predicted for a
                       three-line WINDOW after a commit had already evicted the
                       tail.

            FG-S323-Q  measured property of a shape. A 200-character window
                       does not always contain the phrase that caused the
                       match.

            FG-S323-R  transport defect, and it is silent. A multi-line python3
                       -c inside a paste joined by semicolon and space: three
                       shells return rc 0 and the embedded code is destroyed.

            FG-S323-S  seat error, R2. A grep -o stream was filtered by
                       patterns that cannot appear in it.

            FG-S323-T  seat error, R18. Binaries were filtered by an extension
                       list rather than by the tool's own text detection.

            FG-S323-U  seat error, R2. A count was printed over one set and an
                       enumeration produced over another.

            FG-S323-V  seat error, and the ancestor of FG-S324-E. A column
                       budget was reasoned about for four files and not one of
                       them was measured.

            FG-S323-W  seat error. Set membership was inferred from a substring
                       in a neighbouring path.

            FG-S323-X  THE LARGEST ERROR OF THE SESSION. An architectural case
                       was built across three messages and two rounds of
                       external research on a premise inferred from a MAXLEN
                       delta that nobody had opened. The tests never
                       regenerated the verifier.

            FG-S323-Y  seat error. The stated plan and the emitted paste
                       disagreed.

            FG-S323-Z  seat error, R21. A symbol was named from its position in
                       a file instead of by its identifier.

            FG-S323-AA seat error, R22, for the third time in the same session.
                       Twelve predictions were written from intent.

            FG-S323-AB seat error, R2. Arithmetic on a NET delta was predicted
                       for a git diff GROSS count.

            FG-S324-A  seat error, R2 and R24 together. The listing of a
                       temporary directory was predicted from a handoff
                       sentence about PROVENANCE. The handoff said two operator
                       files were PLACED there; the instrument was a directory
                       listing and printed sixteen entries. A statement about
                       what was put somewhere is not an inventory of what is
                       there.

            FG-S324-B  seat error, and the instrument was the seat's own. A
                       directory count was taken by cutting a path at four
                       segments, on a path depth never read. It printed 3,
                       which is a count of four-segment prefixes and not of
                       directories.

            FG-S324-C  seat error, R2. Published verifiers were predicted at 22
                       and measured at 44, because the fixed-string match also
                       catches the sha256 sidecar beside each verifier. That 44
                       is twice 22 is plausible and was NOT measured.

            FG-S324-D  seat error, R11. A prediction was written with no
                       matchable shape and could not be scored either way.

            FG-S324-E  seat error, and it produced R26. A gate was built whose
                       whole structure rested on the words over budget meaning
                       greater than 79, and no instrument had ever established
                       that 79 is a budget for those files. The gate's own
                       framing leg refuted it: 104 source lines in the six
                       generators exceed 79 and no guard in the tree has ever
                       fired on them. A negative control nobody designed.

            FG-S324-F  seat error, same class as FG-S323-W. The membership of a
                       set difference was predicted from the subject of a file
                       rather than from a line that had been read.

            FG-S324-G  seat error. Nine members of the FG-S322 family were
                       predicted inside the S322 section; eight are there and
                       the ninth sits at line 4720, inside the S321 section. A
                       family count is not a statement about where the family
                       lives.

            FG-S324-H  NOT A SEAT ERROR, AND IT CONCERNS THE SWEEP R20
                       REQUIRES. The RULE 0 leg that sweeps FG anchors matches
                       exactly twelve leading spaces. Under a looser leading-
                       space shape the same file yields twelve families rather
                       than ten, 109 anchor occurrences and 106 distinct
                       anchors. At least one member sits at another indent and
                       some anchors appear more than once. The leg that
                       enforces sweep by anchor family is itself a counter with
                       a known shape. RECORDED AND NOT REPAIRED: one object per
                       arc.

            FG-S324-I  seat error of this session, caught by the operator at
                       read. The payload above carried the S323 subject split
                       as the seal wrote it and never performed its arithmetic:
                       11, 149 and 117 sum to 277 and not to 245. This entry
                       names that class of error four times and then committed
                       it in transcription. AN INHERITED FIGURE COPIED FORWARD
                       IS STILL A FIGURE THIS ENTRY ASSERTS. The check that
                       found it was addition, performed by the operator at
                       read. WHETHER ANY EARLIER PAYLOAD GATE IN THIS CHAIN
                       PERFORMED ITS OWN ARITHMETIC BEFORE EMISSION IS NOT
                       MEASURED AND IS NOT CLAIMED HERE. The builder now
                       refuses to emit unless every sum this entry states is
                       performed.

    WHAT THIS ENTRY DOES NOT DO. It writes no code and authorises none. It
    does not touch claims.toml, whose enforcement axis is the leg that would
    stop the recurrence D323-6 describes and which remains unbuilt. It
    corrects no false surface: the 94 unpublished lines, the four served files
    and the 23 published lines are all untouched, and the published ones are
    correctable by supersession only. It does not edit any byte under
    website/.well-known. It does not close D2, build E4, move the floor, cut a
    release, clear the untracked paths or amend the frozen fixture, and it
    constructs no route to any of them. It edits no sentence already on this
    page; every correction above is an append. And it does not repair the
    sweep leg recorded in FG-S324-H.

  - S324 the enforcement surface is measured phrase by phrase, the
    subject split closes where the S323 one did not, and the entry
    lands two sessions after the session it records

    THIS ENTRY IS WRITTEN IN S327 ABOUT S324, and the gap is the first thing it
    owes. D323-12 named the condition of discharge: these land in a D324 entry
    if the operator brings further work, and in an untracked handoff if not.
    Work came, and it came two sessions late. S325 and S326 each ran a full
    session and each wrote zero bytes, so the chain is intact but the debt
    aged. Nothing below is claimed to have been measured in S325, S326 or S327.

    THE PROVENANCE OF EVERY NUMBER BELOW. Nothing in this entry was measured in
    S327 except where a line says so. Every figure was printed by an instrument
    in S324 and travels in NOUS_SESSION_324_HANDOFF.md, sha 253e204c, 16554
    bytes, 343 lines, MAXLEN 79, byte-verified at the opening of S327 before it
    was read. That handoff is untracked and is not in the repository. Where it
    carries a number without the shape that produced it, this entry says so
    instead of repeating it as though it could be reproduced. R24 applied to
    this entry by its own author.

    AND ONE THING THIS ENTRY HAS THAT D323 DID NOT. The state at the S324 seal
    was re-measured live in S327 at the same commit and reproduced exactly:
    HEAD cbf3308, origin equal, AHEAD 0, BEHIND 0, AHEAD_OF_TAG 72, PORCELAIN
    3, suite 2872 passed and 12 skipped, LINT rc 0 over 421 files with 0
    violations, MIRROR rc 0 CLEAN over 331 tracked files with 5 orphans, and
    this document at b3e689b9, 5363 lines, 315433 bytes, MAXLEN 79. Those
    figures are inherited AND re-measured. The census figures below are
    inherited only.

    D324-1  THE FIFTEEN PHRASES ARE WRITTEN DOWN, WHICH IS THE ONE THING D323-2
            SAYS S323 COULD NOT DO. The S324 census used a NEW fifteen-phrase
            set, written into the paste that ran it, and it is NOT a
            reproduction of the axis A of S323. The phrase list and its
            per-phrase hits:

            A01 is a monitor                   164
            A02 remains a monitor                3
            A03 not a guard                    157
            A04 does not enforce                 4
            A05 does not block                   1
            A06 does not intervene               0
            A07 does not halt                    0
            A08 does not gate                    5
            A09 no enforcement                   0
            A10 monitor-not-guard                4
            A11 never blocks                     0
            A12 does not prevent                 0
            A13 enforce, block, or intervene     1
            A14 monitor rather than a guard      0
            A15 not an enforcement               1

            Nine phrases hit and six return zero, so the set contains its own
            negative arms. THE PER-PHRASE HITS SUM TO 340 AND THAT SUM IS NOT A
            COUNT OF LINES: a line saying NOUS is a monitor, not a guard
            matches A01 and A03 together. The addition was performed while
            writing this entry and 340 is recorded here only so that no later
            seat computes it and reads it as a set size. It is bound to no set.

    D324-2  THE SUBJECT SPLIT CLOSES ARITHMETICALLY, WHERE THE S323 SPLIT
            RECORDED IN D323-3 DOES NOT. MONITOR_ANY 167 divides into SCOPED
            24, UNQUALIFIED 137 and a REMAINDER of 6, and 24 plus 137 plus 6 is
            167. Independently A01 164 plus A02 3 is 167, so no line carries
            both phrases. Both additions were performed while writing this
            entry. THE TOKENS ARE THE SAME AS D323-3 AND THE SETS ARE NOT: the
            11, 149 and 117 of D323-3 belong to the S323 phrase set at 0fd92a3
            and the 24, 137 and 6 belong to the S324 phrase set at cbf3308.
            Neither triple corrects the other and no arithmetic between them is
            admissible.

            The six of the remainder are NAMED, not classified, because naming
            is what the instrument supports and classifying is not:

            closure_ledger.py:21
            docs/AUTHORIZATION_RUNTIME.md:45
            docs/COUNTERPARTY_WITNESSED_CONTINUITY_DESIGN.md:391
            docs/SANTANDER_ADAPTER.md:184
            docs/governance_coverage_profile.json:117
            docs/governance_coverage_profile.json:131

    D324-3  THE PATHSPEC SPLIT IS A DIVISION OF 167 AND NOT OF 137, AND THAT
            DISTINCTION IS THE WHOLE VALUE OF THE ITEM. B1_PUBLISHED 102,
            B2_SERVED 16, B3_TRACKED 49, and 102 plus 16 plus 49 is 167. The
            addition was performed while writing this entry. THE SUBJECT SPLIT
            PER BUCKET WAS NOT MEASURED. No figure in D324-2 may be attributed
            to any bucket here, and no figure here may be attributed to any
            subject class there. Two divisions of the same 167 along different
            axes are not a two-dimensional table until somebody measures the
            cells.

    D324-4  THE OPPOSITE DIRECTION: FIVE HITS AND NONE OF THEM FALSE. This is
            the S324 axis B and it is NOT the axis B of D323-2, which had
            eleven phrases and 87 hits at a different commit. Read as units
            with one line of after-context: EU_AI_ACT_COMPLIANCE.md:193 says
            the block action halts emission and agrees with intervention.py:20;
            :189-190 says execution continues and agrees with
            intervention.py:19; RUNTIME_GOVERNANCE_CROSSWALK.md:99 describes a
            category rather than this system; ADR-0005:22 records the
            alternative that was rejected; governance_coverage_profile.json:117
            declares correctly; and blog/index.html:1842 is about stop buttons
            in general. D323-5 closed :193 and :189 by reading; this item
            closes the other four the same way.

    D324-5  WHERE THE CORRECTED SUBJECT LIVES OUTSIDE THE SIX GENERATORS, AND
            WHY TWO SHAPES DISAGREE BY TWO. Ten sites carry the new subject
            outside the six generator sources, all of them in docs and all of
            them correct. Two shapes for the same idea return 24 and 22, and
            the two extra members are tests/test_s159_u1_provenance.py:89 and
            tests/test_s226_backfill_disclosure.py:42. Both are asserts that
            lock the subject MORE LOOSELY than the generators emit it. A test
            that accepts a superset of what the producer writes is more durable
            than one pinned to the exact string, so the difference of two is a
            property of the assertions and not a defect.

    D324-6  THE PUBLISHED VERIFIERS ARE 44 AND THE SPLIT INSIDE THAT NUMBER WAS
            NEVER TAKEN. FG-S324-C already records that 22 was predicted and 44
            measured because the fixed-string match catches the sha256 sidecar
            beside each verifier. What FG-S324-C does not record, and this item
            does, is that the split between .py files and .py.sha256 sidecars
            WAS NOT MEASURED. That 44 is exactly twice 22 is plausible, it is
            the obvious reading, and no instrument has ever printed it. It is
            not asserted here.

    D324-7  THE COLUMN NUMBERS, WHOSE CONCLUSION IS ALREADY IN D323-12 AND
            WHOSE MEASUREMENTS ARE NOT. D323-12 records that no configuration
            declares a column budget, that the release runs pyflakes for
            undefined names only, and that the sole test over the template
            asserts ASCII. The figures behind that: SRC_OVER79 is 104 across
            the six generator sources, which FG-S324-E also records. The
            per-file maxima do not appear anywhere: build_vsa.py 14454 and
            vsa_verifier.py 29515, each one physical line holding a whole
            template; mint_release_vsa.py 118, provenance.py 86,
            provenance_verifier.py 90, scripts/cold_audit.py 82. The emitted
            artifacts: build_vsa 351 lines with MAXLEN 92 and 8 over 79;
            vsa_verifier 740 lines with MAXLEN 131 and 3 over 79. The published
            5.60.1 verifier: 350 lines, MAXLEN 92, 6 over 79. The delta at both
            wrap sites is exactly 14, which is the length of the phrase the
            evidence layer minus the length of NOUS.

    D324-8  THE WRITE ARC OF S324, SEVEN GATES, EACH SCORED BEFORE THE NEXT.
            Build produced 353 then f65d4f67 at 374 lines then 82e1828d at 375.
            Transfer moved a file and censused it before anything ran. The
            dry-run computed the candidate and wrote zero bytes. Apply wrote
            the candidate beside the target with O_EXCL at mode 0644 and
            re-read it from disk. Rename carried four guards, one of them
            proving the candidate's first 292240 bytes byte-identical to the
            target at that moment, and used os.replace rather than mv. Stage
            used one explicit pathspec and compared the worktree blob to the
            index blob. Commit carried three ordered guards, of which the
            staged-set guard is the one that catches a re-paste. Push carried
            five, then read the blob back from origin/main rather than from the
            worktree. The object is the same in every link: c62323ca as a git
            blob and b3e689b9 as file bytes.

    D324-9  THE PREDICTION RECORD OF S324. 205 declared, 197 hit, 8 missed, 29
            declined, over 13 gates, with the arithmetic performed over the
            gate-by-gate scores; 197 plus 8 is 205 and that addition was
            performed again while writing this entry. EVERY MISS FELL IN THE
            FIRST SIX GATES. The seven gates of the write arc scored 91 for 91,
            which is what fixturing every refuse arm and the happy path buys.
            The misses cluster in two families and each family has a rule: a
            set predicted from a sentence about provenance rather than from an
            instrument over that set, which is A, C, F and G; and a shape or a
            threshold carried in rather than read, which is B, D and E.

    FINDINGS. Twelve were named in S324 and nine of them are already in bytes
    inside the D323 entry, at the twelve-space anchor, for the reason that
    entry gives: a finding found before the payload freezes goes into that
    payload. Nine plus three is twelve and the addition was performed while
    writing this entry. The three below are the ones D323-12 left owed. Their
    absence from the document was measured in S327 before this entry was
    drafted, not assumed.

            FG-S324-J  seat error, R11 on the input side. A census leg used
                       grep -c against a file that did not exist. grep -c sends
                       the error elsewhere and returns 0 on stdout, which is
                       exactly the value the leg was watching for. A LEG WHOSE
                       FAILURE VALUE EQUALS ITS SUCCESS VALUE IS NOT A LEG. The
                       neighbouring legs printed empty and were visible;
                       STARTS_BLANK printed a green 0 over an absent file. The
                       remedy is to guard existence first and print the result
                       of that guard before anything else reads the path.

            FG-S324-K  seat error. A score restated its predictions from the
                       tool's current pins without restating that the object
                       under test had changed since the operator's approval.
                       The change had been declared three times with shas and
                       the corrected arithmetic was written before the run, so
                       the score was not blind. But a score that does not carry
                       the provenance of its own priors invites the reader to
                       score against a dead sha, and one did.

            FG-S324-L  operator, and it is named here at the operator's own
                       instruction. The approved payload sha was held as
                       current and scored against while the change to it had
                       been declared three times with shas. A finding was
                       proposed that the record contradicts, and it was
                       withdrawn on reading the record back. It belongs to the
                       same family as the finding recorded at FG-S324-A, from
                       the operator seat.

    WHAT THIS ENTRY DOES NOT DO. It writes no code and authorises none. It does
    not touch claims.toml. It corrects no false surface and moves no byte under
    website/.well-known or website/blog/index.html. It does not close D2, build
    E4, move the floor, cut a release, clear the untracked paths or amend the
    frozen fixture, and it constructs no route to any of them. It edits no
    sentence already on this page; it is an append. It does not repair the
    sweep leg recorded in FG-S324-H. It does not record S325 or S326, whose
    entries remain owed and whose numbers are not in this entry. And it does
    not re-present as new anything already carried by D323-10, by D323-12, or
    by the block of findings running from FG-S324-A to FG-S324-I.
