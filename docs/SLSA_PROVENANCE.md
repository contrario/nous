# SLSA Provenance (build leg)

NOUS emits SLSA Provenance v1 over its own release artifacts. When the release
pipeline builds the `nous-lang` wheel and sdist, it also produces a
DSSE-wrapped in-toto Statement v1 carrying a `https://slsa.dev/provenance/v1`
predicate that names those exact artifacts, the source commit they were built
from, and the build environment that produced them. The statement is Ed25519
signed by a dedicated builder key and, optionally, anchored into the public
Sigstore Rekor v2 transparency log.

This is the build leg only. It describes how the published package was built.
It does not attest that any particular program executed; runtime execution
evidence is a separate concern (see `docs/CODEGEN_BINDING.md` and
`docs/ATTESTATION_RECEIPT.md`).

## Honest SLSA Build Level 1

The NOUS release is produced by running `scripts/release.py` ad-hoc on an
operator-controlled host. Under the SLSA build track that is Build Level 1:
the provenance exists, is complete, is signed, and is transparency-logged when
anchored, but the build platform is neither hosted nor isolated. NOUS labels
this exactly and does not overclaim.

The two identifying URIs encode that reality:

- `buildType`  = `https://nous-lang.org/buildtypes/release-script/v1`
  The build was defined by the `scripts/release.py` pipeline. External
  parameters are the source repository, the release ref, the commit, and the
  version.
- `builder.id` = `https://nous-lang.org/builders/release-script-adhoc/v1`
  The builder is the ad-hoc, operator-run release script. This is deliberately
  not a hosted-CI or hardened-platform identifier. A verifier that reads this
  id must treat the build as L1: operator-run, not isolated, not hermetic.

What L1 is NOT:

- It is not Build Level 2: there is no hosted build platform signing the
  provenance independently of the operator.
- It is not Build Level 3: the build is not run in a hardened, isolated
  environment that prevents operator interference.

The predicate carries this cap in machine-readable form under the NOUS
extension key `https://nous-lang.org/provenance/ext/v1`:

    "slsaBuildLevel": 1,
    "buildPlatformClass": "adhoc-operator-run-script",
    "scope": "EVIDENCES build composition ... Does NOT prove builder
              integrity, hermeticity, isolation, or source-to-artifact
              reproducibility. SLSA Build Level 1 ... NOUS is a monitor,
              not a guard."

## Separation of duties

The provenance is signed by a builder key that is cryptographically distinct
from the VSA verifier key (`docs/NOUS_VSA.md`). The principal that builds the
artifacts and the principal that audits policy conformance are different
identities, and they sign with different keys, even in the L1 environment.

- Builder key: `~/.local/share/nous/keys/provenance_signing.key`
  (raw 32-byte Ed25519 private key, created on first emission with mode 0600
  under a 0700 keys directory).

The provenance emitter carries its own canonicalization and DSSE
pre-authentication encoding and never imports the VSA module, so the byte
stability of the provenance leg and the VSA leg are independent.

## Predicate shape

    {
      "_type": "https://in-toto.io/Statement/v1",
      "subject": [
        {"name": "nous_lang-<v>-py3-none-any.whl", "digest": {"sha256": "..."}},
        {"name": "nous_lang-<v>.tar.gz",           "digest": {"sha256": "..."}}
      ],
      "predicateType": "https://slsa.dev/provenance/v1",
      "predicate": {
        "buildDefinition": {
          "buildType": "https://nous-lang.org/buildtypes/release-script/v1",
          "externalParameters": {
            "repository": "https://github.com/contrario/nous",
            "ref": "refs/tags/v<v>",
            "commit": "<git HEAD sha>",
            "version": "<v>"
          },
          "internalParameters": {"buildScript": "scripts/release.py"},
          "resolvedDependencies": [
            {"uri": "git+https://github.com/contrario/nous@refs/tags/v<v>",
             "digest": {"gitCommit": "<git HEAD sha>"}}
          ]
        },
        "runDetails": {
          "builder": {
            "id": "https://nous-lang.org/builders/release-script-adhoc/v1",
            "version": {"python": "...", "build": "...", "setuptools": "..."}
          },
          "metadata": {
            "startedOn": "<RFC3339 Z>",
            "finishedOn": "<RFC3339 Z>",
            "invocationId": "<uuid4>"
          }
        },
        "https://nous-lang.org/provenance/ext/v1": {
          "slsaBuildLevel": 1,
          "buildPlatformClass": "adhoc-operator-run-script",
          "scope": "..."
        }
      }
    }

