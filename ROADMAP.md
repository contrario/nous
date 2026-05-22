<!-- __session89_roadmap_v1__ -->
# NOUS Roadmap

This is a direction document, not a commitment schedule. NOUS is built
and maintained by one person (see CONTRIBUTING.md for the development
model), so there are no dates, no SLAs, and no guaranteed ordering. Items
ship when they are correct and the release pipeline is green, not when a
calendar says so. The list is honest about what is done, what is in
progress, and what is deferred -- a stale roadmap that over-promises is
worse than a short one that does not.

Coordination is GitHub-native: open an issue or discussion at
https://github.com/contrario/nous. There is no other channel.

## Recently shipped

- **v5.9.0** -- Rekor v2 read-path verifier groundwork (entry,
  checkpoint, and v2 anchor verification primitives).
- **Differential test (runner vs codegen).** Asserts the live AST runner
  and the codegen path derive an identical semantic surface (souls,
  messages, models, senses, memory fields, law constants) from the same
  validated program. Closed a real defect it surfaced on first run: the
  runner had been ignoring declared per-cycle cost ceilings.
- **Deterministic website deploy.** The served site is now a reproducible
  deploy from the git-tracked `website/` tree via
  `scripts/deploy_website.sh`, replacing in-place editing.

## In progress / near term

- **Rekor v2 activation.** Wire the v2 read-path verifier into the live
  anchoring flow and the portable offline verifier, behind an explicit
  API-version discriminator. The transparency-log write path remains on
  v1 (maintenance mode) until a v2 log is published and pinned; the
  client fails closed on unsupported API versions rather than silently
  downgrading.
- **Annex IV evidence surface.** Continue hardening the dossier so a
  third party can verify offline, with only `cryptography` and
  `z3-solver`, that a cost-bound proof was formed at compile time and
  sealed then. Evidence supports a compliance duty; it does not by
  itself constitute compliance.

## Deferred (intended, not scheduled)

- **Trusted timestamp (RFC 3161 TSA)** for anchored dossiers, so
  formation time is attested by a third party rather than self-asserted.
- **Route-lowering test.** A forward check that codegen emits the channel
  set implied by a program's nervous-system routes (the one semantic
  surface element the differential test does not yet cover).
- **Systemd hardening tiers C and D** for the API service (tiers A and B
  are live).
- **Process-environment secret exposure.** An environment-variable secret
  cannot be scrubbed from `/proc/self/environ` mid-process; the fix is
  re-exec or file-based secret loading at startup.

## Explicitly out of scope

- A second compiler implementation (e.g. Rust/OCaml) for "formal
  semantics." The undefined-name gate, the byte-identity regression
  harness, and the differential test give practical correctness without a
  second language.
- Execution-time gateways or runtime-monitoring daemons. NOUS generates
  formation-time evidence (compile-time SMT proofs sealed into signed
  dossiers); it does not gate or intercept execution.
- Dropping the bilingual (Greek/English) identity. It is intentional and
  documented; the ASCII invariant already scopes cleanly to the repo root
  and `docs/`.

## How to help

For a single-maintainer project the useful contribution is legibility:
clear issues, reproducers, and small isolated improvements (a new
template, a docs fix). See CONTRIBUTING.md for the intake model -- issue
first, PR after the shape is agreed.
