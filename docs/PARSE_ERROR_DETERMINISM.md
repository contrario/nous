# Parse Error Determinism -- the same source gives the same parse-error text (S381)

<!-- __s381_parse_error_determinism_design_v1__ -->

Status: decisions D381-1 to D381-7 recorded before any code. Build notes
are appended in section 9 with the code that implements them.

Marking. [container] is a value measured in the chat container on a
clone of 1fc1fe6 whose bytes were tied to Server A by the 55 file shas
of the S381 RULE 0 paste (2026-09-26 12:45:58Z; a mutated control failed
1 of 1), on 2026-09-26 between 12:44Z and 13:02Z, Python 3.12.3, lark
1.3.1 from PyPI and lark master at 9a4fb9c7 in separate venvs.
[reading] is a statement from reading the source at 1fc1fe6. [external]
is a public source read live on 2026-09-26. [A] was printed on Server A.
The Innovation Gate for this unit is the S379 dossier
S379_GATE_PARSE_ERROR_DETERMINISM.md (sha256 784c2e64, not tracked):
PASS as a feature.

---

## 1. Problem

For the same source bytes, NOUS gives a different parse-error text in
different processes. The order of the "Expected one of" lines follows
the per-process string hash seed. A consumer that compares outputs byte
for byte cannot tell a change in NOUS from a change of seed, and no test
of a parse error with two or more expected tokens can be written. This
is axiom 2 (determinism makes evidence; the suite is held to the same
standard) applied to one output.

## 2. What the code does [reading]

- `parser.parse_nous` (parser.py:1422) calls `Lark.parse` on the cached
  LALR parser, then `NousTransformer().transform`. It is the one shipped
  entry that calls lark's parse; `parse_nous_file` and every other
  shipped caller go through it.
- lark raises `UnexpectedToken`, `UnexpectedCharacters` or
  `UnexpectedEOF`, all subclasses of `UnexpectedInput`. Their `__str__`
  calls `self._format_expected(...)` on `self.accepts or self.expected`,
  `self.allowed` and `self.expected` respectively. In lark 1.3.1
  `_format_expected` joins its argument in iteration order; the
  arguments are sets of terminal names, so the order is the hash order.
- Consumers of the text: the 422 bodies COMPILE001, VERIFY001, RUN001
  (nous_api_server.py:246, 348, 1165) and CHAT002 (1465, 1685); the CLI
  "Parse error:" lines (cli.py:76, 290, 305, 498, 517, 588, 636); the
  REPL (repl.py:373); the shipped LSP diagnostic (lsp_server.py:199);
  `nous dossier` failures (cli_dossier.py:89, which also prints
  `type(e).__name__`).
- nous-vscode/server/nous_lsp.py:146 is not in the wheel. It formats its
  own message by joining `e.expected`.
- regression_harness.py compares only whether a program has an error,
  not its text (lines 147-159).

## 3. Measurements [container]

    tracked .nous programs                       56
    programs that fail to parse                   8 (all UnexpectedToken)
    distinct texts over PYTHONHASHSEED 0..7, one process per seed,
    lark 1.3.1, unchanged tree:
      customer_service.nous                       8 of 8
      noosphere_migrated.nous                     5 of 8
      the other six                               1 each
    same seed twice                               identical, all eight
    `cli.py compile customer_service.nous`, seeds 1, 2, 1:
      rc 1 each; output sha256 95ca23cdfa38adf1, 0663d1a4e55459db,
      95ca23cdfa38adf1; 0.64 to 0.79 s per run

A scratch hook with the mechanism of D381-2 (outside the tree):

    distinct texts over seeds 0..7, lark 1.3.1    1 for each of the eight
    text equals lark master 9a4fb9c7, unhooked    yes, all eight
      customer_service.nous   ad9bf9cc4590ecc9, 268 bytes
      noosphere_migrated.nous 64af0e10a97d5133, 136 bytes
    the hook on lark master                       no change, all eight
    seed 0 of noosphere_migrated.nous, unhooked   already the sorted text

The raised object at seed 3, hooked, against a raw exception from the
same parser: `type(e)` is `lark.exceptions.UnexpectedToken` for both;
token, line, column, expected, considered_rules, state, token_history,
pos_in_stream, args and accepts are equal with the same types (expected
and accepts are sets); the only added state is the instance attribute
`_format_expected`. The class attributes of lark are unchanged, and a
second raw exception carries no such attribute. `pickle.dumps` and
`copy.copy` already fail on the raw lark exception (TypeError: cannot
pickle 'module' object; `__init__` missing arguments), and fail the same
way hooked.

