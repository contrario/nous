# NOUS a50 Marking Two-Axis Map -- Design Doc (BUILD-ELIGIBLE-DEFERRED)

Status: BUILD-ELIGIBLE-DEFERRED. Gated behind the OJ flip and the 2 Dec 2026
Article 50(2) marking date. Not built. Origin: S246 Innovation Gate.
Register: this is a banked frontier, NOT a rejection. The rejected sibling (the
durability harness) is docs/REJECTED_IDEAS.md R3. Do not merge the two registers.

## 1. Forcing function

Article 50(2) marking obligations apply 2 Dec 2026 (absolute calendar date, not
publication-relative). At that point an auditor's live question is: which
content-marking scheme lets a third party verify provenance WITHOUT trusting the
issuer? The LinkedIn thread surfaced this by offering IMATAG as a durable
counterexample to NOUS positioning. The thread is the trigger that surfaced the
question; it is NOT itself the forcing function. Build only when the calendar date
approaches or the OJ flip makes the auditor-facing question live.

## 2. Claim class (minimal, time-bound)

"As of <LIVE-VERIFIED DATE>, no shipped, independently-measured image-marking
scheme occupies the quadrant {durable AND verifiable-without-the-issuer}."

The date is load-bearing: the claim is falsifiable by any future shipped scheme
that fills the quadrant under a public standardized re-encode measurement. It must
be re-verified live at build time, never asserted from this doc.

## 3. The two axes and their honest-boundary treatment

X axis -- durability (fragile ... durable): EMPIRICALLY MEASURABLE, but measured by
WAVES (arXiv 2401.08573), not by NOUS. The map CITES WAVES. It does not re-measure.
Re-measuring is R3 (rejected: duplication + patent-dense + maintenance).

Y axis -- independent verifiability without the issuer (issuer-gated ... publicly
verifiable): NOT A MEASUREMENT. It is a structural classification of the scheme's
trust model -- who must be trusted to obtain a verdict -- read from each scheme's
construction and published documentation. An imperceptible mark's presence is
decidable only by the detector-holder, so NOUS cannot and must not claim to have
MEASURED the verifiability of any imperceptible mark. It classifies the published
trust model. Any page copy implying the Y axis was measured is a honest-boundary
regression and a kill condition.

The ONE measured leg NOUS owns is the C2PA fragility point, and only via the
existing a50 byte-level strip (30/30 stripped). That is the sole reproduce block on
the page; it is not new work.

## 4. Quadrant placement

- Durable + publicly-verifiable (governance-relevant): EMPTY of shipped, measured
  schemes. Public-key watermark constructions aspire here -- Gunn-Zhao-Song PRC /
  Gaussian Shading (ICLR 2025), Fairoze 2025, Duan 2025, VOW (arXiv 2604.27666),
  PVMark (arXiv 2510.26274). Unshipped or unmeasured against standardized
  re-encode at scale.
- Durable + issuer-gated: IMATAG-class forensic watermarking. Durable per issuer
  copy; verification requires the issuer's stored key / API (403 without contract).
- Fragile + publicly-verifiable: C2PA manifests. Cryptographically signed,
  independently verifiable WHEN PRESENT, but strippable (a50, 30/30).
- Fragile + issuer-gated: degenerate, uninteresting.

Thesis: the quadrant real governance needs is empty of shipped, independently-
measured schemes as of the verified date.

## 5. Honest boundary (summary)

- No "proves" anywhere. The map evidences a taxonomy and cites measurements.
- X axis cited from WAVES, not re-measured.
- Y axis classified from construction/docs, not measured.
- Only C2PA fragility is a NOUS-owned measurement, reusing the a50 strip.
- a50-lane exposure artifact. Does not touch the release/claim surface. Ship test
  neutral (no NOUS claim changes).

## 6. Artifact shape

A single a50-style static page at nous-lang.org/a50/ (or a sibling slug). Content:
the four-quadrant map, each scheme placed with an inline trust-model note, the
existing C2PA strip reproduce block, and the citation set (Section 7). No harness,
no embed/detect code, no new dependency, no new trust root. Composes entirely from
the shipped a50 method.

## 7. Citations (verified current at S246)

- WAVES: arXiv 2401.08573 (ICML 2024). Durability benchmark, 26+ attacks.
- Strong-watermarking impossibility: arXiv 2311.04378 (incl. private-detection).
- Robust + publicly-detectable difficulty: arXiv 2502.04901.
- Coding-limit sharp threshold: arXiv 2509.10577.
- Public-verifiability constructions: Gunn-Zhao-Song PRC / Gaussian Shading
  (ICLR 2025), Fairoze 2025, Duan 2025, VOW arXiv 2604.27666, PVMark arXiv
  2510.26274.
- IMATAG issuer-gated trust model: IMATAG API documentation (stored key,
  detection via issuer API/crawlers, 403 without contract).
- DO NOT cite arXiv 2603.14968 as an image-domain impossibility result: it is a
  TEXT/LLM framework paper (TTP-Detect). Its coupling claim is real but its domain
  and genre are wrong for this page.

## 8. Kill criteria (testable)

- KILL the empty-quadrant claim if any shipped scheme demonstrates durable +
  verifiable-without-issuer under a public standardized re-encode measurement.
- KILL / pull if any copy states or implies the Y axis was measured.
- DOWNGRADE to citation-only reply if the sole forcing function at build time is
  the LinkedIn thread.
- DOWNGRADE if WAVES or a successor publishes the same two-axis map.

## 9. Revisit trigger

OJ publication OR approach of 2 Dec 2026 making the auditor-facing question live,
whichever first. Until then: banked. Do not build. Do not accumulate.
