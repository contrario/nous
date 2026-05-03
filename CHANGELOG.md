# Changelog

## [5.0.0] - 2026-05-03

### Breaking

- **Pricing schema v1.0 -> v2.0 field rename.** The `*_usd` suffix
  has been dropped from `PricingEntry` to make per-token rates
  currency-agnostic; per-table `_currency` is now authoritative.
    - `input_per_1m_usd`            -> `input_per_1m`
    - `output_per_1m_usd`           -> `output_per_1m`
    - `input_cached_per_1m_usd`     -> `input_cached_per_1m`
    - `input_cache_write_per_1m_usd`-> `input_cache_write_per_1m`
    - `hourly_cost_usd`             -> `hourly_cost`
  Existing v1.0 pricing TOMLs continue to load via a loader-side
  backward-compat translator that emits exactly one
  `DeprecationWarning` per file. Run `nous prices upgrade <file>`
  to migrate.

- **`PricingTable.sha256()` canonical form changed for v1.0 inputs
  after migration.** The pre-translation v1.0 hash and the
  post-Phase-5b hash for the same logical data will differ
  because canonical field names changed. No production dossiers
  existed prior to this release, so the break has zero deployed
  impact. Going forward, sha256 is stable across v1->v2 loads
  because the translator runs before canonicalisation.

### Added

- **`nous prices upgrade <input.toml> -o <output.toml>`** -- new
  CLI subcommand. Line-based migration that preserves comments,
  blank lines, and formatting verbatim. Validates the migrated
  TOML through the v2 loader and full Pydantic validation BEFORE
  writing the output file. Idempotent on v2.0 input. Refuses to
  overwrite output without `--force`. Supports `--in-place`.

- **EUR end-to-end SMT cost verification.** Programs declaring
  `cost_cap: <amount> EUR` and using a pricing table with
  `_currency = "EUR"` now compile cleanly under `--smt`. Z3
  round-trip confirmed: provable obligations return UNSAT,
  refuted obligations return SAT with counterexamples. The
  Phase 5a `_validate_currency_consistency` guard remains:
  mixing pricing-currency and cap-currency inside a single
  proof is still refused (FX rates are not auditable).

- **`pricing/eur_example.toml`** -- shipped EUR-native pricing
  demonstration with three Mistral models and a local-ollama-eur
  entry. Values are illustrative; production use requires
  provider verification.

- **`tests/test_pricing_v1_compat.py`** (12 tests) locking in
  the v1->v2 loader translator: DeprecationWarning emission,
  sha-stable v1==v2 invariant, dual-name rejection, decimal
  precision preservation.

- **`tests/test_cli_prices_upgrade.py`** (18 tests) covering
  every upgrade CLI behaviour including comment / blank-line
  preservation and post-migration Pydantic validation.

- **`tests/test_smt_emit_eur.py`** (11 tests) end-to-end EUR
  cost verification including Z3 round-trip with provable and
  refuted obligations at multiple `max_ticks` scales.

### Removed

- The v4.13.0 USD-only escape hatch in
  `smt_emit.py::_validate_world` (the `if w.cost_cap.currency
  != "USD"` block raising "USD only"). Phase 5a's
  `_validate_currency_consistency` remains in place as the
  asfaleia floor for mismatched-currency cases.

- `tests/test_smt_emit.py::test_eur_currency_rejected_v4_13`.
  The test asserted error message "USD only" which no longer
  exists. The mismatch case it exercised (USD pricing + EUR
  cap) is covered by `test_currency_consistency_eur_pricing_rejects`
  and the new `test_smt_emit_eur.py::TestCurrencyMismatchStillRejected`
  class.

### Migration guide

```bash
# Migrate a v1.0 pricing TOML in place:
nous prices upgrade ./nous_prices.toml --in-place

# Migrate to a separate output file (safe for review):
nous prices upgrade ./nous_prices.toml -o ./nous_prices_v2.toml
diff ./nous_prices.toml ./nous_prices_v2.toml

# After migration, cost_cap.currency MUST equal pricing _currency.
# If your project uses a non-USD provider (e.g. Mistral via Le
# Plateforme), update BOTH sides:
#   1. _currency = "EUR"        in your pricing TOML
#   2. cost_cap: 0.50 EUR       in your world block
```

PYTEST_FLOOR: 354 -> 394

## [4.18.0] - 2026-05-01

### Added
- `DiffSide` provenance model in `nous_api.py`: classifies one side of a diff
  comparison by `kind` (template / editor / paste / replay / file / unknown),
  optional `identifier`, and optional `label` override.
- `DiffRequest.original_side` and `DiffRequest.modified_side` (both optional;
  default `None` = backward compatible with 4.16.x clients).
- `render_diff_side()` canonical renderer producing deterministic display
  strings: `Template: sycophancy_guard`, `Editor (current)`, `Paste A`,
  `Replay 550e8400…`, `File: sample.jsonl`, `(unknown source)`.
- `/v1/diff` response now includes `original_label` and `modified_label`
  fields, server-rendered via the canonical function. Clients that send
  no provenance get `(unknown source)` for both — explicit, not fabricated.
- 17 regression tests in `tests/test_diff_side.py` covering every kind,
  edge cases (anonymous paste, missing identifier, label override),
  request roundtrip, and Literal enum rejection of unknown kinds.

