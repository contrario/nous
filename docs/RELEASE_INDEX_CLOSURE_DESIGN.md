# Release Index Closure -- index.json as the image of verified inputs (S502)

<!-- __s502_release_index_closure_design_v1__ -->

Status: Innovation Gate dossier and decisions D502-1 to D502-9, recorded
before any code. Build notes are appended in section 16 with the code
that implements them. Origin: S500's board item 1, FG-S485-AN.

Marking. [reading] is a statement from reading the source at 9a5b1b98,
GitHub main and Server A's live tree since 2026-11-26 11:53:51Z. [container]
is a value measured in the chat container on an export of 9a5b1b98 on
2026-11-26 between 12:00Z and 12:06Z (scripts and outputs kept in the
seat S502's evidence, i1/). [web] is a page read on 2026-11-26.
Nothing here is a Z3 or Farkas result.

---

## 1. Problem statement

Each release-VSA directory (website/.well-known/nous/release-vsa/<v>/)
serves index.json beside the VSA, the Rekor bundle, the offline verifier
and the key record. index.json names the wheel and sdist digests, the
verifier and key digests, the Rekor log index and the build identity.
It is not signed. No verifier reads it (FG-S485-AN, S485). The public
guide docs/VERIFYING_A_RELEASE.md, section 1.2, asks a user to compare
the wheel PyPI served with "what the index records" and to stop if they
differ: a decision taken on an unsigned file. scripts/cold_audit.py
binds two of its fields (S485).

## 2. What the code does [reading]

- mint_release_vsa.py `anchor()` writes index.json once, after the
  post-anchor dual-root self-verify, as
  json.dumps(build_release_index(...), sort_keys=True, indent=2), with
  its .sha256 sidecar. build_release_index takes the VSA statement, the
  Rekor bundle, four file names, the committed operator pin, the payload
  digest, the RFC3161 time the self-verify returned, and emitted_at (the
  wall clock at write time). It hashes the co-served files it names.
- cli_verify_release.py (nous build-attest-verify) checks ROOT 1 (the
  DSSE signature under the pinned key), ROOT 2 (Rekor v2 inclusion,
  checkpoint and RFC3161 time) and their BINDING. It does not open
  index.json.
- The served verify_build_vsa_offline.py checks the signature, identity,
  policy and the present subjects' digests. It does not open index.json.
- cold_audit.py `_bind_index` requires the index's vsaPayloadSha256 and
  its wheel name and digest to equal the VSA's.

## 3. Measurements [container]

Scripts i1/probe_i1v3.py and i1/probe_m1b.py, run with -I -B.

| Measure | Result |
|---|---|
| M1 re-derive each served index from its own directory, emittedAt and rfc3161GenTime from the index | 19 of 41 byte-equal (5.79.0 to 11.0.0); 22 (5.60.1 to 5.78.0) differ only in the Rekor leg's boundary text |
| M1b the same with the older boundary text, read from 5.78.0's index | 41 of 41 byte-equal: 19 new era, 22 old era |
| M2 11.0.0, the wheel present, one field changed with its .sha256 rewritten: T1 payload digest zeroed, T2 wheel digest, T3 verifier digest, T4 logIndex + 1, T5 sourceCommit, T6 a duplicate key (first false, last true), T7 10.0.0's index | served verifier PASS rc 0 and build-attest-verify CONVERGENCE PASS rc 0 on all seven and on T0 |
| M3 cold_audit `_bind_index` on T0 to T7 | refuses T1, T2, T7; passes T0, T3, T4, T5, T6 |
| M3 the strict loader (conformance_verifier.loads) | refuses T6 (duplicate key); parses the rest |
| M4 emittedAt over 41 | 41 in the form YYYY-MM-DDTHH:MM:SSZ; 38 equal rfc3161GenTime; 5.60.1 is earlier than it |
| M5 co-served files over 41 | release-verifier-key.json one digest (e9cd1a34); verify_build_vsa_offline.py three (8bdb7a5e x22, 2d24b70d x16, cca57a4c x3), named by no signed object |

T6 is a parser differential: Python keeps the last of two equal keys, a
first-wins parser keeps the first.

## 4. Prior art

- TUF signs its targets metadata and names mix-and-match and arbitrary
  installation among the attacks it answers [web, theupdateframework.io].
- sigstore/model-transparency (standing obligation, REJECTED_IDEAS.md R4
  note b) signs a manifest of file digests; its verifier checks the
  signature, then computes the files' hashes again and compares them
  with the signed ones [web, pypi model-signing 1.0.0].
- Reproducible builds compare bytes rebuilt from source; Kettle (arXiv
  2605.08363) recomputes sha256 over a canonical serialization of
  provenance and checks it against attested data [web].
- JSON parser differentials on duplicate keys: Bishop Fox's survey of 49
  parsers; Moeller et al., ASIA CCS 2024 [web].
Recompute-and-compare is prior art. Not found in the searches run: an
unsigned release index accepted as the byte-exact image of a function
over inputs the verifier has already authenticated, with no signature
over the index. Searches: SLSA VSA v1.1; TUF security; model-
transparency; "verifier recomputes release manifest"; JSON duplicate
keys; one USPTO full-text query. Not a survey.

## 5. Patent landscape

Unknown. One full-text query; generic claims on comparing metadata with
a signed copy exist (US 12542680). Freedom to operate is not assessed and
not assumed.

## 6. Claim class

Every byte of a served release index, except emittedAt, is reproduced
by the verifier from inputs it has already authenticated, and the index
is accepted only if it equals that reproduction byte for byte. The
inputs: the operator-signed VSA payload (ROOT 1), the Rekor v2 bundle
and RFC3161 time (ROOT 2), the pinned key's record, the offline
verifier's digest against a committed table, and a committed boundary
text by version. It reaches the 41 served indexes as they are, without
a new signature (M1b).

## 7. Honest boundary

EVIDENCES that the index is the deterministic image of those inputs.
Does NOT evidence emittedAt (unbound, its form only). Does NOT check the
wheel or sdist bytes (the offline verifier does, from the VSA). Does NOT
re-derive the federation attestations. A user of a verifier older than
this change gets no closure; the served verifier of each released
version is frozen and does not gain it. PROVES nothing: no Z3 or Farkas
leg. The evidence layer is a monitor, not a guard.

## 8. Reasons this should never exist

- R-a. Cheaper: rewrite step 1.2 of the guide to trust only the VSA and
  call the index informational. No code.
- R-b. The closure reaches users only through the next release of nous
  build-attest-verify; the served scripts are frozen per version.
- R-c. A verifier that imports the mint inherits its root guard (the
  probe was refused at import as root without -I -B, [container]).
- R-d. A committed table of verifier digests must grow with every
  verifier change; a missed entry fails a good release.
- R-e. One more leg in a verifier that has three.
Answer. R-a removes the user's unsafe step and leaves the index
unverifiable for cold_audit, the site and any reader; it is taken as
well (D502-8). R-c is met by a pure module the verify path owns
(D502-5, D502-6). R-d fails at the operator's own build, where
cold_audit and the suite run the closure over every served directory,
before a user sees it. R-b stands.

## 9. Commodity vs moat

Commodity: the technique; model-transparency compares recomputed
digests with a signed manifest, and a competitor could add this leg in
days. Moat: none claimed. What is particular is the composition already
in place (operator VSA, Rekor v2 binding, offline verifier) and the
reach over the 41 published indexes without re-signing.

## 10. Kill criteria

Prior art for the exact claim: not found in the searches run, not
excluded. Patent: unknown. Honest boundary: kept (section 7). Overclaim:
none needed. Offline verification: yes. Deterministic replay: 41 of 41
measured. The auditor must trust the operator: no more than today, the
same pin. None fired.

## 11. Opportunity cost

One pure module of about 200 lines, one verifier leg, tests, a guide
section rewritten, about one seat; and the next release to reach users.
Not the witness or split-view work on the board (FG-S485-AO).

## 12. Generalization path

Release-VSA index.json only. If it holds, other served unsigned views
with a deterministic writer (the vsa-vectors and provenance indexes) are
candidates, each with its own measurement. Not before.

## 13. Decisions

- D502-1. Scope: index.json in each release-VSA directory, and nothing
  else served.
- D502-2. Closure is byte equality. The verifier derives the index and
  accepts only the same bytes. emittedAt is the one unbound field; it
  must match ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$
  and nothing else is asked of it. index.json is read with a 1 MiB cap
  and parsed only by the strict loader (duplicate keys refused), only to
  take emittedAt.
- D502-3. Inputs, each from what the verifier already checked: the
  statement from the ROOT 1 verified payload; the bundle ROOT 2
  verified; rfc3161GenTime from ROOT 2's evidence; vsaPayloadSha256 the
  sha256 of the verified payload; the pin the committed constant; the
  VSA and bundle files by the version's names. release-verifier-key.json
  must be byte-equal to the canonical record of the pinned key (M5: one
  digest in 41). verify_build_vsa_offline.py must hash to one of a
  committed table, today the three digests of M5.
- D502-4. The Rekor leg's boundary text is chosen by version: below
  5.79.0 the older text, from 5.79.0 the current one; both committed.
  An index carrying the other era's text fails.
- D502-5. Placement: a new pure module release_index.py (no network, no
  root guard, reads only the files it names) and a fourth leg INDEX in
  cli_verify_release: PASS, FAIL or ABSENT. ABSENT when the bundle
  directory holds no index.json (the mint's own post-anchor self-verify
  stages none): reported, the convergence unchanged. FAIL makes the
  convergence FAIL, rc 1. Rule 9: the module is registered in pyproject
  py-modules and in scripts/release.py's wheel gate in the same patch.
- D502-6. The mint is not changed. release_index.py carries its own
  derivation, held byte-equal to mint_release_vsa.build_release_index by
  tests over the 41 served directories and over synthetic statements.
  Reason: the mint runs as root through the S485 guard, and a mint
  change reopens its release rehearsal. Revisit when the mint's index
  changes.
- D502-7. cold_audit keeps _bind_index and gains the closure through
  nous build-attest-verify, which it already runs on the served
  directory.
- D502-8. The served verify_build_vsa_offline.py is not changed in this
  unit. Guide section 1.2 is rewritten in the build commit: the wheel is
  bound to the VSA's subject by the verifier, and the index is named as
  checked by build-attest-verify's INDEX leg, not by the reader.
- D502-9. The INDEX leg's boundary: "EVIDENCES that index.json is the
  deterministic image of the verified VSA payload, the verified Rekor
  bundle and time, the pinned key and a known verifier; emittedAt is
  not evidenced. PROVES nothing."

## 14. Test plan (red first)

A new tests/test_s502_release_index_closure.py. Each test below fails on
9a5b1b98 (no module, no leg), read by failing id and reason from
--junitxml:

- each of the 41 served directories: closure PASS, and the derived bytes
  equal mint_release_vsa.build_release_index's for the same inputs;
- 11.0.0 with T1 to T7 of M2: INDEX FAIL and build-attest-verify rc 1;
  T6 refused by the strict loader before any derivation;
- emittedAt changed to another well-formed time: PASS, the leg naming it
  unbound; emittedAt malformed: FAIL;
- a co-served file missing; the key record changed; the verifier script
  changed with the index changed to match it (a coherent swap): FAIL;
- a new-era version carrying the old boundary text: FAIL;
- an index over 1 MiB: FAIL before parsing;
- no index.json in the directory: INDEX ABSENT, convergence unchanged
  (the mint's self-verify path).
Mutants: each check removed in turn must turn a named test red.

## 15. Outside this unit

- The guide's v3 VSA vector step takes the signer key for
  --expect-signer from the vector's own unsigned index.json [reading].
  Observed, not measured.
- No witness cosignature is read; a split view of the log is not
  excluded (FG-S485-AO). Unchanged.

## 16. Build notes

<!-- __s502_release_index_build_notes_v1__ -->

Recorded with the build commit. [container] is a value measured in the chat
container on an export of b7cff195 on 2026-11-26.

- B502-1. The VSA and bundle digests are taken from the bytes ROOT 1 and
  ROOT 2 read, under the version's file names (D502-3); the version-named
  copies on disk are not read. A directory whose canonical bundle verifies
  while its version-named copy is damaged stays PASS, as it does today
  (tests/test_s485_convergence_pins.py, X03).
- B502-2. The verifier digest and the Rekor boundary text are tables by
  first version; a version takes the last row at or below it: verifier
  8bdb7a5e from 5.60.1, 2d24b70d from 5.79.0, cca57a4c from 9.0.0
  [container, 41 of 41]. This is tighter than "one of a committed table"
  (D502-3): an older verifier served with a newer release fails. A test
  holds the last row equal to what build_vsa emits today, so a verifier
  change fails at its own commit.
- B502-3. The INDEX outcome is result["index_closure"]. It is in
  result["legs"] only when index.json is present, so the reading
  "CONVERGENCE PASS iff every leg PASS" (tests/test_s167_cli_verify_release.py)
  still holds when the leg is ABSENT.
- B502-4. release_index.py is on build-attest-verify's input reads, so the
  AN-GATE-1 scans cover it (tests/test_an_js_inventory.py, SCOPE_P). Its two
  strict sites, [js:rix.1] index.json and [js:rix.2] canonicalized_body,
  are reached by tests/test_an_js_strict_rix.py, which sorts before
  tests/test_an_js_zz_sites.py.
- B502-5. scripts/cold_audit.py's Rekor section and the guide's 1.5 also
  fetch release-verifier-key.json, and the cold audit the verifier, beside
  index.json: without them the INDEX leg of a release that carries it
  fails the cold audit (D502-7).
- B502-6. The leg reads index.json, the verifier and the key record with
  a 1 MiB cap, regular files only, opened non-blocking: a FIFO or a
  directory under one of those names fails at once.
