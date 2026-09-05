# Predetermined-Change Envelope (PCE)

The predetermined-change envelope (PCE) is one signed artifact that lets an
auditor check, offline, two facts about a build of a high-risk AI system:

1. MEMBERSHIP. Whether the composed change from a committed baseline to the
   current build lies inside a declared envelope of permitted changes.
2. PRE-COMMITMENT-IN-TIME. Whether that envelope was timestamped before the
   build it governs.

Both are evidence legs of the SAME artifact. Neither adjudicates anything. Both
are read by an offline verifier that uses only `cryptography` and the Python
standard library. No solver is required for either leg, and no NOUS install,
and zero issuer trust.

This document mirrors the shipped verifier bytes (the two embedded checks in
`dossier.py`: `_check_pce` and `_check_pce_anchor`, with the ported RFC 3161
verifier `_pa_verify_rfc3161`). Where this prose and the code differ, the code
wins.


## 1. What the PCE is

A predetermined-change envelope is the machine-checkable rendering of the
technical-documentation slot for predetermined changes. It is one declared
document (`pce.json`) plus the per-build evidence that an auditor verifies
against it. The envelope declares, up front, which obligation changes a
continually-updated system is permitted to make without being treated as a new
thing; each build then carries evidence of where it sits relative to that
declaration.

The envelope is NOT a determination. It declares its own non-determinative
status: the verifier refuses to anchor or to decide membership over a `pce.json`
whose `basis` does not contain the literal string
`not a legal substantiality determination`. Whether the envelope was well drawn,
and whether any detected exit is a substantial modification, is the notified
body's call, never NOUS's.


## 2. The two legs, and why both exist

A single envelope is not enough on its own. An operator who can author the
envelope after seeing the change can always draw it to contain whatever it must.
The two legs close two different gaps.

MEMBERSHIP (leg 1, `_check_pce`) answers: is the composed baseline -> current
obligation delta inside the declared envelope? The decision is decidable set
arithmetic over the SA / GA / GQ governance-obligation subset of the signed
SMT-spec canon:

  - SA: an obligation set, with a `mutable` flag. A removal or addition of an SA
    obligation is a breakout when the cumulative envelope declares SA immutable.
  - GA: the gated-action set. A removal is a breakout unless the action is in the
    cumulative `total_removable` allowlist; an addition is a breakout when a
    `total_addable` allowlist is declared and the action is not in it.
  - GQ: per-gated-action quorum thresholds. A quorum reduction that drops an
    oversight gate, or a drift larger than the per-action `quorum_drift_budget`,
    or any drift on an action with no declared budget, is a breakout.

The membership leg reads ONLY the obligation subset of the spec canon. The
sha-gate authenticates the whole spec preimage; the decision does not claim the
spec equals the obligation set. The membership leg makes NO ordering claim and
does not read the envelope's transparency-log or RFC 3161 anchor.

PRE-COMMITMENT-IN-TIME (leg 2, `_check_pce_anchor`) answers: was the envelope
timestamped before the build it governs? This is the "dated" leg. It recovers
two trusted times from pinned roots:

  - T_env: the RFC 3161 genTime over the exact envelope bytes, from the
    `pce.anchor.json` receipt, verified against the pinned TSA root.
  - T_change: the RFC 3161 genTime over this build's Rekor v2 leaf signature,
    recovered from the signed manifest `transparency_log`, when present.

The relation between T_env and T_change is computed by the verifier at audit
time. It is never asserted by the receipt itself: the receipt carries no
ordering claim by construction (it binds the envelope bytes and a timestamp over
those bytes, nothing relative to any later change).

Together the legs are: the change is inside the declared envelope (membership),
AND the envelope was committed in time before the change (pre-commitment). That
pairing is the "dated and signed ... with regard to predetermined changes"
evidence that the Annex IV technical file asks for.


## 3. Schemas (verbatim)

### 3.1 `pce.json` (the envelope; operator-authored)

Required for either leg to run:

  - `pce_schema_version`: integer, must be `1`.
  - `basis`: string, must contain `not a legal substantiality determination`.
  - `baseline_canon_sha256`: 64-hex sha256 of the committed baseline obligations
    canon (`baseline.canon`).
  - `per_step`: object with `SA.mutable` (bool).
  - `cumulative`: optional object. When present:
    - `SA.mutable`: bool (defaults to the per_step value).
    - `GA.total_removable`: list of strings or null.
    - `GA.total_addable`: list of strings or null.
    - `GQ.quorum_drift_budget`: object mapping action -> non-negative integer.