### Fixed
- The IDE diff card no longer needs to hardcode the literal
  `original.nous -> modified.nous` string. All four flows (Save bar,
  template-vs-editor, paste-vs-paste, replay-vs-replay) now have a
  contract-defined provenance shape they can fill in. Frontend wiring
  follows in a separate commit (lives outside this repo at /var/www/).

### Architectural notes
- Mirrors W3C PROV: every comparison artifact has TWO sides, each with
  identity + origin metadata. Removes the audit-trail liability where
  `nous dossier` evidence pointed at fictional file names.
- `kind` is a closed Literal enum. New kinds are explicit additions, not
  silent string drift. `unknown` is the safe default; clients are not
  forced to lie.
- Server computes labels once. Audit logs and dossiers see stable strings
  regardless of client UI version.

### Breaking
- None. Existing 4.16.x clients sending only `original` and `modified`
  continue to work; the response gains two new fields they can ignore.

PYTEST_FLOOR: 320 -> 337

## [4.17.0] - 2026-05-01

### Added
- `ast_nodes.iter_route_edges(nervous_system)`: canonical iterator yielding
  `(source, target, kind)` tuples over every NerveStatement edge
  (RouteNode, MatchRouteNode, FanInNode, FanOutNode, FeedbackNode).
  Single source of truth for route enumeration; reimplementing this
  dispatch elsewhere is now a regression.
- 10 regression tests in `tests/test_iter_route_edges.py` covering
  every variant, silence-arm filtering, empty/None inputs, and
  unknown-subtype panic. PYTEST_FLOOR raised 310 -> 320.

### Fixed
- `nous show` no longer silently drops FanIn/FanOut/Feedback edges.
  Previously the `hasattr(r, "source") and hasattr(r, "target")` guard
  matched only RouteNode; programs with multi-source/multi-target
  topology displayed wrong edge counts.
- `nous cost-cap` no longer crashes on programs containing FanOutNode
  or FeedbackNode. Previously `route.target` access raised AttributeError
  on these variants.
- `behavioral_diff._get_routes` now delegates to `iter_route_edges`,
  collapsing 27 lines of duplicated dispatch into 4. Behavior preserved
  by existing test suite.

### Dependencies
- `cryptography>=42,<47` promoted from `[smt]` extra to a base dependency.
  `cli.py` loads `cli_dossier` -> `dossier` at module import (Session 64),
  so cryptography was already a hard requirement for any working install.
  The `[smt]` extra now contains only `z3-solver`.

### Internal
- NerveStatement dispatch sweep, phase 1-4. Remaining inline dispatch
  in `verifier.py`, `validator.py`, `codegen.py` deliberately retained:
  those sites do per-kind work beyond edge enumeration and need separate
  refactors.

<!-- __session63_changelog_v4_13_0__ -->

<!-- __session63_changelog_v4_13_1__ -->
<!-- __session64_changelog_v4_13_2__ -->
<!-- __session64_changelog_v4_13_3__ -->
<!-- __session65_changelog_v4_16_0__ -->
<!-- __session66_changelog_v4_16_1__ -->
## [4.16.1] - 2026-04-30
### Fixed
- **`/v1/diff`** crashed with `'FeedbackNode' object has no attribute
  'source'` (and `.target`) when either input contained a
  `FeedbackNode`, `FanInNode`, `FanOutNode`, or `MatchRouteNode` in
  its `nervous_system`. Three call sites had blind
  `route.source` / `route.target` access:
    1. `behavioral_diff._get_routes`
    2. `behavioral_diff._get_entrypoints`
    3. nested `_get_routes` inside
       `nous_api_server._transform_diff_for_ide`.
  All three now isinstance-dispatch over every `NerveStatement`
  variant and emit the correct edges (or "is a target" set).
### Tests
- New `tests/test_behavioral_diff_routes.py` (+8 tests) locks in the
  dispatch behavior for each NerveStatement variant plus mixed and
  empty cases. Pytest floor: 302 -> 310.
## [4.16.0] - 2026-04-30
### Added
- **`PUT /v1/templates/{name}`** --- save a `.nous` world template
  to `TEMPLATES_DIR`. Pairs with the existing
  `GET /v1/templates/{name}` (read) for full RESTful CRUD on
  templates. Pipeline:
  1. Hard auth (`require_write_api_key`): empty `API_KEYS` -> 403,
     missing or invalid key -> 401. Reads remain soft-auth.
  2. Name sanitisation: `^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$`,
     resolved path must stay inside `TEMPLATES_DIR`.
  3. Lint gate: `governance_lint` errors block the save unless
     `force=true`. Linter crash treated as has_errors.
  4. Backup: existing file copied to
     `<name>.nous.bak.<YYYYmmddTHHMMSS_uuuuuu>`, oldest pruned
     beyond 5 backups.
  5. Atomic write: `tempfile -> fsync -> os.replace`. No reader
     ever sees a partial file.
  6. Response includes `sha256` of bytes written.

### Architectural notes
- **No alias endpoints added.** The Session 64 sec.6.3 plan listed
  `/v1/policies/list` and `/v1/policies/validate`, but the
  existing `GET /v1/governance/policies` and
  `POST /v1/governance/lint` already cover those. Aliasing
  doubles the API surface for zero new capability and was
  rejected.
