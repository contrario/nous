# ADR-0010: The evidence layer is a monitor; the runtime policy engine gates

Status: Accepted

Supersedes ADR-0005.

## Context

ADR-0005 states, without qualification, that NOUS is a monitor and not a guard,
that policies enforce nothing at runtime, and that only integrity tamper fails
closed. Half of that is correct and load-bearing. The other half has never been
true of the shipped code.

Measured at commit 0c05a1076e8fe455c1afc49c326f7abd2acc3bae:

    intervention.py:19        intervene   -> audit event, pass (a hook)
    intervention.py:20/225    block       -> audit event, raise InterventionBlocked
    intervention.py:21/227    abort_cycle -> audit event, raise InterventionAborted
    intervention.py:119-120   enabled == (self._engine is not None), which is
                              true whenever declared rules exist
    replay_runtime.py:114-131 _intervention_check, whose docstring states that
                              it re-raises "so the caller never proceeds to the
                              real side-effect"
    replay_runtime.py:134-135 the two preconditions: engine present and enabled,
                              and mode == "record"
    replay_runtime.py:168-170 except InterventionError: emit the audit event,
                              then re-raise
    replay_runtime.py:304     the check runs before self._store.append()
                              for sense.invoke
    replay_runtime.py:395     before the model call for llm.request
    replay_runtime.py:490     before self._store.append() for memory.write
    codegen.py:1331/1333      _INTERVENTION_ENGINE is constructed whenever
                              policies exist, on both branches, with no
                              integrator step
    nous_api_server.py:1594-1614  marker __api_intervention_hook_v1__: the API
                              converts InterventionBlocked / InterventionAborted
                              into a structured error carrying the dedicated
                              codes CHAT_INTERVENTION_BLOCKED and
                              CHAT_INTERVENTION_ABORTED, the triggering policy
                              names, the score and the reasons

Under two conditions -- declared policies carrying rules, and record mode -- a
declared blocking action stops the action before its side effect. That is
enforcement. It is wired by codegen with no operator step, and it has a named
production surface in the API.

### The history, and why it decides which document is wrong

Measured from the public repository history, 771 commits, author dates:

    2026-04-17  f1d958d  intervention.py added, already raising
                         InterventionBlocked and InterventionAborted. The same
                         commit adds the runtime hook in replay_runtime.py, the
                         codegen wiring, and tests/test_intervention.py.
    2026-04-17  2bee5bc  the third call site, with the subject line
                         "memory.write intervention hook -- 3-site symmetry
                         complete"
    2026-06-17  44893f3  the first appearance of the phrase "monitor, not a
                         guard" anywhere in the repository, in a commit whose
                         subject pairs "conformant gated-run teeth" with
                         "authorization-runtime honest boundary"
    2026-07-03  b8659fd  ADR-0005 created, one of eight seed ADRs written in a
                         single commit. Never amended.
    2026-07-10  8cfcd94  README.md acquires the claim, seven days after the ADR

intervention.py has two commits in the entire history, both on 17 April 2026,
and has not been modified since. The runtime therefore predates ADR-0005 by 77
days, and the gating was a stated design goal rather than an accretion: three
call sites, described by their author as a completed symmetry, wired
automatically, tested in the same commit.

ADR-0005 was not a decision that later drifted. It was a reconstruction written
77 days afterwards that described the system incorrectly on the day it was
written, and its front-page propagation into README.md followed it a week later.
ADR-0005 says so about itself, in its own Context: "The original session-time
rationale is not fully recoverable from the available record... the supporting
reasoning is reconstructed inference, labeled as such." The measurement above
explains why it was not recoverable.

This ADR does not treat that as a failure of the ADR discipline as written. The
discipline explicitly permits honest reconstruction. What it lacks is a step
requiring a reconstructed decision to be checked against the code it claims to
describe. That gap is recorded here and is not otherwise addressed by this ADR.

### What ADR-0005 got right

The evidence layer. nous verify, conformance, dossier, PCE, VSA and the trace
bundle return rc 0 on a verdict, WITHIN and OUTSIDE alike, and return non-zero
only on integrity failure. The embedded verifiers in dossier.py and tb_check.py
state this per function and remain accurate as written, for example _check_pce:
"MONITOR, NOT GATE: returns 0 on WITHIN and on OUTSIDE; non-zero ONLY on
integrity failure". No change to those strings is required by this ADR.

## Decision

The claim is split along the boundary that the code has always had.

1. THE EVIDENCE LAYER IS A MONITOR. Verification, conformance, dossier
   emission, PCE, VSA and trace-bundle checking return rc 0 on a verdict,
   WITHIN and OUTSIDE alike. A verdict is an observation, not a gate. Only
   integrity failure returns non-zero. This is unchanged, and is the invariant
   ADR-0005 was written to protect.