When `cumulative` is absent the membership verdict is `NO_CUMULATIVE` (the
cumulative anti-salami determination is simply not available; no violation is
asserted and none is claimed).

### 3.2 `pce.anchor.json` (the pre-commitment receipt; ceremony output)

Exactly five fields, assembled pure (no network) by `build_pce_anchor_receipt`:

  - `pce_anchor_schema_version`: integer, `1`.
  - `anchored_pce_sha256`: hex sha256 of the anchored envelope bytes.
  - `basis`: the fixed receipt disclaimer (evidences pre-commitment-in-time;
    not a legal substantiality determination; asserts no ordering).
  - `rekor_v2`: the Rekor v2 transparency-log inclusion block
    (`rekor_api_version` == 2).
  - `pce_rfc3161_token_b64`: base64 of the RFC 3161 token over the envelope
    bytes (the T_env source).

### 3.3 Manifest binding

The signed manifest carries two sha-pinned references; both are drop-when-None,
so a dossier that uses neither leg stays byte-identical to a pre-PCE manifest:

  - `pce_sha256`: sha256 of `pce.json` (membership leg).
  - `pce_anchor_sha256`: sha256 of `pce.anchor.json` (temporal leg).

The membership leg also depends on the existing signed `smt_spec_sha256`
(authenticating `spec.canon`, the current obligations canon) and on the
envelope's own `baseline_canon_sha256` (authenticating `baseline.canon`). No new
manifest field is added for the baseline; the PCE is itself sha-gated by the
signed manifest, and the baseline is sha-gated transitively by the PCE.


## 4. The verdict objects (exactly as emitted)

The verifier prints one machine-readable line per leg. These are the only
verdict objects; no other states exist.

### 4.1 Membership: `PCE_VERDICT_JSON`

```
{
  "kind": "pce-cumulative-membership-v1",
  "verdict": "WITHIN" | "OUTSIDE" | "NO_CUMULATIVE",
  "breakouts": [ ... ],
  "composed_weakened": [ ... ],
  "composed_strengthened": [ ... ],
  "scope": "sa-ga-gq-obligation-subset-of-signed-smt-spec-canon",
  "temporal_precedence": "membership-only-no-temporal-claim",
  "basis_disclaimed": true
}
```

| `verdict`      | Meaning                                                        | rc |
|----------------|---------------------------------------------------------------|----|
| WITHIN         | composed delta lies inside the cumulative envelope            | 0  |
| OUTSIDE        | composed delta exits the envelope on the listed breakouts     | 0  |
| NO_CUMULATIVE  | the PCE declares per_step only; no cumulative decision made   | 0  |

`temporal_precedence` here is the FIXED string
`membership-only-no-temporal-claim`. It is NOT an ordering value. It is a
disclaimer: the membership leg asserts only that the declared envelope admits
this composed delta, NOT that the envelope was committed before the change.
Ordering is the temporal leg's job, never this one's.

### 4.2 Pre-commitment: `PCE_ANCHOR_VERDICT_JSON`

```
{
  "kind": "pce-anchor-temporal-v1",
  "temporal_precedence": "anchored-absolute" | "anchored" | "post-hoc",
  "t_env_utc": "<ISO 8601>",
  "t_change_utc": "<ISO 8601>" | null,
  "basis": "RFC 3161 genTime ordering against a pinned TSA root; not a legal substantiality or precedence determination"
}
```

| `temporal_precedence` | Condition                  | Line  | rc |
|-----------------------|----------------------------|-------|----|
| anchored-absolute     | `t_change` is null         | OK    | 0  |
| anchored              | `t_env < t_change`         | OK    | 0  |
| post-hoc              | `t_env >= t_change`        | INFO  | 0  |

  - anchored-absolute: the dossier carries no in-band change-time (no manifest
    `transparency_log` RFC 3161 token). T_env is asserted absolutely, not
    relative to this build's change-time.
  - anchored: the envelope was timestamped by the pinned TSA strictly before
    this build's own trusted timestamp. The membership claim is not post-hoc.
  - post-hoc: the envelope's timestamp is not strictly before the build's
    change-time. The membership claim may be retrofitted. This is a TRUTHFUL
    detected ordering printed as INFO, not a process failure.

ABSENT case (no fourth value). When the manifest declares no `pce_anchor_sha256`
and no `pce.anchor.json` sidecar is present, the temporal leg returns rc 0 and
emits NO verdict object at all. There is no `silent` precedence value; the
absence of the leg is exactly that, an absence, not a state.