- **Endpoint named for what it actually does.** A `.nous` template
  contains the entire world (souls, mind, governance), not just
  policies. `templates/save` is honest naming.

### Tests
- `tests/test_templates_save.py` --- 13 new tests covering hard
  auth (3 paths), happy path, backup creation + pruning to 5,
  lint-errors-blocks-save, force-override, lint-unavailable,
  lint-crash, and three name-safety rejections.
- PYTEST_FLOOR: 289 -> 302.

### Compatibility
- No changes to existing endpoints. No grammar / AST / codegen
  changes. 57/57 regression templates baseline-stable.

<!-- __session65_changelog_v4_15_0__ -->
## [4.15.0] - 2026-04-30
### Added
- **`GET /v1/replay/list`** --- enumerate replay logs in
  `NOUS_REPLAY_DIR` (default `/var/lib/nous/replays`,
  env-overridable). Returns per-log metadata (name, size,
  mtime, last_seq_id, last_hash, last_kind) via O(8KB) tail
  read. Does not validate hash chains; pair with
  `/v1/replay/verify` for integrity.
- **`POST /v1/replay/diff`** --- lockstep compare two replay
  logs by `(seq_id, hash)`. Body: `{a, b, max_events?}`
  (filenames inside `NOUS_REPLAY_DIR`). Returns status =
  `identical | divergent | truncated_a | truncated_b | error`,
  with first divergence event side-by-side.

### Security
- New endpoints sandbox filenames to `NOUS_REPLAY_DIR`. Reject
  path separators, leading dot, parent-dir traversal, and
  symlinks pointing outside the directory. Existing replay
  endpoints (`summary`, `events`, `verify`) preserve their
  current absolute-path behaviour for backward compatibility.

### Tests
- `tests/test_replay_list_diff.py` --- 11 new tests covering
  list metadata, list filtering, diff identical / truncated_a /
  truncated_b / divergent, and four path-safety rejections.
- PYTEST_FLOOR: 278 -> 289.

### Compatibility
- No changes to existing endpoints. No grammar / AST / codegen
  changes. 57/57 regression templates baseline-stable.

<!-- __session64_changelog_v4_14_0__ -->
## [4.14.0] - 2026-04-29

### Added

- **`nous dossier <source.nous>`** --- new top-level subcommand
  for EU AI Act Annex IV compliance bundles. Takes a NOUS source
  plus its signed manifest, validates the full crypto chain, and
  emits a self-contained directory:

  ```
  source_dossier_<timestamp>/
      source.nous           audited program
      manifest.json         signed manifest (copy)
      pricing.toml          active pricing layer snapshot
      public_key.b64        raw 32-byte Ed25519 pubkey
      README.md             Annex IV item-by-item mapping
      verify_offline.py     portable verifier (cryptography only)
  ```

  Pre-conditions verified before any file is written
  (raises `DossierError` otherwise):
  1. Manifest Ed25519 signature is valid.
  2. Source bytes hash matches `manifest.source_sha256`.
  3. Active pricing TOML hash matches `manifest.pricing_sha256`.
  4. Re-emitted SMT spec hash matches `manifest.smt_spec_sha256`.

- **`verify_offline.py`** ships in every dossier. Pure stdlib +
  `cryptography` library. No NOUS install required. Re-checks
  Ed25519 signature and source SHA-256, prints PASS/FAIL with
  exit `0` / `1`. Designed for regulators and auditors who hold
  the dossier directory and the publisher's public key.

- New module `dossier.py` (`build_dossier()`, `DossierError`,
  `DossierResult`).
- New CLI module `cli_dossier.py` (`cmd_dossier`,
  `build_dossier_parser`).

### Architectural decision

- The original Session 63 candidate name was
  `nous prices export --format=annex_iv`. Renamed to top-level
  `nous dossier` because a dossier composes manifest + source +
  pricing + crypto, not pricing alone. The `nous prices` tree
  stays focused on pricing operations (`show`, `init`, `verify`,
  `age`).

### Tests

- `tests/test_dossier.py` --- 6 tests (272 -> 278 total).
  - happy path emits 6 expected files
  - README contains Annex IV mapping items 1-9
  - verify_offline.py is executable
  - tampered source -> source.sha256 mismatch
  - tampered manifest -> Ed25519 signature does NOT verify
  - non-empty output dir -> refuse to overwrite

### Packaging

- Added `dossier` and `cli_dossier` to `pyproject.toml` py-modules
  so wheel installs include both.

## [4.13.3] - 2026-04-29

### Added

- **`--smt-margin PCT` flag** for `nous verify --smt`. Proves
  `total_cost <= declared_cap * (100 - PCT) / 100` instead of
  `total_cost <= declared_cap`. Conservative buffer for compliance
  use cases (e.g. EU AI Act dossiers where regulators expect a
  proven safety margin against billing surprises). Range `0..99`.
  Default `0`. Example:
  ```
  nous verify file.nous --smt --smt-margin 20
  PROVEN: total_cost <= $0.4 USD across all execution paths.
    Declared cap: $0.5 USD, safety margin: 20%.
  ```

