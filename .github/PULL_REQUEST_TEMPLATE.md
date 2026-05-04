<!-- __session71_community_files_v1__ -->

<!--
  Thanks for the patch. Please fill in this template before
  requesting review. PRs without an antecedent issue are sent
  back, except for one-line documentation typo fixes; see
  CONTRIBUTING.md for the full intake flow.
-->

## Linked issue

Closes #<issue number>

<!-- If there is no issue, explain why this PR is exempt
     (typo fix, doc-only, etc). -->

## What this changes

<!-- Two or three sentences. The diff already shows the what;
     focus on the why. -->

## Type of change

Pick the closest match (delete the rest):

- Bug fix (no API change)
- Bug fix (API change)
- New feature (no breaking change)
- New feature (breaking change)
- Documentation only
- Refactor / internal cleanup
- Build, release, or CI tooling

## Quality gates

All of these must be green before merge. Tick them as you go.

- [ ] `python3 -m pytest tests/ -q` passes (floor 394 as of
      v5.0.0).
- [ ] `python3 regression_harness.py verify` returns
      `RESULT: OK` (or this PR includes a deliberate
      re-baseline with justification below).
- [ ] Pyflakes-clean for any modified production file.
- [ ] If `_version.py` was bumped: `pip install -e . --no-deps
      --force-reinstall` was run, and
      `tests/test_version_consistency.py` passes.
- [ ] If `nous.lark` was modified: `python3
      scripts/sync_grammar.py` was run and the regenerated
      embedded grammar is committed.
- [ ] If user-visible behaviour changed: `CHANGELOG.md` has a
      bullet under `## [Unreleased]`.
- [ ] If user-visible behaviour changed: relevant `docs/*.md`
      updated.
- [ ] No external agent frameworks added (LangChain,
      LlamaIndex, CrewAI, AutoGen, etc).
- [ ] No non-ASCII characters in `.py` source.

## Architecture invariants

If this PR touches any of the following, briefly explain how
the invariant is preserved (or call out the deliberate
break):

- AST sha-stability (`NousNode.sha256()`)
- Pricing TOML sha-stability post-v5.0.0
- Replay chain integrity (`prev_hash` + `content_hash`)
- Currency consistency guard (`_validate_currency_consistency`)
- 57-template codegen byte-stability

<!-- e.g. "Adds a new optional field to PricingEntry; the
     loader translator runs before canonicalisation, so
     existing v1 and v2 inputs continue to produce the same
     sha." -->

## Tests added

<!-- List the new test files or test classes. New behaviour
     must have new tests. Bug fixes must include a regression
     test that fails on the pre-fix code. -->

## Re-baseline justification

<!-- Only if the regression harness was re-baselined on
     purpose. Explain what changed in codegen output and why
     it is correct. Skip this section otherwise. -->

## Anything else reviewers should know

<!-- Performance notes, security implications, follow-up work
     deferred to a later PR, etc. -->
