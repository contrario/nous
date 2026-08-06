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