- New `SMTSpec.cost_cap_margin_pct: int` field (default `0`).
- New `Manifest.safety_margin_pct: Optional[int]` field. Populated
  only when `--smt-margin > 0`; absent from canonical JSON when
  margin is zero (preserves manifest schema for non-margin runs).

### Backward compatibility

- `--smt-margin 0` (default) preserves the v4.13.2 obligation
  literal and SMT-LIB serialize structure exactly. The spec sha256
  cycles on the version-string bump (the `NV:` canonical key
  includes `nous_version`), as it does on every release.
- 57 / 57 regression templates baseline-stable.
- All cost_cap demo templates compile, verify, and emit manifests
  byte-identically when `--smt-margin` is omitted.

### Tests

- `tests/test_smt_margin.py` — 8 new tests (264 -> 272 total).

## [4.13.2] - 2026-04-29

### Removed

- **Broken AetherProof publish path.** `manifest.publish_to_aetherproof()`,
  the `AETHERPROOF_DEFAULT_URL` constant, and the `--publish` /
  `--publish-endpoint` CLI flags on `nous verify --smt` are gone.
  The shipped client posted to `https://api.aetherlang.online/v1/manifests`,
  but that POST endpoint was never built (only `GET /v1/manifests/{id}`
  exists publicly), and the payload schema NOUS sent did not match what
  the AetherProof service expects (gate evidence, not pre-signed
  manifests). Calling `--publish` on v4.13.1 always failed with
  `HTTP 404`.

### Architectural decision

- **NOUS manifests are self-verifying offline artifacts.** A holder of
  the manifest file plus the publisher's Ed25519 public key can verify
  authenticity without contacting any service. Storage is the
  publisher's choice (filesystem, S3, IPFS, git release, etc.) — no
  central-ledger dependency. `manifest.verify_manifest_signature()`
  remains the offline-verification primitive. `sign_manifest`,
  `manifest_json`, `parse_manifest_json`, and the keypair management
  helpers are unchanged.

### Documentation

- `docs/COST_VERIFICATION_GUIDE.md`, `docs/SMT_VERIFICATION_DESIGN.md`,
  and `docs/EU_AI_ACT_COMPLIANCE.md` updated to describe
  storage-agnostic, offline-verifiable manifests instead of
  POST-to-central-service.


## [4.13.1] - 2026-04-28

### Fixed

- **Shipped `pricing/defaults.toml` not found by wheel installs.**
  `pricing.py` hardcoded `<package>/pricing/defaults.toml`, but
  setuptools `data-files` installs the file at
  `<sys.prefix>/pricing/defaults.toml`. Fresh installs of v4.13.0
  could not run `nous verify --smt` (loader raised
  `FileNotFoundError: no pricing TOML found in any layer`).

  The package-defaults layer (layer 4) now resolves through a
  small helper that tries, in order:
  1. `<__file__>/pricing/defaults.toml` (dev tree, editable install).
  2. `<sys.prefix>/pricing/defaults.toml` (data-files install).
  3. `<sys.prefix>/share/pricing/defaults.toml` (some venv layouts).

  Layer index unchanged: still `4` (so existing tests and
  manifest provenance audits remain stable).

### Notes

- v4.13.0 was tagged and a GitHub release was published, but the
  wheel was **never uploaded to PyPI** because clean-install
  verification caught this issue first. v4.13.1 is the first
  v4.13.x to reach PyPI.



## [4.13.0] - 2026-04-28

### Added — Formal SMT cost-bound verification

- **`cost_cap` world-body declaration** — `cost_cap: 0.50 USD` declares a
  hard upper bound on total program spend. Currency parser supports USD
  (extensible to EUR etc. in Phase 5).
- **`max_ticks` world-body declaration** — `max_ticks: 5` bounds the number
  of execution cycles. Required input for SMT proof.
- **Per-soul `tokens` declaration** — `tokens: input=500 output=200`
  declares per-tick token estimates. Multiplied by per-token rates from
  the active pricing table to compute worst-case spend.
- **Layered pricing infrastructure** (`pricing/defaults.toml`):
  - Strict Pydantic loader with schema v1.0.
  - Priority order: `--prices` flag > `./nous.prices.toml` >
    `~/.config/nous/prices.toml` > package defaults.
  - Deterministic ordering, SHA-256 audit hash.
  - New CLI: `nous prices show / init / verify / age`.
- **`smt_emit.py`** — deterministic SMT-LIB 2.6 emitter. Decimal → exact
  rationals; no float artefacts. Output is byte-deterministic across
  runs and machines. New CLI: `nous emit-smt FILE.nous`.
- **`smt_verify.py`** — Z3 wrapper with counterexample extraction and
  **constructive fix suggestions** (raise cap to X / reduce ticks to Y /
  identify largest contributor).
- **`manifest.py`** — ed25519-signed JSON manifests (Sigstore/SLSA
  convention). Single self-contained file with embedded base64 signature.
  Tamper detection. AetherProof publish opt-in via `--publish`.
- **`nous verify FILE.nous --smt`** — flagship CLI: parse → emit → solve
  → manifest. Backward compat preserved: `nous verify FILE.nous` (no
  `--smt`) still runs governance lint as a build gate.
- **ed25519 key management** — auto-generated at
  `~/.local/share/nous/keys/signing.key` (XDG, mode 0600).
  `--key-path` override supported.