lark versions [external, wheels from PyPI and the master source]:

    1.1.0 1.1.9 1.2.2 1.3.0 1.3.1   _format_expected defined on
                                    UnexpectedInput; the three __str__
                                    call it through self; none sorts
    master 9a4fb9c7                 one added line in exceptions.py,
                                    `expected = sorted(expected)`, before
                                    the terminal names map to user_repr;
                                    __version__ still "1.3.1"
    PyPI latest                     1.3.1, uploaded 2025-10-27
                                    ([external] 12:44Z; [A] 12:45:58Z)

K1 of the Gate does not fire: no release that sorts is on PyPI.

## 4. Cause

Python salts str hashes per process unless PYTHONHASHSEED is set. lark
1.3.1 prints a set of terminal names in iteration order. Nothing in NOUS
orders it. Upstream master orders it; no release carries that line.

## 5. Scope of the change

One function in parser.py and its tests. No grammar, AST, codegen,
verifier, API schema or pricing change. No new module.

## 6. Reasons the chosen design should not exist (Article V)

- R1. Upstream already sorts on master; a lark release makes the hook
  redundant. Answer: the hook is idempotent against a sorting lark
  (measured on master) and is removed when the floor reaches that
  release (D381-4).
- R2. The hook names a private lark method. Answer: present and called
  through self in every release from 1.1.0 to master (K5); if a later
  lark stops calling it, the hook is inert and the tests of D381-5 go
  red, so the loss is detected, not silent.
- R3. The text is not evidence; no manifest carries it. Answer: the
  harm is reproducibility for byte-comparing consumers and for tests,
  which axiom 2 covers.
- R4. PYTHONHASHSEED fixed in the service unit is one line. Answer:
  rejected in the Gate (S379 R3): it covers the service only and turns
  off hash randomization on an internet-facing parser of client JSON.
- R5. The 422 text changes once more, after skillctx captured bodies.
  Answer: order only, for two tracked programs, from random to fixed,
  once; skillctx gets a note (D381-7).
- R6. An attribute set on an exception instance is unusual. Answer: it
  is the one design that leaves the class, the public attributes and
  their types exactly as lark raised them (D381-2).
- R7. The tests depend on two example programs staying broken. Answer:
  each subprocess checks that the text starts with "Unexpected token",
  so a program that starts to parse turns the test red with that
  reason; it cannot pass as stable.

## 7. Decisions

- D381-1. Claim. For identical source bytes, grammar and lark version,
  `str(e)` of an `UnexpectedInput` raised by `parse_nous` is
  byte-identical across processes and PYTHONHASHSEED values. The order
  of the expected lines is lark master's: terminal names sorted with
  `sorted()` before they map to their display form. Nothing else in the
  text changes.
