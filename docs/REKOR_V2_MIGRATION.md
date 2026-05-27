# Rekor v1 -> v2 Migration Plan

> Strategic survival document for the NOUS transparency log layer.
> Sigstore Rekor v2 went GA on 6 October 2025; Rekor v1 entered
> maintenance mode the same day with a 1-year deprecation notice.
> NOUS currently anchors against Rekor v1.

**Status:** <!-- __session95_rekor_v2_status_refresh_v1__ --> The v2 write path has SHIPPED. Originally a
Session 83 scoping document, this plan is now partly realised: NOUS
emits v2-anchored, RFC 3161-timestamped dossiers, verifiable offline.
The v2 anchor is exposed on both CLI dossier paths -- `nous dossier
--anchor rekor_v2` (v5.11.0) and `nous dossier-spec --anchor rekor_v2`
(v5.12.0). The v1 path remains the default; v2 is opt-in. Sections 8-11
below retain the original forward-looking phasing for historical
context and for the remaining phases (v1 retirement) not yet reached.

---

## 1. Purpose

This document scopes the migration of NOUS's Rekor anchoring path from
Sigstore Rekor v1 to Rekor v2. It covers:

- Why the migration is non-optional (v1 deprecation).
- What changes in the wire contract.
- Which NOUS code paths are affected.
- How `Path-beta` dual signing (the ECDSA-P-256 leaf workaround for
  Sigstore issue 851) should be reconsidered under v2.
- The phasing strategy for the migration (dual-write, then v2-only).
- Test fixtures and offline-verifier compatibility for historical
  dossiers.

It is **not** an implementation patcher and ships no code change. The
goal is to make the migration patcher in S84 or S85 mechanical.

---

## 2. Status as of May 2026

| Item | Value |
|---|---|
| Rekor v1 GA | January 2021 |
| Rekor v1 status | Maintenance mode since 6 Oct 2025 |
| Rekor v2 GA | 6 October 2025 |
| Public Rekor v2 URL (current shard) | `https://log2025-1.rekor.sigstore.dev` |
| Log sharding cadence | Approximately every 6 months |
| v1 freeze target | Approximately Oct 2026 (1-year deprecation) |
| NOUS Rekor anchor implementation | `rekor_anchor.py` (Path-beta dual signing, hashedrekord/0.0.1) |
| NOUS Rekor anchor shipped | v5.3.0 (Session 77) |
| First live v1 anchor | log_index 1554376230, 2026-05-16T20:08:25Z |
| NOUS Rekor v2 write path shipped | v5.11.0 (`dossier`), v5.12.0 (`dossier-spec`) |
| NOUS Rekor v2 anchor implementation | `rekor_anchor_v2.py` + `tsa_client.py` (tile-backed log + RFC 3161 trusted timestamp) |
| First live v2 anchor | log_index 4598985 (v5.11.0 e2e) |

The 2025 Rekor v2 instance (`log2025-1.rekor.sigstore.dev`) will be
turned down when a 2026 instance is deployed. Per Sigstore guidance,
clients MUST NOT hardcode this URL; the active instance URL is
distributed via TUF's `SigningConfig`.

References for status:
- Sigstore blog "Rekor v2 GA - Cheaper to run, simpler to maintain"
  (blog.sigstore.dev, 10 Oct 2025).
- `sigstore/rekor` README ("Rekor v1 is in maintenance mode").

---

## 3. Architectural change: Trillian -> Trillian-Tessera

Rekor v1 was built on Google's Trillian (the Certificate Transparency
backend) over MariaDB. Rekor v2 replaces this with **Trillian-Tessera**,
a tile-based transparency log that follows the Certificate Transparency
ecosystem's modernisation pattern.

| Aspect | Rekor v1 | Rekor v2 |
|---|---|---|
| Backend | Trillian + MariaDB | Trillian-Tessera (tile-based) |
| Storage | Log entries + Merkle nodes | Append-only tiles + checkpoint |
| Read API | `Get-By-Log-Index`, `Get-By-Leaf-Hash` | Tile-fetch (clients compute proofs locally) |
| Write API | `/api/v1/log/entries` | `/api/v2/log/entries` |
| Append guarantee | Trillian quorum | Trillian-Tessera + planned synchronous witnessing |
| Operational cost | High | Significantly lower |
| Public-instance SLO | 99.5 percent | 99.5 percent (maintained) |