- **`[smt]` optional extra** in `pyproject.toml`:
  `z3-solver>=4.15.0,<4.17.0` and `cryptography>=42,<47`.
- **Documentation**: `docs/COST_VERIFICATION_GUIDE.md`,
  `docs/SMT_VERIFICATION_DESIGN.md`, `docs/EU_AI_ACT_COMPLIANCE.md`.

### Changed

- Existing `nous verify` subparser extended with `--smt` flag. No new
  subparser registered. Default behaviour (no `--smt`) unchanged.

### Stats

- Tests: 184 → 264 (+80).
- Regression templates: 54/54 byte-identical (additive arc only).
- Codegen touch: zero.
- New modules: `smt_emit`, `cli_emit_smt`, `smt_verify`, `manifest`,
  `cli_verify`, `pricing/*`.

---

## [4.12.0] - 2026-04-27

### Added

- **Single-source `VERSION` constant** — `_version.py` is now the sole
  source of truth (`__version__: str` + `__version_tuple__: tuple`).
  `nous_api.py` reads it dynamically; no hardcoded version strings
  anywhere else.
- **R18 version-consistency test** — verifies pip metadata matches
  `_version.__version__` after install. Run with
  `pip install -e .` to refresh metadata before invoking.
- **Atomic release pipeline** — Phase 4.5 pyflakes gate added; release
  pipeline now has 10 phases, each commit-atomic.

### Fixed

- `cli.py`: missing `Any` in typing import.
- `nous_api_server.py`: `NousProgram` forward ref + `body`/`message`
  `NameError` in compile/verify/chat pipelines.
- `tests/conftest.py`: exclude `test_replay_phase_d.py` from collection
  (path-collection edge case).

### Changed

- Build artifacts (`build/`, `dist/`, `*.egg-info/`) added to
  `.gitignore`.

---

## [4.11.3] - 2026-04-25

### Fixed

- **Broken-template hotfix** — `nous templates copy` was emitting a
  template that failed parser load on fresh installs.
- **Grammar single-source** — `nous.lark` is now resolved through one
  canonical loader path. Previous duplicate-resolution paths (package
  vs sys.path) caused divergent parser state on certain installs.

---

## [4.11.2] - 2026-04-21

### Added

- **Templates as proper package** — bundled `.nous` templates moved into
  the top-level `templates/` package and shipped via `package-data`.
  Reachable via `importlib.resources`.
- **`nous templates list / copy <name>`** CLI commands.

---

## [4.11.1] - 2026-04-21

### Changed

- **`nous_api.py` split** into thin importable library + dedicated
  `nous_api_server.py` runner. Programs that only need to call the
  library no longer pull in FastAPI/uvicorn at import time.

---

## [4.11.0] - 2026-04-21

### Added

- **Sycophancy phrase detector** (`phrase_detector.py`) — heuristic
  pass over LLM outputs to flag flattery / capitulation / over-eager
  agreement language.
- **`llm.response` event kind** — first-class event in the governance
  layer. Policies can match on `llm.response` and inspect the response
  string via signal helpers (e.g. `contains_phrase("absolutely")`).
- Governance lint extended to validate `llm.response` policies.

---

## [4.10.0] - 2026-04-17

### Added
- `--error-on CODES` CLI flag for `nous governance lint` — elevate non-error rules to failure (e.g. `--error-on L010,L007`). Exit 2 on invalid rule codes.
- `nous verify` now runs governance lint after formal verification. Errors fail the build by default. New flags: `--no-lint`, `--lint-strict`, `--lint-error-on`.
- LSP server emits lint diagnostics with source `nous.lint`. Visible as red/amber/blue squiggles in VS Code (L008 error, L010 warning, L007 info).
- New module `governance_simulator.py` — safe-eval engine for what-if policy evaluation. Data fields become bare names in signal namespace.
- New HTTP endpoint `POST /v1/governance/simulate` — simulate an event against declared policies. Error codes SIM001/SIM002/SIM003.
- New IDE element: EVENT SIMULATION strip in Governance tab with kind/data inputs and color-coded fired/skipped matches.
- New constant `VALID_RULE_CODES` and helper `_parse_rule_codes()` in `governance_lint`.
- New template `governance_demo.nous` with 5 policies across 3 event kinds.

### Changed
- `lint_cli()` signature extended with optional `error_on: str | frozenset[str] | None = None`.
- `cmd_verify()` behavior change: files with governance lint errors now fail the build. Use `--no-lint` to restore pre-4.10.0 behavior.

### Stats
- Tests: 163 -> 212 (+49)
- Regression templates: 52/52 byte-identical
- Codegen touch: zero
- New modules: 1 (`governance_simulator`)
- New tests files: 3 (`test_governance_simulator`, `test_verify_lint_integration`, `test_lsp_lint_integration`)

## [4.9.1] - 2026-04-17

### Fixed

- **Missing module in wheel**: `governance_lint.py` was not listed in
  `[tool.setuptools].py-modules` despite being introduced in v4.9.0.
  Fresh PyPI installs of 4.9.0 raised `ImportError` when running
  `nous governance lint` or calling `POST /v1/governance/lint`.
- v4.9.0 is broken on PyPI; users should install v4.9.1 or higher.

---


