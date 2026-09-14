# INNOVATION GATE: OFFLINE TRUST-ANCHOR KEY SUCCESSION

ASCII only. No line exceeds 76 columns.

R24 APPLIES TO EVERY VALUE BELOW. A value marked MEASURED was printed
by a named instrument on a named host in the session that wrote this
gate. A value marked INHERITED was not, and must be re-measured before
it is used as a premise.

THE REJECTION ARGUMENT IS WRITTEN BEFORE THE ACCEPTANCE ARGUMENT. NO
NOVELTY IS CLAIMED FOR THE MECHANISM.

---

## 1. THE OBJECT

A succession record: a DSSE envelope, signed by the current release
operator key, naming a successor public key for the same verifier
identity, shipped as a file inside each release directory, and read
by the offline verifier only after the primary signature check has
already failed.

WHAT IT IS FOR. If the release operator private key is lost, an
offline consumer holding the old pin can walk to the new pin using a
signature it can check with the pin it already has. Without it, a
lost key means every future release carries a pin that no existing
consumer can connect to any earlier one.

WHAT PROMPTED IT. Measured on Server A: the key the minter names,
release_attest_signing.key, is 32 bytes, mode 600, owner root, one
path, and it exists on no other host this project owns. Measured on
Server B: the key directory holds one file and it is not that key.
Ten of eleven keys on A have no counterpart anywhere measured.

## 2. THE REJECTION ARGUMENT, WRITTEN FIRST

THE STRONGEST CASE AGAINST BUILDING THIS.

R1. IT ADDS A SECOND ACCEPTANCE PATH TO AN ARTIFACT WHOSE ENTIRE
JOB IS TO FAIL CLOSED. The offline verifier today has one way to
return PASS. This adds another. A defect in the new path turns a
signature that should be rejected into one that is accepted. The
asymmetry is brutal: the existing design fails safe on any bug in
the succession logic ONLY IF that logic is unreachable, and the
whole point is to make it reachable. NOTHING ELSE IN THIS GATE
OUTWEIGHS THIS IF THE IMPLEMENTATION IS NOT DRIVEN RED FIRST.

R2. IT PROTECTS AGAINST NOTHING THAT HAS HAPPENED. No key has been
lost. The argument rests on a neighbouring lane's loss of a
different credential, which is an anecdote about a different key
under different custody.

R3. IT DOES NOT REMOVE THE CUSTODY DECISION. The successor key has
to live somewhere. If it lives on a host that can be rebuilt, the
original problem is reproduced at a new path with a new name. The
record converts an irreplaceable asset into a replaceable one; it
does not make the replaceable one safe.

R4. EVERY VERIFIER ALREADY PUBLISHED IS UNAFFECTED, PERMANENTLY. A
consumer holding the 5.78.0 verifier gains nothing, ever. The pin is
frozen in those bytes. The benefit begins only with consumers of
releases that do not yet exist.

R5. THE FEDERATION ROOTS SURVIVE KEY LOSS ALREADY. The published
verifier states in its own docstring that the operator root sits
ALONGSIDE the GitHub Actions SLSA provenance and the PEP 740 publish
attestation, and names the operator-independent commands. Losing the
operator key costs the zero-dependency convenience path, not the
verifiability of any release.

R6. IT SPENDS A CEREMONY ON THE CONTINUITY KEY. Signing the record
is a use of the one key whose loss this gate is about.

R7. A CHEAPER MOVE EXISTS. A tested copy of the 32-byte seed gives
loss protection with no change to any published artifact and no new
acceptance path. If the only goal is surviving loss, the copy is
smaller in every dimension.

## 3. THE ACCEPTANCE ARGUMENT

A1. A COPY IS A CLAIM UNTIL IT IS RESTORED. A SUCCESSION RECORD IS
EVIDENCE WHEN IT IS PUBLISHED. Anyone holding the published
predecessor public key can check the signature immediately. There is
no untested restore in the middle. This is the same distinction this
project applies to everything else it ships.

