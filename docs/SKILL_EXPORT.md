# NOUS Skill Export

This document describes the `nous skill-export` workflow that
translates a `.nous` program into a spec-compliant
[agentskills.io](https://github.com/agentskills/agentskills) skill,
optionally bundled with an EU AI Act Annex IV-aligned signed dossier.

The export is the inverse of the
[SKILL.md sidecar](SKILL_MD_SIDECAR.md) flow: where the sidecar
attaches NOUS compliance to an *existing* skill, the export emits a
fresh skill from *existing NOUS source*. Both flows produce
byte-identical Annex IV dossiers when fed equivalent inputs.

<!-- __session77_docs_skill_export_v1__ -->

## 1. Motivation

NOUS users write self-evolving agentic programs in the `.nous`
language. Many of these programs are useful beyond their original
deployment: a market monitor, a customer-service triager, a content
summarizer. The agentskills.io ecosystem is the de-facto
distribution channel for such reusable agent capabilities, with
26+ platforms (Claude Code, OpenAI Codex, Gemini CLI, GitHub Copilot,
Cursor, VS Code, and others) consuming the format.

Without a translation path, NOUS users had to hand-author SKILL.md
files separately from their `.nous` source, with no mechanical
guarantee that the two stayed in sync. `nous skill-export` removes
that gap: a single source produces both the runtime artifact (the
`.nous` program) and the publishable skill artifact (SKILL.md +
nous.yaml + optional signed dossier), with a deterministic mapping
between them.

## 2. Translation surface

The translation is **lossy and one-way**. The agentskills.io subset
is strictly smaller than the `.nous` language:

| `.nous` construct      | SKILL.md / nous.yaml projection            |
|------------------------|--------------------------------------------|
| `world` name           | kebab-case skill `name` (auto-derived)     |
| `law cost_<x> = $A per cycle` | `cost_cap: "<A><CCY>"` in nous.yaml |
| `soul` -> `senses` list       | flattened union -> tool list        |
| `soul` -> `mind: model @ tier`| most-frequent model -> `default_model` |
| message contracts             | dropped (not expressible)           |
| nervous_system topology       | dropped                             |
| instinct bodies               | dropped                             |
| mitosis / immune / telemetry  | dropped                             |
| heal rules                    | dropped                             |

The dropped constructs are not lost in the runtime: they continue to
govern the original `.nous` program. They are simply not expressible
in the agentskills.io schema, so the emitted skill carries only the
projection that the schema can hold.

The cost envelope is what makes the export valuable: the SKILL.md +
nous.yaml pair carries enough information to run NOUS's SMT solver
and prove that the skill's declared cost cap holds across every
reachable execution. The dropped constructs do not affect that proof.

## 3. Surfaces

`nous skill-export` is exposed through three independent surfaces.
All three call the same underlying `skill_export.export_skill()`
function and produce byte-identical output for the same inputs.

### 3.1 CLI

```
nous skill-export INPUT.nous
    --description "<one-line description>"
    [--output DIR]
    [--name <skill-name>]
    [--license <license>]
    [--compatibility <constraint>]
```

**Arguments**

| Flag              | Required | Default                          | Notes |
|-------------------|----------|----------------------------------|-------|
| `INPUT.nous`      | yes      | -                                | positional |
| `--description`   | yes      | -                                | 1-1024 chars |
| `--output`        | no       | `<input-stem>.skill/`            | created if missing |
| `--name`          | no       | kebab-case of world name         | regex `^[a-z0-9]+(-[a-z0-9]+)*$` |
| `--license`       | no       | omitted from frontmatter         | 1-64 chars |
| `--compatibility` | no       | omitted from frontmatter         | 1-500 chars, free-form |

**Output**

```
<output-dir>/
  SKILL.md
  nous.yaml
```

The CLI surface emits only the skill files. To produce a signed
dossier from the emitted skill, run `nous dossier-spec
<output-dir>` afterwards.

### 3.2 HTTP API

```
POST /v1/skill/export
Content-Type: application/json
X-API-Key: <key>
```

**Request body**

```json
{
  "source": "<.nous source text>",
  "description": "<1-1024 char description>",
  "skill_name": "<optional kebab-case override>",
  "license": "<optional license identifier>",
  "compatibility": "<optional compatibility constraint>",
  "tool_overrides": [
    {
      "name": "<sense_name>",
      "max_calls": 5,
      "input_tokens": 300,
      "output_tokens": 150,
      "model": "<optional per-tool model>"
    }
  ],
  "with_dossier": true
}
```

| Field             | Required | Default | Notes |
|-------------------|----------|---------|-------|
| `source`          | yes      | -       | 1-100,000 chars |
| `description`     | yes      | -       | 1-1024 chars |
| `skill_name`      | no       | derived | kebab-case |
| `license`         | no       | omitted | 1-64 chars |
| `compatibility`   | no       | omitted | 1-500 chars |
| `tool_overrides`  | no       | `[]`    | per-tool budget tuning |
| `with_dossier`    | no       | `true`  | if false, zip omits dossier dir |

**Response**

- `200 OK` -> `application/zip` payload (see Section 4 for layout);
  headers carry `Content-Disposition: attachment; filename="<skill>.zip"`
  and `X-Skill-Name: <resolved-name>`.
- `408 Request Timeout` -> `{"error": "skill-export timed out (60s)",
  "code": "TIMEOUT003"}` if the SMT step exceeds 60 seconds.
- `422 Unprocessable Entity` -> `{"error": "<message>",
  "code": "SKILLEXPORT001"}` for every other refusal (parse failure,
  cost-law absence, name violation, etc.).

Rate-limited to **10 requests per minute per API key**. The
ephemeral Ed25519 signing key is generated inside the request handler,
used once to sign the manifest, then discarded; no signing key
material persists on the server.

### 3.3 IDE button

The NOUS IDE (`/ide.html`) exposes an **Export Skill** button in the
editor toolbar, next to **Download .py**. Clicking the button:

1. Prompts for the skill description (required).
2. Prompts for an optional kebab-case skill name (blank = auto-derive).
3. Prompts for the X-API-Key on first use; stored in `localStorage`
   for subsequent calls.
4. POSTs the current editor buffer to `/v1/skill/export` with
   `with_dossier: true`.
5. Streams the resulting zip back to the browser as a download.

The IDE flow always requests `with_dossier: true`. To export without
a dossier, use the CLI or the API directly.

## 4. Output bundle

When `with_dossier: true` (default), the zip contains:

```
<skill-name>/
  SKILL.md
  nous.yaml
  dossier/
    source.nous          # deterministic envelope (SKILL.md + nous.yaml bytes)
    manifest.json        # signed manifest (canonical JSON, sorted keys)
    SKILL.md             # verbatim copy
    nous.yaml            # verbatim copy
    pricing.toml         # resolved pricing layer (SHA in manifest)
    public_key.b64       # Ed25519 public key, raw base64
    README.md            # human-readable Annex IV summary
    verify_offline.py    # stand-alone offline verifier
```

When `with_dossier: false`, the zip contains only the top two files
(`SKILL.md` and `nous.yaml`) under the `<skill-name>/` directory.

The dossier directory is byte-identical to what `nous dossier-spec`
would produce when run against the emitted skill directory, with one
exception: the **signing key is ephemeral**. Each request generates
a fresh Ed25519 keypair, signs the manifest with it, and discards
the private key before returning. The `public_key.b64` file is
sufficient for offline verification with `verify_offline.py`, but
the bundle cannot be re-signed by re-running the export.

If you want a stable signing key across many exports (e.g. a single
verifying key for your entire organization), use the CLI surface
with `nous skill-export` followed by `nous dossier-spec --key
PATH`, where `PATH` references a persistent Ed25519 private key.

## 5. Cost cap derivation

The cost cap in the emitted `nous.yaml` is derived from the **first
`law cost_<name> = $<amount> per cycle`** declaration found in the
world block. The world-level `cost_cap: <amount> <currency>` shorthand
(used in `nous emit-smt` demo files) is **not** currently recognized
by `skill_export`; if your `.nous` program uses that form, the export
will refuse with:

```
ERROR: world '<X>' has no cost law; cannot derive cost_cap.
Add a 'law cost_<name> = $<amount> per cycle' declaration.
```

The two forms are semantically equivalent at runtime; only the export
path requires the explicit `law` syntax. Recognition of the shorthand
is tracked for a future minor.

## 6. Tool budget defaults and overrides

Each unique `sense` name across all souls becomes one entry in the
emitted `tools:` list. The default budget per tool is:

| Field           | Default |
|-----------------|---------|
| `max_calls`     | 10      |
| `input_tokens`  | 500     |
| `output_tokens` | 200     |

The defaults are deliberately generous for a first export; in
practice, tighter per-tool budgets produce tighter SMT proofs. Use
`tool_overrides` (HTTP API) or post-export edits to `nous.yaml`
(CLI / IDE) to narrow the budgets, then re-run `nous dossier-spec`
to produce a sharper compliance dossier.

The `model` field on a tool override specializes the per-call model
for that tool. When omitted, the tool uses the sidecar's
`default_model` (which itself is the most-frequent `mind: model`
across souls, ties broken by first occurrence).

## 7. Determinism

`skill_export.export_skill()` is **byte-deterministic**: the same
`NousProgram` plus the same `ExportRequest` always produces the same
`(skill_md, nous_yaml)` pair. No timestamps, no random IDs, no
host-dependent information enter the emitted text. This determinism
is required by the downstream `source.nous` envelope, whose SHA-256
anchors the signed manifest.

The dossier bundle as a whole is **not** byte-deterministic across
calls, because the Ed25519 signature varies per ephemeral keypair.
The manifest's `source_sha256` and `pricing_sha256` fields, however,
are deterministic given the same inputs.

## 8. Refusal conditions

`skill_export.export_skill()` refuses (raises `SkillExportError`)
when:

- The program has no `world` block.
- The world has no `law cost_<name> = $<amount> per cycle` declaration.
- The derived cost is non-positive (`amount <= 0`).
- The cost currency is not a 3-letter ISO 4217 code.
- The program has no `sense` declared across all souls
  (zero tools -> sidecar fails validation).
- The derived or supplied skill name is not agentskills.io-compliant
  (regex `^[a-z0-9]+(-[a-z0-9]+)*$`, 1-64 chars).

All refusals are surfaced verbatim through the CLI (`stderr`, exit 1),
the HTTP API (`422` with `code: "SKILLEXPORT001"`), and the IDE
(`alert("Export failed: ...")`).

## 9. End-to-end verification

Whether produced via the CLI, the API, or the IDE, every dossier
bundle is verifiable offline using only the standard
`cryptography` Python library:

```
cd <skill-name>/dossier/
python3 verify_offline.py
```

A passing verification produces:

```
OK   Ed25519 signature verified
OK   source.sha256 matches manifest (<sha-prefix>...)

VERDICT: PASS
  world:      <skill-name>
  cost_cap:   $<amount> <currency>
  verdict:    proven
  solver:     z3 <version>
  timestamp:  <iso-8601>
```

The verifier checks two things: (a) the Ed25519 signature on
`manifest.json` verifies under `public_key.b64`, and (b) the SHA-256
of `source.nous` matches the value in the manifest. That is the
entire chain of custody.

## 10. What this is and is not

The export covers:

- A spec-compliant agentskills.io SKILL.md.
- A NOUS sidecar (`nous.yaml`) declaring cost and tool budgets.
- An optional Ed25519-signed Annex IV-aligned dossier with formal
  SMT proof of cost-cap satisfaction.

The export does **not** cover:

- Prompt-injection vulnerability assessment.
- Output toxicity, IP leakage, or PII-handling checks.
- Runtime behavior beyond cost (latency, accuracy, robustness).
- Translation of NOUS constructs the agentskills.io schema cannot
  hold (instincts, mitosis, immune, nervous-system topology).
- Stable signing keys for the API and IDE surfaces; both use
  ephemeral keys per request.

For the constructs the agentskills.io schema cannot hold, ship the
original `.nous` program alongside the skill. The skill is the
discovery and admission surface; the `.nous` program is the runtime
authority.
