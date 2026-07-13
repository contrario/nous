# Verifying a NOUS Release

The auditor's procedure. Every command below is what a third party actually
types: from a fresh empty directory, with only what can be downloaded from a
public URL, with no NOUS install, no producer knowledge, and no renaming.

Four artifact classes are published. Each is independently verifiable and each
carries its own boundary. Only one of them carries a PROVES leg (Section 3);
the others EVIDENCE.

Requirements: Python 3 and the `cryptography` package. Sections 1, 2, 3 and 4
need network access to fetch the artifacts; the verification itself is offline
once the bytes are on disk. No solver. No NOUS install.

    pip install 'cryptography>=42'

## The test this document is written against

    A fresh empty directory, the public URL, the published instructions, and
    nothing else -- then assert exit 0.

Every command in this document was run exactly that way, against the live
public site, before the document was written. A procedure that has only ever
been run by the producer, on the producer's machine, with the producer's
knowledge, is not a procedure a stranger can follow.

## 1. Release VSA (one bundle per release)

The release operator's signed endorsement that a published PyPI wheel and sdist
carry the federation attestations the project relies on: a SLSA build
provenance (keyless GitHub Actions, Fulcio/Rekor) and a PEP 740 PyPI publish
attestation, both naming those exact bytes.

Served at: `https://nous-lang.org/.well-known/nous/release-vsa/<version>/`

| file | what it is |
|------|------------|
| `index.json` | artifact index: names, digests, URLs, policy, boundary |
| `build-vsa.intoto.json` | the DSSE-wrapped in-toto VSA, under the name the verifier reads |
| `nous_lang-<version>.build-vsa.intoto.json` | the same VSA bytes, version-named |
| `verify_build_vsa_offline.py` | the self-contained offline verifier (cryptography + stdlib) |
| `release-verifier-key.json` | the pinned release-operator public key |
| `nous_lang-<version>.rekor-v2-bundle.json` | Rekor v2 inclusion proof, C2SP checkpoint, RFC 3161 timestamp |

Each file has a `<name>.sha256` sidecar.

### 1.1 Fetch the bundle and check the sidecars

    V=5.75.0
    B=https://nous-lang.org/.well-known/nous/release-vsa/$V
    mkdir rel && cd rel
    for f in index.json \
             build-vsa.intoto.json build-vsa.intoto.json.sha256 \
             verify_build_vsa_offline.py verify_build_vsa_offline.py.sha256; do
        curl -fsSLO "$B/$f"
    done
    sha256sum -c build-vsa.intoto.json.sha256 verify_build_vsa_offline.py.sha256

Expect `OK` for both, exit `0`.

### 1.2 Fetch the wheel, and bind it yourself

The VSA names the wheel and the sdist as its subjects. The verifier re-derives
every named subject that is present in the directory, and requires at least
one; it does not fetch. The bundle does not ship the wheel, by design -- you
should verify the bytes you will actually install, not a copy this project
mirrors for you.

`index.json` records the wheel's exact name and sha256. Its `url` field points
at the PyPI project page, not at a file, so fetch the file with pip:

    pip download nous-lang==$V --no-deps --only-binary :all: -d .

Bind what you fetched to what the index records. This step is yours, not ours:

    sha256sum nous_lang-$V-py3-none-any.whl
    python3 -c "import json;print([a['sha256'] for a in json.load(open('index.json'))['artifacts'] if a['kind']=='wheel'][0])"

The two digests must be equal. If they are not, stop: the bytes PyPI served you
are not the bytes this release VSA endorses.

### 1.3 Run the verifier bare

    python3 verify_build_vsa_offline.py

Expect exit `0` and `VERDICT: PASS`, reporting `1 of 2 named subject(s)
re-derived` (the sdist is the second subject; fetch it too with
`--no-binary :all:` if you want `2 of 2`).

| exit | meaning |
|------|---------|
| `0` | PASS: operator signature authentic, verifier identity and policy match the pinned ones, and at least one named subject re-derived from local bytes |
| `1` | FAIL: signature invalid, wrong verifier identity, wrong policy, a locally-present subject digest mismatched, or the recorded `verificationResult` is not `PASSED` |
| `2` | environment/incomplete: `cryptography` missing, no VSA present, or zero named subjects present to re-derive |

The verifier reads `build-vsa.intoto.json` by that exact name, from its own
directory or from a directory passed as `argv[1]`. The bundle ships that name.
Do not rename it.

### 1.4 Boundary

EVIDENCES (Ed25519 authenticity, sha-equality identity). The VSA is signed by
the pinned release-operator key, names the expected verifier identity and
policy, and the subject digests are the exact bytes you fetched.

