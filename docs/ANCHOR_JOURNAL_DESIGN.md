# Anchor Journal -- a release-VSA anchor that resumes instead of submitting twice (S386)

<!-- __s386_anchor_journal_design_v1__ -->

Status: Innovation Gate dossier and decisions D386-1 to D386-6, recorded
before any code. Build notes are appended in section 16 with the code
that implements them.

Marking. [reading] is a statement from reading the source at 776327d,
the HEAD Server A printed at 2026-09-27 09:09:24Z. [container] is a value
measured in the chat container on a clone of 776327d on 2026-09-27
between 09:06Z and 09:35Z. [upstream] is read from an upstream
repository cloned in the container on 2026-09-27, at the commit named.
[web] is a page read on 2026-09-27. [testimony] is taken from the S385
handoff or from a third party, and is not re-verified.

---

## 1. Problem statement

`mint_release_vsa.py anchor` writes the release VSA's payload digest to
the Rekor v2 log. That write is permanent. The tool keeps no record that
it was attempted, so a failure after the write followed by a rerun
submits a second entry for the same VSA (FG-S385-D, S385 handoff section
5). In S385 a session driver, vsa_s385.py, wrote a marker before the
anchor ran; that driver is archive outside the tree [testimony]. The
next release VSA must not depend on rebuilding it (opener S386, section
3 item 4).

## 2. What the code does [reading]

`anchor()` (mint_release_vsa.py, from line 873) runs, in order:

1. checks the minted files, the alias, the pins, and that the Rekor
   bundle file does not exist yet;
2. calls `anchor_fn`, by default `rekor_anchor_v2.anchor_manifest_to_rekor_v2`,
   which makes a fresh ephemeral ECDSA P-256 key, signs, and POSTs. This
   is the one irreversible act;
3. prints the log index to stdout only;
4. calls `timestamp_fn` (the TSA) over the entry signature;
5. assembles the bundle and writes it with its sidecar;
6. runs the offline dual-root verify on a copy;
7. writes index.json with its sidecar.

`main()` catches only `MintError`. The network clients raise
`rekor_anchor.RekorUnavailable` and `RekorRejected`, which derive from
RuntimeError. The Rekor client's read timeout is 15 s and its connect
timeout 5 s (rekor_anchor.py:42-43). A retry of step 2 uses a new key and
a new signature, so Rekor cannot recognise it as a duplicate.

## 3. Measurements [container]

The seams of `anchor()` were driven with a replay of the published 6.0.1
bundle (log_index 127205986); fake pins; a verify seam that returns the
status under test. Script: /home/claude/work/fg385d_repro.py (container
only).

| Case | Result |
|---|---|
| Control, no failure | 1 POST; bundle and index written; rc 0 |
| TSA fails after the POST, then rerun | run 1: RekorUnavailable escapes, not MintError, no bundle; run 2: a second POST, then success. 2 POSTs |
| Verify fails after the bundle write, then rerun | run 1: MintError, bundle present, index absent; run 2: refused "rekor bundle already exists". 1 POST, and no way to finish |
| TSA failure through `main()` | RekorUnavailable is not caught: a traceback and rc 1, not "ANCHOR REFUSED" |
| NOUS's Rekor client (`anchor_manifest_to_rekor_v2`) against a local server that reads the whole request, then answers after 4 s; client read timeout 1 s | client: RekorUnavailable, cause ReadTimeout; the server had recorded the full 412-byte request |
| The same client against a closed local port | RekorUnavailable, cause ConnectError |

The fifth row shows that a timeout does not tell the client whether the
entry was created.

## 4. Prior art

- sigstore-python, main 1921163a (2026-09-23), sigstore/sign.py
  (sha256 ef5febdf...), `_finalize_sign`: the TSA timestamp over the
  signature is requested first, then the Rekor entry is created
  [upstream]. NOUS does the two in the other order.
- rekor-tiles, main 8f6548f (2026-09-25) [upstream]:
  - internal/server/service.go (c67f64a3...): a duplicate entry returns
    gRPC AlreadyExists (HTTP 409) with an `x-log-index` header naming
    the existing entry;
  - internal/tessera/tessera.go (5c5384c0...): duplicates are detected
    by an in-memory LRU of 256 entries, always on, plus an optional
    persistent store behind the `persistent-antispam` flag. Whether the
    public log2025-1 instance sets that flag is unknown;
  - CLIENTS.md (9384f0fd...): the server holds the response until a
    checkpoint that includes the entry is published (line 134); clients
    fetch the RFC 3161 timestamp themselves (line 147); there is no
    search API (lines 372-377).
