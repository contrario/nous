# NOUS Session 58 - Handoff

**Date:** 25 April 2026
**Server:** neurodoc-server-v2 (178.105.43.83) - post-migration
**Outcome:** v4.11.2 broken-template incident closed via v4.11.3 hotfix + architectural enforcement

---

## TL;DR

Session 58 began as architectural CC (single-source VERSION refactor). After server-migration verification, three blocking discoveries forced a pivot to emergency hotfix:

1. PyPI v4.11.2 wheel was shipping a stale grammar_data.py (pre-Phase-G governance) that lacked policy_decl / world_body rules.
2. The wheel had nous.lark declared in MANIFEST.in but absent from the actual installed wheel - fallback to stale grammar_data.py was always taken.
3. regression_harness was not gating shipped templates: sycophancy_guard.nous and governance_demo.nous (introduced Sessions 56-57) had never been compile-tested in CI.

---

## Verification - all green

- 178/178 pytest pass (3 pre-existing replay_phase_d fails)
- tests/test_grammar_sync.py 5/5
- Regression harness verify: 0 diffs (54 entries)
- Wheel content gate: nous.lark + grammar_data.py + 6 templates
- PyPI clean install: nous compile sycophancy_guard.nous -> exit 0
- Public https://nous-lang.org/v1/health: version 4.11.3
- GitHub tag v4.11.3 (69c772d) pushed
- PyPI nous-lang 4.11.3 live

---

## Open items for Session 59

HIGH:
- CC: Single-source VERSION constant (_version.py + dynamic version + test)

MEDIUM:
- Server B still on 4.11.2 (confirmed: 3c11c44). Needs: git fetch --tags --force && git checkout v4.11.3 && systemctl restart nous-api.
- replay_phase_d failures (pre-existing, Python 3.12 async deprecation).
- Homepage still shows v4.10.0 + old IP 188.245.245.132 in devAccess().

LOW:
- gitignore updated (backup patterns)
- Token in /root/.git-credentials chmod 600 - consider SSH key

---

## Operational lessons

1. Server-migration .git/ exclusion is silent killer. Workaround: re-init from GitHub + git reset --hard vX.Y.Z.
2. PyPI License-File field requires packaging>=24.2. Debian packaging==24.0 cannot be upgraded. Use isolated venv for twine.
3. MANIFEST.in include nous.lark is for sdist only. For wheel data files, use [tool.setuptools.data-files].
4. Regression harness must gate every shipped template.
5. PyPI JSON API lags ~60s behind upload. Simple index updates faster.
6. Defensive fallback in parser.py existed but no test covered it. Defense in depth needs defense-in-depth tests.

---

## Architectural pattern

Session 57: VERSION drift across files.
Session 58: Grammar drift between nous.lark and grammar_data.py.

Class of bug: dual sources without sync enforcement. Resolution pattern:
1. Single source of truth.
2. Idempotent generator script.
3rm enforcement test.
4. Wheel-content gate.

CC (Session 59) applies this pattern to VERSION.

End.