## 5. Monitor, not gate

Both legs are monitors. Every membership verdict (WITHIN, OUTSIDE,
NO_CUMULATIVE) and every ordering verdict (anchored-absolute, anchored,
post-hoc) returns rc 0. The verdict never fails the verifying process. OUTSIDE
and post-hoc are truthful detected events, printed (INFO / OUTSIDE breakouts),
not raised.

Only an INTEGRITY failure fails closed (rc 1):

  - a declared sidecar is missing, or a sidecar is present that the manifest does
    not declare (unexpected evidence);
  - a sha gate fails (`pce.json`, `pce.anchor.json`, `spec.canon`, or
    `baseline.canon` does not match its committed sha);
  - the receipt's `anchored_pce_sha256` does not equal `sha256(pce.json)`, or
    that does not equal the signed manifest `pce_sha256` (the receipt anchors
    different bytes than the carried envelope);
  - the RFC 3161 token does not verify over the envelope bytes against the pinned
    TSA root, or the change-time token does not verify over the Rekor v2 leaf
    signature;
  - the envelope is malformed (unparseable, wrong schema version, missing or
    non-disclaiming `basis`, bad baseline sha).

An operator who wants CI enforcement keys on the emitted `verdict` /
`temporal_precedence` line, never on the exit status, which stays rc 0 across all
verdicts so the auditor verifier behaves identically whatever the verdict says.


## 6. The honest boundary

  - The membership leg EVIDENCES over decidable set operations. It never proves.
    `proves` remains reserved for the Z3 cost bound and Farkas certificates on
    other legs of the dossier.
  - The anchor leg EVIDENCES pre-commitment-in-time. It does NOT evidence the
    envelope's adequacy or coverage. A well-formed, pre-committed envelope can
    still be a bad envelope; that is the notified body's determination.
  - The membership verdict and the ordering verdict do NOT adjudicate Article
    43(4). NOUS surfaces the change and the timing; the substantiality
    determination is deferred to the notified body in every path.
  - The name-to-key binding is operator-asserted. NOUS runs no CA and certifies
    no human identity. A signature evidences that the holder of a key signed; the
    identity check is the auditor's out-of-band step.


## 7. CLI and offline verification

Ceremony (assessment-time, standalone, LIVE network):

```
nous pce-anchor pce.json [--out pce.anchor.json]
```

Pre-commit a predetermined-change envelope in time: a Rekor v2 entry and an
RFC 3161 timestamp, both over the exact envelope bytes. Writes the five-field
receipt. This is upstream of and independent from any build; it evidences
pre-commitment-in-time, not envelope adequacy, not ordering, not a legal
determination.

Binding (emit-time, on the dossier emit path):

```
nous ... --pce <pce.json> --pce-anchor <pce.anchor.json>
```

Binds the receipt into the signed manifest as `pce_anchor_sha256` and carries it
as a dossier sidecar. The receipt `anchored_pce_sha256` must equal the bound
envelope sha256. Requires `--pce`. Omitted: the manifest is byte-identical to one
emitted without it.

Verification. The two legs run inside the dossier's carried offline verifier
(`verify_offline.py`) alongside the existing checks. They require `cryptography`
(for the Ed25519 manifest signature and the RFC 3161 signer-chain check) and the
standard library (sha gates, JSON, set arithmetic, the ported DER / RFC 3161
parser). The RFC 3161 verification chains the TSA signer to a pinned self-signed
root carried in the verifier; the Rekor v2 leaf is recovered from the signed
manifest. No solver, no network, no NOUS install, zero issuer trust.


## 8. Regulatory framing

VERIFICATION NOTE: the Article 43(4) / Annex IV point 2(f) and 2(g) claims in
this section were verified verbatim against the primary regulation
(Regulation (EU) 2024/1689) on 2026-06-30. The Article 14 co-author sign-off
gate does not apply to this 43(4) / Annex IV surface; the factual risk on these
claims is closed by primary-source verification, not by review.

The EU AI Act provides the legal hook for predetermined change but, in practice,
no tooling. NOUS supplies the deterministic-evidence implementation. The novelty
claimed here is the tooling -- a signed, offline-verifiable, machine-checkable
artifact -- not the regulatory comparison below, which is widely published.

