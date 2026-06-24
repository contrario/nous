# Counterparty-Witnessed Conformance Continuity: Design Freeze (S175)

Design freeze for a run-lineage continuity ledger whose links are
conformance-certified RUNS, each independently witnessed by a COUNTERPARTY
whose receipt verifies with stock JWS/JWT/openssl tooling and zero NOUS
install. ASCII-only.

Status: DESIGN FROZEN, S175. No implementation code is part of this document.
Implementation is a separate later session, gated on confirmation of this
freeze. The live bytes win: if a later session finds the substrate in
section 0 changed, the live bytes supersede this freeze and it must be
reconciled before any code lands.

Cross-references:
  `docs/ENVELOPE_BINDING_DESIGN.md` (the build-lineage manifest chain this
    design retargets to run-lineage; the fail-closed offline walk this
    design mirrors),
  `docs/RUNTIME_CONFORMANCE.md` and `conformance_verifier.py` (the per-run
    certificate that is the unit this ledger chains),
  `docs/WITNESSED_RUN_EVIDENCE.md`, `docs/STRATIFIED_TRUST_DESIGN.md` (the
    frozen witnessed-run evidence triple this design does NOT alter),
  `docs/ATTESTATION_RECEIPT.md` and `attest_apr.py` (the pin-a-foreign-key,
    verify-offline witness pattern this design generalizes from the TEE
    enclave to an external counterparty),
  `docs/NOUS_VSA.md` and `build_vsa.py` (the release VSA whose federation
    legs are the build-time precedent for evidence beyond operator
    telemetry; this design is its run-time analog),
  `docs/DECISION_LEDGER.md` and `decision_ledger.py` (a presentation view,
    explicitly distinct from this continuity ledger; section 12).

================================================================
0. Substrate this design is written against (S175 live bytes)
================================================================

Verified live before designing, not assumed.