- Sigstore, "Rekor v2 GA" (2025-10-10): no Get-By-Log-Index or
  Get-By-Leaf-Hash API [web]. An entry whose index was lost cannot be
  looked up.
- A write-ahead intent record with an idempotent resume is a standard
  pattern (database write-ahead logs, HTTP idempotency keys). Only
  sigstore-python's sign path was searched for a client that journals a
  submission; absence elsewhere is not asserted.
- In this project: the S385 driver's ANCHOR_ATTEMPTED marker
  (vsa_s385.py, 84f1daa8..., archive).

## 5. Patent landscape

UNKNOWN. No professional search has been made. The mechanism is a
generic write-ahead record; this section clears nothing.

## 6. Claim class

None new. The change is an operator-side property of one tool, checked
in its tests through the seams: one anchor run, with any number of reruns, submits at most
one Rekor entry per minted VSA, except that a rerun after an attempt
whose outcome the tool could not determine refuses instead of submitting.
No published artifact, verifier, index field or copy changes.

## 7. Honest boundary

- The journal is local operator state. It is never published and is not
  evidence for a third party. A stranger's verification of a release VSA
  is the same before and after this change.
- It does not prevent a second entry made outside the tool, or after an
  operator deletes the journal by hand.
- It does not find an entry whose submission timed out. Rekor v2 offers
  no search, and the tool will not re-submit to find out.
- The Rekor duplicate check (section 4) is not relied on anywhere.

## 8. Reasons this should never exist

- R1. The harm is small. The published bundle names one entry and the
  offline verifier checks only that one; a second entry changes no
  verification result, and Rekor v2 has no search, so the entry is found
  only by reading the log's tiles.
- R2. The failure is rare: one anchor per release, and the S385 anchor
  succeeded on its first run [testimony].
- R3. A session driver already solved it once, and could be rebuilt.
- R4. It adds a file whose loss or forgery changes behaviour. A deleted
  journal re-enables a second submission; a forged LOGGED journal could
  make the tool assemble a bundle around a foreign entry.
- R5. It refuses some reruns that would have been harmless: a timeout
  on a request the server never processed looks the same as one it did.
- R6. The same pattern stays in 12 other callers of
  `anchor_manifest_to_rekor_v2` (13 files call it, this tool included).

Answers, where there are any. R3: the driver is archive outside the tree,
and the next release's anchor would rest on a session rebuilding it
correctly; the tool is the durable place. R4: before any network call, a
resume checks that the journaled leaf's digest equals this VSA's payload
digest, and the offline dual-root verify still runs on the assembled
bundle before index.json is written, so an entry that is not in the
pinned log fails there. R5 is accepted: refuse over guess. R1, R2 and R6
are not answered; they set the size limits in section 10.

## 9. Commodity vs moat

All commodity. This is a feature of an operator tool, not an arc.

## 10. Kill criteria

- KC1. The implementation needs a change to rekor_anchor_v2.py,
  tsa_client.py, cli_verify_release.py or the emitted offline verifier:
  stop and return to design.
- KC2. Any file other than the existing 8 (after mint) and 12 (after
  anchor) lands in the bundle directory: stop.
- KC3. tests/test_s172_p0b2_anchor_orchestrator.py,
  tests/test_s236_release_vsa_alias.py or
  tests/test_s226_backfill_disclosure.py need an edit to stay green:
  stop.
- KC4. The resume cannot check that the journaled entry binds this VSA's
  payload digest before calling the TSA: fall back to option A (refuse
  only).

## 11. Opportunity cost

It displaces D8 (the claude price cliff, 2026-12-08), which is better
done close to the next release because its window counts from the read
date; the CostTracker recon; and D376-10, which needs a release anyway.
The next release VSA needs this closed, or a driver rebuilt (opener S386,
section 3 item 4). Ranked first.

## 12. Generalization path

Narrow first: the release-VSA anchor only. If it holds up as additive, the
next candidate is `scripts/publish_verifier_registry.py anchor`, which is
also part of every release. A shared primitive (a sign/submit split in
rekor_anchor_v2 with the TSA first, as sigstore-python orders it) waits
for a second consumer that needs it.

