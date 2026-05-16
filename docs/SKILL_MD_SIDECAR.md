# NOUS SKILL.md Sidecar Format

This document describes the `nous.yaml` sidecar that lets NOUS produce
EU AI Act Annex IV-aligned compliance dossiers from existing
[agentskills.io](https://github.com/agentskills/agentskills) skills.

The sidecar is an *addition* to the skill directory; it does not
modify `SKILL.md` itself. Skill-spec validators (e.g. `skills-ref
validate`) continue to pass, and skill clients that do not know
about NOUS simply ignore the extra file.

<!-- __session77_docs_skill_md_sidecar_v1__ -->

## 1. Motivation

The agentskills.io ecosystem is growing fast. Snyk's February 2026
ToxicSkills audit found that 36.8% of public skills had security
flaws, 13.4% had critical issues, and 76 were confirmed malicious.
Independent third parties cannot verify a skill's runtime cost or
compliance posture without per-execution telemetry, which most
deployments do not capture.

The EU AI Act (Regulation (EU) 2024/1689), in force since August 2024,
requires high-risk AI providers to document the "design specifications,
namely the general logic of the AI system and the algorithms"
(Annex IV(2)(b)) and to ensure systems "operate consistently for their
intended purpose" (Article 15). Cost behavior is one such
"design choice" that providers must document.

`nous dossier-spec` bridges that gap by attaching, under Ed25519
signature, a formal SMT proof that a skill's declared cost budget
holds across every reachable execution path.

## 2. File layout

```
my-skill/
  SKILL.md       # unchanged; agentskills.io spec compliant
  nous.yaml      # this sidecar (or nous.yml)
```

Both `SKILL.md` / `skill.md` and `nous.yaml` / `nous.yml` are
recognized, in that order of preference. The frontmatter `name`
field in `SKILL.md` must equal the skill directory name (kebab-case,
1-64 chars, regex `^[a-z0-9]+(-[a-z0-9]+)*$`).

## 3. Sidecar schema (`nous.yaml`)

```yaml
spec_version: "1.0"
cost_cap: 0.50USD
default_model: claude-sonnet-4-6
tools:
  - name: web_search
    max_calls: 10
    input_tokens: 500
    output_tokens: 200
  - name: summarizer
    max_calls: 3
    input_tokens: 2000
    output_tokens: 500
    model: claude-haiku-4-5    # optional per-tool override
```

### 3.1 Top-level fields

| Field           | Type    | Required | Notes                                  |
|-----------------|---------|----------|----------------------------------------|
| `spec_version`  | string  | yes      | Must be `"1.0"`.                       |
| `cost_cap`      | string  | yes      | Format `<amount><CCY>`, e.g. `0.50EUR`. |
| `default_model` | string  | no       | Used when a tool has no own `model`.   |
| `tools`         | list    | yes      | At least one tool. No duplicate names. |

### 3.2 `tools[]` entries

| Field           | Type    | Required | Notes                                  |
|-----------------|---------|----------|----------------------------------------|
| `name`          | string  | yes      | 1-128 chars. Unique within `tools`.    |
| `max_calls`     | integer | yes      | >= 1.                                  |
| `input_tokens`  | integer | yes      | >= 0. Per-invocation upper bound.      |
| `output_tokens` | integer | yes      | >= 0. Per-invocation upper bound.      |
| `model`         | string  | no       | Overrides `default_model` for this tool. |

A tool with both `input_tokens` and `output_tokens` equal to zero is
rejected. Either `model` on the tool or `default_model` at the
sidecar level must be present; otherwise the translator raises a
`SkillMDError` naming the offending tool.

## 4. Currency support

The sidecar `cost_cap` accepts any ISO 4217 three-letter uppercase
code at parse time. The translator currently narrows to USD and EUR
only, matching the existing `ast_nodes.CostCap.currency` literal.
Other currencies raise a clear "ISO 4217 widening planned" error
at translation; widening is tracked for a future minor release.

## 5. CLI

```sh
nous dossier-spec <skill_dir> \
    [--cap <amount><CCY>] \
    [--prices <path>] \
    [--output <dir>] \
    [--smt-margin <pct>] \
    [--key <path>] \
    [--format annex_iv]
```

### 5.1 Flags

- `--cap` overrides the sidecar `cost_cap` for this run. Useful when
  the pricing TOML is denominated in USD but the sidecar declares
  the same skill's cap in EUR (or vice versa); the SMT layer rejects
  currency mismatches between cap and pricing.
- `--prices` overrides the layered pricing TOML lookup with an
  explicit path.
- `--output` defaults to `./<skill_name>_dossier_<UTC_timestamp>/`
  in the current working directory. The output directory must not
  exist or must be empty.
- `--smt-margin` adds a safety percent (0..99) to the cap before
  the proof, producing tighter dossiers. The manifest records the
  margin separately.
- `--key` overrides the default Ed25519 signing key path
  (`$XDG_DATA_HOME/nous/keys/signing.key`). If the key file does
  not exist, it is created with mode `0600` and parent dir `0700`.
- `--format` accepts only `annex_iv` at this time.

### 5.2 Exit codes

- `0` - dossier emitted, manifest signed, source SHA verified
- `1` - parse / translate / SMT / signing failure (`DossierSpecError`)
- `3` - argument error or missing skill directory

## 6. Output bundle

The emitted directory contains:

| File                | Purpose                                                 |
|---------------------|---------------------------------------------------------|
| `source.nous`       | Deterministic envelope wrapping SKILL.md + nous.yaml    |
| `manifest.json`     | Ed25519-signed manifest (canonical JSON, sorted keys)   |
| `SKILL.md`          | Verbatim copy of the input SKILL.md                     |
| `nous.yaml`         | Verbatim copy of the input sidecar                      |
| `pricing.toml`      | Resolved pricing TOML used in the proof                 |
| `public_key.b64`    | Raw Ed25519 public key, base64-encoded                  |
| `README.md`         | Human-readable Annex IV summary                         |
| `verify_offline.py` | Stand-alone verifier (cryptography lib only)            |

## 7. Source envelope format

The `source.nous` file is a deterministic byte sequence whose SHA-256
goes into the manifest. Layout (v1):

```
# NOUS skill_md dossier source envelope v1
# name: <skill_name>
# skill_md_sha256: <hex>
# sidecar_sha256: <hex>
# generator: nous-lang <version>

===== BEGIN SKILL.md =====
<verbatim SKILL.md bytes>
===== END SKILL.md =====

===== BEGIN nous.yaml =====
<verbatim nous.yaml bytes>
===== END nous.yaml =====
```

The per-file SHAs are embedded for forensic clarity; auditors can
independently re-compute them against `SKILL.md` and `nous.yaml` in
the dossier. `verify_offline.py` checks only the envelope SHA against
the manifest.

## 8. Translator semantics

`nous dossier-spec` runs the following pipeline:

1. `parse_skill_dir(skill_dir)` reads frontmatter, body, and sidecar.
2. `translate_to_program(parsed)` produces an internal `NousProgram`:
   - one `SoulNode` per tool with `tokens.input = max_calls * input_tokens` and `tokens.output = max_calls * output_tokens`
   - `world.cost_cap` from sidecar
   - `world.max_ticks = sum(tool.max_calls)` (strictest plausible bound)
3. `emit_smt(prog, pricing)` produces an SMT-LIB spec.
4. Z3 verifies the cost-cap obligation.
5. `manifest_from_verify(result, nous_version)` and `sign_manifest`
   produce the signed manifest.

The dossier bundle is then assembled and written atomically.

## 9. Verifying a dossier offline

```sh
cd <dossier_dir>
python3 verify_offline.py
```

The verifier confirms (a) the Ed25519 signature on `manifest.json`
verifies under `public_key.b64`, and (b) the SHA-256 of `source.nous`
matches `manifest.source_sha256`. It requires only the
`cryptography` Python library; no NOUS install needed.

## 10. Forward compatibility

The Manifest schema is unchanged in v5.1.0; skill_md dossiers use
the same Manifest as `nous dossier`. A `source_kind` discriminator
field is planned for v5.2.0 to enable programmatic differentiation
of `nous` vs `skill_md` dossier flavors.

The envelope format is versioned (`v1` today); future widenings (e.g.
multi-file skills, attached resources) will increment to `v2` while
keeping `verify_offline.py` format-agnostic via the source SHA check.
