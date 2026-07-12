# Claim-Boundary Linter

`scripts/claim_lint.py` + `claims.toml`

A deterministic, repo-local gate that checks one thing: **a reserved claim word
may appear at a site only if that site satisfies a declared, mechanically
decidable justification predicate, or is explicitly allowlisted with a written
reason.**

Stdlib only (`ast`, `tokenize`, `html.parser`, `tomllib`). No new dependency, no
network, no model at judgement time. It runs wherever the offline verifier runs.

---

## The honest boundary of this tool

Read this first. The tool that catches overclaims must not overclaim.

- It checks **conformance to a declared convention**. It does **not** determine
  whether any claim is TRUE. It performs no semantic understanding.
- It cannot detect a capability the config does not name. The forbidden-object
  set is a blocklist, and blocklists are incomplete by construction.
- Passing this linter **EVIDENCES** that no declared reserved word appears
  without its declared justification. It **PROVES** nothing about the
  correctness of the system it scans.
- The word "proves" is reserved, in NOUS, strictly for the three Z3/Farkas legs:
  cost-cap, policy-coverage, sequence-ordering. This tool is not one of them.

### Declared blind spots

Named, not omitted. Each is a real, live example from this repo.

1. **Attribution flaws.** `behavioral_diff.py` routes a material change by
   telling the reader to run the real SMT leg. The string names properties that
   another command genuinely establishes -- so there is no forbidden object, no
   axis binding, and no negation. **No predicate fires. The tool does not catch
   it.** Catching it needs semantics, which is the line this tool does not
   cross.
2. **Claim-class errors.** `README.md` describes a decidable boolean check over
   an already-committed finite set with the reserved word. The wrongness is the
   CLASS of the claim -- a decidable check is tier VERIFIED, not tier PROVEN --
   and the sentence carries no forbidden object. **The tool does not catch it.**
3. **Proof counts inside JavaScript data literals.** The pre-S224 homepage
   carried "7 proof categories" inside a `<script>` cards array. Script contents
   are never scanned, so the `stat` predicate does not see it. Catching it needs
   a JS data-literal extractor. Named, banked, NOT built.
4. **Counts laundered through a variable.** The axis predicate binds a rendered
   word to the nearest preceding f-string expression. A value copied into an
   unrelated local first is invisible.
5. **`str.format()` and `%`-formatting** are not axis-checked. f-strings only.
6. **The false-fix-marker class.** A marker asserting a fix that was never
   applied. Needs a marker bound to a test with a negative control. Out of
   scope, named, banked.

Blind spots 1, 2 and 3 are live in the tree today and this tool will not find
them. That is stated here so nobody reads a green run as a clean bill of health.

---

## What it is for

**The honest framing changed when the tool was actually run, and the earlier one
is left here because the correction is the point.**

Before the first scan I wrote: *regression prevention and audit-cost collapse,
not discovery -- the discovery is done, sessions 224 through 229 found the
family by hand, and the first run may well find nothing new.*

The first real scan found **ten live honest-boundary defects** those five
sessions missed, including one inside `dossier.py` -- the offline-verifier
template written into **every Annex IV dossier NOUS has ever emitted**, telling
auditors the signature "Proves manifest authorship" while the API endpoint tells
the same auditor it PROVES nothing and NOUS certifies no identity.

So the corrected framing: **a declared-convention linter finds what hand audit
structurally cannot, because hand audit greps what it remembers and this greps
what is declared.** Five passes over these surfaces, by a human and by several
models, searched the places that came to mind. The linter searched the places
the convention names. Those are not the same set, and the difference is where
the defects were.

It remains true that the tool is deterministic, pinned to a commit, and cannot
be primed, raced, or argued out of its verdict. That was always its structural
advantage. Discovery turned out to be a consequence of it, not a separate claim.

---

## The predicates

A reserved word is **never** a violation on its own. Only a reserved word plus a
**failed predicate** is. `nous_api_server.py` says an agent "ensures customer
satisfaction" -- reserved word, no forbidden object, no violation.

### 1. axis (Python only)

`verifier.py` carries a dual axis on every `VerificationItem`:

| field | set by | meaning |
|---|---|---|
| `severity` | `prove()` AND `verify()` AND `estimate()` AND `report()` | a count of it is a count of STATIC CHECKS |
| `tier` | discriminates | only the Z3/Farkas SMT leg is tier PROVEN |

`VerificationResult.proven` filters the **severity** axis, so the property name
is itself the trap. An f-string that renders a reserved word from a value bound
to `severity` or `.proven` renders a static-check count as a proof count.

```
f"VERIFIED: {len(result.proven)} proven"        -> forbidden field -> VIOLATION
f"{tproven} proven, {tverified} verified"       -> required field  -> OK
```

Both of those are real bytes: the first was the S228 defect, the second is
`verifier.py` doing it correctly. The two separate on the attribute name alone.

### 2. object

A forbidden object bound to a reserved claim word. Bidirectional, because the
motivating defect was **passive**:

- **Backward (active):** the object binds to the nearest preceding claim word in
  its sentence. If that word is reserved, violation. If it is allowed
  (`verifies`, `records`, `evidences`, `certifies`, ...), pass.
- **Forward (passive):** object + copula + reserved participle. The pre-fix API
  string put the object BEFORE the verb; a backward-only rule would have missed
  the one case that mattered.