## [4.9.0] - 2026-04-17

### Added -- `nous governance lint` CLI

Static analysis for NOUS policy declarations. New subcommand:

    nous governance lint <file.nous> [--format text|json] [--strict]

Rule catalog (L000-L100):

- **L000** file not found
- **L001** duplicate policy name
- **L002** empty policy name
- **L003** invalid action (must be log_only/intervene/block/abort_cycle/inject_message)
- **L004** weight out of range (0.0, 10.0]
- **L006** empty signal expression
- **L007** unknown event kind (info)
- **L008** `inject_message` policy missing `message` field
- **L009** no policies in file (warn)
- **L010** reserved name prefix `__` (warn)
- **L011** negative window
- **L012** literal `True`/`False` signal (always/never fires)
- **L100** parse error

Output: text (default) or machine-readable JSON. `--strict` promotes warnings to non-zero exit for CI pipelines.

### Added -- Interactive Governance tab in IDE (`/ide`)

Sixth tab alongside Editor/Verify/Graph/Architecture Diff/Chat. Two-column layout:

- **Policies** (left): declared policies with color-coded action badges (red for block/abort_cycle, amber for intervene, purple for inject_message, blue for log_only), weight, kind, signal expression.
- **Lint** (right): live static analysis with severity-coded issues (ERR / WARN / INFO), rule code, policy name, message.

Auto-refreshes when the tab is clicked (debounced 150ms). Manual REFRESH button. Reads source via `monaco.editor.getEditors()[0].getValue()`.

### Added -- New backend endpoint

- **POST `/v1/governance/lint`**: exposes `GovernanceLinter.lint_source()`. Request `{source: str, strict: bool}`. Response: full `LintReport` as JSON plus `would_fail_strict` flag. API-key protected, rate-limited 60/min. Error codes LNT001 (module missing) / LNT002 (internal error).

### Tests

- 37 new tests in `tests/test_governance_lint.py`.
- Total test count: **126 -> 163** (+37).
- 52/52 regression templates remain byte-identical (zero codegen impact).

### Architecture notes

- Linter uses `parse_nous()` directly instead of `PolicyInspector` so it can inspect `inject_as`, `message`, `window`, `description` fields that `PolicyInfo` strips.
- Empty/whitespace source short-circuits to L009 instead of L100 parse error for cleaner UX.
- New files: `governance_lint.py`, `tests/test_governance_lint.py`.

---

## [4.8.3] - 2026-04-17

### Fixed

- **Missing dependency**: `pyyaml` was not declared in `pyproject.toml`
  dependencies despite being required by `risk_engine.py` (since v4.5.0).
  Fresh installs from PyPI failed with `ModuleNotFoundError: No module named 'yaml'`
  when importing any governance module.
- `pyyaml>=6.0` is now an explicit core dependency.

### Notes

No functional code changes. v4.8.2 is broken on PyPI for clean installs;
users should install v4.8.3 or higher.

---

## [4.8.2] - 2026-04-17

### Added — Phase G Layer 4.5: prompt-hash recompute on inject_message

When an `inject_message` policy triggers and modifies the outgoing LLM
messages, the `llm.request` event now carries three additional fields:

- `prompt_hash_post_inject`: sha256 of the canonical payload after injection
- `injected_role`: the role (`system` or `user`) that was injected
- `injected_policies`: list of policy names that caused the injection

The original `prompt_hash` (used as the replay match key) is unchanged, so
all existing recorded logs remain playable. The new fields are emitted
**only** when injection actually occurs, preserving byte-identical
codegen output for every template without inject_message policies
(52/52 regression templates verified).

### Tests

- New `test_11_llm_request_event_has_post_inject_hash`
- New `test_12_no_inject_no_rehash_fields`
- New `test_13_post_inject_hash_matches_injected_messages`
- `tests/test_inject_message.py`: 27 -> 39 checks (all green)

### Compliance

This closes the audit gap where the recorded prompt hash did not reflect
the actual content sent to the LLM after governance-driven injection.
Auditors can now verify both what was requested and what was ultimately
transmitted.

---

## [4.8.0] - 2026-04-17

### Added - Phase G Layer 4: Governance Dashboard
- `governance.py`: PolicyInspector, GovernanceLog, GovernanceStats, InterventionRecord
- `GET /v1/governance/policies` - list active policies per world template
- `GET /v1/governance/interventions` - query intervention events from replay logs
- `GET /v1/governance/stats` - aggregated governance statistics
- `nous governance policies <file.nous>` - CLI policy inspector
- `nous governance inspect <log>` - CLI intervention event viewer
- `nous governance stats <log>` - CLI governance stats
- 30 governance dashboard tests (10 test functions, 30 assertions)
- `_signal_to_str()` - human-readable signal rendering from AST



## [4.7.0] - 2026-04-17
### Added - Phase G Governance, Layer 3: Intervention Primitive + Runtime Hook
- **`intervention.py`** - new module with `InterventionEngine`, `InterventionOutcome`, `InterventionError`, `InterventionBlocked`, `InterventionAborted`
  - Synchronous hot-path check with no-op mode when no rules loaded
  - Action priority resolution: `abort_cycle > block > inject_message > intervene > log_only`
  - `inject_message` stubbed to log_only for v4.7.0 (full semantics deferred to Layer 4)