The DSSE envelope wraps this statement as the canonical (sorted-keys, compact)
JSON payload with `payloadType` `application/vnd.in-toto+json`; the signature
is taken over the DSSE pre-authentication encoding of that payload.

## Emission

    python3 scripts/release.py --build     # emits provenance, no upload
    python3 scripts/release.py --upload    # emits provenance, then uploads

`phase_provenance` runs after the install smoke and before the `--build`
early return, so both build-only and full-upload runs emit it. It writes:

    dist/nous_lang-<version>.provenance.intoto.json

With `--anchor`, the canonical statement bytes are submitted to Rekor v2 and a
sidecar is written next to the envelope:

    dist/nous_lang-<version>.provenance.rekor.json

The sidecar records the log index, log id, checkpoint, inclusion-proof hashes,
and the sha256 of the exact canonical statement that was anchored. Anchoring is
opt-in and is the only step that touches the network; the default run is
hermetic. A `--anchor` run that cannot reach Rekor aborts the release.

## Honest boundary

This provenance EVIDENCES build composition: it binds the published wheel and
sdist digests to a build definition and a builder identity via an Ed25519
signature over the DSSE payload, and, when anchored, to a public transparency
log entry.

It does NOT prove builder integrity, hermeticity, isolation, or
source-to-artifact reproducibility. There is no SMT proof leg here and no
guard. The signature evidences who recorded the provenance and over which
bytes; it does not certify that the build environment was trustworthy. That
distinction is the whole content of the L1 label.

## Determinism

The statement is byte-deterministic given identical inputs: the canonical form
is sorted-keys compact JSON, the same form used by the manifest and VSA legs,
and the builder key is a fixed Ed25519 key, so signing is deterministic. The
statement is nonetheless an event record: `startedOn`, `finishedOn`, and
`invocationId` legitimately differ between two builds, exactly as the execution
trace does. The signature is taken over the exact emitted bytes at emission
time; the provenance is not re-derivable from inputs alone.

## Offline verification

A third party verifies the provenance with `cryptography` and the standard
library only:

1. Parse the DSSE envelope. Confirm `payloadType` is
   `application/vnd.in-toto+json`, base64-decode `payload`, and verify the
   Ed25519 signature over the DSSE pre-authentication encoding of the payload
   bytes under the pinned builder public key.
2. Parse the verified payload as the in-toto Statement. Confirm
   `predicateType` is `https://slsa.dev/provenance/v1`.
3. Re-derive the subject digests: sha256 the published wheel and sdist and
   compare against `subject[*].digest.sha256`.
4. When a Rekor sidecar is present, re-check that the anchored canonical bytes
   sha256 matches the sha256 of the locally re-canonicalized statement, then
   verify the Rekor inclusion the same way the dossier verifier does
   (`docs/REKOR_V2_MIGRATION.md`).

The builder public key is published as part of the release; pin it the way you
would pin any other long-lived signing key.

## Durable publication

<!-- __s160_u1_durable_provenance_v1__:doc -->
The v5.58.0 provenance, the sdist it names, and the builder public key are
mirrored to a fetchable, git-tracked, served location so a third party can
retrieve and pin them without trusting any single host's filesystem:

    https://nous-lang.org/.well-known/nous/provenance/

Files at that path:

- `nous_lang-5.58.0.provenance.intoto.json` (+ `.sha256`): the signed DSSE provenance envelope.
- `nous_lang-5.58.0.tar.gz` (+ `.sha256`): the sdist. This is NOT on PyPI for
  5.58.0, so the mirror is its authoritative durable home. The wheel is on
  PyPI with an identical sha256 and is not mirrored as a binary blob.
- `builder-key.json` (+ `.sha256`): the raw Ed25519 builder public key,
  keyid, and SLSA build level, so pinning is a single fetch.
- `index.json` (+ `.sha256`): a manifest of the above with each artifact's
  sha256, size, and source (`pypi` or `mirror`), plus the honest boundary.

Publication EVIDENCES availability and integrity; it proves nothing new.
The provenance remains an emitted-at event record at SLSA Build Level 1.
