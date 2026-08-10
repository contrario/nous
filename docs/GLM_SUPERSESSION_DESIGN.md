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