- **`replay_runtime.py`** - `ReplayContext` gains `intervention_engine` param + `set_intervention_engine()` setter
  - Pre-emit hook at 3 sites: `sense.invoke`, `llm.request` (blocks cost before spend), `memory.write`
  - `governance.intervention` audit event emitted on every triggering (record mode only)
  - `block` raises `InterventionBlocked`, `abort_cycle` raises `InterventionAborted`
  - Replay + off modes: zero intervention logic (determinism preserved)
- **`risk_engine.py`** - predicate namespace expansion
  - `event.data` string-identifier keys now exposed as bare names in predicate scope
  - `cost > 0.10` works identically in `.nous` signals and YAML predicates
  - Reserved names (event fields, stats, `value`) take precedence on collision
  - Fully backward compatible - `data.get('cost', 0)` style YAML rules unchanged
- **`codegen.py`** - runtime engine wiring
  - Emits `from intervention import InterventionEngine` + `_INTERVENTION_ENGINE = InterventionEngine(_POLICIES, _POLICY_ACTIONS)` when policies exist
  - Emits `rt.replay_ctx.set_intervention_engine(_INTERVENTION_ENGINE)` in both simple and distributed `build_runtime()` paths
  - **Zero bytes emitted when no policies declared** - 40 regression templates byte-identical
- **`nous_api.py`** - `/v1/chat` maps `InterventionBlocked`/`InterventionAborted` to HTTP 422
  - Structured payload: `action`, `policies`, `score`, `reasons`, `triggering_event_kind`
  - Codes: `CHAT_INTERVENTION_BLOCKED`, `CHAT_INTERVENTION_ABORTED`
- **`tests/test_intervention.py`** - 10/10 E2E
  - All 5 actions exercised (log_only, intervene, inject_message, block, abort_cycle)
  - LLM block verified to prevent cost spend (execute() never runs)
  - Action priority resolution, codegen emission, generated module load
### Stability
- **40 regression templates byte-identical** throughout all 8 patches (54, 54b, 55, 56, 57c, 58, 59, 60)
- All 43 previous tests remain green
- **53 total replay+governance tests** (43 previous + 10 Intervention)
### Governance loop closed
- Layer 1 (RiskEngine, v4.5.0) + Layer 2 (Policy DSL, v4.6.0) + Layer 3 (Runtime enforcement, v4.7.0)

## [4.6.0] - 2026-04-17
### Added — Phase G Governance, Layer 2: Policy DSL
- **Grammar extension** — `policy NAME { ... }` blocks inside `world`
  - Keywords: `policy` | `πολιτική` (POLICY.2 terminal)
  - Clauses: `kind`, `signal`, `window`, `weight`, `action`, `description`
  - Actions: `log_only`, `intervene`, `block`, `inject_message`, `abort_cycle`
  - **Native NOUS expressions** as signals — type-checked at parse time, not runtime strings
- **AST nodes** — `PolicyNode` (Pydantic V2) with `PolicyAction` Literal enum
  - Rejects invalid actions at construction time (compile-time type safety)
  - `WorldNode.policies: list[PolicyNode]` default empty
- **Validator** — `_check_policies()` with 5 error codes
  - PL001 duplicate name, PL002 missing signal, PL003 weight range, PL004 negative window, PL005 empty kind
- **Codegen emission** — `_emit_policy_constants()`
  - Emits `_POLICIES: list[RiskRule] = [...]` + `_POLICY_ACTIONS: dict[str, str]`
  - Imports `risk_engine.RiskRule` only when policies present
  - Reuses `_expr_to_python` for signal → predicate translation (binop, not, compare)
  - **Zero bytes emitted when no policies declared** → 40 regression templates byte-identical
- **RiskRule** — extended with `action: str = "log_only"` field (backward compatible)
  - `from_dict` reads optional `action` from YAML
  - Existing YAML rules continue to work unchanged
- **`tests/test_policy_grammar.py`** — 10/10 E2E
  - Parse, AST typing, defaults, validator positive+negative, codegen emission, zero-output-without-policies, runtime RiskRule instantiation, py_compile

### Stability
- **40 regression templates remain byte-identical** — the critical gate
- All previous tests green: Foundation 7/7, Phase C 10/10, Phase D 6/6, Risk 10/10
- **43 total replay+governance tests** (7 + 10 + 6 + 10 + 10)

### Why 4.6.0 (minor bump)
Layer 2 closes the loop: policies now live in source code as first-class constructs,
compiled into the same `RiskRule` runtime used by Layer 1. Rules written in `.nous`
and rules loaded from YAML merge into a unified governance surface.
Layer 3 (Intervention primitive + runtime hook) follows in 4.7.0.


## [4.5.0] - 2026-04-17
### Added — Phase G Governance, Layer 1: RiskEngine
- **`risk_engine.py`** — runtime risk assessment over replay event logs
  - `RiskRule` (dataclass) — YAML-configurable rule: `kind_filter`, `predicate`, `weight`, `window`, `extract`
  - `RiskAssessment` — per-event score in [0,1] with `triggered_rules` + `reasoning`
  - `RiskReport` — aggregate over a full log (max/mean score, rule hits, per-event detail)
  - `RiskEngine.assess(event)` and `assess_log(path)` public API
  - Sandboxed predicate eval (no `__` names, no builtins) — safe to load untrusted rule YAML
  - Rolling per-(soul, rule) statistics for drift detection