**Practical consequence for NOUS:** the verification flow changes from
"fetch entry by leaf hash and verify the SET" to "fetch the tiles
covering the entry's log index and verify the inclusion proof against
the checkpoint." The verifier no longer talks to Rekor for inclusion
proofs; the proofs are returned at upload time and persisted with the
artifact.

The Rekor v2 GA blog post explicitly recommends:

> Unless you are monitoring the log for entries, we discourage using
> the read API for computing inclusion proofs. The log will return
> inclusion proofs on upload and these should be persisted alongside
> artifacts and their signatures.

NOUS already persists inclusion proofs in the manifest (`manifest.json`
`rekor_inclusion_proof` field), so this aligns with the current
architecture.

---

## 4. Wire contract: v1 vs v2

### 4.1 Endpoint and version negotiation

| Attribute | Rekor v1 | Rekor v2 |
|---|---|---|
| Entries endpoint | `/api/v1/log/entries` | `/api/v2/log/entries` |
| Service discovery | Hardcoded `https://rekor.sigstore.dev` | TUF-distributed `SigningConfig.rekorTlogUrls` |
| Multiple URLs supported | No | Yes (per `majorApiVersion` + `validFor` window) |
| Single endpoint per shard | Yes | Yes (one upload endpoint per shard) |
| Read API | `/api/v1/log/entries/<uuid>`, `/api/v1/log/entries/retrieve` | Tile-fetch only |

A client must select the first entry from `rekorTlogUrls` whose
`validFor` window is active and whose `majorApiVersion` the client
supports. For Rekor v2 the client picks the highest supported API
version.

### 4.2 Supported entry types

Rekor v2 drops nine of the v1 entry types. Only two remain:

| Type | Rekor v1 | Rekor v2 |
|---|---|---|
| `hashedrekord` | yes (`0.0.1`) | yes (`0.0.2`) |
| `dsse` | yes (`0.0.1`) | yes (`0.0.2`) |
| `intoto` | yes | dropped |
| `rekord` | yes | dropped |
| `helm` | yes | dropped |
| `tuf` | yes | dropped |
| `rfc3161` | yes | dropped |
| `jar` | yes | dropped |
| `rpm` | yes | dropped |
| `cose` | yes | dropped |
| `alpine` | yes | dropped |

NOUS uses `hashedrekord`; the type stays in v2. The version moves from
`0.0.1` to `0.0.2`. The bundle's `kindVersion` field must reflect the
new version.

### 4.3 Supported verifiers

Rekor v2 drops PGP, minisign, pkcs7, SSH, and TUF verifiers. Only
**certificate** or **raw public key** are supported.

NOUS uses raw public key (Ed25519 manifest signature + ECDSA-P-256
leaf via Path-beta); the verifier path remains available in v2.

### 4.4 Request timeouts and batching

Rekor v2 batches requests to enable higher QPS and synchronous
witnessing. Per the GA documentation:

> Clients need to increase request timeouts when creating entries to
> at least 20 seconds. Rekor now blocks on returning a response until
> a checkpoint has been published whose tree size includes the newly
> uploaded entry index.

NOUS's `rekor_anchor.py` currently uses a 10-second default timeout.
This will need to be at least 20 seconds for v2.

### 4.5 Checkpoint and witnessing

Rekor v2 plans to integrate third-party witnessing directly into the
log. Witnesses independently verify log consistency and co-sign
checkpoints with each upload response, raising the bar against a
malicious log operator.

NOUS verification can opt to validate witness co-signatures when they
become available; this is additive and does not change the v1-only
verification path.

---

## 5. `hashedrekord 0.0.1` -> `0.0.2`: what changed

The `hashedrekord/0.0.2` schema was introduced in `sigstore/rekor` for
v1 first (PR 1945, July 2024) and is the only supported version in
Rekor v2. Changes versus 0.0.1:

| Aspect | 0.0.1 | 0.0.2 |
|---|---|---|
| Hash algorithms | SHA-256 | SHA-256, SHA-384, SHA-512 |
| Supported key types | RSA, ECDSA, x509 cert | RSA, ECDSA, x509 cert, **Ed25519ph** |
| Canonicalisation | RFC 8785-style JSON over `spec` | RFC 8785-style JSON over `spec` (same shape) |
| `apiVersion` field value | `0.0.1` | `0.0.2` |
| Wire schema | `hashedrekord_v0_0_1_schema.json` | `hashedrekord_v0_0_2_schema.json` |