The hook (EU AI Act, Regulation (EU) 2024/1689):

  - Article 43(4): a high-risk system that has passed conformity assessment must
    undergo a new assessment on a substantial modification. The carve-out is
    conditional: for high-risk systems that CONTINUE TO LEARN after being placed
    on the market or put into service, changes to the system and its performance
    predetermined by the provider at the moment of the initial conformity
    assessment, and part of the information in the technical documentation under
    Annex IV point 2(f), do not constitute a substantial modification. The
    continue-to-learn precondition is exactly the case the envelope governs. This
    is the hook for the WITHIN verdict.
  - Annex IV point 2(f): the technical-documentation slot for the predetermined
    changes and their assessment methodology. The envelope is the 2(f) artifact,
    rendered machine-checkable.
  - Annex IV point 2(g): requires test logs and reports dated and signed by the
    responsible persons, including with regard to the predetermined changes under
    point 2(f). NOUS produces exactly this: DATED (RFC 3161 genTime plus Rekor v2
    inclusion), SIGNED (Ed25519 manifest plus co-signed attribution), WITH REGARD
    TO PREDETERMINED CHANGES (the envelope membership verdict). The temporal leg
    is the "dated" in "dated and signed."
  - Article 3(23): the substantial-modification definition (a change not foreseen
    at assessment that affects compliance or the intended purpose).
  - Article 18 and the living-document duty: the technical file stays current and
    is retained ten years; every substantial modification is logged. The
    append-only signed change chain with per-build membership is that
    version-controlled, signed substantial-modification log.
  - Article 25: a substantial modification can reclassify a deployer as a
    provider with full obligations, which raises the stakes of getting the
    within / outside call right.

The mature precedent (US FDA Predetermined Change Control Plan):

  - Legal basis: Section 515C of the FD&C Act, added by FDORA (December 2022).
    Final AI guidance issued August 2025.
  - Three mandatory components map onto NOUS:
    - Description of Modifications -> the envelope (the declared change set).
    - Modification Protocol -> the operator's methodology (out of NOUS scope).
    - Impact Assessment, individual AND cumulative -> the per-step and cumulative
      membership deciders. The FDA requirement to assess the cumulative impact of
      all modifications is the precedent for the cumulative anti-salami decider.
  - "Stays within the bounds" means the system implements only modifications the
    plan contemplates; changes outside scope still require a new submission. This
    is the within (no new assessment) / outside (notified body adjudicates)
    distinction exactly.
  - Adoption: 26 authorized PCCPs as of December 2025, all Class II.

The gap, stated honestly:

  - The EU framework does not define upfront which algorithmic changes can be
    handled without a full re-review, and has no pre-planned change-control
    equivalent to a PCCP.
  - As of 2026 no harmonised AI Act standards are published in the Official
    Journal; there is no presumption of conformity, and engineers work directly
    from the Annex IV text.
  - Article 43 (the conformity-assessment provision itself) applies from 2 August
    2026 per Article 113. This is distinct from the dates on which the high-risk
    SYSTEM obligations bind. The Digital Omnibus on AI was published on 24 July
    2026 as Regulation (EU) 2026/1744 (OJ L, 2026/1744, 24.7.2026; CELEX
    32026R1744) and entered into force on 27 July 2026, the third day following
    publication. Its Article 1(40) amends the third paragraph of Article 113:
    the high-risk obligations of Chapter III Sections 1, 2 and 3 (Article 6(5)
    excepted) then apply FROM 2 December 2027 for Annex III systems and FROM
    2 August 2028 for Annex I systems. Those dates are fixed in the enacted
    text; they are not conditional on a Commission availability decision.
  - NOUS fills a de facto tooling vacuum, not a statutory condition: the
    regulation does not reference a tool it waits on. The vacuum is that no team
    can produce the dated-and-signed predetermined-change evidence Annex IV 2(g)
    asks for today; NOUS does.


## References

  - `docs/ANNEX_IV_MAPPING.md` -- per-section Annex IV crosswalk.
  - `docs/EU_AI_ACT_COMPLIANCE.md` -- article-level compliance matrix.
  - `docs/GATED_ACTIONS.md` -- the GA / GQ gated-action and quorum obligations.
  - `docs/REKOR_V2_MIGRATION.md` -- the Rekor v2 anchor path.
  - `docs/MATERIALITY_CLASSIFICATION.md` -- the minor / material change verdict
    that routes a material change toward the envelope-binding leg.
  - `docs/ENVELOPE_LEDGER.md` -- the append-only envelope ledger and its permanent
    witness origin (non-equivocation of the committed history).
