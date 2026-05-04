<!-- __session71_contributing_v1__ -->
# Contributing to NOUS

Thank you for your interest in NOUS. This document describes
how the project is developed, how to report issues, and how
external contributions are handled.

NOUS is developed under an unusual model that is worth being
upfront about: the project is maintained by one person (Hlias
Staurou, aka Hlia), a chef of 23 years turned AI architect,
who is not a working software developer. The codebase is
written interactively in chat with an AI pair, delivered as
idempotent patch scripts, applied to a Linux server via SCP
plus SSH, and released through a 10-phase pipeline. This means
two things in practice:

1. **The bar for code quality is high.** Every change goes
   through pytest (floor: 394 as of v5.0.0), regression
   templates (57 byte-identical fixtures, 0 drift), pyflakes,
   wheel-content gates, and a clean-venv smoke. There is no
   "looks fine, let's merge."
2. **External pull requests follow a non-standard intake.**
   See [Pull requests](#pull-requests) below for the actual
   path. PRs are welcome but the integration model is "issue
   first, PR after we agree on shape." This protects both the
   contributor's time and the codebase.

If any part of this document is unclear, open a discussion
issue and ask. Plain English is fine. There are no
contributor-facing CLAs to sign.

---

## Code of conduct

Be civil. Disagree about technical content. Do not attack the
person. Bad-faith behaviour, harassment, or off-topic flame
gets you uninvited from the project, and that is the end of
the matter.

---

## License

NOUS is licensed under the MIT License (see `LICENSE` at the
repo root). By submitting a contribution you agree it is
licensed under the same terms. There is no separate CLA. If
you cannot license your work under MIT, please do not submit
it.

---

## Where the project lives

- **Source:** https://github.com/contrario/nous
- **PyPI:** https://pypi.org/project/nous-lang/
- **Website:** https://nous-lang.org/
- **Docs:** https://github.com/contrario/nous/tree/main/docs
- **EU AI Act mapping:**
  https://github.com/contrario/nous/blob/main/docs/EU_AI_ACT_COMPLIANCE.md

---

## How to report issues

Use GitHub Issues:
https://github.com/contrario/nous/issues

A useful issue contains:

1. **What you expected** to happen.
2. **What actually happened**, with the exact command you
   ran, the exact error message, and the exact NOUS version
   (`nous version` output, or `pip show nous-lang | grep
   Version`).
3. **Minimal reproducer.** A `.nous` file of fewer than 30
   lines that triggers the issue. If the issue only triggers
   on a specific pricing TOML, attach the TOML.
4. **Environment.** Python version (`python3 --version`), OS,
   and whether you are running from a clean venv or editable
   install.

For SMT-related issues, please also include:

- Z3 version (`python3 -c "import z3; print(z3.get_version())"`).
- Whether the issue reproduces with `--no-manifest` (rules out
  signing-key issues).
- Output of `nous emit-smt <file>` if relevant.

For replay-related issues, please include:

- The first ~50 events of the JSONL log (with secrets
  redacted), or the output of `nous replay verify <log>`.

Security-sensitive issues should be reported privately first.
See [Security](#security) below.

---

## Setting up a development environment

NOUS targets Python 3.11+. The reference development setup is
Ubuntu 24.04 LTS, but anything POSIX with the right Python
should work.

```bash
# Clone
git clone https://github.com/contrario/nous.git
cd nous

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install in editable mode with the SMT extra
pip install -e '.[smt]'

# Run the test suite
python3 -m pytest tests/ -q
```

The full test suite finishes in well under 10 seconds on a
modern laptop. If yours takes much longer, something is
probably importing the network. Open an issue.

### Running the regression harness

The regression harness compiles 57 reference templates and
diffs the generated Python against committed baselines. Any
codegen-adjacent change must keep this harness green:

```bash
python3 regression_harness.py verify
# expected last line: RESULT: OK
```

If the harness fails, the diff output names the offending
template. Either fix your codegen change so the diff
disappears, or, if your change *intentionally* alters codegen,
re-baseline:

```bash
python3 regression_harness.py rebaseline
git diff regression/
```

Re-baselining must be a deliberate, justified commit. Do not
re-baseline to "make the harness pass" without understanding
what changed.

### After bumping `_version.py`

Editable installs read `_version.__version__` from source on
every import, but `importlib.metadata.version("nous-lang")`
reads from pip's captured metadata (set at install time). If
you bump `_version.py` and run pytest, the
`tests/test_version_consistency.py` suite will fail on the
metadata test. Fix:

```bash
pip install -e . --no-deps --force-reinstall
```

Wheel-installed environments (CI, clean-venv smoke) get the
right version automatically; this only affects editable
installs.

---

## Quality gates

Every change must pass, in this order:

1. **AST compile.** `python3 -m py_compile <file>` for any
   modified Python.
2. **Pytest floor.** `python3 -m pytest tests/ -q` must show
   at least the current floor passing (394 as of v5.0.0; the
   floor is enforced by `tests/test_release_gate.py`).
3. **Regression harness.** `regression_harness.py verify`
   must return `RESULT: OK` for any codegen-adjacent change.
4. **Pyflakes.** Production files must be pyflakes-clean. The
   shipped checked set is enforced by
   `tests/test_pyflakes_phase45.py`.
5. **Lark grammar sync.** If you touched `nous.lark`, run
   `python3 scripts/sync_grammar.py` and commit the regenerated
   embedded grammar in `parser.py`.
6. **Version consistency.** If you bumped any version,
   `tests/test_version_consistency.py` must pass. This checks
   `_version.py`, `cli.py`, `nous_api.py`, `pyproject.toml`,
   `CHANGELOG.md`, and the importlib metadata are aligned.

There are no exceptions. A PR that breaks any of these is
sent back for fixes.

---

## Style

- **Python 3.11+ only.** Use modern syntax (`match`, type
  hints with `|`, `from __future__ import annotations` only
  when it actually helps).
- **Type hints on every function signature.** Return types
  are not optional.
- **Pydantic V2 for data models.** Strict validation; no
  `Any` unless you have a documented reason.
- **No external agent frameworks.** NOUS is built from
  scratch on `asyncio`, Pydantic V2, Lark, and httpx. Do not
  introduce LangChain, LlamaIndex, CrewAI, AutoGen, or
  similar. PRs that add such dependencies will be closed.
- **TOML via `tomllib`. YAML via `pyyaml`. Parsing via
  `lark`.** Do not introduce alternatives.
- **ASCII-only source.** Do not use em-dashes, curly quotes,
  or other Unicode in `.py` source. They break `bytes`
  literals in patch tooling and create cross-platform
  surprises. Use `--`, `-`, `'`, `"`.
- **No dead code.** If you remove a feature, remove its
  tests, its CLI registration, and its CHANGELOG references.
  Pyflakes is enforced for a reason.

---

## Pull requests

External PRs are welcome but follow a non-standard intake to
match the project's chat-driven development model.

### Step 1 -- Open an issue first

Before writing code, open a GitHub issue describing:

- The problem you are solving (with reproducer if it is a
  bug).
- The shape of the fix you have in mind.
- Whether you want to write the patch yourself.

The maintainer will respond with a yes / no / let's-shape-it.
This step exists because NOUS has a tightly coupled internal
architecture (parser, AST, codegen, SMT, manifest, dossier
all share invariants), and a 200-line PR can be impossible to
merge if it cuts across an invariant the contributor did not
know about. The issue conversation surfaces those constraints
before the diff exists.

### Step 2 -- Branch, code, push

After alignment on the issue:

- Branch from `main`. Name the branch
  `feat/<short-slug>` for features, `fix/<short-slug>` for
  bugfixes, `docs/<short-slug>` for doc-only changes.
- Make the change. Keep the diff focused on what the issue
  agreed on.
- Run the full quality-gate checklist above.
- Push the branch to your fork and open the PR against
  `main`.

### Step 3 -- PR contents

A mergeable PR contains:

- A title that names the change (e.g.
  `fix(smt): accept lowercase EUR in cost_cap`).
- A body that links the issue (`Closes #N`).
- A `CHANGELOG.md` entry under `## [Unreleased]`. Use the
  same shape as recent entries: `Added`, `Changed`,
  `Fixed`, `Removed`, `Deprecated`, `Security`. One bullet
  per user-visible change.
- Tests for the change. New behaviour must be covered. Bug
  fixes must include a regression test that fails on the
  pre-fix code and passes after.
- Documentation updates in `docs/` if user-facing behaviour
  changed.

### Step 4 -- Review

The maintainer will review with the same standards used
internally. Expect direct, unvarnished feedback. "Why" is
always welcome; "I don't like the style" is not a review
comment, "this conflicts with the AST hashing invariant in
ast_nodes.py L142" is.

Reviews can take days, not minutes. NOUS is built in focused
sessions, not in continuous batches.

### What gets rejected

- PRs that add external agent frameworks.
- PRs that bypass quality gates.
- PRs without an antecedent issue, except for one-line
  documentation typo fixes.
- PRs that introduce non-ASCII characters in `.py` sources.
- PRs that break the regression harness without an explicit,
  justified re-baseline.
- PRs that change pricing TOML schema without a sha-stable
  migration story (v5.0.0 closed the free-rename window;
  future schema changes must be additive or shipped with a
  versioned canonicaliser).

---

## Commit messages

Follow conventional-commits style:

- `feat(scope): short summary`
- `fix(scope): short summary`
- `docs(scope): short summary`
- `refactor(scope): short summary`
- `chore(scope): short summary`
- `release(vX.Y.Z): short summary`

Scope is optional but encouraged. The first line stays under
72 characters. The body explains the why, not the what (the
diff already shows the what).

For multi-line commit messages, use a `commitmsg_*.txt` file
and `git commit -F` to avoid shell-active characters.

---

## Releases

Releases are cut by the maintainer using
`scripts/release.py`, which runs the 10-phase pipeline:

1. Pre-flight (clean tree, tag does not exist)
2. Grammar sync check
3. Pytest with floor enforcement
4. Regression harness
5. Version consistency
6. Pyflakes
7. Build wheel + sdist
8. Wheel content gate (templates, grammar, version metadata)
9. Clean-venv install + UX smoke
10. PyPI upload (only with `--upload`)

Contributors do not run this. The CHANGELOG entry under
`[Unreleased]` is what gets promoted to the released version
when a release is cut.

---

## Architecture invariants

A short list of things that must not silently break:

- **AST sha-stability.** `NousNode.sha256()` is part of the
  signed manifest. Adding a required field to an AST node
  without a migration plan breaks every existing manifest.
- **Pricing TOML sha-stability post-v5.0.0.** Future schema
  changes must produce identical sha256 for logically-
  equivalent v1 and v2+ inputs. The translator must run before
  canonicalisation.
- **Replay chain integrity.** Every event has
  `prev_hash + content_hash`. Anything that touches replay
  must preserve the chain or it is a regression by
  definition.
- **Currency consistency.** The Phase 5a guard
  `_validate_currency_consistency` is the asfaleia floor for
  cost-cap proofs. Removing or weakening it breaks the EU AI
  Act audit chain. Do not.
- **Codegen byte-stability.** 57 templates are pinned. Any
  codegen change either preserves all 57 or is shipped with
  an explicit, justified re-baseline.

If you are about to change one of these, open the issue
first.

---

## Documentation

Doc-only changes (`docs/*.md`, `README.md`, `CHANGELOG.md`)
follow the same PR flow but the bar is much lower: typo
fixes, clarifications, examples, and small structural
improvements are merged quickly. The `docs/` directory is
considered part of the audit surface for EU AI Act
compliance, so accuracy matters; a wrong claim is worse than
a missing claim.

---

## Security

Vulnerabilities should not be reported in public issues.
Email the maintainer through the address listed on the
`nous-lang.org` website, or open a GitHub Security Advisory:
https://github.com/contrario/nous/security/advisories/new

Things that count as security-relevant:

- Bypasses of the SMT cost-bound proof (programs that compile
  under `--smt` but exceed their declared cap at runtime in a
  reproducible way).
- Manifest forgery or signature-bypass attack vectors.
- Replay chain integrity attacks (events that pass
  `nous replay verify` but contain altered content).
- Authentication bypasses on the HTTP API
  (`nous_api_server.py`).
- TOML injection or path traversal in the pricing or template
  loaders.

Things that are not security issues:

- Crashes on malformed `.nous` source. These are bugs; report
  via normal Issues.
- High proven cost bounds. The bound is an upper bound by
  construction; tightening it is a Phase 5c concern, not a
  vulnerability.

---

## Contact

- **Issues / discussion:** GitHub Issues on the repo.
- **General:** the contact form on https://nous-lang.org/.

The maintainer responds in batches, not continuously.
Patience appreciated.

---

*Last updated: Session 71, 3 May 2026 (HEAD post-`4f7e874`,
v5.0.0).*