The backward rule is why the current homepage passes. It says the system
"statically verifies" seven structural-safety categories and then lists them --
the objects bind back to `verifies`, which is allowed. The pre-S224 version used
the reserved word in the same position, and the objects bound back to that. Same
clause, same words, separated on the byte, with no semantics.

### 3. stat (HTML only)

A block whose entire text is a bare numeral, immediately followed by a block
naming a proof noun, asserts a proof count. It must equal `declared_proof_legs`
(3).

```
<div>31+</div><div>Formal Proofs</div>      -> 31 != 3 -> VIOLATION
<div>3</div><div>Z3/Farkas Proofs</div>     -> 3  == 3 -> OK   (live today)
<div>62</div><div>CLI Commands</div>        -> no proof noun -> ignored
<div>1</div><div>Envelope proof</div>       -> SINGULAR -> ignored
```

**Plural only.** The singular "proof" appears as a numbered CARD TITLE ("1 /
Envelope proof"), where the numeral is an ordinal, not a cardinality. Matching it
was a real false positive on the current homepage, caught on the first live run of
this predicate. A stat card that states a count always pluralises. The cost: a
hypothetical card reading "5 / Formal Proof" would be missed. Stated, not hidden.

**This replaces a predicate that was killed on its first real scan.** v1 had a
prose `count` rule -- a numeral whose first following counted noun was a proof
noun. On the live tree it produced **24 hits and 0 true positives: a 100%
false-positive rate.** The error was conceptual, not a missing exemption. "N
proofs" in English is a cardinality of proof INSTANCES -- "one static proof to
many runtime certificates", "two proofs shipped in the last weeks" -- not an
assertion about how many Z3/Farkas legs NOUS has. It also fired on version
strings (`SMT-LIB 2.6`), math (`"0 < 0" => UNSAT proof`), list markers (`5.
Inner proof:`) and timestamps (`0:30 to 2:00 -- Live proof`). A predicate with
no true positives is not a predicate. The stat card is the only shape that
actually makes the claim.

---

## The exemptions

False positives are a defect, not a cost of doing business. A noisy gate gets
disabled, and then it protects nothing.

| | rule | kills |
|---|---|---|
| **E1** | negation, **token-scoped** (+/- 3), deliberately **not** sentence-scoped | `proves nothing`; `we do not guarantee` |
| **E2** | terms of art: inclusion proof, consistency proof, coverage proof, proof obligation | most of `rekor_v2_offline.py` |
| **E3** | identifiers are never scanned -- the walker visits only string constants, f-strings, docstrings and comments | every `*_proofs` variable and every `.proven` attribute. **This is why the tool is AST-based and not a regex.** |
| **E4** | excluded paths: signed and sha-pinned artifacts, tests, generated code | a linter that demands an edit to a signed artifact breaks the signature |
| **E5** | a literal whose entire value is one reserved token is SCHEMA | the `PROVEN` enum and the `"proven"` JSON key -- separated mechanically, not allowlisted |
| **E6** | use vs mention: a reserved word wrapped in quotes, or inside a double-quoted / backticked span | the API string that declares the reservation rule; a doc that QUOTES a known overclaim as an example. Without E6 the linter flags the sentence stating its own rule, and flags this README for quoting the defects it found. |

**E1 is token-scoped for a reason, and the reason is a real near-miss.** The
pre-fix API sentence read: the identity claim, then "but there is no public log
entry confirming when this dossier was issued." A **sentence**-scoped negation
exemption would have seen that "no" and exempted the one string that mattered. A
tight token window does not.

**E6 uses double quotes and backticks as span delimiters, never single quotes.**
An apostrophe (`the manifest's canonical bytes`) would open a span that swallowed
the rest of the sentence and silently exempted a real claim. The word-adjacent
rule still covers the `'proves' is reserved` form.

E6 is verified NOT to mask the real defects: all eight prose sites found on the
live tree still flag with the span rule enabled. But it is an exemption, and an
exemption can mask: **a genuine claim that happens to sit inside a quoted span
will not be flagged.** Stated, not hidden.

---

## The allowlist

Bounded escape hatch. Each entry carries `path`, `line`, `word`, a **written
reason**, and the `sha256` of the justifying line.

If that line changes, the sha stops matching and the entry is reported as
**STALE** with a non-zero exit. It rots loudly instead of silently protecting
text it was never reviewed against.

An allowlist entry that matches nothing is also reported. Dead entries do not
accumulate.

---

## Dropped from v1: call-graph reachability

The original design called for binding the reserved word to a call-graph path
into the Z3/Farkas symbols. It is **dropped as unsound**: a name-based call graph
over this tree, with CLI dispatch tables, will miss a real dispatch edge and flag
a legitimate site. An unsound predicate inside a blocking gate is the noisy gate
that gets disabled, and then it protects nothing. Banked, with the caveat
written down.

---

## Usage

```
python3 scripts/claim_lint.py --config claims.toml --root . \
    --anchor $(git rev-parse HEAD)
```

`--anchor` records the commit the scan is pinned to. It is recorded, not
verified. **On a shared checkout, a byte read is only valid against a named
commit** -- a read with no referent is not evidence of anything.

`--sarif` emits SARIF 2.1.0. `--json` emits the raw findings. Exit is non-zero on
any violation or any stale allowlist entry.

Not wired into `scripts/release.py`. Wiring it into the release gate is a
separate decision.