- D381-2. Mechanism. `parse_nous` wraps only the `Lark.parse` call. On
  `UnexpectedInput` it sets, on that one instance, the attribute
  `_format_expected` to a bound function that calls the class's own
  `_format_expected` with `sorted(expected)`, and re-raises the same
  object with a bare `raise`. Not chosen: the class swap of the S379
  scratch probe (it changes `type(e)`, which cli_dossier.py:89 and every
  traceback print); sorting `expected` and `allowed` into lists (it
  changes a public attribute's type in a patch release, and the text of
  UnexpectedToken reads `accepts`, which lark computes later, so it
  would also need lark's private `_accepts`); constructing a new
  exception (constructor signatures differ across the supported range,
  and identity and traceback change); PYTHONHASHSEED in the unit (R4);
  any process-wide patch of lark (K4).
- D381-3. What the object keeps (K2). `type(e)` is lark's class; token,
  line, column, expected, allowed, accepts and every other attribute
  keep value and type; the one added state is the instance attribute.
  lark's classes are not modified (K4): an exception raised by any other
  Lark instance in the same process is unaffected. The transform step
  is not wrapped.
- D381-4. lark floor. It stays `lark>=1.1.0` in 6.0.1; the hook works
  from 1.1.0 to master. When a lark release sorts, the floor may be
  raised to it and the hook removed in the same change; until then the
  hook stays. Outstanding, not scheduled.
- D381-5. Tests, red first by set and reason, in
  tests/test_s381_parse_error_determinism.py. Red on the tree before
  the patch: the text is the same over PYTHONHASHSEED 0..7 for
  customer_service.nous and for noosphere_migrated.nous; for every seed
  the expected lines of both are in sorted terminal-name order; the CLI
  `compile customer_service.nous` output is the same over seeds 1, 2
  and 3. Green before the patch, by design, because they guard the fix
  rather than detect the defect: the same seed twice gives the same
  text (the control for the seed tests); the object from `parse_nous`
  has the class and attributes of a raw exception from the same parser
  (K2); lark's classes carry no NOUS attribute and a raw exception has
  no override (K4). Every subprocess output must start with
  "Unexpected token" (R7). K3 over all eight tracked failing programs
  and seeds 0..7 is a probe printed on Server A after the apply, not a
  test.
- D381-6. Out of scope. nous-vscode/server/nous_lsp.py (not in the
  wheel) joins `e.expected`, which stays a set under D381-2, so its
  message stays in hash order; outstanding. Other error texts
  (verifier, typechecker, runtime) are not audited for hash order. The
  422 body shape does not change (RFC 9457 stays a separate arc). No
  harness rebaseline (section 2). No codegen change, so no
  templates/trading_floor.py regeneration.
- D381-7. Release and consumers. The fix ships as 6.0.1 by the release
  procedure of the S381 opener section 5, with a CHANGELOG entry under
  6.0.1, the floor and the homepage hero in the bump commit. Server A
  and Server B restart after the release, each with its own approval.
  After the restarts, a live 422 on Server A for customer_service.nous
  is compared with the text the tests pin, and skillctx gets a note:
  the 422 `detail.error` text of customer_service.nous and
  noosphere_migrated.nous changes once, in the order of the expected
  lines only; the other six tracked failing programs are unchanged; the
  CLI line changes the same way.

## 8. Honest boundary

The tests of D381-5 evidence byte-stable parse-error text within one
NOUS release and one lark version, for two tracked programs over the
seeds tested; the probe of D381-5 evidences it for all eight tracked
failing programs over seeds 0..7. No Z3 or Farkas leg is involved. The
change does not make the text stable across lark versions or grammar
changes, does not define an error schema, does not change any other
error text, and does not order the attributes `expected`, `allowed` or
`accepts`, which remain lark's sets. No signed or anchored artifact
carries parse-error text: a parse failure happens before any manifest
exists.

## 9. Build notes

### 9.1 Patch B (S381)

- parser.py: the imports marked `__s381_pe_imports_v1__`
  (`UnexpectedInput`, `Iterable`, `MethodType`); the function
  `_format_expected_sorted` (`__s381_pe_sorted_v1__`); the except
  branch of `parse_nous` (`__s381_pe_hook_v1__`). The two pyflakes
  findings parser.py already had (unused `Tree`, unused `ListenNode`)
  are left as they were.
- tests/test_s381_parse_error_determinism.py
  (`__s381_parse_error_determinism_v1__`), 8 ids. Red before the fix:
  test_text_same_across_hash_seeds[customer_service.nous] and
  [noosphere_migrated.nous], test_expected_lines_in_sorted_terminal_order
  [customer_service.nous] and [noosphere_migrated.nous],
  test_cli_parse_error_same_across_hash_seeds. Green before and after:
  test_same_seed_control, test_raised_object_keeps_lark_class_and_attributes,
  test_no_process_wide_patch_of_lark.
- [container, clone 76ae8e2] Before the fix: 5 failed, 3 passed, with
  8 and 5 distinct texts over seeds 0..7, unsorted lines at seeds 0..7
  and at 1, 2, 3, 5, 6, 7, and 3 distinct CLI outputs over seeds 1, 2,
  3. With the fix: 8 passed. The patch refuses to write the fix unless
  these five ids fail on Server A, each with its reason, and the other
  three pass.
- K3 [container]: with the fix, each of the eight tracked failing
  programs gives one text over seeds 0..7, the same text as under lark
  master 9a4fb9c7. The patch prints the same probe on Server A.
- CHANGELOG.md: a Fixed entry under [Unreleased]
  (`__s381_changelog_parse_error_v1__`); the release moves it under
  6.0.1.
- regression_harness.py: 59 entries, 0 diffs, 0 new errors; no
  rebaseline (section 2).
