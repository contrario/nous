# VSA Conformance Vectors

A published, implementation-independent demonstration that the NOUS VSA
evidence format can be verified offline by anyone, in any language, with only
the Python standard library and the `cryptography` package -- no NOUS install,
no SMT solver.

The vector is a frozen input bundle plus its expected verifier output. A third
party who has never run NOUS can fetch the bundle, run the self-contained
verifier, and confirm byte-for-byte that the canonical manifest body, the
Ed25519 signatures, and the cost- and coverage-Farkas verdicts are exactly what
NOUS produces.

Served at: `https://nous-lang.org/.well-known/nous/vsa-vectors/v1/`

## What is in the bundle

| file | what it is |
|------|------------|
| `vsa.intoto.json` | the DSSE-wrapped in-toto VSA (the summary attestation) |
| `manifest.json` | the signed static-proof manifest (input attestation) |
| `trace.json` | the signed execution trace (input attestation) |
| `conformance.json` | the signed conformance certificate (input attestation) |
| `coverage.farkas.json` | the coverage Farkas certificate (a PROVES leg) |
| `cost.farkas.json` | the cost-cap Farkas certificate (a PROVES leg) |
| `verify_vsa_offline.py` | the self-contained offline verifier (cryptography + stdlib) |
| `expected_stdout.txt` | the exact stdout the verifier prints on this bundle |
| `expected_exit.txt` | the exact exit code (`0`) |
| `index.json` | the artifact index, digests, and this boundary |

Each file has a `<name>.sha256` sidecar.

## How to reproduce (offline, third party)

Fetch the bundle into one directory and run the verifier:

    python3 verify_vsa_offline.py

Expect exit `0`, `VERDICT: PASS`, and stdout byte-identical to
`expected_stdout.txt`. The verifier needs `cryptography` and the standard
library only. It does not import NOUS and does not call a solver.

To regenerate the bundle from its source program (any NOUS version -- the
bundle is version-independent):

    python3 mint_vsa_vector.py vsa_conformance_vector_v1.nous <out_dir>

The mint harness pins every non-deterministic input (four fixed Ed25519 seeds,
fixed timestamps, the frozen source program) and runs the whole mint twice,
asserting the bundle bytes, the verifier stdout, and the exit code are
byte-identical across runs. The published digests are what any conforming
reproduction yields.

## The source program

`vsa_conformance_vector_v1.nous` is the frozen input the bundle is minted from.
It is owned by the vector alone -- no test or module references it -- so it
cannot move out from under a third party's reproduction. It is minimal and
drives two contradictions through the real NOUS producers:

- a cost-cap Farkas contradiction: the declared `cost_cap`, `tokens`, and
  `max_ticks` make the per-call token/tick cost system collapse under the cap.
- a coverage Farkas contradiction: a single `block`-action policy whose signal
  exactly covers the coverage threshold, so the coverage system has no gap.

Both certificates are producer-minted, never hand-written.

## The honest boundary

This is the load-bearing part. State it exactly.

PROVES (rational arithmetic, no solver, no NOUS install). The two Farkas
certificates re-prove offline, by exact rational arithmetic over `fractions`
in the standard library, that:

- no admissible execution exceeds the declared cost cap (cost-cap Farkas), and
- the declared policy coverage has no gap (coverage Farkas).

"Proves" is reserved for these Farkas legs. They are re-checkable with the
standard library and `cryptography` alone -- a z3 runtime is not required to
re-verify them. A verifier that cannot re-run the rational check still sees the
certificates as opaque digest pairs; the value is realized by re-running the
check, which any Python installation can do.

EVIDENCES (Ed25519 authenticity and sha-equality identity). The signatures on
the manifest, trace, certificate, and VSA evidence that the holder of each
fixed vector key signed those exact bytes, and that the input attestations name
those exact bytes. The name-to-key binding is operator-asserted; NOUS runs no
CA and certifies no identity.

FORMAT, not CONTENT. The vector demonstrates that the serialization, the
signature outcomes, and the Farkas verdicts are implementation-independent. It
says nothing about whether any obligation is substantively correct, whether the
governed action was appropriate, or whether the model behaved as intended. A
vector that claimed content-level correctness would overstate what the format
can carry.

Vector keys are fixed, PUBLISHED seeds, not operator keys. Their only purpose
is byte-for-byte reproducibility. They evidence nothing about any real
identity.

The evidence layer is a monitor, not a guard. Runtime policy enforcement is
separate: the runtime policy engine gates in record mode when a policy declares
a blocking action (ADR-0010).

## Scope of "implementation-independent"

The published Python verifier plus these frozen vectors demonstrate that the
format is verifiable with no hidden NOUS dependency and no solver. An
independent-language verifier (a second implementation in another language that
reproduces every vector) is a stronger form of the same claim; it is deferred
until an external party requests it, and is not part of this vector set.