0.1 The envelope-binding chain is BUILD-lineage. `ENVELOPE_BINDING_DESIGN.md`
froze a chain whose links are signed verification MANIFESTS across material
build changes (source / smt_spec / pricing / cost_cap / tick bound). It is
formation-time evidence. The per-run conformance certificate is reachable by
reference from a chained manifest but is NOT itself a link
(`ENVELOPE_BINDING_DESIGN.md` section 4: "the certificate is execution-time
evidence; the chain is formation-time evidence"). There is today no chain
whose links are runs.

0.2 The per-run conformance certificate already binds a run to its formation
envelope. `conformance_verifier.py` (CONFORMANCE_VERIFY_OFFLINE_PY) checks,
cryptography + stdlib only: certificate Ed25519 signature; cert.trace_sha256
== sha256(trace canonical body); cert {source,smt_spec,pricing}_sha256 ==
manifest's; optional codegen leg by sha-equality; trace Ed25519 signature;
recorded verdict consistent with the obligation booleans (six for schema v1,
seven for v2, eight for v4). This certificate is the unit the continuity
ledger chains. Its canonical body serialization is
`json.dumps(sort_keys=True, separators=(",", ":"))` over the body minus
`signature` (and minus `transparency_log` for the cert), per
`conformance_verifier.py` `_canonical_body_bytes` / `_cert_canonical_body_bytes`.

0.3 A run-lineage already exists at the memory layer. `run_identity.py`
exposes `world_sha256` (:40), `producing_soul_sha256` (:48), and
`build_run_consultation` (:61), which reads the soul's signed memory chain
(`memory_store.read_chain`, `memory_entry.genesis_head` /
`chain_entry_hash`) and records `consulted_chain_head` plus
`consulted_seq_count`. This is the existing per-(world, soul) run-lineage.
This design REUSES that head + seq as the run's position anchor; it does NOT
invent a second, parallel lineage.

0.4 The pin-a-foreign-key witness pattern already ships. `attest_apr.py`
implements an Attestation Pinning Record that pins an enclave public key and
an offline verifier that checks per-event inference receipts signed by that
foreign key, cryptography-only (`ATTESTATION_RECEIPT.md`). The trust root is
a key NOT held by the operator. This design generalizes that pattern from a
TEE enclave to an external counterparty.

0.5 DSSE/PAE/Ed25519 over in-toto Statements is the project's machine-plane
attestation format. `vsa.py` defines `DSSE_PAYLOAD_TYPE =
"application/vnd.in-toto+json"` (:66), `_pae` (:102), `sign_vsa` (:400),
`verify_vsa_envelope` (:420), with the DSSE rule enforced: the verified
payload bytes are parsed directly, never re-parsed from the envelope. The
counterparty plane (section 5) deliberately diverges to JWS for the external
party's benefit, with a documented one-way bridge back to the machine plane.

0.6 The release VSA is the build-time precedent for evidence beyond operator
telemetry. `build_vsa.py` summarizes two federation legs (SLSA build
provenance, PEP 740 publish attestation) that name the exact published bytes;
the operator "summarizes the federation truth, it is not a second builder."
The continuity ledger is the run-time analog: it summarizes a counterparty's
witness of a run, it is not a second operator.

================================================================
1. The gap: the operator-telemetry ceiling at run time
================================================================

Every run-time evidence artifact NOUS emits today is rooted in the operator
key. The signed trace, the conformance certificate, the decision ledger, the
envelope-binding chain: all reduce to "the operator signed it." The only
evidence today that does NOT reduce to operator telemetry is (a) the build
federation legs (GitHub / PyPI), which exist only at BUILD time, and (b) the
TEE inference receipt, which exists only for the narrow token-count claim and
requires enclave hardware.

For an AAL-4-style argument (assurance beyond a single party's self-report),
the run-time evidence surface needs at least one leg whose trust root is a
party OTHER than the operator and is available for an ordinary run, with no
special hardware. A relying counterparty in the transaction the agent
mediates is exactly such a party.

================================================================
2. Thesis, and the explicit non-additions
================================================================

This design adds a continuity ledger: an append-only, tamper-evident chain
whose links are conformance-certified runs, where each link may additionally
carry a counterparty receipt -- an independent witness, signed by a key the
operator does not hold and verifiable with stock tooling.

It does NOT add: a new proof. "Proves" stays reserved for Z3 cost bounds and
Farkas certificates. The continuity ledger and the counterparty receipt
EVIDENCE; they prove nothing. It does NOT alter the frozen witnessed-run
evidence triple (`evidence_kind`, `cost_binding`, `provider_token_integrity`)
from `STRATIFIED_TRUST_DESIGN.md`; the counterparty witness is orthogonal to
those fields (section 12.2). It does NOT make any run mandatory in the ledger:
omission is not defeated (section 11).

================================================================
3. The retarget: build-lineage chain -> run-lineage ledger
================================================================

The envelope-binding chain and the continuity ledger are the same mechanical
shape (genesis link, each non-genesis link names its predecessor by a
tamper-evident digest, single chain, no cycles, fail-closed offline walk) over
two different unit types:

  envelope-binding chain : link = signed manifest        (a BUILD)
  continuity ledger      : link = conformance certificate (a RUN)
                           + optional counterparty receipt over that run

The retarget is deliberate and the two chains are complementary, never merged
(architectural axiom: no silent merges across discriminators). A continuity
ledger link carries a `link_kind = "run"` discriminator at construction so it
can never be confused with a manifest chain link, even if a future format
makes their digests structurally similar.

What the ledger chains is the certificate's canonical-body digest, not the
certificate file, so the link is stable under signature re-wrapping and is
re-derivable by any party holding the certificate bytes.

================================================================
4. The counterparty and the witness relationship
================================================================

4.1 Who the counterparty is. In NOUS governance vocabulary the parties to a
gated action are the Requester and the Authority. The counterparty here is the
party that RELIES on the run's outcome and is positioned to witness that the
run occurred and produced the certified result: typically the Authority that
admitted the action, or an external relying organization in the transaction
the agent mediated. The counterparty is NOT the operator and is NOT a NOUS
component.

4.2 The trust root is the counterparty's own published key, not an operator
pin. This is the load-bearing independence property. The APR pattern in
`attest_apr.py` pins the enclave key via a NOUS-signed record; that keeps the
operator in the trust path. For the counterparty receipt the trust root is the
counterparty's public key as the counterparty publishes it out of band (their
own well-known endpoint, their own key transparency, a mutually agreed
exchange). A relying third party verifies a counterparty receipt against the
COUNTERPARTY's key, never against an operator assertion. The ledger RECORDS
the counterparty key id and publication URI; it does not vouch for them.

4.3 Optional operator co-signature, explicitly not the root. The operator MAY
additionally sign "I accepted this counterparty receipt at this ledger
position." That co-signature binds the receipt into the operator's own chain
and is useful for the operator's records, but it is NOT the trust anchor for
the witness leg and a verifier evaluating independence MUST ignore it when
deciding whether the witness is operator-independent.

================================================================
5. The counterparty receipt wire format: detached JWS (EdDSA)
================================================================

Decision: the counterparty receipt is a JWS (RFC 7515) in flattened JSON
serialization, alg = EdDSA over Ed25519 (RFC 8037), with a detached or
attached payload. Not DSSE.

5.1 Why JWS and not DSSE. The counterparty is external and its toolchain is
unknown. The receipt has two hard requirements: the counterparty must be able
to PRODUCE it with ubiquitous libraries, and any relying party must be able to
VERIFY it with stock tooling and zero NOUS install. JWS/JWT EdDSA satisfies
both in every mainstream language; DSSE in-toto does not have comparable
external reach. The machine plane (VSA, provenance) stays DSSE in-toto; the
counterparty plane is JWS. The split is intentional and is the only place in
the project where an external party's signed artifact is not DSSE.

5.2 One-way bridge to the machine plane. The operator MAY canonicalize a
verified counterparty receipt's claim set into a DSSE-carried internal record
for machine-plane consistency. That projection is lossy and one-way (the JWS
is the authoritative artifact; the DSSE projection is a derived convenience).
Never imply the DSSE projection is round-trippable to the original JWS.

5.3 Protected header (minimum):
  alg : "EdDSA"
  typ : "application/nous-counterparty-receipt+jwt"
  kid : counterparty key id (an unauthenticated hint; the verifier resolves
        the key from the counterparty's published key set, never from kid
        alone)

5.4 Claims (the run binding). Standard claims:
  iss : counterparty identity URI (the issuer; matched against the resolved
        key's owner)
  sub : the run identity digest (section 6) -- the receipt's subject IS the
        run
  aud : the world / operator identity the witness is issued to
  iat, nbf : issuance / not-before, RFC 3339 or NumericDate per JWT
Private claims (all sha256 hex, binding the receipt to exact bytes):
  cert_body_sha256        : sha256 of the conformance certificate canonical
                            body (the link digest this receipt witnesses)
  world_sha256            : run_identity.world_sha256
  producing_soul_sha256   : run_identity.producing_soul_sha256
  consulted_chain_head    : the memory-chain head from build_run_consultation
  consulted_seq_count     : integer; the run's position in the soul lineage
  prev_run_digest         : the predecessor link digest, or the genesis
                            sentinel for the first witnessed run
  conformant              : boolean, copied from the certificate verdict (the
                            counterparty witnesses WHAT it was shown; the
                            verifier cross-checks this against the certificate)

5.5 Stock verification paths, zero NOUS install. A relying party verifies a
counterparty receipt by any of:
  - a JWT library: `jwt.decode(token, counterparty_pubkey, algorithms=
    ["EdDSA"], audience=world_id, issuer=counterparty_id)` (PyJWT, jose, etc.);
  - openssl, directly on the JWS signing input: base64url-decode the
    signature, reconstruct the signing input
    `ASCII(BASE64URL(protected) || "." || BASE64URL(payload))`, and run
    `openssl pkeyutl -verify -pubin -inkey <ed25519.pem> -rawin -sigfile`.
None of these requires NOUS, Z3, or any project module. This is the
zero-dependency property the freeze guarantees.

================================================================
6. The run identity the receipt binds to
================================================================

The run identity is not invented here; it is the tuple already produced by the
existing modules, hashed into one digest:

  run_identity_digest = sha256( canonical_json({
      "world_sha256":           world_sha256(world_name),
      "producing_soul_sha256":  producing_soul_sha256(world_name, soul_name),
      "cert_body_sha256":       sha256(cert canonical body),
      "consulted_chain_head":   <from build_run_consultation>,
      "consulted_seq_count":    <from build_run_consultation>,
  }) )

with `canonical_json` = `json.dumps(sort_keys=True, separators=(",", ":"))`,
the project-wide canonical form. The receipt's `sub` is this digest. Because
`cert_body_sha256` is inside the run identity, a counterparty receipt is bound
to one exact certified run and cannot be replayed onto another run (the same
subject-confusion defense `build_vsa.py` applies to subjects, and
`attest_apr.py` applies via `source_sha256`).

Reusing `consulted_chain_head` + `consulted_seq_count` ties the continuity
ledger to the EXISTING memory run-lineage rather than creating a competing
one. A continuity verifier MAY additionally check that `prev_run_digest`'s
recorded `consulted_seq_count` is strictly less than this link's, catching
reordering, but the authoritative ordering anchor is the explicit
`prev_run_digest` chain (section 7).

================================================================
7. The continuity ledger structure
================================================================

7.1 A link is a directory (mirroring the dossier layout in
`ENVELOPE_BINDING_DESIGN.md` 5.3), carrying:
  conformance.json   the signed per-run conformance certificate (the unit)
  trace.json         the signed trace the certificate binds (already required
                     by the conformance verifier)
  manifest.json      the signed manifest the certificate binds
  receipt.jws        zero or one counterparty receipt (drop-when-absent)
  link.json          { link_kind: "run", prev_run_digest, this_link_digest,
                       run_identity_digest, counterparty_key_uri (or null) }

7.2 `this_link_digest` = sha256 of `link.json` minus `this_link_digest`
itself, canonical form. `prev_run_digest` of the genesis link is the frozen
genesis sentinel (a fixed all-zero or named constant, defined at
implementation, identical to the envelope-binding genesis discipline).

7.3 Offline walk, fail-closed conditions (mirroring
`ENVELOPE_BINDING_DESIGN.md` 5.4). The walk REFUSES (non-zero exit, no
partial trust) on any of:
  1. a link whose `conformance.json` fails the existing conformance offline
     verifier (authenticity / binding);
  2. a link whose recomputed `this_link_digest` does not match the recorded
     one (tampered link);
  3. a non-genesis link whose `prev_run_digest` names no present link (a
     truncated or dangling ledger);
  4. more than one genesis, or a cycle, in the ledger (malformed);
  5. a present `receipt.jws` that does not verify against the resolved
     counterparty key, or whose `sub` != this link's `run_identity_digest`,
     or whose `cert_body_sha256` != this link's certificate body sha, or
     whose `conformant` claim != the certificate verdict (forged or
     mis-bound witness);
  6. a `receipt.jws` whose `iss` does not match the owner of the resolved
     key, or whose `aud` does not match the expected world id.
A link with NO `receipt.jws` is VALID but UN-WITNESSED: the walk reports it as
operator-only evidence for that run, never as a failure. Witness is additive.

7.4 The walk's report distinguishes, per link: certified (always, if the link
passes), and witnessed (only if a valid operator-independent counterparty
receipt is present). The ledger-level summary states how many of N runs are
counterparty-witnessed; that ratio is the run-time evidence-surface metric.

================================================================
8. Frozen vocabulary
================================================================

link_kind                 : Literal["run"]   (this ledger; never "build")
witness_kind              : Literal["counterparty"]   (reserved siblings:
                            "tee_attested" already exists in the trace plane,
                            "co_signer" reserved for the structural-independence
                            co-signer forward arc; distinct namespaces)
receipt_format            : Literal["jws_eddsa_v1"]
genesis prev_run_digest   : a single frozen sentinel constant (value fixed at
                            implementation; one genesis per ledger)

These four are byte-level frozen by this document. Adding a value is a new
design increment, never an in-place reinterpretation, exactly as the
stratified-trust triple is frozen in `STRATIFIED_TRUST_DESIGN.md`.

================================================================
9. Serialization and byte-identity contract
================================================================

9.1 Drop-when-absent. `receipt.jws` and the `counterparty_key_uri` field are
present only for witnessed runs. A ledger of un-witnessed runs is byte-
identical to what the same runs would produce with no counterparty mechanism
at all. The continuity ledger therefore preserves byte-identity for every
existing artifact: a pre-S175 dossier is unchanged, and the ledger is a new
sidecar, never a mutation of the certificate, trace, or manifest.

9.2 Canonical form everywhere is
`json.dumps(sort_keys=True, separators=(",", ":"))` over the body minus its
own signature/digest field, matching `conformance_verifier.py`,
`vsa.py`, and `build_vsa.py`. The JWS payload follows RFC 7515 base64url; its
INNER claim object is serialized in the same canonical form before base64url
so the receipt is byte-deterministic given the same claims.

9.3 No partial state is ever signed. A link names its predecessor before it is
signed; a receipt names its run identity before it is signed. A half-declared
link (missing `prev_run_digest`, or a `receipt.jws` whose `sub` is absent) is
REFUSED at construction, never written, mirroring the witnessed-run triple's
construction-time refusal in `STRATIFIED_TRUST_DESIGN.md` 6.

================================================================
10. Verify rule (zero-trust, fail-closed, stock tooling only)
================================================================

A relying party verifies a continuity ledger with cryptography/stdlib for the
chain walk and the conformance legs (the existing offline verifier), plus a
stock JWS/JWT/openssl verification for each counterparty receipt. No NOUS
install is required at any step. The verifier:
  1. walks the chain fail-closed per 7.3;
  2. for each present receipt, resolves the counterparty key from the
     counterparty's published key set (NOT from kid, NOT from any operator
     assertion), then verifies the JWS;
  3. cross-checks every receipt claim against the link it witnesses (sub,
     cert_body_sha256, conformant, prev_run_digest);
  4. reports certified-vs-witnessed per link and the witnessed ratio.
