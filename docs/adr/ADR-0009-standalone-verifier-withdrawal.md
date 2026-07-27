# ADR-0009: The standalone verify_offline.py download is withdrawn

Status: Accepted

## Context

nous-lang.org served a standalone verifier at `/verify_offline.py`, linked from
verify.html and from two dated blog posts. It was never tracked in the repo. It
was an untracked served orphan, reported as one by
`scripts/served_mirror_check.py` and exempted by name in the header comment of
`scripts/deploy_website.sh`.

Measured in S264 against live bytes on Server A and against the repo at commit
4e02744:

    served /var/www/nous-lang.org/verify_offline.py
      12377 bytes
      sha256 a73a8388c1f3f0ebcbd745104e75a50c204bba6a7b4d27705fc3584c445e1b16
      mtime 17 May 2026
      docstring: "Offline verification of NOUS dossier (Annex IV), hybrid mode"
      5 occurrences of allow-unanchored; default refuse-on-missing

    offline_verifier_builder.build_offline_verifier_v2(), built in S264
      44880 bytes
      sha256 18760fff8476992fd4736303eeb5caa72a1a370b2e5897880720a48569d0359d
      also carries --allow-unanchored

The capability is NOT discontinued. `build_offline_verifier_v2` is load-bearing:
`dossier.py:1586` and `dossier_spec.py:392` call it in the rekor_v2 emission
path with `KNOWN_REKOR_V2_LOG_KEYS` pinned. What diverged is the served artifact
and the anchor generation it targets. The served file's docstring describes the
Rekor v1 read path (a hashedrekord leaf plus a signedEntryTimestamp); the
current builder declares a Rekor v2 tile-backed log. Nothing versions the served
download, nothing rebuilds it, and no test reaches it: `scripts/release.py`
gates the wheel and phase_registry_coverage covers packaged templates, but
neither extends to an untracked file under `/var/www`.

This is a release and packaging defect, not a capability defect.

An earlier reading (S263) recorded the served file as the only artifact
implementing a discontinued capability. That reading was measured over the seven
`VERIFY_OFFLINE_PY*` string constants in `dossier.py`, all of which report zero
unanchored lines, and did not extend to the v2 builder. It is corrected here.

## Decision

The generic standalone download is withdrawn. Offline verification is
dossier-embedded: `dossier.py:1561-1593` selects a verifier template per dossier
content at emission time (chain+bundle, chain, bundle, farkas, coverage, rekor,
plain), so each dossier carries the verifier matching its own evidence. There is
no generic standalone verifier.

The revisit trigger, in the operator's words: if a real requirement for one
appears, it returns as a conscious design decision, not as the legacy of an old
artifact.

The 12377 bytes were archived to an operator-held copy, pinned by the sha256
above, before deletion. FG-S250-A: an untracked served orphan has no recovery
path once deleted.

## Alternatives rejected

- Regenerate and re-serve the standalone from `build_offline_verifier_v2`. This
  keeps a second generic verifier whose behaviour differs from the embedded one,
  and it requires a versioning, rebuild and test path that does not exist.
  Rejected as new surface to maintain and audit for no evidentiary gain.
- Leave it served and document the divergence. A reader following the documented
  path would still run a v1-era artifact in a security-critical verification
  step. Rejected.
- Pin the served bytes in a signed inventory attestation. Assessed under a full
  Innovation Gate in S263 and REJECTED AS SCOPED: a digest-based inventory would
  freeze the defect rather than fix it, reporting the served tree CLEAN forever
  over an artifact nobody can account for, with an operator signature and a
  transparency-log anchor behind it.

## Tradeoffs and consequences

- A reader who wants to verify a dossier must obtain the dossier. There is no
  longer a verifier to fetch on its own. This is ADR-0003 applied consistently.
- Dossiers anchored under Rekor v1 are unaffected: `dossier.py` still carries
  `VERIFY_OFFLINE_PY_WITH_REKOR`, so a v1-era dossier ships a v1-capable
  verifier.
- The header comment of `scripts/deploy_website.sh` no longer names this file.
  The deploy stays additive (rsync without --delete), so the served file had to
  be removed by hand after the rsync; it does not return on the next deploy.
- The embedded path stays canonical and was not touched:
  `website/coverage.html:129`, `website/lending.html:283` and `:348`,
  `website/high-assurance.html:278`, `website/ide.html:322`.

## The withdrawn path answers 410, it does not simply disappear

Deleting the file is not sufficient. `infra/nginx/nous-lang.org.conf` routes
every unresolved path through `location / { try_files $uri $uri/ /index.html; }`,
so a request for the withdrawn path would answer 200 with the homepage HTML
under a .py name: a download that looks successful. That is the same defect
class the S235 /.well-known/ carve-out was written to prevent, on a path two
dated blog posts still link to as historical text.

The path answers 410 Gone with a text/plain body naming the replacement
procedure, from an EXACT-match location.

Alternatives rejected:

- Delete and let the SPA fallback answer. 200 with HTML is worse than any
  error, because it looks like the download worked.
- 404. The resource existed and was published; 410 states that it was
  deliberately removed, which is what happened.
- An explanatory HTML page. The consumer of this URL is `curl -sLO`. Serving
  HTML at a .py path is the confusion being removed.
- A prefix location instead of exact. A prefix can be outranked by any regex
  location added later, restoring the 200 silently with the block still sitting
  in the config looking correct. `=` cannot be outranked by anything nginx
  evaluates.
- Rewriting the two dated blog posts to drop the historical links. Rejected by
  the operator: a published post is not edited to make a link tidy.

`tests/test_s237_nginx_config.py` carries the predicate and a negative control
over three synthetic configs it must refuse: prefix instead of exact, exact
returning 200, and no such block at all.

## Evidence ledger (append-only)

- S264: served bytes measured (12377 / a73a8388...); builder output measured
  (44880 / 18760fff...); `served_mirror_check.py` reported tracked 331,
  compared 331, differ 0, missing_served 0, with this file among six orphans.
- S264: nginx reloaded on Server A. Origin-direct, Cloudflare bypassed, two
  identical runs: 410 on the withdrawn path, 200 on /verify_offline2.py and
  /verify_offline.py.bak, 200 on /verify.html and /, 404 on a missing
  /.well-known/ artifact. Suite 2793 passed, 12 skipped.

## Still true?

YES (S264, first entry).