A2. THE TWO ARE NOT ALTERNATIVES AND R7 TREATS THEM AS IF THEY WERE.
A copy fails if the copy is unreadable. A succession record fails if
both keys are lost at once. Together the failure requires both, and
each is verifiable by a different method.

A3. THE DEADLINE IS STRUCTURAL. A succession record can only be
signed while the predecessor key works. After the loss it is
impossible. The copy has the same precondition, so the deadline
argument does not rank them, but it does rule out doing neither.

A4. R4 IS AN ARGUMENT FOR SOONER, NOT FOR NEVER. Every release that
ships without a succession-aware verifier adds one more frozen
artifact that can never walk the chain.

A5. R1 IS ANSWERED BY CONSTRUCTION, NOT BY CARE. The succession path
is attempted only after the primary check has failed, it refuses
closed on every branch, and its acceptance conditions are equality
tests against constants compiled into the verifier. Seven red arms
and one green are specified in section 7 and none of them touches a
host.

A6. IT MAKES A PROPERTY THIS PROJECT ALREADY ASSERTS INTO SOMETHING
A READER CAN CHECK. The operator key is required to stay continuous
across releases. Today that requirement is satisfied by the key not
having been lost. That is a run of luck, not a property of the
system.

## 4. PRIOR ART. NO NOVELTY IS CLAIMED FOR THE MECHANISM.

THE MECHANISM IS OLD, STANDARDS-TRACK, AND WELL UNDERSTOOD.

RFC 5011, Automated Updates of DNSSEC Trust Anchors, 2007. A new
trust anchor is accepted because an existing trust anchor signs a
set containing it, subject to an add hold-down time of thirty days
during which the resolver must see the new key in every valid set.

DNSSEC pre-publish rollover. The successor is published in zone data
before it is used. BIND's dnssec-keygen carries an explicit
successor option that derives the new key's timing from the old.

TUF root rotation. The root role delegates trust and can replace any
key; a threshold of root keys must be compromised before the root
file has to be reissued out of band.

OpenPGP pre-generated revocation certificates. A statement signed in
advance and usable when the key itself is no longer available. The
negative twin of a succession record.

WHAT IS NOT PRIOR ART, AND IS THE ONLY THING CLAIMED HERE. Every
mechanism above assumes the consumer re-fetches. The resolver sees a
new RRSet. The TUF client pulls a new root file. THE VERIFIER THIS
PROJECT PUBLISHES NEVER RE-FETCHES ANYTHING. Its pin is frozen in the
bytes of a script shipped per release, it takes no network, and by
design it requires only the cryptography library. RFC 5011's
hold-down has no analogue because there is no channel on which to
observe anything twice.

THE DESIGN CONTRIBUTION IS THEREFORE NARROW: succession for a trust
anchor distributed as frozen bytes in an offline artifact, where the
succession record travels inside the same release directory as the
attestation it rescues. It is an adaptation of a known mechanism to a
distribution model that mechanism did not contemplate. That is the
whole of it.

## 5. THE PATENT LANDSCAPE

NO PATENT SEARCH WAS RUN. THIS SECTION RECORDS A WEAK NEGATIVE AND
CARRIES ITS OWN VOIDING CONDITION.

Two United States patents surfaced incidentally during a prior-art
web search that was not a patent search: one on managing DNSSEC
including key rollover methods, and one on verified boot and key
rotation. Neither was read. Their appearance evidences that the
general area is patented territory and evidences nothing about this
design.

THE WEAK NEGATIVE. The mechanism is described in a 2007 IETF
standards-track RFC and in DNSSEC operational practice older still.
Published standards-track description that old is a poor foundation
for a novelty claim by anyone.

THE VOIDING CONDITION. Absence of a search is not clearance. If this
work is ever presented as a contribution rather than as an
adaptation, or if it is offered to a standards body, this section is
void and a real search is owed first.