- **`risk_rules.yaml`** — 7 default rules: `high_llm_cost`, `llm_token_burst`, `sense_error`, `memory_write_burst`, `cycle_duration_spike`, `llm_error`, `response_length_anomaly`
- **`nous replay <log> --risk-report`** — new CLI mode
  - `--rules YAML` — load custom ruleset
  - `--json` — machine-parseable output for CI/CD
  - `--verbose` — per-event triggered rows
  - Exit 0 = clean, 5 = triggered, 1 = I/O error
- **`tests/test_risk_engine.py`** — 10/10 E2E: default rules, clean log, each rule fires, custom YAML, sandbox escape blocked, JSON roundtrip

### Stability
- Zero changes to existing code — pure additive layer
- 40 regression templates remain byte-identical
- Phase A 7/7, Phase C 10/10, Phase D 6/6, Risk 10/10 — all green
- 33 total replay+governance tests

### Why 4.5.0 (minor bump)
Phase G (Governance) is a new capability layer, not a patch to Replay. Layer 1 ships the foundation (scoring); Layers 2-4 (grammar `law` blocks, `Intervention` primitive, dashboard) will follow in 4.6.0 / 4.7.0 / 4.8.0.


## [4.4.3] - 2026-04-17
### Added
- **Phase D — LLM Replay in API** — chat endpoint now supports deterministic LLM replay
- **`ReplayContext.record_or_replay_llm`** — coroutine wrap for any async LLM call
  - Events: `llm.request`, `llm.response`, `llm.error`
  - Match key: `sha256(provider | model | canonical(messages) | temperature)[:16]`
  - Prompt hash mismatch raises `ReplayDivergence`
  - Preserves cost, tokens_in, tokens_out, tier, elapsed_ms in recorded response
- **`ChatRequest`** extended with three optional fields: `replay_mode` (off|record|replay), `replay_log`, `replay_seed_base`
- **`tests/test_replay_phase_d.py`** — 6-step E2E harness (OFF passthrough, record roundtrip, replay hit, prompt-hash divergence, error record+replay, seed determinism)

### Changed
- `/v1/chat` handler wraps the tier-call loop under `ReplayContext` when `replay_mode != "off"`; default behavior unchanged

### Stability
- 40 regression templates remain byte-identical
- Phase A foundation: 7/7, Phase C E2E: 10/10, Phase D E2E: 6/6 — all green


## [1.4.0] - 2026-04-12

### Added
- **LALR parser** — 90.6x faster than Earley (3.3ms vs 324ms per parse)
- **Multi-world execution** — `nous run a.nous b.nous` runs worlds concurrently via asyncio.TaskGroup
- **multiworld.py** — WorldInstance, SharedChannelBus, MultiWorldRunner
- **Constitutional guards** — C001 (NoLiveTrading enforcement), C003 (MaxPositionSize warning), C004 (MaxDailyLoss warning)
- **ConstitutionalGuard class** in codegen — position check, daily loss circuit breaker, audit log
- **ccxt RSI-14** — Real OHLCV from Binance/Bybit/Gate/KuCoin/OKX with Wilder smoothing
- **Exchange fallback chain** — 5 exchanges, contract address detection, exotic quote skip
- **`_sense_*` methods** — Per-soul tool delegation to `self._runtime.sense()`
- **`WORLD_CONFIG` dict** — World config + env vars accessible in generated code
- **`model_rebuild()`** — After every Pydantic message class in codegen
- **infra_monitor.nous** — Example infrastructure monitoring world

### Changed
- **nous.lark** — Keyword priority `.2`, `remember_set`/`remember_add` split, `then_block`/`else_block` sub-rules
- **parser.py** — Zero workarounds, `_strip()` helper, `string_lit` returns `{"kind": "string_lit", "value": "..."}`
- **codegen.py** — `self` → `self.name`, `.where()` → `.filter()`, runtime integration in `run_world()`
- **validator.py** — Recursive tool scanning in if/for bodies, `_get_bool_law()`/`_get_currency_law()` helpers
- **cli.py** — v1.4.0, `nargs="+"` for multi-file support
- **gate_alpha_scan.py** — Pair format: `symbol/quote` instead of contract address
- **fetch_rsi.py** — Full rewrite with ccxt async

### Fixed
- `self` in .nous generating Python object instead of soul name string
- `.where(field > val)` crash — ToolResult has `.filter()` not `.where()`
- `world.config.X` generating undefined `world_config` variable
- Channels not connected to runtime
- Pydantic forward refs crash in dynamic import (model_rebuild fix)

## [1.1.0] - 2026-04-11

### Added
- Initial grammar, parser, AST nodes, validator, codegen
- CLI with compile/run/validate/evolve/nsp/info/bridge commands
- NSP protocol (70% token savings)
- Aevolver DNA mutation engine
- Migration tool (106 agents from YAML/TOML)
- VS Code extension
- Gate Alpha example (4 souls: Scout, Quant, Hunter, Monitor)

## [1.0.0] - 2026-04-10

### Added
- Project inception
- Grammar design (Lark EBNF)
- Core AST node definitions