The structural change is **adding Ed25519ph as a first-class signature
type**. This is critical for NOUS, see section 6.

---

## 6. Path-beta reconsidered: does v0.0.2 obviate the ECDSA-P-256 leaf?

### 6.1 Why Path-beta exists

NOUS's manifest is signed with Ed25519 (the project's only long-lived
key type, per `cryptography` library defaults and the constitution).
However, Sigstore Rekor v1's `hashedrekord/0.0.1` schema does **not**
support EdDSA keys, due to Sigstore issue 851. The workaround
("Path-beta dual signing") generates a per-submission ephemeral
ECDSA-P-256 keypair, signs the canonical manifest body bytes with the
ECDSA leaf, and submits the ECDSA leaf signature to Rekor. The
long-lived Ed25519 manifest signature is preserved on the manifest
itself; both signatures cover the same canonical bytes.

This is documented in `docs/REKOR_ANCHOR.md` and `rekor_anchor.py`.

### 6.2 What changes in v2

Rekor v2's `hashedrekord/0.0.2` adds **Ed25519ph** as a supported key
type. Ed25519ph is the pre-hash variant of Ed25519: the signer hashes
the message with SHA-512 first, then signs the hash. This is
semantically distinct from plain Ed25519 (which signs the message
directly), and the signature wire format includes a context tag.

**Decision point for NOUS:**

| Option | Mechanics | Trade-off |
|---|---|---|
| (a) Keep Path-beta on v2 | Continue to use ECDSA-P-256 leaf for Rekor, preserve Ed25519 manifest signature unchanged | Lowest code churn; both v1 historical and v2 future use the same dual-sign pattern. Manifest signature stays Ed25519 (pure). |
| (b) Switch to Ed25519ph on v2 | Replace the ECDSA-P-256 leaf with an Ed25519ph signature over the canonical body; submit Ed25519ph signature directly to Rekor v2 | One key type instead of two; cleaner trust model. But the manifest signature is plain Ed25519, not Ed25519ph -- different signatures, different bytes, more code paths. |
| (c) Switch the manifest itself to Ed25519ph | All NOUS-emitted manifests sign with Ed25519ph | Highest disruption: invalidates the verification path of all historical NOUS dossiers (v5.3.0 through v5.5.0). Hard regression. |

**Recommended option: (a).** Rationale:

1. Path-beta is already a working, audited design. The ECDSA-P-256
   leaf is a clearly-bounded ceremony key that does not leak Ed25519
   semantics into the wire format.
2. The manifest's long-lived Ed25519 signature is the trust anchor
   for offline verification. Changing it (option c) breaks every
   historical dossier. Decoupling it from the Rekor leaf (option a)
   keeps offline verification stable.
3. Ed25519ph (option b) would require touching the leaf-signing code
   anyway and would add a new key type to the offline verifier; the
   complexity gain is small. ECDSA-P-256 is well-supported by
   `cryptography` and already in production.

Option (a) keeps the manifest body Ed25519, the leaf ECDSA-P-256, and
only changes the Rekor wire format (v0.0.1 -> v0.0.2, endpoint v1 ->
v2, type identifier in the bundle).

---

## 7. NOUS code paths affected

The migration touches five files plus tests:

| File | Change |
|---|---|
| `rekor_anchor.py` | Add v2 client path (new URL discovery via TUF SigningConfig, v2 endpoint, hashedrekord 0.0.2 entry, 20-second timeout). Keep v1 path for compatibility window. |
| `manifest.py` | Add `rekor_anchor_version` field (`v1` or `v2`) to manifest schema. Existing manifests default to `v1` for backward compatibility. Bump `schema_version`. |
| `dossier.py` `VERIFY_OFFLINE_PY_HYBRID` | Verifier accepts both v1 and v2 anchor formats. For v2: parse `0.0.2` entry, validate inclusion proof against checkpoint (not SET timestamp), use TUF-distributed log public keys pinned at template emit time. |
| `verify_offline.py` (the emitted dossier script) | Same as HYBRID body. |
| `tests/test_rekor_anchor.py` | Add v2 fixtures: `valid_v2_anchor.json`, `tampered_v2_anchor.json`, `wrong_v2_pubkey_anchor.json`. Keep v1 fixtures for regression. |