Any failure refuses the whole ledger walk with a typed, cause-first message.

================================================================
11. Honest boundary (restated, inviolable)
================================================================

PROVES: nothing new. The continuity ledger carries no Z3 or Farkas leg. The
only PROVES legs in the system remain the cost-cap Z3 bound and the Farkas
certificates, unchanged.

EVIDENCES: (a) a tamper-evident sequence of conformance-certified runs;
(b) for witnessed links, that a party OTHER than the operator issued a signed
receipt naming that exact certified run; (c) that the witness key is not the
operator's. That is the entire claim.

DOES NOT defeat omission. A run can be left out of the ledger, and a
counterparty can decline to issue a receipt; the ledger then simply has fewer
witnessed links. The ledger proves a real sequence of witnessed runs only
insofar as those links are present, the same omission class
`ENVELOPE_BINDING_DESIGN.md` names for silently un-declared material change. A
verifier MUST NOT read "N witnessed runs" as "these were the only runs."

DOES NOT assert behavior. A valid counterparty receipt EVIDENCES that the
counterparty signed off on a certified run; it does not prove the agent could
not misbehave, exactly as coverage proves no gap in the blocking net, not good
conduct. NOUS remains a monitor, not a guard.

================================================================
12. Relationship to existing ledgers and vocabulary
================================================================

