# Materiality Classification

Status: shipped (carriage + verification + producer), gated for release.
Honest boundary: a materiality verdict is a CLASSIFICATION, not a proof. The
verifier authenticates that a named key recorded a verdict and routes the
governance consequence; it never proves the change is a substantial
modification within the meaning of Article 25.

## 1. What it is

A NOUS build may supersede a prior build. The governance question is: does the
change require an envelope-binding re-proof, or only an Article 12 log entry?
Materiality classification answers that question with an evidenced verdict and
carries it inside the Annex IV dossier as a sha-pinned adjacent sidecar
(`materiality.json`), so an offline auditor re-derives the verdict's integrity
years later with cryptography and standard libraries alone.

The classifier compares two builds by behavioral diff and emits `minor` or
`material`:

  - `material` when any of: a soul is removed, a message is removed, a CRITICAL
    diff item is present, or the absolute total cost delta percent meets or
    exceeds the threshold (default 10.0).
  - `minor` otherwise.

The verdict document is canonical JSON (sorted keys, compact separators) with
fields `verdict`, `threshold_pct`, `cost_delta_pct`, `reasons`, `route`,
`basis`. The `basis` field always states the boundary:
`classification, not proof; not an Article 25 determination`.

## 2. The honest gradient

Materiality is the entrance to a three-level gradient. Each level is a stronger
claim than the one before, and only the third PROVES anything:

  1. minor -> behavioral-diff classification, EVIDENCED. Route: record an
     Article 12 log entry; no envelope-binding re-proof required by this
     classification.

  2. material -> the change is large enough that the governance route is to
     bind a fresh signed dossier proving the new build still satisfies the
     same proven properties. Route: `nous verify --smt --supersedes <prior
     manifest>`. The classification EVIDENCES the need; it proves nothing about
     preservation.

  3. material AND coverage-preserving -> the envelope-binding run carries a
     hop-containment Farkas certificate that PROVES the proven coverage region
     of the prior build is contained in the new build's region, offline, with
     no solver trust. This is the only level where "proves" applies.

The academic state of the art frames a breaking change via contracts: A -> A'
is breaking if the contract of A' does not imply the contract of A. The
literature proposes the contracts but admits routine verification of this
implication remains largely unfulfilled, and classification in practice is
human-designated and test-based. NOUS already carries the exact contract the
literature describes but does not check: the hop-containment Farkas certificate
is the proof that prior-region is contained in new-region, i.e. that the new
contract implies the old one, re-derivable offline. Materiality classification
is the surface that routes a change into that proof when -- and only when --
the change is material and the operator chooses to prove preservation.

## 3. Producer

The producer is opt-in. Without it, the verify path is byte-identical to prior
behavior (no manifest field, no sidecar), so the regression harness and dossier
goldens are unaffected.

    nous verify NEW.nous --smt --materiality-against PRIOR.nous \
        [--materiality-threshold-pct 10.0] --manifest-out NEW.manifest.json

When `--materiality-against` is given, cmd_verify:

  1. parses PRIOR and NEW sources, behaviorally diffs them, and classifies the
     result against the threshold;
  2. canonical-serializes the verdict, sha256-pins it into the signed manifest
     field `materiality_sha256` BEFORE signing;
  3. writes `materiality.json` next to the manifest.

`--materiality-against` is orthogonal to `--supersedes`. `--supersedes` binds
the proof leg (it verifies the predecessor signature and records
`prior_digest`); `--materiality-against` classifies the change. A material
verdict with no proof leg routes the operator to add `--supersedes`; a material
verdict with a proof leg present lets the verifier report that envelope
preservation was verified above in the same dossier.

`--materiality-against` is refused early when combined with `--gap-witness`: a
refutation artifact (a coverage-gap witness) carries no minor/material change
verdict, and the combination fails closed with zero writes.

## 4. Carriage and verification

`build_dossier` reads `materiality.json` next to the manifest, gates its sha256
against the signed `materiality_sha256` field (refusing to package on
mismatch), and carries it into the dossier directory. A `gap-witness`
(refutation) manifest that declares `materiality_sha256` is refused at package
time as incoherent.

When the packaged manifest declares `materiality_sha256`, the emitted
`verify_offline.py` is spliced with a `_check_materiality` step that runs LAST
in `main()`. It:

  - re-reads `materiality.json`, recomputes its sha256, and refuses on mismatch
    against the signed field;
  - schema-validates the verdict (verdict in {minor, material}, reasons is a
    list, basis states the boundary);
  - derives whether the envelope-binding proof leg is present from the SIGNED
    manifest (`prior_digest is not None`), not from any build-time flag;
  - prints the honest route.

Because the check runs last, in a chain verifier the chain walk has already
passed before the materiality route is printed; reaching the "verified above"
route is therefore sound by control flow, not by declaration. A builder cannot
bake a false proof-leg-present into a non-chain verifier, because the signed
manifest is what determines the route.

When the manifest declares no `materiality_sha256`, no check is spliced and the
verifier is byte-identical to the classification-free template.

## 5. Manifest field

`materiality_sha256: Optional[str]` is a drop-when-None canonical field
(present in the signed body only when set), mirroring the other sha-bearing
sidecar fields (`policy_coverage_sha256`, `coverage_smt2_sha256`,
`coverage_farkas_sha256`, `gap_witness_sha256`, `codegen_sha256`,
`cost_farkas_sha256`). Old manifests without the field remain byte-identical.

## 6. Boundary, restated

  - The verdict EVIDENCES the size and shape of a change and ADVISES a route.
  - The verifier EVIDENCES that the carried verdict is intact and signed; it
    does not prove the verdict is correct, complete, or an Article 25
    determination.
  - Only the hop-containment Farkas leg PROVES coverage-region preservation,
    and only when the operator runs the envelope-binding verify with chain
    coverage.

"proves" is reserved for the Farkas/Z3 result. Everything else here evidences.