2. THE RUNTIME POLICY ENGINE GATES, under stated conditions. When policies
   carrying rules are declared and the runtime is in record mode, a policy whose
   action is block or abort_cycle raises before the guarded side effect, so the
   action does not occur. The audit event is emitted first, then the exception
   is re-raised. The conditions are load-bearing and are not decoration: in
   replay and off modes _intervention_check returns immediately and nothing is
   gated.

3. THE OTHER ACTIONS DO NOT GATE. log_only, intervene and inject_message emit
   their audit event and pass. In particular, intervene halts nothing; it is a
   hook. Any surface stating otherwise is wrong and is corrected separately.

Neither leg uses the word "proves". Per ADR-0004 that word is reserved for
Z3/Farkas results, and nothing here is one.

ADR-0005 is superseded, not corrected in place. Its record stands.

## Alternatives rejected

- REMOVE THE GATING AND KEEP THE CLAIM. Make block and abort_cycle
  record-and-continue, so ADR-0005 becomes true as written and no document
  changes. Rejected: it deletes deliberately designed, tested and shipped
  behaviour -- three call sites named by their author as a completed symmetry,
  auto-wired by codegen, with a named production surface in the API -- in order
  to conform to a document that was inaccurate on the day it was written and
  has never been reviewed. It would also remove enforcement silently from every
  existing declaration: the audit event still fires, so a trace of a
  recorded-and-continued action is not distinguishable from a trace of a gated
  one by anything present in it. Five .nous files declare action: block,
  including the published conformance vector at
  website/.well-known/nous/vsa-vectors/v1/vsa_conformance_vector_v1.nous, whose
  meaning would change while its bytes stayed identical.

- MAKE GATING OPT-IN AND DEFAULT-OFF. Rejected: it makes the truth of the
  claim depend on deployment, so no single sentence describes the system to a
  reader and every statement acquires a "in which configuration". It also
  carries the same silent-removal risk as the route above at the moment the
  default flips, and it does not settle whether the governance-layer manifest
  may keep asserting that the layer does not enforce, since the capability
  would still ship.

- LEAVE BOTH AND SAY NOTHING. Rejected. The divergence was found by an internal
  mapping pass in S263; the project's standing position is that an overclaim
  found by an external reviewer before an internal gate is a gap, and the same
  applies to one found late by an internal gate.

## Tradeoffs and consequences

- The one-line thesis ends. "NOUS is a monitor, not a guard" is no longer a
  true sentence about the system as a whole, and every future document must
  carry the split or reintroduce the defect. This is a permanent cost.

- THIS ADR DOES NOT ANSWER ADR-0005's REJECTED-ALTERNATIVE ARGUMENT. That
  argument -- a guard must sit in the execution path and be trusted to be
  correct and available, which makes NOUS a single point of failure and a
  control system carrying heavier assurance obligations -- is itself labelled
  reconstructed in ADR-0005, with no known author and no date. Its provenance
  does not reduce its force. What is measured here bounds it rather than
  answering it: the gate exists only in record mode with declared rules, so
  replay and off carry no liveness dependency, and record mode is the
  production path. Whether the enforcement posture changes NOUS's own
  regulatory characterisation has not been assessed and is not claimed either
  way.

- Downstream corrections follow from this record and are not part of it: the
  prose and served surfaces that assert the unscoped claim, and the
  governance-layer manifest, whose operational_scope.does_not item 6 currently
  reads "Enforce, authorize, halt, or intervene in execution". The manifest is
  signed, published and anchored, so its correction is a new manifest version
  with a supersedes chain and is deliberately the last step.

- docs/EU_AI_ACT_COMPLIANCE.md:189 states that the intervene action halts
  execution and surfaces the decision to a human operator, under a status of
  COVERED for Article 14. intervention.py:19 makes intervene a pass-through
  hook. That is the same subsystem misdescribed in the opposite direction, it
  is false under this ADR as it was under ADR-0005, and it is a separate
  decision that this ADR does not resolve.

- No code changes. No runtime behaviour changes. No verifier bytes change. The
  test floor does not move on account of this ADR.

## Evidence ledger (append-only)

- S265: the code positions above measured against the tree at commit
  0c05a107, read from the pinned public tarball at that commit. RULE 0 on the
  same day: HEAD == origin/main == 0c05a107, working tree clean, suite 2793
  passed and 12 skipped against a floor of 2722, served mirror CLEAN at 331 of
  331 tracked files with 5 additive orphans.
- S265: the history above measured from a blobless clone of the public
  repository, 771 commits, using author dates.
- S265: the S263 mapping ledger recorded two intervention call sites; three
  were measured, and commit 2bee5bc names the third as completing the
  intended symmetry.
- S265: the embedded verifier strings in dossier.py and tb_check.py were read
  in full and found to be scoped per function and accurate, so they are not in
  the correction set.

## Still true?

YES (S265, first entry).