NOT re-derived by this verifier (toolchain tier). The named SLSA build
provenance and PEP 740 publish attestation are recorded by URL and digest but
are not fetched or signature-checked: `cryptography` and the standard library
cannot reconstruct a keyless Fulcio/Rekor inclusion proof. For the
operator-independent root, verify them directly (Section 6).

PROVES nothing. No Z3 or Farkas leg is carried by this class.

## 2. SLSA provenance (build leg)

Served at: `https://nous-lang.org/.well-known/nous/provenance/`

This mirror carries a SINGLE published bundle (currently `5.58.0`), not one per
release. It is the durable, fetchable demonstration of the provenance format.
The per-release build leg is named in each release VSA's `index.json` under
`kind: "federation_build_leg"`, and is verified through Section 6, not here.

    mkdir prov && cd prov
    B=https://nous-lang.org/.well-known/nous/provenance
    for f in index.json builder-key.json verify_provenance_offline.py \
             nous_lang-5.58.0.provenance.intoto.json \
             nous_lang-5.58.0.tar.gz; do
        curl -fsSLO "$B/$f"
    done
    python3 verify_provenance_offline.py

Expect exit `0` and `VERDICT: PASS`. The bundle ships its own sdist, so one
subject re-derives with no further fetch; the wheel is reported as asserted,
not re-derived.

Boundary: honestly labeled SLSA Build Level 1 -- an ad-hoc operator-run release
script, not a hosted or isolated builder. EVIDENCES Ed25519 authenticity and
sha-equality identity of the confirmed subject. Out of scope, and not claimed:
builder integrity, hermeticity, build isolation, source-to-artifact
reproducibility. PROVES nothing.

## 3. VSA conformance vector (the class that carries a PROVES leg)

Served at: `https://nous-lang.org/.well-known/nous/vsa-vectors/v1/`

The full file table, the reproduction procedure, and the boundary are in
[VSA Conformance Vectors](VSA_CONFORMANCE_VECTORS.md). In short: fetch the
bundle into one directory and run

    python3 verify_vsa_offline.py

Expect exit `0`, `VERDICT: PASS`, and stdout byte-identical to the published
`expected_stdout.txt` (`diff` them; the published `expected_exit.txt` is `0`).

This is the only published class whose verifier re-proves anything: the cost-cap
and coverage Farkas certificates are re-checked offline by exact rational
arithmetic over the standard library's `fractions`, with no solver and no NOUS
install. "Proves" is reserved for those legs and for nothing else in this
document.

## 4. Verifier-digest registry

The signed, Rekor-v2-anchored allowlist of official `verify_offline.py`
template digests.

    curl -fsSLO https://nous-lang.org/.well-known/nous/verifier-registry.json
    curl -fsSLO https://nous-lang.org/.well-known/nous/verifier-registry.json.sha256
    sha256sum -c verifier-registry.json.sha256

Expect `verifier-registry.json: OK`, exit `0`.

That is a transport check and nothing more. It EVIDENCES that the file you
downloaded is the file the sidecar names. It says NOTHING about whether those
are the right bytes: a sidecar regenerated over tampered content is still
consistent with it. The content is bound to the operator by the registry's own
Ed25519 signature and its Rekor v2 anchor -- never by a sidecar. See
[Verifier-Digest Registry](VERIFIER_DIGEST_REGISTRY.md) for the signature and
anchor verification path.

## 5. The operator's own cold audit

`scripts/cold_audit.py` runs the whole of Sections 1 through 4 exactly as
written, from a fresh temporary directory, against the public URLs:

    python3 scripts/cold_audit.py 5.75.0

It is a POST-PUBLISH command, and it is deliberately NOT a release phase: at
release time the release VSA is not yet minted and the wheel is not yet on
PyPI, so a release-time check could only pass by constructing its own input --
which is the exact defect this tool exists to catch. If the script and this
document ever disagree, the document is wrong and the script is right about
nothing, because a stranger has only the document.

## 6. What a green result does not mean

The name-to-key binding is OPERATOR-ASSERTED. NOUS runs no CA and certifies no
identity. A signature EVIDENCES that the holder of a key signed those exact
bytes; establishing whose key it is is your out-of-band step, not something any
verifier here performs.

A sidecar is not integrity. `sha256sum -c` agreeing EVIDENCES that a file
matches the digest published beside it. Content is bound to an identity by the
Ed25519 signature and the transparency-log anchor.

The release VSA is an operator root ALONGSIDE the federation roots, not a
second build. For the operator-independent root, verify the federation
attestations yourself, with their own tooling:

    gh attestation verify nous_lang-<version>-py3-none-any.whl -R contrario/nous
    pypi-attestations verify pypi \
        --repository https://github.com/contrario/nous \
        pypi:nous_lang-<version>-py3-none-any.whl

Nothing here attests that any run executed, that any governed action was
appropriate, or that any model behaved as intended.

NOUS is a monitor, not a guard.