12.1 Not the decision ledger. `decision_ledger.py` is a PRESENTATION view over
a single signed trace (it "does NOT re-verify signatures, does NOT prove a
decision correct"). The continuity ledger is a multi-run, signature-verifying,
chain-walking artifact with an independent witness. The names are kept
distinct deliberately; a future CLI surface must not let the two be confused
(no silent merge across discriminators -> `link_kind` and the format prefix
keep them separable).

12.2 Orthogonal to the witnessed-run triple. The counterparty witness is NOT a
value of `evidence_kind`, `cost_binding`, or `provider_token_integrity`. A run
can be `witnessed_run` / `realized` / `unattested` in the trace plane and
additionally carry a counterparty receipt in the ledger plane; the two planes
do not interact and neither field set changes. This keeps the
`STRATIFIED_TRUST_DESIGN.md` byte-identity invariant intact.

12.3 Generalizes the APR pattern. `attest_apr.py` pins a foreign (enclave) key
via a NOUS-signed record; the counterparty receipt pins nothing through NOUS
-- its root is the counterparty's published key. The continuity design is the
operator-independent endpoint of the same "verify a foreign key's signature
offline" pattern.

12.4 Run-time analog of the release VSA. `build_vsa.py` summarizes federation
witnesses of a BUILD; this ledger summarizes a counterparty witness of a RUN.
Both add a non-operator root alongside the operator's evidence; neither makes
the operator a second builder or a second counterparty.

================================================================
13. Innovation 5-gate check
================================================================

1. Zero-trust verifiable offline? Yes: chain walk + conformance legs are
   cryptography/stdlib; counterparty receipts are stock JWS/JWT/openssl. No
   NOUS install at any step.
2. Trust surface: reduced (net). It adds a non-operator root at run time, the
   first run-time evidence that does not reduce to operator telemetry.
3. Proves vs evidences: respected. Nothing new is proven; the ledger and the
   receipt evidence only.
4. Additive / drop-when-None: yes. Un-witnessed runs are byte-identical to
   today; the ledger and receipts are sidecars; no existing artifact mutates.
5. Honest scope documented in code, docs, and web copy: this freeze is the
   docs leg; the implementation must carry the same boundary in code strings
   and any web surface (omission caveat, monitor-not-guard, proves-nothing).

================================================================
14. Non-goals and deferrals to the implementation session
================================================================

  - No counterparty key-discovery protocol is specified here; key resolution
    is "the counterparty's published key set," mechanism deferred (well-known
    URI vs key transparency vs out-of-band) to implementation, behind the same
    fail-closed rule.
  - No CLI surface, no module API, no test names are fixed here; this is a
    design freeze, not an interface.
  - No co-signer / structural-independence co-signer integration; that is a
    separate forward arc and only shares the `witness_kind` namespace.
  - No change to the release pipeline, the VSA mint, or any existing verifier.

================================================================
15. Open questions for the implementation session
================================================================

  1. Counterparty key discovery: which resolution mechanism is the first
     supported (well-known URI is the lowest-friction; confirm).
  2. Whether the genesis sentinel is shared with the envelope-binding genesis
     constant or a distinct one (recommend distinct, to keep the two chains
     impossible to cross-link).
  3. Whether the operator co-signature (4.3) is in scope for the first
     implementation or deferred (recommend deferred; the independence property
     holds without it).

End of design freeze.