---

## 13. Decisions

- D386-1. The journal is a sibling of the resolved bundle directory,
  `<dir>.anchor-journal.json`, never inside it. The command line does
  not change, and neither do the bundle's file sets.
- D386-2. The journal is canonical JSON (sorted keys, ASCII) with a
  schema number, the version, vsaPayloadSha256, the Rekor base URL, a
  state, and, from LOGGED on, the log index, log id, canonicalized body,
  checkpoint envelope and inclusion-proof hashes returned by the POST.
  Each write goes to a temporary file in the same directory, is flushed
  and fsynced, replaced atomically, and followed by an fsync of the
  directory.
- D386-3. States and reruns:

  | Found | Action |
  |---|---|
  | no journal, no bundle | write ATTEMPTED; POST; write LOGGED; TSA; bundle; verify; index |
  | POST raised RekorUnavailable caused by httpx.ConnectError or httpx.ConnectTimeout | no request left the host: remove the journal; refuse; a rerun starts fresh |
  | POST raised anything else | keep ATTEMPTED; refuse, "rekor outcome unknown" |
  | ATTEMPTED, no bundle | refuse with no network call; an entry may exist; the tool never submits again for this journal |
  | LOGGED, no bundle | no POST; check version, payload digest and the journaled leaf digest; then TSA, bundle, verify, index |
  | LOGGED, bundle present, index absent | no network; check the bundle's body and log index equal the journal's; verify; index |
  | bundle present, no journal | refuse, as today |
  | bundle and index present | refuse, as today |
  | journal for another version or payload, or unparseable | refuse |

- D386-4. Every failure of the POST, the TSA, the verify or a write
  surfaces as MintError whose message starts with the cause and states
  the journal state and whether a rerun resumes. `main()` keeps printing
  "ANCHOR REFUSED" with rc 2. Only RekorUnavailable, RekorRejected,
  httpx.HTTPError and OSError are converted; any other exception is a
  defect and keeps its traceback.
- D386-5. The order stays Rekor, then TSA. The TSA-first order is
  deferred (section 12): it needs a sign/submit split in rekor_anchor_v2,
  which 13 files call, and it would change what BACKFILL_NOTE's "records
  that anchor instant" means for later backfill VSAs.
- D386-6. Scope: mint_release_vsa.py, one new test file, this document
  and its README link. No change to rekor_anchor_v2.py, tsa_client.py,
  cli_verify_release.py, the emitted verifier, BACKFILL_NOTE,
  REKOR_LEG_BOUNDARY or the index schema.

## 14. Test plan (red first)

A new tests/test_s386_anchor_journal.py drives `anchor()` through its
seams with a replay of the published 6.0.1 bundle. Each test below fails
on 776327d, read by failing id and reason from --junitxml:

- a TSA failure after the POST, then a rerun: one POST in total, and
  bundle and index written;
- an ambiguous POST failure, then a rerun: refused, with no second call
  to the POST seam;
- a POST failure caused by ConnectError: MintError, no journal left, and
  the rerun submits once;
- a verify failure after the bundle write, then a rerun: finishes with
  no POST and no TSA call;
- a network failure through `main()`: "ANCHOR REFUSED" and rc 2;
- a success leaves the journal beside the directory in state LOGGED, and
  the directory holds exactly the expected names;
- a LOGGED journal whose digest does not match this VSA: refused with no
  network call;
- an unparseable journal: refused with no network call.

The five tests in test_s172_p0b2 stay green without edits.

## 15. Outside this unit

- docs/REKOR_V2_MIGRATION.md gives Rekor v1 an "Oct 2026" freeze.
  Sigstore wrote on 2026-06-28 that the public instance stays on Rekor v1
  by default for the foreseeable future, and its Rekor v2 GA post
  (2025-10-10) says a v1 freeze will be announced one year ahead [web].
  D376-2 bars editing the design doc for wording; recorded in the S386
  handoff.
- The anchor's default log is hardcoded to log2025-1. Sigstore's Rekor v2
  GA post asks clients not to hardcode the URL and says instances will
  rotate [web]. Third-party reports: log2026-1 did not resolve on
  2026-07-29, and one production v2 shard was found on 2026-09-08
  [testimony]. S385 anchored to log2025-1 at 2026-09-27 02:12:32Z. Not
  fired.

## 16. Build notes

None yet.