CLI surface remains unchanged. `--anchor rekor` continues to mean
"anchor to the current default version" (initially v1, then v2).
Operators can opt into v2 via a new flag `--anchor-version {v1,v2}`
during the dual-write window. After v1 freeze, v2 becomes the only
option.

**Wheel content gate:** `scripts/release.py` Phase 7 must continue to
pass; no new top-level modules needed (rekor_anchor.py already
shipped).

**Regression harness:** 57-template byte-identity verification is
unaffected (templates do not include Rekor data).

---

## 8. Trust root and log sharding

Rekor v2 sharding is a structural feature: the log URL changes every
approximately 6 months as new shards are deployed. The 2025-1 shard
is the first; 2025-2 (or 2026-1) will follow.

**Source of truth for the active URL:**

Sigstore's TUF repository distributes `SigningConfig.rekorTlogUrls` as
a list of `{url, majorApiVersion, validFor}` entries. Clients pick the
first active entry that they support.

Example structure (annotated):

```
{
  "rekorTlogUrls": [
    {
      "url": "https://log2025-1.rekor.sigstore.dev",
      "majorApiVersion": 2,
      "validFor": { "start": "2025-10-06T00:00:00Z" },
      "operator": "sigstore.dev"
    },
    {
      "url": "https://rekor.sigstore.dev",
      "majorApiVersion": 1,
      "validFor": { "start": "2021-01-12T11:53:27.000Z" },
      "operator": "sigstore.dev"
    }
  ]
}
```

**NOUS approach:**

1. `rekor_anchor.py` parses `SigningConfig.rekorTlogUrls` and selects
   the active entry matching the configured `--anchor-version`.
2. The TUF root is fetched at submission time. The fetched root is
   pinned into the emitted dossier (`manifest.json`
   `tuf_root_sha256` field) so the verifier can validate the same
   trust root used at submission.
3. Each shard's public key is added to the verifier's pinned key
   allowlist when the shard becomes active. Historical shards remain
   in the allowlist forever to keep historical dossiers verifiable.

The TUF dependency means NOUS will need to either embed `sigstore-tuf`
(or `python-tuf`) as a dependency, or maintain an internal mirror of
the `SigningConfig`. Decision deferred to S84+ (sigstore-tuf adds a
non-trivial transitive surface; an internal mirror is a small JSON
file refreshed monthly via a cron / systemd timer).

**P1 decision (S84):** internal mirror chosen over a `python-tuf` /
`sigstore-python` runtime dependency. The mirror is
`infra/sigstore/signing_config.json`, refreshed by
`scripts/refresh_signing_config.py`, which drives a version-pinned
`sigstore` CLI (`sigstore plumbing update-trust-root`) in an isolated
tool venv and never imports `sigstore` into the NOUS runtime. The
refresh writes to a staging path under an unprivileged user; promotion
into the repo is a deliberate commit. Rationale: the `sigstore-python`
public API churned in 2026 (SigningConfig helpers moved to TrustConfig,
v0.1 support dropped), so NOUS depends on the spec-stable
`signingconfig.v0.2+json` output format, not the unstable Python API.

**Live state (2026-05-20):** the production SigningConfig distributed
via TUF lists only `rekor.sigstore.dev` at `majorApiVersion: 1`.
Sigstore has stated it will not distribute the Rekor v2 URL via TUF
until verification clients have upgraded. The annotated v2 example
above is therefore illustrative; the monthly refresh is what will
surface the v2 entry when Sigstore rolls it out.

---

## 9. Backward compatibility for historical v1 dossiers

**Hard requirement: every NOUS dossier emitted between v5.3.0 and the
v2 cutover must continue to verify offline, forever.**

This holds because:

1. The Rekor v1 log is **immutable**. Entries written in 2026 remain
   queryable (via tile reads) even after v1 is frozen. The signed
   inclusion promise embedded in the manifest is the cryptographic
   evidence; verifying it does not require a live Rekor instance.
2. The v1 log public key remains in the verifier's pinned allowlist
   indefinitely.