## 6. WHAT IS UNMEASURED AND GATES THE BUILD

NONE OF THESE MAY BE ASSUMED. EACH IS READ-ONLY.

U1. HOW THE PUBLISHED keyid IS COMPUTED. The current release
verifier key file carries keyid 66969a4e... and the derivation is
unknown here. The record omits keyid entirely for this reason. If it
is ever added, the derivation is measured first, because a field
whose construction is guessed is a false field in a signed artifact.

U2. WHETHER THE TWO FILES NAMED signing.key ARE ONE KEY OR TWO.
MEASURED: Server A 119 bytes PEM, 28 April 14:36:27; Server B 119
bytes PEM, 28 April 19:35:24. Same name, same size, same day, five
hours apart, and the README states the file is auto-generated on
first use. Undecidable without reading content. Not this gate's
object, but it bears on whether one verifier identity is backed by
one key or by two.

U3. WHETHER ANY SERVED SENTENCE ASSERTS KEY CONTINUITY. If one does,
it is a claim about a property the system does not yet have, and it
binds before anything here does.

U4. WHETHER THE EMBEDDED VERIFIER TEXT IS FROZEN BY A TEST. The
offline verifier is carried as a string literal inside build_vsa.py.
Changing it changes every verifier emitted from that point. Whether
a replay lock or a golden fixture pins those bytes is unmeasured, and
it decides whether this is a one-file change or a suite change.

U5. WHETHER THE RELEASE PIPELINE MUST EMIT THE RECORD. If the record
ships inside each release directory, some phase has to write it, and
that phase is unread.

U6. RULE 9. If any new top-level module appears, dual registration in
the manifest and in the wheel gate is required in the same patch.
Whether this design needs a new module is undecided until U4 and U5
are measured.

U7. THE PUBLISHED SURFACE COUNT. MEASURED: the pinned public value
occurs in 85 files under the repository, of which 22 are published
release-vsa directories carrying three files each. Whether the record
is added to past directories or only to future ones is a decision,
not a measurement, and it is the operator's.

## 7. FAILURE-FIRST ANALYSIS

F1. A DEFECT IN THE SUCCESSION PATH TURNS A REJECTION INTO AN
ACCEPTANCE. The dominant risk. Mitigated by: the path is unreachable
until the primary check fails; every acceptance condition is equality
against a compiled-in constant; no field of the record grants a
permission; seven red arms before one green.

F2. COMPROMISE IS NOT COVERED AND MUST NOT APPEAR TO BE. A holder of
the predecessor private key can sign a competing succession. An
offline verifier has no channel on which to observe ordering or
hold-down. THE RECORD STATES THIS IN ITS OWN BOUNDARY FIELD, inside
the signed payload, so the limitation travels with the artifact.

F3. A FIELD THAT GRANTS A PERMISSION. A scope list invites a second
entry and then the verifier branches on the document it is checking.
REMOVED. The role is carried by the predicateType, which is checked
for exact equality the same way the VSA predicate type already is.

F4. A SELF-DECLARED LIMIT. A hops field lets the checked object state
its own bound. REMOVED. One hop is compiled into the verifier and any
such field is ignored.

F5. EXPIRY OR NOT-BEFORE. An expired record is useless precisely when
it is needed, and clock skew on an offline host produces failures
nobody can diagnose without a network. BOTH REMOVED.

F6. UNBOUNDED PARSE. A fail-closed artifact acquires a denial-of-
service surface if it parses an arbitrarily large file. The record is
rejected above a small fixed byte limit BEFORE any parse.

F7. RE-PARSING AFTER VERIFICATION. The DSSE specification forbids
reading the envelope again after the payload verifies. Every field is
read from the verified payload only, as the existing verifier already
does.

F8. CANONICALISATION DRIFT. Not load-bearing here: the signature
covers the exact payload bytes and the verifier reads only those.
This is written down so that no later body adds a canonicalisation
step and creates a second oracle.

