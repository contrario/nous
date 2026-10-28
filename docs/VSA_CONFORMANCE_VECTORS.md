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

Served at: `https://nous-lang.org/.well-known/nous/vsa-vectors/v2/` (the
current vector) and `https://nous-lang.org/.well-known/nous/vsa-vectors/v1/`
(frozen).

<!-- __nt_w_docs_v2_v1__ -->
## v2, and why v1 is frozen

v2's verifier re-derives the cost system before it grades the cost-cap
certificate. The conformance certificate carries the spec canon
(`obligations_canon`); its sha256 must equal the manifest's signed
`smt_spec_sha256`, its cap, ticks and margin must equal the manifest's, and
a cost certificate whose constraints differ from the system rebuilt from it
is refused before its multipliers are graded.

The VSA verifier checks that the certificate's recorded obligations
are consistent with its verdict; it does not recompute them from
`trace.json`. `verify_conformance_offline.py`, run on `manifest.json`,
`trace.json` and `conformance.json` of the v2 directory, recomputes the
cost obligations from the trace and the certificate's spec canon
(NT-GATE-1 V2).

v1 is frozen: its bytes are the ones published at c2d9680. Its verifier
grades the cost certificate it is handed without re-deriving it, so it
accepts a one-row certificate re-signed with the published vector keys
(measured 2026-10-27; v2's verifier refuses the same bundle). Use v2 for the
cost check.

## What is in the bundle

| file | what it is |
|------|------------|
| `vsa.intoto.json` | the DSSE-wrapped in-toto VSA (the summary attestation) |
| `manifest.json` | the signed static-proof manifest (input attestation) |
| `trace.json` | the signed execution trace (input attestation) |
| `conformance.json` | the signed conformance certificate (input attestation; in v2 it carries `obligations_canon`) |
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

To regenerate the bundle from its source program, the digests reproduce only
at the NOUS version, shipped price table and code generator it was minted with
(the signed spec canon and the program digest carry them, so the digests move
with any of the three), and only with the date pinned inside the price table's
90-day window. For v1 the measured terms are in `index.json` (`reproduce`):
a checkout of c2d9680 with `_version.py` at 5.73.0, and

    python3 pin_clock.py 2026-07-10 mint_vsa_vector.py \
        vsa_conformance_vector_v1.nous <out_dir>

The mint harness pins four fixed Ed25519 seeds, fixed timestamps and the
frozen source program, and runs the whole mint twice, asserting the bundle
bytes, the verifier stdout, and the exit code are byte-identical across runs.
v1's harness does not pin the date NOUS reads to decide whether a price is
too old for `--smt`; `pin_clock.py` does. v2's harness pins that date
(2026-10-27) itself and loads the shipped `pricing/defaults.toml` by path, so
neither the wall clock nor a price layer changes its bytes. Its terms are in
v2's `index.json`: in the v2 directory of the tree it was committed from, at
NOUS 7.0.0,

    python3 mint_vsa_vector.py vsa_conformance_vector_v2.nous <out_dir>

## The source program

`vsa_conformance_vector_v1.nous` and `vsa_conformance_vector_v2.nous` (the
same program, its header naming v2) are the frozen inputs the bundles are
minted from. Each is owned by its vector alone -- no test or module
references it -- so it cannot move out from under a third party's
reproduction. It is minimal and
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

- under the declared per-call token/tick estimates, no admissible execution
  exceeds the declared cost cap (cost-cap Farkas); runtime adherence to those
  estimates stays EVIDENCES via the signed trace, and
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