3. The offline HYBRID verifier checks the signature, source hash, and
   (when anchored) the inclusion promise via the log's public key.
   None of these require a network call.

**What does require a network call (and therefore degrades after v1
freeze):**

- Active monitoring of the v1 log (rekor-monitor) for new entries with
  a given identity.
- Re-fetching an entry by UUID or leaf hash.

NOUS does not depend on either of these for verification, so v1
freeze does not break historical verification.

**Test obligation:** the HYBRID verifier test suite must include at
least one fixture from a v1-anchored dossier (we already have
`valid_anchor.json` from S77) and one from a v2-anchored dossier
(to be added). Both must pass under the same verifier code path.

---

## 10. Test fixtures needed

`tests/rekor_fixtures/` currently contains three v1 fixtures (Session
77):

```
tests/rekor_fixtures/valid_anchor.json
tests/rekor_fixtures/tampered_anchor.json
tests/rekor_fixtures/wrong_pubkey_anchor.json
tests/rekor_fixtures/valid_inputs.json
```

For v2, add at minimum:

```
tests/rekor_fixtures/v2/valid_v2_anchor.json          # canonical v2 anchor with valid inclusion proof
tests/rekor_fixtures/v2/tampered_v2_anchor.json       # body modified post-sign
tests/rekor_fixtures/v2/wrong_v2_pubkey_anchor.json   # signature OK, wrong log pubkey
tests/rekor_fixtures/v2/v2_inputs.json                # input bytes used to generate the v2 fixtures
tests/rekor_fixtures/v2/sharded_anchor.json           # anchor from a shard that has since been retired (must still verify)
```

Generation: a one-shot fixture generator script (`scripts/gen_rekor_v2_fixtures.py`)
that uploads to the public Rekor v2 instance with a throwaway key,
captures the response, anonymises sensitive fields, and pins the SHA
of each fixture. Run once at fixture-creation time, never in CI.

---

## 11. Proposed implementation phases

<!-- __session99_docs_second_pass_v1__ -->
**Status as of May 2026:** P1 (trust root mirror) shipped in S84 (v5.6.0). P2 (v2 read path: leaf digest + leaf signature + checkpoint signature + RFC 6962 inclusion proof, plus the trusted-timestamp variant) shipped through v5.10.0 and is now the shared read path for both the dossier verifier and the runtime conformance certificate verifier. Rekor v2 is in PRODUCTION USE for runtime conformance certificates as of v5.13.0 (S97); the first publicly demonstrable anchored certificate is at log_index 4679350 (S98, v5.14.0), with its full reproducible bundle served at `nous-lang.org/proofs/cert-4679350/` and verifiable end-to-end in the browser at `/verify.html?demo=cert-4679350`. The dossier write path remains v1-default (P3 unflipped); the v2 write path is available via `--anchor rekor_v2` and is exercised by the conformance certificate flow. P4 (default flip to v2) and P5 (v1 write retirement) remain ahead.


| Phase | Scope | Risk |
|---|---|---|
| P1 -- Trust root mirror | Add `infra/sigstore/signing_config.json` to repo, refresh via cron / systemd timer. Document refresh procedure. | Low |
| P2 -- v2 read path | Add v2 inclusion-proof verification to HYBRID body. Add v2 fixtures. CLI verifier accepts v1 and v2. No write path yet. | Medium (verifier complexity) |
| P3 -- v2 write path (dual) | Add `--anchor-version {v1,v2}` flag to `nous dossier --anchor rekor`. Default remains v1. Emit dossiers that include a `rekor_anchor_version` field. | Medium (live API integration, 20-second timeout) |
| P4 -- v2 default | Flip the default to v2 after one minor version of dual-write soak. Existing v1 fixtures remain in the regression suite. | Low |
| P5 -- v1 retirement | Remove the v1 write path after the v1 freeze date. Keep the v1 read path forever. | Low |

Each phase ships as a single tagged release with its own CHANGELOG
entry, regression-tested against the 57-template baseline.

Suggested target versions:

- P1: v5.6.0 (S84)
- P2: v5.7.0 (S85)
- P3: v5.8.0 (S86, before Oct 2026)
- P4: v5.9.0 or v6.0.0 (after dual-write soak)
- P5: post-v1-freeze (likely Q4 2026 or Q1 2027)

The cliff is Oct 2026. P3 must ship before then.

---

