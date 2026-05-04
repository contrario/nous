---
name: Bug report
about: Report a defect in the NOUS toolchain, runtime, or HTTP API
title: "bug: <short description>"
labels: ["bug", "triage"]
assignees: []
---

<!-- __session71_community_files_v1__ -->

## Summary

<!-- One or two sentences describing what is broken. -->

## Expected behaviour

<!-- What you expected to happen. -->

## Actual behaviour

<!-- What actually happened. Paste the full error message, not
     a summary. Use a code block. -->

```
<exact output here>
```

## Reproducer

<!-- A minimal `.nous` source file (or sequence of CLI / API
     calls) that triggers the bug. Smaller is better; a 30-line
     file is great, a whole project is hard to triage. -->

```nous
world Repro {
    cost_cap: 0.10 USD
    max_ticks: 1
    soul A {
        mind: claude-haiku-4-5 @ Tier3
        tokens: input=100 output=50
    }
}
```

Exact command(s) that triggered the bug:

```
$ nous verify --smt repro.nous
```

## Environment

- **NOUS version:** <!-- output of `nous version`, or
  `pip show nous-lang | grep Version` -->
- **Python version:** <!-- `python3 --version` -->
- **OS:** <!-- e.g. Ubuntu 24.04, macOS 14, Windows 11 + WSL2 -->
- **Install type:** <!-- one of: clean venv, editable (`pip install -e .`),
  system Python, Docker, other -->
- **Z3 version (if SMT-related):** <!-- `python3 -c "import z3;
  print(z3.get_version())"` -->

## Additional context

<!-- Anything else relevant: pricing TOML if non-default,
     replay log excerpt, screenshot of dashboard, etc.
     Redact secrets and personal data before pasting. -->

## Checklist before submitting

- [ ] I have searched existing issues for duplicates.
- [ ] I have included a minimal reproducer.
- [ ] I have included the exact NOUS version.
- [ ] I have redacted any secrets, API keys, or personal data.
- [ ] If this is a security vulnerability, I am reporting it
      via GitHub Security Advisories instead:
      https://github.com/contrario/nous/security/advisories/new