F9. REPLAY AND ORDERING ARE UNDECIDABLE OFFLINE. timeIssued is
informational and no decision reads it.

F10. THE SUBJECT OF THE STATEMENT IS A PUBLIC KEY, NOT A SOFTWARE
ARTIFACT. An auditor may object that this stretches the in-toto
subject. Recorded, not resolved.

F11. THE CEREMONY USES THE CONTINUITY KEY. One use, one gate, and the
signature is verified against the published predecessor value before
anything is published.

F12. THE SUCCESSOR KEY REPRODUCES THE CUSTODY PROBLEM IF IT LIVES ON
A PRODUCTION HOST. Server B is a second production host at a
different commit that can be rebuilt. IT IS NOT A VAULT. Where the
successor lives is not a technical question and is not decided here.

## 8. THE HONEST BOUNDARY, IN BOTH DIRECTIONS

NOT OVERSTATED. This record EVIDENCES that the holder of the
predecessor key designated a successor. It PROVES nothing; proves is
reserved for Z3 and Farkas results. It does not evidence that any
copy of any key exists. It does not evidence that a key is
recoverable. It does not cover compromise.

NOT UNDERSTATED EITHER. Losing the release operator key does NOT make
any published release unverifiable. The SLSA build provenance and the
PEP 740 publish attestation are independent roots and the published
verifier names the commands that use them. Any sentence that treats
key loss as loss of verifiability is an overclaim in the other
direction and is as wrong as the first kind.

WHAT IS LOST WITHOUT THIS. The ability of a consumer holding an
earlier pin to connect it to a later one. From that consumer's side, a
key change and an impersonation look identical.

## 9. ALTERNATIVES CONSIDERED AND REJECTED

A. A PUBLISHED CUSTODY ATTESTATION. A signed statement that N copies
exist in N places. REJECTED. No reader can verify it. It is testimony
wearing the clothes of evidence, which is the exact overclaim class
an external reviewer has already caught on this project once. It may
exist as an internal record. It never reaches a served surface.

B. KEYLESS SIGNING VIA AN EPHEMERAL IDENTITY-BOUND CERTIFICATE.
REJECTED FOR THIS LAYER. It removes long-lived key custody entirely
and it destroys the zero-dependency offline root, which is the stated
reason this layer exists at all.

C. THRESHOLD SPLIT OF THE SIGNING KEY. Standard guidance for offline
roots is several keys with a signature threshold. BANKED, NOT
REJECTED. That guidance assumes an organisation; for a single
operator it multiplies the operating surface without a second pair of
hands to hold a share.

D. BACKUP ALONE, NO SUCCESSION. REJECTED AS SUFFICIENT, ACCEPTED AS
NECESSARY. See A1 and A2. It follows this work; it does not replace
it.

E. DO NOTHING AND NAME THE PLATEAU. Legitimate and available. It is
rejected only because section 1 records a measured single point of
failure with no recovery path, which is not the same as an absence of
work.

## 10. THE ROUTE, AND WHAT IT COSTS

ROUTE: BUILD-ELIGIBLE, GATED ON SECTION 6.

NOTHING IS BUILT UNTIL U1 THROUGH U7 ARE MEASURED. Every one is
read-only. If U4 shows the embedded verifier text is frozen by a
test, this becomes a suite change and returns to this gate for
re-routing before any code is written.

THE CEREMONY, WHEN AND IF IT OPENS, IS FIVE GATES, ONE IRREVERSIBLE
ACTION EACH: generate the successor; build and sign the record;
verify it against the published predecessor value with a forced red
arm; publish; anchor.

WHAT THE OPERATOR DECIDES AND THE SEAT DOES NOT. Whether this opens
at all. Where the successor key lives. Whether the record is added to
past release directories or only to future ones. Whether a copy of
the predecessor seed is taken, and to where.

WHAT IS OWED TO THE LEDGER REGARDLESS OF THIS ROUTE. The findings
this arc produced, which travel by append and are not urgent.

END OF GATE