## 12. Migration window timeline

| Date | Event | NOUS posture |
|---|---|---|
| 6 Oct 2025 | Rekor v2 GA, v1 maintenance mode | NOUS v5.5.0 still anchors to v1 (status quo). |
| Q3 2026 (target) | NOUS v5.8.0 ships v2 dual-write | Operator can opt into v2. v1 remains default. |
| Q3 2026 (target) | One minor version of soak | Field validation of v2 anchors. |
| Q4 2026 (target) | NOUS v5.9.0 or v6.0.0 flips default to v2 | v1 still selectable via flag. |
| Approximately Oct 2026 | Rekor v1 freeze (Sigstore-determined) | v1 write path stops working; NOUS v1 write path returns a typed error. v1 read path continues to verify historical dossiers. |
| 2027 | NOUS removes v1 write path entirely | Read path retained; freeze date adds visible deprecation warning to anchor=rekor when v=v1 selected. |

If Sigstore delays the v1 freeze, NOUS dual-write can soak longer.
If Sigstore accelerates the freeze, P3 ships earlier. The schedule
above assumes the stated 1-year deprecation window holds.

---

## 13. Out of scope and open questions

**Out of scope:**

- DSSE entry type. NOUS does not use DSSE; the `hashedrekord` path is
  sufficient for the manifest-signing model. If a future NOUS feature
  needs in-toto attestations, DSSE support becomes its own scoping
  exercise.
- Witness co-signature validation. Rekor v2's planned synchronous
  witnessing is not yet shipped; NOUS will adopt it when the Sigstore
  client spec mandates it.
- Migrating away from `cryptography` for Rekor work. The `cryptography`
  library remains the only crypto dependency. We do not adopt the
  `sigstore` Python package; we keep the wire-level integration we
  already have in `rekor_anchor.py`.

**Open questions:**

1. **TUF root distribution mechanism.** Embed `python-tuf` (adds
   dependencies) or mirror `SigningConfig` internally (adds an
   operational refresh task)? Decision deferred to P1.
2. **Synchronous witnessing.** Adopt when Sigstore mandates it, or
   adopt earlier? Recommend "when mandated by client spec".
3. **Multi-log support.** Some users may prefer a private Rekor v2
   instance. Should NOUS support an operator-configurable Rekor URL?
   Out of scope for the migration; defer to a separate feature.
4. **Path-beta retirement.** Once Ed25519ph is broadly supported, is
   the ECDSA-P-256 leaf still worth maintaining? See section 6;
   recommend "retain" for stability, revisit in 2027.

---

## 14. References

**Sigstore:**

- "Rekor v2 GA - Cheaper to run, simpler to maintain"
  (blog.sigstore.dev, 10 Oct 2025).
- "Rekor v2 - Cheaper to run, simpler to maintain" (alpha announcement,
  blog.sigstore.dev, 17 Apr 2025).
- `sigstore/rekor` README, "Rekor v1 is in maintenance mode" section.
- `sigstore/rekor-tiles` repository (v2 implementation).
- `sigstore/rekor-tiles/CLIENTS.md` (client compatibility spec).
- Sigstore architecture-docs `client-spec.md` (verifier requirements).
- Sigstore bundle format documentation (`docs.sigstore.dev/about/bundle/`).

**Wire schemas:**

- `hashedrekord_v0_0_1_schema.json` (current NOUS pin).
- `hashedrekord_v0_0_2_schema.json` (Rekor v2 mandatory).
- Sigstore PR 1945 (hashedrekord 0.0.2 addition of SHA384/SHA512 and
  Ed25519ph).

**NOUS internal:**

- [REKOR_ANCHOR.md](REKOR_ANCHOR.md) -- current v1 anchoring design.
- [VERIFY_DOSSIER.md](VERIFY_DOSSIER.md) -- V2 verify-dossier surface
  consuming the anchor evidence.
- [ANNEX_IV_MAPPING.md](ANNEX_IV_MAPPING.md) -- regulatory context for
  why Rekor anchoring matters (Annex IV item 6, lifecycle changes).

---

*Last updated: Session 83, 19 May 2026 (HEAD: post-`f584c4b`, v5.5.0).*

<!-- __session83_rekor_v2_migration_v1__ -->
<!-- __session84_rekor_p1_mirror_v1__ -->
